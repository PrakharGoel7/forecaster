"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { getFeed } from "@/lib/api";
import { createClient } from "@/lib/supabase";
import type { SavedBasket } from "@/lib/types";

export default function FeedPage() {
  const [baskets, setBaskets] = useState<SavedBasket[]>([]);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const supabase = createClient();

  useEffect(() => {
    if (!supabase) { setAuthed(false); setLoading(false); return; }
    supabase.auth.getSession().then(async ({ data }) => {
      const token = data.session?.access_token;
      if (!token) { setAuthed(false); setLoading(false); return; }
      setAuthed(true);
      try {
        const feed = await getFeed(token, 48);
        setBaskets(Array.isArray(feed) ? feed : []);
      } catch {
        setBaskets([]);
      }
      setLoading(false);
    });
  }, [supabase]);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1100, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ marginBottom: 32 }}>
          <div style={eyebrowStyle}>Following</div>
          <h1 style={{ color: "#1c1814", fontSize: "clamp(30px, 4vw, 48px)", fontWeight: 700, letterSpacing: "-0.05em", margin: 0 }}>
            Your feed
          </h1>
        </div>

        {loading ? (
          <div style={{ color: "#a8a29a", fontSize: 14 }}>Loading feed…</div>
        ) : authed === false ? (
          <EmptyState
            title="Sign in to see your feed"
            body="Follow forecasters and thought leaders to get their latest theses here."
            cta={{ label: "Browse creators", href: "/creators" }}
          />
        ) : baskets.length === 0 ? (
          <EmptyState
            title="Nothing here yet"
            body="Follow some creators to see their theses in your feed."
            cta={{ label: "Discover creators", href: "/creators" }}
          />
        ) : (
          <>
            <div style={{ color: "#9b9390", fontSize: 12, fontFamily: "var(--font-mono), monospace", marginBottom: 16 }}>
              {baskets.length} thesis{baskets.length !== 1 ? "es" : ""} from people you follow
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 20,
            }}>
              {baskets.map(b => <BasketCard key={b.id} basket={b} />)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function EmptyState({ title, body, cta }: { title: string; body: string; cta: { label: string; href: string } }) {
  return (
    <div style={{
      background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)",
      borderRadius: 22, padding: "56px 40px", textAlign: "center", maxWidth: 480, margin: "0 auto",
    }}>
      <div style={{ fontSize: 36, marginBottom: 16 }}>◈</div>
      <div style={{ color: "#1c1814", fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 8 }}>
        {title}
      </div>
      <div style={{ color: "#6e675f", fontSize: 14, lineHeight: 1.65, marginBottom: 24 }}>
        {body}
      </div>
      <Link href={cta.href} style={{
        background: "#4f46e5", color: "#fff", fontWeight: 700,
        fontSize: 14, padding: "11px 22px", borderRadius: 10,
        textDecoration: "none", display: "inline-block",
      }}>
        {cta.label}
      </Link>
    </div>
  );
}

const eyebrowStyle: React.CSSProperties = {
  color: "#4f46e5", fontSize: 11, textTransform: "uppercase",
  letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 10,
};
