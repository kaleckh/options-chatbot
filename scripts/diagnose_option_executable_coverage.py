from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "option_executable_coverage_diagnostic"

DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_CANDIDATE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "option-executable-coverage-diagnostic"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-cvx-executable-coverage.md"

DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
DEFAULT_SNAPSHOT_KIND = "intraday"
TRUSTED_DATA_TRUST = "trusted"
DEFAULT_MIN_EXECUTABLE_QUOTE_PCT = 90.0

REQUIRED_QUOTE_COLUMNS = {
    "as_of_utc",
    "quote_date_et",
    "quote_minute_et",
    "snapshot_kind",
    "underlying",
    "contract_symbol",
    "expiry",
    "option_type",
    "strike",
    "bid",
    "ask",
    "underlying_price",
    "source_batch_id",
}
REQUIRED_BATCH_COLUMNS = {"id", "source_label", "data_trust"}

PROHIBITED_ACTIONS = (
    "do_not_backfill_midpoints_or_synthetic_bids",
    "do_not_lower_executable_quote_floor",
    "do_not_count_zero_bid_rows_as_executable_proof",
    "do_not_create_live_row_from_coverage_diagnostic",
    "do_not_submit_broker_order_from_coverage_diagnostic",
    "do_not_change_scanner_policy_from_coverage_diagnostic",
    "do_not_count_historical_rows_as_fresh_forward_promotion_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _pct(part: Any, total: Any) -> float:
    numerator = _safe_float(part) or 0.0
    denominator = _safe_float(total) or 0.0
    return round((numerator / denominator) * 100.0, 2) if denominator else 0.0


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return ("CVX",)
    result: list[str] = []
    seen: set[str] = set()
    for item in str(value).replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            result.append(symbol)
            seen.add(symbol)
    if not result:
        raise argparse.ArgumentTypeError("At least one symbol is required.")
    return tuple(result)


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _schema_status(conn: sqlite3.Connection) -> dict[str, Any]:
    quote_columns = _table_columns(conn, "option_quote_snapshots")
    batch_columns = _table_columns(conn, "import_batches")
    return {
        "option_quote_snapshots_missing_columns": sorted(REQUIRED_QUOTE_COLUMNS - quote_columns),
        "import_batches_missing_columns": sorted(REQUIRED_BATCH_COLUMNS - batch_columns),
    }


def _base_where() -> str:
    return """
        q.underlying = ?
        AND q.snapshot_kind = ?
        AND b.source_label = ?
        AND b.data_trust = ?
    """


def _base_params(symbol: str, snapshot_kind: str, source_label: str) -> tuple[str, str, str, str]:
    return (symbol, snapshot_kind, source_label, TRUSTED_DATA_TRUST)


def _coverage_select() -> str:
    return """
        COUNT(*) AS quote_rows,
        SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid > 0 AND q.ask > 0 AND q.ask >= q.bid THEN 1 ELSE 0 END)
            AS executable_quote_rows,
        SUM(CASE WHEN q.bid = 0 AND q.ask IS NOT NULL AND q.ask > 0 AND q.ask >= q.bid THEN 1 ELSE 0 END)
            AS zero_bid_positive_ask_rows,
        SUM(CASE WHEN q.bid IS NULL OR q.ask IS NULL THEN 1 ELSE 0 END)
            AS missing_bid_ask_rows,
        SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.ask < q.bid THEN 1 ELSE 0 END)
            AS crossed_quote_rows,
        SUM(CASE WHEN q.ask IS NOT NULL AND q.ask <= 0 THEN 1 ELSE 0 END)
            AS nonpositive_ask_rows,
        SUM(CASE WHEN q.bid IS NOT NULL AND q.bid < 0 THEN 1 ELSE 0 END)
            AS negative_bid_rows,
        SUM(CASE WHEN q.underlying_price IS NOT NULL THEN 1 ELSE 0 END)
            AS rows_with_underlying_price
    """


def _decorate_coverage(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    quote_rows = _safe_int(item.get("quote_rows"))
    executable_rows = _safe_int(item.get("executable_quote_rows"))
    zero_bid_rows = _safe_int(item.get("zero_bid_positive_ask_rows"))
    missing_rows = _safe_int(item.get("missing_bid_ask_rows"))
    crossed_rows = _safe_int(item.get("crossed_quote_rows"))
    nonpositive_ask_rows = _safe_int(item.get("nonpositive_ask_rows"))
    negative_bid_rows = _safe_int(item.get("negative_bid_rows"))
    underlying_price_rows = _safe_int(item.get("rows_with_underlying_price"))
    non_executable_rows = max(quote_rows - executable_rows, 0)
    item.update(
        {
            "quote_rows": quote_rows,
            "executable_quote_rows": executable_rows,
            "non_executable_quote_rows": non_executable_rows,
            "zero_bid_positive_ask_rows": zero_bid_rows,
            "missing_bid_ask_rows": missing_rows,
            "crossed_quote_rows": crossed_rows,
            "nonpositive_ask_rows": nonpositive_ask_rows,
            "negative_bid_rows": negative_bid_rows,
            "rows_with_underlying_price": underlying_price_rows,
            "executable_quote_pct": _pct(executable_rows, quote_rows),
            "non_executable_quote_pct": _pct(non_executable_rows, quote_rows),
            "zero_bid_positive_ask_pct": _pct(zero_bid_rows, quote_rows),
            "zero_bid_share_of_non_executable_pct": _pct(zero_bid_rows, non_executable_rows),
            "missing_bid_ask_pct": _pct(missing_rows, quote_rows),
            "crossed_quote_pct": _pct(crossed_rows, quote_rows),
            "underlying_price_pct": _pct(underlying_price_rows, quote_rows),
        }
    )
    return item


def _assessment(summary: dict[str, Any], *, min_executable_quote_pct: float) -> dict[str, Any]:
    quote_rows = _safe_int(summary.get("quote_rows"))
    executable_pct = _safe_float(summary.get("executable_quote_pct")) or 0.0
    non_executable_rows = _safe_int(summary.get("non_executable_quote_rows"))
    zero_bid_rows = _safe_int(summary.get("zero_bid_positive_ask_rows"))
    repair_like_rows = (
        _safe_int(summary.get("missing_bid_ask_rows"))
        + _safe_int(summary.get("crossed_quote_rows"))
        + _safe_int(summary.get("nonpositive_ask_rows"))
        + _safe_int(summary.get("negative_bid_rows"))
    )

    if quote_rows <= 0:
        status = "no_rows"
        action = "repair_missing_symbol_history_before_evaluating"
    elif executable_pct >= min_executable_quote_pct:
        status = "coverage_floor_passed"
        action = "eligible_for_source_quality_floor_on_this_symbol"
    elif non_executable_rows > 0 and zero_bid_rows == non_executable_rows and repair_like_rows == 0:
        status = "zero_bid_tradability_floor_failure"
        action = "treat_as_real_zero_bid_tradability_failure_or_preregister_candidate_scope_exclusion"
    elif non_executable_rows > 0 and _pct(zero_bid_rows, non_executable_rows) >= 80.0 and repair_like_rows == 0:
        status = "mostly_zero_bid_tradability_floor_failure"
        action = "do_not_synthesize_bids; candidate_scope_or_symbol_surface_rule_must_handle_it"
    elif repair_like_rows > 0:
        status = "source_data_repair_needed"
        action = "inspect_missing_crossed_or_nonpositive_ask_rows_before_using_symbol_surface"
    else:
        status = "mixed_non_executable_failure"
        action = "inspect_symbol_surface_before_using_for_nomination"

    return {
        "status": status,
        "min_executable_quote_pct": float(min_executable_quote_pct),
        "passed": status == "coverage_floor_passed",
        "recommended_action": action,
        "non_proof_warning": "This diagnosis is source-quality evidence only; it is not fresh forward realized P&L.",
    }


def _symbol_summary(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
    min_executable_quote_pct: float,
) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT
            MIN(q.quote_date_et) AS first_quote_date_et,
            MAX(q.quote_date_et) AS latest_quote_date_et,
            COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
            COUNT(DISTINCT q.contract_symbol) AS contract_count,
            {_coverage_select()}
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {_base_where()}
        """,
        _base_params(symbol, snapshot_kind, source_label),
    ).fetchone()
    summary = _decorate_coverage(row or {})
    summary.update(
        {
            "symbol": symbol,
            "source_label": source_label,
            "snapshot_kind": snapshot_kind,
            "data_trust": TRUSTED_DATA_TRUST,
            "first_quote_date_et": row["first_quote_date_et"] if row else None,
            "latest_quote_date_et": row["latest_quote_date_et"] if row else None,
            "quote_date_count": _safe_int(row["quote_date_count"] if row else 0),
            "contract_count": _safe_int(row["contract_count"] if row else 0),
        }
    )
    summary["assessment"] = _assessment(summary, min_executable_quote_pct=min_executable_quote_pct)
    return summary


def _coverage_groups(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
    group_expr: str,
    order_expr: str = "bucket",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = conn.execute(
        f"""
        SELECT
            {group_expr} AS bucket,
            {_coverage_select()}
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {_base_where()}
        GROUP BY bucket
        ORDER BY {order_expr}
        {limit_sql}
        """,
        _base_params(symbol, snapshot_kind, source_label),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = _decorate_coverage(row)
        item["bucket"] = _norm(row["bucket"]) or "unknown"
        result.append(item)
    return result


def _non_executable_reasons(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        WITH scoped AS (
            SELECT
                CASE
                    WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid > 0 AND q.ask > 0 AND q.ask >= q.bid
                        THEN 'executable'
                    WHEN q.bid IS NULL OR q.ask IS NULL
                        THEN 'missing_bid_or_ask'
                    WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.ask < q.bid
                        THEN 'crossed_quote'
                    WHEN q.ask IS NOT NULL AND q.ask <= 0
                        THEN 'nonpositive_ask'
                    WHEN q.bid = 0 AND q.ask IS NOT NULL AND q.ask > 0 AND q.ask >= q.bid
                        THEN 'zero_bid_positive_ask'
                    WHEN q.bid IS NOT NULL AND q.bid < 0
                        THEN 'negative_bid'
                    ELSE 'other_non_executable'
                END AS reason
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE {_base_where()}
        )
        SELECT reason, COUNT(*) AS row_count
        FROM scoped
        WHERE reason != 'executable'
        GROUP BY reason
        ORDER BY row_count DESC, reason
        """,
        _base_params(symbol, snapshot_kind, source_label),
    ).fetchall()
    total = sum(_safe_int(row["row_count"]) for row in rows)
    return [
        {"reason": str(row["reason"]), "row_count": _safe_int(row["row_count"]), "share_of_non_executable_pct": _pct(row["row_count"], total)}
        for row in rows
    ]


def _candidate_membership(candidate_report: Path, symbols: Sequence[str]) -> dict[str, Any]:
    wanted = {symbol.upper() for symbol in symbols}
    result = {
        symbol: {
            "selected_trade_count": 0,
            "suppressed_duplicate_count": 0,
            "selected_trade_lanes": {},
        }
        for symbol in wanted
    }
    meta = {"path": str(candidate_report), "exists": candidate_report.exists(), "status": "missing", "error": None}
    if not candidate_report.exists():
        return {"meta": meta, "symbols": result}
    try:
        payload = json.loads(candidate_report.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {"meta": meta, "symbols": result}
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {"meta": meta, "symbols": result}
    meta["status"] = "loaded"
    selected_lanes: dict[str, Counter[str]] = {symbol: Counter() for symbol in wanted}
    for row in _as_list(payload.get("selected_trades")):
        row = _as_dict(row)
        ticker = _norm(row.get("ticker") or row.get("underlying") or row.get("symbol")).upper()
        if ticker in wanted:
            result[ticker]["selected_trade_count"] += 1
            selected_lanes[ticker][_norm(row.get("lane_id") or row.get("lane") or "unknown")] += 1
    for row in _as_list(payload.get("suppressed_duplicates")):
        row = _as_dict(row)
        ticker = _norm(row.get("ticker") or row.get("underlying") or row.get("symbol")).upper()
        if ticker in wanted:
            result[ticker]["suppressed_duplicate_count"] += 1
    for symbol, lanes in selected_lanes.items():
        result[symbol]["selected_trade_lanes"] = dict(sorted(lanes.items()))
    return {"meta": meta, "symbols": result}


def _symbol_detail(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
    min_executable_quote_pct: float,
) -> dict[str, Any]:
    return {
        "summary": _symbol_summary(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            min_executable_quote_pct=min_executable_quote_pct,
        ),
        "non_executable_reasons": _non_executable_reasons(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
        ),
        "by_option_type": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr="LOWER(q.option_type)",
        ),
        "by_dte_bucket": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr=(
                "CASE "
                "WHEN CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER) < 21 THEN 'lt_21' "
                "WHEN CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER) <= 30 THEN 'dte_21_30' "
                "WHEN CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER) <= 45 THEN 'dte_31_45' "
                "WHEN CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER) <= 60 THEN 'dte_46_60' "
                "ELSE 'gt_60' END"
            ),
        ),
        "by_abs_moneyness_bucket": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr=(
                "CASE "
                "WHEN q.underlying_price IS NULL OR q.underlying_price <= 0 THEN 'missing_underlying_price' "
                "WHEN ABS(q.strike / q.underlying_price - 1.0) <= 0.05 THEN 'abs_moneyness_le_5pct' "
                "WHEN ABS(q.strike / q.underlying_price - 1.0) <= 0.10 THEN 'abs_moneyness_5_10pct' "
                "WHEN ABS(q.strike / q.underlying_price - 1.0) <= 0.15 THEN 'abs_moneyness_10_15pct' "
                "WHEN ABS(q.strike / q.underlying_price - 1.0) <= 0.20 THEN 'abs_moneyness_15_20pct' "
                "ELSE 'abs_moneyness_gt_20pct' END"
            ),
        ),
        "by_month": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr="substr(q.quote_date_et, 1, 7)",
        ),
        "by_quote_minute": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr="CAST(q.quote_minute_et AS TEXT)",
            order_expr="CAST(bucket AS INTEGER)",
        ),
        "worst_quote_dates": _coverage_groups(
            conn,
            symbol=symbol,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            group_expr="q.quote_date_et",
            order_expr="(1.0 * executable_quote_rows / NULLIF(quote_rows, 0)) ASC, quote_rows DESC, bucket ASC",
            limit=15,
        ),
    }


