"""Claude Code adapter: drive `claude-agent-sdk`'s one-shot `query()`.

Verified against the machine, not memory:

- `claude-agent-sdk==0.2.144`, installed into this repo's `.venv` with
  `.venv/bin/pip install claude-agent-sdk` (it was not present beforehand;
  `uv pip install --python .venv/bin/python claude-agent-sdk` was used since
  `.venv/bin/pip` itself is not installed in this venv).
- The `claude` CLI binary at `/Users/datta/.local/bin/claude`, version
  `2.1.241` (`claude --version`). The SDK's own bundled baseline is
  `2.1.239` (`claude_agent_sdk._cli_version.__cli_version__`) — close enough
  that nothing here depends on the gap, but recorded in case it matters later.
- Class names, the `query()` entry point, `ClaudeAgentOptions`, and the
  message/content-block dataclasses all come from reading the installed
  source under `.venv/lib/python3.12/site-packages/claude_agent_sdk/`
  (`types.py`, `query.py`, `client.py`, `_internal/client.py`,
  `_internal/message_parser.py`, `_internal/query.py`, `_errors.py`) via
  `Read` and `grep`, not from recollection.

Why `query()` and not `ClaudeSDKClient`
----------------------------------------
`run()` is one call in, one stream out — exactly the shape `query()` is built
for (see its docstring: "stateless", "fire-and-forget style"). `ClaudeSDKClient`
adds bidirectional, multi-turn session state this adapter has no use for; each
`run()` call gets its own subprocess via its own `query()` generator, which
also makes cleanup simple (closing that one generator is enough — see
`aclose()` below).

Two things about `query()`'s internals shaped `run()`'s control flow:

1. Reading `.venv/lib/python3.12/site-packages/claude_agent_sdk/_internal/client.py`
   shows `InternalClient.process_query` explicitly `await`s `inner.aclose()`
   in a `finally`, with a comment noting `async for` does **not** close its
   iterator when the loop body raises or is cancelled (PEP 533 was deferred).
   The same trap applies to us: `run()` holds the `query()` generator in a
   local variable and explicitly `aclose()`s it in a `finally`, rather than
   trusting a bare `async for` to clean up the subprocess.
2. Reading `_internal/query.py` shows that after the CLI emits a `result`
   frame with `is_error: true` and then exits non-zero, `query()` re-raises
   that as `ResultError` *after* already yielding the `ResultMessage` — i.e.
   an error run surfaces twice: once as data, once as an exception. Since
   this adapter already turns an `is_error` `ResultMessage` into a
   `HarnessTurn(kind="error", ...)`, the follow-up `ResultError`/`ProcessError`
   would just be a duplicate exit-code footnote left to blow up the caller's
   `async for` for no new information. `run()` catches `ClaudeSDKError` and
   only turns it into a *second* error turn when no error turn was already
   emitted for this run (i.e. the CLI died before ever producing a proper
   result — a genuinely new fact worth surfacing).

Block-to-kind mapping
----------------------
Both `AssistantMessage.content` and `UserMessage.content` can carry any
`ContentBlock` subtype on the wire (confirmed by reading
`_internal/message_parser.py`: both the `"user"` and `"assistant"` cases parse
the same block variants defensively). `run()` therefore maps blocks with one
shared helper regardless of which message they arrived on:

- `TextBlock`, `ThinkingBlock` -> `kind="text"` (CONTRACT.md: "assistant
  prose, reasoning summaries, plans").
- `ToolUseBlock`, `ServerToolUseBlock` -> `kind="tool_call"`, and the block's
  `id` is remembered so a later `ToolResultBlock` referencing it can carry
  `tool_name` too (a bare `tool_use_id` on its own does not name the tool).
- `ToolResultBlock`, `ServerToolResultBlock` -> `kind="tool_result"`.
- `AssistantMessage.error` (a per-turn generation failure distinct from
  `ResultMessage.is_error`) -> `kind="error"`.
- `ResultMessage` -> `kind="usage"` always (duration/cost/turn count), plus a
  `kind="error"` turn first when `is_error` is set.
- `SystemMessage` and all of its subclasses (`Task*Message`,
  `HookEventMessage`, ...), plain-string `UserMessage` echoes of the prompt,
  and anything else not listed above are dropped — CONTRACT.md is explicit
  that dropping is not lossy, since `raw` stays available on turns that are
  yielded.

Session continuity
-------------------
`ClaudeAgentOptions.resume` (read from `types.py`) resumes a prior session by
id, which is exactly what `Harness.run`'s `session_id` parameter is for. It is
passed straight through; when `session_id` is `None` this equals
`ClaudeAgentOptions`'s own default (start fresh).

Permissions
-----------
CONTRACT.md rule 1: an adapter never decides whether an action is permitted.
`permission_mode` therefore defaults to `None` here too, which is
`ClaudeAgentOptions`'s own default ("default" — the CLI's standard prompting
behavior for dangerous operations). This adapter does not upgrade that to
`"bypassPermissions"` or `"acceptEdits"` on its own; a caller that wants a
different mode passes it explicitly to `ClaudeCodeHarness.__init__`.
"""

