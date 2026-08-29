import json
import shutil
import subprocess
import traceback
from datetime import UTC, datetime, timedelta

import pytest
import rfc8785

from adk_harness.workflow.models import (
    ActivityEvent,
    Approval,
    ChangeSet,
    TaskRequest,
    TaskState,
    transition,
)


def _records() -> tuple[TaskRequest, ChangeSet, Approval, ActivityEvent]:
    now = datetime.now(UTC).replace(microsecond=123456) - timedelta(minutes=1)
    task = TaskRequest(
        project_id="project-π",
        workspace_id="workspace-1",
        user_id="google-sub-1",
        content="Résumé café ☕",
        intent="apply",
        plan={"steps": [{"n": 1, "value": -0.0}]},
        scope={"paths": ["docs/é.md"], "metadata": {"nested": True}},
        download_scopes=("drive.read",),
        apply_scopes=("drive.write",),
        resource_versions={"docs/é.md": "v1"},
        policy_version="policy-7",
        trace_id="trace-1",
        created_at=now,
        task_id="task-1",
    )
    change = ChangeSet(
        task_id=task.task_id,
        project_id=task.project_id,
        workspace_id=task.workspace_id,
        user_id=task.user_id,
        changes=({"path": "docs/é.md", "patch": [1, 2.5, -0.0]},),
        resource_versions=task.resource_versions,
        policy_version=task.policy_version,
        trace_id=task.trace_id,
        created_at=now,
        change_id="change-1",
    )
    approval = Approval(
        task_id=task.task_id,
        project_id=task.project_id,
        workspace_id=task.workspace_id,
        change_hash=change.content_hash,
        approver_id="google-approver-1",
        action_scope={"paths": ["docs/é.md"]},
        resource_versions=task.resource_versions,
        policy_version=task.policy_version,
        trace_id=task.trace_id,
        approved_at=now,
        expires_at=now + timedelta(hours=1),
        approval_id="approval-1",
    )
    event = ActivityEvent(
        task_id=task.task_id,
        project_id=task.project_id,
        workspace_id=task.workspace_id,
        event_type="approved",
        actor_id=approval.approver_id,
        details={"nested": [{"unicode": "naïve"}]},
        resource_versions=task.resource_versions,
        policy_version=task.policy_version,
        occurred_at=now,
        trace_id=task.trace_id,
        event_id="event-1",
    )
    return task, change, approval, event


def test_task_request_hash_binds_scope_identity_and_versions() -> None:
    task = TaskRequest(
        project_id="p1",
        workspace_id="w1",
        user_id="u1",
        content="update README",
        intent="plan",
        scope={"paths": ["README.md"]},
        resource_versions={"README.md": "v1"},
        policy_version="policy-1",
        trace_id="trace-1",
    )
    same = TaskRequest(
        project_id="p1",
        workspace_id="w1",
        user_id="u1",
        content="update README",
        intent="plan",
        scope={"paths": ["README.md"]},
        resource_versions={"README.md": "v1"},
        policy_version="policy-1",
        trace_id="trace-1",
        created_at=task.created_at,
        task_id=task.task_id,
    )
    changed = TaskRequest(
        project_id="p1",
        workspace_id="w1",
        user_id="u1",
        content="update README",
        intent="plan",
        scope={"paths": ["README.md"]},
        resource_versions={"README.md": "v2"},
        policy_version="policy-1",
        trace_id="trace-1",
        created_at=task.created_at,
        task_id=task.task_id,
    )
    assert task.content_hash == same.content_hash
    assert task.content_hash != changed.content_hash


