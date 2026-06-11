import { test, expect } from '@playwright/test';

test.describe('StadiumPulse Marshal — matchday console', () => {
  test('loads console and shows live problem feed', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.brand')).toContainText('StadiumPulse Marshal');
    await expect(page.getByTestId('mode-badge')).toContainText('MOCK');
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

  test('change operator identity', async ({ page }) => {
    await page.goto('/');
    const op = page.getByTestId('operator-input');
    await op.fill('sre-marshal-lead');
    await expect(op).toHaveValue('sre-marshal-lead');
  });

  test('select a different problem from the feed', async ({ page }) => {
    await page.goto('/');
    const cards = page.getByTestId('problem-card');
    await cards.nth(1).click();
    await expect(page.getByTestId('detail-title')).toBeVisible();
  });
});
