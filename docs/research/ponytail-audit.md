# ponytail-audit: adk-harness

Read-only, repo-wide over-engineering audit. Nothing edited. Ranked by
what can be deleted soonest for the most benefit, per hackathon time
pressure. Two buckets: **safe today** (zero decision needed, zero
functional loss) and **needs a decision** (large, but something else in
the tree currently depends on it, or it contradicts a still-checked-in
plan doc).

## Headline finding

The repo currently contains **three separate, non-overlapping
implementations** of "propose a Workspace action, gate it, get a human to
approve it, run it":

1. `workspace/app.py` + `workspace/connections.py` + `governance/*` — an ADK
   `LlmAgent`, a hand-maintained operation allowlist, and a `coactra`
   policy-engine plugin with a precedent store and Firestore ledger.
2. `workflow/*` + `ui/approval/*` + the `LocalApprovalBridge` half of
   `auth/google.py` — a durable SQLite outbox, RFC 8785 canonical-JSON
   approval envelopes, and a 515KB browser bundle (Firebase JS SDK) that
   talks to Firestore Lite.
3. `workspace/tools.py` + `workspace/mcp_stdio.py` — written **today** — ~375
   lines total, no bundle, no Firebase project, no SQLite, no `coactra`. It
   derives the tool list from Google's own discovery documents, judges each
   call with a 10-line function, and collects approval through native MCP
   `elicit()`.

(3) is a strict, working replacement for the approval-collecting half of (1)
and (2). It is also lean and well-written — no findings inside
`workspace/tools.py` or `workspace/mcp_stdio.py` themselves. Everything
below is about (1) and (2) becoming dead weight now that (3) exists, plus a
few unrelated shims.

One wrinkle: `docs/superpowers/plans/2026-08-28-approved-workspace-execution.md`
("Acceptance contract") explicitly mandates *"No MCP servers, transports,
... No dedicated cloud routing/sync backend"* — that plan is what (2) was
built to satisfy. Today's `mcp_stdio.py` directly contradicts that plan. This
is why the big items below are filed as "needs a decision," not "safe
today": someone has to say out loud that the plan is superseded before the
~9,000 lines it justified come out.

---

## Safe to delete today

No product decision required, no other code path depends on the removed
names, only trivial one-line import fixes in two test files.

1. **`delete:`** `src/adk_harness/_compat.py` (15 lines) — injects
   `adk_harness.precedent`, `.ledger`, `.content_armor`, `.precedent_stores`
   into `sys.modules` as fake legacy import paths. Nothing in `src/` or
   `tests/` imports any of those four names (checked with grep across both
   trees). Cut the file and the `from . import _compat as _compat` line in
   `src/adk_harness/__init__.py:33`. **Replacement: nothing.** ~16 lines gone.

2. **`delete:`** `src/adk_harness/armor.py` (5 lines) and
   `src/adk_harness/stores.py` (22 lines) — pure re-export shims for a
   migration with no external consumers (this is a hackathon project, not a
   published package with back-compat obligations). Only two tests route
   through them: `tests/governance/test_content_armor.py:10`
   (`from adk_harness.armor import ContentArmor`) and
   `tests/governance/test_stores.py:10`
   (`from adk_harness.stores import SQLitePrecedentStore`). Point both at
   `adk_harness.governance.content_armor` / `adk_harness.governance.stores`
   directly (one line each), then delete both shim files plus the
   `PersistentPrecedentStore` deprecation alias and `__getattr__` in
   `src/adk_harness/__init__.py` (the `TYPE_CHECKING` import at line ~33,
   `"PersistentPrecedentStore"` in `__all__`, and the `__getattr__` function
   at the bottom, ~10 lines). **Replacement: direct imports.** ~37 lines gone.

