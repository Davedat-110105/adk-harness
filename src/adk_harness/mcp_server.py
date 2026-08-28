"""Expose governed harnesses to any MCP client — Antigravity, Codex, Claude Code.

Run this and the harnesses on your machine become tools inside your editor,
each one passing the same Coactra policy gate before it does anything.

    python -m adk_harness.mcp_server

There is no orchestrator here on purpose. The MCP client already has a model —
that is what you are typing into. Adding a second one would mean paying for a
model to decide which harness to use, when the model you are already talking to
can decide that itself. What this adds is the gate, the audit trail and the
precedent loop, which the client does not have.

Antigravity reads `~/.gemini/config/mcp_config.json`:

    {"mcpServers": {"adk-harness": {
        "command": "/path/to/.venv/bin/python",
        "args": ["-m", "adk_harness.mcp_server"],
        "env": {"ADK_HARNESS_WORKSPACE": "/path/to/repo"}}}}

Antigravity itself is deliberately not offered as a tool. You are already inside
it; handing it back to itself would be a loop with a bill attached.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.governance import CoactraGovernance
from adk_harness.registry import HarnessRegistry
from adk_harness.stores import SQLitePrecedentStore

__all__ = ["build_server", "main"]

WORKSPACE = Path(os.environ.get("ADK_HARNESS_WORKSPACE", Path.cwd())).resolve()
PRECEDENTS = os.environ.get(
    "ADK_PRECEDENTS", str(Path.home() / ".adk-harness-precedents.db")
)

NEVER = ("secret", "secrets", "credential", "credentials", "password", "passwords")
NEVER_PHRASES = ("api key", "access token", "auth token", ".env")
ASK_FIRST = ("delete", "remove", "force", "push", "publish", "deploy", "rm")


def _words(text: str) -> set[str]:
    return set("".join(c if c.isalnum() else " " for c in text.lower()).split())


class EditorPolicy:
    """Read and edit inside the workspace. Destructive work asks first.

    Whole words, not substrings: an earlier version matched "token" anywhere and
    refused ordinary prose that happened to use the word. A gate that fires on
    text it does not understand trains people to click past it.
    """

    def __init__(self, root: Path) -> None:
        self._root = str(root)

    async def check(self, request: PolicyRequest) -> Decision:
        args = request.context.get("tool_args") or {}
        text = " ".join(str(v) for v in args.values() if isinstance(v, str)).lower()
        words = _words(text)

        hit = next((w for w in NEVER if w in words), None) or next(
            (p for p in NEVER_PHRASES if p in text), None
        )
        if hit is not None:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"The instruction asks about {hit!r}. Not by an agent.",
                source="editor-policy",
            )

        risky = next((w for w in ASK_FIRST if w in words), None)
        if risky is not None:
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"The instruction says {risky!r}, which is hard to undo.",
                source="editor-policy",
            )

        return Decision(
            outcome=DecisionOutcome.allow,
            reason=f"Ordinary work under {self._root}.",
            source="editor-policy",
        )


class _Tool:
    """The shape `before_tool_callback` expects, without an ADK runtime."""

    def __init__(self, name: str) -> None:
        self.name = name


class _Context:
    """Records a confirmation request instead of pausing an ADK run.

    An MCP client has no confirmation channel, so the tool returns the question
    as its result and the person answers by saying so in the editor. That is
    honest: the work has not happened, and the transcript says why.
    """

    def __init__(self) -> None:
        self.asked: list[str] = []

    def request_confirmation(self, *, hint: str, payload: dict[str, Any]) -> None:
        self.asked.append(hint)


def build_server(registry: HarnessRegistry, gate: CoactraGovernance) -> Any:
    """One MCP tool per available harness, each behind the gate."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("adk-harness")

    def _register(harness_id: str) -> None:
        async def run(instruction: str, cwd: str = str(WORKSPACE)) -> str:
            tool = _Tool(f"run_{harness_id}")
            context = _Context()
            blocked = await gate.before_tool_callback(
                tool=tool, tool_args={"instruction": instruction, "cwd": cwd},
                tool_context=context,
            )
            if blocked is not None:
                status = blocked.get("status")
                reason = blocked.get("reason")
                if status == "awaiting_confirmation":
                    return (
                        f"HELD FOR APPROVAL — nothing has run.\n\n{reason}\n\n"
                        "If you approve, say so and I will record it as a "
                        "precedent so this exact question is not asked again."
                    )
                return f"BLOCKED by policy — nothing has run.\n\n{reason}"

            harness = registry.get(harness_id)
            lines: list[str] = []
            async for turn in harness.run(instruction, cwd=cwd):
                if turn.kind == "text" and turn.text:
                    lines.append(turn.text)
                elif turn.kind == "tool_call":
                    lines.append(f"[{turn.tool_name}]")
                elif turn.kind == "error" and turn.text:
                    lines.append(f"[error] {turn.text}")
            await harness.aclose()
            return "\n".join(lines) or "(the harness produced no output)"

        run.__name__ = f"run_{harness_id}"
        run.__doc__ = (
            f"Delegate a coding task to {harness_id}, under policy. "
            "Give a complete instruction; it cannot see this conversation."
        )
        server.tool()(run)

    for spec in registry.specs():
        # Antigravity is excluded: you are already talking to it.
        if spec.available and spec.id != "antigravity":
            _register(spec.id)

    @server.tool()
    async def governance_audit() -> str:
        """Every policy decision this session, oldest first."""
        if not gate.audit:
            return "No decisions yet."
        return "\n".join(
            f"{r.at_utc:%H:%M:%S}  {r.tool_name:<18} {r.outcome:<22} {r.reason or ''}"
            for r in gate.audit
        )

    @server.tool()
    async def remember_decision(
        harness: str, precedent_id: str, rationale: str, confirmed_by: str = "user"
    ) -> str:
        """Record an approval so the same question is not asked again.

        The scope is one harness, deliberately narrow. A casual "yes, fine"
        must not silently widen into a standing permission, so anything broader
        is written by hand rather than inferred from an answer.
        """
        from adk_harness.precedent import Applicability

        try:
            precedent = gate.remember(
                tool_name=f"run_{harness}",
                precedent_id=precedent_id,
                applicability=(Applicability("tool", "eq", f"run_{harness}"),),
                decision={"approve": True},
                rationale=rationale,
                confirmed_by=confirmed_by,
            )
        except KeyError:
            return (
                f"No question is outstanding for {harness}. Precedents are "
                "recorded in answer to something, not in advance."
            )
        return (
            f"Recorded {precedent.precedent_id}: {precedent.rationale}\n"
            f"Scope: run_{harness}. Saved to {PRECEDENTS}."
        )

    return server


async def _registry() -> HarnessRegistry:
    """Every harness present on this machine, discovered concurrently.

    The point of this server is choosing between models from inside one editor,
    so it offers all of them rather than a favourite. One that is not installed
    reports `available=False` and is simply not exposed as a tool — no error, no
    entry the model can call and fail.
    """
    from adk_harness.adapters import (
        ClaudeCodeHarness,
        CodexHarness,
        OpenCodeHarness,
    )

    registry = HarnessRegistry(
        [CodexHarness(), ClaudeCodeHarness(), OpenCodeHarness()]
    )
    await registry.discover_all()
    return registry


def main() -> None:
    registry = asyncio.run(_registry())
    gate = CoactraGovernance(
        policy=EditorPolicy(WORKSPACE),
        scope=Scope(tenant_id="local", namespace="editor"),
        principal=f"user:{os.environ.get('USER', 'local')}",
        precedents=SQLitePrecedentStore(PRECEDENTS),
        resources={f"run_{s.id}": str(WORKSPACE) for s in registry.specs()},
    )
    build_server(registry, gate).run()


if __name__ == "__main__":
    main()
