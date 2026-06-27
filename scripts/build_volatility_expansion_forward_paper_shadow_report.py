from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "volatility_expansion_forward_paper_shadow_report"
FROZEN_LANE_ID = "volatility_expansion_observation"
PHASE2_FROZEN_LANE_IDS = ("volatility_expansion_observation", "bullish_pullback_observation")

DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_FORWARD_COHORT_PREREGISTRATION = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_COHORT_LOG = ROOT / "data" / "forward-tracking" / "volatility_expansion_forward_paper_shadow_cohort.jsonl"
DEFAULT_PHASE2_COHORT_LOG = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_cohort.jsonl"
DEFAULT_SCHEMA = ROOT / "data" / "contracts" / "volatility-expansion-forward-paper-shadow-cohort-schema.json"
DEFAULT_PHASE2_SCHEMA = ROOT / "data" / "contracts" / "phase2-regular-options-forward-paper-shadow-cohort-schema.json"
PROPOSED_REPORT_PATH = ROOT / "data" / "forward-tracking" / "volatility_expansion_forward_paper_shadow_report_latest.json"
PROPOSED_PHASE2_REPORT_PATH = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_report_latest.json"
MARKET_TZ = ZoneInfo("America/New_York")

MIN_COMPLETED_ROWS_FOR_REVIEW = 30
PREFERRED_COMPLETED_ROWS = 50
MIN_STRESSED_PF_LB = 1.0
HEALTHY_STRESSED_PF_LB = 1.20
MAX_SINGLE_WINNER_PROFIT_SHARE_PCT = 25.0
MAX_TOP_THREE_WINNER_PROFIT_SHARE_PCT = 50.0
MAX_SINGLE_GROUP_PROFIT_SHARE_PCT = 50.0
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20260618

DENOMINATOR_STATUSES = {
    "exact_entry_captured",
    "missed_entry_evidence_window",
    "zero_bid_untradable",
    "stale_quote_rejected",
    "display_only_quote_rejected",
    "open_waiting_policy_exit",
    "exact_exit_captured",
    "missing_exit_evidence",
    "fill_attempt_failed_or_incomplete",
}

STRICT_NON_PROOF_CLASSES = {
    "midpoint",
    "stale",
    "eod",
    "daily_eod",
    "display",
    "display_only",
    "last_trade",
    "model",
    "manual",
    "non_executable",
    "lookahead",
    "lookahead_only",
    "lookahead_only_diagnostic",
}

TRUSTED_EXECUTABLE_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
    "alpaca_opra_daily_snapshot",
}

PROHIBITED_ACTIONS = (
    "do_not_place_or_prepare_broker_orders",
    "do_not_import_quotes",
    "do_not_repair_historical_rows",
    "do_not_mutate_existing_evidence_databases",
    "do_not_change_scanner_policy",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_change_broker_behavior",
    "do_not_change_strategy_logic",
)

STOP_LIST = (
    "combined_portfolio",
    "bullish_pullback_core",
    "lane_a_chain_native_ret20_4_stop200_time75",
    "tracked_winner_cheap_debit_continuity_v1",
    "high-PF filter matrix",
    "thin-sample watch candidates",
    "quarantine/no-chase lanes",
    "AAPL/UNH unsupported replay targets",
    "DIA unresolved replay targets",
    "source-blocker burn-down as profitability rescue",
    "broad hypothesis-tournament expansion",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _norm(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "reason_codes": ["missing_readback"],
        "error": None,
    }
    if not path.exists():
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source.update({"status": "malformed", "error": f"JSONDecodeError:{exc.lineno}:{exc.colno}", "reason_codes": ["malformed_readback"]})
        return {}, source
    except OSError as exc:
        source.update({"status": "unreadable", "error": type(exc).__name__, "reason_codes": ["unreadable_readback"]})
        return {}, source
    if not isinstance(payload, dict):
        source.update({"status": "invalid", "reason_codes": ["json_root_not_object"]})
        return {}, source
    source.update(
        {
            "status": "loaded",
            "generated_at_utc": payload.get("generated_at_utc") or payload.get("last_updated"),
            "reason_codes": [],
            "report_id": payload.get("report_id") or payload.get("contract_id"),
        }
    )
    return payload, source


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": False,
        "exists": path.exists(),
        "status": "missing",
        "row_count": 0,
        "malformed_row_count": 0,
        "reason_codes": ["cohort_log_not_created_yet"],
        "error": None,
    }
    if not path.exists():
        return [], source
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        for line_number, raw in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
            text = raw.strip().lstrip("\ufeff")
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(row, dict):
                rows.append(row)
            else:
                malformed += 1
    except OSError as exc:
        source.update({"status": "unreadable", "error": type(exc).__name__, "reason_codes": ["unreadable_cohort_log"]})
        return [], source
    source["row_count"] = len(rows)
    source["malformed_row_count"] = malformed
    if malformed:
        source["status"] = "malformed"
        source["reason_codes"] = ["malformed_jsonl_rows_present"]
    else:
        source["status"] = "loaded"
        source["reason_codes"] = []
    return rows, source


def _current_lane_from_trade_qualification(trade_qualification: dict[str, Any]) -> dict[str, Any]:
    best = _as_dict(trade_qualification.get("best_current_lane_if_any"))
    lane_rows = _as_list(trade_qualification.get("lane_decisions"))
    lane = next(
        (
            _as_dict(row)
            for row in lane_rows
            if isinstance(row, dict) and _norm(row.get("lane_id")) == FROZEN_LANE_ID
        ),
        {},
    )
    return {
        "lane_id": best.get("lane_id") or lane.get("lane_id"),
        "decision": best.get("decision") or lane.get("decision"),
        "promotion_state": lane.get("promotion_state"),
        "profit_factor": best.get("profit_factor") or lane.get("profit_factor"),
        "avg_net_pnl_pct": best.get("avg_net_pnl_pct") or lane.get("avg_net_pnl_pct"),
        "fresh_exact_entry_count": best.get("fresh_exact_entry_count") or lane.get("fresh_exact_entry_count"),
        "exact_realized_pnl_count": best.get("exact_realized_pnl_count") or lane.get("exact_realized_pnl_count"),
        "reason_codes": _as_list(lane.get("reason_codes")),
    }


def _preregistered_lane(preregistration: dict[str, Any], lane_id: str = FROZEN_LANE_ID) -> dict[str, Any]:
    lanes = _as_list(preregistration.get("lanes"))
    lane = next(
        (
            _as_dict(row)
            for row in lanes
            if isinstance(row, dict) and _norm(row.get("lane_id")) == lane_id
        ),
        {},
    )
    policy = _as_dict(_as_dict(_as_dict(preregistration.get("byte_frozen_policy_snapshot")).get("lanes")).get(lane_id))
    return {
        "lane_id": lane.get("lane_id"),
        "freeze_date": _as_dict(preregistration.get("cohort")).get("freeze_date"),
        "eval_date": _as_dict(preregistration.get("cohort")).get("eval_date"),
        "policy_snapshot_sha256": lane.get("policy_snapshot_sha256") or policy.get("sha256"),
        "source_file_sha256": _as_dict(preregistration.get("byte_frozen_policy_snapshot")).get("source_file_sha256"),
        "frozen": bool(_as_dict(preregistration.get("cohort")).get("frozen")),
        "symbols": lane.get("symbols") or _as_dict(policy.get("policy")).get("allowed_tickers"),
    }


