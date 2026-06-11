import { test, expect } from '@playwright/test';

// Runs across both desktop and mobile projects; the menu button is only
// visible on mobile viewports per the responsive CSS.
test.describe('Responsive / mobile', () => {
  test('mobile shows menu toggle and opens the feed drawer', async ({
    page,
    isMobile,
  }) => {
    await page.goto('/');
    if (isMobile) {
      const menu = page.getByTestId('menu-btn');
      await expect(menu).toBeVisible();
      await menu.click();
      await expect(page.getByTestId('feed')).toHaveClass(/open/);
      // Selecting a problem closes the drawer.
      await page.getByTestId('problem-card').first().click();
      await expect(page.getByTestId('detail-title')).toBeVisible();
    } else {
      // On desktop the feed is always present; menu button hidden.
      await expect(page.getByTestId('feed')).toBeVisible();
    }
  });
});
