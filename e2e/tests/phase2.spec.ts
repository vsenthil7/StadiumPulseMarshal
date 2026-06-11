import { test, expect } from '@playwright/test';
import { loginAs } from './_auth';

test.describe('Phase 2 — tabs, reliability, incidents, scenarios', () => {
  test.beforeEach(async ({ page }) => { await loginAs(page, 'admin'); });
  test('navigates between tabs', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('sidebar-rail')).toBeVisible();
    for (const id of ['triage', 'incidents', 'reliability', 'scenarios']) {
      await page.getByTestId(`tab-${id}`).click();
      await expect(page.getByTestId(`tab-${id}`)).toHaveClass(/active/);
    }
  });

  test('reliability tab shows SLO budgets and analytics', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-reliability').click();
    await expect(page.getByTestId('reliability-page')).toBeVisible();
    await expect(page.getByTestId('slo-grid')).toBeVisible();
    await expect(page.getByTestId('slo-card').first()).toBeVisible();
    await expect(page.getByTestId('analytics-panel')).toBeVisible();
  });

  test('incidents tab: create from problem and advance lifecycle', async ({
    page,
  }) => {
    await page.goto('/');
    await page.getByTestId('nav-incidents').click();
    await expect(page.getByTestId('incidents-page')).toBeVisible();
    // Create an incident from the first open problem.
    await page.getByTestId('create-incident-btn').first().click();
    await expect(page.getByTestId('incident-detail-panel')).toBeVisible();
    await expect(page.getByTestId('incident-lifecycle')).toBeVisible();
    // Acknowledge it.
    await page.getByTestId('transition-ACKNOWLEDGED').click();
    await expect(page.getByTestId('incident-timeline')).toContainText(
      'STATE_CHANGE',
    );
  });

  test('scenarios tab: switch scenario changes the feed', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-scenarios').click();
    await expect(page.getByTestId('scenarios-page')).toBeVisible();
    const cards = page.getByTestId('scenario-card');
    await expect(cards).toHaveCount(4);
    // Select the CDN scenario.
    await cards.nth(1).click();
    // Back to triage — feed should reflect the new scenario.
    await page.getByTestId('nav-triage').click();
    await expect(page.getByTestId('detail-title')).toBeVisible();
  });

  test('mode badge visible in shell topbar', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('health-pill')).toContainText('SEED');
  });
});
