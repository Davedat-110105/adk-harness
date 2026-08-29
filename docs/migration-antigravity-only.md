# Migration to the Antigravity only package

Phase 1 is an intentional breaking migration. The generic coding harness,
fleet builder, multi-vendor adapters, and retired server entrypoints are no
longer public APIs. Remove imports from the old `coding` and server packages;
use `AntigravityIntegration` for local SDK discovery and
`build_workspace_app` for governed Workspace toolsets.

Install the package without extras:

```bash
python -m pip install adk-harness
adk-harness doctor
```

The old plugin setup and server launch commands are not replacement paths. The
native assets in `plugins/antigravity/` are the supported integration surface.
The npm launcher requires `uv`, preserves the caller working directory, and
passes arguments without a shell.

Workflow records are now versioned and immutable. `TaskRequest`, `ChangeSet`,
`Approval`, and `ActivityEvent` carry canonical content hashes and identity and
resource bindings. An approval describes a human decision; it does not grant
permission or bypass the policy gate.

The trusted local UI now provides the setup handoff and consent gated workflow
preview, submission, upload, manifest, result download, and recovery routes.
Run `adk-harness onboard` after `adk-harness login --purpose provisioning`.
Remote deployment and Workspace execution still require separately authorized
live proof; no CLI flag or model response can approve them.
