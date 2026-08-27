# adk-harness — design contract

**One sentence:** an installable Python SDK that turns any coding-agent harness
(Claude Code, Codex, opencode) into a governed Google ADK agent, so a Gemini
orchestrator can route work across a fleet of them under one policy.

Not a web app. Not a hosted service. A library you `pip install` and import.

**Hackathon:** Devpost "All Things Agentic", Fortified Enterprise Fleet track,
deadline 2026-08-31 17:00 PDT.

---

## 1. Why this wins the Fleet track

The track asks for "a scalable network of institutional agents that hook into
official enterprise infrastructure", and names the components it wants to see.
Every one of them has a home here:

| Track component | What `adk-harness` provides |
|---|---|
| Agent Registry — publishing, versioning, discovering approved agents | `HarnessRegistry`: which harnesses are installed, at what version, with what capabilities |
| Agent Runtime — long-running async background execution | Vertex AI **Agent Engine** via `VertexAiSessionService`; each harness is an ADK `BaseAgent` inside the runner |
| Memory Bank — persistent secure cross-session context | Vertex AI **Memory Bank** via `VertexAiMemoryBankService`, keyed on a real Agent Engine |
| Agent Identity — zero-trust access control | Coactra `Scope` on every request; `google-adk[agent-identity]` extra |
| Agent Gateway — unified routing and policy enforcement | One Gemini orchestrator routes to harnesses; one `BasePlugin` gates every tool call |
| Model Armor — inline guardrails | The same plugin denies or pauses before any harness touches a repo |
| Observability — OpenTelemetry audit logs and reasoning traces | ADK's OTel output plus a per-decision policy audit record |

The differentiator is honest and narrow: **heterogeneous coding agents,
governed uniformly.** Claude Code, Codex, and opencode have nothing in common —
an SDK, a CLI, and an HTTP server respectively. Making all three obey one policy
gate is the engineering claim, and the three different integration shapes are
what make the adapter protocol a real abstraction rather than a wrapper around
one vendor.

## 2. Proven foundation

The governance seam is already built and executed against live Vertex
(2026-08-24). Reference implementation:
`../coactra/design/2026-08-24-devpost-reference-plugin.py`.

```
TOOL CALL: refund {'amount_usd': 25}
MODEL: I'm sorry, but the refund request for $25 was blocked due to a policy denial.
POLICY DECISIONS: [('refund', 'deny')]
```

Gemini 3.5 Flash called a tool, the Coactra policy plugin denied it, the model
relayed the reason. That is the whole architecture in one class.

## 3. Verified API facts — build against these, not against memory

Introspected from installed packages on 2026-08-24. Do not substitute
recollection for anything in this table.

| Fact | Value |
|---|---|
| ADK version | `google-adk` 2.7.1, Python >=3.10 |
| Custom agent override point | `BaseAgent._run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]` |
| Agent-as-tool | `AgentTool(agent, skip_summarization=False, *, include_plugins=True, propagate_grounding_metadata=False)` — **`include_plugins` defaults True, so the governance plugin applies to agent-as-tool calls** |
| Plugin base | `google.adk.plugins.base_plugin.BasePlugin`, 15 hooks, all async |
| Tool gate | `async before_tool_callback(self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext) -> dict \| None` — return `None` to allow, return a dict to block and substitute that dict as the tool result |
| Human-in-the-loop | `Context.request_confirmation(*, hint: str \| None = None, payload: Any \| None = None)`, plus `interrupt_ids`, `resume_inputs`, `attempt_count` |
| Memory write | `async Context.add_memory(*, memories: Sequence[MemoryEntry], custom_metadata=None)` |
| Sessions | `DatabaseSessionService(db_url=..., db_engine=...)` — needs `google-adk[db]`, plain SQLAlchemy |
| Runner | `Runner(*, app=, app_name=, agent=, plugins=[], session_service=, memory_service=, artifact_service=)` |
| A2A | `to_a2a` and `RemoteA2aAgent` exist but need `google-adk[a2a]` |
| Useful extras | `a2a`, `agent-identity`, `antigravity`, `db`, `e2b`, `daytona`, `gcp`, `eval` |
| Coactra policy | `async Policy.check(request: PolicyRequest) -> Decision`. **There is no `Policy.evaluate`.** |
| PolicyRequest fields | `principal`, `action`, `resource`, `scope`, `component`, `context` |
| Decision fields | `outcome`, `allowed`, `reason`, `source`, `metadata` |
| DecisionOutcome | `allow`, `deny`, `requires_approval` |
| Coactra constructors | `Policy.permissive()`, `Policy.default_deny()`, `Policy.observed(...)`, `Policy.from_authorizer(...)` |
| Claude Code SDK | `claude-agent-sdk` 0.2.144 on PyPI |
| Codex | `codex-cli` 0.146.1, installed locally, `gpt-5.6-luna` configured |
| opencode | headless HTTP server (`opencode serve`) exposing an OpenAPI 3.1 spec |

### Gemini model constraint — verified, easy to get wrong

`gemini-3.5-flash` is reachable **only on the `global` Vertex location**. It
returns HTTP 404 in `us-central1`, while `gemini-2.5-flash` works in both — so
this fails late, not early. Set `GOOGLE_GENAI_USE_ENTERPRISE=true` (the former `GOOGLE_GENAI_USE_VERTEXAI` is deprecated) and
`GOOGLE_CLOUD_LOCATION=global`, even when the Cloud Run service itself is
deployed to a region.

Project: `model-creek-506520-u4`. Available flash tiers, newest first:
`gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`,
`gemini-3.5-flash-lite`. The rules require "3.5 or newer", so `gemini-3.5-flash`
is the safest literal match.

