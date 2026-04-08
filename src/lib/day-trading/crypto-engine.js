const fs = require("fs");
const path = require("path");
const https = require("https");

const legacyEngine = require("./engine");

const shared = legacyEngine.__internal;

const DATA_ROOT = process.env.DAY_TRADING_CRYPTO_DATA_ROOT
  ? path.resolve(process.env.DAY_TRADING_CRYPTO_DATA_ROOT)
  : path.join(process.cwd(), "data", "day-trading", "crypto");
const RAW_DOWNLOADS_DIR = path.join(DATA_ROOT, "raw-downloads");
const NORMALIZED_1M_DIR = path.join(DATA_ROOT, "normalized-1m");
const DERIVED_5M_DIR = path.join(DATA_ROOT, "derived-5m");
const STRATEGIES_PATH = path.join(DATA_ROOT, "strategies.json");
const LEDGER_PATH = path.join(DATA_ROOT, "paper_trading_ledger.json");
const REPORT_PATH = path.join(DATA_ROOT, "trading_validation_report.json");
const WATCHLIST_PATH = path.join(DATA_ROOT, "watchlist_latest.json");
const BACKTEST_DIR = path.join(DATA_ROOT, "backtests");
const EXPERIMENTS_DIR = path.join(DATA_ROOT, "experiments");
const EXPERIMENT_REPORT_PATH = path.join(EXPERIMENTS_DIR, "latest.json");
const IMPORT_REPORT_PATH = path.join(DATA_ROOT, "import_latest.json");
const PROFITABILITY_JOURNAL_PATH = path.join(DATA_ROOT, "profitability_journal.json");
const PROFITABILITY_TICKETS_PATH = path.join(DATA_ROOT, "profitability_preflight_tickets.json");
const READ_ONLY_BUNDLE_CACHE = new Map();
const NORMALIZED_BARS_CACHE = new Map();
const DEFAULT_ACCOUNT_ID = "paper-main";
const MANAGED_STRATEGY_OWNER = "options-chatbot-day-trading-crypto";
const PROFITABILITY_PROFILE_ID = "crypto_profitability_v1";
const DEFAULT_MARKET = "crypto";
const DEFAULT_EXCHANGE = "binance_us";
const DEFAULT_MARKET_TYPE = "spot";
const DEFAULT_INTERVAL = "1m";
const DEFAULT_TIMEFRAME = "5m";
const LOCAL_SESSION_TIMEZONE = "America/Denver";
const SESSION_TIMEZONE = "America/New_York";
const BTC_PROFITABILITY_SETUP_ID = "btcusdt-crypto-range-mean-reversion";
const BTC_PROFITABILITY_SYMBOL = "BTCUSDT";
const PROFITABILITY_REVIEW_TARGET = 30;
const PROFITABILITY_ADVANCE_TARGET = 50;
const PROFITABILITY_DAILY_TRADE_CAP = 2;
const EVENT_SHOCK_LOCKOUT_BARS = 6;
const LOCAL_SESSION_END_MINUTES = (11 * 60);
const BINANCE_API_ROOTS = [
  process.env.DAY_TRADING_CRYPTO_API_ROOT || "https://api.binance.us",
  "https://api.binance.com",
];
const ET_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: SESSION_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  weekday: "short",
  hour12: false,
});
const LOCAL_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: LOCAL_SESSION_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  weekday: "short",
  hour12: false,
});
const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const TRADING_WEEKDAYS = new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]);
const VALID_WINDOW_MODES = new Set(["all_hours", "scheduled_windows", "denver_core"]);
const RESEARCH_WINDOW_MODES = ["scheduled_windows", "denver_core", "all_hours"];
const FROZEN_CRYPTO_FAMILIES = new Set([
  "crypto_bottom_reclaim",
  "crypto_failed_breakdown_reclaim",
  "crypto_opening_range_breakout",
  "crypto_range_mean_reversion",
  "crypto_trend_continuation",
  "crypto_delta_divergence",
  "crypto_delta_breakout",
  "crypto_absorption",
  "crypto_exhaustion",
]);
const CRYPTO_FAMILY_CONTINUE_RULES = {
  minimumTrades: 30,
  minimumProfitFactor: 1.05,
  maxDominantClusterShare: 0.7,
};
const CRYPTO_FAMILY_CHALLENGER_GATE = {
  minimumTrades: 20,
};
const CRYPTO_FUTURES_VALIDATION_GATE = {
  minimumTrades: 50,
  minimumProfitFactor: 1.1,
};
const DEFAULT_CRYPTO_DAY_TRADING_CONFIG = {
  market: DEFAULT_MARKET,
  exchange: DEFAULT_EXCHANGE,
  marketType: DEFAULT_MARKET_TYPE,
  sessionMode: "scheduled_windows",
  importInterval: DEFAULT_INTERVAL,
  strategyTimeframe: DEFAULT_TIMEFRAME,
  bars: 3120,
  startingCash: 10000,
  feesFraction: 0.0002,
  watchlistLimit: 4,
  notifyLookbackBars: 1,
  maxBarAgeMinutes: 10,
  importLookbackDays: 90,
  livePollMinutes: 180,
  localSessionTimeZone: LOCAL_SESSION_TIMEZONE,
  sessionTimeZone: SESSION_TIMEZONE,
  alertWindows: [
    { id: "denver_core", label: "Denver Core", startEt: "09:00", endEt: "13:00" },
  ],
};
const VALID_STATUSES = new Set([
  "draft",
  "backtest_failed",
  "paper_candidate",
  "paper_live",
  "promotion_review",
  "candidate_live",
  "disabled",
]);
const CRYPTO_EXPERIMENT_LIBRARY = {
  crypto_bottom_reclaim: {
    signalThresholds: [0.52, 0.60, 0.68],
    takeProfitFractions: [0.006, 0.007, 0.008],
    stopLossFractions: [0.0035, 0.0042, 0.005],
    maxHoldBars: [3, 5, 6],
    atrStopMultipliers: [0, 1.2, 1.8],
    atrTargetMultipliers: [0, 2.0, 2.8],
  },
  crypto_failed_breakdown_reclaim: {
    signalThresholds: [0.50, 0.58, 0.66],
    takeProfitFractions: [0.006, 0.007, 0.008],
    stopLossFractions: [0.0038, 0.0046, 0.0052],
    maxHoldBars: [3, 5, 6],
    atrStopMultipliers: [0, 1.2, 1.8],
    atrTargetMultipliers: [0, 2.0, 2.8],
  },
  crypto_opening_range_breakout: {
    signalThresholds: [0.55, 0.62, 0.70],
    takeProfitFractions: [0.009, 0.011, 0.013],
    stopLossFractions: [0.003, 0.004, 0.005],
    maxHoldBars: [4, 6, 8],
    atrStopMultipliers: [0, 1.0, 1.5],
    atrTargetMultipliers: [0, 2.5, 3.5],
  },
  crypto_range_mean_reversion: {
    signalThresholds: [0.50, 0.58, 0.66],
    takeProfitFractions: [0.005, 0.006, 0.007],
    stopLossFractions: [0.003, 0.0035, 0.004],
    maxHoldBars: [4, 6, 8],
    atrStopMultipliers: [0, 1.0, 1.5],
    atrTargetMultipliers: [0, 1.8, 2.5],
  },
  crypto_trend_continuation: {
    signalThresholds: [0.55, 0.62, 0.70],
    takeProfitFractions: [0.01, 0.013, 0.016],
    stopLossFractions: [0.004, 0.005, 0.006],
    maxHoldBars: [6, 8, 10],
    atrStopMultipliers: [0, 1.5, 2.0],
    atrTargetMultipliers: [0, 3.0, 4.0],
  },
  crypto_delta_divergence: {
    signalThresholds: [0.48, 0.55, 0.62],
    takeProfitFractions: [0.004, 0.006, 0.008],
    stopLossFractions: [0.0025, 0.0035, 0.0045],
    maxHoldBars: [3, 5, 8],
    atrStopMultipliers: [0, 1.0, 1.5],
    atrTargetMultipliers: [0, 2.0, 3.0],
  },
  crypto_delta_breakout: {
    signalThresholds: [0.50, 0.58, 0.66],
    takeProfitFractions: [0.006, 0.009, 0.012],
    stopLossFractions: [0.003, 0.004, 0.005],
    maxHoldBars: [4, 6, 10],
    atrStopMultipliers: [0, 1.2, 1.8],
    atrTargetMultipliers: [0, 2.5, 3.5],
  },
  crypto_absorption: {
    signalThresholds: [0.46, 0.53, 0.60],
    takeProfitFractions: [0.003, 0.005, 0.007],
    stopLossFractions: [0.002, 0.003, 0.004],
    maxHoldBars: [2, 4, 6],
    atrStopMultipliers: [0, 0.8, 1.2],
    atrTargetMultipliers: [0, 1.5, 2.2],
  },
  crypto_exhaustion: {
    signalThresholds: [0.48, 0.55, 0.62],
    takeProfitFractions: [0.004, 0.006, 0.008],
    stopLossFractions: [0.0025, 0.0035, 0.005],
    maxHoldBars: [2, 4, 6],
    atrStopMultipliers: [0, 1.0, 1.5],
    atrTargetMultipliers: [0, 2.0, 2.8],
  },
};
const PROFITABILITY_PRETRADE_CHECKLIST = [
  {
    key: "setup_match_confirmed",
    label: "Setup match confirmed",
    description: "The trade matches the BTC range mean-reversion playbook exactly.",
    required: true,
  },
  {
    key: "headline_lockout_checked",
    label: "Headline lockout checked",
    description: "No fresh catalyst, exploit, or macro event is invalidating the fade.",
    required: true,
  },
  {
    key: "maker_limit_plan_confirmed",
    label: "Maker limit plan confirmed",
    description: "Entry uses a maker/post-only plan instead of a routine market order.",
    required: true,
  },
];

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function round(value, digits = 6) {
  return Number.isFinite(value) ? Number(value.toFixed(digits)) : null;
}

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function atomicWriteJsonSync(filePath, payload) {
  ensureDir(path.dirname(filePath));
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tempPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  fs.renameSync(tempPath, filePath);
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function nowIso() {
  return new Date().toISOString();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseClockToMinutes(value, fallback) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return fallback;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fallback;
  return (hour * 60) + minute;
}

function normalizeWindowMode(value, fallback = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode) {
  const normalized = String(value || "").trim().toLowerCase();
  if (VALID_WINDOW_MODES.has(normalized)) return normalized;
  return VALID_WINDOW_MODES.has(fallback) ? fallback : DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode;
}

function resolveExperimentWindowModes(value) {
  if (Array.isArray(value) && value.length > 0) {
    return [...new Set(value.map((entry) => normalizeWindowMode(entry)).filter(Boolean))];
  }
  if (value) {
    return [normalizeWindowMode(value)];
  }
  return RESEARCH_WINDOW_MODES.slice();
}

function normalizeBarsSelection(value, fallback = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars) {
  if (typeof value === "string" && value.trim().toLowerCase() === "all") {
    return "all";
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 0) {
    return Math.max(120, Math.round(numeric));
  }
  return fallback;
}

function getAlertWindowById(windowId, config = DEFAULT_CRYPTO_DAY_TRADING_CONFIG) {
  return (config.alertWindows || []).find((window) => window.id === windowId) || null;
}

function getWindowModeLabel(windowMode, config = DEFAULT_CRYPTO_DAY_TRADING_CONFIG) {
  if (windowMode === "all_hours") return "All Hours";
  if (windowMode === "scheduled_windows") return "Fixed Session";
  return getAlertWindowById(windowMode, config)?.label || windowMode;
}

function getEtParts(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(
    ET_FORMATTER.formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    weekday: parts.weekday,
  };
}

function getLocalParts(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(
    LOCAL_FORMATTER.formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    weekday: parts.weekday,
  };
}

function getLocalMinutesSinceMidnight(timestamp) {
  const parts = getLocalParts(timestamp);
  if (!parts) return null;
  return (parts.hour * 60) + parts.minute;
}

function isDuringLocalTradingSession(timestamp) {
  const parts = getLocalParts(timestamp);
  if (!parts || !TRADING_WEEKDAYS.has(parts.weekday)) return false;
  const minutesSinceMidnight = (parts.hour * 60) + parts.minute;
  return minutesSinceMidnight >= (7 * 60) && minutesSinceMidnight < LOCAL_SESSION_END_MINUTES;
}

function classifyScheduledWindow(timestamp, config = DEFAULT_CRYPTO_DAY_TRADING_CONFIG) {
  const parts = getEtParts(timestamp);
  if (!parts) {
    return { active: false, label: "invalid_time", windowId: null, windowLabel: null, minutesSinceMidnight: null };
  }
  if (!TRADING_WEEKDAYS.has(parts.weekday)) {
    return {
      active: false,
      label: "outside_trading_days",
      windowId: null,
      windowLabel: null,
      minutesSinceMidnight: (parts.hour * 60) + parts.minute,
    };
  }

  const minutesSinceMidnight = (parts.hour * 60) + parts.minute;
  for (const window of config.alertWindows || []) {
    const startMinutes = parseClockToMinutes(window.startEt, 0);
    const endMinutes = parseClockToMinutes(window.endEt, startMinutes);
    if (minutesSinceMidnight >= startMinutes && minutesSinceMidnight < endMinutes) {
      return {
        active: true,
        label: window.id,
        windowId: window.id,
        windowLabel: window.label,
        startEt: window.startEt,
        endEt: window.endEt,
        minutesSinceMidnight,
      };
    }
  }

  return {
    active: false,
    label: "outside_windows",
    windowId: null,
    windowLabel: null,
    minutesSinceMidnight,
  };
}

function classifyWindow(timestamp, options = {}) {
  const config = options.config || DEFAULT_CRYPTO_DAY_TRADING_CONFIG;
  const windowMode = normalizeWindowMode(options.windowMode, config.sessionMode);
  const parts = getEtParts(timestamp);
  if (!parts) {
    return { active: false, label: "invalid_time", windowId: null, windowLabel: null, minutesSinceMidnight: null };
  }
  if (!TRADING_WEEKDAYS.has(parts.weekday)) {
    return {
      active: false,
      label: "outside_trading_days",
      windowId: null,
      windowLabel: null,
      minutesSinceMidnight: (parts.hour * 60) + parts.minute,
    };
  }
  if (windowMode === "all_hours") {
    return {
      active: true,
      label: "all_hours",
      windowId: "all_hours",
      windowLabel: "All Hours",
      startEt: "00:00",
      endEt: "24:00",
      minutesSinceMidnight: (parts.hour * 60) + parts.minute,
    };
  }
  if (windowMode === "scheduled_windows") {
    return classifyScheduledWindow(timestamp, config);
  }

  const targetWindow = getAlertWindowById(windowMode, config);
  if (!targetWindow) {
    return {
      active: false,
      label: `unsupported_window_mode:${windowMode}`,
      windowId: null,
      windowLabel: null,
      minutesSinceMidnight: (parts.hour * 60) + parts.minute,
    };
  }

  const minutesSinceMidnight = (parts.hour * 60) + parts.minute;
  const startMinutes = parseClockToMinutes(targetWindow.startEt, 0);
  const endMinutes = parseClockToMinutes(targetWindow.endEt, startMinutes);
  if (minutesSinceMidnight >= startMinutes && minutesSinceMidnight < endMinutes) {
    return {
      active: true,
      label: targetWindow.id,
      windowId: targetWindow.id,
      windowLabel: targetWindow.label,
      startEt: targetWindow.startEt,
      endEt: targetWindow.endEt,
      minutesSinceMidnight,
    };
  }

  return {
    active: false,
    label: `outside_${targetWindow.id}`,
    windowId: targetWindow.id,
    windowLabel: targetWindow.label,
    startEt: targetWindow.startEt,
    endEt: targetWindow.endEt,
    minutesSinceMidnight,
  };
}

function buildWindowSessionKey(timestamp, options = {}) {
  const config = options.config || DEFAULT_CRYPTO_DAY_TRADING_CONFIG;
  const windowMode = normalizeWindowMode(options.windowMode, config.sessionMode);
  const parts = getEtParts(timestamp);
  const window = classifyWindow(timestamp, { config, windowMode });
  if (!parts) return null;
  if (windowMode === "all_hours") {
    return `${parts.date}::all_hours`;
  }
  if (!window.active || !window.windowId) return null;
  return `${parts.date}::${window.windowId}`;
}

function uniqueNumbers(values = []) {
  return [...new Set(values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0)
    .map((value) => Number(value.toFixed(6))))];
}

function normalizeCsvPathInput(value) {
  if (!value) return [];
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildProfitabilityChecklistSchema() {
  return clone(PROFITABILITY_PRETRADE_CHECKLIST);
}

function buildProfitabilityJournalSchema() {
  return [
    { key: "ticketId", label: "Approval ticket", required: true },
    { key: "tradeTimestamp", label: "Trade time", required: true },
    { key: "sessionLabel", label: "Session", required: true },
    { key: "symbol", label: "Coin", required: true },
    { key: "regime", label: "Regime", required: true },
    { key: "setupId", label: "Setup ID", required: true },
    { key: "setup_match_confirmed", label: "Setup match confirmed", required: true },
    { key: "headline_lockout_checked", label: "Headline lockout checked", required: true },
    { key: "maker_limit_plan_confirmed", label: "Maker limit plan confirmed", required: true },
    { key: "side", label: "Side", required: true },
    { key: "plannedEntryPrice", label: "Planned entry", required: true },
    { key: "actualEntryPrice", label: "Actual entry", required: true },
    { key: "stopPrice", label: "Stop", required: true },
    { key: "targetPrice", label: "Target", required: true },
    { key: "actualExitPrice", label: "Actual exit", required: true },
    { key: "orderType", label: "Order type", required: true },
    { key: "entryLiquidityRole", label: "Entry liquidity role", required: true },
    { key: "exitLiquidityRole", label: "Exit liquidity role", required: true },
    { key: "entryFillRatio", label: "Entry fill ratio", required: true },
    { key: "exitFillRatio", label: "Exit fill ratio", required: true },
    { key: "exitReason", label: "Exit reason", required: true },
    { key: "stopExecutionQuality", label: "Stop execution quality", required: true },
    { key: "sizeUsd", label: "Size (USD)", required: true },
    { key: "feesUsd", label: "Fees (USD)", required: true },
    { key: "spreadSlippageUsd", label: "Spread + slippage (USD)", required: true },
    { key: "pnlR", label: "Realized PnL (R)", required: true },
    { key: "pnlUsd", label: "Realized PnL (USD)", required: true },
    { key: "screenshotPath", label: "Screenshot path", required: true },
    { key: "ruleAdherenceScore", label: "Rule adherence", required: true },
    { key: "mistakeTag", label: "Mistake tag", required: true },
    { key: "note", label: "Post-trade note", required: true },
    { key: "pilotEligible", label: "Pilot eligible", required: false },
    { key: "pilotDisqualificationReasons", label: "Pilot disqualification reasons", required: false },
    { key: "entrySlippageBps", label: "Entry slippage (bps)", required: false },
    { key: "exitSlippageBps", label: "Exit slippage (bps)", required: false },
    { key: "roundTripCostBps", label: "Round-trip cost (bps)", required: false },
  ];
}

function defaultProfitabilityJournal() {
  return {
    version: 1,
    profileId: PROFITABILITY_PROFILE_ID,
    generatedAt: nowIso(),
    schema: buildProfitabilityJournalSchema(),
    entries: [],
  };
}

function normalizeRuleAdherenceScore(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (numeric <= 1) return Math.max(0, Math.min(100, numeric * 100));
  return Math.max(0, Math.min(100, numeric));
}

function readProfitabilityJournal() {
  const fallback = defaultProfitabilityJournal();
  const stored = readJson(PROFITABILITY_JOURNAL_PATH, fallback);
  return {
    ...fallback,
    ...stored,
    profileId: PROFITABILITY_PROFILE_ID,
    schema: buildProfitabilityJournalSchema(),
    entries: Array.isArray(stored?.entries)
      ? stored.entries.map((entry) => ({
        ...entry,
        pilotEligible: entry?.pilotEligible === true,
        pilotDisqualificationReasons: Array.isArray(entry?.pilotDisqualificationReasons)
          ? entry.pilotDisqualificationReasons
          : (entry?.pilotEligible === true ? [] : ["legacy_entry_missing_guardrails"]),
      }))
      : [],
  };
}

function serializeProfitabilityJournalEntry(entry = {}) {
  return {
    entryId: String(entry.entryId || ""),
    ticketId: String(entry.ticketId || ""),
    tradeTimestamp: entry.tradeTimestamp || null,
    loggedAt: entry.loggedAt || null,
    localTradeDate: String(entry.localTradeDate || ""),
    sessionLabel: String(entry.sessionLabel || ""),
    symbol: String(entry.symbol || "").toUpperCase(),
    regime: String(entry.regime || ""),
    setupId: String(entry.setupId || ""),
    side: String(entry.side || ""),
    orderType: String(entry.orderType || ""),
    entryLiquidityRole: String(entry.entryLiquidityRole || ""),
    exitLiquidityRole: String(entry.exitLiquidityRole || ""),
    entryFillRatio: Number.isFinite(Number(entry.entryFillRatio)) ? Number(entry.entryFillRatio) : null,
    exitFillRatio: Number.isFinite(Number(entry.exitFillRatio)) ? Number(entry.exitFillRatio) : null,
    plannedEntryPrice: Number.isFinite(Number(entry.plannedEntryPrice)) ? Number(entry.plannedEntryPrice) : null,
    actualEntryPrice: Number.isFinite(Number(entry.actualEntryPrice)) ? Number(entry.actualEntryPrice) : null,
    stopPrice: Number.isFinite(Number(entry.stopPrice)) ? Number(entry.stopPrice) : null,
    targetPrice: Number.isFinite(Number(entry.targetPrice)) ? Number(entry.targetPrice) : null,
    actualExitPrice: Number.isFinite(Number(entry.actualExitPrice)) ? Number(entry.actualExitPrice) : null,
    sizeUsd: Number.isFinite(Number(entry.sizeUsd)) ? Number(entry.sizeUsd) : null,
    feesUsd: Number.isFinite(Number(entry.feesUsd)) ? Number(entry.feesUsd) : null,
    spreadSlippageUsd: Number.isFinite(Number(entry.spreadSlippageUsd)) ? Number(entry.spreadSlippageUsd) : null,
    pnlR: Number.isFinite(Number(entry.pnlR)) ? Number(entry.pnlR) : null,
    pnlUsd: Number.isFinite(Number(entry.pnlUsd)) ? Number(entry.pnlUsd) : null,
    ruleAdherenceScore: normalizeRuleAdherenceScore(entry.ruleAdherenceScore),
    mistakeTag: String(entry.mistakeTag || "none"),
    stopExecutionQuality: String(entry.stopExecutionQuality || ""),
    roundTripCostBps: Number.isFinite(Number(entry.roundTripCostBps)) ? Number(entry.roundTripCostBps) : null,
    pilotEligible: entry.pilotEligible === true,
    pilotDisqualificationReasons: Array.isArray(entry.pilotDisqualificationReasons)
      ? [...entry.pilotDisqualificationReasons]
      : [],
    note: String(entry.note || ""),
  };
}

function getEntryLocalDate(entry = {}) {
  const explicit = String(entry.localTradeDate || "").trim();
  if (explicit) return explicit;
  return getLocalParts(entry.tradeTimestamp || entry.loggedAt || nowIso())?.date || null;
}

function aggregateProfitabilityJournalEntries(entries = []) {
  const list = Array.isArray(entries) ? entries : [];
  const eligibleEntries = list.filter((entry) => entry.pilotEligible === true);
  const disqualifiedEntries = list.filter((entry) => entry.pilotEligible === false);
  const totalPnlUsd = list.reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const eligiblePnlUsd = eligibleEntries.reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const expectancyR = eligibleEntries.length > 0
    ? eligibleEntries.reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0) / eligibleEntries.length
    : null;
  const winRate = eligibleEntries.length > 0
    ? eligibleEntries.filter((entry) => Number(entry.pnlR || 0) > 0).length / eligibleEntries.length
    : null;
  const ruleAdherenceRate = list.length > 0
    ? list.reduce((sum, entry) => sum + Number(normalizeRuleAdherenceScore(entry.ruleAdherenceScore) || 0), 0) / list.length / 100
    : null;

  return {
    totalEntries: list.length,
    eligibleEntries: eligibleEntries.length,
    disqualifiedEntries: disqualifiedEntries.length,
    netPnlUsd: round(totalPnlUsd, 2),
    eligibleNetPnlUsd: round(eligiblePnlUsd, 2),
    expectancyR: expectancyR == null ? null : round(expectancyR, 3),
    winRate: winRate == null ? null : round(winRate, 4),
    ruleAdherenceRate: ruleAdherenceRate == null ? null : round(ruleAdherenceRate, 4),
  };
}

function buildProfitabilityJournalSummary(journal, options = {}) {
  const recentLimit = Math.max(1, Number(options.recentLimit) || 6);
  const entries = Array.isArray(journal?.entries) ? journal.entries : [];
  const todayDate = String(options.todayDate || getLocalParts(options.now || nowIso())?.date || "");
  const todayEntries = todayDate
    ? entries.filter((entry) => getEntryLocalDate(entry) === todayDate)
    : [];
  const trailingDateSet = new Set();
  if (todayDate) {
    const current = new Date(`${todayDate}T00:00:00`);
    for (let offset = 0; offset < 7; offset += 1) {
      const next = new Date(current);
      next.setDate(current.getDate() - offset);
      trailingDateSet.add([
        next.getFullYear(),
        String(next.getMonth() + 1).padStart(2, "0"),
        String(next.getDate()).padStart(2, "0"),
      ].join("-"));
    }
  }
  const trailingWeekEntries = trailingDateSet.size > 0
    ? entries.filter((entry) => trailingDateSet.has(getEntryLocalDate(entry)))
    : [];
  const recentEntries = entries
    .slice()
    .sort((left, right) => String(right.tradeTimestamp || right.loggedAt || "").localeCompare(String(left.tradeTimestamp || left.loggedAt || "")))
    .slice(0, recentLimit)
    .map((entry) => serializeProfitabilityJournalEntry(entry));
  const recentEligibleEntries = entries
    .filter((entry) => entry.pilotEligible === true)
    .slice()
    .sort((left, right) => String(right.tradeTimestamp || right.loggedAt || "").localeCompare(String(left.tradeTimestamp || left.loggedAt || "")))
    .slice(0, recentLimit)
    .map((entry) => serializeProfitabilityJournalEntry(entry));
  const byDate = [...new Set(entries.map((entry) => getEntryLocalDate(entry)).filter(Boolean))]
    .sort((left, right) => String(right).localeCompare(String(left)))
    .map((date) => {
      const groupedEntries = entries.filter((entry) => getEntryLocalDate(entry) === date);
      return {
        label: date,
        ...aggregateProfitabilityJournalEntries(groupedEntries),
      };
    })
    .slice(0, 7);
  const byMistakeTag = [...new Set(entries.map((entry) => String(entry.mistakeTag || "none")))]
    .sort((left, right) => String(left).localeCompare(String(right)))
    .map((mistakeTag) => {
      const groupedEntries = entries.filter((entry) => String(entry.mistakeTag || "none") === mistakeTag);
      return {
        label: mistakeTag,
        ...aggregateProfitabilityJournalEntries(groupedEntries),
      };
    })
    .sort((left, right) => (
      Number(right.totalEntries || 0) - Number(left.totalEntries || 0) ||
      Number(right.disqualifiedEntries || 0) - Number(left.disqualifiedEntries || 0) ||
      String(left.label).localeCompare(String(right.label))
    ));

  return {
    path: PROFITABILITY_JOURNAL_PATH,
    ticketPath: PROFITABILITY_TICKETS_PATH,
    entryCount: entries.length,
    schema: buildProfitabilityJournalSchema(),
    lastLoggedAt: recentEntries[0]?.loggedAt || null,
    todayDate: todayDate || null,
    todayEntryCount: todayEntries.length,
    todayEntries: todayEntries
      .slice()
      .sort((left, right) => String(right.tradeTimestamp || right.loggedAt || "").localeCompare(String(left.tradeTimestamp || left.loggedAt || "")))
      .map((entry) => serializeProfitabilityJournalEntry(entry)),
    recentEntries,
    recentEligibleEntries,
    today: {
      label: todayDate || "today",
      ...aggregateProfitabilityJournalEntries(todayEntries),
    },
    trailingWeek: {
      label: "Trailing 7 days",
      ...aggregateProfitabilityJournalEntries(trailingWeekEntries),
    },
    byDate,
    byMistakeTag,
  };
}

function defaultProfitabilityTicketStore() {
  return {
    version: 1,
    profileId: PROFITABILITY_PROFILE_ID,
    generatedAt: nowIso(),
    dailyTradeCap: PROFITABILITY_DAILY_TRADE_CAP,
    checklist: buildProfitabilityChecklistSchema(),
    tickets: [],
  };
}

function readProfitabilityTicketStore() {
  const fallback = defaultProfitabilityTicketStore();
  const stored = readJson(PROFITABILITY_TICKETS_PATH, fallback);
  return {
    ...fallback,
    ...stored,
    profileId: PROFITABILITY_PROFILE_ID,
    dailyTradeCap: PROFITABILITY_DAILY_TRADE_CAP,
    checklist: buildProfitabilityChecklistSchema(),
    tickets: Array.isArray(stored?.tickets) ? stored.tickets : [],
  };
}

function saveProfitabilityTicketStore(store) {
  atomicWriteJsonSync(PROFITABILITY_TICKETS_PATH, {
    ...defaultProfitabilityTicketStore(),
    ...store,
    generatedAt: nowIso(),
    profileId: PROFITABILITY_PROFILE_ID,
    dailyTradeCap: PROFITABILITY_DAILY_TRADE_CAP,
    checklist: buildProfitabilityChecklistSchema(),
    tickets: Array.isArray(store?.tickets) ? store.tickets : [],
  });
}

function resolveChecklistFlags(input = {}) {
  const resolve = (key) => input[key] === true;
  return {
    setup_match_confirmed: resolve("setup_match_confirmed"),
    headline_lockout_checked: resolve("headline_lockout_checked"),
    maker_limit_plan_confirmed: resolve("maker_limit_plan_confirmed"),
  };
}

function getChecklistFailures(flags = {}) {
  return buildProfitabilityChecklistSchema()
    .filter((item) => item.required && flags[item.key] !== true)
    .map((item) => `manual_checklist_incomplete:${item.key}`);
}

function getTicketLifecycle(ticket = {}, referenceTimestamp = nowIso()) {
  const localDate = String(ticket.localTradeDate || "");
  const referenceLocal = getLocalParts(referenceTimestamp);
  if (!referenceLocal || !localDate) {
    return { status: "invalid", expired: false, localDate };
  }
  const expired = (
    referenceLocal.date > localDate ||
    (referenceLocal.date === localDate && ((referenceLocal.hour * 60) + referenceLocal.minute) >= LOCAL_SESSION_END_MINUTES)
  );
  if (String(ticket.status || "") === "used") {
    return { status: "used", expired: false, localDate };
  }
  if (expired) {
    return { status: "expired", expired: true, localDate };
  }
  return { status: "approved", expired: false, localDate };
}

function calculateSpreadFraction(snapshot = {}, referencePrice = 0) {
  const bestBid = Number(snapshot.bestBid);
  const bestAsk = Number(snapshot.bestAsk);
  if (Number.isFinite(bestBid) && Number.isFinite(bestAsk) && bestBid > 0 && bestAsk >= bestBid) {
    const mid = (bestBid + bestAsk) / 2;
    if (mid > 0) {
      return (bestAsk - bestBid) / mid;
    }
  }
  return referencePrice > 0 ? 0 : null;
}

function resolvePlannedTakeProfitPrice(strategy, bar, entryPrice) {
  const mode = String(strategy?.simulation?.exitTargetMode || "").toLowerCase();
  const numericEntry = Number(entryPrice);
  const candidates = [];
  if (mode === "session_vwap_or_range_midpoint" && bar?.indicators) {
    for (const value of [bar.indicators.sessionVwap, bar.indicators.sessionRangeMidpoint]) {
      const numeric = Number(value);
      if (Number.isFinite(numeric) && numeric > numericEntry) {
        candidates.push(numeric);
      }
    }
  }
  const fallback = numericEntry * (1 + Number(strategy?.simulation?.takeProfitFraction || 0));
  if (Number.isFinite(fallback) && fallback > numericEntry) {
    candidates.push(fallback);
  }
  return candidates.length > 0 ? Math.min(...candidates) : null;
}

