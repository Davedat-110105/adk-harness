# adk-harness — an Antigravity plugin

Govern Google Workspace from inside Antigravity. Calendar and Gmail operations
become tools, each judged individually before it runs.

## Install

```bash
pip install "adk-harness[google-workspace]"
gcloud auth application-default login --client-id-file=client_secret.json \
    --scopes=openid,https://www.googleapis.com/auth/cloud-platform,\
https://www.googleapis.com/auth/calendar.events,\
https://www.googleapis.com/auth/gmail.compose

mkdir -p ~/.gemini/config/plugins
cp -r plugin ~/.gemini/config/plugins/adk-harness
```

Restart Antigravity. A service whose scope your credentials do not carry is
skipped with an explanation rather than exposed as a tool that always fails.

## What the gate decides

| Operation | Decision |
|---|---|
| `calendar_events_list`, `gmail_users_drafts_get` | **allow** — reads only |
| `calendar_events_insert`, `gmail_users_drafts_create` | **ask** — others will see it |
| `gmail_users_messages_send` | **deny** — cannot be undone; a person sends |
| `calendar_acl_update` | **deny** — access is granted by people |
| anything unrecognised | **ask** — the policy fails closed |

Approve once and `remember_decision` records it, scoped to that one operation.

## Calling the tools

Parameters are **snake_case** — `calendar_id`, `max_results` — not the camelCase
in Google's REST docs. ADK converts them; camelCase raises `KeyError`.

## Configuration

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | your Google Cloud project |
| `ADK_SERVICES` | `calendar,gmail` by default; `docs` and `sheets` also supported |
| `ADK_TOOLS` | which operations to expose; the default is seven of the ~117 available |
| `ADK_PRECEDENTS` | SQLite file, so approvals survive a restart |
| `ADK_HARNESSES=1` | also expose Codex / Claude Code / opencode, if installed |

## Honest limits

- **Approvals are text, not a modal.** MCP has no confirmation channel: a held
  action returns "nothing has run" and you approve by saying so.
- **Precedents are per-machine.** SQLite. Two people each answer their own
  questions until the store is shared.
- **Gmail sending is refused by policy, not merely absent.** Drafting is
  reversible; sending is not.
