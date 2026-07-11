import { AnimatePresence, motion } from "framer-motion";
import { fmtPct, HORIZON_LABEL } from "@/lib/format";
import { SECTOR_RETURN_FIELD } from "@/lib/resolve";
import type { Horizon } from "@/lib/types";
import { SceneHeading, SceneShell } from "../SceneShell";
import { BarStrip } from "../marks/BarStrip";
import { useTour } from "../TourContext";

/** The 11-sector return strip at the horizon the active step actually cites;
 *  the spotlit sector surfaces its rate-comovement reading. */
export function SectorsScene() {
  const { model, activeStep } = useTour();
  const sectors = [...model.bundle.sector_performance].sort((a, b) =>
    a.sector.localeCompare(b.sector),
  );

  const isSectorStep = activeStep?.scene === "sectors";
  const horizon: Horizon =
    isSectorStep && activeStep.focus.kind === "sector"
      ? activeStep.focus.horizon
      : "1y";
  const activeTicker = isSectorStep ? (activeStep.target.key ?? null) : null;
  const active = sectors.find((s) => s.etf_ticker === activeTicker);

  return (
    <SceneShell scene="sectors">
      <div className="w-full">
        <SceneHeading index="III" title="Sector performance" />
        <h2 className="font-display text-2xl text-ink">
          All 11 sectors — total return, {HORIZON_LABEL[horizon]}
        </h2>
        <div className="mt-6">
          <BarStrip
            ariaLabel={`Sector ETF returns, ${HORIZON_LABEL[horizon]}`}
            data={sectors.map((s) => ({
              key: s.etf_ticker,
              label: s.etf_ticker,
              value: s[SECTOR_RETURN_FIELD[horizon]],
              emphasis:
                activeTicker === null
                  ? "rest"
                  : s.etf_ticker === activeTicker
                    ? "active"
                    : "dim",
            }))}
            formatValue={(v) => fmtPct(v, { signed: true })}
          />
        </div>
        <div className="mt-4 min-h-12">
          <AnimatePresence initial={false}>
            {active && (
              <motion.p
                key={active.etf_ticker}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="text-sm text-ink-muted"
              >
                <span className="font-data text-xs uppercase tracking-[0.12em] text-pencil">
                  {active.sector}
                </span>{" "}
                — historically{" "}
                <span className="text-ink">{active.rate_comovement_label}</span>{" "}
                ({fmtPct(active[SECTOR_RETURN_FIELD[horizon]], { signed: true })}{" "}
                {HORIZON_LABEL[horizon]})
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>
    </SceneShell>
  );
}
