# Where this can go: services, architecture, and what to build next

Written 2026-08-25, six days before the submission deadline (2026-08-31 17:00
PDT). Ordered by what makes the submission more concrete without making it less
flexible — because those two pull against each other, and most of the bad
choices available here trade one for the other without saying so.

Everything below is either **verified**, **plausible-but-unverified**, or
**explicitly not planned**. Nothing is described as done unless it is.

---

## Where the project actually stands

Verified working, on real infrastructure, as of this writing:

| Thing | Evidence |
|---|---|
| Governance plugin gating a real Gemini tool call | `tests/test_governance_live.py`, 2 passed against Vertex |
| A whole fleet: Gemini picks a harness, dispatch meets the gate | `tests/test_fleet_live.py`, 2 passed against Vertex |
| Codex adapter | 11 tests; flags read from live `--help`, event tags from the binary |
| Claude Code adapter | 18 tests; API read from installed SDK source, not recalled |
| Precedent loop | 10 tests, including the two safety properties |
| Deployed on Cloud Run, end to end | Gemini 3.5 Flash dispatched, gate blocked, model reported the refusal and stopped |
| Offline suite | 57 passed, 4 skipped |

The deployment is the load-bearing evidence, and it is worth being precise about
what it proved: it caught a bug the offline tests did not. The gate refused a
dispatch with *"run_demo is outside the workspace /workspace"* — a refusal that
reads like governance working, and was actually the policy deciding about the
tool's name instead of the working directory. Fixed, with tests pinning the
resolution order. **A gate that denies for the wrong reason is worse than one
that fails loudly, because the audit trail looks correct.**

That is the strongest argument for spending remaining time on running things
rather than describing them.

---

## Tier 1 — do these before the deadline

### 1. Make the precedent loop visible in the deployed demo

**Why this first:** the precedent loop is the project's actual claim, and right
now it is provable only by reading `tests/test_precedent.py`. A judge will not.

The demo currently shows allow and deny. It does not show the sequence that
matters: *asked once, then never again*. That sequence is the difference between
"another policy wrapper" and "an agent that learns your judgment".

**Concretely:** make the deployed `WorkspacePolicy` return `requires_approval`
for a path a demo script will reliably hit, and expose two HTTP endpoints on the
example app — one that lists the audit trail, one that posts a human answer and
calls `governance.remember()`. Then the demo is: send the request, get asked,
answer once, send it again, watch it not ask.

**Risk:** `request_confirmation` pauses an ADK run, and resuming it through the
`api_server` HTTP surface has not been verified. If resumption turns out to be
awkward over HTTP, fall back to a local script for the video rather than
deforming the library to fit a demo.

### 2. State plainly, in the README, what the gate does not cover

Already written into `agent.py`'s docstring and the README, and worth keeping
sharp: **dispatch is gated; a harness's own inner tool calls are observed, not
gated.** They run in the harness's process and never return through ADK.

This is a weakness stated as a fact, which is stronger than a strength that
does not survive a question. Anyone who reads the code will find it in a minute;
finding it in the README first builds trust rather than spending it.

### 3. Record the video against the deployed service, not a local run

The Cloud Run URL, the ADK dev UI, and a real Vertex model call are all already
working. Showing the browser is worth more than showing a terminal, and it is
the only artifact that proves the Google stack is genuinely in the loop.

---

## Tier 2 — real, useful, and each one is a day

### Vertex AI Agent Engine for sessions and memory

**Status: provisioned and verified reachable, not yet wired into the app.**

`adk api_server` accepts `--session_service_uri=agentengine://<id>` and
`--memory_service_uri=agentengine://<id>`. The demo currently runs
`memory://`, so every session dies with the container.

What this buys, concretely: precedents currently live in an in-process
`PrecedentStore`. A Cloud Run instance scaling to zero forgets every answer a
human gave — which quietly destroys the project's central claim in exactly the
deployment being demonstrated. **Precedent that does not survive a restart is
not precedent.**

The honest fix is a persistent `PrecedentStore` backend. Memory Bank is the
Google-native option and is already provisioned; a small SQLite or Firestore
store would also do. This is the single highest-value item in Tier 2, and
arguably belongs in Tier 1 if there is time.