function buildCostProfile(strategy, marketSnapshot = {}, bar) {
  const entryPrice = Number(bar?.close || 0);
  const targetPrice = resolvePlannedTakeProfitPrice(strategy, bar, entryPrice);
  const spreadFraction = calculateSpreadFraction(marketSnapshot, entryPrice);
  const feeFraction = Number(strategy?.riskLimits?.assumedRoundTripFeeFraction || 0);
  const slippageFraction = Number(strategy?.riskLimits?.assumedSlippageFraction || 0);
  const estimatedCostFraction = feeFraction + slippageFraction + (Number.isFinite(spreadFraction) ? spreadFraction : 0);
  const grossTargetFraction = (
    Number.isFinite(targetPrice) &&
    entryPrice > 0 &&
    targetPrice > entryPrice
  ) ? ((targetPrice - entryPrice) / entryPrice) : null;
  const costToTargetFraction = (
    Number.isFinite(grossTargetFraction) &&
    grossTargetFraction > 0
  ) ? (estimatedCostFraction / grossTargetFraction) : null;
  const allowed = (
    Number.isFinite(costToTargetFraction) &&
    costToTargetFraction <= Number(strategy?.riskLimits?.maxCostToTargetFraction || 0)
  );

  return {
    entryPrice: round(entryPrice, 8),
    targetPrice: Number.isFinite(targetPrice) ? round(targetPrice, 8) : null,
    spreadFraction: Number.isFinite(spreadFraction) ? round(spreadFraction, 6) : null,
    estimatedCostFraction: round(estimatedCostFraction, 6),
    grossTargetFraction: Number.isFinite(grossTargetFraction) ? round(grossTargetFraction, 6) : null,
    costToTargetFraction: Number.isFinite(costToTargetFraction) ? round(costToTargetFraction, 6) : null,
    allowed,
  };
}

function buildTodayGate(ticketStore, options = {}) {
  const now = options.now || nowIso();
  const local = getLocalParts(now);
  const dailyTradeCap = Number(ticketStore?.dailyTradeCap || PROFITABILITY_DAILY_TRADE_CAP);
  if (!local) {
    return {
      localDate: null,
      dailyTradeCap,
      reservedTickets: 0,
      usedTickets: 0,
      expiredTickets: 0,
      approvedEntries: 0,
      remainingApprovals: dailyTradeCap,
      activeSessionWindow: false,
      blocked: true,
      reasons: ["invalid_timestamp"],
    };
  }

  const todaysTickets = (ticketStore?.tickets || [])
    .filter((ticket) => String(ticket.strategyId || "") === BTC_PROFITABILITY_SETUP_ID)
    .filter((ticket) => String(ticket.symbol || "").toUpperCase() === BTC_PROFITABILITY_SYMBOL)
    .filter((ticket) => String(ticket.localTradeDate || "") === local.date)
    .map((ticket) => ({ ...ticket, lifecycle: getTicketLifecycle(ticket, now) }));

  const reservedTickets = todaysTickets.filter((ticket) => ticket.lifecycle.status === "approved").length;
  const usedTickets = todaysTickets.filter((ticket) => ticket.lifecycle.status === "used").length;
  const expiredTickets = todaysTickets.filter((ticket) => ticket.lifecycle.status === "expired").length;
  const approvedEntries = reservedTickets + usedTickets;
  const remainingApprovals = Math.max(0, dailyTradeCap - approvedEntries);
  const activeSessionWindow = isDuringLocalTradingSession(now);
  const reasons = [];
  if (!TRADING_WEEKDAYS.has(local.weekday)) reasons.push("outside_trading_days");
  if (!activeSessionWindow) reasons.push("outside_fixed_session");
  if (remainingApprovals <= 0) reasons.push("daily_trade_cap_reached");

  return {
    localDate: local.date,
    dailyTradeCap,
    reservedTickets,
    usedTickets,
    expiredTickets,
    approvedEntries,
    remainingApprovals,
    activeSessionWindow,
    blocked: reasons.length > 0,
    reasons,
  };
}

function normalizeAlertWindowIds(entries = []) {
  return [...new Set(
    entries
      .map((entry) => String(entry || "").trim())
      .filter(Boolean),
  )].sort();
}

function buildArtifactHealth(options = {}) {
  const strategies = Array.isArray(options.strategies) ? options.strategies : [];
  const lastWatchlist = options.lastWatchlist || null;
  const configuredWindowIds = normalizeAlertWindowIds(
    (DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows || []).map((window) => window.id),
  );
  const strategyWindowIds = normalizeAlertWindowIds(
    strategies.flatMap((strategy) => strategy?.metadata?.alertWindowIds || []),
  );
  const watchlistWindowIds = normalizeAlertWindowIds(
    (lastWatchlist?.alertWindows || []).map((window) => window?.id),
  );
  const warnings = [];

  const windowMismatchMessage = (label, expected, actual) => {
    const expectedText = expected.length > 0 ? expected.join(", ") : "none";
    const actualText = actual.length > 0 ? actual.join(", ") : "none";
    return `${label} still reference ${actualText} while the live pilot uses ${expectedText}.`;
  };

  if (strategyWindowIds.length > 0 && strategyWindowIds.join("|") !== configuredWindowIds.join("|")) {
    warnings.push(windowMismatchMessage("Saved strategy artifacts", configuredWindowIds, strategyWindowIds));
  }
  if (watchlistWindowIds.length > 0 && watchlistWindowIds.join("|") !== configuredWindowIds.join("|")) {
    warnings.push(windowMismatchMessage("The latest watchlist artifact", configuredWindowIds, watchlistWindowIds));
  }
  return {
    checkedAt: nowIso(),
    status: warnings.length > 0 ? "warning" : "aligned",
    configuredWindowIds,
    strategyWindowIds,
    watchlistWindowIds,
    lastWatchlistGeneratedAt: lastWatchlist?.generatedAt || null,
    warnings,
  };
}

function serializeProfitabilityTicket(ticket, lifecycle = getTicketLifecycle(ticket)) {
  return {
    ticketId: String(ticket?.ticketId || ""),
    strategyId: String(ticket?.strategyId || ""),
    symbol: String(ticket?.symbol || "").toUpperCase(),
    approvedAt: ticket?.approvedAt || null,
    usedAt: ticket?.usedAt || null,
    localTradeDate: ticket?.localTradeDate || null,
    sessionLabel: ticket?.sessionLabel || null,
    storedStatus: String(ticket?.status || "unknown"),
    lifecycleStatus: lifecycle.status,
    regimeState: ticket?.systemGateSnapshot?.regimeState || null,
    tradeable: ticket?.systemGateSnapshot?.tradeable === true,
    checklistFlags: {
      ...resolveChecklistFlags(ticket?.checklistFlags || {}),
    },
  };
}

function buildProfitabilityTicketSummary(ticketStore, options = {}) {
  const now = options.now || nowIso();
  const local = getLocalParts(now);
  const allTickets = (ticketStore?.tickets || [])
    .filter((ticket) => String(ticket?.strategyId || "") === BTC_PROFITABILITY_SETUP_ID)
    .filter((ticket) => String(ticket?.symbol || "").toUpperCase() === BTC_PROFITABILITY_SYMBOL)
    .map((ticket) => serializeProfitabilityTicket(ticket, getTicketLifecycle(ticket, now)))
    .sort((left, right) => String(right.approvedAt || "").localeCompare(String(left.approvedAt || "")));
  const todaysTickets = local
    ? allTickets.filter((ticket) => String(ticket.localTradeDate || "") === local.date)
    : [];

  return {
    path: PROFITABILITY_TICKETS_PATH,
    totalTickets: allTickets.length,
    todayDate: local?.date || null,
    todayGate: buildTodayGate(ticketStore, { now }),
    todaysTickets,
    recentTickets: allTickets.slice(0, 8),
  };
}

function readLatestExperimentReport() {
  return readJson(EXPERIMENT_REPORT_PATH, null);
}

function buildOperatorConsoleSnapshot(options = {}) {
  const now = options.now || nowIso();
  const ticketStore = options.ticketStore || readProfitabilityTicketStore();
  const journal = options.journal || readProfitabilityJournal();
  const pilotSummary = options.pilotSummary || buildProfitabilityPilotSummary(journal.entries, {
    ticketStore,
    now,
  });
  const journalSummary = buildProfitabilityJournalSummary(journal, {
    todayDate: getLocalParts(now)?.date || null,
    recentLimit: 8,
  });
  return {
    generatedAt: nowIso(),
    now,
    sessionWindow: getWindowSummary(now),
    todayGate: buildTodayGate(ticketStore, { now }),
    pilotPhase: pilotSummary.phase,
    nextUnlock: pilotSummary.nextUnlock,
    journal: journalSummary,
    experimentReport: options.experimentReport || readLatestExperimentReport(),
    artifactHealth: options.artifactHealth || buildArtifactHealth({
      strategies: options.strategies || [],
      lastWatchlist: options.lastWatchlist || null,
    }),
  };
}

function normalizeLiquidityRole(value, fallback = "unknown") {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return fallback;
  if (["maker", "post_only", "post-only"].includes(normalized)) return "maker";
  if (["taker", "marketable"].includes(normalized)) return "taker";
  return normalized;
}

function calculateSignedSlippageBps(actualPrice, referencePrice, side) {
  const actual = Number(actualPrice);
  const reference = Number(referencePrice);
  if (!Number.isFinite(actual) || !Number.isFinite(reference) || reference <= 0) return null;
  const raw = ((actual - reference) / reference) * 10000;
  return side === "sell" ? (raw * -1) : raw;
}

function buildEntryExecutionMetrics(entry = {}) {
  const entrySlippageBps = calculateSignedSlippageBps(entry.actualEntryPrice, entry.plannedEntryPrice, "buy");
  const exitReferencePrice = String(entry.exitReason || "") === "stop_loss"
    ? entry.stopPrice
    : entry.targetPrice;
  const exitSlippageBps = calculateSignedSlippageBps(entry.actualExitPrice, exitReferencePrice, "sell");
  const roundTripCostBps = Number(entry.sizeUsd) > 0
    ? (((Number(entry.feesUsd || 0) + Number(entry.spreadSlippageUsd || 0)) / Number(entry.sizeUsd)) * 10000)
    : null;

  let stopExecutionQuality = String(entry.stopExecutionQuality || "").trim().toLowerCase();
  if (!stopExecutionQuality) {
    if (String(entry.exitReason || "") === "stop_loss") {
      if (exitSlippageBps == null) {
        stopExecutionQuality = "unknown";
      } else if (exitSlippageBps < -0.5) {
        stopExecutionQuality = "slipped";
      } else if (exitSlippageBps > 0.5) {
        stopExecutionQuality = "better_than_stop";
      } else {
        stopExecutionQuality = "clean";
      }
    } else {
      stopExecutionQuality = "not_applicable";
    }
  }

  return {
    entrySlippageBps: entrySlippageBps == null ? null : round(entrySlippageBps, 3),
    exitSlippageBps: exitSlippageBps == null ? null : round(exitSlippageBps, 3),
    roundTripCostBps: roundTripCostBps == null ? null : round(roundTripCostBps, 3),
    stopExecutionQuality,
  };
}

function appendProfitabilityJournalEntry(input = {}) {
  const journal = readProfitabilityJournal();
  const ticketStore = readProfitabilityTicketStore();
  const entryId = `pilot_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const checklistFlags = resolveChecklistFlags(input);
  const checklistFailures = getChecklistFailures(checklistFlags);
  const ticketId = String(input.ticketId || "").trim();
  const tradeTimestamp = String(input.tradeTimestamp || input.timestamp || nowIso());
  const localTradeParts = getLocalParts(tradeTimestamp);
  const ticket = (ticketStore.tickets || []).find((candidate) => candidate.ticketId === ticketId) || null;
  const pilotDisqualificationReasons = [];
  if (String(input.setupId || "") !== BTC_PROFITABILITY_SETUP_ID || String(input.symbol || "").toUpperCase() !== BTC_PROFITABILITY_SYMBOL) {
    pilotDisqualificationReasons.push("non_phase_one_setup");
  }
  if (!ticketId) {
    pilotDisqualificationReasons.push("missing_ticket_id");
  } else if (!ticket) {
    pilotDisqualificationReasons.push("ticket_not_found");
  } else {
    const lifecycle = getTicketLifecycle(ticket, tradeTimestamp);
    if (lifecycle.status === "expired") {
      pilotDisqualificationReasons.push("ticket_expired");
    }
    if (String(ticket.status || "") === "used") {
      pilotDisqualificationReasons.push("ticket_already_used");
    }
    if (String(ticket.strategyId || "") !== String(input.setupId || "")) {
      pilotDisqualificationReasons.push("ticket_setup_mismatch");
    }
    if (String(ticket.symbol || "").toUpperCase() !== String(input.symbol || "").toUpperCase()) {
      pilotDisqualificationReasons.push("ticket_symbol_mismatch");
    }
    if (String(ticket.localTradeDate || "") !== String(localTradeParts?.date || "")) {
      pilotDisqualificationReasons.push("ticket_trade_day_mismatch");
    }
  }
  if (!isDuringLocalTradingSession(tradeTimestamp)) {
    pilotDisqualificationReasons.push("trade_outside_session");
  }
  pilotDisqualificationReasons.push(...checklistFailures);

  const entry = {
    entryId,
    loggedAt: nowIso(),
    ticketId,
    tradeTimestamp,
    localTradeDate: localTradeParts?.date || null,
    sessionLabel: String(input.sessionLabel || "Denver Core"),
    symbol: String(input.symbol || "").toUpperCase(),
    regime: String(input.regime || "").toLowerCase(),
    setupId: String(input.setupId || ""),
    setup_match_confirmed: checklistFlags.setup_match_confirmed,
    headline_lockout_checked: checklistFlags.headline_lockout_checked,
    maker_limit_plan_confirmed: checklistFlags.maker_limit_plan_confirmed,
    side: String(input.side || "").toLowerCase(),
    plannedEntryPrice: Number(input.plannedEntryPrice),
    actualEntryPrice: Number(input.actualEntryPrice),
    stopPrice: Number(input.stopPrice),
    targetPrice: Number(input.targetPrice),
    actualExitPrice: Number(input.actualExitPrice),
    orderType: String(input.orderType || ""),
    entryLiquidityRole: normalizeLiquidityRole(input.entryLiquidityRole),
    exitLiquidityRole: normalizeLiquidityRole(input.exitLiquidityRole),
    entryFillRatio: Number(input.entryFillRatio),
    exitFillRatio: Number(input.exitFillRatio),
    exitReason: String(input.exitReason || "").toLowerCase(),
    stopExecutionQuality: String(input.stopExecutionQuality || "").trim().toLowerCase(),
    sizeUsd: Number(input.sizeUsd),
    feesUsd: Number(input.feesUsd || 0),
    spreadSlippageUsd: Number(input.spreadSlippageUsd || 0),
    pnlR: Number(input.pnlR),
    pnlUsd: Number(input.pnlUsd),
    screenshotPath: String(input.screenshotPath || ""),
    ruleAdherenceScore: normalizeRuleAdherenceScore(input.ruleAdherenceScore),
    mistakeTag: String(input.mistakeTag || "none"),
    note: String(input.note || ""),
  };
  const executionMetrics = buildEntryExecutionMetrics(entry);
  entry.entrySlippageBps = executionMetrics.entrySlippageBps;
  entry.exitSlippageBps = executionMetrics.exitSlippageBps;
  entry.roundTripCostBps = executionMetrics.roundTripCostBps;
  entry.stopExecutionQuality = executionMetrics.stopExecutionQuality;
  entry.pilotEligible = pilotDisqualificationReasons.length === 0;
  entry.pilotDisqualificationReasons = [...new Set(pilotDisqualificationReasons)];

  if (entry.pilotEligible && ticket) {
    ticket.status = "used";
    ticket.usedAt = entry.loggedAt;
    ticket.usedByEntryId = entry.entryId;
    saveProfitabilityTicketStore(ticketStore);
  }

  journal.entries.push(entry);
  journal.generatedAt = nowIso();
  atomicWriteJsonSync(PROFITABILITY_JOURNAL_PATH, journal);
  return {
    journal,
    ticketStore,
    entry,
    summary: buildProfitabilityPilotSummary(journal.entries, {
      ticketStore,
      now: entry.tradeTimestamp,
    }),
  };
}

function computeProfitFactorFromEntries(entries = []) {
  const grossWins = entries
    .filter((entry) => Number(entry.pnlR || 0) > 0)
    .reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0);
  const grossLosses = Math.abs(entries
    .filter((entry) => Number(entry.pnlR || 0) < 0)
    .reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0));
  if (grossLosses === 0) {
    return grossWins > 0 ? null : 0;
  }
  return grossWins / grossLosses;
}

function computeMaxDrawdownR(entries = []) {
  let equity = 0;
  let peak = 0;
  let maxDrawdown = 0;
  for (const entry of entries) {
    equity += Number(entry.pnlR || 0);
    peak = Math.max(peak, equity);
    maxDrawdown = Math.max(maxDrawdown, peak - equity);
  }
  return maxDrawdown;
}

function buildEntryBreakdown(entries = [], key) {
  const grouped = new Map();
  for (const entry of entries) {
    const groupKey = String(entry?.[key] || "unknown");
    const list = grouped.get(groupKey) || [];
    list.push(entry);
    grouped.set(groupKey, list);
  }

  return [...grouped.entries()]
    .map(([groupKey, groupedEntries]) => {
      const wins = groupedEntries.filter((entry) => Number(entry.pnlR || 0) > 0).length;
      const expectancyR = groupedEntries.reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0) / groupedEntries.length;
      const netPnlUsd = groupedEntries.reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
      return {
        label: groupKey,
        trades: groupedEntries.length,
        winRate: wins / groupedEntries.length,
        expectancyR,
        netPnlUsd,
      };
    })
    .sort((left, right) => Number(right.netPnlUsd || 0) - Number(left.netPnlUsd || 0));
}

function buildDisqualificationBreakdown(entries = []) {
  const counts = new Map();
  for (const entry of entries) {
    for (const reason of entry.pilotDisqualificationReasons || []) {
      counts.set(reason, (counts.get(reason) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((left, right) => right.count - left.count || String(left.reason).localeCompare(String(right.reason)));
}

function computeExecutionStats(entries = []) {
  const withEntrySlippage = entries.filter((entry) => Number.isFinite(entry.entrySlippageBps));
  const withExitSlippage = entries.filter((entry) => Number.isFinite(entry.exitSlippageBps));
  const makerEligible = entries.filter((entry) => entry.entryLiquidityRole);
  const stopEntries = entries.filter((entry) => String(entry.exitReason || "") === "stop_loss");
  const partialEntries = entries.filter((entry) => (
    Number(entry.entryFillRatio || 0) < 0.999 || Number(entry.exitFillRatio || 0) < 0.999
  ));

  const averageAbs = (items, key) => {
    if (items.length === 0) return null;
    return items.reduce((sum, item) => sum + Math.abs(Number(item[key] || 0)), 0) / items.length;
  };

  return {
    makerShare: makerEligible.length > 0
      ? makerEligible.filter((entry) => entry.entryLiquidityRole === "maker").length / makerEligible.length
      : null,
    averageEntrySlippageBps: averageAbs(withEntrySlippage, "entrySlippageBps"),
    averageExitSlippageBps: averageAbs(withExitSlippage, "exitSlippageBps"),
    partialFillRate: entries.length > 0 ? partialEntries.length / entries.length : null,
    stopSlipRate: stopEntries.length > 0
      ? stopEntries.filter((entry) => String(entry.stopExecutionQuality || "") === "slipped").length / stopEntries.length
      : null,
  };
}

function buildProfitabilityPilotSummary(entries = [], options = {}) {
  const allEntries = Array.isArray(entries) ? entries.slice() : [];
  const ticketStore = options.ticketStore || readProfitabilityTicketStore();
  const now = options.now || nowIso();
  const eligibleEntries = allEntries.filter((entry) => (
    String(entry.setupId || "") === BTC_PROFITABILITY_SETUP_ID &&
    String(entry.symbol || "").toUpperCase() === BTC_PROFITABILITY_SYMBOL &&
    entry.pilotEligible === true
  ));
  const disqualifiedEntries = allEntries.filter((entry) => entry.pilotEligible === false);
  const tradeCount = eligibleEntries.length;
  const wins = eligibleEntries.filter((entry) => Number(entry.pnlR || 0) > 0).length;
  const losses = eligibleEntries.filter((entry) => Number(entry.pnlR || 0) < 0).length;
  const expectancyR = tradeCount > 0
    ? eligibleEntries.reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0) / tradeCount
    : null;
  const netPnlUsd = eligibleEntries.reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const profitFactor = computeProfitFactorFromEntries(eligibleEntries);
  const ruleAdherenceRate = tradeCount > 0
    ? eligibleEntries.reduce((sum, entry) => sum + Number(entry.ruleAdherenceScore || 0), 0) / tradeCount / 100
    : null;
  const maxDrawdownR = computeMaxDrawdownR(eligibleEntries);
  const grossPositivePnl = eligibleEntries
    .filter((entry) => Number(entry.pnlUsd || 0) > 0)
    .reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const dominantTradePnl = eligibleEntries.reduce((best, entry) => (
    Math.max(best, Number(entry.pnlUsd || 0))
  ), 0);
  const dominantTradeShare = grossPositivePnl > 0 ? dominantTradePnl / grossPositivePnl : null;
  const gates = [
    {
      id: "expectancy",
      label: "Net expectancy > 0",
      target: "> 0R",
      passed: expectancyR != null && expectancyR > 0,
      actual: expectancyR == null ? "-" : `${expectancyR.toFixed(2)}R`,
    },
    {
      id: "profit_factor",
      label: "Profit factor >= 1.20",
      target: ">= 1.20",
      passed: profitFactor != null && profitFactor >= 1.2,
      actual: profitFactor == null ? "-" : profitFactor.toFixed(2),
    },
    {
      id: "rule_adherence",
      label: "Rule adherence >= 90%",
      target: ">= 90%",
      passed: ruleAdherenceRate != null && ruleAdherenceRate >= 0.9,
      actual: ruleAdherenceRate == null ? "-" : `${(ruleAdherenceRate * 100).toFixed(1)}%`,
    },
    {
      id: "drawdown",
      label: "Max drawdown < 4R",
      target: "< 4R",
      passed: tradeCount > 0 && maxDrawdownR < 4,
      actual: tradeCount === 0 ? "-" : `${maxDrawdownR.toFixed(2)}R`,
    },
    {
      id: "outlier",
      label: "Top trade <= 20% of gross PnL",
      target: "<= 20%",
      passed: dominantTradeShare != null && dominantTradeShare <= 0.2,
      actual: dominantTradeShare == null ? "-" : `${(dominantTradeShare * 100).toFixed(1)}%`,
    },
  ];
  const allAdvanceGatesPassed = gates.every((gate) => gate.passed);
  const milestones = [
    {
      id: "review_30",
      label: "30-trade review checkpoint",
      targetTrades: PROFITABILITY_REVIEW_TARGET,
      completedTrades: tradeCount,
      remainingTrades: Math.max(0, PROFITABILITY_REVIEW_TARGET - tradeCount),
      reached: tradeCount >= PROFITABILITY_REVIEW_TARGET,
      status: tradeCount >= PROFITABILITY_REVIEW_TARGET ? "reached" : "pending",
      description: "Informational checkpoint only. BTC-only stays in force after review.",
    },
    {
      id: "advance_50",
      label: "50-trade advance gate",
      targetTrades: PROFITABILITY_ADVANCE_TARGET,
      completedTrades: tradeCount,
      remainingTrades: Math.max(0, PROFITABILITY_ADVANCE_TARGET - tradeCount),
      reached: tradeCount >= PROFITABILITY_ADVANCE_TARGET,
      status: tradeCount < PROFITABILITY_ADVANCE_TARGET
        ? "pending"
        : (allAdvanceGatesPassed ? "ready" : "hold"),
      description: "ETH stays locked until 50 eligible BTC trades and every acceptance gate passes.",
    },
  ];

  let phase = "sample_building";
  if (tradeCount >= PROFITABILITY_ADVANCE_TARGET) {
    phase = allAdvanceGatesPassed ? "advance_ready" : "hold_redesign";
  } else if (tradeCount >= PROFITABILITY_REVIEW_TARGET) {
    phase = "review_checkpoint";
  }

  return {
    profileId: PROFITABILITY_PROFILE_ID,
    phase,
    progress: {
      completedTrades: tradeCount,
      targetTrades: PROFITABILITY_ADVANCE_TARGET,
      remainingTrades: Math.max(0, PROFITABILITY_ADVANCE_TARGET - tradeCount),
    },
    reviewCheckpointTrades: PROFITABILITY_REVIEW_TARGET,
    advanceGateTrades: PROFITABILITY_ADVANCE_TARGET,
    todayGate: buildTodayGate(ticketStore, { now }),
    preTradeChecklist: buildProfitabilityChecklistSchema(),
    milestones,
    journalStats: {
      totalEntries: allEntries.length,
      phaseOneEntries: tradeCount,
      eligibleTradeCount: tradeCount,
      disqualifiedTradeCount: disqualifiedEntries.length,
      wins,
      losses,
      expectancyR,
      profitFactor,
      ruleAdherenceRate,
      netPnlUsd,
      maxDrawdownR,
      dominantTradeShare,
    },
    disqualificationReasons: buildDisqualificationBreakdown(disqualifiedEntries),
    executionStats: computeExecutionStats(eligibleEntries),
    breakdownByRegime: buildEntryBreakdown(eligibleEntries, "regime"),
    breakdownBySetup: buildEntryBreakdown(eligibleEntries, "setupId"),
    breakdownByMistakeTag: buildEntryBreakdown(eligibleEntries, "mistakeTag"),
    gates,
    nextUnlock: tradeCount >= PROFITABILITY_ADVANCE_TARGET && allAdvanceGatesPassed
      ? "ETH trend continuation can be reviewed for unlock."
      : tradeCount >= PROFITABILITY_ADVANCE_TARGET
        ? "Hold BTC-only. The 50-trade gate is complete but one or more acceptance checks still fail."
        : tradeCount >= PROFITABILITY_REVIEW_TARGET
          ? "Review the first 30 eligible BTC trades, then continue building toward the 50-trade advance gate."
          : "Keep BTC-only mean reversion live and keep building eligible sample size.",
  };
}

function buildOperatingPlan() {
  return {
    profileId: PROFITABILITY_PROFILE_ID,
    objective: "Prove a repeatable BTC-first edge net of fees and slippage before unlocking ETH or SOL.",
    activeSetupId: BTC_PROFITABILITY_SETUP_ID,
    activeSetupLabel: "BTC 5m Range Mean Reversion",
    defaultRegimeBias: "Range mean reversion or no-trade",
    marketStanceAsOf: "2026-04-02",
    session: {
      localTimeZone: LOCAL_SESSION_TIMEZONE,
      localWindow: "07:00-11:00 America/Denver",
      sessionTimeZone: SESSION_TIMEZONE,
      etWindow: "09:00-13:00 America/New_York",
      weekdaysOnly: true,
    },
    instruments: {
      liveNow: [BTC_PROFITABILITY_SYMBOL],
      nextPhase: [BTC_PROFITABILITY_SYMBOL, "ETHUSDT"],
      paperOnly: ["SOLUSDT"],
    },
    execution: {
      venues: ["Coinbase Advanced", "Kraken Pro"],
      orderStyle: "Direct order-book only. Prefer post-only or maker limits.",
      blocklist: ["Simple buy/sell", "Convert flows", "Thin alt books", "Weekend trading"],
    },
    risk: {
      riskPerTradeFraction: 0.0025,
      maxTotalOpenRiskFraction: 0.005,
      maxDailyLossFraction: 0.01,
      maxWeeklyLossFraction: 0.025,
      reduceSizeAtDrawdownFraction: 0.04,
      pauseAtDrawdownFraction: 0.06,
      maxCostToTargetFraction: 0.25,
    },
    dailyTradeCap: {
      limit: PROFITABILITY_DAILY_TRADE_CAP,
      countedBy: "Approved BTC entries per America/Denver trading day",
      unusedTicketExpiry: "11:00 America/Denver",
      timeZone: LOCAL_SESSION_TIMEZONE,
    },
    preTradeChecklist: buildProfitabilityChecklistSchema(),
    regimeChecklist: {
      range: [
        "BTC is still inside session or prior-session range and not back through the midpoint.",
        "No expansion or event-shock blocker is active.",
        "No fresh catalyst is pushing price away from VWAP.",
      ],
      trend: [
        "BTC breaks and holds above session structure with expanding range or volume.",
        "Only continuation setups are allowed; stop fading every move.",
        "ETH can mirror only after the BTC 50-trade gate passes.",
      ],
      event: [
        "Any exploit, macro shock, or abnormal expansion starts a 6-bar mean-reversion lockout.",
        "BTC and ETH only. SOL stays no-trade unless paper review explicitly unlocks it.",
      ],
    },
    journalTemplate: {
      path: PROFITABILITY_JOURNAL_PATH,
      fields: buildProfitabilityJournalSchema(),
    },
  };
}

function buildProfitabilitySystemGate({ strategy, marketData, ticketStore, now = nowIso() }) {
  const lastBar = marketData?.priceSeries?.[marketData.priceSeries.length - 1] || null;
  const sessionWindow = classifyScheduledWindow(now, DEFAULT_CRYPTO_DAY_TRADING_CONFIG);
  const barAgeMinutes = calculateBarAgeMinutes(lastBar?.timestamp, now);
  const dataFresh = barAgeMinutes != null && barAgeMinutes <= DEFAULT_CRYPTO_DAY_TRADING_CONFIG.maxBarAgeMinutes;
  const regimeBlockers = Array.isArray(lastBar?.indicators?.regimeBlockers) ? lastBar.indicators.regimeBlockers : [];
  const tradeable = lastBar?.indicators?.tradeable === true;
  const regimeState = String(lastBar?.indicators?.regimeState || "unknown");
  const todayGate = buildTodayGate(ticketStore, { now });
  const reasons = [];

  if (!sessionWindow.active) reasons.push("outside_fixed_session");
  if (marketData?.trusted === false) reasons.push("untrusted_market_data");
  if (!dataFresh) reasons.push("stale_market_data");
  if (!lastBar) reasons.push("missing_live_bar");
  if (!tradeable) {
    if (regimeBlockers.length > 0) {
      reasons.push(...regimeBlockers);
    } else {
      reasons.push("regime_not_tradeable");
    }
  }

  const costProfile = buildCostProfile(strategy, marketData?.marketSnapshot || {}, lastBar);
  if (!costProfile.allowed) reasons.push("cost_cap_blocked");
  if (todayGate.remainingApprovals <= 0) reasons.push("daily_trade_cap_reached");

  return {
    allowed: reasons.length === 0,
    reasons: [...new Set(reasons)],
    regimeState,
    tradeable,
    regimeBlockers,
    dataFresh,
    barAgeMinutes,
    lastBarTimestamp: lastBar?.timestamp || null,
    sessionWindow,
    todayGate,
    costProfile,
  };
}

async function requestProfitabilityPreflightTicket(options = {}) {
  const now = String(options.now || nowIso());
  const strategyId = String(options.strategyId || BTC_PROFITABILITY_SETUP_ID);
  const strategies = options.strategies || loadStrategies({ readOnly: true });
  const strategy = strategies.find((candidate) => candidate.strategyId === strategyId);
  if (!strategy) {
    throw new Error(`Unknown profitability strategy: ${strategyId}`);
  }

  const checklistFlags = resolveChecklistFlags(options);
  const checklistFailures = getChecklistFailures(checklistFlags);
  const ticketStore = readProfitabilityTicketStore();
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : (targetStrategy, loaderOptions) => loadCryptoMarketDataForStrategy(targetStrategy, {
      ...loaderOptions,
      includeLive: true,
      persistArtifacts: false,
    });
  const marketData = await marketDataLoader(strategy, {
    bars: options.bars || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars,
    persistArtifacts: false,
  });
  const systemGate = buildProfitabilitySystemGate({ strategy, marketData, ticketStore, now });
  const blockedReasons = [...new Set([...checklistFailures, ...systemGate.reasons])];
  if (blockedReasons.length > 0) {
    return {
      approved: false,
      blocked: true,
      reasons: blockedReasons,
      checklistFlags,
      systemGate,
      ticket: null,
      ticketStore,
    };
  }

  const local = getLocalParts(now);
  const ticket = {
    ticketId: `preflight_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    profileId: PROFITABILITY_PROFILE_ID,
    strategyId,
    symbol: String(strategy.marketUniverse?.symbols?.[0] || BTC_PROFITABILITY_SYMBOL).toUpperCase(),
    approvedAt: now,
    status: "approved",
    sessionLabel: "Denver Core",
    localTradeDate: local?.date || null,
    checklistFlags,
    systemGateSnapshot: {
      regimeState: systemGate.regimeState,
      tradeable: systemGate.tradeable,
      regimeBlockers: systemGate.regimeBlockers,
      costProfile: systemGate.costProfile,
      sessionWindow: systemGate.sessionWindow,
    },
  };

  const nextStore = {
    ...ticketStore,
    tickets: [...(ticketStore.tickets || []), ticket],
  };
  saveProfitabilityTicketStore(nextStore);
  return {
    approved: true,
    blocked: false,
    reasons: [],
    checklistFlags,
    systemGate: {
      ...systemGate,
      todayGate: buildTodayGate(nextStore, { now }),
    },
    ticket,
    ticketStore: nextStore,
  };
}

function isArtifactCompatible(payload) {
  return payload && payload.profitabilityProfileId === PROFITABILITY_PROFILE_ID;
}

