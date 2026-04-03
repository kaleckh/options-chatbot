const fs = require("fs");
const path = require("path");
const https = require("https");

const DATA_ROOT = process.env.DAY_TRADING_DATA_ROOT
  ? path.resolve(process.env.DAY_TRADING_DATA_ROOT)
  : path.join(process.cwd(), "data", "day-trading");
const STRATEGIES_PATH = path.join(DATA_ROOT, "strategies.json");
const LEDGER_PATH = path.join(DATA_ROOT, "paper_trading_ledger.json");
const REPORT_PATH = path.join(DATA_ROOT, "trading_validation_report.json");
const BACKTEST_DIR = path.join(DATA_ROOT, "backtests");
const EXPERIMENTS_DIR = path.join(DATA_ROOT, "experiments");
const EXPERIMENT_REPORT_PATH = path.join(EXPERIMENTS_DIR, "latest.json");
const READ_ONLY_BUNDLE_CACHE = new Map();

const DEFAULT_ACCOUNT_ID = "paper-main";
const MANAGED_STRATEGY_OWNER = "options-chatbot-day-trading";
const DEFAULT_DAY_TRADING_CONFIG = {
  bars: 3120,
  startingCash: 10000,
  feesFraction: 0.0002,
  watchlistLimit: 4,
  morningStartEt: "09:30",
  morningCutoffEt: "11:30",
  notifyLookbackBars: 2,
  maxBarAgeMinutes: 20,
};
const ET_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  weekday: "short",
  hour12: false,
});

const VALID_STATUSES = new Set([
  "draft",
  "backtest_failed",
  "paper_candidate",
  "paper_live",
  "promotion_review",
  "candidate_live",
  "disabled",
]);

function buildManagedStrategy(options = {}) {
  const symbol = String(options.symbol || "SPY").toUpperCase();
  const category = symbol === "QQQ" ? "nasdaq-index-etf" : "s-and-p-index-etf";
  const liquidityFloor = symbol === "QQQ" ? 40000000 : 50000000;
  const strategyKind = String(options.strategyKind || "opening_range_breakout");
  const isOpeningRange = strategyKind === "opening_range_breakout";

  if (isOpeningRange) {
    return {
      version: 2,
      strategyId: `${symbol.toLowerCase()}-opening-range-breakout`,
      name: `${symbol} 5m Opening Range Breakout`,
      hypothesisSummary:
        `When ${symbol} breaks the first 30-minute range with aligned trend and volume, the morning move can continue far enough to justify a tight intraday momentum trade.`,
      venueType: "equities",
      status: "draft",
      marketUniverse: {
        symbols: [symbol],
        category,
        maxMarkets: 1,
      },
      signalInputs: [
        {
          name: "opening_range_breakout",
          type: "technical",
          source: "computed_signal",
          weight: 1,
        },
      ],
      entryRules: [
        `Enter long on the next open after ${symbol} closes above the opening range high.`,
        "Require short-term trend alignment and volume support before entry.",
      ],
      exitRules: [
        "Exit on 0.8% take profit.",
        "Exit on 0.4% stop loss.",
        "Exit after 10 bars if momentum stalls.",
      ],
      cooldownRules: [
        "Wait 4 bars after exit before taking another opening-range breakout trade.",
      ],
      sizing: {
        model: "fixed_fractional",
        maxPositionFraction: 0.12,
        riskPerTradeFraction: 0.006,
      },
      riskLimits: {
        maxDrawdownFraction: 0.08,
        maxDailyLossFraction: 0.015,
        maxOpenPositions: 1,
        maxLossPerTradeFraction: 0.006,
        minLiquidityUsd: liquidityFloor,
        maxSpreadFraction: 0.0008,
      },
      evaluationWindow: {
        timeframe: "5m",
        warmupBars: 6,
        minimumTrades: 16,
      },
      simulation: {
        direction: "long",
        entrySignal: "opening_range_breakout",
        entryExecution: "next_open",
        takeProfitFraction: 0.008,
        stopLossFraction: 0.004,
        maxHoldBars: 10,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.72,
      },
      metadata: {
        owner: MANAGED_STRATEGY_OWNER,
        tags: ["equities", symbol.toLowerCase(), "morning", "opening-range"],
      },
    };
  }

  return {
    version: 2,
    strategyId: `${symbol.toLowerCase()}-vwap-trend-reclaim`,
    name: `${symbol} 5m VWAP Reclaim`,
    hypothesisSummary:
      `${symbol} pullbacks that reclaim session VWAP inside a live uptrend can provide cleaner morning continuation entries than chasing fresh highs.`,
    venueType: "equities",
    status: "draft",
    marketUniverse: {
      symbols: [symbol],
      category,
      maxMarkets: 1,
    },
    signalInputs: [
      {
        name: "vwap_trend_reclaim",
        type: "technical",
        source: "computed_signal",
        weight: 1,
      },
    ],
    entryRules: [
      `Enter long on the next open after ${symbol} reclaims session VWAP while the short trend stays positive.`,
      "Require the reclaim to happen with stable spread and adequate liquidity.",
    ],
    exitRules: [
      "Exit on 0.6% take profit.",
      "Exit on 0.35% stop loss.",
      "Exit after 12 bars if the continuation fails.",
    ],
    cooldownRules: [
      "Wait 3 bars after exit before re-entering another VWAP reclaim trade.",
    ],
    sizing: {
      model: "fixed_fractional",
      maxPositionFraction: 0.1,
      riskPerTradeFraction: 0.005,
    },
    riskLimits: {
      maxDrawdownFraction: 0.07,
      maxDailyLossFraction: 0.015,
      maxOpenPositions: 1,
      maxLossPerTradeFraction: 0.005,
      minLiquidityUsd: liquidityFloor,
      maxSpreadFraction: 0.0008,
    },
    evaluationWindow: {
      timeframe: "5m",
      warmupBars: 24,
      minimumTrades: 16,
    },
    simulation: {
      direction: "long",
      entrySignal: "vwap_trend_reclaim",
      entryExecution: "next_open",
      takeProfitFraction: 0.006,
      stopLossFraction: 0.0035,
      maxHoldBars: 12,
      cooldownBars: 3,
      maxConcurrentPositions: 1,
      useSignalStrengthThreshold: 0.68,
    },
    metadata: {
      owner: MANAGED_STRATEGY_OWNER,
      tags: ["equities", symbol.toLowerCase(), "morning", "vwap"],
    },
  };
}

const DEFAULT_STRATEGIES = [
  buildManagedStrategy({ symbol: "SPY", strategyKind: "opening_range_breakout" }),
  buildManagedStrategy({ symbol: "QQQ", strategyKind: "opening_range_breakout" }),
  buildManagedStrategy({ symbol: "SPY", strategyKind: "vwap_trend_reclaim" }),
  buildManagedStrategy({ symbol: "QQQ", strategyKind: "vwap_trend_reclaim" }),
];

const DEFAULT_EXPERIMENT_LIBRARY = {
  opening_range_breakout: {
    signalThresholds: [0.66, 0.72, 0.78],
    takeProfitFractions: [0.006, 0.008, 0.01],
    stopLossFractions: [0.003, 0.004, 0.005],
    maxHoldBars: [8, 10, 12],
  },
  vwap_trend_reclaim: {
    signalThresholds: [0.62, 0.68, 0.74],
    takeProfitFractions: [0.0045, 0.006, 0.0075],
    stopLossFractions: [0.0025, 0.0035, 0.0045],
    maxHoldBars: [8, 12, 16],
  },
};

const DAY_TRADING_EXPERIMENT_PRESETS = {
  focus16: {
    opening_range_breakout: {
      variants: [
        { signalThreshold: 0.72, takeProfitFraction: 0.006, stopLossFraction: 0.004, maxHoldBars: 8 },
        { signalThreshold: 0.78, takeProfitFraction: 0.006, stopLossFraction: 0.004, maxHoldBars: 8 },
        { signalThreshold: 0.72, takeProfitFraction: 0.008, stopLossFraction: 0.004, maxHoldBars: 10 },
        { signalThreshold: 0.78, takeProfitFraction: 0.008, stopLossFraction: 0.004, maxHoldBars: 10 },
      ],
    },
    vwap_trend_reclaim: {
      variants: [
        { signalThreshold: 0.68, takeProfitFraction: 0.0045, stopLossFraction: 0.0035, maxHoldBars: 8 },
        { signalThreshold: 0.74, takeProfitFraction: 0.0045, stopLossFraction: 0.0035, maxHoldBars: 8 },
        { signalThreshold: 0.68, takeProfitFraction: 0.006, stopLossFraction: 0.0035, maxHoldBars: 12 },
        { signalThreshold: 0.74, takeProfitFraction: 0.006, stopLossFraction: 0.0035, maxHoldBars: 12 },
      ],
    },
  },
};

function nowIso() {
  return new Date().toISOString();
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function round(value, digits = 6) {
  return Number.isFinite(value) ? Number(value.toFixed(digits)) : null;
}

function uniqueNumbers(values = []) {
  return [...new Set(
    values
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0)
      .map((value) => Number(value.toFixed(6))),
  )];
}

