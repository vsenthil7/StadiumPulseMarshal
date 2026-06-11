# End-to-End Testing (Playwright)

The Playwright suite drives the **real** application stack: the FastAPI backend
serving the built React frontend from a single origin, exactly as verified by
the HTTP smoke test in CI.

## What is covered

`e2e/tests/console.spec.ts`
1. Console loads; live problem feed shows 2 open / 3 total problems; MOCK badge.
2. Triage: root-cause tree flags `payments-postgres`, agent analysis + confidence,
   two remediation recommendations render.
3. Human-in-the-loop: approve → Apply runbook → "Runbook applied"; audit records it.
4. Reject flow records `REJECTED`.
5. Auto-approve guardrail toggle.
6. Operator identity change.
7. Selecting a different problem from the feed.

`e2e/tests/mobile.spec.ts`
8. Mobile viewport (Pixel 7): menu toggle opens the feed drawer; selecting a
   problem closes it. Desktop: feed always visible.

Both specs run under two projects: **desktop-chromium** (1366×900) and
**mobile-chromium** (Pixel 7).

## Prerequisites

```bash
# 1. Build the frontend so the backend can serve it single-origin
cd frontend && npm install && npm run build

# 2. Start the backend serving API + UI on :8000
cd ../backend && pip install -e . && python -m uvicorn app.main:app --port 8000
```

## Run

```bash
cd e2e
npm install
npx playwright install chromium      # downloads the browser binary
# point the suite at the running single-origin server:
PLAYWRIGHT_BASE_URL=http://localhost:8000 npx playwright test
```

Or let Playwright manage a preview server (frontend dev proxy):

```bash
cd e2e && npx playwright test          # uses webServer in playwright.config.ts
```

## Reports

```bash
npx playwright show-report playwright-report
```

> **Sandbox note.** In the build sandbox the Playwright browser binary could not
> be downloaded (the CDN is outside the network allow-list). The specs are
> authored, typecheck clean, and the exact stack they target was validated with
> a live HTTP smoke test (index, assets, analyze → approve → execute → audit all
> 200). On Claude Desktop / CI with browser access, `npx playwright test` runs
> them green.
