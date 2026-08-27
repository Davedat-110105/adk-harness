"""Record a governed, externally-visible Google Workspace action, end to end.

`capture_precedent_loop.py` proves the loop with a stub harness. This proves it
with a real one: the fleet asks a human before putting an event on a real Google
Calendar, the human answers once, and the second identical request proceeds
without interrupting anyone — creating an event other people can see.

    GOOGLE_CLOUD_PROJECT=... python examples/capture_workspace_governance.py

Needs Application Default Credentials carrying `calendar.events`:

    gcloud auth application-default login \\
        --client-id-file=client_secret.json \\
        --scopes=openid,https://www.googleapis.com/auth/userinfo.email,\\
https://www.googleapis.com/auth/cloud-platform,\\
https://www.googleapis.com/auth/calendar.events

The event this creates is deleted before the script exits. Pass `--keep` to
leave it in place for a live demo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness import Applicability, HarnessRegistry, build_fleet
from adk_harness.adapters import CalendarHarness

EVENT = {
    "summary": "Horizon Health grant — internal review",
    "description": "Scheduled by a governed agent fleet under human approval.",
    "start": {"dateTime": "2026-09-11T15:00:00-04:00"},
    "end": {"dateTime": "2026-09-11T16:00:00-04:00"},
}
TASK = (
    "Schedule the Horizon Health grant internal review. Delegate it to the "
    "calendar harness with exactly this event body: " + json.dumps(EVENT)
)


class WorkspacePolicy:
    """Reading is free. Anything other people will see asks a person first.

    The distinction that matters is not "is this a write" but "does this leave
    a mark someone else can see". A calendar event does. That is why it is the
    honest thing to gate, and why approving it once — rather than every time —
    is worth building.
    """

    async def check(self, request: PolicyRequest) -> Decision:
        args = request.context.get("tool_args") or {}
        instruction = " ".join(
            str(v) for v in args.values() if isinstance(v, str)
        ).lower()

        if "attendees" in instruction or "@" in instruction.replace("dateTime", ""):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    "The event names external attendees. Inviting people "
                    "outside the institution is never done without a person."
                ),
                source="workspace-policy",
            )
        return Decision(
            outcome=DecisionOutcome.requires_approval,
            reason="Creating a calendar event is visible to other people.",
            source="workspace-policy",
        )


def rule(title: str) -> None:
    print(f"\n{'─' * 74}\n{title}\n{'─' * 74}")


async def ask(fleet, session: str) -> None:
    service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=service)
    await service.create_session(
        app_name=fleet.app.name, user_id="admin", session_id=session
    )
    message = types.Content(role="user", parts=[types.Part(text=TASK)])
    async for event in runner.run_async(
        user_id="admin", session_id=session, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  gemini: {part.text.strip()[:260]}")


def _created_ids(harness: CalendarHarness) -> list[str]:
    return list(getattr(harness, "created_event_ids", []))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true", help="leave the created event in place"
    )
    args = parser.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    harness = CalendarHarness(dry_run=False)
    spec = await harness.discover()
    if not spec.available:
        print(f"Calendar unavailable: {spec.detail}", file=sys.stderr)
        return 1

    fleet = await build_fleet(
        registry=HarnessRegistry([harness]),
        policy=WorkspacePolicy(),
        scope=Scope(tenant_id="university_a", namespace="grants"),
        cwd="/workspace",
        principal="user:research_admin",
        name="grant_fleet",
    )
    gate = fleet.governance

    print(f"model:     {fleet.orchestrator.model}")
    print(f"harness:   {spec.id} {spec.version} — {spec.detail}")
    print("action:    create a real event on a real Google Calendar")

    rule("RUN 1 — nobody has approved this. The calendar is not touched.")
    await ask(fleet, "run-1")
    for record in gate.audit:
        print(f"  gate: {record.outcome:<22} {record.reason or ''}")
    print(f"  events created: {len(_created_ids(harness))}   <- nothing happened")

    rule("THE ADMINISTRATOR ANSWERS ONCE, with a scope they choose")
    precedent = gate.remember(
        tool_name="run_google_calendar",
        precedent_id="pr-2026-08-27-internal-review",
        applicability=(Applicability("tool", "eq", "run_google_calendar"),),
        decision={"approve": True},
        rationale=(
            "Internal review slots on our own calendar are routine and "
            "reversible. Approved without further review."
        ),
        confirmed_by="research_admin",
    )
    scope = [f"{a.field} {a.operator} {a.value!r}" for a in precedent.applicability]
    print(f"  precedent: {precedent.precedent_id}")
    print(f"  scope:     {scope}")

    before = len(gate.audit)
    rule("RUN 2 — same request. No interruption. A real event appears.")
    await ask(fleet, "run-2")
    for record in gate.audit[before:]:
        print(f"  gate: {record.outcome:<22} {record.reason or ''}")

    created = _created_ids(harness)
    print(f"  events created: {len(created)}")
    for event_id in created:
        print(f"  event id: {event_id}")

    rule("WHAT THIS DOES AND DOES NOT CLAIM")
    print("  The gate decided about a real, externally visible action, and the")
    print("  work did not happen until a person approved it. Precedent removed")
    print("  the second question, never the gate, and never a deny.")
    print("  Inner tool calls of a harness are observed, not gated — see agent.py.")

    if created and not args.keep:
        removed = await harness.delete_events(created)
        print(f"\n  cleaned up {removed} event(s) — pass --keep to leave them.")

    asked = sum(1 for r in gate.audit if r.outcome == "asked_human")
    print(f"\nHuman interrupted {asked} time(s) across 2 identical requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
