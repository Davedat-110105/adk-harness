"""The policy gate.

ADK tool calls and coding-harness dispatch pass through this plugin. Inner
commands executed by a vendor harness do not; see `harness_agent.py`.

The plugin decides nothing itself. It asks a Coactra `Policy` and translates the
answer into the vocabulary ADK understands.
"""

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
        """Consult precedent before spending a human interruption.

        Returning a dict here is not decoration — it is what stops the tool.
        `request_confirmation()` only records a request on the event actions
        (see `ToolContext.request_confirmation`); it does not halt anything. ADK
        runs the tool whenever `before_tool_callback` returns `None`
        (`flows/llm_flows/functions.py`, step 3). Asking a human and returning
        `None` would therefore ask *and* proceed, which is the worst of both:
        an approval prompt that changes nothing.

        Returning a response also produces the function-response event that
        ADK's `generate_request_confirmation_event` needs in order to surface
        the pending confirmation to the client. So the dict is both the brake
        and the signal.

        This is the whole point of the system. Policy has said a human must
        decide. If a human already decided this exact question, under
        conditions that still hold, asking again is noise.

        Precedent removes the repeated question. It never removes the policy
        gate itself, and it never converts a deny into an allow.
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

        # A human may already have answered. When ADK resumes a run after a
        # confirmation, it re-invokes the tool with the answered
        # `ToolConfirmation` attached, which lands us back here. Without this
        # check the gate would ask the same question again and the run could
        # never proceed — the approve button would do nothing.
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
        """Turn a human's answer into a precedent that binds future calls.

        Call this after a human resolves a confirmation. The scope is the
        caller's to set, not the model's: a casual answer must not silently
        become a broad policy, so `applicability` is explicit rather than
        inferred. Pass the confirmation payload's `confirmation_id` when more
        than one question is pending for this tool; ambiguous answers fail closed.
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
            # Failure is propagated. In the before callback this prevents the
            # action; a terminal failure means execution happened but recording
            # failed, never that the action was rolled back.
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
        """Name the thing a policy is actually deciding about.

        A tool that takes `cwd` names its own target, so that wins. But a
        harness dispatched through ADK's `AgentTool` does not: its arguments are
        just the instruction text, and the working directory lives on the agent
        that was wrapped. Without the registered mapping the policy would
        receive the *tool name* as the resource, and a rule like "must be under
        /workspace" would reject every dispatch for the wrong reason — a gate
        that looks like it is working while deciding on the wrong noun.

        `build_fleet` registers `{tool_name: cwd}` for exactly this. Falling
        back to the tool name is kept only so an unregistered tool still gets a
        decision rather than a crash.
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
    """Name the *kind* of question being asked, not the instance.

    Precedent has to key on something more stable than a tool name and less
    vague than "similar situation". The kind of judgment being requested is
    that middle ground.
    """
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
