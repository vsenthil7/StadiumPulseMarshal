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
