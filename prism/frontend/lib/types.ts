export interface KalshiEvent {
  event_ticker: string;
  series_ticker: string;
  title: string;
  sub_title: string;
  category: string;
}

export interface KalshiMarket {
  ticker: string;
  event_ticker: string;
  yes_sub_title: string;
  no_sub_title: string;
  yes_bid: number;
  yes_ask: number;
  last_price: number;
  volume: number;
  rules_primary: string;
  rules_secondary: string;
  close_time: string;
  close_date: string;
  mid_price: number;
  question: string;
  status: string;
}

export interface EvidenceItem {
  direction: string;
  claim: string;
  source_title: string;
  source_url: string;
  relevant_quote_or_snippet?: string;
}

export interface AgentForecast {
  probability: number;
  outside_view_base_rate: number;
  key_factors_for: string[];
  key_factors_against: string[];
  evidence_ledger: { items: EvidenceItem[] };
}

export interface ForecastMemo {
  final_probability: number;
  num_agents: number;
  outside_view_summary: string;
  supervisor_reconciliation: { reconciliation_reasoning: string };
  agent_forecasts: AgentForecast[];
}

export interface SavedForecast {
  id: number;
  created_at: string;
  ticker: string;
  event_title: string;
  question: string;
  close_date: string;
  category: string;
  kalshi_price: number;
  forecaster_prob: number;
  edge: number;
  context_json: string;
  memo_json: string;
}

export interface OVData {
  base_rate: number;
  reference_class: string;
  reasoning: string;
}

export interface IVData {
  key_factors_for: string[];
  key_factors_against: string[];
}

export type StreamMessage =
  | { type: "progress"; label: string }
  | { type: "ov_complete"; base_rate: number; reference_class: string; reasoning: string }
  | { type: "iv_complete"; agent_forecasts: { key_factors_for: string[]; key_factors_against: string[] }[] }
  | { type: "complete"; memo: ForecastMemo; kalshi_price: number; close_date: string }
  | { type: "error"; message: string };

// ── Trading Companion ─────────────────────────────────────────────────────────

export interface BeliefSummary {
  core_belief: string;
  time_horizon: string;
  key_drivers: string[];
  scope: string;
  confidence_level: "low" | "medium" | "high";
  supporting_reasoning: string;
  current_context: string;
}

export interface DomainAnalysis {
  domain: string;
  relevance: "high" | "medium" | "low";
  mechanism: string;
  market_signals: string[];
}

export interface BeliefAnalysis {
  affected_domains: DomainAnalysis[];
  most_surprising_connection: string;
}

export interface TradeRecommendation {
  ticker: string;
  event_ticker: string;
  question: string;
  price: number;
  close_date: string;
  rules_summary: string;
  relevance: string;
  direction: "YES" | "NO";
  rationale: string;
  score: number;
  event_title?: string;
  series_ticker?: string;
  category?: string;
}

export interface TradingChatResponse {
  status: "asking" | "finalized";
  agent_message: string | null;
  search_queries: string[];
  belief_summary: BeliefSummary | null;
  history: Record<string, unknown>[];
}

export interface TradingSession {
  id: number;
  created_at: string;
  core_belief: string;
  time_horizon: string;
  scope: string;
  key_drivers_json: string;
  belief_summary_json: string;
  analysis_json: string;
  recommendations_json: string;
}

// ── Oracle (legacy) ───────────────────────────────────────────────────────────

export type OracleStageStatus = "waiting" | "running" | "done";

export type OraclePipelineMessage =
  | { type: "stage"; stage: string; status: OracleStageStatus; data?: { domains: OracleDomain[]; insight: string } }
  | { type: "complete"; data: { recommendations: OracleRecommendation[]; analysis: { domains: OracleDomain[]; insight: string } } }
  | { type: "error"; message: string };

export interface OracleTurnResponse {
  status: "asking" | "finalized";
  agent_message: string | null;
  search_queries: string[];
  belief_summary: Record<string, unknown> | null;
  history: Record<string, unknown>[];
}

export interface OracleChatMessage {
  role: "user" | "oracle";
  content: string;
  searchQueries?: string[];
}

export interface OracleDomain {
  domain: string;
  relevance: "high" | "medium" | "low";
  mechanism: string;
}

export interface OracleRecommendation {
  ticker: string;
  event_ticker: string;
  question: string;
  price: number;
  close_date: string;
  direction: "YES" | "NO";
  rationale: string;
  score: number;
}

export type TradingStreamMessage =
  | { type: "progress"; label: string }
  | { type: "analyst_done"; analysis: BeliefAnalysis }
  | { type: "screener_done"; tickers: string[]; count: number }
  | { type: "curator_done"; recommendations: TradeRecommendation[]; session_id?: number }
  | { type: "error"; message: string };
