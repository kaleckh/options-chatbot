from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from options_execution import position_pnl_snapshot  # noqa: E402
from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _as_dict,
    _as_list,
    _filter_rows,
    _load_json,
    _safe_float,
)
from scripts.evaluate_regular_options_autoresearch import (  # noqa: E402
    block_bootstrap_confidence_for_values,
)
from us_equity_market_calendar import (  # noqa: E402
    is_us_equity_market_day,
    next_market_day,
    previous_market_day,
)


REPORT_ID = "regular_options_filtered_forward_paper_shadow_tracker"
POLICY_ID = "historical_filtered_candidate_v1"
MATCHED_ROW_IDENTITY_SCHEMA = "policy_ticker_scan_date_direction_v2"
DEFAULT_FILTERED_AUDIT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-historical-filtered-simulated-forward-audit"
    / "latest.json"
)
DEFAULT_SOURCE_SCAN_PICKS = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-underlying-daily-history"
    / "source_rows.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow"
)
DEFAULT_CANDIDATES_JSONL = DEFAULT_OUTPUT_DIR / "candidate_rows.jsonl"
DEFAULT_MATCHED_ROWS_LOG = DEFAULT_OUTPUT_DIR / "matched_rows.jsonl"
DEFAULT_DOCS_REPORT = (
    ROOT / "docs" / "regular-options-filtered-forward-paper-shadow-tracker.md"
)
DEFAULT_POLICY_CONTRACT = (
    ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
)
DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-filtered-forward-evidence-bar-v1.json"
)
DEFAULT_SCAN_TASK_HEALTH = (
    ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_strict_forward_scan_task_health_latest.json"
)
DEFAULT_FORWARD_LEDGER_DB = (
    ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
)
HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT = 306
HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT = 24

