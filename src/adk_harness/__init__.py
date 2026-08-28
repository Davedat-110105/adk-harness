"""adk-harness — governed coding-agent harnesses for Google ADK."""

from typing import TYPE_CHECKING

from adk_harness.coding.fleet import Fleet, build_fleet, build_fleet_sync
from adk_harness.coding.harness_agent import HarnessAgent
from adk_harness.coding.protocol import Harness, HarnessSpec, HarnessTurn
from adk_harness.coding.registry import HarnessRegistry
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
from adk_harness.workspace import (
    WorkspaceApp,
    WorkspaceFleet,
    build_workspace_app,
    build_workspace_fleet,
    check_workspace_service_access,
    usable_services,
)

from . import _compat as _compat

if TYPE_CHECKING:
    from adk_harness.governance.stores import PersistentPrecedentStore

__all__ = [
    "Applicability",
    "ArmorFinding",
    "AuditRecord",
    "CoactraGovernance",
    "ContentArmor",
    "Fleet",
    "Harness",
    "HarnessAgent",
    "HarnessRegistry",
    "HarnessSpec",
    "HarnessTurn",
    "MatchOutcome",
    "MatchResult",
    "PersistentPrecedentStore",
    "Precedent",
    "PrecedentStore",
    "SQLitePrecedentStore",
    "WorkspaceApp",
    "WorkspaceFleet",
    "build_fleet",
    "build_fleet_sync",
    "build_workspace_app",
    "build_workspace_fleet",
    "check_workspace_service_access",
    "usable_services",
]


def __getattr__(name: str):
    if name == "PersistentPrecedentStore":
        from adk_harness.governance.stores import PersistentPrecedentStore

        return PersistentPrecedentStore
    raise AttributeError(name)
