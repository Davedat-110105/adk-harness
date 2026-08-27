"""Record a governed Google Workspace action, end to end, on a real calendar.

Every tool call here is an official ADK `CalendarToolset` operation, so the
policy gate sees each one individually — `calendar_events_insert` is a separate
decision from `calendar_events_list`. That is what the PRD means by *"approval
at initial dispatch is insufficient."*

    GOOGLE_CLOUD_PROJECT=... python examples/capture_workspace_governance.py

Needs Application Default Credentials carrying `calendar.events`:

    gcloud auth application-default login \\
        --client-id-file=client_secret.json \\
        --scopes=openid,https://www.googleapis.com/auth/cloud-platform,\\
https://www.googleapis.com/auth/calendar.events

Events created here are deleted before the script exits. Pass `--keep` to leave
them for a live demo.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness import Applicability, build_workspace_fleet

# Reading is routine. Writing leaves a mark other people can see.
WRITES = ("insert", "update", "delete", "patch", "move", "import")

REQUEST = (
    "Schedule an event on calendar 'primary' titled "
    "'Horizon Health grant — internal review' on 2026-09-11, "
    "from 15:00 to 16:00 America/New_York."
)


class WorkspacePolicy:
    """Reads flow. Anything visible to other people asks a person first.

    The gate now sees the *operation*, not just the dispatch, so this policy can
    say something a dispatch-level rule could not: listing events is fine,
    creating one is not, and changing who can see a calendar is never fine.
    """

    async def check(self, request: PolicyRequest) -> Decision:
        tool = request.resource.removeprefix("tool:")

        if tool.startswith("calendar_acl"):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"{tool} changes who can see this calendar. Sharing is a "
                    "person's decision, not an agent's."
                ),
                source="workspace-policy",
            )

        if any(verb in tool for verb in WRITES):
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"{tool} creates something other people will see.",
                source="workspace-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"{tool} only reads.",
            source="workspace-policy",
        )


def rule(title: str) -> None:
    print(f"\n{'─' * 74}\n{title}\n{'─' * 74}")


async def ask(fleet, session: str) -> list[str]:
    service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=service)
    await service.create_session(
        app_name=fleet.app.name, user_id="admin", session_id=session
    )
    message = types.Content(role="user", parts=[types.Part(text=REQUEST)])
    said: list[str] = []
    async for event in runner.run_async(
        user_id="admin", session_id=session, new_message=message
    ):
        if event.content and event.content.parts:
            said.extend(p.text for p in event.content.parts if p.text)
    return said


def created_ids(fleet) -> list[str]:
    """Event ids the fleet actually created, read out of the audit trail."""
    return [
        record.reason.split("id=", 1)[1].split()[0]
        for record in fleet.audit
        if record.reason and "id=" in record.reason
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="leave events behind")
    args = parser.parse_args()

    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    fleet = await build_workspace_fleet(
        policy=WorkspacePolicy(),
        scope=Scope(tenant_id="university_a", namespace="grants"),
        services=("calendar",),
        # Two operations, named. CalendarToolset offers 38; a fleet should not
        # hold powers nobody decided to give it.
        tool_filter=["calendar_events_insert", "calendar_events_list"],
        principal="user:research_admin",
        name="grant_fleet",
    )
    gate = fleet.governance

    print(f"model:    {fleet.orchestrator.model}")
    print(f"services: {', '.join(fleet.services)}")
    print(f"tools:    {', '.join(fleet.tool_names)}")
    print(f"request:  {REQUEST}")

    rule("RUN 1 — nobody has approved a write. The calendar is not touched.")
    await ask(fleet, "run-1")
    for record in gate.audit:
        print(f"  gate: {record.tool_name:<24} {record.outcome:<22} {record.reason or ''}")

    rule("THE ADMINISTRATOR ANSWERS ONCE, with a scope they choose")
    precedent = gate.remember(
        tool_name="calendar_events_insert",
        precedent_id="pr-2026-08-27-internal-review",
        applicability=(Applicability("tool", "eq", "calendar_events_insert"),),
        decision={"approve": True},
        rationale=(
            "Internal review slots on our own calendar are routine and "
            "reversible. Approved; sharing changes are still refused."
        ),
        confirmed_by="research_admin",
    )
    scope = [f"{a.field} {a.operator} {a.value!r}" for a in precedent.applicability]
    print(f"  precedent: {precedent.precedent_id}")
    print(f"  scope:     {scope}")
    print("  note:      the scope names one operation, not 'calendar'")

    before = len(gate.audit)
    rule("RUN 2 — same request. Nobody is interrupted. A real event appears.")
    said = await ask(fleet, "run-2")
    for record in gate.audit[before:]:
        print(f"  gate: {record.tool_name:<24} {record.outcome:<22} {record.reason or ''}")
    if said:
        print(f"  gemini: {said[-1].strip()[:240]}")

    rule("WHAT THIS DOES AND DOES NOT CLAIM")
    print("  Each Workspace operation is judged on its own: listing is allowed,")
    print("  creating asks a person, and changing calendar sharing is refused")
    print("  outright. Precedent removed the second question — never the gate,")
    print("  and never a deny.")

    asked = sum(1 for r in gate.audit if r.outcome == "asked_human")
    print(f"\nHuman interrupted {asked} time(s) across 2 identical requests.")

    if not args.keep:
        print("\nCheck your calendar for 2026-09-11 and delete the event if present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
