"use client";
import Header from "@/components/Header";

const STEPS = [
  {
    id: "01",
    title: "Question Parser",
    color: "#e36438",
    description: "Before any research begins, a dedicated parsing stage decomposes the raw market into its structural components. It identifies what exactly needs to happen for the question to resolve YES, what the natural reference class is, what the key unknowns are, and what searches would be most informative. It draws on context from all three levels of the Kalshi hierarchy — series, event, and market — so downstream agents start with a precise, well-framed problem rather than a truncated ticker label.",
  },
  {
    id: "02",
    title: "Independent Forecasting Agents",
    color: "#5b9cf6",
    description: "An army of agents run in parallel, each starting from the same parsed question but reasoning independently. Every agent follows the same discipline: anchor on the outside view first by finding historical base rates for this type of event, then update with inside-view evidence specific to the current situation. Agents browse the web, read sources, and record evidence to a ledger as they go. Because they work in isolation, their disagreements surface genuine uncertainty rather than herding.",
  },
  {
    id: "03",
    title: "Supervisor Reconciliation",
    color: "#9b9790",
    description: "A supervisor reviews all three agent estimates alongside their full reasoning and evidence. If the estimates are close, it aggregates them directly. If they diverge, it identifies the specific factual crux driving the disagreement, runs targeted searches to resolve it, and weights the agents by the quality of their evidence rather than averaging blindly. The result is a single reconciled probability with an explicit explanation of what drove it.",
  },
  {
    id: "04",
    title: "Calibration",
    color: "#4ade80",
    description: "The reconciled probability is passed through a Platt scaling transform before being shown. Raw LLM probability estimates tend to cluster near 50% — expressing uncertainty as agnosticism rather than as a genuine base rate. The calibration step corrects for this by stretching well-supported estimates toward the extremes, bringing the distribution closer to what a historically-calibrated forecaster would produce.",
  },
];

export default function ModelPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#080808" }}>
      <Header />
      <div style={{ maxWidth: "760px", margin: "0 auto", padding: "80px 32px 100px" }}>

        <div style={{ marginBottom: "56px" }}>
          <div style={{
            fontFamily: "var(--font-mono), monospace", fontSize: "9px", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.2em", color: "#9b9790", marginBottom: "8px",
          }}>
            Model Architecture
          </div>
          <h1 style={{ fontSize: "26px", fontWeight: 700, color: "#ede9e3", letterSpacing: "-0.01em", marginBottom: "14px" }}>
            How Prism Forecasts
          </h1>
          <p style={{ fontSize: "14px", color: "#6b6865", lineHeight: 1.75 }}>
            Every forecast runs a four-stage pipeline — parsing, parallel research, reconciliation, and calibration.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {STEPS.map((step, i) => (
            <div key={step.id}>
              <div style={{
                background: "rgba(18,18,18,0.98)", border: "1px solid #272727",
                borderRadius: "14px", padding: "28px 32px",
                position: "relative", overflow: "hidden",
              }}>
                <div style={{
                  position: "absolute", left: 0, top: 0, bottom: 0, width: "3px",
                  background: step.color, opacity: 0.8,
                }} />

                <div style={{ display: "flex", gap: "20px", alignItems: "flex-start" }}>
                  <div style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                    fontWeight: 700, color: step.color, flexShrink: 0,
                    paddingTop: "3px", letterSpacing: "0.1em",
                  }}>
                    {step.id}
                  </div>
                  <div>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#ede9e3", marginBottom: "10px" }}>
                      {step.title}
                    </h2>
                    <p style={{ fontSize: "13px", color: "#6b6865", lineHeight: 1.8 }}>
                      {step.description}
                    </p>
                  </div>
                </div>
              </div>

              {i < STEPS.length - 1 && (
                <div style={{
                  display: "flex", justifyContent: "center", padding: "6px 0",
                  fontFamily: "var(--font-mono), monospace", fontSize: "14px", color: "#1e1e1e",
                }}>↓</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
