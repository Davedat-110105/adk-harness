from datetime import UTC, datetime, timedelta

import pytest

from adk_harness.cloud.handler import (
    CloudRunDispatcher,
    EventarcProvenanceAdapter,
    EventarcReceiver,
    ReceiverConfig,
)
from adk_harness.cloud.state import InMemoryExecutionStore, WorkStatus
from adk_harness.cloud.worker import (
    ActionGate,
    ADKPlanner,
    CredentialLoader,
    RuntimeFirestorePublisher,
    Worker,
    WorkerConfig,
    assemble_runtime_worker,
    worker_entry,
)
from adk_harness.workflow.models import Approval, ChangeSet, TaskRequest
from adk_harness.workflow.reviewer import ReviewDecision


class _Review:
    decision = ReviewDecision.ALLOW
    findings = ()


class _Reviewer:
    def review(self, *_args, **_kwargs):
        return _Review()


class _Evidence:
    def record_evidence(self, **_kwargs):
        return "evidence"

EVENT_SUBJECT = (
    "documents/projects/project-a/databases/control/documents/"
    "projects/project-a/workspaces/workspace-a/members/firebase-a/requests/request-a"
)


def request(*, intent: str = "apply") -> TaskRequest:
    return TaskRequest(
        project_id="project-a",
        workspace_id="workspace-a",
        user_id="google-user-a",
        content="update calendar",
        intent=intent,
        scope={"calendar": ["cal-a"]},
        apply_scopes=("calendar:cal-a",),
        resource_versions={"calendar:event-a": "etag-1"},
        policy_version="policy-1",
        task_id="task-a",
    )


