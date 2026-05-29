const test = require("node:test");
const assert = require("node:assert/strict");

const { ArbEngine } = require("../../src/lib/polymarket/arb-engine");
const { MarketMaker } = require("../../src/lib/polymarket/market-maker");
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

test("arb engine blocks live execution when plan would exceed open order cap", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 1 });
  let placeCalls = 0;
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    placeLimitOrderFn: async () => {
      placeCalls++;
      return { id: "unexpected" };
    },
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "blocked");
  assert.match(result.reason, /^risk:max_open_orders/);
  assert.equal(placeCalls, 0);
  assert.equal(risk.openOrderCount, 0);
});

test("arb engine blocks non-atomic live execution by default", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 5 });
  let placeCalls = 0;
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    placeLimitOrderFn: async () => {
      placeCalls++;
      return { id: "unexpected" };
    },
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "blocked");
  assert.equal(result.reason, "non_atomic_live_execution_disabled");
  assert.equal(result.legsExecuted, 0);
  assert.equal(placeCalls, 0);
  assert.equal(risk.openOrderCount, 0);
});

test("arb engine cancels placed legs when later live leg fails", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 5 });
  let placeCalls = 0;
  const canceled = [];
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    allowNonAtomicLiveExecution: true,
    placeLimitOrderFn: async () => {
      placeCalls++;
      if (placeCalls === 1) return { id: "leg-1" };
      throw new Error("leg two rejected");
    },
    cancelOrderFn: async (_client, orderId) => {
      canceled.push(orderId);
    },
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "failed");
  assert.equal(result.legsExecuted, 1);
  assert.equal(result.cancellations[0].status, "canceled");
  assert.deepEqual(canceled, ["leg-1"]);
  assert.equal(risk.openOrderCount, 0);
  assert.equal(engine.getStats().executed, 0);
});

test("arb engine keeps risk and kills switch when rollback cancel is rejected", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 5 });
  let placeCalls = 0;
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    allowNonAtomicLiveExecution: true,
    placeLimitOrderFn: async () => {
      placeCalls++;
      if (placeCalls === 1) return { id: "leg-1" };
      throw new Error("leg two rejected");
    },
    cancelOrderFn: async () => ({ error: "not found", status: 404 }),
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "failed");
  assert.equal(result.cancellations[0].status, "cancel_failed");
  assert.equal(result.cancellations[0].error, "not found");
  assert.equal(risk.openOrderCount, 1);
  assert.equal(risk.killed, true);
});

test("arb engine treats rejected responses with ids as failed placements", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 5 });
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    allowNonAtomicLiveExecution: true,
    placeLimitOrderFn: async () => ({ id: "rejected-id", error: "insufficient balance", status: 400 }),
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "failed");
  assert.equal(result.reason, "insufficient balance");
  assert.equal(result.legsExecuted, 0);
  assert.equal(risk.openOrderCount, 0);
  assert.equal(engine.getStats().executed, 0);
});

test("arb engine treats success false placement payloads as failures", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 1000, maxSinglePositionUsd: 1000, maxOpenOrders: 5 });
  const engine = new ArbEngine(risk, {
    orderSizeUsd: 10,
    limitOffsetFromMid: 0,
    dryRun: false,
    allowNonAtomicLiveExecution: true,
    placeLimitOrderFn: async () => ({ success: false, errorMsg: "not enough allowance", orderID: "rejected-id" }),
  });
  const opportunity = {
    title: "Two-leg arb",
    executable: true,
    arbProfit: 0.2,
    arbType: "UNDER",
    outcomeCount: 2,
    outcomes: [
      { title: "A", tradeable: true, yesTokenId: "yes-a", yesPrice: 0.4, bestAsk: 0.4 },
      { title: "B", tradeable: true, yesTokenId: "yes-b", yesPrice: 0.4, bestAsk: 0.4 },
    ],
  };

  const result = await engine.evaluateAndExecute({}, opportunity);

  assert.equal(result.status, "failed");
  assert.equal(result.reason, "not enough allowance");
  assert.equal(result.legsExecuted, 0);
  assert.equal(risk.openOrderCount, 0);
  assert.equal(engine.getStats().executed, 0);
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

