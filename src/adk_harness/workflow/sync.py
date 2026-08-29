"""Finite, consent-gated local workflow for Firebase Lite operations.

Python prepares and durably records immutable descriptors. It never calls a
Firebase or server SDK. The trusted browser receives the returned instruction,
performs the official Lite read/write, and posts a bounded acknowledgement.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

import rfc8785

from .approvals import (
    ApprovalBinding,
    ApprovalEnvelope,
    ApprovalError,
    create_approval,
    verify_approval,
)
from .models import ActivityEvent, ChangeSet, TaskRequest
from .outbox import OperationRecord, OperationState, Outbox, OutboxConflict


class SyncRejected(PermissionError):
    """The local gate refused an operation before any browser SDK call."""


class SyncOutcome(StrEnum):
    INSTRUCTION_READY = "instruction_ready"
    ACKNOWLEDGED = "acknowledged"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class SyncResult:
    outcome: SyncOutcome
    event_ids: tuple[str, ...] = ()
    ack_id: str | None = None
    error: str | None = None
    operation_id: str | None = None
    instruction: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    """Trusted, host supplied workflow namespace and database configuration."""

    project_id: str
    workspace_id: str
    control_database_id: str
    runtime_database_id: str
    session_id: str
    session_expires_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "project_id",
            "workspace_id",
            "control_database_id",
            "runtime_database_id",
            "session_id",
        ):
            _id(getattr(self, name), name)
        object.__setattr__(self, "session_expires_at", _utc(self.session_expires_at))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> WorkflowConfig:
        def pick(snake: str, camel: str) -> Any:
            if snake in value:
                selected = value[snake]
            elif camel in value:
                selected = value[camel]
            else:
                raise ValueError(f"workflow configuration is missing {snake}")
            if selected is None:
                raise ValueError(f"workflow configuration field {snake} is null")
            return selected

        expiry = pick("session_expires_at", "sessionExpiresAt")
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)
        return cls(
            project_id=pick("project_id", "projectId"),
            workspace_id=pick("workspace_id", "workspaceId"),
            control_database_id=pick("control_database_id", "controlDatabaseId"),
            runtime_database_id=pick("runtime_database_id", "runtimeDatabaseId"),
            session_id=pick("session_id", "sessionId"),
            session_expires_at=expiry,
        )


@dataclass(frozen=True, slots=True)
class ManifestReadConsent:
    project_id: str
    workspace_id: str
    google_subject: str
    firebase_uid: str
    task_id: str
    fields: tuple[str, ...]
    expires_at: datetime
    session_id: str
    attempt_id: str = dataclass_field(default_factory=lambda: uuid4().hex)

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": "bounded_manifest_read",
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "google_subject": self.google_subject,
            "firebase_uid": self.firebase_uid,
            "task_id": self.task_id,
            "path": _runtime_manifest_path(
                self.project_id, self.workspace_id, self.firebase_uid, self.task_id
            ),
            "fields": list(self.fields),
            "session_id": self.session_id,
            "attempt_id": self.attempt_id,
            "expires_at": _utc(self.expires_at).isoformat(),
        }

    @property
    def descriptor_hash(self) -> str:
        return _hash(self.descriptor)


@dataclass(frozen=True, slots=True)
class DownloadConsent:
    metadata_descriptor_hash: str
    result_id: str
    result_hash: str
    scope: tuple[str, ...]
    project_id: str
    workspace_id: str
    google_subject: str
    firebase_uid: str
    task_id: str
    expires_at: datetime
    session_id: str

    @classmethod
    def from_manifest(
        cls, metadata: ManifestReadConsent, manifest: Mapping[str, Any], *, scope: Sequence[str]
    ) -> DownloadConsent:
        result_id = manifest.get("result_id")
        result_hash = manifest.get("result_hash")
        listed_scope = manifest.get("scope")
        selected = tuple(scope)
        if (
            not isinstance(result_id, str)
            or not isinstance(result_hash, str)
            or not _is_digest(result_hash)
        ):
            raise SyncRejected("manifest does not contain a valid result digest")
        if (
            not isinstance(listed_scope, (list, tuple))
            or not selected
            or len(set(listed_scope)) != len(listed_scope)
            or len(set(selected)) != len(selected)
            or tuple(selected) != tuple(listed_scope)
        ):
            raise SyncRejected("manifest does not bind the requested download scope")
        return cls(
            metadata_descriptor_hash=metadata.descriptor_hash,
            result_id=_id(result_id, "result_id"),
            result_hash=result_hash.lower(),
            scope=selected,
            project_id=metadata.project_id,
            workspace_id=metadata.workspace_id,
            google_subject=metadata.google_subject,
            firebase_uid=metadata.firebase_uid,
            task_id=metadata.task_id,
            expires_at=metadata.expires_at,
            session_id=metadata.session_id,
        )


@dataclass(frozen=True, slots=True)
class ReconciliationReadConsent:
    target_operation_id: str
    target_descriptor_hash: str
    project_id: str
    workspace_id: str
    google_subject: str
    firebase_uid: str
    task_id: str
    paths: tuple[str, ...]
    database: str
    expires_at: datetime
    session_id: str

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": "reconciliation_read",
            "target_operation_id": self.target_operation_id,
            "target_descriptor_hash": self.target_descriptor_hash,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "google_subject": self.google_subject,
            "firebase_uid": self.firebase_uid,
            "task_id": self.task_id,
            "paths": list(self.paths),
            "database": self.database,
            "session_id": self.session_id,
            "expires_at": _utc(self.expires_at).isoformat(),
        }

    @property
    def descriptor_hash(self) -> str:
        return _hash(self.descriptor)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SyncRejected("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."} or "/" in value:
        raise SyncRejected(f"{name} is not a valid document ID")
    return value


def _is_digest(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _native_timestamp(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"type", "seconds", "nanoseconds"}
        and value.get("type") == "firestore/timestamp/1.0"
        and isinstance(value.get("seconds"), int)
        and not isinstance(value.get("seconds"), bool)
        and isinstance(value.get("nanoseconds"), int)
        and not isinstance(value.get("nanoseconds"), bool)
        and 0 <= value["nanoseconds"] < 1_000_000_000
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(_plain(value))).hexdigest()


def _canonical_payload(value: Mapping[str, Any]) -> str:
    return rfc8785.dumps(_plain(value)).decode("utf-8")


def _validate_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the one shared, typed result payload shape."""
    if not isinstance(payload, Mapping):
        raise SyncRejected("runtime result payload is malformed")
    common = {
        "kind",
        "project_id",
        "workspace_id",
        "firebase_uid",
        "google_subject",
        "task_id",
        "scope",
        "expires_at",
    }
    kind = payload.get("kind")
    if kind == "history_result":
        allowed = common | {"events"}
        if set(payload) != allowed or not isinstance(payload.get("events"), (list, tuple)):
            raise SyncRejected("history result payload schema is incomplete")
        if not payload["events"]:
            raise SyncRejected("history result payload contains no events")
        for item in payload["events"]:
            try:
                event = ActivityEvent.from_dict(item)
            except (TypeError, ValueError) as exc:
                raise SyncRejected("history result payload contains an invalid event") from exc
            if (
                event.project_id != payload["project_id"]
                or event.workspace_id != payload["workspace_id"]
                or event.task_id != payload["task_id"]
            ):
                raise SyncRejected("history result event owner or task mismatch")
    elif kind == "changeset_result":
        allowed = common | {"changeset"}
        if set(payload) != allowed or not isinstance(payload.get("changeset"), Mapping):
            raise SyncRejected("changeset result payload schema is incomplete")
        try:
            changeset = ChangeSet.from_dict(payload["changeset"])
        except (TypeError, ValueError) as exc:
            raise SyncRejected("changeset result payload is not a valid ChangeSet") from exc
        if (
            changeset.project_id != payload["project_id"]
            or changeset.workspace_id != payload["workspace_id"]
            or changeset.task_id != payload["task_id"]
            or changeset.user_id != payload["google_subject"]
        ):
            raise SyncRejected("changeset result owner or task mismatch")
    else:
        raise SyncRejected("runtime result kind is unknown")
    scope = payload.get("scope")
    if (
        not isinstance(scope, (list, tuple))
        or not scope
        or any(not isinstance(item, str) or not item for item in scope)
        or len(set(scope)) != len(scope)
    ):
        raise SyncRejected("runtime result scope is malformed")
    identity_fields = ("project_id", "workspace_id", "firebase_uid", "google_subject", "task_id")
    if any(not isinstance(payload.get(name), str) for name in identity_fields):
        raise SyncRejected("runtime result owner fields are malformed")
    for name in identity_fields:
        _id(payload[name], name)
    try:
        _utc(datetime.fromisoformat(str(payload["expires_at"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise SyncRejected("runtime result expiry is malformed") from exc
    return dict(payload)


def make_result_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the non-circular result envelope shared with the browser/Rules."""
    payload = _validate_result_payload(payload)
    canonical = _canonical_payload(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    value: dict[str, Any] = {
        "schema_version": 1,
        "result_id": digest,
        "result_hash": digest,
        "payload": _plain(payload),
        "canonical_payload": canonical,
    }
    expiry = _utc(datetime.fromisoformat(str(payload["expires_at"])))
    value["expires_at_ts"] = _timestamp_mirror(expiry)
    return value


def _timestamp_mirror(value: datetime) -> dict[str, Any]:
    value = _utc(value)
    seconds = int(value.timestamp())
    return {
        "type": "firestore/timestamp/1.0",
        "seconds": seconds,
        "nanoseconds": value.microsecond * 1000,
    }


def make_runtime_manifest(
    *,
    project_id: str,
    workspace_id: str,
    firebase_uid: str,
    google_subject: str,
    task_id: str,
    scope: Sequence[str],
    payload: Mapping[str, Any],
    expires_at: datetime,
) -> dict[str, Any]:
    """Create a valid digest addressed manifest fixture for boundary tests."""
    if (
        not scope
        or len(scope) > 20
        or any(not isinstance(item, str) or not item or len(item) > 100 for item in scope)
    ):
        raise SyncRejected("manifest scope exceeds its bound")
    if not isinstance(payload, Mapping):
        raise SyncRejected("manifest payload must be a complete result payload")
    expected_payload = {
        "kind": payload.get("kind"),
        "project_id": payload.get("project_id"),
        "workspace_id": payload.get("workspace_id"),
        "firebase_uid": payload.get("firebase_uid"),
        "google_subject": payload.get("google_subject"),
        "task_id": payload.get("task_id"),
        "scope": payload.get("scope"),
        "expires_at": payload.get("expires_at"),
    }
    if (
        expected_payload["kind"] not in {"history_result", "changeset_result"}
        or expected_payload["project_id"] != project_id
        or expected_payload["workspace_id"] != workspace_id
        or expected_payload["firebase_uid"] != firebase_uid
        or expected_payload["google_subject"] != google_subject
        or expected_payload["task_id"] != task_id
        or expected_payload["scope"] != list(scope)
        or expected_payload["expires_at"] != _utc(expires_at).isoformat()
    ):
        raise SyncRejected("manifest payload does not match its owner and scope")
    envelope = make_result_envelope(payload)
    expiry = _utc(expires_at)
    return {
        "schema_version": 1,
        "kind": "manifest",
        "result_id": envelope["result_id"],
        "result_hash": envelope["result_hash"],
        "scope": list(scope),
        "project_id": _id(project_id, "project_id"),
        "workspace_id": _id(workspace_id, "workspace_id"),
        "firebase_uid": _id(firebase_uid, "firebase_uid"),
        "google_subject": _id(google_subject, "google_subject"),
        "task_id": _id(task_id, "task_id"),
        "available": True,
        "expires_at": expiry.isoformat(),
        "expires_at_ts": _timestamp_mirror(expiry),
    }


def _control_prefix(project: str, workspace: str, uid: str) -> str:
    return (
        f"projects/{_id(project, 'project_id')}/"
        f"workspaces/{_id(workspace, 'workspace_id')}/"
        f"members/{_id(uid, 'firebase_uid')}"
    )


def _runtime_prefix(project: str, workspace: str, uid: str, task: str) -> str:
    return (
        f"projects/{_id(project, 'project_id')}/"
        f"workspaces/{_id(workspace, 'workspace_id')}/"
        f"users/{_id(uid, 'firebase_uid')}/tasks/{_id(task, 'task_id')}"
    )


def _runtime_manifest_path(project: str, workspace: str, uid: str, task: str) -> str:
    return f"{_runtime_prefix(project, workspace, uid, task)}/manifests/latest"


def _record_instruction(
    outbox: Outbox,
    *,
    operation_id: str,
    owner: str,
    uid: str,
    project: str,
    workspace: str,
    namespace: str,
    descriptor: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> OperationRecord:
    try:
        return outbox.claim_instruction(
            operation_id=operation_id,
            owner_google_subject=owner,
            firebase_uid=uid,
            project_id=project,
            workspace_id=workspace,
            namespace=namespace,
            descriptor=descriptor,
            payload=payload,
        )
    except (OutboxConflict, ValueError) as exc:
        raise SyncRejected(
            "operation is already recorded with a different or unresolved descriptor"
        ) from exc


class SyncEngine:
    """Local workflow state machine; ``cloud`` is retained only for API compatibility."""

    def __init__(
        self,
        outbox: Outbox,
        *,
        workflow_config: WorkflowConfig | Mapping[str, Any] | None = None,
    ) -> None:
        self.outbox = outbox
        if isinstance(workflow_config, Mapping):
            workflow_config = WorkflowConfig.from_mapping(workflow_config)
        self.workflow_config = workflow_config
        # Keep a bounded set of immutable previews.  Consent selects by its
        # exact operation/hash; a later preview must never replace an earlier
        # preview that is awaiting human consent.
        self._history_previews: dict[str, tuple[tuple[ActivityEvent, ...], ApprovalBinding]] = {}
        self._latest_history_operation: str | None = None
        self._history_operation: str | None = None
        self._manifest_consents: dict[str, ManifestReadConsent] = {}
        self._manifests: dict[str, dict[str, Any]] = {}
        self._reconciliation_previews: dict[str, ReconciliationReadConsent] = {}
        # Compatibility aliases for callers that inspect the latest staged
        # read; all validation uses the per-operation maps above.
        self._manifest_consent: ManifestReadConsent | None = None
        self._manifest: dict[str, Any] | None = None

    def _trusted_context(self, *, project_id: str, workspace_id: str, session_id: str) -> None:
        config = self.workflow_config
        if config is None:
            return
        if project_id != config.project_id or workspace_id != config.workspace_id:
            raise SyncRejected("workflow namespace does not match trusted configuration")
        if session_id != config.session_id:
            raise SyncRejected("workflow session does not match trusted configuration")
        if datetime.now(UTC) >= config.session_expires_at:
            raise SyncRejected("workflow session has expired")

    def _effective_expiry(self, value: datetime) -> datetime:
        result = _utc(value)
        config = self.workflow_config
        if config is not None and result > config.session_expires_at:
            raise SyncRejected("consent expiry exceeds trusted session expiry")
        return result

    def preview_history(
        self,
        events: Sequence[ActivityEvent],
        *,
        google_subject: str,
        firebase_uid: str,
        session_id: str,
    ) -> tuple[str, ...]:
        if self.workflow_config is None:
            raise SyncRejected("trusted workflow configuration is required")
        if not events or len(events) > self.outbox.max_events:
            raise SyncRejected("history batch is empty or exceeds its bound")
        if any(not isinstance(event, ActivityEvent) for event in events):
            raise SyncRejected("history accepts typed ActivityEvent records only")
        if len({event.event_id for event in events}) != len(events):
            raise SyncRejected("history event IDs must be unique")
        first = events[0]
        self._trusted_context(
            project_id=first.project_id,
            workspace_id=first.workspace_id,
            session_id=session_id,
        )
        if any(
            event.project_id != first.project_id
            or event.workspace_id != first.workspace_id
            or event.task_id != first.task_id
            for event in events
        ):
            raise SyncRejected("history events must share one project, workspace, and task")
        self.outbox.enqueue_history(events)
        owner = _id(google_subject, "google_subject")
        _id(firebase_uid, "firebase_uid")
        payload_hash = _hash([event.to_dict() for event in events])
        frozen_events = tuple(events)
        binding = ApprovalBinding(
            task_id=first.task_id,
            project_id=first.project_id,
            workspace_id=first.workspace_id,
            google_subject=owner,
            firebase_uid=firebase_uid,
            payload_hash=payload_hash,
            action_scope={
                "kind": "history_upload",
                "event_ids": tuple(event.event_id for event in events),
            },
            resource_versions={},
            policy_version=first.policy_version,
            approval_type="history_upload",
            destination="control",
            expires_at=datetime.now(UTC),
            session_id=session_id,
        )
        operation_id = "history-" + payload_hash[:32]
        if len(self._history_previews) >= 32:
            self._history_previews.pop(next(iter(self._history_previews)))
        self._history_previews[operation_id] = (frozen_events, binding)
        self._latest_history_operation = operation_id
        self._history_operation = None
        return tuple(event.event_id for event in events)

    def history_binding(
        self, *, firebase_uid: str, expires_at: datetime, session_id: str | None = None
    ) -> ApprovalBinding:
        if self._latest_history_operation is None:
            raise SyncRejected("preview history before approval")
        base = self._history_previews[self._latest_history_operation][1]
        return ApprovalBinding(
            task_id=base.task_id,
            project_id=base.project_id,
            workspace_id=base.workspace_id,
            google_subject=base.google_subject,
            firebase_uid=firebase_uid,
            payload_hash=base.payload_hash,
            action_scope=base.action_scope,
            resource_versions=base.resource_versions,
            policy_version=base.policy_version,
            approval_type=base.approval_type,
            destination=base.destination,
            expires_at=expires_at,
            session_id=base.session_id if session_id is None else session_id,
        )

    def push_history(
        self, *, approval: ApprovalEnvelope | None = None, accepted: bool = True
    ) -> SyncResult:
        config = self.workflow_config
        if config is None:
            raise SyncRejected("trusted workflow configuration is required")
        if not accepted or approval is None:
            raise SyncRejected("explicit history upload approval is required")
        expiry = approval.approval.expires_at
        assert expiry is not None
        self._trusted_context(
            project_id=approval.approval.project_id,
            workspace_id=approval.approval.workspace_id,
            session_id=approval.session_id,
        )
        self._effective_expiry(expiry)
        candidates = [
            (events, base)
            for events, base in self._history_previews.values()
            if base.payload_hash == approval.approval.change_hash
            and base.task_id == approval.approval.task_id
            and base.project_id == approval.approval.project_id
            and base.workspace_id == approval.approval.workspace_id
        ]
        if not candidates:
            raise SyncRejected("history preview is missing or no longer available")
        events, base = candidates[0]
        expected = ApprovalBinding(
            task_id=base.task_id,
            project_id=base.project_id,
            workspace_id=base.workspace_id,
            google_subject=base.google_subject,
            firebase_uid=approval.firebase_uid,
            payload_hash=base.payload_hash,
            action_scope=base.action_scope,
            resource_versions=base.resource_versions,
            policy_version=base.policy_version,
            approval_type=base.approval_type,
            destination=base.destination,
            expires_at=expiry,
            session_id=approval.session_id,
        )
        try:
            verify_approval(approval, expected=expected)
        except ApprovalError as exc:
            raise SyncRejected("history approval binding is invalid or expired") from exc
        operation_id = "history-" + expected.payload_hash[:32]
        descriptor = {
            "kind": "history_upload",
            "project_id": expected.project_id,
            "workspace_id": expected.workspace_id,
            "task_id": expected.task_id,
            "firebase_uid": expected.firebase_uid,
            "google_subject": expected.google_subject,
            "event_ids": [event.event_id for event in events],
            "event_hashes": [event.content_hash for event in events],
            "payload_hash": expected.payload_hash,
            "approval_id": approval.approval.approval_id,
            "session_id": expected.session_id,
            "expires_at": expiry.isoformat(),
        }
        path = (
            f"{_control_prefix(expected.project_id, expected.workspace_id, expected.firebase_uid)}"
            f"/exports/{operation_id}"
        )
        payload = {
            "database": config.control_database_id,
            "method": "writeBatch",
            "writes": [
                {
                    "path": path,
                    "mode": "create",
                    "data": {
                        "schema_version": 1,
                        "export_id": operation_id,
                        "kind": "history_upload",
                        "project_id": expected.project_id,
                        "workspace_id": expected.workspace_id,
                        "task_id": expected.task_id,
                        "firebase_uid": expected.firebase_uid,
                        "google_sub": expected.google_subject,
                        "owner_google_subject": expected.google_subject,
                        "origin": "local",
                        "session_id": expected.session_id,
                        "event_ids": [event.event_id for event in events],
                        "events": [event.to_dict() for event in events],
                        "payload_hash": expected.payload_hash,
                        "canonical_payload": rfc8785.dumps(
                            [event.to_dict() for event in events]
                        ).decode(),
                        "approval_descriptor_hash": approval.descriptor_hash,
                        "approval": approval.approval.to_dict()
                        | {
                            "canonical_payload": approval.approval.canonical(),
                            "descriptor_hash": approval.descriptor_hash,
                            "session_id": approval.session_id,
                            "destination": approval.destination,
                            "approved_at_ts": _timestamp_mirror(approval.approval.approved_at),
                        },
                        "approval_hash": approval.approval.content_hash,
                        "expires_at_ts": _timestamp_mirror(expiry),
                        "expires_at": expiry.isoformat(),
                    },
                }
            ],
        }
        record = _record_instruction(
            self.outbox,
            operation_id=operation_id,
            owner=expected.google_subject,
            uid=expected.firebase_uid,
            project=expected.project_id,
            workspace=expected.workspace_id,
            namespace="control",
            descriptor=descriptor,
            payload=payload,
        )
        self._history_operation = operation_id
        if record.state is OperationState.ACKNOWLEDGED:
            return SyncResult(
                SyncOutcome.ACKNOWLEDGED,
                tuple(event.event_id for event in events),
                ack_id=record.ack_id,
                operation_id=operation_id,
            )
        if record.state is not OperationState.PENDING:
            return SyncResult(
                SyncOutcome.UNKNOWN,
                tuple(event.event_id for event in events),
                error="operation outcome is unknown",
                operation_id=operation_id,
            )
        if not record.released:
            return SyncResult(
                SyncOutcome.INSTRUCTION_READY,
                tuple(event.event_id for event in events),
                operation_id=operation_id,
            )
        return SyncResult(
            SyncOutcome.INSTRUCTION_READY,
            tuple(event.event_id for event in events),
            operation_id=operation_id,
            instruction=record.instruction,
        )

    def push_task(  # noqa: PLR0915
        self,
        request: TaskRequest,
        *,
        firebase_uid: str,
        approval: ApprovalEnvelope | None = None,
        accepted: bool = True,
        changeset: ChangeSet | None = None,
        session_id: str,
        upload_approval: ApprovalEnvelope | None = None,
    ) -> SyncResult:
        config = self.workflow_config
        if config is None:
            raise SyncRejected("trusted workflow configuration is required")
        if not accepted or approval is None:
            raise SyncRejected("explicit task approval is required")
        bound_hash = request.content_hash
        approval_type = "upload_run"
        digest_kind = "task_request"
        if request.intent == "apply":
            if (
                changeset is None
                or upload_approval is None
                or changeset.task_id != request.task_id
                or changeset.content_hash != request.plan.get("changeset_hash")
            ):
                raise SyncRejected("exact apply requires the bound ChangeSet")
            bound_hash, approval_type, digest_kind = (
                changeset.content_hash,
                "exact_apply",
                "changeset",
            )
        expiry = approval.approval.expires_at
        assert expiry is not None
        self._trusted_context(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            session_id=session_id or approval.session_id,
        )
        self._effective_expiry(expiry)
        expected = ApprovalBinding(
            task_id=request.task_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            google_subject=request.user_id,
            firebase_uid=firebase_uid,
            payload_hash=bound_hash,
            action_scope=request.scope,
            resource_versions=request.resource_versions,
            policy_version=request.policy_version,
            approval_type=approval_type,
            destination="control",
            expires_at=expiry,
            session_id=session_id or approval.session_id,
        )
        try:
            verify_approval(approval, expected=expected)
        except ApprovalError as exc:
            raise SyncRejected("task approval binding is invalid or expired") from exc
        approvals = [approval]
        if request.intent == "apply":
            assert upload_approval is not None
            upload_expiry = upload_approval.approval.expires_at
            assert upload_expiry is not None
            upload_expected = ApprovalBinding(
                task_id=request.task_id,
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                google_subject=request.user_id,
                firebase_uid=firebase_uid,
                payload_hash=request.content_hash,
                action_scope=request.scope,
                resource_versions=request.resource_versions,
                policy_version=request.policy_version,
                approval_type="upload_run",
                destination="control",
                expires_at=upload_expiry,
                session_id=session_id or upload_approval.session_id,
            )
            try:
                verify_approval(upload_approval, expected=upload_expected)
            except ApprovalError as exc:
                raise SyncRejected("upload approval is invalid or expired") from exc
            approvals = [upload_approval, approval]
        descriptor = {
            "kind": "task_request",
            "request_id": "request-" + request.content_hash[:32],
            "project_id": request.project_id,
            "workspace_id": request.workspace_id,
            "firebase_uid": firebase_uid,
            "google_sub": request.user_id,
            "request_hash": request.content_hash,
            "bound_digest_kind": digest_kind,
            "bound_digest": bound_hash,
            "approval_id": approval.approval.approval_id,
            "approval_type": approval_type,
            "action_scope": _plain(request.scope),
            "resource_versions": _plain(request.resource_versions),
            "policy_version": request.policy_version,
            "destination": "control",
            "session_id": expected.session_id,
            "expires_at": expiry.isoformat(),
        }
        operation_id = descriptor["request_id"]
        prefix = _control_prefix(request.project_id, request.workspace_id, firebase_uid)
        request_path = f"{prefix}/requests/{_id(operation_id, 'request_id')}"
        request_data = request.to_dict() | {
            "request_id": operation_id,
            "state": "submitted",
            "firebase_uid": firebase_uid,
            "google_sub": request.user_id,
            "request_hash": request.content_hash,
            "canonical_payload": request.canonical(),
            "expires_at_ts": _timestamp_mirror(expiry),
            "session_id": expected.session_id,
            "owner_google_subject": request.user_id,
            "required_approval": approval_type,
            "approval_id": approval.approval.approval_id,
            "required_approvals": [item.approval.approval_id for item in approvals],
        }
        if changeset is not None:
            request_data |= {
                "changeset": changeset.to_dict(),
                "changeset_canonical": changeset.canonical(),
                "changeset_hash": changeset.content_hash,
            }
        writes = [{"path": request_path, "mode": "create", "data": request_data}]
        for item in approvals:
            item_expiry = item.approval.expires_at
            assert item_expiry is not None
            item_type = "upload_run" if item is upload_approval else approval_type
            item_kind = "task_request" if item is upload_approval else digest_kind
            approval_path = (
                f"{request_path}/approvals/{_id(item.approval.approval_id, 'approval_id')}"
            )
            writes.append(
                {
                    "path": approval_path,
                    "mode": "create",
                    "data": item.approval.to_dict()
                    | {
                        "request_id": operation_id,
                        "firebase_uid": firebase_uid,
                        "google_sub": request.user_id,
                        "approval_type": item_type,
                        "bound_digest_kind": item_kind,
                        "expires_at_ts": _timestamp_mirror(item_expiry),
                        "approval_hash": item.approval.content_hash,
                        "canonical_payload": item.approval.canonical(),
                        "descriptor_hash": item.descriptor_hash,
                        "session_id": item.session_id,
                        "destination": item.destination,
                        "approved_at_ts": _timestamp_mirror(item.approval.approved_at),
                        "approver_firebase_uid": firebase_uid,
                        "approver_google_sub": request.user_id,
                    },
                }
            )
        payload = {
            "database": config.control_database_id,
            "method": "writeBatch",
            "writes": writes,
        }
        record = _record_instruction(
            self.outbox,
            operation_id=operation_id,
            owner=request.user_id,
            uid=firebase_uid,
            project=request.project_id,
            workspace=request.workspace_id,
            namespace="control",
            descriptor=descriptor,
            payload=payload,
        )
        if record.state is OperationState.ACKNOWLEDGED:
            return SyncResult(
                SyncOutcome.ACKNOWLEDGED,
                (request.task_id,),
                ack_id=record.ack_id,
                operation_id=operation_id,
            )
        if record.state is not OperationState.PENDING:
            return SyncResult(
                SyncOutcome.UNKNOWN,
                (request.task_id,),
                error="operation outcome is unknown",
                operation_id=operation_id,
            )
        if not record.released:
            return SyncResult(
                SyncOutcome.INSTRUCTION_READY, (request.task_id,), operation_id=operation_id
            )
        return SyncResult(
            SyncOutcome.INSTRUCTION_READY,
            (request.task_id,),
            operation_id=operation_id,
            instruction=record.instruction,
        )

    def stage_manifest(
        self, *, consent: ManifestReadConsent | None = None, accepted: bool = True
    ) -> Mapping[str, Any]:
        if self.workflow_config is None:
            raise SyncRejected("trusted workflow configuration is required")
        config = self.workflow_config
        if not accepted or consent is None or _utc(consent.expires_at) <= datetime.now(UTC):
            raise SyncRejected("bounded manifest-read consent is required")
        for value, name in (
            (consent.project_id, "project_id"),
            (consent.workspace_id, "workspace_id"),
            (consent.firebase_uid, "firebase_uid"),
            (consent.task_id, "task_id"),
        ):
            _id(value, name)
        self._trusted_context(
            project_id=consent.project_id,
            workspace_id=consent.workspace_id,
            session_id=consent.session_id,
        )
        fields = tuple(consent.fields)
        if (
            not fields
            or len(fields) > 20
            or any(not isinstance(value, str) or not value or len(value) > 100 for value in fields)
        ):
            raise SyncRejected("manifest fields exceed the local bound")
        operation_id = "manifest-" + consent.descriptor_hash[:32]
        descriptor = consent.descriptor
        payload = {
            "database": config.runtime_database_id,
            "method": "getDoc",
            "path": _runtime_manifest_path(
                consent.project_id, consent.workspace_id, consent.firebase_uid, consent.task_id
            ),
            "fields": list(fields),
            "whole_document": True,
            "read_scope": "manifest",
        }
        record = _record_instruction(
            self.outbox,
            operation_id=operation_id,
            owner=consent.google_subject,
            uid=consent.firebase_uid,
            project=consent.project_id,
            workspace=consent.workspace_id,
            namespace="runtime",
            descriptor=descriptor,
            payload=payload,
        )
        self._manifest_consents[operation_id] = consent
        self._manifest_consent = consent
        if record.state is not OperationState.PENDING:
            raise SyncRejected("manifest operation outcome is unresolved")
        if not record.released:
            raise SyncRejected("manifest operation is already awaiting acknowledgement")
        return record.instruction

    def receive_manifest(
        self,
        operation_id: str,
        manifest: Mapping[str, Any],
        *,
        descriptor_hash: str,
        google_subject: str,
        firebase_uid: str,
    ) -> Mapping[str, Any]:
        record = self.outbox.get_instruction(operation_id)
        if (
            record.descriptor_hash != descriptor_hash
            or record.owner_google_subject != google_subject
            or record.firebase_uid != firebase_uid
            or record.descriptor.get("kind") != "bounded_manifest_read"
        ):
            raise SyncRejected("manifest acknowledgement binding mismatch")
        consent = self._manifest_consents.get(operation_id)
        if consent is None:
            raise SyncRejected("manifest read was not consented")
        if datetime.now(UTC) >= consent.expires_at:
            raise SyncRejected("manifest read consent has expired")
        self._trusted_context(
            project_id=consent.project_id,
            workspace_id=consent.workspace_id,
            session_id=consent.session_id,
        )
        if not isinstance(manifest, Mapping):
            raise SyncRejected("runtime manifest is malformed")
        allowed = {
            "schema_version",
            "kind",
            "result_id",
            "result_hash",
            "scope",
            "project_id",
            "workspace_id",
            "firebase_uid",
            "google_subject",
            "task_id",
            "available",
            "expires_at",
            "expires_at_ts",
        }
        if set(manifest) - allowed:
            raise SyncRejected("runtime manifest contains unknown fields")
        required = {
            "schema_version",
            "kind",
            "project_id",
            "workspace_id",
            "firebase_uid",
            "google_subject",
            "task_id",
            "available",
            "expires_at",
            "expires_at_ts",
            "result_id",
            "result_hash",
            "scope",
        }
        if any(key not in manifest for key in required):
            raise SyncRejected("runtime manifest is incomplete")
        if (
            not isinstance(manifest.get("result_id"), str)
            or not _is_digest(manifest.get("result_hash"))
            or not isinstance(manifest.get("scope"), (list, tuple))
            or len(manifest["scope"]) > 20
            or any(
                not isinstance(item, str) or not item or len(item) > 100
                for item in manifest["scope"]
            )
        ):
            raise SyncRejected("runtime manifest is malformed")
        value = dict(manifest)
        value["result_id"] = _id(value["result_id"], "result_id")
        value["result_hash"] = str(value["result_hash"]).lower()
        value["scope"] = tuple(value["scope"])
        if (
            value.get("kind") != "manifest"
            or value.get("project_id") != consent.project_id
            or value.get("workspace_id") != consent.workspace_id
            or value.get("firebase_uid") != consent.firebase_uid
            or value.get("google_subject") != consent.google_subject
            or value.get("task_id") != consent.task_id
            or value.get("available") is not True
        ):
            raise SyncRejected("runtime manifest binding mismatch")
        try:
            remote_expiry = _utc(datetime.fromisoformat(str(value["expires_at"])))
        except (TypeError, ValueError) as exc:
            raise SyncRejected("runtime manifest expiry is malformed") from exc
        if remote_expiry <= datetime.now(UTC):
            raise SyncRejected("runtime manifest has expired")
        if "expires_at_ts" not in value or not _native_timestamp(value["expires_at_ts"]):
            raise SyncRejected("runtime manifest expiry mirror is malformed")
        if value["expires_at_ts"] != _timestamp_mirror(remote_expiry):
            raise SyncRejected("runtime manifest expiry mirror mismatch")
        if value["result_id"] != value["result_hash"]:
            raise SyncRejected("manifest result ID must equal its digest")
        self.outbox.acknowledge_instruction(
            operation_id,
            descriptor_hash=descriptor_hash,
            owner_google_subject=google_subject,
            firebase_uid=firebase_uid,
            ack_id=value["result_hash"],
            ack={
                "kind": "manifest",
                "result_id": value["result_id"],
                "result_hash": value["result_hash"],
            },
        )
        self._manifests[operation_id] = value
        self._manifest = value
        return dict(value)

    def download_result(
        self, *, consent: DownloadConsent | None = None, accepted: bool = True
    ) -> Mapping[str, Any]:
        if self.workflow_config is None:
            raise SyncRejected("trusted workflow configuration is required")
        config = self.workflow_config
        if not accepted or consent is None:
            raise SyncRejected("exact result download consent is required")
        metadata_consent = self._manifest_consents.get(consent.metadata_descriptor_hash)
        # descriptor hashes are the stable lookup key; retain a fallback for
        # direct callers from the original API which staged one latest read.
        if metadata_consent is None:
            metadata_consent = next(
                (
                    item
                    for item in self._manifest_consents.values()
                    if item.descriptor_hash == consent.metadata_descriptor_hash
                ),
                None,
            )
        manifest = None
        if metadata_consent is not None:
            manifest = next(
                (
                    value
                    for operation, value in self._manifests.items()
                    if self._manifest_consents.get(operation) is metadata_consent
                ),
                None,
            )
        if metadata_consent is None or manifest is None:
            raise SyncRejected("exact result requires its staged manifest")
        if (
            consent.metadata_descriptor_hash != metadata_consent.descriptor_hash
            or consent.result_id != manifest.get("result_id")
            or consent.result_hash != manifest.get("result_hash")
        ):
            raise SyncRejected("download consent does not match the staged result")
        if (
            consent.project_id != metadata_consent.project_id
            or consent.workspace_id != metadata_consent.workspace_id
            or consent.firebase_uid != metadata_consent.firebase_uid
            or consent.google_subject != metadata_consent.google_subject
            or consent.task_id != metadata_consent.task_id
            or _utc(consent.expires_at) <= datetime.now(UTC)
            or _utc(consent.expires_at) > _utc(datetime.fromisoformat(str(manifest["expires_at"])))
        ):
            raise SyncRejected("download consent identity or expiry mismatch")
        self._trusted_context(
            project_id=consent.project_id,
            workspace_id=consent.workspace_id,
            session_id=consent.session_id,
        )
        operation_id = "result-" + consent.result_id
        descriptor = {
            "kind": "exact_result_download",
            "project_id": consent.project_id,
            "workspace_id": consent.workspace_id,
            "task_id": consent.task_id,
            "firebase_uid": consent.firebase_uid,
            "google_subject": consent.google_subject,
            "result_id": consent.result_id,
            "result_hash": consent.result_hash,
            "scope": list(consent.scope),
            "metadata_descriptor_hash": consent.metadata_descriptor_hash,
            "session_id": consent.session_id,
            "expires_at": _utc(consent.expires_at).isoformat(),
        }
        result_prefix = _runtime_prefix(
            consent.project_id, consent.workspace_id, consent.firebase_uid, consent.task_id
        )
        payload = {
            "database": config.runtime_database_id,
            "method": "getDoc",
            "path": (f"{result_prefix}/results/{_id(consent.result_id, 'result_id')}"),
            # getDoc returns the complete allowlisted result envelope.  The
            # scope is a consent binding, never a pretend wire projection.
            "fields": list(consent.scope),
            "whole_document": True,
            "read_scope": "exact_result",
        }
        record = _record_instruction(
            self.outbox,
            operation_id=operation_id,
            owner=consent.google_subject,
            uid=consent.firebase_uid,
            project=consent.project_id,
            workspace=consent.workspace_id,
            namespace="runtime",
            descriptor=descriptor,
            payload=payload,
        )
        if record.state is not OperationState.PENDING:
            raise SyncRejected("result operation outcome is unresolved")
        if not record.released:
            raise SyncRejected("result operation is already awaiting acknowledgement")
        return record.instruction

    def receive_result(
        self,
        operation_id: str,
        result: Mapping[str, Any],
        *,
        descriptor_hash: str,
        google_subject: str,
        firebase_uid: str,
        acknowledge: bool = True,
    ) -> Mapping[str, Any]:
        record = self.outbox.get_instruction(operation_id)
        if (
            record.descriptor_hash != descriptor_hash
            or record.owner_google_subject != google_subject
            or record.firebase_uid != firebase_uid
        ):
            raise SyncRejected("result acknowledgement binding mismatch")
        expected_hash = record.descriptor.get("result_hash")
        allowed = {
            "schema_version",
            "result_id",
            "result_hash",
            "payload",
            "canonical_payload",
            "expires_at_ts",
        }
        if not isinstance(result, Mapping) or set(result) - allowed:
            raise SyncRejected("runtime result envelope contains unknown fields")
        required = set(allowed)
        if any(name not in result for name in required) or result.get("schema_version") != 1:
            raise SyncRejected("runtime result envelope is incomplete")
        payload = result.get("payload")
        canonical = result.get("canonical_payload")
        if not isinstance(payload, Mapping) or not isinstance(canonical, str):
            raise SyncRejected("runtime result payload is malformed")
        payload = _validate_result_payload(payload)
        expected_canonical = _canonical_payload(payload)
        digest = hashlib.sha256(expected_canonical.encode("utf-8")).hexdigest()
        if canonical != expected_canonical or result.get("result_hash") != digest:
            raise SyncRejected("runtime result canonical hash mismatch")
        if result.get("result_id") != digest:
            raise SyncRejected("runtime result ID is not digest addressed")
        expected_descriptor_hash = record.descriptor.get("result_hash")
        if expected_descriptor_hash != digest:
            raise SyncRejected("runtime result does not match its approved digest")
        for field in (
            "project_id",
            "workspace_id",
            "firebase_uid",
            "google_subject",
            "task_id",
        ):
            if payload.get(field) != record.descriptor.get(field):
                raise SyncRejected("runtime result owner or task mismatch")
        if payload.get("scope") != record.descriptor.get("scope"):
            raise SyncRejected("runtime result scope mismatch")
        try:
            result_expiry = _utc(datetime.fromisoformat(str(payload["expires_at"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise SyncRejected("runtime result expiry is malformed") from exc
        config = self.workflow_config
        if config is None:  # defensive; strict result paths require config
            raise SyncRejected("trusted workflow configuration is required")
        if result_expiry <= datetime.now(UTC):
            raise SyncRejected("runtime result expiry is outside its trusted bound")
        if not _native_timestamp(result["expires_at_ts"]):
            raise SyncRejected("runtime result expiry mirror is malformed")
        if result["expires_at_ts"] != _timestamp_mirror(result_expiry):
            raise SyncRejected("runtime result expiry mirror mismatch")
        if acknowledge:
            self.outbox.acknowledge_instruction(
                operation_id,
                descriptor_hash=descriptor_hash,
                owner_google_subject=google_subject,
                firebase_uid=firebase_uid,
                ack_id=str(expected_hash),
                ack={"kind": "result", "result_hash": expected_hash},
            )
        return dict(result)

    def acknowledge(
        self,
        operation_id: str,
        *,
        descriptor_hash: str,
        ack_id: str,
        firebase_uid: str,
        google_subject: str,
        ack: Mapping[str, Any] | None = None,
    ) -> SyncResult:
        try:
            record = self.outbox.acknowledge_instruction(
                operation_id,
                descriptor_hash=descriptor_hash,
                owner_google_subject=google_subject,
                firebase_uid=firebase_uid,
                ack_id=ack_id,
                ack=ack,
            )
        except (KeyError, ValueError, OutboxConflict) as exc:
            raise SyncRejected("acknowledgement is invalid or operation is unresolved") from exc
        if record.descriptor.get("kind") == "history_upload":
            for event_id in record.descriptor.get("event_ids", ()):
                try:
                    self.outbox.mark_uploaded(str(event_id), ack_id=ack_id)
                except (KeyError, ValueError, OutboxConflict) as exc:
                    raise SyncRejected("history acknowledgement could not be stored") from exc
        return SyncResult(SyncOutcome.ACKNOWLEDGED, ack_id=record.ack_id, operation_id=operation_id)

    def reconcile(  # noqa: PLR0915
        self,
        operation_id: str,
        *,
        descriptor_hash: str,
        google_subject: str,
        firebase_uid: str,
        observed_ack_id: str | None = None,
        observed_content_hash: str | None = None,
        observed: Mapping[str, Any] | None = None,
    ) -> SyncResult:
        record = self.outbox.get_instruction(operation_id)
        if (
            record.descriptor_hash != descriptor_hash
            or record.owner_google_subject != google_subject
            or record.firebase_uid != firebase_uid
        ):
            raise SyncRejected("reconciliation binding mismatch")
        if record.state is OperationState.ACKNOWLEDGED:
            return SyncResult(
                SyncOutcome.ACKNOWLEDGED, ack_id=record.ack_id, operation_id=operation_id
            )
        if observed is None:
            self.outbox.mark_operation_unknown(
                operation_id, "immutable remote record was not found"
            )
            return SyncResult(
                SyncOutcome.UNKNOWN,
                error="immutable remote record was not found",
                operation_id=operation_id,
            )
        if record.state is not OperationState.UNKNOWN:
            raise SyncRejected("reconciliation is only available for unknown operations")

        def normalized(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {str(key): normalized(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [normalized(item) for item in value]
            return value

        def normalized_documents(value: Any) -> Any:
            if not isinstance(value, (list, tuple)):
                return normalized(value)
            commit_fields = {"createTime", "updateTime", "commitTime", "writeTime"}
            return [
                normalized(
                    {
                        str(key): item
                        for key, item in document.items()
                        if str(key) not in commit_fields
                    }
                )
                if isinstance(document, Mapping)
                else normalized(document)
                for document in value
            ]

        expected_docs: list[dict[str, Any]] | None = None
        if record.payload.get("method") == "getDoc":
            if not isinstance(observed, Mapping):
                raise SyncRejected("reconciliation requires the complete observed result")
            if record.descriptor.get("kind") == "bounded_manifest_read":
                raise SyncRejected(
                    "manifest read recovery requires a fresh bounded metadata preview"
                )
            payload = observed.get("payload")
            canonical = observed.get("canonical_payload")
            digest = (
                hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if isinstance(canonical, str)
                else None
            )
            if (
                not isinstance(payload, Mapping)
                or not isinstance(canonical, str)
                or observed.get("result_id") != digest
                or observed.get("result_hash") != digest
                or digest != record.descriptor.get("result_hash")
                or canonical != _canonical_payload(payload)
            ):
                self.outbox.mark_operation_conflict(
                    operation_id, "remote result conflicts with immutable descriptor"
                )
                return SyncResult(
                    SyncOutcome.CONFLICT,
                    error="remote result conflicts with immutable descriptor",
                    operation_id=operation_id,
                )
            _validate_result_payload(payload)
            for field in (
                "project_id",
                "workspace_id",
                "firebase_uid",
                "google_subject",
                "task_id",
            ):
                if payload.get(field) != record.descriptor.get(field):
                    raise SyncRejected("remote result owner or task mismatch")
            if payload.get("scope") != record.descriptor.get("scope"):
                raise SyncRejected("remote result scope mismatch")
            if not _native_timestamp(observed.get("expires_at_ts")):
                raise SyncRejected("remote result expiry mirror is malformed")
            if observed.get("expires_at_ts") != _timestamp_mirror(
                _utc(datetime.fromisoformat(str(payload["expires_at"])))
            ):
                raise SyncRejected("remote result expiry mirror mismatch")
            observed_docs = [{"path": record.payload.get("path"), "data": normalized(observed)}]
            expected_docs = observed_docs

        if expected_docs is None:
            expected_docs = [
                {"path": write.get("path"), "data": write.get("data")}
                for write in record.payload.get("writes", [])
                if isinstance(write, Mapping)
            ]
        if record.payload.get("method") == "getDoc":
            observed_docs = expected_docs
        else:
            observed_docs = observed.get("documents") if isinstance(observed, Mapping) else None
            if observed_docs is None and isinstance(observed, Mapping) and "path" in observed:
                observed_docs = [observed]
        if not isinstance(observed_docs, (list, tuple)):
            raise SyncRejected("reconciliation requires complete immutable document records")
        if _canonical_payload(
            {"documents": normalized_documents(observed_docs)}
        ) != _canonical_payload({"documents": normalized_documents(expected_docs)}):
            self.outbox.mark_operation_conflict(
                operation_id, "remote record content conflicts with immutable expected payload"
            )
            return SyncResult(
                SyncOutcome.CONFLICT,
                error="remote record content conflicts with immutable expected payload",
                operation_id=operation_id,
            )
        if observed_ack_id is None:
            observed_ack_id = "reconciled-" + descriptor_hash[:32]
        if not isinstance(observed_ack_id, str) or not observed_ack_id:
            raise SyncRejected("reconciliation receipt ID is malformed")
        try:
            reconciled = self.outbox.acknowledge_reconciled(
                operation_id,
                descriptor_hash=descriptor_hash,
                owner_google_subject=google_subject,
                firebase_uid=firebase_uid,
                ack_id=observed_ack_id,
                ack={"reconciled": True, "observed": normalized(observed)},
            )
        except (KeyError, ValueError, OutboxConflict) as exc:
            raise SyncRejected("reconciliation operation is no longer unknown") from exc
        if record.descriptor.get("kind") == "history_upload":
            try:
                for event_id in record.descriptor.get("event_ids", ()):
                    self.outbox.mark_uploaded(str(event_id), ack_id=observed_ack_id)
            except (KeyError, ValueError, OutboxConflict) as exc:
                raise SyncRejected(
                    "reconciled history acknowledgement could not be stored"
                ) from exc
        return SyncResult(
            SyncOutcome.ACKNOWLEDGED, ack_id=reconciled.ack_id, operation_id=operation_id
        )

    def import_history(
        self,
        result: Mapping[str, Any],
        *,
        project_id: str,
        workspace_id: str,
        task_id: str,
        google_subject: str,
        firebase_uid: str,
    ) -> tuple[ActivityEvent, ...]:
        """Validate downloaded evidence without replaying any recorded action."""
        if self.workflow_config is None:
            raise SyncRejected("trusted workflow configuration is required")
        if not isinstance(result, Mapping):
            raise SyncRejected("history result envelope is malformed")
        expected = make_result_envelope(result.get("payload", {}))
        if (
            set(result)
            - {
                "schema_version",
                "result_id",
                "result_hash",
                "payload",
                "canonical_payload",
                "expires_at_ts",
            }
            or result.get("schema_version") != 1
            or result.get("result_id") != expected["result_id"]
            or result.get("result_hash") != expected["result_hash"]
            or result.get("canonical_payload") != expected["canonical_payload"]
            or not _native_timestamp(result.get("expires_at_ts"))
        ):
            raise SyncRejected("history result envelope hash or shape is invalid")
        payload = result.get("payload")
        if not isinstance(payload, Mapping) or payload.get("kind") != "history_result":
            raise SyncRejected("history result payload kind is invalid")
        if any(
            payload.get(name) != expected_value
            for name, expected_value in {
                "project_id": project_id,
                "workspace_id": workspace_id,
                "task_id": task_id,
                "firebase_uid": firebase_uid,
                "google_subject": google_subject,
            }.items()
        ):
            raise SyncRejected("history result payload owner is invalid")
        result = payload
        if not isinstance(result, Mapping) or not isinstance(result.get("events"), (list, tuple)):
            raise SyncRejected("history result is not a typed event set")
        events: list[ActivityEvent] = []
        for item in result["events"]:
            try:
                event = ActivityEvent.from_dict(item)
            except (TypeError, ValueError) as exc:
                raise SyncRejected("history result contains an invalid ActivityEvent") from exc
            if (
                event.project_id != project_id
                or event.workspace_id != workspace_id
                or event.task_id != task_id
            ):
                raise SyncRejected("history result owner or task binding mismatch")
            events.append(event)
        if not events:
            raise SyncRejected("history result contains no events")
        # ActivityEvent.actor_id is provenance and may be a cloud runtime actor;
        # the trusted owner is the separate verified Firebase/Google envelope.
        _id(google_subject, "google_subject")
        _id(firebase_uid, "firebase_uid")
        try:
            self.outbox.import_history_events(
                events, owner_google_subject=google_subject, origin="cloud"
            )
        except (TypeError, ValueError, OutboxConflict) as exc:
            raise SyncRejected("history result could not be stored") from exc
        return tuple(events)

    def bridge_callbacks(self) -> dict[str, Any]:  # noqa: PLR0915
        """Build strict local callbacks for preview, consent, SDK ack and reads."""
        config = self.workflow_config
        if config is None:
            raise SyncRejected("trusted workflow configuration is required")

        def identity_values(identity: Mapping[str, Any]) -> tuple[str, str]:
            subject, uid = identity.get("googleSubject"), identity.get("firebaseUid")
            if not isinstance(subject, str) or not isinstance(uid, str):
                raise SyncRejected("verified identity is incomplete")
            _id(subject, "google_subject")
            _id(uid, "firebase_uid")
            return subject, uid

        def expiry(body: Mapping[str, Any]) -> datetime:
            value = body.get("expiresAt")
            explicit = isinstance(value, str)
            try:
                result = (
                    datetime.fromisoformat(value)
                    if isinstance(value, str)
                    else datetime.now(UTC) + timedelta(minutes=10)
                )
                result = _utc(result)
            except (TypeError, ValueError) as exc:
                raise SyncRejected("consent expiry is invalid") from exc
            now = datetime.now(UTC)
            if result <= now or result > now + timedelta(hours=24):
                raise SyncRejected("consent expiry is outside its bound")
            if not explicit and result > config.session_expires_at:
                result = config.session_expires_at
            if result <= now:
                raise SyncRejected("consent expiry is outside its bound")
            if explicit and result > config.session_expires_at:
                raise SyncRejected("consent expiry exceeds trusted session expiry")
            return result

        def pending(body: Mapping[str, Any], identity: Mapping[str, Any]) -> OperationRecord:
            subject, uid = identity_values(identity)
            operation_id, descriptor_hash = body.get("operationId"), body.get("descriptorHash")
            if not isinstance(operation_id, str) or not isinstance(descriptor_hash, str):
                raise SyncRejected("operation descriptor is required")
            record = self.outbox.get_instruction(operation_id)
            if (
                record.descriptor_hash != descriptor_hash
                or record.owner_google_subject != subject
                or record.firebase_uid != uid
            ):
                raise SyncRejected("operation identity or descriptor mismatch")
            descriptor = record.descriptor
            if descriptor.get("session_id") != config.session_id:
                raise SyncRejected("operation session does not match trusted configuration")
            if record.project_id != config.project_id or record.workspace_id != config.workspace_id:
                raise SyncRejected("operation namespace does not match trusted configuration")
            try:
                operation_expiry = _utc(datetime.fromisoformat(str(descriptor["expires_at"])))
            except (KeyError, TypeError, ValueError) as exc:
                raise SyncRejected("operation expiry is malformed") from exc
            if (
                operation_expiry <= datetime.now(UTC)
                or operation_expiry > config.session_expires_at
            ):
                raise SyncRejected("operation grant has expired")
            if record.state is not OperationState.PENDING:
                raise SyncRejected("operation is no longer pending")
            return record

        # This map holds complete immutable local previews, including the exact
        # records and expiry selected for the human consent step.
        previewed: dict[str, dict[str, Any]] = {}
        consented: set[str] = set()

        def _preview(body: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0915
            subject, uid = identity_values(identity)
            kind = body.get("kind")
            session_id = body.get("sessionId", "")
            if not isinstance(session_id, str) or not session_id or len(session_id) > 200:
                raise SyncRejected("session ID is invalid")
            if session_id != config.session_id:
                raise SyncRejected("workflow session does not match trusted configuration")
            selected_expiry = expiry(body)
            if kind in {"reconciliation", "reconcile"}:
                target_id = body.get("operationId")
                target_hash = body.get("descriptorHash")
                if not isinstance(target_id, str) or not isinstance(target_hash, str):
                    raise SyncRejected("reconciliation preview requires the original operation")
                target = self.outbox.get_instruction(target_id)
                if (
                    target.descriptor_hash != target_hash
                    or target.owner_google_subject != subject
                    or target.firebase_uid != uid
                    or target.project_id != config.project_id
                    or target.workspace_id != config.workspace_id
                    or target.state is not OperationState.UNKNOWN
                ):
                    raise SyncRejected("reconciliation target is not an owned unknown operation")
                if target.descriptor.get("kind") == "bounded_manifest_read":
                    raise SyncRejected(
                        "manifest read recovery requires a fresh bounded metadata preview"
                    )
                expected_database = (
                    config.runtime_database_id
                    if target.namespace == "runtime"
                    else config.control_database_id
                )
                if target.payload.get("database") != expected_database:
                    raise SyncRejected("reconciliation target database is not trusted")
                database = expected_database
                paths = tuple(
                    write["path"]
                    for write in target.payload.get("writes", [])
                    if isinstance(write, Mapping) and isinstance(write.get("path"), str)
                )
                if not paths and isinstance(target.payload.get("path"), str):
                    paths = (target.payload["path"],)
                if not paths or len(paths) > 500:
                    raise SyncRejected("reconciliation target has no bounded document paths")
                consent = ReconciliationReadConsent(
                    target_operation_id=target_id,
                    target_descriptor_hash=target_hash,
                    project_id=target.project_id,
                    workspace_id=target.workspace_id,
                    google_subject=subject,
                    firebase_uid=uid,
                    task_id=str(target.descriptor.get("task_id", "")),
                    paths=paths,
                    database=database,
                    expires_at=selected_expiry,
                    session_id=session_id,
                )
                operation_id = (
                    "reconcile-read-"
                    + _hash(
                        {
                            "target_operation_id": target_id,
                            "target_descriptor_hash": target_hash,
                            "session_id": session_id,
                            "expires_at": selected_expiry.isoformat(),
                            "attempt": len(self._reconciliation_previews),
                        }
                    )[:32]
                )
                self._reconciliation_previews[operation_id] = consent
                previewed[operation_id] = {
                    "kind": kind,
                    "binding": consent,
                    "expiry_explicit": "expiresAt" in body,
                }
                return {
                    "stage": "preview",
                    "operation_id": operation_id,
                    "descriptor_hash": consent.descriptor_hash,
                    "target_operation_id": target_id,
                    "target_descriptor_hash": target_hash,
                    "paths": list(paths),
                    "database": database,
                    "expires_at": selected_expiry.isoformat(),
                    "transfer": {"sdk_calls": 0, "documents": 0, "bytes": 0},
                }
            if kind == "history_upload" and isinstance(body.get("records"), list):
                try:
                    events = tuple(ActivityEvent.from_dict(item) for item in body["records"])
                except (TypeError, ValueError) as exc:
                    raise SyncRejected("history preview contains invalid records") from exc
                if not events:
                    raise SyncRejected("history preview contains no records")
                self._trusted_context(
                    project_id=events[0].project_id,
                    workspace_id=events[0].workspace_id,
                    session_id=session_id,
                )
                self.preview_history(
                    events, google_subject=subject, firebase_uid=uid, session_id=session_id
                )
                stable_operation_id = "history-" + _hash([event.to_dict() for event in events])[:32]
                base = self._history_previews[stable_operation_id][1]
                binding = ApprovalBinding(
                    task_id=base.task_id,
                    project_id=base.project_id,
                    workspace_id=base.workspace_id,
                    google_subject=subject,
                    firebase_uid=uid,
                    payload_hash=base.payload_hash,
                    action_scope=base.action_scope,
                    resource_versions=base.resource_versions,
                    policy_version=base.policy_version,
                    approval_type="history_upload",
                    destination="control",
                    expires_at=selected_expiry,
                    session_id=session_id,
                )
                operation_id = (
                    "history-preview-"
                    + _hash(
                        {
                            "stable": stable_operation_id,
                            "expires_at": selected_expiry.isoformat(),
                            "attempt": len(previewed),
                        }
                    )[:32]
                )
                previewed[operation_id] = {
                    "kind": kind,
                    "binding": binding,
                    "events": events,
                    "expiry_explicit": "expiresAt" in body,
                }
                return {
                    "stage": "preview",
                    "operation_id": operation_id,
                    "descriptor_hash": binding.descriptor_hash,
                    "payload_hash": binding.payload_hash,
                    "project_id": binding.project_id,
                    "workspace_id": binding.workspace_id,
                    "task_id": binding.task_id,
                    "owner_google_subject": binding.google_subject,
                    "firebase_uid": binding.firebase_uid,
                    "scope": dict(binding.action_scope),
                    "destination": binding.destination,
                    "records": [event.to_dict() for event in events],
                    "event_ids": [event.event_id for event in events],
                    "expires_at": selected_expiry.isoformat(),
                    "transfer": {"sdk_calls": 0, "documents": 0, "bytes": 0},
                }
            if kind == "task_request" and isinstance(body.get("request"), Mapping):
                try:
                    request = TaskRequest.from_dict(body["request"])
                    changeset = (
                        ChangeSet.from_dict(body["changeset"])
                        if isinstance(body.get("changeset"), Mapping)
                        else None
                    )
                except (TypeError, ValueError) as exc:
                    raise SyncRejected("task preview contains an invalid complete model") from exc
                if request.user_id != subject or request.state.value != "draft":
                    raise SyncRejected("task preview identity or state is invalid")
                self._trusted_context(
                    project_id=request.project_id,
                    workspace_id=request.workspace_id,
                    session_id=session_id,
                )
                if request.intent == "apply":
                    if (
                        changeset is None
                        or changeset.task_id != request.task_id
                        or request.plan.get("changeset_hash") != changeset.content_hash
                    ):
                        raise SyncRejected("apply preview must bind its exact ChangeSet")
                elif changeset is not None:
                    raise SyncRejected("plan preview cannot include a ChangeSet")
                bound_hash = (
                    changeset.content_hash
                    if request.intent == "apply" and changeset is not None
                    else request.content_hash
                )
                approval_type = "exact_apply" if request.intent == "apply" else "upload_run"
                binding = ApprovalBinding(
                    task_id=request.task_id,
                    project_id=request.project_id,
                    workspace_id=request.workspace_id,
                    google_subject=subject,
                    firebase_uid=uid,
                    payload_hash=bound_hash,
                    action_scope=request.scope,
                    resource_versions=request.resource_versions,
                    policy_version=request.policy_version,
                    approval_type=approval_type,
                    destination="control",
                    expires_at=selected_expiry,
                    session_id=session_id,
                )
                stable_operation_id = "request-" + request.content_hash[:32]
                operation_id = (
                    "request-preview-"
                    + _hash(
                        {
                            "stable": stable_operation_id,
                            "expires_at": selected_expiry.isoformat(),
                            "attempt": len(previewed),
                        }
                    )[:32]
                )
                previewed[operation_id] = {
                    "kind": kind,
                    "binding": binding,
                    "request": request,
                    "changeset": changeset,
                    "expiry_explicit": "expiresAt" in body,
                }
                return {
                    "stage": "preview",
                    "operation_id": operation_id,
                    "descriptor_hash": binding.descriptor_hash,
                    "request_hash": request.content_hash,
                    "bound_digest": bound_hash,
                    "approval_type": approval_type,
                    "project_id": request.project_id,
                    "workspace_id": request.workspace_id,
                    "task_id": request.task_id,
                    "owner_google_subject": subject,
                    "firebase_uid": uid,
                    "request": request.to_dict(),
                    "changeset": changeset.to_dict() if changeset is not None else None,
                    "download_scopes": list(request.download_scopes),
                    "apply_scopes": list(request.apply_scopes),
                    "scope": dict(request.scope),
                    "resource_versions": dict(request.resource_versions),
                    "destination": binding.destination,
                    "expires_at": selected_expiry.isoformat(),
                    "transfer": {"sdk_calls": 0, "documents": 0, "bytes": 0},
                }
            if kind == "bounded_manifest_read":
                fields = body.get("fields")
                task_id = body.get("taskId")
                project_id, workspace_id = body.get("projectId"), body.get("workspaceId")
                if (
                    not isinstance(fields, list)
                    or not isinstance(task_id, str)
                    or not isinstance(project_id, str)
                    or not isinstance(workspace_id, str)
                ):
                    raise SyncRejected("manifest preview must specify its bounded descriptor")
                self._trusted_context(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    session_id=session_id,
                )
                consent = ManifestReadConsent(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    google_subject=subject,
                    firebase_uid=uid,
                    task_id=task_id,
                    fields=tuple(fields),
                    expires_at=selected_expiry,
                    session_id=session_id,
                )
                operation_id = "manifest-preview-" + consent.descriptor_hash[:32]
                previewed[operation_id] = {
                    "kind": kind,
                    "binding": consent,
                    "expiry_explicit": "expiresAt" in body,
                }
                return {
                    "stage": "preview",
                    "operation_id": operation_id,
                    "descriptor_hash": consent.descriptor_hash,
                    "path": consent.descriptor["path"],
                    "fields": list(consent.fields),
                    "expires_at": selected_expiry.isoformat(),
                    "transfer": {"sdk_calls": 0, "documents": 0, "bytes": 0},
                }
            if kind == "exact_result_download":
                scope = body.get("scope")
                if not isinstance(scope, list):
                    raise SyncRejected("result preview must specify an exact scope")
                if not self._manifest_consents:
                    raise SyncRejected("result preview requires its staged manifest")
                metadata_hash = body.get("metadataDescriptorHash")
                staged = None
                if isinstance(metadata_hash, str):
                    staged = next(
                        (
                            (operation, self._manifests[operation], consent)
                            for operation, consent in self._manifest_consents.items()
                            if operation in self._manifests
                            and consent.descriptor_hash == metadata_hash
                        ),
                        None,
                    )
                if staged is None:
                    raise SyncRejected(
                        "result preview requires the exact staged manifest descriptor hash"
                    )
                _, staged_manifest, staged_consent = staged
                try:
                    remote_expiry = _utc(datetime.fromisoformat(str(staged_manifest["expires_at"])))
                except (KeyError, TypeError, ValueError) as exc:
                    raise SyncRejected("staged manifest expiry is malformed") from exc
                if remote_expiry <= datetime.now(UTC):
                    raise SyncRejected("staged manifest has expired")
                if "expiresAt" not in body:
                    selected_expiry = min(selected_expiry, remote_expiry)
                elif selected_expiry > remote_expiry:
                    raise SyncRejected("download consent exceeds remote result expiry")
                download = DownloadConsent.from_manifest(
                    staged_consent, staged_manifest, scope=scope
                )
                if download.result_id != download.result_hash:
                    raise SyncRejected("result preview is not digest addressed")
                self._trusted_context(
                    project_id=download.project_id,
                    workspace_id=download.workspace_id,
                    session_id=download.session_id,
                )
                download = DownloadConsent(
                    metadata_descriptor_hash=download.metadata_descriptor_hash,
                    result_id=download.result_id,
                    result_hash=download.result_hash,
                    scope=download.scope,
                    project_id=download.project_id,
                    workspace_id=download.workspace_id,
                    google_subject=download.google_subject,
                    firebase_uid=download.firebase_uid,
                    task_id=download.task_id,
                    expires_at=selected_expiry,
                    session_id=download.session_id,
                )
                stable_operation_id = "result-" + download.result_id
                operation_id = (
                    "result-preview-"
                    + _hash(
                        {
                            "stable": stable_operation_id,
                            "expires_at": selected_expiry.isoformat(),
                            "attempt": len(previewed),
                        }
                    )[:32]
                )
                descriptor_hash = _hash(
                    {
                        "kind": kind,
                        "operation_id": stable_operation_id,
                        "result_id": download.result_id,
                        "result_hash": download.result_hash,
                        "scope": list(download.scope),
                        "metadata_descriptor_hash": download.metadata_descriptor_hash,
                        "expires_at": selected_expiry.isoformat(),
                    }
                )
                previewed[operation_id] = {
                    "kind": kind,
                    "binding": download,
                    "descriptor_hash": descriptor_hash,
                    "expiry_explicit": "expiresAt" in body,
                }
                return {
                    "stage": "preview",
                    "operation_id": operation_id,
                    "descriptor_hash": descriptor_hash,
                    "result_id": download.result_id,
                    "result_hash": download.result_hash,
                    "scope": list(download.scope),
                    "expires_at": selected_expiry.isoformat(),
                    "transfer": {"sdk_calls": 0, "documents": 0, "bytes": 0},
                }
            raise SyncRejected("workflow preview requires a supported complete record")

        def preview(body: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
            result = _preview(body, identity)
            encoded = _canonical_payload(result).encode("utf-8")
            if len(encoded) > self.outbox.max_instruction_bytes:
                operation_id = result.get("operation_id")
                if isinstance(operation_id, str):
                    previewed.pop(operation_id, None)
                raise SyncRejected("workflow preview exceeds its serialized byte bound")
            now = datetime.now(UTC)
            expired = [
                key
                for key, item in previewed.items()
                if item.get("binding") is not None and _utc(item["binding"].expires_at) <= now
            ]
            for key in expired:
                previewed.pop(key, None)
            for key, consent in list(self._reconciliation_previews.items()):
                if _utc(consent.expires_at) <= now:
                    self._reconciliation_previews.pop(key, None)
            for key, consent in list(self._manifest_consents.items()):
                manifest = self._manifests.get(key)
                keep = False
                if manifest is not None:
                    try:
                        keep = _utc(datetime.fromisoformat(str(manifest["expires_at"]))) > now
                    except (KeyError, TypeError, ValueError):
                        keep = False
                elif _utc(consent.expires_at) > now:
                    keep = True
                if not keep:
                    self._manifest_consents.pop(key, None)
                    self._manifests.pop(key, None)
            while len(self._reconciliation_previews) > 64:
                self._reconciliation_previews.pop(next(iter(self._reconciliation_previews)))
            while len(self._manifest_consents) > 64:
                key = next(iter(self._manifest_consents))
                self._manifest_consents.pop(key, None)
                self._manifests.pop(key, None)
            while len(previewed) > 64:
                previewed.pop(next(iter(previewed)))
            return result

        def consent(  # noqa: PLR0915
            body: dict[str, Any], identity: dict[str, Any]
        ) -> dict[str, Any]:
            subject, uid = identity_values(identity)
            if body.get("sessionId") != config.session_id:
                raise SyncRejected("workflow session does not match trusted configuration")
            operation_id, descriptor_hash = body.get("operationId"), body.get("descriptorHash")
            if not isinstance(operation_id, str) or not isinstance(descriptor_hash, str):
                raise SyncRejected("operation descriptor is required")
            item = previewed.get(operation_id)
            if item is None:
                raise SyncRejected("consent requires an exact local preview")
            binding = item["binding"]
            expected_hash = item.get(
                "descriptor_hash",
                binding.descriptor_hash if hasattr(binding, "descriptor_hash") else "",
            )
            if (
                expected_hash != descriptor_hash
                or binding.google_subject != subject
                or binding.firebase_uid != uid
            ):
                raise SyncRejected("preview identity or descriptor mismatch")
            requested_expiry = body.get("expiresAt")
            if requested_expiry is not None:
                try:
                    requested = _utc(datetime.fromisoformat(requested_expiry))
                except (TypeError, ValueError) as exc:
                    raise SyncRejected("consent expiry is invalid") from exc
                if requested != binding.expires_at:
                    raise SyncRejected("consent expiry must match the preview")
            if operation_id in consented:
                record = self.outbox.get_instruction(operation_id)
                return {
                    "stage": "status",
                    "operation_id": operation_id,
                    "status": record.state.value,
                }
            if isinstance(binding, ManifestReadConsent):
                instruction = self.stage_manifest(consent=binding)
                consented.add(operation_id)
                return {
                    "stage": "instruction",
                    "operation_id": instruction["operation_id"],
                    "descriptor_hash": instruction["descriptor_hash"],
                    "instruction": dict(instruction),
                }
            if isinstance(binding, ReconciliationReadConsent):
                if _utc(binding.expires_at) <= datetime.now(UTC):
                    raise SyncRejected("reconciliation consent has expired")
                target = self.outbox.get_instruction(binding.target_operation_id)
                if (
                    target.state is not OperationState.UNKNOWN
                    or target.descriptor_hash != binding.target_descriptor_hash
                    or target.project_id != config.project_id
                    or target.workspace_id != config.workspace_id
                    or target.payload.get("database") != binding.database
                ):
                    raise SyncRejected("reconciliation target changed")
                # The preview operation is the unique read-attempt ID.  The
                # target operation remains stable for recovery and auditing.
                read_operation_id = operation_id
                payload = {
                    "database": (binding.database),
                    "method": "getDoc",
                    "path": binding.paths[0],
                    "reads": [
                        {"method": "getDoc", "path": path, "whole_document": True}
                        for path in binding.paths
                    ],
                    "whole_document": True,
                    "read_scope": "reconciliation",
                }
                record = _record_instruction(
                    self.outbox,
                    operation_id=read_operation_id,
                    owner=subject,
                    uid=uid,
                    project=binding.project_id,
                    workspace=binding.workspace_id,
                    namespace=target.namespace,
                    descriptor=binding.descriptor,
                    payload=payload,
                )
                consented.add(operation_id)
                if not record.released:
                    raise SyncRejected("reconciliation read is already awaiting acknowledgement")
                return {
                    "stage": "instruction",
                    "operation_id": read_operation_id,
                    "descriptor_hash": record.descriptor_hash,
                    "instruction": dict(record.instruction),
                }
            # DownloadConsent is a dedicated read grant. It is deliberately
            # handled before create_approval(), whose input is an
            # ApprovalBinding and must never be used as a read compatibility
            # path.
            if item["kind"] == "exact_result_download":
                instruction = self.download_result(consent=binding)
                consented.add(operation_id)
                return {
                    "stage": "instruction",
                    "operation_id": instruction["operation_id"],
                    "descriptor_hash": instruction["descriptor_hash"],
                    "instruction": dict(instruction),
                }
            approval = create_approval(binding, approved_at=datetime.now(UTC))
            if item["kind"] == "history_upload":
                result = self.push_history(approval=approval)
            elif item["kind"] == "task_request":
                request = item["request"]
                changeset = item["changeset"]
                upload = None
                if request.intent == "apply":
                    upload_binding = ApprovalBinding(
                        task_id=request.task_id,
                        project_id=request.project_id,
                        workspace_id=request.workspace_id,
                        google_subject=subject,
                        firebase_uid=uid,
                        payload_hash=request.content_hash,
                        action_scope=request.scope,
                        resource_versions=request.resource_versions,
                        policy_version=request.policy_version,
                        approval_type="upload_run",
                        destination="control",
                        expires_at=binding.expires_at,
                        session_id=binding.session_id,
                    )
                    upload = create_approval(
                        upload_binding, approved_at=approval.approval.approved_at
                    )
                result = self.push_task(
                    request,
                    firebase_uid=uid,
                    approval=approval,
                    changeset=changeset,
                    upload_approval=upload,
                    session_id=binding.session_id,
                )
            else:
                raise SyncRejected("unsupported consent operation")
            consented.add(operation_id)
            if result.instruction is None:
                return {
                    "stage": "status",
                    "operation_id": operation_id,
                    "status": result.outcome.value,
                }
            return {
                "stage": "instruction",
                "operation_id": result.operation_id,
                "descriptor_hash": result.instruction["descriptor_hash"],
                "instruction": dict(result.instruction),
            }

        def ack(body: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
            if body.get("sessionId") != config.session_id:
                raise SyncRejected("workflow session does not match trusted configuration")
            record = pending(body, identity)
            if body.get("status") == "unknown":
                self.outbox.mark_operation_unknown(record.operation_id)
                return {
                    "stage": "acknowledgement",
                    "operation_id": record.operation_id,
                    "status": "unknown",
                }
            subject, uid = identity_values(identity)
            if record.descriptor.get("kind") == "reconciliation_read":
                observed = body.get("observed")
                if observed is not None and not isinstance(observed, Mapping):
                    raise SyncRejected("reconciliation observed documents are malformed")
                target_operation_id = str(record.descriptor["target_operation_id"])
                target_record = self.outbox.get_instruction(target_operation_id)
                if target_record.descriptor.get("kind") == "exact_result_download":
                    if not isinstance(observed, Mapping):
                        raise SyncRejected("result recovery requires a complete envelope")
                    self.receive_result(
                        target_operation_id,
                        observed,
                        descriptor_hash=str(record.descriptor["target_descriptor_hash"]),
                        google_subject=subject,
                        firebase_uid=uid,
                        acknowledge=False,
                    )
                    result_payload = observed.get("payload")
                    if isinstance(result_payload, Mapping) and isinstance(
                        result_payload.get("events"), (list, tuple)
                    ):
                        self.import_history(
                            observed,
                            project_id=target_record.project_id,
                            workspace_id=target_record.workspace_id,
                            task_id=str(target_record.descriptor.get("task_id", "")),
                            google_subject=subject,
                            firebase_uid=uid,
                        )
                target_result = self.reconcile(
                    target_operation_id,
                    descriptor_hash=str(record.descriptor["target_descriptor_hash"]),
                    google_subject=subject,
                    firebase_uid=uid,
                    observed_ack_id=(
                        body.get("ackId") if isinstance(body.get("ackId"), str) else None
                    ),
                    observed=observed,
                )
                if target_result.outcome is SyncOutcome.ACKNOWLEDGED:
                    self.outbox.acknowledge_instruction(
                        record.operation_id,
                        descriptor_hash=record.descriptor_hash,
                        owner_google_subject=subject,
                        firebase_uid=uid,
                        ack_id=str(target_result.ack_id),
                        ack={"target_operation_id": target_result.operation_id},
                    )
                elif target_result.outcome is SyncOutcome.CONFLICT:
                    self.outbox.mark_operation_conflict(
                        record.operation_id, target_result.error or "conflict"
                    )
                else:
                    self.outbox.mark_operation_unknown(
                        record.operation_id, target_result.error or "missing"
                    )
                return {
                    "stage": "acknowledgement",
                    "operation_id": target_result.operation_id,
                    "status": target_result.outcome.value,
                    "ack_id": target_result.ack_id,
                }
            if isinstance(body.get("manifest"), Mapping):
                manifest = self.receive_manifest(
                    record.operation_id,
                    body["manifest"],
                    descriptor_hash=record.descriptor_hash,
                    google_subject=subject,
                    firebase_uid=uid,
                )
                return {
                    "stage": "acknowledgement",
                    "operation_id": record.operation_id,
                    "status": "acknowledged",
                    "result_id": manifest["result_id"],
                }
            if isinstance(body.get("result"), Mapping):
                # Validate the complete envelope against the approved read
                # descriptor before importing any typed events.  The second
                # call performs the same strict validation and records the
                # durable acknowledgement only after import succeeds.
                self.receive_result(
                    record.operation_id,
                    body["result"],
                    descriptor_hash=record.descriptor_hash,
                    google_subject=subject,
                    firebase_uid=uid,
                    acknowledge=False,
                )
                imported = []
                if record.descriptor.get("kind") == "exact_result_download":
                    result_body = body["result"]
                    result_payload = (
                        result_body.get("payload")
                        if isinstance(result_body.get("payload"), Mapping)
                        else result_body
                    )
                    if isinstance(result_payload, Mapping) and isinstance(
                        result_payload.get("events"), (list, tuple)
                    ):
                        imported = [
                            event.event_id
                            for event in self.import_history(
                                result_body,
                                project_id=record.project_id,
                                workspace_id=record.workspace_id,
                                task_id=str(record.descriptor.get("task_id", "")),
                                google_subject=subject,
                                firebase_uid=uid,
                            )
                        ]
                result = self.receive_result(
                    record.operation_id,
                    body["result"],
                    descriptor_hash=record.descriptor_hash,
                    google_subject=subject,
                    firebase_uid=uid,
                )
                return {
                    "stage": "acknowledgement",
                    "operation_id": record.operation_id,
                    "status": "acknowledged",
                    "result_hash": result["result_hash"],
                    "imported_event_ids": imported,
                }
            ack_id = body.get("ackId")
            if (
                record.instruction.get("method") != "writeBatch"
                or not isinstance(ack_id, str)
                or not ack_id
            ):
                raise SyncRejected("acknowledgement must include validated read content")
            result = self.acknowledge(
                record.operation_id,
                descriptor_hash=record.descriptor_hash,
                ack_id=ack_id,
                firebase_uid=uid,
                google_subject=subject,
            )
            return {
                "stage": "acknowledgement",
                "operation_id": record.operation_id,
                "status": result.outcome.value,
                "ack_id": result.ack_id,
            }

        def reconcile(body: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
            if body.get("sessionId") != config.session_id:
                raise SyncRejected("workflow session does not match trusted configuration")
            operation_id = body.get("operationId")
            descriptor_hash = body.get("descriptorHash")
            if not isinstance(operation_id, str) or not isinstance(descriptor_hash, str):
                raise SyncRejected("reconciliation requires a read operation descriptor")
            record = self.outbox.get_instruction(operation_id)
            if record.descriptor.get("kind") != "reconciliation_read":
                raise SyncRejected("reconciliation requires a consented read operation")
            # Use the same pending read acknowledgement path as /ack; an
            # original write descriptor can never be submitted to this route.
            result = ack(body, identity)
            result["stage"] = "reconciliation"
            return result

        def recovery(body: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
            """List durable unknown operations for the verified owner.

            The lookup is local and read-only.  It intentionally returns the
            immutable descriptor and original instruction so a restarted UI can
            present the same operation for a new, separately consented read.
            """
            if body.get("sessionId") != config.session_id:
                raise SyncRejected("workflow session does not match trusted configuration")
            subject, uid = identity_values(identity)
            records = self.outbox.recovery_operations(
                owner_google_subject=subject,
                firebase_uid=uid,
                project_id=config.project_id,
                workspace_id=config.workspace_id,
            )
            return {
                "stage": "recovery",
                "operations": [
                    {
                        "operation_id": record.operation_id,
                        "descriptor_hash": record.descriptor_hash,
                        "kind": record.descriptor.get("kind"),
                        "namespace": record.namespace,
                        "descriptor": dict(record.descriptor),
                        "instruction": dict(record.instruction),
                        "state": record.state.value,
                        "error": record.last_error,
                    }
                    for record in records
                ],
            }

        return {
            "workflow_preview": preview,
            "workflow_consent": consent,
            "workflow_ack": ack,
            "workflow_reconcile": reconcile,
            "workflow_recovery": recovery,
        }


__all__ = [
    "DownloadConsent",
    "ManifestReadConsent",
    "ReconciliationReadConsent",
    "SyncEngine",
    "SyncOutcome",
    "SyncRejected",
    "SyncResult",
    "WorkflowConfig",
    "make_result_envelope",
    "make_runtime_manifest",
]
