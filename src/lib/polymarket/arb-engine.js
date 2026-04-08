/**
 * Polymarket Arbitrage Engine
 *
 * Executes multi-outcome probability arbitrage on negRisk markets.
 *
 * UNDER-priced (sum < 1.0): Buy YES on all tradeable outcomes.
 *   One outcome will resolve YES ($1.00), rest resolve NO ($0.00).
 *   Profit = $1.00 - total cost of all YES tokens - fees.
 *
 * OVER-priced (sum > 1.0): Buy NO on all outcomes via negRisk.
 *   In negRisk markets, buying NO on all outcomes guarantees $1.00 payout
 *   (since exactly one YES will resolve, all others = NO = $1.00 each,
 *   but you pay less than $1.00 per NO on overpriced outcomes).
 *   Profit = sum of NO values - $1.00 collateral - fees.
 */

const { placeLimitOrder, fetchMarketOrderBook, fetchTickSize } = require("./client");

const DEFAULT_ARB_CONFIG = {
  minProfitPct: 0.02,             // Minimum 2% profit after fees to execute
  maxSlippagePct: 0.01,           // Max 1% slippage per leg
  orderSizeUsd: 50,               // $ per leg
  maxLegs: 20,                    // Max number of legs to execute
  executionMode: "limit",         // "limit" or "market"
  limitOffsetFromMid: 0.005,      // Place limits 0.5 cents inside the spread
  dryRun: true,                   // Default to dry run — don't actually place orders
};

class ArbEngine {
  constructor(riskManager, config = {}) {
    this.risk = riskManager;
    this.config = { ...DEFAULT_ARB_CONFIG, ...config };
    this.executionLog = [];
    this.stats = { scanned: 0, attempted: 0, executed: 0, totalProfit: 0 };
  }

  async evaluateAndExecute(client, arbOpportunity) {
    this.stats.scanned++;

    if (this.risk.killed) {
      return { status: "skipped", reason: "kill_switch" };
    }

    if (!arbOpportunity.executable) {
      return { status: "skipped", reason: "not_executable" };
    }

    if (arbOpportunity.arbProfit < this.config.minProfitPct) {
      return { status: "skipped", reason: "profit_too_low:" + (arbOpportunity.arbProfit * 100).toFixed(2) + "%" };
    }

    const tradeableOutcomes = arbOpportunity.outcomes.filter((o) => o.tradeable);
    if (tradeableOutcomes.length > this.config.maxLegs) {
      return { status: "skipped", reason: "too_many_legs:" + tradeableOutcomes.length };
    }

    // Build execution plan
    const plan = this._buildPlan(arbOpportunity, tradeableOutcomes);

    if (plan.estimatedProfit < this.config.minProfitPct) {
      return { status: "skipped", reason: "plan_profit_too_low:" + (plan.estimatedProfit * 100).toFixed(2) + "%" };
    }

    // Check risk
    const totalExposure = plan.legs.reduce((s, l) => s + l.cost, 0);
    const riskCheck = this.risk.checkOrder({
      tokenId: "arb_bundle",
      side: "buy",
      size: totalExposure,
      price: 1,
    });

    if (!riskCheck.allowed) {
      return { status: "blocked", reason: "risk:" + riskCheck.reason };
    }

    // Execute (or dry run)
    this.stats.attempted++;

    if (this.config.dryRun) {
      console.log("[ARB DRY RUN] " + arbOpportunity.title);
      console.log("  Type: " + arbOpportunity.arbType + " | Legs: " + plan.legs.length);
      console.log("  Total cost: $" + plan.totalCost.toFixed(2) + " | Est profit: " + (plan.estimatedProfit * 100).toFixed(2) + "%");
      for (const leg of plan.legs) {
        console.log("    " + leg.action + " " + leg.title.slice(0, 40) + " @ " + leg.price.toFixed(3) + " ($" + leg.cost.toFixed(2) + ")");
      }
      return { status: "dry_run", plan };
    }

    // Live execution
    const results = [];
    let successCount = 0;

    for (const leg of plan.legs) {
      try {
        const result = await placeLimitOrder(client, {
          tokenId: leg.tokenId,
          side: leg.side,
          price: leg.price,
          size: leg.size,
          negRisk: true,
          tickSize: leg.tickSize || "0.01",
        });
        results.push({ ...leg, status: "placed", orderId: result.orderID || result.id });
        this.risk.recordOrderPlaced();
        successCount++;
      } catch (err) {
        results.push({ ...leg, status: "failed", error: err.message });
      }
    }

    const execution = {
      status: successCount === plan.legs.length ? "executed" : "partial",
      title: arbOpportunity.title,
      arbType: arbOpportunity.arbType,
      legsPlanned: plan.legs.length,
      legsExecuted: successCount,
      totalCost: plan.totalCost,
      estimatedProfit: plan.estimatedProfit,
      timestamp: new Date().toISOString(),
      results,
    };

    this.executionLog.push(execution);
    if (successCount > 0) {
      this.stats.executed++;
      this.stats.totalProfit += plan.estimatedProfit * plan.totalCost;
    }

    return execution;
  }

  _buildPlan(arb, tradeableOutcomes) {
    const legs = [];
    let totalCost = 0;

    if (arb.arbType === "UNDER") {
      // Buy YES on all tradeable outcomes for less than $1 total
      for (const outcome of tradeableOutcomes) {
        // Place limit order slightly above best ask for faster fill
        const price = Math.min(0.99, outcome.bestAsk + this.config.limitOffsetFromMid);
        const size = Math.max(1, Math.round(this.config.orderSizeUsd / price));
        const cost = price * size;

        legs.push({
          action: "BUY YES",
          title: outcome.title,
          tokenId: outcome.yesTokenId,
          side: "buy",
          price: Math.round(price * 100) / 100,
          size,
          cost,
          tickSize: outcome.tickSize,
        });
        totalCost += cost;
      }
    } else {
      // OVER-priced: buy NO on all outcomes
      // In negRisk, NO token price = 1 - YES price
      for (const outcome of tradeableOutcomes) {
        const noPrice = 1 - outcome.yesPrice;
        const price = Math.min(0.99, Math.max(0.01, noPrice + this.config.limitOffsetFromMid));
        const size = Math.max(1, Math.round(this.config.orderSizeUsd / price));
        const cost = price * size;

        legs.push({
          action: "BUY NO",
          title: outcome.title,
          tokenId: outcome.noTokenId,
          side: "buy",
          price: Math.round(price * 100) / 100,
          size,
          cost,
          tickSize: outcome.tickSize,
        });
        totalCost += cost;
      }
    }

    // Estimate profit: for UNDER, profit = $1 payout per share - total cost per share set
    // Simplified: profit fraction = 1 - sumOfYesPrices for UNDER, sumOfYesPrices - 1 for OVER
    const estFees = legs.reduce((s, l) => s + 0.04 * l.price * (1 - l.price), 0);
    const estimatedProfit = Math.abs(arb.deviation) - estFees;

    return { legs, totalCost, estimatedProfit, estFees };
  }

  getStats() {
    return { ...this.stats, logSize: this.executionLog.length };
  }
}

module.exports = { ArbEngine, DEFAULT_ARB_CONFIG };
