"""Governed Google ADK Workspace application and workflow records."""
from typing import TYPE_CHECKING

from adk_harness.governance import AuditRecord, CoactraGovernance
from adk_harness.governance.content_armor import ArmorFinding, ContentArmor
from adk_harness.governance.precedents import (
    Applicability,
    MatchOutcome,
    MatchResult,
    Precedent,
    PrecedentStore,
)
from adk_harness.governance.stores import SQLitePrecedentStore
from adk_harness.integrations import AntigravityIntegration
from adk_harness.workflow import (
    ActivityEvent,
    Approval,
    ChangeSet,
    TaskRequest,
    TaskState,
    transition,
)
from adk_harness.workspace import (
    APPLICATION_SCOPES,
    CredentialReference,
    WorkspaceApp,
    WorkspaceConnection,
    WorkspaceConsent,
    build_workspace_app,
    check_workspace_service_access,
)

from . import _compat as _compat

if TYPE_CHECKING:
    from adk_harness.governance.stores import PersistentPrecedentStore

__all__ = [
    "APPLICATION_SCOPES",
    "ActivityEvent",
    "AntigravityIntegration",
    "Applicability",
    "Approval",
    "ArmorFinding",
    "AuditRecord",
    "ChangeSet",
    "CoactraGovernance",
    "ContentArmor",
    "CredentialReference",
    "MatchOutcome",
    "MatchResult",
    "PersistentPrecedentStore",
    "Precedent",
    "PrecedentStore",
    "SQLitePrecedentStore",
    "TaskRequest",
    "TaskState",
    "WorkspaceApp",
    "WorkspaceConnection",
    "WorkspaceConsent",
    "build_workspace_app",
    "check_workspace_service_access",
    "transition",
]


def __getattr__(name: str):
    if name == "PersistentPrecedentStore":
        from adk_harness.governance.stores import PersistentPrecedentStore
        return PersistentPrecedentStore
    raise AttributeError(name)
