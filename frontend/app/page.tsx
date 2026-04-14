"use client";

import { useAnalysisStore } from "@/store";
import { TickerInput } from "@/components/playground/TickerInput";
import { AnalysisProgress } from "@/components/playground/AnalysisProgress";
import { ModelSelector } from "@/components/playground/ModelSelector";
import { GlobalFailureBanner } from "@/components/ui/GlobalFailureBanner";
import { ReportReadyCard } from "@/components/playground/ReportReadyCard";
import { TrendingUp, Zap, BarChart2, ShieldCheck } from "lucide-react";

// ─── Feature pill data ────────────────────────────────────────────────────────

const FEATURES = [
  { icon: TrendingUp, label: "Live market data" },
  { icon: BarChart2, label: "Sentiment analysis" },
  { icon: Zap, label: "AI-generated insights" },
  { icon: ShieldCheck, label: "Multi-source validation" },
];

// ─── Hero / empty state ───────────────────────────────────────────────────────

function HeroSection() {
  return (
    <div className="flex flex-col items-center gap-4 pt-10 pb-2 text-center">
      {/* Logo mark (decorative, large) */}
      <div className="relative">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-500 shadow-lg ring-4 ring-brand-500/10 animate-float">
          <svg
            viewBox="0 0 20 20"
            fill="none"
            className="h-8 w-8 text-white"
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
        {/* Glow pulse */}
        <div
          className="absolute inset-0 -z-10 rounded-2xl bg-brand-500 opacity-20 blur-xl"
          aria-hidden="true"
        />
      </div>

      {/* Headline */}
      <div className="flex flex-col items-center gap-4">
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-foreground leading-[1.1]">
          Instant AI <span className="text-brand-500">Stock Research</span>
        </h1>
        <p className="max-w-sm sm:max-w-md text-base text-muted-foreground leading-relaxed">
          Market data, news analysis, sentiment scoring, and AI-generated
          insights — all in seconds.
        </p>
      </div>

      {/* Feature pills */}
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        {FEATURES.map(({ icon: Icon, label }) => (
          <span
            key={label}
            className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-2 py-0.5 text-2xs font-medium text-muted-foreground shadow-xs transition-colors hover:border-brand-200 hover:text-foreground"
          >
            <Icon className="h-3 w-3 text-brand-500" aria-hidden="true" />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlaygroundPage() {
  const { status } = useAnalysisStore();
  const isActive = status !== "idle";

  return (
    <div className="mx-auto flex max-w-6xl flex-col items-center px-4 sm:px-6 py-2 gap-6">
      {/* Hero — only shown when idle */}
      {!isActive && <HeroSection />}

      {/* ── Search bar area ──────────────────────────────────────────────── */}
      <div
        className={`w-full max-w-md flex flex-col items-center gap-3 transition-all duration-300 ${isActive ? "mt-0" : ""}`}
      >
        <div className="w-full flex items-center justify-end">
          <ModelSelector />
        </div>
        <TickerInput />
      </div>

      {/* ── Active analysis area ─────────────────────────────────────────── */}
      {isActive && (
        <div className="w-full max-w-md flex flex-col gap-3 animate-fade-in-up">
          <AnalysisProgress />
          <GlobalFailureBanner />
          {status === "complete" && <ReportReadyCard />}
        </div>
      )}
    </div>
  );
}
