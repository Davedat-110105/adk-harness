# adk-harness

Governed Google ADK Workspace applications for the official Antigravity local
integration. Calendar, Gmail drafts, Docs, and Sheets operations pass a policy
gate before they run.

## Install

The package is not published to npm or PyPI yet. The easiest install is:

```bash
npm install -g github:Davedat-110105/adk-harness
adk-harness --help
adk-harness doctor                 # optional local checks
```

This needs Git, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
uv downloads Python 3.12 if needed; the first launch installs the Python dependencies.
The npm launcher does not install the library into your own Python environment.
For Python code, use Python 3.12+ and install the library directly:

```bash
python -m pip install 'adk-harness @ git+https://github.com/Davedat-110105/adk-harness.git'
# Alternative standalone CLI (no npm):
uv tool install --python 3.12 'adk-harness @ git+https://github.com/Davedat-110105/adk-harness.git'
```

## First local check

Run `adk-harness doctor` to check discovery of the local Antigravity SDK. The
check does not make a model call or transfer Workspace data. See [Getting
started](docs/getting-started.md) for the local ADK example.

## Antigravity plugin

`adk-harness install-plugin` copies the packaged rules and skill into
`~/.gemini/config/plugins/adk-harness`, where Antigravity reads them. The app
lists the result under Settings, Customizations. Pass `--plugin-dir` to install
somewhere else. Reinstalling replaces the previous copy.

It also registers the MCP server in `~/.gemini/config/mcp_config.json`, keeping
any other servers already listed there. Pass `--mcp-config` to write elsewhere.

The copy alone needs no Python and no uv, so it also runs straight from npm:

```bash
npx -y github:Davedat-110105/adk-harness install-plugin
```

## Governance

Allowed actions run. Held actions have run nothing and require a human answer.
Blocked actions stop with a reason. A model cannot self-approve in chat; only a
trusted host API may record a precedent, scoped to the required principal,
tenant/namespace, and working directory bindings.

Workspace API operations are individually gated. Versioned workflow records
bind approvals to the exact request and resource versions.

## Examples and docs

- [Getting started](docs/getting-started.md)
- [Architecture and migration](docs/architecture.md)
- [Migration note](docs/migration-antigravity-only.md)
- [Examples](examples/README.md)
- [Captured proof](docs/PROOF.md) (historical evidence, not a current claim)

The native assets under `plugins/antigravity/` are the supported integration
surface. `adk-harness onboard` opens the trusted local setup/workflow UI;
`adk-harness readiness --handoff HANDOFF.json --select-project PROJECT.json`
performs only read-only checks and reports live proof as awaiting authorization.

## Layout

```text
src/adk_harness/{governance,integrations,workflow,workspace,cli}
examples/{agents,scripts}
plugins/antigravity
```

MIT license. See the migration note for removed public imports and breaking
changes.
