"""Generate Workspace tools from what the person granted, and judge each one.

Nothing here enumerates operations by hand. Google's discovery documents
declare every method, the scopes it needs, and its HTTP verb, so the tool list
is whatever the granted token actually covers and the gate reads the verb
rather than a maintained allowlist.

The credential lookup is the only part that differs between the local server
and a hosted one. Local reads the keyring; a remote server would read a bearer
token off the request. Everything below `resolve_grant` is shared.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from adk_harness.auth.credentials import CredentialPurpose
from adk_harness.auth.google import GoogleAuthenticator

__all__ = [
    "SERVICES",
    "Decision",
    "Grant",
    "ToolSpec",
    "build_tools",
    "decide",
    "discovery_document",
    "execute",
    "resolve_grant",
]

# Which APIs this server is willing to offer. The operations inside each one
# come from Google, not from here.
SERVICES: Mapping[str, tuple[str, str]] = {
    "calendar": ("calendar", "v3"),
    "gmail": ("gmail", "v1"),
    "docs": ("docs", "v1"),
    "sheets": ("sheets", "v4"),
    "drive": ("drive", "v3"),
}

READ_METHODS = frozenset({"GET"})

# Push-notification plumbing. A person never asks for it and a model that calls
# it gets a channel it cannot receive.
SERVER_ONLY_METHODS = ("watch", "stop")

PARAMETER_TYPES: Mapping[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
}

# Sharing and sending are refused whatever the token allows, because neither
# can be taken back once it has happened.
REFUSED_RESOURCES = ("acl", "permissions")
REFUSED_METHODS = ("send",)


@dataclass(frozen=True, slots=True)
class Grant:
    """A verified Workspace grant, with the scopes the person actually approved."""

    subject: str
    scopes: tuple[str, ...]
    credentials: Any

    def covers(self, required: Sequence[str]) -> bool:
        """Return whether any scope the method accepts was granted."""
        return bool(set(required) & set(self.scopes))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One Google API method, ready to expose as an MCP tool."""

    name: str
    service: str
    method_id: str
    http_method: str
    description: str
    parameters: Mapping[str, Any]
    required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    """What the gate decided about one call, before anything ran."""

    outcome: str
    reason: str


def resolve_grant(
    authenticator: GoogleAuthenticator, *, subject: str | None = None
) -> Grant | None:
    """Return the stored Workspace grant, or None when nobody has connected yet.

    This is the seam. A hosted server replaces this one function with a bearer
    token read off the request and returns the same Grant.
    """
    status = authenticator.status(CredentialPurpose.WORKSPACE, subject=subject)
    if not status.authenticated or not status.subject:
        return None
    credentials = authenticator.verified_credentials(
        CredentialPurpose.WORKSPACE, subject=status.subject
    )
    return Grant(
        subject=status.subject,
        scopes=tuple(status.granted_scopes or ()),
        credentials=credentials,
    )


def discovery_document(api_name: str, api_version: str) -> Mapping[str, Any]:
    """Read the discovery document shipped with the Google API client."""
    document = files("googleapiclient.discovery_cache").joinpath(
        f"documents/{api_name}.{api_version}.json"
    )
    return json.loads(document.read_text(encoding="utf-8"))


def _methods(resource: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Walk a discovery document's nested resources and yield every method."""
    yield from (resource.get("methods") or {}).values()
    for child in (resource.get("resources") or {}).values():
        yield from _methods(child)


def _tool_name(method_id: str) -> str:
    """Turn `calendar.events.list` into `calendar_events_list`."""
    return method_id.replace(".", "_")


def decide(spec: ToolSpec) -> Decision:
    """Judge one operation from its own metadata, before it runs."""
    parts = spec.method_id.split(".")
    if any(part in REFUSED_RESOURCES for part in parts):
        return Decision("blocked", "access is granted by people, not by an agent")
    if parts[-1] in REFUSED_METHODS:
        return Decision("blocked", "sending cannot be undone; a person sends")
    if spec.http_method in READ_METHODS:
        return Decision("allowed", "a read of named resources")
    return Decision("held", "others will see this; it needs a person's approval")


def build_tools(grant: Grant, *, services: Sequence[str] | None = None) -> tuple[ToolSpec, ...]:
    """Generate the tool list from the granted scopes.

    A method appears when the token carries one of the scopes it accepts, so a
    person who approved only Calendar sees only Calendar.
    """
    selected = tuple(services) if services is not None else tuple(SERVICES)
    unknown = [service for service in selected if service not in SERVICES]
    if unknown:
        raise ValueError(f"unknown Workspace service(s): {', '.join(unknown)}")
    specs: list[ToolSpec] = []
    for service in selected:
        api_name, api_version = SERVICES[service]
        try:
            document = discovery_document(api_name, api_version)
        except (FileNotFoundError, ModuleNotFoundError):
            # A service the installed client does not ship is simply absent.
            continue
        for method in _methods(document):
            if method["id"].rsplit(".", 1)[-1] in SERVER_ONLY_METHODS:
                continue
            required = tuple(method.get("scopes", ()))
            if not required or not grant.covers(required):
                continue
            parameters = dict(method.get("parameters") or {})
            # Discovery keeps the request body out of `parameters`. Without it
            # the model has nowhere to put the event it was asked to create.
            request = method.get("request") or {}
            if request:
                resource = str(request.get("$ref", "resource"))
                parameters["body"] = {
                    "type": "object",
                    "description": f"The {resource} to send, as a JSON object.",
                    "required": method.get("httpMethod") in ("POST", "PUT"),
                }
            specs.append(
                ToolSpec(
                    name=_tool_name(method["id"]),
                    service=service,
                    method_id=method["id"],
                    http_method=method.get("httpMethod", "GET"),
                    description=method.get("description", method["id"]),
                    parameters=parameters,
                    required=tuple(
                        sorted(
                            name
                            for name, schema in parameters.items()
                            if schema.get("required")
                        )
                    ),
                )
            )
    return tuple(sorted(specs, key=lambda spec: spec.name))


def execute(grant: Grant, spec: ToolSpec, arguments: Mapping[str, Any]) -> Any:
    """Run one allowed operation with the person's own credentials."""
    from googleapiclient.discovery import build

    api_name, api_version = SERVICES[spec.service]
    client = build(
        api_name,
        api_version,
        credentials=grant.credentials,
        cache_discovery=False,
    )
    node: Any = client
    parts = spec.method_id.split(".")[1:]
    for part in parts[:-1]:
        node = getattr(node, part)()
    return getattr(node, parts[-1])(**dict(arguments)).execute()
