"""Tests for the OpenCode HTTP/SSE adapter without a live server."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from adk_harness.adapters.opencode import OpenCodeHarness


class _Response:
    def __init__(self, payload: Any = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.closed = False

    def json(self) -> Any:
        return self._payload

    async def aclose(self) -> None:
        self.closed = True


class _StreamResponse(_Response):
    def __init__(self, lines: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._lines = lines

    def aiter_lines(self):
        async def iterator():
            for line in self._lines:
                yield line

        return iterator()

    async def __aenter__(self) -> _StreamResponse:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()


class _AsyncClient:
    health: _Response = _Response({"healthy": True, "version": "1.17.9"})
    session: _Response = _Response({"id": "sess-1"})
    prompt: _Response = _Response()
    stream_response: _StreamResponse = _StreamResponse([])
    calls: ClassVar[list[tuple[str, str, dict[str, Any]]]] = []

    def __init__(self, **_kwargs: Any) -> None:
        self.closed = False

    async def __aenter__(self) -> _AsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        self.closed = True

    async def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append(("GET", url, kwargs))
        return self.health

    async def post(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append(("POST", url, kwargs))
        return self.session if url == "/session" else self.prompt

    def stream(self, method: str, url: str, **kwargs: Any) -> _StreamResponse:
        self.calls.append((method, url, kwargs))
        return self.stream_response


def _fake_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    _AsyncClient.calls = []
    fake_httpx = SimpleNamespace(AsyncClient=_AsyncClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)


def _sse(event: dict[str, Any]) -> str:
    return "data: " + json.dumps(event)


@pytest.mark.asyncio
async def test_discover_health_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_httpx(monkeypatch)

    spec = await OpenCodeHarness().discover()

    assert spec.available is True
    assert spec.id == "opencode"
    assert spec.version == "1.17.9"
    assert "session_resume" in spec.capabilities


@pytest.mark.asyncio
async def test_discover_unavailable_without_server(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingClient(_AsyncClient):
        async def get(self, _url: str, **_kwargs: Any) -> _Response:
            raise OSError("connection refused")

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=FailingClient))

    spec = await OpenCodeHarness().discover()

    assert spec.available is False
    assert "connection refused" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_reports_missing_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)

    spec = await OpenCodeHarness().discover()

    assert spec.available is False
    assert "httpx" in (spec.detail or "")


@pytest.mark.asyncio
async def test_run_maps_sse_events_to_all_turn_kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_httpx(monkeypatch)
    _AsyncClient.stream_response = _StreamResponse(
        [
            _sse(
                {
                    "type": "message.part.updated",
                    "properties": {
                        "sessionID": "sess-1",
                        "part": {"type": "text", "text": "hello"},
                    },
                }
            ),
            "",
            _sse(
                {
                    "type": "session.next.tool.called",
                    "properties": {
                        "sessionID": "sess-1",
                        "callID": "c1",
                        "tool": "shell",
                        "input": {"command": "ls"},
                    },
                }
            ),
            "",
            _sse(
                {
                    "type": "session.next.tool.success",
                    "properties": {
                        "sessionID": "sess-1",
                        "callID": "c1",
                        "content": [{"type": "text", "text": "a.txt"}],
                    },
                }
            ),
            "",
            _sse(
                {
                    "type": "message.updated",
                    "properties": {
                        "sessionID": "sess-1",
                        "info": {
                            "role": "assistant",
                            "tokens": {"input": 2, "output": 3},
                            "cost": 0.01,
                        },
                    },
                }
            ),
            "",
            _sse(
                {
                    "type": "session.error",
                    "properties": {
                        "sessionID": "sess-1",
                        "error": {"message": "model unavailable"},
                    },
                }
            ),
            "",
        ]
    )

    turns = [turn async for turn in OpenCodeHarness().run("do it", cwd="/repo")]

    assert [turn.kind for turn in turns] == ["text", "tool_call", "tool_result", "usage", "error"]
    assert turns[0].text == "hello"
    assert turns[1].tool_name == "shell"
    assert turns[1].tool_args == {"command": "ls"}
    assert turns[2].text == "a.txt"
    assert turns[3].tool_args["tokens"]["output"] == 3
    assert turns[4].text == "model unavailable"
    assert any(call[1] == "/event" for call in _AsyncClient.calls)
    assert any(call[1] == "/session/sess-1/message" for call in _AsyncClient.calls)


@pytest.mark.asyncio
async def test_run_uses_existing_session_and_sends_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_httpx(monkeypatch)
    _AsyncClient.stream_response = _StreamResponse(
        ['data: {"type":"session.idle","properties":{"sessionID":"existing"}}', ""]
    )

    turns = [
        turn
        async for turn in OpenCodeHarness(model="provider/model", agent="build").run(
            "continue", cwd="/repo", session_id="existing"
        )
    ]

    assert turns == []
    prompt_calls = [call for call in _AsyncClient.calls if call[1] == "/session/existing/message"]
    assert prompt_calls
    assert prompt_calls[0][2]["json"] == {
        "agent": "build",
        "model": {"providerID": "provider", "modelID": "model"},
        "parts": [{"type": "text", "text": "continue"}],
    }


@pytest.mark.asyncio
async def test_aclose_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_httpx(monkeypatch)
    harness = OpenCodeHarness()

    await harness.aclose()
    await harness.aclose()
