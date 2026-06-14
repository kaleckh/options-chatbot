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
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_feature_store"

DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-feature-store"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-feature-store.md"

CORE_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
    "DIA",
)

DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
DEFAULT_SNAPSHOT_KIND = "intraday"
TRUSTED_DATA_TRUST = "trusted"

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
    "last",
    "iv",
    "underlying_price",
    "volume",
    "open_interest",
    "source_batch_id",
}
REQUIRED_BATCH_COLUMNS = {
    "id",
    "source_label",
    "dataset_kind",
    "data_trust",
    "file_hash",
    "imported_at_utc",
}

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_feature_store",
    "do_not_submit_broker_order_from_feature_store",
    "do_not_mutate_trading_database_from_feature_store",
    "do_not_change_scanner_policy_from_feature_store",
    "do_not_change_stop_policy_from_feature_store",
    "do_not_change_sizing_from_feature_store",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_feature_store",
    "do_not_count_feature_rows_as_forward_realized_pnl",
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


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _parse_utc(value: Any) -> datetime | None:
    raw = _norm(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return CORE_SYMBOLS
    result = []
    seen = set()
    for item in str(value).replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            result.append(symbol)
            seen.add(symbol)
    if not result:
        raise argparse.ArgumentTypeError("At least one symbol is required.")
    return tuple(result)


def build_quote_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    mid = round((bid + ask) / 2.0, 4) if bid is not None and ask is not None and ask >= bid else None
    spread_pct = None
    if mid is not None and mid > 0:
        spread_pct = round(((ask or 0.0) - (bid or 0.0)) / mid * 100.0, 4)
    as_of_utc = _norm(row.get("as_of_utc"))
    return {
        "feature_key": _norm(row.get("feature_key") or row.get("contract_symbol")),
        "underlying": _norm(row.get("underlying")).upper(),
        "contract_symbol": _norm(row.get("contract_symbol")).upper(),
        "expiry": _norm(row.get("expiry")),
        "option_type": _norm(row.get("option_type")).lower(),
        "strike": _round_optional(row.get("strike"), 4),
        "event_time": as_of_utc,
        "published_time": as_of_utc,
        "ingested_time": _norm(row.get("imported_at_utc")),
        "tradable_after_time": as_of_utc,
        "quote_date_et": _norm(row.get("quote_date_et")),
        "quote_minute_et": _safe_int(row.get("quote_minute_et")),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "bid_ask_spread_pct": spread_pct,
        "zero_bid_positive_ask": bool(bid == 0 and ask is not None and ask > 0),
        "iv": _safe_float(row.get("iv")),
        "underlying_price": _safe_float(row.get("underlying_price")),
        "volume": _safe_int(row.get("volume")) if row.get("volume") is not None else None,
        "open_interest": _safe_int(row.get("open_interest")) if row.get("open_interest") is not None else None,
        "source_label": _norm(row.get("source_label")),
        "dataset_kind": _norm(row.get("dataset_kind")),
        "data_trust": _norm(row.get("data_trust")),
        "source_batch_id": _safe_int(row.get("source_batch_id")),
    }


def latest_tradable_features(
    features: Iterable[dict[str, Any]],
    *,
    candidate_entry_time: str,
    key_fields: Sequence[str] = ("feature_key",),
) -> list[dict[str, Any]]:
    candidate_time = _parse_utc(candidate_entry_time)
    if candidate_time is None:
        raise ValueError("candidate_entry_time must be an ISO UTC timestamp")
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for feature in features:
        tradable_after = _parse_utc(feature.get("tradable_after_time"))
        if tradable_after is None or tradable_after > candidate_time:
            continue
        key = tuple(_norm(feature.get(field)) for field in key_fields)
        if not any(key):
            continue
        existing = grouped.get(key)
        existing_time = _parse_utc(existing.get("tradable_after_time")) if existing else None
        if existing is None or existing_time is None or tradable_after > existing_time:
            grouped[key] = dict(feature)
    return [grouped[key] for key in sorted(grouped)]


def _source_where() -> str:
    return """
        q.underlying = ?
        AND q.snapshot_kind = ?
        AND b.source_label = ?
        AND b.data_trust = ?
    """


def _symbol_dates(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
) -> set[str]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT q.quote_date_et
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {_source_where()}
        """,
        (symbol, snapshot_kind, source_label, TRUSTED_DATA_TRUST),
    ).fetchall()
    return {str(row["quote_date_et"]) for row in rows}


def _dte_buckets(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
) -> dict[str, int]:
    rows = conn.execute(
        f"""
        WITH dte_rows AS (
            SELECT CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER) AS dte
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE {_source_where()}
        )
        SELECT
            CASE
                WHEN dte < 21 THEN 'lt_21'
                WHEN dte <= 30 THEN 'dte_21_30'
                WHEN dte <= 45 THEN 'dte_31_45'
                WHEN dte <= 60 THEN 'dte_46_60'
                ELSE 'gt_60'
            END AS bucket,
            COUNT(*) AS row_count
        FROM dte_rows
        GROUP BY bucket
        ORDER BY bucket
        """,
        (symbol, snapshot_kind, source_label, TRUSTED_DATA_TRUST),
    ).fetchall()
    return {str(row["bucket"]): int(row["row_count"] or 0) for row in rows}


def _symbol_surface_row(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    source_label: str,
    snapshot_kind: str,
) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS quote_row_count,
            COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
            COUNT(DISTINCT q.contract_symbol) AS contract_count,
            MIN(q.quote_date_et) AS first_quote_date_et,
            MAX(q.quote_date_et) AS latest_quote_date_et,
            MIN(q.as_of_utc) AS first_as_of_utc,
            MAX(q.as_of_utc) AS latest_as_of_utc,
            MIN(q.quote_minute_et) AS min_quote_minute_et,
            MAX(q.quote_minute_et) AS max_quote_minute_et,
            MIN(b.imported_at_utc) AS first_imported_at_utc,
            MAX(b.imported_at_utc) AS latest_imported_at_utc,
            SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid THEN 1 ELSE 0 END) AS bid_ask_quote_count,
            SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid > 0 AND q.ask >= q.bid THEN 1 ELSE 0 END) AS positive_bid_ask_quote_count,
            SUM(CASE WHEN q.bid = 0 AND q.ask IS NOT NULL AND q.ask > 0 THEN 1 ELSE 0 END) AS zero_bid_positive_ask_count,
            AVG(CASE
                WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid AND ((q.ask + q.bid) / 2.0) > 0
                THEN ((q.ask - q.bid) / ((q.ask + q.bid) / 2.0)) * 100.0
                ELSE NULL
            END) AS avg_bid_ask_spread_pct,
            SUM(CASE WHEN q.iv IS NOT NULL THEN 1 ELSE 0 END) AS iv_row_count,
            AVG(CASE WHEN q.iv IS NOT NULL THEN q.iv ELSE NULL END) AS avg_iv,
            SUM(CASE WHEN q.underlying_price IS NOT NULL THEN 1 ELSE 0 END) AS underlying_price_row_count,
            SUM(CASE WHEN q.volume IS NOT NULL THEN 1 ELSE 0 END) AS volume_row_count,
            SUM(CASE WHEN q.open_interest IS NOT NULL THEN 1 ELSE 0 END) AS open_interest_row_count
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE {_source_where()}
        """,
        (symbol, snapshot_kind, source_label, TRUSTED_DATA_TRUST),
    ).fetchone()
    quote_rows = _safe_int(row["quote_row_count"] if row else 0)
    bid_ask_rows = _safe_int(row["bid_ask_quote_count"] if row else 0)
    positive_bid_ask_rows = _safe_int(row["positive_bid_ask_quote_count"] if row else 0)
    iv_rows = _safe_int(row["iv_row_count"] if row else 0)
    underlying_rows = _safe_int(row["underlying_price_row_count"] if row else 0)
    volume_rows = _safe_int(row["volume_row_count"] if row else 0)
    oi_rows = _safe_int(row["open_interest_row_count"] if row else 0)
    return {
        "symbol": symbol,
        "source_label": source_label,
        "snapshot_kind": snapshot_kind,
        "data_trust": TRUSTED_DATA_TRUST,
        "quote_row_count": quote_rows,
        "quote_date_count": _safe_int(row["quote_date_count"] if row else 0),
        "contract_count": _safe_int(row["contract_count"] if row else 0),
        "first_quote_date_et": row["first_quote_date_et"] if row else None,
        "latest_quote_date_et": row["latest_quote_date_et"] if row else None,
        "first_as_of_utc": row["first_as_of_utc"] if row else None,
        "latest_as_of_utc": row["latest_as_of_utc"] if row else None,
        "min_quote_minute_et": row["min_quote_minute_et"] if row else None,
        "max_quote_minute_et": row["max_quote_minute_et"] if row else None,
        "first_imported_at_utc": row["first_imported_at_utc"] if row else None,
        "latest_imported_at_utc": row["latest_imported_at_utc"] if row else None,
        "bid_ask_quote_count": bid_ask_rows,
        "bid_ask_quote_pct": round((bid_ask_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "positive_bid_ask_quote_count": positive_bid_ask_rows,
        "positive_bid_ask_quote_pct": round((positive_bid_ask_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "zero_bid_positive_ask_count": _safe_int(row["zero_bid_positive_ask_count"] if row else 0),
        "avg_bid_ask_spread_pct": _round_optional(row["avg_bid_ask_spread_pct"] if row else None, 4),
        "iv_row_count": iv_rows,
        "iv_coverage_pct": round((iv_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "avg_iv": _round_optional(row["avg_iv"] if row else None, 6),
        "underlying_price_row_count": underlying_rows,
        "underlying_price_coverage_pct": round((underlying_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "volume_row_count": volume_rows,
        "volume_coverage_pct": round((volume_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "open_interest_row_count": oi_rows,
        "open_interest_coverage_pct": round((oi_rows / quote_rows) * 100.0, 2) if quote_rows else 0.0,
        "dte_bucket_counts": _dte_buckets(conn, symbol=symbol, source_label=source_label, snapshot_kind=snapshot_kind)
        if quote_rows
        else {},
        "read_only": True,
    }


def _schema_status(conn: sqlite3.Connection) -> dict[str, Any]:
    quote_columns = _table_columns(conn, "option_quote_snapshots")
    batch_columns = _table_columns(conn, "import_batches")
    return {
        "option_quote_snapshots_missing_columns": sorted(REQUIRED_QUOTE_COLUMNS - quote_columns),
        "import_batches_missing_columns": sorted(REQUIRED_BATCH_COLUMNS - batch_columns),
    }


def _summary(
    *,
    status: str,
    db_path: Path,
    symbols: Sequence[str],
    symbol_rows: list[dict[str, Any]],
    shared_dates: set[str],
    missing_required_inputs: list[str],
) -> dict[str, Any]:
    total_rows = sum(_safe_int(row.get("quote_row_count")) for row in symbol_rows)
    symbol_status_counts = Counter("available" if _safe_int(row.get("quote_row_count")) else "missing" for row in symbol_rows)
    quote_dates = sorted(date for row in symbol_rows for date in (row.get("first_quote_date_et"), row.get("latest_quote_date_et")) if date)
    return {
        "overall_status": status,
        "db_path": str(db_path),
        "symbol_count": len(symbols),
        "available_symbol_count": symbol_status_counts.get("available", 0),
        "missing_symbol_count": symbol_status_counts.get("missing", 0),
        "symbol_status_counts": dict(sorted(symbol_status_counts.items())),
        "quote_row_count": total_rows,
        "first_quote_date_et": quote_dates[0] if quote_dates else None,
        "latest_quote_date_et": quote_dates[-1] if quote_dates else None,
        "shared_quote_date_count": len(shared_dates),
        "first_shared_quote_date_et": min(shared_dates) if shared_dates else None,
        "latest_shared_quote_date_et": max(shared_dates) if shared_dates else None,
        "min_symbol_quote_date_count": min((_safe_int(row.get("quote_date_count")) for row in symbol_rows), default=0),
        "missing_required_inputs": missing_required_inputs,
        "read_only": True,
        "promotion_ready": False,
    }


def build_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    symbols: Sequence[str] = CORE_SYMBOLS,
    source_label: str = DEFAULT_SOURCE_LABEL,
    snapshot_kind: str = DEFAULT_SNAPSHOT_KIND,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    normalized_symbols = tuple(symbol.strip().upper() for symbol in symbols if symbol.strip())
    if not db_path.exists():
        status = "blocked_missing_options_history_db"
        summary = _summary(
            status=status,
            db_path=db_path,
            symbols=normalized_symbols,
            symbol_rows=[],
            shared_dates=set(),
            missing_required_inputs=["options_history_db"],
        )
        return _report_payload(
            status=status,
            generated_at_utc=generated_at_utc,
            db_path=db_path,
            symbols=normalized_symbols,
            source_label=source_label,
            snapshot_kind=snapshot_kind,
            summary=summary,
            schema={},
            symbol_rows=[],
            shared_dates=[],
        )

    with closing(_sqlite_readonly_connect(db_path)) as conn:
        schema = _schema_status(conn)
        missing_schema = list(schema["option_quote_snapshots_missing_columns"]) + list(schema["import_batches_missing_columns"])
        if missing_schema:
            status = "blocked_missing_schema_columns"
            summary = _summary(
                status=status,
                db_path=db_path,
                symbols=normalized_symbols,
                symbol_rows=[],
                shared_dates=set(),
                missing_required_inputs=["schema_columns"],
            )
            return _report_payload(
                status=status,
                generated_at_utc=generated_at_utc,
                db_path=db_path,
                symbols=normalized_symbols,
                source_label=source_label,
                snapshot_kind=snapshot_kind,
                summary=summary,
                schema=schema,
                symbol_rows=[],
                shared_dates=[],
            )

        symbol_rows = [
            _symbol_surface_row(conn, symbol=symbol, source_label=source_label, snapshot_kind=snapshot_kind)
            for symbol in normalized_symbols
        ]
        date_sets = [
            _symbol_dates(conn, symbol=symbol, source_label=source_label, snapshot_kind=snapshot_kind)
            for symbol in normalized_symbols
        ]
    shared_dates = set.intersection(*date_sets) if date_sets else set()
    if not any(_safe_int(row.get("quote_row_count")) for row in symbol_rows):
        status = "blocked_no_trusted_theta_intraday_rows"
    elif any(_safe_int(row.get("quote_row_count")) == 0 for row in symbol_rows):
        status = "feature_store_partial"
    else:
        status = "feature_store_built"
    summary = _summary(
        status=status,
        db_path=db_path,
        symbols=normalized_symbols,
        symbol_rows=symbol_rows,
        shared_dates=shared_dates,
        missing_required_inputs=[],
    )
    return _report_payload(
        status=status,
        generated_at_utc=generated_at_utc,
        db_path=db_path,
        symbols=normalized_symbols,
        source_label=source_label,
        snapshot_kind=snapshot_kind,
        summary=summary,
        schema=schema,
        symbol_rows=symbol_rows,
        shared_dates=sorted(shared_dates),
    )


def _report_payload(
    *,
    status: str,
    generated_at_utc: str | None,
    db_path: Path,
    symbols: Sequence[str],
    source_label: str,
    snapshot_kind: str,
    summary: dict[str, Any],
    schema: dict[str, Any],
    symbol_rows: list[dict[str, Any]],
    shared_dates: list[str],
) -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_point_in_time_feature_store_read_only",
        "schema_version": 1,
        "read_only": True,
        "inputs": {
            "options_history_db": str(db_path),
            "source_label": source_label,
            "snapshot_kind": snapshot_kind,
            "data_trust": TRUSTED_DATA_TRUST,
            "symbols": list(symbols),
        },
        "schema_check": schema,
        "summary": summary,
        "feature_contract": {
            "row_grain": "underlying_contract_quote_timestamp",
            "time_fields": {
                "event_time": "option_quote_snapshots.as_of_utc",
                "published_time": "option_quote_snapshots.as_of_utc",
                "ingested_time": "import_batches.imported_at_utc",
                "tradable_after_time": "option_quote_snapshots.as_of_utc",
            },
            "point_in_time_join_rule": "candidate joins must require feature.tradable_after_time <= candidate_entry_time; if multiple rows match, use the latest tradable_after_time at or before candidate_entry_time",
            "trusted_source_filter": {
                "option_quote_snapshots.snapshot_kind": snapshot_kind,
                "import_batches.source_label": source_label,
                "import_batches.data_trust": TRUSTED_DATA_TRUST,
            },
            "non_proof_warning": "feature rows are research inputs only; they are not fresh forward realized P&L and do not grant live-validation promotion",
        },
        "symbol_surface_rows": symbol_rows,
        "shared_quote_dates": shared_dates,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Feature Store",
        "",
        "This report is generated from `scripts/build_regular_options_feature_store.py`. It builds a read-only point-in-time feature-store readback over trusted ThetaData intraday OPRA/NBBO quote rows. It does not create trades, submit broker orders, change scanner policy, mutate databases, lower proof bars, or count historical feature rows as forward promotion proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source: `{_cell(_as_dict(report.get('inputs')).get('source_label'))}` / `{_cell(_as_dict(report.get('inputs')).get('snapshot_kind'))}` / `{_cell(_as_dict(report.get('inputs')).get('data_trust'))}`.",
        f"- Symbols available: `{summary.get('available_symbol_count')}` / `{summary.get('symbol_count')}`.",
        f"- Quote rows: `{summary.get('quote_row_count')}`.",
        f"- Shared quote dates: `{summary.get('shared_quote_date_count')}` from `{summary.get('first_shared_quote_date_et')}` to `{summary.get('latest_shared_quote_date_et')}`.",
        f"- Missing required inputs: `{_json_inline(summary.get('missing_required_inputs') or [])}`.",
        "",
        "## Point-In-Time Contract",
        "",
        "- `event_time`, `published_time`, and `tradable_after_time` are the quote `as_of_utc`.",
        "- `ingested_time` is the local import batch timestamp and is provenance, not live tradability permission.",
        "- Candidate joins must require `feature.tradable_after_time <= candidate_entry_time`.",
        "",
        "## Symbol Surface Rows",
        "",
        "| Symbol | Dates | Rows | Contracts | Bid/Ask % | Positive Bid/Ask % | Zero-Bid Positive-Ask | Avg Spread % | IV Coverage % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in _as_list(report.get("symbol_surface_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('symbol'))}`",
                    _cell(row.get("quote_date_count")),
                    _cell(row.get("quote_row_count")),
                    _cell(row.get("contract_count")),
                    _cell(row.get("bid_ask_quote_pct")),
                    _cell(row.get("positive_bid_ask_quote_pct")),
                    _cell(row.get("zero_bid_positive_ask_count")),
                    _cell(row.get("avg_bid_ask_spread_pct")),
                    _cell(row.get("iv_coverage_pct")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a feature readback, not production proof. It may support historical split evaluation and later forward nomination work, but live-validation eligibility still requires the existing forward exact realized-P&L evidence chain.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options point-in-time feature store.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--symbols", type=_symbols, default=CORE_SYMBOLS)
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--snapshot-kind", default=DEFAULT_SNAPSHOT_KIND)
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
