"""The scope check must not report success for a service that does not work.

A first version asked the credentials object what it believed it had.
`granted_scopes` is empty for user ADC, so every service came back usable while
Gmail was returning HTTP 403. These tests pin the property that failure taught:
the check reads what the token actually carries, and says so when it is absent.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from adk_harness import workspace


class _Response:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self.data = json.dumps(payload).encode()


def _fake_auth(monkeypatch: pytest.MonkeyPatch, *, scopes: str, status: int = 200):
    class _Credentials:
        token = "fake-token"
        granted_scopes: ClassVar[list[str]] = []

        def refresh(self, request: Any) -> None:
            return None

    class _Request:
        def __call__(self, url: str, method: str = "GET") -> _Response:
            return _Response(status, {"scope": scopes})

    import google.auth
    import google.auth.transport.requests

    monkeypatch.setattr(google.auth, "default", lambda scopes=None: (_Credentials(), "p"))
    monkeypatch.setattr(google.auth.transport.requests, "Request", _Request)


@pytest.mark.asyncio
async def test_a_missing_scope_is_reported_not_assumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_auth(monkeypatch, scopes=workspace.SCOPES["calendar"])

    result = await workspace.check_workspace_service_access(("calendar", "gmail"))

    assert result["calendar"] is None
    assert result["gmail"] is not None
    assert "gmail.compose" in result["gmail"]


@pytest.mark.asyncio
async def test_an_empty_granted_scopes_list_does_not_mean_everything_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact bug. The credentials object reports nothing; the token knows."""
    _fake_auth(monkeypatch, scopes="")

    result = await workspace.usable_services(("calendar",))

    assert result["calendar"] is not None, "no scopes must not read as usable"


@pytest.mark.asyncio
async def test_an_uninspectable_token_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A service account's token cannot be introspected this way.

    It holds whatever its identity was granted, so refusing to guess is right —
    unlike the user case, there is nothing here that could be checked.
    """
    _fake_auth(monkeypatch, scopes="", status=400)

    result = await workspace.usable_services(("calendar", "gmail"))

    assert result == {"calendar": None, "gmail": None}


@pytest.mark.asyncio
async def test_an_unknown_service_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_auth(monkeypatch, scopes=workspace.SCOPES["calendar"])

    result = await workspace.usable_services(("calendar", "telepathy"))

    assert "telepathy" in (result["telepathy"] or "")
