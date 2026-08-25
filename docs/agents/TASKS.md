# Open tasks

Each task is written to be done without reading the others. Read
[CONTRACT.md](CONTRACT.md) and [OWNERSHIP.md](OWNERSHIP.md) first.

Every task shares these requirements:

- Python 3.12+, `from __future__ import annotations`, full type annotations.
- Use the repository's virtualenv: `.venv/bin/python`, `.venv/bin/pytest`.
- Docstrings explain *why*, not *what*. Match the voice of `protocol.py` and
  `registry.py` — they are the house style.
- No vendor import at module level (contract rule 2).
- Tests pass with the vendor tool absent.

---

## Task 1 — the Codex adapter

**Owner:** agent-codex-adapter
**Files you write:** `src/adk_harness/adapters/codex.py`,
`tests/test_adapter_codex.py`

Codex has no Python SDK. The adapter drives the `codex` CLI as a subprocess and
parses its streamed output.

**Verify before you write.** Run `codex exec --help` and read it. The flags you
need — non-interactive execution, structured/JSON output, sandbox mode, working
directory, model selection, session resume — must come from that help text, not
from memory. Also check `codex exec resume --help`. Record what you found in the
module docstring, including the CLI version you verified against
(`codex --version`).

Do **not** run a live `codex exec` that calls the API. Discovery via `--version`
is fine; a real model call is not.

**Shape:**

```python
class CodexHarness:
    def __init__(self, *, binary: str = "codex", model: str | None = None,
                 sandbox: str | None = None, extra_args: Sequence[str] = ()) -> None: ...
```

- `discover()` — run `<binary> --version` via `asyncio.create_subprocess_exec`.
  If the binary is missing (`FileNotFoundError`) or exits non-zero, return
  `HarnessSpec(id="codex", version="unknown", available=False, detail=...)`.
  On success parse the version out and set `available=True` with the
  capabilities the adapter genuinely supports.
- `run()` — spawn the CLI with `cwd=cwd`, feed the prompt (stdin if the help
  text says `-` reads stdin), and read stdout line by line as it arrives, using
  `asyncio.subprocess.PIPE`. Never `await process.communicate()`; that buffers
  the whole session and violates contract rule 5.
  - If a structured output mode exists, parse each line as JSON and map events
    onto `HarnessTurn.KINDS`. A line that is not valid JSON is not an error —
    yield it as `kind="text"` or drop it, whichever the format implies.
  - Non-zero exit yields a final `kind="error"` turn carrying stderr. Do not
    raise out of the generator.
  - `session_id`: if `codex exec resume` supports it, use it. If the mapping is
    not clean, ignore the argument and say so in the docstring.
- `aclose()` — terminate a running process if there is one, await it, and be
  safe to call twice.

**Tests** must not invoke the real binary. Patch
`asyncio.create_subprocess_exec` with a fake that yields scripted stdout lines.
Cover: binary missing → `available=False`; version parsed → `available=True`;
each `HarnessTurn.kind` produced from a representative line; non-zero exit →
`error` turn, no exception; `aclose()` mid-stream terminates and is idempotent.

---

## Task 2 — the Claude Code adapter

**Owner:** agent-claude-code-adapter
**Files you write:** `src/adk_harness/adapters/claude_code.py`,
`tests/test_adapter_claude_code.py`

Claude Code has a real Python SDK, so this adapter uses it rather than a
subprocess.

**Verify before you write.** `claude-agent-sdk` is an optional extra and is
**not currently installed in `.venv`**. Install it there first:

```
.venv/bin/pip install claude-agent-sdk
```

Then introspect the installed package — `dir()`, `inspect.getsource()`, read the
files under `.venv/lib/python3.12/site-packages/claude_agent_sdk/` — to learn
the real names of the query entry point, the options object, and the message and
content-block classes. Do not write the adapter from recollection of the SDK's
API; the exact class names and the streaming shape have changed between
versions. Record the version you verified against in the module docstring.

Note that the SDK generally needs the `claude` CLI binary present on the machine
(it is at `/Users/datta/.local/bin/claude` here). `discover()` should account
for both the Python package and the binary.

**Shape:**

```python
class ClaudeCodeHarness:
    def __init__(self, *, model: str | None = None,
                 allowed_tools: Sequence[str] | None = None,
                 permission_mode: str | None = None,
                 system_prompt: str | None = None) -> None: ...
```

- `discover()` — import the SDK inside the method; on `ImportError` return
  `available=False` with the pip hint in `detail`. Read the installed package
  version (`importlib.metadata.version`). Also confirm the CLI binary resolves;
  if it does not, that is `available=False` with a clear `detail`, not a crash.
- `run()` — call the SDK's streaming query with `cwd=cwd`, and translate each
  message and content block into `HarnessTurn`, putting the SDK object in `raw`.
  Assistant text → `text`. Tool-use blocks → `tool_call` with `tool_name` and
  `tool_args`. Tool results → `tool_result`. The final result message's token
  and cost fields → `usage`. Errors → `error`.
  - **Do not set a permissive permission mode by default.** This SDK's own
    permission settings are not the governance layer; `CoactraGovernance` is.
    Default to whatever the SDK's own default is, and let the caller override.
  - `session_id`: use the SDK's resume/continue support if it has one. If not,
    ignore it and document that.
- `aclose()` — close or disconnect the client, idempotent.

**Tests** must pass with the SDK absent as well as present. Inject a fake SDK
module (`sys.modules` patch or a constructor seam) that emits scripted messages.
Cover: SDK missing → `available=False` with a useful `detail`; SDK present →
`available=True`; the full block-to-kind mapping including a tool-use block with
arguments; an error message → `error` turn; `aclose()` idempotent.

---

## Task 3 — `HarnessAgent` *(integrator)*

`src/adk_harness/agent.py`. Wrap any `Harness` as an ADK `BaseAgent` so a
Gemini orchestrator can call it as a sub-agent or as an `AgentTool`, with the
governance plugin in front.

## Task 4 — `build_fleet` *(integrator)*

`src/adk_harness/fleet.py`. A Gemini `LlmAgent` that routes work across the
available harnesses, with one `CoactraGovernance` instance shared by all of
them so the audit trail and the precedent store are common.

---

## Reporting back

When your task is done, report:

1. The files you created, and confirmation you touched nothing else.
2. The exact `pytest` command you ran and its output.
3. What you verified against the machine, and the versions you verified against.
4. Anything you wanted to change in a frozen file but did not.
5. Anything you had to guess, and what would confirm it.
