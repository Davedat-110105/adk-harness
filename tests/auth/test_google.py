from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from adk_harness.auth.credentials import (
    CloudGrantChallenge,
    CredentialPurpose,
    SecureCredentialStore,
    WorkspaceGrantConsent,
)
from adk_harness.auth.google import (
    FirebaseIdentity,
    GoogleAuthenticator,
    IdentityVerificationError,
    LocalApprovalBridge,
    LocalApprovalSession,
    LoginCancelled,
    MissingScopesError,
    _sdk_log_guard,
    verify_firebase_identity,
)
from adk_harness.workflow.models import ActivityEvent
from adk_harness.workflow.outbox import OperationState, Outbox
from adk_harness.workflow.sync import SyncEngine, WorkflowConfig


class FakeKeyring:
    priority = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.values[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_store_rejects_insecure_backend_without_plaintext_fallback() -> None:
    class NoKeyring:
        priority = 0

    with pytest.raises(RuntimeError, match="secure credential backend"):
        module = type("K", (), {"get_keyring": lambda _: NoKeyring()})()
        SecureCredentialStore(keyring_module=module)


def test_store_separates_provisioning_and_workspace_grants() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.PROVISIONING,
        credentials_json='{"token":"secret-provisioning"}',
        granted_scopes=("scope:provisioning",),
        id_token="id-token-provisioning",
    )
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.WORKSPACE,
        credentials_json='{"token":"secret-workspace"}',
        granted_scopes=("scope:workspace",),
        id_token="id-token-workspace",
    )

    provisioning = store.load("google-sub-1", CredentialPurpose.PROVISIONING)
    workspace = store.load("google-sub-1", CredentialPurpose.WORKSPACE)
    assert provisioning is not None and workspace is not None
    assert provisioning.granted_scopes == ("scope:provisioning",)
    assert workspace.granted_scopes == ("scope:workspace",)
    assert provisioning.secret_payload != workspace.secret_payload
    assert "secret-provisioning" not in repr(provisioning)
    assert "secret-workspace" not in repr(workspace)


def test_cloud_workspace_grant_requires_immutable_explicit_consent() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    with pytest.raises(PermissionError, match="explicit human consent"):
        store.save_cloud_workspace_grant(
            subject="google-sub-1",
            destination="projects/example/secrets/workspace-grant",
            scopes=("scope:workspace",),
            credentials_json='{"token":"secret"}',
            consent=None,
        )

    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.WORKSPACE,
        credentials_json='{"token":"secret"}',
        granted_scopes=("scope:workspace",),
        id_token="id-token-workspace",
    )

    consent = WorkspaceGrantConsent.create(
        subject="google-sub-1",
        destination="projects/example/secrets/workspace-grant",
        scopes=("scope:workspace",),
    )
    store.save_cloud_workspace_grant(
        subject="google-sub-1",
        destination="projects/example/secrets/workspace-grant",
        scopes=("scope:workspace",),
        credentials_json='{"token":"secret"}',
        consent=consent,
    )
    assert keyring.values


def test_secret_manager_upload_is_after_matching_consent_only() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.WORKSPACE,
        credentials_json='{"token":"secret"}',
        granted_scopes=("scope:workspace",),
        id_token="id-token-workspace",
    )

    class FakeSecretManager:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def add_secret_version(self, *, request: dict[str, object]) -> None:
            self.requests.append(request)

    client = FakeSecretManager()
    with pytest.raises(PermissionError):
        store.upload_cloud_workspace_grant(
            subject="google-sub-1",
            destination="projects/example/secrets/workspace-grant",
            scopes=("scope:workspace",),
            credentials_json='{"token":"secret"}',
            consent=None,
            secret_manager_client=client,
        )
    assert client.requests == []
    consent = WorkspaceGrantConsent.create(
        subject="google-sub-1",
        destination="projects/example/secrets/workspace-grant",
        scopes=("scope:workspace",),
    )
    store.upload_cloud_workspace_grant(
        subject="google-sub-1",
        destination="projects/example/secrets/workspace-grant",
        scopes=("scope:workspace",),
        credentials_json='{"token":"secret"}',
        consent=consent,
        secret_manager_client=client,
    )
    assert client.requests[0]["parent"] == "projects/example/secrets/workspace-grant"


