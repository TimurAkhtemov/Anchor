import { sectorsFor, trendWindow } from "@/lib/dashboard";
import { fmtSigned } from "@/lib/format";
import type { AnchorBundle, ReturnHorizon, SectorPerformance } from "@/lib/types";
import { DivergingBar } from "./marks/DivergingBar";
import { Sparkline } from "./marks/Sparkline";
import { SectionHead } from "./SectionHead";
import { returnTone } from "./tone";

const CAPTION_LEAD: Record<ReturnHorizon, string> = {
  "1m": "Return over the past month",
  ytd: "Return year to date",
  "1y": "Return over the past year",
};

const returnOf = (s: SectorPerformance, h: ReturnHorizon) =>
  s[`return_${h}_pct`];

export function SectorsSection({
  bundle,
  horizon,
}: {
  bundle: AnchorBundle;
  horizon: ReturnHorizon;
}) {
  const sectors = sectorsFor(bundle, horizon);
  const maxAbs = Math.max(
    0,
    ...sectors.map((s) => Math.abs(returnOf(s, horizon) ?? 0)),
  );

  return (
    <section className="mt-11">
      <SectionHead numeral="II" title="Sectors" />
      <p className="mb-4 max-w-[64ch] text-sm text-ink-muted">
        {CAPTION_LEAD[horizon]}, read under the regime above, with each
        sector&apos;s measured movement against rates (−1 to +1).
      </p>
      <ul>
        {sectors.map((s) => {
          const value = returnOf(s, horizon);
          return (
            <li
              key={s.etf_ticker}
              data-sector-row={s.etf_ticker}
              className="grid grid-cols-[minmax(0,1fr)_70px] items-center gap-x-3 gap-y-0.5 border-b border-rule py-2 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,2fr)_70px_minmax(0,1.1fr)_minmax(0,1.3fr)] lg:gap-[18px]"
            >
              <div>
                <span className="font-data text-[13.5px] font-medium">
                  {s.etf_ticker}
                </span>{" "}
                <span className="text-[13.5px] text-ink-muted">{s.sector}</span>
              </div>
              <div className="hidden lg:block">
                <DivergingBar value={value} maxAbs={maxAbs} />
              </div>
              <div
                className={`text-right font-data text-[13.5px] tabular-nums ${returnTone(value)}`}
              >
                {fmtSigned(value, "%")}
              </div>
              <div className="hidden lg:block">
                <Sparkline
                  series={trendWindow(bundle, s.etf_ticker, horizon)}
                  height={24}
                  colorClass="text-bar"
                />
              </div>
              <div className="col-span-full text-[12.5px] text-ink-muted lg:col-span-1">
                {fmtSigned(s.rate_comovement)} {s.rate_comovement_label}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
