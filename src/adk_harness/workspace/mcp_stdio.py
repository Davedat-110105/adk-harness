"""Expose the generated Workspace tools over MCP, with the gate in the middle.

A held operation is not refused and it is not run. The server asks the person
directly through MCP elicitation, so the answer travels from the client back to
this process without passing through the model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from adk_harness.auth.credentials import CredentialPurpose
from adk_harness.auth.google import GoogleAuthenticator
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

    def __init__(self, authenticator: GoogleAuthenticator) -> None:
        self.authenticator = authenticator
        self.grant: Grant | None = None
        self.specs: dict[str, ToolSpec] = {}

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
        answer = await context.elicit(
            message=f"Approve {_summary(spec, arguments)}? {decision.reason}",
            schema=Approval,
        )
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


def build_server(authenticator: GoogleAuthenticator) -> tuple[Any, ServerState]:
    """Build the MCP server and the state its tools read."""
    from mcp.server.fastmcp import FastMCP

    state = ServerState(authenticator)
    server = FastMCP("adk-harness")

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

    async def connect_workspace(services: list[str] | None = None) -> dict[str, Any]:
        """Connect a Google Workspace account and expose what it granted."""
        selected = tuple(services or SERVICES)
        unknown = [service for service in selected if service not in APPLICATION_SCOPES]
        if unknown:
            return {"connected": False, "reason": f"unknown service(s): {', '.join(unknown)}"}
        scopes = tuple(
            scope for service in selected for scope in APPLICATION_SCOPES[service]
        )
        try:
            state.authenticator.login(CredentialPurpose.WORKSPACE, scopes=scopes)
        except Exception as exc:  # the SDK's message can carry callback URLs
            del exc
            return {"connected": False, "reason": "Google login did not complete"}
        specs = state.adopt(resolve_grant(state.authenticator))
        register(specs)
        await server.get_context().session.send_tool_list_changed()
        return {
            "connected": state.grant is not None,
            "subject": state.grant.subject if state.grant else None,
            "granted_scopes": list(state.grant.scopes) if state.grant else [],
            "tools": [spec.name for spec in specs],
        }

    server.add_tool(connect_workspace, name="connect_workspace")
    register(state.adopt(resolve_grant(state.authenticator)))
    return server, state


def serve(authenticator: GoogleAuthenticator) -> int:  # pragma: no cover - entry point
    server, _ = build_server(authenticator)
    server.run()
    return 0
