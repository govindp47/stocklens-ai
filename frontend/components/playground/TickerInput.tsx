'use client';

/**
 * TickerInput — ticker symbol input with:
 * - Auto-uppercase on every keystroke
 * - Client-side format validation on submit (no pipeline triggered on invalid input)
 * - Accessible error announcement via role="alert" + aria-describedby
 * - Disabled while the pipeline is running
 */

import { useState, useId } from 'react';
import { useAnalysisStore } from '@/store';
import { useAnalysis } from '@/hooks/useAnalysis';
import { isValidTicker, formatTickerError } from '@/lib/validators';
import { AnalyzeButton } from './AnalyzeButton';

export function TickerInput() {
  const { status } = useAnalysisStore();
  const { analyze } = useAnalysis();

  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const errorId = useId();
  const isRunning = status === 'loading' || status === 'streaming';

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    // Auto-uppercase every character as it's typed
    setValue(e.target.value.toUpperCase());
    // Clear error on edit
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

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col items-center gap-3 w-full max-w-sm mx-auto"
      noValidate
    >
      <div className="w-full">
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
          placeholder="e.g. AAPL"
          value={value}
          onChange={handleChange}
          disabled={isRunning}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? 'true' : undefined}
          className="w-full rounded-md border border-neutral-300 px-4 py-2 text-center text-sm uppercase tracking-widest focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />

        {/* Error message — role="alert" ensures immediate announcement */}
        {error && (
          <div
            id={errorId}
            role="alert"
            className="mt-1.5 text-xs text-sentiment-negative text-center"
            data-testid="ticker-error"
          >
            {error}
          </div>
        )}
      </div>

      <AnalyzeButton status={status} />

      <p className="text-xs text-neutral-400">
        Try: AAPL, TSLA, NVDA, MSFT
      </p>
    </form>
  );
}
