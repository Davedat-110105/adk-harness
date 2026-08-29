# File ownership

Last updated: 2026-08-28.

## Current status

Phase 1 migration is assigned to `/root/phase1_architecture`. The integrator
handles commits and push; subagents do not write Git state.

The original task history is in [TASKS.md](TASKS.md). Those old filenames are
historical; use [architecture.md](../architecture.md) for current module paths
and [AUDIT_REMEDIATION.md](../AUDIT_REMEDIATION.md) for the remediation evidence.

## Phase 1 owner

The phase 1 owner may edit workflow models, Antigravity integration, package
and CLI configuration, plugin assets, retired architecture callers, and the
corresponding tests. Governance and Workspace behavior remains protected.

## Shared files require coordination

| Files | Why |
|---|---|
| `src/adk_harness/governance/` | Policy, precedent admission and audit safety properties |
| `src/adk_harness/__init__.py`, `_compat.py`, feature `__init__.py` files | Public exports and compatibility |
| `pyproject.toml`, `package.json`, plugin manifests | Installation and dependency behavior |

Before parallel edits, assign one owner to each file. Report necessary changes
to another owner's file instead of silently editing it. Preserve unrelated
work, do not format files outside your assignment, and do not delete or rewrite
`.venv`. Adding dependencies requires an explicit integration decision.
