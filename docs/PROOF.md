# Proof: captured runs

Everything below is recorded output from real runs against real infrastructure —
Gemini 3.5 Flash on Vertex AI, and a live Cloud Run service. No output on this
page is illustrative, edited for effect, or written by hand.

You can reproduce any of it (commands are given), but you should not have to in
order to see what this library does.

---

## 1. The precedent loop

This is the claim the project rests on: **a human answers a governance question
once, and stops being asked.** Not "the agent asks less often" — stops.

```bash
GOOGLE_CLOUD_PROJECT=your-project python examples/capture_precedent_loop.py
```

Captured 2026-08-25, `gemini-3.5-flash`, Vertex location `global`:

```
model:     gemini-3.5-flash
harnesses: ['demo']
task:      Bump the replica count in the prod deploy config. Delegate it to a harness.

────────────────────────────────────────────────────────────────────────
RUN 1 — no precedent exists, so a human is asked
────────────────────────────────────────────────────────────────────────
  gemini: The request to bump the replica count in the production deployment
          configuration is currently awaiting confirmation from the policy gate.
  gate: requires_approval      The instruction touches production configuration.
  gate: asked_human            no precedent covers these facts
  gate: completed
  harness reached: False   <- work did not happen

────────────────────────────────────────────────────────────────────────
THE HUMAN ANSWERS, ONCE — with a scope they choose themselves
────────────────────────────────────────────────────────────────────────
  precedent: pr-2026-08-25-replicas
  scope:     ["tool eq 'run_demo'"]
  note:      applicability is passed explicitly, never inferred from the answer

────────────────────────────────────────────────────────────────────────
RUN 2 — same question, same conditions. Nobody is interrupted.
────────────────────────────────────────────────────────────────────────
  gemini: I have successfully delegated the task to the harness, and the replica
          count in the production deployment configuration has been bumped.
  gate: requires_approval      The instruction touches production configuration.
  gate: allowed_by_precedent   pr-2026-08-25-replicas: Replica counts are
                               reversible and monitored. Approved.
  gate: completed
  harness reached: True   <- work happened

Human was interrupted 1 time(s) across 2 runs of the same task.
```

Three details in that transcript are worth pausing on:

- **`harness reached: False` in run 1.** The gate did not merely log a warning
  and continue. The work did not happen while the question was outstanding.
- **The policy still says `requires_approval` in run 2.** Precedent did not
  weaken the rule. It answered the question the rule raised.
- **`scope: ["tool eq 'run_demo'"]`** was passed explicitly by the caller. A
  casual "yes, fine" cannot silently widen into a standing policy, because the
  scope is never inferred from the answer.

---

## 2. All three governance outcomes, on Cloud Run

Deployed service, revision `adk-harness-fleet-00005-tjr`, `us-central1`,
`--min-instances=0`. Gemini 3.5 Flash on Vertex, real HTTP requests to
`/run`.

| Request | Outcome | What actually came back |
|---|---|---|
| "Add a docstring to main.py" | `allow` | dispatched to `run_demo`; the harness responded |
| "Update the prod deploy configuration" | `requires_approval` | ADK emitted `adk_request_confirmation`; the tool returned `awaiting_confirmation` and **the work did not run** |
| "Rotate the API key stored in .env" | `deny` | `blocked`; the model reported the reason and stopped rather than rerouting to another harness |

The denial response, verbatim from the service:

```json
{"status": "blocked",
 "reason": "The instruction mentions 'api key'. Credentials are never edited by an agent in this workspace.",
 "tool": "run_demo"}
```

And what Gemini then said to the user, rather than retrying:

> The task to rotate the API key in `.env` and update the code has been blocked
> by the policy gate. **Reason for block:** "Credentials are never edited by an
> agent in this workspace." In accordance with the governing policy, I have
> stopped further attempts.

---

## 3. A real Google Workspace action, gated per operation

The strongest evidence here, because the action is externally visible: an event
on a real Google Calendar, created only after a person approved it.

```bash
GOOGLE_CLOUD_PROJECT=your-project python examples/capture_workspace_governance.py
```

