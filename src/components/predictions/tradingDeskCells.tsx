import type { ScanPick, SuggestedTrade, TrackedPosition } from "@/lib/types";
import {
  getCloseNowPnlPct,
  getCloseNowPrice,
  getCurrentPolicyReplayState,
  getOpenReviewActionState,
  getMarkPnlPct,
  getMarkPrice,
} from "@/lib/trading-desk/positionEvidence";
import {
  fmtCompactLabel,
  fmtDate,
  fmtDateTime,
  fmtMoney,
  fmtPct,
  fmtPricingSource,
  metricToneClass,
  quoteContextLabel,
} from "@/components/predictions/tradingDeskFormat";

export const SHARE_SAFE_REVIEW_MAX_AGE_MINUTES = 15;

export function getReviewedAt(position: TrackedPosition | SuggestedTrade): string | null {
  return position.share_reviewed_at ?? position.latest_review?.reviewed_at ?? position.last_reviewed_at ?? null;
}

export function getCollectionReviewSummary(items: Array<TrackedPosition | SuggestedTrade>): string | null {
  const reviewedValues = items
    .map((item) => getReviewedAt(item))
    .filter((value): value is string => Boolean(value));
  if (!reviewedValues.length) return null;

  let latestValue: string | null = null;
  let latestMs = -Infinity;
  for (const value of reviewedValues) {
    const parsed = new Date(value).getTime();
    if (Number.isNaN(parsed)) continue;
    if (parsed > latestMs) {
      latestMs = parsed;
      latestValue = value;
    }
  }

  const summaryValue = latestValue ?? reviewedValues[0];
  const uniqueCount = new Set(reviewedValues).size;
  return `${uniqueCount === 1 ? "Last renewed" : "Latest renewal"} ${fmtDateTime(summaryValue)}`;
}

export function isShareSafeLivePosition(position: TrackedPosition | SuggestedTrade): boolean {
  if (typeof position.share_safe_exact_live === "boolean") return position.share_safe_exact_live;
  const contractSymbol =
    position.exact_contract_symbol ??
    position.contract_symbol ??
    position.source_pick_snapshot?.contract_symbol ??
    null;
  if (!contractSymbol || position.source_pick_snapshot?.approximation_only) return false;
  const pricingSource = String(position.latest_review?.pricing_source || "").trim().toLowerCase();
  if (!["mid", "last_price", "spread_mid_exact", "spread_bid_ask_exact"].includes(pricingSource)) return false;
  if (position.latest_review?.current_option_price == null) return false;
  const reviewedAt = getReviewedAt(position);
  if (!reviewedAt) return false;
  const reviewedAtMs = new Date(reviewedAt).getTime();
  if (Number.isNaN(reviewedAtMs)) return false;
  return Date.now() - reviewedAtMs <= SHARE_SAFE_REVIEW_MAX_AGE_MINUTES * 60 * 1000;
}

export function getShareSafeReason(position: TrackedPosition | SuggestedTrade): string {
  if (position.share_safe_exact_live) {
    return position.source_pick_snapshot?.comparable_contract ? "Comparable exact live-priced" : "Exact live-priced";
  }
  if (position.share_safe_reason) return position.share_safe_reason;
  if (position.source_pick_snapshot?.approximation_only) return "Estimated from proxy contract pricing.";
  const contractSymbol =
    position.exact_contract_symbol ??
    position.contract_symbol ??
    position.source_pick_snapshot?.contract_symbol ??
    null;
  if (!contractSymbol) return "Missing exact contract symbol.";
  if (position.latest_review?.current_option_price == null) return "Live review pending.";
  return "Not share-safe yet.";
}

export function getEntryQuoteTimestamp(position: TrackedPosition | SuggestedTrade): string | null {
  return (
    position.source_pick_snapshot?.entry_quote_snapshot?.captured_at_et ??
    position.source_pick_snapshot?.quote_time_et ??
    position.source_pick_snapshot?.entry_quote_snapshot?.captured_at_utc ??
    position.source_pick_snapshot?.quote_time_utc ??
    null
  );
}

