import json
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from adk_harness.auth.google import LocalApprovalBridge, LocalApprovalSession
from adk_harness.workflow.approvals import (
    ApprovalBinding,
    ApprovalError,
    create_approval,
    verify_approval,
)
from adk_harness.workflow.models import ActivityEvent, ChangeSet, TaskRequest
from adk_harness.workflow.outbox import OperationState, Outbox
from adk_harness.workflow.sync import (
    DownloadConsent,
    ManifestReadConsent,
    SyncEngine,
    SyncOutcome,
    SyncRejected,
    WorkflowConfig,
    make_result_envelope,
    make_runtime_manifest,
)


def event() -> ActivityEvent:
    return ActivityEvent(
        task_id="task-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_type="local.edit",
        actor_id="local-actor",
        details={"file": "README.md"},
        event_id="event-1",
        occurred_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def test_history_upload_requires_explicit_approval_and_never_creates_task_request(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    engine.preview_history(
        [event()], google_subject="google-sub-1", firebase_uid="firebase-1", session_id="s1"
    )
    with pytest.raises(SyncRejected):
        engine.push_history()
    result = engine.push_history(
        approval=create_approval(
            engine.history_binding(
                firebase_uid="firebase-1",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                session_id="s1",
            ),
            approved_at=datetime.now(UTC),
        )
    )
    assert result.outcome is SyncOutcome.INSTRUCTION_READY
    assert result.instruction is not None
    acknowledged = engine.acknowledge(
        result.operation_id,
        descriptor_hash=result.instruction["descriptor_hash"],
        ack_id="ack-1",
        firebase_uid="firebase-1",
        google_subject="google-sub-1",
    )
    assert acknowledged.outcome is SyncOutcome.ACKNOWLEDGED


def test_duplicate_or_lost_ack_is_not_retried_automatically(tmp_path) -> None:
    path = tmp_path / "outbox.sqlite3"
    engine = SyncEngine(Outbox(path), workflow_config=_host_config("s1"))
    engine.preview_history(
        [event()], google_subject="google-sub-1", firebase_uid="firebase-1", session_id="s1"
    )
    result = engine.push_history(
        approval=create_approval(
            engine.history_binding(
                    firebase_uid="firebase-1",
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    session_id="s1",
            ),
            approved_at=datetime.now(UTC),
        )
    )
    assert result.instruction is not None
    engine.outbox.close()
    restarted = Outbox(path)
    assert restarted.get_instruction(result.operation_id).state.value == "unknown"
    with pytest.raises(SyncRejected):
        SyncEngine(restarted, workflow_config=_host_config("s1")).push_history(
            approval=create_approval(
                engine.history_binding(
                    firebase_uid="firebase-1", expires_at=datetime.now(UTC) + timedelta(minutes=10)
                ),
                approved_at=datetime.now(UTC),
            )
        )


def test_download_requires_metadata_consent_then_exact_result_consent(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    with pytest.raises(SyncRejected):
        engine.stage_manifest()
    metadata = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id", "result_hash"),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        session_id="s1",
    )
    instruction = engine.stage_manifest(consent=metadata)
    assert instruction["method"] == "getDoc"
    manifest = engine.receive_manifest(
        instruction["operation_id"],
        make_runtime_manifest(
            project_id="project-1",
            workspace_id="workspace-1",
            firebase_uid="firebase-1",
            google_subject="google-sub-1",
            task_id="task-1",
            scope=("history",),
            payload={
                "kind": "history_result",
                "project_id": "project-1",
                "workspace_id": "workspace-1",
                "firebase_uid": "firebase-1",
                "google_subject": "google-sub-1",
                "task_id": "task-1",
                "scope": ["history"],
                "expires_at": metadata.expires_at.isoformat(),
                "events": [event().to_dict()],
            },
            expires_at=metadata.expires_at,
        ),
        descriptor_hash=instruction["descriptor_hash"],
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
    )
    with pytest.raises(SyncRejected):
        engine.download_result()
    consent = DownloadConsent.from_manifest(metadata, manifest, scope=("history",))
    result_instruction = engine.download_result(consent=consent)
    assert result_instruction["method"] == "getDoc"


def test_manifest_refusal_makes_zero_reads_and_tampering_is_rejected(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    metadata = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id",),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        session_id="s1",
    )
    with pytest.raises(SyncRejected):
        engine.stage_manifest(consent=metadata, accepted=False)
    instruction = engine.stage_manifest(consent=metadata, accepted=True)
    assert instruction["method"] == "getDoc"


def test_phase5c_new_metadata_consent_after_restart_gets_new_attempt(tmp_path) -> None:
    path = tmp_path / "outbox.sqlite3"
    first_config = _host_config("session-first")
    first_outbox = Outbox(path)
    first_engine = SyncEngine(first_outbox, workflow_config=first_config)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    first_consent = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id", "result_hash"),
        expires_at=expires,
        session_id=first_config.session_id,
    )
    first_instruction = first_engine.stage_manifest(consent=first_consent)
    first_outbox.close()

    second_config = _host_config("session-second")
    second_outbox = Outbox(path)
    second_engine = SyncEngine(second_outbox, workflow_config=second_config)
    second_consent = replace(first_consent, session_id=second_config.session_id)
    second_instruction = second_engine.stage_manifest(consent=second_consent)
    assert second_instruction["operation_id"] != first_instruction["operation_id"]
    assert (
        second_outbox.get_instruction(first_instruction["operation_id"]).state
        is OperationState.UNKNOWN
    )
    assert (
        second_outbox.get_instruction(second_instruction["operation_id"]).state
        is OperationState.PENDING
    )
    second_outbox.close()


def test_phase5c_same_metadata_grant_shape_binds_second_manifest_result(tmp_path) -> None:
    engine = SyncEngine(
        Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("session-1")
    )
    expires = datetime.now(UTC) + timedelta(minutes=5)

    def read_fixture(item: ActivityEvent) -> dict[str, object]:
        payload = {
            "kind": "history_result",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "firebase_uid": "firebase-1",
            "google_subject": "google-sub-1",
            "task_id": "task-1",
            "scope": ["history"],
            "expires_at": expires.isoformat(),
            "events": [item.to_dict()],
        }
        return make_runtime_manifest(
            project_id="project-1",
            workspace_id="workspace-1",
            firebase_uid="firebase-1",
            google_subject="google-sub-1",
            task_id="task-1",
            scope=("history",),
            payload=payload,
            expires_at=expires,
        )

    first = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id", "result_hash"),
        expires_at=expires,
        session_id="session-1",
    )
    second = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id", "result_hash"),
        expires_at=expires,
        session_id="session-1",
    )
    first_instruction = engine.stage_manifest(consent=first)
    first_manifest = engine.receive_manifest(
        first_instruction["operation_id"],
        read_fixture(event()),
        descriptor_hash=first_instruction["descriptor_hash"],
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
    )
    second_instruction = engine.stage_manifest(consent=second)
    second_manifest = engine.receive_manifest(
        second_instruction["operation_id"],
        read_fixture(replace(event(), event_id="event-2")),
        descriptor_hash=second_instruction["descriptor_hash"],
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
    )
    assert first.descriptor_hash != second.descriptor_hash
    assert first_manifest["result_id"] != second_manifest["result_id"]
    download = engine.download_result(
        consent=DownloadConsent.from_manifest(second, second_manifest, scope=("history",))
    )
    assert second_manifest["result_id"] in download["path"]


