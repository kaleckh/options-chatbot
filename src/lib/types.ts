export interface Prediction {
  id?: number;
  ticker: string;
  direction: "call" | "put";
  direction_score: number;
  tech_score: number;
  quality_score: number;
  stock_price: number;
  strike_est: number;
  est_premium: number;
  delta_est: number;
  dte: number;
  iv_rank: number;
  ev_pct: number;
  entry_date: string;
  target_date: string;
  expiry?: string;
  outcome?: "hit" | "directional" | "miss" | null;
  type?: "daily_scan" | "manual";
  asset_class?: "equity" | "index";
  stop_loss_pct?: number;
  profit_target_pct?: number;
  option_gain_pct?: number;
  current_stock_pct?: number;
  current_option_px?: number;
  live_premium?: number;
  strategy_label?: string;
  strategy_comment?: string;
  rsi14?: number;
  spy_ret5?: number;
  pick_status?: string;
  roll_count?: number;
  last_rolled_date?: string;
  entry_open_price?: number;
  entry_at_open?: boolean;
  daily_option_pnl?: { date: string; pnl_pct: number }[];
}

export interface ScanPick {
  ticker: string;
  type: "call" | "put";
  prediction_type?: string;
  direction: "call" | "put";
  strategy_type?: string | null;
  contract_symbol?: string | null;
  short_contract_symbol?: string | null;
  direction_score: number;
  quality_score: number;
  tech_score?: number;
  ev: number;
  dte: number;
  delta?: number | null;
  iv_percentile?: number | null;
  iv_pct?: number | null;
  target_move_pct?: number | null;
  stock_price?: number;
  strike?: number;
  strike_est?: number;
  short_strike?: number | null;
  premium?: number;
  est_premium?: number;
  bid?: number | null;
  ask?: number | null;
  last?: number | null;
  mid?: number | null;
  expiry?: string;
  asset_class?: "equity" | "index";
  sector?: string | null;
  market_regime?: "bullish" | "neutral" | "bearish" | "unknown" | string;
  stop_loss_pct?: number;
  profit_target_pct?: number;
  time_exit_day?: number;
  strategy_label?: string;
  strategy_comment?: string;
  policy_decision?: "approved" | "watch" | "blocked" | null;
  policy_fit_score?: number | null;
  policy_fit_reasons?: string[];
  playbook?: "short_term" | "swing" | string;
  playbook_label?: string | null;
  guardrail_decision?: "clear" | "caution" | "blocked" | null;
  guardrail_reasons?: string[];
  suggested_size_tier?: "starter" | "half" | "full" | "blocked" | string | null;
  suggested_size_reason?: string | null;
  risk_tier?: 1 | 2 | 3 | 4 | 5 | number | null;
  upside_tier?: 1 | 2 | 3 | 4 | 5 | number | null;
  speculative_flag?: boolean;
  speculative_reason?: string[];
  convexity_class?: "core" | "aggressive" | "speculative" | string | null;
  historical_data_ready?: boolean | null;
  historical_data_source?: string | null;
  historical_data_readiness_status?: string | null;
  ai_commodity_bucket?: "core_options" | "conditional_options" | string | null;
  quote_time_et?: string | null;
  quote_time_utc?: string | null;
  quote_basis?: string | null;
  quote_freshness_status?: string | null;
  original_logged_expiry?: string | null;
  resolved_listed_expiry?: string | null;
  underlying_price_at_selection?: number | null;
  selection_source?: string | null;
  promotion_class?: string | null;
  approximation_only?: boolean | null;
  comparable_contract?: boolean | null;
  comparable_contract_basis?: string | null;
  comparable_contract_label?: string | null;
  resolution_notes?: string | null;
  original_logged_entry_execution_price?: number | null;
  resolved_reference_entry_execution_price?: number | null;
  promotable?: boolean;
  options_snapshot_status?: string | null;
  option_chain_status?: string | null;
  managed_eligible?: boolean;
  managed_block_reason?: string | null;
  entry_execution_price?: number | null;
  entry_execution_basis?: string | null;
  entry_fee_total_usd?: number | null;
  profitability_eligibility?: string | null;
  profitability_blockers?: string[];
  candidate_rank?: number | null;
  profit_candidate_id?: string | null;
  policy_artifact_id?: string | null;
  cohort_id?: string | null;
  cohort_role?: string | null;
  entry_quote_snapshot?: EntryQuoteSnapshot | null;
}

export interface EntryQuoteLeg {
  role?: string | null;
  contract_symbol?: string | null;
  strike?: number | null;
  premium?: number | null;
  bid?: number | null;
  ask?: number | null;
  last?: number | null;
  mid?: number | null;
  delta?: number | null;
  iv?: number | null;
  quote_basis?: string | null;
  quote_age_hours?: number | null;
  volume?: number | null;
  open_interest?: number | null;
}

export interface EntryQuoteSnapshot {
  captured_at_et?: string | null;
  captured_at_utc?: string | null;
  ticker?: string | null;
  direction?: string | null;
  strategy_type?: string | null;
  logged_expiry?: string | null;
  resolved_listed_expiry?: string | null;
  selection_source?: string | null;
  promotion_class?: string | null;
  underlying_price?: number | null;
  quote_basis?: string | null;
  quote_freshness_status?: string | null;
  options_snapshot_status?: string | null;
  option_chain_status?: string | null;
  entry_execution_price?: number | null;
  entry_execution_basis?: string | null;
  entry_fee_total_usd?: number | null;
  display_price?: number | null;
  spread_width?: number | null;
  net_debit?: number | null;
  max_profit?: number | null;
  max_loss?: number | null;
  net_delta?: number | null;
  legs?: EntryQuoteLeg[];
}

