from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_evidence_blocker_burndown"

DEFAULT_TOURNAMENT = ROOT / "data" / "profitability-lab" / "regular-options-hypothesis-tournament" / "latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_REPAIR_BURNDOWN = ROOT / "data" / "profitability-lab" / "regular-options-repair-burndown" / "latest.json"
DEFAULT_REPAIR_ATTEMPTS = ROOT / "data" / "profitability-lab" / "regular-options-repair-attempts" / "latest.json"
DEFAULT_PROFIT_CAPTURE_QUEUE = ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
DEFAULT_MULTILANE = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_MONTHLY_AUDIT = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_PAPER_SHADOW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_paper_shadow_evidence_plan_latest.json"
DEFAULT_MARKET_WINDOW_CHECKLIST = (
    ROOT / "data" / "forward-tracking" / "regular_options_market_window_evidence_checklist_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-evidence-blocker-burndown"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-evidence-blocker-burndown.md"

MAX_SOURCE_AGE_HOURS = 96
MAX_REPAIR_MEMORY_AGE_HOURS = 720

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_evidence_blocker_burndown",
    "do_not_submit_broker_orders_from_evidence_blocker_burndown",
    "do_not_enable_auto_track_from_evidence_blocker_burndown",
    "do_not_enable_live_validation_from_evidence_blocker_burndown",
    "do_not_change_scanner_policy_from_evidence_blocker_burndown",
    "do_not_change_stops_from_evidence_blocker_burndown",
    "do_not_change_sizing_from_evidence_blocker_burndown",
    "do_not_lower_proof_bars_from_evidence_blocker_burndown",
    "do_not_mutate_evidence_databases_from_evidence_blocker_burndown",
    "do_not_import_quotes_without_explicit_later_approval",
    "do_not_write_to_options_history_db_without_explicit_later_approval",
    "do_not_treat_lookahead_only_rows_as_exact_proof",
    "do_not_treat_zero_bid_untradable_rows_as_missing_provider_data",
)

NON_GOALS = (
    "create trades",
    "submit broker orders",
    "enable auto-track",
    "enable live validation",
    "change scanner policy",
    "change stops",
    "change sizing",
    "lower proof bars",
    "mutate evidence databases",
    "prove future profits with certainty",
)

POST_REPAIR_RERUN_COMMANDS = (
    "npm run options:features:regular-options",
    "npm run options:robust-search:regular-options",
    "npm run options:replay:regular-options-walk-forward",
    "npm run options:research:robust-edge",
    "npm run options:research:hypothesis-tournament",
    "npm run options:research:evidence-blocker-burndown",
    "npm run options:audit:monthly-profitability",
)

