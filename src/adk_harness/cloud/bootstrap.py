"""Checkpointed, approval-gated GCP project bootstrap.

The orchestrator owns workflow semantics.  Resource Manager, Cloud Billing,
Service Usage and IAM calls remain official client-library calls supplied by
the caller, which keeps tests deterministic and prevents accidental live setup.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .projects import (
    BootstrapProposal,
    ProjectManager,
    ProjectNotFound,
    ProjectOperationTimeout,
    TransientProjectError,
)


class SetupError(RuntimeError):
    """Base class for setup failures."""


class SetupRejected(SetupError):
    """The trusted human declined the immutable setup proposal."""


class SetupTimeout(SetupError):
    """A setup operation exceeded its bounded deadline."""


class QuotaFailure(SetupError):
    """A service quota prevented setup; no rollback is attempted."""


TERRAFORM_DEFAULTS = {
    "control_database_id": "control",
    "runtime_database_id": "runtime",
    "eventarc_trigger_name": "task-request-created",
    "request_document_path_pattern": (
        "projects/{projectId}/workspaces/{workspaceId}/members/{firebaseUid}/requests/{requestId}"
    ),
    "authorized_ui_domains": ("localhost",),
    "firebase_web_app_display_name": "ADK Harness Approval UI",
    "eventarc_receiver_service_account_id": "eventarc-receiver",
    "worker_runtime_service_account_id": "workspace-worker",
    "receiver_cloud_run_service_name": "workspace-event-receiver",
    "worker_cloud_run_job_name": "workspace-worker",
    "workspace_secret_id": "workspace-grants",
}


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    project_id: str
    parent: str
    billing_account: str
    region: str
    services: tuple[str, ...] = ()
    iam_grants: tuple[str, ...] = ()
    display_name: str | None = None
    project_number: str | None = None
    control_database_id: str = "control"
    runtime_database_id: str = "runtime"
    eventarc_trigger_location: str | None = None
    receiver_cloud_run_region: str | None = None
    identity_platform_google_web_client_id: str | None = None
    # Compatibility input only: InitVar ensures the secret is never retained
    # by the bootstrap config, checkpoint, proposal, or repr. Terraform owns
    # the separately supplied Web IdP secret through its sensitive variable.
    identity_platform_google_web_client_secret: InitVar[str | None] = None
    authorized_ui_domains: tuple[str, ...] = ()
    iam_bindings: Any = field(default_factory=dict)
    # ``iam_owner`` is explicit because grants must have one owner.  The
    # bootstrap SDK owns bindings only when ``iam_owner == "sdk"``.
    iam_owner: str | None = None
    rules_source_hash: str | None = None
    rules_source_version: str | None = None
    control_database_location: str | None = None
    runtime_database_location: str | None = None
    eventarc_trigger_name: str | None = None
    request_document_path_pattern: str | None = None
    eventarc_trigger_service_account_email: str | None = None
    eventarc_receiver_service_account_id: str | None = None
    worker_runtime_service_account_id: str | None = None
    receiver_cloud_run_service_name: str | None = None
    worker_cloud_run_job_name: str | None = None
    receiver_container_image: str | None = None
    worker_container_image: str | None = None
    firebase_web_app_display_name: str | None = None
    workspace_secret_id: str | None = None

    def __post_init__(self, identity_platform_google_web_client_secret: str | None) -> None:
        del identity_platform_google_web_client_secret
        object.__setattr__(self, "services", tuple(self.services))
        object.__setattr__(self, "iam_grants", tuple(self.iam_grants))
        object.__setattr__(self, "authorized_ui_domains", tuple(self.authorized_ui_domains))
        object.__setattr__(
            self,
            "iam_bindings",
            MappingProxyType(
                {
                    str(role): tuple(sorted(str(member) for member in members))
                    for role, members in self.iam_bindings.items()
                }
            ),
        )

    def _template_value(self, name: str, value: Any) -> Any:
        if value is None or (isinstance(value, (tuple, list)) and not value):
            return TERRAFORM_DEFAULTS.get(name)
        return value

    def proposal(self, *, rules_binding: dict[str, Any] | None = None) -> BootstrapProposal:
        rules_binding = rules_binding or {}
        return BootstrapProposal(
            project_id=self.project_id,
            parent=self.parent,
            billing_account=self.billing_account,
            region=self.region,
            display_name=self.display_name,
            project_number=self.project_number,
            services=tuple(self.services),
            iam_grants=tuple(self.iam_grants),
            iam_bindings=dict(self.iam_bindings),
            control_database_id=self._template_value(
                "control_database_id", self.control_database_id
            ),
            runtime_database_id=self._template_value(
                "runtime_database_id", self.runtime_database_id
            ),
            authorized_ui_domains=tuple(
                self._template_value("authorized_ui_domains", self.authorized_ui_domains)
            ),
            identity_platform_google_web_client_id=self.identity_platform_google_web_client_id,
            eventarc_trigger_location=self.eventarc_trigger_location,
            receiver_cloud_run_region=self.receiver_cloud_run_region,
            rules_source_hash=rules_binding.get("source_hash", self.rules_source_hash),
            rules_source_version=rules_binding.get("source_version", self.rules_source_version),
            rules_project_id=rules_binding.get("project_id"),
            rules_project_number=rules_binding.get("project_number"),
            rules_release_names=tuple(rules_binding.get("release_names", ())),
            rules_attachment_points=tuple(rules_binding.get("attachment_points", ())),
            iam_owner=self.iam_owner,
            control_database_location=self.control_database_location,
            runtime_database_location=self.runtime_database_location,
            eventarc_trigger_name=self._template_value(
                "eventarc_trigger_name", self.eventarc_trigger_name
            ),
            request_document_path_pattern=self._template_value(
                "request_document_path_pattern", self.request_document_path_pattern
            ),
            eventarc_trigger_service_account_email=self.eventarc_trigger_service_account_email,
            eventarc_receiver_service_account_id=self._template_value(
                "eventarc_receiver_service_account_id", self.eventarc_receiver_service_account_id
            ),
            worker_runtime_service_account_id=self._template_value(
                "worker_runtime_service_account_id", self.worker_runtime_service_account_id
            ),
            receiver_cloud_run_service_name=self._template_value(
                "receiver_cloud_run_service_name", self.receiver_cloud_run_service_name
            ),
            worker_cloud_run_job_name=self._template_value(
                "worker_cloud_run_job_name", self.worker_cloud_run_job_name
            ),
            receiver_container_image=self.receiver_container_image,
            worker_container_image=self.worker_container_image,
            firebase_web_app_display_name=self._template_value(
                "firebase_web_app_display_name", self.firebase_web_app_display_name
            ),
            workspace_secret_id=self._template_value(
                "workspace_secret_id", self.workspace_secret_id
            ),
        )

    def fingerprint(self, *, rules_binding: dict[str, Any] | None = None) -> str:
        payload = {
            "project_id": self.project_id,
            "parent": self.parent,
            "billing_account": self.billing_account,
            "region": self.region,
            "services": list(self.services),
            "iam_grants": list(self.iam_grants),
            "display_name": self.display_name,
            "project_number": self.project_number,
            "control_database_id": self._template_value(
                "control_database_id", self.control_database_id
            ),
            "runtime_database_id": self._template_value(
                "runtime_database_id", self.runtime_database_id
            ),
            "eventarc_trigger_location": self.eventarc_trigger_location,
            "receiver_cloud_run_region": self.receiver_cloud_run_region,
            "identity_platform_google_web_client_id": self.identity_platform_google_web_client_id,
            "authorized_ui_domains": list(
                self._template_value("authorized_ui_domains", self.authorized_ui_domains)
            ),
            "iam_bindings": {role: list(members) for role, members in self.iam_bindings.items()},
            "iam_owner": self.iam_owner,
            "rules_source_hash": self.rules_source_hash,
            "rules_source_version": self.rules_source_version,
            "control_database_location": self.control_database_location,
            "runtime_database_location": self.runtime_database_location,
            "eventarc_trigger_name": self._template_value(
                "eventarc_trigger_name", self.eventarc_trigger_name
            ),
            "request_document_path_pattern": self._template_value(
                "request_document_path_pattern", self.request_document_path_pattern
            ),
            "eventarc_trigger_service_account_email": self.eventarc_trigger_service_account_email,
            "eventarc_receiver_service_account_id": self._template_value(
                "eventarc_receiver_service_account_id", self.eventarc_receiver_service_account_id
            ),
            "worker_runtime_service_account_id": self._template_value(
                "worker_runtime_service_account_id", self.worker_runtime_service_account_id
            ),
            "receiver_cloud_run_service_name": self._template_value(
                "receiver_cloud_run_service_name", self.receiver_cloud_run_service_name
            ),
            "worker_cloud_run_job_name": self._template_value(
                "worker_cloud_run_job_name", self.worker_cloud_run_job_name
            ),
            "firebase_web_app_display_name": self._template_value(
                "firebase_web_app_display_name", self.firebase_web_app_display_name
            ),
            "workspace_secret_id": self._template_value(
                "workspace_secret_id", self.workspace_secret_id
            ),
            "receiver_container_image": self.receiver_container_image,
            "worker_container_image": self.worker_container_image,
        }
        payload["rules_binding"] = rules_binding or {}
        # This field is converted to a plain mapping so its canonical form is
        # independent of the immutable view used by BootstrapConfig.
        payload["iam_bindings"] = {
            role: list(members) for role, members in self.iam_bindings.items()
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class CheckpointStore:
    """SQLite-backed setup checkpoints with tamper detection."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints ("
                "name TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL)"
            )
            db.commit()

    @staticmethod
    def _encode(value: dict[str, Any]) -> tuple[str, str]:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return payload, digest

    def put(self, name: str, value: dict[str, Any]) -> None:
        payload, digest = self._encode(value)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO checkpoints(name,payload,digest) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,digest=excluded.digest",
                (name, payload, digest),
            )
            db.commit()

    def get(self, name: str, default: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT payload,digest FROM checkpoints WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            return default
        payload, digest = row
        if not isinstance(payload, str) or not isinstance(digest, str):
            raise ValueError("checkpoint is malformed")
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(expected, digest):
            raise ValueError("checkpoint integrity validation failed")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("checkpoint payload is invalid")
        return value


def _is_transient(error: BaseException) -> bool:
    return isinstance(error, TransientProjectError) or getattr(error, "code", None) in {
        408,
        429,
        500,
        502,
        503,
        504,
        "ABORTED",
        "DEADLINE_EXCEEDED",
        "RESOURCE_EXHAUSTED",
        "SERVICE_UNAVAILABLE",
    }


class BootstrapOrchestrator:
    """Run setup once, recording every externally visible checkpoint."""

    def __init__(
        self,
        config: BootstrapConfig,
        *,
        projects_client: Any,
        billing_client: Any,
        service_usage_client: Any,
        checkpoints: CheckpointStore,
        approval: Callable[[BootstrapProposal], bool],
        iam_client: Any | None = None,
        operation_timeout: float = 600.0,
        rpc_timeout: float = 30.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        operation_resolver: Callable[[str], Any] | None = None,
        rules_publisher: Any | None = None,
        iam_owner: str | None = None,
    ) -> None:
        self.config = config
        self.checkpoints = checkpoints
        self.approval = approval
        self.iam_client = iam_client
        self.operation_timeout = operation_timeout
        self.rpc_timeout = rpc_timeout
        self.max_attempts = max_attempts
        self._sleep = sleep
        self.projects = ProjectManager(
            projects_client,
            rpc_timeout=rpc_timeout,
            operation_timeout=operation_timeout,
            sleep=sleep,
            operation_resolver=operation_resolver,
        )
        self.billing = billing_client
        self.services = service_usage_client
        self.rules_publisher = rules_publisher
        self.iam_owner = iam_owner or config.iam_owner
        self._operation_resolver = operation_resolver
        self._project_number: str | None = config.project_number

    def _rules_binding(self) -> dict[str, Any]:
        publisher = self.rules_publisher
        if publisher is None:
            return {}
        if hasattr(publisher, "approval_binding"):
            try:
                binding = publisher.approval_binding(
                    control_database_id=self.config.control_database_id,
                    runtime_database_id=self.config.runtime_database_id,
                )
            except TypeError:
                binding = publisher.approval_binding()
        else:
            binding = {
                "project_id": getattr(publisher, "project_id", None),
                "project_number": getattr(publisher, "project_number", None),
                "source_hash": getattr(publisher, "source_hash", None),
                "release_names": [
                    (
                        f"projects/{getattr(publisher, 'project_id', '')}/releases/"
                        f"cloud.firestore/{database_id}"
                    )
                    for database_id in (
                        self.config.control_database_id,
                        self.config.runtime_database_id,
                    )
                ],
            }
        binding = dict(binding)
        if (
            self.config.rules_source_hash is not None
            and binding.get("source_hash") is not None
            and self.config.rules_source_hash != binding["source_hash"]
        ):
            raise SetupError("Rules source is different from the approved configuration")
        binding["release_names"] = [
            f"projects/{binding.get('project_id', '')}/releases/cloud.firestore/{database_id}"
            for database_id in (self.config.control_database_id, self.config.runtime_database_id)
        ]
        binding["database_ids"] = [self.config.control_database_id, self.config.runtime_database_id]
        binding["attachment_points"] = [
            (
                f"firestore.googleapis.com/projects/{binding.get('project_number', '')}/"
                f"databases/{database_id}"
            )
            for database_id in (self.config.control_database_id, self.config.runtime_database_id)
        ]
        return binding

    def _checkpoint(self, name: str) -> dict[str, Any]:
        return self.checkpoints.get(name) or {}

    def _terraform_inputs(self, selected: dict[str, Any]) -> dict[str, Any]:
        """Return the complete nonsecret Terraform handoff contract."""
        return {
            "project_id": self.config.project_id,
            "receiver_cloud_run_region": self.config.receiver_cloud_run_region,
            "control_database_id": self.config._template_value(
                "control_database_id", self.config.control_database_id
            ),
            "runtime_database_id": self.config._template_value(
                "runtime_database_id", self.config.runtime_database_id
            ),
            "control_database_location": self.config.control_database_location,
            "runtime_database_location": self.config.runtime_database_location,
            "eventarc_trigger_location": self.config.eventarc_trigger_location,
            "eventarc_trigger_name": self.config._template_value(
                "eventarc_trigger_name", self.config.eventarc_trigger_name
            ),
            "request_document_path_pattern": self.config._template_value(
                "request_document_path_pattern", self.config.request_document_path_pattern
            ),
            "eventarc_trigger_service_account_email": (
                self.config.eventarc_trigger_service_account_email
            ),
            "eventarc_receiver_service_account_id": (
                self.config._template_value(
                    "eventarc_receiver_service_account_id",
                    self.config.eventarc_receiver_service_account_id,
                )
            ),
            "worker_runtime_service_account_id": self.config._template_value(
                "worker_runtime_service_account_id", self.config.worker_runtime_service_account_id
            ),
            "receiver_cloud_run_service_name": self.config._template_value(
                "receiver_cloud_run_service_name", self.config.receiver_cloud_run_service_name
            ),
            "worker_cloud_run_job_name": self.config._template_value(
                "worker_cloud_run_job_name", self.config.worker_cloud_run_job_name
            ),
            "receiver_container_image": self.config.receiver_container_image,
            "worker_container_image": self.config.worker_container_image,
            "authorized_ui_domains": list(
                self.config._template_value(
                    "authorized_ui_domains", self.config.authorized_ui_domains
                )
            ),
            "identity_platform_google_web_client_id": (
                self.config.identity_platform_google_web_client_id
            ),
            "firebase_web_app_display_name": self.config._template_value(
                "firebase_web_app_display_name", self.config.firebase_web_app_display_name
            ),
            "workspace_secret_id": self.config._template_value(
                "workspace_secret_id", self.config.workspace_secret_id
            ),
        }

    def _prepare_terraform_handoff(self, selected: dict[str, Any]) -> dict[str, Any]:
        inputs = self._terraform_inputs(selected)
        provisioning_context = {
            "project_number": selected.get("project_number"),
            "parent": self.config.parent,
            "billing_account": self.config.billing_account,
            "region": self.config.region,
            "services": list(self.config.services),
        }
        fingerprint = self.config.fingerprint(
            rules_binding={
                "terraform_inputs": inputs,
                "provisioning_context": provisioning_context,
                **self._rules_binding(),
            }
        )
        saved = self._checkpoint("terraform_handoff")
        if saved.get("status") == "complete":
            if (
                saved.get("inputs") != inputs
                or saved.get("provisioning_context") != provisioning_context
                or saved.get("config_fingerprint") != fingerprint
                or any(inputs.get(key) is None for key in self._required_terraform_inputs())
            ):
                raise SetupError("Terraform handoff does not match the approved setup")
            return saved
        missing = [key for key in self._required_terraform_inputs() if inputs.get(key) is None]
        pending = {
            "status": "pending_configuration" if missing else "pending",
            "inputs": inputs,
            "provisioning_context": provisioning_context,
            "missing_inputs": missing,
            "config_fingerprint": fingerprint,
            "rules": self._rules_binding(),
        }
        self.checkpoints.put("terraform_handoff", pending)
        return pending

    @staticmethod
    def _required_terraform_inputs() -> tuple[str, ...]:
        return (
            "project_id",
            "receiver_cloud_run_region",
            "control_database_location",
            "runtime_database_location",
            "eventarc_trigger_location",
            "identity_platform_google_web_client_id",
            "eventarc_trigger_service_account_email",
            "receiver_container_image",
            "worker_container_image",
        )

    def _lookup_project(self) -> Any:
        return self._call(lambda: self.projects.lookup(self.config.project_id)).project

    def _project_record(self, project: Any, *, created: bool) -> dict[str, Any]:
        project_id = str(getattr(project, "project_id", ""))
        parent = str(getattr(project, "parent", ""))
        state = getattr(project, "state", None)
        state_name = getattr(state, "name", state)
        if project_id != self.config.project_id:
            raise SetupError("Resource Manager returned a different project ID")
        if not parent or parent != self.config.parent:
            raise SetupError("project parent does not match the approved proposal")
        # Resource Manager's protobuf uses STATE_UNSPECIFIED=0.  It is not an
        # ACTIVE attestation, including for a create operation result.
        if state_name in (None, "", "STATE_UNSPECIFIED", 0):
            raise SetupError("selected project does not have verified ACTIVE state")
        if state_name not in (None, "", 1, "ACTIVE"):
            raise SetupError("selected project is not ACTIVE")
        name = str(getattr(project, "name", ""))
        if not name.startswith("projects/"):
            raise SetupError("Resource Manager did not return a verified project name")
        number = name.rsplit("/", 1)[-1] if name.startswith("projects/") else ""
        if not re.fullmatch(r"[0-9]+", number):
            raise SetupError("Resource Manager did not return a verified project number")
        return {
            "status": "complete",
            "project_id": project_id,
            "project_name": name or f"projects/{project_id}",
            "project_number": number,
            "parent": parent,
            "state": "ACTIVE" if state_name in (None, "", 1) else str(state_name),
            "created": created,
        }

    def _call(self, operation: Callable[[], Any]) -> Any:
        last: BaseException | None = None
        for attempt in range(self.max_attempts):
            try:
                return operation()
            except Exception as error:
                last = error
                if getattr(error, "code", None) in (429, "RESOURCE_EXHAUSTED"):
                    raise QuotaFailure("Google Cloud quota prevented setup") from None
                if not _is_transient(error) or attempt + 1 >= self.max_attempts:
                    raise
                self._sleep(min(2**attempt, 8))
        assert last is not None
        raise last

    def _approve(self) -> None:
        state = self.checkpoints.get("approval")
        rules_binding = self._rules_binding()
        fingerprint = self.config.fingerprint(rules_binding=rules_binding)
        if state is not None:
            if state.get("fingerprint") != fingerprint:
                raise SetupError("checkpoint belongs to a different setup proposal")
            return
        proposal = self.config.proposal(rules_binding=rules_binding)
        if self.approval(proposal) is not True:
            raise SetupRejected("setup proposal was not approved")
        self.checkpoints.put("approval", {"status": "approved", "fingerprint": fingerprint})

    def _ensure_project(self) -> Any:  # noqa: PLR0915
        complete = self.checkpoints.get("select_project")
        # Re-read on every process start.  A cached checkpoint is evidence of
        # prior progress, not proof that the project still has the approved
        # parent, ACTIVE state, or the same numeric identity.
        if complete is not None and complete.get("status") == "complete":
            try:
                project = self._lookup_project()
            except ProjectNotFound:
                raise SetupError("approved project is not currently visible") from None
            selected = self._project_record(project, created=bool(complete.get("created")))
            if (
                complete.get("project_number")
                and selected["project_number"] != complete["project_number"]
            ):
                raise SetupError("project number changed after approval")
            self.checkpoints.put("select_project", selected)
            self._project_number = selected["project_number"]
            return selected
        try:
            project = self._lookup_project()
            selected = self._project_record(project, created=False)
            self.checkpoints.put("select_project", selected)
            self._project_number = selected["project_number"]
            return selected
        except ProjectNotFound:
            create = self.checkpoints.get("create_project")
            if create is not None and create.get("status") == "complete":
                raise SetupError("approved project is not currently visible") from None
            operation = None
            if create is None:
                # Record the intended mutation before calling Resource Manager.
                # This makes a crash distinguish an unstarted intent from an
                # accepted operation and prevents blind duplicate creation.
                create = {
                    "status": "pending",
                    "project_id": self.config.project_id,
                    "parent": self.config.parent,
                }
                self.checkpoints.put("create_project", create)
                create = {**create, "status": "submitting"}
                self.checkpoints.put("create_project", create)
                try:
                    operation = self.projects.start_create(
                        project_id=self.config.project_id,
                        parent=self.config.parent,
                        display_name=self.config.display_name,
                    )
                except Exception:
                    # The API may have accepted a non-idempotent create just
                    # before the transport failed.  Reconcile the resource;
                    # never issue a blind second create.
                    try:
                        project = self._lookup_project()
                    except ProjectNotFound:
                        raise SetupError(
                            "project create outcome is unknown; reconcile before retry"
                        ) from None
                    record = self._project_record(project, created=True)
                    create = {**create, "status": "complete", **record}
                    self.checkpoints.put("create_project", create)
                    operation = None
                # Persist the public operation name before polling so a crash
                # after API acceptance can resume or reconcile safely.
                if operation is not None:
                    operation_proto = getattr(operation, "operation", None)
                    operation_name = str(
                        getattr(operation_proto, "name", "") or getattr(operation, "name", "")
                    )
                    if not operation_name:
                        try:
                            project = self._lookup_project()
                        except ProjectNotFound:
                            raise SetupError(
                                "project create outcome is unknown; reconcile before retry"
                            ) from None
                        record = self._project_record(project, created=True)
                        create = {**create, "status": "complete", **record}
                        self.checkpoints.put("create_project", create)
                        operation = None
                    else:
                        create = {
                            **create,
                            "status": "in_flight",
                            "operation_name": operation_name,
                            "project_id": self.config.project_id,
                            "parent": self.config.parent,
                        }
                        self.checkpoints.put("create_project", create)
            if create.get("status") != "complete":
                # The original operation object is available in this process.
                # A durable restart must inject an official operation resolver;
                # without one, reconcile the final project rather than creating again.
                project: Any | None = None
                if operation is None:
                    try:
                        project = self._lookup_project()
                    except ProjectNotFound:
                        if create.get("status") in {"pending", "submitting"}:
                            raise SetupError(
                                "project create submission was interrupted; reconcile before retry"
                            ) from None
                        try:
                            operation = self.projects.resume(str(create.get("operation_name", "")))
                        except Exception:
                            # A completed LRO can expire from the operations
                            # service.  One final resource reconciliation is
                            # safe; otherwise leave the setup held.
                            try:
                                project = self._lookup_project()
                            except ProjectNotFound:
                                raise SetupError(
                                    "saved project operation is unavailable; reconcile before retry"
                                ) from None
                            else:
                                record = self._project_record(project, created=True)
                                create = {**create, "status": "complete", **record}
                                self.checkpoints.put("create_project", create)
                                operation = None
                        if operation is not None:
                            try:
                                project = self.projects.wait(operation)
                            except ProjectOperationTimeout as error:
                                raise SetupTimeout(str(error)) from None
                else:
                    try:
                        project = self.projects.wait(operation)
                    except ProjectOperationTimeout as error:
                        raise SetupTimeout(str(error)) from None
                if project is not None:
                    record = self._project_record(project, created=True)
                    create = {**create, "status": "complete", **record}
                    self.checkpoints.put("create_project", create)
            selected = {
                key: create[key]
                for key in (
                    "status",
                    "project_id",
                    "project_name",
                    "project_number",
                    "parent",
                    "state",
                    "created",
                )
                if key in create
            }
            selected.setdefault("status", "complete")
            self.checkpoints.put("select_project", selected)
            self._project_number = selected.get("project_number") or self._project_number
            return selected

    def _enable_billing(self) -> None:
        saved = self._checkpoint("billing")
        if saved.get("status") == "complete":
            return
        info = None
        getter = getattr(self.billing, "get_project_billing_info", None)
        if getter is not None:
            info = self._call(
                lambda: getter(name=f"projects/{self.config.project_id}", timeout=self.rpc_timeout)
            )
        current_account = getattr(info, "billing_account_name", None)
        if current_account == self.config.billing_account and getattr(
            info, "billing_enabled", True
        ):
            self.checkpoints.put(
                "billing",
                {**saved, "status": "complete", "billing_account": self.config.billing_account},
            )
            return
        self.checkpoints.put(
            "billing",
            {
                **saved,
                "status": "pending",
                "project_id": self.config.project_id,
                "billing_account": self.config.billing_account,
            },
        )
        if current_account != self.config.billing_account or not getattr(
            info, "billing_enabled", False
        ):
            from google.cloud import billing_v1

            request = billing_v1.ProjectBillingInfo(
                name=f"projects/{self.config.project_id}",
                billing_account_name=self.config.billing_account,
                billing_enabled=True,
            )
            self._call(
                lambda: self.billing.update_project_billing_info(
                    name=f"projects/{self.config.project_id}",
                    project_billing_info=request,
                    timeout=self.rpc_timeout,
                )
            )
            if getter is not None:
                verified = self._call(
                    lambda: getter(
                        name=f"projects/{self.config.project_id}",
                        timeout=self.rpc_timeout,
                    )
                )
                verified_account = getattr(verified, "billing_account_name", None)
                verified_enabled = getattr(verified, "billing_enabled", False)
                if verified_account != self.config.billing_account or not verified_enabled:
                    raise SetupError("billing account could not be verified after update")
        self.checkpoints.put(
            "billing",
            {
                "status": "complete",
                "project_id": self.config.project_id,
                "billing_account": self.config.billing_account,
            },
        )

    def _enable_services(self) -> None:
        saved = self._checkpoint("services")
        if saved.get("status") == "complete":
            return
        from google.cloud import service_usage_v1

        parent = self._project_number or self.config.project_number
        if not parent or not str(parent).isdigit():
            raise SetupError("service enablement requires a verified numeric project number")
        request = service_usage_v1.BatchEnableServicesRequest(
            parent=f"projects/{parent}", service_ids=list(self.config.services)
        )
        if not self.config.services:
            self.checkpoints.put(
                "services",
                {
                    "status": "complete",
                    "project_id": self.config.project_id,
                    "services": [],
                },
            )
            return
        # A durable intent makes a crash after Service Usage accepts the batch
        # distinguishable from an unstarted request.
        self.checkpoints.put(
            "services",
            {
                **saved,
                "status": "pending",
                "project_id": self.config.project_id,
                "services": list(self.config.services),
                "parent": f"projects/{parent}",
            },
        )
        operation = None
        operation_name = str(saved.get("operation_name", ""))
        if operation_name:
            try:
                operation = self._resume_service_operation(operation_name)
            except Exception:
                operation = None
            if operation is None and self._services_enabled():
                self.checkpoints.put(
                    "services",
                    {
                        **saved,
                        "status": "complete",
                        "project_id": self.config.project_id,
                    },
                )
                return
            if operation is None:
                raise SetupError(
                    "saved service enablement outcome is unavailable; reconcile before retry"
                )
        elif saved:
            # A pending/submitting intent without a saved LRO means the prior
            # request may have committed but its acknowledgement was lost.
            # Reconcile the actual service state; never submit a second batch.
            if self._services_enabled():
                self.checkpoints.put(
                    "services",
                    {
                        **saved,
                        "status": "complete",
                        "project_id": self.config.project_id,
                    },
                )
                return
            raise SetupError("service enablement outcome is unknown; reconcile before retry")
        if operation is None:
            # Service Usage batch enablement is a non-idempotent submission
            # from this process's perspective.  Retry only by reconciliation;
            # do not replay the RPC after a transport-level failure.
            try:
                operation = self.services.batch_enable_services(
                    request=request, timeout=self.rpc_timeout
                )
            except Exception as error:
                code = getattr(error, "code", None)
                code = code() if callable(code) else code
                code = getattr(code, "value", code)
                if code in (429, "RESOURCE_EXHAUSTED"):
                    raise QuotaFailure("Google Cloud quota prevented setup") from None
                raise SetupError("service enablement request failed") from None
            operation_proto = getattr(operation, "operation", None)
            operation_name = str(getattr(operation_proto, "name", ""))
            if not operation_name or not hasattr(operation, "result"):
                raise SetupError("service enablement outcome is unknown; reconcile before retry")
            self.checkpoints.put(
                "services",
                {
                    **saved,
                    "status": "in_flight",
                    "project_id": self.config.project_id,
                    "services": list(self.config.services),
                    "operation_name": operation_name,
                },
            )
        try:
            self.projects.wait(operation)
        except ProjectOperationTimeout as error:
            raise SetupTimeout(str(error)) from None
        self.checkpoints.put(
            "services",
            {
                "status": "complete",
                "project_id": self.config.project_id,
                "services": list(self.config.services),
                "operation_name": operation_name,
            },
        )

    def _services_enabled(self) -> bool:
        listing = getattr(self.services, "list_services", None)
        if listing is None:
            return False
        try:
            parent = self._project_number or self.config.project_number
            if not parent or not str(parent).isdigit():
                return False
            response = listing(
                parent=f"projects/{parent}",
                filter="state:ENABLED",
                page_size=200,
                timeout=self.rpc_timeout,
            )
            names = {
                str(getattr(getattr(item, "config", None), "name", "") or getattr(item, "name", ""))
                for item in response
            }
            return all(service in names for service in self.config.services)
        except Exception:
            return False

    def _resume_service_operation(self, operation_name: str) -> Any | None:
        if self._operation_resolver is not None:
            return self._operation_resolver(operation_name)
        operations_client = getattr(
            getattr(self.services, "transport", None), "operations_client", None
        )
        if operations_client is None:
            return None
        from google.api_core.operation import from_gapic
        from google.cloud.service_usage_v1 import types as serviceusage

        operation_proto = operations_client.get_operation(
            name=operation_name, timeout=self.rpc_timeout
        )
        return from_gapic(
            operation_proto,
            operations_client,
            result_type=serviceusage.BatchEnableServicesResponse,
            metadata_type=serviceusage.OperationMetadata,
        )

    def _ensure_iam(self) -> None:
        if self._checkpoint("iam").get("status") == "complete":
            return
        if self.config.iam_grants or self.config.iam_bindings:
            if self.iam_client is None or (
                self.config.iam_bindings and self.iam_owner not in (None, "sdk")
            ):
                raise SetupError("requested IAM grants have no approved SDK owner")
            if not self.config.iam_bindings:
                raise SetupError("requested IAM grants were not supplied as SDK bindings")
            from google.iam.v1 import iam_policy_pb2, options_pb2

            iam = self.iam_client
            for attempt in range(self.max_attempts):
                request = iam_policy_pb2.GetIamPolicyRequest(
                    resource=f"projects/{self.config.project_id}",
                    options=options_pb2.GetPolicyOptions(requested_policy_version=3),
                )
                policy = self._call(
                    lambda request=request: iam.get_iam_policy(
                        request=request, timeout=self.rpc_timeout
                    )
                )
                # Merge only requested unconditional members.  Conditional
                # bindings, audit configs, version, and etag stay intact.
                for role, members in self.config.iam_bindings.items():
                    binding = next(
                        (
                            candidate
                            for candidate in getattr(policy, "bindings", [])
                            if candidate.role == role
                            and not (
                                getattr(candidate.condition, "title", "")
                                or getattr(candidate.condition, "description", "")
                                or getattr(candidate.condition, "expression", "")
                            )
                        ),
                        None,
                    )
                    if binding is None:
                        binding = policy.bindings.add(role=role)
                    binding.members[:] = sorted(set(binding.members).union(members))
                set_request = iam_policy_pb2.SetIamPolicyRequest(
                    resource=f"projects/{self.config.project_id}", policy=policy
                )
                try:
                    iam.set_iam_policy(request=set_request, timeout=self.rpc_timeout)
                except Exception as error:
                    raw_code = getattr(error, "code", None)
                    raw_code = raw_code() if callable(raw_code) else raw_code
                    code_value = getattr(raw_code, "value", raw_code)
                    code_name = getattr(raw_code, "name", raw_code)
                    if code_value in (429, "RESOURCE_EXHAUSTED") or code_name == (
                        "RESOURCE_EXHAUSTED"
                    ):
                        raise QuotaFailure("Google Cloud quota prevented setup") from None
                    retryable = code_value in (408, 409, 500, 502, 503, 504) or code_name in (
                        "ABORTED",
                        "ABORTED_ERROR",
                        "CONFLICT",
                        "DEADLINE_EXCEEDED",
                        "GATEWAY_TIMEOUT",
                        "SERVICE_UNAVAILABLE",
                    )
                    if not retryable or attempt + 1 >= self.max_attempts:
                        raise SetupError("IAM policy update failed") from None
                    self._sleep(min(2**attempt, 8))
                    continue
                break
            else:
                raise SetupError("IAM policy update could not be committed") from None
        self.checkpoints.put("iam", {"status": "complete", "grants": list(self.config.iam_grants)})

    def run(self) -> dict[str, Any]:
        self._approve()
        selected = self._ensure_project()
        self._enable_billing()
        self._enable_services()
        self._ensure_iam()
        # Terraform is an explicit operator boundary.  Rules publication must
        # wait until the approved, nonsecret inputs have been applied.
        handoff = self._prepare_terraform_handoff(selected)
        rules_checkpoint = self._checkpoint("rules")
        if (
            handoff.get("status") == "complete"
            and self.rules_publisher is not None
            and rules_checkpoint.get("status") != "complete"
        ):
            publisher_binding = self._rules_binding()
            if publisher_binding.get("project_id") != self.config.project_id:
                raise SetupError("Rules publisher project does not match approved project")
            if publisher_binding.get("project_number") != selected.get("project_number"):
                raise SetupError("Rules publisher project number does not match selected project")
            published = self.rules_publisher.publish_both(
                self.config.control_database_id, self.config.runtime_database_id
            )
            self.checkpoints.put(
                "rules",
                {
                    "status": "complete",
                    "project_id": self.config.project_id,
                    "project_number": selected.get("project_number"),
                    "databases": [self.config.control_database_id, self.config.runtime_database_id],
                    "releases": [published[0]["release_name"], published[1]["release_name"]],
                    "source_hash": publisher_binding.get("source_hash"),
                    "release_bindings": published,
                },
            )
            rules_checkpoint = self._checkpoint("rules")
        elif rules_checkpoint.get("status") == "complete":
            if rules_checkpoint.get("project_id") != self.config.project_id:
                raise SetupError("Rules checkpoint belongs to a different project")
            if rules_checkpoint.get("project_number") != selected.get("project_number"):
                raise SetupError("Rules checkpoint belongs to a different project number")
            binding = self._rules_binding()
            if rules_checkpoint.get("source_hash") != binding.get("source_hash"):
                raise SetupError("Rules checkpoint source is not the approved source")
            expected_releases = set(binding.get("release_names", ()))
            if set(rules_checkpoint.get("releases", ())) != expected_releases:
                raise SetupError("Rules checkpoint destinations are not approved")
        # Phase 3 deliberately cannot attest to a deployed receiver/job,
        # Eventarc delivery, IAM propagation, or Rules behavior. Phase 8 owns
        # that authenticated verification; no checkpoint shape or Boolean
        # callback can make this phase globally ready.
        deployment_verified = False
        result = {
            "status": (
                "ready"
                if rules_checkpoint.get("status") == "complete" and deployment_verified
                else (
                    "awaiting_terraform_handoff"
                    if handoff.get("status") != "complete"
                    else (
                        "awaiting_rules_publication"
                        if (rules_checkpoint.get("status") != "complete")
                        else "awaiting_runtime_verification"
                    )
                )
            ),
            "project_id": self.config.project_id,
            "project_name": selected.get("project_name"),
            "rules_required": rules_checkpoint.get("status") != "complete",
            "rules_owner": "official-google-api-python-client",
            "terraform_handoff_required": handoff.get("status") != "complete",
            "runtime_verification_required": not deployment_verified,
            "deployment_verified": deployment_verified,
        }
        self.checkpoints.put("bootstrap", result)
        return result
