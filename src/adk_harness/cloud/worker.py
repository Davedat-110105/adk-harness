"""Durable Cloud Run worker and deterministic Workspace action gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from adk_harness.governance.ledger import FirestoreActionLedger
from adk_harness.observability.tracing import (
    configure_safe_adk_logging,
    validate_safe_telemetry_environment,
)
from adk_harness.workflow.models import Approval, ChangeSet, TaskRequest
from adk_harness.workflow.reviewer import ADKReviewer, ReviewDecision
from adk_harness.workflow.sync import make_result_envelope, make_runtime_manifest
from adk_harness.workspace.connections import WorkspaceUnknownOutcome

from .state import WorkStatus


class ActionGate:
    """Revalidates immutable approval, trusted policy and mandatory review."""

    def __init__(self, *, policy_version: str, policy_checker: Any | None = None) -> None:
        self.policy_version = policy_version
        self.policy_checker = policy_checker

    def check(
        self,
        request: TaskRequest,
        changeset: ChangeSet,
        approval: Approval,
        review: Mapping[str, Any] | None,
    ) -> None:
        if request.intent != "apply":
            raise PermissionError("only apply requests may mutate Workspace")
        if self.policy_checker is not None and self.policy_checker(request, changeset) is not True:
            raise PermissionError("trusted policy denied Workspace mutation")
        if (
            request.policy_version != self.policy_version
            or changeset.policy_version != self.policy_version
        ):
            raise PermissionError("active policy version does not match request")
        if review is None or review.get("decision") != "allow":
            raise PermissionError("mandatory pre-action review is missing or did not allow")
        approval.require_for(
            changeset.content_hash,
            task_id=request.task_id,
            approver_id=request.user_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            action_scope=request.scope,
            resource_versions=changeset.resource_versions,
            policy_version=self.policy_version,
            trace_id=request.trace_id,
        )
        if changeset.task_id != request.task_id or changeset.user_id != request.user_id:
            raise PermissionError("changeset identity does not match request")


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    policy_version: str


@dataclass(frozen=True, slots=True)
class WorkerResult:
    status: str
    task_id: str
    checkpoint: int = 0
    results: tuple[Mapping[str, Any], ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    model: str
    project_id: str
    location: str
    credentials: Any = field(repr=False)

    def __post_init__(self) -> None:
        if not self.model.startswith("gemini-") or not self.project_id or not self.location:
            raise ValueError("planner requires a fixed trusted Vertex model configuration")


class WorkspaceHost(Protocol):
    def calendar_get_event(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def docs_get(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def calendar_create_event(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def calendar_update_event(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def calendar_delete_event(self, **kwargs: Any) -> Mapping[str, Any]: ...
    def docs_insert_text(self, **kwargs: Any) -> Mapping[str, Any]: ...


class WorkspaceAuthority:
    """Concrete pre-action access/version check using Workspace public reads."""

    def __init__(
        self,
        workspace: WorkspaceHost,
        *,
        policy_version: str,
        credential_loader: Any | None = None,
        membership_verifier: Any | None = None,
        required_scopes: tuple[str, ...] = (),
    ) -> None:
        self.workspace = workspace
        self.policy_version = policy_version
        self.credential_loader = credential_loader
        self.membership_verifier = membership_verifier
        self.required_scopes = tuple(required_scopes)

    def __call__(
        self, request: TaskRequest, changeset: ChangeSet,
        approval: Approval, action: Mapping[str, Any],
    ) -> bool:
        if (
            request.policy_version != self.policy_version
            or changeset.policy_version != self.policy_version
        ):
            return False
        try:
            approval.require_for(
                changeset.content_hash, task_id=request.task_id,
                approver_id=request.user_id, project_id=request.project_id,
                workspace_id=request.workspace_id, action_scope=request.scope,
                resource_versions=changeset.resource_versions,
                policy_version=self.policy_version, trace_id=request.trace_id,
            )
        except (PermissionError, ValueError):
            return False
        operation = action.get("operation")
        if self.credential_loader is not None:
            try:
                self.credential_loader(
                    subject=request.user_id, required_scopes=self.required_scopes
                )
            except TypeError:
                try:
                    self.credential_loader(request.user_id, self.required_scopes)
                except Exception:
                    return False
            except Exception:
                return False
        if self.membership_verifier is not None:
            try:
                member = self.membership_verifier(
                    project_id=request.project_id,
                    workspace_id=request.workspace_id,
                    firebase_uid=getattr(self.workspace, "firebase_uid", None),
                    google_subject=request.user_id,
                    resource=_resource_for_action(action),
                    operation=str(operation),
                )
            except TypeError:
                try:
                    member = self.membership_verifier(request, action)
                except Exception:
                    return False
            except Exception:
                return False
            if member is not True:
                return False
        consent = getattr(self.workspace, "consent", None)
        reference = getattr(self.workspace, "credential_reference", None)
        subject = getattr(reference, "subject", request.user_id)
        if consent is None or not consent.allows(
            subject=subject,
            application="calendar" if str(operation).startswith("calendar_") else "docs",
            resource=str(action.get("calendar_id", action.get("document_id", ""))),
            operation=str(operation),
        ):
            return False
        if operation in {"calendar_update_event", "calendar_delete_event"}:
            current = self.workspace.calendar_get_event(
                calendar_id=_string(action, "calendar_id"),
                event_id=_string(action, "event_id"),
            )
            return (
                current.get("etag") == action.get("etag")
                and current.get("etag") == _approved_resource_version(request, action)
            )
        if operation == "docs_insert_text":
            current = self.workspace.docs_get(document_id=_string(action, "document_id"))
            return (
                current.get("revisionId") == action.get("revision")
                and current.get("revisionId") == _approved_resource_version(request, action)
            )
        if operation == "calendar_create_event":
            body = _mapping(action, "body")
            event_id = _string(body, "id")
            try:
                current = self.workspace.calendar_get_event(
                    calendar_id=_string(action, "calendar_id"), event_id=event_id
                )
            except Exception:
                return True
            return not isinstance(current, Mapping) or not current.get("id")
        return False


class WorkspaceReconciler:
    """Resolve a reserved operation from authoritative Calendar/Docs reads."""

    def __init__(self, workspace: WorkspaceHost) -> None:
        self.workspace = workspace

    def resolve(self, action: Mapping[str, Any]) -> Mapping[str, Any] | None:
        operation = action.get("operation")
        if operation in {"calendar_create_event", "calendar_update_event", "calendar_delete_event"}:
            observed = self.workspace.calendar_get_event(
                calendar_id=_string(action, "calendar_id"),
                event_id=(
                    _string(_mapping(action, "body"), "id")
                    if operation == "calendar_create_event"
                    else _string(action, "event_id")
                ),
            )
            if not isinstance(observed, Mapping):
                return None
            if operation == "calendar_delete_event" and observed.get("status") == "cancelled":
                return (
                    {"resolved": True}
                    if observed.get("etag") and observed.get("etag") != action.get("etag")
                    else None
                )
            body = action.get("body")
            if operation == "calendar_create_event" and isinstance(body, Mapping):
                if observed.get("id") == body.get("id") and _contains_expected(observed, body):
                    return {"resolved": True}
            if operation == "calendar_update_event" and (
                observed.get("etag") != action.get("etag")
                and isinstance(body, Mapping)
                and _contains_expected(observed, body)
            ):
                return {"resolved": True}
            return None
        if operation == "docs_insert_text":
            observed = self.workspace.docs_get(document_id=_string(action, "document_id"))
            expected = {"text": action.get("text"), "index": action.get("index")}
            return (
                {"resolved": True}
                if observed.get("revisionId") != action.get("revision")
                and _contains_expected(observed, expected)
                else None
            )
        return None


class RuntimeFirestorePublisher:
    """Publish immutable result and manifest envelopes through Firestore SDK."""

    def __init__(
        self,
        client: Any,
        *,
        project_id: str,
        workspace_id: str,
        firebase_uid: str,
        google_subject: str | None = None,
    ) -> None:
        self.client = client
        self.project_id = project_id
        self.workspace_id = workspace_id
        self.firebase_uid = firebase_uid
        self.google_subject = google_subject

    def publish(
        self, *, task_id: str, result: Mapping[str, Any], manifest: Mapping[str, Any]
    ) -> None:
        if result.get("result_id") != result.get("result_hash"):
            raise ValueError("result envelope is not digest addressed")
        if manifest.get("result_id") != result.get("result_id"):
            raise ValueError("manifest and result IDs differ")
        payload = result.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("result envelope payload is missing")
        bindings: dict[str, str] = {
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "firebase_uid": self.firebase_uid,
            "task_id": task_id,
        }
        if self.google_subject is not None:
            bindings["google_subject"] = self.google_subject
        if any(payload.get(key) != value for key, value in bindings.items()):
            raise PermissionError("result payload is outside the configured namespace")
        if any(manifest.get(key) != value for key, value in bindings.items()):
            raise PermissionError("result manifest is outside the configured namespace")
        base = (
            f"projects/{self.project_id}/workspaces/{self.workspace_id}/users/"
            f"{self.firebase_uid}/tasks/{task_id}"
        )
        result_ref = self.client.document(f"{base}/results/{result['result_id']}")
        manifest_ref = self.client.document(f"{base}/manifests/latest")
        batch_factory = getattr(self.client, "batch", None)
        if callable(batch_factory):
            batch = cast(Any, batch_factory())
            batch.create(result_ref, dict(result))
            batch.set(manifest_ref, dict(manifest))
            batch.commit()
        else:
            # Synthetic offline clients predate WriteBatch; deployed official
            # clients always take the atomic branch above.
            result_ref.create(dict(result))
            manifest_ref.set(dict(manifest))


class Worker:
    """Executes a validated finite ChangeSet, persisting every checkpoint."""

    def __init__(
        self,
        *,
        config: WorkerConfig,
        state: Any,
        workspace: WorkspaceHost,
        gate: ActionGate | None = None,
        action_checker: Any | None = None,
        publisher: RuntimeFirestorePublisher | None = None,
        reviewer: Any | None = None,
        evidence_ledger: Any | None = None,
        authenticated_actor: str | None = None,
        policy_allowed: bool | None = None,
        approved_context: Mapping[str, Any] | None = None,
    ) -> None:
        self.config, self.state, self.workspace = config, state, workspace
        self.gate = gate or ActionGate(policy_version=config.policy_version)
        self.action_checker = action_checker or WorkspaceAuthority(
            workspace, policy_version=config.policy_version
        )
        self.publisher = publisher
        self.reviewer = reviewer
        self.evidence_ledger = evidence_ledger
        self.authenticated_actor = authenticated_actor
        self.policy_allowed = policy_allowed
        self.approved_context = approved_context

    def run(  # noqa: PLR0915
        self,
        request: TaskRequest,
        changeset: ChangeSet,
        *,
        approval: Approval,
        review: Mapping[str, Any] | None,
    ) -> WorkerResult:
        if self.reviewer is None or self.evidence_ledger is None:
            try:
                self.state.get(request.task_id)
            except KeyError:
                self.state.claim(
                    task_id=request.task_id,
                    request_id=request.task_id,
                    trace_id=request.trace_id,
                )
            self.state.update(
                request.task_id,
                status=WorkStatus.HELD,
                error="mandatory reviewer and durable evidence are required",
            )
            return WorkerResult(
                "held",
                request.task_id,
                reason="mandatory reviewer and durable evidence are required",
            )
        try:
            initial_review = review if self.reviewer is None else {"decision": "allow"}
            self.gate.check(request, changeset, approval, initial_review)
        except (PermissionError, ValueError) as exc:
            self.state.update(request.task_id, status=WorkStatus.HELD, error=str(exc)[:500])
            return WorkerResult("held", request.task_id, reason=str(exc))
        try:
            current = self.state.get(request.task_id)
        except KeyError:
            current = self.state.claim(
                task_id=request.task_id,
                request_id=request.task_id,
                trace_id=request.trace_id,
            )
        if current.status is WorkStatus.COMPLETED:
            prior = current.result if isinstance(current.result, Mapping) else {}
            return WorkerResult(
                "completed",
                request.task_id,
                current.checkpoint,
                tuple(prior.get("results", ())),
            )
        completed: list[Mapping[str, Any]] = []
        start = current.checkpoint
        for index, action in enumerate(changeset.changes):
            if index < start:
                continue
            operation_id = _operation_id(request, changeset, index)
            effective_review = review
            if self.reviewer is not None:
                try:
                    review_result = self.reviewer.review(
                        request,
                        changeset,
                        approved_context=self._review_context(request, changeset),
                        readonly_tools=("calendar_get_event", "calendar_list_events", "docs_get"),
                        policy_allowed=self.policy_allowed,
                    )
                    effective_review = {
                        "decision": getattr(review_result, "decision", None),
                        "findings": getattr(review_result, "findings", ()),
                        "change_hash": changeset.content_hash,
                    }
                    if effective_review["decision"] == ReviewDecision.ALLOW:
                        effective_review["decision"] = ReviewDecision.ALLOW.value
                except Exception:
                    effective_review = None
            elif self.evidence_ledger is not None:
                effective_review = None
            try:
                self.gate.check(request, changeset, approval, effective_review)
                if (
                    self.action_checker is not None
                    and self.action_checker(request, changeset, approval, action) is not True
                ):
                    raise PermissionError("current action authorization is unavailable")
                self._validate_current_action(request, changeset, action)
            except (PermissionError, ValueError) as exc:
                self.state.update(
                    request.task_id, status=WorkStatus.HELD, checkpoint=index, error=str(exc)[:500]
                )
                return WorkerResult("held", request.task_id, index, tuple(completed), str(exc))
            if not self.state.reserve(
                request.task_id, operation_id=operation_id, checkpoint=index
            ):
                self.state.update(
                    request.task_id,
                    status=WorkStatus.RECONCILING,
                    error="unresolved external action requires reconciliation",
                )
                return WorkerResult(
                    "reconciling", request.task_id, index, tuple(completed),
                    "unresolved external action requires reconciliation",
                )
            if self.evidence_ledger is not None:
                try:
                    self._record_evidence(
                        request, changeset, approval, operation_id, "allow", "pre_action"
                    )
                except Exception as exc:
                    self.state.update(
                        request.task_id,
                        status=WorkStatus.HELD,
                        checkpoint=index,
                        operation_id="",
                        error="pre-action audit unavailable",
                    )
                    return WorkerResult("held", request.task_id, index, tuple(completed), str(exc))
            try:
                result = self._execute(action, request, changeset)
            except WorkspaceUnknownOutcome as exc:
                self.state.update(
                    request.task_id,
                    status=WorkStatus.RECONCILING,
                    checkpoint=index,
                    error=str(exc)[:500],
                )
                return WorkerResult(
                    "reconciling", request.task_id, index, tuple(completed), str(exc)
                )
            except Exception as exc:
                self.state.update(
                    request.task_id,
                    status=WorkStatus.FAILED,
                    checkpoint=index,
                    error=str(exc)[:500],
                )
                return WorkerResult("failed", request.task_id, index, tuple(completed), str(exc))
            if self.evidence_ledger is not None:
                try:
                    self._record_evidence(
                        request, changeset, approval, operation_id, "allow", "completed"
                    )
                except Exception as exc:
                    self.state.update(
                        request.task_id,
                        status=WorkStatus.RECONCILING,
                        checkpoint=index,
                        error="post-action audit unavailable",
                    )
                    return WorkerResult(
                        "reconciling", request.task_id, index, tuple(completed), str(exc)
                    )
            completed.append(result)
            self.state.update(
                request.task_id,
                status=WorkStatus.RUNNING,
                checkpoint=index + 1,
                operation_id=operation_id,
                result={"results": completed, "operation_id": operation_id},
            )
            self.state.update(request.task_id, operation_id="")
            current = self.state.get(request.task_id)
        self.state.update(
            request.task_id,
            status=WorkStatus.COMPLETED,
            checkpoint=len(changeset.changes),
            result={"results": completed},
        )
        return WorkerResult("completed", request.task_id, len(changeset.changes), tuple(completed))

    def _review_context(
        self, request: TaskRequest, changeset: ChangeSet
    ) -> Mapping[str, Any]:
        if self.approved_context is not None:
            return json.loads(json.dumps(self.approved_context, ensure_ascii=False))
        return {
            "request": {
                "task_id": request.task_id,
                "project_id": request.project_id,
                "workspace_id": request.workspace_id,
                "user_id": request.user_id,
                "intent": request.intent,
                "policy_version": request.policy_version,
                "trace_id": request.trace_id,
            },
            "changeset": json.loads(changeset.canonical()),
        }

    def _record_evidence(  # noqa: PLR0917
        self,
        request: TaskRequest,
        changeset: ChangeSet,
        approval: Approval,
        operation_id: str,
        decision: str,
        outcome: str,
    ) -> None:
        ledger = self.evidence_ledger
        if ledger is None:
            raise RuntimeError("evidence ledger is not configured")
        ledger.record_evidence(
            actor=self.authenticated_actor or request.user_id,
            approval_hash=approval.change_hash,
            policy_version=self.config.policy_version,
            decision=decision,
            operation_id=operation_id,
            outcome=outcome,
            idempotency_key=f"{request.task_id}:{changeset.content_hash}:{operation_id}:{outcome}",
            trace_id=request.trace_id,
        )

    async def run_plan(
        self, request: TaskRequest, planner: ADKPlanner, *, firebase_uid: str,
        expires_at: datetime | None = None,
    ) -> WorkerResult:
        """Generate and durably publish a typed proposal without host mutations."""
        if request.intent != "plan":
            raise ValueError("run_plan requires a plan request")
        current = self.state.claim(
            task_id=request.task_id, request_id=request.task_id, trace_id=request.trace_id
        )
        if current.status is WorkStatus.DUPLICATE:
            return WorkerResult("duplicate", request.task_id, current.checkpoint)
        try:
            changeset = await planner.plan(request)
            if changeset.task_id != request.task_id or changeset.user_id != request.user_id:
                raise ValueError("planner proposal identity does not match request")
            expiry = expires_at or datetime.now(UTC) + timedelta(minutes=20)
            scope = list(request.apply_scopes) or _scope_strings(request.scope)
            payload = {
                "kind": "changeset_result",
                "project_id": request.project_id,
                "workspace_id": request.workspace_id,
                "firebase_uid": firebase_uid,
                "google_subject": request.user_id,
                "task_id": request.task_id,
                "scope": sorted(scope),
                "expires_at": expiry.isoformat(),
                "changeset": changeset.to_dict(),
            }
            result_envelope = make_result_envelope(payload)
            manifest = make_runtime_manifest(
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                firebase_uid=firebase_uid,
                google_subject=request.user_id,
                task_id=request.task_id,
                scope=sorted(scope),
                payload=payload,
                expires_at=expiry,
            )
            result = {
                "kind": "changeset_result",
                "result": result_envelope,
                "manifest": manifest,
            }
            if self.publisher is None:
                raise RuntimeError("runtime Firestore publisher is required for plan results")
            self.publisher.publish(
                task_id=request.task_id, result=result_envelope, manifest=manifest
            )
            self.state.update(
                request.task_id,
                status=WorkStatus.COMPLETED,
                checkpoint=len(changeset.changes),
                result=result,
            )
            return WorkerResult(
                "completed",
                request.task_id,
                len(changeset.changes),
                tuple(changeset.changes),
            )
        except Exception as exc:
            self.state.update(request.task_id, status=WorkStatus.FAILED, error=str(exc)[:500])
            return WorkerResult("failed", request.task_id, reason="plan generation failed")

    def reconcile(
        self, request: TaskRequest, changeset: ChangeSet, *, index: int,
        resolver: Any | None = None,
    ) -> WorkerResult:
        """Resolve one reserved action from authoritative host readback."""
        if not 0 <= index < len(changeset.changes):
            raise ValueError("reconciliation action index is out of range")
        operation_id = _operation_id(request, changeset, index)
        current = self.state.get(request.task_id)
        if current.operation_id != operation_id:
            raise PermissionError("reconciliation operation identity does not match")
        resolver_fn = resolver or WorkspaceReconciler(self.workspace).resolve
        observed = resolver_fn(changeset.changes[index])
        if not isinstance(observed, Mapping) or observed.get("resolved") is not True:
            self.state.update(
                request.task_id, status=WorkStatus.RECONCILING,
                error="authoritative action readback is incomplete",
            )
            return WorkerResult("reconciling", request.task_id, index)
        self.state.update(
            request.task_id, status=WorkStatus.RUNNING,
            checkpoint=index + 1, operation_id="", result={"reconciled": operation_id},
        )
        return WorkerResult("completed", request.task_id, index + 1)

    @staticmethod
    def _validate_current_action(
        request: TaskRequest, changeset: ChangeSet, action: Mapping[str, Any]
    ) -> None:
        if request.policy_version != changeset.policy_version:
            raise PermissionError("trusted policy changed")
        if request.resource_versions != changeset.resource_versions:
            raise PermissionError("resource version changed")
        if _scope_for(action) not in request.apply_scopes and _scope_for(
            action
        ) not in _scope_strings(request.scope):
            raise PermissionError("Workspace action is outside approved scope")

    def _execute(
        self, action: Mapping[str, Any], request: TaskRequest, changeset: ChangeSet
    ) -> Mapping[str, Any]:
        operation = action.get("operation")
        if operation not in {
            "calendar_create_event",
            "calendar_update_event",
            "calendar_delete_event",
            "docs_insert_text",
        }:
            raise PermissionError("unsupported Workspace operation")
        payload = dict(action)
        expected = _scope_for(action)
        if expected not in request.apply_scopes and expected not in _scope_strings(request.scope):
            raise PermissionError("Workspace action is outside approved scope")
        if request.resource_versions != changeset.resource_versions:
            raise PermissionError("resource versions changed")

        def authorize(name: str, actual: Mapping[str, Any]) -> bool:
            return name == operation and dict(actual) == _host_payload(action)

        if operation == "calendar_create_event":
            return self.workspace.calendar_create_event(
                calendar_id=_string(payload, "calendar_id"),
                body=_mapping(payload, "body"),
                host_authorizer=authorize,
            )
        if operation == "calendar_update_event":
            return self.workspace.calendar_update_event(
                calendar_id=_string(payload, "calendar_id"),
                event_id=_string(payload, "event_id"),
                body=_mapping(payload, "body"),
                approved_etag=_string(payload, "etag"),
                host_authorizer=authorize,
            )
        if operation == "calendar_delete_event":
            return self.workspace.calendar_delete_event(
                calendar_id=_string(payload, "calendar_id"),
                event_id=_string(payload, "event_id"),
                approved_etag=_string(payload, "etag"),
                host_authorizer=authorize,
            )
        return self.workspace.docs_insert_text(
            document_id=_string(payload, "document_id"),
            index=int(payload["index"]),
            text=_string(payload, "text"),
            required_revision_id=_string(payload, "revision"),
            host_authorizer=authorize,
        )


class _RuntimeAuthenticator:
    """Adapter that keeps the current Secret Manager grant at the host edge."""

    def __init__(self, loader: CredentialLoader, *, secret_version: str) -> None:
        self.loader = loader
        self.secret_version = secret_version

    def verified_credentials(
        self, purpose: Any, *, subject: str, required_scopes: tuple[str, ...] = ()
    ) -> Any:
        from adk_harness.auth import CredentialPurpose

        if purpose is not CredentialPurpose.WORKSPACE:
            raise PermissionError("worker only accepts Workspace credentials")
        return self.loader.load(
            secret_version=self.secret_version,
            subject=subject,
            required_scopes=tuple(required_scopes),
        )


def _official_identity_verifier(token: str, audience: str) -> Mapping[str, Any]:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    claims = id_token.verify_oauth2_token(token, Request(), audience)
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise PermissionError("Google identity issuer is invalid")
    return claims


def _official_grant_evidence(credentials: Any, required_scopes: tuple[str, ...]) -> tuple[str, ...]:
    # google-auth exposes granted_scopes only when the current authorization
    # response established them. Serialized ``Credentials.scopes`` is request
    # configuration and is deliberately not accepted as current grant proof.
    granted = getattr(credentials, "granted_scopes", None)
    if not isinstance(granted, (list, tuple, set)) or not granted:
        raise PermissionError("current OAuth response has no authoritative granted scopes")
    observed = tuple(sorted({str(scope) for scope in granted}))
    if not set(required_scopes).issubset(observed):
        raise PermissionError("current OAuth grant is missing required scopes")
    return observed


def _read_runtime_control(client: Any, *, project_id: str, workspace_id: str,
                          firebase_uid: str, task_id: str) -> Mapping[str, Any]:
    prefix = (
        f"projects/{project_id}/workspaces/{workspace_id}/members/{firebase_uid}/requests"
    )
    ref = client.document(f"{prefix}/{task_id}")
    snapshot = ref.get()
    if not getattr(snapshot, "exists", False):
        # Dispatch carries the stable task ID, while the immutable Firestore
        # document ID is a separate request ID. Resolve the latter by its
        # canonical task field rather than guessing a document name.
        query = client.collection(prefix).where("task_id", "==", task_id).limit(1)
        matches = list(query.stream())
        if not matches:
            raise PermissionError("immutable task request is unavailable")
        snapshot = matches[0]
        ref = getattr(snapshot, "reference", None)
        if ref is None:
            raise PermissionError("runtime task request reference is unavailable")
    parent = snapshot.to_dict() or {}
    approvals = [child.to_dict() or {} for child in ref.collection("approvals").stream()]
    return {
        "request": parent,
        "request_id": getattr(ref, "id", task_id),
        "approvals": approvals,
        "changeset": parent.get("changeset"),
        "changeset_hash": parent.get("changeset_hash"),
        "changeset_canonical": parent.get("changeset_canonical"),
        "provenance": parent.get("provenance"),
    }


def assemble_runtime_worker(  # noqa: PLR0915
    *,
    env: Mapping[str, str] | None = None,
    control_client: Any | None = None,
    runtime_client: Any | None = None,
    execution_client: Any | None = None,
    secret_manager_client: Any | None = None,
    workspace: WorkspaceHost | None = None,
    credential_loader: CredentialLoader | None = None,
    publisher: RuntimeFirestorePublisher | None = None,
    membership_verifier: Any | None = None,
    planner: ADKPlanner | None = None,
    state: Any | None = None,
    reviewer: Any | None = None,
    evidence_ledger: Any | None = None,
    model_runtime_credentials: Any | None = None,
    model_runtime_credentials_provider: Any | None = None,
) -> tuple[Worker, Mapping[str, Any]]:
    """Assemble the deployed worker from trusted runtime configuration.

    All external clients are official SDK clients and are constructed lazily.
    Missing identity, grant, membership, task, or namespace configuration is a
    hard error; callers must surface that as a held/failed execution.
    """
    values = dict(os.environ if env is None else env)
    configure_safe_adk_logging()
    required = ("ADK_PROJECT_ID", "ADK_WORKSPACE_ID", "ADK_FIREBASE_UID",
                "ADK_GOOGLE_SUBJECT", "ADK_TASK_ID", "ADK_CLIENT_ID",
                "ADK_WORKSPACE_GRANT_SECRET_VERSION", "ADK_POLICY_VERSION")
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise PermissionError(f"runtime configuration is incomplete: {', '.join(missing)}")
    project_id = values["ADK_PROJECT_ID"]
    workspace_id = values["ADK_WORKSPACE_ID"]
    firebase_uid = values["ADK_FIREBASE_UID"]
    subject = values["ADK_GOOGLE_SUBJECT"]
    task_id = values["ADK_TASK_ID"]
    if control_client is None:
        from google.cloud import firestore

        control_client = firestore.Client(
            project=project_id, database=values.get("ADK_CONTROL_DATABASE", "control")
        )
    trusted = _read_runtime_control(
        control_client, project_id=project_id, workspace_id=workspace_id,
        firebase_uid=firebase_uid, task_id=task_id,
    )
    body = trusted.get("request")
    if not isinstance(body, Mapping):
        raise PermissionError("runtime task request is malformed")
    request = TaskRequest.from_dict(body)
    validate_safe_telemetry_environment(values, require_explicit=request.intent == "apply")
    if (request.project_id, request.workspace_id, request.user_id) != (
        project_id, workspace_id, subject
    ):
        raise PermissionError("runtime task owner is outside the configured namespace")
    if runtime_client is None:
        runtime_client = execution_client
    if runtime_client is None and state is None:
        from google.cloud import firestore
        runtime_database = values.get("ADK_RUNTIME_DATABASE")
        if not runtime_database:
            raise PermissionError("ADK_RUNTIME_DATABASE and runtime Firestore client are required")
        runtime_client = firestore.Client(project=project_id, database=runtime_database)
    if state is None:
        from .state import FirestoreExecutionStore
        if runtime_client is None:
            raise PermissionError("runtime Firestore client is required for execution state")
        state = FirestoreExecutionStore(runtime_client)
    if credential_loader is None:
        if secret_manager_client is None:
            from google.cloud import secretmanager

            secret_manager_client = secretmanager.SecretManagerServiceClient()
        credential_loader = CredentialLoader(
            secret_manager_client=secret_manager_client,
            expected_client_id=values["ADK_CLIENT_ID"],
            identity_verifier=_official_identity_verifier,
            grant_evidence_verifier=_official_grant_evidence,
            approved_versions={subject: values["ADK_WORKSPACE_GRANT_SECRET_VERSION"]},
        )
    auth = _RuntimeAuthenticator(
        credential_loader, secret_version=values["ADK_WORKSPACE_GRANT_SECRET_VERSION"]
    )
    if workspace is None:
        from adk_harness.workspace.connections import (
            CredentialReference,
            WorkspaceConnection,
            WorkspaceConsent,
        )

        raw_consent = body.get("workspace_consent") or values.get("ADK_WORKSPACE_CONSENT")
        if isinstance(raw_consent, str):
            raw_consent = json.loads(raw_consent)
        if not isinstance(raw_consent, Mapping):
            raise PermissionError("explicit Workspace consent configuration is required")
        consent_data = dict(raw_consent)
        if isinstance(consent_data.get("expires_at"), str):
            consent_data["expires_at"] = datetime.fromisoformat(consent_data["expires_at"])
        consent = WorkspaceConsent(**consent_data)
        reference = CredentialReference(
            subject=subject,
            reference=values["ADK_WORKSPACE_GRANT_SECRET_VERSION"],
            scopes=tuple(consent_data.get("scopes", ())),
        )
        workspace = cast(Any, WorkspaceConnection(
            authenticator=cast(Any, auth), credential_reference=reference, consent=consent,
            resource_allowlist=consent.resources,
        ))
    if membership_verifier is None:
        def default_membership_verifier(**kwargs: Any) -> bool:
            ref = control_client.document(
                f"projects/{project_id}/workspaces/{workspace_id}/members/{firebase_uid}"
            )
            snap = ref.get()
            record = snap.to_dict() if getattr(snap, "exists", False) else None
            expires_at = record.get("expires_at") if isinstance(record, Mapping) else None
            return (
                isinstance(record, Mapping)
                and record.get("google_sub") == subject
                and record.get("status") == "active"
                and isinstance(expires_at, datetime)
                and expires_at.tzinfo is not None
                and expires_at > datetime.now(expires_at.tzinfo)
            )
        membership_verifier = default_membership_verifier
    authority = WorkspaceAuthority(
        cast(WorkspaceHost, workspace), policy_version=values["ADK_POLICY_VERSION"],
        credential_loader=lambda *, subject, required_scopes: credential_loader.load(
            secret_version=values["ADK_WORKSPACE_GRANT_SECRET_VERSION"],
            subject=subject,
            required_scopes=tuple(required_scopes),
        ),
        membership_verifier=membership_verifier,
    )
    if publisher is None:
        if runtime_client is None:
            raise PermissionError("runtime Firestore client is required for publication")
        publisher = RuntimeFirestorePublisher(
            runtime_client, project_id=project_id, workspace_id=workspace_id,
            firebase_uid=firebase_uid, google_subject=subject,
        )
    if evidence_ledger is None:
        if runtime_client is None:
            raise PermissionError("runtime Firestore client is required for policy evidence")
        evidence_ledger = FirestoreActionLedger(
            runtime_client,
            owner_namespace=f"{project_id}/{workspace_id}/{firebase_uid}/{task_id}",
        )
    # Workspace grant credentials are never model authority. Production must
    # inject a separately provisioned runtime Vertex credential explicitly.
    if reviewer is None and request.intent == "apply":
        if not values.get("ADK_MODEL_RUNTIME_PROJECT_ID") or not values.get(
            "ADK_MODEL_RUNTIME_LOCATION"
        ):
            raise PermissionError("trusted model runtime project and location are required")
        if model_runtime_credentials is None:
            try:
                if model_runtime_credentials_provider is not None:
                    model_runtime_credentials = model_runtime_credentials_provider(
                        project_id=values.get("ADK_MODEL_RUNTIME_PROJECT_ID", ""),
                        location=values.get("ADK_MODEL_RUNTIME_LOCATION", ""),
                    )
                else:
                    import google.auth

                    model_runtime_credentials, _ = google.auth.default(
                        scopes=("https://www.googleapis.com/auth/cloud-platform",)
                    )
            except Exception as exc:
                raise PermissionError(
                    "separate model runtime credentials are required"
                ) from exc
        if model_runtime_credentials is None:
            raise PermissionError("separate model runtime credentials are required")
        from google.adk.sessions import InMemorySessionService

        reviewer = ADKReviewer(
            model=values.get("ADK_MODEL_RUNTIME_MODEL", "gemini-3.5-flash"),
            project_id=values.get("ADK_MODEL_RUNTIME_PROJECT_ID", ""),
            location=values.get("ADK_MODEL_RUNTIME_LOCATION", ""),
            credentials=model_runtime_credentials,
            session_service=InMemorySessionService(),
        )
    worker = Worker(
        config=WorkerConfig(policy_version=values["ADK_POLICY_VERSION"]),
        state=state, workspace=cast(WorkspaceHost, workspace), action_checker=authority,
        publisher=publisher,
        reviewer=reviewer,
        evidence_ledger=evidence_ledger,
        authenticated_actor=subject,
        policy_allowed=True,
    )
    return worker, {
        "request": request,
        "trusted": trusted,
        "firebase_uid": firebase_uid,
        "google_subject": subject,
        "authenticator": auth,
        "workspace": workspace,
        "credential_loader": credential_loader,
        "planner": planner,
        "env": values,
    }


class ADKPlanner:
    """Run the accepted Workspace ADK app and validate its typed proposal."""

    def __init__(
        self,
        *,
        app: Any,
        session_service: Any,
        runner_factory: Any | None = None,
        config: PlannerConfig | None = None,
    ) -> None:
        self.app = app
        self.session_service = session_service
        self.runner_factory = runner_factory
        self.config = config
        self._model = None
        if config is not None:
            from google.adk.models.google_llm import Gemini

            self._model = Gemini(
                model=config.model,
                client_kwargs={
                    "vertexai": True,
                    "project": config.project_id,
                    "location": config.location,
                    "credentials": config.credentials,
                },
            )
            self.app.orchestrator.model = self._model

    async def plan(self, request: TaskRequest) -> ChangeSet:
        from google.adk.runners import Runner
        from google.genai import types

        factory = Runner if self.config is not None else (self.runner_factory or Runner)
        runner = factory(app=self.app.app, session_service=self.session_service)
        session_id = f"plan-{request.task_id}"
        if hasattr(self.session_service, "create_session"):
            created = self.session_service.create_session(
                app_name=self.app.app.name, user_id=request.user_id, session_id=session_id
            )
            if hasattr(created, "__await__"):
                await created
        text_parts: list[str] = []
        try:
            async for event in runner.run_async(
                user_id=request.user_id,
                session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text=request.content)]),
            ):
                content = getattr(event, "content", None)
                for part in getattr(content, "parts", ()) or ():
                    text = getattr(part, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
        finally:
            close = getattr(runner, "close", None)
            if callable(close):
                close()
            await _close_owned_model(self._model)
        proposal = _parse_proposal("".join(text_parts))
        return ChangeSet(
            task_id=request.task_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            changes=tuple(proposal["changes"]),
            resource_versions=request.resource_versions,
            policy_version=request.policy_version,
            trace_id=request.trace_id,
        )


class CredentialLoader:
    """Loads an exact owner Secret Manager version using official SDKs."""

    def __init__(
        self,
        *,
        secret_manager_client: Any,
        expected_client_id: str,
        credential_factory: Any | None = None,
        identity_verifier: Any | None = None,
        scope_verifier: Any | None = None,
        grant_evidence_verifier: Any | None = None,
        approved_versions: Mapping[str, str] | None = None,
    ) -> None:
        self.client = secret_manager_client
        self.expected_client_id = expected_client_id
        self.credential_factory = credential_factory
        self.identity_verifier = identity_verifier
        self.scope_verifier = scope_verifier
        self.grant_evidence_verifier = grant_evidence_verifier
        self.approved_versions = dict(approved_versions or {})

    def load(self, *, secret_version: str, subject: str, required_scopes: tuple[str, ...]) -> Any:
        if (
            not re.fullmatch(r"projects/[^/]+/secrets/[^/]+/versions/[1-9][0-9]*", secret_version)
            or self.approved_versions.get(subject) != secret_version
        ):
            raise PermissionError("an exact Secret Manager version is required")
        response = self.client.access_secret_version(request={"name": secret_version})
        raw = getattr(getattr(response, "payload", None), "data", None)
        if not raw:
            raise PermissionError("Workspace grant secret is empty")
        from google.oauth2.credentials import Credentials

        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if not isinstance(payload, Mapping):
            raise PermissionError("Workspace grant secret is malformed")
        credentials_json = payload.get("credentials_json", payload)
        factory = self.credential_factory or Credentials.from_authorized_user_info
        credentials = factory(credentials_json)
        if getattr(credentials, "client_id", self.expected_client_id) != self.expected_client_id:
            raise PermissionError("Workspace grant client identity is invalid")
        if self.identity_verifier is None:
            raise PermissionError("current Google identity verification is required")
        from google.auth.transport.requests import Request

        credentials.refresh(Request())
        token = getattr(credentials, "id_token", None)
        if not token:
            raise PermissionError("current Workspace credentials have no ID token")
        try:
            claims = self.identity_verifier(str(token), self.expected_client_id)
        except TypeError:
            claims = self.identity_verifier(str(token))
        if not isinstance(claims, Mapping):
            raise PermissionError("current Google identity could not be verified")
        if claims.get("sub") != subject or claims.get("aud") != self.expected_client_id:
            raise PermissionError("Workspace grant owner or audience does not match")
        if self.grant_evidence_verifier is not None:
            verified_scopes = self.grant_evidence_verifier(credentials, tuple(required_scopes))
        elif self.scope_verifier is not None:
            # Retained only for existing offline callers. Production runtime
            # wiring uses grant_evidence_verifier, never an ID token as scope
            # evidence.
            verified_scopes = self.scope_verifier(str(token))
        else:
            verified_scopes = getattr(credentials, "granted_scopes", None)
        if not isinstance(verified_scopes, (list, tuple, set)):
            raise PermissionError("current Google scopes could not be verified")
        if not set(required_scopes).issubset({str(item) for item in verified_scopes}):
            raise PermissionError("Workspace grant is missing current verified scopes")
        return credentials


def _operation_id(request: TaskRequest, changeset: ChangeSet, index: int) -> str:
    seed = f"{request.user_id}:{request.task_id}:{changeset.content_hash}:{index}"
    return hashlib.sha256(seed.encode()).hexdigest()


async def _close_owned_model(model: Any) -> None:
    if model is None:
        return
    for client_name in ("_client", "_async_client", "client", "async_client"):
        client = getattr(model, client_name, None)
        close = getattr(client, "close", None)
        if callable(close):
            result: Any = close()
            if hasattr(result, "__await__"):
                await result


def _parse_proposal(raw: str) -> Mapping[str, Any]:
    if not raw:
        raise ValueError("ADK planner returned no proposal")
    value = raw.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        proposal = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("ADK planner returned invalid structured JSON") from exc
    if not isinstance(proposal, Mapping) or not isinstance(proposal.get("changes"), list):
        raise ValueError("ADK planner proposal must contain a changes array")
    schemas = {
        "calendar_create_event": {"operation", "calendar_id", "body"},
        "calendar_update_event": {"operation", "calendar_id", "event_id", "body", "etag"},
        "calendar_delete_event": {"operation", "calendar_id", "event_id", "etag"},
        "docs_insert_text": {"operation", "document_id", "index", "text", "revision"},
    }
    for action in proposal["changes"]:
        operation = action.get("operation") if isinstance(action, Mapping) else None
        index_value = action.get("index") if isinstance(action, Mapping) else None
        if (
            operation not in schemas
            or set(action) != schemas[operation]
            or (operation.startswith("calendar_") and operation != "calendar_delete_event"
                and not isinstance(action.get("body"), Mapping))
            or (operation == "docs_insert_text"
                and (not isinstance(index_value, int) or index_value < 1
                     or not isinstance(action.get("text"), str)
                     or not isinstance(action.get("revision"), str)))
        ):
            raise ValueError("ADK planner produced an unsupported action")
    return proposal


def _scope_for(action: Mapping[str, Any]) -> str:
    operation = str(action.get("operation", ""))
    if operation.startswith("calendar_"):
        return f"calendar:{action.get('calendar_id', '')}"
    return f"docs:{action.get('document_id', '')}"


def _resource_for_action(action: Mapping[str, Any]) -> str:
    operation = str(action.get("operation", ""))
    if operation.startswith("calendar_"):
        return str(action.get("calendar_id", ""))
    return str(action.get("document_id", ""))


def _approved_resource_version(request: TaskRequest, action: Mapping[str, Any]) -> str | None:
    """Return the exact approved version for one finite action resource."""
    operation = str(action.get("operation", ""))
    if operation.startswith("calendar_"):
        key = f"calendar:{action.get('event_id', action.get('calendar_id', ''))}"
        return request.resource_versions.get(key) or request.resource_versions.get(
            f"calendar:{action.get('calendar_id', '')}"
        )
    return request.resource_versions.get(f"docs:{action.get('document_id', '')}")


def _contains_expected(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Compare the approved postcondition without rejecting server metadata."""
    for key, value in expected.items():
        if isinstance(value, Mapping):
            nested = observed.get(key)
            if not isinstance(nested, Mapping) or not _contains_expected(nested, value):
                return False
        elif observed.get(key) != value:
            return False
    return True


