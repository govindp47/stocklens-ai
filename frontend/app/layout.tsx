import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Disclaimer } from "@/components/ui/Disclaimer";
import "./globals.css";

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
    <html lang="en" className={`${inter.variable} ${jetBrainsMono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        {/* Skip navigation for keyboard / screen-reader users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow"
        >
          Skip to main content
        </a>

        <Disclaimer />

        <main id="main-content" aria-label="main content">
          {children}
        </main>
      </body>
    </html>
  );
}
