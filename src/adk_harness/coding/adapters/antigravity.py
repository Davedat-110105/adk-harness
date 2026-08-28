"""Google Antigravity adapter using one Agent.chat() session per run.

The unified .chunks stream preserves text/tool ordering and tool results.
Session resume requires save_dir; the conversation ID is returned with usage.
Vendor permission defaults remain intact, and cwd sets the workspace boundary.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import json
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

__all__ = ["AntigravityHarness"]

# Match the SDK runtime lookup: environment override, bundled wheel, then PATH.
_HARNESS_PATH_ENV_VAR = "ANTIGRAVITY_HARNESS_PATH"


def _tool_name(name: Any) -> str:
    """Use the enum value as the wire tool name, not its qualified string form."""
    value = getattr(name, "value", name)
    return value if isinstance(value, str) else str(name)


def _result_text(result: Any) -> str | None:
    """Render a tool result as text; the full payload remains in raw."""
    if result is None:
        return None
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _localharness_binary() -> str | None:
    """Locate the compiled runtime the SDK will shell out to, or None."""
    if path := os.environ.get(_HARNESS_PATH_ENV_VAR):
        return path if os.path.exists(path) else None
    suffix = "bin/localharness.exe" if os.name == "nt" else "bin/localharness"
    try:
        bundled = str(importlib.resources.files("google.antigravity").joinpath(suffix))
    except (ImportError, AttributeError, KeyError, TypeError):
        bundled = ""
    if bundled and os.path.exists(bundled):
        return bundled
    return shutil.which("localharness")


class AntigravityHarness:
    """Run one SDK Agent context per invocation and close it with the stream."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        vertex: bool | None = None,
        project: str | None = None,
        location: str | None = None,
        system_instructions: str | None = None,
        save_dir: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.vertex = vertex
        self.project = project
        self.location = location
        self.system_instructions = system_instructions
        self.save_dir = save_dir
        self.spec = HarnessSpec(id="antigravity", version="unknown", available=False)
        # Track per-run resources so shutdown can close abandoned streams.
        self._active_runs: list[dict[str, Any]] = []

    def _config_kwargs(self) -> dict[str, Any]:
        """Share the same non-None vendor settings between discovery and execution."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "api_key": self.api_key,
            "vertex": self.vertex,
            "project": self.project,
            "location": self.location,
            "system_instructions": self.system_instructions,
        }
        return {key: value for key, value in kwargs.items() if value is not None}

    async def discover(self) -> HarnessSpec:
        try:
            import google.antigravity  # noqa: F401
            from google.antigravity import LocalAgentConfig
        except ImportError as exc:
            self.spec = HarnessSpec(
                id="antigravity",
                version="unknown",
                available=False,
                detail=(
                    f"google-antigravity is not installed ({exc}); "
                    "install with `pip install google-antigravity`."
                ),
            )
            return self.spec

        try:
            try:
                version = importlib.metadata.version("google-antigravity")
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"

            binary = _localharness_binary()
            if binary is None:
                self.spec = HarnessSpec(
                    id="antigravity",
                    version=version,
                    available=False,
                    detail=(
                        "google-antigravity is importable but its compiled "
                        "`localharness` runtime was not found; the SDK ships it "
                        "inside the platform wheel, so install from PyPI rather "
                        "than from a source checkout, or point "
                        f"{_HARNESS_PATH_ENV_VAR} at one."
                    ),
                )
                return self.spec

            # Validate the same SDK config used by run(), without opening a connection.
            config = LocalAgentConfig(**self._config_kwargs())
            try:
                for target in config.models or ():
                    if target.endpoint is not None:
                        target.endpoint.validate_endpoint()
            except ValueError as exc:
                self.spec = HarnessSpec(
                    id="antigravity",
                    version=version,
                    available=False,
                    detail=f"google-antigravity is installed but unauthenticated: {exc}",
                )
                return self.spec

            capabilities: list[str] = list(HarnessTurn.KINDS)
            if self.save_dir is not None:
                # Only genuine with a stable save_dir — see the module docstring.
                capabilities.append("session_resume")
            self.spec = HarnessSpec(
                id="antigravity",
                version=version,
                capabilities=tuple(capabilities),
                available=True,
                detail=f"localharness runtime resolved at {binary}",
            )
            return self.spec
        except Exception as exc:
            # Discovery failures must become unavailable specs, not escape to the caller.
            self.spec = HarnessSpec(
                id="antigravity",
                version="unknown",
                available=False,
                detail=f"unexpected error during discovery: {type(exc).__name__}: {exc}",
            )
            return self.spec

    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        holder: dict[str, Any] = {}
        stream = self._run(prompt, cwd=cwd, session_id=session_id, holder=holder)
        holder["stream"] = stream
        self._active_runs.append(holder)
        return stream

    async def _run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
        holder: dict[str, Any],
    ) -> AsyncIterator[HarnessTurn]:
        try:
            from google.antigravity import Agent, LocalAgentConfig
            from google.antigravity.types import (
                SessionContinuationMode,
                Text,
                Thought,
                ToolCall,
                ToolResult,
            )
        except ImportError as exc:
            self._forget(holder)
            yield HarnessTurn(
                kind="error",
                text=f"google-antigravity is required: {exc}",
                raw=exc,
            )
            return

        kwargs = self._config_kwargs()
        kwargs["workspaces"] = [cwd]
        if self.save_dir is not None:
            kwargs["save_dir"] = self.save_dir
        if session_id is not None:
            kwargs["conversation_id"] = session_id
            kwargs["session_continuation_mode"] = SessionContinuationMode.RESUME

        try:
            config = LocalAgentConfig(**kwargs)
        except Exception as exc:
            # Invalid SDK config becomes an error turn rather than escaping the stream.
            self._forget(holder)
            yield HarnessTurn(kind="error", text=str(exc), raw=exc)
            return

        agent = Agent(config)
        try:
            try:
                await agent.__aenter__()
            except Exception as exc:
                yield HarnessTurn(kind="error", text=str(exc), raw=exc)
                return
            try:
                response = await agent.chat(prompt)
                holder["response"] = response
                async for chunk in response.chunks:
                    turn = self._chunk_to_turn(
                        chunk,
                        text_type=Text,
                        thought_type=Thought,
                        tool_call_type=ToolCall,
                        tool_result_type=ToolResult,
                    )
                    if turn is not None:
                        yield turn
                for turn in self._closing_turns(response, agent):
                    yield turn
            except Exception as exc:
                # Vendor failures become error turns; cancellation propagates.
                yield HarnessTurn(kind="error", text=str(exc), raw=exc)
            finally:
                await agent.__aexit__(None, None, None)
        finally:
            self._forget(holder)

    def _forget(self, holder: dict[str, Any]) -> None:
        if holder in self._active_runs:
            self._active_runs.remove(holder)

    def _chunk_to_turn(
        self,
        chunk: Any,
        *,
        text_type: type,
        thought_type: type,
        tool_call_type: type,
        tool_result_type: type,
    ) -> HarnessTurn | None:
        """Map a chunk using lazily imported vendor types, or drop unknown types."""
        if isinstance(chunk, (thought_type, text_type)):
            # Thought first: both are StreamChunk subclasses carrying `.text`,
            # and reasoning is `text` per CONTRACT.md either way.
            return HarnessTurn(kind="text", text=chunk.text, raw=chunk)
        if isinstance(chunk, tool_call_type):
            return HarnessTurn(
                kind="tool_call",
                tool_name=_tool_name(chunk.name),
                tool_args=dict(chunk.args or {}),
                raw=chunk,
            )
        if isinstance(chunk, tool_result_type):
            return HarnessTurn(
                kind="tool_result",
                tool_name=_tool_name(chunk.name),
                text=chunk.error if chunk.error else _result_text(chunk.result),
                raw=chunk,
            )
        # A StreamChunk subtype added in a later SDK release is dropped rather
        # than force-fitted onto a kind it does not match.
        return None

    def _closing_turns(self, response: Any, agent: Any) -> list[HarnessTurn]:
        """Read final usage and stop reasons defensively; missing accounting is not a run failure."""
        turns: list[HarnessTurn] = []
        try:
            usage = response.usage_metadata
        except Exception:
            usage = None
        if usage is not None:
            counts = {
                key: value
                for key, value in usage.model_dump(exclude_none=True).items()
                if value is not None
            }
            summary = ", ".join(f"{key}={value}" for key, value in counts.items())
            # Return the conversation ID for the next session_id.
            conversation_id = getattr(agent, "conversation_id", None)
            if conversation_id:
                counts["conversation_id"] = conversation_id
            turns.append(
                HarnessTurn(kind="usage", text=summary or None, tool_args=counts, raw=usage)
            )

        try:
            stop_reason = response.stop_reason
        except Exception:
            stop_reason = None
        reason = getattr(stop_reason, "value", stop_reason)
        if reason and reason != "UNSPECIFIED":
            turns.append(
                HarnessTurn(
                    kind="error",
                    text=f"the run stopped early: {reason}",
                    raw=stop_reason,
                )
            )
        return turns

    async def aclose(self) -> None:
        runs, self._active_runs = self._active_runs, []
        for holder in runs:
            response = holder.get("response")
            if response is not None:
                try:
                    await response.cancel()
                except Exception:
                    # A finished turn must not prevent cleanup of other runs.
                    pass
            stream = holder.get("stream")
            if stream is not None:
                # Closing the generator exits Agent and releases the subprocess.
                await stream.aclose()
