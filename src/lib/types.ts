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
  contract_symbol?: string | null;
  direction_score: number;
  quality_score: number;
  tech_score?: number;
  ev: number;
  dte: number;
  target_move_pct?: number | null;
  stock_price?: number;
  strike?: number;
  strike_est?: number;
  premium?: number;
  est_premium?: number;
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
  id: "short_term" | "swing" | string;
  label: string;
  description: string;
  target_dte: number;
  max_new_positions_per_day: number;
  max_sector_open_positions: number;
  max_regime_open_positions: number;
  block_same_ticker: boolean;
}

export interface ExposureSnapshot {
  open_positions: number;
  opened_today: number;
  ticker_counts: Record<string, number>;
  sector_counts: Record<string, number>;
  regime_counts: Record<string, number>;
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

export interface PositionReview {
  id?: number;
  reviewed_at: string;
  pricing_source?: string | null;
  current_option_price?: number | null;
  current_pnl_pct?: number | null;
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
  stop_loss_pct: number;
  profit_target_pct: number;
  time_exit_day: number;
  peak_pnl_pct?: number | null;
  last_option_price?: number | null;
  last_pnl_pct?: number | null;
  last_recommendation?: "HOLD" | "SELL" | null;
  last_recommendation_reason?: string | null;
  last_reviewed_at?: string | null;
  source_pick_snapshot: ScanPick;
  notes?: string | null;
  closed_at?: string | null;
  exit_option_price?: number | null;
  exit_reason?: string | null;
  latest_review?: PositionReview | null;
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

export interface SuggestedTrade extends TrackedPosition {}

export interface CreateSuggestedTradeRequest extends CreateTrackedPositionRequest {}

export interface CloseSuggestedTradeRequest extends CloseTrackedPositionRequest {}

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
  near_ret: number;
  med_sent: string;
  med_ret: number;
  long_sent: string;
  long_ret: number;
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
  win_rate_pct: number;
  full_hit_rate_pct: number;
  directional_accuracy_pct: number;
  profit_factor: number;
  avg_pnl_pct: number;
  avg_picks_per_day: number;
  sharpe: number;
  max_drawdown_pct: number;
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
  direction_score: number;
  quality_score?: number;
  tech_score: number;
  ev: number;
  target_move_pct?: number;
  prediction_outcome?: string;
  market_regime?: string;
  strike: number;
  entry_px: number;
  exit_px: number;
  pnl_pct: number;
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
  };
  riskLimits: {
    maxDrawdownFraction: number;
    maxDailyLossFraction: number;
    maxOpenPositions: number;
    minLiquidityUsd?: number;
    maxSpreadFraction?: number;
  };
  sizing: {
    model: string;
    maxPositionFraction: number;
    riskPerTradeFraction?: number;
  };
  metadata?: {
    owner?: string;
    tags?: string[];
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

export interface DayTradingValidationResult {
  strategyId: string;
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
  dataFresh: boolean;
  currentDataTrusted: boolean;
  currentPrice: number | null;
  indicators: Record<string, unknown> | null;
  reasons: string[];
}

export interface DayTradingWatchlist {
  generatedAt: string;
  evaluatedAt: string;
  rankingBasis: string;
  morningWindow: {
    startEt: string;
    cutoffEt: string;
    activeNow: boolean;
  };
  selectedStrategies: number;
  notifyNowCount: number;
  items: DayTradingWatchlistItem[];
}

export interface DayTradingReport {
  generatedAt: string;
  strategiesScanned: number;
  results: DayTradingValidationResult[];
  scoreboard: DayTradingScoreboard;
  paperAccount: DayTradingPaperAccount;
}

export interface DayTradingSnapshot {
  generatedAt: string;
  defaultConfig: {
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
}
