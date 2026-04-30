import type { StreamMessage } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const searchEvents = (query = "", limit = 24) =>
  apiFetch(`/api/events?query=${encodeURIComponent(query)}&limit=${limit}`);

export const getMarkets = (eventTicker: string) =>
  apiFetch(`/api/events/${eventTicker}/markets`);

export const getMarket = (ticker: string) =>
  apiFetch(`/api/markets/${ticker}`);

export const listForecasts = (limit = 48) =>
  apiFetch(`/api/forecasts?limit=${limit}`);

export function streamForecast(
  body: { ticker: string; event_title: string; ev_sub?: string; ev_category?: string; market?: Record<string, unknown> },
  onMessage: (msg: StreamMessage) => void
): () => void {
  let cancelled = false;

  (async () => {
    try {
      const res = await fetch(`${BASE}/api/forecasts/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
