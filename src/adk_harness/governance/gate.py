"""Apply Coactra decisions to ADK tool calls and harness dispatch, not vendor inner commands."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from coactra import DecisionOutcome, Policy, PolicyRequest, Scope
from google.adk.plugins.base_plugin import BasePlugin

from adk_harness.governance.content_armor import ContentArmor
from adk_harness.governance.ledger import FirestoreActionLedger
from adk_harness.governance.precedents import MatchOutcome, Precedent, PrecedentStore

__all__ = ["ACTION_TOOL_CALL", "AuditRecord", "CoactraGovernance"]

ACTION_TOOL_CALL = "tool.call"
"""coactra 0.7's canonical action for invoking a tool.

The vocabulary is documented at the top of `coactra/policy.py`: actions are
`<component>.<verb>`, resources are `<type>:<identifier>`. This package used to
emit `tool:<name>` as the *action*, which is coactra's *resource* form — so a
policy written against the published contract silently failed to match ours.

Dispatch facts a workspace rule needs, notably `cwd`, travel in `context`,
which is where the contract puts library-owned facts."""


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One policy decision, kept for the reasoning-chain audit trail."""

    at_utc: datetime
    tool_name: str
    action: str
    outcome: str
    reason: str | None = None


class CoactraGovernance(BasePlugin):
    """Translate policy decisions into ADK callbacks.

    Allow returns None; deny and pending confirmation return a result that prevents
    execution. Human decisions may be reused through scoped precedents.
    """

    def __init__(
        self,
        *,
        policy: Policy,
        scope: Scope,
        principal: str = "user:local",
        precedents: PrecedentStore | None = None,
        resources: Mapping[str, str] | None = None,
        armor: ContentArmor | None = None,
        ledger: FirestoreActionLedger | None = None,
        name: str = "coactra-governance",
    ) -> None:
        super().__init__(name=name)
        self._policy = policy
        self._scope = scope
        self._principal = principal
        self._precedents = precedents if precedents is not None else PrecedentStore()
        self._resources = dict(resources or {})
        # Compose controls here: ADK stops at the first non-None plugin result,
        # so independent armor/ledger plugins can miss refusals and quarantine.
        self.armor = armor
        self.ledger = ledger
        self._audit: list[AuditRecord] = []
        self._pending: dict[str, dict[str, Any]] = {}

    @property
    def precedents(self) -> PrecedentStore:
        """The precedents this gate consults before interrupting a human."""
        return self._precedents

    @property
    def audit(self) -> Sequence[AuditRecord]:
        """Every decision this plugin has made, oldest first."""
        return tuple(self._audit)

    def reject_tool_call(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any, reason: str
    ) -> dict[str, Any]:
        """Record a host boundary rejection before consulting a caller policy."""
        tool_context._adk_harness_invocation = uuid4().hex
        self._record(tool.name, ACTION_TOOL_CALL, "deny", reason)
        tool_context._adk_harness_audit = self._audit[-1]
        self._write_ledger(tool, tool_args, tool_context, "blocked", terminal=True)
        return {"status": "blocked", "reason": reason, "tool": tool.name}

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> dict[str, Any] | None:
        action = ACTION_TOOL_CALL
        workspace = self._resource_for(tool, tool_args)
        tool_context._adk_harness_invocation = uuid4().hex
        tool_context._adk_harness_terminal = False
        if self.armor is not None:
            blocked = await self.armor.before_tool_callback(
                tool=tool, tool_args=tool_args, tool_context=tool_context
            )
            if blocked is not None:
                self._record(tool.name, action, "blocked_by_armor", blocked.get("reason"))
                tool_context._adk_harness_audit = self._audit[-1]
                self._write_ledger(tool, tool_args, tool_context, "blocked", terminal=True)
                return blocked
        decision = await self._policy.check(
            PolicyRequest(
                principal=self._principal,
                action=action,
                resource=f"tool:{tool.name}",
                scope=self._scope,
                component="agent",
                # Library-owned facts written last, so caller data in tool_args
                # cannot overwrite them — coactra's contract requires this.
                context={"tool_args": dict(tool_args), "cwd": workspace},
            )
        )
        self._record(tool.name, action, decision.outcome.name, decision.reason)

        if decision.outcome is DecisionOutcome.allow:
            result = None
        elif decision.outcome is DecisionOutcome.requires_approval:
            result = self._approve_or_ask(tool, tool_args, tool_context)
        else:
            result = {
                "status": "blocked",
                "reason": decision.reason or "denied by policy",
                "tool": tool.name,
            }
        # No await between the decision and this assignment: later invocations
        # cannot borrow another request's audit attribution.
        tool_context._adk_harness_audit = self._audit[-1]
        self._write_ledger(
            tool,
            tool_args,
            tool_context,
            result["status"] if result is not None else "authorized",
            terminal=result is not None,
        )
        return result

    def _approve_or_ask(
        self,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> dict[str, Any] | None:
        """Apply a matching precedent or request human confirmation.

        Return a dict to stop execution and surface the confirmation event;
        request_confirmation() alone does not stop the tool. Precedents never override deny.
        """
        action = ACTION_TOOL_CALL
        ambiguity = _ambiguity_type(tool.name)
        facts = _facts(tool.name, tool_args)
        facts.update(
            principal=self._principal,
            tenant_id=self._scope.tenant_id,
            namespace=self._scope.namespace,
            cwd=self._resource_for(tool, tool_args),
        )
        confirmation_id = str(
            getattr(tool_context, "function_call_id", None) or tool_context._adk_harness_invocation
        )
        pending = {"tool": tool.name, "action": action, "ambiguity_type": ambiguity, "facts": facts}

        # ADK retries with the answered confirmation; do not ask again.
        answered = getattr(tool_context, "tool_confirmation", None)
        if answered is not None and getattr(answered, "confirmed", False):
            self._pending[confirmation_id] = pending
            self._record(tool.name, action, "confirmed_by_human", getattr(answered, "hint", None))
            return None
        match = self._precedents.match(action=action, ambiguity_type=ambiguity, facts=facts)

        if match.outcome is MatchOutcome.apply and match.precedent is not None:
            if match.precedent.decision.get("approve") is False:
                self._record(tool.name, action, "denied_by_precedent", match.precedent.rationale)
                return {"status": "blocked", "reason": match.precedent.rationale, "tool": tool.name}
            self._record(
                tool.name,
                action,
                "allowed_by_precedent",
                f"{match.precedent.precedent_id}: {match.precedent.rationale}",
            )
            return None

        self._pending[confirmation_id] = pending
        self._record(tool.name, action, "asked_human", match.reason)
        tool_context.request_confirmation(
            hint=_hint(tool.name, match.outcome, match.reason),
            payload={"tool_args": tool_args, "facts": facts, "confirmation_id": confirmation_id},
        )
        return {
            "status": "awaiting_confirmation",
            "reason": match.reason or "a human must approve this",
            "tool": tool.name,
        }

    def remember(
        self,
        *,
        tool_name: str,
        precedent_id: str,
        decision: Mapping[str, Any],
        rationale: str,
        confirmed_by: str,
        applicability: Sequence[Any] = (),
        review_after: datetime | None = None,
        confirmation_id: str | None = None,
    ) -> Precedent:
        """Save a trusted human decision with explicit applicability.

        The host sets scope, never the model. Supply confirmation_id when multiple
        questions are pending for the same tool; ambiguous answers fail closed.
        """
        if confirmation_id is None:
            candidates = [key for key, value in self._pending.items() if value["tool"] == tool_name]
            if len(candidates) > 1:
                raise ValueError("multiple pending clarifications; specify confirmation_id")
            confirmation_id = next(iter(candidates), "")
        context = self._pending.get(confirmation_id)
        if context is None or context["tool"] != tool_name:
            raise KeyError(f"no pending clarification recorded for {tool_name!r}")
        from adk_harness.governance.precedents import Applicability

        # A trusted host may generalize task predicates, but an answer must not
        # grant authority to another principal, tenant, tool, or workspace.
        bindings = tuple(
            Applicability(key, "eq", context["facts"][key])
            for key in ("tool", "principal", "tenant_id", "namespace", "cwd")
        )
        precedent = Precedent(
            precedent_id=precedent_id,
            action=context["action"],
            ambiguity_type=context["ambiguity_type"],
            applicability=tuple(applicability) + bindings,
            decision=dict(decision),
            rationale=rationale,
            confirmed_by=confirmed_by,
            created_at=datetime.now(UTC),
            review_after=review_after,
        )
        self._precedents.add(precedent)
        self._pending.pop(confirmation_id, None)
        self._record(tool_name, context["action"], "precedent_saved", precedent_id)
        return precedent

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: Any = None,
    ) -> Any:
        """Record the terminal outcome without claiming a held call executed."""
        if getattr(tool_context, "_adk_harness_terminal", False):
            return None
        armored = None
        if self.armor is not None:
            armored = await self.armor.after_tool_callback(
                tool=tool, tool_args=tool_args, tool_context=tool_context, result=result
            )
        effective = armored if armored is not None else result
        status = effective.get("status") if isinstance(effective, dict) else None
        outcome = {
            "blocked": "completed_blocked",
            "awaiting_confirmation": "held",
            "quarantined": "quarantined",
            "error": "error",
        }.get(str(status), "completed")
        self._record(
            tool.name,
            ACTION_TOOL_CALL,
            outcome,
            None,
        )
        self._write_ledger(tool, tool_args, tool_context, outcome, terminal=True)
        return armored if armored is not result else None

    async def on_tool_error_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any, error: BaseException
    ) -> None:
        outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        self._record(tool.name, ACTION_TOOL_CALL, outcome, type(error).__name__)
        self._write_ledger(tool, tool_args, tool_context, outcome, terminal=True)

    def _write_ledger(
        self,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        outcome: str,
        *,
        terminal: bool,
    ) -> None:
        if self.ledger is not None:
            record = getattr(tool_context, "_adk_harness_audit", None)
            invocation = getattr(tool_context, "_adk_harness_invocation", None)
            if invocation is None:
                invocation = uuid4().hex
                tool_context._adk_harness_invocation = invocation
            # Prewrite failure blocks execution; terminal recording failure cannot undo it.
            self.ledger.record(
                actor=self._principal,
                agent="adk-harness",
                action=ACTION_TOOL_CALL,
                resource=f"tool:{tool.name}",
                scope=f"{self._scope.tenant_id}:{self._scope.namespace}",
                policy_outcome=record.outcome if record else "not_evaluated",
                policy_reason=record.reason if record else None,
                tool_args=tool_args,
                outcome=outcome,
                idempotency_key=f"{invocation}:{'terminal' if terminal else 'decision'}",
            )
        tool_context._adk_harness_terminal = terminal

    def _resource_for(self, tool: Any, tool_args: Mapping[str, Any]) -> str:
        """Resolve the policy target from cwd, the registered resource, or the tool name.

        ADK tool arguments may omit cwd, so Workspace applications register
        each tool's governed resource explicitly.
        """
        cwd = tool_args.get("cwd")
        if cwd:
            return str(cwd)
        registered = self._resources.get(tool.name)
        if registered:
            return registered
        return str(tool.name)

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


def _ambiguity_type(tool_name: str) -> str:
    """Classify the policy question so equivalent requests can share a precedent."""
    return f"approval_required:{tool_name}"


def _facts(tool_name: str, tool_args: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a call into the facts a predicate can be written against."""
    facts: dict[str, Any] = {}
    for key, value in tool_args.items():
        if isinstance(value, str | int | float | bool) or value is None:
            facts[key] = value
    facts["tool"] = tool_name
    return facts


def _hint(tool_name: str, outcome: MatchOutcome, reason: str | None) -> str:
    if outcome is MatchOutcome.conflict:
        return f"Approve {tool_name}? Existing precedents disagree: {reason}"
    if outcome is MatchOutcome.expired:
        return f"Approve {tool_name}? A precedent matched but needs review: {reason}"
    return f"Approve {tool_name}? No precedent covers this yet."
