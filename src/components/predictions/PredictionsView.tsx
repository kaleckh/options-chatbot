"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { RefreshCw, Timer, CheckCircle, BarChart3, DollarSign, Map, BriefcaseBusiness, Clipboard } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import Button from "@/components/ui/Button";
import { MetricGridSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
import {
  BreakdownTab,
  GradedTab,
  PendingTab,
  SectorsTab,
  SimTab,
} from "@/components/predictions/legacy-tabs";
import type {
  CloseSuggestedTradeRequest,
  CloseTrackedPositionRequest,
  CreateSuggestedTradeRequest,
  CreateTrackedPositionRequest,
  ExposureSnapshot,
  ForwardEvidenceReport,
  LiveTradePolicy,
  OptionsProfitStatus,
  PlaybookExitAudit,
  Prediction,
  ScanPick,
  ScanPlaybook,
  SectorSentiment,
  SuggestedTrade,
  TrackedPosition,
} from "@/lib/types";

const INDEX_TICKERS = new Set(["QQQ", "SPY", "IWM", "DIA", "XLK"]);
const LEGACY_PREDICTION_TABS = new Set(["pending", "graded", "breakdown", "sim", "sectors"]);
const COMMODITY_PLAYBOOK_ID = "ai_commodity_infra_observation";
const REQUEST_TIMEOUT_MS = 30000;
const POSITION_SYNC_INTERVAL_MS = 60000;
const SHARE_SAFE_REVIEW_MAX_AGE_MINUTES = 15;

function buildTimeoutError(label: string, timeoutMs: number): Error {
  return new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)}s.`);
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  label: string,
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw buildTimeoutError(label, timeoutMs);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function payloadErrorMessage(payload: unknown): string | null {
  if (
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    "error" in payload
  ) {
    return String((payload as { error?: unknown }).error || "Request failed.");
  }
  return null;
}

async function readJsonResponseOrThrow(res: Response, label: string): Promise<unknown> {
  const data = await res.json().catch(() => ({}));
  const errorMessage = payloadErrorMessage(data);
  if (!res.ok || errorMessage) {
    throw new Error(errorMessage || `${label} request failed with status ${res.status}`);
  }
  return data;
}

function parseNonnegativePriceInput(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function fmtMoney(value?: number | null, digits: number = 2): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `$${value.toFixed(digits)}`;
}

function fmtSignedMoney(value?: number | null, digits: number = 2): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `${value >= 0 ? "+" : "-"}$${Math.abs(value).toFixed(digits)}`;
}

function fmtPct(value?: number | null, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function fmtDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "\u2014";
}

type EntryDateFilterPreset = "all" | "today" | "yesterday" | "last7" | "custom";

function toLocalDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftLocalDate(days: number): string {
  const next = new Date();
  next.setHours(0, 0, 0, 0);
  next.setDate(next.getDate() + days);
  return toLocalDateInputValue(next);
}

function getEntryDateValue(value?: string | null): string | null {
  if (!value) return null;
  const normalized = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(normalized) ? normalized : null;
}

function isWeekendDateValue(value: string): boolean {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return false;
  const day = parsed.getDay();
  return day === 0 || day === 6;
}

function matchesEntryDateFilter(
  value: string | null,
  preset: EntryDateFilterPreset,
  customDate: string
): boolean {
  if (preset === "all") return true;
  if (!value) return false;
  if (preset === "today") return value === shiftLocalDate(0);
  if (preset === "yesterday") return value === shiftLocalDate(-1);
  if (preset === "last7") return value >= shiftLocalDate(-6) && value <= shiftLocalDate(0);
  if (preset === "custom") return customDate ? value === customDate : true;
  return true;
}

function entryDateFilterLabel(preset: EntryDateFilterPreset, customDate: string): string {
  if (preset === "today") return "today";
  if (preset === "yesterday") return "yesterday";
  if (preset === "last7") return "the last 7 days";
  if (preset === "custom" && customDate) return customDate;
  return "all entry dates";
}

function fmtDateTime(value?: string | null): string {
  if (!value) return "\u2014";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type TradeDateSource = {
  filled_at?: string | null;
  source_pick_snapshot?: Partial<ScanPick> | null;
};

function getTrustedTakenDateValue(position: TradeDateSource): string | null {
  const source = position.source_pick_snapshot || null;
  const candidates = [
    source?.entry_quote_snapshot?.captured_at_et,
    source?.quote_time_et,
    source?.entry_quote_snapshot?.captured_at_utc,
    source?.quote_time_utc,
    position.filled_at,
  ];

  for (const candidate of candidates) {
    const normalized = getEntryDateValue(candidate);
    if (normalized && !isWeekendDateValue(normalized)) return normalized;
  }
  return null;
}

function getRawTakenDateValue(position: TradeDateSource): string | null {
  return getEntryDateValue(position.filled_at);
}

function getTradeDateFilterValue(position: TradeDateSource): string | null {
  return getTrustedTakenDateValue(position) ?? getRawTakenDateValue(position);
}

function fmtTakenDate(position: TradeDateSource): string {
  const trustedDate = getTrustedTakenDateValue(position);
  if (trustedDate) return trustedDate;

  const rawDate = getRawTakenDateValue(position);
  if (!rawDate) return "\u2014";
  if (isWeekendDateValue(rawDate)) return `Weekend import ${rawDate}`;
  return rawDate;
}

function fmtStrike(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return fmtMoney(value, 0);
}

function fmtContractCoreLabel(position: {
  ticker: string;
  direction: "call" | "put";
  strike?: number | null;
  short_strike?: number | null;
  expiry?: string | null;
}): string {
  const strikeLabel = fmtStrike(position.strike);
  const shortStrikeLabel =
    position.short_strike != null && !Number.isNaN(position.short_strike)
      ? fmtStrike(position.short_strike)
      : null;
  const strikeBlock = shortStrikeLabel ? `${strikeLabel}/${shortStrikeLabel}` : strikeLabel;
  return `${position.ticker} ${position.direction.toUpperCase()} ${strikeBlock} ${fmtDate(position.expiry)}`;
}

function fmtContractLabel(position: {
  ticker: string;
  direction: "call" | "put";
  strike?: number | null;
  short_strike?: number | null;
  expiry?: string | null;
  contract_symbol?: string | null;
}): string {
  const coreLabel = fmtContractCoreLabel(position);
  if (position.contract_symbol) return `${coreLabel} | ${position.contract_symbol}`;
  return coreLabel;
}

type ContractDisplaySource = {
  id?: number;
  ticker: string;
  direction: "call" | "put";
  strike?: number | null;
  short_strike?: number | null;
  expiry?: string | null;
  contract_symbol?: string | null;
  filled_at?: string | null;
  source_pick_snapshot?: Partial<ScanPick> | null;
};

function getContractDisplayFields(position: ContractDisplaySource) {
  const source = position.source_pick_snapshot || null;
  return {
    ticker: position.ticker,
    direction: position.direction,
    strike:
      position.strike ??
      source?.strike ??
      source?.strike_est ??
      null,
    short_strike:
      position.short_strike ??
      source?.short_strike ??
      null,
    expiry: position.expiry ?? source?.expiry ?? null,
    contract_symbol:
      position.contract_symbol ??
      source?.contract_symbol ??
      null,
    short_contract_symbol: source?.short_contract_symbol ?? null,
    strategy_type: source?.strategy_type ?? "single_leg",
  };
}

function buildContractSignature(position: ContractDisplaySource): string {
  const fields = getContractDisplayFields(position);
  return JSON.stringify([
    fields.ticker,
    fields.direction,
    fields.expiry,
    fields.strategy_type,
    fields.strike,
    fields.short_strike,
    fields.contract_symbol,
    fields.short_contract_symbol,
  ]);
}

function getReviewedAt(position: TrackedPosition | SuggestedTrade): string | null {
  return position.share_reviewed_at ?? position.latest_review?.reviewed_at ?? position.last_reviewed_at ?? null;
}

function getCollectionReviewSummary(items: Array<TrackedPosition | SuggestedTrade>): string | null {
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

function isShareSafeLivePosition(position: TrackedPosition | SuggestedTrade): boolean {
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

function getShareSafeReason(position: TrackedPosition | SuggestedTrade): string {
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

function isCommodityLanePosition(position: TrackedPosition | SuggestedTrade): boolean {
  const source = position.source_pick_snapshot || null;
  const values = [
    source?.ai_commodity_bucket,
    source?.cohort_id,
    source?.playbook,
    source?.playbook_label,
    source?.strategy_label,
    source?.strategy_comment,
  ];

  return values.some((value) => {
    const normalized = String(value || "").trim().toLowerCase();
    return (
      normalized === COMMODITY_PLAYBOOK_ID ||
      normalized.includes("ai_commodity") ||
      normalized.includes("commodity")
    );
  });
}

function getSpreadWidth(position: ContractDisplaySource): number | null {
  const { strike, short_strike } = getContractDisplayFields(position);
  if (strike == null || short_strike == null) return null;
  const width = Math.abs(short_strike - strike);
  return width > 0 ? width : null;
}

function fmtTargetLabel(position: ContractDisplaySource, entryPrice?: number | null, targetPct?: number | null): string {
  if (entryPrice == null || entryPrice <= 0 || targetPct == null || Number.isNaN(targetPct)) return "\u2014";
  const spreadWidth = getSpreadWidth(position);
  const rawTargetPrice = entryPrice * (1 + targetPct / 100);
  const targetPrice = spreadWidth != null ? Math.min(rawTargetPrice, spreadWidth) : rawTargetPrice;
  return `+${targetPct}% (${fmtMoney(targetPrice)})`;
}

function fmtStopLabel(entryPrice?: number | null, stopPct?: number | null): string {
  if (entryPrice == null || entryPrice <= 0 || stopPct == null || Number.isNaN(stopPct)) return "\u2014";
  const rawStopPrice = entryPrice * (1 - stopPct / 100);
  const stopPrice = Math.max(0, rawStopPrice);
  if (rawStopPrice < 0) return `Full loss (${fmtMoney(stopPrice)})`;
  return `-${stopPct}% (${fmtMoney(stopPrice)})`;
}

function fmtPricingSource(value?: string | null): string {
  if (!value) return "\u2014";
  if (value === "mid") return "Bid/ask midpoint";
  if (value === "spread_mid_exact") return "Exact spread midpoint";
  if (value === "spread_bid_ask_exact") return "Exact spread bid/ask";
  if (value === "spread_mid_approx") return "Comparable spread midpoint";
  if (value === "last_price") return "Last trade only";
  if (value === "expired") return "Expired";
  if (value === "unavailable") return "Unpriced";
  return value;
}

function fmtTruthSource(value?: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "historical_imported_daily") return "Imported daily validation";
  if (normalized === "historical_imported") return "Imported historical validation";
  if (normalized === "synthetic" || normalized === "synthetic_only") return "Synthetic research-only";
  return value ? `Unknown truth source (${value})` : "Unknown truth source";
}

function fmtCompactLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ");
}

function fmtUpperLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ").toUpperCase();
}

function contractQualityLabel(pick?: Partial<ScanPick> | null): string {
  const selectionSource = String(pick?.selection_source || "").trim().toLowerCase();
  const promotionClass = String(pick?.promotion_class || "").trim().toLowerCase();
  if (String(pick?.contract_symbol || "").trim()) {
    if (selectionSource.includes("archived_exact") || selectionSource.includes("exact_contract")) {
      return "Exact contract";
    }
    if (selectionSource.includes("model_target") || promotionClass.includes("bootstrap") || promotionClass.includes("sparse")) {
      return "Model exact fallback";
    }
    if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
      return "Nearest listed";
    }
    return "Exact symbol recorded";
  }
  if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
    return "Nearest listed";
  }
  return "Contract missing";
}

function quoteContextLabel(pick?: Partial<ScanPick> | null): string {
  const basis = fmtCompactLabel(pick?.quote_basis);
  const freshness = fmtCompactLabel(pick?.quote_freshness_status);
  if (basis === "\u2014" && freshness === "\u2014") return "\u2014";
  if (basis === "\u2014") return freshness;
  if (freshness === "\u2014") return basis;
  return `${basis} / ${freshness}`;
}

function fmtRiskUpsideLabel(pick?: Partial<ScanPick> | null): string {
  const risk = pick?.risk_tier;
  const upside = pick?.upside_tier;
  if (risk == null && upside == null) return "\u2014";
  return `R${risk ?? "\u2014"} / U${upside ?? "\u2014"}`;
}

function calcOptionPnlPct(entryPrice?: number | null, exitPrice?: number | null): number | null {
  if (entryPrice == null || exitPrice == null || entryPrice <= 0) return null;
  return ((exitPrice / entryPrice) - 1) * 100;
}

function calcNetOptionPnlPct(options: {
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
  if (capitalAtRiskUsd <= 0) return null;

  const grossPnlUsd = (exitPrice - entryPrice) * contracts * 100;
  const netPnlUsd = grossPnlUsd - feeTotalUsd;
  return (netPnlUsd / capitalAtRiskUsd) * 100;
}

function metricToneClass(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "text-text-2";
  if (value > 0) return "text-green";
  if (value < 0) return "text-red";
  return "text-text-2";
}

function getEntryExecutionPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.latest_review?.entry_execution_price ??
    position.entry_execution_price ??
    position.source_pick_snapshot?.entry_execution_price ??
    position.entry_option_price ??
    null
  );
}

function getMarkPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return position.latest_review?.current_option_price ?? position.last_option_price ?? null;
}

function getCloseNowPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.latest_review?.exit_execution_price ??
    position.exit_execution_price ??
    position.exit_option_price ??
    position.latest_review?.current_option_price ??
    position.last_option_price ??
    null
  );
}

function getMarkPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
  return calcOptionPnlPct(getEntryExecutionPrice(position), getMarkPrice(position));
}

function calcOptionPnlUsd(position: TrackedPosition | SuggestedTrade, exitPrice?: number | null): number | null {
  const entryPrice = getEntryExecutionPrice(position);
  const resolvedExitPrice = exitPrice ?? getCloseNowPrice(position);
  const contractCount = Number(position.contracts || 0);
  if (
    entryPrice == null ||
    resolvedExitPrice == null ||
    Number.isNaN(entryPrice) ||
    Number.isNaN(resolvedExitPrice) ||
    entryPrice <= 0 ||
    contractCount <= 0
  ) {
    return null;
  }
  const grossPnlUsd = (resolvedExitPrice - entryPrice) * contractCount * 100;
  const feeTotalUsd =
    position.latest_review?.fee_total_usd ??
    position.fee_total_usd ??
    0;
  return grossPnlUsd - feeTotalUsd;
}

function getCloseNowPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
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

function getCloseNowPnlUsd(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.latest_review?.net_pnl_usd ??
    position.net_pnl_usd ??
    position.latest_review?.gross_pnl_usd ??
    position.gross_pnl_usd ??
    calcOptionPnlUsd(position) ??
    null
  );
}

function getRealizedPnlUsd(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.net_pnl_usd ??
    position.latest_review?.net_pnl_usd ??
    calcOptionPnlUsd(position, getRealizedExitPrice(position)) ??
    position.gross_pnl_usd ??
    position.latest_review?.gross_pnl_usd ??
    null
  );
}

function getRealizedExitPrice(position: TrackedPosition | SuggestedTrade): number | null {
  return (
    position.exit_execution_price ??
    position.exit_option_price ??
    position.latest_review?.exit_execution_price ??
    position.latest_review?.current_option_price ??
    null
  );
}

function calcWeightedPositionPnlPct<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlUsd: (position: T) => number | null
): number | null {
  const stats = positions.reduce(
    (acc, position) => {
      const pnlUsd = getPnlUsd(position);
      const entryExecutionPrice = getEntryExecutionPrice(position);
      const contractCount = Number(position.contracts || 0);
      if (
        pnlUsd == null ||
        entryExecutionPrice == null ||
        Number.isNaN(pnlUsd) ||
        Number.isNaN(entryExecutionPrice) ||
        entryExecutionPrice <= 0 ||
        contractCount <= 0
      ) {
        return acc;
      }
      acc.pnlUsd += pnlUsd;
      acc.entryCostUsd += entryExecutionPrice * contractCount * 100;
      return acc;
    },
    { pnlUsd: 0, entryCostUsd: 0 }
  );

  return stats.entryCostUsd > 0
    ? (stats.pnlUsd / stats.entryCostUsd) * 100
    : null;
}

function calcAveragePositionPnlPct<T extends TrackedPosition | SuggestedTrade>(
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

function calcTotalPositionPnlUsd<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlUsd: (position: T) => number | null
): number | null {
  const values = positions
    .map((position) => getPnlUsd(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  return values.length > 0
    ? values.reduce((sum, value) => sum + value, 0)
    : null;
}

function getPositionCostRiskUsd(position: TrackedPosition | SuggestedTrade): number | null {
  const entryPrice = getEntryExecutionPrice(position);
  const contractCount = Number(position.contracts || 0);
  if (entryPrice == null || Number.isNaN(entryPrice) || entryPrice <= 0 || contractCount <= 0) return null;
  return entryPrice * contractCount * 100;
}

function calcTotalPositionCostRiskUsd<T extends TrackedPosition | SuggestedTrade>(positions: T[]): number | null {
  const values = positions
    .map((position) => getPositionCostRiskUsd(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null;
}

function countByLabel<T>(items: T[], getLabel: (item: T) => string | null | undefined): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    const label = String(getLabel(item) || "").trim();
    if (!label) return acc;
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
}

function topCountSummary(counts: Record<string, number>, fallback = "None"): string {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!entries.length) return fallback;
  return `${entries[0][0]} x${entries[0][1]}`;
}

function getConcentrationWarning(positions: Array<TrackedPosition | SuggestedTrade>): string | null {
  const tickerCounts = countByLabel(positions, (position) => position.ticker);
  const sectorCounts = countByLabel(positions, (position) => position.source_pick_snapshot?.sector);
  const spreadCounts = countByLabel(positions, (position) => buildContractSignature(position));
  const topTicker = Object.entries(tickerCounts).sort((a, b) => b[1] - a[1])[0];
  const topSector = Object.entries(sectorCounts).sort((a, b) => b[1] - a[1])[0];
  const topSpread = Object.entries(spreadCounts).sort((a, b) => b[1] - a[1])[0];
  if (topSpread?.[1] > 1) return `${topSpread[1]} open rows share one exact contract/spread signature.`;
  if (topTicker?.[1] > 2) return `${topTicker[0]} has ${topTicker[1]} open tracked positions.`;
  if (topSector?.[1] > 3) return `${topSector[0]} has ${topSector[1]} open tracked positions.`;
  return null;
}

function getPnlExtremes<T extends TrackedPosition | SuggestedTrade>(
  positions: T[],
  getPnlPct: (position: T) => number | null
): { best: number | null; worst: number | null } {
  const values = positions
    .map((position) => getPnlPct(position))
    .filter((value): value is number => value != null && !Number.isNaN(value));
  if (!values.length) return { best: null, worst: null };
  return {
    best: Math.max(...values),
    worst: Math.min(...values),
  };
}

function getRealizedPnlPct(position: TrackedPosition | SuggestedTrade): number | null {
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

function getEntryQuoteTimestamp(position: TrackedPosition | SuggestedTrade): string | null {
  return (
    position.source_pick_snapshot?.entry_quote_snapshot?.captured_at_et ??
    position.source_pick_snapshot?.quote_time_et ??
    position.source_pick_snapshot?.entry_quote_snapshot?.captured_at_utc ??
    position.source_pick_snapshot?.quote_time_utc ??
    null
  );
}

function getOriginalLoggedExpiry(position: TrackedPosition | SuggestedTrade): string | null {
  return position.source_pick_snapshot?.original_logged_expiry ?? null;
}

function getResolvedListedExpiry(position: TrackedPosition | SuggestedTrade): string | null {
  return (
    position.source_pick_snapshot?.resolved_listed_expiry ??
    position.source_pick_snapshot?.entry_quote_snapshot?.resolved_listed_expiry ??
    position.expiry ??
    null
  );
}

function renderDualMetricCell(options: {
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

function renderOpenPriceCell(position: TrackedPosition | SuggestedTrade) {
  return renderDualMetricCell({
    primaryLabel: "Paper value",
    primaryValue: fmtMoney(getMarkPrice(position)),
    secondaryLabel: "Est. exit",
    secondaryValue: fmtMoney(getCloseNowPrice(position)),
  });
}

function renderOpenPnlCell(position: TrackedPosition | SuggestedTrade) {
  const markPnl = getMarkPnlPct(position);
  const closeNowPnl = getCloseNowPnlPct(position);
  return renderDualMetricCell({
    primaryLabel: "Paper P&L",
    primaryValue: fmtPct(markPnl),
    secondaryLabel: "Exit P&L",
    secondaryValue: fmtPct(closeNowPnl),
    primaryToneClass: metricToneClass(markPnl),
    secondaryToneClass: metricToneClass(closeNowPnl),
  });
}

function renderRealizedPnlCell(value?: number | null) {
  const hasValue = value != null && !Number.isNaN(value);
  const isPositive = hasValue && value > 0;
  const isNegative = hasValue && value < 0;
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
      aria-label={hasValue ? `${label}: ${fmtPct(value)}` : label}
      title={label}
    >
      <span className={`h-2 w-2 rounded-full ${dotClass}`} aria-hidden="true" />
      {hasValue ? fmtPct(value) : "\u2014"}
    </span>
  );
}

function renderQuoteCell(position: TrackedPosition | SuggestedTrade) {
  const source = fmtPricingSource(position.latest_review?.pricing_source);
  const context = quoteContextLabel(position.source_pick_snapshot);
  return (
    <div className="space-y-1 leading-tight min-w-[140px]">
      <div className="text-sm text-text-0">{source}</div>
      <div className="text-xs text-text-3">{context}</div>
    </div>
  );
}

function renderPositionStatusCell(position: TrackedPosition | SuggestedTrade) {
  const recommendation = getLatestRecommendation(position);
  const warning = position.latest_review?.warnings?.[0] || null;
  const proofLabel = position.proof_eligible
    ? "proof"
    : fmtCompactLabel(position.proof_class || position.proof_ineligibility_reason);
  return (
    <div className="space-y-1 leading-tight min-w-[150px]">
      <div className={recommendation === "SELL" ? "text-sm font-semibold text-red" : "text-sm font-semibold text-text-0"}>
        {recommendation}
      </div>
      <div className="text-xs text-text-3">{proofLabel}</div>
      {warning ? <div className="text-xs text-amber-300 truncate max-w-[220px]">{warning}</div> : null}
    </div>
  );
}

function getLatestRecommendation(position: TrackedPosition | SuggestedTrade): string {
  return position.last_recommendation || position.latest_review?.recommendation || "\u2014";
}

function renderReviewedCell(position: TrackedPosition | SuggestedTrade) {
  return renderDualMetricCell({
    primaryLabel: "Live",
    primaryValue: fmtDateTime(getReviewedAt(position)),
    secondaryLabel: "Entry snap",
    secondaryValue: fmtDateTime(getEntryQuoteTimestamp(position)),
    primaryToneClass: "text-text-0",
    secondaryToneClass: "text-text-1",
  });
}

function renderExpiryCell(position: TrackedPosition | SuggestedTrade) {
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

export default function PredictionsView() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sectors, setSectors] = useState<SectorSentiment[]>([]);
  const [scanPicks, setScanPicks] = useState<ScanPick[]>([]);
  const [scanPolicy, setScanPolicy] = useState<LiveTradePolicy | null>(null);
  const [scanPolicyError, setScanPolicyError] = useState<string | null>(null);
  const [scanDecisionCounts, setScanDecisionCounts] = useState<Record<string, number> | null>(null);
  const [guardrailDecisionCounts, setGuardrailDecisionCounts] = useState<Record<string, number> | null>(null);
  const [scanExitAudit, setScanExitAudit] = useState<PlaybookExitAudit | null>(null);
  const [scanCandidateCount, setScanCandidateCount] = useState(0);
  const [forwardEvidence, setForwardEvidence] = useState<ForwardEvidenceReport | null>(null);
  const [optionsProfitStatus, setOptionsProfitStatus] = useState<OptionsProfitStatus | null>(null);
  const [truthHealthError, setTruthHealthError] = useState<string | null>(null);
  const [useRecommendedPolicy, setUseRecommendedPolicy] = useState(false);
  const [scanPlaybook, setScanPlaybook] = useState<string>("bullish_pullback_observation");
  const [showBlockedIdeas, setShowBlockedIdeas] = useState(false);
  const [availablePlaybooks, setAvailablePlaybooks] = useState<ScanPlaybook[]>([]);
  const [exposureSnapshot, setExposureSnapshot] = useState<ExposureSnapshot | null>(null);
  const [openPositions, setOpenPositions] = useState<TrackedPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<TrackedPosition[]>([]);
  const [openSuggestedTrades, setOpenSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [closedSuggestedTrades, setClosedSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [activeSubTab, setActiveSubTab] = useState("positions");
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [predictionsLoaded, setPredictionsLoaded] = useState(false);
  const [sectorsLoaded, setSectorsLoaded] = useState(false);
  const [predictionsError, setPredictionsError] = useState<string | null>(null);
  const [sectorsError, setSectorsError] = useState<string | null>(null);
  const [positionsLoaded, setPositionsLoaded] = useState(false);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [suggestedTradesLoaded, setSuggestedTradesLoaded] = useState(false);
  const [suggestedTradesLoading, setSuggestedTradesLoading] = useState(false);
  const [suggestedTradesError, setSuggestedTradesError] = useState<string | null>(null);
  const [selectedPick, setSelectedPick] = useState<ScanPick | null>(null);
  const [fillPrice, setFillPrice] = useState("");
  const [contracts, setContracts] = useState("1");
  const [takeNotes, setTakeNotes] = useState("");
  const [takingTrade, setTakingTrade] = useState(false);
  const [savingSuggestedTrade, setSavingSuggestedTrade] = useState(false);
  const [showLegacyTabs, setShowLegacyTabs] = useState(false);
  const [positionsView, setPositionsView] = useState<"open" | "closed">("open");
  const [reviewingIds, setReviewingIds] = useState<number[]>([]);
  const [closingPosition, setClosingPosition] = useState<TrackedPosition | null>(null);
  const [exitPrice, setExitPrice] = useState("");
  const [closeNotes, setCloseNotes] = useState("");
  const [closingId, setClosingId] = useState<number | null>(null);
  const [suggestedTradesView, setSuggestedTradesView] = useState<"open" | "closed">("open");
  const [reviewingSuggestedTradeIds, setReviewingSuggestedTradeIds] = useState<number[]>([]);
  const [closingSuggestedTrade, setClosingSuggestedTrade] = useState<SuggestedTrade | null>(null);
  const [suggestedExitPrice, setSuggestedExitPrice] = useState("");
  const [suggestedCloseNotes, setSuggestedCloseNotes] = useState("");
  const [closingSuggestedTradeId, setClosingSuggestedTradeId] = useState<number | null>(null);
  const toast = useToast();
  const { guard } = useSubmitGuard();
  const predictionDataRequestIdRef = useRef(0);
  const scanRequestIdRef = useRef(0);
  const truthHealthRequestIdRef = useRef(0);
  const positionsRequestIdRef = useRef(0);
  const suggestedTradesRequestIdRef = useRef(0);

  const mergeTrackedPosition = useCallback((position: TrackedPosition) => {
    setOpenPositions((prev) =>
      position.status === "open"
        ? [position, ...prev.filter((item) => item.id !== position.id)]
        : prev.filter((item) => item.id !== position.id)
    );
    setClosedPositions((prev) =>
      position.status === "closed"
        ? [position, ...prev.filter((item) => item.id !== position.id)]
        : prev.filter((item) => item.id !== position.id)
    );
  }, []);

  const mergeSuggestedTrade = useCallback((trade: SuggestedTrade) => {
    setOpenSuggestedTrades((prev) =>
      trade.status === "open"
        ? [trade, ...prev.filter((item) => item.id !== trade.id)]
        : prev.filter((item) => item.id !== trade.id)
    );
    setClosedSuggestedTrades((prev) =>
      trade.status === "closed"
        ? [trade, ...prev.filter((item) => item.id !== trade.id)]
        : prev.filter((item) => item.id !== trade.id)
    );
  }, []);

  const applyReviewedPositions = useCallback((reviewed: TrackedPosition[]) => {
    const reviewedById = new globalThis.Map<number, TrackedPosition>(
      reviewed.map((position) => [position.id, position])
    );
    const closedReviewed = reviewed.filter((position) => position.status === "closed");
    const closedReviewedIds = new Set(closedReviewed.map((position) => position.id));
    setOpenPositions((prev) =>
      prev
        .map((position) => reviewedById.get(position.id) ?? position)
        .filter((position) => position.status === "open")
    );
    if (closedReviewed.length > 0) {
      setClosedPositions((prev) => [
        ...closedReviewed,
        ...prev.filter((position) => !closedReviewedIds.has(position.id)),
      ]);
    }
  }, []);

  const applyReviewedSuggestedTrades = useCallback((reviewed: SuggestedTrade[]) => {
    const reviewedById = new globalThis.Map<number, SuggestedTrade>(
      reviewed.map((trade) => [trade.id, trade])
    );
    const closedReviewed = reviewed.filter((trade) => trade.status === "closed");
    const closedReviewedIds = new Set(closedReviewed.map((trade) => trade.id));
    setOpenSuggestedTrades((prev) =>
      prev
        .map((trade) => reviewedById.get(trade.id) ?? trade)
        .filter((trade) => trade.status === "open")
    );
    if (closedReviewed.length > 0) {
      setClosedSuggestedTrades((prev) => [
        ...closedReviewed,
        ...prev.filter((trade) => !closedReviewedIds.has(trade.id)),
      ]);
    }
  }, []);

  const fetchPredictionsData = useCallback(async ({
    includePredictions = true,
    includeSectors = false,
    showToast = false,
  }: {
    includePredictions?: boolean;
    includeSectors?: boolean;
    showToast?: boolean;
  } = {}) => {
    const requestId = ++predictionDataRequestIdRef.current;
    const isCurrentRequest = () => requestId === predictionDataRequestIdRef.current;
    const errors: string[] = [];

    if (includePredictions) {
      try {
        const predRes = await fetchWithTimeout("/api/predictions", undefined, "Prediction history");
        const predData = await readJsonResponseOrThrow(predRes, "Prediction history");
        if (!Array.isArray(predData)) {
          throw new Error("Prediction history response was not a list.");
        }
        if (!isCurrentRequest()) return;
        setPredictions(predData as Prediction[]);
        setPredictionsLoaded(true);
        setPredictionsError(null);
      } catch (err) {
        if (!isCurrentRequest()) return;
        const message = err instanceof Error ? err.message : "Failed to load prediction history.";
        console.error("Failed to load prediction history:", err);
        setPredictions([]);
        setPredictionsLoaded(false);
        setPredictionsError(message);
        errors.push(message);
      }
    }

    if (includeSectors) {
      try {
        const sectorRes = await fetchWithTimeout("/api/sectors", undefined, "Sector data");
        const sectorData = await readJsonResponseOrThrow(sectorRes, "Sector data");
        if (!Array.isArray(sectorData)) {
          throw new Error("Sector data response was not a list.");
        }
        if (!isCurrentRequest()) return;
        setSectors(sectorData as SectorSentiment[]);
        setSectorsLoaded(true);
        setSectorsError(null);
      } catch (err) {
        if (!isCurrentRequest()) return;
        const message = err instanceof Error ? err.message : "Failed to load sector data.";
        console.error("Failed to load sector data:", err);
        setSectors([]);
        setSectorsLoaded(false);
        setSectorsError(message);
        errors.push(message);
      }
    }

    if (showToast && errors.length > 0) {
      toast.error(errors.join(" "));
    }
  }, [toast]);

  const fetchScanner = useCallback(async (showToast = false) => {
    const requestId = ++scanRequestIdRef.current;
    const isCurrentRequest = () => requestId === scanRequestIdRef.current;
    setScanLoading(true);
    try {
      const res = await fetchWithTimeout("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          n_picks: 2,
          use_recommended_policy: useRecommendedPolicy,
          playbook: scanPlaybook,
          include_blocked_policy_picks: showBlockedIdeas,
          include_blocked_guardrail_picks: showBlockedIdeas,
          enforce_portfolio_caps: false,
        }),
      }, "Live scan");
      const data = await res.json();
      if (!isCurrentRequest()) return;
      if (!res.ok || data.error) {
        throw new Error(data.error || `Scan request failed with status ${res.status}`);
      }
      setScanPicks(data.picks || []);
      setScanPolicy(data.policy || null);
      setScanPolicyError(data.policy_error || null);
      setScanExitAudit(data.playbook_exit_audit || null);
      setScanDecisionCounts(data.policy_decision_counts || null);
      setGuardrailDecisionCounts(data.guardrail_decision_counts || null);
      setScanCandidateCount(Number(data.candidate_count || (data.picks || []).length || 0));
      setAvailablePlaybooks(data.playbooks || []);
      setExposureSnapshot(data.exposure_snapshot || null);
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load scan picks:", err);
      const message = err instanceof Error ? err.message : "Failed to load scan picks.";
      setScanPicks([]);
      setScanPolicy(null);
      setScanPolicyError(message);
      setScanExitAudit(null);
      setScanDecisionCounts(null);
      setGuardrailDecisionCounts(null);
      setScanCandidateCount(0);
      setAvailablePlaybooks([]);
      setExposureSnapshot(null);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setScanLoading(false);
      }
    }
  }, [showBlockedIdeas, toast, scanPlaybook, useRecommendedPolicy]);

  const fetchTruthHealth = useCallback(async (showToast = false) => {
    const requestId = ++truthHealthRequestIdRef.current;
    const isCurrentRequest = () => requestId === truthHealthRequestIdRef.current;
    try {
      const [forwardRes, statusRes] = await Promise.all([
        fetchWithTimeout("/api/backtest/forward-evidence", undefined, "Forward evidence report"),
        fetchWithTimeout("/api/options-profit/status", undefined, "Options profit status"),
      ]);
      const forwardData = await forwardRes.json();
      const statusData = await statusRes.json();
      if (!isCurrentRequest()) return;
      if (!forwardRes.ok || forwardData.error) {
        throw new Error(forwardData.error || `Forward evidence request failed with status ${forwardRes.status}`);
      }
      if (!statusRes.ok || statusData.error) {
        throw new Error(statusData.error || `Options profit status request failed with status ${statusRes.status}`);
      }
      setForwardEvidence((forwardData || null) as ForwardEvidenceReport | null);
      setOptionsProfitStatus((statusData || null) as OptionsProfitStatus | null);
      setTruthHealthError(null);
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load truth health:", err);
      const message = err instanceof Error ? err.message : "Failed to load truth health.";
      setForwardEvidence(null);
      setOptionsProfitStatus(null);
      setTruthHealthError(message);
      if (showToast) {
        toast.error(message);
      }
    }
  }, [toast]);

  const refreshScannerSurface = useCallback(async (showToast = false) => {
    await Promise.all([
      fetchScanner(showToast),
      fetchTruthHealth(showToast),
    ]);
  }, [fetchScanner, fetchTruthHealth]);

  const fetchPositions = useCallback(async (showToast = false) => {
    const requestId = ++positionsRequestIdRef.current;
    const isCurrentRequest = () => requestId === positionsRequestIdRef.current;
    setPositionsLoading(true);
    try {
      const res = await fetchWithTimeout("/api/positions?status=all&grouped=1", undefined, "Tracked positions");
      const data = await res.json();
      if (!isCurrentRequest()) return;
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to load tracked positions");
      }
      const nextOpenPositions = (data.open || []) as TrackedPosition[];
      setOpenPositions(nextOpenPositions);
      setClosedPositions((data.closed || []) as TrackedPosition[]);
      setPositionsLoaded(true);
      setPositionsError(null);
      let reviewFailed = false;
      if (nextOpenPositions.length > 0) {
        try {
          const reviewRes = await fetchWithTimeout("/api/positions/review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position_ids: nextOpenPositions.map((position) => position.id) }),
          }, "Tracked position review");
          const reviewData = await reviewRes.json();
          if (!reviewRes.ok || reviewData.error) {
            throw new Error(reviewData.error || "Failed to review tracked positions");
          }
          if (!isCurrentRequest()) return;
          applyReviewedPositions((reviewData.positions || []) as TrackedPosition[]);
        } catch (reviewErr) {
          if (!isCurrentRequest()) return;
          reviewFailed = true;
          const message = reviewErr instanceof Error ? reviewErr.message : "Failed to review tracked positions.";
          setPositionsError(`Tracked positions loaded, but repricing failed: ${message}`);
          if (showToast) {
            toast.error(`Tracked positions loaded, but repricing failed: ${message}`);
          }
        }
      }
      if (showToast && !reviewFailed) {
        toast.success(nextOpenPositions.length > 0 ? "Tracked positions refreshed and repriced." : "Tracked positions refreshed.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load tracked positions:", err);
      const message = err instanceof Error ? err.message : "Failed to load tracked positions.";
      setOpenPositions([]);
      setClosedPositions([]);
      setPositionsError(message);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setPositionsLoading(false);
      }
    }
  }, [applyReviewedPositions, toast]);

  const fetchSuggestedTrades = useCallback(async (showToast = false) => {
    const requestId = ++suggestedTradesRequestIdRef.current;
    const isCurrentRequest = () => requestId === suggestedTradesRequestIdRef.current;
    setSuggestedTradesLoading(true);
    try {
      const res = await fetchWithTimeout("/api/suggested-trades?status=all&grouped=1", undefined, "Suggested trades");
      const data = await res.json();
      if (!isCurrentRequest()) return;
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to load suggested trades");
      }
      const nextOpenTrades = (data.open || []) as SuggestedTrade[];
      setOpenSuggestedTrades(nextOpenTrades);
      setClosedSuggestedTrades((data.closed || []) as SuggestedTrade[]);
      setSuggestedTradesLoaded(true);
      setSuggestedTradesError(null);
      let reviewFailed = false;
      if (nextOpenTrades.length > 0) {
        try {
          const reviewRes = await fetchWithTimeout("/api/suggested-trades/review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position_ids: nextOpenTrades.map((trade) => trade.id) }),
          }, "Suggested trade review");
          const reviewData = await reviewRes.json();
          if (!reviewRes.ok || reviewData.error) {
            throw new Error(reviewData.error || "Failed to review suggested trades");
          }
          if (!isCurrentRequest()) return;
          applyReviewedSuggestedTrades((reviewData.trades || []) as SuggestedTrade[]);
        } catch (reviewErr) {
          if (!isCurrentRequest()) return;
          reviewFailed = true;
          const message = reviewErr instanceof Error ? reviewErr.message : "Failed to review suggested trades.";
          setSuggestedTradesError(`Suggested trades loaded, but repricing failed: ${message}`);
          if (showToast) {
            toast.error(`Suggested trades loaded, but repricing failed: ${message}`);
          }
        }
      }
      if (showToast && !reviewFailed) {
        toast.success(nextOpenTrades.length > 0 ? "Suggested trades refreshed and repriced." : "Suggested trades refreshed.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load suggested trades:", err);
      const message = err instanceof Error ? err.message : "Failed to load suggested trades.";
      setOpenSuggestedTrades([]);
      setClosedSuggestedTrades([]);
      setSuggestedTradesError(message);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setSuggestedTradesLoading(false);
      }
    }
  }, [applyReviewedSuggestedTrades, toast]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        await fetchPositions(false);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, [fetchPositions]);

  useEffect(() => {
    if (!LEGACY_PREDICTION_TABS.has(activeSubTab)) return;
    const includePredictions = !predictionsLoaded;
    const includeSectors = activeSubTab === "sectors" && !sectorsLoaded;
    if (!includePredictions && !includeSectors) return;
    void fetchPredictionsData({ includePredictions, includeSectors });
  }, [activeSubTab, fetchPredictionsData, predictionsLoaded, sectorsLoaded]);

  useEffect(() => {
    if (activeSubTab !== "scanner") return;
    void refreshScannerSurface(false);
  }, [activeSubTab, refreshScannerSurface]);

  useEffect(() => {
    if (loading || activeSubTab !== "positions" || positionsLoaded) return;
    void fetchPositions(false);
  }, [activeSubTab, fetchPositions, loading, positionsLoaded]);

  useEffect(() => {
    if (activeSubTab !== "suggestions" || suggestedTradesLoaded) return;
    void fetchSuggestedTrades(false);
  }, [activeSubTab, fetchSuggestedTrades, suggestedTradesLoaded]);

  useEffect(() => {
    if (!showLegacyTabs && (LEGACY_PREDICTION_TABS.has(activeSubTab) || activeSubTab === "suggestions")) {
      setPositionsView("open");
      setActiveSubTab("positions");
    }
  }, [activeSubTab, showLegacyTabs]);

  useEffect(() => {
    if (activeSubTab !== "positions") return;
    const intervalId = window.setInterval(() => {
      void fetchPositions(false);
    }, POSITION_SYNC_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeSubTab, fetchPositions]);

  useEffect(() => {
    if (activeSubTab !== "suggestions") return;
    const intervalId = window.setInterval(() => {
      void fetchSuggestedTrades(false);
    }, POSITION_SYNC_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeSubTab, fetchSuggestedTrades]);

  const openTakeTrade = useCallback((pick: ScanPick) => {
    setSelectedPick(pick);
    const premium = pick.premium ?? pick.est_premium ?? 0;
    setFillPrice(premium > 0 ? premium.toFixed(2) : "");
    setContracts("1");
    const defaultReasons = [
      ...(pick.policy_fit_reasons || []),
      ...(pick.guardrail_reasons || []),
    ];
    const defaultNote = pick.policy_decision === "watch" || pick.guardrail_decision === "caution"
      ? `Cautious entry: ${defaultReasons.join(" | ") || "manual review"}`
      : "";
    setTakeNotes(defaultNote);
  }, []);

  const cancelTakeTrade = useCallback(() => {
    setSelectedPick(null);
    setFillPrice("");
    setContracts("1");
    setTakeNotes("");
  }, []);

  const submitTakeTrade = async () => {
    if (!selectedPick) return;
    const nextSignature = buildContractSignature({
      ...selectedPick,
      source_pick_snapshot: selectedPick,
    });
    const existingOpenPosition = openPositions.find((position) => buildContractSignature(position) === nextSignature);
    if (existingOpenPosition) {
      setActiveSubTab("positions");
      setPositionsView("open");
      toast.error("That contract is already open in tracked positions.");
      return;
    }
    await guard(async () => {
      setTakingTrade(true);
      try {
        const payload: CreateTrackedPositionRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetch("/api/positions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to track position");
        }
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelTakeTrade();
        setPositionsView("open");
        setActiveSubTab("positions");
        toast.success(data.duplicate ? "Open tracked position already exists." : "Tracked position saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to track position.");
      } finally {
        setTakingTrade(false);
      }
    });
  };

  const submitSuggestedTrade = async () => {
    if (!selectedPick) return;
    const nextSignature = buildContractSignature({
      ...selectedPick,
      source_pick_snapshot: selectedPick,
    });
    const existingSuggestedTrade = openSuggestedTrades.find((trade) => buildContractSignature(trade) === nextSignature);
    if (existingSuggestedTrade) {
      setShowLegacyTabs(true);
      setActiveSubTab("suggestions");
      setSuggestedTradesView("open");
      toast.error("That contract is already open in suggested trades.");
      return;
    }
    await guard(async () => {
      setSavingSuggestedTrade(true);
      try {
        const payload: CreateSuggestedTradeRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetch("/api/suggested-trades", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to save suggested trade");
        }
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelTakeTrade();
        setShowLegacyTabs(true);
        setSuggestedTradesView("open");
        setActiveSubTab("suggestions");
        toast.success(data.duplicate ? "Open suggested trade already exists." : "Suggested trade saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to save suggested trade.");
      } finally {
        setSavingSuggestedTrade(false);
      }
    });
  };

  const reviewSinglePosition = async (positionId: number) => {
    setReviewingIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/positions/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Tracked position review");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to review position");
      }
      applyReviewedPositions((data.positions || []) as TrackedPosition[]);
      toast.success("Position reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review position.");
    } finally {
      setReviewingIds((prev) => prev.filter((id) => id !== positionId));
    }
  };

  const reviewSingleSuggestedTrade = async (positionId: number) => {
    setReviewingSuggestedTradeIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/suggested-trades/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Suggested trade review");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to review suggested trade");
      }
      applyReviewedSuggestedTrades((data.trades || []) as SuggestedTrade[]);
      toast.success("Suggested trade reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review suggested trade.");
    } finally {
      setReviewingSuggestedTradeIds((prev) => prev.filter((id) => id !== positionId));
    }
  };

  const openCloseForm = useCallback((position: TrackedPosition) => {
    setClosingPosition(position);
    const suggestedExitPrice = getCloseNowPrice(position) ?? position.last_option_price;
    setExitPrice(suggestedExitPrice != null ? suggestedExitPrice.toFixed(2) : "");
    setCloseNotes("");
  }, []);

  const cancelCloseForm = useCallback(() => {
    setClosingPosition(null);
    setExitPrice("");
    setCloseNotes("");
    setClosingId(null);
  }, []);

  const openCloseSuggestedTradeForm = useCallback((trade: SuggestedTrade) => {
    setClosingSuggestedTrade(trade);
    const suggestedExitPrice = getCloseNowPrice(trade) ?? trade.last_option_price;
    setSuggestedExitPrice(suggestedExitPrice != null ? suggestedExitPrice.toFixed(2) : "");
    setSuggestedCloseNotes("");
  }, []);

  const cancelCloseSuggestedTradeForm = useCallback(() => {
    setClosingSuggestedTrade(null);
    setSuggestedExitPrice("");
    setSuggestedCloseNotes("");
    setClosingSuggestedTradeId(null);
  }, []);

  const submitClosePosition = async () => {
    if (!closingPosition) return;
    const parsedExitPrice = parseNonnegativePriceInput(exitPrice);
    if (parsedExitPrice == null) {
      toast.error("Enter a valid exit price of 0 or greater.");
      return;
    }
    await guard(async () => {
      setClosingId(closingPosition.id);
      try {
        const payload: CloseTrackedPositionRequest = {
          exit_price: parsedExitPrice,
          notes: closeNotes || undefined,
        };
        const res = await fetchWithTimeout(`/api/positions/${closingPosition.id}/close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }, "Close tracked position");
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to close tracked position");
        }
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelCloseForm();
        toast.success("Tracked position closed.");
        void fetchPositions(false);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close tracked position.");
      } finally {
        setClosingId(null);
      }
    });
  };

  const submitCloseSuggestedTrade = async () => {
    if (!closingSuggestedTrade) return;
    const parsedExitPrice = parseNonnegativePriceInput(suggestedExitPrice);
    if (parsedExitPrice == null) {
      toast.error("Enter a valid exit price of 0 or greater.");
      return;
    }
    await guard(async () => {
      setClosingSuggestedTradeId(closingSuggestedTrade.id);
      try {
        const payload: CloseSuggestedTradeRequest = {
          exit_price: parsedExitPrice,
          notes: suggestedCloseNotes || undefined,
        };
        const res = await fetchWithTimeout(`/api/suggested-trades/${closingSuggestedTrade.id}/close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }, "Close suggested trade");
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to close suggested trade");
        }
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelCloseSuggestedTradeForm();
        toast.success("Suggested trade closed.");
        void fetchSuggestedTrades(false);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close suggested trade.");
      } finally {
        setClosingSuggestedTradeId(null);
      }
    });
  };

  const scanPreds = useMemo(
    () => predictions.filter((p) => p.type === "daily_scan"),
    [predictions]
  );
  const graded = useMemo(
    () => scanPreds.filter((p) => p.outcome),
    [scanPreds]
  );
  const pending = useMemo(
    () => scanPreds.filter((p) => !p.outcome),
    [scanPreds]
  );
  const hits = useMemo(
    () => graded.filter((p) => p.outcome === "hit"),
    [graded]
  );
  const dirOk = useMemo(
    () => graded.filter((p) => p.outcome === "hit" || p.outcome === "directional"),
    [graded]
  );
  const callAcc = useMemo(() => {
    const callGraded = graded.filter((p) => p.direction === "call");
    return callGraded.length > 0
      ? ((callGraded.filter((p) => p.outcome === "hit" || p.outcome === "directional").length / (callGraded.length || 1)) * 100).toFixed(1)
      : "\u2014";
  }, [graded]);
  const putAcc = useMemo(() => {
    const putGraded = graded.filter((p) => p.direction === "put");
    return putGraded.length > 0
      ? ((putGraded.filter((p) => p.outcome === "hit" || p.outcome === "directional").length / (putGraded.length || 1)) * 100).toFixed(1)
      : "\u2014";
  }, [graded]);

  const PRIMARY_SUB_TABS = [
    { id: "positions", label: `Tracked Positions (${openPositions.length})`, icon: BriefcaseBusiness, targetView: "open" as const },
    { id: "closed-trades", label: `Closed Trades (${closedPositions.length})`, icon: CheckCircle, targetView: "closed" as const },
    { id: "scanner", label: `Scanner (${scanPicks.length})`, icon: RefreshCw },
  ] as const;
  const LEGACY_SUB_TABS = [
    { id: "suggestions", label: `Suggested Trades (${openSuggestedTrades.length})`, icon: Clipboard },
    { id: "pending", label: `Legacy Active (${pending.length})`, icon: Timer },
    { id: "graded", label: `Legacy Graded (${graded.length})`, icon: CheckCircle },
    { id: "breakdown", label: "Legacy Breakdown", icon: BarChart3 },
    { id: "sim", label: "Legacy Portfolio Sim", icon: DollarSign },
    { id: "sectors", label: "Legacy Sectors", icon: Map },
  ] as const;
  const SUB_TABS = showLegacyTabs ? [...PRIMARY_SUB_TABS, ...LEGACY_SUB_TABS] : PRIMARY_SUB_TABS;
  const legacyDataError = LEGACY_PREDICTION_TABS.has(activeSubTab)
    ? predictionsError || (activeSubTab === "sectors" ? sectorsError : null)
    : null;

  if (loading) {
    return (
      <div className="px-4 md:px-6 xl:px-8 py-5 max-w-[96vw] xl:max-w-[1800px] mx-auto space-y-5">
        <MetricGridSkeleton count={5} />
        <TableSkeleton rows={6} />
      </div>
    );
  }

  return (
    <div className="px-4 md:px-6 xl:px-8 py-5 max-w-[96vw] xl:max-w-[1800px] mx-auto">
      {LEGACY_PREDICTION_TABS.has(activeSubTab) && (
        <div className="space-y-6 mb-6">
          <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
            These legacy prediction analytics are archival scanner research, not the current supervised tracked-position workflow.
          </div>
          {legacyDataError ? (
            <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
              {legacyDataError}
            </div>
          ) : null}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <MetricCard label="Total Picks" value={String(scanPreds.length)} />
            <MetricCard label="Active Trades" value={String(pending.length)} />
            <MetricCard
              label="Hit Rate"
              value={graded.length > 0 ? `${((hits.length / (graded.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
              help="Direction correct AND magnitude >= 50% of target"
            />
            <MetricCard
              label="Directional"
              value={graded.length > 0 ? `${((dirOk.length / (graded.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
              help="% where direction was correct regardless of magnitude"
            />
            <MetricCard
              label="Call/Put Acc"
              value={`${callAcc}% / ${putAcc}%`}
              help="Directional accuracy for call vs put picks"
            />
          </div>
        </div>
      )}

      {graded.length > 0 && LEGACY_PREDICTION_TABS.has(activeSubTab) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {["index", "equity"].map((assetClass) => {
            const subset = graded.filter((p) =>
              assetClass === "index"
                ? INDEX_TICKERS.has(p.ticker?.toUpperCase())
                : !INDEX_TICKERS.has(p.ticker?.toUpperCase())
            );
            const wins = subset.filter((p) => p.outcome === "hit" || p.outcome === "directional");
            const pnls = subset
              .map((p) => p.option_gain_pct)
              .filter((v): v is number => v != null);
            const avgPnl = pnls.length > 0
              ? (pnls.reduce((a, b) => a + b, 0) / (pnls.length || 1)).toFixed(1)
              : "\u2014";
            const iconChar = assetClass === "index" ? "\uD83D\uDCCA" : "\uD83D\uDCC8";
            const label = assetClass === "index" ? "Index picks" : "Equity picks";
            return (
              <div key={assetClass} className="bg-bg-2 border border-border rounded-lg p-4">
                <div className="text-sm font-semibold text-text-0 mb-2">
                  <span aria-hidden="true">{iconChar}</span>
                  <span className="sr-only">{label}</span>{" "}
                  {label}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard
                    label="Win Rate"
                    value={subset.length > 0 ? `${((wins.length / (subset.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
                  />
                  <MetricCard
                    label="Avg Option P&L"
                    value={avgPnl === "\u2014" ? "\u2014" : `${avgPnl}%`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-center gap-0 border-b border-border mb-4 overflow-x-auto" role="tablist">
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive =
            tab.id === "positions"
              ? activeSubTab === "positions" && positionsView === "open"
              : tab.id === "closed-trades"
                ? activeSubTab === "positions" && positionsView === "closed"
                : activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => {
                if ("targetView" in tab) {
                  setPositionsView(tab.targetView);
                  setActiveSubTab("positions");
                  return;
                }
                setActiveSubTab(tab.id);
              }}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium uppercase tracking-wide transition-all border-b-2 whitespace-nowrap ${
                isActive
                  ? "text-text-0 border-accent"
                  : "text-text-2 border-transparent hover:text-text-1"
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowLegacyTabs((prev) => !prev)}
        >
          {showLegacyTabs ? "Hide Legacy" : "Show Legacy Research"}
        </Button>
        {LEGACY_PREDICTION_TABS.has(activeSubTab) && (
          <Button
            variant="secondary"
            size="sm"
            loading={grading}
            icon={<RefreshCw size={12} />}
            onClick={async () => {
              await guard(async () => {
                setGrading(true);
                try {
                  const response = await fetch("/api/predictions/grade", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({}),
                  });
                  const data = await response.json().catch(() => ({}));
                  if (!response.ok || data.error) {
                    throw new Error(data.error || "Failed to grade predictions");
                  }
                  await fetchPredictionsData({
                    includePredictions: true,
                    includeSectors: activeSubTab === "sectors" && !sectorsLoaded,
                  });
                  toast.success("Predictions graded successfully.");
                } catch (err) {
                  console.error("Failed to grade predictions:", err);
                  toast.error("Failed to grade predictions. Please try again.");
                } finally {
                  setGrading(false);
                }
              });
            }}
            aria-label="Grade all predictions"
          >
            {grading ? "Grading..." : "Grade All"}
          </Button>
        )}
      </div>

      <div role="tabpanel">
        {activeSubTab === "scanner" && (
          <ScannerTab
            picks={scanPicks}
            loading={scanLoading}
            useRecommendedPolicy={useRecommendedPolicy}
            policy={scanPolicy}
            policyError={scanPolicyError}
            exitAudit={scanExitAudit}
            decisionCounts={scanDecisionCounts}
            guardrailCounts={guardrailDecisionCounts}
            candidateCount={scanCandidateCount}
            forwardEvidence={forwardEvidence}
            optionsProfitStatus={optionsProfitStatus}
            truthHealthError={truthHealthError}
            playbook={scanPlaybook}
            playbooks={availablePlaybooks}
            exposureSnapshot={exposureSnapshot}
            showBlockedIdeas={showBlockedIdeas}
            selectedPick={selectedPick}
            fillPrice={fillPrice}
            contracts={contracts}
            notes={takeNotes}
            takingTrade={takingTrade}
            savingSuggestedTrade={savingSuggestedTrade}
            onRefresh={() => void refreshScannerSurface(true)}
            onPolicyModeChange={setUseRecommendedPolicy}
            onPlaybookChange={setScanPlaybook}
            onShowBlockedIdeasChange={setShowBlockedIdeas}
            onPick={openTakeTrade}
            onCancel={cancelTakeTrade}
            onFillPriceChange={setFillPrice}
            onContractsChange={setContracts}
            onNotesChange={setTakeNotes}
            onSubmit={() => void submitTakeTrade()}
            onSubmitSuggested={() => void submitSuggestedTrade()}
          />
        )}
        {activeSubTab === "suggestions" && (
          <SuggestedTradesTab
            openTrades={openSuggestedTrades}
            closedTrades={closedSuggestedTrades}
            loading={suggestedTradesLoading}
            error={suggestedTradesError}
            view={suggestedTradesView}
            reviewingIds={reviewingSuggestedTradeIds}
            onViewChange={setSuggestedTradesView}
            onRefresh={() => void fetchSuggestedTrades(true)}
            onReviewTrade={(positionId) => void reviewSingleSuggestedTrade(positionId)}
            onOpenClose={openCloseSuggestedTradeForm}
          />
        )}
        {activeSubTab === "positions" && (
          <TrackedPositionsTab
            openPositions={openPositions}
            closedPositions={closedPositions}
            loading={positionsLoading}
            error={positionsError}
            view={positionsView}
            reviewingIds={reviewingIds}
            onViewChange={setPositionsView}
            onRefresh={() => void fetchPositions(true)}
            onReviewPosition={(positionId) => void reviewSinglePosition(positionId)}
            onOpenClose={openCloseForm}
          />
        )}
        {activeSubTab === "pending" && <PendingTab predictions={pending} />}
        {activeSubTab === "graded" && <GradedTab predictions={graded} />}
        {activeSubTab === "breakdown" && <BreakdownTab predictions={graded} />}
        {activeSubTab === "sim" && <SimTab predictions={scanPreds} />}
        {activeSubTab === "sectors" && (
          <SectorsTab
            sectors={sectors}
            loading={!sectorsLoaded && !sectorsError}
            error={sectorsError}
          />
        )}
      </div>

      <CloseTradeModal
        item={closingPosition}
        mode="tracked"
        exitPrice={exitPrice}
        notes={closeNotes}
        closingId={closingId}
        onExitPriceChange={setExitPrice}
        onNotesChange={setCloseNotes}
        onCancel={cancelCloseForm}
        onConfirm={() => void submitClosePosition()}
      />

      <CloseTradeModal
        item={closingSuggestedTrade}
        mode="suggested"
        exitPrice={suggestedExitPrice}
        notes={suggestedCloseNotes}
        closingId={closingSuggestedTradeId}
        onExitPriceChange={setSuggestedExitPrice}
        onNotesChange={setSuggestedCloseNotes}
        onCancel={cancelCloseSuggestedTradeForm}
        onConfirm={() => void submitCloseSuggestedTrade()}
      />
    </div>
  );
}

function ScannerTab({
  picks,
  loading,
  useRecommendedPolicy,
  policy,
  policyError,
  exitAudit,
  decisionCounts,
  guardrailCounts,
  candidateCount,
  forwardEvidence,
  optionsProfitStatus,
  truthHealthError,
  playbook,
  playbooks,
  exposureSnapshot,
  showBlockedIdeas,
  selectedPick,
  fillPrice,
  contracts,
  notes,
  takingTrade,
  savingSuggestedTrade,
  onRefresh,
  onPolicyModeChange,
  onPlaybookChange,
  onShowBlockedIdeasChange,
  onPick,
  onCancel,
  onFillPriceChange,
  onContractsChange,
  onNotesChange,
  onSubmit,
  onSubmitSuggested,
}: {
  picks: ScanPick[];
  loading: boolean;
  useRecommendedPolicy: boolean;
  policy: LiveTradePolicy | null;
  policyError: string | null;
  exitAudit: PlaybookExitAudit | null;
  decisionCounts: Record<string, number> | null;
  guardrailCounts: Record<string, number> | null;
  candidateCount: number;
  forwardEvidence: ForwardEvidenceReport | null;
  optionsProfitStatus: OptionsProfitStatus | null;
  truthHealthError: string | null;
  playbook: string;
  playbooks: ScanPlaybook[];
  exposureSnapshot: ExposureSnapshot | null;
  showBlockedIdeas: boolean;
  selectedPick: ScanPick | null;
  fillPrice: string;
  contracts: string;
  notes: string;
  takingTrade: boolean;
  savingSuggestedTrade: boolean;
  onRefresh: () => void;
  onPolicyModeChange: (value: boolean) => void;
  onPlaybookChange: (value: string) => void;
  onShowBlockedIdeasChange: (value: boolean) => void;
  onPick: (pick: ScanPick) => void;
  onCancel: () => void;
  onFillPriceChange: (value: string) => void;
  onContractsChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSubmit: () => void;
  onSubmitSuggested: () => void;
}) {
  const hardFilters = policy?.scan_policy.hard_filters;
  const preferred = policy?.scan_policy.preferred_filters;
  const promotionStatus = String(policy?.scan_policy.promotion_status || policy?.promotion_status || "watch").toLowerCase();
  const policyIsPromoted = promotionStatus === "promote";
  const truthSource = String(policy?.source?.truth_source || policy?.truth_source || "").toLowerCase();
  const truthSourceLabel = fmtTruthSource(truthSource);
  const quoteCoverage = policy?.source?.quote_coverage_pct ?? policy?.quote_coverage_pct ?? null;
  const sourceLabel = [
    policy?.source_run_at ? fmtDate(policy.source_run_at) : null,
    policy?.lookback_years != null ? `${policy.lookback_years}y` : null,
    policy?.pricing_lane ? String(policy.pricing_lane).toUpperCase() : null,
    policy?.playbook ? String(policy.playbook).replaceAll("_", " ") : null,
  ].filter(Boolean).join(" \u00b7 ");
  const approvedCount = decisionCounts?.approved || 0;
  const watchCount = decisionCounts?.watch || 0;
  const blockedCount = decisionCounts?.blocked || 0;
  const approvedReplayTrades = exitAudit?.approved?.trades ?? null;
  const clearCount = guardrailCounts?.clear || 0;
  const cautionCount = guardrailCounts?.caution || 0;
  const guardrailBlockedCount = guardrailCounts?.blocked || 0;
  const activePlaybook = playbooks.find((item) => item.id === playbook) || null;
  const measurementGate = optionsProfitStatus?.measurement_gate;
  const gateState = String(measurementGate?.state || "unknown").toLowerCase();
  const importedDailyCheck = measurementGate?.checks?.imported_daily_artifact || null;
  const forwardGateCheck = measurementGate?.checks?.forward_evidence || null;
  const trackedPositionsCheck = measurementGate?.checks?.tracked_positions || null;
  const dailyTruthRefresh = optionsProfitStatus?.daily_truth_refresh || null;
  const exactContractCount = Number(forwardEvidence?.exact_contract_capture_counts?.with_contract_count || 0);
  const totalForwardCaptures = Number(forwardEvidence?.scan_pick_count || 0);
  const exactContractCoveragePct = totalForwardCaptures > 0
    ? (exactContractCount / totalForwardCaptures) * 100
    : null;
  const contractResolutionOverview = forwardEvidence?.archived_forward_artifact?.contract_resolution_overview || null;
  const trackedDbStatus = trackedPositionsCheck?.available
    ? "READY"
    : trackedPositionsCheck?.database_url_configured
      ? "DOWN"
      : "MISSING";
  const blockerMessages = (measurementGate?.blockers || [])
    .map((item) => {
      if (typeof item === "string") return item;
      return String(item?.message || item?.code || "").trim();
    })
    .filter(Boolean)
    .slice(0, 3);

  const rows = picks.map((pick) => ({
    Ticker: pick.ticker,
    Trade: pick.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
    Contract: fmtContractLabel({
      ticker: pick.ticker,
      direction: pick.direction,
      strike: pick.strike ?? pick.strike_est,
      short_strike: pick.short_strike,
      expiry: pick.expiry,
      contract_symbol: pick.contract_symbol,
    }),
    Quote: quoteContextLabel(pick),
    "Dir. Score": pick.direction_score.toFixed(0),
    Quality: pick.quality_score.toFixed(0),
    Decision: pick.policy_decision
      ? pick.policy_decision === "approved"
        ? "Approved"
        : pick.policy_decision === "watch"
        ? "Watch"
        : "Blocked"
      : "\u2014",
    Guardrails: pick.guardrail_decision
      ? pick.guardrail_decision === "clear"
        ? "Clear"
        : pick.guardrail_decision === "caution"
        ? "Caution"
        : "Blocked"
      : "\u2014",
    Size: pick.suggested_size_tier ? pick.suggested_size_tier.toUpperCase() : "\u2014",
    "Risk/Upside": fmtRiskUpsideLabel(pick),
    Regime: pick.market_regime ? pick.market_regime.toUpperCase() : "\u2014",
    Sector: pick.sector || "\u2014",
    Stock: fmtMoney(pick.stock_price),
    Premium: fmtMoney(pick.premium ?? pick.est_premium),
    Strike: fmtMoney(pick.strike ?? pick.strike_est, 0),
    Expiry: fmtDate(pick.expiry),
    "Target Move": pick.target_move_pct != null ? `${pick.target_move_pct.toFixed(2)}%` : "\u2014",
    Action: (
      <Button size="sm" variant="secondary" onClick={() => onPick(pick)}>
        {pick.guardrail_decision === "blocked"
          ? "Inspect"
          : pick.guardrail_decision === "caution"
          ? "Take Smaller"
          : pick.policy_decision === "approved"
          ? "Take Approved"
          : pick.policy_decision === "watch"
          ? "Take Watch"
          : "Take Trade"}
      </Button>
    ),
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="section-header mt-0">Live Options Scanner</div>
          <p className="text-xs text-text-3">
            Supervised decision support for live options ideas. Start from a current scan pick, then either save the trade you actually took or log a clearly hypothetical paper idea.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {(playbooks.length ? playbooks : [
            { id: "bullish_pullback_observation", label: "Bullish Pullback Primary" },
            { id: "tracked_winner_primary", label: "Tracked Winner Primary" },
            { id: "short_term", label: "Short-Term" },
            { id: "swing", label: "Swing" },
            { id: "speculative", label: "Speculative" },
            { id: "bearish_defensive", label: "Bearish Defensive" },
          ]).map((item) => (
            <Button
              key={item.id}
              size="sm"
              variant={playbook === item.id ? "secondary" : "ghost"}
              onClick={() => onPlaybookChange(item.id)}
            >
              {item.label}
            </Button>
          ))}
          <Button
            size="sm"
            variant={useRecommendedPolicy ? "secondary" : "ghost"}
            onClick={() => onPolicyModeChange(true)}
          >
            Replay-Backed Focus
          </Button>
          <Button
            size="sm"
            variant={!useRecommendedPolicy ? "secondary" : "ghost"}
            onClick={() => onPolicyModeChange(false)}
          >
            All Qualifying
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh Scan
          </Button>
          <Button
            size="sm"
            variant={showBlockedIdeas ? "secondary" : "ghost"}
            onClick={() => onShowBlockedIdeasChange(!showBlockedIdeas)}
          >
            {showBlockedIdeas ? "Hide Blocked" : "Show Blocked"}
          </Button>
        </div>
      </div>

      {activePlaybook && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">{activePlaybook.label} Playbook</div>
              <p className="text-xs text-text-3 mt-1">{activePlaybook.description}</p>
              {activePlaybook.allowed_tickers?.length && (
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-2">
                  Managed lane
                  {activePlaybook.allowed_tickers?.length
                    ? ` \u00b7 Universe ${activePlaybook.allowed_tickers.join(" / ")}`
                    : ""}
                </div>
              )}
              {typeof activePlaybook.historical_scan_ready_count === "number" && (
                <div className="text-[11px] uppercase tracking-wide text-emerald-200/80 mt-1">
                  Theta EOD ready {activePlaybook.historical_scan_ready_count}/{activePlaybook.historical_scan_required_count ?? activePlaybook.allowed_tickers?.length ?? 0}
                  {typeof activePlaybook.historical_core_ready_count === "number"
                    ? ` \u00b7 Core ${activePlaybook.historical_core_ready_count}/${activePlaybook.historical_core_required_count ?? 0}`
                    : ""}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <MetricCard label="Target DTE" value={String(activePlaybook.target_dte)} />
              <MetricCard label="Day Cap" value={String(activePlaybook.max_new_positions_per_day)} />
              <MetricCard label="Sector Cap" value={String(activePlaybook.max_sector_open_positions)} />
              <MetricCard label="Regime Cap" value={String(activePlaybook.max_regime_open_positions)} />
            </div>
          </div>

          {exposureSnapshot && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <MetricCard label="Open Positions" value={String(exposureSnapshot.open_positions)} />
                <MetricCard label="Opened Today" value={String(exposureSnapshot.opened_today)} />
                <MetricCard label="Guardrail Clear" value={String(clearCount)} />
                <MetricCard label="Guardrail Caution" value={String(cautionCount)} />
                <MetricCard label="Guardrail Blocked" value={String(guardrailBlockedCount)} />
              </div>
              <div className="text-xs text-text-3">
                Opened today {exposureSnapshot.opened_today}/{activePlaybook.max_new_positions_per_day}
                {" "}&middot; Same-sector cap {activePlaybook.max_sector_open_positions}
                {" "}&middot; Same-regime cap {activePlaybook.max_regime_open_positions}
              </div>
              {(policy?.priced_trade_count != null || policy?.unpriced_trade_count != null || policy?.entry_quote_time_et || policy?.exit_quote_time_et) && (
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                  {policy?.priced_trade_count != null || policy?.unpriced_trade_count != null
                    ? `Priced ${policy?.priced_trade_count ?? 0} / Unpriced ${policy?.unpriced_trade_count ?? 0}`
                    : "Quote windows active"}
                  {policy.entry_quote_time_et ? ` | Entry ${policy.entry_quote_time_et}` : ""}
                  {policy.exit_quote_time_et ? ` | Exit ${policy.exit_quote_time_et}` : ""}
                </div>
              )}
            </div>
          )}

          {exposureSnapshot?.warnings?.length ? (
        <div className="space-y-1">
              {exposureSnapshot.warnings.map((line) => (
                <div key={line} className="text-xs text-text-3">
                  {line}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {(forwardEvidence || optionsProfitStatus || truthHealthError) && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">Options Truth Health</div>
              <p className="text-xs text-text-3 mt-1">
                This surface summarizes whether current scanner evidence is fresh enough, exact enough, and operationally usable for supervised decisions.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <MetricCard label="Gate" value={fmtUpperLabel(gateState)} />
              <MetricCard label="Truth Horizon" value={fmtDate(forwardGateCheck?.trusted_truth_horizon as string | null | undefined)} />
              <MetricCard label="Eligible Live" value={String(forwardGateCheck?.eligible_event_count ?? 0)} />
              <MetricCard label="Exact Coverage" value={exactContractCoveragePct != null ? `${exactContractCoveragePct.toFixed(0)}%` : "\u2014"} />
              <MetricCard label="Tracked DB" value={trackedDbStatus} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Imported Daily</div>
              <div className="text-sm text-text-1">
                {importedDailyCheck?.present && importedDailyCheck?.matches_store
                  ? `Coverage ${Number(importedDailyCheck.quote_coverage_pct ?? 0).toFixed(1)}%`
                  : "Artifact missing or stale"}
              </div>
              <div className="text-xs text-text-3">
                Refresh {fmtCompactLabel(dailyTruthRefresh?.status as string | null | undefined)}
                {dailyTruthRefresh?.stage ? ` · ${fmtCompactLabel(dailyTruthRefresh.stage as string)}` : ""}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Authoritative Forward</div>
              <div className="text-sm text-text-1">
                {String(forwardEvidence?.authoritative_session_count ?? 0)} sessions · {String(forwardEvidence?.scan_pick_count ?? 0)} picks
              </div>
              <div className="text-xs text-text-3">
                Pending truth {String(forwardGateCheck?.pending_truth_event_count ?? 0)}
                {" "}&middot; Artifact {forwardEvidence?.archived_forward_artifact?.available ? "ready" : "waiting"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Contract Quality</div>
              <div className="text-sm text-text-1">
                {exactContractCount}/{totalForwardCaptures || 0} captures kept exact
              </div>
              <div className="text-xs text-text-3">
                Fallback {forwardEvidence?.archived_forward_artifact?.primary_judge_fallback_used ? fmtCompactLabel(forwardEvidence.archived_forward_artifact.primary_judge_fallback_reason) : "none"}
              </div>
              {contractResolutionOverview && (
                <div className="text-xs text-text-3">
                  Archived {String(contractResolutionOverview.exact_archived_contract ?? 0)}
                  {" "}&middot; Model {String(contractResolutionOverview.exact_target_contract ?? 0)}
                  {" "}&middot; Nearest {String(contractResolutionOverview.nearest_listed_contract ?? 0)}
                  {" "}&middot; Pending {String(contractResolutionOverview.pending_truth_horizon ?? 0)}
                </div>
              )}
            </div>
          </div>

          {truthHealthError && (
            <div className="bg-red-dim border border-red/30 rounded-lg px-3 py-2 text-xs text-red">
              {truthHealthError}
            </div>
          )}

          {gateState !== "healthy" && blockerMessages.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              {blockerMessages.map((line) => (
                <div key={line} className="text-xs text-amber-200">
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {policy && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">Replay-Backed Policy State</div>
              <p className="text-xs text-text-3 mt-1">
                This scanner gate follows the latest saved options truth artifacts. It is a truth layer, not a promise that the strategy is ready for trust-by-default.
              </p>
              {sourceLabel && (
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-2">
                  Source {sourceLabel}
                </div>
              )}
              <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                Truth {truthSourceLabel}
                {quoteCoverage != null ? ` | Coverage ${Number(quoteCoverage).toFixed(1)}%` : ""}
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <MetricCard label="Status" value={promotionStatus.toUpperCase()} />
              <MetricCard label="Scan Pool" value={String(candidateCount)} />
              <MetricCard label="Approved" value={String(approvedCount)} />
              <MetricCard label="Watch" value={String(watchCount)} />
              <MetricCard label="Blocked" value={String(blockedCount)} />
            </div>
          </div>

          {!useRecommendedPolicy && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              <div className="text-xs text-amber-200">
                Replay-Backed Focus is overridden. You are looking at all qualifying ideas, but the policy state above still describes the latest replay-backed truth and should be used as the risk context for any manual entry.
              </div>
            </div>
          )}

          {!policyIsPromoted && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              <div className="text-xs text-amber-200">
                Current policy state is <strong>{promotionStatus.toUpperCase()}</strong>, and the current truth lane is <strong>{truthSourceLabel.toUpperCase()}</strong>, so scanner ideas should be treated as watch-oriented and supervised paper-first unless you choose to override that manually.
              </div>
              {approvedReplayTrades === 0 && (
                <div className="text-xs text-amber-200">
                  The active {playbook.replaceAll("_", " ")} replay audit has zero approved trades in the latest saved artifact.
                </div>
              )}
              {approvedCount === 0 && (
                <div className="text-xs text-amber-200">
                  There are zero approved live picks in this scan right now.
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Hard Gate</div>
              <div className="text-sm text-text-1 mt-1">
                {hardFilters?.direction_score_min != null
                  ? `Direction score ${hardFilters.direction_score_min.toFixed(0)}${hardFilters.direction_score_max != null ? `-${hardFilters.direction_score_max.toFixed(0)}` : "+"}`
                  : "No score-band gate available yet"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Context</div>
              <div className="text-sm text-text-1 mt-1">
                {[
                  preferred?.asset_class ? preferred.asset_class : null,
                  ...(preferred?.market_regimes || []),
                ].filter(Boolean).join(" / ") || "No broad asset-regime preference yet"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Sectors</div>
              <div className="text-sm text-text-1 mt-1">
                {preferred?.sectors?.length ? preferred.sectors.join(", ") : "No broad sector preference yet"}
              </div>
            </div>
          </div>

          {policy.scan_policy.rationale.length > 0 && (
            <div className="space-y-1">
              {policy.scan_policy.rationale.map((line) => (
                <div key={line} className="text-xs text-text-2">
                  {line}
                </div>
              ))}
            </div>
          )}

          {policy.scan_policy.warnings.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              {policy.scan_policy.warnings.map((line) => (
                <div key={line} className="text-xs text-amber-200">
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {policyError && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {policyError}
        </div>
      )}

      {selectedPick && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div>
            <div className="text-sm font-semibold text-text-0">
              Record {fmtContractCoreLabel({
                ticker: selectedPick.ticker,
                direction: selectedPick.direction,
                strike: selectedPick.strike ?? selectedPick.strike_est,
                short_strike: selectedPick.short_strike,
                expiry: selectedPick.expiry,
              })}
            </div>
            <div className="text-xs text-text-3 mt-1">
              {fmtContractLabel({
                ticker: selectedPick.ticker,
                direction: selectedPick.direction,
                strike: selectedPick.strike ?? selectedPick.strike_est,
                short_strike: selectedPick.short_strike,
                expiry: selectedPick.expiry,
                contract_symbol: selectedPick.contract_symbol,
              })}
              {" "}&middot; Scan premium {fmtMoney(selectedPick.premium ?? selectedPick.est_premium)}
            </div>
            {(!policyIsPromoted || selectedPick.policy_decision !== "approved") && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mt-3 text-xs text-amber-200">
                {useRecommendedPolicy
                  ? "This setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."
                  : "Replay-Backed Focus is overridden, and this setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."}
              </div>
            )}
            {selectedPick.policy_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Policy</div>
                <div>
                  Decision: <strong className="text-text-0">{selectedPick.policy_decision.toUpperCase()}</strong>
                </div>
                {selectedPick.policy_fit_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            {selectedPick.guardrail_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Portfolio Guardrails</div>
                <div>
                  Guardrails: <strong className="text-text-0">{selectedPick.guardrail_decision.toUpperCase()}</strong>
                  {" "}&middot; Size tier <strong className="text-text-0">{selectedPick.suggested_size_tier?.toUpperCase() || "\u2014"}</strong>
                </div>
                {selectedPick.guardrail_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
                {selectedPick.suggested_size_reason && <div>{selectedPick.suggested_size_reason}</div>}
              </div>
            )}
            {(selectedPick.risk_tier != null
              || selectedPick.upside_tier != null
              || selectedPick.convexity_class) && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Risk Profile</div>
                <div>
                  Convexity: <strong className="text-text-0">{fmtUpperLabel(selectedPick.convexity_class)}</strong>
                  {" "}&middot; {fmtRiskUpsideLabel(selectedPick)}
                  {selectedPick.speculative_flag ? " \u00b7 SPECULATIVE" : ""}
                </div>
                {selectedPick.speculative_reason?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            <div className="text-xs text-text-2 mt-2 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Contract And Quote Provenance</div>
              <div>
                Contract quality: <strong className="text-text-0">{contractQualityLabel(selectedPick)}</strong>
                {selectedPick.contract_symbol ? ` · ${selectedPick.contract_symbol}` : ""}
              </div>
              <div>
                Quote: <strong className="text-text-0">{quoteContextLabel(selectedPick)}</strong>
                {selectedPick.quote_time_et ? ` · ${selectedPick.quote_time_et}` : ""}
              </div>
              <div>
                Selection: <strong className="text-text-0">{fmtCompactLabel(selectedPick.selection_source)}</strong>
                {" "}&middot; Promotion <strong className="text-text-0">{fmtCompactLabel(selectedPick.promotion_class)}</strong>
              </div>
              <div>
                Entry execution: <strong className="text-text-0">{fmtCompactLabel(selectedPick.entry_execution_basis)}</strong>
                {" "}&middot; {fmtMoney(selectedPick.entry_execution_price ?? selectedPick.premium ?? selectedPick.est_premium)}
              </div>
              <div>
                Profitability: <strong className="text-text-0">{fmtUpperLabel(selectedPick.profitability_eligibility)}</strong>
                {selectedPick.profitability_blockers?.length
                  ? ` · ${selectedPick.profitability_blockers.join(", ")}`
                  : ""}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Entry price</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={fillPrice}
                onChange={(e) => onFillPriceChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Contracts</span>
              <input
                type="number"
                min="1"
                step="1"
                value={contracts}
                onChange={(e) => onContractsChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Optional note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
          <div className="text-xs text-text-3">
            Eligible scheduled scanner picks are auto-tracked. Use this form for manual corrections or trades you actually placed outside the scheduled run.
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              loading={takingTrade}
              disabled={selectedPick.guardrail_decision === "blocked" || savingSuggestedTrade}
              onClick={onSubmit}
            >
              Save Real Tracked Position
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={savingSuggestedTrade}
              disabled={takingTrade}
              onClick={onSubmitSuggested}
            >
              Save Hypothetical Suggested Trade
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {picks.length === 0 && !loading ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          No qualifying options picks were returned by the live scan.
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          monoCols={["Contract", "Quote", "Dir. Score", "Quality", "Size", "Stock", "Premium", "Strike"]}
          label="Live options scanner picks"
          maxHeight="620px"
        />
      )}
    </div>
  );
}

function CompactStat({
  label,
  value,
  help,
}: {
  label: string;
  value: string;
  help?: string;
}) {
  return (
    <div className="bg-bg-2 border border-border rounded-lg px-3 py-1.5 min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.09em] text-text-2">
        {label}
        {help && <span className="sr-only">: {help}</span>}
      </div>
      <div className="font-mono text-[0.95rem] text-text-0 mt-0.5">{value}</div>
    </div>
  );
}

function EntryDateFilterControls({
  preset,
  customDate,
  onPresetChange,
  onCustomDateChange,
}: {
  preset: EntryDateFilterPreset;
  customDate: string;
  onPresetChange: (value: EntryDateFilterPreset) => void;
  onCustomDateChange: (value: string) => void;
}) {
  const hasActiveFilter = preset !== "all";

  return (
    <div className="rounded-lg border border-border bg-bg-2 px-3 py-2">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">
            Entry Date
          </span>
          {([
            { id: "today", label: "Today" },
            { id: "yesterday", label: "Yesterday" },
            { id: "last7", label: "Last 7D" },
          ] as const).map((option) => (
            <Button
              key={option.id}
              size="sm"
              variant={preset === option.id ? "secondary" : "ghost"}
              onClick={() => onPresetChange(option.id)}
            >
              {option.label}
            </Button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-text-2">
            <span className="whitespace-nowrap">Pick date</span>
            <input
              type="date"
              value={customDate}
              onChange={(event) => {
                const value = event.target.value;
                onCustomDateChange(value);
                onPresetChange(value ? "custom" : "all");
              }}
              className="rounded border border-border bg-bg-3 px-2.5 py-1 text-xs text-text-0"
            />
          </label>
          {hasActiveFilter ? (
            <Button size="sm" variant="ghost" onClick={() => {
              onCustomDateChange("");
              onPresetChange("all");
            }}>
              Clear
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CloseTradeModal({
  item,
  mode,
  exitPrice,
  notes,
  closingId,
  onExitPriceChange,
  onNotesChange,
  onCancel,
  onConfirm,
}: {
  item: TrackedPosition | SuggestedTrade | null;
  mode: "tracked" | "suggested";
  exitPrice: string;
  notes: string;
  closingId: number | null;
  onExitPriceChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!item) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && closingId !== item.id) {
        onCancel();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [item, closingId, onCancel]);

  if (!item) return null;

  const title = mode === "tracked" ? "Close Tracked Trade" : "Close Suggested Trade";
  const confirmLabel = mode === "tracked" ? "Confirm Close" : "Confirm Hypothetical Close";
  const exitLabel = mode === "tracked" ? "Actual exit price" : "Hypothetical exit price";
  const liveExitPrice = getCloseNowPrice(item);
  const paperValue = getMarkPrice(item);
  const enteredExitPrice = parseNonnegativePriceInput(exitPrice);
  const exitPnl =
    enteredExitPrice != null
      ? calcNetOptionPnlPct({
          entryPrice: getEntryExecutionPrice(item),
          exitPrice: enteredExitPrice,
          contracts: item.contracts,
          feeTotalUsd: item.latest_review?.fee_total_usd ?? item.fee_total_usd ?? 0,
        })
      : getCloseNowPnlPct(item);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 px-4 py-6 flex items-center justify-center"
      onMouseDown={() => {
        if (closingId !== item.id) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="close-trade-modal-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-bg-1 shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border">
          <div id="close-trade-modal-title" className="text-base font-semibold text-text-0">
            {title}
          </div>
          <div className="text-sm text-text-2 mt-1">
            {item.ticker} {item.direction.toUpperCase()} · Taken {fmtTakenDate(item)} · Exp {fmtDate(getResolvedListedExpiry(item))}
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Entry</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(item.entry_option_price)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Paper Value</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(paperValue)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Est. Exit</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(liveExitPrice)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Exit P&L</div>
              <div className={`font-mono text-sm mt-1 ${metricToneClass(exitPnl)}`}>{fmtPct(exitPnl)}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-text-2">
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div>
                Recommendation: <strong className="text-text-0">{item.last_recommendation || "\u2014"}</strong>
              </div>
              <div className="mt-1">
                Pricing: <strong className="text-text-0">{fmtPricingSource(item.latest_review?.pricing_source)}</strong>
              </div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div>
                Provenance: <strong className="text-text-0">{getShareSafeReason(item)}</strong>
              </div>
              <div className="mt-1">
                Renewed: <strong className="text-text-0">{fmtDateTime(getReviewedAt(item))}</strong>
              </div>
            </div>
          </div>

          {item.latest_review?.warnings?.length ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {item.latest_review.warnings[0]}
            </div>
          ) : null}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">{exitLabel}</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={exitPrice}
                onChange={(e) => onExitPriceChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Optional close note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={closingId === item.id}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" loading={closingId === item.id} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

function SuggestedTradesTab({
  openTrades,
  closedTrades,
  loading,
  error,
  view,
  reviewingIds,
  onViewChange,
  onRefresh,
  onReviewTrade,
  onOpenClose,
}: {
  openTrades: SuggestedTrade[];
  closedTrades: SuggestedTrade[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  onViewChange: (value: "open" | "closed") => void;
  onRefresh: () => void;
  onReviewTrade: (positionId: number) => void;
  onOpenClose: (trade: SuggestedTrade) => void;
}) {
  const dedupedOpenTrades = openTrades;
  const [openFilter, setOpenFilter] = useState<"share-safe" | "all">("all");
  const shareSafeOpenTrades = dedupedOpenTrades.filter((trade) => isShareSafeLivePosition(trade));
  const hiddenOpenTradeCount = Math.max(dedupedOpenTrades.length - shareSafeOpenTrades.length, 0);
  const trades = view === "open"
    ? (openFilter === "share-safe" ? shareSafeOpenTrades : dedupedOpenTrades)
    : closedTrades;
  const holdCount = dedupedOpenTrades.filter((trade) => trade.last_recommendation === "HOLD").length;
  const sellCount = dedupedOpenTrades.filter((trade) => trade.last_recommendation === "SELL").length;
  const openPnlValues = dedupedOpenTrades
    .map((trade) => getCloseNowPnlPct(trade))
    .filter((value): value is number => value != null);
  const closedPnlValues = closedTrades
    .map((trade) => getRealizedPnlPct(trade))
    .filter((value): value is number => value != null);
  const avgOpenPnl = openPnlValues.length > 0
    ? openPnlValues.reduce((sum, value) => sum + value, 0) / openPnlValues.length
    : null;
  const avgClosedPnl = closedPnlValues.length > 0
    ? closedPnlValues.reduce((sum, value) => sum + value, 0) / closedPnlValues.length
    : null;

  const rows = trades.map((trade) => {
    const displayPnl = view === "open"
      ? getCloseNowPnlPct(trade)
      : getRealizedPnlPct(trade);

    if (view === "open") {
      return {
        Ticker: trade.ticker,
        Trade: trade.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
        Logged: fmtDate(trade.filled_at),
        Entry: fmtMoney(trade.entry_option_price),
        "Live Px": renderOpenPriceCell(trade),
        "Live P&L": renderOpenPnlCell(trade),
        Recommendation: trade.last_recommendation || "\u2014",
        Action: (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              loading={reviewingIds.includes(trade.id)}
              onClick={() => onReviewTrade(trade.id)}
            >
              Review
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onOpenClose(trade)}
            >
              Mark Closed
            </Button>
          </div>
        ),
        "Contract Q": contractQualityLabel(trade.source_pick_snapshot),
        Source: fmtCompactLabel(trade.source_pick_snapshot?.selection_source || trade.source_pick_snapshot?.promotion_class),
        "Entry Basis": fmtCompactLabel(trade.entry_execution_basis || trade.source_pick_snapshot?.entry_execution_basis),
        Quote: renderQuoteCell(trade),
        Expiry: renderExpiryCell(trade),
        Reviewed: renderReviewedCell(trade),
        Reason: trade.last_recommendation_reason || trade.latest_review?.reason || "\u2014",
      };
    }

    return {
      Ticker: trade.ticker,
      Trade: trade.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      Entry: fmtMoney(trade.entry_option_price),
      "Exit Px": fmtMoney(getRealizedExitPrice(trade)),
      "Realized P&L %": renderRealizedPnlCell(displayPnl),
      Recommendation: trade.last_recommendation || "\u2014",
      Action: <span className="text-xs text-text-3">{trade.exit_reason || "manual_hypothetical_close"}</span>,
      "Contract Q": contractQualityLabel(trade.source_pick_snapshot),
      Source: fmtCompactLabel(trade.source_pick_snapshot?.selection_source || trade.source_pick_snapshot?.promotion_class),
      "Entry Basis": fmtCompactLabel(trade.entry_execution_basis || trade.source_pick_snapshot?.entry_execution_basis),
      Quote: fmtPricingSource(trade.latest_review?.pricing_source),
      Expiry: fmtDate(getResolvedListedExpiry(trade)),
      Reviewed: fmtDateTime(getReviewedAt(trade)),
      Reason: trade.last_recommendation_reason || trade.latest_review?.reason || "\u2014",
      Closed: fmtDate(trade.closed_at),
    };
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div className="max-w-3xl">
          <div className="section-header mt-0">Suggested Trades (Hypothetical)</div>
          <p className="text-xs text-text-3">
            Manual paper-tracked ideas from the scanner. Open trades reprice automatically here, and stay separate from positions you actually took.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={view === "open" ? "secondary" : "ghost"}
            onClick={() => onViewChange("open")}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant={view === "closed" ? "secondary" : "ghost"}
            onClick={() => onViewChange("closed")}
          >
            Closed
          </Button>
          {view === "open" ? (
            <>
              <Button
                size="sm"
                variant={openFilter === "share-safe" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("share-safe")}
              >
                Share-Safe
              </Button>
              <Button
                size="sm"
                variant={openFilter === "all" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("all")}
              >
                All Open
              </Button>
            </>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
          <CompactStat label="Open Trades" value={String(openTrades.length)} />
          <CompactStat label="Share-Safe" value={String(shareSafeOpenTrades.length)} help={`${hiddenOpenTradeCount} hidden from share-safe view`} />
          <CompactStat label="Closed" value={String(closedTrades.length)} />
          <CompactStat label="Avg Open P&L" value={fmtPct(avgOpenPnl)} />
          <CompactStat label="Avg Closed P&L" value={fmtPct(avgClosedPnl)} help={`Last HOLD ${holdCount} / SELL ${sellCount}`} />
        </div>
      )}

      {!error && view === "open" ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-2 text-xs text-text-2">
          {openFilter === "share-safe"
            ? `Showing only exact or comparable-exact trades with fresh live option pricing from the last ${SHARE_SAFE_REVIEW_MAX_AGE_MINUTES} minutes. ${hiddenOpenTradeCount} open trade(s) are hidden.`
            : `Showing all open trades, including rows that are estimated, stale, or not exact-contract priced. ${shareSafeOpenTrades.length} open trade(s) are exact or comparable-exact live-priced right now.`}
        </div>
      ) : null}

      {trades.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          {view === "open"
            ? (openFilter === "share-safe" && dedupedOpenTrades.length > 0
              ? "No share-safe suggested trades yet. Refresh to live-price exact or comparable-exact rows, or switch to All Open to see estimated entries."
              : "No suggested trades yet.")
            : "No closed suggested trades yet."}
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          pnlCols={view === "open" ? [] : ["Realized P&L %"]}
          monoCols={view === "open" ? ["Contract Q", "Entry Basis", "Entry"] : ["Contract Q", "Entry Basis", "Entry", "Exit Px", "Reviewed", "Expiry"]}
          label="Suggested trades"
          maxHeight={view === "open" ? "min(60vh, 760px)" : "min(64vh, 820px)"}
        />
      )}
    </div>
  );
}

function LanePositionPanel({
  title,
  subtitle,
  emptyMessage,
  rows,
  view,
  tableMaxHeight,
}: {
  title: string;
  subtitle: string;
  emptyMessage: string;
  rows: Record<string, unknown>[];
  view: "open" | "closed";
  tableMaxHeight: string;
}) {
  return (
    <section className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
        <div>
          <div className="text-sm font-semibold text-text-0">{title}</div>
          <div className="text-xs text-text-3">{subtitle}</div>
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          {emptyMessage}
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          pnlCols={[]}
          monoCols={view === "open" ? ["Taken", "Entry", "Target", "Stop"] : ["Taken", "Entry", "Exit Px", "Reviewed", "Expiry", "Target", "Stop", "Closed"]}
          label={`${title} tracked options positions`}
          density="compact"
          maxHeight={tableMaxHeight}
        />
      )}
    </section>
  );
}

function TrackedPositionsTab({
  openPositions,
  closedPositions,
  loading,
  error,
  view,
  reviewingIds,
  onViewChange,
  onRefresh,
  onReviewPosition,
  onOpenClose,
}: {
  openPositions: TrackedPosition[];
  closedPositions: TrackedPosition[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  onViewChange: (value: "open" | "closed") => void;
  onRefresh: () => void;
  onReviewPosition: (positionId: number) => void;
  onOpenClose: (position: TrackedPosition) => void;
}) {
  const dedupedOpenPositions = openPositions;
  const [openFilter, setOpenFilter] = useState<"share-safe" | "all">("all");
  const [entryDatePreset, setEntryDatePreset] = useState<EntryDateFilterPreset>("all");
  const [entryDateValue, setEntryDateValue] = useState("");
  const shareSafeOpenPositions = dedupedOpenPositions.filter((position) => isShareSafeLivePosition(position));
  const hiddenOpenPositionCount = Math.max(dedupedOpenPositions.length - shareSafeOpenPositions.length, 0);
  const openBasePositions = openFilter === "share-safe" ? shareSafeOpenPositions : dedupedOpenPositions;
  const filteredOpenPositions = openBasePositions.filter((position) =>
    matchesEntryDateFilter(getTradeDateFilterValue(position), entryDatePreset, entryDateValue)
  );
  const filteredClosedPositions = closedPositions.filter((position) =>
    matchesEntryDateFilter(getTradeDateFilterValue(position), entryDatePreset, entryDateValue)
  );
  const proofOpenPositions = filteredOpenPositions.filter((position) => position.proof_eligible);
  const proofClosedPositions = filteredClosedPositions.filter((position) => position.proof_eligible);
  const basePositions = view === "open" ? openBasePositions : closedPositions;
  const positions = view === "open" ? filteredOpenPositions : filteredClosedPositions;
  const normalLanePositions = positions.filter((position) => !isCommodityLanePosition(position));
  const commodityLanePositions = positions.filter(isCommodityLanePosition);
  const hiddenByEntryDateCount = Math.max(basePositions.length - positions.length, 0);
  const holdCount = dedupedOpenPositions.filter((position) => getLatestRecommendation(position) === "HOLD").length;
  const sellCount = filteredOpenPositions.filter((position) => getLatestRecommendation(position) === "SELL").length;
  const unpricedCount = dedupedOpenPositions.filter((position) => {
    const source = position.latest_review?.pricing_source || null;
    return source === "unavailable" || source === "expired" || source == null;
  }).length;
  const avgOpenExitPnlPct = calcAveragePositionPnlPct(filteredOpenPositions, getCloseNowPnlPct);
  const weightedOpenExitPnlPct = calcWeightedPositionPnlPct(filteredOpenPositions, getCloseNowPnlUsd);
  const totalOpenExitPnlUsd = calcTotalPositionPnlUsd(filteredOpenPositions, getCloseNowPnlUsd);
  const totalProofOpenExitPnlUsd = calcTotalPositionPnlUsd(proofOpenPositions, getCloseNowPnlUsd);
  const totalOpenCostRiskUsd = calcTotalPositionCostRiskUsd(filteredOpenPositions);
  const visibleSellPositions = filteredOpenPositions.filter((position) => getLatestRecommendation(position) === "SELL");
  const sellOpenPnlUsd = calcTotalPositionPnlUsd(
    visibleSellPositions,
    getCloseNowPnlUsd
  );
  const concentrationWarning = getConcentrationWarning(dedupedOpenPositions);
  const tickerConcentrationLabel = topCountSummary(countByLabel(dedupedOpenPositions, (position) => position.ticker));
  const avgRealizedExitPnlPct = calcAveragePositionPnlPct(filteredClosedPositions, getRealizedPnlPct);
  const realizedExitPnlPct = calcWeightedPositionPnlPct(filteredClosedPositions, getRealizedPnlUsd);
  const totalRealizedExitPnlUsd = calcTotalPositionPnlUsd(filteredClosedPositions, getRealizedPnlUsd);
  const totalProofRealizedExitPnlUsd = calcTotalPositionPnlUsd(proofClosedPositions, getRealizedPnlUsd);
  const realizedExtremes = getPnlExtremes(filteredClosedPositions, getRealizedPnlPct);
  const openReviewSummary = view === "open" ? getCollectionReviewSummary(positions) : null;
  const tableMaxHeight = view === "open"
    ? "min(calc(100vh - 18rem), 920px)"
    : "min(calc(100vh - 17rem), 940px)";
  const lanePnlLabel = view === "open" ? "MTM" : "Realized";
  const normalLanePnlUsd = calcTotalPositionPnlUsd(
    normalLanePositions,
    view === "open" ? getCloseNowPnlUsd : getRealizedPnlUsd
  );
  const commodityLanePnlUsd = calcTotalPositionPnlUsd(
    commodityLanePositions,
    view === "open" ? getCloseNowPnlUsd : getRealizedPnlUsd
  );

  const buildRows = (items: TrackedPosition[]) =>
    items.map((position) => {
      const targetPct = position.profit_target_pct;
      const stopPct = position.stop_loss_pct;
      const realizedPnl = getRealizedPnlPct(position);
      if (view === "open") {
        return {
          __rowKey: position.id,
          Ticker: position.ticker,
          Trade: position.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
          Taken: fmtTakenDate(position),
          Entry: fmtMoney(position.entry_option_price),
          "Live Px": renderOpenPriceCell(position),
          "Live P&L": renderOpenPnlCell(position),
          Status: renderPositionStatusCell(position),
          Action: (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                loading={reviewingIds.includes(position.id)}
                onClick={() => onReviewPosition(position.id)}
              >
                Review
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onOpenClose(position)}
              >
                Mark Closed
              </Button>
            </div>
          ),
          Target: fmtTargetLabel(position, position.entry_option_price, targetPct),
          Stop: fmtStopLabel(position.entry_option_price, stopPct),
          Quote: renderQuoteCell(position),
          Expiry: renderExpiryCell(position),
        };
      }

      return {
        __rowKey: position.id,
        Ticker: position.ticker,
        Trade: position.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
        Taken: fmtTakenDate(position),
        Entry: fmtMoney(position.entry_option_price),
        "Exit Px": fmtMoney(getRealizedExitPrice(position)),
        "Realized P&L %": renderRealizedPnlCell(realizedPnl),
        Recommendation: position.last_recommendation || "\u2014",
        Action: <span className="text-xs text-text-3">{position.exit_reason || "manual_close"}</span>,
        Target: fmtTargetLabel(position, position.entry_option_price, targetPct),
        Stop: fmtStopLabel(position.entry_option_price, stopPct),
        Quote: fmtPricingSource(position.latest_review?.pricing_source),
        Expiry: fmtDate(getResolvedListedExpiry(position)),
        Reviewed: fmtDateTime(getReviewedAt(position)),
        Closed: fmtDate(position.closed_at),
      };
    });

  const normalRows = buildRows(normalLanePositions);
  const commodityRows = buildRows(commodityLanePositions);

  return (
    <div className="space-y-2">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-2">
        <div className="max-w-3xl">
          <div className="section-header mt-0">Tracked Options Positions</div>
          <p className="text-xs text-text-3">
            These are the positions you actually took. Open positions refresh profit and HOLD/SELL guidance automatically while keeping exact contract identity when available.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={view === "open" ? "secondary" : "ghost"}
            onClick={() => onViewChange("open")}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant={view === "closed" ? "secondary" : "ghost"}
            onClick={() => onViewChange("closed")}
          >
            Closed
          </Button>
          {view === "open" ? (
            <>
              <Button
                size="sm"
                variant={openFilter === "share-safe" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("share-safe")}
              >
                Share-Safe
              </Button>
              <Button
                size="sm"
                variant={openFilter === "all" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("all")}
              >
                All Open
              </Button>
            </>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {!error && (
        <EntryDateFilterControls
          preset={entryDatePreset}
          customDate={entryDateValue}
          onPresetChange={setEntryDatePreset}
          onCustomDateChange={setEntryDateValue}
        />
      )}

      {!error && view === "open" ? (
        <div className="grid grid-cols-2 lg:grid-cols-8 gap-1.5">
          <CompactStat label="Open Positions" value={String(openPositions.length)} />
          <CompactStat label="Visible Open" value={String(filteredOpenPositions.length)} help="Matches the rows currently included by the open filters" />
          <CompactStat label="Cost Risk" value={fmtMoney(totalOpenCostRiskUsd)} help="Entry debit at risk for visible open positions before any open profit is harvested" />
          <CompactStat label="Tracked MTM" value={fmtSignedMoney(totalOpenExitPnlUsd)} help="Executable mark-to-market P&L for every visible tracked open position, including non-proof comparable/manual rows" />
          <CompactStat label="SELL P&L" value={`${fmtSignedMoney(sellOpenPnlUsd)} (${sellCount})`} help={`${sellCount} visible open position(s) currently carry SELL guidance`} />
          <CompactStat label="Proof Rows" value={`${proofOpenPositions.length}/${filteredOpenPositions.length}`} help="Proof-eligible rows divided by visible tracked rows" />
          <CompactStat label="Weighted Exit P&L" value={fmtPct(weightedOpenExitPnlPct)} help={`Average ${fmtPct(avgOpenExitPnlPct)}; entry-cost-weighted across visible rows`} />
          <CompactStat label="Portfolio Conc." value={tickerConcentrationLabel} help={concentrationWarning || "Largest open ticker cluster before visible filters"} />
          <CompactStat label="Share-Safe" value={String(shareSafeOpenPositions.length)} help={`${hiddenOpenPositionCount} hidden from share-safe view; last HOLD ${holdCount}; unpriced ${unpricedCount}; proof MTM ${fmtSignedMoney(totalProofOpenExitPnlUsd)}`} />
        </div>
      ) : !error ? (
        <div className="grid grid-cols-2 lg:grid-cols-8 gap-1.5">
          <CompactStat label="Closed Positions" value={String(closedPositions.length)} />
          <CompactStat label="Visible Closed" value={String(filteredClosedPositions.length)} help="Matches the rows currently included by the closed filters" />
          <CompactStat label="Tracked Realized" value={fmtSignedMoney(totalRealizedExitPnlUsd)} help="Realized P&L for every visible tracked closed position, including non-proof comparable/manual rows" />
          <CompactStat label="Proof Realized" value={fmtSignedMoney(totalProofRealizedExitPnlUsd)} help="Realized P&L from visible positions that meet strict proof-lane eligibility" />
          <CompactStat label="Proof Rows" value={`${proofClosedPositions.length}/${filteredClosedPositions.length}`} help="Proof-eligible rows divided by visible tracked closed rows" />
          <CompactStat label="Avg Realized P&L" value={fmtPct(avgRealizedExitPnlPct)} help="Simple average of the visible closed-trade realized P&L percentages" />
          <CompactStat label="Weighted Realized P&L" value={fmtPct(realizedExitPnlPct)} help="Entry-cost-weighted average of the visible closed-trade realized P&L values" />
          <CompactStat label="Best Closed" value={fmtPct(realizedExtremes.best)} />
        </div>
      ) : null}

      {!error && view === "open" ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-1.5 text-xs text-text-2 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
          <span>
            {openFilter === "share-safe"
              ? `Showing only exact or comparable-exact positions with fresh live option pricing from the last ${SHARE_SAFE_REVIEW_MAX_AGE_MINUTES} minutes. ${hiddenOpenPositionCount} open position(s) are hidden.`
              : `Showing all open positions, including rows that are estimated, stale, or not exact-contract priced. ${shareSafeOpenPositions.length} open position(s) are exact or comparable-exact live-priced right now.`}
            {entryDatePreset !== "all"
              ? ` Entry-date filter is showing ${positions.length} of ${basePositions.length} position(s) from ${entryDateFilterLabel(entryDatePreset, entryDateValue)}.`
              : ""}
            {` Tracked P&L includes every visible position; Proof P&L only includes strict proof-eligible rows.`}
            {concentrationWarning ? ` Portfolio concentration: ${concentrationWarning}` : ""}
          </span>
          {openReviewSummary ? (
            <span className="text-text-1 whitespace-nowrap">{openReviewSummary}</span>
          ) : null}
        </div>
      ) : !error && entryDatePreset !== "all" ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-2 text-xs text-text-2">
          Showing {positions.length} of {basePositions.length} closed position(s) from {entryDateFilterLabel(entryDatePreset, entryDateValue)}.
        </div>
      ) : null}

      {positions.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          {view === "open"
            ? (openFilter === "share-safe" && dedupedOpenPositions.length > 0
              ? "No share-safe tracked positions match that entry date yet. Refresh to live-price exact or comparable-exact rows, or switch to All Open to inspect estimated entries."
              : hiddenByEntryDateCount > 0
                ? "No tracked positions match that entry date filter."
                : "No tracked positions yet.")
            : hiddenByEntryDateCount > 0
              ? "No closed tracked positions match that entry date filter."
              : "No closed tracked positions yet."}
        </div>
      ) : (
        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
          <LanePositionPanel
            title="Normal Options Lane"
            subtitle={`${normalLanePositions.length} ${view} | ${lanePnlLabel} ${fmtSignedMoney(normalLanePnlUsd)}`}
            emptyMessage={`No normal-lane ${view} positions match the current filters.`}
            rows={normalRows}
            view={view}
            tableMaxHeight={tableMaxHeight}
          />
          <LanePositionPanel
            title="Commodity Lane"
            subtitle={`${commodityLanePositions.length} ${view} | ${lanePnlLabel} ${fmtSignedMoney(commodityLanePnlUsd)}`}
            emptyMessage={`No commodity-lane ${view} positions match the current filters.`}
            rows={commodityRows}
            view={view}
            tableMaxHeight={tableMaxHeight}
          />
        </div>
      )}
    </div>
  );
}

