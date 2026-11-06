import type { RelativeLabel } from "@/lib/types";

/** Colour for an absolute return: its sign, blue above zero, bronze below. */
export function returnTone(v: number | null): string {
  if (v === null || v === 0) return "";
  return v > 0 ? "text-ahead" : "text-behind";
}

/** Colour for a comparison: its label, so a value inside the band never reads
 *  as ahead or behind. */
export const LABEL_TONE: Record<RelativeLabel, string> = {
  ahead: "text-ahead",
  behind: "text-behind",
  in_line: "text-ink-muted",
};
