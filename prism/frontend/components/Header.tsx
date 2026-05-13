"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase";
import { getMyProfile, createProfile, ApiError } from "@/lib/api";
import type { User } from "@supabase/supabase-js";
import type { UserProfile } from "@/lib/types";

const NAV_PUBLIC = [
  { href: "/",          label: "Home"     },
  { href: "/build",     label: "Build"    },
  { href: "/baskets",   label: "Theses"   },
  { href: "/creators",  label: "Creators" },
];
const NAV_AUTHED = [
  { href: "/",          label: "Home"     },
  { href: "/build",     label: "Build"    },
  { href: "/baskets",   label: "Theses"   },
  { href: "/creators",  label: "Creators" },
  { href: "/feed",      label: "Feed"     },
];

export default function Header() {
  const path = usePathname();
  const router = useRouter();
  const supabase = createClient();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showUsernameModal, setShowUsernameModal] = useState(false);
  const [usernameInput, setUsernameInput] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [usernameLoading, setUsernameLoading] = useState(false);
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [usernameSignup, setUsernameSignup] = useState("");
  const [showWelcomeModal, setShowWelcomeModal] = useState(false);
  const [welcomeUsername, setWelcomeUsername] = useState("");

  useEffect(() => {
    if (!supabase) return;

    const checkProfile = async (token: string) => {
      try {
        const p = await getMyProfile(token);
        setProfile(p);
      } catch (err) {
        // Only prompt for username if profile genuinely doesn't exist (404).
        // Any other error (401 auth failure, 5xx, network) should fail silently
        // — don't trap the user in a username modal they can't escape.
        if (!(err instanceof ApiError) || err.status !== 404) return;

        // Check for a username saved during signup (email-confirm flow)
        const pending = typeof window !== "undefined" ? localStorage.getItem("prism_pending_username") : null;
        if (pending) {
          localStorage.removeItem("prism_pending_username");
          try {
            const p = await createProfile(pending, token);
            setProfile(p);
            return;
          } catch { /* fall through to manual prompt */ }
        }
        setPendingToken(token);
        setShowUsernameModal(true);
      }
    };

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => {
      setUser(session?.user ?? null);
      if (session?.access_token) {
        checkProfile(session.access_token);
      } else {
        setProfile(null);
        setShowUsernameModal(false);
      }
    });
    return () => subscription.unsubscribe();
  }, [supabase]);

  async function submit() {
    if (!supabase) {
      setError("Authentication is unavailable in this environment.");
      return;
    }
    if (!email.trim() || !password.trim()) return;
    setLoading(true);
    setError("");
    setSuccess("");
    if (mode === "signin") {
      const { error: e } = await supabase.auth.signInWithPassword({ email, password });
      if (e) setError(e.message);
      else setShowModal(false);
    } else {
      const { data, error: e } = await supabase.auth.signUp({ email, password });
      if (e) {
        setError(e.message);
      } else if (data.session) {
        // Session available immediately — onAuthStateChange will fire and
        // checkProfile will show the username modal automatically
        setShowModal(false);
      } else {
        // Email confirmation required — show success and wait
        setSuccess("Account created! Check your email to confirm, then sign in.");
      }
    }
    setLoading(false);
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setProfile(null);
    router.refresh();
  }

  async function submitUsername() {
    if (!pendingToken || !usernameInput.trim()) return;
    setUsernameLoading(true);
    setUsernameError("");
    try {
      const p = await createProfile(usernameInput.trim().toLowerCase(), pendingToken);
      setProfile(p);
      setShowUsernameModal(false);
      setPendingToken(null);
      setUsernameInput("");
      setWelcomeUsername(p.username);
      setShowWelcomeModal(true);
    } catch (e) {
      setUsernameError(e instanceof Error ? e.message : "Username taken or invalid");
    }
    setUsernameLoading(false);
  }

  function hardNavigate(href: string) {
    window.location.href = href;
  }

  return (
    <>
      <header style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 50,
        borderBottom: "1px solid rgba(0,0,0,0.08)",
        background: "rgba(248,246,242,0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
      }}>
        <div style={{
          maxWidth: "1280px", margin: "0 auto", padding: "0 32px",
          height: "56px", display: "flex", alignItems: "center", gap: "40px",
        }}>
          {/* Logo */}
          <Link
            href="/"
            onClick={e => {
              e.preventDefault();
              hardNavigate("/");
            }}
            style={{ display: "flex", alignItems: "center", gap: "12px", textDecoration: "none", flexShrink: 0 }}
          >
            <div style={{
              width: "28px", height: "28px", borderRadius: "7px",
              background: "linear-gradient(135deg, #f0f0fe 0%, #e0e0fc 100%)",
              border: "1px solid rgba(79,70,229,0.2)", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: "13px", color: "#4f46e5",
              boxShadow: "0 0 12px rgba(79,70,229,0.1)",
            }}>◈</div>
            <span style={{
              fontFamily: "var(--font-mono), monospace", fontWeight: 700,
              fontSize: "13px", letterSpacing: "0.22em", color: "#1c1814",
            }}>PRISM</span>
          </Link>

          {/* Nav links */}
          <nav style={{ display: "flex", alignItems: "center", gap: "2px", flex: 1 }}>
            {(user ? NAV_AUTHED : NAV_PUBLIC).map(({ href, label }) => {
              const active =
                href === "/" ? path === "/" :
                href === "/build" ? (path === "/build" || path.startsWith("/trading")) :
                href === "/baskets" ? (path.startsWith("/baskets")) :
                path.startsWith(href);
              const activeBorder = "1px solid rgba(0,0,0,0.1)";
              const navStyle = {
                fontFamily: "var(--font-mono), monospace",
                fontSize: "12px", fontWeight: active ? 700 : 400,
                letterSpacing: "0.08em",
                color: active ? "#1c1814" : "#a8a29a",
                textDecoration: "none",
                padding: "6px 14px",
                borderRadius: "6px",
                background: active ? "rgba(0,0,0,0.05)" : "transparent",
                border: active ? activeBorder : "1px solid transparent",
                transition: "color 0.15s, background 0.15s",
              };
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={e => {
                    e.preventDefault();
                    hardNavigate(href);
                  }}
                  style={navStyle}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.color = "#1c1814"; }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.color = "#a8a29a"; }}
                >{label}</Link>
              );
            })}
          </nav>

          {/* Right side */}
          <div style={{ display: "flex", alignItems: "center", gap: "16px", flexShrink: 0 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: "8px",
              fontFamily: "var(--font-mono), monospace",
              fontSize: "9px", color: "#c8c2bc", letterSpacing: "0.12em",
            }}>
              <span className="blink" style={{ color: "#4f46e5", fontSize: "7px" }}>●</span>
              LIVE
            </div>

            {user ? (
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                {profile ? (
                  <Link
                    href={`/users/${profile.username}`}
                    onClick={e => { e.preventDefault(); hardNavigate(`/users/${profile.username}`); }}
                    style={{
                      fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                      color: "#4f46e5", letterSpacing: "0.04em", textDecoration: "none",
                      fontWeight: 600,
                    }}
                  >
                    @{profile.username}
                  </Link>
                ) : (
                  <span style={{
                    fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                    color: "#a8a29a", letterSpacing: "0.04em",
                    maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {user.email}
                  </span>
                )}
                <button onClick={signOut} style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  fontWeight: 600, letterSpacing: "0.08em",
                  color: "#a8a29a", background: "transparent",
                  border: "1px solid rgba(79,70,229,0.2)", borderRadius: "6px",
                  padding: "5px 12px", cursor: "pointer",
                  transition: "color 0.15s, border-color 0.15s",
                }}
                  onMouseEnter={e => { e.currentTarget.style.color = "#1c1814"; e.currentTarget.style.borderColor = "rgba(0,0,0,0.2)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "#6e675f"; e.currentTarget.style.borderColor = "rgba(0,0,0,0.1)"; }}
                >
                  Sign out
                </button>
              </div>
            ) : (
              <button onClick={() => { setShowModal(true); setMode("signin"); setEmail(""); setPassword(""); setError(""); setSuccess(""); }} style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                fontWeight: 600, letterSpacing: "0.08em",
                color: "#a8a29a", background: "transparent",
                border: "1px solid rgba(79,70,229,0.2)", borderRadius: "6px",
                padding: "5px 12px", cursor: "pointer",
                transition: "color 0.15s, border-color 0.15s",
              }}
                onMouseEnter={e => { e.currentTarget.style.color = "#1c1814"; e.currentTarget.style.borderColor = "rgba(0,0,0,0.2)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "#6e675f"; e.currentTarget.style.borderColor = "rgba(0,0,0,0.1)"; }}
              >
                Sign in
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Sign-in / Sign-up modal */}
      {showModal && (
        <div
          onClick={() => setShowModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#ffffff", border: "1px solid rgba(79,70,229,0.2)",
              borderRadius: "16px", padding: "32px", width: "100%", maxWidth: "380px",
              boxShadow: "0 24px 80px rgba(0,0,0,0.8)",
            }}
          >
            {/* Mode toggle */}
            <div style={{ display: "flex", gap: "4px", marginBottom: "24px", background: "rgba(0,0,0,0.04)", borderRadius: "8px", padding: "4px" }}>
              {(["signin", "signup"] as const).map(m => (
                <button key={m} onClick={() => { setMode(m); setError(""); setSuccess(""); }}
                  style={{
                    flex: 1, padding: "7px", border: "none", borderRadius: "6px",
                    fontFamily: "var(--font-mono), monospace", fontSize: "11px",
                    fontWeight: 600, letterSpacing: "0.08em", cursor: "pointer",
                    background: mode === m ? "#ffffff" : "transparent",
                    color: mode === m ? "#1c1814" : "#a8a29a",
                    transition: "all 0.15s",
                  }}
                >{m === "signin" ? "Sign in" : "Sign up"}</button>
              ))}
            </div>

            {success ? (
              <div style={{ fontSize: "13px", color: "#16a34a", lineHeight: 1.6, marginBottom: "16px" }}>{success}</div>
            ) : (
              <>
                <input type="email" placeholder="Email" value={email}
                  onChange={e => setEmail(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") submit(); }}
                  autoFocus
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "#f8f6f2", border: "1px solid rgba(0,0,0,0.1)",
                    borderRadius: "8px", padding: "10px 14px",
                    fontSize: "13px", color: "#1c1814",
                    fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                    outline: "none", marginBottom: "8px",
                  }}
                />
                <input type="password" placeholder="Password" value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") submit(); }}
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "#f8f6f2", border: "1px solid rgba(0,0,0,0.1)",
                    borderRadius: "8px", padding: "10px 14px",
                    fontSize: "13px", color: "#1c1814",
                    fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                    outline: "none", marginBottom: "8px",
                  }}
                />
                {error && <div style={{ fontSize: "12px", color: "#dc2626", marginBottom: "10px" }}>{error}</div>}
                {(() => {
                  const ready = !!(email.trim() && password.trim());
                  return (
                <button onClick={submit} disabled={loading || !ready}
                  style={{
                    width: "100%", background: ready ? "#4f46e5" : "#f0ede9",
                    color: "#fff", border: "none", borderRadius: "8px",
                    padding: "10px", fontSize: "12px",
                    fontFamily: "var(--font-mono), monospace",
                    fontWeight: 600, letterSpacing: "0.08em",
                    cursor: ready ? "pointer" : "default",
                    opacity: ready ? 1 : 0.4,
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={e => { if (ready) e.currentTarget.style.background = "#4338ca"; }}
                  onMouseLeave={e => { if (ready) e.currentTarget.style.background = "#4f46e5"; }}
                >
                  {loading ? "…" : mode === "signin" ? "Sign in →" : "Create account →"}
                </button>
                  );
                })()}
              </>
            )}
          </div>
        </div>
      )}

      {/* Welcome modal */}
      {showWelcomeModal && (
        <div
          onClick={() => setShowWelcomeModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 110,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#ffffff", border: "1px solid rgba(79,70,229,0.2)",
              borderRadius: "20px", padding: "36px 32px", width: "100%", maxWidth: "400px",
              boxShadow: "0 24px 80px rgba(0,0,0,0.25)", textAlign: "center",
            }}
          >
            <div style={{ fontSize: 40, marginBottom: 12 }}>◈</div>
            <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
              Welcome to Prism
            </div>
            <div style={{ color: "#1c1814", fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em", marginBottom: 6 }}>
              @{welcomeUsername}
            </div>
            <p style={{ color: "#6e675f", fontSize: 14, lineHeight: 1.65, margin: "0 0 24px" }}>
              You&rsquo;re all set. Build a basket around a conviction or browse what the community is betting on.
            </p>
            <div style={{ display: "grid", gap: 10 }}>
              <button
                onClick={() => { setShowWelcomeModal(false); hardNavigate("/trading"); }}
                style={{
                  background: "#4f46e5", color: "#fff", border: "none", borderRadius: 10,
                  padding: "12px 20px", fontSize: 13, fontWeight: 700, cursor: "pointer",
                  fontFamily: "var(--font-mono), monospace", letterSpacing: "0.06em",
                }}
              >
                AI Build →
              </button>
              <button
                onClick={() => { setShowWelcomeModal(false); hardNavigate("/trading/manual"); }}
                style={{
                  background: "transparent", color: "#4f46e5",
                  border: "1px solid rgba(79,70,229,0.25)", borderRadius: 10,
                  padding: "12px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                  fontFamily: "var(--font-mono), monospace", letterSpacing: "0.06em",
                }}
              >
                Basket Studio
              </button>
              <button
                onClick={() => { setShowWelcomeModal(false); hardNavigate("/baskets"); }}
                style={{
                  background: "transparent", color: "#9b9390", border: "none",
                  fontSize: 13, cursor: "pointer", padding: "4px",
                  fontFamily: "var(--font-jakarta), system-ui, sans-serif",
                }}
              >
                Browse community first
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Username setup modal */}
      {showUsernameModal && (
        <div
          onClick={() => { setShowUsernameModal(false); setPendingToken(null); }}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#ffffff", border: "1px solid rgba(79,70,229,0.2)",
              borderRadius: "16px", padding: "32px", width: "100%", maxWidth: "380px",
              boxShadow: "0 24px 80px rgba(0,0,0,0.8)",
            }}
          >
            <div style={{ marginBottom: 20 }}>
              <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
                One more step
              </div>
              <div style={{ color: "#1c1814", fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 6 }}>
                Choose a username
              </div>
              <div style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6 }}>
                This is how you&rsquo;ll appear on public baskets. Lowercase letters, numbers, and underscores only.
              </div>
            </div>

            <div style={{ position: "relative", marginBottom: 12 }}>
              <span style={{
                position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)",
                color: "#a8a29a", fontSize: 13, fontFamily: "var(--font-mono), monospace",
                pointerEvents: "none",
              }}>@</span>
              <input
                type="text"
                placeholder="yourname"
                value={usernameInput}
                onChange={e => setUsernameInput(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                onKeyDown={e => { if (e.key === "Enter") submitUsername(); }}
                maxLength={24}
                autoFocus
                style={{
                  width: "100%", boxSizing: "border-box",
                  background: "#f8f6f2", border: "1px solid rgba(0,0,0,0.1)",
                  borderRadius: "8px", padding: "10px 14px 10px 28px",
                  fontSize: "13px", color: "#1c1814",
                  fontFamily: "var(--font-mono), monospace",
                  outline: "none",
                }}
              />
            </div>

            {usernameError && <div style={{ fontSize: "12px", color: "#dc2626", marginBottom: "10px" }}>{usernameError}</div>}

            <button
              onClick={submitUsername}
              disabled={usernameLoading || usernameInput.length < 3}
              style={{
                width: "100%",
                background: usernameInput.length >= 3 ? "#4f46e5" : "#f0ede9",
                color: "#fff", border: "none", borderRadius: "8px",
                padding: "10px", fontSize: "12px",
                fontFamily: "var(--font-mono), monospace",
                fontWeight: 600, letterSpacing: "0.08em",
                cursor: usernameInput.length >= 3 ? "pointer" : "default",
                opacity: usernameInput.length >= 3 ? 1 : 0.4,
                transition: "background 0.15s",
              }}
              onMouseEnter={e => { if (usernameInput.length >= 3) e.currentTarget.style.background = "#4338ca"; }}
              onMouseLeave={e => { if (usernameInput.length >= 3) e.currentTarget.style.background = "#4f46e5"; }}
            >
              {usernameLoading ? "…" : "Set username →"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
