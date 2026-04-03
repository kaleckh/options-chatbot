const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  buildSignalSeries,
  createMarketDataFixture,
  createMarketDataLoader,
} = require("./fixtures");

const CRYPTO_ENGINE_PATH = path.join(__dirname, "..", "..", "src", "lib", "day-trading", "crypto-engine.js");
const ROUTER_PATH = path.join(__dirname, "..", "..", "src", "lib", "day-trading", "index.js");
const LEGACY_ENGINE_PATH = path.join(__dirname, "..", "..", "src", "lib", "day-trading", "engine.js");
const HIGH_LIQUIDITY_SNAPSHOT = {
  bestBid: 100,
  bestAsk: 100.08,
  volume: 5000000,
  volumeUsd: 500000000,
  availableLiquidityUsd: 120000000,
};
const TIGHT_LIQUIDITY_SNAPSHOT = {
  bestBid: 99.995,
  bestAsk: 100.005,
  volume: 5000000,
  volumeUsd: 500000000,
  availableLiquidityUsd: 120000000,
};

function loadCryptoEngineWithTempDataRoot() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "crypto-day-trading-engine-"));
  const dataRoot = path.join(tempRoot, "crypto-day-trading-data");
  const legacyDataRoot = path.join(tempRoot, "legacy-day-trading-data");
  const resolvedCryptoEnginePath = require.resolve(CRYPTO_ENGINE_PATH);
  const resolvedRouterPath = require.resolve(ROUTER_PATH);
  const resolvedLegacyEnginePath = require.resolve(LEGACY_ENGINE_PATH);

  process.env.DAY_TRADING_CRYPTO_DATA_ROOT = dataRoot;
  process.env.DAY_TRADING_DATA_ROOT = legacyDataRoot;
  delete require.cache[resolvedCryptoEnginePath];
  delete require.cache[resolvedRouterPath];
  delete require.cache[resolvedLegacyEnginePath];

  const engine = require(resolvedCryptoEnginePath);
  const router = require(resolvedRouterPath);

  return {
    engine,
    router,
    dataRoot,
    cleanup() {
      delete require.cache[resolvedCryptoEnginePath];
      delete require.cache[resolvedRouterPath];
      delete require.cache[resolvedLegacyEnginePath];
      delete process.env.DAY_TRADING_CRYPTO_DATA_ROOT;
      delete process.env.DAY_TRADING_DATA_ROOT;
      fs.rmSync(tempRoot, { recursive: true, force: true });
    },
  };
}

function createCryptoFixtureStrategy(engine, strategyId, overrides = {}) {
  const template = engine.__internal.loadStrategies().find((strategy) => strategy.strategyId === strategyId);
  assert.ok(template, `missing crypto strategy template ${strategyId}`);
  return {
    ...template,
    version: 999,
    evaluationWindow: {
      ...template.evaluationWindow,
      minimumTrades: overrides.minimumTrades ?? 3,
    },
    ...overrides,
  };
}

function createCryptoBar(timestamp, values = {}) {
  const close = values.close ?? 100;
  const volume = values.volume ?? 1000;
  return {
    timestamp,
    symbol: values.symbol || "BTCUSDT",
    open: values.open ?? close,
    high: values.high ?? close,
    low: values.low ?? close,
    close,
    volume,
    quoteVolume: values.quoteVolume ?? close * volume,
    tradeCount: values.tradeCount ?? 10,
    signals: values.signals || {},
    indicators: values.indicators || {},
  };
}

function createTradeablePreflightMarketData(timestamp, overrides = {}) {
  const baseBar = createCryptoBar(timestamp, {
    open: 99.95,
    high: 100.2,
    low: 99.9,
    close: 100,
    indicators: {
      sessionVwap: 100.85,
      sessionRangeMidpoint: 100.8,
      regimeState: "range_tradeable",
      tradeable: true,
      regimeBlockers: [],
    },
    signals: {
      crypto_range_mean_reversion: 0.82,
    },
  });

  return {
    source: "crypto_preflight_fixture",
    symbol: "BTCUSDT",
    trusted: true,
    market: "crypto",
    exchange: "fixture",
    marketType: "spot",
    sessionMode: "scheduled_windows",
    alertWindows: [{
      id: "denver_core",
      label: "Denver Core",
      startEt: "09:00",
      endEt: "13:00",
    }],
    marketSnapshot: TIGHT_LIQUIDITY_SNAPSHOT,
    priceSeries: [baseBar],
    ...overrides,
  };
}

function buildPilotEntry(index, overrides = {}) {
  const timestamp = new Date(Date.parse("2026-04-01T13:30:00.000Z") + (index * 5 * 60 * 1000)).toISOString();
  return {
    entryId: `eligible_${index}`,
    tradeTimestamp: timestamp,
    symbol: "BTCUSDT",
    setupId: "btcusdt-crypto-range-mean-reversion",
    regime: "range",
    pnlR: index % 5 === 0 ? -0.2 : 0.5,
    pnlUsd: index % 5 === 0 ? -40 : 100,
    ruleAdherenceScore: 95,
    pilotEligible: true,
    pilotDisqualificationReasons: [],
    entryLiquidityRole: index % 4 === 0 ? "taker" : "maker",
    exitLiquidityRole: "maker",
    entryFillRatio: index % 6 === 0 ? 0.95 : 1,
    exitFillRatio: 1,
    exitReason: index % 5 === 0 ? "stop_loss" : "target_hit",
    stopExecutionQuality: index % 5 === 0 ? "clean" : "not_applicable",
    entrySlippageBps: index % 4 === 0 ? 2 : 1,
    exitSlippageBps: index % 5 === 0 ? 3 : 1.5,
    ...overrides,
  };
}

