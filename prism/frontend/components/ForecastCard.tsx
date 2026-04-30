"use client";
import { motion } from "framer-motion";
import ProbabilityArc from "./ProbabilityArc";
import { SavedForecast } from "@/lib/types";

interface Props {
  forecast: SavedForecast;
  index: number;
  onSelect: (f: SavedForecast) => void;
  featured?: boolean;
}

function relTime(ts: string): string {
  try {
    const d = Date.now() - new Date(ts).getTime();
    const m = Math.floor(d / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return ""; }
}

function edgeInfo(edge: number): { label: string; color: string } {
  if (edge > 0.03)  return { label: `+${(edge * 100).toFixed(1)}pp`, color: "#5b9cf6" };
  if (edge < -0.03) return { label: `${(edge * 100).toFixed(1)}pp`,  color: "#f87171" };
  return { label: "~inline", color: "#3a3835" };
}

export default function ForecastCard({ forecast: f, index, onSelect, featured }: Props) {
  const fp   = f.forecaster_prob ?? 0;
  const kp   = f.kalshi_price ?? 0;
  const edge = edgeInfo(f.edge ?? 0);

  return (
    <motion.button
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -3, transition: { duration: 0.18 } }}
      onClick={() => onSelect(f)}
      style={{
        width: "100%", textAlign: "left", position: "relative", overflow: "hidden",
        background: featured ? "rgba(20,12,8,0.98)" : "rgba(15,15,15,0.95)",
        border: featured ? "1px solid rgba(227,100,56,0.18)" : "1px solid #1c1c1c",
        borderRadius: "14px",
        padding: featured ? "26px 24px" : "18px 20px",
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = featured ? "rgba(227,100,56,0.38)" : "rgba(227,100,56,0.22)";
        e.currentTarget.style.boxShadow = "0 12px 40px rgba(0,0,0,0.7)";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = featured ? "rgba(227,100,56,0.18)" : "#1c1c1c";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Featured: orange-to-blue top gradient line */}
      {featured && (
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: "2px",
          background: "linear-gradient(90deg, #e36438 0%, #5b9cf6 60%, transparent 100%)",
        }} />
      )}

      {f.category && (
        <div style={{
          fontFamily: "var(--font-mono), monospace", fontSize: "9px",
          fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em",
          color: "#e36438", marginBottom: "8px",
        }}>
          {f.category}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: featured ? "15px" : "13px", fontWeight: 600,
            color: "#ede9e3", lineHeight: 1.5,
            marginBottom: "12px",
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
          }}>
            {f.question}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#4a4845" }}>
              <span style={{ color: "#3a3835" }}>mkt </span>{(kp * 100).toFixed(1)}¢
            </span>
            <span style={{ color: "#1c1c1c" }}>·</span>
            <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", fontWeight: 600, color: edge.color }}>
              {edge.label}
            </span>
            <span style={{ color: "#1c1c1c" }}>·</span>
            <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#2a2826" }}>
              {relTime(f.created_at)}
            </span>
          </div>
        </div>
        <div style={{ flexShrink: 0 }}>
          <ProbabilityArc probability={fp} size={featured ? 88 : 70} />
        </div>
      </div>
    </motion.button>
  );
}
