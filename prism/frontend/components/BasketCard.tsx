"use client";

import Link from "next/link";
import type { PredictionBasket, SavedBasket } from "@/lib/types";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTimeframe(value: string): string {
  // If it looks like an ISO date (YYYY-MM-DD or similar), format it
  if (/^\d{4}-\d{2}/.test(value)) {
    try {
      return new Date(value).toLocaleDateString("en-US", { month: "short", year: "numeric" });
    } catch {
      return value;
    }
  }
  return value;
}

function avatarColor(seed: number): string {
  const palette = ["#4f46e5", "#2563eb", "#16a34a", "#9333ea", "#d97706", "#0891b2", "#db2777"];
  return palette[seed % palette.length];
}

function modeLabel(mode: string): string {
  if (mode === "instant") return "Quick";
  if (mode === "thinking") return "Deep";
  return "Manual";
}

export function BasketCard({ basket }: { basket: SavedBasket }) {
  const parsed: PredictionBasket | null = (() => {
    try { return JSON.parse(basket.basket_json); } catch { return null; }
  })();
  const holdingsCount = parsed?.holdings?.length ?? 0;
  const quality = parsed?.basket_quality;
  const color = avatarColor(basket.id);

  return (
    <Link href={`/baskets/${basket.id}`} style={{ textDecoration: "none", display: "block" }}>
      <article style={{
        background: "#ffffff",
        border: "1px solid rgba(0,0,0,0.07)",
        borderRadius: 16,
        padding: "18px 20px",
        transition: "box-shadow 0.15s, border-color 0.15s",
        cursor: "pointer",
      }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 20px rgba(0,0,0,0.08)";
          (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.12)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = "none";
          (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.07)";
        }}
      >
        {/* Author row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div
            style={{ display: "flex", alignItems: "center", gap: 8 }}
            onClick={basket.username ? (e) => { e.preventDefault(); window.location.href = `/users/${basket.username}`; } : undefined}
          >
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: color,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <span style={{ color: "#fff", fontSize: 10, fontWeight: 700 }}>◈</span>
            </div>
            <div>
              <div style={{
                color: basket.username ? "#4f46e5" : "#1c1814",
                fontSize: 13, fontWeight: 600, lineHeight: 1.2,
                cursor: basket.username ? "pointer" : "default",
              }}>
                {basket.username ? `@${basket.username}` : "Prism"}
              </div>
              <div style={{ color: "#a8a29a", fontSize: 11, lineHeight: 1.2 }}>{timeAgo(basket.created_at)}</div>
            </div>
          </div>
          <span style={{
            fontFamily: "var(--font-mono), monospace",
            fontSize: 10,
            color: "#6e675f",
            border: "1px solid rgba(0,0,0,0.1)",
            borderRadius: 999,
            padding: "3px 8px",
            background: "rgba(0,0,0,0.04)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
          }}>
            {modeLabel(basket.mode)}
          </span>
        </div>

        {/* Title */}
        <div style={{
          color: "#1c1814",
          fontSize: 16,
          fontWeight: 600,
          lineHeight: 1.35,
          letterSpacing: "-0.01em",
          marginBottom: 8,
        }}>
          {basket.title}
        </div>

        {/* Summary */}
        <div style={{
          color: "#6e675f",
          fontSize: 13,
          lineHeight: 1.6,
          marginBottom: 14,
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
        }}>
          {basket.summary}
        </div>

        {/* Footer tags */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <span style={tagStyle}>{holdingsCount} positions</span>
          {(basket.timeframe_end || basket.time_horizon) && (
            <span style={tagStyle}>{formatTimeframe(basket.timeframe_end || basket.time_horizon)}</span>
          )}
          {quality && (
            <span style={{ ...tagStyle, color: "#6e675f" }}>{quality.replace(/_/g, " ")}</span>
          )}
        </div>
      </article>
    </Link>
  );
}

const tagStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 8px",
  borderRadius: 999,
  border: "1px solid rgba(0,0,0,0.08)",
  color: "#9b9390",
  fontSize: 11,
  background: "rgba(0,0,0,0.03)",
};
