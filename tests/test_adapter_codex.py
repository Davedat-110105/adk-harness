"""Tests for the Codex adapter.

These must pass on a machine where the `codex` binary is not installed: every
test patches `asyncio.create_subprocess_exec` with a fake and never touches a
real subprocess or the network.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from adk_harness.adapters.codex import CodexHarness


class _FakeStdin:
    def __init__(self) -> None:
        self.written = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeLineStream:
    """Async-iterable over pre-scripted lines, like a StreamReader."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    def __aiter__(self) -> _FakeLineStream:
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class FakeProcess:
    def __init__(
        self,
        *,
        stdout_lines: list[bytes] = (),
        stderr_lines: list[bytes] = (),
        returncode: int = 0,
        version_stdout: bytes = b"",
        version_stderr: bytes = b"",
    ) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeLineStream(list(stdout_lines))
        self.stderr = _FakeLineStream(list(stderr_lines))
        self.returncode: int | None = None
        self._final_returncode = returncode
        self._version_stdout = version_stdout
        self._version_stderr = version_stderr
        self.terminated = False
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        self.returncode = self._final_returncode
        return self._version_stdout, self._version_stderr

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = self._final_returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, process: FakeProcess | Exception) -> list[list[str]]:
    """Patch asyncio.create_subprocess_exec, recording the args it was called with."""
    calls: list[list[str]] = []

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> FakeProcess:
        calls.append(list(args))
        if isinstance(process, Exception):
            raise process
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return calls


# --- discover() ---------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_subprocess(monkeypatch, FileNotFoundError())
    harness = CodexHarness(binary="codex-does-not-exist")

    spec = await harness.discover()

    assert spec.available is False
    assert spec.id == "codex"
    assert "could not be run" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_version_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(returncode=0, version_stdout=b"codex-cli 0.149.1\n")
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    spec = await harness.discover()

    assert spec.available is True
    assert spec.version == "0.149.1"
    assert spec.id == "codex"
    assert "tool_call" in spec.capabilities


@pytest.mark.asyncio
async def test_discover_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(returncode=1, version_stderr=b"auth error\n")
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    spec = await harness.discover()

    assert spec.available is False
    assert "auth error" in (spec.detail or "")


# --- run() kind mapping ---------------------------------------------------


def _line(msg: dict[str, Any]) -> bytes:
    return (json.dumps({"id": "t0", "msg": msg}) + "\n").encode()


@pytest.mark.asyncio
async def test_run_maps_every_turn_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        _line({"type": "session_configured"}),  # dropped: banner
        _line({"type": "agent_message", "message": "hello there"}),
        _line({"type": "exec_command_begin", "call_id": "c1", "command": ["ls", "-la"]}),
        _line({"type": "exec_command_end", "call_id": "c1", "stdout": "a.txt\n", "exit_code": 0}),
        _line({"type": "token_count", "input_tokens": 10, "output_tokens": 5}),
        _line({"type": "agent_message_delta", "delta": "hel"}),  # dropped: delta
        _line({"type": "task_complete", "last_agent_message": "hello there"}),  # dropped
    ]
    process = FakeProcess(stdout_lines=lines, returncode=0)
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    turns = [t async for t in harness.run("do something", cwd="/tmp")]

    kinds = [t.kind for t in turns]
    assert kinds == ["text", "tool_call", "tool_result", "usage"]

    text_turn = turns[0]
    assert text_turn.text == "hello there"
    assert text_turn.raw["msg"]["type"] == "agent_message"

    call_turn = turns[1]
    assert call_turn.tool_name == "ls -la"  # falls back to the command list
    assert call_turn.tool_args["call_id"] == "c1"

    result_turn = turns[2]
    assert result_turn.text == "a.txt\n"
    assert result_turn.tool_args["exit_code"] == 0

    usage_turn = turns[3]
    assert usage_turn.tool_args["input_tokens"] == 10

    # Prompt was written to stdin and closed, never passed as an argv prompt.
    assert process.stdin.written == b"do something"
    assert process.stdin.closed is True


@pytest.mark.asyncio
async def test_run_error_event_maps_to_error_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [_line({"type": "error", "message": "model unavailable"})]
    process = FakeProcess(stdout_lines=lines, returncode=0)
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    turns = [t async for t in harness.run("x", cwd="/tmp")]

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert turns[0].text == "model unavailable"


@pytest.mark.asyncio
async def test_run_nonzero_exit_yields_error_turn_not_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [_line({"type": "agent_message", "message": "partial work"})]
    process = FakeProcess(
        stdout_lines=lines, stderr_lines=[b"boom: sandbox denied\n"], returncode=1
    )
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    turns = [t async for t in harness.run("x", cwd="/tmp")]

    assert turns[0].kind == "text"
    assert turns[-1].kind == "error"
    assert "boom: sandbox denied" in turns[-1].text


@pytest.mark.asyncio
async def test_run_uses_resume_when_session_id_given(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(stdout_lines=[], returncode=0)
    calls = _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    _ = [t async for t in harness.run("continue please", cwd="/tmp", session_id="abc-123")]

    assert len(calls) == 1
    args = calls[0]
    assert args[1] == "exec"
    assert args[2] == "resume"
    assert args[3] == "abc-123"


@pytest.mark.asyncio
async def test_run_malformed_json_line_is_dropped_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [b"not json at all\n", _line({"type": "agent_message", "message": "ok"})]
    process = FakeProcess(stdout_lines=lines, returncode=0)
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    turns = [t async for t in harness.run("x", cwd="/tmp")]

    assert len(turns) == 1
    assert turns[0].text == "ok"


# --- aclose() --------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_mid_stream_terminates_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stream that never ends on its own, so the generator is still
    # mid-iteration when aclose() is called.
    class _NeverEndingStream:
        def __aiter__(self) -> _NeverEndingStream:
            return self

        async def __anext__(self) -> bytes:
            return _line({"type": "agent_message", "message": "still going"})

    process = FakeProcess(returncode=0)
    process.stdout = _NeverEndingStream()
    _patch_subprocess(monkeypatch, process)
    harness = CodexHarness()

    agen = harness.run("x", cwd="/tmp")
    first_turn = await agen.__anext__()
    assert first_turn.kind == "text"

    await harness.aclose()
    assert process.terminated is True

    # Calling it again must not raise.
    await harness.aclose()

    await agen.aclose()


@pytest.mark.asyncio
async def test_aclose_before_any_run_is_a_noop() -> None:
    harness = CodexHarness()
    await harness.aclose()
    await harness.aclose()


@pytest.mark.asyncio
async def test_discover_never_raises_on_broken_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    # CONTRACT.md rule 3: discover() must not raise for a missing, broken, or
    # unauthenticated harness — not just for the FileNotFoundError case.
    async def boom(*args: Any, **kwargs: Any) -> FakeProcess:
        raise PermissionError("permission denied")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
    harness = CodexHarness()

    spec = await harness.discover()

    assert spec.available is False
    assert "permission denied" in (spec.detail or "")
