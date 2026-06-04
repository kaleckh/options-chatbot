from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Callable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from historical_options_store import HistoricalOptionsStore
from local_env import load_local_env
from options_execution import commission_total_usd, option_pnl_snapshot
from positions_repository import create_positions_repository
from us_equity_market_calendar import is_us_equity_market_day

from scripts.migrate_main_lane_backfills_to_positions import (
    DEFAULT_HISTORICAL_OPTIONS_DB,
    _parse_date,
    _safe_float,
    _source_snapshot,
    _spread_exit_snapshot,
)


ET = ZoneInfo("America/New_York")
REPORT_ID = "current_policy_historical_stop_grid"
DEFAULT_CURRENT_POLICY_REPORT = ROOT / "data" / "forward-tracking" / "current_policy_historical_picks_latest.json"
DEFAULT_REGULAR_MULTILANE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "current-policy-historical-stop-grid.md"
DEFAULT_SOURCE_LABELS = ["thetadata_opra_nbbo_1m"]
DEFAULT_STOP_GRID = (50.0, 60.0, 70.0, 80.0, 90.0)
LOSS_BUCKET_THRESHOLDS = (50, 70, 80, 90, 95, 99)
PROFIT_HARVEST_LANES = {
    "bullish_pullback_observation",
    "tracked_winner_primary",
    "tracked_winner_observation",
}

SnapshotFunc = Callable[..., dict[str, Any]]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _close_datetime(close_date: date) -> datetime:
    return datetime.combine(close_date, time(15, 55), tzinfo=ET)


def _split_csv(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return list(default)
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _split_float_grid(value: str | None, default: tuple[float, ...] = DEFAULT_STOP_GRID) -> list[float]:
    raw_items = _split_csv(value, tuple(str(item) for item in default))
    parsed = sorted({round(abs(float(item)), 4) for item in raw_items if str(item).strip()})
    if not parsed:
        raise ValueError("At least one stop value is required.")
    return parsed


def _market_days(start: date, end: date):
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            yield current
        current += timedelta(days=1)


def _fee_sides(source_pick: dict[str, Any]) -> int:
    return 2 if str(source_pick.get("strategy_type") or "").lower() == "vertical_spread" else 1


def _profit_harvest_enabled(source_pick: dict[str, Any]) -> bool:
    lane = str(source_pick.get("cohort_id") or source_pick.get("playbook_id") or "").strip().lower()
    return lane in PROFIT_HARVEST_LANES


def _candidate_sell_reason(
    *,
    position: dict[str, Any],
    source_pick: dict[str, Any],
    review_date: date,
    entry_date: date,
    gross_pnl_pct: float,
    peak_pnl_pct: float,
    stop_loss_pct: float,
) -> str | None:
    days_held = max((review_date - entry_date).days, 0)
    profit_target_pct = _safe_float(position.get("profit_target_pct"))
    profit_target_pct = profit_target_pct if profit_target_pct is not None else 100.0
    time_exit_day = int(float(position.get("time_exit_day") or 1))

    if gross_pnl_pct <= -abs(float(stop_loss_pct)):
        return "stop_loss"
    if gross_pnl_pct >= profit_target_pct:
        return "profit_target"
    if _profit_harvest_enabled(source_pick) and days_held >= 1 and gross_pnl_pct >= 50.0:
        return "profit_harvest"
    if (
        _profit_harvest_enabled(source_pick)
        and days_held >= 1
        and peak_pnl_pct >= 50.0
        and peak_pnl_pct - gross_pnl_pct >= 20.0
        and gross_pnl_pct >= 15.0
    ):
        return "profit_harvest_giveback"
    if days_held >= time_exit_day:
        return "time_exit"
    return None


def _pct(value: Any, digits: int = 2) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:+.{digits}f}%"


def _plain_pct(value: Any, digits: int = 1) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:.{digits}f}%"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 4) if values else None


def _loss_bucket_counts(values: list[float]) -> dict[str, int]:
    return {
        f"loss_le_{threshold}_pct": sum(1 for value in values if value <= -float(threshold))
        for threshold in LOSS_BUCKET_THRESHOLDS
    }


def _pnl_summary(values: list[float]) -> dict[str, Any]:
    winners = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    summary = {
        "count": len(values),
        "avg_pnl_pct": _mean(values),
        "median_pnl_pct": _median(values),
        "positive_or_flat_count": len(values) - len(losses),
        "negative_count": len(losses),
        "positive_count": len(winners),
        "negative_rate_pct": round(len(losses) / len(values) * 100.0, 4) if values else None,
        "min_pnl_pct": round(min(values), 4) if values else None,
        "max_pnl_pct": round(max(values), 4) if values else None,
    }
    summary["loss_bucket_counts"] = _loss_bucket_counts(values)
    return summary


def _top_counts(rows: list[dict[str, Any]], key: str, limit: int = 10) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "unknown") for row in rows)
    return dict(counts.most_common(limit))


def _ticker_key(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or "unknown").strip().upper() or "unknown"


def _trade_direction(row: dict[str, Any]) -> str:
    raw = str(row.get("type") or row.get("direction") or "").strip().lower()
    return raw if raw in {"call", "put"} else "unknown"


def _trade_key(row: dict[str, Any]) -> str:
    entry_date = str(row.get("date") or row.get("entry_date") or "").strip()
    return "|".join([entry_date, _ticker_key(row), _trade_direction(row)])


