import { fmtPct, fmtSigned } from "@/lib/format";
import {
  GUIDE_INDICATORS,
  GUIDE_INTRO,
  GUIDE_REGIME_STATES,
  MACRO_CARDS,
} from "@/lib/guide";
import type { AnchorBundle } from "@/lib/types";
import { Sparkline } from "./marks/Sparkline";
import { SectionHead } from "./SectionHead";

export function MacroSection({ bundle }: { bundle: AnchorBundle }) {
  const regime = bundle.macro_regime;
  const states: Record<string, string> = {
    fed_funds_rate: regime.rates_state,
    inflation_yoy: regime.inflation_state,
    unemployment_rate: regime.labor_state,
  };

  return (
    <section className="mt-11">
      <SectionHead numeral="I" title="Macro environment" />
      <HowToRead />
      <div className="grid grid-cols-2 border-y border-rule lg:grid-cols-4">
        {MACRO_CARDS.map(({ key, label }) => {
          const m = bundle.macro_indicators.find((x) => x.indicator_key === key);
          return (
            <div
              key={key}
              data-macro-col={key}
              className="min-w-0 border-t border-rule px-3 pt-3 pb-3.5 even:border-l nth-[-n+2]:border-t-0 lg:border-t-0 lg:border-l lg:px-[18px] lg:pt-3.5 lg:pb-4 lg:first:border-l-0 lg:first:pl-0"
            >
              <div className="mb-0.5 min-h-[17px] font-data text-[11px] font-medium tracking-[0.1em] uppercase text-pencil">
                {states[key] ?? ""}
              </div>
              <div className="text-[13px] text-ink-muted">{label}</div>
              <div className="font-display text-[34px] leading-[1.15] tracking-[-0.02em] tabular-nums lg:text-[42px]">
                {fmtPct(m?.current_value ?? null)}
              </div>
              <div className="mb-2.5 font-data text-[11.5px] leading-normal text-ink-muted">
                {fmtSigned(m?.delta_3mo ?? null, " pp")} in 3 mo
              </div>
              {/* Full series at every horizon: monthly indicators have too few
                  points to window to one month. */}
              <Sparkline
                series={bundle.macro_trend[key] ?? []}
                colorClass="text-pencil"
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}

function HowToRead() {
  return (
    <details className="-mt-1.5 mb-4 text-sm text-ink-muted">
      <summary className="cursor-pointer text-pencil">How to read this</summary>
      <div className="mt-3 max-w-[64ch] lg:max-w-none">
        <p className="lg:max-w-[64ch]">{GUIDE_INTRO}</p>
        <div className="mt-4 grid gap-6 lg:grid-cols-3 lg:gap-8">
          <GuideBlock title="The macro indicators">
            <dl className="space-y-2">
              {GUIDE_INDICATORS.map(({ name, text }) => (
                <div key={name}>
                  <dt className="text-ink">{name}</dt>
                  <dd>{text}</dd>
                </div>
              ))}
            </dl>
          </GuideBlock>
          <GuideBlock title="Each column">
            <dl className="space-y-2">
              {MACRO_CARDS.map(({ key, label, help }) => (
                <div key={key}>
                  <dt className="text-ink">{label}</dt>
                  <dd>{help}</dd>
                </div>
              ))}
            </dl>
          </GuideBlock>
          <GuideBlock title="The regime states">
            <div className="space-y-3">
              {GUIDE_REGIME_STATES.map(({ name, states }) => (
                <div key={name}>
                  <div className="text-ink">{name}</div>
                  <dl className="space-y-1">
                    {states.map(({ state, rule }) => (
                      <div key={state}>
                        <dt className="font-data text-[11px] font-medium tracking-[0.1em] uppercase text-pencil">
                          {state}
                        </dt>
                        <dd>{rule}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </GuideBlock>
        </div>
      </div>
    </details>
  );
}

function GuideBlock({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="mb-2 font-data text-[11.5px] font-medium tracking-[0.1em] uppercase text-ink-muted">
        {title}
      </h3>
      {children}
    </div>
  );
}
