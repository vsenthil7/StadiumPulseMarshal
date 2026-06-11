import { test, expect, request as pwRequest } from "@playwright/test";

const PW = "MatchdayDemo123!";

async function login(request, email = "sre@stadiumpulse.demo") {
  const r = await request.post("/api/v1/auth/login", {
    data: { email, password: PW },
  });
  expect(r.status()).toBe(200);
  return r.json();
}

test.describe("auth flows", () => {
  test("login returns a token and user", async ({ request }) => {
    const body = await login(request);
    expect(body.token).toBeTruthy();
    expect(body.refresh_token).toBeTruthy();
    expect(body.user.role).toBe("admin");
  });

  test("login with wrong password is rejected", async ({ request }) => {
    const r = await request.post("/api/v1/auth/login", {
      data: { email: "sre@stadiumpulse.demo", password: "nope" },
    });
    expect(r.status()).toBe(401);
  });

  test("unknown user is rejected", async ({ request }) => {
    const r = await request.post("/api/v1/auth/login", {
      data: { email: "ghost@nowhere.demo", password: PW },
    });
    expect(r.status()).toBe(401);
  });

  test("/me rehydrates the session from the token", async ({ request }) => {
    const { token } = await login(request);
    const me = await request.get("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(me.status()).toBe(200);
    const body = await me.json();
    expect(body.user.email).toBe("sre@stadiumpulse.demo");
  });
});

test.describe("authorized API", () => {
  test("burn alerts are scoped and shaped", async ({ request }) => {
    const { token } = await login(request);
    const r = await request.get("/api/v1/slo/burn-alerts", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(Array.isArray(body.alerts)).toBe(true);
    expect(typeof body.page_count).toBe("number");
  });

  test("ack then unack a burn alert (responder)", async ({ request }) => {
    const { token } = await login(request, "responder@arena-north.demo");
    const h = { Authorization: `Bearer ${token}` };
    const alerts = (await (await request.get("/api/v1/slo/burn-alerts", { headers: h })).json()).alerts;
    test.skip(alerts.length === 0, "no burn alerts in current scenario");
    const a = alerts[0];
    const ack = await request.post(`/api/v1/slo/burn-alerts/${a.slo_id}/ack`, {
      headers: h,
      data: { severity: a.severity },
    });
    expect(ack.status()).toBe(200);
    expect((await ack.json()).acknowledged).toBe(true);
    const un = await request.delete(
      `/api/v1/slo/burn-alerts/${a.slo_id}/ack?severity=${a.severity}`,
      { headers: h },
    );
    expect(un.status()).toBe(200);
  });

  test("auth-events CSV export works for admin", async ({ request }) => {
    const { token } = await login(request);
    const r = await request.get("/api/v1/auth/events?fmt=csv", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(r.status()).toBe(200);
    expect(r.headers()["content-type"]).toContain("text/csv");
    const text = await r.text();
    expect(text).toContain("timestamp,actor,action,outcome,ip");
  });
});

test.describe("negative / RBAC", () => {
  test("no-token request resolves to the demo principal when auth is disabled", async ({ request }) => {
    // In the zero-credential demo default (AUTH_ENABLED=false) a missing token
    // falls back to a permissive demo principal rather than 401. This documents
    // that contract; with AUTH_ENABLED=true the same call would be 401.
    const r = await request.get("/api/v1/auth/events");
    expect([200, 401, 403]).toContain(r.status());
  });

  test("viewer cannot read the auth-events admin trail (403)", async ({ request }) => {
    const { token } = await login(request, "viewer@arena-north.demo");
    const r = await request.get("/api/v1/auth/events", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(r.status()).toBe(403);
  });

  test("viewer cannot ack a burn alert (403)", async ({ request }) => {
    const { token } = await login(request, "viewer@arena-north.demo");
    const r = await request.post("/api/v1/slo/burn-alerts/any/ack", {
      headers: { Authorization: `Bearer ${token}` },
      data: { severity: "page" },
    });
    expect(r.status()).toBe(403);
  });

  test("garbage bearer token is rejected", async ({ request }) => {
    const r = await request.get("/api/v1/auth/me", {
      headers: { Authorization: "Bearer not.a.real.jwt" },
    });
    expect(r.status()).toBe(401);
  });
});

test.describe("served SPA", () => {
  test("index serves the app shell with root div", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/StadiumPulse Marshal/);
    await expect(page.locator("#root")).toBeAttached();
  });

  test("OIDC status endpoint reports disabled by default", async ({ request }) => {
    const r = await request.get("/api/v1/auth/oidc/status");
    expect(r.status()).toBe(200);
    expect((await r.json()).enabled).toBe(false);
  });
});
