"""Wrap a coding harness as an ADK agent that streams events.

Governance gates AgentTool dispatch, not the vendor's inner file or shell calls.
Inner activity is reported as text; enforcement requires vendor permission hooks.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from pydantic import ConfigDict, Field, SkipValidation

from adk_harness.coding.protocol import Harness, HarnessTurn

__all__ = ["HarnessAgent"]


class HarnessAgent(BaseAgent):
    """Stream one harness as ADK events after the governance gate permits dispatch."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    harness: SkipValidation[Harness] = Field(
        description="The harness this agent drives.",
    )
    cwd: str = Field(
        description=(
            "Working directory the harness runs in. This is also the resource "
            "the policy decision is keyed on, so it is a required, explicit "
            "argument rather than something inferred from the process."
        ),
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "A *vendor* session id to resume, or None to start fresh. This is "
            "deliberately not ADK's session id. They live in different "
            "namespaces: passing ADK's id to Claude Code produces 'No "
            "conversation found with session ID', and to Codex produces a "
            "resume against a session that was never recorded. A caller who "
            "genuinely has a vendor session id can pass it; nobody should "
            "infer one."
        ),
    )
    skip_unavailable: bool = Field(
        default=True,
        description=(
            "When the harness is not installed on this machine, emit one "
            "explanatory event and stop, rather than raising. A fleet should "
            "degrade to the harnesses that are present."
        ),
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        spec = await self.harness.discover()
        if not spec.available:
            if not self.skip_unavailable:
                raise RuntimeError(
                    f"harness {spec.id!r} is not available: {spec.detail}"
                )
            yield self._event(
                ctx,
                text=f"Harness {spec.id!r} is not available here: {spec.detail}",
            )
            return

        prompt = _prompt_of(ctx)
        if not prompt:
            yield self._event(ctx, text="No prompt was provided to the harness.")
            return

        # Close only this stream; closing the shared harness would cancel sibling runs.
        stream = self.harness.run(prompt, cwd=self.cwd, session_id=self.session_id)
        try:
            async for turn in stream:
                event = self._event_for_turn(ctx, turn)
                if event is not None:
                    yield event
        finally:
            # Close this invocation's iterator, never the shared harness.
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    def _event_for_turn(self, ctx: InvocationContext, turn: HarnessTurn) -> Event | None:
        """Render harness activity as ADK events.

        Inner tool activity must stay text: FunctionCall events could execute it again.
        """
        if turn.kind == "text":
            return self._event(ctx, text=turn.text or "")
        if turn.kind == "tool_call":
            args = _compact(turn.tool_args)
            return self._event(ctx, text=f"[{turn.tool_name}] {args}")
        if turn.kind == "tool_result":
            return self._event(ctx, text=f"[{turn.tool_name} result] {turn.text or ''}")
        if turn.kind == "usage":
            return self._event(ctx, text=f"[usage] {turn.text or _compact(turn.raw)}")
        if turn.kind == "error":
            return self._event(ctx, text=f"[error] {turn.text or ''}", error=turn.text)
        return None

    def _event(
        self,
        ctx: InvocationContext,
        *,
        text: str,
        error: str | None = None,
    ) -> Event:
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            error_message=error,
        )


def _prompt_of(ctx: InvocationContext) -> str:
    """Extract text from ADK Content; do not serialize images or binary data as instructions."""
    content = ctx.user_content
    if content is None or not content.parts:
        return ""
    return "\n".join(part.text for part in content.parts if part.text).strip()


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)
