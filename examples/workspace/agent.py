"""A governed Workspace fleet, deployable and shared by a team.

Three layers, in the order a request meets them:

1. **ContentArmor** screens outbound tool arguments and quarantines
   instruction-shaped text coming back from Gmail or Docs. Retrieved content is
   data; it is never allowed to read as a command.
2. **CoactraGovernance** decides each operation. Reads flow, writes ask a
   person, and changing who can see a calendar is refused outright.
3. **FirestoreActionLedger** records what happened — actor, policy result,
   hashed inputs, outcome — append-only, with an idempotency key so a retry
   cannot double-record.

Deploy:

    adk deploy cloud_run --project=$GOOGLE_CLOUD_PROJECT --region=us-central1 \\
        --with_ui ./examples/workspace

Which mailbox and calendar it can reach
---------------------------------------
On Cloud Run there is no browser, so there is no user consent: the service
authenticates as its own identity. That identity cannot see a personal calendar
or mailbox, and no flag changes it — reaching one needs domain-wide delegation,
which needs a Google Workspace organisation.

Share a calendar with the service account and set `ADK_CALENDAR_ID`. Run
locally under `gcloud auth application-default login` to act as yourself.

Set `ADK_LEDGER=1` to write the action ledger to Firestore. It is off by
default because a demo that silently writes to a database is a surprise.
"""

from __future__ import annotations

import os

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.armor import ContentArmor
from adk_harness.ledger import FirestoreActionLedger
from adk_harness.workspace import build_workspace_fleet

CALENDAR_ID = os.environ.get("ADK_CALENDAR_ID", "primary")
SERVICES = tuple(os.environ.get("ADK_SERVICES", "calendar,gmail").split(","))
ALLOWED_DOMAINS = tuple(
    d for d in os.environ.get("ADK_ALLOWED_DOMAINS", "gmail.com").split(",") if d
)

# Every verb that changes something. "create" was missing from a first version,
# so gmail_users_drafts_create was judged a read and a draft appeared in a real
# mailbox with nobody asked. A gate that decides by matching substrings fails
# open when the list is short, which is the wrong direction to fail.
WRITE_VERBS = (
    "insert",
    "create",
    "update",
    "delete",
    "patch",
    "move",
    "import",
    "trash",
    "modify",
    "batch",
)

# Drafting is reversible and a person clicks send. Sending is not. An agent
# that can email colleagues on a policy misfire is a different risk class from
# one that can add a calendar entry, so the send operations are simply not
# given to the model — the cheapest control available, applied before any
# policy runs.
TOOLS = [
    "calendar_events_list",
    "calendar_events_get",
    "calendar_events_insert",
    "calendar_events_update",
    "gmail_users_drafts_list",
    "gmail_users_drafts_get",
    "gmail_users_drafts_create",
]


READ_VERBS = ("list", "get", "search", "watch")


class TeamPolicy:
    """One rule set, applied to whoever is using the service.

    Because each API operation is its own tool, this distinguishes reading a
    calendar from writing to it from changing who can see it — three decisions
    a dispatch-level gate would have had to answer identically.
    """

    async def check(self, request: PolicyRequest) -> Decision:
        tool = request.resource.removeprefix("tool:")

        if "acl" in tool or "settings" in tool or "permission" in tool:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"{tool} changes who can access this data. Access is "
                    "granted by a person, never by an agent."
                ),
                source="team-policy",
            )

        if "send" in tool:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"{tool} delivers mail to real people and cannot be undone. "
                    "This fleet drafts; a person sends."
                ),
                source="team-policy",
            )

        if any(verb in tool for verb in WRITE_VERBS):
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"{tool} creates or changes something the team will see.",
                source="team-policy",
            )

        if any(verb in tool for verb in READ_VERBS):
            return Decision(
                outcome=DecisionOutcome.allow,
                reason=f"{tool} only reads.",
                source="team-policy",
            )

        # Unrecognised operation. Ask rather than assume, because the failure
        # above came from assuming, and an unfamiliar tool is exactly the case
        # where a person should look.
        return Decision(
            outcome=DecisionOutcome.requires_approval,
            reason=f"{tool} is not a known read operation. A person should look.",
            source="team-policy",
        )


async def _build():
    fleet = await build_workspace_fleet(
        policy=TeamPolicy(),
        scope=Scope(tenant_id="team", namespace="workspace"),
        services=SERVICES,
        tool_filter=TOOLS,
        principal="user:team",
        name="workspace_fleet",
        instruction=(
            "You help a research team manage a shared calendar and draft mail. "
            f"Use calendar id '{CALENDAR_ID}'. Ask for a date, time or recipient "
            "if you were not given one; never invent them.\n\n"
            "You can draft email. You cannot send it — that is deliberate, and "
            "a person will send. Say so rather than looking for another way.\n\n"
            "Every tool call passes a policy gate. A 'blocked' result is a "
            "decision, not an error: say why and stop. If the gate asks for "
            "confirmation, wait."
        ),
    )

    # Armor runs alongside governance on the same app. Its job is the direction
    # governance does not cover: content arriving *from* Gmail and Docs, which
    # a model would otherwise read as instructions.
    fleet.app.plugins.append(
        ContentArmor(allowed_email_domains=ALLOWED_DOMAINS)
    )
    return fleet


def _ledger() -> FirestoreActionLedger | None:
    """Off unless asked for. A demo that silently writes to a database is rude."""
    if os.environ.get("ADK_LEDGER") != "1":
        return None
    return FirestoreActionLedger(collection="action_ledger")


def _fleet():
    """ADK imports this module and reads `app`, so the fleet is built eagerly.

    A running loop means ADK's web server is loading us and `asyncio.run` would
    refuse, so hand the build to a worker thread in that case.
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
armor = next(p for p in app.plugins if isinstance(p, ContentArmor))
ledger = _ledger()
