const fs = require("fs");
const path = require("path");

process.env.DAY_TRADING_CRYPTO_DATA_ROOT = path.resolve("data/day-trading/crypto");
delete require.cache[require.resolve("../src/lib/day-trading/crypto-engine.js")];
delete require.cache[require.resolve("../src/lib/day-trading/engine.js")];
const engine = require("../src/lib/day-trading/crypto-engine.js");

// ---- Step 1: Load and resample data ----
console.log("Loading data...");
const raw1m = engine.__internal.loadNormalizedBars("BTCUSDT");
const bars15m = engine.__internal.resampleBars(raw1m, 15);
console.log("15m bars:", bars15m.length);

// ---- Step 2: Enrich bars with all indicators ----
// Use a dummy strategy just to get indicators computed
console.log("Enriching bars with indicators...");
const strategies = engine.__internal.loadStrategies();
// Pick one strategy to get base indicators, we'll read from indicators object
const baseStrategy = strategies.find((s) => s.simulation?.entrySignal === "crypto_delta_breakout" && s.strategyId.startsWith("btcusdt"));
const enriched = engine.__internal.enrichBarsWithSignals(bars15m, baseStrategy, undefined, "all_hours");
console.log("Enriched bars:", enriched.length);

// ---- Step 3: Compute forward returns ----
const FORWARD_BARS = [4, 8, 16]; // 1h, 2h, 4h lookahead on 15m bars
const MIN_WARMUP = 100; // Skip first 100 bars for indicator warmup

// Build dataset: each row = { indicators, forwardReturns }
console.log("Building dataset...");
const dataset = [];
for (let i = MIN_WARMUP; i < enriched.length - Math.max(...FORWARD_BARS); i++) {
  const bar = enriched[i];
  const ind = bar.indicators || {};
  const close = Number(bar.close);
  if (!close || close <= 0) continue;

  const forwardReturns = {};
  for (const fb of FORWARD_BARS) {
    const futureClose = Number(enriched[i + fb].close);
    forwardReturns[`fwd_${fb}`] = (futureClose - close) / close;
  }

  // Extract numeric indicators
  const features = {};
  for (const [key, val] of Object.entries(ind)) {
    if (typeof val === "number" && Number.isFinite(val)) {
      features[key] = val;
    }
  }

  // Add derived features
  const prevClose = i > 0 ? Number(enriched[i - 1].close) : close;
  features.ret_1 = (close - prevClose) / prevClose;
  if (i >= 4) features.ret_4 = (close - Number(enriched[i - 4].close)) / Number(enriched[i - 4].close);
  if (i >= 8) features.ret_8 = (close - Number(enriched[i - 8].close)) / Number(enriched[i - 8].close);
  if (i >= 16) features.ret_16 = (close - Number(enriched[i - 16].close)) / Number(enriched[i - 16].close);

  // Volatility features
  if (i >= 20) {
    let sumSqRet = 0;
    for (let j = i - 19; j <= i; j++) {
      const r = (Number(enriched[j].close) - Number(enriched[j - 1].close)) / Number(enriched[j - 1].close);
      sumSqRet += r * r;
    }
    features.realized_vol_20 = Math.sqrt(sumSqRet / 20);
  }

  dataset.push({ features, forwardReturns, timestamp: bar.timestamp, close });
}
console.log("Dataset rows:", dataset.length);

// ---- Step 4: Factor Analysis ----
// For each feature, compute rank correlation with forward returns
// Split into quintiles, compute average forward return per quintile

const featureNames = Object.keys(dataset[0].features);
console.log("Features to analyze:", featureNames.length);
console.log("");

