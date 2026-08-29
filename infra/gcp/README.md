# GCP bootstrap template

The local bootstrap orchestrator uses the official Resource Manager, Cloud
Billing, Service Usage and IAM clients to select or create the project, link
billing, enable APIs, and preserve IAM policy etags. It records every intent in
SQLite before a mutating call and never deletes a partially created project.

This template is pinned to Terraform 1.16.0 and signed `google` and
`google-beta` 8.0.0 providers. Firebase project and Web app resources use the
preview beta provider. The Google Web OAuth client and secret are manual
prerequisites and are separate from the local Desktop OAuth client. Terraform
state and saved plans contain the Web secret even when variables are marked
`sensitive`; use an encrypted, access controlled backend and never commit
state, plans, tfvars, or OAuth JSON.

Firestore Rules are deliberately not Terraform resources. The official
`firebaserules.v1` client publishes and verifies one named release per database
with the required `attachmentPoint`, beginning with the phase 3 deny-all source
and later receiving the combined guarded phase 5 source. The Eventarc Standard
trigger targets the authenticated Cloud Run receiver service; the receiver may
start the separately authorized Cloud Run worker job. This template does not
claim a direct Standard Eventarc-to-job destination.

Before any deployment, review inherited IAM grants and confirm the watched
Firestore and Eventarc locations match. Only `fmt`, `init -backend=false`, and
`validate` are permitted for this phase; do not run plan, refresh, or apply.
