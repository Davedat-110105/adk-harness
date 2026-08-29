"""Offline tests for the finite Workspace connection boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

import httplib2
import pytest

from adk_harness.workspace import (
    CredentialReference,
    WorkspaceConnection,
    WorkspaceConsent,
    WorkspaceDenied,
    WorkspaceStale,
    WorkspaceUnknownOutcome,
    WorkspaceUnsupported,
)
from adk_harness.workspace.connections import OPERATIONS


class _Request:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.headers: dict[str, str] = {}

    def execute(self) -> Any:
        return self.value


class _Events:
    def __init__(self) -> None:
        self.current = {
            "id": "event1",
            "etag": '"v1"',
            "reminders": {"useDefault": False, "overrides": []},
        }
        self.request: _Request | None = None

    def get(self, **kwargs: Any) -> _Request:
        return _Request(self.current)

    def list(self, **kwargs: Any) -> _Request:
        self.request = _Request({"items": []})
        self.kwargs = kwargs
        return self.request

    def update(self, **kwargs: Any) -> _Request:
        self.request = _Request({"id": kwargs["eventId"]})
        self.kwargs = kwargs
        return self.request

    def insert(self, **kwargs: Any) -> _Request:
        self.request = _Request({"id": kwargs["body"]["id"]})
        self.kwargs = kwargs
        return self.request

    def delete(self, **kwargs: Any) -> _Request:
        self.request = _Request({})
        self.kwargs = kwargs
        return self.request


class _Calendar:
    def __init__(self) -> None:
        self.events_client = _Events()
        self.closed = False

    def calendarList(self) -> Any:
        return self

    def get(self, **kwargs: Any) -> _Request:
        return _Request({"id": kwargs["calendarId"], "accessRole": "writer"})

    def events(self) -> _Events:
        return self.events_client

    def close(self) -> None:
        self.closed = True


class _Auth:
    def __init__(self, token: str) -> None:
        self.token = token

    def verified_credentials(self, purpose: Any, *, subject: str, required_scopes: Any) -> object:
        return {"user": subject, "token": self.token}


def _connection(
    *, approved: bool = True, expiry: datetime | None = None
) -> tuple[WorkspaceConnection, _Calendar]:
    service = _Calendar()
    consent = WorkspaceConsent(
        subject="user-a",
        applications=("calendar",),
        resources={"calendar": ("primary",)},
        operations=(
            "calendar_list_events",
            "calendar_update_event",
            "calendar_create_event",
            "calendar_delete_event",
        ),
        approved=approved,
        expires_at=expiry or datetime.now(UTC) + timedelta(minutes=5),
        calendar_windows={"primary": ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")},
        calendar_event_ids={"primary": ("event1",)},
    )
    connection = WorkspaceConnection(
        authenticator=_Auth("A"),
        credential_reference=CredentialReference(subject="user-a"),
        consent=consent,
        service_factory=lambda app, credentials: service,
    )
    return connection, service


def test_calendar_read_is_bounded_and_closes_client() -> None:
    connection, service = _connection()
    result = connection.calendar_list_events(
        calendar_id="primary",
        time_min="2026-09-01T00:00:00Z",
        time_max="2026-09-02T00:00:00Z",
    )
    assert result == {"items": []}
    assert service.events_client.kwargs["maxResults"] == 25
    assert service.closed


def test_missing_consent_and_resource_access_fail_closed() -> None:
    connection, _ = _connection(approved=False)
    with pytest.raises(WorkspaceDenied, match="consent"):
        connection.calendar_list_events(
            calendar_id="primary",
            time_min="2026-09-01T00:00:00Z",
            time_max="2026-09-02T00:00:00Z",
        )


def test_mutation_requires_host_and_uses_if_match() -> None:
    connection, service = _connection()
    with pytest.raises(WorkspaceDenied, match="trusted host"):
        connection.calendar_update_event(
            calendar_id="primary",
            event_id="event1",
            body={
                "id": "event1",
                "start": {"date": "2026-09-01"},
                "end": {"date": "2026-09-02"},
                "reminders": {"useDefault": False, "overrides": []},
            },
            approved_etag='"v1"',
        )
    result = connection.calendar_update_event(
        calendar_id="primary",
        event_id="event1",
        body={
            "id": "event1",
            "start": {"date": "2026-09-01"},
            "end": {"date": "2026-09-02"},
            "reminders": {"useDefault": False, "overrides": []},
        },
        approved_etag='"v1"',
        host_authorizer=lambda operation, payload: payload["calendar_id"] == "primary",
    )
    assert result == {"id": "event1"}
    assert service.events_client.request is not None
    assert service.events_client.request.headers["If-Match"] == '"v1"'


def test_existing_event_side_effects_are_refused() -> None:
    connection, service = _connection()
    service.events_client.current = {
        "id": "event1",
        "etag": '"v1"',
        "attendees": [{"email": "x"}],
        "reminders": {"useDefault": False, "overrides": []},
    }
    with pytest.raises(WorkspaceUnsupported, match="side effects"):
        connection.calendar_delete_event(
            calendar_id="primary",
            event_id="event1",
            approved_etag='"v1"',
            host_authorizer=lambda operation, payload: True,
        )


def test_official_discovery_build_uses_explicit_user_credentials() -> None:
    """The pinned fallback constructs real Resources without ADC or network."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credential_a = Credentials(token="synthetic-user-a")
    calendar = build(
        "calendar",
        "v3",
        credentials=credential_a,
        static_discovery=True,
        cache_discovery=False,
    )
    request = calendar.events().get(calendarId="primary", eventId="event1")
    assert "/calendars/primary/events/event1?" in request.uri
    assert request.http.credentials is credential_a


