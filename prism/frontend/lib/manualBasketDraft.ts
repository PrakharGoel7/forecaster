"use client";

import type { KalshiMarket, ManualBasketDraftHolding } from "./types";

const STORAGE_KEY = "prism.manualBasketDraft";
const EVENT_NAME = "prism-manual-basket-updated";

function emitUpdate() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

export function manualBasketDraftEventName() {
  return EVENT_NAME;
}

export function loadManualBasketDraft(): ManualBasketDraftHolding[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.map((holding) => ({
        ...holding,
        contract_label: holding.contract_label ?? (holding.side === "NO" ? "No" : "Yes"),
        weight_percent: holding.weight_percent ?? holding.weight_dollars ?? 10,
      }))
      : [];
  } catch {
    return [];
  }
}

export function saveManualBasketDraft(holdings: ManualBasketDraftHolding[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(holdings));
  emitUpdate();
}

export function clearManualBasketDraft() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  emitUpdate();
}

export function addMarketToManualBasketDraft(
  market: KalshiMarket,
  options?: {
    side?: "YES" | "NO";
    question?: string;
    marketPrice?: number;
    contractLabel?: string;
  },
) {
  const holdings = loadManualBasketDraft();
  const side = options?.side ?? "YES";
  const question = options?.question ?? market.question;
  const marketPrice = options?.marketPrice ?? (side === "NO" ? 1 - market.mid_price : market.mid_price);
  const contractLabel = options?.contractLabel ?? (side === "NO" ? "No" : market.yes_sub_title || "Yes");
  const existingIndex = holdings.findIndex((holding) => holding.ticker === market.ticker);

  if (existingIndex >= 0) {
    holdings[existingIndex] = {
      ...holdings[existingIndex],
      question,
      market_price: marketPrice,
      side,
      contract_label: contractLabel,
      rules_summary: market.rules_primary,
      close_date: market.close_date,
    };
    saveManualBasketDraft(holdings);
    return "updated";
  }

  holdings.push({
    ticker: market.ticker,
    event_ticker: market.event_ticker,
    question,
    market_price: marketPrice,
    close_date: market.close_date,
    side,
    contract_label: contractLabel,
    weight_percent: 10,
    rationale: "",
    main_risk: "",
    rules_summary: market.rules_primary,
  });
  saveManualBasketDraft(holdings);
  return "added";
}
