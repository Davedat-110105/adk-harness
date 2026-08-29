from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace

import pytest

from adk_harness.cloud.bootstrap import (
    BootstrapConfig,
    BootstrapOrchestrator,
    CheckpointStore,
    QuotaFailure,
    SetupError,
    SetupRejected,
)


@dataclass
class FakeOperation:
    name: str
    result_value: object
    done_calls: int = 0

    @property
    def operation(self):
        from google.longrunning import operations_pb2

        return operations_pb2.Operation(name=self.name, done=True)

    def done(self, timeout: float | None = None) -> bool:
        self.done_calls += 1
        return True

    def result(self, timeout: float | None = None) -> object:
        return self.result_value


class FakeProjects:
    def __init__(self) -> None:
        self.created = 0
        self.project = None

    def get_project(self, *, name: str, timeout: float):
        if self.project is not None:
            return self.project
        class Missing(Exception):
            code = 404

        raise Missing()

    def create_project(self, *, project, timeout: float):
        self.created += 1
        project.state = 1
        project.name = "projects/123"
        self.project = project
        return FakeOperation("operations/create-1", project)


class FakeBilling:
    def __init__(self) -> None:
        self.updated = 0

    def update_project_billing_info(self, *, name: str, project_billing_info, timeout: float):
        self.updated += 1
        return project_billing_info


class FakeServices:
    def __init__(self) -> None:
        self.enabled: list[str] = []

    def batch_enable_services(self, *, request, timeout: float):
        self.enabled.extend(request.service_ids)
        return FakeOperation("operations/services-1", request)


class QuotaServices(FakeServices):
    def batch_enable_services(self, *, request, timeout: float):
        error = RuntimeError("quota")
        error.code = 429
        raise error


class FlakyBilling(FakeBilling):
    def __init__(self):
        super().__init__()
        self.fail = True

    def update_project_billing_info(self, *, name: str, project_billing_info, timeout: float):
        if self.fail:
            self.fail = False
            error = RuntimeError("temporary")
            error.code = 503
            raise error
        return super().update_project_billing_info(
            name=name, project_billing_info=project_billing_info, timeout=timeout
        )


def config() -> BootstrapConfig:
    return BootstrapConfig(
        project_id="demo-project",
        parent="folders/42",
        billing_account="billingAccounts/123",
        region="northamerica-northeast1",
        services=("run.googleapis.com", "eventarc.googleapis.com"),
        iam_grants=(),
    )


def test_rejected_proposal_performs_no_external_mutation(tmp_path) -> None:
    projects, billing, services = FakeProjects(), FakeBilling(), FakeServices()
    orchestrator = BootstrapOrchestrator(
        config(),
        projects_client=projects,
        billing_client=billing,
        service_usage_client=services,
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: False,
    )

    with pytest.raises(SetupRejected):
        orchestrator.run()

    assert projects.created == billing.updated == 0
    assert services.enabled == []


def test_approved_proposal_is_deeply_immutable_and_secret_redacted() -> None:
    cfg = replace(
        config(),
        identity_platform_google_web_client_secret="super-secret",
        iam_bindings={"roles/viewer": ("user:a@example.com",)},
    )
    proposal = cfg.proposal()
    assert "super-secret" not in repr(cfg)
    assert "super-secret" not in repr(proposal)
    with pytest.raises(TypeError):
        proposal.iam_bindings["roles/viewer"] = ("user:b@example.com",)
    proposal_dict = proposal.to_dict()
    proposal_dict["iam_bindings"]["roles/viewer"].append("user:b@example.com")
    assert cfg.iam_bindings["roles/viewer"] == ("user:a@example.com",)