def test_model_tool_declaration_has_typed_finite_parameters() -> None:
    from google.adk.models.llm_request import LlmRequest
    from google.adk.tools.function_tool import FunctionTool

    from adk_harness.workspace.app import _planning_tool

    connection, _ = _connection()
    request = LlmRequest()
    request.append_tools([FunctionTool(_planning_tool(connection, "calendar_get_event"))])
    schema = request.config.tools[0].function_declarations[0].parameters_json_schema
    assert set(schema["properties"]) == {"calendar_id", "event_id"}
    assert set(schema["required"]) == {"calendar_id", "event_id"}


def test_serialized_consent_retains_exact_record_bounds() -> None:
    connection, _ = _connection()
    config = connection.config()["consent"]
    assert config["calendar_windows"]["primary"] == (
        "2026-09-01T00:00:00Z",
        "2026-09-02T00:00:00Z",
    )
    assert config["calendar_event_ids"]["primary"] == ("event1",)


def test_real_discovery_requests_use_a_bearer_header_and_classify_failures() -> None:
    from google.oauth2.credentials import Credentials

    base, _ = _connection()
    calls: list[tuple[str, str, dict[str, str], str | None]] = []

    class Auth:
        def verified_credentials(self, *args: Any, **kwargs: Any) -> Credentials:
            return Credentials(token="transport-user-a")

    connection = WorkspaceConnection(
        authenticator=Auth(),  # type: ignore[arg-type]
        credential_reference=CredentialReference(subject="user-a"),
        consent=base.consent,
    )

    def transport(
        self: Any,
        uri: str,
        method: str = "GET",
        body: Any = None,
        headers: Any = None,
        **kwargs: Any,
    ) -> Any:
        request_headers = dict(headers or {})
        calls.append((method, urlparse(uri).path, request_headers, body))
        path = urlparse(uri).path
        if method == "PUT":
            return (
                httplib2.Response({"status": "412", "content-type": "application/json"}),
                json.dumps({"error": {"status": "ABORTED", "message": "etag stale"}}).encode(),
            )
        if path.endswith("/calendarList/primary"):
            payload = {"id": "primary", "accessRole": "writer"}
        elif path.endswith("/events/event1"):
            payload = {
                "id": "event1",
                "etag": '"v1"',
                "eventType": "default",
                "reminders": {"useDefault": False, "overrides": []},
            }
        else:
            payload = {"items": []}
        return (
            httplib2.Response({"status": "200", "content-type": "application/json"}),
            json.dumps(payload).encode(),
        )

    event = {
        "id": "event1",
        "start": {"date": "2026-09-01"},
        "end": {"date": "2026-09-02"},
        "reminders": {"useDefault": False, "overrides": []},
    }
    with patch.object(httplib2.Http, "request", transport):
        with pytest.raises(WorkspaceStale):
            connection.calendar_update_event(
                calendar_id="primary",
                event_id="event1",
                body=event,
                approved_etag='"v1"',
                host_authorizer=lambda *args: True,
            )
    assert calls and all(
        headers.get("authorization") == "Bearer transport-user-a"
        for _, _, headers, _ in calls
    )
    assert any(headers.get("If-Match") == '"v1"' for _, _, headers, _ in calls)

    def timeout(
        self: Any,
        uri: str,
        method: str = "GET",
        body: Any = None,
        headers: Any = None,
        **kwargs: Any,
    ) -> Any:
        if method == "POST":
            raise TimeoutError("synthetic disconnect")
        return transport(self, uri, method, body, headers, **kwargs)

    with patch.object(httplib2.Http, "request", timeout):
        with pytest.raises(WorkspaceUnknownOutcome):
            connection.calendar_create_event(
                calendar_id="primary", body=event, host_authorizer=lambda *args: True
            )


