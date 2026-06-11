# StadiumPulse Marshal — Console Enhancements

This build applies the four SpoofVane console enhancements to StadiumPulse
Marshal, adapted to its AIOps matchday domain and its **existing** backend RBAC
model (it already had roles, permissions and JWT/API-key auth — we did not
invent a parallel one).

## What changed

### 1. Demo-seed sign-in
- New `frontend/src/pages/LoginPage.tsx` + auth context
  (`frontend/src/lib/auth.tsx`). On sign-in it calls the new backend
  `POST /api/v1/auth/login`; if the backend is unreachable it falls back to an
  in-browser **seed** principal so the console is fully usable offline.
- One-tap **quick-fill chips** for every demo account.
- Session persists across refresh (sessionStorage); **Sign out** in the user
  menu clears it.

### 2. Multi-venue (the matchday analogue of multi-tenant)
- A **venue switcher** in the top bar. Two demo venues — Arena North
  (Manchester) and Olympic Park (London). Admin / platform accounts can switch;
  single-venue roles are scoped to their venue.

### 3. Grouped, collapsible, role-gated sidebar
- The old flat top-tabs are replaced by a left rail grouped into
  **Operations / Reliability / Governance / Administration**.
- Pages above your role are hidden. Rail collapses to an icon strip via the
  toggle button or the `[` key.

### 4. Health surface
- New **Health** page wired to `GET /api/v1/health` (liveness),
  `/api/v1/ready` (dependency probes) and `/api/v1/config` (mode), plus a
  console page-coverage table.

## Roles (unchanged from the backend policy)

| Role | Can | Cannot |
|------|-----|--------|
| viewer | read incidents/SLO/analytics | write, approve, admin |
| operator | + write incidents, run scenarios | approve remediations |
| responder | + **approve** remediations | webhook/settings admin |
| admin | everything | — |

A privileged action (approve / reject / execute a remediation, change settings)
is enforced **on the backend** via `require_permission`, not just hidden in the
UI. Demo password for every account: `MatchdayDemo123!`.

## Backend changes
- `app/api/routes_auth.py` — new `/api/v1/auth/login` (mints a demo JWT carrying
  the role claim) and `/api/v1/auth/demo-users` (lists accounts for quick-fill).
- `app/api/auth.py` — `get_principal` now honors a presented bearer token even
  when auth is globally disabled, so role gating is demonstrable without
  flipping `AUTH_ENABLED`. A demo fallback JWT secret makes the bundled login
  work out of the box.
- `app/api/routes.py` — **added missing authorization guards** to
  `remediations/{id}/approve|reject|execute` and `PATCH /settings` (these were
  previously unguarded — any caller could approve a remediation).
- `app/api/routes_webhooks.py` — fixed a 204 route that crashed under the
  installed FastAPI (a 204 must not declare a response body).

## Run it

```bash
# backend
cd backend && pip install -e . --break-system-packages
python -m uvicorn app.main:app --port 8000

# frontend (dev, proxies to :8000)
cd frontend && npm install && npm run dev      # http://localhost:5173

# or serve the built SPA from the backend
cd frontend && npm run build                   # emits frontend/dist
# (the backend mounts frontend/dist at / automatically)
```

Sign in with any demo account, e.g. `responder@arena-north.demo` /
`MatchdayDemo123!`, or click a quick-fill chip.

## Tests
```bash
cd backend && python -m pytest          # 225 pass (incl. auth/RBAC)
cd frontend && node --test --experimental-strip-types src/lib/rbac.test.ts   # 7 pass
cd e2e && npm install && npx playwright test    # login/sidebar/venue/rbac (CI)
```

> Playwright needs a browser binary that can't be downloaded in the build
> sandbox, so the e2e specs are authored/updated to run in CI. The runnable
> `node:test` RBAC test and the backend suite are the in-sandbox proof; the live
> stack (SPA + login + role-gated 403) was verified by hand.

---

## Round 2 — Enterprise hardening

A review pass found and fixed genuine gaps (not cosmetics):

