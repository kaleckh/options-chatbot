from __future__ import annotations

import argparse
import json
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
REPORT_ID = "regular_options_minute_exit_replay_readiness"

DEFAULT_ARTIFACT_PATHS: dict[str, Path] = {
    "fresh_evidence_loop": ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json",
    "current_policy_stop_grid": ROOT / "data" / "forward-tracking" / "current_policy_historical_stop_grid_latest.json",
    "open_risk": ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json",
}

DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_DB_PATH = Path(os.getenv("HISTORICAL_OPTIONS_DB_PATH", str(ROOT / "data" / "options-validation" / "options_history.db")))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-minute-exit-replay-readiness.md"

REQUIRED_ARTIFACT_KEYS = tuple(DEFAULT_ARTIFACT_PATHS)
EASTERN_TZ = ZoneInfo("America/New_York")
INTRADAY_SNAPSHOT_KIND = "intraday"
TRUSTED_DATA_TRUST = "trusted"
DEFAULT_SOURCE_LABELS = ("thetadata_opra_nbbo_1m",)
DEFAULT_EXIT_MINUTE_ET = 15 * 60 + 55

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_minute_exit_replay_readiness",
    "do_not_submit_broker_order_from_minute_exit_replay_readiness",
    "do_not_mutate_database_from_minute_exit_replay_readiness",
    "do_not_change_scanner_policy_from_minute_exit_replay_readiness",
    "do_not_change_stop_policy_from_minute_exit_replay_readiness",
    "do_not_change_sizing_from_minute_exit_replay_readiness",
    "do_not_synthesize_exit_pnl_from_daily_midpoint_stale_or_display_marks",
    "do_not_promote_readiness_rows_to_production_proof",
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
    return parsed


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
        "source_label": str(row["source_label"]),
        "data_trust": str(row["data_trust"]),
        "quote_evidence_class": "trusted_intraday_opra_nbbo",
    }


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


def _safe_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "error": None,
    }
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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    return payload, meta


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf8").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


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


