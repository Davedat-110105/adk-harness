from __future__ import annotations

import asyncio
import importlib.metadata
import sys
import traceback
from types import SimpleNamespace
from typing import Any

import pytest

from adk_harness.integrations import antigravity as integration_module
from adk_harness.integrations.antigravity import AntigravityIntegration


class FakeRuntime:
    def __init__(self) -> None:
        self.configs: list[dict[str, Any]] = []
        self.agents: list[Any] = []
        self.chat_started: dict[str, asyncio.Event] = {}
        self.chat_release: dict[str, asyncio.Event] = {}
        self.enter_started = asyncio.Event()
        self.enter_release = asyncio.Event()
        self.exit_started = asyncio.Event()
        self.exit_release = asyncio.Event()
        self.exit_release.set()
        self.exit_error: BaseException | None = None
        self.response_created = asyncio.Event()
        self.stream_auto_release = True
        self.stream_error: BaseException | None = None
        self.cancel_started = asyncio.Event()
        self.cancel_release = asyncio.Event()
        self.cancel_release.set()
        self.cancel_error: BaseException | None = None
        self.config_error: BaseException | None = None
        self.enter_error: BaseException | None = None

    def modules(self) -> tuple[SimpleNamespace, SimpleNamespace]:
        runtime = self

        class Config:
            def __init__(self, **kwargs: Any) -> None:
                if runtime.config_error is not None:
                    raise runtime.config_error
                runtime.configs.append(kwargs)
                self.kwargs = kwargs
                self.models: list[Any] = []

        class Response:
            def __init__(self, name: str) -> None:
                self.name = name
                self.cancel_calls = 0
                self.cancelled = asyncio.Event()
                self.stream_started = asyncio.Event()
                self.stream_release = asyncio.Event()
                if runtime.stream_auto_release:
                    self.stream_release.set()

            @property
            def chunks(self):
                async def stream():
                    self.stream_started.set()
                    if not self.stream_release.is_set():
                        await self.stream_release.wait()
                    yield self.name + "-first"
                    if runtime.stream_error is not None:
                        raise runtime.stream_error
                    yield self.name + "-second"

                return stream()

            async def cancel(self) -> None:
                self.cancel_calls += 1
                self.cancelled.set()
                runtime.cancel_started.set()
                if not runtime.cancel_release.is_set():
                    await runtime.cancel_release.wait()
                self.stream_release.set()
                if runtime.cancel_error is not None:
                    raise runtime.cancel_error

        class Agent:
            def __init__(self, config: Config) -> None:
                self.config = config
                self.response: Response | None = None
                self.entered = False
                self.exited = 0
                runtime.agents.append(self)

            async def __aenter__(self) -> Agent:
                runtime.enter_started.set()
                if runtime.enter_error is not None:
                    raise runtime.enter_error
                if not runtime.enter_release.is_set():
                    await runtime.enter_release.wait()
                self.entered = True
                return self

            async def __aexit__(self, *args: Any) -> bool:
                self.exited += 1
                runtime.exit_started.set()
                if runtime.exit_error is not None:
                    raise runtime.exit_error
                if not runtime.exit_release.is_set():
                    await runtime.exit_release.wait()
                return False

            async def chat(self, prompt: str) -> Response:
                started = runtime.chat_started.setdefault(prompt, asyncio.Event())
                release = runtime.chat_release.setdefault(prompt, asyncio.Event())
                started.set()
                await release.wait()
                self.response = Response(prompt)
                runtime.response_created.set()
                return self.response

        fake = SimpleNamespace(Agent=Agent, LocalAgentConfig=Config)
        types = SimpleNamespace(SessionContinuationMode=SimpleNamespace(RESUME="resume"))
        return fake, types


def install_fake(monkeypatch: pytest.MonkeyPatch, runtime: FakeRuntime) -> None:
    fake, types = runtime.modules()
    monkeypatch.setitem(sys.modules, "google.antigravity", fake)
    monkeypatch.setitem(sys.modules, "google.antigravity.types", types)


