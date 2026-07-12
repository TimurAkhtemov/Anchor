import { AnimatePresence, motion } from "framer-motion";
import { useTour } from "./TourContext";
import { FigureChip } from "./marks/Chip";

/**
 * The editor's margin notes: a blue-pencil rule with the active step's
 * narration beside it. Desktop renders it as a sticky side rail; mobile as a
 * bottom sheet. Advances only with the reader's scroll — never on its own.
 */
export function NarrationRail({ variant }: { variant: "rail" | "sheet" }) {
  const { model, activeStep, activeIndex } = useTour();
  const total = model.steps.length;

  const body = (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.div
        key={activeStep?.id ?? "idle"}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="border-l-2 border-pencil pl-4"
      >
        {activeStep ? (
          <>
            <p className="font-data text-[0.6875rem] uppercase tracking-[0.2em] text-pencil">
              ¶ {activeIndex} of {total}
            </p>
            <p
              className={`mt-2 font-display italic leading-relaxed text-ink ${
                variant === "rail" ? "text-[1.0625rem]" : "text-[0.9375rem]"
              }`}
            >
              {activeStep.narration}
            </p>
            {activeStep.figures.length > 0 && (
              <p className="mt-3 flex flex-wrap gap-1.5">
                {activeStep.figures.map((f) => (
                  <FigureChip key={f} figure={f} />
                ))}
              </p>
            )}
          </>
        ) : (
          <p className="font-display italic leading-relaxed text-ink-muted">
            Scroll to begin the reading.
          </p>
        )}
      </motion.div>
    </AnimatePresence>
  );

  if (variant === "sheet") {
    return (
      <div className="pointer-events-none border-t border-rule bg-paper-raised/95 px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-4 backdrop-blur-sm">
        {body}
      </div>
    );
  }
  return <div className="w-full">{body}</div>;
}
