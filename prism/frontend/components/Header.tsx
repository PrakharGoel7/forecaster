"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

const NAV = [
  { href: "/",          label: "Home"      },
  { href: "/trading",   label: "AI Build"  },
  { href: "/trading/manual", label: "Manual Build" },
  { href: "/baskets",   label: "Baskets"   },
  { href: "/model",     label: "Model"     },
];

export default function Header() {
  const path = usePathname();
  const router = useRouter();
  const supabase = createClient();
  const [user, setUser] = useState<User | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getUser().then(({ data }) => setUser(data.user));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => {
      setUser(session?.user ?? null);
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
      const { error: e } = await supabase.auth.signUp({ email, password });
      if (e) setError(e.message);
      else setSuccess("Account created! Check your email to confirm, then sign in.");
    }
    setLoading(false);
  }

  async function signOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    router.refresh();
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
              background: "linear-gradient(135deg, #fff4ef 0%, #ffe8de 100%)",
              border: "1px solid rgba(227,100,56,0.2)", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: "13px", color: "#e36438",
              boxShadow: "0 0 12px rgba(227,100,56,0.1)",
            }}>◈</div>
            <span style={{
              fontFamily: "var(--font-mono), monospace", fontWeight: 700,
              fontSize: "13px", letterSpacing: "0.22em", color: "#1c1814",
            }}>PRISM</span>
          </Link>

          {/* Nav links */}
          <nav style={{ display: "flex", alignItems: "center", gap: "2px", flex: 1 }}>
            {NAV.map(({ href, label }) => {
              const active =
                href === "/" ? path === "/" :
                href === "/trading" ? path === "/trading" :
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
              <span className="blink" style={{ color: "#e36438", fontSize: "7px" }}>●</span>
              LIVE
            </div>

            {user ? (
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  color: "#a8a29a", letterSpacing: "0.04em",
                  maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {user.email}
                </span>
                <button onClick={signOut} style={{
                  fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                  fontWeight: 600, letterSpacing: "0.08em",
                  color: "#a8a29a", background: "transparent",
                  border: "1px solid rgba(227,100,56,0.2)", borderRadius: "6px",
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
                border: "1px solid rgba(227,100,56,0.2)", borderRadius: "6px",
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

      {/* Sign-in modal */}
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
              background: "#ffffff", border: "1px solid rgba(227,100,56,0.2)",
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
                    outline: "none", marginBottom: "12px",
                  }}
                />
                {error && <div style={{ fontSize: "12px", color: "#dc2626", marginBottom: "10px" }}>{error}</div>}
                <button onClick={submit} disabled={loading || !email.trim() || !password.trim()}
                  style={{
                    width: "100%", background: (email.trim() && password.trim()) ? "#e36438" : "#f0ede9",
                    color: "#fff", border: "none", borderRadius: "8px",
                    padding: "10px", fontSize: "12px",
                    fontFamily: "var(--font-mono), monospace",
                    fontWeight: 600, letterSpacing: "0.08em",
                    cursor: (email.trim() && password.trim()) ? "pointer" : "default",
                    opacity: (email.trim() && password.trim()) ? 1 : 0.4,
                    transition: "background 0.15s",
                  }}
                  onMouseEnter={e => { if (email.trim() && password.trim()) e.currentTarget.style.background = "#c4421a"; }}
                  onMouseLeave={e => { if (email.trim() && password.trim()) e.currentTarget.style.background = "#e36438"; }}
                >
                  {loading ? "…" : mode === "signin" ? "Sign in →" : "Create account →"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
