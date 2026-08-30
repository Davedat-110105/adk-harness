"""Authenticated Firestore Eventarc receiver and Cloud Run dispatch boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from google.events.cloud.firestore_v1 import DocumentEventData

from adk_harness.workflow.models import TaskRequest

from .state import InMemoryExecutionStore, WorkRecord, WorkStatus


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    project_id: str
    database: str = "control"
    path_prefix: str | None = None

    def __post_init__(self) -> None:
        if not self.project_id or "/" in self.project_id:
            raise ValueError("project_id is invalid")
        if not self.database or "/" in self.database:
            raise ValueError("database is invalid")


@dataclass(frozen=True, slots=True)
class ReceiverResult:
    status: str
    task_id: str | None = None
    reason: str | None = None
    record: WorkRecord | None = None


class EventarcProvenanceAdapter:
    """Verify originating-user auth context supplied at the Eventarc edge.

    Firestore document fields are not provenance. The adapter accepts only a
    bearer token from the authenticated CloudEvent/request context, verifies it
    with Google's Firebase token verifier, and derives both identities from the
    verified claims. If the platform does not provide that context, it returns
    ``None`` and the receiver holds the delivery.
    """

    def __init__(
        self,
        *,
        firebase_project_id: str,
        expected_delivery_authid: str | None = None,
        token_verifier: Callable[[str, str], Mapping[str, Any]] | None = None,
    ) -> None:
        if not firebase_project_id:
            raise ValueError("firebase_project_id is required")
        self.firebase_project_id = firebase_project_id
        self.expected_delivery_authid = expected_delivery_authid
        self.token_verifier = token_verifier

    def __call__(self, event: Mapping[str, Any]) -> Mapping[str, Any] | None:
        extensions = event.get("extensions")
        if not isinstance(extensions, Mapping):
            extensions = {}
        if self.expected_delivery_authid is not None and (
            extensions.get("authtype") != "service-account"
            or extensions.get("authid") != self.expected_delivery_authid
        ):
            return None
        token = _auth_context_token(event)
        if not token:
            return None
        try:
            if self.token_verifier is None:
                from google.auth.transport.requests import Request
                from google.oauth2 import id_token

                claims = id_token.verify_firebase_token(
                    token, Request(), audience=self.firebase_project_id
                )
            else:
                claims = self.token_verifier(token, self.firebase_project_id)
        except Exception:
            return None
        if not isinstance(claims, Mapping):
            return None
        issuer = f"https://securetoken.google.com/{self.firebase_project_id}"
        if claims.get("iss") != issuer:
            return None
        firebase_uid = claims.get("sub")
        firebase = claims.get("firebase")
        identities = firebase.get("identities") if isinstance(firebase, Mapping) else None
        subjects = identities.get("google.com") if isinstance(identities, Mapping) else None
        if not isinstance(firebase_uid, str) or not firebase_uid:
            return None
        if not isinstance(subjects, (list, tuple)) or len(subjects) != 1:
            return None
        google_subject = subjects[0]
        if not isinstance(google_subject, str) or not google_subject:
            return None
        return {"firebase_uid": firebase_uid, "google_subject": google_subject}


# Eventarc delivers the withAuthContext variant when a trigger asks for the
# originating user, which this receiver requires to verify provenance. The
# plain type stays accepted for callers that supply provenance another way.
CREATED_EVENT_TYPES = frozenset(
    {
        "google.cloud.firestore.document.v1.created",
        "google.cloud.firestore.document.v1.created.withAuthContext",
    }
)


class EventarcReceiver:
    """Small receiver that validates event identity before durable claiming."""

    def __init__(
        self,
        *,
        config: ReceiverConfig,
        store: Any | None = None,
        dispatch: Callable[[TaskRequest], Any] | None = None,
        provenance_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
        control_reader: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.store = store or InMemoryExecutionStore()
        self.dispatch = dispatch
        self.provenance_verifier = provenance_verifier
        self.control_reader = control_reader

    def handle(self, event: Any) -> ReceiverResult:
        event = _event_mapping(event)
        if event.get("type") not in CREATED_EVENT_TYPES:
            return ReceiverResult(
                "ignored", reason="only immutable task-request creation is handled"
            )
        if not self._valid_source(event) or not self._valid_subject(event):
            return ReceiverResult("held", reason="Eventarc source or document namespace is invalid")
        provenance = (
            self.provenance_verifier(event) if self.provenance_verifier is not None else None
        )
        if not isinstance(provenance, Mapping):
            return ReceiverResult("held", reason="originating-user provenance is not verified")
        if self.control_reader is None:
            return ReceiverResult("held", reason="control database reread is not configured")
        subject = str(event.get("subject", ""))
        try:
            trusted = self.control_reader(subject)
        except Exception:
            return ReceiverResult("held", reason="control database reread failed")
        body = trusted.get("request")
        if not isinstance(body, Mapping):
            return ReceiverResult("held", reason="immutable task request is unavailable")
        data = event.get("data")
        if not isinstance(data, Mapping):
            data = {}
        if "fields" in data and isinstance(data["fields"], Mapping):
            _decode_fields(data["fields"])
        try:
            task = TaskRequest.from_dict(body)
        except (TypeError, ValueError, KeyError) as exc:
            return ReceiverResult("held", reason=f"task request rejected: {exc}")
        if task.intent not in {"plan", "apply"}:
            return ReceiverResult("held", task_id=task.task_id, reason="unsupported task intent")
        request_id = _request_id_from_subject(str(event.get("subject", "")))
        if request_id is None:
            return ReceiverResult("held", task_id=task.task_id, reason="request ID is missing")
        if provenance.get("firebase_uid") != _firebase_uid_from_subject(subject):
            return ReceiverResult(
                "held", task_id=task.task_id, reason="provenance owner does not match path"
            )
        if provenance.get("google_subject") != task.user_id:
            return ReceiverResult(
                "held",
                task_id=task.task_id,
                reason="provenance user does not match request",
            )
        if _workspace_from_subject(subject) != task.workspace_id:
            return ReceiverResult(
                "held", task_id=task.task_id,
                reason="request workspace does not match its physical path",
            )
        if trusted.get("request_hash") != task.content_hash:
            return ReceiverResult("held", task_id=task.task_id, reason="request hash is invalid")
        if trusted.get("request_id") != request_id:
            return ReceiverResult("held", task_id=task.task_id, reason="request ID is invalid")
        if not _valid_approvals(
            trusted.get("approvals"), task, trusted.get("changeset"),
            changeset_hash=trusted.get("changeset_hash"),
            changeset_canonical=trusted.get("changeset_canonical"),
        ):
            return ReceiverResult(
                "held",
                task_id=task.task_id,
                reason="required approval is missing or invalid",
            )
        claimed = self.store.claim(
            task_id=task.task_id, request_id=request_id, trace_id=task.trace_id
        )
        if claimed.status is WorkStatus.DUPLICATE:
            return ReceiverResult("duplicate", task_id=task.task_id, record=claimed)
        if self.dispatch is not None:
            dispatch_id = f"dispatch:{task.task_id}:{task.trace_id}"
            self.store.update(task.task_id, status=WorkStatus.RUNNING, operation_id=dispatch_id)
            try:
                dispatch_with_identity = getattr(self.dispatch, "dispatch_with_identity", None)
                if callable(dispatch_with_identity):
                    operation = dispatch_with_identity(
                        task,
                        firebase_uid=str(provenance["firebase_uid"]),
                        google_subject=str(provenance["google_subject"]),
                    )
                else:
                    operation = self.dispatch(task)
                operation_name = getattr(getattr(operation, "operation", None), "name", None)
                self.store.update(
                    task.task_id,
                    status=WorkStatus.RUNNING,
                    dispatch_operation=str(operation_name) if operation_name else dispatch_id,
                )
            except Exception:
                self.store.update(
                    task.task_id,
                    status=WorkStatus.RECONCILING,
                    error="dispatch acknowledgement is uncertain",
                )
                return ReceiverResult(
                    "held",
                    task_id=task.task_id,
                    reason="dispatch acknowledgement is uncertain",
                )
        self.store.update(task.task_id, status=WorkStatus.RUNNING)
        return ReceiverResult("claimed", task_id=task.task_id, record=self.store.get(task.task_id))

    def _valid_source(self, event: Mapping[str, Any]) -> bool:
        expected = (
            "//firestore.googleapis.com/projects/"
            f"{self.config.project_id}/databases/{self.config.database}"
        )
        return event.get("source") == expected

    def _valid_subject(self, event: Mapping[str, Any]) -> bool:
        subject = event.get("subject")
        prefix = self.config.path_prefix or (
            f"documents/projects/{self.config.project_id}/databases/{self.config.database}/documents/"
        )
        if not isinstance(subject, str) or not subject.startswith(prefix):
            return False
        parts = subject[len(prefix) :].split("/")
        return (
            len(parts) == 8
            and parts[0] == "projects"
            and parts[1] == self.config.project_id
            and parts[2] == "workspaces"
            and bool(parts[3])
            and parts[4] == "members"
            and bool(parts[5])
            and parts[6] == "requests"
            and bool(parts[7])
        )


class CloudRunDispatcher:
    """Dispatches only task and trace IDs through the official Cloud Run SDK."""

    def __init__(
        self, *, job_name: str, client: Any | None = None,
        operations_client: Any | None = None,
    ) -> None:
        self.job_name = job_name
        self.client = client
        self.operations_client = operations_client

    def __call__(self, task: TaskRequest) -> Any:
        return self._run(task)

    def dispatch_with_identity(
        self, task: TaskRequest, *, firebase_uid: str, google_subject: str
    ) -> Any:
        """Run a job with identity derived from verified Eventarc context."""
        return self._run(
            task,
            extra_env={
                "ADK_FIREBASE_UID": firebase_uid,
                "ADK_GOOGLE_SUBJECT": google_subject,
                "ADK_WORKSPACE_ID": task.workspace_id,
            },
        )

    def _run(self, task: TaskRequest, *, extra_env: Mapping[str, str] | None = None) -> Any:
        if self.client is None:
            from google.cloud import run_v2

            self.client = run_v2.JobsClient()
        from google.cloud import run_v2

        environment = [
            {"name": "ADK_TASK_ID", "value": task.task_id},
            {"name": "ADK_TRACE_ID", "value": task.trace_id},
        ]
        if extra_env:
            environment.extend({"name": key, "value": value} for key, value in extra_env.items())
        request = run_v2.RunJobRequest(
            name=self.job_name,
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[
                    run_v2.RunJobRequest.Overrides.ContainerOverride(
                        env=environment
                    )
                ]
            ),
        )
        # RunJobRequest has no request_id idempotency field.  retry=None avoids
        # silently replaying an ambiguous non-idempotent submission.
        return self.client.run_job(request=request, retry=None)

    def reconcile(self, operation_name: str) -> str:
        """Read an accepted RunJob operation without resubmitting it."""
        if not operation_name or operation_name.startswith("dispatch:"):
            raise ValueError("an official Cloud Run operation name is required")
        # ``run_job`` returns the standard google-api-core Future whose
        # ``operation.name`` is a resource in the public Operations service.
        # JobsClient.get_operation is not the supported readback boundary.
        operations_client: Any = self.operations_client
        if operations_client is None:
            if self.client is not None and not hasattr(self.client, "transport") and hasattr(
                self.client, "get_operation"
            ):
                operations_client = self.client
            else:
                # The generated Jobs transport owns the matching public
                # OperationsClient/channel; use it when available.
                transport = getattr(self.client, "transport", None)
                operations_client = getattr(transport, "operations_client", None)
                if operations_client is None:
                    operations_client = self.client
        try:
            operation = cast(Any, operations_client).get_operation(name=operation_name)
        except (TypeError, KeyError):
            # A narrow compatibility path for old synthetic fakes. Production
            # always takes the official OperationsClient branch above.
            if self.client is None or not hasattr(self.client, "get_operation"):
                raise
            operation = self.client.get_operation(request={"name": operation_name})
        if not getattr(operation, "done", False):
            return "pending"
        if getattr(operation, "error", None):
            return "failed"
        return "accepted"

    def reconcile_record(self, store: Any, task_id: str) -> ReceiverResult:
        """Resolve a persisted dispatch operation and update durable state."""
        record = store.get(task_id)
        operation_name = record.dispatch_operation
        if not operation_name:
            raise ValueError("execution record has no official dispatch operation")
        status = self.reconcile(operation_name)
        if status == "pending":
            store.update(task_id, status=WorkStatus.RECONCILING)
            return ReceiverResult("reconciling", task_id=task_id, record=store.get(task_id))
        if status == "failed":
            store.update(task_id, status=WorkStatus.FAILED, error="Cloud Run operation failed")
            return ReceiverResult("failed", task_id=task_id, record=store.get(task_id))
        store.update(task_id, status=WorkStatus.RUNNING)
        return ReceiverResult("accepted", task_id=task_id, record=store.get(task_id))


def _event_mapping(event: Any) -> Mapping[str, Any]:
    if isinstance(event, Mapping):
        value = event.get("data")
        if isinstance(value, bytes):
            return dict(event, data=_document_event_data(value))
        return event
    result: dict[str, Any] = {}
    for key in ("type", "source", "subject", "data"):
        value = getattr(event, key, None)
        if value is not None:
            if key == "data" and isinstance(value, bytes):
                value = _document_event_data(value)
            result[key] = value
    extensions = getattr(event, "extensions", None)
    if extensions:
        result["extensions"] = dict(extensions)
    return result


def _auth_context_token(event: Mapping[str, Any]) -> str | None:
    """Extract a bearer token only from documented auth/request context."""
    candidates = (
        event.get("auth_context"),
        event.get("authentication_context"),
        event.get("request_auth"),
        event.get("request"),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            context = candidate
            auth = context.get("auth")
            if isinstance(auth, Mapping):
                context = {**context, **auth}
            direct = (
                context.get("firebase_id_token")
                or context.get("id_token")
                or context.get("idToken")
                or context.get("token")
            )
            if isinstance(direct, str) and direct:
                return direct
            headers = context.get("headers")
            if isinstance(headers, Mapping):
                value = headers.get("authorization") or headers.get("Authorization")
                if isinstance(value, str) and value.lower().startswith("bearer "):
                    token = value[7:].strip()
                    if token:
                        return token
    return None


def _document_event_data(payload: bytes) -> dict[str, Any]:
    parsed = DocumentEventData.deserialize(payload)
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(parsed._pb, preserving_proto_field_name=True)


def _valid_approvals(
    value: Any,
    task: TaskRequest,
    raw_changeset: Any,
    *,
    changeset_hash: Any = None,
    changeset_canonical: Any = None,
) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    from adk_harness.workflow.models import Approval

    required = {"upload_run"}
    expected_hashes = {"upload_run": task.content_hash}
    if task.intent == "apply":
        if not isinstance(raw_changeset, Mapping):
            return False
        try:
            from adk_harness.workflow.models import ChangeSet

            changeset = ChangeSet.from_dict(raw_changeset)
        except (TypeError, ValueError, KeyError):
            return False
        if (
            changeset.task_id != task.task_id
            or changeset.project_id != task.project_id
            or changeset.workspace_id != task.workspace_id
            or changeset.user_id != task.user_id
            or changeset.policy_version != task.policy_version
            or changeset.trace_id != task.trace_id
            or changeset.resource_versions != task.resource_versions
        ):
            return False
        # These are envelope fields written by the trusted control commit.
        # A nested value is not authoritative because it can be copied into a
        # ChangeSet payload without proving that the parent commit was intact.
        if changeset_hash != changeset.content_hash:
            return False
        if changeset_canonical != changeset.canonical():
            return False
        required.add("exact_apply")
        expected_hashes["exact_apply"] = changeset.content_hash
    found: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        approval_type = raw.get("approval_type")
        body = raw.get("approval", raw)
        if approval_type not in required or not isinstance(body, Mapping):
            continue
        body = {key: value for key, value in body.items() if key != "approval_type"}
        try:
            approval = Approval.from_dict(body)
            approval.require_for(
                expected_hashes[approval_type],
                task_id=task.task_id,
                approver_id=task.user_id,
                project_id=task.project_id,
                workspace_id=task.workspace_id,
                action_scope=task.scope,
                resource_versions=task.resource_versions,
                policy_version=task.policy_version,
                trace_id=task.trace_id,
            )
        except (TypeError, ValueError, KeyError):
            continue
        found.add(approval_type)
    return found == required


def _firebase_uid_from_subject(subject: str) -> str | None:
    marker = "/members/"
    if marker not in subject:
        return None
    return subject.split(marker, 1)[1].split("/", 1)[0]


def _workspace_from_subject(subject: str) -> str | None:
    marker = "/workspaces/"
    if marker not in subject:
        return None
    return subject.split(marker, 1)[1].split("/", 1)[0]


def _request_id_from_subject(subject: str) -> str | None:
    marker = "/requests/"
    if marker not in subject:
        return None
    value = subject.rsplit(marker, 1)[1].split("/", 1)[0]
    return value if value and value not in {".", ".."} else None


def _decode_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    def decode(value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        if "stringValue" in value:
            return value["stringValue"]
        if "integerValue" in value:
            return int(value["integerValue"])
        if "booleanValue" in value:
            return bool(value["booleanValue"])
        if "mapValue" in value:
            return _decode_fields(value["mapValue"].get("fields", {}))
        if "arrayValue" in value:
            return [decode(item) for item in value["arrayValue"].get("values", [])]
        return {key: decode(item) for key, item in value.items()}

    return {key: decode(value) for key, value in fields.items()}


def firestore_event(request: Any) -> Any:
    """Functions Framework target; deployment injects configured receiver."""
    receiver = _runtime_receiver()
    return receiver.handle(request)


def _runtime_receiver() -> EventarcReceiver:
    import os

    from google.cloud import firestore

    config = ReceiverConfig(
        project_id=os.environ["ADK_PROJECT_ID"],
        database=os.environ.get("ADK_CONTROL_DATABASE", "control"),
        path_prefix=os.environ.get("ADK_CONTROL_PATH_PREFIX"),
    )
    # Control is authoritative input and is read-only for the receiver. Keep
    # execution claims/checkpoints on the separately authorized runtime DB.
    control_client = firestore.Client(project=config.project_id, database=config.database)
    runtime_database = os.environ.get("ADK_RUNTIME_DATABASE")
    if not runtime_database:
        raise RuntimeError("ADK_RUNTIME_DATABASE is required for receiver execution state")
    runtime_client = firestore.Client(project=config.project_id, database=runtime_database)
    from .state import FirestoreExecutionStore

    def read_control(subject: str) -> Mapping[str, Any]:
        marker = "/documents/"
        path = subject.split(marker, 1)[1] if marker in subject else ""
        ref = control_client.document(path)
        snapshot = ref.get()
        if not snapshot.exists:
            return {}
        parent = snapshot.to_dict() or {}
        approvals = []
        for child in ref.collection("approvals").stream():
            approvals.append(child.to_dict() or {})
        return {
            "request": parent,
            "approvals": approvals,
            "changeset": parent.get("changeset"),
            "changeset_hash": parent.get("changeset_hash"),
            "changeset_canonical": parent.get("changeset_canonical"),
            "provenance": parent.get("provenance"),
        }

    def verify_provenance(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
        firebase_project_id = os.environ.get("ADK_FIREBASE_PROJECT_ID")
        if not firebase_project_id:
            return None
        return EventarcProvenanceAdapter(
            firebase_project_id=firebase_project_id,
            expected_delivery_authid=os.environ.get("ADK_EVENTARC_AUTH_ID"),
        )(event)

    job_name = os.environ.get("ADK_WORKER_JOB_NAME")
    dispatcher = CloudRunDispatcher(job_name=job_name) if job_name else None
    return EventarcReceiver(
        config=config,
        store=FirestoreExecutionStore(runtime_client),
        dispatch=dispatcher,
        provenance_verifier=verify_provenance,
        control_reader=read_control,
    )


__all__ = [
    "CloudRunDispatcher",
    "EventarcProvenanceAdapter",
    "EventarcReceiver",
    "ReceiverConfig",
    "ReceiverResult",
    "firestore_event",
]
