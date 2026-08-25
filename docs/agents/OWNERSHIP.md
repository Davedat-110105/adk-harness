# File ownership

Several agents work in this repository at once. A file has at most one owner.
Claim before you write; if what you need is already claimed, report it rather
than editing it anyway.

Last updated: 2026-08-25.

## Currently claimed

Nothing. Tasks 1–4 are landed and committed; the files below are now ordinary
repository files under normal review, not held by anyone.

| Files | Landed by | Task |
|---|---|---|
| `adapters/codex.py`, `tests/test_adapter_codex.py` | agent-codex-adapter | task 1 — done |
| `adapters/claude_code.py`, `tests/test_adapter_claude_code.py` | agent-claude-code-adapter | task 2 — done |
| `agent.py`, `tests/test_agent.py` | integrator | task 3 — done |
| `fleet.py`, `tests/test_fleet.py`, `tests/test_fleet_live.py` | integrator | task 4 — done |
| `examples/fleet/` | integrator | Cloud Run deployment target |

## In flight — already assigned, do not edit this table

Two agents are working right now. Their claims are recorded here by the
integrator so that neither has to edit this file and collide with the other.

| Files | Owner | Task | Notes |
|---|---|---|---|
| `adapters/opencode.py`, `tests/test_adapter_opencode.py` | codex-luna | [task 5](TASKS.md) | third integration shape: HTTP + OpenAPI |
| `stores.py`, `tests/test_stores.py` | codex-luna | [task 6](TASKS.md) | persistent precedents; do **not** edit `precedent.py` |

The integrator is currently working in `governance.py`, `fleet.py`, and
`examples/fleet/`. Those are live — do not edit them.

## Frozen — nobody edits without clearing it first

| File | Why |
|---|---|
| `src/adk_harness/protocol.py` | The contract. Every adapter is written against it. |
| `src/adk_harness/governance.py` | The single policy gate. Adapters must not reach into it. |
| `src/adk_harness/precedent.py` | The precedent loop, with tests that pin its safety properties. |
| `src/adk_harness/registry.py` | Stable and vendor-neutral. |
| `src/adk_harness/adapters/__init__.py` | Every adapter wants to export here, so it is the one guaranteed collision. The integrator wires exports after adapters land. |
| `src/adk_harness/__init__.py` | Same reason. |
| `pyproject.toml` | Dependency changes are deliberate, not incidental. If your task needs a dependency, report it. |

Installing a package into `.venv` for your own task is fine — that is local
state, not a shared file. Adding it to `pyproject.toml` is not.

## Rules

1. **No git writes.** No `commit`, `push`, `checkout`, `stash`, `rebase`, or
   `reset`. Read-only git (`status`, `diff`, `log`) is fine. The integrator
   commits everything.
2. **Report, do not reach.** If your task appears to need a change to a frozen
   file or to a file someone else owns, stop and say exactly what change and
   why. That is more useful than a merge conflict.
3. **Do not reformat files you do not own**, and do not run a formatter across
   the repository.
4. **Do not delete or rewrite `.venv`.**
