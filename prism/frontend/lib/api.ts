import type {
  StreamMessage,
  TradingChatResponse,
  TradingStreamMessage,
  BeliefSummary,
  SavedBasket,
  UserProfile,
  ManualBasketDraftHolding,
  OracleTurnResponse,
  OraclePipelineMessage,
  KalshiEvent,
  KalshiMarket,
  BasketPerformance,
} from "./types";

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

export const searchEvents = (query = "", limit = 24, category = ""): Promise<KalshiEvent[]> =>
  apiFetch(`/api/events?query=${encodeURIComponent(query)}&limit=${limit}${category ? `&category=${encodeURIComponent(category)}` : ""}`);

export const listEventCategories = (): Promise<string[]> =>
  apiFetch("/api/events/categories");

export const getMarkets = (eventTicker: string): Promise<KalshiMarket[]> =>
  apiFetch(`/api/events/${eventTicker}/markets`);

export const getMarket = (ticker: string): Promise<KalshiMarket> =>
  apiFetch(`/api/markets/${ticker}`);

export const listForecasts = (limit = 48, token?: string) =>
  apiFetch(`/api/forecasts?limit=${limit}`, undefined, token);

export function streamForecast(
  body: {
    ticker: string;
    event_title: string;
    ev_sub?: string;
    ev_category?: string;
    market?: Record<string, unknown>;
    related_markets?: Record<string, unknown>[];
  },
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

export const listBaskets = (limit = 20, token?: string): Promise<SavedBasket[]> =>
  apiFetch(`/api/baskets?limit=${limit}`, undefined, token);

export const listPublicBaskets = (limit = 48): Promise<SavedBasket[]> =>
  apiFetch(`/api/baskets/public?limit=${limit}`);

export const getBasket = (basketId: number, token?: string): Promise<SavedBasket> =>
  apiFetch(`/api/baskets/${basketId}`, undefined, token);

export const getBasketPerformance = (basketId: number, token?: string): Promise<BasketPerformance> =>
  apiFetch(`/api/baskets/${basketId}/performance`, undefined, token);

export async function saveManualBasket(
  body: {
    title: string;
    summary: string;
    timeframe?: string;
    holdings: (ManualBasketDraftHolding & { weight_dollars: number; role: "direct" | "mechanism" | "indirect" | "hedge" })[];
    is_public?: boolean;
  },
  token?: string,
): Promise<{ basket_id: number; basket: SavedBasket }> {
  return apiFetch("/api/baskets/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, token);
}

export async function tradingChat(
  history: Record<string, unknown>[],
  message: string,
  mode: "instant" | "thinking",
  token?: string,
): Promise<TradingChatResponse> {
  return apiFetch("/api/trading/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, message, mode }),
  }, token);
}

export function streamTradingAnalysis(
  beliefSummary: BeliefSummary,
  mode: "instant" | "thinking",
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
        body: JSON.stringify({ belief_summary: beliefSummary, mode }),
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

export const setBasketVisibility = (basketId: number, isPublic: boolean, token: string): Promise<{ ok: boolean }> =>
  apiFetch(`/api/baskets/${basketId}/visibility`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_public: isPublic }),
  }, token);

// ── Profile endpoints ─────────────────────────────────────────────────────────

export const getMyProfile = (token: string): Promise<UserProfile> =>
  apiFetch("/api/profiles/me", undefined, token);

export const createProfile = (username: string, token: string): Promise<UserProfile> =>
  apiFetch("/api/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  }, token);

export const getUserPage = (username: string): Promise<{ profile: UserProfile; baskets: SavedBasket[] }> =>
  apiFetch(`/api/users/${username}`);

// ── Legacy Oracle endpoints ───────────────────────────────────────────────────

export async function oracleTurn(
  history: unknown[],
  message: string,
): Promise<OracleTurnResponse> {
  return apiFetch("/api/oracle/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, message }),
  });
}

export function streamOraclePipeline(
  beliefSummary: Record<string, unknown>,
  onMessage: (msg: OraclePipelineMessage) => void,
): () => void {
  let cancelled = false;
  (async () => {
    try {
      const res = await fetch(`${BASE}/api/oracle/pipeline/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