function buildBottomReclaimWithoutBreakdownBars() {
  const start = Date.parse("2026-04-01T13:00:00.000Z");
  const ts = (index) => new Date(start + (index * 5 * 60 * 1000)).toISOString();
  const bars = [];
  for (let index = 0; index < 20; index += 1) {
    const base = 100 - (index * 0.08);
    bars.push(createCryptoBar(ts(index), {
      open: base + 0.03,
      high: base + 0.08,
      low: base - 0.1,
      close: base,
      volume: 1000 + (index * 10),
    }));
  }
  bars.push(createCryptoBar(ts(20), { open: 98.48, high: 98.56, low: 98.18, close: 98.3, volume: 1200 }));
  bars.push(createCryptoBar(ts(21), { open: 98.32, high: 98.36, low: 98.12, close: 98.22, volume: 1400 }));
  bars.push(createCryptoBar(ts(22), { open: 98.18, high: 98.28, low: 98.04, close: 98.24, volume: 1700 }));
  bars.push(createCryptoBar(ts(23), { open: 98.12, high: 98.26, low: 98.02, close: 98.2, volume: 2100 }));
  return bars;
}

function buildOpeningRangeBreakoutBars(variant) {
  const start = Date.parse("2026-04-01T13:00:00.000Z");
  const ts = (index) => new Date(start + (index * 5 * 60 * 1000)).toISOString();
  const bars = [];
  if (variant === "breakout_retest") {
    for (let index = 0; index < 19; index += 1) {
      const close = index < 6 ? 100 + (index * 0.03) : 100.22 + ((index - 6) * 0.02);
      bars.push(createCryptoBar(ts(index), {
        open: close - 0.03,
        high: close + 0.06,
        low: close - 0.06,
        close,
        volume: 1000 + (index * 10),
      }));
    }
    bars.push(createCryptoBar(ts(19), { open: 100.5, high: 100.68, low: 100.46, close: 100.62, volume: 1500 }));
    bars.push(createCryptoBar(ts(20), { open: 100.44, high: 100.6, low: 100.14, close: 100.56, volume: 1650 }));
    return bars;
  }

  for (let index = 0; index < 19; index += 1) {
    const drift = index < 3 ? 0.03 * index : 0.02 + ((index - 3) * 0.005);
    const close = 100 + drift;
    bars.push(createCryptoBar(ts(index), {
      open: close - 0.02,
      high: close + 0.05,
      low: close - 0.05,
      close,
      volume: 1000 + (index * 8),
    }));
  }
  bars.push(createCryptoBar(ts(19), { open: 100.18, high: 100.62, low: 100.14, close: 100.58, volume: 1800 }));
  bars.push(createCryptoBar(ts(20), { open: 100.56, high: 100.7, low: 100.5, close: 100.66, volume: 1500 }));
  return bars;
}

test("resampleOneMinuteBarsToFiveMinutes aggregates crypto minute bars deterministically", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const bars = [
      { timestamp: "2026-04-01T12:00:00.000Z", symbol: "BTCUSDT", open: 100, high: 101, low: 99.5, close: 100.5, volume: 10, quoteVolume: 1005, tradeCount: 10 },
      { timestamp: "2026-04-01T12:01:00.000Z", symbol: "BTCUSDT", open: 100.5, high: 102, low: 100.2, close: 101.8, volume: 9, quoteVolume: 915, tradeCount: 11 },
      { timestamp: "2026-04-01T12:04:00.000Z", symbol: "BTCUSDT", open: 101.8, high: 103, low: 101.5, close: 102.6, volume: 11, quoteVolume: 1120, tradeCount: 9 },
      { timestamp: "2026-04-01T12:05:00.000Z", symbol: "BTCUSDT", open: 102.6, high: 103.4, low: 102.2, close: 103.1, volume: 8, quoteVolume: 825, tradeCount: 8 },
    ];

    const aggregated = ctx.engine.__internal.resampleOneMinuteBarsToFiveMinutes(bars);
    assert.equal(aggregated.length, 2);
    assert.equal(aggregated[0].timestamp, "2026-04-01T12:00:00.000Z");
    assert.equal(aggregated[0].open, 100);
    assert.equal(aggregated[0].high, 103);
    assert.equal(aggregated[0].low, 99.5);
    assert.equal(aggregated[0].close, 102.6);
    assert.equal(aggregated[0].volume, 30);
    assert.equal(aggregated[1].timestamp, "2026-04-01T12:05:00.000Z");
    assert.equal(aggregated[1].close, 103.1);
  } finally {
    ctx.cleanup();
  }
});

test("importHistoryForSymbol loads Binance-style CSV into normalized and derived crypto stores", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const csvPath = path.join(ctx.dataRoot, "btc.csv");
    fs.mkdirSync(path.dirname(csvPath), { recursive: true });
    fs.writeFileSync(
      csvPath,
      [
        "1711972800000,70000,70100,69950,70080,12,1711972859999,840000,12,6,420000,0",
        "1711972860000,70080,70200,70040,70190,13,1711972919999,912470,15,7,470000,0",
        "1711972920000,70190,70320,70180,70250,10,1711972979999,702500,14,5,350000,0",
      ].join("\n"),
      "utf8",
    );

    const report = await ctx.engine.__internal.importHistoryForSymbol({
      symbol: "BTCUSDT",
      input: csvPath,
      minutes: 3,
    });

    assert.equal(report.symbol, "BTCUSDT");
    assert.equal(report.importedBars, 3);
    assert.equal(report.source, "binance_spot_csv");
    const normalizedBars = ctx.engine.__internal.loadNormalizedBars("BTCUSDT");
    assert.equal(normalizedBars.length, 3);
    assert.ok(fs.existsSync(path.join(ctx.engine.__internal.paths.DERIVED_5M_DIR, "BTCUSDT-5m.json")));
  } finally {
    ctx.cleanup();
  }
});

