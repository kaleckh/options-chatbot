const DEFAULT_STRATEGY = {
  version: 1,
  strategyId: "spy-opening-range-breakout",
  name: "SPY Opening Range Breakout",
  hypothesisSummary: "Deterministic opening range breakout fixture.",
  venueType: "equities",
  status: "draft",
  marketUniverse: {
    symbols: ["SPY"],
    category: "s-and-p-index-etf",
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
  entryRules: ["Enter on the next open after the breakout signal."],
  exitRules: ["Exit on take-profit, stop-loss, or time-exit."],
  cooldownRules: ["Wait for cooldown bars after each exit."],
  sizing: {
    model: "fixed_fractional",
    maxPositionFraction: 0.12,
    riskPerTradeFraction: 0.006,
  },
  riskLimits: {
    maxDrawdownFraction: 0.08,
    maxDailyLossFraction: 0.02,
    maxOpenPositions: 1,
    maxLossPerTradeFraction: 0.006,
    minLiquidityUsd: 1000000,
    maxSpreadFraction: 0.002,
  },
  evaluationWindow: {
    timeframe: "5m",
    warmupBars: 6,
    minimumTrades: 4,
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
    owner: "day-trading-test",
    tags: ["deterministic", "fixture"],
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function mergeDeep(base, overrides) {
  if (!isPlainObject(base) || !isPlainObject(overrides)) {
    return clone(overrides);
  }

  const merged = clone(base);
  for (const [key, value] of Object.entries(overrides)) {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergeDeep(merged[key], value);
    } else {
      merged[key] = clone(value);
    }
  }
  return merged;
}

function round(value, digits = 6) {
  return Number(value.toFixed(digits));
}

function createStrategy(overrides = {}) {
  return mergeDeep(DEFAULT_STRATEGY, overrides);
}

function createBar(timestamp, symbol, open, high, low, close, signals = {}) {
  return {
    timestamp,
    symbol,
    open: round(open),
    high: round(high),
    low: round(low),
    close: round(close),
    volume: 1000000,
    signals,
  };
}

function buildSignalSeries(options = {}) {
  const symbol = options.symbol || "SPY";
  const signalName = options.signalName || "opening_range_breakout";
  const intervalMinutes = Number(options.intervalMinutes) || 5;
  const warmupBars = Number(options.warmupBars) || 6;
  const cooldownBars = Number(options.cooldownBars) || 4;
  const maxHoldBars = Number(options.maxHoldBars) || 10;
  const takeProfitFraction = Number(options.takeProfitFraction) || 0.008;
  const stopLossFraction = Number(options.stopLossFraction) || 0.004;
  const signalStrength = Number(options.signalStrength) || 0.88;
  const startPrice = Number(options.startPrice) || 100;
  const outcomes = Array.isArray(options.outcomes) && options.outcomes.length > 0
    ? options.outcomes
    : ["win", "win", "loss", "win"];
  const appendLiveSignal = options.appendLiveSignal === true;
  const baseTime = new Date(options.startTimestamp || "2026-03-03T14:30:00.000Z").getTime();

  const bars = [];
  let currentPrice = startPrice;
  let index = 0;

  const nextTimestamp = () => new Date(baseTime + (index++ * intervalMinutes * 60 * 1000)).toISOString();

  const pushNeutralBars = (count, driftFraction = 0.0004) => {
    for (let i = 0; i < count; i += 1) {
      const open = currentPrice;
      const close = open * (1 + driftFraction);
      bars.push(createBar(
        nextTimestamp(),
        symbol,
        open,
        close * 1.0008,
        open * 0.9992,
        close,
      ));
      currentPrice = close;
    }
  };

  pushNeutralBars(warmupBars + 2);

  for (const outcome of outcomes) {
    const signalOpen = currentPrice;
    const signalClose = signalOpen * 1.0005;
    bars.push(createBar(
      nextTimestamp(),
      symbol,
      signalOpen,
      signalClose * 1.001,
      signalOpen * 0.9995,
      signalClose,
      { [signalName]: signalStrength },
    ));

    const entryOpen = signalClose * 1.0005;
    if (outcome === "win") {
      const close = entryOpen * (1 + (takeProfitFraction * 0.55));
      bars.push(createBar(
        nextTimestamp(),
        symbol,
        entryOpen,
        entryOpen * (1 + takeProfitFraction + 0.001),
        entryOpen * 0.9992,
        close,
      ));
      currentPrice = close;
    } else if (outcome === "loss") {
      const close = entryOpen * (1 - (stopLossFraction * 0.6));
      bars.push(createBar(
        nextTimestamp(),
        symbol,
        entryOpen,
        entryOpen * 1.0008,
        entryOpen * (1 - stopLossFraction - 0.001),
        close,
      ));
      currentPrice = close;
    } else {
      let holdOpen = entryOpen;
      for (let i = 0; i < maxHoldBars; i += 1) {
        const drift = i === maxHoldBars - 1 ? 0.0005 : 0.0002;
        const close = holdOpen * (1 + drift);
        bars.push(createBar(
          nextTimestamp(),
          symbol,
          holdOpen,
          holdOpen * (1 + Math.max(0.0005, takeProfitFraction * 0.45)),
          holdOpen * (1 - Math.max(0.0005, stopLossFraction * 0.45)),
          close,
        ));
        holdOpen = close;
      }
      currentPrice = holdOpen;
    }

    pushNeutralBars(cooldownBars + 2);
  }

  if (appendLiveSignal) {
    const liveOpen = currentPrice;
    const liveClose = liveOpen * 1.0004;
    bars.push(createBar(
      nextTimestamp(),
      symbol,
      liveOpen,
      liveClose * 1.0008,
      liveOpen * 0.9995,
      liveClose,
      { [signalName]: signalStrength },
    ));
  }

  return bars;
}

function createMarketDataFixture(options = {}) {
  const priceSeries = clone(options.priceSeries || []);
  const lastBar = priceSeries[priceSeries.length - 1];
  return {
    source: options.source || "fixture_series",
    symbol: options.symbol || lastBar?.symbol || "SPY",
    warning: options.warning || null,
    marketSnapshot: options.marketSnapshot || {
      bestBid: lastBar?.close ? round(lastBar.close * 0.9998) : 100,
      bestAsk: lastBar?.close ? round(lastBar.close * 1.0002) : 100.04,
      volume: lastBar?.volume || 1000000,
      volumeUsd: lastBar?.close ? round(lastBar.volume * lastBar.close) : 100000000,
      availableLiquidityUsd: lastBar?.close ? round(lastBar.volume * lastBar.close * 0.08) : 8000000,
    },
    priceSeries,
  };
}

function createMarketDataLoader(fixturesByStrategyId) {
  return async (strategy) => {
    const fixture = fixturesByStrategyId[strategy.strategyId];
    if (!fixture) {
      throw new Error(`Missing market data fixture for ${strategy.strategyId}`);
    }
    return clone(fixture);
  };
}

module.exports = {
  createStrategy,
  buildSignalSeries,
  createMarketDataFixture,
  createMarketDataLoader,
};
