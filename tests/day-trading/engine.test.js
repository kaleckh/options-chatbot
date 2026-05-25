const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  createStrategy,
  buildSignalSeries,
  createMarketDataFixture,
  createMarketDataLoader,
} = require("./fixtures");

const ENGINE_PATH = path.join(__dirname, "..", "..", "src", "lib", "day-trading", "engine.js");
const HIGH_LIQUIDITY_SNAPSHOT = {
  bestBid: 100,
  bestAsk: 100.05,
  volume: 5000000,
  volumeUsd: 500000000,
  availableLiquidityUsd: 100000000,
};

function loadEngineWithTempDataRoot() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "day-trading-engine-"));
  const dataRoot = path.join(tempRoot, "day-trading-data");
  const resolvedEnginePath = require.resolve(ENGINE_PATH);
  const previousDataRoot = process.env.DAY_TRADING_DATA_ROOT;

  process.env.DAY_TRADING_DATA_ROOT = dataRoot;
  delete require.cache[resolvedEnginePath];
  const engine = require(resolvedEnginePath);

  return {
    engine,
    dataRoot,
    cleanup() {
      delete require.cache[resolvedEnginePath];
      if (previousDataRoot === undefined) {
        delete process.env.DAY_TRADING_DATA_ROOT;
      } else {
        process.env.DAY_TRADING_DATA_ROOT = previousDataRoot;
      }
      fs.rmSync(tempRoot, { recursive: true, force: true });
    },
  };
}

test("runBacktest returns deterministic profitable summary for fixture bars", () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-deterministic",
      evaluationWindow: { minimumTrades: 4 },
    });
    const priceSeries = buildSignalSeries({
      symbol: "SPY",
      signalName: strategy.simulation.entrySignal,
      warmupBars: strategy.evaluationWindow.warmupBars,
      cooldownBars: strategy.simulation.cooldownBars,
      maxHoldBars: strategy.simulation.maxHoldBars,
      takeProfitFraction: strategy.simulation.takeProfitFraction,
      stopLossFraction: strategy.simulation.stopLossFraction,
      outcomes: ["win", "win", "loss", "win"],
    });

    const result = ctx.engine.__internal.runBacktest({
      strategySpec: strategy,
      priceSeries,
      feesFraction: 0,
    });

    assert.equal(result.summary.tradeCount, 4);
    assert.equal(result.summary.eligibleForPromotion, true);
    assert.deepEqual(result.summary.vetoReasons, []);
    assert.equal(result.summary.winRate, 0.75);
    assert.ok(result.summary.totalNetReturnFraction > 0, "expected profitable fixture summary");
    assert.ok(result.summary.profitFactor > 1, "expected profit factor above 1");
  } finally {
    ctx.cleanup();
  }
});

test("evaluateTradeRisk blocks oversize, illiquid, and over-loss orders", () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy();
    const decision = ctx.engine.__internal.evaluateTradeRisk({
      strategy,
      order: {
        accountId: "paper-main",
        side: "buy",
        quantity: 25,
        price: 100,
        timestamp: "2026-03-30T14:35:00.000Z",
      },
      accountSummary: {
        accountId: "paper-main",
        startingCash: 1000,
        cash: 900,
        equity: 900,
        positions: [],
      },
      ledger: {
        fills: [
          {
            accountId: "paper-main",
            filledAt: "2026-03-30T14:00:00.000Z",
            realizedPnl: -50,
          },
        ],
      },
      market: {
        availableLiquidityUsd: 10000,
        bestBid: 99,
        bestAsk: 101,
      },
    });

    assert.equal(decision.allowed, false);
    assert.ok(decision.reasons.includes("position_size_exceeds_strategy_limit"));
    assert.ok(decision.reasons.includes("market_liquidity_below_minimum"));
    assert.ok(decision.reasons.includes("market_spread_above_maximum"));
    assert.ok(decision.reasons.includes("daily_loss_limit_breached"));
    assert.ok(decision.reasons.includes("strategy_drawdown_limit_breached"));
  } finally {
    ctx.cleanup();
  }
});

