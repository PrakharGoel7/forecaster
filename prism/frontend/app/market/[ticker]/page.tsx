"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import Header from "@/components/Header";
import { getMarkets, getMarket, listForecasts, streamForecast } from "@/lib/api";
import type {
  KalshiMarket,
  ForecastMemo,
  IVData,
  StreamMessage,
  SavedForecast,
} from "@/lib/types";

function fmtVol(v: number) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

function fmtPct(p: number) {
  return `${Math.round(p * 100)}%`;
}

type Phase = "idle" | "running" | "done" | "error";

const DIR_COLORS: Record<string, string> = {
  raises: "#4ade80",
  lowers: "#f87171",
  base_rate: "#5b9cf6",
  context: "#6b6865",
};

const PROGRESS_STEPS = [
  { key: "rules", label: "Reading the market rules…" },
  { key: "evidence", label: "Looking for relevant evidence…" },
  { key: "pricing", label: "Comparing market price to Prism’s estimate…" },
  { key: "final", label: "Writing final take…" },
] as const;

export default function MarketPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const rawTicker = params.ticker as string;
  const eventTitle = searchParams.get("title") ?? "";
  const evCat = searchParams.get("cat") ?? "";
  const evSub = searchParams.get("sub") ?? "";
  const savedId = searchParams.get("saved");
  const shouldAutoRun = searchParams.get("runForecast") === "1";
  const fromTrading = searchParams.get("from") === "trading";
  const fromSession = searchParams.get("session");
  const backHref = fromTrading
    ? `/trading${fromSession ? `?session=${fromSession}` : ""}`
    : "/";

  const [markets, setMarkets] = useState<KalshiMarket[]>([]);
  const [mkt, setMkt] = useState<KalshiMarket | null>(null);
  const [memo, setMemo] = useState<ForecastMemo | null>(null);
  const [ivData, setIvData] = useState<IVData | null>(null);
  const [kalshiPrice, setKalshiPrice] = useState(0);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progressLabel, setProgressLabel] = useState("Initializing…");
  const [errorMsg, setErrorMsg] = useState("");
  const cancelRef = useRef<(() => void) | null>(null);
  const hasAutoRunRef = useRef(false);

  const [savedEventTitle, setSavedEventTitle] = useState("");
  const [savedEvCat, setSavedEvCat] = useState("");
  const [savedEvSub, setSavedEvSub] = useState("");
  const [categoryStats, setCategoryStats] = useState<{ edge: number; total: number; isCategory: boolean } | null>(null);

  useEffect(() => {
    if (savedId) return;
    const cat = (evCat || savedEvCat).toLowerCase();
    listForecasts(200).then((rows: SavedForecast[]) => {
      if (rows.length === 0) return;
      const catRows = cat ? rows.filter((r) => {
        try {
          const rowCat = (JSON.parse(r.context_json).event?.category ?? "").toLowerCase();
          return rowCat === cat || rowCat.includes(cat) || cat.includes(rowCat);
        } catch {
          return false;
        }
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
        const row = rows.find((r) => r.id === Number(savedId));
        if (!row) return;
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
      }).catch(() => {});
      return;
    }

    getMarkets(rawTicker)
      .then((mkts: KalshiMarket[]) => {
        const sorted = [...mkts].sort((a, b) => b.mid_price - a.mid_price);
        setMarkets(sorted);
        if (sorted.length > 0) setMkt((curr) => curr ?? sorted[0]);
      })
      .catch(() => {
        getMarket(rawTicker)
          .then((market: KalshiMarket) => {
            setMkt(market);
            setMarkets([market]);
          })
          .catch(() => {});
      });
  }, [rawTicker, savedId]);

  const displayTitle = eventTitle || savedEventTitle;
  const displayCat = evCat || savedEvCat;
  const displaySub = evSub || savedEvSub;
  const primaryMarket = mkt ?? markets[0] ?? null;
  const summaryCloseDate = primaryMarket?.close_date ?? "";
  const summaryRules = primaryMarket?.rules_primary ?? "";
  const summaryVolume = markets.length > 1
    ? markets.reduce((sum, market) => sum + market.volume, 0)
    : (primaryMarket?.volume ?? 0);
  const selectedImpliedProbability = mkt?.mid_price ?? 0;
  const relatedMarkets = markets.map((market) => ({
    ticker: market.ticker,
    label: market.yes_sub_title || market.ticker,
    question: market.question,
    market_price: market.mid_price,
  }));

  const runForecast = useCallback(() => {
    if (!mkt) return;
    setPhase("running");
    setProgressLabel(PROGRESS_STEPS[0].label);
    setMemo(null);
    setIvData(null);
    setErrorMsg("");
    cancelRef.current = streamForecast(
      {
        ticker: mkt.ticker,
        event_title: displayTitle,
        ev_sub: displaySub,
        ev_category: displayCat,
        market: mkt as unknown as Record<string, unknown>,
        related_markets: relatedMarkets,
      },
      (msg: StreamMessage) => {
        if (msg.type === "progress") {
          setProgressLabel(msg.label);
        } else if (msg.type === "iv_complete") {
          const allFor = [...new Set(msg.agent_forecasts.flatMap((a) => a.key_factors_for))].slice(0, 5);
          const allAgainst = [...new Set(msg.agent_forecasts.flatMap((a) => a.key_factors_against))].slice(0, 5);
          setIvData({ key_factors_for: allFor, key_factors_against: allAgainst });
        } else if (msg.type === "complete") {
          setMemo(msg.memo);
          setKalshiPrice(msg.kalshi_price);
          setPhase("done");
        } else if (msg.type === "error") {
          setErrorMsg(msg.message);
          setPhase("error");
        }
      },
    );
  }, [displayCat, displaySub, displayTitle, mkt, relatedMarkets]);

  useEffect(() => {
    if (!shouldAutoRun || !mkt || savedId || hasAutoRunRef.current) return;
    hasAutoRunRef.current = true;
    runForecast();
  }, [mkt, runForecast, savedId, shouldAutoRun]);

  const progressIndex = getProgressIndex(progressLabel);
  const verdict = memo ? getVerdict(memo.final_probability, kalshiPrice) : null;
  const confidence = memo ? getConfidenceLabel(memo) : "Medium";
  const keyReasons = summarizeReasons(memo, ivData);
  const evidence = memo ? memo.agent_forecasts.flatMap((agent) => agent.evidence_ledger.items) : [];
  const hasMultipleOptions = markets.length > 1;

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "920px", margin: "0 auto", padding: "84px 28px 96px" }}>
        <button
          onClick={() => router.push(backHref)}
          style={{
            background: "transparent",
            border: "none",
            padding: 0,
            fontFamily: "var(--font-mono), monospace",
            fontSize: "11px",
            color: "#4a4845",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            marginBottom: "28px",
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#8d8780")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#4a4845")}
        >
          ← {fromTrading ? "back to recommendations" : "home"}
        </button>

        {primaryMarket && (
          <section style={{
            background: "linear-gradient(180deg, rgba(19,19,19,0.96), rgba(10,10,10,0.96))",
            border: "1px solid #1d1d1d",
            borderRadius: "20px",
            padding: "28px",
            marginBottom: "24px",
            boxShadow: "0 18px 44px rgba(0,0,0,0.28)",
          }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "18px", marginBottom: "18px" }}>
              {displayCat && <SummaryPill>{displayCat}</SummaryPill>}
              {displaySub && <SummaryPill muted>{displaySub}</SummaryPill>}
              {summaryCloseDate && <SummaryPill muted>Closes {summaryCloseDate}</SummaryPill>}
              <SummaryPill muted>Volume {fmtVol(summaryVolume)}</SummaryPill>
            </div>

            <h1 style={{ fontSize: "34px", fontWeight: 700, color: "#f2ede7", lineHeight: 1.18, marginBottom: "18px" }}>
              {displayTitle || primaryMarket.question || rawTicker}
            </h1>

            {summaryRules && (
              <div style={{
                background: "#0b0b0b",
                border: "1px solid #1a1a1a",
                borderRadius: "14px",
                padding: "16px 18px",
              }}>
                <div style={{ fontSize: "14px", fontWeight: 600, color: "#c6beb4", marginBottom: "8px" }}>
                  Resolution rule
                </div>
                <div style={{ fontSize: "14px", color: "#8f8983", lineHeight: 1.7 }}>
                  {summaryRules}
                </div>
              </div>
            )}
          </section>
        )}

        {hasMultipleOptions && (
          <section style={{
            background: "#101010",
            border: "1px solid #1d1d1d",
            borderRadius: "20px",
            padding: "26px",
            marginBottom: "24px",
          }}>
            <div style={{ fontSize: "25px", fontWeight: 700, color: "#f2ede7", marginBottom: "8px" }}>
              Pick an outcome to analyze
            </div>
            <div style={{ fontSize: "15px", color: "#8c8680", lineHeight: 1.6, marginBottom: "20px" }}>
              Choose the outcome you might trade. Prism will compare the market’s implied odds with its own estimate.
            </div>

            <div style={{ display: "grid", gap: "14px" }}>
              {markets.map((market) => {
                const isSelected = mkt?.ticker === market.ticker;
                return (
                  <button
                    key={market.ticker}
                    onClick={() => {
                      setMkt(market);
                      setMemo(null);
                      setIvData(null);
                      setPhase("idle");
                      setErrorMsg("");
                    }}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      background: isSelected ? "rgba(227,100,56,0.08)" : "#131313",
                      border: `1px solid ${isSelected ? "#e36438" : "#242424"}`,
                      borderRadius: "16px",
                      padding: "18px 20px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "16px",
                      boxShadow: isSelected ? "0 0 0 1px rgba(227,100,56,0.22), 0 14px 34px rgba(227,100,56,0.10)" : "none",
                      transition: "all 0.18s ease",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.borderColor = "#353535";
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.borderColor = "#242424";
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "18px", fontWeight: 600, color: "#f2ede7", marginBottom: "6px" }}>
                        {market.yes_sub_title || market.ticker}
                      </div>
                      <div style={{ fontSize: "14px", color: "#98918b" }}>
                        {fmtPct(market.mid_price)} chance
                      </div>
                    </div>

                    <div style={{
                      flexShrink: 0,
                      padding: "7px 11px",
                      borderRadius: "999px",
                      border: `1px solid ${isSelected ? "#e36438" : "#2a2a2a"}`,
                      color: isSelected ? "#ff8b5f" : "#6f6963",
                      background: isSelected ? "rgba(227,100,56,0.12)" : "transparent",
                      fontSize: "12px",
                      fontWeight: 600,
                    }}>
                      {isSelected ? "Selected" : "Analyze"}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {mkt && (
          <section style={{
            background: "#101010",
            border: "1px solid #1d1d1d",
            borderRadius: "20px",
            padding: "26px",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", flexWrap: "wrap", marginBottom: "20px" }}>
              <div>
                <div style={{ fontSize: "24px", fontWeight: 700, color: "#f2ede7", marginBottom: "8px" }}>
                  {hasMultipleOptions ? (mkt.yes_sub_title || mkt.question || mkt.ticker) : "Yes"}
                </div>
                <div style={{ fontSize: "15px", color: "#8c8680" }}>
                  Market thinks {fmtPct(selectedImpliedProbability)}
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                {phase !== "running" && (
                  <button
                    onClick={runForecast}
                    style={{
                      background: "#e36438",
                      color: "#fff",
                      border: "none",
                      borderRadius: "12px",
                      padding: "14px 18px",
                      fontSize: "14px",
                      fontWeight: 700,
                      boxShadow: "0 12px 24px rgba(227,100,56,0.22)",
                    }}
                  >
                    {phase === "done" ? "Refresh analysis" : "Run analysis"}
                  </button>
                )}
              </div>
            </div>

            {categoryStats && phase === "idle" && (
              <div style={{
                marginBottom: "18px",
                fontSize: "13px",
                color: "#6f6963",
                background: "#0b0b0b",
                border: "1px solid #1a1a1a",
                borderRadius: "12px",
                padding: "12px 14px",
              }}>
                Prism found tradable edge in {categoryStats.edge} of {categoryStats.total}
                {categoryStats.isCategory && displayCat ? ` recent ${displayCat} forecasts` : " recent forecasts"}.
              </div>
            )}

            {phase === "error" && (
              <div style={{
                padding: "14px 16px",
                background: "#180a0a",
                border: "1px solid #3a1515",
                borderRadius: "14px",
                marginBottom: "18px",
                fontSize: "14px",
                color: "#f29b9b",
              }}>
                {errorMsg}
              </div>
            )}

            {phase === "idle" && (
              <EmptyAnalysisState optionName={hasMultipleOptions ? (mkt.yes_sub_title || mkt.ticker) : "Yes"} impliedProbability={selectedImpliedProbability} />
            )}

            {phase === "running" && (
              <ProgressFeed progressIndex={progressIndex} progressLabel={progressLabel} />
            )}

            {phase === "done" && memo && (
              <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
                <ResultHero
                  prismProbability={memo.final_probability}
                  marketProbability={kalshiPrice}
                  verdict={verdict ?? "Not enough edge"}
                  confidence={confidence}
                />

                {keyReasons.length > 0 && (
                  <section style={{
                    background: "#0b0b0b",
                    border: "1px solid #1a1a1a",
                    borderRadius: "16px",
                    padding: "18px 20px",
                  }}>
                    <div style={{ fontSize: "18px", fontWeight: 700, color: "#f2ede7", marginBottom: "12px" }}>
                      Why Prism sees it this way
                    </div>
                    <div style={{ display: "grid", gap: "10px" }}>
                      {keyReasons.map((reason, idx) => (
                        <div key={idx} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
                          <div style={{ width: "7px", height: "7px", borderRadius: "999px", background: "#e36438", marginTop: "8px", flexShrink: 0 }} />
                          <div style={{ fontSize: "14px", color: "#b7b0aa", lineHeight: 1.6 }}>{reason}</div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                <details style={{
                  background: "#0b0b0b",
                  border: "1px solid #1a1a1a",
                  borderRadius: "16px",
                  overflow: "hidden",
                }}>
                  <summary style={{
                    padding: "18px 20px",
                    cursor: "pointer",
                    listStyle: "none",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    color: "#e8e1d9",
                    fontSize: "16px",
                    fontWeight: 700,
                  }}>
                    View full reasoning
                    <span style={{ color: "#7e7872", fontSize: "14px" }}>Expand</span>
                  </summary>

                  <div style={{ padding: "0 20px 20px", display: "flex", flexDirection: "column", gap: "14px" }}>
                    <ReasoningBlock title="Why it might happen">
                      <BulletList items={ivData?.key_factors_for ?? []} emptyText="No strong upside drivers were surfaced." />
                    </ReasoningBlock>

                    <ReasoningBlock title="Why it might not">
                      <BulletList items={ivData?.key_factors_against ?? []} emptyText="No major downside drivers were surfaced." />
                    </ReasoningBlock>

                    <ReasoningBlock title="What could change this">
                      <div style={{ fontSize: "14px", color: "#a79f97", lineHeight: 1.7 }}>
                        {memo.supervisor_reconciliation.reconciliation_reasoning}
                      </div>
                    </ReasoningBlock>

                    <ReasoningBlock title="Sources">
                      {evidence.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          {evidence.map((item, i) => {
                            const c = DIR_COLORS[item.direction] ?? "#6b6865";
                            return (
                              <div key={i} style={{
                                borderLeft: `2px solid ${c}`,
                                paddingLeft: "12px",
                                paddingTop: "6px",
                                paddingBottom: "6px",
                              }}>
                                <div style={{ fontSize: "13px", color: "#eee6de", lineHeight: 1.55, marginBottom: "4px" }}>
                                  {item.claim}
                                </div>
                                <a href={item.source_url} target="_blank" style={{ fontSize: "12px", color: "#8f867f", textDecoration: "underline" }}>
                                  {item.source_title}
                                </a>
                                {item.relevant_quote_or_snippet && (
                                  <div style={{ fontSize: "12px", color: "#6f6963", fontStyle: "italic", marginTop: "4px", lineHeight: 1.6 }}>
                                    “{item.relevant_quote_or_snippet.slice(0, 180)}”
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div style={{ fontSize: "14px", color: "#6f6963" }}>No sources captured.</div>
                      )}
                    </ReasoningBlock>
                  </div>
                </details>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function getProgressIndex(label: string) {
  const lower = label.toLowerCase();
  if (lower.includes("base rate") || lower.includes("rules")) return 0;
  if (lower.includes("evidence") || lower.includes("collecting")) return 1;
  if (lower.includes("analyzing") || lower.includes("comparing")) return 2;
  if (lower.includes("drawing conclusions") || lower.includes("final")) return 3;
  return 0;
}

function getVerdict(prismProbability: number, marketProbability: number) {
  const edge = prismProbability - marketProbability;
  const absEdge = Math.abs(edge);
  if (absEdge < 0.03) return "Looks fairly priced";
  if (absEdge < 0.06) return "Not enough edge";
  return edge > 0 ? "Looks underpriced" : "Looks overpriced";
}

function getConfidenceLabel(memo: ForecastMemo) {
  const values = memo.agent_forecasts.map((agent) => agent.epistemic_confidence ?? "medium");
  const high = values.filter((v) => v === "high").length;
  const low = values.filter((v) => v === "low").length;
  if (high >= Math.max(1, Math.ceil(values.length / 2))) return "High";
  if (low >= Math.max(1, Math.ceil(values.length / 2))) return "Low";
  return "Medium";
}

function summarizeReasons(memo: ForecastMemo | null, ivData: IVData | null) {
  if (!memo) return [];
  const reasons = [
    ...(ivData?.key_factors_for ?? []).slice(0, 2),
    ...(ivData?.key_factors_against ?? []).slice(0, 1).map((item) => `Risk to watch: ${item}`),
  ];
  return reasons.slice(0, 3);
}

function SummaryPill({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <div style={{
      padding: "8px 12px",
      borderRadius: "999px",
      border: `1px solid ${muted ? "#272727" : "#513528"}`,
      background: muted ? "#111111" : "rgba(227,100,56,0.08)",
      color: muted ? "#969089" : "#f08b64",
      fontSize: "13px",
      fontWeight: 600,
    }}>
      {children}
    </div>
  );
}

function EmptyAnalysisState({ optionName, impliedProbability }: { optionName: string; impliedProbability: number }) {
  return (
    <div style={{
      background: "#0b0b0b",
      border: "1px solid #1a1a1a",
      borderRadius: "16px",
      padding: "24px",
    }}>
      <div style={{ fontSize: "20px", fontWeight: 700, color: "#f2ede7", marginBottom: "8px" }}>
        Analyze {optionName}
      </div>
      <div style={{ fontSize: "15px", color: "#8c8680", lineHeight: 1.7 }}>
        Market thinks this outcome has a {fmtPct(impliedProbability)} chance. Run Prism’s analysis to see whether that price looks attractive.
      </div>
    </div>
  );
}

function ProgressFeed({ progressIndex, progressLabel }: { progressIndex: number; progressLabel: string }) {
  return (
    <div style={{
      background: "#0b0b0b",
      border: "1px solid #1a1a1a",
      borderRadius: "16px",
      padding: "20px",
      display: "flex",
      flexDirection: "column",
      gap: "12px",
    }}>
      <div style={{ fontSize: "20px", fontWeight: 700, color: "#f2ede7", marginBottom: "2px" }}>
        Prism is working through the trade
      </div>
      <div style={{ fontSize: "14px", color: "#8a837d", marginBottom: "6px" }}>
        {progressLabel}
      </div>
      {PROGRESS_STEPS.map((step, idx) => {
        const state = idx < progressIndex ? "done" : idx === progressIndex ? "active" : "upcoming";
        return (
          <div
            key={step.key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              padding: "12px 14px",
              borderRadius: "12px",
              border: `1px solid ${state === "active" ? "#3f2b22" : "#171717"}`,
              background: state === "active" ? "rgba(227,100,56,0.07)" : "#101010",
            }}
          >
            <div style={{
              width: "22px",
              height: "22px",
              borderRadius: "999px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "11px",
              fontWeight: 700,
              color: state === "done" ? "#06140b" : state === "active" ? "#f2ede7" : "#726c66",
              background: state === "done" ? "#4ade80" : state === "active" ? "#e36438" : "#181818",
            }}>
              {state === "done" ? "✓" : idx + 1}
            </div>
            <div style={{ fontSize: "14px", color: state === "upcoming" ? "#716b65" : "#ece5dd" }}>
              {step.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ResultHero({
  prismProbability,
  marketProbability,
  verdict,
  confidence,
}: {
  prismProbability: number;
  marketProbability: number;
  verdict: string;
  confidence: string;
}) {
  const edge = prismProbability - marketProbability;
  const verdictColor = edge > 0.06 ? "#4ade80" : edge < -0.06 ? "#f87171" : "#fbbf24";

  return (
    <div style={{
      background: "linear-gradient(180deg, rgba(227,100,56,0.08), rgba(14,14,14,0.98))",
      border: "1px solid #2a1f1a",
      borderRadius: "18px",
      padding: "22px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "18px", flexWrap: "wrap", marginBottom: "18px" }}>
        <div>
          <div style={{ fontSize: "15px", color: "#9d958d", marginBottom: "8px" }}>Is this a good bet?</div>
          <div style={{ fontSize: "28px", fontWeight: 700, color: verdictColor, lineHeight: 1.15 }}>
            {verdict}
          </div>
        </div>
        <div style={{
          padding: "8px 12px",
          borderRadius: "999px",
          background: "#101010",
          border: "1px solid #242424",
          color: "#d7cfc6",
          fontSize: "13px",
          fontWeight: 600,
          height: "fit-content",
        }}>
          Confidence: {confidence}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        <StatCard title="Prism estimate" value={fmtPct(prismProbability)} accent="#e36438" />
        <StatCard title="Market thinks" value={fmtPct(marketProbability)} accent="#8b847d" />
      </div>
    </div>
  );
}

function StatCard({ title, value, accent }: { title: string; value: string; accent: string }) {
  return (
    <div style={{
      background: "#0b0b0b",
      border: "1px solid #171717",
      borderRadius: "14px",
      padding: "16px",
    }}>
      <div style={{ fontSize: "13px", color: "#8a837d", marginBottom: "8px" }}>{title}</div>
      <div style={{ fontFamily: "var(--font-mono), monospace", fontSize: "34px", fontWeight: 700, color: accent, lineHeight: 1 }}>
        {value}
      </div>
    </div>
  );
}

function ReasoningBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{
      background: "#101010",
      border: "1px solid #181818",
      borderRadius: "14px",
      padding: "16px",
    }}>
      <div style={{ fontSize: "16px", fontWeight: 700, color: "#ece5dd", marginBottom: "10px" }}>
        {title}
      </div>
      {children}
    </section>
  );
}

function BulletList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (items.length === 0) {
    return <div style={{ fontSize: "14px", color: "#6f6963" }}>{emptyText}</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {items.map((item, idx) => (
        <div key={idx} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
          <div style={{ width: "6px", height: "6px", borderRadius: "999px", background: "#e36438", marginTop: "8px", flexShrink: 0 }} />
          <div style={{ fontSize: "14px", color: "#b7b0aa", lineHeight: 1.6 }}>{item}</div>
        </div>
      ))}
    </div>
  );
}
