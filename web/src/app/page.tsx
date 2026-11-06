import type { Metadata } from "next";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { loadBundle } from "@/lib/bundle";

export const metadata: Metadata = {
  title: "Anchor — Morning Briefing",
};

// Server Component: the bundle is read once at build time (output: 'export').
export default function Home() {
  return <Dashboard bundle={loadBundle()} />;
}
