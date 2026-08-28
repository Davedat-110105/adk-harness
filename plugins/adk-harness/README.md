# ADK Harness for Codex

ADK Harness exposes policy gated Google Workspace and agent harness operations
through MCP. Reads may run immediately, reversible writes can be held for a
person's approval, and irreversible actions remain refused by policy.

## Install from Git

The repository includes a local marketplace definition. The commands below
use the Codex CLI syntax and pin the marketplace to its `main` branch:

```bash
codex plugin marketplace add https://github.com/Davedat-110105/adk-harness --ref main
codex plugin add adk-harness@adk-harness
```

Start a new Codex task after installation so it loads the plugin's MCP server
and skill. The server runs from the active task workspace (`cwd: "."`).

## Prerequisites

- Codex CLI with plugin support
- `uvx` and Python 3.12 available on `PATH`
- Google Application Default Credentials with the scopes needed for the
  services you enable

Set `GOOGLE_CLOUD_PROJECT` and, when using a credentials file, set
`GOOGLE_APPLICATION_CREDENTIALS` in the environment before starting Codex.
`ADK_SERVICES` defaults to `calendar,gmail`; `ADK_TOOLS` can narrow the exposed
operations. `ADK_LEDGER=1` enables the optional Firestore ledger and requires
its extra dependency and configuration.

If startup reports that `uvx`, Python, or credentials are unavailable, fix the
environment and start a new task. Credentials stay in the user's environment;
the plugin never asks the model to collect or print them.

## Safety behavior

Use snake_case tool arguments. A held result means nothing ran: explain the
proposed action and ask the person. A blocked result means nothing ran: report
the policy reason and stop. The model cannot approve a held action, record a
precedent, send Gmail, or change sharing permissions. Use `governance_audit`
when asked why an action was allowed, held, or blocked.
