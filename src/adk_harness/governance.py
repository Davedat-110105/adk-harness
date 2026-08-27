"""The policy gate.

Every tool call made by every harness passes through this plugin before it
executes. Because ADK's `AgentTool` defaults to `include_plugins=True`, that
holds whether a harness runs as a sub-agent or as a tool.

The plugin decides nothing itself. It asks a Coactra `Policy` and translates the
answer into the vocabulary ADK understands.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from coactra import DecisionOutcome, Policy, PolicyRequest, Scope
from google.adk.plugins.base_plugin import BasePlugin

from adk_harness.precedent import MatchOutcome, Precedent, PrecedentStore

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
        name: str = "coactra-governance",
    ) -> None:
        super().__init__(name=name)
        self._policy = policy
        self._scope = scope
        self._principal = principal
        self._precedents = precedents if precedents is not None else PrecedentStore()
        self._resources = dict(resources or {})
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

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> dict[str, Any] | None:
        action = ACTION_TOOL_CALL
        workspace = self._resource_for(tool, tool_args)
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
            return None

        if decision.outcome is DecisionOutcome.requires_approval:
            return self._approve_or_ask(tool, tool_args, tool_context)

        return {
            "status": "blocked",
            "reason": decision.reason or "denied by policy",
            "tool": tool.name,
        }

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

        # A human may already have answered. When ADK resumes a run after a
        # confirmation, it re-invokes the tool with the answered
        # `ToolConfirmation` attached, which lands us back here. Without this
        # check the gate would ask the same question again and the run could
        # never proceed — the approve button would do nothing.
        answered = getattr(tool_context, "tool_confirmation", None)
        if answered is not None and getattr(answered, "confirmed", False):
            self._pending[tool.name] = {
                "action": action,
                "ambiguity_type": ambiguity,
                "facts": facts,
            }
            self._record(tool.name, action, "confirmed_by_human", getattr(answered, "hint", None))
            return None
        match = self._precedents.match(
            action=action, ambiguity_type=ambiguity, facts=facts
        )

        if match.outcome is MatchOutcome.apply and match.precedent is not None:
            self._record(
                tool.name,
                action,
                "allowed_by_precedent",
                f"{match.precedent.precedent_id}: {match.precedent.rationale}",
            )
            return None

        self._pending[tool.name] = {
            "action": action,
            "ambiguity_type": ambiguity,
            "facts": facts,
        }
        self._record(tool.name, action, "asked_human", match.reason)
        tool_context.request_confirmation(
            hint=_hint(tool.name, match.outcome, match.reason),
            payload={"tool_args": tool_args, "facts": facts},
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
    ) -> Precedent:
        """Turn a human's answer into a precedent that binds future calls.

        Call this after a human resolves a confirmation. The scope is the
        caller's to set, not the model's: a casual answer must not silently
        become a broad policy, so `applicability` is explicit rather than
        inferred.
        """
        context = self._pending.pop(tool_name, None)
        if context is None:
            raise KeyError(f"no pending clarification recorded for {tool_name!r}")
        precedent = Precedent(
            precedent_id=precedent_id,
            action=context["action"],
            ambiguity_type=context["ambiguity_type"],
            applicability=tuple(applicability),
            decision=dict(decision),
            rationale=rationale,
            confirmed_by=confirmed_by,
            created_at=datetime.now(UTC),
            review_after=review_after,
        )
        self._precedents.add(precedent)
        self._record(tool_name, context["action"], "precedent_saved", precedent_id)
        return precedent

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
    facts: dict[str, Any] = {"tool": tool_name}
    for key, value in tool_args.items():
        if isinstance(value, str | int | float | bool) or value is None:
            facts[key] = value
    return facts


def _hint(tool_name: str, outcome: MatchOutcome, reason: str | None) -> str:
    if outcome is MatchOutcome.conflict:
        return f"Approve {tool_name}? Existing precedents disagree: {reason}"
    if outcome is MatchOutcome.expired:
        return f"Approve {tool_name}? A precedent matched but needs review: {reason}"
    return f"Approve {tool_name}? No precedent covers this yet."
