import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Angles — Prediction market portfolios",
  description: "Explore, build, and trade thematic baskets of prediction markets.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "var(--font-jakarta), system-ui, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
