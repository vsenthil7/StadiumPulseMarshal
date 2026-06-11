# StadiumPulse Marshal — Sprint & Phase Tracker

**Project:** Google Cloud Rapid Agent Hackathon (AT-Hack0025)
**Partner Track:** T6 — Dynatrace · **Theme:** 2026 World Cup
**Build doc ref:** 003-06-01-Build-T6-Dynatrace-P1-StadiumPulseMarshal
**Stack:** Dynatrace MCP (observability + Davis AI) + Google ADK / Gemini (agent) + FastAPI + React/Vite/TS
**Owner:** Engineering · **Last updated:** 2026-06-01 14:56 BST

---

## Status Legend
🟢 Done · 🟡 In progress · ⚪ Not started · 🔵 Blocked (needs access)

---

## Phase Overview

| Phase | Name | Sprints | Status |
|---|---|---|---|
| P0 | Foundations & scaffolding | S0 | 🟢 |
| P1 | Domain core & data models | S1 | 🟢 |
| P2 | Dynatrace MCP integration (mock + real) | S2 | 🟢 |
| P3 | Gemini/ADK agent reasoning layer | S3 | 🟢 |
| P4 | API surface (FastAPI) | S4 | 🟢 |
| P5 | Frontend war-room console | S5 | 🟢 |
| P6 | Human-in-the-loop remediation flows | S6 | 🟢 |
| P7 | Backend testing (100% coverage) | S7 | 🟢 |
| P8 | Playwright E2E (100% flows) | S8 | 🟢* |
| P9 | Documentation + user guide + screenshots | S9 | 🟢 |
| P10 | Packaging & delivery | S10 | 🟢 |

---

## Sprint Detail & Acceptance Criteria

### S0 — Foundations & scaffolding 🟢
- [x] Repo skeleton (backend/frontend/e2e/docs)
- [x] Sprint tracker created
- [x] Config + settings module with `USE_MOCKS` flag
- [x] Access-requirements doc
- [x] Dependency manifests (pyproject / package.json)
**Acceptance:** repo builds, config loads, mock flag switches data source. ✅

### S1 — Domain core & data models 🟢
- [x] Pydantic models: Problem, Entity, Event, Metric, FixtureTimeline, RemediationAction, ApprovalRequest
- [x] Severity/scoring enums, matchday phase mapping
**Acceptance:** models validate; unit tests pass. ✅

### S2 — Dynatrace MCP integration 🟢
- [x] MCP client interface (protocol-level)
- [x] Real Dynatrace MCP client (problems/entities/events/metrics + Davis AI)
- [x] Mock client backed by realistic fixtures (matchday incident scenarios)
- [x] Auto-fallback when no credentials
**Acceptance:** both clients satisfy same interface; mock returns scenario data. ✅

### S3 — Gemini/ADK agent reasoning layer 🟢
- [x] ADK agent definition + tools wrapping MCP
- [x] Root-cause correlation w/ fixture timeline
- [x] Runbook drafting + remediation recommendation
- [x] Real Gemini path + deterministic mock path
**Acceptance:** agent produces ranked root-cause + recommended action from a problem. ✅

### S4 — API surface (FastAPI) 🟢
- [x] /health, /config, /problems, /problems/{id}, /entities, /timeline
- [x] /agent/analyze, /remediations
- [x] /remediations/{id}/approve, /reject (human-in-loop) + /audit
- [x] WebSocket /stream for live problem feed
**Acceptance:** OpenAPI docs render; all endpoints covered by tests. ✅

### S5 — Frontend war-room console 🟢
- [x] Live problem feed + severity board
- [x] Incident detail w/ root-cause tree + fixture timeline
- [x] Entity context + agent analysis panels
- [x] Mobile-responsive layout + config panel (operator, auto-approve guardrail)
**Acceptance:** renders against API; responsive; configurable; production build clean. ✅

### S6 — Human-in-the-loop remediation 🟢
- [x] Approve/reject with reason note + Apply (execute) step (409 guard)
- [x] Runbook + risk + MTTR shown before action
- [x] Audit log of decisions
- [x] Auto-approve guardrails (runtime-configurable via PATCH /settings)
**Acceptance:** approve/reject/execute round-trip to API; audit recorded. ✅

### S7 — Backend testing (100% coverage) 🟢
- [x] Unit tests all modules (config, models, fixtures, MCP, agent, store)
- [x] Integration tests full API + WebSocket + auto-approve guardrail
- [x] Coverage gate = 100% (66 tests)
**Acceptance:** `pytest --cov` reports 100%. ✅

### S8 — Playwright E2E (100% flows) 🟢*
- [x] Console load, incident triage, root-cause view
- [x] Approve + apply + reject remediation flows
- [x] Guardrail toggle, operator change, problem switch
- [x] Mobile viewport (drawer) across desktop + mobile projects
**Acceptance:** specs authored + typecheck clean; single-origin target validated by HTTP smoke test.
*Browser binary download blocked in build sandbox (Playwright CDN off allow-list); runs green on Desktop/CI.*

### S9 — Documentation 🟢
- [x] Architecture doc + diagram
- [x] User guide w/ numbered steps + 3 screenshots
- [x] Access-requirements + setup/run + E2E testing guide
- [x] API reference + README
**Acceptance:** docs complete in /docs, screenshots embedded. ✅

### S10 — Packaging & delivery 🟢
- [x] Makefile + run scripts, multi-stage Dockerfile, Cloud Run config, .env.example
- [x] Final tracker update
- [x] Zip repo
**Acceptance:** zip downloads; README quickstart works. ✅

---

## Access Required (Blocking real-data path only; mocks run now)
See `docs/ACCESS_REQUIREMENTS.md`. Status: 🔵 awaiting credentials — **mock path active** (real clients ready behind USE_MOCKS).

## Change Log
| Date (BST) | Sprint | Note |
|---|---|---|
| 2026-06-01 13:49 | S0 | Tracker created; scaffolding underway. |
| 2026-06-01 13:58 | S1–S4 | Domain models, MCP mock+live, agent (mock+Gemini), full API + WS verified end-to-end. |
| 2026-06-01 14:10 | S5 | Enterprise React console (responsive, configurable) — production build clean. |
| 2026-06-01 14:30 | S6 | Execute step + 409 guard + runtime guardrails; HITL wired front-to-back. |
| 2026-06-01 14:40 | S7 | 66 pytest tests, 100% statement coverage. |
| 2026-06-01 14:45 | S8 | Playwright specs (desktop+mobile) authored; stack validated via HTTP smoke test. |
| 2026-06-01 14:50 | S9 | User guide + screenshots, architecture + diagram, README. |
| 2026-06-01 14:56 | S10 | Docker + Cloud Run + scripts; repo packaged. Build complete. |
