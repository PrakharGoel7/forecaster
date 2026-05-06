"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";

export default function HomePage() {
  const router = useRouter();
  const [belief, setBelief] = useState("");

  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1140, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ maxWidth: 760, marginBottom: 34 }}>
          <div style={{ color: "#e36438", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
            Prism
          </div>
          <h1 style={{ color: "#ede9e3", fontSize: "clamp(38px, 6vw, 72px)", lineHeight: 0.98, letterSpacing: "-0.06em", margin: "0 0 14px" }}>
            Build prediction market ETFs from your future theses.
          </h1>
          <p style={{ color: "#948c84", fontSize: 19, lineHeight: 1.65, margin: 0 }}>
            Start from a belief about the future. Prism clarifies the theme, maps the implications, and builds a weighted basket of Kalshi contracts around it.
          </p>
        </div>

        <div style={{ maxWidth: 760 }}>
          <section style={cardStyle}>
            <div style={eyebrowStyle}>Prediction Market ETFs</div>
            <div style={titleStyle}>Turn a thesis into a weighted basket</div>
            <p style={bodyStyle}>
              Describe a future theme. Prism will clarify it, map the implications, and build a shareable $100 basket of direct and indirect prediction market exposures.
            </p>
            <textarea
              value={belief}
              onChange={(e) => setBelief(e.target.value)}
              rows={5}
              placeholder="Example: I think tighter export controls will reshape AI hardware supply chains over the next 12 months."
              style={textareaStyle}
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14 }}>
              <div style={{ color: "#7e766d", fontSize: 13 }}>Instant and thinking modes available inside the builder.</div>
              <button
                onClick={() => router.push(belief.trim() ? `/trading?belief=${encodeURIComponent(belief.trim())}` : "/trading")}
                style={primaryButtonStyle}
              >
                Build basket
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(18,18,18,0.97), rgba(12,12,12,0.98))",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 24,
  padding: 24,
  boxShadow: "0 18px 48px rgba(0,0,0,0.35)",
};

const eyebrowStyle: React.CSSProperties = {
  color: "#e36438",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 10,
};

const titleStyle: React.CSSProperties = {
  color: "#ede9e3",
  fontSize: 28,
  fontWeight: 600,
  letterSpacing: "-0.04em",
  marginBottom: 10,
};

const bodyStyle: React.CSSProperties = {
  color: "#948c84",
  fontSize: 15,
  lineHeight: 1.65,
  margin: "0 0 16px",
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 16,
  padding: "16px 18px",
  color: "#ede9e3",
  fontSize: 15,
  lineHeight: 1.6,
  resize: "vertical",
  minHeight: 140,
  outline: "none",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "#e36438",
  color: "#fff",
  border: "none",
  borderRadius: 12,
  padding: "12px 18px",
  fontWeight: 600,
  cursor: "pointer",
};
