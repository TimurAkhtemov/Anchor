// Shapes of web/public/data/anchor.json (written by app/export_web.py).
// Every numeric field is `number | null`: the exporter maps NaN -> null.

export type Horizon = "daily" | "1m" | "ytd" | "1y";
export type TargetKind =
  | "regime"
  | "indicator"
  | "sector"
  | "allocation"
  | "holding";
export type BenchmarkType =
  | "sector"
  | "cap_style"
  | "market"
  | "bond_market"
  | "duration";
export type RelativeLabel = "ahead" | "behind" | "in_line";
export type SceneKey =
  | "hero"
  | "macro"
  | "sectors"
  | "allocation"
  | "holdings"
  | "coda";

export interface AsOfCalendar {
  as_of_date: string;
  date_prior: string;
  date_1m: string;
  date_ytd: string;
  date_1y: string;
}

export interface MacroRegime {
  as_of_date: string;
  fed_funds_rate: number | null;
  fed_funds_delta_3mo: number | null;
  rates_state: string;
  inflation_yoy: number | null;
  inflation_delta_3mo: number | null;
  inflation_state: string;
  unemployment_rate: number | null;
  unemployment_delta_3mo: number | null;
  labor_state: string;
  regime_summary: string;
}

export interface MacroIndicator {
  indicator_key: string;
  source_series_id: string;
  series_title: string;
  unit_of_measure: string;
  reporting_frequency: string;
  as_of_date: string;
  current_value: number | null;
  value_3mo_ago: number | null;
  delta_3mo: number | null;
  direction: string;
}

export interface SectorPerformance {
  sector: string;
  etf_ticker: string;
  etf_name: string;
  as_of_date: string;
  current_price: number | null;
  daily_return_pct: number | null;
  return_1m_pct: number | null;
  return_ytd_pct: number | null;
  return_1y_pct: number | null;
  rate_comovement: number | null;
  comovement_n_obs: number | null;
  rate_comovement_label: string;
}

export interface PortfolioPosition {
  ticker: string;
  description: string;
  asset_class: string;
  quote_type: string | null;
  sub_style: string | null;
  quantity: number | null;
  latest_close: number | null;
  market_value: number | null;
  weight_pct: number | null;
  valuation_source: string;
  cost_basis: number | null;
  unrealized_gain_pct: number | null;
  return_1m_pct: number | null;
  return_ytd_pct: number | null;
  return_1y_pct: number | null;
  is_root: boolean;
  as_of_date: string;
}

// One row per (holding, benchmark axis) — a holding appears up to 5 times.
export interface HoldingBenchmark {
  holding_ticker: string;
  company_name: string;
  asset_class: string;
  quote_type: string | null;
  weight_pct: number | null;
  sector: string | null;
  market_cap: number | null;
  cap_tier: string | null;
  benchmark_type: BenchmarkType;
  benchmark_etf: string;
  benchmark_name: string;
  as_of_date: string;
  holding_close: number | null;
  benchmark_close: number | null;
  holding_daily_pct: number | null;
  benchmark_daily_pct: number | null;
  relative_daily_pp: number | null;
  label_daily: RelativeLabel;
  holding_1m_pct: number | null;
  benchmark_1m_pct: number | null;
  relative_1m_pp: number | null;
  label_1m: RelativeLabel;
  holding_ytd_pct: number | null;
  benchmark_ytd_pct: number | null;
  relative_ytd_pp: number | null;
  label_ytd: RelativeLabel;
  holding_1y_pct: number | null;
  benchmark_1y_pct: number | null;
  relative_1y_pp: number | null;
  label_1y: RelativeLabel;
}

export interface TourStep {
  id: number;
  target: { kind: TargetKind; key?: string };
  narration: string;
  figures: string[];
  headline_refs: number[];
}

export interface Source {
  ticker: string;
  title: string;
  provider: string;
  pub_date: string;
}

export interface Briefing {
  briefing_md: string;
  steps: TourStep[];
  sources: Source[];
  as_of_date: string;
  generated_at: string;
  provider: string;
  model: string;
}

export interface AnchorBundle {
  as_of_calendar: AsOfCalendar;
  macro_regime: MacroRegime;
  macro_indicators: MacroIndicator[];
  sector_performance: SectorPerformance[];
  portfolio_composition: PortfolioPosition[];
  holdings_benchmarks: HoldingBenchmark[];
  briefing: Briefing;
}

// ---- Resolved tour model (computed at build time in page.tsx) ----

// Steps carry no horizon/axis field; the resolver infers what to spotlight
// by matching the narration's cited figures against the mart rows.
export type StepFocus =
  | { kind: "sector"; horizon: Horizon }
  | { kind: "holding"; horizon: Horizon; axis: BenchmarkType | null }
  | { kind: "static" };

export interface ResolvedStep extends TourStep {
  scene: SceneKey;
  focus: StepFocus;
  headlines: Source[];
}

export interface TourModel {
  steps: ResolvedStep[];
  bundle: AnchorBundle;
}