test("bottom reclaim strategy template is available as a managed BTC research candidate", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-bottom-reclaim");
    assert.equal(strategy.marketUniverse.symbols[0], "BTCUSDT");
    assert.equal(strategy.simulation.entrySignal, "crypto_bottom_reclaim");
    assert.ok(strategy.metadata.tags.includes("bottom"));
    assert.ok(strategy.metadata.tags.includes("stoch-rsi"));
  } finally {
    ctx.cleanup();
  }
});

test("failed breakdown reclaim strategy template is available as a managed BTC research candidate", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-failed-breakdown-reclaim");
    assert.equal(strategy.marketUniverse.symbols[0], "BTCUSDT");
    assert.equal(strategy.simulation.entrySignal, "crypto_failed_breakdown_reclaim");
    assert.ok(strategy.metadata.tags.includes("failed-breakdown"));
    assert.ok(strategy.metadata.tags.includes("reclaim"));
  } finally {
    ctx.cleanup();
  }
});

test("opening range breakout templates are available as managed BTC research candidates", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const closeVariant = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-close");
    const retestVariant = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-retest");
    assert.equal(closeVariant.simulation.entrySignal, "crypto_opening_range_breakout");
    assert.equal(retestVariant.simulation.entrySignal, "crypto_opening_range_breakout");
    assert.equal(closeVariant.metadata.openingRangeVariant, "breakout_close");
    assert.equal(closeVariant.metadata.openingRangeBars, 3);
    assert.equal(retestVariant.metadata.openingRangeVariant, "breakout_retest");
    assert.equal(retestVariant.metadata.openingRangeBars, 6);
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingValidation uses trusted crypto fixtures and updates the crypto snapshot", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategies = [
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-bottom-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-failed-breakdown-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-close", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-retest", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-trend-continuation", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "ethusdt-crypto-trend-continuation", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "solusdt-crypto-event-watch", { status: "disabled" }),
    ];
    ctx.engine.__internal.saveStrategies(strategies);

    const fixtureMap = {};
    for (const strategy of strategies) {
      fixtureMap[strategy.strategyId] = createMarketDataFixture({
        source: "crypto_fixture",
        symbol: strategy.marketUniverse.symbols[0],
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: strategy.marketUniverse.symbols[0],
          signalName: strategy.simulation.entrySignal,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: strategy.simulation.takeProfitFraction,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: strategy.strategyId.startsWith("btcusdt")
            ? ["win", "win", "win", "win"]
            : ["loss", "win", "loss", "win"],
          appendLiveSignal: strategy.strategyId.startsWith("btcusdt"),
        }),
      });
      fixtureMap[strategy.strategyId].trusted = true;
      fixtureMap[strategy.strategyId].market = "crypto";
      fixtureMap[strategy.strategyId].exchange = "fixture";
      fixtureMap[strategy.strategyId].marketType = "spot";
      fixtureMap[strategy.strategyId].sessionMode = "scheduled_windows";
      fixtureMap[strategy.strategyId].alertWindows = ctx.engine.__internal.DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows;
    }

    const marketDataLoader = createMarketDataLoader(fixtureMap);
    const report = await ctx.engine.runDayTradingValidation({
      bars: 240,
      startingCash: 10000,
      marketDataLoader,
    });

    assert.equal(report.market, "crypto");
    assert.equal(report.strategiesScanned, 7);
    assert.equal(report.results[0].marketDataSource, "crypto_fixture");
    assert.equal(report.results[0].trustedMarketData, true);
    assert.equal(report.profitabilityProfileId, "crypto_profitability_v1");

    const snapshot = ctx.engine.getDayTradingSnapshot();
    assert.equal(snapshot.market, "crypto");
    assert.equal(snapshot.lastReport.generatedAt, report.generatedAt);
    assert.equal(snapshot.scoreboard.totals.strategies, 8);
    assert.equal(snapshot.operatingPlan.activeSetupId, "btcusdt-crypto-range-mean-reversion");
    assert.equal(snapshot.pilotSummary.progress.targetTrades, 50);
    assert.equal(snapshot.profitabilityTickets.todayGate.dailyTradeCap, 2);
    assert.equal(snapshot.artifactHealth.status, "aligned");
    assert.equal(
      snapshot.strategies.find((strategy) => strategy.strategyId === "solusdt-crypto-event-watch")?.status,
      "disabled",
    );
  } finally {
    ctx.cleanup();
  }
});

