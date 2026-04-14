/**
 * InsightPanel acceptance tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MOCK_REPORT } from "../mocks/handlers";

vi.mock("@/store", () => ({
  useAnalysisStore: () => ({
    insights: MOCK_REPORT.insights,
    status: "complete",
  }),
  useUIStore: () => ({
    panelExpansion: { insights: true },
    togglePanel: vi.fn(),
  }),
}));

import { InsightPanel } from "@/components/panels/InsightPanel";

describe("InsightPanel", () => {
  it("renders all six insight sections", () => {
    render(<InsightPanel />);
    expect(screen.getByText("Company Overview")).toBeDefined();
    expect(screen.getByText("Recent Developments")).toBeDefined();
    expect(screen.getByText("Sentiment Overview")).toBeDefined();
    expect(screen.getByText("Potential Drivers")).toBeDefined();
    expect(screen.getByText("Potential Risks")).toBeDefined();
    expect(screen.getByText("AI Summary")).toBeDefined();
  });

  it('renders the disclaimer with role="note"', () => {
    render(<InsightPanel />);
    const disclaimer = screen.getByTestId("insight-disclaimer");
    expect(disclaimer).toBeDefined();
    expect(disclaimer.getAttribute("role")).toBe("note");
  });

  it("disclaimer is visible", () => {
    render(<InsightPanel />);
    const disclaimer = screen.getByTestId("insight-disclaimer");
    expect(disclaimer.textContent).toContain("AI-generated analysis");
  });
});
