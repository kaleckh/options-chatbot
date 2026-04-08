"""
Log today's scan picks to data/forward-tracking/scan_picks.jsonl

Each line is one pick with entry details and underlying price at scan time.
Run daily during market hours to build a forward paper-trade record.

Usage: python scripts/log_scan_picks.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "data" / "forward-tracking"
LOG_FILE = LOG_DIR / "scan_picks.jsonl"


def main():
    import market_data_service as mds
    mds._MEMORY_CACHE.clear()
    import options_chatbot as oc

    picks = oc.scan_daily_top_trades(n_picks=10)
    if not picks:
        print("No picks today.")
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    logged = 0
    for p in picks:
        record = {
            "logged_at": datetime.now().isoformat(),
            "scan_date": datetime.now().strftime("%Y-%m-%d"),
            "ticker": p.get("ticker"),
            "direction": p.get("direction"),
            "strategy_type": p.get("strategy_type"),
            "long_strike": p.get("strike"),
            "short_strike": p.get("short_strike"),
            "spread_width": p.get("spread_width"),
            "net_debit": p.get("net_debit"),
            "max_profit": p.get("max_profit"),
            "max_loss": p.get("max_loss"),
            "risk_reward_ratio": p.get("risk_reward_ratio"),
            "debit_pct_of_width": p.get("debit_pct_of_width"),
            "expiry": p.get("expiry"),
            "dte": p.get("dte"),
            "underlying_price": p.get("underlying_price_at_selection") or p.get("stock_price"),
            "direction_score": p.get("direction_score"),
            "tech_score": p.get("tech_score"),
            "quality_score": p.get("quality_score"),
            "ev_pct": p.get("ev_pct"),
            "rsi14": p.get("rsi14"),
            "ret5": p.get("ret5"),
            "hv30": p.get("iv_pct"),
            "market_regime": p.get("market_regime"),
            "spy_ret5": p.get("spy_ret5"),
            "sector": p.get("sector"),
            "signal_reasons": p.get("signal_reasons"),
            "stop_loss_pct": p.get("stop_loss_pct"),
            "profit_target_pct": p.get("profit_target_pct"),
            "time_exit_pct": p.get("time_exit_pct"),
            "time_exit_day": p.get("time_exit_day"),
            # For tracking outcome later
            "outcome": None,
            "exit_date": None,
            "exit_price": None,
            "pnl_pct": None,
        }

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logged += 1
        print(f"  Logged: {record['ticker']} {record['direction']} {record['long_strike']}/{record['short_strike']} ${record['net_debit']:.2f} exp={record['expiry']}")

    print(f"\n{logged} picks logged to {LOG_FILE}")


if __name__ == "__main__":
    main()
