from datetime import UTC, datetime

from adk_harness.workflow.outbox import Outbox
from adk_harness.workflow.sync import SyncEngine, WorkflowConfig


def test_restarted_session_exposes_unknown_for_fresh_recovery_consent(tmp_path) -> None:
    config = WorkflowConfig(
        project_id="project-1", workspace_id="workspace-1", control_database_id="control",
        runtime_database_id="runtime", session_id="session-2",
        session_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    outbox = Outbox(tmp_path / "workflow.sqlite3")
    outbox.claim_instruction(
        operation_id="op-1", owner_google_subject="google-sub", firebase_uid="firebase-uid",
        project_id="project-1", workspace_id="workspace-1", namespace="control",
        descriptor={
            "kind": "task_request",
            "session_id": "session-1",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
        payload={"database": "control", "method": "writeBatch", "writes": []},
    )
    outbox.mark_operation_unknown("op-1", "lost response")
    callbacks = SyncEngine(outbox, workflow_config=config).bridge_callbacks()
    result = callbacks["workflow_recovery"](
        {"sessionId": "session-2"}, {"googleSubject": "google-sub", "firebaseUid": "firebase-uid"}
    )
    assert result["stage"] == "recovery"
    assert result["operations"][0]["operation_id"] == "op-1"


def test_restart_reconciles_unknown_only_after_new_read_consent(tmp_path) -> None:
    config = WorkflowConfig(
        project_id="project-1", workspace_id="workspace-1", control_database_id="control",
        runtime_database_id="runtime", session_id="session-2",
        session_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    outbox = Outbox(tmp_path / "workflow.sqlite3")
    old_descriptor = {
        "kind": "history_upload", "task_id": "task-1", "session_id": "session-1",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    path = "projects/project-1/workspaces/workspace-1/members/firebase-uid/requests/task-1"
    outbox.claim_instruction(
        operation_id="op-1", owner_google_subject="google-sub", firebase_uid="firebase-uid",
        project_id="project-1", workspace_id="workspace-1", namespace="control",
        descriptor=old_descriptor,
        payload={
            "database": "control", "method": "writeBatch",
            "writes": [{"path": path, "data": {"x": 1}}],
        },
    )
    outbox.mark_operation_unknown("op-1", "lost response")
    engine = SyncEngine(outbox, workflow_config=config)
    callbacks = engine.bridge_callbacks()
    identity = {"googleSubject": "google-sub", "firebaseUid": "firebase-uid"}
    recovery = callbacks["workflow_recovery"]({"sessionId": "session-2"}, identity)
    assert recovery["operations"][0]["descriptor"] == old_descriptor
    target_hash = recovery["operations"][0]["descriptor_hash"]

    preview = callbacks["workflow_preview"](
        {
            "kind": "reconciliation", "operationId": "op-1",
            "descriptorHash": target_hash, "sessionId": "session-2",
        },
        identity,
    )
    assert preview["transfer"]["sdk_calls"] == 0
    assert outbox.get_instruction("op-1").state.value == "unknown"
    consent = callbacks["workflow_consent"](
        {
            "operationId": preview["operation_id"],
            "descriptorHash": preview["descriptor_hash"],
            "sessionId": "session-2", "consent": True,
        },
        identity,
    )
    instruction = consent["instruction"]
    assert instruction["operation_id"] != "op-1"
    assert instruction["method"] == "getDoc"
    assert outbox.get_instruction("op-1").descriptor == old_descriptor

    acknowledged = callbacks["workflow_ack"](
        {
            "operationId": instruction["operation_id"],
            "descriptorHash": instruction["descriptor_hash"],
            "sessionId": "session-2",
            "observed": {"documents": [{"path": path, "data": {"x": 1}}]},
        },
        identity,
    )
    assert acknowledged["status"] == "acknowledged"
    assert outbox.get_instruction("op-1").state.value == "acknowledged"