def _preregistered_lanes(preregistration: dict[str, Any], allowed_lane_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {lane_id: _preregistered_lane(preregistration, lane_id) for lane_id in allowed_lane_ids}


def _allowed_lane_ids(frozen_lane: dict[str, Any]) -> set[str]:
    lanes = _as_list(frozen_lane.get("allowed_lane_ids")) or [FROZEN_LANE_ID]
    return {_norm(lane_id) for lane_id in lanes if _norm(lane_id)}


def _lane_preregistration(frozen_lane: dict[str, Any], lane_id: str) -> dict[str, Any]:
    by_lane = _as_dict(frozen_lane.get("preregistration_by_lane"))
    lane = _as_dict(by_lane.get(lane_id))
    if lane:
        return lane
    return _as_dict(frozen_lane.get("preregistration"))


def _policy_hash_for_row(frozen_lane: dict[str, Any], lane_id: str) -> str:
    by_lane = _as_dict(frozen_lane.get("policy_snapshot_sha256_by_lane"))
    return _norm(by_lane.get(lane_id) or frozen_lane.get("policy_snapshot_sha256"))


def _allowed_symbols_for_row(frozen_lane: dict[str, Any], lane_id: str) -> set[str]:
    prereg = _lane_preregistration(frozen_lane, lane_id)
    return {_norm(symbol) for symbol in _as_list(prereg.get("symbols")) if _norm(symbol)}


def _row_status(row: dict[str, Any]) -> str:
    candidates = (
        row.get("denominator_status"),
        row.get("selection_status"),
        row.get("entry_evidence_status"),
        row.get("exit_evidence_status"),
        row.get("fill_attempt_status"),
    )
    for value in candidates:
        text = _norm_lower(value)
        if text in DENOMINATOR_STATUSES:
            return text
    return "unknown"


def _is_exact_entry(row: dict[str, Any]) -> bool:
    return _norm_lower(row.get("entry_evidence_status")) in {"exact_entry_captured", "exact_entry"} or bool(row.get("exact_entry_captured"))


def _is_exact_exit(row: dict[str, Any]) -> bool:
    return _norm_lower(row.get("exit_evidence_status")) in {"exact_exit_captured", "exact_exit"} or bool(row.get("exact_exit_captured"))


def _has_quote_pair(row: dict[str, Any], prefix: str) -> bool:
    return _safe_float(row.get(f"{prefix}_bid")) is not None and _safe_float(row.get(f"{prefix}_ask")) is not None


def _has_trusted_executable_quote_source(row: dict[str, Any], prefix: str) -> bool:
    return _norm_lower(row.get(f"{prefix}_quote_source")) in TRUSTED_EXECUTABLE_QUOTE_SOURCES


def _has_exact_entry_provenance(row: dict[str, Any]) -> bool:
    return bool(_has_trusted_executable_quote_source(row, "entry") and _norm(row.get("entry_quote_timestamp_utc")) and _has_quote_pair(row, "entry"))


def _has_exact_exit_provenance(row: dict[str, Any]) -> bool:
    return bool(_has_trusted_executable_quote_source(row, "exit") and _norm(row.get("exit_quote_timestamp_utc")) and _has_quote_pair(row, "exit"))


def _policy_exit_condition_present(row: dict[str, Any]) -> bool:
    return bool(_norm(row.get("policy_exit_condition")))


def _completed_pnl_value(row: dict[str, Any]) -> float | None:
    if not (_is_exact_entry(row) and _is_exact_exit(row)):
        return None
    return _safe_float(row.get("net_pnl_usd") if row.get("net_pnl_usd") is not None else row.get("realized_net_pnl_usd"))


def _selection_identity(row: dict[str, Any], fallback_index: int | None = None) -> str:
    identity = _norm(row.get("selection_id") or row.get("row_id"))
    if identity:
        return identity
    return f"row_index:{fallback_index}" if fallback_index is not None else ""


def _is_phase2_scope(frozen_lane: dict[str, Any]) -> bool:
    return set(_allowed_lane_ids(frozen_lane)) == set(PHASE2_FROZEN_LANE_IDS)


def _is_fixture_or_synthetic_candidate(row: dict[str, Any]) -> bool:
    source_mode = _norm_lower(row.get("candidate_source_mode") or row.get("source_mode"))
    return bool(
        row.get("fixture_mode") is True
        or source_mode in {"fixture", "test", "synthetic"}
        or "tests/fixtures" in _norm_lower(row.get("source_artifact_path"))
    )


def _phase2_real_source_provenance_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_mode = _norm_lower(row.get("candidate_source_mode") or row.get("source_mode"))
    if _is_fixture_or_synthetic_candidate(row):
        errors.append("fixture_rows_not_append_eligible")
    if source_mode != "real_market_window_scan_picks":
        errors.append("missing_real_source_provenance")
    if _norm_lower(row.get("market_window_status")) != "open":
        errors.append("market_window_not_open")
    if not _norm(row.get("source_artifact_path")) or not _norm(row.get("source_artifact_sha256")) or not _norm(row.get("captured_at_utc")):
        errors.append("missing_source_provenance_fields")
    return _unique(errors)


def _strict_evidence_values(row: dict[str, Any]) -> set[str]:
    return {
        _norm_lower(row.get("quote_evidence_class")),
        _norm_lower(row.get("entry_evidence_class")),
        _norm_lower(row.get("exit_evidence_class")),
        _norm_lower(row.get("entry_quote_source")),
        _norm_lower(row.get("exit_quote_source")),
        _norm_lower(row.get("denominator_status")),
    }


def _timestamp_market_date(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        return parsed.date().isoformat()
    return parsed.astimezone(MARKET_TZ).date().isoformat()


def _selection_date(row: dict[str, Any]) -> str:
    explicit = _norm(row.get("selection_date"))
    if explicit:
        return explicit
    return _timestamp_market_date(row.get("selection_timestamp_utc"))


def _strict_acceptance_snapshot(
    *,
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
    frozen_lane: dict[str, Any],
    contract_blockers: list[str],
) -> dict[str, Any]:
    required_fields = [
        str(field)
        for field in _as_list(schema.get("record_required_fields"))
        if str(field).strip()
    ]
    freeze_date = _norm(_as_dict(frozen_lane.get("preregistration")).get("freeze_date"))
    allowed_lane_ids = _allowed_lane_ids(frozen_lane)
    reject_counts = {
        "blocked_by_required_contracts": 0,
        "missing_required_schema_fields": 0,
        "non_frozen_lane": 0,
        "non_preregistered_symbol": 0,
        "pre_freeze_not_acceptance_eligible": 0,
        "non_executable_mark_claimed_as_exact": 0,
        "lookahead_claimed_as_exact": 0,
        "missing_net_pnl_usd": 0,
        "duplicate_row_id": 0,
        "duplicate_completed_selection_id": 0,
        "fixture_source_not_proof_eligible": 0,
        "missing_real_source_provenance": 0,
        "market_window_not_open": 0,
        "missing_source_provenance_fields": 0,
        "unknown_denominator_status": 0,
        "scanner_hash_drift": 0,
        "exact_completed_missing_entry_quote_provenance": 0,
        "exact_completed_missing_exit_quote_provenance": 0,
        "exact_completed_missing_policy_exit_condition": 0,
    }
    seen_row_ids: set[str] = set()
    seen_completed_selection_ids: set[str] = set()
    accepted_usd: list[float] = []
    accepted_row_ids: list[str] = []
    accepted_rows = 0
    for index, row in enumerate(rows):
        row_rejected = False
        if contract_blockers:
            reject_counts["blocked_by_required_contracts"] += 1
            row_rejected = True
        if required_fields and any(not _norm(row.get(field)) for field in required_fields):
            reject_counts["missing_required_schema_fields"] += 1
            row_rejected = True
        row_lane_id = _norm(row.get("lane_id"))
        expected_policy_hash = _policy_hash_for_row(frozen_lane, row_lane_id)
        allowed_symbols = _allowed_symbols_for_row(frozen_lane, row_lane_id)
        if row_lane_id not in allowed_lane_ids:
            reject_counts["non_frozen_lane"] += 1
            row_rejected = True
        if _is_phase2_scope(frozen_lane):
            provenance_errors = _phase2_real_source_provenance_errors(row)
            if "fixture_rows_not_append_eligible" in provenance_errors:
                reject_counts["fixture_source_not_proof_eligible"] += 1
                row_rejected = True
            if "missing_real_source_provenance" in provenance_errors:
                reject_counts["missing_real_source_provenance"] += 1
                row_rejected = True
            if "market_window_not_open" in provenance_errors:
                reject_counts["market_window_not_open"] += 1
                row_rejected = True
            if "missing_source_provenance_fields" in provenance_errors:
                reject_counts["missing_source_provenance_fields"] += 1
                row_rejected = True
        if allowed_symbols and _norm(row.get("ticker") or row.get("symbol")) not in allowed_symbols:
            reject_counts["non_preregistered_symbol"] += 1
            row_rejected = True
        row_id = _norm(row.get("row_id") or row.get("selection_id"))
        if row_id and row_id in seen_row_ids:
            reject_counts["duplicate_row_id"] += 1
            row_rejected = True
        if row_id:
            seen_row_ids.add(row_id)
        if _norm_lower(row.get("denominator_status")) not in DENOMINATOR_STATUSES:
            reject_counts["unknown_denominator_status"] += 1
            row_rejected = True
        selection_date = _selection_date(row)
        if freeze_date and (not selection_date or selection_date <= freeze_date):
            reject_counts["pre_freeze_not_acceptance_eligible"] += 1
            row_rejected = True
        evidence_values = _strict_evidence_values(row)
        if evidence_values & STRICT_NON_PROOF_CLASSES:
            if any("lookahead" in value for value in evidence_values):
                reject_counts["lookahead_claimed_as_exact"] += 1
            else:
                reject_counts["non_executable_mark_claimed_as_exact"] += 1
            row_rejected = True
        if expected_policy_hash and _norm(row.get("scanner_policy_hash") or row.get("policy_snapshot_sha256")) not in {"", expected_policy_hash}:
            reject_counts["scanner_hash_drift"] += 1
            row_rejected = True
        net_pnl_usd = _safe_float(row.get("net_pnl_usd") if row.get("net_pnl_usd") is not None else row.get("realized_net_pnl_usd"))
        if net_pnl_usd is None:
            reject_counts["missing_net_pnl_usd"] += 1
            row_rejected = True
        exact_completed_claimed = _is_exact_entry(row) and _is_exact_exit(row) and _row_status(row) == "exact_exit_captured"
        if not exact_completed_claimed:
            row_rejected = True
        if exact_completed_claimed:
            selection_identity = _selection_identity(row, index)
            if selection_identity in seen_completed_selection_ids:
                reject_counts["duplicate_completed_selection_id"] += 1
                row_rejected = True
            else:
                seen_completed_selection_ids.add(selection_identity)
            if not _has_exact_entry_provenance(row):
                reject_counts["exact_completed_missing_entry_quote_provenance"] += 1
                row_rejected = True
            if not _has_exact_exit_provenance(row):
                reject_counts["exact_completed_missing_exit_quote_provenance"] += 1
                row_rejected = True
            if not _policy_exit_condition_present(row):
                reject_counts["exact_completed_missing_policy_exit_condition"] += 1
                row_rejected = True
        if not row_rejected and net_pnl_usd is not None:
            accepted_rows += 1
            accepted_usd.append(float(net_pnl_usd))
            if row_id:
                accepted_row_ids.append(row_id)
    return {
        "post_freeze_strict_exact_completed_rows": accepted_rows,
        "minimum_required": MIN_COMPLETED_ROWS_FOR_REVIEW,
        "required_contract_blockers": contract_blockers,
        "positive_net_usd_pnl": bool(accepted_usd) and sum(accepted_usd) > 0,
        "strict_profit_factor_usd": _profit_factor(accepted_usd),
        "bootstrap_pf_lower_bound_5pct_usd": _bootstrap_pf_lb(accepted_usd),
        "strict_net_pnl_usd_values": accepted_usd,
        "strict_accepted_row_ids": accepted_row_ids,
        "all_entries_executable": bool(accepted_rows),
        "all_policy_exits_executable": bool(accepted_rows),
        "proof_bar_unchanged": True,
        "live_authorized": False,
        "strict_reject_counts": reject_counts,
    }


def _candidate_append_validation_snapshot(
    *,
    rows: list[dict[str, Any]],
    schema: dict[str, Any],
    frozen_lane: dict[str, Any],
    source_loaded: bool,
    contract_blockers: list[str],
) -> dict[str, Any]:
    required_fields = [
        str(field)
        for field in _as_list(schema.get("record_required_fields"))
        if str(field).strip()
    ]
    freeze_date = _norm(_as_dict(frozen_lane.get("preregistration")).get("freeze_date"))
    allowed_lane_ids = _allowed_lane_ids(frozen_lane)
    reject_counts = {
        "blocked_by_required_contracts": 0,
        "missing_required_schema_fields": 0,
        "non_frozen_lane": 0,
        "non_preregistered_symbol": 0,
        "pre_freeze_not_append_eligible": 0,
        "duplicate_row_id": 0,
        "fixture_rows_not_append_eligible": 0,
        "missing_real_source_provenance": 0,
        "market_window_not_open": 0,
        "missing_source_provenance_fields": 0,
        "unknown_denominator_status": 0,
        "scanner_hash_drift": 0,
        "lookahead_source": 0,
        "exact_entry_missing_exact_entry_evidence": 0,
        "exact_entry_missing_entry_quote_provenance": 0,
        "exact_exit_missing_exact_entry_evidence": 0,
        "exact_exit_missing_exact_exit_evidence": 0,
        "exact_exit_missing_net_pnl_usd": 0,
        "exact_exit_missing_entry_quote_provenance": 0,
        "exact_exit_missing_exit_quote_provenance": 0,
        "exact_exit_missing_policy_exit_condition": 0,
        "exact_row_uses_non_executable_mark": 0,
    }
    seen_row_ids: set[str] = set()
    append_ready_rows = 0
    for row in rows:
        row_rejected = False
        if contract_blockers:
            reject_counts["blocked_by_required_contracts"] += 1
            row_rejected = True
        if required_fields and any(not _norm(row.get(field)) for field in required_fields):
            reject_counts["missing_required_schema_fields"] += 1
            row_rejected = True
        row_lane_id = _norm(row.get("lane_id"))
        expected_policy_hash = _policy_hash_for_row(frozen_lane, row_lane_id)
        allowed_symbols = _allowed_symbols_for_row(frozen_lane, row_lane_id)
        if row_lane_id not in allowed_lane_ids:
            reject_counts["non_frozen_lane"] += 1
            row_rejected = True
        if _is_phase2_scope(frozen_lane):
            provenance_errors = _phase2_real_source_provenance_errors(row)
            for error in provenance_errors:
                if error in reject_counts:
                    reject_counts[error] += 1
            if provenance_errors:
                row_rejected = True
        if allowed_symbols and _norm(row.get("ticker") or row.get("symbol")) not in allowed_symbols:
            reject_counts["non_preregistered_symbol"] += 1
            row_rejected = True
        row_id = _norm(row.get("row_id") or row.get("selection_id"))
        if row_id and row_id in seen_row_ids:
            reject_counts["duplicate_row_id"] += 1
            row_rejected = True
        if row_id:
            seen_row_ids.add(row_id)
        denominator_status = _norm_lower(row.get("denominator_status"))
        if denominator_status not in DENOMINATOR_STATUSES:
            reject_counts["unknown_denominator_status"] += 1
            row_rejected = True
        selection_date = _selection_date(row)
        if freeze_date and (not selection_date or selection_date <= freeze_date):
            reject_counts["pre_freeze_not_append_eligible"] += 1
            row_rejected = True
        if expected_policy_hash and _norm(row.get("scanner_policy_hash") or row.get("policy_snapshot_sha256")) not in {"", expected_policy_hash}:
            reject_counts["scanner_hash_drift"] += 1
            row_rejected = True
        evidence_values = _strict_evidence_values(row)
        has_lookahead_source = any("lookahead" in value for value in evidence_values)
        if has_lookahead_source:
            reject_counts["lookahead_source"] += 1
            row_rejected = True
        if denominator_status in {"exact_entry_captured", "exact_exit_captured", "open_waiting_policy_exit"} and not _is_exact_entry(row):
            reject_counts["exact_entry_missing_exact_entry_evidence"] += 1
            row_rejected = True
        if denominator_status in {"exact_entry_captured", "exact_exit_captured", "open_waiting_policy_exit"} and not _has_exact_entry_provenance(row):
            reject_counts["exact_entry_missing_entry_quote_provenance"] += 1
            row_rejected = True
        if denominator_status == "exact_exit_captured":
            if not _is_exact_entry(row):
                reject_counts["exact_exit_missing_exact_entry_evidence"] += 1
                row_rejected = True
            if not _is_exact_exit(row):
                reject_counts["exact_exit_missing_exact_exit_evidence"] += 1
                row_rejected = True
            if _safe_float(row.get("net_pnl_usd") if row.get("net_pnl_usd") is not None else row.get("realized_net_pnl_usd")) is None:
                reject_counts["exact_exit_missing_net_pnl_usd"] += 1
                row_rejected = True
            if not _has_exact_entry_provenance(row):
                reject_counts["exact_exit_missing_entry_quote_provenance"] += 1
                row_rejected = True
            if not _has_exact_exit_provenance(row):
                reject_counts["exact_exit_missing_exit_quote_provenance"] += 1
                row_rejected = True
            if not _policy_exit_condition_present(row):
                reject_counts["exact_exit_missing_policy_exit_condition"] += 1
                row_rejected = True
            if evidence_values & STRICT_NON_PROOF_CLASSES and not has_lookahead_source:
                reject_counts["exact_row_uses_non_executable_mark"] += 1
                row_rejected = True
        if not row_rejected:
            append_ready_rows += 1
    append_rejected_rows = len(rows) - append_ready_rows
    return {
        "validates_without_mutating_cohort": True,
        "cohort_append_performed": False,
        "source_loaded": source_loaded,
        "required_contract_blockers": contract_blockers,
        "total_candidate_rows": len(rows),
        "append_ready_rows": append_ready_rows,
        "append_rejected_rows": append_rejected_rows,
        "append_allowed": source_loaded and not contract_blockers and bool(rows) and append_rejected_rows == 0,
        "append_reject_counts": reject_counts,
    }


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if gains <= 0 and losses <= 0:
        return None
    if losses == 0:
        return None
    return round(gains / losses, 4)


def _bootstrap_pf_lb(values: list[float], *, samples: int = BOOTSTRAP_SAMPLES) -> float | None:
    if len(values) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    pfs: list[float] = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        pf = _profit_factor(sample)
        if pf is not None:
            pfs.append(pf)
    if not pfs:
        return None
    pfs.sort()
    index = max(0, int(len(pfs) * 0.05) - 1)
    return round(pfs[index], 4)


def _leave_one_out_pf_lb(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    pfs = [_profit_factor(values[:index] + values[index + 1 :]) for index in range(len(values))]
    finite = [value for value in pfs if value is not None]
    return round(min(finite), 4) if finite else None


def _winner_concentration(values: list[float]) -> dict[str, Any]:
    total_net = sum(values)
    winners = sorted((value for value in values if value > 0), reverse=True)
    largest = None
    top_three = None
    if total_net > 0 and winners:
        largest = round(winners[0] / total_net * 100, 2)
        top_three = round(sum(winners[:3]) / total_net * 100, 2)
    return {
        "total_net_profit": round(total_net, 4),
        "winner_count": len(winners),
        "largest_winner_pct_of_net_profit": largest,
        "top_three_winners_pct_of_net_profit": top_three,
        "largest_winner_gate_passed": largest is not None and largest < MAX_SINGLE_WINNER_PROFIT_SHARE_PCT,
        "top_three_winner_gate_passed": top_three is not None and top_three < MAX_TOP_THREE_WINNER_PROFIT_SHARE_PCT,
    }


def _group_key(row: dict[str, Any], group: str) -> str:
    if group == "ticker":
        return _norm(row.get("ticker") or row.get("symbol") or "unknown")
    if group == "date":
        return _selection_date(row) or "unknown"
    if group == "month":
        date_text = _selection_date(row)
        return date_text[:7] if len(date_text) >= 7 else "unknown"
    return "unknown"


def _group_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [(row, _completed_pnl_value(row)) for row in rows]
    completed = [(row, value) for row, value in completed if value is not None]
    values = [float(value) for _, value in completed]
    total_net = sum(values)
    result: dict[str, Any] = {}
    for group in ("ticker", "date", "month"):
        sums: defaultdict[str, float] = defaultdict(float)
        for row, value in completed:
            sums[_group_key(row, group)] += float(value)
        positive_groups = sorted(((key, value) for key, value in sums.items() if value > 0), key=lambda item: item[1], reverse=True)
        top_key = positive_groups[0][0] if positive_groups else None
        top_profit = positive_groups[0][1] if positive_groups else None
        top_share = round(top_profit / total_net * 100, 2) if total_net > 0 and top_profit is not None else None
        leave_group_values = [float(value) for row, value in completed if _group_key(row, group) != top_key]
        leave_group_pf = _profit_factor(leave_group_values)
        result[group] = {
            "top_group": top_key,
            "top_group_net_profit": round(top_profit, 4) if top_profit is not None else None,
            "top_group_pct_of_net_profit": top_share,
            "leave_top_group_out_pf": leave_group_pf,
            "dependency_gate_passed": bool(
                top_key
                and top_share is not None
                and top_share < MAX_SINGLE_GROUP_PROFIT_SHARE_PCT
                and leave_group_pf is not None
                and leave_group_pf > MIN_STRESSED_PF_LB
            ),
        }
    return result


def _counts(rows: list[dict[str, Any]], *, strict_completed_count: int = 0) -> dict[str, int]:
    statuses = Counter(_row_status(row) for row in rows)
    stale_display = statuses.get("stale_quote_rejected", 0) + statuses.get("display_only_quote_rejected", 0)
    natural_selection_ids = {_selection_identity(row, index) for index, row in enumerate(rows)}
    exact_entry_selection_ids = {
        _selection_identity(row, index)
        for index, row in enumerate(rows)
        if _is_exact_entry(row)
    }
    return {
        "total_natural_selections": len(natural_selection_ids),
        "event_row_count": len(rows),
        "exact_entry_captured_count": len(exact_entry_selection_ids),
        "missed_entry_evidence_count": statuses.get("missed_entry_evidence_window", 0),
        "zero_bid_untradable_count": statuses.get("zero_bid_untradable", 0),
        "stale_display_only_rejected_count": stale_display,
        "open_waiting_policy_exit_count": statuses.get("open_waiting_policy_exit", 0),
        "exact_completed_forward_pnl_count": strict_completed_count,
        "missing_exit_count": statuses.get("missing_exit_evidence", 0),
        "failed_or_incomplete_fill_attempt_count": statuses.get("fill_attempt_failed_or_incomplete", 0),
    }


def _scanner_hash_drift(rows: list[dict[str, Any]], frozen_lane: dict[str, Any]) -> list[str]:
    drifted = [
        _norm(row.get("row_id") or row.get("selection_id") or index)
        for index, row in enumerate(rows)
        if _policy_hash_for_row(frozen_lane, _norm(row.get("lane_id")))
        and _norm(row.get("scanner_policy_hash") or row.get("policy_snapshot_sha256"))
        not in {"", _policy_hash_for_row(frozen_lane, _norm(row.get("lane_id")))}
    ]
    return drifted


def _hard_states(
    *,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    frozen_lane: dict[str, Any],
    concentration: dict[str, Any],
    group_concentration: dict[str, Any],
    leave_one_out_pf_lb: float | None,
) -> dict[str, list[str]]:
    fail: list[str] = []
    warn: list[str] = []
    if not rows:
        warn.append("no_forward_cohort_log_rows_loaded")
    allowed_lane_ids = _allowed_lane_ids(frozen_lane)
    non_lane = [row for row in rows if _norm(row.get("lane_id")) not in allowed_lane_ids]
    if non_lane:
        fail.append("denominator_leakage_non_frozen_lane_rows_present")
    unknown_status = [row for row in rows if _row_status(row) == "unknown"]
    if unknown_status:
        fail.append("denominator_leakage_unknown_denominator_status")
    missing_selection_id = [row for row in rows if not _norm(row.get("row_id") or row.get("selection_id"))]
    if missing_selection_id:
        fail.append("denominator_leakage_missing_row_id")
    drifted = _scanner_hash_drift(rows, frozen_lane)
    if drifted:
        fail.append("scanner_hash_drift")
    if any(bool(row.get("policy_drift")) for row in rows):
        fail.append("policy_drift")
    if any(bool(row.get("evidence_drift")) for row in rows):
        fail.append("evidence_drift")
    if counts["zero_bid_untradable_count"]:
        warn.append("zero_bid_untradable_frequency_present")
    if counts["stale_display_only_rejected_count"]:
        warn.append("stale_or_display_only_quote_dependence_present")
    if counts["missed_entry_evidence_count"]:
        fail.append("missing_exact_entry_evidence")
    if counts["missing_exit_count"]:
        fail.append("missing_policy_defined_exit_evidence")
    if counts["failed_or_incomplete_fill_attempt_count"]:
        fail.append("failed_or_incomplete_fill_attempt_evidence")
    if concentration["largest_winner_pct_of_net_profit"] is not None and not concentration["largest_winner_gate_passed"]:
        fail.append("winner_concentration_largest_winner_failure")
    if concentration["top_three_winners_pct_of_net_profit"] is not None and not concentration["top_three_winner_gate_passed"]:
        fail.append("winner_concentration_top_three_failure")
    if leave_one_out_pf_lb is not None and leave_one_out_pf_lb <= MIN_STRESSED_PF_LB:
        fail.append("leave_one_trade_out_pf_lower_bound_not_above_1")
    for group, payload in group_concentration.items():
        if payload.get("top_group") and not payload.get("dependency_gate_passed"):
            fail.append(f"single_{group}_dependency")
    return {"hard_fail_states": _unique(fail), "warning_states": _unique(warn)}


def _gate_status(
    *,
    counts: dict[str, int],
    stressed_pf_lb: float | None,
    hard_fail_states: list[str],
) -> dict[str, Any]:
    min_rows = counts["exact_completed_forward_pnl_count"] >= MIN_COMPLETED_ROWS_FOR_REVIEW
    preferred_rows = counts["exact_completed_forward_pnl_count"] >= PREFERRED_COMPLETED_ROWS
    continuation = stressed_pf_lb is not None and stressed_pf_lb > MIN_STRESSED_PF_LB
    healthy = stressed_pf_lb is not None and stressed_pf_lb >= HEALTHY_STRESSED_PF_LB
    return {
        "minimum_review_packet_ready": min_rows and not hard_fail_states,
        "preferred_review_packet_ready": preferred_rows and not hard_fail_states,
        "minimum_completed_rows_required": MIN_COMPLETED_ROWS_FOR_REVIEW,
        "preferred_completed_rows": PREFERRED_COMPLETED_ROWS,
        "pf_lower_bound_after_stress_required_gt": MIN_STRESSED_PF_LB,
        "pf_lower_bound_after_stress_healthier_bar_gte": HEALTHY_STRESSED_PF_LB,
        "minimum_continuation_gate_passed": min_rows and continuation and not hard_fail_states,
        "healthier_continuation_gate_passed": preferred_rows and healthy and not hard_fail_states,
        "low_count_interpretation": "underpowered_read_condition_not_profitability_failure_unless_a_predeclared_max_observation_window_has_ended",
        "live_trading_authorized": False,
    }


def _required_contract_blockers(
    *,
    prereg_source: dict[str, Any],
    schema_source: dict[str, Any],
    prereg_lane: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if prereg_source.get("status") != "loaded":
        blockers.append(f"forward_preregistration_{prereg_source.get('status') or 'missing'}")
    if schema_source.get("status") != "loaded":
        blockers.append(f"cohort_schema_{schema_source.get('status') or 'missing'}")
    if _norm(prereg_lane.get("lane_id")) != FROZEN_LANE_ID:
        blockers.append("forward_preregistration_missing_frozen_volatility_lane")
    if not prereg_lane.get("frozen"):
        blockers.append("forward_preregistration_lane_not_frozen")
    if not _norm(prereg_lane.get("freeze_date")):
        blockers.append("forward_preregistration_missing_freeze_date")
    if not _norm(prereg_lane.get("policy_snapshot_sha256")):
        blockers.append("forward_preregistration_missing_policy_snapshot_sha256")
    if not _as_list(prereg_lane.get("symbols")):
        blockers.append("forward_preregistration_missing_symbols")
    if not _as_list(schema.get("record_required_fields")):
        blockers.append("cohort_schema_missing_record_required_fields")
    return _unique(blockers)


def _required_contract_blockers_for_lanes(
    *,
    prereg_source: dict[str, Any],
    schema_source: dict[str, Any],
    prereg_lanes: dict[str, dict[str, Any]],
    schema: dict[str, Any],
    allowed_lane_ids: tuple[str, ...],
) -> list[str]:
    if allowed_lane_ids == (FROZEN_LANE_ID,):
        return _required_contract_blockers(
            prereg_source=prereg_source,
            schema_source=schema_source,
            prereg_lane=prereg_lanes.get(FROZEN_LANE_ID, {}),
            schema=schema,
        )
    blockers: list[str] = []
    if prereg_source.get("status") != "loaded":
        blockers.append(f"forward_preregistration_{prereg_source.get('status') or 'missing'}")
    if schema_source.get("status") != "loaded":
        blockers.append(f"cohort_schema_{schema_source.get('status') or 'missing'}")
    for lane_id in allowed_lane_ids:
        prereg_lane = _as_dict(prereg_lanes.get(lane_id))
        if _norm(prereg_lane.get("lane_id")) != lane_id:
            blockers.append(f"forward_preregistration_missing_frozen_lane:{lane_id}")
        if not prereg_lane.get("frozen"):
            blockers.append(f"forward_preregistration_lane_not_frozen:{lane_id}")
        if not _norm(prereg_lane.get("freeze_date")):
            blockers.append(f"forward_preregistration_missing_freeze_date:{lane_id}")
        if not _norm(prereg_lane.get("policy_snapshot_sha256")):
            blockers.append(f"forward_preregistration_missing_policy_snapshot_sha256:{lane_id}")
        if not _as_list(prereg_lane.get("symbols")):
            blockers.append(f"forward_preregistration_missing_symbols:{lane_id}")
    if not _as_list(schema.get("record_required_fields")):
        blockers.append("cohort_schema_missing_record_required_fields")
    return _unique(blockers)


def _cohort_log_state(cohort_source: dict[str, Any], strict_rows: int) -> str:
    status = _norm(cohort_source.get("status"))
    if status == "missing":
        return "cohort_log_missing_blocker"
    if status in {"malformed", "unreadable"}:
        return "cohort_log_malformed_blocker"
    if _safe_int(cohort_source.get("row_count")) == 0:
        return "initialized_empty_zero_of_gate"
    if strict_rows == 0:
        return "rows_present_none_strict_excluded"
    if strict_rows < MIN_COMPLETED_ROWS_FOR_REVIEW:
        return "strict_rows_under_minimum"
    return "minimum_strict_rows_present_require_pf_and_concentration_gates"


def build_report(
    *,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    forward_cohort_preregistration_path: Path = DEFAULT_FORWARD_COHORT_PREREGISTRATION,
    cohort_log_path: Path = DEFAULT_COHORT_LOG,
    candidate_rows_path: Path | None = None,
    schema_path: Path = DEFAULT_SCHEMA,
    allowed_lane_ids: tuple[str, ...] = (FROZEN_LANE_ID,),
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    input_rows_path = candidate_rows_path or cohort_log_path
    candidate_validation_only = candidate_rows_path is not None
    trade_qualification, trade_source = _load_json(trade_qualification_path, required=True)
    robust_edge, robust_source = _load_json(robust_edge_path, required=True)
    preregistration, prereg_source = _load_json(forward_cohort_preregistration_path, required=True)
    schema, schema_source = _load_json(schema_path, required=True)
    rows, cohort_source = _load_jsonl(input_rows_path)
    if candidate_validation_only:
        cohort_source["artifact_role"] = "candidate_rows_validation_input"

    current_lane = _current_lane_from_trade_qualification(trade_qualification)
    allowed_lane_ids = tuple(_norm(lane_id) for lane_id in allowed_lane_ids if _norm(lane_id)) or (FROZEN_LANE_ID,)
    prereg_lanes = _preregistered_lanes(preregistration, allowed_lane_ids)
    prereg_lane = prereg_lanes.get(allowed_lane_ids[0], {})
    frozen_lane = {
        "lane_id": allowed_lane_ids[0],
        "allowed_lane_ids": list(allowed_lane_ids),
        "current_trade_qualification": current_lane,
        "preregistration": prereg_lane,
        "preregistration_by_lane": prereg_lanes,
        "robust_edge_candidate": _as_dict(robust_edge.get("best_candidate_if_any")),
        "policy_snapshot_sha256": prereg_lane.get("policy_snapshot_sha256"),
        "policy_snapshot_sha256_by_lane": {
            lane_id: _as_dict(prereg_lanes.get(lane_id)).get("policy_snapshot_sha256") for lane_id in allowed_lane_ids
        },
        "source_file_sha256": prereg_lane.get("source_file_sha256"),
    }

    lane_identification_warnings: list[str] = []
    if _norm(current_lane.get("lane_id")) not in set(allowed_lane_ids):
        lane_identification_warnings.append("trade_qualification_best_lane_not_in_forward_cohort")
    if preregistration and any(
        _norm(_as_dict(prereg_lanes.get(lane_id)).get("lane_id")) != lane_id or not _as_dict(prereg_lanes.get(lane_id)).get("frozen")
        for lane_id in allowed_lane_ids
    ):
        lane_identification_warnings.append("forward_preregistration_does_not_confirm_all_requested_frozen_lanes")

    contract_blockers = _required_contract_blockers_for_lanes(
        prereg_source=prereg_source,
        schema_source=schema_source,
        prereg_lanes=prereg_lanes,
        schema=schema,
        allowed_lane_ids=allowed_lane_ids,
    )
    acceptance_readiness = _strict_acceptance_snapshot(
        rows=rows,
        schema=schema,
        frozen_lane=frozen_lane,
        contract_blockers=contract_blockers,
    )
    completed_values = [float(value) for value in _as_list(acceptance_readiness.get("strict_net_pnl_usd_values"))]
    counts = _counts(rows, strict_completed_count=_safe_int(acceptance_readiness.get("post_freeze_strict_exact_completed_rows")))
    point_pf = _profit_factor(completed_values)
    bootstrap_lb = _bootstrap_pf_lb(completed_values)
    loo_lb = _leave_one_out_pf_lb(completed_values)
    stressed_candidates = [value for value in (bootstrap_lb, loo_lb) if value is not None]
    stressed_lb = round(min(stressed_candidates), 4) if stressed_candidates else None
    concentration = _winner_concentration(completed_values)
    group_concentration = _group_concentration(rows)
    states = _hard_states(
        rows=rows,
        counts=counts,
        frozen_lane=frozen_lane,
        concentration=concentration,
        group_concentration=group_concentration,
        leave_one_out_pf_lb=loo_lb,
    )
    states["warning_states"] = _unique([*states["warning_states"], *lane_identification_warnings])
    if contract_blockers:
        states["hard_fail_states"] = _unique([*states["hard_fail_states"], "blocked_missing_required_contract", *contract_blockers])
    if cohort_source.get("status") in {"missing", "malformed", "unreadable"}:
        states["warning_states"] = _unique([*states["warning_states"], _cohort_log_state(cohort_source, 0)])
    gate_status = _gate_status(
        counts=counts,
        stressed_pf_lb=stressed_lb,
        hard_fail_states=states["hard_fail_states"],
    )
    candidate_validation = _candidate_append_validation_snapshot(
        rows=rows,
        schema=schema,
        frozen_lane=frozen_lane,
        source_loaded=cohort_source.get("status") == "loaded",
        contract_blockers=contract_blockers,
    )
    source_artifacts = {
        "trade_qualification": trade_source,
        "robust_edge_discovery": robust_source,
        "forward_cohort_preregistration": prereg_source,
        "cohort_schema": schema_source,
        "cohort_log": cohort_source,
    }
    required_bad = [name for name, source in source_artifacts.items() if source.get("required") and source.get("status") != "loaded"]
    cohort_state = _cohort_log_state(cohort_source, _safe_int(acceptance_readiness.get("post_freeze_strict_exact_completed_rows")))
    if candidate_validation_only and contract_blockers:
        overall_status = "blocked_missing_required_contract"
    elif candidate_validation_only and cohort_source.get("status") != "loaded":
        overall_status = "blocked_candidate_rows_validation_input_missing_or_malformed"
    elif candidate_validation_only and not candidate_validation["append_allowed"]:
        overall_status = "candidate_rows_rejected_before_append"
    elif candidate_validation_only:
        overall_status = "candidate_rows_append_validation_passed_no_append_performed"
    elif required_bad:
        overall_status = "blocked_missing_required_contract"
    elif cohort_state in {"cohort_log_missing_blocker", "cohort_log_malformed_blocker", "initialized_empty_zero_of_gate"}:
        overall_status = cohort_state
    elif states["hard_fail_states"]:
        overall_status = "failed_forward_paper_shadow_protocol"
    elif gate_status["minimum_continuation_gate_passed"]:
        overall_status = "minimum_review_packet_ready_no_live_authorization"
    elif counts["exact_completed_forward_pnl_count"] > 0:
        overall_status = "underpowered_forward_paper_shadow_read"
    else:
        overall_status = "awaiting_forward_paper_shadow_evidence"

    phase2_scope = allowed_lane_ids != (FROZEN_LANE_ID,)
    return {
        "report_id": "phase2_regular_options_forward_paper_shadow_report" if phase2_scope else REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": (
            "phase2_regular_options_forward_paper_shadow_full_denominator"
            if phase2_scope
            else "volatility_expansion_observation_frozen_forward_paper_shadow_full_denominator"
        ),
        "read_only": True,
        "append_only_input_path": _rel(cohort_log_path),
        "candidate_validation_only": candidate_validation_only,
        "validated_candidate_rows_path": _rel(candidate_rows_path) if candidate_rows_path else None,
        "cohort_append_performed": False,
        "schema_contract_path": _rel(schema_path),
        "proposed_report_path": _rel(PROPOSED_PHASE2_REPORT_PATH if phase2_scope else PROPOSED_REPORT_PATH),
        "report_writes_enabled": False,
        "source_artifacts": source_artifacts,
        "overall_status": overall_status,
        "cohort_log_state": cohort_state,
        "required_contract_blockers": contract_blockers,
        "frozen_lane": frozen_lane,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "is_trade_recommendation": False,
        "total_natural_selections": counts["total_natural_selections"],
        "counts": counts,
        "candidate_append_validation": candidate_validation,
        "acceptance_readiness": acceptance_readiness,
        "strict_reject_counts": acceptance_readiness["strict_reject_counts"],
        "exact_realized_forward_profit_factor": point_pf,
        "bootstrap_pf_lower_bound_5pct": bootstrap_lb,
        "leave_one_trade_out_pf_lower_bound": loo_lb,
        "stressed_pf_lower_bound": stressed_lb,
        "winner_concentration": concentration,
        "ticker_date_month_concentration": group_concentration,
        "gates": gate_status,
        "hard_fail_states": states["hard_fail_states"],
        "warning_states": states["warning_states"],
        "denominator_rule": {
            "must_log_every_natural_scanner_selection": True,
            "counted_denominator_statuses": sorted(DENOMINATOR_STATUSES),
            "do_not_count_only_successful_evidence_capture_rows": True,
        },
        "stop_list": [{"branch": item, "decision": "stopped_for_this_protocol"} for item in STOP_LIST],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "cohort_schema_loaded": bool(schema),
    }


def render_markdown(report: dict[str, Any]) -> str:
    gates = _as_dict(report.get("gates"))
    counts = _as_dict(report.get("counts"))
    candidate_validation = _as_dict(report.get("candidate_append_validation"))
    acceptance = _as_dict(report.get("acceptance_readiness"))
    concentration = _as_dict(report.get("winner_concentration"))
    group_concentration = _as_dict(report.get("ticker_date_month_concentration"))
    lines = [
        "# Volatility Expansion Forward Paper-Shadow Cohort Report",
        "",
        "This is a read-only full-denominator paper-shadow report. It does not authorize live trading.",
        "",
        "## Decision State",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Live entry allowed: `{str(report.get('live_entry_allowed')).lower()}`.",
        f"- Auto-track allowed: `{str(report.get('auto_track_allowed')).lower()}`.",
        f"- Broker order allowed: `{str(report.get('broker_order_allowed')).lower()}`.",
        f"- Promotion ready: `{str(report.get('promotion_ready')).lower()}`.",
        f"- Candidate validation only: `{str(report.get('candidate_validation_only')).lower()}`.",
        f"- Cohort append performed: `{str(report.get('cohort_append_performed')).lower()}`.",
        "",
        "## Denominator Counts",
        "",
    ]
    for key in (
        "total_natural_selections",
        "exact_entry_captured_count",
        "missed_entry_evidence_count",
        "zero_bid_untradable_count",
        "stale_display_only_rejected_count",
        "open_waiting_policy_exit_count",
        "exact_completed_forward_pnl_count",
        "missing_exit_count",
        "failed_or_incomplete_fill_attempt_count",
    ):
        lines.append(f"- {key}: `{counts.get(key, report.get(key))}`.")
    lines.extend(
        [
            "",
            "## Profitability Read",
            "",
            f"- Exact realized forward PF: `{report.get('exact_realized_forward_profit_factor')}`.",
            f"- Bootstrap PF lower bound 5 pct: `{report.get('bootstrap_pf_lower_bound_5pct')}`.",
            f"- Leave-one-trade-out PF lower bound: `{report.get('leave_one_trade_out_pf_lower_bound')}`.",
            f"- Stressed PF lower bound: `{report.get('stressed_pf_lower_bound')}`.",
            f"- Minimum review packet ready: `{str(gates.get('minimum_review_packet_ready')).lower()}`.",
            f"- Minimum continuation gate passed: `{str(gates.get('minimum_continuation_gate_passed')).lower()}`.",
            f"- Healthier continuation gate passed: `{str(gates.get('healthier_continuation_gate_passed')).lower()}`.",
            "",
            "## Acceptance Readiness",
            "",
            f"- Post-freeze strict exact completed rows: `{acceptance.get('post_freeze_strict_exact_completed_rows')}` / `{acceptance.get('minimum_required')}`.",
            f"- Positive net USD P&L: `{str(acceptance.get('positive_net_usd_pnl')).lower()}`.",
            f"- Strict USD PF: `{acceptance.get('strict_profit_factor_usd')}`.",
            f"- Bootstrap USD PF lower bound 5 pct: `{acceptance.get('bootstrap_pf_lower_bound_5pct_usd')}`.",
            f"- Live authorized: `{str(acceptance.get('live_authorized')).lower()}`.",
            f"- Strict reject counts: `{json.dumps(report.get('strict_reject_counts'), sort_keys=True)}`.",
            "",
            "## Candidate Append Validation",
            "",
            f"- Append allowed: `{str(candidate_validation.get('append_allowed')).lower()}`.",
            f"- Total candidate rows: `{candidate_validation.get('total_candidate_rows')}`.",
            f"- Append-ready rows: `{candidate_validation.get('append_ready_rows')}`.",
            f"- Append-rejected rows: `{candidate_validation.get('append_rejected_rows')}`.",
            f"- Cohort append performed: `{str(candidate_validation.get('cohort_append_performed')).lower()}`.",
            f"- Append reject counts: `{json.dumps(candidate_validation.get('append_reject_counts'), sort_keys=True)}`.",
            "",
            "## Concentration",
            "",
            f"- Largest winner pct of net profit: `{concentration.get('largest_winner_pct_of_net_profit')}`.",
            f"- Top-three winners pct of net profit: `{concentration.get('top_three_winners_pct_of_net_profit')}`.",
        ]
    )
    for group, payload in group_concentration.items():
        payload = _as_dict(payload)
        lines.append(
            f"- {group}: top `{payload.get('top_group')}`, share `{payload.get('top_group_pct_of_net_profit')}`, "
            f"leave-out PF `{payload.get('leave_top_group_out_pf')}`, pass `{str(payload.get('dependency_gate_passed')).lower()}`."
        )
    lines.extend(["", "## Hard Fail / Warning States", ""])
    lines.append(f"- Hard failures: `{json.dumps(report.get('hard_fail_states'), sort_keys=True)}`.")
    lines.append(f"- Warnings: `{json.dumps(report.get('warning_states'), sort_keys=True)}`.")
    lines.extend(["", "## Stop List", ""])
    for row in _as_list(report.get("stop_list")):
        row = _as_dict(row)
        lines.append(f"- `{row.get('branch')}`: `{row.get('decision')}`.")
    lines.extend(["", "## Prohibited Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.extend(["", "## Source Artifacts", "", "| Source | Status | Path | Reasons |", "| --- | --- | --- | --- |"])
    for name, source in sorted(_as_dict(report.get("source_artifacts")).items()):
        source = _as_dict(source)
        lines.append(f"| `{name}` | `{source.get('status')}` | `{source.get('path')}` | `{json.dumps(source.get('reason_codes'), sort_keys=True)}` |")
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only volatility-expansion forward paper-shadow cohort report.")
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--forward-cohort-preregistration", type=Path, default=DEFAULT_FORWARD_COHORT_PREREGISTRATION)
    parser.add_argument("--cohort-log", type=Path, default=DEFAULT_COHORT_LOG)
    parser.add_argument("--candidate-rows", type=Path, default=None)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--allowed-lane", action="append", default=None)
    parser.add_argument("--phase2", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        trade_qualification_path=args.trade_qualification,
        robust_edge_path=args.robust_edge,
        forward_cohort_preregistration_path=args.forward_cohort_preregistration,
        cohort_log_path=args.cohort_log,
        candidate_rows_path=args.candidate_rows,
        schema_path=args.schema,
        allowed_lane_ids=PHASE2_FROZEN_LANE_IDS if args.phase2 else tuple(args.allowed_lane or [FROZEN_LANE_ID]),
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
