# Working on adk-harness

This directory is the contributor coordination surface for the Antigravity only
package. Read these documents before editing:

1. **[CONTRACT.md](CONTRACT.md)** — immutable workflow records, policy gates,
   identity bindings, and approval rules.
2. **[OWNERSHIP.md](OWNERSHIP.md)** — file ownership and protected areas.
3. **[TASKS.md](TASKS.md)** — current migration tasks and historical records.

The supported product surface is the official Google Antigravity SDK and the
governed ADK Workspace application. Runtime code owns workflow semantics,
scoped policy decisions, local recording, and audit evidence. Official Google
SDKs own authentication and service lifecycles.

Contributors should use the repository virtual environment, keep vendor imports
lazy when runtime discovery needs them, and run offline tests without live
credentials. Verify installed SDK behavior against the machine rather than
guessing at vendor contracts. Do not run cloud deployments or paid models as a
routine test.

The generic coding harness, multi-vendor adapters, and retired server
entrypoints were removed in the Phase 1 breaking migration. New work should use
`AntigravityIntegration`, `build_workspace_app`, and the versioned workflow
records. Historical task notes may mention retired names, but they are evidence
of earlier work and are not current implementation guidance.
