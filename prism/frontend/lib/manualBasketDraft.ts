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
    return Array.isArray(parsed) ? parsed : [];
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
  },
) {
  const holdings = loadManualBasketDraft();
  const side = options?.side ?? "YES";
  const question = options?.question ?? market.question;
  const marketPrice = options?.marketPrice ?? (side === "NO" ? 1 - market.mid_price : market.mid_price);
  const existingIndex = holdings.findIndex((holding) => holding.ticker === market.ticker);

  if (existingIndex >= 0) {
    holdings[existingIndex] = {
      ...holdings[existingIndex],
      question,
      market_price: marketPrice,
      side,
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
    role: "direct",
    weight_dollars: 10,
    rationale: "",
    main_risk: "",
    rules_summary: market.rules_primary,
  });
  saveManualBasketDraft(holdings);
  return "added";
}
