"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";
import Header from "@/components/Header";
import ForecastCard from "@/components/ForecastCard";
import { listForecasts } from "@/lib/api";
import type { SavedForecast } from "@/lib/types";

export default function AllForecastsPage() {
  const router = useRouter();
  const supabase = createClient();
  const [forecasts, setForecasts] = useState<SavedForecast[]>([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      listForecasts(100, token)
        .then(f => { setForecasts(f); setLoading(false); })
        .catch(() => setLoading(false));
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
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

        <div style={{ marginBottom: "40px" }}>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.2em", color: "#5b9cf6", marginBottom: "8px",
            display: "flex", alignItems: "center", gap: "8px",
          }}>
            <span className="blink" style={{ fontSize: "7px", animationDelay: "0.7s" }}>●</span>
            Forecast Reports
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em" }}>
              All Reports
            </h1>
            <a
              href="/forecasts"
              style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                fontWeight: 600, letterSpacing: "0.08em",
                color: "#3a3835", textDecoration: "none",
                transition: "color 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "#6b6865"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "#3a3835"; }}
            >
              ← Intel
            </a>
          </div>
        </div>

        {loading && (
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#2a2826" }}>
            Loading…
          </div>
        )}

        {!loading && forecasts.length === 0 && (
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#2a2826" }}>
            No forecasts yet. Run one from the Intel page.
          </div>
        )}

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
                <ForecastCard key={f.id} forecast={f} index={i} onSelect={goForecast} featured={i === 0} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
