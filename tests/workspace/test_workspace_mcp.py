from __future__ import annotations

from typing import Any

import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from adk_harness.auth.google import GoogleAuthError
from adk_harness.workspace import mcp_stdio, tools
from adk_harness.workspace.tools import Grant, build_tools, decide

CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"
CALENDAR_ACLS = "https://www.googleapis.com/auth/calendar.acls"


def _grant(*scopes: str) -> Grant:
    return Grant(subject="person@example.com", scopes=scopes, credentials=object())


def test_tools_follow_the_granted_scopes() -> None:
    """A narrower grant produces fewer tools, with nothing hand written."""
    events_only = {
        spec.name for spec in build_tools(_grant(CALENDAR_EVENTS), services=["calendar"])
    }
    with_acls = {
        spec.name
        for spec in build_tools(_grant(CALENDAR_EVENTS, CALENDAR_ACLS), services=["calendar"])
    }

    assert "calendar_events_list" in events_only
    assert not any(name.startswith("calendar_acl_") for name in events_only)
    assert events_only < with_acls


def test_no_grant_produces_no_tools() -> None:
    assert build_tools(_grant()) == ()


def test_the_gate_reads_the_method_rather_than_a_list() -> None:
    specs = {spec.name: spec for spec in build_tools(_grant(CALENDAR_EVENTS, CALENDAR_ACLS))}

    assert decide(specs["calendar_events_list"]).outcome == "allowed"
    assert decide(specs["calendar_events_insert"]).outcome == "held"
    assert decide(specs["calendar_acl_insert"]).outcome == "blocked"


def test_unknown_service_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown Workspace service"):
        build_tools(_grant(CALENDAR_EVENTS), services=["payroll"])


class _StubAuthenticator:
    """Stand in for Google so the round trip needs no network and no account."""

    def __init__(self, grant: Grant) -> None:
        self._grant = grant

    def status(self, purpose: Any, *, subject: str | None = None) -> Any:
        raise AssertionError("resolve_grant is patched in these tests")


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch) -> Any:
    grant = _grant(CALENDAR_EVENTS)
    monkeypatch.setattr(mcp_stdio, "resolve_grant", lambda authenticator: grant)
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_execute(_grant: Grant, spec: Any, arguments: Any) -> Any:
        calls.append((spec.method_id, dict(arguments)))
        return {"id": "event-1"}

    monkeypatch.setattr(mcp_stdio, "execute", fake_execute)
    server, state = mcp_stdio.build_server(lambda: _StubAuthenticator(grant))  # type: ignore[arg-type,return-value]
    return server, state, calls


async def _call_tool(server: Any, name: str, arguments: dict[str, Any], elicit: Any) -> Any:
    """Call a tool whose arguments are its own, not wrapped in `arguments`."""
    import json

    async with create_connected_server_and_client_session(
        server._mcp_server, elicitation_callback=elicit
    ) as client:
        result = await client.call_tool(name, arguments)
    return json.loads(result.content[0].text)


async def _call(server: Any, name: str, arguments: dict[str, Any], elicit: Any) -> Any:
    async with create_connected_server_and_client_session(
        server._mcp_server, elicitation_callback=elicit
    ) as client:
        return await client.call_tool(name, arguments)


async def test_a_read_runs_without_asking(connected: Any) -> None:
    server, _state, calls = connected

    async def never(context: Any, params: Any) -> Any:
        raise AssertionError("a read must not ask for approval")

    result = await _call(server, "calendar_events_list", {"calendarId": "primary"}, never)

    assert not result.isError
    assert calls == [("calendar.events.list", {"calendarId": "primary"})]


async def test_a_write_runs_only_after_the_person_approves(connected: Any) -> None:
    server, _state, calls = connected
    asked: list[str] = []

    async def approve(context: Any, params: Any) -> Any:
        asked.append(params.message)
        return types.ElicitResult(action="accept", content={"approve": True, "reason": "mine"})

    result = await _call(server, "calendar_events_insert", {"calendarId": "primary"}, approve)

    assert not result.isError
    assert len(asked) == 1
    assert "calendar.events.insert" in asked[0]
    assert calls == [("calendar.events.insert", {"calendarId": "primary"})]


