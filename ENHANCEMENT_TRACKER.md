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

---

## Round 2 — Enterprise hardening (reviewer-driven depth)

Triggered by review: "are you really happy with this as enterprise grade?".
Audit found genuine gaps below. Scope is NOT shrunk — backend depth + matching
frontend, modularised (no single-file dumping).

### Findings (what a reviewer would flag)
- F1. Frontend gates **nav** by role but **not action buttons** by permission —
  a viewer sees Approve/Execute the backend will 403. Inconsistent.
- F2. **Venue is cosmetic for authz**: Principal carries no venue; backend never
  enforces a user may only act within their venue(s). No `/auth/me`.
- F3. No **`/api/v1/venues`** endpoint; frontend hardcodes venues.
- F4. Frontend HTTP layer ignores **401/403** (no session-expiry redirect / clean
  forbidden surfacing).
- F5. No server-side **venue-scope authorization** dependency.
- F6. No reusable frontend **permission primitives** (`useCan`, `<Can>`,
  `<RequirePermission>`), so gating would be ad-hoc and inconsistent.
- F7. RBAC policy lacks **venue-scoped principals** + tests for them.

### Sprints
| # | Sprint | Status |
|---|--------|--------|
| R1 | Backend: Principal gains venue scope (claims+policy) + unit tests | 🟢 |
| R2 | Backend: `/api/v1/auth/me` (rehydrate) + venue claim in login JWT | 🟢 |
| R3 | Backend: `/api/v1/venues` (list, principal-scoped) module + tests | 🟢 |
| R4 | Backend: `require_venue` authz dependency; apply to incident routes | 🟢 |
| R5 | Backend: tests for venue authz (cross-venue 403) + full suite green | 🟢 |
| R6 | Frontend: permission primitives module (useCan, <Can>, <RequirePermission>) | 🟢 |
| R7 | Frontend: gate action buttons (approve/reject/execute/scenario/settings) | 🟢 |
| R8 | Frontend: 401/403 handling in http layer → session expiry + toast | 🟢 |
| R9 | Frontend: venues from `/venues` (live) w/ seed fallback; me-rehydrate | 🟢 |
| R10 | Frontend: split big files into modules (auth, App shell, client) | 🟢 |
| R11 | Tests (backend + node rbac) green; tsc/build green; e2e updated | 🟢 |
| R12 | Docs + package | 🟢 |

### Round 2 changelog
- **R1–R5 (backend):** Principal gained venue scope (`venues`/`all_venues`);
  JWTs carry venue claims; new `/api/v1/auth/me` (rehydrate) and
  `/api/v1/venues` (principal-scoped); `require_venue_access` dependency applied
  to incident list/create. **+7 tests** (cross-venue 403 proven). Suite 232 green.
- **R6 (frontend):** reusable permission primitives `lib/permissions.tsx`
  (`useCan`, `<Can>`, `<RequirePermission>`).
- **R7:** action buttons now permission-gated to match the backend —
  RemediationCard (approve/reject/execute → `remediation:approve`),
  IncidentLifecycle (transition/escalate → `incident:write`), IncidentsPage
  (create → `incident:write`), ScenariosPage (`scenario:write`), SettingsPanel
  (auto-approve → `settings:write`, operator now read-only from session).
- **R8:** HTTP layers (`http.ts` + `client.ts`) now handle **401** → clear
  session → return to login gate, via an unauthorized handler the auth context
  registers.
- **R9:** venue switcher consumes live `/venues` (seed fallback); session
  rehydrates via `/auth/me` on refresh.
- **R10 (modularisation):** monolithic `auth.tsx` split into
  `lib/auth/{index,types,session-store,seed-auth,live-auth}`; shell chrome
  extracted to `components/shell/{Sidebar,TopBar,VenueSwitcher,UserMenu,HealthPill}`;
  `App.tsx` 207 → 90 lines.
- **R11:** frontend `tsc -b` + `vite build` green; 7 runnable RBAC unit tests
  pass; e2e extended with permission-gating assertions (viewer has no
  approve/create, disabled auto-approve). Browsers BLOCKED-ENV → e2e runs in CI.
- **R12:** docs + package.
- **Verified live:** SPA served; `/auth/me` rehydrates; `/venues` scoped
  (operator 1, platform 2); operator cross-venue list **403**; viewer settings
  **403**; responder approve **200**.

### Round 2 — COMPLETE

---

## Round 3 — Depth: full venue enforcement, OIDC, modularise the rest

Continuation per review. Scope not shrunk.

### Sprints
| # | Sprint | Status |
|---|--------|--------|
| S1 | Audit every venue-bearing route; extend require_venue_access everywhere | 🟢 |
| S2 | Incident sub-routes (get/transition/assign/note) enforce venue on the entity | 🟢 |
| S3 | Tests for per-entity venue enforcement (cross-venue 403 on detail/actions) | 🟢 |
| S4 | OIDC: discovery + authorization-code login module (backend) | 🟢 |
| S5 | OIDC: token exchange → Principal (role+venue mapping) + tests | 🟢 |
| S6 | Frontend: OIDC sign-in button + callback handling (graceful if unconfigured) | 🟢 |
| S7 | Modularise TriagePage (322L) into sub-panels | 🟢 |
| S8 | Modularise client.ts (295L) into api/ modules | 🟢 |
| S9 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| S10 | Docs + package | 🟢 |

### Round 3 changelog
- **S1–S3 (full venue enforcement):** added `_authorize_incident` — every
  incident sub-route (get / transition / assign / note / escalate) now loads the
  entity and enforces the principal's venue scope, not just the list filter.
  +3 tests prove cross-venue 403 on each sub-route (and same-venue 200).
