import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter, Inter_Tight } from "next/font/google";

import { AuthProvider } from "@/components/auth-provider";

import "./globals.css";

/**
 * Three typefaces, each with a job:
 *   Inter        — body and UI, excellent at small sizes
 *   Inter Tight  — headings, tighter fit so large text holds together
 *   IBM Plex Mono — figures, scores and code, properly tabular
 *
 * Self-hosted by next/font at build time, so no external requests at runtime
 * and no layout shift from a late-loading webfont.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  display: "swap",
  weight: ["500", "600", "700"],
  variable: "--font-display",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "JobMatch — Resume-matched job discovery",
  description:
    "Upload a resume once and discover, rank and track matching jobs across multiple job platforms, with an explainable match score.",
};

export const viewport: Viewport = {
  themeColor: "#0a0b0e",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${interTight.variable} ${plexMono.variable}`}
    >
      <body className="min-h-screen bg-ink-950 font-sans text-ink-100 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
