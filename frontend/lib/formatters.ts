/**
 * Locale-aware formatters for prices, percentages, large numbers, and dates.
 *
 * All functions use Intl.NumberFormat / Intl.DateTimeFormat so they produce
 * locale-correct output without additional libraries.
 */

// ─── Price ────────────────────────────────────────────────────────────────────

/**
 * Format a numeric price as a currency string.
 * e.g. formatPrice(182.63) → "$182.63"
 */
export function formatPrice(
  value: number | null | undefined,
  currency = 'USD',
  locale = 'en-US',
): string {
  if (value == null) return 'N/A';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

// ─── Percentage change ────────────────────────────────────────────────────────

/**
 * Format a percentage change, prepending '+' for positive values.
 * e.g. formatChangePct(1.23) → "+1.23%"
 *      formatChangePct(-0.5) → "-0.50%"
 */
export function formatChangePct(
  value: number | null | undefined,
  locale = 'en-US',
): string {
  if (value == null) return 'N/A';
  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(value));
  return `${value >= 0 ? '+' : '-'}${formatted}%`;
}

// ─── Large numbers (compact) ──────────────────────────────────────────────────

/**
 * Format large numbers with compact notation and a currency prefix.
 * e.g. formatLargeNumber(2_710_000_000_000) → "$2.71T"
 *      formatLargeNumber(84_000_000)          → "$84M"
 */
export function formatLargeNumber(
  value: number | null | undefined,
  currency = 'USD',
  locale = 'en-US',
): string {
  if (value == null) return 'N/A';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

// ─── Volume (no currency symbol) ─────────────────────────────────────────────

/**
 * Format a plain large number (e.g. trading volume) with compact notation.
 * e.g. formatVolume(55_120_000) → "55.12M"
 */
export function formatVolume(
  value: number | null | undefined,
  locale = 'en-US',
): string {
  if (value == null) return 'N/A';
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

// ─── Ratio (plain number, 2 decimal places) ───────────────────────────────────

/**
 * Format a financial ratio (e.g. P/E) as a plain decimal.
 * e.g. formatRatio(28.5) → "28.50"
 */
export function formatRatio(
  value: number | null | undefined,
  locale = 'en-US',
): string {
  if (value == null) return 'N/A';
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

// ─── Date ─────────────────────────────────────────────────────────────────────

/**
 * Format an ISO 8601 date string (YYYY-MM-DD) as a readable date.
 * e.g. formatDate("2024-11-01") → "Nov 1, 2024"
 */
export function formatDate(
  isoDate: string | null | undefined,
  locale = 'en-US',
): string {
  if (!isoDate) return 'N/A';
  try {
    // Append T00:00:00 to avoid timezone-offset day-shift when parsing YYYY-MM-DD
    const date = new Date(`${isoDate}T00:00:00`);
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(date);
  } catch {
    return isoDate;
  }
}

/**
 * Format a full ISO 8601 datetime string as a readable datetime.
 * e.g. formatDateTime("2024-11-01T14:30:00Z") → "Nov 1, 2024, 2:30 PM"
 */
export function formatDateTime(
  isoDateTime: string | null | undefined,
  locale = 'en-US',
): string {
  if (!isoDateTime) return 'N/A';
  try {
    const date = new Date(isoDateTime);
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(date);
  } catch {
    return isoDateTime;
  }
}
