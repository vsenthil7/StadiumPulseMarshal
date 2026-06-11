import { test, expect } from '@playwright/test';
import { loginAs } from './_auth';

test.describe('StadiumPulse Marshal — matchday console', () => {
  test.beforeEach(async ({ page }) => { await loginAs(page, 'admin'); });
  test('loads console and shows live problem feed', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.brand')).toContainText('StadiumPulse Marshal');
    await expect(page.getByTestId('health-pill')).toContainText('SEED');
    // Open count badge shows 2 open problems from the fixture scenario.
    await expect(page.getByTestId('open-count')).toHaveText('2');
    const cards = page.getByTestId('problem-card');
    await expect(cards).toHaveCount(3);
  });

  test('triages a problem: root cause, agent analysis, remediations', async ({
    page,
  }) => {
    await page.goto('/');
    // First open problem auto-selected; detail title visible.
    await expect(page.getByTestId('detail-title')).toBeVisible();

    // Root-cause tree flags the database.
    await expect(page.locator('.rc-card.root')).toContainText('payments-postgres');

    // Agent analysis renders with confidence.
    await expect(page.getByTestId('agent-panel')).toContainText('confidence');

    // Remediation recommendations appear.
    const rems = page.getByTestId('remediation');
    await expect(rems.first()).toBeVisible();
    await expect(rems).toHaveCount(2);
  });

  test('approve and apply a remediation (human-in-the-loop)', async ({ page }) => {
    await page.goto('/');
    const firstRem = page.getByTestId('remediation').first();
    await firstRem.getByTestId('decision-reason').fill('surge confirmed on East kiosks');
    await firstRem.getByTestId('approve-btn').click();

    // After approval an Apply button appears.
    await expect(firstRem.getByTestId('execute-btn')).toBeVisible();
    await firstRem.getByTestId('execute-btn').click();
    await expect(firstRem.getByTestId('decided-status')).toContainText(
      'Runbook applied',
    );

    // Audit log records the decision.
    await expect(page.getByTestId('audit-panel')).toContainText('jane');
  });

  test('reject a remediation', async ({ page }) => {
    await page.goto('/');
    const rems = page.getByTestId('remediation');
    const second = rems.nth(1);
    await second.getByTestId('reject-btn').click();
    await expect(second.getByTestId('decided-status')).toContainText(
      'REJECTED',
    );
  });

  test('toggle auto-approve guardrail', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByTestId('auto-approve-toggle');
    await expect(toggle).toBeVisible();
    await toggle.check();
    await expect(toggle).toBeChecked();
  });

  test('operator identity comes from the signed-in session', async ({ page }) => {
    await page.goto('/');
    // Identity is now the authenticated user (set at login), shown in the
    // user menu role badge rather than a free-text field.
    await expect(page.getByTestId('role-badge')).toBeVisible();
  });

  test('select a different problem from the feed', async ({ page }) => {
    await page.goto('/');
    const cards = page.getByTestId('problem-card');
    await cards.nth(1).click();
    await expect(page.getByTestId('detail-title')).toBeVisible();
  });
});
