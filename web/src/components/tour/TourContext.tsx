"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ResolvedStep, TourModel } from "@/lib/types";

interface TourContextValue {
  model: TourModel;
  activeStep: ResolvedStep | null;
  /** 1-based position of the active step in the script, for "¶ k of N". */
  activeIndex: number;
  registerSentinel: (id: number) => (el: HTMLDivElement | null) => void;
}

const TourContext = createContext<TourContextValue | null>(null);

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used inside <TourProvider>");
  return ctx;
}

export function TourProvider({
  model,
  children,
}: {
  model: TourModel;
  children: React.ReactNode;
}) {
  // null until hydration + first intersection: the prerendered HTML shows
  // every scene undimmed, so there is no hydration mismatch or flash.
  const [activeStepId, setActiveStepId] = useState<number | null>(null);
  const elems = useRef(new Map<number, Element>());
  const inBand = useRef(new Set<number>());
  const observer = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    // A sentinel is "active" while it overlaps the middle 10% of the viewport.
    // Sentinels are contiguous 100svh blocks, so at most one occupies the band;
    // boundary frames resolve to the earlier step via Math.min.
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = Number(
            (entry.target as HTMLElement).dataset.stepSentinel,
          );
          if (entry.isIntersecting) inBand.current.add(id);
          else inBand.current.delete(id);
        }
        // Sticky at the edges: past the last sentinel (the coda) the rail
        // keeps the last step's narration rather than going blank.
        if (inBand.current.size > 0) {
          setActiveStepId(Math.min(...inBand.current));
        }
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    );
    observer.current = obs;
    elems.current.forEach((el) => obs.observe(el));
    return () => {
      obs.disconnect();
      observer.current = null;
    };
  }, []);

  const registerSentinel = useCallback(
    (id: number) => (el: HTMLDivElement | null) => {
      const prev = elems.current.get(id);
      if (prev) observer.current?.unobserve(prev);
      if (el) {
        elems.current.set(id, el);
        observer.current?.observe(el);
      } else {
        elems.current.delete(id);
        inBand.current.delete(id);
      }
    },
    [],
  );

  const activeStep = useMemo(
    () => model.steps.find((s) => s.id === activeStepId) ?? null,
    [model, activeStepId],
  );
  const activeIndex = activeStep ? model.steps.indexOf(activeStep) + 1 : 0;

  const value = useMemo(
    () => ({ model, activeStep, activeIndex, registerSentinel }),
    [model, activeStep, activeIndex, registerSentinel],
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}
