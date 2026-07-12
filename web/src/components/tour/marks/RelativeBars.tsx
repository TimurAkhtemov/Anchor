import { motion } from "framer-motion";
import { fmtPp } from "@/lib/format";
import { AXIS_PRIORITY, REL_LABEL_FIELD, REL_PP_FIELD } from "@/lib/resolve";
import type {
  BenchmarkType,
  HoldingBenchmark,
  Horizon,
  RelativeLabel,
} from "@/lib/types";

const LABEL_FILL: Record<RelativeLabel, string> = {
  ahead: "bg-ahead",
  behind: "bg-behind",
  in_line: "bg-steady",
};

const AXIS_LABEL: Record<BenchmarkType, string> = {
  sector: "sector",
  cap_style: "cap style",
  market: "market",
  bond_market: "bond market",
  duration: "duration",
};

/**
 * One center-zero pp bar per benchmark axis, colored by the mart's own
 * ahead/behind/in_line label (calm diverging pair, never red/green). When the
 * step's figures pin an axis, the others recede.
 */
export function RelativeBars({
  rows,
  horizon,
  focusAxis,
}: {
  rows: HoldingBenchmark[];
  horizon: Horizon;
  focusAxis: BenchmarkType | null;
}) {
  const ordered = AXIS_PRIORITY.map((a) =>
    rows.find((r) => r.benchmark_type === a),
  ).filter((r): r is HoldingBenchmark => r !== undefined);
  const maxAbs = Math.max(
    1,
    ...ordered.map((r) => Math.abs(r[REL_PP_FIELD[horizon]] ?? 0)),
  );

  return (
    <div className="flex flex-col gap-2.5">
      {ordered.map((r) => {
        const pp = r[REL_PP_FIELD[horizon]];
        const label = r[REL_LABEL_FIELD[horizon]];
        const inFocus = focusAxis === null || focusAxis === r.benchmark_type;
        const halfWidth = pp === null ? 0 : (Math.abs(pp) / maxAbs) * 50;
        return (
          <div
            key={r.benchmark_type}
            className={`grid grid-cols-[7.5rem_1fr_5.5rem] items-center gap-3 transition-opacity duration-300 ${
              inFocus ? "" : "opacity-40"
            }`}
          >
            <p className="font-data text-xs text-ink">
              vs {r.benchmark_etf}
              <span className="block text-[0.6875rem] text-ink-faint">
                {AXIS_LABEL[r.benchmark_type]}
              </span>
            </p>
            <div className="relative h-2.5">
              <span className="absolute inset-y-0 left-1/2 w-px bg-rule" />
              {pp !== null && (
                <motion.span
                  className={`absolute inset-y-0 rounded-[3px] ${LABEL_FILL[label]}`}
                  initial={false}
                  animate={{
                    left: pp < 0 ? `${50 - halfWidth}%` : "50%",
                    width: `${halfWidth}%`,
                  }}
                  transition={{ type: "spring", stiffness: 170, damping: 26 }}
                />
              )}
            </div>
            <p className="text-right font-data text-xs text-ink">
              {fmtPp(pp)}
            </p>
          </div>
        );
      })}
    </div>
  );
}
