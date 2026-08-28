# Getting started

For the npm launcher, install Git, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
uv manages its own Python runtime. For the Python example below, also use
Python 3.12+ in a virtual environment.

```bash
mkdir -p .adk-harness-sandbox
npm install -g github:Davedat-110105/adk-harness
npm install -g @openai/codex
codex login
adk-harness --help
adk-harness doctor
```

The npm launcher is isolated from your Python environment. Install the library
in your Python 3.12+ virtual environment before running this example:

```bash
python -m pip install 'adk-harness @ git+https://github.com/Davedat-110105/adk-harness.git'
```

For the Gemini orchestrator, configure an existing Google Cloud project with
billing and the Vertex AI API enabled. This example makes paid model calls;
it does not deploy anything. Codex login and Google authentication are separate.

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_ENTERPRISE=true
```

Save this as `first_fleet.py`, then run `python first_fleet.py` from the
directory where you created `.adk-harness-sandbox`. No repository clone is required. It uses
only Codex and a path scoped to the disposable directory:

```python
import asyncio
from pathlib import Path

from adk_harness import HarnessRegistry, build_fleet
from adk_harness.coding.adapters import CodexHarness
from coactra import Decision, DecisionOutcome, PolicyRequest, Scope
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

SANDBOX = (Path.cwd() / ".adk-harness-sandbox").resolve()

class SandboxPolicy:
    async def check(self, request: PolicyRequest) -> Decision:
        cwd = Path(str(request.context.get("cwd") or ".")).resolve()
        outcome = DecisionOutcome.allow if SANDBOX in (cwd, *cwd.parents) else DecisionOutcome.deny
        return Decision(outcome=outcome, reason="scoped disposable sandbox", source="example")

async def main() -> None:
    fleet = await build_fleet(
        registry=HarnessRegistry([CodexHarness()]),
        policy=SandboxPolicy(),
        scope=Scope(tenant_id="example", namespace="first-fleet"),
        cwd=str(SANDBOX),
    )
    print("available:", fleet.available_ids)
    service = InMemorySessionService()
    runner = Runner(app=fleet.app, session_service=service)
    await service.create_session(app_name=fleet.app.name, user_id="u", session_id="s")
    message = types.Content(role="user", parts=[types.Part(
        text="List the files here; do not edit anything or run destructive commands."
    )])
    async for event in runner.run_async(user_id="u", session_id="s", new_message=message):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)

asyncio.run(main())
```

The prompt asks for a read only operation, but the Codex sandbox and permissions
remain responsible for its inner commands. A prompt is not a security boundary.
Held actions have not run; only a trusted host can record a human answer.
