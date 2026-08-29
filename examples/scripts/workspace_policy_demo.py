"""Print a governed, read-only Google Workspace planning run.

    GOOGLE_CLOUD_PROJECT=... python examples/scripts/workspace_policy_demo.py

Needs an explicit verified Workspace grant selected by ``ADK_GOOGLE_SUBJECT``;
the example never discovers or substitutes default credentials.

The example has no mutation or sharing tool. A trusted host must provide any
future mutation authorization separately.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness import build_workspace_app
from adk_harness.auth import CredentialPurpose, GoogleAuthenticator, SecureCredentialStore
from adk_harness.workspace import CredentialReference, WorkspaceConsent

REQUEST = (
    "List events on calendar 'primary' between 2026-09-01 and 2026-09-02."
)


class WorkspacePolicy:
    """Permit only the bounded planning reads exposed by this example."""

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

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"{tool} only reads.",
            source="workspace-policy",
        )


def rule(title: str) -> None:
    print(f"\n{'─' * 74}\n{title}\n{'─' * 74}")


async def ask(workspace_app, session: str) -> list[str]:
    service = InMemorySessionService()
    runner = Runner(app=workspace_app.app, session_service=service)
    await service.create_session(
        app_name=workspace_app.app.name, user_id="admin", session_id=session
    )
    message = types.Content(role="user", parts=[types.Part(text=REQUEST)])
    said: list[str] = []
    async for event in runner.run_async(
        user_id="admin", session_id=session, new_message=message
    ):
        if event.content and event.content.parts:
            said.extend(p.text for p in event.content.parts if p.text)
    return said


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    workspace_app = await build_workspace_app(
        policy=WorkspacePolicy(),
        scope=Scope(tenant_id="university_a", namespace="grants"),
        authenticator=GoogleAuthenticator(
            client_config={
                "installed": {"client_id": os.environ.get("GOOGLE_CLIENT_ID", "example")}
            },
            store=SecureCredentialStore(),
        ),
        credential_reference=CredentialReference(
            subject=os.environ.get("ADK_GOOGLE_SUBJECT", "user:research_admin"),
            purpose=CredentialPurpose.WORKSPACE,
        ),
        consent=WorkspaceConsent(
            subject=os.environ.get("ADK_GOOGLE_SUBJECT", "user:research_admin"),
            applications=("calendar",),
            resources={"calendar": ("primary",)},
            operations=("calendar_list_events",),
            approved=False,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            calendar_windows={"primary": ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")},
        ),
        resource_allowlist={"calendar": ("primary",)},
        services=("calendar",),
        # Only one bounded read is exposed to the model.
        tool_filter=["calendar_list_events"],
        principal=os.environ.get("ADK_GOOGLE_SUBJECT", "user:research_admin"),
        name="grant_workspace",
    )
    gate = workspace_app.governance

    print(f"model:    {workspace_app.orchestrator.model}")
    print(f"services: {', '.join(workspace_app.services)}")
    print(f"tools:    {', '.join(workspace_app.tool_names)}")
    print(f"request:  {REQUEST}")

    if os.environ.get("ADK_RUN_LIVE") != "true":
        print("\nDry run only. Set ADK_RUN_LIVE=true to opt into a model read.")
        return 0
    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT first.", file=sys.stderr)
        return 2

    rule("BOUNDED READ — consent and resource access are checked first")
    await ask(workspace_app, "run-1")
    for record in gate.audit:
        print(f"  gate: {record.tool_name:<24} {record.outcome:<22} {record.reason or ''}")

    print("\nNo mutation, send, or sharing operation is available to this app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
