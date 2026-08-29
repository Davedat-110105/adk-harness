# Phase 5E Rules test

This test uses the official Firebase Lite client for all browser assertions and
the official `google-cloud-firestore` Python client with `AnonymousCredentials`
for emulator-only fixture seeding. It refuses non-loopback emulator hosts and
requires the demo project guard.

With Firebase CLI available, run from the repository root:

```text
firebase emulators:exec --project demo-adk-wire --config .firebase-phase5e.json --only firestore "node tests/emulator/phase5e_rules.cjs"
```

The retained test generates complete fixtures through the production Python
workflow factories on every run. Do not reuse the generated JSON or run the
seeder against a live project. The test covers named `control` and `runtime`
databases, atomic plan/apply/history writes, exact owner reads, create-only and
list denial, identity and binding negatives, malformed runtime metadata, and
rejected-batch absence checks.

An emulator pass verifies Rules behavior and SDK serialization only. It does not
prove deployed IAM, Eventarc, worker provenance, or human consent enforcement.
