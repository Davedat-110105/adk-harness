# Resuming an agent after human approval: how other tools solve it

**Question:** an MCP server needs a human to approve a proposed action before it runs. Our
client is Google Antigravity 2.11.0. Its elicitation support is advertised but non-functional
(form and URL modes both decline silently — verified experimentally). Its hook system in this
build registers only `PreToolUse`, `PostToolUse`, and `PreInvocation`; there is no `Stop` or
`PostInvocation` event, so nothing fires after the model finishes a turn. `PostToolUse` fires
*before* the model writes its reply, so blocking there hides the approval card we render.

**Our current design:** the tool returns `"held"` plus a path to an HTML card rendered inline
via `agent-embed`. The model shows the card, then calls a separate `await_approval` tool that
blocks until the person clicks a button, which POSTs to a loopback HTTP server inside the MCP
server process.

This document surveys how six other approaches solve human-in-the-loop (HITL) approval and,
specifically, how each one **resumes the agent** afterward — then asks whether our blocking-tool
approach is the standard answer, or whether something better exists that we could use against
Antigravity today.

Research was gathered by four parallel research passes against official docs, spec text, and
GitHub issues on 2026-08-29. Every claim below is sourced; anything that could not be
independently verified is flagged as such, not stated as fact.

---

## 1. Claude Code hooks

Claude Code's hook system is much larger than the "classic" `PreToolUse`/`PostToolUse` pair, and
it has an event built for exactly the problem we have: continuing an agent *after* it has already
finished a turn.

**Full current event list** (source: [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)):
`SessionStart`, `Setup`, `InstructionsLoaded`, `UserPromptSubmit`, `UserPromptExpansion`,
`MessageDisplay`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PostToolUseFailure`,
`PostToolBatch`, `PermissionDenied`, `Notification`, `SubagentStart`, `SubagentStop`,
`TaskCreated`, `TaskCompleted`, **`Stop`**, `StopFailure`, `TeammateIdle`, `ConfigChange`,
`CwdChanged`, `DirectoryAdded`, `FileChanged`, `WorktreeCreate`/`WorktreeRemove`,
`PreCompact`/`PostCompact`, `PreModelSwitch`/`PostModelSwitch`, `SessionEnd`, `Elicitation`,
`ElicitationResult`. There is no event named `PreInvocation` or `PostInvocation` in Claude
Code's own vocabulary — that naming is specific to Antigravity's hook system.

### The `Stop` hook contract

`Stop` fires "when the main Claude Code agent has finished responding" — i.e. after the model has
already written its reply, which is precisely the moment Antigravity's hook set cannot observe.

Input JSON (verbatim from the docs):

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": true,
  "last_assistant_message": "I've completed the refactoring. Here's a summary...",
  "background_tasks": [
    { "id": "task-001", "type": "shell", "status": "running", "description": "tail logs", "command": "tail -f /var/log/syslog" }
  ],
  "session_crons": [
    { "id": "cron-001", "schedule": "0 9 * * 1-5", "recurring": true, "prompt": "check the build" }
  ]
}
```

Output JSON — the block/continue decision:

```json
{
  "decision": "block",
  "reason": "Must be provided when Claude is blocked from stopping"
}
```

Docs, verbatim: *"`decision`: `"block"` prevents Claude from stopping. Omit to allow Claude to
stop. `reason`: Required when `decision` is `"block"`. Tells Claude why it should continue."*
Exiting the hook process with code 2 has the same effect, with stderr used as the `reason` text.

Mechanically: returning `decision:"block"` does not "unblock" a paused function call — it tells
Claude Code's own agent loop *"do not end the turn, here is why,"* and the loop runs another
inference pass with that reason injected as context. The `stop_hook_active` field on the next
invocation tells the script whether it already forced one continuation (to avoid loops), and
Claude Code hard-caps this at **8 consecutive blocks** regardless of what the hook returns. There
is also a softer `additionalContext` variant that continues the loop without surfacing a hook-error
notice to the user.

### `PreToolUse`/`PostToolUse` use a different, non-overlapping decision model

`PreToolUse` uses `hookSpecificOutput.permissionDecision` ∈ `allow`/`deny`/`ask`/`defer`, gating a
tool call *before* it runs and optionally rewriting its arguments via `updatedInput`.
`PostToolUse` cannot block at all — the tool has already executed; its `decision`/`reason` only
annotates the result Claude sees. The docs are explicit that these are structurally different
mechanisms from `Stop`: *"Not every event supports blocking or controlling behavior through JSON.
The events that do each use a different set of fields to express that decision."* This confirms
the premise of our problem: Antigravity's `PostToolUse` (an already-happened-action event) is the
wrong shape of hook to gate a not-yet-run action, and it has no `Stop`-equivalent to pick up the
slack after the model's reply.

### `PreToolUse: "defer"` — Claude Code's own answer to "pause on an out-of-band human decision"

This is the closest built-in analogue to our exact problem, and worth calling out because it
*doesn't* rely on a hook process blocking synchronously. Docs, verbatim:

> *"`"defer"` is for integrations that run `claude -p` as a subprocess and read its JSON output…
> It lets that calling process pause Claude at a tool call, collect input through its own
> interface, and resume where it left off. Claude Code honors this value only in non-interactive
> mode with the `-p` flag."*

Flow: `PreToolUse` fires → hook returns `permissionDecision:"defer"` → the CLI process exits with
`stop_reason:"tool_deferred"`, preserving the pending call in the transcript → the *external
calling process* collects the human's answer out of band, on its own time → resumes with
`claude -p --resume <session-id>` → `PreToolUse` fires again with the answer available. Docs state
explicitly: *"There is no timeout or retry limit."* This is architecturally a session
suspend/resume, not an open connection or blocked thread — structurally the same idea MCP's Tasks
extension standardizes at the protocol level (§5).

Claude Code also has a dedicated `Elicitation` hook that can intercept and auto-answer MCP
`elicitation/create` requests before any dialog renders, with its own `accept`/`decline`/`cancel`
contract.

**Sources:** [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks),
[code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp),
[code.claude.com/docs/en/env-vars](https://code.claude.com/docs/en/env-vars)

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
No. `Stop`, `PreToolUse:"defer"`, and the `Elicitation` hook are all *client-side* features of
Claude Code specifically; an MCP server cannot make a different client support them. This section
matters as a **gap analysis**, not a usable technique: it shows precisely what Antigravity's hook
system would need to add (a post-turn event, or a defer-and-resume permission decision) to solve
this natively. Cost to us: zero — nothing to build; the finding is "this is what's missing,"
useful for a feature request to the Antigravity team, not for our server.

---

## 2. MCP elicitation, as specified, and which clients actually implement it

### The spec (2025-06-18, the stable/current baseline)

Server sends a request mid-tool-call:

```json
{"jsonrpc":"2.0","id":1,"method":"elicitation/create",
 "params":{"message":"...", "requestedSchema": {...JSON Schema, flat objects only...}}}
```

Client responds with a three-action model:

```json
{"jsonrpc":"2.0","id":1,"result":{"action":"accept","content":{...}}}
```

`action` is `accept` (content present), `decline` (explicit no), or `cancel` (dialog dismissed
without a choice). The sequence diagram in the spec shows the original `tools/call` staying open
the entire time — elicitation is a genuine nested, bidirectional JSON-RPC exchange, not a
return-and-retry pattern, in this spec revision. Schemas are restricted to flat objects with
primitive properties (string/number/boolean/enum) — no nesting, no arrays of objects. The spec
also says: *"Servers MUST NOT use elicitation to request sensitive information."*

**Important version caveat:** the newer draft/2025-11-25+ spec reworks this substantially — adds
a `mode` field (`form` vs `url`, for out-of-band flows like payments/OAuth that must never
transit the client), and introduces a "multi round-trip request" (MRTR) pattern where the tool
call actually *returns* an `InputRequiredResult` and the client *retries* the call with
`inputResponses`, rather than the server pushing a nested request. Which revision Antigravity
2.11.0 targets is not stated in its public docs — we could not verify this — so it is unclear
whether its (non-functional) elicitation support is even attempting the same wire shape our server
would send.

Sources: [modelcontextprotocol.io/specification/2025-06-18/client/elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation), [modelcontextprotocol.io/specification/draft/client/elicitation](https://modelcontextprotocol.io/specification/draft/client/elicitation)

### The official client matrix has no elicitation column at all

The canonical client-support table lives at
[modelcontextprotocol.io/clients](https://modelcontextprotocol.io/clients), backed by
[github.com/modelcontextprotocol/docs/blob/main/clients.mdx](https://github.com/modelcontextprotocol/docs/blob/main/clients.mdx).
Fetched directly via raw GitHub, its header row is:

```
| Client | Resources | Prompts | Tools | Sampling | Roots | Notes |
```

**There is no Elicitation column.** This gap is tracked by MCP maintainers themselves: issue
[modelcontextprotocol/modelcontextprotocol#839](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/839)
("Add a column in clients.mdx for support of elicitation," filed June 2025, closed via a PR) and
[#1814](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1814) ("SEP-1814:
Caniuse-style Compatibility Matrix for MCP Clients") which explicitly states the existing table
"lacks: Comprehensive feature coverage" and proposes elicitation as a category in a *new*,
currently unbuilt matrix. **Caveat:** the live rendered page at `/clients` could not be
independently re-confirmed through our fetch tooling (it kept returning the site's homepage); the
raw-GitHub source clearly lacks the column, but we cannot rule out the rendered site differing —
flagged, not resolved.

**Antigravity specifically:** does not appear anywhere in `clients.mdx` (zero hits on a direct
grep of the raw file). Antigravity's own MCP docs
([antigravity.google/docs/mcp/](https://antigravity.google/docs/mcp/)) make no mention of
"elicitation," "sampling," "roots," or any feature matrix at all — they document only context
injection, custom tool execution, transports, auth, and permission patterns. A GitHub search
scoped to the `google-antigravity` org's two public repos for "elicitation" returned one
irrelevant hit (a stdio-server-freezes-the-panel bug, not elicitation UX). **We found no public
report, anywhere, specifically describing Antigravity's elicitation as broken** — our own
experimental verification appears to be the only concrete evidence on this point; it could
neither be corroborated nor refuted externally.

### Elicitation is unreliable ecosystem-wide, not just in Antigravity

This is worth stating plainly because it changes the framing from "Antigravity is uniquely
broken" to "elicitation is broadly immature":

- **Claude Desktop has no elicitation support at all**, while Claude Code CLI does — confirmed via
  [anthropics/claude-code#41110](https://github.com/anthropics/claude-code/issues/41110), closed
  as out of scope for that repo.
- **Even where advertised, Claude Code silently no-ops on it**: [#56243](https://github.com/anthropics/claude-code/issues/56243)
  reports `elicitation/create` returning `cancelled` unexpectedly in one surface; [#85442](https://github.com/anthropics/claude-code/issues/85442)
  (open) reports a valid form-mode elicitation over Streamable HTTP rendering no dialog at all,
  timing out at 20s with `MCP error -32001`, and the hook never firing — the reporter notes this
  is indistinguishable from "dialog ignored" and breaks fail-closed write gates. This is
  functionally the exact same failure mode our project observed with Antigravity.
- **Gemini CLI does not support elicitation and fails loudly**: `ctx.elicit()` throws "Method not
  found" ([google-gemini/gemini-cli#22249](https://github.com/google-gemini/gemini-cli/issues/22249)),
  acknowledged but deprioritized by maintainers.
- **fast-agent** had elicitation forms silently fail to render after an update
  ([evalstate/fast-agent#518](https://github.com/evalstate/fast-agent/issues/518)).

**Sources:** all URLs inline above.

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
No — this is the exact mechanism the spec built for our problem, and it is the one we already
tried and found non-functional. The wider ecosystem evidence (Claude Desktop lacking it entirely,
Claude Code silently no-op'ing on valid requests, Gemini CLI erroring outright) suggests this
isn't an Antigravity-specific bug so much as elicitation being immature across nearly every
client eighteen months after specification. Cost: we already paid the cost of trying this and it
doesn't work; no further investment is justified until Antigravity ships a fix, which we have no
visibility into.

---

## 3. LangGraph interrupt/resume, and Temporal-style durable execution

These operate at a different layer than the previous two sections: they are frameworks where
*we* own the execution engine, versus MCP/Antigravity where the *client* owns the turn loop and we
are a guest inside it. They're included because they show what a "correct," purpose-built resume
mechanism looks like, and because our `await_approval` loopback server is a hand-rolled,
lightweight version of the same idea.

### LangGraph `interrupt()` / `Command(resume=...)`

Calling `interrupt(value)` inside a node raises a `GraphInterrupt` exception that the graph
runtime catches; this triggers a **checkpoint write** of the full graph state. Docs: *"When you
call `interrupt` within a node, LangGraph saves the current graph state"* so it "can be resumed
later." A configured checkpointer is mandatory — *"To use an `interrupt`, you must enable a
checkpointer, as the feature relies on persisting the graph state."*

The human's answer re-enters via re-invoking the graph with `Command(resume=<value>)`, e.g.
`graph.stream_events(Command(resume=True), config=config)`. That resume value becomes the return
value of the original `interrupt()` call — but with a critical caveat documented directly:

> *"the runtime restarts the entire node from the beginning — it does not resume from the exact
> line where `interrupt` was called… any code that ran before the `interrupt` will execute
> again."*

This means any side effect placed before `interrupt()` in the same node **re-fires on every
resume** unless made idempotent — the docs explicitly warn against "creating a new record before
interrupt," calling out duplicate-record bugs. This is a real design trap worth internalizing:
resumability via re-execution is not the same guarantee as resumability via true suspension.

Persistence: `InMemorySaver` (dev-only, lost on process restart), `SqliteSaver`, or
`PostgresSaver`/`AsyncPostgresSaver` for production. Only with a real backend can a human take
hours or days to respond while the process itself restarts in between.

Sources: [docs.langchain.com/oss/python/langgraph/interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [reference.langchain.com/python/langgraph/types/interrupt](https://reference.langchain.com/python/langgraph/types/interrupt)

### Temporal (and the "durable timer" trick)

Pattern: a workflow declares a Signal handler (e.g. `approval_decision`) and calls
`await workflow.wait_condition(lambda: self.current_decision is not None, timeout=...)`. An
external approver process sends the Signal via a Temporal client, addressed by workflow ID.

The mechanism that makes this different from a naive blocking call, quoted directly from
Temporal's docs:

> *"When a Workflow calls `workflow.wait_condition()`, the Worker returns the current task to the
> Temporal Server and becomes idle — consuming no compute."* When the Signal (or a timeout)
> fires, *"the Server schedules a new Workflow Task, the Worker replays the Event History to
> reconstruct the Workflow's state, and execution resumes from the `wait_condition` call."*

Concretely: Temporal never keeps a thread or process blocked. The only durable record is an
append-only Event History on the Temporal server. "Resuming" means any available worker re-runs
the workflow function from the top in a special replay mode, where every previously-completed
step (an Activity call, a timer, a received Signal) returns its already-recorded result instantly
instead of re-executing — replay fast-forwards to the waiting point, then real execution resumes
with the new event. This is why the docs say the wait "works identically whether the wait is five
seconds or five months." Unlike LangGraph, side effects (Activities) are individually checkpointed
in Event History and are *not* re-executed on replay — only LangGraph's node-granularity
checkpointing re-runs real code on resume.

A full worked example exists: [docs.temporal.io/guides/reliable-document-approvals](https://docs.temporal.io/guides/reliable-document-approvals)
(a `DocumentApprovalWorkflow` with SLA auto-escalation via durable timers), and an AI-specific
version at [docs.temporal.io/ai/cookbook/human-in-the-loop-python](https://docs.temporal.io/ai/cookbook/human-in-the-loop-python)
which states plainly: *"Can wait for approval for hours, days or indefinitely; while waiting, the
agent consumes no compute resources."* We could not confirm a dedicated "approval" sample by name
in `temporalio/samples-python` specifically (only a generic `hello_signal.py`) — flagged as
unverified.

Comparable named patterns elsewhere, briefly: **AWS Step Functions** `.waitForTaskToken`
("Wait for a Callback with Task Token" — pauses until `SendTaskSuccess`/`SendTaskFailure`, up to a
one-year service quota; [docs](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html)),
**Inngest** `step.waitForEvent()` (explicitly documents HITL as a use case, e.g. `timeout: "7d"`
waiting on an `app/invoice.approved` event; [docs](https://www.inngest.com/docs/features/inngest-functions/steps-workflows/wait-for-event)),
and **Restate** ("Approvals with Pause & Resume" — durable promise + callback ID;
[docs](https://docs.restate.dev/ai/patterns/human-in-the-loop)).

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
Not directly, and that's the point: these tools solve HITL by owning the *orchestration loop*
itself (the workflow engine, the graph runtime) and controlling when/how execution resumes. In
our situation, Antigravity owns the turn loop, and we are a tool call inside it — we cannot make
Antigravity "replay" or "resume a node." What *is* transferable: (a) the design lesson that a
resume mechanism should not double-fire side effects (directly relevant to hardening
`await_approval`, see Conclusion), and (b) the observation that our loopback HTTP server is
functionally a miniature, un-durable version of Temporal's Signal — it works only as long as our
MCP server process itself doesn't die while waiting. Adopting Temporal or LangGraph underneath
our MCP server would only buy us process-restart survivability for the *waiting* state; it would
still need to present as one (or more) blocking `await_approval` tool calls to Antigravity,
because Antigravity has no notion of "resume a suspended MCP session." Cost: meaningful
(standing up Temporal or LangGraph plus a checkpoint store) for a benefit (crash-safe waiting)
that's real but orthogonal to the actual bottleneck, which is client-side resume support.

---

## 4. OpenAI Apps SDK / ChatGPT apps: widget button → model continuation

This is the most directly comparable prior art to our HTML-card approach, and the answer is
important: **a widget button press is not a resume of a blocked call — it is always a brand-new
tool call or message.**

### Architecture

A ChatGPT "app" is an MCP server whose tool result points at a pre-declared `ui://` HTML resource
via `_meta` (legacy flat key `openai/outputTemplate`, or the now-standardized nested
`_meta.ui.resourceUri`). The host renders that HTML in a sandboxed iframe inline in the
conversation. Inside the iframe, ChatGPT injects a `window.openai` bridge
([developers.openai.com/apps-sdk/reference](https://developers.openai.com/apps-sdk/reference))
exposing, among others:

- `window.openai.callTool(name, args)` — *"Invoke another MCP tool from the widget (mirrors
  model-initiated calls)."*
- `window.openai.sendFollowUpMessage({ prompt, scrollToBottom })` — *"Ask ChatGPT to post a
  message authored by the component."*
- `window.openai.setWidgetState(state)` — persisted UI state.

The official docs are explicit that these are *"optional extensions"* over an open standard:
*"Beyond the portable standard, ChatGPT offers optional extensions via `window.openai`:
`window.openai.callTool` (alias for `tools/call`), `window.openai.sendFollowUpMessage` (alias for
`ui/message`)."*

### The underlying protocol is now a real, capability-negotiated MCP extension — MCP Apps (SEP-1865)

Verified against the raw spec file at
[github.com/modelcontextprotocol/ext-apps/.../2026-01-26/apps.mdx](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx):
it *"unifies the approaches pioneered by MCP-UI and the Apps SDK into a single, open standard,"*
built jointly by Anthropic, OpenAI, and the MCP-UI community, announced on the official MCP blog
2025-11-21 and finalized 2026-01-26. It is optional and negotiated via MCP's extension
capabilities mechanism — *not* an OpenAI-only backchannel — meaning **any MCP client, including
Antigravity, could in principle implement the host side without OpenAI's involvement.**

The JSON-RPC surface a widget can use: `ui/open-link`, `ui/message` (send a message into the
conversation, with the host adding it "preserving the specified role"), `ui/request-display-mode`,
`ui/update-model-context` (queues context for a *future* turn, doesn't itself trigger one), and
plain `tools/call` (reused verbatim from core MCP). The spec's own interactive-phase sequence
diagram shows these firing fresh, each as an independent RPC, in a loop, well after the
tool call that produced the widget has already completed:

```
loop Interactive phase
  U ->> UI: interaction (e.g., click)
  alt Tool call
    UI ->> H: tools/call
    H ->> S: tools/call
    H-->>UI: ui/notifications/tool-result
  else Message
    UI ->> H: ui/message
    H -->> UI: ui/message response
    H -->> H: Process message and follow up
  ...
```

There is **no primitive anywhere in the spec for a widget to supply the return value of an
already-open, still-pending tool call.** Every widget-initiated action is its own fresh exchange.
`ui/message` makes the model "continue" only in the sense that a new turn gets appended to the
conversation — not because a previous turn's execution was unblocked.

The one thing in ChatGPT that *does* behave like real call-blocking is separate from all of this:
a host-native write-action confirmation dialog, triggered by core-MCP tool annotations
(`destructiveHint`, `readOnlyHint`) rather than anything in the Apps extension — architecturally
closer to what we're doing, but it's chrome the host owns, not something a custom widget renders.

**Sources:** [developers.openai.com/apps-sdk/reference](https://developers.openai.com/apps-sdk/reference), [developers.openai.com/apps-sdk/build/custom-ux/](https://developers.openai.com/apps-sdk/build/custom-ux/), [github.com/modelcontextprotocol/ext-apps](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx), [blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/](https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/)

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
Not as MCP Apps proper — we found no evidence Antigravity implements SEP-1865 (unverified either
way; not documented). But the *pattern* it reveals is directly validating of our approach: even
in the most mature implementation of "render a card, let a human click it," a click never resumes
a paused tool call — it always issues a fresh RPC. Our `agent-embed` card plus a separate
`await_approval` tool call is structurally the same shape (card → new call), just built by hand
instead of via a standardized extension, and routed through a loopback HTTP POST instead of a
`ui/*` JSON-RPC method over `postMessage`. Cost of adopting MCP Apps instead: none available to
us today, since it requires host-side support Antigravity hasn't (as far as we can verify)
shipped; worth revisiting if Antigravity adds it, since it would replace our loopback HTTP server
with a standard transport, not change the fundamental "new call, not a resume" architecture.

---

## 5. Long-running blocking tool calls: accepted practice, timeouts, and spec guidance

### The spec's own trajectory is *away* from blocking, and names our exact use case

The MCP spec's live version (`2026-07-28`) moved "Tasks" out of core and into an official
extension. Its overview doc is unambiguous, and names human approval as one of three canonical
motivating examples:

> *"Not every tool call returns instantly. Some operations — CI pipelines, batch processing,
> **human approvals** — take seconds, minutes, or longer. MCP Tasks let servers return a durable
> handle instead of blocking, so clients can poll for progress, provide input when needed, and
> retrieve the final result after reconnecting."*

And it argues directly against the blocking pattern we use:

> *"You could hold the connection open until the work finishes. Tasks solve problems that
> blocking cannot: No long-lived connections. Blocking ties up a connection for the duration of
> the operation. Many clients and transport intermediaries impose timeouts that make this
> impractical beyond a few seconds. Crash resilience. A task ID is a durable handle… Mid-flight
> interaction. When a task needs input (e.g., an elicitation for user confirmation), it moves to
> `input_required` and surfaces the request. The client responds via `tasks/update`."*

Mechanically for HITL: a task's status becomes `input_required`, `tasks/get` returns an
`inputRequests` map, and the client answers via `tasks/update` — no open connection, no
unsolicited server push required. This is, verbatim in the spec, our exact use case standardized.

**But adoption is essentially zero.** The community
[Extension Support Matrix](https://modelcontextprotocol.io/extensions/client-matrix.md) doesn't
even carry Tasks as a tracked column (only "MCP Apps," "OAuth Client Credentials," and
"Enterprise-Managed Authorization" are listed) — and Antigravity isn't in that matrix at all.
We could not confirm any mainstream client (Claude Desktop, Claude Code, VS Code Copilot, Cursor,
ChatGPT, or Antigravity) implementing Tasks end-to-end as of this research. The predecessor,
"Asynchronous Tool Execution" (SEP-1391), is the tracking issue that motivated Tasks; it
explicitly diagnoses the failure mode of model-driven polling: *"Model-driven solutions rely
heavily on inconsistent behavior and prompt engineering to decide when and if to poll at all."*
That's a caution against building our own naive polling loop as a substitute, not just an
argument for adopting Tasks.

Sources: [modelcontextprotocol.io/extensions/tasks/overview](https://modelcontextprotocol.io/extensions/tasks/overview), [modelcontextprotocol.io/specification/2026-07-28/changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog), [modelcontextprotocol/modelcontextprotocol#1391](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1391), [modelcontextprotocol/modelcontextprotocol#982](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/982)

### Real client timeouts on blocking tool calls

There is no MUST/SHOULD timeout in the base spec, but a live proposal — **SEP-1539, "Timeout
Coordination"** ([issue](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1539)) —
states: *"At least 9 major MCP client implementations have struggled with timeout-related
issues."* Concretely, what we could verify:

- **MCP TypeScript SDK**: `DEFAULT_REQUEST_TIMEOUT_MSEC = 60_000` (60s), confirmed directly in
  source ([`protocol.ts`](https://github.com/modelcontextprotocol/typescript-sdk/blob/main/packages/core-internal/src/shared/protocol.ts)).
  Two opt-in knobs exist: `resetTimeoutOnProgress` (progress notifications reset the timer — off
  by default) and `maxTotalTimeout` (a hard ceiling even with resets).
- **Claude Code CLI**, from its own env-vars reference
  ([code.claude.com/docs/en/env-vars](https://code.claude.com/docs/en/env-vars)): for **stdio**
  MCP servers specifically — the same transport our server almost certainly uses — *"Stdio and
  WebSocket servers have no per-request timer."* Instead there's an idle-silence cutoff
  (`CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`, default **30 minutes** for stdio) and an absolute ceiling
  (`MCP_TOOL_TIMEOUT`, default ~28 hours). Most notably, Claude Code's own MCP doc states an
  explicit carve-out for exactly our pattern: *"A call waiting on an open elicitation dialog isn't
  backgrounded while the dialog is open; the server is blocked on your input, not slow, so Claude
  Code defers the move until the dialog closes."* That is a client explicitly choosing not to
  penalize "blocked on a human" the same way it penalizes "slow."
- **Claude Desktop** (a different codebase from Claude Code CLI) is reported, via multiple
  user-filed GitHub issues, to hard-kill tool calls after roughly 60s–240s
  ([#43791](https://github.com/anthropics/claude-code/issues/43791), [#65643](https://github.com/anthropics/claude-code/issues/65643)) — these are bug reports, not documented guarantees, so treat the specific numbers as observed, not
  specified.
- **Google Antigravity 2.11.0**: **no documented tool-call timeout found** in its official docs
  ([antigravity.google/docs/cli/mcp](https://antigravity.google/docs/cli/mcp)). A third-party
  proxy project mentioned a CLI flag with conflicting 5-minute/10-minute values in
  search-summarized text only — **this is unverified**; we did not independently read that
  repository's source. **This is the single most consequential unknown for our design** and
  cannot be resolved by further research — it needs to be measured directly against the client we
  actually run.

### Is blocking-on-a-human accepted practice?

Two answers point in slightly different directions and both should be stated: the **spec's own
extension documentation argues against indefinite blocking** and has built a named alternative for
this exact case; **but no mainstream client (including Antigravity) implements that alternative
yet**, and at least one major client (Claude Code) has gone out of its way to special-case
"blocked on human input" as an exemption from its own backgrounding/timeout logic — i.e., the
ecosystem's *de facto* current answer, pending Tasks adoption, is "blocking on a human is a known,
tolerated pattern that clients accommodate via idle timers and elicitation-aware exemptions, not
one they actively prevent."

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
Yes — this is, in effect, already our approach, and the research supports it as the most
realistic option available today, with the explicit understanding that it is a stopgap the spec
itself is trying to obsolete. Cost: low to keep, since it's what we've built; the risk is entirely
about Antigravity's specific timeout/idle-kill behavior toward a stdio tool call blocked for a
long wall-clock time, which we could not verify from documentation and should measure directly
(see Conclusion).

---

## 6. Server-push mid-turn: progress notifications, sampling, other server-initiated requests

### Progress notifications: liveness signal only, not a UI or keep-alive primitive by spec

Payload, quoted from the spec
([basic/utilities/progress](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress)):

```json
{"jsonrpc":"2.0","method":"notifications/progress",
 "params":{"progressToken":"abc123","progress":50,"total":100,"message":"Reticulating splines..."}}
```

Constraints: progress "MUST increase with each notification," `message` "SHOULD provide relevant
human readable progress information." There is **no schema support for structured or rich content**
in `message` — every implementation and discussion found treats it purely as a plain status
string for a spinner/progress-bar label. It is a one-way notification; nothing solicits a
response, so it cannot itself ask a human anything or carry interactive UI.

It *can*, however, function as a **timeout-reset keep-alive** — but only as an opt-in client SDK
behavior, not a spec mandate: the TypeScript SDK's `resetTimeoutOnProgress: true` flag
(confirmed in source, §5) causes each correlated `notifications/progress` to reset the
per-request timer. Whether Antigravity implements anything equivalent is unverified — this is the
second concrete thing worth testing empirically against our client (send periodic progress
notifications during the `await_approval` block and observe whether the call survives longer).
Reliability caveat: even where implemented, this mechanism is itself buggy in practice — e.g. the
official MCP Inspector CLI accepts a `--reset-timeout-on-progress` flag that a filed issue says
doesn't work because the CLI doesn't capture progress notifications at all
([modelcontextprotocol/inspector#880](https://github.com/modelcontextprotocol/inspector/issues/880)).

### Sampling: the wrong tool for this, even where supported

`sampling/createMessage` lets a server ask the *client's LLM* to generate a completion, with a
human nominally reviewing the request/response — but the "approved response" the server gets back
is an **LLM completion**, not a structured accept/decline signal. Using it as a general
approval channel would be a misuse of its intent. Client support is worse than elicitation: in the
official matrix, essentially only `fast-agent` shows Sampling support; Claude Desktop, Claude
Code, and (unverified either way) Antigravity do not. The MCP maintainers themselves have proposed
deprecating sampling (alongside roots and logging) for low adoption — SEP-2577:
*"Despite being available since the November 2024 specification, adoption remains low."*

### Roots and the full inventory of server→client requests

`roots/list` is purely informational (filesystem-boundary declaration, no accept/decline
semantics) and is also on the SEP-2577 deprecation list for low adoption. The **complete current
list** of things a server can ask a client to do mid-session is: `elicitation/create`,
`sampling/createMessage`, `roots/list`, and `ping`. Everything else server→client is a one-way,
no-response notification (`notifications/progress`, `notifications/message`, the various
`*/list_changed` notifications).

**Bottom line:** there is no third channel. `elicitation/create` is the only spec mechanism
designed to push a UI-like interaction to a client mid-call and get a structured answer back, and
it's the one we already found broken. Nothing else in the spec fills that gap.

**Sources:** [modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress), [modelcontextprotocol.io/specification/2025-06-18/client/sampling](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling), [modelcontextprotocol.io/specification/2025-06-18/client/roots](https://modelcontextprotocol.io/specification/2025-06-18/client/roots), [modelcontextprotocol/modelcontextprotocol SEP-2577](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/seps/2577-deprecate-roots-sampling-and-logging.md)

**Verdict — usable from a Python MCP server talking to Antigravity 2.11.0 today?**
Sampling and roots: no, wrong tool for the job even if Antigravity supported them (unverified
whether it does). Progress notifications: **partially and cheaply usable** — they cost almost
nothing to add to our existing `await_approval` blocking call, cannot make things worse, and might
extend how long Antigravity tolerates the block if it implements any timeout-reset-on-progress
behavior. This is a low-cost, uncertain-payoff addition worth making regardless of the rest of
this document's conclusions.

---

## Comparison table

| Approach | Resume mechanism | Requires client support we don't have in Antigravity? | Usable today? | Cost |
|---|---|---|---|---|
| Claude Code `Stop` hook block/continue | Client re-runs a turn on `decision:"block"` | Yes — no post-turn hook event in Antigravity | No | N/A (client-side gap) |
| Claude Code `PreToolUse:"defer"` | External process resumes CLI session (`claude -p --resume`) | Yes — session pause/resume feature | No | N/A |
| MCP elicitation | Nested request/response inside an open `tools/call` | Advertised, non-functional | No (verified broken) | Sunk; revisit if fixed |
| LangGraph `interrupt()`/`Command(resume=...)` | Checkpoint + re-run node from top | We'd own the loop, not Antigravity | Not applicable to this client relationship | High, wrong layer |
| Temporal Signal + `wait_condition` | Durable timer + Event History replay | Same as above | Not applicable to this client relationship | High, wrong layer |
| MCP Apps (SEP-1865) widget click | **New** `tools/call`/`ui/message`, never resumes a pending call | Yes — no confirmed Antigravity support | No (unverified support) | N/A until Antigravity adopts it |
| MCP Tasks extension | `input_required` status + `tasks/update`, no open connection | Yes — no client, including Antigravity, confirmed to implement it | No | N/A until adopted |
| Blocking tool call (our approach) | Tool call simply doesn't return until a human acts | No — this is what Antigravity actually supports | **Yes** | Low; already built |
| Progress notifications as keep-alive | Resets client-side request timer, opt-in | Unverified whether Antigravity honors it | Maybe, cheap to try | Very low |

---

## Conclusion: is blocking the standard answer, or are we missing something?

**We are not missing a better option available to us today.** Every purpose-built alternative —
Claude Code's `Stop` hook and `defer` permission, MCP elicitation, MCP Apps, MCP Tasks — either
requires client-side support Antigravity doesn't expose (the hook events, the extension
negotiation) or is a feature we already tried and confirmed broken (elicitation). The frameworks
that do solve this well in general (LangGraph, Temporal) solve it by *owning the orchestration
loop*, which is a role Antigravity occupies in our architecture, not us — adopting them would add
real infrastructure without removing the fundamental constraint that Antigravity itself has no
concept of "resume a suspended tool call."

**The honest, source-backed framing is: blocking is the spec's own admitted stopgap, not its
endorsed destination.** MCP's Tasks extension explicitly names human approval as a motivating
case and argues against blocking in its own documentation — but as of this research, no
mainstream client, including Antigravity, is confirmed to implement Tasks, MCP Apps, or reliable
elicitation. Until one of those lands in Antigravity, a blocking tool call is not a workaround we
invented in the absence of guidance — it is the one thing the current client demonstrably
supports, and at least one comparable client (Claude Code) treats "blocked on a human" as a
legitimate, exempted case rather than something to be timed out and background-killed.

**Two concrete hardening recommendations follow directly from the research, both cheap:**

1. **Make `await_approval` re-entrant with a bounded wait**, returning "still pending" if no
   decision has arrived within some interval (e.g. 60–120s) rather than blocking indefinitely in
   one call. This converts our pattern into the poll loop that MCP Tasks standardizes at the
   protocol level, without needing Antigravity to implement Tasks — the model just calls
   `await_approval` again. Caveat directly from SEP-1391's own diagnosis: *"Model-driven solutions
   rely heavily on inconsistent behavior and prompt engineering to decide when and if to poll at
   all"* — so this should be a safety net under indefinite blocking, not a replacement for it, and
   the tool description should be explicit that the model must keep calling it.
2. **Make approval consumption idempotent** — a killed-and-retried `await_approval` call (e.g. if
   Antigravity does hard-timeout and the model re-invokes it) must not double-fire the approved
   action. This is the same lesson LangGraph's docs state directly about re-running nodes: side
   effects around a resume point need to be safe to see twice.

**One unresolved question this document cannot close by research alone:** Antigravity 2.11.0's
actual timeout/idle-kill behavior toward a long-blocked stdio tool call is undocumented publicly
in any source we could verify. This should be measured directly — hold `await_approval` open for
increasing durations (1, 5, 15, 30+ minutes) with and without periodic `notifications/progress`
sent, and record whether/when Antigravity kills the call. That experiment, not further research,
is the next step that would actually change this document's recommendation.

---

## Consolidated list of items flagged as unverifiable

- Antigravity's actual MCP tool-call timeout value — no official documentation found; a
  third-party repo mentioned conflicting 5-minute/10-minute figures via search summary only, not
  independently confirmed.
- Whether the live, rendered `modelcontextprotocol.io/clients` page currently has an Elicitation
  column — our fetch tooling returned the site's homepage instead of the clients page; the raw
  GitHub source (`clients.mdx`) clearly lacks it, but the rendered site could not be independently
  re-checked.
- Any direct, specific report of Google Antigravity's elicitation (form or URL mode) being broken,
  beyond our own experimental verification — none found in GitHub, official docs, or general web
  search.
- Which MCP protocol revision (2025-06-18 vs. 2025-11-25+ mode/MRTR semantics) Antigravity 2.11.0
  targets for elicitation — not stated in its public docs.
- Reaction/upvote counts cited in passing for `anthropics/claude-code#2799` — a search snippet
  claimed a specific count that could not be independently confirmed.
- Whether SEP-1814's proposed comprehensive MCP client compatibility matrix has since shipped —
  as of this research it is an unassigned, unsponsored proposal.
- Whether any mainstream MCP client (Claude Desktop, Claude Code, VS Code Copilot, Cursor,
  ChatGPT, or Antigravity) implements the Tasks extension end-to-end — the community extension
  matrix doesn't track Tasks as a column at all, which reads as "not yet adopted," not confirmed
  non-support.
- Full wire schema of the 2026-07-28 spec's "Multi Round-Trip Requests" (MRTR) pattern
  (`InputRequiredResult`, `inputResponses`) — its existence and one-paragraph description were
  confirmed via the changelog; the full spec page was not fetched in detail.
- Whether Google Antigravity has any announced plan to adopt MCP Apps (SEP-1865) — not checked
  against Antigravity's own changelog/docs, out of scope of the topic as researched but relevant
  to future revisits of this document.
- A specific dedicated "approval workflow" sample by name/path in `temporalio/samples-python` —
  only a generic `hello_signal.py` was confirmed; approval-specific examples were found in
  Temporal's docs/cookbook content rather than that samples repository.
- Whether `destructiveHint`/`readOnlyHint` tool annotations are the *exclusive* trigger for
  ChatGPT's native write-action confirmation dialog, versus some additional host-side heuristic —
  the app-submission guidelines describe the annotation-based policy but not the dialog's full
  internal trigger logic.
