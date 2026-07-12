// Resolver unit tests — pure imports, no page fixture, no browser.
import { test, expect } from "@playwright/test";
import {
  buildTourModel,
  parseFigure,
  resolveHoldingFocus,
  resolveStepFocus,
} from "../src/lib/resolve";
import type {
  AnchorBundle,
  HoldingBenchmark,
  RelativeLabel,
  TourStep,
} from "../src/lib/types";
import bundleJson from "../public/data/anchor.json";

const bundle = bundleJson as unknown as AnchorBundle;

test.describe("parseFigure", () => {
  test("parses % and pp display strings", () => {
    expect(parseFigure("4.17%")).toEqual({ value: 4.17, unit: "%" });
    expect(parseFigure("+1.73 pp")).toEqual({ value: 1.73, unit: "pp" });
    expect(parseFigure("-48.41 pp")).toEqual({ value: -48.41, unit: "pp" });
    expect(parseFigure("84.0%")).toEqual({ value: 84, unit: "%" });
  });

  test("rejects non-figures", () => {
    expect(parseFigure("steady")).toBeNull();
    expect(parseFigure("4.17")).toBeNull();
    expect(parseFigure("$622")).toBeNull();
  });
});

test.describe("resolveStepFocus against the committed bundle", () => {
  // Regression pins: verified against the live narrations (HIMS cites its 1m
  // sector comparison; TALO and JPM cite 1y; JPM mixes a 1m % with a 1y pp —
  // the pp must win the horizon).
  const expected: Record<string, { horizon: string; axis: string | null }> = {
    AAPL: { horizon: "1y", axis: "cap_style" },
    JPM: { horizon: "1y", axis: "sector" },
    HIMS: { horizon: "1m", axis: "sector" },
    CVLG: { horizon: "ytd", axis: "sector" },
    TALO: { horizon: "1y", axis: "sector" },
  };

  test("holding steps resolve to the narrated (axis, horizon) cell", () => {
    const holdingSteps = bundle.briefing.steps.filter(
      (s) => s.target.kind === "holding",
    );
    expect(holdingSteps.length).toBeGreaterThan(0);
    for (const step of holdingSteps) {
      const focus = resolveStepFocus(step, bundle);
      const want = expected[step.target.key ?? ""];
      if (want) {
        expect(focus, `step ${step.id} (${step.target.key})`).toEqual({
          kind: "holding",
          ...want,
        });
      } else {
        expect(focus.kind).toBe("holding");
      }
    }
  });

  test("sector steps resolve to the cited horizon", () => {
    const focuses = bundle.briefing.steps
      .filter((s) => s.target.kind === "sector")
      .map((s) => [s.target.key, resolveStepFocus(s, bundle)]);
    expect(focuses).toEqual([
      ["XLV", { kind: "sector", horizon: "1m" }],
      ["XLF", { kind: "sector", horizon: "ytd" }],
    ]);
  });

  test("regime/indicator/allocation steps are static", () => {
    for (const step of bundle.briefing.steps) {
      if (["regime", "indicator", "allocation"].includes(step.target.kind)) {
        expect(resolveStepFocus(step, bundle)).toEqual({ kind: "static" });
      }
    }
  });
});

// Minimal fixture: one holding with two axis rows, distinct values per cell.
function benchRow(over: Partial<HoldingBenchmark>): HoldingBenchmark {
  const label: RelativeLabel = "ahead";
  return {
    holding_ticker: "TEST",
    company_name: "Test Co",
    asset_class: "equity",
    quote_type: "EQUITY",
    weight_pct: 5,
    sector: "Technology",
    market_cap: 1e10,
    cap_tier: "Large",
    benchmark_type: "sector",
    benchmark_etf: "XLK",
    benchmark_name: "Tech SPDR",
    as_of_date: "2026-07-08",
    holding_close: 100,
    benchmark_close: 200,
    holding_daily_pct: 0.5,
    benchmark_daily_pct: 0.1,
    relative_daily_pp: 0.4,
    label_daily: label,
    holding_1m_pct: 10.0,
    benchmark_1m_pct: 4.0,
    relative_1m_pp: 6.0,
    label_1m: label,
    holding_ytd_pct: 20.0,
    benchmark_ytd_pct: 12.0,
    relative_ytd_pp: 8.0,
    label_ytd: label,
    holding_1y_pct: 30.0,
    benchmark_1y_pct: 25.0,
    relative_1y_pp: 5.0,
    label_1y: label,
    ...over,
  };
}

const fixtureRows = [
  benchRow({}),
  benchRow({
    benchmark_type: "cap_style",
    benchmark_etf: "SPY",
    benchmark_name: "SPDR S&P 500",
    benchmark_1m_pct: 3.0,
    relative_1m_pp: 7.0,
    benchmark_ytd_pct: 11.0,
    relative_ytd_pp: 9.0,
    benchmark_1y_pct: 24.0,
    relative_1y_pp: 6.5,
  }),
];

const fig = (s: string) => {
  const parsed = parseFigure(s);
  if (!parsed) throw new Error(`bad fixture figure: ${s}`);
  return parsed;
};

test.describe("resolveHoldingFocus edge cases", () => {
  test("pp match pins both axis and horizon", () => {
    expect(resolveHoldingFocus(fixtureRows, [fig("+7.00 pp")])).toEqual({
      kind: "holding",
      horizon: "1m",
      axis: "cap_style",
    });
  });

  test("% evidence alone fixes the horizon but not the axis", () => {
    expect(resolveHoldingFocus(fixtureRows, [fig("+20.00%")])).toEqual({
      kind: "holding",
      horizon: "ytd",
      axis: null,
    });
  });

  test("nothing matches -> 1y fallback with no axis", () => {
    expect(resolveHoldingFocus(fixtureRows, [fig("+99.99%")])).toEqual({
      kind: "holding",
      horizon: "1y",
      axis: null,
    });
    expect(resolveHoldingFocus([], [fig("+7.00 pp")])).toEqual({
      kind: "holding",
      horizon: "1y",
      axis: null,
    });
  });

  test("null cells never match", () => {
    const rows = [
      benchRow({ relative_1m_pp: null, holding_1m_pct: null }),
    ];
    expect(resolveHoldingFocus(rows, [fig("+6.00 pp")])).toEqual({
      kind: "holding",
      horizon: "1y",
      axis: null,
    });
  });
});

test.describe("buildTourModel", () => {
  test("resolves every step and maps scenes by target kind", () => {
    const model = buildTourModel(bundle);
    expect(model.steps.length).toBe(bundle.briefing.steps.length);
    const scenes = model.steps.map((s) => s.scene);
    // Reading order is validated upstream (regime -> ... -> holding), so
    // scenes must be non-decreasing in tour order.
    const order = ["hero", "macro", "sectors", "allocation", "holdings"];
    const ranks = scenes.map((s) => order.indexOf(s));
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
  });

  test("headline refs resolve to sources; out-of-range refs are dropped", () => {
    const step: TourStep = {
      id: 1,
      target: { kind: "regime", key: "Macro regime" },
      narration: "Test.",
      figures: [],
      headline_refs: [0, 999, -1],
    };
    const model = buildTourModel({
      ...bundle,
      briefing: { ...bundle.briefing, steps: [step] },
    });
    expect(model.steps[0].headlines).toEqual([bundle.briefing.sources[0]]);
  });
});
