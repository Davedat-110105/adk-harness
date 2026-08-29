"""Project lookup and Resource Manager orchestration.

Only official Google client libraries are used for cloud calls.  The clients
are injected so all behavior can be tested offline at the SDK boundary.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


class ProjectError(RuntimeError):
    """Base class for project API failures."""


class ProjectNotFound(ProjectError):
    """The project does not exist or is not yet visible."""


class AccessDenied(ProjectError):
    """The caller cannot inspect or mutate the project."""


class TransientProjectError(ProjectError):
    """A bounded retry may succeed for this project operation."""


class ProjectOperationTimeout(ProjectError):
    """A long-running project operation exceeded its local deadline."""


@dataclass(frozen=True, slots=True)
class ProjectLookup:
    """A normalized project lookup result."""

    project: Any

    @classmethod
    def found(cls, project: Any) -> ProjectLookup:
        return cls(project)


@dataclass(frozen=True, slots=True)
class BootstrapProposal:
    """Human-readable, immutable setup scope presented for approval."""

    project_id: str
    parent: str
    billing_account: str
    region: str
    services: tuple[str, ...] = ()
    iam_grants: tuple[str, ...] = ()
    display_name: str | None = None
    project_number: str | None = None
    iam_bindings: Any = None
    control_database_id: str = "control"
    runtime_database_id: str = "runtime"
    authorized_ui_domains: tuple[str, ...] = ()
    identity_platform_google_web_client_id: str | None = None
    eventarc_trigger_location: str | None = None
    receiver_cloud_run_region: str | None = None
    rules_source_hash: str | None = None
    rules_source_version: str | None = None
    rules_project_id: str | None = None
    rules_project_number: str | None = None
    rules_release_names: tuple[str, ...] = ()
    rules_attachment_points: tuple[str, ...] = ()
    iam_owner: str | None = None
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

    def __post_init__(self) -> None:
        bindings = {
            str(role): tuple(sorted(str(member) for member in members))
            for role, members in (self.iam_bindings or {}).items()
        }
        object.__setattr__(self, "iam_bindings", MappingProxyType(bindings))
        for name in (
            "services",
            "iam_grants",
            "authorized_ui_domains",
            "rules_release_names",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "parent": self.parent,
            "billing_account": self.billing_account,
            "region": self.region,
            "display_name": self.display_name,
            "project_number": self.project_number,
            "services": list(self.services),
            "iam_grants": list(self.iam_grants),
            "iam_bindings": {role: list(members) for role, members in self.iam_bindings.items()},
            "control_database_id": self.control_database_id,
            "runtime_database_id": self.runtime_database_id,
            "authorized_ui_domains": list(self.authorized_ui_domains),
            "identity_platform_google_web_client_id": self.identity_platform_google_web_client_id,
            "eventarc_trigger_location": self.eventarc_trigger_location,
            "receiver_cloud_run_region": self.receiver_cloud_run_region,
            "rules_source_hash": self.rules_source_hash,
            "rules_source_version": self.rules_source_version,
            "rules_project_id": self.rules_project_id,
            "rules_project_number": self.rules_project_number,
            "rules_release_names": list(self.rules_release_names),
            "rules_attachment_points": list(self.rules_attachment_points),
            "iam_owner": self.iam_owner,
            "control_database_location": self.control_database_location,
            "runtime_database_location": self.runtime_database_location,
            "eventarc_trigger_name": self.eventarc_trigger_name,
            "request_document_path_pattern": self.request_document_path_pattern,
            "eventarc_trigger_service_account_email": self.eventarc_trigger_service_account_email,
            "eventarc_receiver_service_account_id": self.eventarc_receiver_service_account_id,
            "worker_runtime_service_account_id": self.worker_runtime_service_account_id,
            "receiver_cloud_run_service_name": self.receiver_cloud_run_service_name,
            "worker_cloud_run_job_name": self.worker_cloud_run_job_name,
            "receiver_container_image": self.receiver_container_image,
            "worker_container_image": self.worker_container_image,
            "firebase_web_app_display_name": self.firebase_web_app_display_name,
            "workspace_secret_id": self.workspace_secret_id,
        }


def _code(error: BaseException) -> int | str | None:
    value = getattr(error, "code", None)
    if callable(value):
        value = value()
    value = getattr(value, "value", value)
    return value if isinstance(value, (int, str)) else None


def _classify(error: BaseException) -> ProjectError:
    code = _code(error)
    if code in (401, 403, "PERMISSION_DENIED", "UNAUTHENTICATED", "UNAUTHENTICATED"):
        return AccessDenied("project access was denied")
    if code in (404, "NOT_FOUND"):
        return ProjectNotFound("project was not found")
    if code in (
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
    ):
        return TransientProjectError("project API returned a transient failure")
    return ProjectError("project API request failed")


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError("project ID must be a valid Google Cloud project ID")
    return project_id


class ProjectManager:
    """Use Resource Manager's official client with bounded calls."""

    def __init__(
        self,
        client: Any,
        *,
        rpc_timeout: float = 30.0,
        operation_timeout: float = 600.0,
        sleep: Any = time.sleep,
        monotonic: Any = time.monotonic,
        operation_resolver: Any | None = None,
    ) -> None:
        self.client = client
        self.rpc_timeout = rpc_timeout
        self.operation_timeout = operation_timeout
        self._sleep = sleep
        self._monotonic = monotonic
        self._operation_resolver = operation_resolver

    def lookup(self, project_id: str) -> ProjectLookup:
        project_id = validate_project_id(project_id)
        try:
            project = self.client.get_project(
                name=f"projects/{project_id}",
                timeout=self.rpc_timeout,
            )
        except Exception as error:
            classified = _classify(error)
            raise classified from None
        return ProjectLookup.found(project)

    def create(self, *, project_id: str, parent: str, display_name: str | None = None) -> Any:
        operation = self.start_create(
            project_id=project_id, parent=parent, display_name=display_name
        )
        return self.wait(operation)

    def start_create(self, *, project_id: str, parent: str, display_name: str | None = None) -> Any:
        project_id = validate_project_id(project_id)
        if not parent or not re.fullmatch(r"(?:folders|organizations)/[0-9]+", parent):
            raise ValueError("parent must be folders/<number> or organizations/<number>")
        from google.cloud import resourcemanager_v3

        project = resourcemanager_v3.Project(
            project_id=project_id,
            parent=parent,
            display_name=display_name or project_id,
        )
        try:
            return self.client.create_project(project=project, timeout=self.rpc_timeout)
        except ProjectError:
            raise
        except Exception as error:
            raise _classify(error) from None

    def wait(self, operation: Any) -> Any:
        """Wait for an official google.api_core Operation without unbounded polling."""
        deadline = self._monotonic() + self.operation_timeout
        try:
            remaining = max(0.01, deadline - self._monotonic())
            # google.api_core.operation.Operation.result performs documented
            # polling and propagates the operation's typed result/error.
            return operation.result(timeout=remaining)
        except TimeoutError:
            raise ProjectOperationTimeout("project operation exceeded its deadline") from None
        except Exception as error:
            if _code(error) in (504, "DEADLINE_EXCEEDED"):
                raise ProjectOperationTimeout("project operation exceeded its deadline") from None
            classified = _classify(error)
            raise classified from None

    def resume(self, operation_name: str) -> Any:
        """Reconstruct a saved Resource Manager LRO through the public SDK."""
        if self._operation_resolver is not None:
            return self._operation_resolver(operation_name)
        from google.api_core.operation import from_gapic
        from google.cloud.resourcemanager_v3 import CreateProjectMetadata, Project

        operation = self.client.transport.operations_client.get_operation(
            name=operation_name, timeout=self.rpc_timeout
        )
        return from_gapic(
            operation,
            self.client.transport.operations_client,
            result_type=Project,
            metadata_type=CreateProjectMetadata,
        )
