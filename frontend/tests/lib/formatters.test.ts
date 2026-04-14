/**
 * Formatter unit tests.
 */

import { describe, it, expect } from "vitest";
import {
  formatPrice,
  formatChangePct,
  formatLargeNumber,
  formatVolume,
  formatDate,
  formatDateTime,
} from "@/lib/formatters";

describe("formatChangePct", () => {
  it("formats positive change with leading plus sign", () => {
    expect(formatChangePct(1.23)).toBe("+1.23%");
  });

  it("formats negative change with leading minus sign", () => {
    expect(formatChangePct(-0.45)).toBe("-0.45%");
  });

  it("formats zero as +0.00%", () => {
    expect(formatChangePct(0)).toBe("+0.00%");
  });

  it("returns N/A for null", () => {
    expect(formatChangePct(null)).toBe("N/A");
  });
});

describe("formatLargeNumber", () => {
  it("formats large numbers with compact notation", () => {
    // $2.71T
    const result = formatLargeNumber(2710000000000);
    expect(result).toMatch(/2\.71T|\$2\.71T/);
  });

  it("returns N/A for null", () => {
    expect(formatLargeNumber(null)).toBe("N/A");
  });
});

describe("formatPrice", () => {
  it("formats a price with two decimal places", () => {
    expect(formatPrice(182.63)).toBe("$182.63");
  });

  it("returns N/A for null", () => {
    expect(formatPrice(null)).toBe("N/A");
  });
});

describe("formatVolume", () => {
  it("formats volume with compact notation", () => {
    const result = formatVolume(55120000);
    expect(result).toMatch(/55/);
  });

  it("returns N/A for null", () => {
    expect(formatVolume(null)).toBe("N/A");
  });
});

describe("formatDate", () => {
  it("formats a YYYY-MM-DD date string", () => {
    const result = formatDate("2024-11-01");
    expect(result).toContain("2024");
    expect(result).toContain("Nov");
  });

  it("returns N/A for null", () => {
    expect(formatDate(null)).toBe("N/A");
  });
});

describe("formatDateTime", () => {
  it("formats an ISO datetime string", () => {
    const result = formatDateTime("2024-11-01T14:30:00Z");
    expect(result).toContain("2024");
  });

  it("returns N/A for null", () => {
    expect(formatDateTime(null)).toBe("N/A");
  });
});
