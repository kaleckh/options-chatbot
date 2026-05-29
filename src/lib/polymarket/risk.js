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
    this.openOrders = new Map();    // orderId -> { exposure, side }
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
    for (const order of this.openOrders.values()) {
      total += Math.abs(order.exposure);
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
    const additionalExposure = this._additionalExposure(order, orderExposure);

    const sellInventoryCheck = this._checkSellInventory(order);
    if (!sellInventoryCheck.allowed) {
      return this._reject(order, sellInventoryCheck.reason);
    }

    const totalExposure = this.getTotalExposure();
    if (totalExposure + additionalExposure > this.config.maxTotalExposureUsd) {
      return this._reject(order, "total_exposure_limit:" + totalExposure.toFixed(2) + "+" + additionalExposure.toFixed(2) + ">" + this.config.maxTotalExposureUsd);
    }

    if (additionalExposure > this.config.maxSinglePositionUsd) {
      return this._reject(order, "single_position_limit:" + additionalExposure.toFixed(2) + ">" + this.config.maxSinglePositionUsd);
    }

    if (this.openOrderCount >= this.config.maxOpenOrders) {
      return this._reject(order, "max_open_orders:" + this.openOrderCount + ">=" + this.config.maxOpenOrders);
    }

    return { allowed: true, reason: null };
  }

  _additionalExposure(order, orderExposure) {
    if (String(order.side || "").toLowerCase() !== "sell") {
      return orderExposure;
    }
    return 0;
  }

  _orderPositionKeys(order) {
    return [order.tokenId, order.conditionId, order.marketId]
      .map((value) => String(value || "").trim())
      .filter(Boolean);
  }

  _positionSizeForOrder(order) {
    for (const key of this._orderPositionKeys(order)) {
      const position = this.positions.get(key);
      if (position) {
        return Number(position.size || 0);
      }
    }
    return 0;
  }

  _reservedSellSharesForOrder(order) {
    const keys = new Set(this._orderPositionKeys(order));
    let reserved = 0;
    for (const openOrder of this.openOrders.values()) {
      if (String(openOrder.side || "").toLowerCase() !== "sell") {
        continue;
      }
      const tokenId = String(openOrder.tokenId || "").trim();
      if (tokenId && keys.has(tokenId)) {
        reserved += Number(openOrder.size || 0);
      }
    }
    return reserved;
  }

  _checkSellInventory(order) {
    if (String(order.side || "").toLowerCase() !== "sell") {
      return { allowed: true, reason: null };
    }
    const sellSize = Number(order.size || 0);
    if (!Number.isFinite(sellSize) || sellSize <= 0) {
      return { allowed: false, reason: "invalid_sell_size" };
    }
    const positionSize = this._positionSizeForOrder(order);
    const reservedSellShares = this._reservedSellSharesForOrder(order);
    const available = Math.max(0, positionSize - reservedSellShares);
    if (sellSize > available) {
      return {
        allowed: false,
        reason: "sell_inventory_limit:" + sellSize.toFixed(2) + ">" + available.toFixed(2),
      };
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
      const closedSize = Math.min(size, existing.size);
      const pnl = (price - existing.avgPrice) * closedSize;
      this.dailyPnl += pnl;
      existing.size -= size;
      if (existing.size <= 0) {
        this.positions.delete(conditionId);
        return pnl;
      }
      existing.exposure = existing.size * existing.avgPrice;
      this.positions.set(conditionId, existing);
      return pnl;
    }
    existing.side = side;
    this.positions.set(conditionId, existing);
    return 0;
  }

  recordOrderPlaced(order = {}) {
    const rawExposure = Number(order.size || 0) * Number(order.price || 0);
    const exposure = String(order.side || "").toLowerCase() === "sell"
      ? this._additionalExposure(order, rawExposure)
      : rawExposure;
    const orderId = String(order.orderId || order.id || "order-" + Date.now() + "-" + this.openOrders.size);
    const reservedExposure = Number.isFinite(exposure) && exposure > 0 ? exposure : 0;
    const wasOpen = this.openOrders.has(orderId);
    this.openOrders.set(orderId, {
      exposure: reservedExposure,
      side: order.side || null,
      tokenId: order.tokenId || order.conditionId || null,
      size: Number(order.size || 0),
    });
    if (!wasOpen) {
      this.openOrderCount++;
    }
    return { openOrderCount: this.openOrderCount, reservedExposure };
  }

  recordOrderClosed(orderId = null) {
    if (orderId && this.openOrders.delete(String(orderId))) {
      this.openOrderCount = Math.max(0, this.openOrderCount - 1);
      return;
    }
    if (orderId) {
      return;
    }
    const firstOrderId = this.openOrders.keys().next().value;
    if (firstOrderId) {
      this.openOrders.delete(firstOrderId);
      this.openOrderCount = Math.max(0, this.openOrderCount - 1);
    }
  }

  clearOpenOrders() {
    this.openOrders.clear();
    this.openOrderCount = 0;
  }

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
      openOrderExposure: [...this.openOrders.values()].reduce((sum, order) => sum + Math.abs(order.exposure), 0),
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
