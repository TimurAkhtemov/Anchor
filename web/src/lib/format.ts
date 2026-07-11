import type { Horizon } from "./types";

// Tour steps address indicators by their briefing label (app/briefing.py
// _INDICATOR_LABELS); the marts key them by indicator_key. Unknown labels
// pass through so a future indicator degrades to "no card matches", not a crash.
export const INDICATOR_LABEL_TO_KEY: Record<string, string> = {
  "Fed Funds Rate": "fed_funds_rate",
  "10-Year Treasury": "ten_year_yield",
  "Inflation (YoY)": "inflation_yoy",
  Unemployment: "unemployment_rate",
};

export function indicatorKeyForLabel(label: string): string {
  return INDICATOR_LABEL_TO_KEY[label] ?? label;
}

export const HORIZON_LABEL: Record<Horizon, string> = {
  daily: "today",
  "1m": "past month",
  ytd: "year to date",
  "1y": "past year",
};

export function fmtPct(
  v: number | null,
  { signed = false }: { signed?: boolean } = {},
): string {
  if (v === null) return "—";
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

export function fmtPp(v: number | null): string {
  if (v === null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)} pp`;
}

export function fmtMoney(v: number | null): string {
  if (v === null) return "—";
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

// Manual parse: `new Date("2026-07-08")` is UTC midnight, so rendering it in a
// client component can shift a day (and mismatch the build server's timezone).
export function fmtDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}
