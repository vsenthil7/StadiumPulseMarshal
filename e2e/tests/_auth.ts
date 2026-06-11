// Shared sign-in helper for e2e. The console now gates on a demo-seed login, so
// tests authenticate first. Offline (no backend) the seed lane authenticates
// in-browser; against a live backend the same call mints a JWT.
//
// NOTE: execution needs the built console served (npm run preview) + browsers.
// Browsers can't be downloaded in the build sandbox → these run in CI.
import { type Page, expect } from '@playwright/test';

export const DEMO_PASSWORD = 'MatchdayDemo123!';

export async function loginAs(page: Page, role: string, venue = 'arena-north') {
  await page.goto('/');
  // The login page is shown when unauthenticated.
  await expect(page.getByTestId('login-submit')).toBeVisible();
  await page.getByTestId(`quickfill-${role}`).first().click();
  await page.getByTestId('login-submit').click();
  // Shell renders once authenticated.
  await expect(page.getByTestId('sidebar-rail')).toBeVisible();
}