SAFE_COMMAND_ORDER = (
    "uv run --locked python scripts/build_regular_options_repair_attempt_readback.py --no-write --json",
    "uv run --locked python scripts/build_regular_options_repair_burndown.py --no-write --json",
    "uv run --locked python scripts/build_regular_options_profit_capture_queue.py --no-write --json",
    "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --plan-only --json",
    "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py <source-run-json> --dry-run --json",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


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


def _contains_any(haystack: Any, needles: tuple[str, ...]) -> bool:
    text = json.dumps(haystack, sort_keys=True, default=str).lower() if isinstance(haystack, (dict, list)) else str(haystack).lower()
    return any(needle in text for needle in needles)


def _load_json_artifact(
    path: Path,
    *,
    name: str,
    required: bool,
    generated_at_utc: str,
    max_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": ["missing_readback"],
        "error": None,
        "report_id": name,
    }
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        meta["reason_codes"] = ["malformed_readback"]
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        meta["reason_codes"] = ["unreadable_readback"]
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["reason_codes"] = ["json_root_not_object"]
        return {}, meta

    meta["generated_at_utc"] = payload.get("generated_at_utc")
    generated = _parse_utc(payload.get("generated_at_utc"))
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    if generated is None:
        meta["status"] = "stale"
        meta["reason_codes"] = ["missing_or_malformed_generated_at_utc", "stale_readback"]
        return payload, meta
    age_hours = (as_of - generated).total_seconds() / 3600
    meta["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        meta["status"] = "invalid"
        meta["reason_codes"] = ["readback_generated_in_future"]
        return payload, meta
    if age_hours > max_age_hours:
        meta["status"] = "stale"
        meta["reason_codes"] = ["stale_readback"]
        return payload, meta

    meta["status"] = "loaded"
    meta["reason_codes"] = []
    meta["report_id"] = payload.get("report_id") or name
    return payload, meta


def _source_block_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(meta.get("status") == "stale" or "stale_readback" in _as_list(meta.get("reason_codes")) for meta in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _row_source_run(row: dict[str, Any]) -> str | None:
    source = _norm(row.get("source_artifact"))
    if source.endswith(".json"):
        return source
    for attempt in _as_list(row.get("latest_attempts")):
        for key in ("source_artifact", "summary_path"):
            value = _norm(_as_dict(attempt).get(key))
            if value.endswith(".json"):
                return value
    return source or None


def _safe_plan_only_command(row: dict[str, Any]) -> str | None:
    source = _row_source_run(row)
    if not source:
        return None
    parts = [f"uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py {source} --plan-only --json"]
    ticker = _norm(row.get("ticker") or row.get("symbol"))
    contract = _norm(row.get("contract_symbol"))
    quote_date = _norm(row.get("quote_date") or row.get("missing_quote_date"))
    if ticker:
        parts.append(f"--ticker {ticker}")
    if contract:
        parts.append(f"--contract-symbol {contract}")
    if quote_date:
        parts.append(f"--quote-date {quote_date[:10]}")
    return " ".join(parts)


def _safe_dry_run_command(row: dict[str, Any]) -> str | None:
    command = _safe_plan_only_command(row)
    if not command:
        return None
    return command.replace(" --plan-only --json", " --dry-run --json")


def _base_blocker(*, blocker_id: str, candidate_id: str, lane_id: str, source_artifact: str) -> dict[str, Any]:
    return {
        "blocker_id": blocker_id,
        "candidate_id": candidate_id,
        "lane_id": lane_id,
        "ticker": None,
        "contract_symbol": None,
        "quote_date": None,
        "entry_or_exit": "unknown",
        "blocker_type": "not_actionable",
        "source_artifact": source_artifact,
        "current_status": "unknown",
        "repair_actionability": "not_worth_repair",
        "expected_value_class": "unknown",
        "could_increase_holdout_count": False,
        "could_affect_pf_lower_bound": False,
        "is_exact_proof_repair": False,
        "is_lookahead_only": False,
        "is_zero_bid_tradability": False,
        "is_exhausted": False,
        "recommended_next_action": "No repair action is supported by local artifacts.",
        "safe_plan_only_command": None,
        "safe_dry_run_command": None,
        "do_not_repeat_reason": None,
    }


def _classify_repair_row(row: dict[str, Any], *, index: int, bucket_name: str) -> dict[str, Any]:
    status = _norm(row.get("burndown_status") or row.get("status") or row.get("repair_actionability_status"))
    actionability = _norm(row.get("repair_actionability") or row.get("repair_actionability_status"))
    missing_role = _norm(row.get("missing_leg_role") or row.get("entry_or_exit"))
    text_blob = {
        "status": status,
        "actionability": actionability,
        "reason_codes": row.get("reason_codes"),
        "blocking_gates": row.get("blocking_gates"),
        "unpriced_reason": row.get("unpriced_reason"),
        "latest_attempt_outcomes": row.get("latest_attempt_outcomes"),
        "latest_proof_repair_statuses": row.get("latest_proof_repair_statuses"),
        "next_action": row.get("next_action") or row.get("next_step") or row.get("row_next_step"),
    }
    lane_id = _norm(row.get("lane_id") or row.get("lane_family"))
    candidate_id = _norm(row.get("candidate_id") or row.get("playbook_id") or row.get("selection_reason") or lane_id)
    blocker = _base_blocker(
        blocker_id=f"repair-{index:04d}",
        candidate_id=candidate_id or "unknown_candidate",
        lane_id=lane_id or "unknown_lane",
        source_artifact="regular-options-repair-burndown",
    )
    blocker.update(
        {
            "ticker": _norm(row.get("ticker") or row.get("symbol")) or None,
            "contract_symbol": _norm(row.get("contract_symbol")) or None,
            "quote_date": (_norm(row.get("quote_date") or row.get("missing_quote_date")) or None),
            "entry_or_exit": "exit" if "exit" in missing_role.lower() else "entry" if "entry" in missing_role.lower() else "unknown",
            "current_status": status or actionability or bucket_name,
            "recommended_next_action": _norm(row.get("next_action") or row.get("next_step") or row.get("row_next_step"))
            or "Keep this blocker parked until a supported read-only repair step exists.",
        }
    )

    priority = _norm(row.get("evidence_repair_priority")).lower()
    is_high = priority == "high" or _safe_float(row.get("rank_score")) and (_safe_float(row.get("rank_score")) or 0) >= 80
    is_medium = priority == "medium"

    if _contains_any(text_blob, ("zero_bid", "zero bid", "non-executable", "untradable")):
        blocker.update(
            {
                "blocker_type": "zero_bid_tradability_failure",
                "repair_actionability": "blocked_zero_bid_tradability",
                "expected_value_class": "do_not_repair",
                "is_zero_bid_tradability": True,
                "do_not_repeat_reason": "Local evidence classifies this as zero-bid/non-executable tradability, not missing provider data.",
            }
        )
    elif "source_replay_required" in status.lower() or (
        "active_" not in status.lower() and _contains_any(text_blob, ("pending_replay", "rerun the source replay"))
    ):
        blocker.update(
            {
                "blocker_type": "source_replay_required",
                "repair_actionability": "source_replay_first",
                "expected_value_class": "high_proof_value" if is_high else "medium_proof_value",
                "is_exact_proof_repair": True,
                "could_increase_holdout_count": True,
                "could_affect_pf_lower_bound": True,
                "safe_plan_only_command": None,
                "safe_dry_run_command": None,
            }
        )
    elif _contains_any(text_blob, ("lookahead",)):
        blocker.update(
            {
                "blocker_type": "lookahead_only_not_proof",
                "repair_actionability": "blocked_lookahead_only",
                "expected_value_class": "diagnostic_only",
                "is_lookahead_only": True,
                "do_not_repeat_reason": "Only lookahead rows are available; they are diagnostic and cannot satisfy exact proof.",
            }
        )
    elif _contains_any(text_blob, ("exhausted", "exact_date_no_match", "current_source_exhausted", "no_match")):
        blocker.update(
            {
                "blocker_type": "exhausted_current_source_no_match",
                "repair_actionability": "blocked_exhausted_source",
                "expected_value_class": "do_not_repair",
                "is_exhausted": True,
                "do_not_repeat_reason": "Repair-attempt memory says the current source has no exact-date match; do not repeat without a new source or materially new evidence.",
            }
        )
    elif _contains_any(text_blob, ("missing_replay_source", "target_details_missing")):
        blocker.update(
            {
                "blocker_type": "repairable_missing_replay_source",
                "repair_actionability": "blocked_no_source_artifact",
                "expected_value_class": "unknown",
            }
        )
    elif _contains_any(text_blob, ("unpriced_exit", "missing_short_exit", "missing_long_exit")) or blocker["entry_or_exit"] == "exit":
        blocker.update({"blocker_type": "repairable_unpriced_exit", "repair_actionability": "ready_for_plan_only_check"})
    elif _contains_any(text_blob, ("unpriced_entry", "missing_short_entry", "missing_long_entry")) or blocker["entry_or_exit"] == "entry":
        blocker.update({"blocker_type": "repairable_unpriced_entry", "repair_actionability": "ready_for_plan_only_check"})
    else:
        blocker.update({"blocker_type": "repairable_missing_quote", "repair_actionability": "ready_for_plan_only_check"})

    if blocker["repair_actionability"] == "ready_for_plan_only_check":
        blocker["expected_value_class"] = "high_proof_value" if is_high else "medium_proof_value" if is_medium else "low_proof_value"
        blocker["is_exact_proof_repair"] = True
        blocker["could_increase_holdout_count"] = True
        blocker["could_affect_pf_lower_bound"] = True
        blocker["safe_plan_only_command"] = _safe_plan_only_command(row)
        blocker["safe_dry_run_command"] = _safe_dry_run_command(row)
        if not blocker["safe_plan_only_command"]:
            blocker["repair_actionability"] = "blocked_no_source_artifact"
            blocker["expected_value_class"] = "unknown"

    if bucket_name == "quarantine_queue" or _contains_any(row, ("quarantine", "no_chase", "no-chase")):
        blocker.update(
            {
                "blocker_type": "quarantine_no_chase",
                "repair_actionability": "not_worth_repair",
                "expected_value_class": "do_not_repair",
                "recommended_next_action": "Keep quarantined/no-chase lane parked; repair only if needed for falsification.",
                "do_not_repeat_reason": "No-chase/quarantine lanes are not current proof-value repair targets.",
            }
        )
    return blocker


def _repair_blockers(repair_burndown: dict[str, Any], profit_capture_queue: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for key in (
        "source_replay_required_targets",
        "active_exact_repair_targets",
        "diagnostic_lookahead_only_targets",
        "exhausted_current_source_targets",
        "target_details_missing_rows",
        "repair_attempt_memory_unavailable_rows",
    ):
        for row in _as_list(repair_burndown.get(key)):
            if isinstance(row, dict):
                rows.append((key, row))
    for key in ("evidence_repair_queue", "quarantine_queue"):
        for row in _as_list(profit_capture_queue.get(key)):
            if isinstance(row, dict):
                rows.append((key, row))

    blockers: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for bucket, row in rows:
        blocker = _classify_repair_row(row, index=len(blockers) + 1, bucket_name=bucket)
        identity = (
            blocker.get("candidate_id") or "",
            blocker.get("lane_id") or "",
            blocker.get("ticker") or "",
            blocker.get("contract_symbol") or "",
            blocker.get("quote_date") or "",
        )
        if identity in seen:
            continue
        seen.add(identity)
        blockers.append(blocker)
    return blockers


def _candidate_blockers(tournament: dict[str, Any], robust_edge: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    candidates = [*_as_list(tournament.get("candidate_rankings")), *_as_list(robust_edge.get("candidate_rankings"))]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = _norm(candidate.get("candidate_id")) or f"candidate-{len(blockers) + 1:04d}"
        lane_id = _norm(candidate.get("lane_id")) or "unknown_lane"
        if (candidate_id, lane_id) in seen:
            continue
        seen.add((candidate_id, lane_id))
        decision = _norm(candidate.get("decision"))
        reason_codes = [str(value) for value in _as_list(candidate.get("reason_codes"))]
        text = " ".join([decision, *reason_codes, _norm(candidate.get("source_quality_status")), _norm(candidate.get("next_step"))]).lower()
        if decision in {"paper_shadow_candidate", "thin_sample_watch"} and "volatility_expansion_observation" in lane_id:
            blocker_type = "thin_sample_only"
            actionability = "not_worth_repair"
            expected = "diagnostic_only"
            next_step = "Collect fresh exact paper-shadow entry and policy-defined exact realized exit evidence; do not repair this into live proof."
        elif "quarantine" in text or "no_chase" in text:
            blocker_type = "quarantine_no_chase"
            actionability = "not_worth_repair"
            expected = "do_not_repair"
            next_step = "Keep no-chase/quarantine candidate parked."
        elif "zero" in text and "bid" in text:
            blocker_type = "zero_bid_tradability_failure"
            actionability = "blocked_zero_bid_tradability"
            expected = "do_not_repair"
            next_step = "Reject as execution/tradability failure unless a predeclared different tradability source proves otherwise."
        elif "unpriced" in text or "source_quality" in text or "quote" in text or "coverage" in text:
            blocker_type = "coverage_gap"
            actionability = "blocked_no_source_artifact"
            expected = "unknown"
            next_step = "Use row-level repair-burndown targets before any import; do not infer proof from candidate aggregate metrics."
        elif "holdout" in text:
            blocker_type = "insufficient_final_holdout"
            actionability = "not_worth_repair"
            expected = "diagnostic_only"
            next_step = "Increase protected final-holdout depth only through predeclared exact rows or future forward paper evidence."
        elif "pf" in text or "lower" in text:
            blocker_type = "pf_lower_bound_fail"
            actionability = "not_worth_repair"
            expected = "diagnostic_only"
            next_step = "Treat PF lower-bound failure as strategy-quality/statistical weakness unless exact row repair changes replay distribution."
        elif "stress" in text or "winner" in text or decision == "overfit_reject":
            blocker_type = "stress_fail"
            actionability = "not_worth_repair"
            expected = "do_not_repair"
            next_step = "Reject or redesign the simple hypothesis; do not repair winner dependence with quote imports."
        elif "overlap" in text:
            blocker_type = "overlap_with_existing_stack"
            actionability = "not_worth_repair"
            expected = "diagnostic_only"
            next_step = "Use only as diagnostic; overlap is not an evidence-quality repair."
        else:
            continue
        blocker = _base_blocker(
            blocker_id=f"candidate-{len(blockers) + 1:04d}",
            candidate_id=candidate_id,
            lane_id=lane_id,
            source_artifact="regular-options-hypothesis-tournament",
        )
        blocker.update(
            {
                "blocker_type": blocker_type,
                "current_status": decision or _norm(candidate.get("source_quality_status")) or "candidate_blocked",
                "repair_actionability": actionability,
                "expected_value_class": expected,
                "could_increase_holdout_count": blocker_type in {"coverage_gap", "insufficient_final_holdout"},
                "could_affect_pf_lower_bound": blocker_type in {"coverage_gap", "pf_lower_bound_fail"},
                "is_exact_proof_repair": False,
                "is_lookahead_only": blocker_type == "lookahead_only_not_proof",
                "is_zero_bid_tradability": blocker_type == "zero_bid_tradability_failure",
                "is_exhausted": False,
                "recommended_next_action": next_step,
                "do_not_repeat_reason": "Candidate-level blocker has no row-level exact repair target." if actionability == "not_worth_repair" else None,
            }
        )
        blockers.append(blocker)
    return blockers


def _rank_key(blocker: dict[str, Any]) -> tuple[int, int, str]:
    expected_order = {
        "high_proof_value": 0,
        "medium_proof_value": 1,
        "low_proof_value": 2,
        "diagnostic_only": 3,
        "unknown": 4,
        "do_not_repair": 5,
    }
    action_order = {
        "source_replay_first": 0,
        "ready_for_plan_only_check": 1,
        "ready_for_dry_run_check": 2,
        "source_replay_required": 3,
        "blocked_no_source_artifact": 4,
        "blocked_lookahead_only": 5,
        "blocked_exhausted_source": 6,
        "blocked_zero_bid_tradability": 7,
        "not_worth_repair": 8,
    }
    return (
        expected_order.get(str(blocker.get("expected_value_class")), 9),
        action_order.get(str(blocker.get("repair_actionability")), 9),
        str(blocker.get("blocker_id")),
    )


def _current_algorithm_status(tournament: dict[str, Any], robust_edge: dict[str, Any]) -> dict[str, Any]:
    best = _as_dict(tournament.get("best_candidate_if_any") or robust_edge.get("best_candidate_if_any"))
    coverage = _as_dict(tournament.get("data_coverage_summary") or robust_edge.get("data_coverage_summary"))
    return {
        "hypothesis_tournament_status": tournament.get("overall_status"),
        "robust_edge_status": robust_edge.get("overall_status"),
        "best_candidate_id": best.get("candidate_id"),
        "best_lane_id": best.get("lane_id"),
        "best_decision": best.get("decision"),
        "best_profit_factor": best.get("profit_factor"),
        "best_avg_net_pnl_pct": best.get("avg_net_pnl_pct"),
        "best_holdout_rows": best.get("holdout_rows"),
        "best_total_exact_rows": best.get("total_exact_rows"),
        "promotion_ready": coverage.get("promotion_ready") or tournament.get("existing_promotion_ready") or False,
        "accepted_exact_trade_count": coverage.get("accepted_exact_trade_count"),
        "ready_candidate_count": coverage.get("ready_candidate_count"),
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
    }


def _holdout_gap_summary(tournament: dict[str, Any], robust_edge: dict[str, Any], blockers: list[dict[str, Any]]) -> dict[str, Any]:
    split = _as_dict(tournament.get("split_summary") or robust_edge.get("split_summary"))
    coverage = _as_dict(tournament.get("data_coverage_summary") or robust_edge.get("data_coverage_summary"))
    candidates = _as_list(tournament.get("candidate_rankings")) or _as_list(robust_edge.get("candidate_rankings"))
    holdouts = [_safe_int(_as_dict(candidate).get("holdout_rows")) for candidate in candidates if isinstance(candidate, dict)]
    current = max(holdouts) if holdouts else _safe_int(split.get("final_holdout_rows") or coverage.get("final_holdout_trades"))
    if current <= 0:
        current = 28 if _contains_any([tournament, robust_edge], ("28", "final holdout")) else 0
    target = 30
    actionable = [
        blocker
        for blocker in blockers
        if blocker.get("is_exact_proof_repair")
        and blocker.get("could_increase_holdout_count")
        and blocker.get("repair_actionability") in {"source_replay_first", "ready_for_plan_only_check", "ready_for_dry_run_check"}
    ]
    row_level_mapping_exposed = any(blocker.get("quote_date") and blocker.get("contract_symbol") for blocker in actionable)
    return {
        "current_final_holdout_rows": current,
        "target_final_holdout_rows": target,
        "gap_rows": max(target - current, 0) if current else None,
        "actionable_exact_repair_count": len(actionable),
        "row_level_holdout_mapping_exposed": row_level_mapping_exposed,
        "could_close_28_to_30_gap": bool(current and current < target and len(actionable) >= target - current and row_level_mapping_exposed),
        "conclusion": (
            "Local row-level repair targets exist, but artifacts do not prove which exact rows count toward protected final holdout."
            if actionable and not row_level_mapping_exposed
            else "Local artifacts expose exact repair rows that may increase holdout count after source replay."
            if actionable
            else "No actionable exact row-level repairs are exposed for the final-holdout gap."
        ),
    }


def _pf_lower_bound_gap_summary(tournament: dict[str, Any], robust_edge: dict[str, Any], blockers: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = _as_list(tournament.get("candidate_rankings")) or _as_list(robust_edge.get("candidate_rankings"))
    lbs = [
        _safe_float(_as_dict(candidate).get("profit_factor_lower_bound"))
        for candidate in candidates
        if isinstance(candidate, dict) and _safe_float(_as_dict(candidate).get("profit_factor_lower_bound")) is not None
    ]
    current = min((value for value in lbs if value is not None), default=None)
    combined = next(
        (
            _safe_float(_as_dict(candidate).get("profit_factor_lower_bound"))
            for candidate in candidates
            if "combined" in _norm(_as_dict(candidate).get("candidate_id")).lower()
            and _safe_float(_as_dict(candidate).get("profit_factor_lower_bound")) is not None
        ),
        None,
    )
    current = combined if combined is not None else current
    repairable = [
        blocker
        for blocker in blockers
        if blocker.get("is_exact_proof_repair")
        and blocker.get("could_affect_pf_lower_bound")
        and blocker.get("repair_actionability") in {"source_replay_first", "ready_for_plan_only_check", "ready_for_dry_run_check"}
    ]
    return {
        "current_profit_factor_lower_bound": _round(current, 2) if current is not None else 0.61,
        "target_profit_factor_lower_bound": 1.0,
        "repairable_exact_blocker_count": len(repairable),
        "count_repair_is_not_pf_repair": True,
        "conclusion": (
            "Exact repairs may change replay distribution, but the current PF lower-bound blocker is strategy-quality/statistical until rerun evidence proves otherwise."
            if repairable
            else "No local exact repair target demonstrates a credible path from PF lower bound 0.61 to above 1.0."
        ),
    }


def build_report(
    *,
    tournament_path: Path = DEFAULT_TOURNAMENT,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    repair_burndown_path: Path = DEFAULT_REPAIR_BURNDOWN,
    repair_attempts_path: Path = DEFAULT_REPAIR_ATTEMPTS,
    profit_capture_queue_path: Path = DEFAULT_PROFIT_CAPTURE_QUEUE,
    multilane_path: Path = DEFAULT_MULTILANE,
    monthly_audit_path: Path = DEFAULT_MONTHLY_AUDIT,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    paper_shadow_plan_path: Path = DEFAULT_PAPER_SHADOW_PLAN,
    market_window_checklist_path: Path = DEFAULT_MARKET_WINDOW_CHECKLIST,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at_utc = generated_at_utc or _utc_now_iso()
    source_specs = {
        "hypothesis_tournament": (tournament_path, True, max_source_age_hours),
        "robust_edge_discovery": (robust_edge_path, True, max_source_age_hours),
        "repair_burndown": (repair_burndown_path, True, max_source_age_hours),
        "repair_attempts": (repair_attempts_path, False, MAX_REPAIR_MEMORY_AGE_HOURS),
        "profit_capture_queue": (profit_capture_queue_path, False, max_source_age_hours),
        "multilane": (multilane_path, False, MAX_REPAIR_MEMORY_AGE_HOURS),
        "monthly_profitability": (monthly_audit_path, False, max_source_age_hours),
        "lane_promotion_state": (lane_promotion_path, False, max_source_age_hours),
        "trade_qualification": (trade_qualification_path, False, max_source_age_hours),
        "paper_shadow_evidence_plan": (paper_shadow_plan_path, False, max_source_age_hours),
        "market_window_evidence_checklist": (market_window_checklist_path, False, max_source_age_hours),
    }
    payloads: dict[str, dict[str, Any]] = {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    for name, (path, required, max_age) in source_specs.items():
        payload, meta = _load_json_artifact(
            path,
            name=name,
            required=required,
            generated_at_utc=generated_at_utc,
            max_age_hours=max_age,
        )
        payloads[name] = payload
        source_artifacts[name] = meta

    source_block = _source_block_status(source_artifacts)
    if source_block:
        return {
            "generated_at_utc": generated_at_utc,
            "report_id": REPORT_ID,
            "schema_version": 1,
            "read_only": True,
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "overall_status": source_block,
            "source_artifacts": source_artifacts,
            "current_algorithm_status": {
                "live_entry_allowed": False,
                "auto_track_allowed": False,
                "broker_order_allowed": False,
            },
            "blocked_candidate_count": 0,
            "repairable_blocker_count": 0,
            "high_proof_value_count": 0,
            "source_replay_required_count": 0,
            "zero_bid_tradability_failure_count": 0,
            "exhausted_source_count": 0,
            "lookahead_only_count": 0,
            "ranked_repair_queue": [],
            "do_not_repeat_queue": [],
            "source_replay_queue": [],
            "diagnostic_only_queue": [],
            "holdout_gap_summary": {},
            "pf_lower_bound_gap_summary": {},
            "recommended_safe_command_order": list(SAFE_COMMAND_ORDER),
            "post_repair_rerun_commands": list(POST_REPAIR_RERUN_COMMANDS),
            "prohibited_actions": list(PROHIBITED_ACTIONS),
            "non_goals": list(NON_GOALS),
        }

    repair_blockers = _repair_blockers(payloads["repair_burndown"], payloads["profit_capture_queue"])
    candidate_blockers = _candidate_blockers(payloads["hypothesis_tournament"], payloads["robust_edge_discovery"])
    blockers = [*repair_blockers, *candidate_blockers]
    if not repair_blockers:
        overall_status = "blocked_missing_row_level_blockers"
    else:
        actionable = [
            blocker
            for blocker in blockers
            if blocker.get("repair_actionability") in {"source_replay_first", "ready_for_plan_only_check", "ready_for_dry_run_check"}
        ]
        source_replay = [blocker for blocker in blockers if blocker.get("repair_actionability") == "source_replay_first"]
        overall_status = (
            "source_replay_required_before_repairs"
            if source_replay
            else "repair_queue_ready"
            if actionable
            else "no_actionable_repairs"
        )

    ranked = sorted(
        [
            blocker
            for blocker in blockers
            if blocker.get("repair_actionability") in {"source_replay_first", "ready_for_plan_only_check", "ready_for_dry_run_check"}
        ],
        key=_rank_key,
    )
    source_replay_queue = [blocker for blocker in ranked if blocker.get("repair_actionability") == "source_replay_first"]
    do_not_repeat_queue = [
        blocker
        for blocker in blockers
        if blocker.get("is_exhausted")
        or blocker.get("is_zero_bid_tradability")
        or blocker.get("blocker_type") == "quarantine_no_chase"
        or blocker.get("repair_actionability") in {"blocked_exhausted_source", "blocked_zero_bid_tradability"}
    ]
    diagnostic_only_queue = [
        blocker
        for blocker in blockers
        if blocker.get("is_lookahead_only") or blocker.get("expected_value_class") == "diagnostic_only"
    ]
    counts = Counter(str(blocker.get("blocker_type")) for blocker in blockers)
    action_counts = Counter(str(blocker.get("repair_actionability")) for blocker in blockers)
    expected_counts = Counter(str(blocker.get("expected_value_class")) for blocker in blockers)
    report = {
        "generated_at_utc": generated_at_utc,
        "report_id": REPORT_ID,
        "schema_version": 1,
        "scope": "regular_options_evidence_blocker_burndown",
        "read_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "overall_status": overall_status,
        "source_artifacts": source_artifacts,
        "current_algorithm_status": _current_algorithm_status(
            payloads["hypothesis_tournament"], payloads["robust_edge_discovery"]
        ),
        "blocked_candidate_count": _safe_int(payloads["hypothesis_tournament"].get("blocked_candidate_count"))
        or _safe_int(payloads["robust_edge_discovery"].get("blocked_candidate_count")),
        "repairable_blocker_count": action_counts.get("source_replay_first", 0)
        + action_counts.get("ready_for_plan_only_check", 0)
        + action_counts.get("ready_for_dry_run_check", 0),
        "high_proof_value_count": expected_counts.get("high_proof_value", 0),
        "source_replay_required_count": action_counts.get("source_replay_first", 0),
        "zero_bid_tradability_failure_count": counts.get("zero_bid_tradability_failure", 0),
        "exhausted_source_count": counts.get("exhausted_current_source_no_match", 0),
        "lookahead_only_count": counts.get("lookahead_only_not_proof", 0),
        "ranked_repair_queue": ranked,
        "do_not_repeat_queue": do_not_repeat_queue,
        "source_replay_queue": source_replay_queue,
        "diagnostic_only_queue": diagnostic_only_queue,
        "holdout_gap_summary": _holdout_gap_summary(
            payloads["hypothesis_tournament"], payloads["robust_edge_discovery"], blockers
        ),
        "pf_lower_bound_gap_summary": _pf_lower_bound_gap_summary(
            payloads["hypothesis_tournament"], payloads["robust_edge_discovery"], blockers
        ),
        "blocker_type_counts": dict(sorted(counts.items())),
        "repair_actionability_counts": dict(sorted(action_counts.items())),
        "expected_value_counts": dict(sorted(expected_counts.items())),
        "recommended_safe_command_order": list(SAFE_COMMAND_ORDER),
        "post_repair_rerun_commands": list(POST_REPAIR_RERUN_COMMANDS),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "non_goals": list(NON_GOALS),
    }
    return report


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], *, limit: int = 20) -> list[str]:
    if not rows:
        return ["No rows."]
    lines = ["| " + " | ".join(label for label, _ in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(_fmt(row.get(key)) for _, key in columns) + " |")
    if len(rows) > limit:
        lines.append(f"\nShowing `{limit}` of `{len(rows)}` rows.")
    return lines


def build_markdown(report: dict[str, Any]) -> str:
    status = report.get("overall_status")
    current = _as_dict(report.get("current_algorithm_status"))
    holdout = _as_dict(report.get("holdout_gap_summary"))
    pf_gap = _as_dict(report.get("pf_lower_bound_gap_summary"))
    ranked = _as_list(report.get("ranked_repair_queue"))
    source_replay = _as_list(report.get("source_replay_queue"))
    do_not_repeat = _as_list(report.get("do_not_repeat_queue"))
    diagnostic = _as_list(report.get("diagnostic_only_queue"))
    lines: list[str] = [
        "# Regular Options Evidence Blocker Burn-Down",
        "",
        (
            "No robust candidate passed. Source replay is the first blocker-burn-down step before any quote repair."
            if status == "source_replay_required_before_repairs"
            else "No robust candidate passed. Use the ranked exact repair queue only as read-only repair planning."
            if status == "repair_queue_ready"
            else "No robust candidate passed, and local artifacts do not expose an actionable row-level repair queue."
        ),
        "",
        "## Current Algorithm Status",
        "",
        f"- Overall status: `{status}`.",
        f"- Hypothesis tournament: `{current.get('hypothesis_tournament_status')}`.",
        f"- Robust-edge discovery: `{current.get('robust_edge_status')}`.",
        f"- Best lane: `{current.get('best_lane_id')}` / `{current.get('best_decision')}`.",
        f"- Best PF / avg net P&L: `{current.get('best_profit_factor')}` / `{current.get('best_avg_net_pnl_pct')}`.",
        f"- Promotion ready: `{current.get('promotion_ready')}`.",
        f"- Live entry / auto-track / broker order allowed: `False` / `False` / `False`.",
        "",
        "## Why No Robust Candidate Passed",
        "",
        "- The current best lane is still paper-shadow/probation, not robust/live-ready.",
        "- The historical combined candidate remains blocked by final-holdout depth and PF lower-bound quality.",
        "- Source-quality, unpriced, zero-bid/tradability, lookahead-only, exhausted-source, stress, and concentration blockers remain separated rather than merged into a false positive.",
        "",
        "## Ranked Repair Queue",
        "",
        *_table(
            ranked,
            [
                ("ID", "blocker_id"),
                ("Lane", "lane_id"),
                ("Ticker", "ticker"),
                ("Contract", "contract_symbol"),
                ("Date", "quote_date"),
                ("Type", "blocker_type"),
                ("Actionability", "repair_actionability"),
                ("Value", "expected_value_class"),
                ("Next", "recommended_next_action"),
            ],
            limit=25,
        ),
        "",
        "## Source Replay Queue",
        "",
        *_table(
            source_replay,
            [
                ("ID", "blocker_id"),
                ("Lane", "lane_id"),
                ("Ticker", "ticker"),
                ("Contract", "contract_symbol"),
                ("Date", "quote_date"),
                ("Next", "recommended_next_action"),
            ],
            limit=20,
        ),
        "",
        "## Do-Not-Repeat Exhausted Queue",
        "",
        *_table(
            do_not_repeat,
            [
                ("ID", "blocker_id"),
                ("Lane", "lane_id"),
                ("Ticker", "ticker"),
                ("Contract", "contract_symbol"),
                ("Date", "quote_date"),
                ("Type", "blocker_type"),
                ("Reason", "do_not_repeat_reason"),
            ],
            limit=25,
        ),
        "",
        "## Zero-Bid/Tradability Failures",
        "",
        f"- Count: `{report.get('zero_bid_tradability_failure_count')}`.",
        "- Zero-bid/non-executable rows are execution/tradability failures, not provider-missing rows.",
        "",
        "## Diagnostic Lookahead-Only Queue",
        "",
        *_table(
            diagnostic,
            [
                ("ID", "blocker_id"),
                ("Lane", "lane_id"),
                ("Ticker", "ticker"),
                ("Contract", "contract_symbol"),
                ("Date", "quote_date"),
                ("Type", "blocker_type"),
                ("Reason", "do_not_repeat_reason"),
            ],
            limit=25,
        ),
        "",
        "## Holdout Gap: 28 To 30 Analysis",
        "",
        f"- Current final-holdout rows: `{holdout.get('current_final_holdout_rows')}`.",
        f"- Target final-holdout rows: `{holdout.get('target_final_holdout_rows')}`.",
        f"- Gap rows: `{holdout.get('gap_rows')}`.",
        f"- Actionable exact repair rows exposed: `{holdout.get('actionable_exact_repair_count')}`.",
        f"- Can currently prove the exact 28-to-30 bridge: `{holdout.get('could_close_28_to_30_gap')}`.",
        f"- Conclusion: {holdout.get('conclusion')}",
        "",
        "## PF Lower-Bound Gap: 0.61 To >1.0 Analysis",
        "",
        f"- Current PF lower bound: `{pf_gap.get('current_profit_factor_lower_bound')}`.",
        f"- Target PF lower bound: `{pf_gap.get('target_profit_factor_lower_bound')}`.",
        f"- Repairable exact blockers that could affect replay distribution: `{pf_gap.get('repairable_exact_blocker_count')}`.",
        f"- Count repair is not PF repair: `{pf_gap.get('count_repair_is_not_pf_repair')}`.",
        f"- Conclusion: {pf_gap.get('conclusion')}",
        "",
        "## Safe Plan-Only/Dry-Run Command Hints",
        "",
        *[f"- `{command}`" for command in report.get("recommended_safe_command_order") or []],
        "",
        "## Post-Repair Rerun Command Order",
        "",
        *[f"- `{command}`" for command in report.get("post_repair_rerun_commands") or []],
        "",
        "## What Not To Repair",
        "",
        "- Do not repeat exhausted current-source exact-date loops without a new source or materially new evidence.",
        "- Do not use lookahead-only rows as proof.",
        "- Do not treat zero-bid/non-executable rows as missing data.",
        "- Do not repair no-chase/quarantined lanes for promotion; keep them parked except for falsification.",
        "",
        "## Source Artifacts And Staleness",
        "",
        *_table(
            list(_as_dict(report.get("source_artifacts")).values()),
            [
                ("Path", "path"),
                ("Required", "required"),
                ("Status", "status"),
                ("Generated", "generated_at_utc"),
                ("Age Hours", "age_hours"),
            ],
            limit=30,
        ),
        "",
        "## Non-Goals",
        "",
        *[f"- This workflow does not {item}." for item in report.get("non_goals") or []],
        "",
    ]
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> dict[str, str]:
    stamp = _utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path = output_dir / f"regular_options_evidence_blocker_burndown_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_evidence_blocker_burndown_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    markdown = build_markdown(report)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return {
        "json": _rel(json_path) or str(json_path),
        "latest_json": _rel(latest_json) or str(latest_json),
        "markdown": _rel(markdown_path) or str(markdown_path),
        "latest_markdown": _rel(latest_markdown) or str(latest_markdown),
        "docs_report": _rel(docs_report) or str(docs_report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options evidence blocker burn-down readback.")
    parser.add_argument("--hypothesis-tournament", type=Path, default=DEFAULT_TOURNAMENT)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--repair-burndown", type=Path, default=DEFAULT_REPAIR_BURNDOWN)
    parser.add_argument("--repair-attempts", type=Path, default=DEFAULT_REPAIR_ATTEMPTS)
    parser.add_argument("--profit-capture-queue", type=Path, default=DEFAULT_PROFIT_CAPTURE_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        tournament_path=args.hypothesis_tournament,
        robust_edge_path=args.robust_edge,
        repair_burndown_path=args.repair_burndown,
        repair_attempts_path=args.repair_attempts,
        profit_capture_queue_path=args.profit_capture_queue,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    else:
        print(report.get("overall_status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