function percentToken(value) {
  if (!Number.isFinite(value)) return "na";
  return String(Math.round(value * 10000)).padStart(2, "0");
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

function assertValidStrategySpec(strategy) {
  if (!strategy || typeof strategy !== "object") {
    throw new Error("Strategy spec must be an object");
  }
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
  const defaultsById = new Map(DEFAULT_STRATEGIES.map((strategy) => [strategy.strategyId, strategy]));
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

function defaultVenueConfig() {
  return {
    feeFraction: 0.0002,
    halfSpreadFraction: 0.0002,
    slippageFraction: 0.00015,
    maxNotionalParticipationFraction: 0.08,
    minPrice: 0.01,
    maxPrice: Number.POSITIVE_INFINITY,
  };
}

function deriveLiquidityNotional(snapshot = {}, price = 0) {
  if (Number.isFinite(snapshot.availableLiquidityUsd)) return snapshot.availableLiquidityUsd;
  if (Number.isFinite(snapshot.volumeUsd)) return snapshot.volumeUsd * 0.08;
  if (Number.isFinite(snapshot.volume) && Number.isFinite(price) && price > 0) {
    return snapshot.volume * price * 0.08;
  }
  return 25000;
}

function simulateExecution(options = {}) {
  const side = String(options.side || "buy").toLowerCase();
  const requestedQuantity = Number(options.quantity);
  const referencePrice = Number(options.referencePrice);
  const snapshot = options.snapshot || {};
  const config = {
    ...defaultVenueConfig(),
    ...(options.executionConfig || {}),
  };

  if (!["buy", "sell"].includes(side)) throw new Error("simulateExecution requires buy or sell side");
  if (!Number.isFinite(requestedQuantity) || requestedQuantity <= 0) {
    throw new Error("simulateExecution requires positive quantity");
  }
  if (!Number.isFinite(referencePrice) || referencePrice <= 0) {
    throw new Error("simulateExecution requires positive referencePrice");
  }

  const requestedNotional = requestedQuantity * referencePrice;
  const liquidityNotional = deriveLiquidityNotional(snapshot, referencePrice);
  const maxFillNotional = Math.max(0, liquidityNotional * config.maxNotionalParticipationFraction);
  const fillRatio = requestedNotional <= 0 ? 0 : clamp(maxFillNotional / requestedNotional, 0, 1);
  const filledQuantity = requestedQuantity * fillRatio;

  const bestBid = Number.isFinite(snapshot.bestBid)
    ? snapshot.bestBid
    : referencePrice * (1 - config.halfSpreadFraction);
  const bestAsk = Number.isFinite(snapshot.bestAsk)
    ? snapshot.bestAsk
    : referencePrice * (1 + config.halfSpreadFraction);
  let fillPrice = side === "buy"
    ? bestAsk * (1 + config.slippageFraction)
    : bestBid * (1 - config.slippageFraction);
  fillPrice = clamp(fillPrice, config.minPrice, config.maxPrice);

  const notional = filledQuantity * fillPrice;
  const fees = notional * config.feeFraction;
  const rejected = filledQuantity <= 1e-12;

  return {
    side,
    requestedQuantity: round(requestedQuantity, 8),
    filledQuantity: round(filledQuantity, 8),
    fillRatio: round(fillRatio, 6),
    referencePrice: round(referencePrice, 8),
    fillPrice: round(fillPrice, 8),
    notional: round(notional, 8),
    fees: round(fees, 8),
    feeFraction: config.feeFraction,
    spreadFraction: round(config.halfSpreadFraction * 2, 6),
    slippageFraction: round(config.slippageFraction, 6),
    liquidityNotional: round(liquidityNotional, 6),
    status: rejected ? "rejected" : (fillRatio < 0.999 ? "partially_filled" : "filled"),
    rejectionReason: rejected ? "insufficient_liquidity" : null,
  };
}

class PaperBroker {
  constructor(options = {}) {
    this.ledgerPath = options.ledgerPath || LEDGER_PATH;
    this.readOnly = Boolean(options.readOnly);
    this.ledger = this._loadLedger();
  }

  _loadLedger() {
    const fallback = {
      version: 1,
      generatedAt: nowIso(),
      accounts: {},
      orders: [],
      fills: [],
    };
    return readJson(this.ledgerPath, fallback);
  }

  _saveLedger() {
    this.ledger.generatedAt = nowIso();
    atomicWriteJsonSync(this.ledgerPath, this.ledger);
  }

  _positionKey(strategyId, symbol) {
    return `${strategyId}::${symbol}`;
  }

  ensureAccount(options = {}) {
    const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID).trim();
    if (!accountId) throw new Error("accountId is required");

    if (!this.ledger.accounts[accountId]) {
      const startingCash = Number.isFinite(options.startingCash) ? Number(options.startingCash) : DEFAULT_DAY_TRADING_CONFIG.startingCash;
      if (this.readOnly || options.createIfMissing === false) {
        return {
          accountId,
          startingCash,
          cash: startingCash,
          realizedPnl: 0,
          feesPaid: 0,
          createdAt: nowIso(),
          updatedAt: nowIso(),
          positions: {},
        };
      }
      this.ledger.accounts[accountId] = {
        accountId,
        startingCash,
        cash: startingCash,
        realizedPnl: 0,
        feesPaid: 0,
        createdAt: nowIso(),
        updatedAt: nowIso(),
        positions: {},
      };
      this._saveLedger();
    }

    return clone(this.ledger.accounts[accountId]);
  }

  getAccount(accountId = DEFAULT_ACCOUNT_ID) {
    return clone(this.ensureAccount({ accountId }));
  }

  getAccountSummary(options = {}) {
    const account = this.getAccount(options.accountId || DEFAULT_ACCOUNT_ID);
    const markPrices = options.markPrices || {};
    const positions = Object.values(account.positions || {}).map((position) => {
      const markPrice = Number.isFinite(markPrices[position.symbol]) ? markPrices[position.symbol] : position.lastPrice;
      const unrealizedPnl = Number.isFinite(markPrice)
        ? (markPrice - position.avgEntryPrice) * position.quantity
        : 0;
      return {
        ...position,
        markPrice: Number.isFinite(markPrice) ? markPrice : null,
        unrealizedPnl: Number(unrealizedPnl.toFixed(6)),
      };
    });

    const totalUnrealizedPnl = positions.reduce((sum, position) => sum + position.unrealizedPnl, 0);
    const equity = account.cash
      + totalUnrealizedPnl
      + positions.reduce((sum, position) => sum + (position.quantity * position.avgEntryPrice), 0);

    return {
      accountId: account.accountId,
      startingCash: account.startingCash,
      cash: Number(account.cash.toFixed(6)),
      realizedPnl: Number(account.realizedPnl.toFixed(6)),
      feesPaid: Number((account.feesPaid || 0).toFixed(6)),
      totalUnrealizedPnl: Number(totalUnrealizedPnl.toFixed(6)),
      equity: Number(equity.toFixed(6)),
      positions,
    };
  }

  placeOrder(orderInput = {}) {
    const timestamp = orderInput.timestamp || nowIso();
    const accountId = String(orderInput.accountId || DEFAULT_ACCOUNT_ID).trim();
    const strategyId = String(orderInput.strategyId || "").trim();
    const symbol = String(orderInput.symbol || "").trim();
    const side = String(orderInput.side || "").trim().toLowerCase();
    const quantity = Number(orderInput.quantity);
    const price = Number(orderInput.price);

    if (!strategyId) throw new Error("strategyId is required");
    if (!symbol) throw new Error("symbol is required");
    if (!["buy", "sell"].includes(side)) throw new Error("side must be buy or sell");
    if (!Number.isFinite(quantity) || quantity <= 0) throw new Error("quantity must be a positive number");
    if (!Number.isFinite(price) || price <= 0) throw new Error("price must be a positive number");

    this.ensureAccount({ accountId, startingCash: orderInput.startingCash });
    const account = this.ledger.accounts[accountId];
    const positionKey = this._positionKey(strategyId, symbol);
    const currentPosition = account.positions[positionKey] || null;
    const orderId = `paper_order_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const execution = simulateExecution({
      side,
      quantity,
      referencePrice: price,
      snapshot: orderInput.market || {},
      executionConfig: orderInput.executionConfig || {},
    });

    const baseOrder = {
      orderId,
      accountId,
      strategyId,
      symbol,
      side,
      quantity: Number(quantity.toFixed(8)),
      requestedPrice: Number(price.toFixed(8)),
      filledQuantity: execution.filledQuantity,
      fillPrice: execution.fillPrice,
      fees: execution.fees,
      notional: execution.notional,
      status: execution.status,
      submittedAt: timestamp,
      metadata: orderInput.metadata || {},
    };

    if (execution.status === "rejected") {
      const rejectedOrder = { ...baseOrder, rejectionReason: execution.rejectionReason };
      this.ledger.orders.push(rejectedOrder);
      this._saveLedger();
      return { accepted: false, order: clone(rejectedOrder), account: this.getAccountSummary({ accountId }) };
    }

    const totalCashCost = execution.notional + (side === "buy" ? execution.fees : 0);
    if (side === "buy" && account.cash + 1e-9 < totalCashCost) {
      const rejectedOrder = { ...baseOrder, status: "rejected", rejectionReason: "insufficient_cash" };
      this.ledger.orders.push(rejectedOrder);
      this._saveLedger();
      return { accepted: false, order: clone(rejectedOrder), account: this.getAccountSummary({ accountId }) };
    }

    if (side === "sell" && (!currentPosition || currentPosition.quantity + 1e-9 < execution.filledQuantity)) {
      const rejectedOrder = { ...baseOrder, status: "rejected", rejectionReason: "insufficient_position" };
      this.ledger.orders.push(rejectedOrder);
      this._saveLedger();
      return { accepted: false, order: clone(rejectedOrder), account: this.getAccountSummary({ accountId }) };
    }

    let realizedPnl = 0;
    if (side === "buy") {
      const newQuantity = (currentPosition?.quantity || 0) + execution.filledQuantity;
      const previousCost = (currentPosition?.avgEntryPrice || 0) * (currentPosition?.quantity || 0);
      const avgEntryPrice = (previousCost + execution.notional + execution.fees) / newQuantity;
      account.cash -= (execution.notional + execution.fees);
      account.feesPaid = (account.feesPaid || 0) + execution.fees;
      account.positions[positionKey] = {
        strategyId,
        symbol,
        quantity: Number(newQuantity.toFixed(8)),
        avgEntryPrice: Number(avgEntryPrice.toFixed(8)),
        lastPrice: Number(execution.fillPrice.toFixed(8)),
        openedAt: currentPosition?.openedAt || timestamp,
        updatedAt: timestamp,
      };
    } else {
      realizedPnl = (execution.fillPrice - currentPosition.avgEntryPrice) * execution.filledQuantity - execution.fees;
      account.cash += (execution.notional - execution.fees);
      account.realizedPnl += realizedPnl;
      account.feesPaid = (account.feesPaid || 0) + execution.fees;
      const remainingQuantity = currentPosition.quantity - execution.filledQuantity;
      if (remainingQuantity <= 1e-9) {
        delete account.positions[positionKey];
      } else {
        account.positions[positionKey] = {
          ...currentPosition,
          quantity: Number(remainingQuantity.toFixed(8)),
          lastPrice: Number(execution.fillPrice.toFixed(8)),
          updatedAt: timestamp,
        };
      }
    }

    account.updatedAt = timestamp;

    const fill = {
      fillId: `paper_fill_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      orderId,
      accountId,
      strategyId,
      symbol,
      side,
      quantity: execution.filledQuantity,
      price: execution.fillPrice,
      notional: execution.notional,
      fees: execution.fees,
      realizedPnl: Number(realizedPnl.toFixed(8)),
      filledAt: timestamp,
    };

    this.ledger.orders.push(baseOrder);
    this.ledger.fills.push(fill);
    this._saveLedger();

    return {
      accepted: true,
      order: clone(baseOrder),
      fill: clone(fill),
      account: this.getAccountSummary({ accountId }),
    };
  }

  getStrategySummaries(options = {}) {
    const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
    const account = this.getAccountSummary({ accountId, markPrices: options.markPrices || {} });
    const fills = this.ledger.fills.filter((fill) => fill.accountId === accountId);
    const summaries = new Map();

    for (const fill of fills) {
      if (!summaries.has(fill.strategyId)) {
        summaries.set(fill.strategyId, {
          strategyId: fill.strategyId,
          tradeCount: 0,
          realizedPnl: 0,
          wins: 0,
          losses: 0,
          grossVolume: 0,
          openPositions: 0,
          unrealizedPnl: 0,
        });
      }
      const summary = summaries.get(fill.strategyId);
      summary.tradeCount += 1;
      summary.realizedPnl += Number(fill.realizedPnl || 0);
      summary.grossVolume += Number(fill.notional || 0);
      if (fill.side === "sell") {
        if (fill.realizedPnl > 0) summary.wins += 1;
        if (fill.realizedPnl < 0) summary.losses += 1;
      }
    }

    for (const position of account.positions) {
      if (!summaries.has(position.strategyId)) {
        summaries.set(position.strategyId, {
          strategyId: position.strategyId,
          tradeCount: 0,
          realizedPnl: 0,
          wins: 0,
          losses: 0,
          grossVolume: 0,
          openPositions: 0,
          unrealizedPnl: 0,
        });
      }
      const summary = summaries.get(position.strategyId);
      summary.openPositions += 1;
      summary.unrealizedPnl += Number(position.unrealizedPnl || 0);
    }

    return [...summaries.values()]
      .map((summary) => ({
        ...summary,
        realizedPnl: Number(summary.realizedPnl.toFixed(6)),
        unrealizedPnl: Number(summary.unrealizedPnl.toFixed(6)),
        grossVolume: Number(summary.grossVolume.toFixed(6)),
        winRate: summary.wins + summary.losses > 0
          ? Number((summary.wins / (summary.wins + summary.losses)).toFixed(4))
          : null,
      }))
      .sort((a, b) => b.realizedPnl - a.realizedPnl);
  }
}

