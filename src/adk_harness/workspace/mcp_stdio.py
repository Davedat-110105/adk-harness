"""Expose the generated Workspace tools over MCP, with the gate in the middle.

A held operation is not refused and it is not run. The server asks the person
directly through MCP elicitation, so the answer travels from the client back to
this process without passing through the model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from adk_harness.auth.credentials import CredentialPurpose
from adk_harness.auth.google import GoogleAuthenticator, GoogleAuthError
from adk_harness.workspace.app import APPLICATION_SCOPES
from adk_harness.workspace.tools import (
    SERVICES,
    Grant,
    ToolSpec,
    build_tools,
    decide,
    execute,
    resolve_grant,
)

__all__ = ["Approval", "ServerState", "build_server", "serve"]


class Approval(BaseModel):
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
    """Judge one call, then run it, hold it, or refuse it."""
    grant = state.grant
    spec = state.specs.get(name)
    if grant is None or spec is None:
        return {"outcome": "blocked", "reason": "no Workspace grant is connected"}

    decision = decide(spec)
    if decision.outcome == "blocked":
        return {"outcome": "blocked", "operation": spec.method_id, "reason": decision.reason}

    if decision.outcome == "held":
        try:
            answer = await context.elicit(
                message=f"Approve {_summary(spec, arguments)}? {decision.reason}",
                schema=Approval,
            )
        except Exception:
            # A client that cannot ask has not approved anything.
            return {
                "outcome": "held",
                "operation": spec.method_id,
                "reason": "nothing ran; this client cannot ask a person for approval",
            }
        if answer.action != "accept" or not answer.data or not answer.data.approve:
            return {
                "outcome": "held",
                "operation": spec.method_id,
                "reason": "nothing ran; the person did not approve",
            }
        result = execute(grant, spec, arguments)
        return {
            "outcome": "allowed",
            "operation": spec.method_id,
            "approved_by": grant.subject,
            "rationale": answer.data.reason,
            "result": result,
        }

    return {
        "outcome": "allowed",
        "operation": spec.method_id,
        "result": execute(grant, spec, arguments),
    }


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

    def make_handler(name: str) -> Any:
        async def handler(arguments: dict[str, Any] | None = None) -> Any:
            return await _run(state, name, arguments or {}, server.get_context())

        return handler

    def register(specs: tuple[ToolSpec, ...]) -> None:
        for spec in specs:
            server.add_tool(
                make_handler(spec.name),
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
        }

    server.add_tool(workspace_status, name="workspace_status")
    return server, state


def serve(
    make_authenticator: Callable[[], GoogleAuthenticator],
) -> int:  # pragma: no cover - entry point
    server, _ = build_server(make_authenticator)
    server.run()
    return 0
