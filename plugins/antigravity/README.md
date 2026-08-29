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
adk-harness install-plugin
adk-harness doctor
```

`install-plugin` copies this directory into `~/.gemini/config/plugins/adk-harness`,
which is where Antigravity looks for local plugins.

`doctor` checks whether the local Antigravity SDK can be discovered. It does not
log in, create a project, transfer Workspace data, or run a model. Configure
credentials through Google's supported tools and review the scopes before use.

## Which tools appear

Nothing here lists operations by hand. `connect_workspace` opens Google's
consent screen, and the tools are whatever the granted token covers. Google's
discovery documents declare every method and the scopes it accepts, so
approving Calendar alone yields Calendar operations and approving nothing
yields none.

## What the gate decides

The verb decides, read from the same discovery document.

| Operation | Decision |
|---|---|
| any `GET`, such as `calendar_events_list` | allow, a read of named resources |
| any `POST`, `PATCH`, `PUT` or `DELETE` | held, because others will see it |
| anything under `acl` or `permissions` | blocked, access is granted by people |
| anything ending in `send` | blocked, sending cannot be undone |

A held operation has run nothing. The server asks the person through MCP
elicitation, so the answer arrives from the client without passing through the
model. A client that cannot ask leaves the operation held.

## Calling the tools

Parameters use Google's own REST spelling, `calendarId` and `maxResults`, since
the server calls the discovery client directly. The snake_case form belongs to
the ADK toolsets used elsewhere in this package.

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
