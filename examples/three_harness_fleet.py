"""Three coding harnesses, three integration shapes, one governance gate.

Codex is a CLI subprocess parsing JSONL. opencode is an HTTP server with an SSE
event stream. Antigravity is a Google SDK driving a local runtime against
Vertex. They have nothing in common, and a Gemini orchestrator routes across all
three without knowing the difference.

    opencode serve --port 4096 &
    GOOGLE_CLOUD_PROJECT=... python examples/three_harness_fleet.py "your task"

Everything runs locally. The only thing on the network is the orchestrator's own
model call to Vertex, and whatever the harnesses do themselves.

What the gate covers here
-------------------------
Dispatch: whether this harness may work in this directory on this instruction.
The file edits and shell commands a harness makes inside its own process do not
return through ADK, so they are streamed and audited rather than approved. That
is the honest boundary — `src/adk_harness/workspace.py` is where per-operation
gating happens, because Google's own toolsets expose each operation separately.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness import HarnessRegistry, SQLitePrecedentStore, build_fleet
from adk_harness.adapters import AntigravityHarness, CodexHarness, OpenCodeHarness

# Matched against the instruction the orchestrator writes, since a fleet
# dispatch resolves to one working directory and a rule reading only the path
# would answer identically every time.
NEVER = ("secret", "credential", "api key", "password", "token", ".env")
ASK_FIRST = ("delete", "remove", "rm ", "force", "push", "publish", "deploy")


class LocalRepoPolicy:
    """Read and edit freely. Destructive or outward-facing work asks first."""

    def __init__(self, root: Path) -> None:
        self._root = str(root.resolve())

    async def check(self, request: PolicyRequest) -> Decision:
        cwd = str(request.context.get("cwd") or "")
        if not cwd.startswith(self._root):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"{cwd or '(unknown)'} is outside {self._root}.",
                source="local-policy",
            )

        args = request.context.get("tool_args") or {}
        instruction = " ".join(
            str(v) for v in args.values() if isinstance(v, str)
        ).lower()

        forbidden = next((w for w in NEVER if w in instruction), None)
        if forbidden is not None:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"The instruction mentions {forbidden!r}. Not by an agent.",
                source="local-policy",
            )

        risky = next((w for w in ASK_FIRST if w in instruction), None)
        if risky is not None:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"The instruction mentions {risky!r}, which is hard to undo.",
                source="local-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"Ordinary work under {self._root}.",
            source="local-policy",
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="what you want done")
    parser.add_argument("--cwd", default=".", help="repository to work in")
    parser.add_argument("--precedents", default=None, help="SQLite file for answers")
    parser.add_argument(
        "--opencode-url", default="http://127.0.0.1:4096", help="opencode serve URL"
    )
    args = parser.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    root = Path(args.cwd).resolve()
    registry = HarnessRegistry(
        [
            CodexHarness(),
            OpenCodeHarness(base_url=args.opencode_url),
            AntigravityHarness(
                vertex=True,
                project=project,
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            ),
        ]
    )

    fleet = await build_fleet(
        registry=registry,
        policy=LocalRepoPolicy(root),
        scope=Scope(tenant_id="local", namespace="three"),
        cwd=str(root),
        principal=f"user:{os.environ.get('USER', 'local')}",
        precedents=SQLitePrecedentStore(args.precedents) if args.precedents else None,
        name="three_harness_fleet",
    )

    print("harnesses:")
    for spec in fleet.specs:
        state = "ready" if spec.available else f"unavailable — {spec.detail}"
        print(f"  {spec.id:<12} {spec.version:<12} {state}")
    print(f"\nworking in {root}\n{'─' * 74}")

    service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=service)
    await service.create_session(
        app_name=fleet.app.name, user_id="local", session_id="s"
    )
    message = types.Content(role="user", parts=[types.Part(text=args.task)])
    async for event in runner.run_async(
        user_id="local", session_id="s", new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)

    print(f"{'─' * 74}\nwhat the gate decided:")
    for record in fleet.governance.audit:
        reason = f" — {record.reason}" if record.reason else ""
        print(f"  {record.tool_name:<22} {record.outcome:<22}{reason}")

    dispatched = {r.tool_name for r in fleet.governance.audit}
    print(f"\nharnesses actually dispatched to: {len(dispatched)} of {len(fleet.available_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