test("loadCryptoMarketDataForStrategy respects bars=all and window modes on imported crypto history", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const morningBars = Array.from({ length: 10 }, (_, index) => ({
      timestamp: new Date(Date.parse("2026-04-01T13:00:00.000Z") + (index * 60 * 1000)).toISOString(),
      symbol: "BTCUSDT",
      open: 100 + (index * 0.1),
      high: 100.2 + (index * 0.1),
      low: 99.9 + (index * 0.1),
      close: 100.1 + (index * 0.1),
      volume: 10 + index,
      quoteVolume: 1000 + (index * 5),
      tradeCount: 5 + index,
    }));
    const offSessionBars = Array.from({ length: 10 }, (_, index) => ({
      timestamp: new Date(Date.parse("2026-04-02T00:00:00.000Z") + (index * 60 * 1000)).toISOString(),
      symbol: "BTCUSDT",
      open: 102 + (index * 0.1),
      high: 102.2 + (index * 0.1),
      low: 101.9 + (index * 0.1),
      close: 102.1 + (index * 0.1),
      volume: 11 + index,
      quoteVolume: 1100 + (index * 5),
      tradeCount: 6 + index,
    }));
    ctx.engine.__internal.saveNormalizedBars("BTCUSDT", [...morningBars, ...offSessionBars], { source: "unit_test" });
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");

    const allHours = await ctx.engine.__internal.loadCryptoMarketDataForStrategy(strategy, {
      bars: "all",
      includeLive: false,
      windowMode: "all_hours",
    });
    const fixedSession = await ctx.engine.__internal.loadCryptoMarketDataForStrategy(strategy, {
      bars: "all",
      includeLive: false,
      windowMode: "denver_core",
    });

    assert.equal(allHours.barsRequested, "all");
    assert.equal(allHours.windowMode, "all_hours");
    assert.equal(allHours.trusted, true);
    assert.equal(allHours.rawBarCount, 20);
    assert.equal(allHours.derivedBarCount, 4);
    assert.equal(allHours.priceSeries.length, 4);
    assert.equal(fixedSession.windowMode, "denver_core");
    assert.equal(fixedSession.priceSeries.length, 4);
    assert.equal(ctx.engine.__internal.classifyWindow("2026-04-01T13:05:00.000Z", { windowMode: "denver_core" }).active, true);
    assert.equal(ctx.engine.__internal.classifyWindow("2026-04-01T12:05:00.000Z", { windowMode: "denver_core" }).active, false);
    assert.equal(ctx.engine.__internal.classifyWindow("2026-04-05T13:05:00.000Z", { windowMode: "denver_core" }).active, false);
    assert.equal(ctx.engine.__internal.classifyWindow("2026-04-01T15:00:00.000Z", { windowMode: "all_hours" }).active, true);
  } finally {
    ctx.cleanup();
  }
});

test("buildMorningWatchlist blocks crypto notify decisions on untrusted data", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", {
      status: "paper_candidate",
    });
    ctx.engine.__internal.saveStrategies([strategy]);

    const marketDataLoader = async () => ({
      ...createMarketDataFixture({
        source: "crypto_fixture_untrusted",
        symbol: "BTCUSDT",
        marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
        priceSeries: buildSignalSeries({
          symbol: "BTCUSDT",
          signalName: strategy.simulation.entrySignal,
          warmupBars: strategy.evaluationWindow.warmupBars,
          cooldownBars: strategy.simulation.cooldownBars,
          maxHoldBars: strategy.simulation.maxHoldBars,
          takeProfitFraction: strategy.simulation.takeProfitFraction,
          stopLossFraction: strategy.simulation.stopLossFraction,
          outcomes: ["win", "win", "win"],
          appendLiveSignal: true,
          startTimestamp: "2026-04-01T12:00:00.000Z",
        }),
      }),
      trusted: false,
      warning: "live_poll_failed:test",
      market: "crypto",
      exchange: "fixture",
      marketType: "spot",
      sessionMode: "scheduled_windows",
      alertWindows: ctx.engine.__internal.DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows,
    });

    const watchlist = await ctx.engine.buildMorningWatchlist({
      bars: 120,
      limit: 1,
      now: "2026-04-01T12:15:00.000Z",
      windowMode: "all_hours",
      marketDataLoader,
    });

    assert.equal(watchlist.market, "crypto");
    assert.equal(watchlist.windowMode, "scheduled_windows");
    assert.equal(watchlist.items.length, 1);
    assert.equal(watchlist.items[0].currentDataTrusted, false);
    assert.equal(watchlist.items[0].liveStatus, "untrusted_data");
    assert.equal(watchlist.items[0].notifyNow, false);
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingExperiments keeps crypto research on controls only until a family clears the trade gate", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategies = [
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-bottom-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-failed-breakdown-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-close", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-retest", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-trend-continuation", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "ethusdt-crypto-trend-continuation", { status: "paper_candidate" }),
    ];

    const fixtureMap = {};
    for (const strategy of strategies) {
      fixtureMap[strategy.strategyId] = {
        ...createMarketDataFixture({
          source: "crypto_fixture_phase_a",
          symbol: strategy.marketUniverse.symbols[0],
          marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
          priceSeries: buildSignalSeries({
            symbol: strategy.marketUniverse.symbols[0],
            signalName: strategy.simulation.entrySignal,
            warmupBars: strategy.evaluationWindow.warmupBars,
            cooldownBars: strategy.simulation.cooldownBars,
            maxHoldBars: strategy.simulation.maxHoldBars,
            takeProfitFraction: strategy.simulation.takeProfitFraction,
            stopLossFraction: strategy.simulation.stopLossFraction,
            outcomes: ["win", "loss", "win"],
          }),
        }),
        trusted: true,
        market: "crypto",
        exchange: "fixture",
        marketType: "spot",
        sessionMode: "scheduled_windows",
        alertWindows: ctx.engine.__internal.DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows,
      };
    }

    const report = await ctx.engine.runDayTradingExperiments({
      strategies,
      windowMode: "scheduled_windows",
      bars: "all",
      marketDataLoader: createMarketDataLoader(fixtureMap),
    });

    assert.equal(report.researchMode, "control_first");
    assert.equal(report.phaseA.controlResults.length, 7);
    assert.equal(report.phaseB.unlocked, false);
    assert.equal(report.phaseB.results.length, 0);
  } finally {
    ctx.cleanup();
  }
});

