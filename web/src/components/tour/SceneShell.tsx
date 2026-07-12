import type { SceneKey } from "@/lib/types";
import { useTour } from "./TourContext";

/**
 * Generic scroll scene: a sticky full-viewport visual layer with the scene's
 * tour steps rendered as invisible, contiguous 100svh sentinels scrolling past
 * behind it. Scenes with no bound steps are one viewport tall and static —
 * any valid 6–12 step script renders without per-script layout code.
 */
export function SceneShell({
  scene,
  children,
}: {
  scene: SceneKey;
  children: React.ReactNode;
}) {
  const { model, registerSentinel } = useTour();
  const steps = model.steps.filter((s) => s.scene === scene);

  return (
    <section
      data-scene={scene}
      className="relative"
      style={{ height: `${Math.max(steps.length, 1) * 100}svh` }}
    >
      {/* pb reserves room for the mobile narration sheet; the rail owns that
          space on md+. */}
      <div className="sticky top-0 flex h-svh flex-col justify-center overflow-hidden pb-56 md:pb-0">
        {children}
      </div>
      {steps.length > 0 && (
        <div
          className="pointer-events-none absolute inset-0"
          aria-hidden="true"
        >
          {steps.map((s) => (
            <div
              key={s.id}
              data-step-sentinel={s.id}
              ref={registerSentinel(s.id)}
              className="h-svh"
            />
          ))}
        </div>
      )}
    </section>
  );
}

/** Small-caps section mark: the forced reading order is the product, so the
 *  numbering carries real information. */
export function SceneHeading({
  index,
  title,
}: {
  index: string;
  title: string;
}) {
  return (
    <p className="mb-6 font-data text-[0.6875rem] uppercase tracking-[0.2em] text-ink-faint">
      <span className="text-pencil">{index}</span>
      <span className="mx-2">·</span>
      {title}
    </p>
  );
}