def _selected_spread(row: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(row.get("selected_spread"))


def _contract_pair(row: dict[str, Any]) -> tuple[str, str]:
    selected = _selected_spread(row)
    long_symbol = _norm(
        _first_present(selected.get("long_contract_symbol"), row.get("long_contract_symbol"), row.get("contract_symbol"))
    ).upper()
    short_symbol = _norm(
        _first_present(selected.get("short_contract_symbol"), row.get("short_contract_symbol"))
    ).upper()
    if long_symbol and short_symbol:
        return long_symbol, short_symbol
    for leg in _as_list(selected.get("legs")):
        leg = _as_dict(leg)
        role = _norm(leg.get("role")).lower()
        symbol = _norm(leg.get("contract_symbol")).upper()
        if role == "long" and symbol:
            long_symbol = symbol
        if role == "short" and symbol:
            short_symbol = symbol
    return long_symbol, short_symbol


def _entry_price(row: dict[str, Any]) -> float | None:
    selected = _selected_spread(row)
    return _safe_float(
        _first_present(
            row.get("filled_price"),
            row.get("attempted_limit_price"),
            row.get("entry_execution_price"),
            selected.get("entry_execution_price"),
            selected.get("spread_entry_debit"),
            selected.get("net_debit"),
        )
    )


def _entry_time(row: dict[str, Any]) -> str:
    selected = _selected_spread(row)
    return _norm(
        _first_present(
            row.get("attempted_limit_quote_time_utc"),
            row.get("quote_time_utc"),
            row.get("quote_timestamp_utc"),
            selected.get("quote_time_utc"),
            row.get("filled_at"),
            row.get("logged_at"),
        )
    )


def _expiry(row: dict[str, Any]) -> str:
    selected = _selected_spread(row)
    return _norm(_first_present(selected.get("expiry"), row.get("expiry")))


def _is_exact_opra_entry(row: dict[str, Any]) -> bool:
    selected = _selected_spread(row)
    tokens = [
        row.get("pricing_evidence_class"),
        row.get("candidate_execution_label"),
        row.get("options_data_source"),
        row.get("selection_source"),
        selected.get("quote_source"),
        selected.get("options_data_source"),
        selected.get("entry_execution_basis"),
    ]
    for leg in _as_list(selected.get("legs")):
        leg = _as_dict(leg)
        tokens.extend([leg.get("quote_source"), leg.get("data_source"), leg.get("source_feed")])
    blob = " ".join(_norm(token).lower() for token in tokens)
    return (
        _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
        or ("opra" in blob and "exact" in blob)
        or "live_chain_exact_contract" in blob
    )


def _has_position_seed(row: dict[str, Any]) -> bool:
    return (
        row.get("auto_track_position_id") is not None
        or bool(row.get("filled"))
        or _norm(row.get("fill_outcome")) == "paper_fill_recorded"
    )


def _candidate_queue_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    long_symbol, short_symbol = _contract_pair(row)
    entry_time = _entry_time(row)
    entry_price = _entry_price(row)
    exact_entry = _is_exact_opra_entry(row)
    has_position_seed = _has_position_seed(row)
    entry_blockers: list[str] = []
    if not exact_entry:
        entry_blockers.append("entry_not_proof_live_exact_contract")
    if not long_symbol:
        entry_blockers.append("missing_long_contract_symbol")
    if not short_symbol:
        entry_blockers.append("missing_short_contract_symbol")
    if not entry_time:
        entry_blockers.append("missing_entry_quote_time")
    if entry_price is None or entry_price <= 0:
        entry_blockers.append("missing_entry_execution_price")

    if entry_blockers:
        readiness_status = "blocked_missing_exact_entry_seed"
        blockers = list(entry_blockers)
    elif has_position_seed:
        readiness_status = "position_seed_ready_engine_missing"
        blockers = [
            "minute_level_exit_replay_engine_missing",
            "minute_opra_nbbo_quote_coverage_missing",
        ]
    else:
        readiness_status = "entry_seed_only_fill_not_recorded"
        blockers = [
            "paper_fill_or_position_link_missing",
            "minute_level_exit_replay_engine_missing",
            "minute_opra_nbbo_quote_coverage_missing",
        ]

    return {
        "source": "fill_attempts",
        "row_index": index,
        "readiness_status": readiness_status,
        "ticker": row.get("ticker"),
        "lane": row.get("playbook_id") or row.get("cohort_id"),
        "scan_date": row.get("scan_date"),
        "logged_at": row.get("logged_at"),
        "entry_time_utc": entry_time,
        "expiry": _expiry(row),
        "long_contract_symbol": long_symbol or None,
        "short_contract_symbol": short_symbol or None,
        "entry_execution_price": entry_price,
        "pricing_evidence_class": row.get("pricing_evidence_class"),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "auto_track_position_id": row.get("auto_track_position_id"),
        "has_fill_discipline_snapshot": isinstance(row.get("fill_discipline_snapshot"), dict),
        "top_alternative_count": len(_as_list(row.get("top_alternatives")) or _as_list(row.get("top_spread_alternatives"))),
        "blockers": blockers,
        "required_next_evidence": [
            "minute_level_exact_opra_nbbo_quote_coverage",
            "minute_exit_replay_engine",
        ]
        + ([] if has_position_seed else ["paper_fill_or_position_link_for_realized_exit"]),
    }


def _daily_stop_grid_summary(stop_grid: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(stop_grid.get("coverage"))
    rows = [row for row in _as_list(stop_grid.get("rows")) if isinstance(row, dict)]
    exact_contract_rows = [
        row
        for row in rows
        if _norm(row.get("contract_symbol")) and _norm(row.get("short_contract_symbol")) and _safe_float(row.get("entry_execution_price")) is not None
    ]
    return {
        "available": bool(stop_grid),
        "generated_at_utc": stop_grid.get("generated_at_utc"),
        "not_claimed": _as_dict(stop_grid.get("evidence_boundary")).get("not_claimed"),
        "replayed_count": coverage.get("replayed_count"),
        "unresolved_count": coverage.get("unresolved_count"),
        "exact_contract_daily_rows": len(exact_contract_rows),
        "source_labels": _as_dict(stop_grid.get("inputs")).get("source_labels"),
    }


def _evaluate_minute_exit_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    exit_minute_et: int,
    entry_window_minutes: int,
    exit_window_minutes: int,
    source_labels: Sequence[str],
) -> dict[str, Any]:
    entry_date_et, entry_minute_et = _entry_date_minute(row.get("entry_time_utc"), row.get("scan_date"))
    long_symbol = _norm(row.get("long_contract_symbol")).upper()
    short_symbol = _norm(row.get("short_contract_symbol")).upper()
    result: dict[str, Any] = {
        "row_index": row.get("row_index"),
        "ticker": row.get("ticker"),
        "lane": row.get("lane"),
        "scan_date": row.get("scan_date"),
        "readiness_status": row.get("readiness_status"),
        "auto_track_position_id": row.get("auto_track_position_id"),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "long_contract_symbol": long_symbol or None,
        "short_contract_symbol": short_symbol or None,
        "entry_quote_date_et": entry_date_et,
        "entry_quote_minute_et": entry_minute_et,
        "exit_quote_date_et": entry_date_et,
        "exit_quote_minute_et": int(exit_minute_et),
        "contract_quantity": 1,
        "fees_slippage_assumption": "gross replay: no extra fees or slippage beyond side-aware bid/ask execution prices",
        "entry_pair_complete": False,
        "exit_pair_complete": False,
        "true_side_aware_pnl_available": False,
        "decision": "reject_missing_exact_minute_pnl",
        "decision_reason": "exact trusted bid/ask entry and exit quote pairs are required before this row can affect minute-exit decisions",
        "blockers": [],
    }
    blockers: list[str] = []
    if not long_symbol:
        blockers.append("missing_long_contract_symbol")
    if not short_symbol:
        blockers.append("missing_short_contract_symbol")
    if not entry_date_et or entry_minute_et is None:
        blockers.append("missing_entry_quote_time")
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
        quote_date_et=entry_date_et,
        center_minute_et=exit_minute_et,
        window_minutes=exit_window_minutes,
        source_labels=source_labels,
    )
    exit_short = _quote_lookup(
        conn,
        contract_symbol=short_symbol,
        quote_date_et=entry_date_et,
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
        exit_side_value = _exit_value(exit_long, exit_short)  # type: ignore[arg-type]
        if entry_debit is not None and exit_side_value is not None:
            pnl_per_spread = round(exit_side_value - entry_debit, 4)
            result.update(
                {
                    "entry_side_aware_debit": entry_debit,
                    "logged_entry_execution_price": row.get("entry_execution_price"),
                    "exit_side_aware_value": exit_side_value,
                    "gross_pnl_per_spread": pnl_per_spread,
                    "gross_pnl_pct": round((pnl_per_spread / entry_debit) * 100.0, 2),
                    "true_side_aware_pnl_available": True,
                }
            )
            if row.get("auto_track_position_id") is not None:
                result["decision"] = "hold_for_current_open_risk_review"
                result["decision_reason"] = (
                    "historical minute replay is exact and executable, but open-risk resolution still requires fresh current exit evidence"
                )
            else:
                result["decision"] = "reject_production_use_without_fill_or_position_link"
                result["decision_reason"] = (
                    "exact minute replay exists, but the row has no fill or tracked-position link and remains diagnostic-only"
                )
        else:
            blockers.append("non_positive_entry_side_aware_debit")
    result["blockers"] = blockers
    return result


def _minute_exit_replay_rows(
    queue_rows: list[dict[str, Any]],
    *,
    db_path: Path,
    exit_minute_et: int,
    entry_window_minutes: int,
    exit_window_minutes: int,
    source_labels: Sequence[str],
) -> tuple[list[dict[str, Any]], str | None]:
    eligible = [
        row
        for row in queue_rows
        if _norm(row.get("readiness_status")) in {"position_seed_ready_engine_missing", "entry_seed_only_fill_not_recorded"}
    ]
    if not db_path.exists():
        return [], "options_history_db_missing"
    try:
        with closing(_sqlite_readonly_connect(db_path)) as conn:
            rows = [
                _evaluate_minute_exit_row(
                    conn,
                    row,
                    exit_minute_et=exit_minute_et,
                    entry_window_minutes=entry_window_minutes,
                    exit_window_minutes=exit_window_minutes,
                    source_labels=source_labels,
                )
                for row in eligible
            ]
        return rows, None
    except sqlite3.Error as exc:
        return [], f"{type(exc).__name__}: {exc}"


def _coverage_status(complete_count: int, candidate_count: int) -> str:
    if candidate_count <= 0:
        return "not_applicable"
    if complete_count == candidate_count:
        return "full"
    if complete_count > 0:
        return "partial"
    return "missing"


def _status_for_summary(
    missing_required: list[str],
    live_policy_change: bool,
    position_seed_count: int,
    entry_seed_count: int,
    true_minute_exit_pnl_count: int,
) -> str:
    if live_policy_change:
        return "invalid_live_policy_change"
    if missing_required:
        return "blocked_missing_inputs"
    if entry_seed_count > 0 and true_minute_exit_pnl_count == entry_seed_count:
        return "minute_exit_replay_coverage_ready"
    if true_minute_exit_pnl_count > 0:
        return "minute_exit_replay_partial_true_pnl_blocked"
    if position_seed_count > 0:
        return "blocked_ready_seed_missing_minute_engine"
    if entry_seed_count > 0:
        return "blocked_entry_seeds_missing_fill_or_minute_engine"
    return "blocked_no_exact_entry_seeds"


def build_report(
    *,
    artifact_paths: dict[str, Path] | None = None,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    db_path: Path = DEFAULT_DB_PATH,
    exit_minute_et: int = DEFAULT_EXIT_MINUTE_ET,
    entry_window_minutes: int = 0,
    exit_window_minutes: int = 0,
    source_labels: Sequence[str] = DEFAULT_SOURCE_LABELS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = dict(DEFAULT_ARTIFACT_PATHS)
    if artifact_paths:
        paths.update(artifact_paths)

    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], inputs[key] = _load_json(path)
    fill_rows, fill_meta = _load_jsonl(fill_attempts_path)
    inputs["fill_attempts"] = fill_meta

    missing_required = [key for key in REQUIRED_ARTIFACT_KEYS if inputs.get(key, {}).get("status") != "loaded"]
    if fill_meta.get("status") != "loaded":
        missing_required.append("fill_attempts")
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())

    candidate_rows = [row for row in fill_rows if _norm(row.get("event_type")) == "candidate_shown"]
    queue_rows = [_candidate_queue_row(row, index) for index, row in enumerate(candidate_rows)]
    queue_rows.sort(
        key=lambda item: (
            0 if item.get("readiness_status") == "position_seed_ready_engine_missing" else 1,
            str(item.get("entry_time_utc") or ""),
        ),
        reverse=False,
    )

    status_counts = Counter(str(row.get("readiness_status")) for row in queue_rows)
    entry_seed_count = int(status_counts.get("position_seed_ready_engine_missing", 0)) + int(
        status_counts.get("entry_seed_only_fill_not_recorded", 0)
    )
    position_seed_count = int(status_counts.get("position_seed_ready_engine_missing", 0))
    minute_exit_rows, quote_store_error = _minute_exit_replay_rows(
        queue_rows,
        db_path=db_path,
        exit_minute_et=exit_minute_et,
        entry_window_minutes=entry_window_minutes,
        exit_window_minutes=exit_window_minutes,
        source_labels=source_labels,
    )
    true_minute_exit_pnl_count = sum(1 for row in minute_exit_rows if bool(row.get("true_side_aware_pnl_available")))
    position_linked_true_minute_exit_pnl_count = sum(
        1 for row in minute_exit_rows if bool(row.get("true_side_aware_pnl_available")) and row.get("auto_track_position_id") is not None
    )
    entry_pair_complete_count = sum(1 for row in minute_exit_rows if bool(row.get("entry_pair_complete")))
    exit_pair_complete_count = sum(1 for row in minute_exit_rows if bool(row.get("exit_pair_complete")))
    blockers = []
    if true_minute_exit_pnl_count < entry_seed_count:
        blockers.append("daily_stop_grid_is_not_minute_level_proof")
    if true_minute_exit_pnl_count == 0:
        blockers.extend(["minute_level_exit_replay_engine_missing", "minute_opra_nbbo_quote_coverage_missing"])
    elif true_minute_exit_pnl_count < entry_seed_count:
        blockers.append("true_minute_exit_pnl_rows_incomplete")
    if quote_store_error:
        blockers.append("quote_store_read_error")
    if position_seed_count == 0:
        blockers.append("no_position_linked_exact_entry_seed")
    if entry_seed_count == 0:
        blockers.append("no_exact_entry_seed_rows")

    fresh_summary = _as_dict(reports["fresh_evidence_loop"].get("summary"))
    open_governor = _as_dict(reports["open_risk"].get("open_risk_governor"))
    daily_stop = _daily_stop_grid_summary(reports["current_policy_stop_grid"])
    overall_status = _status_for_summary(
        missing_required,
        live_policy_change,
        position_seed_count,
        entry_seed_count,
        true_minute_exit_pnl_count,
    )
    report_status = (
        "invalid_live_policy_change"
        if live_policy_change
        else "blocked_missing_inputs"
        if missing_required
        else "minute_exit_replay_readiness_readback"
    )

    return {
        "report_id": REPORT_ID,
        "status": report_status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_minute_exit_replay_readiness_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": {
            "overall_status": overall_status,
            "candidate_shown_count": len(candidate_rows),
            "exact_opra_entry_seed_count": sum(1 for row in candidate_rows if _is_exact_opra_entry(row)),
            "proof_live_pricing_class_count": sum(
                1 for row in candidate_rows if _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
            ),
            "entry_seed_ready_count": entry_seed_count,
            "position_seed_ready_count": position_seed_count,
            "blocked_missing_exact_entry_seed_count": int(status_counts.get("blocked_missing_exact_entry_seed", 0)),
            "paper_fill_recorded_count": sum(1 for row in candidate_rows if _norm(row.get("fill_outcome")) == "paper_fill_recorded"),
            "auto_track_position_seed_count": sum(1 for row in candidate_rows if row.get("auto_track_position_id") is not None),
            "fresh_loop_candidate_count": fresh_summary.get("candidate_count"),
            "fresh_loop_exact_exit_bridge_count": fresh_summary.get("exact_exit_bridge_count"),
            "open_risk_status": open_governor.get("status"),
            "open_risk_live_entry_allowed": open_governor.get("live_entry_allowed"),
            "live_exact_negative_ids": open_governor.get("live_exact_negative_ids"),
            "daily_stop_grid_replayed_count": daily_stop.get("replayed_count"),
            "daily_stop_grid_unresolved_count": daily_stop.get("unresolved_count"),
            "daily_stop_grid_not_minute_proof": True,
            "true_minute_exit_pnl_count": true_minute_exit_pnl_count,
            "position_linked_true_minute_exit_pnl_count": position_linked_true_minute_exit_pnl_count,
            "minute_entry_pair_complete_count": entry_pair_complete_count,
            "minute_exit_pair_complete_count": exit_pair_complete_count,
            "minute_quote_coverage_status": _coverage_status(true_minute_exit_pnl_count, entry_seed_count),
            "minute_entry_quote_coverage_status": _coverage_status(entry_pair_complete_count, entry_seed_count),
            "minute_exit_quote_coverage_status": _coverage_status(exit_pair_complete_count, entry_seed_count),
            "minute_exit_replay_engine_status": "read_only_side_aware_engine_partial"
            if true_minute_exit_pnl_count
            else "missing",
            "minute_exit_decision_counts": dict(
                sorted(Counter(str(row.get("decision")) for row in minute_exit_rows if row.get("decision")).items())
            ),
            "quote_store_error": quote_store_error,
            "missing_required_inputs": missing_required,
            "blocker_count": len(sorted(set(blockers))),
            "blockers": sorted(set(blockers)),
            "live_policy_change": live_policy_change,
        },
        "evidence_boundary": {
            "readback_is": "readiness queue for building a future exact OPRA/NBBO minute-level exit replay",
            "readback_is_not": "simulated P&L, promotion proof, stop-policy approval, broker action, or a live-risk instruction",
            "daily_stop_grid_not_claimed": daily_stop.get("not_claimed"),
            "pnl_rule": "P&L is emitted only when entry and fixed-minute exit long/short bid/ask quotes are present from trusted intraday OPRA/NBBO rows; long exit uses bid and short cover uses ask.",
            "fees_slippage_assumption": "gross replay only: no additional fees or slippage beyond side-aware bid/ask prices",
            "trusted_future_requirement": "minute-by-minute exact-contract OPRA/NBBO bid/ask exit replay with no midpoint, daily/EOD, stale, display, or manual marks",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": {
            **inputs,
            "options_history_db": {
                "path": str(db_path),
                "exists": db_path.exists(),
                "status": "unreadable" if quote_store_error and db_path.exists() else "loaded" if db_path.exists() else "missing",
                "error": quote_store_error,
            },
            "source_labels": list(source_labels),
            "snapshot_kind": INTRADAY_SNAPSHOT_KIND,
            "entry_window_minutes": int(entry_window_minutes),
            "exit_minute_et": int(exit_minute_et),
            "exit_window_minutes": int(exit_window_minutes),
        },
        "daily_stop_grid": daily_stop,
        "readiness_status_counts": dict(sorted(status_counts.items())),
        "candidate_queue": queue_rows[:50],
        "minute_exit_replay_rows": minute_exit_rows[:50],
        "next_evidence_queue": [
            *(
                []
                if true_minute_exit_pnl_count == entry_seed_count and entry_seed_count
                else [
                    {
                        "priority": 0,
                        "action": "build_or_repair_minute_exit_replay_engine",
                        "count": max(entry_seed_count - true_minute_exit_pnl_count, 1),
                        "reason": "true_minute_exit_pnl_rows_missing_or_incomplete",
                        "operator_next_step": "Import trusted minute quotes and rerun the exact OPRA/NBBO minute exit engine before changing stop or exit policy.",
                    }
                ]
            ),
            {
                "priority": 2,
                "action": "collect_position_linked_exact_entry_seed",
                "count": max(entry_seed_count - position_seed_count, 0),
                "reason": "entry_seed_only_rows_need_fill_or_position_link_for_realized_exit",
                "operator_next_step": "Keep entry-only seed rows as paper diagnostics until a paper fill or tracked-position link exists.",
            },
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Minute Exit Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_minute_exit_replay_readiness.py`. It is a read-only readiness and side-aware fixed-minute exit replay for exact OPRA/NBBO rows; it does not change stops, submit orders, or mutate trading rows.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Candidate-shown rows: `{summary.get('candidate_shown_count')}`.",
        f"- Entry seed ready / position seed ready: `{summary.get('entry_seed_ready_count')}` / `{summary.get('position_seed_ready_count')}`.",
        f"- True minute exit P&L rows: `{summary.get('true_minute_exit_pnl_count')}`.",
        f"- Position-linked true minute exit P&L rows: `{summary.get('position_linked_true_minute_exit_pnl_count')}`.",
        f"- Minute quote coverage / engine: `{summary.get('minute_quote_coverage_status')}` / `{summary.get('minute_exit_replay_engine_status')}`.",
        f"- Minute decisions: `{_json_inline(summary.get('minute_exit_decision_counts') or {})}`.",
        f"- Daily stop-grid replayed rows: `{summary.get('daily_stop_grid_replayed_count')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Candidate Queue",
        "",
        "| Status | Ticker | Lane | Entry Time | Long | Short | Position | Blockers |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for row in _as_list(report.get("candidate_queue"))[:25]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('readiness_status'))}`",
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("entry_time_utc")),
                    _cell(row.get("long_contract_symbol")),
                    _cell(row.get("short_contract_symbol")),
                    _cell(row.get("auto_track_position_id")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    true_rows = [
        _as_dict(row)
        for row in _as_list(report.get("minute_exit_replay_rows"))
        if _as_dict(row).get("true_side_aware_pnl_available")
    ]
    lines.extend(
        [
            "",
            "## True Minute Exit Replay Rows",
            "",
            "| Ticker | Lane | Position | Long Quote | Short Quote | Entry Debit | Exit Value | Gross P&L % | Decision |",
            "|---|---|---:|---|---|---:|---:|---:|---|",
        ]
    )
    for row in true_rows[:25]:
        entry_long = _as_dict(row.get("entry_long_quote"))
        entry_short = _as_dict(row.get("entry_short_quote"))
        exit_long = _as_dict(row.get("exit_long_quote"))
        exit_short = _as_dict(row.get("exit_short_quote"))
        long_quote = (
            f"entry {entry_long.get('as_of_utc')} bid/ask {entry_long.get('bid')}/{entry_long.get('ask')}; "
            f"exit {exit_long.get('as_of_utc')} bid/ask {exit_long.get('bid')}/{exit_long.get('ask')}"
        )
        short_quote = (
            f"entry {entry_short.get('as_of_utc')} bid/ask {entry_short.get('bid')}/{entry_short.get('ask')}; "
            f"exit {exit_short.get('as_of_utc')} bid/ask {exit_short.get('bid')}/{exit_short.get('ask')}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("auto_track_position_id")),
                    _cell(long_quote),
                    _cell(short_quote),
                    _cell(row.get("entry_side_aware_debit")),
                    _cell(row.get("exit_side_aware_value")),
                    _cell(row.get("gross_pnl_pct")),
                    f"`{_cell(row.get('decision'))}`",
                ]
            )
            + " |"
        )
    if not true_rows:
        lines.append("| none | none |  |  |  |  |  |  |  |")
    lines.extend(
        [
            "",
            "## Next Evidence Queue",
            "",
            "| Priority | Action | Count | Reason |",
            "|---:|---|---:|---|",
        ]
    )
    for item in _as_list(report.get("next_evidence_queue")):
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('priority'))} | `{_cell(item.get('action'))}` | {_cell(item.get('count'))} | {_cell(item.get('reason'))} |"
        )
    boundary = _as_dict(report.get("evidence_boundary"))
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Readback is: `{boundary.get('readback_is')}`.",
            f"- Readback is not: `{boundary.get('readback_is_not')}`.",
            f"- Daily stop-grid boundary: `{boundary.get('daily_stop_grid_not_claimed')}`.",
            f"- P&L rule: `{boundary.get('pnl_rule')}`.",
            f"- Fees/slippage assumption: `{boundary.get('fees_slippage_assumption')}`.",
            "",
            "This report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stop policy, change sizing, synthesize exit P&L from daily/midpoint/stale/display marks, lower proof bars, or promote replay rows to production proof.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options minute exit replay readiness queue.")
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(fill_attempts_path=args.fill_attempts)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
