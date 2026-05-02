"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";

export default function HomePage() {
  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />

      <div style={{
        position: "relative", zIndex: 10, paddingTop: "56px",
        height: "100vh", overflowY: "auto",
      }}>
        <div style={{ maxWidth: "900px", margin: "0 auto", padding: "48px 28px 80px" }}>

          {/* Headline row */}
          <div style={{
            display: "flex", justifyContent: "space-between",
            alignItems: "flex-start", gap: "32px", marginBottom: "28px",
          }}>
            <div style={{ flex: 1 }}>
              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.05 }}
                style={{
                  fontSize: "clamp(24px, 3.2vw, 34px)", fontWeight: 600,
                  color: "#ede9e3", lineHeight: 1.25, letterSpacing: "-0.02em",
                  marginBottom: "10px",
                }}
              >
                You have views on geopolitics,<br />markets, AI, sports.
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 }}
                style={{
                  fontSize: "clamp(16px, 2vw, 20px)", fontWeight: 400,
                  color: "#7a7570", lineHeight: 1.35, letterSpacing: "-0.01em",
                  margin: 0,
                }}
              >
                Prism turns them into researched Kalshi positions.
              </motion.p>
            </div>
            <div style={{ flexShrink: 0, maxWidth: "215px", paddingTop: "6px" }}>
              <div style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "12px",
                letterSpacing: "0.06em", color: "#9b9790", lineHeight: 1.7,
              }}>
                <Typewriter
                  text="Hedge fund-level research, built for individual Kalshi users"
                  delay={600}
                  speed={60}
                />
              </div>
            </div>
          </div>

          {/* How it works */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.14 }}
            style={{ marginBottom: "32px" }}
          >
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {[
                {
                  n: "01",
                  title: "State your thesis",
                  desc: "Describe what you believe will happen — geopolitics, macro, policy.",
                },
                {
                  n: "02",
                  title: "Map the effects",
                  desc: "We identify the downstream markets your thesis implies — the connections you wouldn't think to look for.",
                },
                {
                  n: "03",
                  title: "Find the edge",
                  desc: "We independently estimate the true probability of each event and flag where the market is wrong.",
                },
              ].map((step) => (
                <div
                  key={step.n}
                  style={{
                    flex: "1 1 160px",
                    background: "rgba(14,14,14,0.95)",
                    border: "1px solid #222",
                    borderRadius: "10px",
                    padding: "14px 16px",
                  }}
                >
                  <div style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "9px",
                    fontWeight: 700, color: "#e36438", letterSpacing: "0.16em",
                    marginBottom: "8px",
                  }}>{step.n}</div>
                  <div style={{
                    fontSize: "12px", fontWeight: 600, color: "#ede9e3",
                    marginBottom: "6px", lineHeight: 1.3,
                  }}>{step.title}</div>
                  <div style={{
                    fontSize: "11px", color: "#7a7570", lineHeight: 1.6,
                  }}>{step.desc}</div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* CTA */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.2 }}
            style={{ display: "flex", gap: "12px", alignItems: "center" }}
          >
            <Link
              href="/trading"
              style={{
                background: "#e36438", color: "#fff",
                border: "none", borderRadius: "10px",
                padding: "11px 28px", fontSize: "12px",
                fontFamily: "var(--font-mono), monospace",
                fontWeight: 600, letterSpacing: "0.08em",
                textDecoration: "none",
                transition: "background 0.15s",
                display: "inline-block",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "#c4421a")}
              onMouseLeave={e => (e.currentTarget.style.background = "#e36438")}
            >
              Open Compass →
            </Link>
            <Link
              href="/forecasts"
              style={{
                color: "#6b6865", fontSize: "12px",
                fontFamily: "var(--font-mono), monospace",
                letterSpacing: "0.06em", textDecoration: "none",
                transition: "color 0.15s",
              }}
              onMouseEnter={e => (e.currentTarget.style.color = "#ede9e3")}
              onMouseLeave={e => (e.currentTarget.style.color = "#6b6865")}
            >
              Browse Intel →
            </Link>
          </motion.div>

        </div>
      </div>
    </div>
  );
}

function Typewriter({ text, delay = 0, speed = 35 }: { text: string; delay?: number; speed?: number }) {
  const [displayed, setDisplayed] = useState("");
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setStarted(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  useEffect(() => {
    if (!started || displayed.length >= text.length) return;
    const t = setTimeout(() => setDisplayed(text.slice(0, displayed.length + 1)), speed);
    return () => clearTimeout(t);
  }, [started, displayed, text, speed]);

  const done = displayed.length >= text.length;
  return (
    <span>
      {displayed}
      <span className="blink" style={{ color: "#e36438", opacity: done ? 0.5 : 1 }}>▋</span>
    </span>
  );
}
