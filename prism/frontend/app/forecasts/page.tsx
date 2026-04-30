"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import ForecastCard from "@/components/ForecastCard";
import { listForecasts } from "@/lib/api";
import type { SavedForecast } from "@/lib/types";

export default function ForecastsPage() {
  const router = useRouter();
  const [forecasts, setForecasts] = useState<SavedForecast[]>([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    listForecasts(100)
      .then(f => { setForecasts(f); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const goForecast = (f: SavedForecast) =>
    router.push(`/market/${f.ticker}?saved=${f.id}`);

  const byCategory = forecasts.reduce<Record<string, SavedForecast[]>>((acc, f) => {
    const cat = f.category || "Other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(f);
    return acc;
  }, {});

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "80px 32px 80px" }}>

        {/* Page title */}
        <div style={{ marginBottom: "40px" }}>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.2em", color: "#5b9cf6", marginBottom: "8px",
          }}>
            <span className="blink" style={{ fontSize: "7px", marginRight: "8px", animationDelay: "0.7s" }}>●</span>
            Forecast Reports
          </div>
          <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em" }}>
            All Forecasts
          </h1>
        </div>

        {loading && (
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#2a2826" }}>
            Loading…
          </div>
        )}

        {!loading && forecasts.length === 0 && (
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#2a2826" }}>
            No forecasts yet. Run one from the Markets page.
          </div>
        )}

        {/* Grouped by category */}
        {Object.entries(byCategory).map(([cat, items]) => (
          <div key={cat} style={{ marginBottom: "48px" }}>
            <div style={{
              fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.18em", color: "#9b9790",
              marginBottom: "12px", paddingBottom: "10px", borderBottom: "1px solid #1e1e1e",
              display: "flex", alignItems: "center", gap: "10px",
            }}>
              <span style={{ color: "#e36438", fontSize: "7px" }}>●</span>
              {cat}
              <span style={{ color: "#2a2826" }}>({items.length})</span>
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: "10px",
            }}>
              {items.map((f, i) => (
                <ForecastCard key={f.id} forecast={f} index={i} onSelect={goForecast} featured={i === 0 && items === forecasts.slice(0, items.length)} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
