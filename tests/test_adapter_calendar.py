"""Tests for the Google Calendar REST adapter without credentials or network."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from adk_harness.adapters.calendar import CalendarHarness

SCOPE = "https://www.googleapis.com/auth/calendar.events"


class FakeHttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps({"error": {"message": message}}).encode()
        super().__init__(message)


class FakeRequest:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def execute(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.result


class FakeEvents:
    def __init__(
        self,
        *,
        probe_error: Exception | None = None,
        insert_result: Any = None,
        insert_error: Exception | None = None,
    ) -> None:
        self.probe_error = probe_error
        self.insert_result = insert_result
        self.insert_error = insert_error
        self.insert_calls: list[dict[str, Any]] = []

    def list(self, **_kwargs: Any) -> FakeRequest:
        return FakeRequest({}, self.probe_error)

    def insert(self, **kwargs: Any) -> FakeRequest:
        self.insert_calls.append(kwargs)
        return FakeRequest(self.insert_result, self.insert_error)


class FakeService:
    def __init__(self, events: FakeEvents) -> None:
        self.events_api = events

    def events(self) -> FakeEvents:
        return self.events_api


def install_google_fakes(
    monkeypatch: pytest.MonkeyPatch,
    default: Callable[..., Any],
    service: FakeService,
) -> None:
    google = ModuleType("google")
    auth = ModuleType("google.auth")
    auth.default = default  # type: ignore[attr-defined]
    google.auth = auth  # type: ignore[attr-defined]

    googleapiclient = ModuleType("googleapiclient")
    discovery = ModuleType("googleapiclient.discovery")
    discovery.build = lambda *_args, **_kwargs: service  # type: ignore[attr-defined]
    googleapiclient.discovery = discovery  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", auth)
    monkeypatch.setitem(sys.modules, "googleapiclient", googleapiclient)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)


@pytest.mark.asyncio
async def test_discover_without_credentials_reports_useful_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def default(*, scopes: list[str]) -> Any:
        assert scopes == [SCOPE]
        raise RuntimeError("ADC not configured")

    install_google_fakes(monkeypatch, default, FakeService(FakeEvents()))

    spec = await CalendarHarness().discover()

    assert spec.available is False
    assert "Application Default Credentials" in (spec.detail or "")
    assert "ADC not configured" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_403_names_missing_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    events = FakeEvents(probe_error=FakeHttpError(403, "Insufficient Permission"))

    install_google_fakes(monkeypatch, lambda **_kwargs: (object(), "project"), FakeService(events))

    spec = await CalendarHarness().discover()

    assert spec.available is False
    assert "HTTP 403" in (spec.detail or "")
    assert SCOPE in (spec.detail or "")


@pytest.mark.asyncio
async def test_dry_run_does_not_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    events = FakeEvents()
    install_google_fakes(monkeypatch, lambda **_kwargs: (object(), "project"), FakeService(events))
    harness = CalendarHarness(dry_run=True)
    await harness.discover()

    turns = [turn async for turn in harness.run("Lunch with Sam", cwd="/tmp")]

    assert [turn.kind for turn in turns] == ["tool_call", "tool_result", "usage"]
    assert turns[0].tool_name == "calendar.events.insert"
    assert turns[0].tool_args == {"summary": "Lunch with Sam"}
    assert turns[1].text == "dry run: nothing was created"
    assert events.insert_calls == []


@pytest.mark.asyncio
async def test_successful_insert_maps_tool_call_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"summary": "Planning", "start": {"date": "2026-08-28"}}
    created = {"id": "event-123", "htmlLink": "https://calendar.google.com/event-123"}
    events = FakeEvents(insert_result=created)
    install_google_fakes(monkeypatch, lambda **_kwargs: (object(), "project"), FakeService(events))
    harness = CalendarHarness(dry_run=False)
    await harness.discover()

    turns = [turn async for turn in harness.run(json.dumps(body), cwd="/tmp")]

    assert [turn.kind for turn in turns] == ["tool_call", "tool_result", "usage"]
    assert turns[0].tool_args == body
    assert events.insert_calls == [{"calendarId": "primary", "body": body}]
    assert turns[1].raw == created
    assert "event-123" in (turns[1].text or "")
    assert "https://calendar.google.com/event-123" in (turns[1].text or "")


@pytest.mark.asyncio
async def test_http_error_becomes_error_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    events = FakeEvents(insert_error=FakeHttpError(500, "Calendar unavailable"))
    install_google_fakes(monkeypatch, lambda **_kwargs: (object(), "project"), FakeService(events))
    harness = CalendarHarness(dry_run=False)
    await harness.discover()

    turns = [turn async for turn in harness.run("Retry appointment", cwd="/tmp")]

    assert [turn.kind for turn in turns] == ["tool_call", "error", "usage"]
    assert "HTTP 500" in (turns[1].text or "")
    assert "Calendar unavailable" in (turns[1].text or "")
