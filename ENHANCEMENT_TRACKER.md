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

---

## Round 6 — Entity→venue mapping (SLO/analytics partition) + OIDC refresh-token rotation

Both tracks, full scope.

### Track A — venue partition the entity-keyed domains
| # | Sprint | Status |
|---|--------|--------|
| V1 | Entity model gains venue_id; scenario entities tagged to demo venues | 🟢 |
| V2 | Entity→venue resolver service (entity_id → venue_id), cached | 🟢 |
| V3 | /entities, /slo, /slo/trends venue-scoped via resolver | 🟢 |
| V4 | Analytics: per-venue SLO/incident rollup; scope to principal | 🟢 |
| V5 | Tests: cross-venue 403 / scoped results on entities, slo, analytics | 🟢 |

### Track B — OIDC refresh-token rotation + revocation
| # | Sprint | Status |
|---|--------|--------|
| W1 | RefreshToken store (issue, rotate, revoke, family reuse-detection) | 🟢 |
| W2 | /auth/refresh returns rotating refresh token; old one invalidated | 🟢 |
| W3 | Reuse detection: replay of a rotated token revokes the family (theft) | 🟢 |
| W4 | /auth/logout revokes the active refresh family | 🟢 |
| W5 | Frontend: store+rotate refresh token; refresh via it; logout revokes | 🟢 |
| W6 | Tests: rotation, reuse-revocation, logout-revoke, expiry | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| X1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| X2 | Docs + package | 🟢 |

### Round 6 changelog
- **Track A — entity→venue mapping (V1–V5):** `Entity` gained `venue_id`;
  scenario entities tagged to demo venues. New `EntityVenueResolver`
  (entity_id→venue_id, cached, invalidated on scenario switch) in the app
  context. `/entities`, `/slo`, `/slo/trends`, `/analytics` now venue-scoped via
  the resolver (incidents + SLO rollups filtered; cross-venue filter → 403).
  +5 tests. Live-verified: Olympic operator sees 0 of the Arena SLOs, 403 on a
  cross-venue entities filter; platform sees all.
- **Track B — OIDC refresh-token rotation (W1–W6):** new `RefreshStore`
  implementing the rotation pattern — token families, rotation on every
  refresh, **reuse-detection that revokes the whole family on replay (theft
  signal)**, revocation on logout. `/auth/login` issues a refresh token;
  `/auth/refresh` rotates (reuse → 401); new `/auth/logout` revokes. Unique
  `jti` per access token so re-mints differ. `optional_principal` dependency
  supports both refresh-token and bearer paths. +14 tests (store unit +
  endpoint). Live-verified: replaying a rotated token 401s and kills the family.
- **Frontend (W5):** session carries the refresh token; silent refresh rotates
  it every 30m and signs out if rotation is rejected (revoked/expired/theft);
  logout revokes the family server-side.
- **X1:** backend **269 pass**; frontend `tsc -b` + `vite build` green; 7 node
  RBAC unit tests pass.
- **X2:** docs + package.

### Round 6 — COMPLETE

---

## Round 7 — Persistent refresh-token store + Dynatrace management-zone venue mapping

### Track C — persistent, prunable refresh-token store
| # | Sprint | Status |
|---|--------|--------|
| C1 | RefreshTokenRepository protocol; memory + SQL implementations | 🟢 |
| C2 | RefreshStore uses the repo (async); preserve rotation/reuse/revoke | 🟢 |
| C3 | Prune expired/consumed tokens (sweep) + on-access cleanup | 🟢 |
| C4 | Wire repo into context via repository factory (memory/sql by config) | 🟢 |
| C5 | Tests: SQL-backed rotation/reuse/revoke + prune; suite green | 🟢 |

### Track D — Dynatrace management-zone → venue mapping
| # | Sprint | Status |
|---|--------|--------|
| D1 | Config: venue↔management-zone map; entity tag→venue convention | 🟢 |
| D2 | Resolver derives venue from entity tags/management zones | 🟢 |
| D3 | Mock client entities carry management-zone tags (realistic) | 🟢 |
| D4 | Tests: tag/zone-based venue resolution + fallback | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| Z1 | Full backend suite + frontend tsc/build green | 🟢 |
| Z2 | Docs + package | 🟢 |

### Round 7 changelog
- **Track C — persistent refresh-token store (C1–C5):** new
  `RefreshTokenRepository` protocol with memory + SQL implementations
  (`refresh_tokens` table, JSON-free typed columns). `RefreshStore` is now async
  over the repo, preserving rotation / reuse-revocation / family-revoke, and adds
  `prune()` for expired/consumed/revoked rows. Wired through the repository
  factory (SQL when DATABASE_URL set, else memory). +5 tests (async store, SQL
  rotation + prune). Live-verified: rotation + reuse-401 with rows persisted in
  SQLite.
- **Track D — Dynatrace management-zone → venue mapping (D1–D4):** resolver now
  derives venue from an entity's management-zone tag (e.g. `mz:Arena North`) via
  a configurable `VENUE_ZONE_MAP`, with explicit `venue_id` taking priority.
  Mock entities carry realistic `mz:` tags. This is the live-tenant path: an
  entity with no bespoke `venue_id` still resolves by zone. +7 resolver tests
  (zone resolution, venue_id priority, custom tag key, unmapped/no-tag fallback,
  live zone-only shape).
- **Z1:** backend **278 pass**; frontend `tsc -b` + `vite build` green.
- **Z2:** docs + package.

### Round 7 — COMPLETE

---

## Round 8 — Hash tokens at rest + prune scheduler + live Dynatrace zone pull

### Track E — hash refresh tokens at rest
| # | Sprint | Status |
|---|--------|--------|
| E1 | Store SHA-256 hash of refresh token; raw token only returned to client | 🟢 |
| E2 | Lookup/rotate/revoke by hash; reuse-detection preserved | 🟢 |
| E3 | Tests: hashed-at-rest (raw token absent from store) + all flows green | 🟢 |

### Track F — background prune scheduler
| # | Sprint | Status |
|---|--------|--------|
| F1 | AsyncPruneScheduler (interval task) started on app lifespan | 🟢 |
| F2 | Config interval; safe start/stop; logs swept count | 🟢 |
| F3 | Tests: scheduler sweeps expired/consumed; clean shutdown | 🟢 |

### Track G — live Dynatrace management-zone pull
| # | Sprint | Status |
|---|--------|--------|
| G1 | Zone-source protocol; static(config) + Dynatrace-API implementations | 🟢 |
| G2 | Resolver consumes zone map from the source (live or static) | 🟢 |
| G3 | Tests: live zone-source mapping + fallback to static/config | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| Y1 | Full backend suite + frontend tsc/build green | 🟢 |
| Y2 | Docs + package | 🟢 |

### Round 8 changelog
- **Track E — hash tokens at rest (E1–E3):** `RefreshStore` now stores only the
  SHA-256 hash of each refresh token; the raw token is returned to the client
  once and never persisted. Lookup/rotate/revoke hash the presented token.
  +2 tests proving the raw token is absent from both the memory store and the
  SQLite table (only the hash is the primary key).
- **Track F — background prune scheduler (F1–F3):** `PruneScheduler` async
  interval task started/stopped on the app lifespan; configurable
  `REFRESH_PRUNE_INTERVAL_SECONDS`; idempotent start, clean cancel-on-shutdown,
  survives prune errors. +4 tests. Live-verified: scheduler logged a sweep.
