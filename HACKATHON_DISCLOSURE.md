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
- The Claude Code, Codex, and opencode adapters
- The Google Cloud provisioning: Agent Engine, Memory Bank configuration,
  budget, IAM
- All documentation, the architecture diagram, and the demo

Verify with `git log` — the first commit is dated 2026-08-24.

## Pre-existing dependencies

### coactra

`coactra` is an existing open-source Python library by the same author,
published on PyPI and developed from 2026-06-01 onward. It predates the
submission window: 158 of its 160 commits are earlier than 2026-08-03, and
versions 0.2.2 through 0.5.0 were released before the hackathon began.

**It is used here as a third-party dependency, installed from PyPI like any
other package.** This project depends on `coactra>=0.5.0` for its policy
primitives — `Policy`, `PolicyRequest`, `Scope`, `Decision`, and
`DecisionOutcome`. No part of `coactra` is claimed as hackathon work.

Two commits were made to `coactra` during the window (exporting an existing
workspace memory contract and adding Vertex AI documentation). Neither is
claimed as part of this submission, and neither is required by it — the
submission runs against the published 0.5.0 wheel.

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