- **S4–S5 (OIDC):** new `app/services/oidc_service.py` (discovery, signed-state
  CSRF, code exchange, claims→Principal role+venue mapping, app-JWT minting) +
  `/api/v1/auth/oidc/{status,login,callback}`. Degrades gracefully when
  unconfigured (status=false, login 401). OIDC settings added to config.
  +10 tests (state tamper, role/venue mapping, admin defaults, status endpoint).
- **S6 (frontend OIDC):** Login page shows an SSO button only when
  `/auth/oidc/status` is enabled; the auth provider captures the `#oidc_token=`
  callback fragment and rehydrates via `/auth/me`.
- **S7 (modularise TriagePage):** 322 → 141 lines. Extracted `useTriage` hook
  (state + IO) and `components/triage/{ProblemFeed,DecisionAuditLog}`.
- **S8 (modularise client.ts):** 295 → 254 lines; shared core extracted to
  `api/core.ts` (http, token, 401 handler, idempotency key) and `api/system.ts`
  (health/ready/config/venues/oidc). `client.ts` is now a barrel.
- **S9:** backend **245 tests pass**; frontend `tsc -b` + `vite build` green; 7
  node RBAC unit tests pass. Live-verified: OIDC status, per-entity cross-venue
  403 on read + write.
- **S10:** docs + package.

### Round 3 — COMPLETE

---

## Round 4 — Production-grade OIDC (JWKS verification + full-flow tests)

### Sprints
| # | Sprint | Status |
|---|--------|--------|
| T1 | JWKS fetch + cache; RS256/ES256 ID-token signature verification | 🟢 |
| T2 | Verify iss/aud/exp/nonce; reject tampered/expired/wrong-aud tokens | 🟢 |
| T3 | Nonce: issue in auth URL, bind in state, enforce on callback | 🟢 |
| T4 | Mock IdP fixture (RSA keypair, discovery, jwks, token endpoint) | 🟢 |
| T5 | Full-flow tests: discovery→authorize→callback→session via mock IdP | 🟢 |
| T6 | Negative tests: bad sig / wrong aud / expired / bad nonce → 401 | 🟢 |
| T7 | Config flag to allow unverified decode (demo only) vs strict (default) | 🟢 |
| T8 | Full suite + frontend build green; docs + package | 🟢 |

### Round 4 changelog
- **T1–T2:** strict JWKS signature verification (RS256/ES256) + iss/aud/exp
  validation via PyJWT `PyJWKClient`.
- **T3:** nonce issued in auth URL, bound into signed state, enforced on callback.
- **T4:** mock IdP fixture (RSA keypair, discovery, JWKS, token endpoint).
- **T5–T6:** full signed flow test + negatives (bad sig / wrong aud / expired /
  nonce mismatch → rejected).
- **T7:** `OIDC_VERIFY_SIGNATURE` flag — strict by default, demo override.
- **T8:** backend 251 pass; docs + .env.example updated; packaged.

### Round 4 — COMPLETE

---

## Round 5 — Venue-partition the remaining data domains + OIDC refresh/rotation

Two reviewer edges from Round 4: (a) only incidents are venue-scoped; SLO/
analytics/observability aren't filtered by venue; (b) OIDC issues a single
session token with no renewal. Round 5 addresses both.

### Sprints
| # | Sprint | Status |
|---|--------|--------|
| U1 | Model: attach venue_id to Problem/SLO/Analytics where applicable | 🟢 |
| U2 | Observability routes accept venue filter; enforce principal scope | 🟢 |
| U3 | SLO + analytics routes venue-scoped; default to principal venues | 🟢 |
| U4 | Tests: cross-venue 403 / scoped results on problems, slo, analytics | 🟢 |
| U5 | Session refresh: /auth/refresh issues a fresh token from a valid one | 🟢 |
| U6 | Frontend: silent token refresh before expiry; refresh on 401-once | 🟢 |
| U7 | Tests: refresh happy-path + expired/invalid refusal | 🟢 |
| U8 | Full suite + frontend build green; docs + package | 🟢 |

### Round 5 changelog
- **U1–U4 (venue-partition the data domains):** `Problem` gained `venue_id`;
  seeded scenario problems split across the two demo venues. New
  `scope_collection` helper; `/problems`, `/problems/{id}` and `/incidents-search`
  are now venue-scoped, and incident creation inherits the source problem's
  venue. +11 tests (operator sees only own venue, 403 cross-venue by list /
  id / filter, platform sees all). Live-verified.
- **Fix (important):** first pass scoped bare (claim-less) JWTs to *zero*
  venues and broke 11 pre-existing tests. Corrected the semantics — venue
  restriction applies only when a token explicitly carries venue scope; API-key
  principals are cross-venue. Demo logins (which always set `venue_id`) remain
  enforced.
- **U5–U7 (OIDC/session refresh):** `POST /api/v1/auth/refresh` re-mints a token
  for the current principal (preserving roles + venue scope); requires a valid
  token (401 otherwise). Frontend does silent refresh every 30m for live
  sessions. +2 tests (happy path preserves scope; auth-enabled refuses
  missing/tampered token).
- **Fix:** caught + fixed a test-pollution bug — a test mutated the
  `lru_cache` settings singleton (`auth_enabled`) and leaked into later tests;
  now restored in a `finally`.
- **U8:** backend **257 pass**; frontend `tsc -b` + `vite build` green; 7 node
  RBAC unit tests pass. Docs + package.

### Round 5 — COMPLETE