def test_real_transport_executes_all_ten_finite_operations_for_isolated_users() -> None:
    from google.oauth2.credentials import Credentials

    consent = WorkspaceConsent(
        subject="user-a",
        applications=("calendar", "gmail", "docs", "sheets"),
        resources={
            "calendar": ("primary",), "gmail": ("me",),
            "docs": ("doc1",), "sheets": ("sheet1",),
        },
        operations=tuple(OPERATIONS),
        approved=True,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        calendar_windows={"primary": ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")},
        sheets_ranges={"sheet1": ("A1:B2",)},
        calendar_event_ids={"primary": ("event1",)},
        gmail_draft_ids=("draft1",),
    )

    class Auth:
        def __init__(self, token: str) -> None:
            self.token = token

        def verified_credentials(self, *args: Any, **kwargs: Any) -> Credentials:
            return Credentials(token=self.token)

    def make(subject: str) -> WorkspaceConnection:
        return WorkspaceConnection(
            authenticator=Auth("transport-" + subject),  # type: ignore[arg-type]
            credential_reference=CredentialReference(subject=subject),
            consent=consent if subject == "user-a" else WorkspaceConsent(
                subject=subject,
                applications=consent.applications,
                resources=consent.resources,
                operations=consent.operations,
                approved=True,
                expires_at=consent.expires_at,
                calendar_windows=consent.calendar_windows,
                sheets_ranges=consent.sheets_ranges,
                calendar_event_ids=consent.calendar_event_ids,
                gmail_draft_ids=consent.gmail_draft_ids,
            ),
        )

    calls: list[tuple[str, str, dict[str, str], Any]] = []

    def transport(
        self: Any, uri: str, method: str = "GET", body: Any = None,
        headers: Any = None, **kwargs: Any,
    ) -> Any:
        path = urlparse(uri).path
        request_headers = dict(headers or {})
        calls.append((method, path, request_headers, body))
        if method == "DELETE":
            return httplib2.Response({"status": "204"}), b""
        if "/calendarList/" in path:
            payload = {"id": "primary", "accessRole": "writer"}
        elif "/events/" in path:
            payload = {
                "id": "event1", "etag": '"v1"', "eventType": "default",
                "reminders": {"useDefault": False},
            }
        elif "/drafts/" in path:
            payload = {"id": "draft1", "message": {"id": "msg1"}}
        elif "/drafts" in path:
            payload = {"drafts": []}
        elif "/documents/" in path:
            payload = {"documentId": "doc1", "revisionId": "rev1"}
        elif "/spreadsheets/" in path:
            payload = {"range": "A1:B2", "values": [[1]]}
        else:
            payload = {"items": []}
        return (
            httplib2.Response({"status": "200", "content-type": "application/json"}),
            json.dumps(payload).encode(),
        )

    event = {
        "id": "event1", "start": {"date": "2026-09-01"},
        "end": {"date": "2026-09-02"},
        "reminders": {"useDefault": False, "overrides": []},
    }
    def allow(*args: Any) -> bool:
        return True
    first = make("user-a")
    operations = (
        lambda c: c.calendar_get_event(calendar_id="primary", event_id="event1"),
        lambda c: c.calendar_list_events(
            calendar_id="primary", time_min="2026-09-01T00:00:00Z",
            time_max="2026-09-02T00:00:00Z",
        ),
        lambda c: c.gmail_get_draft(draft_id="draft1"),
        lambda c: c.gmail_list_drafts(),
        lambda c: c.docs_get(document_id="doc1"),
        lambda c: c.sheets_get_values(spreadsheet_id="sheet1", range="A1:B2"),
        lambda c: c.calendar_create_event(
            calendar_id="primary", body=event, host_authorizer=allow,
        ),
        lambda c: c.calendar_update_event(
            calendar_id="primary", event_id="event1", body=event,
            approved_etag='"v1"', host_authorizer=allow,
        ),
        lambda c: c.calendar_delete_event(
            calendar_id="primary", event_id="event1", approved_etag='"v1"',
            host_authorizer=allow,
        ),
        lambda c: c.docs_insert_text(
            document_id="doc1", index=1, text="test", required_revision_id="rev1",
            host_authorizer=allow,
        ),
    )
    with patch.object(httplib2.Http, "request", transport):
        for operation in operations:
            operation(first)
        before_b = len(calls)
        make("user-b").docs_get(document_id="doc1")
    assert len(calls) > before_b
    assert all(
        headers.get("authorization") == "Bearer transport-user-a"
        for _, _, headers, _ in calls[:before_b]
    )
    assert calls[-1][2].get("authorization") == "Bearer transport-user-b"
    assert any(
        method == "POST" and isinstance(body, str) and '"reminders"' in body
        for method, _, _, body in calls
    )
    assert any(headers.get("If-Match") == '"v1"' for _, _, headers, _ in calls)
    assert any(
        headers.get("authorization") == "Bearer transport-user-a"
        for _, _, headers, _ in calls
    )


def test_real_transport_503_and_malformed_success_are_unknown_outcomes() -> None:
    from google.oauth2.credentials import Credentials

    base, _ = _connection()

    class Auth:
        def verified_credentials(self, *args: Any, **kwargs: Any) -> Credentials:
            return Credentials(token="outcome-user")

    connection = WorkspaceConnection(
        authenticator=Auth(),  # type: ignore[arg-type]
        credential_reference=CredentialReference(subject="user-a"),
        consent=base.consent,
    )
    event = {
        "id": "event1", "start": {"date": "2026-09-01"},
        "end": {"date": "2026-09-02"},
        "reminders": {"useDefault": False, "overrides": []},
    }

    def transport(
        self: Any, uri: str, method: str = "GET", body: Any = None,
        headers: Any = None, **kwargs: Any,
    ) -> Any:
        path = urlparse(uri).path
        if path.endswith("/calendarList/primary"):
            payload = {"id": "primary", "accessRole": "writer"}
            return httplib2.Response({"status": "200"}), json.dumps(payload).encode()
        if path.endswith("/events/event1"):
            payload = {"id": "event1", "etag": '"v1"', "reminders": {"useDefault": False}}
            return httplib2.Response({"status": "200"}), json.dumps(payload).encode()
        if method == "POST":
            return httplib2.Response({"status": "503"}), b'{"error":{"status":"UNAVAILABLE"}}'
        return httplib2.Response({"status": "200"}), b'"malformed"'

    with patch.object(httplib2.Http, "request", transport):
        with pytest.raises(WorkspaceUnknownOutcome) as error:
            connection.calendar_create_event(
                calendar_id="primary", body=event, host_authorizer=lambda *args: True
            )
    assert "outcome-user" not in str(error.value)

    def malformed(
        self: Any, uri: str, method: str = "GET", body: Any = None,
        headers: Any = None, **kwargs: Any,
    ) -> Any:
        path = urlparse(uri).path
        if path.endswith("/calendarList/primary"):
            payload = {"id": "primary", "accessRole": "writer"}
        elif path.endswith("/events/event1"):
            payload = {"id": "event1", "etag": '"v1"', "reminders": {"useDefault": False}}
        else:
            return httplib2.Response({"status": "200"}), b'"malformed"'
        return httplib2.Response({"status": "200"}), json.dumps(payload).encode()

    with patch.object(httplib2.Http, "request", malformed):
        with pytest.raises(WorkspaceUnknownOutcome):
            connection.calendar_create_event(
                calendar_id="primary", body=event, host_authorizer=lambda *args: True
            )
