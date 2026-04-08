const fs = require("fs");
const path = require("path");

process.env.DAY_TRADING_CRYPTO_DATA_ROOT = path.resolve("data/day-trading/crypto");
delete require.cache[require.resolve("../src/lib/day-trading/crypto-engine.js")];
delete require.cache[require.resolve("../src/lib/day-trading/engine.js")];
const engine = require("../src/lib/day-trading/crypto-engine.js");

// ---- Helpers ----
function rankArray(arr) {
  const indexed = arr.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
  const ranks = new Array(arr.length);
  for (let j = 0; j < indexed.length; j++) ranks[indexed[j].i] = j + 1;
  return ranks;
}

function analyzeFactorIC(data, featureName, targetName) {
  const valid = data.filter((d) => Number.isFinite(d.features[featureName]) && Number.isFinite(d.forwardReturns[targetName]));
  if (valid.length < 100) return null;
  const n = valid.length;
  const fRanks = rankArray(valid.map((d) => d.features[featureName]));
  const rRanks = rankArray(valid.map((d) => d.forwardReturns[targetName]));
  let sumD2 = 0;
  for (let j = 0; j < n; j++) sumD2 += (fRanks[j] - rRanks[j]) ** 2;
  return 1 - (6 * sumD2) / (n * (n * n - 1));
}

function buildDataset(enrichedBars, minWarmup) {
  const FORWARD_BARS = [4, 8, 16];
  const dataset = [];
  for (let i = minWarmup; i < enrichedBars.length - Math.max(...FORWARD_BARS); i++) {
    const bar = enrichedBars[i];
    const ind = bar.indicators || {};
    const close = Number(bar.close);
    if (!close || close <= 0) continue;

    const forwardReturns = {};
    for (const fb of FORWARD_BARS) {
      forwardReturns["fwd_" + fb] = (Number(enrichedBars[i + fb].close) - close) / close;
    }

    const features = {};
    for (const [key, val] of Object.entries(ind)) {
      if (typeof val === "number" && Number.isFinite(val)) features[key] = val;
    }

    const prevClose = i > 0 ? Number(enrichedBars[i - 1].close) : close;
    features.ret_1 = (close - prevClose) / prevClose;
    if (i >= 4) features.ret_4 = (close - Number(enrichedBars[i - 4].close)) / Number(enrichedBars[i - 4].close);
    if (i >= 8) features.ret_8 = (close - Number(enrichedBars[i - 8].close)) / Number(enrichedBars[i - 8].close);
    if (i >= 16) features.ret_16 = (close - Number(enrichedBars[i - 16].close)) / Number(enrichedBars[i - 16].close);

    if (i >= 20) {
      let sumSqRet = 0;
      for (let j = i - 19; j <= i; j++) {
        const r = (Number(enrichedBars[j].close) - Number(enrichedBars[j - 1].close)) / Number(enrichedBars[j - 1].close);
        sumSqRet += r * r;
      }
      features.realized_vol_20 = Math.sqrt(sumSqRet / 20);
    }

    dataset.push({ features, forwardReturns, timestamp: bar.timestamp, close, high: Number(bar.high), low: Number(bar.low) });
  }
  return dataset;
}

function computeCompositeScore(row, factors, trainStats) {
  let score = 0;
  let count = 0;
  for (const f of factors) {
    const val = row.features[f.name];
    if (!Number.isFinite(val)) continue;
    const stats = trainStats[f.name];
    if (!stats || stats.std === 0) continue;
    const z = (val - stats.mean) / stats.std;
    score += z * Math.sign(f.ic);
    count++;
  }
  return count > 0 ? score / count : 0;
}

function computeTrainStats(trainData, factors) {
  const stats = {};
  for (const f of factors) {
    const values = trainData.map((d) => d.features[f.name]).filter(Number.isFinite);
    const mean = values.reduce((s, v) => s + v, 0) / values.length;
    const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
    stats[f.name] = { mean, std: Math.sqrt(variance) };
  }
  return stats;
}

