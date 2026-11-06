import type {
  BenchmarkType,
  Horizon,
  RelativeLabel,
  ReturnHorizon,
} from "./types";

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

export const INDICATOR_KEY_TO_LABEL: Record<string, string> =
  Object.fromEntries(
    Object.entries(INDICATOR_LABEL_TO_KEY).map(([label, key]) => [key, label]),
  );

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

export function fmtMoney(
  v: number | null,
  { cents = false }: { cents?: boolean } = {},
): string {
  if (v === null) return "—";
  return v.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  });
}

/** Two decimals with an explicit sign and a true minus; a zero carries neither. */
export function fmtSigned(v: number | null, unit = ""): string {
  if (v === null) return "—";
  const body = Math.abs(v).toFixed(2);
  const sign = Number(body) === 0 ? "" : v > 0 ? "+" : "−";
  return `${sign}${body}${unit}`;
}

export const RETURN_HORIZON_BUTTON: Record<ReturnHorizon, string> = {
  "1m": "1 Month",
  ytd: "YTD",
  "1y": "1 Year",
};

export const AXIS_LABEL: Record<BenchmarkType, string> = {
  sector: "Sector",
  cap_style: "Cap-style",
  market: "Market",
  bond_market: "Bond market",
  duration: "Duration",
};

export const RELATIVE_LABEL: Record<RelativeLabel, string> = {
  ahead: "ahead",
  behind: "behind",
  in_line: "in line",
};

const CLASS_LABEL: Record<string, string> = {
  equity: "Equities",
  fixed_income: "Fixed income",
  commodity: "Commodities",
  cash: "Cash",
  alt: "Other",
};

export function classLabel(assetClass: string): string {
  return CLASS_LABEL[assetClass] ?? assetClass;
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

// Monthly indicators are dated to the 1st; "May 2026" is the honest label.
export function fmtMonth(iso: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}
