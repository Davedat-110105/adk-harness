"""Versioned, credential-free records for approved local work.

Schema version 1 uses RFC 8785 canonical JSON. Timestamps are UTC ISO-8601
strings, and ``content_hash`` is SHA-256 over those canonical UTF-8 bytes.
Records describe intent and evidence; trusted verification of a human action
belongs to the phase 5 control envelope and policy gate.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar
from uuid import uuid4

import rfc8785

SCHEMA_VERSION = 1
_SAFE_INTEGER = 2**53 - 1
_SHA256 = re.compile(r"\A[0-9a-fA-F]{64}\Z")
_CREDENTIAL_KEY = re.compile(
    r"\A(?:authorization|access[_-]?token|refresh[_-]?token|api[_-]?key|"
    r"client[_-]?secret|password|private[_-]?key|credential|secret|token)\Z"
)
_SECRET_VALUE = (
    re.compile(r"authorization\s*[=:]\s*bearer\s+\S+", re.I),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I),
    re.compile(
        r"\b(?:access_token|refresh_token|api_key|client_secret|password)\s*[=:]\s*\S+",
        re.I,
    ),
    re.compile(r"-----BEGIN(?: [^-]+)? PRIVATE KEY-----", re.I),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_string(value: Any, name: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{name} must contain valid Unicode") from None
    if required and not value.strip():
        raise ValueError(f"{name} must be non-empty")
    if any(pattern.search(value) for pattern in _SECRET_VALUE):
        raise ValueError("credential-shaped values are not permitted in workflow records")
    return value


def _credential_key(key: str) -> bool:
    normalized = key.lower().replace(" ", "_")
    if normalized in {"token_count", "token_budget", "token_limit", "token_usage"}:
        return False
    if _CREDENTIAL_KEY.fullmatch(normalized):
        return True
    return any(
        part in {"authorization", "credential", "secret", "password", "token", "key"}
        for part in re.split(r"[_-]", normalized)
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("record mapping keys must be strings")
            key = _safe_string(raw_key, "record mapping key")
            if _credential_key(key):
                raise ValueError("credential-shaped keys are not permitted in workflow records")
            frozen[key] = _freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if abs(value) > _SAFE_INTEGER:
            raise ValueError("record integers must be safe JSON integers")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("record numbers must be finite")
        return value
    if isinstance(value, str):
        return _safe_string(value, "record value", required=False)
    raise TypeError(f"record values must be JSON primitives, got {type(value).__name__}")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return rfc8785.dumps(_plain(payload))


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO-8601 string")
    try:
        return _utc(datetime.fromisoformat(value), name)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a valid timezone-aware ISO-8601 timestamp") from None


def _record(
    data: Mapping[str, Any], required: frozenset[str], allowed: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise TypeError("record input must be a mapping")
    if any(not isinstance(key, str) for key in data):
        raise TypeError("record field names must be strings")
    schema = data.get("schema_version")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != SCHEMA_VERSION:
        raise ValueError("unsupported schema version")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError("unknown workflow record fields")
    missing = required - set(data)
    if missing:
        raise ValueError("missing required workflow record fields")
    return dict(data)


def _ids(**values: Any) -> None:
    for name, value in values.items():
        _safe_string(value, name)


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list or tuple of strings")
    return tuple(_safe_string(item, f"{name} item") for item in value)


def _string_map(value: Any, name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    for key, item in value.items():
        _safe_string(key, f"{name} key")
        _safe_string(item, f"{name} value")
    return _freeze(value)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return _freeze(value)


def _digest(value: Any, name: str = "change_hash") -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 hexadecimal digest")
    return value


class TaskState(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLYING = "applying"
    COMPLETED = "completed"
    HELD = "held"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECONCILING = "reconciling"


_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DRAFT: frozenset({TaskState.SUBMITTED, TaskState.CANCELLED}),
    TaskState.SUBMITTED: frozenset(
        {TaskState.PLANNING, TaskState.HELD, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.PLANNING: frozenset(
        {TaskState.AWAITING_APPROVAL, TaskState.FAILED, TaskState.BLOCKED}
    ),
    TaskState.AWAITING_APPROVAL: frozenset(
        {TaskState.APPLYING, TaskState.HELD, TaskState.CANCELLED, TaskState.BLOCKED}
    ),
    TaskState.APPLYING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.RECONCILING}),
    TaskState.RECONCILING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.BLOCKED}),
    TaskState.HELD: frozenset({TaskState.SUBMITTED, TaskState.CANCELLED, TaskState.BLOCKED}),
    TaskState.BLOCKED: frozenset({TaskState.SUBMITTED, TaskState.CANCELLED, TaskState.RECONCILING}),
    TaskState.FAILED: frozenset({TaskState.RECONCILING, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def transition(current: TaskState, target: TaskState) -> TaskState:
    try:
        current, target = TaskState(current), TaskState(target)
    except (TypeError, ValueError):
        raise ValueError("invalid task state") from None
    if target not in _TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current.value} -> {target.value}")
    return target


@dataclass(frozen=True, slots=True)
class TaskRequest:
    project_id: str
    workspace_id: str
    user_id: str
    content: str
    intent: str
    plan: Mapping[str, Any] = field(default_factory=dict)
    download_scopes: tuple[str, ...] = ()
    apply_scopes: tuple[str, ...] = ()
    scope: Mapping[str, Any] = field(default_factory=dict)
    resource_versions: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "policy-unknown"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_now)
    task_id: str = field(default_factory=lambda: str(uuid4()))
    state: TaskState = TaskState.DRAFT
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _ids(
            project_id=self.project_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            task_id=self.task_id,
        )
        _safe_string(self.content, "content", required=False)
        if self.intent not in ("plan", "apply"):
            raise ValueError("intent must be exactly 'plan' or 'apply'")
        object.__setattr__(self, "plan", _mapping(self.plan, "plan"))
        object.__setattr__(self, "scope", _mapping(self.scope, "scope"))
        object.__setattr__(
            self, "download_scopes", _string_tuple(self.download_scopes, "download_scopes")
        )
        object.__setattr__(self, "apply_scopes", _string_tuple(self.apply_scopes, "apply_scopes"))
        object.__setattr__(
            self, "resource_versions", _string_map(self.resource_versions, "resource_versions")
        )
        object.__setattr__(
            self, "policy_version", _safe_string(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "trace_id", _safe_string(self.trace_id, "trace_id"))
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        try:
            state = TaskState(self.state)
        except (TypeError, ValueError):
            raise ValueError("state must be a valid TaskState") from None
        object.__setattr__(self, "state", state)

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "content": self.content,
            "intent": self.intent,
            "plan": self.plan,
            "download_scopes": self.download_scopes,
            "apply_scopes": self.apply_scopes,
            "scope": self.scope,
            "resource_versions": self.resource_versions,
            "policy_version": self.policy_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self._payload())

    def canonical(self) -> str:
        return self.canonical_bytes().decode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def intent_hash(self) -> str:
        return self.content_hash

    def to_dict(self) -> dict[str, Any]:
        return _plain(self._payload()) | {"state": self.state.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TaskRequest:
        allowed = frozenset(
            {
                "schema_version",
                "task_id",
                "project_id",
                "workspace_id",
                "user_id",
                "content",
                "intent",
                "plan",
                "download_scopes",
                "apply_scopes",
                "scope",
                "resource_versions",
                "policy_version",
                "trace_id",
                "created_at",
                "state",
            }
        )
        raw = _record(data, allowed - {"schema_version"}, allowed)
        raw["created_at"] = _parse_time(raw["created_at"], "created_at")
        return cls(**{key: value for key, value in raw.items() if key != "schema_version"})


@dataclass(frozen=True, slots=True)
class ChangeSet:
    task_id: str
    project_id: str
    workspace_id: str
    user_id: str
    changes: tuple[Mapping[str, Any], ...]
    resource_versions: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "policy-unknown"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_now)
    change_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _ids(
            task_id=self.task_id,
            project_id=self.project_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            change_id=self.change_id,
        )
        if not isinstance(self.changes, (list, tuple)):
            raise TypeError("changes must be a list or tuple")
        frozen_changes = _freeze(self.changes)
        if any(not isinstance(change, Mapping) for change in frozen_changes):
            raise TypeError("changes must contain mappings")
        object.__setattr__(self, "changes", frozen_changes)
        object.__setattr__(
            self, "resource_versions", _string_map(self.resource_versions, "resource_versions")
        )
        object.__setattr__(
            self, "policy_version", _safe_string(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "trace_id", _safe_string(self.trace_id, "trace_id"))
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "change_id": self.change_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "changes": self.changes,
            "resource_versions": self.resource_versions,
            "policy_version": self.policy_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self._payload())

    def canonical(self) -> str:
        return self.canonical_bytes().decode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _plain(self._payload())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChangeSet:
        allowed = frozenset(
            {
                "schema_version",
                "change_id",
                "task_id",
                "project_id",
                "workspace_id",
                "user_id",
                "changes",
                "resource_versions",
                "policy_version",
                "trace_id",
                "created_at",
            }
        )
        raw = _record(data, allowed - {"schema_version"}, allowed)
        raw["created_at"] = _parse_time(raw["created_at"], "created_at")
        return cls(**{key: value for key, value in raw.items() if key != "schema_version"})


@dataclass(frozen=True, slots=True)
class Approval:
    task_id: str
    project_id: str
    workspace_id: str
    change_hash: str
    approver_id: str
    action_scope: Mapping[str, Any] = field(default_factory=dict)
    resource_versions: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "policy-unknown"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    approved_at: datetime = field(default_factory=_now)
    expires_at: datetime | None = None
    approval_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _ids(
            task_id=self.task_id,
            project_id=self.project_id,
            workspace_id=self.workspace_id,
            approver_id=self.approver_id,
            approval_id=self.approval_id,
        )
        _digest(self.change_hash)
        object.__setattr__(self, "action_scope", _mapping(self.action_scope, "action_scope"))
        object.__setattr__(
            self, "resource_versions", _string_map(self.resource_versions, "resource_versions")
        )
        object.__setattr__(
            self, "policy_version", _safe_string(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "trace_id", _safe_string(self.trace_id, "trace_id"))
        approved = _utc(self.approved_at, "approved_at")
        if self.expires_at is None:
            raise ValueError("approval expires_at must be explicit")
        expiry = _utc(self.expires_at, "expires_at")
        if expiry <= approved or expiry > approved + timedelta(hours=24):
            raise ValueError("approval expiry must be within 24 hours of approval")
        object.__setattr__(self, "approved_at", approved)
        object.__setattr__(self, "expires_at", expiry)

    def _payload(self) -> dict[str, Any]:
        assert self.expires_at is not None
        return {
            "schema_version": self.schema_version,
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "change_hash": self.change_hash,
            "approver_id": self.approver_id,
            "action_scope": self.action_scope,
            "resource_versions": self.resource_versions,
            "policy_version": self.policy_version,
            "trace_id": self.trace_id,
            "approved_at": self.approved_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self._payload())

    def canonical(self) -> str:
        return self.canonical_bytes().decode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _plain(self._payload())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Approval:
        allowed = frozenset(
            {
                "schema_version",
                "approval_id",
                "task_id",
                "project_id",
                "workspace_id",
                "change_hash",
                "approver_id",
                "action_scope",
                "resource_versions",
                "policy_version",
                "trace_id",
                "approved_at",
                "expires_at",
            }
        )
        raw = _record(data, allowed - {"schema_version"}, allowed)
        raw["approved_at"] = _parse_time(raw["approved_at"], "approved_at")
        raw["expires_at"] = _parse_time(raw["expires_at"], "expires_at")
        return cls(**{key: value for key, value in raw.items() if key != "schema_version"})

    def _is_usable(self, change_hash: str) -> bool:
        try:
            _digest(change_hash)
        except ValueError:
            return False
        now = _now()
        assert self.expires_at is not None
        return self.change_hash == change_hash and self.approved_at <= now < self.expires_at

    def require_for(
        self,
        change_hash: str,
        *,
        task_id: str,
        approver_id: str,
        project_id: str,
        workspace_id: str,
        action_scope: Mapping[str, Any],
        resource_versions: Mapping[str, str],
        policy_version: str,
        trace_id: str,
    ) -> None:
        if not self._is_usable(change_hash):
            raise ValueError("approval does not match the current change hash or is not usable")
        expected_scope = _mapping(action_scope, "action_scope")
        expected_versions = _string_map(resource_versions, "resource_versions")
        checks = (
            (task_id, self.task_id),
            (approver_id, self.approver_id),
            (project_id, self.project_id),
            (workspace_id, self.workspace_id),
            (expected_versions, self.resource_versions),
            (policy_version, self.policy_version),
            (trace_id, self.trace_id),
        )
        if any(actual != expected for actual, expected in checks):
            raise ValueError("approval binding mismatch")
        if _canonical(expected_scope) != _canonical(self.action_scope):
            raise ValueError("approval binding mismatch")


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    task_id: str
    project_id: str
    workspace_id: str
    event_type: str
    actor_id: str
    details: Mapping[str, Any] = field(default_factory=dict)
    resource_versions: Mapping[str, str] = field(default_factory=dict)
    policy_version: str = "policy-unknown"
    occurred_at: datetime = field(default_factory=_now)
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    event_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: ClassVar[int] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _ids(
            task_id=self.task_id,
            project_id=self.project_id,
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            event_id=self.event_id,
        )
        object.__setattr__(self, "event_type", _safe_string(self.event_type, "event_type"))
        object.__setattr__(self, "details", _mapping(self.details, "details"))
        object.__setattr__(
            self, "resource_versions", _string_map(self.resource_versions, "resource_versions")
        )
        object.__setattr__(
            self, "policy_version", _safe_string(self.policy_version, "policy_version")
        )
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "trace_id", _safe_string(self.trace_id, "trace_id"))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "details": self.details,
            "resource_versions": self.resource_versions,
            "policy_version": self.policy_version,
            "occurred_at": self.occurred_at.isoformat(),
            "trace_id": self.trace_id,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical(self._payload())

    def canonical(self) -> str:
        return self.canonical_bytes().decode("utf-8")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _plain(self._payload())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ActivityEvent:
        allowed = frozenset(
            {
                "schema_version",
                "event_id",
                "task_id",
                "project_id",
                "workspace_id",
                "event_type",
                "actor_id",
                "details",
                "resource_versions",
                "policy_version",
                "occurred_at",
                "trace_id",
            }
        )
        raw = _record(data, allowed - {"schema_version"}, allowed)
        raw["occurred_at"] = _parse_time(raw["occurred_at"], "occurred_at")
        return cls(**{key: value for key, value in raw.items() if key != "schema_version"})
