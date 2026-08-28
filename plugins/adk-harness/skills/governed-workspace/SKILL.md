---
name: governed-workspace
description: Use ADK Harness MCP tools for Google Workspace and agent-harness actions, explaining policy decisions and stopping when an action is held or blocked.
---

# Governed workspace actions

ADK Harness evaluates each tool call before execution. Keep the active workspace as the server's
working directory and use the tool's snake_case arguments.

- `ALLOWED` means the operation ran; report its result.
- `HELD FOR APPROVAL` means nothing ran. Explain what would happen and ask the person to approve.
- `BLOCKED` means nothing ran. Report the policy reason and stop; do not retry or rephrase.

Never send Gmail messages or change sharing/access controls through a workaround. Drafting mail and
reading workspace data are distinct operations. Do not invent dates, recipients, calendar IDs, or
credentials. Authentication is supplied by the user's environment; if `uvx`, Python, or Google
credentials are unavailable, report the startup diagnostic and give the user the command to fix it.

The model cannot approve its own held action or record a precedent. A trusted host may record a
person's decision after they answer. Use `governance_audit` when asked why an action was allowed,
held, or blocked.
