import type { SuggestedTrade, TrackedPosition } from "@/lib/types";
import {
  PRODUCTION_EVIDENCE_GROUP_IDS,
  PROOF_CLASSES,
  ENTRY_PRICE_FIELDS,
  PROOF_SOURCE_FIELDS,
  QUOTE_FRESHNESS_FIELDS,
  QUOTE_FRESHNESS_REQUIRED,
  QUOTE_TIME_FIELDS,
  REQUIRED_LIVE_SELECTION_SOURCE,
  REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS,
  RESEARCH_BACKFILL_IDENTITY_FIELDS,
  RESEARCH_BACKFILL_TOKENS,
  TRUSTED_ENTRY_BASIS_TOKENS,
  TRUSTED_EXIT_BASIS_TOKENS,
  TRUSTED_OPTIONS_SOURCE_LABELS,
  TRUSTED_OPTIONS_SOURCE_REQUIRED_TOKENS,
  UNTRUSTED_ENTRY_BASIS_TOKENS,
  UNTRUSTED_EXIT_BASIS_TOKENS,
  UNTRUSTED_QUOTE_FRESHNESS_TOKENS,
} from "@/lib/trading-desk/proofContract";

export type PositionEvidenceTone = "live" | "warning" | "muted";

export type PositionEvidenceDescriptor = {
  id: PositionEvidenceGroupId;
  label: string;
  detail: string;
  tone: PositionEvidenceTone;
};

export type PositionEvidenceGroupId =
  | "live_exact"
  | "manual_exact"
  | "historical_paper"
  | "research_backfill"
  | "lifecycle_only"
  | "proof_ineligible"
  | "legacy_unclassified"
  | "other";

export type PositionEvidenceGroup = {
  id: PositionEvidenceGroupId;
  label: string;
  tone: PositionEvidenceTone;
  productionProof: boolean;
  researchLearning: boolean;
};

export type ClosedDataView =
  | "current_policy"
  | "learned_away"
  | "realized_pnl"
  | "truth_grade"
  | "all"
  | "live_exact"
  | "manual_exact"
  | "historical_paper"
  | "research_backfill"
  | "lifecycle_only"
  | "legacy_unclassified"
  | "unpriced";

export type PositionOutcomeSummary = {
  rows: number;
  priced: number;
  negative: number;
  positiveOrFlat: number;
  unknown: number;
  winRatePct: number | null;
  avgPnlPct: number | null;
};

export type OpenReviewActionStateId =
  | "hold"
  | "review_missing"
  | "review_unpriced"
  | "non_executable_sell"
  | "executable_sell";

export type OpenReviewActionState = {
  id: OpenReviewActionStateId;
  label: string;
  detail: string;
  tone: "neutral" | "warning" | "danger";
};

export type CurrentPolicyReplayDecisionId =
  | "would_take_today"
  | "blocked_by_current_policy"
  | "unknown_missing_evidence"
  | "out_of_scope_lane";

export type CurrentPolicyReplayState = {
  id: CurrentPolicyReplayDecisionId;
  label: string;
  detail: string;
  tone: "live" | "warning" | "muted";
  lane: string;
  guardrailHits: string[];
};

export type PolicyCohortHealthStatus =
  | "insufficient_evidence"
  | "thin_watch"
  | "paper_only_thin_severe"
  | "paper_only_recent_break"
  | "watch_recent_fragile"
  | "healthy";

export type PolicyCohortSummary = {
  key: string;
  rows: number;
  priced: number;
  negative: number;
  positiveOrFlat: number;
  avgPnlPct: number | null;
  medianPnlPct: number | null;
  negativeRatePct: number | null;
  worstPnlPct: number | null;
  bestPnlPct: number | null;
  status: PolicyCohortHealthStatus;
};

export type CurrentPolicyCohortHealth = {
  rows: number;
  overall: PolicyCohortSummary;
  monthly: PolicyCohortSummary[];
  weekly: PolicyCohortSummary[];
  showcaseMonth: PolicyCohortSummary | null;
  recentMonth: PolicyCohortSummary | null;
  recentWeek: PolicyCohortSummary | null;
  overallStatus:
    | "paper_only_recent_week_break"
    | "paper_only_recent_month_break"
    | "watch_recent_fragile"
    | PolicyCohortHealthStatus;
};

const PRODUCTION_EVIDENCE_IDS = new Set<PositionEvidenceGroupId>(
  PRODUCTION_EVIDENCE_GROUP_IDS as readonly PositionEvidenceGroupId[]
);
const CURRENT_POLICY_REPAIR_LANES = new Set([
  "short_term",
  "swing",
  "bullish_momentum",
  "bullish_pullback_observation",
]);
const BULLISH_PULLBACK_KEEP_TICKERS = new Set(["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"]);
const LANE_TICKER_QUARANTINES: Record<string, Set<string>> = {
  short_term: new Set(["XLK", "IWM", "DIA", "SPY", "SLB", "NVDA"]),
  swing: new Set(["IWM", "XLK", "SLB", "DIA", "NFLX"]),
  bullish_momentum: new Set(["NVDA", "TSLA", "COIN"]),
};

