"""Read-only runtime readiness checks using official Google SDKs.

The verifier deliberately reports ``awaiting_live_proof`` until every approved
resource read succeeds.  Checkpoint presence, Terraform plans, and user
attestations are never treated as readiness evidence.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ReadinessStatus(StrEnum):
    VERIFIED = "verified"
    NOT_RUN = "not_run"
    MISMATCH = "mismatch"
    ERROR = "error"
    AWAITING_LIVE_PROOF = "awaiting_live_proof"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    status: ReadinessStatus
    detail: str = ""
    approved: Any = None
    observed: Any = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    checks: Mapping[str, ReadinessCheck]
    live_only: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return (
            all(item.status is ReadinessStatus.VERIFIED for item in self.checks.values())
            and not self.live_only
        )

    @property
    def status(self) -> ReadinessStatus:
        for status in (ReadinessStatus.ERROR, ReadinessStatus.MISMATCH):
            if any(item.status is status for item in self.checks.values()):
                return status
        return ReadinessStatus.VERIFIED if self.ready else ReadinessStatus.AWAITING_LIVE_PROOF

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ready": self.ready,
            "checks": {
                name: {"status": check.status.value, "detail": check.detail}
                for name, check in self.checks.items()
            },
            "live_only": list(self.live_only),
        }


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _name(value: Any) -> str:
    return str(value or "")


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    return str(name or value or "").upper()


def _has_successful_terminal_condition(resource: Any) -> bool:
    """Require a Cloud Run Ready condition in the successful terminal state."""
    for condition in _value(resource, "conditions", ()) or ():
        condition_type = _enum_name(_value(condition, "type"))
        state = _enum_name(_value(condition, "state"))
        if condition_type in {"", "READY", "CONDITION_TYPE_READY"} and state in {
            "CONDITION_SUCCEEDED",
            "SUCCEEDED",
            "TRUE",
        }:
            return True
    return False


def _check(expected: Any, observed: Any, field: str) -> ReadinessCheck:
    if expected == observed:
        return ReadinessCheck(ReadinessStatus.VERIFIED, f"{field} verified", expected, observed)
    return ReadinessCheck(
        ReadinessStatus.MISMATCH,
        f"{field}: approved={expected!r}, observed={observed!r}",
        expected,
        observed,
    )


class RuntimeReadinessVerifier:
    """Compare approved Terraform/bootstrap values to live SDK resources.

    Clients are injectable solely for offline boundary tests.  Omitting them
    makes the result explicitly ``not_run`` and performs no cloud RPC.
    """

    def __init__(
        self,
        handoff: Mapping[str, Any],
        select_project: Mapping[str, Any],
        *,
        clients: Mapping[str, Any] | None = None,
        rules_source: str | bytes | Path | None = None,
    ) -> None:
        self.handoff = dict(handoff)
        self.select_project = dict(select_project)
        self.clients = dict(clients or {})
        self.rules_source = rules_source

    def _not_run(self, detail: str = "official SDK client was not supplied") -> ReadinessCheck:
        return ReadinessCheck(ReadinessStatus.NOT_RUN, detail)

    def _project(self) -> ReadinessCheck:
        client = self.clients.get("resource_manager")
        if client is None:
            return self._not_run()
        project_id = str(self.handoff.get("project_id", ""))
        try:
            resource = client.get_project(name=f"projects/{project_id}", timeout=30.0)
        except Exception as exc:  # SDK errors are surfaced as bounded evidence.
            return ReadinessCheck(
                ReadinessStatus.ERROR, f"project read failed: {type(exc).__name__}"
            )
        expected_number = str(self.select_project.get("project_number", ""))
        observed_name = _name(_value(resource, "name"))
        observed_number = (
            observed_name.rsplit("/", 1)[-1] if observed_name.startswith("projects/") else ""
        )
        for field, expected, observed in (
            ("project_id", project_id, _value(resource, "project_id")),
            ("parent", self.select_project.get("parent"), _value(resource, "parent")),
            (
                "state",
                "ACTIVE",
                _value(_value(resource, "state"), "name", _value(resource, "state")),
            ),
        ):
            if expected is not None and str(observed) != str(expected):
                return _check(expected, observed, field)
        if not re.fullmatch(r"[0-9]+", observed_number) or observed_number != expected_number:
            return _check(expected_number, observed_number, "project_number")
        return ReadinessCheck(ReadinessStatus.VERIFIED, "project identity verified")

    def _run(self) -> ReadinessCheck:
        services, jobs = self.clients.get("run_services"), self.clients.get("run_jobs")
        if services is None or jobs is None:
            return self._not_run("official Cloud Run service and job clients were not supplied")
        project = self.handoff.get("project_id", "")
        region = self.handoff.get("receiver_cloud_run_region", "")
        service_name = f"projects/{project}/locations/{region}/services/{self.handoff.get('receiver_cloud_run_service_name', '')}"
        job_name = f"projects/{project}/locations/{region}/jobs/{self.handoff.get('worker_cloud_run_job_name', '')}"
        try:
            service = services.get_service(name=service_name, timeout=30.0)
            job = jobs.get_job(name=job_name, timeout=30.0)
        except Exception as exc:
            return ReadinessCheck(
                ReadinessStatus.ERROR, f"Cloud Run read failed: {type(exc).__name__}"
            )
        if _name(_value(service, "name")) != service_name:
            return _check(service_name, _value(service, "name"), "receiver.name")
        if _value(service, "reconciling", False):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "receiver is still reconciling")
        if not _value(service, "latest_ready_revision"):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "receiver has no latest ready revision")
        if not _has_successful_terminal_condition(service):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "receiver has no successful terminal condition")
        template = _value(service, "template")
        containers = _value(template, "containers", ())
        if _value(template, "service_account") != self.handoff.get(
            "receiver_runtime_service_account_email"
        ):
            return _check(
                self.handoff.get("receiver_runtime_service_account_email"),
                _value(template, "service_account"),
                "receiver.service_account",
            )
        if len(containers) != 1 or _value(containers[0], "image") != self.handoff.get(
            "receiver_container_image"
        ):
            return ReadinessCheck(
                ReadinessStatus.MISMATCH, "receiver container image does not match approved input"
            )
        job_template = _value(_value(job, "template"), "template")
        if _name(_value(job, "name")) != job_name:
            return _check(job_name, _value(job, "name"), "worker.name")
        if _value(job, "reconciling", False):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "worker is still reconciling")
        if not _has_successful_terminal_condition(job):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "worker has no successful terminal condition")
        job_containers = _value(job_template, "containers", ())
        if _value(job_template, "service_account") != self.handoff.get(
            "worker_runtime_service_account_email"
        ):
            return _check(
                self.handoff.get("worker_runtime_service_account_email"),
                _value(job_template, "service_account"),
                "worker.service_account",
            )
        if len(job_containers) != 1 or _value(job_containers[0], "image") != self.handoff.get(
            "worker_container_image"
        ):
            return ReadinessCheck(
                ReadinessStatus.MISMATCH, "worker container image does not match approved input"
            )
        return ReadinessCheck(ReadinessStatus.VERIFIED, "Cloud Run receiver and worker verified")

    def _databases(self) -> ReadinessCheck:
        client = self.clients.get("firestore_admin")
        if client is None:
            return self._not_run()
        project = self.handoff.get("project_id", "")
        ids = (self.handoff.get("control_database_id"), self.handoff.get("runtime_database_id"))
        if not ids[0] or ids[0] == ids[1]:
            return ReadinessCheck(
                ReadinessStatus.MISMATCH, "control and runtime database IDs must be distinct"
            )
        for database_id, location in zip(
            ids,
            (
                self.handoff.get("control_database_location"),
                self.handoff.get("runtime_database_location"),
            ),
            strict=True,
        ):
            name = f"projects/{project}/databases/{database_id}"
            try:
                database = client.get_database(name=name, timeout=30.0)
            except Exception as exc:
                return ReadinessCheck(
                    ReadinessStatus.ERROR, f"Firestore database read failed: {type(exc).__name__}"
                )
            if (
                _name(_value(database, "name")) != name
                or _value(database, "location_id") != location
                or _enum_name(_value(database, "type_")) != "FIRESTORE_NATIVE"
            ):
                return ReadinessCheck(
                    ReadinessStatus.MISMATCH,
                    f"database {database_id} does not match approved name/location",
                )
        return ReadinessCheck(ReadinessStatus.VERIFIED, "named Firestore databases verified")

    def _trigger(self) -> ReadinessCheck:
        client = self.clients.get("eventarc")
        if client is None:
            return self._not_run()
        project = self.handoff.get("project_id", "")
        location = self.handoff.get("eventarc_trigger_location", "")
        name = f"projects/{project}/locations/{location}/triggers/{self.handoff.get('eventarc_trigger_name', '')}"
        try:
            trigger = client.get_trigger(name=name, timeout=30.0)
        except Exception as exc:
            return ReadinessCheck(
                ReadinessStatus.ERROR, f"Eventarc trigger read failed: {type(exc).__name__}"
            )
        filters = frozenset(
            (_value(item, "attribute"), _value(item, "value"), _value(item, "operator", ""))
            for item in (_value(trigger, "event_filters", ()) or ())
        )
        expected = frozenset(
            {
                ("type", "google.cloud.firestore.document.v1.created.withAuthContext", ""),
                ("database", self.handoff.get("control_database_id"), ""),
                (
                    "document",
                    self.handoff.get("request_document_path_pattern"),
                    "match-path-pattern",
                ),
            }
        )
        if filters != expected:
            return _check(expected, filters, "trigger.event_filters")
        destination = _value(trigger, "destination")
        run = _value(destination, "cloud_run")
        if _value(trigger, "service_account") != self.handoff.get(
            "eventarc_trigger_service_account_email"
        ):
            return _check(
                self.handoff.get("eventarc_trigger_service_account_email"),
                _value(trigger, "service_account"),
                "trigger.service_account",
            )
        if (
            _value(trigger, "event_data_content_type") != "application/protobuf"
            or _value(run, "path") != "/eventarc/firestore"
            or _value(run, "region") != self.handoff.get("receiver_cloud_run_region")
            or _name(_value(run, "service"))
            != f"projects/{project}/locations/{self.handoff.get('receiver_cloud_run_region', '')}/services/{self.handoff.get('receiver_cloud_run_service_name', '')}"
        ):
            return ReadinessCheck(
                ReadinessStatus.MISMATCH,
                "trigger destination/content type does not match approved input",
            )
        return ReadinessCheck(ReadinessStatus.VERIFIED, "Eventarc trigger verified")

    def _rules(self) -> ReadinessCheck:
        client = self.clients.get("firebaserules")
        if client is None:
            return self._not_run("official Firebase Rules discovery client was not supplied")
        source = self.rules_source
        if source is None:
            return self._not_run("approved firestore.rules source is required")
        if isinstance(source, Path):
            source = source.read_bytes()
        elif isinstance(source, str):
            source = source.encode("utf-8")
        source_hash = hashlib.sha256(source).hexdigest()
        expected_hash = self.handoff.get("rules_source_hash")
        if expected_hash and source_hash != expected_hash:
            return _check(expected_hash, source_hash, "rules_source_hash")
        project = self.handoff.get("project_id", "")
        number = self.select_project.get("project_number", "")
        for database_id in (self.handoff.get("control_database_id"), self.handoff.get("runtime_database_id")):
            release_name = f"projects/{project}/releases/cloud.firestore/{database_id}"
            try:
                release = client.projects().releases().get(name=release_name).execute()
                ruleset_name = release.get("rulesetName", "")
                ruleset = client.projects().rulesets().get(name=ruleset_name).execute()
            except Exception as exc:
                return ReadinessCheck(ReadinessStatus.ERROR, f"Rules read failed: {type(exc).__name__}")
            if release.get("name") != release_name or not ruleset_name.startswith(f"projects/{project}/"):
                return ReadinessCheck(ReadinessStatus.MISMATCH, f"Rules release {database_id} is not approved")
            files = (ruleset.get("source") or {}).get("files", [])
            if len(files) != 1 or files[0].get("name") != "firestore.rules" or files[0].get("content", "").encode("utf-8") != source:
                return ReadinessCheck(ReadinessStatus.MISMATCH, f"Rules source for {database_id} does not match")
            attachment = f"firestore.googleapis.com/projects/{number}/databases/{database_id}"
            if ruleset.get("attachmentPoint") != attachment:
                return _check(attachment, ruleset.get("attachmentPoint"), f"rules.{database_id}.attachmentPoint")
        return ReadinessCheck(ReadinessStatus.VERIFIED, "named Rules releases verified")

    def _firebase(self) -> ReadinessCheck:
        client = self.clients.get("identitytoolkit")
        if client is None:
            return self._not_run("official Identity Toolkit discovery client was not supplied")
        project = self.handoff.get("project_id", "")
        try:
            config = client.projects().getConfig(name=f"projects/{project}/config").execute()
            idp = client.projects().defaultSupportedIdpConfigs().get(name=f"projects/{project}/defaultSupportedIdpConfigs/google.com").execute()
        except Exception as exc:
            return ReadinessCheck(ReadinessStatus.ERROR, f"Firebase identity read failed: {type(exc).__name__}")
        if config.get("name") != f"projects/{project}/config" or not set(self.handoff.get("authorized_ui_domains", ())).issubset(set(config.get("authorizedDomains", ()))):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "Firebase authorized domains do not match")
        if idp.get("name") != f"projects/{project}/defaultSupportedIdpConfigs/google.com" or idp.get("enabled") is not True or idp.get("clientId") != self.handoff.get("identity_platform_google_web_client_id"):
            return ReadinessCheck(ReadinessStatus.MISMATCH, "Google identity provider config does not match")
        management = self.clients.get("firebase_management")
        app_id = self.handoff.get("firebase_web_app_id")
        if management is None or not app_id:
            return self._not_run("Firebase Web App Management read was not supplied")
        try:
            app = management.projects().webApps().get(
                name=f"projects/{project}/webApps/{app_id}"
            ).execute()
            config_app = management.projects().webApps().getConfig(
                name=f"projects/{project}/webApps/{app_id}"
            ).execute()
        except Exception as exc:
            return ReadinessCheck(ReadinessStatus.ERROR, f"Firebase Web App read failed: {type(exc).__name__}")
        if app.get("appId") != app_id or app.get("projectId") != project or config_app.get("appId") != app_id or config_app.get("projectId") != project:
            return ReadinessCheck(ReadinessStatus.MISMATCH, "Firebase Web App identity does not match approved project")
        return ReadinessCheck(ReadinessStatus.VERIFIED, "Firebase identity configuration verified")

    def verify(self) -> ReadinessReport:
        checks = {
            "project": self._project(),
            "cloud_run": self._run(),
            "databases": self._databases(),
            "eventarc": self._trigger(),
        }
        checks["rules"] = self._rules()
        checks["firebase"] = self._firebase()
        live_only = (
            "effective IAM and service-account actAs",
            "Eventarc auth-context writer provenance",
            "Rules enforcement and popup sign-in",
            "external Workspace behavior and image provenance",
        )
        return ReadinessReport(checks, live_only)


__all__ = ["ReadinessCheck", "ReadinessReport", "ReadinessStatus", "RuntimeReadinessVerifier"]
