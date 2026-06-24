from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_point_in_time_flow_extreme_input"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "source_rows.jsonl"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-flow-extreme-ratio-backspread-playbook" / "latest.json"
)
DEFAULT_OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-flow-extreme-input.md"

DEFAULT_START_DATE = "2024-06-01"
DEFAULT_END_DATE = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
DEFAULT_UNDERLYINGS = "SPY,QQQ"
MIN_COVERED_MONTHS = 20
MIN_DATE_COVERAGE_PCT = 90.0

ALLOWED_FLOW_BASES = {
    "volume_open_interest",
    "bid_ask_size_imbalance",
    "quote_depth_pressure",
}
REQUIRED_ROW_FIELDS = (
    "input_date_et",
    "underlying",
    "flow_input_basis",
    "call_pressure_score",
    "put_pressure_score",
    "put_call_pressure_ratio",
    "extreme_state",
    "threshold_policy_id",
    "source_name",
    "source_ref",
    "source_timestamp_utc",
    "known_at_utc",
    "point_in_time_valid",
    "source_provenance_status",
)
BASIS_NUMERIC_FIELDS = {
    "volume_open_interest": (
        "call_pressure_score",
        "put_pressure_score",
        "put_call_pressure_ratio",
    ),
    "bid_ask_size_imbalance": (
        "call_pressure_score",
        "put_pressure_score",
        "put_call_pressure_ratio",
        "quote_depth_imbalance_score",
    ),
    "quote_depth_pressure": (
        "call_pressure_score",
        "put_pressure_score",
        "put_call_pressure_ratio",
        "quote_depth_imbalance_score",
    ),
}
LEAKAGE_KEYS = {
    "future_return",
    "future_returns",
    "future_realized_vol",
    "future_iv",
    "realized_pnl",
    "realized_vol",
    "net_pnl",
    "net_pnl_usd",
    "option_pnl",
    "option_return",
    "trade_outcome",
    "winner",
    "label",
    "post_entry_return",
}
READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "no_write": True,
    "no_write_dry_run_supported": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "promotion_ready": False,
}
FORBIDDEN_ACTIONS = (
    "broker_orders",
    "broker_order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_changes",
    "strategy_logic_changes",
    "stop_changes",
    "sizing_changes",
    "proof_bar_changes",
    "quote_import",
    "external_market_data_fetch",
    "options_history_db_mutation",
    "canonical_evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_realized_pnl_or_selected_winners_to_define_thresholds",
    "relabeling_plain_bid_ask_prices_as_flow",
)