function analyzeFactorPredictiveness(data, featureName, targetName) {
  // Filter rows where feature is available
  const valid = data.filter((d) => Number.isFinite(d.features[featureName]) && Number.isFinite(d.forwardReturns[targetName]));
  if (valid.length < 100) return null;

  // Sort by feature value and split into quintiles
  const sorted = [...valid].sort((a, b) => a.features[featureName] - b.features[featureName]);
  const quintileSize = Math.floor(sorted.length / 5);
  const quintiles = [];
  for (let q = 0; q < 5; q++) {
    const start = q * quintileSize;
    const end = q === 4 ? sorted.length : (q + 1) * quintileSize;
    const slice = sorted.slice(start, end);
    const avgReturn = slice.reduce((s, d) => s + d.forwardReturns[targetName], 0) / slice.length;
    const avgFeature = slice.reduce((s, d) => s + d.features[featureName], 0) / slice.length;
    quintiles.push({ q: q + 1, count: slice.length, avgReturn, avgFeature });
  }

  // Monotonicity score: how consistently does return increase/decrease across quintiles
  let increasing = 0;
  let decreasing = 0;
  for (let q = 1; q < quintiles.length; q++) {
    if (quintiles[q].avgReturn > quintiles[q - 1].avgReturn) increasing++;
    if (quintiles[q].avgReturn < quintiles[q - 1].avgReturn) decreasing++;
  }
  const monotonicity = Math.max(increasing, decreasing) / 4; // 0 to 1

  // Spread: difference between top and bottom quintile average returns
  const spread = quintiles[4].avgReturn - quintiles[0].avgReturn;

  // Information coefficient: rank correlation between feature and forward return
  const n = valid.length;
  const featureRanks = rankArray(valid.map((d) => d.features[featureName]));
  const returnRanks = rankArray(valid.map((d) => d.forwardReturns[targetName]));
  let sumD2 = 0;
  for (let j = 0; j < n; j++) sumD2 += (featureRanks[j] - returnRanks[j]) ** 2;
  const ic = 1 - (6 * sumD2) / (n * (n * n - 1)); // Spearman rank correlation

  return { featureName, targetName, quintiles, monotonicity, spread, ic, sampleSize: valid.length };
}

function rankArray(arr) {
  const indexed = arr.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
  const ranks = new Array(arr.length);
  for (let j = 0; j < indexed.length; j++) ranks[indexed[j].i] = j + 1;
  return ranks;
}

// ---- Step 5: Split into train/test (9 months train, 3 months test) ----
const splitIdx = Math.floor(dataset.length * 0.75);
const trainData = dataset.slice(0, splitIdx);
const testData = dataset.slice(splitIdx);
console.log("Train:", trainData.length, "rows | Test:", testData.length, "rows");
console.log("Train period:", trainData[0].timestamp, "to", trainData[trainData.length - 1].timestamp);
console.log("Test period:", testData[0].timestamp, "to", testData[testData.length - 1].timestamp);
console.log("");

// Analyze all factors on TRAINING data only
const targetReturn = "fwd_8"; // 2-hour forward return on 15m bars
console.log("Analyzing " + featureNames.length + " factors for " + targetReturn + " prediction...");
const factorResults = [];
for (const feat of featureNames) {
  const result = analyzeFactorPredictiveness(trainData, feat, targetReturn);
  if (result) factorResults.push(result);
}

// Sort by absolute IC
factorResults.sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic));

console.log("\n=== TOP 20 PREDICTIVE FACTORS (by |IC|, trained on first 9 months) ===");
for (const f of factorResults.slice(0, 20)) {
  const dir = f.ic > 0 ? "+" : "-";
  const q1ret = (f.quintiles[0].avgReturn * 100).toFixed(3);
  const q5ret = (f.quintiles[4].avgReturn * 100).toFixed(3);
  console.log(
    dir + " " + f.featureName.padEnd(28) +
    " IC:" + f.ic.toFixed(4) +
    " | Mono:" + f.monotonicity.toFixed(2) +
    " | Q1:" + q1ret + "% Q5:" + q5ret + "%" +
    " | Spread:" + (f.spread * 100).toFixed(3) + "%"
  );
}

// ---- Step 6: Build composite signal from top factors ----
// Select factors with |IC| > threshold and good monotonicity
const IC_THRESHOLD = 0.02;
const MONO_THRESHOLD = 0.5;
const selectedFactors = factorResults.filter(
  (f) => Math.abs(f.ic) >= IC_THRESHOLD && f.monotonicity >= MONO_THRESHOLD
);
console.log("\nSelected factors (|IC|>=" + IC_THRESHOLD + ", mono>=" + MONO_THRESHOLD + "):", selectedFactors.length);
for (const f of selectedFactors) {
  console.log("  " + f.featureName + " IC:" + f.ic.toFixed(4));
}

