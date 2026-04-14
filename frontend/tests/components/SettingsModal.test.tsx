/**
 * SettingsModal acceptance tests.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/store", () => ({
  useSettingsStore: () => ({
    openAiKeyStatus: "unset",
    setOpenAiKey: vi.fn(),
    clearOpenAiKey: vi.fn(),
  }),
}));

import { SettingsModal } from "@/components/settings/SettingsModal";

async function openModal() {
  const user = userEvent.setup();
  render(<SettingsModal />);
  await user.click(screen.getByTestId("settings-button"));
  return user;
}

describe("SettingsModal", () => {
  it('key input has type="password"', async () => {
    await openModal();
    const input = screen.getByTestId("openai-key-input");
    expect(input).toHaveAttribute("type", "password");
  });

  it('key input has autoComplete="off"', async () => {
    await openModal();
    const input = screen.getByTestId("openai-key-input");
    expect(input).toHaveAttribute("autoComplete", "off");
  });

  it("input is not pre-populated", async () => {
    await openModal();
    const input = screen.getByTestId("openai-key-input") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("save button is disabled when input is empty", async () => {
    await openModal();
    const saveBtn = screen.getByTestId("save-key-button");
    expect(saveBtn).toBeDisabled();
  });
});
