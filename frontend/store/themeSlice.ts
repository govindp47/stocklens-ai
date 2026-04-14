/**
 * themeSlice — persisted theme preference (light / dark / system).
 *
 * This is a standalone Zustand store with localStorage persistence,
 * intentionally separate from the main combined store to keep persist
 * middleware isolated to only theme state.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "system" | "light" | "dark";

interface ThemeStore {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: "slai-theme",
    },
  ),
);
