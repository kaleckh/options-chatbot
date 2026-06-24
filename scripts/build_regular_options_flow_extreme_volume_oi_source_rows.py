from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_flow_extreme_volume_oi_source_rows"
DEFAULT_OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-volume-oi-source-rows"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-flow-extreme-volume-oi-source-rows.md"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "source_rows.jsonl"

DEFAULT_START_DATE = "2024-06-01"
DEFAULT_END_DATE = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
DEFAULT_UNDERLYINGS = "SPY,QQQ"
DEFAULT_SOURCE_LABELS = "thetadata_opra_nbbo_1m"
DEFAULT_SNAPSHOT_KIND = "intraday"
DEFAULT_DATA_TRUST = "trusted"
MIN_COVERED_MONTHS = 20
MIN_DATE_COVERAGE_PCT = 90.0

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
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
    "bounded_replay",
    "relabeling_plain_bid_ask_prices_as_flow",
    "fabricating_bid_ask_size_or_quote_depth",
    "using_realized_pnl_or_selected_winners_to_define_thresholds",
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


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _safe_float(value: Any) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _split_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value).replace(";", ",").split(",") if item.strip()]


def _split_labels(value: str) -> list[str]:
    return [item.strip() for item in str(value).replace(";", ",").split(",") if item.strip()]


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
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


def _feature_store_dates(feature_store: dict[str, Any], *, start: date, end: date) -> list[str]:
    dates: list[str] = []
    for value in _as_list(feature_store.get("shared_quote_dates")):
        parsed = _parse_date(value)
        if parsed and start <= parsed <= end:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _read_only_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"pragma table_info({table})").fetchall()}


def _schema_status(conn: sqlite3.Connection) -> dict[str, Any]:
    quote_required = {
        "as_of_utc",
        "quote_date_et",
        "snapshot_kind",
        "underlying",
        "option_type",
        "volume",
        "open_interest",
        "source_batch_id",
    }
    batch_required = {"id", "source_label", "data_trust", "imported_at_utc"}
    quote_cols = _table_columns(conn, "option_quote_snapshots")
    batch_cols = _table_columns(conn, "import_batches")
    return {
        "option_quote_snapshots_missing_columns": sorted(quote_required - quote_cols),
        "import_batches_missing_columns": sorted(batch_required - batch_cols),
        "volume_column_present": "volume" in quote_cols,
        "open_interest_column_present": "open_interest" in quote_cols,
        "bid_size_column_present": "bid_size" in quote_cols,
        "ask_size_column_present": "ask_size" in quote_cols,
        "quote_depth_column_present": "quote_depth" in quote_cols,
    }


