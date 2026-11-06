import fs from "node:fs";
import path from "node:path";
import type { AnchorBundle } from "./types";

/** Reads the committed bundle at build time (Server Components only).
 *  ANCHOR_BUNDLE_PATH overrides the path, e.g. for a local private bundle. */
export function loadBundle(): AnchorBundle {
  const file =
    process.env.ANCHOR_BUNDLE_PATH ??
    path.join(process.cwd(), "public", "data", "anchor.json");
  return JSON.parse(fs.readFileSync(file, "utf8")) as AnchorBundle;
}
