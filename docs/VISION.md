# Historical vision and migration context

This document records pre-migration architecture research. It is not an active
server or multi-vendor integration contract. The supported Phase 1 surface is
the local Antigravity integration described in `docs/architecture.md`.

All implementation and deployment statements below are historical captures
from 2026-08-27. The MCP server, multi-vendor fleet, and claimed deployed
Cloud Run fleets described in those captures are retired and are not shipped
or evidence of the current runtime.

The goal, in the owner's words: Antigravity orchestrates the models in its own
environment locally; that syncs to a remote workspace; eventually several
Antigravity instances work against the same remote server.

This maps onto what already exists more closely than it might look, because the
hard part of phase 3 is a phase 1 decision. Written 2026-08-27.

---

## Phase 1 — Antigravity as a local orchestrator

**Historical capture — what existed:** an MCP server (`src/adk_harness/mcp_server.py`), packaged as
an Antigravity plugin (`plugins/antigravity/` — `plugin.json` + `mcp_config.json` +
`skills/` + `rules/`, installed to `~/.gemini/config/plugins`), exposing
governed Workspace operations — and, behind `ADK_HARNESSES=1`, each installed
coding harness — as tools. Verified by speaking MCP to it as a real client:
tools listed, deny path fired, audit recorded. See
[docs/PROOF.md](PROOF.md) §4 for a captured run and `plugins/antigravity/README.md` for
install steps.

**The IDE question is answered, and the answer is definitive.** Antigravity
IDE is a Code-OSS fork of VS Code 1.107.0, installed at
`/Applications/Antigravity IDE.app` — the `/Applications/Antigravity.app`
bundle is only a launcher that installs it. Its `extensionsGallery` points at
Open VSX, so ordinary `.vsix` extensions install normally. But Antigravity's
own agent (Cascade/Jetski, a Go binary at
`Contents/Resources/app/extensions/antigravity/bin/language_server_macos_arm`)
bypasses VS Code's chat and language-model subsystem entirely, and the
proposed `languageModelSystem` API a third-party extension would need in order
to register as a model provider is granted in `product.json` only to
`TeamsDevApp.ms-teams-vscode-extension`. **A third party cannot influence
Antigravity's own model selection.** MCP — plus the documented plugin bundle
format above — is the only supported extension surface for adding capability.

So phase 1 has two shapes, and they are not equivalent:

| Shape | Mechanism | Status |
|---|---|---|
| IDE delegates to external harnesses | MCP tools, packaged as the Antigravity plugin | working today — see `plugins/antigravity/` |
| IDE orchestrates its own models | would need `languageModelSystem`, restricted to one Microsoft extension in `product.json` | answered: not possible for a third party |
| SDK agent orchestrates subagents on different models | `google-antigravity`'s `LocalAgentConfig.models` + `.subagents` | supported by the SDK, not yet built; independent of the IDE question above |

The first row is what this project ships. The third remains open only as an
SDK-level pattern — a lead agent routing to subagents pinned to different
models — and has nothing to do with the IDE, since it runs outside it.

---

## Phase 2 — sync to a remote workspace

**Historical capture — what existed at the time:**

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
4. ~~Resolve the IDE question~~ — resolved (see Phase 1 above): the IDE cannot
   be made to orchestrate its own models from outside Google. Multi-model
   orchestration, if it is wanted, is an SDK-level pattern, not an IDE one.

Steps 1–3 stand on their own regardless of step 4, because they are true of
any client: an editor, a CLI, or a web UI.
