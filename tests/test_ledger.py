from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from adk_harness.ledger import FirestoreActionLedger


class AlreadyExists(Exception):
    pass


class FakeSnapshot:
    def __init__(self, document_id: str, payload: dict[str, Any] | None) -> None:
        self.id = document_id
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._payload


class FakeDocument:
    def __init__(self, documents: dict[str, dict[str, Any]], document_id: str) -> None:
        self._documents = documents
        self.id = document_id

    def create(self, payload: dict[str, Any]) -> None:
        if self.id in self._documents:
            raise AlreadyExists()
        self._documents[self.id] = payload

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self.id, self._documents.get(self.id))


class FakeQuery:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self._documents = documents
        self._scope: Any = None
        self._limit = 100

    def where(self, field: str, operator: str, value: Any) -> FakeQuery:
        assert (field, operator) == ("scope", "==")
        self._scope = value
        return self

    def order_by(self, field: str, *, direction: str) -> FakeQuery:
        assert (field, direction) == ("recorded_at", "DESCENDING")
        return self

    def limit(self, limit: int) -> FakeQuery:
        self._limit = limit
        return self

    def stream(self) -> list[FakeSnapshot]:
        matching = [
            (document_id, payload)
            for document_id, payload in self._documents.items()
            if payload["scope"] == self._scope
        ]
        matching.sort(key=lambda item: item[1]["recorded_at"], reverse=True)
        return [
            FakeSnapshot(document_id, payload)
            for document_id, payload in matching[: self._limit]
        ]


class FakeCollection:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self._documents = documents

    def document(self, document_id: str) -> FakeDocument:
        return FakeDocument(self._documents, document_id)

    def where(self, field: str, operator: str, value: Any) -> FakeQuery:
        return FakeQuery(self._documents).where(field, operator, value)


class FakeClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> FakeCollection:
        assert name == "action_ledger"
        return FakeCollection(self.documents)


def _record(ledger: FirestoreActionLedger, key: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "actor": "user:datta",
        "agent": "agent:builder",
        "action": "tool.call",
        "resource": "tool:deploy",
        "scope": "workspace:demo",
        "policy_outcome": "allow",
        "policy_reason": "matched rule",
        "tool_args": {"path": "README.md"},
        "outcome": "completed",
        "idempotency_key": key,
    }
    values.update(overrides)
    return ledger.record(**values)


def test_record_stores_hash_and_redacts_secrets() -> None:
    client = FakeClient()
    ledger = FirestoreActionLedger(client)
    tool_args = {
        "path": "README.md",
        "password": "do-not-store",
        "nested": {"access_token": "also-do-not-store", "safe": True},
    }

    entry_id = _record(ledger, "key-1", tool_args=tool_args)
    stored = client.documents[entry_id]
    expected = json.dumps(tool_args, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    assert stored["input_hash"] == hashlib.sha256(expected.encode()).hexdigest()
    assert stored["tool_args_redacted"] == {
        "path": "README.md",
        "nested": {"safe": True},
    }
    assert "do-not-store" not in json.dumps(stored["tool_args_redacted"])


def test_custom_denylist_is_applied_recursively() -> None:
    client = FakeClient()
    ledger = FirestoreActionLedger(client, denylist=("internal",))

    entry_id = _record(
        ledger,
        "key-custom",
        tool_args={"internal_note": "hidden", "visible": [{"INTERNAL_ID": "hidden"}]},
    )

    assert client.documents[entry_id]["tool_args_redacted"] == {"visible": [{}]}


def test_same_idempotency_key_returns_one_entry_and_same_id() -> None:
    client = FakeClient()
    ledger = FirestoreActionLedger(client)

    first = _record(ledger, "retry-key", outcome="completed")
    second = _record(ledger, "retry-key", outcome="retried")

    assert second == first
    assert len(client.documents) == 1
    assert client.documents[first]["outcome"] == "completed"


def test_ledger_has_no_mutation_methods() -> None:
    assert not hasattr(FirestoreActionLedger, "update")
    assert not hasattr(FirestoreActionLedger, "delete")


def test_query_returns_scope_in_most_recent_first_order() -> None:
    client = FakeClient()
    ledger = FirestoreActionLedger(client)
    first = _record(ledger, "first", action="first")
    second = _record(ledger, "second", action="second")
    client.documents[first]["recorded_at"] = datetime(2026, 8, 27, 12, tzinfo=UTC)
    client.documents[second]["recorded_at"] = datetime(2026, 8, 27, 13, tzinfo=UTC)

    entries = ledger.query(scope="workspace:demo", limit=1)

    assert [entry["action"] for entry in entries] == ["second"]
