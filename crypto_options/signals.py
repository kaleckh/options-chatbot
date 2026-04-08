"""
Phase 1: Crypto options signal engine.

Reads BTC/ETH 1-minute bar data, computes technical indicators,
and generates directional signals for options spread trading.

Signals are momentum-based with regime and trend filters,
mirroring the equity options strategy that backtested at PF 1.76.
"""

import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import CRYPTO_DATA_DIR, SIGNAL_CONFIG, SYMBOLS


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Signal:
    timestamp: str
    symbol: str
    direction: str              # "call" or "put"
    direction_score: float      # 0-100
    tech_score: float           # 0-100
    signal_strength: float      # 0.0-1.0
    regime: str                 # trending_up, trending_down, ranging, volatile, quiet
    htf_trend: str              # up, down, neutral
    price: float
    rsi: float
    atr: float
    ema_spread_pct: float       # (ema_fast - ema_slow) / price * 100
    ret_5bar: float             # 5-bar return %
    ret_20bar: float            # 20-bar return %
    rationale: str


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars(symbol: str, lookback_minutes: int = 0) -> list[dict]:
    """Load 1-minute bars from normalized JSON."""
    path = CRYPTO_DATA_DIR / f"{symbol}.json"
    if not path.exists():
        raise FileNotFoundError(f"No data for {symbol} at {path}")
    data = json.loads(path.read_text())
    bars = data.get("bars", [])
    if lookback_minutes > 0:
        bars = bars[-lookback_minutes:]
    return bars


def resample_to_5m(bars_1m: list[dict]) -> pd.DataFrame:
    """Resample 1-minute bars to 5-minute OHLCV."""
    df = pd.DataFrame(bars_1m)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    ohlcv = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quoteVolume": "sum",
        "tradeCount": "sum",
        "takerBuyBaseVolume": "sum",
        "takerBuyQuoteVolume": "sum",
    }).dropna(subset=["open"])
    # Order flow
    ohlcv["takerSellBaseVolume"] = ohlcv["volume"] - ohlcv["takerBuyBaseVolume"]
    ohlcv["barDelta"] = ohlcv["takerBuyBaseVolume"] - ohlcv["takerSellBaseVolume"]
    ohlcv["buyPressure"] = np.where(
        ohlcv["volume"] > 0,
        ohlcv["takerBuyBaseVolume"] / ohlcv["volume"],
        0.5,
    )
    return ohlcv


# ── Indicators ────────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on 5-minute bars."""
    c = SIGNAL_CONFIG
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    n = len(close)

    # EMA
    df["ema_fast"] = _ema(close, c["ema_fast"])
    df["ema_slow"] = _ema(close, c["ema_slow"])
    df["ema_spread_pct"] = (df["ema_fast"] - df["ema_slow"]) / df["close"] * 100

    # RSI
    df["rsi"] = _rsi(close, c["rsi_period"])

    # ATR
    df["atr"] = _atr(high, low, close, c["atr_period"])
    df["atr_pct"] = df["atr"] / df["close"] * 100

    # Bollinger Bands
    df["bb_mid"] = df["close"].rolling(c["bb_period"]).mean()
    bb_std = df["close"].rolling(c["bb_period"]).std()
    df["bb_upper"] = df["bb_mid"] + c["bb_std"] * bb_std
    df["bb_lower"] = df["bb_mid"] - c["bb_std"] * bb_std
    df["bb_pct_b"] = np.where(
        (df["bb_upper"] - df["bb_lower"]) > 0,
        (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]),
        0.5,
    )

    # Returns
    df["ret_5"] = df["close"].pct_change(5) * 100
    df["ret_20"] = df["close"].pct_change(20) * 100

    # Cumulative volume delta
    df["cvd"] = df["barDelta"].cumsum()
    df["cvd_14"] = df["barDelta"].rolling(14).sum()

    # ATR percentile for regime
    atr_roll = df["atr"].rolling(100)
    df["atr_percentile"] = df["atr"].rolling(100).apply(
        lambda x: (x.values[-1] > x.values[:-1]).sum() / max(len(x) - 1, 1) * 100,
        raw=False,
    )

    # Trend strength
    df["trend_strength"] = np.where(
        df["atr"] > 0,
        np.abs(df["ema_fast"] - df["ema_slow"]) / df["atr"],
        0,
    )

    return df


