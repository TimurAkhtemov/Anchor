import { Tour } from "@/components/tour/Tour";
import { buildTourModel } from "@/lib/resolve";
import type { AnchorBundle } from "@/lib/types";
import bundleJson from "../../public/data/anchor.json";

// Server Component: the committed bundle is read and resolved once, at build
// time (output: 'export'), and ships to the client as precomputed props.
// The double cast is deliberate — TS widens JSON literals (e.g. benchmark_type
// infers as string), so the union-typed AnchorBundle won't assign directly.
const bundle = bundleJson as unknown as AnchorBundle;

export default function Home() {
  const model = buildTourModel(bundle);
  return (
    <main>
      <Tour model={model} />
    </main>
  );
}
