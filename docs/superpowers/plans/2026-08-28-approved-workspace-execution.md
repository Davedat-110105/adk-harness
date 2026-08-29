# Approved Workspace Execution Implementation Plan

> **Superseded in part on 2026-08-29.** This plan forbids MCP. A Workspace MCP
> server now ships anyway, because MCP is the only way Antigravity accepts new
> tools; skills and rules are text. The prohibition still holds for the generic
> coding-harness server this plan retired. See `docs/architecture.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Track completion with the checkboxes below. Claim implementation files before editing; the integrator owns commits.

**Goal:** Implement an Antigravity-only enterprise workflow: Google login, approved GCP onboarding, Workspace tasks, and user-approved local/cloud sync.

**Architecture:** Antigravity invokes the local ADK Harness application without MCP. Official Google SDKs handle cloud and Workspace access; Firestore task requests trigger Eventarc and reusable Cloud Run functions/jobs. A deterministic gate enforces permissions, policy, and human approval; mandatory read-only AI review flags concerns but cannot grant approval or override policy.

**Tech stack:** Python 3.12+, Google ADK, Coactra, SQLite, official Google/Firebase SDKs, Firestore, Eventarc, Cloud Run, Secret Manager, OpenTelemetry; a small local approval UI using Firebase's official JavaScript SDK.

**Spec:** The user's three diagrams plus the subsequent instructions to remove MCP, remove multi-vendor harness support, and require official Google service SDKs. Planning baseline: `96a06aa`; this revision changes the plan only.

## Acceptance contract

- Diagram 1 defines onboarding; diagram 2 defines approval; diagram 3 defines cloud infrastructure.
- The later approval rule wins: no automatic task, artifact, or history sync. Upload/run approval, exact-change approval, and result/history download approval are distinct; the UI may collect them together if each scope is explicit. User-initiated login and approved setup requests are separate from task-data sync.
- Record activity immediately where it occurs. Local events stay local until upload approval; cloud actions retain cloud evidence even when download is pending.
- No MCP servers, transports, configurations, or MCP-based editor integrations. No dedicated cloud routing/sync backend. Antigravity uses a local CLI/native integration; Google service calls use official SDKs.
- One reusable deployment template per selected real GCP project; application workspaces are isolated namespaces within it.
- Antigravity is the sole coding vendor. Delete (remove fully from current codebase and existing support) the generic `coding/protocol.py`, registry, fleet, vendor adapters, and associated compatibility exports. This is an intentional breaking migration, not a compatibility-preserving opt-in feature. The user's instruction supersedes the earlier frozen-protocol requirement; update repository contracts before implementation removes it.
- Preserve the reusable policy gate, scoped identity checks, content screening, and audit protections. Existing precedents cannot substitute for explicit upload/apply approvals.
- Official Google SDKs are mandatory for supported Google integrations. Do not implement custom REST clients, OAuth exchanges, Workspace connectors, service discovery, or vendor fallback logic. Custom code is limited to our workflow, approvals, configuration, recording, and SDK orchestration. A missing SDK capability must be reported, not silently replaced with custom HTTP.
- GCP APIs cover supported cloud/Workspace operations; they do not observe every local Antigravity command or file edit. Keep explicit local recording through supported Antigravity hooks/events.

## Required SDK choices

| Area | Implementation |
|---|---|
| Calendar, Gmail, Docs, Sheets | Existing official ADK `CalendarToolset`, `GmailToolset`, `DocsToolset`, `SheetsToolset`; use official `google-api-python-client` where a toolset does not expose a required operation. |
| Google login and credentials | `google-auth`, `google-auth-oauthlib`; Google sign-in in the approval UI through the official Firebase SDK. |
| GCP provisioning and jobs | Official Resource Manager, Cloud Billing, Service Usage, Cloud Run, Eventarc, and Secret Manager client libraries. |
| Firestore | Official Firebase JavaScript SDK for user-authorized UI operations; official `google-cloud-firestore` for trusted workers. No hand-written REST sync client. |
| Antigravity | Its existing local command/native integration; official `google-antigravity` SDK when native runtime access is required. No generic harness abstraction. |

Pin and test SDK versions for the supported deployment. Require the selected service dependencies; do not retain optional multi-vendor extras. SDKs own authentication protocols, API serialization, and service transport; our code owns approval and workflow semantics. See [Google API Python client](https://googleapis.github.io/google-api-python-client/) and [Firebase Google sign-in](https://firebase.google.com/docs/auth/web/google-signin).

## Implementation order

For each task: add targeted failing tests, implement the smallest change, run its checks, then review before continuing. Implement sequentially; these milestones share contracts.
Unqualified Python source paths below are relative to `src/adk_harness/`. Paths under `tests/`, `infra/`, `ui/`, `plugins/`, `docs/`, `.github/`, and repository packaging files are rooted at the repository.

### 1. Remove obsolete architecture and establish data contracts

**Files:** retire `coding/`, `mcp/`, and `mcp_server.py`; revise `__init__.py`, `_compat.py`, `cli/main.py`, `pyproject.toml`, `Dockerfile`, and packaging configuration. Remove `plugins/adk-harness/`, its marketplace entry, and `plugins/antigravity/mcp_config.json`; rewrite the Antigravity integration assets. Replace affected `tests/coding/`, `tests/mcp/`, MCP/Codex installation tests, fleet examples/scripts, and public-import tests. Create `workflow/models.py`, `integrations/antigravity.py`, `tests/workflow/test_models.py`, and `tests/integrations/test_antigravity.py`.

- [x] Capture the existing test baseline; update `docs/agents/CONTRACT.md`, `docs/agents/OWNERSHIP.md`, and `docs/agents/TASKS.md` to remove the old protocol-preservation mandate. Inventory imports before retiring files. Move only reusable Antigravity SDK integration into the single-vendor entry point; remove `Harness`, `HarnessSpec`, `HarnessTurn`, `HarnessRegistry`, `HarnessAgent`, and `build_fleet` dependencies after replacing their callers.
- [x] Remove the MCP `serve` entry point, server startup/configuration, adapter scaffolding/discovery, other-vendor extras, MCP plugin packaging, and obsolete compatibility aliases. Keep relevant governance/Workspace tests and migrate useful Antigravity lifecycle tests. Replace the old fleet demo rather than repairing and shipping a retired path. Update runtime/package smoke tests so no deleted module is imported.
- [x] Define versioned `TaskRequest`, `ChangeSet`, `Approval`, and `ActivityEvent` models. Bind IDs to project/workspace/user; include content hash, resource versions, timestamps, policy version, and trace ID. No credentials in these records.
- [x] Define task states: `draft -> submitted -> planning -> awaiting_approval -> applying -> completed`; also `held`, `blocked`, `failed`, `cancelled`, and `reconciling`. Reject invalid transitions and changed approval hashes.

### 2. Implement trusted Google login

**Files:** create `auth/google.py`, `auth/credentials.py`, `tests/auth/test_google.py`, `ui/approval/index.html`, `ui/approval/src/main.ts`, and `ui/approval/package.json`; extend `cli/main.py` and `tests/cli/test_setup_cli.py`.

- [x] Add status/login/logout commands using official Google OAuth flow and credential classes, including their state/PKCE and refresh support. Use secure OS credential storage and stop on cancellation or failure. The local approval UI uses official Firebase Auth/Firestore SDKs; bind its Google identity to the same verified account used for GCP and Workspace grants.
- [x] Separate provisioning credentials from Workspace grants. Derive identity from verified credentials; expose neither tokens nor an approval command to the model. Require explicit consent before storing a Workspace delegation grant in Secret Manager for cloud use.
- [x] Test login cancellation, expired/revoked tokens, missing scopes, and secret redaction. Use fake Google responses offline.

### 3. Select/create and bootstrap the GCP project

**Files:** create `cloud/projects.py`, `cloud/bootstrap.py`, `tests/cloud/test_projects.py`, `tests/cloud/test_bootstrap.py` under the corresponding source/test roots; add `infra/gcp/main.tf`, `variables.tf`, and `outputs.tf`.

- [x] Look up the target project; distinguish absence from denied access and transient errors. Before creation, show project ID, parent folder/organization, billing account, region, services, and proposed IAM grants for user approval.
- [x] Use official Google client libraries for Resource Manager creation/operation polling, billing linkage, and API enablement; use the Google Terraform provider for declarative runtime infrastructure. Configure the Firebase Google sign-in provider and approved UI origins during setup. Preserve IAM bindings with concurrency checks; use separate provisioning and runtime identities.
- [x] Persist setup checkpoints locally and resume partial setup without duplicate resources. Test rejection, insufficient permissions, operation timeout, quota failure, and retry. Never auto-delete a partially created project.

### 4. Connect the selected Workspace applications

**Files:** extend `workspace/app.py`; create `workspace/connections.py`; extend `tests/workspace/test_workspace_scopes.py` and add `tests/workspace/test_connections.py`.

- [x] Reuse official ADK Workspace toolsets with per-user credentials and an explicit application/tool/resource allowlist. Start with Calendar, then Gmail drafts, Docs, and Sheets. For missing toolset operations, use Google's official API client and place the same gate around each call; never create a parallel Workspace API implementation.
- [x] Verify access to selected resources before execution. Store only credential references in configuration. A cloud service account must not silently replace the approving user's Workspace authority.
- [x] Test missing consent, removed resource access, unsupported applications, and cross-user credential isolation. Preserve the current refusal to send mail or change sharing permissions.

Implementation note: pinned ADK 2.7.1 toolset constructors cannot accept the verified per-user credentials required here. The approved fallback uses Google's official API client with those credentials and bounded ADK read tools. Calendar and Docs support guarded host mutations; Gmail drafts and Sheets remain read-only where conditional mutation guarantees are unavailable.

### 5. Add approvals, durable local history, and manual sync

**Files:** create `workflow/approvals.py`, `workflow/outbox.py`, `workflow/sync.py`, and `ui/approval/src/sync.ts`; add `tests/workflow/test_approvals.py`, `test_outbox.py`, `test_sync.py`, and `ui/approval/tests/sync.test.ts`; add `infra/gcp/firestore.rules`.

- [x] Implement a SQLite outbox and trusted local approval UI. Approvals bind actor, project, exact payload hash, action/resource scope, resource versions, and expiry. Keep approval actions and credentials outside model-callable interfaces. A chat assertion or model-supplied `approved=true` is never sufficient; protect the local UI bridge with origin/session checks and do not expose a bypass flag.
- [x] Separate Firestore control records (task requests, approvals) from execution records (checkpoints, events) in two databases. Worker IAM gets read-only control access and scoped execution access. Use the official Firebase JavaScript SDK and Security Rules for user submissions; verify authorship, immutability, membership, hash binding, and expiry at commit. Do not substitute the Python server SDK for this user authorization path.
- [x] Implement preview/push/pull by orchestrating official SDK calls with stable event IDs, acknowledgements, approved download scope, and conflict reporting. No realtime listeners or SDK offline queues as the sync mechanism; never call cloud read/write methods before scoped consent. Test offline restart, duplicate uploads, tampering, expired grants, unauthorized namespaces, and zero project-data transfer before approval. History sync never replays actions.

### 6. Implement Eventarc execution and the action gate

**Files:** create `cloud/handler.py`, `cloud/worker.py`, `cloud/state.py`; extend `governance/gate.py`; add `tests/cloud/test_execution.py` and extend `tests/governance/test_governance.py`.

- [x] Trigger only immutable task-request creation, with `plan` or `apply` intent; never trigger from audit writes. Use authenticated Eventarc delivery and authentication-context events, validating the expected project/database/path and originating user rather than trusting actor fields. An approved proposal produces a new apply request. Validate approvals before accepting either request.
- [x] Use a short function to claim work transactionally and start a deployed worker/job. Persist leases, checkpoints, operation IDs, and results outside container memory. Ignore duplicate/completed requests; reconcile uncertain external outcomes before retrying.
- [x] Before every Workspace mutation, recheck the current user's access, policy, exact approval, and resource version. Block violations; hold stale/missing approvals. Test concurrent delivery, crash/restart, revoked access, changed proposals, and failure after an external write but before acknowledgement.

### 7. Add MANDATORY review and durable policy evidence

**Files:** create `workflow/reviewer.py`, `observability/tracing.py`; extend `governance/ledger.py`; add `tests/workflow/test_reviewer.py`, `tests/observability/test_tracing.py`; extend existing ledger tests.

- [x] Keep AI review enabled by default. Give it only approved context and read-only tools; findings hold the task for human review and cannot override a policy denial.
- [x] Propagate trace context across submission, Eventarc, worker, gate, and API calls. Store unsampled durable evidence containing authenticated actor, approval hash, policy version, decision, operation ID, and outcome; omit secrets and raw sensitive content.
- [x] Test reviewer injection attempts, missing review results, blocked actions, redaction, and trace correlation. Required pre-action audit failure blocks execution; post-action recording failure enters reconciliation.

### 8. Integrate, verify, and document the complete flow

**Files:** extend `cli/main.py`, `plugins/antigravity/skills/governed-workspace/SKILL.md`, `.github/workflows/ci.yml`, `pyproject.toml`, `package.json`, `bin/adk-harness.js`, `tests/check_distribution.py`, `tests/test_public_api.py`, `README.md`, `docs/architecture.md`, `docs/getting-started.md`, and `docs/PROOF.md`; add `tests/workflow/test_end_to_end.py` and `docs/migration-antigravity-only.md`.

- [x] Wire Antigravity's supported local command/native entry point to onboarding, submission, preview, and sync; the human approves through the trusted UI. Document replacement commands and removed public imports. Ship the approval UI assets, official SDK dependencies, and one-vendor runtime; remove MCP/fleet instructions from active docs, CI, distributions, and launchers. Label historical evidence as historical.
- [x] Run offline unit/integration tests, UI and Firestore Rules emulator tests, Ruff including examples, and Pyright. Verify fresh-install imports and CLI startup without any project-owned MCP server or generic harness code. Inspect the resolved dependency tree: remove our explicit MCP extras/dependencies without patching Google's SDK internals if MCP remains transitive. On Windows use `.venv\Scripts\python.exe -m pytest -q`; on Unix use `.venv/bin/python -m pytest -q`.
- [ ] With separate user authorization, deploy into a disposable GCP project and prove: login failure stops; creation requires consent; no approval means no transfer/write; one approved Calendar action runs; replay does not duplicate it; revoked permissions block it; history downloads only when approved; trace and ledger agree. Record the deployed commit SHA and clean up only approved test resources.

## Known caveats

- OAuth client registration, consent configuration/verification, Workspace admin restrictions, billing access, project quotas, and regional service availability can require manual setup. Login is not permission to create projects or read all Workspace data.
- Official SDKs do not erase authorization differences: Firebase user SDK requests use Security Rules; Google Cloud Python clients use IAM and bypass those rules. The small approval UI therefore uses official Firebase SDKs, while trusted workers use the Python SDK. Test both paths and database-level worker separation, including inherited grants. Firebase sign-in does not itself grant GCP or Workspace access. See [Firestore security](https://firebase.google.com/docs/firestore/security/overview) and [database isolation](https://firebase.google.com/docs/firestore/manage-databases).
- Eventarc invokes deployed code and may deliver duplicates out of order. It does not create a new function per task. Firestore transactions cannot atomically commit a Gmail/Calendar write; ambiguous outcomes need reconciliation. See [Firestore triggers](https://docs.cloud.google.com/run/docs/triggering/trigger-functions-with-firestore-documents).
- Approval-based sync prevents remote review of unuploaded local context. Cloud-generated results may be staged privately for review, but must not be published to Workspace before exact-change approval.
- Firestore is not Git, an automatic file merger, or administrator-proof immutable storage. Use Git/artifact references for versions; add retention-locked archival if required. OpenTelemetry is not the complete audit ledger.
- Removing other vendors and the generic harness protocol does not provide complete monitoring. GCP/Workspace APIs expose only supported remote events; local Antigravity file/shell activity still needs supported vendor hooks. Verify those capabilities against the installed official SDK; report gaps rather than inventing interception. External edits cannot be retroactively prevented.
- This deliberately breaks the old MCP/multi-vendor APIs. Inventory and migrate all callers; do not retain the removed architecture through compatibility shims. Google ADK may still depend on MCP internally: no MCP server or transport is used by this application, and SDK internals must not be forked just to remove a transitive package.
- Begin with one real Calendar workflow and one project. Multi-project views, comprehensive Workspace monitoring, stronger archival, and broad autonomous coding are follow-on work, not claims of this first milestone.
