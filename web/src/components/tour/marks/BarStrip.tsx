import { scaleBand, scaleLinear } from "@visx/scale";
import { motion } from "framer-motion";

export interface BarDatum {
  key: string;
  label: string;
  value: number | null;
  emphasis: "active" | "dim" | "rest";
}

/**
 * Diverging bar strip: one ink hue for all bars (a single nominal series —
 * length carries the value, direction carries the sign), the spotlit bar in
 * blue pencil. Bars re-scale smoothly when the step changes the horizon.
 */
export function BarStrip({
  data,
  formatValue,
  ariaLabel,
}: {
  data: BarDatum[];
  formatValue: (v: number) => string;
  ariaLabel: string;
}) {
  const W = 720;
  const H = 250;
  const PAD_X = 6;
  const PAD_TOP = 30;
  const PAD_BOTTOM = 26;

  const x = scaleBand<string>({
    domain: data.map((d) => d.key),
    range: [PAD_X, W - PAD_X],
    padding: 0.45,
  });
  const values = data
    .map((d) => d.value)
    .filter((v): v is number => v !== null);
  const maxAbs = Math.max(1, ...values.map(Math.abs));
  const y = scaleLinear<number>({
    domain: [-maxAbs, maxAbs],
    range: [H - PAD_BOTTOM, PAD_TOP],
  });
  const zero = y(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={ariaLabel}>
      <line
        x1={PAD_X}
        x2={W - PAD_X}
        y1={zero}
        y2={zero}
        className="stroke-rule"
        strokeWidth={1}
      />
      {data.map((d) => {
        const bx = x(d.key) ?? 0;
        const bw = x.bandwidth();
        const cx = bx + bw / 2;
        if (d.value === null) {
          return (
            <text
              key={d.key}
              x={cx}
              y={zero - 6}
              textAnchor="middle"
              fontSize={11}
              className="fill-ink-faint font-data"
            >
              —
            </text>
          );
        }
        const vy = y(d.value);
        const top = Math.min(vy, zero);
        const height = Math.max(Math.abs(vy - zero), 2);
        const active = d.emphasis === "active";
        return (
          <g key={d.key} data-active={active || undefined}>
            <motion.rect
              x={bx}
              width={bw}
              rx={3}
              initial={false}
              animate={{
                y: top,
                height,
                opacity: d.emphasis === "dim" ? 0.3 : 1,
              }}
              transition={{ type: "spring", stiffness: 170, damping: 26 }}
              className={active ? "fill-pencil" : "fill-bar"}
            >
              <title>{`${d.label} ${formatValue(d.value)}`}</title>
            </motion.rect>
            {active && (
              <motion.text
                initial={false}
                animate={{ y: d.value >= 0 ? top - 8 : top + height + 16 }}
                x={cx}
                textAnchor="middle"
                fontSize={12}
                className="fill-ink font-data"
              >
                {formatValue(d.value)}
              </motion.text>
            )}
            <text
              x={cx}
              y={H - 8}
              textAnchor="middle"
              fontSize={10}
              className={`font-data ${active ? "fill-ink" : "fill-ink-muted"}`}
            >
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