def _coverage_by_ticker(
    scoped_rows: list[dict[str, Any]],
    replayed_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    scoped_counts = Counter(_ticker_key(row) for row in scoped_rows)
    replayed_counts = Counter(_ticker_key(row) for row in replayed_rows)
    unresolved_counts = Counter(_ticker_key(row) for row in unresolved_rows)
    unresolved_reasons_by_ticker: dict[str, Counter] = {}
    for row in unresolved_rows:
        ticker = _ticker_key(row)
        unresolved_reasons_by_ticker.setdefault(ticker, Counter())[str(row.get("reason") or "unknown")] += 1

    by_ticker = [
        {
            "ticker": ticker,
            "scoped_count": int(scoped_counts.get(ticker, 0)),
            "replayed_count": int(replayed_counts.get(ticker, 0)),
            "unresolved_count": int(unresolved_counts.get(ticker, 0)),
            "unresolved_reasons": dict(unresolved_reasons_by_ticker.get(ticker, Counter())),
        }
        for ticker in sorted(set(scoped_counts) | set(replayed_counts) | set(unresolved_counts))
    ]
    unresolved_tickers = [row for row in by_ticker if int(row.get("unresolved_count") or 0) > 0]
    return {
        "ticker_count": len(by_ticker),
        "all_tickers_resolved": len(unresolved_tickers) == 0,
        "unresolved_ticker_count": len(unresolved_tickers),
        "unresolved_tickers": unresolved_tickers,
        "by_ticker": by_ticker,
    }


def _repository_path(path_value: Any) -> Path:
    text = str(path_value or "").strip().replace("\\", "/")
    path = Path(text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _occ_expiry_from_contract_symbol(contract_symbol: Any) -> date | None:
    text = str(contract_symbol or "").strip().upper()
    for index in range(max(len(text) - 14, 0)):
        chunk = text[index : index + 6]
        if not chunk.isdigit():
            continue
        marker_index = index + 6
        if marker_index >= len(text) or text[marker_index] not in {"C", "P"}:
            continue
        try:
            return date(2000 + int(chunk[0:2]), int(chunk[2:4]), int(chunk[4:6]))
        except ValueError:
            continue
    return None


def _annual_replay_match_index(multilane_report: dict[str, Any]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    source_paths = {
        str(row.get("source_result_path") or "")
        for row in multilane_report.get("selected_trades") or []
        if str(row.get("source_result_path") or "").strip()
    }
    index: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for source_path in sorted(source_paths):
        path = _repository_path(source_path)
        if not path.exists():
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        source_key = str(path.resolve()).lower()
        for trade in run.get("trades") or []:
            long_symbol = str(trade.get("contract_symbol") or trade.get("long_contract_symbol") or "").strip().upper()
            short_symbol = str(trade.get("short_contract_symbol") or "").strip().upper()
            exit_date = str(trade.get("exit_date") or "").strip()
            key = (source_key, _trade_key(trade), long_symbol, short_symbol, exit_date)
            index.setdefault(key, trade)
    return index


def _annual_replay_position_and_row(
    selected_trade: dict[str, Any],
    source_trade: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ticker = _ticker_key(selected_trade)
    entry_date = _parse_date(source_trade.get("date") or selected_trade.get("entry_date"))
    exit_date = _parse_date(source_trade.get("exit_date") or selected_trade.get("exit_date"))
    long_symbol = str(
        selected_trade.get("long_contract_symbol")
        or source_trade.get("contract_symbol")
        or source_trade.get("long_contract_symbol")
        or ""
    ).strip().upper()
    short_symbol = str(selected_trade.get("short_contract_symbol") or source_trade.get("short_contract_symbol") or "").strip().upper()
    expiry = _occ_expiry_from_contract_symbol(long_symbol) or _parse_date(source_trade.get("target_expiry") or exit_date)
    entry_execution_price = (
        _safe_float(source_trade.get("entry_px"))
        or _safe_float(source_trade.get("net_debit"))
        or _safe_float(selected_trade.get("entry_px"))
        or _safe_float(selected_trade.get("net_debit"))
    )
    if entry_execution_price is None or entry_execution_price <= 0:
        raise ValueError("annual replay row is missing a positive entry execution price")
    if not long_symbol or not short_symbol:
        raise ValueError("annual replay row is missing one or both spread contract symbols")

    source_snapshot = dict(source_trade)
    source_snapshot.update(
        {
            "playbook_id": selected_trade.get("lane_family") or selected_trade.get("lane_id"),
            "cohort_id": selected_trade.get("lane_id"),
            "contract_symbol": long_symbol,
            "short_contract_symbol": short_symbol,
            "strategy_type": source_trade.get("strategy_type") or selected_trade.get("strategy_type") or "vertical_spread",
            "pricing_evidence_class": "annual_replay_exact",
            "source_result_path": selected_trade.get("source_result_path"),
        }
    )
    trade_id = (
        "annual_replay:"
        + str(selected_trade.get("lane_id") or "unknown")
        + ":"
        + str(selected_trade.get("dedupe_key") or _trade_key(selected_trade)).replace("|", ":")
    )
    position = {
        "id": trade_id,
        "ticker": ticker,
        "status": "closed",
        "filled_at": datetime.combine(entry_date, time(10, 10), tzinfo=ET).isoformat(),
        "closed_at": _close_datetime(exit_date).isoformat(),
        "expiry": expiry.isoformat(),
        "entry_execution_price": entry_execution_price,
        "entry_fee_total_usd": _safe_float(source_trade.get("entry_fee_total_usd")),
        "contracts": 1,
        "profit_target_pct": _safe_float(source_trade.get("profit_target_pct")) or 150.0,
        "time_exit_day": int(float(source_trade.get("time_exit_day") or 1)),
        "source_pick_snapshot": source_snapshot,
        "gross_pnl_pct": _safe_float(source_trade.get("gross_pnl_pct")),
    }
    row = {
        "trade_id": trade_id,
        "ticker": ticker,
        "lane": selected_trade.get("lane_id") or selected_trade.get("lane_family"),
        "closed_at": exit_date.isoformat(),
        "current_policy_decision": "would_take_today",
        "has_realized_pnl": True,
        "pnl_pct": _safe_float(selected_trade.get("pnl_pct") or source_trade.get("net_pnl_pct") or source_trade.get("pnl_pct")),
        "evidence_group": "annual_replay_exact",
        "symbol_sleeve_status": None,
        "symbol_sleeve_evidence_class": "trusted_intraday_opra_nbbo",
        "source_result_path": selected_trade.get("source_result_path"),
    }
    return position, row


def _leg_spread_pct(bid: Any, ask: Any) -> float | None:
    bid_value = _safe_float(bid)
    ask_value = _safe_float(ask)
    if bid_value is None or ask_value is None or ask_value < bid_value:
        return None
    midpoint = (bid_value + ask_value) / 2.0
    if midpoint <= 0:
        return None
    return round((ask_value - bid_value) / midpoint * 100.0, 4)


def _entry_signal_snapshot(position: dict[str, Any], source_pick: dict[str, Any]) -> dict[str, Any]:
    liquidity = source_pick.get("spread_liquidity") if isinstance(source_pick.get("spread_liquidity"), dict) else {}
    entry_debit = (
        _safe_float(position.get("entry_execution_price"))
        or _safe_float(source_pick.get("entry_execution_price"))
        or _safe_float(source_pick.get("spread_entry_debit"))
        or _safe_float(source_pick.get("net_debit"))
    )
    spread_mid = (
        _safe_float(liquidity.get("spread_mid_debit"))
        or _safe_float(source_pick.get("spread_mid_debit"))
        or _safe_float(source_pick.get("mid"))
    )
    fill_degradation_pct = None
    if entry_debit is not None and spread_mid is not None and spread_mid > 0:
        fill_degradation_pct = round((entry_debit - spread_mid) / spread_mid * 100.0, 4)

    long_spread = _leg_spread_pct(liquidity.get("long_bid"), liquidity.get("long_ask"))
    short_spread = _leg_spread_pct(liquidity.get("short_bid"), liquidity.get("short_ask"))
    leg_spreads = [value for value in (long_spread, short_spread) if value is not None]
    worst_leg_bid_ask_pct = round(max(leg_spreads), 4) if leg_spreads else None

    return {
        "market_regime": source_pick.get("market_regime"),
        "quality_score": _safe_float(source_pick.get("quality_score")),
        "direction_score": _safe_float(source_pick.get("direction_score")),
        "candidate_rank": source_pick.get("candidate_rank"),
        "ret5": _safe_float(source_pick.get("ret5")),
        "spy_ret5": _safe_float(source_pick.get("spy_ret5")),
        "hv30": _safe_float(source_pick.get("hv30")),
        "rsi14": _safe_float(source_pick.get("rsi14")),
        "dte": source_pick.get("dte"),
        "debit_pct_of_width": _safe_float(source_pick.get("debit_pct_of_width")),
        "fill_degradation_pct": fill_degradation_pct,
        "worst_leg_bid_ask_pct": worst_leg_bid_ask_pct,
        "entry_execution_basis": position.get("entry_execution_basis") or source_pick.get("entry_execution_basis"),
        "pricing_evidence_class": source_pick.get("pricing_evidence_class") or source_pick.get("promotion_class"),
        "source_scan_run_id": source_pick.get("source_scan_run_id"),
    }


def _classify_stop_result(*, baseline_pnl_pct: float | None, stop_result: dict[str, Any]) -> str:
    if not stop_result.get("triggered"):
        return "no_stop_trigger"
    stop_pnl = _safe_float(stop_result.get("pnl_pct"))
    if baseline_pnl_pct is None or stop_pnl is None:
        return "triggered_without_baseline"
    if baseline_pnl_pct > 0 and stop_pnl < 0:
        return "winner_flipped_to_loss"
    if baseline_pnl_pct > 0 and stop_pnl < baseline_pnl_pct:
        return "winner_harvested_too_early"
    if baseline_pnl_pct < 0 and stop_pnl > baseline_pnl_pct:
        if baseline_pnl_pct <= -90.0 and stop_pnl <= -90.0:
            return "near_total_trimmed_but_not_saved"
        if baseline_pnl_pct <= -50.0:
            return "deep_loss_reduced"
        return "loss_reduced"
    if stop_pnl < baseline_pnl_pct:
        return "stop_worse_than_baseline"
    return "same_as_baseline"


def _stop_quality(
    *,
    stop_loss_pct: float,
    entry_date: date,
    first_priced_point: dict[str, Any] | None,
    stop_result: dict[str, Any],
) -> str:
    if not stop_result.get("triggered"):
        return "no_stop_trigger"
    trigger_date = str(stop_result.get("trigger_date") or "")
    if first_priced_point:
        first_date = str(first_priced_point.get("review_date") or "")
        first_gross = _safe_float(first_priced_point.get("gross_pnl_pct"))
        if first_date == trigger_date and first_gross is not None and first_gross <= -abs(float(stop_loss_pct)):
            if first_date == entry_date.isoformat():
                return "same_day_close_already_through_stop"
            return "first_priced_close_already_through_stop"
    if int(stop_result.get("unpriced_before_trigger") or 0) > 0:
        return "unpriced_before_stop"
    return "actionable_close_check_stop"


def simulate_position_stop_grid(
    position: dict[str, Any],
    current_policy_row: dict[str, Any],
    *,
    store: HistoricalOptionsStore | None,
    source_labels: list[str],
    pricing_lane: str,
    trusted_only: bool,
    as_of: date,
    stop_grid: list[float],
    snapshot_func: SnapshotFunc = _spread_exit_snapshot,
) -> dict[str, Any]:
    source_pick = _source_snapshot(position.get("source_pick_snapshot"))
    baseline_pnl_pct = _safe_float(current_policy_row.get("pnl_pct"))
    entry_date = _parse_date(position.get("filled_at"))
    expiry_date = _parse_date(position.get("expiry"))
    close_source = position.get("closed_at") or current_policy_row.get("closed_at") or as_of.isoformat()
    baseline_close_date = min(_parse_date(close_source), expiry_date, as_of)
    if baseline_close_date < entry_date:
        return {
            "status": "skipped",
            "reason": "baseline_close_before_entry",
            "position_id": position.get("id"),
            "ticker": position.get("ticker"),
        }

    entry_execution_price = _safe_float(position.get("entry_execution_price") or position.get("entry_option_price"))
    if entry_execution_price is None or entry_execution_price <= 0:
        return {
            "status": "skipped",
            "reason": "missing_entry_execution_price",
            "position_id": position.get("id"),
            "ticker": position.get("ticker"),
        }

    contracts = max(int(position.get("contracts") or 1), 1)
    fee_sides = _fee_sides(source_pick)
    entry_fee = _safe_float(position.get("entry_fee_total_usd"))
    if entry_fee is None:
        entry_fee = commission_total_usd(contracts=contracts, sides=fee_sides)
    exit_fee = commission_total_usd(contracts=contracts, sides=fee_sides)

    stop_results: dict[str, dict[str, Any]] = {
        str(int(stop) if float(stop).is_integer() else stop): {
            "stop_loss_pct": stop,
            "triggered": False,
            "pnl_pct": baseline_pnl_pct,
            "gross_pnl_pct": None,
            "delta_vs_baseline_pct": 0.0 if baseline_pnl_pct is not None else None,
            "classification": "no_stop_trigger",
            "stop_quality": "no_stop_trigger",
        }
        for stop in stop_grid
    }
    triggered_stops: set[str] = set()
    priced_points: list[dict[str, Any]] = []
    first_priced_point: dict[str, Any] | None = None
    first_unpriced_sell: dict[str, Any] | None = None
    peak_pnl_pct = _safe_float(position.get("peak_pnl_pct")) or 0.0
    unpriced_day_count = 0
    priced_day_count = 0

    for review_date in _market_days(entry_date, baseline_close_date):
        days_held = max((review_date - entry_date).days, 0)
        exit_snapshot = snapshot_func(
            source_pick,
            close_date=review_date,
            store=store,
            source_labels=source_labels,
            requested_pricing_lane=pricing_lane,
            trusted_only=trusted_only,
        )
        if not exit_snapshot.get("priced"):
            unpriced_day_count += 1
            time_exit_day = int(float(position.get("time_exit_day") or 1))
            if days_held >= time_exit_day and first_unpriced_sell is None:
                first_unpriced_sell = {
                    "review_date": review_date.isoformat(),
                    "unpriced_reason": exit_snapshot.get("unpriced_reason"),
                    "missing_long_contract_symbol": exit_snapshot.get("missing_long_contract_symbol"),
                    "missing_short_contract_symbol": exit_snapshot.get("missing_short_contract_symbol"),
                }
            continue

        priced_day_count += 1
        exit_price = float(exit_snapshot["exit_price"])
        pnl = option_pnl_snapshot(
            entry_execution_price=entry_execution_price,
            exit_execution_price=exit_price,
            contracts=contracts,
            entry_fee_total_usd=entry_fee,
            exit_fee_total_usd=exit_fee,
        )
        gross_pnl_pct = _safe_float(pnl.get("gross_pnl_pct"))
        net_pnl_pct = _safe_float(pnl.get("net_pnl_pct"))
        if gross_pnl_pct is None:
            continue
        peak_pnl_pct = round(max(peak_pnl_pct, gross_pnl_pct), 4)
        point = {
            "review_date": review_date.isoformat(),
            "exit_price": round(exit_price, 4),
            "gross_pnl_pct": round(gross_pnl_pct, 4),
            "net_pnl_pct": round(net_pnl_pct, 4) if net_pnl_pct is not None else None,
            "exit_execution_basis": exit_snapshot.get("exit_execution_basis"),
            "unpriced_before": unpriced_day_count,
        }
        priced_points.append(point)
        if first_priced_point is None:
            first_priced_point = point

        for stop in stop_grid:
            key = str(int(stop) if float(stop).is_integer() else stop)
            if key in triggered_stops:
                continue
            reason = _candidate_sell_reason(
                position=position,
                source_pick=source_pick,
                review_date=review_date,
                entry_date=entry_date,
                gross_pnl_pct=gross_pnl_pct,
                peak_pnl_pct=peak_pnl_pct,
                stop_loss_pct=stop,
            )
            if reason != "stop_loss":
                continue
            triggered_stops.add(key)
            final_pnl = net_pnl_pct if net_pnl_pct is not None else gross_pnl_pct
            stop_results[key] = {
                "stop_loss_pct": stop,
                "triggered": True,
                "trigger_date": review_date.isoformat(),
                "closed_at": _close_datetime(review_date).isoformat(),
                "exit_price": round(exit_price, 4),
                "exit_execution_basis": exit_snapshot.get("exit_execution_basis"),
                "pnl_pct": round(final_pnl, 4),
                "gross_pnl_pct": round(gross_pnl_pct, 4),
                "delta_vs_baseline_pct": (
                    round(final_pnl - baseline_pnl_pct, 4) if baseline_pnl_pct is not None else None
                ),
                "priced_day_index": priced_day_count,
                "unpriced_before_trigger": unpriced_day_count,
            }

    for stop in stop_grid:
        key = str(int(stop) if float(stop).is_integer() else stop)
        stop_results[key]["classification"] = _classify_stop_result(
            baseline_pnl_pct=baseline_pnl_pct,
            stop_result=stop_results[key],
        )
        stop_results[key]["stop_quality"] = _stop_quality(
            stop_loss_pct=stop,
            entry_date=entry_date,
            first_priced_point=first_priced_point,
            stop_result=stop_results[key],
        )

    source_lane = str(source_pick.get("playbook_id") or source_pick.get("cohort_id") or current_policy_row.get("lane") or "")
    return {
        "status": "replayed" if priced_day_count else "unpriced",
        "position_id": position.get("id"),
        "trade_id": current_policy_row.get("trade_id"),
        "ticker": position.get("ticker") or current_policy_row.get("ticker"),
        "lane": source_lane or current_policy_row.get("lane"),
        "entry_date": entry_date.isoformat(),
        "baseline_close_date": baseline_close_date.isoformat(),
        "baseline_pnl_pct": baseline_pnl_pct,
        "baseline_gross_pnl_pct": _safe_float(position.get("gross_pnl_pct")),
        "evidence_group": current_policy_row.get("evidence_group"),
        "symbol_sleeve_status": current_policy_row.get("symbol_sleeve_status"),
        "symbol_sleeve_evidence_class": current_policy_row.get("symbol_sleeve_evidence_class"),
        "entry_execution_price": entry_execution_price,
        "contract_symbol": source_pick.get("contract_symbol") or position.get("contract_symbol"),
        "short_contract_symbol": source_pick.get("short_contract_symbol") or position.get("short_contract_symbol"),
        "priced_day_count": priced_day_count,
        "unpriced_day_count": unpriced_day_count,
        "first_unpriced_sell": first_unpriced_sell,
        "first_priced_point": first_priced_point,
        "last_priced_point": priced_points[-1] if priced_points else None,
        "entry_signals": _entry_signal_snapshot(position, source_pick),
        "stop_results": stop_results,
    }


def _current_policy_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in report.get("rows") or []
        if str(row.get("current_policy_decision") or "") == "would_take_today"
        and row.get("has_realized_pnl")
        and _safe_float(row.get("pnl_pct")) is not None
    ]


def _policy_values(rows: list[dict[str, Any]], stop_key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        result = (row.get("stop_results") or {}).get(stop_key) or {}
        value = _safe_float(result.get("pnl_pct"))
        if value is not None:
            values.append(value)
    return values


def _summarize_stop_policy(rows: list[dict[str, Any]], stop_key: str) -> dict[str, Any]:
    values = _policy_values(rows, stop_key)
    triggered = [row for row in rows if ((row.get("stop_results") or {}).get(stop_key) or {}).get("triggered")]
    baseline_values = [_safe_float(row.get("baseline_pnl_pct")) for row in rows]
    baseline_values = [value for value in baseline_values if value is not None]
    deltas = [
        _safe_float(((row.get("stop_results") or {}).get(stop_key) or {}).get("delta_vs_baseline_pct"))
        for row in rows
    ]
    deltas = [value for value in deltas if value is not None]
    classifications = Counter(
        str(((row.get("stop_results") or {}).get(stop_key) or {}).get("classification") or "unknown")
        for row in rows
    )
    stop_quality = Counter(
        str(((row.get("stop_results") or {}).get(stop_key) or {}).get("stop_quality") or "unknown")
        for row in rows
    )
    summary = _pnl_summary(values)
    summary.update(
        {
            "stop_key": stop_key,
            "triggered_count": len(triggered),
            "triggered_rate_pct": round(len(triggered) / len(rows) * 100.0, 4) if rows else None,
            "avg_delta_vs_baseline_pct": _mean(deltas),
            "median_delta_vs_baseline_pct": _median(deltas),
            "loss_reduced_count": int(
                classifications.get("loss_reduced", 0)
                + classifications.get("deep_loss_reduced", 0)
                + classifications.get("near_total_trimmed_but_not_saved", 0)
            ),
            "deep_loss_reduced_count": int(classifications.get("deep_loss_reduced", 0)),
            "near_total_trimmed_count": int(classifications.get("near_total_trimmed_but_not_saved", 0)),
            "winner_flip_count": int(classifications.get("winner_flipped_to_loss", 0)),
            "winner_harmed_count": int(
                classifications.get("winner_flipped_to_loss", 0)
                + classifications.get("winner_harvested_too_early", 0)
            ),
            "first_priced_already_through_stop_count": int(
                stop_quality.get("first_priced_close_already_through_stop", 0)
                + stop_quality.get("same_day_close_already_through_stop", 0)
            ),
            "unpriced_before_stop_count": int(stop_quality.get("unpriced_before_stop", 0)),
            "classification_counts": dict(classifications),
            "stop_quality_counts": dict(stop_quality),
            "loss_bucket_delta_vs_baseline": {
                key: int(summary["loss_bucket_counts"].get(key, 0) - _loss_bucket_counts(baseline_values).get(key, 0))
                for key in _loss_bucket_counts(values)
            },
        }
    )
    return summary


def _focus_loss_summary(rows: list[dict[str, Any]], *, loss_threshold_pct: float) -> dict[str, Any]:
    focus_rows = [
        row
        for row in rows
        if (baseline := _safe_float(row.get("baseline_pnl_pct"))) is not None
        and baseline <= -abs(float(loss_threshold_pct))
    ]
    entry_signals = [row.get("entry_signals") or {} for row in focus_rows]
    high_fill = [
        signal for signal in entry_signals if (_safe_float(signal.get("fill_degradation_pct")) or 0.0) >= 15.0
    ]
    high_debit = [
        signal for signal in entry_signals if (_safe_float(signal.get("debit_pct_of_width")) or 0.0) >= 45.0
    ]
    wide_leg = [
        signal for signal in entry_signals if (_safe_float(signal.get("worst_leg_bid_ask_pct")) or 0.0) >= 20.0
    ]
    low_quality = [
        signal
        for signal in entry_signals
        if (quality := _safe_float(signal.get("quality_score"))) is not None and quality < 60.0
    ]
    return {
        "loss_threshold_pct": -abs(float(loss_threshold_pct)),
        "count": len(focus_rows),
        "summary": _pnl_summary([float(row["baseline_pnl_pct"]) for row in focus_rows]),
        "lane_counts": _top_counts(focus_rows, "lane"),
        "ticker_counts": _top_counts(focus_rows, "ticker"),
        "evidence_group_counts": _top_counts(focus_rows, "evidence_group"),
        "market_regime_counts": dict(Counter(str(signal.get("market_regime") or "unknown") for signal in entry_signals)),
        "high_fill_degradation_15_pct_count": len(high_fill),
        "high_debit_45_pct_width_count": len(high_debit),
        "worst_leg_spread_20_pct_count": len(wide_leg),
        "quality_below_60_count": len(low_quality),
    }


def _decision_summary(report: dict[str, Any]) -> dict[str, Any]:
    baseline = report.get("baseline") or {}
    baseline_buckets = baseline.get("loss_bucket_counts") or {}
    baseline_negative = int(baseline.get("negative_count") or 0)
    baseline_near_total = int(baseline_buckets.get("loss_le_90_pct") or 0)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for stop_key, policy in (report.get("stop_policies") or {}).items():
        policy_buckets = policy.get("loss_bucket_counts") or {}
        near_total_delta = baseline_near_total - int(policy_buckets.get("loss_le_90_pct") or 0)
        candidate = {
            "stop_key": stop_key,
            "avg_delta_vs_baseline_pct": policy.get("avg_delta_vs_baseline_pct"),
            "negative_count": policy.get("negative_count"),
            "winner_flip_count": policy.get("winner_flip_count"),
            "near_total_reduction_count": near_total_delta,
            "triggered_count": policy.get("triggered_count"),
        }
        avg_delta = _safe_float(policy.get("avg_delta_vs_baseline_pct")) or 0.0
        if (
            int(policy.get("winner_flip_count") or 0) == 0
            and int(policy.get("negative_count") or 0) <= baseline_negative
            and avg_delta >= 0.0
            and near_total_delta >= 0
        ):
            candidates.append(candidate)
        else:
            rejected.append(candidate)

    candidates.sort(
        key=lambda item: (
            int(item.get("near_total_reduction_count") or 0),
            float(item.get("avg_delta_vs_baseline_pct") or 0.0),
            -int(item.get("negative_count") or 0),
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    focus = report.get("focus_loss_summary") or {}
    return {
        "status": "daily_close_research_candidate" if best else "no_stop_candidate",
        "best_non_destructive_stop": best,
        "rejected_stop_shapes": rejected,
        "recommended_next_action": (
            "Keep live stops unchanged for now. Treat the best non-destructive daily close-check stop as "
            "a research candidate, then test minute-by-minute OPRA/NBBO stops and entry avoidance filters "
            "before promotion."
            if best
            else "Keep live stops unchanged and prioritize entry avoidance filters before any tighter stop."
        ),
        "entry_filter_hypotheses": [
            "short_term deep-loss concentration",
            "fill_degradation_pct >= 15 on loss-cohort entries",
            "quality_score < 60 on loss-cohort entries",
            "repeat ticker cooldown for TSLA/MSTR/QQQ-style clusters",
        ],
        "focus_loss_counts": {
            "loss_count": focus.get("count"),
            "short_term_count": (focus.get("lane_counts") or {}).get("short_term", 0),
            "high_fill_degradation_15_pct_count": focus.get("high_fill_degradation_15_pct_count"),
            "quality_below_60_count": focus.get("quality_below_60_count"),
        },
    }


def build_report(
    *,
    current_policy_report: dict[str, Any],
    positions: list[dict[str, Any]],
    store: HistoricalOptionsStore,
    source_labels: list[str],
    pricing_lane: str,
    trusted_only: bool,
    as_of: date,
    stop_grid: list[float],
    loss_threshold_pct: float,
) -> dict[str, Any]:
    rows = _current_policy_rows(current_policy_report)
    positions_by_id = {int(position["id"]): position for position in positions if position.get("id") is not None}
    replayed_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    for row in rows:
        try:
            position_id = int(row.get("trade_id"))
        except (TypeError, ValueError):
            unresolved_rows.append({"trade_id": row.get("trade_id"), "ticker": row.get("ticker"), "reason": "missing_trade_id"})
            continue
        position = positions_by_id.get(position_id)
        if position is None:
            unresolved_rows.append({"trade_id": position_id, "ticker": row.get("ticker"), "reason": "position_not_found"})
            continue
        result = simulate_position_stop_grid(
            position,
            row,
            store=store,
            source_labels=source_labels,
            pricing_lane=pricing_lane,
            trusted_only=trusted_only,
            as_of=as_of,
            stop_grid=stop_grid,
        )
        if result.get("status") == "replayed":
            replayed_rows.append(result)
        else:
            unresolved_rows.append(
                {
                    "trade_id": position_id,
                    "ticker": row.get("ticker"),
                    "lane": row.get("lane"),
                    "reason": result.get("reason") or result.get("status"),
                    "priced_day_count": result.get("priced_day_count"),
                    "unpriced_day_count": result.get("unpriced_day_count"),
                }
            )

    baseline_values = [
        value
        for row in replayed_rows
        if (value := _safe_float(row.get("baseline_pnl_pct"))) is not None
    ]
    stop_summaries = {
        str(int(stop) if float(stop).is_integer() else stop): _summarize_stop_policy(
            replayed_rows,
            str(int(stop) if float(stop).is_integer() else stop),
        )
        for stop in stop_grid
    }
    focus_rows = [
        row
        for row in replayed_rows
        if (baseline := _safe_float(row.get("baseline_pnl_pct"))) is not None
        and baseline <= -abs(float(loss_threshold_pct))
    ]
    worst_examples = sorted(focus_rows, key=lambda item: float(item.get("baseline_pnl_pct") or 0.0))[:25]
    ticker_coverage = _coverage_by_ticker(rows, replayed_rows, unresolved_rows)

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_current_policy_historical_stop_grid",
        "evidence_boundary": {
            "description": (
                "Read-only exact-contract OPRA/NBBO daily close-check replay. It uses trusted historical "
                "spread exit snapshots through the historical options store and does not mutate tracked positions."
            ),
            "not_claimed": "This is not yet a minute-by-minute intraday stop simulation.",
        },
        "inputs": {
            "current_policy_rows": len(rows),
            "position_count": len(positions),
            "as_of_date": as_of.isoformat(),
            "source_labels": source_labels,
            "pricing_lane": pricing_lane,
            "trusted_only": bool(trusted_only),
            "stop_grid": stop_grid,
            "loss_threshold_pct": -abs(float(loss_threshold_pct)),
        },
        "coverage": {
            "replayed_count": len(replayed_rows),
            "unresolved_count": len(unresolved_rows),
            "unresolved_reasons": dict(Counter(str(row.get("reason") or "unknown") for row in unresolved_rows)),
            **ticker_coverage,
        },
        "baseline": _pnl_summary(baseline_values),
        "stop_policies": stop_summaries,
        "focus_loss_summary": _focus_loss_summary(replayed_rows, loss_threshold_pct=loss_threshold_pct),
        "worst_loss_examples": worst_examples,
        "unresolved_examples": unresolved_rows[:50],
        "rows": replayed_rows,
    }
    report["decision_summary"] = _decision_summary(report)
    return report


def build_annual_replay_cohort(
    *,
    regular_multilane_report: dict[str, Any],
    store: HistoricalOptionsStore,
    source_labels: list[str],
    pricing_lane: str,
    trusted_only: bool,
    as_of: date,
    stop_grid: list[float],
    loss_threshold_pct: float,
    report_path: Path,
) -> dict[str, Any]:
    match_index = _annual_replay_match_index(regular_multilane_report)
    replayed_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    scoped_rows: list[dict[str, Any]] = []
    entry_dates: list[str] = []
    exit_dates: list[str] = []

    selected = [
        row
        for row in regular_multilane_report.get("selected_trades") or []
        if row.get("exact_priced")
        and row.get("priced")
        and str(row.get("proof_grade") or "") == "trusted_intraday_opra_nbbo"
    ]

    for selected_trade in selected:
        source_path = _repository_path(selected_trade.get("source_result_path"))
        key = (
            str(source_path.resolve()).lower(),
            _trade_key(selected_trade),
            str(selected_trade.get("long_contract_symbol") or "").strip().upper(),
            str(selected_trade.get("short_contract_symbol") or "").strip().upper(),
            str(selected_trade.get("exit_date") or "").strip(),
        )
        source_trade = match_index.get(key)
        if source_trade is None:
            unresolved_rows.append(
                {
                    "trade_id": selected_trade.get("dedupe_key"),
                    "ticker": selected_trade.get("ticker"),
                    "lane": selected_trade.get("lane_id"),
                    "reason": "source_trade_not_found",
                    "source_result_path": selected_trade.get("source_result_path"),
                }
            )
            scoped_rows.append(
                {
                    "trade_id": selected_trade.get("dedupe_key"),
                    "ticker": selected_trade.get("ticker"),
                    "lane": selected_trade.get("lane_id"),
                }
            )
            continue

        try:
            position, row = _annual_replay_position_and_row(selected_trade, source_trade)
        except Exception as exc:
            unresolved_rows.append(
                {
                    "trade_id": selected_trade.get("dedupe_key"),
                    "ticker": selected_trade.get("ticker"),
                    "lane": selected_trade.get("lane_id"),
                    "reason": f"annual_replay_payload_error:{exc}",
                    "source_result_path": selected_trade.get("source_result_path"),
                }
            )
            scoped_rows.append(
                {
                    "trade_id": selected_trade.get("dedupe_key"),
                    "ticker": selected_trade.get("ticker"),
                    "lane": selected_trade.get("lane_id"),
                }
            )
            continue

        scoped_rows.append(row)
        entry_dates.append(str(source_trade.get("date") or selected_trade.get("entry_date") or ""))
        exit_dates.append(str(source_trade.get("exit_date") or selected_trade.get("exit_date") or ""))
        result = simulate_position_stop_grid(
            position,
            row,
            store=store,
            source_labels=source_labels,
            pricing_lane=pricing_lane,
            trusted_only=trusted_only,
            as_of=as_of,
            stop_grid=stop_grid,
        )
        if result.get("status") == "replayed":
            replayed_rows.append(result)
        else:
            unresolved_rows.append(
                {
                    "trade_id": row.get("trade_id"),
                    "ticker": row.get("ticker"),
                    "lane": row.get("lane"),
                    "reason": result.get("reason") or result.get("status"),
                    "priced_day_count": result.get("priced_day_count"),
                    "unpriced_day_count": result.get("unpriced_day_count"),
                    "source_result_path": selected_trade.get("source_result_path"),
                }
            )

    baseline_values = [
        value
        for row in replayed_rows
        if (value := _safe_float(row.get("baseline_pnl_pct"))) is not None
    ]
    stop_summaries = {
        str(int(stop) if float(stop).is_integer() else stop): _summarize_stop_policy(
            replayed_rows,
            str(int(stop) if float(stop).is_integer() else stop),
        )
        for stop in stop_grid
    }
    focus_rows = [
        row
        for row in replayed_rows
        if (baseline := _safe_float(row.get("baseline_pnl_pct"))) is not None
        and baseline <= -abs(float(loss_threshold_pct))
    ]
    section = {
        "scope": "regular_options_annual_replay_backed_stop_grid",
        "evidence_boundary": {
            "description": (
                "One-year trusted intraday OPRA/NBBO exact replay rows from the regular multi-lane artifact. "
                "These are replay-backed historical paper rows, not live broker fills or Postgres-tracked rows."
            ),
            "not_claimed": "This does not mutate tracked positions and does not make replay rows live-production fills.",
        },
        "inputs": {
            "regular_multilane_report": str(report_path),
            "selected_exact_replay_rows": len(selected),
            "entry_date_min": min([value for value in entry_dates if value], default=None),
            "entry_date_max": max([value for value in entry_dates if value], default=None),
            "exit_date_min": min([value for value in exit_dates if value], default=None),
            "exit_date_max": max([value for value in exit_dates if value], default=None),
            "source_labels": source_labels,
            "pricing_lane": pricing_lane,
            "trusted_only": bool(trusted_only),
            "stop_grid": stop_grid,
        },
        "coverage": {
            "replayed_count": len(replayed_rows),
            "unresolved_count": len(unresolved_rows),
            "unresolved_reasons": dict(Counter(str(row.get("reason") or "unknown") for row in unresolved_rows)),
            **_coverage_by_ticker(scoped_rows, replayed_rows, unresolved_rows),
        },
        "baseline": _pnl_summary(baseline_values),
        "stop_policies": stop_summaries,
        "focus_loss_summary": _focus_loss_summary(replayed_rows, loss_threshold_pct=loss_threshold_pct),
        "worst_loss_examples": sorted(focus_rows, key=lambda item: float(item.get("baseline_pnl_pct") or 0.0))[:25],
        "unresolved_examples": unresolved_rows[:50],
        "rows": replayed_rows,
    }
    section["decision_summary"] = _decision_summary(section)
    return section


def _best_stop_for_row(row: dict[str, Any]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for key, result in (row.get("stop_results") or {}).items():
        pnl = _safe_float(result.get("pnl_pct"))
        if pnl is None:
            continue
        candidate = {**result, "stop_key": key}
        if best is None or pnl > float(best.get("pnl_pct") or -10_000.0):
            best = candidate
    return best or {}


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("coverage") or {}
    annual = report.get("annual_replay_cohort") or {}
    annual_coverage = annual.get("coverage") or {}
    annual_inputs = annual.get("inputs") or {}
    lines: list[str] = [
        "# Current-Policy Historical Stop Grid",
        "",
        (
            "Read-only exact-contract OPRA/NBBO daily close-check replay for current-policy realized rows. "
            "This does not change live stops and does not claim minute-by-minute intraday stop evidence."
        ),
        (
            "The annual replay-backed section is reconstructed from the regular multi-lane exact replay stack; "
            "it is not inserted into the tracked-position store and is not labeled as broker/live tracked fills."
        ),
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Replayed rows: `{coverage['replayed_count']}`",
        f"- Unresolved rows: `{coverage['unresolved_count']}`",
        f"- Tickers with unresolved rows: `{coverage.get('unresolved_ticker_count', 0)}` of `{coverage.get('ticker_count', 0)}`",
        (
            f"- Annual replay-backed rows: `{annual_coverage.get('replayed_count', 0)}` replayed, "
            f"`{annual_coverage.get('unresolved_count', 0)}` unresolved across "
            f"`{annual_coverage.get('ticker_count', 0)}` tickers"
            if annual
            else "- Annual replay-backed rows: `not generated`"
        ),
        f"- Source labels: `{', '.join(report['inputs']['source_labels'])}`",
        f"- Pricing lane: `{report['inputs']['pricing_lane']}`",
        "",
        "## Per-Ticker Coverage",
        "",
        "| Ticker | Rows | Replayed | Unresolved | Reasons |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in coverage.get("by_ticker") or []:
        reasons = row.get("unresolved_reasons") or {}
        lines.append(
            f"| {row.get('ticker')} | {row.get('scoped_count', 0)} | {row.get('replayed_count', 0)} | "
            f"{row.get('unresolved_count', 0)} | {json.dumps(reasons, sort_keys=True)} |"
        )

    lines.extend(
        [
        "",
        "## Annual Replay-Backed Coverage",
        "",
        (
            f"Entry window: `{annual_inputs.get('entry_date_min')}` to `{annual_inputs.get('entry_date_max')}`. "
            f"Exit window: `{annual_inputs.get('exit_date_min')}` to `{annual_inputs.get('exit_date_max')}`."
            if annual
            else "Annual replay-backed cohort was not generated."
        ),
        (
            "These rows are replay-backed exact evidence shaped for the stop-grid audit, not Postgres tracked rows."
            if annual
            else ""
        ),
        "",
        "| Ticker | Rows | Replayed | Unresolved | Reasons |",
        "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in annual_coverage.get("by_ticker") or []:
        reasons = row.get("unresolved_reasons") or {}
        lines.append(
            f"| {row.get('ticker')} | {row.get('scoped_count', 0)} | {row.get('replayed_count', 0)} | "
            f"{row.get('unresolved_count', 0)} | {json.dumps(reasons, sort_keys=True)} |"
        )

    if annual:
        annual_baseline = annual.get("baseline") or {}
        annual_buckets = annual_baseline.get("loss_bucket_counts") or {}
        lines.extend(
            [
                "",
                "### Annual Replay Stop Grid",
                "",
                "| Policy | Rows | Avg | Median | Negatives | <= -50% | <= -70% | <= -80% | <= -90% | Stop hits | Avg delta | Winner flips |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                (
                    "| Baseline | "
                    f"{annual_baseline.get('count', 0)} | {_pct(annual_baseline.get('avg_pnl_pct'))} | "
                    f"{_pct(annual_baseline.get('median_pnl_pct'))} | {annual_baseline.get('negative_count', 0)} | "
                    f"{annual_buckets.get('loss_le_50_pct', 0)} | {annual_buckets.get('loss_le_70_pct', 0)} | "
                    f"{annual_buckets.get('loss_le_80_pct', 0)} | {annual_buckets.get('loss_le_90_pct', 0)} | - | - | - |"
                ),
            ]
        )
        for stop_key, policy in annual.get("stop_policies", {}).items():
            buckets = policy.get("loss_bucket_counts") or {}
            lines.append(
                f"| Stop {stop_key}% | {policy.get('count', 0)} | {_pct(policy.get('avg_pnl_pct'))} | "
                f"{_pct(policy.get('median_pnl_pct'))} | {policy.get('negative_count', 0)} | "
                f"{buckets.get('loss_le_50_pct', 0)} | {buckets.get('loss_le_70_pct', 0)} | "
                f"{buckets.get('loss_le_80_pct', 0)} | {buckets.get('loss_le_90_pct', 0)} | "
                f"{policy.get('triggered_count', 0)} | {_pct(policy.get('avg_delta_vs_baseline_pct'))} | "
                f"{policy.get('winner_flip_count', 0)} |"
            )

    lines.extend(
        [
        "",
        "## Baseline And Stop Grid",
        "",
        "| Policy | Rows | Avg | Median | Negatives | <= -50% | <= -70% | <= -80% | <= -90% | Stop hits | Avg delta | Winner flips | First priced already through stop |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    baseline = report["baseline"]
    baseline_buckets = baseline.get("loss_bucket_counts") or {}
    lines.append(
        "| Baseline | "
        f"{baseline.get('count', 0)} | {_pct(baseline.get('avg_pnl_pct'))} | {_pct(baseline.get('median_pnl_pct'))} | "
        f"{baseline.get('negative_count', 0)} | {baseline_buckets.get('loss_le_50_pct', 0)} | "
        f"{baseline_buckets.get('loss_le_70_pct', 0)} | {baseline_buckets.get('loss_le_80_pct', 0)} | "
        f"{baseline_buckets.get('loss_le_90_pct', 0)} | - | - | - | - |"
    )
    for stop_key, policy in report.get("stop_policies", {}).items():
        buckets = policy.get("loss_bucket_counts") or {}
        lines.append(
            f"| Stop {stop_key}% | {policy.get('count', 0)} | {_pct(policy.get('avg_pnl_pct'))} | "
            f"{_pct(policy.get('median_pnl_pct'))} | {policy.get('negative_count', 0)} | "
            f"{buckets.get('loss_le_50_pct', 0)} | {buckets.get('loss_le_70_pct', 0)} | "
            f"{buckets.get('loss_le_80_pct', 0)} | {buckets.get('loss_le_90_pct', 0)} | "
            f"{policy.get('triggered_count', 0)} | {_pct(policy.get('avg_delta_vs_baseline_pct'))} | "
            f"{policy.get('winner_flip_count', 0)} | {policy.get('first_priced_already_through_stop_count', 0)} |"
        )

    focus = report.get("focus_loss_summary") or {}
    focus_summary = focus.get("summary") or {}
    lines.extend(
        [
            "",
            "## Focus Loss Cohort",
            "",
            (
                f"Rows at or below `{_pct(focus.get('loss_threshold_pct'))}`: `{focus.get('count', 0)}`. "
                f"Average `{_pct(focus_summary.get('avg_pnl_pct'))}`, median `{_pct(focus_summary.get('median_pnl_pct'))}`."
            ),
            "",
            f"- Lane counts: `{json.dumps(focus.get('lane_counts') or {}, sort_keys=True)}`",
            f"- Ticker counts: `{json.dumps(focus.get('ticker_counts') or {}, sort_keys=True)}`",
            f"- Market regimes: `{json.dumps(focus.get('market_regime_counts') or {}, sort_keys=True)}`",
            f"- Fill degradation >= 15%: `{focus.get('high_fill_degradation_15_pct_count', 0)}`",
            f"- Debit >= 45% of width: `{focus.get('high_debit_45_pct_width_count', 0)}`",
            f"- Worst-leg bid/ask >= 20%: `{focus.get('worst_leg_spread_20_pct_count', 0)}`",
            f"- Quality score below 60: `{focus.get('quality_below_60_count', 0)}`",
            "",
            "## Worst Loss Examples",
            "",
            "| ID | Ticker | Lane | Entry | Baseline close | Baseline | Best close-check stop | Best stop P&L | Stop quality | Entry signals |",
            "| ---: | --- | --- | --- | --- | ---: | --- | ---: | --- | --- |",
        ]
    )
    for row in report.get("worst_loss_examples", [])[:15]:
        best = _best_stop_for_row(row)
        signals = row.get("entry_signals") or {}
        signal_text = (
            f"regime={signals.get('market_regime') or 'n/a'}, "
            f"fill={_plain_pct(signals.get('fill_degradation_pct'))}, "
            f"debit_width={_plain_pct(signals.get('debit_pct_of_width'))}, "
            f"worst_spread={_plain_pct(signals.get('worst_leg_bid_ask_pct'))}, "
            f"quality={signals.get('quality_score') if signals.get('quality_score') is not None else 'n/a'}"
        )
        lines.append(
            f"| {row.get('position_id')} | {row.get('ticker')} | {row.get('lane')} | "
            f"{row.get('entry_date')} | {row.get('baseline_close_date')} | {_pct(row.get('baseline_pnl_pct'))} | "
            f"{best.get('stop_key', 'n/a')} | {_pct(best.get('pnl_pct'))} | "
            f"{best.get('stop_quality', 'n/a')} | {signal_text} |"
        )

    unresolved = report.get("coverage", {}).get("unresolved_reasons") or {}
    decision = report.get("decision_summary") or {}
    best_stop = decision.get("best_non_destructive_stop") or {}
    lines.extend(
        [
            "",
            "## Decision Read",
            "",
            f"Status: `{decision.get('status', 'unknown')}`",
            "",
            f"Best non-destructive daily close-check stop: `{best_stop.get('stop_key', 'none')}`",
            "",
            f"Recommended next action: {decision.get('recommended_next_action', 'n/a')}",
            "",
            (
                "Promote a live stop change only if a stop level reduces deep-loss buckets without increasing "
                "negative rows or flipping winners. If the best rows show first-priced or unpriced-before-stop "
                "failures, treat that as an entry/liquidity filter problem rather than a stop-policy win."
            ),
            "",
            f"Unresolved reasons: `{json.dumps(unresolved, sort_keys=True)}`",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stop_keys = list((report.get("stop_policies") or {}).keys())
    for row in report.get("rows") or []:
        signals = row.get("entry_signals") or {}
        output = {
            "position_id": row.get("position_id"),
            "ticker": row.get("ticker"),
            "lane": row.get("lane"),
            "entry_date": row.get("entry_date"),
            "baseline_close_date": row.get("baseline_close_date"),
            "baseline_pnl_pct": row.get("baseline_pnl_pct"),
            "evidence_group": row.get("evidence_group"),
            "market_regime": signals.get("market_regime"),
            "quality_score": signals.get("quality_score"),
            "fill_degradation_pct": signals.get("fill_degradation_pct"),
            "debit_pct_of_width": signals.get("debit_pct_of_width"),
            "worst_leg_bid_ask_pct": signals.get("worst_leg_bid_ask_pct"),
            "priced_day_count": row.get("priced_day_count"),
            "unpriced_day_count": row.get("unpriced_day_count"),
        }
        for stop_key in stop_keys:
            result = (row.get("stop_results") or {}).get(stop_key) or {}
            output[f"stop_{stop_key}_triggered"] = result.get("triggered")
            output[f"stop_{stop_key}_date"] = result.get("trigger_date")
            output[f"stop_{stop_key}_pnl_pct"] = result.get("pnl_pct")
            output[f"stop_{stop_key}_delta_pct"] = result.get("delta_vs_baseline_pct")
            output[f"stop_{stop_key}_classification"] = result.get("classification")
            output[f"stop_{stop_key}_quality"] = result.get("stop_quality")
        rows.append(output)
    return rows


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path,
    docs_report: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    csv_path = output_dir / f"{REPORT_ID}_{stamp}.csv"
    latest_csv = output_dir / f"{REPORT_ID}_latest.csv"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"

    markdown = render_markdown(report)
    payload = json.dumps(report, indent=2, default=str)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    latest_md.write_text(markdown + "\n", encoding="utf-8")
    docs_report.write_text(markdown + "\n", encoding="utf-8")

    csv_rows = _csv_rows(report)
    if csv_rows:
        fieldnames = list(csv_rows[0].keys())
        for path in (csv_path, latest_csv):
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
    else:
        csv_path.write_text("", encoding="utf-8")
        latest_csv.write_text("", encoding="utf-8")

    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "csv": str(csv_path),
        "latest_csv": str(latest_csv),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    latest_json.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay current-policy realized rows through exact-contract historical stop grids."
    )
    parser.add_argument("--current-policy-report", type=Path, default=DEFAULT_CURRENT_POLICY_REPORT)
    parser.add_argument("--regular-multilane-report", type=Path, default=DEFAULT_REGULAR_MULTILANE_REPORT)
    parser.add_argument("--historical-db-path", type=Path, default=DEFAULT_HISTORICAL_OPTIONS_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--pricing-lane", default="pessimistic", choices=["pessimistic", "mid"])
    parser.add_argument("--trusted-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--as-of-date", default=datetime.now(ET).date().isoformat())
    parser.add_argument("--stop-grid", default=",".join(str(int(item)) for item in DEFAULT_STOP_GRID))
    parser.add_argument("--loss-threshold-pct", type=float, default=50.0)
    parser.add_argument("--annual-replay", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_local_env(ROOT)
    os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(Path(args.historical_db_path))
    current_policy_report = json.loads(Path(args.current_policy_report).read_text(encoding="utf-8"))
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    positions = repository.list_positions(None) or []
    store = HistoricalOptionsStore(args.historical_db_path)
    source_labels = _split_csv(args.source_labels, tuple(DEFAULT_SOURCE_LABELS))
    stop_grid = _split_float_grid(args.stop_grid)
    as_of = _parse_date(args.as_of_date)
    report = build_report(
        current_policy_report=current_policy_report,
        positions=positions,
        store=store,
        source_labels=source_labels,
        pricing_lane=args.pricing_lane,
        trusted_only=bool(args.trusted_only),
        as_of=as_of,
        stop_grid=stop_grid,
        loss_threshold_pct=float(args.loss_threshold_pct),
    )
    report["inputs"]["current_policy_report"] = str(Path(args.current_policy_report))
    report["inputs"]["historical_options_db"] = str(Path(args.historical_db_path))
    if bool(args.annual_replay) and Path(args.regular_multilane_report).exists():
        annual_report = json.loads(Path(args.regular_multilane_report).read_text(encoding="utf-8"))
        report["annual_replay_cohort"] = build_annual_replay_cohort(
            regular_multilane_report=annual_report,
            store=store,
            source_labels=source_labels,
            pricing_lane=args.pricing_lane,
            trusted_only=bool(args.trusted_only),
            as_of=as_of,
            stop_grid=stop_grid,
            loss_threshold_pct=float(args.loss_threshold_pct),
            report_path=Path(args.regular_multilane_report),
        )
        report["inputs"]["regular_multilane_report"] = str(Path(args.regular_multilane_report))
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=Path(args.output_dir), docs_report=Path(args.docs_report))
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        coverage = report["coverage"]
        baseline = report["baseline"]
        print(
            f"{REPORT_ID}: replayed={coverage['replayed_count']} unresolved={coverage['unresolved_count']} "
            f"baseline_avg={_pct(baseline.get('avg_pnl_pct'))} baseline_median={_pct(baseline.get('median_pnl_pct'))}"
        )
        for stop_key, policy in report.get("stop_policies", {}).items():
            print(
                f"  stop {stop_key}%: avg={_pct(policy.get('avg_pnl_pct'))} "
                f"negatives={policy.get('negative_count')} <=-90={policy.get('loss_bucket_counts', {}).get('loss_le_90_pct')} "
                f"hits={policy.get('triggered_count')} winner_flips={policy.get('winner_flip_count')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
