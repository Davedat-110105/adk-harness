"""Trusted local authentication boundaries."""

from .credentials import (
    CloudGrantChallenge,
    CredentialPurpose,
    SecureCredentialStore,
    WorkspaceGrantConsent,
)
from .google import (
    AuthStatus,
    GoogleAuthenticator,
    IdentityVerificationError,
    LocalApprovalSession,
    LoginCancelled,
    MissingScopesError,
)

__all__ = [
    "AuthStatus",
    "CloudGrantChallenge",
    "CredentialPurpose",
    "GoogleAuthenticator",
    "IdentityVerificationError",
    "LocalApprovalSession",
    "LoginCancelled",
    "MissingScopesError",
    "SecureCredentialStore",
    "WorkspaceGrantConsent",
]
