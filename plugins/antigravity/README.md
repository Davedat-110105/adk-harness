# adk-harness — Antigravity native integration

Use the official Google Antigravity SDK and ADK Workspace toolsets from a local
Antigravity workspace. Every Workspace operation is evaluated by the governed
application before it runs.

## Install

```bash
uv tool install --python 3.12 \
  'adk-harness @ git+https://github.com/Davedat-110105/adk-harness.git@main'
gcloud auth application-default login --client-id-file=client_secret.json \
    --scopes=openid,https://www.googleapis.com/auth/cloud-platform,\
https://www.googleapis.com/auth/calendar.events,\
https://www.googleapis.com/auth/gmail.compose
adk-harness doctor
```

`doctor` checks whether the local Antigravity SDK can be discovered. It does not
log in, create a project, transfer Workspace data, or run a model. Configure
credentials through Google's supported tools and review the scopes before use.

## What the gate decides

| Operation | Decision |
|---|---|
| `calendar_events_list`, `gmail_users_drafts_get` | **allow** — reads only |
| `calendar_events_insert`, `gmail_users_drafts_create` | **ask** — others will see it |
| `gmail_users_messages_send` | **deny** — cannot be undone; a person sends |
| `calendar_acl_update` | **deny** — access is granted by people |
| anything unrecognised | **ask** — the policy fails closed |

An approval must come from the trusted host integration. The model cannot
self-approve. Versioned workflow records bind the request, exact change hash,
actor, scope, policy version, resource versions, and trace ID.

## Calling the tools

Parameters are **snake_case** — `calendar_id`, `max_results` — not the camelCase
in Google's REST docs. ADK converts them; camelCase raises `KeyError`.

## Configuration

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | your Google Cloud project |
| `ADK_SERVICES` | `calendar,gmail` by default; `docs` and `sheets` also supported |
| `ADK_TOOLS` | which operations to expose; the default is seven of the ~117 available |
| `GOOGLE_CLOUD_LOCATION` | Google ADK model location when a local run is explicitly enabled |

## Honest limits

- A held action means nothing has run. The person must approve it through the
  trusted host path; a chat response is not authorization.
- Sending mail and changing sharing permissions remain refused by policy.
- Trusted local onboarding and consent gated manual sync are available through
  `adk-harness onboard`. Cloud deployment, identity binding, and Workspace
  outcomes remain separately authorized live proof boundaries.
