"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { KalshiEvent, KalshiMarket } from "@/lib/types";
import { getMarkets } from "@/lib/api";

interface Props {
  event: KalshiEvent;
  index: number;
  onForecast: (e: KalshiEvent) => void;
}

function categoryAccent(category: string): string {
  const c = category.toLowerCase();
  if (c.includes("polit") || c.includes("elect") || c.includes("govern")) return "#5b9cf6";
  if (c.includes("crypto") || c.includes("bitcoin") || c.includes("coin") || c.includes("eth")) return "#f59e0b";
  if (c.includes("sport") || c.includes("nba") || c.includes("nfl") || c.includes("mlb") || c.includes("soccer")) return "#4ade80";
  if (c.includes("econ") || c.includes("financ") || c.includes("fed") || c.includes("rate")) return "#a78bfa";
  if (c.includes("tech") || c.includes("ai") || c.includes("sci")) return "#2dd4bf";
  if (c.includes("weather") || c.includes("climate")) return "#7dd3fc";
  if (c.includes("entertain") || c.includes("award") || c.includes("oscar") || c.includes("music")) return "#f472b6";
  return "#e36438";
}

function priceColor(p: number): string {
  if (p >= 0.65) return "#4ade80";
  if (p <= 0.35) return "#f87171";
  return "#9b9790";
}

export default function MarketCard({ event, index, onForecast }: Props) {
  const accent = categoryAccent(event.category ?? "");
  const [markets, setMarkets] = useState<KalshiMarket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      getMarkets(event.event_ticker)
        .then((m: KalshiMarket[]) => { setMarkets(m); setLoading(false); })
        .catch(() => setLoading(false));
    }, index * 60);
    return () => clearTimeout(t);
  }, [event.event_ticker, index]);

  const isBinary = markets.length === 1;
  const shown    = markets.slice(0, 2);
  const extra    = Math.max(0, markets.length - 2);

  return (
    <motion.button
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.04, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ y: -3, transition: { duration: 0.18 } }}
      onClick={() => onForecast(event)}
      style={{
        width: "100%", textAlign: "left",
        background: "rgba(18,18,18,0.98)",
        border: "1px solid #272727",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "14px", padding: "18px 20px",
        position: "relative", overflow: "hidden",
        transition: "border-color 0.2s, box-shadow 0.2s",
        cursor: "pointer",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = `0 0 0 1px ${accent}18, 0 12px 40px rgba(0,0,0,0.7)`;
        e.currentTarget.style.borderColor = `${accent}55`;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = "none";
        e.currentTarget.style.borderColor = "#272727";
      }}
    >
      {/* Category pill */}
      {event.category && (
        <div style={{ marginBottom: "10px" }}>
          <span style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px",
            fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.14em",
            color: accent, border: `1px solid ${accent}33`,
            borderRadius: "4px", padding: "2px 7px",
          }}>
            {event.category}
          </span>
        </div>
      )}

      {/* Title */}
      <div style={{
        fontSize: "14px", fontWeight: 600, color: "#ede9e3",
        lineHeight: 1.45, marginBottom: "14px",
      }}>
        {event.title}
      </div>

      {/* Market prices */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {[1, 2].map(n => (
            <div key={n} style={{
              height: "14px", borderRadius: "3px",
              background: "rgba(255,255,255,0.03)",
              width: n === 1 ? "80%" : "60%",
            }} />
          ))}
        </div>
      ) : markets.length === 0 ? null : (
        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          {isBinary ? (
            <>
              <PriceLine label="Yes" price={shown[0].mid_price} />
              <PriceLine label="No"  price={1 - shown[0].mid_price} />
            </>
          ) : (
            <>
              {shown.map(m => (
                <PriceLine
                  key={m.ticker}
                  label={m.yes_sub_title || "Yes"}
                  price={m.mid_price}
                />
              ))}
              {extra > 0 && (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                  color: "#3a3835", marginTop: "2px",
                }}>
                  +{extra} more
                </div>
              )}
            </>
          )}
        </div>
      )}
    </motion.button>
  );
}

function PriceLine({ label, price }: { label: string; price: number }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span style={{
        fontSize: "11px", color: "#6b6865",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        maxWidth: "68%",
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: "var(--font-mono), monospace", fontSize: "11px",
        fontWeight: 600, color: priceColor(price), flexShrink: 0,
      }}>
        {(price * 100).toFixed(0)}%
      </span>
    </div>
  );
}
