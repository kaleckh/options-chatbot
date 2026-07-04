from __future__ import annotations

import argparse
import ast
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_13_symbol_candidate_generation_surface_audit import (  # noqa: E402
    ALLOWED_UNIVERSE,
    DEFAULT_AS_OF_DATE,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    _as_dict,
    _as_list,
    _month_range,
    _parse_date,
)
from scripts.build_regular_options_13_symbol_frozen_candidate_generation_engine import (  # noqa: E402
    _cohort_pairs,
    _market_dates,
)
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_historical_frozen_scanner_replay_adapter"
DEFAULT_FORWARD_COHORT = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MARKET_REGIME_INPUTS = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-market-regime-inputs" / "latest.json"
)
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_INPUT_SURFACE_TRACKER = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-scanner-input-surface-tracker" / "latest.json"
)
DEFAULT_EARNINGS_CALENDAR = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-earnings-calendar" / "latest.json"
)
DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-frozen-scanner-replay-adapter.md"

ACCEPTED_STATUSES = {"selected_candidate", "explicit_no_pick"}
ETF_OR_INDEX_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA"}
THETADATA_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
ENTRY_START_MINUTE = 10 * 60 + 10
ENTRY_WINDOW_MINUTES = 15
EXIT_MINUTE = 15 * 60 + 55
TARGET_EXIT_PCT_OF_DTE = 0.75
DEFAULT_FEE_PER_CONTRACT_LEG_USD = 0.65
CONTRACT_MULTIPLIER = 100
FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
}
FORBIDDEN_ACTIONS = [
    "broker_orders",
    "live_validation",
    "auto_track",
    "production_scanner_policy_change",
    "production_strategy_change",
    "stop_change",
    "sizing_change",
    "proof_bar_change",
    "quote_import",
    "external_market_data_fetch",
    "options_history_db_mutation",
    "market_data_db_mutation",
    "evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_current_latest_data_for_historical_candidate_dates",
    "using_pnl_outcomes_winners_or_exits_to_decide_candidates",
    "inventing_selected_or_no_pick_rows",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = value.split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _function_parameters(path: Path, function_name: str) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf8"))
    except OSError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            params = [arg.arg for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
            if node.args.vararg:
                params.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                params.append("**" + node.args.kwarg.arg)
            return params
    return []


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_probe_option_rows(db_path: Path) -> None:
    from historical_options_store import init_schema

    init_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        batch_id = conn.execute(
            """
            INSERT INTO import_batches (
                source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thetadata_opra_nbbo_1m",
                "intraday_csv",
                "trusted",
                "fixture.csv",
                "abc",
                "2026-06-04T00:00:00Z",
                1,
                1,
                0,
                0,
                "[]",
            ),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO option_quote_snapshots (
                as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                underlying_price, volume, open_interest, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-03T15:12:00Z",
                "2026-02-03",
                10 * 60 + 12,
                "intraday",
                "SPY",
                "SPY260220C00500000",
                "2026-02-20",
                "call",
                500.0,
                4.1,
                4.3,
                None,
                None,
                501.0,
                None,
                None,
                batch_id,
            ),
        )
        conn.commit()


def _historical_option_provider_behavior_probe() -> dict[str, Any]:
    try:
        import options_chatbot as oc
        from historical_options_store import init_schema

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "options_history.db"
            _write_probe_option_rows(db_path)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(db_path)}, clear=False), patch.object(
                oc,
                "_cached_options_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ):
                option = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.50,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                )
            reads_trusted_row = bool(
                option
                and option.get("contract_symbol") == "SPY260220C00500000"
                and option.get("premium") == 4.3
                and option.get("quote_basis") == "ask"
                and option.get("iv") is None
                and option.get("volume") is None
                and option.get("open_interest") is None
                and option.get("historical_chain") is True
            )
            empty_db = Path(tmp) / "empty_options_history.db"
            init_schema(empty_db)
            with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(empty_db)}, clear=False), patch.object(
                oc,
                "_cached_options_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ), patch.object(
                oc,
                "_cached_option_chain_metadata",
                side_effect=AssertionError("latest chain fallback called"),
            ):
                missing = oc._fetch_best_option(
                    "SPY",
                    "call",
                    0.50,
                    17,
                    stock_price=501.0,
                    hv30_fallback=0.25,
                    candidate_generation_date="2026-02-03",
                    as_of_date="2026-06-04",
                )
        fail_closed_without_fallback = missing is None
        return {
            "proven": bool(reads_trusted_row and fail_closed_without_fallback),
            "reads_trusted_historical_rows": reads_trusted_row,
            "fails_closed_without_latest_chain_fallback": fail_closed_without_fallback,
            "error": None,
        }
    except Exception as exc:
        return {
            "proven": False,
            "reads_trusted_historical_rows": False,
            "fails_closed_without_latest_chain_fallback": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _scanner_contract() -> dict[str, Any]:
    run_params = _function_parameters(ROOT / "supervised_scan.py", "run_supervised_scan")
    scan_params = _function_parameters(ROOT / "options_chatbot.py", "scan_daily_top_trades")
    option_params = _function_parameters(ROOT / "options_chatbot.py", "_fetch_best_option")
    spread_params = _function_parameters(ROOT / "options_chatbot.py", "_fetch_best_spread")
    required = {"candidate_generation_date", "as_of_date", "no_write"}
    run_missing = sorted(required - set(run_params))
    scan_missing = sorted(required - set(scan_params))
    option_missing = sorted({"candidate_generation_date", "as_of_date"} - set(option_params))
    spread_missing = sorted({"candidate_generation_date", "as_of_date"} - set(spread_params))
    blockers: list[str] = []
    if run_missing or scan_missing:
        blockers.append("scanner_api_missing_historical_no_write_contract")
    if option_missing or spread_missing:
        blockers.append("scanner_option_selection_missing_historical_as_of_contract")
    provider_behavior = _historical_option_provider_behavior_probe() if not blockers else {
        "proven": False,
        "reads_trusted_historical_rows": False,
        "fails_closed_without_latest_chain_fallback": False,
        "error": "signature_contract_missing",
    }
    if not provider_behavior.get("proven"):
        blockers.append("scanner_option_selection_missing_historical_as_of_contract")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "proof_safe_contract_available": not blockers,
        "required_parameters": sorted(required),
        "inspected_callables": [
            {
                "path": "supervised_scan.py",
                "function": "run_supervised_scan",
                "parameters": run_params,
                "missing_required_parameters": run_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "scan_daily_top_trades",
                "parameters": scan_params,
                "missing_required_parameters": scan_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "_fetch_best_option",
                "parameters": option_params,
                "missing_historical_parameters": option_missing,
            },
            {
                "path": "options_chatbot.py",
                "function": "_fetch_best_spread",
                "parameters": spread_params,
                "missing_historical_parameters": spread_missing,
            },
        ],
        "historical_option_provider_behavior": provider_behavior,
        "blockers": blockers,
    }


def _tracker_surface_available(
    tracker: dict[str, Any],
    tracker_meta: dict[str, Any],
    *,
    surface_key: str,
    expected_symbol_date_count: int,
    window_start: str,
    window_end: str,
) -> bool:
    if tracker_meta.get("status") != "loaded":
        return False
    if tracker.get("report_id") != "regular_options_historical_scanner_input_surface_tracker":
        return False
    window = _as_dict(tracker.get("requested_window"))
    if window.get("window_start") != window_start or window.get("window_end") != window_end:
        return False
    if int(window.get("symbol_date_count") or -1) != int(expected_symbol_date_count):
        return False
    surface = _as_dict(_as_dict(tracker.get("surface_readiness")).get(surface_key))
    return surface.get("available") is True


def _surface_inventory(
    market_regime: dict[str, Any],
    market_meta: dict[str, Any],
    vix: dict[str, Any],
    vix_meta: dict[str, Any],
    tracker: dict[str, Any],
    tracker_meta: dict[str, Any],
    earnings_calendar: dict[str, Any],
    earnings_meta: dict[str, Any],
    *,
    expected_symbol_date_count: int,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    market_row_blockers = Counter(
        {str(key): int(value or 0) for key, value in _as_dict(market_regime.get("row_blocker_counts")).items()}
    )
    market_regime_ready = bool(
        market_meta.get("status") == "loaded"
        and market_regime.get("point_in_time_market_regime_inputs_available") is True
        and not _as_list(market_regime.get("blockers"))
    )
    vix_ready = bool(
        vix_meta.get("status") == "loaded"
        and vix.get("status") == "point_in_time_vix_bucket_ready"
        and not _as_list(vix.get("blockers"))
    )
    entry_underlying_ready = _tracker_surface_available(
        tracker,
        tracker_meta,
        surface_key="entry_underlying_price_surface",
        expected_symbol_date_count=expected_symbol_date_count,
        window_start=window_start,
        window_end=window_end,
    )
    option_chain_ready = _tracker_surface_available(
        tracker,
        tracker_meta,
        surface_key="option_chain_selection_surface",
        expected_symbol_date_count=expected_symbol_date_count,
        window_start=window_start,
        window_end=window_end,
    )
    earnings_window = _as_dict(earnings_calendar.get("requested_window"))
    earnings_ready = bool(
        earnings_meta.get("status") == "loaded"
        and earnings_calendar.get("status") == "point_in_time_earnings_calendar_ready"
        and not _as_list(earnings_calendar.get("blockers"))
        and earnings_window.get("window_start") == window_start
        and earnings_window.get("window_end") == window_end
    )
    blockers: list[str] = []
    if not market_regime_ready:
        blockers.append("missing_point_in_time_market_regime_inputs")
        if market_row_blockers.get("market_regime_source_time_not_point_in_time"):
            blockers.append("underlying_daily_history_source_not_point_in_time")
    if not vix_ready:
        blockers.append("missing_point_in_time_vix_source")
    lane_features_ready = bool(market_regime_ready and market_regime.get("input_rows"))
    if not lane_features_ready:
        blockers.append("missing_lane_specific_point_in_time_feature_inputs")
    if not entry_underlying_ready:
        blockers.append("missing_historical_entry_underlying_price_surface")
    if not option_chain_ready:
        blockers.append("missing_historical_option_chain_selection_surface")
    if not earnings_ready:
        blockers.append("missing_point_in_time_earnings_calendar_source")
    return {
        "point_in_time_inputs_ready": False,
        "market_regime": {
            "path": market_meta.get("path"),
            "loaded": market_meta.get("status") == "loaded",
            "status": market_regime.get("status"),
            "available": market_regime_ready,
            "row_blocker_counts": dict(sorted(market_row_blockers.items())),
            "source_time_policy": market_regime.get("source_time_policy"),
        },
        "vix_bucket": {
            "path": vix_meta.get("path"),
            "loaded": vix_meta.get("status") == "loaded",
            "status": vix.get("status"),
            "available": vix_ready,
        },
        "historical_scanner_input_surface_tracker": {
            "path": tracker_meta.get("path"),
            "loaded": tracker_meta.get("status") == "loaded",
            "status": tracker.get("status"),
            "matching_window_and_denominator": bool(
                tracker_meta.get("status") == "loaded"
                and _as_dict(tracker.get("requested_window")).get("window_start") == window_start
                and _as_dict(tracker.get("requested_window")).get("window_end") == window_end
                and int(_as_dict(tracker.get("requested_window")).get("symbol_date_count") or -1)
                == int(expected_symbol_date_count)
            ),
        },
        "underlying_feature_inputs": {
            "available": lane_features_ready,
            "required_fields": [
                "ret20",
                "sma50",
                "prior close",
                "above prior 50-day SMA",
                "point-in-time known-at/source hashes",
            ],
            "blocker": None if lane_features_ready else "missing_lane_specific_point_in_time_feature_inputs",
        },
        "entry_underlying_price_surface": {
            "available": entry_underlying_ready,
            "required": "candidate-date entry underlying price used for contract selection, known before or at the candidate decision time",
            "blocker": "missing_historical_entry_underlying_price_surface",
        },
        "option_chain_selection_surface": {
            "available": option_chain_ready,
            "required": "historical option expirations, bid/ask, volume, open interest, IV/delta inputs with known-at proof for candidate-date contract selection",
            "blocker": "missing_historical_option_chain_selection_surface",
        },
        "earnings_calendar": {
            "path": earnings_meta.get("path"),
            "loaded": earnings_meta.get("status") == "loaded",
            "status": earnings_calendar.get("status"),
            "available": earnings_ready,
            "required": "point-in-time next-earnings dates for equity symbols in the frozen cohort",
            "blocker": None if earnings_ready else "missing_point_in_time_earnings_calendar_source",
            "covered_equity_symbols": _as_list(earnings_calendar.get("covered_equity_symbols")),
            "missing_equity_symbols": _as_list(earnings_calendar.get("missing_equity_symbols")),
        },
        "blockers": sorted(dict.fromkeys(blockers)),
    }


def _earnings_dates_by_symbol(earnings_calendar: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    if earnings_calendar.get("status") != "point_in_time_earnings_calendar_ready":
        return indexed
    for raw_row in _as_list(earnings_calendar.get("earnings_events")):
        row = _as_dict(raw_row)
        symbol = str(row.get("symbol") or "").strip().upper()
        event_date = _parse_date(str(row.get("earnings_date_et") or "")[:10])
        known_at = _parse_utc(row.get("known_at_utc"))
        retrieved_at = _parse_utc(row.get("source_retrieved_at_utc"))
        if symbol and event_date:
            indexed.setdefault(symbol, []).append(
                {
                    "earnings_date_et": event_date,
                    "known_at_utc": known_at,
                    "source_retrieved_at_utc": retrieved_at,
                }
            )
    return {
        symbol: sorted(rows, key=lambda item: item["earnings_date_et"])
        for symbol, rows in indexed.items()
    }


def _earnings_within_hold_window(
    earnings_index: dict[str, list[dict[str, Any]]],
    *,
    symbol: str,
    candidate_date: date,
    dte: int,
) -> date | None:
    if symbol in ETF_OR_INDEX_SYMBOLS:
        return None
    candidate_decision = datetime.combine(candidate_date, datetime.min.time(), tzinfo=UTC)
    for row in earnings_index.get(symbol, []):
        event_date = row["earnings_date_et"]
        known_at = row.get("known_at_utc")
        retrieved_at = row.get("source_retrieved_at_utc")
        if known_at is None or retrieved_at is None or known_at > candidate_decision or retrieved_at > candidate_decision:
            continue
        if 0 <= (event_date - candidate_date).days <= dte:
            return event_date
    return None


def _row_blockers(symbol: str, contract: dict[str, Any], surfaces: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    blockers.extend(str(item) for item in _as_list(contract.get("blockers")))
    blockers.extend(str(item) for item in _as_list(surfaces.get("blockers")))
    if symbol in ETF_OR_INDEX_SYMBOLS:
        blockers = [item for item in blockers if item != "missing_point_in_time_earnings_calendar_source"]
    if blockers:
        blockers.append("missing_historical_scanner_point_in_time_inputs")
    return sorted(dict.fromkeys(blockers))


def _symbol_features_by_date(market_regime: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for raw_row in _as_list(market_regime.get("input_rows")):
        row = _as_dict(raw_row)
        day = str(row.get("input_date_et") or "")[:10]
        if not day:
            continue
        symbols: dict[str, dict[str, Any]] = {}
        for raw_feature in _as_list(row.get("symbol_features")):
            feature = _as_dict(raw_feature)
            symbol = str(feature.get("symbol") or "").upper()
            if symbol:
                symbols[symbol] = feature
        indexed[day] = symbols
    return indexed


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _feature_ready(feature: dict[str, Any], *, candidate_date: date) -> bool:
    if feature.get("point_in_time_valid") is not True or feature.get("proof_eligible") is not True:
        return False
    known_at = str(feature.get("known_at_utc") or feature.get("source_timestamp_utc") or "")
    prior_bar = str(feature.get("prior_bar_date_et") or "")[:10]
    if prior_bar and prior_bar >= candidate_date.isoformat():
        return False
    return bool(known_at)


def _direction_for_row(
    *,
    lane: str,
    symbol: str,
    feature: dict[str, Any] | None,
    candidate_date: date,
) -> tuple[str | None, list[str], dict[str, Any]]:
    if not feature or not _feature_ready(feature, candidate_date=candidate_date):
        return None, ["missing_lane_specific_point_in_time_feature_inputs"], {}
    prior_ret20 = _safe_float(feature.get("prior_20_trading_day_return_pct"))
    prior_close = _safe_float(feature.get("prior_close"))
    prior_sma50 = _safe_float(feature.get("prior_50_trading_day_sma"))
    above_sma = bool(feature.get("above_prior_50_sma"))
    if prior_ret20 is None or prior_close is None or prior_sma50 is None:
        return None, ["missing_lane_specific_point_in_time_feature_inputs"], {}
    evidence = {
        "prior_20_trading_day_return_pct": prior_ret20,
        "prior_close": prior_close,
        "prior_50_trading_day_sma": prior_sma50,
        "above_prior_50_sma": above_sma,
        "known_at_utc": feature.get("known_at_utc"),
        "source_ref": feature.get("source_ref"),
        "source_row_hash": feature.get("source_row_hash"),
    }
    if lane == "bullish_pullback_observation":
        if above_sma and prior_ret20 >= -2.0:
            return "call", [], evidence
        return None, [], evidence
    if lane == "volatility_expansion_observation":
        if prior_ret20 >= 3.0 and above_sma:
            return "call", [], evidence
        if prior_ret20 <= -3.0 and not above_sma:
            return "put", [], evidence
        return None, [], evidence
    return None, ["unsupported_frozen_lane"], evidence


def _policy_for_lane(cohort: dict[str, Any], lane: str) -> dict[str, Any]:
    return _as_dict(
        _as_dict(
            _as_dict(cohort.get("byte_frozen_policy_snapshot")).get("lanes")
        ).get(lane)
    ).get("policy") or {}


def _entry_quote_rows(conn: sqlite3.Connection, *, symbol: str, day: date, direction: str, target_dte: int) -> list[sqlite3.Row]:
    min_expiry = (day + timedelta(days=max(target_dte - 10, 1))).isoformat()
    max_expiry = (day + timedelta(days=target_dte + 10)).isoformat()
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        WITH first_valid_quotes AS (
            SELECT
                q.*,
                ROW_NUMBER() OVER (
                    PARTITION BY q.contract_symbol
                    ORDER BY q.quote_minute_et ASC, q.as_of_utc ASC
                ) AS quote_rank
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE q.underlying = ?
              AND q.snapshot_kind = 'intraday'
              AND q.option_type = ?
              AND q.quote_date_et = ?
              AND q.quote_minute_et >= ?
              AND q.quote_minute_et <= ?
              AND q.expiry >= ?
              AND q.expiry <= ?
              AND b.source_label = ?
              AND b.data_trust = 'trusted'
              AND q.bid IS NOT NULL
              AND q.ask IS NOT NULL
              AND q.bid > 0
              AND q.ask > q.bid
        )
        SELECT *
        FROM first_valid_quotes
        WHERE quote_rank = 1
        ORDER BY expiry ASC, strike ASC, contract_symbol ASC
        """,
        (
            symbol,
            direction,
            day.isoformat(),
            ENTRY_START_MINUTE,
            ENTRY_START_MINUTE + ENTRY_WINDOW_MINUTES,
            min_expiry,
            max_expiry,
            THETADATA_SOURCE_LABEL,
        ),
    ).fetchall()


def _quote_mid(row: sqlite3.Row) -> float | None:
    bid = _safe_float(row["bid"])
    ask = _safe_float(row["ask"])
    if bid is None or ask is None or bid <= 0 or ask <= bid:
        return None
    return (bid + ask) / 2.0


def _select_spread(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    day: date,
    direction: str,
    policy: dict[str, Any],
    stock_price: float | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    target_dte = int(policy.get("target_dte") or (14 if direction == "put" else 35))
    max_debit_pct = float(
        policy.get("profitability_repair_max_debit_pct_of_width")
        or policy.get("max_debit_pct_of_width")
        or 55.0
    )
    max_width_pct = 5.0
    max_spread_pct = float(policy.get("max_worst_leg_bid_ask_spread_pct") or 20.0)
    rows = _entry_quote_rows(conn, symbol=symbol, day=day, direction=direction, target_dte=target_dte)
    if not rows:
        return None, "no_trusted_entry_option_quotes"
    candidates: list[dict[str, Any]] = []
    by_expiry: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_expiry.setdefault(str(row["expiry"]), []).append(row)
    for expiry, expiry_rows in by_expiry.items():
        for long_row in expiry_rows:
            underlying_price = _safe_float(long_row["underlying_price"]) or stock_price
            if underlying_price is None or underlying_price <= 0:
                continue
            long_strike = float(long_row["strike"])
            long_ask = float(long_row["ask"])
            long_bid = float(long_row["bid"])
            long_mid = _quote_mid(long_row)
            if long_mid is None:
                continue
            long_spread_pct = (long_ask - long_bid) / long_mid * 100.0
            if long_spread_pct > max_spread_pct:
                continue
            for short_row in expiry_rows:
                short_strike = float(short_row["strike"])
                if direction == "call" and short_strike <= long_strike:
                    continue
                if direction == "put" and short_strike >= long_strike:
                    continue
                width = abs(short_strike - long_strike)
                if width <= 0 or (width / underlying_price * 100.0) > max_width_pct:
                    continue
                short_bid = float(short_row["bid"])
                short_ask = float(short_row["ask"])
                short_mid = _quote_mid(short_row)
                if short_mid is None:
                    continue
                short_spread_pct = (short_ask - short_bid) / short_mid * 100.0
                if short_spread_pct > max_spread_pct:
                    continue
                debit = long_ask - short_bid
                if debit <= 0:
                    continue
                debit_pct = debit / width * 100.0
                if debit_pct > max_debit_pct:
                    continue
                dte = (date.fromisoformat(str(expiry)[:10]) - day).days
                moneyness = abs(long_strike - underlying_price) / underlying_price
                candidates.append(
                    {
                        "long": long_row,
                        "short": short_row,
                        "expiry": expiry,
                        "dte": dte,
                        "width": width,
                        "entry_debit": debit,
                        "debit_pct_of_width": debit_pct,
                        "score": (
                            abs(dte - target_dte),
                            moneyness,
                            debit_pct,
                            long_strike if direction == "call" else -long_strike,
                        ),
                    }
                )
    if not candidates:
        return None, "no_executable_vertical_spread_candidate"
    selected = sorted(candidates, key=lambda item: item["score"])[0]
    long_row = selected["long"]
    short_row = selected["short"]
    return {
        "entry_date": day.isoformat(),
        "ticker": symbol,
        "direction": direction,
        "strategy_type": "vertical_spread",
        "entry_contract_resolution": "exact_contract_pair",
        "fill_basis": "imported_spread_mark",
        "proof_grade": "trusted_intraday_opra_nbbo",
        "quote_source": "historical_options_store_trusted_thetadata_opra_nbbo",
        "exact_priced": False,
        "long_contract_symbol": long_row["contract_symbol"],
        "short_contract_symbol": short_row["contract_symbol"],
        "expiry": selected["expiry"],
        "dte": selected["dte"],
        "spread_width": round(float(selected["width"]), 4),
        "entry_debit": round(float(selected["entry_debit"]), 4),
        "net_debit": round(float(selected["entry_debit"]), 4),
        "debit_pct_of_width": round(float(selected["debit_pct_of_width"]), 4),
        "long_entry_bid": long_row["bid"],
        "long_entry_ask": long_row["ask"],
        "short_entry_bid": short_row["bid"],
        "short_entry_ask": short_row["ask"],
        "entry_quote_minute_et": long_row["quote_minute_et"],
        "entry_quote_as_of_utc": long_row["as_of_utc"],
    }, None


def _market_day_on_or_after(market_dates: Sequence[date], target: date, *, latest: date) -> date | None:
    for day in market_dates:
        if day >= target and day <= latest:
            return day
    return None


def _exit_quote(conn: sqlite3.Connection, *, contract_symbol: str, quote_date: date) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT q.*
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.contract_symbol = ?
          AND q.snapshot_kind = 'intraday'
          AND q.quote_date_et = ?
          AND q.quote_minute_et >= ?
          AND b.source_label = ?
          AND b.data_trust = 'trusted'
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.bid >= 0
          AND q.ask >= q.bid
        ORDER BY q.quote_minute_et DESC, q.as_of_utc DESC
        LIMIT 1
        """,
        (contract_symbol, quote_date.isoformat(), EXIT_MINUTE, THETADATA_SOURCE_LABEL),
    ).fetchone()


def _attach_exit_pnl(
    conn: sqlite3.Connection,
    *,
    trade: dict[str, Any],
    market_dates: Sequence[date],
    fee_per_contract_leg_usd: float = DEFAULT_FEE_PER_CONTRACT_LEG_USD,
) -> dict[str, Any]:
    entry_date = date.fromisoformat(str(trade["entry_date"])[:10])
    expiry = date.fromisoformat(str(trade["expiry"])[:10])
    dte = max(int(trade.get("dte") or (expiry - entry_date).days), 1)
    target_exit = min(expiry, entry_date + timedelta(days=max(1, int(round(dte * TARGET_EXIT_PCT_OF_DTE)))))
    exit_date = _market_day_on_or_after(market_dates, target_exit, latest=expiry)
    if exit_date is None:
        trade["exit_pricing_status"] = "missing_market_day_for_policy_exit"
        return trade
    long_exit = _exit_quote(conn, contract_symbol=str(trade["long_contract_symbol"]), quote_date=exit_date)
    short_exit = _exit_quote(conn, contract_symbol=str(trade["short_contract_symbol"]), quote_date=exit_date)
    if long_exit is None or short_exit is None:
        trade["exit_pricing_status"] = "missing_trusted_exit_quote"
        trade["exit_date"] = exit_date.isoformat()
        return trade
    long_bid = _safe_float(long_exit["bid"])
    short_ask = _safe_float(short_exit["ask"])
    entry_debit = _safe_float(trade.get("entry_debit"))
    if long_bid is None or short_ask is None or entry_debit is None or entry_debit <= 0:
        trade["exit_pricing_status"] = "non_executable_exit_quote"
        trade["exit_date"] = exit_date.isoformat()
        return trade
    raw_exit_value = long_bid - short_ask
    exit_value = max(0.0, raw_exit_value)
    pnl_pct = (exit_value - entry_debit) / entry_debit * 100.0
    total_fees_usd = 4.0 * max(float(fee_per_contract_leg_usd), 0.0)
    gross_pnl_usd = (exit_value - entry_debit) * CONTRACT_MULTIPLIER
    net_pnl_usd = gross_pnl_usd - total_fees_usd
    net_pnl_pct_after_fees = net_pnl_usd / (entry_debit * CONTRACT_MULTIPLIER) * 100.0
    trade.update(
        {
            "exact_priced": True,
            "exit_pricing_status": "trusted_exit_priced",
            "exit_date": exit_date.isoformat(),
            "exit_reason": "fixed_75pct_dte_time_exit",
            "contract_multiplier": CONTRACT_MULTIPLIER,
            "fee_per_contract_leg_usd": round(max(float(fee_per_contract_leg_usd), 0.0), 4),
            "total_fees_usd": round(total_fees_usd, 4),
            "gross_pnl_usd": round(gross_pnl_usd, 4),
            "net_pnl_usd": round(net_pnl_usd, 4),
            "net_pnl_pct_after_fees": round(net_pnl_pct_after_fees, 4),
            "exit_value_floored_at_zero": raw_exit_value < 0.0,
            "exit_value": round(exit_value, 4),
            "exit_px": round(exit_value, 4),
            "pnl_pct": round(pnl_pct, 4),
            "net_pnl_pct": round(pnl_pct, 4),
            "long_exit_bid": long_bid,
            "long_exit_ask": _safe_float(long_exit["ask"]),
            "short_exit_bid": _safe_float(short_exit["bid"]),
            "short_exit_ask": short_ask,
            "exit_quote_minute_et": long_exit["quote_minute_et"],
            "exit_quote_as_of_utc": long_exit["as_of_utc"],
        }
    )
    return trade


def _build_rows(
    *,
    market_dates: Sequence[date],
    pairs: Sequence[dict[str, str]],
    as_of: date,
    cohort: dict[str, Any],
    market_regime: dict[str, Any],
    scanner_contract: dict[str, Any],
    surface_inventory: dict[str, Any],
    earnings_calendar: dict[str, Any],
    options_db_path: Path,
    fee_per_contract_leg_usd: float = DEFAULT_FEE_PER_CONTRACT_LEG_USD,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    feature_index = _symbol_features_by_date(market_regime)
    earnings_index = _earnings_dates_by_symbol(earnings_calendar)
    with sqlite3.connect(options_db_path) as conn:
        conn.row_factory = sqlite3.Row
        for current_date in market_dates:
            for pair in pairs:
                lane = str(pair["lane"])
                symbol = str(pair["underlying"]).upper()
                feature = feature_index.get(current_date.isoformat(), {}).get(symbol)
                blockers = _row_blockers(symbol, scanner_contract, surface_inventory)
                direction, signal_blockers, signal_evidence = _direction_for_row(
                    lane=lane,
                    symbol=symbol,
                    feature=feature,
                    candidate_date=current_date,
                )
                blockers.extend(signal_blockers)
                trade: dict[str, Any] | None = None
                no_pick_reason: str | None = None
                status = "blocked_missing_historical_scanner_point_in_time_inputs" if blockers else "explicit_no_pick"
                if not blockers and direction:
                    policy = _policy_for_lane(cohort, lane)
                    target_dte = int(policy.get("target_dte") or (14 if direction == "put" else 35))
                    earnings_date = _earnings_within_hold_window(
                        earnings_index,
                        symbol=symbol,
                        candidate_date=current_date,
                        dte=target_dte,
                    )
                    if earnings_date is not None:
                        no_pick_reason = "earnings_within_hold_window"
                        signal_evidence = dict(signal_evidence)
                        signal_evidence["earnings_event_date_et"] = earnings_date.isoformat()
                        signal_evidence["earnings_window_dte"] = target_dte
                    else:
                        trade, no_pick_reason = _select_spread(
                            conn,
                            symbol=symbol,
                            day=current_date,
                            direction=direction,
                            policy=policy,
                            stock_price=_safe_float(signal_evidence.get("prior_close")),
                        )
                        if trade is None:
                            status = "explicit_no_pick"
                        else:
                            trade = _attach_exit_pnl(
                                conn,
                                trade=trade,
                                market_dates=market_dates,
                                fee_per_contract_leg_usd=fee_per_contract_leg_usd,
                            )
                            trade.update(
                                {
                                    "lane_id": lane,
                                    "lane_family": lane,
                                    "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
                                    "source_result_path": "data/profitability-lab/regular-options-historical-frozen-scanner-replay-adapter/latest.json",
                                    "dedupe_key": f"{current_date.isoformat()}:{lane}:{symbol}:{direction}:{trade.get('long_contract_symbol')}:{trade.get('short_contract_symbol')}",
                                    "portfolio_eligible": True,
                                }
                            )
                            status = "selected_candidate"
                row = {
                    "row_id": f"{REPORT_ID}:{current_date.isoformat()}:{lane}:{symbol}",
                    "date": current_date.isoformat(),
                    "candidate_generation_date": current_date.isoformat(),
                    "entry_date": current_date.isoformat() if trade else None,
                    "month": current_date.isoformat()[:7],
                    "lane": lane,
                    "lane_id": lane,
                    "lane_family": lane,
                    "underlying": symbol,
                    "ticker": symbol,
                    "symbol": symbol,
                    "direction": direction,
                    "policy_snapshot_sha256": pair.get("policy_snapshot_sha256"),
                    "status": status,
                    "selected_candidate": status == "selected_candidate",
                    "explicit_no_pick": status == "explicit_no_pick",
                    "proof_safe": status in ACCEPTED_STATUSES,
                    "as_of_date": as_of.isoformat(),
                    "known_at": signal_evidence.get("known_at_utc") if signal_evidence else f"{current_date.isoformat()}T00:00:00Z",
                    "tradable_after": f"{current_date.isoformat()}T14:10:00Z",
                    "decision_timestamp_utc": f"{current_date.isoformat()}T14:10:00Z",
                    "read_only": True,
                    "no_write": True,
                    "decision_source": "deterministic_local_pit_materializer_v1",
                    "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
                    "scanner_parity": False,
                    "production_scanner_replay": False,
                    "signal_evidence": signal_evidence,
                    "no_pick_reason": no_pick_reason if status == "explicit_no_pick" else None,
                    "blockers": sorted(dict.fromkeys(blockers)),
                    "missing_inputs": sorted(dict.fromkeys(blockers)),
                }
                if trade:
                    row.update(trade)
                rows.append(row)
    return rows


def _coverage(rows: Sequence[dict[str, Any]], requested_months: Sequence[str]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_month.setdefault(str(row.get("month")), []).append(dict(row))
    covered = [
        month
        for month in requested_months
        if by_month.get(month) and all(str(row.get("status")) in ACCEPTED_STATUSES for row in by_month[month])
    ]
    return {
        "requested_months": list(requested_months),
        "requested_month_count": len(requested_months),
        "covered_months": covered,
        "covered_month_count": len(covered),
        "blocked_months": [month for month in requested_months if month not in set(covered)],
    }


def build_report(
    *,
    forward_cohort_path: Path = DEFAULT_FORWARD_COHORT,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    market_regime_inputs_path: Path = DEFAULT_MARKET_REGIME_INPUTS,
    vix_bucket_path: Path = DEFAULT_VIX_BUCKET,
    input_surface_tracker_path: Path = DEFAULT_INPUT_SURFACE_TRACKER,
    earnings_calendar_path: Path = DEFAULT_EARNINGS_CALENDAR,
    options_db_path: Path = DEFAULT_OPTIONS_DB,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: Sequence[str] = ALLOWED_UNIVERSE,
    no_write: bool = True,
    fee_per_contract_leg_usd: float = DEFAULT_FEE_PER_CONTRACT_LEG_USD,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    frozen_universe = _parse_universe(universe)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("start-date, end-date, and as-of-date must be valid YYYY-MM-DD values with start <= end")
    if frozen_universe != ALLOWED_UNIVERSE:
        raise ValueError("universe must exactly match the frozen 13-symbol universe")
    no_write = True

    cohort, cohort_meta = _load_json(forward_cohort_path)
    feature, feature_meta = _load_json(feature_store_path)
    market_regime, market_regime_meta = _load_json(market_regime_inputs_path)
    vix, vix_meta = _load_json(vix_bucket_path)
    input_surface_tracker, input_surface_tracker_meta = _load_json(input_surface_tracker_path)
    earnings_calendar, earnings_calendar_meta = _load_json(earnings_calendar_path)
    market_dates = _market_dates(feature, start, end)
    pairs = _cohort_pairs(cohort, ALLOWED_UNIVERSE)
    scanner_contract = _scanner_contract()
    surface_inventory = _surface_inventory(
        market_regime,
        market_regime_meta,
        vix,
        vix_meta,
        input_surface_tracker,
        input_surface_tracker_meta,
        earnings_calendar,
        earnings_calendar_meta,
        expected_symbol_date_count=len(market_dates) * len(ALLOWED_UNIVERSE),
        window_start=start.isoformat(),
        window_end=end.isoformat(),
    )
    daily_rows = _build_rows(
        market_dates=market_dates,
        pairs=pairs,
        as_of=as_of,
        cohort=cohort,
        market_regime=market_regime,
        scanner_contract=scanner_contract,
        surface_inventory=surface_inventory,
        earnings_calendar=earnings_calendar,
        options_db_path=options_db_path,
        fee_per_contract_leg_usd=fee_per_contract_leg_usd,
    )
    requested_months = _month_range(start, end)
    coverage = _coverage(daily_rows, requested_months)
    status_counts = Counter(str(row.get("status")) for row in daily_rows)
    blocker_counts = Counter(
        str(blocker)
        for row in daily_rows
        for blocker in _as_list(row.get("blockers"))
    )
    blockers = sorted(dict.fromkeys(blocker_counts))
    if cohort_meta.get("status") != "loaded":
        blockers.append("forward_cohort_preregistration_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_not_loaded")
    if not market_dates:
        blockers.append("market_date_denominator_missing")
    if not pairs:
        blockers.append("forward_cohort_lane_symbol_pairs_missing")
    if coverage["covered_month_count"] < len(requested_months):
        blockers.append(f"candidate_generation_months_{coverage['covered_month_count']}_below_requested_{len(requested_months)}")
    blockers = sorted(dict.fromkeys(blockers))
    selected_rows = [row for row in daily_rows if row.get("selected_candidate")]
    floored_exit_count = sum(1 for row in selected_rows if row.get("exit_value_floored_at_zero") is True)
    report = {
        "report_id": REPORT_ID,
        "status": "blocked_historical_frozen_scanner_replay_adapter" if blockers else "historical_frozen_scanner_replay_adapter_ready",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "no_write": no_write,
        **FALSE_FLAGS,
        "scope": "bounded_read_only_historical_frozen_scanner_replay_adapter",
        "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
        "scanner_parity": False,
        "production_scanner_replay": False,
        "allowed_universe": list(ALLOWED_UNIVERSE),
        "frozen_universe": list(ALLOWED_UNIVERSE),
        "requested_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "fee_per_contract_leg_usd": round(max(float(fee_per_contract_leg_usd), 0.0), 4),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
        },
        "adapter_contract": {
            "accepted_fields": ["candidate_generation_date", "as_of_date", "lane_id", "symbol", "no_write"],
            "emitted_fields": ["candidate_generation_date", "as_of_date", "lane_id", "symbol", "no_write", "proof_safe"],
            "default_no_write": True,
            "scanner_parity": False,
            "production_scanner_replay": False,
            "proof_safe_success_rule": "selected_candidate or explicit_no_pick rows require all scanner inputs known at or before candidate_generation_date and no current/latest provider calls",
            "non_parity_note": "Rows are deterministic local PIT materializer decisions, not proof that scan_daily_top_trades would have selected the same trades.",
        },
        "inputs": {
            "forward_cohort": cohort_meta,
            "feature_store": feature_meta,
            "market_regime_inputs": market_regime_meta,
            "vix_bucket": vix_meta,
            "historical_scanner_input_surface_tracker": input_surface_tracker_meta,
            "earnings_calendar": earnings_calendar_meta,
        },
        "scanner_contract": scanner_contract,
        "point_in_time_input_inventory": surface_inventory,
        "coverage": coverage,
        "calendar_coverage": {
            "status": "calendar_coverage_not_proven" if blockers else "calendar_coverage_proven",
            "coverage_basis": "proof_safe_selected_or_explicit_no_pick_rows_only",
            "calendar_months_covered": coverage["covered_months"],
            "calendar_months_covered_count": coverage["covered_month_count"],
            "blocked_months": coverage["blocked_months"],
        },
        "daily_status_counts": dict(sorted(status_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "daily_candidate_generation_row_count": len(daily_rows),
        "daily_candidate_decision_row_count": len(daily_rows),
        "selected_candidate_row_count": len(selected_rows),
        "selected_candidate_floored_exit_value_count": floored_exit_count,
        "daily_candidate_generation": daily_rows,
        "daily_candidate_decisions": daily_rows,
        "selected_candidates": selected_rows,
        "selected_trades": selected_rows,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": "underlying_daily_history_source_not_point_in_time"
        if "underlying_daily_history_source_not_point_in_time" in blockers
        else (blockers[0] if blockers else None),
        "proof_policy": {
            "readback_is": "read-only historical frozen scanner replay adapter blocker proof",
            "readback_is_not": "profitability proof, fresh forward proof, scanner release, quote import, evidence mutation, live validation, auto-track, broker permission, protected-holdout consumption, proof-bar change, or promotion",
            "fail_closed_rule": "blocked rows are emitted instead of selected/no-pick rows until every scanner input has point-in-time known-at proof",
        },
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_window"))
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Historical Frozen Scanner Replay Adapter",
        "",
        "This generated artifact is a bounded read-only adapter for the frozen Phase 2 lane/symbol/date denominator. It fails closed when the scanner inputs needed for point-in-time replay are unavailable.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Daily rows: `{report.get('daily_candidate_decision_row_count')}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Selected candidates: `{report.get('selected_candidate_row_count')}`.",
        f"- Floored exit-value rows: `{report.get('selected_candidate_floored_exit_value_count')}`.",
        f"- Smallest next blocker: `{report.get('smallest_next_blocker_clearing_slice')}`.",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in _as_dict(report.get("daily_status_counts")).items():
        lines.append(f"| `{status}` | `{count}` |")
    lines.extend(["", "## Blocker Counts", "", "| Blocker | Count |", "|---|---:|"])
    for blocker, count in _as_dict(report.get("blocker_counts")).items():
        lines.append(f"| `{blocker}` | `{count}` |")
    if blockers := _as_list(report.get("blockers")):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(["", "## Boundary", "", "The adapter did not call the scanner, fetch market data, import quotes, mutate evidence stores, or infer candidates from outcomes.", ""])
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    daily_path = output_dir / "daily_candidate_decisions.jsonl"
    selected_path = output_dir / "selected_candidates.jsonl"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "daily_candidate_decisions_jsonl": _rel(daily_path),
        "selected_candidates_jsonl": _rel(selected_path),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    with daily_path.open("w", encoding="utf8", newline="\n") as handle:
        for row in _as_list(report.get("daily_candidate_decisions")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with selected_path.open("w", encoding="utf8", newline="\n") as handle:
        for row in _as_list(report.get("selected_candidates")):
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only historical frozen scanner replay adapter.")
    parser.add_argument("--forward-cohort", type=Path, default=DEFAULT_FORWARD_COHORT)
    parser.add_argument("--source-feature-store", "--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--market-regime-inputs", type=Path, default=DEFAULT_MARKET_REGIME_INPUTS)
    parser.add_argument("--vix-bucket", type=Path, default=DEFAULT_VIX_BUCKET)
    parser.add_argument("--input-surface-tracker", type=Path, default=DEFAULT_INPUT_SURFACE_TRACKER)
    parser.add_argument("--earnings-calendar", type=Path, default=DEFAULT_EARNINGS_CALENDAR)
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--start-date", default=DEFAULT_WINDOW_START)
    parser.add_argument("--end-date", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--fee-per-contract-leg", type=float, default=DEFAULT_FEE_PER_CONTRACT_LEG_USD)
    parser.add_argument("--candidate-generation-date", default=None)
    parser.add_argument("--lane-id", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--universe", default=",".join(ALLOWED_UNIVERSE))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    start_date = args.candidate_generation_date or args.start_date
    end_date = args.candidate_generation_date or args.end_date
    report = build_report(
        forward_cohort_path=args.forward_cohort,
        feature_store_path=args.source_feature_store,
        market_regime_inputs_path=args.market_regime_inputs,
        vix_bucket_path=args.vix_bucket,
        input_surface_tracker_path=args.input_surface_tracker,
        earnings_calendar_path=args.earnings_calendar,
        options_db_path=args.options_db,
        window_start=start_date,
        window_end=end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
        no_write=True,
        fee_per_contract_leg_usd=max(float(args.fee_per_contract_leg), 0.0),
    )
    if args.lane_id or args.symbol:
        lane = str(args.lane_id or "").strip()
        symbol = str(args.symbol or "").strip().upper()
        rows = [
            row
            for row in _as_list(report.get("daily_candidate_decisions"))
            if (not lane or row.get("lane_id") == lane) and (not symbol or row.get("symbol") == symbol)
        ]
        report["daily_candidate_generation"] = rows
        report["daily_candidate_decisions"] = rows
        report["selected_candidates"] = [row for row in rows if _as_dict(row).get("selected_candidate")]
        report["selected_trades"] = list(report["selected_candidates"])
        report["daily_candidate_generation_row_count"] = len(rows)
        report["daily_candidate_decision_row_count"] = len(rows)
        report["selected_candidate_row_count"] = len(report["selected_candidates"])
        report["daily_status_counts"] = dict(sorted(Counter(str(row.get("status")) for row in rows).items()))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
