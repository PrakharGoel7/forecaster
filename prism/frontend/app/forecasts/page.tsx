"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@clerk/nextjs";
import Header from "@/components/Header";
import MarketCard from "@/components/MarketCard";
import { listForecasts, searchEvents } from "@/lib/api";
import type { SavedForecast, KalshiEvent } from "@/lib/types";

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

function edgeColor(edge: number) {
  if (edge > 0.03)  return "#5b9cf6";
  if (edge < -0.03) return "#f87171";
  return "#3a3835";
}

export default function IntelPage() {
  const router = useRouter();
  const { getToken, isLoaded, userId } = useAuth();

  const [query, setQuery]         = useState("");
  const [events, setEvents]       = useState<KalshiEvent[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched]   = useState(false);
  const [searchError, setSearchError] = useState("");

  const [forecasts, setForecasts]           = useState<SavedForecast[]>([]);
  const [forecastsLoading, setForecastsLoading] = useState(true);

  useEffect(() => {
    setSearching(true);
    searchEvents("", 48)
      .then(e => { setEvents(e); setSearching(false); })
      .catch(() => setSearching(false));
  }, []);

  useEffect(() => {
    if (!isLoaded) return;
    (async () => {
      const token = userId ? await getToken().catch(() => null) : null;
      listForecasts(100, token ?? undefined)
        .then(f => { setForecasts(f); setForecastsLoading(false); })
        .catch(() => setForecastsLoading(false));
    })();
  }, [isLoaded, userId]);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true); setSearchError("");
    try {
      setEvents(await searchEvents(query, 48));
      setSearched(true);
    } catch (e: unknown) {
      setSearchError(e instanceof Error ? e.message : "Search failed");
    } finally { setSearching(false); }
  }, [query]);

  const clearSearch = () => {
    setQuery(""); setSearched(false); setSearchError("");
    setSearching(true);
    searchEvents("", 48).then(e => { setEvents(e); setSearching(false); }).catch(() => setSearching(false));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") runSearch();
    if (e.key === "Escape") clearSearch();
  };

  const goRunForecast = (event: KalshiEvent) =>
    router.push(`/market/${event.event_ticker}?title=${encodeURIComponent(event.title)}&cat=${encodeURIComponent(event.category)}&sub=${encodeURIComponent(event.sub_title)}&runForecast=1`);

  const goForecast = (f: SavedForecast) =>
    router.push(`/market/${f.ticker}?saved=${f.id}`);

  const showStrip = !forecastsLoading && forecasts.length > 0;

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />

      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "80px 32px 80px" }}>

        {/* Page header */}
        <div style={{ marginBottom: "28px" }}>
          <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em" }}>
            Intel
          </h1>
        </div>

        {/* Search bar */}
        <div style={{
          display: "flex", gap: "8px", marginBottom: "24px",
          background: "rgba(14,14,14,0.95)", border: "1px solid #282828",
          borderRadius: "12px", padding: "6px 6px 6px 18px",
          boxShadow: "0 0 0 1px rgba(255,255,255,0.02)",
        }}>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search markets — Bitcoin, elections, Fed, AI…"
            style={{
              flex: 1, background: "transparent", border: "none",
              fontSize: "13px", color: "#ede9e3", outline: "none",
              fontFamily: "var(--font-jakarta), system-ui, sans-serif",
            }}
          />
          {searched && (
            <button onClick={clearSearch} style={{
              background: "transparent", color: "#3a3835", border: "none",
              padding: "8px 12px", fontSize: "11px", cursor: "pointer",
              fontFamily: "var(--font-mono), monospace", transition: "color 0.15s",
            }}
              onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
              onMouseLeave={e => (e.currentTarget.style.color = "#3a3835")}
            >clear</button>
          )}
          <button onClick={runSearch} disabled={searching} style={{
            background: searching ? "#181818" : "#5aaa72", color: "#fff",
            border: "none", borderRadius: "8px", padding: "8px 18px",
            fontSize: "11px", fontFamily: "var(--font-mono), monospace",
            fontWeight: 600, letterSpacing: "0.06em", cursor: "pointer",
            opacity: searching ? 0.5 : 1, transition: "background 0.15s",
          }}
            onMouseEnter={e => { if (!searching) e.currentTarget.style.background = "#3d8a57"; }}
            onMouseLeave={e => { if (!searching) e.currentTarget.style.background = "#5aaa72"; }}
          >
            {searching ? "…" : "search →"}
          </button>
        </div>
        {searchError && (
          <p style={{ fontSize: "11px", color: "#f87171", fontFamily: "var(--font-mono), monospace", marginBottom: "16px" }}>
            {searchError}
          </p>
        )}

        {/* ── Recently Analysed strip ── */}
        {showStrip && (
          <div style={{ marginBottom: "28px" }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: "10px",
            }}>
              <div style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                textTransform: "uppercase", letterSpacing: "0.18em", color: "#5aaa72",
                display: "flex", alignItems: "center", gap: "8px",
              }}>
                <span className="blink" style={{ fontSize: "7px", animationDelay: "0.7s", color: "#5aaa72" }}>●</span>
                Recently Analysed
              </div>
              <a
                href="/forecasts/all"
                style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  fontWeight: 600, letterSpacing: "0.06em",
                  color: "#3a3835", textDecoration: "none",
                  transition: "color 0.15s",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "#5b9cf6"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "#3a3835"; }}
              >
                See all ({forecasts.length}) →
              </a>
            </div>

            {/* Scrollable row */}
            <div style={{
              display: "flex", gap: "8px",
              overflowX: "auto", paddingBottom: "4px",
              scrollbarWidth: "none",
            }}>
              {forecasts.slice(0, 8).map((f, i) => {
                const fp   = f.forecaster_prob ?? 0;
                const edge = f.edge ?? 0;
                const ec   = edgeColor(edge);
                return (
                  <motion.button
                    key={f.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.28, delay: i * 0.04 }}
                    onClick={() => goForecast(f)}
                    style={{
                      flexShrink: 0, width: "200px", textAlign: "left",
                      background: "rgba(14,14,14,0.95)",
                      border: "1px solid #1e1e1e", borderRadius: "10px",
                      padding: "12px 14px", cursor: "pointer",
                      transition: "border-color 0.15s, background 0.15s",
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.borderColor = "rgba(91,156,246,0.22)";
                      e.currentTarget.style.background = "rgba(18,18,18,0.98)";
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.borderColor = "#1e1e1e";
                      e.currentTarget.style.background = "rgba(14,14,14,0.95)";
                    }}
                  >
                    {/* Event title — eyebrow */}
                    {f.event_title && (
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "8px",
                        fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em",
                        color: "#6b6865", marginBottom: "5px",
                        overflow: "hidden", display: "-webkit-box",
                        WebkitLineClamp: 1, WebkitBoxOrient: "vertical" as const,
                      }}>
                        {f.event_title}
                      </div>
                    )}

                    {/* Question */}
                    <div style={{
                      fontSize: "12px", fontWeight: 500, color: "#ede9e3", lineHeight: 1.5,
                      overflow: "hidden", display: "-webkit-box",
                      WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const,
                      marginBottom: "10px",
                    }}>
                      {f.question}
                    </div>

                    {/* Hero: edge */}
                    <div style={{ marginBottom: "10px" }}>
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "26px",
                        fontWeight: 700, color: ec, letterSpacing: "-0.03em",
                        lineHeight: 1, marginBottom: "3px",
                      }}>
                        {edge > 0 ? "+" : ""}{(edge * 100).toFixed(0)}%
                      </div>
                      <div style={{
                        fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                        fontWeight: 600, letterSpacing: "0.1em",
                        textTransform: "uppercase", color: ec, opacity: 0.7,
                      }}>
                        {Math.abs(edge) > 0.03 ? "mispriced" : "inline"}
                      </div>
                    </div>

                    {/* Supporting: model vs market */}
                    <div style={{ display: "flex", gap: "12px", marginBottom: "8px" }}>
                      <div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "8px", color: "#4a4845", letterSpacing: "0.08em", marginBottom: "1px" }}>Model</div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "12px", fontWeight: 600, color: "#9b9790" }}>{(fp * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "8px", color: "#4a4845", letterSpacing: "0.08em", marginBottom: "1px" }}>Market</div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "12px", fontWeight: 600, color: "#9b9790" }}>{((f.kalshi_price ?? 0) * 100).toFixed(0)}%</div>
                      </div>
                    </div>
                    <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", color: "#2a2826" }}>
                      {relTime(f.created_at)}
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Live Markets ── */}
        <div style={{
          fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.2em", color: "#5aaa72",
          display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px",
        }}>
          <span className="blink" style={{ fontSize: "7px", color: "#5aaa72" }}>●</span>
          Live Markets
          <span style={{ color: "#2a2826" }}>·</span>
          <span style={{ color: "#6b6865", fontWeight: 400, letterSpacing: "0.1em" }}>click any card to analyse</span>
        </div>

        {events.length > 0 ? (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "10px",
          }}>
            {events.map((e, i) => (
              <MarketCard key={e.event_ticker} event={e} index={i} onForecast={goRunForecast} />
            ))}
          </div>
        ) : (
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#2a2826", paddingTop: "40px", textAlign: "center" }}>
            {searching ? "Loading markets…" : "No results."}
          </div>
        )}

      </div>
    </div>
  );
}
