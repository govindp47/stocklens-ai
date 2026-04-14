/**
 * settingsSlice — in-memory API key, model settings, and provider selection.
 *
 * IMPORTANT: No persist middleware is used. The openAiKey is intentionally
 * stored in memory only and is NEVER written to localStorage, sessionStorage,
 * cookies, or any other persistent browser storage.
 */

import type { StateCreator } from "zustand";
import type { StoreState } from "./index";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ModelProvider =
  | "ollama"
  | "openai"
  | "nvidia-llama"
  | "nvidia-mistral"
  | "nvidia-deepseek";

// ─── State shape ─────────────────────────────────────────────────────────────

export interface SettingsState {
  /** OpenAI API key — in memory only, never persisted. */
  openAiKey: string;
  openAiKeyStatus: "unset" | "set" | "invalid";
  /** LLM model identifier, e.g. "mistral:7b-instruct" or "gpt-4o-mini". */
  activeModel: string;
  /** Selected provider: 'ollama' (default, local/free) or 'openai'. */
  selectedProvider: ModelProvider;

  setOpenAiKey: (key: string) => void;
  clearOpenAiKey: () => void;
  markKeyInvalid: () => void;
  setProvider: (provider: ModelProvider) => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initialSettingsState = {
  openAiKey: "",
  openAiKeyStatus: "unset" as const,
  activeModel: "meta/llama-3.1-8b-instruct",
  selectedProvider: "nvidia-llama" as ModelProvider,
};

// ─── Slice factory ────────────────────────────────────────────────────────────

export const createSettingsSlice: StateCreator<
  StoreState,
  [],
  [],
  SettingsState
> = (set) => ({
  ...initialSettingsState,

  /**
   * Stores the API key in Zustand in-memory state only.
   * No localStorage write is performed here or anywhere in this slice.
   */
  setOpenAiKey: (key: string) =>
    set({
      openAiKey: key,
      openAiKeyStatus: key.trim().length > 0 ? "set" : "unset",
    }),

  clearOpenAiKey: () =>
    set({
      openAiKey: "",
      openAiKeyStatus: "unset",
    }),

  markKeyInvalid: () =>
    set({
      openAiKeyStatus: "invalid",
    }),

  setProvider: (provider: ModelProvider) =>
    set(() => {
      // Ollama reset
      if (provider === "ollama") {
        return {
          selectedProvider: "ollama",
          openAiKey: "",
          openAiKeyStatus: "unset" as const,
          activeModel: "mistral:7b-instruct",
        };
      }

      // OpenAI
      if (provider === "openai") {
        return {
          selectedProvider: "openai",
          activeModel: "gpt-4o-mini",
        };
      }

      // NVIDIA providers
      if (provider === "nvidia-llama") {
        return {
          selectedProvider: "nvidia-llama",
          openAiKey: "",
          openAiKeyStatus: "unset" as const,
          activeModel: "meta/llama-3.1-8b-instruct",
        };
      }

      if (provider === "nvidia-mistral") {
        return {
          selectedProvider: "nvidia-mistral",
          openAiKey: "",
          openAiKeyStatus: "unset" as const,
          activeModel: "mistralai/mistral-7b-instruct-v0.3",
        };
      }

      if (provider === "nvidia-deepseek") {
        return {
          selectedProvider: "nvidia-deepseek",
          openAiKey: "",
          openAiKeyStatus: "unset" as const,
          activeModel: "deepseek-ai/deepseek-r1-distill-llama-8b",
        };
      }

      return {};
    }),
});
