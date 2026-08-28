# Hackathon disclosure

Submitted to the Devpost "All Things Agentic" hackathon, submission window
2026-08-03 to 2026-08-31.

The rules require that the submitted work be created during the submission
window, that standard libraries and frameworks are permitted, and that any
pre-existing code be disclosed. This document is that disclosure.

## Built during the submission window

Everything in this repository. It was created on 2026-08-24 and its entire git
history falls inside the submission window.

- The `Harness` protocol and its `HarnessSpec` / `HarnessTurn` value types
- `CoactraGovernance`, the ADK plugin that gates every tool call on a policy
  decision and records an audit trail
- The precedent store and its matcher
- `HarnessRegistry` — discovery, versioning, capability lookup
- `HarnessAgent`, the ADK `BaseAgent` wrapper
- The Claude Code, Codex, opencode, and Antigravity adapters
- Google Workspace governance (`src/adk_harness/workspace.py`) on ADK's
  official toolsets, exposed over MCP (`src/adk_harness/mcp_server.py`) and
  packaged as an Antigravity plugin (`plugin/`)
- The Google Cloud provisioning: Agent Engine, Memory Bank configuration,
  budget, IAM
- All documentation, the architecture diagram, and the demo

Verify with `git log` — the first commit is dated 2026-08-24.

## Pre-existing dependencies

### coactra

`coactra` is an existing open-source Python library by the same author,
published on PyPI and developed from 2026-06-01 onward. It predates the
submission window: of its 165 commits, 158 are earlier than 2026-08-03, and
versions 0.2.2 through 0.5.0 were released before the hackathon began.

**It is used here as a third-party dependency, installed from PyPI like any
other package.** This project depends on `coactra>=0.7.0,<0.8` for its policy
primitives — `Policy`, `PolicyRequest`, `Scope`, `Decision`, and
`DecisionOutcome`. No part of `coactra` is claimed as hackathon work.

Seven commits were made to `coactra` during the window, and versions 0.6.0 and
0.7.0 were released from them. None of that work is claimed as part of this
submission. It is disclosed here rather than omitted because the submission
does now depend on one of those releases: it installs the published 0.7.0
wheel, not the 0.5.0 one it originally targeted.

What changed in those releases was coactra's own housekeeping — a package
rename, a trimmed public surface, and a documented policy-request vocabulary.
The five primitives this project imports are unchanged in shape across 0.5.0,
0.6.0 and 0.7.0. The dependency became newer; it did not become a place where
submission work was hidden.

- Repository: https://github.com/DataOpsFusion/coactra
- Package: https://pypi.org/project/coactra/

### Standard frameworks and SDKs

Used as dependencies, not authored here: `google-adk`, `google-genai`,
`google-cloud-aiplatform`, `claude-agent-sdk`, the Codex CLI, `httpx`,
`pydantic`, `hatchling`, and `pytest`.

### AI coding tools

Claude Code and the Codex CLI were used while writing this project, which the
rules permit. They are also the subject of the project — the adapters drive
these same tools — so their use is disclosed twice over.

## Not used

No pre-existing application code, templates, or prior hackathon submissions
were carried into this repository. Git history has not been rewritten.
