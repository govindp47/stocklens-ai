/**
 * Client-side ticker validation.
 *
 * The regex mirrors the backend's validation:
 *   ^[A-Za-z]{1,5}(\.[A-Za-z]{1,3})?$
 *
 * Valid examples:  AAPL, BRK.A, MSFT, BRK.B
 * Invalid examples: 123, TOOLONG, AAPL.TOLONG
 */

const TICKER_REGEX = /^[A-Za-z]{1,5}(\.[A-Za-z]{1,3})?$/;

export function isValidTicker(ticker: string): boolean {
  return TICKER_REGEX.test(ticker.trim());
}

export function formatTickerError(ticker: string): string {
  const trimmed = ticker.trim();

  if (!trimmed) {
    return 'Please enter a ticker symbol.';
  }

  if (/\d/.test(trimmed)) {
    return 'Ticker symbols contain letters only (e.g. AAPL, TSLA).';
  }

  if (trimmed.length > 6) {
    return 'Ticker symbols are 1–5 letters, optionally followed by a dot and 1–3 letters (e.g. BRK.A).';
  }

  return `"${trimmed.toUpperCase()}" is not a valid ticker symbol. Try a format like AAPL or BRK.A.`;
}