function buildCryptoManagedStrategy(options = {}) {
  const symbol = String(options.symbol || "BTCUSDT").toUpperCase();
  const baseAsset = symbol.replace(/USDT$/i, "").toLowerCase();
  const strategyKind = String(options.strategyKind || "range_mean_reversion");
  const breakoutVariant = String(options.breakoutVariant || "breakout_close");
  const openingRangeBars = Math.max(1, Math.round(Number(options.openingRangeBars || (
    breakoutVariant === "breakout_retest" ? 6 : 3
  ))));
  const openingRangeMinutes = openingRangeBars * 5;
  const liveStatus = String(options.status || "draft");
  const unlockPhase = String(options.unlockPhase || "phase_1");
  const maxPositionFraction = Number(options.maxPositionFraction || (
    symbol === "BTCUSDT" ? 0.35 : symbol === "ETHUSDT" ? 0.28 : 0.18
  ));
  const minLiquidityUsd = symbol === "BTCUSDT"
    ? 6000000
    : symbol === "ETHUSDT"
      ? 4500000
      : 2500000;
  const assumedSlippageFraction = symbol === "SOLUSDT" ? 0.0007 : 0.0004;
  const common = {
    version: 2,
    venueType: "crypto",
    status: liveStatus,
    marketUniverse: {
      symbols: [symbol],
      category: "crypto-spot",
      maxMarkets: 1,
    },
    sizing: {
      model: "fixed_fractional",
      riskSizing: "stop_based",
      maxPositionFraction,
      riskPerTradeFraction: 0.0025,
    },
    evaluationWindow: {
      timeframe: DEFAULT_TIMEFRAME,
      warmupBars: 30,
      minimumTrades: 30,
    },
    metadata: {
      owner: MANAGED_STRATEGY_OWNER,
      profitabilityProfileId: PROFITABILITY_PROFILE_ID,
      unlockPhase,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
      marketType: DEFAULT_MARKET_TYPE,
      sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      sessionTimeZone: SESSION_TIMEZONE,
      localSessionTimeZone: LOCAL_SESSION_TIMEZONE,
      executionVenuePrimary: "coinbase_advanced",
      executionVenueBackup: "kraken_pro",
      executionMode: "direct_order_book_only",
      alertWindowIds: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows.map((window) => window.id),
      tags: ["crypto", "spot", baseAsset],
    },
  };

  if (strategyKind === "trend_continuation") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-trend-continuation`,
      name: `${symbol} 5m Trend Continuation`,
      hypothesisSummary:
        `${symbol} should only be promoted after the BTC range pilot proves profitable. On true trend days, continuation after a break-and-hold above session structure should outperform fading every push.`,
      signalInputs: [{ name: "crypto_trend_continuation", type: "technical", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Enter long only after ${symbol} breaks and holds above session structure, then confirms continuation on a controlled retest.`,
        "Require trend alignment, expanding range or volume, and no weekend or event lockout.",
      ],
      exitRules: [
        "Exit on breakout failure or a 0.95% continuation target.",
        "Exit on a 0.50% stop loss.",
        "Exit after 12 bars if follow-through stalls.",
      ],
      cooldownRules: ["Wait 4 bars after a continuation exit before another entry."],
      riskLimits: {
        maxDrawdownFraction: 0.06,
        reduceSizeAtDrawdownFraction: 0.04,
        reduceSizeMultiplier: 0.5,
        maxDailyLossFraction: 0.01,
        maxWeeklyLossFraction: 0.025,
        maxDailyLosingTrades: 3,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: 0.005,
        minLiquidityUsd,
        maxSpreadFraction: symbol === "BTCUSDT" ? 0.0012 : 0.0015,
        maxCostToTargetFraction: 0.25,
        assumedRoundTripFeeFraction: 0.001,
        assumedSlippageFraction,
      },
      simulation: {
        direction: "long",
        entrySignal: "crypto_trend_continuation",
        entryExecution: "next_open",
        takeProfitFraction: 0.013,
        stopLossFraction: 0.005,
        maxHoldBars: 8,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: symbol === "BTCUSDT" ? 0.55 : 0.58,
      },
      metadata: {
        ...common.metadata,
        tags: [...common.metadata.tags, "trend", "continuation"],
      },
    };
  }

  if (strategyKind === "event_watch") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-event-watch`,
      name: `${symbol} 5m Event Watch`,
      hypothesisSummary:
        `${symbol} stays paper-only until BTC and ETH survive a weak/choppy stretch. This strategy exists to track event-driven dislocations without turning SOL into the core live product.`,
      signalInputs: [{ name: "crypto_event_watch", type: "technical", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Stand aside by default. Only evaluate ${symbol} when there is a specific chain or market catalyst and the event playbook has been reviewed.`,
        "Do not promote this setup while BTC phase 1 or ETH phase 2 is still incomplete.",
      ],
      exitRules: ["Paper-only tracking until explicitly unlocked."],
      cooldownRules: ["No live re-entry while event risk remains active."],
      riskLimits: {
        maxDrawdownFraction: 0.06,
        reduceSizeAtDrawdownFraction: 0.04,
        reduceSizeMultiplier: 0.5,
        maxDailyLossFraction: 0.01,
        maxWeeklyLossFraction: 0.025,
        maxDailyLosingTrades: 3,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: 0.005,
        minLiquidityUsd,
        maxSpreadFraction: 0.0025,
        maxCostToTargetFraction: 0.25,
        assumedRoundTripFeeFraction: 0.001,
        assumedSlippageFraction: 0.0008,
      },
      simulation: {
        direction: "long",
        entrySignal: "crypto_event_watch",
        entryExecution: "next_open",
        takeProfitFraction: 0.01,
        stopLossFraction: 0.0055,
        maxHoldBars: 8,
        cooldownBars: 8,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.8,
      },
      metadata: {
        ...common.metadata,
        tags: [...common.metadata.tags, "event", "paper-only"],
      },
    };
  }

  if (strategyKind === "bottom_reclaim") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-bottom-reclaim`,
      name: `${symbol} 5m Bottom Reclaim`,
      hypothesisSummary:
        `${symbol} should occasionally offer cleaner reversal entries than the base range pilot when a sweep of session lows tags the lower Bollinger band, momentum refuses to confirm the new low, and a fast oversold reset turns back up on rising volume.`,
      signalInputs: [{ name: "crypto_bottom_reclaim", type: "technical", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Enter long only after ${symbol} sweeps session or prior-session lows, touches the lower Bollinger band, and prints a bullish RSI divergence.`,
        "Require a Stoch RSI cross up from oversold, a three-bar volume ramp into the reclaim, a rejection candle, and no event-shock lockout.",
      ],
      exitRules: [
        "Exit at session VWAP or range midpoint, whichever is hit first.",
        "Exit on a 0.42% stop loss.",
        "Exit after 6 bars if the reclaim stalls.",
      ],
      cooldownRules: ["Wait 5 bars after a bottom-reclaim exit before another entry."],
      riskLimits: {
        maxDrawdownFraction: 0.06,
        reduceSizeAtDrawdownFraction: 0.04,
        reduceSizeMultiplier: 0.5,
        maxDailyLossFraction: 0.01,
        maxWeeklyLossFraction: 0.025,
        maxDailyLosingTrades: 3,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: 0.0042,
        minLiquidityUsd,
        maxSpreadFraction: symbol === "BTCUSDT" ? 0.0012 : 0.0015,
        maxCostToTargetFraction: 0.25,
        assumedRoundTripFeeFraction: 0.001,
        assumedSlippageFraction,
      },
      simulation: {
        direction: "long",
        entrySignal: "crypto_bottom_reclaim",
        entryExecution: "next_open",
        takeProfitFraction: 0.007,
        stopLossFraction: 0.0042,
        maxHoldBars: 5,
        cooldownBars: 5,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: symbol === "BTCUSDT" ? 0.56 : 0.60,
        exitTargetMode: "session_vwap_or_range_midpoint",
      },
      metadata: {
        ...common.metadata,
        tags: [...common.metadata.tags, "bottom", "reversal", "bollinger", "stoch-rsi", "research-phase-1"],
      },
    };
  }

  if (strategyKind === "failed_breakdown_reclaim") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-failed-breakdown-reclaim`,
      name: `${symbol} 5m Failed Breakdown Reclaim`,
      hypothesisSummary:
        `${symbol} should occasionally reverse more cleanly after a true stop-run than after a soft sweep. We want a tighter state machine than bottom reclaim: break support, close back above it immediately, then hold the reclaim on the next bar while the move is still near session structure.`,
      signalInputs: [{ name: "crypto_failed_breakdown_reclaim", type: "technical", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Enter long only after ${symbol} breaks below session, prior-session, or prior swing support, then closes back above that broken level and holds the reclaim on the next bar.`,
        "Require the move to stay near support, confirm on usable volume, and avoid the event-shock lockout.",
      ],
      exitRules: [
        "Exit at session VWAP or range midpoint, whichever is hit first.",
        "Exit on a 0.46% stop loss.",
        "Exit after 6 bars if the reclaim loses follow-through.",
      ],
      cooldownRules: ["Wait 6 bars after a failed-breakdown-reclaim exit before another entry."],
      riskLimits: {
        maxDrawdownFraction: 0.06,
        reduceSizeAtDrawdownFraction: 0.04,
        reduceSizeMultiplier: 0.5,
        maxDailyLossFraction: 0.01,
        maxWeeklyLossFraction: 0.025,
        maxDailyLosingTrades: 3,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: 0.0046,
        minLiquidityUsd,
        maxSpreadFraction: symbol === "BTCUSDT" ? 0.0012 : 0.0015,
        maxCostToTargetFraction: 0.25,
        assumedRoundTripFeeFraction: 0.001,
        assumedSlippageFraction,
      },
      simulation: {
        direction: "long",
        entrySignal: "crypto_failed_breakdown_reclaim",
        entryExecution: "next_open",
        takeProfitFraction: 0.007,
        stopLossFraction: 0.0046,
        maxHoldBars: 5,
        cooldownBars: 6,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: symbol === "BTCUSDT" ? 0.54 : 0.58,
        exitTargetMode: "session_vwap_or_range_midpoint",
      },
      metadata: {
        ...common.metadata,
        tags: [...common.metadata.tags, "failed-breakdown", "reclaim", "reversal", "research-phase-1"],
      },
    };
  }

  if (strategyKind === "opening_range_breakout") {
    const variantToken = breakoutVariant === "breakout_retest" ? "retest" : "close";
    const variantLabel = breakoutVariant === "breakout_retest" ? "Retest" : "Close";
    const takeProfitFraction = breakoutVariant === "breakout_retest" ? 0.011 : 0.011;
    const stopLossFraction = breakoutVariant === "breakout_retest" ? 0.004 : 0.004;
    const maxHoldBars = breakoutVariant === "breakout_retest" ? 8 : 6;
    const signalThreshold = breakoutVariant === "breakout_retest" ? 0.76 : 0.74;
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-opening-range-breakout-${variantToken}`,
      name: `${symbol} 5m Opening Range Breakout ${openingRangeMinutes}m ${variantLabel}`,
      hypothesisSummary:
        `${symbol} should sometimes trend cleanly out of the Denver Core open after price defines a tight early range, clears the range high, and either keeps going immediately or confirms the move with a controlled retest.`,
      signalInputs: [{ name: "crypto_opening_range_breakout", type: "technical", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Enter long only after ${symbol} finishes the first ${openingRangeMinutes} minutes of the Denver Core session and confirms a breakout above the opening-range high.`,
        breakoutVariant === "breakout_retest"
          ? "Require the first break to hold and reclaim the opening-range high on a retest with trend and VWAP still aligned."
          : "Require a decisive close above the opening-range high with trend and VWAP aligned.",
      ],
      exitRules: [
        "Exit on failed breakout back through the opening range.",
        `Exit on a ${(takeProfitFraction * 100).toFixed(2)}% take-profit target.`,
        `Exit on a ${(stopLossFraction * 100).toFixed(2)}% stop loss or after ${maxHoldBars} bars if the move stalls.`,
      ],
      cooldownRules: ["Wait 4 bars after an opening-range-breakout exit before another entry."],
      riskLimits: {
        maxDrawdownFraction: 0.06,
        reduceSizeAtDrawdownFraction: 0.04,
        reduceSizeMultiplier: 0.5,
        maxDailyLossFraction: 0.01,
        maxWeeklyLossFraction: 0.025,
        maxDailyLosingTrades: 3,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: stopLossFraction,
        minLiquidityUsd,
        maxSpreadFraction: symbol === "BTCUSDT" ? 0.0012 : 0.0015,
        maxCostToTargetFraction: 0.25,
        assumedRoundTripFeeFraction: 0.001,
        assumedSlippageFraction,
      },
      simulation: {
        direction: "long",
        entrySignal: "crypto_opening_range_breakout",
        entryExecution: "next_open",
        takeProfitFraction,
        stopLossFraction,
        maxHoldBars,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: signalThreshold,
      },
      metadata: {
        ...common.metadata,
        openingRangeBars,
        openingRangeMinutes,
        openingRangeVariant: breakoutVariant,
        tags: [...common.metadata.tags, "opening-range", "breakout", variantToken, "research-phase-1"],
      },
    };
  }

  if (strategyKind === "delta_divergence") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-delta-divergence`,
      name: `${symbol} 5m Delta Divergence`,
      hypothesisSummary: `${symbol} order flow divergences: when price makes a new session extreme but volume delta disagrees, the move is likely to reverse.`,
      signalInputs: [{ name: "crypto_delta_divergence", type: "order_flow", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Long: ${symbol} near session low but CVD rising and buy pressure > 55%.`,
        `Short: ${symbol} near session high but CVD falling and sell pressure > 55%.`,
      ],
      exitRules: ["Exit on take profit, stop loss, or max hold bars."],
      cooldownRules: ["Wait 3 bars after exit."],
      riskLimits: { ...common.riskLimits || {}, maxDrawdownFraction: 0.06, maxDailyLossFraction: 0.01, maxOpenPositions: 1, maxLossPerTradeFraction: 0.0035, minLiquidityUsd },
      simulation: {
        direction: "both",
        entrySignal: "crypto_delta_divergence",
        entryExecution: "next_open",
        takeProfitFraction: 0.006,
        stopLossFraction: 0.0035,
        maxHoldBars: 5,
        cooldownBars: 3,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.50,
      },
      metadata: { ...common.metadata, tags: [...common.metadata.tags, "delta", "divergence", "order-flow"] },
    };
  }

  if (strategyKind === "delta_breakout") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-delta-breakout`,
      name: `${symbol} 5m Delta Breakout`,
      hypothesisSummary: `${symbol} breakouts confirmed by volume delta surge -- real demand/supply, not just price noise.`,
      signalInputs: [{ name: "crypto_delta_breakout", type: "order_flow", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Long: ${symbol} breaks session high with surging CVD and expanding volume.`,
        `Short: ${symbol} breaks session low with plunging CVD and expanding volume.`,
      ],
      exitRules: ["Exit on take profit, stop loss, or max hold bars."],
      cooldownRules: ["Wait 4 bars after exit."],
      riskLimits: { ...common.riskLimits || {}, maxDrawdownFraction: 0.06, maxDailyLossFraction: 0.01, maxOpenPositions: 1, maxLossPerTradeFraction: 0.004, minLiquidityUsd },
      simulation: {
        direction: "both",
        entrySignal: "crypto_delta_breakout",
        entryExecution: "next_open",
        takeProfitFraction: 0.009,
        stopLossFraction: 0.004,
        maxHoldBars: 6,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.52,
      },
      metadata: { ...common.metadata, tags: [...common.metadata.tags, "delta", "breakout", "order-flow"] },
    };
  }

  if (strategyKind === "absorption") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-absorption`,
      name: `${symbol} 5m Absorption`,
      hypothesisSummary: `${symbol} absorption: huge volume but price barely moves indicates large orders absorbing directional flow. Fade the trapped side.`,
      signalInputs: [{ name: "crypto_absorption", type: "order_flow", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Long: ${symbol} high volume at session low with tiny price move and buy-side pressure.`,
        `Short: ${symbol} high volume at session high with tiny price move and sell-side pressure.`,
      ],
      exitRules: ["Exit on take profit, stop loss, or max hold bars."],
      cooldownRules: ["Wait 2 bars after exit."],
      riskLimits: { ...common.riskLimits || {}, maxDrawdownFraction: 0.06, maxDailyLossFraction: 0.01, maxOpenPositions: 1, maxLossPerTradeFraction: 0.003, minLiquidityUsd },
      simulation: {
        direction: "both",
        entrySignal: "crypto_absorption",
        entryExecution: "next_open",
        takeProfitFraction: 0.005,
        stopLossFraction: 0.003,
        maxHoldBars: 4,
        cooldownBars: 2,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.48,
      },
      metadata: { ...common.metadata, tags: [...common.metadata.tags, "absorption", "order-flow"] },
    };
  }

  if (strategyKind === "exhaustion") {
    return {
      ...common,
      strategyId: `${symbol.toLowerCase()}-crypto-exhaustion`,
      name: `${symbol} 5m Exhaustion`,
      hypothesisSummary: `${symbol} exhaustion: volume spike with immediate reversal candle after a directional move traps late entries. Fade the exhausted side.`,
      signalInputs: [{ name: "crypto_exhaustion", type: "order_flow", source: "computed_signal", weight: 1 }],
      entryRules: [
        `Long: ${symbol} volume spike after downmove with bullish reversal candle and buyer takeover.`,
        `Short: ${symbol} volume spike after upmove with bearish reversal candle and seller takeover.`,
      ],
      exitRules: ["Exit on take profit, stop loss, or max hold bars."],
      cooldownRules: ["Wait 3 bars after exit."],
      riskLimits: { ...common.riskLimits || {}, maxDrawdownFraction: 0.06, maxDailyLossFraction: 0.01, maxOpenPositions: 1, maxLossPerTradeFraction: 0.0035, minLiquidityUsd },
      simulation: {
        direction: "both",
        entrySignal: "crypto_exhaustion",
        entryExecution: "next_open",
        takeProfitFraction: 0.006,
        stopLossFraction: 0.0035,
        maxHoldBars: 4,
        cooldownBars: 3,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.50,
      },
      metadata: { ...common.metadata, tags: [...common.metadata.tags, "exhaustion", "reversal", "order-flow"] },
    };
  }

  return {
    ...common,
    strategyId: `${symbol.toLowerCase()}-crypto-range-mean-reversion`,
    name: `${symbol} 5m Range Mean Reversion`,
    hypothesisSummary:
      `${symbol} is the anchor for the profitability pilot. In defensive, low-conviction tape we want selective long-only fades from session or prior-session lows back toward VWAP or the range midpoint, not broad breakout chasing.`,
    signalInputs: [{ name: "crypto_range_mean_reversion", type: "technical", source: "computed_signal", weight: 1 }],
    entryRules: [
      `Enter long only near ${symbol} session or prior-session lows while price is still inside range and not expanding away from VWAP.`,
      "Require a rejection candle, contained volume expansion, and no catalyst/event lockout.",
    ],
    exitRules: [
      "Exit at session VWAP or range midpoint, whichever is hit first.",
      "Exit on a 0.45% stop loss.",
      "Exit after 8 bars if the bounce does not materialize.",
    ],
    cooldownRules: ["Wait 4 bars after a range-mean-reversion exit before another entry."],
    riskLimits: {
      maxDrawdownFraction: 0.06,
      reduceSizeAtDrawdownFraction: 0.04,
      reduceSizeMultiplier: 0.5,
      maxDailyLossFraction: 0.01,
      maxWeeklyLossFraction: 0.025,
      maxDailyLosingTrades: 3,
      maxOpenPositions: 1,
      maxLossPerTradeFraction: 0.0045,
      minLiquidityUsd,
      maxSpreadFraction: symbol === "BTCUSDT" ? 0.0012 : 0.0015,
      maxCostToTargetFraction: 0.25,
      assumedRoundTripFeeFraction: 0.001,
      assumedSlippageFraction,
    },
    simulation: {
      direction: "long",
      entrySignal: "crypto_range_mean_reversion",
      entryExecution: "next_open",
      takeProfitFraction: 0.006,
      stopLossFraction: 0.0035,
      maxHoldBars: 6,
      cooldownBars: 4,
      maxConcurrentPositions: 1,
      useSignalStrengthThreshold: 0.52,
      exitTargetMode: "session_vwap_or_range_midpoint",
    },
    metadata: {
      ...common.metadata,
      tags: [...common.metadata.tags, "range", "mean-reversion", "pilot-phase-1"],
    },
  };
}

const DEFAULT_STRATEGIES = [
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "bottom_reclaim",
    status: "paper_candidate",
    unlockPhase: "phase_1_research",
    maxPositionFraction: 0.2,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "failed_breakdown_reclaim",
    status: "paper_candidate",
    unlockPhase: "phase_1_research",
    maxPositionFraction: 0.2,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "range_mean_reversion",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.35,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "opening_range_breakout",
    breakoutVariant: "breakout_close",
    openingRangeBars: 3,
    status: "paper_candidate",
    unlockPhase: "phase_1_research",
    maxPositionFraction: 0.18,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "opening_range_breakout",
    breakoutVariant: "breakout_retest",
    openingRangeBars: 6,
    status: "paper_candidate",
    unlockPhase: "phase_1_research",
    maxPositionFraction: 0.18,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "trend_continuation",
    status: "disabled",
    unlockPhase: "phase_2",
    maxPositionFraction: 0.35,
  }),
  buildCryptoManagedStrategy({
    symbol: "ETHUSDT",
    strategyKind: "trend_continuation",
    status: "disabled",
    unlockPhase: "phase_2",
    maxPositionFraction: 0.28,
  }),
  buildCryptoManagedStrategy({
    symbol: "SOLUSDT",
    strategyKind: "event_watch",
    status: "disabled",
    unlockPhase: "phase_3",
    maxPositionFraction: 0.18,
  }),
  // Order flow strategies
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "delta_divergence",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.25,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "delta_breakout",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.25,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "absorption",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.25,
  }),
  buildCryptoManagedStrategy({
    symbol: "BTCUSDT",
    strategyKind: "exhaustion",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.25,
  }),
];

function assertValidStrategySpec(strategy) {
  if (!strategy || typeof strategy !== "object") throw new Error("Strategy spec must be an object");
  if (!strategy.strategyId || typeof strategy.strategyId !== "string") {
    throw new Error("Strategy spec requires strategyId");
  }
  if (!strategy.name || typeof strategy.name !== "string") {
    throw new Error(`Strategy ${strategy.strategyId} requires a name`);
  }
  if (!VALID_STATUSES.has(String(strategy.status || "draft"))) {
    throw new Error(`Strategy ${strategy.strategyId} has an invalid status`);
  }
  if (!Array.isArray(strategy.marketUniverse?.symbols) || strategy.marketUniverse.symbols.length === 0) {
    throw new Error(`Strategy ${strategy.strategyId} requires at least one symbol`);
  }
  if (!strategy.evaluationWindow?.timeframe || !strategy.simulation?.entrySignal) {
    throw new Error(`Strategy ${strategy.strategyId} is missing evaluation settings`);
  }
  return strategy;
}

function synchronizeManagedStrategies(strategies) {
  const storedStrategies = Array.isArray(strategies) ? strategies.slice() : [];
  const storedById = new Map(storedStrategies.map((strategy) => [strategy.strategyId, strategy]));
  const merged = [];
  const seen = new Set();
  let changed = false;

  for (const defaultStrategy of DEFAULT_STRATEGIES) {
    const stored = storedById.get(defaultStrategy.strategyId);
    if (!stored) {
      merged.push(clone(defaultStrategy));
      seen.add(defaultStrategy.strategyId);
      changed = true;
      continue;
    }
    const isManaged = String(stored.metadata?.owner || "") === MANAGED_STRATEGY_OWNER;
    const storedVersion = Number(stored.version || 0);
    if (isManaged && storedVersion < defaultStrategy.version) {
      merged.push(clone(defaultStrategy));
      changed = true;
    } else {
      merged.push(stored);
    }
    seen.add(defaultStrategy.strategyId);
  }

  for (const strategy of storedStrategies) {
    if (seen.has(strategy.strategyId)) continue;
    const isManaged = String(strategy.metadata?.owner || "") === MANAGED_STRATEGY_OWNER;
    if (isManaged) {
      changed = true;
      continue;
    }
    merged.push(strategy);
  }

  return {
    strategies: merged.map(assertValidStrategySpec),
    changed,
  };
}

function loadStrategies(options = {}) {
  const readOnly = Boolean(options.readOnly);
  const stored = readJson(STRATEGIES_PATH, null);
  if (!Array.isArray(stored) || stored.length === 0) {
    const seeded = clone(DEFAULT_STRATEGIES);
    if (!readOnly) {
      atomicWriteJsonSync(STRATEGIES_PATH, seeded);
    }
    return seeded;
  }
  const synchronized = synchronizeManagedStrategies(stored);
  if (synchronized.changed && !readOnly) {
    atomicWriteJsonSync(STRATEGIES_PATH, synchronized.strategies);
  }
  return synchronized.strategies;
}

function saveStrategies(strategies) {
  atomicWriteJsonSync(STRATEGIES_PATH, strategies.map(assertValidStrategySpec));
}

function saveStrategiesIfChanged(currentStrategies, nextStrategies) {
  const normalizedCurrent = currentStrategies.map(assertValidStrategySpec);
  const normalizedNext = nextStrategies.map(assertValidStrategySpec);
  if (JSON.stringify(normalizedCurrent) === JSON.stringify(normalizedNext)) {
    return false;
  }
  atomicWriteJsonSync(STRATEGIES_PATH, normalizedNext);
  return true;
}

function getNormalizedBarsPath(symbol) {
  return path.join(NORMALIZED_1M_DIR, `${String(symbol || "").toUpperCase()}.json`);
}

function getDerivedBarsPath(symbol, timeframe = DEFAULT_TIMEFRAME, windowMode = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode) {
  const normalizedWindowMode = normalizeWindowMode(windowMode);
  const suffix = normalizedWindowMode === DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode ? "" : `-${normalizedWindowMode}`;
  return path.join(DERIVED_5M_DIR, `${String(symbol || "").toUpperCase()}-${timeframe}${suffix}.json`);
}

function getBacktestPath(strategyId) {
  return path.join(BACKTEST_DIR, `${strategyId}.json`);
}

function saveBacktestResult(result) {
  ensureDir(BACKTEST_DIR);
  const filePath = getBacktestPath(result.strategyId);
  atomicWriteJsonSync(filePath, { ...result, savedAt: nowIso() });
  return { filePath, result: readJson(filePath, result) };
}

function getBacktestResult(strategyId) {
  return strategyId ? readJson(getBacktestPath(strategyId), null) : null;
}

function loadBacktestSummaries() {
  if (!fs.existsSync(BACKTEST_DIR)) return [];
  return fs.readdirSync(BACKTEST_DIR)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => readJson(path.join(BACKTEST_DIR, name), null))
    .map((raw) => raw?.summary ? raw : { strategyId: raw?.strategyId, summary: raw })
    .filter((result) => result?.strategyId && result?.summary);
}

function loadNormalizedBars(symbol) {
  const filePath = getNormalizedBarsPath(symbol);
  const cacheKey = `${filePath}::${_mtimeMs(filePath)}`;
  const cached = NORMALIZED_BARS_CACHE.get(cacheKey);
  if (cached) {
    return cached.slice();
  }
  const payload = readJson(filePath, null);
  const bars = Array.isArray(payload?.bars) ? payload.bars : [];
  NORMALIZED_BARS_CACHE.set(cacheKey, bars.slice());
  return bars;
}

function _invalidateNormalizedBarsCache(symbol) {
  const filePath = getNormalizedBarsPath(symbol);
  for (const key of Array.from(NORMALIZED_BARS_CACHE.keys())) {
    if (key.startsWith(`${filePath}::`)) {
      NORMALIZED_BARS_CACHE.delete(key);
    }
  }
}

function _mtimeMs(filePath) {
  try {
    return fs.statSync(filePath).mtimeMs;
  } catch {
    return 0;
  }
}

function _directorySignature(dirPath) {
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    let latest = _mtimeMs(dirPath);
    for (const entry of entries) {
      const entryPath = path.join(dirPath, entry.name);
      latest = Math.max(
        latest,
        entry.isDirectory() ? _directorySignature(entryPath) : _mtimeMs(entryPath),
      );
    }
    return latest;
  } catch {
    return 0;
  }
}

function _readOnlyBundleKey(options = {}) {
  const bars = Number(options.bars) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars;
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  return [
    "crypto",
    bars,
    accountId,
    _mtimeMs(STRATEGIES_PATH),
    _mtimeMs(LEDGER_PATH),
    _mtimeMs(REPORT_PATH),
    _mtimeMs(WATCHLIST_PATH),
    _mtimeMs(IMPORT_REPORT_PATH),
    _mtimeMs(EXPERIMENT_REPORT_PATH),
    _mtimeMs(PROFITABILITY_JOURNAL_PATH),
    _mtimeMs(PROFITABILITY_TICKETS_PATH),
    _directorySignature(BACKTEST_DIR),
    _directorySignature(EXPERIMENTS_DIR),
    _directorySignature(NORMALIZED_1M_DIR),
    _directorySignature(DERIVED_5M_DIR),
  ].join("::");
}

function _readOnlyDayTradingBundle(options = {}) {
  const cacheKey = _readOnlyBundleKey(options);
  const cached = READ_ONLY_BUNDLE_CACHE.get(cacheKey);
  if (cached) {
    return cached;
  }
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const broker = new shared.PaperBroker({ ledgerPath: LEDGER_PATH, readOnly: true });
  const profitabilityJournal = readProfitabilityJournal();
  const profitabilityTicketStore = readProfitabilityTicketStore();
  const bundle = {
    accountId,
    strategies: loadStrategies({ readOnly: true }),
    backtests: loadBacktestSummaries(),
    broker,
    paperSummaries: broker.getStrategySummaries({ accountId }),
    paperAccount: broker.getAccountSummary({ accountId }),
    lastReport: readJson(REPORT_PATH, null),
    lastWatchlist: readJson(WATCHLIST_PATH, null),
    lastImport: readJson(IMPORT_REPORT_PATH, null),
    experimentReport: readJson(EXPERIMENT_REPORT_PATH, null),
    profitabilityJournal,
    profitabilityTicketStore,
    pilotSummary: buildProfitabilityPilotSummary(profitabilityJournal.entries, {
      ticketStore: profitabilityTicketStore,
    }),
    operatingPlan: buildOperatingPlan(),
  };
  READ_ONLY_BUNDLE_CACHE.set(cacheKey, bundle);
  return bundle;
}

function saveNormalizedBars(symbol, bars, metadata = {}) {
  atomicWriteJsonSync(getNormalizedBarsPath(symbol), {
    savedAt: nowIso(),
    symbol,
    interval: DEFAULT_INTERVAL,
    metadata,
    bars,
  });
  _invalidateNormalizedBarsCache(symbol);
}

function saveDerivedBars(symbol, timeframe, bars, windowMode = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode) {
  atomicWriteJsonSync(getDerivedBarsPath(symbol, timeframe, windowMode), {
    savedAt: nowIso(),
    symbol,
    timeframe,
    windowMode: normalizeWindowMode(windowMode),
    bars,
  });
}

function httpJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "options-chatbot/crypto-daytrading" } }, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    }).on("error", reject);
  });
}

function normalizeBars(bars = []) {
  return bars
    .map((bar, index) => {
      const timestamp = new Date(bar.timestamp).toISOString();
      const symbol = String(bar.symbol || "").toUpperCase();
      const open = Number(bar.open);
      const high = Number(bar.high);
      const low = Number(bar.low);
      const close = Number(bar.close);
      const volume = Number(bar.volume || 0);
      if (!timestamp || Number.isNaN(new Date(timestamp).getTime())) {
        throw new Error(`bars[${index}] is missing a valid timestamp`);
      }
      if (!symbol) throw new Error(`bars[${index}] is missing symbol`);
      if (![open, high, low, close].every((value) => Number.isFinite(value) && value > 0)) {
        throw new Error(`bars[${index}] must contain positive OHLC values`);
      }
      return {
        ...bar,
        timestamp,
        symbol,
        open,
        high,
        low,
        close,
        volume: Number.isFinite(volume) ? volume : 0,
      };
    })
    .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
}

function mergeBars(existingBars = [], incomingBars = []) {
  const merged = new Map();
  for (const bar of [...existingBars, ...incomingBars]) {
    if (!bar?.timestamp) continue;
    merged.set(bar.timestamp, bar);
  }
  return [...merged.values()].sort((left, right) => (
    new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime()
  ));
}

function floorTimeMs(timeMs, bucketMinutes) {
  const bucketMs = bucketMinutes * 60 * 1000;
  return Math.floor(timeMs / bucketMs) * bucketMs;
}

function resampleBars(bars = [], bucketMinutes = 5) {
  const normalized = normalizeBars(bars);
  const grouped = new Map();

  for (const bar of normalized) {
    const bucketMs = floorTimeMs(new Date(bar.timestamp).getTime(), bucketMinutes);
    const key = `${bar.symbol}::${bucketMs}`;
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        timestamp: new Date(bucketMs).toISOString(),
        symbol: bar.symbol,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: Number(bar.volume || 0),
        quoteVolume: Number(bar.quoteVolume || 0),
        tradeCount: Number(bar.tradeCount || 0),
        takerBuyBaseVolume: Number(bar.takerBuyBaseVolume || 0),
        takerBuyQuoteVolume: Number(bar.takerBuyQuoteVolume || 0),
      });
      continue;
    }
    existing.high = Math.max(existing.high, bar.high);
    existing.low = Math.min(existing.low, bar.low);
    existing.close = bar.close;
    existing.volume += Number(bar.volume || 0);
    existing.quoteVolume += Number(bar.quoteVolume || 0);
    existing.tradeCount += Number(bar.tradeCount || 0);
    existing.takerBuyBaseVolume += Number(bar.takerBuyBaseVolume || 0);
    existing.takerBuyQuoteVolume += Number(bar.takerBuyQuoteVolume || 0);
  }

  return [...grouped.values()].sort((left, right) => (
    new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime()
  ));
}

