from __future__ import annotations

from adk_harness.cloud.readiness import ReadinessStatus, RuntimeReadinessVerifier


def _handoff() -> dict[str, object]:
    return {
        "project_id": "demo-project",
        "project_number": "123456",
        "parent": "folders/42",
        "receiver_cloud_run_region": "us-central1",
        "receiver_cloud_run_service_name": "receiver",
        "worker_cloud_run_job_name": "worker",
        "receiver_runtime_service_account_email": "receiver@demo-project.iam.gserviceaccount.com",
        "worker_runtime_service_account_email": "worker@demo-project.iam.gserviceaccount.com",
        "eventarc_trigger_location": "us-central1",
        "eventarc_trigger_name": "task-request-created",
        "eventarc_trigger_service_account_email": "eventarc@demo-project.iam.gserviceaccount.com",
        "control_database_id": "control",
        "runtime_database_id": "runtime",
        "control_database_location": "nam5",
        "runtime_database_location": "nam5",
        "request_document_path_pattern": "projects/{projectId}/workspaces/{workspaceId}/members/{firebaseUid}/requests/{requestId}",
        "receiver_container_image": "us-docker.pkg.dev/demo/receiver@sha256:" + "a" * 64,
        "worker_container_image": "us-docker.pkg.dev/demo/worker@sha256:" + "b" * 64,
        "authorized_ui_domains": ["127.0.0.1"],
        "identity_platform_google_web_client_id": "client.apps.googleusercontent.com",
        "firebase_web_app_id": "1:123:web:abc",
        "rules_source_hash": "hash",
        "rules_release_names": [
            "projects/demo-project/releases/cloud.firestore/control",
            "projects/demo-project/releases/cloud.firestore/runtime",
        ],
    }


def test_readiness_without_clients_is_explicitly_awaiting_live_verification() -> None:
    report = RuntimeReadinessVerifier(_handoff(), {"project_number": "123456"}).verify()
    assert report.ready is False
    assert report.status is ReadinessStatus.AWAITING_LIVE_PROOF
    assert "project" in report.checks
    assert report.checks["project"].status is ReadinessStatus.NOT_RUN
    assert report.live_only


def test_readiness_rejects_project_number_mismatch_before_resource_reads() -> None:
    class ProjectClient:
        def get_project(self, **kwargs):
            return {
                "project_id": "demo-project",
                "parent": "folders/42",
                "state": "ACTIVE",
                "name": "projects/123456",
            }

    report = RuntimeReadinessVerifier(
        _handoff(), {"project_number": "999"}, clients={"resource_manager": ProjectClient()}
    ).verify()
    assert report.ready is False
    assert report.checks["project"].status is ReadinessStatus.MISMATCH
    assert "project_number" in report.checks["project"].detail


def test_readiness_requires_cloud_run_terminal_ready_fields() -> None:
    class Client:
        def get_service(self, **kwargs):
            return {
                "name": "projects/demo-project/locations/us-central1/services/receiver",
                "reconciling": False,
                "template": {"service_account": _handoff()["receiver_runtime_service_account_email"], "containers": [{"image": _handoff()["receiver_container_image"]}]},
            }

        def get_job(self, **kwargs):
            return {}

    report = RuntimeReadinessVerifier(
        _handoff(), {"project_number": "123456"}, clients={"run_services": Client(), "run_jobs": Client()}
    ).verify()
    assert report.checks["cloud_run"].status is ReadinessStatus.MISMATCH
    assert "latest ready revision" in report.checks["cloud_run"].detail


def test_readiness_requires_native_firestore_databases() -> None:
    class Client:
        def get_database(self, *, name, timeout):
            database_id = name.rsplit("/", 1)[-1]
            return {"name": name, "location_id": "nam5", "type_": "DATASTORE_MODE" if database_id == "control" else "FIRESTORE_NATIVE"}

    report = RuntimeReadinessVerifier(
        _handoff(), {"project_number": "123456"}, clients={"firestore_admin": Client()}
    ).verify()
    assert report.checks["databases"].status is ReadinessStatus.MISMATCH


def test_unknown_recovery_is_owner_and_namespace_scoped(tmp_path) -> None:
    from adk_harness.workflow.outbox import Outbox

    outbox = Outbox(tmp_path / "outbox.sqlite3")
    outbox.claim_instruction(
        operation_id="op-1",
        owner_google_subject="subject",
        firebase_uid="uid",
        project_id="demo-project",
        workspace_id="workspace",
        namespace="control",
        descriptor={"kind": "history_upload", "expires_at": "2099-01-01T00:00:00+00:00"},
        payload={"database": "control", "method": "writeBatch", "writes": []},
    )
    outbox.mark_operation_unknown("op-1", "lost response")
    assert (
        outbox.recovery_operations(
            owner_google_subject="subject",
            firebase_uid="uid",
            project_id="demo-project",
            workspace_id="workspace",
        )[0].operation_id
        == "op-1"
    )
    assert (
        outbox.recovery_operations(
            owner_google_subject="other",
            firebase_uid="uid",
            project_id="demo-project",
            workspace_id="workspace",
        )
        == ()
    )