def test_history_consent_returns_browser_instruction_and_acknowledges_once(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    engine.preview_history(
        [event()], google_subject="google-sub-1", firebase_uid="firebase-1", session_id="s1"
    )
    result = engine.push_history(
        approval=create_approval(
            engine.history_binding(
                firebase_uid="firebase-1",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                session_id="s1",
            ),
            approved_at=datetime.now(UTC),
        )
    )
    assert result.instruction is not None
    assert result.instruction["sdk"] == "firebase/firestore/lite"
    assert result.instruction["database"] == "control-db"
    assert result.instruction["writes"]
    acknowledged = engine.acknowledge(
        result.operation_id,
        descriptor_hash=result.instruction["descriptor_hash"],
        ack_id="commit-1",
        firebase_uid="firebase-1",
        google_subject="google-sub-1",
    )
    assert acknowledged.outcome is SyncOutcome.ACKNOWLEDGED
    with pytest.raises(SyncRejected):
        engine.acknowledge(
            result.operation_id,
            descriptor_hash=result.instruction["descriptor_hash"],
            ack_id="commit-2",
            firebase_uid="firebase-1",
            google_subject="google-sub-1",
        )


def test_apply_instruction_requires_distinct_upload_and_exact_apply_approvals(tmp_path) -> None:
    request = TaskRequest(
        project_id="project-1",
        workspace_id="workspace-1",
        user_id="google-sub-1",
        content="apply",
        intent="apply",
        plan={"changeset_hash": "0" * 64},
    )
    changes = ChangeSet(
        task_id=request.task_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        user_id=request.user_id,
        changes=({"kind": "calendar_create_event"},),
    )
    request = TaskRequest.from_dict(
        request.to_dict() | {"plan": {"changeset_hash": changes.content_hash}}
    )
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    engine = SyncEngine(outbox, workflow_config=_host_config("s1"))
    upload_binding = ApprovalBinding(
        task_id=request.task_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        google_subject=request.user_id,
        firebase_uid="firebase-1",
        payload_hash=request.content_hash,
        action_scope=request.scope,
        resource_versions=request.resource_versions,
        policy_version=request.policy_version,
        approval_type="upload_run",
        destination="control",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        session_id="s1",
    )
    exact_binding = ApprovalBinding(
        task_id=request.task_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        google_subject=request.user_id,
        firebase_uid="firebase-1",
        payload_hash=changes.content_hash,
        action_scope=request.scope,
        resource_versions=request.resource_versions,
        policy_version=request.policy_version,
        approval_type="exact_apply",
        destination="control",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        session_id="s1",
    )
    exact = create_approval(exact_binding, approved_at=datetime.now(UTC))
    with pytest.raises(SyncRejected):
        engine.push_task(
            request,
            firebase_uid="firebase-1",
            approval=exact,
            changeset=changes,
            session_id="s1",
        )
    upload = create_approval(upload_binding, approved_at=datetime.now(UTC))
    result = engine.push_task(
        request,
        firebase_uid="firebase-1",
        approval=exact,
        upload_approval=upload,
        changeset=changes,
        session_id="s1",
    )
    assert result.instruction is not None
    assert len(result.instruction["writes"]) == 3
    assert result.instruction["writes"][0]["data"]["request_id"] != request.task_id


def test_bridge_callbacks_map_consent_and_ack_to_durable_operation(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    callbacks = engine.bridge_callbacks()
    identity = {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"}
    preview = callbacks["workflow_preview"](
        {"kind": "history_upload", "records": [event().to_dict()], "sessionId": "s1"}, identity
    )
    consent = callbacks["workflow_consent"](
        {
            "operationId": preview["operation_id"],
            "descriptorHash": preview["descriptor_hash"],
            "consent": True,
            "sessionId": "s1",
        },
        identity,
    )
    assert consent["instruction"]["sdk"] == "firebase/firestore/lite"
    ack = callbacks["workflow_ack"](
        {
            "operationId": consent["operation_id"],
            "descriptorHash": consent["descriptor_hash"],
            "ackId": "ack-1",
            "sessionId": "s1",
        },
        identity,
    )
    assert ack["status"] == "acknowledged"


def test_history_callback_freezes_each_preview_when_a_later_preview_is_created(tmp_path) -> None:
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    callbacks = engine.bridge_callbacks()
    identity = {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"}
    first = callbacks["workflow_preview"](
        {"kind": "history_upload", "records": [event().to_dict()], "sessionId": "s1"}, identity
    )
    second_event = event().to_dict() | {"event_id": "event-2"}
    second = callbacks["workflow_preview"](
        {"kind": "history_upload", "records": [second_event], "sessionId": "s1"}, identity
    )
    assert first["payload_hash"] != second["payload_hash"]
    consent = callbacks["workflow_consent"](
        {
            "operationId": first["operation_id"],
            "descriptorHash": first["descriptor_hash"],
            "consent": True,
            "sessionId": "s1",
        },
        identity,
    )
    assert consent["instruction"]["writes"][0]["data"]["event_ids"] == ["event-1"]


def test_phase5c_same_payload_previews_retain_distinct_expiry_challenges(tmp_path) -> None:
    engine = SyncEngine(
        Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1")
    )
    callbacks = engine.bridge_callbacks()
    identity = {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"}
    same_event = event()
    first = callbacks["workflow_preview"](
        {
            "kind": "history_upload",
            "records": [same_event.to_dict()],
            "sessionId": "s1",
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=4)).isoformat(),
        },
        identity,
    )
    second = callbacks["workflow_preview"](
        {
            "kind": "history_upload",
            "records": [same_event.to_dict()],
            "sessionId": "s1",
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
        identity,
    )
    assert first["operation_id"] != second["operation_id"]
    assert first["payload_hash"] == second["payload_hash"]


def test_phase5c_result_download_requires_the_complete_manifest_scope(tmp_path) -> None:
    expires = datetime.now(UTC) + timedelta(minutes=5)
    metadata = ManifestReadConsent(
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        task_id="task-1",
        fields=("result_id",),
        expires_at=expires,
        session_id="s1",
    )
    payload = {
        "kind": "history_result",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "firebase_uid": "firebase-1",
        "google_subject": "google-sub-1",
        "task_id": "task-1",
        "scope": ["history", "calendar"],
        "expires_at": expires.isoformat(),
        "events": [event().to_dict()],
    }
    manifest = make_runtime_manifest(
        project_id="project-1",
        workspace_id="workspace-1",
        firebase_uid="firebase-1",
        google_subject="google-sub-1",
        task_id="task-1",
        scope=("history", "calendar"),
        payload=payload,
        expires_at=expires,
    )
    with pytest.raises(SyncRejected):
        DownloadConsent.from_manifest(metadata, manifest, scope=("history",))


def test_callback_rejects_generic_descriptor_echo_and_mints_task_approvals(tmp_path) -> None:
    request = TaskRequest(
        project_id="project-1",
        workspace_id="workspace-1",
        user_id="google-sub-1",
        content="plan",
        intent="plan",
        task_id="task-plan",
    )
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=_host_config("s1"))
    callbacks = engine.bridge_callbacks()
    identity = {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"}
    with pytest.raises(SyncRejected):
        callbacks["workflow_preview"]({"kind": "unknown", "descriptor": {"x": 1}}, identity)
    preview = callbacks["workflow_preview"](
        {"kind": "task_request", "request": request.to_dict(), "sessionId": "s1"}, identity
    )
    consent = callbacks["workflow_consent"](
        {
            "operationId": preview["operation_id"],
            "descriptorHash": preview["descriptor_hash"],
            "consent": True,
            "sessionId": "s1",
        },
        identity,
    )
    assert len(consent["instruction"]["writes"]) == 2
    assert consent["instruction"]["writes"][1]["data"]["approval_type"] == "upload_run"


def _host_config(session_id: str) -> WorkflowConfig:
    return WorkflowConfig(
        project_id="project-1",
        workspace_id="workspace-1",
        control_database_id="control-db",
        runtime_database_id="runtime-db",
        session_id=session_id,
        session_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


def _bridge_post(
    session: LocalApprovalSession,
    headers: dict[str, str],
    path: str,
    body: dict[str, object],
) -> dict[str, object]:
    request = urllib.request.Request(
        f"{session.origin}{path}",
        method="POST",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    return json.loads(urllib.request.urlopen(request, timeout=2).read())


def _test_bridge(
    engine: SyncEngine, session: LocalApprovalSession, config: WorkflowConfig
) -> LocalApprovalBridge:
    return LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {},
        workflow_config={
            "project_id": config.project_id,
            "workspace_id": config.workspace_id,
            "control_database_id": config.control_database_id,
            "runtime_database_id": config.runtime_database_id,
            "session_id": config.session_id,
            "session_expires_at": config.session_expires_at.isoformat(),
        },
        firebase_binding=lambda body: {
            "firebaseUid": "firebase-1",
            "googleSubject": "google-sub-1",
        },
        **engine.bridge_callbacks(),
    )


def test_phase5c_real_http_manifest_and_exact_result_flow(tmp_path) -> None:
    session = LocalApprovalSession.create()
    config = _host_config(session.session_id)
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    engine = SyncEngine(outbox, workflow_config=config)
    bridge = _test_bridge(engine, session, config)
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    metadata_expiry = datetime.now(UTC) + timedelta(minutes=2)
    download_expiry = datetime.now(UTC) + timedelta(minutes=4)
    remote_expiry = datetime.now(UTC) + timedelta(minutes=10)
    common = {
        "firebaseIdToken": "opaque",
        "projectId": config.project_id,
        "workspaceId": config.workspace_id,
        "taskId": "task-1",
        "sessionId": session.session_id,
        "expiresAt": metadata_expiry.isoformat(),
    }
    try:
        manifest_preview = _bridge_post(
            session,
            headers,
            "/api/workflow/preview",
            common | {"kind": "bounded_manifest_read", "fields": ["result_id", "result_hash"]},
        )
        manifest_consent = _bridge_post(
            session,
            headers,
            "/api/workflow/consent",
            {
                "firebaseIdToken": "opaque",
                "operationId": manifest_preview["operation_id"],
                "descriptorHash": manifest_preview["descriptor_hash"],
                "consent": True,
                "sessionId": session.session_id,
                "expiresAt": metadata_expiry.isoformat(),
            },
        )
        manifest_instruction = manifest_consent["instruction"]
        payload = {
            "kind": "history_result",
            "project_id": config.project_id,
            "workspace_id": config.workspace_id,
            "firebase_uid": "firebase-1",
            "google_subject": "google-sub-1",
            "task_id": "task-1",
            "scope": ["history"],
            "expires_at": remote_expiry.isoformat(),
            "events": [event().to_dict()],
        }
        manifest = make_runtime_manifest(
            project_id=config.project_id,
            workspace_id=config.workspace_id,
            firebase_uid="firebase-1",
            google_subject="google-sub-1",
            task_id="task-1",
            scope=("history",),
            payload=payload,
            expires_at=remote_expiry,
        )
        manifest_ack = _bridge_post(
            session,
            headers,
            "/api/workflow/ack",
            {
                "firebaseIdToken": "opaque",
                "operationId": manifest_instruction["operation_id"],
                "descriptorHash": manifest_instruction["descriptor_hash"],
                "sessionId": session.session_id,
                "manifest": manifest,
            },
        )
        assert manifest_ack["status"] == "acknowledged"
        result_preview = _bridge_post(
            session,
            headers,
            "/api/workflow/preview",
            common
            | {
                "kind": "exact_result_download",
                "metadataDescriptorHash": manifest_preview["descriptor_hash"],
                "scope": ["history"],
                "expiresAt": download_expiry.isoformat(),
            },
        )
        result_consent = _bridge_post(
            session,
            headers,
            "/api/workflow/consent",
            {
                "firebaseIdToken": "opaque",
                "operationId": result_preview["operation_id"],
                "descriptorHash": result_preview["descriptor_hash"],
                "consent": True,
                "sessionId": session.session_id,
                "expiresAt": download_expiry.isoformat(),
            },
        )
        result_instruction = result_consent["instruction"]
        result = make_result_envelope(payload)
        result["expires_at_ts"] = {
            "type": "firestore/timestamp/1.0",
            "seconds": int(remote_expiry.timestamp()),
            "nanoseconds": remote_expiry.microsecond * 1000,
        }
        result_ack = _bridge_post(
            session,
            headers,
            "/api/workflow/ack",
            {
                "firebaseIdToken": "opaque",
                "operationId": result_instruction["operation_id"],
                "descriptorHash": result_instruction["descriptor_hash"],
                "sessionId": session.session_id,
                "result": result,
            },
        )
        assert result_ack["status"] == "acknowledged"
        assert outbox.imported_history("event-1").event_id == "event-1"
    finally:
        bridge.stop()
        outbox.close()


def test_phase5c_real_http_reconciliation_requires_bounded_read_consent(tmp_path) -> None:
    session = LocalApprovalSession.create()
    config = _host_config(session.session_id)
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    engine = SyncEngine(outbox, workflow_config=config)
    bridge = _test_bridge(engine, session, config)
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    try:
        preview = _bridge_post(
            session,
            headers,
            "/api/workflow/preview",
            {
                "firebaseIdToken": "opaque",
                "kind": "history_upload",
                "records": [event().to_dict()],
                "projectId": config.project_id,
                "workspaceId": config.workspace_id,
                "sessionId": session.session_id,
            },
        )
        consent = _bridge_post(
            session,
            headers,
            "/api/workflow/consent",
            {
                "firebaseIdToken": "opaque",
                "operationId": preview["operation_id"],
                "descriptorHash": preview["descriptor_hash"],
                "consent": True,
                "sessionId": session.session_id,
            },
        )
        upload_instruction = consent["instruction"]
        unknown = _bridge_post(
            session,
            headers,
            "/api/workflow/ack",
            {
                "firebaseIdToken": "opaque",
                "operationId": upload_instruction["operation_id"],
                "descriptorHash": upload_instruction["descriptor_hash"],
                "sessionId": session.session_id,
                "status": "unknown",
            },
        )
        assert unknown["status"] == "unknown"
        bad_workspace = SyncEngine(
            outbox,
            workflow_config=replace(config, workspace_id="other-workspace", session_id="bad-ws"),
        )
        with pytest.raises(SyncRejected):
            bad_workspace.bridge_callbacks()["workflow_preview"](
                {
                    "kind": "reconciliation",
                    "operationId": upload_instruction["operation_id"],
                    "descriptorHash": upload_instruction["descriptor_hash"],
                    "sessionId": "bad-ws",
                },
                {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"},
            )
        bad_database = SyncEngine(
            outbox,
            workflow_config=replace(config, control_database_id="other-db", session_id="bad-db"),
        )
        with pytest.raises(SyncRejected):
            bad_database.bridge_callbacks()["workflow_preview"](
                {
                    "kind": "reconciliation",
                    "operationId": upload_instruction["operation_id"],
                    "descriptorHash": upload_instruction["descriptor_hash"],
                    "sessionId": "bad-db",
                },
                {"googleSubject": "google-sub-1", "firebaseUid": "firebase-1"},
            )
        with pytest.raises(urllib.error.HTTPError) as direct_error:
            _bridge_post(
                session,
                headers,
                "/api/workflow/reconcile",
                {
                    "firebaseIdToken": "opaque",
                    "operationId": upload_instruction["operation_id"],
                    "descriptorHash": upload_instruction["descriptor_hash"],
                    "sessionId": session.session_id,
                    "ackId": "forged-receipt",
                    "observed": {"documents": [{"path": "forged", "data": {}}]},
                },
            )
        assert direct_error.value.code == 403
        recon_preview = _bridge_post(
            session,
            headers,
            "/api/workflow/preview",
            {
                "firebaseIdToken": "opaque",
                "kind": "reconciliation",
                "operationId": upload_instruction["operation_id"],
                "descriptorHash": upload_instruction["descriptor_hash"],
                "projectId": config.project_id,
                "workspaceId": config.workspace_id,
                "sessionId": session.session_id,
            },
        )
        recon_consent = _bridge_post(
            session,
            headers,
            "/api/workflow/consent",
            {
                "firebaseIdToken": "opaque",
                "operationId": recon_preview["operation_id"],
                "descriptorHash": recon_preview["descriptor_hash"],
                "consent": True,
                "sessionId": session.session_id,
            },
        )
        read_instruction = recon_consent["instruction"]
        expected = upload_instruction["writes"][0]
        result = _bridge_post(
            session,
            headers,
            "/api/workflow/ack",
            {
                "firebaseIdToken": "opaque",
                "operationId": read_instruction["operation_id"],
                "descriptorHash": read_instruction["descriptor_hash"],
                "sessionId": session.session_id,
                "ackId": "commit-reconciled",
                "observed": {
                    "documents": [{"path": expected["path"], "data": expected["data"]}]
                },
            },
        )
        assert result["status"] == "acknowledged"
        assert (
            outbox.get_instruction(upload_instruction["operation_id"]).state
            is OperationState.ACKNOWLEDGED
        )
    finally:
        bridge.stop()
        outbox.close()


def test_phase5c_session_binding_and_result_hash_boundary(tmp_path) -> None:
    config = _host_config("session-1")
    engine = SyncEngine(Outbox(tmp_path / "outbox.sqlite3"), workflow_config=config)
    binding = ApprovalBinding(
        task_id="task-1",
        project_id="project-1",
        workspace_id="workspace-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
        payload_hash="a" * 64,
        action_scope={"kind": "history_upload"},
        resource_versions={},
        policy_version="policy-1",
        approval_type="history_upload",
        destination="control",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        session_id=config.session_id,
    )
    envelope = create_approval(binding, approved_at=datetime.now(UTC))
    assert binding.descriptor()["session_id"] == config.session_id
    verify_approval(envelope, expected=binding)
    with pytest.raises(ApprovalError):
        verify_approval(envelope, expected=replace(binding, session_id="other"))
    result = make_result_envelope(
        {
            "kind": "history_result",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "firebase_uid": "firebase-1",
            "google_subject": "google-sub-1",
            "task_id": "task-1",
            "scope": ["history"],
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "events": [event().to_dict()],
        }
    )
    assert result["result_id"] == result["result_hash"]
    assert result["result_hash"] not in result["canonical_payload"]
    assert engine.workflow_config is config


def test_phase5c_real_bridge_uses_trusted_database_and_releases_once(tmp_path) -> None:
    session = LocalApprovalSession.create()
    config = _host_config(session.session_id)
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    engine = SyncEngine(outbox, workflow_config=config)
    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {},
        workflow_config={
            "project_id": config.project_id,
            "workspace_id": config.workspace_id,
            "control_database_id": config.control_database_id,
            "runtime_database_id": config.runtime_database_id,
            "session_id": session.session_id,
            "session_expires_at": config.session_expires_at.isoformat(),
        },
        firebase_binding=lambda body: {
            "firebaseUid": "firebase-1",
            "googleSubject": "google-sub-1",
        },
        **engine.bridge_callbacks(),
    )
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    try:
        body = {
            "firebaseIdToken": "opaque",
            "kind": "history_upload",
            "records": [event().to_dict()],
            "sessionId": session.session_id,
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
        request = urllib.request.Request(
            f"{session.origin}/api/workflow/preview",
            method="POST",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        preview = json.loads(urllib.request.urlopen(request, timeout=2).read())
        body = {
            "firebaseIdToken": "opaque",
            "operationId": preview["operation_id"],
            "descriptorHash": preview["descriptor_hash"],
            "consent": True,
            "sessionId": session.session_id,
        }
        request = urllib.request.Request(
            f"{session.origin}/api/workflow/consent",
            method="POST",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        consent = json.loads(urllib.request.urlopen(request, timeout=2).read())
        assert consent["instruction"]["database"] == config.control_database_id
        assert consent["instruction"]["session_id"] == session.session_id
    finally:
        bridge.stop()
        outbox.close()


def test_phase5c_import_history_is_durable_without_outgoing_replay(tmp_path) -> None:
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    engine = SyncEngine(outbox, workflow_config=_host_config("session-1"))
    expires = datetime.now(UTC) + timedelta(minutes=5)
    payload = {
        "kind": "history_result",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "firebase_uid": "firebase-1",
        "google_subject": "google-sub-1",
        "task_id": "task-1",
        "scope": ["history"],
        "expires_at": expires.isoformat(),
        "events": [event().to_dict()],
    }
    result = make_result_envelope(payload)
    result["expires_at_ts"] = {
        "type": "firestore/timestamp/1.0",
        "seconds": int(expires.timestamp()),
        "nanoseconds": expires.microsecond * 1000,
    }
    imported = engine.import_history(
        result,
        project_id="project-1",
        workspace_id="workspace-1",
        task_id="task-1",
        google_subject="google-sub-1",
        firebase_uid="firebase-1",
    )
    assert imported[0].event_id == outbox.imported_history("event-1").event_id
    assert outbox.pending() == []
    outbox.close()