def compute_htf(df_5m: pd.DataFrame) -> pd.DataFrame:
    """Compute 1-hour higher timeframe indicators from 5-minute bars."""
    htf = df_5m.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    close = htf["close"].values.astype(float)
    htf["ema20"] = _ema(close, 20)
    htf["ema50"] = _ema(close, 50)
    htf["rsi"] = _rsi(close, 14)
    htf["trend"] = np.where(
        (htf["close"] > htf["ema20"]) & (htf["ema20"] > htf["ema50"]),
        "up",
        np.where(
            (htf["close"] < htf["ema20"]) & (htf["ema20"] < htf["ema50"]),
            "down",
            "neutral",
        ),
    )
    return htf


# ── Regime classification ─────────────────────────────────────────────────────

def classify_regime(row: pd.Series) -> str:
    """Classify market regime from indicator values."""
    c = SIGNAL_CONFIG
    atr_pct = float(row.get("atr_percentile", 50))
    ts = float(row.get("trend_strength", 0))
    ema_spread = float(row.get("ema_spread_pct", 0))

    if atr_pct >= c["atr_volatile_percentile"]:
        if ts >= c["trend_strength_threshold"]:
            return "trending_up" if ema_spread > 0 else "trending_down"
        return "volatile"
    if atr_pct <= c["atr_quiet_percentile"]:
        return "quiet"
    if ts >= c["trend_strength_threshold"]:
        return "trending_up" if ema_spread > 0 else "trending_down"
    return "ranging"


# ── Signal scoring ────────────────────────────────────────────────────────────

def score_signal(row: pd.Series, regime: str, htf_trend: str) -> Optional[Signal]:
    """
    Score a single bar for options signal strength.

    Returns a Signal if conditions are met, None otherwise.
    Mirrors the equity strategy's momentum + tech scoring concept.
    """
    c = SIGNAL_CONFIG
    close = float(row["close"])
    rsi = float(row.get("rsi", 50))
    ema_fast = float(row.get("ema_fast", close))
    ema_slow = float(row.get("ema_slow", close))
    ret_5 = float(row.get("ret_5", 0))
    ret_20 = float(row.get("ret_20", 0))
    bb_pct_b = float(row.get("bb_pct_b", 0.5))
    atr = float(row.get("atr", 0))
    ema_spread = float(row.get("ema_spread_pct", 0))

    # ── Determine direction ───────────────────────────────────────────────
    bullish = (
        close > ema_fast
        and ema_fast > ema_slow
        and ret_5 > 0.3
    )
    bearish = (
        close < ema_fast
        and ema_fast < ema_slow
        and ret_5 < -0.3
    )

    if not bullish and not bearish:
        return None

    direction = "call" if bullish else "put"

    # ── Regime filter ─────────────────────────────────────────────────────
    # Calls: prefer trending_up, ranging, quiet. Block trending_down.
    # Puts: prefer trending_down, volatile. Block trending_up.
    if direction == "call" and regime == "trending_down":
        return None
    if direction == "put" and regime == "trending_up":
        return None

    # ── HTF trend filter ──────────────────────────────────────────────────
    if direction == "call" and htf_trend == "down":
        return None
    if direction == "put" and htf_trend == "up":
        return None

    # ── Tech score (0-100) ────────────────────────────────────────────────
    tech = 50.0  # base

    # RSI component
    if direction == "call":
        if 40 <= rsi <= 65:
            tech += 15  # healthy bullish RSI
        elif rsi > 75:
            tech -= 15  # overbought
        elif rsi < 30:
            tech -= 10  # oversold but we're bullish
    else:
        if 35 <= rsi <= 60:
            tech += 15
        elif rsi < 25:
            tech -= 15
        elif rsi > 70:
            tech -= 10

    # EMA alignment
    if direction == "call" and ema_spread > 0.2:
        tech += 10
    elif direction == "put" and ema_spread < -0.2:
        tech += 10

    # Bollinger position
    if direction == "call" and 0.3 <= bb_pct_b <= 0.7:
        tech += 5  # middle of bands, room to run
    elif direction == "put" and 0.3 <= bb_pct_b <= 0.7:
        tech += 5

    tech = max(0, min(100, tech))

    # ── Direction score (0-100) ───────────────────────────────────────────
    # Weighted: tech 50%, momentum 30%, regime 20%
    momentum_score = min(100, max(0, 50 + abs(ret_5) * 5))

    regime_score = 50.0
    if direction == "call":
        if regime in ("trending_up", "quiet"):
            regime_score = 80
        elif regime == "ranging":
            regime_score = 60
        elif regime == "volatile":
            regime_score = 40
    else:
        if regime in ("trending_down", "volatile"):
            regime_score = 80
        elif regime == "ranging":
            regime_score = 60
        elif regime == "quiet":
            regime_score = 40

    dir_score = tech * 0.50 + momentum_score * 0.30 + regime_score * 0.20

    if dir_score < c["min_direction_score"]:
        return None

    # ── Signal strength (0-1) ─────────────────────────────────────────────
    strength = dir_score / 100.0

    if strength < c["min_signal_strength"]:
        return None

    # ── Build rationale ───────────────────────────────────────────────────
    reasons = []
    reasons.append(f"{'Bullish' if direction == 'call' else 'Bearish'} momentum: {ret_5:+.1f}% (5-bar)")
    reasons.append(f"Price {'above' if close > ema_fast else 'below'} EMA20, EMA spread {ema_spread:+.2f}%")
    reasons.append(f"RSI {rsi:.0f}, regime={regime}, 1h trend={htf_trend}")

    return Signal(
        timestamp=str(row.name) if hasattr(row, "name") else "",
        symbol=str(row.get("symbol", "")),
        direction=direction,
        direction_score=round(dir_score, 1),
        tech_score=round(tech, 1),
        signal_strength=round(strength, 3),
        regime=regime,
        htf_trend=htf_trend,
        price=round(close, 2),
        rsi=round(rsi, 1),
        atr=round(atr, 2),
        ema_spread_pct=round(ema_spread, 3),
        ret_5bar=round(ret_5, 2),
        ret_20bar=round(ret_20, 2),
        rationale="; ".join(reasons),
    )