export type TruthLane = "synthetic" | "historical_imported" | "historical_imported_daily";
export type BacktestPricingLane = "pessimistic" | "mid";

export interface ExperimentSliceSummary {
  label: string;
  trades: number;
  profit_factor: number;
  avg_pnl_pct: number;
  directional_accuracy_pct: number;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
}

export interface LiveTradePolicy {
  generated_at: string;
  source?: {
    run_at?: string | null;
    lookback_years?: number | null;
    pricing_lane?: string | null;
    playbook?: string | null;
    truth_source?: string | null;
    priced_trade_count?: number | null;
    unpriced_trade_count?: number | null;
    quote_coverage_pct?: number | null;
    entry_quote_time_et?: string | null;
    exit_quote_time_et?: string | null;
    total_trades?: number | null;
  } & Record<string, unknown>;
  source_run_at?: string | null;
  lookback_years?: number | null;
  pricing_lane?: string | null;
  playbook?: string | null;
  promotion_status?: string | null;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
  strategy_domain: string;
  trade_types: string[];
  overall: {
    trades: number;
    profit_factor: number;
    avg_pnl_pct: number;
    directional_accuracy_pct: number;
  } & Record<string, unknown>;
  scan_policy: {
    mode: string;
    promotion_status?: string | null;
    decision_labels: {
      approved: string;
      watch: string;
      blocked: string;
    };
    hard_filters: {
      direction_score_min?: number | null;
      direction_score_max?: number | null;
    };
    preferred_filters: {
      asset_class?: string | null;
      market_regimes: string[];
      sectors: string[];
    };
    highlighted_tickers: string[];
    rationale: string[];
    warnings: string[];
    supporting_slices: {
      score_band?: ExperimentSliceSummary | null;
      asset_regime?: ExperimentSliceSummary | null;
      sectors: ExperimentSliceSummary[];
      tickers: ExperimentSliceSummary[];
    };
  };
}

export interface ScanPlaybook {
  id: "short_term" | "swing" | "speculative" | string;
  label: string;
  description: string;
  target_dte: number;
  max_new_positions_per_day: number;
  max_sector_open_positions: number;
  max_regime_open_positions: number;
  block_same_ticker: boolean;
  max_concurrent_positions?: number;
  max_correlated_index_positions?: number;
  daily_loss_limit_pct?: number;
  weekly_loss_limit_pct?: number;
  allowed_tickers?: string[];
  scan_tickers?: string[];
  core_tickers?: string[];
  conditional_tickers?: string[];
  historical_data_ready_tickers?: string[];
  historical_core_ready_tickers?: string[];
  historical_conditional_ready_tickers?: string[];
  historical_missing_tickers?: string[];
  historical_data_readiness_status?: string;
  historical_core_ready_count?: number;
  historical_core_required_count?: number;
  historical_scan_ready_count?: number;
  historical_scan_required_count?: number;
  allowed_directions?: string[];
  allowed_strategy_types?: string[];
  theme_tags?: string[];
}

export interface ExposureSnapshot {
  available?: boolean;
  open_positions: number;
  opened_today: number;
  ticker_counts: Record<string, number>;
  sector_counts: Record<string, number>;
  regime_counts: Record<string, number>;
  sector_direction_counts?: Record<string, number>;
  vertical_spread_signature_counts?: Record<string, number>;
  open_cost_risk_usd?: number;
  warnings: string[];
}

export interface PlaybookExitAuditBucket {
  label: string;
  trades: number;
  avg_pnl_pct: number;
  profit_factor: number;
  directional_accuracy_pct: number;
  exit_reasons: Array<Record<string, unknown>>;
}

export interface PlaybookExitAudit {
  generated_at: string;
  source_run_at?: string | null;
  lookback_years?: number | null;
  pricing_lane?: string | null;
  playbook: string;
  promotion_status?: string | null;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
  overall_playbook_trades: number;
  approved: PlaybookExitAuditBucket;
  watch: PlaybookExitAuditBucket;
  blocked: PlaybookExitAuditBucket;
}

export interface TruthMetadata {
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
}

export interface TruthLaneSummary extends TruthMetadata {
  run_at?: string | null;
  lookback_years?: number | null;
  pricing_lane?: string | null;
  playbook?: string | null;
  promotion_status?: string | null;
  total_trades?: number | null;
  total_days?: number | null;
  profit_factor?: number | null;
  avg_pnl_pct?: number | null;
  win_rate_pct?: number | null;
  directional_accuracy_pct?: number | null;
  trades?: number | null;
  [key: string]: unknown;
}

export interface TruthLaneComparisonDeltas {
  total_trades: number;
  profit_factor: number;
  avg_pnl_pct: number;
  directional_accuracy_pct: number;
  quote_coverage_pct: number;
}

