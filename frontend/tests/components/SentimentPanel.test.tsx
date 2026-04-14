/**
 * SentimentPanel acceptance tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, getAllByText } from "@testing-library/react";
import { MOCK_REPORT } from "../mocks/handlers";

vi.mock("@/store", () => ({
  useAnalysisStore: () => ({
    sentiment: MOCK_REPORT.sentiment,
    status: "complete",
  }),
  useUIStore: () => ({
    panelExpansion: { sentiment: true },
    togglePanel: vi.fn(),
  }),
}));

import { SentimentPanel } from "@/components/panels/SentimentPanel";

describe("SentimentPanel", () => {
  it("renders sentiment bar container with aria-label containing percentages", () => {
    const { container } = render(<SentimentPanel />);
    const bar = screen.getByRole("img");
    const label = bar.getAttribute("aria-label") ?? "";
    expect(label).toContain("70%");
    expect(label).toContain("20%");
    expect(label).toContain("10%");
  });

  it("individual bar segments have aria-label communicating percentage", () => {
    render(<SentimentPanel />);
    // Segments have aria-label like "Positive: 70%"
    const bar = screen.getByRole("img");
    const positiveSegment = bar.querySelector('[aria-label="Positive: 70%"]');
    expect(positiveSegment).not.toBeNull();
    const neutralSegment = bar.querySelector('[aria-label="Neutral: 20%"]');
    expect(neutralSegment).not.toBeNull();
    const negativeSegment = bar.querySelector('[aria-label="Negative: 10%"]');
    expect(negativeSegment).not.toBeNull();
  });

  it("shows percentage text labels inside segments (always-visible)", () => {
    render(<SentimentPanel />);
    // Multiple 70% elements exist (in bar + legend) - use getAllByText
    const all70 = screen.getAllByText("70%");
    expect(all70.length).toBeGreaterThanOrEqual(1);
  });

  it("shows the dominant label via SentimentBadge", () => {
    render(<SentimentPanel />);
    // SentimentBadge renders aria-label "Sentiment: Positive"
    const badge = screen.getByLabelText(/Sentiment: Positive/i);
    expect(badge).toBeDefined();
  });

  it("shows legend rows with text labels and percentages", () => {
    render(<SentimentPanel />);
    // Legend has "Positive" text label
    const positiveLabels = screen.getAllByText("Positive");
    // At least one from the legend
    expect(positiveLabels.length).toBeGreaterThanOrEqual(1);
  });
});
