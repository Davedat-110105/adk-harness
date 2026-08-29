from datetime import UTC, datetime

import pytest

from adk_harness.workflow.models import ActivityEvent
from adk_harness.workflow.outbox import Outbox, OutboxConflict, OutboxState


def event(event_id: str = "event-1") -> ActivityEvent:
    return ActivityEvent(
        task_id="task-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_type="local.edit",
        actor_id="google-sub-1",
        details={"file": "README.md"},
        occurred_at=datetime(2030, 1, 1, tzinfo=UTC),
        event_id=event_id,
    )


def test_sqlite_outbox_survives_restart_and_deduplicates_stable_event_ids(tmp_path) -> None:
    path = tmp_path / "outbox.sqlite3"
    first = Outbox(path)
    first.enqueue_history([event()])
    first.close()

    second = Outbox(path)
    records = second.pending()
    assert len(records) == 1
    assert records[0].event_id == "event-1"
    with pytest.raises(OutboxConflict):
        second.enqueue_history([event()])
    second.mark_uploaded("event-1", ack_id="ack-1")
    second.close()

    third = Outbox(path)
    assert third.pending() == []
    assert third.get("event-1").state is OutboxState.UPLOADED


def test_unknown_ack_is_retained_for_explicit_reconciliation(tmp_path) -> None:
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue_history([event()])
    outbox.mark_unknown("event-1", "connection lost")
    assert outbox.get("event-1").state is OutboxState.UNKNOWN
    assert outbox.pending(include_unknown=False) == []
    assert [item.event_id for item in outbox.pending(include_unknown=True)] == ["event-1"]


def test_outbox_rejects_unbounded_batch_before_transfer(tmp_path) -> None:
    outbox = Outbox(tmp_path / "outbox.sqlite3", max_events=1)
    with pytest.raises(ValueError, match="batch"):
        outbox.enqueue_history([event("one"), event("two")])


def test_instruction_is_durable_and_duplicate_claim_returns_same_instruction(tmp_path) -> None:
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    first = outbox.claim_instruction(
        operation_id="op-1",
        owner_google_subject="google-sub-1",
        firebase_uid="firebase-1",
        project_id="project-1",
        workspace_id="workspace-1",
        namespace="control",
        descriptor={"kind": "history_upload", "event_ids": ["event-1"]},
        payload={"method": "writeBatch", "writes": []},
    )
    second = outbox.claim_instruction(
        operation_id="op-1",
        owner_google_subject="google-sub-1",
        firebase_uid="firebase-1",
        project_id="project-1",
        workspace_id="workspace-1",
        namespace="control",
        descriptor={"kind": "history_upload", "event_ids": ["event-1"]},
        payload={"method": "writeBatch", "writes": []},
    )
    assert first.operation_id == second.operation_id == "op-1"
    assert first.instruction == second.instruction


def test_unresolved_instruction_becomes_unknown_after_restart(tmp_path) -> None:
    path = tmp_path / "outbox.sqlite3"
    first = Outbox(path)
    first.claim_instruction(
        operation_id="op-1",
        owner_google_subject="g",
        firebase_uid="f",
        project_id="p",
        workspace_id="w",
        namespace="control",
        descriptor={"kind": "history_upload"},
        payload={"method": "writeBatch", "writes": []},
    )
    first.close()
    second = Outbox(path)
    assert second.get_instruction("op-1").state.value == "unknown"
    with pytest.raises(ValueError, match="unknown"):
        second.claim_instruction(
            operation_id="op-1",
            owner_google_subject="g",
            firebase_uid="f",
            project_id="p",
            workspace_id="w",
            namespace="control",
            descriptor={"kind": "history_upload"},
            payload={"method": "writeBatch", "writes": []},
        )


def test_duplicate_claim_reports_status_without_a_second_release(tmp_path) -> None:
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    first = outbox.claim_instruction(
        operation_id="op-1",
        owner_google_subject="g",
        firebase_uid="f",
        project_id="p",
        workspace_id="w",
        namespace="control",
        descriptor={"kind": "history_upload"},
        payload={"method": "writeBatch", "writes": []},
    )
    second = outbox.claim_instruction(
        operation_id="op-1",
        owner_google_subject="g",
        firebase_uid="f",
        project_id="p",
        workspace_id="w",
        namespace="control",
        descriptor={"kind": "history_upload"},
        payload={"method": "writeBatch", "writes": []},
    )
    assert first.released is True
    assert second.released is False