def test_transitions_are_strict_and_approval_is_hash_bound() -> None:
    assert transition(TaskState.DRAFT, TaskState.SUBMITTED) == TaskState.SUBMITTED
    with pytest.raises(ValueError):
        transition(TaskState.DRAFT, TaskState.APPLYING)
    approval = Approval(
        task_id="t1",
        project_id="p1",
        workspace_id="w1",
        change_hash="a" * 64,
        approver_id="u2",
        approved_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    approval.require_for(
        "a" * 64,
        task_id="t1",
        approver_id="u2",
        project_id="p1",
        workspace_id="w1",
        action_scope={},
        resource_versions={},
        policy_version="policy-unknown",
        trace_id=approval.trace_id,
    )
    with pytest.raises(ValueError):
        approval.require_for(
            "b" * 64,
            task_id="t1",
            approver_id="u2",
            project_id="p1",
            workspace_id="w1",
            action_scope={},
            resource_versions={},
            policy_version="policy-1",
            trace_id=approval.trace_id,
        )


def test_change_and_activity_records_are_versioned_and_immutable() -> None:
    change = ChangeSet(
        task_id="t1",
        project_id="p1",
        workspace_id="w1",
        user_id="u1",
        changes=({"path": "README.md", "operation": "update", "content": "x"},),
        resource_versions={"README.md": "v1"},
        policy_version="policy-1",
        trace_id="trace-1",
    )
    event = ActivityEvent(
        task_id="t1",
        project_id="p1",
        workspace_id="w1",
        event_type="submitted",
        actor_id="u1",
        details={},
        resource_versions={"README.md": "v1"},
        policy_version="policy-1",
    )
    assert change.content_hash
    assert event.content_hash
    assert event.schema_version == 1
    with pytest.raises(AttributeError):
        event.event_type = "x"


def test_serialization_rejects_unknown_schema_and_bad_values() -> None:
    task = TaskRequest(project_id="p", workspace_id="w", user_id="u", content="c", intent="plan")
    restored = TaskRequest.from_dict(task.to_dict())
    assert restored.content_hash == task.content_hash
    with pytest.raises(ValueError):
        TaskRequest.from_dict(task.to_dict() | {"schema_version": 99})
    with pytest.raises(TypeError):
        TaskRequest(
            project_id="p",
            workspace_id="w",
            user_id="u",
            content="c",
            intent="plan",
            scope={1: "bad"},
        )
    with pytest.raises(ValueError):
        TaskRequest(project_id="p", workspace_id="w", user_id="u", content="c", intent="explain")


def test_approval_binds_identity_scope_and_bounded_expiry() -> None:
    now = datetime.now(UTC)
    approval = Approval(
        task_id="t",
        project_id="p",
        workspace_id="w",
        change_hash="a" * 64,
        approver_id="a",
        action_scope={"path": "x"},
        resource_versions={"x": "v1"},
        policy_version="p1",
        trace_id="tr",
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    approval.require_for(
        "a" * 64,
        task_id="t",
        approver_id="a",
        project_id="p",
        workspace_id="w",
        action_scope={"path": "x"},
        resource_versions={"x": "v1"},
        policy_version="p1",
        trace_id="tr",
    )
    with pytest.raises(ValueError):
        approval.require_for(
            "a" * 64,
            task_id="t",
            approver_id="a",
            project_id="other",
            workspace_id="w",
            action_scope={"path": "x"},
            resource_versions={"x": "v1"},
            policy_version="p1",
            trace_id="tr",
        )


def test_all_records_have_strict_round_trips_and_hashes() -> None:
    for record in _records():
        payload = record.to_dict()
        restored = type(record).from_dict(payload)
        assert restored == record
        assert restored.content_hash == record.content_hash
        assert record.canonical_bytes() == record.canonical().encode("utf-8")
        with pytest.raises(ValueError):
            type(record).from_dict(payload | {"unexpected": True})
        with pytest.raises(ValueError):
            type(record).from_dict(payload | {"schema_version": True})
    assert json.loads(_records()[0].canonical())["content"] == "Résumé café ☕"


def test_task_intent_and_state_are_validated_without_changing_intent_hash() -> None:
    task = _records()[0]
    original_hash = task.content_hash
    progressed = TaskRequest.from_dict(task.to_dict() | {"state": "submitted"})
    assert progressed.state is TaskState.SUBMITTED
    assert progressed.content_hash == original_hash
    with pytest.raises(ValueError):
        TaskRequest.from_dict(task.to_dict() | {"intent": "explain"})
    with pytest.raises(ValueError):
        TaskRequest(
            project_id="p", workspace_id="w", user_id="u", content="c", intent="plan", state="bad"
        )


def test_nested_inputs_are_frozen_and_reject_unsafe_json() -> None:
    paths = ["a"]
    nested = {"paths": paths}
    task = TaskRequest(
        project_id="p", workspace_id="w", user_id="u", content="c", intent="plan", scope=nested
    )
    paths.append("b")
    nested["new"] = "value"
    assert task.scope == {"paths": ("a",)}
    with pytest.raises(ValueError):
        TaskRequest(
            project_id="p",
            workspace_id="w",
            user_id="u",
            content="c",
            intent="plan",
            plan={"n": 2**53},
        )
    with pytest.raises(ValueError):
        TaskRequest(
            project_id="p",
            workspace_id="w",
            user_id="u",
            content="c",
            intent="plan",
            plan={"n": float("nan")},
        )
    with pytest.raises(ValueError):
        TaskRequest(
            project_id="p", workspace_id="w", user_id="u", content="bad\ud800", intent="plan"
        )


@pytest.mark.parametrize(
    "value",
    [
        "Authorization: Bearer abc.def.ghi",
        "https://example.test/callback?access_token=abc",
        "api_key=abc123",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_credential_shaped_values_are_rejected_without_echoing(value: str) -> None:
    with pytest.raises(ValueError) as exc:
        TaskRequest(project_id="p", workspace_id="w", user_id="u", content=value, intent="plan")
    assert value not in str(exc.value)
    with pytest.raises(ValueError):
        TaskRequest(
            project_id="p",
            workspace_id="w",
            user_id="u",
            content="safe",
            intent="plan",
            scope={"note": value},
        )


def test_token_count_metadata_is_allowed_and_approval_requires_every_binding() -> None:
    task, change, approval, _ = _records()
    safe = TaskRequest(
        project_id="p",
        workspace_id="w",
        user_id="u",
        content="safe",
        intent="plan",
        scope={"token_count": 4},
    )
    assert safe.scope["token_count"] == 4
    kwargs = {
        "task_id": task.task_id,
        "approver_id": approval.approver_id,
        "project_id": task.project_id,
        "workspace_id": task.workspace_id,
        "action_scope": approval.action_scope,
        "resource_versions": approval.resource_versions,
        "policy_version": approval.policy_version,
        "trace_id": approval.trace_id,
    }
    approval.require_for(change.content_hash, **kwargs)
    for key, wrong in (
        ("task_id", "wrong"),
        ("approver_id", "wrong"),
        ("policy_version", "wrong"),
        ("trace_id", "wrong"),
    ):
        with pytest.raises(ValueError):
            approval.require_for(change.content_hash, **(kwargs | {key: wrong}))


def test_approval_digest_expiry_and_future_time_are_fail_closed() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        Approval(
            task_id="t",
            project_id="p",
            workspace_id="w",
            change_hash="bad",
            approver_id="a",
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        )
    with pytest.raises(ValueError):
        Approval(
            task_id="t",
            project_id="p",
            workspace_id="w",
            change_hash="a" * 64,
            approver_id="a",
            approved_at=now,
            expires_at=None,
        )
    future = Approval(
        task_id="t",
        project_id="p",
        workspace_id="w",
        change_hash="a" * 64,
        approver_id="a",
        approved_at=now + timedelta(hours=1),
        expires_at=now + timedelta(hours=2),
    )
    with pytest.raises(ValueError):
        future.require_for(
            "a" * 64,
            task_id="t",
            approver_id="a",
            project_id="p",
            workspace_id="w",
            action_scope={},
            resource_versions={},
            policy_version="policy-unknown",
            trace_id=future.trace_id,
        )
    expired = Approval(
        task_id="t",
        project_id="p",
        workspace_id="w",
        change_hash="a" * 64,
        approver_id="a",
        approved_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    with pytest.raises(ValueError):
        expired.require_for(
            "a" * 64,
            task_id="t",
            approver_id="a",
            project_id="p",
            workspace_id="w",
            action_scope={},
            resource_versions={},
            policy_version="policy-unknown",
            trace_id=expired.trace_id,
        )


def test_approval_has_no_digest_only_public_authorization_api() -> None:
    assert not hasattr(Approval, "accepts")


def test_approval_scope_comparison_is_json_type_sensitive() -> None:
    now = datetime.now(UTC)
    approval = Approval(
        task_id="t",
        project_id="p",
        workspace_id="w",
        change_hash="a" * 64,
        approver_id="a",
        action_scope={"enabled": True, "nested": [{"count": 1}]},
        policy_version="p1",
        trace_id="tr",
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    common = {
        "task_id": "t",
        "approver_id": "a",
        "project_id": "p",
        "workspace_id": "w",
        "resource_versions": {},
        "policy_version": "p1",
        "trace_id": "tr",
    }
    approval.require_for(
        "a" * 64, action_scope={"enabled": True, "nested": [{"count": 1}]}, **common
    )
    for scope in (
        {"enabled": 1, "nested": [{"count": 1}]},
        {"enabled": True, "nested": [{"count": True}]},
    ):
        with pytest.raises(ValueError):
            approval.require_for("a" * 64, action_scope=scope, **common)


def test_invalid_deserialization_errors_do_not_chain_untrusted_values() -> None:
    task = _records()[0]
    for bad in (
        task.to_dict() | {"created_at": "access_token=synthetic-sentinel"},
        task.to_dict() | {"state": "access_token=synthetic-sentinel"},
    ):
        with pytest.raises((TypeError, ValueError)) as caught:
            TaskRequest.from_dict(bad)
        assert "synthetic-sentinel" not in "".join(traceback.format_exception(caught.value))


def test_rfc8785_independent_node_vectors_when_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    raw = (
        '{"z":{"large":1e+21,"small":1e-7,"one":1.0,"negative_zero":-0.0},'
        '"\\uE000":"bmp","😀":"astral","n":[3.1400,-2.5e+2],'
        '"2":"two","10":"ten","a":"café"}'
    ).encode()
    script = (
        "const fs = require('fs');"
        "const x = JSON.parse(fs.readFileSync(0, 'utf8'));"
        "function c(v) {"
        " if (Array.isArray(v)) return '[' + v.map(c).join(',') + ']';"
        " if (v && typeof v === 'object') return '{' + Object.keys(v).sort()"
        ".map(k => JSON.stringify(k) + ':' + c(v[k])).join(',') + '}';"
        " return JSON.stringify(v);"
        "} process.stdout.write(c(x));"
    )
    result = subprocess.run(
        [node, "-e", script], input=raw, check=True, capture_output=True, timeout=5
    )
    expected = (
        '{"10":"ten","2":"two","a":"café","n":[3.14,-250],'
        '"z":{"large":1e+21,"negative_zero":0,"one":1,"small":1e-7},'
        '"😀":"astral","":"bmp"}'
    ).encode()
    assert result.stdout == expected
    assert result.stdout == rfc8785.dumps(json.loads(raw))