function startOfUtcDay(isoString) {
  const date = isoString ? new Date(isoString) : new Date();
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function getTimeZoneDateParts(isoString, timeZone) {
  try {
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: timeZone || "UTC",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    });
    const parts = Object.fromEntries(
      formatter
        .formatToParts(new Date(isoString || Date.now()))
        .filter((part) => part.type !== "literal")
        .map((part) => [part.type, part.value]),
    );
    if (!parts.year || !parts.month || !parts.day) {
      return null;
    }
    return {
      year: Number(parts.year),
      month: Number(parts.month),
      day: Number(parts.day),
      weekday: String(parts.weekday || ""),
    };
  } catch {
    return null;
  }
}

function getPeriodKey(isoString, period = "day", timeZone = "UTC") {
  const parts = getTimeZoneDateParts(isoString, timeZone);
  if (!parts) return null;
  const dayKey = `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
  if (period === "day") return dayKey;
  if (period !== "week") return dayKey;
  const weekdayIndex = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(parts.weekday);
  if (weekdayIndex < 0) return dayKey;
  const mondayOffset = (weekdayIndex + 6) % 7;
  const mondayUtcMs = Date.UTC(parts.year, parts.month - 1, parts.day - mondayOffset);
  return new Date(mondayUtcMs).toISOString().slice(0, 10);
}

function sumRealizedPnlForDay(fills = [], accountId, dayStartMs) {
  return fills
    .filter((fill) => fill.accountId === accountId)
    .filter((fill) => {
      const ts = new Date(fill.filledAt || 0).getTime();
      return Number.isFinite(ts) && ts >= dayStartMs;
    })
    .reduce((sum, fill) => sum + Number(fill.realizedPnl || 0), 0);
}

function sumRealizedPnlForPeriod(fills = [], accountId, isoString, period = "day", timeZone = "UTC") {
  const targetKey = getPeriodKey(isoString, period, timeZone);
  if (!targetKey) return 0;
  return fills
    .filter((fill) => fill.accountId === accountId)
    .filter((fill) => getPeriodKey(fill.filledAt, period, timeZone) === targetKey)
    .reduce((sum, fill) => sum + Number(fill.realizedPnl || 0), 0);
}

function countClosingLossesForPeriod(fills = [], accountId, isoString, period = "day", timeZone = "UTC") {
  const targetKey = getPeriodKey(isoString, period, timeZone);
  if (!targetKey) return 0;
  return fills
    .filter((fill) => fill.accountId === accountId)
    .filter((fill) => String(fill.side || "").toLowerCase() === "sell")
    .filter((fill) => Number(fill.realizedPnl || 0) < 0)
    .filter((fill) => getPeriodKey(fill.filledAt, period, timeZone) === targetKey)
    .length;
}

function resolveStrategyDrawdownFraction(strategy, accountSummary = {}) {
  const equity = Number(accountSummary.equity || accountSummary.cash || 0);
  const startingCash = Number(accountSummary.startingCash || 0);
  if (!(equity > 0) || !(startingCash > 0)) {
    return 0;
  }
  return Math.max(0, (startingCash - equity) / startingCash);
}

function resolveDrawdownPositionMultiplier(strategy, accountSummary = {}) {
  const drawdownFraction = resolveStrategyDrawdownFraction(strategy, accountSummary);
  const reduceAt = Number(strategy?.riskLimits?.reduceSizeAtDrawdownFraction || 0);
  const reduceMultiplier = Number(strategy?.riskLimits?.reduceSizeMultiplier || 1);
  if (reduceAt > 0 && reduceMultiplier > 0 && reduceMultiplier < 1 && drawdownFraction >= reduceAt) {
    return reduceMultiplier;
  }
  return 1;
}

function resolvePositionFraction(strategy, priorDrawdownFraction = 0) {
  const maxPositionFraction = Number(strategy?.sizing?.maxPositionFraction || 0);
  const riskPerTradeFraction = Number(strategy?.sizing?.riskPerTradeFraction || maxPositionFraction || 0);
  const stopLossFraction = Number(strategy?.simulation?.stopLossFraction || 0);
  const usesStopBasedSizing = String(strategy?.sizing?.riskSizing || "").toLowerCase() === "stop_based";
  const reduceAt = Number(strategy?.riskLimits?.reduceSizeAtDrawdownFraction || 0);
  const reduceMultiplier = Number(strategy?.riskLimits?.reduceSizeMultiplier || 1);
  const drawdownMultiplier = (
    reduceAt > 0 &&
    reduceMultiplier > 0 &&
    reduceMultiplier < 1 &&
    priorDrawdownFraction >= reduceAt
  ) ? reduceMultiplier : 1;

  let positionFraction = riskPerTradeFraction;
  if (usesStopBasedSizing && stopLossFraction > 0) {
    positionFraction = riskPerTradeFraction / stopLossFraction;
  }

  if (maxPositionFraction > 0) {
    positionFraction = Math.min(positionFraction, maxPositionFraction);
  }

  return Math.max(0, positionFraction * drawdownMultiplier);
}

function evaluateTradeRisk(options = {}) {
  const strategy = options.strategy;
  const order = options.order || {};
  const accountSummary = options.accountSummary || {};
  const ledger = options.ledger || { fills: [] };
  const market = options.market || {};

  if (!strategy || !strategy.riskLimits) {
    return { allowed: false, reasons: ["missing_strategy_risk_limits"], context: {} };
  }

  const reasons = [];
  const quantity = Number(order.quantity || 0);
  const price = Number(order.price || 0);
  const notional = quantity * price;
  const equity = Number(accountSummary.equity || accountSummary.cash || 0);
  const positionFraction = equity > 0 ? notional / equity : 0;
  const timeZone = String(strategy?.metadata?.sessionTimeZone || "UTC");
  const currentPositions = Array.isArray(accountSummary.positions) ? accountSummary.positions : [];
  const strategyPositions = currentPositions.filter((position) => position.strategyId === strategy.strategyId);

  if (
    strategy.riskLimits.maxOpenPositions != null &&
    currentPositions.length >= strategy.riskLimits.maxOpenPositions &&
    strategyPositions.length === 0 &&
    String(order.side || "").toLowerCase() === "buy"
  ) {
    reasons.push("max_open_positions_reached");
  }

  if (
    strategy.sizing?.maxPositionFraction != null &&
    positionFraction > Number(strategy.sizing.maxPositionFraction) + 1e-9
  ) {
    reasons.push("position_size_exceeds_strategy_limit");
  }

  if (strategy.riskLimits.minLiquidityUsd != null) {
    const liquidityUsd = Number(market.availableLiquidityUsd || market.volumeUsd || 0);
    if (Number.isFinite(liquidityUsd) && liquidityUsd < Number(strategy.riskLimits.minLiquidityUsd)) {
      reasons.push("market_liquidity_below_minimum");
    }
  }

  if (
    strategy.riskLimits.maxSpreadFraction != null &&
    Number.isFinite(market.bestBid) &&
    Number.isFinite(market.bestAsk) &&
    Number(market.bestAsk) > 0
  ) {
    const spreadFraction = (Number(market.bestAsk) - Number(market.bestBid)) / Number(market.bestAsk);
    if (spreadFraction > Number(strategy.riskLimits.maxSpreadFraction)) {
      reasons.push("market_spread_above_maximum");
    }
  }

  const dayStartMs = startOfUtcDay(order.timestamp);
  const realizedPnlToday = sumRealizedPnlForDay(ledger.fills || [], accountSummary.accountId, dayStartMs);
  const dailyLossFraction = equity > 0 ? Math.abs(Math.min(0, realizedPnlToday)) / equity : 0;
  const realizedPnlWeek = sumRealizedPnlForPeriod(ledger.fills || [], accountSummary.accountId, order.timestamp, "week", timeZone);
  const weeklyLossFraction = equity > 0 ? Math.abs(Math.min(0, realizedPnlWeek)) / equity : 0;
  const dailyLosingTrades = countClosingLossesForPeriod(ledger.fills || [], accountSummary.accountId, order.timestamp, "day", timeZone);
  if (
    strategy.riskLimits.maxDailyLossFraction != null &&
    dailyLossFraction > Number(strategy.riskLimits.maxDailyLossFraction)
  ) {
    reasons.push("daily_loss_limit_breached");
  }
  if (
    strategy.riskLimits.maxWeeklyLossFraction != null &&
    weeklyLossFraction > Number(strategy.riskLimits.maxWeeklyLossFraction)
  ) {
    reasons.push("weekly_loss_limit_breached");
  }
  if (
    strategy.riskLimits.maxDailyLosingTrades != null &&
    dailyLosingTrades >= Number(strategy.riskLimits.maxDailyLosingTrades)
  ) {
    reasons.push("daily_losing_trade_limit_breached");
  }

  if (
    strategy.riskLimits.maxDrawdownFraction != null &&
    equity > 0 &&
    Number(accountSummary.startingCash || 0) > 0
  ) {
    const drawdownFraction = (Number(accountSummary.startingCash) - equity) / Number(accountSummary.startingCash);
    if (drawdownFraction > Number(strategy.riskLimits.maxDrawdownFraction)) {
      reasons.push("strategy_drawdown_limit_breached");
    }
  }

  if (
    strategy.riskLimits.maxCostToTargetFraction != null &&
    strategy.simulation?.takeProfitFraction != null &&
    Number(strategy.simulation.takeProfitFraction) > 0
  ) {
    const spreadFraction = (
      Number.isFinite(market.bestBid) &&
      Number.isFinite(market.bestAsk) &&
      Number(market.bestAsk) > 0
    ) ? ((Number(market.bestAsk) - Number(market.bestBid)) / Number(market.bestAsk)) : 0;
    const assumedRoundTripFeeFraction = Number(strategy.riskLimits.assumedRoundTripFeeFraction || 0);
    const assumedSlippageFraction = Number(strategy.riskLimits.assumedSlippageFraction || 0);
    const totalEstimatedCostFraction = assumedRoundTripFeeFraction + spreadFraction + assumedSlippageFraction;
    const maxAllowedCostFraction = Number(strategy.simulation.takeProfitFraction) * Number(strategy.riskLimits.maxCostToTargetFraction);
    if (totalEstimatedCostFraction > maxAllowedCostFraction) {
      reasons.push("estimated_round_trip_cost_too_high");
    }
  }

  return {
    allowed: reasons.length === 0,
    reasons,
    context: {
      realizedPnlToday,
      dailyLossFraction,
      realizedPnlWeek,
      weeklyLossFraction,
      dailyLosingTrades,
      positionFraction,
      openPositions: currentPositions.length,
    },
  };
}

function median(numbers) {
  const values = (Array.isArray(numbers) ? numbers : [])
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (values.length === 0) return null;
  const mid = Math.floor(values.length / 2);
  if (values.length % 2 === 1) return values[mid];
  return (values[mid - 1] + values[mid]) / 2;
}

function normalizeBars(priceSeries) {
  if (!Array.isArray(priceSeries)) {
    throw new Error("priceSeries must be an array of bars");
  }

  return priceSeries.map((bar, index) => {
    if (!bar || typeof bar !== "object") {
      throw new Error(`priceSeries[${index}] must be an object`);
    }

    const normalized = {
      timestamp: String(bar.timestamp || ""),
      symbol: String(bar.symbol || "").trim(),
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
      volume: bar.volume == null ? null : Number(bar.volume),
      signals: bar.signals && typeof bar.signals === "object" ? bar.signals : {},
      indicators: bar.indicators && typeof bar.indicators === "object" ? bar.indicators : null,
      sessionKey: bar.sessionKey == null ? null : String(bar.sessionKey),
      window: bar.window && typeof bar.window === "object" ? bar.window : null,
    };

    if (!normalized.timestamp) throw new Error(`priceSeries[${index}].timestamp is required`);
    if (!normalized.symbol) throw new Error(`priceSeries[${index}].symbol is required`);

    for (const field of ["open", "high", "low", "close"]) {
      if (!Number.isFinite(normalized[field]) || normalized[field] <= 0) {
        throw new Error(`priceSeries[${index}].${field} must be a positive number`);
      }
    }

    if (!(normalized.high >= normalized.low)) {
      throw new Error(`priceSeries[${index}] high must be >= low`);
    }

    return normalized;
  });
}

function getSignalValue(bar, signalName) {
  const raw = bar.signals ? bar.signals[signalName] : undefined;
  if (typeof raw === "number") return raw;
  if (raw === true) return 1;
  if (raw === false || raw == null) return 0;
  if (typeof raw === "object" && Number.isFinite(raw.value)) return raw.value;
  return 0;
}

function pickEntryPrice(currentBar, nextBar, entryExecution) {
  if (entryExecution === "next_open") {
    return nextBar ? nextBar.open : null;
  }
  return currentBar.close;
}

function resolveDynamicTakeProfitPrice(position, bar) {
  const mode = String(position?.exitTargetMode || "").toLowerCase();
  if (!mode || !bar?.indicators || typeof bar.indicators !== "object") {
    return null;
  }

  const candidates = [];
  if (mode === "session_vwap_or_range_midpoint") {
    for (const value of [bar.indicators.sessionVwap, bar.indicators.sessionRangeMidpoint]) {
      const numeric = Number(value);
      if (Number.isFinite(numeric) && numeric > Number(position.entryPrice || 0)) {
        candidates.push(numeric);
      }
    }
  }

  const fallbackPrice = Number(position.entryPrice) * (1 + Number(position.takeProfitFraction || 0));
  if (Number.isFinite(fallbackPrice) && fallbackPrice > Number(position.entryPrice || 0)) {
    candidates.push(fallbackPrice);
  }

  if (candidates.length === 0) return null;
  return Math.min(...candidates);
}

function calculateTradeOutcome(position, bars, feesFraction) {
  let exitBar = bars[bars.length - 1];
  let exitReason = "end_of_series";
  let exitPrice = exitBar.close;
  let holdBars = 0;

  for (let i = 0; i < bars.length; i += 1) {
    const bar = bars[i];
    holdBars = i + 1;

    const stopPrice = position.entryPrice * (1 - position.stopLossFraction);
    const takePrice = resolveDynamicTakeProfitPrice(position, bar)
      || (position.entryPrice * (1 + position.takeProfitFraction));
    if (bar.low <= stopPrice) {
      exitBar = bar;
      exitReason = "stop_loss";
      exitPrice = stopPrice;
      break;
    }
    if (bar.high >= takePrice) {
      exitBar = bar;
      exitReason = position.exitTargetMode ? "dynamic_take_profit" : "take_profit";
      exitPrice = takePrice;
      break;
    }

    if (holdBars >= position.maxHoldBars) {
      exitBar = bar;
      exitReason = "time_exit";
      exitPrice = bar.close;
      break;
    }
  }

  const exitExecution = simulateExecution({
    side: "sell",
    quantity: 1,
    referencePrice: exitPrice,
    snapshot: {
      volume: exitBar.volume,
      volumeUsd: Number.isFinite(exitBar.volume) ? exitBar.volume * exitPrice : undefined,
    },
    executionConfig: { feeFraction: feesFraction },
  });

  const realizedExitPrice = exitExecution.fillPrice;
  const grossReturnFraction = (realizedExitPrice - position.entryPrice) / position.entryPrice;
  const netReturnFraction = grossReturnFraction - exitExecution.feeFraction;

  return {
    exitBar,
    exitPrice: realizedExitPrice,
    exitReason,
    holdBars,
    grossReturnFraction,
    netReturnFraction,
    exitFeesFraction: exitExecution.feeFraction,
    exitSlippageFraction: exitExecution.slippageFraction,
  };
}

function buildSummary(result, minimumTrades) {
  const wins = result.trades.filter((trade) => trade.netReturnFraction > 0);
  const losses = result.trades.filter((trade) => trade.netReturnFraction < 0);
  const grossProfit = wins.reduce((sum, trade) => sum + trade.netReturnFraction, 0);
  const grossLoss = Math.abs(losses.reduce((sum, trade) => sum + trade.netReturnFraction, 0));
  const profitFactor = grossLoss === 0 ? (grossProfit > 0 ? null : 0) : grossProfit / grossLoss;
  const totalNetReturnFraction = result.equityCurve.length > 0
    ? (result.equityCurve[result.equityCurve.length - 1].equity - 1)
    : 0;
  const winRate = result.trades.length > 0 ? (wins.length / result.trades.length) : 0;
  const vetoReasons = [];

  if (result.trades.length < minimumTrades) {
    vetoReasons.push(`insufficient_trades:${result.trades.length}<${minimumTrades}`);
  }
  if (totalNetReturnFraction <= 0) {
    vetoReasons.push(`non_positive_return:${round(totalNetReturnFraction)}`);
  }
  if (profitFactor != null && profitFactor < 1) {
    vetoReasons.push(`profit_factor_below_one:${round(profitFactor)}`);
  }
  if (result.trades.length > 0 && winRate < 0.5) {
    vetoReasons.push(`win_rate_below_floor:${round(winRate)}`);
  }

  return {
    tradeCount: result.trades.length,
    eligibleForPromotion: vetoReasons.length === 0,
    totalNetReturnFraction: round(totalNetReturnFraction),
    maxDrawdownFraction: round(result.maxDrawdownFraction),
    winRate: round(winRate),
    profitFactor: profitFactor == null ? null : round(profitFactor),
    averageHoldBars: result.trades.length > 0
      ? round(result.trades.reduce((sum, trade) => sum + trade.holdBars, 0) / result.trades.length)
      : null,
    medianHoldBars: median(result.trades.map((trade) => trade.holdBars)),
    slippageAdjustedReturnFraction: round(totalNetReturnFraction),
    vetoReasons,
  };
}

function runBacktest(options = {}) {
  const strategy = assertValidStrategySpec(options.strategySpec);
  const bars = normalizeBars(options.priceSeries || []);
  const feesFraction = Number.isFinite(options.feesFraction) ? Math.max(0, options.feesFraction) : DEFAULT_DAY_TRADING_CONFIG.feesFraction;
  const initialEquity = Number.isFinite(options.initialEquity) && options.initialEquity > 0 ? options.initialEquity : 1;

  if (bars.length === 0) {
    throw new Error("priceSeries must contain at least one bar");
  }

  const trades = [];
  const equityCurve = [];
  let equity = initialEquity;
  let peakEquity = equity;
  let maxDrawdownFraction = 0;
  let lastExitIndex = -Infinity;

  for (let i = strategy.evaluationWindow.warmupBars; i < bars.length - 1; i += 1) {
    const bar = bars[i];
    const signalValue = getSignalValue(bar, strategy.simulation.entrySignal);
    if (signalValue <= 0) continue;
    if (
      strategy.simulation.useSignalStrengthThreshold != null &&
      signalValue < strategy.simulation.useSignalStrengthThreshold
    ) {
      continue;
    }
    if ((i - lastExitIndex) <= strategy.simulation.cooldownBars) continue;

    const rawEntryPrice = pickEntryPrice(bar, bars[i + 1], strategy.simulation.entryExecution);
    if (!Number.isFinite(rawEntryPrice) || rawEntryPrice <= 0) continue;

    const entryExecution = simulateExecution({
      side: "buy",
      quantity: 1,
      referencePrice: rawEntryPrice,
      snapshot: {
        volume: bars[i + 1]?.volume,
        volumeUsd: Number.isFinite(bars[i + 1]?.volume) ? bars[i + 1].volume * rawEntryPrice : undefined,
      },
      executionConfig: { feeFraction: feesFraction },
    });
    if (entryExecution.status === "rejected") continue;

    const outcome = calculateTradeOutcome({
      entryPrice: entryExecution.fillPrice,
      takeProfitFraction: strategy.simulation.takeProfitFraction,
      stopLossFraction: strategy.simulation.stopLossFraction,
      maxHoldBars: strategy.simulation.maxHoldBars,
      exitTargetMode: strategy.simulation.exitTargetMode,
    }, bars.slice(i + 1), feesFraction);
    outcome.netReturnFraction -= entryExecution.feeFraction;

    const priorDrawdownFraction = peakEquity > 0 ? (peakEquity - equity) / peakEquity : 0;
    const positionFraction = resolvePositionFraction(strategy, priorDrawdownFraction);
    const pnlFractionOfEquity = outcome.netReturnFraction * positionFraction;
    equity *= (1 + pnlFractionOfEquity);
    peakEquity = Math.max(peakEquity, equity);
    const drawdownFraction = peakEquity > 0 ? (peakEquity - equity) / peakEquity : 0;
    maxDrawdownFraction = Math.max(maxDrawdownFraction, drawdownFraction);

    const exitIndex = bars.findIndex((candidate) => (
      candidate.timestamp === outcome.exitBar.timestamp &&
      candidate.symbol === outcome.exitBar.symbol
    ));
    lastExitIndex = exitIndex >= 0 ? exitIndex : i + outcome.holdBars;

    trades.push({
      strategyId: strategy.strategyId,
      symbol: bar.symbol,
      entryTimestamp: bars[i + 1] ? bars[i + 1].timestamp : bar.timestamp,
      exitTimestamp: outcome.exitBar.timestamp,
      direction: strategy.simulation.direction,
      entryPrice: round(entryExecution.fillPrice),
      exitPrice: round(outcome.exitPrice),
      holdBars: outcome.holdBars,
      exitReason: outcome.exitReason,
      signalValue: round(signalValue),
      grossReturnFraction: round(outcome.grossReturnFraction),
      netReturnFraction: round(outcome.netReturnFraction),
      entryFeesFraction: round(entryExecution.feeFraction),
      exitFeesFraction: round(outcome.exitFeesFraction),
      entrySlippageFraction: round(entryExecution.slippageFraction),
      exitSlippageFraction: round(outcome.exitSlippageFraction),
      positionFraction: round(positionFraction),
      pnlFractionOfEquity: round(pnlFractionOfEquity),
    });

    equityCurve.push({
      timestamp: outcome.exitBar.timestamp,
      equity: round(equity),
      drawdownFraction: round(drawdownFraction),
    });

    if (drawdownFraction >= strategy.riskLimits.maxDrawdownFraction) {
      break;
    }

    i = Math.max(i + outcome.holdBars - 1, i);
  }

  const result = {
    strategyId: strategy.strategyId,
    generatedAt: nowIso(),
    assumptions: {
      initialEquity,
      feesFraction,
      warmupBars: strategy.evaluationWindow.warmupBars,
      entrySignal: strategy.simulation.entrySignal,
      entryExecution: strategy.simulation.entryExecution,
    },
    trades,
    equityCurve,
    maxDrawdownFraction: round(maxDrawdownFraction),
  };
  result.summary = buildSummary(result, strategy.evaluationWindow.minimumTrades);
  return result;
}

function saveBacktestResult(result) {
  if (!result || !result.strategyId) {
    throw new Error("saveBacktestResult requires result.strategyId");
  }

  ensureDir(BACKTEST_DIR);
  const filePath = path.join(BACKTEST_DIR, `${result.strategyId}.json`);
  const payload = {
    ...result,
    savedAt: nowIso(),
  };
  atomicWriteJsonSync(filePath, payload);
  return { filePath, result: payload };
}

function getBacktestResult(strategyId) {
  if (!strategyId) return null;
  const filePath = path.join(BACKTEST_DIR, `${strategyId}.json`);
  return readJson(filePath, null);
}

function loadBacktestSummaries() {
  if (!fs.existsSync(BACKTEST_DIR)) return [];

  return fs.readdirSync(BACKTEST_DIR)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => {
      const filePath = path.join(BACKTEST_DIR, name);
      const raw = readJson(filePath, null);
      return raw?.summary ? raw : { strategyId: raw?.strategyId, summary: raw };
    })
    .filter((result) => result?.strategyId && result?.summary);
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
  const bars = Number(options.bars) || DEFAULT_DAY_TRADING_CONFIG.bars;
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  return [
    "legacy",
    bars,
    accountId,
    _mtimeMs(STRATEGIES_PATH),
    _mtimeMs(LEDGER_PATH),
    _mtimeMs(REPORT_PATH),
    _mtimeMs(EXPERIMENT_REPORT_PATH),
    _directorySignature(BACKTEST_DIR),
    _directorySignature(EXPERIMENTS_DIR),
  ].join("::");
}

function _readOnlyDayTradingBundle(options = {}) {
  const cacheKey = _readOnlyBundleKey(options);
  const cached = READ_ONLY_BUNDLE_CACHE.get(cacheKey);
  if (cached) {
    return cached;
  }
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const broker = new PaperBroker({ ledgerPath: LEDGER_PATH, readOnly: true });
  const bundle = {
    accountId,
    strategies: loadStrategies({ readOnly: true }),
    backtests: loadBacktestSummaries(),
    broker,
    paperSummaries: broker.getStrategySummaries({ accountId }),
    paperAccount: broker.getAccountSummary({ accountId }),
    lastReport: readJson(REPORT_PATH, null),
    lastWatchlist: readJson(path.join(DATA_ROOT, "watchlist_latest.json"), null),
    experimentReport: readJson(EXPERIMENT_REPORT_PATH, null),
  };
  READ_ONLY_BUNDLE_CACHE.set(cacheKey, bundle);
  return bundle;
}

function httpsJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "Mozilla/5.0" } }, (res) => {
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

function sma(values, period, index) {
  if (index + 1 < period) return null;
  let sum = 0;
  for (let i = index - period + 1; i <= index; i += 1) {
    sum += values[i];
  }
  return sum / period;
}

function stddev(values, period, index) {
  const mean = sma(values, period, index);
  if (mean == null) return null;
  let variance = 0;
  for (let i = index - period + 1; i <= index; i += 1) {
    variance += (values[i] - mean) ** 2;
  }
  return Math.sqrt(variance / period);
}

function highest(values, period, index) {
  if (index + 1 < period) return null;
  let max = -Infinity;
  for (let i = index - period + 1; i <= index; i += 1) {
    if (values[i] > max) max = values[i];
  }
  return max;
}

function computeEmaSeries(values, period) {
  const multiplier = 2 / (period + 1);
  const result = new Array(values.length).fill(null);
  let ema = null;
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (!Number.isFinite(value)) continue;
    if (ema == null) {
      ema = value;
    } else {
      ema = ((value - ema) * multiplier) + ema;
    }
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

function computeVwapSeries(bars) {
  let currentSession = null;
  let cumulativeVolume = 0;
  let cumulativePriceVolume = 0;

  return bars.map((bar) => {
    const session = String(bar.timestamp || "").slice(0, 10);
    if (session !== currentSession) {
      currentSession = session;
      cumulativeVolume = 0;
      cumulativePriceVolume = 0;
    }

    const high = Number(bar.high);
    const low = Number(bar.low);
    const close = Number(bar.close);
    const volume = Number(bar.volume || 0);
    const typicalPrice = (high + low + close) / 3;

    if (Number.isFinite(volume) && volume > 0 && Number.isFinite(typicalPrice)) {
      cumulativeVolume += volume;
      cumulativePriceVolume += typicalPrice * volume;
    }

    if (cumulativeVolume <= 0) return null;
    return cumulativePriceVolume / cumulativeVolume;
  });
}

function computeSessionOpeningRangeHighs(bars, openingRangeBars) {
  let currentSession = null;
  let sessionStartIndex = -1;
  let openingRangeHigh = null;

  return bars.map((bar, index) => {
    const session = String(bar.timestamp || "").slice(0, 10);
    if (session !== currentSession) {
      currentSession = session;
      sessionStartIndex = index;
      openingRangeHigh = Number(bar.high);
    } else if ((index - sessionStartIndex) < openingRangeBars) {
      openingRangeHigh = Math.max(Number(openingRangeHigh || Number.NEGATIVE_INFINITY), Number(bar.high));
    }

    return {
      openingRangeHigh: (index - sessionStartIndex) >= (openingRangeBars - 1) ? openingRangeHigh : null,
      barsSinceSessionStart: index - sessionStartIndex,
    };
  });
}

function enrichBarsWithSignals(bars, strategy) {
  const closes = bars.map((bar) => Number(bar.close));
  const highs = bars.map((bar) => Number(bar.high));
  const volumes = bars.map((bar) => Number(bar.volume || 0));
  const ema20 = computeEmaSeries(closes, 20);
  const ema50 = computeEmaSeries(closes, 50);
  const rsi14 = computeRsiSeries(closes, 14);
  const vwap = computeVwapSeries(bars);
  const signalName = strategy.simulation?.entrySignal || "entry_signal";
  const timeframe = String(strategy.evaluationWindow?.timeframe || "").toLowerCase();
  const openingRangeBars = timeframe === "5m" ? 6 : 2;
  const sessionOpeningRanges = computeSessionOpeningRangeHighs(bars, openingRangeBars);

  return bars.map((bar, index) => {
    const close = closes[index];
    const low = Number(bar.low);
    const prevClose = index > 0 ? closes[index - 1] : close;
    const volume20 = sma(volumes, 20, index);
    const volumeRatio = volume20 ? volumes[index] / volume20 : null;
    const pctChange = prevClose ? (close - prevClose) / prevClose : 0;
    const priorVwap = index > 0 ? vwap[index - 1] : null;
    const openingRangeHigh = sessionOpeningRanges[index].openingRangeHigh;
    const barsSinceSessionStart = sessionOpeningRanges[index].barsSinceSessionStart;
    const sameSessionAsPrevious = index > 0
      ? String(bar.timestamp || "").slice(0, 10) === String(bars[index - 1]?.timestamp || "").slice(0, 10)
      : false;

    let signalValue = 0;

    if (signalName === "opening_range_breakout") {
      const trendOkay = ema20[index] != null && ema50[index] != null && ema20[index] > ema50[index];
      const brokeOpeningRange = barsSinceSessionStart >= openingRangeBars &&
        openingRangeHigh != null &&
        close > openingRangeHigh &&
        prevClose <= openingRangeHigh;
      const volumeBoost = volumeRatio != null ? Math.min(volumeRatio / 1.8, 1) : 0;
      signalValue = (trendOkay && brokeOpeningRange)
        ? Math.min(1, 0.6 + (volumeBoost * 0.25) + Math.max(0, pctChange * 80))
        : 0;
    } else if (signalName === "vwap_trend_reclaim") {
      const trendOkay = ema20[index] != null && ema50[index] != null && ema20[index] > ema50[index];
      const reclaim = vwap[index] != null &&
        close > vwap[index] &&
        low <= vwap[index] &&
        (!sameSessionAsPrevious || priorVwap == null || prevClose <= (priorVwap * 1.0015));
      const rsiOkay = rsi14[index] != null && rsi14[index] >= 48 && rsi14[index] <= 68;
      const volumeSupport = volumeRatio != null && volumeRatio >= 0.9;
      signalValue = (trendOkay && reclaim && rsiOkay && volumeSupport)
        ? Math.min(1, 0.58 + Math.min(Math.abs(close - vwap[index]) / Math.max(close, 1) * 100, 0.18) + 0.12)
        : 0;
    }

    return {
      ...bar,
      indicators: {
        ema20: round(ema20[index]),
        ema50: round(ema50[index]),
        vwapSession: round(vwap[index]),
        rsi14: round(rsi14[index]),
        volumeRatio20: round(volumeRatio),
        openingRangeHigh: round(openingRangeHigh),
      },
      signals: {
        ...(bar.signals || {}),
        [signalName]: round(signalValue) || 0,
      },
    };
  });
}

function buildSampleSeries(options = {}) {
  const strategy = assertValidStrategySpec(options.strategySpec);
  const symbol = options.symbol || strategy.marketUniverse?.symbols?.[0] || "SPY";
  const bars = Math.max(12, Number(options.bars) || 64);
  const intervalMinutes = String(strategy.evaluationWindow?.timeframe || "").toLowerCase().includes("5m") ? 5 : 15;
  const startPrice = String(symbol).toUpperCase() === "QQQ" ? 520 : 575;
  const trendBias = strategy.simulation.entrySignal === "opening_range_breakout" ? 0.24 : 0.16;
  const threshold = Number(strategy.simulation?.useSignalStrengthThreshold || 0.7);

  const series = [];
  let price = startPrice;
  const baseTime = new Date("2026-03-01T14:30:00.000Z").getTime();

  for (let i = 0; i < bars; i += 1) {
    const drift = Math.sin(i / 4) * 0.9;
    const directional = (i % 11 === 0 ? trendBias * -1 : trendBias) + 0.85;
    const open = price;
    const close = Math.max(1, open + drift + directional);
    const high = Math.max(open, close) + 0.8;
    const low = Math.max(0.5, Math.min(open, close) - 0.8);

    series.push({
      timestamp: new Date(baseTime + (i * intervalMinutes * 60 * 1000)).toISOString(),
      symbol,
      open: round(open),
      high: round(high),
      low: round(low),
      close: round(close),
      volume: round(1000000 + (i * 10000)),
      signals: {
        [strategy.simulation.entrySignal]: i % (intervalMinutes === 5 ? 18 : 14) === 0 ? round(threshold + 0.15) : 0,
      },
    });

    price = close;
  }

  return series;
}

function mapTimeframeToYahooInterval(timeframe, limit = 200) {
  const normalized = String(timeframe || "").toLowerCase();
  if (normalized === "5m") {
    return {
      interval: "5m",
      ranges: Number(limit) > 780 ? ["60d", "1mo"] : ["1mo", "60d"],
    };
  }
  if (normalized === "15m") {
    return {
      interval: "15m",
      ranges: Number(limit) > 520 ? ["60d", "1mo"] : ["1mo", "60d"],
    };
  }
  return { interval: "15m", ranges: ["1mo"] };
}

async function fetchYahooBars({ symbol, timeframe, limit = 200, signalName, strategy }) {
  const { interval, ranges } = mapTimeframeToYahooInterval(timeframe, limit);
  let lastError = new Error("No equity chart data returned");

  for (const range of ranges) {
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}&includePrePost=false&events=div%2Csplits`;
      const payload = await httpsJson(url);
      const result = payload?.chart?.result?.[0];
      const quote = result?.indicators?.quote?.[0];
      const timestamps = Array.isArray(result?.timestamp) ? result.timestamp : [];

      if (!result || !quote || timestamps.length === 0) {
        throw new Error(`No equity chart data returned for range ${range}`);
      }

      const rows = timestamps.map((timestamp, index) => ({
        timestamp: new Date(Number(timestamp) * 1000).toISOString(),
        symbol,
        open: Number(quote.open?.[index]),
        high: Number(quote.high?.[index]),
        low: Number(quote.low?.[index]),
        close: Number(quote.close?.[index]),
        volume: Number(quote.volume?.[index] || 0),
        signals: {},
      })).filter((bar) => (
        Number.isFinite(bar.open) &&
        Number.isFinite(bar.high) &&
        Number.isFinite(bar.low) &&
        Number.isFinite(bar.close) &&
        bar.open > 0 &&
        bar.high > 0 &&
        bar.low > 0 &&
        bar.close > 0
      ));

      if (rows.length === 0) {
        throw new Error(`Equity chart data had no valid bars for range ${range}`);
      }

      const enriched = enrichBarsWithSignals(rows, {
        ...strategy,
        simulation: { ...strategy.simulation, entrySignal: signalName },
      });
      return enriched.slice(-limit);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }

  throw lastError;
}

