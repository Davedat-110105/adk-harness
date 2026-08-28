# adk-harness — an Antigravity plugin

Govern Google Workspace from inside Antigravity. Calendar and Gmail operations
become tools, each judged individually before it runs.

## Install

```bash
uv tool install --python 3.12 \
  'adk-harness[google-workspace] @ git+https://github.com/Davedat-110105/adk-harness.git@main'
gcloud auth application-default login --client-id-file=client_secret.json \
    --scopes=openid,https://www.googleapis.com/auth/cloud-platform,\
https://www.googleapis.com/auth/calendar.events,\
https://www.googleapis.com/auth/gmail.compose
adk-harness setup
```

If replacing an existing plugin, setup preserves it as `adk-harness.backup`
and refuses to overwrite an existing backup. Review and move that backup before
upgrading again.

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

An approval must come from the trusted host integration. The model cannot
self-approve or call a `remember_decision` tool; record precedents through the
host API after a person answers.

## Calling the tools

Parameters are **snake_case** — `calendar_id`, `max_results` — not the camelCase
in Google's REST docs. ADK converts them; camelCase raises `KeyError`.

## Configuration

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | your Google Cloud project |
| `ADK_SERVICES` | `calendar,gmail` by default; `docs` and `sheets` also supported |
| `ADK_TOOLS` | which operations to expose; the default is seven of the ~117 available |
| `ADK_LEDGER=1` | Enable the optional Firestore action ledger |
| `ADK_HARNESSES=1` | also expose Codex / Claude Code / opencode, if installed |

## Honest limits

- **Approvals are text, not a modal.** MCP has no confirmation channel: a held
  action returns "nothing has run". Only the trusted host integration may
  record the human's answer; the model cannot approve itself by chat.
- **Held writes stay held in the stock MCP plugin.** A host integration must
  record approved decisions through the Python API. The server does not load
  a legacy local precedent database or treat a chat reply as authorization.
- **Gmail sending is refused by policy, not merely absent.** Drafting is
  reversible; sending is not.
