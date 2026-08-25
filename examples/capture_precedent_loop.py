"""Record the precedent loop end to end, against real Gemini on Vertex.

The output of this script is the artifact: a transcript showing a human being
asked once, answering once, and never being asked again. Run it and paste the
output into docs; it is meant to be read, not just executed.

    GOOGLE_CLOUD_PROJECT=... python examples/capture_precedent_loop.py

Every model call here is real. Nothing is stubbed except the harness itself,
which is a stand-in so the transcript is about governance rather than about
whichever coding CLI happens to be installed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness import (
    Applicability,
    HarnessRegistry,
    HarnessSpec,
    HarnessTurn,
    build_fleet,
)

TASK = "Bump the replica count in the prod deploy config. Delegate it to a harness."


class RecordingHarness:
    """Stands in for a coding agent, and records whether it was ever reached."""

    def __init__(self) -> None:
        self.spec = HarnessSpec(
            id="demo", version="stub", capabilities=("edit",), available=True
        )
        self.dispatches: list[str] = []

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        self.dispatches.append(prompt)
        yield HarnessTurn(kind="text", text=f"Edited the deploy config in {cwd}.")

    async def aclose(self) -> None:
        return None


class ProdNeedsAHuman:
    """Ordinary work proceeds. Production configuration asks a person."""

    async def check(self, request: PolicyRequest) -> Decision:
        args = request.context.get("tool_args") or {}
        instruction = " ".join(
            str(v) for v in args.values() if isinstance(v, str)
        ).lower()
        if "prod" in instruction:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason="The instruction touches production configuration.",
                source="demo-policy",
            )
        return Decision(
            outcome=DecisionOutcome.allow, reason="Ordinary work.", source="demo-policy"
        )


def rule(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")


async def ask(fleet, harness: RecordingHarness, session: str) -> None:
    service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=service)
    await service.create_session(
        app_name=fleet.app.name, user_id="dave", session_id=session
    )
    message = types.Content(role="user", parts=[types.Part(text=TASK)])
    async for event in runner.run_async(
        user_id="dave", session_id=session, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  gemini: {part.text.strip()[:300]}")


async def main() -> int:
    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    harness = RecordingHarness()
    fleet = await build_fleet(
        registry=HarnessRegistry([harness]),
        policy=ProdNeedsAHuman(),
        scope=Scope(tenant_id="acme", namespace="fleet"),
        cwd="/workspace",
        principal="user:dave",
        name="governed_fleet",
    )
    gate = fleet.governance

    print(f"model:     {fleet.orchestrator.model}")
    print(f"harnesses: {[s.id for s in fleet.specs]}")
    print(f"task:      {TASK}")

    rule("RUN 1 — no precedent exists, so a human is asked")
    await ask(fleet, harness, "run-1")
    for record in gate.audit:
        print(f"  gate: {record.outcome:<22} {record.reason or ''}")
    print(f"  harness reached: {bool(harness.dispatches)}   <- work did not happen")

    rule("THE HUMAN ANSWERS, ONCE — with a scope they choose themselves")
    precedent = gate.remember(
        tool_name="run_demo",
        precedent_id="pr-2026-08-25-replicas",
        applicability=(Applicability("tool", "eq", "run_demo"),),
        decision={"approve": True},
        rationale="Replica counts are reversible and monitored. Approved.",
        confirmed_by="dave",
    )
    print(f"  precedent: {precedent.precedent_id}")
    print(f"  scope:     {[f'{a.field} {a.operator} {a.value!r}' for a in precedent.applicability]}")
    print("  note:      applicability is passed explicitly, never inferred from the answer")

    before = len(gate.audit)
    rule("RUN 2 — same question, same conditions. Nobody is interrupted.")
    await ask(fleet, harness, "run-2")
    for record in gate.audit[before:]:
        print(f"  gate: {record.outcome:<22} {record.reason or ''}")
    print(f"  harness reached: {bool(harness.dispatches)}   <- work happened")

    rule("WHAT IS NOT CLAIMED")
    print("  Precedent removes a repeated question. It never removes the gate,")
    print("  and it never turns a deny into an allow. A precedent whose")
    print("  predicates do not hold is not applied; a fact that is missing is")
    print("  never treated as a match. See src/adk_harness/precedent.py.")

    asked = sum(1 for r in gate.audit if r.outcome == "asked_human")
    print(f"\nHuman was interrupted {asked} time(s) across 2 runs of the same task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
