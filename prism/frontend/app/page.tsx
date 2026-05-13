"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { listPublicBaskets, getCreators } from "@/lib/api";
import type { SavedBasket, Creator } from "@/lib/types";

function avatarColor(seed: string): string {
  const palette = ["#4f46e5", "#2563eb", "#16a34a", "#9333ea", "#d97706", "#0891b2", "#db2777"];
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

export default function HomePage() {
  const [publicBaskets, setPublicBaskets] = useState<SavedBasket[]>([]);
  const [loading, setLoading] = useState(true);
  const [creators, setCreators] = useState<Creator[]>([]);

  useEffect(() => {
    listPublicBaskets(9).then(setPublicBaskets).catch(() => {}).finally(() => setLoading(false));
    getCreators(6).then(data => setCreators(Array.isArray(data) ? data.filter(c => (c.basket_count ?? 0) > 0).slice(0, 6) : [])).catch(() => {});
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />

      {/* ── Hero ── */}
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1140, margin: "0 auto", padding: "120px 24px 80px" }}>
        <div style={{ maxWidth: 700, marginBottom: 52 }}>
          <div style={eyebrowStyle}>Prism</div>
          <h1 style={{
            color: "#1c1814",
            fontSize: "clamp(40px, 6vw, 72px)",
            lineHeight: 0.96,
            letterSpacing: "-0.055em",
            margin: "0 0 20px",
          }}>
            See what the community<br />is betting on.
          </h1>
          <p style={{ color: "#6e675f", fontSize: 18, lineHeight: 1.65, margin: "0 0 32px", maxWidth: 520 }}>
            Prism is a social platform for prediction market portfolios. Browse community baskets, follow convictions, or build and share your own.
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <Link href="/baskets" style={primaryLinkStyle}>
              Browse theses
            </Link>
            <Link href="/creators" style={ghostLinkStyle}>
              Follow experts
            </Link>
            <Link href="/build" style={{ ...ghostLinkStyle, color: "#9b9390" }}>
              Build your own
            </Link>
          </div>
        </div>

        {/* ── Basket feed ── */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <div style={eyebrowStyle}>Latest theses from the community</div>
            <Link href="/baskets" style={{ color: "#6e675f", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
              View all
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </Link>
          </div>

          {loading ? (
            <div style={{ color: "#a8a29a", fontSize: 14 }}>Loading…</div>
          ) : publicBaskets.length === 0 ? (
            <div style={{
              background: "#ffffff",
              border: "1px solid rgba(0,0,0,0.08)",
              borderRadius: 22,
              padding: "48px 32px",
              textAlign: "center",
            }}>
              <div style={{ color: "#1c1814", fontSize: 18, fontWeight: 600, marginBottom: 8 }}>No theses yet.</div>
              <div style={{ color: "#6e675f", fontSize: 14, marginBottom: 24 }}>Be the first to build and share one.</div>
              <Link href="/trading" style={primaryLinkStyle}>Build a thesis</Link>
            </div>
          ) : (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 20,
            }}>
              {publicBaskets.map((basket) => (
                <BasketCard key={basket.id} basket={basket} />
              ))}
            </div>
          )}
        </div>

        {/* ── Featured Creators ── */}
        {creators.length > 0 && (
          <div style={{ marginTop: 56 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <div style={eyebrowStyle}>Featured experts</div>
              <Link href="/creators" style={{ color: "#6e675f", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                All creators
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </Link>
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 14,
            }}>
              {creators.map(c => {
                const color = avatarColor(c.username);
                const tags: string[] = Array.isArray(c.domain_tags) ? c.domain_tags : [];
                return (
                  <Link key={c.user_id} href={`/users/${c.username}`} style={{ textDecoration: "none" }}>
                    <div style={{
                      background: "#ffffff", border: "1px solid rgba(0,0,0,0.07)",
                      borderRadius: 14, padding: "16px 18px", cursor: "pointer",
                      transition: "box-shadow 0.15s",
                    }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 16px rgba(0,0,0,0.07)"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                        <div style={{ width: 34, height: 34, borderRadius: "50%", background: color, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>◈</span>
                        </div>
                        <div>
                          <div style={{ color: "#4f46e5", fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono), monospace" }}>@{c.username}</div>
                          <div style={{ color: "#9b9390", fontSize: 11 }}>{c.follower_count} follower{c.follower_count !== 1 ? "s" : ""} · {c.basket_count} ths.</div>
                        </div>
                      </div>
                      {tags.slice(0, 3).map(t => (
                        <span key={t} style={{ display: "inline-block", background: "rgba(79,70,229,0.07)", color: "#4f46e5", fontSize: 10, padding: "2px 7px", borderRadius: 999, marginRight: 4, marginBottom: 2, fontWeight: 500 }}>{t}</span>
                      ))}
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Build CTA banner ── */}
        <div style={{
          marginTop: 72,
          background: "#4f46e5",
          borderRadius: 28,
          padding: "44px 48px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 32,
          flexWrap: "wrap",
        }}>
          <div>
            <div style={{
              color: "rgba(255,255,255,0.55)",
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: "0.16em",
              fontFamily: "var(--font-mono), monospace",
              marginBottom: 10,
            }}>
              Build on Prism
            </div>
            <div style={{
              color: "#ffffff",
              fontSize: "clamp(22px, 3vw, 32px)",
              fontWeight: 700,
              letterSpacing: "-0.04em",
              lineHeight: 1.1,
              marginBottom: 10,
            }}>
              Share your market thesis.
            </div>
            <p style={{ color: "rgba(255,255,255,0.65)", fontSize: 15, lineHeight: 1.6, maxWidth: 460, margin: 0 }}>
              Turn a belief about the future into a weighted basket of Kalshi contracts — then share it with the community.
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", flexShrink: 0 }}>
            <Link href="/trading" style={{
              background: "#ffffff",
              color: "#4f46e5",
              fontWeight: 700,
              fontSize: 14,
              padding: "12px 22px",
              borderRadius: 12,
              textDecoration: "none",
              display: "inline-block",
            }}>
              AI Build
            </Link>
            <Link href="/trading/manual" style={{
              background: "rgba(255,255,255,0.15)",
              color: "#ffffff",
              fontWeight: 600,
              fontSize: 14,
              padding: "12px 22px",
              borderRadius: 12,
              textDecoration: "none",
              display: "inline-block",
              border: "1px solid rgba(255,255,255,0.2)",
            }}>
              Basket Studio
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

const eyebrowStyle: React.CSSProperties = {
  color: "#4f46e5",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 12,
};

const primaryLinkStyle: React.CSSProperties = {
  background: "#4f46e5",
  color: "#ffffff",
  fontWeight: 700,
  fontSize: 15,
  padding: "13px 24px",
  borderRadius: 12,
  textDecoration: "none",
  display: "inline-block",
};

const ghostLinkStyle: React.CSSProperties = {
  background: "transparent",
  color: "#6e675f",
  fontWeight: 600,
  fontSize: 15,
  padding: "13px 24px",
  borderRadius: 12,
  textDecoration: "none",
  display: "inline-block",
  border: "1px solid rgba(0,0,0,0.1)",
};
