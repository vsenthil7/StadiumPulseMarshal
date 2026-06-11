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
