"""Expose the generated Workspace tools over MCP, with the gate in the middle.

A held operation is not refused and it is not run. The server asks the person
directly through MCP elicitation, so the answer travels from the client back to
this process without passing through the model.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from adk_harness.auth.credentials import CredentialPurpose
from adk_harness.auth.google import GoogleAuthenticator, GoogleAuthError
from adk_harness.workspace.app import APPLICATION_SCOPES
from adk_harness.workspace.approval_page import ApprovalServer
from adk_harness.workspace.evidence import EvidenceWriter
from adk_harness.workspace.tools import (
    PARAMETER_TYPES,
    SERVICES,
    Grant,
    ToolSpec,
    build_tools,
    decide,
    execute,
    resolve_grant,
)

__all__ = ["ApprovalAnswer", "ServerState", "build_server", "serve"]

# Long enough to read a change, short enough that a forgotten tab expires.
APPROVAL_TIMEOUT_SECONDS = float(os.environ.get("ADK_HARNESS_APPROVAL_TIMEOUT", "180"))


class LedgerTarget(BaseModel):
    """Which Google Cloud project holds the shared decision trail."""

    project_id: str = Field(description="Google Cloud project id for the audit ledger")


class ApprovalAnswer(BaseModel):
    """What a person is asked before a change others will see."""

    approve: bool = Field(description="Run this change now")
    reason: str = Field(default="", description="Why, in your own words")


class ServerState:
    """One connected person's grant and the tools it produced."""

    def __init__(self, make_authenticator: Callable[[], GoogleAuthenticator]) -> None:
        self._make_authenticator = make_authenticator
        self._authenticator: GoogleAuthenticator | None = None
        self.grant: Grant | None = None
        self.specs: dict[str, ToolSpec] = {}
        self.startup_error: str | None = None
        self.evidence = EvidenceWriter(ledger=_ledger())
        self.approvals = ApprovalServer()

    @property
    def authenticator(self) -> GoogleAuthenticator:
        """Build the authenticator on first use.

        It needs an OAuth client configuration, which a person supplies when
        they connect. The server still has to start without one.
        """
        if self._authenticator is None:
            self._authenticator = self._make_authenticator()
        return self._authenticator

    def adopt(self, grant: Grant | None) -> tuple[ToolSpec, ...]:
        self.grant = grant
        specs = build_tools(grant) if grant else ()
        self.specs = {spec.name: spec for spec in specs}
        return specs


def _summary(spec: ToolSpec, arguments: Mapping[str, Any]) -> str:
    named = ", ".join(f"{key}={value!r}" for key, value in sorted(arguments.items()))
    return f"{spec.method_id}({named})"


async def _run(
    state: ServerState, name: str, arguments: Mapping[str, Any], context: Any
) -> dict[str, Any]:
    """Judge one call, record the decision, then run it, hold it, or refuse it."""
    grant = state.grant
    spec = state.specs.get(name)
    if grant is None or spec is None:
        return {"outcome": "blocked", "reason": "no Workspace grant is connected"}

    change = state.evidence.propose(
        subject=grant.subject, operation=spec.method_id, arguments=arguments
    )
    decision = decide(spec)

    def written(outcome: str, reason: str, approval: Any = None) -> dict[str, Any]:
        evidence = state.evidence.record(
            change,
            actor=grant.subject,
            operation=spec.method_id,
            outcome=outcome,
            reason=reason,
            approval=approval,
            arguments=arguments,
        )
        return {"outcome": outcome, "operation": spec.method_id, "reason": reason,
                "evidence": evidence.summary()}

    if decision.outcome == "blocked":
        return written("blocked", decision.reason)

    if decision.outcome == "held":
        approved = await _ask_person(state, context, spec, arguments, change.content_hash)
        if approved is None:
            return written("held", "nothing ran; nobody could be asked")
        if not approved:
            return written("held", "nothing ran; the person did not approve")

        approval = state.evidence.approve(
            change,
            approver=grant.subject,
            scope={"operation": spec.method_id},
        )
        result = execute(grant, spec, arguments)
        recorded = written("allowed", "approved by the person", approval)
        return {**recorded, "result": result}

    result = execute(grant, spec, arguments)
    return {**written("allowed", decision.reason), "result": result}


def _projects(grant: Grant | None) -> tuple[str, ...]:
    """List the projects this grant can see, or nothing when it cannot look."""
    if grant is None:
        return ()
    try:
        from google.cloud import resourcemanager_v3

        client = resourcemanager_v3.ProjectsClient(credentials=grant.credentials)
        return tuple(sorted(project.project_id for project in client.search_projects()))
    except Exception:
        # Listing needs a cloud scope this grant may not carry. Ask instead.
        return ()