def _scope_strings(scope: Mapping[str, Any]) -> set[str]:
    return {
        str(v)
        for values in scope.values()
        if isinstance(values, (list, tuple, set))
        for v in values
    }


def _host_payload(action: Mapping[str, Any]) -> dict[str, Any]:
    op = action["operation"]
    if op == "calendar_create_event":
        return {"calendar_id": action["calendar_id"], "body": action["body"]}
    if op == "calendar_update_event":
        return {
            "calendar_id": action["calendar_id"],
            "event_id": action["event_id"],
            "body": action["body"],
            "etag": action["etag"],
        }
    if op == "calendar_delete_event":
        return {
            "calendar_id": action["calendar_id"],
            "event_id": action["event_id"],
            "etag": action["etag"],
        }
    return {
        "document_id": action["document_id"],
        "index": action["index"],
        "text": action["text"],
        "revision": action["revision"],
    }


def _string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"action field {key} is required")
    return value


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"action field {key} must be an object")
    return value


def worker_entry(
    request: Mapping[str, Any] | None = None,
    *,
    dependencies: Mapping[str, Any] | None = None,
) -> WorkerResult:
    """Importable Cloud Run Job target for one persisted task.

    The job receives only task/trace identifiers in its environment. It reads
    the immutable control request and approvals through Firestore, assembles
    the current verified Workspace authority, and then executes or plans the
    finite action set. No secret is accepted in the job payload.
    """
    overrides = dict(dependencies or {})
    env = dict(os.environ)
    configured_env = overrides.pop("env", None)
    if isinstance(configured_env, Mapping):
        env.update({str(key): str(value) for key, value in configured_env.items()})
    if isinstance(request, Mapping):
        for key in ("task_id", "trace_id"):
            value = request.get(key)
            if isinstance(value, str) and value:
                env["ADK_TASK_ID" if key == "task_id" else "ADK_TRACE_ID"] = value
    worker, context = assemble_runtime_worker(env=env, **overrides)
    task = context["request"]
    trusted = context["trusted"]
    if task.intent == "plan":
        planner = context.get("planner")
        if planner is None:
            planner = _build_runtime_planner(context)
        return asyncio.run(
            worker.run_plan(task, planner, firebase_uid=context["firebase_uid"])
        )
    try:
        worker.state.get(task.task_id)
    except KeyError:
        worker.state.claim(
            task_id=task.task_id,
            request_id=str(context["trusted"].get("request_id", task.task_id)),
            trace_id=task.trace_id,
        )
    raw_changeset = trusted.get("changeset")
    if not isinstance(raw_changeset, Mapping):
        worker.state.update(
            task.task_id, status=WorkStatus.HELD, error="approved ChangeSet is missing"
        )
        return WorkerResult("held", task.task_id, reason="approved ChangeSet is missing")
    changeset = ChangeSet.from_dict(raw_changeset)
    if (
        trusted.get("changeset_hash") != changeset.content_hash
        or trusted.get("changeset_canonical") != changeset.canonical()
    ):
        worker.state.update(
            task.task_id, status=WorkStatus.HELD, error="approved ChangeSet digest is invalid"
        )
        return WorkerResult("held", task.task_id, reason="approved ChangeSet digest is invalid")
    approval: Approval | None = None
    for item in trusted.get("approvals", ()):
        if not isinstance(item, Mapping) or item.get("approval_type") != "exact_apply":
            continue
        candidate = item.get("approval", item)
        if isinstance(candidate, Mapping):
            try:
                approval = Approval.from_dict(
                    {key: value for key, value in candidate.items() if key != "approval_type"}
                )
            except (TypeError, ValueError, KeyError):
                continue
            break
    if approval is None:
        worker.state.update(
            task.task_id, status=WorkStatus.HELD, error="exact apply approval is missing"
        )
        return WorkerResult("held", task.task_id, reason="exact apply approval is missing")
    # Phase 7 supplies mandatory review evidence. The entry remains fail
    # closed until that persisted evidence is present.
    review = trusted.get("review")
    return worker.run(task, changeset, approval=approval, review=review)


