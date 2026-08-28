# Audit assessment and remediation

Date: 2026-08-27. Six Luna agents implemented separate fixes; the integrator
reviewed the combined changes and added regression and installation checks.
The user requested a feature-layout refactor, simple installation, and commit/push.
No live Workspace operations or deployments ran.

## Assessment

The specific security, lifecycle and usability findings were actionable.
Naming was lower priority and did not justify breaking existing imports.
The numerical audit scores are subjective; this pass does not assign replacement
scores or claim a complete security certification.

The packaging report was partly stale: `LICENSE` already existed. Conversely,
a fresh base installation found another real defect: importing the package
eagerly required the optional Google API client. Workspace toolset construction
is now lazy, and missing extras produce installation guidance.

## Changes and evidence

| Area | Implemented | Regression evidence |
|---|---|---|
| Workspace boundary | Canonical, existing directories required at MCP dispatch even with a custom allow policy; example policies use path containment | `test_mcp_server.py`, `test_example_policy_paths.py` |
| MCP approval | Removed model-callable `remember_decision`; arbitrary harness instructions require approval; old MCP precedent database is not automatically loaded | `test_mcp_server.py` |
| Precedent scope | Saved host decisions bind tool, principal, tenant, namespace and cwd; negative approval does not authorize execution; concurrent requests require a specific confirmation ID | `test_governance.py` |
| Armor and ledger | Shared governance pipeline covers decisions, holds, errors, cancellations and quarantines; distinct invocations receive distinct IDs; required pre-execution ledger failure stops execution | `test_governance.py`, `test_mcp_server.py` |
| Audit data | No raw argument values stored by default; optional explicit field allowlist still respects denied field names | `test_ledger.py` |
| Lifecycle | Wrappers close their own stream rather than the shared harness; Codex processes and OpenCode clients/tasks are owned per run | `test_agent.py`, Codex/OpenCode adapter tests |
| Naming | Canonical `WorkspaceApp`, `build_workspace_app`, `content_armor`, `precedent_stores`, `harness_agent`, `check_workspace_service_access`; old public names retained; missing `MatchResult` exported | `test_public_api.py` |
| CLI | Real `setup`, read-only `doctor`, validated `new-adapter`; Codex login diagnostics use its native status command; other credentials are explicitly unverified | `test_setup_cli.py` |
| Discovery | Standard registry factory, stdlib entry-point discovery, isolated malformed extensions, discovered spec synchronization | `test_registry.py`, fleet tests |
| Docs/examples | One-adapter quickstart, real Workspace armor/ledger attachment, truthful manual cleanup, example prerequisites and executable adapter snippets, clarified task/roadmap history | Example policy and cookbook tests; compilation/link checks |
| Distribution | Explicit MCP dependency via ADK extra; runtime integrations in `all`; optional Workspace imports; bundled plugin copied for Docker; runtime files excluded from archives/images; wheel/sdist CI smoke job | `check_distribution.py`; fresh base wheel install |

Code and tests are now grouped under `coding`, `governance`, `workspace`, `mcp`,
and `cli`. ADK examples live under `examples/agents`; executable scripts under
`examples/scripts`. The former `dogfood.py` is now
`examples/scripts/run_fleet_on_repository.py`. Public imports remain compatible;
canonical and legacy modules share the same runtime state.

## Compatibility and behavior changes

- Import aliases remain; deprecated functions and legacy armor/store modules warn.
  `PersistentPrecedentStore` remains a deprecated alias for SQLite, not a generic backend.
- The MCP model cannot approve itself. A trusted host must implement its own
  human authorization flow; a chat message or caller-supplied name is not proof.
- `remember()` still allows a trusted host to choose task predicates within
  the mandatory identity/workspace bindings. When more than one question is
  pending, supply `confirmation_id` from the confirmation payload.
- `ADK_LEDGER=1` makes the pre-execution audit write required. A terminal
  recording failure after an action cannot undo that action; do not blindly retry it.
- The base install does not include Workspace API clients. Install
  `adk-harness[google-workspace]` or the runtime `all` extra when needed.
- `new-adapter` writes an adapter and test, not entry-point metadata. The adapter
  cookbook shows how a separately packaged adapter registers its factory.

## Verification

- Baseline: **127 passed, 4 skipped**.
- Pre-layout audit suite: **170 passed, 4 skipped**, on both ADK **2.7.1** and
  **2.8.0**. The skips are live tests, not exercised by this pass.
- `ruff check src tests`: passed.
- `pyright src`: zero errors and warnings.
- Example compilation, executable cookbook snippets and `git diff --check`: passed.
- Wheel and sdist build/content checks: passed; plugin, license and canonical
  modules present; `.env`, `.adk` and local databases absent.
- Fresh base wheel installation outside the checkout: imports, MCP, bundled
  plugin, CLI help and `pip check` passed. It resolved ADK 2.8.0, Coactra 0.7.0,
  and MCP 1.29.1. Missing Workspace extras returned actionable guidance.

## Installation and layout follow-up

- Final offline suite: **183 passed, 5 skipped** (four live model tests and the
  separately verified real uv installation test). With the real installation
  check enabled: **184 passed, 4 skipped**. Ruff and Pyright pass.

- npm global installation from Git wraps the packaged Python source through
  `uv tool run`, includes the Workspace extra, and preserves caller cwd. There
  are no postinstall scripts or hidden runtime installers. uv is a prerequisite.
- `adk-harness serve` runs stdio MCP. No-command invocation shows help rather
  than installing a plugin. `python -m adk_harness` preserves CLI exit codes.
- A Codex plugin and repository marketplace live under `plugins/adk-harness`
  and `.agents/plugins/marketplace.json`. Its runtime source is pinned to the
  verified runtime commit; it is not an official catalog listing.
- Antigravity setup stages replacements, preserves a backup, and rolls back
  a failed replacement. Adapter scaffolding refuses symlinked ancestors.
- Antigravity plugin files live under `plugins/antigravity` and ship inside the
  Python wheel. Runtime `.env` files, sessions, and databases stay out of builds.
- Fresh base and `[all]` wheel installations outside the checkout passed
  imports, plugin lookup, CLI help, and dependency checks. The self-referencing
  `all` extra resolved correctly with uv; no dependency duplication was needed.
- A packed npm tarball installed under a temporary prefix and launched
  `serve --help` through real uv successfully. The MCP subprocess handshake,
  tool listing, and `governance_audit` call passed without Google credentials.
- Python documentation blocks compile and local Markdown links resolve.

## Not completed or deliberately unchanged

- **Docker runtime/build verification is blocked:** the Docker daemon is not running.
  CI now includes release-archive checks, but remote CI has not run in this pass.
- Six previously tracked `.env` and `.adk/session.db` files were removed from
  Git tracking, retaining their local copies under the original example paths.
  This does not erase their contents from existing Git history; no history
  rewrite or credential rotation was performed.
- No credentials were rotated, no historical database records were rewritten,
  and no live model/API or production infrastructure claims were revalidated.
- The package is not published to npm/PyPI. Git-based installation is supported;
  bare `npm install -g adk-harness` awaits a separately authorized publication.
- Codex plugin manifests and runtime were checked; installing into the user's
  personal Codex configuration was not performed.
- The frozen `Harness` protocol remains unchanged. Stronger event typing is a
  potential API design change, not a necessary repair for these defects.
- Coding-harness inner commands remain outside this library's policy gate.
  The docs state this boundary; per-command mediation needs vendor-specific
  permission hooks and was not fabricated here.
- Content armor is local defensive screening, not a guarantee against prompt
  injection or an integration with Google's managed Model Armor service.