async def collect(stream: Any) -> list[Any]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_discover_reports_safe_codes_for_missing_sdk_and_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "google.antigravity", None)
    missing = await AntigravityIntegration().discover()
    assert missing == {
        "available": False,
        "version": "unknown",
        "code": "sdk_unavailable",
        "detail": "google-antigravity SDK is unavailable",
    }

    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.14")
    monkeypatch.setattr(integration_module, "_runtime", lambda: None)
    unavailable = await AntigravityIntegration().discover()
    assert unavailable["code"] == "runtime_unavailable"
    assert unavailable["detail"] == "localharness runtime not found"


@pytest.mark.asyncio
async def test_discover_hides_hostile_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    runtime.config_error = ValueError("api_key=SECRET bearer TOPSECRET C:\\private\\prompt")
    install_fake(monkeypatch, runtime)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.14")
    monkeypatch.setattr(integration_module, "_runtime", lambda: "localharness")

    result = await AntigravityIntegration().discover()

    assert result == {
        "available": False,
        "version": "0.1.14",
        "code": "configuration_invalid",
        "detail": "Antigravity configuration is invalid",
    }
    assert "SECRET" not in str(result)
    assert "TOPSECRET" not in str(result)


@pytest.mark.asyncio
async def test_discover_advertises_resume_only_for_stable_save_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.14")
    monkeypatch.setattr(integration_module, "_runtime", lambda: "localharness")

    without_save_dir = await AntigravityIntegration().discover()
    with_save_dir = await AntigravityIntegration(save_dir="C:/sessions").discover()

    assert "capabilities" not in without_save_dir
    assert with_save_dir["capabilities"] == ["session_resume"]


