"use client";

import { useEffect, useState } from "react";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { listPublicBaskets } from "@/lib/api";
import type { SavedBasket } from "@/lib/types";

const PAGE_SIZE = 12;

export default function BasketsPage() {
  const [baskets, setBaskets] = useState<SavedBasket[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [sort, setSort] = useState<"newest" | "positions">("newest");
  const [modeFilter, setModeFilter] = useState<"all" | "ai" | "manual">("all");

  useEffect(() => {
    listPublicBaskets(96).then(setBaskets).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const filteredBaskets = (() => {
    let list = baskets.filter((basket) => {
      if (modeFilter === "ai" && basket.mode === "manual") return false;
      if (modeFilter === "manual" && basket.mode !== "manual") return false;
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return basket.title.toLowerCase().includes(q) || basket.summary.toLowerCase().includes(q);
    });
    if (sort === "positions") {
      list = [...list].sort((a, b) => {
        const count = (x: typeof a) => { try { return JSON.parse(x.basket_json)?.holdings?.length ?? 0; } catch { return 0; } };
        return count(b) - count(a);
      });
    }
    return list;
  })();

  const totalPages = Math.max(1, Math.ceil(filteredBaskets.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filteredBaskets.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1200, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ marginBottom: 36 }}>
          <div style={eyebrowStyle}>Community</div>
          <h1 style={{ color: "#1c1814", fontSize: "clamp(32px, 5vw, 56px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
            What people are betting on
          </h1>
          <p style={{ color: "#6e675f", fontSize: 17, lineHeight: 1.65, margin: 0, maxWidth: 600 }}>
            Browse prediction market theses from the Prism community.
          </p>
        </div>

        <input
          placeholder="Search baskets..."
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
          style={{
            width: "100%",
            maxWidth: 480,
            background: "#ffffff",
            border: "1px solid rgba(0,0,0,0.1)",
            borderRadius: 12,
            padding: "10px 16px",
            fontSize: 14,
            color: "#1c1814",
            outline: "none",
            marginBottom: 12,
            display: "block",
          }}
        />

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 28, alignItems: "center" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {(["all", "ai", "manual"] as const).map((f) => (
              <button
                key={f}
                onClick={() => { setModeFilter(f); setPage(1); }}
                style={{
                  borderRadius: 999, border: `1px solid ${modeFilter === f ? "rgba(79,70,229,0.4)" : "rgba(0,0,0,0.08)"}`,
                  background: modeFilter === f ? "rgba(79,70,229,0.1)" : "rgba(0,0,0,0.03)",
                  color: modeFilter === f ? "#1c1814" : "#6e675f",
                  padding: "7px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                {f === "all" ? "All" : f === "ai" ? "AI Built" : "Manual"}
              </button>
            ))}
          </div>
          <div style={{ width: 1, height: 20, background: "rgba(0,0,0,0.1)", margin: "0 4px" }} />
          <div style={{ display: "flex", gap: 6 }}>
            {(["newest", "positions"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSort(s)}
                style={{
                  borderRadius: 999, border: `1px solid ${sort === s ? "rgba(79,70,229,0.4)" : "rgba(0,0,0,0.08)"}`,
                  background: sort === s ? "rgba(79,70,229,0.1)" : "rgba(0,0,0,0.03)",
                  color: sort === s ? "#1c1814" : "#6e675f",
                  padding: "7px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                {s === "newest" ? "Newest" : "Most positions"}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div style={{ color: "#9b9390", fontSize: 15 }}>Loading baskets…</div>
        ) : !baskets.length ? (
          <div style={{ color: "#9b9390", fontSize: 15 }}>No public baskets yet. Be the first to build one.</div>
        ) : (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 20,
            }}>
              {visible.map((basket) => (
                <BasketCard key={basket.id} basket={basket} />
              ))}
            </div>

            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 28, gap: 12 }}>
                <div style={{ color: "#9b9390", fontSize: 13 }}>
                  Page {currentPage} of {totalPages} · {filteredBaskets.length} baskets
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    style={{ ...ghostButtonStyle, opacity: currentPage === 1 ? 0.4 : 1, cursor: currentPage === 1 ? "default" : "pointer" }}
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    style={{ ...ghostButtonStyle, opacity: currentPage === totalPages ? 0.4 : 1, cursor: currentPage === totalPages ? "default" : "pointer" }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
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

const ghostButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "#6e675f",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 12,
  padding: "10px 16px",
  cursor: "pointer",
  fontSize: 13,
};
