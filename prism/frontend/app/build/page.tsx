"use client";

import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";

export default function BuildPage() {
  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 880, margin: "0 auto", padding: "110px 24px 80px" }}>

        <div style={{ marginBottom: 52, maxWidth: 600 }}>
          <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
            Build on Prism
          </div>
          <h1 style={{ color: "#1c1814", fontSize: "clamp(32px, 5vw, 52px)", lineHeight: 1.04, letterSpacing: "-0.05em", margin: "0 0 14px" }}>
            How do you want to build?
          </h1>
          <p style={{ color: "#6e675f", fontSize: 17, lineHeight: 1.65, margin: 0 }}>
            Turn a conviction into a weighted basket of prediction-market contracts, then share it with the community.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20, marginBottom: 48 }}>

          {/* AI Build */}
          <Link href="/trading" style={{ textDecoration: "none", display: "flex" }}>
            <div
              style={{
                background: "#ffffff", border: "1px solid rgba(0,0,0,0.07)",
                borderRadius: 24, padding: 28, cursor: "pointer",
                transition: "box-shadow 0.15s, border-color 0.15s",
                display: "flex", flexDirection: "column", flex: 1,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 24px rgba(0,0,0,0.09)";
                (e.currentTarget as HTMLElement).style.borderColor = "rgba(79,70,229,0.3)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = "none";
                (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.07)";
              }}
            >
              <div style={{ width: 44, height: 44, borderRadius: 12, background: "rgba(79,70,229,0.1)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 18, fontSize: 22, color: "#4f46e5" }}>◈</div>
              <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>AI Build</div>
              <div style={{ color: "#1c1814", fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 10 }}>Describe a future</div>
              <p style={{ color: "#6e675f", fontSize: 14, lineHeight: 1.7, margin: "0 0 24px", flex: 1 }}>
                Tell Prism what you believe will happen. It finds the prediction-market positions that express your thesis and sizes them into a basket.
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
                {["Conversational", "AI-guided", "Fast"].map((tag) => (
                  <span key={tag} style={{ background: "rgba(79,70,229,0.08)", color: "#4f46e5", fontSize: 11, padding: "4px 10px", borderRadius: 999, fontWeight: 600, border: "1px solid rgba(79,70,229,0.15)" }}>{tag}</span>
                ))}
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "#4f46e5", color: "#fff", padding: "11px 18px", borderRadius: 12, fontWeight: 700, fontSize: 14, alignSelf: "flex-start" }}>
                Start AI Build →
              </div>
            </div>
          </Link>

          {/* Basket Studio */}
          <Link href="/trading/manual" style={{ textDecoration: "none", display: "flex" }}>
            <div
              style={{
                background: "#ffffff", border: "1px solid rgba(0,0,0,0.07)",
                borderRadius: 24, padding: 28, cursor: "pointer",
                transition: "box-shadow 0.15s, border-color 0.15s",
                display: "flex", flexDirection: "column", flex: 1,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 24px rgba(0,0,0,0.09)";
                (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.15)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = "none";
                (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.07)";
              }}
            >
              <div style={{ width: 44, height: 44, borderRadius: 12, background: "rgba(0,0,0,0.05)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 18, fontSize: 22 }}>⊞</div>
              <div style={{ color: "#6e675f", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>Basket Studio</div>
              <div style={{ color: "#1c1814", fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 10 }}>Pick your contracts</div>
              <p style={{ color: "#6e675f", fontSize: 14, lineHeight: 1.7, margin: "0 0 24px", flex: 1 }}>
                Browse the full Kalshi market catalog, choose specific contracts, set your own weights, and build a basket with complete manual control.
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 24 }}>
                {["Manual control", "Market browser", "Custom weights"].map((tag) => (
                  <span key={tag} style={{ background: "rgba(0,0,0,0.04)", color: "#6e675f", fontSize: 11, padding: "4px 10px", borderRadius: 999, fontWeight: 600, border: "1px solid rgba(0,0,0,0.08)" }}>{tag}</span>
                ))}
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "transparent", color: "#1c1814", padding: "11px 18px", borderRadius: 12, fontWeight: 700, fontSize: 14, border: "1px solid rgba(0,0,0,0.12)", alignSelf: "flex-start" }}>
                Open Basket Studio →
              </div>
            </div>
          </Link>
        </div>

        <div style={{ textAlign: "center" }}>
          <Link href="/baskets" style={{ color: "#9b9390", fontSize: 13, textDecoration: "none" }}>
            Not sure yet? Browse what others have built →
          </Link>
        </div>
      </div>
    </div>
  );
}
