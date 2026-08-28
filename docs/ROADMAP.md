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
| Deployed on Cloud Run, all three outcomes | revision `adk-harness-fleet-00005-tjr`, see below |
| A real Google Calendar event, gated per operation | `docs/PROOF.md` §3 — event created, verified, deleted |
| Antigravity harness on Vertex | `available=True` from explicit args, no env vars |
| Offline suite | 126 passed, 4 skipped (`.venv/bin/pytest -q`, measured 2026-08-27) |

The three governance outcomes, verified live against the deployed service with
Gemini 3.5 Flash on Vertex:

| Request | Outcome | What came back |
|---|---|---|
| "Add a docstring to main.py" | `allow` | dispatched to `run_demo`, harness responded |
| "Update the prod deploy configuration" | `requires_approval` | ADK emitted `adk_request_confirmation`; tool returned `awaiting_confirmation` and the work did **not** run |
| "Rotate the API key stored in .env" | `deny` | `blocked`, and the model reported the reason and stopped rather than rerouting |

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

### A third adapter — done, and a fourth landed alongside it

`opencode` (HTTP + OpenAPI, `src/adk_harness/adapters/opencode.py`) and
`antigravity` (Python SDK over a bundled compiled runtime,
`src/adk_harness/adapters/antigravity.py`) are both landed and tested. Four
integration shapes now satisfy one protocol — stronger evidence than the three
this section originally asked for. See the status table in
[README.md](../README.md).

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

---

# Appendix: the Enterprise Fleet PRD, measured against this

Merged here from the former `docs/ROADMAP.md`, so there is one place that
says what is next rather than two that disagree.

## The honest summary

The PRD's stated differentiator is *"controlled execution with durable
institutional memory and proof of action."*

**That part is already built and proven live.** What is missing is the entire
Google Workspace surface the PRD is about — and its own acceptance criteria
(§12) explicitly rule out faking it: *"unverified API simulation ... does not
satisfy acceptance."*

So this is not a project that is 80% done. It is a project whose *hard*
governance half is done and whose *large* integration half is not started.

## What maps directly, with evidence

| PRD requirement | What exists | Evidence |
|---|---|---|
| "The gateway evaluates every tool call" | `CoactraGovernance.before_tool_callback` | 3 outcomes verified live on Cloud Run |
| "Prior decisions may guide future plans but cannot override policy" | The precedent loop — this is a *literal* match | `precedent.py`, tests pin that precedent never overrides a deny |
| "Sending email ... requires approval in the MVP" | `requires_approval` halts the work | verified: harness not reached while the question is open |
| "Every action records actor, agent, policy result, outcome" | `AuditRecord` | needs `input hash` and `scope` added |
| Registry: capabilities, versions, status | `HarnessRegistry` | needs manifests, owners, approval status |
| "Demonstrate real Gemini, ADK and Google Cloud execution" | Deployed, revision `00005-tjr` | 4 live Vertex tests |
| OpenTelemetry spans | `--trace_to_cloud` wired | wired, not verified end to end |
| Justified delegation among agents | `AgentTool` fan-out | 4 harnesses dispatch through one gate |

## What does not exist at all

Gmail / Calendar / Drive / Docs integration · per-user OAuth · Firestore
workflow state and action ledger · Pub/Sub · Model Armor · the 9-state workflow
machine with durable resume · idempotency keys · read-after-write verification ·
partial-failure recovery · the 7 specialist agents with enforced boundaries ·
the 4-view web control plane · the structured action envelope that replaces
`prompt + cwd + session`.

That last one matters more than its size suggests: it replaces `protocol.py`,
which every adapter and test is written against.

## The judgement

**The full PRD is not reachable in 4 days.** OAuth plus four Workspace APIs plus
a durable state machine plus a control plane is multiple weeks of work, and
§12 forbids simulating any of it.

Two things are worth saying plainly:

1. **The PRD asks to throw away the strongest evidence.** Four harnesses across
   four genuinely different integration shapes, satisfying one protocol, is a
   demonstrated claim. Replacing the contract discards it and starts the
   evidence over with days left.
2. **The differentiator does not depend on Workspace.** "Ask once, then never
   again, and never override a deny" is provable today, and is the part judges
   cannot get from anyone else.

