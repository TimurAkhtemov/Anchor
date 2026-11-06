import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: the tour surface is a credential-free artifact consumer,
  // same posture as the committed parquet snapshot (docs/immersive_briefing_design.md).
  output: "export",
  // /text/ and /reading/ resolve on any static server (emits dir/index.html).
  trailingSlash: true,
};

export default nextConfig;