async def _choose_project(state: ServerState, context: Any) -> str | None:
    """Offer the projects a person has, and fall back to asking them to name one."""
    choices = _projects(state.grant)
    if choices:
        answer = await context.session.elicit_form(
            message="Which project should hold the audit trail?",
            requestedSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "title": "Project",
                        "enum": list(choices),
                    }
                },
                "required": ["project_id"],
            },
        )
        if answer.action != "accept" or not answer.content:
            return None
        return str(answer.content.get("project_id") or "")
    answer = await context.elicit(
        message="Which Google Cloud project should hold the audit trail?",
        schema=LedgerTarget,
    )
    if answer.action != "accept" or not answer.data:
        return None
    return answer.data.project_id


def _client_capabilities(server: Any) -> dict[str, Any]:
    """Report what this client says it supports, notably elicitation."""
    try:
        capabilities = server.get_context().session.client_params.capabilities
    except Exception as exc:
        return {"known": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "known": True,
        "elicitation": capabilities.elicitation is not None,
        "sampling": capabilities.sampling is not None,
        "roots": capabilities.roots is not None,
    }


async def _ask_person(
    state: ServerState,
    context: Any,
    spec: ToolSpec,
    arguments: Mapping[str, Any],
    change_hash: str,
) -> bool | None:
    """Ask through a page the person opens, not through the conversation.

    The answer travels from their browser to this process. The model is handed
    a link and never sees the question, so it cannot answer on their behalf.
    """
    pending, url = state.approvals.offer(
        operation=spec.method_id, arguments=arguments, change_hash=change_hash
    )
    try:
        answer = await context.elicit_url(
            message=f"Approve {spec.method_id}? Open the link to decide.",
            url=url,
            elicitation_id=pending.token,
        )
    except Exception:
        state.approvals.withdraw(pending)
        return None
    if getattr(answer, "action", None) != "accept":
        state.approvals.withdraw(pending)
        return None

    decided = await asyncio.to_thread(pending.wait, APPROVAL_TIMEOUT_SECONDS)
    state.approvals.withdraw(pending)
    with contextlib.suppress(Exception):
        await context.session.send_elicit_complete(pending.token)
    return decided


async def _connect_ledger(
    state: ServerState, context: Any, project_id: str | None
) -> dict[str, Any]:
    """Attach a shared ledger, asking for the project only when nobody said."""
    target = project_id
    if not target:
        try:
            target = await _choose_project(state, context)
        except Exception:
            return {"connected": False, "reason": "this client cannot ask; pass project_id"}
    if not target or not target.strip():
        return {"connected": False, "reason": "nobody named a project"}
    target = target.strip()
    ledger = _ledger(target)
    if ledger is None:
        return {"connected": False, "reason": f"no Firestore ledger opened for {target}"}
    state.evidence.attach_ledger(ledger, project_id=target)
    return {"connected": True, "project": target, "ledger": "firestore"}


def _ledger(project_id: str | None = None) -> Any | None:
    """Open a Firestore ledger for a project, or return nothing.

    A local demo keeps its trail in memory. A fleet points every machine at one
    project and the trail becomes shared.
    """
    target = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not target:
        return None
    try:
        from google.cloud import firestore

        from adk_harness.governance.ledger import FirestoreActionLedger

        return FirestoreActionLedger(firestore.Client(project=target))
    except Exception:
        return None


def _annotations(spec: ToolSpec) -> dict[str, Any]:
    """Map each Google parameter onto a typed, described annotation."""
    from typing import Annotated

    annotations: dict[str, Any] = {}
    for parameter, schema in spec.parameters.items():
        python_type = PARAMETER_TYPES.get(str(schema.get("type", "string")), str)
        description = str(schema.get("description", "")).strip()
        annotations[parameter] = (
            Annotated[python_type, Field(description=description)]
            if description
            else python_type
        )
    return annotations


def _signature(spec: ToolSpec) -> inspect.Signature:
    """Required parameters stay required; the rest default to nothing."""
    annotations = _annotations(spec)
    required = [name for name in annotations if name in spec.required]
    optional = [name for name in annotations if name not in spec.required]
    return inspect.Signature(
        [
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=inspect.Parameter.empty if name in spec.required else None,
                annotation=annotations[name],
            )
            for name in required + optional
        ]
    )


def _stored_grant(state: ServerState) -> Grant | None:
    """Return the stored grant, recording why there is none."""
    try:
        grant = resolve_grant(state.authenticator)
    except Exception as exc:
        state.startup_error = f"{type(exc).__name__}: {exc}"
        return None
    if grant is None:
        state.startup_error = "no stored Workspace grant"
    else:
        state.startup_error = None
    return grant


