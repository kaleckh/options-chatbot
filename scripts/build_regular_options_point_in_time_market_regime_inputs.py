from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_point_in_time_market_regime_inputs"

DEFAULT_MARKET_DATA_DB = ROOT / "market_data.db"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_UNDERLYING_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-underlying-daily-history"
    / "source_rows.jsonl"
)
DEFAULT_UNDERLYING_SOURCE_IMPORT_REPORT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-underlying-daily-source-import"
    / "latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-market-regime-inputs"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-market-regime-inputs.md"

DEFAULT_START_DATE = "2024-06-01"
DEFAULT_END_DATE = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
DEFAULT_UNIVERSE = "SPY,QQQ,IWM,DIA,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM"
DEFAULT_SOURCE = "alpaca_sip"
DEFAULT_ADJUSTMENT_MODE = "adjusted"
UNDERLYING_SOURCE_FAMILY = "point_in_time_underlying_daily_ohlcv_adjusted_v1"
POINT_IN_TIME_SOURCE_MODE = "point_in_time_verified_daily_history_source_rows"
HISTORICAL_RECONSTRUCTION_SOURCE_MODE = "historical_prior_bar_reconstruction"

MIN_COVERED_MONTHS = 20
MIN_DATE_COVERAGE_PCT = 90.0
MIN_BREADTH_AVAILABLE_SYMBOLS = 10
BREADTH_THRESHOLD = 0.60
SOURCE_ROW_REQUIRED_FIELDS = (
    "input_date_et",
    "symbol",
    "prior_bar_date_et",
    "close",
    "known_at_utc",
    "source_timestamp_utc",
    "source_ref",
    "source_file_hash",
    "source_row_hash",
    "prior_20_trading_day_return_pct",
    "prior_50_trading_day_sma",
    "source_family",
    "point_in_time_valid",
    "proof_eligible",
)
SOURCE_MARKER_FIELDS = (
    "source",
    "vendor",
    "source_name",
    "source_ref",
    "source_provenance_status",
    "provenance",
    "provenance_id",
    "source_quality",
    "data_trust",
    "row_type",
    "proof_exclusion_reason",
)
UNTRUSTED_SOURCE_MARKERS = ("stale", "manual", "synthetic", "source_mark", "source-mark")
DEFAULT_FIXTURE_MARKERS = ("fixture", "sample", "test_only", "fixture_only")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

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
    "market_data_db_mutation",
    "canonical_evidence_store_mutation",
    "forward_cohort_append",
    "protected_holdout_consumption",
    "promotion",
    "using_realized_pnl_or_selected_winners_to_define_thresholds",
    "using_option_marks_midpoints_eod_display_last_manual_synthetic_or_lookahead_rows_as_proof",
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
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_sha256_hex(value: Any) -> bool:
    return bool(SHA256_HEX_RE.fullmatch(str(value or "")))


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        meta["report_id"] = payload.get("report_id")
        meta["status_value"] = payload.get("status")
    meta["status"] = "loaded"
    return payload, meta


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                malformed += 1
                if malformed <= 5:
                    rows.append({"_malformed_line_number": line_number})
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                malformed += 1
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    meta["malformed_line_count"] = malformed
    return rows, meta


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


def _universe(value: str) -> tuple[str, ...]:
    symbols: list[str] = []
    seen: set[str] = set()
    for item in str(value).replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise argparse.ArgumentTypeError("universe must contain at least one symbol")
    return tuple(symbols)


def _feature_store_dates(feature_store: Any, *, start: date, end: date) -> list[str]:
    dates: list[str] = []
    for value in _as_list(_as_dict(feature_store).get("shared_quote_dates")):
        parsed = _parse_date(value)
        if parsed and start <= parsed <= end:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _candidate_decision_utc(input_date: date) -> datetime:
    return _parse_utc(f"{input_date.isoformat()}T13:35:00Z") or datetime.combine(input_date, datetime.min.time(), UTC)


def _marker_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(field) or "").lower() for field in SOURCE_MARKER_FIELDS)