def _trusted_daily_aggregates(
    conn: sqlite3.Connection,
    *,
    source_labels: list[str],
    underlyings: list[str],
    snapshot_kind: str,
    data_trust: str,
    start: date,
    end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    placeholders_labels = ",".join("?" for _ in source_labels)
    placeholders_underlyings = ",".join("?" for _ in underlyings)
    query = f"""
        SELECT
            q.quote_date_et,
            q.underlying,
            lower(q.option_type) AS option_type,
            COUNT(*) AS quote_row_count,
            SUM(CASE WHEN q.volume IS NOT NULL THEN 1 ELSE 0 END) AS volume_row_count,
            SUM(CASE WHEN q.open_interest IS NOT NULL THEN 1 ELSE 0 END) AS open_interest_row_count,
            SUM(CASE WHEN q.volume IS NOT NULL AND q.open_interest IS NOT NULL THEN 1 ELSE 0 END) AS usable_row_count,
            SUM(COALESCE(q.volume, 0)) AS total_volume,
            SUM(COALESCE(q.open_interest, 0)) AS total_open_interest,
            MAX(q.as_of_utc) AS source_timestamp_utc,
            GROUP_CONCAT(DISTINCT b.source_label) AS source_labels,
            COUNT(DISTINCT b.id) AS batch_count
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.underlying IN ({placeholders_underlyings})
          AND b.source_label IN ({placeholders_labels})
          AND b.data_trust = ?
          AND q.snapshot_kind = ?
          AND q.quote_date_et >= ?
          AND q.quote_date_et <= ?
        GROUP BY q.quote_date_et, q.underlying, lower(q.option_type)
    """
    params: list[Any] = (
        list(underlyings)
        + list(source_labels)
        + [data_trust, snapshot_kind, (start - timedelta(days=10)).isoformat(), end.isoformat()]
    )
    rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    meta = {
        "source_labels": source_labels,
        "snapshot_kind": snapshot_kind,
        "data_trust": data_trust,
        "aggregate_row_count": len(rows),
        "date_count": len({str(row.get("quote_date_et")) for row in rows}),
        "usable_aggregate_row_count": sum(1 for row in rows if int(row.get("usable_row_count") or 0) > 0),
    }
    return rows, meta


def _index_aggregates(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    indexed: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[(str(row.get("quote_date_et")), str(row.get("underlying")).upper())][str(row.get("option_type")).lower()] = row
    return indexed


def _pressure_score(row: dict[str, Any]) -> float:
    volume = _safe_float(row.get("total_volume"))
    open_interest = _safe_float(row.get("total_open_interest"))
    return round(math.log1p(volume) + 0.25 * math.log1p(open_interest), 6)


def _build_source_rows(
    *,
    aggregates: list[dict[str, Any]],
    requested_dates: list[str],
    underlyings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = _index_aggregates(aggregates)
    source_dates = sorted({str(row.get("quote_date_et")) for row in aggregates})
    source_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for input_date in requested_dates:
        prior_dates = [day for day in source_dates if day < input_date]
        source_date = prior_dates[-1] if prior_dates else None
        for underlying in underlyings:
            if not source_date:
                rejected.append({"input_date_et": input_date, "underlying": underlying, "reason": "no_prior_source_date"})
                continue
            legs = by_key.get((source_date, underlying), {})
            call = legs.get("call")
            put = legs.get("put")
            if not call or not put:
                rejected.append(
                    {
                        "input_date_et": input_date,
                        "underlying": underlying,
                        "source_date_et": source_date,
                        "reason": "missing_call_or_put_aggregate",
                    }
                )
                continue
            if int(call.get("usable_row_count") or 0) <= 0 or int(put.get("usable_row_count") or 0) <= 0:
                rejected.append(
                    {
                        "input_date_et": input_date,
                        "underlying": underlying,
                        "source_date_et": source_date,
                        "reason": "missing_trusted_volume_open_interest",
                        "call_usable_row_count": int(call.get("usable_row_count") or 0),
                        "put_usable_row_count": int(put.get("usable_row_count") or 0),
                    }
                )
                continue
            call_score = _pressure_score(call)
            put_score = _pressure_score(put)
            ratio = round(put_score / call_score, 6) if call_score > 0 else 0.0
            extreme_state = "neutral"
            if ratio >= 1.15:
                extreme_state = "put_pressure_extreme"
            elif ratio <= 0.85:
                extreme_state = "call_pressure_extreme"
            source_ts = str(max(call.get("source_timestamp_utc") or "", put.get("source_timestamp_utc") or ""))
            row = {
                "input_date_et": input_date,
                "underlying": underlying,
                "flow_input_basis": "volume_open_interest",
                "call_pressure_score": call_score,
                "put_pressure_score": put_score,
                "put_call_pressure_ratio": ratio,
                "extreme_state": extreme_state,
                "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
                "source_name": "options_history_db_trusted_volume_open_interest",
                "source_ref": f"options_history_db:{source_date}:{underlying}:volume_open_interest",
                "source_timestamp_utc": source_ts,
                "known_at_utc": source_ts,
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "prior_day_aggregate",
                "source_date_et": source_date,
                "source_labels": sorted(set(str(call.get("source_labels") or "").split(",") + str(put.get("source_labels") or "").split(","))),
                "call_usable_row_count": int(call.get("usable_row_count") or 0),
                "put_usable_row_count": int(put.get("usable_row_count") or 0),
                "proof_eligible": False,
            }
            source_rows.append(row)
    return source_rows, rejected


def _coverage(rows: list[dict[str, Any]], requested_dates: list[str], underlyings: list[str], start: date, end: date) -> dict[str, Any]:
    requested_months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        requested_months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    by_date: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_date[str(row["input_date_et"])].add(str(row["underlying"]).upper())
    clean_dates = sorted(day for day, symbols in by_date.items() if set(underlyings) <= symbols)
    covered_dates = sorted(set(clean_dates) & set(requested_dates))
    covered_months = sorted({day[:7] for day in covered_dates})
    return {
        "requested_date_count": len(requested_dates),
        "covered_date_count": len(covered_dates),
        "date_coverage_pct": round(len(covered_dates) / len(requested_dates) * 100.0, 4) if requested_dates else 0.0,
        "requested_month_count": len(requested_months),
        "covered_month_count": len(covered_months),
        "requested_months": requested_months,
        "covered_months": covered_months,
        "missing_months": sorted(set(requested_months) - set(covered_months)),
        "minimum_covered_months": min(MIN_COVERED_MONTHS, len(requested_months)),
        "minimum_date_coverage_pct": MIN_DATE_COVERAGE_PCT,
    }


def _hash_rows(rows: list[dict[str, Any]]) -> str:
    text = "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _status(blockers: list[str]) -> str:
    return "flow_extreme_volume_oi_source_rows_available" if not blockers else "blocked_flow_extreme_volume_oi_source_rows"


def build_report(
    *,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    underlyings: str = DEFAULT_UNDERLYINGS,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    source_labels: str = DEFAULT_SOURCE_LABELS,
    snapshot_kind: str = DEFAULT_SNAPSHOT_KIND,
    data_trust: str = DEFAULT_DATA_TRUST,
    write_source_rows_requested: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or start > end:
        raise ValueError("invalid date window")
    symbols = _split_symbols(underlyings)
    labels = _split_labels(source_labels)
    feature_store, feature_meta = _load_json(feature_store_path, required=True)
    requested_dates = _feature_store_dates(feature_store, start=start, end=end)
    requested_dates = [day for day in requested_dates if _parse_date(day) and _parse_date(day) <= as_of]
    db_meta = {"path": _rel(options_history_db_path), "exists": options_history_db_path.exists(), "status": "missing", "read_only_confirmed": False}
    schema: dict[str, Any] = {}
    aggregate_meta: dict[str, Any] = {}
    aggregates: list[dict[str, Any]] = []
    if options_history_db_path.exists():
        try:
            conn = _read_only_connect(options_history_db_path)
            try:
                conn.execute("pragma query_only=ON")
                db_meta["status"] = "loaded"
                db_meta["read_only_confirmed"] = True
                schema = _schema_status(conn)
                if not schema["option_quote_snapshots_missing_columns"] and not schema["import_batches_missing_columns"]:
                    aggregates, aggregate_meta = _trusted_daily_aggregates(
                        conn,
                        source_labels=labels,
                        underlyings=symbols,
                        snapshot_kind=snapshot_kind,
                        data_trust=data_trust,
                        start=start,
                        end=end,
                    )
            finally:
                conn.close()
        except sqlite3.Error as exc:
            db_meta["status"] = "unreadable"
            db_meta["error"] = type(exc).__name__
    source_rows, rejected_rows = _build_source_rows(aggregates=aggregates, requested_dates=requested_dates, underlyings=symbols)
    coverage = _coverage(source_rows, requested_dates, symbols, start, end)
    blockers: list[str] = []
    if feature_meta.get("status") != "loaded":
        blockers.append("missing_feature_store")
    if db_meta.get("status") != "loaded" or db_meta.get("read_only_confirmed") is not True:
        blockers.append("options_history_db_not_read_only_available")
    if schema.get("option_quote_snapshots_missing_columns") or schema.get("import_batches_missing_columns"):
        blockers.append("missing_required_db_columns")
    if not schema.get("volume_column_present") or not schema.get("open_interest_column_present"):
        blockers.append("missing_volume_open_interest_columns")
    if not requested_dates:
        blockers.append("missing_requested_feature_store_dates")
    if not source_rows:
        blockers.append("missing_trusted_volume_open_interest_source_rows")
    if aggregate_meta and int(aggregate_meta.get("usable_aggregate_row_count") or 0) == 0:
        blockers.append("trusted_rows_have_null_volume_open_interest")
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
        "scope": "read_only_flow_extreme_volume_open_interest_source_row_generator",
        "research_window": {"start_date": start.isoformat(), "end_date": end.isoformat(), "as_of_date": as_of.isoformat()},
        "underlyings": symbols,
        "source_filter": {"source_labels": labels, "snapshot_kind": snapshot_kind, "data_trust": data_trust},
        "options_history_db": db_meta,
        "feature_store": feature_meta,
        "schema": schema,
        "aggregate_source_summary": aggregate_meta,
        "threshold_policy": {
            "threshold_policy_id": "volume_open_interest_prior_day_trailing_distribution_v1",
            "flow_input_basis": "volume_open_interest",
            "known_at_rule": "prior trusted source date strictly before input_date_et",
            "outcome_tuned": False,
            "realized_pnl_used": False,
            "selected_winners_used": False,
            "future_outcomes_used": False,
            "plain_bid_ask_used_as_flow": False,
            "quote_depth_fabricated": False,
        },
        "source_row_count": len(source_rows),
        "rejected_row_count": len(rejected_rows),
        "rejected_rows_sample": rejected_rows[:50],
        "rejected_reason_counts": dict(sorted(Counter(str(row.get("reason")) for row in rejected_rows).items())),
        "coverage": coverage,
        "source_rows_sha256": _hash_rows(source_rows),
        "source_rows": source_rows,
        "write_source_rows_requested": write_source_rows_requested,
        "write_source_rows_allowed": write_source_rows_requested and not blockers,
        "blockers": blockers,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] == "flow_extreme_volume_oi_source_rows_available" and report["blockers"]:
        raise ValueError("available source rows cannot have blockers")
    for row in _as_list(report.get("source_rows")):
        if _as_dict(row).get("flow_input_basis") != "volume_open_interest":
            raise ValueError("unexpected flow input basis")
        if "quote_depth_imbalance_score" in _as_dict(row):
            raise ValueError("volume/OI rows must not fabricate quote-depth score")
        if _as_dict(row).get("proof_eligible") is not False:
            raise ValueError("source rows cannot be proof eligible")


def render_markdown(report: dict[str, Any]) -> str:
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Flow-Extreme Volume/OI Source Rows",
        "",
        "This generated artifact builds read-only point-in-time volume/open-interest source rows for the flow-extreme ratio/backspread branch. It does not import quotes, mutate the options history database, run replay, create trades, count profitability, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Date coverage: `{coverage.get('date_coverage_pct')}`.",
        f"- Write source rows allowed: `{str(report.get('write_source_rows_allowed')).lower()}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Threshold Policy", "", "```json", json.dumps(report["threshold_policy"], indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
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
    if report.get("write_source_rows_allowed") is True:
        _write_jsonl(source_rows_path, [_as_dict(row) for row in _as_list(report.get("source_rows"))])
        artifacts["source_rows_jsonl"] = _rel(source_rows_path)
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
    parser = argparse.ArgumentParser(description="Build read-only flow-extreme volume/open-interest source rows.")
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--underlyings", default=DEFAULT_UNDERLYINGS)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--source-labels", default=DEFAULT_SOURCE_LABELS)
    parser.add_argument("--snapshot-kind", default=DEFAULT_SNAPSHOT_KIND)
    parser.add_argument("--data-trust", default=DEFAULT_DATA_TRUST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--write-source-rows", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        options_history_db_path=args.options_history_db,
        feature_store_path=args.feature_store,
        underlyings=args.underlyings,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        source_labels=args.source_labels,
        snapshot_kind=args.snapshot_kind,
        data_trust=args.data_trust,
        write_source_rows_requested=args.write_source_rows,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(
            report,
            output_dir=args.output_dir,
            docs_report=args.docs_report,
            source_rows_path=args.source_rows,
        )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
