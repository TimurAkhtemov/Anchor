import { fmtDate } from "@/lib/format";
import { SceneShell } from "../SceneShell";
import { StateChip } from "../marks/Chip";
import { useTour } from "../TourContext";

/** The masthead: dateline, the regime sentence set as the day's headline,
 *  and the three state chips. */
export function HeroScene() {
  const { model } = useTour();
  const { macro_regime, as_of_calendar } = model.bundle;

  return (
    <SceneShell scene="hero">
      <div className="w-full">
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink pb-3">
          <p className="font-data text-[0.6875rem] uppercase tracking-[0.25em] text-ink">
            Anchor · Morning Briefing
          </p>
          <p className="font-data text-[0.6875rem] uppercase tracking-[0.15em] text-ink-muted">
            {fmtDate(as_of_calendar.as_of_date)} · demo portfolio
          </p>
        </header>

        <h1 className="mt-10 font-display text-[clamp(2.5rem,6.5vw,5rem)] leading-[1.06] tracking-[-0.015em] text-ink">
          {macro_regime.regime_summary}.
        </h1>

        <div className="mt-10 flex flex-wrap gap-3">
          <StateChip label="Rates" state={macro_regime.rates_state} />
          <StateChip label="Inflation" state={macro_regime.inflation_state} />
          <StateChip label="Labor" state={macro_regime.labor_state} />
        </div>

        <p className="mt-14 font-display italic text-ink-faint">
          A guided reading — macro, then sectors, then holdings. Scroll when
          ready. ↓
        </p>
      </div>
    </SceneShell>
  );
}