test("resolveDynamicTakeProfitPrice is direction-aware for short positions", () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const bar = {
      indicators: {
        sessionVwap: 99,
        sessionRangeMidpoint: 97,
      },
    };

    assert.equal(
      ctx.engine.__internal.resolveDynamicTakeProfitPrice({
        direction: "short",
        entryPrice: 100,
        takeProfitFraction: 0.02,
        exitTargetMode: "session_vwap_or_range_midpoint",
      }, bar),
      99,
    );
    assert.equal(
      ctx.engine.__internal.resolveDynamicTakeProfitPrice({
        direction: "long",
        entryPrice: 100,
        takeProfitFraction: 0.02,
        exitTargetMode: "session_vwap_or_range_midpoint",
      }, bar),
      102,
    );
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingValidation uses injected fixtures, persists artifacts, and updates snapshot", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategies = ctx.engine.__internal.loadStrategies().map((strategy) => ({
      ...strategy,
      version: 999,
      evaluationWindow: {
        ...strategy.evaluationWindow,
        minimumTrades: 4,
      },
    }));
    ctx.engine.__internal.saveStrategies(strategies);

    const breakoutStrategy = strategies.find((item) => item.strategyId === "spy-opening-range-breakout");
    const qqqBreakoutStrategy = strategies.find((item) => item.strategyId === "qqq-opening-range-breakout");
    const spyReclaimStrategy = strategies.find((item) => item.strategyId === "spy-vwap-trend-reclaim");
    const reclaimStrategy = strategies.find((item) => item.strategyId === "qqq-vwap-trend-reclaim");

    assert.ok(breakoutStrategy, "expected managed SPY breakout strategy");
    assert.ok(qqqBreakoutStrategy, "expected managed QQQ breakout strategy");
    assert.ok(spyReclaimStrategy, "expected managed SPY reclaim strategy");
    assert.ok(reclaimStrategy, "expected managed QQQ reclaim strategy");

    const marketDataLoader = createMarketDataLoader({
      [breakoutStrategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "SPY",
          signalName: breakoutStrategy.simulation.entrySignal,
          warmupBars: breakoutStrategy.evaluationWindow.warmupBars,
          cooldownBars: breakoutStrategy.simulation.cooldownBars,
          maxHoldBars: breakoutStrategy.simulation.maxHoldBars,
          takeProfitFraction: breakoutStrategy.simulation.takeProfitFraction,
          stopLossFraction: breakoutStrategy.simulation.stopLossFraction,
          outcomes: ["win", "win", "win", "win", "win"],
          appendLiveSignal: true,
        }),
      }),
      [qqqBreakoutStrategy.strategyId]: createMarketDataFixture({
        symbol: "QQQ",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "QQQ",
          signalName: qqqBreakoutStrategy.simulation.entrySignal,
          warmupBars: qqqBreakoutStrategy.evaluationWindow.warmupBars,
          cooldownBars: qqqBreakoutStrategy.simulation.cooldownBars,
          maxHoldBars: qqqBreakoutStrategy.simulation.maxHoldBars,
          takeProfitFraction: qqqBreakoutStrategy.simulation.takeProfitFraction,
          stopLossFraction: qqqBreakoutStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "loss", "loss", "loss"],
        }),
      }),
      [spyReclaimStrategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "SPY",
          signalName: spyReclaimStrategy.simulation.entrySignal,
          warmupBars: spyReclaimStrategy.evaluationWindow.warmupBars,
          cooldownBars: spyReclaimStrategy.simulation.cooldownBars,
          maxHoldBars: spyReclaimStrategy.simulation.maxHoldBars,
          takeProfitFraction: spyReclaimStrategy.simulation.takeProfitFraction,
          stopLossFraction: spyReclaimStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "win", "loss"],
        }),
      }),
      [reclaimStrategy.strategyId]: createMarketDataFixture({
        symbol: "QQQ",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "QQQ",
          signalName: reclaimStrategy.simulation.entrySignal,
          warmupBars: reclaimStrategy.evaluationWindow.warmupBars,
          cooldownBars: reclaimStrategy.simulation.cooldownBars,
          maxHoldBars: reclaimStrategy.simulation.maxHoldBars,
          takeProfitFraction: reclaimStrategy.simulation.takeProfitFraction,
          stopLossFraction: reclaimStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "loss"],
        }),
      }),
    });

    const report = await ctx.engine.runDayTradingValidation({
      bars: 240,
      startingCash: 10000,
      marketDataLoader,
    });

    assert.equal(report.strategiesScanned, 4);

    const breakoutResult = report.results.find((item) => item.strategyId === breakoutStrategy.strategyId);
    const reclaimResult = report.results.find((item) => item.strategyId === reclaimStrategy.strategyId);

    assert.equal(breakoutResult.marketDataSource, "fixture_series");
    assert.equal(breakoutResult.backtestSummary.eligibleForPromotion, true);
    assert.deepEqual(breakoutResult.backtestSummary.vetoReasons, []);
    assert.equal(breakoutResult.paperAction.action, "opened");

    assert.equal(reclaimResult.backtestSummary.eligibleForPromotion, false);
    assert.ok(
      reclaimResult.backtestSummary.vetoReasons.includes("insufficient_trades:2<4"),
      "expected insufficient trade veto for weak fixture",
    );

    const snapshot = ctx.engine.getDayTradingSnapshot();
    assert.equal(snapshot.lastReport.generatedAt, report.generatedAt);
    assert.equal(snapshot.paperAccount.positions.length, 1);
    assert.equal(snapshot.scoreboard.totals.withPaperActivity, 1);

    assert.ok(fs.existsSync(ctx.engine.__internal.paths.REPORT_PATH));
    assert.ok(
      fs.existsSync(path.join(ctx.engine.__internal.paths.BACKTEST_DIR, `${breakoutStrategy.strategyId}.json`)),
      "expected breakout backtest artifact",
    );

    const savedStrategies = ctx.engine.__internal.loadStrategies();
    const savedBreakout = savedStrategies.find((item) => item.strategyId === breakoutStrategy.strategyId);
    const savedReclaim = savedStrategies.find((item) => item.strategyId === reclaimStrategy.strategyId);

    assert.equal(savedBreakout.status, "paper_candidate");
    assert.equal(savedReclaim.status, "backtest_failed");
  } finally {
    ctx.cleanup();
  }
});