test("runDayTradingExperiments unlocks one narrow challenger batch when a crypto family clears the trade gate", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategies = [
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-bottom-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-failed-breakdown-reclaim", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-close", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-retest", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-trend-continuation", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "ethusdt-crypto-trend-continuation", { status: "paper_candidate" }),
    ];

    const fixtureMap = {};
    for (const strategy of strategies) {
      const isRangeMeanReversion = strategy.simulation.entrySignal === "crypto_range_mean_reversion";
      fixtureMap[strategy.strategyId] = {
        ...createMarketDataFixture({
          source: "crypto_fixture_phase_b",
          symbol: strategy.marketUniverse.symbols[0],
          marketSnapshot: HIGH_LIQUIDITY_SNAPSHOT,
          priceSeries: buildSignalSeries({
            symbol: strategy.marketUniverse.symbols[0],
            signalName: strategy.simulation.entrySignal,
            warmupBars: strategy.evaluationWindow.warmupBars,
            cooldownBars: strategy.simulation.cooldownBars,
            maxHoldBars: strategy.simulation.maxHoldBars,
            takeProfitFraction: strategy.simulation.takeProfitFraction,
            stopLossFraction: strategy.simulation.stopLossFraction,
            outcomes: isRangeMeanReversion
              ? Array.from({ length: 24 }, () => "win")
              : ["loss", "loss", "win"],
          }),
        }),
        trusted: true,
        market: "crypto",
        exchange: "fixture",
        marketType: "spot",
        sessionMode: "scheduled_windows",
        alertWindows: ctx.engine.__internal.DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows,
      };
    }

    const report = await ctx.engine.runDayTradingExperiments({
      strategies,
      windowMode: "scheduled_windows",
      bars: "all",
      marketDataLoader: createMarketDataLoader(fixtureMap),
    });

    assert.equal(report.phaseB.unlocked, true);
    assert.equal(report.phaseB.batchShape, "1_control_plus_3_challengers");
    assert.equal(report.phaseB.results.length, 4);
    assert.equal(report.phaseB.selectedFamilyWindow.strategyFamily, "crypto_range_mean_reversion");
    assert.equal(report.recommendation, "run_narrow_challenger_batch_only");
  } finally {
    ctx.cleanup();
  }
});

test("profitability preflight enforces two approved BTC entries per Denver trading day and resets next day", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");
    ctx.engine.__internal.saveStrategies([strategy]);
    const marketDataLoader = async () => createTradeablePreflightMarketData("2026-04-01T13:35:00.000Z");

    const first = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T13:35:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader,
    });
    const second = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T13:45:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader,
    });
    const third = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T13:55:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader,
    });
    const nextDay = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-02T13:35:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader: async () => createTradeablePreflightMarketData("2026-04-02T13:35:00.000Z"),
    });

    assert.equal(first.approved, true);
    assert.equal(second.approved, true);
    assert.equal(third.approved, false);
    assert.ok(third.reasons.includes("daily_trade_cap_reached"));
    assert.equal(nextDay.approved, true);
    assert.equal(nextDay.systemGate.todayGate.remainingApprovals, 1);
  } finally {
    ctx.cleanup();
  }
});

test("snapshot exposes same-day profitability tickets after approvals", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const marketDataLoader = async () => createTradeablePreflightMarketData("2026-04-01T13:35:00.000Z");

    await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T13:35:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader,
    });

    const snapshot = ctx.engine.getDayTradingSnapshot({ now: "2026-04-01T13:40:00.000Z" });

    assert.equal(snapshot.profitabilityTickets.todaysTickets.length, 1);
    assert.equal(snapshot.profitabilityTickets.todaysTickets[0].lifecycleStatus, "approved");
    assert.equal(snapshot.profitabilityTickets.todayGate.remainingApprovals, 1);
  } finally {
    ctx.cleanup();
  }
});

test("unused profitability tickets expire at the end of the Denver session", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");
    ctx.engine.__internal.saveStrategies([strategy]);

    const approval = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T16:55:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader: async () => createTradeablePreflightMarketData("2026-04-01T16:55:00.000Z"),
    });
    assert.equal(approval.approved, true);

    const ticketStore = ctx.engine.__internal.readProfitabilityTicketStore();
    const summary = ctx.engine.__internal.buildProfitabilityPilotSummary([], {
      ticketStore,
      now: "2026-04-01T17:05:00.000Z",
    });

    assert.equal(summary.todayGate.expiredTickets, 1);
    assert.equal(summary.todayGate.remainingApprovals, 2);
    assert.equal(summary.todayGate.activeSessionWindow, false);
  } finally {
    ctx.cleanup();
  }
});

