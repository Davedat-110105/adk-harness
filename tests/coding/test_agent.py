"""HarnessAgent: what a harness's output looks like once it is an ADK agent.

These run a real ADK `InMemoryRunner` against a fake harness. Faking the harness
rather than the runner is deliberate — the part worth testing is the translation
into ADK's event model, and testing that against a fake ADK would test nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from adk_harness.agent import HarnessAgent
from adk_harness.coding.protocol import HarnessSpec, HarnessTurn


class FakeHarness:
    """A harness that replays a scripted sequence of turns."""

    def __init__(
        self,
        turns: tuple[HarnessTurn, ...] = (),
        *,
        available: bool = True,
        detail: str | None = None,
    ) -> None:
        self.spec = HarnessSpec(
            id="fake", version="0.0.1", available=available, detail=detail
        )
        self._turns = turns
        self.prompts: list[str] = []
        self.cwds: list[str] = []
        self.closed = 0
        self.stream_closed = 0

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        self.prompts.append(prompt)
        self.cwds.append(cwd)
        try:
            for turn in self._turns:
                yield turn
        finally:
            self.stream_closed += 1

    async def aclose(self) -> None:
        self.closed += 1


async def _texts(agent: HarnessAgent, prompt: str) -> list[str]:
    """Run the agent through a real runner and collect what it said."""
    runner = InMemoryRunner(agent=agent, app_name="test")
    session = await runner.session_service.create_session(
        app_name="test", user_id="u"
    )
    out: list[str] = []
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.content and event.content.parts:
            out.extend(p.text for p in event.content.parts if p.text)
    return out


@pytest.mark.asyncio
async def test_the_prompt_and_cwd_reach_the_harness() -> None:
    harness = FakeHarness((HarnessTurn(kind="text", text="done"),))
    agent = HarnessAgent(name="fake_agent", harness=harness, cwd="/work/repo")

    assert await _texts(agent, "fix the flaky test") == ["done"]
    assert harness.prompts == ["fix the flaky test"]
    assert harness.cwds == ["/work/repo"]


@pytest.mark.asyncio
async def test_every_turn_kind_becomes_an_event() -> None:
    harness = FakeHarness(
        (
            HarnessTurn(kind="text", text="planning"),
            HarnessTurn(kind="tool_call", tool_name="Bash", tool_args={"cmd": "ls"}),
            HarnessTurn(kind="tool_result", tool_name="Bash", text="a.py"),
            HarnessTurn(kind="usage", text="1200 tokens"),
            HarnessTurn(kind="error", text="exit 1"),
        )
    )
    agent = HarnessAgent(name="fake_agent", harness=harness, cwd="/work/repo")

    texts = await _texts(agent, "go")

    assert texts[0] == "planning"
    assert texts[1] == '[Bash] {"cmd": "ls"}'
    assert texts[2] == "[Bash result] a.py"
    assert texts[3] == "[usage] 1200 tokens"
    assert texts[4] == "[error] exit 1"


@pytest.mark.asyncio
async def test_inner_tool_calls_are_narrated_not_re_executed() -> None:
    """An inner tool call must not become an ADK FunctionCall.

    The harness already ran it in its own process. Emitting a function call
    would misattribute the action and invite the runtime to run it twice.
    """
    harness = FakeHarness(
        (HarnessTurn(kind="tool_call", tool_name="Bash", tool_args={"cmd": "rm -rf /"}),)
    )
    agent = HarnessAgent(name="fake_agent", harness=harness, cwd="/work/repo")

    runner = InMemoryRunner(agent=agent, app_name="test")
    session = await runner.session_service.create_session(app_name="test", user_id="u")
    calls = []
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="go")]),
    ):
        calls.extend(event.get_function_calls() or [])

    assert calls == []


@pytest.mark.asyncio
async def test_an_absent_harness_explains_itself_instead_of_raising() -> None:
    harness = FakeHarness(available=False, detail="codex not on PATH")
    agent = HarnessAgent(name="fake_agent", harness=harness, cwd="/work/repo")

    texts = await _texts(agent, "go")

    assert len(texts) == 1
    assert "not available" in texts[0]
    assert "codex not on PATH" in texts[0]
    assert harness.prompts == []


@pytest.mark.asyncio
async def test_an_absent_harness_can_be_made_fatal() -> None:
    harness = FakeHarness(available=False, detail="codex not on PATH")
    agent = HarnessAgent(
        name="fake_agent", harness=harness, cwd="/work/repo", skip_unavailable=False
    )

    with pytest.raises(RuntimeError, match="not available"):
        await _texts(agent, "go")


@pytest.mark.asyncio
async def test_agent_does_not_close_shared_harness_when_the_stream_fails() -> None:
    class Exploding(FakeHarness):
        async def run(self, prompt, *, cwd, session_id=None):
            yield HarnessTurn(kind="text", text="starting")
            raise RuntimeError("subprocess died")

    harness = Exploding()
    agent = HarnessAgent(name="fake_agent", harness=harness, cwd="/work/repo")

    with pytest.raises(RuntimeError, match="subprocess died"):
        await _texts(agent, "go")
    # Registry instances are shared; the adapter owns per-run cleanup and a
    # global aclose() remains an explicit shutdown operation.
    assert harness.closed == 0


@pytest.mark.asyncio
async def test_wrappers_close_only_their_own_streams() -> None:
    harness = FakeHarness((HarnessTurn(kind="text", text="done"),))
    first = HarnessAgent(name="first", harness=harness, cwd="/work/repo")
    second = HarnessAgent(name="second", harness=harness, cwd="/work/repo")

    await _texts(first, "one")
    await _texts(second, "two")

    assert harness.stream_closed == 2
    assert harness.closed == 0


@pytest.mark.asyncio
async def test_closing_agent_stream_closes_adapter_stream() -> None:
    harness = FakeHarness((HarnessTurn(kind="text", text="first"),))
    agent = HarnessAgent(name="agent", harness=harness, cwd="/work/repo")
    ctx = SimpleNamespace(
        invocation_id="invocation",
        branch=None,
        user_content=types.Content(role="user", parts=[types.Part(text="go")]),
    )

    stream = agent._run_async_impl(ctx)
    await stream.__anext__()
    await stream.aclose()

    assert harness.stream_closed == 1
    assert harness.closed == 0
