import { test, expect } from '@playwright/test';
import { loginAs } from './_auth';

test.describe('Auth, roles, venues, sidebar', () => {
  test('login gate is shown when unauthenticated', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('login-submit')).toBeVisible();
    await expect(page.getByTestId('login-email')).toBeVisible();
  });

  test('operator sees grouped sidebar with Operations + Reliability', async ({ page }) => {
    await loginAs(page, 'operator');
    await expect(page.getByTestId('nav-group-Operations')).toBeVisible();
    await expect(page.getByTestId('nav-group-Reliability')).toBeVisible();
    // operator can see Scenarios (operator+), not Webhooks (admin only)
    await expect(page.getByTestId('nav-scenarios')).toBeVisible();
    await expect(page.getByTestId('nav-webhooks')).toHaveCount(0);
  });

  test('viewer cannot see operator/admin nav', async ({ page }) => {
    await loginAs(page, 'viewer');
    await expect(page.getByTestId('nav-triage')).toBeVisible();
    await expect(page.getByTestId('nav-scenarios')).toHaveCount(0); // operator+
    await expect(page.getByTestId('nav-webhooks')).toHaveCount(0);  // admin
  });

  test('admin sees Administration group incl. Webhooks + Health', async ({ page }) => {
    await loginAs(page, 'admin');
    await expect(page.getByTestId('nav-group-Administration')).toBeVisible();
    await expect(page.getByTestId('nav-webhooks')).toBeVisible();
    await expect(page.getByTestId('nav-health')).toBeVisible();
  });

  test('sidebar collapses and expands', async ({ page }) => {
    await loginAs(page, 'admin');
    const rail = page.getByTestId('sidebar-rail');
    await expect(rail).toHaveAttribute('data-collapsed', 'false');
    await page.getByTestId('sidebar-toggle').click();
    await expect(rail).toHaveAttribute('data-collapsed', 'true');
  });

  test('venue switcher present for multi-venue admin', async ({ page }) => {
    await loginAs(page, 'admin');
    await expect(page.getByTestId('venue-switcher')).toBeVisible();
    await page.getByTestId('venue-switcher').click();
    await expect(page.getByTestId('venue-menu')).toBeVisible();
  });

  test('health page renders system status', async ({ page }) => {
    await loginAs(page, 'admin');
    await page.getByTestId('nav-health').click();
    await expect(page.getByTestId('health-page')).toBeVisible();
    await expect(page.getByTestId('coverage-table')).toBeVisible();
  });

  test('logout returns to the login gate', async ({ page }) => {
    await loginAs(page, 'operator');
    await page.getByTestId('user-menu').click();
    await page.getByTestId('logout').click();
    await expect(page.getByTestId('login-submit')).toBeVisible();
  });
});

test.describe('Permission-gated actions (UI matches backend RBAC)', () => {
  test('viewer sees read-only remediations, no approve button', async ({ page }) => {
    await loginAs(page, 'viewer');
    await page.getByTestId('nav-triage').click();
    // A viewer must never see approve/reject affordances.
    await expect(page.getByTestId('approve-btn')).toHaveCount(0);
    await expect(page.getByTestId('reject-btn')).toHaveCount(0);
    // Read-only note is shown instead where a pending remediation exists.
    // (Tolerant: only assert if a remediation is present.)
    const rems = page.getByTestId('remediation');
    if (await rems.count()) {
      await expect(page.getByTestId('rem-readonly').first()).toBeVisible();
    }
  });

  test('responder sees approve/reject on a pending remediation', async ({ page }) => {
    await loginAs(page, 'responder');
    await page.getByTestId('nav-triage').click();
    const rems = page.getByTestId('remediation');
    if (await rems.count()) {
      await expect(page.getByTestId('approve-btn').first()).toBeVisible();
    }
  });

  test('viewer cannot toggle auto-approve (disabled)', async ({ page }) => {
    await loginAs(page, 'viewer');
    await page.getByTestId('nav-triage').click();
    await expect(page.getByTestId('auto-approve-toggle')).toBeDisabled();
  });

  test('viewer on Incidents sees view-only, no create button', async ({ page }) => {
    await loginAs(page, 'viewer');
    await page.getByTestId('nav-incidents').click();
    await expect(page.getByTestId('create-incident-btn')).toHaveCount(0);
  });
});
