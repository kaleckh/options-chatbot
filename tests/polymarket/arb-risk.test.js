const test = require("node:test");
const assert = require("node:assert/strict");

const { ArbEngine } = require("../../src/lib/polymarket/arb-engine");
const { RiskManager } = require("../../src/lib/polymarket/risk");
const { analyzeMultiOutcomeArb } = require("../../src/lib/polymarket/scanner");

function market({
  title,
  price,
  bid = 0.2,
  ask = 0.25,
  liquidity = 10000,
  spread = 0.02,
  tokenIds = ["yes", "no"],
}) {
  return {
    groupItemTitle: title,
    conditionId: title,
    outcomePrices: JSON.stringify([price, 1 - price]),
    clobTokenIds: JSON.stringify(tokenIds),
    bestBid: bid,
    bestAsk: ask,
    liquidityNum: liquidity,
    spread,
  };
}

test("scanner marks incomplete multi-outcome hedges non-executable", () => {
  const opportunity = analyzeMultiOutcomeArb({
    title: "Incomplete hedge",
    slug: "incomplete",
    negRisk: true,
    markets: [
      market({ title: "A", price: 0.2 }),
      market({ title: "B", price: 0.2 }),
      market({ title: "C", price: 0.2, ask: 0, bid: 0, liquidity: 0 }),
    ],
  }, {
    minLiquidity: 5000,
    minEventLiquidity: 10000,
    maxTradeableSpread: 0.1,
    minDeviationPct: 0.03,
  });

  assert.equal(opportunity.arbType, "UNDER");
  assert.equal(opportunity.tradeableOutcomes, 2);
  assert.equal(opportunity.fullHedgeTradeable, false);
  assert.equal(opportunity.executable, false);
});

test("arb plan uses equal shares and estimates profit from the rounded plan", () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000 });
  const engine = new ArbEngine(risk, { orderSizeUsd: 50, limitOffsetFromMid: 0, dryRun: true });
  const opportunity = analyzeMultiOutcomeArb({
    title: "Complete hedge",
    slug: "complete",
    negRisk: true,
    markets: [
      market({ title: "A", price: 0.2, ask: 0.2 }),
      market({ title: "B", price: 0.2, ask: 0.2 }),
      market({ title: "C", price: 0.2, ask: 0.2 }),
    ],
  }, {
    minLiquidity: 5000,
    minEventLiquidity: 10000,
    maxTradeableSpread: 0.1,
    minDeviationPct: 0.03,
  });

  const plan = engine._buildPlan(opportunity, opportunity.outcomes.filter((outcome) => outcome.tradeable));
  assert.equal(new Set(plan.legs.map((leg) => leg.size)).size, 1);
  assert.equal(plan.totalCost, 150);
  assert.ok(plan.estimatedProfit > 0);
  assert.ok(plan.estimatedProfitUsd > 0);
});

test("risk manager reserves open-order exposure and realizes partial sell pnl", () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });

  assert.equal(risk.checkOrder({ tokenId: "a", side: "buy", size: 60, price: 1 }).allowed, true);
  risk.recordOrderPlaced({ orderId: "order-1", tokenId: "a", side: "buy", size: 60, price: 1 });
  const blocked = risk.checkOrder({ tokenId: "b", side: "buy", size: 50, price: 1 });
  assert.equal(blocked.allowed, false);
  assert.match(blocked.reason, /^total_exposure_limit/);

  risk.recordOrderClosed("order-1");
  risk.recordFill("condition-1", "buy", 10, 0.4);
  const pnl = risk.recordFill("condition-1", "sell", 4, 0.6);
  assert.equal(Number(pnl.toFixed(2)), 0.8);
  assert.equal(Number(risk.dailyPnl.toFixed(2)), 0.8);
  assert.equal(risk.positions.get("condition-1").size, 6);
});
