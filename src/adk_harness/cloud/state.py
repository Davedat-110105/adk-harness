"""Durable execution claims and checkpoints.

The in-memory implementation is intentionally useful for offline tests.  The
Firestore implementation is a thin official SDK adapter; callers persist a
claim before dispatching a Cloud Run Job and never treat an expired lease as
proof that an external operation did not happen.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class WorkStatus(StrEnum):
    CLAIMED = "claimed"
    DUPLICATE = "duplicate"
    RUNNING = "running"
    COMPLETED = "completed"
    HELD = "held"
    BLOCKED = "blocked"
    FAILED = "failed"
    RECONCILING = "reconciling"


@dataclass(frozen=True, slots=True)
class WorkRecord:
    task_id: str
    request_id: str
    trace_id: str
    status: WorkStatus
    lease_until: datetime
    checkpoint: int = 0
    operation_id: str | None = None
    dispatch_operation: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class InMemoryExecutionStore:
    """Thread-safe deterministic store used by synthetic tests and local runs."""

    def __init__(self, *, lease_seconds: int = 300) -> None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        self.lease_seconds = lease_seconds
        self._records: dict[str, WorkRecord] = {}
        self._lock = threading.RLock()

    def claim(self, *, task_id: str, request_id: str, trace_id: str) -> WorkRecord:
        self._validate(task_id, "task_id")
        self._validate(request_id, "request_id")
        self._validate(trace_id, "trace_id")
        with self._lock:
            existing = self._records.get(task_id)
            if existing is not None:
                return WorkRecord(
                    task_id=existing.task_id,
                    request_id=existing.request_id,
                    trace_id=existing.trace_id,
                    status=WorkStatus.DUPLICATE,
                    lease_until=existing.lease_until,
                    checkpoint=existing.checkpoint,
                    operation_id=existing.operation_id,
                    result=existing.result,
                    error=existing.error,
                )
            record = WorkRecord(
                task_id=task_id,
                request_id=request_id,
                trace_id=trace_id,
                status=WorkStatus.CLAIMED,
                lease_until=datetime.now(UTC) + timedelta(seconds=self.lease_seconds),
            )
            self._records[task_id] = record
            return record

    def get(self, task_id: str) -> WorkRecord:
        with self._lock:
            try:
                return self._records[task_id]
            except KeyError:
                raise KeyError(task_id) from None

    def update(
        self,
        task_id: str,
        *,
        status: WorkStatus | None = None,
        checkpoint: int | None = None,
        operation_id: str | None = None,
        dispatch_operation: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> WorkRecord:
        with self._lock:
            current = self.get(task_id)
            record = WorkRecord(
                task_id=current.task_id,
                request_id=current.request_id,
                trace_id=current.trace_id,
                status=status or current.status,
                lease_until=current.lease_until,
                checkpoint=current.checkpoint if checkpoint is None else checkpoint,
                operation_id=operation_id if operation_id is not None else current.operation_id,
                dispatch_operation=(
                    dispatch_operation
                    if dispatch_operation is not None
                    else current.dispatch_operation
                ),
                result=result if result is not None else current.result,
                error=error if error is not None else current.error,
            )
            self._records[task_id] = record
            return record

    def reserve(self, task_id: str, *, operation_id: str, checkpoint: int) -> bool:
        """Compare and set one action reservation under the store lock."""
        with self._lock:
            current = self.get(task_id)
            if current.checkpoint != checkpoint:
                return False
            if current.operation_id and not str(current.operation_id).startswith("dispatch:"):
                return False
            self._records[task_id] = WorkRecord(
                task_id=current.task_id, request_id=current.request_id,
                trace_id=current.trace_id, status=WorkStatus.RUNNING,
                lease_until=current.lease_until, checkpoint=checkpoint,
                operation_id=operation_id, dispatch_operation=current.dispatch_operation,
                result=current.result, error=current.error,
            )
            return True

    @staticmethod
    def _validate(value: str, name: str) -> None:
        if not isinstance(value, str) or not value or "/" in value:
            raise ValueError(f"{name} is invalid")


class FirestoreExecutionStore:
    """Official google-cloud-firestore adapter for worker state."""

    def __init__(self, client: Any, *, collection: str = "execution") -> None:
        self.client = client
        self.collection = collection

    def _ref(self, task_id: str) -> Any:
        if not isinstance(task_id, str) or not task_id or "/" in task_id:
            raise ValueError("task_id is invalid")
        return self.client.collection(self.collection).document(task_id)

    def claim(self, *, task_id: str, request_id: str, trace_id: str) -> WorkRecord:
        from google.cloud import firestore

        ref = self._ref(task_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def claim_once(tx: Any) -> dict[str, Any]:
            snapshot = ref.get(transaction=tx)
            if snapshot.exists:
                return {"_existing": True, **dict(snapshot.to_dict() or {})}
            now = datetime.now(UTC)
            payload = {
                "task_id": task_id,
                "request_id": request_id,
                "trace_id": trace_id,
                "status": WorkStatus.CLAIMED.value,
                "lease_until": now + timedelta(minutes=5),
                "checkpoint": 0,
            }
            tx.create(ref, payload)
            return payload

        payload = claim_once(transaction)
        status = (
            WorkStatus.DUPLICATE
            if payload.pop("_existing", False)
            else WorkStatus(payload["status"])
        )
        return WorkRecord(
            task_id=str(payload["task_id"]),
            request_id=str(payload["request_id"]),
            trace_id=str(payload["trace_id"]),
            status=status,
            lease_until=payload["lease_until"],
            checkpoint=int(payload.get("checkpoint", 0)),
            operation_id=payload.get("operation_id"),
            dispatch_operation=payload.get("dispatch_operation"),
            result=payload.get("result"),
            error=payload.get("error"),
        )

    def get(self, task_id: str) -> WorkRecord:
        snap = self._ref(task_id).get()
        if not snap.exists:
            raise KeyError(task_id)
        payload = snap.to_dict() or {}
        return WorkRecord(
            task_id=str(payload["task_id"]),
            request_id=str(payload["request_id"]),
            trace_id=str(payload["trace_id"]),
            status=WorkStatus(payload["status"]),
            lease_until=payload["lease_until"],
            checkpoint=int(payload.get("checkpoint", 0)),
            operation_id=payload.get("operation_id"),
            dispatch_operation=payload.get("dispatch_operation"),
            result=payload.get("result"),
            error=payload.get("error"),
        )

    def update(self, task_id: str, **changes: Any) -> WorkRecord:
        allowed = {"status", "checkpoint", "operation_id", "dispatch_operation", "result", "error"}
        if set(changes) - allowed:
            raise ValueError("unsupported execution state field")
        if "status" in changes:
            changes["status"] = WorkStatus(changes["status"]).value
        self._ref(task_id).update(changes)
        return self.get(task_id)

    def reserve(self, task_id: str, *, operation_id: str, checkpoint: int) -> bool:
        from google.cloud import firestore

        ref = self._ref(task_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def reserve_once(tx: Any) -> bool:
            snapshot = ref.get(transaction=tx)
            if not snapshot.exists:
                return False
            payload = snapshot.to_dict() or {}
            existing = payload.get("operation_id")
            if (
                int(payload.get("checkpoint", 0)) != checkpoint
                or (existing and not str(existing).startswith("dispatch:"))
            ):
                return False
            tx.update(ref, {"status": WorkStatus.RUNNING.value, "operation_id": operation_id})
            return True

        return bool(reserve_once(transaction))


__all__ = ["FirestoreExecutionStore", "InMemoryExecutionStore", "WorkRecord", "WorkStatus"]
