"""Tests for the Google Antigravity adapter.

These must pass whether or not `google-antigravity` is actually installed in
the environment running pytest — and it *is* installed in this repo's `.venv`,
so every test here overrides it deliberately rather than relying on absence.
"SDK missing" is simulated by stuffing `None` into
`sys.modules["google.antigravity"]`, which makes any import of it raise
`ImportError`. "SDK present" is simulated by installing one fake per test:
`_FakeAntigravitySdk`, a plain class (not `types.ModuleType`, so every
attribute is a normal, statically-typed instance attribute rather than dynamic
module-attribute noise pyright cannot follow) built from dataclasses that
mirror the real package's chunk and config shapes.

The adapter imports from two module paths — `google.antigravity` for `Agent`
and `LocalAgentConfig`, and `google.antigravity.types` for the chunk classes —
so both keys are patched, the second pointing at the same fake's `.types`
attribute. Every chunk instance a test constructs must come from the *same*
fake that gets installed into `sys.modules`, because `run()` re-imports the
classes inside the generator and `isinstance` against a class from a different
fake would silently fail.

The compiled `localharness` runtime is located through the adapter's own
`_localharness_binary`, monkeypatched here so these tests do not depend on what
happens to be inside the installed wheel or on PATH. Credentials are controlled
by monkeypatching the fake config's endpoint validation, which is the same seam
the real SDK validates through.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

from adk_harness.adapters.antigravity import AntigravityHarness
from adk_harness.protocol import HarnessTurn

_BINARY = "/opt/antigravity/bin/localharness"
# The real `AgentConfig` validator rejects anything shorter than 32 characters
# or outside `[a-zA-Z0-9-]`, so a realistic session id has to look like this.
_CONVERSATION_ID = "abcdefgh-1234-5678-9012-abcdefghijkl"


class _FakeAntigravitySdk:
    """A fake `google.antigravity` module-alike. Fill `.chunks` before running.

    Python's import system does not require `sys.modules["google.antigravity"]`
    to be a real `types.ModuleType` — `from google.antigravity import X` only
    needs the object already in `sys.modules` to have an `.X` attribute.

    The vendor knobs a test wants to move are plain attributes on the fake:
    `chunks` (what the turn streams), `raise_during_stream`, `usage`,
    `stop_reason`, `endpoint_error` (an unauthenticated config),
    `enter_error` (a session that refuses to start). `calls` records what the
    adapter passed in.
    """

    def __init__(self) -> None:
        self.chunks: list[Any] = []
        self.raise_during_stream: Exception | None = None
        self.usage: Any = None
        self.stop_reason: Any = None
        self.endpoint_error: str | None = None
        self.enter_error: Exception | None = None
        self.calls: dict[str, Any] = {}
        self.entered = 0
        self.exited = 0
        self.cancelled = 0

        fake = self

        @dataclass(frozen=True)
        class StreamChunk:
            step_index: int = 0

        @dataclass(frozen=True)
        class Text(StreamChunk):
            text: str = ""

        @dataclass(frozen=True)
        class Thought(StreamChunk):
            text: str = ""

        @dataclass(frozen=True)
        class Compaction(StreamChunk):
            """A chunk type the adapter has never heard of, and must drop."""

        @dataclass
        class ToolCall:
            name: Any = ""
            args: dict[str, Any] = field(default_factory=dict)
            id: str | None = None

        @dataclass
        class ToolResult:
            name: Any = ""
            id: str | None = None
            result: Any = None
            error: str | None = None

        class SessionContinuationMode:
            RESUME = "resume"
            CREATE_OR_RESUME = "create_or_resume"

        @dataclass
        class UsageMetadata:
            prompt_token_count: int | None = None
            candidates_token_count: int | None = None
            total_token_count: int | None = None

            def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
                data = {
                    "prompt_token_count": self.prompt_token_count,
                    "candidates_token_count": self.candidates_token_count,
                    "total_token_count": self.total_token_count,
                }
                if exclude_none:
                    return {k: v for k, v in data.items() if v is not None}
                return data

        class _Endpoint:
            def validate_endpoint(self) -> None:
                if fake.endpoint_error is not None:
                    raise ValueError(fake.endpoint_error)

        class _ModelTarget:
            def __init__(self) -> None:
                self.name = "gemini-3.7-flash"
                self.endpoint = _Endpoint()

        class LocalAgentConfig:
            """Mirrors the real config closely enough to be worth asserting on.

            In particular it reproduces the real `conversation_id` validator,
            because "a bad session id must become an error turn, not an
            exception" is one of the behaviours under test.
            """

            def __init__(self, **kwargs: Any) -> None:
                conversation_id = kwargs.get("conversation_id")
                if conversation_id is not None and len(conversation_id) < 32:
                    raise ValueError(
                        "conversation_id must be at least 32 characters long, "
                        f"got {len(conversation_id)}"
                    )
                self.kwargs = kwargs
                self.models = [_ModelTarget()]
                fake.calls["config"] = kwargs

        class ChatResponse:
            def __init__(self) -> None:
                self._done = False

            @property
            def chunks(self) -> Any:
                async def _gen() -> Any:
                    for chunk in fake.chunks:
                        yield chunk
                    if fake.raise_during_stream is not None:
                        raise fake.raise_during_stream
                    self._done = True

                return _gen()

            @property
            def usage_metadata(self) -> Any:
                return fake.usage

            @property
            def stop_reason(self) -> Any:
                return fake.stop_reason

            async def cancel(self) -> None:
                fake.cancelled += 1

        class Agent:
            def __init__(self, config: Any) -> None:
                self.config = config
                self.conversation_id = _CONVERSATION_ID

            async def __aenter__(self) -> Any:
                if fake.enter_error is not None:
                    raise fake.enter_error
                fake.entered += 1
                return self

            async def __aexit__(self, *exc: Any) -> bool:
                fake.exited += 1
                return False

            async def chat(self, prompt: Any) -> Any:
                fake.calls["prompt"] = prompt
                return ChatResponse()

        class _Types:
            """Stands in for `google.antigravity.types`."""

            def __init__(self) -> None:
                self.StreamChunk = StreamChunk
                self.Text = Text
                self.Thought = Thought
                self.Compaction = Compaction
                self.ToolCall = ToolCall
                self.ToolResult = ToolResult
                self.SessionContinuationMode = SessionContinuationMode
                self.UsageMetadata = UsageMetadata

        self.Agent = Agent
        self.LocalAgentConfig = LocalAgentConfig
        self.ChatResponse = ChatResponse
        self.types = _Types()
        # Convenience aliases so tests can build chunks off the fake directly.
        self.Text = Text
        self.Thought = Thought
        self.Compaction = Compaction
        self.ToolCall = ToolCall
        self.ToolResult = ToolResult
        self.UsageMetadata = UsageMetadata


def _install(monkeypatch: pytest.MonkeyPatch) -> _FakeAntigravitySdk:
    """Install a fake SDK under both module paths the adapter imports from."""
    fake = _FakeAntigravitySdk()
    monkeypatch.setitem(sys.modules, "google.antigravity", fake)
    monkeypatch.setitem(sys.modules, "google.antigravity.types", fake.types)
    monkeypatch.setattr(
        "adk_harness.adapters.antigravity._localharness_binary", lambda: _BINARY
    )
    return fake


class _Enumish:
    """Stands in for a `(str, Enum)` member, whose `str()` is not its value."""

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:  # pragma: no cover - only here to be wrong
        return f"BuiltinTools.{self.value.upper()}"


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_reports_unavailable_when_sdk_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "google.antigravity", None)

    harness = AntigravityHarness()
    spec = await harness.discover()

    assert spec.id == "antigravity"
    assert spec.available is False
    assert "google-antigravity" in (spec.detail or "")
    assert "pip install" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_reports_unavailable_when_runtime_binary_missing(monkeypatch) -> None:
    """The wheel ships a compiled binary; a source checkout does not."""
    _install(monkeypatch)
    monkeypatch.setattr(
        "adk_harness.adapters.antigravity._localharness_binary", lambda: None
    )

    spec = await AntigravityHarness(api_key="k").discover()

    assert spec.available is False
    assert "localharness" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_reports_unavailable_when_unauthenticated(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.endpoint_error = (
        "A Gemini API key is required. Set it via GEMINI_API_KEY environment variable"
    )

    spec = await AntigravityHarness().discover()

    assert spec.available is False
    assert "unauthenticated" in (spec.detail or "")
    assert "GEMINI_API_KEY" in (spec.detail or "")


@pytest.mark.asyncio
async def test_discover_reports_available_when_authenticated(monkeypatch) -> None:
    _install(monkeypatch)

    spec = await AntigravityHarness(api_key="secret").discover()

    assert spec.available is True
    assert spec.version  # whatever importlib.metadata reported
    assert set(HarnessTurn.KINDS).issubset(spec.capabilities)
    assert spec.detail and _BINARY in spec.detail


@pytest.mark.asyncio
async def test_discover_validates_the_same_config_run_would_use(monkeypatch) -> None:
    fake = _install(monkeypatch)

    await AntigravityHarness(
        model="gemini-3.7-flash", vertex=True, project="proj", location="global"
    ).discover()

    config = fake.calls["config"]
    assert config == {
        "model": "gemini-3.7-flash",
        "vertex": True,
        "project": "proj",
        "location": "global",
    }


@pytest.mark.asyncio
async def test_discover_claims_session_resume_only_with_a_save_dir(monkeypatch) -> None:
    """Resume is only real when sessions are written somewhere durable."""
    _install(monkeypatch)

    without = await AntigravityHarness(api_key="k").discover()
    assert "session_resume" not in without.capabilities

    _install(monkeypatch)
    with_dir = await AntigravityHarness(api_key="k", save_dir="/var/sessions").discover()
    assert "session_resume" in with_dir.capabilities


@pytest.mark.asyncio
async def test_discover_never_raises_on_unexpected_failure(monkeypatch) -> None:
    """CONTRACT.md rule 3: discover() must not raise, full stop."""
    fake = _install(monkeypatch)

    def boom(**kwargs: Any) -> Any:
        raise RuntimeError("simulated pydantic validator failure")

    fake.LocalAgentConfig = boom

    spec = await AntigravityHarness(api_key="k").discover()  # must not raise

    assert spec.available is False
    assert "simulated pydantic validator failure" in (spec.detail or "")


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


async def _drain(
    harness: AntigravityHarness, prompt: str = "do the thing", **kwargs: Any
) -> list[HarnessTurn]:
    return [turn async for turn in harness.run(prompt, cwd="/work/repo", **kwargs)]


@pytest.mark.asyncio
async def test_run_reports_error_turn_when_sdk_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "google.antigravity", None)

    turns = await _drain(AntigravityHarness())

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert "google-antigravity" in (turns[0].text or "")


@pytest.mark.asyncio
async def test_run_maps_text_and_thought_chunks_to_text_turns(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [
        fake.Thought(step_index=0, text="pondering"),
        fake.Text(step_index=1, text="hello"),
    ]

    turns = await _drain(AntigravityHarness())

    assert [(t.kind, t.text) for t in turns] == [
        ("text", "pondering"),
        ("text", "hello"),
    ]
    assert turns[0].raw is fake.chunks[0]


@pytest.mark.asyncio
async def test_run_preserves_the_order_tool_calls_interleave_with_prose(monkeypatch) -> None:
    """The reason `run()` iterates `.chunks` and not the filtered cursors."""
    fake = _install(monkeypatch)
    fake.chunks = [
        fake.Text(step_index=0, text="looking"),
        fake.ToolCall(name=_Enumish("view_file"), args={"path": "README.md"}, id="c1"),
        fake.ToolResult(name=_Enumish("view_file"), id="c1", result="# adk-harness"),
        fake.Text(step_index=1, text="found it"),
    ]

    turns = await _drain(AntigravityHarness())

    assert [t.kind for t in turns] == ["text", "tool_call", "tool_result", "text"]
    call, result = turns[1], turns[2]
    assert call.tool_name == "view_file"  # `.value`, not "BuiltinTools.VIEW_FILE"
    assert call.tool_args == {"path": "README.md"}
    assert result.tool_name == "view_file"
    assert result.text == "# adk-harness"
    assert result.raw is fake.chunks[2]


@pytest.mark.asyncio
async def test_run_keeps_a_failed_tool_result_a_tool_result(monkeypatch) -> None:
    """A tool that failed is not the harness failing."""
    fake = _install(monkeypatch)
    fake.chunks = [
        fake.ToolResult(name="run_command", id="c1", error="exit status 1: no such file")
    ]

    turns = await _drain(AntigravityHarness())

    assert len(turns) == 1
    assert turns[0].kind == "tool_result"
    assert turns[0].text == "exit status 1: no such file"


@pytest.mark.asyncio
async def test_run_renders_a_structured_tool_result_as_json_text(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.ToolResult(name="find_file", result={"matches": ["a.py"]})]

    turns = await _drain(AntigravityHarness())

    assert turns[0].text == '{"matches": ["a.py"]}'


@pytest.mark.asyncio
async def test_run_drops_chunk_types_it_does_not_recognize(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.Compaction(step_index=0), fake.Text(step_index=1, text="hi")]

    turns = await _drain(AntigravityHarness())

    assert [(t.kind, t.text) for t in turns] == [("text", "hi")]


@pytest.mark.asyncio
async def test_run_yields_a_usage_turn_carrying_the_conversation_id(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.Text(step_index=0, text="done")]
    fake.usage = fake.UsageMetadata(prompt_token_count=120, total_token_count=300)

    turns = await _drain(AntigravityHarness())

    assert [t.kind for t in turns] == ["text", "usage"]
    usage = turns[-1]
    assert usage.tool_args["prompt_token_count"] == 120
    assert usage.tool_args["total_token_count"] == 300
    assert "candidates_token_count" not in usage.tool_args  # exclude_none
    # The id a caller passes back as `session_id`; there is no other turn for it.
    assert usage.tool_args["conversation_id"] == _CONVERSATION_ID
    assert usage.text and "total_token_count=300" in usage.text


@pytest.mark.asyncio
async def test_run_reports_a_short_stop_as_an_error_turn(monkeypatch) -> None:
    """A truncated run must not be indistinguishable from a finished one."""
    fake = _install(monkeypatch)
    fake.chunks = [fake.Text(step_index=0, text="partial")]
    fake.stop_reason = _Enumish("MAX_TOOL_CALLS_EXCEEDED")

    turns = await _drain(AntigravityHarness())

    assert [t.kind for t in turns] == ["text", "error"]
    assert "MAX_TOOL_CALLS_EXCEEDED" in (turns[-1].text or "")


@pytest.mark.asyncio
async def test_run_treats_an_unspecified_stop_reason_as_success(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.Text(step_index=0, text="all done")]
    fake.stop_reason = _Enumish("UNSPECIFIED")

    turns = await _drain(AntigravityHarness())

    assert [t.kind for t in turns] == ["text"]


@pytest.mark.asyncio
async def test_run_surfaces_a_mid_stream_sdk_failure_as_an_error_turn(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.Text(step_index=0, text="starting")]
    fake.raise_during_stream = RuntimeError("connection to localharness lost")

    turns = await _drain(AntigravityHarness())

    assert [t.kind for t in turns] == ["text", "error"]
    assert "connection to localharness lost" in (turns[-1].text or "")
    assert fake.exited == 1  # the Agent context still unwound


@pytest.mark.asyncio
async def test_run_surfaces_a_refused_session_start_as_an_error_turn(monkeypatch) -> None:
    """The SDK is fail-closed: it raises when write tools have no policy."""
    fake = _install(monkeypatch)
    fake.enter_error = ValueError("Write tools or MCP servers are enabled without a policy")

    turns = await _drain(AntigravityHarness())

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert "without a policy" in (turns[0].text or "")


@pytest.mark.asyncio
async def test_run_passes_cwd_as_the_workspace_and_the_prompt_through(monkeypatch) -> None:
    fake = _install(monkeypatch)

    await _drain(
        AntigravityHarness(model="gemini-3.7-flash", api_key="k", save_dir="/var/sessions"),
        prompt="investigate the bug",
    )

    assert fake.calls["prompt"] == "investigate the bug"
    config = fake.calls["config"]
    assert config["workspaces"] == ["/work/repo"]
    assert config["model"] == "gemini-3.7-flash"
    assert config["api_key"] == "k"
    assert config["save_dir"] == "/var/sessions"
    assert "conversation_id" not in config
    assert "session_continuation_mode" not in config


@pytest.mark.asyncio
async def test_run_resumes_a_session_when_given_one(monkeypatch) -> None:
    fake = _install(monkeypatch)

    await _drain(AntigravityHarness(save_dir="/var/sessions"), session_id=_CONVERSATION_ID)

    config = fake.calls["config"]
    assert config["conversation_id"] == _CONVERSATION_ID
    # RESUME, not CREATE_OR_RESUME: a silent new session is a lie.
    assert config["session_continuation_mode"] == fake.types.SessionContinuationMode.RESUME


@pytest.mark.asyncio
async def test_run_turns_a_rejected_session_id_into_an_error_turn(monkeypatch) -> None:
    """The vendor validates conversation_id; that must not escape as an exception."""
    _install(monkeypatch)

    turns = await _drain(AntigravityHarness(save_dir="/var/sessions"), session_id="too-short")

    assert len(turns) == 1
    assert turns[0].kind == "error"
    assert "conversation_id" in (turns[0].text or "")


# ---------------------------------------------------------------------------
# aclose()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_is_a_no_op_when_nothing_is_running() -> None:
    harness = AntigravityHarness()
    await harness.aclose()
    await harness.aclose()  # idempotent


@pytest.mark.asyncio
async def test_a_finished_run_forgets_itself(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [fake.Text(step_index=0, text="hi")]

    harness = AntigravityHarness()
    await _drain(harness)

    assert harness._active_runs == []
    assert fake.exited == 1


@pytest.mark.asyncio
async def test_aclose_cancels_and_unwinds_a_run_left_mid_stream(monkeypatch) -> None:
    fake = _install(monkeypatch)
    fake.chunks = [
        fake.Text(step_index=0, text="first"),
        fake.Text(step_index=1, text="second"),
    ]

    harness = AntigravityHarness()
    # `run()`'s declared return type matches the frozen `Harness` protocol
    # (`AsyncIterator[HarnessTurn]`), which has no `.aclose()`; at runtime it is
    # the async generator it actually is.
    gen: Any = harness.run("hello", cwd="/work/repo")
    first = await gen.__anext__()
    assert first.text == "first"
    assert len(harness._active_runs) == 1

    await harness.aclose()

    assert fake.cancelled == 1  # the in-flight turn was cancelled
    assert fake.exited == 1  # the Agent context unwound, releasing the runtime
    assert harness._active_runs == []

    await harness.aclose()  # idempotent