if (selectedFactors.length === 0) {
  console.log("\nNo factors met selection criteria. Lowering thresholds...");
  const relaxed = factorResults.filter((f) => Math.abs(f.ic) >= 0.01);
  console.log("Factors with |IC| >= 0.01:", relaxed.length);
  for (const f of relaxed.slice(0, 10)) {
    console.log("  " + f.featureName + " IC:" + f.ic.toFixed(4) + " Mono:" + f.monotonicity.toFixed(2));
  }
}

// Build z-score composite: for each row, z-score each selected factor,
// multiply by sign of IC, and average
function computeCompositeScore(row, factors, trainStats) {
  let score = 0;
  let count = 0;
  for (const f of factors) {
    const val = row.features[f.featureName];
    if (!Number.isFinite(val)) continue;
    const stats = trainStats[f.featureName];
    if (!stats || stats.std === 0) continue;
    const z = (val - stats.mean) / stats.std;
    score += z * Math.sign(f.ic);
    count++;
  }
  return count > 0 ? score / count : 0;
}

// Compute training stats for normalization
const trainStats = {};
for (const f of selectedFactors.length > 0 ? selectedFactors : factorResults.slice(0, 10)) {
  const values = trainData.map((d) => d.features[f.featureName]).filter(Number.isFinite);
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
  trainStats[f.featureName] = { mean, std: Math.sqrt(variance) };
}

const activeFactors = selectedFactors.length > 0 ? selectedFactors : factorResults.slice(0, 10);

// ---- Step 7: Backtest composite signal on TEST data ----
console.log("\n=== BACKTESTING COMPOSITE SIGNAL ON OUT-OF-SAMPLE DATA ===\n");

