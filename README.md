# adk-harness

Governed Google ADK agents backed by coding harnesses. Fleet dispatches pass a
shared policy gate; inner file and shell calls inside a vendor process are
observed, not re-gated by ADK.

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
uv tool install --python 3.12 'adk-harness[google-workspace] @ git+https://github.com/Davedat-110105/adk-harness.git'
```

## First fleet

Follow the runnable Python example in [Getting started](docs/getting-started.md).
It creates a disposable sandbox and uses a read-only prompt. Vertex credentials
are required for the Gemini orchestrator (`gcloud auth application-default
login`, then set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION=global`).

## Governance

Allowed actions run. Held actions have run nothing and require a human answer.
Blocked actions stop with a reason. A model cannot self-approve in chat; only a
trusted host API may record a precedent, scoped to the required principal,
tenant/namespace, and working directory bindings.

Workspace API operations are individually gated. Coding harness dispatch is
gated at the fleet boundary; vendor inner actions need the vendor's permission
hook for per-action enforcement.

## Examples and docs

- [Getting started](docs/getting-started.md)
- [Architecture and migration](docs/architecture.md)
- [Adapter cookbook](docs/adapters.md)
- [Examples](examples/README.md)
- [Captured proof](docs/PROOF.md) (historical runs; not a live-test claim)

## Codex plugin

```bash
codex plugin marketplace add https://github.com/Davedat-110105/adk-harness --ref main
codex plugin add adk-harness@adk-harness
```

The plugin uses Git through `uvx` and the `google-workspace` extra. See
[plugins/adk-harness/README.md](plugins/adk-harness/README.md) for setup.

## Layout

```text
src/adk_harness/{coding,governance,workspace,mcp,cli}
examples/{agents,scripts}
plugins/{adk-harness,antigravity}
```

MIT license. See the focused docs for API details and compatibility aliases.
