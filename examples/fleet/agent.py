"""A deployable governed fleet.

This is what `adk deploy cloud_run --with_ui ./examples/fleet` ships, and what
`adk web ./examples` serves locally. ADK imports this module and reads `app` off
it, so the fleet is built at import time.

    adk web examples
    adk deploy cloud_run --project=$GOOGLE_CLOUD_PROJECT \
        --region=us-central1 --with_ui ./examples/fleet

Requires `GOOGLE_GENAI_USE_ENTERPRISE=true`, `GOOGLE_CLOUD_PROJECT`, and
`GOOGLE_CLOUD_LOCATION=global` — `gemini-3.5-flash` resolves only on `global`.

The policy below is the interesting part, so read it before the wiring.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.adapters import ClaudeCodeHarness, CodexHarness
from adk_harness.fleet import build_fleet_sync
from adk_harness.protocol import HarnessSpec, HarnessTurn
from adk_harness.registry import HarnessRegistry

WORKSPACE = os.environ.get("ADK_HARNESS_WORKSPACE", "/workspace")

# Matched against the instruction the orchestrator writes, not against a path:
# see WorkspacePolicy.check for why the path alone cannot decide anything here.
SENSITIVE = ("prod", "deploy", "infra", "migration", "release")
FORBIDDEN = ("secret", "credential", "api key", "password", ".env")


def _requested(request: PolicyRequest) -> str:
    """The instruction text the orchestrator wrote for the harness."""
    args = request.context.get("tool_args") or {}
    if not isinstance(args, dict):
        return ""
    return " ".join(str(v) for v in args.values() if isinstance(v, str))


class WorkspacePolicy:
    """Source is fair game; anything that smells like production asks a human.

    This is a deliberately small policy, because the point of the demo is not
    the rule — it is what happens after the rule says "ask". The first time a
    human answers, `governance.remember()` turns that answer into a precedent,
    and the same question stops being asked. See `precedent.py`.

    Three outcomes, and the middle one is the one that matters:

    - `allow`      — dispatch proceeds.
    - `requires_approval` — the run pauses and a human is asked, unless a
      precedent already covers it.
    - `deny`       — the model is told why, and told not to route around it.
    """

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace

    async def check(self, request: PolicyRequest) -> Decision:
        resource = request.resource

        if not resource.startswith(self._workspace):
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"{resource} is outside the workspace {self._workspace}. "
                    "This fleet only works inside the repository it was given."
                ),
                source="workspace-policy",
            )

        # A fleet dispatch resolves to the fleet's working directory, which is
        # the same string every time — so a rule that reads only `resource`
        # would answer identically for every request, which is not a policy.
        # What varies is the instruction the orchestrator wrote, and that is
        # what a reviewer would actually read before approving. Coactra puts
        # the tool arguments on the request context for exactly this.
        target = _requested(request).lower()

        forbidden = next((word for word in FORBIDDEN if word in target), None)
        if forbidden is not None:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=(
                    f"The instruction mentions {forbidden!r}. Credentials are "
                    "never edited by an agent in this workspace."
                ),
                source="workspace-policy",
            )

        sensitive = next((word for word in SENSITIVE if word in target), None)
        if sensitive is not None:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=(
                    f"The instruction mentions {sensitive!r}, which reads as "
                    "production configuration. A human decides this one."
                ),
                source="workspace-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"Ordinary source work under {self._workspace}.",
            source="workspace-policy",
        )


class DemoHarness:
    """A harness that describes the change instead of making it.

    A Cloud Run container has no `codex` binary and no `claude` binary, so a
    deployment registering only real harnesses would fail to build a fleet at
    all. This one is always available, which keeps the hosted demo about the
    thing it is meant to demonstrate — the gate, the pause, and the precedent —
    rather than about which CLIs happen to be installed in a container.

    It is a stub and says so. Running the example locally picks up the real
    harnesses alongside it.
    """

    def __init__(self) -> None:
        self.spec = HarnessSpec(
            id="demo",
            version="stub",
            capabilities=("edit", "explain"),
            available=True,
            detail="Describes the change it would make; never writes to disk.",
        )

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        yield HarnessTurn(
            kind="text",
            text=(
                f"(demo harness) In {cwd} I would: {prompt}\n"
                "No file was written — this stub exists so the hosted demo runs "
                "without a coding-agent CLI installed."
            ),
        )

    async def aclose(self) -> None:
        return None


registry = HarnessRegistry([DemoHarness(), CodexHarness(), ClaudeCodeHarness()])

fleet = build_fleet_sync(
    registry=registry,
    policy=WorkspacePolicy(WORKSPACE),
    scope=Scope(tenant_id="demo", namespace="fleet"),
    cwd=WORKSPACE,
    principal="user:demo",
    name="governed_fleet",
)

app = fleet.app
governance = fleet.governance
