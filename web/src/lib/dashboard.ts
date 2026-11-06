// Pure selectors over AnchorBundle for the dashboard. No I/O, no React.
import type {
  AnchorBundle,
  BenchmarkType,
  HoldingBenchmark,
  PortfolioPosition,
  ReturnHorizon,
  SectorPerformance,
  TrendSeries,
} from "./types";

const CLASS_ORDER = ["equity", "fixed_income", "commodity", "cash", "alt"];
const AXIS_ORDER: BenchmarkType[] = [
  "sector",
  "cap_style",
  "market",
  "bond_market",
  "duration",
];
export const MAX_STALE_DAYS = 4;

const retKey = (h: ReturnHorizon) => `return_${h}_pct` as const;
const dateKey = (h: ReturnHorizon) => `date_${h}` as const;
const labelKey = (h: ReturnHorizon) => `label_${h}` as const;

/** Sectors sorted by the horizon's return, best first, nulls last. */
export function sectorsFor(
  b: AnchorBundle,
  h: ReturnHorizon,
): SectorPerformance[] {
  const k = retKey(h);
  return [...b.sector_performance].sort((x, y) => {
    const a = x[k];
    const c = y[k];
    if (a === null && c === null) return 0;
    if (a === null) return 1;
    if (c === null) return -1;
    return c - a;
  });
}

/** A ticker's closes from the horizon's start date through the as-of date. */
export function trendWindow(
  b: AnchorBundle,
  ticker: string,
  h: ReturnHorizon,
): TrendSeries {
  const start = b.as_of_calendar[dateKey(h)];
  return (b.ticker_trend[ticker] ?? []).filter(([d]) => d >= start);
}

export function benchmarksFor(
  b: AnchorBundle,
  ticker: string,
): HoldingBenchmark[] {
  return b.holdings_benchmarks.filter((r) => r.holding_ticker === ticker);
}

function classRank(c: string): number {
  const i = CLASS_ORDER.indexOf(c);
  return i === -1 ? CLASS_ORDER.length : i;
}

export function presentClasses(b: AnchorBundle): string[] {
  const held = new Set(b.portfolio_composition.map((p) => p.asset_class));
  return [...held].sort((x, y) => classRank(x) - classRank(y));
}

export function heldByClass(
  b: AnchorBundle,
  cls: string,
): PortfolioPosition[] {
  return b.portfolio_composition
    .filter((p) => p.asset_class === cls)
    .sort((x, y) => (y.weight_pct ?? -Infinity) - (x.weight_pct ?? -Infinity));
}

export function allocation(
  b: AnchorBundle,
): { asset_class: string; weight_pct: number }[] {
  return presentClasses(b).map((asset_class) => ({
    asset_class,
    weight_pct: b.portfolio_composition
      .filter((p) => p.asset_class === asset_class)
      .reduce((sum, p) => sum + (p.weight_pct ?? 0), 0),
  }));
}

export interface AxisRollup {
  axis: BenchmarkType;
  ahead: number;
  behind: number;
  in_line: number;
}

/** Ahead/behind/in-line counts per benchmark axis at a horizon. */
export function rollup(b: AnchorBundle, h: ReturnHorizon): AxisRollup[] {
  const k = labelKey(h);
  const out: AxisRollup[] = [];
  for (const axis of AXIS_ORDER) {
    const rows = b.holdings_benchmarks.filter((r) => r.benchmark_type === axis);
    if (rows.length === 0) continue;
    out.push({
      axis,
      ahead: rows.filter((r) => r[k] === "ahead").length,
      behind: rows.filter((r) => r[k] === "behind").length,
      in_line: rows.filter((r) => r[k] === "in_line").length,
    });
  }
  return out;
}

/** Whole calendar days from the as-of date to `today` (local date). */
export function staleness(
  asOf: string,
  today: Date,
): { stale: boolean; days: number } {
  const [y, m, d] = asOf.split("-").map(Number);
  const days = Math.round(
    (Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
      Date.UTC(y, m - 1, d)) /
      86_400_000,
  );
  return { stale: days > MAX_STALE_DAYS, days };
}

export type RailContent =
  | { kind: "narration"; text: string }
  | { kind: "regime"; summary: string; states: [string, string][] };

/** The reading rail: today's briefing when there is one, else the regime. */
export function railContent(b: AnchorBundle): RailContent {
  if (b.briefing) {
    const text =
      b.briefing.steps[0]?.narration ??
      b.briefing.briefing_md.split(/\n\n+/)[0] ??
      "";
    return { kind: "narration", text };
  }
  const r = b.macro_regime;
  return {
    kind: "regime",
    summary: r.regime_summary,
    states: [
      ["Rates", r.rates_state],
      ["Inflation", r.inflation_state],
      ["Labor", r.labor_state],
    ],
  };
}
