import { motion } from "framer-motion";

export interface AllocationSegment {
  key: string;
  label: string;
  pct: number;
  colorClass: string;
}

/**
 * Proportional ink-wash band: identity comes from the direct labels beneath,
 * darkness steps with the band order. Segments grow into place once, on entry
 * (scroll-triggered, never autoplaying).
 */
export function AllocationBand({ segments }: { segments: AllocationSegment[] }) {
  return (
    <div>
      <div className="flex h-16 w-full gap-[2px] overflow-hidden rounded-sm">
        {segments.map((s, i) => (
          <motion.div
            key={s.key}
            className={s.colorClass}
            initial={{ width: 0 }}
            whileInView={{ width: `${s.pct}%` }}
            viewport={{ once: true, amount: 0.5 }}
            transition={{
              duration: 0.7,
              delay: i * 0.15,
              ease: [0.22, 1, 0.36, 1],
            }}
          />
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2">
        {segments.map((s) => (
          <p key={s.key} className="flex items-baseline gap-2">
            <span
              className={`inline-block size-2.5 self-center rounded-[2px] ${s.colorClass}`}
              aria-hidden="true"
            />
            <span className="text-sm text-ink-muted">{s.label}</span>
            <span className="font-data text-sm text-ink">
              {s.pct.toFixed(1)}%
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}