def test_missing_project_identity_fields_fail_closed(tmp_path) -> None:
    class MissingIdentity:
        project_id = "demo-project"

    orchestrator = BootstrapOrchestrator(
        config(),
        projects_client=type(
            "Client",
            (),
            {"get_project": lambda self, *, name, timeout: MissingIdentity()},
        )(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: True,
    )
    with pytest.raises(SetupError):
        orchestrator.run()


def test_restart_resumes_checkpoint_without_duplicate_project_creation(tmp_path) -> None:
    projects, billing, services = FakeProjects(), FakeBilling(), FakeServices()
    store = CheckpointStore(tmp_path / "setup.db")
    first = BootstrapOrchestrator(
        config(),
        projects_client=projects,
        billing_client=billing,
        service_usage_client=services,
        checkpoints=store,
        approval=lambda proposal: True,
    )
    first.run()
    second = BootstrapOrchestrator(
        config(),
        projects_client=projects,
        billing_client=billing,
        service_usage_client=services,
        checkpoints=store,
        approval=lambda proposal: True,
    )

    second.run()

    assert projects.created == 1
    assert store.get("create_project")["operation_name"] == "operations/create-1"


def test_checkpoint_store_uses_sqlite_and_rejects_tampering(tmp_path) -> None:
    store = CheckpointStore(tmp_path / "setup.db")
    store.put("step", {"status": "complete", "project_id": "demo-project"})
    assert store.get("step")["status"] == "complete"

    with sqlite3.connect(tmp_path / "setup.db") as connection:
        connection.execute(
            "UPDATE checkpoints SET payload = ? WHERE name = ?",
            ('{"status":"bad"}', "step"),
        )
        connection.commit()

    with pytest.raises(ValueError, match="checkpoint"):
        store.get("step")


def test_quota_failure_is_reported_without_retrying_mutations(tmp_path) -> None:
    services = QuotaServices()
    orchestrator = BootstrapOrchestrator(
        config(),
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=services,
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: True,
        sleep=lambda _: None,
        max_attempts=1,
    )

    with pytest.raises(QuotaFailure):
        orchestrator.run()

    assert services.enabled == []


def test_partial_setup_retry_uses_saved_project_checkpoint(tmp_path) -> None:
    projects, billing, services = FakeProjects(), FlakyBilling(), FakeServices()
    store = CheckpointStore(tmp_path / "setup.db")
    kwargs = {
        "projects_client": projects,
        "billing_client": billing,
        "service_usage_client": services,
        "checkpoints": store,
        "approval": lambda proposal: True,
        "sleep": lambda _: None,
        "max_attempts": 1,
    }
    with pytest.raises(RuntimeError, match="temporary"):
        BootstrapOrchestrator(config(), **kwargs).run()
    BootstrapOrchestrator(config(), **kwargs).run()

    assert projects.created == 1
    assert billing.updated == 1


def test_iam_merge_sends_official_options_and_preserves_etag(tmp_path) -> None:
    from google.iam.v1 import policy_pb2

    class FakeIAM:
        def __init__(self):
            self.policy = policy_pb2.Policy(version=3, etag=b"etag")
            self.policy.bindings.add(
                role="roles/run.invoker",
                members=["serviceAccount:old@example.com"],
                condition={"title": "keep", "expression": "resource.name.startsWith('x')"},
            )
            self.received = None

        def get_iam_policy(self, *, request, timeout):
            assert request.options.requested_policy_version == 3
            return self.policy

        def set_iam_policy(self, *, request, timeout):
            self.received = request
            return self.policy

    iam = FakeIAM()
    bootstrap_config = replace(
        config(), iam_bindings={"roles/run.invoker": ("serviceAccount:new@example.com",)}
    )
    BootstrapOrchestrator(
        bootstrap_config,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: True,
        iam_client=iam,
    ).run()

    assert iam.received.policy.etag == b"etag"
    assert len(iam.received.policy.bindings) == 2


def test_iam_aborted_reloads_policy_before_retry(tmp_path) -> None:
    from google.iam.v1 import policy_pb2

    class ConflictIAM:
        def __init__(self):
            self.gets = 0
            self.sets = []

        def get_iam_policy(self, *, request, timeout):
            self.gets += 1
            policy = policy_pb2.Policy(version=3, etag=f"etag-{self.gets}".encode())
            if self.gets == 2:
                policy.bindings.add(role="roles/viewer", members=["user:other@example.com"])
            return policy

        def set_iam_policy(self, *, request, timeout):
            self.sets.append(request.policy.etag)
            if len(self.sets) == 1:
                from google.api_core.exceptions import Aborted

                raise Aborted("conflict")

    iam = ConflictIAM()
    cfg = replace(
        config(),
        iam_bindings={"roles/viewer": ("user:new@example.com",)},
    )
    BootstrapOrchestrator(
        cfg,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: True,
        iam_client=iam,
        max_attempts=2,
        sleep=lambda _: None,
    ).run()
    assert iam.gets == 2
    assert iam.sets == [b"etag-1", b"etag-2"]


def test_service_usage_lost_ack_reconciles_without_resubmission(tmp_path) -> None:
    from google.api_core import exceptions
    from google.cloud import service_usage_v1 as service_usage

    class Services:
        def __init__(self):
            self.calls = 0
            self.parents = []
            self.list_parents = []

        def list_services(self, **kwargs):
            self.list_parents.append(kwargs["parent"])
            return [
                service_usage.Service(
                    name="projects/123/services/run.googleapis.com",
                    config=service_usage.ServiceConfig(name="run.googleapis.com"),
                    state=service_usage.State.ENABLED,
                )
            ]

        def batch_enable_services(self, *, request, timeout):
            self.calls += 1
            self.parents.append(request.parent)
            raise exceptions.ServiceUnavailable("lost acknowledgement")

    services = Services()
    flow = BootstrapOrchestrator(
        replace(config(), project_number="123", services=("run.googleapis.com",)),
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=services,
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        approval=lambda proposal: True,
        max_attempts=1,
    )
    with pytest.raises(SetupError, match="service enablement request failed"):
        flow._enable_services()
    flow._enable_services()
    assert services.calls == 1
    assert services.parents == ["projects/123"]
    assert services.list_parents == ["projects/123"]


def _full_template_config() -> BootstrapConfig:
    return replace(
        config(),
        project_number="123",
        control_database_location="nam5",
        runtime_database_location="us-central1",
        eventarc_trigger_location="nam5",
        receiver_cloud_run_region="us-central1",
        identity_platform_google_web_client_id="client-id.apps.googleusercontent.com",
        eventarc_trigger_service_account_email="eventarc@example.iam.gserviceaccount.com",
        receiver_container_image="us-docker.pkg.dev/demo/receiver:1",
        worker_container_image="us-docker.pkg.dev/demo/worker:1",
        workspace_secret_id="workspace-grants",
        firebase_web_app_display_name="Approval UI",
    )


def test_terraform_handoff_contains_resolved_inputs_and_stays_pending(tmp_path) -> None:
    cfg = _full_template_config()
    store = CheckpointStore(tmp_path / "setup.db")
    flow = BootstrapOrchestrator(
        cfg,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=store,
        approval=lambda proposal: True,
    )
    selected = {"project_number": "123"}
    pending = flow._prepare_terraform_handoff(selected)
    assert pending["status"] == "pending"
    assert pending["inputs"]["workspace_secret_id"] == "workspace-grants"
    assert pending["inputs"]["firebase_web_app_display_name"] == "Approval UI"
    assert "project_number" not in pending["inputs"]
    complete = {**pending, "status": "complete"}
    store.put("terraform_handoff", complete)
    assert flow._prepare_terraform_handoff(selected)["status"] == "complete"


def test_terraform_handoff_reports_missing_and_changed_inputs(tmp_path) -> None:
    cfg = config()
    store = CheckpointStore(tmp_path / "setup.db")
    flow = BootstrapOrchestrator(
        cfg,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=store,
        approval=lambda proposal: True,
    )
    pending = flow._prepare_terraform_handoff({"project_number": "123"})
    assert pending["status"] == "pending_configuration"
    assert "receiver_container_image" in pending["missing_inputs"]

    full = _full_template_config()
    full_store = CheckpointStore(tmp_path / "full.db")
    full_flow = BootstrapOrchestrator(
        full,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=full_store,
        approval=lambda proposal: True,
    )
    complete = full_flow._prepare_terraform_handoff({"project_number": "123"})
    full_store.put("terraform_handoff", {**complete, "status": "complete"})
    changed = replace(full, worker_container_image="changed.example/worker:2")
    changed_flow = BootstrapOrchestrator(
        changed,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=full_store,
        approval=lambda proposal: True,
    )
    with pytest.raises(SetupError, match="Terraform handoff"):
        changed_flow._prepare_terraform_handoff({"project_number": "123"})


def test_arbitrary_runtime_evidence_cannot_claim_ready(tmp_path) -> None:
    cfg = _full_template_config()
    store = CheckpointStore(tmp_path / "ready.db")
    flow = BootstrapOrchestrator(
        cfg,
        projects_client=FakeProjects(),
        billing_client=FakeBilling(),
        service_usage_client=FakeServices(),
        checkpoints=store,
        approval=lambda proposal: True,
    )
    selected = {
        "project_id": "demo-project",
        "project_name": "projects/123",
        "project_number": "123",
    }
    pending = flow._prepare_terraform_handoff({"project_number": "123"})
    store.put("terraform_handoff", {**pending, "status": "complete"})
    store.put(
        "rules",
        {
            "status": "complete",
            "project_id": "demo-project",
            "project_number": "123",
            "source_hash": None,
            "releases": [],
        },
    )
    store.put(
        "runtime_deployment",
        {
            "status": "complete",
            "handoff_fingerprint": pending["config_fingerprint"],
            "evidence": {"arbitrary": True},
        },
    )
    flow._ensure_project = lambda: selected
    flow._enable_billing = lambda: None
    flow._enable_services = lambda: None
    flow._ensure_iam = lambda: None
    result = flow.run()
    assert result["status"] == "awaiting_runtime_verification"
    assert result["deployment_verified"] is False
