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

## 3. Three harnesses, one protocol

Discovery against the machine, not a fixture. Three genuinely different
integration shapes satisfying one 5-method protocol:

```
  claude_code  0.2.144      ready        (Python SDK)
  codex        0.149.1      ready        (CLI subprocess, JSONL stream)
  opencode     1.17.9       needs serve  (HTTP + SSE)
```

A harness that is not installed reports `available=False` with a reason and is
left out of the fleet. Nothing raises:

```
opencode  unknown  unavailable (OpenCode server 'http://127.0.0.1:4096'
                    could not be reached: All connection attempts failed)
```

---

## 4. Running it on a real repository

```bash
GOOGLE_CLOUD_PROJECT=your-project python examples/dogfood.py --cwd . "your task"
```

This is not the demo — it registers the real harnesses and lets them work in a
directory you name, under the same gate. Add `--precedents ~/.adk-harness.db` to
make answers survive the process.

---

## What these runs do not prove

Stated here rather than left to be discovered:

- **Dispatch is gated; a harness's own inner tool calls are not.** They execute
  in the harness's process and never return through ADK. They are streamed and
  audited, not individually approved. See `src/adk_harness/agent.py`.
- **The Cloud Run demo registers a stub harness**, because a container has
  neither `codex` nor `claude` installed. The stub says so in its own output.
  The transcript in §1 uses a stub for the same reason: it keeps the recording
  about governance rather than about which CLI is present.
- **§3's opencode row is discovery, not a full run.** The adapter has tests and
  was written against the real binary and its SDK, but no end-to-end opencode
  session is captured here.
- **`coactra` is a pre-existing dependency**, disclosed in
  [HACKATHON_DISCLOSURE.md](../HACKATHON_DISCLOSURE.md).
