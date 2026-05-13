"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { getUserPage, followUser, unfollowUser, updateMyProfile } from "@/lib/api";
import { createClient } from "@/lib/supabase";
import type { SavedBasket, UserProfile } from "@/lib/types";

function avatarColor(seed: string): string {
  const palette = ["#4f46e5", "#2563eb", "#16a34a", "#9333ea", "#d97706", "#0891b2", "#db2777"];
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

const DOMAIN_OPTIONS = [
  "Macro", "Geopolitics", "AI / Tech", "Crypto", "Politics", "Climate",
  "Healthcare", "Energy", "Finance", "Sports", "Entertainment",
];

export default function UserProfilePage() {
  const params = useParams<{ username: string }>();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [baskets, setBaskets] = useState<SavedBasket[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);
  const [myUserId, setMyUserId] = useState<string | null>(null);
  const [myToken, setMyToken] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);

  // Edit profile state
  const [editBio, setEditBio] = useState("");
  const [editTags, setEditTags] = useState<string[]>([]);
  const [editTwitter, setEditTwitter] = useState("");
  const [editSubstack, setEditSubstack] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState("");

  const supabase = createClient();

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      setMyUserId(data.session?.user?.id ?? null);
      setMyToken(data.session?.access_token ?? null);
    });
  }, [supabase]);

  useEffect(() => {
    if (!params?.username) return;
    const token = myToken ?? undefined;
    getUserPage(params.username, token)
      .then(({ profile: p, baskets: b, is_following: f }) => {
        setProfile(p);
        setBaskets(b);
        setIsFollowing(f);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [params, myToken]);

  async function handleFollow() {
    if (!myToken || !profile) return;
    setFollowLoading(true);
    try {
      if (isFollowing) {
        const res = await unfollowUser(profile.username, myToken);
        setIsFollowing(false);
        setProfile(p => p ? { ...p, follower_count: res.follower_count } : p);
      } else {
        const res = await followUser(profile.username, myToken);
        setIsFollowing(true);
        setProfile(p => p ? { ...p, follower_count: res.follower_count } : p);
      }
    } catch {
      // ignore
    }
    setFollowLoading(false);
  }

  function openEdit() {
    if (!profile) return;
    setEditBio(profile.bio || "");
    setEditTags(Array.isArray(profile.domain_tags) ? profile.domain_tags : []);
    setEditTwitter(profile.twitter || "");
    setEditSubstack(profile.substack || "");
    setEditError("");
    setShowEditModal(true);
  }

  async function saveEdit() {
    if (!myToken) return;
    setEditLoading(true);
    setEditError("");
    try {
      const updated = await updateMyProfile({
        bio: editBio || undefined,
        domain_tags: editTags.length ? editTags : undefined,
        twitter: editTwitter || undefined,
        substack: editSubstack || undefined,
      }, myToken);
      setProfile(updated);
      setShowEditModal(false);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Failed to save");
    }
    setEditLoading(false);
  }

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
            ← Browse theses
          </Link>
        </div>
      </div>
    );
  }

  const color = avatarColor(profile.username);
  const joinedDate = new Date(profile.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const isOwnProfile = myUserId === profile.user_id;
  const tags: string[] = Array.isArray(profile.domain_tags) ? profile.domain_tags : [];

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1100, margin: "0 auto", padding: "110px 24px 80px" }}>
        <Link href="/creators" style={{ color: "#9b9390", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 32 }}>
          ← Creators
        </Link>

        {/* Profile header */}
        <div style={{
          background: "#ffffff",
          border: "1px solid rgba(0,0,0,0.08)",
          borderRadius: 22,
          padding: "28px 28px 24px",
          marginBottom: 28,
        }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
            <div style={{
              width: 72, height: 72, borderRadius: "50%",
              background: color,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <span style={{ color: "#fff", fontSize: 26, fontWeight: 700 }}>◈</span>
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 4 }}>
                <h1 style={{
                  color: "#1c1814", fontSize: "clamp(22px, 3vw, 32px)", fontWeight: 700,
                  letterSpacing: "-0.04em", margin: 0,
                }}>
                  @{profile.username}
                </h1>
                {/* Follow / Edit button */}
                {isOwnProfile ? (
                  <button onClick={openEdit} style={ghostBtnStyle}>
                    Edit profile
                  </button>
                ) : myToken ? (
                  <button
                    onClick={handleFollow}
                    disabled={followLoading}
                    style={{
                      ...ghostBtnStyle,
                      background: isFollowing ? "#4f46e5" : "transparent",
                      color: isFollowing ? "#fff" : "#4f46e5",
                      borderColor: "#4f46e5",
                    }}
                  >
                    {followLoading ? "…" : isFollowing ? "Following" : "Follow"}
                  </button>
                ) : null}
              </div>

              <div style={{ color: "#9b9390", fontSize: 12, fontFamily: "var(--font-mono), monospace", marginBottom: profile.bio ? 10 : 0 }}>
                Joined {joinedDate}
              </div>

              {profile.bio && (
                <p style={{ color: "#3a3530", fontSize: 15, lineHeight: 1.65, margin: "0 0 12px", maxWidth: 640 }}>
                  {profile.bio}
                </p>
              )}

              {tags.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 14 }}>
                  {tags.map(tag => (
                    <span key={tag} style={{
                      background: "rgba(79,70,229,0.07)", color: "#4f46e5",
                      fontSize: 11, padding: "3px 9px", borderRadius: 999, fontWeight: 500,
                    }}>{tag}</span>
                  ))}
                </div>
              )}

              {/* Social links */}
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {profile.twitter && (
                  <a
                    href={`https://twitter.com/${profile.twitter.replace(/^@/, "")}`}
                    target="_blank" rel="noopener noreferrer"
                    style={{ color: "#6e675f", fontSize: 12, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}
                  >
                    <XIcon /> @{profile.twitter.replace(/^@/, "")}
                  </a>
                )}
                {profile.substack && (
                  <a
                    href={profile.substack.startsWith("http") ? profile.substack : `https://${profile.substack}`}
                    target="_blank" rel="noopener noreferrer"
                    style={{ color: "#6e675f", fontSize: 12, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}
                  >
                    <SubstackIcon /> Substack
                  </a>
                )}
              </div>
            </div>

            {/* Stats */}
            <div style={{ display: "flex", gap: 24, flexShrink: 0 }}>
              <Stat value={profile.follower_count ?? 0} label="Followers" />
              <Stat value={profile.following_count ?? 0} label="Following" />
              <Stat value={baskets.length} label="Theses" />
            </div>
          </div>
        </div>

        {/* Baskets grid */}
        {baskets.length === 0 ? (
          <div style={{
            background: "#ffffff", border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 22, padding: 40, textAlign: "center", color: "#9b9390", fontSize: 15,
          }}>
            No public theses yet.
          </div>
        ) : (
          <>
            <div style={eyebrowStyle}>Public theses</div>
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

      {/* Edit profile modal */}
      {showEditModal && (
        <div
          onClick={() => setShowEditModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#ffffff", border: "1px solid rgba(79,70,229,0.15)",
              borderRadius: 20, padding: "32px", width: "100%", maxWidth: 480,
              boxShadow: "0 24px 80px rgba(0,0,0,0.25)", maxHeight: "90vh", overflowY: "auto",
            }}
          >
            <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
              Profile
            </div>
            <div style={{ color: "#1c1814", fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 20 }}>
              Edit your profile
            </div>

            <FieldLabel>Bio</FieldLabel>
            <textarea
              value={editBio}
              onChange={e => setEditBio(e.target.value)}
              rows={3}
              maxLength={280}
              placeholder="Tell people what you focus on…"
              style={inputStyle}
            />

            <FieldLabel>Domain expertise</FieldLabel>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
              {DOMAIN_OPTIONS.map(tag => (
                <button
                  key={tag}
                  onClick={() => setEditTags(prev =>
                    prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
                  )}
                  style={{
                    padding: "4px 10px", borderRadius: 999, fontSize: 12, cursor: "pointer",
                    fontWeight: 500, border: "1px solid",
                    background: editTags.includes(tag) ? "#4f46e5" : "transparent",
                    color: editTags.includes(tag) ? "#fff" : "#4f46e5",
                    borderColor: "#4f46e5",
                  }}
                >{tag}</button>
              ))}
            </div>

            <FieldLabel>X / Twitter handle</FieldLabel>
            <div style={{ position: "relative", marginBottom: 12 }}>
              <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#a8a29a", fontSize: 13, pointerEvents: "none" }}>@</span>
              <input
                type="text"
                value={editTwitter.replace(/^@/, "")}
                onChange={e => setEditTwitter(e.target.value)}
                placeholder="yourhandle"
                style={{ ...inputStyle, paddingLeft: 26, marginBottom: 0 }}
              />
            </div>

            <FieldLabel>Substack URL</FieldLabel>
            <input
              type="text"
              value={editSubstack}
              onChange={e => setEditSubstack(e.target.value)}
              placeholder="yourname.substack.com"
              style={inputStyle}
            />

            {editError && <div style={{ fontSize: 12, color: "#dc2626", marginBottom: 10 }}>{editError}</div>}

            <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
              <button
                onClick={saveEdit}
                disabled={editLoading}
                style={{
                  flex: 1, background: "#4f46e5", color: "#fff", border: "none",
                  borderRadius: 10, padding: "11px", fontSize: 13, fontWeight: 700,
                  cursor: "pointer", opacity: editLoading ? 0.6 : 1,
                  fontFamily: "var(--font-mono), monospace", letterSpacing: "0.06em",
                }}
              >
                {editLoading ? "Saving…" : "Save changes →"}
              </button>
              <button
                onClick={() => setShowEditModal(false)}
                style={{
                  background: "transparent", color: "#9b9390", border: "1px solid rgba(0,0,0,0.1)",
                  borderRadius: 10, padding: "11px 16px", fontSize: 13, cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ color: "#1c1814", fontSize: 22, fontWeight: 700, lineHeight: 1 }}>{value}</div>
      <div style={{ color: "#9b9390", fontSize: 11, marginTop: 3, fontFamily: "var(--font-mono), monospace", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: "#6e675f", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, fontFamily: "var(--font-mono), monospace" }}>
      {children}
    </div>
  );
}

function XIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function SubstackIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.539 8.242H1.46V5.406h21.08v2.836zM1.46 10.812V24L12 18.11 22.54 24V10.812H1.46zM22.54 0H1.46v2.836h21.08V0z" />
    </svg>
  );
}

const eyebrowStyle: React.CSSProperties = {
  color: "#4f46e5", fontSize: 11, textTransform: "uppercase",
  letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 16,
};

const ghostBtnStyle: React.CSSProperties = {
  background: "transparent", color: "#4f46e5",
  border: "1px solid rgba(79,70,229,0.35)", borderRadius: 8,
  padding: "6px 14px", fontSize: 12, fontWeight: 600,
  cursor: "pointer", fontFamily: "var(--font-mono), monospace",
  letterSpacing: "0.06em", transition: "all 0.15s",
};

const inputStyle: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  background: "#f8f6f2", border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 8, padding: "10px 12px", fontSize: 13, color: "#1c1814",
  outline: "none", marginBottom: 14, resize: "vertical" as const,
  fontFamily: "var(--font-jakarta), system-ui, sans-serif",
};
