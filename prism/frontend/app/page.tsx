"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import MarketCard from "@/components/MarketCard";
import ForecastCard from "@/components/ForecastCard";
import { searchEvents, listForecasts } from "@/lib/api";
import type { KalshiEvent, SavedForecast } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [query, setQuery]         = useState("");
  const [browse, setBrowse]       = useState<KalshiEvent[]>([]);
  const [results, setResults]     = useState<KalshiEvent[]>([]);
  const [forecasts, setForecasts] = useState<SavedForecast[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched]   = useState(false);
  const [error, setError]         = useState("");

  useEffect(() => {
    searchEvents("", 18).then(setBrowse).catch(() => {});
    listForecasts(12).then(setForecasts).catch(() => {});
  }, []);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await searchEvents(query);
      setResults(res);
      setSearched(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }, [query]);

  const clearSearch = () => {
    setQuery("");
    setSearched(false);
    setResults([]);
    setError("");
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") runSearch();
    if (e.key === "Escape") clearSearch();
  };

  const goMarket = (event: KalshiEvent) =>
    router.push(
      `/market/${event.event_ticker}?title=${encodeURIComponent(event.title)}&cat=${encodeURIComponent(event.category)}&sub=${encodeURIComponent(event.sub_title)}`
    );

  const goForecast = (f: SavedForecast) =>
    router.push(`/market/${f.ticker}?saved=${f.id}`);

  const displayEvents = searched ? results : browse;
  const sectionLabel  = searched
    ? `${results.length} result${results.length !== 1 ? "s" : ""} for "${query}"`
    : "Browse Markets";

  return (
    <div style={{
      height: "100vh", overflow: "hidden",
      background: "#080808", position: "relative",
      display: "flex", flexDirection: "column",
    }}>
      <Header />
      <GridOverlay />

      {/* Main content — fills space below fixed header */}
      <div style={{
        position: "relative", zIndex: 10,
        flex: 1, minHeight: 0,
        paddingTop: "56px",
        display: "flex", flexDirection: "column",
        padding: "72px 32px 24px",
        gap: "16px",
      }}>

        {/* Search bar */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{
            flex: 1,
            display: "flex", gap: "8px",
            background: "rgba(14,14,14,0.95)",
            border: "1px solid #282828", borderRadius: "12px",
            padding: "6px 6px 6px 18px",
            backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
            boxShadow: "0 0 0 1px rgba(255,255,255,0.02), 0 8px 32px rgba(0,0,0,0.5)",
          }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={onKey}
              placeholder="Search markets — Trump, Fed, Bitcoin, elections…"
              style={{
                flex: 1, background: "transparent", border: "none",
                fontSize: "13px", color: "#ede9e3",
                fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                outline: "none",
              }}
            />
            {searched && (
              <button
                onClick={clearSearch}
                style={{
                  background: "transparent", color: "#3a3835", border: "none",
                  padding: "8px 12px", fontSize: "11px",
                  fontFamily: "var(--font-mono), monospace",
                  transition: "color 0.15s", cursor: "pointer",
                }}
                onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
                onMouseLeave={e => (e.currentTarget.style.color = "#3a3835")}
              >
                clear
              </button>
            )}
            <button
              onClick={runSearch}
              disabled={searching}
              style={{
                background: searching ? "#181818" : "#e36438",
                color: "#fff", border: "none", borderRadius: "8px",
                padding: "8px 18px", fontSize: "11px",
                fontFamily: "var(--font-mono), monospace",
                fontWeight: 600, letterSpacing: "0.06em",
                transition: "background 0.15s", whiteSpace: "nowrap",
                opacity: searching ? 0.5 : 1, cursor: "pointer",
              }}
              onMouseEnter={e => { if (!searching) e.currentTarget.style.background = "#c4421a"; }}
              onMouseLeave={e => { if (!searching) e.currentTarget.style.background = "#e36438"; }}
            >
              {searching ? "…" : "search →"}
            </button>
          </div>
          {error && (
            <span style={{
              fontSize: "11px", color: "#f87171",
              fontFamily: "var(--font-mono), monospace", flexShrink: 0,
            }}>
              {error}
            </span>
          )}
        </div>

        {/* Two-column content */}
        <div style={{
          flex: 1, minHeight: 0,
          display: "grid",
          gridTemplateColumns: "1fr 340px",
          gap: "20px",
        }}>

          {/* Left — Markets */}
          <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
            <SectionHeader label={sectionLabel} dot="orange" />
            <div style={{ flex: 1, overflowY: "auto", paddingRight: "4px" }}>
              {displayEvents.length > 0 ? (
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                  gap: "8px", alignContent: "start",
                }}>
                  {displayEvents.map((e, i) => (
                    <MarketCard key={e.event_ticker} event={e} index={i} onSelect={goMarket} />
                  ))}
                </div>
              ) : (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                  color: "#2a2826", paddingTop: "24px",
                }}>
                  {searching ? "Searching…" : searched ? "No results." : "Loading…"}
                </div>
              )}
            </div>
          </div>

          {/* Right — Forecasts */}
          <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
            <SectionHeader label="Latest Forecasts" dot="blue" />
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
              {forecasts.length > 0 ? (
                forecasts.map((f, i) => (
                  <motion.div key={f.id}
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.35, delay: i * 0.04 }}
                  >
                    <ForecastCard forecast={f} index={i} onSelect={goForecast} featured={i === 0} />
                  </motion.div>
                ))
              ) : (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                  color: "#2a2826", paddingTop: "24px",
                }}>
                  No forecasts yet.
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

function SectionHeader({ label, dot }: { label: string; dot: "orange" | "blue" }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono), monospace", fontSize: "10px", fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.18em", color: "#9b9790",
      marginBottom: "12px", paddingBottom: "10px", borderBottom: "1px solid #1e1e1e",
      display: "flex", alignItems: "center", gap: "10px",
      flexShrink: 0,
    }}>
      <span
        className="blink"
        style={{ fontSize: "7px", color: dot === "orange" ? "#e36438" : "#5b9cf6", animationDelay: dot === "blue" ? "0.7s" : "0s" }}
      >●</span>
      {label}
    </div>
  );
}
