# The phase 1 contract

This repository is an Antigravity only local integration. Google ADK and the
official Google Workspace SDKs own vendor lifecycles and authentication. The
application owns governance, workspace boundaries, immutable records, and
audit evidence. Records describe intent and approval; they never grant
permission. The policy gate is the only authority that permits an action.

`TaskRequest`, `ChangeSet`, `Approval`, and `ActivityEvent` are versioned,
deeply immutable, canonical JSON records. Their hashes bind project,
workspace, user, scope, policy version, resource versions, and trace ID.
Credentials and credential-shaped values are forbidden. Timestamps are
timezone-aware UTC values. Unknown schema versions and invalid state
transitions must be rejected.

Task states are `draft -> submitted -> planning -> awaiting_approval ->
applying -> completed`, with explicit `held`, `blocked`, `failed`,
`cancelled`, and `reconciling` outcomes. An approval is valid only for the
exact current change hash and its unexpired validity window.
