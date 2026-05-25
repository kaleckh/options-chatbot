/**
 * Polymarket Market Maker
 *
 * Provides two-sided liquidity on selected markets. Posts limit orders
 * on both bid and ask sides, captures the spread, earns maker rebates.
 *
 * Strategy:
 * - Posts bid at (midpoint - halfSpread) and ask at (midpoint + halfSpread)
 * - Skews quotes based on inventory (if long, lower bid to reduce further buys)
 * - Refreshes quotes every cycle (default 30s)
 * - Respects risk limits from RiskManager
 */

const { placeLimitOrder } = require("./client");

const DEFAULT_MM_CONFIG = {
  orderSizeUsd: 25,              // $ size per side per market
  halfSpreadOverride: null,      // Override spread (null = use market spread / 2)
  minHalfSpread: 0.005,          // Minimum 0.5 cent each side
  maxHalfSpread: 0.03,           // Maximum 3 cent each side (tighter = fills faster)
  inventorySkewFactor: 0.3,      // How much to skew price based on inventory
  maxInventoryUsd: 100,          // Max inventory per side before stopping that side
  refreshIntervalMs: 30000,      // Quote refresh interval
  maxMarketsPerCycle: 5,         // Max markets to quote simultaneously
};

class MarketMaker {
  constructor(riskManager, config = {}) {
    this.risk = riskManager;
    this.config = { ...DEFAULT_MM_CONFIG, ...config };
    this.activeMarkets = new Map(); // tokenId -> market config
    this.inventory = new Map();     // tokenId -> { yesShares, noShares }
    this.running = false;
    this.cycleCount = 0;
    this.stats = { ordersPlaced: 0, ordersFilled: 0, totalSpreadCaptured: 0 };
  }

  addMarket(mmOpportunity) {
    if (this.activeMarkets.size >= this.config.maxMarketsPerCycle) {
      console.log("[MM] Max markets reached, skipping " + mmOpportunity.question);
      return false;
    }
    this.activeMarkets.set(mmOpportunity.yesTokenId, mmOpportunity);
    console.log("[MM] Added: " + mmOpportunity.question + " (spread:" + (mmOpportunity.spread * 100).toFixed(1) + "%)");
    return true;
  }

  removeMarket(tokenId) {
    this.activeMarkets.delete(tokenId);
  }

  async runCycle(client) {
    if (this.risk.killed) {
      console.log("[MM] Kill switch active, skipping cycle.");
      return;
    }

    this.cycleCount++;

    // Cancel stale orders before posting fresh quotes
    try {
      await client.cancelAll();
      this.risk.openOrderCount = 0;
    } catch (err) {
      console.log("[MM] Cancel all failed: " + err.message.slice(0, 80));
    }

    const results = [];

    for (const [tokenId, market] of this.activeMarkets) {
      try {
        const result = await this._quoteMarket(client, tokenId, market);
        results.push(result);
      } catch (err) {
        console.log("[MM] Error quoting " + market.question.slice(0, 40) + ": " + err.message);
      }
    }

    return {
      cycle: this.cycleCount,
      timestamp: new Date().toISOString(),
      marketsQuoted: results.length,
      results,
      riskStatus: this.risk.getStatus(),
    };
  }

  async _quoteMarket(client, tokenId, market) {
    let midPrice = market.midPrice;

    // Use the scanner's midPrice (from outcomePrices) as the reference.
    // The raw CLOB orderbook for YES tokens can be misleading on extreme-priced
    // markets. The scanner midPrice is more reliable.
    const halfSpread = Math.max(this.config.minHalfSpread, Math.min(this.config.maxHalfSpread, market.spread / 2));

    // Inventory skew
    const inv = this.inventory.get(tokenId) || { yesShares: 0, noShares: 0 };
    const netInventoryUsd = (inv.yesShares - inv.noShares) * midPrice;
    const skew = (netInventoryUsd / this.config.maxInventoryUsd) * this.config.inventorySkewFactor;

    let bidPrice = midPrice - halfSpread - skew;
    let askPrice = midPrice + halfSpread - skew;

    bidPrice = Math.max(0.01, Math.round(bidPrice * 100) / 100);
    askPrice = Math.min(0.99, Math.round(askPrice * 100) / 100);
    const orderSize = Math.round(this.config.orderSizeUsd / midPrice);

    if (orderSize < 1) return { tokenId, status: "skip", reason: "order_size_too_small" };

    // Check risk for both sides
    const bidCheck = this.risk.checkOrder({ tokenId, side: "buy", size: orderSize, price: bidPrice });
    const askCheck = this.risk.checkOrder({ tokenId, side: "sell", size: orderSize, price: askPrice });

    const actions = [];

    if (bidCheck.allowed && Math.abs(netInventoryUsd) < this.config.maxInventoryUsd) {
      try {
        const result = await placeLimitOrder(client, {
          tokenId,
          side: "buy",
          price: bidPrice,
          size: orderSize,
          negRisk: market.negRisk || false,
          tickSize: market.tickSize || "0.01",
        });
        this.risk.recordOrderPlaced({ tokenId, side: "buy", price: bidPrice, size: orderSize, orderId: result?.orderID || result?.id });
        this.stats.ordersPlaced++;
        actions.push({ side: "bid", price: bidPrice, size: orderSize });
      } catch (err) {
        actions.push({ side: "bid", error: err.message });
      }
    }

    if (askCheck.allowed && inv.yesShares > 0) {
      try {
        const askSize = Math.min(orderSize, inv.yesShares);
        const result = await placeLimitOrder(client, {
          tokenId,
          side: "sell",
          price: askPrice,
          size: askSize,
          negRisk: market.negRisk || false,
          tickSize: market.tickSize || "0.01",
        });
        this.risk.recordOrderPlaced({ tokenId, side: "sell", price: askPrice, size: askSize, orderId: result?.orderID || result?.id });
        this.stats.ordersPlaced++;
        actions.push({ side: "ask", price: askPrice, size: askSize });
      } catch (err) {
        actions.push({ side: "ask", error: err.message });
      }
    }

    return {
      tokenId,
      question: market.question,
      midPrice,
      bidPrice,
      askPrice,
      spread: askPrice - bidPrice,
      skew,
      netInventoryUsd,
      actions,
    };
  }

  getStats() {
    return {
      ...this.stats,
      activeMarkets: this.activeMarkets.size,
      cycleCount: this.cycleCount,
      inventory: Object.fromEntries(this.inventory),
    };
  }
}

module.exports = { MarketMaker, DEFAULT_MM_CONFIG };