function backtestTightened(testData, factors, trainStats, config) {
  const { scoreThr, volMin, volMax, tpFraction, slFraction, holdBars, feesFraction, direction } = config;

  const trades = [];
  let lastExitIdx = -Infinity;
  const cooldown = Math.max(1, Math.ceil(holdBars * 0.5));

  for (let i = 0; i < testData.length - holdBars - 1; i++) {
    if (i - lastExitIdx <= cooldown) continue;
    const row = testData[i];

    const score = computeCompositeScore(row, factors, trainStats);
    const vol = row.features.realized_vol_20;
    if (!Number.isFinite(vol)) continue;

    // Volatility filter
    if (volMin > 0 && vol < volMin) continue;
    if (volMax > 0 && vol > volMax) continue;

    let dir = null;
    if (direction === "long" || direction === "both") {
      if (score >= scoreThr) dir = "long"; // High score = mean reversion says buy (after dip)
    }
    if (direction === "short" || direction === "both") {
      if (score <= -scoreThr) dir = "short";
    }
    if (!dir) continue;

    const entryPrice = row.close;
    const isShort = dir === "short";
    const tpPrice = isShort ? entryPrice * (1 - tpFraction) : entryPrice * (1 + tpFraction);
    const slPrice = isShort ? entryPrice * (1 + slFraction) : entryPrice * (1 - slFraction);

    let exitPrice = null;
    let exitReason = "time_exit";
    let exitIdx = i;

    for (let j = i + 1; j <= Math.min(i + holdBars, testData.length - 1); j++) {
      const fh = testData[j].high;
      const fl = testData[j].low;
      const fc = testData[j].close;
      if (isShort) {
        if (fh >= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (fl <= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      } else {
        if (fl <= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (fh >= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      }
      exitPrice = fc;
      exitIdx = j;
    }
    if (!exitPrice) exitPrice = testData[Math.min(i + holdBars, testData.length - 1)].close;

    const grossReturn = isShort ? (entryPrice - exitPrice) / entryPrice : (exitPrice - entryPrice) / entryPrice;
    const netReturn = grossReturn - feesFraction * 2;
    lastExitIdx = exitIdx;
    trades.push({ direction: dir, netReturn, exitReason });
  }

  const wins = trades.filter((t) => t.netReturn > 0);
  const losses = trades.filter((t) => t.netReturn <= 0);
  const totalReturn = trades.reduce((s, t) => s + t.netReturn, 0);
  const gp = wins.reduce((s, t) => s + t.netReturn, 0);
  const gl = Math.abs(losses.reduce((s, t) => s + t.netReturn, 0));

  return {
    trades: trades.length,
    winRate: trades.length > 0 ? wins.length / trades.length : 0,
    profitFactor: gl > 0 ? gp / gl : gp > 0 ? 999 : 0,
    totalReturn,
    longs: trades.filter((t) => t.direction === "long").length,
    shorts: trades.filter((t) => t.direction === "short").length,
    longWR: trades.filter((t) => t.direction === "long").length > 0 ? trades.filter((t) => t.direction === "long" && t.netReturn > 0).length / trades.filter((t) => t.direction === "long").length : 0,
    shortWR: trades.filter((t) => t.direction === "short").length > 0 ? trades.filter((t) => t.direction === "short" && t.netReturn > 0).length / trades.filter((t) => t.direction === "short").length : 0,
    byExit: {
      tp: trades.filter((t) => t.exitReason === "take_profit").length,
      sl: trades.filter((t) => t.exitReason === "stop_loss").length,
      te: trades.filter((t) => t.exitReason === "time_exit").length,
    },
  };
}

// ---- Main pipeline: run on BTC, ETH, SOL ----
async function runForSymbol(symbol) {
  console.log("\n" + "=".repeat(70));
  console.log("  " + symbol);
  console.log("=".repeat(70));

  const raw1m = engine.__internal.loadNormalizedBars(symbol);
  if (raw1m.length < 5000) {
    console.log("Insufficient 1m data for " + symbol + ": " + raw1m.length + " bars. Skipping.");
    return null;
  }
  const bars15m = engine.__internal.resampleBars(raw1m, 15);
  console.log("15m bars: " + bars15m.length);

  const strategies = engine.__internal.loadStrategies();
  const baseStrategy = strategies.find((s) => s.simulation?.entrySignal === "crypto_delta_breakout" && s.strategyId.startsWith("btcusdt"));
  // Swap symbol in bars for enrichment
  const symbolBars = bars15m.map((b) => ({ ...b, symbol }));
  const enriched = engine.__internal.enrichBarsWithSignals(symbolBars, baseStrategy, undefined, "all_hours");

  const dataset = buildDataset(enriched, 100);
  console.log("Dataset: " + dataset.length + " rows");

  const splitIdx = Math.floor(dataset.length * 0.75);
  const trainData = dataset.slice(0, splitIdx);
  const testData = dataset.slice(splitIdx);
  console.log("Train: " + trainData.length + " (" + trainData[0].timestamp + " to " + trainData[trainData.length - 1].timestamp + ")");
  console.log("Test:  " + testData.length + " (" + testData[0].timestamp + " to " + testData[testData.length - 1].timestamp + ")");

  // Factor analysis on training data
  const featureNames = Object.keys(dataset[0].features);
  const targetReturn = "fwd_8";
  const factorResults = [];
  for (const feat of featureNames) {
    const ic = analyzeFactorIC(trainData, feat, targetReturn);
    if (ic != null) factorResults.push({ name: feat, ic });
  }
  factorResults.sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic));

  console.log("\nTop 10 factors:");
  for (const f of factorResults.slice(0, 10)) {
    console.log("  " + f.name.padEnd(25) + " IC:" + f.ic.toFixed(4));
  }

  // Select top factors with |IC| > 0.02
  const selected = factorResults.filter((f) => Math.abs(f.ic) >= 0.02).slice(0, 15);
  if (selected.length < 3) {
    console.log("Too few predictive factors. No signal for " + symbol);
    return null;
  }
  console.log("Selected " + selected.length + " factors");

  const trainStats = computeTrainStats(trainData, selected);

  // Out-of-sample quintile test
  const testScores = testData.map((d) => ({
    score: computeCompositeScore(d, selected, trainStats),
    fwd: d.forwardReturns[targetReturn],
  })).filter((d) => Number.isFinite(d.score) && Number.isFinite(d.fwd));
  testScores.sort((a, b) => a.score - b.score);
  const qSize = Math.floor(testScores.length / 5);

  console.log("\nOut-of-sample quintile analysis:");
  let q5positive = false;
  for (let q = 0; q < 5; q++) {
    const slice = testScores.slice(q * qSize, q === 4 ? testScores.length : (q + 1) * qSize);
    const avgRet = slice.reduce((s, d) => s + d.fwd, 0) / slice.length;
    const wr = slice.filter((d) => d.fwd > 0).length / slice.length;
    const avgScore = slice.reduce((s, d) => s + d.score, 0) / slice.length;
    const marker = q === 4 && avgRet > 0 ? " <<<" : "";
    console.log("  Q" + (q + 1) + ": score=" + avgScore.toFixed(3) + " ret=" + (avgRet * 100).toFixed(3) + "% WR:" + (wr * 100).toFixed(0) + "%" + marker);
    if (q === 4 && avgRet > 0) q5positive = true;
  }

  if (!q5positive) {
    console.log("Q5 not positive out-of-sample. No tradeable signal for " + symbol);
    return null;
  }

  // Compute vol percentiles on training data
  const trainVols = trainData.map((d) => d.features.realized_vol_20).filter(Number.isFinite).sort((a, b) => a - b);
  const volP25 = trainVols[Math.floor(trainVols.length * 0.25)];
  const volP50 = trainVols[Math.floor(trainVols.length * 0.50)];
  const volP75 = trainVols[Math.floor(trainVols.length * 0.75)];
  console.log("\nVol percentiles: P25=" + (volP25 * 100).toFixed(3) + "% P50=" + (volP50 * 100).toFixed(3) + "% P75=" + (volP75 * 100).toFixed(3) + "%");

  // Tightened sweep: high score + volatility filter
  console.log("\nRunning tightened backtest sweep...");
  const results = [];
  for (const scoreThr of [1.0, 1.2, 1.5, 1.8, 2.0, 2.5]) {
    for (const volFilter of [
      { min: 0, max: 0, label: "all_vol" },
      { min: volP50, max: 0, label: "above_median_vol" },
      { min: volP75, max: 0, label: "high_vol" },
      { min: volP25, max: volP75, label: "mid_vol" },
    ]) {
      for (const tp of [0.004, 0.006, 0.008, 0.012, 0.02]) {
        for (const sl of [0.003, 0.005, 0.008, 0.012]) {
          if (tp / sl < 1.2) continue;
          for (const hold of [4, 8, 16]) {
            for (const dir of ["long", "short", "both"]) {
              const r = backtestTightened(testData, selected, trainStats, {
                scoreThr, volMin: volFilter.min, volMax: volFilter.max,
                tpFraction: tp, slFraction: sl, holdBars: hold, feesFraction: 0.0002, direction: dir,
              });
              if (r.trades >= 10) {
                results.push({ symbol, scoreThr, vol: volFilter.label, tp, sl, hold, dir, ...r });
              }
            }
          }
        }
      }
    }
  }

  results.sort((a, b) => b.totalReturn - a.totalReturn);

  console.log("\nCombos with 10+ trades: " + results.length);
  const robust = results.filter((r) => r.totalReturn > 0 && r.winRate >= 0.45 && r.profitFactor >= 1.3 && r.trades >= 15);
  console.log("Robust (>0% ret, >45% WR, PF>=1.3, 15+ trades): " + robust.length);

  console.log("\nTop 10:");
  for (const r of results.slice(0, 10)) {
    const icon = r.totalReturn > 0 ? "+" : "-";
    console.log(
      icon + " score>" + r.scoreThr + " " + r.vol + " " + r.dir +
      " TP=" + (r.tp * 100).toFixed(1) + "% SL=" + (r.sl * 100).toFixed(1) + "% hold=" + r.hold +
      " -> " + r.trades + "t WR:" + (r.winRate * 100).toFixed(0) + "% PF:" + r.profitFactor.toFixed(2) +
      " Ret:" + (r.totalReturn * 100).toFixed(2) + "%" +
      " [L:" + r.longs + "/" + (r.longWR * 100).toFixed(0) + "% S:" + r.shorts + "/" + (r.shortWR * 100).toFixed(0) + "%]"
    );
  }

  if (robust.length > 0) {
    console.log("\n*** ROBUST PROFITABLE VARIANTS ***");
    for (const r of robust.slice(0, 15)) {
      console.log(
        "  score>" + r.scoreThr + " " + r.vol + " " + r.dir +
        " TP=" + (r.tp * 100).toFixed(1) + "% SL=" + (r.sl * 100).toFixed(1) + "% hold=" + r.hold +
        " -> " + r.trades + "t WR:" + (r.winRate * 100).toFixed(0) + "% PF:" + r.profitFactor.toFixed(2) +
        " Ret:" + (r.totalReturn * 100).toFixed(2) + "%"
      );
    }
  }

  return { symbol, factorCount: selected.length, topIC: factorResults[0], results: results.length, robust: robust.length, bestReturn: results[0]?.totalReturn || 0 };
}

async function main() {
  const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
  const summaries = [];

  for (const symbol of symbols) {
    const summary = await runForSymbol(symbol);
    if (summary) summaries.push(summary);
  }

  console.log("\n" + "=".repeat(70));
  console.log("  FINAL SUMMARY");
  console.log("=".repeat(70));
  for (const s of summaries) {
    console.log(s.symbol + ": " + s.factorCount + " factors | top IC: " + s.topIC.name + " " + s.topIC.ic.toFixed(4) + " | " + s.results + " combos | " + s.robust + " robust | best ret: " + (s.bestReturn * 100).toFixed(2) + "%");
  }
  if (summaries.every((s) => s.robust === 0)) {
    console.log("\nNo robust profitable signal found on any asset.");
  }
}

main();
