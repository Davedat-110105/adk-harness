"""Assemble a governed fleet: one Gemini orchestrator, many harnesses.

`build_fleet` is the function most users of this SDK will call. It takes a
registry of harnesses and returns an ADK `App` — a Gemini agent that can
dispatch work to whichever harnesses are installed, with a single Coactra
policy gate in front of all of them.

One gate, not one per harness. That is the point of the whole library. If each
harness carried its own permission model, the answer to "may this happen?" would
depend on which harness the orchestrator happened to pick, and a fleet whose
rules vary by worker is not governed — it is merely supervised, inconsistently.
So the gate, the audit trail, and the precedent store are shared, and every
dispatch passes through them identically.

The gate fires because ADK's `AgentTool` defaults to `include_plugins=True`,
which routes tool calls made against a wrapped agent through the app's plugins.
See `agent.py` for exactly what the gate does and does not cover.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from coactra import Policy, Scope
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App
from google.adk.tools.agent_tool import AgentTool

from adk_harness.agent import HarnessAgent
from adk_harness.governance import CoactraGovernance
from adk_harness.precedent import PrecedentStore
from adk_harness.protocol import HarnessSpec
from adk_harness.registry import HarnessRegistry

__all__ = ["Fleet", "build_fleet", "build_fleet_sync", "DEFAULT_MODEL"]

DEFAULT_MODEL = "gemini-3.5-flash"
"""Resolves only on the `global` Vertex location. Set GOOGLE_CLOUD_LOCATION=global."""


@dataclass(frozen=True, slots=True)
class Fleet:
    """Everything the caller needs to run and to answer for a fleet.

    `governance` is returned rather than hidden because a human has to be able
    to reach it: to read the audit trail, and to call `remember()` when they
    answer a confirmation, which is what stops the same question being asked
    again tomorrow.
    """

    app: App
    orchestrator: LlmAgent
    governance: CoactraGovernance
    specs: tuple[HarnessSpec, ...]

    @property
    def available_ids(self) -> tuple[str, ...]:
        return tuple(spec.id for spec in self.specs if spec.available)


async def build_fleet(
    *,
    registry: HarnessRegistry,
    policy: Policy,
    scope: Scope,
    cwd: str,
    model: str = DEFAULT_MODEL,
    principal: str = "user:local",
    precedents: PrecedentStore | None = None,
    name: str = "fleet",
    instruction: str | None = None,
    skip_summarization: bool = False,
) -> Fleet:
    """Discover what is installed and wire it into one governed app.

    Discovery happens here rather than being left to the caller because the
    orchestrator's instruction has to name the harnesses that actually exist.
    Telling a model it may delegate to Codex on a machine without Codex
    produces confident dispatch to nothing.

    Raises `RuntimeError` when no harness is available. That is a real dead end
    — an orchestrator with no workers cannot do the one thing it is for — and
    failing at build time gives a clearer message than failing at dispatch.
    """
    specs = await registry.discover_all()
    available = registry.available()
    if not available:
        detail = "; ".join(f"{s.id}: {s.detail or 'unavailable'}" for s in specs)
        raise RuntimeError(
            f"no coding-agent harness is available here ({detail or 'none registered'})"
        )

    governance = CoactraGovernance(
        policy=policy,
        scope=scope,
        principal=principal,
        precedents=precedents,
        # An AgentTool call carries only the instruction text, so the gate
        # cannot see where the harness will work unless it is told here.
        resources={_tool_name(h.spec.id): cwd for h in available},
    )

    tools = [
        AgentTool(
            agent=HarnessAgent(
                name=_tool_name(harness.spec.id),
                description=_describe(harness.spec),
                harness=harness,
                cwd=cwd,
            ),
            skip_summarization=skip_summarization,
        )
        for harness in available
    ]

    orchestrator = LlmAgent(
        name=name,
        model=model,
        description="Routes coding work to whichever harnesses are installed.",
        instruction=instruction or _instruction(specs, cwd),
        tools=tools,
    )

    return Fleet(
        app=App(name=name, root_agent=orchestrator, plugins=[governance]),
        orchestrator=orchestrator,
        governance=governance,
        specs=specs,
    )


def _tool_name(harness_id: str) -> str:
    """`claude-code` is a fine harness id and an invalid function name."""
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", harness_id).strip("_").lower()
    return f"run_{cleaned or 'harness'}"


def _describe(spec: HarnessSpec) -> str:
    caps = ", ".join(spec.capabilities) if spec.capabilities else "general coding"
    return f"Delegate a coding task to {spec.id} {spec.version} ({caps})."


def _instruction(specs: Sequence[HarnessSpec], cwd: str) -> str:
    """Tell the model what it has, and tell it the truth about refusals.

    The last paragraph matters more than it looks. When policy denies a tool
    call, the gate returns a blocked result rather than raising, precisely so
    the model can report the refusal to the user. A model that instead retries
    the same call in a loop, or invents a workaround, turns a clean governance
    decision into a mess. So it is instructed not to.
    """
    lines = []
    for spec in specs:
        if spec.available:
            lines.append(f"- {_tool_name(spec.id)}: {spec.id} {spec.version}")
        else:
            lines.append(f"- ({spec.id} is not installed here: {spec.detail})")
    roster = "\n".join(lines)

    return (
        "You coordinate a fleet of coding agents working in the repository at "
        f"{cwd}.\n\n"
        f"Available harnesses:\n{roster}\n\n"
        "Choose one harness per task and give it a complete, self-contained "
        "instruction: it cannot see this conversation. Prefer one harness doing "
        "one whole task over several doing fragments of it.\n\n"
        "Every dispatch passes through a policy gate. If a call comes back with "
        "status 'blocked', that is a decision, not a transient failure. Report "
        "the reason to the user and stop. Do not retry it, do not route the same "
        "work to a different harness, and do not look for another way to achieve "
        "it. If the gate instead asks a human to confirm, wait for the answer."
    )


def build_fleet_sync(**kwargs: Any) -> Fleet:
    """Build a fleet from a module-level import.

    ADK's deployment convention is to `import` a module and read `app` off it,
    which means the fleet has to exist before anything awaits. Discovery is
    async — it probes several harnesses concurrently — so this bridges the two.

    If a loop is already running (ADK's web server loads agent modules from
    inside one), `asyncio.run` would raise, so the build is handed to a worker
    thread. Discovery is I/O against local binaries, so a thread is the right
    shape for it and the wait is short.

    Prefer `build_fleet` anywhere you can already await.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_fleet(**kwargs))

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(build_fleet(**kwargs))).result()
