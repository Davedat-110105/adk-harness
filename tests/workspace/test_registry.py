from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from adk_harness.workspace.registry import AgentCatalogue, MemoryBank, agent_id


class _Document:
    def __init__(self, store: dict[str, Any], key: str) -> None:
        self._store = store
        self._key = key

    def set(self, payload: dict[str, Any]) -> None:
        self._store[self._key] = payload

    def to_dict(self) -> dict[str, Any]:
        return self._store[self._key]


class _Collection:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def document(self, key: str) -> _Document:
        return _Document(self._store, key)

    def stream(self) -> list[_Document]:
        return [_Document(self._store, key) for key in self._store]


class _Client:
    def __init__(self, **collections: dict[str, Any]) -> None:
        self._collections = collections

    def collection(self, name: str) -> _Collection:
        return _Collection(self._collections.setdefault(name, {}))


def test_publishing_tells_the_fleet_what_this_machine_can_do() -> None:
    client = _Client()
    catalogue = AgentCatalogue(client)

    entry = catalogue.publish(
        agent_id="agent-1",
        subject="person@example.com",
        operations=["calendar_events_list", "calendar_events_insert", "gmail_drafts_create"],
        granted_scopes=["https://www.googleapis.com/auth/calendar.events"],
        policy_version="workspace-mcp-1",
    )

    assert entry.services == ("calendar", "gmail")
    assert catalogue.discover()[0]["agent_id"] == "agent-1"


def test_discovery_can_ask_for_one_service() -> None:
    client = _Client()
    catalogue = AgentCatalogue(client)
    catalogue.publish(
        agent_id="calendar-only",
        subject="a@example.com",
        operations=["calendar_events_list"],
        granted_scopes=[],
        policy_version="v1",
    )
    catalogue.publish(
        agent_id="sheets-only",
        subject="b@example.com",
        operations=["sheets_values_get"],
        granted_scopes=[],
        policy_version="v1",
    )

    found = catalogue.discover(service="sheets")

    assert [item["agent_id"] for item in found] == ["sheets-only"]


def test_publishing_again_replaces_the_previous_entry() -> None:
    """A machine has one current capability, not a pile of stale ones."""
    client = _Client()
    catalogue = AgentCatalogue(client)
    for operations in (["calendar_events_list"], ["calendar_events_list", "docs_get"]):
        catalogue.publish(
            agent_id="agent-1",
            subject="person@example.com",
            operations=operations,
            granted_scopes=[],
            policy_version="v1",
        )

    found = catalogue.discover()

    assert len(found) == 1
    assert found[0]["services"] == ["calendar", "docs"]


def test_recall_returns_recent_decisions_newest_first() -> None:
    now = datetime.now(UTC)
    ledger = {
        "old": {
            "action": "calendar.events.list",
            "policy_outcome": "allowed",
            "actor": "person",
            "input_hash": "h1",
            "recorded_at": now - timedelta(days=90),
        },
        "recent": {
            "action": "calendar.events.insert",
            "policy_outcome": "held",
            "actor": "person",
            "input_hash": "h2",
            "recorded_at": now - timedelta(days=2),
            "policy_reason": "others will see it",
        },
        "newest": {
            "action": "calendar.events.get",
            "policy_outcome": "allowed",
            "actor": "person",
            "input_hash": "h3",
            "recorded_at": now - timedelta(hours=1),
        },
    }

    recalled = MemoryBank(_Client(action_ledger=ledger)).recall(since_days=30)

    assert [item.operation for item in recalled] == [
        "calendar.events.get",
        "calendar.events.insert",
    ]
    assert recalled[1].outcome == "held"
    assert recalled[1].reason == "others will see it"


def test_recall_can_be_limited_to_one_person() -> None:
    now = datetime.now(UTC)
    ledger = {
        "mine": {"action": "a", "actor": "me", "recorded_at": now, "policy_outcome": "allowed"},
        "theirs": {"action": "b", "actor": "you", "recorded_at": now, "policy_outcome": "allowed"},
    }

    recalled = MemoryBank(_Client(action_ledger=ledger)).recall(actor="me")

    assert [item.operation for item in recalled] == ["a"]


def test_the_agent_id_is_stable_for_one_person_on_one_machine() -> None:
    assert agent_id("person@example.com") == agent_id("person@example.com")
    assert agent_id("person@example.com") != agent_id("other@example.com")
