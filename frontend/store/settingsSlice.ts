/**
 * settingsSlice — in-memory API key and model settings.
 *
 * IMPORTANT: No persist middleware is used. The openAiKey is intentionally
 * stored in memory only and is NEVER written to localStorage, sessionStorage,
 * cookies, or any other persistent browser storage.
 */

import type { StateCreator } from 'zustand';
import type { StoreState } from './index';

// ─── State shape ─────────────────────────────────────────────────────────────

export interface SettingsState {
  /** OpenAI API key — in memory only, never persisted. */
  openAiKey: string;
  openAiKeyStatus: 'unset' | 'set' | 'invalid';
  /** LLM model identifier, e.g. "mistral:7b-instruct" or "gpt-4o-mini". */
  activeModel: string;

  setOpenAiKey: (key: string) => void;
  clearOpenAiKey: () => void;
  markKeyInvalid: () => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initialSettingsState = {
  openAiKey: '',
  openAiKeyStatus: 'unset' as const,
  activeModel: 'mistral:7b-instruct',
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
      openAiKeyStatus: key.trim().length > 0 ? 'set' : 'unset',
    }),

  clearOpenAiKey: () =>
    set({
      openAiKey: '',
      openAiKeyStatus: 'unset',
    }),

  markKeyInvalid: () =>
    set({
      openAiKeyStatus: 'invalid',
    }),
});
