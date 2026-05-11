"use client";

import Link from "next/link";
import type { PredictionBasket, SavedBasket } from "@/lib/types";

function modeLabel(mode: string): string {
  if (mode === "instant") return "Quick Build";
  if (mode === "thinking") return "Deep Build";
  return "Manual";
}

function qualityLabel(quality?: PredictionBasket["basket_quality"]): string {
  switch (quality) {
    case "direct": return "Direct";
    case "strong_proxy": return "Strong proxy";
    case "mixed_proxy": return "Mixed proxy";
    case "thin_market_coverage": return "Thin coverage";
    default: return "";
  }
}

export function BasketCard({ basket }: { basket: SavedBasket }) {
  const parsed: PredictionBasket | null = (() => {
    try { return JSON.parse(basket.basket_json); } catch { return null; }
  })();
  const holdingsCount = parsed?.holdings?.length ?? 0;
  const quality = parsed?.basket_quality;
  const qualityText = qualityLabel(quality);

  return (
    <Link href={`/baskets/${basket.id}`} style={{ textDecoration: "none", display: "block", height: "100%" }}>
      <div style={{
        background: "linear-gradient(180deg, rgba(18,18,18,0.97), rgba(12,12,12,0.98))",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 20,
        padding: 20,
        height: "100%",
        boxSizing: "border-box",
        display: "grid",
        gridTemplateRows: "auto 1fr auto",
        gap: 10,
      }}>
        <div>
          <div style={{
            color: "#e36438",
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: "0.14em",
            fontFamily: "var(--font-mono), monospace",
            marginBottom: 8,
          }}>
            {modeLabel(basket.mode)}
          </div>
          <div style={{
            color: "#ede9e3",
            fontSize: 17,
            fontWeight: 600,
            lineHeight: 1.3,
            letterSpacing: "-0.02em",
          }}>
            {basket.title}
          </div>
        </div>

        <div style={{
          color: "#948c84",
          fontSize: 13,
          lineHeight: 1.6,
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
        }}>
          {basket.summary}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
          <span style={tagStyle}>{holdingsCount} positions</span>
          {(basket.timeframe_end || basket.time_horizon) && (
            <span style={tagStyle}>{basket.timeframe_end || basket.time_horizon}</span>
          )}
          {qualityText && <span style={tagStyle}>{qualityText}</span>}
        </div>
      </div>
    </Link>
  );
}

const tagStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "4px 8px",
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,0.08)",
  color: "#a09890",
  fontSize: 11,
  background: "rgba(255,255,255,0.03)",
};