@dataclass
class FakeCredentials:
    id_token: str | None = "id-token"
    granted_scopes: tuple[str, ...] | None = ("openid", "scope:provisioning")
    valid: bool = True
    expired: bool = False

    def to_json(self) -> str:
        return json.dumps({"token": "access-secret", "refresh_token": "refresh-secret"})

    def refresh(self, request: object) -> None:
        self.valid = True
        self.expired = False


class FakeFlow:
    def __init__(
        self,
        credentials: FakeCredentials | None = None,
        error: Exception | None = None,
    ) -> None:
        self.credentials = credentials or FakeCredentials()
        self.error = error
        self.kwargs: dict[str, object] = {}

    def run_local_server(self, **kwargs: object) -> FakeCredentials:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.credentials


def test_login_uses_local_pkce_and_stores_verified_subject_without_printing_secrets(
    capsys: pytest.CaptureFixture[str],
) -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    flow = FakeFlow()
    requested_scopes: list[str] = []
    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        flow_factory=lambda config, scopes: requested_scopes.extend(scopes) or flow,
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
    )

    status = auth.login(CredentialPurpose.PROVISIONING, scopes=("scope:provisioning",))

    assert status.subject == "google-sub-1"
    assert status.purpose is CredentialPurpose.PROVISIONING
    assert flow.kwargs["bind_addr"] == "127.0.0.1"
    assert flow.kwargs["host"] == "localhost"
    assert flow.kwargs["authorization_prompt_message"] is None
    assert "autogenerate_code_verifier" not in flow.kwargs
    assert "openid" in requested_scopes
    captured = capsys.readouterr()
    assert "access-secret" not in captured.out + captured.err
    assert "refresh-secret" not in captured.out + captured.err


def test_login_cancellation_does_not_store_credentials() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        flow_factory=lambda config, scopes: FakeFlow(error=KeyboardInterrupt()),
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
    )

    with pytest.raises(LoginCancelled):
        auth.login(CredentialPurpose.PROVISIONING, scopes=("scope:provisioning",))
    assert not keyring.values


def test_login_rejects_missing_granted_scope_and_identity_failure() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        flow_factory=lambda config, scopes: FakeFlow(FakeCredentials(granted_scopes=("other",))),
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
    )
    with pytest.raises(MissingScopesError):
        auth.login(CredentialPurpose.PROVISIONING, scopes=("scope:provisioning",))
    assert not keyring.values

    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        flow_factory=lambda config, scopes: FakeFlow(),
        identity_verifier=lambda token, audience: (_ for _ in ()).throw(
            ValueError("sentinel-secret")
        ),
    )
    with pytest.raises(IdentityVerificationError):
        auth.login(CredentialPurpose.PROVISIONING, scopes=("scope:provisioning",))
    assert not keyring.values


def test_status_marks_expired_or_revoked_credentials_unverified() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.PROVISIONING,
        credentials_json=(
            '{"token":"access-secret", "refresh_token":"refresh-secret", '
            '"client_id":"client-id", "token_uri":"https://oauth2.googleapis.com/token"}'
        ),
        granted_scopes=("scope:provisioning",),
        id_token="id-token",
    )
    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
        credential_factory=lambda payload: FakeCredentials(expired=True),
        refresh_request_factory=object,
    )
    status = auth.status(CredentialPurpose.PROVISIONING, subject="google-sub-1")
    assert status.stored is True
    assert status.authenticated is True

    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
        credential_factory=lambda payload: FakeCredentials(expired=True),
        refresh_request_factory=object,
        # Refresh failure is the revoked-token path.
        refresh_credentials=lambda credentials, request: (_ for _ in ()).throw(
            RuntimeError("refresh-secret")
        ),
    )
    status = auth.status(CredentialPurpose.PROVISIONING, subject="google-sub-1")
    assert status.stored is True
    assert status.authenticated is False


