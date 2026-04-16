"""
Log today's scan picks to data/forward-tracking/scan_picks.jsonl

Each line is one pick with entry details and underlying price at scan time.
The daily scan also auto-creates tracked positions for new picks using the
same exact/comparable-contract resolution path as the app UI.

Usage: python scripts/log_scan_picks.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PYTHON_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND_DIR))

from local_env import load_local_env
from positions_repository import create_positions_repository
from positions_service import build_position_payload, review_open_positions


LOG_DIR = ROOT / "data" / "forward-tracking"
LOG_FILE = LOG_DIR / "scan_picks.jsonl"


def _is_weekend(run_at: datetime) -> bool:
    return run_at.weekday() >= 5


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_fill_price(scan_pick: dict[str, Any]) -> float | None:
    for field in ("entry_execution_price", "net_debit", "premium", "est_premium", "mid"):
        value = _safe_float(scan_pick.get(field))
        if value is not None and value > 0:
            return round(float(value), 4)
    return None


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _position_contract_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    source = _safe_dict(record.get("source_pick_snapshot"))

    def _norm_float(value: Any) -> float | None:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    strike = record.get("strike")
    if strike is None:
        strike = source.get("strike")
    if strike is None:
        strike = source.get("strike_est")

    expiry = record.get("expiry")
    if expiry is None:
        expiry = source.get("expiry")

    direction = record.get("direction")
    if direction is None:
        direction = source.get("direction") or source.get("type")

    contract_symbol = record.get("contract_symbol")
    if contract_symbol is None:
        contract_symbol = source.get("contract_symbol") or source.get("contractSymbol")

    strategy_type = (
        source.get("strategy_type")
        or record.get("strategy_type")
        or ("vertical_spread" if source.get("short_strike") is not None else "single_leg")
    )

    return (
        str(record.get("ticker") or source.get("ticker") or "").strip().upper() or None,
        str(direction or "").strip().lower() or None,
        str(expiry or "").strip()[:10] or None,
        str(strategy_type or "").strip().lower() or None,
        _norm_float(strike),
        _norm_float(source.get("short_strike") if source else record.get("short_strike")),
        str(contract_symbol or "").strip().upper() or None,
        str(source.get("short_contract_symbol") or record.get("short_contract_symbol") or "").strip().upper() or None,
    )


def _find_existing_open_contract(repository: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        open_positions = list(repository.list_positions("open") or [])
    except Exception:
        return None
    target_signature = _position_contract_signature(payload)
    for position in open_positions:
        if _position_contract_signature(dict(position)) == target_signature:
            return dict(position)
    return None


def _auto_track_scan_picks(
    *,
    repository: Any,
    picks: list[dict[str, Any]],
    filled_at: str,
    scan_date: str,
) -> tuple[int, int, int]:
    created_ids: list[int] = []
    created = 0
    duplicates = 0
    skipped = 0

    for pick in picks:
        fill_price = _pick_fill_price(pick)
        if fill_price is None:
            skipped += 1
            print(f"  Skipped auto-track: {pick.get('ticker')} missing fill price")
            continue

        try:
            payload = build_position_payload(
                scan_pick=copy.deepcopy(pick),
                fill_price=fill_price,
                contracts=1,
                filled_at=filled_at,
                notes=f"Auto-created from scheduled daily scan {scan_date}.",
                require_resolved_contract=True,
                preserve_fill_price=True,
            )
        except Exception as exc:
            skipped += 1
            print(f"  Skipped auto-track: {pick.get('ticker')} ({exc})")
            continue

        existing_position = _find_existing_open_contract(repository, payload)
        if existing_position is not None:
            duplicates += 1
            print(f"  Already open: {pick.get('ticker')} {payload.get('expiry')}")
            continue

        created_position = repository.create_position(payload)
        created += 1
        if created_position.get("id") is not None:
            created_ids.append(int(created_position["id"]))
        print(
            "  Auto-tracked: "
            f"{created_position.get('ticker')} {created_position.get('direction')} "
            f"${created_position.get('entry_option_price'):.2f} exp={created_position.get('expiry')}"
        )

    if created_ids:
        try:
            review_open_positions(repository, position_ids=created_ids)
        except Exception as exc:
            print(f"  Review after auto-track failed: {exc}")

    return created, duplicates, skipped


def _build_log_record(pick: dict[str, Any], *, run_at: datetime) -> dict[str, Any]:
    return {
        "logged_at": run_at.isoformat(),
        "scan_date": run_at.strftime("%Y-%m-%d"),
        "ticker": pick.get("ticker"),
        "direction": pick.get("direction"),
        "type": pick.get("type"),
        "strategy_type": pick.get("strategy_type"),
        "contract_symbol": pick.get("contract_symbol"),
        "short_contract_symbol": pick.get("short_contract_symbol"),
        "long_strike": pick.get("strike"),
        "short_strike": pick.get("short_strike"),
        "spread_width": pick.get("spread_width"),
        "net_debit": pick.get("net_debit"),
        "entry_execution_price": pick.get("entry_execution_price"),
        "entry_execution_basis": pick.get("entry_execution_basis"),
        "max_profit": pick.get("max_profit"),
        "max_loss": pick.get("max_loss"),
        "risk_reward_ratio": pick.get("risk_reward_ratio"),
        "debit_pct_of_width": pick.get("debit_pct_of_width"),
        "expiry": pick.get("expiry"),
        "original_logged_expiry": pick.get("original_logged_expiry"),
        "resolved_listed_expiry": pick.get("resolved_listed_expiry"),
        "dte": pick.get("dte"),
        "underlying_price": pick.get("underlying_price_at_selection") or pick.get("stock_price"),
        "direction_score": pick.get("direction_score"),
        "tech_score": pick.get("tech_score"),
        "quality_score": pick.get("quality_score"),
        "ev_pct": pick.get("ev_pct"),
        "rsi14": pick.get("rsi14"),
        "ret5": pick.get("ret5"),
        "hv30": pick.get("iv_pct"),
        "market_regime": pick.get("market_regime"),
        "spy_ret5": pick.get("spy_ret5"),
        "sector": pick.get("sector"),
        "signal_reasons": pick.get("signal_reasons"),
        "quote_time_et": pick.get("quote_time_et"),
        "quote_time_utc": pick.get("quote_time_utc"),
        "quote_basis": pick.get("quote_basis"),
        "quote_freshness_status": pick.get("quote_freshness_status"),
        "selection_source": pick.get("selection_source"),
        "promotion_class": pick.get("promotion_class"),
        "approximation_only": pick.get("approximation_only"),
        "comparable_contract": pick.get("comparable_contract"),
        "comparable_contract_basis": pick.get("comparable_contract_basis"),
        "comparable_contract_label": pick.get("comparable_contract_label"),
        "resolution_notes": pick.get("resolution_notes"),
        "entry_quote_snapshot": pick.get("entry_quote_snapshot"),
        "stop_loss_pct": pick.get("stop_loss_pct"),
        "profit_target_pct": pick.get("profit_target_pct"),
        "time_exit_pct": pick.get("time_exit_pct"),
        "time_exit_day": pick.get("time_exit_day"),
        # For tracking outcome later
        "outcome": None,
        "exit_date": None,
        "exit_price": None,
        "pnl_pct": None,
    }


def main():
    load_local_env(ROOT)

    import market_data_service as mds
    mds._MEMORY_CACHE.clear()
    import options_chatbot as oc

    run_at = datetime.now()
    scan_date = run_at.strftime("%Y-%m-%d")
    picks = list(oc.scan_daily_top_trades(n_picks=10) or [])
    if not picks:
        print("No picks today.")
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    repository = create_positions_repository(os.getenv("DATABASE_URL"))

    logged = 0
    for pick in picks:
        record = _build_log_record(pick, run_at=run_at)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logged += 1
        print(
            f"  Logged: {record['ticker']} {record['direction']} "
            f"{record['long_strike']}/{record['short_strike']} "
            f"${(record.get('net_debit') or record.get('entry_execution_price') or 0.0):.2f} exp={record['expiry']}"
        )

    print(f"\n{logged} picks logged to {LOG_FILE}")

    if getattr(repository, "is_available", False):
        if _is_weekend(run_at):
            print("Weekend run detected; auto-track skipped so no tracked positions get a non-tradable weekend fill timestamp.")
        else:
            created, duplicates, skipped = _auto_track_scan_picks(
                repository=repository,
                picks=picks,
                filled_at=run_at.isoformat(),
                scan_date=scan_date,
            )
            print(
                f"Auto-track summary: created={created}, duplicate_open={duplicates}, skipped={skipped}"
            )
        try:
            reviewed_positions = review_open_positions(repository)
            expired_auto_closed = sum(
                1
                for position in reviewed_positions
                if position.get("status") == "closed" and position.get("exit_reason") == "expired_auto_close"
            )
            print(
                f"Open position review summary: reviewed={len(reviewed_positions)}, expired_auto_closed={expired_auto_closed}"
            )
        except Exception as exc:
            print(f"Open position review failed: {exc}")
    else:
        print("Tracked positions repository unavailable; auto-track skipped.")


if __name__ == "__main__":
    main()
