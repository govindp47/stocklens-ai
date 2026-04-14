"use client";

/**
 * TickerInput — ticker symbol input with:
 * - Auto-uppercase on every keystroke
 * - Client-side format validation on submit
 * - Accessible error announcement via role="alert" + aria-describedby
 * - Disabled while the pipeline is running
 */

import { useState, useId } from "react";
import { useAnalysisStore } from "@/store";
import { useAnalysis } from "@/hooks/useAnalysis";
import { isValidTicker, formatTickerError } from "@/lib/validators";
import { AnalyzeButton } from "./AnalyzeButton";

const EXAMPLE_TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"];

export function TickerInput() {
  const { status } = useAnalysisStore();
  const { analyze } = useAnalysis();

  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const errorId = useId();
  const isRunning = status === "loading" || status === "streaming";

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setValue(e.target.value.toUpperCase());
    if (error) setError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (!isValidTicker(trimmed)) {
      setError(formatTickerError(trimmed));
      return;
    }
    setError(null);
    analyze(trimmed);
  }

  function handleExampleClick(ticker: string) {
    setValue(ticker);
    setError(null);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col items-center gap-3 w-full max-w-md mx-auto"
      noValidate
    >
      {/* Search row */}
      <div className="flex w-full items-stretch gap-2">
        <div className="relative flex-1">
          <label htmlFor="ticker-input" className="sr-only">
            Stock ticker symbol
          </label>
          <input
            id="ticker-input"
            type="text"
            inputMode="text"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="Enter ticker — e.g. AAPL"
            maxLength={25}
            value={value}
            onChange={handleChange}
            disabled={isRunning}
            aria-describedby={error ? errorId : undefined}
            aria-invalid={error ? "true" : undefined}
            className={`w-full h-11 rounded-xl border px-4 text-sm font-mono uppercase tracking-widest transition-all duration-150
              focus:outline-none focus:ring-2 focus:ring-offset-0
              disabled:opacity-50 disabled:cursor-not-allowed
              placeholder:normal-case placeholder:tracking-normal placeholder:font-sans placeholder:text-muted-foreground
              ${
                error
                  ? "border-sentiment-negative bg-red-50/50 text-sentiment-negative focus:ring-sentiment-negative/40 dark:bg-red-950/20"
                  : "border-border bg-surface text-foreground hover:border-brand-200 focus:border-brand-500 focus:ring-brand-500/20"
              }`}
          />
        </div>
        <AnalyzeButton status={status} />
      </div>

      {/* Error message */}
      {error && (
        <div
          id={errorId}
          role="alert"
          className="w-full text-xs text-sentiment-negative text-center"
          data-testid="ticker-error"
        >
          {error}
        </div>
      )}

      {/* Example tickers — shown when idle and no value entered */}
      {value === "" && status === "idle" && (
        <div className="w-full flex items-center gap-1.5 flex-wrap justify-center">
          <span className="text-xs text-muted-foreground">Try:</span>
          {EXAMPLE_TICKERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => handleExampleClick(t)}
              className="rounded-md border border-border bg-surface px-2 py-0.5 text-2xs font-mono font-medium text-muted-foreground
                hover:border-brand-200 hover:text-brand-600 hover:bg-brand-50 transition-all duration-100"
            >
              {t}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