async def test_a_declined_write_runs_nothing(connected: Any) -> None:
    server, _state, calls = connected

    async def decline(context: Any, params: Any) -> Any:
        return types.ElicitResult(action="decline")

    result = await _call(server, "calendar_events_insert", {"calendarId": "primary"}, decline)

    assert not result.isError
    assert calls == []
    assert "held" in str(result.content).lower()


def test_sharing_stays_refused_even_when_granted() -> None:
    specs = {spec.name: spec for spec in build_tools(_grant(CALENDAR_EVENTS, CALENDAR_ACLS))}
    decision = decide(specs["calendar_acl_insert"])

    assert decision.outcome == "blocked"
    assert "people" in decision.reason


def test_discovery_documents_come_from_the_installed_client() -> None:
    document = tools.discovery_document("calendar", "v3")

    assert document["title"]
    assert "resources" in document


def test_the_server_advertises_that_its_tool_list_changes(connected: Any) -> None:
    """Without this the client never asks for the tool list again."""
    server, _state, _calls = connected
    options = server._mcp_server.create_initialization_options()

    assert options.capabilities.tools is not None
    assert options.capabilities.tools.listChanged is True


async def test_a_client_that_cannot_ask_runs_nothing(connected: Any) -> None:
    server, _state, calls = connected

    result = await _call(server, "calendar_events_insert", {"calendarId": "primary"}, None)

    assert calls == []
    assert "held" in str(result.content).lower()


def test_the_server_starts_without_an_oauth_client_configuration() -> None:
    """A judge installs before they configure anything, and it must still run."""

    def unconfigured() -> Any:
        raise GoogleAuthError("Google OAuth client configuration is not configured")

    server, state = mcp_stdio.build_server(unconfigured)

    assert state.grant is None
    assert state.specs == {}
    assert server is not None


async def test_connecting_again_reuses_the_grant_instead_of_a_second_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A returning person should not be sent back to Google's consent screen."""
    grant = _grant(CALENDAR_EVENTS)
    monkeypatch.setattr(mcp_stdio, "resolve_grant", lambda authenticator: grant)
    logins: list[Any] = []

    class Authenticator:
        def login(self, purpose: Any, *, scopes: Any) -> None:
            logins.append(scopes)

    server, _state = mcp_stdio.build_server(Authenticator)  # type: ignore[arg-type]

    async def never(context: Any, params: Any) -> Any:
        raise AssertionError("connecting must not need approval")

    result = await _call_tool(server, "connect_workspace", {"services": ["calendar"]}, never)

    assert logins == []
    assert result["reused_existing_grant"] is True
    assert "calendar_events_list" in result["tools"]


async def test_a_service_outside_the_grant_still_asks_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = _grant(CALENDAR_EVENTS)
    monkeypatch.setattr(mcp_stdio, "resolve_grant", lambda authenticator: grant)
    logins: list[Any] = []

    class Authenticator:
        def login(self, purpose: Any, *, scopes: Any) -> None:
            logins.append(tuple(scopes))

    server, _state = mcp_stdio.build_server(Authenticator)  # type: ignore[arg-type]

    async def never(context: Any, params: Any) -> Any:
        raise AssertionError("connecting must not need approval")

    await _call_tool(server, "connect_workspace", {"services": ["sheets"]}, never)

    assert len(logins) == 1


def test_status_reports_why_no_tools_appeared() -> None:
    def unconfigured() -> Any:
        raise GoogleAuthError("Google OAuth client configuration is not configured")

    _server, state = mcp_stdio.build_server(unconfigured)

    assert state.specs == {}
    assert state.startup_error is not None
    assert "GoogleAuthError" in state.startup_error


async def test_a_tool_advertises_the_operation_s_real_parameters(connected: Any) -> None:
    """Without this the model guesses field names and burns a turn on the error."""
    server, _state, _calls = connected
    tool = server._tool_manager.get_tool("calendar_events_list")

    assert tool.parameters["required"] == ["calendarId"]
    assert "maxResults" in tool.parameters["properties"]
    assert tool.parameters["properties"]["calendarId"]["description"]


def test_push_notification_plumbing_is_not_offered(connected: Any) -> None:
    server, _state, _calls = connected

    assert "calendar_events_watch" not in server._tool_manager._tools
    assert "calendar_channels_stop" not in server._tool_manager._tools
