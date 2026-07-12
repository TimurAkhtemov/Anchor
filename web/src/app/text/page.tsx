import type { Metadata } from "next";
import Link from "next/link";
import { fmtDate } from "@/lib/format";
import type { AnchorBundle } from "@/lib/types";
import bundleJson from "../../../public/data/anchor.json";

// The accessibility/honesty fallback: the same briefing as plain paragraphs.
// briefing_md is assembled from step narrations upstream — plain text with
// \n\n paragraph breaks, no markdown to parse.

const bundle = bundleJson as unknown as AnchorBundle;

export const metadata: Metadata = {
  title: "Anchor — Briefing (plain text)",
};

export default function TextBriefing() {
  const briefing = bundle.briefing;
  const paragraphs = briefing.briefing_md
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <main className="mx-auto max-w-2xl px-5 py-16">
      <header className="border-b border-ink pb-3">
        <p className="font-data text-[0.6875rem] uppercase tracking-[0.25em] text-ink">
          Anchor · Morning Briefing
        </p>
        <p className="mt-1 font-data text-[0.6875rem] uppercase tracking-[0.15em] text-ink-muted">
          {fmtDate(briefing.as_of_date)} · plain-text edition
        </p>
      </header>

      <section className="mt-8 space-y-5">
        {paragraphs.map((p, i) => (
          <p key={i} className="font-display text-[1.0625rem] leading-relaxed text-ink">
            {p}
          </p>
        ))}
      </section>

      <section className="mt-12">
        <h2 className="font-data text-[0.6875rem] uppercase tracking-[0.2em] text-ink-muted">
          Headlines reviewed
        </h2>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5">
          {briefing.sources.map((s) => (
            <li key={`${s.ticker}-${s.title}`} className="text-sm leading-snug">
              <span className="text-ink">{s.title}</span>{" "}
              <span className="font-data text-xs text-ink-faint">
                — {s.provider}, {s.pub_date} ({s.ticker})
              </span>
            </li>
          ))}
        </ol>
      </section>

      <footer className="mt-12 border-t border-rule pt-5">
        <p className="font-data text-xs text-ink-muted">
          Generated {fmtDate(briefing.generated_at)} · {briefing.model} via{" "}
          {briefing.provider}
        </p>
        <p className="mt-4">
          <Link
            href="/"
            className="font-display italic text-pencil underline decoration-1 underline-offset-4"
          >
            ← Back to the guided tour
          </Link>
        </p>
      </footer>
    </main>
  );
}
