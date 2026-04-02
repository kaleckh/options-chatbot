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

test("runDayTradingValidation uses trusted crypto fixtures and updates the crypto snapshot", async () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const strategies = [
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-range-mean-reversion", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "btcusdt-crypto-trend-continuation", { status: "paper_candidate" }),
      createCryptoFixtureStrategy(ctx.engine, "ethusdt-crypto-trend-continuation", { status: "paper_candidate" }),
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
    assert.equal(report.strategiesScanned, 3);
    assert.equal(report.results[0].marketDataSource, "crypto_fixture");
    assert.equal(report.results[0].trustedMarketData, true);
    assert.equal(report.profitabilityProfileId, "crypto_profitability_v1");

    const snapshot = ctx.engine.getDayTradingSnapshot();
    assert.equal(snapshot.market, "crypto");
    assert.equal(snapshot.lastReport.generatedAt, report.generatedAt);
    assert.equal(snapshot.scoreboard.totals.strategies, 4);
    assert.equal(snapshot.operatingPlan.activeSetupId, "btcusdt-crypto-range-mean-reversion");
    assert.equal(snapshot.pilotSummary.progress.targetTrades, 30);
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
    assert.equal(report.phaseA.controlResults.length, 3);
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

test("router defaults day trading snapshots to crypto and keeps equities legacy reachable", () => {
  const ctx = loadCryptoEngineWithTempDataRoot();
  try {
    const cryptoSnapshot = ctx.router.getDayTradingSnapshot();
    const equitiesSnapshot = ctx.router.getDayTradingSnapshot({ market: "equities_legacy" });

    assert.equal(cryptoSnapshot.market, "crypto");
    assert.equal(cryptoSnapshot.strategies.length, 4);
    assert.equal(equitiesSnapshot.market, "equities_legacy");
    assert.equal(equitiesSnapshot.strategies.length, 4);
  } finally {
    ctx.cleanup();
  }
});
