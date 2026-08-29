"""Lifecycle integration for Google's official Antigravity SDK.

The SDK owns authentication, policy-aware tools, and the localharness runtime.
This module supplies only the workspace boundary and ordered event stream.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.resources
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

__all__ = ["AntigravityIntegration"]


def _runtime() -> str | None:
    override = os.environ.get("ANTIGRAVITY_HARNESS_PATH")
    if override:
        return override if os.path.exists(override) else None
    suffix = "bin/localharness.exe" if os.name == "nt" else "bin/localharness"
    try:
        path = str(importlib.resources.files("google.antigravity").joinpath(suffix))
    except (ImportError, AttributeError, KeyError, TypeError):
        path = ""
    return path if path and os.path.exists(path) else shutil.which("localharness")


@dataclass
class _RunHandle:
    """Own all resources associated with one generator invocation."""

    agent: Any
    task: asyncio.Task[Any] | None
    response: Any | None = None
    entered: bool = False
    stream_done: bool = False
    response_cancelled: bool = False
    cleanup_failed: bool = False
    cancelled_during_cleanup: bool = False
    agent_exited: bool = False
    closing: bool = False
    shutdown_cancelled: bool = False
    cancel_task: asyncio.Task[Any] | None = None
    exit_task: asyncio.Task[Any] | None = None


class _CleanupError(RuntimeError):
    """Safe marker for an SDK context cleanup failure."""


class AntigravityIntegration:
    """Run Antigravity sessions while preserving the SDK lifecycle semantics."""

    def __init__(self, **config: Any) -> None:
        self.config = {key: value for key, value in config.items() if value is not None}
        self._active: dict[int, _RunHandle] = {}
        self._closed = False
        self._close_operation: asyncio.Task[None] | None = None
        self._close_callers: set[asyncio.Task[Any]] = set()
        self._close_error: _CleanupError | None = None

    def _has_stable_save_dir(self) -> bool:
        value = self.config.get("save_dir")
        if value is None:
            return False
        try:
            path = os.fspath(value)
        except TypeError:
            return False
        return isinstance(path, str) and bool(path.strip())

    async def discover(self) -> dict[str, Any]:
        try:
            from google.antigravity import LocalAgentConfig
        except Exception:
            return {
                "available": False,
                "version": "unknown",
                "code": "sdk_unavailable",
                "detail": "google-antigravity SDK is unavailable",
            }

        version = "unknown"
        try:
            version = importlib.metadata.version("google-antigravity")
        except Exception:
            # The SDK can still be inspected when package metadata is absent.
            pass
        try:
            runtime = _runtime()
        except Exception:
            runtime = None
        if runtime is None:
            return {
                "available": False,
                "version": version,
                "code": "runtime_unavailable",
                "detail": "localharness runtime not found",
            }
        try:
            cfg = LocalAgentConfig(**self.config)
            for model in cfg.models or ():
                if model.endpoint is not None:
                    model.endpoint.validate_endpoint()
        except Exception:
            return {
                "available": False,
                "version": version,
                "code": "configuration_invalid",
                "detail": "Antigravity configuration is invalid",
            }
        result: dict[str, Any] = {
            "available": True,
            "version": version,
            "runtime": runtime,
        }
        if self._has_stable_save_dir():
            result["capabilities"] = ["session_resume"]
        return result

    async def run(  # noqa: PLR0915
        self, prompt: str, *, workspace: str, conversation_id: str | None = None
    ) -> AsyncIterator[Any]:
        if self._closed:
            yield {
                "kind": "error",
                "code": "integration_closed",
                "text": "Antigravity integration is closed",
            }
            return
        try:
            from google.antigravity import Agent, LocalAgentConfig
            from google.antigravity.types import SessionContinuationMode
        except Exception:
            yield {
                "kind": "error",
                "code": "sdk_unavailable",
                "text": "google-antigravity SDK is unavailable",
            }
            return

        kwargs = dict(self.config)
        # The per-call workspace is authoritative over caller configuration.
        kwargs["workspaces"] = [workspace]
        if conversation_id is not None:
            if not self._has_stable_save_dir():
                yield {
                    "kind": "error",
                    "code": "resume_requires_save_dir",
                    "text": "conversation resume requires a configured save_dir",
                }
                return
            kwargs.update(
                conversation_id=conversation_id,
                session_continuation_mode=SessionContinuationMode.RESUME,
            )
        try:
            config = LocalAgentConfig(**kwargs)
            agent = Agent(config)
        except Exception:
            yield {
                "kind": "error",
                "code": "configuration_invalid",
                "text": "Antigravity configuration is invalid",
            }
            return

        handle = _RunHandle(agent=agent, task=asyncio.current_task())
        self._active[id(handle)] = handle
        cancelled = False
        consumer_closed = False
        cleanup_error: _CleanupError | None = None
        try:
            try:
                await agent.__aenter__()
                handle.entered = True
                handle.response = await agent.chat(prompt)
                async for event in handle.response.chunks:
                    if handle.closing:
                        if handle.shutdown_cancelled:
                            raise asyncio.CancelledError()
                        return
                    yield event
                handle.stream_done = True
                if handle.shutdown_cancelled:
                    raise asyncio.CancelledError()
            except asyncio.CancelledError:
                cancelled = True
                raise
            except GeneratorExit:
                consumer_closed = True
                raise
            except Exception:
                yield {
                    "kind": "error",
                    "code": "execution_failed",
                    "text": "Antigravity execution failed",
                }
        finally:
            try:
                try:
                    if handle.response is not None and not handle.stream_done:
                        await self._cancel_response(handle)
                    if handle.entered:
                        if cancelled:
                            await self._exit_agent(
                                handle,
                                asyncio.CancelledError,
                                asyncio.CancelledError(),
                                None,
                            )
                        else:
                            await self._exit_agent(handle, None, None, None)
                    elif cancelled:
                        # Agent.__aenter__ catches Exception, not
                        # CancelledError. If cancellation interrupts entry,
                        # close its public lifecycle stack explicitly.
                        await self._exit_agent(
                            handle,
                            asyncio.CancelledError,
                            asyncio.CancelledError(),
                            None,
                        )
                    if handle.cleanup_failed:
                        raise _CleanupError("Antigravity cleanup failed") from None
                except _CleanupError as exc:
                    cleanup_error = exc
            finally:
                self._active.pop(id(handle), None)
            current_task = asyncio.current_task()
            unwind_cancelled = handle.cancelled_during_cleanup or (
                consumer_closed
                and current_task is not None
                and current_task.cancelling() > 0
            )
            if unwind_cancelled:
                raise asyncio.CancelledError()
            if consumer_closed and cleanup_error is not None:
                raise cleanup_error from None
        if handle.cancelled_during_cleanup:
            raise asyncio.CancelledError()
        if cleanup_error is not None and not cancelled:
            yield {
                "kind": "error",
                "code": "cleanup_failed",
                "text": "Antigravity cleanup failed",
            }

    async def aclose(self) -> None:
        """Cancel active SDK turns and make the integration permanently closed."""

        owner_task = asyncio.current_task()
        if owner_task is not None:
            self._close_callers.add(owner_task)
        if self._close_operation is None:
            self._closed = True
            self._close_operation = asyncio.create_task(self._close_active())
        operation = self._close_operation
        caller_cancelled: asyncio.CancelledError | None = None
        try:
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError as exc:
                    caller_cancelled = exc
                except _CleanupError as exc:
                    self._close_error = exc
                    break
            try:
                await operation
            except _CleanupError as exc:
                self._close_error = exc
        finally:
            if owner_task is not None:
                self._close_callers.discard(owner_task)
        if caller_cancelled is not None:
            raise caller_cancelled
        if self._close_error is not None:
            raise _CleanupError("Antigravity cleanup failed") from None

    async def _close_active(self) -> None:
        # Let concurrent close callers register before any run task is targeted.
        await asyncio.sleep(0)
        active = list(self._active.values())
        cleanup_error: _CleanupError | None = None
        close_callers: set[asyncio.Task[Any]] = set()
        for handle in active:
            handle.closing = True
            close_callers = {
                task for task in self._close_callers if task is not None
            }
            if (
                handle.task is not None
                and handle.task not in close_callers
                and not handle.task.done()
            ):
                handle.shutdown_cancelled = True
                handle.task.cancel()
            await self._cancel_response(handle)
            if not handle.entered and handle.task not in close_callers:
                await asyncio.sleep(0)
            try:
                await self._exit_agent(handle, None, None, None)
            except _CleanupError as exc:
                cleanup_error = cleanup_error or exc
            finally:
                self._active.pop(id(handle), None)
            close_callers = {
                task for task in self._close_callers if task is not None
            }
        tasks = [
            handle.task
            for handle in active
            if handle.task is not None
            and handle.task not in close_callers
            and not handle.task.done()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.sleep(0)
        for handle in active:
            if handle.cleanup_failed:
                cleanup_error = cleanup_error or _CleanupError(
                    "Antigravity cleanup failed"
                )
        if cleanup_error is not None:
            self._close_error = cleanup_error
            raise cleanup_error

    async def _cancel_response(self, handle: _RunHandle) -> None:
        response = handle.response
        if response is None or handle.stream_done:
            return
        if handle.cancel_task is None:
            handle.response_cancelled = True
            handle.cancel_task = asyncio.create_task(response.cancel())
        pending_cancel, cleanup_failed = await self._wait_cancel_task(handle.cancel_task)
        handle.cleanup_failed = handle.cleanup_failed or cleanup_failed
        if pending_cancel is not None:
            handle.cancelled_during_cleanup = True

    async def _wait_cancel_task(
        self, cancel_task: asyncio.Task[Any]
    ) -> tuple[asyncio.CancelledError | None, bool]:
        pending_cancel: asyncio.CancelledError | None = None
        cleanup_failed = False
        while not cancel_task.done():
            try:
                await asyncio.shield(cancel_task)
            except asyncio.CancelledError as exc:
                if cancel_task.done():
                    cleanup_failed = True
                else:
                    pending_cancel = exc
            except Exception:
                cleanup_failed = True
                break
        while pending_cancel is not None and not cancel_task.done():
            try:
                await asyncio.shield(cancel_task)
            except asyncio.CancelledError:
                if cancel_task.done():
                    cleanup_failed = True
            except Exception:
                cleanup_failed = True
                break
        if cancel_task.done():
            try:
                cancel_task.result()
            except asyncio.CancelledError:
                cleanup_failed = True
            except Exception:
                cleanup_failed = True
        return pending_cancel, cleanup_failed

    async def _exit_agent(
        self,
        handle: _RunHandle,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if handle.agent_exited:
            if handle.exit_task is None:
                return
            pending_cancel, cleanup_failed = await self._wait_exit_task(handle.exit_task)
        else:
            handle.agent_exited = True
            handle.exit_task = asyncio.create_task(
                handle.agent.__aexit__(exc_type, exc_value, traceback)
            )
            pending_cancel, cleanup_failed = await self._wait_exit_task(handle.exit_task)
        if cleanup_failed:
            # Do not expose SDK diagnostics, which may contain credentials or
            # request payloads. Keep cleanup failure distinct from completion.
            if pending_cancel is None:
                raise _CleanupError("Antigravity cleanup failed") from None
        if pending_cancel is not None:
            raise pending_cancel

    async def _wait_exit_task(
        self, exit_task: asyncio.Task[Any]
    ) -> tuple[asyncio.CancelledError | None, bool]:
        pending_cancel: asyncio.CancelledError | None = None
        cleanup_failed = False
        while not exit_task.done():
            try:
                await asyncio.shield(exit_task)
            except asyncio.CancelledError as exc:
                if exit_task.done():
                    cleanup_failed = True
                else:
                    pending_cancel = exc
            except Exception:
                cleanup_failed = True
                break
        while pending_cancel is not None and not exit_task.done():
            try:
                await asyncio.shield(exit_task)
            except asyncio.CancelledError:
                if exit_task.done():
                    cleanup_failed = True
            except Exception:
                cleanup_failed = True
                break
        if exit_task.done():
            try:
                exit_task.result()
            except asyncio.CancelledError:
                cleanup_failed = True
            except Exception:
                cleanup_failed = True
        return pending_cancel, cleanup_failed