def build_server(
    make_authenticator: Callable[[], GoogleAuthenticator],
) -> tuple[Any, ServerState]:
    """Build the MCP server and the state its tools read."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.lowlevel.server import NotificationOptions

    state = ServerState(make_authenticator)
    server = FastMCP("adk-harness")

    # FastMCP builds its initialization options with no notification options, so
    # it advertises tools.listChanged as false and a client has no reason to ask
    # for the tool list again. The grant decides the tools, so it must be true.
    low_level = server._mcp_server
    original_options = low_level.create_initialization_options

    def initialization_options(
        notification_options: Any = None, experimental_capabilities: Any = None
    ) -> Any:
        return original_options(
            notification_options or NotificationOptions(tools_changed=True),
            experimental_capabilities,
        )

    low_level.create_initialization_options = initialization_options

    def make_handler(spec: ToolSpec) -> Any:
        """Build a handler whose signature is the operation's real parameters.

        Without this the tool advertises an untyped bag and the model guesses
        the field names. Google's discovery document already knows them.
        """
        name = spec.name

        async def handler(**arguments: Any) -> Any:
            # Unset optional parameters arrive as None; Google wants them absent.
            supplied = {key: value for key, value in arguments.items() if value is not None}
            return await _run(state, name, supplied, server.get_context())

        handler.__signature__ = _signature(spec)  # type: ignore[attr-defined]
        handler.__annotations__ = dict(_annotations(spec))
        return handler

    def register(specs: tuple[ToolSpec, ...]) -> None:
        for spec in specs:
            server.add_tool(
                make_handler(spec),
                name=spec.name,
                description=f"[{decide(spec).outcome}] {spec.description}",
            )

    async def adopt(grant: Grant | None, *, reused: bool) -> dict[str, Any]:
        """Expose whatever the grant covers and tell the client the list moved."""
        specs = state.adopt(grant)
        register(specs)
        await server.get_context().session.send_tool_list_changed()
        return {
            "connected": grant is not None,
            "reused_existing_grant": reused,
            "subject": grant.subject if grant else None,
            "granted_scopes": list(grant.scopes) if grant else [],
            "tools": [spec.name for spec in specs],
        }

    async def connect_workspace(services: list[str] | None = None) -> dict[str, Any]:
        """Connect a Google Workspace account and expose what it granted."""
        selected = tuple(services or SERVICES)
        unknown = [service for service in selected if service not in APPLICATION_SCOPES]
        if unknown:
            return {"connected": False, "reason": f"unknown service(s): {', '.join(unknown)}"}
        scopes = tuple(
            scope for service in selected for scope in APPLICATION_SCOPES[service]
        )

        # A grant that already covers these services is the answer. Sending a
        # person back to Google every time would teach them to click through it.
        existing = _stored_grant(state)
        if existing is not None and set(scopes) <= set(existing.scopes):
            return await adopt(existing, reused=True)

        try:
            state.authenticator.login(CredentialPurpose.WORKSPACE, scopes=scopes)
        except GoogleAuthError:
            return {
                "connected": False,
                "reason": (
                    "set ADK_HARNESS_GOOGLE_CLIENT_CONFIG to an OAuth client JSON "
                    "file from your own Google Cloud project"
                ),
            }
        except Exception as exc:  # the SDK's message can carry callback URLs
            del exc
            return {"connected": False, "reason": "Google login did not complete"}
        return await adopt(_stored_grant(state), reused=False)

    server.add_tool(connect_workspace, name="connect_workspace")
    # Reading the keyring at startup is a convenience, not the design. When it
    # fails, connect_workspace still finds the grant and the tools still appear.
    register(state.adopt(_stored_grant(state)))

    def workspace_status() -> dict[str, Any]:
        """Report whether a Workspace grant was found, and why not."""
        return {
            "connected": state.grant is not None,
            "subject": state.grant.subject if state.grant else None,
            "granted_scopes": list(state.grant.scopes) if state.grant else [],
            "tools": sorted(state.specs),
            "startup_error": state.startup_error,
            "client": _client_capabilities(server),
        }

    async def connect_ledger() -> dict[str, Any]:
        """Send this machine's decisions to a shared Firestore audit trail.

        Do not guess the project. The person picks it, or an administrator set
        GOOGLE_CLOUD_PROJECT and nobody is asked.
        """
        return await _connect_ledger(
            state, server.get_context(), os.environ.get("GOOGLE_CLOUD_PROJECT")
        )

    def governance_audit() -> dict[str, Any]:
        """Every decision this session, oldest first, with its change hash."""
        return {
            "project": state.evidence.project_id,
            "ledger": "firestore" if state.evidence.ledger else "session only",
            "decisions": [evidence.summary() for evidence in state.evidence.trail],
        }

    server.add_tool(workspace_status, name="workspace_status")
    server.add_tool(governance_audit, name="governance_audit")
    server.add_tool(connect_ledger, name="connect_ledger")
    return server, state


def serve(
    make_authenticator: Callable[[], GoogleAuthenticator],
) -> int:  # pragma: no cover - entry point
    server, _ = build_server(make_authenticator)
    server.run()
    return 0
