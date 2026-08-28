"""Codex subprocess adapter for `codex exec --json` and session resume.

Prompts go through stdin. JSONL item events become text or tool activity;
turn completion/failure events supply usage or errors. Original payloads stay
in raw. Captured event coverage lives in tests/coding/adapters/test_codex_capture.py.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

__all__ = ["CodexHarness"]

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")

_TEXT_TYPES = frozenset({"agent_message", "agent_reasoning"})
_TOOL_CALL_TYPES = frozenset(
    {"exec_command_begin", "mcp_tool_call_begin", "patch_apply_begin", "web_search_begin"}
)
_TOOL_RESULT_TYPES = frozenset(
    {"exec_command_end", "mcp_tool_call_end", "patch_apply_end", "web_search_end"}
)
_USAGE_TYPES = frozenset({"token_count"})
_ERROR_TYPES = frozenset({"error", "stream_error", "turn_aborted"})

# Ignore known startup warnings; nonzero exits are reported separately.
_BENIGN_ERROR_MARKERS = (
    "Under-development features",
    "loading hooks from both",
    "clamping ",
    "Skill descriptions were shortened",
)


def _is_benign(message: str) -> bool:
    return any(marker in message for marker in _BENIGN_ERROR_MARKERS)


def _event_to_turn(event: dict[str, Any]) -> HarnessTurn | None:
    """Map a JSONL item or turn event; ignore lifecycle events without content."""
    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None

    if event_type == "turn.completed":
        usage = event.get("usage")
        if isinstance(usage, dict):
            summary = ", ".join(f"{k}={v}" for k, v in usage.items())
            return HarnessTurn(kind="usage", text=summary, tool_args=dict(usage), raw=event)
        return None

    if event_type == "turn.failed":
        error = event.get("error")
        text = error.get("message") if isinstance(error, dict) else str(error)
        return HarnessTurn(kind="error", text=text or "turn failed", raw=event)

    if event_type not in ("item.started", "item.completed"):
        # thread.started, turn.started and friends carry no content.
        return None

    item = event.get("item")
    if not isinstance(item, dict):
        return None
    item_type = item.get("type")
    args = {k: v for k, v in item.items() if k != "type"}

    if item_type == "agent_message":
        return HarnessTurn(kind="text", text=item.get("text") or "", raw=event)

    if item_type in ("reasoning", "agent_reasoning"):
        text = item.get("text") or item.get("summary") or ""
        return HarnessTurn(kind="text", text=str(text), raw=event) if text else None

    if item_type == "error":
        message = str(item.get("message") or "")
        if _is_benign(message):
            return None
        return HarnessTurn(kind="error", text=message, raw=event)

    if item_type in ("command_execution", "mcp_tool_call", "file_change", "web_search"):
        name = str(item.get("command") or item.get("tool") or item.get("server") or item_type)
        if event_type == "item.started":
            return HarnessTurn(kind="tool_call", tool_name=name, tool_args=args, raw=event)
        text = item.get("aggregated_output") or item.get("output") or item.get("result")
        return HarnessTurn(
            kind="tool_result",
            tool_name=name,
            text=str(text) if text is not None else None,
            tool_args=args,
            raw=event,
        )

    return None


class CodexHarness:
    """Stream recognized JSONL events from a Codex subprocess."""

    def __init__(
        self,
        *,
        binary: str = "codex",
        model: str | None = None,
        sandbox: str | None = None,
        extra_args: Sequence[str] = (),
    ) -> None:
        self._binary = binary
        self._model = model
        self._sandbox = sandbox
        self._extra_args = tuple(extra_args)
        self._active_processes: list[asyncio.subprocess.Process] = []
        self.spec = HarnessSpec(id="codex", version="unknown", available=False)

    async def discover(self) -> HarnessSpec:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except OSError as exc:
            # FileNotFoundError (binary absent) is the common case, but any
            # OSError here means the harness is not usable on this machine
            # (permissions, a broken symlink, ...). CONTRACT.md rule 3 says
            # discover() must not raise for a "missing, broken, or
            # unauthenticated" harness, so all of these degrade to
            # available=False rather than propagating.
            self.spec = HarnessSpec(
                id="codex",
                version="unknown",
                available=False,
                detail=f"{self._binary!r} could not be run: {exc}",
            )
            return self.spec

        if proc.returncode != 0:
            self.spec = HarnessSpec(
                id="codex",
                version="unknown",
                available=False,
                detail=f"{self._binary} --version exited {proc.returncode}: "
                f"{stderr.decode(errors='replace').strip()}",
            )
            return self.spec

        text = stdout.decode(errors="replace").strip()
        match = _VERSION_RE.search(text)
        version = match.group(1) if match else text or "unknown"
        self.spec = HarnessSpec(
            id="codex",
            version=version,
            capabilities=("text", "tool_call", "tool_result", "usage", "session_resume"),
            available=True,
            detail=text or None,
        )
        return self.spec

    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        return self._run(prompt, cwd=cwd, session_id=session_id)

    def _args(self, cwd: str, session_id: str | None) -> list[str]:
        args: list[str] = ["exec"]
        resuming = session_id is not None
        if resuming:
            args += ["resume", session_id]
        args += ["--json"]
        # Resume inherits cwd from the subprocess; the CLI rejects -C there.
        if not resuming:
            args += ["-C", cwd]
        if self._model is not None:
            args += ["-m", self._model]
        if self._sandbox is not None:
            args += ["-s", self._sandbox]
        args += [*self._extra_args, "-"]
        return args

    async def _run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> AsyncIterator[HarnessTurn]:
        args = self._args(cwd, session_id)

        process = await asyncio.create_subprocess_exec(
            self._binary,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_processes.append(process)

        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            assert process.stderr is not None
            async for line in process.stderr:
                stderr_chunks.append(line)

        stderr_task = asyncio.ensure_future(_drain_stderr())

        try:
            assert process.stdin is not None
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

            assert process.stdout is not None
            async for raw_line in process.stdout:
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # `--json` mode should only emit structured lines; a
                    # malformed one carries no reliable content to surface,
                    # so it is dropped rather than force-fitted into `text`.
                    continue
                turn = _event_to_turn(event) if isinstance(event, dict) else None
                if turn is not None:
                    yield turn

            returncode = await process.wait()
            await stderr_task
            if returncode != 0:
                stderr_text = b"".join(stderr_chunks).decode(errors="replace").strip()
                yield HarnessTurn(
                    kind="error",
                    text=stderr_text or f"codex exec exited {returncode}",
                    raw={"returncode": returncode, "stderr": stderr_text},
                )
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
            if process in self._active_processes:
                self._active_processes.remove(process)
            if process.returncode is None:
                await self._terminate(process)

    async def aclose(self) -> None:
        processes, self._active_processes = self._active_processes, []
        for process in processes:
            await self._terminate(process)

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
