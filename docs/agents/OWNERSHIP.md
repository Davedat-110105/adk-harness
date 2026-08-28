# File ownership

Last updated: 2026-08-27.

## Current status

The audit remediation and feature-layout assignments are complete. No files
remain reserved by those assignments. The integrator handles the user's
requested commits and push; subagents do not write Git state.

The original task history is in [TASKS.md](TASKS.md). Those old filenames are
historical; use [architecture.md](../architecture.md) for current module paths
and [AUDIT_REMEDIATION.md](../AUDIT_REMEDIATION.md) for the remediation evidence.

## Shared files require coordination

| Files | Why |
|---|---|
| `src/adk_harness/coding/protocol.py` | Shared adapter contract; preserve its signatures |
| `src/adk_harness/governance/` | Policy, precedent admission and audit safety properties |
| `src/adk_harness/coding/registry.py` | Shared adapter discovery |
| `src/adk_harness/__init__.py`, `_compat.py`, feature `__init__.py` files | Public exports and compatibility |
| `pyproject.toml`, `package.json`, plugin manifests | Installation and dependency behavior |

Before parallel edits, assign one owner to each file. Report necessary changes
to another owner's file instead of silently editing it. Preserve unrelated
work, do not format files outside your assignment, and do not delete or rewrite
`.venv`. Adding dependencies requires an explicit integration decision.