async function fetchMarketDataForStrategy(strategy, options = {}) {
  const symbol = options.symbol || strategy.marketUniverse?.symbols?.[0] || "SPY";
  const bars = Number(options.bars) || DEFAULT_DAY_TRADING_CONFIG.bars;

  try {
    const priceSeries = await fetchYahooBars({
      symbol,
      timeframe: strategy.evaluationWindow?.timeframe,
      limit: bars,
      signalName: strategy.simulation?.entrySignal || "entry_signal",
      strategy,
    });
    const lastBar = priceSeries[priceSeries.length - 1];
    return {
      source: "yahoo_chart",
      symbol,
      marketSnapshot: {
        bestBid: lastBar.close * 0.99985,
        bestAsk: lastBar.close * 1.00015,
        volume: lastBar.volume,
        volumeUsd: Number.isFinite(lastBar.volume) ? lastBar.volume * lastBar.close : undefined,
        availableLiquidityUsd: Number.isFinite(lastBar.volume) ? lastBar.volume * lastBar.close * 0.08 : undefined,
      },
      priceSeries,
    };
  } catch (error) {
    const priceSeries = buildSampleSeries({
      strategySpec: strategy,
      symbol,
      bars,
    });
    const lastBar = priceSeries[priceSeries.length - 1];
    return {
      source: "sample_fallback",
      symbol,
      warning: `real_market_data_failed:${error.message}`,
      marketSnapshot: {
        bestBid: lastBar.close * 0.9998,
        bestAsk: lastBar.close * 1.0002,
        volume: lastBar.volume,
        volumeUsd: Number.isFinite(lastBar.volume) ? lastBar.volume * lastBar.close : undefined,
        availableLiquidityUsd: Number.isFinite(lastBar.volume) ? lastBar.volume * lastBar.close * 0.08 : undefined,
      },
      priceSeries,
    };
  }
}

