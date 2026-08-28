"""Your three local harnesses, in the ADK web UI, on your machine.

    opencode serve --port 4096 &
    GOOGLE_CLOUD_PROJECT=... adk web examples

Then open the printed localhost URL and pick **local**. You type; Gemini decides
which of Codex, opencode or Antigravity should do the work; every dispatch meets
the policy gate first.

Everything executes here. The only thing that leaves your machine is the
orchestrator's own model call to Vertex, plus whatever each harness does on its
own account.

Nothing is deployed and nothing is shared. `examples/workspace` is the one meant
for a team; this one is for you.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness import HarnessRegistry, SQLitePrecedentStore, build_fleet
from adk_harness.adapters import AntigravityHarness, CodexHarness, OpenCodeHarness

WORKSPACE = Path(os.environ.get("ADK_HARNESS_WORKSPACE", Path.cwd())).resolve()
PRECEDENTS = os.environ.get("ADK_PRECEDENTS")

# Matched against the instruction, because a fleet dispatch resolves to one
# directory and a rule reading only the path would answer identically each time.
#
# Whole words, not substrings. A first version matched "token" anywhere and
# refused a request that merely used the word in a sentence — a gate that fires
# on prose it does not understand teaches people to ignore it.
NEVER = ("secret", "secrets", "credential", "credentials", "password", "passwords")
NEVER_PHRASES = ("api key", "access token", "auth token", ".env")
ASK_FIRST = ("delete", "remove", "force", "push", "publish", "deploy", "rm")


def _words(text: str) -> set[str]:
    return set("".join(c if c.isalnum() else " " for c in text.lower()).split())


class LocalPolicy:
    """Read and edit freely here. Destructive or outward-facing work asks."""

    def __init__(self, root: Path) -> None:
        self._root = str(root)

    async def check(self, request: PolicyRequest) -> Decision:
        cwd = str(request.context.get("cwd") or "")
        if not cwd.startswith(self._root):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"{cwd or '(unknown)'} is outside {self._root}.",
                source="local-policy",
            )

        args = request.context.get("tool_args") or {}
        text = " ".join(str(v) for v in args.values() if isinstance(v, str)).lower()
        words = _words(text)

        hit = next((w for w in NEVER if w in words), None) or next(
            (p for p in NEVER_PHRASES if p in text), None
        )
        if hit is not None:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"The instruction asks about {hit!r}. Not by an agent.",
                source="local-policy",
            )

        risky = next((w for w in ASK_FIRST if w in words), None)
        if risky is not None:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"The instruction says {risky!r}, which is hard to undo.",
                source="local-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"Ordinary work under {self._root}.",
            source="local-policy",
        )


async def _build():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    registry = HarnessRegistry(
        [
            CodexHarness(),
            OpenCodeHarness(),
            AntigravityHarness(
                vertex=True,
                project=project or None,
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            ),
        ]
    )
    return await build_fleet(
        registry=registry,
        policy=LocalPolicy(WORKSPACE),
        scope=Scope(tenant_id="local", namespace="desktop"),
        cwd=str(WORKSPACE),
        principal=f"user:{os.environ.get('USER', 'local')}",
        precedents=SQLitePrecedentStore(PRECEDENTS) if PRECEDENTS else None,
        name="local",
        instruction=(
            f"You coordinate coding agents working in {WORKSPACE}.\n\n"
            "Pick one harness per task and give it a complete, self-contained "
            "instruction — it cannot see this conversation. Prefer one harness "
            "doing a whole task over several doing fragments.\n\n"
            "Every dispatch passes a policy gate. A 'blocked' result is a "
            "decision, not a transient error: report the reason and stop. Do "
            "not retry, and do not route the same work to a different harness. "
            "If the gate asks a human to confirm, wait for the answer."
        ),
    )


def _fleet():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_build())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_build())).result()


fleet = _fleet()
app = fleet.app
governance = fleet.governance