def test_empty_current_scopes_fail_closed_after_sdk_reload() -> None:
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.PROVISIONING,
        credentials_json='{"token":"access-secret"}',
        granted_scopes=("scope:provisioning",),
        id_token="id-token",
    )
    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
        credential_factory=lambda payload: FakeCredentials(granted_scopes=()),
    )
    assert (
        auth.status(CredentialPurpose.PROVISIONING, subject="google-sub-1").authenticated is False
    )


def test_public_google_credentials_reload_refresh_and_persist_new_verified_json() -> None:
    from google.oauth2.credentials import Credentials

    initial = Credentials(
        token="old-access",
        refresh_token="refresh-secret",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=("scope:provisioning",),
    ).to_json()
    payload = json.loads(initial)
    payload["expiry"] = "2000-01-01T00:00:00Z"
    keyring = FakeKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.PROVISIONING,
        credentials_json=json.dumps(payload),
        granted_scopes=("scope:provisioning",),
        id_token="old-id-token",
    )

    class RefreshRequest:
        def __call__(self, **kwargs: object) -> object:
            return SimpleNamespace(
                status=200,
                data=json.dumps(
                    {
                        "access_token": "new-access",
                        "expires_in": 3600,
                        "id_token": "new-id-token",
                        "scope": "scope:provisioning",
                        "token_type": "Bearer",
                    }
                ).encode(),
            )

    auth = GoogleAuthenticator(
        client_config={"installed": {"client_id": "client-id"}},
        store=store,
        identity_verifier=lambda token, audience: {"sub": "google-sub-1", "aud": audience},
        credential_factory=lambda value: Credentials.from_authorized_user_info(json.loads(value)),
        refresh_request_factory=RefreshRequest,
    )
    credentials = auth.verified_credentials(
        CredentialPurpose.PROVISIONING,
        subject="google-sub-1",
        required_scopes=("scope:provisioning",),
    )
    assert credentials.token == "new-access"
    refreshed = store.load("google-sub-1", CredentialPurpose.PROVISIONING)
    assert refreshed is not None
    assert "new-access" in refreshed.secret_payload["credentials_json"]
    assert refreshed.secret_payload["id_token"] == "new-id-token"


def test_sdk_log_guard_suppresses_token_messages_and_restores_logger_state() -> None:
    logger = logging.getLogger("requests_oauthlib.oauth2_session")
    prior_level, prior_disabled = logger.level, logger.disabled
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with _sdk_log_guard():
            logger.debug("access-secret refresh-secret")
        logger.debug("outside-message")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)
        logger.disabled = prior_disabled
    assert records == ["outside-message"]


def test_real_oauth2_session_exchange_and_refresh_debug_logs_are_suppressed() -> None:
    from oauthlib.oauth2 import WebApplicationClient
    from requests_oauthlib import OAuth2Session

    response = SimpleNamespace(
        status_code=200,
        headers={"X-Test": "refresh-secret"},
        text='{"access_token":"access-secret","refresh_token":"refresh-secret","token_type":"Bearer"}',
        request=SimpleNamespace(
            url="https://oauth2.example/token",
            headers={"Authorization": "refresh-secret"},
            body="refresh_secret=refresh-secret",
        ),
    )
    session = OAuth2Session(
        client_id="client-id",
        client=WebApplicationClient("client-id"),
    )
    session.redirect_uri = "https://localhost/callback"
    session.request = lambda **kwargs: response
    session.post = lambda *args, **kwargs: response
    logger = logging.getLogger("requests_oauthlib.oauth2_session")
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    prior_level, prior_disabled = logger.level, logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with _sdk_log_guard():
            session.fetch_token(
                "https://oauth2.example/token",
                code="authorization-code",
                client_secret="client-secret",
            )
            session.refresh_token("https://oauth2.example/token", refresh_token="refresh-secret")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)
        logger.disabled = prior_disabled
    assert all("secret" not in message for message in records)


