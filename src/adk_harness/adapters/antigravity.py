"""Google Antigravity adapter: drive `google-antigravity`'s `Agent.chat()`.

Verified against the machine, not memory:

- `google-antigravity==0.1.14`, installed into this repo's `.venv` with
  `.venv/Scripts/python -m pip install google-antigravity`. The wheel is
  `google_antigravity-0.1.14-py3-none-win_amd64.whl`; every platform wheel
  bundles a compiled Go `localharness` binary, and the sdist-less
  distribution means "the package imports" and "the runtime exists" are two
  different questions (see `discover()`).
- Class names, the `chat()` entry point, `LocalAgentConfig`'s fields, and the
  chunk types all come from reading the installed source under
  `.venv/Lib/site-packages/google/antigravity/` (`__init__.py`, `agent.py`,
  `types.py`, `models.py`, `conversation/conversation.py`,
  `connections/connection.py`, `connections/local/local_connection_config.py`,
  `connections/local/local_connection.py`), not from recollection.
- No live `agent.chat()` was run while writing this: that spends real Gemini
  quota. Everything below was read from source or exercised against the
  config objects directly, which do not call the model.

Why `chat()` and the unified chunk stream
------------------------------------------
`ChatResponse` exposes four cursors over one shared buffer: `__aiter__`
(text deltas as bare strings), `.thoughts`, `.tool_calls`, and `.chunks`.
The first three are filtered views of the fourth, so only `.chunks` preserves
the **order** in which the agent actually did things — a tool call that
happened between two sentences is otherwise unrecoverable. `run()` therefore
iterates `.chunks` and does its own dispatch, which is also the only cursor
that surfaces `ToolResult` at all.

Chunk-to-kind mapping
----------------------
| chunk type (`google.antigravity.types`) | `HarnessTurn.kind` |
|---|---|
| `Text` (response delta) | `text` |
| `Thought` (reasoning delta) | `text` |
| `ToolCall` | `tool_call`, `tool_name` from `name`, `tool_args` from `args` |
| `ToolResult` | `tool_result`, `text` from `error` or `result` |
| end of turn: `response.usage_metadata` | `usage` |
| end of turn: a non-`UNSPECIFIED` `response.stop_reason` | `error` |
| any other `StreamChunk` subtype added later | dropped |

`ToolCall.name` and `ToolResult.name` are typed `BuiltinTools | str`, and
`BuiltinTools` is a `(str, Enum)` mixin whose `str()` is `"BuiltinTools.RUN_COMMAND"`,
not `"run_command"` — so the mapping reads `.value` rather than stringifying.

A `ToolResult` carrying an `error` stays a `tool_result`: a tool that failed is
not the harness failing, and CONTRACT.md reserves `error` for the latter. The
error text lands in `text` and the whole object in `raw`. A `stop_reason` of
`MAX_TOOL_CALLS_EXCEEDED` or `QUOTA_EXHAUSTED`, on the other hand, *is* the
harness stopping short of the work it was asked to do, so that becomes an
`error` turn — otherwise a truncated run is indistinguishable from a finished
one.

Session continuity
-------------------
Genuine, with a condition worth stating plainly. `AgentConfig.conversation_id`
plus `session_continuation_mode=RESUME` resumes a prior session, and
`Agent.conversation_id` is the value to pass back — this adapter reports it in
the final `usage` turn's `tool_args` so a caller has somewhere to read it from.

The condition: sessions are persisted under `save_dir`, and
`LocalAgentConfig._get_or_create_save_dir()` mints a fresh `tempfile.mkdtemp()`
when `save_dir` is unset. A harness constructed without `save_dir` therefore
writes every session into a directory nothing will ever look at again, and
resume cannot work no matter what id is passed. So `session_resume` is
advertised in `HarnessSpec.capabilities` **only** when this adapter was
constructed with a `save_dir`. Claiming it unconditionally would be exactly the
"believes it has continuity when it does not" failure CONTRACT.md warns about.

`RESUME` is used rather than `CREATE_OR_RESUME` for the same reason: a resume
that silently starts a brand-new session when the old one is gone is a lie the
caller cannot detect. Failing loudly becomes one `error` turn.

Permissions
-----------
CONTRACT.md rule 1: an adapter never decides whether an action is permitted.
`LocalAgentConfig`'s own defaults are left exactly as they ship — all builtin
tools enabled, `policies=policy.confirm_run_command()`, and file tools fenced
to `workspaces`. This adapter does not pass `policies=[policy.allow_all()]` to
unlock autonomous shell access, and does not narrow the capability set either;
`CoactraGovernance` is the governance layer, and a caller who wants different
vendor-side defaults passes `capabilities` or `policies` explicitly.

Note that the SDK is fail-closed about this: `Agent.__aenter__` raises
`ValueError` when write-capable tools or MCP servers are enabled with no policy
and no `PreToolCallDecide` hook. The shipped default satisfies that check, so
leaving it alone is both the conservative choice and the working one.

Working directory
------------------
`cwd` maps to `workspaces=[cwd]`, which is the SDK's file-access boundary —
`LocalAgentConfig` defaults it to `os.getcwd()`, and the policy evaluator
restricts file tools to it. It is the closest thing the SDK has to a working
directory, and it is the same value `governance.py` keys the policy resource
on, so the gate and the harness are talking about the same place.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import json
import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from adk_harness.protocol import HarnessSpec, HarnessTurn

__all__ = ["AntigravityHarness"]

# The SDK reads this itself (`_HARNESS_PATH_ENV_VAR` in
# `connections/local/local_connection.py`) before falling back to the bundled
# wheel resource and then to PATH. `discover()` checks the same three places in
# the same order, so it cannot report "no runtime" for a machine the SDK would
# in fact have run on.
_HARNESS_PATH_ENV_VAR = "ANTIGRAVITY_HARNESS_PATH"


def _tool_name(name: Any) -> str:
    """Render `BuiltinTools | str` as the plain tool name.

    `BuiltinTools` is a `(str, Enum)` mixin, so `str()` yields
    `"BuiltinTools.RUN_COMMAND"`. `.value` is the name the vendor uses on the
    wire and the one a policy would be written against.
    """
    value = getattr(name, "value", name)
    return value if isinstance(value, str) else str(name)


def _result_text(result: Any) -> str | None:
    """Best plain-text rendering of a `ToolResult.result` for `text`.

    The full object survives in `raw` regardless; this only exists for callers
    that read `text` and nothing else.
    """
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
    """Run Google Antigravity through its SDK, one `Agent` session per `run()` call.

    Each `run()` opens its own `Agent` context and closes it when the stream
    ends or the caller walks away, which keeps cleanup to a single unwinding
    path — the same reasoning that made the Claude Code adapter prefer a
    one-shot `query()` over a long-lived client.
    """

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
        # One dict per in-flight run, holding the async generator `run()`
        # returned and the vendor `ChatResponse` once it exists, so `aclose()`
        # can cancel the turn and unwind the `Agent` context of a run the
        # caller abandoned mid-stream. A run removes its own holder when it
        # finishes; `aclose()` drains whatever is left.
        self._active_runs: list[dict[str, Any]] = []

    def _config_kwargs(self) -> dict[str, Any]:
        """The constructor's vendor-facing fields, minus the unset ones.

        `LocalAgentConfig.__init__` drops `None` values itself, but building the
        dict here keeps `discover()` and `run()` provably configured the same
        way — a credential check that validated a different config than the one
        that runs is worse than no check.
        """
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

            # Credentials are checked by building the config the way `run()`
            # will and asking the SDK's own endpoint validator about it, rather
            # than reimplementing which env var means what. `GEMINI_API_KEY`,
            # the `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_GENAI_USE_ENTERPRISE`
            # switches, and `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` are
            # all read by the vendor code this calls, so the answer here cannot
            # drift from what an actual run would do. None of it opens a
            # connection or spends quota.
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
            # CONTRACT.md rule 3: discover() must not raise. Config construction
            # runs pydantic validators, and a future one could reject something
            # this adapter passes; that should read as "unavailable, here is
            # why" rather than take down a fleet that has other harnesses.
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
            # `conversation_id` is validated for length and character set, and
            # `workspaces` for shape. A caller's bad session id is an error
            # turn, not an exception thrown through their `async for`.
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
                # Connection loss, model errors, tool-execution failures: the
                # SDK raises several unrelated exception types with no shared
                # base (`AntigravityConnectionError`, `AntigravityExecutionError`,
                # `ToolExecutionError`, ...), so they are caught as a group and
                # reported. `AntigravityCancelledError` subclasses
                # `asyncio.CancelledError`, which is a `BaseException` — it
                # deliberately passes straight through, because a cancelled
                # caller does not want a turn, it wants to stop.
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
        """Map one chunk off `ChatResponse.chunks`, or drop it.

        The vendor types arrive as arguments rather than module-level imports
        because CONTRACT.md rule 2 forbids importing them at import time, and
        `isinstance` needs the real classes.
        """
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
        """Usage and short-stop turns, read once the chunk stream is exhausted.

        Both `usage_metadata` and `stop_reason` are only meaningful after the
        turn completes, and both reach through `ChatResponse` into the
        conversation — so each is read defensively. A missing accounting field
        must not turn a successful run into a failed one.
        """
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
            # The conversation id rides along here because it is the value a
            # caller needs to pass back as `session_id`, and there is no other
            # turn on which it belongs.
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
                    # Best effort: a turn that already finished, or a
                    # connection already gone, must not stop us from unwinding
                    # the rest of the runs below.
                    pass
            stream = holder.get("stream")
            if stream is not None:
                # Closing the generator is what runs its `finally` and exits
                # the `Agent` context, which is what actually releases the
                # localharness subprocess.
                await stream.aclose()