function rankStrategy(strategy, backtestSummary, paperSummary) {
  const reasons = [];
  const vetoReasons = [];
  let score = 0;

  if (backtestSummary) {
    const returnFraction = Number(backtestSummary.totalNetReturnFraction || 0);
    const drawdownFraction = Number(backtestSummary.maxDrawdownFraction || 0);
    const tradeCount = Number(backtestSummary.tradeCount || 0);
    score += clamp(returnFraction * 300, -40, 60);
    score -= clamp(drawdownFraction * 140, 0, 45);
    score += clamp(tradeCount, 0, 25);
    reasons.push(`backtest_return:${returnFraction}`);
    reasons.push(`backtest_drawdown:${drawdownFraction}`);
    reasons.push(`backtest_trades:${tradeCount}`);
    if (Array.isArray(backtestSummary.vetoReasons) && backtestSummary.vetoReasons.length > 0) {
      vetoReasons.push(...backtestSummary.vetoReasons);
      score -= 20;
    }
  } else {
    vetoReasons.push("missing_backtest");
    score -= 15;
  }

  if (paperSummary) {
    const realizedPnl = Number(paperSummary.realizedPnl || 0);
    const unrealizedPnl = Number(paperSummary.unrealizedPnl || 0);
    const tradeCount = Number(paperSummary.tradeCount || 0);
    const winRate = paperSummary.winRate == null ? null : Number(paperSummary.winRate);
    score += clamp(realizedPnl / 25, -30, 40);
    score += clamp(unrealizedPnl / 25, -15, 20);
    score += clamp(tradeCount * 1.5, 0, 18);
    if (winRate != null) score += clamp((winRate - 0.5) * 30, -10, 10);
    reasons.push(`paper_realized:${realizedPnl}`);
    reasons.push(`paper_unrealized:${unrealizedPnl}`);
    reasons.push(`paper_trades:${tradeCount}`);
    if (tradeCount === 0) vetoReasons.push("no_paper_trades");
  } else {
    vetoReasons.push("no_paper_activity");
    score -= 10;
  }

  if (strategy.status === "candidate_live") score += 10;
  else if (strategy.status === "promotion_review") score += 6;
  else if (strategy.status === "paper_live") score += 4;
  else if (strategy.status === "disabled") score -= 100;

  return {
    strategyId: strategy.strategyId,
    strategyName: strategy.name,
    status: strategy.status,
    venueType: strategy.venueType,
    score: Number(score.toFixed(4)),
    reasons,
    vetoReasons: [...new Set(vetoReasons)],
    backtest: backtestSummary || null,
    paper: paperSummary || null,
  };
}

