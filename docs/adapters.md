# Adapter cookbook

Implement the frozen `Harness` protocol. Keep vendor imports inside discovery,
return `available=False` when a dependency is absent, and stream
`HarnessTurn` values without buffering a session.

The smallest useful offline matrix covers discovery with and without the
vendor, text/tool event mapping, and clean close during a stream. Fake the
subprocess or SDK; live credentials are optional and never required by tests.
See [examples/README.md](../examples/README.md) for an echo adapter and a
subprocess outline.


## Scaffold and register

In a checkout of this repository:

```bash
adk-harness new-adapter my_harness
python -m pytest tests/coding/adapters/test_my_harness.py -q
```

The command creates `src/adk_harness/coding/adapters/my_harness.py` and its
matching offline test, and refuses to overwrite files. It does not edit exports
or packaging. For an extension in your own package, register a zero-argument
adapter factory in that package's `pyproject.toml`:

```toml
[project.entry-points."adk_harness.adapters"]
my_harness = "your_package.adapter:MyHarness"
```

Install the extension in the same Python environment as ADK Harness, then use
`adk_harness.coding.registry.default_registry()`. An explicit
`HarnessRegistry([...])` includes only the supplied adapters. An npm/uv-managed
CLI runs in an isolated environment, so packages installed in a different Python
environment are not automatically visible to it.
