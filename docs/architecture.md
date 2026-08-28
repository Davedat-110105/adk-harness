# Architecture and migration

The source is grouped by feature:

```text
src/adk_harness/coding/{protocol,registry,harness_agent,fleet,adapters}
src/adk_harness/governance/{gate,precedents,stores,content_armor,ledger}
src/adk_harness/workspace/app.py
src/adk_harness/mcp/server.py
src/adk_harness/cli/main.py
```

The public imports remain available from `adk_harness`. Compatibility names are
kept temporarily: `WorkspaceFleet`/`build_workspace_fleet`, `armor`, `stores`,
and `agent` point to their canonical replacements. New code should use
`WorkspaceApp`/`build_workspace_app` from the package root, or these feature paths:

| Feature | Canonical module |
|---|---|
| ADK agent wrapper | `adk_harness.coding.harness_agent` |
| Adapter contract and discovery | `adk_harness.coding.protocol`, `adk_harness.coding.registry` |
| Policy gate | `adk_harness.governance.gate` |
| Saved human decisions | `adk_harness.governance.precedents`, `adk_harness.governance.stores` |
| Content screening and audit | `adk_harness.governance.content_armor`, `adk_harness.governance.ledger` |
| Google Workspace tools | `adk_harness.workspace.app` |

`PersistentPrecedentStore` remains a deprecated alias for `SQLitePrecedentStore`.
`MatchResult` is available from the package root. Old module aliases share the
canonical module objects; there is no separate registry or runtime state.

Workspace operations are gated one tool at a time. Coding harness dispatch is
gated before the vendor process starts; calls made within that process require
the vendor's own permission hook.
