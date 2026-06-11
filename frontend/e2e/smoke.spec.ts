import { test, expect } from "@playwright/test";

test("health endpoint returns ok", async ({ request }) => {
  const resp = await request.get("/api/v1/health");
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  expect(body.status).toBe("ok");
});

test("frontend loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).not.toBeEmpty();
});

test("problems endpoint returns array", async ({ request }) => {
  const resp = await request.get("/api/v1/problems");
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  expect(Array.isArray(body.problems ?? body)).toBe(true);
});