def test_local_approval_session_requires_exact_loopback_origin_and_capability() -> None:
    session = LocalApprovalSession.create()
    assert session.url.startswith("http://127.0.0.1:")
    assert "capability=" in session.url
    capability = session.capability
    assert session.authorize(host=session.host, origin=session.origin, capability=capability)
    assert not session.authorize(host="localhost", origin=session.origin, capability=capability)
    assert not session.authorize(
        host=session.host,
        origin="http://evil.example",
        capability=capability,
    )
    assert not session.authorize(host=session.host, origin=session.origin, capability="wrong")


def test_firebase_binding_requires_verified_issuer_provider_uid_and_google_subject() -> None:
    claims = {
        "iss": "https://securetoken.google.com/example",
        "sub": "firebase-uid-1",
        "auth_time": 100,
        "firebase": {
            "sign_in_provider": "google.com",
            "identities": {"google.com": ["google-sub-1"]},
        },
    }
    identity = verify_firebase_identity(
        "firebase-token",
        firebase_project_id="example",
        expected_google_subject="google-sub-1",
        verifier=lambda token, audience: claims,
    )
    assert identity == FirebaseIdentity(
        firebase_uid="firebase-uid-1", google_subject="google-sub-1"
    )
    with pytest.raises(IdentityVerificationError):
        verify_firebase_identity(
            "firebase-token",
            firebase_project_id="example",
            expected_google_subject="different-sub",
            verifier=lambda token, audience: claims,
        )


def test_local_bridge_rejects_wrong_host_or_capability_before_callbacks() -> None:
    session = LocalApprovalSession.create()
    seen: list[dict[str, object]] = []
    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {"googleSubject": "google-sub-1", "firebaseConfig": {}},
        firebase_binding=lambda body: (
            seen.append(body) or {"firebaseUid": "uid", "googleSubject": "google-sub-1"}
        ),
    )
    assert not bridge.authorize_request(
        host="localhost",
        origin=session.origin,
        capability=session.capability,
    )
    assert bridge.authorize_request(
        host=session.host,
        origin=session.origin,
        capability=session.capability,
    )
    assert seen == []


