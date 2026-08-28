# Examples

## Prerequisites

Use Python 3.12+ and install the project with `pip install -e ".[dev,all]"`.
The orchestrated examples also need Application Default Credentials and a
Vertex project:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_ENTERPRISE=true
```

The local harness examples may run Codex, Claude Code, or opencode processes in
the directory you provide. Their own credentials and permissions apply.

| Example | External side effects |
|---|---|
| `agents/local/agent.py` | Runs selected local harnesses in the workspace; Vertex model call |
| `scripts/run_fleet_on_repository.py` | Runs harnesses in the chosen repository; optional SQLite precedents |
| `agents/fleet/agent.py` | Vertex model calls; available installed harnesses plus fallback stub; deployment only when explicitly requested |
| `agents/workspace/agent.py` | Reads Workspace APIs; writes require policy approval; optional Firestore ledger with `ADK_LEDGER=1` |
| `scripts/workspace_policy_demo.py` | Live run may create a calendar event; prints cleanup instructions and never deletes it |

ADK requires the `agent.py` entry-point name within each agent directory.
Use `adk web examples/agents` to serve these examples locally.

## Minimal adapter cookbook

Adapters implement the frozen `Harness` protocol. Start with a deterministic
echo adapter, then replace its `run()` body with the vendor stream:

| Case | Offline check | Live check |
|---|---|---|
| discovery | fake the vendor import or executable and assert `HarnessSpec` | vendor `--version` or SDK discovery |
| text/tool mapping | feed captured events and assert `HarnessTurn.kind` | one small prompt |
| missing dependency | hide import/PATH and assert `available=False` | unavailable machine |
| close mid-stream | cancel/close the fake stream and assert clean `aclose()` | stop a real session |

No framework is required: a small `asyncio` test with a fake stream covers the
offline matrix, and live checks should be opt-in.

Minimal echo adapter shape (the scaffold produced by `adk-harness
new-adapter demo` contains the same protocol wiring):

```python
from collections.abc import AsyncIterator
from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

class EchoHarness:
    spec = HarnessSpec("echo", "0", ("text",), True)
    async def discover(self): return self.spec
    async def aclose(self) -> None: pass
    async def run(self, prompt: str, *, cwd: str, session_id=None) -> AsyncIterator[HarnessTurn]:
        yield HarnessTurn(kind="text", text=prompt)
```

For a subprocess adapter, keep the process local to the run and clean it up
when the caller closes the stream. This offline example invokes Python, not a
vendor or a shell. Replace its command and event mapping with the vendor's
verified contract; see `src/adk_harness/coding/adapters/codex.py` for JSONL mapping.

```python
import asyncio
import sys
from collections.abc import AsyncIterator
from adk_harness.coding.protocol import HarnessSpec, HarnessTurn

class SubprocessEchoHarness:
    spec = HarnessSpec("subprocess_echo", "0", ("text",), True)

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def run(self, prompt: str, *, cwd: str, session_id=None) -> AsyncIterator[HarnessTurn]:
        # Session continuity is unsupported and session_id is ignored.
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "-c", "import sys; print(sys.argv[1])", prompt,
            cwd=cwd, stdout=asyncio.subprocess.PIPE,
        )
        try:
            async for line in process.stdout:
                yield HarnessTurn(kind="text", text=line.decode().rstrip(), raw=line)
            if await process.wait():
                yield HarnessTurn(kind="error", text="subprocess failed")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def aclose(self) -> None:
        pass  # This teaching example has no shared client; close each run iterator.
```

The production adapter also needs global shutdown of active runs, missing-binary
discovery and vendor-specific errors. Add these when replacing this offline demo.
The matrix above identifies the checks to keep.
