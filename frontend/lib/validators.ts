/**
 * Client-side ticker validation.
 *
 * The regex accepts alphanumeric characters plus an optional dot-suffix,
 * up to 20 base characters — matching the product spec.
 *
 * Valid examples:  AAPL, BRK.B, TSLA, NVDA, MSFT, BRK.A
 * Invalid examples: 123, TOOLONGNAME123, AAPL.TOLONG, @@@@
 */

const TICKER_REGEX = /^[A-Z0-9]{1,20}(\.[A-Z]{1,5})?$/;

export function isValidTicker(ticker: string): boolean {
  return TICKER_REGEX.test(ticker.trim().toUpperCase());
}

export function formatTickerError(ticker: string): string {
  const trimmed = ticker.trim();

  if (!trimmed) {
    return "Please enter a ticker symbol.";
  }

  return "Please enter a valid stock ticker (e.g., AAPL, TSLA, MSFT)";
}
