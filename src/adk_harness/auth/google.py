"""Official Google OAuth login and trusted local approval session helpers."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import urllib.parse
import webbrowser
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .credentials import CloudGrantChallenge, CredentialPurpose, SecureCredentialStore

__all__ = [
    "AuthStatus",
    "FirebaseIdentity",
    "GoogleAuthenticator",
    "IdentityVerificationError",
    "LocalApprovalBridge",
    "LocalApprovalSession",
    "LoginCancelled",
    "MissingScopesError",
    "verify_firebase_identity",
]

_LOGGER = logging.getLogger(__name__)
_SDK_LOGGER_NAMES = (
    "google_auth_oauthlib.flow",
    "requests_oauthlib.oauth2_session",
    "oauthlib.oauth2.rfc6749.clients.base",
)
_SDK_LOG_LOCK = threading.RLock()


@contextmanager
def _sdk_log_guard():
    """Temporarily suppress secret-bearing official SDK debug logs."""
    with _SDK_LOG_LOCK:
        loggers = [logging.getLogger(name) for name in _SDK_LOGGER_NAMES]
        state = [(logger.level, logger.disabled) for logger in loggers]
        for logger in loggers:
            logger.setLevel(logging.WARNING)
            logger.disabled = True
        try:
            yield
        finally:
            for logger, (level, disabled) in zip(loggers, state, strict=True):
                logger.setLevel(level)
                logger.disabled = disabled


class GoogleAuthError(RuntimeError):
    """Base class for user-safe authentication errors."""


class LoginCancelled(GoogleAuthError):
    """The human cancelled or timed out the OAuth flow."""


class IdentityVerificationError(GoogleAuthError):
    """The returned ID token did not establish the configured Google account."""


class MissingScopesError(GoogleAuthError):
    """Google returned a grant that omitted a required scope."""


@dataclass(frozen=True, slots=True)
class FirebaseIdentity:
    firebase_uid: str
    google_subject: str


def verify_firebase_identity(
    token: str,
    *,
    firebase_project_id: str,
    expected_google_subject: str,
    verifier: Callable[[str, str], dict[str, Any]] | None = None,
) -> FirebaseIdentity:
    """Verify a Firebase ID token and bind its Google provider subject.

    Firebase's official verifier checks signature, time, and audience.  The
    issuer/provider/identity checks below are application binding checks and
    deliberately keep Firebase UID distinct from the Google OAuth subject.
    """
    try:
        if verifier is None:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            claims = id_token.verify_firebase_token(
                token,
                Request(),
                audience=firebase_project_id,
            )
        else:
            claims = verifier(token, firebase_project_id)
        issuer = f"https://securetoken.google.com/{firebase_project_id}"
        if claims.get("iss") != issuer:
            raise IdentityVerificationError("Firebase issuer is invalid")
        uid = str(claims.get("sub", ""))
        auth_time = claims.get("auth_time")
        firebase = claims.get("firebase") or {}
        if not uid or not auth_time or firebase.get("sign_in_provider") != "google.com":
            raise IdentityVerificationError("Firebase token is not a Google user session")
        identities = firebase.get("identities") or {}
        google_subjects = {str(value) for value in identities.get("google.com", [])}
        if expected_google_subject not in google_subjects:
            raise IdentityVerificationError("Firebase and Google identities do not match")
        return FirebaseIdentity(firebase_uid=uid, google_subject=expected_google_subject)
    except IdentityVerificationError:
        raise
    except Exception:
        raise IdentityVerificationError("Firebase identity validation failed") from None


@dataclass(frozen=True, slots=True)
class AuthStatus:
    subject: str | None
    purpose: CredentialPurpose
    stored: bool
    authenticated: bool
    granted_scopes: tuple[str, ...] = ()
    reason: str | None = None


class GoogleAuthenticator:
    """Own one official OAuth client and a purpose-separated secure store."""

    def __init__(
        self,
        *,
        client_config: dict[str, Any],
        store: SecureCredentialStore,
        flow_factory: Callable[[dict[str, Any], list[str]], Any] | None = None,
        identity_verifier: Callable[[str, str], dict[str, Any]] | None = None,
        credential_factory: Callable[[str], Any] | None = None,
        refresh_request_factory: Callable[[], Any] | None = None,
        refresh_credentials: Callable[[Any, Any], None] | None = None,
    ) -> None:
        self.client_config = client_config
        self.store = store
        self._flow_factory = flow_factory or self._official_flow
        self._verify_identity = identity_verifier or self._official_identity_verifier
        self._credential_factory = credential_factory or self._official_credential_factory
        self._refresh_request_factory = refresh_request_factory or self._official_request
        self._refresh_credentials = refresh_credentials or self._default_refresh
        self.client_id = self._client_id(client_config)

    @staticmethod
    def _client_id(client_config: dict[str, Any]) -> str:
        for kind in ("installed", "web"):
            value = client_config.get(kind, {}).get("client_id")
            if value:
                return str(value)
        raise ValueError("OAuth client configuration has no client_id")

    @staticmethod
    def _official_flow(config: dict[str, Any], scopes: list[str]) -> Any:
        from google_auth_oauthlib.flow import InstalledAppFlow

        # InstalledAppFlow delegates state, PKCE, and token exchange to the SDK.
        return InstalledAppFlow.from_client_config(
            config,
            scopes,
            autogenerate_code_verifier=True,
        )

    @staticmethod
    def _official_identity_verifier(token: str, audience: str) -> dict[str, Any]:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(token, Request(), audience)
        if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
            raise IdentityVerificationError("Google ID token issuer is invalid")
        return dict(claims)

    @staticmethod
    def _official_credential_factory(payload: str) -> Any:
        import json

        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_info(json.loads(payload))

    @staticmethod
    def _official_request() -> Any:
        from google.auth.transport.requests import Request

        return Request()

    @staticmethod
    def _default_refresh(credentials: Any, request: Any) -> None:
        credentials.refresh(request)

    def login(
        self,
        purpose: CredentialPurpose,
        *,
        scopes: tuple[str, ...] | list[str],
        timeout_seconds: int = 300,
    ) -> AuthStatus:
        requested_set = {str(scope) for scope in scopes}
        requested_set.add("openid")
        requested = tuple(sorted(requested_set))
        if not requested:
            raise ValueError("login requires at least one purpose scope")
        flow = self._flow_factory(self.client_config, list(requested))
        try:
            with _sdk_log_guard():
                credentials = flow.run_local_server(
                    host="localhost",
                    bind_addr="127.0.0.1",
                    port=0,
                    timeout_seconds=timeout_seconds,
                    authorization_prompt_message=None,
                    open_browser=True,
                )
        except (KeyboardInterrupt, TimeoutError, OSError):
            raise LoginCancelled("Google login was cancelled or timed out") from None
        except Exception as exc:
            # SDK exceptions can include callback URLs or authorization
            # responses.  Do not retain or log their formatted traceback.
            if type(exc).__name__ == "WSGITimeoutError":
                raise LoginCancelled("Google login was cancelled or timed out") from None
            del exc
            raise GoogleAuthError("Google login failed") from None

        try:
            identity_token = getattr(credentials, "id_token", None)
            if not identity_token:
                raise IdentityVerificationError("Google login returned no ID token")
            claims = self._verify_identity(str(identity_token), self.client_id)
            subject = str(claims.get("sub", ""))
            if not subject:
                raise IdentityVerificationError("Google ID token has no subject")
            granted = self._observed_scopes(credentials)
            missing = set(requested) - set(granted)
            if missing:
                raise MissingScopesError("Google did not grant all requested scopes")
            credentials_json = credentials.to_json()
        except GoogleAuthError:
            raise
        except ValueError:
            raise IdentityVerificationError("Google identity validation failed") from None
        except Exception as exc:
            del exc
            raise IdentityVerificationError("Google identity validation failed") from None

        # Storage is reported separately: a keyring failure is not an identity
        # problem, and conflating them hides the real cause from the operator.
        try:
            self.store.save(
                subject=subject,
                purpose=purpose,
                credentials_json=credentials_json,
                granted_scopes=granted,
                id_token=str(identity_token),
            )
        except GoogleAuthError:
            raise
        except Exception as exc:
            detail = type(exc).__name__
            del exc
            raise GoogleAuthError(
                f"verified credentials could not be stored securely ({detail})"
            ) from None
        return AuthStatus(subject, purpose, True, True, granted)

    @staticmethod
    def _observed_scopes(credentials: Any) -> tuple[str, ...]:
        granted = getattr(credentials, "granted_scopes", None)
        if not granted:
            # ``scopes`` can mean requested scopes in google-auth and is not
            # evidence of what Google actually granted.
            raise MissingScopesError("Google response did not include observed granted scopes")
        return tuple(sorted({str(scope) for scope in granted}))

    def status(
        self,
        purpose: CredentialPurpose,
        *,
        subject: str | None = None,
    ) -> AuthStatus:
        if subject is None:
            subjects = self.store.subjects()
            if len(subjects) > 1:
                return AuthStatus(
                    None,
                    purpose,
                    False,
                    False,
                    reason="an explicit subject is required when multiple accounts exist",
                )
            subject = subjects[0] if subjects else None
        if not subject:
            return AuthStatus(None, purpose, False, False, reason="no stored credentials")
        record = self.store.load(subject, purpose)
        if record is None:
            return AuthStatus(subject, purpose, False, False, reason="no stored credentials")
        try:
            self.verified_credentials(purpose, subject=subject)
            return AuthStatus(subject, purpose, True, True, record.granted_scopes)
        except Exception:
            return AuthStatus(
                subject,
                purpose,
                True,
                False,
                record.granted_scopes,
                "authentication is expired or revoked",
            )

    def verified_credentials(
        self,
        purpose: CredentialPurpose,
        *,
        subject: str,
        required_scopes: tuple[str, ...] | list[str] = (),
    ) -> Any:
        """Return a currently verified official credential for trusted callers.

        This method intentionally returns a secret-bearing SDK object. Callers
        must keep it in process memory and must not serialize it into workflow
        records, model context, CLI output, or browser state.
        """
        record = self.store.load(subject, purpose)
        if record is None:
            raise IdentityVerificationError("stored purpose grant is missing")
        credentials = self._credential_factory(record.secret_payload["credentials_json"])
        was_expired = bool(getattr(credentials, "expired", False))
        if was_expired:
            with _sdk_log_guard():
                self._refresh_credentials(credentials, self._refresh_request_factory())
        if getattr(credentials, "valid", True) is False:
            raise IdentityVerificationError("current credentials are invalid")
        current_scopes = getattr(credentials, "granted_scopes", None)
        if current_scopes is not None:
            if not current_scopes:
                raise MissingScopesError("current credentials have no observed scopes")
            if not set(record.granted_scopes).issubset(set(current_scopes)):
                raise MissingScopesError("current credentials have fewer granted scopes")
            observed_scopes = tuple(sorted({str(scope) for scope in current_scopes}))
        else:
            # Standard google-auth JSON omits granted_scopes. The prior secure
            # envelope is the only acceptable observed evidence after reload.
            observed_scopes = record.granted_scopes
        requested = set(required_scopes)
        if requested and not requested.issubset(set(record.granted_scopes)):
            raise MissingScopesError("stored credentials do not carry required scopes")
        # A refreshed token must carry a fresh ID token. Never fall back to the
        # previously stored ID token after refresh, since it may be expired.
        token = getattr(credentials, "id_token", None)
        if not token and not was_expired:
            token = record.secret_payload.get("id_token")
        if not token:
            raise IdentityVerificationError("current authentication has no ID token")
        claims = self._verify_identity(str(token), self.client_id)
        if str(claims.get("sub", "")) != subject:
            raise IdentityVerificationError("stored and current Google identities differ")
        if was_expired:
            self.store.save(
                subject=subject,
                purpose=purpose,
                credentials_json=credentials.to_json(),
                granted_scopes=observed_scopes,
                id_token=str(token),
            )
        return credentials

    def logout(self, *, subject: str, purpose: CredentialPurpose) -> AuthStatus:
        deleted = self.store.delete(subject, purpose)
        return AuthStatus(subject, purpose, not deleted, False, reason="local credentials deleted")

    def upload_workspace_grant_to_secret_manager(
        self,
        *,
        subject: str,
        destination: str,
        scopes: tuple[str, ...] | list[str],
        consent: Any,
        secret_manager_client: Any | None = None,
    ) -> None:
        """Reverify both purpose grants, then delegate upload to official SDK."""
        self.verified_credentials(
            CredentialPurpose.WORKSPACE,
            subject=subject,
            required_scopes=scopes,
        )
        provisioning_credentials = self.verified_credentials(
            CredentialPurpose.PROVISIONING,
            subject=subject,
        )
        workspace_record = self.store.load(subject, CredentialPurpose.WORKSPACE)
        if workspace_record is None:
            raise IdentityVerificationError("purpose grant is missing")
        self.store.upload_cloud_workspace_grant(
            subject=subject,
            destination=destination,
            scopes=scopes,
            credentials_json=workspace_record.secret_payload["credentials_json"],
            consent=consent,
            secret_manager_client=secret_manager_client,
            provisioning_credentials=provisioning_credentials,
        )


class LocalApprovalSession:
    """Capability-bound loopback session for the trusted human UI."""

    def __init__(
        self,
        *,
        port: int,
        capability: str,
        expires_at: datetime | None = None,
        session_id: str | None = None,
    ) -> None:
        self.host = f"127.0.0.1:{port}"
        self.origin = f"http://{self.host}"
        self.capability = capability
        self.expires_at = expires_at or (datetime.now(UTC) + timedelta(minutes=30))
        # Nonsecret identifier used to bind workflow descriptors. This is
        # intentionally distinct from the URL capability secret.
        self.session_id = session_id or secrets.token_urlsafe(18)
        if not self.session_id or "/" in self.session_id:
            raise ValueError("session_id must be a non-empty path-safe value")
        self.url = f"{self.origin}/approval#capability={urllib.parse.quote(capability)}"

    @classmethod
    def create(cls) -> LocalApprovalSession:
        # Reserve an ephemeral loopback port without opening a public listener.
        server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = int(server.server_address[1])
        server.server_close()
        return cls(port=port, capability=secrets.token_urlsafe(32))

    def authorize(self, *, host: str, origin: str, capability: str) -> bool:
        return (
            datetime.now(UTC) < self.expires_at
            and secrets.compare_digest(host, self.host)
            and secrets.compare_digest(origin, self.origin)
            and secrets.compare_digest(capability, self.capability)
        )

    def expire(self) -> None:
        """Expire this local consent session and invalidate late callbacks."""
        self.expires_at = datetime.now(UTC) - timedelta(microseconds=1)

    def open(self) -> None:
        """Open the capability URL without writing it to model-visible output."""
        webbrowser.open(self.url, new=1, autoraise=True)


class LocalApprovalBridge:
    """Small local-only HTTP bridge for the trusted approval browser."""

    def __init__(
        self,
        *,
        session: LocalApprovalSession,
        ui_root: str | Path,
        bootstrap: Callable[[], dict[str, Any]],
        firebase_binding: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        cloud_grant_consent: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        setup_confirmation: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        cloud_grant_challenge: CloudGrantChallenge | None = None,
        workflow_preview: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        workflow_consent: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        workflow_ack: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        workflow_reconcile: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
        | None = None,
        workflow_recovery: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
        workflow_config: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.ui_root = Path(ui_root).resolve()
        self.bootstrap = bootstrap
        self.firebase_binding = firebase_binding
        self.cloud_grant_consent = cloud_grant_consent
        self.setup_confirmation = setup_confirmation
        self.cloud_grant_challenge = cloud_grant_challenge
        self.workflow_preview = workflow_preview
        self.workflow_consent = workflow_consent
        self.workflow_ack = workflow_ack
        self.workflow_reconcile = workflow_reconcile
        self.workflow_recovery = workflow_recovery
        self.workflow_config = dict(workflow_config) if workflow_config is not None else None
        self._consumed_challenges: set[str] = set()
        self._challenge_lock = threading.Lock()
        self._consumed_workflow_operations: set[str] = set()
        self._workflow_lock = threading.Lock()

    def _accept_cloud_challenge(self, body: dict[str, Any]) -> bool:
        challenge = self.cloud_grant_challenge
        if challenge is None or body.get("consent") is not True or not challenge.matches(body):
            return False
        with self._challenge_lock:
            if challenge.challenge in self._consumed_challenges:
                return False
            self._consumed_challenges.add(challenge.challenge)
        return True

    def authorize_request(self, *, host: str, origin: str, capability: str) -> bool:
        return self.session.authorize(host=host, origin=origin, capability=capability)

    def _authorized(self, handler: BaseHTTPRequestHandler, *, require_origin: bool) -> bool:
        host = handler.headers.get("Host", "")
        origin = handler.headers.get("Origin", "")
        capability = handler.headers.get("X-Session-Capability", "")
        if (require_origin and origin != self.session.origin) or (
            not require_origin and origin and origin != self.session.origin
        ):
            return False
        return self.authorize_request(
            host=host,
            origin=origin or self.session.origin,
            capability=capability,
        )

    def _workflow_identity(self, body: dict[str, Any]) -> dict[str, Any] | None:
        """Reverify the Firebase identity for every workflow callback.

        Only the ID token is passed to the injected trusted binder. Identity
        fields supplied by browser JSON are consequently never authority.
        """
        binder = self.firebase_binding
        token = body.get("firebaseIdToken")
        if binder is None or not isinstance(token, str) or not token:
            return None
        try:
            verified = binder({"firebaseIdToken": token})
        except Exception:
            return None
        if not isinstance(verified, dict):
            return None
        uid, subject = verified.get("firebaseUid"), verified.get("googleSubject")
        if not isinstance(uid, str) or not uid or not isinstance(subject, str) or not subject:
            return None
        return {"firebaseUid": uid, "googleSubject": subject}

    def _bootstrap(self) -> dict[str, Any]:
        value = self.bootstrap()
        if not isinstance(value, dict):
            raise ValueError("bootstrap must return a record")
        if self.workflow_config is None:
            return value
        config = dict(self.workflow_config)
        config.setdefault("session_id", self.session.session_id)
        config.setdefault("session_expires_at", self.session.expires_at.isoformat())
        # The config is nonsecret and is intended for later UI/CLI wiring.
        result = dict(value)
        result["workflowConfig"] = config
        # Let the UI discover optional durable recovery without probing an
        # endpoint that older hosts do not expose.
        result["workflowRecovery"] = self.workflow_recovery is not None
        return result

    @staticmethod
    def _workflow_body(body: Any) -> dict[str, Any] | None:
        if not isinstance(body, dict):
            return None
        if "approved" in body or "approved_true" in body:
            return None
        return body

    @staticmethod
    def _safe_workflow_result(value: dict[str, Any]) -> dict[str, Any] | None:
        """Reject accidental secret-bearing callback output at the bridge."""
        forbidden = ("token", "secret", "credential", "capability", "private_key")

        def check(item: Any) -> bool:
            if isinstance(item, dict):
                return all(
                    not any(word in key.lower() for word in forbidden) and check(child)
                    for key, child in item.items()
                    if isinstance(key, str)
                )
            if isinstance(item, (list, tuple)):
                return all(check(child) for child in item)
            return isinstance(item, (str, int, float, bool)) or item is None

        return value if check(value) else None

    def start(self) -> None:
        """Serve the UI on the exact loopback address in a daemon thread."""
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def _send_json(self, value: dict[str, Any], status: int = 200) -> None:
                encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self) -> None:
                if self.path == "/api/session":
                    if not bridge._authorized(self, require_origin=False):
                        self._send_json({"error": "forbidden"}, 403)
                        return
                    self._send_json(bridge._bootstrap())
                    return
                if self.path not in {"/approval", "/", "/dist/main.js"}:
                    self.send_error(404)
                    return
                if self.headers.get("Host", "") != bridge.session.host:
                    self.send_error(403)
                    return
                relative = "index.html" if self.path in {"/", "/approval"} else "dist/main.js"
                target = (bridge.ui_root / relative).resolve()
                if bridge.ui_root not in target.parents:
                    self.send_error(403)
                    return
                try:
                    data = target.read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                content_type = (
                    "text/html; charset=utf-8" if relative == "index.html" else "text/javascript"
                )
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: PLR0915
                if not bridge._authorized(self, require_origin=True):
                    self._send_json({"error": "forbidden"}, 403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 0 or length > 1_000_000:
                        raise ValueError("request exceeds local bound")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError("request must be an object")
                except (ValueError, json.JSONDecodeError):
                    self._send_json({"error": "invalid request"}, 400)
                    return
                callback = {
                    "/api/firebase-binding": bridge.firebase_binding,
                    "/api/cloud-grant-consent": bridge.cloud_grant_consent,
                    "/api/setup-confirmation": bridge.setup_confirmation,
                }.get(self.path)
                workflow_callback = {
                    "/api/workflow/preview": bridge.workflow_preview,
                    "/api/workflow/consent": bridge.workflow_consent,
                    "/api/workflow/ack": bridge.workflow_ack,
                    "/api/workflow/acknowledge": bridge.workflow_ack,
                    "/api/workflow/reconcile": bridge.workflow_reconcile,
                    "/api/workflow/recovery": bridge.workflow_recovery,
                }.get(self.path)
                if self.path.startswith("/api/workflow/"):
                    body = bridge._workflow_body(body)
                    if bridge.workflow_config is not None and (
                        not isinstance(body, dict)
                        or body.get("sessionId") != bridge.session.session_id
                    ):
                        self._send_json({"error": "workflow session rejected"}, 403)
                        return
                    if (
                        bridge.workflow_config is not None
                        and isinstance(body, dict)
                        and self.path == "/api/workflow/preview"
                    ):
                        config = bridge.workflow_config
                        expected_project = config.get("project_id", config.get("projectId"))
                        expected_workspace = config.get("workspace_id", config.get("workspaceId"))
                        candidates: list[tuple[Any, Any]] = []
                        request = body.get("request")
                        if isinstance(request, dict):
                            candidates.append(
                                (request.get("project_id"), request.get("workspace_id"))
                            )
                        candidates.append((body.get("projectId"), body.get("workspaceId")))
                        records = body.get("records")
                        if isinstance(records, list) and records and isinstance(records[0], dict):
                            candidates.append(
                                (records[0].get("project_id"), records[0].get("workspace_id"))
                            )
                        specified = [
                            item for item in candidates if any(value is not None for value in item)
                        ]
                        if not specified or any(
                            project != expected_project or workspace != expected_workspace
                            for project, workspace in specified
                        ):
                            self._send_json({"error": "workflow namespace rejected"}, 403)
                            return
                    identity = bridge._workflow_identity(body or {})
                    if workflow_callback is None or body is None or identity is None:
                        self._send_json({"error": "workflow request rejected"}, 403)
                        return
                    operation_id: str | None = None
                    if self.path in {
                        "/api/workflow/consent",
                        "/api/workflow/ack",
                        "/api/workflow/acknowledge",
                        "/api/workflow/reconcile",
                    }:
                        operation_id = body.get("operationId")
                        descriptor_hash = body.get("descriptorHash")
                        if (
                            not isinstance(operation_id, str)
                            or not operation_id
                            or not isinstance(descriptor_hash, str)
                            or not descriptor_hash
                            or (
                                self.path == "/api/workflow/consent"
                                and body.get("consent") is not True
                            )
                        ):
                            self._send_json({"error": "workflow descriptor rejected"}, 403)
                            return
                    if self.path in {"/api/workflow/ack", "/api/workflow/acknowledge"}:
                        allowed = {
                            "firebaseIdToken",
                            "operationId",
                            "descriptorHash",
                            "sessionId",
                            "ackId",
                            "status",
                            "contentHash",
                            "manifest",
                            "result",
                            "observed",
                        }
                        if any(key not in allowed for key in body):
                            self._send_json({"error": "acknowledgement fields rejected"}, 403)
                            return
                    if self.path == "/api/workflow/reconcile":
                        allowed = {
                            "firebaseIdToken",
                            "operationId",
                            "descriptorHash",
                            "sessionId",
                            "ackId",
                            "contentHash",
                            "observed",
                        }
                        if any(key not in allowed for key in body):
                            self._send_json({"error": "reconciliation fields rejected"}, 403)
                            return
                    if self.path == "/api/workflow/consent" and isinstance(operation_id, str):
                        with bridge._workflow_lock:
                            if operation_id in bridge._consumed_workflow_operations:
                                self._send_json(
                                    {"error": "workflow operation already consumed"}, 409
                                )
                                return
                    try:
                        result = workflow_callback(body, identity)
                        if not isinstance(result, dict):
                            raise ValueError("workflow callback must return a record")
                        result = bridge._safe_workflow_result(result)
                        if result is None:
                            raise ValueError("workflow callback returned restricted data")
                        if self.path == "/api/workflow/consent" and isinstance(operation_id, str):
                            with bridge._workflow_lock:
                                bridge._consumed_workflow_operations.add(operation_id)
                        self._send_json(result)
                    except Exception:
                        if self.path == "/api/workflow/consent" and isinstance(operation_id, str):
                            with bridge._workflow_lock:
                                bridge._consumed_workflow_operations.discard(operation_id)
                        self._send_json({"error": "workflow request rejected"}, 403)
                    return
                if callback is None:
                    self._send_json({"error": "not found"}, 404)
                    return
                if self.path == "/api/cloud-grant-consent" and not bridge._accept_cloud_challenge(
                    body
                ):
                    self._send_json({"error": "consent challenge rejected"}, 403)
                    return
                try:
                    self._send_json(callback(body))
                except Exception:
                    self._send_json({"error": "request rejected"}, 403)

        server = ThreadingHTTPServer(
            ("127.0.0.1", int(self.session.host.rsplit(":", 1)[1])), Handler
        )
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        server = getattr(self, "_server", None)
        if server is not None:
            server.shutdown()
            server.server_close()
