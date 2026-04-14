/**
 * TickerInput unit tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ─── Mock the store and analysis hook ─────────────────────────────────────────

vi.mock("@/store", () => ({
  useAnalysisStore: () => ({
    status: "idle",
  }),
  useSettingsStore: () => ({
    openAiKey: "",
    openAiKeyStatus: "unset",
  }),
}));

vi.mock("@/hooks/useAnalysis", () => ({
  useAnalysis: () => ({
    analyze: vi.fn(),
  }),
}));

// Import after mocks
import { TickerInput } from "@/components/playground/TickerInput";

describe("TickerInput", () => {
  it("auto-uppercases typed input", async () => {
    const user = userEvent.setup();
    render(<TickerInput />);
    const input = screen.getByRole("textbox");
    await user.type(input, "aapl");
    expect(input).toHaveValue("AAPL");
  });

  it("shows inline error on empty submission", async () => {
    const user = userEvent.setup();
    render(<TickerInput />);
    const btn = screen.getByRole("button", { name: /analyze/i });
    await user.click(btn);
    expect(screen.getByRole("alert")).toBeDefined();
  });

  it("shows inline error for invalid characters", async () => {
    const user = userEvent.setup();
    render(<TickerInput />);
    const input = screen.getByRole("textbox");
    await user.type(input, "1234");
    const btn = screen.getByRole("button", { name: /analyze/i });
    await user.click(btn);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/letters/i);
  });
});
