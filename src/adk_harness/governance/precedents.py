"""Human judgment, captured once and reused safely.

When policy says a call needs human approval, the human's answer is worth more
than one decision. This module turns that answer into a scoped, typed precedent
so the next equivalent call does not interrupt anyone.

The matcher is deliberately deterministic. Hard predicates decide whether a
precedent is *admissible* at all; ranking only orders the candidates that
already passed. Similarity never admits a precedent that the predicates
rejected — that inversion is how these systems start applying a rule about one
service to every service that merely reads similar.

No model call happens anywhere in this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

__all__ = [
    "Applicability",
    "MatchOutcome",
    "MatchResult",
    "Precedent",
    "PrecedentStore",
]


class MatchOutcome(StrEnum):
    """What the store concluded about a pending decision."""

    apply = "apply"
    """Exactly one admissible precedent. Use its decision, do not ask."""

    ask = "ask"
    """Nothing admissible. Ask the human."""

    conflict = "conflict"
    """Several admissible precedents disagree. Ask, and say why."""

    expired = "expired"
    """A precedent matches but is past review. Ask, and offer to renew it."""


@dataclass(frozen=True, slots=True)
class Applicability:
    """One hard predicate that a fact bundle must satisfy.

    A missing fact is never treated as a pass. If the caller cannot supply a
    fact the predicate names, the precedent is inadmissible and the human is
    asked — guessing is what makes precedent dangerous.
    """

    field: str
    operator: str
    value: Any

    SUPPORTED = ("eq", "ne", "in", "contains", "startswith")

    def satisfied_by(self, facts: Mapping[str, Any]) -> bool:
        if self.field not in facts:
            return False
        actual = facts[self.field]
        match self.operator:
            case "eq":
                return bool(actual == self.value)
            case "ne":
                return bool(actual != self.value)
            case "in":
                return actual in self.value
            case "contains":
                return self.value in actual
            case "startswith":
                return isinstance(actual, str) and actual.startswith(self.value)
        raise ValueError(f"unsupported operator {self.operator!r}; use one of {self.SUPPORTED}")


@dataclass(frozen=True, slots=True)
class Precedent:
    """A human decision, scoped so it can be reapplied without re-asking."""

    precedent_id: str
    action: str
    ambiguity_type: str
    applicability: tuple[Applicability, ...]
    decision: Mapping[str, Any]
    rationale: str
    confirmed_by: str
    created_at: datetime
    review_after: datetime | None = None
    supersedes: str | None = None
    status: str = "active"
    schema_version: int = 1

    def signature(self) -> str:
        """A stable identity for "this exact question, asked again"."""
        payload = json.dumps(
            {
                "action": self.action,
                "ambiguity_type": self.ambiguity_type,
                "schema_version": self.schema_version,
                "predicates": sorted(
                    (p.field, p.operator, repr(p.value)) for p in self.applicability
                ),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def admits(self, *, action: str, ambiguity_type: str, facts: Mapping[str, Any]) -> bool:
        """Hard gate. Every condition must hold; none of it is fuzzy."""
        if self.status != "active":
            return False
        if self.action != action or self.ambiguity_type != ambiguity_type:
            return False
        return all(predicate.satisfied_by(facts) for predicate in self.applicability)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.review_after is None:
            return False
        return (now or datetime.now(UTC)) >= self.review_after

    def specificity(self) -> int:
        """How many predicates this precedent commits to.

        Used only to order admissible candidates. A precedent that names more
        conditions is a closer fit than one that names fewer.
        """
        return len(self.applicability)


@dataclass(frozen=True, slots=True)
class MatchResult:
    outcome: MatchOutcome
    precedent: Precedent | None = None
    candidates: tuple[Precedent, ...] = ()
    reason: str | None = None


class PrecedentStore:
    """Hold precedents and answer whether one applies.

    In-process for now. The contract is deliberately small so a durable backing
    store can implement it without the matcher changing.
    """

    def __init__(self, precedents: Iterable[Precedent] = ()) -> None:
        self._by_id: dict[str, Precedent] = {}
        for precedent in precedents:
            self.add(precedent)

    def add(self, precedent: Precedent) -> None:
        """Store a precedent, retiring anything it supersedes."""
        if precedent.supersedes and precedent.supersedes in self._by_id:
            old = self._by_id[precedent.supersedes]
            self._by_id[old.precedent_id] = _retire(old)
        self._by_id[precedent.precedent_id] = precedent

    def all(self) -> tuple[Precedent, ...]:
        return tuple(self._by_id.values())

    def active(self) -> tuple[Precedent, ...]:
        return tuple(p for p in self._by_id.values() if p.status == "active")

    def match(
        self,
        *,
        action: str,
        ambiguity_type: str,
        facts: Mapping[str, Any],
        now: datetime | None = None,
    ) -> MatchResult:
        """Decide whether a human still needs to be asked.

        Stage one admits only precedents whose hard predicates all hold. Stage
        two orders survivors by specificity. Stage three refuses to guess when
        survivors disagree or when the best one is due for review.
        """
        admissible = [
            p
            for p in self._by_id.values()
            if p.admits(action=action, ambiguity_type=ambiguity_type, facts=facts)
        ]
        if not admissible:
            return MatchResult(MatchOutcome.ask, reason="no precedent covers these facts")

        expired = [p for p in admissible if p.is_expired(now=now)]
        live = [p for p in admissible if not p.is_expired(now=now)]

        if not live:
            best = max(expired, key=_rank)
            return MatchResult(
                MatchOutcome.expired,
                precedent=best,
                candidates=tuple(expired),
                reason="the matching precedent is past its review date",
            )

        if _disagree(live):
            return MatchResult(
                MatchOutcome.conflict,
                candidates=tuple(live),
                reason=f"{len(live)} precedents apply and their decisions differ",
            )

        return MatchResult(
            MatchOutcome.apply,
            precedent=max(live, key=_rank),
            candidates=tuple(live),
        )


def _rank(precedent: Precedent) -> tuple[int, datetime]:
    """More specific wins; the newer one breaks a tie."""
    return (precedent.specificity(), precedent.created_at)


def _disagree(precedents: Sequence[Precedent]) -> bool:
    first = json.dumps(dict(precedents[0].decision), sort_keys=True)
    return any(json.dumps(dict(p.decision), sort_keys=True) != first for p in precedents[1:])


def _retire(precedent: Precedent) -> Precedent:
    from dataclasses import replace

    return replace(precedent, status="superseded")
