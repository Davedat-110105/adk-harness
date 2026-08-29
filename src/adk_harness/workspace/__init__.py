"""Governed, per-user Google Workspace application."""

from .app import (
    APPLICATION_SCOPES,
    READ_OPERATIONS,
    SCOPES,
    WorkspaceApp,
    WorkspaceConnection,
    WorkspaceConsent,
    build_workspace_app,
    check_workspace_service_access,
)
from .connections import (
    CredentialReference,
    WorkspaceConnectionError,
    WorkspaceDenied,
    WorkspaceStale,
    WorkspaceUnknownOutcome,
    WorkspaceUnsupported,
)

__all__ = [
    "APPLICATION_SCOPES",
    "READ_OPERATIONS",
    "SCOPES",
    "CredentialReference",
    "WorkspaceApp",
    "WorkspaceConnection",
    "WorkspaceConnectionError",
    "WorkspaceConsent",
    "WorkspaceDenied",
    "WorkspaceStale",
    "WorkspaceUnknownOutcome",
    "WorkspaceUnsupported",
    "build_workspace_app",
    "check_workspace_service_access",
]
