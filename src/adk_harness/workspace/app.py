"""Build a governed app from ADK's Google Workspace toolsets.

Each API operation is gated separately. Authentication uses Application Default
Credentials with explicit service scopes.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from importlib.util import find_spec
from typing import Any

from coactra import Policy, Scope
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps.app import App
from google.adk.auth.auth_credential import ServiceAccount

from adk_harness.governance import CoactraGovernance
from adk_harness.governance.content_armor import ContentArmor
from adk_harness.governance.ledger import FirestoreActionLedger
from adk_harness.governance.precedents import PrecedentStore

__all__ = [
    "SCOPES",
    "TOOLSETS",
    "WorkspaceApp",
    "WorkspaceFleet",
    "build_workspace_app",
    "build_workspace_fleet",
    "check_workspace_service_access",
    "usable_services",
]

DEFAULT_MODEL = "gemini-3.5-flash"

SCOPES = {
    "calendar": "https://www.googleapis.com/auth/calendar.events",
    "gmail": "https://www.googleapis.com/auth/gmail.compose",
    "docs": "https://www.googleapis.com/auth/documents",
    "sheets": "https://www.googleapis.com/auth/spreadsheets",
}
"""Narrowest scope that does the job, per service.

`gmail.compose` is a *restricted* scope: Google requires app verification before
it will issue one outside a tester list. That is a real constraint, not a
configuration mistake, and it is why a fleet may legitimately ship with Gmail
absent.
"""


def _make_toolset(class_name: str, **kwargs: Any) -> Any:
    """Keep optional Google API dependencies out of base-package imports."""
    try:
        from google.adk.tools import google_api_tool
    except ImportError as exc:
        raise RuntimeError(
            'install Workspace dependencies: pip install "adk-harness[google-workspace]"'
        ) from exc
    return getattr(google_api_tool, class_name)(**kwargs)


TOOLSETS: dict[str, Any] = {
    service: partial(_make_toolset, class_name)
    for service, class_name in (
        ("calendar", "CalendarToolset"),
        ("gmail", "GmailToolset"),
        ("docs", "DocsToolset"),
        ("sheets", "SheetsToolset"),
    )
}


@dataclass(frozen=True, slots=True)
class WorkspaceApp:
    """A governed Workspace app, plus the gate that answers for it."""

    app: App
    orchestrator: LlmAgent
    governance: CoactraGovernance
    services: tuple[str, ...]
    tool_names: tuple[str, ...]

    @property
    def audit(self) -> Sequence[Any]:
        return self.governance.audit


async def build_workspace_app(
    *,
    policy: Policy,
    scope: Scope,
    services: Sequence[str] = ("calendar",),
    tool_filter: Sequence[str] | None = None,
    model: str = DEFAULT_MODEL,
    principal: str = "user:local",
    precedents: PrecedentStore | None = None,
    ledger: FirestoreActionLedger | None = None,
    armor: ContentArmor | None = None,
    name: str = "workspace_fleet",
    instruction: str | None = None,
) -> WorkspaceApp:
    """Wire official Workspace toolsets behind one policy gate.

    Use tool_filter to expose only the operations the app needs, before policy checks.
    """
    unknown = [s for s in services if s not in TOOLSETS]
    if unknown:
        raise ValueError(
            f"unknown Workspace service(s): {', '.join(unknown)}; "
            f"known: {', '.join(sorted(TOOLSETS))}"
        )

    credential = ServiceAccount(
        use_default_credential=True,
        scopes=[SCOPES[service] for service in services],
    )

    tools: list[Any] = []
    for service in services:
        tools.append(
            TOOLSETS[service](
                service_account=credential,
                tool_filter=list(tool_filter) if tool_filter else None,
            )
        )

    governance = CoactraGovernance(
        policy=policy,
        scope=scope,
        principal=principal,
        precedents=precedents,
        ledger=ledger,
        armor=armor,
    )

    orchestrator = LlmAgent(
        name=name,
        model=model,
        description="Completes Workspace work under a single policy gate.",
        instruction=instruction or _instruction(services),
        tools=tools,
    )

    names: list[str] = []
    for toolset in tools:
        names.extend(tool.name for tool in await toolset.get_tools())

    return WorkspaceApp(
        app=App(name=name, root_agent=orchestrator, plugins=[governance]),
        orchestrator=orchestrator,
        governance=governance,
        services=tuple(services),
        tool_names=tuple(names),
    )


async def check_workspace_service_access(
    services: Sequence[str] = tuple(SCOPES),
) -> dict[str, str | None]:
    """Return service-to-error mappings; None means no access issue was detected.

    Inspect token scopes because user ADC granted_scopes can be empty. Tokens that
    cannot be introspected are left to the API's authorization checks.
    """
    if find_spec("googleapiclient") is None:
        return dict.fromkeys(
            services, 'install Workspace dependencies: pip install "adk-harness[google-workspace]"'
        )

    if not services:
        return {}

    import google.auth
    import google.auth.transport.requests

    try:
        credentials, _ = google.auth.default(scopes=list(SCOPES.values()))
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
    except Exception as exc:
        detail = f"no usable Application Default Credentials: {exc}"
        return dict.fromkeys(services, detail)

    token = getattr(credentials, "token", None)
    if not token:
        return dict.fromkeys(services, "credentials produced no access token")

    response = request(
        url=f"https://oauth2.googleapis.com/tokeninfo?access_token={token}",
        method="GET",
    )
    if response.status != 200:
        # A service account's token is not introspectable this way. It holds
        # whatever its identity was granted, and there is nothing to check.
        return dict.fromkeys(services)

    payload = json.loads(response.data)
    granted = set(str(payload.get("scope", "")).split())

    result: dict[str, str | None] = {}
    for service in services:
        needed = SCOPES.get(service)
        if needed is None:
            result[service] = f"unknown service {service!r}"
        elif needed in granted:
            result[service] = None
        else:
            result[service] = (
                f"the token does not carry {needed}. Re-run `gcloud auth "
                "application-default login --client-id-file=... --scopes=..."
                f",{needed}` and check the consent screen actually lists it — "
                "Google drops scopes it will not grant rather than failing."
            )
    return result


# Compatibility names retained for callers of the pre-audit API.
WorkspaceFleet = WorkspaceApp


async def build_workspace_fleet(**kwargs: Any) -> WorkspaceApp:
    warnings.warn(
        "build_workspace_fleet() is deprecated; use build_workspace_app()",
        DeprecationWarning,
        stacklevel=2,
    )
    return await build_workspace_app(**kwargs)


async def usable_services(
    services: Sequence[str] = tuple(SCOPES),
) -> dict[str, str | None]:
    warnings.warn(
        "usable_services() is deprecated; use check_workspace_service_access()",
        DeprecationWarning,
        stacklevel=2,
    )
    return await check_workspace_service_access(services)


def _instruction(services: Sequence[str]) -> str:
    """Describe available services and require the model to respect policy refusals."""
    return (
        f"You complete work in Google Workspace: {', '.join(services)}.\n\n"
        "Use `primary` as the calendar id unless told otherwise. Call tools "
        "with complete arguments; do not guess times or recipients that were "
        "not given to you.\n\n"
        "Every tool call passes a policy gate. A result with status 'blocked' "
        "is a decision, not a transient error: report the reason and stop. Do "
        "not retry it, and do not look for a different tool that achieves the "
        "same thing. If the gate asks a human to confirm, wait for the answer "
        "rather than proceeding."
    )
