# Three phases: local orchestrator → remote workspace → many clients

The goal, in the owner's words: Antigravity orchestrates the models in its own
environment locally; that syncs to a remote workspace; eventually several
Antigravity instances work against the same remote server.

This maps onto what already exists more closely than it might look, because the
hard part of phase 3 is a phase 1 decision. Written 2026-08-27.

---

## Phase 1 — Antigravity as a local orchestrator

**What exists:** an MCP server (`src/adk_harness/mcp_server.py`) registered in
`~/.gemini/config/mcp_config.json`, exposing each installed harness as a
governed tool. Verified by speaking MCP to it as a real client: tools listed,
deny path fired, audit recorded.

**What is unresolved:** whether the Antigravity *IDE* can orchestrate its own
models. MCP tools sit beside the model the IDE is running; they do not steer
which model it picks. The `google-antigravity` **SDK** does support this
directly — `LocalAgentConfig` has both `models: list[ModelTarget]` and
`subagents: list[SubagentConfig]`, so a lead model can route to subagents pinned
to different models.

So phase 1 has two possible shapes, and they are not equivalent:

| Shape | Mechanism | Status |
|---|---|---|
| IDE delegates to external harnesses | MCP tools | working today |
| IDE orchestrates its own models | needs an IDE extension API | unknown — under investigation |
| SDK agent orchestrates subagents on different models | `subagents` + `models` | supported by the SDK, not yet built |

The third row is buildable now and is the honest version of "one model
controlling others". Whether it can live *inside* the IDE is the open question.

---

## Phase 2 — sync to a remote workspace

**What exists, and it is most of this:**

- A deployed Cloud Run service, already running two fleets.
- `CoactraGovernance` — the gate, identical wherever it runs.
- `FirestoreActionLedger` — append-only, idempotency-keyed, so a retry from a
  flaky client cannot double-record.
- `SQLitePrecedentStore` — decisions that survive a restart.

**What phase 2 actually needs beyond that:** the precedent store must move from
SQLite to something shared. SQLite is per-machine by construction; the moment
two clients exist, "answer once" silently becomes "answer once *each*", which is
the whole value gone. Firestore is already a dependency for the ledger, so the
same backend serves.

That is a small piece of work with a large consequence, and it is the real
boundary between phase 1 and phase 2.

---

## Phase 3 — several Antigravity clients, one server

The interesting phase, and the one where a design decision made now decides
whether it works.

**Why it is valuable:** if five people share one fleet, a governance question
answered by one of them need not be asked of the others. That is the precedent
loop doing something no single-user tool can: institutional memory rather than
personal memory.

**Why it is dangerous, and the decision that has to be made deliberately:**

> Should one person's approval bind everybody else?

Sometimes obviously yes — "internal review slots on our own calendar are
routine" is a team fact, and re-asking each colleague is noise. Sometimes
obviously no — an intern approving a production deploy must not silently
authorise it for the whole company.

The machinery for this already exists and is unused: `coactra.Scope` carries
`tenant_id`, `namespace`, `agent_id` and `session_id`. A precedent recorded at
`session_id` scope binds one conversation; at `agent_id` scope, one person; at
`tenant_id` scope, the organisation. `Precedent.applicability` is already
explicit rather than inferred, so the widening is always an act, never an
accident.

**What phase 3 needs:**

1. Precedents stored with the scope they were approved at, and matched only
   within it.
2. An audit trail that records *who* approved, which `AuditRecord` does not yet
   carry — it has the principal on the request, not on the approval.
3. A way for a person to see precedents that bind them and that they did not
   personally create. Being governed by a decision you cannot inspect is worse
   than being asked again.

Point 3 is not a technical requirement. It is the difference between a system
people trust and one they route around.

---

## The order that matters

1. **Scope precedents properly** — phase 1 work, phase 3 payoff. Doing it later
   means migrating decisions whose scope nobody recorded, which cannot be done
   correctly after the fact.
2. **Move the precedent store to Firestore** — unlocks phase 2.
3. **Record the approver on the approval** — small, and phase 3 is not
   defensible without it.
4. **Resolve the IDE question** — whether phase 1's richer form is reachable
   inside Antigravity, or whether the SDK is where multi-model orchestration
   lives.

Steps 1–3 are worth doing regardless of how step 4 resolves, because they are
true of any client: an editor, a CLI, or a web UI.
