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
  event_title?: string;
  category?: string;
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
  epistemic_confidence?: "low" | "medium" | "high";
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
  belief_direction?: "happen" | "not_happen" | "increase" | "decrease" | "outperform" | "underperform";
  desired_exposure?: string;
  key_drivers: string[];
  scope: string;
  confidence_level: "low" | "medium" | "high";
  confidence_style?: "strong_directional" | "speculative" | "hedge" | "exploratory";
  supporting_reasoning: string;
  current_context: string;
  resolution_target?: string;
  resolution_type?: string;
  timeframe_start?: string;
  timeframe_end?: string;
  mechanism?: string[] | string;
  falsifiers?: string[];
  timeframe_inferred?: boolean;
  mode_used?: "instant" | "thinking";
}

export interface ExposureRoute {
  exposure_name: string;
  route_ring: "direct" | "strong_proxy" | "early_signal";
  tier: "direct_thesis" | "mechanism" | "first_order_consequence" | "hedge_or_falsifier";
  direction_if_belief_true: "YES" | "NO" | "UP" | "DOWN";
  causal_distance: "direct" | "precursor" | "first_order" | "second_order" | "speculative";
  causal_path: string;
  why_this_is_clean_or_useful: string;
  main_confounders: string[];
  timeframe_fit: "strong" | "partial" | "weak";
  search_terms: string[];
  negative_search_terms: string[];
  resolution_features: string[];
  causal_purity_score: number;
  expressiveness_score: number;
}

export interface RejectedRoute {
  route: string;
  reason: string;
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
  exposures?: ExposureRoute[];
  rejected_routes?: RejectedRoute[];
}

export interface RetrievedCandidate {
  event_ticker: string;
  ticker: string;
  question: string;
  event_title: string;
  category: string;
  close_date: string;
  route_ring?: "direct" | "strong_proxy" | "early_signal";
  yes_price: number | null;
  no_price: number | null;
  volume: number | null;
  retrieval_score: number;
  retrieval_reasons: string[];
}

export interface ScreenedMarket {
  ticker: string;
  event_ticker: string;
  question: string;
  linked_exposure_name: string;
  route_ring: "direct" | "strong_proxy" | "early_signal";
  tier: "direct_thesis" | "mechanism" | "first_order_consequence" | "hedge_or_falsifier";
  recommended_side: "YES" | "NO";
  alignment: "YES" | "NO";
  expressiveness_score: number;
  resolution_fit_score: number;
  causal_purity_score: number;
  timeframe_alignment_score: number;
  liquidity_usability_score: number;
  overall_score: number;
  fit_type: "direct_thesis" | "strong_proxy" | "good_proxy" | "partial_proxy" | "early_signal" | "hedge";
  fit_confidence: "high" | "medium" | "low";
  fit_warning: string | null;
  proxy_reason: string | null;
  rationale: string;
  main_confounder: string;
}

export interface CoverageSummary {
  direct_count: number;
  strong_proxy_count: number;
  partial_proxy_count: number;
  early_signal_count: number;
  hedge_count: number;
  overall_coverage_quality: "direct" | "strong_proxy" | "mixed_proxy" | "thin_market_coverage";
}

export interface BasketCritiqueIssue {
  severity: "low" | "medium" | "high";
  holding_ticker: string | null;
  issue: string;
  suggested_fix: string;
}

export interface BasketCritique {
  verdict: "pass" | "needs_repair" | "fail";
  issues: BasketCritiqueIssue[];
  suggested_removals: string[];
  suggested_replacements: { remove_ticker: string; add_ticker: string; reason: string }[];
  final_notes: string;
}

export interface BasketHolding {
  ticker: string;
  event_ticker: string;
  question: string;
  market_price: number;
  close_date: string;
  side: "YES" | "NO";
  role?: "direct" | "mechanism" | "indirect" | "hedge";
  weight_dollars: number;
  topic_bucket?: string;
  bucket_thesis?: string | null;
  linked_exposure_name?: string;
  route_ring?: "direct" | "strong_proxy" | "early_signal";
  fit_type?: "direct_thesis" | "strong_proxy" | "good_proxy" | "partial_proxy" | "early_signal" | "hedge";
  fit_confidence?: "high" | "medium" | "low";
  fit_warning?: string | null;
  proxy_reason?: string | null;
  rationale: string;
  main_risk: string;
  tier?: "direct_thesis" | "mechanism" | "first_order_consequence" | "hedge_or_falsifier";
  rules_summary?: string;
  event_title?: string;
  series_ticker?: string;
  category?: string;
}

export interface PredictionBasket {
  basket_title: string;
  basket_summary: string;
  construction_notes: string;
  basket_quality?: "direct" | "strong_proxy" | "mixed_proxy" | "thin_market_coverage";
  basket_quality_explanation?: string;
  basket_buckets?: {
    name: string;
    description: string;
  }[];
  exposure_allocations?: {
    bucket: "direct_thesis" | "mechanism" | "first_order_consequence" | "hedge_or_falsifier";
    weight_dollars: number;
    reason: string;
  }[];
  holdings: BasketHolding[];
  total_notional: number;
}

export interface BasketPerformance {
  dates: string[];
  values: number[];
  current_return: number | null;
}

export interface TradingChatResponse {
  status: "asking" | "finalized";
  agent_message: string | null;
  search_queries: string[];
  belief_summary: BeliefSummary | null;
  history: Record<string, unknown>[];
}

export interface SavedBasket {
  id: number;
  created_at: string;
  title: string;
  summary: string;
  core_belief: string;
  mode: "instant" | "thinking" | "manual";
  time_horizon: string;
  timeframe_start: string;
  timeframe_end: string;
  resolution_target: string;
  mechanism: string;
  scope: string;
  key_drivers_json: string;
  belief_summary_json: string;
  analysis_json: string;
  basket_json: string;
  total_notional: number;
  screened_count: number;
  is_public: boolean;
  user_id?: string;
  username?: string;
  holdings?: BasketHolding[];
}

export interface UserProfile {
  user_id: string;
  username: string;
  created_at: string;
}

export interface ManualBasketDraftHolding {
  ticker: string;
  event_ticker: string;
  event_title?: string;
  question: string;
  market_price: number;
  close_date: string;
  side: "YES" | "NO";
  contract_label?: string;
  weight_percent: number;
  rationale: string;
  main_risk: string;
  rules_summary?: string;
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
  | { type: "screener_done"; tickers: string[]; count: number; selected_markets?: ScreenedMarket[]; coverage_summary?: CoverageSummary }
  | { type: "critic_done"; critique: BasketCritique }
  | { type: "basket_done"; basket: PredictionBasket; basket_id?: number }
  | { type: "error"; message: string };
