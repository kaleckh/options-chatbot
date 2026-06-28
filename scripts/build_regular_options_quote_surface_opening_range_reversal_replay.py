from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_quote_surface_opening_range_reversal_replay"
CONCEPT_ID = "quote_surface_opening_range_reversal_vertical_v1"
STRUCTURE = "defined_risk_same_expiration_debit_verticals_only"
DEFAULT_QUOTES_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_BASE_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_UNDERLYING_PRICE_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-alpaca-underlying-minute-price-surface"
    / "source_rows.jsonl"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-quote-surface-opening-range-reversal-replay"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-quote-surface-opening-range-reversal-replay.md"

DEFAULT_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
LATEST_FOUR_MONTHS = ("2026-02", "2026-03", "2026-04", "2026-05")
CONTRACT_MULTIPLIER = 100
FEE_PER_CONTRACT_PER_LEG_PER_SIDE = 0.65
MIN_FULL_WINDOW_EXACT_ROWS = 200
MIN_STRICT_NEW_GAP = 43
MIN_LATEST_FOUR_EXACT_ROWS = 30

OPENING_START_MINUTE = 9 * 60 + 35
OPENING_END_MINUTE = 10 * 60 + 35
ENTRY_START_MINUTE = 10 * 60 + 40
ENTRY_END_MINUTE = 10 * 60 + 45
EXIT_START_MINUTE = 15 * 60 + 45
EXIT_END_MINUTE = 15 * 60 + 55