function resampleOneMinuteBarsToFiveMinutes(bars = []) {
  const normalized = normalizeBars(bars);
  const grouped = new Map();

  for (const bar of normalized) {
    const bucketMs = floorTimeMs(new Date(bar.timestamp).getTime(), 5);
    const key = `${bar.symbol}::${bucketMs}`;
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, {
        timestamp: new Date(bucketMs).toISOString(),
        symbol: bar.symbol,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: Number(bar.volume || 0),
        quoteVolume: Number(bar.quoteVolume || 0),
        tradeCount: Number(bar.tradeCount || 0),
        takerBuyBaseVolume: Number(bar.takerBuyBaseVolume || 0),
        takerBuyQuoteVolume: Number(bar.takerBuyQuoteVolume || 0),
      });
      continue;
    }
    existing.high = Math.max(existing.high, bar.high);
    existing.low = Math.min(existing.low, bar.low);
    existing.close = bar.close;
    existing.volume += Number(bar.volume || 0);
    existing.quoteVolume += Number(bar.quoteVolume || 0);
    existing.tradeCount += Number(bar.tradeCount || 0);
    existing.takerBuyBaseVolume += Number(bar.takerBuyBaseVolume || 0);
    existing.takerBuyQuoteVolume += Number(bar.takerBuyQuoteVolume || 0);
  }

  return [...grouped.values()].sort((left, right) => (
    new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime()
  ));
}

function sma(values, period, index) {
  if (index + 1 < period) return null;
  let sum = 0;
  for (let i = index - period + 1; i <= index; i += 1) {
    sum += values[i];
  }
  return sum / period;
}

function smaFinite(values, period, index) {
  if (index + 1 < period) return null;
  let sum = 0;
  for (let i = index - period + 1; i <= index; i += 1) {
    const value = values[i];
    if (!Number.isFinite(value)) return null;
    sum += value;
  }
  return sum / period;
}

function computeEmaSeries(values, period) {
  const multiplier = 2 / (period + 1);
  const result = new Array(values.length).fill(null);
  let ema = null;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (!Number.isFinite(value)) continue;
    ema = ema == null ? value : ((value - ema) * multiplier) + ema;
    result[i] = ema;
  }
  return result;
}

function computeRsiSeries(closes, period = 14) {
  const result = new Array(closes.length).fill(null);
  if (closes.length <= period) return result;
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i += 1) {
    const delta = closes[i] - closes[i - 1];
    if (delta >= 0) gains += delta;
    else losses += Math.abs(delta);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;
  result[period] = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));

  for (let i = period + 1; i < closes.length; i += 1) {
    const delta = closes[i] - closes[i - 1];
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? Math.abs(delta) : 0;
    avgGain = ((avgGain * (period - 1)) + gain) / period;
    avgLoss = ((avgLoss * (period - 1)) + loss) / period;
    result[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
  }

  return result;
}

function computeStdDevSeries(values, period = 20) {
  const result = new Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i += 1) {
    const mean = smaFinite(values, period, i);
    if (!Number.isFinite(mean)) continue;
    let variance = 0;
    let valid = true;
    for (let j = i - period + 1; j <= i; j += 1) {
      const value = values[j];
      if (!Number.isFinite(value)) {
        valid = false;
        break;
      }
      variance += (value - mean) ** 2;
    }
    if (!valid) continue;
    result[i] = Math.sqrt(variance / period);
  }
  return result;
}

function computeAtrSeries(bars, period = 14) {
  const result = new Array(bars.length).fill(null);
  if (bars.length <= period) return result;
  const trueRanges = new Array(bars.length).fill(null);
  for (let i = 0; i < bars.length; i += 1) {
    const high = Number(bars[i].high);
    const low = Number(bars[i].low);
    const prevClose = i > 0 ? Number(bars[i - 1].close) : high;
    if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(prevClose)) continue;
    trueRanges[i] = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
  }
  let sum = 0;
  let count = 0;
  for (let i = 0; i < period; i += 1) {
    if (Number.isFinite(trueRanges[i])) {
      sum += trueRanges[i];
      count += 1;
    }
  }
  if (count < period) return result;
  let atr = sum / period;
  result[period - 1] = atr;
  for (let i = period; i < bars.length; i += 1) {
    if (!Number.isFinite(trueRanges[i])) continue;
    atr = ((atr * (period - 1)) + trueRanges[i]) / period;
    result[i] = atr;
  }
  return result;
}

function computeBollingerBandsSeries(values, period = 20, stdDevMultiplier = 2) {
  const basis = new Array(values.length).fill(null);
  const upper = new Array(values.length).fill(null);
  const lower = new Array(values.length).fill(null);
  const stdDev = computeStdDevSeries(values, period);
  for (let i = period - 1; i < values.length; i += 1) {
    const mean = smaFinite(values, period, i);
    const deviation = stdDev[i];
    if (!Number.isFinite(mean) || !Number.isFinite(deviation)) continue;
    basis[i] = mean;
    upper[i] = mean + (stdDevMultiplier * deviation);
    lower[i] = mean - (stdDevMultiplier * deviation);
  }
  return { basis, upper, lower };
}

function computeStochRsiSeries(rsiValues, period = 14, smoothK = 3, smoothD = 3) {
  const raw = new Array(rsiValues.length).fill(null);
  for (let i = period - 1; i < rsiValues.length; i += 1) {
    let minRsi = Number.POSITIVE_INFINITY;
    let maxRsi = Number.NEGATIVE_INFINITY;
    let valid = true;
    for (let j = i - period + 1; j <= i; j += 1) {
      const value = rsiValues[j];
      if (!Number.isFinite(value)) {
        valid = false;
        break;
      }
      minRsi = Math.min(minRsi, value);
      maxRsi = Math.max(maxRsi, value);
    }
    if (!valid || !Number.isFinite(rsiValues[i])) continue;
    raw[i] = maxRsi === minRsi ? 0 : ((rsiValues[i] - minRsi) / (maxRsi - minRsi)) * 100;
  }

  const k = new Array(rsiValues.length).fill(null);
  const d = new Array(rsiValues.length).fill(null);
  for (let i = 0; i < rsiValues.length; i += 1) {
    k[i] = smaFinite(raw, smoothK, i);
    d[i] = smaFinite(k, smoothD, i);
  }
  return { raw, k, d };
}

function findPriorConfirmedSwingLowIndex(lows, index, lookback = 18, swingWindow = 2) {
  const latestCandidate = index - swingWindow - 1;
  if (latestCandidate < swingWindow) return null;
  const start = Math.max(swingWindow, latestCandidate - lookback + 1);
  for (let candidate = latestCandidate; candidate >= start; candidate -= 1) {
    const center = lows[candidate];
    if (!Number.isFinite(center)) continue;
    let isSwingLow = true;
    for (let offset = 1; offset <= swingWindow; offset += 1) {
      const left = lows[candidate - offset];
      const right = lows[candidate + offset];
      if (!Number.isFinite(left) || !Number.isFinite(right) || center > left || center > right) {
        isSwingLow = false;
        break;
      }
    }
    if (isSwingLow) return candidate;
  }
  return null;
}

function computeSessionVwapSeries(bars, getSessionKey) {
  let currentSession = null;
  let cumulativeVolume = 0;
  let cumulativePriceVolume = 0;
  return bars.map((bar) => {
    const sessionKey = getSessionKey(bar.timestamp);
    if (sessionKey !== currentSession) {
      currentSession = sessionKey;
      cumulativeVolume = 0;
      cumulativePriceVolume = 0;
    }
    if (!sessionKey) return null;
    const typicalPrice = (Number(bar.high) + Number(bar.low) + Number(bar.close)) / 3;
    const volume = Number(bar.quoteVolume || bar.volume || 0);
    if (volume > 0 && Number.isFinite(typicalPrice)) {
      cumulativeVolume += volume;
      cumulativePriceVolume += typicalPrice * volume;
    }
    return cumulativeVolume > 0 ? cumulativePriceVolume / cumulativeVolume : null;
  });
}

function computeSessionOpeningRangeContexts(bars, openingRangeBars, getSessionKey) {
  let currentSession = null;
  let sessionStartIndex = -1;
  let openingRangeHigh = null;
  let openingRangeLow = null;
  return bars.map((bar, index) => {
    const sessionKey = getSessionKey(bar.timestamp);
    if (!sessionKey) {
      currentSession = null;
      sessionStartIndex = -1;
      openingRangeHigh = null;
      openingRangeLow = null;
      return {
        openingRangeHigh: null,
        openingRangeLow: null,
        openingRangeWidthPct: null,
        openingRangeComplete: false,
        barsSinceSessionStart: null,
      };
    }
    if (sessionKey !== currentSession) {
      currentSession = sessionKey;
      sessionStartIndex = index;
      openingRangeHigh = Number(bar.high);
      openingRangeLow = Number(bar.low);
    } else if ((index - sessionStartIndex) < openingRangeBars) {
      openingRangeHigh = Math.max(Number(openingRangeHigh || Number.NEGATIVE_INFINITY), Number(bar.high));
      openingRangeLow = Math.min(Number(openingRangeLow || Number.POSITIVE_INFINITY), Number(bar.low));
    }
    const barsSinceSessionStart = index - sessionStartIndex;
    return {
      openingRangeHigh,
      openingRangeLow,
      openingRangeWidthPct: (
        Number.isFinite(openingRangeHigh) &&
        Number.isFinite(openingRangeLow) &&
        Number(bar.close) > 0
      ) ? ((openingRangeHigh - openingRangeLow) / Number(bar.close)) : null,
      openingRangeComplete: barsSinceSessionStart >= (openingRangeBars - 1),
      barsSinceSessionStart,
    };
  });
}

function computeSessionRangeContexts(bars, getSessionKey) {
  let currentSession = null;
  let sessionHigh = null;
  let sessionLow = null;
  let priorSessionHigh = null;
  let priorSessionLow = null;

  return bars.map((bar) => {
    const sessionKey = getSessionKey(bar.timestamp);
    if (!sessionKey) {
      currentSession = null;
      sessionHigh = null;
      sessionLow = null;
      return null;
    }

    if (sessionKey !== currentSession) {
      if (currentSession != null) {
        priorSessionHigh = sessionHigh;
        priorSessionLow = sessionLow;
      }
      currentSession = sessionKey;
      sessionHigh = Number(bar.high);
      sessionLow = Number(bar.low);
    } else {
      sessionHigh = Math.max(Number(sessionHigh || Number.NEGATIVE_INFINITY), Number(bar.high));
      sessionLow = Math.min(Number(sessionLow || Number.POSITIVE_INFINITY), Number(bar.low));
    }

    return {
      sessionHigh,
      sessionLow,
      priorSessionHigh,
      priorSessionLow,
      sessionRangeMidpoint: (
        Number.isFinite(sessionHigh) &&
        Number.isFinite(sessionLow)
      ) ? ((sessionHigh + sessionLow) / 2) : null,
    };
  });
}

function resolveBrokenReferenceLevel(options = {}) {
  const low = Number(options.low);
  if (!Number.isFinite(low)) return null;
  const candidates = [
    { kind: "session_low", level: Number(options.sessionLowBeforeBar) },
    { kind: "prior_session_low", level: Number(options.priorSessionLow) },
    { kind: "prior_swing_low", level: Number(options.priorSwingLow) },
  ];
  for (const candidate of candidates) {
    if (!Number.isFinite(candidate.level) || candidate.level <= 0) continue;
    if (low < candidate.level) {
      return {
        kind: candidate.kind,
        level: candidate.level,
        depthPct: (candidate.level - low) / candidate.level,
      };
    }
  }
  return null;
}

function buildFailedBreakdownState(options = {}) {
  const index = Number(options.index);
  const bars = options.bars || [];
  const lows = options.lows || [];
  const closes = options.closes || [];
  const rsi14 = options.rsi14 || [];
  const bollinger20 = options.bollinger20 || { lower: [] };
  const sessionContexts = options.sessionContexts || [];
  const getSessionKey = typeof options.getSessionKey === "function" ? options.getSessionKey : () => null;

  if (!(index > 0)) {
    return {
      brokenReferenceLevel: null,
      brokenReferenceKind: null,
      breakdownDepthPct: null,
      previousBullishRsiDivergence: false,
      previousLowerBandTouched: false,
      reclaimCloseConfirmed: false,
      reclaimHoldConfirmed: false,
    };
  }

  const previousSessionKey = getSessionKey(bars[index - 1].timestamp);
  const previousPreviousSessionContext = (
    index > 1 &&
    previousSessionKey != null &&
    previousSessionKey === getSessionKey(bars[index - 2].timestamp)
  ) ? sessionContexts[index - 2] : null;
  const previousSessionLowBeforeBar = previousPreviousSessionContext?.sessionLow ?? null;
  const previousSessionContext = sessionContexts[index - 1] || null;
  const previousPriorSessionLow = previousSessionContext?.priorSessionLow ?? null;
  const previousPriorSwingLowIndex = findPriorConfirmedSwingLowIndex(lows, index - 1, 20, 2);
  const previousPriorSwingLow = previousPriorSwingLowIndex != null ? lows[previousPriorSwingLowIndex] : null;
  const previousPriorSwingLowRsi14 = previousPriorSwingLowIndex != null ? rsi14[previousPriorSwingLowIndex] : null;
  const breakdown = resolveBrokenReferenceLevel({
    sessionLowBeforeBar: previousSessionLowBeforeBar,
    priorSessionLow: previousPriorSessionLow,
    priorSwingLow: previousPriorSwingLow,
    low: lows[index - 1],
  });
  const previousBullishRsiDivergence = (
    Number.isFinite(previousPriorSwingLow) &&
    Number.isFinite(previousPriorSwingLowRsi14) &&
    Number.isFinite(rsi14[index - 1]) &&
    lows[index - 1] < (previousPriorSwingLow * 0.9995) &&
    rsi14[index - 1] >= (previousPriorSwingLowRsi14 + 2.5)
  );
  const previousLowerBandTouched = Number.isFinite(bollinger20.lower[index - 1])
    ? lows[index - 1] <= (bollinger20.lower[index - 1] * 1.005)
    : false;
  const previousCandleRange = Math.max(
    Number(bars[index - 1].high) - Number(bars[index - 1].low),
    closes[index - 1] * 0.0003,
  );
  const previousRejectionStrength = previousCandleRange > 0
    ? ((Number(bars[index - 1].close) - Number(bars[index - 1].low)) / previousCandleRange)
    : null;
  const reclaimCloseConfirmed = Boolean(
    breakdown &&
    breakdown.depthPct >= 0.0006 &&
    closes[index - 1] > breakdown.level &&
    previousRejectionStrength != null &&
    previousRejectionStrength >= 0.52
  );
  const reclaimHoldConfirmed = Boolean(
    breakdown &&
    reclaimCloseConfirmed &&
    lows[index] >= (breakdown.level * 0.999) &&
    closes[index] >= breakdown.level &&
    closes[index] > Number(bars[index].open)
  );

  return {
    brokenReferenceLevel: breakdown?.level ?? null,
    brokenReferenceKind: breakdown?.kind ?? null,
    breakdownDepthPct: breakdown?.depthPct ?? null,
    previousBullishRsiDivergence,
    previousLowerBandTouched,
    reclaimCloseConfirmed,
    reclaimHoldConfirmed,
  };
}

// ---------------------------------------------------------------------------
// Profitability Module 1: Market Regime Classifier
// Classifies each bar into a macro regime (trending_up, trending_down,
// ranging, volatile, quiet) using ATR percentile rank + EMA-based
// directional trend strength. Each strategy family declares which regimes
// it is allowed to trade in; signals are zeroed when the regime is wrong.
// ---------------------------------------------------------------------------

const ATR_PERCENTILE_LOOKBACK = 100;
const TREND_STRENGTH_ATR_DIVISOR = 1; // trendStrength = |EMA20 - EMA50| / ATR14

const REGIME_FAMILY_WHITELIST = {
  // Mean-reversion families: only trade in ranging or quiet markets
  crypto_range_mean_reversion:       ["ranging", "quiet"],
  // Reversal families: explicitly catch bottoms, so they need trending_down too
  crypto_bottom_reclaim:             ["ranging", "quiet", "volatile", "trending_down"],
  crypto_failed_breakdown_reclaim:   ["ranging", "quiet", "volatile", "trending_down"],
  // Momentum / breakout families: only trade when trending or volatile
  // ORB trades the breakout FROM a range, so it needs ranging too
  crypto_opening_range_breakout:     ["trending_up", "ranging", "volatile"],
  crypto_trend_continuation:         ["trending_up"],
  crypto_delta_breakout:             ["trending_up", "trending_down", "volatile"],
  // Order-flow families: work across regimes but not in quiet
  crypto_delta_divergence:           ["ranging", "trending_up", "trending_down", "volatile"],
  crypto_absorption:                 ["ranging", "volatile"],
  crypto_exhaustion:                 ["trending_up", "trending_down", "volatile"],
};

function computeRegimeClassification(options) {
  const { atr14, atr14Sma50, ema20, ema50, closes, index } = options;

  const currentAtr = atr14[index];
  const currentEma20 = ema20[index];
  const currentEma50 = ema50[index];
  const close = closes[index];

  if (!Number.isFinite(currentAtr) || !Number.isFinite(currentEma20) || !Number.isFinite(currentEma50) || close <= 0) {
    return { regime: "unknown", regimeStrength: 0, atrPercentile: null, trendStrength: null, trendDirection: null };
  }

  // ATR percentile rank over lookback window
  const lookbackStart = Math.max(0, index - ATR_PERCENTILE_LOOKBACK + 1);
  let below = 0;
  let total = 0;
  for (let i = lookbackStart; i <= index; i += 1) {
    if (Number.isFinite(atr14[i])) {
      total += 1;
      if (atr14[i] < currentAtr) below += 1;
    }
  }
  const atrPercentile = total > 10 ? below / total : null;

  // Directional trend strength: |EMA20 - EMA50| normalized by ATR14
  const emaDiff = currentEma20 - currentEma50;
  const trendStrength = currentAtr > 0 ? Math.abs(emaDiff) / (currentAtr * TREND_STRENGTH_ATR_DIVISOR) : 0;
  const trendDirection = emaDiff > 0 && close > currentEma20 ? "up"
    : emaDiff < 0 && close < currentEma20 ? "down"
    : "neutral";

  // Classify regime
  let regime;
  if (atrPercentile != null && atrPercentile >= 0.85 && trendStrength < 1.2) {
    regime = "volatile";      // High ATR but no strong directional trend
  } else if (atrPercentile != null && atrPercentile <= 0.2) {
    regime = "quiet";         // Very low volatility
  } else if (trendStrength >= 1.5 && trendDirection === "up") {
    regime = "trending_up";
  } else if (trendStrength >= 1.5 && trendDirection === "down") {
    regime = "trending_down";
  } else if (trendStrength < 0.8) {
    regime = "ranging";       // EMAs close together, no direction
  } else if (trendDirection === "up") {
    regime = "trending_up";
  } else if (trendDirection === "down") {
    regime = "trending_down";
  } else {
    regime = "ranging";
  }

  const regimeStrength = regime === "volatile" ? (atrPercentile || 0)
    : regime === "quiet" ? (1 - (atrPercentile || 0))
    : Math.min(trendStrength / 2, 1);

  return { regime, regimeStrength: round(regimeStrength, 4), atrPercentile: round(atrPercentile, 4), trendStrength: round(trendStrength, 4), trendDirection };
}

function isRegimeAllowed(signalName, regime) {
  const whitelist = REGIME_FAMILY_WHITELIST[signalName];
  if (!whitelist) return true; // Unknown families pass through
  if (regime === "unknown") return true; // Not enough data to classify
  return whitelist.includes(regime);
}

// ---------------------------------------------------------------------------
// Profitability Module 2: Multi-Timeframe Trend Filter
// Aggregates 5m bars into 1h bars (12:1) and computes higher-timeframe
// EMA20/EMA50 trend. Blocks counter-trend signals:
//   - Mean-reversion longs blocked when 1h trend is strongly down
//   - Breakout longs blocked when 1h trend is flat/ranging
//   - Trend continuation blocked when 1h trend disagrees
// ---------------------------------------------------------------------------

const HTF_AGGREGATION_RATIO = 12; // 12 × 5m = 1h
const HTF_EMA_FAST = 20;
const HTF_EMA_SLOW = 50;
const HTF_RSI_PERIOD = 14;

function computeHtfSeries(bars) {
  // Build 1h OHLCV bars by aggregating every 12 consecutive 5m bars
  const htfBars = [];
  for (let i = 0; i + HTF_AGGREGATION_RATIO - 1 < bars.length; i += HTF_AGGREGATION_RATIO) {
    const slice = bars.slice(i, i + HTF_AGGREGATION_RATIO);
    let high = -Infinity, low = Infinity, volume = 0;
    for (const b of slice) {
      const h = Number(b.high), l = Number(b.low), v = Number(b.quoteVolume || b.volume || 0);
      if (h > high) high = h;
      if (l < low) low = l;
      volume += v;
    }
    htfBars.push({
      open: Number(slice[0].open),
      high,
      low,
      close: Number(slice[slice.length - 1].close),
      volume,
    });
  }

  const htfCloses = htfBars.map((b) => b.close);
  const htfEmaFast = computeEmaSeries(htfCloses, HTF_EMA_FAST);
  const htfEmaSlow = computeEmaSeries(htfCloses, HTF_EMA_SLOW);
  const htfRsi = computeRsiSeries(htfCloses, HTF_RSI_PERIOD);

  // Map each 5m bar index back to its corresponding HTF bar
  const result = new Array(bars.length).fill(null);
  for (let htfIdx = 0; htfIdx < htfBars.length; htfIdx += 1) {
    const htfTrendUp = htfEmaFast[htfIdx] != null && htfEmaSlow[htfIdx] != null && htfEmaFast[htfIdx] > htfEmaSlow[htfIdx];
    const htfTrendDown = htfEmaFast[htfIdx] != null && htfEmaSlow[htfIdx] != null && htfEmaFast[htfIdx] < htfEmaSlow[htfIdx];
    const htfTrend = htfTrendUp ? "up" : htfTrendDown ? "down" : "neutral";
    const htfRsiVal = htfRsi[htfIdx];
    const htfEntry = {
      htfTrend,
      htfEmaFast: htfEmaFast[htfIdx],
      htfEmaSlow: htfEmaSlow[htfIdx],
      htfRsi: htfRsiVal,
      htfClose: htfCloses[htfIdx],
    };
    // Apply the same HTF state to all 12 constituent 5m bars
    const startIdx = htfIdx * HTF_AGGREGATION_RATIO;
    for (let j = 0; j < HTF_AGGREGATION_RATIO && startIdx + j < bars.length; j += 1) {
      result[startIdx + j] = htfEntry;
    }
  }
  // Fill remaining bars (incomplete last HTF bar) with last known state
  const lastHtf = htfBars.length > 0 ? result[(htfBars.length - 1) * HTF_AGGREGATION_RATIO] : null;
  for (let i = htfBars.length * HTF_AGGREGATION_RATIO; i < bars.length; i += 1) {
    result[i] = lastHtf;
  }
  return result;
}

const HTF_COUNTER_TREND_RULES = {
  // Mean-reversion longs: blocked when 1h trend is strongly down
  crypto_range_mean_reversion:       { blockLongWhenHtf: "down" },
  // Reversal signals: these fire AT bottoms during downtrends — no HTF block
  crypto_bottom_reclaim:             {},
  crypto_failed_breakdown_reclaim:   {},
  // Breakout / momentum longs: blocked when 1h trend is neutral or down
  crypto_opening_range_breakout:     { blockLongWhenHtf: "down", blockLongWhenHtfNeutral: true },
  crypto_trend_continuation:         { blockLongWhenHtf: "down", blockLongWhenHtfNeutral: true },
  crypto_delta_breakout:             { blockLongWhenHtf: "down" },
  // Bidirectional signals: block the side that opposes HTF trend
  crypto_delta_divergence:           { blockLongWhenHtf: "down", blockShortWhenHtf: "up" },
  crypto_exhaustion:                 { blockLongWhenHtf: "down", blockShortWhenHtf: "up" },
  crypto_absorption:                 { blockLongWhenHtf: "down", blockShortWhenHtf: "up" },
};