export function normalizeEvidenceValue(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function compactEvidenceText(value: unknown): string {
  return String(value ?? "").trim().replaceAll("_", " ");
}

function positionEvidenceValues(position: TrackedPosition | SuggestedTrade): string[] {
  const source = position.source_pick_snapshot || null;
  return [
    position.proof_class,
    position.proof_class_reason,
    position.proof_ineligibility_reason,
    position.notes,
    source?.pricing_evidence_class,
    source?.profitability_evidence_class,
    source?.production_filter_action,
    source?.source_separation,
    source?.promotion_class,
    source?.selection_source,
    source?.event_type,
    source?.candidate_execution_label,
    source?.backfill_audit_id,
    source?.position_migration_id,
    source?.market_data_source,
    source?.status,
  ]
    .map(normalizeEvidenceValue)
    .filter(Boolean);
}

function safeNumber(value: unknown): number | null {
  if (value == null || value === "" || typeof value === "boolean") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function recordValue(record: Record<string, unknown>, key: string): unknown {
  return Object.prototype.hasOwnProperty.call(record, key) ? record[key] : undefined;
}

function sourceRecord(position: TrackedPosition | SuggestedTrade): Record<string, unknown> {
  return (position.source_pick_snapshot || {}) as unknown as Record<string, unknown>;
}

function compactEvidenceRecord(position: TrackedPosition | SuggestedTrade): Record<string, unknown> {
  return (position.compact_evidence || {}) as unknown as Record<string, unknown>;
}

function nestedRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function getCanonicalPolicyLane(position: TrackedPosition | SuggestedTrade): string {
  const source = sourceRecord(position);
  const raw = String(
    recordValue(source, "playbook_id") ||
    recordValue(source, "playbook") ||
    ""
  ).trim();
  if (raw.startsWith("bullish_pullback")) return "bullish_pullback_observation";
  return raw || "legacy_unlabeled";
}

function debitPctOfWidth(position: TrackedPosition | SuggestedTrade): number | null {
  const source = sourceRecord(position);
  const explicit = safeNumber(recordValue(source, "debit_pct_of_width"));
  if (explicit != null) return explicit;
  const netDebit =
    safeNumber(recordValue(source, "net_debit")) ??
    safeNumber(recordValue(source, "entry_execution_price"));
  const spreadWidth = safeNumber(recordValue(source, "spread_width"));
  if (netDebit == null || spreadWidth == null || spreadWidth <= 0) return null;
  return (netDebit / spreadWidth) * 100;
}

function fillDegradationVsMidPct(position: TrackedPosition | SuggestedTrade): number | null {
  const source = sourceRecord(position);
  const liquidity = nestedRecord(recordValue(source, "spread_liquidity"));
  const explicit =
    safeNumber(recordValue(source, "fill_degradation_vs_mid_pct")) ??
    safeNumber(recordValue(liquidity, "fill_degradation_vs_mid_pct"));
  if (explicit != null) return explicit;
  const entryDebit =
    safeNumber(recordValue(liquidity, "spread_entry_debit")) ??
    safeNumber(recordValue(source, "spread_entry_debit")) ??
    safeNumber(recordValue(source, "entry_execution_price")) ??
    safeNumber(recordValue(source, "net_debit"));
  const midDebit =
    safeNumber(recordValue(liquidity, "spread_mid_debit")) ??
    safeNumber(recordValue(source, "spread_mid_debit"));
  if (entryDebit == null || midDebit == null || midDebit <= 0) return null;
  return Math.max((entryDebit / midDebit - 1) * 100, 0);
}

function worstLegBidAskSpreadPct(position: TrackedPosition | SuggestedTrade): number | null {
  const source = sourceRecord(position);
  const liquidity = nestedRecord(recordValue(source, "spread_liquidity"));
  const explicit =
    safeNumber(recordValue(source, "worst_leg_bid_ask_spread_pct")) ??
    safeNumber(recordValue(source, "worst_leg_spread_pct")) ??
    safeNumber(recordValue(liquidity, "worst_leg_bid_ask_spread_pct"));
  if (explicit != null) return explicit;

  const values: number[] = [];
  for (const prefix of ["long", "short"]) {
    const bid = safeNumber(recordValue(liquidity, `${prefix}_bid`));
    const ask = safeNumber(recordValue(liquidity, `${prefix}_ask`));
    if (bid == null || ask == null) continue;
    const mid = (bid + ask) / 2;
    if (mid > 0) values.push(Math.max(((ask - bid) / mid) * 100, 0));
  }
  return values.length ? Math.max(...values) : null;
}

function signalRet5(position: TrackedPosition | SuggestedTrade): number | null {
  const source = sourceRecord(position);
  return safeNumber(recordValue(source, "signal_ret5")) ?? safeNumber(recordValue(source, "ret5"));
}

function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function medianNumber(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function normalizedTradeDateValue(position: TrackedPosition | SuggestedTrade): string | null {
  const source = sourceRecord(position);
  const quoteSnapshot = nestedRecord(recordValue(source, "entry_quote_snapshot"));
  const candidates = [
    recordValue(source, "signal_date"),
    recordValue(source, "scan_date"),
    recordValue(source, "trade_date"),
    recordValue(source, "date"),
    recordValue(quoteSnapshot, "captured_at_et"),
    recordValue(source, "quote_time_et"),
    recordValue(source, "logged_at"),
    recordValue(source, "source_scan_recorded_at_utc"),
    recordValue(source, "quote_timestamp_et"),
    recordValue(quoteSnapshot, "captured_at_utc"),
    recordValue(source, "quote_time_utc"),
    recordValue(source, "quote_timestamp_utc"),
    position.filled_at,
  ];

  for (const candidate of candidates) {
    const value = String(candidate ?? "").trim();
    const match = value.match(/^(\d{4}-\d{2}-\d{2})/);
    if (match) return match[1];
  }
  return null;
}

function monthCohortKey(position: TrackedPosition | SuggestedTrade): string {
  return normalizedTradeDateValue(position)?.slice(0, 7) || "unknown";
}

function weekCohortKey(position: TrackedPosition | SuggestedTrade): string {
  const value = normalizedTradeDateValue(position);
  if (!value) return "unknown";
  const [year, month, day] = value.split("-").map((part) => Number(part));
  if (!year || !month || !day) return "unknown";
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return "unknown";
  const dayOfWeek = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayOfWeek);
  const weekYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(weekYear, 0, 1));
  const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${weekYear}-W${String(week).padStart(2, "0")}`;
}

function classifyPolicyCohort(
  summary: Omit<PolicyCohortSummary, "key" | "status">,
  minRows: number
): PolicyCohortHealthStatus {
  const avg = summary.avgPnlPct;
  const med = summary.medianPnlPct;
  const negRate = summary.negativeRatePct;
  const worst = summary.worstPnlPct;

  if (summary.priced === 0) return "insufficient_evidence";
  if (summary.priced < minRows) {
    if (avg != null && avg < 0 && worst != null && worst <= -50) return "paper_only_thin_severe";
    return "thin_watch";
  }
  if (avg != null && avg < 0) return "paper_only_recent_break";
  if (med != null && med < 0 && negRate != null && negRate >= 50) return "paper_only_recent_break";
  if (negRate != null && negRate >= 70) return "paper_only_recent_break";
  if (med != null && med < 10) return "watch_recent_fragile";
  if (negRate != null && negRate >= 40) return "watch_recent_fragile";
  return "healthy";
}

function summarizePolicyCohortValues(key: string, values: number[], rows: number, minRows: number): PolicyCohortSummary {
  const negative = values.filter((value) => value < 0).length;
  const base = {
    key,
    rows,
    priced: values.length,
    negative,
    positiveOrFlat: values.length - negative,
    avgPnlPct: values.length ? roundTo(values.reduce((sum, value) => sum + value, 0) / values.length, 2) : null,
    medianPnlPct: values.length ? roundTo(medianNumber(values) ?? 0, 2) : null,
    negativeRatePct: values.length ? roundTo((negative / values.length) * 100, 1) : null,
    worstPnlPct: values.length ? roundTo(Math.min(...values), 2) : null,
    bestPnlPct: values.length ? roundTo(Math.max(...values), 2) : null,
  };
  return {
    ...base,
    status: classifyPolicyCohort(base, minRows),
  };
}

function summarizePolicyCohort(
  key: string,
  positions: Array<TrackedPosition | SuggestedTrade>,
  minRows: number
): PolicyCohortSummary {
  const values = positions
    .map((position) => getRealizedPnlPct(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  return summarizePolicyCohortValues(key, values, positions.length, minRows);
}

function groupedPolicyCohortSummaries(
  positions: Array<TrackedPosition | SuggestedTrade>,
  keyForPosition: (position: TrackedPosition | SuggestedTrade) => string,
  minRows: number
): PolicyCohortSummary[] {
  const grouped = new Map<string, Array<TrackedPosition | SuggestedTrade>>();
  for (const position of positions) {
    const key = keyForPosition(position);
    grouped.set(key, [...(grouped.get(key) || []), position]);
  }
  return Array.from(grouped.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, items]) => summarizePolicyCohort(key, items, minRows));
}

function latestKnownCohort(cohorts: PolicyCohortSummary[]): PolicyCohortSummary | null {
  const known = cohorts.filter((cohort) => cohort.key !== "unknown");
  return known.length ? known[known.length - 1] : null;
}

function bestShowcaseMonth(cohorts: PolicyCohortSummary[]): PolicyCohortSummary | null {
  const candidates = cohorts.filter((cohort) => cohort.key !== "unknown" && cohort.priced >= 5 && cohort.avgPnlPct != null);
  if (!candidates.length) return null;
  return candidates.reduce((best, cohort) =>
    (cohort.avgPnlPct ?? Number.NEGATIVE_INFINITY) > (best.avgPnlPct ?? Number.NEGATIVE_INFINITY)
      ? cohort
      : best
  );
}

export function policyCohortHealthStatusLabel(
  status: CurrentPolicyCohortHealth["overallStatus"] | PolicyCohortHealthStatus
): string {
  if (String(status).startsWith("paper_only")) return "Paper-only";
  if (status === "watch_recent_fragile") return "Watch";
  if (status === "thin_watch") return "Thin watch";
  if (status === "healthy") return "Healthy";
  return "Insufficient";
}

export function buildCurrentPolicyCohortHealth(
  positions: Array<TrackedPosition | SuggestedTrade>
): CurrentPolicyCohortHealth {
  const scoped = positions.filter(isCurrentPolicyClosedPosition);
  const monthly = groupedPolicyCohortSummaries(scoped, monthCohortKey, 5);
  const weekly = groupedPolicyCohortSummaries(scoped, weekCohortKey, 3);
  const recentMonth = latestKnownCohort(monthly);
  const recentWeek = latestKnownCohort(weekly);
  const showcaseMonth = bestShowcaseMonth(monthly);
  const recentMonthStatus = recentMonth?.status || "insufficient_evidence";
  const recentWeekStatus = recentWeek?.status || "insufficient_evidence";
  const overallStatus = String(recentWeekStatus).startsWith("paper_only")
    ? "paper_only_recent_week_break"
    : String(recentMonthStatus).startsWith("paper_only")
      ? "paper_only_recent_month_break"
      : recentMonthStatus === "watch_recent_fragile"
        ? "watch_recent_fragile"
        : recentMonthStatus;

  return {
    rows: scoped.length,
    overall: summarizePolicyCohort("overall", scoped, 5),
    monthly,
    weekly,
    showcaseMonth,
    recentMonth,
    recentWeek,
    overallStatus,
  };
}

export function currentPolicyGuardrailHits(position: TrackedPosition | SuggestedTrade): string[] {
  const lane = getCanonicalPolicyLane(position);
  if (!CURRENT_POLICY_REPAIR_LANES.has(lane)) return [];

  const ticker = String(position.ticker || "").trim().toUpperCase();
  const hits: string[] = [];
  const debitPct = debitPctOfWidth(position);
  const fillDegradation = fillDegradationVsMidPct(position);
  const worstLeg = worstLegBidAskSpreadPct(position);
  const ret5 = signalRet5(position);

  if (debitPct != null && debitPct > 45) hits.push("debit_gt_45_width");
  if (fillDegradation != null && fillDegradation >= 20) hits.push("fill_degradation_ge_20");
  if (worstLeg != null && worstLeg >= 20) hits.push("worst_leg_spread_ge_20");
  if (LANE_TICKER_QUARANTINES[lane]?.has(ticker)) hits.push("lane_ticker_quarantine");
  if (lane === "bullish_pullback_observation" && !BULLISH_PULLBACK_KEEP_TICKERS.has(ticker)) {
    hits.push("bullish_pullback_not_keep_bucket");
  }
  if (lane === "bullish_pullback_observation" && ret5 != null && ret5 < -2) {
    hits.push("bullish_pullback_ret5_lt_minus_2");
  }

  return hits;
}

export function getCurrentPolicyReplayState(position: TrackedPosition | SuggestedTrade): CurrentPolicyReplayState {
  const lane = getCanonicalPolicyLane(position);
  const guardrailHits = currentPolicyGuardrailHits(position);

  if (!CURRENT_POLICY_REPAIR_LANES.has(lane)) {
    return {
      id: "out_of_scope_lane",
      label: "Outside policy",
      detail: "This lane does not have a promoted current-policy replay in the Trading Desk repair audit.",
      tone: "muted",
      lane,
      guardrailHits,
    };
  }

  if (guardrailHits.length > 0) {
    return {
      id: "blocked_by_current_policy",
      label: "Learned away",
      detail: `Current entry guardrails would block: ${guardrailHits.join(", ")}`,
      tone: "warning",
      lane,
      guardrailHits,
    };
  }

  if (!isRealizedPnlClosedPosition(position)) {
    return {
      id: "unknown_missing_evidence",
      label: "Needs evidence",
      detail: "Trusted executable realized P&L is missing, so current-policy outcome is not scored.",
      tone: "warning",
      lane,
      guardrailHits,
    };
  }

  return {
    id: "would_take_today",
    label: "Would take today",
    detail: "This row clears the current promoted entry guardrails and has trusted realized P&L.",
    tone: "live",
    lane,
    guardrailHits,
  };
}

function hasAnyEvidenceToken(values: string[], tokens: readonly string[]): boolean {
  return values.some((value) => tokens.some((token) => value.includes(token)));
}

function hasAnyEvidenceIdentityField(
  row: Record<string, unknown>,
  source: Record<string, unknown>,
  fields: readonly string[]
): boolean {
  return fields.some((field) =>
    (row[field] != null && row[field] !== "") ||
    (source[field] != null && source[field] !== "")
  );
}

function asEvidenceRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function sourceEvidenceRecord(position: TrackedPosition | SuggestedTrade): Record<string, unknown> {
  return asEvidenceRecord(position.source_pick_snapshot);
}

function entryQuoteSnapshotRecord(position: TrackedPosition | SuggestedTrade): Record<string, unknown> {
  const topLevel = asEvidenceRecord((position as unknown as Record<string, unknown>).entry_quote_snapshot);
  if (Object.keys(topLevel).length > 0) return topLevel;
  return asEvidenceRecord(sourceEvidenceRecord(position).entry_quote_snapshot);
}

function finiteEvidenceNumber(value: unknown): number | null {
  if (typeof value === "boolean" || value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstEvidenceValue(
  position: TrackedPosition | SuggestedTrade,
  fields: readonly string[],
  snapshot: Record<string, unknown> = entryQuoteSnapshotRecord(position)
): unknown {
  const row = position as unknown as Record<string, unknown>;
  const source = sourceEvidenceRecord(position);
  for (const field of fields) {
    if (row[field] != null && row[field] !== "") return row[field];
    if (source[field] != null && source[field] !== "") return source[field];
    if (snapshot[field] != null && snapshot[field] !== "") return snapshot[field];
  }
  return null;
}

function hasEvidenceValue(position: TrackedPosition | SuggestedTrade, fields: readonly string[]): boolean {
  return firstEvidenceValue(position, fields) != null;
}

function hasRawExactContract(position: TrackedPosition | SuggestedTrade): boolean {
  return Boolean(
    normalizeEvidenceValue(position.contract_symbol || sourceEvidenceRecord(position).contract_symbol).trim()
  );
}

function hasLiveExactSelectionSource(position: TrackedPosition | SuggestedTrade): boolean {
  return (
    normalizeEvidenceValue(
      firstEvidenceValue(position, ["selection_source", "contract_selection_source"])
    ) === REQUIRED_LIVE_SELECTION_SOURCE
  );
}

function hasVerifiedSourceScanLineage(position: TrackedPosition | SuggestedTrade): boolean {
  const row = position as unknown as Record<string, unknown>;
  const source = sourceEvidenceRecord(position);
  const hasRequiredFields = REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS.every((field) =>
    (row[field] != null && row[field] !== "") ||
    (source[field] != null && source[field] !== "")
  );
  if (!hasRequiredFields) return false;
  return Boolean(row.source_scan_lineage_verified || source.source_scan_lineage_verified);
}

function hasTrustedOpraSource(position: TrackedPosition | SuggestedTrade): boolean {
  const row = position as unknown as Record<string, unknown>;
  const source = sourceEvidenceRecord(position);
  const values = PROOF_SOURCE_FIELDS.flatMap((field) => [
    normalizeEvidenceValue(row[field]),
    normalizeEvidenceValue(source[field]),
  ]).filter(Boolean);
  return values.some(
    (value) =>
      TRUSTED_OPTIONS_SOURCE_LABELS.includes(value) ||
      TRUSTED_OPTIONS_SOURCE_REQUIRED_TOKENS.every((token) => value.includes(token))
  );
}

function hasFreshProofQuote(position: TrackedPosition | SuggestedTrade): boolean {
  const snapshot = entryQuoteSnapshotRecord(position);
  const row = position as unknown as Record<string, unknown>;
  const source = sourceEvidenceRecord(position);
  const freshnessValues = QUOTE_FRESHNESS_FIELDS.flatMap((field) => [
    normalizeEvidenceValue(row[field]),
    normalizeEvidenceValue(source[field]),
    normalizeEvidenceValue(snapshot[field]),
  ]);
  if (QUOTE_FRESHNESS_REQUIRED && !freshnessValues.some(Boolean)) return false;
  return !freshnessValues.some((value) =>
    UNTRUSTED_QUOTE_FRESHNESS_TOKENS.some((token) => value.includes(token))
  );
}

function hasExecutableProofEntry(position: TrackedPosition | SuggestedTrade): boolean {
  const snapshot = entryQuoteSnapshotRecord(position);
  const entryPrice = finiteEvidenceNumber(firstEvidenceValue(position, ENTRY_PRICE_FIELDS, snapshot));
  if (entryPrice == null || entryPrice <= 0) return false;
  const basis = normalizeEvidenceValue(
    (position as unknown as Record<string, unknown>).entry_execution_basis ||
    sourceEvidenceRecord(position).entry_execution_basis ||
    snapshot.entry_execution_basis
  );
  if (!basis) return false;
  if (UNTRUSTED_ENTRY_BASIS_TOKENS.some((token) => basis.includes(token))) return false;
  if (!TRUSTED_ENTRY_BASIS_TOKENS.some((token) => basis.includes(token))) return false;
  const quoteTimestamp = Boolean(
    hasEvidenceValue(position, QUOTE_TIME_FIELDS) ||
    snapshot.quote_time_et ||
    snapshot.quote_time_utc ||
    snapshot.captured_at_utc
  );
  return quoteTimestamp && hasFreshProofQuote(position);
}

function hasLiveExactProductionProof(position: TrackedPosition | SuggestedTrade): boolean {
  const source = sourceEvidenceRecord(position);
  const proofClass = normalizeEvidenceValue(position.proof_class ?? source.proof_class);
  return (
    proofClass === PROOF_CLASSES.liveScanExact &&
    position.proof_eligible === true &&
    hasRawExactContract(position) &&
    hasLiveExactSelectionSource(position) &&
    hasVerifiedSourceScanLineage(position) &&
    hasTrustedOpraSource(position) &&
    hasExecutableProofEntry(position)
  );
}

export function getPositionEvidenceDescriptor(
  position: TrackedPosition | SuggestedTrade
): PositionEvidenceDescriptor {
  const source = position.source_pick_snapshot || null;
  const compactEvidence = compactEvidenceRecord(position);
  const proofClass = normalizeEvidenceValue(position.proof_class ?? source?.proof_class);
  const proofReason = compactEvidenceText(position.proof_class_reason || position.proof_ineligibility_reason);
  const evidenceValues = positionEvidenceValues(position);
  const rowRecord = position as unknown as Record<string, unknown>;
  const sourceRecord = sourceEvidenceRecord(position);
  const migratedPaper = Boolean(
    source?.position_migration_id ||
    source?.position_migrated_at_utc ||
    compactEvidence.migrated_paper
  );
  const backfillOrResearch =
    Boolean(source?.research_only || compactEvidence.research_backfill) ||
    hasAnyEvidenceIdentityField(rowRecord, sourceRecord, RESEARCH_BACKFILL_IDENTITY_FIELDS) ||
    hasAnyEvidenceToken(evidenceValues, RESEARCH_BACKFILL_TOKENS);
  const lifecycleOnly =
    position.status === "closed" &&
    position.exit_execution_price == null &&
    position.exit_option_price == null &&
    position.latest_review?.exit_execution_price == null;

  if (lifecycleOnly) {
    return {
      id: "lifecycle_only",
      label: "Lifecycle-only",
      detail: "No executable exit proof",
      tone: "warning",
    };
  }

  if (migratedPaper) {
    return {
      id: "historical_paper",
      label: "Historical paper",
      detail: "Migrated research row",
      tone: "warning",
    };
  }

  if (backfillOrResearch) {
    return {
      id: "research_backfill",
      label: "Research backfill",
      detail: "Not live production proof",
      tone: "warning",
    };
  }

  if (source?.comparable_contract || compactEvidence.comparable_contract) {
    return {
      id: "proof_ineligible",
      label: "Comparable exact",
      detail: "Excluded from proof lane",
      tone: "warning",
    };
  }

  if (proofClass === PROOF_CLASSES.manualBrokerExact) {
    return {
      id: "manual_exact",
      label: "Manual exact",
      detail: "Broker/manual fill",
      tone: "muted",
    };
  }

  if (proofClass === PROOF_CLASSES.ineligible || position.proof_eligible === false) {
    return {
      id: "proof_ineligible",
      label: "Proof ineligible",
      detail: proofReason || "Missing proof gate",
      tone: "warning",
    };
  }

  if (proofClass === PROOF_CLASSES.liveScanExact) {
    if (!hasLiveExactProductionProof(position)) {
      return {
        id: "proof_ineligible",
        label: "Proof ineligible",
        detail: proofReason || "Missing persisted live proof gate",
        tone: "warning",
      };
    }
    return {
      id: "live_exact",
      label: "Live exact",
      detail: "Proof eligible scan row",
      tone: "live",
    };
  }

  return {
    id: "legacy_unclassified",
    label: "Legacy/unclassified",
    detail: "Review provenance",
    tone: "muted",
  };
}

export function getPositionEvidenceGroup(position: TrackedPosition | SuggestedTrade): PositionEvidenceGroup {
  const descriptor = getPositionEvidenceDescriptor(position);
  const base = {
    label: descriptor.label,
    tone: descriptor.tone,
  };

  if (descriptor.id === "live_exact") {
    return { ...base, id: "live_exact", productionProof: true, researchLearning: false };
  }
  if (descriptor.id === "manual_exact") {
    return { ...base, id: "manual_exact", productionProof: false, researchLearning: false };
  }
  if (descriptor.id === "historical_paper") {
    return { ...base, id: "historical_paper", productionProof: false, researchLearning: true };
  }
  if (descriptor.id === "research_backfill") {
    return { ...base, id: "research_backfill", productionProof: false, researchLearning: true };
  }
  if (descriptor.id === "lifecycle_only") {
    return { ...base, id: "lifecycle_only", productionProof: false, researchLearning: true };
  }
  if (descriptor.id === "proof_ineligible") {
    return { ...base, id: "proof_ineligible", productionProof: false, researchLearning: true };
  }
  if (descriptor.id === "legacy_unclassified") {
    return { ...base, id: "legacy_unclassified", productionProof: false, researchLearning: false };
  }
  return { ...base, id: "other", productionProof: false, researchLearning: false };
}

export function isProductionProofPosition(position: TrackedPosition | SuggestedTrade): boolean {
  const hasProductionEntryEvidence = PRODUCTION_EVIDENCE_IDS.has(getPositionEvidenceGroup(position).id);
  if (!hasProductionEntryEvidence) return false;
  // Closed production-proof claims need trusted exit evidence and calculable realized P&L.
  return position.status === "closed" ? isTruthGradeClosedPosition(position) : true;
}

export function isResearchLearningPosition(position: TrackedPosition | SuggestedTrade): boolean {
  return getPositionEvidenceGroup(position).researchLearning;
}

export function getEntryExecutionPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.latest_review?.entry_execution_price ??
    position.entry_execution_price ??
    position.source_pick_snapshot?.entry_execution_price ??
    position.entry_option_price ??
    null
  );
}

export function getMarkPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return position.latest_review?.current_option_price ?? position.last_option_price ?? null;
}

export function getCloseNowPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.latest_review?.exit_execution_price ??
    position.exit_execution_price ??
    position.exit_option_price ??
    position.latest_review?.current_option_price ??
    position.last_option_price ??
    null
  );
}

export function getRealizedExitPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.exit_execution_price ??
    position.exit_option_price ??
    position.latest_review?.exit_execution_price ??
    position.latest_review?.current_option_price ??
    null
  );
}

export function calcOptionPnlPct(entryPrice?: number | null, exitPrice?: number | null): number | null {
  if (entryPrice == null || exitPrice == null || entryPrice <= 0) return null;
  return Math.max((exitPrice / entryPrice - 1) * 100, -100);
}

export function calcNetOptionPnlPct(options: {
  entryPrice?: number | null;
  exitPrice?: number | null;
  contracts?: number | null;
  feeTotalUsd?: number | null;
}): number | null {
  const entryPrice = options.entryPrice ?? null;
  const exitPrice = options.exitPrice ?? null;
  const contracts = Number(options.contracts || 0);
  const feeTotalUsd = options.feeTotalUsd ?? 0;
  if (
    entryPrice == null ||
    exitPrice == null ||
    Number.isNaN(entryPrice) ||
    Number.isNaN(exitPrice) ||
    entryPrice <= 0 ||
    contracts <= 0
  ) {
    return null;
  }

  const capitalAtRiskUsd = entryPrice * contracts * 100;
  const totalCostBasisUsd = capitalAtRiskUsd + Math.max(feeTotalUsd, 0);
  if (capitalAtRiskUsd <= 0 || totalCostBasisUsd <= 0) return null;

  const grossPnlUsd = (exitPrice - entryPrice) * contracts * 100;
  const netPnlUsd = grossPnlUsd - feeTotalUsd;
  return Math.max((netPnlUsd / totalCostBasisUsd) * 100, -100);
}

export function getMarkPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
  return calcOptionPnlPct(getEntryExecutionPrice(position), getMarkPrice(position));
}

export function getCloseNowPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
  const feeTotalUsd =
    position.latest_review?.fee_total_usd ??
    position.fee_total_usd ??
    0;

  return (
    calcNetOptionPnlPct({
      entryPrice: getEntryExecutionPrice(position),
      exitPrice: getCloseNowPrice(position),
      contracts: position.contracts,
      feeTotalUsd,
    }) ??
    position.latest_review?.net_pnl_pct ??
    position.net_pnl_pct ??
    position.latest_review?.gross_pnl_pct ??
    position.gross_pnl_pct ??
    position.last_pnl_pct ??
    null
  );
}

export function getRealizedPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.net_pnl_pct ??
    position.latest_review?.net_pnl_pct ??
    calcNetOptionPnlPct({
      entryPrice: getEntryExecutionPrice(position),
      exitPrice: getRealizedExitPrice(position),
      contracts: position.contracts,
      feeTotalUsd: position.fee_total_usd ?? position.latest_review?.fee_total_usd ?? 0,
    }) ??
    position.gross_pnl_pct ??
    position.latest_review?.gross_pnl_pct ??
    calcOptionPnlPct(getEntryExecutionPrice(position), getRealizedExitPrice(position)) ??
    null
  );
}

export function getExitExecutionBasis(position: TrackedPosition | SuggestedTrade): string {
  return normalizeEvidenceValue(
    position.exit_execution_basis ??
    position.latest_review?.exit_execution_basis ??
    position.latest_review?.pricing_source ??
    position.exit_reason ??
    ""
  );
}

export function hasTrustedExecutableExit(position: TrackedPosition | SuggestedTrade): boolean {
  const exitPrice = getRealizedExitPrice(position);
  if (exitPrice == null || Number.isNaN(exitPrice)) return false;
  const basis = getExitExecutionBasis(position);
  if (!basis) return false;
  if (UNTRUSTED_EXIT_BASIS_TOKENS.some((token) => basis.includes(token))) return false;
  return TRUSTED_EXIT_BASIS_TOKENS.some((token) => basis.includes(token));
}

export function hasExecutableEntry(position: TrackedPosition | SuggestedTrade): boolean {
  const entryPrice = getEntryExecutionPrice(position);
  return entryPrice != null && !Number.isNaN(entryPrice) && entryPrice > 0;
}

function latestReviewMetricIsTrue(position: TrackedPosition | SuggestedTrade, key: string): boolean {
  const metrics = position.latest_review?.metrics_snapshot;
  return Boolean(metrics && metrics[key] === true);
}

export function hasExecutableLatestReviewExit(position: TrackedPosition | SuggestedTrade): boolean {
  const review = position.latest_review;
  if (!review) return false;
  const exitPrice = review.exit_execution_price;
  if (exitPrice == null || Number.isNaN(exitPrice)) return false;

  if (latestReviewMetricIsTrue(position, "price_trigger_ok")) return true;

  const basis = normalizeEvidenceValue(review.exit_execution_basis);
  if (!basis) return false;
  if (UNTRUSTED_EXIT_BASIS_TOKENS.some((token) => basis.includes(token))) return false;
  return TRUSTED_EXIT_BASIS_TOKENS.some((token) => basis.includes(token));
}

export function getOpenReviewActionState(position: TrackedPosition | SuggestedTrade): OpenReviewActionState {
  if (!position.latest_review) {
    return {
      id: "review_missing",
      label: "Review needed",
      detail: "No stored review is available.",
      tone: "warning",
    };
  }

  const recommendation = normalizeEvidenceValue(
    position.last_recommendation || position.latest_review.recommendation
  ).toUpperCase();

  if (recommendation === "SELL") {
    if (hasExecutableLatestReviewExit(position)) {
      return {
        id: "executable_sell",
        label: "Close now",
        detail: "Stored SELL review has executable exit evidence.",
        tone: "danger",
      };
    }
    return {
      id: "non_executable_sell",
      label: "Review quote",
      detail: "SELL signal needs executable exit evidence before close.",
      tone: "warning",
    };
  }

  if (position.latest_review.current_option_price == null) {
    return {
      id: "review_unpriced",
      label: "Review quote",
      detail: "Latest review has no live option price.",
      tone: "warning",
    };
  }

  return {
    id: "hold",
    label: "Hold",
    detail: "No close action is indicated.",
    tone: "neutral",
  };
}

export function isTruthGradeClosedPosition(position: TrackedPosition | SuggestedTrade): boolean {
  if (position.status !== "closed") return false;
  if (!hasExecutableEntry(position) || !hasTrustedExecutableExit(position)) return false;
  if (getRealizedPnlPct(position) == null) return false;
  const evidence = getPositionEvidenceGroup(position);
  return evidence.productionProof;
}

export function isRealizedPnlClosedPosition(position: TrackedPosition | SuggestedTrade): boolean {
  if (position.status !== "closed") return false;
  if (!hasExecutableEntry(position) || !hasTrustedExecutableExit(position)) return false;
  return getRealizedPnlPct(position) != null;
}

export function isCurrentPolicyClosedPosition(position: TrackedPosition | SuggestedTrade): boolean {
  return getCurrentPolicyReplayState(position).id === "would_take_today";
}

export function isLearnedAwayClosedPosition(position: TrackedPosition | SuggestedTrade): boolean {
  return getCurrentPolicyReplayState(position).id === "blocked_by_current_policy";
}

export function matchesClosedDataView(position: TrackedPosition, dataView: ClosedDataView): boolean {
  if (dataView === "all") return true;
  if (dataView === "current_policy") return isCurrentPolicyClosedPosition(position);
  if (dataView === "learned_away") return isLearnedAwayClosedPosition(position);
  if (dataView === "realized_pnl") return isRealizedPnlClosedPosition(position);
  if (dataView === "truth_grade") return isTruthGradeClosedPosition(position);
  if (dataView === "unpriced") return getRealizedPnlPct(position) == null || !hasTrustedExecutableExit(position);
  return getPositionEvidenceGroup(position).id === dataView;
}

export function closedDataViewLabel(dataView: ClosedDataView): string {
  if (dataView === "current_policy") return "Current policy";
  if (dataView === "learned_away") return "Learned away";
  if (dataView === "realized_pnl") return "Realized P&L";
  if (dataView === "truth_grade") return "Truth-grade";
  if (dataView === "all") return "All closed";
  if (dataView === "live_exact") return "Live exact";
  if (dataView === "manual_exact") return "Manual exact";
  if (dataView === "historical_paper") return "Historical paper";
  if (dataView === "research_backfill") return "Research backfill";
  if (dataView === "lifecycle_only") return "Lifecycle-only";
  if (dataView === "legacy_unclassified") return "Legacy";
  return "Unpriced";
}

export function calcAveragePositionPnlPct<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlPct: (position: T) => number | null
): number | null {
  const values = positions
    .map((position) => getPnlPct(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  return values.length > 0
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null;
}

export function calcWinRatePct<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlPct: (position: T) => number | null
): number | null {
  const values = positions
    .map((position) => getPnlPct(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  if (values.length === 0) return null;
  const wins = values.filter((value) => value > 0).length;
  return (wins / values.length) * 100;
}

export function summarizePositionOutcomes<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlPct: (position: T) => number | null
): PositionOutcomeSummary {
  const values = positions
    .map((position) => getPnlPct(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  const negative = values.filter((value) => value < 0).length;
  const positiveOrFlat = values.filter((value) => value >= 0).length;
  return {
    rows: positions.length,
    priced: values.length,
    negative,
    positiveOrFlat,
    unknown: Math.max(positions.length - values.length, 0),
    winRatePct: values.length > 0 ? (positiveOrFlat / values.length) * 100 : null,
    avgPnlPct: values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
  };
}

export function positionQualityPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
  return position.status === "closed" ? getRealizedPnlPct(position) : getCloseNowPnlPct(position);
}
