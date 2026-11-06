"use client";

// The dashboard's single client boundary: owns the horizon and the cleared
// asset classes. Everything renders from the bundle prop, so the static HTML
// already holds the full 1 Month view before hydration.

import { useState } from "react";
import type { AnchorBundle, ReturnHorizon } from "@/lib/types";
import { HoldingsSection } from "./HoldingsSection";
import { MacroSection } from "./MacroSection";
import { Masthead } from "./Masthead";
import { SectorsSection } from "./SectorsSection";

export function Dashboard({ bundle }: { bundle: AnchorBundle }) {
  const [horizon, setHorizon] = useState<ReturnHorizon>("1m");
  const [cleared, setCleared] = useState<ReadonlySet<string>>(new Set());

  const toggleClass = (assetClass: string) =>
    setCleared((prev) => {
      const next = new Set(prev);
      if (!next.delete(assetClass)) next.add(assetClass);
      return next;
    });

  return (
    <main
      data-dashboard
      className="mx-auto w-full max-w-[1180px] px-4 pt-[22px] pb-12 text-[15px] leading-normal lg:px-10 lg:pt-[34px] lg:pb-16"
    >
      <Masthead bundle={bundle} horizon={horizon} onHorizon={setHorizon} />
      <MacroSection bundle={bundle} />
      <SectorsSection bundle={bundle} horizon={horizon} />
      <HoldingsSection
        bundle={bundle}
        horizon={horizon}
        cleared={cleared}
        onToggleClass={toggleClass}
        onResetClasses={() => setCleared(new Set())}
      />
    </main>
  );
}