test("buildMorningWatchlist ranks replay-backed leaders and marks active notify candidates", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategies = ctx.engine.__internal.loadStrategies().map((strategy) => ({
      ...strategy,
      version: 999,
      evaluationWindow: {
        ...strategy.evaluationWindow,
        minimumTrades: 1,
      },
    }));
    ctx.engine.__internal.saveStrategies(strategies);

    const breakoutStrategy = strategies.find((item) => item.strategyId === "spy-opening-range-breakout");
    const qqqBreakoutStrategy = strategies.find((item) => item.strategyId === "qqq-opening-range-breakout");
    const spyReclaimStrategy = strategies.find((item) => item.strategyId === "spy-vwap-trend-reclaim");
    const reclaimStrategy = strategies.find((item) => item.strategyId === "qqq-vwap-trend-reclaim");

    assert.ok(breakoutStrategy);
    assert.ok(qqqBreakoutStrategy);
    assert.ok(spyReclaimStrategy);
    assert.ok(reclaimStrategy);

    const marketDataLoader = createMarketDataLoader({
      [breakoutStrategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          startTimestamp: "2026-03-03T13:30:00.000Z",
          symbol: "SPY",
          signalName: breakoutStrategy.simulation.entrySignal,
          warmupBars: breakoutStrategy.evaluationWindow.warmupBars,
          cooldownBars: breakoutStrategy.simulation.cooldownBars,
          maxHoldBars: breakoutStrategy.simulation.maxHoldBars,
          takeProfitFraction: breakoutStrategy.simulation.takeProfitFraction,
          stopLossFraction: breakoutStrategy.simulation.stopLossFraction,
          outcomes: ["win"],
          appendLiveSignal: true,
        }),
      }),
      [qqqBreakoutStrategy.strategyId]: createMarketDataFixture({
        symbol: "QQQ",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          startTimestamp: "2026-03-03T13:30:00.000Z",
          symbol: "QQQ",
          signalName: qqqBreakoutStrategy.simulation.entrySignal,
          warmupBars: qqqBreakoutStrategy.evaluationWindow.warmupBars,
          cooldownBars: qqqBreakoutStrategy.simulation.cooldownBars,
          maxHoldBars: qqqBreakoutStrategy.simulation.maxHoldBars,
          takeProfitFraction: qqqBreakoutStrategy.simulation.takeProfitFraction,
          stopLossFraction: qqqBreakoutStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "loss", "loss"],
        }),
      }),
      [spyReclaimStrategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          startTimestamp: "2026-03-03T13:30:00.000Z",
          symbol: "SPY",
          signalName: spyReclaimStrategy.simulation.entrySignal,
          warmupBars: spyReclaimStrategy.evaluationWindow.warmupBars,
          cooldownBars: spyReclaimStrategy.simulation.cooldownBars,
          maxHoldBars: spyReclaimStrategy.simulation.maxHoldBars,
          takeProfitFraction: spyReclaimStrategy.simulation.takeProfitFraction,
          stopLossFraction: spyReclaimStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "win"],
        }),
      }),
      [reclaimStrategy.strategyId]: createMarketDataFixture({
        symbol: "QQQ",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          startTimestamp: "2026-03-03T13:30:00.000Z",
          symbol: "QQQ",
          signalName: reclaimStrategy.simulation.entrySignal,
          warmupBars: reclaimStrategy.evaluationWindow.warmupBars,
          cooldownBars: reclaimStrategy.simulation.cooldownBars,
          maxHoldBars: reclaimStrategy.simulation.maxHoldBars,
          takeProfitFraction: reclaimStrategy.simulation.takeProfitFraction,
          stopLossFraction: reclaimStrategy.simulation.stopLossFraction,
          outcomes: ["loss", "loss"],
        }),
      }),
    });

    await ctx.engine.runDayTradingValidation({
      bars: 240,
      startingCash: 10000,
      marketDataLoader,
    });

    const watchlist = await ctx.engine.buildMorningWatchlist({
      bars: 240,
      limit: 4,
      now: "2026-03-03T15:10:00.000Z",
      marketDataLoader,
    });

    assert.equal(watchlist.selectedStrategies, 4);
    assert.equal(watchlist.notifyNowCount, 1);
    assert.equal(watchlist.items[0].strategyId, "spy-opening-range-breakout");
    assert.equal(watchlist.items[0].notifyNow, true);
    assert.equal(watchlist.items[0].liveStatus, "triggered_now");
    assert.ok(watchlist.items[0].replayEvidence?.eligibleForPromotion);
  } finally {
    ctx.cleanup();
  }
});