function parseClockToMinutes(clockValue, fallbackMinutes) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(clockValue || "").trim());
  if (!match) return fallbackMinutes;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return fallbackMinutes;
  return (hours * 60) + minutes;
}

function getEtParts(dateInput) {
  const value = dateInput ? new Date(dateInput) : new Date();
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null;
  const parts = ET_FORMATTER.formatToParts(value);
  const map = {};
  for (const part of parts) {
    if (part.type !== "literal") map[part.type] = part.value;
  }
  const hour = Number(map.hour);
  const minute = Number(map.minute);
  return {
    date: `${map.year}-${map.month}-${map.day}`,
    weekday: map.weekday,
    hour,
    minute,
    minutesSinceMidnight: (hour * 60) + minute,
  };
}

function classifyMorningWindow(timestamp, config = DEFAULT_DAY_TRADING_CONFIG) {
  const parts = getEtParts(timestamp);
  if (!parts) {
    return {
      active: false,
      label: "invalid_time",
      minutesSinceMidnight: null,
    };
  }

  const openMinutes = parseClockToMinutes(config.morningStartEt, 9 * 60 + 30);
  const cutoffMinutes = parseClockToMinutes(config.morningCutoffEt, 11 * 60 + 30);
  const isWeekday = !["Sat", "Sun"].includes(String(parts.weekday || ""));
  const active = isWeekday &&
    parts.minutesSinceMidnight >= openMinutes &&
    parts.minutesSinceMidnight <= cutoffMinutes;

  return {
    active,
    label: active ? "morning_window" : "outside_morning_window",
    minutesSinceMidnight: parts.minutesSinceMidnight,
    date: parts.date,
    weekday: parts.weekday,
  };
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

function buildDayTradingExperimentVariants(strategy, options = {}) {
  const family = String(strategy?.simulation?.entrySignal || "");
  const baseGrid = DEFAULT_EXPERIMENT_LIBRARY[family];
  if (!baseGrid) {
    return [{
      variantId: `${strategy.strategyId}__baseline`,
      variantLabel: "baseline",
      parameters: {
        signalThreshold: Number(strategy?.simulation?.useSignalStrengthThreshold || 0),
        takeProfitFraction: Number(strategy?.simulation?.takeProfitFraction || 0),
        stopLossFraction: Number(strategy?.simulation?.stopLossFraction || 0),
        maxHoldBars: Number(strategy?.simulation?.maxHoldBars || 0),
      },
      strategySpec: clone(strategy),
    }];
  }

  const customGrid = options.grid?.[family] || {};
  if (Array.isArray(customGrid.variants) && customGrid.variants.length > 0) {
    return customGrid.variants.map((variant) => {
      const signalThreshold = Number(variant.signalThreshold);
      const takeProfitFraction = Number(variant.takeProfitFraction);
      const stopLossFraction = Number(variant.stopLossFraction);
      const holdBars = Math.round(Number(variant.maxHoldBars));
      const variantId = `${strategy.strategyId}__thr${percentToken(signalThreshold)}_tp${percentToken(takeProfitFraction)}_sl${percentToken(stopLossFraction)}_hold${holdBars}`;
      const variantLabel = `thr ${round(signalThreshold, 2)} / tp ${round(takeProfitFraction * 100, 2)}% / sl ${round(stopLossFraction * 100, 2)}% / hold ${holdBars}`;
      return {
        variantId,
        variantLabel,
        parameters: {
          signalThreshold: round(signalThreshold),
          takeProfitFraction: round(takeProfitFraction),
          stopLossFraction: round(stopLossFraction),
          maxHoldBars: holdBars,
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
            maxHoldBars: holdBars,
          },
          metadata: {
            ...(strategy.metadata || {}),
            experimentBaseStrategyId: strategy.strategyId,
            experimentVariantLabel: variantLabel,
            experimentKind: "parameter_sweep",
          },
        },
      };
    });
  }

  const signalThresholds = uniqueNumbers(customGrid.signalThresholds || [
    strategy.simulation.useSignalStrengthThreshold,
    ...baseGrid.signalThresholds,
  ]);
  const takeProfitFractions = uniqueNumbers(customGrid.takeProfitFractions || [
    strategy.simulation.takeProfitFraction,
    ...baseGrid.takeProfitFractions,
  ]);
  const stopLossFractions = uniqueNumbers(customGrid.stopLossFractions || [
    strategy.simulation.stopLossFraction,
    ...baseGrid.stopLossFractions,
  ]);
  const maxHoldBars = uniqueNumbers(customGrid.maxHoldBars || [
    strategy.simulation.maxHoldBars,
    ...baseGrid.maxHoldBars,
  ]).map((value) => Math.round(value));

  const variants = [];
  for (const signalThreshold of signalThresholds) {
    for (const takeProfitFraction of takeProfitFractions) {
      for (const stopLossFraction of stopLossFractions) {
        for (const holdBars of maxHoldBars) {
          const variantId = `${strategy.strategyId}__thr${percentToken(signalThreshold)}_tp${percentToken(takeProfitFraction)}_sl${percentToken(stopLossFraction)}_hold${holdBars}`;
          const variantLabel = `thr ${round(signalThreshold, 2)} / tp ${round(takeProfitFraction * 100, 2)}% / sl ${round(stopLossFraction * 100, 2)}% / hold ${holdBars}`;
          variants.push({
            variantId,
            variantLabel,
            parameters: {
              signalThreshold: round(signalThreshold),
              takeProfitFraction: round(takeProfitFraction),
              stopLossFraction: round(stopLossFraction),
              maxHoldBars: holdBars,
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
                maxHoldBars: holdBars,
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

async function runDayTradingExperiments(options = {}) {
  const strategies = (options.strategies || loadStrategies()).filter((strategy) => String(strategy.status || "") !== "disabled");
  const bars = Number(options.bars) || DEFAULT_DAY_TRADING_CONFIG.bars;
  const feesFraction = Number.isFinite(options.feesFraction) ? Number(options.feesFraction) : DEFAULT_DAY_TRADING_CONFIG.feesFraction;
  const persistArtifacts = options.persistArtifacts !== false;
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : fetchMarketDataForStrategy;
  const strictMarketData = options.strictMarketData !== false;
  const top = Math.max(1, Number(options.top) || 10);
  const presetName = options.preset ? String(options.preset) : null;
  const presetGrid = presetName ? DAY_TRADING_EXPERIMENT_PRESETS[presetName] || null : null;
  const experimentOptions = presetGrid
    ? { ...options, grid: presetGrid }
    : options;

  ensureDir(EXPERIMENTS_DIR);

  const marketDataByBase = new Map();
  const results = [];

  for (const strategy of strategies) {
    const marketData = await marketDataLoader(strategy, { bars, persistArtifacts });
    marketDataByBase.set(strategy.strategyId, marketData);
    const trustedMarketData = marketData?.source !== "sample_fallback";
    const variants = buildDayTradingExperimentVariants(strategy, experimentOptions);

    for (const variant of variants) {
      const backtest = runBacktest({
        strategySpec: variant.strategySpec,
        priceSeries: marketData.priceSeries,
        feesFraction,
      });
      const trusted = trustedMarketData || !strictMarketData;
      const summary = trusted
        ? backtest.summary
        : {
          ...backtest.summary,
          eligibleForPromotion: false,
          vetoReasons: [...(backtest.summary.vetoReasons || []), "synthetic_market_data"],
        };
      const result = {
        variantId: variant.variantId,
        strategyName: strategy.name,
        baseStrategyId: strategy.strategyId,
        strategyFamily: String(strategy.simulation?.entrySignal || ""),
        symbol: strategy.marketUniverse?.symbols?.[0] || null,
        timeframe: strategy.evaluationWindow?.timeframe || null,
        parameters: variant.parameters,
        variantLabel: variant.variantLabel,
        trustedMarketData: trusted,
        marketDataSource: marketData?.source || null,
        marketDataWarning: marketData?.warning || null,
        dataBarCount: Array.isArray(marketData?.priceSeries) ? marketData.priceSeries.length : 0,
        latestBarTimestamp: marketData?.priceSeries?.[marketData.priceSeries.length - 1]?.timestamp || null,
        summary,
      };
      result.experimentScore = scoreExperimentResult(result);
      results.push(result);
    }
  }

  const sortedResults = results.slice().sort(compareExperimentResults);
  const trustedCount = sortedResults.filter((result) => result.trustedMarketData).length;
  const eligibleCount = sortedResults.filter((result) => result.summary?.eligibleForPromotion === true).length;
  const report = {
    generatedAt: nowIso(),
    bars,
    feesFraction,
    strictMarketData,
    preset: presetName,
    strategiesTested: strategies.length,
    variantsTested: results.length,
    trustedVariantCount: trustedCount,
    untrustedVariantCount: results.length - trustedCount,
    eligibleVariantCount: eligibleCount,
    baseStrategies: strategies.map((strategy) => {
      const marketData = marketDataByBase.get(strategy.strategyId) || {};
      return {
        strategyId: strategy.strategyId,
        strategyName: strategy.name,
        symbol: strategy.marketUniverse?.symbols?.[0] || null,
        strategyFamily: String(strategy.simulation?.entrySignal || ""),
        timeframe: strategy.evaluationWindow?.timeframe || null,
        marketDataSource: marketData.source || null,
        marketDataWarning: marketData.warning || null,
        dataBarCount: Array.isArray(marketData.priceSeries) ? marketData.priceSeries.length : 0,
        latestBarTimestamp: marketData.priceSeries?.[marketData.priceSeries.length - 1]?.timestamp || null,
      };
    }),
    leaders: sortedResults.slice(0, top),
    leadersByBase: summarizeExperimentLeaders(sortedResults, "baseStrategyId", 3),
    leadersByFamily: summarizeExperimentLeaders(sortedResults, "strategyFamily", 5),
    recommendation: eligibleCount > 0
      ? "candidate_ready_for_live_watchlist"
      : (trustedCount > 0 ? "continue_strategy_iteration" : "improve_intraday_data_source"),
    notes: [
      strictMarketData
        ? "Synthetic fallback data is marked untrusted and cannot promote a strategy."
        : "Synthetic fallback data is allowed in this experiment run; treat leaders as exploratory only.",
      "Leaders are ranked by trusted market data first, then promotion eligibility, return, profit factor, win rate, trade count, and drawdown.",
    ],
    results: sortedResults,
  };

  atomicWriteJsonSync(EXPERIMENT_REPORT_PATH, report);
  return report;
}

function calculateBarAgeMinutes(latestTimestamp, nowTimestamp) {
  const latestMs = latestTimestamp ? new Date(latestTimestamp).getTime() : NaN;
  const nowMs = nowTimestamp ? new Date(nowTimestamp).getTime() : NaN;
  if (!Number.isFinite(latestMs) || !Number.isFinite(nowMs)) return null;
  return round(Math.max(0, (nowMs - latestMs) / 60000), 3);
}

async function buildMorningWatchlist(options = {}) {
  const bars = Number(options.bars) || DEFAULT_DAY_TRADING_CONFIG.bars;
  const limit = Math.max(1, Number(options.limit) || DEFAULT_DAY_TRADING_CONFIG.watchlistLimit || 4);
  const readOnly = Boolean(options.readOnly);
  const persistArtifacts = options.persistArtifacts !== false && !readOnly;
  const bundle = options.artifactBundle || (readOnly ? _readOnlyDayTradingBundle({ ...options, bars }) : null);
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : fetchMarketDataForStrategy;
  const strategies = ((bundle?.strategies || options.strategies || loadStrategies({ readOnly })) || [])
    .filter((strategy) => String(strategy.status || "") !== "disabled");
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const now = options.now || nowIso();
  const nowWindow = classifyMorningWindow(now, DEFAULT_DAY_TRADING_CONFIG);
  const broker = bundle?.broker || new PaperBroker({ ledgerPath: LEDGER_PATH, readOnly });
  broker.ensureAccount({
    accountId,
    startingCash: DEFAULT_DAY_TRADING_CONFIG.startingCash,
    createIfMissing: readOnly,
  });
  const paperSummaries = bundle?.paperSummaries || broker.getStrategySummaries({ accountId });
  const scoreboard = buildStrategyScoreboard({
    strategies,
    backtests: bundle?.backtests || loadBacktestSummaries(),
    paperSummaries,
  });
  const strategyMap = new Map(strategies.map((strategy) => [strategy.strategyId, strategy]));
  const rankedCandidates = scoreboard.items
    .map((item) => ({
      ...item,
      evidenceScore: round(scoreWatchlistEvidence(item), 4),
    }))
    .sort(compareWatchlistCandidates)
    .slice(0, limit);

  const items = (await Promise.all(rankedCandidates.map(async (candidate) => {
    const strategy = strategyMap.get(candidate.strategyId);
    if (!strategy) return null;

    const marketData = await marketDataLoader(strategy, { bars, persistArtifacts });
    const priceSeries = Array.isArray(marketData?.priceSeries) ? marketData.priceSeries : [];
    const lastBar = priceSeries[priceSeries.length - 1] || null;
    const latestSessionDate = lastBar ? getEtParts(lastBar.timestamp)?.date : null;
    const nowSessionDate = getEtParts(now)?.date || null;
    const signalName = strategy.simulation.entrySignal;
    const threshold = Number(strategy.simulation.useSignalStrengthThreshold || 0);
    const sessionBars = latestSessionDate == null
      ? []
      : priceSeries.filter((bar) => getEtParts(bar.timestamp)?.date === latestSessionDate);
    const signalBars = sessionBars
      .map((bar, index) => ({
        bar,
        index,
        signalValue: Number(getSignalValue(bar, signalName) || 0),
        window: classifyMorningWindow(bar.timestamp, DEFAULT_DAY_TRADING_CONFIG),
      }))
      .filter((entry) => entry.signalValue >= threshold);
    const latestSignal = signalBars.length > 0 ? signalBars[signalBars.length - 1] : null;
    const barsSinceTrigger = latestSignal ? Math.max(0, sessionBars.length - latestSignal.index - 1) : null;
    const lastBarSignalValue = lastBar ? Number(getSignalValue(lastBar, signalName) || 0) : 0;
    const lastBarWindow = lastBar ? classifyMorningWindow(lastBar.timestamp, DEFAULT_DAY_TRADING_CONFIG) : { active: false };
    const barAgeMinutes = calculateBarAgeMinutes(lastBar?.timestamp, now);
    const currentDataTrusted = marketData?.source !== "sample_fallback";
    const dataFresh = latestSessionDate != null &&
      latestSessionDate === nowSessionDate &&
      barAgeMinutes != null &&
      barAgeMinutes <= DEFAULT_DAY_TRADING_CONFIG.maxBarAgeMinutes;
    const alertEligible = candidate.backtest?.eligibleForPromotion === true;

    let liveStatus = "inactive";
    let notifyNow = false;
    if (!currentDataTrusted) {
      liveStatus = "untrusted_data";
    } else if (!dataFresh) {
      liveStatus = "stale";
    } else if (latestSignal && latestSignal.window.active && nowWindow.active && barsSinceTrigger != null && barsSinceTrigger <= DEFAULT_DAY_TRADING_CONFIG.notifyLookbackBars) {
      liveStatus = barsSinceTrigger === 0 ? "triggered_now" : "triggered_recently";
      notifyNow = alertEligible;
    } else if (latestSignal && latestSignal.window.active) {
      liveStatus = "triggered_this_morning";
    } else if (nowWindow.active && lastBarWindow.active) {
      liveStatus = "tracking";
    }

    return {
      strategyId: strategy.strategyId,
      strategyName: strategy.name,
      symbol: strategy.marketUniverse?.symbols?.[0] || null,
      timeframe: strategy.evaluationWindow?.timeframe || null,
      signalName,
      liveStatus,
      notifyNow,
      alertEligible,
      evidenceScore: candidate.evidenceScore,
      score: candidate.score,
      status: candidate.status,
      replayEvidence: candidate.backtest ? {
        tradeCount: candidate.backtest.tradeCount,
        winRate: candidate.backtest.winRate,
        profitFactor: candidate.backtest.profitFactor,
        totalNetReturnFraction: candidate.backtest.totalNetReturnFraction,
        eligibleForPromotion: candidate.backtest.eligibleForPromotion,
        vetoReasons: candidate.backtest.vetoReasons || [],
      } : null,
      paperEvidence: candidate.paper || null,
      marketDataSource: marketData?.source || "unknown",
      marketDataWarning: marketData?.warning || null,
      lastBarTimestamp: lastBar?.timestamp || null,
      latestSignalTimestamp: latestSignal?.bar?.timestamp || null,
      latestSignalValue: latestSignal ? round(latestSignal.signalValue) : null,
      currentSignalValue: round(lastBarSignalValue),
      signalThreshold: round(threshold),
      barsSinceTrigger,
      barAgeMinutes,
      morningWindowActive: nowWindow.active,
      dataFresh,
      currentDataTrusted,
      currentPrice: lastBar?.close != null ? round(Number(lastBar.close), 4) : null,
      indicators: lastBar?.indicators || null,
      reasons: [
        currentDataTrusted ? "trusted_market_data" : "untrusted_market_data",
        dataFresh ? "fresh_session_data" : "stale_session_data",
        notifyNow ? "notify_candidate" : "manual_watch_only",
        latestSignal
          ? `latest_trigger:${latestSignal.bar.timestamp}`
          : `signal_below_threshold:${round(lastBarSignalValue - threshold, 4)}`,
      ],
    };
  }))).filter(Boolean);

  return {
    generatedAt: nowIso(),
    evaluatedAt: now,
    rankingBasis: "eligible -> win rate -> profit factor -> trade count -> scoreboard score",
    morningWindow: {
      startEt: DEFAULT_DAY_TRADING_CONFIG.morningStartEt,
      cutoffEt: DEFAULT_DAY_TRADING_CONFIG.morningCutoffEt,
      activeNow: nowWindow.active,
    },
    selectedStrategies: items.length,
    notifyNowCount: items.filter((item) => item.notifyNow).length,
    items,
  };
}

function buildStrategyScoreboard(options = {}) {
  const strategies = options.strategies || loadStrategies();
  const backtests = options.backtests || loadBacktestSummaries();
  const paperSummaries = options.paperSummaries || [];

  const strategyMap = new Map();
  for (const strategy of strategies) {
    strategyMap.set(strategy.strategyId, strategy);
  }
  const backtestMap = new Map(backtests.map((result) => [result.strategyId, result.summary]));
  const paperMap = new Map(paperSummaries.map((summary) => [summary.strategyId, summary]));

  const items = [...strategyMap.values()]
    .map((strategy) => rankStrategy(strategy, backtestMap.get(strategy.strategyId), paperMap.get(strategy.strategyId)))
    .sort((a, b) => b.score - a.score);

  return {
    generatedAt: nowIso(),
    totals: {
      strategies: items.length,
      withPaperActivity: items.filter((item) => item.paper && item.paper.tradeCount > 0).length,
      candidateLive: items.filter((item) => item.status === "candidate_live").length,
      blocked: items.filter((item) => item.vetoReasons.length > 0).length,
    },
    leaders: items.slice(0, 5),
    items,
  };
}

function nextPromotionDecision(strategy, context = {}) {
  const currentStatus = String(strategy.status || "draft");
  const backtest = context.backtestSummary || {};
  const paper = context.paperSummary || {};
  const hasBacktestVeto = Array.isArray(backtest.vetoReasons) && backtest.vetoReasons.length > 0;
  const tradeCount = Number(paper.tradeCount || 0);
  const realizedPnl = Number(paper.realizedPnl || 0);
  const unrealizedPnl = Number(paper.unrealizedPnl || 0);
  const winRate = paper.winRate == null ? null : Number(paper.winRate);
  const combinedPnl = realizedPnl + unrealizedPnl;

  let nextStatus = currentStatus;
  let reason = "no_change";

  if (hasBacktestVeto || backtest.eligibleForPromotion === false) {
    nextStatus = "backtest_failed";
    reason = hasBacktestVeto ? "backtest_veto" : "backtest_ineligible";
  } else if (tradeCount === 0) {
    nextStatus = "paper_candidate";
    reason = "awaiting_paper_activity";
  } else if (tradeCount >= 8 && realizedPnl > 50 && winRate != null && winRate >= 0.6) {
    nextStatus = "promotion_review";
    reason = "paper_threshold_promotion_review";
  } else if (tradeCount >= 4 && combinedPnl > 0 && winRate != null && winRate >= 0.55) {
    nextStatus = "promotion_review";
    reason = "paper_threshold_promotion_review";
  } else if (tradeCount >= 2 && combinedPnl > 0) {
    nextStatus = "paper_live";
    reason = "paper_threshold_paper_live";
  } else {
    nextStatus = "paper_candidate";
    reason = "paper_threshold_not_met";
  }

  return {
    currentStatus,
    nextStatus,
    changed: nextStatus !== currentStatus,
    reason,
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

async function maybePaperTrade({ paperBroker, strategy, marketData, accountId = DEFAULT_ACCOUNT_ID }) {
  if (!paperBroker || !marketData?.priceSeries?.length) {
    return { action: "skipped", reason: "no_broker_or_data" };
  }

  const symbol = marketData.symbol;
  const account = paperBroker.getAccount(accountId);
  const positionKey = `${strategy.strategyId}::${symbol}`;
  const position = account.positions[positionKey] || null;
  const lastBar = marketData.priceSeries[marketData.priceSeries.length - 1];
  const signalValue = Number(lastBar.signals?.[strategy.simulation.entrySignal] || 0);
  const threshold = Number(strategy.simulation.useSignalStrengthThreshold || 0);

  if (!position && signalValue >= threshold) {
    const accountSummary = paperBroker.getAccountSummary({ accountId });
    const equity = Number(accountSummary.equity || accountSummary.cash || 0);
    const stopLossFraction = Number(strategy.simulation?.stopLossFraction || 0);
    const usesStopBasedSizing = String(strategy.sizing?.riskSizing || "").toLowerCase() === "stop_based";
    const drawdownMultiplier = resolveDrawdownPositionMultiplier(strategy, accountSummary);
    const maxNotional = equity * Number(strategy.sizing?.maxPositionFraction || 0);
    const riskBudget = equity * Number(strategy.sizing?.riskPerTradeFraction || 0) * drawdownMultiplier;
    const targetNotional = usesStopBasedSizing && stopLossFraction > 0
      ? Math.min(maxNotional || Number.POSITIVE_INFINITY, riskBudget / stopLossFraction)
      : Math.min(maxNotional || Number.POSITIVE_INFINITY, riskBudget || Number.POSITIVE_INFINITY);
    const cashToDeploy = Math.min(account.cash, Number.isFinite(targetNotional) ? targetNotional : 100);
    const quantity = cashToDeploy > 0 ? cashToDeploy / lastBar.close : 0;
    if (quantity <= 0) {
      return { action: "skipped", reason: "no_cash" };
    }
    const riskDecision = evaluateTradeRisk({
      strategy,
      order: {
        accountId,
        strategyId: strategy.strategyId,
        side: "buy",
        quantity,
        price: lastBar.close,
        timestamp: lastBar.timestamp,
      },
      accountSummary,
      ledger: paperBroker.ledger,
      market: marketData.marketSnapshot || {},
    });
    if (!riskDecision.allowed) {
      return { action: "risk_blocked", reasons: riskDecision.reasons, context: riskDecision.context };
    }
    const result = paperBroker.placeOrder({
      accountId,
      strategyId: strategy.strategyId,
      symbol,
      side: "buy",
      quantity,
      price: lastBar.close,
      market: marketData.marketSnapshot || {},
      metadata: { source: marketData.source, trigger: "validation_cycle_entry" },
    });
    return { action: result.accepted ? "opened" : "rejected", result };
  }

  if (position) {
    const takeProfitPrice = resolveDynamicTakeProfitPrice({
      entryPrice: position.avgEntryPrice,
      takeProfitFraction: strategy.simulation.takeProfitFraction,
      exitTargetMode: strategy.simulation.exitTargetMode,
    }, lastBar) || (position.avgEntryPrice * (1 + strategy.simulation.takeProfitFraction));
    const stopLossPrice = position.avgEntryPrice * (1 - strategy.simulation.stopLossFraction);
    if (lastBar.close >= takeProfitPrice || lastBar.close <= stopLossPrice) {
      const riskDecision = evaluateTradeRisk({
        strategy,
        order: {
          accountId,
          strategyId: strategy.strategyId,
          side: "sell",
          quantity: position.quantity,
          price: lastBar.close,
          timestamp: lastBar.timestamp,
        },
        accountSummary: paperBroker.getAccountSummary({ accountId }),
        ledger: paperBroker.ledger,
        market: marketData.marketSnapshot || {},
      });
      if (!riskDecision.allowed) {
        return { action: "risk_blocked", reasons: riskDecision.reasons, context: riskDecision.context };
      }
      const result = paperBroker.placeOrder({
        accountId,
        strategyId: strategy.strategyId,
        symbol,
        side: "sell",
        quantity: position.quantity,
        price: lastBar.close,
        market: marketData.marketSnapshot || {},
        metadata: { source: marketData.source, trigger: "validation_cycle_exit" },
      });
      return { action: result.accepted ? "closed" : "rejected", result };
    }
    return { action: "held", price: lastBar.close };
  }

  return { action: "skipped", reason: "signal_below_threshold" };
}

async function runDayTradingValidation(options = {}) {
  const useCustomStrategies = Array.isArray(options.strategies);
  const strategies = (useCustomStrategies ? options.strategies : loadStrategies())
    .filter((strategy) => String(strategy.status || "") !== "disabled");
  const bars = Number(options.bars) || DEFAULT_DAY_TRADING_CONFIG.bars;
  const feesFraction = Number.isFinite(options.feesFraction) ? Number(options.feesFraction) : DEFAULT_DAY_TRADING_CONFIG.feesFraction;
  const startingCash = Number(options.startingCash) || DEFAULT_DAY_TRADING_CONFIG.startingCash;
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const marketDataLoader = typeof options.marketDataLoader === "function"
    ? options.marketDataLoader
    : fetchMarketDataForStrategy;

  const broker = new PaperBroker({ ledgerPath: LEDGER_PATH });
  broker.ensureAccount({ accountId, startingCash });

  const report = {
    generatedAt: nowIso(),
    strategiesScanned: strategies.length,
    results: [],
  };

  for (const strategy of strategies) {
    const previousBacktest = getBacktestResult(strategy.strategyId);
    const marketData = await marketDataLoader(strategy, { bars });
    const backtest = runBacktest({
      strategySpec: strategy,
      priceSeries: marketData.priceSeries,
      feesFraction,
    });
    const saved = saveBacktestResult({
      ...backtest,
      marketDataSource: marketData.source,
      marketDataWarning: marketData.warning || null,
    });
    const paperAction = await maybePaperTrade({
      paperBroker: broker,
      strategy,
      marketData,
      accountId,
    });

    report.results.push({
      strategyId: strategy.strategyId,
      marketDataSource: marketData.source,
      marketDataWarning: marketData.warning || null,
      savedTo: saved.filePath,
      backtestSummary: backtest.summary,
      paperAction,
      previousBacktestSummary: previousBacktest?.summary || null,
    });
  }

  const paperSummaries = broker.getStrategySummaries({ accountId });
  const paperMap = new Map(paperSummaries.map((summary) => [summary.strategyId, summary]));
  const strategyUniverse = useCustomStrategies ? strategies : loadStrategies();
  const updatedStrategies = strategyUniverse.map((strategy) => {
    const result = report.results.find((entry) => entry.strategyId === strategy.strategyId);
    if (!result) return strategy;
    const decision = nextPromotionDecision(strategy, {
      backtestSummary: result.backtestSummary,
      paperSummary: paperMap.get(strategy.strategyId) || null,
    });
    result.promotionDecision = decision;
    return applyPromotionDecision(strategy, decision, report.generatedAt);
  });

  if (!useCustomStrategies) {
    saveStrategiesIfChanged(strategyUniverse, updatedStrategies);
  }

  report.scoreboard = buildStrategyScoreboard({
    strategies: updatedStrategies,
    backtests: loadBacktestSummaries(),
    paperSummaries,
  });
  report.paperAccount = broker.getAccountSummary({ accountId });

  atomicWriteJsonSync(REPORT_PATH, report);
  return report;
}

function getDayTradingSnapshot(options = {}) {
  const accountId = String(options.accountId || DEFAULT_ACCOUNT_ID);
  const bundle = options.artifactBundle || _readOnlyDayTradingBundle(options);
  const broker = bundle.broker || new PaperBroker({ ledgerPath: LEDGER_PATH, readOnly: true });
  broker.ensureAccount({
    accountId,
    startingCash: DEFAULT_DAY_TRADING_CONFIG.startingCash,
    createIfMissing: true,
  });
  const strategies = bundle.strategies || loadStrategies({ readOnly: true });
  const paperAccount = bundle.paperAccount || broker.getAccountSummary({ accountId });
  const paperSummaries = bundle.paperSummaries || broker.getStrategySummaries({ accountId });
  const scoreboard = buildStrategyScoreboard({
    strategies,
    backtests: bundle.backtests || loadBacktestSummaries(),
    paperSummaries,
  });

  return {
    generatedAt: nowIso(),
    defaultConfig: clone(DEFAULT_DAY_TRADING_CONFIG),
    strategies,
    scoreboard,
    paperAccount,
    paperSummaries,
    lastReport: bundle.lastReport || readJson(REPORT_PATH, null),
  };
}

const __internal = {
  paths: {
    DATA_ROOT,
    STRATEGIES_PATH,
    LEDGER_PATH,
    REPORT_PATH,
    BACKTEST_DIR,
    EXPERIMENTS_DIR,
    EXPERIMENT_REPORT_PATH,
  },
  assertValidStrategySpec,
  DAY_TRADING_EXPERIMENT_PRESETS,
  loadStrategies,
  saveStrategies,
  simulateExecution,
  PaperBroker,
  evaluateTradeRisk,
  buildSummary,
  runBacktest,
  saveBacktestResult,
  getBacktestResult,
  loadBacktestSummaries,
  enrichBarsWithSignals,
  buildSampleSeries,
  fetchMarketDataForStrategy,
  buildStrategyScoreboard,
  buildMorningWatchlist,
  buildDayTradingExperimentVariants,
  runDayTradingExperiments,
  nextPromotionDecision,
  maybePaperTrade,
};

module.exports = {
  DEFAULT_DAY_TRADING_CONFIG,
  getDayTradingSnapshot,
  runDayTradingValidation,
  buildMorningWatchlist,
  runDayTradingExperiments,
  __internal,
};