function isHtfBlocked(signalName, signalValue, htfEntry) {
  // If HTF data is insufficient (no EMAs or EMAs too close = not enough bars), don't block
  if (!htfEntry || htfEntry.htfEmaFast == null || htfEntry.htfEmaSlow == null) return false;
  // When fast and slow EMAs are nearly identical, there isn't enough HTF history
  // to distinguish trend direction — treat as insufficient data
  const emaDiffPct = htfEntry.htfEmaSlow > 0
    ? Math.abs(htfEntry.htfEmaFast - htfEntry.htfEmaSlow) / htfEntry.htfEmaSlow
    : 0;
  if (emaDiffPct < 0.0001) return false;
  const rules = HTF_COUNTER_TREND_RULES[signalName];
  if (!rules) return false;
  if (htfEntry.htfTrend === "neutral") {
    // For strategies that need trend confirmation even in neutral
    if (rules.blockLongWhenHtfNeutral && signalValue > 0) return true;
    return false;
  }
  if (signalValue > 0 && rules.blockLongWhenHtf === htfEntry.htfTrend) return true;
  if (signalValue < 0 && rules.blockShortWhenHtf === htfEntry.htfTrend) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Profitability Module 3: Session Phase Edge Scoring
// Profiles signal quality by session phase (early/mid/late/extended).
// Each strategy family has empirically tuned phase multipliers:
//   early (bars 0-8):    breakouts and ORB strongest
//   mid (bars 9-20):     mean reversion and divergence strongest
//   late (bars 21-32):   declining edge, tighter filter
//   extended (bars 33+): minimal edge, heavy penalty
// The edge score scales the final signal value, reducing false signals
// during statistically weak periods.
// ---------------------------------------------------------------------------

const SESSION_PHASE_THRESHOLDS = { early: 8, mid: 20, late: 32 };

function classifySessionPhase(barsSinceSessionStart) {
  if (barsSinceSessionStart == null || barsSinceSessionStart < 0) return "pre_session";
  if (barsSinceSessionStart <= SESSION_PHASE_THRESHOLDS.early) return "early";
  if (barsSinceSessionStart <= SESSION_PHASE_THRESHOLDS.mid) return "mid";
  if (barsSinceSessionStart <= SESSION_PHASE_THRESHOLDS.late) return "late";
  return "extended";
}

const SESSION_PHASE_MULTIPLIERS = {
  // Breakout families: strongest early when ranges form, weakest late
  crypto_opening_range_breakout:     { early: 1.15, mid: 1.0, late: 0.7, extended: 0.3, pre_session: 0 },
  crypto_delta_breakout:             { early: 1.1,  mid: 1.05, late: 0.75, extended: 0.4, pre_session: 0 },
  crypto_trend_continuation:         { early: 1.1,  mid: 1.1,  late: 0.8, extended: 0.5, pre_session: 0 },
  // Mean-reversion families: need range to form first, strongest mid-session
  crypto_range_mean_reversion:       { early: 0.6,  mid: 1.15, late: 1.0, extended: 0.5, pre_session: 0 },
  crypto_bottom_reclaim:             { early: 0.6,  mid: 1.15, late: 1.0, extended: 0.5, pre_session: 0 },
  crypto_failed_breakdown_reclaim:   { early: 0.5,  mid: 1.1,  late: 1.0, extended: 0.4, pre_session: 0 },
  // Order-flow families: moderate across phases, weaker extended
  crypto_delta_divergence:           { early: 0.85, mid: 1.1,  late: 0.9, extended: 0.4, pre_session: 0 },
  crypto_absorption:                 { early: 0.8,  mid: 1.1,  late: 0.95, extended: 0.45, pre_session: 0 },
  crypto_exhaustion:                 { early: 1.0,  mid: 1.05, late: 0.85, extended: 0.4, pre_session: 0 },
};

function getSessionPhaseMultiplier(signalName, barsSinceSessionStart) {
  const phase = classifySessionPhase(barsSinceSessionStart);
  const multipliers = SESSION_PHASE_MULTIPLIERS[signalName];
  if (!multipliers) return 1;
  return multipliers[phase] ?? 1;
}

// ---------------------------------------------------------------------------

function enrichBarsWithSignals(
  bars,
  strategy,
  config = DEFAULT_CRYPTO_DAY_TRADING_CONFIG,
  windowMode = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
) {
  const normalizedWindowMode = normalizeWindowMode(windowMode, config.sessionMode);
  const signalName = String(strategy.simulation?.entrySignal || "");
  const closes = bars.map((bar) => Number(bar.close));
  const lows = bars.map((bar) => Number(bar.low));
  const volumes = bars.map((bar) => Number(bar.quoteVolume || bar.volume || 0));
  const ema20 = computeEmaSeries(closes, 20);
  const ema50 = computeEmaSeries(closes, 50);
  const rsi14 = computeRsiSeries(closes, 14);
  const bollinger20 = computeBollingerBandsSeries(closes, 20, 2);
  const stochRsi14 = computeStochRsiSeries(rsi14, 14, 3, 3);
  const atr14 = computeAtrSeries(bars, 14);
  const atr14Sma50 = new Array(bars.length).fill(null);
  for (let i = 49; i < bars.length; i += 1) {
    const avg = smaFinite(atr14, 50, i);
    if (Number.isFinite(avg)) atr14Sma50[i] = avg;
  }

  // Order flow: taker buy volume, sell volume, delta, CVD
  const takerBuyVol = bars.map((bar) => Number(bar.takerBuyQuoteVolume || bar.takerBuyBaseVolume || 0));
  const totalVol = bars.map((bar) => Number(bar.quoteVolume || bar.volume || 0));
  const takerSellVol = totalVol.map((tv, i) => Math.max(0, tv - takerBuyVol[i]));
  const barDelta = takerBuyVol.map((bv, i) => bv - takerSellVol[i]);
  const buyPressure = totalVol.map((tv, i) => tv > 0 ? takerBuyVol[i] / tv : 0.5);
  // Session cumulative volume delta (resets each session)
  const sessionCvd = new Array(bars.length).fill(0);
  // Rolling CVD over N bars
  const cvd14 = new Array(bars.length).fill(0);
  // Delta EMA for smoothing
  const deltaEma8 = computeEmaSeries(barDelta, 8);
  const deltaEma20 = computeEmaSeries(barDelta, 20);

  const getSessionKey = (timestamp) => buildWindowSessionKey(timestamp, { config, windowMode: normalizedWindowMode });
  const openingRangeBars = Math.max(1, Math.round(Number(
    strategy.metadata?.openingRangeBars ||
    strategy.simulation?.openingRangeBars ||
    3
  )));
  const getOpeningRangeSessionKey = (timestamp) => buildWindowSessionKey(timestamp, {
    config,
    windowMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
  });
  const vwap = computeSessionVwapSeries(bars, getSessionKey);
  const sessionContexts = computeSessionRangeContexts(bars, getSessionKey);
  const openingRangeContexts = computeSessionOpeningRangeContexts(bars, openingRangeBars, getOpeningRangeSessionKey);
  const openingRangeSessionContexts = computeSessionRangeContexts(bars, getOpeningRangeSessionKey);
  const openingRangeSessionVwap = computeSessionVwapSeries(bars, getOpeningRangeSessionKey);
  let currentSessionKey = null;
  let currentSessionStartIndex = -1;
  let eventShockLockoutRemaining = 0;
  let sessionCvdAccumulator = 0;

  // Pre-compute rolling CVD (sum of barDelta over last 14 bars)
  for (let i = 0; i < bars.length; i += 1) {
    let sum = 0;
    for (let j = Math.max(0, i - 13); j <= i; j += 1) sum += barDelta[j];
    cvd14[i] = sum;
  }

  // Profitability Module 2: Pre-compute 1h (HTF) trend series
  const htfSeries = computeHtfSeries(bars);

  return bars.map((bar, index) => {
    const priorClose = index > 0 ? closes[index - 1] : null;
    const sessionKey = getSessionKey(bar.timestamp);
    if (sessionKey !== currentSessionKey) {
      currentSessionKey = sessionKey;
      currentSessionStartIndex = sessionKey ? index : -1;
      sessionCvdAccumulator = 0;
    }
    sessionCvdAccumulator += barDelta[index];
    sessionCvd[index] = sessionCvdAccumulator;
    const window = classifyWindow(bar.timestamp, { config, windowMode: normalizedWindowMode });
    const openingRangeWindow = classifyScheduledWindow(bar.timestamp, config);
    const barsSinceSessionStart = sessionKey && currentSessionStartIndex >= 0 ? (index - currentSessionStartIndex) : null;
    const volumeAverage = sma(volumes, 20, index);
    const volumeRatio = volumeAverage && volumeAverage > 0 ? volumes[index] / volumeAverage : null;
    const previousVolumeAverage = index > 0 ? sma(volumes, 20, index - 1) : null;
    const previousVolumeRatio = previousVolumeAverage && previousVolumeAverage > 0 ? volumes[index - 1] / previousVolumeAverage : null;
    const pctChange = priorClose && priorClose > 0 ? (closes[index] - priorClose) / priorClose : 0;
    const sessionContext = sessionContexts[index];
    const openingRangeContext = openingRangeContexts[index];
    const openingRangeSessionContext = openingRangeSessionContexts[index];
    const priorContext = (
      index > 0 &&
      sessionKey != null &&
      sessionKey === getSessionKey(bars[index - 1].timestamp)
    ) ? sessionContexts[index - 1] : null;
    const sessionHighBeforeBar = priorContext?.sessionHigh ?? sessionContext?.sessionHigh ?? null;
    const sessionLowBeforeBar = priorContext?.sessionLow ?? sessionContext?.sessionLow ?? null;
    const openingRangePriorContext = (
      index > 0 &&
      getOpeningRangeSessionKey(bar.timestamp) != null &&
      getOpeningRangeSessionKey(bar.timestamp) === getOpeningRangeSessionKey(bars[index - 1].timestamp)
    ) ? openingRangeSessionContexts[index - 1] : null;
    const openingRangeSessionHighBeforeBar = openingRangePriorContext?.sessionHigh ?? openingRangeSessionContext?.sessionHigh ?? null;
    const openingRangeSessionLowBeforeBar = openingRangePriorContext?.sessionLow ?? openingRangeSessionContext?.sessionLow ?? null;
    const priorSwingLowIndex = findPriorConfirmedSwingLowIndex(lows, index, 20, 2);
    const priorSwingLow = priorSwingLowIndex != null ? lows[priorSwingLowIndex] : null;
    const priorSwingLowRsi14 = priorSwingLowIndex != null ? rsi14[priorSwingLowIndex] : null;
    const bullishRsiDivergence = (
      Number.isFinite(priorSwingLow) &&
      Number.isFinite(priorSwingLowRsi14) &&
      Number.isFinite(rsi14[index]) &&
      lows[index] < (priorSwingLow * 0.9995) &&
      rsi14[index] >= (priorSwingLowRsi14 + 2.5)
    );
    const sessionRangeWidth = (
      Number.isFinite(sessionHighBeforeBar) &&
      Number.isFinite(sessionLowBeforeBar) &&
      closes[index] > 0
    ) ? ((sessionHighBeforeBar - sessionLowBeforeBar) / closes[index]) : null;
    const openingRangeSessionRangeWidth = (
      Number.isFinite(openingRangeSessionHighBeforeBar) &&
      Number.isFinite(openingRangeSessionLowBeforeBar) &&
      closes[index] > 0
    ) ? ((openingRangeSessionHighBeforeBar - openingRangeSessionLowBeforeBar) / closes[index]) : null;
    const candleRange = Math.max(Number(bar.high) - Number(bar.low), closes[index] * 0.0003);
    const rejectionStrength = candleRange > 0 ? ((Number(bar.close) - Number(bar.low)) / candleRange) : 0;
    const priorSessionLow = sessionContext?.priorSessionLow ?? null;
    const priorSessionHigh = sessionContext?.priorSessionHigh ?? null;
    const abnormalRange = sessionRangeWidth != null && sessionRangeWidth >= 0.018;
    const volumeShock = volumeRatio != null && volumeRatio >= 1.7;
    const eventShockTrigger = Boolean(window.active && sessionKey && abnormalRange && volumeShock);
    const eventShockBlocked = eventShockTrigger || eventShockLockoutRemaining > 0;
    let signalValue = 0;
    let regimeState = window.active && sessionKey ? "monitoring" : "outside_fixed_session";
    let tradeable = false;
    const regimeBlockers = [];

    if (!window.active || !sessionKey) {
      signalValue = 0;
      regimeBlockers.push("outside_fixed_session");
    } else if (signalName === "crypto_range_mean_reversion") {
      const nearSessionLow = Number.isFinite(sessionLowBeforeBar)
        ? ((closes[index] - sessionLowBeforeBar) / closes[index]) <= 0.005
        : false;
      const nearPriorSessionLow = Number.isFinite(priorSessionLow)
        ? Math.abs((closes[index] - priorSessionLow) / closes[index]) <= 0.006
        : false;
      const rejectionCandle = closes[index] > Number(bar.open) && rejectionStrength >= 0.42;
      const rsiRecovering = rsi14[index] != null && rsi14[index] >= 25 && rsi14[index] <= 65;
      const movingAwayFromVwap = vwap[index] != null && closes[index] > (vwap[index] * 1.005);
      const nearVwap = vwap[index] != null && !movingAwayFromVwap;
      const containedVolume = volumeRatio == null || volumeRatio <= 2.5;
      const rangeReady = sessionRangeWidth != null && sessionRangeWidth >= 0.002;
      const expansionBlocked = movingAwayFromVwap || sessionRangeWidth > 0.03 || !containedVolume;
      const sessionMidpoint = Number(sessionContext?.sessionRangeMidpoint);
      const crossedMidpoint = Number.isFinite(sessionMidpoint) && closes[index] >= sessionMidpoint;
      const midRangeBlocked = (!(nearSessionLow || nearPriorSessionLow)) || crossedMidpoint;
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 44;
      const highVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] > atr14Sma50[index] * 2.5;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (highVolBlocked) regimeBlockers.push("high_volatility_lockout");
      if (expansionBlocked) regimeBlockers.push("expansion");
      if (midRangeBlocked) regimeBlockers.push("mid_range");
      if (!rangeReady) regimeBlockers.push("range_not_ready");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable
        ? "range_tradeable"
        : (eventShockBlocked
          ? "range_blocked_event_shock_lockout"
          : (highVolBlocked
            ? "range_blocked_high_volatility"
            : (expansionBlocked
              ? "range_blocked_expansion"
              : (midRangeBlocked ? "range_blocked_mid_range" : "range_monitoring"))));
      signalValue = (
        tradeable &&
        sessionTimingOkay &&
        rangeReady &&
        nearVwap &&
        rsiRecovering &&
        rejectionCandle &&
        (nearSessionLow || nearPriorSessionLow)
      ) ? Math.min(1, 0.58 + Math.min(Math.abs(pctChange) * 30, 0.18) + Math.min(rejectionStrength * 0.2, 0.18)) : 0;
    } else if (signalName === "crypto_bottom_reclaim") {
      const nearSessionLow = Number.isFinite(sessionLowBeforeBar)
        ? ((closes[index] - sessionLowBeforeBar) / closes[index]) <= 0.005
        : false;
      const nearPriorSessionLow = Number.isFinite(priorSessionLow)
        ? Math.abs((closes[index] - priorSessionLow) / closes[index]) <= 0.006
        : false;
      const lowerBandTouched = Number.isFinite(bollinger20.lower[index])
        ? lows[index] <= (bollinger20.lower[index] * 1.008)
        : false;
      const stochCrossUp = (
        Number.isFinite(stochRsi14.k[index]) &&
        Number.isFinite(stochRsi14.k[index - 1]) &&
        stochRsi14.k[index] > stochRsi14.k[index - 1] &&
        stochRsi14.k[index - 1] <= 45 &&
        stochRsi14.k[index] <= 80
      );
      const volumeRamp = index >= 3
        ? (
          (volumes[index - 2] > volumes[index - 3] && volumes[index - 1] > volumes[index - 2] && volumes[index] > volumes[index - 1]) ||
          (volumes[index] > volumes[index - 1] && volumes[index - 1] > volumes[index - 3]) ||
          (volumeRatio != null && volumeRatio >= 1.1)
        )
        : false;
      const volumeConfirmed = volumeRamp && volumeRatio != null && volumeRatio >= 0.8 && volumeRatio <= 3.5;
      const rejectionCandle = closes[index] > Number(bar.open) && rejectionStrength >= 0.42;
      const movingAwayFromVwap = vwap[index] != null && closes[index] > (vwap[index] * 1.004);
      const rangeReady = sessionRangeWidth != null && sessionRangeWidth >= 0.002;
      const sessionMidpoint = Number(sessionContext?.sessionRangeMidpoint);
      const crossedMidpoint = Number.isFinite(sessionMidpoint) && closes[index] >= sessionMidpoint;
      const midRangeBlocked = (!(nearSessionLow || nearPriorSessionLow)) || crossedMidpoint;
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 44;
      const expansionBlocked = movingAwayFromVwap || sessionRangeWidth > 0.03 || (volumeRatio != null && volumeRatio > 3.5);
      const highVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] > atr14Sma50[index] * 2.5;
      const volumeSmaConfirmed = volumeAverage != null && volumeAverage > 0 && volumes[index] > volumeAverage * 0.9;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (highVolBlocked) regimeBlockers.push("high_volatility_lockout");
      if (expansionBlocked) regimeBlockers.push("expansion");
      if (midRangeBlocked) regimeBlockers.push("mid_range");
      if (!rangeReady) regimeBlockers.push("range_not_ready");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable
        ? "bottom_reclaim_tradeable"
        : (eventShockBlocked
          ? "bottom_reclaim_blocked_event_shock_lockout"
          : (highVolBlocked
            ? "bottom_reclaim_blocked_high_volatility"
            : (expansionBlocked
              ? "bottom_reclaim_blocked_expansion"
              : (midRangeBlocked ? "bottom_reclaim_blocked_mid_range" : "bottom_reclaim_monitoring"))));
      const confluenceCount = [
        lowerBandTouched,
        bullishRsiDivergence,
        stochCrossUp,
        volumeConfirmed,
        rejectionCandle,
      ].filter(Boolean).length;
      const setupConfirmed = rejectionCandle && confluenceCount >= 2 && (lowerBandTouched || bullishRsiDivergence || volumeSmaConfirmed);
      const divergenceStrength = bullishRsiDivergence && Number.isFinite(priorSwingLowRsi14) && Number.isFinite(rsi14[index])
        ? Math.min(Math.max(rsi14[index] - priorSwingLowRsi14, 0) / 20, 0.16)
        : 0;
      const stochLift = Number.isFinite(stochRsi14.k[index]) && Number.isFinite(stochRsi14.d[index])
        ? Math.min(Math.max(stochRsi14.k[index] - stochRsi14.d[index], 0) / 100, 0.08)
        : 0;
      signalValue = (
        tradeable &&
        setupConfirmed &&
        (nearSessionLow || nearPriorSessionLow)
      ) ? Math.min(
        1,
        0.48 +
        (confluenceCount * 0.1) +
        divergenceStrength +
        stochLift +
        Math.min(rejectionStrength * 0.1, 0.08),
      ) : 0;
    } else if (signalName === "crypto_failed_breakdown_reclaim") {
      const failedBreakdownState = buildFailedBreakdownState({
        index,
        bars,
        lows,
        closes,
        rsi14,
        bollinger20,
        sessionContexts,
        getSessionKey,
      });
      const stochRecovery = (
        Number.isFinite(stochRsi14.k[index]) &&
        Number.isFinite(stochRsi14.d[index]) &&
        stochRsi14.k[index] >= stochRsi14.d[index] &&
        stochRsi14.k[index] >= 18 &&
        stochRsi14.k[index] <= 85
      );
      const volumeConfirmed = [volumeRatio, previousVolumeRatio]
        .some((value) => value != null && value >= 0.7 && value <= 4.0);
      const movingAwayFromVwap = vwap[index] != null && closes[index] > (vwap[index] * 1.004);
      const rangeReady = sessionRangeWidth != null && sessionRangeWidth >= 0.002;
      const sessionMidpoint = Number(sessionContext?.sessionRangeMidpoint);
      const crossedMidpoint = Number.isFinite(sessionMidpoint) && closes[index] >= sessionMidpoint;
      const midRangeBlocked = (
        failedBreakdownState.brokenReferenceKind == null ||
        crossedMidpoint
      );
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 44;
      const expansionBlocked = movingAwayFromVwap || sessionRangeWidth > 0.03 || (volumeRatio != null && volumeRatio > 4.0);
      const highVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] > atr14Sma50[index] * 2.5;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (highVolBlocked) regimeBlockers.push("high_volatility_lockout");
      if (expansionBlocked) regimeBlockers.push("expansion");
      if (midRangeBlocked) regimeBlockers.push("mid_range");
      if (!rangeReady) regimeBlockers.push("range_not_ready");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable
        ? "failed_breakdown_reclaim_tradeable"
        : (eventShockBlocked
          ? "failed_breakdown_reclaim_blocked_event_shock_lockout"
          : (highVolBlocked
            ? "failed_breakdown_reclaim_blocked_high_volatility"
            : (expansionBlocked
              ? "failed_breakdown_reclaim_blocked_expansion"
              : (midRangeBlocked ? "failed_breakdown_reclaim_blocked_mid_range" : "failed_breakdown_reclaim_monitoring"))));
      const confluenceCount = [
        failedBreakdownState.previousBullishRsiDivergence,
        failedBreakdownState.previousLowerBandTouched,
        stochRecovery,
        volumeConfirmed,
        closes[index] > Number(bar.open),
      ].filter(Boolean).length;
      const depthStrength = failedBreakdownState.breakdownDepthPct != null
        ? Math.min(Math.max(failedBreakdownState.breakdownDepthPct - 0.0006, 0) / 0.01, 0.16)
        : 0;
      signalValue = (
        tradeable &&
        failedBreakdownState.reclaimCloseConfirmed &&
        failedBreakdownState.reclaimHoldConfirmed &&
        confluenceCount >= 2
      ) ? Math.min(
        1,
        0.46 +
        (confluenceCount * 0.08) +
        depthStrength +
        Math.min(rejectionStrength * 0.1, 0.08),
      ) : 0;
    } else if (signalName === "crypto_opening_range_breakout") {
      const openingRangeVariant = String(strategy.metadata?.openingRangeVariant || "breakout_close");
      const openingRangeHigh = openingRangeContext?.openingRangeHigh ?? null;
      const openingRangeWidthPct = openingRangeContext?.openingRangeWidthPct ?? null;
      const openingRangeComplete = openingRangeContext?.openingRangeComplete === true;
      const openingRangeBarsSinceSessionStart = openingRangeContext?.barsSinceSessionStart ?? null;
      const orbVwap = openingRangeSessionVwap[index];
      const trendOkay = ema20[index] != null && ema50[index] != null && ema20[index] > ema50[index];
      const aboveVwap = orbVwap != null && closes[index] > orbVwap;
      const rangeUsable = openingRangeWidthPct != null && openingRangeWidthPct >= 0.0008 && openingRangeWidthPct <= 0.018;
      const sessionTimingOkay = openingRangeBarsSinceSessionStart != null &&
        openingRangeBarsSinceSessionStart >= openingRangeBars &&
        openingRangeBarsSinceSessionStart <= 36;
      const breakoutBufferFraction = openingRangeWidthPct != null
        ? Math.min(Math.max(openingRangeWidthPct * 0.08, 0.0004), 0.0012)
        : 0.0006;
      const breakoutLevel = Number.isFinite(openingRangeHigh)
        ? openingRangeHigh * (1 + breakoutBufferFraction)
        : null;
      const breakoutCloseSignal = Boolean(
        openingRangeComplete &&
        Number.isFinite(breakoutLevel) &&
        priorClose != null &&
        priorClose <= breakoutLevel &&
        closes[index] > breakoutLevel
      );
      const breakoutRetestSignal = Boolean(
        openingRangeComplete &&
        Number.isFinite(openingRangeHigh) &&
        priorClose != null &&
        priorClose > (openingRangeHigh * 1.0004) &&
        Number(bar.low) <= (openingRangeHigh * 1.0015) &&
        closes[index] >= (openingRangeHigh * 1.0002) &&
        closes[index] > Number(bar.open) &&
        rejectionStrength >= 0.55
      );
      const volumeConfirmed = volumeRatio != null && volumeRatio >= (openingRangeVariant === "breakout_retest" ? 0.8 : 0.85);
      const lowVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] < atr14Sma50[index] * 0.25;
      const rangeTooNarrow = openingRangeWidthPct != null && openingRangeWidthPct < 0.001;
      if (!openingRangeWindow.active) regimeBlockers.push("outside_fixed_session");
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (lowVolBlocked) regimeBlockers.push("low_volatility_lockout");
      if (rangeTooNarrow) regimeBlockers.push("range_too_narrow");
      if (!openingRangeComplete) regimeBlockers.push("opening_range_not_complete");
      if (!rangeUsable) regimeBlockers.push("opening_range_not_usable");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      if (!(trendOkay && aboveVwap)) regimeBlockers.push("trend_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable
        ? `opening_range_breakout_tradeable_${openingRangeVariant}`
        : (eventShockBlocked
          ? "opening_range_breakout_blocked_event_shock_lockout"
          : (lowVolBlocked
            ? "opening_range_breakout_blocked_low_volatility"
            : (!openingRangeWindow.active
              ? "opening_range_breakout_blocked_outside_fixed_session"
              : "opening_range_breakout_monitoring")));
      const openingRangeSignal = openingRangeVariant === "breakout_retest"
        ? breakoutRetestSignal
        : breakoutCloseSignal;
      signalValue = (
        tradeable &&
        volumeConfirmed &&
        openingRangeSignal
      ) ? Math.min(
        1,
        0.58 +
        Math.min((volumeRatio || 0) / 6, 0.2) +
        Math.min((openingRangeWidthPct || 0) * 8, 0.08) +
        Math.max(0, pctChange * 40),
      ) : 0;
    } else if (signalName === "crypto_trend_continuation") {
      const trendOkay = ema20[index] != null && ema50[index] != null && ema20[index] > ema50[index];
      const heldAboveFastTrend = ema20[index] != null && closes[index] > ema20[index];
      const brokePriorSessionHigh = Number.isFinite(priorSessionHigh) &&
        closes[index] > (priorSessionHigh * 1.0003) &&
        priorClose != null &&
        priorClose <= (priorSessionHigh * 1.003);
      const rsiOkay = rsi14[index] != null && rsi14[index] >= 48 && rsi14[index] <= 80;
      const volumeBoost = volumeRatio != null && volumeRatio >= 0.85;
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 44;
      const lowVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] < atr14Sma50[index] * 0.3;
      if (lowVolBlocked) regimeBlockers.push("low_volatility_lockout");
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      tradeable = trendOkay && heldAboveFastTrend && regimeBlockers.length === 0;
      regimeState = tradeable ? "trend_tradeable" : (lowVolBlocked ? "trend_blocked_low_volatility" : "trend_monitoring");
      signalValue = (tradeable && brokePriorSessionHigh && rsiOkay && volumeBoost && sessionTimingOkay)
        ? Math.min(1, 0.6 + Math.max(0, pctChange * 45) + Math.min((volumeRatio || 0) / 6, 0.18))
        : 0;
    } else if (signalName === "crypto_delta_divergence") {
      // Delta divergence: price makes new session low but CVD holds higher (buyers absorbing selling)
      // OR price makes new session high but CVD holds lower (sellers absorbing buying) → short
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 8 && barsSinceSessionStart <= 40;
      const rangeReady = sessionRangeWidth != null && sessionRangeWidth >= 0.003;
      const highVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] > atr14Sma50[index] * 2.0;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (highVolBlocked) regimeBlockers.push("high_volatility_lockout");
      if (!rangeReady) regimeBlockers.push("range_not_ready");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable ? "delta_divergence_tradeable" : "delta_divergence_monitoring";

      // Look for bullish divergence: price at/near session low, but CVD is rising
      const nearSessionLow = Number.isFinite(sessionLowBeforeBar) && ((closes[index] - sessionLowBeforeBar) / closes[index]) <= 0.005;
      const priorCvd = index >= 5 ? sessionCvd[index - 5] : null;
      const cvdRising = priorCvd != null && sessionCvd[index] > priorCvd;
      const deltaPositive = deltaEma8[index] != null && deltaEma8[index] > 0;
      const buyPressureStrong = buyPressure[index] >= 0.52;
      const rejectionCandle = closes[index] > Number(bar.open) && rejectionStrength >= 0.42;
      // Bearish divergence: price at/near session high, but CVD is falling
      const nearSessionHigh = Number.isFinite(sessionHighBeforeBar) && ((sessionHighBeforeBar - closes[index]) / closes[index]) <= 0.005;
      const cvdFalling = priorCvd != null && sessionCvd[index] < priorCvd;
      const deltaNegative = deltaEma8[index] != null && deltaEma8[index] < 0;
      const sellPressureStrong = buyPressure[index] <= 0.48;
      const bearishRejection = closes[index] < Number(bar.open) && ((Number(bar.high) - closes[index]) / candleRange) >= 0.42;

      const bullishSetup = nearSessionLow && cvdRising && deltaPositive && buyPressureStrong && rejectionCandle;
      const bearishSetup = nearSessionHigh && cvdFalling && deltaNegative && sellPressureStrong && bearishRejection;

      if (tradeable && bullishSetup) {
        const cvdStrength = priorCvd != null ? Math.min(Math.abs(sessionCvd[index] - priorCvd) / (totalVol[index] || 1), 0.15) : 0;
        signalValue = Math.min(1, 0.55 + (buyPressure[index] - 0.5) * 2 + cvdStrength + Math.min(rejectionStrength * 0.12, 0.1));
      } else if (tradeable && bearishSetup) {
        const cvdStrength = priorCvd != null ? Math.min(Math.abs(sessionCvd[index] - priorCvd) / (totalVol[index] || 1), 0.15) : 0;
        signalValue = -(Math.min(1, 0.55 + (0.5 - buyPressure[index]) * 2 + cvdStrength + Math.min((1 - rejectionStrength) * 0.12, 0.1)));
      } else {
        signalValue = 0;
      }

    } else if (signalName === "crypto_delta_breakout") {
      // Delta breakout: CVD surges past session high while price breaks out -- confirms real demand (or supply for short)
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 6 && barsSinceSessionStart <= 40;
      const trendOkay = ema20[index] != null && ema50[index] != null;
      const bullishTrend = trendOkay && ema20[index] > ema50[index];
      const bearishTrend = trendOkay && ema20[index] < ema50[index];
      const lowVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] < atr14Sma50[index] * 0.4;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (lowVolBlocked) regimeBlockers.push("low_volatility_lockout");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable ? "delta_breakout_tradeable" : "delta_breakout_monitoring";

      // Bullish: price breaks session high + CVD surging + strong buy pressure + expanding volume
      const priceBreakHigh = Number.isFinite(sessionHighBeforeBar) && closes[index] > sessionHighBeforeBar && priorClose != null && priorClose <= sessionHighBeforeBar * 1.003;
      const cvdSurging = deltaEma8[index] != null && deltaEma20[index] != null && deltaEma8[index] > deltaEma20[index] * 1.2 && deltaEma8[index] > 0;
      const volumeExpanding = volumeRatio != null && volumeRatio >= 1.0;
      const buyDominant = buyPressure[index] >= 0.53;
      // Bearish: price breaks session low + CVD plunging + strong sell pressure
      const priceBreakLow = Number.isFinite(sessionLowBeforeBar) && closes[index] < sessionLowBeforeBar && priorClose != null && priorClose >= sessionLowBeforeBar * 0.997;
      const cvdPlunging = deltaEma8[index] != null && deltaEma20[index] != null && deltaEma8[index] < deltaEma20[index] * 1.2 && deltaEma8[index] < 0;
      const sellDominant = buyPressure[index] <= 0.47;

      const bullishBreakout = priceBreakHigh && cvdSurging && volumeExpanding && buyDominant && bullishTrend;
      const bearishBreakout = priceBreakLow && cvdPlunging && volumeExpanding && sellDominant && bearishTrend;

      if (tradeable && bullishBreakout) {
        signalValue = Math.min(1, 0.56 + Math.min((volumeRatio || 0) / 5, 0.2) + (buyPressure[index] - 0.5) * 1.5 + Math.max(0, pctChange * 30));
      } else if (tradeable && bearishBreakout) {
        signalValue = -(Math.min(1, 0.56 + Math.min((volumeRatio || 0) / 5, 0.2) + (0.5 - buyPressure[index]) * 1.5 + Math.max(0, -pctChange * 30)));
      } else {
        signalValue = 0;
      }

    } else if (signalName === "crypto_absorption") {
      // Absorption: high volume bar but price barely moves -- large orders are absorbing directional flow
      // If absorbing at lows (big volume, price doesn't drop) → bullish
      // If absorbing at highs (big volume, price doesn't rise) → bearish
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 40;
      const highVolBlocked = Number.isFinite(atr14[index]) && Number.isFinite(atr14Sma50[index]) && atr14Sma50[index] > 0 && atr14[index] > atr14Sma50[index] * 2.5;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (highVolBlocked) regimeBlockers.push("high_volatility_lockout");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable ? "absorption_tradeable" : "absorption_monitoring";

      const highVolume = volumeRatio != null && volumeRatio >= 1.4;
      const tinyMove = Math.abs(pctChange) <= 0.002;
      const narrowBody = candleRange > 0 && Math.abs(closes[index] - Number(bar.open)) / candleRange <= 0.45;
      const absorptionBar = highVolume && tinyMove && narrowBody;

      // At session lows with buy pressure → bullish absorption
      const nearLow = Number.isFinite(sessionLowBeforeBar) && ((closes[index] - sessionLowBeforeBar) / closes[index]) <= 0.006;
      const buyAbsorption = absorptionBar && nearLow && buyPressure[index] >= 0.51;
      // At session highs with sell pressure → bearish absorption
      const nearHigh = Number.isFinite(sessionHighBeforeBar) && ((sessionHighBeforeBar - closes[index]) / closes[index]) <= 0.006;
      const sellAbsorption = absorptionBar && nearHigh && buyPressure[index] <= 0.49;

      if (tradeable && buyAbsorption) {
        signalValue = Math.min(1, 0.52 + Math.min((volumeRatio || 0) / 8, 0.2) + (buyPressure[index] - 0.5) * 2 + Math.min(Math.abs(barDelta[index]) / (totalVol[index] || 1), 0.12));
      } else if (tradeable && sellAbsorption) {
        signalValue = -(Math.min(1, 0.52 + Math.min((volumeRatio || 0) / 8, 0.2) + (0.5 - buyPressure[index]) * 2 + Math.min(Math.abs(barDelta[index]) / (totalVol[index] || 1), 0.12)));
      } else {
        signalValue = 0;
      }

    } else if (signalName === "crypto_exhaustion") {
      // Exhaustion: volume spike with immediate reversal -- trapped traders
      // After a move up: spike volume, bearish reversal candle → short
      // After a move down: spike volume, bullish reversal candle → long
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 4 && barsSinceSessionStart <= 40;
      if (eventShockBlocked) regimeBlockers.push("event_shock_lockout");
      if (!sessionTimingOkay) regimeBlockers.push("timing_not_ready");
      tradeable = regimeBlockers.length === 0;
      regimeState = tradeable ? "exhaustion_tradeable" : "exhaustion_monitoring";

      const volumeSpike = volumeRatio != null && volumeRatio >= 1.6;
      const priorMoveUp = index >= 3 && closes[index - 1] > closes[index - 3] && ((closes[index - 1] - closes[index - 3]) / closes[index - 3]) >= 0.002;
      const priorMoveDown = index >= 3 && closes[index - 1] < closes[index - 3] && ((closes[index - 3] - closes[index - 1]) / closes[index - 3]) >= 0.002;
      const bearishReversal = closes[index] < Number(bar.open) && ((Number(bar.high) - closes[index]) / candleRange) >= 0.48;
      const bullishReversal = closes[index] > Number(bar.open) && rejectionStrength >= 0.48;
      // Delta confirmation: exhaustion candle should show the trapped side
      const deltaFlip = deltaEma8[index] != null && deltaEma20[index] != null;

      // Bearish exhaustion: big move up, spike volume, bearish reversal, sellers taking over
      const bearishExhaustion = volumeSpike && priorMoveUp && bearishReversal && buyPressure[index] <= 0.50;
      // Bullish exhaustion: big move down, spike volume, bullish reversal, buyers taking over
      const bullishExhaustion = volumeSpike && priorMoveDown && bullishReversal && buyPressure[index] >= 0.50;

      if (tradeable && bullishExhaustion) {
        signalValue = Math.min(1, 0.54 + Math.min((volumeRatio || 0) / 6, 0.18) + (buyPressure[index] - 0.5) * 2 + Math.min(rejectionStrength * 0.15, 0.12));
      } else if (tradeable && bearishExhaustion) {
        signalValue = -(Math.min(1, 0.54 + Math.min((volumeRatio || 0) / 6, 0.18) + (0.5 - buyPressure[index]) * 2 + Math.min((1 - rejectionStrength) * 0.15, 0.12)));
      } else {
        signalValue = 0;
      }

    } else if (signalName === "crypto_event_watch") {
      regimeState = eventShockTrigger ? "event_shock" : "event_monitoring";
      tradeable = false;
      if (eventShockTrigger) regimeBlockers.push("event_shock_lockout");
      signalValue = (abnormalRange && volumeShock)
        ? Math.min(1, 0.62 + Math.min((volumeRatio || 0) / 6, 0.22))
        : 0;
    }

    if (eventShockTrigger) {
      eventShockLockoutRemaining = EVENT_SHOCK_LOCKOUT_BARS;
    } else if (eventShockLockoutRemaining > 0) {
      eventShockLockoutRemaining -= 1;
    }

    // --- Profitability filters: regime, HTF trend, session phase ---
    const regimeClassification = computeRegimeClassification({
      atr14, atr14Sma50, ema20, ema50, closes, index,
    });

    const htfEntry = htfSeries[index];

    if (signalValue !== 0 && signalName !== "crypto_event_watch") {
      // Module 1: Regime filter — zero signal when macro regime doesn't match
      if (!isRegimeAllowed(signalName, regimeClassification.regime)) {
        signalValue = 0;
        if (!regimeBlockers.includes("regime_mismatch")) regimeBlockers.push("regime_mismatch");
      }
      // Module 2: HTF trend filter — zero signal when counter-trend on 1h
      if (signalValue !== 0 && isHtfBlocked(signalName, signalValue, htfEntry)) {
        signalValue = 0;
        if (!regimeBlockers.includes("htf_counter_trend")) regimeBlockers.push("htf_counter_trend");
      }
      // Module 3: Session phase multiplier — scale signal strength by phase edge
      if (signalValue !== 0) {
        const phaseMultiplier = getSessionPhaseMultiplier(signalName, barsSinceSessionStart);
        signalValue = signalValue > 0
          ? Math.min(1, signalValue * phaseMultiplier)
          : Math.max(-1, signalValue * phaseMultiplier);
        // If multiplier pushed signal below minimum useful threshold, zero it
        if (Math.abs(signalValue) < 0.35) {
          signalValue = 0;
          if (!regimeBlockers.includes("session_phase_weak")) regimeBlockers.push("session_phase_weak");
        }
      }
    }

    const failedBreakdownState = signalName === "crypto_failed_breakdown_reclaim"
      ? buildFailedBreakdownState({
        index,
        bars,
        lows,
        closes,
        rsi14,
        bollinger20,
        sessionContexts,
        getSessionKey,
      })
      : null;
    const signalSessionVwap = signalName === "crypto_opening_range_breakout"
      ? openingRangeSessionVwap[index]
      : vwap[index];
    const signalSessionContext = signalName === "crypto_opening_range_breakout"
      ? openingRangeSessionContext
      : sessionContext;
    const signalSessionRangeWidth = signalName === "crypto_opening_range_breakout"
      ? openingRangeSessionRangeWidth
      : sessionRangeWidth;
    const signalBarsSinceSessionStart = signalName === "crypto_opening_range_breakout"
      ? (openingRangeContext?.barsSinceSessionStart ?? null)
      : barsSinceSessionStart;

    return {
      ...bar,
      signals: {
        ...(bar.signals || {}),
        [signalName]: round(signalValue, 4),
      },
      indicators: {
        ...(bar.indicators || {}),
        ema20: round(ema20[index], 6),
        ema50: round(ema50[index], 6),
        rsi14: round(rsi14[index], 4),
        bollingerBasis20: round(bollinger20.basis[index], 6),
        bollingerUpper20: round(bollinger20.upper[index], 6),
        bollingerLower20: round(bollinger20.lower[index], 6),
        stochRsiK: round(stochRsi14.k[index], 4),
        stochRsiD: round(stochRsi14.d[index], 4),
        sessionVwap: round(signalSessionVwap, 6),
        sessionRangeHigh: round(signalSessionContext?.sessionHigh, 6),
        sessionRangeLow: round(signalSessionContext?.sessionLow, 6),
        priorSessionHigh: round(signalSessionContext?.priorSessionHigh, 6),
        priorSessionLow: round(signalSessionContext?.priorSessionLow, 6),
        sessionRangeMidpoint: round(signalSessionContext?.sessionRangeMidpoint, 6),
        sessionRangeWidth: round(signalSessionRangeWidth, 6),
        barsSinceSessionStart: signalBarsSinceSessionStart,
        volumeRatio: round(volumeRatio, 4),
        rejectionStrength: round(rejectionStrength, 4),
        pctChange: round(pctChange, 6),
        priorSwingLow: round(priorSwingLow, 6),
        priorSwingLowRsi14: round(priorSwingLowRsi14, 4),
        openingRangeHigh: signalName === "crypto_opening_range_breakout" ? round(openingRangeContext?.openingRangeHigh, 6) : null,
        openingRangeLow: signalName === "crypto_opening_range_breakout" ? round(openingRangeContext?.openingRangeLow, 6) : null,
        openingRangeWidthPct: signalName === "crypto_opening_range_breakout" ? round(openingRangeContext?.openingRangeWidthPct, 6) : null,
        openingRangeComplete: signalName === "crypto_opening_range_breakout" ? openingRangeContext?.openingRangeComplete === true : null,
        openingRangeVariant: signalName === "crypto_opening_range_breakout"
          ? String(strategy.metadata?.openingRangeVariant || "breakout_close")
          : null,
        bullishRsiDivergence: signalName === "crypto_bottom_reclaim" ? bullishRsiDivergence : null,
        bottomReclaimLowerBandTouched: signalName === "crypto_bottom_reclaim" ? Number.isFinite(bollinger20.lower[index]) && lows[index] <= (bollinger20.lower[index] * 1.005) : null,
        bottomReclaimStochRecovery: signalName === "crypto_bottom_reclaim"
          ? (
            Number.isFinite(stochRsi14.k[index]) &&
            Number.isFinite(stochRsi14.k[index - 1]) &&
            stochRsi14.k[index] > stochRsi14.k[index - 1] &&
            stochRsi14.k[index - 1] <= 35 &&
            stochRsi14.k[index] <= 75
          )
          : null,
        bottomReclaimVolumeRamp: signalName === "crypto_bottom_reclaim"
          ? (
            index >= 3 &&
            (
              (volumes[index - 2] > volumes[index - 3] && volumes[index - 1] > volumes[index - 2] && volumes[index] > volumes[index - 1]) ||
              (volumes[index] > volumes[index - 1] && volumes[index - 1] > volumes[index - 3])
            )
          )
          : null,
        brokenReferenceLevel: signalName === "crypto_failed_breakdown_reclaim" ? round(failedBreakdownState?.brokenReferenceLevel, 6) : null,
        brokenReferenceKind: signalName === "crypto_failed_breakdown_reclaim" ? failedBreakdownState?.brokenReferenceKind || null : null,
        breakdownDepthPct: signalName === "crypto_failed_breakdown_reclaim" ? round(failedBreakdownState?.breakdownDepthPct, 6) : null,
        reclaimCloseConfirmed: signalName === "crypto_failed_breakdown_reclaim" ? failedBreakdownState?.reclaimCloseConfirmed === true : null,
        reclaimHoldConfirmed: signalName === "crypto_failed_breakdown_reclaim" ? failedBreakdownState?.reclaimHoldConfirmed === true : null,
        // Order flow indicators
        barDelta: round(barDelta[index], 2),
        sessionCvd: round(sessionCvd[index], 2),
        cvd14: round(cvd14[index], 2),
        buyPressure: round(buyPressure[index], 4),
        deltaEma8: round(deltaEma8[index], 2),
        deltaEma20: round(deltaEma20[index], 2),
        takerBuyVol: round(takerBuyVol[index], 2),
        takerSellVol: round(takerSellVol[index], 2),
        atr14: round(atr14[index], 6),
        // Profitability Module 1: Regime classification
        marketRegime: regimeClassification.regime,
        marketRegimeStrength: regimeClassification.regimeStrength,
        atrPercentile: regimeClassification.atrPercentile,
        trendStrength: regimeClassification.trendStrength,
        trendDirection: regimeClassification.trendDirection,
        // Profitability Module 2: Higher-timeframe trend
        htfTrend: htfEntry?.htfTrend || null,
        htfEmaFast: round(htfEntry?.htfEmaFast, 6),
        htfEmaSlow: round(htfEntry?.htfEmaSlow, 6),
        htfRsi: round(htfEntry?.htfRsi, 4),
        // Profitability Module 3: Session phase
        sessionPhase: classifySessionPhase(barsSinceSessionStart),
        sessionPhaseMultiplier: round(getSessionPhaseMultiplier(signalName, barsSinceSessionStart), 4),
        regimeState,
        tradeable,
        regimeBlockers,
        eventShockLockoutActive: eventShockBlocked,
      },
      sessionKey,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
      marketType: DEFAULT_MARKET_TYPE,
      sessionMode: config.sessionMode,
      windowMode: normalizedWindowMode,
      alertWindows: clone(config.alertWindows),
      window,
    };
  });
}