test("risk manager clears canceled order exposure and allows exposure-reducing sells", () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  risk.recordOrderPlaced({ orderId: "order-1", tokenId: "a", side: "buy", size: 60, price: 1 });
  assert.equal(risk.getStatus().openOrderExposure, 60);

  risk.clearOpenOrders();
  assert.equal(risk.openOrderCount, 0);
  assert.equal(risk.getStatus().openOrderExposure, 0);

  risk.recordFill("a", "buy", 100, 1);
  const sellCheck = risk.checkOrder({ tokenId: "a", side: "sell", size: 10, price: 1 });
  assert.equal(sellCheck.allowed, true);
});

test("risk manager blocks sell orders beyond available inventory", () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  risk.recordFill("a", "buy", 10, 0.4);

  const oversized = risk.checkOrder({ tokenId: "a", side: "sell", size: 20, price: 0.6 });
  assert.equal(oversized.allowed, false);
  assert.match(oversized.reason, /^sell_inventory_limit/);

  const first = risk.checkOrder({ tokenId: "a", side: "sell", size: 10, price: 0.6 });
  assert.equal(first.allowed, true);
  risk.recordOrderPlaced({ orderId: "sell-1", tokenId: "a", side: "sell", size: 10, price: 0.6 });

  const duplicate = risk.checkOrder({ tokenId: "a", side: "sell", size: 1, price: 0.6 });
  assert.equal(duplicate.allowed, false);
  assert.match(duplicate.reason, /^sell_inventory_limit/);
});

test("risk manager tracks zero-exposure sell orders by id", () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });

  risk.recordOrderPlaced({ orderId: "buy-1", tokenId: "a", side: "buy", size: 60, price: 1 });
  risk.recordOrderPlaced({ orderId: "sell-1", tokenId: "a", side: "sell", size: 10, price: 1 });
  assert.equal(risk.getStatus().openOrderExposure, 60);
  assert.equal(risk.openOrderCount, 2);

  risk.recordOrderClosed("sell-1");
  assert.equal(risk.getStatus().openOrderExposure, 60);
  assert.equal(risk.openOrderCount, 1);
});

test("market maker dry run simulates quotes without reserving orders", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: true, orderSizeUsd: 10 });

  const result = await maker._quoteMarket(
    { cancelAll: async () => undefined },
    "yes-token",
    {
      question: "Dry run market",
      midPrice: 0.5,
      spread: 0.04,
    }
  );

  assert.equal(result.actions.length, 1);
  assert.equal(result.actions[0].dryRun, true);
  assert.equal(risk.openOrderCount, 0);
  assert.equal(maker.stats.ordersPlaced, 0);
});

test("market maker dry run cycle does not cancel live orders", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: true, orderSizeUsd: 10 });
  maker.addMarket({
    yesTokenId: "yes-token",
    question: "Dry run market",
    midPrice: 0.5,
    spread: 0.04,
  });

  let cancelCalls = 0;
  const result = await maker.runCycle({
    cancelAll: async () => {
      cancelCalls++;
    },
  });

  assert.equal(cancelCalls, 0);
  assert.equal(result.results.length, 1);
  assert.equal(result.results[0].actions[0].dryRun, true);
});

test("market maker clamps ask preflight to available inventory", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  risk.recordFill("yes-token", "buy", 5, 0.4);
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });
  maker.inventory.set("yes-token", { yesShares: 5, noShares: 0 });

  const actions = [];
  const result = await maker._quoteMarket(
    {
      createOrder: async (order) => order,
      postOrder: async (order) => {
        actions.push(order);
        return { id: order.side === "BUY" ? "bid-1" : "ask-1" };
      },
    },
    "yes-token",
    {
      question: "Inventory market",
      midPrice: 0.5,
      spread: 0.04,
    }
  );

  const ask = result.actions.find((action) => action.side === "ask");
  assert.equal(ask.size, 5);
  assert.equal(ask.orderId, "ask-1");
  assert.equal(risk.openOrders.get("ask-1").size, 5);
  assert.equal(actions.length, 2);
});

