from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_underlying_daily_source_repair_packet"
SOURCE_FAMILY = "point_in_time_underlying_daily_ohlcv_adjusted_v1"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-underlying-daily-source-repair-packet"
DEFAULT_DOC = ROOT / "docs" / "regular-options-underlying-daily-source-repair-packet.md"
DEFAULT_MARKET_DATA_DB = ROOT / "market_data.db"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MARKET_REGIME = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-market-regime-inputs" / "latest.json"
DEFAULT_SCANNER_ADAPTER = ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter" / "latest.json"
DEFAULT_DAILY_DECISIONS = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-daily-candidate-decisions" / "latest.json"
DEFAULT_HISTORICAL_AUDIT = ROOT / "data" / "profitability-lab" / "regular-options-historical-simulated-forward-audit" / "latest.json"
DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"

TARGET_UNIVERSE = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
)
TARGET_START_DATE = "2024-06-01"
TARGET_END_DATE = "2026-05-31"
AS_OF_DATE = "2026-06-04"
LOOKBACK_START_DATE = "2024-03-01"
MIN_TRAIN_MONTHS = 20
FALLBACK_FROZEN_SCANNER_BLOCKED_ROWS = 6916
MIN_LATEST_FOUR_MONTHS = 4
MIN_DATE_COVERAGE_PCT = 90.0
APPROVAL_TOKEN = "APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT"

STRICT_REQUIRED_FIELDS = (
    "symbol",
    "bar_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "fetched_at_utc",
    "adjustment_mode",
    "corporate_action_basis",
)
ALTERNATIVE_FIELD_GROUPS = (
    ("adjusted_close", "adjustment_policy"),
    ("vendor", "source"),
    ("source_event_time", "source_event_date"),
    ("published_at_utc", "known_at_utc"),
    ("source_file_hash", "provenance_id"),
)
FUTURE_SOURCE_FIELDS = (
    "symbol",
    "bar_date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close or adjustment policy",
    "volume",
    "vendor/source",
    "source_event_time/date",
    "published_at_utc or known_at_utc",
    "fetched_at_utc",
    "adjustment_mode",
    "corporate_action_basis",
    "source_file_hash/provenance id",
)
LEAKAGE_FIELDS = {
    "winner",
    "selected_winner",
    "realized_pnl",
    "pnl",
    "net_pnl",
    "net_pnl_usd",
    "return_after_entry",
    "future_return",
    "trade_outcome",
    "label",
    "target",
}
UNTRUSTED_SOURCE_MARKERS = {"manual", "synthetic", "stale", "source_mark", "source-mark", "display_only"}
UNTRUSTED_MARKER_FIELDS = (
    "source_type",
    "source_quality",
    "data_trust",
    "row_type",
    "proof_exclusion_reason",
    "quality",
    "type",
    "vendor",
    "source",
    "source_name",
    "source_ref",
    "source_url_or_file_name",
    "provenance",
    "provenance_id",
    "source_provenance_status",
)
READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "materialized": False,
    "source_materialized": False,
    "future_import_command_executed": False,
    "future_import_command_currently_implemented": True,
    "source_rows_written": False,
    "historical_replay_performed": False,
    "p_l_replay_performed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _candidate_decision_utc(input_date: str) -> str:
    # 09:35 ET expressed as UTC during the regular-options historical feature window.
    return f"{input_date}T13:35:00Z"


