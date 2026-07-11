import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtDate } from "@/lib/format";
import { SceneShell } from "../SceneShell";
import { useTour } from "../TourContext";

const STALE_AFTER_DAYS = 5;

/** The colophon: provenance, an honest staleness marker, and the plain-text
 *  fallback link. */
export function CodaScene() {
  const { model } = useTour();
  const briefing = model.bundle.briefing;

  // Staleness needs the reader's wall clock — computed after hydration so the
  // build-time HTML never disagrees with the first client render.
  const [staleDays, setStaleDays] = useState<number | null>(null);
  useEffect(() => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(briefing.as_of_date);
    if (!m) return;
    const asOf = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    setStaleDays(Math.floor((Date.now() - asOf) / 86_400_000));
  }, [briefing.as_of_date]);

  return (
    <SceneShell scene="coda">
      <div className="mx-auto w-full max-w-xl text-center">
        <div className="mx-auto mb-10 h-px w-24 bg-ink" />
        <p className="font-display text-2xl italic text-ink">
          End of the morning reading.
        </p>
        <p className="mt-6 font-data text-xs leading-relaxed text-ink-muted">
          Generated {fmtDate(briefing.generated_at)} · {briefing.model} via{" "}
          {briefing.provider} · {briefing.sources.length} headlines reviewed
        </p>
        {staleDays !== null && staleDays > STALE_AFTER_DAYS && (
          <p className="mt-3 font-data text-xs text-behind">
            Data as of {fmtDate(briefing.as_of_date)} — markets have moved
            since.
          </p>
        )}
        <p className="mt-10">
          <Link
            href="/text"
            className="font-display italic text-pencil underline decoration-1 underline-offset-4"
          >
            Read the briefing as plain text →
          </Link>
        </p>
      </div>
    </SceneShell>
  );
}