function backtestComposite(data, factors, stats, config) {
  const { entryThresholdLong, entryThresholdShort, tpFraction, slFraction, holdBars, feesFraction } = config;

  const trades = [];
  let lastExitIdx = -Infinity;
  const cooldown = Math.max(1, Math.ceil(holdBars * 0.5));

  for (let i = 0; i < data.length - holdBars - 1; i++) {
    if (i - lastExitIdx <= cooldown) continue;

    const score = computeCompositeScore(data[i], factors, stats);
    let direction = null;
    if (score >= entryThresholdLong) direction = "long";
    if (score <= entryThresholdShort) direction = "short";
    if (!direction) continue;

    const entryPrice = data[i].close;
    const isShort = direction === "short";
    const tpPrice = isShort ? entryPrice * (1 - tpFraction) : entryPrice * (1 + tpFraction);
    const slPrice = isShort ? entryPrice * (1 + slFraction) : entryPrice * (1 - slFraction);

    // Look ahead for exit
    let exitPrice = null;
    let exitReason = "time_exit";
    let exitIdx = i;

    for (let j = i + 1; j <= Math.min(i + holdBars, data.length - 1); j++) {
      const futureHigh = Number(enriched[MIN_WARMUP + splitIdx + j]?.high || data[j].close);
      const futureLow = Number(enriched[MIN_WARMUP + splitIdx + j]?.low || data[j].close);
      const futureClose = data[j].close;

      if (isShort) {
        if (futureHigh >= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (futureLow <= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      } else {
        if (futureLow <= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (futureHigh >= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      }
      exitPrice = futureClose;
      exitIdx = j;
    }

    if (!exitPrice) exitPrice = data[Math.min(i + holdBars, data.length - 1)].close;

    const grossReturn = isShort
      ? (entryPrice - exitPrice) / entryPrice
      : (exitPrice - entryPrice) / entryPrice;
    const netReturn = grossReturn - feesFraction * 2;

    lastExitIdx = exitIdx;
    trades.push({ direction, netReturn, exitReason, score, entryTime: data[i].timestamp });
  }

  const wins = trades.filter((t) => t.netReturn > 0);
  const losses = trades.filter((t) => t.netReturn <= 0);
  const totalReturn = trades.reduce((s, t) => s + t.netReturn, 0);
  const grossProfit = wins.reduce((s, t) => s + t.netReturn, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.netReturn, 0));

  return {
    trades: trades.length,
    winRate: trades.length > 0 ? wins.length / trades.length : 0,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 999 : 0,
    totalReturn,
    byExit: {
      take_profit: trades.filter((t) => t.exitReason === "take_profit").length,
      stop_loss: trades.filter((t) => t.exitReason === "stop_loss").length,
      time_exit: trades.filter((t) => t.exitReason === "time_exit").length,
    },
    longs: trades.filter((t) => t.direction === "long").length,
    shorts: trades.filter((t) => t.direction === "short").length,
    longWins: trades.filter((t) => t.direction === "long" && t.netReturn > 0).length,
    shortWins: trades.filter((t) => t.direction === "short" && t.netReturn > 0).length,
  };
}

// Parameter sweep on test data
const sweepResults = [];
for (const longThr of [0.3, 0.5, 0.8, 1.0, 1.5]) {
  for (const shortThr of [-0.3, -0.5, -0.8, -1.0, -1.5]) {
    for (const tp of [0.005, 0.008, 0.012, 0.02]) {
      for (const sl of [0.005, 0.008, 0.012]) {
        if (tp / sl < 1.2) continue;
        for (const hold of [4, 8, 16]) {
          const r = backtestComposite(testData, activeFactors, trainStats, {
            entryThresholdLong: longThr,
            entryThresholdShort: shortThr,
            tpFraction: tp,
            slFraction: sl,
            holdBars: hold,
            feesFraction: 0.0002,
          });
          if (r.trades >= 10) {
            sweepResults.push({ longThr, shortThr, tp, sl, hold, ...r });
          }
        }
      }
    }
  }
}

sweepResults.sort((a, b) => b.totalReturn - a.totalReturn);

console.log("Parameter combos with 10+ trades:", sweepResults.length);
console.log("\n=== TOP 15 OUT-OF-SAMPLE RESULTS ===");
for (const r of sweepResults.slice(0, 15)) {
  const icon = r.totalReturn > 0 ? "***" : "   ";
  console.log(
    icon + " Lthr=" + r.longThr.toFixed(1) + " Sthr=" + r.shortThr.toFixed(1) +
    " TP=" + (r.tp * 100).toFixed(1) + "% SL=" + (r.sl * 100).toFixed(1) +
    "% hold=" + r.hold
  );
  console.log(
    "     " + r.trades + "t | WR:" + (r.winRate * 100).toFixed(0) +
    "% | PF:" + r.profitFactor.toFixed(2) +
    " | Ret:" + (r.totalReturn * 100).toFixed(2) +
    "% | TP:" + r.byExit.take_profit + " SL:" + r.byExit.stop_loss + " T:" + r.byExit.time_exit +
    " | L:" + r.longs + "/" + r.longWins + "w S:" + r.shorts + "/" + r.shortWins + "w"
  );
}

// Summary stats
const profitable = sweepResults.filter((r) => r.totalReturn > 0 && r.winRate >= 0.4 && r.profitFactor > 1.2);
console.log("\nRobust profitable (>0% ret, >40% WR, PF>1.2): " + profitable.length + " / " + sweepResults.length);

// Also show: does the composite score actually predict?
console.log("\n=== COMPOSITE SCORE vs ACTUAL FORWARD RETURN (test data) ===");
const testScores = testData.map((d) => ({
  score: computeCompositeScore(d, activeFactors, trainStats),
  fwdReturn: d.forwardReturns[targetReturn],
})).filter((d) => Number.isFinite(d.score) && Number.isFinite(d.fwdReturn));

// Quintile analysis of composite score on test data
testScores.sort((a, b) => a.score - b.score);
const qSize = Math.floor(testScores.length / 5);
console.log("Score quintile analysis (out-of-sample):");
for (let q = 0; q < 5; q++) {
  const start = q * qSize;
  const end = q === 4 ? testScores.length : (q + 1) * qSize;
  const slice = testScores.slice(start, end);
  const avgScore = slice.reduce((s, d) => s + d.score, 0) / slice.length;
  const avgRet = slice.reduce((s, d) => s + d.fwdReturn, 0) / slice.length;
  const wr = slice.filter((d) => d.fwdReturn > 0).length / slice.length;
  console.log(
    "  Q" + (q + 1) + ": avgScore=" + avgScore.toFixed(3) +
    " avgRet=" + (avgRet * 100).toFixed(3) + "%" +
    " WR:" + (wr * 100).toFixed(0) + "%" +
    " (" + slice.length + " bars)"
  );
}
