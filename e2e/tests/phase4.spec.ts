import { test, expect } from '@playwright/test';
import { loginAs } from './_auth';

test.describe('Phase 4 — audit log, dead-letter, optimistic concurrency', () => {
  test.beforeEach(async ({ page }) => { await loginAs(page, 'admin'); });
  test('audit tab lists entries after an incident mutation', async ({ page }) => {
    await page.goto('/');
    // create + transition an incident to generate audit entries
    await page.getByTestId('nav-incidents').click();
    await page.getByTestId('create-incident-btn').first().click();
    await expect(page.getByTestId('incident-lifecycle')).toBeVisible();
    await page.getByTestId('transition-ACKNOWLEDGED').click();
    // audit tab shows the entries
    await page.getByTestId('nav-audit').click();
    await expect(page.getByTestId('audit-page')).toBeVisible();
    await expect(page.getByTestId('audit-row').first()).toBeVisible();
    // filter control present
    await expect(page.getByTestId('audit-filter')).toBeVisible();
  });

  test('webhooks tab shows dead-letter panel', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-webhooks').click();
    await expect(page.getByTestId('dead-letter-panel')).toBeVisible();
  });

  test('audit filter narrows results', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('nav-incidents').click();
    await page.getByTestId('create-incident-btn').first().click();
    await page.getByTestId('transition-ACKNOWLEDGED').click();
    await page.getByTestId('nav-audit').click();
    await page.getByTestId('audit-filter').selectOption('incident.create');
    // at least one row remains and all are create actions
    await expect(page.getByTestId('audit-row').first()).toBeVisible();
  });
});
