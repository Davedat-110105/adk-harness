# The Enterprise Fleet PRD, measured against what exists

Written 2026-08-27, with **4 days and 5 hours** until the 2026-08-31 17:00 PDT
deadline. This is an assessment, not a plan of record. Nothing here is built.

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

## If B is chosen, the order that matters

1. OAuth for one user, one scope (`calendar.events`). Verify a token round trip
   before writing any adapter.
2. `CalendarHarness` behind the existing protocol.
3. Policy: create event → `requires_approval`; external attendees → `deny`.
4. Capture the transcript, as with `docs/PROOF.md`.
5. Only then, if time remains: Gmail draft-only.

Step 1 is the gate. If OAuth is not working by end of day one, fall back to C
rather than spending day two on it.
