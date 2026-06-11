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

---

## Round 9 — Auto zone-id mapping + auth rate-limiting + auth audit events

### Fully-automatic zone mapping by stable id
`VENUE_ZONE_ID_MAP` (`zoneId=venue`) lets the live `DynatraceZoneSource` map
management zones by their **id** — stable across zone renames — in addition to
name. The source fetches id+name and keys the result by zone name (what entity
tags carry as `mz:<name>`). Precedence is zone-id map > static name map, so an
operator can pin a venue by id regardless of how the zone is named.

### Always-on auth rate-limiting
A reusable `RateLimiter` token bucket protects `/auth/login` and `/auth/refresh`
with a strict per-IP limit (`AUTH_RATE_LIMIT_PER_MINUTE`, default 10),
independent of the global middleware toggle — so credential-stuffing and
token-guessing are throttled even when the global limiter is off. Over the limit
returns 429 with `Retry-After`; the client IP is taken from `X-Forwarded-For`
when present. Verified live: the 4th rapid login attempt returns 429 while a
request from a different IP is unaffected.

### Auth audit trail
Every auth event is now recorded in the existing audit log: login
success/failure, refresh success/failure, **refresh-reuse detection (token
theft)**, and logout — each with actor, outcome and source IP. Auditing is
best-effort and never blocks the auth path. These entries are queryable through
the same audit API as incident mutations.

