"""Write down what was decided, so an approval outlives the conversation.

A gate that only answers allow or hold leaves nothing behind. These records say
who approved which exact change, under which policy, and what happened next.
The change hash binds the approval to the arguments that were shown, so an
approval cannot be reused for a different call.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from adk_harness.workflow.models import ActivityEvent, Approval, ChangeSet

__all__ = ["Evidence", "EvidenceWriter", "intent_hash"]

POLICY_VERSION = "workspace-mcp-1"


def intent_hash(*, subject: str, operation: str, arguments: Mapping[str, Any]) -> str:
    """Hash what is being asked for, so two identical requests match.

    A ChangeSet carries its own id and timestamp, so its content hash differs
    every attempt. An approval has to survive being asked again, and must not
    survive a change to the arguments.
    """
    import hashlib

    import rfc8785

    payload = {"subject": subject, "operation": operation, "arguments": dict(arguments)}
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()

# An approval covers the call it was shown, not the rest of the session.
APPROVAL_LIFETIME = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One decision and everything recorded about it."""

    change: ChangeSet
    event: ActivityEvent
    approval: Approval | None = None
    ledger_entry_id: str | None = None

    def summary(self) -> dict[str, Any]:
        """Return the non-secret shape of this record."""
        return {
            "task_id": self.change.task_id,
            "operation": self.event.details.get("operation"),
            "outcome": self.event.event_type,
            "change_hash": self.change.content_hash,
            "approved_by": self.approval.approver_id if self.approval else None,
            "approval_id": self.approval.approval_id if self.approval else None,
            "policy_version": self.event.policy_version,
            "occurred_at": self.event.occurred_at.isoformat(),
            "ledger_entry_id": self.ledger_entry_id,
        }


class EvidenceWriter:
    """Build the workflow records for one machine's decisions.

    The trail is kept in memory so a person can read it back in the same
    conversation. When a Firestore ledger is configured every entry also lands
    in one shared collection, which is what makes a fleet auditable rather than
    a set of separate laptops.
    """

    def __init__(
        self,
        *,
        project_id: str | None = None,
        workspace_id: str = "workspace",
        ledger: Any | None = None,
    ) -> None:
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or "local"
        self.workspace_id = workspace_id
        self.ledger = ledger
        self._trail: list[Evidence] = []

    @property
    def trail(self) -> tuple[Evidence, ...]:
        return tuple(self._trail)

    def attach_ledger(self, ledger: Any, *, project_id: str) -> None:
        """Point this machine's trail at one shared project.

        An administrator can set GOOGLE_CLOUD_PROJECT in the server's
        configuration and nobody is ever asked. Otherwise a person names the
        project once, in the client's own prompt.
        """
        self.ledger = ledger
        self.project_id = project_id

    def propose(self, *, subject: str, operation: str, arguments: Mapping[str, Any]) -> ChangeSet:
        """Describe the change before anyone decides about it."""
        return ChangeSet(
            task_id=str(uuid4()),
            project_id=self.project_id,
            workspace_id=self.workspace_id,
            user_id=subject,
            changes=({"operation": operation, "arguments": dict(arguments)},),
            policy_version=POLICY_VERSION,
        )

    def approve(self, change: ChangeSet, *, approver: str, scope: Mapping[str, Any]) -> Approval:
        """Bind a person's decision to this exact change."""
        approved_at = datetime.now(UTC)
        return Approval(
            task_id=change.task_id,
            project_id=change.project_id,
            workspace_id=change.workspace_id,
            change_hash=change.content_hash,
            approver_id=approver,
            action_scope=dict(scope),
            policy_version=POLICY_VERSION,
            trace_id=change.trace_id,
            approved_at=approved_at,
            expires_at=approved_at + APPROVAL_LIFETIME,
        )

    def record(
        self,
        change: ChangeSet,
        *,
        actor: str,
        operation: str,
        outcome: str,
        reason: str,
        approval: Approval | None = None,
        arguments: Mapping[str, Any] | None = None,
    ) -> Evidence:
        """Append what happened, and put it in the shared ledger when there is one."""
        event = ActivityEvent(
            task_id=change.task_id,
            project_id=change.project_id,
            workspace_id=change.workspace_id,
            event_type=outcome,
            actor_id=actor,
            details={
                "operation": operation,
                "reason": reason,
                "change_hash": change.content_hash,
                "approval_id": approval.approval_id if approval else None,
            },
            policy_version=POLICY_VERSION,
            trace_id=change.trace_id,
        )
        entry_id = self._append_to_ledger(
            actor=actor,
            operation=operation,
            outcome=outcome,
            reason=reason,
            change=change,
            arguments=arguments or {},
        )
        evidence = Evidence(
            change=change, event=event, approval=approval, ledger_entry_id=entry_id
        )
        self._trail.append(evidence)
        return evidence

    def _append_to_ledger(
        self,
        *,
        actor: str,
        operation: str,
        outcome: str,
        reason: str,
        change: ChangeSet,
        arguments: Mapping[str, Any],
    ) -> str | None:
        """Write one ledger entry, or none when no ledger is configured."""
        if self.ledger is None:
            return None
        try:
            return self.ledger.record(
                actor=actor,
                agent="adk-harness-mcp",
                action=operation,
                resource=f"workspace:{operation}",
                scope={"project": self.project_id, "workspace": self.workspace_id},
                policy_outcome=outcome,
                policy_reason=reason,
                tool_args=arguments,
                outcome=outcome,
                idempotency_key=f"{change.task_id}:{change.content_hash}",
            )
        except Exception:
            # A ledger that is unreachable must not decide whether a read runs.
            # The in-memory trail still holds the record for this session.
            return None