### Venue-scoped authorization (was cosmetic, now enforced)
- The `Principal` now carries `venues` + `all_venues`; the login JWT includes
  these claims and `get_principal` resolves them.
- New `require_venue_access` dependency enforces that a caller may only
  list/create incidents within a venue they're scoped to. Cross-venue access is
  **403** (proven by tests + live). Platform/admin principals are cross-venue.
- New `GET /api/v1/venues` returns only the venues the caller can see.
- New `GET /api/v1/auth/me` rehydrates a session from the token (used on refresh).

### UI now matches backend RBAC (was: nav-only gating)
Previously the sidebar hid pages by role but action buttons were always shown,
so a viewer saw Approve/Execute the backend would 403. Now there is a reusable
permission layer — `lib/permissions.tsx` (`useCan`, `<Can>`,
`<RequirePermission>`) — and every privileged affordance is gated:

| Action | Permission |
|--------|-----------|
| Approve / Reject / Apply remediation | `remediation:approve` |
| Incident transition / escalate / open | `incident:write` |
| Change scenario | `scenario:write` |
| Toggle auto-approve guardrail | `settings:write` |

A viewer now sees clear read-only notes instead of dead buttons.

### Session-expiry handling
Both HTTP layers detect **401** and clear the session, returning the user to the
login gate instead of failing silently.

### Modularisation (no single-file dumping)
- `lib/auth.tsx` (245 lines) → `lib/auth/{index,types,session-store,seed-auth,live-auth}`.
- Shell chrome → `components/shell/{Sidebar,TopBar,VenueSwitcher,UserMenu,HealthPill}`.
- `App.tsx` reduced from 207 → 90 lines (composition only).

### Tests
- Backend **232 pass** (incl. venue authz + cross-venue 403 + `/auth/me` +
  `/venues` scoping).
- Frontend **7 runnable RBAC unit tests** (`node --test src/lib/rbac.test.ts`).
- e2e extended with permission-gating assertions (run in CI).

---

## Round 3 — Full venue enforcement, OIDC SSO, deeper modularisation

### Per-entity venue authorization (closes the by-id loophole)
Round 2 enforced venue scope on the incident *list filter*. A reviewer would
note that an operator could still act on another venue's incident by hitting
`/incidents/{id}` directly. Round 3 closes this: every incident sub-route
(`GET /{id}`, `transition`, `assign`, `note`, `escalate`) loads the entity and
runs `require_venue_access(principal, incident.venue_id)` before acting. Proven
by tests and live — an Arena North operator gets **403** on an Olympic Park
incident for both read and write; a platform (cross-venue) principal is allowed.

### OIDC single sign-on (enterprise SSO)
New `app/services/oidc_service.py` implements an authorization-code flow:
provider discovery, signed-state CSRF protection, code→token exchange, and
mapping of ID-token claims to the app's role + venue scope. It mints the app's
own session JWT so an SSO login produces an identical `Principal` to the demo
password flow. Endpoints: `GET /api/v1/auth/oidc/{status,login,callback}`.

It is **off by default and degrades gracefully** — when `OIDC_ISSUER` /
`OIDC_CLIENT_ID` / `OIDC_REDIRECT_URI` are unset, `status` returns
`{"enabled": false}`, `login` returns 401, and the SPA simply doesn't show the
SSO button. Configure via env:

```
OIDC_ISSUER=https://your-idp.example.com
OIDC_CLIENT_ID=stadiumpulse
OIDC_CLIENT_SECRET=…
OIDC_REDIRECT_URI=https://your-app/api/v1/auth/oidc/callback
OIDC_ROLES_CLAIM=roles      # default
OIDC_VENUES_CLAIM=venues    # default
```

The frontend shows a "Sign in with SSO" button when enabled and captures the
returned token from the callback fragment, then rehydrates via `/auth/me`.

### Deeper modularisation
- `TriagePage` 322 → 141 lines: data + IO moved to a `useTriage` hook; the feed
  and decision-audit regions are now `components/triage/ProblemFeed` and
  `DecisionAuditLog`.