test("journal entries linked to approved tickets consume the ticket and count toward pilot metrics", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");
    ctx.engine.__internal.saveStrategies([strategy]);

    const approval = await ctx.engine.requestProfitabilityPreflightTicket({
      now: "2026-04-01T13:35:00.000Z",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      marketDataLoader: async () => createTradeablePreflightMarketData("2026-04-01T13:35:00.000Z"),
    });

    const result = ctx.engine.appendProfitabilityJournalEntry({
      ticketId: approval.ticket.ticketId,
      tradeTimestamp: "2026-04-01T13:40:00.000Z",
      sessionLabel: "Denver Core",
      symbol: "BTCUSDT",
      regime: "range",
      setupId: "btcusdt-crypto-range-mean-reversion",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      side: "buy",
      plannedEntryPrice: 100,
      actualEntryPrice: 100.02,
      stopPrice: 99.6,
      targetPrice: 100.5,
      actualExitPrice: 100.45,
      orderType: "limit",
      entryLiquidityRole: "maker",
      exitLiquidityRole: "maker",
      entryFillRatio: 1,
      exitFillRatio: 1,
      exitReason: "target_hit",
      stopExecutionQuality: "not_applicable",
      sizeUsd: 500,
      feesUsd: 1.2,
      spreadSlippageUsd: 0.8,
      pnlR: 1.1,
      pnlUsd: 22,
      screenshotPath: "screenshots/btc-ticket-trade.png",
      ruleAdherenceScore: 100,
      mistakeTag: "none",
      note: "Clean ticket-linked pilot trade.",
    });

    const snapshot = ctx.engine.getDayTradingSnapshot({ now: "2026-04-01T13:45:00.000Z" });

    assert.equal(result.entry.pilotEligible, true);
    assert.equal(result.summary.journalStats.eligibleTradeCount, 1);
    assert.equal(snapshot.profitabilityTickets.todaysTickets[0].lifecycleStatus, "used");
    assert.equal(snapshot.profitabilityTickets.todayGate.usedTickets, 1);
  } finally {
    ctx.cleanup();
  }
});

test("artifact health warns when saved strategies and watchlists still point to old windows", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const staleStrategy = {
      ...createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion"),
      metadata: {
        ...createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion").metadata,
        alertWindowIds: ["us_morning", "asia_open"],
      },
    };
    ctx.engine.__internal.saveStrategies([staleStrategy]);
    fs.writeFileSync(
      ctx.engine.__internal.paths.WATCHLIST_PATH,
      `${JSON.stringify({
        profitabilityProfileId: ctx.engine.__internal.PROFITABILITY_PROFILE_ID,
        generatedAt: "2026-04-02T04:33:05.500Z",
        alertWindows: [
          { id: "us_morning", label: "US Morning", startEt: "08:00", endEt: "11:00" },
          { id: "asia_open", label: "Asia Open", startEt: "20:00", endEt: "23:00" },
        ],
      }, null, 2)}\n`,
      "utf8",
    );

    const snapshot = ctx.engine.getDayTradingSnapshot();

    assert.equal(snapshot.artifactHealth.status, "warning");
    assert.ok(snapshot.artifactHealth.warnings.some((warning) => warning.includes("Saved strategy artifacts")));
    assert.ok(snapshot.artifactHealth.warnings.some((warning) => warning.includes("latest watchlist artifact")));
  } finally {
    ctx.cleanup();
  }
});

test("journal entries without a valid ticket are recorded but disqualified from pilot metrics", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const result = ctx.engine.appendProfitabilityJournalEntry({
      ticketId: "missing-ticket",
      tradeTimestamp: "2026-04-01T13:40:00.000Z",
      sessionLabel: "Denver Core",
      symbol: "BTCUSDT",
      regime: "range",
      setupId: "btcusdt-crypto-range-mean-reversion",
      setup_match_confirmed: true,
      headline_lockout_checked: true,
      maker_limit_plan_confirmed: true,
      side: "buy",
      plannedEntryPrice: 100,
      actualEntryPrice: 100.02,
      stopPrice: 99.6,
      targetPrice: 100.5,
      actualExitPrice: 100.45,
      orderType: "limit",
      entryLiquidityRole: "maker",
      exitLiquidityRole: "maker",
      entryFillRatio: 1,
      exitFillRatio: 1,
      exitReason: "target_hit",
      stopExecutionQuality: "not_applicable",
      sizeUsd: 1000,
      feesUsd: 1,
      spreadSlippageUsd: 1,
      pnlR: 0.8,
      pnlUsd: 20,
      screenshotPath: "C:\\temp\\trade.png",
      ruleAdherenceScore: 100,
      mistakeTag: "none",
      note: "unit test",
    });

    assert.equal(result.entry.pilotEligible, false);
    assert.ok(result.entry.pilotDisqualificationReasons.includes("ticket_not_found"));
    assert.equal(result.summary.journalStats.eligibleTradeCount, 0);
    assert.equal(result.summary.journalStats.disqualifiedTradeCount, 1);
  } finally {
    ctx.cleanup();
  }
});

test("range mean reversion flags mid-range and expansion blockers explicitly", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");
    const start = Date.parse("2026-04-01T13:00:00.000Z");
    const ts = (index) => new Date(start + (index * 5 * 60 * 1000)).toISOString();

    const midRangeBars = [
      createCryptoBar(ts(0), { open: 100.02, high: 100.05, low: 100.0, close: 100.02 }),
      createCryptoBar(ts(1), { open: 100.02, high: 100.12, low: 100.01, close: 100.1 }),
      createCryptoBar(ts(2), { open: 100.1, high: 100.25, low: 100.08, close: 100.2 }),
      createCryptoBar(ts(3), { open: 100.2, high: 100.35, low: 100.18, close: 100.3 }),
      createCryptoBar(ts(4), { open: 100.3, high: 100.45, low: 100.24, close: 100.4 }),
      createCryptoBar(ts(5), { open: 100.4, high: 100.5, low: 100.3, close: 100.36 }),
      createCryptoBar(ts(6), { open: 100.36, high: 100.42, low: 100.28, close: 100.32 }),
      createCryptoBar(ts(7), { open: 100.32, high: 100.36, low: 100.24, close: 100.31 }),
    ];
    const expansionBars = [
      createCryptoBar(ts(0), { open: 100.02, high: 100.05, low: 100.0, close: 100.02, volume: 1000 }),
      createCryptoBar(ts(1), { open: 100.02, high: 100.12, low: 100.01, close: 100.08, volume: 1000 }),
      createCryptoBar(ts(2), { open: 100.08, high: 100.18, low: 100.02, close: 100.12, volume: 1000 }),
      createCryptoBar(ts(3), { open: 100.12, high: 100.24, low: 100.06, close: 100.16, volume: 1000 }),
      createCryptoBar(ts(4), { open: 100.16, high: 100.36, low: 100.1, close: 100.22, volume: 1000 }),
      createCryptoBar(ts(5), { open: 100.22, high: 100.44, low: 100.16, close: 100.18, volume: 1000 }),
      createCryptoBar(ts(6), { open: 100.18, high: 100.42, low: 100.06, close: 100.12, volume: 1000 }),
      createCryptoBar(ts(7), { open: 100.12, high: 100.52, low: 100.08, close: 100.48, volume: 1000 }),
    ];

    const midRangeResult = ctx.engine.__internal.enrichBarsWithSignals(midRangeBars, strategy);
    const expansionResult = ctx.engine.__internal.enrichBarsWithSignals(expansionBars, strategy);

    assert.ok(midRangeResult.at(-1).indicators.regimeBlockers.includes("mid_range"));
    assert.equal(midRangeResult.at(-1).indicators.tradeable, false);
    assert.ok(expansionResult.at(-1).indicators.regimeBlockers.includes("expansion"));
    assert.equal(expansionResult.at(-1).indicators.tradeable, false);
  } finally {
    ctx.cleanup();
  }
});

