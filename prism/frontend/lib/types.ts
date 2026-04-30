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

export type StreamMessage =
  | { type: "progress"; label: string }
  | { type: "complete"; memo: ForecastMemo; kalshi_price: number; close_date: string }
  | { type: "error"; message: string };
