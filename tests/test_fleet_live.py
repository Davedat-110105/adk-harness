"""Live check: a whole governed fleet against real Gemini on Vertex.

`test_governance_live.py` proves the plugin gates a plain ADK tool. This proves
the thing the library actually ships: a Gemini orchestrator choosing a harness,
dispatching to it through `AgentTool`, and that dispatch passing the policy gate.

The harness is a stub. That is deliberate — this test is about the Google side
of the seam, and a stub keeps it runnable on a machine with no coding agent
installed and with no second model's bill attached. The adapters have their own
tests.

Skipped unless ADK_HARNESS_LIVE=1.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from coactra import Policy, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness.fleet import build_fleet
from adk_harness.protocol import HarnessSpec, HarnessTurn
from adk_harness.registry import HarnessRegistry

pytestmark = pytest.mark.skipif(
    os.environ.get("ADK_HARNESS_LIVE") != "1",
    reason="set ADK_HARNESS_LIVE=1 to run against live Vertex",
)

SCOPE = Scope(tenant_id="acme", namespace="fleet")


class EchoHarness:
    """A harness that reports what it was asked to do and stops."""

    def __init__(self, harness_id: str = "echo") -> None:
        self.spec = HarnessSpec(
            id=harness_id,
            version="0.0.1-stub",
            capabilities=("edit", "shell"),
            available=True,
        )
        self.prompts: list[str] = []

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        self.prompts.append(prompt)
        yield HarnessTurn(kind="text", text=f"Applied the change in {cwd}: {prompt}")

    async def aclose(self) -> None:
        return None


def _vertex() -> None:
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "model-creek-506520-u4")
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"


async def _ask(fleet_app, prompt: str) -> str:
    svc = InMemorySessionService()
    runner = Runner(app=fleet_app, session_service=svc)
    await svc.create_session(app_name=fleet_app.name, user_id="u", session_id="s")
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    said: list[str] = []
    async for ev in runner.run_async(user_id="u", session_id="s", new_message=msg):
        if ev.content and ev.content.parts:
            said.extend(p.text for p in ev.content.parts if p.text)
    return "\n".join(said)


@pytest.mark.asyncio
async def test_gemini_dispatches_to_a_harness_through_the_gate() -> None:
    _vertex()
    harness = EchoHarness()
    fleet = await build_fleet(
        registry=HarnessRegistry([harness]),
        policy=Policy.permissive(),
        scope=SCOPE,
        cwd="/work/repo",
    )

    text = await _ask(fleet.app, "Add a docstring to src/main.py. Delegate it.")

    outcomes = [r.outcome for r in fleet.governance.audit]
    assert "allow" in outcomes, outcomes
    assert harness.prompts, "the orchestrator should have dispatched to the harness"
    assert text.strip()


@pytest.mark.asyncio
async def test_a_denied_dispatch_is_explained_and_the_harness_never_runs() -> None:
    """The gate stops the dispatch itself, not just the harness's output."""
    _vertex()
    harness = EchoHarness()
    fleet = await build_fleet(
        registry=HarnessRegistry([harness]),
        policy=Policy.default_deny(),
        scope=SCOPE,
        cwd="/work/repo",
    )

    text = await _ask(fleet.app, "Rewrite the production config in src/main.py.")

    outcomes = [r.outcome for r in fleet.governance.audit]
    assert "deny" in outcomes, outcomes
    assert harness.prompts == [], "a denied dispatch must not reach the harness"
    assert text.strip(), "the model should explain the refusal rather than fail silently"