def test_local_bridge_http_boundary_gates_bootstrap_and_binding() -> None:
    session = LocalApprovalSession.create()
    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {"googleSubject": "google-sub-1", "firebaseConfig": {}},
        firebase_binding=lambda body: {"firebaseUid": "uid", "googleSubject": "google-sub-1"},
    )
    bridge.start()
    try:
        url = f"{session.origin}/api/session"
        request = urllib.request.Request(
            url,
            headers={"Host": session.host, "X-Session-Capability": session.capability},
        )
        assert (
            json.loads(urllib.request.urlopen(request, timeout=2).read())["googleSubject"]
            == "google-sub-1"
        )
        wrong = urllib.request.Request(
            url,
            headers={"Host": session.host, "X-Session-Capability": "wrong"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(wrong, timeout=2)
        assert error.value.code == 403
        post = urllib.request.Request(
            f"{session.origin}/api/firebase-binding",
            method="POST",
            data=b'{"firebaseIdToken":"opaque"}',
            headers={
                "Host": session.host,
                "Origin": session.origin,
                "X-Session-Capability": session.capability,
                "Content-Type": "application/json",
            },
        )
        assert json.loads(urllib.request.urlopen(post, timeout=2).read())["firebaseUid"] == "uid"
        page = urllib.request.urlopen(
            urllib.request.Request(f"{session.origin}/approval", headers={"Host": session.host}),
            timeout=2,
        ).read()
        bundle_request = urllib.request.Request(
            f"{session.origin}/dist/main.js",
            headers={"Host": session.host},
        )
        bundle = urllib.request.urlopen(bundle_request, timeout=2).read()
        assert b"Trusted setup confirmation" in page
        assert len(bundle) > 1000
    finally:
        bridge.stop()


def test_cloud_challenge_rejects_missing_changed_and_replayed_consent() -> None:
    challenge = CloudGrantChallenge.issue(
        subject="google-sub-1",
        destination="projects/p/secrets/s",
        scopes=("openid", "scope:workspace"),
    )
    base = {
        "challenge": challenge.challenge,
        "googleSubject": challenge.subject,
        "purpose": "workspace",
        "destination": challenge.destination,
        "scopes": list(challenge.scopes),
    }
    assert not challenge.matches({**base, "consent": True}, now=challenge.expires_at)
    assert challenge.matches({**base, "consent": True})


def test_cloud_challenge_bridge_consumes_once_before_cloud_callback() -> None:
    session = LocalApprovalSession.create()
    challenge = CloudGrantChallenge.issue(
        subject="google-sub-1",
        destination="projects/p/secrets/s",
        scopes=("openid", "scope:workspace"),
    )
    calls: list[dict[str, object]] = []
    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {},
        cloud_grant_challenge=challenge,
        cloud_grant_consent=lambda body: calls.append(body) or {"status": "stored"},
    )
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    valid = {
        "firebaseIdToken": "opaque",
        "consent": True,
        "googleSubject": challenge.subject,
        "purpose": challenge.purpose.value,
        "destination": challenge.destination,
        "scopes": list(challenge.scopes),
        "challenge": challenge.challenge,
    }
    try:
        absent = dict(valid)
        absent.pop("consent")
        request = urllib.request.Request(
            f"{session.origin}/api/cloud-grant-consent",
            method="POST",
            data=json.dumps(absent).encode(),
            headers=headers,
        )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(request, timeout=2)
        assert calls == []
        changed = {**valid, "destination": "projects/other/secrets/s"}
        request = urllib.request.Request(
            f"{session.origin}/api/cloud-grant-consent",
            method="POST",
            data=json.dumps(changed).encode(),
            headers=headers,
        )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(request, timeout=2)
        assert calls == []
        request = urllib.request.Request(
            f"{session.origin}/api/cloud-grant-consent",
            method="POST",
            data=json.dumps(valid).encode(),
            headers=headers,
        )
        assert json.loads(urllib.request.urlopen(request, timeout=2).read())["status"] == "stored"
        assert len(calls) == 1
        request = urllib.request.Request(
            f"{session.origin}/api/cloud-grant-consent",
            method="POST",
            data=json.dumps(valid).encode(),
            headers=headers,
        )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(request, timeout=2)
        assert len(calls) == 1
    finally:
        bridge.stop()


def test_local_bridge_workflow_reverifies_identity_and_consumes_consent_once() -> None:
    session = LocalApprovalSession.create()
    seen: list[tuple[dict[str, object], dict[str, object]]] = []
    bound: list[dict[str, object]] = []

    def binder(body: dict[str, object]) -> dict[str, object]:
        bound.append(body)
        return {"firebaseUid": "firebase-1", "googleSubject": "google-sub-1"}

    def consent(body: dict[str, object], identity: dict[str, object]) -> dict[str, object]:
        seen.append((body, identity))
        return {"operationId": body["operationId"], "status": "instruction_ready"}

    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {},
        firebase_binding=binder,
        workflow_consent=consent,
    )
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    payload = {
        "firebaseIdToken": "opaque",
        "operationId": "operation-1",
        "descriptorHash": "a" * 64,
        "consent": True,
        "googleSubject": "attacker-controlled",
    }
    try:
        request = urllib.request.Request(
            f"{session.origin}/api/workflow/consent",
            method="POST",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        response = json.loads(urllib.request.urlopen(request, timeout=2).read())
        assert response["status"] == "instruction_ready"
        assert bound == [{"firebaseIdToken": "opaque"}]
        assert seen[0][1] == {"firebaseUid": "firebase-1", "googleSubject": "google-sub-1"}
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)
        assert error.value.code == 409
    finally:
        bridge.stop()


def test_local_approval_session_expiry_rejects_late_requests() -> None:
    session = LocalApprovalSession.create()
    assert session.authorize(
        host=session.host, origin=session.origin, capability=session.capability
    )
    session.expire()
    assert not session.authorize(
        host=session.host, origin=session.origin, capability=session.capability
    )


