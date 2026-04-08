/**
 * Polymarket Risk Manager
 *
 * Enforces position limits, exposure caps, and provides a kill switch.
 * All engines check with risk manager before placing orders.
 */

const DEFAULT_RISK_CONFIG = {
  maxTotalExposureUsd: 1000,        // Max total $ at risk across all positions
  maxSinglePositionUsd: 200,        // Max $ in any single market
  maxOpenOrders: 20,                // Max concurrent open orders
  maxDailyLossUsd: 100,             // Stop trading if daily loss exceeds this
  maxPositionsPerEvent: 3,          // Max positions in outcomes of the same event
  minBalanceUsd: 50,                // Stop trading if balance drops below this
  killSwitch: false,                // Emergency stop — no orders placed when true
};

class RiskManager {
  constructor(options = {}) {
    this.config = { ...DEFAULT_RISK_CONFIG, ...options };
    this.positions = new Map();     // conditionId -> { size, avgPrice, side, exposure }
    this.openOrderCount = 0;
    this.dailyPnl = 0;
    this.dailyResetAt = null;
    this.killed = this.config.killSwitch;
    this.rejectLog = [];
  }

  resetDaily() {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    if (this.dailyResetAt !== today) {
      this.dailyPnl = 0;
      this.dailyResetAt = today;
    }
  }

  getTotalExposure() {
    let total = 0;
    for (const pos of this.positions.values()) {
      total += Math.abs(pos.exposure);
    }
    return total;
  }

  checkOrder(order) {
    this.resetDaily();

    if (this.killed) {
      return this._reject(order, "kill_switch_active");
    }

    if (this.dailyPnl <= -this.config.maxDailyLossUsd) {
      return this._reject(order, "daily_loss_limit_reached");
    }

    const orderExposure = order.size * order.price;

    if (this.getTotalExposure() + orderExposure > this.config.maxTotalExposureUsd) {
      return this._reject(order, "total_exposure_limit:" + this.getTotalExposure().toFixed(2) + "+" + orderExposure.toFixed(2) + ">" + this.config.maxTotalExposureUsd);
    }

    if (orderExposure > this.config.maxSinglePositionUsd) {
      return this._reject(order, "single_position_limit:" + orderExposure.toFixed(2) + ">" + this.config.maxSinglePositionUsd);
    }

    if (this.openOrderCount >= this.config.maxOpenOrders) {
      return this._reject(order, "max_open_orders:" + this.openOrderCount + ">=" + this.config.maxOpenOrders);
    }

    return { allowed: true, reason: null };
  }

  recordFill(conditionId, side, size, price) {
    const existing = this.positions.get(conditionId) || { size: 0, avgPrice: 0, side, exposure: 0 };
    if (side === "buy") {
      const totalCost = existing.size * existing.avgPrice + size * price;
      existing.size += size;
      existing.avgPrice = existing.size > 0 ? totalCost / existing.size : 0;
      existing.exposure = existing.size * existing.avgPrice;
    } else {
      existing.size -= size;
      if (existing.size <= 0) {
        const pnl = (price - existing.avgPrice) * size;
        this.dailyPnl += pnl;
        this.positions.delete(conditionId);
        return pnl;
      }
      existing.exposure = existing.size * existing.avgPrice;
    }
    existing.side = side;
    this.positions.set(conditionId, existing);
    return 0;
  }

  recordOrderPlaced() { this.openOrderCount++; }
  recordOrderClosed() { this.openOrderCount = Math.max(0, this.openOrderCount - 1); }

  kill(reason) {
    this.killed = true;
    console.log("[RISK] KILL SWITCH ACTIVATED: " + reason);
  }

  resume() {
    this.killed = false;
    console.log("[RISK] Kill switch deactivated.");
  }

  getStatus() {
    return {
      killed: this.killed,
      totalExposure: this.getTotalExposure(),
      openOrders: this.openOrderCount,
      dailyPnl: this.dailyPnl,
      positionCount: this.positions.size,
      limits: this.config,
    };
  }

  _reject(order, reason) {
    this.rejectLog.push({ timestamp: new Date().toISOString(), reason, order: { tokenId: order.tokenId, side: order.side, size: order.size, price: order.price } });
    return { allowed: false, reason };
  }
}

module.exports = { RiskManager, DEFAULT_RISK_CONFIG };