test("market maker does not reserve failed post responses", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });

  const result = await maker._quoteMarket(
    {
      createOrder: async (order) => order,
      postOrder: async () => ({ error: "insufficient balance", status: 400 }),
    },
    "yes-token",
    {
      question: "Rejected market",
      midPrice: 0.5,
      spread: 0.04,
    }
  );

  assert.equal(result.actions[0].side, "bid");
  assert.equal(result.actions[0].error, "insufficient balance");
  assert.equal(risk.openOrderCount, 0);
  assert.equal(maker.openOrderIds.size, 0);
  assert.equal(maker.stats.ordersPlaced, 0);
});

test("market maker does not reserve success false post responses", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });

  const result = await maker._quoteMarket(
    {
      createOrder: async (order) => order,
      postOrder: async () => ({ success: false, errorMsg: "not enough allowance", orderID: "rejected-mm" }),
    },
    "yes-token",
    {
      question: "Rejected market",
      midPrice: 0.5,
      spread: 0.04,
    }
  );

  assert.equal(result.actions[0].side, "bid");
  assert.equal(result.actions[0].error, "not enough allowance");
  assert.equal(risk.openOrderCount, 0);
  assert.equal(maker.openOrderIds.size, 0);
  assert.equal(maker.stats.ordersPlaced, 0);
});

test("market maker live cycle only cancels owned quote orders", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  risk.recordOrderPlaced({ orderId: "arb-1", tokenId: "arb-token", side: "buy", size: 10, price: 0.5 });
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });
  maker.addMarket({
    yesTokenId: "yes-token",
    question: "Live market",
    midPrice: 0.5,
    spread: 0.04,
  });
  maker._quoteMarket = async () => ({ tokenId: "yes-token", actions: [] });

  let cancelAllCalls = 0;
  let cancelOrderCalls = 0;
  const result = await maker.runCycle({
    cancelAll: async () => {
      cancelAllCalls++;
    },
    cancelOrder: async () => {
      cancelOrderCalls++;
    },
  });

  assert.equal(cancelAllCalls, 0);
  assert.equal(cancelOrderCalls, 0);
  assert.equal(result.results.length, 1);
  assert.equal(risk.openOrderCount, 1);
  assert.equal(risk.openOrders.has("arb-1"), true);
});

test("market maker live cycle skips fresh quotes when quote cancel fails", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });
  maker.openOrderIds.add("mm-1");
  risk.recordOrderPlaced({ orderId: "mm-1", tokenId: "yes-token", side: "buy", size: 10, price: 0.5 });
  maker.addMarket({
    yesTokenId: "yes-token",
    question: "Live market",
    midPrice: 0.5,
    spread: 0.04,
  });

  let quoteCalls = 0;
  maker._quoteMarket = async () => {
    quoteCalls++;
    return { tokenId: "yes-token", actions: [] };
  };

  const result = await maker.runCycle({
    cancelOrder: async () => {
      throw new Error("exchange unavailable");
    },
  });

  assert.equal(result.status, "cancel_failed");
  assert.equal(quoteCalls, 0);
  assert.equal(risk.openOrders.has("mm-1"), true);
});

test("market maker treats resolved cancel error payloads as failures", async () => {
  const risk = new RiskManager({ maxTotalExposureUsd: 100, maxSinglePositionUsd: 100, maxOpenOrders: 5 });
  const maker = new MarketMaker(risk, { dryRun: false, orderSizeUsd: 10 });
  maker.openOrderIds.add("mm-1");
  risk.recordOrderPlaced({ orderId: "mm-1", tokenId: "yes-token", side: "buy", size: 10, price: 0.5 });

  const result = await maker._cancelOpenQuotes({
    cancelOrder: async () => ({ error: "not found", status: 404 }),
  });

  assert.equal(result.ok, false);
  assert.deepEqual(result.canceled, []);
  assert.equal(result.failed[0].orderId, "mm-1");
  assert.equal(result.failed[0].error, "not found");
  assert.equal(risk.openOrders.has("mm-1"), true);
  assert.equal(maker.openOrderIds.has("mm-1"), true);
});
