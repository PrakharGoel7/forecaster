"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { listPublicBaskets } from "@/lib/api";
import type { SavedBasket } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [belief, setBelief] = useState("");
  const [publicBaskets, setPublicBaskets] = useState<SavedBasket[]>([]);
  const [textareaFocused, setTextareaFocused] = useState(false);
  const carouselRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listPublicBaskets(12).then(setPublicBaskets).catch(() => {});
  }, []);

  function scrollCarousel(dir: "left" | "right") {
    if (!carouselRef.current) return;
    carouselRef.current.scrollBy({ left: dir === "right" ? 360 : -360, behavior: "smooth" });
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1140, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ maxWidth: 760, marginBottom: 34 }}>
          <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 }}>
            Prism
          </div>
          <h1 style={{ color: "#1c1814", fontSize: "clamp(38px, 6vw, 72px)", lineHeight: 0.98, letterSpacing: "-0.06em", margin: "0 0 14px" }}>
            Build prediction market ETFs from your future theses.
          </h1>
          <p style={{ color: "#6e675f", fontSize: 19, lineHeight: 1.65, margin: 0 }}>
            Start from a belief about the future. Prism clarifies the theme, maps the implications, and builds a weighted basket of Kalshi contracts around it.
          </p>
        </div>

        <div style={{ maxWidth: 760 }}>
          <section style={cardStyle}>
            <div style={{ color: "#9b9390", fontSize: 13, marginBottom: 12 }}>What future are you betting on?</div>
            <textarea
              value={belief}
              onChange={(e) => setBelief(e.target.value)}
              rows={5}
              placeholder="Example: I think tighter export controls will reshape AI hardware supply chains over the next 12 months."
              style={{
                ...textareaStyle,
                border: textareaFocused ? "1px solid rgba(79,70,229,0.4)" : "1px solid rgba(0,0,0,0.12)",
              }}
              onFocus={() => setTextareaFocused(true)}
              onBlur={() => setTextareaFocused(false)}
            />
            <div style={{ marginTop: 14 }}>
              <button
                onClick={() => router.push(belief.trim() ? `/trading?belief=${encodeURIComponent(belief.trim())}` : "/trading")}
                style={{ ...primaryButtonStyle, width: "100%", padding: "14px 18px", fontSize: 15 }}
              >
                Build basket
              </button>
            </div>
          </section>
        </div>

        {publicBaskets.length > 0 && (
          <div style={{ marginTop: 72 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, gap: 16 }}>
              <div>
                <div style={eyebrowStyle}>Community</div>
                <div style={{ color: "#1c1814", fontSize: 26, fontWeight: 600, letterSpacing: "-0.035em" }}>
                  Public baskets
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexShrink: 0 }}>
                <button onClick={() => scrollCarousel("left")} style={arrowButtonStyle} aria-label="Scroll left">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button onClick={() => scrollCarousel("right")} style={arrowButtonStyle} aria-label="Scroll right">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M6 12l4-4-4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <Link
                  href="/baskets"
                  style={{
                    ...ghostButtonLinkStyle,
                    textDecoration: "none",
                  }}
                >
                  View all
                </Link>
              </div>
            </div>

            <div
              ref={carouselRef}
              style={{
                display: "flex",
                gap: 16,
                overflowX: "auto",
                scrollSnapType: "x mandatory",
                paddingBottom: 8,
                scrollbarWidth: "none",
                msOverflowStyle: "none",
              }}
            >
              {publicBaskets.map((basket) => (
                <div
                  key={basket.id}
                  style={{ minWidth: 300, maxWidth: 300, scrollSnapAlign: "start", flexShrink: 0 }}
                >
                  <BasketCard basket={basket} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 24,
  padding: 24,
  boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
};

const eyebrowStyle: React.CSSProperties = {
  color: "#4f46e5",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 10,
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  background: "#ffffff",
  borderRadius: 16,
  padding: "16px 18px",
  color: "#1c1814",
  fontSize: 15,
  lineHeight: 1.6,
  resize: "vertical",
  minHeight: 140,
  outline: "none",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "#4f46e5",
  color: "#fff",
  border: "none",
  borderRadius: 12,
  fontWeight: 600,
  cursor: "pointer",
};

const arrowButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(0,0,0,0.08)",
  color: "#6e675f",
  borderRadius: 999,
  width: 36,
  height: 36,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  fontSize: 16,
  lineHeight: 1,
};

const ghostButtonLinkStyle: React.CSSProperties = {
  background: "transparent",
  color: "#6e675f",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 12,
  padding: "8px 14px",
  cursor: "pointer",
  fontSize: 13,
  display: "inline-block",
};
