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
const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const TRADING_WEEKDAYS = new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]);
const VALID_WINDOW_MODES = new Set(["all_hours", "scheduled_windows", "denver_core"]);
const RESEARCH_WINDOW_MODES = ["scheduled_windows", "denver_core", "all_hours"];
const FROZEN_CRYPTO_FAMILIES = new Set([
  "crypto_range_mean_reversion",
  "crypto_trend_continuation",
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
  feesFraction: 0.0005,
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
  crypto_range_mean_reversion: {
    signalThresholds: [0.64, 0.7, 0.76],
    takeProfitFractions: [0.0055, 0.0065, 0.0075],
    stopLossFractions: [0.0035, 0.0045, 0.0055],
    maxHoldBars: [6, 8, 10],
  },
  crypto_trend_continuation: {
    signalThresholds: [0.66, 0.72, 0.78],
    takeProfitFractions: [0.008, 0.0095, 0.011],
    stopLossFractions: [0.004, 0.005, 0.006],
    maxHoldBars: [8, 12, 16],
  },
};

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

function buildProfitabilityJournalSchema() {
  return [
    { key: "tradeTimestamp", label: "Trade time", required: true },
    { key: "sessionLabel", label: "Session", required: true },
    { key: "symbol", label: "Coin", required: true },
    { key: "regime", label: "Regime", required: true },
    { key: "setupId", label: "Setup ID", required: true },
    { key: "side", label: "Side", required: true },
    { key: "plannedEntryPrice", label: "Planned entry", required: true },
    { key: "stopPrice", label: "Stop", required: true },
    { key: "targetPrice", label: "Target", required: true },
    { key: "orderType", label: "Order type", required: true },
    { key: "sizeUsd", label: "Size (USD)", required: true },
    { key: "feesUsd", label: "Fees (USD)", required: true },
    { key: "spreadSlippageUsd", label: "Spread + slippage (USD)", required: true },
    { key: "pnlR", label: "Realized PnL (R)", required: true },
    { key: "pnlUsd", label: "Realized PnL (USD)", required: true },
    { key: "screenshotPath", label: "Screenshot path", required: true },
    { key: "ruleAdherenceScore", label: "Rule adherence", required: true },
    { key: "mistakeTag", label: "Mistake tag", required: true },
    { key: "note", label: "Post-trade note", required: true },
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
    entries: Array.isArray(stored?.entries) ? stored.entries : [],
  };
}

function appendProfitabilityJournalEntry(input = {}) {
  const journal = readProfitabilityJournal();
  const entry = {
    entryId: `pilot_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    loggedAt: nowIso(),
    tradeTimestamp: String(input.tradeTimestamp || input.timestamp || nowIso()),
    sessionLabel: String(input.sessionLabel || "Denver Core"),
    symbol: String(input.symbol || "").toUpperCase(),
    regime: String(input.regime || "").toLowerCase(),
    setupId: String(input.setupId || ""),
    side: String(input.side || "").toLowerCase(),
    plannedEntryPrice: Number(input.plannedEntryPrice),
    stopPrice: Number(input.stopPrice),
    targetPrice: Number(input.targetPrice),
    orderType: String(input.orderType || ""),
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

  journal.entries.push(entry);
  journal.generatedAt = nowIso();
  atomicWriteJsonSync(PROFITABILITY_JOURNAL_PATH, journal);
  return {
    journal,
    entry,
    summary: buildProfitabilityPilotSummary(journal.entries),
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

function buildProfitabilityPilotSummary(entries = []) {
  const allEntries = Array.isArray(entries) ? entries.slice() : [];
  const phaseOneEntries = allEntries.filter((entry) => (
    String(entry.setupId || "") === "btcusdt-crypto-range-mean-reversion" &&
    String(entry.symbol || "").toUpperCase() === "BTCUSDT"
  ));
  const tradeCount = phaseOneEntries.length;
  const wins = phaseOneEntries.filter((entry) => Number(entry.pnlR || 0) > 0).length;
  const losses = phaseOneEntries.filter((entry) => Number(entry.pnlR || 0) < 0).length;
  const expectancyR = tradeCount > 0
    ? phaseOneEntries.reduce((sum, entry) => sum + Number(entry.pnlR || 0), 0) / tradeCount
    : null;
  const netPnlUsd = phaseOneEntries.reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const profitFactor = computeProfitFactorFromEntries(phaseOneEntries);
  const ruleAdherenceRate = tradeCount > 0
    ? phaseOneEntries.reduce((sum, entry) => sum + Number(entry.ruleAdherenceScore || 0), 0) / tradeCount / 100
    : null;
  const maxDrawdownR = computeMaxDrawdownR(phaseOneEntries);
  const grossPositivePnl = phaseOneEntries
    .filter((entry) => Number(entry.pnlUsd || 0) > 0)
    .reduce((sum, entry) => sum + Number(entry.pnlUsd || 0), 0);
  const dominantTradePnl = phaseOneEntries.reduce((best, entry) => (
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
      actual: `${maxDrawdownR.toFixed(2)}R`,
    },
    {
      id: "outlier",
      label: "Top trade <= 20% of gross PnL",
      target: "<= 20%",
      passed: dominantTradeShare != null && dominantTradeShare <= 0.2,
      actual: dominantTradeShare == null ? "-" : `${(dominantTradeShare * 100).toFixed(1)}%`,
    },
  ];

  return {
    profileId: PROFITABILITY_PROFILE_ID,
    phase: tradeCount >= 30 && gates.every((gate) => gate.passed) ? "phase_2_ready" : "phase_1_btc_only",
    progress: {
      completedTrades: tradeCount,
      targetTrades: 30,
      remainingTrades: Math.max(0, 30 - tradeCount),
    },
    journalStats: {
      totalEntries: allEntries.length,
      phaseOneEntries: tradeCount,
      wins,
      losses,
      expectancyR,
      profitFactor,
      ruleAdherenceRate,
      netPnlUsd,
      maxDrawdownR,
      dominantTradeShare,
    },
    breakdownByRegime: buildEntryBreakdown(allEntries, "regime"),
    breakdownBySetup: buildEntryBreakdown(allEntries, "setupId"),
    gates,
    nextUnlock: tradeCount >= 30 && gates.every((gate) => gate.passed)
      ? "Enable BTC and ETH trend continuation for phase 2."
      : "Keep BTC-only mean reversion live and finish the 30-trade pilot.",
  };
}

function buildOperatingPlan() {
  return {
    profileId: PROFITABILITY_PROFILE_ID,
    objective: "Prove a repeatable BTC-first edge net of fees and slippage before unlocking ETH or SOL.",
    activeSetupId: "btcusdt-crypto-range-mean-reversion",
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
      liveNow: ["BTCUSDT"],
      nextPhase: ["BTCUSDT", "ETHUSDT"],
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
    regimeChecklist: {
      range: [
        "BTC is still inside session or prior-session range.",
        "ETF, basis, and funding backdrop is mixed or muted.",
        "No fresh catalyst is pushing price away from VWAP.",
      ],
      trend: [
        "BTC breaks and holds above session structure with expanding range or volume.",
        "Only continuation setups are allowed; stop fading every move.",
        "ETH can mirror only after BTC phase 1 passes.",
      ],
      event: [
        "Any exploit, macro shock, or abnormal expansion locks new trades for 30 minutes.",
        "BTC and ETH only. SOL stays no-trade unless paper review explicitly unlocks it.",
      ],
    },
    journalTemplate: {
      path: PROFITABILITY_JOURNAL_PATH,
      fields: buildProfitabilityJournalSchema(),
    },
  };
}

function isArtifactCompatible(payload) {
  return payload && payload.profitabilityProfileId === PROFITABILITY_PROFILE_ID;
}

function buildCryptoManagedStrategy(options = {}) {
  const symbol = String(options.symbol || "BTCUSDT").toUpperCase();
  const baseAsset = symbol.replace(/USDT$/i, "").toLowerCase();
  const strategyKind = String(options.strategyKind || "range_mean_reversion");
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
        takeProfitFraction: 0.0095,
        stopLossFraction: 0.005,
        maxHoldBars: 12,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: symbol === "BTCUSDT" ? 0.72 : 0.74,
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
      takeProfitFraction: 0.0065,
      stopLossFraction: 0.0045,
      maxHoldBars: 8,
      cooldownBars: 4,
      maxConcurrentPositions: 1,
      useSignalStrengthThreshold: 0.7,
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
    strategyKind: "range_mean_reversion",
    status: "paper_candidate",
    unlockPhase: "phase_1",
    maxPositionFraction: 0.35,
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
    pilotSummary: buildProfitabilityPilotSummary(profitabilityJournal.entries),
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
      });
      continue;
    }
    existing.high = Math.max(existing.high, bar.high);
    existing.low = Math.min(existing.low, bar.low);
    existing.close = bar.close;
    existing.volume += Number(bar.volume || 0);
    existing.quoteVolume += Number(bar.quoteVolume || 0);
    existing.tradeCount += Number(bar.tradeCount || 0);
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

function computeSessionOpeningRangeHighs(bars, openingRangeBars, getSessionKey) {
  let currentSession = null;
  let sessionStartIndex = -1;
  let openingRangeHigh = null;
  return bars.map((bar, index) => {
    const sessionKey = getSessionKey(bar.timestamp);
    if (!sessionKey) {
      currentSession = null;
      sessionStartIndex = -1;
      openingRangeHigh = null;
      return null;
    }
    if (sessionKey !== currentSession) {
      currentSession = sessionKey;
      sessionStartIndex = index;
      openingRangeHigh = Number(bar.high);
    } else if ((index - sessionStartIndex) < openingRangeBars) {
      openingRangeHigh = Math.max(Number(openingRangeHigh || Number.NEGATIVE_INFINITY), Number(bar.high));
    }
    return openingRangeHigh;
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
  const getSessionKey = (timestamp) => buildWindowSessionKey(timestamp, { config, windowMode: normalizedWindowMode });
  const vwap = computeSessionVwapSeries(bars, getSessionKey);
  const sessionContexts = computeSessionRangeContexts(bars, getSessionKey);
  let currentSessionKey = null;
  let currentSessionStartIndex = -1;

  return bars.map((bar, index) => {
    const priorClose = index > 0 ? closes[index - 1] : null;
    const sessionKey = getSessionKey(bar.timestamp);
    if (sessionKey !== currentSessionKey) {
      currentSessionKey = sessionKey;
      currentSessionStartIndex = sessionKey ? index : -1;
    }
    const window = classifyWindow(bar.timestamp, { config, windowMode: normalizedWindowMode });
    const barsSinceSessionStart = sessionKey && currentSessionStartIndex >= 0 ? (index - currentSessionStartIndex) : null;
    const volumeAverage = sma(volumes, 20, index);
    const volumeRatio = volumeAverage && volumeAverage > 0 ? volumes[index] / volumeAverage : null;
    const pctChange = priorClose && priorClose > 0 ? (closes[index] - priorClose) / priorClose : 0;
    const sessionContext = sessionContexts[index];
    const priorContext = (
      index > 0 &&
      sessionKey != null &&
      sessionKey === getSessionKey(bars[index - 1].timestamp)
    ) ? sessionContexts[index - 1] : null;
    const sessionHighBeforeBar = priorContext?.sessionHigh ?? sessionContext?.sessionHigh ?? null;
    const sessionLowBeforeBar = priorContext?.sessionLow ?? sessionContext?.sessionLow ?? null;
    const sessionRangeWidth = (
      Number.isFinite(sessionHighBeforeBar) &&
      Number.isFinite(sessionLowBeforeBar) &&
      closes[index] > 0
    ) ? ((sessionHighBeforeBar - sessionLowBeforeBar) / closes[index]) : null;
    const candleRange = Math.max(Number(bar.high) - Number(bar.low), closes[index] * 0.0003);
    const rejectionStrength = candleRange > 0 ? ((Number(bar.close) - Number(bar.low)) / candleRange) : 0;
    const priorSessionLow = sessionContext?.priorSessionLow ?? null;
    const priorSessionHigh = sessionContext?.priorSessionHigh ?? null;
    let signalValue = 0;

    if (!window.active || !sessionKey) {
      signalValue = 0;
    } else if (signalName === "crypto_range_mean_reversion") {
      const nearSessionLow = Number.isFinite(sessionLowBeforeBar)
        ? ((closes[index] - sessionLowBeforeBar) / closes[index]) <= 0.0018
        : false;
      const nearPriorSessionLow = Number.isFinite(priorSessionLow)
        ? Math.abs((closes[index] - priorSessionLow) / closes[index]) <= 0.0022
        : false;
      const rejectionCandle = closes[index] > Number(bar.open) && rejectionStrength >= 0.55;
      const rsiRecovering = rsi14[index] != null && rsi14[index] >= 36 && rsi14[index] <= 58;
      const nearVwap = vwap[index] != null && closes[index] <= (vwap[index] * 1.0025);
      const containedVolume = volumeRatio == null || volumeRatio <= 1.8;
      const insideHealthyRange = sessionRangeWidth != null && sessionRangeWidth >= 0.003 && sessionRangeWidth <= 0.02;
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 6 && barsSinceSessionStart <= 36;
      signalValue = (
        sessionTimingOkay &&
        insideHealthyRange &&
        nearVwap &&
        containedVolume &&
        rsiRecovering &&
        rejectionCandle &&
        (nearSessionLow || nearPriorSessionLow)
      ) ? Math.min(1, 0.58 + Math.min(Math.abs(pctChange) * 30, 0.18) + Math.min(rejectionStrength * 0.2, 0.18)) : 0;
    } else if (signalName === "crypto_trend_continuation") {
      const trendOkay = ema20[index] != null && ema50[index] != null && ema20[index] > ema50[index];
      const heldAboveFastTrend = ema20[index] != null && closes[index] > ema20[index];
      const brokePriorSessionHigh = Number.isFinite(priorSessionHigh) &&
        closes[index] > (priorSessionHigh * 1.0005) &&
        priorClose != null &&
        priorClose <= (priorSessionHigh * 1.001);
      const rsiOkay = rsi14[index] != null && rsi14[index] >= 54 && rsi14[index] <= 74;
      const volumeBoost = volumeRatio != null && volumeRatio >= 1.05;
      const sessionTimingOkay = barsSinceSessionStart != null && barsSinceSessionStart >= 6 && barsSinceSessionStart <= 38;
      signalValue = (trendOkay && heldAboveFastTrend && brokePriorSessionHigh && rsiOkay && volumeBoost && sessionTimingOkay)
        ? Math.min(1, 0.6 + Math.max(0, pctChange * 45) + Math.min((volumeRatio || 0) / 6, 0.18))
        : 0;
    } else if (signalName === "crypto_event_watch") {
      const abnormalRange = sessionRangeWidth != null && sessionRangeWidth >= 0.018;
      const volumeShock = volumeRatio != null && volumeRatio >= 1.7;
      signalValue = (abnormalRange && volumeShock)
        ? Math.min(1, 0.62 + Math.min((volumeRatio || 0) / 6, 0.22))
        : 0;
    }

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
        sessionVwap: round(vwap[index], 6),
        sessionRangeHigh: round(sessionContext?.sessionHigh, 6),
        sessionRangeLow: round(sessionContext?.sessionLow, 6),
        priorSessionHigh: round(priorSessionHigh, 6),
        priorSessionLow: round(priorSessionLow, 6),
        sessionRangeMidpoint: round(sessionContext?.sessionRangeMidpoint, 6),
        sessionRangeWidth: round(sessionRangeWidth, 6),
        barsSinceSessionStart,
        volumeRatio: round(volumeRatio, 4),
        rejectionStrength: round(rejectionStrength, 4),
        pctChange: round(pctChange, 6),
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

function compareWatchlistCandidates(left, right) {
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
  const clearlyNegative = Number(stats.netPnlFraction || 0) <= 0 && Number(stats.profitFactor || 0) < 1;
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
  const variants = [];

  for (const signalThreshold of thresholds) {
    for (const takeProfitFraction of takeProfits) {
      for (const stopLossFraction of stopLosses) {
        for (const maxHoldBars of holdBars) {
          const variantLabel = `thr${Math.round(signalThreshold * 100)}-tp${Math.round(takeProfitFraction * 10000)}-sl${Math.round(stopLossFraction * 10000)}-hold${maxHoldBars}`;
          const variantId = `${strategy.strategyId}-${variantLabel}`;
          variants.push({
            variantId,
            variantLabel,
            parameters: {
              signalThreshold: round(signalThreshold),
              takeProfitFraction: round(takeProfitFraction),
              stopLossFraction: round(stopLossFraction),
              maxHoldBars,
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
  const strategies = (useCustomStrategies ? options.strategies : loadStrategies())
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

  saveStrategies(nextStrategies);
  report.paperAccount = broker.getAccountSummary({ accountId });
  report.scoreboard = shared.buildStrategyScoreboard({
    strategies: loadStrategies(),
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
    researchMode: "control_first",
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
  const broker = bundle?.broker || new shared.PaperBroker({ ledgerPath: LEDGER_PATH, readOnly });
  broker.ensureAccount({
    accountId,
    startingCash: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.startingCash,
    createIfMissing: readOnly,
  });
  const paperSummaries = bundle?.paperSummaries || broker.getStrategySummaries({ accountId });
  const scoreboard = shared.buildStrategyScoreboard({
    strategies,
    backtests: bundle?.backtests || loadBacktestSummaries(),
    paperSummaries,
  });
  const strategyMap = new Map(strategies.map((strategy) => [strategy.strategyId, strategy]));
  const rankedCandidates = scoreboard.items
    .map((item) => ({ ...item, evidenceScore: round(scoreWatchlistEvidence(item), 4) }))
    .sort(compareWatchlistCandidates)
    .slice(0, limit);

  const items = [];
  for (const candidate of rankedCandidates) {
    const strategy = strategyMap.get(candidate.strategyId);
    if (!strategy) continue;
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

    let liveStatus = "inactive";
    let notifyNow = false;
    if (!trusted) {
      liveStatus = "untrusted_data";
    } else if (!dataFresh) {
      liveStatus = "stale";
    } else if (latestSignal && latestSignal.window.active && nowWindow.active && latestSessionKey != null && latestSessionKey === nowSessionKey && barsSinceTrigger != null && barsSinceTrigger <= DEFAULT_CRYPTO_DAY_TRADING_CONFIG.notifyLookbackBars) {
      liveStatus = barsSinceTrigger === 0 ? "triggered_now" : "triggered_recently";
      notifyNow = alertEligible;
    } else if (latestSignal && latestSignal.window.active) {
      liveStatus = "triggered_this_window";
    } else if (nowWindow.active && lastBarWindow.active && latestSessionKey === nowSessionKey) {
      liveStatus = "tracking";
    }

    items.push({
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
      dataFresh,
      currentDataTrusted: trusted,
      sessionWindowId: latestSignal?.window?.windowId || lastBarWindow.windowId || null,
      sessionWindowLabel: latestSignal?.window?.windowLabel || lastBarWindow.windowLabel || null,
      sessionActiveNow: nowWindow.active,
    });
  }

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
    morningWindow: {
      startEt: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows[0].startEt,
      cutoffEt: DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows[0].endEt,
      activeNow: nowWindow.active,
    },
    sessionWindow: getWindowSummary(now),
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
  const lastReport = isArtifactCompatible(bundle?.lastReport) ? bundle.lastReport : null;
  const lastWatchlist = isArtifactCompatible(bundle?.lastWatchlist) ? bundle.lastWatchlist : null;

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
    pilotSummary: bundle?.pilotSummary || buildProfitabilityPilotSummary(profitabilityJournal.entries),
    profitabilityJournal: {
      path: PROFITABILITY_JOURNAL_PATH,
      entryCount: Array.isArray(profitabilityJournal.entries) ? profitabilityJournal.entries.length : 0,
      schema: buildProfitabilityJournalSchema(),
    },
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
  },
  DEFAULT_CRYPTO_DAY_TRADING_CONFIG,
  PROFITABILITY_PROFILE_ID,
  buildCryptoManagedStrategy,
  loadStrategies,
  saveStrategies,
  buildOperatingPlan,
  buildProfitabilityPilotSummary,
  readProfitabilityJournal,
  appendProfitabilityJournalEntry,
  loadNormalizedBars,
  saveNormalizedBars,
  resampleOneMinuteBarsToFiveMinutes,
  enrichBarsWithSignals,
  importHistoryForSymbol,
  importCryptoDayTradingHistory,
  loadCryptoMarketDataForStrategy,
  classifyScheduledWindow,
  classifyWindow,
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
  __internal,
};
