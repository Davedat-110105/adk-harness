# File ownership

Several agents work in this repository at once. A file has at most one owner.
Claim before you write; if what you need is already claimed, report it rather
than editing it anyway.

Last updated: 2026-08-25.

## Currently claimed

| Files | Owner | Task |
|---|---|---|
| `src/adk_harness/adapters/codex.py`, `tests/test_adapter_codex.py` | agent-codex-adapter | [TASKS.md](TASKS.md) task 1 |
| `src/adk_harness/adapters/claude_code.py`, `tests/test_adapter_claude_code.py` | agent-claude-code-adapter | [TASKS.md](TASKS.md) task 2 |
| `src/adk_harness/agent.py`, `src/adk_harness/fleet.py` | integrator | [TASKS.md](TASKS.md) tasks 3 and 4 |

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
