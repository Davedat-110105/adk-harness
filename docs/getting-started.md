# Getting started

The supported package surface is a local Google Antigravity integration. Install
the native package with npm, or install the Python package directly:

```bash
npm install -g github:Davedat-110105/adk-harness
adk-harness --help
adk-harness doctor

# Python installation
python -m pip install 'adk-harness @ git+https://github.com/Davedat-110105/adk-harness.git'
```

The npm launcher uses `uv` to create an isolated Python 3.12 tool environment.
It passes arguments as an argument vector and does not install dependencies
into the caller's Python environment. The Python package includes the official
Google ADK, Antigravity, authentication, and Workspace client dependencies.

`adk-harness doctor` reports whether the installed Antigravity SDK is available.
It is a local diagnostic: it does not authenticate, call a model, create cloud
resources, or transfer task data.

For a local Workspace application, configure credentials through Google's
supported tooling and explicitly choose the Workspace scopes you need. Then
adapt the shipped example at `examples/agents/workspace/agent.py` for your own
policy and service allowlist. A Workspace write is held until a trusted host
records an approval; sending mail and changing sharing permissions are refused.

The immutable `TaskRequest`, `ChangeSet`, `Approval`, and `ActivityEvent`
records bind identity, scope, policy version, resource versions, timestamps,
and content hashes. They describe intent and evidence; they never grant
permission.

## Trusted onboarding and workflow UI

After provisioning login, launch `adk-harness onboard`. With a trusted workflow
configuration and SQLite outbox, pass `--workflow-config` and `--outbox`; the
browser then owns Firebase Lite calls and shows exact hashes, scopes, and
destinations before each consent. Unknown operations survive restart and can
only be reconciled after a new bounded read consent. Cloud deployment and live
Workspace proof remain separately authorized.
