"""Expose governed harnesses to any MCP client — Antigravity, Codex, Claude Code.

Run this and the harnesses on your machine become tools inside your editor,
each one passing the same Coactra policy gate before it does anything.

    python -m adk_harness.mcp.server

There is no orchestrator here on purpose. The MCP client already has a model —
that is what you are typing into. Adding a second one would mean paying for a
model to decide which harness to use, when the model you are already talking to
can decide that itself. What this adds is the gate, the audit trail and the
precedent loop, which the client does not have.

Antigravity reads `~/.gemini/config/mcp_config.json`:

    {"mcpServers": {"adk-harness": {
        "command": "/path/to/.venv/bin/python",
        "args": ["-m", "adk_harness.mcp.server"],
        "env": {"ADK_HARNESS_WORKSPACE": "/path/to/repo"}}}}

Antigravity itself is deliberately not offered as a tool. You are already inside
it; handing it back to itself would be a loop with a bill attached.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from coactra import Decision, DecisionOutcome, PolicyRequest, Scope

from adk_harness.coding.registry import HarnessRegistry
from adk_harness.governance import CoactraGovernance

__all__ = ["build_server", "main"]

WORKSPACE = Path(os.environ.get("ADK_HARNESS_WORKSPACE", Path.cwd())).resolve()

NEVER = ("secret", "secrets", "credential", "credentials", "password", "passwords")
NEVER_PHRASES = ("api key", "access token", "auth token", ".env")
ASK_FIRST = ("delete", "remove", "force", "push", "publish", "deploy", "rm")

# Named, not inherited. CalendarToolset alone offers 38 operations including
# ACL changes; a plugin should hold only what somebody decided to give it.
DEFAULT_TOOLS = (
    "calendar_events_list,calendar_events_get,calendar_events_insert,"
    "calendar_events_update,gmail_users_drafts_list,gmail_users_drafts_get,"
    "gmail_users_drafts_create"
)
WORKSPACE_READ_ALLOWLIST = frozenset(
    name for name in DEFAULT_TOOLS.split(",") if name.endswith(("_list", "_get"))
)


def _words(text: str) -> set[str]:
    return set("".join(c if c.isalnum() else " " for c in text.lower()).split())


WRITE_VERBS = (
    "insert",
    "create",
    "update",
    "delete",
    "patch",
    "move",
    "import",
    "trash",
    "modify",
    "batch",
    "send",
)


class EditorPolicy:
    """Reads flow. Anything other people will see asks a person. Sharing is refused.

    Two rules learned the hard way. Whole words, not substrings: an earlier
    version matched "token" anywhere and refused ordinary prose. And it fails
    closed — an operation matching no known verb asks rather than proceeds,
    because a first version omitted "create" from the write list and a Gmail
    draft was written to a real mailbox judged as "only reads".
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def check(self, request: PolicyRequest) -> Decision:
        tool = request.resource.removeprefix("tool:")
        args = request.context.get("tool_args") or {}
        if (tool.startswith("run_") or "cwd" in args) and _canonical_cwd(
            args.get("cwd", request.context.get("cwd")), self._root
        ) is None:
            return Decision(
                outcome=DecisionOutcome.deny,
                reason=f"cwd must be an existing directory under {self._root}.",
                source="editor-policy",
            )

        # Google Workspace operations are judged on the operation itself.
        if tool.startswith(("calendar_", "gmail_", "docs_", "sheets_")):
            if "acl" in tool or "settings" in tool or "permission" in tool:
                return Decision(
                    outcome=DecisionOutcome.deny,
                    reason=(
                        f"{tool} changes who can access this data. Access is "
                        "granted by a person, never by an agent."
                    ),
                    source="editor-policy",
                )
            if "send" in tool:
                return Decision(
                    outcome=DecisionOutcome.deny,
                    reason=(
                        f"{tool} delivers mail to real people and cannot be "
                        "undone. This fleet drafts; a person sends."
                    ),
                    source="editor-policy",
                )
            operation = tool.rsplit("_", 1)[-1]
            if tool in WORKSPACE_READ_ALLOWLIST:
                return Decision(
                    outcome=DecisionOutcome.allow,
                    reason=f"{tool} only reads.",
                    source="editor-policy",
                )
            if operation in WRITE_VERBS:
                return Decision(
                    outcome=DecisionOutcome.requires_approval,
                    reason=f"{tool} creates or changes something others will see.",
                    source="editor-policy",
                )
            return Decision(
                outcome=DecisionOutcome.requires_approval,
                reason=f"{tool} is not a known read operation. A person should look.",
                source="editor-policy",
            )

        return await self._check_harness(request)

    async def _check_harness(self, request: PolicyRequest) -> Decision:
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
            outcome=DecisionOutcome.requires_approval,
            reason=f"Ordinary work under {self._root}.",
            source="editor-policy",
        )


