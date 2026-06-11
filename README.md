# StadiumPulse Marshal

> AIOps matchday operations agent for the 2026 World Cup — **Dynatrace MCP**
> (observability + Davis AI causal root-cause) + **Google ADK / Gemini**
> reasoning, with human-in-the-loop remediation.
> Google Cloud Rapid Agent Hackathon · **T6 — Dynatrace**.

When matchday systems (ticket scanning, payments, app backends, networks)
degrade under extreme spikes, ops teams drown in alerts. StadiumPulse Marshal
localises the *causal* root with Davis AI, correlates it with the match
timeline, and proposes ranked remediation runbooks an SRE approves in one click.

![Triage view](docs/screenshots/01-console-triage.svg)

## Highlights

- **100% agentic, partner-first** — Dynatrace MCP for problems/Davis-AI
  root-cause; Gemini/ADK for reasoning and runbook drafting.
- **Mock-first, live-ready** — runs end-to-end with zero credentials; flips to
  live data per-subsystem when keys are present (`USE_MOCKS` flag).
- **Human-in-the-loop** — approve / reject / apply, configurable auto-approve
  guardrails, full decision audit log.
- **Enterprise console** — React/Vite/TS, mobile-responsive, configurable.
- **Tested** — 100% backend coverage (66 pytest tests); Playwright E2E across
  desktop + mobile.

## Quickstart (mock mode, no credentials)

```bash
# 1. Backend (API + agent) on :8000
cd backend
pip install -e .
python -m uvicorn app.main:app --port 8000

# 2. Frontend
cd ../frontend
npm install
npm run build          # single-origin: backend serves the UI at http://localhost:8000
# — or — npm run dev   # hot-reload dev server on :5173 (proxies /api)
```

Open <http://localhost:8000> (built) or <http://localhost:5173> (dev).

## Going live

Set credentials per [`docs/ACCESS_REQUIREMENTS.md`](docs/ACCESS_REQUIREMENTS.md)
and `USE_MOCKS=false`. Install the agent extra for the Gemini SDK:
`pip install -e .[agent]`.

## Tests

```bash
cd backend && pytest --cov=app --cov-report=term-missing   # 100%
cd ../e2e && npm install && npx playwright install chromium && npx playwright test
```

## Documentation

| Doc | What |
|---|---|
| [User Guide](docs/USER_GUIDE.md) | Screen-by-screen, with screenshots. |
| [Architecture & API](docs/ARCHITECTURE.md) | Design, modules, endpoints. |
| [Access Requirements](docs/ACCESS_REQUIREMENTS.md) | Credentials for live mode. |
| [E2E Testing](docs/E2E_TESTING.md) | Playwright setup & coverage. |
| [Sprint Tracker](docs/SPRINT_TRACKER.md) | Build progress per sprint. |

## Layout

```
backend/    FastAPI + agent + MCP clients + tests (100% cov)
frontend/   React + Vite + TypeScript console
e2e/        Playwright specs (desktop + mobile)
docs/       Guides, architecture, screenshots, sprint tracker
scripts/    Run helpers
```

## License

Built for AT-Hack0025. See partner terms for Dynatrace and Google Cloud usage.
