import type { ScanPick, SuggestedTrade, TrackedPosition } from "@/lib/types";
import {
  getPositionEvidenceDescriptor,
  type PositionEvidenceTone,
} from "@/lib/trading-desk/positionEvidence";
import { fmtDate, fmtMoney } from "@/components/predictions/tradingDeskFormat";

export const ALL_POSITION_LANES = "__all__";
export const COMMODITY_PLAYBOOK_ID = "ai_commodity_infra_observation";

const RECENT_TRADE_WINDOW_MS = 24 * 60 * 60 * 1000;

export type EntryDateFilterPreset = "all" | "today" | "yesterday" | "last7" | "custom";

export type PositionLaneOption = {
  id: string;
  label: string;
  count: number;
};

type TradeDateSource = {
  filled_at?: string | null;
  source_pick_snapshot?: Partial<ScanPick> | null;
};

export type ContractDisplaySource = {
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

export function matchesEntryDateFilter(
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

export function entryDateFilterLabel(preset: EntryDateFilterPreset, customDate: string): string {
  if (preset === "today") return "today";
  if (preset === "yesterday") return "yesterday";
  if (preset === "last7") return "the last 7 days";
  if (preset === "custom" && customDate) return customDate;
  return "all entry dates";
}

function scanPickText(
  pick: Partial<ScanPick> | null | undefined,
  keys: string[]
): string | null {
  if (!pick) return null;
  const record = pick as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (value == null) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return null;
}

function parseTimestampMs(value?: string | null): number | null {
  if (!value || !value.includes("T")) return null;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function getTakenTimestampMs(position: TradeDateSource): number | null {
  const source = position.source_pick_snapshot || null;
  const candidates = [
    source?.entry_quote_snapshot?.captured_at_utc,
    source?.quote_time_utc,
    source?.entry_quote_snapshot?.captured_at_et,
    source?.quote_time_et,
    position.filled_at,
  ];

  for (const candidate of candidates) {
    const parsed = parseTimestampMs(candidate);
    if (parsed != null) return parsed;
  }
  return null;
}

export function isTakenWithinLast24Hours(position: TradeDateSource): boolean {
  const takenAt = getTakenTimestampMs(position);
  if (takenAt == null) return false;
  const ageMs = Date.now() - takenAt;
  return ageMs >= 0 && ageMs <= RECENT_TRADE_WINDOW_MS;
}

export function getSignalGivenDateValue(position: TradeDateSource): string | null {
  const source = position.source_pick_snapshot || null;
  const candidates = [
    scanPickText(source, ["signal_date", "scan_date", "trade_date", "date"]),
    source?.entry_quote_snapshot?.captured_at_et,
    source?.quote_time_et,
    scanPickText(source, ["logged_at", "source_scan_recorded_at_utc", "quote_timestamp_et"]),
    source?.entry_quote_snapshot?.captured_at_utc,
    source?.quote_time_utc,
    scanPickText(source, ["quote_timestamp_utc"]),
    position.filled_at,
  ];

  for (const candidate of candidates) {
    const normalized = getEntryDateValue(candidate);
    if (normalized) return normalized;
  }
  return null;
}

function getTrustedTakenDateValue(position: TradeDateSource): string | null {
  const signalDate = getSignalGivenDateValue(position);
  if (signalDate && !isWeekendDateValue(signalDate)) return signalDate;
  return null;
}

function getRawTakenDateValue(position: TradeDateSource): string | null {
  return getEntryDateValue(position.filled_at);
}

export function getTradeDateFilterValue(position: TradeDateSource): string | null {
  return getTrustedTakenDateValue(position) ?? getRawTakenDateValue(position);
}

export function fmtTakenDate(position: TradeDateSource): string {
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

export function fmtContractCoreLabel(position: {
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

export function fmtContractLabel(position: {
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

export function buildContractSignature(position: ContractDisplaySource): string {
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

function evidenceBadgeClass(tone: PositionEvidenceTone): string {
  if (tone === "live") return "border-green/40 bg-green-dim text-green";
  if (tone === "warning") return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-border bg-bg-3 text-text-2";
}

function titleCaseWords(value: string): string {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => {
      const upperTokens = new Set(["AI", "OPRA", "NBBO", "ETF"]);
      const normalized = word.toUpperCase();
      if (upperTokens.has(normalized)) return normalized;
      return `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`;
    })
    .join(" ");
}

function normalizeLaneId(value: string): string {
  const normalized = value.trim().toLowerCase();
  return normalized || "unlabeled";
}

function laneLabelFromId(value: string): string {
  return titleCaseWords(value.replaceAll("_", " ").replaceAll("-", " "));
}

function canonicalLaneDescriptor(rawId: string, rawLabel?: string | null): {
  id: string;
  label: string;
} {
  const id = normalizeLaneId(rawId);
  const label = String(rawLabel || "").trim();
  const searchable = `${id} ${label}`.toLowerCase();
  if (searchable.includes("bullish_pullback") || searchable.includes("bullish pullback")) {
    return { id: "bullish_pullback", label: "Bullish Pullback" };
  }
  if (id === COMMODITY_PLAYBOOK_ID || searchable.includes("ai_commodity") || searchable.includes("ai commodity")) {
    return { id: "ai_commodity", label: "AI Commodity" };
  }
  if (id === "legacy_scheduled_scan") {
    return { id, label: "Legacy Scheduled Scan" };
  }
  return { id, label: label || laneLabelFromId(id) };
}

export function displayLaneLabel(rawId: string, rawLabel?: string | null): string {
  return canonicalLaneDescriptor(rawId, rawLabel).label;
}

export function getPositionLaneDescriptor(position: TrackedPosition | SuggestedTrade): {
  id: string;
  label: string;
  detail: string | null;
} {
  const source = position.source_pick_snapshot || null;
  const notes = "notes" in position ? String(position.notes || "") : "";
  const scheduledLegacy = notes.toLowerCase().includes("scheduled daily scan");
  const rawPlaybookId =
    source?.playbook_id ||
    source?.playbook ||
    (isCommodityLanePosition(position) ? COMMODITY_PLAYBOOK_ID : null) ||
    (scheduledLegacy ? "legacy_scheduled_scan" : null) ||
    source?.strategy_label ||
    source?.ai_commodity_bucket ||
    source?.cohort_id ||
    "unlabeled";
  const rawPlaybookLabel =
    source?.playbook_label ||
    source?.strategy_label ||
    (scheduledLegacy ? "Legacy Scheduled Scan" : null) ||
    (rawPlaybookId === COMMODITY_PLAYBOOK_ID ? "AI Commodity" : null) ||
    laneLabelFromId(String(rawPlaybookId));
  const lane = canonicalLaneDescriptor(String(rawPlaybookId), rawPlaybookLabel);

  return {
    ...lane,
    detail: null,
  };
}

export function buildPositionLaneOptions(items: TrackedPosition[]): PositionLaneOption[] {
  const optionsById = new globalThis.Map<string, PositionLaneOption>();
  for (const item of items) {
    const lane = getPositionLaneDescriptor(item);
    const existing = optionsById.get(lane.id);
    if (existing) {
      existing.count += 1;
    } else {
      optionsById.set(lane.id, { id: lane.id, label: lane.label, count: 1 });
    }
  }

  return Array.from(optionsById.values()).sort((a, b) =>
    b.count - a.count || a.label.localeCompare(b.label)
  );
}

export function matchesPositionLaneFilter(position: TrackedPosition, laneFilter: string): boolean {
  return laneFilter === ALL_POSITION_LANES || getPositionLaneDescriptor(position).id === laneFilter;
}

export function positionLaneFilterLabel(laneFilter: string, options: PositionLaneOption[]): string | null {
  if (laneFilter === ALL_POSITION_LANES) return null;
  return options.find((option) => option.id === laneFilter)?.label || null;
}

export function laneMixSummary(options: PositionLaneOption[]): string {
  if (!options.length) return "Lane mix: none.";
  const visible = options.slice(0, 3).map((option) => `${option.label} ${option.count}`);
  const remainder = options.length - visible.length;
  return `Lane mix: ${visible.join(" / ")}${remainder > 0 ? ` / +${remainder} more` : ""}.`;
}

export function renderPositionLaneCell(position: TrackedPosition | SuggestedTrade) {
  const lane = getPositionLaneDescriptor(position);
  const evidence = getPositionEvidenceDescriptor(position);
  const evidenceTitle = `${evidence.label}: ${evidence.detail}`;
  const signalDate = getSignalGivenDateValue(position);
  return (
    <div className="min-w-[138px] max-w-[178px] space-y-1 leading-tight">
      <div className="text-sm font-semibold text-text-0">{lane.label}</div>
      {lane.detail ? (
        <div className="text-xs text-text-3">{lane.detail}</div>
      ) : null}
      <div className="text-xs text-text-2">
        {signalDate ? `Signal ${signalDate}` : "Signal date unknown"}
      </div>
      <span
        className={`inline-flex max-w-full items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none ${evidenceBadgeClass(evidence.tone)}`}
        title={evidenceTitle}
        aria-label={`Evidence: ${evidenceTitle}`}
      >
        {evidence.label}
      </span>
    </div>
  );
}

export function renderTickerCell(position: TrackedPosition | SuggestedTrade) {
  const recent = isTakenWithinLast24Hours(position);
  return (
    <div className="flex min-w-[84px] flex-wrap items-center gap-1.5">
      <span className="font-mono text-sm text-text-0">{position.ticker}</span>
      {recent ? (
        <span
          className="rounded border border-green/40 bg-green-dim px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none text-green"
          title="Taken in the last 24 hours"
          aria-label="Taken in the last 24 hours"
        >
          24h
        </span>
      ) : null}
    </div>
  );
}

export function latestDateValue(current: string | null, candidate: string | null): string | null {
  if (!candidate) return current;
  if (!current || candidate > current) return candidate;
  return current;
}
