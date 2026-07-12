import type { Metadata, Viewport } from "next";
import { Geist_Mono, Newsreader, Public_Sans } from "next/font/google";
import "./globals.css";

// Newsreader: a face designed for on-screen news reading — the display voice
// of the morning-paper identity. Public Sans carries body/UI; Geist Mono
// carries figures (tickers, percentages, datelines).
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

const publicSans = Public_Sans({
  variable: "--font-public-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Anchor — Morning Briefing",
  description:
    "A guided reading of the day's portfolio context: macro environment, then sectors, then holdings.",
};

export const viewport: Viewport = {
  themeColor: "#f9f5ec",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${publicSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
