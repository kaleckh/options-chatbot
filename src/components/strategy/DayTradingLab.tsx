"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, AlertTriangle, BellRing, CalendarClock, CheckCircle2, Clock3, FileText, Loader2, Play, RefreshCw, ShieldCheck, Ticket, Trophy } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import type {
  DayTradingProfitabilityTicket,
  DayTradingExperimentReport,
  DayTradingReport,
  DayTradingOperatingPlan,
  DayTradingPilotSummary,
  DayTradingSnapshot,
  DayTradingStrategySpec,
  DayTradingWatchlist,
} from "@/lib/types";

type DayTradingMarket = "crypto" | "equities_legacy";
type MarketInputState = { bars: number; startingCash: number };
type PreflightChecklistState = {
  setup_match_confirmed: boolean;
  headline_lockout_checked: boolean;
  maker_limit_plan_confirmed: boolean;
};
type PreflightResult = {
  approved: boolean;
  blocked: boolean;
  reasons: string[];
  ticket: {
    ticketId: string;
    approvedAt: string | null;
    sessionLabel: string | null;
    symbol: string;
  } | null;
  systemGate?: {
    regimeState?: string;
    dataFresh?: boolean;
    costProfile?: {
      allowed?: boolean;
      costToTargetFraction?: number | null;
    };
    todayGate?: {
      approvedEntries: number;
      dailyTradeCap: number;
      remainingApprovals: number;
    };
  } | null;
};
type PreflightResponse = {
  result: PreflightResult;
  snapshot: DayTradingSnapshot;
};
type JournalFormState = {
  ticketId: string;
  tradeTimestampLocal: string;
  sessionLabel: string;
  symbol: string;
  regime: string;
  setupId: string;
  side: string;
  setup_match_confirmed: boolean;
  headline_lockout_checked: boolean;
  maker_limit_plan_confirmed: boolean;
  plannedEntryPrice: string;
  actualEntryPrice: string;
  stopPrice: string;
  targetPrice: string;
  actualExitPrice: string;
  orderType: string;
  entryLiquidityRole: string;
  exitLiquidityRole: string;
  entryFillRatio: string;
  exitFillRatio: string;
  exitReason: string;
  stopExecutionQuality: string;
  sizeUsd: string;
  feesUsd: string;
  spreadSlippageUsd: string;
  pnlR: string;
  pnlUsd: string;
  screenshotPath: string;
  ruleAdherenceScore: string;
  mistakeTag: string;
  note: string;
};
type JournalResult = {
  entry: {
    entryId: string;
    ticketId: string;
    pilotEligible: boolean;
    pilotDisqualificationReasons: string[];
    loggedAt: string;
  };
  summary: DayTradingPilotSummary;
};
type JournalResponse = JournalResult & {
  snapshot: DayTradingSnapshot;
};
type JournalAggregateSummary = {
  label: string;
  totalEntries: number;
  eligibleEntries: number;
  disqualifiedEntries: number;
  netPnlUsd: number;
  eligibleNetPnlUsd: number;
  expectancyR: number | null;
  winRate: number | null;
  ruleAdherenceRate: number | null;
};

const DEFAULT_PREFLIGHT_CHECKLIST: PreflightChecklistState = {
  setup_match_confirmed: false,
  headline_lockout_checked: false,
  maker_limit_plan_confirmed: false,
};

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function localDateTimeInputValue(date: Date = new Date()): string {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toIsoFromLocalInput(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString();
}

function deriveRegimeFromTicket(ticket: DayTradingProfitabilityTicket | null | undefined): string {
  const value = String(ticket?.regimeState || "").toLowerCase();
  if (value.includes("trend")) return "trend";
  if (value.includes("event")) return "event";
  return "range";
}

function buildJournalDraft(ticket?: DayTradingProfitabilityTicket | null): JournalFormState {
  return {
    ticketId: ticket?.ticketId || "",
    tradeTimestampLocal: localDateTimeInputValue(),
    sessionLabel: ticket?.sessionLabel || "Denver Core",
    symbol: ticket?.symbol || "BTCUSDT",
    regime: deriveRegimeFromTicket(ticket),
    setupId: ticket?.strategyId || "btcusdt-crypto-range-mean-reversion",
    side: "buy",
    setup_match_confirmed: ticket?.checklistFlags?.setup_match_confirmed ?? true,
    headline_lockout_checked: ticket?.checklistFlags?.headline_lockout_checked ?? true,
    maker_limit_plan_confirmed: ticket?.checklistFlags?.maker_limit_plan_confirmed ?? true,
    plannedEntryPrice: "",
    actualEntryPrice: "",
    stopPrice: "",
    targetPrice: "",
    actualExitPrice: "",
    orderType: "limit",
    entryLiquidityRole: "maker",
    exitLiquidityRole: "maker",
    entryFillRatio: "1",
    exitFillRatio: "1",
    exitReason: "target_hit",
    stopExecutionQuality: "not_applicable",
    sizeUsd: "",
    feesUsd: "0",
    spreadSlippageUsd: "0",
    pnlR: "",
    pnlUsd: "",
    screenshotPath: "",
    ruleAdherenceScore: "100",
    mistakeTag: "none",
    note: "",
  };
}

const MARKET_OPTIONS: { value: DayTradingMarket; label: string; description: string }[] = [
  {
    value: "crypto",
    label: "Crypto",
    description: "Default research lane using free Binance-style spot data.",
  },
  {
    value: "equities_legacy",
    label: "Equities Legacy",
    description: "Previous Yahoo-based ETF morning lab kept for comparison.",
  },
];
const MARKET_INPUT_DEFAULTS: Record<DayTradingMarket, MarketInputState> = {
  crypto: {
    bars: 3120,
    startingCash: 10000,
  },
  equities_legacy: {
    bars: 3120,
    startingCash: 10000,
  },
};

function pct(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function money(value: number | null | undefined, digits: number = 0): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `$${value.toFixed(digits)}`;
}

function ratio(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}x`;
}

function bps(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)} bps`;
}

function phaseLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace(/_/g, " ");
}

function statusTone(status: string): string {
  switch (status) {
    case "candidate_live":
      return "text-green";
    case "promotion_review":
      return "text-amber";
    case "paper_live":
      return "text-accent";
    case "backtest_failed":
    case "disabled":
      return "text-red";
    default:
      return "text-text-2";
  }
}

function watchStatusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function labelize(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace(/_/g, " ");
}

function reasonLabel(value: string | null | undefined): string {
  if (!value) return "-";
  if (value.includes(":")) {
    const [prefix, suffix] = value.split(":");
    return `${labelize(prefix)}: ${labelize(suffix)}`;
  }
  return labelize(value);
}

function timeLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return value.slice(11, 16);
}

function toDateTimeLocalValue(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}

