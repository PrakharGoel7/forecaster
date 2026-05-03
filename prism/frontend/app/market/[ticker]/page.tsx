"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import { getMarkets, getMarket, listForecasts, streamForecast } from "@/lib/api";
import type { KalshiMarket, ForecastMemo, OVData, IVData, StreamMessage, SavedForecast } from "@/lib/types";

function fmtVol(v: number) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

type Phase = "idle" | "running" | "done" | "error";

const DIR_COLORS: Record<string, string> = {
  raises: "#4ade80", lowers: "#f87171", base_rate: "#5b9cf6", context: "#6b6865",
};

export default function MarketPage() {
  const params       = useParams();
  const searchParams = useSearchParams();
  const router       = useRouter();

  const rawTicker   = params.ticker as string;
  const eventTitle  = searchParams.get("title") ?? "";
  const evCat       = searchParams.get("cat") ?? "";
  const evSub       = searchParams.get("sub") ?? "";
  const savedId     = searchParams.get("saved");
  const fromTrading = searchParams.get("from") === "trading";
  const fromSession = searchParams.get("session");
  const backHref    = fromTrading
    ? `/trading${fromSession ? `?session=${fromSession}` : ""}`
    : "/";

  const [markets, setMarkets]             = useState<KalshiMarket[]>([]);
  const [mkt, setMkt]                     = useState<KalshiMarket | null>(null);
  const [memo, setMemo]                   = useState<ForecastMemo | null>(null);
  const [ovData, setOvData]               = useState<OVData | null>(null);
  const [ivData, setIvData]               = useState<IVData | null>(null);
  const [kalshiPrice, setKalshiPrice]     = useState(0);
  const [phase, setPhase]                 = useState<Phase>("idle");
  const [progressLabel, setProgressLabel] = useState("Initializing…");
  const [errorMsg, setErrorMsg]           = useState("");
  const cancelRef = useRef<(() => void) | null>(null);

  const [savedEventTitle, setSavedEventTitle] = useState("");
  const [savedEvCat, setSavedEvCat]           = useState("");
  const [savedEvSub, setSavedEvSub]           = useState("");

  const [categoryStats, setCategoryStats] = useState<{ edge: number; total: number; isCategory: boolean } | null>(null);

  useEffect(() => {
    if (savedId) return;
    const cat = (evCat || savedEvCat).toLowerCase();
    listForecasts(200).then((rows: SavedForecast[]) => {
      if (rows.length === 0) return;
      const catRows = cat ? rows.filter(r => {
        try {
          const rowCat = (JSON.parse(r.context_json).event?.category ?? "").toLowerCase();
          return rowCat === cat || rowCat.includes(cat) || cat.includes(rowCat);
        } catch { return false; }
      }) : [];
      const pool = catRows.length >= 3
        ? { rows: catRows, isCategory: true }
        : rows.length >= 5 ? { rows, isCategory: false } : null;
      if (!pool) return;
      let edge = 0;
      for (const r of pool.rows) {
        try {
          const fp = JSON.parse(r.memo_json).final_probability as number;
          if (Math.abs(fp - r.kalshi_price) > 0.03) edge++;
        } catch {}
      }
      setCategoryStats({ edge, total: pool.rows.length, isCategory: pool.isCategory });
    }).catch(() => {});
  }, [evCat, savedEvCat, savedId]);

  useEffect(() => {
    if (savedId) {
      listForecasts(200).then((rows: SavedForecast[]) => {
        const row = rows.find(r => r.id === Number(savedId));
        if (row) {
          const ctx = JSON.parse(row.context_json);
          setMkt(ctx.market as KalshiMarket);
          setMemo(JSON.parse(row.memo_json));
          setKalshiPrice(row.kalshi_price);
          setPhase("done");
          if (ctx.event) {
            setSavedEventTitle(ctx.event.title ?? "");
            setSavedEvCat(ctx.event.category ?? "");
            setSavedEvSub(ctx.event.sub_title ?? "");
          }
        }
      }).catch(() => {});
    } else {
      getMarkets(rawTicker)
        .then((mkts: KalshiMarket[]) => {
          setMarkets(mkts);
          if (mkts.length === 1) setMkt(mkts[0]);
        })
        .catch(() => {
          getMarket(rawTicker)
            .then((m: KalshiMarket) => { setMkt(m); setMarkets([m]); })
            .catch(() => {});
        });
    }
  }, [rawTicker, savedId]);

  const displayTitle = eventTitle || savedEventTitle;
  const displayCat   = evCat     || savedEvCat;
  const displaySub   = evSub     || savedEvSub;

  const runForecast = () => {
    if (!mkt) return;
    setPhase("running");
    setProgressLabel("Initializing…");
    setMemo(null);
    setOvData(null);
    setIvData(null);
    cancelRef.current = streamForecast(
      { ticker: mkt.ticker, event_title: displayTitle, ev_sub: displaySub, ev_category: displayCat, market: mkt as unknown as Record<string, unknown> },
      (msg: StreamMessage) => {
        if (msg.type === "progress") {
          setProgressLabel(msg.label);
        } else if (msg.type === "ov_complete") {
          setOvData({ base_rate: msg.base_rate, reference_class: msg.reference_class, reasoning: msg.reasoning });
        } else if (msg.type === "iv_complete") {
          const allFor = [...new Set(msg.agent_forecasts.flatMap(a => a.key_factors_for))].slice(0, 5);
          const allAgainst = [...new Set(msg.agent_forecasts.flatMap(a => a.key_factors_against))].slice(0, 5);
          setIvData({ key_factors_for: allFor, key_factors_against: allAgainst });
        } else if (msg.type === "complete") {
          setMemo(msg.memo); setKalshiPrice(msg.kalshi_price); setPhase("done");
        } else if (msg.type === "error") {
          setErrorMsg(msg.message); setPhase("error");
        }
      }
    );
  };

  const pColor = (p: number) => p >= 0.6 ? "#4ade80" : p >= 0.35 ? "#fbbf24" : "#f87171";

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "760px", margin: "0 auto", padding: "84px 32px 80px" }}>

        {/* Breadcrumb */}
        <button
          onClick={() => router.push(backHref)}
          style={{
            background: "transparent", border: "none", padding: 0,
            fontFamily: "var(--font-mono), monospace", fontSize: "10px",
            color: "#2a2826", display: "flex", alignItems: "center", gap: "6px",
            marginBottom: "32px", transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
          onMouseLeave={e => (e.currentTarget.style.color = "#2a2826")}
        >
          ← {fromTrading ? "back to recommendations" : "home"}
          {displayTitle && (
            <><span style={{ color: "#1a1a1a" }}> › </span>
            <span style={{ color: "#3a3835" }}>{displayTitle.slice(0, 60)}</span></>
          )}
        </button>

        {/* Multi-market picker */}
        {!savedId && markets.length > 1 && !mkt && (
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 700, color: "#ede9e3", marginBottom: "20px" }}>
              {eventTitle}
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {markets.map(m => (
                <button key={m.ticker} onClick={() => setMkt(m)} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "14px 18px", background: "#0f0f0f", border: "1px solid #1c1c1c",
                  borderRadius: "10px", transition: "border-color 0.15s",
                }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "rgba(227,100,56,0.3)")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "#1c1c1c")}
                >
                  <span style={{ fontSize: "14px", color: "#ede9e3", fontWeight: 500 }}>
                    {m.yes_sub_title || m.ticker}
                  </span>
                  <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "16px", fontWeight: 700, color: pColor(m.mid_price) }}>
                    {(m.mid_price * 100).toFixed(0)}¢
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Main single-column layout ── */}
        {mkt && (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
          >

            {/* 1. Category + Title */}
            <div style={{ marginBottom: "20px" }}>
              {displayCat && (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.16em", color: "#e36438", marginBottom: "10px",
                }}>
                  {displayCat}{displaySub ? ` · ${displaySub}` : ""}
                </div>
              )}
              <h1 style={{ fontSize: "24px", fontWeight: 700, color: "#ede9e3", lineHeight: 1.4, marginBottom: markets.length > 1 && mkt.yes_sub_title ? "12px" : "20px" }}>
                {displayTitle || mkt.yes_sub_title || mkt.ticker}
              </h1>
              {markets.length > 1 && mkt.yes_sub_title && (
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.16em", color: "#6b6865",
                  marginBottom: "20px",
                }}>
                  Selected Option · <span style={{ color: "#ede9e3" }}>{mkt.yes_sub_title}</span>
                </div>
              )}
              <YesNoBar price={mkt.mid_price} />
            </div>

            {/* 2. Vitals strip */}
            <div style={{
              display: "flex", gap: "32px", alignItems: "center",
              padding: "14px 0", borderTop: "1px solid #141414",
              marginBottom: "8px", flexWrap: "wrap",
            }}>
              <VitalStat label="Closes" value={mkt.close_date} accent />
              <VitalStat label="Volume" value={fmtVol(mkt.volume)} />
            </div>

            {/* 3. Resolution rules — always visible */}
            {mkt.rules_primary && (
              <div style={{ marginBottom: "28px" }}>
                <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "8px" }}>
                  Resolution Rules
                </div>
                <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "8px", padding: "12px 14px", fontSize: "12px", color: "#6b6865", lineHeight: 1.75 }}>
                  {mkt.rules_primary}
                </div>
              </div>
            )}

            {/* 4. Forecast panel */}
            <div style={{
              background: "#0f0f0f", border: "1px solid #1c1c1c",
              borderRadius: "16px", overflow: "hidden",
            }}>
              <div style={{ height: "2px", background: "linear-gradient(90deg, #e36438, #5b9cf6 60%, transparent)" }} />
              <div style={{ padding: "24px" }}>
                <div style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.16em", color: "#2a2826", marginBottom: "18px",
                }}>
                  AI Forecast
                </div>

                {/* Error */}
                {phase === "error" && (
                  <div style={{ padding: "12px 14px", background: "#180a0a", border: "1px solid #3a1515", borderRadius: "8px", marginBottom: "16px" }}>
                    <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#f87171" }}>{errorMsg}</div>
                  </div>
                )}

                {/* Idle / Running / Done — dashboard grid */}
                {(phase === "idle" || phase === "running" || (phase === "done" && memo)) && (() => {
                  const isIdle     = phase === "idle";
                  const isRunning  = phase === "running";
                  const allFor     = ivData?.key_factors_for ?? [];
                  const allAgainst = ivData?.key_factors_against ?? [];
                  const evidence   = memo ? memo.agent_forecasts.flatMap(a => a.evidence_ledger.items) : [];
                  const prismPct   = memo ? Math.round(memo.final_probability * 100) : 0;
                  const kalshiPct  = Math.round(kalshiPrice * 100);
                  const probColor  = memo ? pColor(memo.final_probability) : "#6b6865";

                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

                      {/* Row 1: Prior & Base Rate | Cog */}
                      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: "10px", alignItems: "stretch" }}>
                        <GridCell label="Prior & Base Rate">
                          {!ovData ? <Skeleton lines={[80, 65, 75, 50, 70]} /> : (
                            <>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "28px", fontWeight: 700, color: "#ede9e3", margin: "10px 0 12px", lineHeight: 1 }}>
                                {(ovData.base_rate * 100).toFixed(0)}%
                              </div>
                              <div style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.75 }}>
                                {ovData.reasoning}
                              </div>
                            </>
                          )}
                        </GridCell>
                        <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "12px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "20px", gap: "14px", minHeight: "120px" }}>
                          <motion.svg
                            width="52" height="52" viewBox="-22 -22 44 44"
                            style={{ display: "block" }}
                            animate={isRunning ? { rotate: 360 } : { rotate: 0 }}
                            transition={isRunning ? { duration: 2.4, repeat: Infinity, ease: "linear" } : { duration: 0 }}
                          >
                            <g>
                              {[0, 45, 90, 135, 180, 225, 270, 315].map(deg => (
                                <rect key={deg} x="-3.5" y="-19" width="7" height="6" rx="1.5" fill="#2a2826" transform={`rotate(${deg})`} />
                              ))}
                              <circle cx="0" cy="0" r="12" fill="#141414" />
                              <circle cx="0" cy="0" r="4.5" fill="#080808" />
                            </g>
                          </motion.svg>
                          {isRunning && (
                            <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#e36438", textAlign: "center", lineHeight: 1.5 }}>
                              {progressLabel}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Row 2: For | Against */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", alignItems: "stretch" }}>
                        <GridCell label="For YES" labelColor="#4ade80">
                          {!ivData ? <Skeleton lines={[75, 60, 80, 55]} /> : (
                            allFor.length > 0
                              ? allFor.map((f, i) => <div key={i} style={{ fontSize: "12px", color: "#ede9e3", padding: "5px 0", borderBottom: "1px solid #141414" }}>+ {f}</div>)
                              : <div style={{ fontSize: "12px", color: "#3a3835" }}>—</div>
                          )}
                        </GridCell>
                        <GridCell label="Against" labelColor="#f87171">
                          {!ivData ? <Skeleton lines={[65, 75, 55, 80]} /> : (
                            allAgainst.length > 0
                              ? allAgainst.map((f, i) => <div key={i} style={{ fontSize: "12px", color: "#ede9e3", padding: "5px 0", borderBottom: "1px solid #141414" }}>− {f}</div>)
                              : <div style={{ fontSize: "12px", color: "#3a3835" }}>—</div>
                          )}
                        </GridCell>
                      </div>

                      {/* Row 3: Final Synthesis | Final Probability */}
                      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: "10px", alignItems: "stretch" }}>
                        <GridCell label="Final Synthesis">
                          {(isIdle || isRunning) ? <Skeleton lines={[90, 75, 85, 60, 80, 55, 70]} /> : (
                            <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.75, marginTop: "8px" }}>
                              {memo!.supervisor_reconciliation.reconciliation_reasoning}
                            </div>
                          )}
                        </GridCell>
                        <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "12px", padding: "20px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                          {(isIdle || isRunning) ? <Skeleton lines={[50, 35]} /> : (
                            <>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "8px" }}>Prism</div>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "48px", fontWeight: 700, color: probColor, lineHeight: 1 }}>
                                {prismPct}%
                              </div>
                              <div style={{ width: "32px", height: "1px", background: "#1c1c1c", margin: "14px 0" }} />
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "8px" }}>Kalshi</div>
                              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "26px", fontWeight: 600, color: "#6b6865", lineHeight: 1 }}>
                                {kalshiPct}¢
                              </div>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Row 4: Sources — collapsed */}
                      {!isIdle && !isRunning && evidence.length > 0 && (
                        <details style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "12px", overflow: "hidden" }}>
                          <summary style={{
                            cursor: "pointer", listStyle: "none",
                            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                            textTransform: "uppercase", letterSpacing: "0.12em", color: "#3a3835",
                            padding: "14px 20px",
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            transition: "color 0.15s",
                          }}
                            onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
                            onMouseLeave={e => (e.currentTarget.style.color = "#3a3835")}
                          >
                            Sources ({evidence.length}) <span style={{ fontSize: "10px" }}>▾</span>
                          </summary>
                          <div style={{ padding: "12px 20px 16px", borderTop: "1px solid #141414", display: "flex", flexDirection: "column", gap: "8px" }}>
                            {evidence.map((item, i) => {
                              const c = DIR_COLORS[item.direction] ?? "#6b6865";
                              return (
                                <div key={i} style={{ borderLeft: `2px solid ${c}`, paddingLeft: "10px", paddingTop: "6px", paddingBottom: "6px" }}>
                                  <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: c, marginBottom: "4px" }}>{item.direction.replace("_", " ")}</div>
                                  <div style={{ fontSize: "12px", color: "#ede9e3", lineHeight: 1.5, marginBottom: "3px" }}>{item.claim}</div>
                                  <a href={item.source_url} target="_blank" style={{ fontSize: "10px", color: "#3a3835", textDecoration: "underline" }}>{item.source_title}</a>
                                  {item.relevant_quote_or_snippet && (
                                    <div style={{ fontSize: "10px", color: "#3a3835", fontStyle: "italic", marginTop: "4px" }}>"{item.relevant_quote_or_snippet.slice(0, 160)}"</div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </details>
                      )}

                      {/* Run button (idle) */}
                      {isIdle && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          {categoryStats && categoryStats.total >= 3 && (
                            <div style={{ textAlign: "center", fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#3a3835" }}>
                              edge found in {categoryStats.edge} of {categoryStats.total}{categoryStats.isCategory && displayCat ? ` ${displayCat}` : ""} forecasts
                            </div>
                          )}
                          <button onClick={runForecast} style={{
                            width: "100%", background: "#e36438", color: "#fff", border: "none",
                            borderRadius: "10px", padding: "13px", fontSize: "12px",
                            fontFamily: "var(--font-mono), monospace", fontWeight: 600, letterSpacing: "0.06em",
                            transition: "background 0.15s",
                          }}
                            onMouseEnter={e => (e.currentTarget.style.background = "#c4421a")}
                            onMouseLeave={e => (e.currentTarget.style.background = "#e36438")}
                          >
                            run forecast →
                          </button>
                        </div>
                      )}

                      {/* Refresh button (done) */}
                      {!isIdle && !isRunning && !savedId && (
                        <button onClick={runForecast} style={{
                          width: "100%", background: "transparent", color: "#3a3835",
                          border: "1px solid #1a1a1a", borderRadius: "8px", padding: "10px",
                          fontSize: "11px", fontFamily: "var(--font-mono), monospace",
                          transition: "all 0.15s",
                        }}
                          onMouseEnter={e => { e.currentTarget.style.color = "#6b6865"; e.currentTarget.style.borderColor = "#252525"; }}
                          onMouseLeave={e => { e.currentTarget.style.color = "#3a3835"; e.currentTarget.style.borderColor = "#1a1a1a"; }}
                        >
                          refresh forecast
                        </button>
                      )}

                    </div>
                  );
                })()}
              </div>
            </div>

          </motion.div>
        )}
      </div>
    </div>
  );
}

