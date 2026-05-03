"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SignInButton, UserButton, useUser } from "@clerk/nextjs";

const NAV = [
  { href: "/",          label: "Home"      },
  { href: "/forecasts", label: "Intel"     },
  { href: "/model",     label: "Model"     },
];

export default function Header() {
  const path = usePathname();
  const { isSignedIn } = useUser();

  return (
    <header style={{
      position: "fixed", top: 0, left: 0, right: 0, zIndex: 50,
      borderBottom: "1px solid #141414",
      background: "rgba(8,8,8,0.85)",
      backdropFilter: "blur(20px)",
      WebkitBackdropFilter: "blur(20px)",
    }}>
      <div style={{
        maxWidth: "1280px", margin: "0 auto", padding: "0 32px",
        height: "56px", display: "flex", alignItems: "center", gap: "40px",
      }}>
        {/* Logo */}
        <a href="/" style={{ display: "flex", alignItems: "center", gap: "12px", textDecoration: "none", flexShrink: 0 }}>
          <div style={{
            width: "28px", height: "28px", borderRadius: "7px",
            background: "linear-gradient(135deg, #181818 0%, #0a0a0a 100%)",
            border: "1px solid #252525", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: "13px", color: "#e36438",
            boxShadow: "0 0 12px rgba(227,100,56,0.15)",
          }}>◈</div>
          <span style={{
            fontFamily: "var(--font-mono), monospace", fontWeight: 700,
            fontSize: "13px", letterSpacing: "0.22em", color: "#ede9e3",
          }}>PRISM</span>
        </a>

        {/* Nav links */}
        <nav style={{ display: "flex", alignItems: "center", gap: "2px", flex: 1 }}>
          {NAV.map(({ href, label }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            const activeBorder = href === "/trading"
              ? "1px solid rgba(155,127,232,0.35)"
              : href === "/forecasts"
              ? "1px solid rgba(90,170,114,0.35)"
              : "1px solid #252525";
            const navStyle = {
              fontFamily: "var(--font-mono), monospace",
              fontSize: "12px", fontWeight: active ? 700 : 400,
              letterSpacing: "0.08em",
              color: active ? "#ede9e3" : "#6b6865",
              textDecoration: "none",
              padding: "6px 14px",
              borderRadius: "6px",
              background: active ? "rgba(255,255,255,0.04)" : "transparent",
              border: active ? activeBorder : "1px solid transparent",
              transition: "color 0.15s, background 0.15s",
            };
            if (href === "/") {
              return (
                <a
                  key={href}
                  href={href}
                  style={navStyle}
                  onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.color = "#ede9e3"; }}
                  onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.color = "#6b6865"; }}
                >
                  {label}
                </a>
              );
            }
            return (
              <Link
                key={href}
                href={href}
                style={navStyle}
                onMouseEnter={e => { if (!active) e.currentTarget.style.color = "#ede9e3"; }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.color = "#6b6865"; }}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Right side: live indicator + auth */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexShrink: 0 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: "8px",
            fontFamily: "var(--font-mono), monospace",
            fontSize: "9px", color: "#2a2826", letterSpacing: "0.12em",
          }}>
            <span className="blink" style={{ color: "#e36438", fontSize: "7px" }}>●</span>
            LIVE
          </div>

          {!isSignedIn ? (
            <SignInButton mode="modal">
              <button style={{
                fontFamily: "var(--font-mono), monospace", fontSize: "10px",
                fontWeight: 600, letterSpacing: "0.08em",
                color: "#6b6865", background: "transparent",
                border: "1px solid #252525", borderRadius: "6px",
                padding: "5px 12px", cursor: "pointer",
                transition: "color 0.15s, border-color 0.15s",
              }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = "#ede9e3";
                  e.currentTarget.style.borderColor = "#3a3835";
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = "#6b6865";
                  e.currentTarget.style.borderColor = "#252525";
                }}
              >
                Sign in
              </button>
            </SignInButton>
          ) : (
            <UserButton
              appearance={{
                elements: {
                  avatarBox: { width: "28px", height: "28px" },
                },
              }}
            />
          )}
        </div>
      </div>
    </header>
  );
}
