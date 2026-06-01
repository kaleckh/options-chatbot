import type { SuggestedTrade, TrackedPosition } from "@/lib/types";

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

const PRODUCTION_EVIDENCE_IDS = new Set<PositionEvidenceGroupId>(["live_exact", "manual_exact"]);
const TRUSTED_EXIT_BASIS_TOKENS = [
  "spread_bid_ask",
  "spread_bid_ask_exact",
  "historical_spread_bid_ask",
  "historical_suggested_close",
  "auto_sell_recommendation",
  "manual",
  "broker",
  "exact",
];
const UNTRUSTED_EXIT_BASIS_TOKENS = [
  "lifecycle",
  "elapsed",
  "last",
  "midpoint",
  "mark",
  "model",
  "unpriced",
];

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

function hasAnyEvidenceToken(values: string[], tokens: string[]): boolean {
  return values.some((value) => tokens.some((token) => value.includes(token)));
}

export function getPositionEvidenceDescriptor(
  position: TrackedPosition | SuggestedTrade
): PositionEvidenceDescriptor {
  const source = position.source_pick_snapshot || null;
  const proofClass = normalizeEvidenceValue(position.proof_class ?? source?.proof_class);
  const proofReason = compactEvidenceText(position.proof_class_reason || position.proof_ineligibility_reason);
  const evidenceValues = positionEvidenceValues(position);
  const migratedPaper = Boolean(source?.position_migration_id || source?.position_migrated_at_utc);
  const backfillOrResearch = Boolean(source?.research_only) || hasAnyEvidenceToken(evidenceValues, [
    "backfill",
    "research",
    "historical_replay",
    "historical_selection",
  ]);
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

  if (source?.comparable_contract) {
    return {
      id: "proof_ineligible",
      label: "Comparable exact",
      detail: "Excluded from proof lane",
      tone: "warning",
    };
  }

  if (proofClass === "ineligible" || position.proof_eligible === false) {
    return {
      id: "proof_ineligible",
      label: "Proof ineligible",
      detail: proofReason || "Missing proof gate",
      tone: "warning",
    };
  }

  if (proofClass === "live_scan_exact_contract" || position.proof_eligible) {
    return {
      id: "live_exact",
      label: "Live exact",
      detail: "Proof eligible scan row",
      tone: "live",
    };
  }

  if (proofClass === "manual_broker_exact_contract") {
    return {
      id: "manual_exact",
      label: "Manual exact",
      detail: "Broker/manual fill",
      tone: "muted",
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
    return { ...base, id: "manual_exact", productionProof: true, researchLearning: false };
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
  return PRODUCTION_EVIDENCE_IDS.has(getPositionEvidenceGroup(position).id);
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

export function isTruthGradeClosedPosition(position: TrackedPosition | SuggestedTrade): boolean {
  if (position.status !== "closed") return false;
  if (!hasExecutableEntry(position) || !hasTrustedExecutableExit(position)) return false;
  if (getRealizedPnlPct(position) == null) return false;
  const evidence = getPositionEvidenceGroup(position);
  return evidence.productionProof;
}

export function matchesClosedDataView(position: TrackedPosition, dataView: ClosedDataView): boolean {
  if (dataView === "all") return true;
  if (dataView === "truth_grade") return isTruthGradeClosedPosition(position);
  if (dataView === "unpriced") return getRealizedPnlPct(position) == null || !hasTrustedExecutableExit(position);
  return getPositionEvidenceGroup(position).id === dataView;
}

export function closedDataViewLabel(dataView: ClosedDataView): string {
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
