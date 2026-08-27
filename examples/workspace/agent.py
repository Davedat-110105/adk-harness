"""A governed Workspace fleet, deployable to Cloud Run and shared by a team.

This is the one two people can use at once. It runs as a Cloud Run service, so
a colleague opens the same URL, prompts the same model, and gets the same policy
gate — nobody installs anything.

    adk deploy cloud_run --project=$GOOGLE_CLOUD_PROJECT --region=us-central1 \\
        --with_ui ./examples/workspace

Which calendar it can reach, and why that is not your personal one
-----------------------------------------------------------------
On Cloud Run there is no browser, so there is no user consent. The service
authenticates as its own identity via Application Default Credentials, which is
what `use_default_credential=True` means.

That identity cannot see a personal calendar, and no flag changes it: reaching
one would need domain-wide delegation, which requires a Google Workspace
organisation. A personal `@gmail.com` account does not have one.

**Share a calendar with the service account instead.** In Google Calendar →
Settings → the calendar → *Share with specific people*, add the service
account's email with "Make changes to events", then set `ADK_CALENDAR_ID` to
that calendar's id.

That is the better shape anyway. A team fleet acting on a shared team calendar
is the thing being demonstrated; an agent reaching into one person's private
calendar is not.

Without that share the service still deploys, the gate still works, and Calendar
calls return a permission error the model reports honestly.
"""

from __future__ import annotations

import os

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.workspace import build_workspace_fleet

CALENDAR_ID = os.environ.get("ADK_CALENDAR_ID", "primary")

# Read freely. Anything that leaves a mark other people see asks a person.
WRITE_VERBS = ("insert", "update", "delete", "patch", "move", "import")


class TeamPolicy:
    """One rule set, applied to whoever is using the service.

    Because the toolsets expose each API operation as its own tool, this can
    distinguish between reading a calendar, writing to it, and changing who can
    see it — three different decisions that a dispatch-level gate would have had
    to answer identically.
    """

    async def check(self, request: PolicyRequest) -> Decision:
        tool = request.resource.removeprefix("tool:")

        if "acl" in tool or "share" in tool:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"{tool} changes who can see this calendar. Access is "
                    "granted by a person, never by an agent."
                ),
                source="team-policy",
            )

        if any(verb in tool for verb in WRITE_VERBS):
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"{tool} creates or changes something the team will see.",
                source="team-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"{tool} only reads.",
            source="team-policy",
        )


async def _build():
    return await build_workspace_fleet(
        policy=TeamPolicy(),
        scope=Scope(tenant_id="team", namespace="workspace"),
        services=("calendar",),
        # Named, not inherited. CalendarToolset offers 38 operations including
        # ACL changes; a deployed service should hold only the ones somebody
        # decided to give it.
        tool_filter=[
            "calendar_events_list",
            "calendar_events_get",
            "calendar_events_insert",
            "calendar_events_update",
        ],
        principal="user:team",
        name="workspace_fleet",
        instruction=(
            "You help a research team manage a shared calendar. Use calendar id "
            f"'{CALENDAR_ID}'. Ask for a date and time if you were not given "
            "one; never invent them.\n\n"
            "Every tool call passes a policy gate. A 'blocked' result is a "
            "decision, not an error: say why and stop. If the gate asks for "
            "human confirmation, wait — do not try another route."
        ),
    )


def _fleet():
    """ADK imports this module and reads `app`, so the fleet is built eagerly.

    `build_workspace_fleet` is async because listing a toolset's tools is, so
    this bridges to the module-level import ADK expects. A running loop means
    ADK's web server is loading us, and `asyncio.run` would refuse — hand it to
    a worker thread in that case.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_build())

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_build())).result()


fleet = _fleet()
app = fleet.app
governance = fleet.governance
