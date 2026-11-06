import {
  allocation,
  benchmarksFor,
  heldByClass,
  presentClasses,
  rollup,
  trendWindow,
} from "@/lib/dashboard";
import {
  AXIS_LABEL,
  classLabel,
  fmtMoney,
  fmtSigned,
  RELATIVE_LABEL,
} from "@/lib/format";
import type {
  AnchorBundle,
  PortfolioPosition,
  ReturnHorizon,
} from "@/lib/types";
import { Sparkline } from "./marks/Sparkline";
import { SectionHead } from "./SectionHead";
import { LABEL_TONE, returnTone } from "./tone";

// Commodity and alt have no alloc token; the demo holds neither, so these are
// the mockup's ramp steps rather than new theme entries.
const ALLOC_COLOR: Record<string, string> = {
  equity: "bg-alloc-equity",
  fixed_income: "bg-alloc-fixed",
  commodity: "bg-[#94866b]",
  cash: "bg-alloc-cash",
  alt: "bg-[#cfc5b1]",
};

export function HoldingsSection({
  bundle,
  horizon,
  cleared,
  onToggleClass,
  onResetClasses,
}: {
  bundle: AnchorBundle;
  horizon: ReturnHorizon;
  cleared: ReadonlySet<string>;
  onToggleClass: (assetClass: string) => void;
  onResetClasses: () => void;
}) {
  const alloc = allocation(bundle);
  const classes = presentClasses(bundle);
  const shown = classes.filter((c) => !cleared.has(c));

  return (
    <section className="mt-11">
      <SectionHead numeral="III" title="Holdings" />
      <p className="mb-4 max-w-[64ch] text-sm text-ink-muted">
        Each holding set against the benchmarks suited to its asset class.
      </p>

      <div className="flex h-[22px] gap-0.5" aria-hidden="true">
        {alloc.map(({ asset_class, weight_pct }) => (
          <span
            key={asset_class}
            className={ALLOC_COLOR[asset_class] ?? "bg-ink-faint"}
            style={{ flexGrow: weight_pct, flexBasis: 0 }}
          />
        ))}
      </div>
      <div className="mt-[9px] mb-[18px] flex flex-wrap gap-x-5 gap-y-1 font-data text-[12.5px] text-ink-muted">
        {alloc.map(({ asset_class, weight_pct }) => (
          <span key={asset_class}>
            <span
              className={`mr-1.5 inline-block size-[9px] ${ALLOC_COLOR[asset_class] ?? "bg-ink-faint"}`}
            />
            {classLabel(asset_class)} {weight_pct.toFixed(1)}%
          </span>
        ))}
      </div>

      <div className="mb-[22px] grid grid-cols-1 lg:grid-cols-5 lg:gap-x-[22px]">
        {rollup(bundle, horizon).map((r) => (
          <div
            key={r.axis}
            data-rollup={r.axis}
            className="flex items-baseline justify-between gap-3 border-t border-rule py-[7px] text-[13.5px] lg:block lg:pb-0"
          >
            <b className="block font-data text-[11px] font-medium tracking-[0.08em] uppercase text-ink-muted lg:mb-0.5">
              {AXIS_LABEL[r.axis]}
            </b>
            <span>
              {r.ahead} ahead · {r.behind} behind · {r.in_line} in line
            </span>
          </div>
        ))}
      </div>

      <div className="mb-2.5 flex flex-wrap items-center gap-4 font-data text-xs tracking-[0.06em] uppercase text-ink-muted">
        <span>Show</span>
        <div
          role="group"
          aria-label="Filter by asset class"
          className="flex flex-wrap items-center gap-4"
        >
          {classes.map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={!cleared.has(c)}
              onClick={() => onToggleClass(c)}
              className="min-h-[34px] cursor-pointer border-b-2 border-transparent py-[7px] uppercase tracking-[0.06em] text-ink-faint line-through hover:text-ink-muted aria-pressed:border-pencil aria-pressed:text-ink aria-pressed:no-underline"
            >
              {classLabel(c)}
            </button>
          ))}
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="border-t border-rule py-8 text-center text-sm text-ink-muted">
          <p>No asset classes selected</p>
          <button
            type="button"
            onClick={onResetClasses}
            className="mt-1 min-h-[34px] cursor-pointer font-data text-xs tracking-[0.06em] uppercase text-pencil underline underline-offset-4"
          >
            Show all
          </button>
        </div>
      ) : (
        shown.map((c) => (
          <div key={c}>
            <h3 className="border-b border-ink pt-[18px] pb-[7px] font-data text-[11.5px] font-medium tracking-[0.1em] uppercase text-ink-muted">
              {classLabel(c)} ·{" "}
              {alloc.find((a) => a.asset_class === c)?.weight_pct.toFixed(1)}% of
              portfolio
            </h3>
            <ul>
              {heldByClass(bundle, c).map((p) => (
                <HoldingRow
                  key={p.ticker}
                  bundle={bundle}
                  position={p}
                  horizon={horizon}
                />
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

function descriptors(bundle: AnchorBundle, p: PortfolioPosition): string {
  const first = benchmarksFor(bundle, p.ticker)[0];
  const out: string[] = [];
  if (first?.quote_type === "EQUITY") {
    if (first.sector) out.push(first.sector);
    if (first.cap_tier) out.push(`${first.cap_tier}-cap`);
  }
  if (p.asset_class === "fixed_income" && p.sub_style) {
    out.push(`${p.sub_style} duration`);
  }
  if (p.is_root) out.push("market root");
  if (p.valuation_source === "source") out.push("import-valued");
  return out.join(" · ");
}

function HoldingRow({
  bundle,
  position: p,
  horizon,
}: {
  bundle: AnchorBundle;
  position: PortfolioPosition;
  horizon: ReturnHorizon;
}) {
  const value = p[`return_${horizon}_pct`];
  const benches = benchmarksFor(bundle, p.ticker);
  const tags = descriptors(bundle, p);
  const series = trendWindow(bundle, p.ticker, horizon);
  const overlay =
    benches[0] && !p.is_root
      ? trendWindow(bundle, benches[0].benchmark_etf, horizon)
      : undefined;
  const weight = p.weight_pct === null ? "—" : `${p.weight_pct.toFixed(1)}%`;

  return (
    <li
      data-holding-row={p.ticker}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 border-b border-rule py-[11px] lg:grid-cols-[minmax(0,1.9fr)_104px_74px_minmax(0,2.3fr)_110px] lg:gap-[18px]"
    >
      <div>
        <span className="font-data text-[13.5px] font-medium">{p.ticker}</span>{" "}
        <span className="text-[13.5px] text-ink-muted">{p.description}</span>
        {tags && <div className="text-[12.5px] text-ink-muted">{tags}</div>}
      </div>
      <div className="text-right lg:text-left">
        <div className="font-data text-[13.5px] tabular-nums">
          {fmtMoney(p.market_value, { cents: true })}
        </div>
        <div className="text-[12.5px] text-ink-muted">
          {weight} weight
          <span className={`lg:hidden ${returnTone(value)}`}>
            {" "}
            · {fmtSigned(value, "%")}
          </span>
        </div>
      </div>
      <div
        className={`hidden text-right font-data text-[13.5px] tabular-nums lg:block ${returnTone(value)}`}
      >
        {fmtSigned(value, "%")}
      </div>
      <div className="col-span-full lg:col-span-1">
        {benches.length === 0 ? (
          <div className="my-px text-[13px] text-ink-muted">
            {p.is_root ? "Market reference point" : "Not benchmarked"}
          </div>
        ) : (
          benches.map((b) => {
            const label = b[`label_${horizon}`];
            return (
              <div
                key={b.benchmark_type}
                className="my-px text-[13px] text-ink-muted"
              >
                {AXIS_LABEL[b.benchmark_type]} vs {b.benchmark_etf}{" "}
                <span
                  className={`font-data text-[12.5px] ${LABEL_TONE[label]}`}
                >
                  {fmtSigned(b[`relative_${horizon}_pp`], " pp")}
                </span>
                <span
                  className={`ml-[5px] font-data text-[11px] tracking-[0.04em] uppercase ${LABEL_TONE[label]}`}
                >
                  {RELATIVE_LABEL[label]}
                </span>
              </div>
            );
          })
        )}
      </div>
      <div className="col-span-full lg:col-span-1">
        <Sparkline series={series} overlay={overlay} />
      </div>
    </li>
  );
}
