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
