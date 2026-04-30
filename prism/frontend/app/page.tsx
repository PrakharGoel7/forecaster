"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import SpectralGlow from "@/components/SpectralGlow";
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

  const onKey = (e: React.KeyboardEvent) => { if (e.key === "Enter") runSearch(); };

  const goMarket = (event: KalshiEvent) =>
    router.push(
      `/market/${event.event_ticker}?title=${encodeURIComponent(event.title)}&cat=${encodeURIComponent(event.category)}&sub=${encodeURIComponent(event.sub_title)}`
    );

  const goForecast = (f: SavedForecast) =>
    router.push(`/market/${f.ticker}?saved=${f.id}`);

  const displayEvents = searched ? results : browse;
  const sectionLabel  = searched
    ? `${results.length} result${results.length !== 1 ? "s" : ""}`
    : "Browse Markets";

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />

      {/* ── Hero ── */}
      <section style={{
        position: "relative", minHeight: "100vh",
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        padding: "80px 24px 60px",
      }}>
        <GridOverlay />
        <SpectralGlow />

        <div style={{
          position: "relative", zIndex: 10,
          width: "100%", maxWidth: "620px", textAlign: "center",
        }}>
          {/* Icon */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            style={{ marginBottom: "28px", display: "flex", justifyContent: "center" }}
          >
            <div style={{
              width: "60px", height: "60px", borderRadius: "16px",
              background: "linear-gradient(135deg, #1c1c1c 0%, #080808 100%)",
              border: "1px solid #252525",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: "26px", color: "#e36438",
              boxShadow: "0 0 48px rgba(227,100,56,0.14), 0 0 90px rgba(91,156,246,0.06), inset 0 1px 0 rgba(255,255,255,0.04)",
            }}>◈</div>
          </motion.div>

          {/* Wordmark */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
          >
            <h1 style={{
              fontFamily: "var(--font-mono), monospace",
              fontSize: "clamp(42px, 7vw, 72px)", fontWeight: 700,
              letterSpacing: "0.24em", color: "#ede9e3",
              marginBottom: "14px",
              textShadow: "0 0 80px rgba(227,100,56,0.1)",
            }}>
              PRISM
            </h1>
            <p style={{
              fontFamily: "var(--font-mono), monospace",
              fontSize: "11px", color: "#3a3835",
              letterSpacing: "0.1em", marginBottom: "52px",
            }}>
              See through the noise.
            </p>
          </motion.div>

          {/* Search */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.24, ease: [0.16, 1, 0.3, 1] }}
          >
            <div style={{
              display: "flex", gap: "8px",
              background: "rgba(14,14,14,0.95)",
              border: "1px solid #282828", borderRadius: "14px",
              padding: "7px 7px 7px 22px",
              backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
              boxShadow: "0 0 0 1px rgba(255,255,255,0.02), 0 24px 64px rgba(0,0,0,0.65)",
            }}>
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={onKey}
                placeholder="Search markets — Trump, Fed, Bitcoin, elections…"
                style={{
                  flex: 1, background: "transparent", border: "none",
                  fontSize: "14px", color: "#ede9e3",
                  fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                }}
              />
              <button
                onClick={runSearch}
                disabled={searching}
                style={{
                  background: searching ? "#181818" : "#e36438",
                  color: "#fff", border: "none", borderRadius: "10px",
                  padding: "10px 22px", fontSize: "12px",
                  fontFamily: "var(--font-mono), monospace",
                  fontWeight: 600, letterSpacing: "0.06em",
                  transition: "background 0.15s", whiteSpace: "nowrap",
                  opacity: searching ? 0.5 : 1,
                }}
                onMouseEnter={e => { if (!searching) e.currentTarget.style.background = "#c4421a"; }}
                onMouseLeave={e => { if (!searching) e.currentTarget.style.background = "#e36438"; }}
              >
                {searching ? "…" : "search →"}
              </button>
            </div>
            {error && (
              <p style={{
                marginTop: "10px", fontSize: "11px", color: "#f87171",
                fontFamily: "var(--font-mono), monospace",
              }}>
                {error}
              </p>
            )}
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5, duration: 1.2 }}
          style={{
            position: "absolute", bottom: "28px", left: "50%", transform: "translateX(-50%)",
            fontFamily: "var(--font-mono), monospace", fontSize: "9px",
            color: "#1e1e1e", letterSpacing: "0.1em",
          }}
        >↓</motion.div>
      </section>

      {/* ── Content below fold ── */}
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "0 32px 100px" }}>

        {displayEvents.length > 0 && (
          <section style={{ marginBottom: "72px" }}>
            <SectionHeader label={sectionLabel} dot="orange" />
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(268px, 1fr))",
              gap: "10px",
            }}>
              {displayEvents.map((e, i) => (
                <MarketCard key={e.event_ticker} event={e} index={i} onSelect={goMarket} />
              ))}
            </div>
          </section>
        )}

        {forecasts.length > 0 && (
          <section>
            <SectionHeader label="Latest Forecasts" dot="blue" />
            <div style={{ marginBottom: "10px" }}>
              <ForecastCard forecast={forecasts[0]} index={0} onSelect={goForecast} featured />
            </div>
            {forecasts.length > 1 && (
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
                gap: "10px",
              }}>
                {forecasts.slice(1).map((f, i) => (
                  <ForecastCard key={f.id} forecast={f} index={i + 1} onSelect={goForecast} />
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ label, dot }: { label: string; dot: "orange" | "blue" }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.18em", color: "#2a2826",
      marginBottom: "18px", paddingBottom: "14px", borderBottom: "1px solid #141414",
      display: "flex", alignItems: "center", gap: "10px",
    }}>
      <span
        className="blink"
        style={{ fontSize: "7px", color: dot === "orange" ? "#e36438" : "#5b9cf6", animationDelay: dot === "blue" ? "0.7s" : "0s" }}
      >●</span>
      {label}
    </div>
  );
}