test("buildMorningWatchlist never notifies from synthetic fallback data", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-fallback-watch",
      name: "SPY Fallback Watch",
      evaluationWindow: {
        timeframe: "5m",
        warmupBars: 6,
        minimumTrades: 1,
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
    });

    const marketDataLoader = createMarketDataLoader({
      [strategy.strategyId]: createMarketDataFixture({
        source: "sample_fallback",
        warning: "real_market_data_failed:test",
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          startTimestamp: "2026-03-03T13:30:00.000Z",
          symbol: "SPY",
          signalName: strategy.simulation.entrySignal,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: strategy.simulation.takeProfitFraction,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: ["win", "win"],
          appendLiveSignal: true,
        }),
      }),
    });

    const validation = await ctx.engine.runDayTradingValidation({
      strategies: [strategy],
      bars: 240,
      startingCash: 10000,
      marketDataLoader,
    });

    assert.equal(validation.results[0].trustedMarketData, false);
    assert.equal(validation.results[0].savedTo, null);
    assert.equal(validation.results[0].paperAction.action, "skipped");
    assert.equal(validation.results[0].paperAction.reason, "untrusted_market_data");
    assert.equal(validation.results[0].backtestSummary.eligibleForPromotion, false);
    assert.ok(validation.results[0].backtestSummary.vetoReasons.includes("synthetic_market_data"));

    const watchlist = await ctx.engine.buildMorningWatchlist({
      strategies: [strategy],
      bars: 240,
      limit: 1,
      now: "2026-03-03T15:10:00.000Z",
      marketDataLoader,
    });

    assert.equal(watchlist.notifyNowCount, 0);
    assert.equal(watchlist.items[0].alertEligible, false);
    assert.equal(watchlist.items[0].currentDataTrusted, false);
    assert.equal(watchlist.items[0].liveStatus, "untrusted_data");
    assert.equal(watchlist.items[0].notifyNow, false);
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingValidation keeps short strategies out of paper/live promotion", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-short-backtest-only",
      name: "SPY Short Backtest Only",
      status: "draft",
      evaluationWindow: {
        timeframe: "5m",
        warmupBars: 6,
        minimumTrades: 1,
      },
      simulation: {
        direction: "short",
        entrySignal: "opening_range_breakout",
        entryExecution: "next_open",
        takeProfitFraction: 0.008,
        stopLossFraction: 0.004,
        maxHoldBars: 10,
        cooldownBars: 4,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.72,
      },
    });

    const marketDataLoader = createMarketDataLoader({
      [strategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "SPY",
          signalName: strategy.simulation.entrySignal,
          signalStrength: -0.88,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: strategy.simulation.takeProfitFraction,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: ["flat"],
          appendLiveSignal: true,
        }),
      }),
    });

    const report = await ctx.engine.runDayTradingValidation({
      strategies: [strategy],
      bars: 120,
      startingCash: 10000,
      marketDataLoader,
    });

    assert.equal(report.results[0].paperAction.action, "skipped");
    assert.equal(report.results[0].paperAction.reason, "paper_direction_unsupported:short");
    assert.equal(report.results[0].promotionDecision.reason, "paper_direction_unsupported:short");
    assert.equal(report.paperAccount.positions.length, 0);
  } finally {
    ctx.cleanup();
  }
});

