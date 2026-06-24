from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "bullish_pullback_layer_execution_safety_audit"

DEFAULT_LAYER_STACK = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "layer-stack" / "latest.json"
DEFAULT_LAYER_SHADOW_SELECTION = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_shadow_selection_latest.json"
DEFAULT_SELECTED_SOURCE_RUN = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json"
)
DEFAULT_OPTIONS_HISTORY_DB = Path(os.getenv("HISTORICAL_OPTIONS_DB_PATH", str(ROOT / "data" / "options-validation" / "options_history.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-bullish-pullback-layer-execution-safety-audit.md"

MAX_SOURCE_AGE_HOURS = 720
PRIMARY_LAYER_ID = "layer_4_clean_exact"
PRIMARY_VARIANT_ID = "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1"
EXPECTED_METRICS = {
    "candidate_trade_count": 129,
    "exact_trade_count": 129,
    "profit_factor": 2.20,
    "quote_coverage_pct": 100.0,
    "stress_5pct_per_side_profit_factor": 1.67,
    "unpriced_trade_count": 0,
}
DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)
TRUSTED_DATA_TRUST = "trusted"
INTRADAY_SNAPSHOT_KIND = "intraday"
DEFAULT_ENTRY_MINUTE_ET = 10 * 60 + 10
DEFAULT_EXIT_MINUTE_ET = 15 * 60 + 55
SIDE_AWARE_PRICE_TOLERANCE = 0.05

LONG_ENTRY_BID_KEYS = ("long_entry_bid", "long_entry_bid_px", "long_entry_bid_price")
LONG_ENTRY_ASK_KEYS = ("long_entry_ask", "long_entry_ask_px", "long_entry_ask_price")
SHORT_ENTRY_BID_KEYS = ("short_entry_bid", "short_entry_bid_px", "short_entry_bid_price")
SHORT_ENTRY_ASK_KEYS = ("short_entry_ask", "short_entry_ask_px", "short_entry_ask_price")
LONG_EXIT_BID_KEYS = ("long_exit_bid", "long_exit_bid_px", "long_exit_bid_price")
LONG_EXIT_ASK_KEYS = ("long_exit_ask", "long_exit_ask_px", "long_exit_ask_price")
SHORT_EXIT_BID_KEYS = ("short_exit_bid", "short_exit_bid_px", "short_exit_bid_price")
SHORT_EXIT_ASK_KEYS = ("short_exit_ask", "short_exit_ask_px", "short_exit_ask_price")

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_submit_broker_orders_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_enable_live_validation_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_enable_auto_track_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_change_scanner_policy_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_change_strategy_logic_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_change_stops_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_change_sizing_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_mutate_evidence_databases_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_import_quotes_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_append_forward_cohort_rows_from_bullish_pullback_layer_execution_safety_audit",
    "do_not_consume_protected_holdout_from_bullish_pullback_layer_execution_safety_audit",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_number(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _load_json_artifact(
    path: Path,
    *,
    name: str,
    required: bool,
    generated_at_utc: str,
    max_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": ["missing_readback"],
        "error": None,
    }
    if not path.exists():
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source["status"] = "malformed"
        source["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        source["reason_codes"] = ["malformed_readback"]
        return {}, source
    except OSError as exc:
        source["status"] = "unreadable"
        source["error"] = type(exc).__name__
        source["reason_codes"] = ["unreadable_readback"]
        return {}, source
    if not isinstance(payload, dict):
        source["status"] = "invalid"
        source["reason_codes"] = ["json_root_not_object"]
        return {}, source

    source_generated = payload.get("generated_at_utc") or payload.get("generated_at") or payload.get("run_at")
    source["generated_at_utc"] = source_generated
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    source_dt = _parse_utc(source_generated)
    if source_dt is None:
        source["status"] = "stale"
        source["reason_codes"] = ["missing_or_malformed_generated_at", "stale_readback"]
        return payload, source
    age_hours = (as_of - source_dt).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        source["status"] = "invalid"
        source["reason_codes"] = ["readback_generated_in_future"]
        return payload, source
    if age_hours > max_age_hours:
        source["status"] = "stale"
        source["reason_codes"] = ["stale_readback"]
        return payload, source
    source["status"] = "loaded"
    source["reason_codes"] = []
    source["report_id"] = payload.get("report_id") or name
    return payload, source


def _layers_by_id(layer_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for row in _as_list(layer_stack.get("ordered_layers")):
        if isinstance(row, dict):
            layer_id = _norm(row.get("layer_id"))
            if layer_id:
                layers[layer_id] = row
    return layers


def _metric(layer: dict[str, Any], name: str) -> Any:
    return _as_dict(layer.get("metrics")).get(name)


def _metric_blockers(layer: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key, expected in EXPECTED_METRICS.items():
        actual = _metric(layer, key)
        if isinstance(expected, float):
            parsed = _safe_float(actual)
            if parsed is None or round(parsed, 2) != round(expected, 2):
                blockers.append(f"selected_layer_{key}_expected_{expected}_got_{actual}")
        else:
            parsed_int = _safe_int(actual)
            if parsed_int != expected:
                blockers.append(f"selected_layer_{key}_expected_{expected}_got_{actual}")
    return blockers


def _parse_occ(symbol: Any) -> dict[str, Any]:
    text = _norm(symbol)
    match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", text)
    if not match:
        return {
            "contract_symbol": text or None,
            "underlying": None,
            "expiry": None,
            "right": None,
            "strike": None,
            "parse_status": "unparsed_occ_symbol",
        }
    yy, mm, dd = match.group(2)[:2], match.group(2)[2:4], match.group(2)[4:6]
    return {
        "contract_symbol": text,
        "underlying": match.group(1),
        "expiry": f"20{yy}-{mm}-{dd}",
        "right": match.group(3),
        "strike": int(match.group(4)) / 1000,
        "parse_status": "parsed_occ_symbol",
    }


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _source_labels(values: Sequence[str]) -> tuple[str, ...]:
    labels = tuple(str(value).strip() for value in values if str(value).strip())
    return labels or DEFAULT_SOURCE_LABELS


def _trusted_source_batch_ids(conn: sqlite3.Connection, source_labels: Sequence[str]) -> set[int]:
    labels = _source_labels(source_labels)
    placeholders = ",".join("?" for _ in labels)
    rows = conn.execute(
        f"""
        SELECT id
        FROM import_batches
        WHERE source_label IN ({placeholders})
          AND data_trust = ?
        """,
        (*labels, TRUSTED_DATA_TRUST),
    ).fetchall()
    return {int(row["id"]) for row in rows}


def _db_meta(path: Path, source_labels: Sequence[str]) -> dict[str, Any]:
    meta = {
        "path": _rel(path),
        "exists": path.exists(),
        "status": "missing",
        "error": None,
        "snapshot_kind": INTRADAY_SNAPSHOT_KIND,
        "source_labels": list(_source_labels(source_labels)),
        "data_trust": TRUSTED_DATA_TRUST,
        "read_only_mode": True,
    }
    if not path.exists():
        meta["error"] = "missing_artifact"
        return meta
    try:
        with closing(_sqlite_readonly_connect(path)) as conn:
            meta["status"] = "loaded"
            row = conn.execute(
                "SELECT COUNT(*) FROM option_quote_snapshots WHERE snapshot_kind = ?",
                (INTRADAY_SNAPSHOT_KIND,),
            ).fetchone()
            meta["intraday_quote_row_count"] = int((row[0] if row else 0) or 0)
            meta["trusted_source_batch_count"] = len(_trusted_source_batch_ids(conn, source_labels))
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
    return meta


def _quote_public(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    bid = _safe_float(row["bid"] if isinstance(row, sqlite3.Row) else row.get("bid"))
    ask = _safe_float(row["ask"] if isinstance(row, sqlite3.Row) else row.get("ask"))
    return {
        "contract_symbol": row["contract_symbol"] if isinstance(row, sqlite3.Row) else row.get("contract_symbol"),
        "quote_date_et": row["quote_date_et"] if isinstance(row, sqlite3.Row) else row.get("quote_date_et"),
        "quote_minute_et": int(row["quote_minute_et"] if isinstance(row, sqlite3.Row) else row.get("quote_minute_et")),
        "as_of_utc": row["as_of_utc"] if isinstance(row, sqlite3.Row) else row.get("as_of_utc"),
        "bid": round(float(bid), 4) if bid is not None else None,
        "ask": round(float(ask), 4) if ask is not None else None,
        "source_batch_id": int(row["source_batch_id"] if isinstance(row, sqlite3.Row) else row.get("source_batch_id")),
        "quote_evidence_class": "trusted_intraday_opra_nbbo_existing_store",
    }


def _quote_is_usable(quote: dict[str, Any] | None) -> bool:
    if not quote:
        return False
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    return bid is not None and ask is not None and bid >= 0 and ask > 0 and ask >= bid


def _quote_is_zero_or_untradable(quote: dict[str, Any] | None) -> bool:
    if not quote:
        return False
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    return bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid


def _quote_rows_by_minute(
    conn: sqlite3.Connection,
    *,
    contract_symbol: str,
    quote_date_et: str,
    trusted_batch_ids: set[int],
    cache: dict[tuple[str, str], dict[int, dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    key = (contract_symbol, quote_date_et)
    if key in cache:
        return cache[key]
    rows = conn.execute(
        """
        SELECT contract_symbol, quote_date_et, quote_minute_et, as_of_utc, bid, ask, source_batch_id
        FROM option_quote_snapshots INDEXED BY idx_option_quotes_contract_date
        WHERE contract_symbol = ?
          AND snapshot_kind = ?
          AND quote_date_et = ?
        ORDER BY quote_minute_et ASC, as_of_utc ASC
        """,
        (contract_symbol, INTRADAY_SNAPSHOT_KIND, quote_date_et),
    ).fetchall()
    by_minute: dict[int, dict[str, Any]] = {}
    for row in rows:
        batch_id = int(row["source_batch_id"])
        minute = int(row["quote_minute_et"])
        if batch_id not in trusted_batch_ids or minute in by_minute:
            continue
        public = _quote_public(row)
        if public:
            by_minute[minute] = public
    cache[key] = by_minute
    return by_minute


def _quote_pair_at_minute(
    conn: sqlite3.Connection,
    *,
    long_contract: str,
    short_contract: str,
    quote_date_et: str,
    minute_et: int,
    trusted_batch_ids: set[int],
    cache: dict[tuple[str, str], dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    long_quotes = _quote_rows_by_minute(
        conn, contract_symbol=long_contract, quote_date_et=quote_date_et, trusted_batch_ids=trusted_batch_ids, cache=cache
    )
    short_quotes = _quote_rows_by_minute(
        conn, contract_symbol=short_contract, quote_date_et=quote_date_et, trusted_batch_ids=trusted_batch_ids, cache=cache
    )
    return {
        "quote_date_et": quote_date_et,
        "quote_minute_et": minute_et,
        "long_quote": long_quotes.get(minute_et),
        "short_quote": short_quotes.get(minute_et),
        "lookup_rule": "exact_minute",
    }


def _latest_common_quote_pair(
    conn: sqlite3.Connection,
    *,
    long_contract: str,
    short_contract: str,
    quote_date_et: str,
    latest_minute_et: int,
    trusted_batch_ids: set[int],
    cache: dict[tuple[str, str], dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    long_quotes = _quote_rows_by_minute(
        conn, contract_symbol=long_contract, quote_date_et=quote_date_et, trusted_batch_ids=trusted_batch_ids, cache=cache
    )
    short_quotes = _quote_rows_by_minute(
        conn, contract_symbol=short_contract, quote_date_et=quote_date_et, trusted_batch_ids=trusted_batch_ids, cache=cache
    )
    common_minutes = sorted(minute for minute in set(long_quotes).intersection(short_quotes) if minute <= latest_minute_et)
    if not common_minutes:
        return {
            "quote_date_et": quote_date_et,
            "quote_minute_et": None,
            "long_quote": None,
            "short_quote": None,
            "lookup_rule": "latest_common_minute_at_or_before_exit_cutoff",
        }
    minute = common_minutes[-1]
    return {
        "quote_date_et": quote_date_et,
        "quote_minute_et": minute,
        "long_quote": long_quotes.get(minute),
        "short_quote": short_quotes.get(minute),
        "lookup_rule": "latest_common_minute_at_or_before_exit_cutoff",
    }


def _entry_debit(long_quote: dict[str, Any] | None, short_quote: dict[str, Any] | None) -> float | None:
    if not _quote_is_usable(long_quote) or not _quote_is_usable(short_quote):
        return None
    return round(float(long_quote["ask"]) - float(short_quote["bid"]), 4)


def _exit_credit(long_quote: dict[str, Any] | None, short_quote: dict[str, Any] | None) -> float | None:
    if not _quote_is_usable(long_quote) or not _quote_is_usable(short_quote):
        return None
    return round(float(long_quote["bid"]) - float(short_quote["ask"]), 4)


def _price_matches(actual: float | None, expected: Any) -> bool:
    expected_float = _safe_float(expected)
    if actual is None or expected_float is None:
        return False
    return abs(float(actual) - float(expected_float)) <= SIDE_AWARE_PRICE_TOLERANCE


def _has_leg_entry_bid_ask(row: dict[str, Any]) -> bool:
    return all(
        value is not None
        for value in (
            _first_number(row, LONG_ENTRY_BID_KEYS),
            _first_number(row, LONG_ENTRY_ASK_KEYS),
            _first_number(row, SHORT_ENTRY_BID_KEYS),
            _first_number(row, SHORT_ENTRY_ASK_KEYS),
        )
    )


def _has_leg_exit_bid_ask(row: dict[str, Any]) -> bool:
    return all(
        value is not None
        for value in (
            _first_number(row, LONG_EXIT_BID_KEYS),
            _first_number(row, LONG_EXIT_ASK_KEYS),
            _first_number(row, SHORT_EXIT_BID_KEYS),
            _first_number(row, SHORT_EXIT_ASK_KEYS),
        )
    )


def _has_crossed_quote(row: dict[str, Any]) -> bool:
    pairs = (
        (LONG_ENTRY_BID_KEYS, LONG_ENTRY_ASK_KEYS),
        (SHORT_ENTRY_BID_KEYS, SHORT_ENTRY_ASK_KEYS),
        (LONG_EXIT_BID_KEYS, LONG_EXIT_ASK_KEYS),
        (SHORT_EXIT_BID_KEYS, SHORT_EXIT_ASK_KEYS),
    )
    for bid_keys, ask_keys in pairs:
        bid = _first_number(row, bid_keys)
        ask = _first_number(row, ask_keys)
        if bid is not None and ask is not None and bid > ask:
            return True
    return False


def _has_zero_bid(row: dict[str, Any]) -> bool:
    for keys in (LONG_ENTRY_BID_KEYS, SHORT_ENTRY_BID_KEYS, LONG_EXIT_BID_KEYS, SHORT_EXIT_BID_KEYS):
        bid = _first_number(row, keys)
        if bid is not None and bid <= 0:
            return True
    return False


def _assignment_expiration_review(row: dict[str, Any], long_leg: dict[str, Any], short_leg: dict[str, Any]) -> dict[str, Any]:
    exit_dt = _parse_date(row.get("exit_date"))
    expiry_dt = _parse_date(long_leg.get("expiry") or short_leg.get("expiry") or row.get("target_expiry"))
    if exit_dt is None or expiry_dt is None:
        return {
            "classification_available": False,
            "assignment_risk_bucket": "unknown_missing_exit_or_expiry",
            "expiration_safety_bucket": "unknown_missing_exit_or_expiry",
            "days_exit_before_expiry": None,
        }
    days_before = (expiry_dt - exit_dt).days
    if days_before <= 0:
        expiration_bucket = "exit_on_or_after_expiration_requires_resolution"
    elif days_before <= 3:
        expiration_bucket = "near_expiration_review_required"
    else:
        expiration_bucket = "exit_before_expiration"
    assignment_bucket = "short_call_assignment_review_required" if short_leg.get("right") == "C" else "short_leg_assignment_review_required"
    return {
        "classification_available": True,
        "assignment_risk_bucket": assignment_bucket,
        "expiration_safety_bucket": expiration_bucket,
        "days_exit_before_expiry": days_before,
    }


def _audit_row(
    row: dict[str, Any],
    index: int,
    *,
    entry_pair: dict[str, Any] | None = None,
    exit_pair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    long_leg = _parse_occ(row.get("contract_symbol"))
    short_leg = _parse_occ(row.get("short_contract_symbol"))
    long_expiry = _norm(long_leg.get("expiry"))
    short_expiry = _norm(short_leg.get("expiry"))
    parsed_leg_identity = long_leg.get("parse_status") == "parsed_occ_symbol" and short_leg.get("parse_status") == "parsed_occ_symbol"
    source_has_entry_bid_ask = _has_leg_entry_bid_ask(row)
    source_has_exit_bid_ask = _has_leg_exit_bid_ask(row)
    source_crossed_quote = _has_crossed_quote(row)
    source_zero_bid = _has_zero_bid(row)
    entry_pair = entry_pair or {}
    exit_pair = exit_pair or {}
    entry_long_quote = _quote_public(entry_pair.get("long_quote"))
    entry_short_quote = _quote_public(entry_pair.get("short_quote"))
    exit_long_quote = _quote_public(exit_pair.get("long_quote"))
    exit_short_quote = _quote_public(exit_pair.get("short_quote"))
    existing_entry_bid_ask = _quote_is_usable(entry_long_quote) and _quote_is_usable(entry_short_quote)
    existing_exit_bid_ask = _quote_is_usable(exit_long_quote) and _quote_is_usable(exit_short_quote)
    resolved_entry_price = _entry_debit(entry_long_quote, entry_short_quote)
    resolved_exit_price = _exit_credit(exit_long_quote, exit_short_quote)
    has_entry_bid_ask = source_has_entry_bid_ask or existing_entry_bid_ask
    has_exit_bid_ask = source_has_exit_bid_ask or existing_exit_bid_ask
    has_side_entry = (source_has_entry_bid_ask and _safe_float(row.get("entry_px")) is not None) or resolved_entry_price is not None
    has_side_exit = (source_has_exit_bid_ask and _safe_float(row.get("exit_px")) is not None) or resolved_exit_price is not None
    missing_quote = not has_entry_bid_ask or not has_exit_bid_ask
    existing_zero_bid = any(
        _quote_is_zero_or_untradable(quote)
        for quote in (entry_long_quote, entry_short_quote, exit_long_quote, exit_short_quote)
    )
    crossed_quote = source_crossed_quote or any(
        quote is not None
        and _safe_float(quote.get("bid")) is not None
        and _safe_float(quote.get("ask")) is not None
        and float(quote["bid"]) > float(quote["ask"])
        for quote in (entry_long_quote, entry_short_quote, exit_long_quote, exit_short_quote)
    )
    zero_bid = source_zero_bid or existing_zero_bid
    side_aware_entry_matches_source = resolved_entry_price is not None and _price_matches(resolved_entry_price, row.get("entry_px"))
    side_aware_exit_matches_source = resolved_exit_price is not None and _price_matches(resolved_exit_price, row.get("exit_px"))
    side_aware_mismatch = bool(
        (resolved_entry_price is not None and not side_aware_entry_matches_source)
        or (resolved_exit_price is not None and not side_aware_exit_matches_source)
    )
    policy_visible = bool(_norm(row.get("exit_reason")) and _norm(row.get("exit_fill_basis")))
    assignment_review = _assignment_expiration_review(row, long_leg, short_leg)

    blockers: list[str] = []
    if not parsed_leg_identity:
        blockers.append("source_run_missing_leg_identity")
    if not has_entry_bid_ask:
        blockers.append("missing_leg_level_entry_bid_ask")
    if not has_exit_bid_ask:
        blockers.append("missing_leg_level_exit_bid_ask")
    if not has_side_entry:
        blockers.append("missing_side_aware_entry_price")
    if not has_side_exit:
        blockers.append("missing_side_aware_exit_price")
    if not policy_visible:
        blockers.append("missing_policy_exit_condition")
    if not assignment_review["classification_available"]:
        blockers.append("missing_assignment_expiration_classification")
    if long_expiry and short_expiry and long_expiry != short_expiry:
        blockers.append("mismatched_long_short_expiration")
    if crossed_quote:
        blockers.append("crossed_leg_quote")
    if zero_bid:
        blockers.append("zero_bid_or_untradable_leg_quote")
    if side_aware_mismatch:
        blockers.append("side_aware_price_mismatch_with_source_run")

    return {
        "row_index": index,
        "candidate_identity": "|".join(
            [
                _norm(row.get("ticker")),
                _norm(row.get("date")),
                _norm(row.get("contract_symbol")),
                _norm(row.get("short_contract_symbol")),
            ]
        ),
        "ticker": row.get("ticker"),
        "entry_date": row.get("date"),
        "entry_time": row.get("entry_time") or row.get("entry_quote_time_et"),
        "exit_date": row.get("exit_date"),
        "exit_time": row.get("exit_time") or row.get("exit_quote_time_et"),
        "expiration": long_leg.get("expiry") or short_leg.get("expiry") or row.get("target_expiry"),
        "target_expiry": row.get("target_expiry"),
        "structure_type": row.get("strategy_type") or "unknown",
        "long_leg": long_leg,
        "short_leg": short_leg,
        "entry_quote_provenance": {
            "long_entry_quote_basis": row.get("long_entry_quote_basis"),
            "short_entry_quote_basis": row.get("short_entry_quote_basis"),
            "entry_contract_resolution": row.get("entry_contract_resolution"),
            "contract_selection_source": row.get("contract_selection_source"),
            "source_run_has_leg_level_bid_ask": source_has_entry_bid_ask,
            "existing_trusted_quote_pair": entry_pair,
            "side_aware_entry_price": resolved_entry_price,
            "source_entry_price": _safe_float(row.get("entry_px")),
            "side_aware_price_matches_source_run": side_aware_entry_matches_source,
        },
        "exit_quote_provenance": {
            "exit_fill_basis": row.get("exit_fill_basis"),
            "exit_reason": row.get("exit_reason"),
            "exit_monitoring_mode": row.get("exit_monitoring_mode"),
            "source_run_has_leg_level_bid_ask": source_has_exit_bid_ask,
            "existing_trusted_quote_pair": exit_pair,
            "side_aware_exit_price": resolved_exit_price,
            "source_exit_price": _safe_float(row.get("exit_px")),
            "side_aware_price_matches_source_run": side_aware_exit_matches_source,
        },
        "parsed_leg_identity": parsed_leg_identity,
        "source_run_has_leg_level_entry_bid_ask": source_has_entry_bid_ask,
        "source_run_has_leg_level_exit_bid_ask": source_has_exit_bid_ask,
        "existing_trusted_entry_leg_bid_ask": existing_entry_bid_ask,
        "existing_trusted_exit_leg_bid_ask": existing_exit_bid_ask,
        "has_leg_level_entry_bid_ask": has_entry_bid_ask,
        "has_leg_level_exit_bid_ask": has_exit_bid_ask,
        "has_side_aware_entry_price": has_side_entry,
        "has_side_aware_exit_price": has_side_exit,
        "side_aware_entry_price_matches_source_run": side_aware_entry_matches_source,
        "side_aware_exit_price_matches_source_run": side_aware_exit_matches_source,
        "side_aware_price_mismatch_with_source_run": side_aware_mismatch,
        "zero_bid_or_untradable": zero_bid,
        "crossed_or_missing_quote": crossed_quote or missing_quote,
        "assignment_expiration_review": assignment_review,
        "policy_exit_condition_visible": policy_visible,
        "future_denominator_status": "blocked_until_future_row_has_leg_level_bid_ask_and_policy_exit",
        "fatal_blockers": blockers,
    }


def _row_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_selected_rows": len(rows),
        "rows_with_parsed_leg_identity": sum(1 for row in rows if row.get("parsed_leg_identity")),
        "rows_with_source_run_leg_level_entry_bid_ask": sum(1 for row in rows if row.get("source_run_has_leg_level_entry_bid_ask")),
        "rows_with_source_run_leg_level_exit_bid_ask": sum(1 for row in rows if row.get("source_run_has_leg_level_exit_bid_ask")),
        "rows_with_existing_trusted_entry_leg_bid_ask": sum(1 for row in rows if row.get("existing_trusted_entry_leg_bid_ask")),
        "rows_with_existing_trusted_exit_leg_bid_ask": sum(1 for row in rows if row.get("existing_trusted_exit_leg_bid_ask")),
        "rows_with_leg_level_entry_bid_ask": sum(1 for row in rows if row.get("has_leg_level_entry_bid_ask")),
        "rows_with_leg_level_exit_bid_ask": sum(1 for row in rows if row.get("has_leg_level_exit_bid_ask")),
        "rows_with_side_aware_entry_price": sum(1 for row in rows if row.get("has_side_aware_entry_price")),
        "rows_with_side_aware_exit_price": sum(1 for row in rows if row.get("has_side_aware_exit_price")),
        "rows_with_side_aware_entry_price_matching_source_run": sum(
            1 for row in rows if row.get("side_aware_entry_price_matches_source_run")
        ),
        "rows_with_side_aware_exit_price_matching_source_run": sum(
            1 for row in rows if row.get("side_aware_exit_price_matches_source_run")
        ),
        "rows_with_side_aware_price_mismatch": sum(1 for row in rows if row.get("side_aware_price_mismatch_with_source_run")),
        "rows_with_assignment_expiration_classification": sum(
            1 for row in rows if _as_dict(row.get("assignment_expiration_review")).get("classification_available")
        ),
        "rows_missing_policy_exit_condition": sum(1 for row in rows if not row.get("policy_exit_condition_visible")),
        "zero_bid_or_untradable_rows": sum(1 for row in rows if row.get("zero_bid_or_untradable")),
        "crossed_or_missing_quote_rows": sum(1 for row in rows if row.get("crossed_or_missing_quote")),
        "fatal_blocker_count": sum(1 for row in rows if _as_list(row.get("fatal_blockers"))),
    }


def _source_blockers(source_artifacts: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name, meta in source_artifacts.items():
        if meta.get("required") and meta.get("status") != "loaded":
            blockers.append(f"{name}:{','.join(_as_list(meta.get('reason_codes')))}")
    return blockers


def _status(blockers: list[str], counts: dict[str, Any]) -> str:
    if blockers or counts.get("fatal_blocker_count"):
        return "blocked_execution_safety_preflight"
    return "ready_for_future_market_window_paper_shadow_preflight"


def build_report(
    *,
    layer_stack_path: Path = DEFAULT_LAYER_STACK,
    layer_shadow_selection_path: Path = DEFAULT_LAYER_SHADOW_SELECTION,
    selected_source_run_path: Path = DEFAULT_SELECTED_SOURCE_RUN,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    layer_stack, layer_stack_source = _load_json_artifact(
        layer_stack_path,
        name="bullish_pullback_layer_stack",
        required=True,
        generated_at_utc=generated_at,
        max_age_hours=max_source_age_hours,
    )
    selector, selector_source = _load_json_artifact(
        layer_shadow_selection_path,
        name="bullish_pullback_layer_shadow_selection",
        required=True,
        generated_at_utc=generated_at,
        max_age_hours=max_source_age_hours,
    )
    source_run, source_run_source = _load_json_artifact(
        selected_source_run_path,
        name="selected_layer_source_run",
        required=True,
        generated_at_utc=generated_at,
        max_age_hours=max_source_age_hours,
    )
    source_artifacts = {
        "bullish_pullback_layer_stack": layer_stack_source,
        "bullish_pullback_layer_shadow_selection": selector_source,
        "selected_layer_source_run": source_run_source,
    }
    quote_store = _db_meta(options_history_db_path, source_labels)
    blockers = _source_blockers(source_artifacts)
    diagnostics: list[str] = []

    layers = _layers_by_id(layer_stack)
    primary_layer = layers.get(PRIMARY_LAYER_ID, {})
    primary_selector = _as_dict(selector.get("primary_harness_layer"))
    selector_requirements = _as_dict(selector.get("harness_requirements"))

    if layer_stack and layer_stack.get("paper_shadow_only") is not True:
        blockers.append("layer_stack_not_paper_shadow_only")
    if selector and selector.get("overall_status") != "layer_shadow_selection_ready":
        blockers.append("layer_shadow_selection_not_ready")
    if not primary_layer:
        blockers.append(f"missing_selected_layer:{PRIMARY_LAYER_ID}")
    if primary_layer and _norm(primary_layer.get("variant_id")) != PRIMARY_VARIANT_ID:
        blockers.append("selected_layer_variant_drift")
    if primary_selector and _norm(primary_selector.get("layer_id")) != PRIMARY_LAYER_ID:
        blockers.append("selector_primary_layer_drift")
    if primary_selector and _norm(primary_selector.get("variant_id")) != PRIMARY_VARIANT_ID:
        blockers.append("selector_primary_variant_drift")
    source_path_from_selector = _norm(selector_requirements.get("source_result_path") or primary_selector.get("source_result_path"))
    if source_path_from_selector and source_path_from_selector != _rel(selected_source_run_path):
        blockers.append("selector_source_result_path_drift")
    if primary_layer:
        blockers.extend(_metric_blockers(primary_layer))

    trades = [row for row in _as_list(source_run.get("trades")) if isinstance(row, dict)]
    if source_run and not trades:
        blockers.append("source_run_missing_trades")
    if trades and len(trades) != EXPECTED_METRICS["exact_trade_count"]:
        blockers.append(f"source_run_trade_count_expected_{EXPECTED_METRICS['exact_trade_count']}_got_{len(trades)}")

    source_rows_have_leg_quotes = bool(trades) and all(_has_leg_entry_bid_ask(row) and _has_leg_exit_bid_ask(row) for row in trades)
    quote_cache: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
    entry_exit_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if trades and not source_rows_have_leg_quotes and quote_store.get("status") == "loaded":
        try:
            with closing(_sqlite_readonly_connect(options_history_db_path)) as conn:
                trusted_batch_ids = _trusted_source_batch_ids(conn, source_labels)
                if not trusted_batch_ids:
                    blockers.append("existing_quote_lookup_unavailable_no_trusted_source_batches")
                for row in trades:
                    long_contract = _norm(row.get("contract_symbol")).upper()
                    short_contract = _norm(row.get("short_contract_symbol")).upper()
                    entry_date = _norm(row.get("date"))[:10]
                    exit_date = _norm(row.get("exit_date"))[:10]
                    if trusted_batch_ids and long_contract and short_contract and entry_date:
                        entry_pair = _quote_pair_at_minute(
                            conn,
                            long_contract=long_contract,
                            short_contract=short_contract,
                            quote_date_et=entry_date,
                            minute_et=DEFAULT_ENTRY_MINUTE_ET,
                            trusted_batch_ids=trusted_batch_ids,
                            cache=quote_cache,
                        )
                    else:
                        entry_pair = {"lookup_rule": "not_attempted_missing_leg_identity_or_entry_date"}
                    if trusted_batch_ids and long_contract and short_contract and exit_date:
                        exit_pair = _latest_common_quote_pair(
                            conn,
                            long_contract=long_contract,
                            short_contract=short_contract,
                            quote_date_et=exit_date,
                            latest_minute_et=DEFAULT_EXIT_MINUTE_ET,
                            trusted_batch_ids=trusted_batch_ids,
                            cache=quote_cache,
                        )
                    else:
                        exit_pair = {"lookup_rule": "not_attempted_missing_leg_identity_or_exit_date"}
                    entry_exit_pairs.append((entry_pair, exit_pair))
        except sqlite3.Error as exc:
            quote_store["status"] = "unreadable"
            quote_store["error"] = type(exc).__name__
            blockers.append("existing_quote_lookup_unavailable")
    elif trades and not source_rows_have_leg_quotes and quote_store.get("status") != "loaded":
        blockers.append("existing_quote_lookup_unavailable")

    if len(entry_exit_pairs) != len(trades):
        entry_exit_pairs = [({}, {}) for _ in trades]

    audited_rows = [
        _audit_row(row, index, entry_pair=entry_pair, exit_pair=exit_pair)
        for index, (row, (entry_pair, exit_pair)) in enumerate(zip(trades, entry_exit_pairs), start=1)
    ]
    counts = _row_counts(audited_rows)
    if trades and counts["rows_with_parsed_leg_identity"] < counts["total_selected_rows"]:
        blockers.append("source_run_missing_leg_identity")
    if trades and counts["rows_with_source_run_leg_level_entry_bid_ask"] < counts["total_selected_rows"]:
        diagnostics.append("source_run_missing_leg_level_entry_bid_ask")
    if trades and counts["rows_with_source_run_leg_level_exit_bid_ask"] < counts["total_selected_rows"]:
        diagnostics.append("source_run_missing_leg_level_exit_bid_ask")
    if (
        trades
        and not source_rows_have_leg_quotes
        and counts["rows_with_existing_trusted_entry_leg_bid_ask"] < counts["total_selected_rows"]
    ):
        blockers.append("existing_trusted_leg_entry_quotes_missing")
    if (
        trades
        and not source_rows_have_leg_quotes
        and counts["rows_with_existing_trusted_exit_leg_bid_ask"] < counts["total_selected_rows"]
    ):
        blockers.append("existing_trusted_leg_exit_quotes_missing")
    if trades and (
        counts["rows_with_side_aware_entry_price"] < counts["total_selected_rows"]
        or counts["rows_with_side_aware_exit_price"] < counts["total_selected_rows"]
    ):
        blockers.append("existing_trusted_side_aware_bid_ask_prices_missing")
    if trades and counts["crossed_or_missing_quote_rows"]:
        blockers.append("existing_trusted_missing_or_crossed_quote_fields")
    if trades and counts["zero_bid_or_untradable_rows"]:
        blockers.append("existing_trusted_zero_bid_or_untradable_leg_quote")
    if trades and counts["rows_with_side_aware_price_mismatch"]:
        blockers.append("existing_trusted_side_aware_price_mismatch_with_source_run")

    unique_blockers = sorted(set(blockers))
    unique_diagnostics = sorted(set(diagnostics))
    status = _status(unique_blockers, counts)
    fatal_reason_counts = Counter(reason for row in audited_rows for reason in _as_list(row.get("fatal_blockers")))

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "bullish_pullback_layer_4_execution_safety_preflight",
        "read_only": True,
        "paper_shadow_only": True,
        "overall_status": status,
        "preflight_ready": status == "ready_for_future_market_window_paper_shadow_preflight",
        "source_artifacts": source_artifacts,
        "existing_quote_store": quote_store,
        "existing_quote_resolution": {
            "enabled": True,
            "read_only": True,
            "entry_lookup_rule": f"exact trusted quote at {DEFAULT_ENTRY_MINUTE_ET // 60:02d}:{DEFAULT_ENTRY_MINUTE_ET % 60:02d} ET",
            "exit_lookup_rule": f"latest common trusted quote at or before {DEFAULT_EXIT_MINUTE_ET // 60:02d}:{DEFAULT_EXIT_MINUTE_ET % 60:02d} ET",
            "source_labels": list(_source_labels(source_labels)),
            "side_aware_entry_price_formula": "long_ask_minus_short_bid",
            "side_aware_exit_price_formula": "long_bid_minus_short_ask",
            "side_aware_price_tolerance": SIDE_AWARE_PRICE_TOLERANCE,
        },
        "selected_layer": {
            "layer_id": PRIMARY_LAYER_ID,
            "variant_id": PRIMARY_VARIANT_ID,
            "source_result_path": _rel(selected_source_run_path),
            "metrics": {key: _metric(primary_layer, key) for key in EXPECTED_METRICS},
        },
        "selector_primary": {
            "layer_id": primary_selector.get("layer_id"),
            "variant_id": primary_selector.get("variant_id"),
            "source_result_path": primary_selector.get("source_result_path"),
        },
        "row_counts": counts,
        "fatal_reason_counts": dict(sorted(fatal_reason_counts.items())),
        "blockers": unique_blockers,
        "diagnostics": unique_diagnostics,
        "audit_rows": audited_rows,
        "preflight_requirements": {
            "exact_entry_quote_required": True,
            "policy_defined_exact_exit_required": True,
            "leg_level_bid_ask_audit_required": True,
            "assignment_expiration_risk_review_required": True,
            "denominator_failure_row_handling_required": True,
            "trusted_exact_opra_nbbo_only": True,
        },
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "is_trade_recommendation": False,
        "mutated_evidence_databases": False,
        "imported_quotes": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_live_validation": False,
        "changed_auto_track_behavior": False,
        "changed_broker_behavior": False,
        "appended_forward_cohort_rows": False,
        "consumed_protected_holdout": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    counts = _as_dict(report.get("row_counts"))
    selected = _as_dict(report.get("selected_layer"))
    lines = [
        "# Regular Options Bullish-Pullback Layer Execution-Safety Audit",
        "",
        f"Status: `{report.get('overall_status')}`.",
        "",
        "This is a read-only preflight for future paper-shadow harness work. It does not collect market evidence, create trades, submit broker orders, import quotes, mutate evidence stores, change scanner policy, change strategy/stops/sizing/proof bars, enable live validation, enable auto-track, consume protected holdout, append forward cohort rows, or promote a lane.",
        "",
        "## Selected Harness",
        "",
        f"- Layer: `{selected.get('layer_id')}`.",
        f"- Variant: `{selected.get('variant_id')}`.",
        f"- Source run: `{selected.get('source_result_path')}`.",
        f"- Metrics: `{_json_inline(selected.get('metrics') or {})}`.",
        "",
        "## Preflight Counts",
        "",
    ]
    for key in (
        "total_selected_rows",
        "rows_with_parsed_leg_identity",
        "rows_with_source_run_leg_level_entry_bid_ask",
        "rows_with_source_run_leg_level_exit_bid_ask",
        "rows_with_existing_trusted_entry_leg_bid_ask",
        "rows_with_existing_trusted_exit_leg_bid_ask",
        "rows_with_leg_level_entry_bid_ask",
        "rows_with_leg_level_exit_bid_ask",
        "rows_with_side_aware_entry_price",
        "rows_with_side_aware_exit_price",
        "rows_with_side_aware_entry_price_matching_source_run",
        "rows_with_side_aware_exit_price_matching_source_run",
        "rows_with_side_aware_price_mismatch",
        "rows_with_assignment_expiration_classification",
        "rows_missing_policy_exit_condition",
        "zero_bid_or_untradable_rows",
        "crossed_or_missing_quote_rows",
        "fatal_blocker_count",
    ):
        lines.append(f"- `{key}`: `{counts.get(key)}`.")
    lines.extend(["", "## Blockers", ""])
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{reason}`" for reason in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Diagnostics", ""])
    diagnostics = _as_list(report.get("diagnostics"))
    if diagnostics:
        lines.extend(f"- `{reason}`" for reason in diagnostics)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Existing Quote Resolution",
            "",
            f"- Quote store: `{_json_inline(report.get('existing_quote_store') or {})}`.",
            f"- Resolution rules: `{_json_inline(report.get('existing_quote_resolution') or {})}`.",
            "",
            f"Fatal reason counts: `{_json_inline(report.get('fatal_reason_counts') or {})}`.",
            "",
            "## Source Artifacts",
            "",
            "| Source | Status | Age hours | Generated at | Reasons |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for name, meta in sorted(_as_dict(report.get("source_artifacts")).items()):
        lines.append(
            f"| `{name}` | `{meta.get('status')}` | `{meta.get('age_hours')}` | `{meta.get('generated_at_utc')}` | `{_json_inline(meta.get('reason_codes') or [])}` |"
        )
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only bullish-pullback layer execution-safety audit.")
    parser.add_argument("--layer-stack", type=Path, default=DEFAULT_LAYER_STACK)
    parser.add_argument("--layer-shadow-selection", type=Path, default=DEFAULT_LAYER_SHADOW_SELECTION)
    parser.add_argument("--selected-source-run", type=Path, default=DEFAULT_SELECTED_SOURCE_RUN)
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
    parser.add_argument("--source-label", action="append", dest="source_labels", default=None)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        layer_stack_path=args.layer_stack,
        layer_shadow_selection_path=args.layer_shadow_selection,
        selected_source_run_path=args.selected_source_run,
        options_history_db_path=args.options_history_db,
        source_labels=tuple(args.source_labels or DEFAULT_SOURCE_LABELS),
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
