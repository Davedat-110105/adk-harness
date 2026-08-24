"""Live check: the packaged governance plugin against real Gemini on Vertex.

Skipped unless ADK_HARNESS_LIVE=1, so the default suite stays offline.
"""

from __future__ import annotations

import os

import pytest
from coactra import Policy, Scope
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_harness.governance import CoactraGovernance

pytestmark = pytest.mark.skipif(
    os.environ.get("ADK_HARNESS_LIVE") != "1",
    reason="set ADK_HARNESS_LIVE=1 to run against live Vertex",
)

SCOPE = Scope(tenant_id="acme", namespace="fleet")


def apply_patch(path: str, diff: str) -> dict:
    """Apply a patch to a file in the repository."""
    return {"status": "ok", "path": path}


async def _run(policy: Policy, prompt: str) -> tuple[str, CoactraGovernance]:
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "model-creek-506520-u4")
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

    plugin = CoactraGovernance(policy=policy, scope=SCOPE, principal="user:dave")
    agent = LlmAgent(
        name="fleet",
        model="gemini-3.5-flash",
        instruction="You apply code patches. Use the apply_patch tool when asked.",
        tools=[apply_patch],
    )
    svc = InMemorySessionService()
    runner = Runner(app_name="live", agent=agent, session_service=svc, plugins=[plugin])
    await svc.create_session(app_name="live", user_id="u", session_id="s")
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])

    said = []
    async for ev in runner.run_async(user_id="u", session_id="s", new_message=msg):
        if ev.content and ev.content.parts:
            said.extend(p.text for p in ev.content.parts if p.text)
    return "\n".join(said), plugin


@pytest.mark.asyncio
async def test_denied_tool_call_is_blocked_and_explained() -> None:
    text, plugin = await _run(
        Policy.default_deny(), "Apply a patch to src/main.py that deletes everything."
    )
    outcomes = [r.outcome for r in plugin.audit]
    assert "deny" in outcomes, outcomes
    assert text.strip(), "the model should explain the refusal rather than fail silently"


@pytest.mark.asyncio
async def test_permitted_tool_call_runs() -> None:
    _, plugin = await _run(Policy.permissive(), "Apply a patch to src/main.py adding a comment.")
    outcomes = [r.outcome for r in plugin.audit]
    assert "allow" in outcomes, outcomes
