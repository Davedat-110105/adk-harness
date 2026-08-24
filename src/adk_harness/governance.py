"""The policy gate.

Every tool call made by every harness passes through this plugin before it
executes. Because ADK's `AgentTool` defaults to `include_plugins=True`, that
holds whether a harness runs as a sub-agent or as a tool.

The plugin decides nothing itself. It asks a Coactra `Policy` and translates the
answer into the vocabulary ADK understands.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from coactra import DecisionOutcome, Policy, PolicyRequest, Scope
from google.adk.plugins.base_plugin import BasePlugin

__all__ = ["CoactraGovernance", "AuditRecord"]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One policy decision, kept for the reasoning-chain audit trail."""

    at_utc: datetime
    tool_name: str
    action: str
    outcome: str
    reason: str | None = None


class CoactraGovernance(BasePlugin):
    """Gate ADK tool calls on a Coactra policy decision.

    The three outcomes map onto ADK as follows. `allow` returns `None`, which
    lets the tool run. `deny` returns a dict, which ADK substitutes as the tool's
    result, so the model sees the refusal and can explain it rather than failing
    opaquely. `requires_approval` calls ADK's own `request_confirmation`, which
    interrupts the run until a human answers and then resumes it.
    """

    def __init__(
        self,
        *,
        policy: Policy,
        scope: Scope,
        principal: str = "user:local",
        name: str = "coactra-governance",
    ) -> None:
        super().__init__(name=name)
        self._policy = policy
        self._scope = scope
        self._principal = principal
        self._audit: list[AuditRecord] = []

    @property
    def audit(self) -> Sequence[AuditRecord]:
        """Every decision this plugin has made, oldest first."""
        return tuple(self._audit)

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> dict[str, Any] | None:
        action = f"tool:{tool.name}"
        decision = await self._policy.check(
            PolicyRequest(
                principal=self._principal,
                action=action,
                resource=str(tool_args.get("cwd") or tool.name),
                scope=self._scope,
                component="adk-harness",
                context={"tool_args": tool_args},
            )
        )
        self._record(tool.name, action, decision.outcome.name, decision.reason)

        if decision.outcome is DecisionOutcome.allow:
            return None

        if decision.outcome is DecisionOutcome.requires_approval:
            tool_context.request_confirmation(
                hint=f"Approve {tool.name}? Policy requires human sign-off.",
                payload=tool_args,
            )
            return None

        return {
            "status": "blocked",
            "reason": decision.reason or "denied by policy",
            "tool": tool.name,
        }

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: Any = None,
    ) -> None:
        """Close the audit record for a call that actually ran."""
        blocked = isinstance(result, dict) and result.get("status") == "blocked"
        self._record(
            tool.name,
            f"tool:{tool.name}",
            "completed_blocked" if blocked else "completed",
            None,
        )
        return None

    def _record(self, tool_name: str, action: str, outcome: str, reason: str | None) -> None:
        self._audit.append(
            AuditRecord(
                at_utc=datetime.now(UTC),
                tool_name=tool_name,
                action=action,
                outcome=outcome,
                reason=reason,
            )
        )