## Three options, honestly costed

### A. Full pivot as written
Build Workspace + OAuth + state machine + control plane.
**Cost:** weeks. **In 4 days:** a partial build that fails its own §12.
**Recommendation:** no.

### B. Governed Workspace slice — the credible pivot
Keep the governance core, the precedent loop, the registry and the audit trail
exactly as they are. Add **one** Workspace harness — Calendar `create_event`,
draft-only Gmail — as a fifth adapter behind the existing protocol. Show the
same gate deciding about a real, consequential, external action.

**What lands:** a real Workspace mutation, gated, approved once, remembered,
audited, on real Google Cloud. That satisfies most of §11's metrics and the
spirit of §12 for one action rather than a workflow.
**Cost:** ~1.5 days for OAuth + Calendar, leaving time for the video.
**Risk:** OAuth consent screens are fiddly and can eat a day.

### C. Sharpen what exists
No pivot. Fix the opencode adapter's defects, finish the audit findings, record
the demo against the four-harness fleet.
**Cost:** ~1 day. **Ceiling:** lower — it is a developer-tools story, not an
institutional one.

## Revised, with Codex in parallel

Parallel agents change the arithmetic, but not evenly. They multiply how much
code gets written; they do not multiply the two things that have actually
consumed time on this project.

**What parallelism buys:** Calendar, Gmail, Docs and a Firestore action ledger
are independent files behind one frozen protocol. Four agents can write them at
once, and today two did exactly that successfully.

**What it does not buy:**

1. **OAuth consent is human-serial.** On a personal `@gmail.com` account there
   is no domain-wide delegation, so a browser consent step is irreducible. No
   number of agents removes it.
2. **Verification is where this project loses time, and it does not
   parallelise.** Every Codex-built component today had a real defect that only
   appeared when run: the Codex adapter yielded zero turns while eleven of its
   own tests passed. §12 forbids unverified API simulation, so each Workspace
   call has to be *observed working*, one at a time, against a real account.

So: **B becomes comfortable, and B+ becomes reachable** — Calendar plus
draft-only Gmail plus a Firestore action ledger, rather than Calendar alone.

Still not reachable in four days: the fourteen-step multi-week workflow, seven
agents with enforced permission boundaries, Pub/Sub resumption, Model Armor, and
a four-view control plane. Claiming those would fail §12 rather than satisfy it.

## Recommendation

**B+, built in parallel.** Serial gate first (OAuth), then fan out. It keeps every piece of evidence already earned, adds the one thing the
PRD has that the current build lacks — a consequential external action under
governance — and is achievable in the time left.

The grant-coordination narrative can still frame the demo. What changes is that
the fleet governs *one* real Workspace action end to end instead of
orchestrating a fourteen-step multi-week workflow that would have to be
simulated, which the PRD itself refuses to accept.

## B was chosen. What actually happened

1. **OAuth was the gate, as predicted, and it cost real time.** `gcloud auth
   application-default login --scopes` is refused for sensitive scopes — Google
   will not issue them to its own shared CLI client. The fix is a project OAuth
   client with the consent screen left in Testing and the developer added as a
   test user. That step cannot be automated on a personal account: there is no
   domain-wide delegation without a Workspace organisation.
2. **A hand-rolled `CalendarHarness` was written, then deleted.** It worked, but
   it reimplemented ADK's official `CalendarToolset` and gated at dispatch. The
   PRD requires per-call evaluation, and the toolsets provide it by
   construction. See `src/adk_harness/workspace.py`.
3. **A real event was created under governance and verified.** `docs/PROOF.md`
   §3. Approved once, applied by precedent the second time, deleted afterwards.

Still open, honestly:

- **Gmail is blocked and not by us.** `gmail.compose` is a *restricted* scope
  requiring Google app verification. `GmailToolset` is wired and will work the
  moment a token carries the scope. Until then it is not demonstrable, and
  claiming otherwise would fail §12.
- **The Workspace fleet is not deployed to Cloud Run yet.** The auth shape
  supports it — `use_default_credential=True` reads the service identity — but
  it has not been run there.
- **Docs, opencode turn quality, and the audit findings** from
  `docs/audits/` remain.
