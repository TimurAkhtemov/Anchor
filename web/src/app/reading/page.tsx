import type { Metadata } from "next";
import Link from "next/link";
import { Tour } from "@/components/tour/Tour";
import { loadBundle } from "@/lib/bundle";
import { buildTourModel } from "@/lib/resolve";

export const metadata: Metadata = {
  title: "Anchor — Guided Reading",
};

// Server Component: the bundle is read and resolved once, at build time
// (output: 'export'), and ships to the client as precomputed props.
export default function Reading() {
  const bundle = loadBundle();
  if (!bundle.briefing) {
    return (
      <main className="mx-auto w-full max-w-2xl px-5 py-16">
        <p className="font-display text-[1.0625rem] text-ink">
          No guided reading is available for the latest market date.
        </p>
        <p className="mt-4">
          <Link href="/" className="font-display italic text-pencil underline">
            ← Back to the dashboard
          </Link>
        </p>
      </main>
    );
  }
  const model = buildTourModel({ ...bundle, briefing: bundle.briefing });
  return (
    <main>
      <Tour model={model} />
    </main>
  );
}
