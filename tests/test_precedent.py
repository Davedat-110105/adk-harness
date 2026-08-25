"""The precedent loop: ask once, then stop asking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from coactra import Policy, Scope

from adk_harness.governance import CoactraGovernance
from adk_harness.precedent import (
    Applicability,
    MatchOutcome,
    Precedent,
    PrecedentStore,
)

SCOPE = Scope(tenant_id="acme", namespace="fleet")


def _precedent(pid: str = "prec_01", **over: Any) -> Precedent:
    base: dict[str, Any] = dict(
        precedent_id=pid,
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        applicability=(
            Applicability("publicly_exposed", "eq", True),
            Applicability("stateful", "eq", True),
        ),
        decision={"strategy": "prefer_zero_downtime"},
        rationale="Public stateful services should avoid visible interruption.",
        confirmed_by="human:dave",
        created_at=datetime.now(UTC),
    )
    base.update(over)
    return Precedent(**base)


FACTS = {"publicly_exposed": True, "stateful": True}


class StubTool:
    name = "apply_patch"


class StubContext:
    def __init__(self) -> None:
        self.confirmations: list[dict[str, Any]] = []

    def request_confirmation(self, *, hint: str | None = None, payload: Any = None) -> None:
        self.confirmations.append({"hint": hint, "payload": payload})


# --- the matcher -----------------------------------------------------------


def test_no_precedent_means_ask() -> None:
    result = PrecedentStore().match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.ask


def test_matching_precedent_applies() -> None:
    store = PrecedentStore([_precedent()])
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.apply
    assert result.precedent is not None
    assert result.precedent.decision["strategy"] == "prefer_zero_downtime"


def test_a_missing_fact_is_never_a_pass() -> None:
    """The safety property. Absent evidence must not be read as agreement."""
    store = PrecedentStore([_precedent()])
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts={"publicly_exposed": True},  # `stateful` unknown
    )
    assert result.outcome is MatchOutcome.ask


def test_different_facts_do_not_match() -> None:
    store = PrecedentStore([_precedent()])
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts={"publicly_exposed": False, "stateful": True},
    )
    assert result.outcome is MatchOutcome.ask


def test_a_different_question_does_not_match() -> None:
    store = PrecedentStore([_precedent()])
    result = store.match(
        action="tool:delete_volume",
        ambiguity_type="approval_required:delete_volume",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.ask


def test_disagreeing_precedents_conflict_rather_than_guess() -> None:
    store = PrecedentStore(
        [
            _precedent("prec_01"),
            _precedent("prec_02", decision={"strategy": "prefer_low_cost"}),
        ]
    )
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.conflict
    assert len(result.candidates) == 2


def test_expired_precedent_asks_for_revalidation() -> None:
    store = PrecedentStore(
        [_precedent(review_after=datetime.now(UTC) - timedelta(days=1))]
    )
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.expired
    assert result.precedent is not None


def test_superseding_retires_the_old_precedent() -> None:
    store = PrecedentStore([_precedent("prec_01")])
    store.add(
        _precedent(
            "prec_02",
            decision={"strategy": "prefer_low_cost"},
            supersedes="prec_01",
        )
    )
    assert {p.precedent_id for p in store.active()} == {"prec_02"}
    result = store.match(
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        facts=FACTS,
    )
    assert result.outcome is MatchOutcome.apply
    assert result.precedent is not None
    assert result.precedent.precedent_id == "prec_02"


# --- the loop, through the plugin -----------------------------------------


@pytest.mark.asyncio
async def test_asks_once_then_stops_asking() -> None:
    """First call interrupts the human. Second call, same facts, does not."""
    gate = CoactraGovernance(
        policy=_ApprovalPolicy(), scope=SCOPE, principal="user:dave"
    )
    tool, ctx = StubTool(), StubContext()
    args = {"publicly_exposed": True, "stateful": True, "service": "checkout"}

    first = await gate.before_tool_callback(tool=tool, tool_args=args, tool_context=ctx)
    assert first is None
    assert len(ctx.confirmations) == 1, "the first call must ask"

    gate.remember(
        tool_name="apply_patch",
        precedent_id="prec_01",
        decision={"strategy": "prefer_zero_downtime"},
        rationale="Public stateful services should avoid visible interruption.",
        confirmed_by="human:dave",
        applicability=(
            Applicability("publicly_exposed", "eq", True),
            Applicability("stateful", "eq", True),
        ),
    )

    second = await gate.before_tool_callback(
        tool=tool, tool_args=dict(args, service="billing"), tool_context=ctx
    )
    assert second is None
    assert len(ctx.confirmations) == 1, "the second call must not ask again"

    outcomes = [r.outcome for r in gate.audit]
    assert "asked_human" in outcomes
    assert "precedent_saved" in outcomes
    assert "allowed_by_precedent" in outcomes


@pytest.mark.asyncio
async def test_precedent_never_overrides_a_deny() -> None:
    """Precedent removes repeated questions, not the policy gate."""
    gate = CoactraGovernance(policy=Policy.default_deny(), scope=SCOPE)
    tool, ctx = StubTool(), StubContext()
    result = await gate.before_tool_callback(
        tool=tool, tool_args=FACTS, tool_context=ctx
    )
    assert result is not None
    assert result["status"] == "blocked"
    assert ctx.confirmations == []


class _ApprovalPolicy:
    """A policy that always wants a human. Isolates the precedent behaviour."""

    async def check(self, request: Any) -> Any:
        from coactra import Decision, DecisionOutcome

        return Decision(
            outcome=DecisionOutcome.requires_approval,
            reason="human sign-off required",
        )
