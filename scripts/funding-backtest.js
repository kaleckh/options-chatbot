const fs = require("fs");
const path = require("path");

// Load funding rates and spot data
const fundingData = JSON.parse(fs.readFileSync(path.resolve("data/day-trading/crypto/funding_rates_btc.json")));
const rates = fundingData.rates;
console.log("Funding rates:", rates.length, "| Range:", rates[0].timestamp, "to", rates[rates.length - 1].timestamp);

// Load 15m and 1h spot data
process.env.DAY_TRADING_CRYPTO_DATA_ROOT = path.resolve("data/day-trading/crypto");
delete require.cache[require.resolve("../src/lib/day-trading/crypto-engine.js")];
delete require.cache[require.resolve("../src/lib/day-trading/engine.js")];
const engine = require("../src/lib/day-trading/crypto-engine.js");
const raw1m = engine.__internal.loadNormalizedBars("BTCUSDT");
const bars15m = engine.__internal.resampleBars(raw1m, 15);
const bars1h = engine.__internal.resampleBars(raw1m, 60);

// Filter to overlap period
const fundingStart = new Date(rates[0].timestamp).getTime();
const fundingEnd = new Date(rates[rates.length - 1].timestamp).getTime();
const spot15m = bars15m.filter((b) => {
  const t = new Date(b.timestamp).getTime();
  return t >= fundingStart && t <= fundingEnd;
});
const spot1h = bars1h.filter((b) => {
  const t = new Date(b.timestamp).getTime();
  return t >= fundingStart && t <= fundingEnd;
});
console.log("Overlap 15m bars:", spot15m.length, "| 1h bars:", spot1h.length);

// Distribution
const rateValues = rates.map((r) => r.rate).sort((a, b) => a - b);
const p10 = rateValues[Math.floor(rateValues.length * 0.1)];
const p90 = rateValues[Math.floor(rateValues.length * 0.9)];
console.log("\nFunding: P10=" + (p10 * 100).toFixed(4) + "% P90=" + (p90 * 100).toFixed(4) + "%\n");

