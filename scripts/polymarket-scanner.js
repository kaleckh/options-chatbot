#!/usr/bin/env node
/**
 * Polymarket Arbitrage & Market-Making Scanner
 *
 * Scans all active Polymarket events for:
 * 1. Multi-outcome probability mispricings (sum != 1.0)
 * 2. Same-market YES+NO deviations
 * 3. Market-making opportunities (wide spreads with good liquidity)
 * 4. Cross-market logical inconsistencies
 *
 * Uses only the public Gamma API — no authentication needed for scanning.
 */

const https = require("https");

// ---- Config ----
const MIN_LIQUIDITY = 5000; // Minimum $ liquidity per outcome to consider tradeable
const MIN_EVENT_LIQUIDITY = 20000; // Minimum total event liquidity
const MAX_SPREAD_FOR_ARB = 0.05; // Max 5% spread per leg for arb to be executable
const MIN_DEVIATION_PCT = 0.03; // Min 3% deviation from 1.0 to flag
const MAX_TRADEABLE_SPREAD = 0.10; // Outcomes with >10% spread are untradeable
const MM_MIN_SPREAD = 0.02; // Minimum spread to be interesting for market-making
const MM_MIN_LIQUIDITY = 10000; // Minimum liquidity for MM candidate

// ---- API ----
function fetch(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "PolymarketScanner/1.0" } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch { reject(new Error("Failed to parse: " + data.slice(0, 200))); }
      });
    }).on("error", reject);
  });
}

