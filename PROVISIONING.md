# Provisioned Google Cloud resources

Everything below was created and verified with the `gcloud` CLI and the Vertex
REST API on 2026-08-24. These are real resource ids, not placeholders.

## Project

| Field | Value |
|---|---|
| Project id | `model-creek-506520-u4` |
| Project number | `1054475334942` |
| Billing account | `01F5F5-10DD3E-2E965B` (CAD-denominated) |
| gcloud account | `tatandat110105@gmail.com` |

## Agent Engine — the GEAP Agent Runtime

| Field | Value |
|---|---|
| Resource | `projects/1054475334942/locations/us-central1/reasoningEngines/2214932639050104832` |
| `agent_engine_id` | `2214932639050104832` |
| Location | `us-central1` |
| Display name | `adk-harness-fleet` |

Memory Bank is configured on it via `contextSpec.memoryBankConfig`, using
`gemini-2.5-flash` for generation and `text-embedding-005` for similarity search.

```bash
export AGENT_ENGINE_ID=2214932639050104832
export GOOGLE_CLOUD_PROJECT=model-creek-506520-u4
export GOOGLE_CLOUD_LOCATION=global          # for model calls
export AGENT_ENGINE_LOCATION=us-central1     # for sessions and memory
export GOOGLE_GENAI_USE_VERTEXAI=true
```

### Verified working

```
SESSION CREATED: 4677253745082368
SESSION ROUNDTRIP: True
SESSIONS LISTED: 4
MEMORY BANK: VertexAiMemoryBankService ready
MEMORY SEARCH OK, hits: 0
```

Produced by `VertexAiSessionService(project, location, agent_engine_id)` and
`VertexAiMemoryBankService(project, location, agent_engine_id)` from ADK 2.7.1.
Zero hits is correct — the bank is empty.

## Enabled APIs

`aiplatform`, `run`, `artifactregistry`, `cloudbuild`, `firestore`,
`secretmanager`, `billingbudgets`.

## IAM

The Reasoning Engine service agent
`service-1054475334942@gcp-sa-aiplatform-re.iam.gserviceaccount.com` holds
`roles/aiplatform.user` in addition to its default
`roles/aiplatform.reasoningEngineServiceAgent`. Without the added role, Memory
Bank's embedding call fails with:

> 403 PERMISSION_DENIED ... Please ensure the Reasoning Engine service account
> has `aiplatform.endpoints.predict` permission.

Granting the role alone is not sufficient — `contextSpec.memoryBankConfig` must
also be set on the engine, or the same 403 persists. Both steps are required.

## Budget

| Field | Value |
|---|---|
| Budget id | `7f540bbb-52ea-4d2d-906d-6677d1326d51` |
| Display name | `devpost-agentic-hackathon` |
| Amount | 200 CAD (the billing account is CAD; this is roughly the $150 USD credit) |
| Scope | `projects/1054475334942` only |
| Alert thresholds | 50%, 90%, 100% |

A USD-denominated budget is rejected with `INVALID_ARGUMENT` on a CAD billing
account — the currency must match.

## Why Agent Engine and not Cloud SQL

An earlier draft of this design used Cloud SQL Postgres behind ADK's
`DatabaseSessionService`. That was replaced, for three reasons:

1. The hackathon's own cost guidance says to avoid dedicated, always-on database
   clusters. A Cloud SQL instance is exactly that; Agent Engine sessions and
   Memory Bank are usage-priced and idle at zero.
2. The Fortified Enterprise Fleet track names **Agent Runtime** and **Memory
   Bank** as its recommended components. These are those products, not
   substitutes for them.
3. It removes a provisioning step and a connection string from the spin-up
   instructions.

## Cost controls still to apply at deploy time

From the hackathon's cost guidance, applied when the example fleet is deployed:

- `--min-instances=0` so the service idles at zero.
- `--max-instances` set to a small ceiling to block runaway spend.
- Minimal CPU and memory on the Cloud Run service.
- Do not use `--allow-unauthenticated`; leave the endpoint authenticated so
  stray traffic cannot drain credits.
- Delete the Cloud Run service after the demo is recorded. The Agent Engine can
  stay — it costs nothing idle.

## Deprecation noticed

ADK 2.7.1's `VertexAiSessionService` emits:

> FutureWarning: The `vertexai.Client` class is deprecated. Please use
> `agentplatform.Client` instead.

Harmless today. Worth a note in the README if it starts appearing in demo output.