READ_ONLY_FLAGS = {
    "read_only": True,
    "no_write": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "live_entry_allowed": False,
    "live_validation_enabled": False,
    "auto_track_allowed": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

DENOMINATOR_STATUSES = (
    "candidate_generated",
    "explicit_no_pick",
    "blocked_missing_underlying_price",
    "blocked_missing_opening_range_snapshot",
    "blocked_insufficient_prior_20_day_distribution",
    "blocked_missing_leg_quote",
    "blocked_zero_bid_or_untradable",
    "blocked_crossed_or_stale_quote",
    "blocked_outside_universe",
    "duplicate_within_research_harness",
    "duplicate_existing_base_stack",
    "protected_holdout_overlap",
    "blocked_unknown",
)

FORBIDDEN_ACTIONS = (
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_append_forward_paper_shadow_cohort",
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_treat_historical_rows_as_forward_proof",
    "do_not_count_midpoint_stale_eod_display_last_model_manual_or_synthetic_marks",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return None
    return value_float if math.isfinite(value_float) else None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


def _load_underlying_price_source_rows(path: Path) -> tuple[dict[tuple[str, str, int], dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "row_count": 0, "error": None}
    if not path.exists():
        return {}, meta
    price_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf8").splitlines()
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"line {index}: expected object")
            if row.get("source_family") != "alpaca_sip_underlying_minute_price_v1":
                raise ValueError(f"line {index}: unsupported source_family")
            symbol = str(row.get("underlying") or "").upper()
            quote_date = str(row.get("price_date_et") or "")
            minute = int(row.get("price_minute_et"))
            close = _safe_float(row.get("close"))
            if not symbol or not quote_date or close is None or close <= 0:
                raise ValueError(f"line {index}: invalid source row")
            price_rows[(symbol, quote_date, minute)] = row
    except Exception as exc:
        meta["status"] = "malformed"
        meta["error"] = f"{exc.__class__.__name__}: {exc}"
        return {}, meta
    meta["status"] = "loaded"
    meta["row_count"] = len(price_rows)
    return price_rows, meta


def _base_identity_hashes(base_ledger: dict[str, Any]) -> set[str]:
    hashes: set[str] = set()
    for value in _as_list(base_ledger.get("identity_hashes")):
        if value:
            hashes.add(str(value))
    for entry in _as_list(base_ledger.get("ledger_entries")):
        if not isinstance(entry, dict):
            continue
        for key in ("identity_hash", "opportunity_identity_hash"):
            if entry.get(key):
                hashes.add(str(entry[key]))
    return hashes


def _protected_holdout_start(holdout: dict[str, Any]) -> str | None:
    return (
        holdout.get("protected_holdout_start")
        or _as_dict(holdout.get("protected_range")).get("start_date")
        or _as_dict(holdout.get("range")).get("start_date")
    )


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _read_only_confirmed(conn: sqlite3.Connection) -> bool:
    try:
        return int(conn.execute("PRAGMA query_only").fetchone()[0]) == 1
    except (sqlite3.Error, TypeError, IndexError):
        return False


def _available_symbol_dates(conn: sqlite3.Connection, *, start_date: str, end_date: str, universe: tuple[str, ...]) -> list[tuple[str, str]]:
    placeholders = ",".join("?" for _ in universe)
    rows = conn.execute(
        f"""
        SELECT underlying, quote_date_et
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND quote_date_et BETWEEN ? AND ?
          AND underlying IN ({placeholders})
        GROUP BY underlying, quote_date_et
        ORDER BY quote_date_et, underlying
        """,
        (start_date, end_date, *universe),
    ).fetchall()
    return [(str(row["underlying"]).upper(), str(row["quote_date_et"])) for row in rows]


def _snapshot_underlying(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    quote_date: str,
    start_minute: int,
    end_minute: int,
    underlying_price_rows: dict[tuple[str, str, int], dict[str, Any]] | None = None,
    choose_latest: bool = False,
) -> dict[str, Any] | None:
    order = "DESC" if choose_latest else "ASC"
    row = conn.execute(
        f"""
        SELECT quote_minute_et, as_of_utc, underlying_price
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND underlying = ?
          AND quote_date_et = ?
          AND quote_minute_et BETWEEN ? AND ?
        ORDER BY quote_minute_et {order}, as_of_utc {order}
        LIMIT 1
        """,
        (symbol, quote_date, start_minute, end_minute),
    ).fetchone()
    prices = underlying_price_rows or {}
    if not row:
        candidate_minutes = sorted(
            minute
            for source_symbol, source_date, minute in prices
            if source_symbol == str(symbol).upper() and source_date == str(quote_date) and start_minute <= minute <= end_minute
        )
        if choose_latest:
            candidate_minutes = list(reversed(candidate_minutes))
        if not candidate_minutes:
            return None
        source_row = prices[(str(symbol).upper(), str(quote_date), candidate_minutes[0])]
        return {
            "quote_minute_et": int(source_row["price_minute_et"]),
            "as_of_utc": source_row.get("price_timestamp_utc"),
            "underlying_price": _safe_float(source_row.get("close")),
            "underlying_price_source": source_row.get("source_family"),
            "underlying_price_source_ref": source_row.get("source_ref"),
        }
    payload = dict(row)
    if payload.get("underlying_price") is not None:
        return payload
    source_row = prices.get((str(symbol).upper(), str(quote_date), int(payload["quote_minute_et"])))
    if source_row is not None:
        payload["underlying_price"] = _safe_float(source_row.get("close"))
        payload["underlying_price_source"] = source_row.get("source_family")
        payload["underlying_price_source_ref"] = source_row.get("source_ref")
    return payload


def _has_snapshot_rows(conn: sqlite3.Connection, *, symbol: str, quote_date: str, start_minute: int, end_minute: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND underlying = ?
          AND quote_date_et = ?
          AND quote_minute_et BETWEEN ? AND ?
        LIMIT 1
        """,
        (symbol, quote_date, start_minute, end_minute),
    ).fetchone()
    return row is not None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _fetch_chain_rows(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    quote_date: str,
    option_type: str,
    start_minute: int,
    end_minute: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT as_of_utc, quote_minute_et, contract_symbol, expiry, option_type, strike, bid, ask
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND underlying = ?
          AND quote_date_et = ?
          AND quote_minute_et BETWEEN ? AND ?
          AND option_type = ?
        ORDER BY quote_minute_et ASC, expiry ASC, strike ASC
        """,
        (symbol, quote_date, start_minute, end_minute, option_type),
    ).fetchall()
    return [dict(row) for row in rows]


def _tradable_quote(row: dict[str, Any]) -> bool:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    return bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid


def _select_vertical(
    entry_rows: list[dict[str, Any]],
    *,
    quote_date: str,
    direction: str,
    underlying_price: float,
) -> tuple[dict[str, Any] | None, str | None]:
    option_type = "call" if direction == "call" else "put"
    by_expiry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trade_date = _parse_date(quote_date)
    if trade_date is None:
        return None, "blocked_unknown"
    for row in entry_rows:
        if str(row.get("option_type")) != option_type:
            continue
        expiry = str(row.get("expiry") or "")
        expiry_date = _parse_date(expiry)
        if expiry_date is None:
            continue
        dte = (expiry_date - trade_date).days
        if 7 <= dte <= 21:
            by_expiry[expiry].append(row)
    if not by_expiry:
        return None, "blocked_missing_leg_quote"
    expiries = sorted(by_expiry, key=lambda exp: (abs((_parse_date(exp) - trade_date).days - 14), exp))  # type: ignore[operator]
    for expiry in expiries:
        rows = [row for row in by_expiry[expiry] if _tradable_quote(row)]
        if len(rows) < 2:
            continue
        rows.sort(key=lambda item: float(item["strike"]))
        long_leg = min(rows, key=lambda item: abs(float(item["strike"]) - underlying_price))
        long_strike = float(long_leg["strike"])
        if direction == "call":
            candidates = [
                row
                for row in rows
                if float(row["strike"]) > long_strike and 0.0075 <= (float(row["strike"]) - long_strike) / underlying_price <= 0.015
            ]
            candidates.sort(key=lambda item: (abs(((float(item["strike"]) - long_strike) / underlying_price) - 0.01), float(item["strike"])))
        else:
            candidates = [
                row
                for row in rows
                if float(row["strike"]) < long_strike and 0.0075 <= (long_strike - float(row["strike"])) / underlying_price <= 0.015
            ]
            candidates.sort(key=lambda item: (abs(((long_strike - float(item["strike"])) / underlying_price) - 0.01), -float(item["strike"])))
        if candidates:
            short_leg = candidates[0]
            return {
                "direction": direction,
                "option_type": option_type,
                "expiry": expiry,
                "long_contract_symbol": long_leg["contract_symbol"],
                "short_contract_symbol": short_leg["contract_symbol"],
                "long_strike": float(long_leg["strike"]),
                "short_strike": float(short_leg["strike"]),
                "entry_minute": int(long_leg["quote_minute_et"]),
                "entry_long_bid": _safe_float(long_leg.get("bid")),
                "entry_long_ask": _safe_float(long_leg.get("ask")),
                "entry_short_bid": _safe_float(short_leg.get("bid")),
                "entry_short_ask": _safe_float(short_leg.get("ask")),
            }, None
    return None, "blocked_zero_bid_or_untradable"


def _exit_quotes(
    conn: sqlite3.Connection,
    *,
    long_contract: str,
    short_contract: str,
    quote_date: str,
) -> tuple[dict[str, Any] | None, str | None]:
    rows = conn.execute(
        """
        SELECT contract_symbol, quote_minute_et, bid, ask
        FROM option_quote_snapshots
        WHERE snapshot_kind = 'intraday'
          AND quote_date_et = ?
          AND quote_minute_et BETWEEN ? AND ?
          AND contract_symbol IN (?, ?)
        ORDER BY quote_minute_et DESC
        """,
        (quote_date, EXIT_START_MINUTE, EXIT_END_MINUTE, long_contract, short_contract),
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row)
        latest.setdefault(str(payload["contract_symbol"]), payload)
    if long_contract not in latest or short_contract not in latest:
        return None, "blocked_missing_leg_quote"
    long_row = latest[long_contract]
    short_row = latest[short_contract]
    if not _tradable_quote(long_row) or not _tradable_quote(short_row):
        long_bid = _safe_float(long_row.get("bid"))
        short_ask = _safe_float(short_row.get("ask"))
        if long_bid is not None and long_bid <= 0:
            return None, "blocked_zero_bid_or_untradable"
        if short_ask is not None and short_ask <= 0:
            return None, "blocked_zero_bid_or_untradable"
        return None, "blocked_crossed_or_stale_quote"
    return {
        "exit_minute": int(long_row["quote_minute_et"]),
        "exit_long_bid": _safe_float(long_row.get("bid")),
        "exit_long_ask": _safe_float(long_row.get("ask")),
        "exit_short_bid": _safe_float(short_row.get("bid")),
        "exit_short_ask": _safe_float(short_row.get("ask")),
    }, None


def _opportunity_hash(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _candidate_identity(*, symbol: str, quote_date: str, vertical: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    payload = {
        "concept_id": CONCEPT_ID,
        "structure": STRUCTURE,
        "underlying": symbol,
        "signal_date": quote_date,
        "direction": vertical["direction"],
        "entry_timestamp_bucket": "10:40-10:45_ET",
        "exit_timestamp_bucket": "15:45-15:55_ET_same_day",
        "expiration": vertical["expiry"],
        "long_contract_symbol": vertical["long_contract_symbol"],
        "short_contract_symbol": vertical["short_contract_symbol"],
        "long_strike": vertical["long_strike"],
        "short_strike": vertical["short_strike"],
        "leg_sides": "buy_long_sell_short_debit_vertical",
        "leg_ratios": "1x-1x",
        "entry_policy": "long_ask_minus_short_bid",
        "exit_policy": "long_bid_minus_short_ask_same_day",
        "candidate_source_id": "quote_surface_opening_range_reversal_v1",
    }
    return _opportunity_hash(payload), payload


def _fees_usd() -> float:
    return round(FEE_PER_CONTRACT_PER_LEG_PER_SIDE * 2 * 2, 2)


def _profit_factor(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def _bootstrap_pf_lower_bound(values: list[float], *, samples: int = 500) -> float | None:
    if len(values) < 2 or not any(value > 0 for value in values) or not any(value < 0 for value in values):
        return None
    rng = random.Random(17)
    pfs: list[float] = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        pf = _profit_factor(sample)
        if pf is not None:
            pfs.append(pf)
    if not pfs:
        return None
    pfs.sort()
    return pfs[max(0, int(len(pfs) * 0.05) - 1)]


def _stress_profit_factor(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins) * 0.95
    gross_loss = abs(sum(losses)) * 1.05
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def _profit_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_safe_float(row.get("net_pnl_usd")) for row in rows]
    pnl = [value for value in values if value is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    pf = _profit_factor(pnl)
    pf_lb = _bootstrap_pf_lower_bound(pnl)
    stress_pf = _stress_profit_factor(pnl)
    return {
        "row_count": len(rows),
        "priced_row_count": len(pnl),
        "win_count": len(wins),
        "loss_count": len(losses),
        "net_usd_pnl": round(sum(pnl), 2) if pnl else 0.0,
        "average_net_usd_pnl": round(sum(pnl) / len(pnl), 2) if pnl else None,
        "profit_factor": round(pf, 4) if pf is not None else None,
        "profit_factor_lower_bound_5pct": round(pf_lb, 4) if pf_lb is not None else None,
        "stress_profit_factor": round(stress_pf, 4) if stress_pf is not None else None,
    }


def _profit_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [row for row in rows if (_safe_float(row.get("net_pnl_usd")) or 0) > 0]
    gross_profit = sum(float(row["net_pnl_usd"]) for row in positive)
    if gross_profit <= 0:
        return {
            "single_trade_profit_share": 0.0,
            "top_5_trade_profit_share": 0.0,
            "single_month_profit_share": 0.0,
            "single_underlying_profit_share": 0.0,
            "single_expiration_profit_share": 0.0,
        }
    trade_profits = sorted((float(row["net_pnl_usd"]) for row in positive), reverse=True)
    month_profit: Counter[str] = Counter()
    symbol_profit: Counter[str] = Counter()
    expiry_profit: Counter[str] = Counter()
    for row in positive:
        value = float(row["net_pnl_usd"])
        month_profit[str(row.get("entry_date"))[:7]] += value
        symbol_profit[str(row.get("underlying"))] += value
        expiry_profit[str(row.get("expiry"))] += value
    return {
        "single_trade_profit_share": round(trade_profits[0] / gross_profit, 4),
        "top_5_trade_profit_share": round(sum(trade_profits[:5]) / gross_profit, 4),
        "single_month_profit_share": round(max(month_profit.values()) / gross_profit, 4) if month_profit else 0.0,
        "single_underlying_profit_share": round(max(symbol_profit.values()) / gross_profit, 4) if symbol_profit else 0.0,
        "single_expiration_profit_share": round(max(expiry_profit.values()) / gross_profit, 4) if expiry_profit else 0.0,
    }


def _classify_status(metrics: dict[str, Any], blockers: list[str]) -> str:
    if "blocked_missing_quote_surface_underlying_price" in blockers:
        return "blocked_quote_surface_opening_range_reversal_replay"
    if "blocked_insufficient_daily_denominator_coverage" in blockers or "blocked_latest_four_rows_below_30" in blockers:
        return "blocked_quote_surface_opening_range_reversal_replay"
    if blockers:
        return "blocked_quote_surface_opening_range_reversal_replay"
    latest = _as_dict(metrics.get("latest_four_months"))
    full = _as_dict(metrics.get("full_window"))
    concentration = _as_dict(metrics.get("concentration"))
    if (
        latest.get("strict_executable_completed_rows_after_opportunity_dedupe", 0) >= MIN_LATEST_FOUR_EXACT_ROWS
        and full.get("strict_new_rows_after_opportunity_dedupe", 0) >= MIN_STRICT_NEW_GAP
        and full.get("exact_completed_rows", 0) >= MIN_FULL_WINDOW_EXACT_ROWS
        and (latest.get("net_usd_pnl") or 0) > 0
        and (latest.get("profit_factor") or 0) >= 1.20
        and (latest.get("profit_factor_lower_bound_5pct") or 0) > 1.0
        and (full.get("profit_factor") or 0) >= 1.20
        and (full.get("profit_factor_lower_bound_5pct") or 0) > 1.0
        and (full.get("stress_profit_factor") or 0) >= 1.05
        and concentration.get("single_trade_profit_share", 1.0) <= 0.20
        and concentration.get("top_5_trade_profit_share", 1.0) <= 0.50
        and concentration.get("single_month_profit_share", 1.0) <= 0.35
        and concentration.get("single_underlying_profit_share", 1.0) <= 0.50
        and concentration.get("single_expiration_profit_share", 1.0) <= 0.40
    ):
        return "quote_surface_opening_range_reversal_candidate_for_forward_freeze_review"
    if (full.get("net_usd_pnl") or 0) <= 0 or (full.get("profit_factor") or 0) < 1.0:
        return "rejected_quote_surface_opening_range_reversal_edge"
    if (full.get("profit_factor_lower_bound_5pct") or 0) <= 1.0:
        return "blocked_quote_surface_opening_range_reversal_replay"
    return "diagnostic_only_quote_surface_opening_range_reversal"


def _smallest_blocker(blockers: list[str]) -> str | None:
    priority = (
        "db_read_only_not_confirmed",
        "blocked_missing_quote_surface_underlying_price",
        "blocked_insufficient_daily_denominator_coverage",
        "blocked_latest_four_rows_below_30",
        "blocked_pf_lower_bound_not_above_1",
        "blocked_single_trade_profit_concentration",
        "blocked_top_5_trade_profit_concentration",
        "blocked_single_month_profit_concentration",
        "blocked_single_underlying_profit_concentration",
        "blocked_single_expiration_profit_concentration",
    )
    for blocker in priority:
        if blocker in blockers:
            return blocker
    return blockers[0] if blockers else None


def _build_metrics(
    denominator_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    requested_months: list[str],
) -> dict[str, Any]:
    exact = [row for row in candidate_rows if row.get("execution_status") == "exact_exit_captured"]
    strict = [row for row in exact if row.get("strict_new") is True]
    latest_strict = [row for row in strict if str(row.get("entry_date", ""))[:7] in LATEST_FOUR_MONTHS]
    train = [row for row in strict if str(row.get("entry_date", ""))[:7] not in LATEST_FOUR_MONTHS]
    status_counts = Counter(str(row.get("denominator_status")) for row in denominator_rows)
    explicit_months = sorted({str(row.get("entry_date"))[:7] for row in denominator_rows if row.get("denominator_status")})
    train_denominator_months = [month for month in explicit_months if month not in LATEST_FOUR_MONTHS]
    blocked_days = sum(1 for row in denominator_rows if str(row.get("denominator_status", "")).startswith("blocked"))
    full_metrics = _profit_metrics(strict)
    latest_metrics = _profit_metrics(latest_strict)
    full_metrics.update(
        {
            "exact_completed_rows": len(exact),
            "strict_new_rows_after_opportunity_dedupe": len(strict),
        }
    )
    latest_metrics.update(
        {
            "strict_executable_completed_rows_after_opportunity_dedupe": len(latest_strict),
        }
    )
    return {
        "daily_denominator_rows": len(denominator_rows),
        "explicit_denominator_months": explicit_months,
        "explicit_denominator_month_count": len(explicit_months),
        "requested_months": requested_months,
        "blocked_days": blocked_days,
        "denominator_status_counts": dict(sorted(status_counts.items())),
        "candidate_rows": len(candidate_rows),
        "unpriced_selected_rows": sum(1 for row in candidate_rows if row.get("execution_status") != "exact_exit_captured"),
        "zero_bid_selected_rows": status_counts.get("blocked_zero_bid_or_untradable", 0),
        "untradable_selected_rows": status_counts.get("blocked_zero_bid_or_untradable", 0)
        + status_counts.get("blocked_crossed_or_stale_quote", 0),
        "protected_holdout_overlap_rows": status_counts.get("protected_holdout_overlap", 0),
        "leakage_reject_rows": 0,
        "train_months": train_denominator_months,
        "train_month_count": len(train_denominator_months),
        "strict_candidate_train_months": sorted({str(row.get("entry_date"))[:7] for row in train}),
        "strict_candidate_train_month_count": len({str(row.get("entry_date"))[:7] for row in train}),
        "latest_four_months_list": list(LATEST_FOUR_MONTHS),
        "full_window": full_metrics,
        "latest_four_months": latest_metrics,
        "concentration": _profit_concentration(strict),
    }


def build_report(
    *,
    quotes_db_path: Path = DEFAULT_QUOTES_DB,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    underlying_price_source_rows_path: Path = DEFAULT_UNDERLYING_PRICE_SOURCE_ROWS,
    start_date: str = "2024-06-01",
    end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    universe: tuple[str, ...] = DEFAULT_UNIVERSE,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    universe = tuple(symbol.upper().strip() for symbol in universe if symbol.strip())
    if tuple(universe) != DEFAULT_UNIVERSE:
        raise ValueError("universe must be exactly SPY,QQQ,IWM,DIA in that order")
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or start > end:
        raise ValueError("invalid date window")

    base_ledger, base_meta = _load_json(base_ledger_path, required=True)
    holdout, holdout_meta = _load_json(holdout_contract_path, required=True)
    underlying_price_rows, underlying_price_meta = _load_underlying_price_source_rows(underlying_price_source_rows_path)
    base_hashes = _base_identity_hashes(base_ledger)
    holdout_start = _parse_date(_protected_holdout_start(holdout))
    requested_months = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        requested_months.append(cursor.isoformat()[:7])
        cursor = date(cursor.year + (1 if cursor.month == 12 else 0), 1 if cursor.month == 12 else cursor.month + 1, 1)

    conn = _connect_read_only(quotes_db_path)
    read_only_confirmed = _read_only_confirmed(conn)
    symbol_dates = _available_symbol_dates(conn, start_date=start_date, end_date=end_date, universe=universe)
    denominator_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    prior_returns: dict[str, list[float]] = defaultdict(list)

    for symbol, quote_date in symbol_dates:
        row: dict[str, Any] = {
            "entry_date": quote_date,
            "underlying": symbol,
            "concept_id": CONCEPT_ID,
            "structure": STRUCTURE,
            "denominator_status": "blocked_unknown",
            "reason_codes": [],
        }
        quote_dt = _parse_date(quote_date)
        if quote_dt is None or quote_dt > as_of:
            row["denominator_status"] = "blocked_unknown"
            row["reason_codes"] = ["date_after_as_of_or_invalid"]
            denominator_rows.append(row)
            continue
        if symbol not in universe:
            row["denominator_status"] = "blocked_outside_universe"
            row["reason_codes"] = ["symbol_outside_frozen_universe"]
            denominator_rows.append(row)
            continue
        if holdout_start is not None and quote_dt >= holdout_start:
            row["denominator_status"] = "protected_holdout_overlap"
            row["reason_codes"] = ["protected_holdout_overlap"]
            denominator_rows.append(row)
            continue

        has_start = _has_snapshot_rows(conn, symbol=symbol, quote_date=quote_date, start_minute=OPENING_START_MINUTE, end_minute=OPENING_END_MINUTE)
        has_end = _has_snapshot_rows(conn, symbol=symbol, quote_date=quote_date, start_minute=OPENING_END_MINUTE, end_minute=OPENING_END_MINUTE)
        start_snap = _snapshot_underlying(
            conn,
            symbol=symbol,
            quote_date=quote_date,
            start_minute=OPENING_START_MINUTE,
            end_minute=OPENING_END_MINUTE,
            underlying_price_rows=underlying_price_rows,
        )
        end_snap = _snapshot_underlying(
            conn,
            symbol=symbol,
            quote_date=quote_date,
            start_minute=OPENING_END_MINUTE,
            end_minute=OPENING_END_MINUTE,
            underlying_price_rows=underlying_price_rows,
        )
        if start_snap is None or end_snap is None:
            reasons = []
            if not has_start or not has_end:
                reasons.append("blocked_missing_opening_range_snapshot")
            reasons.append("blocked_missing_underlying_price")
            row["denominator_status"] = "blocked_missing_underlying_price"
            row["reason_codes"] = sorted(set(reasons))
            denominator_rows.append(row)
            continue

        start_price = _safe_float(start_snap.get("underlying_price"))
        end_price = _safe_float(end_snap.get("underlying_price"))
        if start_price is None or end_price is None or start_price <= 0 or end_price <= 0:
            row["denominator_status"] = "blocked_missing_underlying_price"
            row["reason_codes"] = ["blocked_missing_underlying_price"]
            denominator_rows.append(row)
            continue
        opening_return = (end_price - start_price) / start_price
        row["opening_range_return"] = round(opening_return, 6)
        row["opening_start_minute"] = int(start_snap["quote_minute_et"])
        row["opening_end_minute"] = int(end_snap["quote_minute_et"])

        prior = prior_returns[symbol][-20:]
        prior_returns[symbol].append(opening_return)
        if len(prior) < 20:
            row["denominator_status"] = "blocked_insufficient_prior_20_day_distribution"
            row["reason_codes"] = ["blocked_insufficient_prior_20_day_distribution"]
            denominator_rows.append(row)
            continue
        p10 = _percentile(prior, 0.10)
        p90 = _percentile(prior, 0.90)
        row["prior_20_p10"] = round(p10, 6)
        row["prior_20_p90"] = round(p90, 6)
        if opening_return <= p10:
            direction = "call"
        elif opening_return >= p90:
            direction = "put"
        else:
            row["denominator_status"] = "explicit_no_pick"
            row["reason_codes"] = ["opening_range_inside_prior_20_percentile_band"]
            denominator_rows.append(row)
            continue

        entry_rows = _fetch_chain_rows(
            conn,
            symbol=symbol,
            quote_date=quote_date,
            option_type="call" if direction == "call" else "put",
            start_minute=ENTRY_START_MINUTE,
            end_minute=ENTRY_END_MINUTE,
        )
        vertical, blocker = _select_vertical(entry_rows, quote_date=quote_date, direction=direction, underlying_price=end_price)
        if vertical is None:
            row["denominator_status"] = blocker or "blocked_missing_leg_quote"
            row["reason_codes"] = [row["denominator_status"]]
            denominator_rows.append(row)
            continue
        identity_hash, identity_payload = _candidate_identity(symbol=symbol, quote_date=quote_date, vertical=vertical)
        if identity_hash in seen_hashes:
            row["denominator_status"] = "duplicate_within_research_harness"
            row["reason_codes"] = ["duplicate_within_research_harness"]
            denominator_rows.append(row)
            continue
        seen_hashes.add(identity_hash)
        strict_new = identity_hash not in base_hashes
        if not strict_new:
            row["denominator_status"] = "duplicate_existing_base_stack"
            row["reason_codes"] = ["duplicate_existing_base_stack"]
            denominator_rows.append(row)
            continue

        exit_row, exit_blocker = _exit_quotes(
            conn,
            long_contract=str(vertical["long_contract_symbol"]),
            short_contract=str(vertical["short_contract_symbol"]),
            quote_date=quote_date,
        )
        if exit_row is None:
            row["denominator_status"] = exit_blocker or "blocked_missing_leg_quote"
            row["reason_codes"] = [row["denominator_status"]]
            denominator_rows.append(row)
            continue
        entry_debit = float(vertical["entry_long_ask"]) - float(vertical["entry_short_bid"])
        exit_value = float(exit_row["exit_long_bid"]) - float(exit_row["exit_short_ask"])
        if entry_debit <= 0 or exit_value < 0:
            row["denominator_status"] = "blocked_crossed_or_stale_quote"
            row["reason_codes"] = ["nonpositive_entry_debit_or_negative_exit_value"]
            denominator_rows.append(row)
            continue
        fees = _fees_usd()
        net = (exit_value - entry_debit) * CONTRACT_MULTIPLIER - fees
        candidate = {
            **row,
            **vertical,
            **exit_row,
            "denominator_status": "candidate_generated",
            "execution_status": "exact_exit_captured",
            "strict_new": strict_new,
            "opportunity_identity_hash": identity_hash,
            "opportunity_identity_payload": identity_payload,
            "entry_debit": round(entry_debit, 4),
            "exit_value": round(exit_value, 4),
            "fees_usd": fees,
            "fee_policy_source": "fallback_testable_constant",
            "net_pnl_usd": round(net, 2),
            "reason_codes": [],
        }
        row.update(
            {
                "denominator_status": "candidate_generated",
                "reason_codes": [],
                "direction": direction,
                "opportunity_identity_hash": identity_hash,
                "execution_status": "exact_exit_captured",
                "net_pnl_usd": round(net, 2),
            }
        )
        candidate_rows.append(candidate)
        denominator_rows.append(row)

    conn.close()
    metrics = _build_metrics(denominator_rows, candidate_rows, requested_months=requested_months)
    blockers: list[str] = []
    if not read_only_confirmed:
        blockers.append("db_read_only_not_confirmed")
    if metrics["explicit_denominator_month_count"] < 24 or metrics["train_month_count"] < 20:
        blockers.append("blocked_insufficient_daily_denominator_coverage")
    if metrics["latest_four_months"]["strict_executable_completed_rows_after_opportunity_dedupe"] < MIN_LATEST_FOUR_EXACT_ROWS:
        blockers.append("blocked_latest_four_rows_below_30")
    if metrics["denominator_status_counts"].get("blocked_missing_underlying_price", 0) > 0:
        blockers.append("blocked_missing_quote_surface_underlying_price")
    if metrics["full_window"]["priced_row_count"] and (metrics["full_window"]["profit_factor_lower_bound_5pct"] or 0) <= 1.0:
        blockers.append("blocked_pf_lower_bound_not_above_1")
    concentration = metrics["concentration"]
    if concentration["single_trade_profit_share"] > 0.20:
        blockers.append("blocked_single_trade_profit_concentration")
    if concentration["top_5_trade_profit_share"] > 0.50:
        blockers.append("blocked_top_5_trade_profit_concentration")
    if concentration["single_month_profit_share"] > 0.35:
        blockers.append("blocked_single_month_profit_concentration")
    if concentration["single_underlying_profit_share"] > 0.50:
        blockers.append("blocked_single_underlying_profit_concentration")
    if concentration["single_expiration_profit_share"] > 0.40:
        blockers.append("blocked_single_expiration_profit_concentration")
    blockers = sorted(set(blockers))
    status = _classify_status(metrics, blockers)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write": no_write,
        "concept_id": CONCEPT_ID,
        "structure": STRUCTURE,
        "universe": list(universe),
        "window": {"start_date": start_date, "end_date": end_date, "as_of_date": as_of_date},
        "target_latest_four_strict_completed_rows": MIN_LATEST_FOUR_EXACT_ROWS,
        "base_clean_stack_exact_rows": 157,
        "read_only_db_open": read_only_confirmed,
        "expected_base_clean_stack_exact_rows": 157,
        "base_identity_hash_count": len(base_hashes),
        "protected_holdout_start": holdout_start.isoformat() if holdout_start else None,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": _smallest_blocker(blockers),
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "metrics": metrics,
        "daily_denominator_preview": denominator_rows[:50],
        "candidate_rows_preview": candidate_rows[:50],
        "source_artifacts": {
            "quotes_db": {"path": _rel(quotes_db_path), "exists": quotes_db_path.exists(), "status": "read_only_opened"},
            "base_clean_stack_identity_ledger": base_meta,
            "forward_holdout_contract": holdout_meta,
            "underlying_price_source_rows": underlying_price_meta,
        },
        "proof_formula": {
            "entry_debit": "long_leg_ask - short_leg_bid",
            "exit_value": "long_leg_bid - short_leg_ask",
            "net_pnl_usd": "(exit_value - entry_debit) * 100 - $0.65 per contract per leg per side",
        },
        "proof_boundary": "historical rows are read-only research falsification/nomination evidence and are not forward proof or accepted profitability",
        "next_oracle_instruction": (
            "Return this result to the same GPT-5.5 Pro session. If blocked on missing underlying price/opening buckets or fewer "
            "than 30 latest-four strict executable completed rows, park this branch unless a new trusted quote/underlying surface "
            "or explicit research-only replay source changes the blocker; then select the next materially different read-only "
            "option-structure or quote-surface branch."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "_daily_denominator_rows": denominator_rows,
        "_candidate_rows": candidate_rows,
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    for status in DENOMINATOR_STATUSES:
        if status not in report.get("denominator_statuses", []):
            raise ValueError(f"missing denominator status {status}")
    if report.get("concept_id") != CONCEPT_ID:
        raise ValueError("wrong concept id")
    if report.get("accepted_profitability") is not False:
        raise ValueError("accepted profitability must remain false")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    full = _as_dict(metrics.get("full_window"))
    latest = _as_dict(metrics.get("latest_four_months"))
    concentration = _as_dict(metrics.get("concentration"))
    lines = [
        "# Regular Options Quote-Surface Opening-Range Reversal Replay",
        "",
        "This generated report is read-only. It tests one quote-surface-only mean-reversion debit-vertical concept from existing local OPRA/NBBO rows without importing quotes, mutating evidence stores, changing scanner logic, consuming protected holdout, enabling live validation, auto-track, broker orders, or promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report['concept_id']}`.",
        f"- Window: `{report['window']['start_date']}` through `{report['window']['end_date']}` as of `{report['window']['as_of_date']}`.",
        f"- Universe: `{', '.join(report['universe'])}`.",
        f"- Read-only DB open: `{_fmt_bool(report['read_only_db_open'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        f"- Daily denominator rows: `{metrics.get('daily_denominator_rows')}`.",
        f"- Candidate rows: `{metrics.get('candidate_rows')}`.",
        f"- Latest-four strict executable rows: `{latest.get('strict_executable_completed_rows_after_opportunity_dedupe')}`.",
        f"- Full-window strict-new rows: `{full.get('strict_new_rows_after_opportunity_dedupe')}`.",
        f"- Full-window net USD P&L: `{full.get('net_usd_pnl')}`.",
        f"- Full-window PF / lower-bound / stress PF: `{full.get('profit_factor')}` / `{full.get('profit_factor_lower_bound_5pct')}` / `{full.get('stress_profit_factor')}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Denominator Status Counts",
            "",
            "| Status | Count |",
            "|---|---:|",
        ]
    )
    for status, count in _as_dict(metrics.get("denominator_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Concentration",
            "",
            f"- Single-trade profit share: `{concentration.get('single_trade_profit_share')}`.",
            f"- Top-5 trade profit share: `{concentration.get('top_5_trade_profit_share')}`.",
            f"- Single-month profit share: `{concentration.get('single_month_profit_share')}`.",
            f"- Single-underlying profit share: `{concentration.get('single_underlying_profit_share')}`.",
            f"- Single-expiration profit share: `{concentration.get('single_expiration_profit_share')}`.",
            "",
            "## Boundary",
            "",
            report["proof_boundary"],
            "",
            "## Next Oracle Instruction",
            "",
            report["next_oracle_instruction"],
            "",
            "## Forbidden Actions",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    daily_path = output_dir / "daily_denominator.jsonl"
    candidates_path = output_dir / "candidate_rows.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
        "daily_denominator_jsonl": _rel(daily_path),
        "candidate_rows_jsonl": _rel(candidates_path),
    }
    public = _public_report(report)
    public["artifacts"] = artifacts
    markdown = render_markdown(public)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    daily_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_daily_denominator_rows"))) + "\n",
        encoding="utf8",
    )
    candidates_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in _as_list(report.get("_candidate_rows"))) + "\n",
        encoding="utf8",
    )
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only quote-surface opening-range reversal replay.")
    parser.add_argument("--quotes-db", type=Path, default=DEFAULT_QUOTES_DB)
    parser.add_argument("--base-ledger", type=Path, default=DEFAULT_BASE_LEDGER)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--underlying-price-source-rows", type=Path, default=DEFAULT_UNDERLYING_PRICE_SOURCE_ROWS)
    parser.add_argument("--start-date", default="2024-06-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--universe", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    universe = tuple(part.strip().upper() for part in args.universe.split(",") if part.strip())
    report = build_report(
        quotes_db_path=args.quotes_db,
        base_ledger_path=args.base_ledger,
        holdout_contract_path=args.holdout_contract,
        underlying_price_source_rows_path=args.underlying_price_source_rows,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=universe,
        no_write=True,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    public = _public_report(report)
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True))
    else:
        print(render_markdown(public))
    return 0


if __name__ == "__main__":
    sys.exit(main())