// ── Helper components ────────────────────────────────────────────────────────

function YesNoBar({ price }: { price: number }) {
  const yesPct = price * 100;
  const noPct  = (1 - price) * 100;
  const yesColor = yesPct >= 60 ? "#4ade80" : yesPct >= 35 ? "#fbbf24" : "#f87171";
  return (
    <div>
      <div style={{ display: "flex", borderRadius: "4px", overflow: "hidden", height: "4px", marginBottom: "12px", background: "#1c1c1c" }}>
        <div style={{ width: `${yesPct}%`, background: yesColor, transition: "width 0.4s" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "7px" }}>
          <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "30px", fontWeight: 700, color: yesColor, lineHeight: 1 }}>
            {yesPct.toFixed(0)}¢
          </span>
          <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#3a3835", textTransform: "uppercase", letterSpacing: "0.12em" }}>yes</span>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "7px" }}>
          <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#3a3835", textTransform: "uppercase", letterSpacing: "0.12em" }}>no</span>
          <span style={{ fontFamily: "var(--font-mono), monospace", fontSize: "30px", fontWeight: 700, color: "#4a4845", lineHeight: 1 }}>
            {noPct.toFixed(0)}¢
          </span>
        </div>
      </div>
    </div>
  );
}

function VitalStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "3px" }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "13px", fontWeight: 600, color: accent ? "#e36438" : "#ede9e3" }}>
        {value}
      </div>
    </div>
  );
}

