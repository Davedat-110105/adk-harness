"""What the gate decides about, and what it does with the answer.

The first test here exists because of a real failure. The demo deployed to
Cloud Run, Gemini dispatched to a harness, and the gate blocked it with
"run_demo is outside the workspace /workspace" — a refusal that reads as
governance working and is actually the policy deciding about the wrong noun.
An `AgentTool` call carries only instruction text, so `tool_args` has no `cwd`,
and the resource fell back to the tool's name.

A gate that denies for the wrong reason is worse than one that fails loudly,
because the audit trail looks correct.
"""

from __future__ import annotations

from typing import Any

import pytest
from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.governance import CoactraGovernance

SCOPE = Scope(tenant_id="acme", namespace="fleet")


class RecordingPolicy:
    """Allows everything and remembers what it was asked about."""

    def __init__(self, outcome: DecisionOutcome = DecisionOutcome.allow) -> None:
        self.requests: list[PolicyRequest] = []
        self._outcome = outcome

    async def check(self, request: PolicyRequest) -> Decision:
        self.requests.append(request)
        return Decision(outcome=self._outcome, reason="test", source="test")


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeToolContext:
    def __init__(self) -> None:
        self.confirmations: list[dict[str, Any]] = []

    def request_confirmation(self, *, hint: str, payload: dict[str, Any]) -> None:
        self.confirmations.append({"hint": hint, "payload": payload})


@pytest.mark.asyncio
async def test_a_dispatch_without_cwd_is_judged_on_the_registered_directory() -> None:
    policy = RecordingPolicy()
    gate = CoactraGovernance(
        policy=policy,
        scope=SCOPE,
        resources={"run_demo": "/workspace"},
    )

    await gate.before_tool_callback(
        tool=FakeTool("run_demo"),
        tool_args={"request": "add a docstring"},
        tool_context=FakeToolContext(),
    )

    assert policy.requests[0].resource == "/workspace"
    assert policy.requests[0].action == "tool:run_demo"


@pytest.mark.asyncio
async def test_an_explicit_cwd_beats_the_registered_directory() -> None:
    """A tool that names its own target is more specific than the fleet default."""
    policy = RecordingPolicy()
    gate = CoactraGovernance(
        policy=policy, scope=SCOPE, resources={"edit": "/workspace"}
    )

    await gate.before_tool_callback(
        tool=FakeTool("edit"),
        tool_args={"cwd": "/workspace/api"},
        tool_context=FakeToolContext(),
    )

    assert policy.requests[0].resource == "/workspace/api"


@pytest.mark.asyncio
async def test_an_unregistered_tool_still_gets_a_decision() -> None:
    """Falling back to the tool name is not good, but it beats crashing."""
    policy = RecordingPolicy()
    gate = CoactraGovernance(policy=policy, scope=SCOPE)

    await gate.before_tool_callback(
        tool=FakeTool("mystery"), tool_args={}, tool_context=FakeToolContext()
    )

    assert policy.requests[0].resource == "mystery"


@pytest.mark.asyncio
async def test_a_denial_becomes_the_tool_result_rather_than_an_exception() -> None:
    """The model must be able to explain the refusal, so it has to see it."""
    gate = CoactraGovernance(
        policy=RecordingPolicy(DecisionOutcome.deny),
        scope=SCOPE,
        resources={"run_demo": "/workspace"},
    )

    result = await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={}, tool_context=FakeToolContext()
    )

    assert result == {"status": "blocked", "reason": "test", "tool": "run_demo"}
    assert [r.outcome for r in gate.audit] == ["deny"]


@pytest.mark.asyncio
async def test_an_allow_returns_none_so_the_tool_runs() -> None:
    gate = CoactraGovernance(policy=RecordingPolicy(), scope=SCOPE)

    result = await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={}, tool_context=FakeToolContext()
    )

    assert result is None
    assert [r.outcome for r in gate.audit] == ["allow"]


@pytest.mark.asyncio
async def test_requires_approval_with_no_precedent_asks_a_human() -> None:
    gate = CoactraGovernance(
        policy=RecordingPolicy(DecisionOutcome.requires_approval),
        scope=SCOPE,
        resources={"run_demo": "/workspace/prod"},
    )
    context = FakeToolContext()

    await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={"request": "edit"}, tool_context=context
    )

    assert len(context.confirmations) == 1
    assert "No precedent covers this yet" in context.confirmations[0]["hint"]
    assert "asked_human" in [r.outcome for r in gate.audit]


@pytest.mark.asyncio
async def test_asking_a_human_also_stops_the_tool() -> None:
    """The brake and the question are the same return value.

    `request_confirmation()` only records a request on the event actions; it
    halts nothing. ADK runs the tool whenever `before_tool_callback` returns
    `None` (`flows/llm_flows/functions.py`, step 3). So a gate that asks and
    returns `None` asks *and* proceeds — an approval prompt that changes
    nothing, which is worse than no prompt at all because it looks like
    oversight.
    """
    gate = CoactraGovernance(
        policy=RecordingPolicy(DecisionOutcome.requires_approval),
        scope=SCOPE,
        resources={"run_demo": "/workspace/prod"},
    )
    context = FakeToolContext()

    result = await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={}, tool_context=context
    )

    assert result is not None, "returning None would let the work proceed"
    assert result["status"] == "awaiting_confirmation"
    assert context.confirmations, "the human still has to be asked"


class ConfirmedContext(FakeToolContext):
    """What ADK hands back after a human clicks approve."""

    def __init__(self, confirmed: bool = True) -> None:
        super().__init__()
        self.tool_confirmation = type(
            "Answer", (), {"confirmed": confirmed, "hint": "approved by dave"}
        )()


@pytest.mark.asyncio
async def test_an_answered_confirmation_lets_the_run_proceed() -> None:
    """Otherwise the approve button does nothing and the run never finishes.

    ADK resumes by re-invoking the tool with the answered ToolConfirmation
    attached, which re-enters this gate. A gate that only consults precedent
    would ask the same question forever.
    """
    gate = CoactraGovernance(
        policy=RecordingPolicy(DecisionOutcome.requires_approval),
        scope=SCOPE,
        resources={"run_demo": "/workspace/prod"},
    )
    context = ConfirmedContext()

    result = await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={}, tool_context=context
    )

    assert result is None, "an approved call must run"
    assert context.confirmations == [], "and must not ask again"
    assert "confirmed_by_human" in [r.outcome for r in gate.audit]


@pytest.mark.asyncio
async def test_an_unanswered_confirmation_still_asks() -> None:
    gate = CoactraGovernance(
        policy=RecordingPolicy(DecisionOutcome.requires_approval), scope=SCOPE
    )
    context = ConfirmedContext(confirmed=False)

    result = await gate.before_tool_callback(
        tool=FakeTool("run_demo"), tool_args={}, tool_context=context
    )

    assert result is not None
    assert len(context.confirmations) == 1