@pytest.mark.asyncio
@pytest.mark.parametrize("save_dir", ["", "   "])
async def test_discover_does_not_advertise_resume_for_blank_save_dir(
    monkeypatch: pytest.MonkeyPatch,
    save_dir: str,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.14")
    monkeypatch.setattr(integration_module, "_runtime", lambda: "localharness")

    result = await AntigravityIntegration(save_dir=save_dir).discover()

    assert "capabilities" not in result


@pytest.mark.asyncio
async def test_run_overrides_workspace_and_preserves_ordered_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    stream = AntigravityIntegration(model="x", workspaces=["caller-workspace"]).run(
        "hello", workspace="C:/repo"
    )

    events = await collect(stream)

    assert events == ["hello-first", "hello-second"]
    assert runtime.configs == [{"model": "x", "workspaces": ["C:/repo"]}]
    assert runtime.agents[0].exited == 1


@pytest.mark.asyncio
async def test_run_uses_genuine_resume_only_with_save_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()

    await collect(
        AntigravityIntegration(save_dir="C:/sessions").run(
            "hello", workspace="C:/repo", conversation_id="a" * 32
        )
    )

    assert runtime.configs == [
        {
            "save_dir": "C:/sessions",
            "workspaces": ["C:/repo"],
            "conversation_id": "a" * 32,
            "session_continuation_mode": "resume",
        }
    ]


@pytest.mark.asyncio
async def test_run_hides_hostile_runtime_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    runtime.enter_error = RuntimeError("Authorization: Bearer RUNTIME_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()

    events = await collect(AntigravityIntegration().run("hello", workspace="C:/repo"))

    assert events == [
        {
            "kind": "error",
            "code": "execution_failed",
            "text": "Antigravity execution failed",
        }
    ]
    assert "RUNTIME_SECRET" not in str(events)


@pytest.mark.asyncio
async def test_normal_cleanup_failure_is_safe_non_success(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    runtime.exit_error = ValueError("SYNTHETIC_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()

    events = await collect(AntigravityIntegration().run("hello", workspace="C:/repo"))

    assert events[-1] == {
        "kind": "error",
        "code": "cleanup_failed",
        "text": "Antigravity cleanup failed",
    }
    assert "SYNTHETIC_SECRET" not in str(events)
    assert runtime.agents[0].exited == 1


@pytest.mark.asyncio
async def test_explicit_stream_close_reports_safe_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.exit_error = ValueError("SYNTHETIC_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    stream = integration.run("hello", workspace="C:/repo")
    await stream.__anext__()

    with pytest.raises(RuntimeError, match="Antigravity cleanup failed") as error:
        await stream.aclose()

    assert "SYNTHETIC_SECRET" not in str(error.value)
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_overlapping_chat_completions_keep_their_response_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    integration = AntigravityIntegration()
    runtime.chat_started["A"] = asyncio.Event()
    runtime.chat_started["B"] = asyncio.Event()
    stream_a = integration.run("A", workspace="C:/repo")
    stream_b = integration.run("B", workspace="C:/repo")

    task_a = asyncio.create_task(collect(stream_a))
    task_b = asyncio.create_task(collect(stream_b))
    await asyncio.wait_for(runtime.chat_started["A"].wait(), timeout=1)
    await asyncio.wait_for(runtime.chat_started["B"].wait(), timeout=1)
    runtime.chat_release["B"].set()
    await asyncio.wait_for(asyncio.shield(task_b), timeout=1)
    runtime.chat_release["A"].set()
    assert await asyncio.wait_for(task_a, timeout=1) == ["A-first", "A-second"]
    assert await asyncio.wait_for(task_b, timeout=1) == ["B-first", "B-second"]


@pytest.mark.asyncio
async def test_aclose_cancels_runs_while_both_chat_calls_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    integration = AntigravityIntegration()
    runtime.chat_started["A"] = asyncio.Event()
    runtime.chat_started["B"] = asyncio.Event()
    tasks = [
        asyncio.create_task(collect(integration.run(prompt, workspace="C:/repo")))
        for prompt in ("A", "B")
    ]
    await asyncio.wait_for(runtime.chat_started["A"].wait(), timeout=1)
    await asyncio.wait_for(runtime.chat_started["B"].wait(), timeout=1)

    await asyncio.wait_for(integration.aclose(), timeout=1)
    gather_task = asyncio.gather(*tasks, return_exceptions=True)
    try:
        results = await asyncio.wait_for(asyncio.shield(gather_task), timeout=1)
    except TimeoutError:
        for task in tasks:
            if not task.done():
                task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert all(agent.exited == 1 for agent in runtime.agents)
    assert not integration._active
    await integration.aclose()


@pytest.mark.asyncio
async def test_aclose_cancels_response_while_stream_awaits(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[0].response is not None
    await asyncio.wait_for(runtime.agents[0].response.stream_started.wait(), timeout=1)

    await integration.aclose()
    result = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(result[0], asyncio.CancelledError)
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_same_consumer_aclose_unwinds_suspended_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    stream = integration.run("hello", workspace="C:/repo")
    assert await stream.__anext__() == "hello-first"

    await integration.aclose()

    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active
    await stream.aclose()
    assert runtime.agents[0].exited == 1
    assert runtime.agents[0].response.cancel_calls == 1


@pytest.mark.asyncio
async def test_aclose_caller_cancellation_is_propagated_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_started["hello"] = asyncio.Event()
    integration = AntigravityIntegration()
    run_task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    runtime.chat_release.setdefault("hello", asyncio.Event())
    await asyncio.wait_for(runtime.chat_started["hello"].wait(), timeout=1)
    runtime.exit_release.clear()
    close_task = asyncio.create_task(integration.aclose())
    await asyncio.wait_for(runtime.exit_started.wait(), timeout=1)
    close_task.cancel()
    runtime.exit_release.set()

    _done, pending = await asyncio.wait({close_task}, timeout=1)
    assert not pending
    with pytest.raises(asyncio.CancelledError):
        close_task.result()
    result = await asyncio.wait_for(
        asyncio.gather(run_task, return_exceptions=True), timeout=1
    )
    assert isinstance(result[0], asyncio.CancelledError)
    assert not integration._active
    await integration.aclose()


@pytest.mark.asyncio
async def test_stream_aclose_cancels_response_and_unwinds_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    stream = integration.run("hello", workspace="C:/repo")
    first = await stream.__anext__()

    await stream.aclose()

    assert first == "hello-first"
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cancel_error",
    [None, ValueError("SYNTHETIC_ONLY")],
    ids=["cleanup-success", "cleanup-failure"],
)
async def test_stream_aclose_caller_cancellation_wins_after_owned_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    cancel_error: BaseException | None,
) -> None:
    runtime = FakeRuntime()
    runtime.cancel_error = cancel_error
    runtime.cancel_release.clear()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    stream = integration.run("hello", workspace="C:/repo")
    await stream.__anext__()
    handle = next(iter(integration._active.values()))

    close_task = asyncio.create_task(stream.aclose())
    await asyncio.wait_for(runtime.cancel_started.wait(), timeout=1)
    close_task.cancel()
    runtime.cancel_release.set()

    _done, pending = await asyncio.wait({close_task}, timeout=1)
    if pending:
        runtime.cancel_release.set()
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=1)
        pytest.fail("stream.aclose() caller cancellation did not complete")

    try:
        close_task.result()
    except asyncio.CancelledError as error:
        formatted = "".join(traceback.format_exception(error))
    else:
        pytest.fail("stream.aclose() lost caller cancellation")

    assert cancel_error is None or "SYNTHETIC_ONLY" not in formatted
    assert handle.cancel_task is not None and handle.cancel_task.done()
    assert handle.exit_task is not None and handle.exit_task.done()
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_aclose_caller_cancellation_during_response_cancel_is_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.cancel_release.clear()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    run_task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[0].response is not None
    await asyncio.wait_for(runtime.agents[0].response.stream_started.wait(), timeout=1)

    close_task = asyncio.create_task(integration.aclose())
    await asyncio.wait_for(runtime.cancel_started.wait(), timeout=1)
    close_task.cancel()
    runtime.cancel_release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(close_task, timeout=1)
    result = await asyncio.wait_for(
        asyncio.gather(run_task, return_exceptions=True), timeout=1
    )
    assert isinstance(result[0], asyncio.CancelledError)
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active
    await integration.aclose()


@pytest.mark.asyncio
async def test_concurrent_consumer_closes_do_not_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    for prompt in ("A", "B"):
        runtime.chat_release[prompt] = asyncio.Event()
        runtime.chat_release[prompt].set()
    integration = AntigravityIntegration()
    ready = [asyncio.Event(), asyncio.Event()]
    both_ready = asyncio.Event()

    async def consume_then_close(prompt: str, index: int) -> None:
        stream = integration.run(prompt, workspace="C:/repo")
        assert await stream.__anext__() == prompt + "-first"
        ready[index].set()
        if all(event.is_set() for event in ready):
            both_ready.set()
        await both_ready.wait()
        await integration.aclose()

    tasks = [
        asyncio.create_task(consume_then_close("A", 0)),
        asyncio.create_task(consume_then_close("B", 1)),
    ]
    _done, pending = await asyncio.wait(tasks, timeout=1)
    if pending:
        if integration._close_operation is not None and not integration._close_operation.done():
            integration._close_operation.cancel()
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=1)
        pytest.fail("concurrent consumer closes deadlocked")
    results = [task.result() for task in tasks]

    assert results == [None, None]
    assert all(agent.response is not None for agent in runtime.agents)
    assert all(agent.response.cancel_calls == 1 for agent in runtime.agents)
    assert all(agent.exited == 1 for agent in runtime.agents)
    assert not integration._active
    assert all(task.done() for task in tasks)
    assert integration._close_operation is not None
    assert integration._close_operation.done()
    await integration.aclose()


@pytest.mark.asyncio
async def test_mixed_external_and_consumer_close_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    ready = asyncio.Event()
    proceed = asyncio.Event()

    async def consumer_close() -> None:
        stream = integration.run("hello", workspace="C:/repo")
        assert await stream.__anext__() == "hello-first"
        ready.set()
        await proceed.wait()
        await integration.aclose()

    consumer_task = asyncio.create_task(consumer_close())
    await asyncio.wait_for(ready.wait(), timeout=1)
    proceed.set()
    await asyncio.sleep(0)
    external_task = asyncio.create_task(integration.aclose())
    _done, pending = await asyncio.wait({consumer_task, external_task}, timeout=1)
    if pending:
        if integration._close_operation is not None and not integration._close_operation.done():
            integration._close_operation.cancel()
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=1)
        pytest.fail("mixed external and consumer close deadlocked")
    results = [task.result() for task in (consumer_task, external_task)]

    assert results == [None, None]
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active
    await integration.aclose()


@pytest.mark.asyncio
async def test_late_consumer_close_during_agent_exit_does_not_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    for prompt in ("A", "B"):
        runtime.chat_release[prompt] = asyncio.Event()
        runtime.chat_release[prompt].set()
    runtime.exit_release.clear()
    integration = AntigravityIntegration()
    ready = [asyncio.Event(), asyncio.Event()]
    go = [asyncio.Event(), asyncio.Event()]
    b_calling = asyncio.Event()

    async def consumer_close(prompt: str, index: int) -> None:
        stream = integration.run(prompt, workspace="C:/repo")
        assert await stream.__anext__() == prompt + "-first"
        ready[index].set()
        await go[index].wait()
        if index == 1:
            b_calling.set()
        await integration.aclose()

    task_a = asyncio.create_task(consumer_close("A", 0))
    task_b = asyncio.create_task(consumer_close("B", 1))
    await asyncio.wait_for(ready[0].wait(), timeout=1)
    await asyncio.wait_for(ready[1].wait(), timeout=1)
    go[0].set()
    await asyncio.wait_for(runtime.exit_started.wait(), timeout=1)
    go[1].set()
    await asyncio.wait_for(b_calling.wait(), timeout=1)
    runtime.exit_release.set()

    _done, pending = await asyncio.wait({task_a, task_b}, timeout=1)
    if pending:
        if integration._close_operation is not None and not integration._close_operation.done():
            integration._close_operation.cancel()
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=1)
        pytest.fail("late consumer close deadlocked during Agent exit")
    results = [task.result() for task in (task_a, task_b)]

    assert results == [None, None]
    assert all(agent.response is not None for agent in runtime.agents)
    assert all(agent.response.cancel_calls == 1 for agent in runtime.agents)
    assert all(agent.exited == 1 for agent in runtime.agents)
    assert not integration._active


