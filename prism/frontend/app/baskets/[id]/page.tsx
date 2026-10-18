"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { ApiError, getBasket, getBasketPerformance, getUserPage, bookmarkBasket, unbookmarkBasket, resolveBasket } from "@/lib/api";
import { createClient } from "@/lib/supabase";
import { BasketCard } from "@/components/BasketCard";
import { BasketTradePanel } from "@/components/BasketTradePanel";
import type { BasketPerformance, BeliefAnalysis, BeliefSummary, PredictionBasket, SavedBasket } from "@/lib/types";
import styles from "./page.module.css";

export default function BasketSharePage() {
  const params = useParams<{ id: string }>();
  const [basket, setBasket] = useState<SavedBasket | null>(null);
  const [basketError, setBasketError] = useState<"missing" | "temporary" | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const [beliefSummary, setBeliefSummary] = useState<BeliefSummary | null>(null);
  const [analysis, setAnalysis] = useState<BeliefAnalysis | null>(null);
  const [copied, setCopied] = useState(false);
  const [authorBaskets, setAuthorBaskets] = useState<SavedBasket[]>([]);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [performance, setPerformance] = useState<BasketPerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [perfError, setPerfError] = useState("");
  const [perfRefreshNonce, setPerfRefreshNonce] = useState(0);
  const [bookmarked, setBookmarked] = useState(false);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [myToken, setMyToken] = useState<string | null>(null);
  const [myUserId, setMyUserId] = useState<string | null>(null);
  const [signInRequest, setSignInRequest] = useState(0);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [resolveNote, setResolveNote] = useState("");
  const [resolveLoading, setResolveLoading] = useState(false);
  const supabase = createClient();

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      setMyToken(data.session?.access_token ?? null);
      setMyUserId(data.session?.user?.id ?? null);
    });
  }, [supabase]);

  const basketId = params?.id;
  useEffect(() => {
    if (!basketId) return;
    let active = true;
    getBasket(Number(basketId), myToken ?? undefined).then((saved) => {
      if (!active) return;
      setBasketError(null);
      setBasket(saved);
      setBookmarked(saved.is_bookmarked ?? false);
      setBeliefSummary(JSON.parse(saved.belief_summary_json));
      setAnalysis(JSON.parse(saved.analysis_json));
    }).catch((error: unknown) => {
      if (active) setBasketError(error instanceof ApiError && error.status === 404 ? "missing" : "temporary");
    });
    return () => { active = false; };
  }, [basketId, myToken, retryNonce]);

  useEffect(() => {
    if (!basket?.username || !basket?.id) return;
    getUserPage(basket.username).then(({ baskets: b }) => {
      setAuthorBaskets(b.filter((x) => x.id !== basket.id).slice(0, 3));
    }).catch(() => {});
  }, [basket?.username, basket?.id]);

  useEffect(() => {
    if (!basket?.id) return;
    let active = true;
    setPerfLoading(true);
    getBasketPerformance(basket.id, myToken ?? undefined).then((data) => {
      if (!active) return;
      setPerformance(data);
      setPerfError("");
    }).catch(() => {
      if (!active) return;
      setPerformance(null);
      setPerfError("Could not load price history right now.");
    }).finally(() => {
      if (active) setPerfLoading(false);
    });
    return () => { active = false; };
  }, [basket?.id, myToken, perfRefreshNonce]);

  async function copyLink() {
    if (typeof window === "undefined" || !navigator.clipboard || !basket) return;
    await navigator.clipboard.writeText(`${window.location.origin}/baskets/${basket.id}`);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  function shareToX() {
    if (!basket) return;
    const url = `${window.location.origin}/baskets/${basket.id}`;
    const metadata: PredictionBasket = (() => { try { return JSON.parse(basket.basket_json); } catch { return {} as PredictionBasket; } })();
    const isEditorial = !!metadata.editorial_hypothetical;
    const text = isEditorial
      ? `"${basket.title}" — a hypothetical Prism editorial concept, not endorsed by the person named`
      : metadata.demo_basket?.created_by === "Prism"
        ? `"${basket.title}" — a sample prediction market basket created by Prism`
        : `"${basket.title}" — my prediction market portfolio on @prismforecaster`;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`, "_blank");
  }

  function shareToLinkedIn() {
    if (!basket) return;
    const url = `${window.location.origin}/baskets/${basket.id}`;
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`, "_blank");
  }

  async function shareToInstagram() {
    if (!basket || generatingImage) return;
    setGeneratingImage(true);
    try {
      const blob = await generateShareImage(basket, JSON.parse(basket.basket_json));
      const file = new File([blob], `prism-${basket.id}.png`, { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: basket.title, text: `${basket.title} — prediction market portfolio` });
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `prism-${(basket.title || "portfolio").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.png`;
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } finally {
      setGeneratingImage(false);
    }
  }

  async function toggleBookmark() {
    if (!myToken || !basket) return;
    setBookmarkLoading(true);
    try {
      if (bookmarked) {
        const result = await unbookmarkBasket(basket.id, myToken);
        setBookmarked(false);
        setBasket(b => b ? { ...b, watchlist_count: result.watchlist_count } : b);
      } else {
        const result = await bookmarkBasket(basket.id, myToken);
        setBookmarked(true);
        setBasket(b => b ? { ...b, watchlist_count: result.watchlist_count } : b);
      }
    } catch {
      // ignore
    }
    setBookmarkLoading(false);
  }

  async function submitResolve() {
    if (!myToken || !basket) return;
    setResolveLoading(true);
    try {
      await resolveBasket(basket.id, resolveNote, myToken);
      setBasket(b => b ? { ...b, resolved_at: new Date().toISOString(), resolution_note: resolveNote } : b);
      setShowResolveModal(false);
    } catch {
      // ignore
    }
    setResolveLoading(false);
  }

  if (!basket) {
    return (
      <div style={{ minHeight: "100vh", background: "#f8f6f2", color: "#1c1814" }}>
        <Header />
        <GridOverlay />
        <div style={{ position: "relative", zIndex: 10, maxWidth: 900, margin: "0 auto", padding: "120px 24px" }}>
          {basketError === "missing" ? "Basket unavailable. It may be private, removed, or this link may be incorrect." :
            basketError === "temporary" ? <div>Could not load this basket right now. <button onClick={() => { setBasketError(null); setRetryNonce(n => n + 1); }} style={{ color: "#4f46e5", background: "none", border: 0, cursor: "pointer", font: "inherit", textDecoration: "underline" }}>Try again</button></div> :
            "Loading basket…"}
        </div>
      </div>
    );
  }

  const parsedBasket = JSON.parse(basket.basket_json);

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header signInRequest={signInRequest} />
      <GridOverlay />
      <div style={{ position: "relative", zIndex: 10, maxWidth: 960, margin: "0 auto", padding: "110px 24px 80px" }}>
        <Link href="/baskets" style={{ color: "#9b9390", fontSize: 13, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 20 }}>
          ← Back to theses
        </Link>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
          <div style={{ color: "#4f46e5", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace" }}>
            Prediction Market Thesis
          </div>
          {basket.resolved_at && (
            <span style={{
              background: "#dcfce7", color: "#15803d",
              fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
              fontFamily: "var(--font-mono), monospace", textTransform: "uppercase", letterSpacing: "0.1em",
            }}>
              ✓ Resolved
            </span>
          )}
        </div>
        <h1 style={{ color: "#1c1814", fontSize: "clamp(34px, 5vw, 56px)", lineHeight: 1.02, letterSpacing: "-0.05em", margin: "0 0 10px" }}>
          {basket.title}
        </h1>
        {basket.username && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <div style={{ width: 24, height: 24, borderRadius: "50%", background: "#4f46e5", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ color: "#fff", fontSize: 9, fontWeight: 700 }}>◈</span>
            </div>
            <Link href={`/users/${basket.username}`} style={{ color: "#6e675f", fontSize: 13, textDecoration: "none", fontFamily: "var(--font-mono), monospace" }}>
              {basket.display_name || `@${basket.username}`}
            </Link>
            {parsedBasket.editorial_hypothetical && (
              <span style={{ color: "#7c3aed", fontSize: 11, fontWeight: 700 }}>Market selections by Prism</span>
            )}
            {parsedBasket.demo_basket?.created_by === "Prism" && (
              <span style={{ color: "#7c3aed", fontSize: 11, fontWeight: 700 }}>Sample basket by Prism</span>
            )}
          </div>
        )}
        <p style={{ color: "#6e675f", fontSize: 17, lineHeight: 1.65, margin: "0 0 26px", maxWidth: 780 }}>
          {basket.summary}
        </p>
        {parsedBasket.editorial_hypothetical && (
          <p style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6, margin: "-12px 0 24px", maxWidth: 780 }}>
            Prism selected the markets in this hypothetical basket. {parsedBasket.editorial_hypothetical.inspiration_person} did not create, review, or endorse these positions.
          </p>
        )}
        {basket.is_public && (
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", color: "#6e675f", fontSize: 13, marginBottom: 18 }}>
            <span><strong style={{ color: "#1c1814" }}>{basket.investor_count ?? 0}</strong> investors</span>
            <span><strong style={{ color: "#1c1814" }}>${(basket.invested_dollars ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong> filled investment</span>
            <span><strong style={{ color: "#1c1814" }}>{basket.watchlist_count ?? 0}</strong> watchlists</span>
          </div>
        )}

        <section id="price-tracking" className={styles.priceTracking} aria-labelledby="price-tracking-title">
          <div className={styles.priceHeader}>
            <div>
              <div className={styles.priceEyebrow}>Market movement</div>
              <h2 id="price-tracking-title" className={styles.priceTitle}>Price tracking</h2>
              <p className={styles.priceDescription}>How the basket&apos;s market prices have moved since it was created.</p>
              <button className={styles.priceRefresh} onClick={() => setPerfRefreshNonce((nonce) => nonce + 1)} disabled={perfLoading}>
                Refresh prices
              </button>
            </div>
            {!perfLoading && !perfError && performance && performance.dates.length > 1 && (
              <div className={styles.priceMetric}>
                <span className={styles.priceMetricLabel}>Indicative change</span>
                <strong className={(performance.current_return ?? 0) >= 0 ? styles.priceUp : styles.priceDown}>
                  {(performance.current_return ?? 0) >= 0 ? "+" : ""}{performance.current_return?.toFixed(1)}%
                </strong>
                <span className={styles.priceMetricDetail}>Index {performance.values[performance.values.length - 1]?.toFixed(1)} · started at 100</span>
              </div>
            )}
          </div>
          {perfLoading ? (
            <div className={styles.priceStatus}>Loading price history…</div>
          ) : perfError ? (
            <div role="alert" className={styles.priceStatus}>{perfError}</div>
          ) : !performance || performance.dates.length < 2 ? (
            <div className={styles.priceStatus}>Tracking begins when these markets receive new Kalshi quotes. Check back as prices move.</div>
          ) : (
            <>
              <div className={styles.chartWrap}>
                <div className={styles.desktopChart}><PerformanceChart dates={performance.dates} values={performance.values} periodMinutes={performance.period_minutes} /></div>
                <div className={styles.mobileChart}><PerformanceChart dates={performance.dates} values={performance.values} periodMinutes={performance.period_minutes} compact /></div>
              </div>
              <div className={styles.priceFooter}>
                <span>{performance.updated_holdings} of {performance.total_holdings} markets have new quotes</span>
                <span>Latest quote {new Date(performance.dates[performance.dates.length - 1]).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
              </div>
              <p className={styles.priceNote}>Indicative mark from Kalshi quotes, indexed to 100 at creation. Markets without new quotes retain their entry price.</p>
            </>
          )}
        </section>

        <div className={styles.thesisTradeGrid} style={basket.resolved_at ? { gridTemplateColumns: "1fr" } : undefined}>
          <section className={styles.thesisCard}>
            <div style={sectionTitleStyle}>Thesis</div>
            <h2 className={styles.thesisHeading}>What this basket predicts</h2>
            <p className={styles.thesisStatement}>{beliefSummary?.core_belief || basket.core_belief || basket.summary}</p>
            {beliefSummary?.resolution_target && beliefSummary.resolution_target !== (beliefSummary.core_belief || basket.core_belief || basket.summary) && (
              <div className={styles.thesisTarget}>
                <span>Resolution target</span>
                <p>{beliefSummary.resolution_target}</p>
              </div>
            )}
          </section>
          {!basket.resolved_at && <BasketTradePanel basketId={basket.id} token={myToken} onSignIn={() => setSignInRequest((request) => request + 1)} onExecution={() => {
            getBasket(basket.id, myToken ?? undefined).then(setBasket).catch(() => {});
          }} />}
        </div>

        <section style={sectionStyle}>
          <div style={sectionTitleStyle}>Holdings</div>
          {(() => {
            const total = parsedBasket.total_notional || parsedBasket.holdings.reduce((s: number, h: { weight_dollars: number }) => s + h.weight_dollars, 0) || 1;
            const colors = ["#4f46e5","#4338ca","#7c73f0","#312e9e","#a5a0f4","#6159eb","#2dd4bf","#f59e0b"];
            return (
              <div style={{ marginBottom: 18 }}>
                <div style={{ display: "flex", height: 6, borderRadius: 999, overflow: "hidden", gap: 2, marginBottom: 10 }}>
                  {(parsedBasket as PredictionBasket).holdings.map((h: { ticker: string; weight_dollars: number }, i: number) => (
                    <div key={h.ticker} style={{ flexBasis: `${(h.weight_dollars / total) * 100}%`, background: colors[i % colors.length], flexShrink: 0 }} />
                  ))}
                </div>
              </div>
            );
          })()}
          <div className={styles.holdingsList}>
            {(parsedBasket as PredictionBasket).holdings.map((holding, index) => (
              <div key={holding.ticker} className={styles.holdingRow}>
                <div className={styles.holdingMain}>
                  <span className={styles.holdingDot} style={{ background: ["#4f46e5","#4338ca","#7c73f0","#312e9e","#a5a0f4","#6159eb","#2dd4bf","#f59e0b"][index % 8] }} />
                  <div className={styles.holdingContent}>
                    <div className={styles.holdingQuestion}>{holding.question}</div>
                    <div className={styles.holdingMeta}>
                      <span className={styles.holdingSide}>{holding.side}</span>
                      <span>Entry odds {Math.round(holding.market_price * 100)}%</span>
                      {holding.close_date && <span>Closes {formatCloseDate(holding.close_date)}</span>}
                    </div>
                    {holding.rationale && (
                      <details className={styles.holdingDetails}>
                        <summary>Why this market</summary>
                        <p>{holding.rationale}</p>
                      </details>
                    )}
                  </div>
                </div>
                <div className={styles.holdingWeight}>
                  <strong>{Math.round((holding.weight_dollars / (parsedBasket.total_notional || 1)) * 100)}%</strong>
                  <span>of basket</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {analysis?.most_surprising_connection && (
          <section style={sectionStyle}>
            <div style={sectionTitleStyle}>What Could Change It</div>
            <div style={{ color: "#6e675f", lineHeight: 1.7 }}>{analysis.most_surprising_connection}</div>
          </section>
        )}

        {basket.thesis_notes && !parsedBasket.editorial_hypothetical && (
          <section style={sectionStyle}>
            <div style={sectionTitleStyle}>{parsedBasket.demo_basket ? "About this sample" : "Creator's Notes"}</div>
            <div style={{ color: "#3a3530", lineHeight: 1.8, whiteSpace: "pre-wrap", fontSize: 15 }}>
              {basket.thesis_notes}
            </div>
          </section>
        )}

        {basket.resolved_at && (
          <section style={{ ...sectionStyle, borderColor: "#bbf7d0", background: "#f0fdf4" }}>
            <div style={{ ...sectionTitleStyle, color: "#15803d" }}>Resolution</div>
            <div style={{ color: "#166534", fontSize: 13, marginBottom: basket.resolution_note ? 8 : 0 }}>
              Marked resolved on {new Date(basket.resolved_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
            </div>
            {basket.resolution_note && (
              <div style={{ color: "#3a3530", lineHeight: 1.75, whiteSpace: "pre-wrap" }}>
                {basket.resolution_note}
              </div>
            )}
          </section>
        )}

        <div style={{ marginTop: 28, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          {beliefSummary?.core_belief && (
            <Link href={`/trading?belief=${encodeURIComponent(beliefSummary.core_belief)}`} style={{
              background: "#4f46e5",
              color: "#fff",
              padding: "10px 18px",
              borderRadius: 12,
              fontWeight: 600,
              textDecoration: "none",
              display: "inline-block",
            }}>
              Remix with AI
            </Link>
          )}
          <Link href={`/trading?basket=${basket.id}`} style={{
            background: "transparent",
            color: "#6e675f",
            border: "1px solid rgba(0,0,0,0.12)",
            padding: "10px 18px",
            borderRadius: 12,
            fontWeight: 600,
            textDecoration: "none",
            display: "inline-block",
          }}>
            Open in builder
          </Link>
          <Link href="/trading/manual" style={{
            background: "transparent",
            color: "#6e675f",
            border: "1px solid rgba(0,0,0,0.12)",
            padding: "10px 18px",
            borderRadius: 12,
            fontWeight: 600,
            textDecoration: "none",
            display: "inline-block",
          }}>
            Edit basket
          </Link>
          <button
            onClick={copyLink}
            style={{
              background: "transparent",
              color: "#6e675f",
              border: "1px solid rgba(0,0,0,0.12)",
              padding: "10px 18px",
              borderRadius: 12,
              fontWeight: 600,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            {copied ? "Copied ✓" : "Copy link"}
          </button>
          <a
            href="#price-tracking"
            style={{
              background: "transparent",
              color: "#6e675f",
              border: "1px solid rgba(0,0,0,0.12)",
              padding: "10px 18px",
              borderRadius: 12,
              fontWeight: 600,
              fontSize: 14,
              textDecoration: "none",
            }}
          >
            Price tracking
          </a>
          {myToken && (
            <button
              onClick={toggleBookmark}
              disabled={bookmarkLoading}
              style={{
                background: bookmarked ? "#fffbeb" : "transparent",
                color: bookmarked ? "#d97706" : "#6e675f",
                border: "1px solid " + (bookmarked ? "#fde68a" : "rgba(0,0,0,0.12)"),
                padding: "10px 18px",
                borderRadius: 12,
                fontWeight: 600,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              {bookmarkLoading ? "…" : bookmarked ? "★ In watchlist" : "☆ Add to watchlist"}
            </button>
          )}
          {myToken && myUserId && basket.user_id === myUserId && !basket.resolved_at && (
            <button
              onClick={() => setShowResolveModal(true)}
              style={{
                background: "transparent", color: "#6e675f",
                border: "1px solid rgba(0,0,0,0.12)",
                padding: "10px 18px", borderRadius: 12,
                fontWeight: 600, fontSize: 14, cursor: "pointer",
              }}
            >
              Mark resolved
            </button>
          )}
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ color: "#9b9390", fontSize: 12, fontFamily: "var(--font-mono), monospace", textTransform: "uppercase", letterSpacing: "0.1em", marginRight: 4 }}>Share</span>
          <button onClick={shareToX} style={socialBtnStyle} title="Share on X">
            <XIcon /> X
          </button>
          <button onClick={shareToLinkedIn} style={socialBtnStyle} title="Share on LinkedIn">
            <LinkedInIcon /> LinkedIn
          </button>
          <button onClick={shareToInstagram} disabled={generatingImage} style={{ ...socialBtnStyle, opacity: generatingImage ? 0.6 : 1 }} title="Download image for Instagram">
            <InstagramIcon /> {generatingImage ? "Generating…" : "Instagram"}
          </button>
        </div>

        {authorBaskets.length > 0 && basket.username && (
          <div style={{ marginTop: 40 }}>
            <div style={sectionTitleStyle}>More from {basket.display_name || `@${basket.username}`}</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
              {authorBaskets.map((b) => (
                <BasketCard key={b.id} basket={b} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Resolve modal */}
      {showResolveModal && (
        <div
          onClick={() => setShowResolveModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "#ffffff", border: "1px solid rgba(0,0,0,0.12)",
              borderRadius: 20, padding: "28px", width: "100%", maxWidth: 440,
              boxShadow: "0 24px 80px rgba(0,0,0,0.2)",
            }}
          >
            <div style={{ color: "#15803d", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.14em", fontFamily: "var(--font-mono), monospace", marginBottom: 8 }}>
              Resolve thesis
            </div>
            <div style={{ color: "#1c1814", fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 6 }}>
              How did it play out?
            </div>
            <div style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
              Write a retrospective — what happened, what you got right or wrong.
            </div>
            <textarea
              value={resolveNote}
              onChange={e => setResolveNote(e.target.value)}
              rows={5}
              placeholder="The thesis played out because…"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "#f8f6f2", border: "1px solid rgba(0,0,0,0.1)",
                borderRadius: 8, padding: "10px 12px", fontSize: 13,
                color: "#1c1814", outline: "none", resize: "vertical",
                marginBottom: 14,
                fontFamily: "var(--font-jakarta), system-ui, sans-serif",
              }}
            />
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={submitResolve}
                disabled={resolveLoading}
                style={{
                  flex: 1, background: "#16a34a", color: "#fff", border: "none",
                  borderRadius: 10, padding: "11px", fontSize: 13, fontWeight: 700,
                  cursor: "pointer", opacity: resolveLoading ? 0.6 : 1,
                  fontFamily: "var(--font-mono), monospace", letterSpacing: "0.06em",
                }}
              >
                {resolveLoading ? "Saving…" : "Mark as resolved →"}
              </button>
              <button
                onClick={() => setShowResolveModal(false)}
                style={{
                  background: "transparent", color: "#9b9390",
                  border: "1px solid rgba(0,0,0,0.1)", borderRadius: 10,
                  padding: "11px 16px", fontSize: 13, cursor: "pointer",
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

const sectionStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 22,
  padding: 22,
  boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
  marginTop: 18,
};

const sectionTitleStyle: React.CSSProperties = {
  color: "#4f46e5",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.16em",
  fontFamily: "var(--font-mono), monospace",
  marginBottom: 12,
};

function formatCloseDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function PerformanceChart({ dates, values, periodMinutes, compact = false }: { dates: string[]; values: number[]; periodMinutes: number | null; compact?: boolean }) {
  const W = compact ? 320 : 560, H = compact ? 175 : 160, PL = compact ? 32 : 44, PR = compact ? 8 : 16, PT = 16, PB = compact ? 34 : 28;
  const cW = W - PL - PR, cH = H - PT - PB;
  const n = values.length;
  const times = dates.map((date) => new Date(date).getTime());
  const span = Math.max(times[n - 1] - times[0], 1);

  const minV = Math.min(...values, 92);
  const maxV = Math.max(...values, 108);
  const range = maxV - minV || 1;

  const toX = (i: number) => PL + ((times[i] - times[0]) / span) * cW;
  const toY = (v: number) => PT + cH - ((v - minV) / range) * cH;

  const baseY = Math.min(Math.max(toY(100), PT), PT + cH);
  const lastVal = values[n - 1];
  const color = lastVal >= 100 ? "#16a34a" : "#dc2626";

  const pts = values.map((v, i) => `${toX(i)},${toY(v)}`).join(" ");
  const linePath = values.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i)} ${toY(v)}`).join(" ");
  const areaPath = `${linePath} L${toX(n - 1)} ${baseY} L${toX(0)} ${baseY} Z`;

  // Y-axis labels (100 + one tick above/below)
  const yLabels = Array.from(new Set([100, Math.round(minV + range * 0.25), Math.round(maxV - range * 0.25)])).sort((a, b) => b - a);

  // X-axis: show ~4 date labels
  const xIdxs = (compact ? [0, n - 1] : [0, Math.floor(n * 0.33), Math.floor(n * 0.66), n - 1]).filter((v, i, a) => a.indexOf(v) === i);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {/* Grid lines */}
      {yLabels.map((v) => (
        <line key={v} x1={PL} y1={toY(v)} x2={W - PR} y2={toY(v)}
          stroke={v === 100 ? "rgba(0,0,0,0.15)" : "rgba(0,0,0,0.06)"}
          strokeWidth={v === 100 ? 1.5 : 1}
          strokeDasharray={v === 100 ? "4 3" : "2 3"} />
      ))}

      {/* Area fill */}
      <path d={areaPath} fill={color} opacity={0.1} />

      {/* Line */}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

      {/* Last dot */}
      <circle cx={toX(n - 1)} cy={toY(lastVal)} r={4} fill={color} />

      {/* Y labels */}
      {yLabels.map((v) => (
        <text key={v} x={PL - 4} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#9b9390" fontFamily="monospace">{v}</text>
      ))}

      {/* X labels */}
      {xIdxs.map((i) => (
        <text key={i} x={toX(i)} y={H - 4} textAnchor={compact ? (i === 0 ? "start" : "end") : "middle"} fontSize={compact ? 10 : 9} fill="#9b9390" fontFamily="monospace">
          {new Date(dates[i]).toLocaleString(undefined, periodMinutes === 1440
            ? { month: "short", day: "numeric" }
            : compact ? { month: "short", day: "numeric", hour: "numeric" } : { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
        </text>
      ))}
    </svg>
  );
}

const socialBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  background: "transparent",
  color: "#3a3530",
  border: "1px solid rgba(0,0,0,0.12)",
  padding: "8px 14px",
  borderRadius: 10,
  fontWeight: 500,
  fontSize: 13,
  cursor: "pointer",
};

function XIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}

function InstagramIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z" />
    </svg>
  );
}

function rrect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const test = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(test).width > maxW && cur) { lines.push(cur); cur = w; }
    else cur = test;
  }
  if (cur) lines.push(cur);
  return lines;
}

async function generateShareImage(basket: SavedBasket, parsedBasket: PredictionBasket): Promise<Blob> {
  const W = 1080, H = 1080, PAD = 80;
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  // Background
  ctx.fillStyle = "#f8f6f2";
  ctx.fillRect(0, 0, W, H);

  // Subtle grid
  ctx.strokeStyle = "rgba(0,0,0,0.035)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= W; x += 54) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y <= H; y += 54) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

  // Indigo left accent
  ctx.fillStyle = "#4f46e5";
  ctx.fillRect(PAD, PAD, 5, 52);

  // PRISM header
  ctx.fillStyle = "#4f46e5";
  ctx.font = "bold 30px monospace";
  ctx.fillText("◈  PRISM", PAD + 18, PAD + 33);
  ctx.fillStyle = "#9b9390";
  ctx.font = "20px monospace";
  ctx.fillText("PREDICTION MARKET ETF", PAD + 18, PAD + 58);
  if (parsedBasket.demo_basket?.created_by === "Prism") {
    ctx.fillText("SAMPLE BASKET BY PRISM", PAD + 18, PAD + 89);
  }

  // Divider
  ctx.fillStyle = "rgba(0,0,0,0.08)";
  ctx.fillRect(PAD, PAD + 72, W - PAD * 2, 1);

  // Title
  const titleSize = basket.title.length > 35 ? 56 : 68;
  ctx.fillStyle = "#1c1814";
  ctx.font = `bold ${titleSize}px Arial`;
  const titleLines = wrapLines(ctx, basket.title, W - PAD * 2);
  let curY = PAD + 72 + 70;
  titleLines.slice(0, 3).forEach(line => { ctx.fillText(line, PAD, curY); curY += titleSize * 1.15; });

  // Summary
  curY += 12;
  ctx.fillStyle = "#6e675f";
  ctx.font = "27px Arial";
  const summLines = wrapLines(ctx, basket.summary || "", W - PAD * 2);
  summLines.slice(0, 2).forEach(line => { ctx.fillText(line, PAD, curY); curY += 38; });

  // Holdings
  const holdings = parsedBasket.holdings;
  const total = parsedBasket.total_notional || holdings.reduce((s, h) => s + h.weight_dollars, 0) || 1;
  const colors = ["#4f46e5", "#4338ca", "#7c73f0", "#312e9e", "#a5a0f4"];

  curY = Math.max(curY + 36, 620);

  // Allocation bar
  const barTotalW = W - PAD * 2;
  let barX = PAD;
  holdings.slice(0, 6).forEach((h, i) => {
    const segW = Math.max((h.weight_dollars / total) * barTotalW - 3, 4);
    rrect(ctx, barX, curY, segW, 14, 4);
    ctx.fillStyle = colors[i % colors.length];
    ctx.fill();
    barX += segW + 3;
  });
  curY += 30;

  // Holdings label
  ctx.fillStyle = "#4f46e5";
  ctx.font = "bold 18px monospace";
  ctx.fillText("HOLDINGS", PAD, curY);
  curY += 26;

  holdings.slice(0, 5).forEach((h, i) => {
    const pct = Math.round((h.weight_dollars / total) * 100);
    const fillW = Math.max((pct / 100) * 440, 8);

    // Track background
    rrect(ctx, PAD, curY, 440, 34, 7);
    ctx.fillStyle = "rgba(0,0,0,0.05)";
    ctx.fill();
    // Track fill
    rrect(ctx, PAD, curY, fillW, 34, 7);
    ctx.fillStyle = colors[i % colors.length];
    ctx.fill();

    // Pct label
    ctx.fillStyle = "#1c1814";
    ctx.font = "bold 22px monospace";
    ctx.fillText(`${pct}%`, PAD + 452, curY + 23);

    // Market label
    ctx.fillStyle = "#2e2924";
    ctx.font = "22px Arial";
    const label = (h.event_title && h.event_title !== h.question ? h.event_title : h.question) || "";
    const truncated = label.length > 28 ? label.slice(0, 27) + "…" : label;
    ctx.fillText(truncated, PAD + 510, curY + 23);

    curY += 50;
  });

  // Footer URL
  ctx.fillStyle = "#9b9390";
  ctx.font = "22px monospace";
  const host = typeof window !== "undefined" ? window.location.host : "prism.markets";
  const hostW = ctx.measureText(host).width;
  ctx.fillText(host, W - PAD - hostW, H - PAD + 20);

  return new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b!), "image/png"));
}