### Coactra version pin

Depend on `coactra>=0.7.0,<0.8` from PyPI. The published 0.7.0 wheel carries
everything used here — `Policy`, `PolicyRequest`, `Scope`, `Decision`,
`DecisionOutcome` — and the reference implementation was proven against it.

**Ignore `coactra/docs/maintainers/target-architecture.md`.** It describes an
unshipped vNext API where `Policy` is a Protocol with `decide()` and
`PolicyRequest` has different fields. Building against that document will not
compile against the installed package.

## 4. The adapter protocol — the contract everything else depends on

One protocol, three shapes behind it.

```python
# src/adk_harness/protocol.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass(frozen=True)
class HarnessSpec:
    """Static description of a harness. Registry entries are these."""
    id: str                      # "claude-code", "codex", "opencode"
    version: str                 # resolved at discovery time
    capabilities: tuple[str, ...]  # "edit", "run-tests", "review", "search"
    available: bool              # is it actually installed/reachable here

@dataclass(frozen=True)
class HarnessTurn:
    """One streamed step out of a harness, normalized across vendors."""
    kind: str                    # "text" | "tool_call" | "tool_result" | "usage" | "error"
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict | None = None
    raw: object | None = None    # vendor payload, never interpreted by the core

class Harness(Protocol):
    """Every adapter implements exactly this."""
    spec: HarnessSpec
    async def discover(self) -> HarnessSpec: ...
    async def run(self, prompt: str, *, cwd: str, session_id: str | None = None) -> AsyncIterator[HarnessTurn]: ...
    async def aclose(self) -> None: ...
```

Rules the adapters must not break:

1. An adapter **never** decides whether an action is permitted. It streams
   `HarnessTurn`s; the governance plugin decides.
2. An adapter **never** imports another adapter's vendor SDK at module import
   time. Import inside `discover()` so a missing harness degrades to
   `available=False` instead of an ImportError.
3. `raw` is opaque. The core never branches on vendor payload shape.
4. `run()` is an async generator. No adapter buffers a whole session in memory.

### How each shape maps

| Harness | Integration shape | Adapter strategy |
|---|---|---|
| Claude Code | Python SDK (`claude-agent-sdk`) | Call the SDK's streaming query API directly, map its message types onto `HarnessTurn` |
| Codex | CLI subprocess (`codex exec`) | `asyncio.create_subprocess_exec`, parse streamed output, map onto `HarnessTurn`. Note `--sandbox` values: `read-only`, `workspace-write`, `danger-full-access` |
| opencode | HTTP server (`opencode serve`) | Start or attach to the server, drive its OpenAPI endpoints over `httpx`, map SSE events onto `HarnessTurn` |

Three genuinely different shapes. If the protocol survives all three, it is real.

### Deliberately out of scope for v1

Hermes Agent and DeepSeek Harness. Both are general agent runtimes rather than
coding-first agents, and DeepSeek Harness is a v0.1 developer preview that
guarantees breaking changes. Document them in the README roadmap, honestly
labelled as unimplemented. Two deep adapters plus a protocol that provably
generalizes beats five shallow ones.

## 5. Package layout

```
src/adk_harness/
    protocol.py       Harness, HarnessSpec, HarnessTurn   (no vendor imports)
    registry.py       HarnessRegistry — discovery, versioning, capability lookup
    governance.py     CoactraGovernance(BasePlugin) — the policy gate
    agent.py          HarnessAgent(BaseAgent) — wraps one Harness as an ADK agent
    fleet.py          build_fleet(...) — Gemini orchestrator + harness sub-agents
    adapters/
        claude_code.py
        codex.py
        opencode.py
```

`protocol.py` and `registry.py` import nothing vendor-specific. That boundary is
what makes the SDK installable without every harness present.

## 6. Public API — what a user writes

The whole point is that this is short. If the quickstart does not fit on one
screen, the design failed.

```python
from adk_harness import build_fleet
from coactra import Policy

fleet = build_fleet(
    policy=Policy.default_deny(),
    model="gemini-3.5-flash",
    harnesses=["claude-code", "codex"],
)

async for turn in fleet.run("Fix the failing tests in ./api", cwd="./api"):
    print(turn)
```

`build_fleet` returns something with a `Runner` behind it, the governance plugin
already installed, and one ADK sub-agent per available harness.

## 7. Build order

Strictly sequential at the start, then parallel.

0. `protocol.py` — frozen first. Everything depends on it.
1. `governance.py` — port the proven reference plugin.
2. `registry.py` + `agent.py` — discovery and the ADK `BaseAgent` wrapper.
3. **Parallel from here:** `adapters/claude_code.py`, `adapters/codex.py`,
   `adapters/opencode.py`. Independent once step 0 is frozen.
4. `fleet.py` — the Gemini orchestrator that routes across whatever registered.
5. README with spin-up instructions, a Mermaid architecture diagram, and the
   roadmap section naming Hermes and DeepSeek Harness as unimplemented.

## 8. Demo strategy for a library

A library is harder to demo than a web app, and the rules want to see the agent
working. Three things carry it:

1. `adk web` against an example fleet — ADK's own dev UI, no frontend to build.
2. A terminal run showing Gemini routing one task to Claude Code and a different
   task to Codex, with the policy gate pausing for approval on a destructive
   edit. This is the money shot: two different vendors, one policy.
3. Cloud Run deployment of the example fleet via `adk deploy cloud_run --with_ui`,
   shown in the Cloud Run dashboard, to satisfy "proof it runs on Google Cloud".

The submission itself remains the library. The deployment is evidence, not the
product.
