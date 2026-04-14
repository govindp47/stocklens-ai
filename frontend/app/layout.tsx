import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { HeaderNav } from "@/components/layout/HeaderNav";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "StockLens AI",
  description:
    "AI-powered stock analysis: market data, news sentiment, events, and insights — all in one view.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetBrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen flex flex-col font-sans antialiased bg-background text-foreground">
        <ThemeProvider>
          {/* Skip navigation for keyboard / screen-reader users */}
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-card focus:ring-2 focus:ring-brand-500"
          >
            Skip to main content
          </a>

          {/* ── Top navigation bar ─────────────────────────────────────────── */}
          <header className="sticky top-0 z-30 border-b border-border/60 bg-surface/90 backdrop-blur-md">
            <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
              {/* Logo + wordmark */}
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-500 shadow-xs ring-1 ring-brand-600/20">
                  <svg
                    viewBox="0 0 20 20"
                    fill="none"
                    className="h-4.5 w-4.5 text-white"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 13l4-5 3 4 3-6 4 7"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold tracking-tight text-foreground">
                    StockLens
                  </span>
                  <span className="hidden text-sm font-bold tracking-tight text-brand-500 sm:inline">
                    AI
                  </span>
                  <span className="hidden rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-600 ring-1 ring-brand-200/60 sm:inline-flex">
                    Beta
                  </span>
                </div>
              </div>

              {/* Navigation + theme toggle */}
              <HeaderNav />
            </div>
          </header>

          <main id="main-content" aria-label="main content" className="flex-1">
            {children}
          </main>

          {/* ── Footer ───────────────────────────────────────────── */}
          <footer className="mt-16 border-t border-border/60 bg-surface/60 py-6 px-4 sm:px-6">
            <div className="mx-auto max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-muted-foreground">
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-3.5 w-3.5 text-brand-500/70"
                  aria-hidden="true"
                >
                  <path
                    d="M3 13l4-5 3 4 3-6 4 7"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="text-xs font-medium text-muted-foreground">
                  StockLens AI
                </span>
              </div>
              <p className="text-center text-[11px] text-muted-foreground/80 leading-relaxed max-w-lg">
                For informational purposes only. Not financial advice. Market
                data may be delayed. Always conduct your own research before
                making investment decisions.
              </p>
            </div>
          </footer>
        </ThemeProvider>
      </body>
    </html>
  );
}
