"""adk-harness — governed coding-agent harnesses for Google ADK."""

from adk_harness.agent import HarnessAgent
from adk_harness.fleet import Fleet, build_fleet, build_fleet_sync
from adk_harness.governance import AuditRecord, CoactraGovernance
from adk_harness.precedent import (
    Applicability,
    MatchOutcome,
    Precedent,
    PrecedentStore,
)
from adk_harness.protocol import Harness, HarnessSpec, HarnessTurn
from adk_harness.registry import HarnessRegistry
from adk_harness.stores import SQLitePrecedentStore
from adk_harness.workspace import WorkspaceFleet, build_workspace_fleet

__all__ = [
    "Applicability",
    "AuditRecord",
    "CoactraGovernance",
    "Fleet",
    "Harness",
    "HarnessAgent",
    "HarnessRegistry",
    "HarnessSpec",
    "HarnessTurn",
    "MatchOutcome",
    "Precedent",
    "PrecedentStore",
    "SQLitePrecedentStore",
    "WorkspaceFleet",
    "build_fleet",
    "build_fleet_sync",
    "build_workspace_fleet",
]
