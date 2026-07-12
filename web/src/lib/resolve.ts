// Pure tour-script resolution — no React, no browser APIs.
// Runs once at build time (page.tsx) and directly in unit tests.

import type {
  AnchorBundle,
  BenchmarkType,
  HoldingBenchmark,
  Horizon,
  ResolvedStep,
  SceneKey,
  SectorPerformance,
  StepFocus,
  TargetKind,
  TourModel,
  TourStep,
} from "./types";

export interface ParsedFigure {
  value: number;
  unit: "%" | "pp";
}

// Figures arrive as display strings verbatim from the narration: "+31.18 pp", "4.17%".
export function parseFigure(fig: string): ParsedFigure | null {
  const m = /^([+-]?\d+(?:\.\d+)?)\s*(%|pp)$/.exec(fig.trim());
  if (!m) return null;
  return { value: Number(m[1]), unit: m[2] as "%" | "pp" };
}

// Mart values are rounded to 2dp before narration, so equality within half a
// basis point is a match, not a coincidence.
const EPS = 0.005;
export const near = (a: number, b: number | null): boolean =>
  b !== null && Math.abs(a - b) < EPS;

export const HORIZONS: Horizon[] = ["daily", "1m", "ytd", "1y"];
// Tie-break toward the longer lens — the briefing leans on 1y context.
export const HORIZON_PRIORITY: Horizon[] = ["1y", "ytd", "1m", "daily"];
// Tie-break toward the more specific comparison (sector before market-wide).
export const AXIS_PRIORITY: BenchmarkType[] = [
  "sector",
  "cap_style",
  "market",
  "bond_market",
  "duration",
];

export const SECTOR_RETURN_FIELD = {
  daily: "daily_return_pct",
  "1m": "return_1m_pct",
  ytd: "return_ytd_pct",
  "1y": "return_1y_pct",
} as const satisfies Record<Horizon, keyof SectorPerformance>;

export const REL_PP_FIELD = {
  daily: "relative_daily_pp",
  "1m": "relative_1m_pp",
  ytd: "relative_ytd_pp",
  "1y": "relative_1y_pp",
} as const satisfies Record<Horizon, keyof HoldingBenchmark>;

export const HOLDING_PCT_FIELD = {
  daily: "holding_daily_pct",
  "1m": "holding_1m_pct",
  ytd: "holding_ytd_pct",
  "1y": "holding_1y_pct",
} as const satisfies Record<Horizon, keyof HoldingBenchmark>;

export const BENCHMARK_PCT_FIELD = {
  daily: "benchmark_daily_pct",
  "1m": "benchmark_1m_pct",
  ytd: "benchmark_ytd_pct",
  "1y": "benchmark_1y_pct",
} as const satisfies Record<Horizon, keyof HoldingBenchmark>;

export const REL_LABEL_FIELD = {
  daily: "label_daily",
  "1m": "label_1m",
  ytd: "label_ytd",
  "1y": "label_1y",
} as const satisfies Record<Horizon, keyof HoldingBenchmark>;

function resolveSectorFocus(
  row: SectorPerformance | undefined,
  figures: ParsedFigure[],
): StepFocus {
  if (!row) return { kind: "sector", horizon: "1y" };
  const pcts = figures.filter((f) => f.unit === "%");
  let best: Horizon | null = null;
  let bestScore = 0;
  // Iterating in priority order + strict `>` makes ties fall to the longer lens.
  for (const h of HORIZON_PRIORITY) {
    const v = row[SECTOR_RETURN_FIELD[h]];
    const score = pcts.filter((f) => near(f.value, v)).length;
    if (score > bestScore) {
      best = h;
      bestScore = score;
    }
  }
  return { kind: "sector", horizon: best ?? "1y" };
}

// A holding step cites figures at unstated horizons, sometimes mixed within one
// narration (JPM: a 1m return % next to a 1y relative pp). The pp figure is the
// authoritative signal — `relative_{h}_pp` is unique per (axis, horizon) cell,
// so a pp match pins both. A % match only says "this horizon is being discussed"
// (holding_%/benchmark_% repeat across the holding's axis rows).
export function resolveHoldingFocus(
  rows: HoldingBenchmark[],
  figures: ParsedFigure[],
): StepFocus {
  const pps = figures.filter((f) => f.unit === "pp");
  const pcts = figures.filter((f) => f.unit === "%");
  if (rows.length === 0) return { kind: "holding", horizon: "1y", axis: null };

  // Rows arrive in mart order; walk them in axis-priority order so that with
  // strict `>` below, ties fall to horizon priority first, then axis priority.
  const ordered = AXIS_PRIORITY.map((axis) =>
    rows.find((r) => r.benchmark_type === axis),
  ).filter((r): r is HoldingBenchmark => r !== undefined);

  let best: StepFocus | null = null;
  let bestScore = 0;
  for (const h of HORIZON_PRIORITY) {
    for (const row of ordered) {
      const ppHits = pps.filter((f) => near(f.value, row[REL_PP_FIELD[h]]));
      const pctHits = pcts.filter(
        (f) =>
          near(f.value, row[HOLDING_PCT_FIELD[h]]) ||
          near(f.value, row[BENCHMARK_PCT_FIELD[h]]),
      );
      const score = ppHits.length * 2 + pctHits.length;
      if (score > bestScore) {
        // Only a pp match may fix the axis; % evidence alone repeats across
        // the holding's axis rows, so it can only vouch for the horizon.
        best = {
          kind: "holding",
          horizon: h,
          axis: ppHits.length > 0 ? row.benchmark_type : null,
        };
        bestScore = score;
      }
    }
  }
  return best ?? { kind: "holding", horizon: "1y", axis: null };
}

export function resolveStepFocus(
  step: TourStep,
  bundle: AnchorBundle,
): StepFocus {
  const figures = step.figures
    .map(parseFigure)
    .filter((f): f is ParsedFigure => f !== null);
  switch (step.target.kind) {
    case "sector":
      return resolveSectorFocus(
        bundle.sector_performance.find(
          (r) => r.etf_ticker === step.target.key,
        ),
        figures,
      );
    case "holding":
      return resolveHoldingFocus(
        bundle.holdings_benchmarks.filter(
          (r) => r.holding_ticker === step.target.key,
        ),
        figures,
      );
    // regime / indicator / allocation figures are the displayed numbers
    // themselves — nothing to infer.
    default:
      return { kind: "static" };
  }
}

const KIND_TO_SCENE: Record<TargetKind, SceneKey> = {
  regime: "hero",
  indicator: "macro",
  sector: "sectors",
  allocation: "allocation",
  holding: "holdings",
};

export function buildTourModel(bundle: AnchorBundle): TourModel {
  const { sources } = bundle.briefing;
  const steps: ResolvedStep[] = bundle.briefing.steps.map((step) => ({
    ...step,
    scene: KIND_TO_SCENE[step.target.kind] ?? "hero",
    focus: resolveStepFocus(step, bundle),
    headlines: step.headline_refs
      .filter((i) => Number.isInteger(i) && i >= 0 && i < sources.length)
      .map((i) => sources[i]),
  }));
  return { steps, bundle };
}
