"""Build a Gemini orchestrator with a shared policy gate for harness dispatch.

AgentTool includes app plugins by default. Vendor inner actions remain outside
this gate; see harness_agent.py.
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

from adk_harness.coding.harness_agent import HarnessAgent
from adk_harness.coding.protocol import HarnessSpec
from adk_harness.coding.registry import HarnessRegistry
from adk_harness.governance import CoactraGovernance
from adk_harness.governance.precedents import PrecedentStore

__all__ = ["DEFAULT_MODEL", "Fleet", "build_fleet", "build_fleet_sync"]

DEFAULT_MODEL = "gemini-3.5-flash"
"""Resolves only on the `global` Vertex location. Set GOOGLE_CLOUD_LOCATION=global."""


@dataclass(frozen=True, slots=True)
class Fleet:
    """The ADK app, discovered harnesses, and governance API for audits and human decisions."""

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
    """Discover harnesses and build a governed ADK app.

    Raises RuntimeError when no harness is available.
    """
    specs = await registry.discover_all()
    available = registry.available()
    if not available:
        detail = "; ".join(f"{s.id}: {s.detail or 'unavailable'}" for s in specs)
        raise RuntimeError(
            "no coding-agent harness is available here "
            f"({detail or 'none registered'}). Next: run `adk-harness doctor`, "
            "install/configure a harness, then retry."
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

    tools: list[Any] = [
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
    """Describe available harnesses and require the model to respect refusals."""
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
    """Build a fleet during an ADK module import.

    Uses a worker thread when an event loop is already running. Prefer the async
    build_fleet() when callers can await.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_fleet(**kwargs))

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(build_fleet(**kwargs))).result()
