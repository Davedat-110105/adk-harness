# Architecture and migration

This release is an Antigravity only local integration. The application owns
workspace boundaries, policy decisions, immutable workflow records, and audit
evidence. Official Google SDKs own authentication, service clients, and vendor
lifecycle behavior.

```text
src/adk_harness/integrations/antigravity.py  local SDK discovery and streaming
src/adk_harness/workspace/app.py             governed ADK Workspace toolsets
src/adk_harness/workflow/models.py           immutable request and evidence records
src/adk_harness/governance/{gate,precedents,stores,content_armor,ledger}.py
src/adk_harness/cli/main.py                  local auth, onboarding, and readiness commands
src/adk_harness/cloud/readiness.py            read-only official SDK readiness boundary
plugins/antigravity/                         native integration assets
```

The public package exports the current `WorkspaceApp`, `build_workspace_app`,
`AntigravityIntegration`, and the four workflow records. Workspace operations
are gated one tool at a time. An approval is valid only for the exact current
change hash, actor, scope, policy version, resource versions, and expiry.

The trusted local approval UI wires setup confirmation, workflow preview,
consent, Firebase Lite instructions, acknowledgements, manifest/result reads,
imports, and durable unknown recovery. Cloud deployment, effective IAM,
Eventarc auth-context provenance, popup login, and Workspace outcomes remain
explicit live proof boundaries.

## Breaking migration

The generic coding harness, multi-vendor adapters, fleet builder, and retired
server entrypoints were removed. Existing imports must migrate to the
Antigravity integration and `build_workspace_app`; there are no compatibility
aliases for the removed architecture. The old implementation and run records
remain historical evidence only. See [the migration note](migration-antigravity-only.md).
