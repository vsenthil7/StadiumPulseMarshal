# Architecture & API Reference — StadiumPulse Marshal

![Architecture](images/architecture.svg)

## Design principles

1. **100% agentic, partner-first.** Observability and causal root-cause come
   from the **Dynatrace MCP server / Davis AI**; reasoning comes from
   **Google ADK / Gemini**. The agent is grounded in real Dynatrace facts rather
   than asked to invent infrastructure.
2. **Mock-first, live-ready.** Every external dependency has a real client *and*
   a mock behind one `USE_MOCKS` flag, with independent per-subsystem fallback.
   The app runs end-to-end with zero credentials and flips to live data when
   keys are present.
3. **Human-in-the-loop by default.** The agent recommends; a person decides.
   Optional guardrails auto-approve only low-risk actions within a severity
   ceiling. Every decision is audited.
4. **Single interface, swappable internals.** `ObservabilityClient` and
   `ReasoningAgent` are abstract; mock and live implementations are
   interchangeable, selected by factories.

## Module map

```
backend/app
├── core/            config (USE_MOCKS), logging, app context, static serving
├── models/          enums + Pydantic domain models (Problem, RootCauseNode, …)
├── fixtures/        deterministic matchday incident scenario
├── mcp/             ObservabilityClient: base · mock · Dynatrace (live) · factory
├── agent/           ReasoningAgent: base/mock · Gemini (live) · factory
├── services/        remediation planner · store (decisions + audit + guardrails)
├── api/             schemas · routes
└── main.py          FastAPI app, lifespan, WebSocket /stream, frontend mount

frontend/src
├── types/           TS mirrors of the domain
├── api/             fetch client
├── components/      RootCauseTree · Timeline · RemediationCard · SettingsPanel
├── styles/          design system
└── App.tsx          console composition
```

## Data flow

1. **Feed.** `GET /problems` (+ WebSocket `/stream`) via the observability
   client (Dynatrace live or mock).
2. **Analyze.** `POST /agent/analyze/{id}` → agent localises root cause,
   correlates with the matchday phase, ranks remediations, registers them, and
   applies auto-approve guardrails.
3. **Decide.** `POST /remediations/{id}/approve|reject` → audited decision.
4. **Apply.** `POST /remediations/{id}/execute` → transitions to EXECUTED
   (dispatches the runbook in live mode). Requires prior approval (else 409).

## API reference (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness. |
| GET | `/config` | Mode, backends, guardrail state. |
| GET | `/problems?open_only=` | List problems. |
| GET | `/problems/{id}` | One problem (404 if absent). |
| GET | `/entities` | Monitored entities. |
| GET | `/timeline` | Matchday fixture timeline. |
| POST | `/agent/analyze/{id}` | Agent analysis + remediations (404 if absent). |
| GET | `/remediations?pending=` | Remediation actions. |
| POST | `/remediations/{id}/approve` | Approve (audited). |
| POST | `/remediations/{id}/reject` | Reject (audited). |
| POST | `/remediations/{id}/execute` | Apply approved action (409 if not approved). |
| GET | `/audit` | Decision audit log. |
| PATCH | `/settings` | Update guardrails at runtime. |
| WS | `/stream` | Live open-problem feed. |

Interactive OpenAPI docs are served at `/docs` when the backend runs.

## Why these technologies (and the alternative)

**Dynatrace** is chosen for *causal* AIOps: Davis AI auto-instruments the stack
and localises the responsible entity, which beats hand-tuned metric dashboards
under matchday alert noise — and it is exposed over MCP for agentic use. The
alternative (Prometheus + Grafana + manual correlation, or Datadog) gives
correlation, not causation, so the agent would localise more slowly.

**Google ADK / Gemini** provides the reasoning and runbook drafting with
human-in-the-loop control via Agent Builder, hosted on Cloud Run. The agent is
deliberately grounded with deterministic candidate remediations so the LLM
selects and explains rather than fabricates.

## Testing

- **Backend:** `pytest --cov=app` → **100%** statement coverage (66 tests).
- **E2E:** Playwright specs across desktop + mobile projects (see
  `E2E_TESTING.md`). The single-origin stack they drive is validated by an HTTP
  smoke test.

---

## Phase 2 — Enterprise Depth

Phase 2 extends the vertical slice into an operations platform. New, strictly
modular subsystems:

### Domain (`app/models/`)
- `slo.py` — SLI / SLO / SLOMeasurement / ErrorBudget with burn-state.
- `incident.py` — Incident with a validated lifecycle state machine
  (`DETECTED → ACKNOWLEDGED → INVESTIGATING → MITIGATING → RESOLVED → POSTMORTEM
  → CLOSED`), escalation tiers, and a timeline.
- `notification.py` — on-call engineers, escalation policies, notifications.
- `venue.py` — venues, matches, matchday context (multi-venue).

### Persistence (`app/repositories/`)
Repository pattern with two interchangeable backends behind one factory:
in-memory and SQLAlchemy/SQLite (async). Services depend only on the interfaces
(`base.py`); the same contract tests pass against both backends.

### MCP protocol (`app/mcp/`)
- `protocol.py` — a real MCP JSON-RPC 2.0 client: `initialize`, `tools/list`,
  `tools/call`, content extraction, typed errors.
- `dynatrace_mcp_adapter.py` — uses the MCP session to satisfy
  `ObservabilityClient`, mapping tool results into the domain. The factory now
  prefers MCP-protocol → Environment-API → mock.

### Services (`app/services/`)
- `slo_engine.py` — error-budget + **burn-rate** computation. Burn rate is the
  current error rate over a short observation window divided by the
  budget-neutral rate, so fast/slow burn is detected before cumulative
  exhaustion. Classification is ordered by urgency (fast burn first).
- `incident_service.py` — orchestrates lifecycle, assignment, escalation and
  notification dispatch, and links remediation decisions onto the timeline.
- `escalation_engine.py` — policy-driven tier escalation + on-call routing.
- `notification_service.py` — builds and dispatches notifications.
- `analytics.py` — MTTR/MTTA and breakdowns by severity/state/venue.
- `ops_defaults.py` — default escalation policies, on-call roster, synthetic SLO
  measurements for mock mode.

### Scenarios (`app/fixtures/scenarios/`)
Four selectable matchday scenarios (payment DB saturation, CDN edge failure,
network partition, k8s OOM) across three venues, behind a registry. The mock
observability client is scenario-aware and switchable at runtime.

### API additions (`/api/v1`)
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/incidents` | List (paginated) / create from a problem. |
| GET | `/incidents/{id}` | Fetch one. |
| POST | `/incidents/{id}/transition` | Lifecycle change (409 on illegal). |
| POST | `/incidents/{id}/assign` `/note` `/escalate` | Ops actions. |
| GET | `/slo` | Error budgets with burn state. |
| GET | `/analytics` | Operational metrics. |
| GET | `/notifications` | Dispatched notifications (optionally by incident). |
| GET/POST | `/scenarios` `/scenarios/select` | List / switch scenario. |

Auth: when `auth_enabled`, all routes require an `X-API-Key` or a valid Bearer
JWT (`jwt_secret`). Pagination via `offset`/`limit`.

### Frontend
Refactored into a tab shell (`App.tsx`) plus page modules
(`pages/TriagePage`, `IncidentsPage`, `ReliabilityPage`, `ScenariosPage`) and new
components (`SLODashboard`, `AnalyticsPanel`, `ScenarioSwitcher`,
`IncidentLifecycle`).

### Testing
**135 tests, 100% backend statement coverage**, including a parametrised
repository contract suite run against both persistence backends.
