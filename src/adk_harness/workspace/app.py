"""Build a governed, per-user Google Workspace planning application."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from coactra import Policy, Scope
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App

from adk_harness.auth import CredentialPurpose, GoogleAuthenticator
from adk_harness.governance import CoactraGovernance
from adk_harness.governance.content_armor import ContentArmor
from adk_harness.governance.ledger import FirestoreActionLedger
from adk_harness.governance.precedents import PrecedentStore

from .connections import (
    APPLICATION_SCOPES,
    OPERATIONS,
    READ_OPERATION_ORDER,
    READ_OPERATIONS,
    CredentialReference,
    WorkspaceConnection,
    WorkspaceConsent,
)

__all__ = [
    "APPLICATION_SCOPES",
    "READ_OPERATIONS",
    "CredentialReference",
    "WorkspaceApp",
    "WorkspaceConnection",
    "WorkspaceConsent",
    "build_workspace_app",
    "check_workspace_service_access",
]

DEFAULT_MODEL = "gemini-3.5-flash"
SCOPES = {service: scopes[0] for service, scopes in APPLICATION_SCOPES.items()}


@dataclass(frozen=True, slots=True)
class WorkspaceApp:
    """An ADK planner with a separately governed Workspace connection."""

    app: App
    orchestrator: LlmAgent
    governance: CoactraGovernance
    connection: WorkspaceConnection
    services: tuple[str, ...]
    tool_names: tuple[str, ...]

    @property
    def audit(self) -> Sequence[Any]:
        return self.governance.audit


async def build_workspace_app(
    *,
    policy: Policy,
    scope: Scope,
    authenticator: GoogleAuthenticator,
    credential_reference: CredentialReference,
    consent: WorkspaceConsent,
    resource_allowlist: Mapping[str, Sequence[str]] | None = None,
    services: Sequence[str] = ("calendar",),
    tool_filter: Sequence[str] | None = None,
    model: str = DEFAULT_MODEL,
    principal: str | None = None,
    precedents: PrecedentStore | None = None,
    ledger: FirestoreActionLedger | None = None,
    armor: ContentArmor | None = None,
    name: str = "workspace_app",
    instruction: str | None = None,
) -> WorkspaceApp:
    """Build the planner using an explicit verified grant reference.

    No credentials are serialized into the returned app or passed to the
    model. Only bounded read functions are model facing; mutations are solely
    available through the connection's host boundary.
    """
    selected = tuple(dict.fromkeys(services))
    unknown = [service for service in selected if service not in APPLICATION_SCOPES]
    if unknown:
        raise ValueError(f"unknown Workspace service(s): {', '.join(unknown)}")
    if resource_allowlist is None:
        raise ValueError("Workspace app requires an explicit resource allowlist")
    if principal is not None and principal != credential_reference.subject:
        raise ValueError("policy principal must match the verified Workspace subject")
    selected_ops = tuple(tool_filter) if tool_filter is not None else tuple(
        operation for operation in READ_OPERATION_ORDER if operation.split("_", 1)[0] in selected
    )
    unsupported = [operation for operation in selected_ops if operation not in OPERATIONS]
    if unsupported:
        raise ValueError(f"unsupported Workspace operation(s): {', '.join(unsupported)}")
    wrong_service = [
        operation for operation in selected_ops if operation.split("_", 1)[0] not in selected
    ]
    if wrong_service:
        raise ValueError("tool_filter contains an operation for an unselected service")
    if any(operation not in READ_OPERATIONS for operation in selected_ops):
        raise ValueError("mutating Workspace operations are host-only and cannot be model tools")

    connection = WorkspaceConnection(
        authenticator=authenticator,
        credential_reference=credential_reference,
        consent=consent,
        resource_allowlist=resource_allowlist,
    )
    governance = CoactraGovernance(
        policy=policy,
        scope=scope,
        principal=principal or credential_reference.subject,
        precedents=precedents,
        ledger=ledger,
        armor=armor,
    )
    tools = [_planning_tool(connection, operation) for operation in selected_ops]
    orchestrator = LlmAgent(
        name=name,
        model=model,
        description="Plans bounded Workspace reads under explicit consent and policy gates.",
        instruction=instruction or _instruction(selected),
        tools=tools,
    )
    return WorkspaceApp(
        app=App(name=name, root_agent=orchestrator, plugins=[governance]),
        orchestrator=orchestrator,
        governance=governance,
        connection=connection,
        services=selected,
        tool_names=tuple(selected_ops),
    )


def _planning_tool(connection: WorkspaceConnection, operation: str) -> Any:
    method = getattr(connection, operation)

    if operation == "calendar_get_event":
        def calendar_get_tool(calendar_id: str, event_id: str) -> Any:
            return method(calendar_id=calendar_id, event_id=event_id)
        tool = calendar_get_tool
    elif operation == "calendar_list_events":
        def calendar_list_tool(
            calendar_id: str, time_min: str, time_max: str, max_results: int = 25
        ) -> Any:
            return method(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
            )
        tool = calendar_list_tool
    elif operation == "gmail_list_drafts":
        def gmail_list_tool(max_results: int = 25, page_token: str | None = None) -> Any:
            return method(max_results=max_results, page_token=page_token)
        tool = gmail_list_tool
    elif operation == "gmail_get_draft":
        def gmail_get_tool(draft_id: str) -> Any:
            return method(draft_id=draft_id)
        tool = gmail_get_tool
    elif operation == "docs_get":
        def docs_get_tool(document_id: str) -> Any:
            return method(document_id=document_id)
        tool = docs_get_tool
    elif operation == "sheets_get_values":
        def sheets_get_tool(spreadsheet_id: str, range: str) -> Any:
            return method(spreadsheet_id=spreadsheet_id, range=range)
        tool = sheets_get_tool
    else:
        raise ValueError(f"operation is not a model planning read: {operation}")

    tool.__name__ = operation
    tool.__qualname__ = operation
    tool.__doc__ = f"Execute the bounded, consented {operation} read."
    return tool


async def check_workspace_service_access(
    services: Sequence[str],
    *,
    authenticator: GoogleAuthenticator,
    credential_reference: CredentialReference,
) -> dict[str, str | None]:
    """Check grant metadata without default credentials or custom introspection.

    This does not establish resource access; every connection operation still
    performs its consented official API preflight.
    """
    result: dict[str, str | None] = {}
    for service in services:
        scopes = APPLICATION_SCOPES.get(service)
        if scopes is None:
            result[service] = f"unknown service {service!r}"
            continue
        try:
            authenticator.verified_credentials(
                CredentialPurpose.WORKSPACE,
                subject=credential_reference.subject,
                required_scopes=scopes,
            )
        except Exception:
            result[service] = "verified Workspace credentials or required scope unavailable"
        else:
            result[service] = None
    return result


def _instruction(services: Sequence[str]) -> str:
    return (
        f"Plan bounded reads in Google Workspace: {', '.join(services)}. "
        "Use only explicitly listed resources and time ranges. Consent or "
        "policy refusals are terminal; report the reason and stop. Workspace "
        "mutations, mail sending, and sharing changes are host-only or prohibited."
    )