from __future__ import annotations

import importlib.metadata
import json
import shutil
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

from adk_harness.protocol import HarnessSpec, HarnessTurn

__all__ = ["ClaudeCodeHarness"]


def _stringify_tool_result(content: str | list[dict[str, Any]] | None) -> str | None:
    """Flatten a `ToolResultBlock.content` payload to text for `HarnessTurn.text`.

    The full structure survives regardless, in `raw`; this is just the best
    plain-text rendering for callers that only look at `text`.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    parts = [
        item["text"] if item.get("type") == "text" and "text" in item else json.dumps(item)
        for item in content
    ]
    return "\n".join(parts) if parts else None


def _usage_text(message: Any) -> str:
    parts = [f"{message.num_turns} turn(s)", f"{message.duration_ms}ms"]
    if message.total_cost_usd is not None:
        parts.append(f"${message.total_cost_usd:.4f}")
    return ", ".join(parts)


class ClaudeCodeHarness:
    """Run Claude Code through `claude-agent-sdk`, one `query()` per `run()` call."""

    def __init__(
        self,
        *,
        model: str | None = None,
        allowed_tools: Sequence[str] | None = None,
        permission_mode: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.allowed_tools = tuple(allowed_tools) if allowed_tools is not None else None
        self.permission_mode = permission_mode
        self.system_prompt = system_prompt
        self.spec = HarnessSpec(id="claude_code", version="unknown", available=False)
        # `query()` async generators currently in flight, so `aclose()` has
        # something to close. A generator removes itself when it finishes on
        # its own; `aclose()` drains whatever is left. Typed `Any`, not
        # `AsyncIterator`, because `query()`'s declared return type is the
        # narrower `AsyncIterator[Message]` protocol (no `.aclose()`) even
        # though it is, in fact, an async generator (confirmed by reading
        # `query.py`'s source, not just its signature).
        self._active_queries: list[Any] = []

    async def discover(self) -> HarnessSpec:
        try:
            import claude_agent_sdk
        except ImportError as exc:
            self.spec = HarnessSpec(
                id="claude_code",
                version="unknown",
                available=False,
                detail=(
                    f"claude-agent-sdk is not installed ({exc}); "
                    "install with `pip install claude-agent-sdk`."
                ),
            )
            return self.spec

        try:
            try:
                version = importlib.metadata.version("claude-agent-sdk")
            except importlib.metadata.PackageNotFoundError:
                version = getattr(claude_agent_sdk, "__version__", "unknown")

            binary = shutil.which("claude")
            if binary is None:
                self.spec = HarnessSpec(
                    id="claude_code",
                    version=version,
                    available=False,
                    detail=(
                        "claude-agent-sdk is installed but the `claude` CLI binary "
                        "was not found on PATH; the SDK shells out to it for every run."
                    ),
                )
                return self.spec

            self.spec = HarnessSpec(
                id="claude_code",
                version=version,
                capabilities=(*HarnessTurn.KINDS, "session_resume"),
                available=True,
                detail=f"claude CLI resolved at {binary}",
            )
            return self.spec
        except Exception as exc:  # noqa: BLE001 - CONTRACT.md rule 3 requires this to be unconditional
            # Belt-and-suspenders backstop for CONTRACT.md rule 3 ("discover()
            # must not raise"): everything above is expected to be safe
            # (PackageNotFoundError is caught explicitly, shutil.which does
            # not raise), but a version-lookup backend or import hook doing
            # something unexpected should degrade to unavailable, not crash
            # the caller. HarnessRegistry.discover_all() has its own
            # exception backstop, but relying on that loses this detail
            # string, per CONTRACT.md.
            self.spec = HarnessSpec(
                id="claude_code",
                version="unknown",
                available=False,
                detail=f"unexpected error during discovery: {type(exc).__name__}: {exc}",
            )
            return self.spec

    async def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKError,
            ResultMessage,
            ServerToolResultBlock,
            ServerToolUseBlock,
            TextBlock,
            ThinkingBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
            query,
        )

        options = ClaudeAgentOptions(
            cwd=cwd,
            model=self.model,
            allowed_tools=list(self.allowed_tools) if self.allowed_tools is not None else [],
            # `self.permission_mode` is a plain `str` in this adapter's public
            # signature (deliberately: constraining it to the vendor's exact
            # `PermissionMode` Literal set would require importing that type
            # at module level, which CONTRACT.md rule 2 forbids). Widened
            # here for the SDK's stricter type; an invalid value is the
            # SDK's own runtime error to raise, not this adapter's to predict.
            permission_mode=cast(Any, self.permission_mode),
            system_prompt=self.system_prompt,
            resume=session_id,
        )

        tool_names: dict[str, str] = {}

        def turns_for_content(content: list[Any]) -> Iterator[HarnessTurn]:
            for block in content:
                if isinstance(block, TextBlock):
                    yield HarnessTurn(kind="text", text=block.text, raw=block)
                elif isinstance(block, ThinkingBlock):
                    yield HarnessTurn(kind="text", text=block.thinking, raw=block)
                elif isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
                    tool_names[block.id] = block.name
                    yield HarnessTurn(
                        kind="tool_call",
                        tool_name=block.name,
                        tool_args=dict(block.input),
                        raw=block,
                    )
                elif isinstance(block, ToolResultBlock):
                    yield HarnessTurn(
                        kind="tool_result",
                        text=_stringify_tool_result(block.content),
                        tool_name=tool_names.get(block.tool_use_id),
                        raw=block,
                    )
                elif isinstance(block, ServerToolResultBlock):
                    yield HarnessTurn(
                        kind="tool_result",
                        text=json.dumps(block.content),
                        tool_name=tool_names.get(block.tool_use_id),
                        raw=block,
                    )
                # Any other block type (a future addition to the wire format)
                # is dropped rather than force-fitted onto a kind it doesn't
                # match — CONTRACT.md is explicit that this is the right call.

        # `query()`'s declared return type is `AsyncIterator[Message]` (no
        # `.aclose()` in that protocol) even though it is, in fact, an async
        # generator — see the module docstring. `Any` here is what lets the
        # `agen.aclose()` calls below type-check against what it actually is.
        agen: Any = query(prompt=prompt, options=options)
        self._active_queries.append(agen)
        saw_error_turn = False
        try:
            async for message in agen:
                if isinstance(message, AssistantMessage):
                    for turn in turns_for_content(message.content):
                        yield turn
                    if message.error is not None:
                        saw_error_turn = True
                        yield HarnessTurn(
                            kind="error",
                            text=f"assistant error: {message.error}",
                            raw=message,
                        )
                elif isinstance(message, UserMessage):
                    if isinstance(message.content, list):
                        for turn in turns_for_content(message.content):
                            yield turn
                    # A plain string UserMessage is the CLI echoing the prompt
                    # we just sent; dropped as a repeat of previous content.
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        saw_error_turn = True
                        text = message.result or "; ".join(message.errors or [])
                        yield HarnessTurn(
                            kind="error",
                            text=text or "Claude Code reported an error result.",
                            raw=message,
                        )
                    yield HarnessTurn(kind="usage", text=_usage_text(message), raw=message)
                # SystemMessage and its Task*/HookEvent subclasses are session
                # bookkeeping (init banners, task-progress heartbeats, hook
                # lifecycle events) — dropped per CONTRACT.md.
        except ClaudeSDKError as exc:
            # `query()` re-raises after an `is_error` result frame (see the
            # module docstring). If we already turned that result into an
            # error turn, this is the same failure a second time — swallow
            # it. If not, the CLI failed before ever producing a proper
            # result (e.g. spawn failure), and this is the only signal we get.
            if not saw_error_turn:
                yield HarnessTurn(kind="error", text=str(exc), raw=exc)
        finally:
            if agen in self._active_queries:
                self._active_queries.remove(agen)
            await agen.aclose()

    async def aclose(self) -> None:
        queries, self._active_queries = self._active_queries, []
        for agen in queries:
            await agen.aclose()
