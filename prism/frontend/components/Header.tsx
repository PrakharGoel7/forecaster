"use client";
import Link from "next/link";

export default function Header() {
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
        height: "56px", display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: "12px", textDecoration: "none" }}>
          <div style={{
            width: "28px", height: "28px", borderRadius: "7px",
            background: "linear-gradient(135deg, #181818 0%, #0a0a0a 100%)",
            border: "1px solid #252525", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: "13px", color: "#e36438",
            boxShadow: "0 0 12px rgba(227,100,56,0.15)",
          }}>
            ◈
          </div>
          <span style={{
            fontFamily: "var(--font-mono), monospace", fontWeight: 700,
            fontSize: "13px", letterSpacing: "0.22em", color: "#ede9e3",
          }}>
            PRISM
          </span>
        </Link>

        <div style={{
          display: "flex", alignItems: "center", gap: "8px",
          fontFamily: "var(--font-mono), monospace",
          fontSize: "9px", color: "#2a2826", letterSpacing: "0.12em",
        }}>
          <span className="blink" style={{ color: "#e36438", fontSize: "7px" }}>●</span>
          LIVE
        </div>
      </div>
    </header>
  );
}