test("event shock lockout blocks the trigger bar plus the next six bars", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion");
    const start = Date.parse("2026-04-01T13:00:00.000Z");
    const ts = (index) => new Date(start + (index * 5 * 60 * 1000)).toISOString();
    const bars = Array.from({ length: 20 }, (_, index) => createCryptoBar(ts(index), {
      open: 100 + (index * 0.01),
      high: 100.08 + (index * 0.01),
      low: 99.98 + (index * 0.01),
      close: 100.04 + (index * 0.01),
      volume: 1000,
    }));
    bars.push(createCryptoBar(ts(20), { open: 100.2, high: 102.5, low: 99.4, close: 100.05, volume: 5000 }));
    bars.push(createCryptoBar(ts(21), { open: 100.05, high: 100.42, low: 99.92, close: 100.08, volume: 5000 }));
    bars.push(createCryptoBar(ts(22), { open: 100.08, high: 100.16, low: 100.02, close: 100.1, volume: 1000 }));
    bars.push(createCryptoBar(ts(23), { open: 100.1, high: 100.18, low: 100.04, close: 100.12, volume: 1000 }));
    bars.push(createCryptoBar(ts(24), { open: 100.12, high: 100.2, low: 100.06, close: 100.13, volume: 1000 }));
    bars.push(createCryptoBar(ts(25), { open: 100.13, high: 100.21, low: 100.07, close: 100.15, volume: 1000 }));
    bars.push(createCryptoBar(ts(26), { open: 100.15, high: 100.23, low: 100.09, close: 100.17, volume: 1000 }));
    bars.push(createCryptoBar(ts(27), { open: 100.17, high: 100.25, low: 100.11, close: 100.19, volume: 1000 }));
    bars.push(createCryptoBar(ts(28), { open: 100.19, high: 100.27, low: 100.13, close: 100.21, volume: 1000 }));

    const enriched = ctx.engine.__internal.enrichBarsWithSignals(bars, strategy);

    for (let index = 21; index <= 27; index += 1) {
      assert.ok(enriched[index].indicators.regimeBlockers.includes("event_shock_lockout"));
    }
    assert.equal(enriched[20].indicators.regimeBlockers.includes("event_shock_lockout"), false);
    assert.equal(enriched[28].indicators.regimeBlockers.includes("event_shock_lockout"), false);
  } finally {
    ctx.cleanup();
  }
});

test("computeSessionOpeningRangeContexts tracks completion and resets across Denver Core sessions", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const bars = [
      createCryptoBar("2026-04-01T13:00:00.000Z", { high: 100.1, low: 99.9, close: 100 }),
      createCryptoBar("2026-04-01T13:05:00.000Z", { high: 100.2, low: 99.95, close: 100.1 }),
      createCryptoBar("2026-04-01T13:10:00.000Z", { high: 100.18, low: 99.98, close: 100.08 }),
      createCryptoBar("2026-04-01T13:15:00.000Z", { high: 100.25, low: 100.04, close: 100.2 }),
      createCryptoBar("2026-04-02T13:00:00.000Z", { high: 101.1, low: 100.7, close: 100.9 }),
      createCryptoBar("2026-04-02T13:05:00.000Z", { high: 101.2, low: 100.8, close: 101 }),
    ];
    const contexts = ctx.engine.__internal.computeSessionOpeningRangeContexts(
      bars,
      3,
      (timestamp) => ctx.engine.__internal.classifyScheduledWindow(timestamp).active
        ? `${String(timestamp).slice(0, 10)}::denver_core`
        : null,
    );

    assert.equal(contexts[0].openingRangeComplete, false);
    assert.equal(contexts[2].openingRangeComplete, true);
    assert.equal(contexts[3].openingRangeHigh, 100.2);
    assert.equal(contexts[3].openingRangeLow, 99.9);
    assert.equal(contexts[4].openingRangeComplete, false);
    assert.equal(contexts[4].barsSinceSessionStart, 0);
    assert.equal(contexts[5].openingRangeHigh, 101.2);
  } finally {
    ctx.cleanup();
  }
});

