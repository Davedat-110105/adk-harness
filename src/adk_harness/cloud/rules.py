"""Checkpointed named Firestore Rules publication via the official SDK.

Terraform provider 8.0.0 cannot set Ruleset.attachmentPoint. This module uses
the generated google-api-python-client firebaserules.v1 discovery client and
never constructs HTTP requests itself.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from .bootstrap import CheckpointStore


class RulesPublicationError(RuntimeError):
    """Rules publication did not reach a verified named release."""


def _safe_database_id(database_id: str) -> str:
    if not database_id or "/" in database_id or database_id.startswith("projects"):
        raise ValueError("database ID must be a single Firestore database name")
    return database_id


class RulesPublisher:
    """Publish and verify one source to one named Firestore database."""

    def __init__(
        self,
        *,
        project_id: str,
        project_number: str,
        source: str,
        credentials: Any,
        checkpoints: CheckpointStore,
        discovery_build: Callable[..., Any] | None = None,
        approved_source_hash: str | None = None,
        source_version: str | None = None,
        max_pages: int = 100,
    ) -> None:
        if not project_id or not project_number or credentials is None:
            raise ValueError("project ID and project number are required")
        self.project_id = project_id
        self.project_number = project_number
        self.source = source
        self.source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        self.checkpoints = checkpoints
        self.credentials = credentials
        self._build = discovery_build or self._official_build
        self.approved_source_hash = approved_source_hash
        self.source_version = source_version or self.source_hash[:12]
        self.max_pages = max(1, max_pages)
        self._approved_project_id = project_id
        self._approved_project_number = project_number
        self._approved_source = source
        self._approved_source_hash = self.source_hash
        self._approved_source_version = self.source_version

    def _validate_approved_inputs(self) -> None:
        if (
            self.project_id != self._approved_project_id
            or self.project_number != self._approved_project_number
            or self.source != self._approved_source
            or self.source_version != self._approved_source_version
            or self.source_hash != self._approved_source_hash
            or hashlib.sha256(self.source.encode("utf-8")).hexdigest() != self._approved_source_hash
        ):
            raise RulesPublicationError("Rules publication inputs changed after approval")

    def approval_binding(
        self,
        *,
        control_database_id: str = "control",
        runtime_database_id: str = "runtime",
    ) -> dict[str, Any]:
        self._validate_approved_inputs()
        if control_database_id == runtime_database_id:
            raise ValueError("control and runtime database IDs must be distinct")
        database_ids = (control_database_id, runtime_database_id)
        return {
            "project_id": self.project_id,
            "project_number": self.project_number,
            "source_hash": self.source_hash,
            "source_version": self.source_version,
            "release_names": [
                f"projects/{self.project_id}/releases/cloud.firestore/{database_id}"
                for database_id in database_ids
            ],
            "database_ids": list(database_ids),
            "attachment_points": [
                f"firestore.googleapis.com/projects/{self.project_number}/databases/{database_id}"
                for database_id in database_ids
            ],
        }

    @staticmethod
    def _official_build(*args: Any, **kwargs: Any) -> Any:
        from googleapiclient.discovery import build

        return build(*args, **kwargs)

    def _service(self) -> Any:
        return self._build(
            "firebaserules", "v1", credentials=self.credentials, cache_discovery=False
        )

    @staticmethod
    def _execute(request: Any) -> Any:
        try:
            return request.execute(num_retries=0)
        except Exception:
            raise RulesPublicationError("official Rules SDK request failed") from None

    @staticmethod
    def _get_release(request: Any) -> dict[str, Any]:
        try:
            value = request.execute(num_retries=0)
        except Exception as error:
            code = getattr(error, "status_code", getattr(error, "code", None))
            if code in (404, "NOT_FOUND"):
                return {}
            raise RulesPublicationError("official Rules SDK request failed") from None
        return value if isinstance(value, dict) else {}

    def _find_existing_ruleset(self, service: Any, attachment_point: str) -> str | None:
        """Reconcile a crash after Rules API accepted auto-ID creation."""
        rulesets_api = service.projects().rulesets()
        list_method = getattr(rulesets_api, "list", None)
        if list_method is None:
            return None
        page_token = ""
        for _ in range(self.max_pages):
            params = {"pageToken": page_token} if page_token else {}
            request = list_method(name=f"projects/{self.project_id}", pageSize=100, **params)
            page = self._execute(request)
            for summary in page.get("rulesets", []):
                name = str(summary.get("name", ""))
                if not name:
                    continue
                record = self._execute(rulesets_api.get(name=name))
                if (
                    name.startswith(f"projects/{self.project_id}/rulesets/")
                    and record.get("attachmentPoint") == attachment_point
                    and record.get("source", {}).get("files", [])
                    == [{"name": "firestore.rules", "content": self.source}]
                ):
                    return name
            page_token = str(page.get("nextPageToken", ""))
            if not page_token:
                return None
        raise RulesPublicationError("Rules API pagination exceeded its bound")

    def _verify_ruleset(self, rulesets_api: Any, ruleset_name: str, attachment_point: str) -> None:
        if not ruleset_name.startswith(f"projects/{self.project_id}/rulesets/"):
            raise RulesPublicationError("Ruleset belongs to a different project")
        record = self._execute(rulesets_api.get(name=ruleset_name))
        files = record.get("source", {}).get("files", [])
        source = next(
            (item.get("content") for item in files if item.get("name") == "firestore.rules"),
            None,
        )
        if str(record.get("attachmentPoint", "")) != attachment_point or source != self.source:
            raise RulesPublicationError("Ruleset source or attachment does not match")

    def publish(self, database_id: str) -> dict[str, str]:  # noqa: PLR0915
        self._validate_approved_inputs()
        database_id = _safe_database_id(database_id)
        key = f"rules:{database_id}"
        saved = self.checkpoints.get(key)
        if saved and saved.get("source_hash") != self.source_hash:
            if self.approved_source_hash != self.source_hash:
                raise RulesPublicationError("checkpoint source hash does not match requested Rules")
            key = f"rules:{database_id}:{self.source_hash}"
            saved = self.checkpoints.get(key)
        release_name = f"projects/{self.project_id}/releases/cloud.firestore/{database_id}"
        attachment_point = (
            f"firestore.googleapis.com/projects/{self.project_number}/databases/{database_id}"
        )
        service = self._service()
        try:
            binding = {
                "database_id": database_id,
                "project_id": self.project_id,
                "project_number": self.project_number,
                "release_name": release_name,
                "attachment_point": attachment_point,
                "source_hash": self.source_hash,
                "source_version": self.source_version,
            }
            if saved is None:
                saved = {**binding, "status": "ruleset_pending"}
                self.checkpoints.put(key, saved)
            elif any(saved.get(name) != value for name, value in binding.items()):
                raise RulesPublicationError("Rules checkpoint binding does not match request")
            rulesets_api = service.projects().rulesets()
            ruleset_name = str(saved.get("ruleset_name", ""))
            if ruleset_name and not ruleset_name.startswith(
                f"projects/{self.project_id}/rulesets/"
            ):
                raise RulesPublicationError("Rules checkpoint targets a different project")
            if not ruleset_name:
                ruleset_name = self._find_existing_ruleset(service, attachment_point) or ""
            if not ruleset_name:
                try:
                    ruleset = self._execute(
                        rulesets_api.create(
                            name=f"projects/{self.project_id}",
                            body={
                                "source": {
                                    "files": [{"name": "firestore.rules", "content": self.source}]
                                },
                                "attachmentPoint": attachment_point,
                            },
                        )
                    )
                except RulesPublicationError:
                    ruleset_name = self._find_existing_ruleset(service, attachment_point) or ""
                    if not ruleset_name:
                        raise
                else:
                    ruleset_name = str(ruleset.get("name", ""))
            if not ruleset_name:
                raise RulesPublicationError("Rules API returned no ruleset name")
            # Validate the exact target before mutating any release.
            self._verify_ruleset(rulesets_api, ruleset_name, attachment_point)
            saved = {**saved, "status": "release_pending", "ruleset_name": ruleset_name}
            self.checkpoints.put(key, saved)
            release_api = service.projects().releases()
            release = self._get_release(release_api.get(name=release_name))
            if release and str(release.get("name", release_name)) != release_name:
                raise RulesPublicationError(
                    "Rules API returned a release for a different destination"
                )
            old_ruleset = str(release.get("rulesetName", ""))
            if old_ruleset and old_ruleset != ruleset_name:
                if not old_ruleset.startswith(f"projects/{self.project_id}/rulesets/"):
                    raise RulesPublicationError("existing release targets a different project")
                old_record = self._execute(rulesets_api.get(name=old_ruleset))
                if str(old_record.get("attachmentPoint", "")) != attachment_point:
                    raise RulesPublicationError("existing release targets a different database")
            if old_ruleset != ruleset_name:
                release_body = {"name": release_name, "rulesetName": ruleset_name}
                if release:
                    self._execute(
                        release_api.patch(
                            name=release_name,
                            body={"release": release_body},
                        )
                    )
                else:
                    self._execute(
                        release_api.create(name=f"projects/{self.project_id}", body=release_body)
                    )
            release = self._get_release(release_api.get(name=release_name))
            if (
                str(release.get("name", release_name)) != release_name
                or str(release.get("rulesetName", "")) != ruleset_name
            ):
                raise RulesPublicationError("Rules release does not point at the approved Ruleset")
            ruleset_record = self._execute(rulesets_api.get(name=ruleset_name))
            actual_attachment = str(ruleset_record.get("attachmentPoint", ""))
            files = ruleset_record.get("source", {}).get("files", [])
            actual_source = next(
                (item.get("content") for item in files if item.get("name") == "firestore.rules"),
                None,
            )
            if actual_attachment != attachment_point or actual_source != self.source:
                raise RulesPublicationError(
                    "named Rules release source or attachment does not match"
                )
            complete = {**binding, "status": "complete", "ruleset_name": ruleset_name}
            self.checkpoints.put(key, complete)
            return {**complete, "database_id": database_id, "release_name": release_name}
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
            else:
                http = getattr(service, "_http", None)
                close_http = getattr(http, "close", None)
                if callable(close_http):
                    close_http()

    def publish_both(
        self, control_database_id: str, runtime_database_id: str
    ) -> tuple[dict[str, str], dict[str, str]]:
        if control_database_id == runtime_database_id:
            raise ValueError("control and runtime database IDs must be distinct")
        return self.publish(control_database_id), self.publish(runtime_database_id)