function backtestFundingStrategy(spotBars, config) {
  const { entryThresholdNeg, entryThresholdPos, holdBars, tpFraction, slFraction, feesFraction } = config;

  // Build rolling 24h (3-period) average funding rate per bar (optimized)
  const rateTimes = rates.map((r) => new Date(r.timestamp).getTime());
  const rollingFunding = new Array(spotBars.length);
  let rIdx = 0;
  for (let bi = 0; bi < spotBars.length; bi++) {
    const barTime = new Date(spotBars[bi].timestamp).getTime();
    while (rIdx < rateTimes.length - 1 && rateTimes[rIdx + 1] <= barTime) rIdx++;
    if (rIdx < 2) { rollingFunding[bi] = null; continue; }
    rollingFunding[bi] = (rates[rIdx].rate + rates[rIdx - 1].rate + rates[rIdx - 2].rate) / 3;
  }

  const trades = [];
  let equity = 1;
  let peakEquity = 1;
  let maxDD = 0;
  let lastExitIdx = -Infinity;
  const cooldown = Math.max(1, Math.ceil(holdBars * 0.5));

  for (let i = 50; i < spotBars.length - holdBars - 1; i++) {
    if (i - lastExitIdx <= cooldown) continue;
    const currentFunding = rollingFunding[i];
    if (currentFunding == null) continue;

    let direction = null;
    if (currentFunding <= entryThresholdNeg) direction = "long";
    if (currentFunding >= entryThresholdPos) direction = "short";
    if (!direction) continue;

    const entryPrice = Number(spotBars[i + 1].open);
    if (!entryPrice || entryPrice <= 0) continue;
    const isShort = direction === "short";
    const tpPrice = isShort ? entryPrice * (1 - tpFraction) : entryPrice * (1 + tpFraction);
    const slPrice = isShort ? entryPrice * (1 + slFraction) : entryPrice * (1 - slFraction);

    let exitPrice = null;
    let exitReason = "time_exit";
    let exitIdx = i + 1;

    for (let j = i + 1; j <= Math.min(i + holdBars, spotBars.length - 1); j++) {
      const bar = spotBars[j];
      if (isShort) {
        if (Number(bar.high) >= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (Number(bar.low) <= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      } else {
        if (Number(bar.low) <= slPrice) { exitPrice = slPrice; exitReason = "stop_loss"; exitIdx = j; break; }
        if (Number(bar.high) >= tpPrice) { exitPrice = tpPrice; exitReason = "take_profit"; exitIdx = j; break; }
      }
      exitPrice = Number(bar.close);
      exitIdx = j;
    }

    if (!exitPrice) exitPrice = Number(spotBars[Math.min(i + holdBars, spotBars.length - 1)].close);

    const grossReturn = isShort
      ? (entryPrice - exitPrice) / entryPrice
      : (exitPrice - entryPrice) / entryPrice;
    const netReturn = grossReturn - feesFraction * 2;

    equity *= 1 + netReturn * 0.1;
    peakEquity = Math.max(peakEquity, equity);
    maxDD = Math.max(maxDD, (peakEquity - equity) / peakEquity);
    lastExitIdx = exitIdx;

    trades.push({ direction, exitReason, netReturn, fundingRate: currentFunding });
  }

  const wins = trades.filter((t) => t.netReturn > 0);
  const losses = trades.filter((t) => t.netReturn <= 0);
  const totalReturn = trades.reduce((s, t) => s + t.netReturn, 0);
  const grossProfit = wins.reduce((s, t) => s + t.netReturn, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.netReturn, 0));

  return {
    trades: trades.length,
    winRate: trades.length > 0 ? wins.length / trades.length : 0,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0,
    totalReturn,
    equityReturn: equity - 1,
    maxDD,
    byExit: {
      take_profit: trades.filter((t) => t.exitReason === "take_profit").length,
      stop_loss: trades.filter((t) => t.exitReason === "stop_loss").length,
      time_exit: trades.filter((t) => t.exitReason === "time_exit").length,
    },
    byDirection: {
      long: { count: trades.filter((t) => t.direction === "long").length, wins: trades.filter((t) => t.direction === "long" && t.netReturn > 0).length },
      short: { count: trades.filter((t) => t.direction === "short").length, wins: trades.filter((t) => t.direction === "short" && t.netReturn > 0).length },
    },
  };
}

// Parameter sweep
const configs = [];
for (const tf of ["15m", "1h"]) {
  const bars = tf === "15m" ? spot15m : spot1h;
  // Funding rates are tiny decimals: 0.00005 = 0.005%. Only trade EXTREME funding.
  // P10=-0.000036, P90=0.000080. We want beyond P5/P95 = truly crowded.
  for (const negThr of [-0.00007, -0.00005, -0.00004, -0.00003]) {
    for (const posThr of [0.00005, 0.00007, 0.00008, 0.00009]) {
      for (const hold of tf === "15m" ? [4, 8, 16, 32, 48] : [2, 4, 8, 12, 24]) {
        for (const tp of [0.005, 0.008, 0.012, 0.02, 0.03]) {
          for (const sl of [0.005, 0.008, 0.012]) {
            if (tp / sl < 1.2) continue;
            configs.push({ tf, bars, entryThresholdNeg: negThr, entryThresholdPos: posThr, holdBars: hold, tpFraction: tp, slFraction: sl, feesFraction: 0.0002 });
          }
        }
      }
    }
  }
}

console.log("Running " + configs.length + " parameter combos...");
const results = [];
for (const c of configs) {
  const r = backtestFundingStrategy(c.bars, c);
  if (r.trades >= 5) {
    results.push({ tf: c.tf, negThr: c.entryThresholdNeg, posThr: c.entryThresholdPos, hold: c.holdBars, tp: c.tpFraction, sl: c.slFraction, ...r });
  }
}

results.sort((a, b) => b.totalReturn - a.totalReturn);
console.log("\n=== TOP 20 RESULTS ===");
for (const r of results.slice(0, 20)) {
  const icon = r.totalReturn > 0 ? "***" : "   ";
  console.log(icon + " [" + r.tf + "] neg=" + (r.negThr * 100).toFixed(2) + "% pos=" + (r.posThr * 100).toFixed(2) + "% TP=" + (r.tp * 100).toFixed(1) + "% SL=" + (r.sl * 100).toFixed(1) + "% hold=" + r.hold);
  console.log("     " + r.trades + "t | WR:" + (r.winRate * 100).toFixed(0) + "% | PF:" + r.profitFactor.toFixed(2) + " | Ret:" + (r.totalReturn * 100).toFixed(2) + "% | DD:" + (r.maxDD * 100).toFixed(2) + "% | TP:" + r.byExit.take_profit + " SL:" + r.byExit.stop_loss + " T:" + r.byExit.time_exit);
  console.log("     L:" + r.byDirection.long.count + "t/" + r.byDirection.long.wins + "w S:" + r.byDirection.short.count + "t/" + r.byDirection.short.wins + "w");
}

const profitable = results.filter((r) => r.totalReturn > 0 && r.winRate >= 0.4 && r.profitFactor > 1.2);
console.log("\nProfitable combos (>0% ret, >40% WR, PF>1.2): " + profitable.length + " / " + results.length + " with 5+ trades");

if (profitable.length > 0) {
  console.log("\n=== ALL ROBUST PROFITABLE VARIANTS ===");
  for (const r of profitable) {
    console.log("[" + r.tf + "] neg=" + (r.negThr * 100).toFixed(2) + "% pos=" + (r.posThr * 100).toFixed(2) + "% TP=" + (r.tp * 100).toFixed(1) + "% SL=" + (r.sl * 100).toFixed(1) + "% hold=" + r.hold + " -> " + r.trades + "t WR:" + (r.winRate * 100).toFixed(0) + "% PF:" + r.profitFactor.toFixed(2) + " Ret:" + (r.totalReturn * 100).toFixed(2) + "%");
  }
}
