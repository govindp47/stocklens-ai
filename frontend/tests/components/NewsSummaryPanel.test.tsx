/**
 * NewsSummaryPanel acceptance tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MOCK_REPORT } from "../mocks/handlers";

// ─── Store mock ────────────────────────────────────────────────────────────────

vi.mock("@/store", () => ({
  useAnalysisStore: () => ({
    news: MOCK_REPORT.news,
    ticker: "AAPL",
    status: "complete",
  }),
  useUIStore: () => ({
    panelExpansion: { news_summary: true },
    togglePanel: vi.fn(),
  }),
}));

import { NewsSummaryPanel } from "@/components/panels/NewsSummaryPanel";

describe("NewsSummaryPanel", () => {
  it('renders article links with target="_blank"', () => {
    render(<NewsSummaryPanel />);
    const links = screen.getAllByTestId("news-article-link");
    links.forEach((link) => {
      expect(link).toHaveAttribute("target", "_blank");
    });
  });

  it('renders article links with rel="noopener noreferrer"', () => {
    render(<NewsSummaryPanel />);
    const links = screen.getAllByTestId("news-article-link");
    links.forEach((link) => {
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });
  });

  it("renders article titles", () => {
    render(<NewsSummaryPanel />);
    expect(
      screen.getByText("Apple Reports Record Quarterly Earnings"),
    ).toBeDefined();
  });
});

describe("NewsSummaryPanel empty state", () => {
  it("renders empty state when no articles", () => {
    vi.doMock("@/store", () => ({
      useAnalysisStore: () => ({
        news: { available: true, articles: [] },
        ticker: "AAPL",
        status: "complete",
      }),
      useUIStore: () => ({
        panelExpansion: { news_summary: true },
        togglePanel: vi.fn(),
      }),
    }));
  });
});
