import type { Metadata } from "next";
import "./globals.css";
import "./review.css";

export const metadata: Metadata = {
  title: "RDTII AutoExtract — Review Console",
  description:
    "Reviewer / audit UI for the RDTII digital-trade regulatory analysis engine. Verify or reject article-level findings for Pillars 6 & 7.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
