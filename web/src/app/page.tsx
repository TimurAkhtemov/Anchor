import { Tour } from "@/components/tour/Tour";
import { buildTourModel } from "@/lib/resolve";
import { loadBundle } from "@/lib/bundle";

// Server Component: the bundle is read and resolved once, at build time
// (output: 'export'), and ships to the client as precomputed props.
export default function Home() {
  const bundle = loadBundle();
  // The briefing is null when stale or missing; the dashboard (next task)
  // replaces this fallback.
  if (!bundle.briefing) {
    return (
      <main className="mx-auto max-w-2xl px-5 py-16">
        <h1 className="font-display text-2xl">{bundle.macro_regime.regime_summary}</h1>
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
