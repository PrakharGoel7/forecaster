"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import ProbabilityArc from "@/components/ProbabilityArc";
import { getMarkets, getMarket, listForecasts, streamForecast } from "@/lib/api";
import type { KalshiMarket, ForecastMemo, StreamMessage, SavedForecast } from "@/lib/types";

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

  const rawTicker  = params.ticker as string;
  const eventTitle = searchParams.get("title") ?? "";
  const evCat      = searchParams.get("cat") ?? "";
  const evSub      = searchParams.get("sub") ?? "";
  const savedId    = searchParams.get("saved");

  const [markets, setMarkets]           = useState<KalshiMarket[]>([]);
  const [mkt, setMkt]                   = useState<KalshiMarket | null>(null);
  const [memo, setMemo]                 = useState<ForecastMemo | null>(null);
  const [kalshiPrice, setKalshiPrice]   = useState(0);
  const [phase, setPhase]               = useState<Phase>("idle");
  const [progressLabel, setProgressLabel] = useState("Initializing…");
  const [errorMsg, setErrorMsg]         = useState("");
  const cancelRef = useRef<(() => void) | null>(null);

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

  const runForecast = () => {
    if (!mkt) return;
    setPhase("running");
    setProgressLabel("Collecting evidence (0%)");
    setMemo(null);
    cancelRef.current = streamForecast(
      { ticker: mkt.ticker, event_title: eventTitle, ev_sub: evSub, ev_category: evCat, market: mkt as unknown as Record<string, unknown> },
      (msg: StreamMessage) => {
        if (msg.type === "progress") setProgressLabel(msg.label);
        else if (msg.type === "complete") {
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
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "84px 32px 80px" }}>

        {/* Breadcrumb */}
        <button
          onClick={() => router.push("/")}
          style={{
            background: "transparent", border: "none", padding: 0,
            fontFamily: "var(--font-mono), monospace", fontSize: "10px",
            color: "#2a2826", display: "flex", alignItems: "center", gap: "6px",
            marginBottom: "32px", transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "#6b6865")}
          onMouseLeave={e => (e.currentTarget.style.color = "#2a2826")}
        >
          ← home
          {eventTitle && (
            <><span style={{ color: "#1a1a1a" }}> › </span>
            <span style={{ color: "#3a3835" }}>{eventTitle.slice(0, 60)}</span></>
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

        {/* Main two-column layout */}
        {mkt && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", alignItems: "start" }}>

            {/* LEFT — market detail */}
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45 }}
              style={{ background: "#0f0f0f", border: "1px solid #1c1c1c", borderRadius: "16px", overflow: "hidden" }}
            >
              <div style={{ height: "2px", background: "linear-gradient(90deg, #e36438, #5b9cf6 60%, transparent)" }} />
              <div style={{ padding: "24px" }}>
                {evCat && (
                  <div style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
                    textTransform: "uppercase", letterSpacing: "0.16em", color: "#e36438", marginBottom: "10px",
                  }}>
                    {evCat}{evSub ? ` · ${evSub}` : ""}
                  </div>
                )}
                <h1 style={{ fontSize: "20px", fontWeight: 700, color: "#ede9e3", lineHeight: 1.4, marginBottom: "24px" }}>
                  {eventTitle || mkt.yes_sub_title || mkt.ticker}
                </h1>

                {/* Stats */}
                <div style={{ display: "flex", gap: "28px", flexWrap: "wrap", marginBottom: "24px" }}>
                  {[
                    { lbl: "Yes Price", val: `${(mkt.mid_price * 100).toFixed(1)}¢`, color: pColor(mkt.mid_price) },
                    { lbl: "Bid / Ask", val: `${mkt.yes_bid > 0 ? (mkt.yes_bid * 100).toFixed(0) + "¢" : "—"} / ${mkt.yes_ask > 0 ? (mkt.yes_ask * 100).toFixed(0) + "¢" : "—"}`, color: "#ede9e3" },
                    { lbl: "Closes", val: mkt.close_date, color: "#e36438" },
                    { lbl: "Volume", val: fmtVol(mkt.volume), color: "#ede9e3" },
                  ].map(s => (
                    <div key={s.lbl}>
                      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "5px" }}>{s.lbl}</div>
                      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "20px", fontWeight: 700, color: s.color }}>{s.val}</div>
                    </div>
                  ))}
                </div>

                {/* Rules */}
                {mkt.rules_primary && (
                  <>
                    <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2a2826", marginBottom: "8px" }}>Resolution Rules</div>
                    <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "8px", padding: "12px 14px", fontSize: "12px", color: "#6b6865", lineHeight: 1.75, maxHeight: "120px", overflowY: "auto" }}>
                      {mkt.rules_primary}
                    </div>
                  </>
                )}
              </div>
            </motion.div>

            {/* RIGHT — forecast */}
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.1 }}
              style={{ background: "#0f0f0f", border: "1px solid #1c1c1c", borderRadius: "16px", padding: "24px" }}
            >
              <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.16em", color: "#2a2826", marginBottom: "18px" }}>
                AI Forecast
              </div>

              {/* Idle */}
              {phase === "idle" && (
                <>
                  <p style={{ fontSize: "13px", color: "#6b6865", lineHeight: 1.75, marginBottom: "18px" }}>
                    Prism deploys multiple independent AI agents to research this market, weigh the evidence, and return a calibrated probability.
                  </p>
                  <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#2a2826", marginBottom: "24px" }}>
                    3 agents · gpt-4o · Platt-scaled
                  </div>
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
                </>
              )}

              {/* Running */}
              {phase === "running" && (
                <div style={{ padding: "16px 0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
                    <div className="blink" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#e36438", flexShrink: 0 }} />
                    <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "12px", color: "#e36438" }}>{progressLabel}</div>
                  </div>
                  <div style={{ height: "2px", background: "#141414", borderRadius: "1px", overflow: "hidden" }}>
                    <div className="shimmer-bar" style={{ height: "100%", borderRadius: "1px" }} />
                  </div>
                </div>
              )}

              {/* Error */}
              {phase === "error" && (
                <div style={{ padding: "12px 14px", background: "#180a0a", border: "1px solid #3a1515", borderRadius: "8px", marginBottom: "16px" }}>
                  <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "11px", color: "#f87171" }}>{errorMsg}</div>
                </div>
              )}

              {/* Done */}
              {phase === "done" && memo && (() => {
                const edge  = memo.final_probability - kalshiPrice;
                const isPos = edge > 0.03, isNeg = edge < -0.03;
                const ec    = isPos ? "#5b9cf6" : isNeg ? "#f87171" : "#3a3835";
                const el    = isPos ? `+${(edge * 100).toFixed(1)}pp — underpriced`
                            : isNeg ? `${(edge * 100).toFixed(1)}pp — overpriced`
                            : "in line with market";
                const avgBase = memo.agent_forecasts.reduce((s, a) => s + a.outside_view_base_rate, 0) / memo.agent_forecasts.length;
                const allFor  = [...new Set(memo.agent_forecasts.flatMap(a => a.key_factors_for))].slice(0, 5);
                const allAgainst = [...new Set(memo.agent_forecasts.flatMap(a => a.key_factors_against))].slice(0, 5);
                const evidence   = memo.agent_forecasts.flatMap(a => a.evidence_ledger.items);

                return (
                  <div>
                    {/* Result cards */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "12px" }}>
                      <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "10px", padding: "16px", textAlign: "center" }}>
                        <Lbl>Prism P(YES)</Lbl>
                        <div style={{ display: "flex", justifyContent: "center", margin: "8px 0" }}>
                          <ProbabilityArc probability={memo.final_probability} size={84} />
                        </div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", color: "#2a2826", marginTop: "4px" }}>
                          {memo.num_agents} agents · calibrated
                        </div>
                      </div>
                      <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "10px", padding: "16px", textAlign: "center" }}>
                        <Lbl>Kalshi Price</Lbl>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "34px", fontWeight: 700, color: "#ede9e3", lineHeight: 1, margin: "14px 0 6px" }}>
                          {(kalshiPrice * 100).toFixed(1)}¢
                        </div>
                        <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", color: "#2a2826" }}>live mid price</div>
                      </div>
                    </div>

                    {/* Edge */}
                    <div style={{ background: "#080808", border: "1px solid #1a1a1a", borderRadius: "10px", padding: "14px 16px", marginBottom: "14px" }}>
                      <Lbl>Edge</Lbl>
                      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "17px", fontWeight: 700, color: ec, textShadow: `0 0 24px ${ec}44`, marginTop: "6px" }}>
                        {el}
                      </div>
                    </div>

                    {/* Expanders */}
                    <Expander label="Final Synthesis" defaultOpen>
                      <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.75 }}>
                        {memo.supervisor_reconciliation.reconciliation_reasoning}
                      </div>
                    </Expander>

                    <Expander label="Prior & Base Rate">
                      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "10px", color: "#6b6865", marginBottom: "8px" }}>
                        avg base rate: {(avgBase * 100).toFixed(1)}%
                      </div>
                      <div style={{ fontSize: "13px", color: "#9b9790", lineHeight: 1.75 }}>{memo.outside_view_summary}</div>
                    </Expander>

                    {(allFor.length > 0 || allAgainst.length > 0) && (
                      <Expander label="Pros / Cons">
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                          <div>
                            <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#4ade80", marginBottom: "8px" }}>For YES</div>
                            {allFor.map((f, i) => <div key={i} style={{ fontSize: "12px", color: "#ede9e3", padding: "5px 0", borderBottom: "1px solid #141414" }}>+ {f}</div>)}
                          </div>
                          <div>
                            <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#f87171", marginBottom: "8px" }}>Against</div>
                            {allAgainst.map((f, i) => <div key={i} style={{ fontSize: "12px", color: "#ede9e3", padding: "5px 0", borderBottom: "1px solid #141414" }}>− {f}</div>)}
                          </div>
                        </div>
                      </Expander>
                    )}

                    {evidence.length > 0 && (
                      <Expander label={`Evidence (${evidence.length} sources)`}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
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
                      </Expander>
                    )}

                    {!savedId && (
                      <button onClick={runForecast} style={{
                        width: "100%", background: "transparent", color: "#3a3835",
                        border: "1px solid #1a1a1a", borderRadius: "8px", padding: "10px",
                        fontSize: "11px", fontFamily: "var(--font-mono), monospace",
                        marginTop: "14px", transition: "all 0.15s",
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
            </motion.div>
          </div>
        )}
      </div>
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
        cursor: "pointer", fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
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
