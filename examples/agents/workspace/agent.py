"""A governed local Google Workspace application for Antigravity.

The example selects services and operations explicitly. Content screening and
the policy gate run locally; a held write has not run and requires a trusted
host approval. It does not provision cloud resources or transfer history.
Configure Google's supported credentials yourself before any live use.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.auth import CredentialPurpose, GoogleAuthenticator, SecureCredentialStore
from adk_harness.governance.content_armor import ContentArmor
from adk_harness.workspace import CredentialReference, WorkspaceConsent, build_workspace_app

CALENDAR_ID = os.environ.get("ADK_CALENDAR_ID", "primary")
CALENDAR_TIME_MIN = os.environ.get("ADK_CALENDAR_TIME_MIN", "2026-09-01T00:00:00Z")
CALENDAR_TIME_MAX = os.environ.get("ADK_CALENDAR_TIME_MAX", "2026-09-02T00:00:00Z")
SERVICES = tuple(os.environ.get("ADK_SERVICES", "calendar").split(","))
ALLOWED_DOMAINS = tuple(
    d for d in os.environ.get("ADK_ALLOWED_DOMAINS", "gmail.com").split(",") if d
)

# This sample exposes one bounded calendar list read.
WRITE_VERBS = ("insert", "create", "update", "delete", "patch", "modify", "batch")
TOOLS = [
    "calendar_list_events",
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
                    "This app drafts; a person sends."
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
    armor = ContentArmor(allowed_email_domains=ALLOWED_DOMAINS)
    subject = os.environ.get("ADK_GOOGLE_SUBJECT", "user:local")
    authenticator = GoogleAuthenticator(
        client_config={"installed": {"client_id": os.environ.get("GOOGLE_CLIENT_ID", "example")}},
        store=SecureCredentialStore(),
    )
    consent = WorkspaceConsent(
        subject=subject,
        applications=("calendar",),
        resources={"calendar": (CALENDAR_ID,)},
        operations=tuple(TOOLS),
        approved=False,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        calendar_windows={CALENDAR_ID: (CALENDAR_TIME_MIN, CALENDAR_TIME_MAX)},
    )
    workspace_app = await build_workspace_app(
        policy=TeamPolicy(),
        scope=Scope(tenant_id="team", namespace="workspace"),
        authenticator=authenticator,
        credential_reference=CredentialReference(
            subject=subject, purpose=CredentialPurpose.WORKSPACE
        ),
        consent=consent,
        resource_allowlist={"calendar": (CALENDAR_ID,)},
        services=SERVICES,
        tool_filter=TOOLS,
        principal=subject,
        name="workspace_app",
        armor=armor,
        instruction=(
            "You help a research team inspect a shared calendar. "
            f"Use calendar id '{CALENDAR_ID}' and only the consented time window.\n\n"
            "Every tool call passes a policy gate. A 'blocked' result is a "
            "decision, not an error: say why and stop. If the gate asks for "
            "confirmation, wait."
        ),
    )

    return workspace_app, armor


def _workspace_app():
    """ADK imports this module and reads `app`, so the app is built eagerly.

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


workspace_app, armor = _workspace_app()
app = workspace_app.app
governance = workspace_app.governance