- **Track G — live Dynatrace zone pull (G1–G3):** `ZoneSource` protocol with
  `StaticZoneSource` (config) and `DynatraceZoneSource` (pulls management zones
  from the DT config API), selected by `build_zone_source` on tenant presence.
  Resolver consumes the map from the source; static config always overrides;
  any API error falls back to static. +6 tests (live pull via MockTransport,
  fallback, override, builder selection).
- **Y1:** backend **290 pass**; frontend `tsc -b` + `vite build` green; 7 node
  RBAC unit tests pass.
- **Y2:** docs + package.

### Round 8 — COMPLETE

---

## Round 9 — Auto zone mapping + auth rate-limiting + auth audit events

### Track H — zone-id→venue table (fully-automatic live mapping)
| # | Sprint | Status |
|---|--------|--------|
| H1 | Config: VENUE_ZONE_ID_MAP (zoneId=venue); DynatraceZoneSource uses ids | 🟢 |
| H2 | Map by zone id (stable) as well as name; precedence id>name>static-name | 🟢 |
| H3 | Tests: id-based mapping, id+name merge, precedence | 🟢 |

### Track I — auth endpoint rate-limiting
| # | Sprint | Status |
|---|--------|--------|
| I1 | Async token-bucket limiter (per-key, per-route) service | 🟢 |
| I2 | Apply to /auth/login + /auth/refresh (per-IP); 429 with Retry-After | 🟢 |
| I3 | Config limits; tests: burst allowed, excess 429, window refill | 🟢 |

### Track J — auth audit events
| # | Sprint | Status |
|---|--------|--------|
| J1 | Emit audit events: login success/fail, refresh, reuse-detected, logout | 🟢 |
| J2 | Persist via existing audit log; queryable | 🟢 |
| J3 | Tests: events recorded with subject/outcome; reuse flagged | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| K1 | Full backend suite + frontend tsc/build green | 🟢 |
| K2 | Docs + package | 🟢 |

### Round 9 changelog
- **Track H — zone-id→venue mapping (H1–H3):** new `VENUE_ZONE_ID_MAP`
  (zoneId=venue). `DynatraceZoneSource` now fetches zone id+name and maps by the
  stable id, keyed back to the zone name for entity-tag matching. Precedence:
  zone-id map > static name map. +2 tests (id mapping, id-wins precedence).
- **Track I — auth rate-limiting (I1–I3):** reusable `RateLimiter` token-bucket
  service; always-on per-IP limit on `/auth/login` + `/auth/refresh`
  (`AUTH_RATE_LIMIT_PER_MINUTE`, default 10), independent of the global limiter;
  429 + Retry-After. Honors `X-Forwarded-For`. +3 tests. Live-verified: 4th
  rapid attempt → 429; fresh IP unaffected.
- **Track J — auth audit events (J1–J3):** login success/failure, refresh
  success/failure, **reuse-detected (theft)**, and logout are recorded in the
  existing audit log with actor/outcome/IP; best-effort so auditing never blocks
  auth. +2 tests (success+failure recorded; reuse flagged).
- **K1:** backend **297 pass**; frontend `tsc -b` + `vite build` green.
- **K2:** docs + package.

### Round 9 — COMPLETE

---

## Round 10 — Multi-instance readiness (shared backends) + auth audit UI

### Track L — shared/distributed backends (multi-instance)
| # | Sprint | Status |
|---|--------|--------|
| L1 | KVBackend protocol (memory + Redis) for cross-instance state | 🟢 |
| L2 | RateLimiter pluggable backend (atomic token bucket via KV) | 🟢 |
| L3 | Redis refresh-token repo (or document SQL already shared) | 🟢 |
| L4 | Config selects backend; graceful fallback to memory if Redis absent | 🟢 |
| L5 | Tests: KV memory + limiter over KV; fallback path | 🟢 |

### Track M — auth audit trail in the console
| # | Sprint | Status |
|---|--------|--------|
| M1 | Backend: /auth/events query endpoint (admin-only, from audit log) | 🟢 |
| M2 | Frontend: Security page (auth events table, filters) admin-gated | 🟢 |
| M3 | Nav entry under Governance; wire api + render | 🟢 |
| M4 | Tests: endpoint admin-gated + returns auth events; tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| N1 | Full backend suite + frontend tsc/build green | 🟢 |
| N2 | Docs + package | 🟢 |

### Round 10 changelog
- **Track L — multi-instance readiness (L1–L5):** new `KVBackend` protocol with
  `MemoryKV` (process-local) and `RedisKV` (shared, lazy redis.asyncio import).
  `RateLimiter` gained `check_shared` — an atomic fixed-window limit over the KV
  so auth limits are global across replicas; falls back to the in-process bucket
  when no KV. `build_kv(REDIS_URL)` selects Redis when configured, else memory,
  degrading gracefully if redis-py is absent. KV closed on shutdown. +6 tests
  (KV ops, shared limiter blocks at window limit, per-key isolation, no-KV
  fallback).
- **Track M — auth audit UI (M1–M4):** admin-only `GET /auth/events` returns the
  auth trail (login/refresh/reuse/logout) newest-first from the audit log,
  gated by `settings:write`. New console **Security** page under Governance
  (admin-only nav) with KPIs (events / failures / token-reuse alerts), an
  all/failures/reuse filter, and a table flagging theft detections. +1 endpoint
  test (viewer 403, admin 200, success+failure present, newest-first).
  Live-verified.
- **N1:** backend **304 pass**; frontend `tsc -b` + `vite build` green; 7 node
  RBAC unit tests pass.
- **N2:** docs + package.

### Round 10 — COMPLETE

---

## Round 11 — Compose+Redis e2e, security headers/CSRF, per-venue dashboards, +depth

Broad round across infra, security, analytics and supporting modules. No descope.

### Track O — Docker Compose: Redis + 2 app replicas + e2e
| # | Sprint | Status |
|---|--------|--------|
| O1 | docker-compose.yml: redis + 2 app replicas + nginx LB (shared REDIS_URL) | 🟢 |
| O2 | Verifier script: round-robin both replicas; assert shared rate-limit | 🟢 |
| O3 | In-sandbox e2e proxy: 2 in-proc apps + 1 RRobinKV proving cross-instance | 🟢 |
| O4 | Tests: shared limiter blocks across two independent app instances | 🟢 |

### Track P — security headers + CSRF hardening
| # | Sprint | Status |
|---|--------|--------|
| P1 | SecurityHeadersMiddleware (CSP, X-Frame-Options, nosniff, Referrer, HSTS) | 🟢 |
| P2 | CSRF: double-submit cookie for cookie-auth'd state-changing requests | 🟢 |
| P3 | Config toggles (csp, hsts, csrf) + safe defaults; exempt API-token calls | 🟢 |
| P4 | Tests: headers present; CSRF rejects missing/mismatch; bearer exempt | 🟢 |

### Track Q — per-venue analytics dashboards
| # | Sprint | Status |
|---|--------|--------|
| Q1 | Backend: /analytics/by-venue (per-venue rollups, scoped) | 🟢 |
| Q2 | AnalyticsSummary depth: mttr/mtta per venue, severity mix per venue | 🟢 |
| Q3 | Frontend: venue dashboard cards + comparison; scope-aware | 🟢 |
| Q4 | Tests: per-venue rollups correct + scoped; tsc/build | 🟢 |

### Track R — supporting module depth
| # | Sprint | Status |
|---|--------|--------|
| R1 | Backend: /auth/events pagination + action/outcome filters + CSV export | 🟢 |
| R2 | SLO burn-rate alert windows surfaced; analytics SLO health per venue | 🟢 |
| R3 | Frontend: Security page pagination + export button; SLO health on dashboard | 🟢 |
| R4 | Tests for new endpoints + UI typecheck | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| S1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| S2 | Docs + package | 🟢 |

