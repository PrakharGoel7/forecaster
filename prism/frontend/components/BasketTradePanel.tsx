"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { executeBasketTrade, getKalshiCredentials, previewBasketTrade } from "@/lib/api";
import type { TradeExecution, TradePreview } from "@/lib/types";
import styles from "./BasketTradePanel.module.css";

const money = (value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "The request failed. Please try again.";
  try {
    const parsed = JSON.parse(error.message);
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch { /* use raw error */ }
  return error.message;
}

export function BasketTradePanel({ basketId, token, onExecution, onSignIn }: { basketId: number; token: string | null; onExecution?: () => void; onSignIn: () => void }) {
  const [amount, setAmount] = useState("100");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<TradePreview | null>(null);
  const [execution, setExecution] = useState<TradeExecution | null>(null);
  const [busy, setBusy] = useState<"preview" | "execute" | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) { Promise.resolve().then(() => setConnected(null)); return; }
    let active = true;
    getKalshiCredentials(token)
      .then((status) => { if (active) setConnected(status.connected); })
      .catch(() => { if (active) { setConnected(null); setError("Could not check your Kalshi connection. Refresh and try again."); } });
    return () => { active = false; };
  }, [token]);

  async function requestPreview() {
    if (!token || busy) return;
    const dollars = Number(amount);
    if (!Number.isFinite(dollars) || dollars <= 0) {
      setError("Enter a dollar amount greater than zero.");
      return;
    }
    setBusy("preview");
    setError("");
    setExecution(null);
    setPreview(null);
    try {
      setPreview(await previewBasketTrade(basketId, dollars, token));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function execute() {
    if (!token || !preview || busy) return;
    if (Date.parse(preview.expires_at) <= Date.now()) {
      setPreview(null);
      setError("This quote expired. Preview the basket again before placing orders.");
      return;
    }
    setBusy("execute");
    setError("");
    try {
      const result = await executeBasketTrade(basketId, preview.preview_id, token);
      setExecution(result);
      setPreview(null);
      onExecution?.();
    } catch (err) {
      setError(errorMessage(err));
      setPreview(null);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className={styles.tradeCard}>
      <div className={styles.tradeEyebrow}>Trade this thesis</div>
      <h2 className={styles.tradeHeading}>Invest in this basket</h2>
      {!token ? (
        <div className={styles.tradeAction}>
          <button type="button" onClick={onSignIn} className={styles.primaryAction}>Sign in to invest <span aria-hidden="true">→</span></button>
        </div>
      ) : connected === false ? (
        <div className={styles.tradeAction}>
          <p className={styles.tradeHint}>Connect Kalshi to preview and place orders.</p>
          <Link href="/account" className={styles.primaryAction}>Connect Kalshi <span aria-hidden="true">→</span></Link>
        </div>
      ) : connected === null ? (
        <div className={styles.tradeAction}>
          <p className={styles.tradeHint}>{error ? "Check your connection in Account settings." : "Checking your Kalshi connection…"}</p>
          {error && <Link href="/account" className={styles.primaryAction}>Account settings <span aria-hidden="true">→</span></Link>}
        </div>
      ) : (
        <form className={styles.tradeAction} onSubmit={(event) => { event.preventDefault(); requestPreview(); }}>
          <label htmlFor="basket-invest-amount" className={styles.amountLabel}>Investment amount</label>
          <div className={styles.amountField}>
            <span aria-hidden="true">$</span>
            <input id="basket-invest-amount" type="number" inputMode="decimal" min="1" step="0.01" value={amount}
              onChange={(event) => { setAmount(event.target.value); setPreview(null); setExecution(null); }} />
          </div>
          <button type="submit" disabled={busy !== null} className={styles.primaryAction}>
            {busy === "preview" ? "Getting live quote…" : "Preview investment →"}
          </button>
        </form>
      )}
      {error && <div role="alert" style={{ marginTop: 12, color: "#b91c1c", fontSize: 13 }}>{error}</div>}
      {preview && (
        <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid rgba(0,0,0,0.08)" }}>
          <div style={{ color: "#1c1814", fontWeight: 700, marginBottom: 4 }}>Review before placing orders</div>
          <div style={{ color: "#6e675f", fontSize: 12, marginBottom: 12 }}>
            Requested {money(preview.amount_dollars)} · Estimated contract cost before fees {money(preview.estimated_max_cost_dollars)} · Quote expires {new Date(preview.expires_at).toLocaleTimeString()}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
              <thead><tr style={{ color: "#9b9390" }}><th style={cell}>Market</th><th style={cell}>Position</th><th style={cell}>Contracts</th><th style={cell}>Kalshi YES limit</th><th style={cell}>Est. cost</th></tr></thead>
              <tbody>{preview.lines.map((line, i) => (
                <tr key={`${line.ticker}-${i}`} style={{ borderTop: "1px solid rgba(0,0,0,0.06)" }}>
                  <td style={cell}>{line.ticker}<div style={{ color: "#9b9390" }}>{line.weight_percent.toFixed(1)}% target</div></td>
                  <td style={cell}>{line.side}</td><td style={cell}>{line.count}</td><td style={cell}>{money(Number(line.limit_price_dollars))}</td><td style={cell}>{money(line.estimated_cost_dollars)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p style={{ color: "#6e675f", fontSize: 12, lineHeight: 1.5 }}>Kalshi expresses NO positions as a sell YES order, so the limit column shows the YES price for both sides. Actual fills and fees may differ. Some markets may remain unfilled. Your invested total updates only after fills are confirmed.</p>
          <button onClick={execute} disabled={busy !== null} style={{ padding: "12px 18px", border: 0, borderRadius: 10, background: "#15803d", color: "#fff", fontWeight: 700, cursor: "pointer", opacity: busy ? 0.6 : 1 }}>
            {busy === "execute" ? "Submitting orders…" : "Confirm and place Kalshi orders"}
          </button>
        </div>
      )}
      {execution && (
        <div role="status" style={{ marginTop: 18, padding: 16, background: execution.status === "filled" ? "#f0fdf4" : "#fffbeb", borderRadius: 12, fontSize: 13 }}>
          <strong style={{ display: "block", marginBottom: 5 }}>Order status: {execution.status.replaceAll("_", " ")}</strong>
          <span style={{ color: "#6e675f" }}>Investment #{execution.investment_id}. {execution.status === "pending_reconciliation" ? "Kalshi has not confirmed the outcome yet. Check your trade history before trying again." : "See your portfolio for confirmed fills and position values."}</span>
          <div style={{ marginTop: 8 }}><Link href="/account" style={{ color: "#216a4a" }}>View portfolio and trades →</Link></div>
          {execution.orders.map((order, i) => <div key={`${order.client_order_id}-${i}`} style={{ marginTop: 6, color: "#6e675f" }}>{order.ticker}: {order.status} · {order.filled_contracts} filled · {money(order.filled_cost_dollars)}{order.error ? ` · ${order.error}` : ""}</div>)}
        </div>
      )}
    </section>
  );
}

const cell: React.CSSProperties = { padding: "8px 10px 8px 0", verticalAlign: "top" };