def _source_row_reject_reasons(
    row: dict[str, Any],
    *,
    requested_dates: set[str],
    requested_universe: set[str],
    default_source_path: bool,
) -> list[str]:
    reasons: list[str] = []
    if "_malformed_line_number" in row:
        return ["malformed_jsonl_row"]
    for field in SOURCE_ROW_REQUIRED_FIELDS:
        if row.get(field) in (None, ""):
            reasons.append(f"missing_{field}")
    symbol = str(row.get("symbol") or "").upper()
    input_date = _parse_date(row.get("input_date_et"))
    prior_bar_date = _parse_date(row.get("prior_bar_date_et"))
    known_at = _parse_utc(row.get("known_at_utc"))
    source_timestamp = _parse_utc(row.get("source_timestamp_utc"))
    close = _safe_float(row.get("close"))
    prior_return = _safe_float(row.get("prior_20_trading_day_return_pct"))
    prior_sma = _safe_float(row.get("prior_50_trading_day_sma"))
    if symbol not in requested_universe:
        reasons.append("outside_requested_universe")
    if input_date is None or str(row.get("input_date_et"))[:10] not in requested_dates:
        reasons.append("outside_requested_window")
    if prior_bar_date is None:
        reasons.append("invalid_prior_bar_date")
    elif input_date is not None and prior_bar_date >= input_date:
        reasons.append("non_prior_bar")
    if known_at is None:
        reasons.append("missing_or_invalid_known_at_utc")
    elif input_date is not None and known_at >= _candidate_decision_utc(input_date):
        reasons.append("known_at_not_before_candidate_decision")
    if source_timestamp is None:
        reasons.append("missing_or_invalid_source_timestamp_utc")
    if close is None or close <= 0:
        reasons.append("missing_or_invalid_close")
    if prior_return is None:
        reasons.append("missing_or_invalid_prior_20_trading_day_return_pct")
    if prior_sma is None or prior_sma <= 0:
        reasons.append("missing_or_invalid_prior_50_trading_day_sma")
    if not _is_sha256_hex(row.get("source_file_hash")):
        reasons.append("invalid_source_file_hash")
    if not _is_sha256_hex(row.get("source_row_hash")):
        reasons.append("invalid_source_row_hash")
    if row.get("source_family") != UNDERLYING_SOURCE_FAMILY:
        reasons.append("source_family_mismatch")
    if row.get("proof_eligible") is not False:
        reasons.append("source_rows_proof_eligible_true")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_false")
    marker_text = _marker_text(row)
    if any(marker in marker_text for marker in UNTRUSTED_SOURCE_MARKERS):
        reasons.append("stale_manual_synthetic_or_source_mark_marker")
    if default_source_path and any(marker in marker_text for marker in DEFAULT_FIXTURE_MARKERS):
        reasons.append("default_source_rows_fixture_or_sample_contamination")
    return sorted(set(reasons))


def _path_matches_report_value(report_value: Any, path: Path) -> bool:
    text = str(report_value or "").strip()
    if not text:
        return False
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return candidate.resolve() == path.resolve()
    except OSError:
        return False


def _source_import_report_binding(
    *,
    import_report_path: Path | None,
    source_rows_path: Path,
    row_count: int,
    source_file_hashes: set[str],
) -> tuple[dict[str, Any], list[str]]:
    if import_report_path is None:
        return {
            "path": None,
            "status": "not_configured",
            "bound": False,
            "limitation": "source import report path was not configured; source rows are validated by row schema, point-in-time fields, and SHA-256 hash shape only",
        }, []
    payload, meta = _load_json(import_report_path, required=False)
    binding = {"path": _rel(import_report_path), "bound": False, "report": meta}
    if meta.get("status") == "missing":
        binding["status"] = "not_available"
        binding["limitation"] = "source import report is not present; source rows are validated by row schema, point-in-time fields, and SHA-256 hash shape only"
        return binding, []
    if meta.get("status") != "loaded" or not isinstance(payload, dict):
        binding["status"] = "invalid_report"
        return binding, ["source_import_report_unreadable_or_malformed"]

    reasons: list[str] = []
    expected_hash = str(payload.get("source_file_hash") or "")
    if payload.get("status") != "underlying_daily_history_source_import_materialized":
        reasons.append("source_import_report_not_materialized")
    if payload.get("source_rows_written") is not True:
        reasons.append("source_import_report_source_rows_not_written")
    if not _path_matches_report_value(payload.get("source_rows_path"), source_rows_path):
        reasons.append("source_rows_path_not_bound_to_import_report")
    if int(payload.get("source_row_count") or -1) != row_count:
        reasons.append("source_row_count_not_bound_to_import_report")
    if not _is_sha256_hex(expected_hash) or source_file_hashes != {expected_hash}:
        reasons.append("source_file_hash_not_bound_to_import_report")

    binding.update(
        {
            "status": "bound" if not reasons else "binding_failed",
            "bound": not reasons,
            "expected_source_file_hash": expected_hash or None,
            "observed_source_file_hashes": sorted(source_file_hashes),
            "expected_source_rows_path": payload.get("source_rows_path"),
            "expected_source_row_count": payload.get("source_row_count"),
            "observed_source_row_count": row_count,
        }
    )
    return binding, reasons


