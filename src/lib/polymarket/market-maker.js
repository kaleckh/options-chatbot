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

const { cancelOrder, placeLimitOrder } = require("./client");

const DEFAULT_MM_CONFIG = {
  orderSizeUsd: 25,              // $ size per side per market
  halfSpreadOverride: null,      // Override spread (null = use market spread / 2)
  minHalfSpread: 0.005,          // Minimum 0.5 cent each side
  maxHalfSpread: 0.03,           // Maximum 3 cent each side (tighter = fills faster)
  inventorySkewFactor: 0.3,      // How much to skew price based on inventory
  maxInventoryUsd: 100,          // Max inventory per side before stopping that side
  refreshIntervalMs: 30000,      // Quote refresh interval
  maxMarketsPerCycle: 5,         // Max markets to quote simultaneously
  dryRun: false,                 // Simulate quotes without placing orders
};

class MarketMaker {
  constructor(riskManager, config = {}) {
    this.risk = riskManager;
    this.config = { ...DEFAULT_MM_CONFIG, ...config };
    this.activeMarkets = new Map(); // tokenId -> market config
    this.inventory = new Map();     // tokenId -> { yesShares, noShares }
    this.openOrderIds = new Set();  // MM-owned quote order ids
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

    // Cancel stale MM-owned quote orders before posting fresh quotes.
    if (!this.config.dryRun) {
      const cancelResult = await this._cancelOpenQuotes(client);
      if (!cancelResult.ok) {
        return {
          cycle: this.cycleCount,
          timestamp: new Date().toISOString(),
          marketsQuoted: 0,
          results: [],
          status: "cancel_failed",
          cancelResult,
          riskStatus: this.risk.getStatus(),
        };
      }
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

  _requireOrderId(result) {
    const status = Number(result?.status);
    if (result?.success === false || result?.error || result?.errorMsg || (Number.isFinite(status) && status >= 400)) {
      throw new Error(String(result?.error || result?.errorMsg || result?.message || "order_rejected"));
    }
    const orderId = result?.orderID || result?.id;
    if (!orderId) {
      throw new Error("missing_order_id");
    }
    return String(orderId);
  }

  _requireCancelAccepted(result) {
    const status = Number(result?.status);
    if (result?.success === false || result?.error || result?.errorMsg || (Number.isFinite(status) && status >= 400)) {
      throw new Error(String(result?.error || result?.errorMsg || result?.message || "cancel_rejected"));
    }
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
    const askSize = Math.min(orderSize, inv.yesShares);
    const bidCheck = this.risk.checkOrder({ tokenId, side: "buy", size: orderSize, price: bidPrice });
    const askCheck = askSize >= 1
      ? this.risk.checkOrder({ tokenId, side: "sell", size: askSize, price: askPrice })
      : { allowed: false, reason: "no_sell_inventory" };

    const actions = [];

    if (bidCheck.allowed && Math.abs(netInventoryUsd) < this.config.maxInventoryUsd) {
      try {
        if (this.config.dryRun) {
          actions.push({ side: "bid", price: bidPrice, size: orderSize, dryRun: true });
        } else {
          const result = await placeLimitOrder(client, {
            tokenId,
            side: "buy",
            price: bidPrice,
            size: orderSize,
            negRisk: market.negRisk || false,
            tickSize: market.tickSize || "0.01",
          });
          const orderId = this._requireOrderId(result);
          this.risk.recordOrderPlaced({ tokenId, side: "buy", price: bidPrice, size: orderSize, orderId });
          this.openOrderIds.add(orderId);
          this.stats.ordersPlaced++;
          actions.push({ side: "bid", price: bidPrice, size: orderSize, orderId });
        }
      } catch (err) {
        actions.push({ side: "bid", error: err.message });
      }
    }

    if (askCheck.allowed && inv.yesShares > 0) {
      try {
        if (this.config.dryRun) {
          actions.push({ side: "ask", price: askPrice, size: askSize, dryRun: true });
        } else {
          const result = await placeLimitOrder(client, {
            tokenId,
            side: "sell",
            price: askPrice,
            size: askSize,
            negRisk: market.negRisk || false,
            tickSize: market.tickSize || "0.01",
          });
          const orderId = this._requireOrderId(result);
          this.risk.recordOrderPlaced({ tokenId, side: "sell", price: askPrice, size: askSize, orderId });
          this.openOrderIds.add(orderId);
          this.stats.ordersPlaced++;
          actions.push({ side: "ask", price: askPrice, size: askSize, orderId });
        }
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

  async _cancelOpenQuotes(client) {
    const orderIds = [...this.openOrderIds];
    if (orderIds.length === 0) {
      return { ok: true, canceled: [], failed: [] };
    }

    const canceled = [];
    const failed = [];
    for (const orderId of orderIds) {
      try {
        if (typeof client?.cancelOrder === "function") {
          this._requireCancelAccepted(await client.cancelOrder({ orderID: orderId }));
        } else {
          this._requireCancelAccepted(await cancelOrder(client, orderId));
        }
        this.openOrderIds.delete(orderId);
        this.risk.recordOrderClosed(orderId);
        canceled.push(orderId);
      } catch (err) {
        failed.push({ orderId, error: err.message });
      }
    }

    if (failed.length > 0) {
      console.log("[MM] Quote cancel failed for " + failed.length + " order(s); skipping fresh quotes.");
    }

    return { ok: failed.length === 0, canceled, failed };
  }

  getStats() {
    return {
      ...this.stats,
      activeMarkets: this.activeMarkets.size,
      cycleCount: this.cycleCount,
      openQuoteOrders: this.openOrderIds.size,
      inventory: Object.fromEntries(this.inventory),
    };
  }
}

module.exports = { MarketMaker, DEFAULT_MM_CONFIG };
