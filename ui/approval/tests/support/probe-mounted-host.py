"""Actual HTML/UI/HTTP/SyncEngine probe; synthetic auth/Firestore only."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
import json
import subprocess
import sys
import tempfile

from adk_harness.auth.google import LocalApprovalBridge, LocalApprovalSession
from adk_harness.workflow.models import ActivityEvent, ChangeSet, TaskRequest
from adk_harness.workflow.outbox import Outbox
from adk_harness.workflow.sync import SyncEngine, WorkflowConfig, make_result_envelope, make_runtime_manifest

scratch = Path(__file__).resolve().parent
root = scratch.parents[3]
failed = False
for mode in (sys.argv[1:] or ["plan", "apply", "history", "history_unknown", "history_unknown_relogin", "history_metadata_unknown", "history_two_handles", "download", "download_unknown", "history_signout", "history_signout_replace", "history_signout_success", "download_ack_withdraw", "history_consent_withdraw", "history_consent_response", "history_consent_response_withdraw", "history_consent_lost", "preview_signout_history", "preview_signout_task", "preview_signout_manifest", "preview_signout_history_failure", "preview_signout_task_failure", "preview_signout_manifest_failure"]):
    at = datetime.now(UTC).replace(microsecond=123456)
    session = LocalApprovalSession.create()
    owner = {"firebaseUid": "firebase-1", "googleSubject": "google-1"}
    config = WorkflowConfig(project_id="demo-adk-mounted", workspace_id="workspace-1", control_database_id="control", runtime_database_id="runtime", session_id=session.session_id, session_expires_at=session.expires_at)
    temp_dir = tempfile.TemporaryDirectory(prefix="adk-ui-mounted-")
    outbox = Outbox(Path(temp_dir.name) / "state.sqlite3")
    engine = SyncEngine(outbox, workflow_config=config)
    event = ActivityEvent(project_id=config.project_id, workspace_id=config.workspace_id, task_id="task-1", actor_id="runtime-1", event_type="synthetic", details={"nested_ts": "unchanged", "2": "two", "10": "ten"}, event_id="event-1", occurred_at=at, trace_id="trace-1", policy_version="policy-1")
    common = dict(project_id=config.project_id, workspace_id=config.workspace_id, task_id=event.task_id, user_id=owner["googleSubject"], policy_version="policy-1", trace_id="trace-1", created_at=at)
    change = ChangeSet(**common, change_id="change-1", changes=({"operation": "calendar.events.insert", "context": {"nested_ts": "unchanged"}},))
    task = TaskRequest(**common, content="synthetic task", intent="apply" if mode == "apply" else "plan", plan={"changeset_hash": change.content_hash} if mode == "apply" else {}, apply_scopes=("calendar.events",) if mode == "apply" else ())
    pending_history = [event.to_dict()]
    if mode == "history_capacity":
        pending_history = [{**event.to_dict(), "event_id": f"event-{index}"} for index in range(1, 9)]
    bootstrap = {"googleSubject": owner["googleSubject"], "firebaseConfig": {"apiKey": "synthetic", "authDomain": "synthetic.invalid", "projectId": config.project_id}, "setupOnly": False, "pendingHistory": pending_history, "pendingTask": {"payload": task.to_dict(), **({"changeset": change.to_dict()} if mode == "apply" else {})}}
    remote_expiry = at + timedelta(hours=1)
    payload = {"kind": "history_result", "project_id": config.project_id, "workspace_id": config.workspace_id, "firebase_uid": owner["firebaseUid"], "google_subject": owner["googleSubject"], "task_id": event.task_id, "scope": ["history"], "expires_at": remote_expiry.isoformat(), "events": [event.to_dict()]}
    manifest = make_runtime_manifest(project_id=config.project_id, workspace_id=config.workspace_id, firebase_uid=owner["firebaseUid"], google_subject=owner["googleSubject"], task_id=event.task_id, scope=["history"], payload=payload, expires_at=remote_expiry)
    envelope = {**make_result_envelope(payload), "expires_at_ts": manifest["expires_at_ts"]}
    config_dict = {"project_id": config.project_id, "workspace_id": config.workspace_id, "control_database_id": config.control_database_id, "runtime_database_id": config.runtime_database_id, "session_id": config.session_id, "session_expires_at": config.session_expires_at.isoformat()}
    bridge = LocalApprovalBridge(session=session, ui_root=root / "ui/approval", bootstrap=lambda: bootstrap, workflow_config=config_dict, firebase_binding=lambda body: owner, **engine.bridge_callbacks())
    bridge.start()
    try:
        run = subprocess.run(["node", str(scratch / "probe-mounted-host.cjs")], input=json.dumps({"mode": mode, "origin": session.origin, "capability": session.capability, "manifest": manifest, "envelope": envelope}), text=True, encoding="utf-8", capture_output=True, timeout=35)
        if run.returncode:
            raise AssertionError((run.stderr or run.stdout)[-1800:])
        result = json.loads(run.stdout)
        operation_states = [outbox.get_instruction(operation).state.value for operation in result["operations"]]
        if mode == "history_metadata_unknown":
            assert result["reconciliationTargets"] and result["reconciliationTargets"][0] == result["operations"][0], (mode, result, operation_states)
            assert operation_states[0] == "acknowledged", (mode, operation_states)
        elif mode == "history_two_handles":
            assert len(operation_states) >= 3 and operation_states[0] == "acknowledged", (mode, operation_states)
            assert result["reconciliationTargets"] and result["reconciliationTargets"][0] == result["operations"][0], (mode, result, operation_states)
            assert operation_states[2] in {"unknown", "pending"}, (mode, operation_states)
        acknowledged = 0
        for operation in result["operations"]:
            record = outbox.get_instruction(operation)
            acknowledged += int(record.state.value == "acknowledged")
            if mode in {"history_metadata_unknown", "history_two_handles"}:
                pass
            elif mode in {"history_signout", "history_signout_replace", "history_consent_response", "history_consent_response_withdraw"}:
                assert record.state.value in {"unknown", "pending"}, (mode, record.state.value)
            elif mode not in {"download_ack_withdraw", "history_consent_lost"} and not mode.startswith("preview_signout_"):
                assert record.state.value == "acknowledged", (mode, record.state.value)
            elif mode == "history_consent_lost":
                assert record.state.value == "pending", (mode, record.state.value)
        if mode == "download_ack_withdraw":
            try:
                outbox.imported_history(event.event_id)
            except KeyError:
                pass
            else:
                raise AssertionError("result imported after consent withdrawal")
        elif mode.startswith("download"):
            assert outbox.imported_history(event.event_id).event.content_hash == event.content_hash
        elif mode.startswith("history") and mode not in {"history_signout", "history_signout_replace", "history_metadata_unknown", "history_two_handles", "history_consent_withdraw", "history_consent_lost", "history_consent_response", "history_consent_response_withdraw"}:
            assert outbox.get(event.event_id).state.value == "uploaded"
        print(f"PASS mounted actual UI + HTTP host: {mode}; {acknowledged} acknowledged operations", flush=True)
    except Exception as exc:
        failed = True
        print(f"FAIL mounted actual UI + HTTP host: {mode}: {exc}", flush=True)
    finally:
        bridge.stop()
        outbox.close()
        temp_dir.cleanup()
sys.exit(1 if failed else 0)
