"""Tests for the Claude Code adapter.

These must pass whether or not `claude-agent-sdk` is actually installed in the
environment running pytest. "SDK missing" is simulated by stuffing `None` into
`sys.modules["claude_agent_sdk"]`, which makes any `import claude_agent_sdk`
raise `ImportError` (the standard trick for this — see the import system
docs). "SDK present" is simulated by installing one fake module per test, built
from dataclasses that mirror the real package's message and content-block
shapes (same field names, same `isinstance` targets), so `run()`'s
block-to-kind mapping is exercised without a real subprocess or network call.

Every message and block instance a test constructs must come from the *same*
fake module that gets installed into `sys.modules` — the adapter re-imports
`from claude_agent_sdk import AssistantMessage, ...` inside `run()`, so an
`isinstance` check against a class from a different module instance (even one
built by the same factory function) would silently fail. `_fake_claude_agent_sdk()`
therefore returns one module whose `messages` list a test fills in afterwards,
rather than taking the messages up front.

The `claude` CLI binary check is exercised via monkeypatching `shutil.which`,
so these tests don't depend on what happens to be on PATH.
"""

from __future__ import annotations

import sys
import types as module_types
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from adk_harness.adapters.claude_code import ClaudeCodeHarness
from adk_harness.protocol import HarnessTurn


