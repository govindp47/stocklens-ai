/**
 * E2E tests for the primary analysis flow.
 *
 * Uses Playwright's page.route() to intercept API calls — no real backend required.
 * All mock responses match the MSW handler shapes from tests/mocks/handlers.ts.
 */

import { test, expect } from "@playwright/test";
import { MOCK_RUN_ID, MOCK_REPORT } from "../mocks/handlers";

// ─── SSE stream helper ────────────────────────────────────────────────────────

function buildSSEBody(): string {
  const steps = [
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "ticker_validation",
      status: "completed",
      step_index: 1,
      timestamp: "2026-03-30T12:00:00Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "market_data_collection",
      status: "completed",
      step_index: 2,
      timestamp: "2026-03-30T12:00:01Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "news_retrieval",
      status: "completed",
      step_index: 3,
      timestamp: "2026-03-30T12:00:02Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "news_deduplication",
      status: "completed",
      step_index: 4,
      timestamp: "2026-03-30T12:00:03Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "article_summarization",
      status: "completed",
      step_index: 5,
      timestamp: "2026-03-30T12:00:04Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "sentiment_classification",
      status: "completed",
      step_index: 6,
      timestamp: "2026-03-30T12:00:05Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "event_extraction",
      status: "completed",
      step_index: 7,
      timestamp: "2026-03-30T12:00:06Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "insight_generation",
      status: "completed",
      step_index: 8,
      timestamp: "2026-03-30T12:00:07Z",
    },
    {
      event_type: "step_event",
      run_id: MOCK_RUN_ID,
      step: "report_assembly",
      status: "completed",
      step_index: 9,
      timestamp: "2026-03-30T12:00:08Z",
    },
  ];
  const completeEvent = {
    event_type: "pipeline_complete",
    run_id: MOCK_RUN_ID,
    timestamp: "2026-03-30T12:00:09Z",
    report: MOCK_REPORT,
    completeness: "complete",
  };

  return (
    steps.map((s) => `data: ${JSON.stringify(s)}\n\n`).join("") +
    `data: ${JSON.stringify(completeEvent)}\n\n`
  );
}

// ─── Route mocking helper ─────────────────────────────────────────────────────

async function mockAPIRoutes(page: import("@playwright/test").Page) {
  // POST /api/v1/analyze
  await page.route("**/api/v1/analyze", (route) => {
    if (route.request().method() === "POST") {
      route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ run_id: MOCK_RUN_ID, status: "accepted" }),
      });
    } else {
      route.continue();
    }
  });

  // GET /api/v1/analyze/stream/:run_id
  await page.route(`**/api/v1/analyze/stream/${MOCK_RUN_ID}`, (route) => {
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: buildSSEBody(),
    });
  });
}

async function runFullAnalysis(
  page: import("@playwright/test").Page,
  ticker: string,
) {
  await mockAPIRoutes(page);
  await page.goto("/");
  await page.fill('[data-testid="ticker-input"]', ticker);
  await page.click('[data-testid="analyze-button"]');
}

// ─── Tests ────────────────────────────────────────────────────────────────────

test.describe("Primary Analysis Flow", () => {
  test("shows inline validation error for invalid ticker", async ({ page }) => {
    await page.goto("/");
    await page.fill('[data-testid="ticker-input"]', "123");
    await page.click('[data-testid="analyze-button"]');

    const alert = page.locator('[role="alert"]');
    await expect(alert).toContainText(/letters/i);

    // No reasoning viewer should appear
    await expect(
      page.locator('section[aria-label="Analysis reasoning steps"]'),
    ).not.toBeVisible();
  });

  test("disclaimer is visible in viewport on initial load", async ({
    page,
  }) => {
    await page.goto("/");
    const disclaimer = page.locator('[data-testid="disclaimer"]');
    await expect(disclaimer).toBeInViewport();
  });

  test("news links open in new tab", async ({ page }) => {
    await runFullAnalysis(page, "AAPL");

    // Wait for the analysis to complete and news panel to populate
    await expect(
      page.locator('[data-testid="news-article-link"]').first(),
    ).toBeVisible({ timeout: 15000 });

    const newsLinks = page.locator('[data-testid="news-article-link"]');
    const count = await newsLinks.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      await expect(newsLinks.nth(i)).toHaveAttribute("target", "_blank");
      await expect(newsLinks.nth(i)).toHaveAttribute("rel", /noopener/);
    }
  });

  test("price direction uses non-color indicator with aria-label", async ({
    page,
  }) => {
    await runFullAnalysis(page, "AAPL");
    const priceDirection = page.locator('[data-testid="price-direction"]');
    await expect(priceDirection).toBeVisible({ timeout: 15000 });
    const label = await priceDirection.getAttribute("aria-label");
    expect(label).toMatch(/up|down|unchanged/i);
  });

  test("panel collapse/expand is keyboard accessible", async ({ page }) => {
    await runFullAnalysis(page, "AAPL");

    // Wait for panels to render
    await expect(
      page.locator('section[aria-labelledby="panel-title-stock_overview"]'),
    ).toBeVisible({ timeout: 15000 });

    const panelToggle = page.locator(
      'section[aria-labelledby="panel-title-stock_overview"] [role="button"]',
    );
    await panelToggle.focus();
    await page.keyboard.press("Enter");

    // Panel content should be hidden
    const content = page.locator("#panel-content-stock_overview");
    await expect(content).toBeHidden();
  });
});