@pytest.mark.asyncio
async def test_run_cancellation_wins_over_delayed_response_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.cancel_error = ValueError("RESPONSE_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.cancel_release.clear()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    run_task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[0].response is not None
    await asyncio.wait_for(runtime.agents[0].response.stream_started.wait(), timeout=1)
    run_task.cancel()
    await asyncio.wait_for(runtime.cancel_started.wait(), timeout=1)
    run_task.cancel()
    runtime.cancel_release.set()

    _done, pending = await asyncio.wait({run_task}, timeout=1)
    assert not pending
    with pytest.raises(asyncio.CancelledError):
        run_task.result()
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_response_cancel_failure_on_stream_close_is_safe_non_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.cancel_error = ValueError("RESPONSE_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    stream = integration.run("hello", workspace="C:/repo")
    await stream.__anext__()

    with pytest.raises(RuntimeError, match="Antigravity cleanup failed") as error:
        await stream.aclose()

    assert "RESPONSE_SECRET" not in str(error.value)
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_response_cancel_failure_on_integration_close_is_safe_non_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.cancel_error = ValueError("RESPONSE_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    run_task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[0].response is not None
    await asyncio.wait_for(runtime.agents[0].response.stream_started.wait(), timeout=1)

    with pytest.raises(RuntimeError, match="Antigravity cleanup failed") as error:
        await integration.aclose()

    assert "RESPONSE_SECRET" not in str(error.value)
    result = await asyncio.gather(run_task, return_exceptions=True)
    assert isinstance(result[0], asyncio.CancelledError)
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1
    assert not integration._active


@pytest.mark.asyncio
async def test_response_cancel_failure_after_stream_error_is_safe_non_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.stream_error = RuntimeError("STREAM_SECRET")
    runtime.cancel_error = ValueError("RESPONSE_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()

    events = await collect(AntigravityIntegration().run("hello", workspace="C:/repo"))

    assert events == [
        "hello-first",
        {
            "kind": "error",
            "code": "execution_failed",
            "text": "Antigravity execution failed",
        },
        {
            "kind": "error",
            "code": "cleanup_failed",
            "text": "Antigravity cleanup failed",
        },
    ]
    assert "STREAM_SECRET" not in str(events)
    assert "RESPONSE_SECRET" not in str(events)
    assert runtime.agents[0].response is not None
    assert runtime.agents[0].response.cancel_calls == 1
    assert runtime.agents[0].exited == 1


@pytest.mark.asyncio
async def test_sdk_exit_cancellation_is_safe_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.exit_error = asyncio.CancelledError("SDK_EXIT_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()

    events = await collect(AntigravityIntegration().run("hello", workspace="C:/repo"))

    assert events[-1] == {
        "kind": "error",
        "code": "cleanup_failed",
        "text": "Antigravity cleanup failed",
    }
    assert "SDK_EXIT_SECRET" not in str(events)
    assert runtime.agents[0].exited == 1


@pytest.mark.asyncio
async def test_caller_cancellation_wins_over_response_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    runtime.cancel_error = ValueError("RESPONSE_SECRET")
    install_fake(monkeypatch, runtime)
    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.cancel_release.clear()
    runtime.chat_release["hello"] = asyncio.Event()
    runtime.chat_release["hello"].set()
    integration = AntigravityIntegration()
    run_task = asyncio.create_task(collect(integration.run("hello", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[0].response is not None
    await asyncio.wait_for(runtime.agents[0].response.stream_started.wait(), timeout=1)

    close_task = asyncio.create_task(integration.aclose())
    await asyncio.wait_for(runtime.cancel_started.wait(), timeout=1)
    close_task.cancel()
    runtime.cancel_release.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(close_task, timeout=1)
    result = await asyncio.wait_for(asyncio.gather(run_task, return_exceptions=True), timeout=1)
    assert isinstance(result[0], asyncio.CancelledError)
    assert not integration._active
    with pytest.raises(RuntimeError, match="Antigravity cleanup failed"):
        await integration.aclose()


@pytest.mark.asyncio
async def test_cancellation_during_agent_enter_and_exit_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    integration = AntigravityIntegration()
    enter_task = asyncio.create_task(collect(integration.run("enter", workspace="C:/repo")))
    await asyncio.wait_for(runtime.enter_started.wait(), timeout=1)
    enter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await enter_task
    assert runtime.agents[0].exited == 1

    runtime.enter_release.set()
    runtime.stream_auto_release = False
    runtime.chat_release["exit"] = asyncio.Event()
    runtime.chat_release["exit"].set()
    runtime.exit_release.clear()
    exit_task = asyncio.create_task(collect(integration.run("exit", workspace="C:/repo")))
    await asyncio.wait_for(runtime.response_created.wait(), timeout=1)
    assert runtime.agents[1].response is not None
    await asyncio.wait_for(runtime.agents[1].response.stream_started.wait(), timeout=1)
    runtime.agents[1].response.stream_release.set()
    await asyncio.wait_for(runtime.exit_started.wait(), timeout=1)
    exit_task.cancel()
    runtime.exit_release.set()
    with pytest.raises(asyncio.CancelledError):
        await exit_task
    assert runtime.agents[1].exited == 1


@pytest.mark.asyncio
async def test_new_runs_after_close_return_stable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    install_fake(monkeypatch, runtime)
    integration = AntigravityIntegration()
    await integration.aclose()

    events = await collect(integration.run("hello", workspace="C:/repo"))

    assert events == [
        {
            "kind": "error",
            "code": "integration_closed",
            "text": "Antigravity integration is closed",
        }
    ]