EASTERN = ZoneInfo("America/New_York")


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
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _months_between(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _load_json(path: Path, *, required: bool) -> tuple[Any, dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if isinstance(payload, dict):
        meta["generated_at_utc"] = payload.get("generated_at_utc")
        meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
        meta["status_value"] = payload.get("status")
    meta["status"] = "loaded"
    return payload, meta


def _load_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    meta.setdefault("non_object_lines", []).append(line_number)
        else:
            payload = json.loads(path.read_text(encoding="utf8"))
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                for key in ("source_rows", "flow_source_rows", "input_rows", "rows"):
                    if isinstance(payload.get(key), list):
                        rows = [row for row in payload[key] if isinstance(row, dict)]
                        break
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return [], meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _feature_store_dates(feature_store: Any, *, start: date, end: date) -> list[str]:
    dates: list[str] = []
    for value in _as_list(_as_dict(feature_store).get("shared_quote_dates")):
        parsed = _parse_date(value)
        if parsed and start <= parsed <= end:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _feature_store_symbols(feature_store: Any) -> set[str]:
    feature = _as_dict(feature_store)
    symbols = {str(value).upper() for value in _as_list(_as_dict(feature.get("inputs")).get("symbols")) if value}
    for row in _as_list(feature.get("symbol_surface_rows")):
        row = _as_dict(row)
        if row.get("symbol"):
            symbols.add(str(row["symbol"]).upper())
    return symbols


def _sqlite_inventory(path: Path) -> dict[str, Any]:
    inventory = {"path": _rel(path), "exists": path.exists(), "status": "missing", "tables": {}, "flow_columns": {}, "error": None}
    if not path.exists():
        return inventory
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()]
            inventory["status"] = "loaded"
            for table in tables:
                columns = [row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()]
                inventory["tables"][table] = columns
            quote_columns = set(_as_list(_as_dict(inventory["tables"]).get("option_quote_snapshots")))
            inventory["flow_columns"] = {
                "volume": "volume" in quote_columns,
                "open_interest": "open_interest" in quote_columns,
                "bid_size": "bid_size" in quote_columns,
                "ask_size": "ask_size" in quote_columns,
                "quote_depth": "quote_depth" in quote_columns,
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        inventory["status"] = "unreadable"
        inventory["error"] = type(exc).__name__
    return inventory


def _find_leakage_keys(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if str(key).lower() in LEAKAGE_KEYS:
                    hits.append(path)
                walk(nested, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(row)
    return hits


def _known_before_input_date(row: dict[str, Any], known_at: datetime) -> bool:
    source_frequency = str(row.get("source_frequency") or "prior_day_aggregate").lower()
    candidate_entry = _parse_dt(row.get("candidate_entry_timestamp_utc"))
    if candidate_entry:
        return known_at <= candidate_entry
    if source_frequency == "intraday":
        return True
    input_date = _parse_date(row.get("input_date_et"))
    return bool(input_date and known_at.astimezone(EASTERN).date() < input_date)


def _validate_row(
    row: dict[str, Any],
    index: int,
    *,
    start: date,
    end: date,
    as_of_date: date,
    underlyings: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reasons: list[str] = []
    missing = [field for field in REQUIRED_ROW_FIELDS if row.get(field) in (None, "")]
    if missing:
        reasons.append("missing_required_fields")
    input_date = _parse_date(row.get("input_date_et"))
    underlying = str(row.get("underlying") or "").upper()
    flow_input_basis = str(row.get("flow_input_basis") or "")
    source_ts = _parse_dt(row.get("source_timestamp_utc"))
    known_at = _parse_dt(row.get("known_at_utc"))
    leakage = _find_leakage_keys(row)
    if underlying not in underlyings:
        reasons.append("underlying_outside_requested_universe")
    if flow_input_basis not in ALLOWED_FLOW_BASES:
        reasons.append("unsupported_proxy_basis")
    if input_date is None or not (start <= input_date <= end):
        reasons.append("input_date_outside_requested_window")
    elif input_date > as_of_date:
        reasons.append("input_date_after_as_of_date")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_not_true")
    if row.get("source_provenance_status") != "trusted_local_or_contract_declared":
        reasons.append("source_provenance_status_not_trusted_local_or_contract_declared")
    if source_ts is None or known_at is None:
        reasons.append("missing_or_invalid_source_or_known_at_timestamp")
    elif known_at < source_ts:
        reasons.append("known_at_before_source_timestamp")
    elif not _known_before_input_date(row, known_at):
        reasons.append("known_at_after_candidate_join_cutoff")
    numeric_fields = BASIS_NUMERIC_FIELDS.get(
        flow_input_basis,
        (
            "call_pressure_score",
            "put_pressure_score",
            "put_call_pressure_ratio",
            "quote_depth_imbalance_score",
        ),
    )
    invalid_numeric = [field for field in numeric_fields if _safe_float(row.get(field)) is None]
    if invalid_numeric:
        reasons.append("missing_or_invalid_flow_numeric_fields")
    if leakage:
        reasons.append("leakage_fields_present")
    if reasons:
        return None, {
            "index": index,
            "input_date_et": row.get("input_date_et"),
            "underlying": row.get("underlying"),
            "reasons": reasons,
            "missing_fields": missing,
            "invalid_numeric_fields": invalid_numeric,
            "leakage_keys": leakage,
        }
    assert input_date is not None
    return (
        {
            "input_date_et": input_date.isoformat(),
            "known_at_utc": str(row["known_at_utc"]),
            "underlying": underlying,
            "flow_input_basis": flow_input_basis,
            "call_pressure_score": _safe_float(row.get("call_pressure_score")),
            "put_pressure_score": _safe_float(row.get("put_pressure_score")),
            "put_call_pressure_ratio": _safe_float(row.get("put_call_pressure_ratio")),
            "quote_depth_imbalance_score": _safe_float(row.get("quote_depth_imbalance_score")),
            "extreme_state": str(row.get("extreme_state")),
            "threshold_policy_id": str(row.get("threshold_policy_id")),
            "missing_field_count": int(row.get("missing_field_count") or 0),
            "stale_row_count": int(row.get("stale_row_count") or 0),
            "source_name": str(row["source_name"]),
            "source_ref": str(row["source_ref"]),
            "source_timestamp_utc": str(row["source_timestamp_utc"]),
            "point_in_time_valid": True,
            "source_provenance_status": "trusted_local_or_contract_declared",
            "proof_eligible": False,
            "blockers": [],
        },
        None,
    )


def _coverage(rows: list[dict[str, Any]], requested_dates: list[str], requested_months: list[str], underlyings: set[str]) -> dict[str, Any]:
    by_date: dict[str, set[str]] = {}
    for row in rows:
        by_date.setdefault(str(row["input_date_et"]), set()).add(str(row["underlying"]))
    clean_dates = sorted(day for day, symbols in by_date.items() if underlyings <= symbols)
    covered_months = sorted({item[:7] for item in clean_dates})
    requested_date_set = set(requested_dates)
    covered_dates = sorted(set(clean_dates) & requested_date_set) if requested_date_set else clean_dates
    date_coverage_pct = 100.0 if not requested_dates else round(len(covered_dates) / len(requested_dates) * 100.0, 4)
    return {
        "requested_months": requested_months,
        "requested_month_count": len(requested_months),
        "covered_months": covered_months,
        "covered_month_count": len(covered_months),
        "missing_months": sorted(set(requested_months) - set(covered_months)),
        "requested_date_count": len(requested_dates),
        "covered_date_count": len(covered_dates),
        "date_coverage_pct": date_coverage_pct,
        "minimum_covered_months": min(MIN_COVERED_MONTHS, len(requested_months)),
        "minimum_date_coverage_pct": MIN_DATE_COVERAGE_PCT,
        "required_underlyings": sorted(underlyings),
    }


def _source_inventory(
    *,
    source_meta: dict[str, Any],
    feature_store: Any,
    feature_meta: dict[str, Any],
    playbook_meta: dict[str, Any],
    sqlite_inventory: dict[str, Any],
    requested_dates: list[str],
    underlyings: set[str],
) -> dict[str, Any]:
    available_symbols = _feature_store_symbols(feature_store)
    missing_symbols = sorted(underlyings - available_symbols)
    flow_columns = _as_dict(sqlite_inventory.get("flow_columns"))
    schema_flow_basis = {
        "volume_open_interest": bool(flow_columns.get("volume") and flow_columns.get("open_interest")),
        "bid_ask_size_imbalance": bool(flow_columns.get("bid_size") and flow_columns.get("ask_size")),
        "quote_depth_pressure": bool(flow_columns.get("quote_depth")),
    }
    if source_meta.get("status") == "loaded" and int(source_meta.get("row_count") or 0) > 0:
        status = "source_rows_loaded"
    else:
        status = "missing_flow_source_rows"
    return {
        "status": status,
        "source_rows": source_meta,
        "feature_store": {
            **feature_meta,
            "requested_date_count": len(requested_dates),
            "available_symbols": sorted(available_symbols & underlyings),
            "missing_symbols": missing_symbols,
            "inventory_status": "feature_store_universe_mismatch" if missing_symbols else "feature_store_loaded_for_underlyings",
        },
        "preregistered_playbook": playbook_meta,
        "options_history_db": sqlite_inventory,
        "schema_declared_flow_basis": schema_flow_basis,
        "plain_bid_ask_only_is_not_flow": True,
    }


def _status(blockers: list[str]) -> str:
    return "blocked_point_in_time_flow_extreme_input" if blockers else "point_in_time_flow_extreme_input_available"


def build_report(
    *,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    underlyings: str = DEFAULT_UNDERLYINGS,
    no_write: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or start > end:
        raise ValueError("invalid start/end/as-of date")
    requested_underlyings = {item.strip().upper() for item in underlyings.split(",") if item.strip()}
    if not requested_underlyings:
        raise ValueError("underlyings must not be empty")
    if not no_write:
        raise ValueError("--no-write is required for this materializer")

    source_rows, source_meta = _load_source_rows(source_rows_path)
    feature_store, feature_meta = _load_json(feature_store_path, required=True)
    _playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    sqlite_inventory = _sqlite_inventory(options_history_db_path)
    requested_dates = _feature_store_dates(feature_store, start=start, end=end)
    requested_months = _months_between(start, end)
    inventory = _source_inventory(
        source_meta=source_meta,
        feature_store=feature_store,
        feature_meta=feature_meta,
        playbook_meta=playbook_meta,
        sqlite_inventory=sqlite_inventory,
        requested_dates=requested_dates,
        underlyings=requested_underlyings,
    )

    input_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        clean, reject = _validate_row(row, index, start=start, end=end, as_of_date=as_of, underlyings=requested_underlyings)
        if clean:
            input_rows.append(clean)
        if reject:
            rejected_rows.append(reject)
    coverage = _coverage(input_rows, requested_dates, requested_months, requested_underlyings)
    bases = sorted({str(row.get("flow_input_basis")) for row in input_rows})

    blockers: list[str] = []
    if source_meta.get("status") == "missing" or source_meta.get("row_count", 0) == 0:
        blockers.append("missing_point_in_time_flow_extreme_source")
    if feature_meta.get("status") != "loaded":
        blockers.append("missing_trusted_feature_store")
    if playbook_meta.get("status") != "loaded":
        blockers.append("missing_preregistered_flow_extreme_playbook")
    if sqlite_inventory.get("status") != "loaded":
        blockers.append("missing_local_options_history_inventory")
    if _as_dict(inventory.get("feature_store")).get("missing_symbols"):
        blockers.append("source_universe_mismatch")
    if not input_rows:
        blockers.append("missing_required_flow_fields")
    if rejected_rows:
        blockers.append("point_in_time_flow_extreme_row_validation_failed")
    if any(basis not in ALLOWED_FLOW_BASES for basis in bases):
        blockers.append("unsupported_proxy_basis")
    if not requested_dates:
        blockers.append("missing_requested_feature_store_dates")
    if coverage["covered_month_count"] < coverage["minimum_covered_months"]:
        blockers.append("insufficient_month_coverage")
    if coverage["date_coverage_pct"] < MIN_DATE_COVERAGE_PCT:
        blockers.append("insufficient_date_coverage")
    blockers = list(dict.fromkeys(blockers))

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(blockers),
        **READ_ONLY_FLAGS,
        "scope": "read_only_point_in_time_flow_extreme_input_materializer",
        "research_window": {"start_date": start.isoformat(), "end_date": end.isoformat(), "as_of_date": as_of.isoformat()},
        "requested_underlyings": sorted(requested_underlyings),
        "allowed_flow_input_bases": sorted(ALLOWED_FLOW_BASES),
        "source_inventory": inventory,
        "threshold_policy": {
            "policy_id": "point_in_time_flow_extreme_static_proxy_policy_v1",
            "outcome_tuned": False,
            "realized_pnl_used": False,
            "selected_winners_used": False,
            "future_outcomes_used": False,
            "description": "Rows must carry predeclared flow/extreme scores and known-at timestamps. Plain bid/ask price availability is not a flow input.",
        },
        "coverage": coverage,
        "input_rows": input_rows,
        "accepted_source_row_count": len(input_rows),
        "rejected_source_rows": rejected_rows,
        "blockers": blockers,
        "proxy_basis": bases,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] == "point_in_time_flow_extreme_input_available" and report["blockers"]:
        raise ValueError("flow input cannot be available while blockers are present")
    if report["status"] == "point_in_time_flow_extreme_input_available" and not report.get("proxy_basis"):
        raise ValueError("available flow input requires proxy basis")
    for row in _as_list(report.get("input_rows")):
        if _as_dict(row).get("proof_eligible") is not False:
            raise ValueError("input rows cannot be proof eligible")


def render_markdown(report: dict[str, Any]) -> str:
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Point-in-Time Flow-Extreme Input",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_flow_extreme_input.py`. It is a read-only input materializer for the flow-extreme ratio/backspread research branch. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Date coverage: `{coverage.get('date_coverage_pct')}`.",
        f"- Accepted source rows: `{report.get('accepted_source_row_count')}`.",
        f"- Proxy basis: `{json.dumps(report.get('proxy_basis'))}`.",
        "",
        "## Source Inventory",
        "",
        "```json",
        json.dumps(report.get("source_inventory"), indent=2, sort_keys=True),
        "```",
        "",
        "## Threshold Policy",
        "",
        "```json",
        json.dumps(report.get("threshold_policy"), indent=2, sort_keys=True),
        "```",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
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
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only point-in-time flow-extreme input artifact.")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--underlyings", default=DEFAULT_UNDERLYINGS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        source_rows_path=args.source_rows,
        feature_store_path=args.feature_store,
        preregistered_playbook_path=args.preregistered_playbook,
        options_history_db_path=args.options_history_db,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        underlyings=args.underlyings,
        no_write=args.no_write,
    )
    report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