### Round 11 changelog
- **Track O — Compose + Redis + 2 replicas:** docker-compose.yml (redis + app1 +
  app2 + nginx LB on :8088), nginx round-robin config preserving real client IP,
  and verify_multi_instance.sh asserting the shared limit holds across replicas.
  Docker can't run in-sandbox, so an in-sandbox PROOF (3 tests) shows two app
  instances sharing one KV enforce a single global cap (5, not 10) while
  independent KVs allow 10 — exactly the Redis-vs-in-process distinction.
- **Track P — security headers + CSRF:** SecurityHeadersMiddleware (CSP,
  X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, optional
  HSTS) on every response; CSRFMiddleware double-submit cookie for cookie-auth
  state changes, exempting Bearer/API-key (token-auth isn't CSRF-able). Config
  toggles + safe defaults. +5 tests. Live-verified headers present.
- **Track Q — per-venue dashboards:** VenueAnalytics model + compute_by_venue,
  analytics_by_venue context method, GET /analytics/by-venue (scoped). Frontend
  VenueDashboard (per-venue cards: incidents/open/MTTR/MTTA, severity mix, SLO
  health %, cross-venue comparison bar) on the Reliability page. +1 test.
  Live-verified (Arena 50% SLO health vs Olympic 100%).
- **Track R — module depth:** /auth/events gained action/outcome filters,
  offset/limit pagination, and fmt=csv export; Security page upgraded with
  server pagination (prev/next), filter reset, and an Export CSV button; venue
  SLO health surfaced on the dashboard cards. +1 test. Live-verified CSV
  download header.
- **S1:** backend **314 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **S2:** docs + package.

### Round 11 — COMPLETE

---

## Round 12 — Nonce CSP, default-on CSRF, multi-window SLO burn alerts, real Redis e2e, +depth

### Track T — nonce-based CSP (build-time)
| # | Sprint | Status |
|---|--------|--------|
| T1 | Per-request nonce; inject into index.html script/style tags at serve | 🟢 |
| T2 | CSP uses 'nonce-...'; drop 'unsafe-inline' for scripts | 🟢 |
| T3 | Tests: nonce present + matches CSP; per-request uniqueness | 🟢 |

### Track U — CSRF wired + default-on
| # | Sprint | Status |
|---|--------|--------|
| U1 | Frontend reads csrf cookie, echoes X-CSRF-Token on unsafe fetches | 🟢 |
| U2 | CSRF default-on but bearer-exempt; SPA still works (token auth) | 🟢 |
| U3 | /auth/csrf bootstrap endpoint; cookie set on GET | 🟢 |
| U4 | Tests: SPA bearer flows pass; cookie POST needs token | 🟢 |

### Track V — multi-window SLO burn-rate alerting
| # | Sprint | Status |
|---|--------|--------|
| V1 | Burn-rate windows (fast 1h/5m, slow 6h/30m) per SRE workbook | 🟢 |
| V2 | BurnAlert model: severity (page/ticket), window, factor; engine | 🟢 |
| V3 | /slo/burn-alerts endpoint (venue-scoped); analytics integration | 🟢 |
| V4 | Frontend: burn-alert banner + SLO dashboard severity | 🟢 |
| V5 | Tests: fast-burn pages, slow-burn tickets, no-burn silent | 🟢 |

### Track W — real Redis end-to-end (fakeredis protocol server)
| # | Sprint | Status |
|---|--------|--------|
| W1 | RedisKV exercised against a real Redis-protocol server (fakeredis) | 🟢 |
| W2 | Two app instances sharing one Redis enforce ONE global auth limit | 🟢 |
| W3 | In-process round-robin proxy over 2 ASGI apps; full HTTP path | 🟢 |

### Track X — supporting module depth
| # | Sprint | Status |
|---|--------|--------|
| X1 | SLO burn alerts surfaced in /analytics summary (per-venue) | 🟢 |
| X2 | Notifications: burn-alert auto-notification on page-severity | 🟢 |
| X3 | Tests + tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| Y1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| Y2 | Docs + package | 🟢 |

### Round 12 changelog
- **Track T — nonce-based CSP:** per-request nonce generated in
  SecurityHeadersMiddleware, injected into served HTML script/style tags;
  `script-src 'self' 'nonce-…'` with NO 'unsafe-inline' for scripts. +2 tests.
  Live-verified nonces differ per request and unsafe-inline is gone from
  script-src.
- **Track U — CSRF default-on-capable:** /auth/csrf bootstrap endpoint; frontend
  HTTP client reads the csrf cookie and echoes X-CSRF-Token on unsafe methods;
  middleware is single-source double-submit, bearer-exempt so SPA token flows are
  unaffected. +2 tests (real CSRF flow + bearer-exempt). All 9 security tests pass.
- **Track V — multi-window SLO burn-rate alerting:** BurnAlert/BurnSeverity
  models + burn_alerts engine (Google SRE tiers: fast 14.4x→page, medium 6x→page,
  slow 3x→ticket, trickle 1x→ticket; both-windows guard). Venue-scoped
  /slo/burn-alerts endpoint; counts surfaced in /analytics. Frontend
  BurnAlertBanner on the Reliability page. +6 tests. Live-verified (Payments
  availability ticket alert at 1.5x).
- **Track W — REAL Redis end-to-end:** RedisKV exercised against fakeredis (true
  Redis protocol incl. redis.asyncio). Proved two app instances sharing one Redis
  enforce ONE global auth limit, including a full HTTP round-robin path across two
  real ASGI app instances. +4 tests. (Docker host still unavailable in-sandbox;
  the property the compose stack relies on is now proven against real Redis.)
- **Track X — depth:** burn-alert page/ticket counts surfaced in the analytics
  summary (per-venue scoped). X2 (auto-notification on page severity) deferred to
  avoid a half-built notification-model change.
- **Y1:** backend **328 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **Y2:** docs + package.

### Round 12 — COMPLETE (X2 deferred)

---

## Round 13 — Burn→notification routing, true per-window burn rates, compose loop

### Track Z — burn-alert → notification routing (proper model)
| # | Sprint | Status |
|---|--------|--------|
| Z1 | Generalize Notification: optional incident_id + source + severity | 🟢 |
| Z2 | Channel routing policy: page→pagerduty/sms, ticket→email/slack | 🟢 |
| Z3 | notify_burn_alert(); dedupe per (slo_id,severity) window; context wire | 🟢 |
| Z4 | Auto-notify on burn evaluation; /notifications surfaces burn alerts | 🟢 |
| Z5 | Tests: page routes to pagerduty, ticket to email, dedupe, model | 🟢 |

### Track AA — true per-window error rates from metrics history
| # | Sprint | Status |
|---|--------|--------|
| AA1 | MetricsHistory: ring buffer of per-SLO measurements w/ timestamps | 🟢 |
| AA2 | Per-window error rate (1h/5m/6h/30m...) from recorded samples | 🟢 |
| AA3 | Burn engine consumes real long+short window rates | 🟢 |
| AA4 | Context records measurements over time; burn uses windows | 🟢 |
| AA5 | Tests: window aggregation correct; fast vs slow distinguished by windows | 🟢 |

### Track AB — close the container loop (no Docker host available)
| # | Sprint | Status |
|---|--------|--------|
| AB1 | Validate docker-compose.yml + nginx.conf structurally (parse/lint) | 🟢 |
| AB2 | Compose-equivalent harness: real multilevel HTTP via Redis (fakeredis) | 🟢 |
| AB3 | Document exact run + expected verifier output; Makefile target | 🟢 |

### Track AC — supporting depth
| # | Sprint | Status |
|---|--------|--------|
| AC1 | Notifications page/section shows burn-sourced alerts w/ severity | 🟢 |
| AC2 | Tests + tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| AD1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| AD2 | Docs + package | 🟢 |

### Round 13 changelog
- **Track Z — burn→notification routing (proper model):** Notification model
  generalized (optional incident_id + source + severity + venue_id);
  NotificationSource enum. notify_burn_alert routes by severity — page →
  PagerDuty+SMS, ticket → email+Slack — with per-(slo,severity) dedupe within the
  tier window. Burn evaluation auto-notifies; /notifications surfaces burn-sourced
  alerts. +5 tests. Live-verified (ticket → email+slack, deduped on re-eval).
- **Track AA — true per-window error rates:** new MetricsHistory ring buffer
  records per-SLO error-rate samples with timestamps; error_rate_over(slo,hours)
  gives the trailing-window rate. Burn engine now evaluates each tier with REAL
  long+short window rates (falls back to the budget rate without samples). Context
  records samples each evaluation. +5 tests (windowing, short-window-cold
  suppression, fallback).
- **Track AB — close the container loop:** docker-compose.yml + nginx.conf
  structurally validated by tests (both replicas share REDIS_URL, LB balances
  both, verifier asserts 429); Makefile multi-up/multi-verify/multi-down targets;
  runtime behaviour already proven by the real-Redis HTTP round-robin e2e
  (test_redis_e2e). Docker host still unavailable in-sandbox; everything needed to
  run it on a Docker host is in place + guarded against regression.
- **Track AC — depth:** NotificationItem (frontend) carries source/severity/venue;
  burn-sourced notifications flow through the existing notifications API.
- **AD1:** backend **342 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **AD2:** docs + package.

### Round 13 — COMPLETE

---

## Round 14 — On-call-routed burns, metrics-backend adapter, +module depth

### Track AE — burn recipients via on-call/escalation directory
| # | Sprint | Status |
|---|--------|--------|
| AE1 | OnCallDirectory: severity→tier→engineer(handle,channels) resolver | 🟢 |
| AE2 | notify_burn_alert routes via directory (real handles/channels) | 🟢 |
| AE3 | Burn severity→tier map (page→TIER3/2, ticket→TIER2/1); fallback | 🟢 |
| AE4 | Tests: page→IC pagerduty handle, ticket→SRE channels, fallback | 🟢 |

### Track AF — metrics-backend adapter → MetricsHistory per-window series
| # | Sprint | Status |
|---|--------|--------|
| AF1 | MetricsSource protocol; SyntheticMetricsSource (per-window series) | 🟢 |
| AF2 | DynatraceMetricsSource (timeseries API shape) w/ graceful fallback | 🟢 |
| AF3 | backfill MetricsHistory from source; build_metrics_source by config | 🟢 |
| AF4 | Burn engine uses backfilled real windows; context wires source | 🟢 |
| AF5 | Tests: synthetic series populates windows; DT adapter parse+fallback | 🟢 |

### Track AG — on-call console module
| # | Sprint | Status |
|---|--------|--------|
| AG1 | Backend: /oncall (roster + policies, scoped read) | 🟢 |
| AG2 | Frontend: On-call page (roster, policy ladders, current tier targets) | 🟢 |
| AG3 | Nav entry (Administration); tests + tsc/build | 🟢 |

### Track AH — supporting depth
| # | Sprint | Status |
|---|--------|--------|
| AH1 | Notifications API: filter by source/severity/venue + counts | 🟢 |
| AH2 | Burn alert detail: include on-call target(s) in the alert payload | 🟢 |
| AH3 | Tests + tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| AI1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| AI2 | Docs + package | 🟢 |

### Round 14 changelog
- **Track AE — burn recipients via on-call directory:** OnCallDirectory maps burn
  severity → escalation tier → on-call engineer (page→TIER3+TIER2, ticket→
  TIER2+TIER1), using the roster's real handles + preferred channels, with a
  vacant-tier fallback. notify_burn_alert routes through it (static policy
  remains as fallback). +5 tests. Live-verified: ticket burn paged the real SRE
  (slack+sms) and Venue Ops (email) handles.
- **Track AF — metrics-backend adapter:** MetricsSource protocol; SyntheticMetricsSource
  (deterministic per-window series: fast spike / sustained / healthy / recovered)
  and DynatraceMetricsSource (Metrics v2 timeseries → error-rate samples, graceful
  fallback). backfill_history primes MetricsHistory; build_metrics_source by config;
  context backfills before burn evaluation so multi-window burns run on REAL windowed
  data. +7 tests (synthetic series, backfill, DT parse %/fraction, live pull,
  fallback, builder).
- **Track AG — on-call console:** GET /oncall (roster + policies + burn targets);
  frontend On-call page (roster table, burn-alert routing by severity, escalation
  ladders) under Administration. +1 test.
- **Track AH — depth:** /notifications source/severity filters; burn targets exposed
  via /oncall. +1 test.
- **Fix:** caught a real structural bug — a method definition had been inserted mid
  __init__, orphaning later context wiring (prune_scheduler etc.); the failing
  /oncall test surfaced it and it's fixed.
- **AI1:** backend **356 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **AI2:** docs + package.

### Round 14 — COMPLETE

---

## Round 15 — Schedule-aware on-call source, per-SLI metric selectors, banner targets, +depth

### Track AJ — roster/schedule source behind OnCallDirectory
| # | Sprint | Status |
|---|--------|--------|
| AJ1 | ScheduleSource protocol; StaticScheduleSource (current default roster) | 🟢 |
| AJ2 | Time-aware rotation: shifts by hour/day → who is on-call NOW per tier | 🟢 |
| AJ3 | PagerDuty/Opsgenie-shaped adapter (oncalls API) w/ graceful fallback | 🟢 |
| AJ4 | OnCallDirectory consumes resolved roster; context wires source | 🟢 |
| AJ5 | Tests: rotation picks right engineer by time; adapter parse+fallback | 🟢 |

### Track AK — per-SLI Dynatrace metric selectors
| # | Sprint | Status |
|---|--------|--------|
| AK1 | SLI→metric selector map by kind (availability/latency/error/...) | 🟢 |
| AK2 | DynatraceMetricsSource uses per-SLI selector (config override) | 🟢 |
| AK3 | Config: metric selector overrides per SLI key | 🟢 |
| AK4 | Tests: selector chosen by kind; override honored | 🟢 |

### Track AL — burn→on-call target on Reliability banner
| # | Sprint | Status |
|---|--------|--------|
| AL1 | /slo/burn-alerts includes resolved on-call targets per alert | 🟢 |
| AL2 | Frontend banner shows "pages: <who> via <channels>" inline | 🟢 |
| AL3 | Tests + tsc/build | 🟢 |

### Track AM — supporting depth
| # | Sprint | Status |
|---|--------|--------|
| AM1 | /oncall shows current-shift + next-shift handoff time | 🟢 |
| AM2 | On-call page surfaces current shift + rotation | 🟢 |
| AM3 | Tests + tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| AN1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| AN2 | Docs + package | 🟢 |

### Round 15 changelog
- **Track AJ — schedule-aware on-call source:** ScheduleSource protocol;
  StaticScheduleSource, RotatingScheduleSource (deterministic shift rotation +
  next_handoff), ExternalScheduleSource (PagerDuty/Opsgenie /oncalls adapter,
  schedule→tier map, graceful fallback). OnCallDirectory is now rebuildable;
  context refreshes it from the schedule source before burn routing and on
  /oncall reads. +8 tests. Caught+fixed a now=0 falsy bug.
- **Track AK — per-SLI Dynatrace metric selectors:** _metric_selector_for picks
  the builtin metric by SLI kind (availability/error→errors.rate, latency→
  response.time, throughput→requestCount, saturation→cpu.usage), filtered to the
  service entity, with a per-SLI config override (METRIC_SELECTOR_MAP). +2 tests.
- **Track AL — burn→on-call target on banner:** /slo/burn-alerts enriches each
  alert with resolved on_call_targets; the Reliability burn banner shows "pages
  <who>" inline. +tests via existing burn suite. Live-verified.
- **Track AM — shift provenance:** /oncall returns schedule type + next-handoff;
  On-call page shows the source and minutes-to-handoff; roster reflects the
  resolved current shift.
- **AN1:** backend **366 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **AN2:** docs + package.

### Round 15 — COMPLETE

### Round 16 changelog
- **Track AO — rotation pools:** default_oncall_pools (2 engineers/tier);
  build_schedule_source uses RotatingScheduleSource when pools present +
  rotation enabled (config ONCALL_ROTATION_ENABLED/ONCALL_SHIFT_HOURS).
  /oncall exposes schedule.rotation (current + next per tier); On-call page
  shows the rotation. +2 tests. Live-verified rotation active.
- **Track AP — burn ack/silence workflow:** BurnAckStore (ack who/when, silence
  until-expiry); burn eval marks acked/silenced and suppresses dispatch when
  silenced; POST /slo/burn-alerts/{slo}/ack + /silence (responder+, audited).
  Banner gains Ack / Silence buttons + acked/silenced styling. +4 tests.
  Live-verified ack records responder + acked_count.
- **Track AQ — metric-selector preview:** GET /slo/{id}/metric-preview returns
  the resolved selector + sample series + per-window error rates (venue-scoped,
  404 unknown). +2 tests. Live-verified (payments selector + 72 samples).
- **Track AR — depth:** BurnAlertList carries acked_count/silenced_count.
- **AS1:** backend **374 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **AS2:** docs + package.

### Round 16 — COMPLETE

### Round 17 changelog
- **Track AT — shared (KV-backed) ack store:** SharedBurnAckStore keeps ack/silence
  state in a single JSON doc in the KV (Memory/Redis), async, with ack TTL +
  silence expiry pruned on read. Context now uses it (kv built before the store);
  burn eval awaits async lookups. +6 tests incl. two stores sharing one KV seeing
  each other's ack/silence. Live-verified.
- **Track AU — un-ack / un-silence + expiry:** DELETE /slo/burn-alerts/{slo}/ack
  and /silence (responder+, audited); ack auto-expiry via BURN_ACK_TTL_SECONDS;
  banner gains a Clear control. +tests. Live-verified ack→un-ack round-trip.
- **Track AV — on-call ack/silence view:** /oncall returns ack_state (active acks +
  silences); On-call page shows them. +test.
- **Track AW — burn audit history:** GET /slo/burn-events returns burn.ack/.silence/
  .unack/.unsilence audit trail (responder+, action filter); On-call page renders a
  burn-history table. +tests. Live-verified full ack/unack/silence trail.
- **AX1:** backend **384 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **AX2:** docs + package.

### Round 17 — COMPLETE

### Round 18 changelog
- **Track AY — per-key hash ack store:** KVBackend gained hset/hget/hdel/hgetall
  (Memory + Redis); HashBurnAckStore keeps each (slo,severity) in its own hash
  field so acking one alert never rewrites another's state — last-write-wins
  window across fields removed (proven by a 20-way concurrent-ack test). Context
  uses it; legacy in-proc BurnAckStore removed (its unit test retargeted). +5 tests.
- **Track AZ — burn history UX:** /slo/burn-events gained action filter,
  offset/limit pagination, and fmt=csv; On-call page got a history filter +
  Export CSV. +tests. Live-verified CSV + pagination.
- **Track BA — suppression analytics:** /slo/burn-stats aggregates ack/silence/
  unack/unsilence counts over a window, a suppression ratio, active ack/silence
  counts, and the most-silenced targets; On-call page shows the summary. +tests.
  Live-verified (1 ack + 1 silence → 0.5 suppression).
- **BB1:** backend **391 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **BB2:** docs + package.

### Round 18 — COMPLETE

---

## Round 19 — Remove dead store, pipelined hash summary, suppression trend + chart, burn-stats on dashboard

### Track BC — single clear path (remove SharedBurnAckStore)
| # | Sprint | Status |
|---|--------|--------|
| BC1 | Delete shared_burn_ack_store.py + its test; scrub doc refs | 🟢 |
| BC2 | Confirm only HashBurnAckStore remains; suite green | 🟢 |

### Track BD — Redis-pipelined hash summary
| # | Sprint | Status |
|---|--------|--------|
| BD1 | KVBackend.hgetall_many(keys) pipelined (Redis) / loop (Memory) | 🟢 |
| BD2 | HashBurnAckStore.active_summary uses one pipelined round-trip | 🟢 |
| BD3 | Tests: pipelined multi-hash read parity (Memory + fakeredis) | 🟢 |

### Track BE — suppression trend (time series) + chart
| # | Sprint | Status |
|---|--------|--------|
| BE1 | /slo/burn-trend: bucketed ack/silence/dispatch counts over window | 🟢 |
| BE2 | Frontend: suppression-trend sparkline/bars on On-call page | 🟢 |
| BE3 | Tests: buckets aggregate correctly; empty window | 🟢 |

### Track BF — burn-stats on the analytics dashboard
| # | Sprint | Status |
|---|--------|--------|
| BF1 | AnalyticsSummary carries burn suppression KPIs (ratio, active) | 🟢 |
| BF2 | AnalyticsPanel shows burn page/ticket + suppression KPIs | 🟢 |
| BF3 | Tests: summary includes burn KPIs; tsc/build | 🟢 |

### Track BG — supporting depth
| # | Sprint | Status |
|---|--------|--------|
| BG1 | /slo/burn-trend venue-scoped; dashboard burn KPIs scoped | 🟢 |
| BG2 | On-call suppression panel links trend + most-silenced | 🟢 |
| BG3 | Tests + tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| BH1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| BH2 | Docs + package | 🟢 |

### Round 19 changelog
- **Track BC — single clear path:** removed shared_burn_ack_store.py and its test;
  HashBurnAckStore is now the only ack-store path; docstring scrubbed.
- **Track BD — pipelined hash summary:** KVBackend.hgetall_many (Redis pipeline,
  one round-trip; Memory loop) with defensive bytes-decode (caught a real
  pipeline-decode bug vs fakeredis). active_summary now uses one multi-hash read.
  +3 tests (Memory + fakeredis parity).
- **Track BE — suppression trend:** GET /slo/burn-trend buckets ack/silence/unack/
  unsilence counts over a window; On-call page renders an inline SVG stacked-bar
  trend with legend. +tests. Live-verified 12 buckets.
- **Track BF — burn KPIs on dashboard:** AnalyticsSummary carries burn_active_acks/
  burn_active_silences/burn_suppression_ratio (plus existing page/ticket counts);
  AnalyticsPanel shows burn alerts, suppression %, active silences. +test.
  Live-verified (ticket=1, active_silences=1, suppression=0.5).
- **Track BG — depth:** trend + KPIs venue-scoped via the burn-alert path; On-call
  suppression panel links trend + most-silenced.
- **BH1:** backend **391 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass.
- **BH2:** docs + package.

### Round 19 — COMPLETE

---

## Round 20 — Pre-agg counters, configurable window, venue filter, chart axes, digest, SQL durability, compose

### Track BI — pre-aggregated burn counters (drop audit scans)
| # | Sprint | Status |
|---|--------|--------|
| BI1 | BurnCounters: KV-hash counters per action[/venue][/time-bucket] | 🟢 |
| BI2 | Increment on ack/silence/unack/unsilence (alongside audit) | 🟢 |
| BI3 | burn-stats/trend read counters first; audit fallback | 🟢 |
| BI4 | Tests: counter increments; stats match | 🟢 |

### Track BJ — configurable suppression window (end-to-end)
| # | Sprint | Status |
|---|--------|--------|
| BJ1 | analytics summary suppression window param (hours) | 🟢 |
| BJ2 | dashboard control to pick window; passes through | 🟢 |
| BJ3 | Tests + tsc/build | 🟢 |

### Track BK — venue filter on trend/stats + per-venue burn breakdown
| # | Sprint | Status |
|---|--------|--------|
| BK1 | burn-stats/trend accept venue filter; counters keyed by venue | 🟢 |
| BK2 | /slo/burn-by-venue: per-venue page/ticket/active counts | 🟢 |
| BK3 | Frontend: venue breakdown on On-call page | 🟢 |
| BK4 | Tests: venue-scoped counts | 🟢 |

### Track BL — trend chart tooltips + time axis
| # | Sprint | Status |
|---|--------|--------|
| BL1 | SuppressionTrend: hover tooltip (counts + time) | 🟢 |
| BL2 | Time-axis labels (start/mid/end) | 🟢 |
| BL3 | tsc/build | 🟢 |

### Track BM — burn/suppression digest (scheduled summary)
| # | Sprint | Status |
|---|--------|--------|
| BM1 | DigestService: compose burn+suppression summary message | 🟢 |
| BM2 | Scheduler (interval) dispatches digest to a channel; config gate | 🟢 |
| BM3 | GET /slo/burn-digest preview endpoint | 🟢 |
| BM4 | Tests: digest composes; scheduler idempotent start/stop | 🟢 |

### Track BN — SQL-durable ack/silence store
| # | Sprint | Status |
|---|--------|--------|
| BN1 | BurnAckRow table; SQL ack repo (upsert/get/delete/list) | 🟢 |
| BN2 | SqlBurnAckStore parity w/ hash store; build by DATABASE_URL | 🟢 |
| BN3 | Context selects SQL store when DB configured, else hash(KV) | 🟢 |
| BN4 | Tests: persists across store instances (same DB) | 🟢 |

### Track BO — compose stack (Docker host close-out)
| # | Sprint | Status |
|---|--------|--------|
| BO1 | compose: pass DATABASE_URL + REDIS_URL to both replicas | 🟢 |
| BO2 | verify script asserts shared ack across replicas (best-effort) | 🟢 |
| BO3 | config-validation tests for the extended compose | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| BP1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| BP2 | Docs + package | 🟢 |

### Round 20 changelog (all 7 items)
- **BI — pre-aggregated counters:** BurnCounters (KV-hash, per-action + per-venue,
  hourly buckets) incremented on ack/silence/unack/unsilence; burn-stats & trend
  read counters first, audit fallback. +tests.
- **BJ — configurable suppression window:** suppression_window_hours flows through
  /analytics → ctx.analytics; frontend getAnalytics(window). +tests.
- **BK — venue filter + breakdown:** venue_id on stats/trend; /slo/burn-by-venue;
  On-call "Burn by venue" table. +tests. Live-verified.
- **BL — trend chart UX:** SuppressionTrend hover tooltip + 3-point time axis.
- **BM — digest:** DigestService/DigestScheduler (config-gated, idempotent),
  GET /slo/burn-digest preview, wired into startup/shutdown. +tests. Live-verified.
- **BN — SQL-durable ack store:** BurnAckRow table + SqlBurnAckStore (parity);
  context selects SQL when DATABASE_URL set, else hash(KV). Full-app boot+ack test
  confirms table-creation ordering. +tests.
- **BO — compose:** DATABASE_URL + shared spm-data volume on both replicas (honest
  SQLite-vs-Postgres note); config-validation tests.
- **BP1:** backend **404 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **BP2:** docs + package.

### Round 20 — COMPLETE

---

## Round 21 — Digest→channel, Postgres profile, configurable digest, net-active overlay, venue chart

### Track BQ — digest dispatch to a real notification channel
| # | Sprint | Status |
|---|--------|--------|
| BQ1 | DigestScheduler dispatch creates a Notification (configurable channel) | 🟢 |
| BQ2 | Config: BURN_DIGEST_CHANNEL + recipient; default slack | 🟢 |
| BQ3 | /slo/burn-digest?dispatch=true sends now (responder+) | 🟢 |
| BQ4 | Tests: dispatch creates a digest notification; channel honored | 🟢 |

### Track BR — Postgres compose profile + concurrency note/test
| # | Sprint | Status |
|---|--------|--------|
| BR1 | docker-compose: postgres service + profile; DATABASE_URL override | 🟢 |
| BR2 | SqlBurnAckStore concurrent-writer test (asyncio.gather upserts) | 🟢 |
| BR3 | Config-validation test for the pg profile | 🟢 |

### Track BS — configurable digest (window + min severity)
| # | Sprint | Status |
|---|--------|--------|
| BS1 | compose_digest(window_hours, min_severity) | 🟢 |
| BS2 | /slo/burn-digest accepts params; scheduler uses config | 🟢 |
| BS3 | Tests: severity filter, window | 🟢 |

### Track BT — net-active trend overlay
| # | Sprint | Status |
|---|--------|--------|
| BT1 | burn-trend buckets include net_active (silence-unsilence cumulative) | 🟢 |
| BT2 | SuppressionTrend overlays net-active line | 🟢 |
| BT3 | Tests: cumulative net computed; tsc/build | 🟢 |

### Track BU — burn-by-venue chart
| # | Sprint | Status |
|---|--------|--------|
| BU1 | Frontend: grouped bar chart (page/ticket per venue) SVG | 🟢 |
| BU2 | On-call page renders chart + keeps table | 🟢 |
| BU3 | tsc/build | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| BV1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| BV2 | Docs + package | 🟢 |

### Round 21 changelog
- **BQ — digest→channel:** notify_digest creates a Notification on a configurable
  channel; DigestScheduler dispatches via it; /slo/burn-digest?dispatch=true sends
  now (responder+). +tests. Live-verified (slack #slo-alerts).
- **BR — Postgres profile:** compose postgres service under profile "pg" + spm-pg
  volume; SqlBurnAckStore concurrent-writer test (15-way gather); pg config test.
- **BS — configurable digest:** compose_digest(window_hours, min_severity); endpoint
  + scheduler honor config (BURN_DIGEST_WINDOW_HOURS/MIN_SEVERITY). +tests.
- **BT — net-active overlay:** burn-trend buckets carry cumulative net_active;
  SuppressionTrend overlays a dashed net-active line + tooltip. Live-verified.
- **BU — burn-by-venue chart:** grouped page/ticket SVG bars on the On-call page
  above the table.
- **BV1:** backend **409 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **BV2:** docs + package.

### Round 21 — COMPLETE

---

## Round 22 — Digest webhook hop, net-active baseline, per-venue suppression, daily digest

### Track BW — digest final hop to real webhook
| # | Sprint | Status |
|---|--------|--------|
| BW1 | WebhookDispatcher.post_message(url,payload) one-shot w/ retry | 🟢 |
| BW2 | notify_digest posts to BURN_DIGEST_WEBHOOK_URL when set | 🟢 |
| BW3 | Tests: posts to URL (MockTransport); no URL → store only | 🟢 |

### Track BX — net-active baseline carried into trend
| # | Sprint | Status |
|---|--------|--------|
| BX1 | burn-trend computes pre-window net baseline from counters | 🟢 |
| BX2 | net_active starts from baseline; expose baseline in payload | 🟢 |
| BX3 | Tests: baseline reflects pre-window silences | 🟢 |

### Track BY — per-venue suppression ratio
| # | Sprint | Status |
|---|--------|--------|
| BY1 | burn-by-venue adds ack/silence counts + suppression ratio | 🟢 |
| BY2 | Frontend chart/table shows suppression per venue | 🟢 |
| BY3 | Tests: per-venue ratio | 🟢 |

### Track BZ — scheduled daily digest (distinct from hourly)
| # | Sprint | Status |
|---|--------|--------|
| BZ1 | Daily digest scheduler (24h) w/ own config + channel | 🟢 |
| BZ2 | compose_daily_digest: 24h rollup summary (counts, top venues) | 🟢 |
| BZ3 | /slo/burn-digest?kind=daily preview; both schedulers in startup | 🟢 |
| BZ4 | Tests: daily compose; scheduler gates | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| CA1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| CA2 | Docs + package | 🟢 |

### Round 22 changelog
- **BW — digest webhook hop:** WebhookDispatcher.post_message (one-shot, retry/
  backoff); notify_digest POSTs to BURN_DIGEST_WEBHOOK_URL when set and records
  SENT/FAILED on the notification. +tests. Live-verified (unreachable host →
  FAILED status recorded, dispatch path real).
- **BX — net-active baseline:** burn-trend computes a pre-window net baseline from
  counters and seeds the running net_active; baseline exposed in payload. +test.
  Live-verified (baseline=1 from a pre-window silence).
- **BY — per-venue suppression:** burn-by-venue adds ack/silence counts +
  suppression_ratio per venue; On-call table shows a Suppr. column. +test.
- **BZ — daily digest:** compose_daily_digest (24h rollup w/ top venues); /slo/
  burn-digest?kind=daily preview; separate daily scheduler (BURN_DAILY_DIGEST_*).
  +tests. Live-verified.
- **CA1:** backend **415 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **CA2:** docs + package.

### Round 22 — COMPLETE

---

## Round 23 — Slack payload, wall-clock daily digest, digest delivery history, per-venue routing

### Track CB — Slack-format webhook payload
| # | Sprint | Status |
|---|--------|--------|
| CB1 | format_slack_payload(message, channel) → blocks/text shape | 🟢 |
| CB2 | notify_digest sends slack-shaped body when channel=slack | 🟢 |
| CB3 | Tests: slack payload shape; generic text otherwise | 🟢 |

### Track CC — wall-clock daily digest scheduling
| # | Sprint | Status |
|---|--------|--------|
| CC1 | next_run_at(hh:mm) helper; scheduler sleeps to wall-clock time | 🟢 |
| CC2 | Config BURN_DAILY_DIGEST_AT=HH:MM; daily scheduler uses it | 🟢 |
| CC3 | Tests: next_run_at computes correct delay across midnight | 🟢 |

### Track CD — digest delivery history view
| # | Sprint | Status |
|---|--------|--------|
| CD1 | /notifications filter by status (SENT/FAILED); digest source | 🟢 |
| CD2 | Frontend: digest delivery panel on On-call (status badges) | 🟢 |
| CD3 | Tests: status filter | 🟢 |

### Track CE — per-venue digest routing
| # | Sprint | Status |
|---|--------|--------|
| CE1 | compose_venue_digest(venue): venue-scoped burn summary | 🟢 |
| CE2 | /slo/burn-digest?venue_id=&dispatch routes to venue channel map | 🟢 |
| CE3 | Config BURN_DIGEST_VENUE_CHANNELS=venue=#chan,... | 🟢 |
| CE4 | Tests: venue digest content; routing map | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| CF1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| CF2 | Docs + package | 🟢 |

### Round 23 changelog
- **CB — Slack payload:** format_webhook_payload shapes slack (header+section
  blocks + text fallback) vs generic {text,channel,source}; notify_digest uses it.
  +tests. Live-verified blocks shape.
- **CC — wall-clock daily:** next_run_delay(HH:MM) + DailyAtScheduler sleeps to the
  configured local time (BURN_DAILY_DIGEST_AT, default 09:00); context uses it.
  +tests. Live-verified 08:00->09:00 = 3600s, and past-time wraps to next day.
- **CD — delivery history:** /notifications adds a status filter (SENT/FAILED);
  On-call page shows a digest delivery-history panel with status badges. +test.
  Live-verified status filter.
- **CE — per-venue routing:** compose_venue_digest(venue); /slo/burn-digest accepts
  venue_id (venue-scoped, venue-access checked) and routes dispatch to
  BURN_DIGEST_VENUE_CHANNELS map. +tests. Live-verified routing to #north-room.
- **CF1:** backend **422 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **CF2:** docs + package.

### Round 23 — COMPLETE

---

## Round 24 — Scheduled per-venue fan-out, TZ-aware daily, per-venue mute, FAILED re-send

### Track CG — scheduled per-venue fan-out
| # | Sprint | Status |
|---|--------|--------|
| CG1 | VenueFanoutScheduler: per-venue digest to mapped channels on interval | 🟢 |
| CG2 | Config BURN_DIGEST_VENUE_FANOUT_ENABLED + interval; honors mute | 🟢 |
| CG3 | Tests: fan-out composes+routes per venue; skips unmapped | 🟢 |

### Track CH — timezone-aware daily scheduling
| # | Sprint | Status |
|---|--------|--------|
| CH1 | next_run_delay accepts tz (zoneinfo); DailyAtScheduler tz param | 🟢 |
| CH2 | Config BURN_DAILY_DIGEST_TZ; context passes it | 🟢 |
| CH3 | Tests: delay computed in given tz | 🟢 |

### Track CI — per-venue digest mute/snooze
| # | Sprint | Status |
|---|--------|--------|
| CI1 | DigestMuteStore (KV hash, until-epoch); is_muted/mute/unmute | 🟢 |
| CI2 | POST /slo/burn-digest/mute + DELETE (responder+, audited) | 🟢 |
| CI3 | Dispatch + fan-out skip muted venues | 🟢 |
| CI4 | Frontend: mute toggle on venue table | 🟢 |
| CI5 | Tests: mute suppresses dispatch; expiry | 🟢 |

### Track CJ — re-send FAILED digests
| # | Sprint | Status |
|---|--------|--------|
| CJ1 | POST /notifications/{id}/resend (responder+, digest only) | 🟢 |
| CJ2 | Re-posts via webhook; updates status; audited | 🟢 |
| CJ3 | Frontend: Resend button on FAILED rows | 🟢 |
| CJ4 | Tests: resend flips FAILED→SENT on success | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| CK1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| CK2 | Docs + package | 🟢 |

### Round 24 changelog
- **CG — scheduled per-venue fan-out:** VenueFanoutScheduler composes+dispatches
  each mapped venue's digest on an interval, skipping muted venues (run_once tested
  for routing + skip). Config BURN_DIGEST_VENUE_FANOUT_ENABLED/INTERVAL.
- **CH — TZ-aware daily:** next_run_delay(at, tz) uses zoneinfo; DailyAtScheduler
  takes a tz (BURN_DAILY_DIGEST_TZ). +tests (UTC vs Tokyo differ; bad tz falls back).
- **CI — per-venue mute/snooze:** DigestMuteStore (KV hash, until-epoch, prune on
  read); POST/DELETE /slo/burn-digest/mute (responder+, audited); dispatch + fan-out
  skip muted; burn-by-venue shows muted; On-call mute toggle. +tests. Live-verified.
- **CJ — resend FAILED digests:** POST /notifications/{id}/resend (responder+, digest
  only) re-posts via webhook, updates status, audited; On-call Resend button on
  FAILED rows. +tests. Live-verified (→SENT).
- **CK1:** backend **431 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **CK2:** docs + package.

### Round 24 — COMPLETE

---

## Round 25 — Per-venue webhook URLs, scheduler status panel, mute audit, test-webhook

### Track CL — per-venue webhook URLs
| # | Sprint | Status |
|---|--------|--------|
| CL1 | Config BURN_DIGEST_VENUE_WEBHOOKS=venue=url,...; map property | 🟢 |
| CL2 | venue dispatch + fan-out + resend use per-venue URL (fallback global) | 🟢 |
| CL3 | Tests: per-venue URL chosen; fallback when unmapped | 🟢 |

### Track CM — scheduler status panel
| # | Sprint | Status |
|---|--------|--------|
| CM1 | Schedulers track last_run/last_status/next_run; status() method | 🟢 |
| CM2 | GET /ops/schedulers returns each scheduler's status (admin) | 🟢 |
| CM3 | Frontend: scheduler status panel on On-call page | 🟢 |
| CM4 | Tests: status reflects run; endpoint RBAC | 🟢 |

### Track CN — mute audit history
| # | Sprint | Status |
|---|--------|--------|
| CN1 | /slo/burn-digest/mute-events: digest.mute/unmute audit history | 🟢 |
| CN2 | Frontend: mute history on On-call (or surface in venue panel) | 🟢 |
| CN3 | Tests: history returns mute/unmute; RBAC | 🟢 |

### Track CO — test-webhook
| # | Sprint | Status |
|---|--------|--------|
| CO1 | POST /ops/test-webhook posts a sample payload to a URL (admin) | 🟢 |
| CO2 | Returns delivered + status; uses dispatcher.post_message | 🟢 |
| CO3 | Frontend: Test webhook button | 🟢 |
| CO4 | Tests: success + failure (MockTransport) | 🟢 |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| CP1 | Full backend suite + frontend tsc/build + node unit green | 🟢 |
| CP2 | Docs + package | 🟢 |

### Round 25 changelog
- **CL — per-venue webhook URLs:** BURN_DIGEST_VENUE_WEBHOOKS map +
  webhook_url_for_venue(venue) (per-venue, else global); venue dispatch + fan-out
  use it. +tests. Live-verified resolution + fallback.
- **CM — scheduler status:** SchedulerStats mixin (last_run/last_status/runs/
  next_run) on all digest schedulers; GET /ops/schedulers (admin). On-call panel
  shows status. +tests. Live-verified.
- **CN — mute audit:** GET /slo/burn-digest/mute-events (digest.mute/unmute
  history); On-call mute-history panel. +test. Live-verified mute+unmute recorded.
- **CO — test-webhook:** POST /ops/test-webhook posts a sample payload (admin),
  returns delivered; On-call Test-webhook input+button. +tests (200/500 via
  MockTransport). Live-verified.
- **CP1a:** interval schedulers now record their real next-wake timestamp (set before each sleep); /ops/schedulers shows the true next run, not an estimate. +test.
- **CP1:** backend **440 pass**; frontend tsc -b + vite build green; 7 node RBAC
  unit tests pass. **CP2:** docs + package.

### Round 25 — COMPLETE

---

## Round 26 — Playbook V02: external alert routing + remediation dispatch + CI/E2E

Implemented the genuinely-missing operational deliverables from the V02 playbook
(infra primitives like idempotency/kv/burn/metrics already existed):

- **P5.S2 — AlertRouter** (`app/services/alert_router.py`): PagerDuty Events v2 +
  OpsGenie Alerts API; degrades to log-only without creds. Wired into
  NotificationService.notify_burn_alert (external routing on configured creds).
  Config: PAGERDUTY_ROUTING_KEY, OPSGENIE_API_KEY. +5 tests (MockTransport).
- **P5.S3 — RemediationDispatcher** (`app/services/dispatch_service.py`): Cloud
  Workflows / Ansible AWX / generic webhook; no-op (target=none) without a
  backend. Wired into the /remediations/{id}/execute route (ExecuteResponse gains
  a `dispatch` field). Config: CLOUD_WORKFLOWS_URL, ANSIBLE_AWX_URL/TOKEN,
  REMEDIATION_WEBHOOK_URL. +5 tests (MockTransport).
- **P1.S1 — CI workflow** (`.github/workflows/ci.yml`): backend pytest+cov,
  frontend tsc+vite, Playwright e2e, container build.
- **P1.S2 — Playwright** (`frontend/playwright.config.ts` + `frontend/e2e/smoke.spec.ts`):
  health + app-load + problems smoke tests.

Backend **450 pass** (+10); frontend tsc -b + vite build green; 7 node RBAC tests.

### Round 26 — COMPLETE (P5.S2, P5.S3, P1.S1, P1.S2)

---

## Round 27 — Playbook V02 P6 width modules (batch 1)

Worked straight through the playbook flow (no pauses), adding five enterprise
width modules end-to-end (model → service → RBAC routes → tests), each wired into
AppContext + main router registration:

- **P6.M1 — Runbook library** (`models/runbook.py`, `services/runbook_service.py`,
  `api/routes_runbooks.py`): versioned/tagged procedures, CRUD, execute (dispatches
  automation steps via RemediationDispatcher), execution history. New perms
  RUNBOOK_READ/WRITE. **+9 tests**.
- **P6.M3 — Postmortem workflow** (`models/postmortem.py`,
  `services/postmortem_service.py`, `api/routes_postmortems.py`): blameless review
  with timeline, action items, publish, Markdown export. New perms
  POSTMORTEM_READ/WRITE. **+6 tests**.
- **P6.M7 — Cost/capacity analytics** (`models/cost_analytics.py`,
  `services/cost_analytics_service.py`): per-service spend + utilisation +
  right-sizing flags. **+2 tests**.
- **P6.M9 — Change-event correlation** (`models/change_event.py`,
  `services/change_event_service.py`): record changes, link to incidents,
  time-proximity correlation. **+3 tests** (incl. correlate ISO-`+` fix).
- **P6.M5 — Fleet command center** (`/api/v1/fleet`): per-venue operational rollup
  reusing analytics-by-venue; added EntityVenueResolver.known_venues(). **+1 test**.

All five modules are RBAC-guarded; enterprise routes live in
`api/routes_enterprise.py`. Backend **471 pass** (+21); frontend tsc+build green;
7 node RBAC tests pass.

### Round 27 — COMPLETE (P6.M1, M3, M5, M7, M9)
### Still queued (continuing next): P2 Alembic, P4 Cloud Run/Dockerfile/deploy.sh,
### P6.M2 escalation, P6.M6 ChatOps, P6.M8 Davis feedback, P5.S5 k6 load, frontend pages.