def _canonical_cwd(value: Any, root: Path = WORKSPACE) -> Path | None:
    """Resolve a run directory and reject missing, non-directory, or escaping paths."""
    if not isinstance(value, str) or not value:
        return None
    try:
        candidate = Path(value).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_dir() else None


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


async def build_server(registry: HarnessRegistry, gate: CoactraGovernance) -> Any:  # noqa: PLR0915
    """Google Workspace operations, plus any coding harnesses, all behind the gate."""
    from mcp.server.fastmcp import FastMCP

    from adk_harness.governance.content_armor import ContentArmor

    server = FastMCP("adk-harness")
    armor = ContentArmor(
        allowed_email_domains=(
            domain
            for domain in os.environ.get("ADK_ALLOWED_DOMAINS", "gmail.com").split(",")
            if domain
        )
    )
    armor = getattr(gate, "armor", None) or armor
    if getattr(gate, "armor", None) is None:
        gate.armor = armor
    ledger = getattr(gate, "ledger", None)
    if ledger is None:
        ledger = _ledger()
        gate.ledger = ledger
    ledger_scope = _ledger_scope(gate)
    await _register_workspace(server, gate)

    def _register(harness_id: str) -> None:
        async def run(instruction: str, cwd: str = str(WORKSPACE)) -> str:
            tool = _Tool(f"run_{harness_id}")
            context = _Context()
            canonical_cwd = _canonical_cwd(cwd, WORKSPACE)
            if canonical_cwd is None:
                blocked = gate.reject_tool_call(
                    tool=tool,
                    tool_args={"instruction": instruction, "cwd": cwd},
                    tool_context=context,
                    reason=f"cwd must be an existing directory under {WORKSPACE}.",
                )
                return f"BLOCKED by policy — nothing has run.\n\n{blocked['reason']}"
            blocked = await gate.before_tool_callback(
                tool=tool,
                tool_args={"instruction": instruction, "cwd": str(canonical_cwd)},
                tool_context=context,
            )
            if blocked is not None:
                status = blocked.get("status")
                reason = blocked.get("reason")
                if status == "awaiting_confirmation":
                    return (
                        f"HELD FOR APPROVAL — nothing has run.\n\n{reason}\n\n"
                        "A trusted host administrator must record any resulting "
                        "precedent through the host API."
                    )
                return f"BLOCKED by policy — nothing has run.\n\n{reason}"

            harness = registry.get(harness_id)
            lines: list[str] = []
            stream_error: str | None = None
            try:
                stream = harness.run(instruction, cwd=str(canonical_cwd))
                try:
                    async for turn in stream:
                        if turn.kind == "text" and turn.text:
                            lines.append(turn.text)
                        elif turn.kind == "tool_call":
                            lines.append(f"[{turn.tool_name}]")
                        elif turn.kind == "error" and turn.text:
                            lines.append(f"[error] {turn.text}")
                            stream_error = turn.text
                finally:
                    close_stream = getattr(stream, "aclose", None)
                    if close_stream is not None:
                        await close_stream()
            except BaseException as exc:
                await gate.on_tool_error_callback(
                    tool=tool,
                    tool_args={"instruction": instruction, "cwd": str(canonical_cwd)},
                    tool_context=context,
                    error=exc,
                )
                raise
            result = {
                "status": "error" if stream_error else "completed",
                "text": "\n".join(lines),
            }
            terminal = await gate.after_tool_callback(
                tool=tool,
                tool_args={"instruction": instruction, "cwd": str(canonical_cwd)},
                tool_context=context,
                result=result,
            )
            if terminal is not None:
                return json.dumps(terminal, default=str)
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
    async def armor_findings() -> str:
        """Show suspicious content or arguments found during this server session."""
        if not armor.findings:
            return "No armor findings this session."
        return json.dumps(armor.findings, ensure_ascii=False)

    @server.tool()
    async def ledger_recent(limit: int = 20) -> str:
        """Show recent executions so a person can verify what the agent did."""
        if ledger is None:
            return "Action ledger is off. Set ADK_LEDGER=1 to enable it."
        try:
            entries = ledger.query(scope=ledger_scope, limit=limit)
        except Exception as exc:  # observability must not break the MCP server
            return f"Action ledger unavailable: {type(exc).__name__}: {exc}"
        if not entries:
            return "No ledger entries yet."
        return json.dumps(entries, default=str, ensure_ascii=False)[:4000]

    return server


