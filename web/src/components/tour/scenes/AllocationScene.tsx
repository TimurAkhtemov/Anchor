import { fmtMoney } from "@/lib/format";
import { SceneHeading, SceneShell } from "../SceneShell";
import { AllocationBand } from "../marks/AllocationBand";
import type { AllocationSegment } from "../marks/AllocationBand";
import { useTour } from "../TourContext";

// Band order = ink-wash darkness order; unknown future classes append in
// neutral rather than silently dropping.
const CLASS_META: Array<{ key: string; label: string; colorClass: string }> = [
  { key: "equity", label: "Equity", colorClass: "bg-alloc-equity" },
  { key: "fixed_income", label: "Fixed income", colorClass: "bg-alloc-fixed" },
  { key: "cash", label: "Cash", colorClass: "bg-alloc-cash" },
];

/** The proportional ink-wash band: how the portfolio is deployed. */
export function AllocationScene() {
  const { model } = useTour();
  const positions = model.bundle.portfolio_composition;

  const sums = new Map<string, number>();
  let total = 0;
  for (const p of positions) {
    if (p.weight_pct === null) continue;
    sums.set(p.asset_class, (sums.get(p.asset_class) ?? 0) + p.weight_pct);
    total += p.market_value ?? 0;
  }

  const segments: AllocationSegment[] = CLASS_META.filter((c) =>
    sums.has(c.key),
  ).map((c) => ({
    key: c.key,
    label: c.label,
    pct: sums.get(c.key)!,
    colorClass: c.colorClass,
  }));
  for (const [key, pct] of sums) {
    if (!CLASS_META.some((c) => c.key === key)) {
      segments.push({ key, label: key, pct, colorClass: "bg-steady" });
    }
  }

  return (
    <SceneShell scene="allocation">
      <div className="w-full">
        <SceneHeading index="IV" title="Portfolio allocation" />
        <h2 className="font-display text-2xl text-ink">
          How the portfolio is deployed
        </h2>
        <div className="mt-8">
          <AllocationBand segments={segments} />
        </div>
        <p className="mt-6 font-data text-xs text-ink-faint">
          {positions.length} positions · {fmtMoney(total)} at market
        </p>
      </div>
    </SceneShell>
  );
}