- `client.ts` 295 → 254 lines: shared HTTP core extracted to `api/core.ts`
  (base URL, bearer token, 401 handling, idempotency key) and system endpoints
  to `api/system.ts`; `client.ts` is now a barrel that re-exports them.

### Tests
- Backend **245 pass** (+13 this round: venue per-entity enforcement + OIDC).
- Frontend `tsc -b` + `vite build` green; 7 runnable RBAC unit tests pass.
- Live-verified: OIDC `status`, per-entity cross-venue **403** on read + write.

---

## Round 4 — Production-grade OIDC (signature verification)

Round 3 shipped the OIDC flow but decoded the ID token without verifying the
provider signature — fine for a demo, not for production. Round 4 closes that.

### Strict verification (default)
`OIDCService` now, by default (`OIDC_VERIFY_SIGNATURE=true`):
- fetches the provider **JWKS** and verifies the ID-token **RS256/ES256
  signature** (via PyJWT's `PyJWKClient`),
- validates **issuer**, **audience** (must equal the client id), and **expiry**
  (`exp`/`iat` required),
- issues a **nonce** in the authorization request, binds it into the signed
  `state`, and enforces it on the callback (replay/CSRF defence).

A demo escape hatch (`OIDC_VERIFY_SIGNATURE=false`) allows an unsigned local IdP
— the nonce is still checked, but the signature isn't. Default is strict.

### Mock IdP + full-flow tests
A self-contained mock IdP (RSA keypair, discovery doc, JWKS, token endpoint via
`httpx.MockTransport`) exercises the real signed flow end to end:
- valid signed token → identity with mapped role + venues ✅
- **bad signature → rejected**, **wrong audience → rejected**,
  **expired → rejected**, **nonce mismatch → rejected**,
- demo unverified mode still accepts an unsigned token (nonce enforced).

### Tests
Backend **251 pass** (+6 full-flow/negative OIDC). Frontend build unchanged/green.

---

## Round 5 — Venue-partitioned data domains + session refresh

### Venue partitioning beyond incidents
`Problem` now carries `venue_id`, and the seeded matchday problems are split
across the two demo venues. Venue scope is enforced on the observability data,
not just incidents:
- `GET /problems` returns only problems the caller's venues cover (platform
  principals see all);
- `GET /problems/{id}` is **403** across venues;
- `GET /incidents-search` results are scoped;
- creating an incident inherits the source problem's venue.

**Scope semantics (important):** venue restriction applies only when a token
explicitly carries venue scope (a `venue_id`/`venues` claim or `all_venues`).
Tokens with no venue information are treated as unconstrained, so service/API-key
credentials and legacy tokens keep working; the demo login always sets a venue,
so demo roles are properly scoped. Verified live: an Arena North operator sees
only Arena North problems and is 403 on an Olympic Park problem.

### Session refresh (silent token renewal)
`POST /api/v1/auth/refresh` exchanges a still-valid token for a fresh one,
preserving subject, roles and venue scope. It requires a valid token (an expired
or tampered token is 401), so it cannot resurrect a dead session. The SPA renews
silently every 30 minutes for live sessions, so long matchday shifts don't get
bounced to the login screen mid-incident.

### Tests
Backend **257 pass** (+13 this round). Frontend `tsc -b` + `vite build` green;
7 node RBAC unit tests pass.

---

## Round 6 — Entity→venue partitioning + OIDC refresh-token rotation

### Entity-keyed domains are now venue-partitioned
SLO budgets, SLO trends, entities and analytics are keyed by *entity*, not
venue. `Entity` now carries `venue_id`, and an `EntityVenueResolver`
(entity_id → venue_id, cached, rebuilt on scenario change) lets those domains be
scoped:
- `/entities` returns only the caller's venues' entities;
- `/slo` and `/slo/trends` return only budgets/trends for entities in the
  caller's venues;
- `/analytics` filters incidents and SLO rollups to the caller's venues;
- explicit cross-venue `?venue_id=` filters are **403**.

