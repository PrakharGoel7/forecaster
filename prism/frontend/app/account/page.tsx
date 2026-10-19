"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import GridOverlay from "@/components/GridOverlay";
import { BasketCard } from "@/components/BasketCard";
import { deleteKalshiCredentials, getBookmarks, getKalshiCredentials, getPortfolio, getPortfolioTrades, reconcilePortfolio, saveKalshiCredentials } from "@/lib/api";
import { createClient } from "@/lib/supabase";
import type { KalshiCredentialsStatus, Portfolio, PortfolioOrder, PortfolioTrade, SavedBasket } from "@/lib/types";

const money = (value: number | null | undefined) => value == null ? "Unavailable" : `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "The request failed. Please try again.";
  try {
    const parsed = JSON.parse(error.message);
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch { /* raw error */ }
  return error.message;
}

export default function AccountPage() {
  const [token, setToken] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [credentials, setCredentials] = useState<KalshiCredentialsStatus | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<PortfolioTrade[]>([]);
  const [orders, setOrders] = useState<PortfolioOrder[]>([]);
  const [watchlist, setWatchlist] = useState<SavedBasket[]>([]);
  const [keyId, setKeyId] = useState("");
  const [privateKeyPem, setPrivateKeyPem] = useState("");
  const [busy, setBusy] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const supabase = createClient();
    if (!supabase) { Promise.resolve().then(() => setAuthReady(true)); return; }
    supabase.auth.getSession().then(({ data }) => { setToken(data.session?.access_token ?? null); setAuthReady(true); });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => {
      setToken(session?.access_token ?? null);
      setAuthReady(true);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!token) {
      Promise.resolve().then(() => { setCredentials(null); setPortfolio(null); setTrades([]); setOrders([]); setWatchlist([]); });
      return;
    }
    let active = true;
    Promise.resolve().then(() => { if (active) setLoading(true); });
    Promise.allSettled([getKalshiCredentials(token), getPortfolio(token), getPortfolioTrades(token), getBookmarks(token)])
      .then(([credentialResult, portfolioResult, tradesResult, watchlistResult]) => {
        if (!active) return;
        if (credentialResult.status === "fulfilled") setCredentials(credentialResult.value);
        if (portfolioResult.status === "fulfilled") setPortfolio(portfolioResult.value);
        if (tradesResult.status === "fulfilled") { setTrades(tradesResult.value.trades); setOrders(tradesResult.value.orders); }
        if (watchlistResult.status === "fulfilled") setWatchlist(watchlistResult.value);
        if (credentialResult.status === "rejected" || portfolioResult.status === "rejected" || tradesResult.status === "rejected" || watchlistResult.status === "rejected") {
          setError("Some account information could not be loaded. Refresh to try again.");
        }
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token]);

  async function saveCredentials(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !keyId.trim() || !privateKeyPem.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const status = await saveKalshiCredentials(keyId.trim(), privateKeyPem.trim(), token);
      setCredentials(status);
      setKeyId(""); setPrivateKeyPem("");
      setNotice("Kalshi connection verified for balance access. Order permission is checked when you trade.");
      getPortfolio(token).then(setPortfolio).catch(() => {});
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    if (!token) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await deleteKalshiCredentials(token);
      setCredentials({ connected: false });
      setNotice("Kalshi credentials removed. Existing trade history remains visible.");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function refreshOrders() {
    if (!token || reconciling) return;
    setReconciling(true); setError(""); setNotice("");
    try {
      await reconcilePortfolio(token);
      const [updatedPortfolio, updatedTrades] = await Promise.all([getPortfolio(token), getPortfolioTrades(token)]);
      setPortfolio(updatedPortfolio);
      setTrades(updatedTrades.trades);
      setOrders(updatedTrades.orders);
      setNotice("Order statuses refreshed from Kalshi.");
    } catch (err) { setError(errorMessage(err)); }
    finally { setReconciling(false); }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f8f6f2", position: "relative" }}>
      <Header /><GridOverlay />
      <main style={{ position: "relative", zIndex: 10, maxWidth: 1000, margin: "0 auto", padding: "110px 24px 80px" }}>
        <div style={eyebrow}>Your account</div>
        <h1 style={{ color: "#1c1814", fontSize: "clamp(32px, 5vw, 50px)", letterSpacing: "-0.05em", margin: "0 0 10px" }}>Portfolio & settings</h1>
        <p style={{ color: "#6e675f", fontSize: 15, lineHeight: 1.6, marginBottom: 26 }}>Review orders placed through Angles, confirmed Kalshi fills, Angles basket positions, and their performance over time. Trades made directly on Kalshi are not shown here.</p>
        {!authReady || loading ? <p style={{ color: "#6e675f" }}>Loading account…</p> : !token ? (
          <section style={card}><p style={{ color: "#6e675f", margin: 0 }}>Sign in from the menu above to connect Kalshi and view your portfolio.</p></section>
        ) : (
          <>
            {error && <div role="alert" style={{ color: "#b91c1c", background: "#fef2f2", padding: 12, borderRadius: 10, marginBottom: 14 }}>{error}</div>}
            {notice && <div role="status" style={{ color: "#15803d", background: "#f0fdf4", padding: 12, borderRadius: 10, marginBottom: 14 }}>{notice}</div>}
            <section style={card}>
              <div style={eyebrow}>Kalshi connection</div>
              {credentials?.connected ? (
                <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
                  <div style={{ flex: 1, color: "#15803d", fontWeight: 700 }}>Connected · API key {credentials.key_id_masked || "verified"}</div>
                  <button onClick={disconnect} disabled={busy} style={secondaryButton}>Disconnect</button>
                </div>
              ) : (
                <>
                  <p style={{ color: "#6e675f", fontSize: 13, lineHeight: 1.6 }}>Create a trade-enabled API key in your Kalshi account and paste its key ID and private key here. Angles verifies balance access now; Kalshi checks order permission when you trade. The private key is sent to the server and is never displayed again.</p>
                  <form onSubmit={saveCredentials} style={{ display: "grid", gap: 12 }}>
                    <label style={label}>API key ID<input required autoComplete="off" value={keyId} onChange={e => setKeyId(e.target.value)} style={input} /></label>
                    <label style={label}>Private key (PEM)<textarea required rows={5} autoComplete="off" value={privateKeyPem} onChange={e => setPrivateKeyPem(e.target.value)} style={{ ...input, resize: "vertical", fontFamily: "monospace" }} /></label>
                    <button type="submit" disabled={busy} style={{ ...primaryButton, justifySelf: "start" }}>{busy ? "Verifying…" : "Verify and connect Kalshi"}</button>
                  </form>
                </>
              )}
            </section>
            <section style={card}>
              <div style={eyebrow}>Angles basket portfolio</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                <Metric label="Confirmed invested" value={money(portfolio?.summary.invested_dollars ?? 0)} />
                <Metric label="Current marked value" value={money(portfolio?.summary.current_value_dollars)} />
                <Metric label="Unrealized P/L" value={money(portfolio?.summary.unrealized_pnl_dollars)} />
                <Metric label="Kalshi cash balance" value={money(portfolio?.summary.kalshi_cash_balance_dollars)} />
              </div>
              <div style={{ color: "#9b9390", fontSize: 11, marginTop: 12 }}>
                {portfolio?.summary.valuation_status === "partial" ? `Valuation incomplete: ${portfolio.summary.marked_position_count} of ${portfolio.summary.position_count} positions currently marked. Closed markets awaiting settlement and unavailable quotes have no estimated value.` : "Values use confirmed fills and available market marks. They can differ from Kalshi's final settlement value."}
              </div>
            </section>
            <section style={card}>
              <div style={eyebrow}>Performance over time</div>
              {portfolio?.history && portfolio.history.length >= 2 ? <PortfolioChart history={portfolio.history} /> : (
                <p style={{ color: "#6e675f", fontSize: 13, margin: 0 }}>A chart will appear after your first confirmed fills and subsequent valuation snapshots.</p>
              )}
              <div style={{ color: "#9b9390", fontSize: 11, marginTop: 10 }}>Indicative daily marks from Kalshi history when available; otherwise recorded portfolio snapshots. Intraday moves and settlement values may be missing.</div>
            </section>
            <section style={card}>
              <div style={eyebrow}>Angles basket positions</div>
              {!portfolio?.positions.length ? <p style={{ color: "#6e675f", fontSize: 13, margin: 0 }}>No confirmed basket positions yet.</p> : (
                <div style={{ overflowX: "auto" }}><table style={table}><thead><tr><th style={cell}>Basket / market</th><th style={cell}>Side</th><th style={cell}>Contracts</th><th style={cell}>Status</th><th style={cell}>Invested</th><th style={cell}>Current value</th><th style={cell}>Unrealized P/L</th></tr></thead><tbody>
                  {portfolio.positions.map((p, i) => <tr key={`${p.basket_id}-${p.ticker}-${p.side}-${i}`} style={row}><td style={cell}><Link href={`/baskets/${p.basket_id}`} style={{ color: "#216a4a", fontWeight: 700 }}>{p.basket_title}</Link><div style={{ color: "#6e675f" }}>{p.ticker}</div></td><td style={cell}>{p.side}</td><td style={cell}>{p.contracts}</td><td style={cell}>{p.status.replaceAll("_", " ")}</td><td style={cell}>{money(p.invested_dollars)}</td><td style={cell}>{money(p.current_value_dollars)}</td><td style={cell}>{money(p.unrealized_pnl_dollars)}</td></tr>)}
                </tbody></table></div>
              )}
            </section>
            <section style={card}>
              <div style={eyebrow}>Angles order history · all outcomes</div>
              {credentials?.connected && <button onClick={refreshOrders} disabled={reconciling} style={{ ...secondaryButton, color: "#216a4a", borderColor: "rgba(33,106,74,0.25)", marginBottom: 12 }}>{reconciling ? "Checking Kalshi…" : "Refresh order statuses"}</button>}
              {!orders.length ? <p style={{ color: "#6e675f", fontSize: 13, margin: 0 }}>No basket orders submitted yet.</p> : (
                <div style={{ overflowX: "auto" }}><table style={table}><thead><tr><th style={cell}>Submitted</th><th style={cell}>Basket / market</th><th style={cell}>Side</th><th style={cell}>Status</th><th style={cell}>Filled</th><th style={cell}>Filled cost</th></tr></thead><tbody>
                  {orders.map((o, i) => <tr key={`${o.client_order_id}-${i}`} style={row}><td style={cell}>{new Date(o.created_at).toLocaleString()}</td><td style={cell}><Link href={`/baskets/${o.basket_id}`} style={{ color: "#216a4a", fontWeight: 700 }}>{o.basket_title}</Link><div style={{ color: "#6e675f" }}>{o.ticker}</div></td><td style={cell}>{o.side}</td><td style={cell}><strong style={{ color: o.status === "filled" ? "#15803d" : o.status === "failed" ? "#b91c1c" : "#92400e" }}>{o.status.replaceAll("_", " ")}</strong>{o.error && <div style={{ color: "#b91c1c", whiteSpace: "normal", maxWidth: 280 }}>{o.error}</div>}</td><td style={cell}>{o.filled_contracts}</td><td style={cell}>{money(o.filled_cost_dollars)}</td></tr>)}
                </tbody></table></div>
              )}
            </section>
            <section style={card}>
              <div style={eyebrow}>Angles trade history · confirmed fills</div>
              {!trades.length ? <p style={{ color: "#6e675f", fontSize: 13, margin: 0 }}>No confirmed trades yet.</p> : (
                <div style={{ overflowX: "auto" }}><table style={table}><thead><tr><th style={cell}>Date</th><th style={cell}>Market</th><th style={cell}>Side</th><th style={cell}>Contracts</th><th style={cell}>Price</th><th style={cell}>Fees</th><th style={cell}>Total cost</th></tr></thead><tbody>
                  {trades.map((t, i) => <tr key={`${t.fill_id}-${i}`} style={row}><td style={cell}>{new Date(t.created_at).toLocaleString()}</td><td style={cell}><Link href={`/baskets/${t.basket_id}`} style={{ color: "#216a4a" }}>{t.ticker}</Link></td><td style={cell}>{t.side}</td><td style={cell}>{t.contracts}</td><td style={cell}>{money(t.price_dollars)}</td><td style={cell}>{money(t.fee_dollars)}</td><td style={cell}>{money(t.cost_dollars)}</td></tr>)}
                </tbody></table></div>
              )}
            </section>
            <section style={card}>
              <div style={eyebrow}>Your watchlist</div>
              {!watchlist.length ? <p style={{ color: "#6e675f", fontSize: 13, margin: 0 }}>No baskets in your watchlist yet. <Link href="/baskets" style={{ color: "#216a4a" }}>Browse baskets</Link>.</p> : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>{watchlist.map(b => <BasketCard key={b.id} basket={b} />)}</div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function Metric({ label: name, value }: { label: string; value: string }) {
  return <div style={{ background: "#f8f6f2", borderRadius: 12, padding: 14 }}><div style={{ color: "#9b9390", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 7 }}>{name}</div><div style={{ color: "#1c1814", fontSize: 20, fontWeight: 700 }}>{value}</div></div>;
}

function PortfolioChart({ history }: { history: Portfolio["history"] }) {
  const valid = history.filter(p => p.current_value_dollars !== null);
  if (valid.length < 2) return <p style={{ color: "#6e675f", fontSize: 13 }}>Valuation data is not yet available for enough dates.</p>;
  const values = valid.map(p => p.current_value_dollars as number);
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const points = values.map((v, i) => `${40 + i * 540 / (values.length - 1)},${150 - (v - min) / range * 120}`).join(" ");
  return <div><svg role="img" aria-label="Portfolio marked value over time" viewBox="0 0 600 180" style={{ width: "100%", maxHeight: 240 }}><line x1="40" y1="150" x2="580" y2="150" stroke="#d6d3d1" /><polyline points={points} fill="none" stroke="#216a4a" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" /><text x="40" y="170" fill="#9b9390" fontSize="11">{valid[0].date}</text><text x="580" y="170" textAnchor="end" fill="#9b9390" fontSize="11">{valid[valid.length - 1].date}</text></svg><div style={{ color: "#6e675f", fontSize: 12 }}>Marked value: {money(values[0])} → {money(values[values.length - 1])}</div></div>;
}

const eyebrow: React.CSSProperties = { color: "#216a4a", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.16em", fontFamily: "var(--font-mono), monospace", marginBottom: 12 };
const card: React.CSSProperties = { background: "#fff", border: "1px solid rgba(0,0,0,0.08)", borderRadius: 20, padding: 22, boxShadow: "0 2px 12px rgba(0,0,0,0.05)", marginBottom: 18 };
const label: React.CSSProperties = { color: "#1c1814", fontSize: 13, fontWeight: 700, display: "grid", gap: 6 };
const input: React.CSSProperties = { border: "1px solid rgba(0,0,0,0.14)", borderRadius: 10, padding: "10px 12px", fontSize: 14, width: "100%", boxSizing: "border-box", color: "#1c1814", background: "#fff" };
const primaryButton: React.CSSProperties = { background: "#216a4a", color: "#fff", border: 0, borderRadius: 10, padding: "11px 16px", fontWeight: 700, cursor: "pointer" };
const secondaryButton: React.CSSProperties = { background: "#fff", color: "#b91c1c", border: "1px solid #fecaca", borderRadius: 10, padding: "9px 14px", fontWeight: 700, cursor: "pointer" };
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", textAlign: "left", color: "#1c1814", fontSize: 12 };
const cell: React.CSSProperties = { padding: "10px 12px 10px 0", whiteSpace: "nowrap" };
const row: React.CSSProperties = { borderTop: "1px solid rgba(0,0,0,0.07)" };
