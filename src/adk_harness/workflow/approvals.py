"""Trusted, human-bound approval envelopes for local sync.

The model ``Approval`` is an immutable approval intent record.  This module adds
the local trust boundary: a verified Google subject and Firebase UID are bound
to one exact descriptor before a caller is allowed to release an SDK write.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

import rfc8785

from .models import Approval


class ApprovalError(ValueError):
    """The approval is not a valid trusted authorization."""


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, frozenset)):
        return [_plain(v) for v in value]
    return value


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApprovalError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _digest(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ApprovalError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError:
        raise ApprovalError(f"{name} must be a SHA-256 digest") from None
    return value.lower()


def _canonical(value: Mapping[str, Any]) -> bytes:
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): plain(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(value) for value in item]
        return item

    return rfc8785.dumps(plain(value))


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Exact scope and dual identity approved by one human action."""

    task_id: str
    project_id: str
    workspace_id: str
    google_subject: str
    firebase_uid: str
    payload_hash: str
    action_scope: Mapping[str, Any]
    resource_versions: Mapping[str, str]
    policy_version: str
    approval_type: str
    destination: str
    expires_at: datetime
    session_id: str

    def __post_init__(self) -> None:
        for name in (
            "task_id",
            "project_id",
            "workspace_id",
            "google_subject",
            "firebase_uid",
            "policy_version",
            "approval_type",
            "destination",
            "session_id",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value.strip()
                or "/" in value
            ):
                raise ApprovalError(f"{name} must be a non-empty path-safe string")
        object.__setattr__(self, "payload_hash", _digest(self.payload_hash, "payload_hash"))
        expires = _utc(self.expires_at, "expires_at")
        object.__setattr__(self, "expires_at", expires)
        if not isinstance(self.action_scope, Mapping) or not isinstance(
            self.resource_versions, Mapping
        ):
            raise ApprovalError("scope and resource versions must be mappings")
        object.__setattr__(self, "action_scope", _freeze(self.action_scope))
        object.__setattr__(self, "resource_versions", _freeze(self.resource_versions))

    def descriptor(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "google_subject": self.google_subject,
            "firebase_uid": self.firebase_uid,
            "payload_hash": self.payload_hash,
            "action_scope": _plain(self.action_scope),
            "resource_versions": _plain(self.resource_versions),
            "policy_version": self.policy_version,
            "approval_type": self.approval_type,
            "destination": self.destination,
            "session_id": self.session_id,
            "expires_at": self.expires_at.isoformat(),
        }

    @property
    def descriptor_hash(self) -> str:
        return hashlib.sha256(_canonical(self.descriptor())).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalEnvelope:
    approval: Approval
    firebase_uid: str
    google_subject: str
    approval_type: str
    destination: str
    descriptor_hash: str
    session_id: str

    @property
    def binding(self) -> ApprovalBinding:
        expiry = self.approval.expires_at
        assert expiry is not None
        return ApprovalBinding(
            task_id=self.approval.task_id,
            project_id=self.approval.project_id,
            workspace_id=self.approval.workspace_id,
            google_subject=self.google_subject,
            firebase_uid=self.firebase_uid,
            payload_hash=self.approval.change_hash,
            action_scope=self.approval.action_scope,
            resource_versions=self.approval.resource_versions,
            policy_version=self.approval.policy_version,
            approval_type=self.approval_type,
            destination=self.destination,
            expires_at=expiry,
            session_id=self.session_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval": self.approval.to_dict(),
            "firebase_uid": self.firebase_uid,
            "google_subject": self.google_subject,
            "approval_type": self.approval_type,
            "destination": self.destination,
            "descriptor_hash": self.descriptor_hash,
            "session_id": self.session_id,
        }


def create_approval(binding: ApprovalBinding, *, approved_at: datetime) -> ApprovalEnvelope:
    approved = _utc(approved_at, "approved_at")
    now = datetime.now(UTC)
    if approved > now + timedelta(seconds=5):
        raise ApprovalError("approval time cannot be in the future")
    if binding.expires_at <= approved or binding.expires_at > approved + timedelta(hours=24):
        raise ApprovalError("approval expiry must be after approval and within 24 hours")
    approval = Approval(
        task_id=binding.task_id,
        project_id=binding.project_id,
        workspace_id=binding.workspace_id,
        change_hash=binding.payload_hash,
        approver_id=binding.google_subject,
        action_scope=binding.action_scope,
        resource_versions=binding.resource_versions,
        policy_version=binding.policy_version,
        approved_at=approved,
        expires_at=binding.expires_at,
    )
    return ApprovalEnvelope(
        approval=approval,
        firebase_uid=binding.firebase_uid,
        google_subject=binding.google_subject,
        approval_type=binding.approval_type,
        destination=binding.destination,
        descriptor_hash=binding.descriptor_hash,
        session_id=binding.session_id,
    )


def verify_approval(
    envelope: ApprovalEnvelope,
    *,
    expected: ApprovalBinding,
    now: datetime | None = None,
    native_expires_at: datetime | None = None,
) -> None:
    if not isinstance(envelope, ApprovalEnvelope):
        raise ApprovalError("approval must be a trusted envelope")
    if envelope.descriptor_hash != expected.descriptor_hash:
        raise ApprovalError("approval descriptor hash mismatch")
    if (
        envelope.firebase_uid != expected.firebase_uid
        or envelope.google_subject != expected.google_subject
    ):
        raise ApprovalError("verified identity mismatch")
    if (
        envelope.approval_type != expected.approval_type
        or envelope.destination != expected.destination
        or envelope.session_id != expected.session_id
    ):
        raise ApprovalError("approval destination or type mismatch")
    try:
        envelope.approval.require_for(
            expected.payload_hash,
            task_id=expected.task_id,
            approver_id=expected.google_subject,
            project_id=expected.project_id,
            workspace_id=expected.workspace_id,
            action_scope=expected.action_scope,
            resource_versions=expected.resource_versions,
            policy_version=expected.policy_version,
            trace_id=envelope.approval.trace_id,
        )
    except (TypeError, ValueError) as exc:
        raise ApprovalError("approval binding mismatch") from exc
    expiry = envelope.approval.expires_at
    assert expiry is not None
    if native_expires_at is not None and _utc(native_expires_at, "native_expires_at") != expiry:
        raise ApprovalError("native expiry mirror mismatch")
    check_time = _utc(now, "now") if now is not None else datetime.now(UTC)
    if not envelope.approval.approved_at <= check_time < expiry:
        raise ApprovalError("approval is expired or not yet active")


__all__ = [
    "ApprovalBinding",
    "ApprovalEnvelope",
    "ApprovalError",
    "create_approval",
    "verify_approval",
]
