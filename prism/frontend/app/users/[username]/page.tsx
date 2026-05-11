"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { getUserPage } from "@/lib/api";
import type { SavedBasket, UserProfile } from "@/lib/types";

function avatarColor(seed: string): string {
  const palette = ["#4f46e5", "#2563eb", "#16a34a", "#9333ea", "#d97706", "#0891b2", "#db2777"];
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

export default function UserProfilePage() {
  const params = useParams<{ username: string }>();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [baskets, setBaskets] = useState<SavedBasket[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!params?.username) return;
    getUserPage(params.username)
      .then(({ profile: p, baskets: b }) => {
        setProfile(p);
        setBaskets(b);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [params]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#f8f6f2" }}>
        <Header />
        <GridOverlay />
        <div style={{ position: "relative", zIndex: 10, maxWidth: 900, margin: "0 auto", padding: "120px 24px" }}>
          <div style={{ color: "#9b9390", fontSize: 15 }}>Loading profile…</div>
        </div>
      </div>
    );
  }

  if (notFound || !profile) {
    return (
      <div style={{ minHeight: "100vh", background: "#f8f6f2" }}>
        <Header />
        <GridOverlay />
        <div style={{ position: "relative", zIndex: 10, maxWidth: 900, margin: "0 auto", padding: "120px 24px" }}>
          <div style={{ color: "#9b9390", fontSize: 15 }}>User not found.</div>
          <Link href="/baskets" style={{ color: "#4f46e5", fontSize: 13, textDecoration: "none", display: "inline-block", marginTop: 12 }}>
            ← Browse baskets
          </Link>
        </div>
      </div>
    );
  }

  const color = avatarColor(profile.username);
  const joinedDate = new Date(profile.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" });

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1100, margin: "0 auto", padding: "110px 24px 80px" }}>
        <Link href="/baskets" style={{ color: "#9b9390", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 32 }}>
          ← Back to baskets
        </Link>

        {/* Profile header */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 40 }}>
          <div style={{
            width: 64, height: 64, borderRadius: "50%",
            background: color,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <span style={{ color: "#fff", fontSize: 22, fontWeight: 700 }}>◈</span>
          </div>
          <div>
            <h1 style={{
              color: "#1c1814",
              fontSize: "clamp(24px, 4vw, 36px)",
              fontWeight: 700,
              letterSpacing: "-0.04em",
              margin: "0 0 4px",
            }}>
              @{profile.username}
            </h1>
            <div style={{ color: "#9b9390", fontSize: 13, fontFamily: "var(--font-mono), monospace" }}>
              Joined {joinedDate} · {baskets.length} public basket{baskets.length !== 1 ? "s" : ""}
            </div>
          </div>
        </div>

        {/* Baskets grid */}
        {baskets.length === 0 ? (
          <div style={{
            background: "#ffffff",
            border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 22,
            padding: 40,
            textAlign: "center",
            color: "#9b9390",
            fontSize: 15,
          }}>
            No public baskets yet.
          </div>
        ) : (
          <>
            <div style={{
              color: "#4f46e5", fontSize: 11, textTransform: "uppercase",
              letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace",
              marginBottom: 16,
            }}>
              Public baskets
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 20,
            }}>
              {baskets.map((basket) => (
                <BasketCard key={basket.id} basket={basket} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
