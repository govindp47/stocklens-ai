/**
 * historySlice — persisted list of past analysis runs.
 *
 * Standalone Zustand store with localStorage persistence (key: 'slai-history').
 * Capped at MAX_ENTRIES to prevent unbounded growth.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const MAX_ENTRIES = 50;

export interface HistoryEntry {
  runId: string;
  ticker: string;
  companyName?: string;
  timestamp: string; // ISO 8601
  completeness: "complete" | "partial" | "minimal";
}

interface HistoryStore {
  entries: HistoryEntry[];
  addEntry: (entry: HistoryEntry) => void;
  clearHistory: () => void;
}

export const useHistoryStore = create<HistoryStore>()(
  persist(
    (set) => ({
      entries: [],

      addEntry: (entry) =>
        set((state) => {
          // Remove duplicate run if it already exists (idempotent)
          const filtered = state.entries.filter((e) => e.runId !== entry.runId);
          // Prepend newest first, cap at MAX_ENTRIES
          const next = [entry, ...filtered].slice(0, MAX_ENTRIES);
          return { entries: next };
        }),

      clearHistory: () => set({ entries: [] }),
    }),
    {
      name: "slai-history",
    },
  ),
);
