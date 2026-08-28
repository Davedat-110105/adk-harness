"""Present a harness as an ADK agent.

`HarnessAgent` is the seam between two worlds. On one side is a coding-agent
harness that runs as its own process and makes its own decisions. On the other
is ADK, which expects a `BaseAgent` yielding `Event`s. This wraps the first as
the second, so a Gemini orchestrator can dispatch to Claude Code or Codex the
same way it dispatches to any other sub-agent.

Where governance actually applies
---------------------------------
Be precise about this, because it is easy to overclaim.

A `HarnessAgent` is meant to be exposed to an orchestrator as an `AgentTool`.
That tool call passes through `CoactraGovernance`, which decides whether *this
harness may be dispatched into this working directory for this task*. That is
the enforced boundary, and it is the one the policy is written against —
`governance.py` keys the policy resource on `cwd` for exactly this reason.

The tool calls a harness makes *inside* its own run — the individual file edits
and shell commands — do not pass back through ADK, because the harness executes
them in its own process. This agent surfaces them as events so they land in the
session transcript and are visible to an auditor, but it does not pretend to
have stopped them. Per-call enforcement inside a harness requires that harness's
own permission hook, and wiring one belongs to the adapter's vendor surface, not
here.

So: dispatch is gated, inner activity is observed. Saying otherwise would make
the audit trail a liar, and an audit trail nobody can trust is worse than none.
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
    """Run one harness as an ADK agent, streaming its work as events.

    The agent holds no policy of its own. It streams; the governance plugin
    sitting in front of the tool call that reached here has already decided
    whether this run happens at all.
    """

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

        # The registry intentionally shares adapter instances.  Closing here
        # would terminate a sibling invocation using the same harness; each
        # adapter owns cleanup of its per-run resources instead.
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
        """Render one harness turn as an ADK event.

        Inner tool activity becomes readable text rather than an ADK function
        call. An ADK `FunctionCall` event means "the model is asking the runtime
        to run this", and the runtime would then try to run it — but the harness
        already ran it in its own process. Emitting one would be a lie about who
        did what, and it would double-execute if anything downstream believed it.
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
    """Recover the user's request as plain text.

    A harness takes a string. ADK carries structured `Content`. Non-text parts
    (images, inline data) are dropped rather than serialized into the prompt,
    because a harness that reads a base64 blob as instructions behaves worse
    than one that never saw it.
    """
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
