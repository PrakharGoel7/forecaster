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

  useEffect(() => {
    listPublicBaskets(96).then(setBaskets).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const totalPages = Math.max(1, Math.ceil(baskets.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = baskets.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <div style={{ minHeight: "100vh", background: "#080808", position: "relative" }}>
      <Header />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 1200, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={{ marginBottom: 36 }}>
          <div style={eyebrowStyle}>Community</div>
          <h1 style={{ color: "#ede9e3", fontSize: "clamp(32px, 5vw, 56px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 12px" }}>
            Public Baskets
          </h1>
          <p style={{ color: "#948c84", fontSize: 17, lineHeight: 1.65, margin: 0, maxWidth: 600 }}>
            Prediction market baskets built by the Prism community. Click any basket to inspect the thesis and holdings.
          </p>
        </div>

        {loading ? (
          <div style={{ color: "#6f6861", fontSize: 15 }}>Loading baskets…</div>
        ) : !baskets.length ? (
          <div style={{ color: "#6f6861", fontSize: 15 }}>No public baskets yet. Be the first to build one.</div>
        ) : (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 16,
            }}>
              {visible.map((basket) => (
                <BasketCard key={basket.id} basket={basket} />
              ))}
            </div>

            {totalPages > 1 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 28, gap: 12 }}>
                <div style={{ color: "#7f776f", fontSize: 13 }}>
                  Page {currentPage} of {totalPages} · {baskets.length} baskets
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
  color: "#e36438",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 12,
};

const ghostButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "#8d857d",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 12,
  padding: "10px 16px",
  cursor: "pointer",
  fontSize: 13,
};
