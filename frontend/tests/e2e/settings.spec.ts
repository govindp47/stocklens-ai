/**
 * E2E tests for the Settings modal.
 */

import { test, expect } from '@playwright/test';

test.describe('Settings Modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('OpenAI key input has type="password"', async ({ page }) => {
    await page.click('[data-testid="settings-button"]');
    const keyInput = page.locator('[data-testid="openai-key-input"]');
    await expect(keyInput).toBeVisible();
    await expect(keyInput).toHaveAttribute('type', 'password');
  });

  test('key input has autoComplete="off"', async ({ page }) => {
    await page.click('[data-testid="settings-button"]');
    const keyInput = page.locator('[data-testid="openai-key-input"]');
    await expect(keyInput).toHaveAttribute('autocomplete', 'off');
  });

  test('key is not stored in localStorage after save', async ({ page }) => {
    await page.click('[data-testid="settings-button"]');
    await page.fill('[data-testid="openai-key-input"]', 'sk-test-key-12345');
    await page.click('[data-testid="save-key-button"]');

    // Wait for modal to close
    await expect(page.locator('[data-testid="openai-key-input"]')).not.toBeVisible();

    const localStorageContent = await page.evaluate(() =>
      JSON.stringify(window.localStorage),
    );
    expect(localStorageContent).not.toContain('sk-test');
    expect(localStorageContent).not.toContain('openai');
    expect(localStorageContent).not.toContain('OpenAi');
  });

  test('key is cleared after page refresh (session-only)', async ({ page }) => {
    await page.click('[data-testid="settings-button"]');
    await page.fill('[data-testid="openai-key-input"]', 'sk-test-key-12345');
    await page.click('[data-testid="save-key-button"]');

    // Reload the page
    await page.reload();

    // After reload, the Zustand store resets — openAiKeyStatus should be 'unset'
    // Verify by opening settings again and checking no "key active" message
    await page.click('[data-testid="settings-button"]');
    await expect(page.locator('text=✓ API key is active for this session')).not.toBeVisible();
  });
});
