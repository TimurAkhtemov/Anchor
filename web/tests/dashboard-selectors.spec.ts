// Selector unit tests — small inline fixtures, no live bundle, no browser.
import { test, expect } from "@playwright/test";
import {
  allocation,
  benchmarksFor,
  heldByClass,
  presentClasses,
  railContent,
  rollup,
  sectorsFor,
  staleness,
  trendWindow,
} from "../src/lib/dashboard";
import type { AnchorBundle } from "../src/lib/types";

function fixture(over: Record<string, unknown> = {}): AnchorBundle {
  const bundle = {
    portfolio: "demo",
    as_of_calendar: {
      as_of_date: "2026-09-04",
      date_prior: "2026-09-03",
      date_1m: "2026-08-04",
      date_ytd: "2025-12-31",
      date_1y: "2025-09-04",
    },
    macro_regime: {
      regime_summary: "Rates steady, inflation cooling, labor firm.",
      rates_state: "steady",
      inflation_state: "cooling",
      labor_state: "firm",
    },
    macro_trend: {},
    ticker_trend: {
      SPY: [
        ["2025-12-30", 1],
        ["2025-12-31", 2],
        ["2026-08-03", 3],
        ["2026-08-04", 4],
        ["2026-09-04", 5],
      ],
    },
    sector_performance: [
      { sector: "A", return_1m_pct: 1 },
      { sector: "B", return_1m_pct: null },
      { sector: "C", return_1m_pct: 3 },
      { sector: "D", return_1m_pct: -2 },
    ],
    portfolio_composition: [
      { ticker: "CASH", asset_class: "cash", weight_pct: 5, market_value: 50 },
      { ticker: "AGG", asset_class: "fixed_income", weight_pct: 15, market_value: 150 },
      { ticker: "AAPL", asset_class: "equity", weight_pct: 30, market_value: 300 },
      { ticker: "MSFT", asset_class: "equity", weight_pct: 50, market_value: 500 },
    ],
    holdings_benchmarks: [
      { holding_ticker: "AAPL", benchmark_type: "sector", label_1m: "ahead", label_ytd: "behind", label_1y: "in_line" },
      { holding_ticker: "MSFT", benchmark_type: "sector", label_1m: "ahead", label_ytd: "ahead", label_1y: "in_line" },
      { holding_ticker: "MSFT", benchmark_type: "cap_style", label_1m: "behind", label_ytd: "ahead", label_1y: "in_line" },
    ],
    briefing: null,
    ...over,
  };
  return bundle as unknown as AnchorBundle;
}

test.describe("sectorsFor", () => {
  test("sorts descending for the horizon with null returns last", () => {
    expect(sectorsFor(fixture(), "1m").map((s) => s.sector)).toEqual([
      "C",
      "A",
      "D",
      "B",
    ]);
  });
});

test.describe("trendWindow", () => {
  test("starts at the horizon's calendar date", () => {
    const b = fixture();
    expect(trendWindow(b, "SPY", "1m").map(([d]) => d)).toEqual([
      "2026-08-04",
      "2026-09-04",
    ]);
    expect(trendWindow(b, "SPY", "ytd")[0][0]).toBe("2025-12-31");
  });
  test("unknown ticker yields an empty series", () => {
    expect(trendWindow(fixture(), "NOPE", "1y")).toEqual([]);
  });
});

test.describe("benchmarksFor", () => {
  test("returns only that holding's axes", () => {
    expect(benchmarksFor(fixture(), "MSFT").map((r) => r.benchmark_type)).toEqual([
      "sector",
      "cap_style",
    ]);
  });
  test("orders axes canonically whatever the mart's row order", () => {
    const b = fixture({
      holdings_benchmarks: [
        { holding_ticker: "X", benchmark_type: "duration" },
        { holding_ticker: "X", benchmark_type: "cap_style" },
        { holding_ticker: "X", benchmark_type: "bond_market" },
        { holding_ticker: "X", benchmark_type: "sector" },
      ],
    });
    expect(benchmarksFor(b, "X").map((r) => r.benchmark_type)).toEqual([
      "sector",
      "cap_style",
      "bond_market",
      "duration",
    ]);
  });
});

test.describe("rollup", () => {
  test("counts labels per axis and omits empty axes", () => {
    const r = rollup(fixture(), "1m");
    expect(r).toEqual([
      { axis: "sector", ahead: 2, behind: 0, in_line: 0 },
      { axis: "cap_style", ahead: 0, behind: 1, in_line: 0 },
    ]);
    expect(r.some((x) => x.axis === "duration")).toBe(false);
  });
});

test.describe("classes", () => {
  test("presentClasses keeps canonical order and lists only held classes", () => {
    expect(presentClasses(fixture())).toEqual(["equity", "fixed_income", "cash"]);
  });
  test("heldByClass sorts by weight descending", () => {
    expect(heldByClass(fixture(), "equity").map((p) => p.ticker)).toEqual([
      "MSFT",
      "AAPL",
    ]);
  });
  test("allocation sums weight per class in canonical order", () => {
    expect(allocation(fixture())).toEqual([
      { asset_class: "equity", weight_pct: 80 },
      { asset_class: "fixed_income", weight_pct: 15 },
      { asset_class: "cash", weight_pct: 5 },
    ]);
  });
});

test.describe("staleness", () => {
  const today = new Date(2026, 8, 8);
  test("4 days is not stale", () => {
    expect(staleness("2026-09-04", today)).toEqual({ stale: false, days: 4 });
  });
  test("5 days is stale", () => {
    expect(staleness("2026-09-03", today)).toEqual({ stale: true, days: 5 });
  });
});

test.describe("railContent", () => {
  test("narration when a briefing exists", () => {
    const b = fixture({
      briefing: {
        briefing_md: "First para.\n\nSecond.",
        steps: [{ narration: "Step zero narration." }],
      },
    });
    expect(railContent(b)).toEqual({ kind: "narration", text: "Step zero narration." });
  });
  test("regime summary with three states when briefing is null", () => {
    const r = railContent(fixture());
    expect(r).toEqual({
      kind: "regime",
      summary: "Rates steady, inflation cooling, labor firm.",
      states: [
        ["Rates", "steady"],
        ["Inflation", "cooling"],
        ["Labor", "firm"],
      ],
    });
  });
});
