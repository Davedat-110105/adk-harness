"""Run the fleet on a real repository, with the real harnesses installed here.

This is the one that is not a demo. `examples/agents/fleet` registers a stub so the
Cloud Run container has something to dispatch to; this registers Codex, Claude
Code and opencode, points them at a directory you name, and lets them do actual
work under the governance gate.

    python examples/scripts/run_fleet_on_repository.py "Add a docstring to src/adk_harness/coding/registry.py"
    python examples/scripts/run_fleet_on_repository.py --cwd ../coactra "Find unused exports"
    python examples/scripts/run_fleet_on_repository.py --precedents ~/.adk-harness.db "..."

Precedents persist to SQLite when you pass `--precedents`, which is what makes
the second run of a similar task quieter than the first. Without it the store
is in-process and every question gets asked again.

What is actually enforced
-------------------------
The gate decides *dispatch*: whether this harness may work in this directory on
this instruction. A harness's own file edits and shell commands run inside its
own process and never return through ADK, so they are streamed and audited but
not individually gated. Read `src/adk_harness/harness_agent.py` before pointing this at
anything you would mind having edited.

Requires GOOGLE_GENAI_USE_ENTERPRISE=true, GOOGLE_CLOUD_PROJECT, and
GOOGLE_CLOUD_LOCATION=global.
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
from adk_harness.coding.adapters import (
    AntigravityHarness,
    ClaudeCodeHarness,
    CodexHarness,
    OpenCodeHarness,
)

# Matched against the instruction, not against a path. A fleet dispatch resolves
# to one working directory, so a rule reading only the resource would answer
# identically every time.
ASK_FIRST = ("release", "publish", "deploy", "migration", "force", "rewrite history")
NEVER = ("secret", "credential", "api key", "password", "token", ".env")


class RepoPolicy:
    """Edit the source freely; stop and think before anything outward-facing.

    The interesting outcome is the middle one. Anything that leaves this
    machine — a release, a deploy, a force-push — is a decision a person should
    make once, deliberately. After they make it, `remember()` turns that answer
    into a precedent and they stop being asked.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def check(self, request: PolicyRequest) -> Decision:
        # coactra 0.7 puts the tool in `resource` and dispatch facts in
        # `context`, so the working directory is read from there.
        cwd = Path(str(request.context.get("cwd") or ".")).resolve()
        if self._root not in (cwd, *cwd.parents):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"{cwd} is outside {self._root}.",
                source="repo-policy",
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
                source="repo-policy",
            )

        sensitive = next((w for w in ASK_FIRST if w in instruction), None)
        if sensitive is not None:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=(
                    f"The instruction mentions {sensitive!r}, which reaches "
                    "outside this machine."
                ),
                source="repo-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"Ordinary source work under {self._root}.",
            source="repo-policy",
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="what you want done")
    parser.add_argument("--cwd", default=".", help="repository to work in")
    parser.add_argument(
        "--precedents",
        default=None,
        help="SQLite file for precedents; omit to forget answers on exit",
    )
    parser.add_argument("--model", default=None, help="override the orchestrator model")
    args = parser.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    root = Path(args.cwd).resolve()
    store = SQLitePrecedentStore(args.precedents) if args.precedents else None

    # Antigravity is given the Vertex project explicitly rather than left to
    # find an env var, so it is configured the same way the rest of this
    # project is: Vertex and ADC, never a Gemini API key.
    registry = HarnessRegistry(
        [
            CodexHarness(),
            ClaudeCodeHarness(),
            OpenCodeHarness(),
            AntigravityHarness(
                vertex=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            ),
        ]
    )
    kwargs = {"model": args.model} if args.model else {}
    fleet = await build_fleet(
        registry=registry,
        policy=RepoPolicy(root),
        scope=Scope(tenant_id="local", namespace="dogfood"),
        cwd=str(root),
        principal=f"user:{os.environ.get('USER', 'local')}",
        precedents=store,
        name="dogfood",
        **kwargs,
    )

    for spec in fleet.specs:
        state = "ready" if spec.available else f"unavailable ({spec.detail})"
        print(f"  {spec.id:<12} {spec.version:<12} {state}")
    print(f"\nworking in {root}\n")

    session_service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=session_service)
    await session_service.create_session(
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

    print("\n--- what the gate decided ---")
    for record in fleet.governance.audit:
        reason = f" — {record.reason}" if record.reason else ""
        print(f"  {record.outcome:<22} {record.tool_name}{reason}")

    if any(r.outcome == "asked_human" for r in fleet.governance.audit):
        print(
            "\nA question is outstanding. Answer it once with "
            "fleet.governance.remember(...) and, with --precedents set, it will "
            "not be asked again."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