Verified live: an Olympic Park operator sees none of the (Arena North) payment
SLOs and is 403 on a cross-venue entities filter; a platform principal sees all.

### OIDC refresh-token rotation with theft detection
Round 5 added a simple re-mint. Round 6 implements the full OAuth2 rotation
pattern via a `RefreshStore`:
- login starts a refresh-token **family**;
- each `/auth/refresh` consumes the presented token and issues a new one in the
  same family (rotation), returning a fresh access token (unique `jti`) too;
- presenting an already-rotated token is treated as **theft** — the whole
  family is revoked and the call is 401;
- `/auth/logout` revokes the active family.

The SPA stores the refresh token, rotates it on the 30-minute silent-refresh
tick, signs out if a rotation is rejected, and revokes the family on logout.

### Tests
Backend **269 pass** (+12 this round: entity/SLO/analytics scoping + refresh
rotation/reuse/logout). Frontend `tsc -b` + `vite build` green.

---

## Round 7 — Persistent refresh-token store + Dynatrace zone→venue mapping

### Durable, prunable refresh-token store
The refresh-token rotation from Round 6 now runs over a `RefreshTokenRepository`
with two implementations:
- **memory** (demo / tests), and
- **SQL** (a `refresh_tokens` table) selected automatically when `DATABASE_URL`
  is set.

`RefreshStore` is async over the repo and keeps the same guarantees (rotation,
reuse-detection family revocation, logout revoke), adding `prune()` to clear
expired/consumed/revoked rows. Verified live against SQLite: rotation works,
reuse is 401, and rows persist across the process.

### Dynatrace management-zone → venue mapping
Venue ownership for entity-keyed domains (SLO/analytics/entities) no longer
relies on a bespoke field. The `EntityVenueResolver` derives venue from an
entity's **management-zone tag** (e.g. `mz:Arena North`) via a configurable map:

```
VENUE_ZONE_MAP=Arena North=venue_arena_north,Olympic Park=venue_olympic_park
VENUE_ZONE_TAG_KEY=mz
```

Resolution priority is: explicit `venue_id` first (demo / already-mapped), then
the management-zone tag. This is the realistic live-tenant path — entities that
arrive from Dynatrace tagged only with a management zone resolve to a venue
without any code change. Mock entities now carry `mz:` tags to exercise it.

### Tests
Backend **278 pass** (+9 this round: async store, SQL rotation+prune, 7 resolver
cases incl. the live zone-only shape). Frontend `tsc -b` + `vite build` green.

---

## Round 8 — Token hashing at rest + prune scheduler + live Dynatrace zones

### Refresh tokens hashed at rest
`RefreshStore` now persists only the SHA-256 **hash** of each refresh token; the
raw token is returned to the client once and never stored. A database leak
therefore exposes no usable tokens. All lookups (rotate/revoke/subject) hash the
presented token first. Verified: the raw token appears in neither the in-memory
store nor the SQLite `refresh_tokens` table — only its hash.

### Background prune scheduler
A `PruneScheduler` async task runs for the app lifespan, sweeping
expired/consumed/revoked refresh tokens every `REFRESH_PRUNE_INTERVAL_SECONDS`
(default 1h). Start is idempotent, shutdown cancels cleanly, and a failing prune
never kills the loop. Verified live: the scheduler logged a sweep that removed a
consumed token.

### Live Dynatrace management-zone pull
The zone→venue map now comes from a `ZoneSource`:
- `StaticZoneSource` — from `VENUE_ZONE_MAP` config (Round 7 behaviour);
- `DynatraceZoneSource` — pulls management zones from the Dynatrace config API
  (`/api/config/v1/managementZones`) when a tenant + token are configured.

`build_zone_source` selects live when a tenant is present, else static. Static
config entries always override the live map, and any API error falls back to
static — the optional live source never hard-fails the resolver.

### Tests
Backend **290 pass** (+12 this round: hash-at-rest, scheduler, zone sources).
Frontend `tsc -b` + `vite build` green.
