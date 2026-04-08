"""
Crypto options trading configuration.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Data paths ────────────────────────────────────────────────────────────────
CRYPTO_DATA_DIR = ROOT / "data" / "day-trading" / "crypto" / "normalized-1m"
FORWARD_TRACKING_DIR = ROOT / "data" / "forward-tracking"
FORWARD_LOG = FORWARD_TRACKING_DIR / "crypto_options_picks.jsonl"

# ── Symbols ───────────────────────────────────────────────────────────────────
SYMBOLS = ["ETHUSDT", "BTCUSDT"]  # ETH first — stronger backtest results
DERIBIT_CURRENCY_MAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}

# ── Signal thresholds ─────────────────────────────────────────────────────────
SIGNAL_CONFIG = {
    "bar_interval_minutes": 5,
    "lookback_bars": 500,           # 500 x 5m = ~42 hours of history
    "ema_fast": 20,
    "ema_slow": 50,
    "rsi_period": 14,
    "atr_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    # Scoring
    "min_direction_score": 60.0,
    "min_signal_strength": 0.55,
    # Regime
    "trend_strength_threshold": 0.5,
    "atr_volatile_percentile": 75,
    "atr_quiet_percentile": 25,
}

# ── Spread construction ───────────────────────────────────────────────────────
SPREAD_CONFIG = {
    "long_delta_target": 0.50,
    "short_delta_target": 0.20,
    "dte_min": 3,
    "dte_max": 14,
    "dte_target": 7,
    "max_width_pct": 5.0,
    "max_debit_pct_of_width": 65.0,
    "min_net_debit_usd": 50.0,
}

# ── Risk management ──────────────────────────────────────────────────────────
RISK_CONFIG = {
    "stop_loss_pct": 50.0,         # crypto more volatile, wider stop
    "profit_target_pct": 100.0,
    "time_exit_dte": 1,            # exit 1 day before expiry
    "max_position_pct": 3.0,
    "max_concurrent_positions": 3,
    "stop_cooldown_hours": 24,     # 24/7 market, use hours not days
    # Optimal backtest params (ETH: PF 1.81, 177 trades)
    "underlying_stop_pct": 3.0,    # stop if underlying moves 3% against
    "underlying_target_pct": 8.0,  # target if underlying moves 8% in favor
    "hold_bars_5m": 336,           # 28 hours max hold
}

# ── Deribit API ───────────────────────────────────────────────────────────────
DERIBIT_CONFIG = {
    "base_url": "https://www.deribit.com/api/v2",
    "testnet_url": "https://test.deribit.com/api/v2",
    "use_testnet": True,
    "client_id": os.getenv("DERIBIT_CLIENT_ID", ""),
    "client_secret": os.getenv("DERIBIT_CLIENT_SECRET", ""),
}
