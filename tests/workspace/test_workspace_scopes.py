"""Workspace grant metadata checks never use ADC or token introspection."""

from __future__ import annotations

from typing import Any

import pytest

from adk_harness.workspace import CredentialReference, check_workspace_service_access


class _Auth:
    def __init__(self, missing: bool = False) -> None:
        self.missing = missing
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def verified_credentials(self, purpose: Any, *, subject: str, required_scopes: Any) -> object:
        self.calls.append((subject, tuple(required_scopes)))
        if self.missing:
            raise RuntimeError("secret token must never escape")
        return object()


@pytest.mark.asyncio
async def test_access_uses_explicit_verified_workspace_reference() -> None:
    auth = _Auth()
    result = await check_workspace_service_access(
        ("calendar", "gmail", "telepathy"),
        authenticator=auth,  # type: ignore[arg-type]
        credential_reference=CredentialReference(subject="google-user"),
    )

    assert result["calendar"] is None
    assert result["gmail"] is None
    assert "unknown service" in (result["telepathy"] or "")
    assert all(subject == "google-user" for subject, _ in auth.calls)


@pytest.mark.asyncio
async def test_missing_verified_grant_fails_closed() -> None:
    result = await check_workspace_service_access(
        ("calendar",),
        authenticator=_Auth(missing=True),  # type: ignore[arg-type]
        credential_reference=CredentialReference(subject="google-user"),
    )
    assert result == {"calendar": "verified Workspace credentials or required scope unavailable"}