function normalizeBinanceKline(symbol, row) {
  const openTimeMs = Number(row?.[0]);
  const closeTimeMs = Number(row?.[6]);
  return {
    timestamp: new Date(openTimeMs).toISOString(),
    symbol,
    open: round(Number(row?.[1])),
    high: round(Number(row?.[2])),
    low: round(Number(row?.[3])),
    close: round(Number(row?.[4])),
    volume: round(Number(row?.[5])),
    closeTime: Number.isFinite(closeTimeMs) ? new Date(closeTimeMs).toISOString() : null,
    quoteVolume: round(Number(row?.[7])),
    tradeCount: Number(row?.[8]) || 0,
    takerBuyBaseVolume: round(Number(row?.[9])),
    takerBuyQuoteVolume: round(Number(row?.[10])),
  };
}

async function fetchBinanceKlinesPage(options = {}) {
  const params = new URLSearchParams({
    symbol: String(options.symbol || "").toUpperCase(),
    interval: String(options.interval || DEFAULT_INTERVAL),
    limit: String(Math.max(1, Math.min(1000, Number(options.limit) || 1000))),
  });
  if (Number.isFinite(options.startTime)) params.set("startTime", String(Math.floor(options.startTime)));
  if (Number.isFinite(options.endTime)) params.set("endTime", String(Math.floor(options.endTime)));

  let lastError = null;
  for (const root of BINANCE_API_ROOTS) {
    try {
      const payload = await httpJson(`${root}/api/v3/klines?${params.toString()}`);
      if (!Array.isArray(payload)) {
        throw new Error("Unexpected Binance klines payload");
      }
      return payload;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Failed to fetch Binance klines");
}

function parseBinanceCsvBars(csvText, symbol) {
  return String(csvText || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(","))
    .filter((columns) => columns.length >= 11)
    .map((columns) => normalizeBinanceKline(symbol, columns));
}

function parseImportedCsvFiles(symbol, filePaths) {
  const bars = [];
  for (const filePath of filePaths) {
    bars.push(...parseBinanceCsvBars(fs.readFileSync(filePath, "utf8"), symbol));
  }
  return bars;
}

async function importHistoryForSymbol(options = {}) {
  const symbol = String(options.symbol || "").toUpperCase();
  if (!symbol) throw new Error("importHistoryForSymbol requires a symbol");
  const minutes = Math.max(60, Number(options.minutes) || (DEFAULT_CRYPTO_DAY_TRADING_CONFIG.importLookbackDays * 24 * 60));
  const inputPaths = normalizeCsvPathInput(options.input);
  const rawRecords = [];
  let importedBars = [];
  let source = "binance_spot_api";

  if (inputPaths.length > 0) {
    importedBars = parseImportedCsvFiles(symbol, inputPaths);
    source = "binance_spot_csv";
  } else {
    let collected = [];
    let endTime = Number(options.endTime) || Date.now();
    let pageIndex = 0;
    while (collected.length < minutes) {
      const remaining = minutes - collected.length;
      const limit = Math.min(1000, remaining);
      const page = await fetchBinanceKlinesPage({
        symbol,
        interval: DEFAULT_INTERVAL,
        endTime: endTime - 1,
        limit,
      });
      if (!Array.isArray(page) || page.length === 0) break;
      rawRecords.push({
        fetchedAt: nowIso(),
        pageIndex,
        request: { symbol, endTime, limit },
        page,
      });
      const normalized = page.map((row) => normalizeBinanceKline(symbol, row));
      collected = mergeBars(normalized, collected);
      const firstTimestamp = normalized[0]?.timestamp;
      if (!firstTimestamp) break;
      endTime = new Date(firstTimestamp).getTime();
      pageIndex += 1;
      if (page.length < limit) break;
      await sleep(60);
    }
    importedBars = collected.slice(-minutes);
  }

  const existingBars = loadNormalizedBars(symbol);
  const mergedBars = mergeBars(existingBars, importedBars);
  saveNormalizedBars(symbol, mergedBars, {
    source,
    importedAt: nowIso(),
    inputPaths,
  });
  const derivedBars = resampleOneMinuteBarsToFiveMinutes(mergedBars);
  saveDerivedBars(symbol, DEFAULT_TIMEFRAME, derivedBars);

  if (rawRecords.length > 0) {
    ensureDir(path.join(RAW_DOWNLOADS_DIR, symbol));
    atomicWriteJsonSync(path.join(RAW_DOWNLOADS_DIR, symbol, `${Date.now()}-api-pages.json`), {
      savedAt: nowIso(),
      symbol,
      source,
      pages: rawRecords,
    });
  }

  return {
    symbol,
    source,
    importedBars: importedBars.length,
    totalBars: mergedBars.length,
    derivedBars: derivedBars.length,
    startTimestamp: mergedBars[0]?.timestamp || null,
    endTimestamp: mergedBars[mergedBars.length - 1]?.timestamp || null,
    inputPaths,
  };
}

async function importCryptoDayTradingHistory(options = {}) {
  const symbols = Array.isArray(options.symbols) && options.symbols.length > 0
    ? options.symbols.map((symbol) => String(symbol).toUpperCase())
    : DEFAULT_SYMBOLS.slice();
  const minutes = Math.max(60, Number(options.minutes) || ((Number(options.days) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.importLookbackDays) * 24 * 60));
  const inputMap = options.inputMap || {};
  const results = [];

  for (const symbol of symbols) {
    results.push(await importHistoryForSymbol({
      symbol,
      minutes,
      input: inputMap[symbol] || options.input,
      endTime: options.endTime,
    }));
  }

  const summary = {
    generatedAt: nowIso(),
    market: DEFAULT_MARKET,
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    interval: DEFAULT_INTERVAL,
    symbols,
    minutes,
    results,
  };
  atomicWriteJsonSync(IMPORT_REPORT_PATH, summary);
  return summary;
}

async function fetchRecentLiveOneMinuteBars(symbol, minutes = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.livePollMinutes) {
  const page = await fetchBinanceKlinesPage({
    symbol,
    interval: DEFAULT_INTERVAL,
    limit: Math.max(60, Math.min(1000, Number(minutes) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.livePollMinutes)),
  });
  return {
    source: "binance_spot_live_poll",
    symbol,
    bars: page.map((row) => normalizeBinanceKline(symbol, row)),
  };
}

function buildMarketSnapshotFromBars(symbol, rawBars, lastDerivedBar) {
  const lastRawBar = rawBars[rawBars.length - 1] || null;
  const referenceBar = lastDerivedBar || lastRawBar;
  if (!referenceBar) {
    return {
      bestBid: null,
      bestAsk: null,
      volume: 0,
      volumeUsd: 0,
      availableLiquidityUsd: 0,
    };
  }

  const close = Number(referenceBar.close || 0);
  const spreadFraction = symbol === "SOLUSDT" ? 0.0009 : 0.0005;
  const quoteVolume = Number(lastRawBar?.quoteVolume || referenceBar.quoteVolume || 0);
  return {
    bestBid: round(close * (1 - (spreadFraction / 2))),
    bestAsk: round(close * (1 + (spreadFraction / 2))),
    volume: Number(referenceBar.volume || 0),
    volumeUsd: Number.isFinite(quoteVolume) && quoteVolume > 0
      ? round(quoteVolume)
      : round(Number(referenceBar.volume || 0) * close),
    availableLiquidityUsd: round((Number.isFinite(quoteVolume) && quoteVolume > 0 ? quoteVolume : (Number(referenceBar.volume || 0) * close)) * 0.08),
  };
}

function unavailableBacktest(strategyId, reason) {
  return {
    strategyId,
    generatedAt: nowIso(),
    assumptions: { reason },
    trades: [],
    equityCurve: [],
    maxDrawdownFraction: 0,
    summary: {
      tradeCount: 0,
      eligibleForPromotion: false,
      totalNetReturnFraction: 0,
      maxDrawdownFraction: 0,
      winRate: 0,
      profitFactor: 0,
      averageHoldBars: null,
      medianHoldBars: null,
      slippageAdjustedReturnFraction: 0,
      vetoReasons: [reason],
    },
  };
}

function applyPromotionDecision(strategy, decision, timestamp = nowIso()) {
  if (!decision || !decision.nextStatus) return strategy;
  const metadata = strategy.metadata || {};
  const history = Array.isArray(metadata.stageHistory) ? metadata.stageHistory.slice() : [];
  if (decision.changed) {
    history.push({
      from: decision.currentStatus,
      to: decision.nextStatus,
      reason: decision.reason,
      at: timestamp,
    });
  }
  return {
    ...strategy,
    status: decision.nextStatus,
    metadata: {
      ...metadata,
      lastPromotionDecision: {
        reason: decision.reason,
        at: timestamp,
      },
      stageHistory: history,
    },
  };
}

async function loadCryptoMarketDataForStrategy(strategy, options = {}) {
  const symbol = String(strategy.marketUniverse?.symbols?.[0] || "").toUpperCase();
  const requestedBars = normalizeBarsSelection(options.bars, DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars);
  const windowMode = normalizeWindowMode(options.windowMode, DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode);
  const persistArtifacts = options.persistArtifacts !== false && options.readOnly !== true;
  const importedBars = loadNormalizedBars(symbol);
  const rawBarsNeeded = requestedBars === "all"
    ? importedBars.length
    : Math.max((requestedBars * 5) + 50, 1000);
  let rawBars = requestedBars === "all"
    ? importedBars.slice()
    : importedBars.slice(-rawBarsNeeded);
  let warning = null;
  let source = "binance_spot_imported_1m";
  let trusted = true;

  if (options.includeLive !== false) {
    try {
      const live = await fetchRecentLiveOneMinuteBars(symbol, options.livePollMinutes || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.livePollMinutes);
      rawBars = mergeBars(rawBars, live.bars);
      if (persistArtifacts && rawBars.length > 0) {
        saveNormalizedBars(symbol, mergeBars(importedBars, live.bars), {
          source: "binance_spot_imported_plus_live",
          liveUpdatedAt: nowIso(),
        });
      }
      source = importedBars.length > 0 ? "binance_spot_imported_plus_live" : "binance_spot_live_only";
    } catch (error) {
      warning = `live_poll_failed:${error instanceof Error ? error.message : "unknown"}`;
      if (importedBars.length === 0) {
        trusted = false;
        source = "binance_spot_live_unavailable";
      }
    }
  }

  if (rawBars.length === 0) {
    return {
      source: "missing_crypto_history",
      warning: warning || "missing_imported_history",
      trusted: false,
      symbol,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
      marketType: DEFAULT_MARKET_TYPE,
      sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      windowMode,
      alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
      marketSnapshot: buildMarketSnapshotFromBars(symbol, [], null),
      rawBarCount: 0,
      derivedBarCount: 0,
      importedBarCount: importedBars.length,
      importedStartTimestamp: importedBars[0]?.timestamp || null,
      importedEndTimestamp: importedBars[importedBars.length - 1]?.timestamp || null,
      usedStartTimestamp: null,
      usedEndTimestamp: null,
      priceSeries: [],
    };
  }

  if (importedBars.length < rawBarsNeeded && source !== "binance_spot_imported_plus_live") {
    warning = warning || `limited_imported_history:${importedBars.length}<${rawBarsNeeded}`;
    trusted = false;
  }

  const derivedBars = resampleOneMinuteBarsToFiveMinutes(rawBars);
  const selectedDerivedBars = requestedBars === "all"
    ? derivedBars
    : derivedBars.slice(-requestedBars);
  const enrichedBars = enrichBarsWithSignals(
    selectedDerivedBars,
    strategy,
    DEFAULT_CRYPTO_DAY_TRADING_CONFIG,
    windowMode,
  );
  if (persistArtifacts) {
    saveDerivedBars(symbol, DEFAULT_TIMEFRAME, enrichedBars, windowMode);
  }
  const lastBar = enrichedBars[enrichedBars.length - 1] || null;

  return {
    source,
    warning,
    trusted,
    symbol,
    market: DEFAULT_MARKET,
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    windowMode,
    alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
    marketSnapshot: buildMarketSnapshotFromBars(symbol, rawBars, lastBar),
    rawBarCount: rawBars.length,
    derivedBarCount: enrichedBars.length,
    importedBarCount: importedBars.length,
    importedStartTimestamp: importedBars[0]?.timestamp || null,
    importedEndTimestamp: importedBars[importedBars.length - 1]?.timestamp || null,
    usedStartTimestamp: enrichedBars[0]?.timestamp || rawBars[0]?.timestamp || null,
    usedEndTimestamp: lastBar?.timestamp || rawBars[rawBars.length - 1]?.timestamp || null,
    barsRequested: requestedBars,
    priceSeries: enrichedBars,
  };
}

function calculateBarAgeMinutes(latestTimestamp, nowTimestamp) {
  const latestMs = latestTimestamp ? new Date(latestTimestamp).getTime() : NaN;
  const nowMs = nowTimestamp ? new Date(nowTimestamp).getTime() : NaN;
  if (!Number.isFinite(latestMs) || !Number.isFinite(nowMs)) return null;
  return round(Math.max(0, (nowMs - latestMs) / 60000), 3);
}

function scoreWatchlistEvidence(scoreboardItem) {
  const backtest = scoreboardItem?.backtest || {};
  const paper = scoreboardItem?.paper || {};
  const eligible = backtest.eligibleForPromotion === true;
  const winRate = Number(backtest.winRate || 0);
  const profitFactor = Number(backtest.profitFactor || 0);
  const tradeCount = Number(backtest.tradeCount || 0);
  const totalReturn = Number(backtest.totalNetReturnFraction || 0);
  const paperPnl = Number((paper.realizedPnl || 0) + (paper.unrealizedPnl || 0));
  const scoreboardScore = Number(scoreboardItem?.score || 0);

  return (
    (eligible ? 1000 : 0) +
    (winRate * 200) +
    (Math.min(profitFactor, 5) * 50) +
    Math.min(tradeCount, 50) +
    (totalReturn * 1000) +
    (paperPnl / 25) +
    scoreboardScore
  );
}

function scorePilotWatchlistCandidate(options = {}) {
  const strategy = options.strategy || {};
  const candidate = options.candidate || {};
  const todayGate = options.todayGate || {};
  const tradeable = options.tradeable === true;
  const trusted = options.trusted !== false;
  const dataFresh = options.dataFresh === true;
  const alertEligible = options.alertEligible === true;
  const barsSinceTrigger = Number.isFinite(Number(options.barsSinceTrigger)) ? Number(options.barsSinceTrigger) : null;
  const currentSignalValue = Number(options.currentSignalValue || 0);
  const signalThreshold = Number(options.signalThreshold || 0);
  const regimeBlockers = Array.isArray(options.regimeBlockers) ? options.regimeBlockers : [];
  const notes = [];
  let score = Number(candidate.evidenceScore || scoreWatchlistEvidence(candidate));

  if (String(strategy.strategyId || "") === BTC_PROFITABILITY_SETUP_ID) {
    score += 450;
    notes.push("phase_1_btc");
  } else if (String(strategy.metadata?.unlockPhase || "") !== "phase_1") {
    score -= 120;
    notes.push("locked_phase");
  }

  if (trusted) {
    score += 180;
    notes.push("trusted_data");
  } else {
    score -= 600;
  }

  if (dataFresh) {
    score += 120;
    notes.push("fresh_bars");
  } else {
    score -= 180;
  }

  if (tradeable) {
    score += 260;
    notes.push("tradeable_now");
  } else if (regimeBlockers.length > 0) {
    score -= Math.min(180, regimeBlockers.length * 45);
  }

  if (alertEligible) {
    score += 120;
    notes.push("replay_eligible");
  }

  if (barsSinceTrigger != null) {
    score += Math.max(0, 180 - (barsSinceTrigger * 45));
    if (barsSinceTrigger <= 1) {
      notes.push("recent_trigger");
    }
  }

  if (signalThreshold > 0) {
    if (currentSignalValue >= signalThreshold) {
      score += 90;
    } else {
      const gap = Math.max(0, signalThreshold - currentSignalValue);
      score += Math.max(0, 50 - (gap * 100));
    }
  }

  const candidateStatus = String(candidate.status || "");
  if (candidateStatus === "candidate_live") score += 120;
  else if (candidateStatus === "promotion_review") score += 70;
  else if (candidateStatus === "paper_live") score += 40;
  else if (candidateStatus === "backtest_failed") score -= 140;

  if (String(strategy.strategyId || "") === BTC_PROFITABILITY_SETUP_ID) {
    if (Number(todayGate.remainingApprovals || 0) > 0) {
      score += 110;
      notes.push("approval_slots_open");
    } else {
      score -= 260;
    }
  }

  return {
    pilotPriorityScore: round(score, 4),
    rankingNotes: notes.slice(0, 4),
  };
}

function compareWatchlistCandidates(left, right) {
  const leftPilotPriority = Number(left?.pilotPriorityScore || 0);
  const rightPilotPriority = Number(right?.pilotPriorityScore || 0);
  if (rightPilotPriority !== leftPilotPriority) return rightPilotPriority - leftPilotPriority;

  const leftBacktest = left?.backtest || {};
  const rightBacktest = right?.backtest || {};
  const leftEligible = leftBacktest.eligibleForPromotion === true ? 1 : 0;
  const rightEligible = rightBacktest.eligibleForPromotion === true ? 1 : 0;
  if (rightEligible !== leftEligible) return rightEligible - leftEligible;

  const leftWinRate = Number(leftBacktest.winRate || 0);
  const rightWinRate = Number(rightBacktest.winRate || 0);
  if (rightWinRate !== leftWinRate) return rightWinRate - leftWinRate;

  const leftProfitFactor = Number(leftBacktest.profitFactor || 0);
  const rightProfitFactor = Number(rightBacktest.profitFactor || 0);
  if (rightProfitFactor !== leftProfitFactor) return rightProfitFactor - leftProfitFactor;

  const leftTradeCount = Number(leftBacktest.tradeCount || 0);
  const rightTradeCount = Number(rightBacktest.tradeCount || 0);
  if (rightTradeCount !== leftTradeCount) return rightTradeCount - leftTradeCount;

  return Number(right?.score || 0) - Number(left?.score || 0);
}

function buildWatchlistPriorityProfile(item, context = {}) {
  const reasons = [];
  const pilotSummary = context.pilotSummary || null;
  const todayGate = context.todayGate || null;
  const prioritySignals = {
    trustedData: item.currentDataTrusted === true,
    dataFresh: item.dataFresh === true,
    tradeable: item.tradeable === true,
    notifyNow: item.notifyNow === true,
    alertEligible: item.alertEligible === true,
    approvalSlotsRemaining: Number(item.approvalSlotsRemaining ?? todayGate?.remainingApprovals ?? 0),
    barsSinceTrigger: Number.isFinite(Number(item.barsSinceTrigger)) ? Number(item.barsSinceTrigger) : null,
    signalGap: Number.isFinite(Number(item.currentSignalValue)) && Number.isFinite(Number(item.signalThreshold))
      ? round(Number(item.currentSignalValue) - Number(item.signalThreshold), 4)
      : null,
    regimeBlockers: Array.isArray(item.regimeBlockers) ? item.regimeBlockers.slice() : [],
    liveStatus: String(item.liveStatus || ""),
    strategyType: item.strategyId === BTC_PROFITABILITY_SETUP_ID ? "pilot" : "candidate",
  };

  let score = Number(item.evidenceScore || 0) * 0.25 + Number(item.score || 0) * 0.1;

  if (prioritySignals.trustedData) {
    score += 120;
    reasons.push("trusted_data");
  } else {
    score -= 240;
    reasons.push("untrusted_data");
  }

  if (prioritySignals.dataFresh) {
    score += 90;
    reasons.push("fresh_data");
  } else {
    score -= 180;
    reasons.push("stale_data");
  }

  if (prioritySignals.tradeable) {
    score += 120;
    reasons.push("tradeable");
  } else {
    score -= 180;
    reasons.push("not_tradeable");
  }

  if (prioritySignals.notifyNow) {
    score += 180;
    reasons.push("notify_now");
  } else if (prioritySignals.alertEligible) {
    score += 60;
    reasons.push("alert_eligible");
  } else {
    score -= 20;
  }

  if (prioritySignals.approvalSlotsRemaining > 0) {
    score += 80;
    reasons.push("approval_slots_available");
  } else if (item.strategyId === BTC_PROFITABILITY_SETUP_ID) {
    score -= 240;
    reasons.push("approval_slots_exhausted");
  }

  if (prioritySignals.strategyType === "pilot") {
    score += 120;
    reasons.push("btc_pilot");
  } else {
    score -= 30;
  }

  if (prioritySignals.liveStatus === "triggered_now") {
    score += 160;
    reasons.push("triggered_now");
  } else if (prioritySignals.liveStatus === "triggered_recently") {
    score += 120;
    reasons.push("triggered_recently");
  } else if (prioritySignals.liveStatus === "triggered_this_window") {
    score += 70;
    reasons.push("triggered_this_window");
  } else if (prioritySignals.liveStatus === "tracking") {
    score += 40;
    reasons.push("tracking");
  } else if (String(prioritySignals.liveStatus).startsWith("blocked")) {
    score -= 80;
    reasons.push(prioritySignals.liveStatus);
  }

  for (const blocker of prioritySignals.regimeBlockers) {
    switch (String(blocker)) {
      case "event_shock_lockout":
        score -= 180;
        break;
      case "expansion":
        score -= 120;
        break;
      case "mid_range":
        score -= 90;
        break;
      case "timing_not_ready":
        score -= 70;
        break;
      case "range_not_ready":
        score -= 60;
        break;
      default:
        score -= 40;
        break;
    }
    reasons.push(`blocker:${blocker}`);
  }

  if (prioritySignals.signalGap != null) {
    if (prioritySignals.signalGap >= 0.12) {
      score += 50;
      reasons.push("signal_above_threshold");
    } else if (prioritySignals.signalGap >= 0) {
      score += 25;
    } else {
      score -= 20;
      reasons.push("signal_below_threshold");
    }
  }

  if (prioritySignals.barsSinceTrigger != null) {
    const barsSinceTrigger = Math.max(0, Math.min(25, prioritySignals.barsSinceTrigger));
    score += Math.max(0, 35 - (barsSinceTrigger * 1.4));
  }

  const executionStats = pilotSummary?.executionStats || {};
  if (Number.isFinite(Number(executionStats.makerShare))) {
    score += (Number(executionStats.makerShare) - 0.5) * 70;
  }
  if (Number.isFinite(Number(executionStats.averageEntrySlippageBps))) {
    score -= Math.min(Math.max(Number(executionStats.averageEntrySlippageBps), 0), 10) * 3;
  }
  if (Number.isFinite(Number(executionStats.averageExitSlippageBps))) {
    score -= Math.min(Math.max(Number(executionStats.averageExitSlippageBps), 0), 10) * 2;
  }
  if (Number.isFinite(Number(executionStats.stopSlipRate))) {
    score -= Number(executionStats.stopSlipRate) * 80;
  }

  const ruleAdherenceRate = pilotSummary?.journalStats?.ruleAdherenceRate;
  if (Number.isFinite(Number(ruleAdherenceRate))) {
    score += (Number(ruleAdherenceRate) - 0.85) * 160;
  }

  const disqualificationCount = Number(pilotSummary?.journalStats?.disqualifiedTradeCount || 0);
  if (disqualificationCount > 0) {
    score -= Math.min(disqualificationCount, 20) * 1.5;
  }

  const realizedPnl = Number(item.paperEvidence?.realizedPnl || 0) + Number(item.paperEvidence?.unrealizedPnl || 0);
  if (realizedPnl > 0) {
    score += Math.min(realizedPnl / 25, 30);
  } else if (realizedPnl < 0) {
    score += Math.max(realizedPnl / 25, -30);
  }

  return {
    priorityScore: round(score, 4),
    priorityReasons: [...new Set(reasons)],
    prioritySignals,
  };
}

function comparePilotAwareWatchlistCandidates(left, right) {
  const leftPriority = Number(left?.priorityScore || 0);
  const rightPriority = Number(right?.priorityScore || 0);
  if (rightPriority !== leftPriority) return rightPriority - leftPriority;

  const leftNotify = left?.notifyNow === true ? 1 : 0;
  const rightNotify = right?.notifyNow === true ? 1 : 0;
  if (rightNotify !== leftNotify) return rightNotify - leftNotify;

  const leftEligible = left?.alertEligible === true ? 1 : 0;
  const rightEligible = right?.alertEligible === true ? 1 : 0;
  if (rightEligible !== leftEligible) return rightEligible - leftEligible;

  const leftTradeable = left?.tradeable === true ? 1 : 0;
  const rightTradeable = right?.tradeable === true ? 1 : 0;
  if (rightTradeable !== leftTradeable) return rightTradeable - leftTradeable;

  const leftTrusted = left?.currentDataTrusted === true ? 1 : 0;
  const rightTrusted = right?.currentDataTrusted === true ? 1 : 0;
  if (rightTrusted !== leftTrusted) return rightTrusted - leftTrusted;

  const leftFresh = left?.dataFresh === true ? 1 : 0;
  const rightFresh = right?.dataFresh === true ? 1 : 0;
  if (rightFresh !== leftFresh) return rightFresh - leftFresh;

  const leftSlots = Number(left?.approvalSlotsRemaining ?? 0);
  const rightSlots = Number(right?.approvalSlotsRemaining ?? 0);
  if (rightSlots !== leftSlots) return rightSlots - leftSlots;

  const leftSignal = Number(left?.currentSignalValue || 0);
  const rightSignal = Number(right?.currentSignalValue || 0);
  if (rightSignal !== leftSignal) return rightSignal - leftSignal;

  return compareWatchlistCandidates(left, right);
}

function getTradePnlFraction(trade) {
  return Number(trade?.pnlFractionOfEquity ?? trade?.netReturnFraction ?? 0);
}

function aggregateTradeCollection(trades = []) {
  const normalizedTrades = Array.isArray(trades) ? trades : [];
  let grossProfit = 0;
  let grossLoss = 0;
  let netPnlFraction = 0;
  let wins = 0;

  for (const trade of normalizedTrades) {
    const pnl = getTradePnlFraction(trade);
    if (!Number.isFinite(pnl)) continue;
    netPnlFraction += pnl;
    if (pnl > 0) {
      grossProfit += pnl;
      wins += 1;
    } else if (pnl < 0) {
      grossLoss += Math.abs(pnl);
    }
  }

  return {
    tradeCount: normalizedTrades.length,
    winRate: normalizedTrades.length > 0 ? round(wins / normalizedTrades.length, 4) : 0,
    grossProfitFraction: round(grossProfit),
    grossLossFraction: round(grossLoss),
    netPnlFraction: round(netPnlFraction),
    profitFactor: grossLoss === 0 ? (grossProfit > 0 ? null : 0) : round(grossProfit / grossLoss),
  };
}

function buildTradeBreakdown(trades = [], keyBuilder) {
  const buckets = new Map();
  const normalizedTrades = Array.isArray(trades) ? trades : [];
  for (const trade of normalizedTrades) {
    const key = keyBuilder(trade);
    if (!key) continue;
    const pnl = getTradePnlFraction(trade);
    const bucket = buckets.get(key) || { key, tradeCount: 0, netPnlFraction: 0 };
    bucket.tradeCount += 1;
    bucket.netPnlFraction += Number.isFinite(pnl) ? pnl : 0;
    buckets.set(key, bucket);
  }

  const totalNetPnlFraction = [...buckets.values()].reduce((sum, bucket) => sum + bucket.netPnlFraction, 0);
  const totalAbsolutePnlFraction = [...buckets.values()].reduce((sum, bucket) => sum + Math.abs(bucket.netPnlFraction), 0);
  return [...buckets.values()]
    .map((bucket) => ({
      key: bucket.key,
      tradeCount: bucket.tradeCount,
      netPnlFraction: round(bucket.netPnlFraction),
      pnlShare: totalNetPnlFraction === 0 ? null : round(bucket.netPnlFraction / totalNetPnlFraction, 4),
      pnlAbsoluteShare: totalAbsolutePnlFraction === 0 ? null : round(Math.abs(bucket.netPnlFraction) / totalAbsolutePnlFraction, 4),
    }))
    .sort((left, right) => (
      Math.abs(Number(right.netPnlFraction || 0)) - Math.abs(Number(left.netPnlFraction || 0)) ||
      Number(right.tradeCount || 0) - Number(left.tradeCount || 0) ||
      String(left.key).localeCompare(String(right.key))
    ));
}

function buildMarketDataUsageSummary(bundles = []) {
  const uniqueContexts = new Map();
  for (const bundle of bundles) {
    const key = `${bundle.symbol || "unknown"}::${bundle.windowMode || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode}`;
    if (uniqueContexts.has(key)) continue;
    uniqueContexts.set(key, {
      symbol: bundle.symbol || null,
      windowMode: bundle.windowMode || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      rawBarCount: Number(bundle.rawBarCount || 0),
      derivedBarCount: Number(bundle.derivedBarCount || 0),
      importedBarCount: Number(bundle.importedBarCount || 0),
      importedStartTimestamp: bundle.importedStartTimestamp || null,
      importedEndTimestamp: bundle.importedEndTimestamp || null,
      usedStartTimestamp: bundle.usedStartTimestamp || null,
      usedEndTimestamp: bundle.usedEndTimestamp || null,
    });
  }

  const contexts = [...uniqueContexts.values()];
  const startTimestamps = contexts.map((item) => item.usedStartTimestamp || item.importedStartTimestamp).filter(Boolean);
  const endTimestamps = contexts.map((item) => item.usedEndTimestamp || item.importedEndTimestamp).filter(Boolean);
  const startMs = startTimestamps.map((timestamp) => new Date(timestamp).getTime()).filter(Number.isFinite);
  const endMs = endTimestamps.map((timestamp) => new Date(timestamp).getTime()).filter(Number.isFinite);
  const importedSpanDays = startMs.length > 0 && endMs.length > 0
    ? round((Math.max(...endMs) - Math.min(...startMs)) / (24 * 60 * 60 * 1000), 2)
    : null;

  const bySymbol = {};
  const byWindowMode = {};
  for (const context of contexts) {
    bySymbol[context.symbol] = {
      rawBarCount: (bySymbol[context.symbol]?.rawBarCount || 0) + context.rawBarCount,
      derivedBarCount: (bySymbol[context.symbol]?.derivedBarCount || 0) + context.derivedBarCount,
      importedBarCount: (bySymbol[context.symbol]?.importedBarCount || 0) + context.importedBarCount,
    };
    byWindowMode[context.windowMode] = {
      rawBarCount: (byWindowMode[context.windowMode]?.rawBarCount || 0) + context.rawBarCount,
      derivedBarCount: (byWindowMode[context.windowMode]?.derivedBarCount || 0) + context.derivedBarCount,
      importedBarCount: (byWindowMode[context.windowMode]?.importedBarCount || 0) + context.importedBarCount,
    };
  }

  return {
    importedSpanUsed: {
      startTimestamp: startTimestamps.length > 0 ? new Date(Math.min(...startMs)).toISOString() : null,
      endTimestamp: endTimestamps.length > 0 ? new Date(Math.max(...endMs)).toISOString() : null,
      spanDays: importedSpanDays,
    },
    raw1mBarCountUsed: contexts.reduce((sum, item) => sum + item.rawBarCount, 0),
    derived5mBarCountUsed: contexts.reduce((sum, item) => sum + item.derivedBarCount, 0),
    imported1mBarCountUsed: contexts.reduce((sum, item) => sum + item.importedBarCount, 0),
    bySymbol,
    byWindowMode,
  };
}

function scoreControlBundle(bundle) {
  const summary = bundle?.summary || {};
  return round(
    (bundle?.trustedMarketData === true ? 1000 : -1000) +
    (Number(summary.totalNetReturnFraction || 0) * 100000) +
    (Number(summary.profitFactor || 0) * 100) +
    (Number(summary.winRate || 0) * 100) +
    Math.min(Number(summary.tradeCount || 0), 60) -
    (Number(summary.maxDrawdownFraction || 0) * 1000),
    4,
  );
}

function compareControlBundles(left, right) {
  const leftTrusted = left?.trustedMarketData === true ? 1 : 0;
  const rightTrusted = right?.trustedMarketData === true ? 1 : 0;
  if (rightTrusted !== leftTrusted) return rightTrusted - leftTrusted;

  const leftSummary = left?.summary || {};
  const rightSummary = right?.summary || {};
  const leftReturn = Number(leftSummary.totalNetReturnFraction || 0);
  const rightReturn = Number(rightSummary.totalNetReturnFraction || 0);
  if (rightReturn !== leftReturn) return rightReturn - leftReturn;

  const leftProfitFactor = Number(leftSummary.profitFactor || 0);
  const rightProfitFactor = Number(rightSummary.profitFactor || 0);
  if (rightProfitFactor !== leftProfitFactor) return rightProfitFactor - leftProfitFactor;

  const leftTradeCount = Number(leftSummary.tradeCount || 0);
  const rightTradeCount = Number(rightSummary.tradeCount || 0);
  if (rightTradeCount !== leftTradeCount) return rightTradeCount - leftTradeCount;

  return String(left?.strategyId || "").localeCompare(String(right?.strategyId || ""));
}

function buildFamilyRollup(strategyFamily, windowMode, bundles = []) {
  const trades = bundles.flatMap((bundle) => (bundle.backtest?.trades || []).map((trade) => ({
    ...trade,
    windowMode: bundle.windowMode,
  })));
  const stats = aggregateTradeCollection(trades);
  const tradesBySymbol = buildTradeBreakdown(trades, (trade) => trade.symbol || "unknown");
  const tradesByWindowMode = buildTradeBreakdown(trades, (trade) => trade.windowMode || windowMode || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode);
  const clusterBreakdown = buildTradeBreakdown(trades, (trade) => `${trade.symbol || "unknown"}::${trade.windowMode || windowMode || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode}`);
  const positiveSymbols = tradesBySymbol.filter((item) => Number(item.netPnlFraction || 0) > 0).length;
  const positiveWindowModes = tradesByWindowMode.filter((item) => Number(item.netPnlFraction || 0) > 0).length;
  const dominantClusterShare = clusterBreakdown.length > 0 ? Number(clusterBreakdown[0].pnlAbsoluteShare || 0) : null;
  const clearlyNegative = Number(stats.netPnlFraction || 0) <= 0 && Number(stats.profitFactor || 0) < 0.5;
  const qualifiesForChallengerBatch = stats.tradeCount >= CRYPTO_FAMILY_CHALLENGER_GATE.minimumTrades && !clearlyNegative;
  const continueCurrentFamily = (
    stats.tradeCount >= CRYPTO_FAMILY_CONTINUE_RULES.minimumTrades &&
    Number(stats.netPnlFraction || 0) > 0 &&
    Number(stats.profitFactor || 0) >= CRYPTO_FAMILY_CONTINUE_RULES.minimumProfitFactor &&
    (positiveSymbols >= 2 || positiveWindowModes >= 2) &&
    (dominantClusterShare == null || dominantClusterShare <= CRYPTO_FAMILY_CONTINUE_RULES.maxDominantClusterShare)
  );

  let holdout = null;
  const timestamps = bundles
    .flatMap((bundle) => [bundle.usedStartTimestamp, bundle.usedEndTimestamp])
    .filter(Boolean)
    .map((timestamp) => new Date(timestamp).getTime())
    .filter(Number.isFinite);
  if (timestamps.length >= 2) {
    const splitMs = Math.min(...timestamps) + ((Math.max(...timestamps) - Math.min(...timestamps)) * 0.7);
    const holdoutTrades = trades.filter((trade) => {
      const entryMs = new Date(trade.entryTimestamp).getTime();
      return Number.isFinite(entryMs) && entryMs >= splitMs;
    });
    holdout = {
      splitTimestamp: new Date(splitMs).toISOString(),
      ...aggregateTradeCollection(holdoutTrades),
      positive: Number(aggregateTradeCollection(holdoutTrades).netPnlFraction || 0) > 0,
    };
  }

  return {
    strategyFamily,
    windowMode,
    windowModeLabel: getWindowModeLabel(windowMode),
    strategyCount: bundles.length,
    symbolCount: [...new Set(bundles.map((bundle) => bundle.symbol).filter(Boolean))].length,
    tradeCount: stats.tradeCount,
    aggregateNetPnlFraction: stats.netPnlFraction,
    winRate: stats.winRate,
    profitFactor: stats.profitFactor,
    grossProfitFraction: stats.grossProfitFraction,
    grossLossFraction: stats.grossLossFraction,
    positiveSymbols,
    positiveWindowModes,
    dominantClusterShare: dominantClusterShare == null ? null : round(dominantClusterShare, 4),
    clearlyNegative,
    qualifiesForChallengerBatch,
    continueCurrentFamily,
    tradeCountBySymbol: Object.fromEntries(tradesBySymbol.map((item) => [item.key, item.tradeCount])),
    tradeCountByWindowMode: Object.fromEntries(tradesByWindowMode.map((item) => [item.key, item.tradeCount])),
    pnlShareBySymbol: Object.fromEntries(tradesBySymbol.map((item) => [item.key, item.pnlShare])),
    pnlShareByWindowMode: Object.fromEntries(tradesByWindowMode.map((item) => [item.key, item.pnlShare])),
    clusterBreakdown,
    symbolBreakdown: tradesBySymbol,
    windowModeBreakdown: tradesByWindowMode,
    holdout,
    reasons: [
      stats.tradeCount < CRYPTO_FAMILY_CHALLENGER_GATE.minimumTrades ? `under_min_trades:${stats.tradeCount}<${CRYPTO_FAMILY_CHALLENGER_GATE.minimumTrades}` : null,
      clearlyNegative ? "clearly_negative" : null,
      !continueCurrentFamily && stats.tradeCount >= CRYPTO_FAMILY_CONTINUE_RULES.minimumTrades && Number(stats.netPnlFraction || 0) > 0 && Number(stats.profitFactor || 0) >= CRYPTO_FAMILY_CONTINUE_RULES.minimumProfitFactor
        ? "concentration_or_breadth_limit"
        : null,
    ].filter(Boolean),
  };
}

function selectPhaseBFamilyRollup(rollups = []) {
  return rollups
    .filter((rollup) => rollup.qualifiesForChallengerBatch)
    .slice()
    .sort((left, right) => (
      Number(right.aggregateNetPnlFraction || 0) - Number(left.aggregateNetPnlFraction || 0) ||
      Number(right.profitFactor || 0) - Number(left.profitFactor || 0) ||
      Number(right.tradeCount || 0) - Number(left.tradeCount || 0) ||
      String(left.strategyFamily).localeCompare(String(right.strategyFamily))
    ))[0] || null;
}

function buildControlFirstChallengerBatch(strategy) {
  const baseThreshold = Number(strategy?.simulation?.useSignalStrengthThreshold || 0);
  const baseHoldBars = Math.max(1, Math.round(Number(strategy?.simulation?.maxHoldBars || 1)));
  const relaxedThreshold = round(Math.max(0.5, baseThreshold - 0.06), 4);
  const longerHoldBars = baseHoldBars + 6;
  const variants = [
    {
      variantId: `${strategy.strategyId}-control`,
      variantLabel: "control",
      challengerKind: "control",
      parameters: {
        signalThreshold: round(baseThreshold, 4),
        takeProfitFraction: round(Number(strategy.simulation?.takeProfitFraction || 0), 6),
        stopLossFraction: round(Number(strategy.simulation?.stopLossFraction || 0), 6),
        maxHoldBars: baseHoldBars,
      },
      strategySpec: clone(strategy),
    },
    {
      variantId: `${strategy.strategyId}-threshold-looser`,
      variantLabel: "threshold_looser",
      challengerKind: "threshold_looser",
      parameters: {
        signalThreshold: relaxedThreshold,
        takeProfitFraction: round(Number(strategy.simulation?.takeProfitFraction || 0), 6),
        stopLossFraction: round(Number(strategy.simulation?.stopLossFraction || 0), 6),
        maxHoldBars: baseHoldBars,
      },
      strategySpec: {
        ...clone(strategy),
        strategyId: `${strategy.strategyId}-threshold-looser`,
        name: `${strategy.name} [threshold looser]`,
        simulation: {
          ...clone(strategy.simulation),
          useSignalStrengthThreshold: relaxedThreshold,
        },
        metadata: {
          ...(strategy.metadata || {}),
          experimentBaseStrategyId: strategy.strategyId,
          experimentVariantLabel: "threshold_looser",
          experimentKind: "control_first_challenger",
        },
      },
    },
    {
      variantId: `${strategy.strategyId}-hold-longer`,
      variantLabel: "hold_longer",
      challengerKind: "hold_longer",
      parameters: {
        signalThreshold: round(baseThreshold, 4),
        takeProfitFraction: round(Number(strategy.simulation?.takeProfitFraction || 0), 6),
        stopLossFraction: round(Number(strategy.simulation?.stopLossFraction || 0), 6),
        maxHoldBars: longerHoldBars,
      },
      strategySpec: {
        ...clone(strategy),
        strategyId: `${strategy.strategyId}-hold-longer`,
        name: `${strategy.name} [hold longer]`,
        simulation: {
          ...clone(strategy.simulation),
          maxHoldBars: longerHoldBars,
        },
        metadata: {
          ...(strategy.metadata || {}),
          experimentBaseStrategyId: strategy.strategyId,
          experimentVariantLabel: "hold_longer",
          experimentKind: "control_first_challenger",
        },
      },
    },
    {
      variantId: `${strategy.strategyId}-threshold-looser-hold-longer`,
      variantLabel: "threshold_looser_hold_longer",
      challengerKind: "threshold_looser_hold_longer",
      parameters: {
        signalThreshold: relaxedThreshold,
        takeProfitFraction: round(Number(strategy.simulation?.takeProfitFraction || 0), 6),
        stopLossFraction: round(Number(strategy.simulation?.stopLossFraction || 0), 6),
        maxHoldBars: longerHoldBars,
      },
      strategySpec: {
        ...clone(strategy),
        strategyId: `${strategy.strategyId}-threshold-looser-hold-longer`,
        name: `${strategy.name} [threshold looser + hold longer]`,
        simulation: {
          ...clone(strategy.simulation),
          useSignalStrengthThreshold: relaxedThreshold,
          maxHoldBars: longerHoldBars,
        },
        metadata: {
          ...(strategy.metadata || {}),
          experimentBaseStrategyId: strategy.strategyId,
          experimentVariantLabel: "threshold_looser_hold_longer",
          experimentKind: "control_first_challenger",
        },
      },
    },
  ];

  return variants;
}

function buildCryptoExperimentVariants(strategy, options = {}) {
  const signalName = String(strategy.simulation?.entrySignal || "");
  const library = options.grid || CRYPTO_EXPERIMENT_LIBRARY;
  const family = library[signalName];
  if (!family) return [];

  const thresholds = uniqueNumbers(family.signalThresholds || [strategy.simulation.useSignalStrengthThreshold || 0.7]);
  const takeProfits = uniqueNumbers(family.takeProfitFractions || [strategy.simulation.takeProfitFraction || 0.008]);
  const stopLosses = uniqueNumbers(family.stopLossFractions || [strategy.simulation.stopLossFraction || 0.004]);
  const holdBars = [...new Set((family.maxHoldBars || [strategy.simulation.maxHoldBars || 12]).map((value) => Math.max(1, Math.round(Number(value) || 1))))];
  // ATR-based stop/target multipliers: 0 means "use fixed fractions" (default)
  const atrStopMults = uniqueNumbers(family.atrStopMultipliers || [0]);
  const atrTargetMults = uniqueNumbers(family.atrTargetMultipliers || [0]);
  // Build paired ATR combos: (0,0) = fixed, plus each (stop,target) pair where both > 0
  const atrCombos = [[0, 0]];
  for (const stopMult of atrStopMults) {
    for (const targetMult of atrTargetMults) {
      if (stopMult > 0 && targetMult > 0) atrCombos.push([stopMult, targetMult]);
    }
  }
  const variants = [];

  for (const signalThreshold of thresholds) {
    for (const takeProfitFraction of takeProfits) {
      for (const stopLossFraction of stopLosses) {
        for (const maxHoldBars of holdBars) {
          for (const [atrStopMultiplier, atrTargetMultiplier] of atrCombos) {
            const atrLabel = atrStopMultiplier > 0
              ? `-atrS${Math.round(atrStopMultiplier * 10)}T${Math.round(atrTargetMultiplier * 10)}`
              : "";
            const variantLabel = `thr${Math.round(signalThreshold * 100)}-tp${Math.round(takeProfitFraction * 10000)}-sl${Math.round(stopLossFraction * 10000)}-hold${maxHoldBars}${atrLabel}`;
            const variantId = `${strategy.strategyId}-${variantLabel}`;
            variants.push({
              variantId,
              variantLabel,
              parameters: {
                signalThreshold: round(signalThreshold),
                takeProfitFraction: round(takeProfitFraction),
                stopLossFraction: round(stopLossFraction),
                maxHoldBars,
                atrStopMultiplier: round(atrStopMultiplier),
                atrTargetMultiplier: round(atrTargetMultiplier),
              },
              strategySpec: {
                ...clone(strategy),
                strategyId: variantId,
                name: `${strategy.name} [${variantLabel}]`,
                status: "draft",
                simulation: {
                  ...clone(strategy.simulation),
                  useSignalStrengthThreshold: signalThreshold,
                  takeProfitFraction,
                  stopLossFraction,
                  maxHoldBars,
                  atrStopMultiplier: atrStopMultiplier || undefined,
                  atrTargetMultiplier: atrTargetMultiplier || undefined,
                },
                metadata: {
                  ...(strategy.metadata || {}),
                  experimentBaseStrategyId: strategy.strategyId,
                  experimentVariantLabel: variantLabel,
                  experimentKind: "parameter_sweep",
                },
              },
            });
          }
        }
      }
    }
  }

  return variants;
}

function compareExperimentResults(left, right) {
  const leftTrusted = left?.trustedMarketData === true ? 1 : 0;
  const rightTrusted = right?.trustedMarketData === true ? 1 : 0;
  if (rightTrusted !== leftTrusted) return rightTrusted - leftTrusted;

  const leftSummary = left?.summary || {};
  const rightSummary = right?.summary || {};
  const leftEligible = leftSummary.eligibleForPromotion === true ? 1 : 0;
  const rightEligible = rightSummary.eligibleForPromotion === true ? 1 : 0;
  if (rightEligible !== leftEligible) return rightEligible - leftEligible;

  const leftReturn = Number(leftSummary.totalNetReturnFraction || 0);
  const rightReturn = Number(rightSummary.totalNetReturnFraction || 0);
  if (rightReturn !== leftReturn) return rightReturn - leftReturn;

  const leftProfitFactor = Number(leftSummary.profitFactor || 0);
  const rightProfitFactor = Number(rightSummary.profitFactor || 0);
  if (rightProfitFactor !== leftProfitFactor) return rightProfitFactor - leftProfitFactor;

  const leftWinRate = Number(leftSummary.winRate || 0);
  const rightWinRate = Number(rightSummary.winRate || 0);
  if (rightWinRate !== leftWinRate) return rightWinRate - leftWinRate;

  const leftTradeCount = Number(leftSummary.tradeCount || 0);
  const rightTradeCount = Number(rightSummary.tradeCount || 0);
  if (rightTradeCount !== leftTradeCount) return rightTradeCount - leftTradeCount;

  const leftDrawdown = Number(leftSummary.maxDrawdownFraction || 0);
  const rightDrawdown = Number(rightSummary.maxDrawdownFraction || 0);
  if (leftDrawdown !== rightDrawdown) return leftDrawdown - rightDrawdown;

  return String(left?.variantId || "").localeCompare(String(right?.variantId || ""));
}

function scoreExperimentResult(result) {
  const summary = result?.summary || {};
  return round(
    (result?.trustedMarketData === true ? 1000 : -1000) +
    (summary.eligibleForPromotion === true ? 250 : 0) +
    (Number(summary.totalNetReturnFraction || 0) * 100000) +
    (Number(summary.profitFactor || 0) * 100) +
    (Number(summary.winRate || 0) * 100) +
    Math.min(Number(summary.tradeCount || 0), 50) -
    (Number(summary.maxDrawdownFraction || 0) * 1000),
    4,
  );
}

function summarizeExperimentLeaders(results, groupKey, limit = 3) {
  const grouped = new Map();
  for (const result of results) {
    const key = result[groupKey];
    if (key == null) continue;
    const list = grouped.get(key) || [];
    list.push(result);
    grouped.set(key, list);
  }

  return [...grouped.entries()]
    .map(([key, items]) => ({
      key,
      leaders: items
        .slice()
        .sort(compareExperimentResults)
        .slice(0, limit)
        .map((item) => ({
          variantId: item.variantId,
          strategyName: item.strategyName,
          symbol: item.symbol,
          parameters: item.parameters,
          summary: item.summary,
          trustedMarketData: item.trustedMarketData,
          marketDataSource: item.marketDataSource,
          marketDataWarning: item.marketDataWarning,
          experimentScore: item.experimentScore,
        })),
    }))
    .sort((left, right) => String(left.key).localeCompare(String(right.key)));
}

async function runDayTradingValidation(options = {}) {
  const useCustomStrategies = Array.isArray(options.strategies);
  const strategyUniverse = useCustomStrategies ? options.strategies : loadStrategies();
  const strategies = strategyUniverse
    .filter((strategy) => FROZEN_CRYPTO_FAMILIES.has(String(strategy.simulation?.entrySignal || "")))
    .filter((strategy) => String(strategy.status || "") !== "disabled");
  const bars = normalizeBarsSelection(options.bars, DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars);
  const windowMode = normalizeWindowMode(options.windowMode, DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode);
  const feesFraction = Number.isFinite(options.feesFraction)
    ? Number(options.feesFraction)
    : DEFAULT_CRYPTO_DAY_TRADING_CONFIG.feesFraction;
  const startingCash = Number(options.startingCash) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.startingCash;
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : (strategy, loaderOptions) => loadCryptoMarketDataForStrategy(strategy, { ...loaderOptions, includeLive: false });

  const broker = new shared.PaperBroker({ ledgerPath: LEDGER_PATH });
  broker.ensureAccount({ accountId, startingCash });
  const nextStrategies = [];
  const bundles = [];
  const report = {
    generatedAt: nowIso(),
    profitabilityProfileId: PROFITABILITY_PROFILE_ID,
    market: DEFAULT_MARKET,
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    windowMode,
    windowModeLabel: getWindowModeLabel(windowMode),
    alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
    barsRequested: bars,
    feesFraction,
    strategiesScanned: strategies.length,
    results: [],
  };

  for (const strategy of strategies) {
    const previousBacktest = getBacktestResult(strategy.strategyId);
    const marketData = await marketDataLoader(strategy, { bars, windowMode });
    const trusted = marketData?.trusted !== false;
    const backtest = marketData?.priceSeries?.length > 0
      ? shared.runBacktest({
        strategySpec: strategy,
        priceSeries: marketData.priceSeries,
        feesFraction,
      })
      : unavailableBacktest(strategy.strategyId, marketData?.warning || "missing_imported_history");
    if (!trusted) {
      backtest.summary = {
        ...backtest.summary,
        eligibleForPromotion: false,
        vetoReasons: [...new Set([...(backtest.summary?.vetoReasons || []), marketData?.warning || "untrusted_market_data"])],
      };
    }

    const saved = saveBacktestResult({
      ...backtest,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
        marketType: DEFAULT_MARKET_TYPE,
        sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
        windowMode,
        alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
        marketDataSource: marketData?.source || null,
        marketDataWarning: marketData?.warning || null,
      trustedMarketData: trusted,
    });
    const paperAction = trusted
      ? await shared.maybePaperTrade({
        paperBroker: broker,
        strategy,
        marketData,
        accountId,
      })
      : { action: "skipped", reason: "untrusted_market_data" };
    const paperSummary = broker.getStrategySummaries({ accountId })
      .find((item) => item.strategyId === strategy.strategyId) || null;
    const promotionDecision = shared.nextPromotionDecision(strategy, {
      backtestSummary: backtest.summary,
      paperSummary,
    });
    nextStrategies.push(applyPromotionDecision(strategy, promotionDecision));

    const bundle = {
      strategyId: strategy.strategyId,
      strategyName: strategy.name,
      strategyFamily: String(strategy.simulation?.entrySignal || ""),
      symbol: strategy.marketUniverse?.symbols?.[0] || null,
      windowMode,
      trustedMarketData: trusted,
      marketDataSource: marketData?.source || null,
      marketDataWarning: marketData?.warning || null,
      rawBarCount: Number(marketData?.rawBarCount || 0),
      derivedBarCount: Number(marketData?.derivedBarCount || marketData?.priceSeries?.length || 0),
      importedBarCount: Number(marketData?.importedBarCount || 0),
      importedStartTimestamp: marketData?.importedStartTimestamp || null,
      importedEndTimestamp: marketData?.importedEndTimestamp || null,
      usedStartTimestamp: marketData?.usedStartTimestamp || null,
      usedEndTimestamp: marketData?.usedEndTimestamp || null,
      backtest,
      summary: backtest.summary,
    };
    bundles.push(bundle);

    report.results.push({
      strategyId: strategy.strategyId,
      strategyName: strategy.name,
      strategyFamily: bundle.strategyFamily,
      symbol: bundle.symbol,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
      marketType: DEFAULT_MARKET_TYPE,
      sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      windowMode,
      alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
      marketDataSource: marketData?.source || null,
      marketDataWarning: marketData?.warning || null,
      trustedMarketData: trusted,
      raw1mBarCountUsed: bundle.rawBarCount,
      derived5mBarCountUsed: bundle.derivedBarCount,
      imported1mBarCountUsed: bundle.importedBarCount,
      importedSpanUsed: {
        startTimestamp: bundle.importedStartTimestamp,
        endTimestamp: bundle.importedEndTimestamp,
      },
      usedSpan: {
        startTimestamp: bundle.usedStartTimestamp,
        endTimestamp: bundle.usedEndTimestamp,
      },
      savedTo: saved.filePath,
      backtestSummary: backtest.summary,
      previousBacktestSummary: previousBacktest?.summary || null,
      paperAction,
      promotionDecision,
    });
  }

  const updatedStrategyMap = new Map(nextStrategies.map((strategy) => [strategy.strategyId, strategy]));
  const persistedStrategies = strategyUniverse.map((strategy) => updatedStrategyMap.get(strategy.strategyId) || strategy);
  if (!useCustomStrategies) {
    saveStrategiesIfChanged(strategyUniverse, persistedStrategies);
  }
  report.paperAccount = broker.getAccountSummary({ accountId });
  report.scoreboard = shared.buildStrategyScoreboard({
    strategies: persistedStrategies,
    backtests: loadBacktestSummaries(),
    paperSummaries: broker.getStrategySummaries({ accountId }),
  });
  const allTrades = bundles.flatMap((bundle) => (bundle.backtest?.trades || []).map((trade) => ({
    ...trade,
    windowMode: bundle.windowMode,
  })));
  const tradeBySymbol = buildTradeBreakdown(allTrades, (trade) => trade.symbol || "unknown");
  const tradeByWindowMode = buildTradeBreakdown(allTrades, (trade) => trade.windowMode || windowMode);
  report.marketDataUsage = buildMarketDataUsageSummary(bundles);
  report.tradeCountBySymbol = Object.fromEntries(tradeBySymbol.map((item) => [item.key, item.tradeCount]));
  report.tradeCountByWindowMode = Object.fromEntries(tradeByWindowMode.map((item) => [item.key, item.tradeCount]));
  report.pnlShareBySymbol = Object.fromEntries(tradeBySymbol.map((item) => [item.key, item.pnlShare]));
  report.pnlShareByWindowMode = Object.fromEntries(tradeByWindowMode.map((item) => [item.key, item.pnlShare]));
  report.tradeBreakdownBySymbol = tradeBySymbol;
  report.tradeBreakdownByWindowMode = tradeByWindowMode;
  atomicWriteJsonSync(REPORT_PATH, report);
  return report;
}

async function runDayTradingExperiments(options = {}) {
  const strategies = (options.strategies || loadStrategies())
    .filter((strategy) => FROZEN_CRYPTO_FAMILIES.has(String(strategy.simulation?.entrySignal || "")))
    .filter((strategy) => String(strategy.status || "") !== "disabled");
  const bars = normalizeBarsSelection(options.bars, DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars);
  const windowModes = resolveExperimentWindowModes(options.windowMode);
  const feesFraction = Number.isFinite(options.feesFraction)
    ? Number(options.feesFraction)
    : DEFAULT_CRYPTO_DAY_TRADING_CONFIG.feesFraction;
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : (strategy, loaderOptions) => loadCryptoMarketDataForStrategy(strategy, { ...loaderOptions, includeLive: false });
  const strictMarketData = options.strictMarketData !== false;
  const top = Math.max(1, Number(options.top) || 10);
  ensureDir(EXPERIMENTS_DIR);

  const controlBundles = [];
  for (const windowMode of windowModes) {
    for (const strategy of strategies) {
      const marketData = await marketDataLoader(strategy, { bars, windowMode });
      const trustedMarketData = marketData?.trusted !== false;
      const backtest = marketData?.priceSeries?.length > 0
        ? shared.runBacktest({
          strategySpec: strategy,
          priceSeries: marketData.priceSeries,
          feesFraction,
        })
        : unavailableBacktest(strategy.strategyId, marketData?.warning || "missing_imported_history");
      const summary = trustedMarketData || !strictMarketData
        ? backtest.summary
        : {
          ...backtest.summary,
          eligibleForPromotion: false,
          vetoReasons: [...(backtest.summary.vetoReasons || []), "untrusted_market_data"],
        };
      const bundle = {
        variantId: `${strategy.strategyId}-${windowMode}-control`,
        strategyId: strategy.strategyId,
        strategySpec: clone(strategy),
        strategyName: strategy.name,
        baseStrategyId: strategy.strategyId,
        strategyFamily: String(strategy.simulation?.entrySignal || ""),
        symbol: strategy.marketUniverse?.symbols?.[0] || null,
        timeframe: strategy.evaluationWindow?.timeframe || null,
        market: DEFAULT_MARKET,
        exchange: DEFAULT_EXCHANGE,
        marketType: DEFAULT_MARKET_TYPE,
        sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
        windowMode,
        windowModeLabel: getWindowModeLabel(windowMode),
        alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
        variantLabel: "control",
        challengerKind: "control",
        parameters: {
          signalThreshold: round(Number(strategy.simulation?.useSignalStrengthThreshold || 0), 4),
          takeProfitFraction: round(Number(strategy.simulation?.takeProfitFraction || 0), 6),
          stopLossFraction: round(Number(strategy.simulation?.stopLossFraction || 0), 6),
          maxHoldBars: Math.round(Number(strategy.simulation?.maxHoldBars || 0)),
        },
        trustedMarketData: trustedMarketData || !strictMarketData,
        marketDataSource: marketData?.source || null,
        marketDataWarning: marketData?.warning || null,
        rawBarCount: Number(marketData?.rawBarCount || 0),
        derivedBarCount: Number(marketData?.derivedBarCount || marketData?.priceSeries?.length || 0),
        importedBarCount: Number(marketData?.importedBarCount || 0),
        importedStartTimestamp: marketData?.importedStartTimestamp || null,
        importedEndTimestamp: marketData?.importedEndTimestamp || null,
        usedStartTimestamp: marketData?.usedStartTimestamp || null,
        usedEndTimestamp: marketData?.usedEndTimestamp || null,
        latestBarTimestamp: marketData?.priceSeries?.[marketData.priceSeries.length - 1]?.timestamp || null,
        backtest,
        summary,
      };
      bundle.experimentScore = scoreControlBundle(bundle);
      controlBundles.push(bundle);
    }
  }

  const controlResults = controlBundles
    .map((bundle) => ({
      variantId: bundle.variantId,
      strategyId: bundle.strategyId,
      strategyName: bundle.strategyName,
      baseStrategyId: bundle.baseStrategyId,
      strategyFamily: bundle.strategyFamily,
      symbol: bundle.symbol,
      timeframe: bundle.timeframe,
      market: bundle.market,
      exchange: bundle.exchange,
      marketType: bundle.marketType,
      sessionMode: bundle.sessionMode,
      windowMode: bundle.windowMode,
      windowModeLabel: bundle.windowModeLabel,
      alertWindows: bundle.alertWindows,
      variantLabel: bundle.variantLabel,
      challengerKind: bundle.challengerKind,
      parameters: bundle.parameters,
      trustedMarketData: bundle.trustedMarketData,
      marketDataSource: bundle.marketDataSource,
      marketDataWarning: bundle.marketDataWarning,
      raw1mBarCountUsed: bundle.rawBarCount,
      derived5mBarCountUsed: bundle.derivedBarCount,
      imported1mBarCountUsed: bundle.importedBarCount,
      importedSpanUsed: {
        startTimestamp: bundle.importedStartTimestamp,
        endTimestamp: bundle.importedEndTimestamp,
      },
      usedSpan: {
        startTimestamp: bundle.usedStartTimestamp,
        endTimestamp: bundle.usedEndTimestamp,
      },
      latestBarTimestamp: bundle.latestBarTimestamp,
      summary: bundle.summary,
      experimentScore: bundle.experimentScore,
    }))
    .sort(compareControlBundles);

  const familyModeGroups = new Map();
  for (const bundle of controlBundles) {
    const key = `${bundle.strategyFamily}::${bundle.windowMode}`;
    const list = familyModeGroups.get(key) || [];
    list.push(bundle);
    familyModeGroups.set(key, list);
  }

  const familyModeReviews = [...familyModeGroups.entries()]
    .map(([key, bundles]) => {
      const [strategyFamily, windowMode] = key.split("::");
      return buildFamilyRollup(strategyFamily, windowMode, bundles);
    })
    .sort((left, right) => (
      Number(right.aggregateNetPnlFraction || 0) - Number(left.aggregateNetPnlFraction || 0) ||
      Number(right.profitFactor || 0) - Number(left.profitFactor || 0) ||
      Number(right.tradeCount || 0) - Number(left.tradeCount || 0) ||
      String(left.strategyFamily).localeCompare(String(right.strategyFamily))
    ));

  const phaseBFamily = selectPhaseBFamilyRollup(familyModeReviews);
  let phaseBResults = [];
  let phaseBTopControl = null;
  if (phaseBFamily) {
    phaseBTopControl = controlBundles
      .filter((bundle) => bundle.strategyFamily === phaseBFamily.strategyFamily && bundle.windowMode === phaseBFamily.windowMode)
      .sort(compareControlBundles)[0] || null;

    if (phaseBTopControl) {
      const marketData = await marketDataLoader(phaseBTopControl.strategySpec, {
        bars,
        windowMode: phaseBTopControl.windowMode,
      });
      const trustedMarketData = marketData?.trusted !== false;
      phaseBResults = buildControlFirstChallengerBatch(phaseBTopControl.strategySpec)
        .map((variant) => {
          const backtest = marketData?.priceSeries?.length > 0
            ? shared.runBacktest({
              strategySpec: variant.strategySpec,
              priceSeries: marketData.priceSeries,
              feesFraction,
            })
            : unavailableBacktest(variant.variantId, marketData?.warning || "missing_imported_history");
          const summary = trustedMarketData || !strictMarketData
            ? backtest.summary
            : {
              ...backtest.summary,
              eligibleForPromotion: false,
              vetoReasons: [...(backtest.summary.vetoReasons || []), "untrusted_market_data"],
            };
          const result = {
            variantId: variant.variantId,
            strategyId: phaseBTopControl.strategyId,
            strategyName: phaseBTopControl.strategyName,
            baseStrategyId: phaseBTopControl.baseStrategyId,
            strategyFamily: phaseBTopControl.strategyFamily,
            symbol: phaseBTopControl.symbol,
            timeframe: phaseBTopControl.timeframe,
            market: DEFAULT_MARKET,
            exchange: DEFAULT_EXCHANGE,
            marketType: DEFAULT_MARKET_TYPE,
            sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
            windowMode: phaseBTopControl.windowMode,
            windowModeLabel: phaseBTopControl.windowModeLabel,
            alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
            variantLabel: variant.variantLabel,
            challengerKind: variant.challengerKind,
            parameters: variant.parameters,
            trustedMarketData: trustedMarketData || !strictMarketData,
            marketDataSource: marketData?.source || null,
            marketDataWarning: marketData?.warning || null,
            raw1mBarCountUsed: Number(marketData?.rawBarCount || 0),
            derived5mBarCountUsed: Number(marketData?.derivedBarCount || marketData?.priceSeries?.length || 0),
            imported1mBarCountUsed: Number(marketData?.importedBarCount || 0),
            importedSpanUsed: {
              startTimestamp: marketData?.importedStartTimestamp || null,
              endTimestamp: marketData?.importedEndTimestamp || null,
            },
            usedSpan: {
              startTimestamp: marketData?.usedStartTimestamp || null,
              endTimestamp: marketData?.usedEndTimestamp || null,
            },
            latestBarTimestamp: marketData?.priceSeries?.[marketData.priceSeries.length - 1]?.timestamp || null,
            summary,
          };
          result.experimentScore = scoreExperimentResult(result);
          return result;
        })
        .sort(compareExperimentResults);
    }
  }

  const allPhaseTrades = controlBundles.flatMap((bundle) => (bundle.backtest?.trades || []).map((trade) => ({
    ...trade,
    windowMode: bundle.windowMode,
  })));
  const tradeBySymbol = buildTradeBreakdown(allPhaseTrades, (trade) => trade.symbol || "unknown");
  const tradeByWindowMode = buildTradeBreakdown(allPhaseTrades, (trade) => trade.windowMode || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode);
  const familyReachedTradeGate = familyModeReviews.some((rollup) => rollup.tradeCount >= CRYPTO_FAMILY_CHALLENGER_GATE.minimumTrades);
  const allFamiliesClearlyNegative = familyModeReviews.length > 0 && familyModeReviews.every((rollup) => rollup.clearlyNegative);
  const marketDataUsage = buildMarketDataUsageSummary(controlBundles);
  const spanDays = Number(marketDataUsage.importedSpanUsed.spanDays || 0);
  const bestFamilyOverall = familyModeReviews[0] || null;

  let recommendation = "continue_control_matrix";
  let nextSprint = "collect_more_crypto_history";
  if (phaseBResults.length > 0) {
    recommendation = "run_narrow_challenger_batch_only";
    nextSprint = "narrow_family_follow_up";
  } else if (
    spanDays >= 180 &&
    bestFamilyOverall &&
    (Number(bestFamilyOverall.profitFactor || 0) < 1 || Number(bestFamilyOverall.aggregateNetPnlFraction || 0) <= 0)
  ) {
    recommendation = "strategy_redesign_next_sprint";
    nextSprint = "strategy_redesign";
  } else if (spanDays >= 90 && (!familyReachedTradeGate || allFamiliesClearlyNegative)) {
    recommendation = "strategy_redesign_next_sprint";
    nextSprint = "strategy_redesign";
  }

  const trustedCount = controlResults.filter((result) => result.trustedMarketData).length + phaseBResults.filter((result) => result.trustedMarketData).length;
  const eligibleCount = phaseBResults.filter((result) => result.summary?.eligibleForPromotion === true).length;
  const leaders = phaseBResults.length > 0
    ? phaseBResults.slice(0, top)
    : controlResults.slice(0, top);

  const report = {
    generatedAt: nowIso(),
    market: DEFAULT_MARKET,
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    windowModesEvaluated: windowModes,
    alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
    barsRequested: bars,
    feesFraction,
    strictMarketData,
    scope: String(options.scope || "snapshot"),
    researchMode: String(options.researchMode || "control_first"),
    strategiesTested: strategies.length,
    controlStrategiesTested: controlResults.length,
    variantsTested: controlResults.length + phaseBResults.length,
    trustedVariantCount: trustedCount,
    untrustedVariantCount: (controlResults.length + phaseBResults.length) - trustedCount,
    eligibleVariantCount: eligibleCount,
    marketDataUsage,
    tradeCountBySymbol: Object.fromEntries(tradeBySymbol.map((item) => [item.key, item.tradeCount])),
    tradeCountByWindowMode: Object.fromEntries(tradeByWindowMode.map((item) => [item.key, item.tradeCount])),
    pnlShareBySymbol: Object.fromEntries(tradeBySymbol.map((item) => [item.key, item.pnlShare])),
    pnlShareByWindowMode: Object.fromEntries(tradeByWindowMode.map((item) => [item.key, item.pnlShare])),
    leaders,
    phaseA: {
      description: "Managed crypto controls across the requested window modes.",
      familyWindowReviews: familyModeReviews,
      controlResults,
    },
    phaseB: {
      unlocked: phaseBResults.length > 0,
      reason: phaseBResults.length > 0 ? "family_trade_gate_cleared" : "no_family_cleared_trade_gate",
      selectedFamilyWindow: phaseBFamily ? {
        strategyFamily: phaseBFamily.strategyFamily,
        windowMode: phaseBFamily.windowMode,
        windowModeLabel: phaseBFamily.windowModeLabel,
      } : null,
      selectedControlStrategyId: phaseBTopControl?.strategyId || null,
      batchShape: phaseBResults.length > 0 ? "1_control_plus_3_challengers" : null,
      results: phaseBResults,
    },
    recommendation,
    nextSprintDefault: nextSprint,
    notes: [
      "Crypto replay only uses trusted imported spot data for promotable results.",
      "Broad crypto parameter sweeps are paused. The default loop is controls first, then one narrow challenger batch if a family clears the trade gate.",
      "Current continue gate: 30+ trades, positive return, PF >= 1.05, breadth across 2 symbols or 2 window modes, and no more than 70% of P&L from one symbol/window cluster.",
      "Futures/perps validation stays blocked until a spot family reaches 50+ trades, positive return, PF >= 1.10, and a positive last-30%-of-history holdout.",
    ],
    results: phaseBResults.length > 0 ? phaseBResults : controlResults,
  };

  atomicWriteJsonSync(EXPERIMENT_REPORT_PATH, report);
  return report;
}

function getWindowSummary(now) {
  const watchWindowMode = DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode;
  const current = classifyWindow(now, { config: DEFAULT_CRYPTO_DAY_TRADING_CONFIG, windowMode: watchWindowMode });
  return {
    windowMode: watchWindowMode,
    activeNow: current.active,
    activeWindowId: current.windowId,
    activeWindowLabel: current.windowLabel,
    windows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
  };
}

async function buildMorningWatchlist(options = {}) {
  const bars = Number(options.bars) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.bars;
  const limit = Math.max(1, Number(options.limit) || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.watchlistLimit || 6);
  const readOnly = Boolean(options.readOnly);
  const persistArtifacts = options.persistArtifacts !== false && !readOnly;
  const bundle = options.artifactBundle || (readOnly ? _readOnlyDayTradingBundle({ ...options, bars }) : null);
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : (strategy, loaderOptions) => loadCryptoMarketDataForStrategy(strategy, { ...loaderOptions, includeLive: true });
  const strategies = ((bundle?.strategies || options.strategies || loadStrategies({ readOnly })) || [])
    .filter((strategy) => String(strategy.status || "") !== "disabled");
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const now = options.now || nowIso();
  const nowWindow = classifyScheduledWindow(now, DEFAULT_CRYPTO_DAY_TRADING_CONFIG);
  const profitabilityTicketStore = bundle?.profitabilityTicketStore || readProfitabilityTicketStore();
  const todayGate = buildTodayGate(profitabilityTicketStore, { now });
  const broker = bundle?.broker || new shared.PaperBroker({ ledgerPath: LEDGER_PATH, readOnly });
  broker.ensureAccount({
    accountId,
    startingCash: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.startingCash,
    createIfMissing: readOnly,
  });
  const paperSummaries = bundle?.paperSummaries || broker.getStrategySummaries({ accountId });
  const profitabilityJournal = bundle?.profitabilityJournal || readProfitabilityJournal();
  const pilotSummary = buildProfitabilityPilotSummary(profitabilityJournal.entries, {
    ticketStore: profitabilityTicketStore,
    now,
  });
  const journalSummary = buildProfitabilityJournalSummary(profitabilityJournal, {
    todayDate: getLocalParts(now)?.date || null,
    recentLimit: 8,
  });
  const scoreboard = shared.buildStrategyScoreboard({
    strategies,
    backtests: bundle?.backtests || loadBacktestSummaries(),
    paperSummaries,
  });
  const strategyMap = new Map(strategies.map((strategy) => [strategy.strategyId, strategy]));
  const evaluatedCandidates = (await Promise.all(scoreboard.items.map(async (candidate) => {
    const strategy = strategyMap.get(candidate.strategyId);
    if (!strategy) return null;
    const marketData = await marketDataLoader(strategy, { bars, persistArtifacts });
    const trusted = marketData?.trusted !== false;
    const priceSeries = Array.isArray(marketData?.priceSeries) ? marketData.priceSeries : [];
    const lastBar = priceSeries[priceSeries.length - 1] || null;
    const signalName = strategy.simulation.entrySignal;
    const threshold = Number(strategy.simulation.useSignalStrengthThreshold || 0);
    const latestSessionKey = lastBar ? buildWindowSessionKey(lastBar.timestamp, DEFAULT_CRYPTO_DAY_TRADING_CONFIG) : null;
    const nowSessionKey = buildWindowSessionKey(now, DEFAULT_CRYPTO_DAY_TRADING_CONFIG);
    const sessionBars = latestSessionKey == null
      ? []
      : priceSeries.filter((bar) => buildWindowSessionKey(bar.timestamp, DEFAULT_CRYPTO_DAY_TRADING_CONFIG) === latestSessionKey);
    const signalBars = sessionBars
      .map((bar, index) => ({
        bar,
        index,
        signalValue: Number(bar.signals?.[signalName] || 0),
        window: classifyScheduledWindow(bar.timestamp, DEFAULT_CRYPTO_DAY_TRADING_CONFIG),
      }))
      .filter((entry) => entry.signalValue >= threshold);
    const latestSignal = signalBars.length > 0 ? signalBars[signalBars.length - 1] : null;
    const barsSinceTrigger = latestSignal ? Math.max(0, sessionBars.length - latestSignal.index - 1) : null;
    const currentSignalValue = lastBar ? Number(lastBar.signals?.[signalName] || 0) : 0;
    const lastBarWindow = lastBar ? classifyScheduledWindow(lastBar.timestamp, DEFAULT_CRYPTO_DAY_TRADING_CONFIG) : { active: false };
    const barAgeMinutes = calculateBarAgeMinutes(lastBar?.timestamp, now);
    const dataFresh = barAgeMinutes != null && barAgeMinutes <= DEFAULT_CRYPTO_DAY_TRADING_CONFIG.maxBarAgeMinutes;
    const alertEligible = candidate.backtest?.eligibleForPromotion === true;
    const regimeState = String(lastBar?.indicators?.regimeState || "unknown");
    const tradeable = lastBar?.indicators?.tradeable === true;
    const regimeBlockers = Array.isArray(lastBar?.indicators?.regimeBlockers) ? lastBar.indicators.regimeBlockers : [];
    const gateBlockedReasons = [...regimeBlockers];
    if (strategy.strategyId === BTC_PROFITABILITY_SETUP_ID && todayGate.remainingApprovals <= 0) {
      gateBlockedReasons.push("daily_trade_cap_reached");
    }

    let liveStatus = "inactive";
    let notifyNow = false;
    if (!trusted) {
      liveStatus = "untrusted_data";
    } else if (!dataFresh) {
      liveStatus = "stale";
    } else if (strategy.strategyId === BTC_PROFITABILITY_SETUP_ID && todayGate.remainingApprovals <= 0) {
      liveStatus = "blocked_daily_cap";
    } else if (!tradeable && regimeBlockers.length > 0) {
      liveStatus = regimeBlockers.includes("event_shock_lockout")
        ? "blocked_event_shock"
        : regimeBlockers.includes("expansion")
          ? "blocked_expansion"
          : regimeBlockers.includes("mid_range")
            ? "blocked_mid_range"
            : "blocked_regime";
    } else if (latestSignal && latestSignal.window.active && nowWindow.active && latestSessionKey != null && latestSessionKey === nowSessionKey && barsSinceTrigger != null && barsSinceTrigger <= DEFAULT_CRYPTO_DAY_TRADING_CONFIG.notifyLookbackBars) {
      liveStatus = barsSinceTrigger === 0 ? "triggered_now" : "triggered_recently";
      notifyNow = alertEligible;
    } else if (latestSignal && latestSignal.window.active) {
      liveStatus = "triggered_this_window";
    } else if (nowWindow.active && lastBarWindow.active && latestSessionKey === nowSessionKey) {
      liveStatus = "tracking";
    }

    const baseItem = {
      strategyId: strategy.strategyId,
      strategyName: strategy.name,
      symbol: strategy.marketUniverse?.symbols?.[0] || null,
      timeframe: strategy.evaluationWindow?.timeframe || null,
      signalName,
      market: DEFAULT_MARKET,
      exchange: DEFAULT_EXCHANGE,
      marketType: DEFAULT_MARKET_TYPE,
      sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      windowMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
      alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
      liveStatus,
      notifyNow,
      alertEligible,
      evidenceScore: candidate.evidenceScore,
      score: candidate.score,
      status: candidate.status,
      replayEvidence: candidate.backtest || null,
      paperEvidence: candidate.paper || null,
      marketDataSource: marketData?.source || null,
      marketDataWarning: marketData?.warning || null,
      trustedMarketData: trusted,
      lastBarTimestamp: lastBar?.timestamp || null,
      latestSignalTimestamp: latestSignal?.bar?.timestamp || null,
      latestSignalValue: latestSignal?.signalValue ?? null,
      currentSignalValue: round(currentSignalValue, 4),
      signalThreshold: round(threshold, 4),
      barsSinceTrigger,
      barAgeMinutes,
      morningWindowActive: nowWindow.active,
      regimeState,
      tradeable,
      regimeBlockers,
      approvalSlotsRemaining: strategy.strategyId === BTC_PROFITABILITY_SETUP_ID ? todayGate.remainingApprovals : null,
      dataFresh,
      currentDataTrusted: trusted,
      sessionWindowId: latestSignal?.window?.windowId || lastBarWindow.windowId || null,
      sessionWindowLabel: latestSignal?.window?.windowLabel || lastBarWindow.windowLabel || null,
      sessionActiveNow: nowWindow.active,
      currentPrice: lastBar?.close || null,
      indicators: lastBar?.indicators || null,
      reasons: [...new Set(gateBlockedReasons)],
    };
    const priority = buildWatchlistPriorityProfile(baseItem, {
      pilotSummary,
      todayGate,
      now,
    });
    return {
      ...baseItem,
      ...priority,
      pilotSignals: {
        currentSessionActive: nowWindow.active,
        activeWindow: nowWindow.label || nowWindow.windowLabel || null,
        approvalSlotsRemaining: todayGate.remainingApprovals,
        pilotPhase: pilotSummary.phase,
        ruleAdherenceRate: pilotSummary.journalStats.ruleAdherenceRate,
        makerShare: pilotSummary.executionStats?.makerShare ?? null,
      },
    };
  }))).filter(Boolean);

  const items = evaluatedCandidates
    .sort(comparePilotAwareWatchlistCandidates)
    .slice(0, limit);

  const watchlist = {
    generatedAt: nowIso(),
    profitabilityProfileId: PROFITABILITY_PROFILE_ID,
    evaluatedAt: now,
    market: DEFAULT_MARKET,
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    windowMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
    rankingBasis: "replay_backed_watchlist",
    rankingMethod: "pilot_aware_priority",
    morningWindow: {
      startEt: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows[0].startEt,
      cutoffEt: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows[0].endEt,
      activeNow: nowWindow.active,
    },
    todayGate,
    sessionWindow: getWindowSummary(now),
    pilotSummary: {
      phase: pilotSummary.phase,
      progress: pilotSummary.progress,
      nextUnlock: pilotSummary.nextUnlock,
      journalStats: pilotSummary.journalStats,
      executionStats: pilotSummary.executionStats || null,
      disqualificationReasons: pilotSummary.disqualificationReasons || [],
    },
    journalSummary,
    selectedStrategies: items.length,
    notifyNowCount: items.filter((item) => item.notifyNow).length,
    items,
  };
  if (persistArtifacts) {
    atomicWriteJsonSync(WATCHLIST_PATH, watchlist);
  }
  return watchlist;
}

function getDayTradingSnapshot(options = {}) {
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const now = options.now || nowIso();
  const bundle = options.artifactBundle || _readOnlyDayTradingBundle(options);
  const broker = bundle?.broker || new shared.PaperBroker({ ledgerPath: LEDGER_PATH, readOnly: true });
  broker.ensureAccount({
    accountId,
    startingCash: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.startingCash,
    createIfMissing: true,
  });
  const strategies = bundle?.strategies || loadStrategies({ readOnly: true });
  const paperSummaries = bundle?.paperSummaries || broker.getStrategySummaries({ accountId });
  const profitabilityJournal = bundle?.profitabilityJournal || readProfitabilityJournal();
  const profitabilityTicketStore = bundle?.profitabilityTicketStore || readProfitabilityTicketStore();
  const lastReport = isArtifactCompatible(bundle?.lastReport) ? bundle.lastReport : null;
  const lastWatchlist = isArtifactCompatible(bundle?.lastWatchlist) ? bundle.lastWatchlist : null;
  const experimentReport = bundle?.experimentReport || readLatestExperimentReport();
  const pilotSummary = buildProfitabilityPilotSummary(profitabilityJournal.entries, {
    ticketStore: profitabilityTicketStore,
    now,
  });
  const profitabilityTickets = buildProfitabilityTicketSummary(profitabilityTicketStore, { now });
  const profitabilityJournalSummary = buildProfitabilityJournalSummary(profitabilityJournal);
  const artifactHealth = buildArtifactHealth({
    strategies,
    lastWatchlist,
  });
  const operatorConsole = buildOperatorConsoleSnapshot({
    now,
    ticketStore: profitabilityTicketStore,
    journal: profitabilityJournal,
    pilotSummary,
    experimentReport,
    artifactHealth,
    strategies,
    lastWatchlist,
  });

  return {
    generatedAt: nowIso(),
    profitabilityProfileId: PROFITABILITY_PROFILE_ID,
    market: DEFAULT_MARKET,
    marketLabel: "Crypto Profitability Pilot",
    exchange: DEFAULT_EXCHANGE,
    marketType: DEFAULT_MARKET_TYPE,
    sessionMode: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.sessionMode,
    alertWindows: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows),
    defaultConfig: clone(DEFAULT_CRYPTO_DAY_TRADING_CONFIG),
    strategies,
    scoreboard: shared.buildStrategyScoreboard({
      strategies,
      backtests: bundle?.backtests || loadBacktestSummaries(),
      paperSummaries,
    }),
    paperAccount: bundle?.paperAccount || broker.getAccountSummary({ accountId }),
    paperSummaries,
    lastReport,
    lastWatchlist,
    lastImport: bundle?.lastImport || readJson(IMPORT_REPORT_PATH, null),
    operatingPlan: bundle?.operatingPlan || buildOperatingPlan(),
    pilotSummary,
    profitabilityJournal: profitabilityJournalSummary,
    profitabilityTickets,
    artifactHealth,
    experimentReport,
    operatorConsole,
  };
}

// ---------------------------------------------------------------------------
// Trade-Level Performance Forensics
// Takes backtest results with enriched trade context (regime, HTF trend,
// session phase at entry) and produces dimensional breakdowns of performance.
// Surfaces which filter combinations actually make money vs. which are dead weight.
// ---------------------------------------------------------------------------

function buildTradeForensics(backtestResult) {
  const trades = backtestResult?.trades || [];
  if (trades.length === 0) {
    return {
      generatedAt: nowIso(),
      strategyId: backtestResult?.strategyId || null,
      tradeCount: 0,
      dimensions: {},
      summary: null,
    };
  }

  function aggregateTrades(filteredTrades) {
    if (filteredTrades.length === 0) return null;
    const wins = filteredTrades.filter((t) => t.netReturnFraction > 0);
    const losses = filteredTrades.filter((t) => t.netReturnFraction < 0);
    const totalReturn = filteredTrades.reduce((s, t) => s + t.netReturnFraction, 0);
    const grossProfit = wins.reduce((s, t) => s + t.netReturnFraction, 0);
    const grossLoss = Math.abs(losses.reduce((s, t) => s + t.netReturnFraction, 0));
    const avgReturn = totalReturn / filteredTrades.length;
    const avgWin = wins.length > 0 ? grossProfit / wins.length : 0;
    const avgLoss = losses.length > 0 ? grossLoss / losses.length : 0;
    return {
      tradeCount: filteredTrades.length,
      winRate: round(wins.length / filteredTrades.length, 4),
      totalReturn: round(totalReturn, 6),
      avgReturn: round(avgReturn, 6),
      avgWin: round(avgWin, 6),
      avgLoss: round(avgLoss, 6),
      profitFactor: grossLoss > 0 ? round(grossProfit / grossLoss, 4) : grossProfit > 0 ? null : 0,
      expectancy: round(avgReturn, 6),
      payoffRatio: avgLoss > 0 ? round(avgWin / avgLoss, 4) : null,
    };
  }

  function buildDimension(dimensionKey, extractValue) {
    const buckets = {};
    for (const trade of trades) {
      const value = extractValue(trade) || "unknown";
      if (!buckets[value]) buckets[value] = [];
      buckets[value].push(trade);
    }
    const breakdown = {};
    for (const [key, bucket] of Object.entries(buckets)) {
      breakdown[key] = aggregateTrades(bucket);
    }
    // Rank buckets by expectancy
    const ranked = Object.entries(breakdown)
      .filter(([, stats]) => stats != null)
      .sort((a, b) => (b[1].expectancy || 0) - (a[1].expectancy || 0))
      .map(([key, stats]) => ({ value: key, ...stats }));
    return { dimensionKey, breakdown, ranked };
  }

  const dimensions = {
    regime: buildDimension("regime", (t) => t.entryRegime),
    htfTrend: buildDimension("htfTrend", (t) => t.entryHtfTrend),
    sessionPhase: buildDimension("sessionPhase", (t) => t.entrySessionPhase),
    exitReason: buildDimension("exitReason", (t) => t.exitReason),
    signalStrength: buildDimension("signalStrength", (t) => {
      const sv = Math.abs(t.signalValue || 0);
      if (sv >= 0.85) return "very_strong";
      if (sv >= 0.72) return "strong";
      if (sv >= 0.6) return "moderate";
      return "weak";
    }),
    atrSizing: buildDimension("atrSizing", (t) => {
      if (t.effectiveStopFraction != null && t.effectiveTargetFraction != null && t.entryAtr14 > 0) {
        const entryPrice = t.entryPrice || 1;
        const atrPctOfPrice = t.entryAtr14 / entryPrice;
        const isAtrDriven = Math.abs(t.effectiveStopFraction - atrPctOfPrice) < atrPctOfPrice * 0.5;
        return isAtrDriven ? "atr_dynamic" : "fixed_fraction";
      }
      return "fixed_fraction";
    }),
  };

  // Cross-dimensional: best and worst combinations
  const crossCombos = {};
  for (const trade of trades) {
    const key = `${trade.entryRegime || "?"}|${trade.entryHtfTrend || "?"}|${trade.entrySessionPhase || "?"}`;
    if (!crossCombos[key]) crossCombos[key] = [];
    crossCombos[key].push(trade);
  }
  const crossBreakdown = {};
  for (const [key, bucket] of Object.entries(crossCombos)) {
    if (bucket.length >= 3) { // Only report combos with enough trades
      crossBreakdown[key] = aggregateTrades(bucket);
    }
  }
  const crossRanked = Object.entries(crossBreakdown)
    .filter(([, stats]) => stats != null)
    .sort((a, b) => (b[1].expectancy || 0) - (a[1].expectancy || 0))
    .map(([key, stats]) => {
      const [regime, htf, phase] = key.split("|");
      return { regime, htfTrend: htf, sessionPhase: phase, ...stats };
    });

  return {
    generatedAt: nowIso(),
    strategyId: backtestResult?.strategyId || null,
    tradeCount: trades.length,
    summary: aggregateTrades(trades),
    dimensions,
    crossDimensional: {
      best: crossRanked.slice(0, 5),
      worst: crossRanked.slice(-5).reverse(),
    },
  };
}

// ---------------------------------------------------------------------------
// Filter Validation Harness
// Runs the same strategy twice — once with the profitability filters active
// (regime, HTF, session phase) and once with filters bypassed — then compares
// key metrics to determine whether the filters improve out-of-sample results.
// ---------------------------------------------------------------------------

function runFilterValidation(options = {}) {
  const strategy = options.strategy;
  const bars = options.bars || [];
  const feesFraction = options.feesFraction || DEFAULT_CRYPTO_DAY_TRADING_CONFIG.feesFraction;
  const config = options.config || DEFAULT_CRYPTO_DAY_TRADING_CONFIG;
  const windowMode = options.windowMode || config.sessionMode;

  if (!strategy || bars.length < 100) {
    return { error: "Insufficient data or missing strategy for filter validation" };
  }

  // Run 1: With all profitability filters active (default behavior)
  const enrichedFiltered = enrichBarsWithSignals(bars, strategy, config, windowMode);
  const filteredBacktest = shared.runBacktest({
    strategySpec: strategy,
    priceSeries: enrichedFiltered,
    feesFraction,
  });
  const filteredForensics = buildTradeForensics(filteredBacktest);

  // Run 2: With filters bypassed — temporarily modify the enriched bars to restore
  // signals that were zeroed by the profitability filters.
  // We do this by re-enriching with a "passthrough" wrapper that keeps all
  // signals at their pre-filter values. The simplest approach: enrich bars with
  // a modified strategy whose signal family doesn't match any whitelist rules,
  // effectively treating it as an unknown family that passes through all filters.
  // However, that won't work because the signal computation is per-family.
  //
  // Better approach: re-enrich the bars, then for each bar that has a
  // regime_mismatch/htf_counter_trend/session_phase_weak blocker, we know
  // the original family-level signal was non-zero but got zeroed. We can't
  // recover the exact pre-filter signal value without re-running the family
  // signal computation. So instead, we run the full enrichment twice: once
  // normally (already done above), and once with the filters disabled by
  // temporarily replacing the filter functions.
  //
  // Cleanest approach: run enrichBarsWithSignals normally to get all indicators,
  // then re-run the backtest with a lowered signal threshold to capture
  // signals that the phase multiplier dampened. For regime/HTF blocks, we
  // detect which bars had non-zero pre-filter signals by checking if the bar
  // was tradeable AND had all family-specific conditions met but got blocked
  // only by the new filters.
  //
  // Actually, the simplest correct approach: build the unfiltered bars by
  // copying the filtered bars and restoring signals that were blocked only
  // by the new profitability filters.
  const unfilteredBars = enrichedFiltered.map((bar) => {
    const blockers = bar.indicators?.regimeBlockers || [];
    const onlyNewFiltersBlocked = blockers.length > 0 &&
      blockers.every((b) => b === "regime_mismatch" || b === "htf_counter_trend" || b === "session_phase_weak");
    if (!onlyNewFiltersBlocked) return bar;
    // This bar was blocked only by new filters. We can't recover the exact
    // signal value, but we know it was tradeable pre-filter. Use a synthetic
    // signal at the strategy's threshold to simulate what would have happened.
    const signalName = String(strategy.simulation?.entrySignal || "");
    const threshold = strategy.simulation?.useSignalStrengthThreshold || 0.7;
    return {
      ...bar,
      signals: {
        ...bar.signals,
        [signalName]: bar.indicators?.tradeable ? threshold : 0,
      },
    };
  });

  const unfilteredBacktest = shared.runBacktest({
    strategySpec: strategy,
    priceSeries: unfilteredBars,
    feesFraction,
  });
  const unfilteredForensics = buildTradeForensics(unfilteredBacktest);

  // Compare metrics
  const fs = filteredBacktest.summary;
  const us = unfilteredBacktest.summary;
  const improvement = {
    tradeReduction: us.tradeCount > 0 ? round(1 - fs.tradeCount / us.tradeCount, 4) : 0,
    winRateDelta: round((fs.winRate || 0) - (us.winRate || 0), 4),
    profitFactorDelta: (fs.profitFactor != null && us.profitFactor != null)
      ? round(fs.profitFactor - us.profitFactor, 4) : null,
    returnDelta: round((fs.totalNetReturnFraction || 0) - (us.totalNetReturnFraction || 0), 6),
    maxDrawdownDelta: round((fs.maxDrawdownFraction || 0) - (us.maxDrawdownFraction || 0), 6),
    filtersHelpful: (
      (fs.winRate || 0) >= (us.winRate || 0) &&
      (fs.totalNetReturnFraction || 0) >= (us.totalNetReturnFraction || 0) * 0.9 &&
      (fs.maxDrawdownFraction || 0) <= (us.maxDrawdownFraction || 0) * 1.1
    ),
  };

  // Count how many signals each filter blocked
  const filterStats = { regime_mismatch: 0, htf_counter_trend: 0, session_phase_weak: 0 };
  for (const bar of enrichedFiltered) {
    for (const blocker of (bar.indicators?.regimeBlockers || [])) {
      if (blocker in filterStats) filterStats[blocker] += 1;
    }
  }

  return {
    generatedAt: nowIso(),
    strategyId: strategy.strategyId,
    barCount: bars.length,
    filtered: {
      summary: fs,
      forensics: filteredForensics,
    },
    unfiltered: {
      summary: us,
      forensics: unfilteredForensics,
    },
    improvement,
    filterStats,
  };
}

const __internal = {
  paths: {
    DATA_ROOT,
    RAW_DOWNLOADS_DIR,
    NORMALIZED_1M_DIR,
    DERIVED_5M_DIR,
    STRATEGIES_PATH,
    LEDGER_PATH,
    REPORT_PATH,
    WATCHLIST_PATH,
    BACKTEST_DIR,
    EXPERIMENTS_DIR,
    EXPERIMENT_REPORT_PATH,
    IMPORT_REPORT_PATH,
    PROFITABILITY_JOURNAL_PATH,
    PROFITABILITY_TICKETS_PATH,
  },
  DEFAULT_CRYPTO_DAY_TRADING_CONFIG,
  PROFITABILITY_PROFILE_ID,
  buildCryptoManagedStrategy,
  loadStrategies,
  saveStrategies,
  buildOperatingPlan,
  buildProfitabilityPilotSummary,
  buildProfitabilityJournalSummary,
  buildProfitabilityTicketSummary,
  buildArtifactHealth,
  buildOperatorConsoleSnapshot,
  readProfitabilityJournal,
  readProfitabilityTicketStore,
  readLatestExperimentReport,
  appendProfitabilityJournalEntry,
  requestProfitabilityPreflightTicket,
  loadNormalizedBars,
  saveNormalizedBars,
  resampleOneMinuteBarsToFiveMinutes,
  enrichBarsWithSignals,
  computeAtrSeries,
  computeRegimeClassification,
  computeHtfSeries,
  classifySessionPhase,
  getSessionPhaseMultiplier,
  isRegimeAllowed,
  isHtfBlocked,
  REGIME_FAMILY_WHITELIST,
  HTF_COUNTER_TREND_RULES,
  SESSION_PHASE_MULTIPLIERS,
  resampleBars,
  buildTradeForensics,
  runFilterValidation,
  FROZEN_CRYPTO_FAMILIES,
  CRYPTO_EXPERIMENT_LIBRARY,
  importHistoryForSymbol,
  importCryptoDayTradingHistory,
  loadCryptoMarketDataForStrategy,
  classifyScheduledWindow,
  classifyWindow,
  computeSessionOpeningRangeContexts,
  normalizeWindowMode,
  normalizeBarsSelection,
  resolveExperimentWindowModes,
};

module.exports = {
  DEFAULT_DAY_TRADING_CONFIG: DEFAULT_CRYPTO_DAY_TRADING_CONFIG,
  getDayTradingSnapshot,
  runDayTradingValidation,
  buildMorningWatchlist,
  runDayTradingExperiments,
  importCryptoDayTradingHistory,
  appendProfitabilityJournalEntry,
  requestProfitabilityPreflightTicket,
  __internal,
};
