# Naming and layout audit

Scope: current repository paths only. This is an audit; no renames or moves are made here.

## 1. Core module names

| Current path | Rename or move to | Finding |
|---|---|---|
| `src/adk_harness/protocol.py` | Keep `src/adk_harness/protocol.py` | This is fine: it contains the vendor-neutral `Harness`, `HarnessSpec`, and `HarnessTurn` contract types, so “protocol” describes what the module is. |
| `src/adk_harness/registry.py` | Keep `src/adk_harness/registry.py` | This is fine: `HarnessRegistry` owns discovery and harness lookup, matching the module name. |
| `src/adk_harness/governance.py` | Keep `src/adk_harness/governance.py` | This is fine: `CoactraGovernance` and `AuditRecord` implement the policy gate and its decision audit trail. |
| `src/adk_harness/precedent.py` | Keep `src/adk_harness/precedent.py` for now | This is fine: it defines the precedent model, matching logic, and in-memory `PrecedentStore`; the name identifies the domain concept rather than an implementation detail. |
| `src/adk_harness/fleet.py` | Keep `src/adk_harness/fleet.py` | This is fine: `Fleet` and `build_fleet` assemble the orchestrator and worker harnesses, and “fleet” is the project’s established domain term. |
| `src/adk_harness/agent.py` | `src/adk_harness/harness_agent.py` | This is weak: the only production class is `HarnessAgent`, so the current generic “agent” name hides which kind of agent the module implements. |
| `src/adk_harness/stores.py` | `src/adk_harness/precedent/sqlite.py` after making `precedent` a package | This is the weakest name: the file currently contains only `SQLitePrecedentStore`, so the plural “stores” neither states the backend nor the stored domain object. |

The naming pattern is otherwise consistent: modules describe a domain role, while classes use the concrete `Harness...` or domain name. `agent.py` and especially `stores.py` are the exceptions because they are broader than their actual contents.

## 2. SQLite precedent store placement

| Current path | Rename or move to | Finding |
|---|---|---|
| `src/adk_harness/stores.py` | `src/adk_harness/precedent/sqlite.py` | Move the SQLite implementation beside the in-memory matcher and `PrecedentStore`; the implementation is specifically a precedent persistence backend, not a general store collection. |
| `src/adk_harness/precedent.py` | `src/adk_harness/precedent/__init__.py` | Convert the single module into a package only if the SQLite move is accepted, so `precedent.py` and its backend can share one discoverable namespace without a generic top-level `stores.py`. |
| `tests/test_stores.py` | `tests/precedent/test_sqlite.py` | Move the test with the implementation so the test name identifies both the precedent domain and SQLite backend. |

This package split is the clean long-term shape, but it is not required for correctness today; the current imports work and the store already subclasses `PrecedentStore` without changing the matcher.

## 3. Adapter names and harness ids

| Current path | Rename or move to | Finding |
|---|---|---|
| `src/adk_harness/adapters/codex.py` (`CodexHarness`, id `codex`) | Keep the path and class | This is fine: the class casing matches the Codex product name and its reported harness id. |
| `src/adk_harness/adapters/claude_code.py` (`ClaudeCodeHarness`, id `claude_code`) | Keep the path and class | This is fine: the compound module/class spelling consistently represents the `claude_code` id. |
| `src/adk_harness/adapters/opencode.py` (`OpencodeHarness`, id `opencode`) | Rename the class to `OpenCodeHarness`; keep the module path and id | The class is inconsistent with the product’s `OpenCode` casing: `OpencodeHarness` reads as one ordinary word even though the adapter id is `opencode` for the OpenCode harness. |
| `src/adk_harness/adapters/__init__.py` | Update its export from `OpencodeHarness` to `OpenCodeHarness` | The package export must use the same corrected class spelling or the inconsistency will remain at the public import surface. |

The filenames are fine as adapter ids: `codex.py`, `claude_code.py`, and `opencode.py` correspond to `codex`, `claude_code`, and `opencode`; only the branded class casing is off.

## 4. Tests layout and names

| Current path | Rename or move to | Finding |
|---|---|---|
| `tests/test_adapter_codex.py`, `tests/test_adapter_claude_code.py`, `tests/test_adapter_opencode.py` | Keep the paths | This is fine: all adapter tests use the same `test_adapter_<id>.py` convention, and the flat test directory makes the three related adapters easy to scan. |
| `tests/test_agent.py`, `tests/test_fleet.py`, `tests/test_governance.py`, `tests/test_precedent.py`, `tests/test_stores.py` | Keep the paths for the current size | This is fine: each test filename mirrors its corresponding top-level source module, while adapter tests add the shared `adapter` qualifier because their source files live below `src/adk_harness/adapters/`. |
| `tests/test_fleet_live.py`, `tests/test_governance_live.py` | Keep the paths | This is fine: the `_live` suffix consistently distinguishes environment-dependent tests from the offline module tests. |

The layout sensibly mirrors the source at its current size. If adapter coverage grows substantially, `tests/adapters/test_codex.py` and the analogous files would be a reasonable future mirror, but there is no present inconsistency worth introducing that move for.

## 5. Examples

| Current path | Rename or move to | Finding |
|---|---|---|
| `examples/fleet/agent.py` and `examples/fleet/__init__.py` | Keep `examples/fleet/` | This is fine: it is a deployable ADK application package, not merely a code snippet, and the package shape matches the documented `adk web examples` / Cloud Run usage. |
| `examples/dogfood.py` | Keep `examples/dogfood.py` | This is fine: it is a separate local dogfood script that imports the library directly, so a single-file example is clearer than wrapping it in a package with no current need for multiple modules. |

The mixed package/script shape is coherent because the examples represent different execution modes: `fleet/` is a deployable app, while `dogfood.py` is a local runner. No reorganisation is justified by the current two examples.

## 6. Documentation tree

| Current path | Rename or move to | Finding |
|---|---|---|
| `docs/agents/` | Keep `docs/agents/` | This is fine: `README.md`, `CONTRACT.md`, `OWNERSHIP.md`, and `TASKS.md` form a focused coordination area for contributing agents. |
| `docs/ROADMAP.md` | `docs/roadmap.md` | Rename this file to lowercase to match the lowercase directory names and the requested lowercase audit filename; the current uppercase basename is the only obvious docs naming mismatch. |
| `docs/audits/` | Keep `docs/audits/` | This is fine: audits are separated from operational agent instructions and project planning, and the requested `naming-and-layout.md` fits the directory’s purpose. |
| `docs/` | Add `docs/README.md` only if the tree grows | The current tree is navigable from the three obvious categories, so an index is not needed yet; add one when more top-level document categories or cross-links make discovery non-obvious. |

Overall, the docs tree has a sensible separation of concerns. The actionable issue is the `ROADMAP.md` casing; a landing page would currently be extra structure rather than a fix.