def _fake_claude_agent_sdk() -> module_types.ModuleType:
    """A fake `claude_agent_sdk` module. Fill `mod.messages` before running.

    `query()` reads `mod.messages` (and raises `mod.raise_after`, if set) at
    call time, so a test can build message/block instances using this
    module's own classes and only then point `mod.messages` at them.
    """
    mod = module_types.ModuleType("claude_agent_sdk")
    mod.__version__ = "0.0.0-fake"
    mod.messages: list[Any] = []
    mod.raise_after: Exception | None = None
    mod.calls: dict[str, Any] = {}

    @dataclass
    class TextBlock:
        text: str

    @dataclass
    class ThinkingBlock:
        thinking: str
        signature: str = "sig"

    @dataclass
    class ToolUseBlock:
        id: str
        name: str
        input: dict[str, Any]

    @dataclass
    class ToolResultBlock:
        tool_use_id: str
        content: str | list[dict[str, Any]] | None = None
        is_error: bool | None = None

    @dataclass
    class ServerToolUseBlock:
        id: str
        name: str
        input: dict[str, Any]

    @dataclass
    class ServerToolResultBlock:
        tool_use_id: str
        content: Any = None

    @dataclass
    class AssistantMessage:
        content: list[Any]
        model: str = "fake-model"
        error: str | None = None

    @dataclass
    class UserMessage:
        content: Any = ""

    @dataclass
    class ResultMessage:
        subtype: str = "success"
        duration_ms: int = 100
        duration_api_ms: int = 90
        is_error: bool = False
        num_turns: int = 1
        session_id: str = "sess-1"
        total_cost_usd: float | None = 0.01
        result: str | None = None
        errors: list[str] | None = None

    class ClaudeSDKError(Exception):
        pass

    class ResultError(ClaudeSDKError):
        pass

    @dataclass
    class ClaudeAgentOptions:
        cwd: Any = None
        model: Any = None
        allowed_tools: list[str] = field(default_factory=list)
        permission_mode: Any = None
        system_prompt: Any = None
        resume: Any = None

    async def query(*, prompt: Any, options: Any = None) -> AsyncIterator[Any]:
        mod.calls["prompt"] = prompt
        mod.calls["options"] = options
        for message in mod.messages:
            yield message
        if mod.raise_after is not None:
            raise mod.raise_after

    mod.TextBlock = TextBlock
    mod.ThinkingBlock = ThinkingBlock
    mod.ToolUseBlock = ToolUseBlock
    mod.ToolResultBlock = ToolResultBlock
    mod.ServerToolUseBlock = ServerToolUseBlock
    mod.ServerToolResultBlock = ServerToolResultBlock
    mod.AssistantMessage = AssistantMessage
    mod.UserMessage = UserMessage
    mod.ResultMessage = ResultMessage
    mod.ClaudeSDKError = ClaudeSDKError
    mod.ResultError = ResultError
    mod.ClaudeAgentOptions = ClaudeAgentOptions
    mod.query = query
    return mod


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_reports_unavailable_when_sdk_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    harness = ClaudeCodeHarness()
    spec = await harness.discover()

    assert spec.id == "claude_code"
    assert spec.available is False
    assert "claude-agent-sdk" in (spec.detail or "")
    assert "pip install" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_reports_unavailable_when_cli_binary_missing(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    monkeypatch.setattr("shutil.which", lambda name: None)

    harness = ClaudeCodeHarness()
    spec = await harness.discover()

    assert spec.available is False
    assert "claude" in (spec.detail or "").lower()


@pytest.mark.asyncio
async def test_discover_reports_available_when_sdk_and_binary_present(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/local/bin/claude" if name == "claude" else None
    )

    harness = ClaudeCodeHarness()
    spec = await harness.discover()

    assert spec.available is True
    assert spec.version  # non-empty, whichever source it came from
    assert set(HarnessTurn.KINDS).issubset(spec.capabilities)
    assert spec.detail and "/usr/local/bin/claude" in spec.detail


@pytest.mark.asyncio
async def test_discover_never_raises_on_unexpected_lookup_failure(monkeypatch) -> None:
    """CONTRACT.md rule 3: discover() must not raise, full stop."""
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")

    def boom(_name: str) -> str:
        raise RuntimeError("simulated metadata backend failure")

    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", boom)

    harness = ClaudeCodeHarness()
    spec = await harness.discover()  # must not raise

    assert spec.available is False
    assert "simulated metadata backend failure" in (spec.detail or "")


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


async def _drain(harness: ClaudeCodeHarness, prompt: str = "do the thing", **kwargs: Any) -> list[HarnessTurn]:
    return [turn async for turn in harness.run(prompt, cwd="/work/repo", **kwargs)]


@pytest.mark.asyncio
async def test_run_maps_text_and_thinking_blocks_to_text_turns(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.messages = [
        fake.AssistantMessage(
            content=[
                fake.TextBlock(text="hello"),
                fake.ThinkingBlock(thinking="pondering"),
            ]
        ),
    ]

    turns = await _drain(ClaudeCodeHarness())

    assert [(t.kind, t.text) for t in turns] == [
        ("text", "hello"),
        ("text", "pondering"),
    ]
    assert turns[0].raw is fake.messages[0].content[0]


@pytest.mark.asyncio
async def test_run_maps_tool_use_and_backfills_tool_name_on_result(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    tool_use = fake.ToolUseBlock(id="call-1", name="Read", input={"path": "README.md"})
    tool_result = fake.ToolResultBlock(tool_use_id="call-1", content="file contents", is_error=False)
    fake.messages = [
        fake.AssistantMessage(content=[tool_use]),
        fake.UserMessage(content=[tool_result]),
    ]

    turns = await _drain(ClaudeCodeHarness())

    assert len(turns) == 2
    call, result = turns
    assert call.kind == "tool_call"
    assert call.tool_name == "Read"
    assert call.tool_args == {"path": "README.md"}
    assert call.raw is tool_use

    assert result.kind == "tool_result"
    assert result.tool_name == "Read"  # backfilled from the matching tool_use id
    assert result.text == "file contents"
    assert result.raw is tool_result


@pytest.mark.asyncio
async def test_run_maps_tool_result_list_content_to_joined_text(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    tool_result = fake.ToolResultBlock(
        tool_use_id="unknown-id",
        content=[{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}],
    )
    fake.messages = [fake.UserMessage(content=[tool_result])]

    turns = await _drain(ClaudeCodeHarness())

    assert len(turns) == 1
    assert turns[0].kind == "tool_result"
    assert turns[0].text == "line one\nline two"
    assert turns[0].tool_name is None  # no matching tool_use seen this run


@pytest.mark.asyncio
async def test_run_maps_server_tool_use_and_result(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    use = fake.ServerToolUseBlock(id="srv-1", name="web_search", input={"query": "adk"})
    result = fake.ServerToolResultBlock(tool_use_id="srv-1", content={"type": "web_search_result", "hits": []})
    fake.messages = [
        fake.AssistantMessage(content=[use]),
        fake.AssistantMessage(content=[result]),
    ]

    turns = await _drain(ClaudeCodeHarness())

    assert turns[0].kind == "tool_call"
    assert turns[0].tool_name == "web_search"
    assert turns[1].kind == "tool_result"
    assert turns[1].tool_name == "web_search"


@pytest.mark.asyncio
async def test_run_maps_assistant_error_field_to_error_turn(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.messages = [fake.AssistantMessage(content=[], error="rate_limit")]

    turns = await _drain(ClaudeCodeHarness())

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert "rate_limit" in turns[0].text


@pytest.mark.asyncio
async def test_run_maps_successful_result_to_usage_turn(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    result = fake.ResultMessage(is_error=False, num_turns=3, duration_ms=1500, total_cost_usd=0.0123)
    fake.messages = [result]

    turns = await _drain(ClaudeCodeHarness())

    assert len(turns) == 1
    assert turns[0].kind == "usage"
    assert turns[0].raw is result
    assert "3 turn" in turns[0].text
    assert "1500ms" in turns[0].text


@pytest.mark.asyncio
async def test_run_maps_error_result_to_error_then_usage_turns(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    result = fake.ResultMessage(is_error=True, result="Claude Code hit max turns", num_turns=10)
    fake.messages = [result]

    turns = await _drain(ClaudeCodeHarness())

    assert [t.kind for t in turns] == ["error", "usage"]
    assert turns[0].text == "Claude Code hit max turns"


@pytest.mark.asyncio
async def test_run_does_not_duplicate_error_when_sdk_reraises_after_error_result(monkeypatch) -> None:
    """query() yields the error ResultMessage and then raises — don't double-report."""
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.messages = [fake.ResultMessage(is_error=True, result="boom")]
    fake.raise_after = fake.ResultError("exit code 1")

    turns = await _drain(ClaudeCodeHarness())

    error_turns = [t for t in turns if t.kind == "error"]
    assert len(error_turns) == 1
    assert error_turns[0].text == "boom"


@pytest.mark.asyncio
async def test_run_surfaces_error_turn_when_sdk_raises_before_any_result(monkeypatch) -> None:
    """The CLI can fail before ever producing a proper result frame (e.g. spawn failure)."""
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.raise_after = fake.ClaudeSDKError("claude binary vanished")

    turns = await _drain(ClaudeCodeHarness())

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert "claude binary vanished" in turns[0].text


@pytest.mark.asyncio
async def test_run_drops_plain_string_user_message_echo(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.messages = [fake.UserMessage(content="do the thing")]  # plain string == prompt echo

    turns = await _drain(ClaudeCodeHarness())

    assert turns == []


@pytest.mark.asyncio
async def test_run_passes_prompt_cwd_and_session_id_through_to_query(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    harness = ClaudeCodeHarness(model="claude-opus-4-5", allowed_tools=["Read", "Bash"])
    turns = [
        turn
        async for turn in harness.run("investigate the bug", cwd="/work/repo", session_id="sess-42")
    ]

    assert turns == []
    assert fake.calls["prompt"] == "investigate the bug"
    options = fake.calls["options"]
    assert options.cwd == "/work/repo"
    assert options.model == "claude-opus-4-5"
    assert options.allowed_tools == ["Read", "Bash"]
    assert options.resume == "sess-42"


@pytest.mark.asyncio
async def test_run_leaves_resume_unset_when_no_session_id(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    harness = ClaudeCodeHarness()
    async for _ in harness.run("hello", cwd="/work/repo"):
        pass

    assert fake.calls["options"].resume is None


# ---------------------------------------------------------------------------
# aclose()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_is_a_no_op_when_nothing_is_running() -> None:
    harness = ClaudeCodeHarness()
    await harness.aclose()
    await harness.aclose()  # idempotent


@pytest.mark.asyncio
async def test_aclose_terminates_a_run_left_mid_stream(monkeypatch) -> None:
    fake = _fake_claude_agent_sdk()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    fake.messages = [
        fake.AssistantMessage(content=[fake.TextBlock(text="first")]),
        fake.AssistantMessage(content=[fake.TextBlock(text="second")]),
    ]

    harness = ClaudeCodeHarness()
    gen = harness.run("hello", cwd="/work/repo")
    first = await gen.__anext__()
    assert first.text == "first"

    # Stop consuming mid-stream and clean up, as a caller that gave up early would.
    await gen.aclose()
    assert harness._active_queries == []

    # Idempotent even after a run already cleaned itself up.
    await harness.aclose()
