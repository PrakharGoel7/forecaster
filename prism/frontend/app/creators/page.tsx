"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { getCreators } from "@/lib/api";
import type { Creator } from "@/lib/types";

function avatarColor(seed: string): string {
  const palette = ["#4f46e5", "#2563eb", "#16a34a", "#9333ea", "#d97706", "#0891b2", "#db2777"];
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

function CreatorCard({ creator }: { creator: Creator }) {
  const color = avatarColor(creator.username);
  const tags: string[] = Array.isArray(creator.domain_tags) ? creator.domain_tags : [];

  return (
    <Link href={`/users/${creator.username}`} style={{ textDecoration: "none", display: "block" }}>
      <article style={{
        background: "#ffffff",
        border: "1px solid rgba(0,0,0,0.07)",
        borderRadius: 16,
        padding: "20px 22px",
        cursor: "pointer",
        transition: "box-shadow 0.15s, border-color 0.15s",
      }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 20px rgba(0,0,0,0.08)";
          (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.12)";
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.boxShadow = "none";
          (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,0,0,0.07)";
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: "50%",
            background: color,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <span style={{ color: "#fff", fontSize: 16, fontWeight: 700 }}>◈</span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: "#4f46e5", fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono), monospace", marginBottom: 2 }}>
              @{creator.username}
            </div>
            {creator.bio && (
              <div style={{
                color: "#6e675f", fontSize: 13, lineHeight: 1.5,
                overflow: "hidden", display: "-webkit-box",
                WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
              }}>
                {creator.bio}
              </div>
            )}
          </div>
        </div>

        {tags.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 12 }}>
            {tags.map(tag => (
              <span key={tag} style={{
                background: "rgba(79,70,229,0.07)",
                color: "#4f46e5",
                fontSize: 11,
                padding: "3px 8px",
                borderRadius: 999,
                fontWeight: 500,
              }}>{tag}</span>
            ))}
          </div>
        )}

        <div style={{ display: "flex", gap: 20, borderTop: "1px solid rgba(0,0,0,0.06)", paddingTop: 12 }}>
          <Stat label="Followers" value={creator.follower_count} />
          <Stat label="Theses" value={creator.basket_count} />
        </div>
      </article>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div style={{ color: "#1c1814", fontSize: 18, fontWeight: 700, lineHeight: 1 }}>{value}</div>
      <div style={{ color: "#9b9390", fontSize: 11, marginTop: 2, fontFamily: "var(--font-mono), monospace", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
    </div>
  );
}

export default function CreatorsPage() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [filtered, setFiltered] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getCreators(100).then(data => {
      const arr = Array.isArray(data) ? data : [];
      setCreators(arr);
      setFiltered(arr);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const q = search.toLowerCase().trim();
    if (!q) { setFiltered(creators); return; }
    setFiltered(creators.filter(c =>
      c.username.includes(q) ||
      (c.bio || "").toLowerCase().includes(q) ||
      (Array.isArray(c.domain_tags) ? c.domain_tags : []).some(t => t.toLowerCase().includes(q))
    ));
  }, [search, creators]);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1100, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ marginBottom: 32 }}>
          <div style={eyebrowStyle}>Creators</div>
          <h1 style={{ color: "#1c1814", fontSize: "clamp(32px, 5vw, 52px)", fontWeight: 700, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
            Thought leaders & forecasters
          </h1>
          <p style={{ color: "#6e675f", fontSize: 16, lineHeight: 1.65, margin: "0 0 24px", maxWidth: 560 }}>
            Follow experts building prediction market theses across macro, geopolitics, tech, and more.
          </p>
          <input
            type="text"
            placeholder="Search by name, bio, or domain…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              width: "100%", maxWidth: 400, boxSizing: "border-box",
              background: "#ffffff", border: "1px solid rgba(0,0,0,0.1)",
              borderRadius: 10, padding: "10px 16px", fontSize: 14,
              color: "#1c1814", outline: "none",
              fontFamily: "var(--font-jakarta), system-ui, sans-serif",
            }}
          />
        </div>

        {loading ? (
          <div style={{ color: "#a8a29a", fontSize: 14 }}>Loading creators…</div>
        ) : filtered.length === 0 ? (
          <div style={{
            background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 22, padding: "48px 32px", textAlign: "center",
          }}>
            <div style={{ color: "#9b9390", fontSize: 15 }}>
              {search ? "No creators match your search." : "No creators yet. Be the first to publish a thesis."}
            </div>
            {!search && (
              <Link href="/trading" style={{ ...primaryLinkStyle, display: "inline-block", marginTop: 16 }}>
                Build a thesis
              </Link>
            )}
          </div>
        ) : (
          <>
            <div style={{ color: "#9b9390", fontSize: 12, fontFamily: "var(--font-mono), monospace", marginBottom: 16 }}>
              {filtered.length} creator{filtered.length !== 1 ? "s" : ""}
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 18,
            }}>
              {filtered.map(c => <CreatorCard key={c.user_id} creator={c} />)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const eyebrowStyle: React.CSSProperties = {
  color: "#4f46e5", fontSize: 11, textTransform: "uppercase",
  letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10,
};

const primaryLinkStyle: React.CSSProperties = {
  background: "#4f46e5", color: "#ffffff", fontWeight: 700,
  fontSize: 14, padding: "11px 22px", borderRadius: 10, textDecoration: "none",
};
