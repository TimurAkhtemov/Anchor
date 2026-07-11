"use client";

// The single client boundary: everything below hydrates; the TourModel
// arrives fully resolved from the build-time Server Component.

import { MotionConfig } from "framer-motion";
import type { TourModel } from "@/lib/types";
import { NarrationRail } from "./NarrationRail";
import { TourProvider, useTour } from "./TourContext";
import { AllocationScene } from "./scenes/AllocationScene";
import { CodaScene } from "./scenes/CodaScene";
import { HeroScene } from "./scenes/HeroScene";
import { HoldingsScene } from "./scenes/HoldingsScene";
import { MacroScene } from "./scenes/MacroScene";
import { SectorsScene } from "./scenes/SectorsScene";

export function Tour({ model }: { model: TourModel }) {
  return (
    // reducedMotion="user": prefers-reduced-motion drops transforms/layout
    // animation while opacity states (spotlight/dim) stay fully legible.
    <MotionConfig reducedMotion="user">
      <TourProvider model={model}>
        <TourBody />
      </TourProvider>
    </MotionConfig>
  );
}

function TourBody() {
  const { activeStep } = useTour();
  return (
    <div data-active-step={activeStep?.id ?? ""}>
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-x-14 px-5 md:grid-cols-[minmax(0,1fr)_21rem] md:px-10">
        <div className="pb-16 md:pb-0">
          <HeroScene />
          <MacroScene />
          <SectorsScene />
          <AllocationScene />
          <HoldingsScene />
          <CodaScene />
        </div>
        <aside className="hidden md:block">
          <div className="sticky top-0 flex h-svh items-center">
            <NarrationRail variant="rail" />
          </div>
        </aside>
      </div>
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 md:hidden">
        <NarrationRail variant="sheet" />
      </div>
    </div>
  );
}
