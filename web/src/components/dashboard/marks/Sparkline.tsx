import type { TrendSeries } from "@/lib/types";

const WIDTH = 110;

// Rebased to the first point so a holding and its benchmark share one scale.
function rebase(series: TrendSeries): number[] {
  const base = series[0][1];
  return series.map(([, v]) => (base ? v / base - 1 : v));
}

/** Inline-SVG trend line, optionally overlaid with a dashed benchmark. Draws
 *  nothing below two points, at the same height so rows stay aligned. */
export function Sparkline({
  series,
  overlay,
  height = 34,
  colorClass = "text-ink",
}: {
  series: TrendSeries;
  overlay?: TrendSeries;
  height?: number;
  colorClass?: string;
}) {
  if (series.length < 2) {
    return <svg width="100%" height={height} aria-hidden="true" />;
  }

  const line = rebase(series);
  const under = overlay && overlay.length > 1 ? rebase(overlay) : null;
  const all = under ? line.concat(under) : line;
  const lo = Math.min(...all);
  const range = Math.max(...all) - lo;

  const path = (values: number[]) =>
    values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * (WIDTH - 2) + 1;
        const y =
          range === 0
            ? height / 2
            : height - 2 - ((v - lo) / range) * (height - 4);
        return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join("");

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      aria-hidden="true"
      className={`block ${colorClass}`}
    >
      {under && (
        <path
          d={path(under)}
          fill="none"
          stroke="var(--color-ink-faint)"
          strokeWidth={1.2}
          strokeDasharray="2 2"
          vectorEffect="non-scaling-stroke"
        />
      )}
      <path
        d={path(line)}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
