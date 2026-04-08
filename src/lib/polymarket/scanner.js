/**
 * Polymarket Market Scanner
 *
 * Scans for arbitrage opportunities and market-making candidates.
 * Returns structured opportunity objects for the engines to act on.
 */

const { fetchAllEvents, httpGet, GAMMA_HOST } = require("./client");

const DEFAULT_CONFIG = {
  minLiquidity: 5000,
  minEventLiquidity: 20000,
  maxTradeableSpread: 0.10,
  minDeviationPct: 0.03,
  mmMinSpread: 0.02,
  mmMinLiquidity: 10000,
  mmMinVolume24h: 5000,
};

function parseOutcomePrices(market) {
  try { return JSON.parse(market.outcomePrices || "[]").map(Number); }
  catch { return []; }
}

function parseClobTokenIds(market) {
  try { return JSON.parse(market.clobTokenIds || "[]"); }
  catch { return []; }
}

function analyzeMultiOutcomeArb(event, config) {
  if (!event.markets || event.markets.length < 3 || !event.negRisk) return null;

  const outcomes = [];
  let sumYes = 0;
  let totalLiquidity = 0;
  let tradeableCount = 0;

  for (const m of event.markets) {
    const prices = parseOutcomePrices(m);
    const tokenIds = parseClobTokenIds(m);
    const yesPrice = prices[0] || 0;
    const spread = Number(m.spread || 0);
    const liq = Number(m.liquidityNum || 0);
    const bestBid = Number(m.bestBid || 0);
    const bestAsk = Number(m.bestAsk || 0);
    const tradeable = spread <= config.maxTradeableSpread && liq >= config.minLiquidity && bestBid > 0 && bestAsk > 0;

    outcomes.push({
      title: (m.groupItemTitle || m.question || "").slice(0, 60),
      conditionId: m.conditionId,
      yesTokenId: tokenIds[0] || null,
      noTokenId: tokenIds[1] || null,
      yesPrice,
      bestBid,
      bestAsk,
      spread,
      liquidity: liq,
      tradeable,
      tickSize: m.orderPriceMinTickSize || "0.01",
    });

    sumYes += yesPrice;
    totalLiquidity += liq;
    if (tradeable) tradeableCount++;
  }

  const deviation = sumYes - 1;
  if (Math.abs(deviation) < config.minDeviationPct) return null;
  if (totalLiquidity < config.minEventLiquidity) return null;

  const arbType = deviation > 0 ? "OVER" : "UNDER";

  // Estimate fees (taker ~4% * p * (1-p) per leg)
  const estFees = outcomes
    .filter((o) => o.tradeable)
    .reduce((s, o) => s + 0.04 * o.yesPrice * (1 - o.yesPrice), 0);
  const arbProfit = Math.abs(deviation) - estFees;

  const executable = arbProfit > 0.01 && (
    arbType === "OVER" ? tradeableCount / outcomes.length >= 0.5 : tradeableCount >= 2
  );

  return {
    type: "multi_outcome_arb",
    title: event.title,
    slug: event.slug,
    arbType,
    outcomeCount: outcomes.length,
    tradeableOutcomes: tradeableCount,
    sumYes: Math.round(sumYes * 10000) / 10000,
    deviation: Math.round(deviation * 10000) / 10000,
    deviationPct: Math.round(Math.abs(deviation) * 10000) / 100,
    arbProfit: Math.round(arbProfit * 10000) / 10000,
    estFees: Math.round(estFees * 10000) / 10000,
    executable,
    totalLiquidity: Math.round(totalLiquidity),
    outcomes,
  };
}

function analyzeMarketMaking(market, config) {
  const spread = Number(market.spread || 0);
  const liq = Number(market.liquidityNum || 0);
  const vol24h = Number(market.volume24hr || 0);
  if (spread < config.mmMinSpread || liq < config.mmMinLiquidity) return null;
  if (vol24h < config.mmMinVolume24h) return null;

  const prices = parseOutcomePrices(market);
  const tokenIds = parseClobTokenIds(market);
  const midPrice = prices[0] || 0.5;
  const estTakerFee = 0.04 * midPrice * (1 - midPrice);
  const profitPerRT = spread - estTakerFee;
  if (profitPerRT <= 0) return null;

  return {
    type: "market_making",
    question: (market.question || market.groupItemTitle || "").slice(0, 60),
    conditionId: market.conditionId,
    yesTokenId: tokenIds[0] || null,
    noTokenId: tokenIds[1] || null,
    spread,
    midPrice,
    bestBid: Number(market.bestBid || 0),
    bestAsk: Number(market.bestAsk || 0),
    liquidity: Math.round(liq),
    volume24h: Math.round(vol24h),
    profitPerRT: Math.round(profitPerRT * 10000) / 10000,
    turnover: liq > 0 ? Math.round((vol24h / liq) * 100) / 100 : 0,
    estDailyProfit: Math.round(profitPerRT * vol24h * 100) / 100, // Very rough estimate
    tickSize: market.orderPriceMinTickSize || "0.01",
    negRisk: !!market.negRisk,
  };
}

async function scan(options = {}) {
  const config = { ...DEFAULT_CONFIG, ...options };

  console.log("Scanning Polymarket...");
  const events = await fetchAllEvents({ limit: options.eventLimit || 2000 });

  let allMarkets = [];
  for (const e of events) {
    if (e.markets) allMarkets.push(...e.markets);
  }

  // Multi-outcome arb
  const arbs = events
    .map((e) => analyzeMultiOutcomeArb(e, config))
    .filter(Boolean)
    .sort((a, b) => b.arbProfit - a.arbProfit);

  const executableArbs = arbs.filter((a) => a.executable);

  // Market-making
  const mmOpps = allMarkets
    .map((m) => analyzeMarketMaking(m, config))
    .filter(Boolean)
    .sort((a, b) => b.estDailyProfit - a.estDailyProfit);

  return {
    scannedAt: new Date().toISOString(),
    eventCount: events.length,
    marketCount: allMarkets.length,
    arbs: {
      total: arbs.length,
      executable: executableArbs.length,
      items: arbs,
    },
    marketMaking: {
      total: mmOpps.length,
      items: mmOpps,
    },
  };
}

module.exports = { scan, analyzeMultiOutcomeArb, analyzeMarketMaking, DEFAULT_CONFIG };
