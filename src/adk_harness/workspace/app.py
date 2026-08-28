"""Governed Google Workspace fleets, built on ADK's own toolsets.

Why this is not another adapter
-------------------------------
This package's `Harness` protocol exists because Claude Code, Codex, opencode
and Antigravity have nothing in common — each needed wrapping before a fleet
could treat them alike. Google Workspace is different: ADK already ships
`CalendarToolset`, `GmailToolset`, `DocsToolset` and friends, generated from
Google's own API discovery documents.

Hand-writing a Calendar adapter reimplemented that, worse. It was gated at
*dispatch* — one decision covering everything the harness then did — whereas an
ADK toolset presents each operation as its own tool, so `before_tool_callback`
fires on `calendar_events_insert` and `calendar_events_delete` separately.

That distinction is the whole point:

    The gateway evaluates every tool call. Approval at initial dispatch is
    insufficient.

Using the official toolsets satisfies that by construction, and by deleting
code rather than adding it.

Authentication
--------------
`ServiceAccount(use_default_credential=True)` uses Application Default
Credentials, so the same code runs locally under `gcloud auth
application-default login` and on Cloud Run under the service identity — no
browser, no client secret in the image.

Scopes are requested explicitly and narrowly. `calendar.events` grants event
read and write and nothing else; it cannot even list which calendars exist.
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
    """Wire official Workspace toolsets behind one Coactra policy gate.

    `tool_filter` is worth using rather than ignoring. `CalendarToolset` alone
    exposes 38 operations, including ACL changes; handing all of them to a model
    because they happen to exist is how a fleet acquires powers nobody decided
    to give it. Naming the operations you want is the cheapest control there is,
    and it applies before the policy ever runs.
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
    """Which Workspace services the current credentials can actually reach.

    A harness that is not installed reports `available=False` with a reason
    rather than raising; a Workspace service the credentials cannot reach
    deserves the same. Without this the failure arrives later as an HTTP 403
    from Google mid-run, which reads like a bug in this library.

    This asks Google what the token actually carries rather than asking the
    credentials object what it believes. A first version did the latter:
    `granted_scopes` is empty for user ADC, so every service came back usable
    while Gmail was in fact returning 403. A check that reports success when
    the thing does not work is worse than no check, because it is believed.

    Returns a mapping of service to `None` when usable, or a sentence saying
    what to do about it.
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
    """Tell the model what it has, and what a refusal means.

    The last paragraph matters. When policy denies a call, the gate returns a
    blocked result rather than raising, so the model can explain the refusal. A
    model that instead retries, or reaches for a different tool that achieves
    the same effect, converts a clean governance decision into a workaround.
    """
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
