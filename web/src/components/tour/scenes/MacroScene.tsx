import { motion } from "framer-motion";
import {
  fmtMonth,
  fmtPct,
  fmtPp,
  INDICATOR_KEY_TO_LABEL,
  indicatorKeyForLabel,
} from "@/lib/format";
import type { MacroIndicator } from "@/lib/types";
import { SceneHeading, SceneShell } from "../SceneShell";
import { useTour } from "../TourContext";

const DIRECTION_GLYPH: Record<string, string> = {
  up: "↑",
  down: "↓",
};

/** Four indicator cards; the active step's indicator lifts, the others recede.
 *  Deltas are annotated numbers, not charts — monthly series stay humble. */
export function MacroScene() {
  const { model, activeStep } = useTour();
  const indicators = model.bundle.macro_indicators;
  const activeKey =
    activeStep?.scene === "macro" && activeStep.target.key
      ? indicatorKeyForLabel(activeStep.target.key)
      : null;

  return (
    <SceneShell scene="macro">
      <div className="w-full">
        <SceneHeading index="II" title="Macro environment" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {indicators.map((ind) => (
            <IndicatorCard
              key={ind.indicator_key}
              indicator={ind}
              state={
                activeKey === null
                  ? "rest"
                  : activeKey === ind.indicator_key
                    ? "active"
                    : "dim"
              }
            />
          ))}
        </div>
      </div>
    </SceneShell>
  );
}

function IndicatorCard({
  indicator,
  state,
}: {
  indicator: MacroIndicator;
  state: "active" | "dim" | "rest";
}) {
  const label =
    INDICATOR_KEY_TO_LABEL[indicator.indicator_key] ?? indicator.series_title;
  const glyph = DIRECTION_GLYPH[indicator.direction] ?? "→";

  return (
    <motion.div
      data-active={state === "active" || undefined}
      initial={false}
      animate={{
        opacity: state === "dim" ? 0.4 : 1,
        scale: state === "active" ? 1.03 : 1,
      }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className={`rounded-sm border bg-paper-raised p-5 ${
        state === "active" ? "border-pencil shadow-sm" : "border-rule"
      }`}
    >
      <p className="text-sm text-ink-muted">{label}</p>
      <p className="mt-2 font-display text-4xl text-ink">
        {fmtPct(indicator.current_value)}
      </p>
      <p className="mt-2 font-data text-xs text-ink-muted">
        <span
          className={state === "active" ? "text-pencil" : "text-ink"}
        >{`${glyph} ${fmtPp(indicator.delta_3mo)}`}</span>{" "}
        vs 3 months ago
      </p>
      <p className="mt-1 font-data text-[0.6875rem] text-ink-faint">
        as of {fmtMonth(indicator.as_of_date)}
      </p>
    </motion.div>
  );
}
