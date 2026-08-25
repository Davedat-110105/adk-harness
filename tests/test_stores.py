"""SQLite persistence for precedents."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from adk_harness.precedent import Applicability, MatchOutcome, Precedent, PrecedentStore
from adk_harness.stores import SQLitePrecedentStore


def _precedent() -> Precedent:
    return Precedent(
        precedent_id="prec_sqlite",
        action="tool:apply_patch",
        ambiguity_type="approval_required:apply_patch",
        applicability=(
            Applicability("publicly_exposed", "eq", True),
            Applicability("environment", "in", ("production", "staging")),
            Applicability("labels", "contains", "stateful"),
            Applicability("service", "startswith", "checkout-"),
            Applicability("tier", "ne", "development"),
        ),
        decision={"strategy": "prefer_zero_downtime", "limits": {"max": 2}},
        rationale="Public stateful services should avoid visible interruption.",
        confirmed_by="human:dave",
        created_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        review_after=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
    )


FACTS: dict[str, Any] = {
    "publicly_exposed": True,
    "environment": "production",
    "labels": ["stateful", "customer-facing"],
    "service": "checkout-api",
    "tier": "production",
}
NOW = datetime(2026, 8, 25, 13, 0, tzinfo=UTC)


def test_precedent_round_trip_preserves_predicates_and_review_date(tmp_path: Any) -> None:
    database = tmp_path / "precedents.sqlite3"
    precedent = _precedent()

    expected_store = PrecedentStore([precedent])
    expected = expected_store.match(
        action=precedent.action,
        ambiguity_type=precedent.ambiguity_type,
        facts=FACTS,
        now=NOW,
    )

    with SQLitePrecedentStore(database) as store:
        store.add(precedent)

    with SQLitePrecedentStore(database) as restored:
        assert restored.all() == (precedent,)
        assert restored.all()[0].review_after == precedent.review_after
        assert restored.match(
            action=precedent.action,
            ambiguity_type=precedent.ambiguity_type,
            facts=FACTS,
            now=NOW,
        ) == expected
        assert restored.match(
            action=precedent.action,
            ambiguity_type=precedent.ambiguity_type,
            facts=FACTS,
            now=precedent.review_after + timedelta(seconds=1),
        ).outcome is MatchOutcome.expired


def test_superseding_precedent_retirement_survives_restart(tmp_path: Any) -> None:
    database = tmp_path / "precedents.sqlite3"
    old = _precedent()
    new = replace(
        old,
        precedent_id="prec_sqlite_new",
        decision={"strategy": "prefer_low_cost"},
        supersedes=old.precedent_id,
    )

    with SQLitePrecedentStore(database) as store:
        store.add(old)
        store.add(new)

    with SQLitePrecedentStore(database) as restored:
        assert {precedent.precedent_id for precedent in restored.active()} == {
            new.precedent_id
        }
        assert restored.all()[0].status == "superseded"