def test_local_bridge_real_preview_consent_instruction_ack_flow_mints_approval(tmp_path) -> None:
    session = LocalApprovalSession.create()
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    config = WorkflowConfig(
        project_id="project-1",
        workspace_id="workspace-1",
        control_database_id="control-db",
        runtime_database_id="runtime-db",
        session_id=session.session_id,
        session_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    engine = SyncEngine(outbox, workflow_config=config)
    event = ActivityEvent(
        task_id="task-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_type="local.edit",
        actor_id="cloud-runtime-actor",
        details={"file": "README.md"},
        event_id="event-1",
        occurred_at=datetime(2030, 1, 1, 0, 0, 0, 123456, tzinfo=UTC),
    )

    def binder(body: dict[str, object]) -> dict[str, object]:
        assert body == {"firebaseIdToken": "opaque"}
        return {"firebaseUid": "firebase-1", "googleSubject": "google-sub-1"}

    bridge = LocalApprovalBridge(
        session=session,
        ui_root="ui/approval",
        bootstrap=lambda: {},
        firebase_binding=binder,
        workflow_config={
            "project_id": config.project_id,
            "workspace_id": config.workspace_id,
            "control_database_id": config.control_database_id,
            "runtime_database_id": config.runtime_database_id,
            "session_id": config.session_id,
            "session_expires_at": config.session_expires_at.isoformat(),
        },
        **engine.bridge_callbacks(),
    )
    bridge.start()
    headers = {
        "Host": session.host,
        "Origin": session.origin,
        "X-Session-Capability": session.capability,
        "Content-Type": "application/json",
    }
    base = {
        "firebaseIdToken": "opaque",
        "kind": "history_upload",
        "records": [event.to_dict()],
        "sessionId": session.session_id,
    }

    def post(path: str, body: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{session.origin}{path}",
            method="POST",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        return json.loads(urllib.request.urlopen(request, timeout=2).read())

    try:
        preview = post("/api/workflow/preview", base)
        assert preview["transfer"] == {"sdk_calls": 0, "documents": 0, "bytes": 0}
        consent = post(
            "/api/workflow/consent",
            {
                "firebaseIdToken": "opaque",
                "operationId": preview["operation_id"],
                "descriptorHash": preview["descriptor_hash"],
                "consent": True,
                "sessionId": session.session_id,
            },
        )
        instruction = consent["instruction"]
        assert instruction["sdk"] == "firebase/firestore/lite"
        ack = post(
            "/api/workflow/ack",
            {
                "firebaseIdToken": "opaque",
                "operationId": consent["operation_id"],
                "descriptorHash": consent["descriptor_hash"],
                "ackId": "firebase-commit-1",
                "sessionId": session.session_id,
            },
        )
        assert ack["status"] == "acknowledged"
        assert outbox.get_instruction(consent["operation_id"]).state is OperationState.ACKNOWLEDGED
    finally:
        bridge.stop()
        outbox.close()


class BlobLimitedKeyring(FakeKeyring):
    """Reject an oversized blob the way Windows Credential Manager does."""

    LIMIT = 1280

    def set_password(self, service: str, username: str, value: str) -> None:
        if len(value) > self.LIMIT:
            raise OSError(1783, "CredWrite", "The stub received bad data")
        super().set_password(service, username, value)


def test_store_round_trips_an_envelope_larger_than_one_backend_entry() -> None:
    keyring = BlobLimitedKeyring()
    store = SecureCredentialStore(keyring_module=keyring)
    credentials_json = json.dumps({"token": "y" * 1200, "id_token": "j" * 1300})

    store.save(
        subject="google-sub-1",
        purpose=CredentialPurpose.PROVISIONING,
        credentials_json=credentials_json,
        granted_scopes=("openid",),
        id_token="j" * 1300,
    )

    record = store.load("google-sub-1", CredentialPurpose.PROVISIONING)
    assert record is not None
    assert record.secret_payload["credentials_json"] == credentials_json
    assert store.delete("google-sub-1", CredentialPurpose.PROVISIONING)
    assert store.load("google-sub-1", CredentialPurpose.PROVISIONING) is None
    # Deleting must leave no split part behind.
    assert not [key for key in keyring.values if "#part" in key[1]]
