"use client";
import { motion } from "framer-motion";
import { KalshiEvent } from "@/lib/types";

interface Props {
  event: KalshiEvent;
  index: number;
  onSelect: (e: KalshiEvent) => void;
}

export default function MarketCard({ event, index, onSelect }: Props) {
  return (
    <motion.button
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.04, ease: [0.16, 1, 0.3, 1] }}
      onClick={() => onSelect(event)}
      style={{
        width: "100%", textAlign: "left",
        background: "rgba(15,15,15,0.95)", border: "1px solid #1c1c1c",
        borderRadius: "14px", padding: "20px 22px",
        position: "relative", overflow: "hidden",
        transition: "border-color 0.2s, box-shadow 0.2s, transform 0.2s",
      }}
      whileHover={{ y: -3, transition: { duration: 0.18 } }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = "rgba(227,100,56,0.28)";
        e.currentTarget.style.boxShadow = "0 0 0 1px rgba(227,100,56,0.08), 0 12px 40px rgba(0,0,0,0.7)";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = "#1c1c1c";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Top spectral line — shows on hover via JS since we can't use CSS group */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: "1px",
        background: "linear-gradient(90deg, transparent 0%, rgba(227,100,56,0.6) 40%, rgba(91,156,246,0.4) 70%, transparent 100%)",
        opacity: 0, transition: "opacity 0.2s",
      }} />

      {event.category && (
        <div style={{
          fontFamily: "var(--font-mono), monospace", fontSize: "9px",
          fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em",
          color: "#e36438", marginBottom: "10px",
        }}>
          {event.category}
        </div>
      )}

      <div style={{
        fontSize: "14px", fontWeight: 600, color: "#ede9e3",
        lineHeight: 1.5, marginBottom: event.sub_title ? "8px" : "16px",
      }}>
        {event.title}
      </div>

      {event.sub_title && (
        <div style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.45, marginBottom: "16px" }}>
          {event.sub_title}
        </div>
      )}

      <div style={{
        fontFamily: "var(--font-mono), monospace", fontSize: "10px",
        color: "#3a3835", display: "flex", alignItems: "center", gap: "6px",
      }}>
        <span style={{ color: "#e36438" }}>→</span> explore
      </div>
    </motion.button>
  );
}