PROHIBITED_ACTIONS = (
    "do_not_submit_broker_order_from_filtered_forward_tracker",
    "do_not_enable_live_validation_from_filtered_forward_tracker",
    "do_not_enable_auto_track_from_filtered_forward_tracker",
    "do_not_mutate_tracked_positions_from_filtered_forward_tracker",
    "do_not_import_quotes_from_filtered_forward_tracker",
    "do_not_change_scanner_policy_from_filtered_forward_tracker",
    "do_not_lower_proof_bars_from_filtered_forward_tracker",
    "do_not_promote_from_filtered_forward_tracker",
)
TRUSTED_EXECUTABLE_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
    "alpaca_opra_daily_snapshot",
}
TRUSTED_COMPLETION_ENTRY_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
}
TRUSTED_COMPLETION_EXIT_QUOTE_SOURCES = set(TRUSTED_COMPLETION_ENTRY_QUOTE_SOURCES)
CONTRACT_MULTIPLIER = 100
DEFAULT_FEE_PER_CONTRACT_LEG_USD = 0.65
TARGET_EXIT_PCT_OF_DTE = 0.75
COMPLETION_LINEAGE_SCHEMA = "trusted_synchronized_exact_exit_v1"
EXIT_CAPTURE_MINUTE_START_ET = 15 * 60 + 50
EXIT_CAPTURE_MINUTE_END_ET = 16 * 60
ALLOWED_EXIT_CAPTURE_BASES = {
    "trusted_thetadata_intraday_options_history_db_read_only",
    "trusted_live_exit_evidence_jsonl",
}
EASTERN = ZoneInfo("America/New_York")
OCC_CONTRACT_RE = re.compile(r"^([A-Z0-9]{1,6})(\d{6})([CP])(\d{8})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
READY_SCAN_TASK_HEALTH_STATUS = "scan_tasks_ready_for_next_market_window"
ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER = (
    "entry_quote_store_verification_not_established"
)
ENTRY_QUOTE_STORE_BINDING_SCHEMA = "authoritative_forward_scan_event_v1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _canonical_net_pnl_pct(row: dict[str, Any]) -> float | None:
    for field in ("net_pnl_pct_after_fees", "net_pnl_pct", "pnl_pct"):
        value = _safe_float(row.get(field))
        if value is not None:
            return value
    return None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {
            "path": _rel(path),
            "exists": False,
            "status": "missing",
            "row_count": 0,
            "bad_row_count": 0,
        }
    rows: list[dict[str, Any]] = []
    bad = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            bad += 1
    return rows, {
        "path": _rel(path),
        "exists": True,
        "status": "loaded" if bad == 0 else "malformed",
        "row_count": len(rows),
        "bad_row_count": bad,
    }


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _conditions_sha256(conditions: Sequence[Any]) -> str:
    payload = json.dumps(list(conditions), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


def _load_policy_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {
            "path": _rel(path),
            "exists": True,
            "status": "invalid_json",
            "error": str(exc),
        }
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {
        "path": _rel(path),
        "exists": True,
        "status": "loaded",
        "sha256": _file_hash(path),
    }


def _load_optional_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {
            "path": _rel(path),
            "exists": True,
            "status": "invalid_json",
            "error": str(exc),
        }
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {
        "path": _rel(path),
        "exists": True,
        "status": "loaded",
        "sha256": _file_hash(path),
    }


def _stable_tracking_start_at(
    previous_tracker_dir: Path, *, policy_id: str = POLICY_ID
) -> str | None:
    if not previous_tracker_dir.exists():
        return None
    candidates: list[datetime] = []
    for path in sorted(previous_tracker_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("report_id") != REPORT_ID
            or payload.get("tracking_policy_id") != policy_id
        ):
            continue
        if payload.get("status") != "filtered_forward_paper_shadow_tracking_active":
            continue
        value = _norm(
            payload.get("tracking_start_at_utc") or payload.get("generated_at_utc")
        )
        parsed = _parse_utc_timestamp(value)
        if parsed is not None:
            candidates.append(parsed)
    return _utc_iso(min(candidates)) if candidates else None


def _candidate_date(row: dict[str, Any]) -> str:
    return _norm(
        row.get("selection_date")
        or row.get("scan_date")
        or row.get("candidate_generation_date")
        or row.get("entry_date")
        or row.get("logged_at")
    )[:10]


def _candidate_timestamp(row: dict[str, Any]) -> str:
    return _norm(
        row.get("logged_at")
        or row.get("scan_timestamp_utc")
        or row.get("scan_started_at_utc")
        or row.get("generated_at_utc")
        or row.get("entry_quote_timestamp_utc")
        or row.get("quote_timestamp_utc")
        or row.get("quote_time_utc")
    )


def _field_from_row(row: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = row
        ok = True
        for part in field.split("."):
            if not isinstance(value, dict) or part not in value:
                ok = False
                break
            value = value[part]
        if ok and value not in (None, ""):
            return value
    return None


def _source_row_index(
    rows: Sequence[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("point_in_time_valid") is False:
            continue
        symbol = _norm(row.get("symbol")).upper()
        input_date = _norm(row.get("input_date_et") or row.get("bar_date"))[:10]
        if symbol and input_date:
            key = (symbol, input_date)
            if key in indexed:
                indexed[key] = {
                    "symbol": symbol,
                    "input_date_et": input_date,
                    "_duplicate_point_in_time_signal_source_lineage": True,
                }
            else:
                indexed[key] = dict(row)
    return indexed


def _prior_20_return(
    row: dict[str, Any], source_index: dict[tuple[str, str], dict[str, Any]]
) -> tuple[float | None, str]:
    direct = _safe_float(
        _field_from_row(
            row,
            (
                "signal_evidence.prior_20_trading_day_return_pct",
                "prior_20_trading_day_return_pct",
                "ret20",
                "signal_ret20",
            ),
        )
    )
    if direct is not None:
        return direct, "scan_row"
    symbol = _norm(
        row.get("ticker") or row.get("symbol") or row.get("underlying")
    ).upper()
    scan_date = _candidate_date(row)
    source = source_index.get((symbol, scan_date))
    if source:
        if source.get("_duplicate_point_in_time_signal_source_lineage") is True:
            return None, "duplicate_point_in_time_signal_source_lineage"
        parsed = _safe_float(source.get("prior_20_trading_day_return_pct"))
        if parsed is not None:
            return parsed, "point_in_time_underlying_daily_source_rows"
    return None, "missing_prior_20_trading_day_return_pct"


def _scan_row_for_filter(
    row: dict[str, Any], source_index: dict[tuple[str, str], dict[str, Any]]
) -> tuple[dict[str, Any], str | None]:
    ticker = _norm(
        row.get("ticker") or row.get("symbol") or row.get("underlying")
    ).upper()
    scan_date = _candidate_date(row)
    prior_20, prior_source = _prior_20_return(row, source_index)
    if not ticker:
        return dict(row), "missing_ticker"
    if not scan_date:
        return dict(row), "missing_scan_date"
    if prior_20 is None:
        enriched = dict(row)
        enriched["ticker"] = ticker
        enriched["candidate_generation_date"] = scan_date
        return enriched, prior_source
    enriched = dict(row)
    enriched["ticker"] = ticker
    enriched["symbol"] = ticker
    enriched["candidate_generation_date"] = scan_date
    signal = dict(_as_dict(enriched.get("signal_evidence")))
    signal["prior_20_trading_day_return_pct"] = prior_20
    signal.setdefault("prior_20_trading_day_return_source", prior_source)
    if prior_source == "point_in_time_underlying_daily_source_rows":
        source = source_index.get((ticker, scan_date)) or {}
        signal.setdefault(
            "known_at_utc",
            source.get("known_at_utc") or source.get("source_timestamp_utc"),
        )
        signal.setdefault("source_ref", source.get("source_ref"))
        signal.setdefault("source_row_hash", source.get("source_row_hash"))
    enriched["signal_evidence"] = signal
    return enriched, None


def _candidate_direction(row: dict[str, Any]) -> str:
    return _norm_lower(
        row.get("direction")
        or row.get("option_direction")
        or row.get("side")
        or "unknown"
    )


def _candidate_identity_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm(row.get("tracking_policy_id") or row.get("policy_id") or POLICY_ID),
        _norm(row.get("ticker") or row.get("symbol")).upper(),
        _candidate_date(row),
        _candidate_direction(row),
    )


def _candidate_identity(row: dict[str, Any]) -> str:
    parts = [
        _norm(row.get("tracking_policy_id") or row.get("policy_id") or POLICY_ID),
        _norm(row.get("ticker") or row.get("symbol")).upper(),
        _candidate_date(row),
        _candidate_direction(row),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf8")).hexdigest()[:24]


def _candidate_identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    policy_id, ticker, scan_date, direction = _candidate_identity_key(row)
    return {
        "candidate_id": _candidate_identity(row),
        "candidate_identity_schema": MATCHED_ROW_IDENTITY_SCHEMA,
        "candidate_identity_key": {
            "policy_id": policy_id,
            "ticker": ticker,
            "scan_date": scan_date,
            "direction": direction,
        },
        "identity_policy_id": policy_id,
        "identity_ticker": ticker,
        "identity_scan_date": scan_date,
        "identity_direction": direction,
    }


def _sort_key_first_session(row: dict[str, Any], index: int) -> tuple[str, str, int]:
    return (_candidate_date(row), _candidate_timestamp(row), index)


def _first_daily_signal_matches(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    first_by_key: dict[
        tuple[str, str, str, str], tuple[dict[str, Any], tuple[str, str, int]]
    ] = {}
    duplicate_count = 0
    for index, row in enumerate(rows):
        key = _candidate_identity_key(row)
        sort_key = _sort_key_first_session(row, index)
        current = first_by_key.get(key)
        if current is None:
            first_by_key[key] = (dict(row), sort_key)
            continue
        duplicate_count += 1
        if sort_key < current[1]:
            first_by_key[key] = (dict(row), sort_key)
    return [
        item[0] for item in sorted(first_by_key.values(), key=lambda item: item[1])
    ], {
        "duplicate_same_day_signal_matches_suppressed": duplicate_count,
    }


def _matched_log_has_current_identity_schema(rows: Sequence[dict[str, Any]]) -> bool:
    if not rows:
        return True
    return all(
        _norm(row.get("candidate_identity_schema")) == MATCHED_ROW_IDENTITY_SCHEMA
        for row in rows
    )


def _matched_log_duplicate_daily_signal_identities(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched_entry_rows = [
        row
        for row in rows
        if not _declares_completed_forward_row(dict(row))
        and _norm(row.get("record_type") or "matched_entry") == "matched_entry"
    ]
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in matched_entry_rows:
        key_payload = _as_dict(row.get("candidate_identity_key"))
        key = (
            _norm(
                key_payload.get("policy_id")
                or row.get("identity_policy_id")
                or row.get("tracking_policy_id")
                or POLICY_ID
            ),
            _norm(
                key_payload.get("ticker")
                or row.get("identity_ticker")
                or row.get("ticker")
            ).upper(),
            _norm(
                key_payload.get("scan_date")
                or row.get("identity_scan_date")
                or row.get("scan_date")
            )[:10],
            _norm_lower(
                key_payload.get("direction")
                or row.get("identity_direction")
                or row.get("direction")
                or "unknown"
            ),
        )
        if all(key):
            grouped.setdefault(key, []).append(dict(row))
    duplicates: list[dict[str, Any]] = []
    for key, group in sorted(grouped.items()):
        candidate_ids = sorted(
            {
                _norm(row.get("candidate_id"))
                for row in group
                if _norm(row.get("candidate_id"))
            }
        )
        if len(group) > 1 or len(candidate_ids) > 1:
            duplicates.append(
                {
                    "policy_id": key[0],
                    "ticker": key[1],
                    "scan_date": key[2],
                    "direction": key[3],
                    "matched_entry_row_count": len(group),
                    "candidate_ids": candidate_ids,
                }
            )
    return duplicates


def _candidate_month(row: dict[str, Any]) -> str:
    return _norm(row.get("scan_date") or row.get("entry_date") or row.get("exit_date"))[
        :7
    ]


def _ticker_week_cluster(row: dict[str, Any]) -> str:
    raw_date = _norm(row.get("scan_date") or row.get("entry_date"))[:10]
    ticker = _norm(row.get("ticker") or row.get("symbol")).upper() or "UNKNOWN"
    try:
        parsed = datetime.fromisoformat(raw_date).date()
        iso = parsed.isocalendar()
        return f"{ticker}:{iso.year}-W{iso.week:02d}"
    except ValueError:
        return f"{ticker}:unknown-week"


def _policy_exit_date(row: dict[str, Any]) -> str | None:
    raw_scan_date = _candidate_date(row)
    raw_expiry = _norm(
        row.get("expiry") or row.get("expiration") or row.get("resolved_listed_expiry")
    )[:10]
    dte = _safe_float(row.get("dte"))
    try:
        entry = date.fromisoformat(raw_scan_date)
        expiry = date.fromisoformat(raw_expiry)
    except (TypeError, ValueError):
        return None
    if expiry <= entry:
        return None
    if dte is None:
        dte = max((expiry - entry).days, 1)
    if dte <= 0:
        return None
    target_days = max(1, int(round(float(dte) * TARGET_EXIT_PCT_OF_DTE)))
    raw_target = min(expiry, entry + timedelta(days=target_days))
    target = (
        raw_target
        if is_us_equity_market_day(raw_target)
        else next_market_day(raw_target)
    )
    if target > expiry:
        target = previous_market_day(expiry + timedelta(days=1))
    if target <= entry or target > expiry or not is_us_equity_market_day(target):
        return None
    return target.isoformat()


def _declares_completed_forward_row(row: dict[str, Any]) -> bool:
    state = _norm(row.get("tracking_state"))
    realized = _norm(row.get("realized_pnl_status"))
    return state == "forward_paper_shadow_completed" or realized in {
        "realized_pnl_available",
        "closed_realized_pnl",
        "closed_with_realized_pnl",
        "completed_exact_exit",
    }


def _parse_utc_timestamp(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_occ_contract(value: Any) -> dict[str, Any] | None:
    match = OCC_CONTRACT_RE.fullmatch(_norm(value).upper())
    if match is None:
        return None
    root, expiry_token, right, strike_token = match.groups()
    try:
        expiry = datetime.strptime(expiry_token, "%y%m%d").date()
        strike = int(strike_token) / 1000.0
    except (TypeError, ValueError):
        return None
    return {"root": root, "expiry": expiry, "right": right, "strike": strike}


def _canonical_ticker_root(value: Any) -> str:
    return "".join(
        character for character in _norm(value).upper() if character.isalnum()
    )


def _vertical_geometry(
    row: dict[str, Any],
    *,
    reason_prefix: str = "",
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []

    def reject(reason: str) -> None:
        reasons.append(f"{reason_prefix}{reason}")

    long_symbol = _norm(
        row.get("long_contract_symbol") or row.get("contract_symbol")
    ).upper()
    short_symbol = _norm(row.get("short_contract_symbol")).upper()
    long_occ = _parse_occ_contract(long_symbol)
    short_occ = _parse_occ_contract(short_symbol)
    if long_occ is None:
        reject("long_contract_symbol_not_valid_occ")
    if short_occ is None:
        reject("short_contract_symbol_not_valid_occ")
    if long_occ is None or short_occ is None:
        return {}, sorted(set(reasons))
    ticker_root = _canonical_ticker_root(row.get("ticker") or row.get("symbol"))
    if (
        not ticker_root
        or long_occ["root"] != ticker_root
        or short_occ["root"] != ticker_root
    ):
        reject("occ_contract_root_ticker_mismatch")
    if long_occ["expiry"] != short_occ["expiry"]:
        reject("vertical_contract_expiry_mismatch")
    if long_occ["right"] != short_occ["right"]:
        reject("vertical_contract_right_mismatch")
    direction = _candidate_direction(row)
    expected_right = (
        "C"
        if direction.startswith("call")
        else "P"
        if direction.startswith("put")
        else None
    )
    if expected_right is None:
        reject("vertical_direction_missing_or_invalid")
    elif long_occ["right"] != expected_right or short_occ["right"] != expected_right:
        reject("vertical_contract_right_direction_mismatch")
    expiry_text = _norm(
        row.get("expiry") or row.get("expiration") or row.get("resolved_listed_expiry")
    )[:10]
    try:
        declared_expiry = date.fromisoformat(expiry_text)
    except ValueError:
        declared_expiry = None
        reject("vertical_declared_expiry_missing_or_invalid")
    if declared_expiry is not None and (
        long_occ["expiry"] != declared_expiry or short_occ["expiry"] != declared_expiry
    ):
        reject("vertical_occ_expiry_declared_expiry_mismatch")
    long_strike = float(long_occ["strike"])
    short_strike = float(short_occ["strike"])
    width = abs(short_strike - long_strike)
    if width <= 0:
        reject("vertical_width_non_positive")
    if expected_right == "C" and short_strike <= long_strike:
        reject("call_vertical_strike_order_invalid")
    if expected_right == "P" and short_strike >= long_strike:
        reject("put_vertical_strike_order_invalid")
    for field, expected in (
        ("long_strike", long_strike),
        ("short_strike", short_strike),
        ("spread_width", width),
    ):
        declared = _safe_float(row.get(field))
        if declared is not None and abs(declared - expected) > 0.0001:
            reject(f"vertical_{field}_occ_mismatch")
    scan_date_text = _candidate_date(row)
    try:
        scan_date = date.fromisoformat(scan_date_text)
    except ValueError:
        scan_date = None
        reject("vertical_scan_date_missing_or_invalid")
    dte = _safe_float(row.get("dte"))
    if dte is None or int(dte) != dte or dte <= 0:
        reject("vertical_dte_missing_or_invalid")
    elif scan_date is not None and int(dte) != (long_occ["expiry"] - scan_date).days:
        reject("vertical_dte_expiry_mismatch")
    return {
        "long_contract_symbol": long_symbol,
        "short_contract_symbol": short_symbol,
        "expiry": long_occ["expiry"].isoformat(),
        "long_strike": long_strike,
        "short_strike": short_strike,
        "spread_width": width,
        "dte": int(dte) if dte is not None and int(dte) == dte else None,
        "option_right": long_occ["right"],
    }, sorted(set(reasons))


def _scan_task_health_reject_reasons(
    scan_task_health: dict[str, Any],
    scan_task_meta: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if scan_task_meta.get("status") != "loaded":
        reasons.append("scan_task_health_not_loaded")
    if (
        scan_task_health.get("report_id")
        != "regular_options_strict_forward_scan_task_health"
    ):
        reasons.append("scan_task_health_report_id_invalid")
    if scan_task_health.get("status") != READY_SCAN_TASK_HEALTH_STATUS:
        reasons.append("scan_task_health_status_not_ready")
    if _as_list(scan_task_health.get("blockers")):
        reasons.append("scan_task_health_has_blockers")
    if _as_list(scan_task_health.get("config_blockers")):
        reasons.append("scan_task_health_has_config_blockers")
    if _as_list(scan_task_health.get("runtime_blockers")):
        reasons.append("scan_task_health_has_runtime_blockers")
    if _parse_utc_timestamp(scan_task_health.get("generated_at_utc")) is None:
        reasons.append("scan_task_health_generated_at_missing_or_not_timezone_aware")
    if not SHA256_RE.fullmatch(_norm_lower(scan_task_meta.get("sha256"))):
        reasons.append("scan_task_health_artifact_hash_missing_or_invalid")
    return sorted(set(reasons))


def _scan_provenance(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    stored = _as_dict(row.get("scan_provenance"))
    scan_timestamp_raw = stored.get("scan_timestamp_utc") or _candidate_timestamp(row)
    scan_timestamp = _parse_utc_timestamp(scan_timestamp_raw)
    health_generated_raw = stored.get("scan_task_health_generated_at_utc") or row.get(
        "_scan_task_health_generated_at_utc"
    )
    health_generated = _parse_utc_timestamp(health_generated_raw)
    payload = {
        "schema": "proof_grade_scan_provenance_v1",
        "scan_run_id": _norm(
            stored.get("scan_run_id")
            or row.get("scanner_run_id")
            or row.get("scan_run_id")
            or row.get("source_scan_run_id")
        ),
        "scan_timestamp_utc": _utc_iso(scan_timestamp)
        if scan_timestamp is not None
        else _norm(scan_timestamp_raw),
        "scan_host": _norm(stored.get("scan_host") or row.get("scan_host")),
        "scan_commit_sha": _norm_lower(
            stored.get("scan_commit_sha") or row.get("scan_commit_sha")
        ),
        "scan_branch": _norm(stored.get("scan_branch") or row.get("scan_branch")),
        "source_scan_picks_sha256": _norm_lower(
            stored.get("source_scan_picks_sha256")
            or row.get("_source_scan_picks_sha256")
        ),
        "scan_task_health_sha256": _norm_lower(
            stored.get("scan_task_health_sha256") or row.get("_scan_task_health_sha256")
        ),
        "scan_task_health_status": _norm(
            stored.get("scan_task_health_status") or row.get("_scan_task_health_status")
        ),
        "scan_task_health_generated_at_utc": (
            _utc_iso(health_generated)
            if health_generated is not None
            else _norm(health_generated_raw)
        ),
    }
    reasons: list[str] = []
    if payload["schema"] != "proof_grade_scan_provenance_v1":
        reasons.append("scan_provenance_schema_invalid")
    if not payload["scan_run_id"]:
        reasons.append("scan_run_id_missing")
    if scan_timestamp is None:
        reasons.append("scan_timestamp_missing_or_not_timezone_aware")
    else:
        scan_date = _candidate_date(row)
        if (
            not scan_date
            or scan_timestamp.astimezone(EASTERN).date().isoformat() != scan_date
        ):
            reasons.append("scan_timestamp_date_mismatch")
    if not payload["scan_host"]:
        reasons.append("scan_host_missing")
    if not GIT_SHA_RE.fullmatch(payload["scan_commit_sha"]):
        reasons.append("scan_commit_sha_missing_or_invalid")
    if not payload["scan_branch"]:
        reasons.append("scan_branch_missing")
    if not SHA256_RE.fullmatch(payload["source_scan_picks_sha256"]):
        reasons.append("source_scan_picks_hash_missing_or_invalid")
    if not SHA256_RE.fullmatch(payload["scan_task_health_sha256"]):
        reasons.append("scan_task_health_hash_missing_or_invalid")
    if payload["scan_task_health_status"] != READY_SCAN_TASK_HEALTH_STATUS:
        reasons.append("scan_task_health_status_not_ready")
    if health_generated is None:
        reasons.append("scan_task_health_generated_at_missing_or_not_timezone_aware")
    elif scan_timestamp is not None and health_generated < scan_timestamp:
        reasons.append("scan_task_health_predates_scan")
    return payload, sorted(set(reasons))


def _signal_lineage(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    stored = _as_dict(row.get("signal_lineage"))
    signal = _as_dict(row.get("signal_evidence"))
    known_raw = (
        stored.get("known_at_utc") or signal.get("known_at_utc") or row.get("known_at")
    )
    decision_raw = (
        stored.get("decision_timestamp_utc")
        or row.get("decision_timestamp_utc")
        or _candidate_timestamp(row)
    )
    known_at = _parse_utc_timestamp(known_raw)
    decision = _parse_utc_timestamp(decision_raw)
    payload = {
        "schema": "point_in_time_signal_lineage_v1",
        "known_at_utc": _utc_iso(known_at)
        if known_at is not None
        else _norm(known_raw),
        "decision_timestamp_utc": _utc_iso(decision)
        if decision is not None
        else _norm(decision_raw),
        "source_ref": _norm(stored.get("source_ref") or signal.get("source_ref")),
        "source_row_hash": _norm_lower(
            stored.get("source_row_hash") or signal.get("source_row_hash")
        ),
        "prior_20_trading_day_return_source": _norm(
            stored.get("prior_20_trading_day_return_source")
            or signal.get("prior_20_trading_day_return_source")
            or row.get("prior_20_trading_day_return_source")
        ),
        "prior_20_trading_day_return_pct": _safe_float(
            stored.get("prior_20_trading_day_return_pct")
            if stored.get("prior_20_trading_day_return_pct") is not None
            else signal.get("prior_20_trading_day_return_pct")
            if signal.get("prior_20_trading_day_return_pct") is not None
            else row.get("prior_20_trading_day_return_pct")
        ),
    }
    reasons: list[str] = []
    if known_at is None:
        reasons.append("signal_known_at_missing_or_not_timezone_aware")
    if decision is None:
        reasons.append("signal_decision_timestamp_missing_or_not_timezone_aware")
    elif known_at is not None and known_at > decision:
        reasons.append("signal_known_after_candidate_decision")
    if not payload["source_ref"]:
        reasons.append("signal_source_ref_missing")
    if not SHA256_RE.fullmatch(payload["source_row_hash"]):
        reasons.append("signal_source_row_hash_missing_or_invalid")
    if not payload["prior_20_trading_day_return_source"] or payload[
        "prior_20_trading_day_return_source"
    ] in {"scan_row", "missing_prior_20_trading_day_return_pct"}:
        reasons.append("signal_source_lineage_missing_or_ambiguous")
    if payload["prior_20_trading_day_return_pct"] is None:
        reasons.append("signal_prior_20_return_missing")
    return payload, sorted(set(reasons))


def _entry_quote_store_verification_established(
    row: dict[str, Any] | None = None,
    *,
    verifier: _EntryQuoteStoreVerifier | None = None,
) -> bool:
    result = (
        verifier.verify(row)
        if verifier is not None
        else _entry_quote_store_verification(row)
    )
    return bool(result.get("verified"))


def _strict_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    return None


def _exact_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    normalized = parsed.normalize()
    if normalized.as_tuple().exponent < -4:
        return None
    return parsed


def _canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=lambda value: (
            format(value, "f")
            if isinstance(value, Decimal)
            else TypeError(type(value).__name__)
        ),
    ).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _populated_entry_metadata_values(
    row: dict[str, Any], field_names: Sequence[str]
) -> set[str]:
    snapshot = _as_dict(row.get("entry_quote_snapshot"))
    legs = [_as_dict(item) for item in _as_list(snapshot.get("legs"))]
    containers = [row, snapshot, *legs]
    return {
        _norm_lower(container.get(field))
        for container in containers
        for field in field_names
        if _norm(container.get(field))
    }


def _raw_entry_leg_prices(row: dict[str, Any]) -> dict[str, Any]:
    long_leg = _entry_snapshot_leg(row, "long")
    short_leg = _entry_snapshot_leg(row, "short")
    paths = {
        "entry_long_bid": (
            "entry_long_bid",
            "long_bid",
            "spread_liquidity.long_bid",
            "entry_quote_snapshot.long_bid",
        ),
        "entry_long_ask": (
            "entry_long_ask",
            "long_ask",
            "spread_liquidity.long_ask",
            "entry_quote_snapshot.long_ask",
        ),
        "entry_short_bid": (
            "entry_short_bid",
            "short_bid",
            "spread_liquidity.short_bid",
            "entry_quote_snapshot.short_bid",
        ),
        "entry_short_ask": (
            "entry_short_ask",
            "short_ask",
            "spread_liquidity.short_ask",
            "entry_quote_snapshot.short_ask",
        ),
    }
    result = {
        field: _field_from_row(row, candidates) for field, candidates in paths.items()
    }
    if result["entry_long_bid"] is None:
        result["entry_long_bid"] = long_leg.get("bid")
    if result["entry_long_ask"] is None:
        result["entry_long_ask"] = long_leg.get("ask")
    if result["entry_short_bid"] is None:
        result["entry_short_bid"] = short_leg.get("bid")
    if result["entry_short_ask"] is None:
        result["entry_short_ask"] = short_leg.get("ask")
    declared_debit = row.get("net_debit")
    if declared_debit is None:
        declared_debit = row.get("entry_execution_price")
    if declared_debit is None:
        declared_debit = row.get("entry_debit")
    result["entry_debit"] = declared_debit
    return result


def _entry_price_alias_sets(
    row: dict[str, Any],
) -> tuple[dict[str, set[Decimal]], list[str]]:
    long_leg = _entry_snapshot_leg(row, "long")
    short_leg = _entry_snapshot_leg(row, "short")
    specs = {
        "entry_long_bid": (
            (
                "entry_long_bid",
                "long_bid",
                "spread_liquidity.long_bid",
                "entry_quote_snapshot.long_bid",
            ),
            long_leg.get("bid"),
        ),
        "entry_long_ask": (
            (
                "entry_long_ask",
                "long_ask",
                "spread_liquidity.long_ask",
                "entry_quote_snapshot.long_ask",
            ),
            long_leg.get("ask"),
        ),
        "entry_short_bid": (
            (
                "entry_short_bid",
                "short_bid",
                "spread_liquidity.short_bid",
                "entry_quote_snapshot.short_bid",
            ),
            short_leg.get("bid"),
        ),
        "entry_short_ask": (
            (
                "entry_short_ask",
                "short_ask",
                "spread_liquidity.short_ask",
                "entry_quote_snapshot.short_ask",
            ),
            short_leg.get("ask"),
        ),
    }
    aliases: dict[str, set[Decimal]] = {}
    reasons: list[str] = []
    for field, (paths, leg_value) in specs.items():
        raw_values: list[Any] = []
        for path in paths:
            value: Any = row
            found = True
            for part in path.split("."):
                if not isinstance(value, dict) or part not in value:
                    found = False
                    break
                value = value[part]
            if found and value not in (None, ""):
                raw_values.append(value)
        if leg_value not in (None, ""):
            raw_values.append(leg_value)
        parsed = [_exact_decimal(value) for value in raw_values]
        if not parsed or any(value is None for value in parsed):
            reasons.append(f"{field}_aliases_missing_or_invalid")
            aliases[field] = set()
            continue
        aliases[field] = {value for value in parsed if value is not None}
        if len(aliases[field]) != 1:
            reasons.append(f"{field}_aliases_conflict")
    return aliases, reasons


class _EntryQuoteStoreVerifier:
    """One read-only SQLite snapshot and locator cache for one report build."""

    def __init__(self, db_path: Path = DEFAULT_FORWARD_LEDGER_DB) -> None:
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None
        self.initialization_detail: str | None = None
        self.cache: dict[tuple[int, str, str, str, str], dict[str, Any]] = {}

    def __enter__(self) -> _EntryQuoteStoreVerifier:
        if not self.db_path.exists() or not self.db_path.is_file():
            self.initialization_detail = "authoritative_forward_ledger_missing"
            return self
        try:
            uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only = ON")
            self.connection.execute("BEGIN")
        except (OSError, sqlite3.Error) as exc:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            self.initialization_detail = (
                f"authoritative_forward_ledger_read_failed:{type(exc).__name__}"
            )
        return self

    def __exit__(self, *_args: Any) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def verify(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if self.initialization_detail:
            return {
                "schema": ENTRY_QUOTE_STORE_BINDING_SCHEMA,
                "verified": False,
                "reason": ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER,
                "db_path": _rel(self.db_path),
                "detail": self.initialization_detail,
            }
        if not isinstance(row, dict):
            return _entry_quote_store_verification(row, db_path=self.db_path)
        session_id = _strict_positive_int(row.get("source_scan_session_id"))
        key = (
            session_id or 0,
            _norm(row.get("source_scan_event_key")),
            _norm(row.get("source_scan_run_id")),
            _norm(row.get("source_scan_recorded_at_utc")),
            _canonical_payload_sha256(row),
        )
        if key not in self.cache:
            self.cache[key] = _entry_quote_store_verification(
                row,
                db_path=self.db_path,
                connection=self.connection,
            )
        return dict(self.cache[key])


def _entry_quote_store_verification(
    row: dict[str, Any] | None,
    *,
    db_path: Path = DEFAULT_FORWARD_LEDGER_DB,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Content-verify one matched entry against one authoritative scan event."""
    result: dict[str, Any] = {
        "schema": ENTRY_QUOTE_STORE_BINDING_SCHEMA,
        "verified": False,
        "reason": ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER,
        "db_path": _rel(db_path),
    }
    if not isinstance(row, dict):
        result["detail"] = "matched_entry_missing"
        return result
    session_id = _strict_positive_int(row.get("source_scan_session_id"))
    if session_id is None:
        result["detail"] = "source_scan_session_id_missing_or_invalid"
        return result
    event_key = _norm(row.get("source_scan_event_key"))
    run_id = _norm(row.get("source_scan_run_id"))
    recorded_at = _norm(row.get("source_scan_recorded_at_utc"))
    if not event_key or not run_id or _parse_utc_timestamp(recorded_at) is None:
        result["detail"] = "source_scan_locator_incomplete"
        return result
    if not db_path.exists() or not db_path.is_file():
        result["detail"] = "authoritative_forward_ledger_missing"
        return result

    owned_connection: sqlite3.Connection | None = None
    try:
        active_connection = connection
        if active_connection is None:
            uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
            owned_connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            owned_connection.row_factory = sqlite3.Row
            owned_connection.execute("PRAGMA query_only = ON")
            owned_connection.execute("BEGIN")
            active_connection = owned_connection
        matches = active_connection.execute(
            """
            SELECT
                fs.id AS session_id,
                fs.recorded_at_utc AS session_recorded_at_utc,
                fs.source_label AS session_source_label,
                fs.playbook AS session_playbook,
                fs.run_id AS session_run_id,
                fs.run_mode AS session_run_mode,
                fs.evidence_class AS session_evidence_class,
                fs.is_fixture AS session_is_fixture,
                fe.id AS event_id,
                fe.event_key,
                fe.run_id AS event_run_id,
                fe.run_mode AS event_run_mode,
                fe.evidence_class AS event_evidence_class,
                fe.is_fixture AS event_is_fixture,
                fe.payload_json
            FROM forward_sessions fs
            JOIN forward_events fe ON fe.session_id = fs.id
            WHERE fs.id = ?
              AND fe.event_type = 'scan_pick'
              AND fe.event_key = ?
            """,
            (session_id, event_key),
        ).fetchall()
    except (OSError, sqlite3.Error) as exc:
        result["detail"] = (
            f"authoritative_forward_ledger_read_failed:{type(exc).__name__}"
        )
        return result
    finally:
        if owned_connection is not None:
            owned_connection.close()

    if len(matches) != 1:
        result["detail"] = f"authoritative_scan_event_match_count:{len(matches)}"
        return result
    stored = dict(matches[0])
    try:
        event = json.loads(str(stored.pop("payload_json") or "{}"), parse_float=Decimal)
    except json.JSONDecodeError:
        result["detail"] = "authoritative_scan_event_payload_invalid_json"
        return result
    if not isinstance(event, dict):
        result["detail"] = "authoritative_scan_event_payload_not_object"
        return result

    exact_metadata = {
        "session_recorded_at_utc": recorded_at,
        "session_run_id": run_id,
        "event_run_id": run_id,
        "session_source_label": "scheduled_scan",
        "session_run_mode": "scheduled_scan",
        "event_run_mode": "scheduled_scan",
        "session_evidence_class": "live_production",
        "event_evidence_class": "live_production",
    }
    for field, expected in exact_metadata.items():
        if _norm(stored.get(field)) != expected:
            result["detail"] = f"authoritative_scan_event_{field}_mismatch"
            return result
    if bool(stored.get("session_is_fixture")) or bool(stored.get("event_is_fixture")):
        result["detail"] = "authoritative_scan_event_fixture"
        return result
    if _norm(stored.get("session_playbook")) != _norm(row.get("lane_id")):
        result["detail"] = "authoritative_scan_event_session_playbook_mismatch"
        return result
    if _norm(event.get("selection_source")) != "live_chain_exact_contract":
        result["detail"] = "authoritative_scan_event_selection_source_invalid"
        return result
    if _norm(event.get("entry_execution_basis")) != "spread_ask_bid":
        result["detail"] = "authoritative_scan_event_entry_basis_invalid"
        return result
    event_sources = _populated_entry_metadata_values(
        event,
        (
            "entry_quote_source",
            "quote_source",
            "options_data_source",
            "data_source",
            "market_data_source",
            "options_market_data_source",
        ),
    )
    row_sources = _populated_entry_metadata_values(
        row,
        (
            "entry_quote_source",
            "quote_source",
            "options_data_source",
            "data_source",
            "market_data_source",
            "options_market_data_source",
        ),
    )
    if event_sources != {"alpaca_opra"}:
        result["detail"] = "authoritative_scan_event_quote_source_invalid"
        return result
    if row_sources != event_sources:
        result["detail"] = "matched_entry_quote_source_mismatch"
        return result
    event_source_feeds = _populated_entry_metadata_values(event, ("source_feed",))
    row_source_feeds = _populated_entry_metadata_values(row, ("source_feed",))
    if event_source_feeds - {"opra"} or row_source_feeds != event_source_feeds:
        result["detail"] = "authoritative_scan_event_source_feed_invalid"
        return result
    freshness_values = _populated_entry_metadata_values(
        event,
        (
            "quote_freshness_status",
            "freshness_status",
            "options_snapshot_status",
            "option_chain_status",
        ),
    )
    if not freshness_values or freshness_values != {"fresh"}:
        result["detail"] = "authoritative_scan_event_quote_freshness_invalid"
        return result
    row_freshness_values = _populated_entry_metadata_values(
        row,
        (
            "quote_freshness_status",
            "freshness_status",
            "options_snapshot_status",
            "option_chain_status",
        ),
    )
    if row_freshness_values != freshness_values:
        result["detail"] = "matched_entry_quote_freshness_mismatch"
        return result
    snapshot_kinds = _populated_entry_metadata_values(
        event, ("snapshot_kind", "quote_snapshot_kind")
    )
    if snapshot_kinds & {"daily", "eod", "end_of_day", "daily_snapshot"}:
        result["detail"] = "authoritative_scan_event_snapshot_kind_invalid"
        return result

    event_legs = [
        _as_dict(item)
        for item in _as_list(_as_dict(event.get("entry_quote_snapshot")).get("legs"))
    ]
    if len(event_legs) != 2 or sorted(
        _norm_lower(leg.get("role")) for leg in event_legs
    ) != ["long", "short"]:
        result["detail"] = "authoritative_scan_event_leg_roles_not_exact"
        return result
    event_provenance, event_reasons = _entry_provenance(event)
    row_provenance, row_reasons = _entry_provenance(row)
    if event_reasons:
        result["detail"] = f"authoritative_scan_event_entry_invalid:{event_reasons[0]}"
        return result
    if row_reasons:
        result["detail"] = f"matched_entry_invalid:{row_reasons[0]}"
        return result
    event_price_aliases, event_price_alias_reasons = _entry_price_alias_sets(event)
    row_price_aliases, row_price_alias_reasons = _entry_price_alias_sets(row)
    if event_price_alias_reasons:
        result["detail"] = f"authoritative_scan_event_{event_price_alias_reasons[0]}"
        return result
    if row_price_alias_reasons:
        result["detail"] = f"matched_entry_{row_price_alias_reasons[0]}"
        return result
    if _norm_lower(event_provenance.get("entry_quote_source")) != _norm_lower(
        row_provenance.get("entry_quote_source")
    ):
        result["detail"] = "authoritative_scan_event_entry_quote_source_mismatch"
        return result

    text_pairs = (
        (
            _norm(event.get("ticker")).upper(),
            _norm(row.get("ticker")).upper(),
            "ticker",
        ),
        (_candidate_direction(event), _candidate_direction(row), "direction"),
        (
            _norm(event.get("strategy_type")),
            _norm(row.get("strategy_type")),
            "strategy_type",
        ),
        (_norm(event.get("playbook_id")), _norm(row.get("lane_id")), "lane_id"),
        (
            _norm(event_provenance.get("expiry")),
            _norm(row_provenance.get("expiry")),
            "expiry",
        ),
        (
            _norm(event_provenance.get("long_contract_symbol")),
            _norm(row_provenance.get("long_contract_symbol")),
            "long_contract_symbol",
        ),
        (
            _norm(event_provenance.get("short_contract_symbol")),
            _norm(row_provenance.get("short_contract_symbol")),
            "short_contract_symbol",
        ),
        (
            _norm(event_provenance.get("entry_quote_timestamp_utc")),
            _norm(row_provenance.get("entry_quote_timestamp_utc")),
            "entry_quote_timestamp_utc",
        ),
        (
            _norm(event_provenance.get("long_entry_quote_timestamp_utc")),
            _norm(row_provenance.get("long_entry_quote_timestamp_utc")),
            "long_entry_quote_timestamp_utc",
        ),
        (
            _norm(event_provenance.get("short_entry_quote_timestamp_utc")),
            _norm(row_provenance.get("short_entry_quote_timestamp_utc")),
            "short_entry_quote_timestamp_utc",
        ),
    )
    for left, right, field in text_pairs:
        if not left or left != right:
            result["detail"] = f"authoritative_scan_event_{field}_mismatch"
            return result
    for field in (
        "entry_long_bid",
        "entry_long_ask",
        "entry_short_bid",
        "entry_short_ask",
    ):
        if event_price_aliases.get(field) != row_price_aliases.get(field):
            result["detail"] = f"authoritative_scan_event_{field}_mismatch"
            return result
    event_debit = _exact_decimal(_raw_entry_leg_prices(event).get("entry_debit"))
    row_debit = _exact_decimal(_raw_entry_leg_prices(row).get("entry_debit"))
    if event_debit is None or row_debit is None or event_debit != row_debit:
        result["detail"] = "authoritative_scan_event_entry_debit_mismatch"
        return result

    result.update(
        {
            "verified": True,
            "reason": None,
            "detail": "exact_authoritative_scan_event_match",
            "session_id": session_id,
            "event_id": int(stored["event_id"]),
            "event_key": event_key,
            "run_id": run_id,
            "recorded_at_utc": recorded_at,
            "canonical_payload_sha256": _canonical_payload_sha256(event),
        }
    )
    return result


def _completion_lineage_reject_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    candidate_id = _norm(row.get("candidate_id"))
    if not candidate_id:
        reasons.append("completion_candidate_id_missing")
    if _norm(row.get("tracking_state")) != "forward_paper_shadow_completed":
        reasons.append("completion_tracking_state_not_exact")
    if _norm(row.get("realized_pnl_status")) != "completed_exact_exit":
        reasons.append("completion_realized_pnl_status_not_exact")
    if _norm(row.get("record_type")) != "completion":
        reasons.append("completion_record_type_not_exact")
    if _norm(row.get("lifecycle_event")) != "completed_exact_exit":
        reasons.append("completion_lifecycle_event_not_exact")
    if _norm(row.get("completion_lineage_schema")) != COMPLETION_LINEAGE_SCHEMA:
        reasons.append("completion_lineage_schema_missing_or_invalid")
    if _norm(row.get("source_entry_candidate_id")) != candidate_id:
        reasons.append("completion_source_entry_candidate_id_mismatch")
    if _norm(row.get("source_entry_record_type")) != "matched_entry":
        reasons.append("completion_source_entry_record_type_not_exact")
    if _norm(row.get("source_entry_lifecycle_event")) != "matched_entry":
        reasons.append("completion_source_entry_lifecycle_event_not_exact")
    geometry, geometry_reasons = _vertical_geometry(row, reason_prefix="completion_")
    reasons.extend(geometry_reasons)
    _scan, scan_reasons = _scan_provenance(row)
    reasons.extend(f"completion_{reason}" for reason in scan_reasons)
    _signal, signal_reasons = _signal_lineage(row)
    reasons.extend(f"completion_{reason}" for reason in signal_reasons)
    expected_policy_exit = _policy_exit_date(row)
    declared_policy_exit = _norm(row.get("policy_exit_date"))[:10]
    declared_exit = _norm(row.get("exit_date"))[:10]
    try:
        entry_day = date.fromisoformat(_candidate_date(row))
        expiry_day = date.fromisoformat(_norm(row.get("expiry"))[:10])
        exit_day = date.fromisoformat(declared_exit)
    except ValueError:
        entry_day = expiry_day = exit_day = None
        reasons.append("completion_entry_expiry_or_exit_date_missing_or_invalid")
    if expected_policy_exit is None:
        reasons.append("completion_policy_exit_date_not_computable")
    elif declared_policy_exit != expected_policy_exit:
        reasons.append("completion_policy_exit_date_mismatch")
    if expected_policy_exit is not None and declared_exit != expected_policy_exit:
        reasons.append("completion_exit_date_not_policy_exit_date")
    if _norm(row.get("exit_reason")) != "fixed_75pct_dte_time_exit":
        reasons.append("completion_exit_reason_not_policy_exact")
    if entry_day is not None and expiry_day is not None and exit_day is not None:
        if exit_day <= entry_day:
            reasons.append("completion_exit_not_after_entry")
        if exit_day > expiry_day:
            reasons.append("completion_exit_after_expiry")
        if not is_us_equity_market_day(exit_day):
            reasons.append("completion_exit_date_not_authoritative_market_day")

    entry_source = _norm_lower(row.get("entry_quote_source"))
    if entry_source not in TRUSTED_COMPLETION_ENTRY_QUOTE_SOURCES:
        reasons.append("completion_entry_quote_source_untrusted")
    entry_timestamp = _parse_utc_timestamp(row.get("entry_quote_timestamp_utc"))
    long_entry_timestamp = _parse_utc_timestamp(
        row.get("long_entry_quote_timestamp_utc")
    )
    short_entry_timestamp = _parse_utc_timestamp(
        row.get("short_entry_quote_timestamp_utc")
    )
    if entry_timestamp is None:
        reasons.append("completion_entry_timestamp_missing_or_invalid")
    if long_entry_timestamp is None:
        reasons.append("completion_long_entry_timestamp_missing_or_invalid")
    if short_entry_timestamp is None:
        reasons.append("completion_short_entry_timestamp_missing_or_invalid")
    if (
        entry_timestamp is not None
        and long_entry_timestamp is not None
        and short_entry_timestamp is not None
    ):
        if (
            entry_timestamp != long_entry_timestamp
            or entry_timestamp != short_entry_timestamp
        ):
            reasons.append("completion_entry_quote_timestamps_not_exactly_synchronized")
        long_entry_et = long_entry_timestamp.astimezone(EASTERN)
        short_entry_et = short_entry_timestamp.astimezone(EASTERN)
        candidate_date = _candidate_date(row)
        if candidate_date and (
            candidate_date != long_entry_et.date().isoformat()
            or candidate_date != short_entry_et.date().isoformat()
        ):
            reasons.append("completion_entry_date_timestamp_mismatch")

    entry_long_ask = _safe_float(row.get("entry_long_ask"))
    entry_long_bid = _safe_float(row.get("entry_long_bid"))
    entry_short_bid = _safe_float(row.get("entry_short_bid"))
    entry_short_ask = _safe_float(row.get("entry_short_ask"))
    entry_debit = _safe_float(row.get("entry_debit"))
    if entry_long_ask is None or entry_long_ask <= 0:
        reasons.append("completion_entry_long_ask_missing_or_invalid")
    if entry_short_bid is None or entry_short_bid < 0:
        reasons.append("completion_entry_short_bid_missing_or_invalid")
    if entry_long_bid is None or entry_long_bid < 0:
        reasons.append("completion_entry_long_bid_missing_or_invalid")
    if entry_short_ask is None or entry_short_ask < 0:
        reasons.append("completion_entry_short_ask_missing_or_invalid")
    if (
        entry_long_bid is not None
        and entry_long_ask is not None
        and entry_long_ask < entry_long_bid
    ):
        reasons.append("completion_entry_long_quote_crossed")
    if (
        entry_short_bid is not None
        and entry_short_ask is not None
        and entry_short_ask < entry_short_bid
    ):
        reasons.append("completion_entry_short_quote_crossed")
    if entry_long_ask is not None and entry_short_bid is not None:
        expected_entry_debit = entry_long_ask - entry_short_bid
        if expected_entry_debit <= 0:
            reasons.append("completion_entry_debit_non_positive")
        elif entry_debit is None or abs(entry_debit - expected_entry_debit) > 0.0001:
            reasons.append("completion_entry_debit_not_derived_from_executable_sides")
        elif (
            _safe_float(geometry.get("spread_width")) is not None
            and entry_debit > float(geometry["spread_width"]) + 0.0001
        ):
            reasons.append("completion_entry_debit_exceeds_vertical_width")
    if _norm(row.get("entry_debit_basis")) != "long_ask_minus_short_bid":
        reasons.append("completion_entry_debit_basis_not_exact")

    source = _norm_lower(row.get("exit_quote_source"))
    if source not in TRUSTED_COMPLETION_EXIT_QUOTE_SOURCES:
        reasons.append("completion_exit_quote_source_untrusted")
    if _norm(row.get("exit_capture_basis")) not in ALLOWED_EXIT_CAPTURE_BASES:
        reasons.append("completion_exit_capture_basis_untrusted")
    if not _norm(row.get("long_contract_symbol")):
        reasons.append("completion_long_contract_symbol_missing")
    if not _norm(row.get("short_contract_symbol")):
        reasons.append("completion_short_contract_symbol_missing")
    lineage = _as_dict(row.get("exit_price_lineage"))
    if _norm(lineage.get("schema")) != COMPLETION_LINEAGE_SCHEMA:
        reasons.append("completion_exit_price_lineage_schema_missing_or_invalid")
    if _norm(lineage.get("long_contract_symbol")) != _norm(
        row.get("long_contract_symbol")
    ):
        reasons.append("completion_exit_lineage_long_contract_mismatch")
    if _norm(lineage.get("short_contract_symbol")) != _norm(
        row.get("short_contract_symbol")
    ):
        reasons.append("completion_exit_lineage_short_contract_mismatch")

    exit_timestamp = _parse_utc_timestamp(row.get("exit_quote_timestamp_utc"))
    long_timestamp = _parse_utc_timestamp(row.get("long_exit_quote_timestamp_utc"))
    short_timestamp = _parse_utc_timestamp(row.get("short_exit_quote_timestamp_utc"))
    if exit_timestamp is None:
        reasons.append("completion_exit_timestamp_missing_or_invalid")
    if long_timestamp is None:
        reasons.append("completion_long_exit_timestamp_missing_or_invalid")
    if short_timestamp is None:
        reasons.append("completion_short_exit_timestamp_missing_or_invalid")
    if (
        exit_timestamp is not None
        and long_timestamp is not None
        and short_timestamp is not None
    ):
        if exit_timestamp != long_timestamp or exit_timestamp != short_timestamp:
            reasons.append("completion_exit_quote_timestamps_not_exactly_synchronized")
        long_et = long_timestamp.astimezone(EASTERN)
        short_et = short_timestamp.astimezone(EASTERN)
        long_minute = long_et.hour * 60 + long_et.minute
        short_minute = short_et.hour * 60 + short_et.minute
        if (
            not EXIT_CAPTURE_MINUTE_START_ET
            <= long_minute
            <= EXIT_CAPTURE_MINUTE_END_ET
        ):
            reasons.append("completion_exit_quote_outside_capture_window")
        try:
            declared_long_minute = int(row.get("long_exit_quote_minute_et"))
            declared_short_minute = int(row.get("short_exit_quote_minute_et"))
        except (TypeError, ValueError):
            reasons.append("completion_exit_quote_minutes_missing_or_invalid")
        else:
            if (
                declared_long_minute != long_minute
                or declared_short_minute != short_minute
            ):
                reasons.append("completion_exit_quote_minute_lineage_mismatch")
        exit_date = _norm(row.get("exit_date"))[:10]
        if (
            exit_date != long_et.date().isoformat()
            or exit_date != short_et.date().isoformat()
        ):
            reasons.append("completion_exit_date_timestamp_mismatch")

    long_bid = _safe_float(row.get("long_exit_bid"))
    long_ask = _safe_float(row.get("long_exit_ask"))
    short_bid = _safe_float(row.get("short_exit_bid"))
    short_ask = _safe_float(row.get("short_exit_ask"))
    exit_value = _safe_float(row.get("exit_value"))
    if long_bid is None or long_bid < 0:
        reasons.append("completion_long_exit_bid_missing_or_invalid")
    if short_ask is None or short_ask < 0:
        reasons.append("completion_short_exit_ask_missing_or_invalid")
    if long_ask is not None and long_bid is not None and long_ask < long_bid:
        reasons.append("completion_long_exit_quote_crossed")
    if short_bid is not None and short_ask is not None and short_ask < short_bid:
        reasons.append("completion_short_exit_quote_crossed")
    if long_bid is not None and short_ask is not None:
        expected_exit_value = max(0.0, long_bid - short_ask)
        if exit_value is None or abs(exit_value - expected_exit_value) > 0.0001:
            reasons.append("completion_exit_value_not_derived_from_executable_sides")
        width = _safe_float(geometry.get("spread_width"))
        if width is not None and expected_exit_value > width + 0.0001:
            reasons.append("completion_exit_value_exceeds_vertical_width")
    net_pnl_pct = _safe_float(row.get("net_pnl_pct_after_fees"))
    net_pnl_usd = _safe_float(row.get("net_pnl_usd"))
    if net_pnl_pct is None:
        reasons.append("completion_fee_adjusted_pnl_pct_missing")
    if net_pnl_usd is None:
        reasons.append("completion_net_pnl_usd_missing")
    fee_per_leg = _safe_float(row.get("fee_per_contract_leg_usd"))
    if fee_per_leg is None or fee_per_leg < 0:
        reasons.append("completion_fee_per_contract_leg_missing_or_invalid")
    try:
        contract_multiplier = int(row.get("contract_multiplier"))
    except (TypeError, ValueError):
        contract_multiplier = -1
        reasons.append("completion_contract_multiplier_missing_or_invalid")
    if contract_multiplier != CONTRACT_MULTIPLIER:
        reasons.append("completion_contract_multiplier_not_exact")
    if (
        entry_debit is not None
        and entry_debit > 0
        and exit_value is not None
        and fee_per_leg is not None
        and fee_per_leg >= 0
        and contract_multiplier == CONTRACT_MULTIPLIER
    ):
        expected_pnl = position_pnl_snapshot(
            entry_execution_price=entry_debit,
            exit_execution_price=exit_value,
            contracts=1,
            entry_fee_total_usd=2.0 * fee_per_leg,
            exit_fee_total_usd=2.0 * fee_per_leg,
            contract_multiplier=contract_multiplier,
        )
        expected_net_pct = _safe_float(expected_pnl.get("net_pnl_pct"))
        expected_net_usd = _safe_float(expected_pnl.get("net_pnl_usd"))
        expected_fees = _safe_float(expected_pnl.get("fee_total_usd"))
        if (
            expected_net_pct is None
            or net_pnl_pct is None
            or abs(net_pnl_pct - expected_net_pct) > 0.0001
        ):
            reasons.append("completion_fee_adjusted_pnl_pct_not_recomputed")
        if (
            expected_net_usd is None
            or net_pnl_usd is None
            or abs(net_pnl_usd - expected_net_usd) > 0.0001
        ):
            reasons.append("completion_net_pnl_usd_not_recomputed")
        recorded_fees = _safe_float(row.get("total_fees_usd"))
        if (
            expected_fees is None
            or recorded_fees is None
            or abs(recorded_fees - expected_fees) > 0.0001
        ):
            reasons.append("completion_total_fees_not_recomputed")
    return sorted(set(reasons))


def _is_completed_forward_row(row: dict[str, Any]) -> bool:
    return _declares_completed_forward_row(
        row
    ) and not _completion_lineage_reject_reasons(row)


def _is_fixture_row(row: dict[str, Any]) -> bool:
    source = _as_dict(row.get("source_row"))
    text_values = [
        row.get("source_report"),
        row.get("evidence_bucket"),
        row.get("row_source"),
        source.get("source_report"),
        source.get("row_source"),
        source.get("data_source"),
    ]
    if row.get("is_fixture") is True or source.get("is_fixture") is True:
        return True
    return any("fixture" in _norm(value).lower() for value in text_values)


def _scheduled_session_times(scan_task_health: dict[str, Any]) -> dict[str, Any]:
    expected = _as_dict(scan_task_health.get("expected"))
    tasks = _as_dict(expected.get("tasks"))
    if tasks:
        return {
            str(name): _as_dict(task).get("start_time")
            for name, task in sorted(tasks.items())
            if _as_dict(task).get("start_time")
        }
    task_reports = _as_dict(scan_task_health.get("task_reports"))
    result: dict[str, Any] = {}
    for name, report in sorted(task_reports.items()):
        fields = _as_dict(_as_dict(report).get("runtime_telemetry")).get("fields")
        start_time = _as_dict(fields).get("configured_expected_start_time")
        if start_time:
            result[str(name)] = start_time
    return result


def _forward_evidence_bar_progress(
    rows: Sequence[dict[str, Any]],
    *,
    bar_contract: dict[str, Any],
    bar_meta: dict[str, Any],
    verifier: _EntryQuoteStoreVerifier | None = None,
) -> dict[str, Any]:
    requirements = _as_dict(bar_contract.get("requirements"))
    min_rows = int(requirements.get("min_completed_forward_paper_shadow_rows") or 30)
    min_clusters = int(requirements.get("min_ticker_week_clusters") or 8)
    min_months = int(requirements.get("min_calendar_months_with_rows") or 3)
    min_pct_lb = float(requirements.get("min_percent_cluster_pf_lb_5pct") or 1.0)
    min_usd_lb = float(requirements.get("min_usd_cluster_pf_lb_5pct") or 1.0)
    min_total_usd = float(requirements.get("min_total_net_pnl_usd_exclusive") or 0.0)
    max_fixture_rows = int(requirements.get("max_fixture_rows") or 0)
    draws = int(requirements.get("bootstrap_draws") or 10000)
    completed_rows, declared_rows, lineage_reject_counts = _validated_completion_rows(
        rows, verifier=verifier
    )
    declared_completed = [dict(row) for row in declared_rows]
    completed = [dict(row) for row in completed_rows]
    declared_candidate_ids = {
        _norm(row.get("candidate_id"))
        for row in declared_completed
        if _norm(row.get("candidate_id"))
    }
    completed_candidate_ids = {
        _norm(row.get("candidate_id"))
        for row in completed
        if _norm(row.get("candidate_id"))
    }
    unresolved_candidate_ids = sorted(declared_candidate_ids - completed_candidate_ids)
    duplicate_valid_completion_event_count = int(
        lineage_reject_counts.get("duplicate_valid_completion_event") or 0
    )
    clusters = sorted({_ticker_week_cluster(row) for row in completed})
    months = sorted(
        {_candidate_month(row) for row in completed if _candidate_month(row)}
    )
    fixture_count = sum(1 for row in completed if _is_fixture_row(row))
    pct_entries: list[tuple[str, float]] = []
    usd_entries: list[tuple[str, float]] = []
    for row in completed:
        cluster = _ticker_week_cluster(row)
        pct = _canonical_net_pnl_pct(row)
        usd = _safe_float(row.get("net_pnl_usd"))
        if pct is not None:
            pct_entries.append((cluster, pct))
        if usd is not None:
            usd_entries.append((cluster, usd))

    entry_quote_store_verification_established = bool(
        completed
        and not lineage_reject_counts.get(ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER)
    )
    evaluation_permitted = bool(
        entry_quote_store_verification_established and len(completed) >= min_rows
    )
    percent_bootstrap = None
    usd_bootstrap = None
    if evaluation_permitted:
        percent_bootstrap = block_bootstrap_confidence_for_values(
            pct_entries,
            branch_id=f"{REPORT_ID}:forward_evidence_bar:percent",
            draws=max(draws, 1),
        )
        usd_bootstrap = block_bootstrap_confidence_for_values(
            usd_entries,
            branch_id=f"{REPORT_ID}:forward_evidence_bar:usd",
            draws=max(draws, 1),
        )

    total_net_pnl_usd = (
        round(sum(value for _cluster, value in usd_entries), 4) if usd_entries else None
    )
    checks = {
        "completed_rows": len(completed) >= min_rows,
        "ticker_week_clusters": len(clusters) >= min_clusters,
        "calendar_months_with_rows": len(months) >= min_months,
        "fixture_rows": fixture_count <= max_fixture_rows,
        "percent_metric_complete": len(pct_entries) == len(completed),
        "usd_metric_complete": len(usd_entries) == len(completed),
        "percent_cluster_pf_lb": bool(
            evaluation_permitted
            and percent_bootstrap
            and _safe_float(percent_bootstrap.get("pf_lb_5pct")) is not None
            and float(percent_bootstrap.get("pf_lb_5pct")) > min_pct_lb
        ),
        "usd_cluster_pf_lb": bool(
            evaluation_permitted
            and usd_bootstrap
            and _safe_float(usd_bootstrap.get("pf_lb_5pct")) is not None
            and float(usd_bootstrap.get("pf_lb_5pct")) > min_usd_lb
        ),
        "total_net_pnl_usd": bool(
            total_net_pnl_usd is not None and total_net_pnl_usd > min_total_usd
        ),
        "trusted_synchronized_exit_price_lineage": not unresolved_candidate_ids,
        "unique_valid_completion_events": duplicate_valid_completion_event_count == 0,
        "entry_quote_store_verification": entry_quote_store_verification_established,
    }
    criteria_met = bool(evaluation_permitted and all(checks.values()))
    if bar_meta.get("status") != "loaded":
        status = "forward_evidence_bar_contract_missing"
    elif not entry_quote_store_verification_established:
        status = ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER
    elif not evaluation_permitted:
        status = "waiting_for_min_completed_forward_rows"
    elif criteria_met:
        status = "forward_evidence_bar_criteria_met_reporting_only"
    else:
        status = "forward_evidence_bar_criteria_not_met"
    return {
        "status": status,
        "bar_contract": bar_meta,
        "bar_id": bar_contract.get("bar_id"),
        "approval_authority": False,
        "accepted_profitability": False,
        "can_change_scanner_policy": False,
        "evaluation_permitted": evaluation_permitted,
        "entry_quote_store_verification_established": (
            entry_quote_store_verification_established
        ),
        "proof_blockers": (
            []
            if entry_quote_store_verification_established
            else [ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER]
        ),
        "evaluation_waits_for_min_completed_rows": bool(
            requirements.get("evaluation_may_not_occur_before_min_completed_rows", True)
        ),
        "completed_forward_rows": len(completed),
        "declared_completed_forward_rows": len(declared_completed),
        "declared_completed_candidate_count": len(declared_candidate_ids),
        "completion_lineage_incomplete_count": len(unresolved_candidate_ids),
        "completion_lineage_unresolved_candidate_ids": unresolved_candidate_ids,
        "duplicate_valid_completion_event_count": duplicate_valid_completion_event_count,
        "completion_lineage_reject_counts": dict(sorted(lineage_reject_counts.items())),
        "completion_lineage_schema": COMPLETION_LINEAGE_SCHEMA,
        "required_completed_forward_rows": min_rows,
        "ticker_week_cluster_count": len(clusters),
        "required_ticker_week_clusters": min_clusters,
        "calendar_month_count": len(months),
        "required_calendar_months": min_months,
        "fixture_row_count": fixture_count,
        "max_fixture_rows": max_fixture_rows,
        "percent_metric_row_count": len(pct_entries),
        "usd_metric_row_count": len(usd_entries),
        "total_net_pnl_usd": total_net_pnl_usd,
        "percent_cluster_bootstrap": percent_bootstrap,
        "usd_cluster_bootstrap": usd_bootstrap,
        "checks": checks,
        "criteria_met_reporting_only": criteria_met,
    }


def _parity_disclosure(
    scan_task_health: dict[str, Any], scan_task_meta: dict[str, Any]
) -> dict[str, Any]:
    monthly_upper_bound = (
        HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT
        / HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT
    )
    return {
        "historical_materializer_entry_window_et": "10:10-10:25",
        "historical_materializer": "deterministic_local_pit_candidate_materializer_v1",
        "forward_source": "production_scan_sessions",
        "forward_scheduled_session_times": _scheduled_session_times(scan_task_health),
        "scan_task_health": scan_task_meta,
        "additional_forward_scanner_gates": [
            "momentum",
            "tech_score",
            "history_or_liquidity",
            "option_liquidity",
            "portfolio_and_profitability_gates",
        ],
        "forward_results_are_new_distribution": True,
        "not_continuation_of_historical_audit_sample": True,
        "historical_filtered_materializer_rows": HISTORICAL_FILTERED_MATERIALIZER_ROW_COUNT,
        "historical_filtered_materializer_months": HISTORICAL_FILTERED_MATERIALIZER_MONTH_COUNT,
        "expected_match_rate_note": (
            "filtered materializer produced 306 rows / 24 months "
            f"(~{round(monthly_upper_bound)} per month upper bound before production scanner gates), "
            "so months of zero forward matches are expected and are not by themselves a tracker bug"
        ),
    }


def _entry_quote_source(row: dict[str, Any]) -> str:
    return _norm(
        row.get("entry_quote_source")
        or row.get("quote_source")
        or row.get("options_data_source")
        or _as_dict(row.get("entry_quote_snapshot")).get("quote_source")
        or _as_dict(row.get("entry_quote_snapshot")).get("options_data_source")
    )


def _entry_quote_timestamp(row: dict[str, Any]) -> str:
    return _norm(
        row.get("entry_quote_timestamp_utc")
        or row.get("entry_quote_as_of_utc")
        or row.get("quote_timestamp_utc")
        or row.get("quote_time_utc")
        or _as_dict(row.get("entry_quote_snapshot")).get("quote_timestamp_utc")
    )


def _entry_snapshot_leg(row: dict[str, Any], role: str) -> dict[str, Any]:
    for raw_leg in _as_list(_as_dict(row.get("entry_quote_snapshot")).get("legs")):
        leg = _as_dict(raw_leg)
        if _norm_lower(leg.get("role")) == role:
            return leg
    return {}


def _entry_leg_prices(
    row: dict[str, Any],
) -> tuple[float | None, float | None, float | None, float | None]:
    long_leg = _entry_snapshot_leg(row, "long")
    short_leg = _entry_snapshot_leg(row, "short")
    long_bid = _field_from_row(
        row,
        (
            "entry_long_bid",
            "long_bid",
            "spread_liquidity.long_bid",
            "entry_quote_snapshot.long_bid",
        ),
    )
    long_ask = _field_from_row(
        row,
        (
            "entry_long_ask",
            "long_ask",
            "spread_liquidity.long_ask",
            "entry_quote_snapshot.long_ask",
        ),
    )
    short_bid = _field_from_row(
        row,
        (
            "entry_short_bid",
            "short_bid",
            "spread_liquidity.short_bid",
            "entry_quote_snapshot.short_bid",
        ),
    )
    short_ask = _field_from_row(
        row,
        (
            "entry_short_ask",
            "short_ask",
            "spread_liquidity.short_ask",
            "entry_quote_snapshot.short_ask",
        ),
    )
    return (
        _safe_float(long_bid if long_bid is not None else long_leg.get("bid")),
        _safe_float(long_ask if long_ask is not None else long_leg.get("ask")),
        _safe_float(short_bid if short_bid is not None else short_leg.get("bid")),
        _safe_float(short_ask if short_ask is not None else short_leg.get("ask")),
    )


def _entry_provenance(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    long_leg = _entry_snapshot_leg(row, "long")
    short_leg = _entry_snapshot_leg(row, "short")
    long_contract = _norm(
        row.get("long_contract_symbol")
        or row.get("contract_symbol")
        or long_leg.get("contract_symbol")
    )
    short_contract = _norm(
        row.get("short_contract_symbol") or short_leg.get("contract_symbol")
    )
    quote_source = _entry_quote_source(row)
    quote_timestamp_raw = _entry_quote_timestamp(row)
    long_timestamp_raw = _norm(
        row.get("long_entry_quote_timestamp_utc")
        or row.get("long_entry_quote_as_of_utc")
        or long_leg.get("quote_timestamp_utc")
    )
    short_timestamp_raw = _norm(
        row.get("short_entry_quote_timestamp_utc")
        or row.get("short_entry_quote_as_of_utc")
        or short_leg.get("quote_timestamp_utc")
    )
    quote_timestamp = _parse_utc_timestamp(quote_timestamp_raw)
    long_timestamp = _parse_utc_timestamp(long_timestamp_raw)
    short_timestamp = _parse_utc_timestamp(short_timestamp_raw)
    long_bid, long_ask, short_bid, short_ask = _entry_leg_prices(row)
    if not long_contract:
        reasons.append("missing_long_contract_symbol")
    if not short_contract:
        reasons.append("missing_short_contract_symbol")
    if not quote_source:
        reasons.append("missing_entry_quote_source")
    elif _norm_lower(quote_source) not in TRUSTED_COMPLETION_ENTRY_QUOTE_SOURCES:
        reasons.append("untrusted_entry_quote_source")
    if quote_timestamp is None:
        reasons.append("missing_or_invalid_timezone_aware_entry_quote_timestamp")
    if long_timestamp is None:
        reasons.append("missing_or_invalid_explicit_long_entry_quote_timestamp")
    if short_timestamp is None:
        reasons.append("missing_or_invalid_explicit_short_entry_quote_timestamp")
    if (
        quote_timestamp is not None
        and long_timestamp is not None
        and short_timestamp is not None
    ):
        if quote_timestamp != long_timestamp or quote_timestamp != short_timestamp:
            reasons.append("entry_quote_timestamps_not_exactly_synchronized")
        scan_date = _candidate_date(row)
        if not scan_date or any(
            timestamp.astimezone(EASTERN).date().isoformat() != scan_date
            for timestamp in (quote_timestamp, long_timestamp, short_timestamp)
        ):
            reasons.append("entry_quote_timestamp_date_mismatch")
    for field, value in (
        ("long_bid", long_bid),
        ("long_ask", long_ask),
        ("short_bid", short_bid),
        ("short_ask", short_ask),
    ):
        if value is None or value < 0:
            reasons.append(f"missing_or_invalid_entry_{field}")
    if long_bid is not None and long_ask is not None and long_ask < long_bid:
        reasons.append("entry_long_quote_crossed")
    if short_bid is not None and short_ask is not None and short_ask < short_bid:
        reasons.append("entry_short_quote_crossed")
    entry_debit = (
        round(float(long_ask) - float(short_bid), 4)
        if long_ask is not None and short_bid is not None
        else None
    )
    if entry_debit is not None and entry_debit <= 0:
        reasons.append("non_positive_entry_debit")
    geometry, geometry_reasons = _vertical_geometry(
        {
            **row,
            "long_contract_symbol": long_contract,
            "short_contract_symbol": short_contract,
        }
    )
    reasons.extend(geometry_reasons)
    width = _safe_float(geometry.get("spread_width"))
    if entry_debit is not None and width is not None and entry_debit > width + 0.0001:
        reasons.append("entry_debit_exceeds_vertical_width")
    declared_debit = _safe_float(
        row.get("net_debit")
        if row.get("net_debit") is not None
        else row.get("entry_execution_price")
        if row.get("entry_execution_price") is not None
        else row.get("entry_debit")
    )
    if (
        declared_debit is not None
        and entry_debit is not None
        and abs(declared_debit - entry_debit) > 0.0001
    ):
        reasons.append("declared_entry_debit_not_executable_leg_debit")
    canonical_timestamp = (
        _utc_iso(quote_timestamp)
        if quote_timestamp is not None
        else quote_timestamp_raw
    )
    canonical_long_timestamp = (
        _utc_iso(long_timestamp) if long_timestamp is not None else long_timestamp_raw
    )
    canonical_short_timestamp = (
        _utc_iso(short_timestamp)
        if short_timestamp is not None
        else short_timestamp_raw
    )
    derived_minute = (
        quote_timestamp.astimezone(EASTERN).hour * 60
        + quote_timestamp.astimezone(EASTERN).minute
        if quote_timestamp is not None
        else None
    )
    return (
        {
            **geometry,
            "long_contract_symbol": long_contract
            or geometry.get("long_contract_symbol"),
            "short_contract_symbol": short_contract
            or geometry.get("short_contract_symbol"),
            "entry_quote_source": quote_source,
            "entry_quote_timestamp_utc": canonical_timestamp,
            "entry_quote_as_of_utc": canonical_timestamp,
            "entry_quote_minute_et": derived_minute,
            "long_entry_quote_timestamp_utc": canonical_long_timestamp,
            "short_entry_quote_timestamp_utc": canonical_short_timestamp,
            "long_entry_quote_minute_et": derived_minute,
            "short_entry_quote_minute_et": derived_minute,
            "entry_long_bid": long_bid,
            "entry_long_ask": long_ask,
            "entry_short_bid": short_bid,
            "entry_short_ask": short_ask,
            "entry_debit": entry_debit,
            "entry_debit_basis": "long_ask_minus_short_bid",
        },
        sorted(set(reasons)),
    )


def _paper_shadow_row(
    row: dict[str, Any], *, tracking_start_date: str, tracking_start_at_utc: str
) -> dict[str, Any]:
    signal = _as_dict(row.get("signal_evidence"))
    tracking_state = _norm(row.get("tracking_state")) or "forward_paper_shadow_open"
    if not tracking_state.startswith("forward_paper_shadow_"):
        tracking_state = "forward_paper_shadow_open"
    return {
        **_candidate_identity_payload(row),
        "tracking_policy_id": POLICY_ID,
        "tracking_start_date": tracking_start_date,
        "tracking_start_at_utc": tracking_start_at_utc,
        "tracking_state": tracking_state,
        "evidence_bucket": "forward_paper_shadow",
        "scan_date": _candidate_date(row),
        "policy_exit_date": row.get("policy_exit_date") or _policy_exit_date(row),
        "exit_date": row.get("exit_date"),
        "ticker": _norm(row.get("ticker") or row.get("symbol")).upper(),
        "lane_id": _norm(
            row.get("lane_id") or row.get("playbook_id") or row.get("lane")
        ),
        "direction": _candidate_direction(row),
        "strategy_type": row.get("strategy_type"),
        "expiry": row.get("expiry")
        or row.get("expiration")
        or row.get("resolved_listed_expiry"),
        "dte": row.get("dte"),
        "long_contract_symbol": row.get("long_contract_symbol")
        or row.get("contract_symbol"),
        "short_contract_symbol": row.get("short_contract_symbol"),
        "long_strike": row.get("long_strike"),
        "short_strike": row.get("short_strike"),
        "spread_width": row.get("spread_width"),
        "net_debit": row.get("net_debit") or row.get("entry_execution_price"),
        "debit_pct_of_width": row.get("debit_pct_of_width"),
        "underlying_price": row.get("underlying_price"),
        "prior_20_trading_day_return_pct": signal.get(
            "prior_20_trading_day_return_pct"
        ),
        "prior_20_trading_day_return_source": signal.get(
            "prior_20_trading_day_return_source"
        ),
        "entry_quote_source": row.get("entry_quote_source")
        or row.get("quote_source")
        or row.get("options_data_source"),
        "quote_freshness_status": row.get("quote_freshness_status"),
        "entry_quote_snapshot": row.get("entry_quote_snapshot"),
        "entry_quote_timestamp_utc": _entry_quote_timestamp(row),
        "entry_quote_as_of_utc": row.get("entry_quote_as_of_utc")
        or _entry_quote_timestamp(row),
        "entry_quote_minute_et": row.get("entry_quote_minute_et"),
        "long_entry_quote_timestamp_utc": row.get("long_entry_quote_timestamp_utc")
        or row.get("long_entry_quote_as_of_utc"),
        "short_entry_quote_timestamp_utc": row.get("short_entry_quote_timestamp_utc")
        or row.get("short_entry_quote_as_of_utc"),
        "long_entry_quote_minute_et": row.get("long_entry_quote_minute_et"),
        "short_entry_quote_minute_et": row.get("short_entry_quote_minute_et"),
        "known_at": row.get("known_at"),
        "tradable_after": row.get("tradable_after"),
        "decision_timestamp_utc": row.get("decision_timestamp_utc"),
        "planned_exit_status": row.get("planned_exit_status") or "waiting_policy_exit",
        "realized_pnl_status": row.get("realized_pnl_status") or "open_no_exit_yet",
        "exit_quote_timestamp_utc": row.get("exit_quote_timestamp_utc")
        or row.get("exit_quote_as_of_utc"),
        "exit_quote_as_of_utc": row.get("exit_quote_as_of_utc")
        or row.get("exit_quote_timestamp_utc"),
        "exit_quote_minute_et": row.get("exit_quote_minute_et"),
        "long_exit_quote_timestamp_utc": row.get("long_exit_quote_timestamp_utc")
        or row.get("long_exit_quote_as_of_utc"),
        "short_exit_quote_timestamp_utc": row.get("short_exit_quote_timestamp_utc")
        or row.get("short_exit_quote_as_of_utc"),
        "long_exit_quote_minute_et": row.get("long_exit_quote_minute_et"),
        "short_exit_quote_minute_et": row.get("short_exit_quote_minute_et"),
        "pnl_pct": row.get("pnl_pct"),
        "gross_pnl_pct": row.get("gross_pnl_pct")
        if row.get("gross_pnl_pct") is not None
        else row.get("pnl_pct"),
        "net_pnl_pct": _canonical_net_pnl_pct(row),
        "net_pnl_pct_after_fees": row.get("net_pnl_pct_after_fees"),
        "net_pnl_usd": row.get("net_pnl_usd"),
        "source_scan_run_id": row.get("source_scan_run_id"),
        "source_scan_session_id": row.get("source_scan_session_id"),
        "source_scan_event_key": row.get("source_scan_event_key"),
        "source_scan_recorded_at_utc": row.get("source_scan_recorded_at_utc"),
        "source_logged_at": row.get("logged_at"),
        "source_row": row,
        "live_trade": False,
        "paper_broker_order": False,
        "broker_order_allowed": False,
        "auto_track_allowed": False,
        "scanner_policy_changed": False,
    }


def _matched_entry_log_row(
    row: dict[str, Any], *, tracking_start_date: str, tracking_start_at_utc: str
) -> tuple[dict[str, Any], list[str]]:
    base = _paper_shadow_row(
        row,
        tracking_start_date=tracking_start_date,
        tracking_start_at_utc=tracking_start_at_utc,
    )
    provenance, reasons = _entry_provenance(row)
    scan_provenance, scan_reasons = _scan_provenance(row)
    signal_lineage, signal_reasons = _signal_lineage(row)
    base.update(provenance)
    base.update(
        {
            "schema_version": 1,
            "record_type": "matched_entry",
            "lifecycle_event": "matched_entry",
            "append_only_log": True,
            "candidate_source_mode": "real_market_window_scan_picks",
            "fixture_mode": False,
            "contract_multiplier": CONTRACT_MULTIPLIER,
            "fee_per_contract_leg_usd": DEFAULT_FEE_PER_CONTRACT_LEG_USD,
            "scan_provenance": scan_provenance,
            "signal_lineage": signal_lineage,
        }
    )
    return base, sorted(set([*reasons, *scan_reasons, *signal_reasons]))


def _matched_entry_lineage_reject_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _norm(row.get("record_type")) != "matched_entry":
        reasons.append("preceding_entry_record_type_not_exact")
    if _norm(row.get("lifecycle_event")) != "matched_entry":
        reasons.append("preceding_entry_lifecycle_event_not_exact")
    if _norm(row.get("candidate_identity_schema")) != MATCHED_ROW_IDENTITY_SCHEMA:
        reasons.append("preceding_entry_identity_schema_missing_or_invalid")
    if not _norm(row.get("candidate_id")):
        reasons.append("preceding_entry_candidate_id_missing")
    if _strict_positive_int(row.get("source_scan_session_id")) is None:
        reasons.append("preceding_entry_source_scan_session_id_missing_or_invalid")
    if not _norm(row.get("source_scan_event_key")):
        reasons.append("preceding_entry_source_scan_event_key_missing")
    if not _norm(row.get("source_scan_run_id")):
        reasons.append("preceding_entry_source_scan_run_id_missing")
    if _parse_utc_timestamp(row.get("source_scan_recorded_at_utc")) is None:
        reasons.append("preceding_entry_source_scan_recorded_at_missing_or_invalid")
    _provenance, provenance_reasons = _entry_provenance(row)
    reasons.extend(f"preceding_entry_{reason}" for reason in provenance_reasons)
    _scan, scan_reasons = _scan_provenance(row)
    reasons.extend(f"preceding_entry_{reason}" for reason in scan_reasons)
    _signal, signal_reasons = _signal_lineage(row)
    reasons.extend(f"preceding_entry_{reason}" for reason in signal_reasons)
    if not _norm(row.get("ticker")):
        reasons.append("preceding_entry_ticker_missing")
    if not _norm(row.get("lane_id")):
        reasons.append("preceding_entry_lane_id_missing")
    if _norm(row.get("tracking_policy_id")) != POLICY_ID:
        reasons.append("preceding_entry_tracking_policy_id_invalid")
    expected_exit = _policy_exit_date(row)
    if expected_exit is None:
        reasons.append("preceding_entry_policy_exit_date_not_computable")
    elif _norm(row.get("policy_exit_date"))[:10] != expected_exit:
        reasons.append("preceding_entry_policy_exit_date_mismatch")
    return sorted(set(reasons))


def _completion_preceding_entry_reject_reasons(
    completion: dict[str, Any],
    preceding_entry: dict[str, Any] | None,
) -> list[str]:
    if preceding_entry is None:
        return ["completion_preceding_matched_entry_missing"]
    reasons: list[str] = []
    text_fields = (
        "candidate_id",
        "ticker",
        "direction",
        "lane_id",
        "strategy_type",
        "tracking_policy_id",
        "expiry",
        "policy_exit_date",
        "long_contract_symbol",
        "short_contract_symbol",
        "entry_quote_source",
        "entry_quote_timestamp_utc",
        "long_entry_quote_timestamp_utc",
        "short_entry_quote_timestamp_utc",
        "source_scan_event_key",
        "source_scan_run_id",
        "source_scan_recorded_at_utc",
    )
    for field in text_fields:
        left = (
            _norm_lower(completion.get(field))
            if field == "entry_quote_source"
            else _norm(completion.get(field))
        )
        right = (
            _norm_lower(preceding_entry.get(field))
            if field == "entry_quote_source"
            else _norm(preceding_entry.get(field))
        )
        if left != right:
            reasons.append(f"completion_preceding_entry_{field}_mismatch")
    numeric_fields = (
        "dte",
        "long_strike",
        "short_strike",
        "spread_width",
        "entry_long_ask",
        "entry_short_bid",
        "entry_debit",
    )
    for field in numeric_fields:
        left = _safe_float(completion.get(field))
        right = _safe_float(preceding_entry.get(field))
        if left is None or right is None or abs(left - right) > 0.0001:
            reasons.append(f"completion_preceding_entry_{field}_mismatch")
    completion_session_id = _strict_positive_int(
        completion.get("source_scan_session_id")
    )
    preceding_session_id = _strict_positive_int(
        preceding_entry.get("source_scan_session_id")
    )
    if (
        completion_session_id is None
        or preceding_session_id is None
        or completion_session_id != preceding_session_id
    ):
        reasons.append("completion_preceding_entry_source_scan_session_id_mismatch")
    for field in ("scan_provenance", "signal_lineage"):
        if _as_dict(completion.get(field)) != _as_dict(preceding_entry.get(field)):
            reasons.append(f"completion_preceding_entry_{field}_mismatch")
    return sorted(set(reasons))


def _validated_completion_rows(
    rows: Sequence[dict[str, Any]],
    *,
    verifier: _EntryQuoteStoreVerifier | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    declared_entries: dict[str, list[dict[str, Any]]] = {}
    locator_candidate_ids: dict[tuple[int, str, str, str], set[str]] = {}
    for declared_entry in rows:
        if _norm(declared_entry.get("record_type")) != "matched_entry":
            continue
        declared_candidate_id = _norm(declared_entry.get("candidate_id"))
        declared_session_id = _strict_positive_int(
            declared_entry.get("source_scan_session_id")
        )
        declared_locator = (
            declared_session_id or 0,
            _norm(declared_entry.get("source_scan_event_key")),
            _norm(declared_entry.get("source_scan_run_id")),
            _norm(declared_entry.get("source_scan_recorded_at_utc")),
        )
        if all(declared_locator) and declared_candidate_id:
            locator_candidate_ids.setdefault(declared_locator, set()).add(
                declared_candidate_id
            )
    valid_entries: dict[str, list[dict[str, Any]]] = {}
    completed_by_candidate: dict[str, dict[str, Any]] = {}
    declared: list[dict[str, Any]] = []
    reject_counts: Counter[str] = Counter()
    for row in rows:
        candidate_id = _norm(row.get("candidate_id"))
        if _norm(row.get("record_type")) == "matched_entry":
            declared_entries.setdefault(candidate_id, []).append(row)
            if not _matched_entry_lineage_reject_reasons(row):
                valid_entries.setdefault(candidate_id, []).append(row)
        if not _declares_completed_forward_row(row):
            continue
        declared.append(row)
        preceding_declared_entries = declared_entries.get(candidate_id, [])
        preceding_entries = valid_entries.get(candidate_id, [])
        preceding_entry = (
            preceding_entries[0]
            if len(preceding_declared_entries) == 1 and len(preceding_entries) == 1
            else None
        )
        reasons = [*_completion_lineage_reject_reasons(row)]
        if len(preceding_declared_entries) > 1:
            reasons.append("completion_preceding_matched_entry_not_unique")
        reasons.extend(_completion_preceding_entry_reject_reasons(row, preceding_entry))
        if preceding_entry is not None:
            preceding_locator = (
                _strict_positive_int(preceding_entry.get("source_scan_session_id"))
                or 0,
                _norm(preceding_entry.get("source_scan_event_key")),
                _norm(preceding_entry.get("source_scan_run_id")),
                _norm(preceding_entry.get("source_scan_recorded_at_utc")),
            )
            if len(locator_candidate_ids.get(preceding_locator, set())) != 1:
                reasons.append("completion_source_scan_locator_not_unique")
        verification_established = (
            _entry_quote_store_verification_established(
                preceding_entry, verifier=verifier
            )
            if verifier is not None
            else _entry_quote_store_verification_established(preceding_entry)
        )
        if not verification_established:
            reasons.append(ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER)
        if reasons:
            for reason in sorted(set(reasons)):
                reject_counts[reason] += 1
            continue
        if candidate_id in completed_by_candidate:
            reject_counts["duplicate_valid_completion_event"] += 1
            continue
        completed_by_candidate[candidate_id] = row
    return list(completed_by_candidate.values()), declared, reject_counts


def _validated_completed_candidate_ids(
    rows: Sequence[dict[str, Any]],
    *,
    verifier: _EntryQuoteStoreVerifier | None = None,
) -> set[str]:
    completed, _declared, _reject_counts = _validated_completion_rows(
        rows, verifier=verifier
    )
    return {
        _norm(row.get("candidate_id"))
        for row in completed
        if _norm(row.get("candidate_id"))
    }


def _merge_lifecycle_rows(
    rows: Sequence[dict[str, Any]],
    *,
    verifier: _EntryQuoteStoreVerifier | None = None,
) -> list[dict[str, Any]]:
    valid_completed, _declared, _reject_counts = _validated_completion_rows(
        rows, verifier=verifier
    )
    valid_completion_objects = {id(row) for row in valid_completed}
    by_candidate: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = _norm(row.get("candidate_id"))
        if not candidate_id:
            continue
        if _declares_completed_forward_row(row):
            if id(row) in valid_completion_objects:
                by_candidate[candidate_id] = dict(row)
            continue
        current = by_candidate.get(candidate_id)
        if current is None:
            by_candidate[candidate_id] = dict(row)
    return sorted(
        by_candidate.values(),
        key=lambda row: (
            str(row.get("identity_scan_date") or row.get("scan_date")),
            str(row.get("identity_ticker") or row.get("ticker")),
            str(row.get("identity_direction") or row.get("direction")),
            str(row.get("candidate_id")),
        ),
    )


def _append_jsonl_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n"
            )


def _conditions_text(conditions: Sequence[Any]) -> str:
    chunks = []
    for condition in conditions:
        condition = _as_dict(condition)
        value = condition.get("value")
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        chunks.append(f"{condition.get('field')} {condition.get('op')} {value}")
    return "; ".join(chunks) if chunks else "none"


def build_report(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    filtered_audit_path: Path = DEFAULT_FILTERED_AUDIT,
    source_scan_picks_path: Path = DEFAULT_SOURCE_SCAN_PICKS,
    underlying_daily_source_rows_path: Path = DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS,
    matched_rows_log_path: Path = DEFAULT_MATCHED_ROWS_LOG,
    forward_evidence_bar_contract_path: Path = DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    scan_task_health_path: Path = DEFAULT_SCAN_TASK_HEALTH,
    tracking_start_date: str | None = None,
    tracking_start_at_utc: str | None = None,
    previous_tracker_dir: Path | None = None,
    generated_at_utc: str | None = None,
    append_matched_rows: bool = False,
) -> dict[str, Any]:
    generated_at_raw = generated_at_utc or _utc_now_iso()
    generated_at_parsed = _parse_utc_timestamp(generated_at_raw)
    generated_at = (
        _utc_iso(generated_at_parsed)
        if generated_at_parsed is not None
        else _norm(generated_at_raw)
    )
    policy_contract, policy_contract_meta = _load_policy_contract(policy_contract_path)
    bar_contract, bar_meta = _load_optional_json(forward_evidence_bar_contract_path)
    scan_task_health, scan_task_meta = _load_optional_json(scan_task_health_path)
    filtered_audit, filtered_meta = _load_json(filtered_audit_path)
    scan_rows, scan_meta = _load_jsonl(source_scan_picks_path)
    matched_log_rows, matched_log_meta = _load_jsonl(matched_rows_log_path)
    daily_rows, daily_meta = _load_jsonl(underlying_daily_source_rows_path)
    source_index = _source_row_index(daily_rows)
    filter_source = _as_dict(filtered_audit.get("filter_source"))
    contract_conditions = _as_list(policy_contract.get("conditions"))
    conditions = contract_conditions
    expected_conditions_hash = _norm(policy_contract.get("conditions_sha256"))
    computed_conditions_hash = (
        _conditions_sha256(contract_conditions) if contract_conditions else ""
    )
    latest_audit_conditions = _as_list(filter_source.get("conditions"))
    if filtered_meta.get("status") != "loaded":
        policy_drift_status = "latest_filtered_audit_unavailable"
    elif latest_audit_conditions != contract_conditions:
        policy_drift_status = "latest_filtered_audit_diverged_from_frozen_contract"
    else:
        policy_drift_status = "latest_filtered_audit_matches_frozen_contract"
    prior_start_at = (
        _stable_tracking_start_at(previous_tracker_dir)
        if previous_tracker_dir
        else None
    )
    contract_start_at = _norm(policy_contract.get("tracking_start_at_utc"))
    start_at_raw = _norm(
        contract_start_at
        or tracking_start_at_utc
        or prior_start_at
        or filtered_audit.get("generated_at_utc")
        or filtered_audit.get("completed_at_utc")
        or generated_at
    )
    start_at_parsed = _parse_utc_timestamp(start_at_raw)
    start_at = (
        _utc_iso(start_at_parsed) if start_at_parsed is not None else start_at_raw
    )
    start_source = (
        "frozen_policy_contract"
        if contract_start_at
        else "explicit_tracking_start_at_utc"
        if tracking_start_at_utc
        else "previous_tracker_artifacts"
        if prior_start_at
        else "filtered_audit_timestamp"
    )
    start_date = (
        start_at_parsed.astimezone(EASTERN).date().isoformat()
        if start_at_parsed is not None
        else _norm(tracking_start_date or start_at)[:10]
    )

    blockers: list[str] = []
    if generated_at_parsed is None:
        blockers.append("generated_at_timestamp_missing_or_not_timezone_aware")
    if start_at_parsed is None:
        blockers.append("tracking_start_timestamp_missing_or_not_timezone_aware")
    if tracking_start_date and _norm(tracking_start_date)[:10] != start_date:
        blockers.append("tracking_start_date_timestamp_mismatch")
    if policy_contract_meta.get("status") != "loaded":
        blockers.append("frozen_filtered_policy_contract_missing")
    if not conditions:
        blockers.append("frozen_filtered_policy_conditions_missing")
    if (
        expected_conditions_hash
        and computed_conditions_hash
        and expected_conditions_hash != computed_conditions_hash
    ):
        blockers.append("frozen_filtered_policy_hash_mismatch")
    elif conditions and not expected_conditions_hash:
        blockers.append("frozen_filtered_policy_hash_missing")
    if scan_meta.get("status") != "loaded":
        blockers.append("scan_picks_not_loaded")
    blockers.extend(_scan_task_health_reject_reasons(scan_task_health, scan_task_meta))
    matched_log_duplicates = _matched_log_duplicate_daily_signal_identities(
        matched_log_rows
    )
    matched_log_identity_schema_current = _matched_log_has_current_identity_schema(
        matched_log_rows
    )
    if matched_log_rows and not matched_log_identity_schema_current:
        blockers.append(
            "matched_rows_log_nonempty_before_daily_signal_identity_upgrade"
        )
    if matched_log_duplicates:
        blockers.append("duplicate_ticker_date_direction_matched_rows")

    enriched_rows: list[dict[str, Any]] = []
    rejected_counts: Counter[str] = Counter()
    if not blockers:
        for row in scan_rows:
            source_row = {
                **row,
                "_source_scan_picks_sha256": _file_hash(source_scan_picks_path),
                "_scan_task_health_sha256": scan_task_meta.get("sha256"),
                "_scan_task_health_status": scan_task_health.get("status"),
                "_scan_task_health_generated_at_utc": scan_task_health.get(
                    "generated_at_utc"
                ),
            }
            enriched, reject_reason = _scan_row_for_filter(source_row, source_index)
            if reject_reason:
                rejected_counts[reject_reason] += 1
                continue
            scan_date = _candidate_date(enriched)
            if start_date and scan_date and scan_date < start_date:
                rejected_counts["pre_tracking_start_date"] += 1
                continue
            scan_timestamp = _parse_utc_timestamp(_candidate_timestamp(enriched))
            if scan_timestamp is None:
                rejected_counts["missing_or_invalid_timezone_aware_scan_timestamp"] += 1
                continue
            if (
                not scan_date
                or scan_timestamp.astimezone(EASTERN).date().isoformat() != scan_date
            ):
                rejected_counts["scan_timestamp_date_mismatch"] += 1
                continue
            if start_at_parsed is not None and scan_timestamp < start_at_parsed:
                rejected_counts["pre_tracking_start_timestamp"] += 1
                continue
            enriched_rows.append(enriched)
    raw_matched = (
        _filter_rows(enriched_rows, {"conditions": conditions})
        if conditions and not blockers
        else []
    )
    matched, match_dedupe_counts = _first_daily_signal_matches(raw_matched)
    existing_candidate_ids = {
        _norm(row.get("candidate_id"))
        for row in matched_log_rows
        if _norm(row.get("candidate_id"))
    }
    appendable_entries: list[dict[str, Any]] = []
    unappendable_rows: list[dict[str, Any]] = []
    unappendable_counts: Counter[str] = Counter()
    for row in matched:
        entry, reasons = _matched_entry_log_row(
            row, tracking_start_date=start_date, tracking_start_at_utc=start_at
        )
        if reasons:
            for reason in reasons:
                unappendable_counts[reason] += 1
            unappendable_rows.append(
                {
                    "candidate_id": entry.get("candidate_id"),
                    "scan_date": entry.get("scan_date"),
                    "ticker": entry.get("ticker"),
                    "status": "matched_but_unappendable_missing_entry_provenance",
                    "missing_entry_provenance_reasons": reasons,
                }
            )
            continue
        if _norm(entry.get("candidate_id")) not in existing_candidate_ids:
            appendable_entries.append(entry)
    if append_matched_rows:
        matched_rows_log_path.parent.mkdir(parents=True, exist_ok=True)
        matched_rows_log_path.touch(exist_ok=True)
        _append_jsonl_rows(matched_rows_log_path, appendable_entries)
        matched_log_rows = [*matched_log_rows, *appendable_entries]
        matched_log_meta = {
            **matched_log_meta,
            "exists": True,
            "status": "loaded"
            if matched_log_meta.get("status") in {"loaded", "missing"}
            else matched_log_meta.get("status"),
            "row_count": int(matched_log_meta.get("row_count") or 0)
            + len(appendable_entries),
        }
    merged_source_rows = [
        *matched_log_rows,
        *([] if append_matched_rows else appendable_entries),
    ]
    with _EntryQuoteStoreVerifier() as entry_verifier:
        paper_shadow_rows = _merge_lifecycle_rows(
            merged_source_rows, verifier=entry_verifier
        )
        forward_evidence_bar = _forward_evidence_bar_progress(
            merged_source_rows,
            bar_contract=bar_contract,
            bar_meta=bar_meta,
            verifier=entry_verifier,
        )
        (
            validated_completion_rows,
            declared_completion_rows,
            raw_completion_lineage_reject_counts,
        ) = _validated_completion_rows(matched_log_rows, verifier=entry_verifier)
        entry_quote_store_verifications = [
            dict(value) for value in entry_verifier.cache.values()
        ]
    by_ticker = Counter(str(row.get("ticker")) for row in paper_shadow_rows)
    by_date = Counter(str(row.get("scan_date")) for row in paper_shadow_rows)
    historical_metrics = _as_dict(filtered_audit.get("metrics"))
    audit_metrics = _as_dict(historical_metrics.get("simulated_forward_audit"))
    audit_bootstrap = _as_dict(
        audit_metrics.get("bootstrap_cluster") or audit_metrics.get("bootstrap")
    )
    parity_disclosure = _parity_disclosure(scan_task_health, scan_task_meta)
    duplicate_valid_completion_event_count = int(
        raw_completion_lineage_reject_counts.get("duplicate_valid_completion_event")
        or 0
    )
    invalid_completion_claim_count = max(
        0,
        len(declared_completion_rows)
        - len(validated_completion_rows)
        - duplicate_valid_completion_event_count,
    )
    validated_completed_count = len(
        {_norm(row.get("candidate_id")) for row in validated_completion_rows}
    )
    status = (
        "filtered_forward_paper_shadow_tracking_active"
        if not blockers
        else "blocked_filtered_forward_paper_shadow_tracker"
    )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at,
        "schema_version": 1,
        "read_only": not append_matched_rows,
        "matched_rows_log_write_requested": bool(append_matched_rows),
        "matched_rows_log_rows_written": len(appendable_entries)
        if append_matched_rows
        else 0,
        "report_artifact_write_performed": False,
        "tracking_policy_id": POLICY_ID,
        "tracking_start_date": start_date,
        "tracking_start_at_utc": start_at,
        "tracking_start_source": start_source,
        "tracking_label": "Historical filtered candidate v1 forward paper-shadow tracker",
        "inputs": {
            "policy_contract": policy_contract_meta,
            "forward_evidence_bar_contract": bar_meta,
            "scan_task_health": scan_task_meta,
            "filtered_audit": filtered_meta,
            "source_scan_picks": {
                **scan_meta,
                "sha256": _file_hash(source_scan_picks_path),
            },
            "matched_rows_log": {
                **matched_log_meta,
                "sha256": _file_hash(matched_rows_log_path),
            },
            "underlying_daily_source_rows": daily_meta,
        },
        "frozen_filter": {
            "source": "frozen_policy_contract",
            "contract_path": policy_contract_meta.get("path"),
            "contract_sha256": policy_contract_meta.get("sha256"),
            "policy_id": policy_contract.get("policy_id") or POLICY_ID,
            "filter_id": policy_contract.get("filter_id"),
            "description": policy_contract.get("description"),
            "conditions": conditions,
            "conditions_sha256": expected_conditions_hash,
            "computed_conditions_sha256": computed_conditions_hash,
            "conditions_text": _conditions_text(conditions),
            "freeze_rule": "consume the hash-pinned frozen policy contract exactly; do not retune from filtered audit or forward rows",
        },
        "policy_drift_status": policy_drift_status,
        "latest_filtered_audit_filter": {
            "source_report_id": filter_source.get("source_report_id"),
            "source_status": filter_source.get("source_status"),
            "filter_id": filter_source.get("filter_id"),
            "conditions_sha256": _conditions_sha256(latest_audit_conditions)
            if latest_audit_conditions
            else None,
        },
        "historical_audit_context": {
            "status": filtered_audit.get("status"),
            "accepted_historical_filtered_audit": filtered_audit.get(
                "accepted_historical_filtered_audit"
            ),
            "accepted_profitability": filtered_audit.get("accepted_profitability"),
            "audit_exact_trade_count": audit_metrics.get("exact_trade_count"),
            "audit_profit_factor": audit_metrics.get("profit_factor"),
            "audit_avg_pnl_pct": audit_metrics.get("avg_pnl_pct"),
            "audit_pf_lb_5pct": audit_bootstrap.get("pf_lb_5pct"),
            "historical_rows_are_forward_proof": filtered_audit.get(
                "historical_rows_are_forward_proof"
            ),
        },
        "forward_tracking": {
            "tracking_start_date": start_date,
            "tracking_start_at_utc": start_at,
            "tracking_start_source": start_source,
            "source_scan_row_count": len(scan_rows),
            "evaluated_scan_row_count": len(enriched_rows),
            "matched_candidate_count": len(paper_shadow_rows),
            "open_candidate_count": len(paper_shadow_rows) - validated_completed_count,
            "completed_candidate_count": validated_completed_count,
            "invalid_completion_claim_count": invalid_completion_claim_count,
            "duplicate_valid_completion_event_count": duplicate_valid_completion_event_count,
            "completion_lineage_reject_counts": dict(
                sorted(raw_completion_lineage_reject_counts.items())
            ),
            "completion_lineage_schema": COMPLETION_LINEAGE_SCHEMA,
            "entry_quote_store_verification_established": forward_evidence_bar.get(
                "entry_quote_store_verification_established"
            ),
            "entry_quote_store_verifications": entry_quote_store_verifications,
            "appendable_entry_count": len(appendable_entries),
            "entry_rows_appended_count": len(appendable_entries)
            if append_matched_rows
            else 0,
            "raw_matched_scan_row_count": len(raw_matched),
            "daily_signal_matched_row_count": len(matched),
            "same_day_signal_duplicate_matches_suppressed_count": match_dedupe_counts[
                "duplicate_same_day_signal_matches_suppressed"
            ],
            "matched_but_unappendable_missing_entry_provenance_count": len(
                unappendable_rows
            ),
            "matched_but_unappendable_counts": dict(
                sorted(unappendable_counts.items())
            ),
            "matched_rows_log_identity_schema": MATCHED_ROW_IDENTITY_SCHEMA,
            "matched_rows_log_identity_schema_current": matched_log_identity_schema_current,
            "duplicate_daily_signal_identity_count": len(matched_log_duplicates),
            "by_ticker": dict(sorted(by_ticker.items())),
            "by_scan_date": dict(sorted(by_date.items())),
            "rejected_counts": dict(sorted(rejected_counts.items())),
        },
        "forward_evidence_bar": forward_evidence_bar,
        "profitability_proof_blockers": forward_evidence_bar.get("proof_blockers", []),
        "parity_disclosure": parity_disclosure,
        "candidate_rows": paper_shadow_rows,
        "matched_but_unappendable_rows": unappendable_rows,
        "duplicate_daily_signal_identities": matched_log_duplicates,
        "blockers": blockers,
        "live_trade": False,
        "approval_authority": False,
        "accepted_profitability": False,
        "forward_rows_are_profitability_proof": False,
        "scanner_policy_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def render_markdown(report: dict[str, Any]) -> str:
    tracking = _as_dict(report.get("forward_tracking"))
    audit = _as_dict(report.get("historical_audit_context"))
    filt = _as_dict(report.get("frozen_filter"))
    bar = _as_dict(report.get("forward_evidence_bar"))
    parity = _as_dict(report.get("parity_disclosure"))
    lines = [
        "# Regular Options Filtered Forward Paper-Shadow Tracker",
        "",
        "This generated readback tracks prospective scan-pick rows that match the frozen historical filtered candidate policy. It is dashboard/reporting evidence, not broker execution.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Tracking policy: `{report.get('tracking_policy_id')}`.",
        f"- Tracking start date: `{tracking.get('tracking_start_date') or report.get('tracking_start_date')}`.",
        f"- Tracking start timestamp: `{tracking.get('tracking_start_at_utc') or report.get('tracking_start_at_utc')}`.",
        f"- Tracking start source: `{tracking.get('tracking_start_source') or report.get('tracking_start_source')}`.",
        f"- Filter: `{filt.get('filter_id')}`.",
        f"- Policy contract: `{filt.get('contract_path')}`.",
        f"- Policy drift status: `{report.get('policy_drift_status')}`.",
        f"- Conditions: {filt.get('conditions_text')}.",
        f"- Source scan rows: `{tracking.get('source_scan_row_count')}`.",
        f"- Evaluated scan rows: `{tracking.get('evaluated_scan_row_count')}`.",
        f"- Matched forward paper-shadow candidates: `{tracking.get('matched_candidate_count')}`.",
        f"- Open candidates: `{tracking.get('open_candidate_count')}`.",
        f"- Completed candidates: `{tracking.get('completed_candidate_count')}`.",
        f"- Entry rows appended: `{tracking.get('entry_rows_appended_count')}`.",
        f"- Matched but unappendable rows: `{tracking.get('matched_but_unappendable_missing_entry_provenance_count')}`.",
        f"- Matched-but-unappendable counts: `{json.dumps(tracking.get('matched_but_unappendable_counts') or {}, sort_keys=True)}`.",
        f"- Rejected counts: `{json.dumps(tracking.get('rejected_counts') or {}, sort_keys=True)}`.",
        f"- Forward evidence bar status: `{bar.get('status')}`.",
        f"- Entry quote store verification established: `{bar.get('entry_quote_store_verification_established')}`.",
        f"- Profitability proof blockers: `{json.dumps(bar.get('proof_blockers') or [], sort_keys=True)}`.",
        "",
        "## Historical Context",
        "",
        f"- Historical filtered audit status: `{audit.get('status')}`.",
        f"- Latest-four historical audit rows: `{audit.get('audit_exact_trade_count')}`.",
        f"- Latest-four historical audit PF: `{audit.get('audit_profit_factor')}`.",
        f"- Latest-four historical audit PF LB 5%: `{audit.get('audit_pf_lb_5pct')}`.",
        f"- Historical rows are forward proof: `{audit.get('historical_rows_are_forward_proof')}`.",
        "",
        "## Forward Evidence Bar",
        "",
        f"- Bar ID: `{bar.get('bar_id')}`.",
        f"- Completed rows: `{bar.get('completed_forward_rows')}` / `{bar.get('required_completed_forward_rows')}`.",
        f"- Ticker-week clusters: `{bar.get('ticker_week_cluster_count')}` / `{bar.get('required_ticker_week_clusters')}`.",
        f"- Calendar months with rows: `{bar.get('calendar_month_count')}` / `{bar.get('required_calendar_months')}`.",
        f"- Fixture rows: `{bar.get('fixture_row_count')}` / max `{bar.get('max_fixture_rows')}`.",
        f"- Evaluation permitted: `{bar.get('evaluation_permitted')}`.",
        f"- Entry quote store verification established: `{bar.get('entry_quote_store_verification_established')}`.",
        f"- Proof blockers: `{json.dumps(bar.get('proof_blockers') or [], sort_keys=True)}`.",
        f"- Criteria met reporting-only: `{bar.get('criteria_met_reporting_only')}`.",
        f"- Approval authority: `{bar.get('approval_authority')}`.",
        f"- Percent cluster PF LB 5%: `{_as_dict(bar.get('percent_cluster_bootstrap')).get('pf_lb_5pct')}`.",
        f"- USD cluster PF LB 5%: `{_as_dict(bar.get('usd_cluster_bootstrap')).get('pf_lb_5pct')}`.",
        f"- Total net USD: `{bar.get('total_net_pnl_usd')}`.",
        "",
        "## Parity Disclosure",
        "",
        f"- Historical materializer entry window ET: `{parity.get('historical_materializer_entry_window_et')}`.",
        f"- Historical materializer: `{parity.get('historical_materializer')}`.",
        f"- Forward source: `{parity.get('forward_source')}`.",
        f"- Scheduled session times: `{json.dumps(parity.get('forward_scheduled_session_times') or {}, sort_keys=True)}`.",
        f"- Forward results are a new distribution: `{parity.get('forward_results_are_new_distribution')}`.",
        f"- Expected match-rate note: {parity.get('expected_match_rate_note')}.",
        "",
        "## Candidate Rows",
        "",
        "| Scan Date | Ticker | Lane | Strategy | Expiry | Prior 20% | State |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in _as_list(report.get("candidate_rows"))[:50]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("scan_date") or ""),
                    str(row.get("ticker") or ""),
                    str(row.get("lane_id") or ""),
                    str(row.get("strategy_type") or ""),
                    str(row.get("expiry") or ""),
                    str(row.get("prior_20_trading_day_return_pct") or ""),
                    f"`{row.get('tracking_state')}`",
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Rows here are forward paper-shadow tracking rows for dashboard/reporting. They are not live trades, Alpaca paper orders, scanner-policy approval, promotion, quote import, evidence mutation, protected-holdout use, or proof-bar changes.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    candidates_jsonl: Path = DEFAULT_CANDIDATES_JSONL,
    matched_rows_log: Path = DEFAULT_MATCHED_ROWS_LOG,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    report["report_artifact_write_performed"] = True
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_jsonl.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "candidate_rows_jsonl": _rel(candidates_jsonl),
        "matched_rows_log": _rel(matched_rows_log),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    rows = _as_list(report.get("candidate_rows"))
    jsonl = "".join(
        json.dumps(_as_dict(row), sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    candidates_jsonl.write_text(jsonl, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track forward paper-shadow candidates for the frozen filtered policy."
    )
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument(
        "--forward-evidence-bar-contract",
        type=Path,
        default=DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    )
    parser.add_argument(
        "--scan-task-health", type=Path, default=DEFAULT_SCAN_TASK_HEALTH
    )
    parser.add_argument("--filtered-audit", type=Path, default=DEFAULT_FILTERED_AUDIT)
    parser.add_argument(
        "--source-scan-picks", type=Path, default=DEFAULT_SOURCE_SCAN_PICKS
    )
    parser.add_argument(
        "--underlying-daily-source-rows",
        type=Path,
        default=DEFAULT_UNDERLYING_DAILY_SOURCE_ROWS,
    )
    parser.add_argument(
        "--matched-rows-log", type=Path, default=DEFAULT_MATCHED_ROWS_LOG
    )
    parser.add_argument("--tracking-start-date", default=None)
    parser.add_argument("--tracking-start-at-utc", default=None)
    parser.add_argument("--previous-tracker-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--candidate-rows-jsonl", type=Path, default=DEFAULT_CANDIDATES_JSONL
    )
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        policy_contract_path=args.policy_contract,
        forward_evidence_bar_contract_path=args.forward_evidence_bar_contract,
        scan_task_health_path=args.scan_task_health,
        filtered_audit_path=args.filtered_audit,
        source_scan_picks_path=args.source_scan_picks,
        underlying_daily_source_rows_path=args.underlying_daily_source_rows,
        matched_rows_log_path=args.matched_rows_log,
        tracking_start_date=args.tracking_start_date,
        tracking_start_at_utc=args.tracking_start_at_utc,
        previous_tracker_dir=args.previous_tracker_dir or args.output_dir,
        append_matched_rows=not args.no_write,
    )
    if not args.no_write:
        write_outputs(
            report,
            output_dir=args.output_dir,
            candidates_jsonl=args.candidate_rows_jsonl,
            matched_rows_log=args.matched_rows_log,
            docs_report=args.docs_report,
        )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
