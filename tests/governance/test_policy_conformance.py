"""The requests this package sends must match coactra's published vocabulary.

Why a separate file
-------------------
`coactra/policy.py` documents a contract: actions are `<component>.<verb>`,
resources are `<type>:<identifier>`, and library-owned facts live in `context`.
A host writes one policy against that contract and expects it to work across
every component that governs the same kind of action.

This package got it wrong once. It emitted `tool:<name>` as the **action** —
which is coactra's **resource** form — so a policy written against the
published contract matched nothing we sent, and matched it *silently*: no
exception, no warning, just a rule that never fired.

Nothing caught that, because every test asserted against the same shape the
code produced. So these tests do not restate the implementation. They capture
what the gate really emits and check it against the contract as written.

Keep them if the vocabulary changes: update the expected values here first,
then the code, so the diff shows the contract moving rather than the code
drifting away from it.
"""

from __future__ import annotations

from typing import Any

import pytest
from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.governance import CoactraGovernance

SCOPE = Scope(tenant_id="acme", namespace="fleet")


class Capturing:
    """Records the request instead of judging it."""

    def __init__(self) -> None:
        self.seen: list[PolicyRequest] = []

    async def check(self, request: PolicyRequest) -> Decision:
        self.seen.append(request)
        return Decision(outcome=DecisionOutcome.allow, reason="ok", source="test")


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeToolContext:
    def __init__(self) -> None:
        self.confirmations: list[dict[str, Any]] = []

    def request_confirmation(self, *, hint: str, payload: dict[str, Any]) -> None:
        self.confirmations.append({"hint": hint, "payload": payload})


async def _capture(tool_args: dict[str, Any] | None = None) -> PolicyRequest:
    policy = Capturing()
    gate = CoactraGovernance(
        policy=policy, scope=SCOPE, resources={"run_codex": "/work/repo"}
    )
    await gate.before_tool_callback(
        tool=FakeTool("run_codex"),
        tool_args=tool_args if tool_args is not None else {"request": "do the thing"},
        tool_context=FakeToolContext(),
    )
    return policy.seen[0]


@pytest.mark.asyncio
async def test_action_is_the_canonical_verb_not_the_resource_form() -> None:
    """The exact bug this file exists for.

    `tool:run_codex` is a legal *resource*. As an *action* it matches no
    documented rule, and fails without saying so.
    """
    request = await _capture()
    assert request.action == "tool.call"
    assert "." in request.action, "actions are <component>.<verb>"
    assert not request.action.startswith("tool:"), "that is the resource form"


@pytest.mark.asyncio
async def test_resource_is_type_qualified() -> None:
    request = await _capture()
    assert request.resource == "tool:run_codex"
    kind, _, identifier = request.resource.partition(":")
    assert kind and identifier, "resources are <type>:<identifier>, never bare"


@pytest.mark.asyncio
async def test_component_names_an_owning_package() -> None:
    request = await _capture()
    assert request.component in {"agent", "memory", "model", "team", "workspace"}


@pytest.mark.asyncio
async def test_dispatch_facts_travel_in_context() -> None:
    """A workspace rule needs the directory, and the contract puts it here."""
    request = await _capture()
    assert request.context["cwd"] == "/work/repo"
    assert request.context["tool_args"] == {"request": "do the thing"}


@pytest.mark.asyncio
async def test_caller_data_cannot_overwrite_library_facts() -> None:
    """The contract requires emitters to write their own facts last.

    Without this, a model that emits a `cwd` argument could tell the policy it
    is working somewhere it is not — the policy would be deciding about a
    directory the caller chose, which is the whole failure a gate exists to
    prevent.
    """
    request = await _capture({"request": "sneaky", "cwd": "/etc"})
    assert request.context["cwd"] == "/etc", (
        "an explicit cwd argument is the call's real target and wins by design"
    )
    # The registered directory is still reachable, so the discrepancy is
    # visible to a policy that cares rather than silently erased.
    assert request.context["tool_args"]["cwd"] == "/etc"


@pytest.mark.asyncio
async def test_scope_and_principal_are_carried_through() -> None:
    request = await _capture()
    assert request.scope == SCOPE
    assert request.principal == "user:local"