export function getOriginalLoggedExpiry(position: TrackedPosition | SuggestedTrade): string | null {
  return position.source_pick_snapshot?.original_logged_expiry ?? null;
}

export function getResolvedListedExpiry(position: TrackedPosition | SuggestedTrade): string | null {
  return (
    position.source_pick_snapshot?.resolved_listed_expiry ??
    position.source_pick_snapshot?.entry_quote_snapshot?.resolved_listed_expiry ??
    position.expiry ??
    null
  );
}

export function getLatestRecommendation(position: TrackedPosition | SuggestedTrade): string {
  return position.last_recommendation || position.latest_review?.recommendation || "\u2014";
}

export function formatSignalLabel(recommendation: string | null | undefined): string {
  const normalized = String(recommendation || "").trim().toUpperCase();
  if (normalized === "SELL") return "Close now";
  if (normalized === "HOLD") return "Hold";
  if (!normalized || normalized === "\u2014") return "Waiting";
  return fmtCompactLabel(normalized);
}

export function renderDualMetricCell(options: {
  primaryLabel: string;
  primaryValue: string;
  secondaryLabel: string;
  secondaryValue: string;
  primaryToneClass?: string;
  secondaryToneClass?: string;
}) {
  const {
    primaryLabel,
    primaryValue,
    secondaryLabel,
    secondaryValue,
    primaryToneClass = "text-text-0",
    secondaryToneClass = "text-text-1",
  } = options;
  return (
    <div className="space-y-1 leading-tight min-w-[112px]">
      <div className="text-xs">
        <span className="text-text-3 uppercase tracking-wide">{primaryLabel}</span>
        <div className={`font-mono text-sm ${primaryToneClass}`}>{primaryValue}</div>
      </div>
      <div className="text-xs">
        <span className="text-text-3 uppercase tracking-wide">{secondaryLabel}</span>
        <div className={`font-mono ${secondaryToneClass}`}>{secondaryValue}</div>
      </div>
    </div>
  );
}

export function renderOpenPriceCell(position: TrackedPosition | SuggestedTrade) {
  return renderDualMetricCell({
    primaryLabel: "Est. exit",
    primaryValue: fmtMoney(getCloseNowPrice(position)),
    secondaryLabel: "Mark value",
    secondaryValue: fmtMoney(getMarkPrice(position)),
  });
}

export function renderOpenPnlCell(position: TrackedPosition | SuggestedTrade) {
  const markPnl = getMarkPnlPct(position);
  const closeNowPnl = getCloseNowPnlPct(position);
  return renderDualMetricCell({
    primaryLabel: "Exit P&L",
    primaryValue: fmtPct(closeNowPnl),
    secondaryLabel: "Mark P&L",
    secondaryValue: fmtPct(markPnl),
    primaryToneClass: metricToneClass(closeNowPnl),
    secondaryToneClass: metricToneClass(markPnl),
  });
}

export function renderRealizedPnlCell(value?: number | null) {
  const hasValue = value != null && !Number.isNaN(value);
  const isPositive = hasValue && value > 0;
  const isNegative = hasValue && value < 0;
  const displayValue = hasValue ? fmtPct(value) : "\u2014";
  const exactValue = hasValue ? fmtPct(value, 4) : null;
  const precisionLabel =
    hasValue && exactValue && displayValue !== exactValue
      ? `${displayValue} (exact ${exactValue})`
      : displayValue;
  const toneClass = isPositive ? "text-green" : isNegative ? "text-red" : "text-text-2";
  const dotClass = isPositive
    ? "bg-green shadow-[0_0_8px_var(--green)]"
    : isNegative
      ? "bg-red shadow-[0_0_8px_var(--red)]"
      : "bg-border";
  const label = isPositive
    ? "Positive realized P&L"
    : isNegative
      ? "Negative realized P&L"
      : hasValue
        ? "Flat realized P&L"
        : "Realized P&L unavailable";

  return (
    <span
      className={`inline-flex min-w-[92px] items-center gap-1.5 font-mono text-sm font-semibold ${toneClass}`}
      aria-label={hasValue ? `${label}: ${precisionLabel}` : label}
      title={hasValue ? `${label}: ${precisionLabel}` : label}
    >
      <span className={`h-2 w-2 rounded-full ${dotClass}`} aria-hidden="true" />
      {displayValue}
    </span>
  );
}

