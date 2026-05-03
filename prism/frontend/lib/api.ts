import type { StreamMessage, TradingChatResponse, TradingStreamMessage, BeliefSummary, TradingSession } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch(path: string, init?: RequestInit, token?: string) {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const searchEvents = (query = "", limit = 24, category = "") =>
  apiFetch(`/api/events?query=${encodeURIComponent(query)}&limit=${limit}${category ? `&category=${encodeURIComponent(category)}` : ""}`);

export const getMarkets = (eventTicker: string) =>
  apiFetch(`/api/events/${eventTicker}/markets`);

export const getMarket = (ticker: string) =>
  apiFetch(`/api/markets/${ticker}`);

export const listForecasts = (limit = 48, token?: string) =>
  apiFetch(`/api/forecasts?limit=${limit}`, undefined, token);

export function streamForecast(
  body: { ticker: string; event_title: string; ev_sub?: string; ev_category?: string; market?: Record<string, unknown> },
  onMessage: (msg: StreamMessage) => void,
  token?: string,
): () => void {
  let cancelled = false;

  (async () => {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/api/forecasts/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!res.body) return;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!cancelled) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (line) {
            try { onMessage(JSON.parse(line)); } catch {}
          }
        }
      }
    } catch (err) {
      if (!cancelled) {
        onMessage({ type: "error", message: err instanceof Error ? err.message : "Connection lost" });
      }
    }
  })();

  return () => { cancelled = true; };
}

export const listTradingSessions = (limit = 20, token?: string): Promise<TradingSession[]> =>
  apiFetch(`/api/trading/sessions?limit=${limit}`, undefined, token);

export async function tradingChat(
  history: Record<string, unknown>[],
  message: string,
  token?: string,
): Promise<TradingChatResponse> {
  return apiFetch("/api/trading/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, message }),
  }, token);
}

export function streamTradingAnalysis(
  beliefSummary: BeliefSummary,
  onMessage: (msg: TradingStreamMessage) => void,
  token?: string,
): () => void {
  let cancelled = false;

  (async () => {
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${BASE}/api/trading/analyze`, {
        method: "POST",
        headers,
        body: JSON.stringify({ belief_summary: beliefSummary }),
      });
      if (!res.body) return;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!cancelled) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (line) {
            try { onMessage(JSON.parse(line)); } catch {}
          }
        }
      }
    } catch (err) {
      if (!cancelled) {
        onMessage({ type: "error", message: err instanceof Error ? err.message : "Connection lost" });
      }
    }
  })();

  return () => { cancelled = true; };
}
