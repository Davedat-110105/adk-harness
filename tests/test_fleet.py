"""build_fleet: what gets wired, and what happens when nothing is installed.

These tests never call a model. They assert on the structure `build_fleet`
produces — which harnesses became tools, what the orchestrator was told, and
that one governance instance is shared by all of them. That last property is the
library's central claim, so it is pinned here rather than left to inspection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.tools.agent_tool import AgentTool

from adk_harness.fleet import build_fleet
from adk_harness.protocol import HarnessSpec, HarnessTurn
from adk_harness.registry import HarnessRegistry

SCOPE = Scope(tenant_id="acme", namespace="default")


class AllowAll:
    async def check(self, request: PolicyRequest) -> Decision:
        return Decision(outcome=DecisionOutcome.allow, source="test")


class StubHarness:
    def __init__(self, harness_id: str, *, available: bool = True) -> None:
        self.spec = HarnessSpec(
            id=harness_id,
            version="1.2.3",
            capabilities=("edit", "shell"),
            available=available,
            detail=None if available else f"{harness_id} not on PATH",
        )

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        yield HarnessTurn(kind="text", text="ok")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_only_available_harnesses_become_tools() -> None:
    registry = HarnessRegistry(
        [StubHarness("codex"), StubHarness("claude-code", available=False)]
    )

    fleet = await build_fleet(
        registry=registry, policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
    )

    assert fleet.available_ids == ("codex",)
    names = [t.name for t in fleet.orchestrator.tools if isinstance(t, AgentTool)]
    assert names == ["run_codex"]


@pytest.mark.asyncio
async def test_a_hyphenated_id_becomes_a_legal_function_name() -> None:
    registry = HarnessRegistry([StubHarness("claude-code")])

    fleet = await build_fleet(
        registry=registry, policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
    )

    assert [t.name for t in fleet.orchestrator.tools] == ["run_claude_code"]


@pytest.mark.asyncio
async def test_one_governance_instance_is_shared_by_every_harness() -> None:
    """The central claim: the rules do not vary by which worker was picked."""
    registry = HarnessRegistry([StubHarness("codex"), StubHarness("claude-code")])

    fleet = await build_fleet(
        registry=registry, policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
    )

    assert fleet.app.plugins == [fleet.governance]
    assert len(fleet.orchestrator.tools) == 2
    # include_plugins is what routes an AgentTool call through the app's
    # plugins. With it off, the gate would never see the dispatch and the
    # fleet would be ungoverned while still looking governed.
    assert all(t.include_plugins for t in fleet.orchestrator.tools)
    # One audit trail and one precedent store, not one per harness: a
    # precedent set while one harness ran must apply when a different harness
    # asks the same question later.
    assert len(fleet.app.plugins) == 1
    assert fleet.governance.precedents is fleet.app.plugins[0].precedents


@pytest.mark.asyncio
async def test_the_instruction_names_what_is_there_and_what_is_not() -> None:
    registry = HarnessRegistry(
        [StubHarness("codex"), StubHarness("claude-code", available=False)]
    )

    fleet = await build_fleet(
        registry=registry, policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
    )

    instruction = fleet.orchestrator.instruction
    assert "run_codex" in instruction
    assert "claude-code is not installed here" in instruction
    assert "/work/repo" in instruction
    # A blocked call is a decision, not a retryable failure.
    assert "Do not retry it" in instruction


@pytest.mark.asyncio
async def test_a_fleet_with_no_workers_fails_at_build_time() -> None:
    registry = HarnessRegistry([StubHarness("codex", available=False)])

    with pytest.raises(RuntimeError, match="no coding-agent harness is available"):
        await build_fleet(
            registry=registry, policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
        )


@pytest.mark.asyncio
async def test_an_empty_registry_fails_the_same_way() -> None:
    with pytest.raises(RuntimeError, match="none registered"):
        await build_fleet(
            registry=HarnessRegistry(), policy=AllowAll(), scope=SCOPE, cwd="/work/repo"
        )