async def _register_workspace(
    server: Any,
    gate: CoactraGovernance,
) -> list[str]:
    """Expose Google Workspace operations as governed MCP tools.

    Each operation is its own tool, so the gate judges `calendar_events_insert`
    separately from `calendar_events_list` — which is what the PRD means by
    "the gateway evaluates every tool call; approval at initial dispatch is
    insufficient."

    A service whose scope the credentials do not carry is skipped with a note
    rather than exposed as a tool that would fail. An editor showing a tool that
    always errors is worse than one that shows fewer tools.
    """
    from google.adk.auth.auth_credential import ServiceAccount

    from adk_harness.workspace import SCOPES, TOOLSETS, check_workspace_service_access

    wanted = [
        s.strip() for s in os.environ.get("ADK_SERVICES", "calendar,gmail").split(",") if s.strip()
    ]
    reachable = await check_workspace_service_access(tuple(wanted))
    services = [name for name in wanted if reachable.get(name) is None]
    skipped = {n: why for n, why in reachable.items() if why is not None}

    if skipped:

        @server.tool()
        async def workspace_unavailable() -> str:
            """Why a Google service is not offered here, and how to fix it."""
            return "\n\n".join(f"{n}: {why}" for n, why in skipped.items())

    exposed: list[str] = []
    if not services:
        return exposed

    credential = ServiceAccount(use_default_credential=True, scopes=[SCOPES[n] for n in services])
    allow = [t.strip() for t in os.environ.get("ADK_TOOLS", DEFAULT_TOOLS).split(",")]

    for name in services:
        toolset = TOOLSETS[name](service_account=credential, tool_filter=[t for t in allow if t])
        for tool in await toolset.get_tools():
            _register_workspace_tool(
                server,
                gate,
                tool,
            )
            exposed.append(tool.name)

    return exposed


def _register_workspace_tool(
    server: Any,
    gate: CoactraGovernance,
    tool: Any,
) -> None:
    async def call(arguments: dict[str, Any] | None = None) -> str:
        args = arguments or {}
        context = _Context()
        tool_ref = _Tool(tool.name)
        blocked = await gate.before_tool_callback(
            tool=tool_ref, tool_args=args, tool_context=context
        )
        if blocked is not None:
            status = blocked.get("status")
            if status == "awaiting_confirmation":
                return (
                    f"HELD FOR APPROVAL — nothing has run.\n\n{blocked.get('reason')}\n\n"
                    "A trusted host administrator must record any resulting "
                    "precedent through the host API."
                )
            return f"BLOCKED by policy — nothing has run.\n\n{blocked.get('reason')}"

        try:
            result = await tool.run_async(args=args, tool_context=None)
        except BaseException as exc:
            await gate.on_tool_error_callback(
                tool=tool_ref, tool_args=args, tool_context=context, error=exc
            )
            raise
        terminal = await gate.after_tool_callback(
            tool=tool_ref, tool_args=args, tool_context=context, result=result
        )
        if terminal is not None:
            result = terminal

        return json.dumps(result, default=str)[:4000]

    call.__name__ = tool.name
    call.__doc__ = (
        f"{getattr(tool, 'description', tool.name)}\n\n"
        "Pass parameters in `arguments` using snake_case — `calendar_id`, "
        "`max_results`, `time_min` — not the camelCase of Google's REST docs. "
        "ADK converts them; sending camelCase raises KeyError on the field "
        "name.\n\n"
        "Every call passes the policy gate first."
    )
    server.tool()(call)


def _ledger() -> Any | None:
    """Keep Firestore opt-in so local MCP use has no database side effects."""
    if os.environ.get("ADK_LEDGER") != "1":
        return None
    from adk_harness.governance.ledger import FirestoreActionLedger

    return FirestoreActionLedger(collection="action_ledger")


def _ledger_scope(gate: CoactraGovernance) -> str:
    scope = getattr(gate, "_scope", None)
    return f"{getattr(scope, 'tenant_id', 'local')}:{getattr(scope, 'namespace', 'editor')}"


async def _registry() -> HarnessRegistry:
    """Coding harnesses, when this server is asked to expose them.

    Off by default. The Google surface is the point; coding agents are a second
    concern and adding them silently would double the tool list for people who
    only wanted Workspace. Set ADK_HARNESSES=1 to include whichever are present.
    """
    if os.environ.get("ADK_HARNESSES") != "1":
        return HarnessRegistry([])

    from adk_harness.coding.registry import default_registry

    registry = default_registry(include_antigravity=False)
    await registry.discover_all()
    return registry


def main() -> None:
    registry = asyncio.run(_registry())
    gate = CoactraGovernance(
        policy=EditorPolicy(WORKSPACE),
        scope=Scope(tenant_id="local", namespace="editor"),
        principal=f"user:{os.environ.get('USER', 'local')}",
        resources={f"run_{s.id}": str(WORKSPACE) for s in registry.specs()},
    )
    server = asyncio.run(build_server(registry, gate))
    server.run()


if __name__ == "__main__":
    main()