export interface TruthLaneComparisonReport {
  generated_at?: string | null;
  synthetic?: TruthLaneSummary | null;
  imported?: TruthLaneSummary | null;
  deltas?: TruthLaneComparisonDeltas | null;
  matching_priced_trade_count?: number | null;
  unsupported_by_import_count?: number | null;
  unsupported_by_import?: Record<string, unknown>[];
  notes?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

export interface OptionsProfitGateBlocker {
  code: string;
  severity?: string | null;
  message?: string | null;
  [key: string]: unknown;
}

export interface OptionsProfitSideEntry {
  symbol?: string | null;
  direction?: "call" | "put" | string | null;
  candidate_id?: string | null;
  cohort_id?: string | null;
  base_profile?: string | null;
  overrides?: Record<string, unknown> | null;
  source?: string | null;
  mode?: string | null;
  status?: string | null;
  applied_at?: string | null;
  [key: string]: unknown;
}

export interface OptionsProfitCurrentCanary {
  symbol?: string | null;
  direction?: "call" | "put" | string | null;
  candidate_id?: string | null;
  started_at?: string | null;
  required_outcomes?: number | null;
  [key: string]: unknown;
}

export interface OptionsProfitCandidateRanking {
  candidate_id?: string | null;
  symbol?: string | null;
  direction?: "call" | "put" | string | null;
  eligible?: boolean;
  blockers?: string[];
  delta_vs_incumbent?: number | null;
  [key: string]: unknown;
}

export interface OptionsProfitStatus {
  generated_at?: string | null;
  daily_truth_refresh?: {
    status?: string | null;
    stage?: string | null;
    error?: string | null;
    manifest_path?: string | null;
    manifest_source?: string | null;
    artifact_refresh?: Record<string, unknown> | null;
    import_summary?: Record<string, unknown> | null;
    [key: string]: unknown;
  } | null;
  measurement_gate: {
    state?: string | null;
    blockers?: OptionsProfitGateBlocker[];
    warnings?: string[];
    checks?: {
      imported_daily_artifact?: {
        path?: string | null;
        present?: boolean;
        matches_store?: boolean;
        quote_coverage_pct?: number | null;
        required_quote_coverage_pct?: number | null;
        [key: string]: unknown;
      } | null;
      forward_evidence?: {
        db_path?: string | null;
        eligible_event_count?: number | null;
        pending_truth_event_count?: number | null;
        trusted_truth_horizon?: string | null;
        truth_staleness_business_days?: number | null;
        by_symbol?: Record<string, { eligible?: number; pending_truth?: number; ineligible?: number }>;
        contamination_finding_count?: number | null;
        stale_metadata_finding_count?: number | null;
        [key: string]: unknown;
      } | null;
      tracked_positions?: {
        available?: boolean;
        database_url_configured?: boolean;
        error_message?: string | null;
        closed_position_count?: number | null;
        required_closed_position_count?: number | null;
        [key: string]: unknown;
      } | null;
      [key: string]: unknown;
    } | null;
  };
  active_incumbents?: Record<string, Record<string, OptionsProfitSideEntry>>;
  current_canary?: Record<string, Record<string, OptionsProfitCurrentCanary | null>> | null;
  last_decision?: Record<string, unknown> | null;
  blockers?: Array<string | OptionsProfitGateBlocker>;
  candidate_rankings?: OptionsProfitCandidateRanking[];
  [key: string]: unknown;
}

export interface ForwardEvidenceReport {
  generated_at?: string | null;
  source_label?: string | null;
  recent_session_count?: number | null;
  authoritative_session_count?: number | null;
  scan_pick_count?: number | null;
  eligible_scan_pick_count?: number | null;
  exact_contract_capture_counts?: {
    with_contract_count?: number | null;
    without_contract_count?: number | null;
  } | null;
  forward_truth_recording_failure_count?: number | null;
  activation_check?: {
    active?: boolean;
    status?: string | null;
    message?: string | null;
    historical_evidence_available?: boolean;
    latest_recorded_scan_pick_count?: number | null;
    [key: string]: unknown;
  } | null;
  ledger_summary?: {
    available?: boolean;
    authoritative_db_path?: string | null;
    archive_db_path?: string | null;
    scan_pick_count?: number | null;
    eligible_scan_pick_count?: number | null;
    observation_scan_pick_count?: number | null;
    recent_session_count?: number | null;
    authoritative_session_count?: number | null;
    [key: string]: unknown;
  } | null;
  archived_forward_artifact?: {
    available?: boolean;
    path?: string | null;
    run_at?: string | null;
    evidence_status?: string | null;
    primary_judge_trade_count?: number | null;
    primary_judge_fallback_used?: boolean;
    primary_judge_fallback_reason?: string | null;
    pending_truth_horizon_count?: number | null;
    contract_resolution_overview?: Record<string, number> | null;
    archived_sample_date_coverage?: Record<string, unknown> | null;
    [key: string]: unknown;
  } | null;
  recording_health?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface PositionReview {
  id?: number;
  reviewed_at: string;
  pricing_source?: string | null;
  current_option_price?: number | null;
  current_pnl_pct?: number | null;
  entry_execution_price?: number | null;
  exit_execution_price?: number | null;
  entry_execution_basis?: string | null;
  exit_execution_basis?: string | null;
  gross_pnl_pct?: number | null;
  net_pnl_pct?: number | null;
  gross_pnl_usd?: number | null;
  net_pnl_usd?: number | null;
  fee_total_usd?: number | null;
  recommendation: "HOLD" | "SELL";
  reason: string;
  warnings: string[];
  metrics_snapshot: Record<string, unknown>;
}

export interface TrackedPosition {
  id: number;
  status: "open" | "closed";
  ticker: string;
  direction: "call" | "put";
  contract_symbol?: string | null;
  strike: number;
  expiry: string;
  asset_class?: "equity" | "index" | null;
  contracts: number;
  entry_option_price: number;
  entry_underlying_price?: number | null;
  filled_at: string;
  entry_execution_price?: number | null;
  entry_execution_basis?: string | null;
  stop_loss_pct: number;
  profit_target_pct: number;
  time_exit_day: number;
  peak_pnl_pct?: number | null;
  last_option_price?: number | null;
  last_pnl_pct?: number | null;
  gross_pnl_pct?: number | null;
  net_pnl_pct?: number | null;
  gross_pnl_usd?: number | null;
  net_pnl_usd?: number | null;
  fee_total_usd?: number | null;
  last_recommendation?: "HOLD" | "SELL" | null;
  last_recommendation_reason?: string | null;
  last_reviewed_at?: string | null;
  source_pick_snapshot: ScanPick;
  notes?: string | null;
  closed_at?: string | null;
  exit_option_price?: number | null;
  exit_execution_price?: number | null;
  exit_execution_basis?: string | null;
  exit_reason?: string | null;
  latest_review?: PositionReview | null;
  share_safe_exact_live?: boolean;
  share_safe_reason?: string | null;
  share_review_age_minutes?: number | null;
  share_reviewed_at?: string | null;
  exact_contract_symbol?: string | null;
  proof_eligible?: boolean;
  proof_ineligibility_reason?: string | null;
  proof_class?: string | null;
  proof_class_reason?: string | null;
}

export interface CreateTrackedPositionRequest {
  scan_pick: ScanPick;
  fill_price: number;
  contracts: number;
  filled_at?: string;
  notes?: string;
}

export interface CloseTrackedPositionRequest {
  exit_price: number;
  closed_at?: string;
  notes?: string;
}

export type SuggestedTrade = TrackedPosition;

export type CreateSuggestedTradeRequest = CreateTrackedPositionRequest;

export type CloseSuggestedTradeRequest = CloseTrackedPositionRequest;

export interface StrategyProfile {
  name: string;
  philosophy: string;
  confidence_weights: {
    iv_percentile: number;
    delta: number;
    dte: number;
    technical: number;
  };
  targets: {
    delta_optimal: number;
    delta_falloff: number;
    dte_optimal: number;
    dte_falloff: number;
    iv_percentile_max: number;
  };
  filters: {
    vix_defense_threshold: number;
    atr_expansion_stop_mult: number;
    defense_position_mult: number;
    liquidity_spread_max_pct: number;
    illiquid_extra_margin_pct: number;
    iv_crush_z_threshold: number;
    iv_crush_confidence_penalty: number;
    min_ev_return_pct: number;
  };
  risk: {
    stop_loss_pct: number;
    profit_target_pct: number;
    max_position_pct: number;
    min_position_pct: number;
    account_size: number | null;
    max_drawdown_pct: number;
    dte_0_max_pct: number;
    time_exit_pct: number;
  };
  entry: {
    entry_momentum_pct: number;
    min_direction_score: number;
    min_tech_score: number;
  };
  direction_score_weights: {
    tech: number;
    regime: number;
    momentum: number;
  };
  rsi_overextension: {
    severe_threshold: number;
    moderate_threshold: number;
    severe_penalty: number;
    moderate_penalty: number;
  };
  quality_score_weights: {
    iv_rank: number;
    delta: number;
    dte: number;
  };
  early_exit: {
    enabled: boolean;
    min_hold_days: number;
    tech_decay_pct: number;
    direction_floor: number;
    momentum_reversal: boolean;
    rsi_extreme_exit: boolean;
    rsi_call_ceiling: number;
    rsi_put_floor: number;
    trailing_profit_pct: number;
    trailing_giveback_pct: number;
    min_profit_to_exit_pct: number;
  };
}

export interface SectorSentiment {
  sector: string;
  etf: string;
  near_sent: string;
  near_ret: number | null;
  med_sent: string;
  med_ret: number | null;
  long_sent: string;
  long_ret: number | null;
  data_status?: "available" | "unavailable";
}

export interface DailyPerformance {
  date: string;
  picks_graded: number;
  directional_wins: number;
  full_target_hits: number;
  win_rate_pct: number;
  avg_est_option_gain_pct: number;
  high_score_win_rate: number;
  low_score_win_rate: number;
  current_streak: number;
  current_streak_type: "win" | "loss";
  all_time_win_rate_pct: number;
  all_time_graded: number;
}

export interface BacktestResult {
  run_at: string;
  mode: string;
  profile?: string;
  lookback_years: number;
  iv_adj?: number;
  pricing_lane?: string | null;
  playbook?: string | null;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
  comparison?: TruthLaneComparisonReport | null;
  source?: TruthLaneSummary & Record<string, unknown>;
  total_days: number;
  total_trades: number;
  win_rate_pct: number | null;
  full_hit_rate_pct: number | null;
  directional_accuracy_pct: number | null;
  profit_factor: number | null;
  avg_pnl_pct: number | null;
  avg_picks_per_day: number | null;
  sharpe: number | null;
  max_drawdown_pct: number | null;
  trades: BacktestTrade[];
  equity_curve: { date: string; cum_pnl_pct: number }[];
}

export interface BacktestReplayGroupSummary {
  group: string;
  value: string;
  trades: number;
  share_of_total_pct: number;
  win_rate_pct: number;
  full_hit_rate_pct: number;
  directional_accuracy_pct: number;
  profit_factor: number;
  avg_pnl_pct: number;
  avg_direction_score: number;
  avg_quality_score?: number;
  avg_ev?: number;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
}

export interface BacktestReplayReport {
  generated_at: string;
  source: TruthLaneSummary & Record<string, unknown>;
  source_run_at?: string | null;
  source_mode?: string | null;
  lookback_years?: number | null;
  pricing_lane?: string | null;
  playbook?: string | null;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
  min_trades_filter: number;
  overall: BacktestReplayGroupSummary;
  by_direction_score: BacktestReplayGroupSummary[];
  by_ticker: BacktestReplayGroupSummary[];
  by_sector: BacktestReplayGroupSummary[];
  by_regime: BacktestReplayGroupSummary[];
  best_segments: BacktestReplayGroupSummary[];
  weakest_segments: BacktestReplayGroupSummary[];
  risk_flags: string[];
  sample_notes: string[];
  comparison?: TruthLaneComparisonReport | null;
}

export interface BacktestTrade {
  date: string;
  ticker: string;
  type: string;
  sector?: string | null;
  direction_score?: number | null;
  quality_score?: number | null;
  tech_score?: number | null;
  ev?: number | null;
  target_move_pct?: number | null;
  prediction_outcome?: string;
  market_regime?: string;
  strike?: number | null;
  entry_px?: number | null;
  exit_px?: number | null;
  pnl_pct?: number | null;
  exit_reason: string;
}

export interface MetricTruthSliceSummary {
  label: string;
  trades: number;
  share_of_total_pct: number;
  win_rate_pct: number;
  directional_accuracy_pct: number;
  full_hit_rate_pct: number;
  profit_factor: number;
  avg_pnl_pct: number;
  median_pnl_pct: number;
  avg_direction_score: number | null;
  sparse?: boolean;
  calibration_gap_pct?: number;
  truth_source?: string | null;
  priced_trade_count?: number | null;
  unpriced_trade_count?: number | null;
  quote_coverage_pct?: number | null;
  entry_quote_time_et?: string | null;
  exit_quote_time_et?: string | null;
}

export interface MetricTruthFloorSummary extends MetricTruthSliceSummary {
  floor: number;
  metric: string;
}

export interface MetricTruthHealthSummary {
  avg_pnl_trend: {
    dense_buckets: number;
    improving_steps: number;
    regressing_steps: number;
  };
  win_rate_trend: {
    dense_buckets: number;
    improving_steps: number;
    regressing_steps: number;
  };
  best_floor: MetricTruthFloorSummary | null;
}

export interface MetricTruthReport {
  generated_at?: string | null;
  source: {
    run_at?: string;
    mode?: string;
    lookback_years?: number;
    pricing_lane?: string | null;
    playbook?: string | null;
    total_days?: number;
    total_trades: number;
    truth_source?: string | null;
    priced_trade_count?: number | null;
    unpriced_trade_count?: number | null;
    quote_coverage_pct?: number | null;
    entry_quote_time_et?: string | null;
    exit_quote_time_et?: string | null;
  };
  quality_bar: {
    min_trades: number;
    bucket_size: number;
  };
  overall: MetricTruthSliceSummary;
  metric_buckets: Record<string, MetricTruthSliceSummary[]>;
  metric_floors: Record<string, MetricTruthFloorSummary[]>;
  metric_health: Record<string, MetricTruthHealthSummary>;
  risk_flags: string[];
  recommendations: string[];
}

export interface DayTradingStrategySpec {
  strategyId: string;
  name: string;
  hypothesisSummary: string;
  venueType: string;
  status: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  marketUniverse: {
    symbols: string[];
    category?: string;
    maxMarkets?: number;
  };
  entryRules: string[];
  exitRules: string[];
  cooldownRules: string[];
  evaluationWindow: {
    timeframe: string;
    warmupBars: number;
    minimumTrades: number;
  };
  simulation: {
    direction: string;
    entrySignal: string;
    entryExecution: string;
    takeProfitFraction: number;
    stopLossFraction: number;
    maxHoldBars: number;
    cooldownBars: number;
    maxConcurrentPositions?: number;
    useSignalStrengthThreshold?: number;
    exitTargetMode?: string;
  };
  riskLimits: {
    maxDrawdownFraction: number;
    maxDailyLossFraction: number;
    maxOpenPositions: number;
    minLiquidityUsd?: number;
    maxSpreadFraction?: number;
    maxWeeklyLossFraction?: number;
    maxDailyLosingTrades?: number;
    reduceSizeAtDrawdownFraction?: number;
    reduceSizeMultiplier?: number;
    maxCostToTargetFraction?: number;
    assumedRoundTripFeeFraction?: number;
    assumedSlippageFraction?: number;
  };
  sizing: {
    model: string;
    maxPositionFraction: number;
    riskPerTradeFraction?: number;
    riskSizing?: string;
  };
  metadata?: {
    owner?: string;
    tags?: string[];
    market?: string;
    exchange?: string;
    marketType?: string;
    sessionMode?: string;
    profitabilityProfileId?: string;
    unlockPhase?: string;
    executionVenuePrimary?: string;
    executionVenueBackup?: string;
    executionMode?: string;
    sessionTimeZone?: string;
    localSessionTimeZone?: string;
    alertWindowIds?: string[];
    stageHistory?: {
      from: string;
      to: string;
      reason: string;
      at: string;
    }[];
  };
}

export interface DayTradingPaperPosition {
  strategyId: string;
  symbol: string;
  quantity: number;
  avgEntryPrice: number;
  lastPrice: number;
  openedAt: string;
  updatedAt: string;
  markPrice: number | null;
  unrealizedPnl: number;
}

export interface DayTradingPaperAccount {
  accountId: string;
  startingCash: number;
  cash: number;
  realizedPnl: number;
  feesPaid: number;
  totalUnrealizedPnl: number;
  equity: number;
  positions: DayTradingPaperPosition[];
}

export interface DayTradingPaperSummary {
  strategyId: string;
  tradeCount: number;
  realizedPnl: number;
  unrealizedPnl: number;
  grossVolume: number;
  openPositions: number;
  winRate: number | null;
}

export interface DayTradingBacktestSummary {
  tradeCount: number;
  eligibleForPromotion: boolean;
  totalNetReturnFraction: number;
  maxDrawdownFraction: number;
  winRate: number;
  profitFactor: number | null;
  averageHoldBars: number | null;
  medianHoldBars: number | null;
  slippageAdjustedReturnFraction: number;
  vetoReasons: string[];
}

export interface DayTradingScoreboardItem {
  strategyId: string;
  strategyName: string;
  status: string;
  venueType: string;
  score: number;
  reasons: string[];
  vetoReasons: string[];
  backtest: DayTradingBacktestSummary | null;
  paper: DayTradingPaperSummary | null;
}

export interface DayTradingScoreboard {
  generatedAt: string;
  totals: {
    strategies: number;
    withPaperActivity: number;
    candidateLive: number;
    blocked: number;
  };
  leaders: DayTradingScoreboardItem[];
  items: DayTradingScoreboardItem[];
}

export interface DayTradingPilotGate {
  id: string;
  label: string;
  target: string;
  passed: boolean;
  actual: string;
}

export interface DayTradingPilotBreakdown {
  label: string;
  trades: number;
  winRate: number;
  expectancyR: number;
  netPnlUsd: number;
}

export interface DayTradingChecklistItem {
  key: string;
  label: string;
  description?: string;
  required: boolean;
}

export interface DayTradingTodayGate {
  localDate: string | null;
  dailyTradeCap: number;
  reservedTickets: number;
  usedTickets: number;
  expiredTickets: number;
  approvedEntries: number;
  remainingApprovals: number;
  activeSessionWindow: boolean;
  blocked: boolean;
  reasons: string[];
}

export interface DayTradingProfitabilityTicket {
  ticketId: string;
  strategyId: string;
  symbol: string;
  approvedAt: string | null;
  usedAt: string | null;
  localTradeDate: string | null;
  sessionLabel: string | null;
  storedStatus: string;
  lifecycleStatus: string;
  regimeState: string | null;
  tradeable: boolean;
  checklistFlags: Record<string, boolean>;
}

export interface DayTradingProfitabilityTicketsSummary {
  path: string;
  totalTickets: number;
  todayDate: string | null;
  todayGate: DayTradingTodayGate;
  todaysTickets: DayTradingProfitabilityTicket[];
  recentTickets: DayTradingProfitabilityTicket[];
}

export interface DayTradingArtifactHealth {
  checkedAt: string;
  status: string;
  configuredWindowIds: string[];
  strategyWindowIds: string[];
  watchlistWindowIds: string[];
  lastWatchlistGeneratedAt: string | null;
  warnings: string[];
}

export interface DayTradingProfitabilityJournalEntrySummary {
  entryId: string;
  ticketId: string;
  tradeTimestamp: string | null;
  loggedAt: string | null;
  localTradeDate?: string | null;
  sessionLabel?: string | null;
  symbol: string;
  regime: string;
  setupId: string;
  side: string;
  orderType?: string;
  entryLiquidityRole?: string;
  exitLiquidityRole?: string;
  entryFillRatio?: number | null;
  exitFillRatio?: number | null;
  plannedEntryPrice?: number | null;
  actualEntryPrice?: number | null;
  stopPrice?: number | null;
  targetPrice?: number | null;
  actualExitPrice?: number | null;
  sizeUsd?: number | null;
  feesUsd?: number | null;
  spreadSlippageUsd?: number | null;
  pnlR: number | null;
  pnlUsd: number | null;
  ruleAdherenceScore: number | null;
  mistakeTag: string;
  stopExecutionQuality: string;
  roundTripCostBps: number | null;
  pilotEligible: boolean;
  pilotDisqualificationReasons: string[];
  note: string;
}

export interface DayTradingProfitabilityJournalAggregate {
  label: string;
  totalEntries: number;
  eligibleEntries: number;
  disqualifiedEntries: number;
  netPnlUsd: number;
  eligibleNetPnlUsd: number;
  expectancyR: number | null;
  winRate: number | null;
  ruleAdherenceRate: number | null;
}

export interface DayTradingProfitabilityJournalSummary {
  path: string;
  ticketPath?: string;
  entryCount: number;
  schema: Array<{
    key: string;
    label: string;
    required: boolean;
  }>;
  lastLoggedAt: string | null;
  todayDate?: string | null;
  todayEntryCount?: number;
  todayEntries?: DayTradingProfitabilityJournalEntrySummary[];
  recentEntries: DayTradingProfitabilityJournalEntrySummary[];
  recentEligibleEntries?: DayTradingProfitabilityJournalEntrySummary[];
  today?: DayTradingProfitabilityJournalAggregate | null;
  trailingWeek?: DayTradingProfitabilityJournalAggregate | null;
  byDate?: DayTradingProfitabilityJournalAggregate[];
  byMistakeTag?: DayTradingProfitabilityJournalAggregate[];
}

export interface DayTradingExperimentVariantResult {
  variantId: string;
  strategyId: string;
  strategyName: string;
  baseStrategyId?: string | null;
  strategyFamily?: string | null;
  symbol?: string | null;
  timeframe?: string | null;
  market?: string | null;
  exchange?: string | null;
  marketType?: string | null;
  sessionMode?: string | null;
  windowMode?: string | null;
  windowModeLabel?: string | null;
  variantLabel?: string | null;
  challengerKind?: string | null;
  trustedMarketData?: boolean;
  marketDataSource?: string | null;
  marketDataWarning?: string | null;
  raw1mBarCountUsed?: number | null;
  derived5mBarCountUsed?: number | null;
  imported1mBarCountUsed?: number | null;
  importedSpanUsed?: {
    startTimestamp?: string | null;
    endTimestamp?: string | null;
  } | null;
  usedSpan?: {
    startTimestamp?: string | null;
    endTimestamp?: string | null;
  } | null;
  latestBarTimestamp?: string | null;
  experimentScore?: number | null;
  summary?: {
    eligibleForPromotion?: boolean;
    profitFactor?: number | null;
    totalNetReturnFraction?: number | null;
    winRate?: number | null;
    tradeCount?: number | null;
    vetoReasons?: string[];
  } | null;
  parameters?: Record<string, unknown> | null;
}

export interface DayTradingExperimentReport {
  generatedAt: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  windowModesEvaluated?: string[];
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  barsRequested?: number;
  feesFraction?: number;
  strictMarketData?: boolean;
  scope?: string;
  researchMode?: string;
  strategiesTested?: number;
  controlStrategiesTested?: number;
  variantsTested?: number;
  trustedVariantCount?: number;
  untrustedVariantCount?: number;
  eligibleVariantCount?: number;
  marketDataUsage?: Record<string, unknown> | null;
  tradeCountBySymbol?: Record<string, number>;
  tradeCountByWindowMode?: Record<string, number>;
  pnlShareBySymbol?: Record<string, number>;
  pnlShareByWindowMode?: Record<string, number>;
  leaders?: DayTradingExperimentVariantResult[];
  phaseA?: {
    description?: string;
    familyWindowReviews?: Record<string, unknown>[];
    controlResults?: DayTradingExperimentVariantResult[];
  };
  phaseB?: {
    unlocked?: boolean;
    reason?: string;
    selectedFamilyWindow?: {
      strategyFamily?: string;
      windowMode?: string;
      windowModeLabel?: string;
    } | null;
    selectedControlStrategyId?: string | null;
    batchShape?: string | null;
    results?: DayTradingExperimentVariantResult[];
  };
  recommendation?: string;
  nextSprintDefault?: string;
  notes?: string[];
  results?: DayTradingExperimentVariantResult[];
}

export interface DayTradingPilotMilestone {
  id: string;
  label: string;
  targetTrades: number;
  completedTrades: number;
  remainingTrades: number;
  reached: boolean;
  status: string;
  description: string;
}

export interface DayTradingPilotDisqualificationReason {
  reason: string;
  count: number;
}

export interface DayTradingPilotExecutionStats {
  makerShare: number | null;
  averageEntrySlippageBps: number | null;
  averageExitSlippageBps: number | null;
  partialFillRate: number | null;
  stopSlipRate: number | null;
}

export interface DayTradingOperatingPlan {
  profileId: string;
  objective: string;
  activeSetupId: string;
  activeSetupLabel: string;
  defaultRegimeBias: string;
  marketStanceAsOf: string;
  session: {
    localTimeZone: string;
    localWindow: string;
    sessionTimeZone: string;
    etWindow: string;
    weekdaysOnly: boolean;
  };
  instruments: {
    liveNow: string[];
    nextPhase: string[];
    paperOnly: string[];
  };
  execution: {
    venues: string[];
    orderStyle: string;
    blocklist: string[];
  };
  risk: {
    riskPerTradeFraction: number;
    maxTotalOpenRiskFraction: number;
    maxDailyLossFraction: number;
    maxWeeklyLossFraction: number;
    reduceSizeAtDrawdownFraction: number;
    pauseAtDrawdownFraction: number;
    maxCostToTargetFraction: number;
  };
  dailyTradeCap?: {
    limit: number;
    countedBy: string;
    unusedTicketExpiry: string;
    timeZone: string;
  };
  preTradeChecklist?: DayTradingChecklistItem[];
  regimeChecklist: {
    range: string[];
    trend: string[];
    event: string[];
  };
  journalTemplate: {
    path: string;
    fields: Array<{
      key: string;
      label: string;
      required: boolean;
    }>;
  };
}

export interface DayTradingPilotSummary {
  profileId: string;
  phase: string;
  progress: {
    completedTrades: number;
    targetTrades: number;
    remainingTrades: number;
  };
  journalStats: {
    totalEntries: number;
    phaseOneEntries: number;
    eligibleTradeCount?: number;
    disqualifiedTradeCount?: number;
    wins: number;
    losses: number;
    expectancyR: number | null;
    profitFactor: number | null;
    ruleAdherenceRate: number | null;
    netPnlUsd: number;
    maxDrawdownR: number;
    dominantTradeShare: number | null;
  };
  reviewCheckpointTrades?: number;
  advanceGateTrades?: number;
  todayGate?: DayTradingTodayGate;
  preTradeChecklist?: DayTradingChecklistItem[];
  milestones?: DayTradingPilotMilestone[];
  disqualificationReasons?: DayTradingPilotDisqualificationReason[];
  executionStats?: DayTradingPilotExecutionStats;
  breakdownByRegime: DayTradingPilotBreakdown[];
  breakdownBySetup: DayTradingPilotBreakdown[];
  breakdownByMistakeTag?: DayTradingPilotBreakdown[];
  gates: DayTradingPilotGate[];
  nextUnlock: string;
}

export interface DayTradingOperatorConsoleSnapshot {
  generatedAt: string;
  now: string;
  sessionWindow: {
    windowMode: string;
    activeNow: boolean;
    activeWindowId: string | null;
    activeWindowLabel: string | null;
    windows: {
      id: string;
      label: string;
      startEt: string;
      endEt: string;
    }[];
  };
  todayGate: DayTradingTodayGate;
  pilotPhase: string;
  nextUnlock: string;
  journal: DayTradingProfitabilityJournalSummary;
  experimentReport?: DayTradingExperimentReport | null;
  artifactHealth?: DayTradingArtifactHealth | null;
}

export interface DayTradingValidationResult {
  strategyId: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  trustedMarketData?: boolean;
  marketDataSource: string;
  marketDataWarning: string | null;
  savedTo: string;
  backtestSummary: DayTradingBacktestSummary;
  previousBacktestSummary: DayTradingBacktestSummary | null;
  paperAction: {
    action: string;
    reason?: string;
    reasons?: string[];
    price?: number;
  };
  promotionDecision?: {
    currentStatus: string;
    nextStatus: string;
    changed: boolean;
    reason: string;
  };
}

export interface DayTradingWatchlistItem {
  strategyId: string;
  strategyName: string;
  symbol: string | null;
  timeframe: string | null;
  signalName: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  liveStatus: string;
  notifyNow: boolean;
  alertEligible: boolean;
  evidenceScore: number | null;
  score: number;
  status: string;
  replayEvidence: {
    tradeCount: number;
    winRate: number;
    profitFactor: number | null;
    totalNetReturnFraction: number;
    eligibleForPromotion: boolean;
    vetoReasons: string[];
  } | null;
  paperEvidence: DayTradingPaperSummary | null;
  marketDataSource: string;
  marketDataWarning: string | null;
  lastBarTimestamp: string | null;
  latestSignalTimestamp: string | null;
  latestSignalValue: number | null;
  currentSignalValue: number | null;
  signalThreshold: number | null;
  barsSinceTrigger: number | null;
  barAgeMinutes: number | null;
  morningWindowActive: boolean;
  regimeState?: string;
  tradeable?: boolean;
  regimeBlockers?: string[];
  approvalSlotsRemaining?: number | null;
  dataFresh: boolean;
  currentDataTrusted: boolean;
  trustedMarketData?: boolean;
  sessionWindowId?: string | null;
  sessionWindowLabel?: string | null;
  sessionActiveNow?: boolean;
  currentPrice: number | null;
  indicators: Record<string, unknown> | null;
  reasons: string[];
  priorityScore?: number | null;
  priorityReasons?: string[];
  prioritySignals?: Record<string, unknown>;
  pilotSignals?: Record<string, unknown>;
}

export interface DayTradingWatchlist {
  generatedAt: string;
  profitabilityProfileId?: string;
  evaluatedAt: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  rankingBasis: string;
  rankingMethod?: string;
  morningWindow: {
    startEt: string;
    cutoffEt: string;
    activeNow: boolean;
  };
  sessionWindow?: {
    activeNow: boolean;
    activeWindowId: string | null;
    activeWindowLabel: string | null;
    windows: {
      id: string;
      label: string;
      startEt: string;
      endEt: string;
    }[];
  };
  selectedStrategies: number;
  notifyNowCount: number;
  todayGate?: DayTradingTodayGate;
  pilotSummary?: Partial<DayTradingPilotSummary> | null;
  journalSummary?: DayTradingProfitabilityJournalSummary | null;
  items: DayTradingWatchlistItem[];
}

export interface DayTradingReport {
  generatedAt: string;
  profitabilityProfileId?: string;
  market?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  strategiesScanned: number;
  results: DayTradingValidationResult[];
  scoreboard: DayTradingScoreboard;
  paperAccount: DayTradingPaperAccount;
}

export interface DayTradingSnapshot {
  generatedAt: string;
  profitabilityProfileId?: string;
  market?: string;
  marketLabel?: string;
  exchange?: string;
  marketType?: string;
  sessionMode?: string;
  alertWindows?: {
    id: string;
    label: string;
    startEt: string;
    endEt: string;
  }[];
  defaultConfig: {
    market?: string;
    exchange?: string;
    marketType?: string;
    sessionMode?: string;
    importInterval?: string;
    strategyTimeframe?: string;
    bars: number;
    startingCash: number;
    feesFraction: number;
    watchlistLimit?: number;
    morningStartEt?: string;
    morningCutoffEt?: string;
    notifyLookbackBars?: number;
    maxBarAgeMinutes?: number;
  };
  strategies: DayTradingStrategySpec[];
  scoreboard: DayTradingScoreboard;
  paperAccount: DayTradingPaperAccount;
  paperSummaries: DayTradingPaperSummary[];
  lastReport: DayTradingReport | null;
  lastWatchlist?: DayTradingWatchlist | null;
  lastImport?: {
    generatedAt: string;
    symbols: string[];
    minutes: number;
    results: {
      symbol: string;
      source: string;
      importedBars: number;
      totalBars: number;
      derivedBars: number;
      startTimestamp: string | null;
      endTimestamp: string | null;
    }[];
  } | null;
  operatingPlan?: DayTradingOperatingPlan;
  pilotSummary?: DayTradingPilotSummary;
  profitabilityJournal?: DayTradingProfitabilityJournalSummary;
  profitabilityTickets?: DayTradingProfitabilityTicketsSummary;
  artifactHealth?: DayTradingArtifactHealth;
  experimentReport?: DayTradingExperimentReport | null;
  operatorConsole?: DayTradingOperatorConsoleSnapshot;
}
