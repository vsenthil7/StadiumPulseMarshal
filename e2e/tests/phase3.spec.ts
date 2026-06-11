import { test, expect } from '@playwright/test';
import { loginAs } from './_auth';

test.describe('Phase 3 — webhooks, trends, postmortem, live, toasts', () => {
  test.beforeEach(async ({ page }) => { await loginAs(page, 'admin'); });
  test('webhooks tab: register and delete a webhook', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-webhooks').click();
    await expect(page.getByTestId('webhooks-page')).toBeVisible();
    await page.getByTestId('webhook-url').fill('http://example.test/hook');
    await page.getByTestId('webhook-create').click();
    await expect(page.getByTestId('webhook-row')).toHaveCount(1);
    // a toast confirms success
    await expect(page.getByTestId('toast').first()).toBeVisible();
    await page.getByTestId('webhook-delete').first().click();
    await expect(page.getByTestId('webhook-row')).toHaveCount(0);
  });

  test('reliability tab shows SLO trend rows', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-reliability').click();
    await expect(page.getByTestId('slo-trends')).toBeVisible();
    await expect(page.getByTestId('trend-row').first()).toBeVisible();
  });

  test('incident postmortem generation', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-incidents').click();
    await page.getByTestId('create-incident-btn').first().click();
    await expect(page.getByTestId('incident-lifecycle')).toBeVisible();
    await page.getByTestId('transition-ACKNOWLEDGED').click();
    await page.getByTestId('transition-RESOLVED').click();
    await page.getByTestId('postmortem-btn').click();
    await expect(page.getByTestId('postmortem')).toContainText('Postmortem');
  });

  test('live indicator present in topbar', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('live-indicator')).toBeVisible();
  });
});