# ── Main scan ─────────────────────────────────────────────────────────────────

def scan_crypto_signals(
    symbols: list[str] = None,
    lookback_minutes: int = 0,
) -> list[Signal]:
    """
    Scan crypto symbols for options trading signals.

    Returns list of Signal objects sorted by direction_score descending.
    """
    symbols = symbols or SYMBOLS
    c = SIGNAL_CONFIG
    lookback = lookback_minutes or c["lookback_bars"] * c["bar_interval_minutes"]
    all_signals: list[Signal] = []

    for symbol in symbols:
        try:
            bars = load_bars(symbol, lookback_minutes=lookback)
            if len(bars) < 300:
                continue

            df = resample_to_5m(bars)
            if len(df) < 100:
                continue

            df = compute_indicators(df)
            htf = compute_htf(df)

            # Get latest HTF trend
            htf_trend = str(htf["trend"].iloc[-1]) if len(htf) > 0 else "neutral"

            # Score the latest bar
            latest = df.iloc[-1]
            regime = classify_regime(latest)

            sig = score_signal(latest, regime, htf_trend)
            if sig is not None:
                sig.symbol = symbol
                all_signals.append(sig)

        except Exception as e:
            print(f"  {symbol}: signal error — {e}")

    all_signals.sort(key=lambda s: s.direction_score, reverse=True)
    return all_signals


# ── Backtester ────────────────────────────────────────────────────────────────

