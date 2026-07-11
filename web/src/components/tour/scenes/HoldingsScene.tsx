import { AnimatePresence, motion } from "framer-motion";
import { fmtPct, HORIZON_LABEL } from "@/lib/format";
import type { PortfolioPosition } from "@/lib/types";
import { SceneHeading, SceneShell } from "../SceneShell";
import { HeadlineChip } from "../marks/Chip";
import { RelativeBars } from "../marks/RelativeBars";
import { useTour } from "../TourContext";

/** Position tiles with a detail panel: the active step's tile spotlights, and
 *  its benchmark-relative bars + cited headline surface beneath the grid. */
export function HoldingsScene() {
  const { model, activeStep } = useTour();
  const positions = [...model.bundle.portfolio_composition].sort(
    (a, b) => (b.weight_pct ?? 0) - (a.weight_pct ?? 0),
  );

  const isHoldingStep = activeStep?.scene === "holdings";
  const activeTicker = isHoldingStep ? (activeStep.target.key ?? null) : null;
  const focus =
    isHoldingStep && activeStep.focus.kind === "holding"
      ? activeStep.focus
      : null;
  const headlines = isHoldingStep ? activeStep.headlines : [];
  const activePosition = positions.find((p) => p.ticker === activeTicker);
  const benchRows = activeTicker
    ? model.bundle.holdings_benchmarks.filter(
        (r) => r.holding_ticker === activeTicker,
      )
    : [];

  return (
    <SceneShell scene="holdings">
      <div className="w-full">
        <SceneHeading index="V" title="Holdings" />
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
          {positions.map((p) => (
            <HoldingTile
              key={p.ticker}
              position={p}
              state={
                activeTicker === null
                  ? "rest"
                  : p.ticker === activeTicker
                    ? "active"
                    : "dim"
              }
            />
          ))}
        </div>

        <div className="mt-6 min-h-[13rem]">
          <AnimatePresence mode="popLayout" initial={false}>
            {activeTicker && focus && benchRows.length > 0 && (
              <motion.div
                key={activeTicker}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <p className="mb-3 text-sm text-ink-muted">
                  <span className="font-data text-ink">{activeTicker}</span>
                  {activePosition?.description
                    ? ` · ${activePosition.description}`
                    : ""}{" "}
                  — against its benchmarks, {HORIZON_LABEL[focus.horizon]}
                </p>
                <RelativeBars
                  rows={benchRows}
                  horizon={focus.horizon}
                  focusAxis={focus.axis}
                />
                {headlines.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {headlines.map((h) => (
                      <HeadlineChip key={h.title} source={h} />
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </SceneShell>
  );
}

function HoldingTile({
  position,
  state,
}: {
  position: PortfolioPosition;
  state: "active" | "dim" | "rest";
}) {
  return (
    <motion.div
      data-active={state === "active" || undefined}
      initial={false}
      animate={{
        opacity: state === "dim" ? 0.35 : 1,
        scale: state === "active" ? 1.05 : 1,
      }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`rounded-sm border bg-paper-raised px-3 py-2.5 ${
        state === "active" ? "border-pencil shadow-sm" : "border-rule"
      }`}
    >
      <p className="flex items-baseline justify-between gap-2">
        <span className="font-data text-sm font-semibold text-ink">
          {position.ticker}
        </span>
        <span className="font-data text-xs text-ink-muted">
          {position.weight_pct !== null
            ? `${position.weight_pct.toFixed(1)}%`
            : "—"}
        </span>
      </p>
      <p className="mt-0.5 truncate text-[0.6875rem] text-ink-faint">
        {position.description}
      </p>
    </motion.div>
  );
}
