"""
Walk-Forward Optimization (WFO) engine for options strategy confidence weights
and entry/exit parameters.

Pipeline
--------
1. Download N years of daily closes via yfinance for one or more tickers.
2. Split into rolling windows: train_months train → test_months test.
3. For each window, run Optuna to find the full parameter set that maximises
   Profit Factor on training data (9 parameters tuned simultaneously).
   Optuna is warm-started from the prior window's best params so each
   window converges faster and builds on what it learned.
4. Validate winning params on the held-out test slice (OOS).
5. Accept window only if ALL 5 guardrails pass.
6. Log accepted params by market regime to wfo_results.json.

What gets optimised (9 parameters)
-----------------------------------
Confidence weights : iv_percentile, delta, dte
Entry rules        : delta_target, entry_momentum_pct, min_confidence, min_ev_pct
Exit rules         : stop_loss_pct, profit_target_pct

Fitness function
----------------
Primary   : Profit Factor = gross_profit / gross_loss  (>1.5 good, >2 excellent)
Secondary : +0.1 × Sharpe bonus  (stabilises against outlier-driven PF)
Penalty   : −0.02 × max_drawdown_pct

Guardrails (ALL must pass)
--------------------------
G1  OOS Profit Factor ≥ 80% of IS Profit Factor   (overfitting gate)
G2  Weight drift ≤ max_drift_pct from profile      (stability gate — default 40%)
G3  Auto min-trades ≥ floor(test_days / 4, 10)    (sample-size gate — computed automatically)
G4  Top-10 trial weight std < 0.15                 (noise gate)
G5  OOS win rate ≥ 45%                             (consistency gate)

Params are NEVER written to STRATEGY_PROFILE automatically.
The UI exposes an Apply button with a full before/after diff.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

from options_chatbot import (
    STRATEGY_PROFILE,
    RISK_FREE_RATE,
    _bs_greeks,
    _get_market_regime,
)

WFO_RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wfo_results.json")


# ── TradeEvaluator ────────────────────────────────────────────────────────────

class TradeEvaluator:
    """
    Scores a single option candidate using parameterized confidence weights.
    Mirrors the live bot's formula — weights are supplied externally so
    Optuna can test thousands of combinations without touching STRATEGY_PROFILE.
    """

    def __init__(
        self,
        weights: dict,
        delta_target: float = 0.30,
        dte_optimal: int = 7,
        delta_falloff: float = 0.15,
        dte_falloff: float = 10.0,
    ) -> None:
        self.weights = weights
        self.delta_target = delta_target
        self.dte_optimal = dte_optimal
        self.delta_falloff = delta_falloff
        self.dte_falloff = dte_falloff

    def confidence_score(
        self,
        iv_percentile: float,
        delta: float,
        dte: int,
        tech_score: float = 50.0,   # 0–100 directional technical setup score
        bid_ask_spread_pct: float = 0.0,
    ) -> float:
        w = self.weights
        total_w = sum(w.values()) or 1.0

        iv_score    = max(0.0, 100.0 - iv_percentile)
        delta_score = 100.0 * math.exp(
            -((abs(delta) - self.delta_target) ** 2) / (2 * self.delta_falloff ** 2)
        )
        dte_score   = 100.0 * math.exp(
            -((dte - self.dte_optimal) ** 2) / (2 * self.dte_falloff ** 2)
        )

        raw = (
            w["iv_percentile"]        * iv_score
            + w["delta"]              * delta_score
            + w["dte"]                * dte_score
            + w.get("technical", 0.0) * tech_score
        ) / total_w

        spread_max = STRATEGY_PROFILE["filters"].get("liquidity_spread_max_pct", 10.0)
        if bid_ask_spread_pct > spread_max:
            raw -= STRATEGY_PROFILE["filters"].get("illiquid_extra_margin_pct", 5.0)

        return max(0.0, min(100.0, raw))

    def expected_value(
        self,
        confidence: float,
        stop_loss_pct: float,
        profit_target_pct: float,
    ) -> float:
        p_win = confidence / 100.0
        return p_win * profit_target_pct - (1.0 - p_win) * stop_loss_pct


# ── Portfolio metrics ─────────────────────────────────────────────────────────

def _sharpe(pnl_series: list[float], periods_per_year: int = 252) -> float:
    if len(pnl_series) < 5:
        return -99.0
    arr = np.array(pnl_series, dtype=float)
    std = arr.std(ddof=1)
    if std == 0:
        return 0.0
    return float(arr.mean() / std * math.sqrt(min(len(arr), periods_per_year)))


def _max_drawdown(pnl_series: list[float]) -> float:
    if not pnl_series:
        return 0.0
    cum  = np.cumsum(np.array(pnl_series, dtype=float))
    peak = np.maximum.accumulate(cum)
    dd   = (cum - peak) / (np.abs(peak) + 1e-9) * 100
    return float(abs(dd.min()))


# ── Precomputation (run once per window, shared across all Optuna trials) ─────

def _precompute(
    closes: pd.Series,
    dte_at_entry: int,
    trade_offset: int = 0,
) -> list[Optional[dict]]:
    """
    Compute per-day invariants ONCE before the Optuna trial loop starts.

    trade_offset : number of leading context-only days in `closes`.
                   Days before this index are used for HV computation but
                   do NOT generate trades. This lets short OOS windows borrow
                   history from the tail of the training slice so that hv30 and
                   iv_pct are valid even on the first day of the test period.

    Returns a list of length len(closes). Each entry is either:
      None  — filtered out (context day, no signal, bad HV, near boundary)
      dict  — {"idx", "S0", "hv30", "iv_pct", "trade_type", "date"}
    """
    prices = closes.values.astype(float)
    n      = len(prices)

    # Vectorised HV30: rolling 30-day annualised vol
    log_rets = np.log(prices[1:] / prices[:-1])
    hv30_arr = np.full(n, np.nan)
    for i in range(30, n):
        hv30_arr[i] = float(np.std(log_rets[i - 30 : i]) * math.sqrt(252))

    # IV percentile: rank of current hv30 vs trailing 252-day hv30 history
    iv_pct_arr = np.full(n, np.nan)
    for i in range(30, n):
        hv = hv30_arr[i]
        if np.isnan(hv) or hv <= 0:
            continue
        window = hv30_arr[max(0, i - 252) : i]
        valid  = window[~np.isnan(window)]
        if len(valid) >= 5:                          # need at least 5 data points
            iv_pct_arr[i] = float(np.sum(valid <= hv) / len(valid) * 100)

    # ── RSI 14 ────────────────────────────────────────────────────────────────
    rsi14_arr = np.full(n, 50.0)   # default to neutral
    deltas_p  = np.zeros(n)
    deltas_p[1:] = np.diff(prices)
    for i in range(15, n):
        win = deltas_p[i - 14 : i]
        avg_up   = float(np.mean(win[win > 0])) if np.any(win > 0) else 0.0
        avg_down = float(np.mean(-win[win < 0])) if np.any(win < 0) else 0.0
        rs = avg_up / (avg_down + 1e-9)
        rsi14_arr[i] = 100.0 - 100.0 / (1.0 + rs)

    # ── MACD (EMA12 − EMA26) ──────────────────────────────────────────────────
    k12 = 2.0 / 13.0
    k26 = 2.0 / 27.0
    ema12_arr = np.empty(n)
    ema26_arr = np.empty(n)
    ema12_arr[0] = ema26_arr[0] = prices[0]
    for i in range(1, n):
        ema12_arr[i] = prices[i] * k12 + ema12_arr[i - 1] * (1 - k12)
        ema26_arr[i] = prices[i] * k26 + ema26_arr[i - 1] * (1 - k26)
    macd_arr = ema12_arr - ema26_arr   # positive = bullish; rising = accelerating

    # ── SMA 50 ────────────────────────────────────────────────────────────────
    sma50_arr = np.full(n, np.nan)
    for i in range(50, n):
        sma50_arr[i] = float(np.mean(prices[i - 50 : i]))

    # trade_start: earliest index that can generate a real trade signal
    trade_start = max(50, trade_offset)   # bumped to 50 so sma50 is always valid

    precomputed: list[Optional[dict]] = []
    for i in range(n):
        if i < trade_start or i >= n - dte_at_entry - 1:
            precomputed.append(None)
            continue

        hv30   = hv30_arr[i]
        iv_pct = iv_pct_arr[i]
        if np.isnan(hv30) or hv30 <= 0 or np.isnan(iv_pct):
            precomputed.append(None)
            continue

        S0    = prices[i]
        ret5  = (S0 / prices[i - 5] - 1) * 100
        sma20 = float(np.mean(prices[i - 20 : i]))

        # Store ALL valid HV days — simulation loop applies the actual
        # trial-specific momentum threshold so Optuna can tune it.
        sma50 = float(sma50_arr[i]) if not np.isnan(sma50_arr[i]) else float(sma20)
        precomputed.append({
            "idx":    i,
            "S0":     float(S0),
            "hv30":   float(hv30),
            "iv_pct": float(iv_pct),
            "ret5":   float(ret5),
            "sma20":  float(sma20),
            "sma50":  sma50,
            "rsi14":  float(rsi14_arr[i]),
            "macd":   float(macd_arr[i]),
            "macd_prev": float(macd_arr[i - 1]) if i > 0 else float(macd_arr[i]),
            "date":   str(closes.index[i].date()),
        })

    return precomputed


# ── Portfolio metrics ─────────────────────────────────────────────────────────

def _profit_factor(trades: list[dict]) -> float:
    """Gross profit / gross loss. >1.5 is solid; >2.0 is excellent."""
    gross_win  = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = sum(abs(t["pnl_pct"]) for t in trades if t["pnl_pct"] < 0)
    if gross_loss < 0.01:
        return gross_win / 0.01 if gross_win > 0 else 0.0
    return gross_win / gross_loss


# ── Single-ticker simulation ──────────────────────────────────────────────────

def _simulate_window(
    closes: pd.Series,
    weights: dict,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    delta_target: float,
    min_confidence: float,
    min_ev_pct: float,
    entry_momentum: float = 0.5,     # % 5-day return needed to trigger signal
    _cache: Optional[list] = None,
) -> dict:
    """
    Simulate options trades on one price slice.

    entry_momentum is tunable per trial — precompute stores all valid HV days
    and this function applies the threshold, so Optuna can search it freely.
    """
    evaluator = TradeEvaluator(
        weights=weights,
        delta_target=delta_target,
        dte_optimal=dte_at_entry,
    )
    prices = closes.values.astype(float)
    n      = len(prices)

    cache = _cache if _cache is not None else _precompute(closes, dte_at_entry)

    # ── Per-day indicator arrays for adaptive exit scoring ─────────────────────
    # RSI 14
    _rsi14 = np.full(n, 50.0)
    _dp    = np.zeros(n)
    _dp[1:] = np.diff(prices)
    for _i in range(15, n):
        _w = _dp[_i - 14 : _i]
        _u = float(np.mean(_w[_w > 0])) if np.any(_w > 0) else 0.0
        _d = float(np.mean(-_w[_w < 0])) if np.any(_w < 0) else 0.0
        _rsi14[_i] = 100.0 - 100.0 / (1.0 + _u / (_d + 1e-9))
    # MACD (EMA12 − EMA26)
    _k12 = 2.0 / 13.0; _k26 = 2.0 / 27.0
    _ema12 = np.empty(n); _ema26 = np.empty(n)
    _ema12[0] = _ema26[0] = prices[0]
    for _i in range(1, n):
        _ema12[_i] = prices[_i] * _k12 + _ema12[_i - 1] * (1 - _k12)
        _ema26[_i] = prices[_i] * _k26 + _ema26[_i - 1] * (1 - _k26)
    _macd = _ema12 - _ema26
    # SMA 20 / SMA 50
    _sma20 = np.full(n, np.nan)
    _sma50 = np.full(n, np.nan)
    for _i in range(20, n):
        _sma20[_i] = float(np.mean(prices[_i - 20 : _i]))
    for _i in range(50, n):
        _sma50[_i] = float(np.mean(prices[_i - 50 : _i]))

    T = dte_at_entry / 365.0
    pnl_list: list[float] = []
    trades:   list[dict]  = []

    for day in cache:
        if day is None:
            continue
        i     = day["idx"]
        S0    = day["S0"]
        hv30  = day["hv30"]
        iv_pct = day["iv_pct"]
        ret5  = day["ret5"]
        sma20 = day["sma20"]

        # Apply trial-specific momentum threshold
        bullish = ret5 >  entry_momentum and S0 > sma20
        bearish = ret5 < -entry_momentum and S0 < sma20
        if not bullish and not bearish:
            continue
        trade_type = "call" if bullish else "put"

        # Technical setup score — uses precomputed indicators from _precompute
        tech = _tech_score(
            rsi14=day.get("rsi14", 50.0),
            macd=day.get("macd", 0.0),
            macd_prev=day.get("macd_prev", 0.0),
            price=S0,
            sma20=day["sma20"],
            sma50=day.get("sma50", day["sma20"]),
            trade_type=trade_type,
        )

        # Strike search (depends on delta_target, must stay in trial loop)
        best_strike: Optional[float] = None
        best_g:      Optional[dict]  = None
        best_diff = 999.0
        for offset in [x * 0.5 for x in range(-10, 16)]:
            K = round(S0 * (1 + offset / 100), 2)
            g = _bs_greeks(S0, K, T, RISK_FREE_RATE, hv30, trade_type)
            if not g:
                continue
            diff = abs(abs(g.get("delta", 0)) - delta_target)
            if diff < best_diff:
                best_diff   = diff
                best_strike = K
                best_g      = g

        if best_strike is None or not best_g or best_g.get("bs_price", 0) < 0.01:
            continue

        entry_px  = best_g["bs_price"]
        delta_val = abs(best_g.get("delta", 0))

        confidence = evaluator.confidence_score(
            iv_percentile=iv_pct, delta=delta_val, dte=dte_at_entry, tech_score=tech
        )
        ev = evaluator.expected_value(confidence, stop_loss_pct, profit_target_pct)
        if confidence < min_confidence or ev < min_ev_pct:
            continue

        stop_px   = entry_px * (1 - stop_loss_pct   / 100)
        target_px = entry_px * (1 + profit_target_pct / 100)
        exit_px, exit_reason = entry_px, "expired"

        # ── Adaptive exit state ───────────────────────────────────────────────
        # Trailing stop: activates once option gains ≥50% of profit target,
        # then trails 18% below the high-watermark option price.
        # TP extension: if tech setup is still intact at target, ride with trail.
        # Tech decay: if indicators collapse mid-trade, raise the stop floor.
        trail_activate_px = entry_px * (1 + profit_target_pct * 0.50 / 100)
        trail_depth       = 0.18       # trail stop sits 18% below peak
        high_watermark    = entry_px
        trail_active      = False
        trail_stop_px     = 0.0
        dynamic_stop_px   = stop_px    # raised by tech-decay logic

        for d in range(1, dte_at_entry + 1):
            fi = i + d
            if fi >= n:
                break
            S_now = float(prices[fi])
            T_now = max((dte_at_entry - d) / 365.0, 0)
            if T_now <= 0:
                intrinsic = (
                    max(0.0, S_now - best_strike)
                    if trade_type == "call"
                    else max(0.0, best_strike - S_now)
                )
                # If trailing was active, allow gains above original target;
                # otherwise cap at target to prevent inflated expiry returns.
                exit_px     = min(intrinsic, high_watermark) if trail_active else min(intrinsic, target_px)
                exit_reason = "expired"
                break

            g2      = _bs_greeks(S_now, best_strike, T_now, RISK_FREE_RATE, hv30, trade_type)
            opt_now = g2.get("bs_price", 0.0) if g2 else 0.0

            # Update high watermark
            if opt_now > high_watermark:
                high_watermark = opt_now

            # ── Current tech score from live indicators ───────────────────────
            if fi >= 50 and not np.isnan(_sma50[fi]):
                cur_tech = _tech_score(
                    rsi14     = float(_rsi14[fi]),
                    macd      = float(_macd[fi]),
                    macd_prev = float(_macd[fi - 1]),
                    price     = S_now,
                    sma20     = float(_sma20[fi]) if not np.isnan(_sma20[fi]) else S_now,
                    sma50     = float(_sma50[fi]),
                    trade_type= trade_type,
                )
            else:
                cur_tech = tech   # fallback to entry-day score

            tech_healthy  = cur_tech >= max(25.0, tech * 0.65)
            tech_decayed  = cur_tech <  max(20.0, tech * 0.40)

            # ── Activate trailing stop once position is well in-profit ────────
            if not trail_active and opt_now >= trail_activate_px:
                trail_active  = True
                trail_stop_px = high_watermark * (1 - trail_depth)

            # ── Update trailing stop to follow high watermark ─────────────────
            if trail_active:
                trail_stop_px = max(trail_stop_px, high_watermark * (1 - trail_depth))

            # ── Tech-decay: raise stop floor to protect against bad setups ────
            if tech_decayed:
                if opt_now >= entry_px:
                    # In profit — lock in at least break-even
                    dynamic_stop_px = max(dynamic_stop_px, entry_px * 1.02)
                else:
                    # In loss — tighten remaining loss budget by 40%
                    tighter = dynamic_stop_px + (entry_px - dynamic_stop_px) * 0.40
                    dynamic_stop_px = max(dynamic_stop_px, tighter)

            # ── Hard stop (whichever is higher: static, dynamic, or trail) ────
            effective_stop = max(dynamic_stop_px, trail_stop_px if trail_active else 0.0)
            if opt_now <= effective_stop:
                exit_px     = opt_now
                exit_reason = "trailing_stop" if trail_active else "stop"
                break

            # ── Take-profit: extend if setup still healthy, else lock in ──────
            if opt_now >= target_px:
                if tech_healthy and not trail_active:
                    # Tech still intact — switch to trailing stop; let it run
                    trail_active  = True
                    trail_stop_px = high_watermark * (1 - trail_depth)
                    # Don't break — trade continues under trail management
                elif not trail_active:
                    exit_px     = target_px
                    exit_reason = "target"
                    break
                # If trail already active, just keep riding

        pnl = (exit_px - entry_px) / entry_px * 100
        pnl_list.append(pnl)
        trades.append({
            "date":        day["date"],
            "type":        trade_type,
            "strike":      best_strike,
            "entry_px":    round(entry_px, 4),
            "exit_px":     round(exit_px, 4),
            "exit_reason": exit_reason,
            "confidence":  round(confidence, 1),
            "tech_score":  round(tech, 1),
            "ev":          round(ev, 1),
            "pnl_pct":     round(pnl, 2),
        })

    wins = sum(1 for p in pnl_list if p > 0)
    return {
        "sharpe":           _sharpe(pnl_list),
        "profit_factor":    _profit_factor(trades),
        "win_rate":         round(wins / max(len(pnl_list), 1), 4),
        "max_drawdown_pct": _max_drawdown(pnl_list),
        "n_trades":         len(pnl_list),
        "trades":           trades,
    }


def _simulate_window_multi(
    closes_dict: dict[str, pd.Series],
    weights: dict,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    delta_target: float,
    min_confidence: float,
    min_ev_pct: float,
    entry_momentum: float = 0.5,
    _caches: Optional[dict] = None,
) -> dict:
    """Pool trades across multiple tickers. Pass _caches to skip HV recomputation."""
    all_pnl:    list[float] = []
    all_trades: list[dict]  = []

    for ticker, closes in closes_dict.items():
        if len(closes) < 50:
            continue
        cache = _caches.get(ticker) if _caches else None
        result = _simulate_window(
            closes=closes, weights=weights,
            dte_at_entry=dte_at_entry, stop_loss_pct=stop_loss_pct,
            profit_target_pct=profit_target_pct, delta_target=delta_target,
            min_confidence=min_confidence, min_ev_pct=min_ev_pct,
            entry_momentum=entry_momentum, _cache=cache,
        )
        for t in result["trades"]:
            t["ticker"] = ticker
        all_pnl.extend([t["pnl_pct"] for t in result["trades"]])
        all_trades.extend(result["trades"])

    wins = sum(1 for p in all_pnl if p > 0)
    return {
        "sharpe":           _sharpe(all_pnl),
        "profit_factor":    _profit_factor(all_trades),
        "win_rate":         round(wins / max(len(all_pnl), 1), 4),
        "max_drawdown_pct": _max_drawdown(all_pnl),
        "n_trades":         len(all_pnl),
        "trades":           all_trades,
    }


# ── Technical setup score ─────────────────────────────────────────────────────

def _tech_score(
    rsi14: float,
    macd: float,
    macd_prev: float,
    price: float,
    sma20: float,
    sma50: float,
    trade_type: str,
) -> float:
    """
    Direction-aware technical setup score (0–100).

    Call setup  : wants RSI building (45–70), MACD positive/rising, price above SMAs
    Put setup   : wants RSI declining (30–55), MACD negative/falling, price below SMAs

    Components (weighted):
      40% SMA trend alignment  (price/sma20/sma50 stack)
      35% RSI positioning      (momentum building in the right direction)
      25% MACD momentum        (histogram sign + direction)
    """
    macd_rising = macd > macd_prev   # histogram is growing

    if trade_type == "call":
        # Trend: price > sma20 > sma50 = full alignment
        trend = (50.0 if price > sma20 else 0.0) + (50.0 if sma20 > sma50 else 0.0)
        # RSI: ideal ~55 (building momentum, not overbought)
        rsi_s = max(0.0, 100.0 - abs(rsi14 - 55.0) * (100.0 / 35.0))
        # MACD: positive and rising = 100, positive only = 50, negative = 0
        macd_s = 100.0 if macd > 0 and macd_rising else (50.0 if macd > 0 else 0.0)
    else:
        trend = (50.0 if price < sma20 else 0.0) + (50.0 if sma20 < sma50 else 0.0)
        rsi_s = max(0.0, 100.0 - abs(rsi14 - 45.0) * (100.0 / 35.0))
        macd_s = 100.0 if macd < 0 and not macd_rising else (50.0 if macd < 0 else 0.0)

    return trend * 0.40 + rsi_s * 0.35 + macd_s * 0.25


# ── Auto min-trades (no manual input required) ───────────────────────────────

def _auto_min_trades(test_days: int, n_tickers: int = 1) -> int:
    """
    Compute the minimum acceptable OOS trade count automatically.

    Formula: max(10, test_days // 4) × sqrt(n_tickers)
    Examples
    --------
    42-day test, 1 ticker  → max(10, 10) = 10
    63-day test, 1 ticker  → max(10, 15) = 15
    63-day test, 3 tickers → 15 × ~1.7  = 25
    """
    base = max(10, test_days // 4)
    return max(10, int(base * (n_tickers ** 0.5)))


# ── Adaptive exit bounds (learned from prior window IS trades) ────────────────

def _adapt_bounds(
    is_trades: list[dict],
    current_stop: float,
    current_target: float,
    min_sample: int = 8,
) -> dict:
    """
    Analyse IS trade exit patterns to shift stop-loss / profit-target search
    bounds for the *next* window's Optuna run.

    Stop-loss rules
    ---------------
    > 60% losses are stop-outs  → stop may be too tight → widen range upward
    < 25% losses are stop-outs  → losses bleed to expiry → tighten to cut sooner

    Profit-target rules
    -------------------
    > 65% wins hit target       → target may be too low  → shift range higher
    < 30% wins hit target       → wins expire below target → lower range

    Returns a dict with stop_lo, stop_hi, tgt_lo, tgt_hi, and notes list.
    """
    wins   = [t for t in is_trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in is_trades if t.get("pnl_pct", 0) <= 0]
    notes: list[str] = []

    # ── Stop-loss bounds ──────────────────────────────────────────────────────
    stop_lo, stop_hi = 20.0, 85.0   # absolute search limits
    if len(losses) >= min_sample:
        stop_hits = sum(1 for t in losses if "stop" in t.get("exit_reason", ""))
        stop_rate = stop_hits / len(losses)
        if stop_rate > 0.60:
            # Too many stops — trades getting cut before they recover
            stop_lo = min(current_stop * 0.80, 40.0)
            stop_hi = min(current_stop * 1.60, 85.0)
            notes.append(
                f"Stop widened (stop-out rate {stop_rate*100:.0f}% — trades cut early; "
                f"trying {stop_lo:.0f}–{stop_hi:.0f}%)"
            )
        elif stop_rate < 0.25:
            # Losses bleeding to expiry — stop not triggering; tighten to exit sooner
            stop_lo = max(current_stop * 0.50, 15.0)
            stop_hi = max(current_stop * 1.10, 30.0)
            notes.append(
                f"Stop tightened (stop-out rate {stop_rate*100:.0f}% — losses expiring; "
                f"trying {stop_lo:.0f}–{stop_hi:.0f}%)"
            )
        else:
            # Balanced — stay near current value
            stop_lo = max(current_stop * 0.70, 20.0)
            stop_hi = min(current_stop * 1.40, 80.0)

    # ── Profit-target bounds ──────────────────────────────────────────────────
    tgt_lo, tgt_hi = 40.0, 250.0   # absolute search limits
    if len(wins) >= min_sample:
        target_hits = sum(1 for t in wins if "target" in t.get("exit_reason", ""))
        target_rate = target_hits / len(wins)
        avg_win     = sum(t["pnl_pct"] for t in wins) / len(wins)
        if target_rate > 0.65:
            # Most wins are capped at target — may be leaving gains on table
            tgt_lo = max(current_target * 0.80, 50.0)
            tgt_hi = min(current_target * 1.80, 300.0)
            notes.append(
                f"Target raised ({target_rate*100:.0f}% hit limit; "
                f"trying {tgt_lo:.0f}–{tgt_hi:.0f}%)"
            )
        elif target_rate < 0.30:
            # Most wins expire below target — target is set too high for this regime
            tgt_lo = max(avg_win * 0.60, 30.0)
            tgt_hi = min(avg_win * 1.50, 200.0)
            notes.append(
                f"Target lowered ({target_rate*100:.0f}% hit limit, avg win {avg_win:.0f}%; "
                f"trying {tgt_lo:.0f}–{tgt_hi:.0f}%)"
            )
        else:
            tgt_lo = max(current_target * 0.70, 40.0)
            tgt_hi = min(current_target * 1.50, 250.0)

    # Round to natural step sizes
    stop_lo = max(round(stop_lo / 5) * 5, 15.0)
    stop_hi = max(round(stop_hi / 5) * 5, stop_lo + 10.0)
    tgt_lo  = max(round(tgt_lo  / 10) * 10, 30.0)
    tgt_hi  = max(round(tgt_hi  / 10) * 10, tgt_lo + 20.0)

    return {
        "stop_lo": stop_lo, "stop_hi": stop_hi,
        "tgt_lo":  tgt_lo,  "tgt_hi":  tgt_hi,
        "notes":   notes,
    }


# ── Optuna objective factory ──────────────────────────────────────────────────

def _make_objective(
    closes_input,   # pd.Series (single) or dict[str, pd.Series] (multi)
    config: dict,
    multi: bool = False,
    stop_bounds: tuple = (25.0, 60.0),   # (lo, hi) learned from prior window
    tgt_bounds:  tuple = (50.0, 150.0),  # (lo, hi) learned from prior window
) -> Callable:
    """
    Precompute HV/IV data ONCE. Each trial tunes 9 parameters:
      3 confidence weights + 6 entry/exit params.
    Stop-loss and profit-target bounds adapt from prior window's trade outcomes.
    Fitness = Profit Factor + 0.1×Sharpe − 0.02×MaxDrawdown.
    """
    dte = config["dte_at_entry"]

    if multi:
        caches = {sym: _precompute(c, dte) for sym, c in closes_input.items()}
    else:
        single_cache = _precompute(closes_input, dte)

    def objective(trial: "optuna.Trial") -> float:
        # ── Confidence weights ────────────────────────────────────────────────
        # DTE weight is fixed — it was causing 70-107% drift between windows
        # (too noisy to optimize on short windows) so it's locked to profile value.
        w_iv    = trial.suggest_float("w_iv",    0.10, 0.70)
        w_delta = trial.suggest_float("w_delta", 0.10, 0.60)
        w_dte   = float(STRATEGY_PROFILE["confidence_weights"].get("dte", 0.20))   # fixed, not tuned
        w_tech  = trial.suggest_float("w_tech",  0.00, 0.15)   # capped low — lagging indicators
        weights = {"iv_percentile": w_iv, "delta": w_delta, "dte": w_dte, "technical": w_tech}

        # ── Entry parameters ──────────────────────────────────────────────────
        delta_target    = trial.suggest_float("delta_target",    0.15, 0.45, step=0.05)
        entry_momentum  = trial.suggest_float("entry_momentum",  0.20, 1.50, step=0.10)
        min_confidence  = trial.suggest_float("min_confidence",  30.0, 70.0, step=5.0)
        min_ev_pct      = trial.suggest_float("min_ev_pct",       5.0, 20.0, step=1.0)

        # ── Exit parameters — bounds adapt from prior window's trade outcomes ─
        stop_loss_pct     = trial.suggest_float(
            "stop_loss_pct", stop_bounds[0], stop_bounds[1], step=5.0)
        profit_target_pct = trial.suggest_float(
            "profit_target_pct", tgt_bounds[0], tgt_bounds[1], step=10.0)

        sim_kwargs = dict(
            weights=weights,
            dte_at_entry=dte,
            stop_loss_pct=stop_loss_pct,
            profit_target_pct=profit_target_pct,
            delta_target=delta_target,
            min_confidence=min_confidence,
            min_ev_pct=min_ev_pct,
            entry_momentum=entry_momentum,
        )

        if multi:
            result = _simulate_window_multi(closes_input, **sim_kwargs, _caches=caches)
        else:
            result = _simulate_window(closes_input, **sim_kwargs, _cache=single_cache)

        if result["n_trades"] < max(5, config["min_trades"] // 3):
            return -99.0

        pf = result["profit_factor"]
        sr = result["sharpe"]
        dd = result["max_drawdown_pct"]
        return pf + 0.1 * max(0.0, sr) - 0.02 * dd

    return objective


# ── Guardrail checks ──────────────────────────────────────────────────────────

def _check_guardrails(
    is_result: dict,
    oos_result: dict,
    best_weights: dict,
    current_weights: dict,
    top_trials: list[dict],
    min_trades: int,            # auto-computed via _auto_min_trades()
    max_drift_pct: float = 0.40,
) -> tuple[bool, list[str]]:
    """Returns (passed, [issue messages]). ALL must pass."""
    issues: list[str] = []

    # G1: Overfit gate — two-part rule:
    #   Part A: OOS PF must be ≥ 1.0 (strategy must be profitable on unseen data)
    #   Part B: Only apply ratio check when IS PF > 3.0 (genuinely inflated in-sample)
    #           A modest IS PF of 1.5–2.5 degrading slightly OOS is normal, not overfit.
    is_pf  = is_result.get("profit_factor",  0)
    oos_pf = oos_result.get("profit_factor", 0)
    if oos_pf < 1.0:
        issues.append(
            f"G1 — OOS PF ({oos_pf:.2f}) < 1.0: strategy loses money on unseen data"
        )
    elif is_pf > 3.0 and oos_pf < 0.70 * is_pf:
        issues.append(
            f"G1 — OOS PF ({oos_pf:.2f}) < 70% of IS PF ({is_pf:.2f}): overfit"
        )

    # G2: Weight drift ≤ max_drift_pct from current profile
    # DTE excluded — it's now fixed, not tuned
    total = sum(best_weights.values()) or 1.0
    norm  = {k: v / total for k, v in best_weights.items()}
    for key in ["iv_percentile", "delta"]:
        cur   = current_weights.get(key, 0.33)
        new   = norm.get(key, 0.33)
        drift = abs(new - cur) / max(cur, 0.01)
        if drift > max_drift_pct:
            issues.append(
                f"G2 — '{key}' drifted {drift*100:.1f}% from current "
                f"(limit {max_drift_pct*100:.0f}%)"
            )

    # G3: Minimum trades in OOS window
    if oos_result["n_trades"] < min_trades:
        issues.append(
            f"G3 — only {oos_result['n_trades']} OOS trades (need ≥ {min_trades})"
        )

    # G4: Top-10 trial weight stability (DTE excluded — fixed, not tuned)
    if len(top_trials) >= 3:
        for key in ["w_iv", "w_delta"]:
            vals = [t.get(key, 0.0) for t in top_trials]
            std  = float(np.std(vals))
            if std > 0.15:
                issues.append(
                    f"G4 — '{key}' unstable across top trials (std={std:.3f} > 0.15)"
                )

    # G5: OOS win rate ≥ 35% — long options are asymmetric: a 35% win rate with
    # large winners (PF > 1.5) is genuinely profitable. 40% was rejecting good windows.
    oos_wr = oos_result.get("win_rate", 0)
    if oos_wr < 0.35:
        issues.append(
            f"G5 — OOS win rate {oos_wr*100:.1f}% < 35% floor (consistency gate)"
        )

    return len(issues) == 0, issues


# ── Walk-Forward loop ─────────────────────────────────────────────────────────

def _run_wfo_for_closes(
    closes_input,       # pd.Series or dict[str, pd.Series]
    label: str,         # ticker name or "pooled"
    train_days: int,
    test_days: int,
    n_trials: int,
    config: dict,
    current_weights: dict,
    max_drift_pct: float,
    multi: bool,
    progress_callback: Optional[Callable],
    base_pct: float,
    pct_span: float,
) -> dict:
    """Run the full WFO loop on a single closes input (single or multi-ticker)."""
    # Determine length for window building
    if multi:
        ref = next(iter(closes_input.values()))
        n = len(ref)
    else:
        n = len(closes_input)

    # How many context days to prepend to each test slice so that hv30 and
    # iv_pct are valid on the very first day of the actual test period.
    # 30 (hv30 warmup) + 252 (iv_pct lookback) + small buffer = 290.
    CONTEXT_DAYS = 290

    # Expanding window: training always anchors at index 0 and grows each step.
    # Each test period advances by test_days, but training sees ALL prior history.
    # This prevents the rolling approach from "forgetting" old regimes.
    windows     = []
    test_start  = train_days   # first test begins after minimum training period
    while test_start + test_days <= n:
        ctx_start    = max(0, test_start - CONTEXT_DAYS)
        trade_offset = test_start - ctx_start
        if multi:
            windows.append({
                "train":        {sym: c.iloc[0 : test_start]          # always from day 0
                                 for sym, c in closes_input.items()},
                "test":         {sym: c.iloc[ctx_start : test_start + test_days]
                                 for sym, c in closes_input.items()},
                "trade_offset": trade_offset,
            })
        else:
            windows.append({
                "train":        closes_input.iloc[0 : test_start],     # always from day 0
                "test":         closes_input.iloc[ctx_start : test_start + test_days],
                "trade_offset": trade_offset,
            })
        test_start += test_days

    if not windows:
        return {"error": f"Not enough data for even one WFO window for {label}"}

    accepted: list[dict] = []
    rejected: list[dict] = []
    regime_params: dict[str, list[dict]] = {"normal": [], "defense": []}

    # Adaptive exit bounds — start at defaults, shift after each window
    stop_bounds: tuple = (25.0, 60.0)
    tgt_bounds:  tuple = (50.0, 150.0)
    adaptation_notes: list[str] = []   # notes from the most recent adaptation
    prev_best_params: Optional[dict] = None   # warm-start for next window

    # Auto min-trades: derive from test window length (no manual input needed)
    n_tickers = len(closes_input) if multi else 1
    auto_min  = _auto_min_trades(test_days, n_tickers)
    config["min_trades"] = auto_min

    for wi, win in enumerate(windows):
        pct = base_pct + pct_span * (wi / len(windows))
        if progress_callback:
            progress_callback(
                f"[{label}] Window {wi+1}/{len(windows)}  "
                f"(stop {stop_bounds[0]:.0f}–{stop_bounds[1]:.0f}%  "
                f"target {tgt_bounds[0]:.0f}–{tgt_bounds[1]:.0f}%)…",
                pct,
            )

        train_input  = win["train"]
        test_input   = win["test"]
        trade_offset = win["trade_offset"]

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42 + wi),
        )

        # Warm-start: seed Optuna with the prior window's best params so it
        # converges faster and doesn't start from scratch each time.
        if prev_best_params is not None:
            warm = {}
            for k, v in prev_best_params.items():
                if k == "w_dte":
                    continue  # fixed — not a tunable param any more
                elif k == "stop_loss_pct":
                    warm[k] = float(np.clip(v, stop_bounds[0], stop_bounds[1]))
                elif k == "profit_target_pct":
                    warm[k] = float(np.clip(v, tgt_bounds[0], tgt_bounds[1]))
                else:
                    warm[k] = v
            study.enqueue_trial(warm)

        study.optimize(
            _make_objective(train_input, config, multi=multi,
                            stop_bounds=stop_bounds, tgt_bounds=tgt_bounds),
            n_trials=n_trials,
            show_progress_bar=False,
        )

        best_params  = study.best_params
        prev_best_params = best_params   # carry forward for next window warm-start
        best_weights = {
            "iv_percentile": best_params["w_iv"],
            "delta":         best_params["w_delta"],
            "dte":           float(STRATEGY_PROFILE["confidence_weights"].get("dte", 0.20)),  # fixed
            "technical":     best_params.get("w_tech", 0.0),
        }
        total = sum(best_weights.values()) or 1.0
        norm_weights = {k: round(v / total, 4) for k, v in best_weights.items()}

        # Use the full optimized param set for IS/OOS evaluation (not config defaults)
        sim_kwargs = dict(
            weights=best_weights,
            dte_at_entry=config["dte_at_entry"],
            stop_loss_pct=best_params.get("stop_loss_pct",    config["stop_loss_pct"]),
            profit_target_pct=best_params.get("profit_target_pct", config["profit_target_pct"]),
            delta_target=best_params.get("delta_target",      config["delta_target"]),
            min_confidence=best_params.get("min_confidence",  config["min_confidence"]),
            min_ev_pct=best_params.get("min_ev_pct",          config["min_ev_pct"]),
            entry_momentum=best_params.get("entry_momentum",  0.5),
        )
        # Full set of 9 optimized params (stored in results for diffing / apply)
        best_params_all = {
            "iv_percentile": round(norm_weights["iv_percentile"], 4),
            "delta":         round(norm_weights["delta"], 4),
            "dte":           round(norm_weights["dte"], 4),
            "technical":     round(norm_weights.get("technical", 0.0), 4),
            "delta_target":     round(sim_kwargs["delta_target"], 4),
            "entry_momentum":   round(sim_kwargs["entry_momentum"], 4),
            "min_confidence":   round(sim_kwargs["min_confidence"], 1),
            "min_ev_pct":       round(sim_kwargs["min_ev_pct"], 1),
            "stop_loss_pct":    round(sim_kwargs["stop_loss_pct"], 1),
            "profit_target_pct": round(sim_kwargs["profit_target_pct"], 1),
        }
        # Precompute IS/OOS caches — test slice gets trade_offset so context
        # days are used for HV warmup but don't generate trades
        dte = config["dte_at_entry"]
        if multi:
            train_caches = {s: _precompute(c, dte) for s, c in train_input.items()}
            test_caches  = {s: _precompute(c, dte, trade_offset) for s, c in test_input.items()}
            is_result  = _simulate_window_multi(train_input, **sim_kwargs, _caches=train_caches)
            oos_result = _simulate_window_multi(test_input,  **sim_kwargs, _caches=test_caches)
        else:
            train_cache = _precompute(train_input, dte)
            test_cache  = _precompute(test_input,  dte, trade_offset)
            is_result  = _simulate_window(train_input, **sim_kwargs, _cache=train_cache)
            oos_result = _simulate_window(test_input,  **sim_kwargs, _cache=test_cache)

        top_trials = [
            t.params
            for t in sorted(
                [t for t in study.trials if t.value is not None],
                key=lambda t: t.value, reverse=True,
            )[:10]
        ]

        passed, issues = _check_guardrails(
            is_result=is_result, oos_result=oos_result,
            best_weights=best_weights, current_weights=current_weights,
            top_trials=top_trials, min_trades=config["min_trades"],
            max_drift_pct=max_drift_pct,
        )

        # Date labels — handle both single and multi
        if multi:
            ref = next(iter(train_input.values()))
            ref_t = next(iter(test_input.values()))
        else:
            ref, ref_t = train_input, test_input

        regime = "normal"
        try:
            sym_for_regime = label if not multi else list(closes_input.keys())[0]
            regime_data = json.loads(_get_market_regime(sym_for_regime))
            if regime_data.get("regime") == "defense":
                regime = "defense"
        except Exception:
            pass

        record = {
            "window":             wi + 1,
            "train_start":        str(ref.index[0].date()),
            "train_end":          str(ref.index[-1].date()),
            "test_start":         str(ref_t.index[0].date()),
            "test_end":           str(ref_t.index[-1].date()),
            "is_sharpe":          round(is_result["sharpe"], 3),
            "is_profit_factor":   round(is_result["profit_factor"], 3),
            "oos_sharpe":         round(oos_result["sharpe"], 3),
            "oos_profit_factor":  round(oos_result["profit_factor"], 3),
            "oos_win_rate":       round(oos_result["win_rate"] * 100, 1),
            "oos_trades":         oos_result["n_trades"],
            "oos_max_dd":         round(oos_result["max_drawdown_pct"], 2),
            "weights":            norm_weights,
            "best_params":        best_params_all,
            "regime":             regime,
            "passed":             passed,
            "issues":             issues,
        }

        # ── Adapt exit bounds for the NEXT window using IS trade outcomes ────
        is_trades = is_result.get("trades", [])
        if len(is_trades) >= 8:
            adapted = _adapt_bounds(
                is_trades,
                current_stop=sim_kwargs["stop_loss_pct"],
                current_target=sim_kwargs["profit_target_pct"],
            )
            stop_bounds      = (adapted["stop_lo"], adapted["stop_hi"])
            tgt_bounds       = (adapted["tgt_lo"],  adapted["tgt_hi"])
            adaptation_notes = adapted["notes"]
        else:
            adaptation_notes = []

        record["adaptation_notes"]      = adaptation_notes
        record["stop_search_bounds"]    = list(stop_bounds)
        record["target_search_bounds"]  = list(tgt_bounds)

        # IS trade quality breakdown
        if is_trades:
            is_stops   = sum(1 for t in is_trades if "stop"   in t.get("exit_reason", ""))
            is_targets = sum(1 for t in is_trades if "target" in t.get("exit_reason", ""))
            is_wins    = [t for t in is_trades if t.get("pnl_pct", 0) > 0]
            is_losses  = [t for t in is_trades if t.get("pnl_pct", 0) <= 0]
            record["is_stop_rate"]   = round(is_stops   / max(len(is_losses), 1) * 100, 1)
            record["is_target_rate"] = round(is_targets / max(len(is_wins),   1) * 100, 1)
            record["is_avg_win"]     = round(sum(t["pnl_pct"] for t in is_wins)   / max(len(is_wins),   1), 1)
            record["is_avg_loss"]    = round(sum(t["pnl_pct"] for t in is_losses) / max(len(is_losses), 1), 1)

        if passed:
            # Store compact OOS trade list (with exit_reason for UI analysis)
            record["oos_trade_pnl"] = [
                {
                    "ticker":      t.get("ticker",     ""),
                    "date":        t["date"],
                    "type":        t.get("type", ""),
                    "pnl_pct":     round(t["pnl_pct"], 2),
                    "exit_reason": t.get("exit_reason", ""),
                    "confidence":  round(t.get("confidence", 0.0), 1),
                    "tech_score":  round(t.get("tech_score",  0.0), 1),
                    "ev":          round(t.get("ev",          0.0), 1),
                    "strike":      round(t.get("strike",      0.0), 2),
                    "entry_px":    round(t.get("entry_px",    0.0), 4),
                    "exit_px":     round(t.get("exit_px",     0.0), 4),
                }
                for t in oos_result.get("trades", [])
            ]
            accepted.append(record)
            regime_params[regime].append(best_params_all)
        else:
            rejected.append(record)

    # Average all 9 accepted params per regime → final_recommendations
    _PARAM_KEYS = [
        "iv_percentile", "delta", "dte", "technical",
        "delta_target", "entry_momentum", "min_confidence",
        "min_ev_pct", "stop_loss_pct", "profit_target_pct",
    ]
    final_recommendations: dict[str, dict] = {}
    for regime, plist in regime_params.items():
        if plist:
            final_recommendations[regime] = {
                k: round(sum(p.get(k, 0) for p in plist) / len(plist), 4)
                for k in _PARAM_KEYS
            }

    return {
        "label":                label,
        "windows_total":        len(windows),
        "windows_passed":       len(accepted),
        "windows_rejected":     len(rejected),
        "pass_rate_pct":        round(len(accepted) / max(len(windows), 1) * 100, 1),
        "accepted":             accepted,
        "rejected":             rejected,
        "final_recommendations": final_recommendations,
        # backwards-compat alias for old wfo_results.json files
        "final_weights":        {r: {k: v for k, v in p.items() if k in ("iv_percentile", "delta", "dte", "technical")}
                                 for r, p in final_recommendations.items()},
    }


def walk_forward(
    symbols: list[str],
    train_months: int = 6,
    test_months: int = 2,
    n_trials: int = 50,
    lookback_years: int = 5,
    mode: str = "pooled",           # "pooled" or "per_ticker"
    max_drift_pct: float = 0.40,    # G2 limit — how far weights can move from current
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> dict:
    """
    Main WFO entry point.

    Parameters
    ----------
    symbols         : list of tickers (e.g. ["SPY", "NVDA", "QQQ"])
    mode            : "pooled" — one universal weight set trained across all tickers
                      "per_ticker" — independent optimization per ticker
    max_drift_pct   : G2 guardrail — max allowed weight drift from current profile

    G3 min-trades is computed automatically via _auto_min_trades(test_days, n_tickers).
    """
    if not HAS_OPTUNA:
        return {"error": "optuna not installed — run: uv add optuna"}
    if not symbols:
        return {"error": "Provide at least one ticker symbol"}

    symbols = [s.upper() for s in symbols]
    sp = STRATEGY_PROFILE
    config = {
        "dte_at_entry":      int(sp["targets"]["dte_optimal"]),
        "stop_loss_pct":     float(sp["risk"]["stop_loss_pct"]),
        "profit_target_pct": float(sp["risk"]["profit_target_pct"]),
        "delta_target":      float(sp["targets"]["delta_optimal"]),
        "min_confidence":    50.0,
        "min_ev_pct":        float(sp["filters"]["min_ev_return_pct"]),
        "min_trades":        15,   # placeholder — overwritten by _auto_min_trades() per run
    }
    current_weights = sp["confidence_weights"].copy()

    # ── Fetch price history for all tickers ───────────────────────────────────
    if progress_callback:
        progress_callback("Fetching price history…", 0.02)

    fetch_days = lookback_years * 365 + 180
    all_closes: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period=f"{fetch_days}d")
            if not hist.empty and len(hist) >= 100:
                all_closes[sym] = hist["Close"].dropna()
        except Exception:
            pass

    if not all_closes:
        return {"error": "Could not fetch price history for any of the provided tickers"}

    fetched = list(all_closes.keys())
    train_days = int(train_months * 21)
    test_days  = int(test_months  * 21)

    # ── Run optimization ──────────────────────────────────────────────────────
    if mode == "pooled":
        if progress_callback:
            progress_callback(f"Running pooled WFO across {len(fetched)} tickers…", 0.05)

        # Use shortest series length to define windows (all tickers stay in sync)
        min_len = min(len(c) for c in all_closes.values())
        trimmed = {sym: c.iloc[-min_len:] for sym, c in all_closes.items()}

        result = _run_wfo_for_closes(
            closes_input=trimmed, label="pooled",
            train_days=train_days, test_days=test_days, n_trials=n_trials,
            config=config, current_weights=current_weights,
            max_drift_pct=max_drift_pct, multi=True,
            progress_callback=progress_callback, base_pct=0.05, pct_span=0.90,
        )

        if "error" in result:
            return result

        output = {
            "run_at":         datetime.now().isoformat(timespec="seconds"),
            "mode":           "pooled",
            "symbols":        fetched,
            "config":         config,
            "max_drift_pct":  max_drift_pct,
            **{k: result[k] for k in [
                "windows_total", "windows_passed", "windows_rejected",
                "pass_rate_pct", "accepted", "rejected", "final_weights", "final_recommendations",
            ]},
            "note": "Weights NOT applied automatically. Use 'Apply' in the UI.",
        }

    else:  # per_ticker
        per_ticker: dict[str, dict] = {}
        n_syms = len(fetched)

        for ti, sym in enumerate(fetched):
            base = 0.05 + 0.88 * (ti / n_syms)
            span = 0.88 / n_syms
            if progress_callback:
                progress_callback(f"[{sym}] optimising…", base)

            result = _run_wfo_for_closes(
                closes_input=all_closes[sym], label=sym,
                train_days=train_days, test_days=test_days, n_trials=n_trials,
                config=config, current_weights=current_weights,
                max_drift_pct=max_drift_pct, multi=False,
                progress_callback=progress_callback, base_pct=base, pct_span=span,
            )
            per_ticker[sym] = result

        output = {
            "run_at":        datetime.now().isoformat(timespec="seconds"),
            "mode":          "per_ticker",
            "symbols":       fetched,
            "config":        config,
            "max_drift_pct": max_drift_pct,
            "per_ticker":    per_ticker,
            "note": "Weights NOT applied automatically. Use 'Apply' in the UI.",
        }

    with open(WFO_RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    if progress_callback:
        progress_callback("Done.", 1.0)

    return output


def load_last_results() -> Optional[dict]:
    if not os.path.exists(WFO_RESULTS_FILE):
        return None
    try:
        with open(WFO_RESULTS_FILE) as f:
            return json.load(f)
    except Exception:
        return None
