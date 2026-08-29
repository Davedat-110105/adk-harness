"""Append-only Firestore storage for governed action executions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

__all__ = ["EvidenceConflict", "FirestoreActionLedger"]

DEFAULT_DENYLIST = (
    "password",
    "token",
    "secret",
    "api_key",
    "credential",
    "authorization",
)


class EvidenceConflict(RuntimeError):
    """An idempotency key was reused with different immutable evidence."""


class FirestoreActionLedger:
    """Persist governed actions as immutable, retry-safe Firestore entries.

    Entries are append-only by design: this preserves historical execution
    evidence when an agent or policy version is disabled. The class exposes no
    update or delete method, and writes use Firestore ``create`` so an existing
    idempotency key cannot be overwritten.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        collection: str = "action_ledger",
        evidence_collection: str = "policy_evidence",
        owner_namespace: str | None = None,
        denylist: Iterable[str] = DEFAULT_DENYLIST,
        arg_allowlist: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        """Configure append-only storage.

        ``arg_allowlist`` maps action names to top-level argument keys that are
        explicitly safe to retain. With no allowlist, argument values are not
        persisted; ``input_hash`` remains available for correlation without
        exposing the request payload.
        """
        self._firestore_client = client
        self._collection_name = collection
        self._evidence_collection_name = evidence_collection
        self._owner_namespace = owner_namespace
        self._denylist = tuple(item.casefold() for item in denylist)
        self._arg_allowlist = {
            action: frozenset(keys) for action, keys in (arg_allowlist or {}).items()
        }

    def record(
        self,
        *,
        actor: str,
        agent: str,
        action: str,
        resource: str,
        scope: Any,
        policy_outcome: Any,
        policy_reason: str | None,
        tool_args: Mapping[str, Any],
        outcome: Any,
        idempotency_key: str,
    ) -> str:
        """Create one action entry and return its stable Firestore document ID.

        Reusing ``idempotency_key`` is treated as a retry of the same execution.
        Callers must provide a fresh key for each distinct execution.
        """
        input_hash = _input_hash(tool_args)
        entry_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        payload = {
            "idempotency_key": idempotency_key,
            "actor": actor,
            "agent": agent,
            "action": action,
            "resource": resource,
            "scope": scope,
            "policy_outcome": policy_outcome,
            "policy_reason": policy_reason,
            "input_hash": input_hash,
            # Arguments are metadata-only unless the caller explicitly names
            # safe top-level fields for this action. A denylist cannot reliably
            # identify secrets in arbitrary strings, lists, or nested payloads.
            "tool_args_redacted": _allowed_args(
                tool_args,
                self._arg_allowlist.get(action, ()),
                self._denylist,
            ),
            "outcome": outcome,
            "recorded_at": datetime.now(UTC),
        }

        document = self._collection().document(entry_id)
        try:
            document.create(payload)
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
            if not document.get().exists:
                raise RuntimeError(
                    f"Firestore reported an existing action entry for {idempotency_key!r}, "
                    "but it could not be read back"
                ) from exc
        return entry_id

    def query(self, *, scope: Any, limit: int = 100) -> list[dict[str, Any]]:
        """Return at most ``limit`` entries for ``scope``, newest first."""
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        entries = (
            self._collection()
            .where("scope", "==", scope)
            .order_by("recorded_at", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [{"id": snapshot.id, **(snapshot.to_dict() or {})} for snapshot in entries]

    def record_evidence(
        self,
        *,
        actor: str,
        approval_hash: str,
        policy_version: str,
        decision: str,
        operation_id: str,
        outcome: str,
        idempotency_key: str,
        trace_id: str,
    ) -> str:
        """Write unsampled immutable policy evidence.

        This path requires an injected, explicitly configured runtime client
        and owner namespace. Retries with byte-for-byte identical immutable
        fields succeed; a conflicting reuse is surfaced for reconciliation.
        """
        if self._firestore_client is None:
            raise RuntimeError("policy evidence requires an explicit runtime Firestore client")
        if not self._owner_namespace:
            raise ValueError("policy evidence requires an explicit owner namespace")
        for name, value in {
            "actor": actor,
            "policy_version": policy_version,
            "decision": decision,
            "operation_id": operation_id,
            "outcome": outcome,
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
        }.items():
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError(f"{name} must be a bounded non-empty string")
        if not isinstance(approval_hash, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", approval_hash
        ):
            raise ValueError("approval_hash must be a SHA-256 hexadecimal digest")
        if decision not in {"allow", "deny", "hold"}:
            raise ValueError("decision must be allow, deny, or hold")
        immutable = {
            "kind": "policy_evidence",
            "owner_namespace": self._owner_namespace,
            "idempotency_key": idempotency_key,
            "actor": actor,
            "approval_hash": approval_hash.lower(),
            "policy_version": policy_version,
            "decision": decision,
            "operation_id": operation_id,
            "outcome": outcome,
            "trace_id": trace_id,
        }
        payload: dict[str, Any] = dict(immutable)
        payload["recorded_at"] = datetime.now(UTC)
        entry_id = hashlib.sha256(
            ("policy-evidence:" + self._owner_namespace + ":" + idempotency_key).encode("utf-8")
        ).hexdigest()
        document = self._client().collection(self._evidence_collection_name).document(entry_id)
        try:
            document.create(payload)
        except Exception as exc:
            if not _is_already_exists(exc):
                raise
            snapshot = document.get()
            if not snapshot.exists:
                raise RuntimeError("existing policy evidence could not be read back") from exc
            existing = snapshot.to_dict() or {}
            existing_immutable = {
                key: value for key, value in existing.items() if key != "recorded_at"
            }
            if existing_immutable != immutable:
                raise EvidenceConflict(
                    f"conflicting policy evidence for idempotency key {idempotency_key!r}"
                ) from exc
        return entry_id

    def _collection(self) -> Any:
        return self._client().collection(self._collection_name)

    def _client(self) -> Any:
        if self._firestore_client is not None:
            return self._firestore_client
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-firestore is required for FirestoreActionLedger"
            ) from exc
        try:
            self._firestore_client = firestore.Client()
        except Exception as exc:
            raise RuntimeError(
                "Could not initialize FirestoreActionLedger; configure Google "
                "Cloud credentials and a Firestore project"
            ) from exc
        return self._firestore_client


def _input_hash(tool_args: Mapping[str, Any]) -> str:
    try:
        canonical = json.dumps(
            tool_args,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("tool_args must contain only canonical JSON values") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redact(value: Any, denylist: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _redact(item, denylist)
            for key, item in value.items()
            if not isinstance(key, str) or not any(term in key.casefold() for term in denylist)
        }
    if isinstance(value, list):
        return [_redact(item, denylist) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, denylist) for item in value]
    return value


def _allowed_args(
    tool_args: Mapping[str, Any],
    allowed_keys: Iterable[str],
    denylist: tuple[str, ...],
) -> dict[str, Any]:
    allowed = set(allowed_keys)
    return {
        key: _redact(value, denylist)
        for key, value in tool_args.items()
        if isinstance(key, str)
        and key in allowed
        and not any(term in key.casefold() for term in denylist)
    }


def _is_already_exists(exc: Exception) -> bool:
    return exc.__class__.__name__ == "AlreadyExists" or getattr(exc, "code", None) in {
        6,
        "ALREADY_EXISTS",
    }
