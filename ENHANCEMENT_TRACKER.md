# StadiumPulse Marshal — "SpoofVane-parity" Enhancement Tracker

**Goal:** Apply the four enhancements built for the SpoofVane console onto the
StadiumPulse Marshal frontend, adapted to *this* app's domain (AIOps matchday
operations) and its **existing** backend RBAC model — do not invent a parallel
one.

## Baseline (audit)
- Frontend already boots (Vite + React, has index.html, dist). Flat **top-tab**
  nav (Triage/Incidents/Reliability/Scenarios/Webhooks/Audit). No login, no
  role/tenant context. An `operator` *name* string exists but no auth.
- Backend ALREADY has RBAC: `app/rbac/policy.py` roles `viewer/operator/
  responder/admin` + fine-grained permissions; `app/api/auth.py` resolves a
  JWT/API-key Principal; `auth_enabled` defaults false → anonymous admin.
  Health endpoints exist: `/api/v1/health`, `/api/v1/config`, `/api/v1/ready`.
- So the four SpoofVane enhancements map as:
  - **Demo-seed login** → sign-in using the backend's 4 roles; offline seed
    auth + optional live JWT. (Backend may need a tiny `/auth/login` to mint a
    demo JWT — add only if cheap; otherwise client-side seed principals.)
  - **Multi-tenant** → **multi-venue** (matchday domain): two demo venues, a
    venue switcher. (Backend has a `venue` model.)
  - **Grouped collapsible sidebar** → convert top tabs into a left rail with
    groups: Operations / Reliability / Governance / Administration; collapsible.
  - **Health surface** → a Health page wired to `/health` + `/ready` + `/config`.

## Sprints
| # | Sprint | Status |
|---|--------|--------|
|M1| Frontend RBAC mirror of app/rbac/policy.py (roles, perms, ranks) | 🟢 |
|M2| Demo accounts (role × 2 venues) + auth/session/venue/role context | 🟢 |
|M3| Demo-seed Login page (quick-fill, offline seed + live JWT, logout) | 🟢 |
|M4| Grouped collapsible role-gated sidebar (replaces flat tabs) | 🟢 |
|M5| AppShell chrome: venue switcher, role badge, user menu, health pill | 🟢 |
|M6| RBAC gating of nav + actions (approve/execute/scenario/webhook/settings) | 🟢 |
|M7| Health page wired to /health + /ready + /config + nav-page coverage | 🟢 |
|M8| API client: send bearer token; auth-aware; keep existing endpoints | 🟢 |
|M9| Backend: optional /auth/login (mint demo JWT) + venue list; confirm health | 🟢 |
|M10| Tests (unit: rbac/seed; e2e: login/rbac/sidebar) + tsc/build green | 🟢 |
|M11| Docs + package | 🟢 |

## Changelog

## Changelog
- **M1–M11 complete.** Applied the four SpoofVane console enhancements to
  StadiumPulse Marshal, adapted to its domain and **existing** backend RBAC:
  - Demo-seed **login** (LoginPage + auth context): live JWT via new
    `/api/v1/auth/login`, offline seed fallback, quick-fill chips, logout.
  - **Multi-venue** (the matchday analogue of multi-tenant): venue switcher,
    two demo venues, role × venue matrix on front and back ends.
  - **Grouped collapsible role-gated sidebar** replacing the flat tabs
    (Operations / Reliability / Governance / Administration); `[`-key + button
    collapse.
  - **Health page** wired to `/health` + `/ready` + `/config` + page coverage.
  - Backend: added `/api/v1/auth/login` + `/auth/demo-users` (mint demo JWT);
    made `get_principal` honor a presented bearer token even when auth is
    globally disabled, so role gating is demonstrable without a flag flip.
  - **Fixed a real authorization gap**: `approve`/`reject`/`execute`/`settings`
    routes had NO permission guard — any caller could approve a remediation.
    Added `require_permission` guards; proved viewer→403, responder→200.
  - Fixed a pre-existing FastAPI-compat crash (204 route with a body model)
    that stopped the app starting under the installed FastAPI.
  - Tests: backend **225 pass** (incl. 6 new auth/RBAC tests); frontend **7**
    runnable RBAC unit tests; Playwright specs updated for the login gate +
    new nav, plus a new `auth-rbac.spec.ts` (browsers BLOCKED-ENV in sandbox →
    run in CI). Frontend `tsc -b` + `vite build` green (60 modules). Live stack
    verified: SPA served, login works, viewer 403 on settings.