function ProbabilityComparison({ prism, kalshi, edgeColor, numAgents }: {
  prism: number; kalshi: number; edgeColor: string; numAgents: number;
}) {
  const prismPct  = Math.round(prism * 100);
  const kalshiPct = Math.round(kalshi * 100);
  const lo = Math.min(prismPct, kalshiPct);
  const hi = Math.max(prismPct, kalshiPct);

  // Clamp so labels don't clip off screen edges
  const kPos = Math.min(Math.max(kalshiPct, 7), 93);
  const pPos = Math.min(Math.max(prismPct, 7), 93);
  // If markers are too close, put Kalshi label above the track
  const tooClose = Math.abs(kPos - pPos) < 18;
  const TRACK_Y  = tooClose ? 28 : 20;

  return (
    <div style={{
      background: "#080808", border: "1px solid #1a1a1a",
      borderRadius: "10px", padding: "20px 20px 16px", marginBottom: "14px",
    }}>
      <Lbl>Prism vs Market</Lbl>
      <div style={{ margin: "18px 0 0", position: "relative", height: tooClose ? "80px" : "64px" }}>

        {/* Track */}
        <div style={{
          position: "absolute", top: `${TRACK_Y}px`, left: 0, right: 0,
          height: "1px", background: "#1c1c1c",
        }} />

        {/* Gap highlight between the two markers */}
        <div style={{
          position: "absolute", top: `${TRACK_Y}px`, height: "1px",
          left: `${lo}%`, width: `${hi - lo}%`,
          background: edgeColor + "66",
        }} />

        {/* Kalshi marker — shorter, gray */}
        <div style={{
          position: "absolute", left: `${kPos}%`,
          top: `${TRACK_Y - 8}px`, transform: "translateX(-50%)",
          width: "1px", height: "16px", background: "#4a4845",
        }} />

        {/* Prism marker — taller, orange glow */}
        <div style={{
          position: "absolute", left: `${pPos}%`,
          top: `${TRACK_Y - 11}px`, transform: "translateX(-50%)",
          width: "2px", height: "22px", background: "#e36438",
          boxShadow: "0 0 8px #e3643855",
        }} />

        {/* Kalshi label */}
        <div style={{
          position: "absolute",
          left: `${kPos}%`,
          top: tooClose ? `${TRACK_Y - 42}px` : `${TRACK_Y + 10}px`,
          transform: "translateX(-50%)", textAlign: "center", whiteSpace: "nowrap",
        }}>
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "15px", fontWeight: 600, color: "#6b6865", lineHeight: 1 }}>
            {kalshiPct}¢
          </div>
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "8px", color: "#3a3835", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "3px" }}>
            kalshi
          </div>
        </div>

        {/* Prism label */}
        <div style={{
          position: "absolute",
          left: `${pPos}%`,
          top: `${TRACK_Y + 10}px`,
          transform: "translateX(-50%)", textAlign: "center", whiteSpace: "nowrap",
        }}>
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "15px", fontWeight: 600, color: "#e36438", lineHeight: 1 }}>
            {prismPct}%
          </div>
          <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "8px", color: "#3a3835", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "3px" }}>
            prism · {numAgents} agents
          </div>
        </div>

      </div>
    </div>
  );
}

function GridCell({ label, children, labelColor }: { label: string; children: React.ReactNode; labelColor?: string }) {
  return (
    <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "12px", padding: "18px 20px" }}>
      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: labelColor ?? "#2a2826", marginBottom: "10px" }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function Skeleton({ lines }: { lines: number[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "7px", paddingTop: "4px" }}>
      {lines.map((w, i) => (
        <div key={i} style={{ height: "9px", borderRadius: "2px", background: "#161616", width: `${w}%` }} />
      ))}
    </div>
  );
}

function Lbl({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "4px" }}>
      {children}
    </div>
  );
}

function Expander({ label, children, defaultOpen }: { label: string; children: React.ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} style={{ marginBottom: "10px" }}>
      <summary style={{
        cursor: "pointer", listStyle: "none",
        fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.12em", color: "#3a3835",
        padding: "10px 0", borderBottom: "1px solid #141414",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        transition: "color 0.15s",
      }}
        onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
        onMouseLeave={e => (e.currentTarget.style.color = "#3a3835")}
      >
        {label} <span style={{ fontSize: "10px" }}>▾</span>
      </summary>
      <div style={{ paddingTop: "12px" }}>{children}</div>
    </details>
  );
}
