"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { getBasket } from "@/lib/api";
import type { BeliefAnalysis, BeliefSummary, PredictionBasket, SavedBasket } from "@/lib/types";

export default function BasketSharePage() {
  const params = useParams<{ id: string }>();
  const [basket, setBasket] = useState<SavedBasket | null>(null);
  const [beliefSummary, setBeliefSummary] = useState<BeliefSummary | null>(null);
  const [analysis, setAnalysis] = useState<BeliefAnalysis | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    getBasket(Number(params.id)).then((saved) => {
      setBasket(saved);
      setBeliefSummary(JSON.parse(saved.belief_summary_json));
      setAnalysis(JSON.parse(saved.analysis_json));
    }).catch(() => {});
  }, [params]);

  if (!basket) {
    return (
      <div style={{ minHeight: "100vh", background: "#f8f6f2", color: "#1c1814" }}>
        <Header />
        <GridOverlay />
        <div style={{ position: "relative", zIndex: 10, maxWidth: 900, margin: "0 auto", padding: "120px 24px" }}>
          Loading basket…
        </div>
      </div>
    );
  }

  const parsedBasket = JSON.parse(basket.basket_json);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 960, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 14 }}>
          Shared Prediction Market ETF
        </div>
        <h1 style={{ color: "#1c1814", fontSize: "clamp(34px, 5vw, 56px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 10px" }}>
          {basket.title}
        </h1>
        <p style={{ color: "#6e675f", fontSize: 17, lineHeight: 1.65, margin: "0 0 26px", maxWidth: 780 }}>
          {basket.summary}
        </p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
          <Tag>{basket.mode}</Tag>
          <Tag>{parsedBasket.holdings.length} positions</Tag>
          <Tag>{basket.timeframe_start || "now"} → {basket.timeframe_end || basket.time_horizon}</Tag>
        </div>

        <section style={sectionStyle}>
          <div style={sectionTitleStyle}>Thesis</div>
          <div style={{ color: "#1c1814", fontSize: 24, fontWeight: 600, marginBottom: 10 }}>{beliefSummary?.core_belief}</div>
          <div style={{ color: "#6e675f", lineHeight: 1.7 }}>
            <strong style={{ color: "#2e2924" }}>Resolution target:</strong> {beliefSummary?.resolution_target}<br />
            <strong style={{ color: "#2e2924" }}>Mechanism:</strong> {beliefSummary?.mechanism}
          </div>
        </section>

        <section style={sectionStyle}>
          <div style={sectionTitleStyle}>Holdings</div>
          <div style={{ display: "grid", gap: 12 }}>
        {(parsedBasket as PredictionBasket).holdings.map((holding) => (
              <div key={holding.ticker} style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 18, padding: 18, background: "rgba(0,0,0,0.02)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 100px", gap: 16 }}>
                  <div>
                    <div style={{ color: "#1c1814", fontWeight: 600, fontSize: 18, marginBottom: 8 }}>{holding.question}</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                      <Tag>{holding.side}</Tag>
                      <Tag>{holding.topic_bucket || holding.fit_type?.replace(/_/g, " ") || "position"}</Tag>
                      <Tag>{Math.round(holding.market_price * 100)}% market odds</Tag>
                    </div>
                    <div style={{ color: "#6e675f", lineHeight: 1.6 }}>{holding.rationale}</div>
                  </div>
                  <div style={{ textAlign: "right", color: "#1c1814", fontSize: 30, fontWeight: 600 }}>
                    {Math.round((holding.weight_dollars / parsedBasket.total_notional) * 100)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {analysis?.most_surprising_connection && (
          <section style={sectionStyle}>
            <div style={sectionTitleStyle}>What Could Change It</div>
            <div style={{ color: "#6e675f", lineHeight: 1.7 }}>{analysis.most_surprising_connection}</div>
          </section>
        )}

        <div style={{ marginTop: 28 }}>
          <Link href={`/trading?basket=${basket.id}`} style={{ color: "#e36438", textDecoration: "none", fontWeight: 600 }}>
            Open in builder
          </Link>
        </div>
      </div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 22,
  padding: 22,
  boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
  marginTop: 18,
};

const sectionTitleStyle: React.CSSProperties = {
  color: "#e36438",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 12,
};

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "5px 9px",
      borderRadius: 999,
      border: "1px solid rgba(255,255,255,0.08)",
      color: "#3a3530",
      fontSize: 12,
      background: "rgba(0,0,0,0.03)",
    }}>
      {children}
    </span>
  );
}
