"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Header from "@/components/Header";
import { getMarket, getMarkets } from "@/lib/api";
import { addMarketToManualBasketDraft } from "@/lib/manualBasketDraft";
import type { KalshiMarket } from "@/lib/types";

function fmtVol(v: number) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

function fmtPct(p: number) {
  return `${Math.round(p * 100)}%`;
}

export default function MarketPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const rawTicker = params.ticker as string;
  const eventTitle = searchParams.get("title") ?? "";
  const evCat = searchParams.get("cat") ?? "";
  const evSub = searchParams.get("sub") ?? "";
  const fromManual = searchParams.get("from") === "manual";
  const fromTrading = searchParams.get("from") === "trading";
  const fromSession = searchParams.get("session");
  const backHref = fromTrading
    ? `/trading${fromSession ? `?session=${fromSession}` : ""}`
    : fromManual
      ? "/trading/manual"
      : "/";

  const [markets, setMarkets] = useState<KalshiMarket[]>([]);
  const [selectedMarket, setSelectedMarket] = useState<KalshiMarket | null>(null);
  const [basketNotice, setBasketNotice] = useState("");

  useEffect(() => {
    getMarkets(rawTicker)
      .then((mkts: KalshiMarket[]) => {
        const sorted = [...mkts].sort((a, b) => b.mid_price - a.mid_price);
        setMarkets(sorted);
        if (sorted.length > 0) setSelectedMarket(sorted[0]);
      })
      .catch(() => {
        getMarket(rawTicker)
          .then((market: KalshiMarket) => {
            setMarkets([market]);
            setSelectedMarket(market);
          })
          .catch(() => {});
      });
  }, [rawTicker]);

  const primaryMarket = selectedMarket ?? markets[0] ?? null;
  const summaryCloseDate = primaryMarket?.close_date ?? "";
  const summaryVolume = markets.length > 1
    ? markets.reduce((sum, market) => sum + market.volume, 0)
    : (primaryMarket?.volume ?? 0);
  const options = useMemo(() => [...markets].sort((a, b) => b.mid_price - a.mid_price), [markets]);

  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "84px 24px 96px" }}>
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
          ← {fromTrading ? "back to recommendations" : fromManual ? "back to manual build" : "home"}
        </button>

        {primaryMarket && (
          <section style={{
            background: "linear-gradient(180deg, rgba(20,20,20,0.97), rgba(10,10,10,0.98))",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "24px",
            padding: "28px",
            marginBottom: "22px",
            boxShadow: "0 20px 50px rgba(0,0,0,0.32)",
          }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "18px" }}>
              {evCat && <SummaryPill>{evCat}</SummaryPill>}
              {evSub && <SummaryPill muted>{evSub}</SummaryPill>}
              {summaryCloseDate && <SummaryPill muted>Closes {summaryCloseDate}</SummaryPill>}
              <SummaryPill muted>Volume {fmtVol(summaryVolume)}</SummaryPill>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 260px", gap: "20px", alignItems: "start" }}>
              <div>
                <h1 style={{ fontSize: "clamp(30px, 4vw, 42px)", fontWeight: 700, color: "#f2ede7", lineHeight: 1.08, letterSpacing: "-0.04em", margin: "0 0 12px" }}>
                  {eventTitle || primaryMarket.question || rawTicker}
                </h1>
                <div style={{ color: "#918981", fontSize: "15px", lineHeight: 1.7 }}>
                  Review the event rules, compare the available answer options, and add the contract you want to your basket.
                </div>
              </div>

              {fromManual && (
                <div style={{
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: "18px",
                  padding: "18px",
                  background: "rgba(255,255,255,0.03)",
                }}>
                  <div style={{ color: "#8f877e", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace", marginBottom: "10px" }}>
                    Selected Option
                  </div>
                  <div style={{ color: "#ede9e3", fontSize: "18px", fontWeight: 600, lineHeight: 1.35, marginBottom: "8px" }}>
                    {primaryMarket.yes_sub_title || primaryMarket.question}
                  </div>
                  <div style={{ color: "#9f978f", fontSize: "14px", marginBottom: "14px" }}>
                    {fmtPct(primaryMarket.mid_price)} implied probability
                  </div>
                  <button
                    onClick={() => {
                      const added = addMarketToManualBasketDraft(primaryMarket);
                      setBasketNotice(added ? "Added to basket." : "Already in basket.");
                    }}
                    style={{
                      width: "100%",
                      background: "linear-gradient(180deg, #f07a4b, #d95426)",
                      color: "#fff",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: "12px",
                      padding: "13px 16px",
                      fontSize: "13px",
                      fontWeight: 700,
                    }}
                  >
                    Add selected option
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.2fr) minmax(320px,0.9fr)", gap: "20px", alignItems: "start" }}>
          <section style={{
            background: "#101010",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "22px",
            padding: "24px",
          }}>
            <div style={{ fontSize: "22px", fontWeight: 700, color: "#f2ede7", marginBottom: "8px" }}>
              Answer options
            </div>
            <div style={{ fontSize: "14px", color: "#8c8680", lineHeight: 1.6, marginBottom: "18px" }}>
              Pick the contract you want exposure to. Multi-option events list each outcome separately.
            </div>

            <div style={{ display: "grid", gap: "12px" }}>
              {options.map((market) => {
                const isSelected = selectedMarket?.ticker === market.ticker;
                return (
                  <div
                    key={market.ticker}
                    style={{
                      border: `1px solid ${isSelected ? "rgba(227,100,56,0.42)" : "rgba(255,255,255,0.08)"}`,
                      borderRadius: "18px",
                      padding: "18px",
                      background: isSelected ? "rgba(227,100,56,0.08)" : "rgba(255,255,255,0.02)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "14px", alignItems: "start", marginBottom: "10px" }}>
                      <div>
                        <div style={{ color: "#ede9e3", fontSize: "18px", fontWeight: 600, lineHeight: 1.35, marginBottom: "6px" }}>
                          {market.yes_sub_title || market.ticker}
                        </div>
                        <div style={{ color: "#9c948c", fontSize: "14px" }}>
                          {fmtPct(market.mid_price)} chance
                        </div>
                      </div>
                      <button
                        onClick={() => setSelectedMarket(market)}
                        style={{
                          borderRadius: "999px",
                          border: `1px solid ${isSelected ? "#e36438" : "rgba(255,255,255,0.10)"}`,
                          background: isSelected ? "rgba(227,100,56,0.12)" : "transparent",
                          color: isSelected ? "#ff8b5f" : "#8c847c",
                          padding: "7px 11px",
                          fontSize: "12px",
                          fontWeight: 600,
                        }}
                      >
                        {isSelected ? "Selected" : "Select"}
                      </button>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                      <div style={{ color: "#7c746c", fontSize: "12px" }}>
                        Closes {market.close_date} · Volume {fmtVol(market.volume)}
                      </div>
                      {fromManual && (
                        <button
                          onClick={() => {
                            const added = addMarketToManualBasketDraft(market);
                            setBasketNotice(added ? "Added to basket." : "Already in basket.");
                          }}
                          style={{
                            borderRadius: "10px",
                            border: "1px solid rgba(227,100,56,0.24)",
                            background: "rgba(227,100,56,0.08)",
                            color: "#ede9e3",
                            padding: "9px 12px",
                            fontSize: "12px",
                            fontWeight: 700,
                          }}
                        >
                          Add to basket
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {fromManual && basketNotice && (
              <div style={{
                marginTop: "14px",
                borderRadius: "12px",
                border: "1px solid rgba(227,100,56,0.18)",
                background: "rgba(227,100,56,0.06)",
                padding: "12px 14px",
                color: "#c9beb2",
                fontSize: "13px",
              }}>
                {basketNotice}
              </div>
            )}
          </section>

          <section style={{ display: "grid", gap: "20px" }}>
            {primaryMarket?.rules_primary && (
              <div style={{
                background: "#101010",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "22px",
                padding: "24px",
              }}>
                <div style={{ fontSize: "19px", fontWeight: 700, color: "#f2ede7", marginBottom: "10px" }}>
                  Resolution rule
                </div>
                <div style={{ fontSize: "14px", color: "#9b938b", lineHeight: 1.75 }}>
                  {primaryMarket.rules_primary}
                </div>
              </div>
            )}

            <div style={{
              background: "#101010",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "22px",
              padding: "24px",
            }}>
              <div style={{ fontSize: "19px", fontWeight: 700, color: "#f2ede7", marginBottom: "12px" }}>
                Selected option details
              </div>
              {primaryMarket ? (
                <div style={{ display: "grid", gap: "12px" }}>
                  <DetailRow label="Option" value={primaryMarket.yes_sub_title || primaryMarket.question} />
                  <DetailRow label="Implied probability" value={fmtPct(primaryMarket.mid_price)} />
                  <DetailRow label="Close date" value={primaryMarket.close_date} />
                  <DetailRow label="Volume" value={fmtVol(primaryMarket.volume)} />
                  <DetailRow label="Question" value={primaryMarket.question} />
                </div>
              ) : (
                <div style={{ color: "#7f776f", fontSize: "14px" }}>No market loaded.</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
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

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "#7b746d", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono), monospace", marginBottom: "5px" }}>
        {label}
      </div>
      <div style={{ color: "#e1dbd3", fontSize: "14px", lineHeight: 1.6 }}>
        {value}
      </div>
    </div>
  );
}