def approval_for(req: TaskRequest, digest: str | None = None) -> Approval:
    now = datetime.now(UTC)
    return Approval(
        task_id=req.task_id,
        project_id=req.project_id,
        workspace_id=req.workspace_id,
        change_hash=digest or req.content_hash,
        approver_id=req.user_id,
        action_scope=req.scope,
        resource_versions=req.resource_versions,
        policy_version=req.policy_version,
        trace_id=req.trace_id,
        approved_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def test_claim_is_durable_and_duplicate_delivery_is_not_dispatched():
    store = InMemoryExecutionStore()
    first = store.claim(task_id="task-a", request_id="request-a", trace_id="trace-a")
    second = store.claim(task_id="task-a", request_id="request-b", trace_id="trace-b")

    assert first.status is WorkStatus.CLAIMED
    assert second.status is WorkStatus.DUPLICATE
    assert store.get("task-a").request_id == "request-a"


def test_receiver_holds_unverified_eventarc_provenance():
    receiver = EventarcReceiver(
        config=ReceiverConfig(
            project_id="project-a",
            database="control",
            path_prefix="projects/project-a/databases/control/documents/",
        ),
        store=InMemoryExecutionStore(),
        dispatch=lambda _: pytest.fail("unverified event must not dispatch"),
        provenance_verifier=lambda _: None,
        control_reader=lambda _: {},
    )
    result = receiver.handle(
        {
            "type": "google.cloud.firestore.document.v1.created",
            "source": "//firestore.googleapis.com/projects/project-a/databases/control",
            "subject": EVENT_SUBJECT,
            "data": {"intent": "apply"},
            "extensions": {"authtype": "service-account", "authid": "delivery-a"},
        }
    )
    assert result.status == "held"


def test_receiver_ignores_audit_writes_and_only_accepts_task_request_creation():
    seen: list[str] = []
    receiver = EventarcReceiver(
        config=ReceiverConfig(
            project_id="project-a",
            database="control",
            path_prefix="projects/project-a/databases/control/documents/",
        ),
        store=InMemoryExecutionStore(),
        dispatch=lambda item: seen.append(item.task_id),
        provenance_verifier=lambda _: {
            "google_subject": "google-user-a",
            "firebase_uid": "firebase-a",
        },
        control_reader=lambda _: {
            "request": request(intent="plan").to_dict(),
            "request_id": "request-a",
            "request_hash": request(intent="plan").content_hash,
            "approvals": [
                {
                    "approval_type": "upload_run",
                    **approval_for(request(intent="plan")).to_dict(),
                }
            ],
        },
    )
    event = {
        "type": "google.cloud.firestore.document.v1.updated",
        "source": "//firestore.googleapis.com/projects/project-a/databases/control",
        "subject": EVENT_SUBJECT,
        "data": {"intent": "apply"},
    }
    assert receiver.handle(event).status == "ignored"
    assert seen == []


def test_receiver_claims_verified_task_request_once():
    seen: list[str] = []
    task = request(intent="plan")
    receiver = EventarcReceiver(
        config=ReceiverConfig(project_id="project-a", database="control"),
        store=InMemoryExecutionStore(),
        dispatch=lambda item: seen.append(item.task_id),
        provenance_verifier=lambda _: {
            "google_subject": "google-user-a",
            "firebase_uid": "firebase-a",
        },
        control_reader=lambda _: {
            "request": task.to_dict(),
            "request_id": "request-a",
            "request_hash": task.content_hash,
            "approvals": [{"approval_type": "upload_run", **approval_for(task).to_dict()}],
        },
    )
    event = {
        "type": "google.cloud.firestore.document.v1.created",
        "source": "//firestore.googleapis.com/projects/project-a/databases/control",
        "subject": EVENT_SUBJECT,
        "data": task.to_dict(),
    }
    result = receiver.handle(event)
    assert result.status == "claimed"
    assert seen == ["task-a"]


def test_action_gate_requires_exact_approval_and_review_before_mutation():
    req = request()
    changes = ChangeSet(
        task_id=req.task_id,
        project_id=req.project_id,
        workspace_id=req.workspace_id,
        user_id=req.user_id,
        changes=(
            {
                "operation": "calendar_create_event",
                "calendar_id": "cal-a",
                "body": {
                    "id": "eventa1",
                    "start": {"date": "2030-01-01"},
                    "end": {"date": "2030-01-02"},
                    "reminders": {"useDefault": False, "overrides": []},
                },
            },
        ),
        resource_versions=req.resource_versions,
        policy_version=req.policy_version,
        trace_id=req.trace_id,
    )
    gate = ActionGate(policy_version="policy-1")
    with pytest.raises(PermissionError):
        gate.check(req, changes, approval_for(req, changes.content_hash), review=None)


def test_worker_holds_when_mandatory_reviewer_or_evidence_is_not_configured():
    store = InMemoryExecutionStore()
    req = request()
    changes = ChangeSet(
        task_id=req.task_id, project_id=req.project_id, workspace_id=req.workspace_id,
        user_id=req.user_id, changes=(), resource_versions=req.resource_versions,
        policy_version=req.policy_version, trace_id=req.trace_id,
    )
    result = Worker(
        config=WorkerConfig(policy_version="policy-1"), state=store, workspace=object()
    ).run(
        req,
        changes,
        approval=approval_for(req, changes.content_hash),
        review={"decision": "allow"},
    )
    assert result.status == "held"


def test_worker_uses_finite_catalog_and_persists_checkpoint():
    store = InMemoryExecutionStore()
    calls: list[dict] = []

    class Host:
        def calendar_create_event(self, **kwargs):
            calls.append(kwargs)
            return {"id": kwargs["body"]["id"]}

    req = request()
    changes = ChangeSet(
        task_id=req.task_id,
        project_id=req.project_id,
        workspace_id=req.workspace_id,
        user_id=req.user_id,
        changes=(
            {
                "operation": "calendar_create_event",
                "calendar_id": "cal-a",
                "body": {
                    "id": "eventa1",
                    "start": {"date": "2030-01-01"},
                    "end": {"date": "2030-01-02"},
                    "reminders": {"useDefault": False, "overrides": []},
                },
            },
        ),
        resource_versions=req.resource_versions,
        policy_version=req.policy_version,
        trace_id=req.trace_id,
    )
    approval = approval_for(req, changes.content_hash)
    worker = Worker(
        config=WorkerConfig(policy_version="policy-1"), state=store, workspace=Host(),
        action_checker=lambda *_: True, reviewer=_Reviewer(), evidence_ledger=_Evidence(),
    )
    result = worker.run(req, changes, approval=approval, review={"decision": "allow"})
    assert result.status == "completed"
    assert len(calls) == 1
    assert store.get(req.task_id).checkpoint == 1


def test_worker_reserves_action_before_external_call_and_reconciles_after_crash():
    store = InMemoryExecutionStore()
    req = request()
    changes = ChangeSet(
        task_id=req.task_id,
        project_id=req.project_id,
        workspace_id=req.workspace_id,
        user_id=req.user_id,
        changes=(
            {
                "operation": "calendar_create_event",
                "calendar_id": "cal-a",
                "body": {
                    "id": "eventa1",
                    "start": {"date": "2030-01-01"},
                    "end": {"date": "2030-01-02"},
                    "reminders": {"useDefault": False, "overrides": []},
                },
            },
        ),
        resource_versions=req.resource_versions,
        policy_version=req.policy_version,
        trace_id=req.trace_id,
    )
    approval = approval_for(req, changes.content_hash)

    class CrashingHost:
        def calendar_create_event(self, **kwargs):
            raise SystemExit("crash after external success")

    worker = Worker(
        config=WorkerConfig(policy_version="policy-1"), state=store,
        workspace=CrashingHost(), action_checker=lambda *_: True,
        reviewer=_Reviewer(), evidence_ledger=_Evidence(),
    )
    with pytest.raises(SystemExit):
        worker.run(req, changes, approval=approval, review={"decision": "allow"})
    assert store.get(req.task_id).operation_id
    result = Worker(
        config=WorkerConfig(policy_version="policy-1"), state=store,
        workspace=CrashingHost(), action_checker=lambda *_: True,
        reviewer=_Reviewer(), evidence_ledger=_Evidence(),
    ).run(req, changes, approval=approval, review={"decision": "allow"})
    assert result.status == "reconciling"


def test_secret_loader_rejects_latest_and_requires_identity_verifier():
    class Client:
        def access_secret_version(self, **kwargs):
            raise AssertionError("latest must be rejected before SDK call")

    loader = CredentialLoader(secret_manager_client=Client(), expected_client_id="client-a")
    with pytest.raises(PermissionError):
        loader.load(
            secret_version="projects/p/secrets/s/versions/latest",
            subject="u",
            required_scopes=("scope",),
        )


def test_cloud_run_reconcile_reads_official_operation_name():
    class Operation:
        done = True
        error = None

    class Client:
        def get_operation(self, **kwargs):
            assert kwargs["request"]["name"] == "projects/p/locations/l/operations/o"
            return Operation()

    assert CloudRunDispatcher(job_name="job", client=Client()).reconcile(
        "projects/p/locations/l/operations/o"
    ) == "accepted"


def test_runtime_publisher_uses_digest_addressed_paths():
    class Ref:
        def __init__(self, path):
            self.path = path
        def create(self, data):
            self.created = data
        def set(self, data):
            self.set_data = data

    class Client:
        def __init__(self):
            self.refs = {}
        def document(self, path):
            self.refs[path] = Ref(path)
            return self.refs[path]

    from adk_harness.workflow.sync import make_result_envelope, make_runtime_manifest
    expires = datetime.now(UTC) + timedelta(minutes=5)
    changeset = ChangeSet(
        task_id="t", project_id="p", workspace_id="w", user_id="u", changes=(),
        policy_version="policy-1",
    )
    payload = {"kind": "changeset_result", "project_id": "p", "workspace_id": "w",
               "firebase_uid": "f", "google_subject": "u", "task_id": "t",
               "scope": ["calendar:c"], "expires_at": expires.isoformat(),
               "changeset": changeset.to_dict()}
    result = make_result_envelope(payload)
    manifest = make_runtime_manifest(project_id="p", workspace_id="w", firebase_uid="f",
                                     google_subject="u", task_id="t", scope=["calendar:c"],
                                     payload=payload, expires_at=expires)
    client = Client()
    RuntimeFirestorePublisher(client, project_id="p", workspace_id="w", firebase_uid="f").publish(
        task_id="t", result=result, manifest=manifest
    )
    assert any("results/" + result["result_id"] in path for path in client.refs)


@pytest.mark.asyncio
async def test_plan_request_persists_typed_proposal_without_host_call():
    req = request(intent="plan")
    store = InMemoryExecutionStore()
    changeset = ChangeSet(
        task_id=req.task_id,
        project_id=req.project_id,
        workspace_id=req.workspace_id,
        user_id=req.user_id,
        changes=(),
        resource_versions=req.resource_versions,
        policy_version=req.policy_version,
        trace_id=req.trace_id,
    )

    class Planner:
        async def plan(self, request):
            return changeset

    result = await Worker(
        config=WorkerConfig(policy_version="policy-1"), state=store, workspace=object(),
        action_checker=lambda *_: True,
        publisher=type("Publisher", (), {"publish": lambda self, **kwargs: None})(),
    ).run_plan(req, Planner(), firebase_uid="firebase-a")
    assert result.status == "completed"
    assert store.get(req.task_id).result["manifest"]["kind"] == "manifest"


@pytest.mark.asyncio
async def test_adk_planner_runs_runner_and_returns_typed_changeset():
    class Part:
        text = (
            '{"changes": [{"operation": "calendar_delete_event", '
            '"calendar_id": "cal-a", "event_id": "event-a", '
            '"etag": "etag-1"}]}'
        )

    class Event:
        content = type("Content", (), {"parts": [Part()]})()

    class Runner:
        def __init__(self, **kwargs):
            self.closed = False

        async def run_async(self, **kwargs):
            yield Event()

        def close(self):
            self.closed = True

    class Sessions:
        def create_session(self, **kwargs):
            return None

    app = type("WorkspaceApp", (), {"app": type("App", (), {"name": "workspace"})()})()
    changes = await ADKPlanner(app=app, session_service=Sessions(), runner_factory=Runner).plan(
        request(intent="plan")
    )
    assert changes.changes[0]["operation"] == "calendar_delete_event"


def test_apply_receiver_requires_parent_changeset_digests():
    req = request(intent="apply")
    changes = ChangeSet(
        task_id=req.task_id, project_id=req.project_id, workspace_id=req.workspace_id,
        user_id=req.user_id, changes=(), resource_versions=req.resource_versions,
        policy_version=req.policy_version, trace_id=req.trace_id,
    )
    trusted = {
        "request": req.to_dict(), "request_id": "request-a",
        "request_hash": req.content_hash,
        "changeset": changes.to_dict(),
        "approvals": [{"approval_type": "upload_run", **approval_for(req).to_dict()},
                      {"approval_type": "exact_apply",
                       **approval_for(req, changes.content_hash).to_dict()}],
    }
    receiver = EventarcReceiver(
        config=ReceiverConfig(project_id="project-a", database="control"),
        store=InMemoryExecutionStore(), dispatch=lambda _: None,
        provenance_verifier=lambda _: {
            "firebase_uid": "firebase-a", "google_subject": "google-user-a"
        },
        control_reader=lambda _: trusted,
    )
    held = receiver.handle({
        "type": "google.cloud.firestore.document.v1.created",
        "source": "//firestore.googleapis.com/projects/project-a/databases/control",
        "subject": EVENT_SUBJECT, "data": req.to_dict(),
    })
    assert held.status == "held"
    trusted["changeset_hash"] = changes.content_hash
    trusted["changeset_canonical"] = changes.canonical()
    assert receiver.handle({
        "type": "google.cloud.firestore.document.v1.created",
        "source": "//firestore.googleapis.com/projects/project-a/databases/control",
        "subject": EVENT_SUBJECT, "data": req.to_dict(),
    }).status == "claimed"


def test_worker_entry_assembles_real_runtime_dependencies_with_official_client_shapes():
    req = request(intent="plan")

    class Snapshot:
        exists = True
        def to_dict(self):
            return req.to_dict()

    class Ref:
        def get(self):
            return Snapshot()
        def collection(self, _name):
            return self
        def stream(self):
            return iter(())

    class FirestoreFake:
        def document(self, _path):
            return Ref()

    class Loader:
        def load(self, **_kwargs):
            return object()

    class Planner:
        async def plan(self, request):
            return ChangeSet(task_id=request.task_id, project_id=request.project_id,
                             workspace_id=request.workspace_id, user_id=request.user_id,
                             changes=(), resource_versions=request.resource_versions,
                             policy_version=request.policy_version, trace_id=request.trace_id)

    class Publisher:
        def publish(self, **_kwargs):
            return None

    env = {
        "ADK_PROJECT_ID": "project-a", "ADK_WORKSPACE_ID": "workspace-a",
        "ADK_FIREBASE_UID": "firebase-a", "ADK_GOOGLE_SUBJECT": "google-user-a",
        "ADK_TASK_ID": req.task_id, "ADK_CLIENT_ID": "client-a",
        "ADK_WORKSPACE_GRANT_SECRET_VERSION": "projects/p/secrets/s/versions/1",
        "ADK_POLICY_VERSION": "policy-1",
    }
    worker, _context = assemble_runtime_worker(
        env=env, control_client=FirestoreFake(), execution_client=object(),
        credential_loader=Loader(), workspace=object(), publisher=Publisher(),
        membership_verifier=lambda **_kwargs: True, planner=Planner(),
        state=InMemoryExecutionStore(),
    )
    assert isinstance(worker, Worker)
    assert worker_entry(
        dependencies={"env": env, "control_client": FirestoreFake(), "execution_client": object(),
                      "credential_loader": Loader(), "workspace": object(),
                      "publisher": Publisher(), "membership_verifier": lambda **_kwargs: True,
                      "planner": Planner(), "state": InMemoryExecutionStore()},
    )


def test_eventarc_provenance_comes_from_verified_auth_context_only():
    adapter = EventarcProvenanceAdapter(
        firebase_project_id="firebase-project",
        expected_delivery_authid="eventarc@example.iam.gserviceaccount.com",
        token_verifier=lambda token, audience: {
            "iss": f"https://securetoken.google.com/{audience}",
            "sub": "firebase-a",
            "firebase": {"identities": {"google.com": ["google-user-a"]}},
        } if token == "token" else {},
    )
    event = {
        "extensions": {
            "authtype": "service-account",
            "authid": "eventarc@example.iam.gserviceaccount.com",
        },
        "auth_context": {"firebase_id_token": "token"},
        "data": {"provenance": {"verified": True, "firebase_uid": "attacker"}},
    }
    assert adapter(event) == {"firebase_uid": "firebase-a", "google_subject": "google-user-a"}
    event.pop("auth_context")
    assert adapter(event) is None


def test_runtime_membership_requires_google_sub_active_native_unexpired_timestamp():
    req = request(intent="plan")

    class Snapshot:
        exists = True
        def to_dict(self):
            return req.to_dict()

    class Ref:
        def __init__(self, record=None):
            self.record = record
        def get(self):
            return Snapshot() if self.record is None else type("MemberSnapshot", (), {
                "exists": True, "to_dict": lambda _self: self.record
            })()
        def collection(self, _name):
            return self
        def stream(self):
            return iter(())

    member = {"google_sub": "google-user-a", "status": "active",
              "expires_at": datetime.now(UTC) + timedelta(minutes=5)}

    class Client:
        def document(self, path):
            return Ref(
                member
                if "/members/firebase-a" in path and "/requests/" not in path
                else None
            )

    env = {
        "ADK_PROJECT_ID": "project-a", "ADK_WORKSPACE_ID": "workspace-a",
        "ADK_FIREBASE_UID": "firebase-a", "ADK_GOOGLE_SUBJECT": "google-user-a",
        "ADK_TASK_ID": req.task_id, "ADK_CLIENT_ID": "client-a",
        "ADK_WORKSPACE_GRANT_SECRET_VERSION": "projects/p/secrets/s/versions/1",
        "ADK_POLICY_VERSION": "policy-1",
    }
    worker, _ = assemble_runtime_worker(
        env=env, control_client=Client(), runtime_client=object(),
        credential_loader=type("Loader", (), {"load": lambda *_args, **_kwargs: object()})(),
        workspace=object(), publisher=type("Publisher", (), {})(), state=InMemoryExecutionStore(),
    )
    assert worker.action_checker.membership_verifier(
        project_id="project-a", workspace_id="workspace-a", firebase_uid="firebase-a",
        google_subject="google-user-a", resource="cal-a", operation="calendar_create_event",
    ) is True
    member["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    assert worker.action_checker.membership_verifier(
        project_id="project-a", workspace_id="workspace-a", firebase_uid="firebase-a",
        google_subject="google-user-a", resource="cal-a", operation="calendar_create_event",
    ) is False


def test_runtime_assembly_binds_state_and_publisher_to_runtime_client():
    req = request(intent="plan")
    class Snapshot:
        exists = True
        def to_dict(self):
            return req.to_dict()
    class Ref:
        def get(self): return Snapshot()
        def collection(self, _name): return self
        def stream(self): return iter(())
    class Control:
        def document(self, _path): return Ref()
    runtime = object()
    env = {
        "ADK_PROJECT_ID": "project-a", "ADK_WORKSPACE_ID": "workspace-a",
        "ADK_FIREBASE_UID": "firebase-a", "ADK_GOOGLE_SUBJECT": "google-user-a",
        "ADK_TASK_ID": req.task_id, "ADK_CLIENT_ID": "client-a",
        "ADK_WORKSPACE_GRANT_SECRET_VERSION": "projects/p/secrets/s/versions/1",
        "ADK_POLICY_VERSION": "policy-1",
    }
    worker, _ = assemble_runtime_worker(
        env=env, control_client=Control(), runtime_client=runtime,
        credential_loader=type("Loader", (), {"load": lambda *_args, **_kwargs: object()})(),
        workspace=object(), membership_verifier=lambda **_kwargs: True,
    )
    assert worker.state.client is runtime
    assert worker.publisher.client is runtime


def test_the_receiver_accepts_the_event_type_the_trigger_sends() -> None:
    """The trigger asks for auth context, so the type carries that suffix."""
    from adk_harness.cloud.handler import CREATED_EVENT_TYPES

    assert "google.cloud.firestore.document.v1.created.withAuthContext" in CREATED_EVENT_TYPES

    receiver = EventarcReceiver(
        config=ReceiverConfig(
            project_id="project-a",
            database="control",
            path_prefix="projects/project-a/databases/control/documents/",
        ),
        store=InMemoryExecutionStore(),
        dispatch=lambda _: pytest.fail("an unverified event must not dispatch"),
        provenance_verifier=lambda _: None,
        control_reader=lambda _: {},
    )

    result = receiver.handle(
        {
            "type": "google.cloud.firestore.document.v1.created.withAuthContext",
            "source": "//firestore.googleapis.com/projects/project-a/databases/control",
            "subject": (
                "documents/projects/project-a/databases/control/documents/"
                "projects/project-a/workspaces/w/members/u/requests/r"
            ),
        }
    )

    # It gets past the type check and is judged on its merits, rather than
    # being dropped as an event this receiver does not handle.
    assert result.status != "ignored"


def test_an_unrelated_event_type_is_still_ignored() -> None:
    receiver = EventarcReceiver(
        config=ReceiverConfig(project_id="project-a", database="control"),
        store=InMemoryExecutionStore(),
        dispatch=lambda _: pytest.fail("a deletion must not dispatch"),
        provenance_verifier=lambda _: None,
        control_reader=lambda _: {},
    )

    result = receiver.handle({"type": "google.cloud.firestore.document.v1.deleted"})

    assert result.status == "ignored"


def test_the_control_reader_carries_the_request_hash_and_id(monkeypatch) -> None:
    """The receiver compares both, so a reader that drops them holds everything."""
    from adk_harness.cloud import handler

    stored = {
        "request": {"task_id": "t-1"},
        "request_hash": "h-1",
        "request_id": "r-1",
        "changeset": {"change_id": "c-1"},
        "changeset_hash": "ch-1",
        "changeset_canonical": "{}",
        "provenance": {"firebase_uid": "u-1"},
    }

    class _Snapshot:
        exists = True

        def to_dict(self):
            return stored

    class _Reference:
        def get(self):
            return _Snapshot()

        def collection(self, name):
            return _Empty()

    class _Empty:
        def stream(self):
            return []

    class _Client:
        def __init__(self, **kwargs):
            pass

        def document(self, path):
            return _Reference()

    monkeypatch.setenv("ADK_PROJECT_ID", "demo")
    monkeypatch.setenv("ADK_RUNTIME_DATABASE", "runtime")
    monkeypatch.setenv("ADK_FIREBASE_PROJECT_ID", "demo")
    monkeypatch.setattr("google.cloud.firestore.Client", _Client)

    receiver = handler._runtime_receiver()
    trusted = receiver.control_reader("//x/documents/projects/demo/requests/r-1")

    assert trusted["request_hash"] == "h-1"
    assert trusted["request_id"] == "r-1"
    assert trusted["request"] == {"task_id": "t-1"}


def test_provenance_can_come_from_the_eventarc_auth_context() -> None:
    """Nobody should have to stand up Firebase to run one governed task."""
    from adk_harness.cloud.handler import GooglePrincipalProvenanceAdapter

    adapter = GooglePrincipalProvenanceAdapter()

    provenance = adapter(
        {"extensions": {"authtype": "user", "authid": "112029692704988327139"}}
    )

    assert provenance == {
        "firebase_uid": "112029692704988327139",
        "google_subject": "112029692704988327139",
        "authtype": "user",
    }


def test_an_unauthenticated_write_has_no_provenance() -> None:
    from adk_harness.cloud.handler import GooglePrincipalProvenanceAdapter

    adapter = GooglePrincipalProvenanceAdapter()

    assert adapter({"extensions": {"authtype": "unauthenticated", "authid": "x"}}) is None
    assert adapter({"extensions": {"authtype": "user", "authid": ""}}) is None
    assert adapter({}) is None