test("maybePaperTrade closes long paper positions at maxHoldBars", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-paper-time-exit",
      simulation: {
        direction: "long",
        entrySignal: "opening_range_breakout",
        entryExecution: "next_open",
        takeProfitFraction: 0.5,
        stopLossFraction: 0.5,
        maxHoldBars: 2,
        cooldownBars: 0,
        maxConcurrentPositions: 1,
        useSignalStrengthThreshold: 0.72,
      },
    });
    const broker = new ctx.engine.__internal.PaperBroker({
      ledgerPath: path.join(ctx.dataRoot, "paper-time-exit-ledger.json"),
    });
    broker.ensureAccount({ accountId: "paper-main", startingCash: 10000 });

    const openingSeries = buildSignalSeries({
      symbol: "SPY",
      signalName: strategy.simulation.entrySignal,
      warmupBars: strategy.evaluationWindow.warmupBars,
      cooldownBars: strategy.simulation.cooldownBars,
      maxHoldBars: strategy.simulation.maxHoldBars,
      takeProfitFraction: strategy.simulation.takeProfitFraction,
      stopLossFraction: strategy.simulation.stopLossFraction,
      outcomes: ["flat"],
      appendLiveSignal: true,
    });
    const opened = await ctx.engine.__internal.maybePaperTrade({
      paperBroker: broker,
      strategy,
      marketData: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: openingSeries,
      }),
      accountId: "paper-main",
    });
    assert.equal(opened.action, "opened");

    const lastBar = openingSeries[openingSeries.length - 1];
    const lastMs = new Date(lastBar.timestamp).getTime();
    const laterSeries = openingSeries.concat([
      {
        ...lastBar,
        timestamp: new Date(lastMs + 5 * 60 * 1000).toISOString(),
        open: lastBar.close,
        high: lastBar.close * 1.001,
        low: lastBar.close * 0.999,
        close: lastBar.close,
        signals: {},
      },
      {
        ...lastBar,
        timestamp: new Date(lastMs + 10 * 60 * 1000).toISOString(),
        open: lastBar.close,
        high: lastBar.close * 1.001,
        low: lastBar.close * 0.999,
        close: lastBar.close,
        signals: {},
      },
    ]);

    const closed = await ctx.engine.__internal.maybePaperTrade({
      paperBroker: broker,
      strategy,
      marketData: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: laterSeries,
      }),
      accountId: "paper-main",
    });

    assert.equal(closed.action, "closed");
    assert.equal(closed.reason, "time_exit");
    assert.equal(closed.heldBars, 2);
    assert.equal(broker.getAccountSummary({ accountId: "paper-main" }).positions.length, 0);
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingExperiments ranks the strongest trusted variant and persists the latest report", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-experiment-base",
      name: "SPY Experiment Base",
      evaluationWindow: {
        timeframe: "5m",
        warmupBars: 6,
        minimumTrades: 3,
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
    });

    const marketDataLoader = createMarketDataLoader({
      [strategy.strategyId]: createMarketDataFixture({
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "SPY",
          signalName: strategy.simulation.entrySignal,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: 0.006,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: ["win", "win", "loss", "win"],
        }),
      }),
    });

    const report = await ctx.engine.runDayTradingExperiments({
      strategies: [strategy],
      bars: 240,
      strictMarketData: true,
      top: 4,
      grid: {
        opening_range_breakout: {
          signalThresholds: [0.72],
          takeProfitFractions: [0.006, 0.009],
          stopLossFractions: [0.004],
          maxHoldBars: [10],
        },
      },
      marketDataLoader,
    });

    assert.equal(report.strategiesTested, 1);
    assert.equal(report.variantsTested, 2);
    assert.equal(report.trustedVariantCount, 2);
    assert.ok(report.eligibleVariantCount >= 1);
    assert.equal(report.recommendation, "candidate_ready_for_live_watchlist");
    assert.equal(report.leaders[0].parameters.takeProfitFraction, 0.006);
    assert.equal(report.leaders[0].trustedMarketData, true);
    assert.ok(fs.existsSync(ctx.engine.__internal.paths.EXPERIMENT_REPORT_PATH));
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingExperiments disqualifies synthetic fallback data when strict mode is enabled", async () => {
  const ctx = loadEngineWithTempDataRoot();
  try {
    const strategy = createStrategy({
      strategyId: "spy-experiment-fallback",
      name: "SPY Fallback Experiment",
      evaluationWindow: {
        timeframe: "5m",
        warmupBars: 6,
        minimumTrades: 1,
      },
    });

    const marketDataLoader = createMarketDataLoader({
      [strategy.strategyId]: createMarketDataFixture({
        source: "sample_fallback",
        warning: "real_market_data_failed:test",
        symbol: "SPY",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "SPY",
          signalName: strategy.simulation.entrySignal,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: strategy.simulation.takeProfitFraction,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: ["win", "win"],
        }),
      }),
    });

    const report = await ctx.engine.runDayTradingExperiments({
      strategies: [strategy],
      bars: 120,
      strictMarketData: true,
      top: 2,
      grid: {
        opening_range_breakout: {
          signalThresholds: [0.72],
          takeProfitFractions: [0.008],
          stopLossFractions: [0.004],
          maxHoldBars: [10],
        },
      },
      marketDataLoader,
    });

    assert.equal(report.trustedVariantCount, 0);
    assert.equal(report.untrustedVariantCount, 1);
    assert.equal(report.eligibleVariantCount, 0);
    assert.equal(report.recommendation, "improve_intraday_data_source");
    assert.equal(report.leaders[0].trustedMarketData, false);
    assert.ok(report.leaders[0].summary.vetoReasons.includes("synthetic_market_data"));
  } finally {
    ctx.cleanup();
  }
});