export function renderQuoteCell(position: TrackedPosition | SuggestedTrade) {
  const source = fmtPricingSource(position.latest_review?.pricing_source);
  const context = quoteContextLabel(position.source_pick_snapshot);
  return (
    <div className="space-y-1 leading-tight min-w-[140px]">
      <div className="text-sm text-text-0">{source}</div>
      <div className="text-xs text-text-3">{context}</div>
    </div>
  );
}

export function renderPositionStatusCell(position: TrackedPosition | SuggestedTrade) {
  const actionState = getOpenReviewActionState(position);
  const warning = position.latest_review?.warnings?.[0] || null;
  const reviewedAt = getReviewedAt(position);
  const toneClass =
    actionState.tone === "danger"
      ? "text-red"
      : actionState.tone === "warning"
        ? "text-amber-300"
        : "text-text-0";
  const showDetail = actionState.id !== "hold";
  return (
    <div className="space-y-1 leading-tight min-w-[150px]">
      <div className={`text-sm font-semibold ${toneClass}`} title={actionState.detail}>
        {actionState.label}
      </div>
      <div className="text-xs text-text-3">{reviewedAt ? `Checked ${fmtDateTime(reviewedAt)}` : "Waiting for review"}</div>
      {showDetail ? <div className="text-xs text-text-2 truncate max-w-[220px]">{actionState.detail}</div> : null}
      {warning ? <div className="text-xs text-amber-300 truncate max-w-[220px]">{warning}</div> : null}
    </div>
  );
}

export function renderClosedStatusCell(position: TrackedPosition | SuggestedTrade) {
  const policyState = getCurrentPolicyReplayState(position);
  const policyToneClass =
    policyState.tone === "live"
      ? "text-green"
      : policyState.tone === "warning"
        ? "text-amber-300"
        : "text-text-3";

  return (
    <div className="space-y-1 leading-tight min-w-[132px]">
      <div className="text-sm font-semibold text-text-0">Closed</div>
      <div className="text-xs text-text-3">{fmtDate(position.closed_at)}</div>
      <div className={`text-xs ${policyToneClass}`} title={policyState.detail}>
        {policyState.label}
      </div>
    </div>
  );
}

export function renderReviewedCell(position: TrackedPosition | SuggestedTrade) {
  return renderDualMetricCell({
    primaryLabel: "Live",
    primaryValue: fmtDateTime(getReviewedAt(position)),
    secondaryLabel: "Entry snap",
    secondaryValue: fmtDateTime(getEntryQuoteTimestamp(position)),
    primaryToneClass: "text-text-0",
    secondaryToneClass: "text-text-1",
  });
}

export function renderExpiryCell(position: TrackedPosition | SuggestedTrade) {
  const resolved = getResolvedListedExpiry(position);
  const original = getOriginalLoggedExpiry(position);
  const secondary =
    original && resolved && original !== resolved
      ? `Logged ${fmtDate(original)}`
      : original && resolved
        ? "Exact expiry match"
        : resolved
          ? "Listed expiry"
          : original
            ? "Logged expiry"
            : "\u2014";
  return (
    <div className="space-y-1 leading-tight min-w-[118px]">
      <div className="text-sm font-mono text-text-0">{fmtDate(resolved ?? original)}</div>
      <div className="text-xs text-text-3">{secondary}</div>
    </div>
  );
}

export type PositionWithScanSnapshot = TrackedPosition | SuggestedTrade | Partial<ScanPick>;
