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
EVENT = {"calendarId": "primary", "body": {"summary": "x"}}
OTHER_EVENT = {"calendarId": "team", "body": {"summary": "x"}}


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


async def test_a_write_runs_only_after_the_person_approves(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _state, calls = connected
    asked: list[str] = []

    async def approves(state, context, spec, arguments, change_hash):
        asked.append(spec.method_id)
        return True

    monkeypatch.setattr(mcp_stdio, "_ask_person", approves)
    result = await _call(server, "calendar_events_insert", EVENT, None)

    assert not result.isError
    assert asked == ["calendar.events.insert"]
    assert calls == [("calendar.events.insert", EVENT)]


async def test_a_declined_write_runs_nothing(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _state, calls = connected

    async def declines(state, context, spec, arguments, change_hash):
        return False

    monkeypatch.setattr(mcp_stdio, "_ask_person", declines)
    result = await _call(server, "calendar_events_insert", EVENT, None)

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
    """No elicitation callback at all, so the link is never accepted."""
    server, _state, calls = connected

    result = await _call(server, "calendar_events_insert", EVENT, None)

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


async def test_an_approval_is_bound_to_the_exact_arguments(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An approval for one call must not cover a different one."""
    server, state, _calls = connected

    async def approves(state_, context, spec, arguments, change_hash):
        return True

    monkeypatch.setattr(mcp_stdio, "_ask_person", approves)
    await _call(server, "calendar_events_insert", EVENT, None)
    await _call(server, "calendar_events_insert", OTHER_EVENT, None)

    approvals = [item.approval for item in state.evidence.trail if item.approval]
    assert len(approvals) == 2
    assert approvals[0].change_hash != approvals[1].change_hash
    assert all(item.approver_id == "person@example.com" for item in approvals)


async def test_a_refusal_is_recorded_rather_than_forgotten(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, state, calls = connected

    async def declines(state_, context, spec, arguments, change_hash):
        return False

    monkeypatch.setattr(mcp_stdio, "_ask_person", declines)
    await _call(server, "calendar_events_insert", EVENT, None)

    held = [item for item in state.evidence.trail if item.event.event_type == "held"]
    assert calls == []
    assert len(held) == 1
    assert held[0].approval is None
    assert held[0].change.content_hash


async def test_the_audit_trail_is_readable_in_the_conversation(connected: Any) -> None:
    server, _state, _calls = connected

    async def never(context: Any, params: Any) -> Any:
        raise AssertionError("a read must not ask")

    await _call(server, "calendar_events_list", {"calendarId": "primary"}, never)
    audit = await _call_tool(server, "governance_audit", {}, never)

    assert audit["ledger"] == "session only"
    decisions = audit["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["operation"] == "calendar.events.list"
    assert decisions[0]["outcome"] == "allowed"
    assert decisions[0]["change_hash"]


def test_the_ledger_receives_the_decision_when_one_is_configured() -> None:
    """A fleet points every machine at one project; this is that write."""
    from adk_harness.workspace.evidence import EvidenceWriter

    written: list[dict[str, Any]] = []

    class Ledger:
        def record(self, **payload: Any) -> str:
            written.append(payload)
            return "entry-1"

    writer = EvidenceWriter(project_id="demo", ledger=Ledger())
    change = writer.propose(
        subject="person@example.com",
        operation="calendar.events.insert",
        arguments={"calendarId": "primary"},
    )
    approval = writer.approve(change, approver="person@example.com", scope={})
    evidence = writer.record(
        change,
        actor="person@example.com",
        operation="calendar.events.insert",
        outcome="allowed",
        reason="approved",
        approval=approval,
    )

    assert evidence.ledger_entry_id == "entry-1"
    assert written[0]["action"] == "calendar.events.insert"
    assert written[0]["policy_outcome"] == "allowed"
    assert change.content_hash in written[0]["idempotency_key"]


def test_an_unreachable_ledger_does_not_stop_the_work() -> None:
    from adk_harness.workspace.evidence import EvidenceWriter

    class Broken:
        def record(self, **payload: Any) -> str:
            raise RuntimeError("firestore is unreachable")

    writer = EvidenceWriter(project_id="demo", ledger=Broken())
    change = writer.propose(subject="p", operation="calendar.events.list", arguments={})
    evidence = writer.record(
        change, actor="p", operation="calendar.events.list", outcome="allowed", reason="read"
    )

    assert evidence.ledger_entry_id is None
    assert writer.trail


async def test_the_project_is_offered_as_a_list_when_the_grant_can_see_them(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Picking from a list beats typing a project id from memory."""
    _server, state, _calls = connected
    monkeypatch.setattr(mcp_stdio, "_projects", lambda grant: ("alpha-1", "beta-2"))
    monkeypatch.setattr(mcp_stdio, "_ledger", lambda project: object())
    offered: list[dict[str, Any]] = []

    class Session:
        async def elicit_form(self, *, message: str, requestedSchema: dict[str, Any]) -> Any:
            offered.append(requestedSchema)
            return types.ElicitResult(action="accept", content={"project_id": "beta-2"})

    class Context:
        session = Session()

    result = await mcp_stdio._connect_ledger(state, Context(), None)

    assert offered[0]["properties"]["project_id"]["enum"] == ["alpha-1", "beta-2"]
    assert result == {"connected": True, "project": "beta-2", "ledger": "firestore"}
    assert state.evidence.project_id == "beta-2"


async def test_naming_a_project_skips_the_question(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An administrator can set it once and nobody is ever asked."""
    _server, state, _calls = connected
    monkeypatch.setattr(mcp_stdio, "_ledger", lambda project: object())

    class Context:
        session = None

    result = await mcp_stdio._connect_ledger(state, Context(), "set-by-admin")

    assert result["project"] == "set-by-admin"
    assert state.evidence.ledger is not None


async def test_declining_the_project_question_changes_nothing(
    connected: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _server, state, _calls = connected
    monkeypatch.setattr(mcp_stdio, "_projects", lambda grant: ("alpha-1",))

    class Session:
        async def elicit_form(self, *, message: str, requestedSchema: dict[str, Any]) -> Any:
            return types.ElicitResult(action="decline")

    class Context:
        session = Session()

    result = await mcp_stdio._connect_ledger(state, Context(), None)

    assert result["connected"] is False
    assert state.evidence.ledger is None


async def test_status_reports_whether_the_client_can_be_asked(connected: Any) -> None:
    """When no prompt appears, this says whether one was ever possible."""
    server, _state, _calls = connected

    async def never(context: Any, params: Any) -> Any:
        raise AssertionError("status must not ask")

    status = await _call_tool(server, "workspace_status", {}, never)

    assert status["client"]["known"] is True
    assert status["client"]["elicitation"] is True


async def test_a_client_that_will_not_ask_gets_a_link_instead(connected: Any) -> None:
    """Antigravity declines elicitation, so the person answers out of band."""
    server, _state, calls = connected

    result = await _call_tool(
        server, "calendar_events_insert", EVENT, None
    )

    assert calls == []
    assert result["outcome"] == "held"
    assert result["approval_url"].startswith("http://127.0.0.1:")
    assert "/approve/" in result["approval_url"]


async def test_the_same_change_keeps_one_link(connected: Any) -> None:
    """Asking twice must not leave two live approvals for one change."""
    server, _state, _calls = connected

    first = await _call_tool(server, "calendar_events_insert", EVENT, None)
    second = await _call_tool(server, "calendar_events_insert", EVENT, None)

    assert first["approval_url"] == second["approval_url"]


async def test_an_answered_link_lets_the_next_call_run(connected: Any) -> None:
    server, state, calls = connected

    held = await _call_tool(server, "calendar_events_insert", EVENT, None)
    token = held["approval_url"].rsplit("/", 1)[-1]
    state.approvals._pending[token].resolve(True)
    item = state.approvals._pending.pop(token)
    state.approvals._granted[item.change_hash] = item

    result = await _call_tool(server, "calendar_events_insert", EVENT, None)

    assert result["outcome"] == "allowed"
    assert calls == [("calendar.events.insert", EVENT)]
    assert result["evidence"]["approved_by"] == "person@example.com"


async def test_approving_one_change_does_not_run_another(connected: Any) -> None:
    """The approval is bound to the arguments the person was shown."""
    server, state, calls = connected

    held = await _call_tool(server, "calendar_events_insert", EVENT, None)
    token = held["approval_url"].rsplit("/", 1)[-1]
    state.approvals._pending[token].resolve(True)
    item = state.approvals._pending.pop(token)
    state.approvals._granted[item.change_hash] = item

    other = await _call_tool(server, "calendar_events_insert", OTHER_EVENT, None)

    assert other["outcome"] == "held"
    assert calls == []


async def test_a_write_advertises_the_body_it_needs(connected: Any) -> None:
    """Without this the model calls insert with no event and then improvises."""
    server, _state, _calls = connected
    insert = server._tool_manager.get_tool("calendar_events_insert")

    assert "body" in insert.parameters["properties"]
    assert set(insert.parameters["required"]) == {"body", "calendarId"}
    assert "Event" in insert.parameters["properties"]["body"]["description"]


async def test_a_read_has_no_body(connected: Any) -> None:
    server, _state, _calls = connected
    listing = server._tool_manager.get_tool("calendar_events_list")

    assert "body" not in listing.parameters["properties"]
