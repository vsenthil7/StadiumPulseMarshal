# Access Requirements — StadiumPulse Marshal

> The application runs **end-to-end today** using built-in mock fixtures. The
> items below are required only to switch to the **live** data/agent path.
> Set `USE_MOCKS=false` in `.env` once credentials are present.

---

## 1. Dynatrace (Partner Track T6)

| Item | Purpose | Env var |
|---|---|---|
| Tenant URL | Base of your Dynatrace environment, e.g. `https://abc12345.live.dynatrace.com` | `DT_TENANT_URL` |
| Platform / API token | Read problems, entities, events, metrics; access Davis AI | `DT_API_TOKEN` |
| MCP server endpoint | Dynatrace MCP server URL exposing problems/events tools | `DT_MCP_URL` |
| MCP auth (OAuth client id/secret **or** token) | Authenticate the MCP session | `DT_MCP_CLIENT_ID`, `DT_MCP_CLIENT_SECRET` |

**Required token scopes**
- `problems.read`
- `entities.read`
- `events.read`
- `metrics.read`
- `securityProblems.read` (optional, for security signals)

**How to obtain:** Dynatrace → *Access Tokens* → create token with the scopes
above. For MCP, enable the Dynatrace MCP server and create an OAuth client under
*Settings → Integration → Platform tokens / OAuth clients*.

---

## 2. Google Cloud (Agent + Gemini)

| Item | Purpose | Env var |
|---|---|---|
| GCP Project ID | Project hosting Gemini / Agent Builder | `GOOGLE_CLOUD_PROJECT` |
| Region | Vertex region, e.g. `europe-west2` | `GOOGLE_CLOUD_LOCATION` |
| Service account JSON **or** API key | Auth for Gemini via Vertex AI / AI Studio | `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_API_KEY` |
| Vertex AI API enabled | Gemini model access | — |
| Agent Builder / ADK enabled | Agent runtime | — |

**Model:** defaults to `gemini-2.0-flash` (override via `GEMINI_MODEL`). Use a
Gemini 2.5/3 model id when available in your project.

**Roles for the service account**
- `roles/aiplatform.user`
- `roles/run.invoker` (deploy only)
- `roles/run.admin` + `roles/iam.serviceAccountUser` (deploy only)

---

## 3. Deployment (optional — Cloud Run)

| Item | Purpose |
|---|---|
| Cloud Run admin | Deploy backend + frontend services |
| Artifact Registry | Store container images |
| `gcloud` CLI authenticated | Build & deploy |

---

## Quick check

```bash
# Backend reports which mode it is running in:
curl localhost:8000/api/v1/config | jq '.data_source'
# -> "mock"  (no creds)   or   "live"  (creds present + USE_MOCKS=false)
```

When any required live credential is missing, the service logs a warning and
automatically falls back to mock data for that subsystem, so partial credentials
are fine during incremental bring-up.
