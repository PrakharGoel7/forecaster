"use client";
import Header from "@/components/Header";

const ETF_STEPS = [
  {
    id: "01",
    title: "Belief Elicitor",
    color: "#4f46e5",
    description: "Clarifies the user's future thesis in instant or thinking mode, producing a structured brief with a resolution target, timeframe, mechanism, and key drivers.",
  },
  {
    id: "02",
    title: "Domain Analyst",
    color: "#a78bfa",
    description: "Maps the thesis across major domains and causal chains so Prism can separate direct exposure from indirect implications, hedges, and falsifiers.",
  },
  {
    id: "03",
    title: "Market Screener",
    color: "#fbbf24",
    description: "Screens the Kalshi event catalog using the structured thesis and domain map to shortlist markets that provide meaningful thematic exposure.",
  },
  {
    id: "04",
    title: "Basket Builder",
    color: "#4ade80",
    description: "Constructs a weighted $100 prediction market ETF with direct holdings, mechanism bets, indirect implications, and selective hedge positions.",
  },
];

function PipelineColumn({ steps }: { steps: typeof ETF_STEPS }) {
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
        <div style={{ marginBottom: "52px" }}>
          <h1 style={{ fontSize: "56px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.03em" }}>
            How Prism Works
          </h1>
        </div>

        <div style={{ maxWidth: "760px" }}>
          <ColumnHeader
            label="Prediction Market ETFs"
            subtitle="Prism converts a freeform belief about the future into a weighted, shareable thematic basket of Kalshi contracts."
            accent="#a78bfa"
          />
          <PipelineColumn steps={ETF_STEPS} />
        </div>

      </div>
    </div>
  );
}