3. **`yagni:`** `src/adk_harness/workspace/connections.py` hand-maintained
   `READ_OPERATIONS` / `READ_OPERATION_ORDER` / per-operation wrapper
   functions (lines 42-60+, most of the file's 790 lines) — a manually typed
   allowlist of six Calendar/Gmail/Docs/Sheets operations with bespoke
   request/response shaping. `workspace/tools.py`'s own docstring says the
   point of that file is "Nothing here enumerates operations by hand" — it
   derives the identical read/write judgment from Google's discovery
   documents in `build_tools()`/`decide()` (10-40 lines total). This file is
   the thing `tools.py` was written to replace. Not wired into the `mcp`
   command at all (only `workspace/app.py` and `cloud/worker.py` import it —
   see the "needs a decision" items below, since deleting it cleanly means
   deleting its only two callers too). **Filed here only as evidence; treat
   the actual deletion as part of item 1 below**, since `workspace/app.py`
   is what keeps it alive.

4. **Housekeeping, not a git change:** `tests/coding/__pycache__/*` and
   `tests/mcp/__pycache__/*` are stale compiled bytecode for source files
   that no longer exist anywhere in the tree (`git ls-files tests/coding
   tests/mcp` returns nothing — these directories aren't tracked). They're
   leftovers from the earlier "delete the multi-vendor coding harness"
   migration the plan doc mentions. `rm -rf tests/coding tests/mcp` cleans
   local disk only; no lines "removed" from the repo since git never had
   them.

**Safe-today total: ~53 lines of dead shim code deleted, 2 trivial test
import fixes, zero behavior change.**

---

## Needs a decision first

These are the actual mass. Ranked by size and by how directly they're
superseded by today's `mcp_stdio.py`.

### 1. `ui/approval/` (whole directory) + its build step — biggest single item

**What it is:** `src/main.ts` (1,020 lines) + `src/sync.ts` (514 lines), a
committed **515KB / 14,156-line** `dist/main.js` bundle (the entire Firebase
JS SDK — `firebase/app`, `firebase/auth`, `firebase/firestore/lite` —
bundled with esbuild), `canonicalize` (a JS reimplementation of RFC 8785
that mirrors the Python `rfc8785` package line-for-line in intent), plus a
test harness: `tests/main.test.ts` (463), `tests/sync.test.ts` (268),
`tests/support/probe-mounted-host.cjs` (297) and `.py` (85),
`tests/support/run-mounted-host.cjs` (18).

**What replaces it:** `src/adk_harness/workspace/mcp_stdio.py` (176 lines,
today). It does the exact "auto-allow reads, block sharing/sending, ask a
person for everything else" judgment via `context.elicit()` — no browser
tab, no Firebase project, no OAuth popup, no bundle. This is literally the
scenario the task brief describes: the host IDE renders the elicitation
inline and collects the approval.

**What depends on it today (why this isn't "safe"):**
- `src/adk_harness/auth/google.py:417-812` — `LocalApprovalSession` and
  `LocalApprovalBridge` (~395 of the file's 812 lines) exist solely to serve
  `/`, `/approval`, `/dist/main.js` (`google.py:611-636`) and proxy
  `/api/workflow/*` POSTs into `workflow/sync.py` (`google.py:644-720`+).
  None of this is touched by the `mcp` CLI command.
- `src/adk_harness/cli/main.py` — the `ui`/`onboard` command (`_ui`, uses
  `LocalApprovalBridge` at line 264) and five CLI flags that exist only for
  it: `--ui-root` (line 254), `--workflow-config`/`--outbox` (lines
  229-244), `--firebase-config` (line 161), `--cloud-destination` (line
  166).
- `pyproject.toml` — `tool.hatch.build.exclude` line 51-52 (dev copy of the
  bundle), `sdist.include` line 97, and **two `force-include` rules** (lines
  105, 115) that make `ui/approval/dist/main.js` a mandatory build input for
  *both* the sdist and the wheel. This is why `pip install .` cannot
  succeed without Node.js and a successful `npm run build` first — a pure
  Python package now hard-depends on an npm toolchain to build at all.
- `.github/workflows/ci.yml` — **every one of the 5 jobs** runs `npm ci
  --prefix ui/approval && npm run build --prefix ui/approval` (lines 26-29,
  70-73, 109-112, 144-147, 171-174), including `lint`, `base-install`, and
  `container`, none of which exercise the UI — they only need it because
  the wheel build silently requires the artifact to exist.

**Rough size if this whole branch goes:** ~2,670 lines of TS source, ~1,133
lines of TS test/support scaffolding, the 515KB bundle itself, ~395 lines of
`auth/google.py`, ~80-100 lines of `cli/main.py` plumbing and 5 CLI flags,
2 npm-only devDependency categories (`firebase`, `canonicalize`, `esbuild`,
`vitest`, `jsdom`, `typescript`, `@types/node`), 4 `force-include`/`exclude`
rules in `pyproject.toml`, and 5×2 lines of CI. **Once the bridge is gone,
nothing calls `workflow/*` either** (see item 2) — that's another 4,392
lines of source and 1,985 lines of tests that lose their only caller.

**Verdict:** yes, plainly removable, if the team is committing to the MCP
path. `mcp_stdio.py` already does the job in 176 lines. The only reason
this is "needs a decision" and not "safe today" is that the checked-in plan
doc says the opposite, and deleting the CI/pyproject wiring needs someone
to also decide the package no longer ships a browser artifact at all.

### 2. `workflow/` package (2nd biggest)

`sync.py` (2,443 lines — the single largest file in the repo), `outbox.py`
(682, SQLite-backed durable operation log with conflict detection),
`approvals.py` (263, trust envelopes bound to a Firebase UID),
`models.py` (647, versioned RFC-8785-canonical records with a
credential-redaction regex bank), `reviewer.py` (357, an ADK-based
mandatory review pass) — 4,392 lines, plus 1,985 lines of tests in
`tests/workflow/`. Every consumer of this package (`workflow_preview`,
`workflow_consent`, `workflow_ack`, `workflow_reconcile`,
`workflow_recovery` in `auth/google.py:644-660`) exists only to be called
from the browser bundle in item 1. Once `ui/approval` is gone this package
has no caller left. **Needs the same decision as item 1** — they come out
together or not at all.

### 3. `governance/` package + `coactra` dependency

`gate.py` (374), `ledger.py` (276), `precedents.py` (223),
`content_armor.py` (162), `stores.py` (183) = 1,218 lines, built on the
pre-1.0 `coactra==0.7.0` dependency (`Policy`, `Scope`, `PolicyRequest`,
`DecisionOutcome`, a precedent-matching store that "learns" from past human
decisions). This is a second, independent gate implementation for the same
problem `workspace/tools.py::decide()` (10 lines, `workspace/tools.py:129-138`,
zero dependencies) already solves for the identical Google APIs. Used only
by `workspace/app.py` (217 lines) and `cloud/worker.py`. **`yagni:`** a
general-purpose policy engine with a persistence layer, standing in for a
rule that is, in full: *reads auto-allow, `acl`/`permissions`/`send` are
always blocked, everything else asks a human.* Needs a decision because
`cloud/worker.py` (item 4) still calls it.

### 4. `cloud/` package

`bootstrap.py` (1,102), `worker.py` (1,406), `handler.py` (599),
`readiness.py` (396), `rules.py` (291), `projects.py` (266), `state.py`
(248), `entrypoints.py` (28) = 4,336 lines, plus `tests/cloud/` (1,607
lines) — a full second deployment target: a Cloud Run Job worker plus an
Eventarc/Cloud Functions receiver plus a Firestore work-item state machine.
**Nothing in the `adk-harness` CLI ever calls it** except `cli/main.py:295`,
which only invokes `RuntimeReadinessVerifier` for the `readiness`
diagnostic command — `worker_entry()`, `receiver_entrypoint()`, and
`BootstrapOrchestrator` are reachable only from `cloud/entrypoints.py`,
which is a Docker container entrypoint that CI's `container` job builds and
smoke-tests (`ci.yml:160-194`) but that the actual CLI/MCP demo flow never
runs. If this pipeline isn't part of what gets demoed, cutting it also
removes 7 GCP-only dependencies from `pyproject.toml`
(`google-cloud-run`, `google-cloud-eventarc`, `google-cloud-billing`,
`google-cloud-service-usage`, `google-cloud-resource-manager`,
`google-events`, `functions-framework`) and the entire `container` CI job.
`observability/tracing.py` (129 lines, `opentelemetry-exporter-gcp-trace`
dependency) is used only by `cloud/worker.py` and `workflow/reviewer.py`,
so it leaves with whichever of items 2/4 goes. **Biggest open question in
the whole audit:** is this cloud-hosted path still the product, or a
pre-pivot detour? It's the single largest chunk of code in the repo
(4,336 + 1,607 test lines) sitting behind one diagnostic-only CLI call.

---

## Not findings (checked, came back clean)

- `src/adk_harness/workspace/tools.py` and `mcp_stdio.py` (today's new
  code) — no speculative abstraction, no unused flexibility, no config
  knobs. `SERVICES`, `READ_METHODS`, `REFUSED_RESOURCES`/`REFUSED_METHODS`
  are the entire policy and every constant is read. Nothing to cut here.
- `rfc8785`/`canonicalize` as dependency choices are reasonable given what
  `workflow/*` does with them — Python has no built-in RFC 8785
  canonicalizer, so this isn't reinvented stdlib. They only exist to serve
  `workflow/*`, so their fate is tied to item 2, not an independent finding.
- `keyring` for OS-keychain-backed token storage is a normal, non-reinvented
  choice; not flagged.

---

## net

Safe today: **-53 lines**, 2 one-line test import fixes, 0 behavior change.

If the `mcp_stdio.py` direction is confirmed and items 1-4 are taken
together: **-9,000 to -10,000 lines** of source, **-3,600 lines** of tests,
**-515KB** binary bundle out of the git tree, **-1** npm toolchain (7
devDependencies + `package-lock.json`), **-8** Python dependencies
(`coactra`, `google-cloud-run`, `google-cloud-eventarc`,
`google-cloud-billing`, `google-cloud-service-usage`,
`google-cloud-resource-manager`, `google-events`,
`functions-framework`), and 4 of `ci.yml`'s 5 jobs stop needing Node.js at
all.