Note the IAM shape, learned the hard way during provisioning: Memory Bank needs
**both** `roles/aiplatform.user` on the Reasoning Engine service agent **and**
`contextSpec.memoryBankConfig` on the engine. Either alone returns 403 on the
embedding call.

### A third adapter, to prove the protocol is not shaped around two vendors

`opencode` is the right candidate: it is an HTTP server with an OpenAPI spec,
which is a genuinely third integration shape after "CLI subprocess" and "Python
SDK". Two adapters can accidentally agree; three that disagree structurally and
still fit the same protocol is evidence.

`httpx` is already declared as the `opencode` extra. The work is the adapter
itself.

**Not planned:** Hermes Agent and DeepSeek Harness. They are general agent
runtimes rather than coding-first agents, and DeepSeek Harness is a v0.1
developer preview that guarantees breaking changes. Adding shallow adapters
would weaken the protocol claim rather than strengthen it.

### A2A, for the thing A2A is actually good at

Verified by SDK introspection, not documentation: the protocol **does** support
back-and-forth. `TASK_STATE_INPUT_REQUIRED` exists, `TaskStatus.message` carries
the question, `Message` has `context_id` and `task_id`, and `Task.history` is
the transcript.

What it lacks is any notion of a *conversation* as a first-class object — no
discussion view, no tooling that renders history as dialogue. It is task-centric
by construction.

That maps onto this project unusually well: `requires_approval` **is** a task
that needs input. Exposing the fleet over A2A with approvals as
`TASK_STATE_INPUT_REQUIRED` would let another agent — not just a human — answer
a governance question, and the answer would still become a precedent.

`google-adk[a2a]` is already declared as an extra. This is the most interesting
stretch goal in the list and the least likely to fit before the deadline.

---

## Tier 3 — worth writing down, not worth building now

- **Model Armor / safety filtering** in front of the orchestrator. Real product,
  real fit, but it protects a surface this project does not currently expose.
- **Multi-tenant precedent scoping.** `coactra.Scope` already carries
  `tenant_id`, and `Precedent` already has `specificity()`. The pieces are
  there; the use case is not, yet.
- **A policy DSL.** Tempting and wrong. The policy is a Protocol with one async
  method, which means anyone can write one in plain Python with no framework to
  learn. A DSL would trade that flexibility for a concreteness nobody asked for.

---

## What "flexible enough to actually use" means here, concretely

Worth stating, because it is the constraint most likely to be violated while
adding features under time pressure:

1. **`protocol.py` stays frozen.** Five methods, no vendor types. Every adapter
   written against it keeps working.
2. **`Policy` stays a Protocol with one `async check()`.** An external caller
   implements one method and imports five DTOs. No base class, no registration,
   no framework.
3. **Adapters never decide permission.** The moment one does, the answer to "may
   this happen?" starts depending on which harness was picked, and the fleet is
   supervised rather than governed.
4. **A missing harness is `available=False`, never an ImportError.** This is
   what lets someone `pip install adk-harness` and use it with whatever they
   happen to have.
5. **The precedent store never calls a model.** Admission is by hard predicate;
   similarity only ranks what was already admitted. A model deciding whether a
   past approval applies to a new situation is precisely the thing a governance
   layer exists to avoid.

Any feature that requires breaking one of these five is the wrong feature, no
matter how good it looks in a demo.

---

## Honest weaknesses, listed so they are not discovered instead

- Inner tool calls are observed, not gated (see Tier 1, item 2).
- Precedents do not survive a restart (see Tier 2, Agent Engine).
- The Codex adapter's JSONL **event tags** were verified from the binary, but
  the **field names inside each payload** were not. The adapter is written not
  to depend on any single key — `raw` carries the whole line, and `tool_args`
  carries the whole payload — but a live `codex exec --json` run would let those
  be tightened from defensive to exact.
- The hosted demo registers a stub harness, because a Cloud Run container has
  neither `codex` nor `claude` installed. The stub says so in its own output.
- `coactra` is a pre-existing dependency, disclosed in
  [HACKATHON_DISCLOSURE.md](../HACKATHON_DISCLOSURE.md): 158 of its 160 commits
  predate the submission window. Everything in this repository was written
  inside it.