def backtest_signals(
    symbol: str = "BTCUSDT",
    signal_interval_bars: int = 12,   # check for signal every 12 5m-bars (1 hour)
    hold_bars: int = 84,              # hold for 84 5m-bars (7 hours ≈ 1 DTE equivalent)
    stop_loss_pct: float = 5.0,       # max loss on underlying move
    profit_target_pct: float = 5.0,   # target gain on underlying move
    cooldown_bars: int = 24,          # 24 x 5m = 2 hours after a stop
) -> dict:
    """
    Backtest momentum signals on historical crypto data.

    Simulates directional exposure (not actual options) to validate
    signal quality before wiring to Deribit.

    Returns aggregate metrics: trade count, win rate, PF, avg P&L.
    """
    bars = load_bars(symbol)
    if len(bars) < 1000:
        return {"error": f"Insufficient data for {symbol}: {len(bars)} bars"}

    df = resample_to_5m(bars)
    df = compute_indicators(df)
    htf = compute_htf(df)

    # Map HTF trend to 5m index
    htf_trend_map = {}
    for idx, row in htf.iterrows():
        htf_trend_map[idx] = str(row["trend"])

    trades = []
    cooldown_until = -1
    n = len(df)

    for i in range(100, n - hold_bars, signal_interval_bars):
        if i <= cooldown_until:
            continue

        row = df.iloc[i]
        regime = classify_regime(row)

        # Find nearest HTF bar
        bar_time = df.index[i]
        htf_times = htf.index[htf.index <= bar_time]
        htf_trend = htf_trend_map.get(htf_times[-1], "neutral") if len(htf_times) > 0 else "neutral"

        sig = score_signal(row, regime, htf_trend)
        if sig is None:
            continue

        entry_price = float(df.iloc[i + 1]["open"])  # enter on next bar open
        direction_mult = 1.0 if sig.direction == "call" else -1.0

        # Simulate hold period
        exit_reason = "time_exit"
        exit_price = float(df.iloc[i + hold_bars]["close"])
        best_pnl = 0
        worst_pnl = 0

        for j in range(1, hold_bars + 1):
            bar = df.iloc[i + j]
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])

            high_pnl = (bar_high / entry_price - 1) * 100 * direction_mult
            low_pnl = (bar_low / entry_price - 1) * 100 * direction_mult

            best_pnl = max(best_pnl, high_pnl)
            worst_pnl = min(worst_pnl, low_pnl)

            if worst_pnl <= -stop_loss_pct:
                exit_reason = "stop"
                exit_price = entry_price * (1 - stop_loss_pct / 100 * direction_mult)
                break
            if best_pnl >= profit_target_pct:
                exit_reason = "target"
                exit_price = entry_price * (1 + profit_target_pct / 100 * direction_mult)
                break

        pnl_pct = (exit_price / entry_price - 1) * 100 * direction_mult

        trades.append({
            "date": str(df.index[i]),
            "symbol": symbol,
            "direction": sig.direction,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "pnl_pct": round(pnl_pct, 2),
            "exit_reason": exit_reason,
            "direction_score": sig.direction_score,
            "tech_score": sig.tech_score,
            "regime": regime,
            "htf_trend": htf_trend,
        })

        if exit_reason == "stop":
            cooldown_until = i + cooldown_bars

    # Aggregate
    if not trades:
        return {"total_trades": 0, "error": "No trades generated"}

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_win = sum(t["pnl_pct"] for t in wins)
    total_loss = abs(sum(t["pnl_pct"] for t in losses))
    pf = total_win / total_loss if total_loss > 0 else 999

    by_exit = {}
    for t in trades:
        r = t["exit_reason"]
        if r not in by_exit:
            by_exit[r] = {"count": 0, "total_pnl": 0}
        by_exit[r]["count"] += 1
        by_exit[r]["total_pnl"] += t["pnl_pct"]

    return {
        "symbol": symbol,
        "total_trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
        "profit_factor": round(pf, 2),
        "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 2),
        "total_pnl_pct": round(sum(t["pnl_pct"] for t in trades), 2),
        "max_win_pct": round(max(t["pnl_pct"] for t in trades), 2),
        "max_loss_pct": round(min(t["pnl_pct"] for t in trades), 2),
        "by_exit_reason": {
            k: {"count": v["count"], "avg_pnl": round(v["total_pnl"] / v["count"], 2)}
            for k, v in by_exit.items()
        },
        "trades": trades,
    }


# ── Helper functions ──────────────────────────────────────────────────────────

def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _rsi(data: np.ndarray, period: int) -> np.ndarray:
    """Relative Strength Index."""
    deltas = np.diff(data, prepend=data[0])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = _ema(gains, period)
    avg_loss = _ema(losses, period)
    rs = np.where(avg_loss > 1e-10, avg_gain / avg_loss, 100.0)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Average True Range."""
    n = len(close)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return _ema(tr, period)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--backtest" in sys.argv:
        for sym in SYMBOLS:
            print(f"\n{'='*60}")
            print(f"  Backtesting {sym}")
            print(f"{'='*60}")
            result = backtest_signals(sym)
            if "error" in result:
                print(f"  {result['error']}")
                continue
            print(f"  Trades: {result['total_trades']}")
            print(f"  Win Rate: {result['win_rate_pct']}%")
            print(f"  Profit Factor: {result['profit_factor']}")
            print(f"  Avg P&L: {result['avg_pnl_pct']}%")
            print(f"  Exit breakdown:")
            for reason, stats in result["by_exit_reason"].items():
                print(f"    {reason}: {stats['count']} trades, avg {stats['avg_pnl']:+.2f}%")
    else:
        print("Scanning for crypto options signals...")
        signals = scan_crypto_signals()
        if not signals:
            print("No signals found.")
        for sig in signals:
            print(f"  {sig.symbol} {sig.direction.upper()} dir={sig.direction_score:.0f} "
                  f"tech={sig.tech_score:.0f} regime={sig.regime} price=${sig.price:.0f}")
            print(f"    {sig.rationale}")
