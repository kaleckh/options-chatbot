from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from local_env import load_local_env
except Exception:  # pragma: no cover - import fallback for minimal test contexts
    load_local_env = None  # type: ignore[assignment]

if load_local_env is not None:
    load_local_env(ROOT)

REPORT_ID = "regular_options_execution_alternative_replay_coverage"
DEFAULT_READINESS = ROOT / "data" / "forward-tracking" / "regular_options_execution_alternative_replay_readiness_latest.json"
DEFAULT_DB_PATH = Path(os.getenv("HISTORICAL_OPTIONS_DB_PATH", str(ROOT / "data" / "options-validation" / "options_history.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-execution-alternative-replay-coverage.md"

EASTERN_TZ = ZoneInfo("America/New_York")
DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)
INTRADAY_SNAPSHOT_KIND = "intraday"
TRUSTED_DATA_TRUST = "trusted"
DEFAULT_EXIT_MINUTE_ET = 15 * 60 + 55

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_execution_alternative_replay_coverage",
    "do_not_submit_broker_order_from_execution_alternative_replay_coverage",
    "do_not_mutate_database_from_execution_alternative_replay_coverage",
    "do_not_change_scanner_policy_from_execution_alternative_replay_coverage",
    "do_not_change_contract_selection_from_execution_alternative_replay_coverage",
    "do_not_change_stop_policy_from_execution_alternative_replay_coverage",
    "do_not_change_sizing_from_execution_alternative_replay_coverage",
    "do_not_synthesize_alternative_pnl_from_midpoint_daily_stale_or_display_marks",
    "do_not_promote_replay_coverage_rows_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    return payload, meta


def _has_live_policy_change(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "live_policy_change" and bool(item):
                return True
            if _has_live_policy_change(item):
                return True
    if isinstance(value, list):
        return any(_has_live_policy_change(item) for item in value)
    return False


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _source_labels_clause(source_labels: Sequence[str]) -> tuple[str, list[Any]]:
    labels = [str(label).strip() for label in source_labels if str(label).strip()]
    if not labels:
        return "", []
    placeholders = ", ".join("?" for _ in labels)
    return f" AND b.source_label IN ({placeholders})", labels


def _minute_window(center: int, width: int) -> tuple[int, int]:
    return max(0, int(center) - max(int(width), 0)), min((24 * 60) - 1, int(center) + max(int(width), 0))


def _entry_date_minute(entry_time_utc: Any, fallback_date: Any = None) -> tuple[str | None, int | None]:
    raw = _norm(entry_time_utc)
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            as_et = parsed.astimezone(EASTERN_TZ)
            return as_et.date().isoformat(), as_et.hour * 60 + as_et.minute
    fallback = _norm(fallback_date)
    if fallback:
        return fallback[:10], None
    return None, None


def _quote_lookup(
    conn: sqlite3.Connection,
    *,
    contract_symbol: str,
    quote_date_et: str,
    center_minute_et: int,
    window_minutes: int,
    source_labels: Sequence[str],
) -> dict[str, Any] | None:
    start_minute, end_minute = _minute_window(center_minute_et, window_minutes)
    source_clause, source_params = _source_labels_clause(source_labels)
    row = conn.execute(
        f"""
        SELECT
            q.contract_symbol,
            q.quote_date_et,
            q.quote_minute_et,
            q.as_of_utc,
            q.bid,
            q.ask,
            q.underlying_price,
            q.volume,
            q.open_interest,
            b.source_label,
            b.data_trust
        FROM option_quote_snapshots q INDEXED BY idx_option_quotes_contract_date
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.contract_symbol = ?
          AND q.snapshot_kind = ?
          AND q.quote_date_et = ?
          AND q.quote_minute_et >= ?
          AND q.quote_minute_et <= ?
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.bid >= 0
          AND q.ask > 0
          AND q.ask >= q.bid
          AND b.data_trust = ?
          {source_clause}
        ORDER BY ABS(q.quote_minute_et - ?) ASC, q.quote_minute_et ASC, q.as_of_utc ASC
        LIMIT 1
        """,
        (
            contract_symbol,
            INTRADAY_SNAPSHOT_KIND,
            quote_date_et,
            start_minute,
            end_minute,
            TRUSTED_DATA_TRUST,
            *source_params,
            int(center_minute_et),
        ),
    ).fetchone()
    if row is None:
        return None
    bid = _safe_float(row["bid"])
    ask = _safe_float(row["ask"])
    if bid is None or ask is None:
        return None
    return {
        "contract_symbol": str(row["contract_symbol"]),
        "quote_date_et": str(row["quote_date_et"]),
        "quote_minute_et": int(row["quote_minute_et"]),
        "as_of_utc": str(row["as_of_utc"]),
        "bid": round(float(bid), 4),
        "ask": round(float(ask), 4),
        "underlying_price": _safe_float(row["underlying_price"]),
        "volume": row["volume"],
        "open_interest": row["open_interest"],
        "source_label": str(row["source_label"]),
        "data_trust": str(row["data_trust"]),
        "quote_evidence_class": "trusted_intraday_opra_nbbo",
    }


def _pair_identity(long_symbol: Any, short_symbol: Any) -> tuple[str, str]:
    return _norm(long_symbol).upper(), _norm(short_symbol).upper()


def _first_distinct_replacement(row: dict[str, Any]) -> dict[str, Any] | None:
    selected = _pair_identity(row.get("selected_long_contract_symbol"), row.get("selected_short_contract_symbol"))
    for alt in _as_list(row.get("top_alternatives")):
        alt = _as_dict(alt)
        pair = _pair_identity(alt.get("long_contract_symbol"), alt.get("short_contract_symbol"))
        if pair[0] and pair[1] and pair != selected:
            return alt
    return None


def _quote_public(quote: dict[str, Any] | None) -> dict[str, Any] | None:
    if quote is None:
        return None
    return {
        "contract_symbol": quote.get("contract_symbol"),
        "quote_date_et": quote.get("quote_date_et"),
        "quote_minute_et": quote.get("quote_minute_et"),
        "as_of_utc": quote.get("as_of_utc"),
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "source_label": quote.get("source_label"),
        "data_trust": quote.get("data_trust"),
        "quote_evidence_class": quote.get("quote_evidence_class"),
    }


def _entry_debit(long_quote: dict[str, Any], short_quote: dict[str, Any]) -> float | None:
    long_ask = _safe_float(long_quote.get("ask"))
    short_bid = _safe_float(short_quote.get("bid"))
    if long_ask is None or short_bid is None:
        return None
    debit = round(long_ask - short_bid, 4)
    return debit if debit > 0 else None


def _exit_value(long_quote: dict[str, Any], short_quote: dict[str, Any]) -> float | None:
    long_bid = _safe_float(long_quote.get("bid"))
    short_ask = _safe_float(short_quote.get("ask"))
    if long_bid is None or short_ask is None:
        return None
    return round(long_bid - short_ask, 4)


def _evaluate_pair(
    conn: sqlite3.Connection,
    *,
    label: str,
    long_symbol: str,
    short_symbol: str,
    entry_date_et: str | None,
    entry_minute_et: int | None,
    scan_date: str | None,
    exit_minute_et: int,
    entry_window_minutes: int,
    exit_window_minutes: int,
    source_labels: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": label,
        "long_contract_symbol": long_symbol or None,
        "short_contract_symbol": short_symbol or None,
        "entry_quote_date_et": entry_date_et,
        "entry_quote_minute_et": entry_minute_et,
        "exit_quote_date_et": scan_date,
        "exit_quote_minute_et": exit_minute_et,
        "entry_pair_complete": False,
        "exit_pair_complete": False,
        "true_side_aware_pnl_available": False,
        "blockers": [],
    }
    blockers: list[str] = []
    if not long_symbol:
        blockers.append("missing_long_contract_symbol")
    if not short_symbol:
        blockers.append("missing_short_contract_symbol")
    if not entry_date_et or entry_minute_et is None:
        blockers.append("missing_entry_quote_time")
    if not scan_date:
        blockers.append("missing_exit_quote_date")
    if blockers:
        result["blockers"] = blockers
        return result

    entry_long = _quote_lookup(
        conn,
        contract_symbol=long_symbol,
        quote_date_et=entry_date_et,
        center_minute_et=entry_minute_et,
        window_minutes=entry_window_minutes,
        source_labels=source_labels,
    )
    entry_short = _quote_lookup(
        conn,
        contract_symbol=short_symbol,
        quote_date_et=entry_date_et,
        center_minute_et=entry_minute_et,
        window_minutes=entry_window_minutes,
        source_labels=source_labels,
    )
    exit_long = _quote_lookup(
        conn,
        contract_symbol=long_symbol,
        quote_date_et=scan_date,
        center_minute_et=exit_minute_et,
        window_minutes=exit_window_minutes,
        source_labels=source_labels,
    )
    exit_short = _quote_lookup(
        conn,
        contract_symbol=short_symbol,
        quote_date_et=scan_date,
        center_minute_et=exit_minute_et,
        window_minutes=exit_window_minutes,
        source_labels=source_labels,
    )

    result.update(
        {
            "entry_long_quote": _quote_public(entry_long),
            "entry_short_quote": _quote_public(entry_short),
            "exit_long_quote": _quote_public(exit_long),
            "exit_short_quote": _quote_public(exit_short),
        }
    )
    if entry_long is None:
        blockers.append("missing_entry_long_quote")
    if entry_short is None:
        blockers.append("missing_entry_short_quote")
    if exit_long is None:
        blockers.append("missing_exit_long_quote")
    if exit_short is None:
        blockers.append("missing_exit_short_quote")

    result["entry_pair_complete"] = entry_long is not None and entry_short is not None
    result["exit_pair_complete"] = exit_long is not None and exit_short is not None
    if result["entry_pair_complete"] and result["exit_pair_complete"]:
        entry_debit = _entry_debit(entry_long, entry_short)  # type: ignore[arg-type]
        exit_value = _exit_value(exit_long, exit_short)  # type: ignore[arg-type]
        if entry_debit is not None and exit_value is not None:
            pnl_per_spread = round(exit_value - entry_debit, 4)
            result.update(
                {
                    "entry_side_aware_debit": entry_debit,
                    "exit_side_aware_value": exit_value,
                    "gross_pnl_per_spread": pnl_per_spread,
                    "gross_pnl_pct": round((pnl_per_spread / entry_debit) * 100.0, 2),
                    "true_side_aware_pnl_available": True,
                }
            )
        else:
            blockers.append("non_positive_entry_side_aware_debit")
    result["blockers"] = blockers
    return result


def _coverage_status(complete_count: int, candidate_count: int) -> str:
    if candidate_count <= 0:
        return "not_applicable"
    if complete_count == candidate_count:
        return "full"
    if complete_count > 0:
        return "partial"
    return "missing"


def _coverage_blocker(prefix: str, complete_count: int, candidate_count: int, *, missing_name: str, partial_name: str) -> str | None:
    if candidate_count <= 0 or complete_count == candidate_count:
        return None
    return missing_name if complete_count == 0 else partial_name


def _build_coverage_rows(
    readiness: dict[str, Any],
    *,
    db_path: Path,
    exit_minute_et: int,
    entry_window_minutes: int,
    exit_window_minutes: int,
    source_labels: Sequence[str],
) -> list[dict[str, Any]]:
    seed_rows = [
        _as_dict(row)
        for row in _as_list(readiness.get("candidate_queue"))
        if _norm(_as_dict(row).get("readiness_status"))
        in {"alternative_seed_ready_engine_missing", "top_alternative_seed_ready_no_replacement_candidate"}
    ]
    rows: list[dict[str, Any]] = []
    with closing(_sqlite_readonly_connect(db_path)) as conn:
        for seed in seed_rows:
            entry_date_et, entry_minute_et = _entry_date_minute(seed.get("entry_time_utc"), seed.get("scan_date"))
            selected_long, selected_short = _pair_identity(
                seed.get("selected_long_contract_symbol"),
                seed.get("selected_short_contract_symbol"),
            )
            top_alt = _as_dict(_as_list(seed.get("top_alternatives"))[0]) if _as_list(seed.get("top_alternatives")) else {}
            top_long, top_short = _pair_identity(top_alt.get("long_contract_symbol"), top_alt.get("short_contract_symbol"))
            replacement_alt = _first_distinct_replacement(seed)
            replacement_long, replacement_short = _pair_identity(
                _as_dict(replacement_alt).get("long_contract_symbol"),
                _as_dict(replacement_alt).get("short_contract_symbol"),
            )

            selected_eval = _evaluate_pair(
                conn,
                label="selected",
                long_symbol=selected_long,
                short_symbol=selected_short,
                entry_date_et=entry_date_et,
                entry_minute_et=entry_minute_et,
                scan_date=_norm(seed.get("scan_date"))[:10],
                exit_minute_et=exit_minute_et,
                entry_window_minutes=entry_window_minutes,
                exit_window_minutes=exit_window_minutes,
                source_labels=source_labels,
            )
            top_eval = _evaluate_pair(
                conn,
                label="top_spread",
                long_symbol=top_long,
                short_symbol=top_short,
                entry_date_et=entry_date_et,
                entry_minute_et=entry_minute_et,
                scan_date=_norm(seed.get("scan_date"))[:10],
                exit_minute_et=exit_minute_et,
                entry_window_minutes=entry_window_minutes,
                exit_window_minutes=exit_window_minutes,
                source_labels=source_labels,
            )
            replacement_eval = (
                _evaluate_pair(
                    conn,
                    label="contract_replacement",
                    long_symbol=replacement_long,
                    short_symbol=replacement_short,
                    entry_date_et=entry_date_et,
                    entry_minute_et=entry_minute_et,
                    scan_date=_norm(seed.get("scan_date"))[:10],
                    exit_minute_et=exit_minute_et,
                    entry_window_minutes=entry_window_minutes,
                    exit_window_minutes=exit_window_minutes,
                    source_labels=source_labels,
                )
                if replacement_long and replacement_short
                else None
            )

            row_blockers = sorted(
                set(
                    str(blocker)
                    for evaluation in (selected_eval, top_eval, replacement_eval)
                    if isinstance(evaluation, dict)
                    for blocker in _as_list(evaluation.get("blockers"))
                    if blocker
                )
            )
            rows.append(
                {
                    "row_index": seed.get("row_index"),
                    "ticker": seed.get("ticker"),
                    "lane": seed.get("lane"),
                    "scan_date": seed.get("scan_date"),
                    "entry_time_utc": seed.get("entry_time_utc"),
                    "entry_quote_date_et": entry_date_et,
                    "entry_quote_minute_et": entry_minute_et,
                    "exit_quote_minute_et": exit_minute_et,
                    "selected": selected_eval,
                    "top_spread": top_eval,
                    "contract_replacement": replacement_eval,
                    "row_true_top_spread_replay_pnl": bool(top_eval.get("true_side_aware_pnl_available")),
                    "row_true_contract_replacement_pnl": bool(
                        isinstance(replacement_eval, dict) and replacement_eval.get("true_side_aware_pnl_available")
                    ),
                    "blockers": row_blockers,
                }
            )
    return rows


def _summary_from_rows(rows: list[dict[str, Any]], *, readiness: dict[str, Any], missing_required: list[str], quote_store_error: str | None, live_policy_change: bool) -> dict[str, Any]:
    top_count = sum(1 for row in rows if isinstance(row.get("top_spread"), dict))
    replacement_count = sum(1 for row in rows if isinstance(row.get("contract_replacement"), dict))
    selected_entry = sum(1 for row in rows if _as_dict(row.get("selected")).get("entry_pair_complete"))
    selected_exit = sum(1 for row in rows if _as_dict(row.get("selected")).get("exit_pair_complete"))
    top_entry = sum(1 for row in rows if _as_dict(row.get("top_spread")).get("entry_pair_complete"))
    top_exit = sum(1 for row in rows if _as_dict(row.get("top_spread")).get("exit_pair_complete"))
    replacement_entry = sum(1 for row in rows if _as_dict(row.get("contract_replacement")).get("entry_pair_complete"))
    replacement_exit = sum(1 for row in rows if _as_dict(row.get("contract_replacement")).get("exit_pair_complete"))
    true_top = sum(1 for row in rows if bool(row.get("row_true_top_spread_replay_pnl")))
    true_replacement = sum(1 for row in rows if bool(row.get("row_true_contract_replacement_pnl")))

    blocker_items = [
        _coverage_blocker(
            "top",
            top_entry,
            top_count,
            missing_name="top_spread_entry_quote_coverage_missing",
            partial_name="top_spread_entry_quote_coverage_partial",
        ),
        _coverage_blocker(
            "top",
            top_exit,
            top_count,
            missing_name="alternate_contract_exit_quote_coverage_missing",
            partial_name="alternate_contract_exit_quote_coverage_partial",
        ),
        _coverage_blocker(
            "replacement",
            replacement_entry,
            replacement_count,
            missing_name="contract_replacement_entry_quote_coverage_missing",
            partial_name="contract_replacement_entry_quote_coverage_partial",
        ),
        _coverage_blocker(
            "replacement",
            replacement_exit,
            replacement_count,
            missing_name="contract_replacement_exit_quote_coverage_missing",
            partial_name="contract_replacement_exit_quote_coverage_partial",
        ),
    ]
    if top_count and true_top == 0:
        blocker_items.append("true_top_spread_replay_pnl_rows_missing")
    elif true_top < top_count:
        blocker_items.append("true_top_spread_replay_pnl_rows_incomplete")
    if replacement_count and true_replacement == 0:
        blocker_items.append("true_contract_replacement_pnl_rows_missing")
    elif true_replacement < replacement_count:
        blocker_items.append("true_contract_replacement_pnl_rows_incomplete")
    if not rows and not missing_required:
        blocker_items.append("no_execution_alternative_seed_rows")
    if quote_store_error:
        blocker_items.append("quote_store_read_error")
    blocker_items.extend(missing_required)
    blockers = sorted(set(str(item) for item in blocker_items if item))

    if live_policy_change:
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        overall_status = "blocked_missing_inputs"
    elif quote_store_error:
        overall_status = "blocked_quote_store_unreadable"
    elif top_count > 0 and true_top == top_count and true_replacement == replacement_count:
        overall_status = "execution_alternative_replay_coverage_ready"
    elif true_top or true_replacement:
        overall_status = "execution_alternative_replay_partial_true_pnl_blocked"
    elif top_entry or top_exit or replacement_entry or replacement_exit:
        overall_status = "blocked_partial_quote_coverage_no_true_replay_pnl"
    else:
        overall_status = "blocked_missing_execution_alternative_quote_coverage"

    return {
        "overall_status": overall_status,
        "readiness_status": readiness.get("status"),
        "candidate_seed_count": len(rows),
        "top_spread_candidate_count": top_count,
        "contract_replacement_candidate_count": replacement_count,
        "selected_entry_pair_complete_count": selected_entry,
        "selected_exit_pair_complete_count": selected_exit,
        "top_spread_entry_pair_complete_count": top_entry,
        "top_spread_exit_pair_complete_count": top_exit,
        "contract_replacement_entry_pair_complete_count": replacement_entry,
        "contract_replacement_exit_pair_complete_count": replacement_exit,
        "true_top_spread_replay_pnl_count": true_top,
        "true_contract_replacement_pnl_count": true_replacement,
        "selected_entry_quote_coverage_status": _coverage_status(selected_entry, len(rows)),
        "selected_exit_quote_coverage_status": _coverage_status(selected_exit, len(rows)),
        "top_spread_entry_quote_coverage_status": _coverage_status(top_entry, top_count),
        "top_spread_exit_quote_coverage_status": _coverage_status(top_exit, top_count),
        "contract_replacement_entry_quote_coverage_status": _coverage_status(replacement_entry, replacement_count),
        "contract_replacement_exit_quote_coverage_status": _coverage_status(replacement_exit, replacement_count),
        "alternative_exit_quote_coverage_status": _coverage_status(top_exit + replacement_exit, top_count + replacement_count),
        "liquidity_first_replay_engine_status": "read_only_side_aware_engine_partial"
        if true_top
        else "read_only_side_aware_engine_waiting_for_quote_coverage",
        "contract_replacement_replay_engine_status": "read_only_side_aware_engine_partial"
        if true_replacement
        else "read_only_side_aware_engine_waiting_for_quote_coverage",
        "missing_required_inputs": missing_required,
        "quote_store_error": quote_store_error,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "live_policy_change": live_policy_change,
    }


def _add_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def _quote_demands_from_rows(
    rows: list[dict[str, Any]],
    *,
    entry_window_minutes: int,
    exit_window_minutes: int,
    source_labels: Sequence[str],
) -> list[dict[str, Any]]:
    role_map = {
        "missing_entry_long_quote": ("entry", "long", "long_contract_symbol", "entry_quote_date_et", "entry_quote_minute_et", entry_window_minutes),
        "missing_entry_short_quote": ("entry", "short", "short_contract_symbol", "entry_quote_date_et", "entry_quote_minute_et", entry_window_minutes),
        "missing_exit_long_quote": ("exit", "long", "long_contract_symbol", "exit_quote_date_et", "exit_quote_minute_et", exit_window_minutes),
        "missing_exit_short_quote": ("exit", "short", "short_contract_symbol", "exit_quote_date_et", "exit_quote_minute_et", exit_window_minutes),
    }
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        row = _as_dict(row)
        for label in ("selected", "top_spread", "contract_replacement"):
            evaluation = _as_dict(row.get(label))
            if not evaluation:
                continue
            blockers = set(str(item) for item in _as_list(evaluation.get("blockers")))
            for reason, (phase, leg, contract_key, date_key, minute_key, window_minutes) in role_map.items():
                if reason not in blockers:
                    continue
                contract_symbol = _norm(evaluation.get(contract_key)).upper()
                quote_date_et = _norm(evaluation.get(date_key))[:10]
                quote_minute_et = evaluation.get(minute_key)
                if not contract_symbol or not quote_date_et or quote_minute_et in {None, ""}:
                    continue
                try:
                    minute = int(quote_minute_et)
                except (TypeError, ValueError):
                    continue
                key = (
                    contract_symbol,
                    quote_date_et,
                    minute,
                    int(window_minutes),
                    phase,
                    tuple(source_labels),
                )
                priority = 0 if phase == "entry" and label in {"top_spread", "contract_replacement"} else 1
                if phase == "exit" and label in {"top_spread", "contract_replacement"}:
                    priority = 1
                if label == "selected":
                    priority = 2
                demand = by_key.setdefault(
                    key,
                    {
                        "priority": priority,
                        "contract_symbol": contract_symbol,
                        "quote_date_et": quote_date_et,
                        "quote_minute_et": minute,
                        "window_minutes": int(window_minutes),
                        "quote_phase": phase,
                        "source_labels": list(source_labels),
                        "snapshot_kind": INTRADAY_SNAPSHOT_KIND,
                        "data_trust": TRUSTED_DATA_TRUST,
                        "quote_evidence_class": "trusted_intraday_opra_nbbo",
                        "usage_labels": [],
                        "missing_reasons": [],
                        "source_rows": [],
                    },
                )
                demand["priority"] = min(int(demand["priority"]), priority)
                _add_unique(demand["usage_labels"], f"{label}:{phase}_{leg}")
                _add_unique(demand["missing_reasons"], reason)
                source_row = {
                    "row_index": row.get("row_index"),
                    "ticker": row.get("ticker"),
                    "lane": row.get("lane"),
                    "scan_date": row.get("scan_date"),
                    "evaluation_label": label,
                    "quote_phase": phase,
                    "leg": leg,
                    "missing_reason": reason,
                }
                if source_row not in demand["source_rows"]:
                    demand["source_rows"].append(source_row)
    demands = list(by_key.values())
    for demand in demands:
        demand["source_row_count"] = len(_as_list(demand.get("source_rows")))
    return sorted(
        demands,
        key=lambda item: (
            int(item.get("priority") or 0),
            str(item.get("quote_date_et") or ""),
            int(item.get("quote_minute_et") or 0),
            str(item.get("contract_symbol") or ""),
        ),
    )


def build_report(
    *,
    readiness_path: Path = DEFAULT_READINESS,
    db_path: Path = DEFAULT_DB_PATH,
    exit_minute_et: int = DEFAULT_EXIT_MINUTE_ET,
    entry_window_minutes: int = 0,
    exit_window_minutes: int = 0,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    readiness, readiness_meta = _load_json(readiness_path)
    missing_required: list[str] = []
    if readiness_meta.get("status") != "loaded":
        missing_required.append("execution_alternative_replay_readiness")
    db_meta = {"path": str(db_path), "exists": db_path.exists(), "status": "loaded" if db_path.exists() else "missing", "error": None}
    if not db_path.exists():
        db_meta["error"] = "missing_artifact"
        missing_required.append("options_history_db")
    live_policy_change = _has_live_policy_change(readiness)
    coverage_rows: list[dict[str, Any]] = []
    quote_store_error: str | None = None
    if not missing_required and not live_policy_change:
        try:
            coverage_rows = _build_coverage_rows(
                readiness,
                db_path=db_path,
                exit_minute_et=exit_minute_et,
                entry_window_minutes=entry_window_minutes,
                exit_window_minutes=exit_window_minutes,
                source_labels=source_labels,
            )
        except sqlite3.Error as exc:
            quote_store_error = f"{type(exc).__name__}: {exc}"
            db_meta["status"] = "unreadable"
            db_meta["error"] = quote_store_error

    status = (
        "invalid_live_policy_change"
        if live_policy_change
        else "blocked_missing_inputs"
        if missing_required
        else "blocked_quote_store_unreadable"
        if quote_store_error
        else "execution_alternative_replay_coverage_readback"
    )
    summary = _summary_from_rows(
        coverage_rows,
        readiness=readiness,
        missing_required=missing_required,
        quote_store_error=quote_store_error,
        live_policy_change=live_policy_change,
    )
    quote_demands = _quote_demands_from_rows(
        coverage_rows,
        entry_window_minutes=entry_window_minutes,
        exit_window_minutes=exit_window_minutes,
        source_labels=source_labels,
    )
    quote_demand_phase_counts = Counter(str(item.get("quote_phase")) for item in quote_demands)
    quote_demand_usage_counts = Counter(
        str(usage)
        for item in quote_demands
        for usage in _as_list(item.get("usage_labels"))
    )
    summary.update(
        {
            "quote_demand_manifest_status": "ready_for_import_or_query" if quote_demands else "no_missing_quote_demands",
            "missing_quote_demand_count": len(quote_demands),
            "missing_entry_quote_demand_count": int(quote_demand_phase_counts.get("entry", 0)),
            "missing_exit_quote_demand_count": int(quote_demand_phase_counts.get("exit", 0)),
            "quote_demand_usage_counts": dict(sorted(quote_demand_usage_counts.items())),
        }
    )
    missing_by_reason = Counter(
        blocker
        for row in coverage_rows
        for blocker in _as_list(row.get("blockers"))
        if str(blocker).startswith("missing_")
    )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_execution_alternative_replay_coverage_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {
            "execution_alternative_replay_readiness": readiness_meta,
            "options_history_db": db_meta,
            "source_labels": list(source_labels),
            "snapshot_kind": INTRADAY_SNAPSHOT_KIND,
            "entry_window_minutes": int(entry_window_minutes),
            "exit_minute_et": int(exit_minute_et),
            "exit_window_minutes": int(exit_window_minutes),
        },
        "coverage_rows": coverage_rows[:50],
        "quote_demands": quote_demands[:200],
        "missing_quote_reason_counts": dict(sorted(missing_by_reason.items())),
        "next_evidence_queue": [
            {
                "priority": 0,
                "action": "import_or_query_missing_execution_alternative_entry_quotes",
                "count": int(summary.get("missing_entry_quote_demand_count") or 0),
                "reason": "top_spread_or_replacement_entry_quote_coverage_incomplete",
                "operator_next_step": "Use `quote_demands` priority 0/entry rows to import or query trusted same-minute OPRA/NBBO entry quotes before counting replay P&L.",
            },
            {
                "priority": 1,
                "action": "import_or_query_missing_execution_alternative_exit_quotes",
                "count": int(summary.get("missing_exit_quote_demand_count") or 0),
                "reason": "top_spread_or_replacement_exit_quote_coverage_incomplete",
                "operator_next_step": "Use `quote_demands` exit rows to import or query trusted OPRA/NBBO exit-window quotes before changing contract selection.",
            },
        ],
        "evidence_boundary": {
            "readback_is": "read-only exact OPRA/NBBO bid/ask coverage and side-aware replay availability for logged execution alternatives",
            "readback_is_not": "scanner policy, contract-selection permission, broker action, DB mutation, stop/sizing change, or promotion proof",
            "pnl_rule": "P&L is emitted only when both entry and exit long/short bid/ask quotes are present from trusted intraday OPRA/NBBO rows.",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text.replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Execution Alternative Replay Coverage",
        "",
        "This report is generated from `scripts/build_regular_options_execution_alternative_replay_coverage.py`. It is a read-only exact OPRA/NBBO coverage and side-aware replay availability report for logged execution alternatives.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Candidate seeds: `{summary.get('candidate_seed_count')}`.",
        f"- Top-spread true P&L rows: `{summary.get('true_top_spread_replay_pnl_count')}` / `{summary.get('top_spread_candidate_count')}`.",
        f"- Contract-replacement true P&L rows: `{summary.get('true_contract_replacement_pnl_count')}` / `{summary.get('contract_replacement_candidate_count')}`.",
        f"- Top entry/exit coverage: `{summary.get('top_spread_entry_quote_coverage_status')}` / `{summary.get('top_spread_exit_quote_coverage_status')}`.",
        f"- Replacement entry/exit coverage: `{summary.get('contract_replacement_entry_quote_coverage_status')}` / `{summary.get('contract_replacement_exit_quote_coverage_status')}`.",
        f"- Quote-demand manifest: `{summary.get('quote_demand_manifest_status')}` with `{summary.get('missing_quote_demand_count')}` unique missing quote targets.",
        f"- Replay engines: `{summary.get('liquidity_first_replay_engine_status')}` / `{summary.get('contract_replacement_replay_engine_status')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Coverage Rows",
        "",
        "| Ticker | Lane | Entry ET Minute | Top Entry | Top Exit | Replacement Entry | Replacement Exit | True Top P&L | True Replacement P&L | Blockers |",
        "|---|---|---:|---|---|---|---|---:|---:|---|",
    ]
    for row in _as_list(report.get("coverage_rows"))[:25]:
        row = _as_dict(row)
        top = _as_dict(row.get("top_spread"))
        replacement = _as_dict(row.get("contract_replacement"))
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("entry_quote_minute_et")),
                    _cell(top.get("entry_pair_complete")),
                    _cell(top.get("exit_pair_complete")),
                    _cell(replacement.get("entry_pair_complete")),
                    _cell(replacement.get("exit_pair_complete")),
                    _cell(row.get("row_true_top_spread_replay_pnl")),
                    _cell(row.get("row_true_contract_replacement_pnl")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    true_rows = [
        row
        for row in _as_list(report.get("coverage_rows"))
        if _as_dict(row).get("row_true_top_spread_replay_pnl")
        or _as_dict(row).get("row_true_contract_replacement_pnl")
    ]
    lines.extend(
        [
            "",
            "## True Side-Aware Rows",
            "",
            "| Ticker | Label | Entry Debit | Exit Value | Gross P&L % |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in true_rows[:25]:
        row = _as_dict(row)
        for label in ("top_spread", "contract_replacement"):
            replay = _as_dict(row.get(label))
            if not replay.get("true_side_aware_pnl_available"):
                continue
            lines.append(
                f"| {_cell(row.get('ticker'))} | `{label}` | {_cell(replay.get('entry_side_aware_debit'))} | {_cell(replay.get('exit_side_aware_value'))} | {_cell(replay.get('gross_pnl_pct'))} |"
            )
    if not true_rows:
        lines.append("| none | none |  |  |  |")
    lines.extend(
        [
            "",
            "## Quote Demand Manifest",
            "",
            "| Priority | Phase | Contract | Date | Minute ET | Window | Usages | Source Rows | Missing Reasons |",
            "|---:|---|---|---|---:|---:|---|---:|---|",
        ]
    )
    for demand in _as_list(report.get("quote_demands"))[:50]:
        demand = _as_dict(demand)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(demand.get("priority")),
                    _cell(demand.get("quote_phase")),
                    _cell(demand.get("contract_symbol")),
                    _cell(demand.get("quote_date_et")),
                    _cell(demand.get("quote_minute_et")),
                    _cell(demand.get("window_minutes")),
                    _cell(", ".join(str(item) for item in _as_list(demand.get("usage_labels")))),
                    _cell(demand.get("source_row_count")),
                    _cell(", ".join(str(item) for item in _as_list(demand.get("missing_reasons")))),
                ]
            )
            + " |"
        )
    if not _as_list(report.get("quote_demands")):
        lines.append("|  | none |  |  |  |  |  |  |  |")
    boundary = _as_dict(report.get("evidence_boundary"))
    lines.extend(
        [
            "",
            "## Missing Quote Reasons",
            "",
            f"`{_json_inline(report.get('missing_quote_reason_counts') or {})}`",
            "",
            "## Boundary",
            "",
            f"- Readback is: `{boundary.get('readback_is')}`.",
            f"- Readback is not: `{boundary.get('readback_is_not')}`.",
            f"- P&L rule: `{boundary.get('pnl_rule')}`.",
            "",
            "This coverage report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change contract selection, change stops, change sizing, synthesize P&L from midpoint/daily/stale/display marks, lower proof bars, or promote replay rows to production proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only execution-alternative exact quote coverage and replay availability.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--entry-window-minutes", type=int, default=0)
    parser.add_argument("--exit-minute-et", type=int, default=DEFAULT_EXIT_MINUTE_ET)
    parser.add_argument("--exit-window-minutes", type=int, default=0)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    source_labels = [item.strip() for item in str(args.source_labels or "").split(",") if item.strip()]
    report = build_report(
        readiness_path=args.readiness,
        db_path=args.db_path,
        exit_minute_et=args.exit_minute_et,
        entry_window_minutes=args.entry_window_minutes,
        exit_window_minutes=args.exit_window_minutes,
        source_labels=source_labels,
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