test("bottom reclaim can trigger without a true failed-breakdown reclaim", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const bars = buildBottomReclaimWithoutBreakdownBars();
    const bottomStrategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-bottom-reclaim");
    const failedBreakdownStrategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-failed-breakdown-reclaim");

    const bottomResult = ctx.engine.__internal.enrichBarsWithSignals(bars, bottomStrategy);
    const failedBreakdownResult = ctx.engine.__internal.enrichBarsWithSignals(bars, failedBreakdownStrategy);

    assert.ok(bottomResult[22].signals.crypto_bottom_reclaim > 0.7);
    assert.equal(failedBreakdownResult[22].signals.crypto_failed_breakdown_reclaim, 0);
    assert.equal(failedBreakdownResult[22].indicators.reclaimCloseConfirmed, false);
    assert.equal(failedBreakdownResult[22].indicators.reclaimHoldConfirmed, false);
  } finally {
    ctx.cleanup();
  }
});

test("opening range breakout waits for the range to complete and then triggers distinct close and retest variants", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const closeStrategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-close");
    const retestStrategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-opening-range-breakout-retest");
    const closeResult = ctx.engine.__internal.enrichBarsWithSignals(buildOpeningRangeBreakoutBars("breakout_close"), closeStrategy);
    const retestResult = ctx.engine.__internal.enrichBarsWithSignals(buildOpeningRangeBreakoutBars("breakout_retest"), retestStrategy);

    assert.equal(closeResult[1].signals.crypto_opening_range_breakout, 0);
    assert.equal(closeResult[1].indicators.openingRangeComplete, false);
    assert.ok(closeResult[19].signals.crypto_opening_range_breakout > 0.9);
    assert.equal(closeResult[19].indicators.openingRangeVariant, "breakout_close");
    assert.ok(retestResult[20].signals.crypto_opening_range_breakout > 0.75);
    assert.equal(retestResult[20].indicators.openingRangeVariant, "breakout_retest");
    assert.equal(retestResult[20].indicators.openingRangeComplete, true);
  } finally {
    ctx.cleanup();
  }
});

test("blocked watchlist items never raise notify-now alerts", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategy = createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", {
      status: "paper_candidate",
    });
    ctx.engine.__internal.saveStrategies([strategy]);
    const now = "2026-04-01T13:35:00.000Z";
    const marketDataLoader = async () => ({
      source: "crypto_blocked_watchlist_fixture",
      symbol: "BTCUSDT",
      trusted: true,
      market: "crypto",
      exchange: "fixture",
      marketType: "spot",
      sessionMode: "scheduled_windows",
      alertWindows: ctx.engine.__internal.DEFAULT_CRYPTO_DAY_TRADING_CONFIG.alertWindows,
      marketSnapshot: TIGHT_LIQUIDITY_SNAPSHOT,
      priceSeries: [
        createCryptoBar(now, {
          close: 100,
          signals: {
            crypto_range_mean_reversion: 0.92,
          },
          indicators: {
            regimeState: "range_blocked_mid_range",
            tradeable: false,
            regimeBlockers: ["mid_range"],
          },
        }),
      ],
    });

    const watchlist = await ctx.engine.buildMorningWatchlist({
      bars: 60,
      limit: 1,
      now,
      marketDataLoader,
    });

    assert.equal(watchlist.items[0].liveStatus, "blocked_mid_range");
    assert.equal(watchlist.items[0].notifyNow, false);
    assert.deepEqual(watchlist.items[0].regimeBlockers, ["mid_range"]);
  } finally {
    ctx.cleanup();
  }
});

test("pilot summary uses a 30-trade review checkpoint and a 50-trade advance gate", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const eligible30 = Array.from({ length: 30 }, (_, index) => buildPilotEntry(index));
    const summary30 = ctx.engine.__internal.buildProfitabilityPilotSummary([
      ...eligible30,
      buildPilotEntry(999, {
        entryId: "disqualified_1",
        pilotEligible: false,
        pilotDisqualificationReasons: ["ticket_not_found"],
      }),
    ], {
      ticketStore: ctx.engine.__internal.readProfitabilityTicketStore(),
      now: "2026-04-02T13:30:00.000Z",
    });
    const summary50 = ctx.engine.__internal.buildProfitabilityPilotSummary(
      Array.from({ length: 50 }, (_, index) => buildPilotEntry(index)),
      {
        ticketStore: ctx.engine.__internal.readProfitabilityTicketStore(),
        now: "2026-04-02T13:30:00.000Z",
      },
    );

    assert.equal(summary30.phase, "review_checkpoint");
    assert.equal(summary30.milestones[0].status, "reached");
    assert.equal(summary30.milestones[1].status, "pending");
    assert.equal(summary30.journalStats.eligibleTradeCount, 30);
    assert.equal(summary30.journalStats.disqualifiedTradeCount, 1);
    assert.equal(summary30.disqualificationReasons[0].reason, "ticket_not_found");

    assert.equal(summary50.phase, "advance_ready");
    assert.equal(summary50.milestones[1].status, "ready");
    assert.ok(summary50.nextUnlock.includes("ETH"));
    assert.equal(summary50.progress.targetTrades, 50);
  } finally {
    ctx.cleanup();
  }
});

test("router defaults day trading snapshots to crypto and keeps equities legacy reachable", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const cryptoSnapshot = ctx.router.getDayTradingSnapshot();
    const equitiesSnapshot = ctx.router.getDayTradingSnapshot({ market: "equities_legacy" });

    assert.equal(cryptoSnapshot.market, "crypto");
    assert.equal(cryptoSnapshot.strategies.length, 8);
    assert.equal(equitiesSnapshot.market, "equities_legacy");
    assert.equal(equitiesSnapshot.strategies.length, 4);
  } finally {
    ctx.cleanup();
  }
});