def _summary_from_symbols(symbol_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter()
    for detail in symbol_reports.values():
        status_counts[_as_dict(_as_dict(detail.get("summary")).get("assessment")).get("status") or "unknown"] += 1
    return {
        "symbol_count": len(symbol_reports),
        "status_counts": dict(sorted(status_counts.items())),
        "all_symbols_pass": bool(symbol_reports) and all(
            _as_dict(_as_dict(detail.get("summary")).get("assessment")).get("passed") for detail in symbol_reports.values()
        ),
        "promotion_ready": False,
        "read_only": True,
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    symbols: Sequence[str] = ("CVX",),
    source_label: str = DEFAULT_SOURCE_LABEL,
    snapshot_kind: str = DEFAULT_SNAPSHOT_KIND,
    min_executable_quote_pct: float = DEFAULT_MIN_EXECUTABLE_QUOTE_PCT,
    candidate_report: Path = DEFAULT_CANDIDATE_REPORT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    normalized_symbols = tuple(symbol.strip().upper() for symbol in symbols if symbol.strip())
    if not db_path.exists():
        return {
            "report_id": REPORT_ID,
            "status": "blocked_missing_options_history_db",
            "generated_at_utc": generated_at_utc or _utc_now_iso(),
            "schema_version": 1,
            "read_only": True,
            "inputs": {
                "options_history_db": str(db_path),
                "source_label": source_label,
                "snapshot_kind": snapshot_kind,
                "data_trust": TRUSTED_DATA_TRUST,
                "symbols": list(normalized_symbols),
                "min_executable_quote_pct": float(min_executable_quote_pct),
                "candidate_report": str(candidate_report),
            },
            "summary": {"promotion_ready": False, "missing_required_inputs": ["options_history_db"]},
            "schema_check": {},
            "symbol_reports": {},
            "candidate_membership": _candidate_membership(candidate_report, normalized_symbols),
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        }

    with closing(_sqlite_readonly_connect(db_path)) as conn:
        schema = _schema_status(conn)
        missing_schema = list(schema["option_quote_snapshots_missing_columns"]) + list(schema["import_batches_missing_columns"])
        if missing_schema:
            status = "blocked_missing_schema_columns"
            symbol_reports: dict[str, dict[str, Any]] = {}
        else:
            status = "coverage_diagnostic_built"
            symbol_reports = {
                symbol: _symbol_detail(
                    conn,
                    symbol=symbol,
                    source_label=source_label,
                    snapshot_kind=snapshot_kind,
                    min_executable_quote_pct=min_executable_quote_pct,
                )
                for symbol in normalized_symbols
            }

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_source_quality_executable_coverage_diagnostic",
        "schema_version": 1,
        "read_only": True,
        "inputs": {
            "options_history_db": str(db_path),
            "source_label": source_label,
            "snapshot_kind": snapshot_kind,
            "data_trust": TRUSTED_DATA_TRUST,
            "symbols": list(normalized_symbols),
            "min_executable_quote_pct": float(min_executable_quote_pct),
            "candidate_report": str(candidate_report),
        },
        "summary": _summary_from_symbols(symbol_reports)
        | {"missing_required_inputs": ["schema_columns"] if status == "blocked_missing_schema_columns" else []},
        "schema_check": schema,
        "symbol_reports": symbol_reports,
        "candidate_membership": _candidate_membership(candidate_report, normalized_symbols),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _coverage_table(rows: Sequence[dict[str, Any]], *, bucket_label: str = "Bucket") -> list[str]:
    lines = [
        f"| {bucket_label} | Rows | Exec % | Zero-Bid % | Zero Share Non-Exec % | Missing | Crossed |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('bucket'))}`",
                    _cell(row.get("quote_rows")),
                    _cell(row.get("executable_quote_pct")),
                    _cell(row.get("zero_bid_positive_ask_pct")),
                    _cell(row.get("zero_bid_share_of_non_executable_pct")),
                    _cell(row.get("missing_bid_ask_rows")),
                    _cell(row.get("crossed_quote_rows")),
                ]
            )
            + " |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    inputs = _as_dict(report.get("inputs"))
    membership = _as_dict(_as_dict(report.get("candidate_membership")).get("symbols"))
    lines = [
        "# Option Executable Coverage Diagnostic",
        "",
        "This report is generated from `scripts/diagnose_option_executable_coverage.py`. It is a read-only source-quality diagnostic over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, lower proof bars, synthesize prices, or count historical rows as fresh forward promotion proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source: `{_cell(inputs.get('source_label'))}` / `{_cell(inputs.get('snapshot_kind'))}` / `{_cell(inputs.get('data_trust'))}`.",
        f"- Symbols: `{_json_inline(inputs.get('symbols') or [])}`.",
        f"- Minimum executable quote floor: `{inputs.get('min_executable_quote_pct')}`.",
        f"- Candidate report: `{_cell(inputs.get('candidate_report'))}`.",
        "",
        "| Symbol | Rows | Dates | Exec % | Non-Exec | Zero-Bid Positive-Ask | Zero Share Non-Exec % | Missing | Crossed | Assessment | Selected Trades | Suppressed Duplicates |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for symbol, detail in sorted(_as_dict(report.get("symbol_reports")).items()):
        summary = _as_dict(_as_dict(detail).get("summary"))
        assessment = _as_dict(summary.get("assessment"))
        member = _as_dict(membership.get(symbol))
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(symbol)}`",
                    _cell(summary.get("quote_rows")),
                    _cell(summary.get("quote_date_count")),
                    _cell(summary.get("executable_quote_pct")),
                    _cell(summary.get("non_executable_quote_rows")),
                    _cell(summary.get("zero_bid_positive_ask_rows")),
                    _cell(summary.get("zero_bid_share_of_non_executable_pct")),
                    _cell(summary.get("missing_bid_ask_rows")),
                    _cell(summary.get("crossed_quote_rows")),
                    f"`{_cell(assessment.get('status'))}`",
                    _cell(member.get("selected_trade_count")),
                    _cell(member.get("suppressed_duplicate_count")),
                ]
            )
            + " |"
        )

    for symbol, detail in sorted(_as_dict(report.get("symbol_reports")).items()):
        detail = _as_dict(detail)
        summary = _as_dict(detail.get("summary"))
        assessment = _as_dict(summary.get("assessment"))
        lines.extend(
            [
                "",
                f"## {symbol} Detail",
                "",
                f"- Recommended action: `{_cell(assessment.get('recommended_action'))}`.",
                f"- Underlying-price coverage: `{summary.get('underlying_price_pct')}`%.",
                "",
                "### Non-Executable Reasons",
                "",
                "| Reason | Rows | Share Of Non-Exec % |",
                "|---|---:|---:|",
            ]
        )
        reasons = _as_list(detail.get("non_executable_reasons"))
        if reasons:
            for row in reasons:
                row = _as_dict(row)
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{_cell(row.get('reason'))}`",
                            _cell(row.get("row_count")),
                            _cell(row.get("share_of_non_executable_pct")),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| `none` | 0 | 0.0 |")

        for title, key, label in (
            ("Option Type", "by_option_type", "Type"),
            ("DTE Bucket", "by_dte_bucket", "DTE"),
            ("Abs Moneyness Bucket", "by_abs_moneyness_bucket", "Bucket"),
            ("Month", "by_month", "Month"),
            ("Quote Minute", "by_quote_minute", "Minute ET"),
            ("Worst Quote Dates", "worst_quote_dates", "Date"),
        ):
            lines.extend(["", f"### {title}", ""])
            lines.extend(_coverage_table([_as_dict(row) for row in _as_list(detail.get(key))], bucket_label=label))

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A zero bid with a positive ask is an observed non-executable quote for proof purposes, not missing data. The allowed responses are source repair for genuinely bad rows, candidate-scope exclusion, or a kill verdict for affected candidates. The diagnostic must not be used to lower quote-quality floors or manufacture historical fills.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


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
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
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
    parser = argparse.ArgumentParser(description="Diagnose executable bid/ask coverage for option quote surfaces.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--symbols", type=_symbols, default=("CVX",))
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--snapshot-kind", default=DEFAULT_SNAPSHOT_KIND)
    parser.add_argument("--min-executable-quote-pct", type=float, default=DEFAULT_MIN_EXECUTABLE_QUOTE_PCT)
    parser.add_argument("--candidate-report", type=Path, default=DEFAULT_CANDIDATE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        db_path=args.db_path,
        symbols=args.symbols,
        source_label=args.source_label,
        snapshot_kind=args.snapshot_kind,
        min_executable_quote_pct=args.min_executable_quote_pct,
        candidate_report=args.candidate_report,
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