def _build_runtime_planner(context: Mapping[str, Any]) -> ADKPlanner:
    from coactra import Policy, Scope
    from google.adk.sessions import InMemorySessionService

    from adk_harness.workspace.app import build_workspace_app

    request = context["request"]
    workspace = context["workspace"]
    env = context["env"]
    reference = workspace.credential_reference
    app = asyncio.run(
        build_workspace_app(
            policy=Policy.default_deny(),
            scope=Scope(tenant_id=request.project_id, namespace=request.workspace_id),
            authenticator=context["authenticator"],
            credential_reference=reference,
            consent=workspace.consent,
            resource_allowlist=workspace.resource_allowlist,
            services=tuple(workspace.consent.applications),
            model=env.get("ADK_MODEL", "gemini-3.5-flash"),
            principal=request.user_id,
        )
    )
    credentials = context["credential_loader"].load(
        secret_version=env["ADK_WORKSPACE_GRANT_SECRET_VERSION"],
        subject=request.user_id,
        required_scopes=(),
    )
    config = PlannerConfig(
        model=env.get("ADK_MODEL", "gemini-3.5-flash"),
        project_id=request.project_id,
        location=env.get("ADK_VERTEX_LOCATION", "us-central1"),
        credentials=credentials,
    )
    return ADKPlanner(
        app=app, session_service=InMemorySessionService(), config=config
    )


__all__ = [
    "ADKPlanner",
    "ActionGate",
    "CredentialLoader",
    "PlannerConfig",
    "RuntimeFirestorePublisher",
    "Worker",
    "WorkerConfig",
    "WorkerResult",
    "assemble_runtime_worker",
    "worker_entry",
]
