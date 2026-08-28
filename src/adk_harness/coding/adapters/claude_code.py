"""Claude Code adapter using one SDK query() generator per run.

Streams text, tool activity, usage, and errors; session_id maps to resume.
Vendor permission defaults are preserved. Explicit generator closure releases
the subprocess, and repeated SDK errors are emitted only once.
"""

from __future__ import annotations

import importlib.metadata
import json
import shutil
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

__all__ = ["ClaudeCodeHarness"]


def _stringify_tool_result(content: str | list[dict[str, Any]] | None) -> str | None:
    """Render tool content as text; the original structure remains in raw."""
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
        # Track active query generators for shutdown.
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
        except Exception as exc:
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
                # Ignore unknown block types.

        # The SDK annotation omits aclose(), but query() returns an async generator.
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
                # Ignore SDK bookkeeping messages.
        except ClaudeSDKError as exc:
            # Avoid reporting an SDK error twice after an error result frame.
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