Captured 2026-08-27. Tools are ADK's official `CalendarToolset`, filtered to two
operations of the 38 it offers:

```
model:    gemini-3.5-flash
services: calendar
tools:    calendar_events_list, calendar_events_insert

──────────────────────────────────────────────────────────────────────────
RUN 1 — nobody has approved a write. The calendar is not touched.
──────────────────────────────────────────────────────────────────────────
  gate: calendar_events_insert   requires_approval   calendar_events_insert creates something other people will see.
  gate: calendar_events_insert   asked_human         no precedent covers these facts

──────────────────────────────────────────────────────────────────────────
THE ADMINISTRATOR ANSWERS ONCE, with a scope they choose
──────────────────────────────────────────────────────────────────────────
  precedent: pr-2026-08-27-internal-review
  scope:     ["tool eq 'calendar_events_insert'"]
  note:      the scope names one operation, not 'calendar'

──────────────────────────────────────────────────────────────────────────
RUN 2 — same request. Nobody is interrupted. A real event appears.
──────────────────────────────────────────────────────────────────────────
  gate: calendar_events_insert   requires_approval      calendar_events_insert creates something other people will see.
  gate: calendar_events_insert   allowed_by_precedent   pr-2026-08-27-internal-review: Internal review slots on our
                                                        own calendar are routine and reversible.
  gemini: I have scheduled the event "Horizon Health grant — internal review" on
          your primary calendar for September 11, 2026, from 15:00 to 16:00.
```

Verified independently against the Calendar API afterwards — the event existed,
and was then deleted:

```
CREATED: 1
dc3ve6fl8dsaj7nfi006gnphuk | Horizon Health grant — internal review
deleted dc3ve6fl8dsaj7nfi006gnphuk -> HTTP 204
```

What makes this different from §1: the gate names the **operation**, not the
dispatch. `calendar_events_insert` was approved; `calendar_events_list` was
never in question; `calendar_acl_update` would still be refused outright, because
it is a different tool. A dispatch-level gate cannot express that distinction.

## 4. Four harnesses, one protocol

Discovery against the machine, not a fixture. Four genuinely different
integration shapes satisfying one 5-method protocol:

```
  antigravity  0.1.15       ready        (Google SDK, local runtime, Vertex)
  claude_code  0.2.144      ready        (Python SDK)
  codex        0.149.1      ready        (CLI subprocess, JSONL stream)
  opencode     1.17.9       needs serve  (HTTP + SSE)
```

Google Workspace is deliberately **not** in this list. ADK already ships
official toolsets for it, so wrapping it in this protocol would have
reimplemented them — and gated at dispatch instead of per operation. See §3.

A harness that is not installed reports `available=False` with a reason and is
left out of the fleet. Nothing raises:

```
opencode  unknown  unavailable (OpenCode server 'http://127.0.0.1:4096'
                    could not be reached: All connection attempts failed)
```

---

## 5. Running it on a real repository

```bash
GOOGLE_CLOUD_PROJECT=your-project python examples/dogfood.py --cwd . "your task"
```

This is not the demo — it registers the real harnesses and lets them work in a
directory you name, under the same gate. Add `--precedents ~/.adk-harness.db` to
make answers survive the process.

---

## What these runs do not prove

Stated here rather than left to be discovered:

- **Enforcement differs by path.** Workspace operations are gated individually
  — `calendar_events_insert` is its own decision. Coding harnesses are gated at
  dispatch only: their inner file edits and shell commands run in their own
  process, never return through ADK, and are streamed and audited rather than
  approved. See `src/adk_harness/agent.py` and `src/adk_harness/workspace.py`.
- **The Cloud Run demo registers a stub harness**, because a container has
  neither `codex` nor `claude` installed. The stub says so in its own output.
  The transcript in §1 uses a stub for the same reason: it keeps the recording
  about governance rather than about which CLI is present.
- **§4's opencode row is discovery, not a full run.** The adapter has tests and
  was written against the real binary and its SDK, but no end-to-end opencode
  session is captured here.
- **`coactra` is a pre-existing dependency**, disclosed in
  [HACKATHON_DISCLOSURE.md](../HACKATHON_DISCLOSURE.md).
