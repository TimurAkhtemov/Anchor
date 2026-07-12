import type { Source } from "@/lib/types";

/** Hairline-bordered state chip: "Rates — steady". */
export function StateChip({ label, state }: { label: string; state: string }) {
  return (
    <span className="inline-flex items-baseline gap-2 rounded-full border border-rule bg-paper-raised px-4 py-1.5 font-data text-[0.75rem] uppercase tracking-[0.12em]">
      <span className="text-ink-muted">{label}</span>
      <span className="text-ink">{state}</span>
    </span>
  );
}

/** Figure chip: a number the narration cites, verbatim. */
export function FigureChip({ figure }: { figure: string }) {
  return (
    <span className="inline-block rounded bg-pencil-wash px-2 py-0.5 font-data text-[0.75rem] text-pencil">
      {figure}
    </span>
  );
}

/** Attributed headline chip — the audit trail made visible. */
export function HeadlineChip({ source }: { source: Source }) {
  return (
    <span className="block max-w-md rounded border border-rule bg-paper-raised px-3 py-2 text-left">
      <span className="block font-display text-[0.9375rem] italic leading-snug text-ink">
        &ldquo;{source.title}&rdquo;
      </span>
      <span className="mt-1 block font-data text-[0.6875rem] uppercase tracking-[0.08em] text-ink-faint">
        {source.provider} · {source.pub_date}
      </span>
    </span>
  );
}
