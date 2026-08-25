"""Codex CLI adapter.

Codex has no Python SDK, so this adapter drives the `codex` binary as a
subprocess and parses its streamed JSONL output. Verified against:

    $ codex --version
    codex-cli 0.149.1

    $ codex exec --help          (2026-08-25, codex-cli 0.149.1)
    $ codex exec resume --help   (2026-08-25, codex-cli 0.149.1)

Flags this adapter relies on, confirmed from that `--help` output:

- `codex exec [OPTIONS] [PROMPT]` runs non-interactively. `[PROMPT]` is read
  from stdin when omitted or given as `-`. This adapter always passes `-` and
  writes the prompt to stdin, since prompts may be long or contain characters
  that are awkward as a shell argument.
- `--json` prints one JSON object per line to stdout ("Print events to stdout
  as JSONL"). Without it, `codex exec` prints human-readable text with no
  stable shape to parse, so this adapter always passes `--json`.
- `-C, --cd <DIR>` sets the working root — used for `cwd`.
- `-m, --model <MODEL>` selects the model.
- `-s, --sandbox <SANDBOX_MODE>` takes `read-only`, `workspace-write`, or
  `danger-full-access`.
- `codex exec resume [SESSION_ID] [PROMPT]` resumes a prior session; `PROMPT`
  is read from stdin under the same `-` convention. This adapter uses it
  whenever `run()` is given a `session_id`, so continuity is genuine rather
  than simulated by replaying history into the prompt.

What the JSONL envelope looks like: each line is `{"id": ..., "msg": {"type":
<tag>, ...fields}}`. The `--help` text does not document the payload shape, and
this repository's rules forbid running a real `codex exec` that would call the
API to observe one directly. The envelope shape and the set of `type` tags
below were instead confirmed by extracting the serde tag strings compiled into
the installed 0.149.1 binary itself (`strings` on
`~/.codex/packages/standalone/releases/0.149.1-aarch64-apple-darwin/bin/codex`),
which is how `task_started`/`task_complete`/`agent_message`/`token_count`/
`exec_command_begin`/`exec_command_end`/`mcp_tool_call_begin`/
`mcp_tool_call_end`/`patch_apply_begin`/`patch_apply_end`/`web_search_begin`/
`web_search_end`/`error`/`stream_error`/`turn_aborted`/`session_configured`
were confirmed to be real tags this binary emits. The exact field names inside
each event's payload were **not** confirmed this way — the binary's string
table shows the struct exists but not, without deeper reverse engineering,
which JSON key holds which field. To stay correct even if a guessed field name
is wrong, `_event_to_turn` below never requires a specific key: `raw` always
carries the full `msg` dict untouched (contract rule 4), and `tool_args` for
`tool_call`/`tool_result` turns is the full payload minus `type` rather than a
hand-picked subset, so nothing is silently lost if a field name differs from
what's guessed here. A real `codex exec --json` run (with network access,
outside this task's constraints) against a prompt that triggers a shell
command and an MCP tool call would confirm the payload shapes precisely.

Turn-kind mapping:

| `msg.type`                                             | `HarnessTurn.kind` |
|----------------------------------------------------------|---------------------|
| `agent_message`, `agent_reasoning`                        | `text`              |
| `exec_command_begin`, `mcp_tool_call_begin`, `patch_apply_begin`, `web_search_begin` | `tool_call` |
| `exec_command_end`, `mcp_tool_call_end`, `patch_apply_end`, `web_search_end` | `tool_result` |
| `token_count`                                              | `usage`             |
| `error`, `stream_error`, `turn_aborted`                    | `error`             |
| everything else (`task_started`, `task_complete`, `session_configured`, `*_delta`, banners, heartbeats, ...) | dropped |

`*_delta` events are dropped per CONTRACT.md: they only repeat content that
arrives whole in the corresponding non-delta event. `task_complete` carries
`last_agent_message`, which duplicates the final `agent_message` turn already
yielded, so it is dropped too rather than double-reporting the same text.

Session continuity: `session_id` is honored. When present, `run()` invokes
`codex exec resume <session_id> --json ...` instead of `codex exec --json
...`. This is genuine resume support from the vendor CLI, not simulated.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from adk_harness.protocol import HarnessSpec, HarnessTurn

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

# Candidate keys tried in order to find human-readable text in a payload whose
# exact field names were not confirmed against a live run (see module
# docstring). First match wins; if none match, the payload is stringified.
_TEXT_KEYS = ("message", "text", "reason", "last_agent_message", "delta")

# Candidate keys for a tool/command name.
_NAME_KEYS = ("tool", "name", "command", "server")


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return " ".join(value)
    return None


def _event_to_turn(event: dict[str, Any]) -> HarnessTurn | None:
    """Map one decoded JSONL line onto a `HarnessTurn`, or drop it (None)."""
    msg = event.get("msg")
    if not isinstance(msg, dict):
        return None
    kind_tag = msg.get("type")
    if not isinstance(kind_tag, str):
        return None

    payload_args = {k: v for k, v in msg.items() if k != "type"}

    if kind_tag in _TEXT_TYPES:
        text = _first_str(msg, _TEXT_KEYS) or ""
        return HarnessTurn(kind="text", text=text, raw=event)

    if kind_tag in _TOOL_CALL_TYPES:
        name = _first_str(msg, _NAME_KEYS) or kind_tag
        return HarnessTurn(kind="tool_call", tool_name=name, tool_args=payload_args, raw=event)

    if kind_tag in _TOOL_RESULT_TYPES:
        name = _first_str(msg, _NAME_KEYS) or kind_tag
        text = _first_str(msg, ("stdout", "output", "result", "text"))
        return HarnessTurn(
            kind="tool_result", tool_name=name, text=text, tool_args=payload_args, raw=event
        )

    if kind_tag in _USAGE_TYPES:
        return HarnessTurn(kind="usage", tool_args=payload_args, raw=event)

    if kind_tag in _ERROR_TYPES:
        text = _first_str(msg, _TEXT_KEYS) or kind_tag
        return HarnessTurn(kind="error", text=text, raw=event)

    return None


class CodexHarness:
    """Drive the `codex` CLI as a subprocess and stream its turns.

    `run()` never buffers a whole session: stdout is read line by line as the
    subprocess produces it, and each recognized event is yielded as soon as it
    is decoded.
    """

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
        self._process: asyncio.subprocess.Process | None = None
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

    async def _run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None,
    ) -> AsyncIterator[HarnessTurn]:
        args: list[str] = ["exec"]
        if session_id is not None:
            args += ["resume", session_id]
        args += ["--json", "-C", cwd]
        if self._model is not None:
            args += ["-m", self._model]
        if self._sandbox is not None:
            args += ["-s", self._sandbox]
        args += list(self._extra_args)
        args += ["-"]

        process = await asyncio.create_subprocess_exec(
            self._binary,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = process

        assert process.stdin is not None
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()

        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            assert process.stderr is not None
            async for line in process.stderr:
                stderr_chunks.append(line)

        stderr_task = asyncio.ensure_future(_drain_stderr())

        try:
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
                if not isinstance(event, dict):
                    continue
                turn = _event_to_turn(event)
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
            self._process = None

    async def aclose(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except (TimeoutError, asyncio.TimeoutError):
                process.kill()
                await process.wait()
        self._process = None
