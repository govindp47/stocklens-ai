"use client";

/**
 * ThemeProvider — applies dark/light class to <html> based on persisted preference.
 *
 * - 'dark'   → adds class="dark" to <html>
 * - 'light'  → adds class="light" to <html> (overrides system prefers-color-scheme)
 * - 'system' → removes both classes, falls back to CSS @media prefers-color-scheme
 */

import { useEffect } from "react";
import { useThemeStore } from "@/store/themeSlice";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { theme } = useThemeStore();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("dark", "light");
    if (theme === "dark" || theme === "light") {
      root.classList.add(theme);
    }
  }, [theme]);

  return <>{children}</>;
}
