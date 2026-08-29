from datetime import UTC, datetime, timedelta

import pytest

from adk_harness.workflow.approvals import (
    ApprovalBinding,
    ApprovalEnvelope,
    ApprovalError,
    create_approval,
    verify_approval,
)


def binding(**overrides: object) -> ApprovalBinding:
    values: dict[str, object] = {
        "task_id": "task-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "google_subject": "google-sub-1",
        "firebase_uid": "firebase-1",
        "payload_hash": "a" * 64,
        "action_scope": {"kind": "upload", "resource": "history"},
        "resource_versions": {"calendar": "v1"},
        "policy_version": "policy-1",
        "approval_type": "upload_run",
        "destination": "control",
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        "session_id": "session-1",
    }
    values.update(overrides)
    return ApprovalBinding(**values)


def test_approval_envelope_binds_both_identity_domains_and_exact_scope() -> None:
    expected = binding()
    envelope = create_approval(expected, approved_at=datetime.now(UTC))
    assert isinstance(envelope, ApprovalEnvelope)
    assert envelope.approval.approver_id == "google-sub-1"
    assert envelope.firebase_uid == "firebase-1"
    assert envelope.descriptor_hash == expected.descriptor_hash
    verify_approval(envelope, expected=expected)


def test_model_assertion_or_changed_descriptor_never_verifies() -> None:
    envelope = create_approval(binding(), approved_at=datetime.now(UTC))
    with pytest.raises(ApprovalError):
        verify_approval(envelope, expected=binding(action_scope={"kind": "apply"}))
    with pytest.raises(ApprovalError):
        verify_approval(envelope, expected=binding(firebase_uid="other"))


def test_expired_and_future_approval_are_rejected() -> None:
    now = datetime.now(UTC)
    expired = create_approval(
        binding(expires_at=now - timedelta(seconds=1)),
        approved_at=now - timedelta(minutes=2),
    )
    with pytest.raises(ApprovalError):
        verify_approval(expired, expected=expired.binding, now=now)
    envelope = create_approval(binding(expires_at=now + timedelta(seconds=1)), approved_at=now)
    with pytest.raises(ApprovalError):
        verify_approval(envelope, expected=envelope.binding, now=now + timedelta(seconds=2))


def test_native_expiry_mirror_must_preserve_microseconds() -> None:
    expires = datetime.now(UTC).replace(microsecond=123456) + timedelta(minutes=10)
    envelope = create_approval(binding(expires_at=expires), approved_at=datetime.now(UTC))
    verify_approval(envelope, expected=envelope.binding, native_expires_at=expires)
    with pytest.raises(ApprovalError):
        verify_approval(
            envelope,
            expected=envelope.binding,
            native_expires_at=expires.replace(microsecond=123000),
        )
