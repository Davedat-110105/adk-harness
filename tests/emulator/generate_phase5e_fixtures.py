"""Generate fresh complete Rules fixtures through production host factories."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from adk_harness.auth.google import LocalApprovalSession
from adk_harness.workflow.approvals import ApprovalBinding, create_approval
from adk_harness.workflow.models import ActivityEvent, ChangeSet, TaskRequest
from adk_harness.workflow.outbox import Outbox
from adk_harness.workflow.sync import (
    SyncEngine,
    WorkflowConfig,
    make_result_envelope,
    make_runtime_manifest,
)


def binding(request, *, uid, session, payload_hash, approval_type, expires):
    return ApprovalBinding(
        task_id=request.task_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        google_subject=request.user_id,
        firebase_uid=uid,
        payload_hash=payload_hash,
        action_scope=request.scope,
        resource_versions=request.resource_versions,
        policy_version=request.policy_version,
        approval_type=approval_type,
        destination="control",
        expires_at=expires,
        session_id=session.session_id,
    )


def make_negative_history(
    engine, *, project, workspace, subject, uid, session, context, now, expiry
):
    event = ActivityEvent(
        project_id=project,
        workspace_id=workspace,
        task_id="history-negative",
        actor_id="runtime-1",
        event_type="synthetic",
        details=context,
        event_id="event-negative",
        occurred_at=now,
        trace_id="trace-1",
        policy_version="policy-1",
    )
    engine.preview_history(
        [event], google_subject=subject, firebase_uid=uid, session_id=session.session_id
    )
    approval = create_approval(
        engine.history_binding(firebase_uid=uid, expires_at=expiry), approved_at=now
    )
    return engine.push_history(approval=approval)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate_phase5e_fixtures.py OUTPUT.json")
    # Keep the native timestamp nonzero while safely behind the live approval
    # usability clock, which avoids a subsecond future-time race.
    now = (datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=123456)
    project, workspace, uid, subject = "demo-adk-wire", "workspace-1", "firebase-1", "google-1"
    session = LocalApprovalSession.create()
    config = WorkflowConfig(
        project_id=project,
        workspace_id=workspace,
        control_database_id="control",
        runtime_database_id="runtime",
        session_id=session.session_id,
        session_expires_at=session.expires_at,
    )
    sqlite_path = Path(sys.argv[1]).with_suffix(".sqlite3")
    outbox = Outbox(sqlite_path)
    try:
        engine = SyncEngine(outbox, workflow_config=config)

        def instruction(result):
            if result.instruction is None:
                raise RuntimeError("production host did not return an instruction")
            return result.instruction

        common = {
            "project_id": project,
            "workspace_id": workspace,
            "user_id": subject,
            "policy_version": "policy-1",
            "trace_id": "trace-1",
            "created_at": now,
        }
        context = {
            "10": "ten",
            "2": "two",
            "nested_ts": {"type": "firestore/timestamp/1.0", "seconds": 1, "nanoseconds": 2},
            "microseconds": now.isoformat(),
        }
        expiry = now + timedelta(minutes=10)
        plan = TaskRequest(
            **common, task_id="plan-1", content="synthetic plan", intent="plan", plan=context
        )
        plan_approval = create_approval(
            binding(
                plan,
                uid=uid,
                session=session,
                payload_hash=plan.content_hash,
                approval_type="upload_run",
                expires=expiry,
            ),
            approved_at=now,
        )
        plan_result = engine.push_task(
            plan, firebase_uid=uid, approval=plan_approval, session_id=session.session_id
        )
        negative_plans = []
        for index in range(4):
            negative = TaskRequest(
                **common,
                task_id=f"negative-{index}",
                content=f"negative {index}",
                intent="plan",
                plan=context,
            )
            negative_approval = create_approval(
                binding(
                    negative,
                    uid=uid,
                    session=session,
                    payload_hash=negative.content_hash,
                    approval_type="upload_run",
                    expires=expiry,
                ),
                approved_at=now,
            )
            negative_result = engine.push_task(
                negative,
                firebase_uid=uid,
                approval=negative_approval,
                session_id=session.session_id,
            )
            negative_plans.append(
                instruction(negative_result) if negative_result.instruction is not None else None
            )
        change = ChangeSet(
            **common,
            task_id="apply-1",
            change_id="change-1",
            changes=({"operation": "calendar.events.insert", "context": context},),
        )
        apply = TaskRequest(
            **common,
            task_id="apply-1",
            content="synthetic apply",
            intent="apply",
            plan={"changeset_hash": change.content_hash},
            apply_scopes=("calendar.events",),
        )
        upload = create_approval(
            binding(
                apply,
                uid=uid,
                session=session,
                payload_hash=apply.content_hash,
                approval_type="upload_run",
                expires=expiry,
            ),
            approved_at=now,
        )
        exact = create_approval(
            binding(
                apply,
                uid=uid,
                session=session,
                payload_hash=change.content_hash,
                approval_type="exact_apply",
                expires=expiry,
            ),
            approved_at=now,
        )
        apply_result = engine.push_task(
            apply,
            firebase_uid=uid,
            approval=exact,
            upload_approval=upload,
            changeset=change,
            session_id=session.session_id,
        )
        negative_change = ChangeSet(
            **common,
            task_id="apply-negative",
            change_id="change-negative",
            changes=({"operation": "calendar.events.insert", "context": context},),
        )
        negative_apply = TaskRequest(
            **common,
            task_id="apply-negative",
            content="synthetic negative apply",
            intent="apply",
            plan={"changeset_hash": negative_change.content_hash},
            apply_scopes=("calendar.events",),
        )
        negative_upload = create_approval(
            binding(
                negative_apply,
                uid=uid,
                session=session,
                payload_hash=negative_apply.content_hash,
                approval_type="upload_run",
                expires=expiry,
            ),
            approved_at=now,
        )
        negative_exact = create_approval(
            binding(
                negative_apply,
                uid=uid,
                session=session,
                payload_hash=negative_change.content_hash,
                approval_type="exact_apply",
                expires=expiry,
            ),
            approved_at=now,
        )
        negative_apply_result = engine.push_task(
            negative_apply,
            firebase_uid=uid,
            approval=negative_exact,
            upload_approval=negative_upload,
            changeset=negative_change,
            session_id=session.session_id,
        )
        event = ActivityEvent(
            project_id=project,
            workspace_id=workspace,
            task_id="history-1",
            actor_id="runtime-1",
            event_type="synthetic",
            details=context,
            event_id="event-1",
            occurred_at=now,
            trace_id="trace-1",
            policy_version="policy-1",
        )
        engine.preview_history(
            [event], google_subject=subject, firebase_uid=uid, session_id=session.session_id
        )
        history = create_approval(
            engine.history_binding(firebase_uid=uid, expires_at=expiry), approved_at=now
        )
        history_result = engine.push_history(approval=history)
        negative_history_result = make_negative_history(
            engine,
            project=project,
            workspace=workspace,
            subject=subject,
            uid=uid,
            session=session,
            context=context,
            now=now,
            expiry=expiry,
        )
        remote_expiry = now + timedelta(hours=1)
        payload = {
            "kind": "history_result",
            "project_id": project,
            "workspace_id": workspace,
            "firebase_uid": uid,
            "google_subject": subject,
            "task_id": event.task_id,
            "scope": ["history"],
            "expires_at": remote_expiry.isoformat(),
            "events": [event.to_dict()],
        }
        manifest = make_runtime_manifest(
            project_id=project,
            workspace_id=workspace,
            firebase_uid=uid,
            google_subject=subject,
            task_id=event.task_id,
            scope=["history"],
            payload=payload,
            expires_at=remote_expiry,
        )
        envelope = make_result_envelope(payload)
        data = {
            "config": {
                "project_id": project,
                "workspace_id": workspace,
                "control_database_id": "control",
                "runtime_database_id": "runtime",
                "session_id": session.session_id,
                "session_expires_at": session.expires_at.isoformat(),
            },
            "plan": instruction(plan_result),
            "apply": instruction(apply_result),
            "negative_apply": instruction(negative_apply_result),
            "history": instruction(history_result),
            "negative_history": instruction(negative_history_result),
            "negative_plans": negative_plans,
            "manifest": manifest,
            "result_envelope": envelope,
        }
    finally:
        outbox.close()
        sqlite_path.unlink(missing_ok=True)
    Path(sys.argv[1]).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
