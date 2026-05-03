"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import MarketCard from "@/components/MarketCard";
import { searchEvents } from "@/lib/api";
import type { KalshiEvent } from "@/lib/types";

export default function MarketsPage() {
  const router = useRouter();
  const [query, setQuery]       = useState("");
  const [events, setEvents]     = useState<KalshiEvent[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError]       = useState("");

  useEffect(() => {
    setSearching(true);
    searchEvents("", 48)
      .then(e => { setEvents(e); setSearching(false); })
      .catch(() => setSearching(false));
  }, []);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError("");
    try {
      const res = await searchEvents(query, 48);
      setEvents(res);
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
    setError("");
    setSearching(true);
    searchEvents("", 48).then(e => { setEvents(e); setSearching(false); }).catch(() => setSearching(false));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") runSearch();
    if (e.key === "Escape") clearSearch();
  };

  const goMarket = (event: KalshiEvent) =>
    router.push(`/market/${event.event_ticker}?title=${encodeURIComponent(event.title)}&cat=${encodeURIComponent(event.category)}&sub=${encodeURIComponent(event.sub_title)}`);

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "80px 32px 60px" }}>

        {/* Page title */}
        <div style={{ marginBottom: "28px" }}>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.2em", color: "#e36438", marginBottom: "8px",
          }}>
            <span className="blink" style={{ fontSize: "7px", marginRight: "8px" }}>●</span>
            Live Markets
          </div>
          <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em" }}>
            Browse Prediction Markets
          </h1>
        </div>

        {/* Search */}
        <div style={{
          display: "flex", gap: "8px", marginBottom: "32px",
          background: "rgba(14,14,14,0.95)", border: "1px solid #282828",
          borderRadius: "12px", padding: "6px 6px 6px 18px",
          boxShadow: "0 0 0 1px rgba(255,255,255,0.02)",
        }}>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search by topic — Bitcoin, elections, Fed, AI…"
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
            background: searching ? "#181818" : "#e36438", color: "#fff",
            border: "none", borderRadius: "8px", padding: "8px 18px",
            fontSize: "11px", fontFamily: "var(--font-mono), monospace",
            fontWeight: 600, letterSpacing: "0.06em", cursor: "pointer",
            opacity: searching ? 0.5 : 1, transition: "background 0.15s",
          }}
            onMouseEnter={e => { if (!searching) e.currentTarget.style.background = "#c4421a"; }}
            onMouseLeave={e => { if (!searching) e.currentTarget.style.background = "#e36438"; }}
          >
            {searching ? "…" : "search →"}
          </button>
        </div>
        {error && <p style={{ fontSize: "11px", color: "#f87171", fontFamily: "var(--font-mono), monospace", marginBottom: "16px" }}>{error}</p>}

        {/* Grid */}
        {events.length > 0 ? (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "10px",
          }}>
            {events.map((e, i) => (
              <MarketCard key={e.event_ticker} event={e} index={i} onSelect={goMarket} />
            ))}
          </div>
        ) : (
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "11px",
            color: "#2a2826", paddingTop: "40px", textAlign: "center",
          }}>
            {searching ? "Loading markets…" : "No results."}
          </div>
        )}
      </div>
    </div>
  );
}
