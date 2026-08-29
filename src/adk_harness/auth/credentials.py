"""Secure storage for verified, purpose-separated Google grants.

The application never falls back to a file, environment variable, or SQLite
record for credentials.  The keyring implementation must provide an actual
secure backend supplied by the operating system.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class CredentialPurpose(StrEnum):
    """The authority represented by one stored grant."""

    PROVISIONING = "provisioning"
    WORKSPACE = "workspace"


@dataclass(frozen=True, slots=True)
class StoredCredential:
    """Metadata plus private credential payload loaded from the OS keyring."""

    subject: str
    purpose: CredentialPurpose
    granted_scopes: tuple[str, ...]
    secret_payload: dict[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class WorkspaceGrantConsent:
    """Immutable human consent binding for a cloud Workspace grant.

    ``create`` is intended to be called by the trusted browser bridge after a
    human confirmation.  A model or CLI argument must never construct a cloud
    grant write directly.
    """

    subject: str
    destination: str
    scopes: tuple[str, ...]
    binding: str
    confirmed: bool = field(repr=False, default=True)

    @classmethod
    def create(
        cls, *, subject: str, destination: str, scopes: tuple[str, ...] | list[str]
    ) -> WorkspaceGrantConsent:
        normalized = tuple(sorted(set(scopes)))
        if not subject or not destination or not normalized:
            raise ValueError("consent binding requires subject, destination, and scopes")
        payload = json.dumps(
            {"destination": destination, "scopes": normalized, "subject": subject},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return cls(
            subject=subject,
            destination=destination,
            scopes=normalized,
            binding=hashlib.sha256(payload).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class CloudGrantChallenge:
    """Single-session binding displayed before a cloud grant consent."""

    challenge: str
    subject: str
    purpose: CredentialPurpose
    destination: str
    scopes: tuple[str, ...]
    expires_at: datetime

    @classmethod
    def issue(
        cls,
        *,
        subject: str,
        destination: str,
        scopes: tuple[str, ...] | list[str],
        lifetime_seconds: int = 300,
    ) -> CloudGrantChallenge:
        normalized = tuple(sorted(set(scopes)))
        if not subject or not destination or not normalized:
            raise ValueError("cloud grant challenge requires complete binding")
        return cls(
            challenge=secrets.token_urlsafe(32),
            subject=subject,
            purpose=CredentialPurpose.WORKSPACE,
            destination=destination,
            scopes=normalized,
            expires_at=datetime.now(UTC) + timedelta(seconds=lifetime_seconds),
        )

    def matches(self, payload: dict[str, Any], *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return (
            current < self.expires_at
            and payload.get("challenge") == self.challenge
            and payload.get("googleSubject") == self.subject
            and payload.get("purpose") == self.purpose.value
            and payload.get("destination") == self.destination
            and tuple(payload.get("scopes", ())) == self.scopes
        )


class SecureCredentialStore:
    """Fail-closed OS keyring store for OAuth envelopes."""

    SERVICE = "adk-harness.google"
    INDEX_USER = "__subjects__"
    # Windows Credential Manager rejects a blob over 2560 bytes, which one
    # OAuth envelope exceeds.  Split the payload across entries instead.
    CHUNK_CHARS = 1000
    MAX_CHUNKS = 64

    def __init__(self, *, keyring_module: Any | None = None) -> None:
        injected = keyring_module is not None
        if keyring_module is None:
            import keyring as keyring_module
        self._keyring = keyring_module
        self._backend = self._resolve_backend(keyring_module)
        self._ensure_secure_backend(self._backend, strict=not injected)

    @staticmethod
    def _resolve_backend(module: Any) -> Any:
        getter = getattr(module, "get_keyring", None)
        return getter() if callable(getter) else module

    @staticmethod
    def _ensure_secure_backend(backend: Any, *, strict: bool) -> None:
        priority = getattr(backend, "priority", 0)
        module_name = type(backend).__module__
        if not isinstance(priority, (int, float)) or priority <= 0:
            raise RuntimeError("secure credential backend is unavailable")
        if module_name.startswith("keyring.backends.fail"):
            raise RuntimeError("secure credential backend is unavailable")
        if strict and not any(
            module_name.startswith(prefix)
            for prefix in (
                "keyring.backends.Windows",
                "keyring.backends.macOS",
                "keyring.backends.SecretService",
                "keyring.backends.kwallet",
                "keyring.backends.libsecret",
            )
        ):
            raise RuntimeError("secure OS credential backend is unavailable")

    @classmethod
    def _username(cls, subject: str, purpose: CredentialPurpose) -> str:
        if not subject or any(char.isspace() for char in subject):
            raise ValueError("credential subject must be a non-empty verified identifier")
        return f"{subject}:{purpose.value}"

    @classmethod
    def _part_name(cls, username: str, index: int) -> str:
        return f"{username}#part{index}"

    def _write_chunked(self, username: str, payload: str) -> None:
        """Write the payload, splitting it when a backend cannot hold it whole."""
        chunks = [
            payload[start : start + self.CHUNK_CHARS]
            for start in range(0, len(payload), self.CHUNK_CHARS)
        ] or [""]
        if len(chunks) > self.MAX_CHUNKS:
            raise ValueError("credential envelope is too large to store")
        if len(chunks) == 1:
            self._keyring.set_password(self.SERVICE, username, payload)
        else:
            # Parts are written before the header so an interrupted save never
            # leaves a header pointing at entries that do not exist.
            for index, chunk in enumerate(chunks):
                self._keyring.set_password(self.SERVICE, self._part_name(username, index), chunk)
            self._keyring.set_password(
                self.SERVICE,
                username,
                json.dumps({"schema_version": 1, "chunks": len(chunks)}, separators=(",", ":")),
            )
        self._delete_parts(username, start=len(chunks) if len(chunks) > 1 else 0)

    def _read_chunked(self, username: str, raw: str) -> str:
        try:
            header = json.loads(raw)
            count = header.get("chunks") if isinstance(header, dict) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return raw
        if not isinstance(count, int) or not 0 < count <= self.MAX_CHUNKS:
            return raw
        parts: list[str] = []
        for index in range(count):
            chunk = self._keyring.get_password(self.SERVICE, self._part_name(username, index))
            if chunk is None:
                raise RuntimeError("stored credential envelope is invalid")
            parts.append(chunk)
        return "".join(parts)

    def _delete_parts(self, username: str, *, start: int = 0) -> None:
        for index in range(start, self.MAX_CHUNKS):
            name = self._part_name(username, index)
            if self._keyring.get_password(self.SERVICE, name) is None:
                break
            self._keyring.delete_password(self.SERVICE, name)

    def save(
        self,
        *,
        subject: str,
        purpose: CredentialPurpose,
        credentials_json: str,
        granted_scopes: tuple[str, ...] | list[str],
        id_token: str,
    ) -> None:
        if not id_token or not credentials_json:
            raise ValueError("credential envelope is incomplete")
        scopes = tuple(sorted(set(granted_scopes)))
        if not scopes:
            raise ValueError("credential envelope has no observed granted scopes")
        try:
            json.loads(credentials_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("credential payload must be valid SDK JSON") from exc
        envelope = {
            "schema_version": 1,
            "subject": subject,
            "purpose": purpose.value,
            "granted_scopes": scopes,
            "credentials_json": credentials_json,
            "id_token": id_token,
        }
        self._write_chunked(
            self._username(subject, purpose),
            json.dumps(envelope, separators=(",", ":"), sort_keys=True),
        )
        subjects = self._subjects()
        subjects.add(subject)
        self._keyring.set_password(self.SERVICE, self.INDEX_USER, json.dumps(sorted(subjects)))

    def load(self, subject: str, purpose: CredentialPurpose) -> StoredCredential | None:
        username = self._username(subject, purpose)
        raw = self._keyring.get_password(self.SERVICE, username)
        if raw is None:
            return None
        raw = self._read_chunked(username, raw)
        try:
            envelope = json.loads(raw)
            if (
                envelope.get("schema_version") != 1
                or envelope.get("subject") != subject
                or envelope.get("purpose") != purpose.value
            ):
                raise ValueError
            scopes = tuple(str(item) for item in envelope["granted_scopes"])
            credentials_json = str(envelope["credentials_json"])
            id_token = str(envelope["id_token"])
            json.loads(credentials_json)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("stored credential envelope is invalid") from exc
        return StoredCredential(
            subject=subject,
            purpose=purpose,
            granted_scopes=scopes,
            secret_payload={
                "credentials_json": credentials_json,
                "id_token": id_token,
            },
        )

    def delete(self, subject: str, purpose: CredentialPurpose) -> bool:
        username = self._username(subject, purpose)
        if self._keyring.get_password(self.SERVICE, username) is None:
            return False
        self._keyring.delete_password(self.SERVICE, username)
        self._delete_parts(username)
        return True

    def subjects(self) -> tuple[str, ...]:
        return tuple(sorted(self._subjects()))

    def _subjects(self) -> set[str]:
        raw = self._keyring.get_password(self.SERVICE, self.INDEX_USER)
        if raw is None:
            return set()
        try:
            values = json.loads(raw)
            return {str(value) for value in values if value}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("stored credential index is invalid") from exc

    def save_cloud_workspace_grant(
        self,
        *,
        subject: str,
        destination: str,
        scopes: tuple[str, ...] | list[str],
        credentials_json: str,
        consent: WorkspaceGrantConsent | None,
    ) -> None:
        """Store a cloud grant only with a matching trusted human consent.

        Secret Manager upload is owned by the cloud bootstrap phase.  This
        method only records the immutable authorization envelope in the secure
        local store and never calls a cloud service.
        """
        normalized = tuple(sorted(set(scopes)))
        existing = self.load(subject, CredentialPurpose.WORKSPACE)
        if (
            consent is None
            or not consent.confirmed
            or consent.subject != subject
            or consent.destination != destination
            or consent.scopes != normalized
            or consent != WorkspaceGrantConsent.create(
                subject=subject, destination=destination, scopes=normalized
            )
            or existing is None
            or existing.granted_scopes != normalized
            or existing.secret_payload["credentials_json"] != credentials_json
        ):
            raise PermissionError("explicit human consent is required for cloud grant storage")
        # Keep the verified Workspace grant intact.  Only the consent binding
        # is stored locally; Secret Manager upload is a separate explicit call.
        consent_key = f"cloud-consent:{subject}:{consent.binding}"
        self._keyring.set_password(
            self.SERVICE,
            consent_key,
            json.dumps(
                {"destination": destination, "scopes": normalized, "subject": subject},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    def upload_cloud_workspace_grant(
        self,
        *,
        subject: str,
        destination: str,
        scopes: tuple[str, ...] | list[str],
        credentials_json: str,
        consent: WorkspaceGrantConsent | None,
        secret_manager_client: Any | None = None,
        provisioning_credentials: Any | None = None,
    ) -> None:
        """Upload a grant through the official Secret Manager client.

        The client is constructed and called only after the immutable consent
        binding passes.  Tests inject a fake client; production uses the
        official ``google-cloud-secret-manager`` client.
        """
        normalized = tuple(sorted(set(scopes)))
        expected = (
            consent is not None
            and consent.confirmed
            and consent.subject == subject
            and consent.destination == destination
            and consent.scopes == normalized
            and consent
            == WorkspaceGrantConsent.create(
                subject=subject, destination=destination, scopes=normalized
            )
        )
        existing = self.load(subject, CredentialPurpose.WORKSPACE)
        if (
            not expected
            or existing is None
            or existing.granted_scopes != normalized
            or existing.secret_payload["credentials_json"] != credentials_json
        ):
            raise PermissionError("explicit human consent is required before Secret Manager")
        if secret_manager_client is None:
            if provisioning_credentials is None:
                raise RuntimeError(
                    "verified provisioning credentials are required for Secret Manager"
                )
            from google.cloud import secretmanager

            secret_manager_client = secretmanager.SecretManagerServiceClient(
                credentials=provisioning_credentials
            )
        request = {"parent": destination, "payload": {"data": credentials_json.encode("utf-8")}}
        secret_manager_client.add_secret_version(request=request)
