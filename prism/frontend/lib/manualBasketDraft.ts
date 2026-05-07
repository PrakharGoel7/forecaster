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

export function addMarketToManualBasketDraft(market: KalshiMarket) {
  const holdings = loadManualBasketDraft();
  if (holdings.some((holding) => holding.ticker === market.ticker)) return false;
  holdings.push({
    ticker: market.ticker,
    event_ticker: market.event_ticker,
    question: market.question,
    market_price: market.mid_price,
    close_date: market.close_date,
    side: "YES",
    role: "direct",
    weight_dollars: 10,
    rationale: "",
    main_risk: "",
    rules_summary: market.rules_primary,
  });
  saveManualBasketDraft(holdings);
  return true;
}