function formatDurationMinutes(totalMinutes: number): string {
  const rounded = Math.max(0, Math.round(totalMinutes));
  const hours = Math.floor(rounded / 60);
  const minutes = rounded % 60;
  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h ${pad(minutes)}m`;
}

function formatAgeLabel(value: string | null | undefined, nowMs: number = Date.now()): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  const deltaMs = nowMs - parsed.getTime();
  if (deltaMs < 0) return "just now";
  const deltaSeconds = Math.floor(deltaMs / 1000);
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const hours = Math.floor(deltaMinutes / 60);
  const minutes = deltaMinutes % 60;
  if (hours < 24) return minutes === 0 ? `${hours}h ago` : `${hours}h ${minutes}m ago`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours === 0 ? `${days}d ago` : `${days}d ${remainingHours}h ago`;
}

function parseClockMinutes(value: string | null | undefined): number | null {
  if (!value) return null;
  const normalized = value.trim().toUpperCase();
  const ampmMatch = normalized.match(/^(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*([AP]M)$/);
  if (ampmMatch) {
    let hours = Number(ampmMatch[1]);
    const minutes = Number(ampmMatch[2] || "0");
    const suffix = ampmMatch[3];
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
    hours = hours % 12;
    if (suffix === "PM") hours += 12;
    return hours * 60 + minutes;
  }
  const twentyFourHourMatch = normalized.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (twentyFourHourMatch) {
    const hours = Number(twentyFourHourMatch[1]);
    const minutes = Number(twentyFourHourMatch[2]);
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
    return hours * 60 + minutes;
  }
  const compactMatch = normalized.match(/^(\d{3,4})$/);
  if (compactMatch) {
    const digits = compactMatch[1];
    const hours = Number(digits.slice(0, digits.length - 2));
    const minutes = Number(digits.slice(-2));
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
    return hours * 60 + minutes;
  }
  return null;
}

function getTimeZoneMinutes(date: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(date);
  const hour = Number(parts.find((part) => part.type === "hour")?.value || "0");
  const minute = Number(parts.find((part) => part.type === "minute")?.value || "0");
  return hour * 60 + minute;
}

function getSessionClock(
  session: DayTradingOperatingPlan["session"] | undefined,
  sessionWindow: DayTradingWatchlist["sessionWindow"] | undefined,
  now: Date
) {
  const timeZone = session?.sessionTimeZone || "America/New_York";
  const windows = sessionWindow?.windows?.length
    ? sessionWindow.windows
    : (() => {
        const match = session?.localWindow?.match(/(\d{1,2}(?::\d{2})?\s*[AP]M?|\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}(?::\d{2})?\s*[AP]M?|\d{1,2}:\d{2})/i);
        if (!match) return [];
        return [{
          id: "session-local-window",
          label: session?.localWindow || "Session Window",
          startEt: match[1].replace(/\s+/g, " ").trim(),
          endEt: match[2].replace(/\s+/g, " ").trim(),
        }];
      })();
  const currentMinutes = getTimeZoneMinutes(now, timeZone);
  const currentLabel = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZoneName: "short",
  }).format(now);

  const parsedWindows = windows
    .map((window) => {
      const startMinutes = parseClockMinutes(window.startEt);
      const endMinutes = parseClockMinutes(window.endEt);
      if (startMinutes == null || endMinutes == null) return null;
      return { ...window, startMinutes, endMinutes };
    })
    .filter(Boolean) as Array<{ id: string; label: string; startEt: string; endEt: string; startMinutes: number; endMinutes: number }>;

  const activeWindow = sessionWindow?.activeWindowLabel
    ? parsedWindows.find((window) => window.id === sessionWindow.activeWindowId || window.label === sessionWindow.activeWindowLabel) || null
    : parsedWindows.find((window) => window.startMinutes <= currentMinutes && currentMinutes < window.endMinutes) || null;

  const nextWindow = parsedWindows.find((window) => window.startMinutes > currentMinutes) || parsedWindows[0] || null;
  const active = Boolean(activeWindow);
  const minutesToClose = activeWindow ? Math.max(0, activeWindow.endMinutes - currentMinutes) : null;
  const minutesToOpen = nextWindow
    ? nextWindow.startMinutes > currentMinutes
      ? nextWindow.startMinutes - currentMinutes
      : (24 * 60 - currentMinutes) + nextWindow.startMinutes
    : null;

  return {
    timeZone,
    currentLabel,
    active,
    activeWindowLabel: activeWindow?.label || sessionWindow?.activeWindowLabel || null,
    nextWindowLabel: active ? null : nextWindow?.label || null,
    countdown: active
      ? minutesToClose == null
        ? "live"
        : `${formatDurationMinutes(minutesToClose)} remaining`
      : minutesToOpen == null
        ? "session closed"
        : `${formatDurationMinutes(minutesToOpen)} until next open`,
    windowLabels: parsedWindows.map((window) => `${window.label} ${window.startEt}-${window.endEt} ET`),
  };
}

function isSameLocalDay(left: string | null | undefined, right: Date): boolean {
  if (!left) return false;
  const leftDate = new Date(left);
  if (Number.isNaN(leftDate.getTime())) return false;
  return leftDate.toDateString() === right.toDateString();
}

function isWithinDays(left: string | null | undefined, right: Date, days: number): boolean {
  if (!left) return false;
  const leftDate = new Date(left);
  if (Number.isNaN(leftDate.getTime())) return false;
  const deltaMs = right.getTime() - leftDate.getTime();
  return deltaMs >= 0 && deltaMs <= days * 24 * 60 * 60 * 1000;
}

function summarizeJournalEntries(entries: NonNullable<DayTradingSnapshot["profitabilityJournal"]>["recentEntries"]) {
  const totalPnlUsd = entries.reduce((sum, entry) => sum + (entry.pnlUsd || 0), 0);
  const totalPnlR = entries.reduce((sum, entry) => sum + (entry.pnlR || 0), 0);
  const totalAdherence = entries.reduce((sum, entry) => sum + (entry.ruleAdherenceScore || 0), 0);
  const eligibleCount = entries.filter((entry) => entry.pilotEligible).length;
  const disqualifiedCount = entries.filter((entry) => !entry.pilotEligible).length;
  return {
    trades: entries.length,
    totalPnlUsd,
    totalPnlR,
    avgPnlUsd: entries.length ? totalPnlUsd / entries.length : null,
    avgPnlR: entries.length ? totalPnlR / entries.length : null,
    avgAdherence: entries.length ? totalAdherence / entries.length : null,
    eligibleCount,
    disqualifiedCount,
  };
}

function mapSummaryToAggregate(summary: ReturnType<typeof summarizeJournalEntries>, label: string): JournalAggregateSummary {
  const eligibleDenominator = Math.max(1, summary.eligibleCount);
  return {
    label,
    totalEntries: summary.trades,
    eligibleEntries: summary.eligibleCount,
    disqualifiedEntries: summary.disqualifiedCount,
    netPnlUsd: summary.totalPnlUsd,
    eligibleNetPnlUsd: summary.totalPnlUsd,
    expectancyR: summary.avgPnlR,
    winRate: null,
    ruleAdherenceRate: summary.avgAdherence == null ? null : summary.avgAdherence / 100,
  };
}

function buildAggregateReviewRows(items: JournalAggregateSummary[] | undefined, labelKey: string) {
  return (items || []).map((item) => ({
    [labelKey]: labelize(item.label),
    Trades: String(item.totalEntries || 0),
    "Net PnL": money(item.netPnlUsd, 2),
    "Eligible PnL": money(item.eligibleNetPnlUsd, 2),
    "Avg R": item.expectancyR == null ? "-" : item.expectancyR.toFixed(2),
    "Win Rate": pct(item.winRate),
    Adherence: pct(item.ruleAdherenceRate),
    Eligible: `${item.eligibleEntries || 0}/${item.totalEntries || 0}`,
    Disqualified: String(item.disqualifiedEntries || 0),
  }));
}

function experimentReportFromPayload(payload: unknown): DayTradingExperimentReport | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const record = payload as Record<string, unknown>;
  const nested = record.report || record.experimentReport || (record.snapshot && typeof record.snapshot === "object" ? (record.snapshot as Record<string, unknown>).experimentReport : null);
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    return nested as DayTradingExperimentReport;
  }
  if ("generatedAt" in record && ("results" in record || "leaders" in record || "recommendation" in record)) {
    return record as unknown as DayTradingExperimentReport;
  }
  return null;
}

function marketCopy(market: DayTradingMarket) {
  if (market === "equities_legacy") {
    return {
      title: "Day Trading Lab",
      description:
        "Legacy ETF morning lab that tracks SPY/QQQ replay evidence and paper activity. This lane is still available for comparison, but crypto is now the default active research track.",
      watchlistTitle: "Morning Watchlist",
      windowActive: "Morning window live",
      windowInactive: "Outside morning window",
    };
  }
  return {
    title: "Crypto Day Trading Lab",
    description:
      "Profitability pilot for BTC-first crypto spot trading. The active live lane is a rules-first BTC range mean-reversion setup in one fixed session, while ETH stays locked until phase 1 passes and SOL remains paper-only.",
    watchlistTitle: "Fixed Session Watchlist",
    windowActive: "Core session live",
    windowInactive: "Outside fixed session",
  };
}

function StrategyCard({ strategy }: { strategy: DayTradingStrategySpec }) {
  return (
    <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-text-0">{strategy.name}</div>
          <div className="text-xs text-text-3 mt-1">
            {strategy.marketUniverse.symbols.join(", ")} - {strategy.evaluationWindow.timeframe} - {strategy.simulation.entrySignal}
          </div>
        </div>
        <div className={`text-xs font-semibold uppercase tracking-wide ${statusTone(strategy.status)}`}>
          {strategy.status.replace(/_/g, " ")}
        </div>
      </div>

      <p className="text-sm text-text-2 leading-relaxed">{strategy.hypothesisSummary}</p>

      {strategy.metadata?.unlockPhase && (
        <div className="text-xs text-text-3 uppercase tracking-wide">
          Unlock phase: {strategy.metadata.unlockPhase.replace(/_/g, " ")}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="bg-bg-3 border border-border rounded-md p-3">
          <div className="text-text-3 uppercase tracking-wide mb-1">Entry</div>
          <div className="text-text-1">Threshold: {strategy.simulation.useSignalStrengthThreshold?.toFixed(2) || "-"}</div>
          <div className="text-text-2 mt-1">Warmup: {strategy.evaluationWindow.warmupBars} bars</div>
          <div className="text-text-2 mt-1">Cooldown: {strategy.simulation.cooldownBars} bars</div>
        </div>
        <div className="bg-bg-3 border border-border rounded-md p-3">
          <div className="text-text-3 uppercase tracking-wide mb-1">Risk</div>
          <div className="text-text-1">TP / SL: {pct(strategy.simulation.takeProfitFraction)} / {pct(strategy.simulation.stopLossFraction)}</div>
          <div className="text-text-2 mt-1">Max DD: {pct(strategy.riskLimits.maxDrawdownFraction)}</div>
          <div className="text-text-2 mt-1">Min trades: {strategy.evaluationWindow.minimumTrades}</div>
        </div>
      </div>

      <div className="text-xs text-text-3">
        <div>Entry rule: {strategy.entryRules[0]}</div>
        <div className="mt-1">Exit rule: {strategy.exitRules[0]}</div>
      </div>
    </div>
  );
}

export default function DayTradingLab() {
  const [snapshot, setSnapshot] = useState<DayTradingSnapshot | null>(null);
  const [watchlist, setWatchlist] = useState<DayTradingWatchlist | null>(null);
  const [market, setMarket] = useState<DayTradingMarket>("crypto");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [journalLoading, setJournalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preflightResult, setPreflightResult] = useState<PreflightResult | null>(null);
  const [preflightChecklist, setPreflightChecklist] = useState<PreflightChecklistState>(DEFAULT_PREFLIGHT_CHECKLIST);
  const [journalResult, setJournalResult] = useState<JournalResult | null>(null);
  const [journalTicketId, setJournalTicketId] = useState("");
  const [journalForm, setJournalForm] = useState<JournalFormState>(() => buildJournalDraft());
  const [bars, setBars] = useState(MARKET_INPUT_DEFAULTS.crypto.bars);
  const [startingCash, setStartingCash] = useState(MARKET_INPUT_DEFAULTS.crypto.startingCash);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [watchlistAutoRefresh, setWatchlistAutoRefresh] = useState(true);
  const [experimentReport, setExperimentReport] = useState<DayTradingExperimentReport | null>(null);
  const [experimentLoading, setExperimentLoading] = useState(false);
  const [experimentRunning, setExperimentRunning] = useState(false);
  const [experimentError, setExperimentError] = useState<string | null>(null);
  const [experimentForm, setExperimentForm] = useState({
    scope: "snapshot",
    researchMode: "control_first",
    windowMode: "fixed_session",
    strictMarketData: true,
    barsRequested: String(MARKET_INPUT_DEFAULTS.crypto.bars),
  });
  const snapshotRequestRef = useRef(0);
  const watchlistRequestRef = useRef(0);
  const marketInputsRef = useRef<Record<DayTradingMarket, MarketInputState>>({
    crypto: { ...MARKET_INPUT_DEFAULTS.crypto },
    equities_legacy: { ...MARKET_INPUT_DEFAULTS.equities_legacy },
  });
  const hydratedMarketsRef = useRef<Record<DayTradingMarket, boolean>>({
    crypto: false,
    equities_legacy: false,
  });

  const syncJournalTicketState = useCallback((nextSnapshot: DayTradingSnapshot | null, preferredTicketId?: string) => {
    const approvedTickets = (nextSnapshot?.profitabilityTickets?.todaysTickets || [])
      .filter((ticket) => ticket.lifecycleStatus === "approved");
    const selectedTicket = approvedTickets.find((ticket) => ticket.ticketId === preferredTicketId)
      || approvedTickets[0]
      || null;
    setJournalTicketId(selectedTicket?.ticketId || "");
    setJournalForm(buildJournalDraft(selectedTicket));
  }, []);

  const fetchWatchlist = useCallback(async (requestedBars: number, requestedLimit: number = 4) => {
    const requestId = ++watchlistRequestRef.current;
    setWatchlistLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        bars: String(requestedBars),
        limit: String(requestedLimit),
        market,
      });
      const res = await fetch(`/api/day-trading/watchlist?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load day-trading watchlist");
      if (requestId === watchlistRequestRef.current) {
        setWatchlist(data);
      }
    } catch (err) {
      if (requestId === watchlistRequestRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load day-trading watchlist");
      }
    } finally {
      if (requestId === watchlistRequestRef.current) {
        setWatchlistLoading(false);
      }
    }
  }, [market]);

  useEffect(() => {
    const nextInputs = marketInputsRef.current[market] || MARKET_INPUT_DEFAULTS[market];
    setBars(nextInputs.bars);
    setStartingCash(nextInputs.startingCash);
    setPreflightResult(null);
    setJournalResult(null);
    setJournalTicketId("");
    setJournalForm(buildJournalDraft());
    setExperimentReport(null);
    setExperimentError(null);
  }, [market]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 15000);
    return () => window.clearInterval(timer);
  }, []);

  const loadSnapshot = useCallback(async () => {
    const requestId = ++snapshotRequestRef.current;
    setLoading(true);
    setError(null);
    watchlistRequestRef.current += 1;
    setWatchlist(null);
    setWatchlistLoading(false);
    try {
      const params = new URLSearchParams({ market });
      const res = await fetch(`/api/day-trading?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load day-trading lab");
      if (requestId !== snapshotRequestRef.current) {
        return;
      }
      setSnapshot(data);
      setExperimentReport(data.experimentReport || null);
      syncJournalTicketState(data, journalTicketId);
      const targetMarket = (data.market || market) as DayTradingMarket;
      const defaultBars = data.defaultConfig?.bars || 3120;
      const watchlistLimit = data.defaultConfig?.watchlistLimit || 4;
      const defaultStartingCash = data.defaultConfig?.startingCash || 10000;
      if (!hydratedMarketsRef.current[targetMarket]) {
        marketInputsRef.current[targetMarket] = {
          bars: defaultBars,
          startingCash: defaultStartingCash,
        };
        hydratedMarketsRef.current[targetMarket] = true;
      }
      const activeInputs = marketInputsRef.current[targetMarket] || {
        bars: defaultBars,
        startingCash: defaultStartingCash,
      };
      setBars(activeInputs.bars);
      setStartingCash(activeInputs.startingCash);
      void fetchWatchlist(activeInputs.bars, watchlistLimit);
    } catch (err) {
      if (requestId === snapshotRequestRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load day-trading lab");
      }
    } finally {
      if (requestId === snapshotRequestRef.current) {
        setLoading(false);
      }
    }
  }, [fetchWatchlist, journalTicketId, market, syncJournalTicketState]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    setExperimentForm((current) => ({
      ...current,
      barsRequested: String(bars),
    }));
  }, [bars]);

  useEffect(() => {
    if (market !== "crypto") return;
    const sessionActive = Boolean(
      watchlist?.sessionWindow?.activeNow
      || watchlist?.morningWindow.activeNow
      || snapshot?.pilotSummary?.todayGate?.activeSessionWindow
    );
    if (!watchlistAutoRefresh || !sessionActive) return;
    const timer = window.setInterval(() => {
      void fetchWatchlist(bars, snapshot?.defaultConfig?.watchlistLimit || 4);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [
    bars,
    fetchWatchlist,
    market,
    snapshot?.pilotSummary?.todayGate?.activeSessionWindow,
    snapshot?.defaultConfig?.watchlistLimit,
    watchlist?.morningWindow.activeNow,
    watchlist?.sessionWindow?.activeNow,
    watchlistAutoRefresh,
  ]);

  const runValidation = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/day-trading", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, bars, startingCash }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Validation run failed");
      setSnapshot(data.snapshot);
      setExperimentReport(data.snapshot?.experimentReport || null);
      syncJournalTicketState(data.snapshot, journalTicketId);
      setWatchlist(null);
      void fetchWatchlist(bars, data.snapshot?.defaultConfig?.watchlistLimit || 4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation run failed");
    } finally {
      setRunning(false);
    }
  };

  const requestPreflightTicket = async () => {
    setPreflightLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/day-trading/preflight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market: "crypto",
          strategyId: snapshot?.operatingPlan?.activeSetupId,
          bars,
          ...preflightChecklist,
        }),
      });
      const data: PreflightResponse | { error?: string } = await res.json();
      if (!res.ok || !("result" in data) || !("snapshot" in data)) {
        throw new Error(("error" in data && data.error) || "Preflight request failed");
      }
      setPreflightResult(data.result);
      setJournalResult(null);
      setSnapshot(data.snapshot);
      setExperimentReport(data.snapshot?.experimentReport || null);
      syncJournalTicketState(data.snapshot, data.result.ticket?.ticketId || journalTicketId);
      setWatchlist(null);
      void fetchWatchlist(bars, data.snapshot?.defaultConfig?.watchlistLimit || 4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preflight request failed");
    } finally {
      setPreflightLoading(false);
    }
  };

  const submitJournalEntry = async () => {
    setJournalLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/day-trading/journal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market: "crypto",
          ticketId: journalForm.ticketId,
          tradeTimestamp: toIsoFromLocalInput(journalForm.tradeTimestampLocal),
          sessionLabel: journalForm.sessionLabel,
          symbol: journalForm.symbol,
          regime: journalForm.regime,
          setupId: journalForm.setupId,
          side: journalForm.side,
          setup_match_confirmed: journalForm.setup_match_confirmed,
          headline_lockout_checked: journalForm.headline_lockout_checked,
          maker_limit_plan_confirmed: journalForm.maker_limit_plan_confirmed,
          plannedEntryPrice: Number(journalForm.plannedEntryPrice),
          actualEntryPrice: Number(journalForm.actualEntryPrice),
          stopPrice: Number(journalForm.stopPrice),
          targetPrice: Number(journalForm.targetPrice),
          actualExitPrice: Number(journalForm.actualExitPrice),
          orderType: journalForm.orderType,
          entryLiquidityRole: journalForm.entryLiquidityRole,
          exitLiquidityRole: journalForm.exitLiquidityRole,
          entryFillRatio: Number(journalForm.entryFillRatio),
          exitFillRatio: Number(journalForm.exitFillRatio),
          exitReason: journalForm.exitReason,
          stopExecutionQuality: journalForm.stopExecutionQuality,
          sizeUsd: Number(journalForm.sizeUsd),
          feesUsd: Number(journalForm.feesUsd),
          spreadSlippageUsd: Number(journalForm.spreadSlippageUsd),
          pnlR: Number(journalForm.pnlR),
          pnlUsd: Number(journalForm.pnlUsd),
          screenshotPath: journalForm.screenshotPath,
          ruleAdherenceScore: Number(journalForm.ruleAdherenceScore),
          mistakeTag: journalForm.mistakeTag,
          note: journalForm.note,
        }),
      });
      const data: JournalResponse | { error?: string } = await res.json();
      if (!res.ok || !("entry" in data) || !("snapshot" in data)) {
        throw new Error(("error" in data && data.error) || "Journal submission failed");
      }
      setJournalResult({
        entry: data.entry,
        summary: data.summary,
      });
      setPreflightResult(null);
      setSnapshot(data.snapshot);
      syncJournalTicketState(data.snapshot, journalTicketId);
      setWatchlist(null);
      void fetchWatchlist(bars, data.snapshot?.defaultConfig?.watchlistLimit || 4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Journal submission failed");
    } finally {
      setJournalLoading(false);
    }
  };

  const loadExperimentReport = async () => {
    setExperimentLoading(true);
    setExperimentError(null);
    try {
      const params = new URLSearchParams({
        market,
        scope: experimentForm.scope,
        researchMode: experimentForm.researchMode,
        windowMode: experimentForm.windowMode,
        strictMarketData: String(experimentForm.strictMarketData),
        barsRequested: experimentForm.barsRequested || String(bars),
      });
      const res = await fetch(`/api/day-trading/experiments?${params.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data as { error?: string }).error || "Failed to load experiment report");
      }
      const nextReport = experimentReportFromPayload(data);
      if (!nextReport) {
        throw new Error("Experiment report payload was missing");
      }
      setExperimentReport(nextReport);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load experiment report";
      setExperimentError(message);
    } finally {
      setExperimentLoading(false);
    }
  };

  const runExperimentSweep = async () => {
    setExperimentRunning(true);
    setExperimentError(null);
    try {
      const res = await fetch("/api/day-trading/experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market,
          scope: experimentForm.scope,
          researchMode: experimentForm.researchMode,
          windowMode: experimentForm.windowMode,
          strictMarketData: experimentForm.strictMarketData,
          barsRequested: Number(experimentForm.barsRequested || bars),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((data as { error?: string }).error || "Failed to run experiment sweep");
      }
      const nextReport = experimentReportFromPayload(data);
      if (!nextReport) {
        throw new Error("Experiment sweep did not return a report");
      }
      setExperimentReport(nextReport);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to run experiment sweep";
      setExperimentError(message);
    } finally {
      setExperimentRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-text-3">
        Loading day-trading lab...
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="bg-bg-2 border border-border rounded-lg p-6 text-sm text-text-3">
        {error || "Unable to load day-trading lab."}
      </div>
    );
  }

  const report: DayTradingReport | null = snapshot.lastReport;
  const selectedMarket = (snapshot.market || market) as DayTradingMarket;
  const copy = marketCopy(selectedMarket);
  const operatingPlan: DayTradingOperatingPlan | null = snapshot.operatingPlan || null;
  const pilotSummary: DayTradingPilotSummary | null = snapshot.pilotSummary || null;
  const artifactHealth = snapshot.artifactHealth || null;
  const profitabilityTickets = snapshot.profitabilityTickets || null;
  const approvedTickets = (profitabilityTickets?.todaysTickets || []).filter((ticket) => ticket.lifecycleStatus === "approved");
  const selectedJournalTicket = approvedTickets.find((ticket) => ticket.ticketId === journalTicketId) || null;
  const scoreboardRows = snapshot.scoreboard.items.map((item) => ({
    Strategy: item.strategyName,
    Status: item.status.replace(/_/g, " "),
    Score: item.score.toFixed(1),
    "Backtest Return": item.backtest ? pct(item.backtest.totalNetReturnFraction) : "-",
    "Drawdown": item.backtest ? pct(item.backtest.maxDrawdownFraction) : "-",
    "Win Rate": item.backtest ? pct(item.backtest.winRate) : "-",
    "Paper PnL": item.paper ? money(item.paper.realizedPnl) : "-",
    Vetoes: item.vetoReasons.length > 0 ? item.vetoReasons.join(", ") : "-",
  }));

  const validationRows = report?.results.map((result) => ({
    Strategy: result.strategyId,
    Source: result.marketDataSource,
    "Backtest Return": pct(result.backtestSummary.totalNetReturnFraction),
    "Trades": String(result.backtestSummary.tradeCount),
    "Profit Factor": result.backtestSummary.profitFactor?.toFixed(2) || "-",
    "Hit Rate": pct(result.backtestSummary.winRate),
    "Paper Action": result.paperAction.action,
    Promotion: result.promotionDecision?.nextStatus?.replace(/_/g, " ") || "-",
    Warning: result.marketDataWarning || "-",
  })) || [];

  const watchlistRows = watchlist?.items.map((item) => ({
    Strategy: item.strategyName,
    Symbol: item.symbol || "-",
    Priority: item.priorityScore == null ? "-" : item.priorityScore.toFixed(1),
    Status: item.notifyNow ? "notify now" : watchStatusLabel(item.liveStatus),
    Regime: labelize(item.regimeState),
    Tradeable: item.tradeable ? "yes" : "no",
    "Why Now": item.priorityReasons && item.priorityReasons.length > 0
      ? item.priorityReasons.slice(0, 3).map((reason) => reasonLabel(reason)).join(", ")
      : "-",
    Blockers: item.regimeBlockers && item.regimeBlockers.length > 0 ? item.regimeBlockers.map((reason) => labelize(reason)).join(", ") : "-",
    "Slots Left": item.approvalSlotsRemaining != null ? String(item.approvalSlotsRemaining) : "-",
    "Replay Ready": item.alertEligible ? "yes" : "no",
    "Data Trust": item.currentDataTrusted ? "trusted" : "untrusted",
    "Hit Rate": item.replayEvidence ? pct(item.replayEvidence.winRate) : "-",
    "Profit Factor": item.replayEvidence?.profitFactor?.toFixed(2) || "-",
    Trades: item.replayEvidence?.tradeCount?.toString() || "-",
    "Signal / Threshold": item.currentSignalValue != null && item.signalThreshold != null
      ? `${item.currentSignalValue.toFixed(2)} / ${item.signalThreshold.toFixed(2)}`
      : "-",
    "Bar Age": item.barAgeMinutes != null ? `${item.barAgeMinutes.toFixed(1)}m` : "-",
    "Triggered At": item.latestSignalTimestamp
      ? item.latestSignalTimestamp.slice(11, 16)
      : "-",
    Window: item.sessionWindowLabel || "-",
    Source: item.marketDataSource,
    Warning: item.marketDataWarning || "-",
  })) || [];
  const pilotGateRows = pilotSummary?.gates.map((gate) => ({
    Gate: gate.label,
    Target: gate.target,
    Actual: gate.actual,
    Status: gate.passed ? "passed" : "pending",
  })) || [];
  const milestoneRows = pilotSummary?.milestones?.map((milestone) => ({
    Milestone: milestone.label,
    Progress: `${milestone.completedTrades}/${milestone.targetTrades}`,
    Remaining: String(milestone.remainingTrades),
    Status: labelize(milestone.status),
    Notes: milestone.description,
  })) || [];
  const checklistRows = (pilotSummary?.preTradeChecklist || operatingPlan?.preTradeChecklist || []).map((item) => ({
    Item: item.label,
    Required: item.required ? "yes" : "no",
    Notes: item.description || "-",
  }));
  const regimeRows = operatingPlan ? [
    {
      Mode: "Range",
      Checklist: operatingPlan.regimeChecklist.range.join(" "),
    },
    {
      Mode: "Trend",
      Checklist: operatingPlan.regimeChecklist.trend.join(" "),
    },
    {
      Mode: "Event",
      Checklist: operatingPlan.regimeChecklist.event.join(" "),
    },
  ] : [];
  const regimeBreakdownRows = pilotSummary?.breakdownByRegime.map((row) => ({
    Regime: row.label,
    Trades: String(row.trades),
    "Win Rate": pct(row.winRate),
    "Expectancy (R)": row.expectancyR.toFixed(2),
    "Net PnL": money(row.netPnlUsd, 2),
  })) || [];
  const setupBreakdownRows = pilotSummary?.breakdownBySetup.map((row) => ({
    Setup: row.label,
    Trades: String(row.trades),
    "Win Rate": pct(row.winRate),
    "Expectancy (R)": row.expectancyR.toFixed(2),
    "Net PnL": money(row.netPnlUsd, 2),
  })) || [];
  const disqualificationRows = pilotSummary?.disqualificationReasons?.map((row) => ({
    Reason: labelize(row.reason),
    Count: String(row.count),
  })) || [];
  const executionRows = pilotSummary?.executionStats ? [
    {
      Metric: "Maker share",
      Value: pct(pilotSummary.executionStats.makerShare),
    },
    {
      Metric: "Average entry slippage",
      Value: bps(pilotSummary.executionStats.averageEntrySlippageBps),
    },
    {
      Metric: "Average exit slippage",
      Value: bps(pilotSummary.executionStats.averageExitSlippageBps),
    },
    {
      Metric: "Partial fill rate",
      Value: pct(pilotSummary.executionStats.partialFillRate),
    },
    {
      Metric: "Stop slip rate",
      Value: pct(pilotSummary.executionStats.stopSlipRate),
    },
  ] : [];
  const ticketRows = profitabilityTickets?.todaysTickets.map((ticket) => ({
    Ticket: ticket.ticketId.slice(-8),
    Status: labelize(ticket.lifecycleStatus),
    Approved: timeLabel(ticket.approvedAt),
    Used: timeLabel(ticket.usedAt),
    Regime: labelize(ticket.regimeState),
    Tradeable: ticket.tradeable ? "yes" : "no",
    Checklist: Object.values(ticket.checklistFlags || {}).every(Boolean) ? "complete" : "incomplete",
  })) || [];
  const currentTime = new Date(nowTick);
  const sessionClock = getSessionClock(operatingPlan?.session, watchlist?.sessionWindow, currentTime);
  const profitabilityJournal = snapshot.profitabilityJournal || null;
  const reviewEntries = [...(snapshot.profitabilityJournal?.recentEntries || [])].sort((left, right) => {
    const leftTime = new Date(left.loggedAt || left.tradeTimestamp || 0).getTime();
    const rightTime = new Date(right.loggedAt || right.tradeTimestamp || 0).getTime();
    return rightTime - leftTime;
  });
  const todayReviewEntries = reviewEntries.filter((entry) => isSameLocalDay(entry.loggedAt || entry.tradeTimestamp, currentTime));
  const weekReviewEntries = reviewEntries.filter((entry) => isWithinDays(entry.loggedAt || entry.tradeTimestamp, currentTime, 7));
  const todayReviewSummary = profitabilityJournal?.today || mapSummaryToAggregate(summarizeJournalEntries(todayReviewEntries), "today");
  const weekReviewSummary = profitabilityJournal?.trailingWeek || mapSummaryToAggregate(summarizeJournalEntries(weekReviewEntries), "Trailing 7 days");
  const buildJournalRows = (entries: typeof reviewEntries) => entries.map((entry) => ({
    Logged: timeLabel(entry.loggedAt || entry.tradeTimestamp),
    Ticket: entry.ticketId ? entry.ticketId.slice(-8) : "-",
    Symbol: entry.symbol || "-",
    Regime: labelize(entry.regime),
    Setup: labelize(entry.setupId),
    "PnL (R)": entry.pnlR == null ? "-" : entry.pnlR.toFixed(2),
    "PnL ($)": money(entry.pnlUsd, 2),
    Adherence: entry.ruleAdherenceScore == null ? "-" : `${entry.ruleAdherenceScore.toFixed(1)}%`,
    Mistake: labelize(entry.mistakeTag),
    Eligible: entry.pilotEligible ? "yes" : "no",
    Notes: entry.note || "-",
  }));
  const buildGroupedRows = (entries: typeof reviewEntries, groupKey: "Regime" | "Mistake Tag") => {
    const grouped = new Map<string, typeof reviewEntries>();
    entries.forEach((entry) => {
      const key = groupKey === "Regime" ? labelize(entry.regime) : labelize(entry.mistakeTag);
      const bucket = grouped.get(key) || [];
      bucket.push(entry);
      grouped.set(key, bucket);
    });
    return Array.from(grouped.entries())
      .map(([label, items]) => {
        const summary = summarizeJournalEntries(items);
        const netPnl = money(summary.totalPnlUsd, 2);
        return {
          [groupKey]: label,
          Trades: String(summary.trades),
          "Net PnL": netPnl,
          "Avg PnL": money(summary.avgPnlUsd, 2),
          "Avg R": summary.avgPnlR == null ? "-" : summary.avgPnlR.toFixed(2),
          "Avg Adherence": summary.avgAdherence == null ? "-" : `${summary.avgAdherence.toFixed(1)}%`,
          Eligible: summary.trades === 0 ? "-" : `${summary.eligibleCount}/${summary.trades}`,
          Disqualified: String(summary.disqualifiedCount),
        };
      })
      .sort((left, right) => {
        const leftPnl = parseFloat(String(left["Net PnL"]).replace(/[^0-9.-]/g, "")) || 0;
        const rightPnl = parseFloat(String(right["Net PnL"]).replace(/[^0-9.-]/g, "")) || 0;
        return rightPnl - leftPnl;
      });
  };
  const regimeReviewRows = buildGroupedRows(reviewEntries, "Regime");
  const mistakeReviewRows = profitabilityJournal?.byMistakeTag?.length
    ? buildAggregateReviewRows(profitabilityJournal.byMistakeTag, "Mistake Tag")
    : buildGroupedRows(reviewEntries, "Mistake Tag");
  const dateReviewRows = profitabilityJournal?.byDate?.length
    ? buildAggregateReviewRows(profitabilityJournal.byDate, "Date")
    : [];
  const snapshotAgeLabel = formatAgeLabel(snapshot.generatedAt, nowTick);
  const watchlistAgeLabel = formatAgeLabel(watchlist?.generatedAt, nowTick);
  const journalAgeLabel = formatAgeLabel(snapshot.profitabilityJournal?.lastLoggedAt, nowTick);
  const activeExperimentReport = experimentReport || snapshot.experimentReport || null;
  const experimentResultRows = (activeExperimentReport?.leaders || activeExperimentReport?.results || []).map((variant) => ({
    Variant: variant.variantLabel || variant.variantId.slice(-8),
    Strategy: variant.strategyName,
    Score: variant.experimentScore == null ? "-" : variant.experimentScore.toFixed(1),
    PF: variant.summary?.profitFactor == null ? "-" : variant.summary.profitFactor.toFixed(2),
    Return: variant.summary?.totalNetReturnFraction == null ? "-" : pct(variant.summary.totalNetReturnFraction),
    "Win Rate": variant.summary?.winRate == null ? "-" : pct(variant.summary.winRate),
    Trades: String(variant.summary?.tradeCount ?? 0),
    Window: variant.windowModeLabel || variant.windowMode || "-",
    Data: variant.trustedMarketData ? "trusted" : "untrusted",
    Vetoes: variant.summary?.vetoReasons?.length ? variant.summary.vetoReasons.join(", ") : "-",
  })).sort((left, right) => (Number(right.Score) || 0) - (Number(left.Score) || 0));
  const experimentMetrics = activeExperimentReport ? [
    {
      label: "Variants Tested",
      value: String(activeExperimentReport.variantsTested ?? activeExperimentReport.results?.length ?? 0),
      delta: `Generated ${formatAgeLabel(activeExperimentReport.generatedAt, nowTick)}`,
    },
    {
      label: "Eligible Variants",
      value: String(activeExperimentReport.eligibleVariantCount ?? 0),
      delta: `${activeExperimentReport.trustedVariantCount ?? 0} trusted`,
    },
    {
      label: "Control Strategies",
      value: String(activeExperimentReport.controlStrategiesTested ?? 0),
      delta: activeExperimentReport.sessionMode || "Session not specified",
    },
    {
      label: "Windows Reviewed",
      value: String(activeExperimentReport.windowModesEvaluated?.length || 0),
      delta: activeExperimentReport.researchMode || "Research mode unset",
    },
  ] : [];
  const artifactWindowCopy = artifactHealth && artifactHealth.warnings.length > 0
    ? `Live windows ${artifactHealth.configuredWindowIds.join(", ") || "none"} | strategy artifacts ${artifactHealth.strategyWindowIds.join(", ") || "none"} | watchlist artifact ${artifactHealth.watchlistWindowIds.join(", ") || "none"}`
    : null;
  const updateJournalField = <K extends keyof JournalFormState>(key: K, value: JournalFormState[K]) => {
    setJournalForm((current) => ({
      ...current,
      [key]: value,
    }));
  };

  return (
    <div className="space-y-6">
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <div className="section-header mt-0 mb-1 border-0 pb-0">{copy.title}</div>
            <p className="text-sm text-text-3 max-w-3xl">
              {copy.description}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadSnapshot()}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-md border border-border bg-bg-3 text-text-1 text-sm font-medium hover:bg-bg-4 disabled:opacity-50 transition-all"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Clock3 size={14} />}
              {loading ? "Reloading..." : "Refresh Snapshot"}
            </button>
            <button
              onClick={() => fetchWatchlist(bars, snapshot?.defaultConfig?.watchlistLimit || 4)}
              disabled={watchlistLoading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-md border border-border bg-bg-3 text-text-1 text-sm font-medium hover:bg-bg-4 disabled:opacity-50 transition-all"
            >
              {watchlistLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {watchlistLoading ? "Refreshing..." : "Refresh Watchlist"}
            </button>
            <button
              onClick={() => setWatchlistAutoRefresh((current) => !current)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-md border text-sm font-medium transition-all ${
                watchlistAutoRefresh
                  ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/15"
                  : "border-border bg-bg-3 text-text-1 hover:bg-bg-4"
              }`}
            >
              <CalendarClock size={14} />
              {watchlistAutoRefresh ? "Auto-Poll On" : "Auto-Poll Off"}
            </button>
            <button
              onClick={runValidation}
              disabled={running}
              className="flex items-center gap-2 px-5 py-2.5 rounded-md bg-gradient-to-r from-accent to-blue-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? "Running..." : "Run Validation Cycle"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-text-2 block mb-1">Active market</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as DayTradingMarket)}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            >
              {MARKET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="mt-1 text-xs text-text-3">
              {MARKET_OPTIONS.find((option) => option.value === market)?.description}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Bars of intraday history</label>
            <input
              type="number"
              min={48}
              max={3900}
              step={78}
              value={bars}
              onChange={(e) => {
                const nextBars = Math.max(48, Math.min(3900, Number(e.target.value) || 3120));
                marketInputsRef.current[market] = {
                  ...marketInputsRef.current[market],
                  bars: nextBars,
                };
                setBars(nextBars);
              }}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            />
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Paper account starting cash</label>
            <input
              type="number"
              min={1000}
              step={500}
              value={startingCash}
              onChange={(e) => {
                const nextStartingCash = Math.max(1000, Number(e.target.value) || 10000);
                marketInputsRef.current[market] = {
                  ...marketInputsRef.current[market],
                  startingCash: nextStartingCash,
                };
                setStartingCash(nextStartingCash);
              }}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 text-sm text-red bg-red/10 border border-red/20 rounded-md px-3 py-2">
            {error}
          </div>
        )}
      </div>

      {selectedMarket === "crypto" && artifactHealth && artifactHealth.warnings.length > 0 && (
        <div className="relative overflow-hidden rounded-lg border border-amber/30 bg-[linear-gradient(135deg,rgba(245,158,11,0.12),rgba(15,23,42,0.04))] p-4">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.14),transparent_48%)] pointer-events-none" />
          <div className="relative flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-amber/15 p-2 text-amber">
              <AlertTriangle size={16} />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-semibold text-text-0">Pilot Artifact Drift</div>
              <p className="text-sm text-text-2 max-w-4xl">
                The live BTC-first pilot is using the current Denver Core config, but one or more saved artifacts still point at older session windows.
                The lane is still usable, but the persisted strategy/watchlist files should be treated as legacy until they are regenerated.
              </p>
              {artifactWindowCopy && (
                <div className="text-xs text-text-3 uppercase tracking-[0.18em]">
                  {artifactWindowCopy}
                </div>
              )}
              <div className="flex flex-wrap gap-2 text-xs text-text-2">
                {artifactHealth.warnings.map((warning) => (
                  <span
                    key={warning}
                    className="rounded-full border border-amber/25 bg-amber/10 px-3 py-1"
                  >
                    {warning}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_0.75fr] gap-4">
        <div className="rounded-lg border border-border bg-bg-2 p-4 space-y-4">
          <div className="section-header mt-0 flex items-center gap-2">
            <Clock3 size={14} />
            Live Operator Console
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <MetricCard
              label="Session"
              value={sessionClock.active ? "Live" : "Closed"}
              delta={`${sessionClock.activeWindowLabel || sessionClock.nextWindowLabel || "No session window"} - ${sessionClock.countdown}`}
            />
            <MetricCard
              label="Snapshot Age"
              value={snapshotAgeLabel}
              delta={`Captured ${snapshot.generatedAt.slice(0, 16).replace("T", " ")}`}
            />
            <MetricCard
              label="Watchlist Age"
              value={watchlist ? watchlistAgeLabel : "-"}
              delta={market === "crypto" && watchlistAutoRefresh
                ? (sessionClock.active ? "Auto-polling during active window" : "Waiting for the next active window")
                : "Manual refresh only"}
            />
            <MetricCard
              label="Journal Age"
              value={journalAgeLabel}
              delta={`${reviewEntries.length} recent entries in the snapshot`}
            />
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-text-2">
            <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
              Now: {sessionClock.currentLabel}
            </span>
            <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
              Time zone: {sessionClock.timeZone}
            </span>
            <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
              Session windows: {sessionClock.windowLabels.length ? sessionClock.windowLabels.join(" | ") : operatingPlan?.session.localWindow || "n/a"}
            </span>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-bg-2 p-4 space-y-3">
          <div className="section-header mt-0 flex items-center gap-2">
            <RefreshCw size={14} />
            Refresh Controls
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <button
              onClick={() => loadSnapshot()}
              disabled={loading}
              className="flex items-center justify-center gap-2 rounded-md border border-border bg-bg-3 px-4 py-3 text-text-1 hover:bg-bg-4 disabled:opacity-50"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Clock3 size={14} />}
              Reload snapshot
            </button>
            <button
              onClick={() => fetchWatchlist(bars, snapshot?.defaultConfig?.watchlistLimit || 4)}
              disabled={watchlistLoading}
              className="flex items-center justify-center gap-2 rounded-md border border-border bg-bg-3 px-4 py-3 text-text-1 hover:bg-bg-4 disabled:opacity-50"
            >
              {watchlistLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Reload watchlist
            </button>
            <button
              onClick={() => setWatchlistAutoRefresh((current) => !current)}
              className={`flex items-center justify-center gap-2 rounded-md border px-4 py-3 font-medium ${
                watchlistAutoRefresh
                  ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/15"
                  : "border-border bg-bg-3 text-text-1 hover:bg-bg-4"
              }`}
            >
              <CalendarClock size={14} />
              {watchlistAutoRefresh ? "Auto-poll on" : "Auto-poll off"}
            </button>
            <button
              onClick={runValidation}
              disabled={running}
              className="flex items-center justify-center gap-2 rounded-md bg-gradient-to-r from-accent to-blue-600 px-4 py-3 font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              Run validation
            </button>
          </div>
          <div className="text-xs text-text-3">
            Watchlist polling is automatic only while the active window is live.
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <MetricCard
          label="Strategies"
          value={String(snapshot.scoreboard.totals.strategies)}
          delta={`${snapshot.strategies.length} loaded`}
        />
        <MetricCard
          label="Paper Equity"
          value={money(snapshot.paperAccount.equity)}
          delta={snapshot.paperAccount.totalUnrealizedPnl >= 0
            ? `+${snapshot.paperAccount.totalUnrealizedPnl.toFixed(2)} unrealized`
            : `${snapshot.paperAccount.totalUnrealizedPnl.toFixed(2)} unrealized`}
        />
        <MetricCard
          label="Candidate Live"
          value={String(snapshot.scoreboard.totals.candidateLive)}
          delta={`${snapshot.scoreboard.totals.withPaperActivity} with paper activity`}
        />
        <MetricCard
          label="Blocked"
          value={String(snapshot.scoreboard.totals.blocked)}
          delta={report ? `Last run ${report.generatedAt.slice(0, 16).replace("T", " ")}` : "No run yet"}
        />
      </div>

      {operatingPlan && pilotSummary && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <ShieldCheck size={14} />
            Profitability Pilot
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
            <MetricCard
              label="Pilot Phase"
              value={phaseLabel(pilotSummary.phase)}
              delta={operatingPlan.defaultRegimeBias}
            />
            <MetricCard
              label="Eligible Trades"
              value={`${pilotSummary.progress.completedTrades}/${pilotSummary.progress.targetTrades}`}
              delta={`${pilotSummary.reviewCheckpointTrades || 30} review / ${pilotSummary.advanceGateTrades || 50} advance`}
            />
            <MetricCard
              label="Daily Cap"
              value={`${pilotSummary.todayGate?.approvedEntries || 0}/${pilotSummary.todayGate?.dailyTradeCap || operatingPlan.dailyTradeCap?.limit || 0}`}
              delta={pilotSummary.todayGate
                ? `${pilotSummary.todayGate.remainingApprovals} slots left${pilotSummary.todayGate.activeSessionWindow ? " - session live" : " - session closed"}`
                : "No gate data"}
            />
            <MetricCard
              label="Expectancy"
              value={pilotSummary.journalStats.expectancyR == null ? "-" : `${pilotSummary.journalStats.expectancyR.toFixed(2)}R`}
              delta="Net after fees/slippage"
            />
            <MetricCard
              label="Profit Factor"
              value={ratio(pilotSummary.journalStats.profitFactor, 2)}
              delta="50-trade gate >= 1.20x"
            />
            <MetricCard
              label="Rule Adherence"
              value={pct(pilotSummary.journalStats.ruleAdherenceRate)}
              delta="50-trade gate >= 90%"
            />
            <MetricCard
              label="Disqualified"
              value={String(pilotSummary.journalStats.disqualifiedTradeCount || 0)}
              delta={`${pilotSummary.journalStats.eligibleTradeCount || 0} eligible entries`}
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_0.9fr] gap-4">
            <div className="relative overflow-hidden rounded-lg border border-accent/20 bg-[linear-gradient(145deg,rgba(28,100,242,0.14),rgba(15,23,42,0.05))] p-4">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.14),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(28,100,242,0.14),transparent_38%)] pointer-events-none" />
              <div className="relative space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="section-header mt-0 mb-1 border-0 pb-0 flex items-center gap-2">
                      <Ticket size={14} />
                      Preflight Console
                    </div>
                    <p className="text-sm text-text-2 max-w-2xl">
                      Request a same-day approval ticket from inside the lane. This keeps the BTC pilot honest by forcing the manual checklist and live system gate to agree before a trade is allowed.
                    </p>
                  </div>
                  <div className="rounded-full border border-white/10 bg-black/10 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-text-2">
                    {operatingPlan.activeSetupLabel}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {(pilotSummary.preTradeChecklist || operatingPlan.preTradeChecklist || []).map((item) => (
                    <label
                      key={item.key}
                      className={`rounded-xl border px-4 py-3 transition-colors cursor-pointer ${
                        preflightChecklist[item.key as keyof PreflightChecklistState]
                          ? "border-green/30 bg-green/10"
                          : "border-border bg-bg-2/80"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={preflightChecklist[item.key as keyof PreflightChecklistState] || false}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setPreflightChecklist((current) => ({
                              ...current,
                              [item.key]: checked,
                            }));
                          }}
                          className="mt-1"
                        />
                        <div>
                          <div className="text-sm font-semibold text-text-0">{item.label}</div>
                          <div className="text-xs text-text-3 mt-1">{item.description || "Manual confirmation required."}</div>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="rounded-lg border border-border bg-bg-2/80 px-3 py-3">
                    <div className="text-text-3 uppercase tracking-wide mb-1">Today Gate</div>
                    <div className="text-text-1">
                      {pilotSummary.todayGate?.approvedEntries || 0}/{pilotSummary.todayGate?.dailyTradeCap || 0} approved
                    </div>
                    <div className="text-text-2 mt-1">
                      {pilotSummary.todayGate?.remainingApprovals || 0} slots left
                    </div>
                  </div>
                  <div className="rounded-lg border border-border bg-bg-2/80 px-3 py-3">
                    <div className="text-text-3 uppercase tracking-wide mb-1">Session</div>
                    <div className="text-text-1">{pilotSummary.todayGate?.activeSessionWindow ? "Live now" : "Closed"}</div>
                    <div className="text-text-2 mt-1">{operatingPlan.session.localWindow}</div>
                  </div>
                  <div className="rounded-lg border border-border bg-bg-2/80 px-3 py-3">
                    <div className="text-text-3 uppercase tracking-wide mb-1">Expiry</div>
                    <div className="text-text-1">{operatingPlan.dailyTradeCap?.unusedTicketExpiry || "-"}</div>
                    <div className="text-text-2 mt-1">{operatingPlan.dailyTradeCap?.countedBy || "-"}</div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={requestPreflightTicket}
                    disabled={preflightLoading}
                    className="flex items-center gap-2 rounded-md bg-gradient-to-r from-accent to-emerald-600 px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
                  >
                    {preflightLoading ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                    {preflightLoading ? "Checking..." : "Request Ticket"}
                  </button>
                  <div className="text-xs text-text-3">
                    The request will verify checklist completion, data freshness, live regime state, cost cap, and remaining approvals.
                  </div>
                </div>

                {preflightResult && (
                  <div className={`rounded-xl border px-4 py-4 ${
                    preflightResult.approved
                      ? "border-green/30 bg-green/10"
                      : "border-red/25 bg-red/10"
                  }`}>
                    <div className="flex items-start gap-3">
                      <div className={`mt-0.5 rounded-full p-2 ${
                        preflightResult.approved ? "bg-green/15 text-green" : "bg-red/15 text-red"
                      }`}>
                        {preflightResult.approved ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                      </div>
                      <div className="space-y-2">
                        <div className="text-sm font-semibold text-text-0">
                          {preflightResult.approved
                            ? `Ticket ${preflightResult.ticket?.ticketId || ""} approved`
                            : "Ticket request blocked"}
                        </div>
                        <div className="text-sm text-text-2">
                          {preflightResult.approved
                            ? `Approved for ${preflightResult.ticket?.symbol || "BTC"} in ${preflightResult.ticket?.sessionLabel || "Denver Core"} at ${timeLabel(preflightResult.ticket?.approvedAt)}.`
                            : (preflightResult.reasons.length > 0
                              ? preflightResult.reasons.map((reason) => reasonLabel(reason)).join(", ")
                              : "The live gate did not allow a new approval ticket.")}
                        </div>
                        <div className="flex flex-wrap gap-2 text-xs text-text-2">
                          <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                            Regime: {labelize(preflightResult.systemGate?.regimeState)}
                          </span>
                          <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                            Data: {preflightResult.systemGate?.dataFresh ? "fresh" : "stale"}
                          </span>
                          <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                            Cost cap: {preflightResult.systemGate?.costProfile?.allowed ? "pass" : "blocked"}
                          </span>
                          <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                            Cost to target: {pct(preflightResult.systemGate?.costProfile?.costToTargetFraction, 1)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div>
                <div className="section-header mt-0">Ticket Desk</div>
                <p className="text-sm text-text-2">
                  Same-day approvals now stay visible in the lane instead of disappearing into a file path.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <MetricCard
                  label="Today"
                  value={String(profitabilityTickets?.todaysTickets.length || 0)}
                  delta={profitabilityTickets?.todayDate || "No local date"}
                />
                <MetricCard
                  label="Reserved"
                  value={String(profitabilityTickets?.todayGate.reservedTickets || 0)}
                  delta={`${profitabilityTickets?.todayGate.usedTickets || 0} used`}
                />
                <MetricCard
                  label="Remaining"
                  value={String(profitabilityTickets?.todayGate.remainingApprovals || 0)}
                  delta={profitabilityTickets?.todayGate.activeSessionWindow ? "Session live" : "Session closed"}
                />
              </div>
              <FinTable
                data={ticketRows}
                monoCols={["Ticket", "Approved", "Used"]}
                maxHeight="280px"
              />
            </div>
          </div>

          <div className="relative overflow-hidden rounded-lg border border-emerald-500/20 bg-[linear-gradient(155deg,rgba(16,185,129,0.12),rgba(15,23,42,0.05))] p-4">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.14),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.12),transparent_36%)] pointer-events-none" />
            <div className="relative space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="section-header mt-0 mb-1 border-0 pb-0 flex items-center gap-2">
                    <CheckCircle2 size={14} />
                    Journal Trade
                  </div>
                  <p className="text-sm text-text-2 max-w-3xl">
                    Log the executed BTC trade against an approved ticket so the pilot sample, adherence stats, and ticket lifecycle all stay truthful inside the app.
                  </p>
                </div>
                <div className="rounded-full border border-white/10 bg-black/10 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-text-2">
                  Approved tickets only
                </div>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr_1.1fr] gap-4">
                <div className="space-y-3">
                  <div className="rounded-lg border border-border bg-bg-2/80 p-3">
                    <label className="text-xs text-text-2 block mb-1">Approved ticket</label>
                    <select
                      value={journalTicketId}
                      onChange={(e) => {
                        const nextTicketId = e.target.value;
                        const nextTicket = approvedTickets.find((ticket) => ticket.ticketId === nextTicketId) || null;
                        setJournalTicketId(nextTicketId);
                        setJournalResult(null);
                        setJournalForm(buildJournalDraft(nextTicket));
                      }}
                      className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
                      disabled={approvedTickets.length === 0}
                    >
                      {approvedTickets.length === 0 ? (
                        <option value="">No approved tickets yet</option>
                      ) : (
                        approvedTickets.map((ticket) => (
                          <option key={ticket.ticketId} value={ticket.ticketId}>
                            {ticket.symbol} {timeLabel(ticket.approvedAt)} {labelize(ticket.regimeState)}
                          </option>
                        ))
                      )}
                    </select>
                    <div className="mt-2 text-xs text-text-3">
                      Request a preflight ticket first, then journal the fill against that ticket.
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-bg-2/80 p-3 space-y-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide">Ticket Context</div>
                    <div className="flex flex-wrap gap-2 text-xs text-text-2">
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Setup: {journalForm.setupId || "-"}
                      </span>
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Regime: {labelize(journalForm.regime)}
                      </span>
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Session: {journalForm.sessionLabel}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Trade timestamp</label>
                        <input
                          type="datetime-local"
                          value={journalForm.tradeTimestampLocal}
                          onChange={(e) => updateJournalField("tradeTimestampLocal", e.target.value)}
                          className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs text-text-2 block mb-1">Side</label>
                          <select
                            value={journalForm.side}
                            onChange={(e) => updateJournalField("side", e.target.value)}
                            className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
                          >
                            <option value="buy">Buy</option>
                            <option value="sell">Sell</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-xs text-text-2 block mb-1">Screenshot path</label>
                          <input
                            value={journalForm.screenshotPath}
                            onChange={(e) => updateJournalField("screenshotPath", e.target.value)}
                            placeholder="screenshots/btc-setup.png"
                            className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-bg-2/80 p-3 space-y-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide">Checklist Lock</div>
                    {[
                      ["setup_match_confirmed", "Setup match confirmed"],
                      ["headline_lockout_checked", "Headline lockout checked"],
                      ["maker_limit_plan_confirmed", "Maker limit plan confirmed"],
                    ].map(([key, label]) => (
                      <label key={key} className="flex items-center gap-3 text-sm text-text-1">
                        <input
                          type="checkbox"
                          checked={journalForm[key as keyof PreflightChecklistState] as boolean}
                          onChange={(e) => updateJournalField(key as keyof JournalFormState, e.target.checked)}
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="rounded-lg border border-border bg-bg-2/80 p-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide mb-3">Prices And Size</div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Planned entry</label>
                        <input value={journalForm.plannedEntryPrice} onChange={(e) => updateJournalField("plannedEntryPrice", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Actual entry</label>
                        <input value={journalForm.actualEntryPrice} onChange={(e) => updateJournalField("actualEntryPrice", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Stop</label>
                        <input value={journalForm.stopPrice} onChange={(e) => updateJournalField("stopPrice", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Target</label>
                        <input value={journalForm.targetPrice} onChange={(e) => updateJournalField("targetPrice", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Actual exit</label>
                        <input value={journalForm.actualExitPrice} onChange={(e) => updateJournalField("actualExitPrice", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Size USD</label>
                        <input value={journalForm.sizeUsd} onChange={(e) => updateJournalField("sizeUsd", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">PnL (R)</label>
                        <input value={journalForm.pnlR} onChange={(e) => updateJournalField("pnlR", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">PnL USD</label>
                        <input value={journalForm.pnlUsd} onChange={(e) => updateJournalField("pnlUsd", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-bg-2/80 p-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide mb-3">Execution Quality</div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Order type</label>
                        <select value={journalForm.orderType} onChange={(e) => updateJournalField("orderType", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0">
                          <option value="limit">Limit</option>
                          <option value="market">Market</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Exit reason</label>
                        <select value={journalForm.exitReason} onChange={(e) => updateJournalField("exitReason", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0">
                          <option value="target_hit">Target hit</option>
                          <option value="stop_loss">Stop loss</option>
                          <option value="time_exit">Time exit</option>
                          <option value="manual_exit">Manual exit</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Entry liquidity</label>
                        <select value={journalForm.entryLiquidityRole} onChange={(e) => updateJournalField("entryLiquidityRole", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0">
                          <option value="maker">Maker</option>
                          <option value="taker">Taker</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Exit liquidity</label>
                        <select value={journalForm.exitLiquidityRole} onChange={(e) => updateJournalField("exitLiquidityRole", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0">
                          <option value="maker">Maker</option>
                          <option value="taker">Taker</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Entry fill ratio</label>
                        <input value={journalForm.entryFillRatio} onChange={(e) => updateJournalField("entryFillRatio", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Exit fill ratio</label>
                        <input value={journalForm.exitFillRatio} onChange={(e) => updateJournalField("exitFillRatio", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Fees USD</label>
                        <input value={journalForm.feesUsd} onChange={(e) => updateJournalField("feesUsd", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Spread + slippage USD</label>
                        <input value={journalForm.spreadSlippageUsd} onChange={(e) => updateJournalField("spreadSlippageUsd", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs text-text-2 block mb-1">Stop execution quality</label>
                        <select value={journalForm.stopExecutionQuality} onChange={(e) => updateJournalField("stopExecutionQuality", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0">
                          <option value="not_applicable">Not applicable</option>
                          <option value="clean">Clean</option>
                          <option value="slipped">Slipped</option>
                          <option value="better_than_stop">Better than stop</option>
                          <option value="unknown">Unknown</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="rounded-lg border border-border bg-bg-2/80 p-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide mb-3">Review</div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Rule adherence</label>
                        <input value={journalForm.ruleAdherenceScore} onChange={(e) => updateJournalField("ruleAdherenceScore", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div>
                        <label className="text-xs text-text-2 block mb-1">Mistake tag</label>
                        <input value={journalForm.mistakeTag} onChange={(e) => updateJournalField("mistakeTag", e.target.value)} className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0" />
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs text-text-2 block mb-1">Post-trade note</label>
                        <textarea
                          value={journalForm.note}
                          onChange={(e) => updateJournalField("note", e.target.value)}
                          rows={6}
                          className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-bg-2/80 p-3 space-y-3">
                    <div className="text-xs text-text-3 uppercase tracking-wide">Submission</div>
                    <div className="flex flex-wrap gap-2 text-xs text-text-2">
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Ticket: {selectedJournalTicket ? selectedJournalTicket.ticketId.slice(-8) : "none"}
                      </span>
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Approved: {selectedJournalTicket ? timeLabel(selectedJournalTicket.approvedAt) : "-"}
                      </span>
                      <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                        Gate slots after log: {profitabilityTickets?.todayGate.remainingApprovals ?? 0}
                      </span>
                    </div>
                    <button
                      onClick={submitJournalEntry}
                      disabled={journalLoading || approvedTickets.length === 0 || !journalForm.ticketId}
                      className="flex items-center gap-2 rounded-md bg-gradient-to-r from-emerald-600 to-teal-500 px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
                    >
                      {journalLoading ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                      {journalLoading ? "Logging..." : "Log Trade"}
                    </button>
                    <div className="text-xs text-text-3">
                      This records the trade even if it gets disqualified, so review truth stays intact.
                    </div>
                  </div>

                  {journalResult && (
                    <div className={`rounded-xl border px-4 py-4 ${
                      journalResult.entry.pilotEligible
                        ? "border-green/30 bg-green/10"
                        : "border-amber/30 bg-amber/10"
                    }`}>
                      <div className="text-sm font-semibold text-text-0">
                        {journalResult.entry.pilotEligible ? "Trade logged and counted toward the pilot." : "Trade logged, but excluded from pilot metrics."}
                      </div>
                      <div className="mt-2 text-sm text-text-2">
                        Entry {journalResult.entry.entryId} was recorded at {timeLabel(journalResult.entry.loggedAt)}.
                      </div>
                      {journalResult.entry.pilotDisqualificationReasons.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-2">
                          {journalResult.entry.pilotDisqualificationReasons.map((reason) => (
                            <span key={reason} className="rounded-full border border-amber/25 bg-amber/10 px-3 py-1">
                              {reasonLabel(reason)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-3">
              <div>
                <div className="section-header mt-0">Operating Plan</div>
                <p className="text-sm text-text-2">{operatingPlan.objective}</p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Session</div>
                  <div className="text-text-1">{operatingPlan.session.localWindow}</div>
                  <div className="text-text-2 mt-1">{operatingPlan.session.etWindow}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Instruments</div>
                  <div className="text-text-1">Live now: {operatingPlan.instruments.liveNow.join(", ")}</div>
                  <div className="text-text-2 mt-1">Next: {operatingPlan.instruments.nextPhase.join(", ")}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Execution</div>
                  <div className="text-text-1">{operatingPlan.execution.venues.join(" / ")}</div>
                  <div className="text-text-2 mt-1">{operatingPlan.execution.orderStyle}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Risk</div>
                  <div className="text-text-1">Per trade: {pct(operatingPlan.risk.riskPerTradeFraction, 2)}</div>
                  <div className="text-text-2 mt-1">Daily / Weekly: {pct(operatingPlan.risk.maxDailyLossFraction)} / {pct(operatingPlan.risk.maxWeeklyLossFraction)}</div>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Daily Cap</div>
                  <div className="text-text-1">{operatingPlan.dailyTradeCap?.limit || 0} approved BTC entries</div>
                  <div className="text-text-2 mt-1">{operatingPlan.dailyTradeCap?.unusedTicketExpiry || "-"}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Artifacts</div>
                  <div className="text-text-1">Journal: {snapshot.profitabilityJournal?.path || "-"}</div>
                  <div className="text-text-2 mt-1">Tickets: {snapshot.profitabilityJournal?.ticketPath || "-"}</div>
                </div>
              </div>
            </div>

            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div>
                <div className="section-header mt-0">Validation Gates</div>
                <p className="text-sm text-text-2">
                  BTC stays locked to one setup until the 50-trade advance gate passes. The 30-trade checkpoint is a review, not a promotion.
                </p>
              </div>
              <FinTable
                data={pilotGateRows}
                badgeCol="Status"
                monoCols={["Target", "Actual"]}
                maxHeight="320px"
              />
              <div className="text-xs text-text-3">
                Next unlock: {pilotSummary.nextUnlock}
              </div>
            </div>

            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div>
                <div className="section-header mt-0">Pre-Trade Checklist</div>
                <p className="text-sm text-text-2">
                  Every eligible BTC entry needs a same-day approval ticket and all three manual confirmations.
                </p>
              </div>
              <FinTable
                data={checklistRows}
                badgeCol="Required"
                maxHeight="320px"
              />
              <div className="text-xs text-text-3">
                Today gate: {pilotSummary.todayGate?.blocked ? labelize(pilotSummary.todayGate.reasons.join(", ")) : "open"}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Milestones</div>
              <FinTable
                data={milestoneRows}
                badgeCol="Status"
                monoCols={["Progress", "Remaining"]}
                maxHeight="280px"
              />
            </div>
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Execution Stats</div>
              <FinTable
                data={executionRows}
                monoCols={["Value"]}
                maxHeight="280px"
              />
            </div>
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Disqualifications</div>
              <FinTable
                data={disqualificationRows}
                monoCols={["Count"]}
                maxHeight="280px"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {regimeRows.map((row) => (
              <div key={row.Mode} className="bg-bg-2 border border-border rounded-lg p-4">
                <div className="section-header mt-0">{row.Mode}</div>
                <p className="text-sm text-text-2 leading-relaxed">{row.Checklist}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Journal By Regime</div>
              <FinTable
                data={regimeBreakdownRows}
                pnlCols={["Net PnL"]}
                rateCols={["Win Rate"]}
                monoCols={["Trades", "Expectancy (R)"]}
                maxHeight="280px"
              />
            </div>
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Journal By Setup</div>
              <FinTable
                data={setupBreakdownRows}
                pnlCols={["Net PnL"]}
                rateCols={["Win Rate"]}
                monoCols={["Trades", "Expectancy (R)"]}
                maxHeight="280px"
              />
            </div>
          </div>

          <div className="bg-bg-2 border border-border rounded-lg p-4">
            <div className="section-header mt-0">Journal Template</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 text-xs">
              {(snapshot.profitabilityJournal?.schema || []).map((field) => (
                <div key={field.key} className="bg-bg-3 border border-border rounded-md px-3 py-2 text-text-2">
                  <span className="text-text-1">{field.label}</span>
                  {field.required ? " - required" : ""}
                </div>
              ))}
            </div>
          </div>

          <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
            <div>
              <div className="section-header mt-0 flex items-center gap-2">
                <FileText size={14} />
                Session Review
              </div>
              <p className="text-sm text-text-2">
                The review surfaces below use the recent journal sample already in the snapshot, grouped by day, week, regime, and mistake tag.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <MetricCard
                label="Recent Sample"
                value={String(reviewEntries.length)}
                delta="Snapshot-backed only"
              />
              <MetricCard
                label="Today"
                value={String(todayReviewSummary.totalEntries)}
                delta={`${money(todayReviewSummary.netPnlUsd, 2)} net / ${todayReviewSummary.ruleAdherenceRate == null ? "-" : `${(todayReviewSummary.ruleAdherenceRate * 100).toFixed(1)}% adherence`}`}
              />
              <MetricCard
                label="Week"
                value={String(weekReviewSummary.totalEntries)}
                delta={`${money(weekReviewSummary.netPnlUsd, 2)} net / ${weekReviewSummary.disqualifiedEntries} disqualified`}
              />
              <MetricCard
                label="Session Window"
                value={sessionClock.active ? "Live" : "Idle"}
                delta={sessionClock.activeWindowLabel || sessionClock.nextWindowLabel || "No active window"}
              />
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-3">Today</div>
                <FinTable
                  data={buildJournalRows(todayReviewEntries)}
                  monoCols={["Logged", "Ticket", "Symbol", "Regime", "Setup", "PnL (R)", "PnL ($)", "Adherence"]}
                  maxHeight="280px"
                />
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-3">This Week</div>
                <FinTable
                  data={buildJournalRows(weekReviewEntries)}
                  monoCols={["Logged", "Ticket", "Symbol", "Regime", "Setup", "PnL (R)", "PnL ($)", "Adherence"]}
                  maxHeight="280px"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {dateReviewRows.length > 0 && (
                <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                  <div className="text-xs uppercase tracking-wide text-text-3">By Day</div>
                  <FinTable
                    data={dateReviewRows}
                    pnlCols={["Net PnL", "Eligible PnL"]}
                    rateCols={["Win Rate", "Adherence"]}
                    monoCols={["Trades", "Avg R", "Eligible", "Disqualified"]}
                    maxHeight="280px"
                  />
                </div>
              )}
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-3">By Regime</div>
                <FinTable
                  data={regimeReviewRows}
                  pnlCols={["Net PnL", "Avg PnL"]}
                  rateCols={["Avg Adherence"]}
                  monoCols={["Trades", "Avg R", "Eligible", "Disqualified"]}
                  maxHeight="280px"
                />
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-3">By Mistake Tag</div>
                <FinTable
                  data={mistakeReviewRows}
                  pnlCols={["Net PnL", "Avg PnL"]}
                  rateCols={["Avg Adherence"]}
                  monoCols={["Trades", "Avg R", "Eligible", "Disqualified"]}
                  maxHeight="280px"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {(watchlistLoading || watchlist) && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <BellRing size={14} />
            {copy.watchlistTitle}
          </div>
          {watchlist ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
                <MetricCard
                  label="Notify Now"
                  value={String(watchlist.notifyNowCount)}
                  delta={(watchlist.sessionWindow?.activeNow || watchlist.morningWindow.activeNow) ? copy.windowActive : copy.windowInactive}
                />
                <MetricCard
                  label="Strategies Checked"
                  value={String(watchlist.selectedStrategies)}
                  delta={watchlist.rankingBasis}
                />
                <MetricCard
                  label="Tradeable"
                  value={String(watchlist.items.filter((item) => item.tradeable).length)}
                  delta={selectedMarket === "crypto"
                    ? `${watchlist.items.filter((item) => item.regimeBlockers && item.regimeBlockers.length > 0).length} blocked by regime`
                    : (watchlist.items[0]?.strategyName || "No ranked strategy yet")}
                />
                <MetricCard
                  label="Approval Slots"
                  value={selectedMarket === "crypto"
                    ? String(watchlist.todayGate?.remainingApprovals ?? 0)
                    : "-"}
                  delta={selectedMarket === "crypto"
                    ? `${watchlist.todayGate?.approvedEntries ?? 0}/${watchlist.todayGate?.dailyTradeCap ?? 0} used`
                    : "Crypto-only gate"}
                />
                <MetricCard
                  label={selectedMarket === "crypto" ? "Trusted Data" : "Alert Eligible"}
                  value={String(selectedMarket === "crypto"
                    ? watchlist.items.filter((item) => item.currentDataTrusted).length
                    : watchlist.items.filter((item) => item.alertEligible).length)}
                  delta={selectedMarket === "crypto"
                    ? `${watchlist.sessionWindow?.windows.length || 0} scheduled windows`
                    : (watchlist.items.some((item) => item.alertEligible)
                      ? "Replay-approved setup exists"
                      : "No setup has earned alerts yet")}
                />
              </div>
              {selectedMarket === "crypto" && watchlist.sessionWindow && (
                <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2 space-y-2">
                  <div>
                    Windows: {watchlist.sessionWindow.windows.map((window) => `${window.label} ${window.startEt}-${window.endEt} ET`).join(" | ")}
                  </div>
                  <div>
                    Today gate: {watchlist.todayGate
                      ? `${watchlist.todayGate.approvedEntries}/${watchlist.todayGate.dailyTradeCap} approved, ${watchlist.todayGate.remainingApprovals} remaining`
                      : "unavailable"}
                  </div>
                </div>
              )}
              <FinTable
                data={watchlistRows}
                badgeCol="Status"
                rateCols={["Hit Rate"]}
                monoCols={["Priority", "Trades", "Profit Factor", "Signal / Threshold", "Bar Age", "Triggered At", "Window", "Slots Left"]}
                maxHeight="360px"
              />
            </>
          ) : (
            <div className="bg-bg-2 border border-border rounded-lg px-4 py-4 text-sm text-text-2 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Loading watchlist...
            </div>
          )}
        </div>
      )}

      <div>
        <div className="section-header flex items-center gap-2">
          <Activity size={14} />
          Imported Strategies
        </div>
        <div className="grid grid-cols-2 gap-4">
          {snapshot.strategies.map((strategy) => (
            <StrategyCard key={strategy.strategyId} strategy={strategy} />
          ))}
        </div>
      </div>

      <div>
        <div className="section-header flex items-center gap-2">
          <Trophy size={14} />
          Scoreboard
        </div>
        <FinTable
          data={scoreboardRows}
          pnlCols={["Paper PnL"]}
          rateCols={["Win Rate"]}
          monoCols={["Score", "Trades"]}
          maxHeight="420px"
        />
      </div>

      {report && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <ShieldCheck size={14} />
            Latest Validation Run
          </div>
          <div className="grid grid-cols-3 gap-3">
            <MetricCard
              label="Run Time"
              value={report.generatedAt.slice(0, 16).replace("T", " ")}
            />
            <MetricCard
              label="Strategies Scanned"
              value={String(report.strategiesScanned)}
            />
            <MetricCard
              label="Open Paper Positions"
              value={String(report.paperAccount.positions.length)}
            />
          </div>
          {selectedMarket === "crypto" && snapshot.lastImport && (
            <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
              Latest import: {snapshot.lastImport.results.map((item) => `${item.symbol} ${item.totalBars} x 1m bars`).join(" | ")}
            </div>
          )}
          <FinTable
            data={validationRows}
            pnlCols={["Backtest Return"]}
            rateCols={["Hit Rate"]}
            monoCols={["Trades", "Profit Factor"]}
            maxHeight="420px"
          />
        </div>
      )}

      <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
        <div>
          <div className="section-header mt-0 flex items-center gap-2">
            <Trophy size={14} />
            Experiment Console
          </div>
          <p className="text-sm text-text-2 max-w-4xl">
            Run or reload crypto experiment sweeps without dropping to scripts. The lane now sends the selected scope label, window mode, strict-data setting, and requested bar count through the in-app workflow.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-text-2 block mb-1">Scope</label>
            <select
              value={experimentForm.scope}
              onChange={(e) => setExperimentForm((current) => ({ ...current, scope: e.target.value }))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            >
              <option value="snapshot">Snapshot</option>
              <option value="backtest">Backtest</option>
              <option value="research">Research</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Research mode</label>
            <input
              value={experimentForm.researchMode}
              onChange={(e) => setExperimentForm((current) => ({ ...current, researchMode: e.target.value }))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              placeholder="phase_a"
            />
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Window mode</label>
            <select
              value={experimentForm.windowMode}
              onChange={(e) => setExperimentForm((current) => ({ ...current, windowMode: e.target.value }))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            >
              <option value="fixed_session">Fixed session</option>
              <option value="full_day">Full day</option>
              <option value="alert_window">Alert window</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Bars requested</label>
            <input
              type="number"
              min={48}
              max={12000}
              step={78}
              value={experimentForm.barsRequested}
              onChange={(e) => setExperimentForm((current) => ({ ...current, barsRequested: e.target.value }))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            />
          </div>
        </div>

        <label className="flex items-center gap-3 text-sm text-text-1">
          <input
            type="checkbox"
            checked={experimentForm.strictMarketData}
            onChange={(e) => setExperimentForm((current) => ({ ...current, strictMarketData: e.target.checked }))}
          />
          Strict market data
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={loadExperimentReport}
            disabled={experimentLoading}
            className="flex items-center gap-2 rounded-md border border-border bg-bg-3 px-4 py-2.5 text-sm font-medium text-text-1 hover:bg-bg-4 disabled:opacity-50"
          >
            {experimentLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Load report
          </button>
          <button
            onClick={runExperimentSweep}
            disabled={experimentRunning}
            className="flex items-center gap-2 rounded-md bg-gradient-to-r from-accent to-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {experimentRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Run sweep
          </button>
          <div className="text-xs text-text-3">
            Backend response can either populate the snapshot directly or return a dedicated experiment report payload.
          </div>
        </div>

        {experimentError && (
          <div className="text-sm text-amber-200 bg-amber-500/10 border border-amber-500/20 rounded-md px-3 py-2">
            {experimentError}
          </div>
        )}

        {activeExperimentReport ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              {experimentMetrics.map((metric) => (
                <MetricCard
                  key={metric.label}
                  label={metric.label}
                  value={metric.value}
                  delta={metric.delta}
                />
              ))}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4">
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                <div className="text-xs uppercase tracking-wide text-text-3">Leaders</div>
                <FinTable
                  data={experimentResultRows}
                  pnlCols={["Return"]}
                  rateCols={["Win Rate"]}
                  monoCols={["Score", "PF", "Trades", "Window", "Data"]}
                  maxHeight="320px"
                />
              </div>
              <div className="space-y-3">
                <div className="bg-bg-3 border border-border rounded-lg p-3">
                  <div className="text-xs uppercase tracking-wide text-text-3 mb-2">Recommendation</div>
                  <div className="text-sm text-text-1 leading-relaxed">
                    {activeExperimentReport.recommendation || "No recommendation supplied yet."}
                  </div>
                </div>
                <div className="bg-bg-3 border border-border rounded-lg p-3">
                  <div className="text-xs uppercase tracking-wide text-text-3 mb-2">Next Sprint Default</div>
                  <div className="text-sm text-text-1 leading-relaxed">
                    {activeExperimentReport.nextSprintDefault || "No sprint default supplied yet."}
                  </div>
                </div>
                {activeExperimentReport.notes && activeExperimentReport.notes.length > 0 && (
                  <div className="bg-bg-3 border border-border rounded-lg p-3">
                    <div className="text-xs uppercase tracking-wide text-text-3 mb-2">Notes</div>
                    <div className="flex flex-wrap gap-2 text-xs text-text-2">
                      {activeExperimentReport.notes.map((note) => (
                        <span key={note} className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                          {note}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {(activeExperimentReport.phaseA || activeExperimentReport.phaseB) && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {activeExperimentReport.phaseA && (
                  <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                    <div className="text-xs uppercase tracking-wide text-text-3">Phase A</div>
                    <div className="text-sm text-text-1">{activeExperimentReport.phaseA.description || "Phase A results loaded."}</div>
                    {activeExperimentReport.phaseA.controlResults && activeExperimentReport.phaseA.controlResults.length > 0 && (
                      <FinTable
                        data={activeExperimentReport.phaseA.controlResults.map((variant) => ({
                          Variant: variant.variantLabel || variant.variantId.slice(-8),
                          Strategy: variant.strategyName,
                          Score: variant.experimentScore == null ? "-" : variant.experimentScore.toFixed(1),
                          PF: variant.summary?.profitFactor == null ? "-" : variant.summary.profitFactor.toFixed(2),
                          Return: variant.summary?.totalNetReturnFraction == null ? "-" : pct(variant.summary.totalNetReturnFraction),
                        }))}
                        pnlCols={["Return"]}
                        monoCols={["Score", "PF"]}
                        maxHeight="220px"
                      />
                    )}
                  </div>
                )}
                {activeExperimentReport.phaseB && (
                  <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-3">
                    <div className="text-xs uppercase tracking-wide text-text-3">Phase B</div>
                    <div className="text-sm text-text-1">
                      {activeExperimentReport.phaseB.unlocked
                        ? "Phase B is unlocked."
                        : activeExperimentReport.phaseB.reason || "Phase B is not yet unlocked."}
                    </div>
                    <div className="text-xs text-text-2 flex flex-wrap gap-2">
                      {activeExperimentReport.phaseB.selectedFamilyWindow?.strategyFamily && (
                        <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                          Family: {activeExperimentReport.phaseB.selectedFamilyWindow.strategyFamily}
                        </span>
                      )}
                      {activeExperimentReport.phaseB.selectedFamilyWindow?.windowModeLabel && (
                        <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                          Window: {activeExperimentReport.phaseB.selectedFamilyWindow.windowModeLabel}
                        </span>
                      )}
                      {activeExperimentReport.phaseB.batchShape && (
                        <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1">
                          Batch: {activeExperimentReport.phaseB.batchShape}
                        </span>
                      )}
                    </div>
                    {activeExperimentReport.phaseB.results && activeExperimentReport.phaseB.results.length > 0 && (
                      <FinTable
                        data={activeExperimentReport.phaseB.results.map((variant) => ({
                          Variant: variant.variantLabel || variant.variantId.slice(-8),
                          Strategy: variant.strategyName,
                          Score: variant.experimentScore == null ? "-" : variant.experimentScore.toFixed(1),
                          PF: variant.summary?.profitFactor == null ? "-" : variant.summary.profitFactor.toFixed(2),
                          Return: variant.summary?.totalNetReturnFraction == null ? "-" : pct(variant.summary.totalNetReturnFraction),
                        }))}
                        pnlCols={["Return"]}
                        monoCols={["Score", "PF"]}
                        maxHeight="220px"
                      />
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border bg-bg-3/70 px-4 py-5 text-sm text-text-2">
            No experiment report is loaded yet. Use the controls above to view the latest sweep or run a fresh one.
          </div>
        )}
      </div>
    </div>
  );
}