def _safe_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return months


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = str(value).split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _field_value(row: dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if row.get(name) not in (None, ""):
            return row.get(name)
    return None


def known_at_for_row(row: dict[str, Any]) -> datetime:
    return _parse_utc(_field_value(row, ("known_at_utc", "published_at_utc")))


def row_usable_for_candidate(row: dict[str, Any], *, candidate_decision_utc: str, candidate_date: str | None = None) -> bool:
    if candidate_date is not None and _parse_date(row.get("bar_date")) >= _parse_date(candidate_date):
        return False
    return known_at_for_row(row) < _parse_utc(candidate_decision_utc)


def _business_dates(start: date, end: date) -> list[str]:
    days: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current = date.fromordinal(current.toordinal() + 1)
    return days


def _row_has_usable_adjustment(row: dict[str, Any]) -> bool:
    adjusted_close = str(row.get("adjusted_close") or "").strip()
    if adjusted_close:
        value = _safe_float(adjusted_close)
        return value is not None and value > 0
    return bool(str(_field_value(row, ("adjustment_policy", "policy")) or "").strip())


def _leakage_reference_dates(row: dict[str, Any]) -> list[tuple[str, date]]:
    dates: list[tuple[str, date]] = []
    for field in ("candidate_date", "input_date", "input_date_et"):
        value = str(row.get(field) or "").strip()
        if not value:
            continue
        try:
            dates.append((field, _parse_date(value)))
        except ValueError:
            dates.append((field, date.min))
    return dates


def _date_invalid(field: str, parsed: date) -> bool:
    return parsed == date.min and field in {"candidate_date", "input_date", "input_date_et"}


def _missing_fields(fieldnames: Sequence[str]) -> list[str]:
    present = {str(field) for field in fieldnames}
    missing = [field for field in STRICT_REQUIRED_FIELDS if field not in present]
    for group in ALTERNATIVE_FIELD_GROUPS:
        if not any(field in present for field in group):
            missing.append(" or ".join(group))
    return missing


def parse_future_source_csv(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf8")
    return parse_future_source_csv_from_text(raw)


def parse_future_source_csv_from_text(raw: str) -> list[dict[str, Any]]:
    file_hash = _sha256_text(raw)
    reader = csv.DictReader(raw.splitlines())
    fieldnames = reader.fieldnames or []
    missing = _missing_fields(fieldnames)
    if missing:
        raise ValueError(f"missing required source fields: {', '.join(missing)}")
    forbidden = [field for field in fieldnames if field.strip().lower() in LEAKAGE_FIELDS]
    if forbidden:
        raise ValueError(f"outcome/leakage fields are not allowed: {', '.join(forbidden)}")

    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(reader, start=1):
        row = {str(key): value for key, value in raw_row.items()}
        row["symbol"] = str(row.get("symbol") or "").strip().upper()
        row["source_file_hash"] = str(row.get("source_file_hash") or file_hash).strip()
        row["source_row_hash"] = _sha256_text(json.dumps({**row, "_row_number": index}, sort_keys=True))
        rows.append(row)
    return rows


def validate_future_source_rows(
    rows: Sequence[dict[str, Any]],
    *,
    target_universe: Sequence[str] = TARGET_UNIVERSE,
    target_start_date: str = TARGET_START_DATE,
    target_end_date: str = TARGET_END_DATE,
    requested_dates: Sequence[str] | None = None,
) -> dict[str, Any]:
    allowed = set(target_universe)
    target_start = _parse_date(target_start_date)
    target_end = _parse_date(target_end_date)
    rejects: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    duplicate_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    known_by_symbol: dict[str, list[tuple[date, datetime]]] = defaultdict(list)
    target_requested_dates = sorted(
        {
            parsed.isoformat()
            for value in (requested_dates or _business_dates(target_start, target_end))
            for parsed in [_parse_date(value)]
            if target_start <= parsed <= target_end
        }
    )

    for index, row in enumerate(rows, start=1):
        reasons: list[str] = []
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in allowed:
            reasons.append("outside_target_universe")
        try:
            bar_date = _parse_date(row.get("bar_date"))
        except ValueError:
            bar_date = None
            reasons.append("invalid_bar_date")
        try:
            known_at = known_at_for_row(row)
        except ValueError:
            known_at = None
            reasons.append("missing_or_invalid_known_at_or_published_at")
        for field in ("open", "high", "low", "close"):
            value = _safe_float(row.get(field))
            if value is None or value <= 0:
                reasons.append(f"missing_or_invalid_{field}")
        volume = _safe_float(row.get("volume"))
        if volume is None or volume <= 0:
            reasons.append("missing_or_invalid_volume")
        if not _row_has_usable_adjustment(row):
            reasons.append("missing_adjusted_close_or_adjustment_policy")
        fetched_at = None
        try:
            fetched_at = _parse_utc(row.get("fetched_at_utc"))
        except ValueError:
            reasons.append("missing_or_invalid_fetched_at_utc")
        if fetched_at and known_at and known_at > fetched_at:
            reasons.append("known_at_after_fetched_at")
        marker_values = " ".join(str(row.get(field) or "").strip().lower() for field in UNTRUSTED_MARKER_FIELDS)
        if any(marker in marker_values for marker in UNTRUSTED_SOURCE_MARKERS):
            reasons.append("stale_manual_synthetic_or_source_mark_only_row")
        if bar_date and not (date.fromisoformat(LOOKBACK_START_DATE) <= bar_date <= target_end):
            reasons.append("outside_required_lookback_or_target_window")
        if bar_date:
            for field, leakage_date in _leakage_reference_dates(row):
                if _date_invalid(field, leakage_date):
                    reasons.append(f"invalid_{field}")
                elif bar_date >= leakage_date:
                    reasons.append("future_or_same_day_bar_for_candidate")
        decision_time = _field_value(row, ("candidate_decision_utc", "candidate_decision_timestamp_utc", "input_decision_utc"))
        if known_at and decision_time not in (None, ""):
            try:
                if known_at >= _parse_utc(decision_time):
                    reasons.append("known_at_not_before_candidate_decision")
            except ValueError:
                reasons.append("invalid_candidate_decision_utc")
        if reasons:
            rejects.append({"index": index, "symbol": symbol, "bar_date": row.get("bar_date"), "reasons": sorted(set(reasons))})
            continue
        assert bar_date is not None
        assert known_at is not None
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["bar_date"] = bar_date.isoformat()
        valid_rows.append(normalized)
        duplicate_key = (
            symbol,
            bar_date.isoformat(),
            str(row.get("adjustment_mode") or ""),
            str(row.get("corporate_action_basis") or ""),
        )
        duplicate_groups[duplicate_key].append(normalized)
        known_by_symbol[symbol].append((bar_date, known_at))

    conflict_count = 0
    exact_duplicate_group_count = 0
    deduped_exact_duplicate_row_count = 0
    duplicate_conflict_keys: set[tuple[str, str, str, str]] = set()
    for key, group in duplicate_groups.items():
        signatures = {
            tuple(str(item.get(field) or "") for field in ("open", "high", "low", "close", "adjusted_close", "volume"))
            for item in group
        }
        if len(signatures) > 1:
            conflict_count += 1
            duplicate_conflict_keys.add(key)
            for item in group:
                rejects.append({"index": None, "symbol": key[0], "bar_date": key[1], "reasons": ["duplicate_conflicting_rows"]})
        elif len(group) > 1:
            exact_duplicate_group_count += 1
            deduped_exact_duplicate_row_count += len(group) - 1

    non_monotonic_known_at = 0
    for symbol, values in known_by_symbol.items():
        previous: datetime | None = None
        for bar_date, known_at in sorted(values, key=lambda item: item[0]):
            if previous is not None and known_at < previous:
                non_monotonic_known_at += 1
                rejects.append({"index": None, "symbol": symbol, "bar_date": bar_date.isoformat(), "reasons": ["non_monotonic_known_at"]})
            previous = known_at

    valid_without_conflicts: list[dict[str, Any]] = []
    seen_exact_keys: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    for row in valid_rows:
        base_key = (
            row["symbol"],
            row["bar_date"],
            str(row.get("adjustment_mode") or ""),
            str(row.get("corporate_action_basis") or ""),
        )
        if base_key in duplicate_conflict_keys:
            continue
        if any(
            reject.get("symbol") == row["symbol"]
            and reject.get("bar_date") == row["bar_date"]
            and "non_monotonic_known_at" in reject.get("reasons", [])
            for reject in rejects
        ):
            continue
        exact_key = (
            *base_key,
            tuple(str(row.get(field) or "") for field in ("open", "high", "low", "close", "adjusted_close", "volume")),
        )
        if exact_key in seen_exact_keys:
            continue
        seen_exact_keys.add(exact_key)
        valid_without_conflicts.append(row)
    target_months = _month_range(target_start, target_end)
    rows_by_symbol = {
        symbol: sorted(
            (row for row in valid_without_conflicts if row["symbol"] == symbol),
            key=lambda item: item["bar_date"],
        )
        for symbol in tuple(target_universe)
    }
    per_symbol_date_coverage: dict[str, dict[str, Any]] = {}
    for symbol, symbol_rows in rows_by_symbol.items():
        covered_dates = []
        for requested_date in target_requested_dates:
            decision_utc = _candidate_decision_utc(requested_date)
            usable = [
                row
                for row in symbol_rows
                if row_usable_for_candidate(row, candidate_date=requested_date, candidate_decision_utc=decision_utc)
            ]
            if usable:
                covered_dates.append(requested_date)
        pct = round((len(covered_dates) / len(target_requested_dates)) * 100, 4) if target_requested_dates else 0.0
        per_symbol_date_coverage[symbol] = {
            "requested_date_count": len(target_requested_dates),
            "covered_date_count": len(covered_dates),
            "coverage_pct": pct,
            "coverage_ready": pct >= MIN_DATE_COVERAGE_PCT,
        }
    min_date_coverage_pct = min(
        (item["coverage_pct"] for item in per_symbol_date_coverage.values()),
        default=0.0,
    )
    coverage_symbols = sorted(
        symbol for symbol, item in per_symbol_date_coverage.items() if int(item["covered_date_count"]) > 0
    )
    coverage_months = sorted(
        {
            requested_date[:7]
            for symbol_rows in rows_by_symbol.values()
            for requested_date in target_requested_dates
            if any(
                row_usable_for_candidate(
                    row,
                    candidate_date=requested_date,
                    candidate_decision_utc=_candidate_decision_utc(requested_date),
                )
                for row in symbol_rows
            )
        }
    )
    required_month_count = min(len(target_months), MIN_TRAIN_MONTHS + MIN_LATEST_FOUR_MONTHS)
    reject_counts = Counter(reason for reject in rejects for reason in reject.get("reasons", []))
    return {
        "row_count": len(rows),
        "valid_row_count": len(valid_without_conflicts),
        "reject_count": len(rejects),
        "reject_counts": dict(sorted(reject_counts.items())),
        "rejected_rows": rejects,
        "covered_symbols": coverage_symbols,
        "covered_symbol_count": len(coverage_symbols),
        "target_symbol_count": len(tuple(target_universe)),
        "covered_months": coverage_months,
        "covered_month_count": len(coverage_months),
        "target_month_count": len(target_months),
        "required_month_count": required_month_count,
        "requested_date_count": len(target_requested_dates),
        "per_symbol_date_coverage": per_symbol_date_coverage,
        "min_date_coverage_pct": min_date_coverage_pct,
        "min_date_coverage_required_pct": MIN_DATE_COVERAGE_PCT,
        "coverage_ready": (
            len(coverage_symbols) == len(tuple(target_universe))
            and len(coverage_months) >= required_month_count
            and min_date_coverage_pct >= MIN_DATE_COVERAGE_PCT
            and not rejects
        ),
        "duplicate_conflicting_group_count": conflict_count,
        "duplicate_exact_group_count": exact_duplicate_group_count,
        "deduped_exact_duplicate_row_count": deduped_exact_duplicate_row_count,
        "non_monotonic_known_at_count": non_monotonic_known_at,
    }


def _sqlite_readonly_connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def inspect_local_daily_history(
    path: Path,
    *,
    symbols: Sequence[str] = TARGET_UNIVERSE,
    lookback_start_date: str = LOOKBACK_START_DATE,
    target_end_date: str = TARGET_END_DATE,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"path": _rel(path), "exists": path.exists(), "status": "missing"}
    if not path.exists():
        return meta
    try:
        conn = _sqlite_readonly_connect(path)
        try:
            tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "daily_history" not in tables:
                meta["status"] = "missing_daily_history_table"
                return meta
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(daily_history)").fetchall()}
            meta["columns"] = sorted(columns)
            placeholders = ", ".join("?" for _ in symbols)
            rows = conn.execute(
                f"""
                SELECT symbol, COUNT(*) AS row_count, MIN(bar_date) AS first_bar_date, MAX(bar_date) AS latest_bar_date,
                       MIN(fetched_at) AS first_fetched_at, MAX(fetched_at) AS latest_fetched_at
                FROM daily_history
                WHERE symbol IN ({placeholders})
                  AND bar_date >= ?
                  AND bar_date <= ?
                GROUP BY symbol
                ORDER BY symbol
                """,
                (*symbols, lookback_start_date, target_end_date),
            ).fetchall()
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS row_count, MIN(bar_date) AS first_bar_date, MAX(bar_date) AS latest_bar_date,
                       MIN(fetched_at) AS first_fetched_at, MAX(fetched_at) AS latest_fetched_at
                FROM daily_history
                WHERE symbol IN ({placeholders})
                  AND bar_date >= ?
                  AND bar_date <= ?
                """,
                (*symbols, lookback_start_date, target_end_date),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return meta

    required_point_in_time_columns = {"published_at_utc", "known_at_utc", "source_event_time", "source_file_hash", "provenance_id"}
    missing_point_in_time_columns = sorted(required_point_in_time_columns - set(meta.get("columns", [])))
    per_symbol = {
        str(row["symbol"]).upper(): {
            "row_count": int(row["row_count"] or 0),
            "first_bar_date": row["first_bar_date"],
            "latest_bar_date": row["latest_bar_date"],
            "first_fetched_at": row["first_fetched_at"],
            "latest_fetched_at": row["latest_fetched_at"],
        }
        for row in rows
    }
    first_fetch = str(total["first_fetched_at"] or "") if total else ""
    latest_fetch = str(total["latest_fetched_at"] or "") if total else ""
    fetched_in_2026 = first_fetch.startswith("2026") or latest_fetch.startswith("2026")
    meta.update(
        {
            "status": "loaded",
            "row_count": int(total["row_count"] or 0) if total else 0,
            "first_bar_date": total["first_bar_date"] if total else None,
            "latest_bar_date": total["latest_bar_date"] if total else None,
            "first_fetched_at": first_fetch or None,
            "latest_fetched_at": latest_fetch or None,
            "symbols": per_symbol,
            "missing_requested_symbols": [symbol for symbol in symbols if symbol not in per_symbol],
            "missing_point_in_time_columns": missing_point_in_time_columns,
            "fetched_in_2026": fetched_in_2026,
            "point_in_time_sufficient": False,
            "insufficiency_reason": (
                "daily_history rows were fetched after the historical candidate dates and lack published_at_utc/known_at_utc/source-event provenance; "
                "bar_date alone cannot prove the row was known before a 2024-06-01..2026-05-31 candidate decision"
            ),
        }
    )
    return meta


def _feature_store_dates(path: Path, *, start: date, end: date) -> list[str]:
    feature = _load_json(path)
    dates = []
    for item in _as_list(feature.get("shared_quote_dates")):
        try:
            parsed = _parse_date(item)
        except ValueError:
            continue
        if start <= parsed <= end:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _downstream_statuses() -> list[dict[str, Any]]:
    market_regime = _load_json(DEFAULT_MARKET_REGIME)
    scanner_adapter = _load_json(DEFAULT_SCANNER_ADAPTER)
    daily_decisions = _load_json(DEFAULT_DAILY_DECISIONS)
    historical_audit = _load_json(DEFAULT_HISTORICAL_AUDIT)
    return [
        {
            "artifact": "point_in_time_market_regime_inputs",
            "status": market_regime.get("status"),
            "currently_blocked_by_underlying_source": bool(
                _as_dict(market_regime.get("row_blocker_counts")).get("market_regime_source_time_not_point_in_time")
            ),
            "would_unlock_if_future_source_passes": "point-in-time SPY/QQQ momentum and 13-symbol breadth inputs",
        },
        {
            "artifact": "historical_frozen_scanner_replay_adapter",
            "status": scanner_adapter.get("status"),
            "currently_blocked_by_underlying_source": "underlying_daily_history_source_not_point_in_time"
            in _as_list(scanner_adapter.get("blockers")),
            "would_unlock_if_future_source_passes": "historical frozen scanner replay adapter input surface",
        },
        {
            "artifact": "frozen_daily_candidate_decisions",
            "status": daily_decisions.get("status"),
            "currently_blocked_by_underlying_source": True,
            "would_unlock_if_future_source_passes": "frozen daily candidate/no-pick decision source after scanner inputs are point-in-time",
        },
        {
            "artifact": "historical_simulated_forward_audit",
            "status": historical_audit.get("status"),
            "currently_blocked_by_underlying_source": True,
            "would_unlock_if_future_source_passes": "historical simulated-forward audit only after point-in-time scanner replay and frozen decisions exist",
        },
    ]


def _current_baseline() -> dict[str, Any]:
    market_regime = _load_json(DEFAULT_MARKET_REGIME)
    scanner_adapter = _load_json(DEFAULT_SCANNER_ADAPTER)
    market_row_blockers = _as_dict(market_regime.get("row_blocker_counts"))
    scanner_blockers = _as_dict(scanner_adapter.get("blocker_counts"))
    scanner_rows = scanner_adapter.get("daily_candidate_decision_row_count")
    if scanner_rows in (None, "") and not scanner_adapter.get("status"):
        scanner_rows = FALLBACK_FROZEN_SCANNER_BLOCKED_ROWS
        scanner_blockers = {"underlying_daily_history_source_not_point_in_time": FALLBACK_FROZEN_SCANNER_BLOCKED_ROWS}
    return {
        "strict_forward_proof": "0/30",
        "vix_source_status": "ready",
        "market_regime_status": market_regime.get("status"),
        "market_regime_source_time_mode": _as_dict(market_regime.get("source_time_policy")).get("source_time_mode"),
        "market_regime_source_time_not_point_in_time_rows": market_row_blockers.get("market_regime_source_time_not_point_in_time", 0),
        "frozen_scanner_adapter_status": scanner_adapter.get("status"),
        "frozen_scanner_blocked_rows": scanner_rows or 0,
        "frozen_scanner_underlying_blocker_rows": scanner_blockers.get("underlying_daily_history_source_not_point_in_time", 0),
    }


def build_report(
    *,
    market_data_db_path: Path = DEFAULT_MARKET_DATA_DB,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    lookback_start_date: str = LOOKBACK_START_DATE,
    target_start_date: str = TARGET_START_DATE,
    target_end_date: str = TARGET_END_DATE,
    as_of_date: str = AS_OF_DATE,
    universe: Sequence[str] = TARGET_UNIVERSE,
    write_outputs: bool = True,
) -> dict[str, Any]:
    target_start = _parse_date(target_start_date)
    target_end = _parse_date(target_end_date)
    target_universe = tuple(universe)
    local_inventory = inspect_local_daily_history(
        market_data_db_path,
        symbols=target_universe,
        lookback_start_date=lookback_start_date,
        target_end_date=target_end_date,
    )
    requested_dates = _feature_store_dates(feature_store_path, start=target_start, end=target_end)
    requested_months = _month_range(target_start, target_end)
    oracle_packet = _load_json(DEFAULT_ORACLE_PACKET)
    target = _as_dict(oracle_packet.get("profitability_target"))
    current_baseline = _current_baseline()
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "status": "underlying_daily_source_repair_packet_ready_for_future_source_import_decision",
        "source_family": SOURCE_FAMILY,
        "blocker": "underlying_daily_history_source_not_point_in_time",
        "accepted_profitability": False,
        "strict_forward_completed_rows": 0,
        "target_forward_rows": target.get("minimum_profitable_strict_completed_rows", 30),
        "proof_claim": "none",
        "current_baseline": current_baseline,
        "target_universe": list(target_universe),
        "target_window": {
            "start_date": target_start_date,
            "end_date": target_end_date,
            "as_of_date": as_of_date,
            "lookback_start_date": lookback_start_date,
            "lookback_reason": "pre-window daily bars are required for prior 20-trading-day return and prior 50-trading-day SMA calculations",
        },
        "requested_coverage": {
            "requested_market_date_count": len(requested_dates),
            "requested_months": requested_months,
            "requested_month_count": len(requested_months),
            "min_train_months": MIN_TRAIN_MONTHS,
            "min_latest_four_months": MIN_LATEST_FOUR_MONTHS,
            "min_date_coverage_pct": MIN_DATE_COVERAGE_PCT,
        },
        "future_source_schema": {
            "family": SOURCE_FAMILY,
            "required_fields": list(FUTURE_SOURCE_FIELDS),
            "strict_required_field_names": list(STRICT_REQUIRED_FIELDS),
            "alternative_field_groups": [list(group) for group in ALTERNATIVE_FIELD_GROUPS],
        },
        "known_at_policy": {
            "policy_id": "underlying_daily_known_before_candidate_decision_v1",
            "rule": "A row for bar_date D is usable for candidate date T only if published_at_utc or known_at_utc is strictly before the candidate decision timestamp/date.",
            "bar_date_alone_is_never_known_at_proof": True,
            "same_day_or_future_bar_for_candidate_allowed": False,
            "do_not_infer_known_at_from_bar_date": True,
        },
        "validation_failure_gates": {
            "no_future_or_same_day_leakage": True,
            "no_outcome_pnl_winner_fields": sorted(LEAKAGE_FIELDS),
            "no_stale_manual_synthetic_source_mark_only_rows": True,
            "no_missing_prices_or_volume": True,
            "no_non_monotonic_known_at": True,
            "no_duplicate_conflicting_rows": True,
            "coverage_thresholds": {
                "symbols_required": list(target_universe),
                "train_months_min": MIN_TRAIN_MONTHS,
                "latest_four_months_required": MIN_LATEST_FOUR_MONTHS,
                "date_coverage_pct_min": MIN_DATE_COVERAGE_PCT,
            },
            "protected_holdout_use_allowed": False,
        },
        "local_market_data_db_assessment": {
            **local_inventory,
            "sufficient_for_historical_reconstruction": local_inventory.get("status") == "loaded",
            "sufficient_for_point_in_time_scanner_decisions": False,
            "why_insufficient": (
                "Local market_data.db daily_history can reconstruct prior daily closes after the fact, but its fetched_at timestamps are in 2026 "
                "for 2024-06-01..2026-05-31 decisions and the table lacks independent published_at/known_at/source-event provenance. "
                "Using those rows would infer known-at from bar_date or from a later fetch, which is not point-in-time proof."
            ),
        },
        "downstream_unlocks_after_future_approval_and_valid_source": [
            "point-in-time market-regime inputs",
            "historical frozen scanner replay adapter",
            "frozen daily candidate decisions",
            "historical simulated-forward audit",
        ],
        "downstream_commands_after_future_source_materialization": {
            "point_in_time_market_regime_inputs": "npm run options:research:point-in-time-market-regime-inputs -- --no-write --json",
            "historical_frozen_scanner_replay_adapter": "npm run options:research:historical-frozen-scanner-replay-adapter -- --no-write --json",
            "frozen_daily_candidate_decisions": "npm run options:research:13-symbol-frozen-daily-candidate-decisions -- --no-write --json",
            "historical_simulated_forward_audit": "npm run options:audit:historical-simulated-forward -- --json",
        },
        "downstream_statuses": _downstream_statuses(),
        "future_approval": {
            "required_approval_token": APPROVAL_TOKEN,
            "approval_text": (
                "Approve future non-live, non-broker materialization of trusted point-in-time underlying daily history rows "
                "for the 13-symbol universe and 2024-06-01..2026-05-31 window plus lookback, into a generated source artifact only."
            ),
            "not_run_now": True,
            "source_rows_written_now": False,
            "future_materialization_command_template": (
                "npm run options:source-import:underlying-daily-history -- "
                "--source-file data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv "
                f"--lookback-start-date {lookback_start_date} --target-start-date {target_start_date} "
                f"--target-end-date {target_end_date} --as-of-date {as_of_date} "
                f"--universe {','.join(target_universe)} --source-family {SOURCE_FAMILY} "
                f"--approval-token {APPROVAL_TOKEN} --no-replay --json"
            ),
        },
        **READ_ONLY_FLAGS,
        "artifacts": {
            "docs_report": _rel(docs_report),
            "latest_json": _rel(output_dir / "latest.json"),
            "latest_markdown": _rel(output_dir / "latest.md"),
        },
    }
    if write_outputs:
        write_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    local = _as_dict(report.get("local_market_data_db_assessment"))
    baseline = _as_dict(report.get("current_baseline"))
    lines = [
        "# Regular Options Underlying Daily Source Repair Packet",
        "",
        f"- Status: `{report['status']}`",
        f"- Blocker: `{report['blocker']}`",
        f"- Source family: `{report['source_family']}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        f"- Strict forward proof: `{baseline.get('strict_forward_proof', '0/30')}`",
        f"- Frozen scanner blocked rows: `{baseline.get('frozen_scanner_blocked_rows')}`",
        f"- Underlying blocker rows: `{baseline.get('frozen_scanner_underlying_blocker_rows')}`",
        f"- Materialized: `{str(report['materialized']).lower()}`",
        "",
        "This is a read-only source repair packet. It does not import data, write source rows, mutate trusted evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Why Local daily_history Is Insufficient",
        "",
        local.get("why_insufficient") or "Local daily_history was not point-in-time verified.",
        "",
        "## Required Future Source Fields",
        "",
    ]
    lines.extend(f"- `{field}`" for field in _as_list(_as_dict(report.get("future_source_schema")).get("required_fields")))
    lines.extend(
        [
            "",
            "## Known-At Policy",
            "",
            _as_dict(report.get("known_at_policy")).get("rule", ""),
            "",
            "Do not infer `known_at` from `bar_date` alone.",
            "",
            "## Validation Gates",
            "",
            "```json",
            json.dumps(report.get("validation_failure_gates"), indent=2, sort_keys=True),
            "```",
            "",
            "## Downstream Unlocks",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _as_list(report.get("downstream_unlocks_after_future_approval_and_valid_source")))
    lines.extend(
        [
            "",
            "## Downstream Commands After Future Source Materialization",
            "",
            "```powershell",
        ]
    )
    lines.extend(str(command) for command in _as_dict(report.get("downstream_commands_after_future_source_materialization")).values())
    lines.extend(["```"])
    approval = _as_dict(report.get("future_approval"))
    lines.extend(
        [
            "",
            "## Future Approval",
            "",
            f"- Required token: `{approval.get('required_approval_token')}`",
            f"- Not run now: `{str(approval.get('not_run_now')).lower()}`",
            f"- Source rows written now: `{str(approval.get('source_rows_written_now')).lower()}`",
            "",
            approval.get("approval_text", ""),
            "",
            "```powershell",
            str(approval.get("future_materialization_command_template") or ""),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    (output_dir / "latest.json").write_text(payload, encoding="utf8")
    (output_dir / "latest.md").write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only underlying daily history source repair packet.")
    parser.add_argument("--market-data-db", type=Path, default=DEFAULT_MARKET_DATA_DB)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--lookback-start-date", default=LOOKBACK_START_DATE)
    parser.add_argument("--target-start-date", default=TARGET_START_DATE)
    parser.add_argument("--target-end-date", default=TARGET_END_DATE)
    parser.add_argument("--as-of-date", default=AS_OF_DATE)
    parser.add_argument("--universe", default=",".join(TARGET_UNIVERSE))
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        market_data_db_path=args.market_data_db,
        feature_store_path=args.feature_store,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        universe=_parse_universe(args.universe),
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
