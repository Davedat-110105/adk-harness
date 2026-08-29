"""Durable local history and browser-operation storage.

The outbox is transport agnostic. A browser operation is first recorded here,
then a finite Firebase Lite instruction is returned to the trusted UI. A
restart turns unresolved operations into ``unknown`` so they cannot be retried
without an explicit reconciliation read.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import rfc8785

from .models import ActivityEvent


class OutboxConflict(ValueError):
    """An immutable local record or operation changed."""


class OutboxState(StrEnum):
    PENDING = "pending"
    UNKNOWN = "unknown"
    UPLOADED = "uploaded"
    CONFLICT = "conflict"


class OperationState(StrEnum):
    PENDING = "pending"
    UNKNOWN = "unknown"
    ACKNOWLEDGED = "acknowledged"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    event_id: str
    event: ActivityEvent
    state: OutboxState
    attempts: int
    ack_id: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    owner_google_subject: str
    firebase_uid: str
    project_id: str
    workspace_id: str
    namespace: str
    descriptor_hash: str
    descriptor: Mapping[str, Any]
    payload: Mapping[str, Any]
    instruction: Mapping[str, Any]
    state: OperationState
    ack_id: str | None
    ack: Mapping[str, Any] | None
    last_error: str | None
    # True only for the caller that atomically inserted this operation.  A
    # duplicate claim may inspect its durable status, but never receives a
    # second executable release.
    released: bool = False


@dataclass(frozen=True, slots=True)
class ImportedHistoryRecord:
    event_id: str
    event: ActivityEvent
    owner_google_subject: str
    origin: str


def _canonical(value: Any) -> bytes:
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(k): plain(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(v) for v in item]
        return item

    return rfc8785.dumps(plain(value))


def _json(value: Any) -> str:
    return _canonical(value).decode("utf-8")


def _safe_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."} or "/" in value:
        raise ValueError(f"{name} is invalid")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Outbox:
    """Thread-safe SQLite store; it never invokes a cloud SDK."""

    def __init__(self, path: str | Path, *, max_events: int = 100) -> None:
        if max_events < 1 or max_events > 500:
            raise ValueError("max_events must be between 1 and 500")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_outbox (
                event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                content_hash TEXT NOT NULL, state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, ack_id TEXT,
                last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS browser_operations (
                operation_id TEXT PRIMARY KEY, owner_google_subject TEXT NOT NULL,
                firebase_uid TEXT NOT NULL, project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL, namespace TEXT NOT NULL,
                descriptor_hash TEXT NOT NULL, descriptor TEXT NOT NULL,
                payload TEXT NOT NULL, instruction TEXT NOT NULL,
                state TEXT NOT NULL, ack_id TEXT, ack TEXT, last_error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imported_history (
                event_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                content_hash TEXT NOT NULL, owner_google_subject TEXT NOT NULL,
                origin TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        self._db.execute(
            "UPDATE browser_operations SET state=?, last_error=?, updated_at=? WHERE state=?",
            (
                OperationState.UNKNOWN,
                "process restarted before acknowledgement",
                _now(),
                OperationState.PENDING,
            ),
        )
        self.max_events = max_events
        self.max_instruction_bytes = 1_000_000
        self.max_instruction_documents = 500

    def enqueue_history(self, events: Iterable[ActivityEvent]) -> None:
        values = list(events)
        if not values or len(values) > self.max_events:
            raise ValueError("history batch exceeds configured batch bound")
        if any(not isinstance(event, ActivityEvent) for event in values):
            raise TypeError("history outbox accepts ActivityEvent records")
        if len({event.event_id for event in values}) != len(values):
            raise OutboxConflict("duplicate event ID in batch")
        now = _now()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for event in values:
                    row = self._db.execute(
                        "SELECT content_hash, payload FROM history_outbox WHERE event_id=?",
                        (event.event_id,),
                    ).fetchone()
                    payload = json.dumps(event.to_dict(), separators=(",", ":"), ensure_ascii=False)
                    if row is not None:
                        if (
                            row["content_hash"] != event.content_hash
                            or json.loads(row["payload"]) != event.to_dict()
                        ):
                            raise OutboxConflict(f"event {event.event_id} has changed content")
                        continue
                    self._db.execute(
                        # The explicit column list makes schema evolution safe.
                        "INSERT INTO history_outbox(event_id,payload,content_hash,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",  # noqa: E501
                        (
                            event.event_id,
                            payload,
                            event.content_hash,
                            OutboxState.PENDING,
                            now,
                            now,
                        ),
                    )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def get(self, event_id: str) -> OutboxRecord:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM history_outbox WHERE event_id=?", (event_id,)
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return OutboxRecord(
            event_id=row["event_id"],
            event=ActivityEvent.from_dict(json.loads(row["payload"])),
            state=OutboxState(row["state"]),
            attempts=int(row["attempts"]),
            ack_id=row["ack_id"],
            last_error=row["last_error"],
        )

    def pending(self, *, include_unknown: bool = False) -> list[OutboxRecord]:
        states = (
            (OutboxState.PENDING, OutboxState.UNKNOWN)
            if include_unknown
            else (OutboxState.PENDING,)
        )
        marks = ",".join("?" for _ in states)
        with self._lock:
            rows = self._db.execute(
                f"SELECT event_id FROM history_outbox WHERE state IN ({marks}) ORDER BY created_at,event_id",  # noqa: E501
                states,
            ).fetchall()
        return [self.get(row["event_id"]) for row in rows]

    def mark_uploaded(self, event_id: str, *, ack_id: str) -> None:
        _safe_id(ack_id, "ack_id")
        with self._lock:
            row = self._db.execute(
                "SELECT state, ack_id FROM history_outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            if row["state"] in {OutboxState.UPLOADED, OutboxState.UNKNOWN}:
                if row["state"] == OutboxState.UPLOADED and row["ack_id"] == ack_id:
                    return
                raise OutboxConflict("history acknowledgement is not reconcilable")
            self._db.execute(
                "UPDATE history_outbox SET state=?, attempts=attempts+1, ack_id=?, last_error=NULL, updated_at=? WHERE event_id=?",  # noqa: E501
                (OutboxState.UPLOADED, ack_id, _now(), event_id),
            )

    def mark_unknown(self, event_id: str, error: str) -> None:
        if not isinstance(error, str) or not error or len(error) > 500:
            raise ValueError("unknown outcome must include a bounded error")
        with self._lock:
            row = self._db.execute(
                "SELECT state FROM history_outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if row is None:
                raise KeyError(event_id)
            if row["state"] == OutboxState.UPLOADED:
                return
            self._db.execute(
                "UPDATE history_outbox SET state=?, attempts=attempts+1, last_error=?, updated_at=? WHERE event_id=?",  # noqa: E501
                (OutboxState.UNKNOWN, error, _now(), event_id),
            )

    def claim_instruction(
        self,
        *,
        operation_id: str,
        owner_google_subject: str,
        firebase_uid: str,
        project_id: str,
        workspace_id: str,
        namespace: str,
        descriptor: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> OperationRecord:
        for value, name in (
            (operation_id, "operation_id"),
            (owner_google_subject, "owner_google_subject"),
            (firebase_uid, "firebase_uid"),
            (project_id, "project_id"),
            (workspace_id, "workspace_id"),
            (namespace, "namespace"),
        ):
            _safe_id(value, name)
        descriptor_json, payload_json = _json(descriptor), _json(payload)
        descriptor_hash = hashlib.sha256(descriptor_json.encode()).hexdigest()
        instruction = {
            "version": 1,
            "sdk": "firebase/firestore/lite",
            "operation_id": operation_id,
            "namespace": namespace,
            "owner_google_subject": owner_google_subject,
            "firebase_uid": firebase_uid,
            "project_id": project_id,
            "workspace_id": workspace_id,
            "session_id": descriptor.get("session_id"),
            "descriptor_hash": descriptor_hash,
            "descriptor": json.loads(descriptor_json),
            "payload": json.loads(payload_json),
            "bounds": {"max_documents": 500, "max_bytes": 1_000_000},
        }
        # Keep the SDK call shape directly inspectable by the browser while
        # retaining the complete immutable payload for reconciliation.
        instruction.update(json.loads(payload_json))
        instruction["payload_hash"] = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        instruction_json = _json(instruction)
        if len(instruction_json.encode("utf-8")) > self.max_instruction_bytes:
            raise ValueError("browser instruction exceeds its byte bound")
        method = instruction.get("method")
        if method == "writeBatch":
            writes = instruction.get("writes")
            if not isinstance(writes, list) or len(writes) > self.max_instruction_documents:
                raise ValueError("browser instruction exceeds its document bound")
        elif method == "getDoc":
            if not isinstance(instruction.get("path"), str):
                raise ValueError("read instruction has no document path")
        else:
            raise ValueError("unsupported browser instruction method")
        with self._lock:
            # BEGIN IMMEDIATE makes the read/insert decision atomic across
            # separate Outbox instances as well as concurrent threads.
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if row is not None:
                    if (
                        row["descriptor_hash"] != descriptor_hash
                        or row["payload"] != payload_json
                        or row["owner_google_subject"] != owner_google_subject
                        or row["firebase_uid"] != firebase_uid
                    ):
                        raise OutboxConflict("operation descriptor or owner changed")
                    if row["state"] != OperationState.PENDING:
                        raise ValueError("operation outcome is unknown or already acknowledged")
                    self._db.execute("COMMIT")
                    return self._operation(row, released=False)
                now = _now()
                self._db.execute(
                    "INSERT INTO browser_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        operation_id,
                        owner_google_subject,
                        firebase_uid,
                        project_id,
                        workspace_id,
                        namespace,
                        descriptor_hash,
                        descriptor_json,
                        payload_json,
                        instruction_json,
                        OperationState.PENDING,
                        None,
                        None,
                        None,
                        now,
                        now,
                    ),
                )
                row = self._db.execute(
                    "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                assert row is not None
                self._db.execute("COMMIT")
                return self._operation(row, released=True)
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def _operation(self, row: sqlite3.Row, *, released: bool = False) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            owner_google_subject=row["owner_google_subject"],
            firebase_uid=row["firebase_uid"],
            project_id=row["project_id"],
            workspace_id=row["workspace_id"],
            namespace=row["namespace"],
            descriptor_hash=row["descriptor_hash"],
            descriptor=json.loads(row["descriptor"]),
            payload=json.loads(row["payload"]),
            instruction=json.loads(row["instruction"]),
            state=OperationState(row["state"]),
            ack_id=row["ack_id"],
            ack=json.loads(row["ack"]) if row["ack"] else None,
            last_error=row["last_error"],
            released=released,
        )

    def get_instruction(self, operation_id: str) -> OperationRecord:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(operation_id)
        return self._operation(row)

    def recovery_operations(
        self,
        *,
        owner_google_subject: str,
        firebase_uid: str,
        project_id: str,
        workspace_id: str,
    ) -> tuple[OperationRecord, ...]:
        """Return durable unknown operations for one verified local owner.

        This is a local lookup only. It never performs a remote read or changes
        an operation's state; reconciliation still requires a fresh consent.
        """
        for value, name in (
            (owner_google_subject, "owner_google_subject"),
            (firebase_uid, "firebase_uid"),
            (project_id, "project_id"),
            (workspace_id, "workspace_id"),
        ):
            _safe_id(value, name)
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM browser_operations WHERE state=? AND owner_google_subject=? "
                "AND firebase_uid=? AND project_id=? AND workspace_id=? ORDER BY updated_at",
                (
                    OperationState.UNKNOWN,
                    owner_google_subject,
                    firebase_uid,
                    project_id,
                    workspace_id,
                ),
            ).fetchall()
        return tuple(self._operation(row) for row in rows)

    def acknowledge_instruction(
        self,
        operation_id: str,
        *,
        descriptor_hash: str,
        owner_google_subject: str,
        firebase_uid: str,
        ack_id: str,
        ack: Mapping[str, Any] | None = None,
    ) -> OperationRecord:
        _safe_id(ack_id, "ack_id")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            if (
                row["descriptor_hash"] != descriptor_hash
                or row["owner_google_subject"] != owner_google_subject
                or row["firebase_uid"] != firebase_uid
            ):
                raise OutboxConflict("acknowledgement identity or descriptor mismatch")
            if row["state"] != OperationState.PENDING:
                raise ValueError("operation is not awaiting acknowledgement")
            payload = _json(ack or {"ack_id": ack_id})
            self._db.execute(
                "UPDATE browser_operations SET state=?, ack_id=?, ack=?, updated_at=? WHERE operation_id=? AND state=?",  # noqa: E501
                (
                    OperationState.ACKNOWLEDGED,
                    ack_id,
                    payload,
                    _now(),
                    operation_id,
                    OperationState.PENDING,
                ),
            )
            updated = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            assert updated is not None
            return self._operation(updated)

    def acknowledge_reconciled(
        self,
        operation_id: str,
        *,
        descriptor_hash: str,
        owner_google_subject: str,
        firebase_uid: str,
        ack_id: str,
        ack: Mapping[str, Any] | None = None,
    ) -> OperationRecord:
        """Atomically resolve one previously unknown operation from exact evidence."""
        _safe_id(ack_id, "ack_id")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            if (
                row["descriptor_hash"] != descriptor_hash
                or row["owner_google_subject"] != owner_google_subject
                or row["firebase_uid"] != firebase_uid
            ):
                raise OutboxConflict("reconciliation identity or descriptor mismatch")
            if row["state"] == OperationState.ACKNOWLEDGED:
                return self._operation(row)
            if row["state"] != OperationState.UNKNOWN:
                raise ValueError("only unknown operations can be reconciled")
            self._db.execute(
                "UPDATE browser_operations SET state=?, ack_id=?, ack=?, last_error=NULL, "
                "updated_at=? WHERE operation_id=? AND state=?",
                (
                    OperationState.ACKNOWLEDGED,
                    ack_id,
                    _json(ack or {"ack_id": ack_id, "reconciled": True}),
                    _now(),
                    operation_id,
                    OperationState.UNKNOWN,
                ),
            )
            updated = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            assert updated is not None
            return self._operation(updated)

    def mark_operation_unknown(
        self, operation_id: str, error: str = "browser acknowledgement is unknown"
    ) -> OperationRecord:
        if not error or len(error) > 500:
            raise ValueError("unknown outcome must include a bounded error")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            if row["state"] == OperationState.ACKNOWLEDGED:
                return self._operation(row)
            self._db.execute(
                "UPDATE browser_operations SET state=?, last_error=?, updated_at=? WHERE operation_id=?",  # noqa: E501
                (OperationState.UNKNOWN, error, _now(), operation_id),
            )
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            assert row is not None
            return self._operation(row)

    def mark_operation_conflict(self, operation_id: str, error: str) -> OperationRecord:
        if not error or len(error) > 500:
            raise ValueError("conflict outcome must include a bounded error")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            if row["state"] == OperationState.ACKNOWLEDGED:
                return self._operation(row)
            self._db.execute(
                "UPDATE browser_operations SET state=?, last_error=?, updated_at=? WHERE operation_id=?",  # noqa: E501
                (OperationState.CONFLICT, error, _now(), operation_id),
            )
            row = self._db.execute(
                "SELECT * FROM browser_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            assert row is not None
            return self._operation(row)

    def import_history_event(
        self,
        event: ActivityEvent,
        *,
        owner_google_subject: str,
        origin: str = "cloud",
    ) -> ImportedHistoryRecord:
        """Durably record cloud history evidence without queueing outgoing work."""
        if not isinstance(event, ActivityEvent):
            raise TypeError("imported history must be an ActivityEvent")
        _safe_id(owner_google_subject, "owner_google_subject")
        _safe_id(origin, "origin")
        payload = _json(event.to_dict())
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM imported_history WHERE event_id=?", (event.event_id,)
            ).fetchone()
            if row is not None:
                if row["content_hash"] != event.content_hash or row["payload"] != payload:
                    raise OutboxConflict("imported history event changed content")
                return ImportedHistoryRecord(
                    event.event_id, event, row["owner_google_subject"], row["origin"]
                )
            self._db.execute(
                "INSERT INTO imported_history VALUES(?,?,?,?,?,?)",
                (event.event_id, payload, event.content_hash, owner_google_subject, origin, _now()),
            )
        return ImportedHistoryRecord(event.event_id, event, owner_google_subject, origin)

    def import_history_events(
        self,
        events: Iterable[ActivityEvent],
        *,
        owner_google_subject: str,
        origin: str = "cloud",
    ) -> tuple[ImportedHistoryRecord, ...]:
        values = tuple(events)
        if not values or len(values) > self.max_events:
            raise ValueError("imported history batch exceeds configured bound")
        if len({event.event_id for event in values}) != len(values):
            raise OutboxConflict("duplicate imported event ID in batch")
        _safe_id(owner_google_subject, "owner_google_subject")
        _safe_id(origin, "origin")
        rows = [(event, _json(event.to_dict())) for event in values]
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                result: list[ImportedHistoryRecord] = []
                for event, payload in rows:
                    row = self._db.execute(
                        "SELECT * FROM imported_history WHERE event_id=?", (event.event_id,)
                    ).fetchone()
                    if row is not None:
                        if row["content_hash"] != event.content_hash or row["payload"] != payload:
                            raise OutboxConflict("imported history event changed content")
                        result.append(
                            ImportedHistoryRecord(
                                event.event_id, event, row["owner_google_subject"], row["origin"]
                            )
                        )
                        continue
                    self._db.execute(
                        "INSERT INTO imported_history VALUES(?,?,?,?,?,?)",
                        (
                            event.event_id,
                            payload,
                            event.content_hash,
                            owner_google_subject,
                            origin,
                            _now(),
                        ),
                    )
                    result.append(
                        ImportedHistoryRecord(event.event_id, event, owner_google_subject, origin)
                    )
                self._db.execute("COMMIT")
                return tuple(result)
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def imported_history(self, event_id: str) -> ImportedHistoryRecord:
        _safe_id(event_id, "event_id")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM imported_history WHERE event_id=?", (event_id,)
            ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return ImportedHistoryRecord(
            event_id=row["event_id"],
            event=ActivityEvent.from_dict(json.loads(row["payload"])),
            owner_google_subject=row["owner_google_subject"],
            origin=row["origin"],
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Outbox:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "ImportedHistoryRecord",
    "OperationRecord",
    "OperationState",
    "Outbox",
    "OutboxConflict",
    "OutboxRecord",
    "OutboxState",
]
