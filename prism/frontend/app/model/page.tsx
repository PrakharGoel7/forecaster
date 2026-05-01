"use client";
import Header from "@/components/Header";

const INTEL_STEPS = [
  {
    id: "01",
    title: "Question Parser",
    color: "#e36438",
    description: "Decomposes the raw market ticker into its structural components — what must happen for YES, the natural reference class, and the most informative searches — so downstream agents start with a precise problem.",
  },
  {
    id: "02",
    title: "Independent Forecasting Agents",
    color: "#5b9cf6",
    description: "An ensemble of agents research in parallel, each anchoring on historical base rates before updating with current evidence. Working in isolation, their disagreements surface genuine uncertainty rather than herding.",
  },
  {
    id: "03",
    title: "Supervisor Reconciliation",
    color: "#9b9790",
    description: "Reviews all agent estimates and either aggregates them directly or resolves the specific factual crux driving disagreement before weighting agents by evidence quality.",
  },
  {
    id: "04",
    title: "Calibration",
    color: "#4ade80",
    description: "Passes the reconciled estimate through a Platt scaling transform to correct for LLMs' tendency to cluster near 50%, stretching well-supported estimates toward the extremes.",
  },
];

const COMPASS_STEPS = [
  {
    id: "01",
    title: "Belief Elicitor",
    color: "#e36438",
    description: "Interviews you with three focused questions — after first searching the web so it never asks things it can look up. Outputs a structured belief summary: core thesis, time horizon, key drivers, and scope.",
  },
  {
    id: "02",
    title: "Domain Analyst",
    color: "#a78bfa",
    description: "Maps your belief's ramifications across 16 domains via causal chains, surfacing second and third-order effects a keyword search would miss — a conflict thesis shouldn't only find geopolitics markets.",
  },
  {
    id: "03",
    title: "Market Screener",
    color: "#fbbf24",
    description: "Reads the full Kalshi event catalog and uses the domain impact map — not keyword matching — to shortlist 20–35 relevant events, erring on the side of inclusion.",
  },
  {
    id: "04",
    title: "Market Curator",
    color: "#4ade80",
    description: "Selects 5–8 positions optimised for relevance, variety across belief dimensions, and conviction match — specifying YES or NO and why the current price is interesting given your thesis.",
  },
];

function PipelineColumn({ steps }: { steps: typeof INTEL_STEPS }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
      {steps.map((step, i) => (
        <div key={step.id}>
          <div style={{
            background: "rgba(18,18,18,0.98)", border: "1px solid #272727",
            borderRadius: "14px", padding: "22px 24px",
            position: "relative", overflow: "hidden",
          }}>
            <div style={{
              position: "absolute", left: 0, top: 0, bottom: 0, width: "3px",
              background: step.color, opacity: 0.8,
            }} />
            <div style={{ display: "flex", gap: "16px", alignItems: "flex-start" }}>
              <div style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                fontWeight: 700, color: step.color, flexShrink: 0,
                paddingTop: "3px", letterSpacing: "0.1em",
              }}>
                {step.id}
              </div>
              <div>
                <h2 style={{ fontSize: "14px", fontWeight: 700, color: "#ede9e3", marginBottom: "8px" }}>
                  {step.title}
                </h2>
                <p style={{ fontSize: "12px", color: "#6b6865", lineHeight: 1.75 }}>
                  {step.description}
                </p>
              </div>
            </div>
          </div>
          {i < steps.length - 1 && (
            <div style={{
              display: "flex", justifyContent: "center", padding: "5px 0",
              fontFamily: "var(--font-mono), monospace", fontSize: "13px", color: "#1e1e1e",
            }}>↓</div>
          )}
        </div>
      ))}
    </div>
  );
}

function ColumnHeader({ label, subtitle, accent }: { label: string; subtitle: string; accent: string }) {
  return (
    <div style={{ marginBottom: "20px" }}>
      <div style={{
        display: "inline-flex", alignItems: "center", gap: "8px",
        fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.22em", color: accent,
        padding: "5px 12px",
        border: `1px solid ${accent}30`,
        borderRadius: "20px",
        background: `${accent}08`,
        marginBottom: "10px",
      }}>
        {label}
      </div>
      <p style={{ fontSize: "12px", color: "#4a4845", lineHeight: 1.65 }}>{subtitle}</p>
    </div>
  );
}

export default function ModelPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "80px 32px 100px" }}>

        {/* Page header */}
        <div style={{ marginBottom: "52px", maxWidth: "600px" }}>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.2em", color: "#9b9790", marginBottom: "8px",
          }}>
            Model Architecture
          </div>
          <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em", marginBottom: "14px" }}>
            How Prism Works
          </h1>
          <p style={{ fontSize: "14px", color: "#6b6865", lineHeight: 1.75 }}>
            Prism runs two intelligence pipelines.{" "}
            <span style={{ color: "#e36438" }}>Intel</span> forecasts the probability of a market resolving YES.{" "}
            <span style={{ color: "#a78bfa" }}>Compass</span> maps your beliefs about the future to the best prediction market positions to express them.
          </p>
        </div>

        {/* Two-column layout */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "32px",
          alignItems: "start",
        }}>
          <div>
            <ColumnHeader
              label="Intel — How Prism Forecasts"
              subtitle="Every forecast runs a four-stage pipeline — parsing, parallel research, reconciliation, and calibration."
              accent="#e36438"
            />
            <PipelineColumn steps={INTEL_STEPS} />
          </div>

          <div>
            <ColumnHeader
              label="Compass — How Prism Trades"
              subtitle="Compass converts a freeform belief about the future into a curated portfolio of prediction market positions."
              accent="#a78bfa"
            />
            <PipelineColumn steps={COMPASS_STEPS} />
          </div>
        </div>

      </div>
    </div>
  );
}