### Tests
Backend **297 pass** (+7 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 10 — Multi-instance readiness + auth audit in the console

### Shared backends for horizontal scale
A `KVBackend` abstraction makes cross-instance state possible:
- `MemoryKV` — process-local (single instance / demo / tests);
- `RedisKV` — shared across replicas, used when `REDIS_URL` is set (redis-py is
  imported lazily, so the dependency is optional).

`RateLimiter.check_shared` runs an atomic fixed-window limit over the KV, so the
always-on auth rate limit becomes **global across instances** in a clustered
deployment; with no KV it transparently falls back to the in-process token
bucket. `build_kv` selects Redis when configured and degrades to memory if
Redis is unavailable, so a misconfiguration never blocks boot. (Refresh tokens
were already shareable via the SQL repository from Round 7.)

### Authentication audit trail in the UI
`GET /api/v1/auth/events` (admin-only, gated by `settings:write`) returns the
auth audit trail newest-first. A new **Security** page under Governance surfaces
it: KPIs for total events, failures and token-reuse alerts; a filter for
all / failures / token-reuse; and a table that flags theft detections. Verified
live: viewers are 403, admins see login successes and failures.

### Tests
Backend **304 pass** (+7 this round: KV + shared limiter, /auth/events).
Frontend `tsc -b` + `vite build` green; 7 node RBAC unit tests pass.

---

## Round 11 — Multi-instance compose, security hardening, per-venue dashboards

### Compose: Redis + two replicas (multi-instance, verified)
`docker-compose.yml` runs Redis, two app replicas and an nginx round-robin load
balancer (`:8088`); `scripts/verify_multi_instance.sh` hammers `/auth/login` and
asserts the shared rate limit produces a 429 within 6 attempts *even though
requests alternate across replicas* — only possible because both replicas share
one Redis window counter. Docker isn't available in the build sandbox, so the
property the stack depends on is proven directly by tests: two independent app
instances sharing one KV enforce a single global cap (5), while independent KVs
allow double (10).

### Security headers + CSRF
Every response now carries a hardened header set — Content-Security-Policy
(same-origin, `frame-ancestors 'none'`), `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, and
optional HSTS (enable behind TLS). A double-submit-cookie CSRF guard is available
for cookie-authenticated deployments; it exempts `Authorization`/`X-API-Key`
requests since token auth cannot be CSRF'd. All toggle via config.

### Per-venue analytics dashboards
`GET /analytics/by-venue` returns scoped per-venue rollups — incidents (total /
open / resolved), MTTR/MTTA, severity mix, and SLO health (% of a venue's SLOs
not breaching). The Reliability page renders a card per venue plus a cross-venue
incident-volume comparison; a venue-scoped operator sees only their own venue.

### Module depth
The auth audit endpoint gained `action`/`outcome` filters, `offset`/`limit`
pagination and `fmt=csv` export; the Security page got server-side pagination
(prev/next), a filter reset, and an Export CSV button.

### Tests
Backend **314 pass** (+10 this round). Frontend `tsc -b` + `vite build` green;
7 node RBAC unit tests pass.

---

## Round 12 — Nonce CSP, default-on CSRF, burn-rate alerting, real Redis e2e

### Nonce-based Content-Security-Policy
The CSP is now per-request nonce-based: `SecurityHeadersMiddleware` generates a
fresh nonce each request, the served SPA HTML has the nonce injected into its
script/style tags, and `script-src` is `'self' 'nonce-…'` with **no
`'unsafe-inline'` for scripts** — closing the inline-script XSS vector. Verified
live: nonces differ per request.

### CSRF wired and default-on-capable
`GET /auth/csrf` issues a double-submit token cookie; the SPA's HTTP client reads
it and echoes `X-CSRF-Token` on every state-changing request. The CSRF guard is
bearer-exempt (token auth can't be CSRF'd), so enabling it does not break the
SPA's normal Bearer flows — it's safe to turn on for cookie-auth deployments.

### Multi-window SLO burn-rate alerting
A burn-rate engine implements the Google SRE multi-window/multi-burn-rate tiers:
fast (14.4× over 1h/5m → **page**), medium (6× over 6h/30m → page), slow (3× over
24h/2h → **ticket**), trickle (1× → ticket). A tier fires only when both its
windows exceed the factor (anti-flap). `GET /slo/burn-alerts` is venue-scoped,
counts are surfaced in `/analytics`, and the Reliability page shows a burn-alert
banner. Verified live: the degraded Payments SLO raises a 1.5× ticket alert.

### Real Redis end-to-end
The shared-state design is now validated against a real Redis protocol
(`fakeredis`, including `redis.asyncio`): two app instances sharing one Redis
enforce a single global auth rate limit — proven through a full HTTP round-robin
path across two ASGI app instances, not just at the limiter level. The
`docker-compose.yml` (Redis + 2 replicas + nginx) remains for a Docker host;
`scripts/verify_multi_instance.sh` exercises it there.

### Tests
Backend **328 pass** (+14 this round). Frontend `tsc -b` + `vite build` green;
7 node RBAC unit tests pass.

---

## Round 13 — Burn→notification routing, true per-window burn rates, container loop

### Burn alerts route to notification channels
The Notification model is generalized (optional `incident_id`, plus `source`,
`severity`, `venue_id`) so non-incident notifications are first-class. A burn
alert is routed by severity — **page → PagerDuty + SMS**, **ticket → email +
Slack** — and deduplicated per (SLO, severity) within the tier's window so a
sustained burn doesn't spam. Burn evaluation auto-notifies; the notifications API
surfaces burn-sourced alerts. Verified live: a ticket-tier burn routed to email +
Slack and did not duplicate on re-evaluation.

### True multi-window burn rates
`MetricsHistory` records per-SLO error-rate samples with timestamps;
`error_rate_over(slo, hours)` returns the trailing-window rate. The burn engine
now evaluates each tier with the **real long- and short-window rates** (e.g.
1h + 5m for fast), so an already-recovered incident (long window hot, short
window clean) does not page — the genuine multi-window guard. Without samples it
falls back to the budget's single rate.

### Multi-instance container loop
`docker-compose.yml` (Redis + two app replicas + nginx LB) and
`scripts/verify_multi_instance.sh` are now guarded by config tests (both replicas
share `REDIS_URL`, the LB balances both, the verifier asserts a 429), and
`make multi-up / multi-verify / multi-down` run the stack on any Docker host. The
runtime property is already proven in-sandbox by the real-Redis HTTP round-robin
test.

### Tests
Backend **342 pass** (+14 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 14 — On-call-routed burns, metrics-backend adapter, on-call console

### Burn alerts route through the on-call directory
Burn-rate alerts now page the same people as incident escalation, via an
`OnCallDirectory` that maps severity → escalation tier → on-call engineer:
page → incident commander (TIER3) + SRE (TIER2); ticket → SRE (TIER2) + venue
ops (TIER1). Each target carries the engineer's real handle and preferred
channels, with a fallback to the highest available tier if one is vacant.
Verified live: a ticket burn routed to the real SRE handle (slack+sms) and venue
ops (email), not hardcoded addresses.

### Metrics-backend adapter feeds true per-window series
A `MetricsSource` yields a per-SLO error-rate timeseries that is backfilled into
`MetricsHistory`, so the multi-window burn engine evaluates on genuine windowed
data. `SyntheticMetricsSource` shapes deterministic series (recent spike /
sustained / healthy / recovered) for mock mode; `DynatraceMetricsSource` pulls
from the Dynatrace Metrics v2 API and converts datapoints to error-rate samples,
falling back to synthetic on any error.

### On-call console
`GET /oncall` returns the roster, escalation policy ladders, and the resolved
burn-alert targets per severity. The On-call page (Administration) shows all
three so an operator can see exactly who a page or ticket would reach before it
fires.

### Tests
Backend **356 pass** (+14 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 15 — Schedule-aware on-call, per-SLI metric selectors, banner targets

### On-call schedule source (rotation + external adapter)
The on-call roster is now resolved from a `ScheduleSource` rather than a fixed
list: `RotatingScheduleSource` rotates a per-tier pool on a fixed shift cadence
(with a `next_handoff`), and `ExternalScheduleSource` pulls the current on-calls
from a PagerDuty/Opsgenie-shaped `/oncalls` API (schedule→tier mapping, graceful
fallback to static). The directory is refreshed before burn routing and on
`/oncall` reads, so alerts always page whoever holds the pager now.

### Per-SLI Dynatrace metric selectors
`DynatraceMetricsSource` now chooses the metric selector by SLI kind
(availability/error → error rate, latency → response time, throughput → request
count, saturation → CPU), filtered to the SLO's service entity, with a per-SLI
`METRIC_SELECTOR_MAP` override for bespoke metrics.

### Burn → on-call target on the banner
`/slo/burn-alerts` enriches each alert with its resolved on-call targets, and the
Reliability burn banner shows "pages <who>" inline — so an operator sees who a
burn would wake without leaving the page. The On-call page surfaces the schedule
source and the next-handoff time.

### Tests
Backend **366 pass** (+10 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 16 — Rotation pools, burn ack/silence, metric-selector preview

### Rotating on-call pools
The default deployment now rotates a per-tier pool (two engineers per tier) on a
fixed shift cadence, so the resolved roster advances each shift. `/oncall`
exposes the rotation (current holder + who is next per tier, plus next-handoff)
and the On-call page renders it. Rotation is config-toggled
(`ONCALL_ROTATION_ENABLED`, `ONCALL_SHIFT_HOURS`); disabling it falls back to the
static roster.

### Burn-alert acknowledge / silence
Responders can acknowledge a burn alert (recorded with who/when, audited) or
silence it for a period — a silenced alert is marked and not dispatched, so a
burn already being worked stops paging. The Reliability banner shows Ack /
Silence buttons (responder+), acked/silenced styling, and the alert list carries
`acked_count` / `silenced_count`. Endpoints: `POST /slo/burn-alerts/{slo}/ack`
and `/silence`.

### Metric-selector preview
`GET /slo/{id}/metric-preview` returns the resolved metric selector, a sample
error series, and the per-window error rates (5m/1h/6h) the burn engine would
use — so an operator can confirm a selector resolves before relying on it.
Venue-scoped; 404 for an unknown SLO.

### Tests
Backend **374 pass** (+8 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 17 — Shared ack store, un-ack/expiry, on-call ack view, burn history

### Multi-instance acknowledge / silence
Burn ack/silence state moved to a KV-backed `SharedBurnAckStore` (a single JSON
document in Memory or Redis), so acknowledging or silencing on one replica is
seen by all. Acks auto-expire (`BURN_ACK_TTL_SECONDS`) and silences expire at
their deadline, pruned on read.

### Un-ack / un-silence
Responders can clear an acknowledgement or lift a silence early via
`DELETE /slo/burn-alerts/{slo}/ack` and `/silence` (audited); the Reliability
banner shows a Clear control on acked/silenced alerts.

### On-call ack/silence view + burn history
`/oncall` now includes the active acks and silences, and `GET /slo/burn-events`
returns the ack/silence audit trail (responder+, filterable by action). The
On-call page surfaces both — current acknowledgements/silences and a burn-alert
history table.

### Tests
Backend **384 pass** (+10 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 18 — Per-key hash ack store, burn-history UX, suppression analytics

### Hash-backed ack store (no last-write-wins)
The KV backend gained hash operations (Memory + Redis), and burn ack/silence
state now lives in per-(slo,severity) hash fields via `HashBurnAckStore`. Acking
or silencing one alert no longer rewrites the whole document, so concurrent
updates to different alerts across replicas can't clobber each other (verified by
a 20-way concurrent-ack test). The legacy in-process store was removed.

### Burn-history filter / pagination / CSV
`/slo/burn-events` supports an action filter, offset/limit pagination, and
`fmt=csv`; the On-call page's burn-history table has matching filter buttons and
an Export CSV control.

### Suppression analytics
`/slo/burn-stats` aggregates the ack/silence audit trail over a trailing window
into counts, a suppression ratio (silences vs acknowledgements), active ack and
silence counts, and the most-silenced targets — surfaced as a summary on the
On-call page so habitually-silenced (noisy) alerts stand out.

### Tests
Backend **391 pass** (+7 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 19 — Single ack-store path, pipelined summary, suppression trend, dashboard KPIs

### One ack-store path
The single-document `SharedBurnAckStore` was removed; `HashBurnAckStore`
(per-field, multi-instance) is the only path.

### Pipelined hash summary
`KVBackend.hgetall_many` reads multiple hashes in one Redis pipeline round-trip
(a loop on Memory), with a defensive bytes-decode for clients that don't apply
`decode_responses` to pipelined replies. The ack-store summary uses it.

### Suppression trend
`GET /slo/burn-trend` buckets ack/silence counts over a window; the On-call page
renders an inline SVG stacked-bar trend (acks vs silences) with a legend, beside
the suppression ratio and most-silenced targets.

### Burn KPIs on the analytics dashboard
The analytics summary now carries burn alert counts, the suppression ratio, and
active ack/silence counts; the dashboard's Operational analytics panel surfaces
them, so burn health sits alongside incident and SLO metrics.

### Tests
Backend **391 pass**. Frontend `tsc -b` + `vite build` green; 7 node RBAC tests.

---

## Round 20 — Counters, configurable window, venue breakdown, chart UX, digest, SQL durability, compose

### Pre-aggregated counters
Burn ack/silence actions increment KV-hash counters (per action, per venue,
hourly buckets), so `burn-stats` and `burn-trend` no longer scan the audit trail
on every call — they read counters first and fall back to the audit only when
counters are empty (fresh KV after restart).

### Configurable suppression window
The analytics suppression KPIs accept a `suppression_window_hours` parameter
end-to-end (API + dashboard fetch).

### Venue filter + per-venue breakdown
`burn-stats`/`burn-trend` accept a `venue_id` filter, and `/slo/burn-by-venue`
returns per-venue page/ticket and active ack/silence counts, shown as a table on
the On-call page.

### Trend chart UX
The suppression trend gained hover tooltips (counts + bucket time) and a
three-point time axis.

### Burn/suppression digest
A config-gated `DigestScheduler` periodically composes and dispatches a
burn/suppression summary; `GET /slo/burn-digest` previews the message.

### SQL-durable ack/silence store
`SqlBurnAckStore` persists acknowledgements/silences in a `burn_acks` table so
they survive restarts; the app selects it when `DATABASE_URL` is set, else the
KV hash store. A full-app boot test confirms the table is created before use.

### Compose
Both replicas receive `DATABASE_URL` and share a `spm-data` volume for the
SQLite ack DB (use Postgres for true multi-writer concurrency).

### Tests
Backend **404 pass** (+13 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 21 — Digest dispatch, Postgres profile, configurable digest, net-active, venue chart

### Digest to a real channel
The digest scheduler now dispatches via the notification service onto a
configurable channel (`BURN_DIGEST_CHANNEL` / `BURN_DIGEST_RECIPIENT`), and
`GET /slo/burn-digest?dispatch=true` sends it on demand (responder+).

### Postgres compose profile
`docker compose --profile pg up` brings up Postgres for true multi-writer
durability; point `DATABASE_URL` at it. A concurrent-writer test exercises the
SQL ack store under `asyncio.gather`.

### Configurable digest
`compose_digest` takes a window and minimum severity; the endpoint and scheduler
honor `BURN_DIGEST_WINDOW_HOURS` / `BURN_DIGEST_MIN_SEVERITY`.

### Net-active trend overlay
Trend buckets carry a cumulative `net_active` (silence − unsilence); the chart
overlays it as a dashed line, with the count in the hover tooltip.

### Burn-by-venue chart
The On-call page shows page/ticket burn as grouped bars per venue, above the
existing table.

### Tests
Backend **409 pass** (+5 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 22 — Digest webhook hop, net-active baseline, per-venue suppression, daily digest

### Digest reaches a real webhook
`WebhookDispatcher.post_message` does a one-shot POST with the same retry/backoff
as event delivery. When `BURN_DIGEST_WEBHOOK_URL` is set, `notify_digest` posts
the message out-of-band and records SENT/FAILED on the notification, so a failed
delivery is visible rather than silent.

### Net-active baseline
The trend now seeds its running net-active silence count from a pre-window
baseline (cumulative silence − unsilence before the window), so silences opened
earlier and still in effect are reflected from the first bucket.

### Per-venue suppression
`/slo/burn-by-venue` carries per-venue ack/silence counts and a suppression
ratio, shown as a column on the On-call venue table.

### Daily digest
A distinct 24h rollup (`compose_daily_digest`, with top burn venues) runs on its
own daily scheduler and channel; preview via `GET /slo/burn-digest?kind=daily`.

### Tests
Backend **415 pass** (+6 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 23 — Slack payload, wall-clock daily digest, delivery history, per-venue routing

### Slack-shaped webhook payload
Digest webhook bodies are now shaped per channel: Slack receives header+section
blocks (with a text fallback); other channels get a generic text body.

### Wall-clock daily digest
The daily digest runs at a configured local time (`BURN_DAILY_DIGEST_AT`, e.g.
09:00) via a wall-clock scheduler, rather than a fixed interval from start.

### Digest delivery history
`/notifications` accepts a `status` filter (SENT/FAILED); the On-call page shows
a digest delivery-history panel with status badges so failed sends are visible.

### Per-venue digest routing
`GET /slo/burn-digest?venue_id=...` composes a venue-scoped digest and, on
dispatch, routes to that venue's channel from `BURN_DIGEST_VENUE_CHANNELS`
(falling back to the default recipient). Venue access is enforced.

### Tests
Backend **422 pass** (+7 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 24 — Per-venue fan-out, TZ-aware daily, per-venue mute, FAILED resend

### Scheduled per-venue fan-out
A `VenueFanoutScheduler` composes each mapped venue's digest and dispatches it to
that venue's channel on an interval, skipping muted venues
(`BURN_DIGEST_VENUE_FANOUT_ENABLED` / `..._INTERVAL_SECONDS`).

### Timezone-aware daily digest
`BURN_DAILY_DIGEST_TZ` (an IANA name) makes the daily wall-clock time fire in a
specific zone rather than the server's local time.

### Per-venue digest mute/snooze
Operators can mute a venue's digest for a window via
`POST /slo/burn-digest/mute` (and `DELETE` to lift early); muted venues are
skipped by both on-demand dispatch and the fan-out scheduler, and the mute state
shows on the On-call venue table with a toggle.

### Re-send failed digests
`POST /notifications/{id}/resend` re-posts a digest via the webhook and updates
its status; the On-call delivery-history panel shows a Resend button on FAILED
rows.

### Tests
Backend **431 pass** (+9 this round). Frontend `tsc -b` + `vite build` green.

---

## Round 25 — Per-venue webhooks, scheduler status, mute audit, test-webhook

### Per-venue webhook URLs
`BURN_DIGEST_VENUE_WEBHOOKS` maps venue → URL; venue-scoped dispatch and the
fan-out scheduler post to the venue's own endpoint, falling back to the global
`BURN_DIGEST_WEBHOOK_URL`.

### Scheduler status
All digest schedulers track last run / status / run count / next run; `GET
/ops/schedulers` (admin) returns them, surfaced as a panel on the On-call page.

### Mute audit history
`GET /slo/burn-digest/mute-events` returns the digest mute/unmute audit trail;
the On-call page shows a mute-history panel.

### Test webhook
`POST /ops/test-webhook` (admin) posts a sample payload to a URL to verify
connectivity; the On-call page has a URL field and Send-test button.

### Tests
Backend **439 pass** (+8 this round). Frontend `tsc -b` + `vite build` green.