def _validate_underlying_source_rows(
    path: Path,
    *,
    requested_dates: list[str],
    universe: tuple[str, ...],
    import_report_path: Path | None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows, meta = _load_jsonl(path)
    requested_date_set = set(requested_dates)
    requested_universe = set(universe)
    default_source_path = path.resolve() == DEFAULT_UNDERLYING_SOURCE_ROWS.resolve()
    reject_counts: Counter[str] = Counter()
    rejects: list[dict[str, Any]] = []
    valid_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_keys: set[tuple[str, str]] = set()
    duplicate_count = 0
    source_file_hashes: set[str] = set()
    for index, row in enumerate(rows, start=1):
        reasons = _source_row_reject_reasons(
            row,
            requested_dates=requested_date_set,
            requested_universe=requested_universe,
            default_source_path=default_source_path,
        )
        key = (str(row.get("input_date_et") or "")[:10], str(row.get("symbol") or "").upper())
        if not reasons and key in seen_keys:
            reasons.append("duplicate_symbol_input_date_source_row")
            duplicate_count += 1
        if reasons:
            reject_counts.update(reasons)
            rejects.append(
                {
                    "index": index,
                    "symbol": str(row.get("symbol") or "").upper() or None,
                    "input_date_et": row.get("input_date_et"),
                    "prior_bar_date_et": row.get("prior_bar_date_et"),
                    "reasons": reasons,
                }
            )
            continue
        source_file_hashes.add(str(row.get("source_file_hash")))
        seen_keys.add(key)
        normalized = dict(row)
        normalized["symbol"] = key[1]
        normalized["input_date_et"] = key[0]
        normalized["prior_bar_date_et"] = str(row["prior_bar_date_et"])[:10]
        normalized["date"] = _parse_date(key[0])
        normalized["prior_bar_date"] = _parse_date(row["prior_bar_date_et"])
        normalized["close"] = float(row["close"])
        normalized["known_at_utc_parsed"] = _parse_utc(row["known_at_utc"])
        valid_by_symbol[key[1]].append(normalized)

    for symbol in valid_by_symbol:
        valid_by_symbol[symbol].sort(key=lambda item: (item["date"], item["prior_bar_date"]))

    per_symbol: dict[str, dict[str, Any]] = {}
    for symbol in universe:
        covered = {row["input_date_et"] for row in valid_by_symbol.get(symbol, [])}
        coverage_pct = round(len(covered & requested_date_set) / len(requested_date_set) * 100.0, 4) if requested_date_set else 0.0
        per_symbol[symbol] = {
            "covered_date_count": len(covered & requested_date_set),
            "requested_date_count": len(requested_date_set),
            "coverage_pct": coverage_pct,
            "coverage_ready": coverage_pct >= MIN_DATE_COVERAGE_PCT,
        }

    min_coverage = min((item["coverage_pct"] for item in per_symbol.values()), default=0.0)
    import_report_binding, import_report_reasons = _source_import_report_binding(
        import_report_path=import_report_path,
        source_rows_path=path,
        row_count=len(rows),
        source_file_hashes=source_file_hashes,
    )
    reject_counts.update(import_report_reasons)
    coverage_ready = (
        bool(requested_date_set)
        and not rejects
        and not import_report_reasons
        and all(item["coverage_ready"] for item in per_symbol.values())
        and set(valid_by_symbol) == requested_universe
    )
    if meta.get("status") == "loaded":
        meta.update(
            {
                "status": "loaded_ready" if coverage_ready else "loaded_invalid",
                "source_family": UNDERLYING_SOURCE_FAMILY,
                "default_source_rows_path": default_source_path,
                "valid_row_count": sum(len(items) for items in valid_by_symbol.values()),
                "reject_count": len(rejects),
                "reject_counts": dict(sorted(reject_counts.items())),
                "rejected_rows": rejects[:50],
                "source_import_report_binding": import_report_binding,
                "duplicate_symbol_input_date_count": duplicate_count,
                "per_symbol_coverage": per_symbol,
                "min_symbol_date_coverage_pct": min_coverage,
                "min_date_coverage_required_pct": MIN_DATE_COVERAGE_PCT,
                "coverage_ready": coverage_ready,
                "source_mode": POINT_IN_TIME_SOURCE_MODE if coverage_ready else None,
            }
        )
    return dict(valid_by_symbol), meta


def _load_daily_history(
    path: Path,
    *,
    symbols: tuple[str, ...],
    as_of: date,
    source: str,
    adjustment_mode: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "error": None}
    history: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    if not path.exists():
        meta["error"] = "missing_market_data_db"
        return history, meta
    try:
        conn = _sqlite_readonly_connect(path)
        try:
            columns = {str(row["name"]) for row in conn.execute("pragma table_info(daily_history)").fetchall()}
            required = {"symbol", "bar_date", "close", "fetched_at", "source", "adjustment_mode"}
            missing = sorted(required - columns)
            if missing:
                meta["status"] = "missing_schema_columns"
                meta["missing_columns"] = missing
                return history, meta
            placeholders = ", ".join("?" for _ in symbols)
            rows = conn.execute(
                f"""
                SELECT symbol, bar_date, close, fetched_at, source, adjustment_mode
                FROM daily_history
                WHERE symbol IN ({placeholders})
                  AND bar_date <= ?
                  AND source = ?
                  AND adjustment_mode = ?
                ORDER BY symbol, bar_date
                """,
                (*symbols, as_of.isoformat(), source, adjustment_mode),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return history, meta

    rejected_row_counts: Counter[str] = Counter()
    for row in rows:
        parsed_date = _parse_date(row["bar_date"])
        close = _safe_float(row["close"])
        fetched_at = _parse_utc(row["fetched_at"])
        symbol = str(row["symbol"]).upper()
        if symbol not in history:
            rejected_row_counts["outside_requested_universe"] += 1
            continue
        if parsed_date is None:
            rejected_row_counts["invalid_bar_date"] += 1
            continue
        if close is None or close <= 0:
            rejected_row_counts["invalid_close"] += 1
            continue
        if fetched_at is None:
            rejected_row_counts["invalid_fetched_at"] += 1
            continue
        history[symbol].append(
            {
                "symbol": symbol,
                "bar_date": parsed_date.isoformat(),
                "date": parsed_date,
                "close": close,
                "fetched_at": row["fetched_at"],
                "fetched_at_utc": fetched_at,
                "source": row["source"],
                "adjustment_mode": row["adjustment_mode"],
            }
        )
    meta["status"] = "loaded"
    meta["source"] = source
    meta["adjustment_mode"] = adjustment_mode
    meta["rejected_row_counts"] = dict(sorted(rejected_row_counts.items()))
    meta["symbols"] = {
        symbol: {
            "row_count": len(items),
            "first_bar_date": items[0]["bar_date"] if items else None,
            "latest_bar_date": items[-1]["bar_date"] if items else None,
            "latest_fetched_at_utc": _iso_utc(items[-1]["fetched_at_utc"]) if items else None,
        }
        for symbol, items in history.items()
    }
    return history, meta


def _prior_feature(symbol: str, rows: list[dict[str, Any]], input_date: date) -> tuple[dict[str, Any] | None, str | None]:
    prior_rows = [row for row in rows if row["date"] < input_date]
    if len(prior_rows) < 51:
        return None, "insufficient_prior_daily_close_history"
    prior = prior_rows[-1]
    close_20 = prior_rows[-21]["close"]
    sma_50_values = [float(row["close"]) for row in prior_rows[-50:]]
    if close_20 <= 0:
        return None, "invalid_20_day_reference_close"
    close = float(prior["close"])
    sma_50 = sum(sma_50_values) / len(sma_50_values)
    fetched_at = prior.get("fetched_at_utc")
    source_time_status = (
        "source_known_before_input_date"
        if isinstance(fetched_at, datetime) and fetched_at.date() < input_date
        else "source_not_auditable_before_input_date"
    )
    source_time_blocker = None if source_time_status == "source_known_before_input_date" else "source_fetched_at_not_before_input_date"
    return (
        {
            "symbol": symbol,
            "prior_bar_date_et": prior["bar_date"],
            "prior_close": round(close, 6),
            "prior_20_trading_day_return_pct": round(((close / close_20) - 1.0) * 100.0, 6),
            "prior_50_trading_day_sma": round(sma_50, 6),
            "above_prior_50_sma": close > sma_50,
            "source_name": "market_data_daily_history",
            "source_ref": f"market_data.db:daily_history:{symbol}:{prior['bar_date']}",
            "source_timestamp_utc": _iso_utc(fetched_at),
            "known_at_utc": _iso_utc(fetched_at),
            "source_fetched_at_raw": prior.get("fetched_at"),
            "source_timestamp_role": "daily_history_fetched_at",
            "source_provenance_status": source_time_status,
            "source_time_blocker": source_time_blocker,
            "point_in_time_valid": source_time_blocker is None,
            "historical_prior_bar_reconstruction": source_time_blocker is not None,
            "proof_eligible": False,
        },
        None,
    )


def _source_rows_feature(
    symbol: str,
    rows: list[dict[str, Any]],
    input_date: date,
    *,
    source_rows_path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    matching = [row for row in rows if row.get("date") == input_date]
    if not matching:
        return None, "missing_verified_underlying_source_row"
    row = matching[-1]
    close = float(row["close"])
    precomputed_return = _safe_float(row.get("prior_20_trading_day_return_pct"))
    precomputed_sma = _safe_float(row.get("prior_50_trading_day_sma"))
    if precomputed_return is None or precomputed_sma is None:
        return None, "missing_precomputed_underlying_rolling_metrics"
    prior_return = precomputed_return
    sma_50 = precomputed_sma
    source_ref = f"{_rel(source_rows_path)}:{symbol}:{row['input_date_et']}:{str(row.get('source_row_hash'))[:12]}"
    return (
        {
            "symbol": symbol,
            "prior_bar_date_et": row["prior_bar_date_et"],
            "prior_close": round(close, 6),
            "prior_20_trading_day_return_pct": round(prior_return, 6),
            "prior_50_trading_day_sma": round(sma_50, 6),
            "above_prior_50_sma": close > sma_50,
            "source_name": "underlying_daily_source_rows",
            "source_ref": source_ref,
            "upstream_source_ref": row.get("source_ref"),
            "source_timestamp_utc": row.get("source_timestamp_utc"),
            "known_at_utc": row.get("known_at_utc"),
            "source_timestamp_role": "source_rows_known_at_utc",
            "source_provenance_status": "source_rows_point_in_time_verified",
            "source_family": row.get("source_family"),
            "source_file_hash": row.get("source_file_hash"),
            "source_row_hash": row.get("source_row_hash"),
            "source_time_blocker": None,
            "point_in_time_valid": True,
            "historical_prior_bar_reconstruction": False,
            "proof_eligible": True,
        },
        None,
    )
def _market_regime_row(
    input_date: str,
    history: dict[str, list[dict[str, Any]]],
    universe: tuple[str, ...],
    *,
    source_mode: str,
    source_rows_path: Path | None = None,
) -> dict[str, Any]:
    parsed = _parse_date(input_date)
    if parsed is None:
        return {"input_date_et": input_date, "blockers": ["invalid_input_date"], "proof_eligible": False}
    symbol_features: dict[str, dict[str, Any]] = {}
    missing: dict[str, str] = {}
    for symbol in universe:
        if source_mode == POINT_IN_TIME_SOURCE_MODE:
            assert source_rows_path is not None
            feature, reason = _source_rows_feature(symbol, history.get(symbol, []), parsed, source_rows_path=source_rows_path)
        else:
            feature, reason = _prior_feature(symbol, history.get(symbol, []), parsed)
        if feature:
            symbol_features[symbol] = feature
        elif reason:
            missing[symbol] = reason
    blockers: list[str] = []
    spy = symbol_features.get("SPY")
    qqq = symbol_features.get("QQQ")
    if spy is None:
        blockers.append("missing_spy_momentum_inputs")
    if qqq is None:
        blockers.append("missing_qqq_momentum_inputs")
    if any(row.get("source_time_blocker") for row in symbol_features.values()):
        blockers.append("market_regime_source_time_not_point_in_time")
    available_symbol_count = len(symbol_features)
    above_count = sum(1 for row in symbol_features.values() if row["above_prior_50_sma"])
    breadth_ratio = above_count / available_symbol_count if available_symbol_count else None
    if available_symbol_count < MIN_BREADTH_AVAILABLE_SYMBOLS:
        blockers.append("insufficient_breadth_symbol_coverage")
    spy_confirmed = bool(
        spy
        and float(spy["prior_20_trading_day_return_pct"]) > 0.0
        and spy["above_prior_50_sma"] is True
    )
    qqq_confirmed = bool(
        qqq
        and float(qqq["prior_20_trading_day_return_pct"]) > 0.0
        and qqq["above_prior_50_sma"] is True
    )
    breadth_confirmed = bool(
        not blockers
        and breadth_ratio is not None
        and breadth_ratio >= BREADTH_THRESHOLD
        and available_symbol_count >= MIN_BREADTH_AVAILABLE_SYMBOLS
    )
    proof_eligible = source_mode == POINT_IN_TIME_SOURCE_MODE and not blockers
    return {
        "input_date_et": input_date,
        "point_in_time_valid": not blockers,
        "source_time_status": (
            POINT_IN_TIME_SOURCE_MODE
            if proof_eligible
            else "source_known_before_input_date"
            if symbol_features and source_mode != POINT_IN_TIME_SOURCE_MODE and not any(row.get("source_time_blocker") for row in symbol_features.values())
            else "historical_prior_bar_reconstruction"
        ),
        "historical_prior_bar_reconstruction": source_mode != POINT_IN_TIME_SOURCE_MODE,
        "spy_momentum_confirmed": spy_confirmed,
        "qqq_momentum_confirmed": qqq_confirmed,
        "breadth_confirmed": breadth_confirmed,
        "breadth_ratio": round(breadth_ratio, 6) if breadth_ratio is not None else None,
        "available_symbol_count": available_symbol_count,
        "above_prior_50_sma_symbol_count": above_count,
        "minimum_available_symbol_count": MIN_BREADTH_AVAILABLE_SYMBOLS,
        "breadth_threshold": BREADTH_THRESHOLD,
        "spy_feature": spy,
        "qqq_feature": qqq,
        "symbol_features": [symbol_features[symbol] for symbol in sorted(symbol_features)],
        "missing_symbol_inputs": missing,
        "blockers": sorted(set(blockers)),
        "proof_eligible": proof_eligible,
    }


def _coverage(rows: list[dict[str, Any]], requested_dates: list[str], requested_months: list[str]) -> dict[str, Any]:
    clean_dates = sorted(str(row["input_date_et"]) for row in rows if not row.get("blockers"))
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
    }


def _status(blockers: list[str]) -> str:
    return "blocked_point_in_time_market_regime_inputs" if blockers else "point_in_time_market_regime_inputs_ready"


def build_report(
    *,
    market_data_db_path: Path = DEFAULT_MARKET_DATA_DB,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    underlying_source_rows_path: Path = DEFAULT_UNDERLYING_SOURCE_ROWS,
    underlying_source_import_report_path: Path | None = DEFAULT_UNDERLYING_SOURCE_IMPORT_REPORT,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    universe: str = DEFAULT_UNIVERSE,
    source: str = DEFAULT_SOURCE,
    adjustment_mode: str = DEFAULT_ADJUSTMENT_MODE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or start > end:
        raise ValueError("invalid start/end/as-of date")
    requested_universe = _universe(universe)
    feature_store, feature_meta = _load_json(feature_store_path, required=True)
    requested_dates = _feature_store_dates(feature_store, start=start, end=end)
    requested_months = _months_between(start, end)
    source_history, source_rows_meta = _validate_underlying_source_rows(
        underlying_source_rows_path,
        requested_dates=requested_dates,
        universe=requested_universe,
        import_report_path=underlying_source_import_report_path,
    )
    if source_rows_meta.get("status") == "loaded_ready":
        source_time_mode = POINT_IN_TIME_SOURCE_MODE
        history = source_history
        market_meta = {"path": _rel(market_data_db_path), "status": "not_used_source_rows_preferred", "exists": market_data_db_path.exists()}
    else:
        source_time_mode = HISTORICAL_RECONSTRUCTION_SOURCE_MODE
        history, market_meta = _load_daily_history(
            market_data_db_path,
            symbols=requested_universe,
            as_of=as_of,
            source=source,
            adjustment_mode=adjustment_mode,
        )
    input_rows = [
        _market_regime_row(
            day,
            history,
            requested_universe,
            source_mode=source_time_mode,
            source_rows_path=underlying_source_rows_path if source_time_mode == POINT_IN_TIME_SOURCE_MODE else None,
        )
        for day in requested_dates
    ]
    coverage = _coverage(input_rows, requested_dates, requested_months)
    row_blocker_counts: Counter[str] = Counter()
    for row in input_rows:
        row_blocker_counts.update(str(item) for item in _as_list(row.get("blockers")))

    blockers: list[str] = []
    if feature_meta.get("status") != "loaded":
        blockers.append("missing_trusted_feature_store")
    if not requested_dates:
        blockers.append("missing_requested_market_dates")
    if source_rows_meta.get("status") != "loaded_ready":
        blockers.append("missing_or_invalid_verified_underlying_source_rows")
        blockers.append("market_regime_inputs_using_historical_reconstruction")
    if source_time_mode != POINT_IN_TIME_SOURCE_MODE and market_meta.get("status") != "loaded":
        blockers.append("missing_or_unreadable_market_data_db")
    missing_symbols = [symbol for symbol, items in history.items() if not items]
    missing_key_symbols = [symbol for symbol in missing_symbols if symbol in {"SPY", "QQQ"}]
    if missing_key_symbols:
        blockers.append("missing_key_market_data_daily_history_symbols")
    if row_blocker_counts:
        blockers.append("point_in_time_market_regime_row_validation_failed")
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
        "scope": "read_only_point_in_time_market_regime_input_materializer",
        "research_window": {"start_date": start.isoformat(), "end_date": end.isoformat(), "as_of_date": as_of.isoformat()},
        "requested_universe": list(requested_universe),
        "formula_policy": {
            "spy_momentum_confirmed": "prior SPY 20-trading-day return > 0 and prior SPY close > prior 50-trading-day SMA",
            "qqq_momentum_confirmed": "prior QQQ 20-trading-day return > 0 and prior QQQ close > prior 50-trading-day SMA",
            "breadth_confirmed": "at least 60% of available eligible universe symbols are above prior 50-trading-day SMA and available_symbol_count >= 10",
            "prior_close_rule": "input_date_et joins only to daily_history rows with bar_date < input_date_et",
            "source_time_rule": "verified source_rows rows must have point_in_time_valid=true, proof_eligible=false, source_family match, precomputed prior_20_trading_day_return_pct and prior_50_trading_day_sma from importer-known prior bars, SHA-256 source hashes, prior_bar_date_et < input_date_et, and known_at_utc before the candidate decision. market_data.db is fallback reconstruction only.",
            "missing_symbol_policy": "SPY and QQQ are key symbols. Non-key missing symbols are tolerated only while breadth available_symbol_count remains at least 10.",
            "outcome_tuned": False,
            "realized_pnl_used": False,
            "selected_winners_used": False,
            "option_marks_used": False,
        },
        "point_in_time_market_regime_inputs_available": source_time_mode == POINT_IN_TIME_SOURCE_MODE and not blockers,
        "source_time_policy": {
            "source_time_mode": source_time_mode,
            "point_in_time_source_mode": POINT_IN_TIME_SOURCE_MODE,
            "historical_reconstruction_source_mode": HISTORICAL_RECONSTRUCTION_SOURCE_MODE,
            "source_time_field": "source_rows.known_at_utc when source_rows pass validation; market_data.db:daily_history.fetched_at only for fallback reconstruction",
            "known_at_policy": "known_at_utc must be explicit and before the candidate decision; bar_date is not used as source known-at proof",
            "source_import_report_binding_policy": "when the source import report exists, source_rows_path, source_row_count, and source_file_hash must match it; when it is absent, provenance remains limited to row-level point-in-time validation and SHA-256 hash shape",
            "historical_reconstruction_can_clear_point_in_time_blockers": False,
        },
        "source_inventory": {
            "source_mode": source_time_mode,
            "feature_store": feature_meta,
            "underlying_source_rows": source_rows_meta,
            "market_data_db": market_meta,
            "source_filter": {"source": source, "adjustment_mode": adjustment_mode},
            "missing_symbols": missing_symbols,
            "missing_key_symbols": missing_key_symbols,
            "missing_non_key_symbols": [symbol for symbol in missing_symbols if symbol not in {"SPY", "QQQ"}],
        },
        "coverage": coverage,
        "input_rows": input_rows,
        "row_blocker_counts": dict(sorted(row_blocker_counts.items())),
        "confirmation_counts": {
            "spy_momentum_confirmed": sum(1 for row in input_rows if row.get("spy_momentum_confirmed") is True),
            "qqq_momentum_confirmed": sum(1 for row in input_rows if row.get("qqq_momentum_confirmed") is True),
            "breadth_confirmed": sum(1 for row in input_rows if row.get("breadth_confirmed") is True),
        },
        "blockers": blockers,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] == "point_in_time_market_regime_inputs_ready" and report["blockers"]:
        raise ValueError("market regime inputs cannot be ready while blockers are present")
    for row in _as_list(report.get("input_rows")):
        row_dict = _as_dict(row)
        if row_dict.get("proof_eligible") is True and (
            _as_dict(report.get("source_time_policy")).get("source_time_mode") != POINT_IN_TIME_SOURCE_MODE
            or row_dict.get("blockers")
        ):
            raise ValueError("only clean source_rows market-regime rows can be research-input proof eligible")


def render_markdown(report: dict[str, Any]) -> str:
    coverage = _as_dict(report.get("coverage"))
    lines = [
        "# Regular Options Point-in-Time Market Regime Inputs",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_market_regime_inputs.py`. It is a read-only materializer for SPY momentum, QQQ momentum, and 13-symbol breadth confirmations. It reads local daily close history only, uses prior trading-day rows for candidate dates, and does not run replay, create trades, import quotes, mutate evidence stores, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        f"- Requested dates: `{coverage.get('requested_date_count')}`.",
        f"- Covered dates: `{coverage.get('covered_date_count')}`.",
        f"- Covered months: `{coverage.get('covered_month_count')}` / `{coverage.get('requested_month_count')}`.",
        f"- Date coverage: `{coverage.get('date_coverage_pct')}`.",
        f"- Confirmation counts: `{json.dumps(report.get('confirmation_counts'), sort_keys=True)}`.",
        "",
        "## Formula Policy",
        "",
        "```json",
        json.dumps(report.get("formula_policy"), indent=2, sort_keys=True),
        "```",
        "",
        "## Source Inventory",
        "",
        "```json",
        json.dumps(report.get("source_inventory"), indent=2, sort_keys=True),
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
    parser = argparse.ArgumentParser(description="Build read-only point-in-time market-regime inputs.")
    parser.add_argument("--market-data-db", type=Path, default=DEFAULT_MARKET_DATA_DB)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--underlying-source-rows", type=Path, default=DEFAULT_UNDERLYING_SOURCE_ROWS)
    parser.add_argument("--underlying-source-import-report", type=Path, default=DEFAULT_UNDERLYING_SOURCE_IMPORT_REPORT)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--adjustment-mode", default=DEFAULT_ADJUSTMENT_MODE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        market_data_db_path=args.market_data_db,
        feature_store_path=args.feature_store,
        underlying_source_rows_path=args.underlying_source_rows,
        underlying_source_import_report_path=args.underlying_source_import_report,
        start_date=args.start_date,
        end_date=args.end_date,
        as_of_date=args.as_of_date,
        universe=args.universe,
        source=args.source,
        adjustment_mode=args.adjustment_mode,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
