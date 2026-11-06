import Link from "next/link";
import { useSyncExternalStore } from "react";
import { railContent, staleness } from "@/lib/dashboard";
import { fmtDate, RETURN_HORIZON_BUTTON } from "@/lib/format";
import type { AnchorBundle, ReturnHorizon } from "@/lib/types";

const HORIZONS: ReturnHorizon[] = ["1m", "ytd", "1y"];
const subscribeNever = () => () => {};

/** Days the data has been stale, or null when fresh. The server render has no
 *  "today", so the notice can only appear after hydration. */
function useStaleDays(asOf: string): number | null {
  return useSyncExternalStore(
    subscribeNever,
    () => {
      const { stale, days } = staleness(asOf, new Date());
      return stale ? days : null;
    },
    () => null,
  );
}

export function Masthead({
  bundle,
  horizon,
  onHorizon,
}: {
  bundle: AnchorBundle;
  horizon: ReturnHorizon;
  onHorizon: (h: ReturnHorizon) => void;
}) {
  const asOf = bundle.as_of_calendar.as_of_date;
  const staleDays = useStaleDays(asOf);

  return (
    <header data-masthead>
      <div className="flex flex-wrap justify-between gap-x-4 border-b border-ink pb-[9px] font-data text-[11.5px] leading-normal tracking-[0.14em] uppercase text-ink-muted">
        <span>
          <b className="font-medium text-ink">Anchor</b> · Morning briefing
        </span>
        <span>
          {fmtDate(asOf)} ·{" "}
          <span className="text-pencil">
            {bundle.portfolio === "demo" ? "Demo portfolio" : "Private"}
          </span>
        </span>
      </div>

      {staleDays !== null && (
        <p className="mt-2 font-data text-xs text-ink-muted">
          Data through {fmtDate(asOf)}, {staleDays} days ago.
        </p>
      )}

      <div className="mt-6 grid grid-cols-1 gap-[22px] lg:grid-cols-[minmax(0,1fr)_330px] lg:gap-[52px]">
        <div>
          <h1 className="m-0 font-display text-[clamp(38px,5.4vw,66px)] leading-[1.04] font-normal tracking-[-0.022em]">
            {bundle.macro_regime.regime_summary}.
          </h1>
          <div
            role="group"
            aria-label="Return horizon"
            className="mt-[22px] flex flex-wrap items-center gap-4 font-data text-xs tracking-[0.06em] uppercase text-ink-muted"
          >
            <span>Returns over</span>
            {HORIZONS.map((h) => (
              <button
                key={h}
                type="button"
                aria-pressed={horizon === h}
                onClick={() => onHorizon(h)}
                className="min-h-[34px] cursor-pointer border-b-2 border-transparent px-0.5 py-2 uppercase tracking-[0.06em] text-ink-muted hover:text-ink aria-pressed:border-pencil aria-pressed:text-ink"
              >
                {RETURN_HORIZON_BUTTON[h]}
              </button>
            ))}
          </div>
        </div>
        <Rail bundle={bundle} />
      </div>
    </header>
  );
}

function Rail({ bundle }: { bundle: AnchorBundle }) {
  const rail = railContent(bundle);
  return (
    <aside
      data-rail
      className="border-l-2 border-pencil pl-4 font-display text-[16.5px] leading-normal italic"
    >
      {rail.kind === "narration" ? (
        <>
          <p className="mb-[9px]">{rail.text}</p>
          <Link
            href="/reading/"
            className="inline-block border-b border-pencil pt-1.5 pb-0.5 font-data text-xs leading-[1.4] font-medium tracking-[0.08em] uppercase not-italic text-pencil"
          >
            Begin the guided reading →
          </Link>
        </>
      ) : (
        <>
          <p className="mb-[9px]">{rail.summary}.</p>
          <dl className="font-data text-xs not-italic">
            {rail.states.map(([name, state]) => (
              <div key={name} className="flex gap-2 py-0.5">
                <dt className="w-20 text-ink-muted">{name}</dt>
                <dd className="tracking-[0.1em] uppercase text-pencil">{state}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </aside>
  );
}