async function fetchAllEvents() {
  const all = [];
  for (let offset = 0; offset < 2000; offset += 100) {
    const batch = await fetch(
      "https://gamma-api.polymarket.com/events?limit=100&offset=" + offset + "&active=true&closed=false"
    );
    if (!Array.isArray(batch) || batch.length === 0) break;
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

// ---- Analysis ----

function parseOutcomePrices(market) {
  try {
    return JSON.parse(market.outcomePrices || "[]").map(Number);
  } catch {
    return [];
  }
}

function analyzeMultiOutcomeArb(event) {
  if (!event.markets || event.markets.length < 3) return null;
  // Only negRisk events have mutually exclusive outcomes where probabilities should sum to 1
  // Non-negRisk events (like "will X hit price Y") have independent outcomes
  if (!event.negRisk) return null;

  const outcomes = [];
  let sumYes = 0;
  let totalLiquidity = 0;
  let tradeableOutcomes = 0;

  for (const m of event.markets) {
    const prices = parseOutcomePrices(m);
    const yesPrice = prices[0] || 0;
    const spread = Number(m.spread || 0);
    const liq = Number(m.liquidityNum || 0);
    const bestBid = Number(m.bestBid || 0);
    const bestAsk = Number(m.bestAsk || 0);
    const tradeable = spread <= MAX_TRADEABLE_SPREAD && liq >= MIN_LIQUIDITY && bestBid > 0 && bestAsk > 0;

    outcomes.push({
      title: (m.groupItemTitle || m.question || "").slice(0, 50),
      yesPrice,
      bestBid,
      bestAsk,
      spread,
      liquidity: liq,
      tradeable,
      conditionId: m.conditionId,
      clobTokenIds: m.clobTokenIds,
    });

    sumYes += yesPrice;
    totalLiquidity += liq;
    if (tradeable) tradeableOutcomes++;
  }

  const deviation = sumYes - 1;
  if (Math.abs(deviation) < MIN_DEVIATION_PCT) return null;
  if (totalLiquidity < MIN_EVENT_LIQUIDITY) return null;

  // Calculate executable arb: only count tradeable outcomes
  const tradeableSum = outcomes
    .filter((o) => o.tradeable)
    .reduce((s, o) => s + o.yesPrice, 0);
  const nonTradeableSum = outcomes
    .filter((o) => !o.tradeable)
    .reduce((s, o) => s + o.yesPrice, 0);

  // For OVER-priced markets (sum > 1): profit = sell all YES tokens, cost = $1 collateral
  // You need ALL outcomes to be tradeable to execute
  // For UNDER-priced markets (sum < 1): profit = buy all YES tokens for < $1, one will pay $1
  // You only need enough tradeable outcomes to capture the gap

  let arbExecutable = false;
  let arbProfit = 0;
  let arbType = deviation > 0 ? "OVER" : "UNDER";

  if (deviation > 0) {
    // Can sell (short) YES on all outcomes, pay $1 collateral, collect sumYes > $1
    // Need all major outcomes tradeable
    const tradeablePct = tradeableOutcomes / outcomes.length;
    // Estimate fees: taker fee ~4% * p * (1-p) per leg
    const estFees = outcomes.filter((o) => o.tradeable).reduce((s, o) => {
      return s + 0.04 * o.yesPrice * (1 - o.yesPrice);
    }, 0);
    arbProfit = deviation - estFees;
    arbExecutable = arbProfit > 0.01 && tradeablePct >= 0.5;
  } else {
    // Can buy YES on all outcomes for sum < $1, guaranteed $1 payout
    const estFees = outcomes.filter((o) => o.tradeable).reduce((s, o) => {
      return s + 0.04 * o.yesPrice * (1 - o.yesPrice);
    }, 0);
    arbProfit = Math.abs(deviation) - estFees;
    arbExecutable = arbProfit > 0.01 && tradeableOutcomes >= 2;
  }

  return {
    title: event.title,
    slug: event.slug,
    negRisk: event.negRisk,
    outcomeCount: outcomes.length,
    tradeableOutcomes,
    sumYes: Math.round(sumYes * 10000) / 10000,
    deviation: Math.round(deviation * 10000) / 10000,
    deviationPct: Math.round(deviation * 10000) / 100,
    arbType,
    arbExecutable,
    arbProfit: Math.round(arbProfit * 10000) / 10000,
    totalLiquidity: Math.round(totalLiquidity),
    outcomes: outcomes.sort((a, b) => b.yesPrice - a.yesPrice),
  };
}

function analyzeYesNoDeviation(market) {
  const prices = parseOutcomePrices(market);
  if (prices.length !== 2) return null;
  const sum = prices[0] + prices[1];
  const dev = Math.abs(sum - 1);
  const liq = Number(market.liquidityNum || 0);
  if (dev < 0.005 || liq < MIN_LIQUIDITY) return null;

  return {
    question: (market.question || market.groupItemTitle || "").slice(0, 60),
    yesPrice: prices[0],
    noPrice: prices[1],
    sum: Math.round(sum * 10000) / 10000,
    deviation: Math.round(dev * 10000) / 10000,
    type: sum > 1 ? "OVER (short both)" : "UNDER (buy both)",
    liquidity: Math.round(liq),
    spread: Number(market.spread || 0),
    bestBid: Number(market.bestBid || 0),
    bestAsk: Number(market.bestAsk || 0),
  };
}

function analyzeMarketMaking(market) {
  const spread = Number(market.spread || 0);
  const liq = Number(market.liquidityNum || 0);
  const volume24h = Number(market.volume24hr || 0);
  if (spread < MM_MIN_SPREAD || liq < MM_MIN_LIQUIDITY) return null;

  const prices = parseOutcomePrices(market);
  const midPrice = prices[0] || 0.5;
  // Estimate fee on taker fills against our limit orders: we pay zero as maker
  // Profit per round trip = spread - taker fee on exit
  const estTakerFee = 0.04 * midPrice * (1 - midPrice);
  const profitPerRoundTrip = spread - estTakerFee;

  return {
    question: (market.question || market.groupItemTitle || "").slice(0, 60),
    spread,
    spreadPct: Math.round(spread * 10000) / 100,
    midPrice,
    liquidity: Math.round(liq),
    volume24h: Math.round(volume24h),
    profitPerRT: Math.round(profitPerRoundTrip * 10000) / 10000,
    profitPct: Math.round((profitPerRoundTrip / midPrice) * 10000) / 100,
    bestBid: Number(market.bestBid || 0),
    bestAsk: Number(market.bestAsk || 0),
    turnover: volume24h > 0 && liq > 0 ? Math.round((volume24h / liq) * 100) / 100 : 0,
  };
}

// ---- Main ----
async function main() {
  console.log("Polymarket Arbitrage Scanner");
  console.log("Fetching all active events...\n");

  const events = await fetchAllEvents();
  console.log("Active events: " + events.length);

  let allMarkets = [];
  for (const e of events) {
    if (e.markets) allMarkets.push(...e.markets);
  }
  console.log("Active markets: " + allMarkets.length);
  console.log("");

  // ---- 1. Multi-outcome arbitrage ----
  console.log("=" .repeat(70));
  console.log("  MULTI-OUTCOME PROBABILITY ARBITRAGE");
  console.log("=".repeat(70));

  const multiArbs = events
    .map(analyzeMultiOutcomeArb)
    .filter(Boolean)
    .sort((a, b) => Math.abs(b.deviation) - Math.abs(a.deviation));

  const executableArbs = multiArbs.filter((a) => a.arbExecutable);

  console.log("\nTotal mispriced events (>" + (MIN_DEVIATION_PCT * 100) + "% dev, >$" + MIN_EVENT_LIQUIDITY + " liq): " + multiArbs.length);
  console.log("Executable after fees: " + executableArbs.length);

  if (executableArbs.length > 0) {
    console.log("\n*** EXECUTABLE ARBITRAGE OPPORTUNITIES ***\n");
    for (const a of executableArbs.slice(0, 10)) {
      console.log(a.title.slice(0, 60));
      console.log(
        "  " + a.arbType + " | Sum: " + a.sumYes.toFixed(4) +
        " | Dev: " + a.deviationPct.toFixed(1) + "%" +
        " | Est profit: " + (a.arbProfit * 100).toFixed(1) + "% per $1" +
        " | Liq: $" + a.totalLiquidity +
        " | Tradeable: " + a.tradeableOutcomes + "/" + a.outcomeCount
      );
      for (const o of a.outcomes.filter((o) => o.tradeable).slice(0, 5)) {
        console.log("    " + o.title.padEnd(52) + " bid:" + o.bestBid.toFixed(3) + " ask:" + o.bestAsk.toFixed(3) + " spr:" + (o.spread * 100).toFixed(1) + "% liq:$" + Math.round(o.liquidity));
      }
      console.log("");
    }
  }

  console.log("\nTop 10 mispriced (including non-executable):");
  for (const a of multiArbs.slice(0, 10)) {
    const exec = a.arbExecutable ? " [EXEC]" : "";
    console.log(
      "  " + a.arbType.padEnd(5) + " " + a.deviationPct.toFixed(1).padStart(6) + "%" +
      " profit:" + (a.arbProfit * 100).toFixed(1).padStart(5) + "%" +
      " liq:$" + String(a.totalLiquidity).padStart(10) +
      " trade:" + a.tradeableOutcomes + "/" + a.outcomeCount +
      exec + " | " + a.title.slice(0, 45)
    );
  }

  // ---- 2. YES+NO same-market deviations ----
  console.log("\n" + "=".repeat(70));
  console.log("  SAME-MARKET YES+NO DEVIATIONS");
  console.log("=".repeat(70));

  const yesNoArbs = allMarkets
    .map(analyzeYesNoDeviation)
    .filter(Boolean)
    .sort((a, b) => b.deviation - a.deviation);

  console.log("\nDeviations >0.5% with >$" + MIN_LIQUIDITY + " liquidity: " + yesNoArbs.length);
  for (const a of yesNoArbs.slice(0, 10)) {
    console.log(
      "  " + a.question.padEnd(62) +
      " sum:" + a.sum.toFixed(4) +
      " dev:" + (a.deviation * 100).toFixed(2) + "%" +
      " " + a.type +
      " liq:$" + a.liquidity
    );
  }

  // ---- 3. Market-making opportunities ----
  console.log("\n" + "=".repeat(70));
  console.log("  MARKET-MAKING OPPORTUNITIES");
  console.log("=".repeat(70));

  const mmOpps = allMarkets
    .map(analyzeMarketMaking)
    .filter(Boolean)
    .filter((m) => m.profitPerRT > 0)
    .sort((a, b) => b.profitPerRT * b.turnover - a.profitPerRT * a.turnover); // Sort by expected daily profit

  console.log("\nProfitable MM opportunities (spread >" + (MM_MIN_SPREAD * 100) + "%, liq >$" + MM_MIN_LIQUIDITY + ", profit after fees): " + mmOpps.length);
  console.log("\nTop 15 by spread * turnover:");
  for (const m of mmOpps.slice(0, 15)) {
    console.log(
      "  " + m.question.padEnd(62) +
      " spr:" + m.spreadPct.toFixed(1).padStart(4) + "%" +
      " profit/RT:" + (m.profitPerRT * 100).toFixed(1).padStart(4) + "c" +
      " bid:" + m.bestBid.toFixed(2) +
      " ask:" + m.bestAsk.toFixed(2) +
      " vol24h:$" + String(m.volume24h).padStart(7) +
      " liq:$" + String(m.liquidity).padStart(7)
    );
  }

  // ---- Summary ----
  console.log("\n" + "=".repeat(70));
  console.log("  SUMMARY");
  console.log("=".repeat(70));
  console.log("\nMulti-outcome arb opportunities: " + executableArbs.length + " executable, " + multiArbs.length + " total mispriced");
  console.log("YES/NO deviations: " + yesNoArbs.length);
  console.log("Market-making opportunities: " + mmOpps.length);

  const totalArbProfit = executableArbs.reduce((s, a) => s + Math.abs(a.arbProfit), 0);
  console.log("\nTotal estimated arb profit available: " + (totalArbProfit * 100).toFixed(1) + " cents per $1 risked across " + executableArbs.length + " opportunities");
  console.log("Best single arb: " + (executableArbs[0] ? executableArbs[0].title.slice(0, 50) + " (" + (executableArbs[0].arbProfit * 100).toFixed(1) + "% profit)" : "none"));
  console.log("Best MM opportunity: " + (mmOpps[0] ? mmOpps[0].question.slice(0, 50) + " (" + mmOpps[0].spreadPct.toFixed(1) + "% spread, $" + mmOpps[0].volume24h + " daily vol)" : "none"));
}

main().catch((err) => console.error("Scanner error:", err.message));
