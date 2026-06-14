from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "monthly_all_lanes_profitability_audit"

DEFAULT_ARTIFACT_PATHS: dict[str, Path] = {
    "missed_picks_outcome": ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json",
    "missed_picks_failure_modes": ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json",
    "missed_picks_filter_matrix": ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json",
    "current_policy_cohort_health": ROOT / "data" / "forward-tracking" / "current_policy_cohort_health_latest.json",
    "current_policy_circuit_breaker": ROOT / "data" / "forward-tracking" / "current_policy_circuit_breaker_latest.json",
    "entry_filter_walkforward": ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_walkforward_latest.json",
    "entry_filter_point_in_time": ROOT / "data" / "forward-tracking" / "short_term_filter_point_in_time_replay_latest.json",
    "entry_filter_paper_monitor": ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_paper_monitor_latest.json",
    "candidate_ledger": ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json",
    "profitability_layer_stack": ROOT / "data" / "forward-tracking" / "regular_options_profitability_layer_stack_latest.json",
    "open_risk": ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json",
    "multilane_portfolio": ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json",
    "lane_promotion_state": ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json",
}

DEFAULT_OPTIONAL_ARTIFACT_PATHS: dict[str, Path] = {
    "scheduled_scan_heartbeat": ROOT / "data" / "forward-tracking" / "scheduled_scan_heartbeat_latest.json",
    "regular_options_autoresearch_scoreboard": ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-autoresearch"
    / "latest.json",
    "regime_stratified_replay_report": ROOT / "data" / "profitability-lab" / "regime-stratified-replay" / "latest.json",
    "overfit_rule_archive": ROOT / "data" / "forward-tracking" / "regular_options_overfit_rule_archive_latest.json",
    "lane_quarantine_archive": ROOT / "data" / "forward-tracking" / "regular_options_lane_quarantine_archive_latest.json",
    "stale_candidate_archive": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_stale_candidate_archive_latest.json",
    "lane_outcome_replay": ROOT / "data" / "forward-tracking" / "regular_options_lane_outcome_replay_latest.json",
    "lane_scan_hypothesis_repair": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_lane_scan_hypothesis_repair_latest.json",
    "exact_candidate_selection_repair": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_exact_candidate_selection_repair_latest.json",
    "chain_native_filter_relaxation_replay": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_chain_native_filter_relaxation_replay_latest.json",
    "chain_native_exit_outcome_replay": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_chain_native_exit_outcome_replay_latest.json",
    "chain_native_relaxation_archive": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_chain_native_relaxation_archive_latest.json",
    "exhausted_contract_archive": ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-exhausted-contract-archive"
    / "latest.json",
    "execution_alternative_quote_import_plan": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_execution_alternative_quote_import_plan_latest.json",
    "minute_exit_quote_import_plan": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_minute_exit_quote_import_plan_latest.json",
    "open_risk_resolution_plan": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_open_risk_resolution_plan_latest.json",
    "fill_attempt_evidence_capture_plan": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_fill_attempt_evidence_capture_plan_latest.json",
    "suggested_trade_review_plan": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_suggested_trade_review_plan_latest.json",
}

DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "monthly-all-lanes-profitability-audit.md"

REQUIRED_ARTIFACT_KEYS = tuple(DEFAULT_ARTIFACT_PATHS)

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_monthly_profitability_audit",
    "do_not_submit_broker_order_from_monthly_profitability_audit",
    "do_not_mutate_database_from_monthly_profitability_audit",
    "do_not_change_scanner_policy_from_monthly_profitability_audit",
    "do_not_change_stop_policy_from_monthly_profitability_audit",
    "do_not_change_sizing_from_monthly_profitability_audit",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_monthly_profitability_audit",
    "do_not_promote_paper_research_or_backfill_rows_to_production_proof",
)

REPLAY_GAP_LAYER_ACTIONS = {
    "top_spread_alternative_replay": "build_top_spread_alternative_replay",
    "contract_replacement_exit_survivability": "build_contract_replacement_replay",
    "minute_level_exit_quote_deterioration": "build_minute_exit_replay",
    "risk_budget_sizing_replay": "build_risk_budget_sizing_replay",
    "structure_specific_multileg_harness": "build_structure_specific_harness",
    "event_data_spine_post_event_vol_crush": "build_event_data_spine",
}

OPEN_RISK_RESOLUTION_PLAN_REPLACED_ACTIONS = {
    "resolve_open_risk_governor",
    "refresh_open_position_executable_review",
}

FILL_ATTEMPT_CAPTURE_PLAN_REPLACED_ACTIONS = {
    "capture_missing_fill_attempt_evidence",
}

SUGGESTED_TRADE_REVIEW_PLAN_REPLACED_ACTIONS = {
    "refresh_suggested_trade_review",
}

STALE_CANDIDATE_ARCHIVE_REPLACED_ACTIONS = {
    "wait_for_fresh_match_or_archive_candidate",
}

LANE_DISPOSITION_STATUSES = (
    "profitable_candidate",
    "paper_shadow",
    "retest",
    "needs_replay_engine",
    "quarantine",
    "archive",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _parse_utc_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _weekday_market_days_since(value: Any, *, as_of_utc: str | None = None) -> int | None:
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return None
    as_of = _parse_utc_datetime(as_of_utc) or datetime.now(UTC)
    current = parsed.date()
    count = 0
    while current < as_of.date():
        current = current.fromordinal(current.toordinal() + 1)
        if current.weekday() < 5:
            count += 1
    return count


def _scheduled_scan_health(heartbeat: dict[str, Any], *, as_of_utc: str | None = None) -> dict[str, Any]:
    if not heartbeat:
        return {
            "status": "missing",
            "state": "fail",
            "days_since_last_scheduled_scan": None,
            "blocker": "scheduled_scan_heartbeat_missing",
        }
    generated = heartbeat.get("run_completed_at_utc") or heartbeat.get("generated_at_utc")
    days = _weekday_market_days_since(generated, as_of_utc=as_of_utc)
    if days is None:
        status = "unusable_timestamp"
        state = "fail"
    elif days > 2:
        status = "stale"
        state = "fail"
    else:
        status = "fresh"
        state = "pass"
    return {
        "status": status,
        "state": state,
        "last_run_at_utc": generated,
        "last_status": heartbeat.get("status"),
        "last_host": heartbeat.get("host"),
        "last_commit_sha": heartbeat.get("commit_sha"),
        "days_since_last_scheduled_scan": days,
        "stale_market_day_limit": 2,
        "blocker": None if state == "pass" else "scheduled_scan_heartbeat_missing_or_stale",
    }


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


def _metric(row: dict[str, Any], key: str) -> Any:
    return row.get(key)


def _lane_leaderboard(failure_modes: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = {
        _norm(item.get("playbook")): item
        for item in _as_list(failure_modes.get("lane_decisions"))
        if isinstance(item, dict)
    }
    rows = []
    for item in _as_list(_as_dict(failure_modes.get("failure_modes")).get("by_playbook")):
        if not isinstance(item, dict):
            continue
        lane = _norm(item.get("key"))
        decision = decisions.get(lane, {})
        rows.append(
            {
                "lane": lane,
                "rows": item.get("rows"),
                "priced": item.get("priced"),
                "profit_factor": item.get("profit_factor"),
                "avg_net_pnl_pct": item.get("avg_net_pnl_pct"),
                "median_net_pnl_pct": item.get("median_net_pnl_pct"),
                "win_rate_pct": item.get("win_rate_pct"),
                "sum_net_pnl_usd": item.get("sum_net_pnl_usd"),
                "winner_count": item.get("winner_count"),
                "loser_count": item.get("loser_count"),
                "decision": decision.get("decision") or "unclassified",
                "blockers": list(decision.get("blockers") or []),
            }
        )
    rows.sort(
        key=lambda item: (
            _safe_float(item.get("avg_net_pnl_pct")) if _safe_float(item.get("avg_net_pnl_pct")) is not None else 999.0,
            _safe_float(item.get("profit_factor")) if _safe_float(item.get("profit_factor")) is not None else 999.0,
        )
    )
    return rows


def _active_regular_lane_states(lane_promotion_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    states = _as_dict(lane_promotion_state.get("lane_states"))
    active: dict[str, dict[str, Any]] = {}
    for lane, state in states.items():
        state = _as_dict(state)
        if _norm(state.get("tracking_mode")) == "auto_track" or bool(state.get("fresh_live_validation_enabled")):
            active[_norm(lane)] = state
    return active


def _lane_metric_value(
    lane_row: dict[str, Any],
    lane_state: dict[str, Any],
    key: str,
) -> Any:
    if lane_row.get(key) is not None:
        return lane_row.get(key)
    return _as_dict(lane_state.get("lane_gate_metrics")).get(key)


def _classify_lane_disposition(
    lane_row: dict[str, Any],
    lane_state: dict[str, Any],
    promotion: dict[str, Any],
) -> tuple[str, list[str], str]:
    pf = _safe_float(_lane_metric_value(lane_row, lane_state, "profit_factor"))
    avg = _safe_float(_lane_metric_value(lane_row, lane_state, "avg_net_pnl_pct"))
    priced = _safe_int(_lane_metric_value(lane_row, lane_state, "priced"))
    source_decision = _norm(lane_row.get("decision"))
    promotion_state = _norm(lane_state.get("promotion_state"))
    candidate_reason = _norm(lane_state.get("candidate_status_reason"))

    blockers = sorted(
        set(
            str(item)
            for item in [
                *_as_list(lane_row.get("blockers")),
                *_as_list(lane_state.get("blockers")),
                *_as_list(lane_state.get("failed_promotion_gates")),
            ]
            if item
        )
    )

    if _norm(lane_state.get("tracking_mode")) == "disabled" or candidate_reason == "lane_outside_regular_auto_track_scope":
        return (
            "archive",
            sorted(set([*blockers, "outside_regular_auto_track_scope"])),
            "outside regular supervised auto-track scope; keep out of this monthly profitability loop unless explicitly reopened",
        )
    if priced <= 0 or pf is None or avg is None:
        return (
            "needs_replay_engine",
            sorted(set([*blockers, "missing_monthly_lane_economics"])),
            "build or refresh exact lane outcome replay before tuning or promotion discussion",
        )
    if pf >= 1.2 and avg > 0:
        if priced >= 30 and bool(promotion.get("promotion_ready")) and not blockers:
            return (
                "profitable_candidate",
                blockers,
                "lane economics clear the current stage; existing promotion gates still own any stage advance",
            )
        if "probation" in source_decision or promotion_state == "paper_probation" or priced < 30:
            return (
                "paper_shadow",
                blockers,
                "collect fresh exact paper entries and exact realized exits before promotion",
            )
        return (
            "retest",
            blockers,
            "positive historical lane needs stronger holdout and fresh exact paper confirmation",
        )
    if priced >= 10 and (avg <= -20 or pf <= 0.3):
        return (
            "quarantine",
            blockers,
            "keep diagnostic/no-chase and require earn-back or a frozen entry-time retest",
        )
    if priced >= 30 and avg < 0 and pf < 0.8:
        return (
            "quarantine",
            blockers,
            "negative sufficiently sized lane should stay out of live validation until earn-back",
        )
    return (
        "retest",
        blockers,
        "freeze an entry-time-only retest or collect more exact evidence before lane decisions",
    )


def _lane_dispositions(
    lane_leaderboard: list[dict[str, Any]],
    lane_promotion_state: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, Any]:
    rows_by_lane = {_norm(row.get("lane")): row for row in lane_leaderboard if isinstance(row, dict)}
    active_states = _active_regular_lane_states(lane_promotion_state)
    lane_names = sorted(set(rows_by_lane) | set(active_states))
    dispositions = []
    for lane in lane_names:
        if not lane:
            continue
        lane_row = rows_by_lane.get(lane, {})
        lane_state = active_states.get(lane, {})
        status, blockers, operator_next_step = _classify_lane_disposition(lane_row, lane_state, promotion)
        dispositions.append(
            {
                "lane": lane,
                "disposition": status,
                "rows": lane_row.get("rows"),
                "priced": _lane_metric_value(lane_row, lane_state, "priced"),
                "profit_factor": _lane_metric_value(lane_row, lane_state, "profit_factor"),
                "avg_net_pnl_pct": _lane_metric_value(lane_row, lane_state, "avg_net_pnl_pct"),
                "source_decision": lane_row.get("decision") or _norm(lane_state.get("candidate_status")) or "missing_lane_row",
                "promotion_state": lane_state.get("promotion_state"),
                "candidate_status": lane_state.get("candidate_status"),
                "blockers": blockers,
                "operator_next_step": operator_next_step,
            }
        )
    counts = Counter(item["disposition"] for item in dispositions)
    unclassified = [
        item
        for item in dispositions
        if item.get("disposition") not in LANE_DISPOSITION_STATUSES
    ]
    return {
        "lane_disposition_status": "all_active_regular_lanes_classified_read_only"
        if not unclassified
        else "unclassified_lane_disposition_present",
        "allowed_statuses": list(LANE_DISPOSITION_STATUSES),
        "lane_count": len(dispositions),
        "status_counts": {status: counts.get(status, 0) for status in LANE_DISPOSITION_STATUSES},
        "unclassified_count": len(unclassified),
        "dispositions": dispositions,
        "live_policy_change": False,
    }


def _archived_quarantine_lanes(lane_quarantine_archive: dict[str, Any]) -> set[str]:
    summary = _as_dict(lane_quarantine_archive.get("summary"))
    if lane_quarantine_archive.get("status") != "lane_quarantine_archive_readback":
        return set()
    if bool(summary.get("live_policy_change")):
        return set()
    return {
        _norm(item.get("lane"))
        for item in _as_list(lane_quarantine_archive.get("archived_lanes"))
        if isinstance(item, dict)
        and _norm(item.get("archive_status")) == "archived_quarantine_lane"
        and _norm(item.get("lane"))
    }


def _annotate_lane_quarantine_archive(
    lane_dispositions: dict[str, Any],
    lane_quarantine_archive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    archived = _archived_quarantine_lanes(lane_quarantine_archive or {})
    dispositions = []
    quarantine_lanes = set()
    for item in _as_list(lane_dispositions.get("dispositions")):
        item = dict(_as_dict(item))
        if item.get("disposition") == "quarantine":
            lane = _norm(item.get("lane"))
            quarantine_lanes.add(lane)
            item["archive_status"] = "archived_quarantine_lane" if lane in archived else "unarchived_quarantine_lane"
        dispositions.append(item)
    unarchived = sorted(quarantine_lanes - archived)
    annotated = dict(lane_dispositions)
    annotated["dispositions"] = dispositions
    annotated["archived_quarantine_lane_count"] = len(quarantine_lanes & archived)
    annotated["unarchived_quarantine_lane_count"] = len(unarchived)
    annotated["unarchived_quarantine_lanes"] = unarchived
    return annotated


def _stale_candidate_archive(stale_candidate_archive: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(stale_candidate_archive.get("summary"))
    if stale_candidate_archive.get("status") != "stale_candidate_archive_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    return {
        "status": summary.get("overall_status"),
        "implementation_status": "built" if bool(summary.get("archive_complete")) else "built_collecting",
        "metrics": {
            "source_wait_or_archive_count": summary.get("source_wait_or_archive_count"),
            "archived_no_longer_matched_candidate_count": summary.get(
                "archived_no_longer_matched_candidate_count"
            ),
            "archive_exception_count": summary.get("archive_exception_count"),
            "archive_complete": summary.get("archive_complete"),
            "lane_counts": summary.get("lane_counts"),
            "ticker_counts": summary.get("ticker_counts"),
            "production_proof_ready_count": summary.get("production_proof_ready_count"),
        },
        "next_evidence_queue": _as_list(stale_candidate_archive.get("next_evidence_queue")),
    }


def _monthly_drift(cohort_health: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(cohort_health.get("summary"))
    recent_month = _norm(summary.get("recent_month"))
    lane_recent = [
        {"cohort": key, **_as_dict(value)}
        for key, value in _as_dict(cohort_health.get("lane_monthly")).items()
        if not recent_month or str(key).startswith(f"{recent_month}:")
    ]
    ticker_recent = [
        {"cohort": key, **_as_dict(value)}
        for key, value in _as_dict(cohort_health.get("ticker_monthly")).items()
        if not recent_month or str(key).startswith(f"{recent_month}:")
    ]
    ticker_recent.sort(
        key=lambda item: (
            _safe_float(item.get("avg_pnl_pct")) if _safe_float(item.get("avg_pnl_pct")) is not None else 999.0,
            -_safe_int(item.get("priced")),
        )
    )
    return {
        "overall_status": summary.get("overall_status"),
        "showcase_month": summary.get("showcase_month"),
        "showcase_month_summary": summary.get("showcase_month_summary"),
        "recent_month": summary.get("recent_month"),
        "recent_month_summary": summary.get("recent_month_summary"),
        "recent_week": summary.get("recent_week"),
        "recent_week_summary": summary.get("recent_week_summary"),
        "monthly": _as_dict(cohort_health.get("monthly")),
        "recent_lane_health": lane_recent,
        "recent_ticker_health": ticker_recent[:10],
        "recommended_actions": _as_list(cohort_health.get("recommended_actions")),
    }


def _worst_buckets(failure_modes: dict[str, Any]) -> dict[str, Any]:
    modes = _as_dict(failure_modes.get("failure_modes"))
    guardrails = _as_dict(failure_modes.get("guardrail_candidates") or failure_modes.get("pre_entry_guardrail_candidates"))
    return {
        "worst_ticker_clusters": _as_list(modes.get("worst_ticker_clusters"))[:12],
        "worst_playbook_ticker_clusters": _as_list(modes.get("worst_playbook_ticker_clusters"))[:12],
        "debit_pct_bucket_metrics": _as_list(modes.get("debit_pct_bucket_metrics")),
        "dte_bucket_metrics": _as_list(modes.get("dte_bucket_metrics")),
        "entry_debit_bucket_metrics": _as_list(modes.get("entry_debit_bucket_metrics")),
        "duplicate_exact_spread_groups": _as_list(modes.get("duplicate_exact_spread_groups"))[:10],
        "fill_degradation_bucket_metrics": [],
        "fill_degradation_status": "not_available_in_missed_pick_failure_modes",
        "debit_pct_gte_45_diagnostic": guardrails.get("debit_pct_gte_45_diagnostic"),
        "dte_gte_36_diagnostic": guardrails.get("dte_gte_36_diagnostic"),
    }


def _scenario_metrics(scenario: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(scenario.get("kept_metrics"))


def _classify_scenario(scenario: dict[str, Any]) -> tuple[str, list[str]]:
    status = _norm(scenario.get("status")).lower()
    metrics = _scenario_metrics(scenario)
    later = _as_dict(scenario.get("later_date_read"))
    pf = _safe_float(metrics.get("profit_factor"))
    avg = _safe_float(metrics.get("avg_net_pnl_pct"))
    unpriced = _safe_int(metrics.get("unpriced"))
    later_rows = _safe_int(later.get("later_date_rows"))
    survives_later = bool(later.get("survives_later_date_split"))
    lost_winners = _safe_int(scenario.get("lost_winner_count"))
    avoided_deep = _safe_int(scenario.get("avoided_deep_loss_count_lte_minus_50"))
    notes = [_norm(item).lower() for item in _as_list(scenario.get("notes"))]
    blockers: list[str] = []
    if "overfit" in status:
        blockers.append("overfit_status")
    if not bool(scenario.get("entry_time_only")):
        blockers.append("not_entry_time_only")
    if lost_winners > avoided_deep:
        blockers.append("winner_damage_exceeds_deep_losses_avoided")
    if later_rows < 10:
        blockers.append("thin_later_date_holdout")
    if not survives_later:
        blockers.append("later_date_holdout_not_passed")
    if unpriced > 0:
        blockers.append("unpriced_rows_present")
    if pf is None or pf < 1.2:
        blockers.append("profit_factor_below_paper_candidate_gate")
    if avg is None or avg <= 0:
        blockers.append("average_net_pnl_not_positive")
    if lost_winners > 0 or any("winner" in note and "damage" in note for note in notes):
        blockers.append("winner_damage_warning")
    if any(
        blocker
        in {
            "overfit_status",
            "not_entry_time_only",
            "winner_damage_exceeds_deep_losses_avoided",
            "thin_later_date_holdout",
            "later_date_holdout_not_passed",
        }
        for blocker in blockers
    ):
        return "reject_overfit", blockers
    paper_candidate_blockers = {
        "unpriced_rows_present",
        "profit_factor_below_paper_candidate_gate",
        "average_net_pnl_not_positive",
        "winner_damage_warning",
    }
    if not any(blocker in paper_candidate_blockers for blocker in blockers):
        return "paper_candidate_only", []
    return "diagnostic_retest_required", blockers


def _archived_rule_ids(rule_archive: dict[str, Any]) -> set[str]:
    summary = _as_dict(rule_archive.get("summary"))
    if rule_archive.get("status") != "overfit_rule_archive_readback":
        return set()
    if bool(summary.get("live_policy_change")):
        return set()
    return {
        _norm(rule.get("scenario_id"))
        for rule in _as_list(rule_archive.get("archived_rules"))
        if isinstance(rule, dict)
        and _norm(rule.get("archive_status")) == "archived_rejected_rule"
        and _norm(rule.get("scenario_id"))
    }


def _candidate_rule_table(filter_matrix: dict[str, Any], rule_archive: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    archived_ids = _archived_rule_ids(rule_archive or {})
    rows = []
    for scenario in _as_list(filter_matrix.get("scenarios")):
        if not isinstance(scenario, dict):
            continue
        classification, blockers = _classify_scenario(scenario)
        metrics = _scenario_metrics(scenario)
        later = _as_dict(scenario.get("later_date_read"))
        scenario_id = scenario.get("scenario_id")
        scenario_key = _norm(scenario_id)
        if classification == "reject_overfit":
            archive_status = "archived_rejected_rule" if scenario_key in archived_ids else "unarchived_rejected_rule"
        elif classification == "paper_candidate_only":
            archive_status = "active_paper_candidate"
        else:
            archive_status = "active_diagnostic_retest"
        rows.append(
            {
                "scenario_id": scenario_id,
                "source_status": scenario.get("status"),
                "classification": classification,
                "archive_status": archive_status,
                "classification_blockers": blockers,
                "entry_time_only": bool(scenario.get("entry_time_only")),
                "kept_count": scenario.get("kept_count"),
                "blocked_count": scenario.get("blocked_count"),
                "profit_factor": metrics.get("profit_factor"),
                "avg_net_pnl_pct": metrics.get("avg_net_pnl_pct"),
                "unpriced": metrics.get("unpriced"),
                "lost_winner_count": scenario.get("lost_winner_count"),
                "avoided_lte_minus_50": scenario.get("avoided_deep_loss_count_lte_minus_50"),
                "later_date_rows": later.get("later_date_rows"),
                "survives_later_date_split": bool(later.get("survives_later_date_split")),
                "promotion_ready": False,
            }
        )
    rows.sort(
        key=lambda item: (
            0 if item["classification"] == "paper_candidate_only" else 1 if item["classification"] == "diagnostic_retest_required" else 2,
            -(_safe_float(item.get("profit_factor")) or 0.0),
            -_safe_int(item.get("kept_count")),
        )
    )
    return rows


def _fill_attempt_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_rows = [row for row in rows if _norm(row.get("event_type")) == "candidate_shown"]
    fill_status_counts = Counter(_norm(row.get("fill_status")) or "unknown" for row in candidate_rows)
    fill_outcome_counts = Counter(_norm(row.get("fill_outcome")) or "unknown" for row in candidate_rows)
    status_values = [
        (_norm(row.get("fill_status")).lower(), _norm(row.get("fill_outcome")).lower())
        for row in candidate_rows
    ]
    no_fill_count = sum(
        1
        for status, outcome in status_values
        if status in {"no_fill", "not_filled", "not_filled_auto_track_skipped"}
        or outcome in {"no_fill", "not_filled", "not_filled_auto_track_skipped"}
        or "not_filled" in status
        or "no_fill" in status
        or "not_filled" in outcome
        or "no_fill" in outcome
    )
    not_submitted_count = sum(
        1
        for status, outcome in status_values
        if status in {"not_submitted", "not_submitted_auto_track_disabled"}
        or outcome in {"not_submitted", "not_submitted_auto_track_disabled"}
        or "not_submitted" in status
        or "not_submitted" in outcome
    )
    discipline_count = sum(1 for row in candidate_rows if isinstance(row.get("fill_discipline_snapshot"), dict))
    return {
        "row_count": len(rows),
        "candidate_shown_count": len(candidate_rows),
        "proof_live_exact_count": sum(
            1 for row in candidate_rows if _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
        ),
        "no_fill_count": no_fill_count,
        "not_submitted_count": not_submitted_count,
        "paper_fill_recorded_count": fill_outcome_counts.get("paper_fill_recorded", 0),
        "fill_discipline_snapshot_count": discipline_count,
        "fill_discipline_snapshot_coverage_pct": round((discipline_count / len(candidate_rows)) * 100, 2)
        if candidate_rows
        else 0.0,
        "top_alternative_count": sum(
            1 for row in candidate_rows if _as_list(row.get("top_alternatives")) or _as_list(row.get("top_spread_alternatives"))
        ),
        "fill_status_counts": dict(sorted(fill_status_counts.items())),
        "fill_outcome_counts": dict(sorted(fill_outcome_counts.items())),
    }


def _layer_by_slug(layer_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _norm(layer.get("slug")): layer
        for layer in _as_list(layer_stack.get("layers"))
        if isinstance(layer, dict) and _norm(layer.get("slug"))
    }


def _execution_realism(fill_summary: dict[str, Any], layer_stack: dict[str, Any]) -> dict[str, Any]:
    layers = _layer_by_slug(layer_stack)
    replay_gaps = {}
    for slug in (
        "top_spread_alternative_replay",
        "contract_replacement_exit_survivability",
        "minute_level_exit_quote_deterioration",
        "structure_specific_multileg_harness",
    ):
        layer = layers.get(slug, {})
        replay_gaps[slug] = {
            "gate_status": layer.get("gate_status"),
            "implementation_status": layer.get("implementation_status"),
            "blockers": list(layer.get("primary_blockers") or []),
            "metrics": _as_dict(layer.get("metrics")),
        }
    blockers = [
        slug
        for slug, item in replay_gaps.items()
        if item.get("gate_status") == "blocked" or _norm(item.get("implementation_status")).startswith("wired_")
    ]
    return {
        **fill_summary,
        "execution_realism_status": "blocked_replay_gaps" if blockers else "ready",
        "execution_realism_blockers": blockers,
        "replay_gap_flags": replay_gaps,
        "minute_exit_readiness": _as_dict(replay_gaps.get("minute_level_exit_quote_deterioration")).get("metrics") or {},
        "promotion_blocker": bool(blockers),
    }


def _risk_portfolio(open_risk: dict[str, Any], multilane: dict[str, Any], layer_stack: dict[str, Any]) -> dict[str, Any]:
    governor = _as_dict(open_risk.get("open_risk_governor"))
    quality_gate = _as_dict(multilane.get("quality_gate"))
    layers = _layer_by_slug(layer_stack)
    sizing = layers.get("risk_budget_sizing_replay", {})
    throttle = layers.get("portfolio_throttle_replay", {})
    quality_blockers = [str(item) for item in _as_list(quality_gate.get("blockers"))]
    blockers = []
    if governor.get("live_entry_allowed") is False:
        blockers.append("open_risk_governor_blocked")
    if _norm(quality_gate.get("overall_status") or quality_gate.get("status")) not in {"", "pass"}:
        blockers.extend([f"multilane:{item}" for item in quality_blockers] or ["multilane_quality_pending"])
    if sizing.get("gate_status") == "blocked":
        blockers.extend(_as_list(sizing.get("primary_blockers")) or ["risk_budget_sizing_replay_missing"])
    if throttle.get("gate_status") == "blocked":
        blockers.extend(_as_list(throttle.get("primary_blockers")) or ["portfolio_throttle_replay_blocked"])
    zero_bid_liquidity_blockers = [
        blocker
        for blocker in quality_blockers
        if any(token in blocker.lower() for token in ("zero_bid", "liquidity", "quote_coverage", "unpriced"))
    ]
    return {
        "open_risk_status": governor.get("status"),
        "live_entry_allowed": governor.get("live_entry_allowed"),
        "live_exact_negative_ids": governor.get("live_exact_negative_ids"),
        "open_risk_blockers": governor.get("blockers"),
        "multilane_quality_status": quality_gate.get("overall_status") or quality_gate.get("status"),
        "multilane_quality_blockers": quality_blockers,
        "zero_bid_liquidity_blockers": zero_bid_liquidity_blockers,
        "portfolio_throttle_status": throttle.get("gate_status"),
        "risk_budget_sizing_status": sizing.get("gate_status"),
        "risk_budget_sizing_implementation_status": sizing.get("implementation_status"),
        "risk_budget_sizing_blockers": _as_list(sizing.get("primary_blockers")),
        "risk_budget_sizing_metrics": _as_dict(sizing.get("metrics")),
        "risk_portfolio_status": "blocked" if blockers else "ready",
        "promotion_blockers": blockers,
    }


def _regime_stratified_replay_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(report.get("summary"))
    if report.get("status") != "regime_stratified_replay_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "regime_robust": False,
            "metrics": {},
            "next_evidence_queue": [],
        }
    market_context_status = _norm(summary.get("market_context_status"))
    regime_robust = bool(summary.get("regime_robust"))
    if regime_robust:
        implementation_status = "built_regime_robust"
    elif market_context_status != "complete":
        implementation_status = "built_context_blocked"
    else:
        implementation_status = "built_regime_failure"
    return {
        "status": summary.get("overall_status"),
        "implementation_status": implementation_status,
        "regime_robust": regime_robust,
        "metrics": {
            "eligible_replay_row_count": summary.get("eligible_replay_row_count"),
            "vix_missing_count": summary.get("vix_missing_count"),
            "spy50_missing_count": summary.get("spy50_missing_count"),
            "market_context_status": summary.get("market_context_status"),
            "evaluable_bucket_count": summary.get("evaluable_bucket_count"),
            "failing_bucket_count": summary.get("failing_bucket_count"),
            "branch_count": summary.get("branch_count"),
            "branch_bucket_count": summary.get("branch_bucket_count"),
            "minimum_bucket_n_for_robustness": summary.get("minimum_bucket_n_for_robustness"),
        },
        "next_evidence_queue": _as_list(report.get("next_evidence_queue")),
    }


def _autoresearch_search_effort(scoreboard: dict[str, Any]) -> dict[str, Any]:
    if not scoreboard or not scoreboard.get("evaluator_version"):
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
        }
    search_effort = _as_dict(scoreboard.get("search_effort"))
    metrics = _as_dict(scoreboard.get("metrics"))
    variants_searched = search_effort.get("variants_searched", metrics.get("variants_searched"))
    selection_adjusted_bar = search_effort.get("selection_adjusted_bar", metrics.get("selection_adjusted_bar"))
    formula = search_effort.get("selection_adjustment_formula", metrics.get("selection_adjustment_formula"))
    return {
        "status": "available",
        "implementation_status": "built_advisory",
        "metrics": {
            "strategy_family": search_effort.get("strategy_family", metrics.get("strategy_family")),
            "variant_id": search_effort.get("variant_id", metrics.get("variant_id")),
            "variants_searched": variants_searched,
            "selection_adjusted_bar": selection_adjusted_bar,
            "selection_adjusted_confidence": metrics.get("selection_adjusted_confidence"),
            "selection_adjustment_formula": formula,
            "selection_adjustment_metric": search_effort.get("selection_adjustment_metric", "pf_lb_5pct"),
            "pf_lb_5pct": metrics.get("pf_lb_5pct"),
            "statistical_confidence": metrics.get("statistical_confidence"),
            "diagnostic_only": True,
        },
    }


def _lane_outcome_replay(lane_outcome_replay: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(lane_outcome_replay.get("summary"))
    if lane_outcome_replay.get("status") != "lane_outcome_replay_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    return {
        "status": summary.get("overall_status"),
        "implementation_status": "built_collecting"
        if _safe_int(summary.get("missing_outcome_lane_count"))
        else "built",
        "metrics": {
            "active_lane_count": summary.get("active_lane_count"),
            "priced_outcome_lane_count": summary.get("priced_outcome_lane_count"),
            "missing_outcome_lane_count": summary.get("missing_outcome_lane_count"),
            "outcome_status_counts": summary.get("outcome_status_counts"),
        },
        "next_evidence_queue": _as_list(lane_outcome_replay.get("next_evidence_queue")),
    }


def _lane_scan_hypothesis_repair(lane_scan_hypothesis_repair: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(lane_scan_hypothesis_repair.get("summary"))
    if lane_scan_hypothesis_repair.get("status") != "lane_scan_hypothesis_repair_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    target_count = _safe_int(summary.get("target_no_signal_lane_count"))
    candidate_count = _safe_int(summary.get("predeclared_replacement_candidate_count"))
    missing_candidate_count = _safe_int(summary.get("missing_replacement_candidate_lane_count"))
    if target_count and (candidate_count or missing_candidate_count):
        implementation_status = "built_collecting"
    else:
        implementation_status = "built"
    return {
        "status": summary.get("overall_status"),
        "implementation_status": implementation_status,
        "metrics": {
            "target_no_signal_lane_count": summary.get("target_no_signal_lane_count"),
            "predeclared_replacement_candidate_count": summary.get(
                "predeclared_replacement_candidate_count"
            ),
            "predeclared_candidate_lane_count": summary.get("predeclared_candidate_lane_count"),
            "missing_replacement_candidate_lane_count": summary.get(
                "missing_replacement_candidate_lane_count"
            ),
            "proof_ready_replacement_candidate_count": summary.get(
                "proof_ready_replacement_candidate_count"
            ),
            "fresh_exact_scan_retest_row_count": summary.get("fresh_exact_scan_retest_row_count"),
            "true_lane_outcome_pnl_row_count": summary.get("true_lane_outcome_pnl_row_count"),
            "repair_status_counts": summary.get("repair_status_counts"),
        },
        "next_evidence_queue": _as_list(lane_scan_hypothesis_repair.get("next_evidence_queue")),
    }


def _exact_candidate_selection_repair(exact_candidate_selection_repair: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(exact_candidate_selection_repair.get("summary"))
    if exact_candidate_selection_repair.get("status") != "exact_candidate_selection_repair_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    return {
        "status": summary.get("overall_status"),
        "implementation_status": "built_collecting" if _safe_int(summary.get("target_date_count")) else "built",
        "metrics": {
            "target_lane_count": summary.get("target_lane_count"),
            "target_date_count": summary.get("target_date_count"),
            "target_signal_candidate_count": summary.get("target_signal_candidate_count"),
            "target_exact_candidate_count": summary.get("target_exact_candidate_count"),
            "exact_reject_reason_counts": summary.get("exact_reject_reason_counts"),
            "top_signal_tickers": summary.get("top_signal_tickers"),
        },
        "next_evidence_queue": _as_list(exact_candidate_selection_repair.get("next_evidence_queue")),
    }


def _chain_native_filter_relaxation_replay(chain_native_filter_relaxation_replay: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(chain_native_filter_relaxation_replay.get("summary"))
    if chain_native_filter_relaxation_replay.get("status") != "chain_native_filter_relaxation_replay_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    selected_count = _safe_int(summary.get("relaxed_selected_chain_native_entry_spread_count"))
    entry_quote_demand_count = _safe_int(summary.get("entry_quote_demand_count"))
    implementation_status = "built_collecting" if selected_count or entry_quote_demand_count else "built_blocked"
    return {
        "status": summary.get("overall_status"),
        "implementation_status": implementation_status,
        "metrics": {
            "target_lane_count": summary.get("target_lane_count"),
            "target_date_count": summary.get("target_date_count"),
            "target_signal_candidate_count": summary.get("target_signal_candidate_count"),
            "replay_signal_candidate_count": summary.get("replay_signal_candidate_count"),
            "scenario_count": summary.get("scenario_count"),
            "scenario_row_count": summary.get("scenario_row_count"),
            "current_selected_chain_native_entry_spread_count": summary.get(
                "current_selected_chain_native_entry_spread_count"
            ),
            "relaxed_selected_chain_native_entry_spread_count": summary.get(
                "relaxed_selected_chain_native_entry_spread_count"
            ),
            "entry_quote_demand_count": summary.get("entry_quote_demand_count"),
            "entry_quote_demand_tickers": summary.get("entry_quote_demand_tickers"),
            "scenario_status_counts": summary.get("scenario_status_counts"),
        },
        "next_evidence_queue": _as_list(chain_native_filter_relaxation_replay.get("next_evidence_queue")),
    }


def _chain_native_exit_outcome_replay(chain_native_exit_outcome_replay: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(chain_native_exit_outcome_replay.get("summary"))
    if chain_native_exit_outcome_replay.get("status") != "chain_native_exit_outcome_replay_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    priced = _safe_int(summary.get("priced_scenario_row_count"))
    demand_count = _safe_int(summary.get("missing_exit_quote_demand_count"))
    return {
        "status": summary.get("overall_status"),
        "implementation_status": "built_collecting" if priced or demand_count else "built_blocked",
        "metrics": {
            "selected_scenario_row_count": summary.get("selected_scenario_row_count"),
            "current_selected_scenario_row_count": summary.get("current_selected_scenario_row_count"),
            "relaxed_selected_scenario_row_count": summary.get("relaxed_selected_scenario_row_count"),
            "priced_scenario_row_count": summary.get("priced_scenario_row_count"),
            "priced_current_scenario_row_count": summary.get("priced_current_scenario_row_count"),
            "priced_relaxed_scenario_row_count": summary.get("priced_relaxed_scenario_row_count"),
            "missing_exit_quote_demand_count": summary.get("missing_exit_quote_demand_count"),
            "best_relaxed_scenario": summary.get("best_relaxed_scenario"),
            "latest_intraday_quote_date": summary.get("latest_intraday_quote_date"),
        },
        "next_evidence_queue": _as_list(chain_native_exit_outcome_replay.get("next_evidence_queue")),
    }


def _chain_native_relaxation_archive(chain_native_relaxation_archive: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(chain_native_relaxation_archive.get("summary"))
    if chain_native_relaxation_archive.get("status") != "chain_native_relaxation_archive_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
        }
    return {
        "status": summary.get("overall_status"),
        "implementation_status": "built" if bool(summary.get("archive_complete")) else "built_collecting",
        "metrics": {
            "source_exit_outcome_status": summary.get("source_exit_outcome_status"),
            "source_ready_for_archive": summary.get("source_ready_for_archive"),
            "branch_scenario_count": summary.get("branch_scenario_count"),
            "negative_branch_count": summary.get("negative_branch_count"),
            "archived_negative_branch_count": summary.get("archived_negative_branch_count"),
            "unarchived_negative_branch_count": summary.get("unarchived_negative_branch_count"),
            "current_scenario_count": summary.get("current_scenario_count"),
            "negative_current_scenario_count": summary.get("negative_current_scenario_count"),
            "archived_negative_current_scenario_count": summary.get("archived_negative_current_scenario_count"),
            "unarchived_negative_current_scenario_count": summary.get(
                "unarchived_negative_current_scenario_count"
            ),
            "relaxed_scenario_count": summary.get("relaxed_scenario_count"),
            "negative_relaxed_scenario_count": summary.get("negative_relaxed_scenario_count"),
            "archived_negative_relaxed_scenario_count": summary.get("archived_negative_relaxed_scenario_count"),
            "unarchived_negative_relaxed_scenario_count": summary.get("unarchived_negative_relaxed_scenario_count"),
            "archive_complete": summary.get("archive_complete"),
            "archive_requested_by_exit_outcome_replay": summary.get("archive_requested_by_exit_outcome_replay"),
        },
    }


def _exhausted_contract_archive(exhausted_contract_archive: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(exhausted_contract_archive.get("summary"))
    if exhausted_contract_archive.get("status") != "exhausted_contract_archive_readback":
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
        }
    implementation_status = (
        "built" if _safe_int(summary.get("archived_exhausted_contract_count")) > 0 else "built_collecting"
    )
    return {
        "status": summary.get("overall_status"),
        "implementation_status": implementation_status,
        "metrics": {
            "source_repair_burndown_status": summary.get("source_repair_burndown_status"),
            "source_ready_for_archive": summary.get("source_ready_for_archive"),
            "source_exhausted_current_source_target_count": summary.get(
                "source_exhausted_current_source_target_count"
            ),
            "archived_exhausted_contract_count": summary.get("archived_exhausted_contract_count"),
            "previous_archived_exhausted_contract_count": summary.get(
                "previous_archived_exhausted_contract_count"
            ),
            "newly_archived_exhausted_contract_count": summary.get(
                "newly_archived_exhausted_contract_count"
            ),
            "remaining_eligible_exhausted_contract_count": summary.get(
                "remaining_eligible_exhausted_contract_count"
            ),
            "archive_limit": summary.get("archive_limit"),
            "new_target_limit": summary.get("new_target_limit"),
            "min_attempt_count_required": summary.get("min_attempt_count_required"),
            "archive_complete_for_selected_limit": summary.get("archive_complete_for_selected_limit"),
        },
    }


def _execution_alternative_quote_import_plan(execution_alternative_quote_import_plan: dict[str, Any]) -> dict[str, Any]:
    status = _norm(execution_alternative_quote_import_plan.get("status"))
    summary = _as_dict(execution_alternative_quote_import_plan.get("summary"))
    if status not in {
        "execution_alternative_quote_import_plan_ready",
        "no_quote_demands_to_plan",
        "blocked_unparsed_quote_demands",
    }:
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    if status == "execution_alternative_quote_import_plan_ready":
        implementation_status = "built_collecting"
    elif status == "no_quote_demands_to_plan":
        implementation_status = "built"
    else:
        implementation_status = "built_blocked"
    return {
        "status": status,
        "implementation_status": implementation_status,
        "metrics": {
            "source_coverage_status": summary.get("source_coverage_status"),
            "source_quote_demand_manifest_status": summary.get("source_quote_demand_manifest_status"),
            "exact_contract_manifest_count": summary.get("exact_contract_manifest_count"),
            "unparsed_quote_demand_count": summary.get("unparsed_quote_demand_count"),
            "command_group_count": summary.get("command_group_count"),
            "entry_quote_demand_count": summary.get("entry_quote_demand_count"),
            "exit_quote_demand_count": summary.get("exit_quote_demand_count"),
            "quote_dates": summary.get("quote_dates"),
            "underlyings": summary.get("underlyings"),
            "operator_command_status": summary.get("operator_command_status"),
        },
        "next_evidence_queue": _as_list(execution_alternative_quote_import_plan.get("next_evidence_queue")),
    }


def _minute_exit_quote_import_plan(minute_exit_quote_import_plan: dict[str, Any]) -> dict[str, Any]:
    status = _norm(minute_exit_quote_import_plan.get("status"))
    summary = _as_dict(minute_exit_quote_import_plan.get("summary"))
    if status not in {
        "minute_exit_quote_import_plan_ready_engine_blocked",
        "no_minute_exit_quote_seeds_to_plan",
        "blocked_unparsed_minute_exit_quote_demands",
        "blocked_missing_inputs",
        "invalid_live_policy_change",
    }:
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "next_evidence_queue": [],
        }
    if status == "minute_exit_quote_import_plan_ready_engine_blocked":
        implementation_status = "built_collecting"
    elif status == "no_minute_exit_quote_seeds_to_plan":
        implementation_status = "built"
    else:
        implementation_status = "built_blocked"
    return {
        "status": status,
        "implementation_status": implementation_status,
        "metrics": {
            "source_readiness_status": summary.get("source_readiness_status"),
            "source_overall_status": summary.get("source_overall_status"),
            "source_entry_seed_ready_count": summary.get("source_entry_seed_ready_count"),
            "source_position_seed_ready_count": summary.get("source_position_seed_ready_count"),
            "source_true_minute_exit_pnl_count": summary.get("source_true_minute_exit_pnl_count"),
            "source_minute_exit_replay_engine_status": summary.get("source_minute_exit_replay_engine_status"),
            "source_minute_quote_coverage_status": summary.get("source_minute_quote_coverage_status"),
            "exact_contract_manifest_count": summary.get("exact_contract_manifest_count"),
            "unparsed_quote_demand_count": summary.get("unparsed_quote_demand_count"),
            "command_group_count": summary.get("command_group_count"),
            "position_linked_quote_demand_count": summary.get("position_linked_quote_demand_count"),
            "entry_only_quote_demand_count": summary.get("entry_only_quote_demand_count"),
            "quote_dates": summary.get("quote_dates"),
            "underlyings": summary.get("underlyings"),
            "operator_command_status": summary.get("operator_command_status"),
            "replay_pnl_status": summary.get("replay_pnl_status"),
        },
        "next_evidence_queue": _as_list(minute_exit_quote_import_plan.get("next_evidence_queue")),
    }


def _open_risk_resolution_plan(open_risk_resolution_plan: dict[str, Any]) -> dict[str, Any]:
    status = _norm(open_risk_resolution_plan.get("status"))
    summary = _as_dict(open_risk_resolution_plan.get("summary"))
    if status not in {
        "open_risk_resolution_plan_ready_blocked_for_market_window",
        "open_risk_resolution_plan_clear",
        "blocked_missing_inputs",
        "invalid_live_policy_change",
    }:
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "plan_rows": [],
            "next_evidence_queue": [],
        }
    if status == "open_risk_resolution_plan_ready_blocked_for_market_window":
        implementation_status = "built_collecting"
    elif status == "open_risk_resolution_plan_clear":
        implementation_status = "built"
    else:
        implementation_status = "built_blocked"
    return {
        "status": status,
        "implementation_status": implementation_status,
        "metrics": {
            "source_open_risk_status": summary.get("source_open_risk_status"),
            "live_entry_allowed": summary.get("live_entry_allowed"),
            "live_exact_negative_count": summary.get("live_exact_negative_count"),
            "live_exact_negative_ids": summary.get("live_exact_negative_ids"),
            "open_position_row_count": summary.get("open_position_row_count"),
            "open_position_negative_count": summary.get("open_position_negative_count"),
            "open_position_avg_pnl_pct": summary.get("open_position_avg_pnl_pct"),
            "open_position_median_pnl_pct": summary.get("open_position_median_pnl_pct"),
            "plan_row_count": summary.get("plan_row_count"),
            "market_window_required_count": summary.get("market_window_required_count"),
            "live_exact_plan_row_count": summary.get("live_exact_plan_row_count"),
            "display_only_sell_count": summary.get("display_only_sell_count"),
            "action_counts": summary.get("action_counts"),
            "operator_plan_status": summary.get("operator_plan_status"),
        },
        "plan_rows": _as_list(open_risk_resolution_plan.get("plan_rows")),
        "next_evidence_queue": _as_list(open_risk_resolution_plan.get("next_evidence_queue")),
    }


def _fill_attempt_evidence_capture_plan(fill_attempt_evidence_capture_plan: dict[str, Any]) -> dict[str, Any]:
    status = _norm(fill_attempt_evidence_capture_plan.get("status"))
    summary = _as_dict(fill_attempt_evidence_capture_plan.get("summary"))
    if status not in {
        "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection",
        "fill_attempt_evidence_capture_plan_clear",
        "blocked_missing_inputs",
        "invalid_live_policy_change",
    }:
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "plan_rows": [],
            "next_evidence_queue": [],
        }
    if status == "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection":
        implementation_status = "built_collecting"
    elif status == "fill_attempt_evidence_capture_plan_clear":
        implementation_status = "built"
    else:
        implementation_status = "built_blocked"
    return {
        "status": status,
        "implementation_status": implementation_status,
        "metrics": {
            "source_candidate_ledger_operating_status": summary.get("source_candidate_ledger_operating_status"),
            "source_fill_attempt_rows": summary.get("source_fill_attempt_rows"),
            "source_missing_fill_attempt_action_count": summary.get("source_missing_fill_attempt_action_count"),
            "plan_row_count": summary.get("plan_row_count"),
            "missing_fill_attempt_evidence_count": summary.get("missing_fill_attempt_evidence_count"),
            "ledger_stale_fill_attempt_logged_count": summary.get("ledger_stale_fill_attempt_logged_count"),
            "market_window_required_count": summary.get("market_window_required_count"),
            "scan_dates": summary.get("scan_dates"),
            "lane_counts": summary.get("lane_counts"),
            "ticker_counts": summary.get("ticker_counts"),
            "operator_plan_status": summary.get("operator_plan_status"),
        },
        "plan_rows": _as_list(fill_attempt_evidence_capture_plan.get("plan_rows")),
        "next_evidence_queue": _as_list(fill_attempt_evidence_capture_plan.get("next_evidence_queue")),
    }


def _suggested_trade_review_plan(suggested_trade_review_plan: dict[str, Any]) -> dict[str, Any]:
    status = _norm(suggested_trade_review_plan.get("status"))
    summary = _as_dict(suggested_trade_review_plan.get("summary"))
    if status not in {
        "suggested_trade_review_plan_ready_blocked_for_market_window",
        "suggested_trade_review_plan_clear",
        "blocked_missing_inputs",
        "invalid_live_policy_change",
    }:
        return {
            "status": "missing_or_unavailable",
            "implementation_status": "missing",
            "metrics": {},
            "plan_rows": [],
            "next_evidence_queue": [],
        }
    if status == "suggested_trade_review_plan_ready_blocked_for_market_window":
        implementation_status = "built_collecting"
    elif status == "suggested_trade_review_plan_clear":
        implementation_status = "built"
    else:
        implementation_status = "built_blocked"
    return {
        "status": status,
        "implementation_status": implementation_status,
        "metrics": {
            "open_suggested_trade_rows": summary.get("open_suggested_trade_rows"),
            "attention_trade_count": summary.get("attention_trade_count"),
            "close_risk_trade_count": summary.get("close_risk_trade_count"),
            "stale_or_missing_review_trade_count": summary.get("stale_or_missing_review_trade_count"),
            "missing_review_count": summary.get("missing_review_count"),
            "stale_review_count": summary.get("stale_review_count"),
            "executable_close_ready_count": summary.get("executable_close_ready_count"),
            "non_executable_close_risk_count": summary.get("non_executable_close_risk_count"),
            "plan_row_count": summary.get("plan_row_count"),
            "market_window_required_count": summary.get("market_window_required_count"),
            "source_action_counts": summary.get("source_action_counts"),
            "source_evidence_counts": summary.get("source_evidence_counts"),
            "operator_plan_status": summary.get("operator_plan_status"),
        },
        "plan_rows": _as_list(suggested_trade_review_plan.get("plan_rows")),
        "next_evidence_queue": _as_list(suggested_trade_review_plan.get("next_evidence_queue")),
    }


def _chain_native_negative_relaxation_archived(chain_native_relaxation_archive: dict[str, Any]) -> bool:
    summary = _as_dict(chain_native_relaxation_archive.get("summary"))
    if chain_native_relaxation_archive.get("status") != "chain_native_relaxation_archive_readback":
        return False
    if bool(summary.get("live_policy_change")):
        return False
    return bool(summary.get("archive_complete")) and _safe_int(
        summary.get("archived_negative_relaxed_scenario_count")
    ) > 0


def _all_chain_native_relaxation_branches_archived(chain_native_relaxation_archive: dict[str, Any]) -> bool:
    summary = _as_dict(chain_native_relaxation_archive.get("summary"))
    if not _chain_native_negative_relaxation_archived(chain_native_relaxation_archive):
        return False
    relaxed_count = _safe_int(summary.get("relaxed_scenario_count"))
    negative_count = _safe_int(summary.get("negative_relaxed_scenario_count"))
    return relaxed_count > 0 and negative_count == relaxed_count


def _oracle_ceiling() -> dict[str, Any]:
    return {
        "oracle_ceiling_status": "not_available_replay_gap",
        "trusted_mfe_mae_artifact": None,
        "promotion_allowed": False,
        "notes": [
            "V1 does not synthesize maximum possible P&L.",
            "Any future MFE/MAE or best-exit artifact must use trusted exact OPRA/NBBO evidence and remain non-promotable until converted into an entry-time-only rule.",
        ],
    }


def _promotion_gate(reports: dict[str, dict[str, Any]], risk: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    ledger_summary = _as_dict(reports["candidate_ledger"].get("summary"))
    walkforward_decision = _as_dict(reports["entry_filter_walkforward"].get("decision_summary"))
    point_decision = _as_dict(reports["entry_filter_point_in_time"].get("decision_summary"))
    paper_gate = _as_dict(reports["entry_filter_paper_monitor"].get("gate")) or _as_dict(
        reports["entry_filter_paper_monitor"].get("summary")
    )
    circuit_summary = _as_dict(reports["current_policy_circuit_breaker"].get("summary"))
    lane_summary = _as_dict(reports["lane_promotion_state"].get("summary"))
    layer_summary = _as_dict(reports["profitability_layer_stack"].get("summary"))
    blockers: list[str] = []
    if _safe_int(ledger_summary.get("exact_realized_pnl_count")) == 0:
        blockers.append("no_exact_realized_pnl_rows")
    if _safe_int(ledger_summary.get("paper_probation_bridge_count")) > 0:
        blockers.append("fresh_exact_paper_rows_still_collecting")
    if _norm(walkforward_decision.get("status")) not in {"pass", "passed", "promotion_ready"}:
        blockers.append("entry_filter_walkforward_not_passed")
    if _norm(point_decision.get("status")) not in {"pass", "passed", "promotion_ready"}:
        blockers.append("point_in_time_replay_not_passed")
    if _norm(paper_gate.get("status")) not in {"pass", "passed", "promotion_ready"}:
        blockers.append("paper_monitor_not_passed")
    if circuit_summary.get("breaker_active") or _norm(circuit_summary.get("overall_status")).startswith("paper_only"):
        blockers.append("current_policy_circuit_breaker_active")
    if _safe_int(lane_summary.get("live_validation_lane_count")) == 0:
        blockers.append("no_live_validation_lanes")
    if _safe_int(layer_summary.get("blocked_or_collecting_layer_count")) > 0:
        blockers.append("profitability_layer_stack_blocked_or_collecting")
    blockers.extend(risk.get("promotion_blockers") or [])
    if execution.get("promotion_blocker"):
        blockers.extend([f"execution:{item}" for item in execution.get("execution_realism_blockers") or []])
    return {
        "promotion_ready": False if blockers else True,
        "status": "blocked" if blockers else "ready_for_review",
        "blockers": sorted(set(str(item) for item in blockers if item)),
    }


def _next_evidence_queue(
    *,
    candidate_ledger: dict[str, Any],
    stale_candidate_archive: dict[str, Any],
    candidate_rules: list[dict[str, Any]],
    lane_dispositions: dict[str, Any],
    lane_outcome_replay: dict[str, Any],
    lane_scan_hypothesis_repair: dict[str, Any],
    exact_candidate_selection_repair: dict[str, Any],
    chain_native_filter_relaxation_replay: dict[str, Any],
    chain_native_exit_outcome_replay: dict[str, Any],
    chain_native_relaxation_archive: dict[str, Any],
    execution_alternative_quote_import_plan: dict[str, Any],
    minute_exit_quote_import_plan: dict[str, Any],
    open_risk_resolution_plan: dict[str, Any],
    fill_attempt_evidence_capture_plan: dict[str, Any],
    suggested_trade_review_plan: dict[str, Any],
    execution: dict[str, Any],
    risk: dict[str, Any],
    layer_stack: dict[str, Any],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    open_risk_plan_ready = (
        _norm(open_risk_resolution_plan.get("status"))
        == "open_risk_resolution_plan_ready_blocked_for_market_window"
        and not bool(open_risk_resolution_plan.get("live_policy_change"))
    )
    fill_attempt_plan_ready = (
        _norm(fill_attempt_evidence_capture_plan.get("status"))
        == "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection"
        and not bool(fill_attempt_evidence_capture_plan.get("live_policy_change"))
    )
    suggested_trade_plan_ready = (
        _norm(suggested_trade_review_plan.get("status"))
        == "suggested_trade_review_plan_ready_blocked_for_market_window"
        and not bool(suggested_trade_review_plan.get("live_policy_change"))
    )
    stale_candidate_archive_complete = (
        _norm(stale_candidate_archive.get("status")) == "stale_candidate_archive_readback"
        and bool(_as_dict(stale_candidate_archive.get("summary")).get("archive_complete"))
        and not bool(stale_candidate_archive.get("live_policy_change"))
    )
    for item in _as_list(candidate_ledger.get("next_evidence_queue")):
        if not isinstance(item, dict):
            continue
        action = _norm(item.get("next_evidence_action") or item.get("action"))
        if open_risk_plan_ready and action in OPEN_RISK_RESOLUTION_PLAN_REPLACED_ACTIONS:
            continue
        if fill_attempt_plan_ready and action in FILL_ATTEMPT_CAPTURE_PLAN_REPLACED_ACTIONS:
            continue
        if suggested_trade_plan_ready and action in SUGGESTED_TRADE_REVIEW_PLAN_REPLACED_ACTIONS:
            continue
        if stale_candidate_archive_complete and action in STALE_CANDIDATE_ARCHIVE_REPLACED_ACTIONS:
            continue
        queue.append(
            {
                "source": "candidate_outcome_ledger",
                "priority": _safe_int(item.get("action_priority") if item.get("action_priority") is not None else item.get("priority")),
                "action": action,
                "count": item.get("count"),
                "reason": item.get("action_reason") or action,
                "operator_next_step": item.get("operator_next_step"),
            }
        )
    disposition_counts = _as_dict(lane_dispositions.get("status_counts"))
    unarchived_quarantine_count = _safe_int(
        lane_dispositions.get("unarchived_quarantine_lane_count")
        if lane_dispositions.get("unarchived_quarantine_lane_count") is not None
        else disposition_counts.get("quarantine")
    )
    if unarchived_quarantine_count:
        queue.append(
            {
                "source": "lane_disposition",
                "priority": 3,
                "action": "record_lane_quarantine_disposition",
                "count": unarchived_quarantine_count,
                "reason": "negative_lane_economics_require_diagnostic_no_chase_status",
                "operator_next_step": "Keep quarantined lanes diagnostic until they earn back through frozen entry-time retests.",
            }
        )
    if _safe_int(disposition_counts.get("paper_shadow")):
        queue.append(
            {
                "source": "lane_disposition",
                "priority": 4,
                "action": "collect_paper_shadow_exact_evidence",
                "count": disposition_counts.get("paper_shadow"),
                "reason": "profitable_but_not_promotable_lane_needs_fresh_exact_paper_evidence",
                "operator_next_step": "Collect exact paper entries and exact realized exits for paper-shadow lanes.",
            }
        )
    if _safe_int(disposition_counts.get("retest")):
        queue.append(
            {
                "source": "lane_disposition",
                "priority": 5,
                "action": "retest_lane",
                "count": disposition_counts.get("retest"),
                "reason": "lane_economics_are_not_profitable_but_not_sufficiently_severe_for_archive",
                "operator_next_step": "Freeze entry-time-only retests and require later-date/fresh-paper evidence.",
            }
        )
    lane_outcome_status = _norm(lane_outcome_replay.get("status"))
    lane_outcome_built = lane_outcome_status == "lane_outcome_replay_readback"
    lane_scan_repair_built = (
        _norm(lane_scan_hypothesis_repair.get("status")) == "lane_scan_hypothesis_repair_readback"
        and not bool(lane_scan_hypothesis_repair.get("live_policy_change"))
    )
    exact_repair_built = exact_candidate_selection_repair.get("status") == "exact_candidate_selection_repair_readback"
    chain_relaxation_built = (
        chain_native_filter_relaxation_replay.get("status") == "chain_native_filter_relaxation_replay_readback"
    )
    chain_exit_built = chain_native_exit_outcome_replay.get("status") == "chain_native_exit_outcome_replay_readback"
    chain_negative_relaxation_archived = _chain_native_negative_relaxation_archived(
        chain_native_relaxation_archive
    )
    all_chain_relaxations_archived = _all_chain_native_relaxation_branches_archived(
        chain_native_relaxation_archive
    )
    execution_quote_plan_ready = (
        _norm(execution_alternative_quote_import_plan.get("status"))
        == "execution_alternative_quote_import_plan_ready"
        and not bool(execution_alternative_quote_import_plan.get("live_policy_change"))
    )
    minute_exit_quote_plan_ready = (
        _norm(minute_exit_quote_import_plan.get("status"))
        == "minute_exit_quote_import_plan_ready_engine_blocked"
        and not bool(minute_exit_quote_import_plan.get("live_policy_change"))
    )
    if _safe_int(disposition_counts.get("needs_replay_engine")) and not lane_outcome_built:
        queue.append(
            {
                "source": "lane_disposition",
                "priority": 7,
                "action": "build_lane_outcome_replay",
                "count": disposition_counts.get("needs_replay_engine"),
                "reason": "active_regular_lanes_have_no_monthly_exact_outcome_economics",
                "operator_next_step": "Build or refresh exact outcome replay before tuning these lanes.",
            }
        )
    if risk.get("live_entry_allowed") is False and not open_risk_plan_ready:
        queue.append(
            {
                "source": "monthly_profitability_audit",
                "priority": 0,
                "action": "resolve_open_risk",
                "count": len(_as_list(risk.get("live_exact_negative_ids"))),
                "reason": "open_risk_governor_blocks_promotion_and_live_entries",
                "operator_next_step": "Refresh exact open-risk/exit evidence before considering new live-validation work.",
            }
        )
    if open_risk_plan_ready:
        for item in _as_list(open_risk_resolution_plan.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            queue.append(
                {
                    "source": "open_risk_resolution_plan",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the open-risk resolution plan during the next fresh executable quote window.",
                }
            )
    if fill_attempt_plan_ready:
        for item in _as_list(fill_attempt_evidence_capture_plan.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            queue.append(
                {
                    "source": "fill_attempt_evidence_capture_plan",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the fill-attempt capture plan during the next fresh selection window.",
                }
            )
    if suggested_trade_plan_ready:
        for item in _as_list(suggested_trade_review_plan.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            queue.append(
                {
                    "source": "suggested_trade_review_plan",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the suggested-trade review plan during the next fresh executable quote window.",
                }
            )
    rejected = [
        rule
        for rule in candidate_rules
        if rule["classification"] == "reject_overfit" and rule.get("archive_status") != "archived_rejected_rule"
    ]
    if rejected:
        queue.append(
            {
                "source": "monthly_profitability_audit",
                "priority": 6,
                "action": "archive_overfit_rule",
                "count": len(rejected),
                "reason": "candidate_rules_failed_overfit_or_winner_damage_checks",
                "operator_next_step": "Keep rejected rules as diagnostics; do not promote them without a frozen retest and stronger holdout.",
            }
        )
    diagnostic = [rule for rule in candidate_rules if rule["classification"] == "diagnostic_retest_required"]
    if diagnostic:
        queue.append(
            {
                "source": "monthly_profitability_audit",
                "priority": 5,
                "action": "retest_filter",
                "count": len(diagnostic),
                "reason": "candidate_rules_need_later_point_in_time_or_fresh_paper_retest",
                "operator_next_step": "Freeze candidate rules before holdout; route all surviving ideas to paper/probation only.",
            }
        )
    if execution.get("promotion_blocker"):
        queue.append(
            {
                "source": "monthly_profitability_audit",
                "priority": 4,
                "action": "collect_fresh_paper_rows",
                "count": execution.get("proof_live_exact_count"),
                "reason": "execution_realism_is_not_sufficient_for_promotion",
                "operator_next_step": "Collect proof-live exact paper attempts with fill discipline, top alternatives, and exact exits.",
            }
        )
    if lane_outcome_built:
        for item in _as_list(lane_outcome_replay.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            if exact_repair_built and item.get("action") == "repair_chain_native_exact_candidate_selection":
                continue
            if lane_scan_repair_built and item.get("action") == "build_or_repair_lane_scan_hypothesis_before_pnl_replay":
                continue
            queue.append(
                {
                    "source": "lane_outcome_replay",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": "Use the lane outcome replay to repair scan/exact-candidate coverage before tuning no-outcome lanes.",
                }
            )
    if exact_repair_built:
        for item in _as_list(exact_candidate_selection_repair.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            if chain_relaxation_built and item.get("action") == "build_chain_native_filter_relaxation_replay":
                continue
            queue.append(
                {
                    "source": "exact_candidate_selection_repair",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the exact-candidate repair report to target chain-native filter attribution before policy tuning.",
                }
            )
    if chain_relaxation_built:
        for item in _as_list(chain_native_filter_relaxation_replay.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            if chain_exit_built and item.get("action") == "build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates":
                continue
            if (
                all_chain_relaxations_archived
                and item.get("action") == "validate_chain_native_relaxation_on_later_holdout"
            ):
                continue
            queue.append(
                {
                    "source": "chain_native_filter_relaxation_replay",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the chain-native relaxation replay readback before any policy discussion.",
                }
            )
    if chain_exit_built:
        for item in _as_list(chain_native_exit_outcome_replay.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            if (
                chain_negative_relaxation_archived
                and item.get("action") == "archive_negative_chain_native_relaxation_branch"
            ):
                continue
            queue.append(
                {
                    "source": "chain_native_exit_outcome_replay",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Use the chain-native exit outcome replay before any policy discussion.",
                }
            )
    if execution_quote_plan_ready:
        for item in _as_list(execution_alternative_quote_import_plan.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            queue.append(
                {
                    "source": "execution_alternative_quote_import_plan",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Run the read-only quote import plan commands, then rerun execution-alternative coverage.",
                }
            )
    if minute_exit_quote_plan_ready:
        for item in _as_list(minute_exit_quote_import_plan.get("next_evidence_queue")):
            if not isinstance(item, dict):
                continue
            queue.append(
                {
                    "source": "minute_exit_quote_import_plan",
                    "priority": _safe_int(item.get("priority")),
                    "action": item.get("action"),
                    "count": item.get("count"),
                    "reason": item.get("reason"),
                    "operator_next_step": item.get("operator_next_step")
                    or "Run the read-only minute-exit quote import plan commands, then rerun minute readiness.",
                }
            )
    layers = _layer_by_slug(layer_stack)
    for slug, action in REPLAY_GAP_LAYER_ACTIONS.items():
        layer = layers.get(slug, {})
        if not layer:
            continue
        if execution_quote_plan_ready and action in {
            "build_top_spread_alternative_replay",
            "build_contract_replacement_replay",
        }:
            continue
        if minute_exit_quote_plan_ready and action == "build_minute_exit_replay":
            continue
        if layer.get("gate_status") == "blocked" or _norm(layer.get("implementation_status")).startswith("wired_"):
            queue.append(
                {
                    "source": "profitability_layer_stack",
                    "priority": 7,
                    "action": action,
                    "count": 1,
                    "reason": ", ".join(str(item) for item in _as_list(layer.get("primary_blockers"))) or "replay_gap",
                    "operator_next_step": layer.get("next_action"),
                }
            )
    queue.sort(key=lambda item: (_safe_int(item.get("priority")), _norm(item.get("action"))))
    return queue


def build_report(
    *,
    artifact_paths: dict[str, Path] | None = None,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = dict(DEFAULT_ARTIFACT_PATHS)
    if artifact_paths:
        paths.update(artifact_paths)
    else:
        paths.update(DEFAULT_OPTIONAL_ARTIFACT_PATHS)
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], inputs[key] = _load_json(path)
    fill_rows, fill_meta = _load_jsonl(fill_attempts_path)
    inputs["fill_attempts"] = fill_meta

    missing_required = [
        key for key in REQUIRED_ARTIFACT_KEYS if inputs.get(key, {}).get("status") != "loaded"
    ]
    if fill_meta.get("status") != "loaded":
        missing_required.append("fill_attempts")
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())

    lane_leaderboard = _lane_leaderboard(reports["missed_picks_failure_modes"])
    monthly_drift = _monthly_drift(reports["current_policy_cohort_health"])
    worst_buckets = _worst_buckets(reports["missed_picks_failure_modes"])
    candidate_rules = _candidate_rule_table(
        reports["missed_picks_filter_matrix"],
        reports.get("overfit_rule_archive"),
    )
    fill_summary = _fill_attempt_summary(fill_rows)
    execution = _execution_realism(fill_summary, reports["profitability_layer_stack"])
    risk = _risk_portfolio(reports["open_risk"], reports["multilane_portfolio"], reports["profitability_layer_stack"])
    stale_archive = _stale_candidate_archive(reports.get("stale_candidate_archive", {}))
    lane_outcome = _lane_outcome_replay(reports.get("lane_outcome_replay", {}))
    lane_scan_repair = _lane_scan_hypothesis_repair(reports.get("lane_scan_hypothesis_repair", {}))
    exact_repair = _exact_candidate_selection_repair(reports.get("exact_candidate_selection_repair", {}))
    chain_relaxation = _chain_native_filter_relaxation_replay(
        reports.get("chain_native_filter_relaxation_replay", {})
    )
    chain_exit_outcome = _chain_native_exit_outcome_replay(reports.get("chain_native_exit_outcome_replay", {}))
    chain_relaxation_archive = _chain_native_relaxation_archive(
        reports.get("chain_native_relaxation_archive", {})
    )
    exhausted_contract_archive = _exhausted_contract_archive(
        reports.get("exhausted_contract_archive", {})
    )
    execution_quote_plan = _execution_alternative_quote_import_plan(
        reports.get("execution_alternative_quote_import_plan", {})
    )
    minute_exit_quote_plan = _minute_exit_quote_import_plan(
        reports.get("minute_exit_quote_import_plan", {})
    )
    open_risk_plan = _open_risk_resolution_plan(reports.get("open_risk_resolution_plan", {}))
    fill_attempt_plan = _fill_attempt_evidence_capture_plan(
        reports.get("fill_attempt_evidence_capture_plan", {})
    )
    suggested_trade_plan = _suggested_trade_review_plan(
        reports.get("suggested_trade_review_plan", {})
    )
    regime_stratification = _regime_stratified_replay_report(
        reports.get("regime_stratified_replay_report", {})
    )
    autoresearch_search_effort = _autoresearch_search_effort(
        reports.get("regular_options_autoresearch_scoreboard", {})
    )
    scheduled_scan = _scheduled_scan_health(
        reports.get("scheduled_scan_heartbeat", {}),
        as_of_utc=generated_at_utc,
    )
    oracle = _oracle_ceiling()
    promotion = _promotion_gate(reports, risk, execution)
    lane_dispositions = _annotate_lane_quarantine_archive(
        _lane_dispositions(lane_leaderboard, reports["lane_promotion_state"], promotion),
        reports.get("lane_quarantine_archive"),
    )
    next_queue = _next_evidence_queue(
        candidate_ledger=reports["candidate_ledger"],
        stale_candidate_archive=reports.get("stale_candidate_archive", {}),
        candidate_rules=candidate_rules,
        lane_dispositions=lane_dispositions,
        lane_outcome_replay=reports.get("lane_outcome_replay", {}),
        lane_scan_hypothesis_repair=reports.get("lane_scan_hypothesis_repair", {}),
        exact_candidate_selection_repair=reports.get("exact_candidate_selection_repair", {}),
        chain_native_filter_relaxation_replay=reports.get("chain_native_filter_relaxation_replay", {}),
        chain_native_exit_outcome_replay=reports.get("chain_native_exit_outcome_replay", {}),
        chain_native_relaxation_archive=reports.get("chain_native_relaxation_archive", {}),
        execution_alternative_quote_import_plan=reports.get("execution_alternative_quote_import_plan", {}),
        minute_exit_quote_import_plan=reports.get("minute_exit_quote_import_plan", {}),
        open_risk_resolution_plan=reports.get("open_risk_resolution_plan", {}),
        fill_attempt_evidence_capture_plan=reports.get("fill_attempt_evidence_capture_plan", {}),
        suggested_trade_review_plan=reports.get("suggested_trade_review_plan", {}),
        execution=execution,
        risk=risk,
        layer_stack=reports["profitability_layer_stack"],
    )

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "monthly_profitability_readback"
        overall_status = "profitability_iteration_ready_blocked_for_promotion"

    baseline = _as_dict(reports["missed_picks_filter_matrix"].get("baseline_metrics"))
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_monthly_all_lanes_profitability_command_center",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "missing_required_inputs": missing_required,
            "lane_count": len(lane_leaderboard),
            "candidate_rule_count": len(candidate_rules),
            "lane_disposition_status": lane_dispositions.get("lane_disposition_status"),
            "lane_disposition_counts": lane_dispositions.get("status_counts"),
            "lane_disposition_unclassified_count": lane_dispositions.get("unclassified_count"),
            "archived_quarantine_lane_count": lane_dispositions.get("archived_quarantine_lane_count"),
            "unarchived_quarantine_lane_count": lane_dispositions.get("unarchived_quarantine_lane_count"),
            "paper_candidate_rule_count": sum(1 for rule in candidate_rules if rule["classification"] == "paper_candidate_only"),
            "reject_overfit_rule_count": sum(1 for rule in candidate_rules if rule["classification"] == "reject_overfit"),
            "archived_reject_overfit_rule_count": sum(
                1
                for rule in candidate_rules
                if rule["classification"] == "reject_overfit" and rule.get("archive_status") == "archived_rejected_rule"
            ),
            "unarchived_reject_overfit_rule_count": sum(
                1
                for rule in candidate_rules
                if rule["classification"] == "reject_overfit" and rule.get("archive_status") != "archived_rejected_rule"
            ),
            "baseline_untracked_rows": baseline.get("rows"),
            "baseline_profit_factor": baseline.get("profit_factor"),
            "baseline_avg_net_pnl_pct": baseline.get("avg_net_pnl_pct"),
            "recent_month": monthly_drift.get("recent_month"),
            "recent_month_status": _as_dict(monthly_drift.get("recent_month_summary")).get("health_status"),
            "execution_realism_status": execution.get("execution_realism_status"),
            "risk_portfolio_status": risk.get("risk_portfolio_status"),
            "promotion_gate_status": promotion.get("status"),
            "promotion_ready": promotion.get("promotion_ready"),
            "promotion_blocker_count": len(promotion.get("blockers") or []),
            "open_risk_status": risk.get("open_risk_status"),
            "live_entry_allowed": risk.get("live_entry_allowed"),
            "oracle_ceiling_status": oracle.get("oracle_ceiling_status"),
            "stale_candidate_archive_status": stale_archive.get("status"),
            "stale_candidate_archive_implementation_status": stale_archive.get(
                "implementation_status"
            ),
            "stale_candidate_archive_metrics": stale_archive.get("metrics"),
            "lane_outcome_replay_status": lane_outcome.get("status"),
            "lane_outcome_replay_implementation_status": lane_outcome.get("implementation_status"),
            "lane_outcome_replay_metrics": lane_outcome.get("metrics"),
            "lane_scan_hypothesis_repair_status": lane_scan_repair.get("status"),
            "lane_scan_hypothesis_repair_implementation_status": lane_scan_repair.get(
                "implementation_status"
            ),
            "lane_scan_hypothesis_repair_metrics": lane_scan_repair.get("metrics"),
            "exact_candidate_selection_repair_status": exact_repair.get("status"),
            "exact_candidate_selection_repair_implementation_status": exact_repair.get("implementation_status"),
            "exact_candidate_selection_repair_metrics": exact_repair.get("metrics"),
            "chain_native_filter_relaxation_replay_status": chain_relaxation.get("status"),
            "chain_native_filter_relaxation_replay_implementation_status": chain_relaxation.get(
                "implementation_status"
            ),
            "chain_native_filter_relaxation_replay_metrics": chain_relaxation.get("metrics"),
            "chain_native_exit_outcome_replay_status": chain_exit_outcome.get("status"),
            "chain_native_exit_outcome_replay_implementation_status": chain_exit_outcome.get(
                "implementation_status"
            ),
            "chain_native_exit_outcome_replay_metrics": chain_exit_outcome.get("metrics"),
            "chain_native_relaxation_archive_status": chain_relaxation_archive.get("status"),
            "chain_native_relaxation_archive_implementation_status": chain_relaxation_archive.get(
                "implementation_status"
            ),
            "chain_native_relaxation_archive_metrics": chain_relaxation_archive.get("metrics"),
            "exhausted_contract_archive_status": exhausted_contract_archive.get("status"),
            "exhausted_contract_archive_implementation_status": exhausted_contract_archive.get(
                "implementation_status"
            ),
            "exhausted_contract_archive_metrics": exhausted_contract_archive.get("metrics"),
            "execution_alternative_quote_import_plan_status": execution_quote_plan.get("status"),
            "execution_alternative_quote_import_plan_implementation_status": execution_quote_plan.get(
                "implementation_status"
            ),
            "execution_alternative_quote_import_plan_metrics": execution_quote_plan.get("metrics"),
            "minute_exit_quote_import_plan_status": minute_exit_quote_plan.get("status"),
            "minute_exit_quote_import_plan_implementation_status": minute_exit_quote_plan.get(
                "implementation_status"
            ),
            "minute_exit_quote_import_plan_metrics": minute_exit_quote_plan.get("metrics"),
            "open_risk_resolution_plan_status": open_risk_plan.get("status"),
            "open_risk_resolution_plan_implementation_status": open_risk_plan.get(
                "implementation_status"
            ),
            "open_risk_resolution_plan_metrics": open_risk_plan.get("metrics"),
            "fill_attempt_evidence_capture_plan_status": fill_attempt_plan.get("status"),
            "fill_attempt_evidence_capture_plan_implementation_status": fill_attempt_plan.get(
                "implementation_status"
            ),
            "fill_attempt_evidence_capture_plan_metrics": fill_attempt_plan.get("metrics"),
            "suggested_trade_review_plan_status": suggested_trade_plan.get("status"),
            "suggested_trade_review_plan_implementation_status": suggested_trade_plan.get(
                "implementation_status"
            ),
            "suggested_trade_review_plan_metrics": suggested_trade_plan.get("metrics"),
            "regime_stratification_status": regime_stratification.get("status"),
            "regime_stratification_implementation_status": regime_stratification.get("implementation_status"),
            "regime_robust": regime_stratification.get("regime_robust"),
            "regime_stratification_metrics": regime_stratification.get("metrics"),
            "autoresearch_search_effort_status": autoresearch_search_effort.get("status"),
            "autoresearch_search_effort_implementation_status": autoresearch_search_effort.get(
                "implementation_status"
            ),
            "autoresearch_search_effort_metrics": autoresearch_search_effort.get("metrics"),
            "scheduled_scan_heartbeat_status": scheduled_scan.get("status"),
            "days_since_last_scheduled_scan": scheduled_scan.get("days_since_last_scheduled_scan"),
            "scheduled_scan_heartbeat_state": scheduled_scan.get("state"),
            "next_evidence_action_count": len(next_queue),
            "live_policy_change": live_policy_change,
        },
        "proof_policy": {
            "readback_is": "read-only monthly all-lanes profitability command center for regular supervised options",
            "readback_is_not": "scanner policy change, broker recommendation, stop change, sizing change, DB mutation, or lane promotion",
            "trusted_proof_standard": "trusted intraday exact-contract OPRA/NBBO evidence for proof claims",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "lane_leaderboard": lane_leaderboard,
        "lane_dispositions": lane_dispositions,
        "stale_candidate_archive": stale_archive,
        "lane_outcome_replay": lane_outcome,
        "lane_scan_hypothesis_repair": lane_scan_repair,
        "exact_candidate_selection_repair": exact_repair,
        "chain_native_filter_relaxation_replay": chain_relaxation,
        "chain_native_exit_outcome_replay": chain_exit_outcome,
        "chain_native_relaxation_archive": chain_relaxation_archive,
        "exhausted_contract_archive": exhausted_contract_archive,
        "execution_alternative_quote_import_plan": execution_quote_plan,
        "minute_exit_quote_import_plan": minute_exit_quote_plan,
        "open_risk_resolution_plan": open_risk_plan,
        "fill_attempt_evidence_capture_plan": fill_attempt_plan,
        "suggested_trade_review_plan": suggested_trade_plan,
        "regime_stratified_replay_report": regime_stratification,
        "autoresearch_search_effort": autoresearch_search_effort,
        "scheduled_scan_health": scheduled_scan,
        "monthly_drift": monthly_drift,
        "worst_buckets": worst_buckets,
        "candidate_rules": candidate_rules,
        "execution_realism": execution,
        "risk_portfolio": risk,
        "oracle_ceiling": oracle,
        "promotion_gate": promotion,
        "next_evidence_queue": next_queue,
        "live_policy_change": live_policy_change,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    text = _norm(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Monthly All-Lanes Profitability Audit",
        "",
        "This report is generated from `scripts/build_monthly_all_lanes_profitability_audit.py`. It is a read-only command center for monthly regular-options profitability iteration and does not change scanner, broker, database, stop, sizing, proof, or lane-promotion behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Baseline PF / avg: `{summary.get('baseline_profit_factor')}` / `{summary.get('baseline_avg_net_pnl_pct')}%`.",
        f"- Recent month: `{summary.get('recent_month')}` / `{summary.get('recent_month_status')}`.",
        f"- Execution realism: `{summary.get('execution_realism_status')}`.",
        f"- Risk/portfolio: `{summary.get('risk_portfolio_status')}`.",
        f"- Promotion gate: `{summary.get('promotion_gate_status')}` with `{summary.get('promotion_blocker_count')}` blockers.",
        f"- Open-risk status / live entry allowed: `{summary.get('open_risk_status')}` / `{summary.get('live_entry_allowed')}`.",
        f"- Oracle ceiling: `{summary.get('oracle_ceiling_status')}`.",
        f"- Stale candidate archive: `{summary.get('stale_candidate_archive_status')}` / `{summary.get('stale_candidate_archive_implementation_status')}` / `{_json_inline(summary.get('stale_candidate_archive_metrics') or {})}`.",
        f"- Candidate rules: `{summary.get('candidate_rule_count')}` total, `{summary.get('paper_candidate_rule_count')}` paper candidates, `{summary.get('reject_overfit_rule_count')}` rejected/overfit.",
        f"- Lane dispositions: `{summary.get('lane_disposition_status')}` / `{_json_inline(summary.get('lane_disposition_counts') or {})}`.",
        f"- Lane outcome replay: `{summary.get('lane_outcome_replay_status')}` / `{summary.get('lane_outcome_replay_implementation_status')}` / `{_json_inline(summary.get('lane_outcome_replay_metrics') or {})}`.",
        f"- Lane scan hypothesis repair: `{summary.get('lane_scan_hypothesis_repair_status')}` / `{summary.get('lane_scan_hypothesis_repair_implementation_status')}` / `{_json_inline(summary.get('lane_scan_hypothesis_repair_metrics') or {})}`.",
        f"- Exact-candidate selection repair: `{summary.get('exact_candidate_selection_repair_status')}` / `{summary.get('exact_candidate_selection_repair_implementation_status')}` / `{_json_inline(summary.get('exact_candidate_selection_repair_metrics') or {})}`.",
        f"- Chain-native filter relaxation replay: `{summary.get('chain_native_filter_relaxation_replay_status')}` / `{summary.get('chain_native_filter_relaxation_replay_implementation_status')}` / `{_json_inline(summary.get('chain_native_filter_relaxation_replay_metrics') or {})}`.",
        f"- Chain-native exit outcome replay: `{summary.get('chain_native_exit_outcome_replay_status')}` / `{summary.get('chain_native_exit_outcome_replay_implementation_status')}` / `{_json_inline(summary.get('chain_native_exit_outcome_replay_metrics') or {})}`.",
        f"- Execution-alternative quote import plan: `{summary.get('execution_alternative_quote_import_plan_status')}` / `{summary.get('execution_alternative_quote_import_plan_implementation_status')}` / `{_json_inline(summary.get('execution_alternative_quote_import_plan_metrics') or {})}`.",
        f"- Minute-exit quote import plan: `{summary.get('minute_exit_quote_import_plan_status')}` / `{summary.get('minute_exit_quote_import_plan_implementation_status')}` / `{_json_inline(summary.get('minute_exit_quote_import_plan_metrics') or {})}`.",
        f"- Open-risk resolution plan: `{summary.get('open_risk_resolution_plan_status')}` / `{summary.get('open_risk_resolution_plan_implementation_status')}` / `{_json_inline(summary.get('open_risk_resolution_plan_metrics') or {})}`.",
        f"- Fill-attempt evidence capture plan: `{summary.get('fill_attempt_evidence_capture_plan_status')}` / `{summary.get('fill_attempt_evidence_capture_plan_implementation_status')}` / `{_json_inline(summary.get('fill_attempt_evidence_capture_plan_metrics') or {})}`.",
        f"- Suggested-trade review plan: `{summary.get('suggested_trade_review_plan_status')}` / `{summary.get('suggested_trade_review_plan_implementation_status')}` / `{_json_inline(summary.get('suggested_trade_review_plan_metrics') or {})}`.",
        f"- Regime stratification: `{summary.get('regime_stratification_status')}` / `{summary.get('regime_stratification_implementation_status')}` / robust `{summary.get('regime_robust')}` / `{_json_inline(summary.get('regime_stratification_metrics') or {})}`.",
        f"- Autoresearch search effort: `{summary.get('autoresearch_search_effort_status')}` / `{summary.get('autoresearch_search_effort_implementation_status')}` / `{_json_inline(summary.get('autoresearch_search_effort_metrics') or {})}`.",
        f"- Scheduled scan heartbeat: `{summary.get('scheduled_scan_heartbeat_status')}`; days since last scheduled scan `{summary.get('days_since_last_scheduled_scan')}`.",
        f"- Quarantine archive: `{summary.get('archived_quarantine_lane_count')}` archived, `{summary.get('unarchived_quarantine_lane_count')}` unarchived.",
        f"- Archived rejected rules: `{summary.get('archived_reject_overfit_rule_count')}` archived, `{summary.get('unarchived_reject_overfit_rule_count')}` unarchived.",
        f"- Next evidence actions: `{summary.get('next_evidence_action_count')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Lane Leaderboard",
        "",
        "| Lane | Rows | PF | Avg Net | Median | Win Rate | Net USD | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for lane in _as_list(report.get("lane_leaderboard")):
        if not isinstance(lane, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(lane.get("lane")),
                    _cell(lane.get("rows")),
                    _cell(lane.get("profit_factor")),
                    _cell(lane.get("avg_net_pnl_pct")),
                    _cell(lane.get("median_net_pnl_pct")),
                    _cell(lane.get("win_rate_pct")),
                    _cell(lane.get("sum_net_pnl_usd")),
                    _cell(lane.get("decision")),
                ]
            )
            + " |"
        )
    disposition = _as_dict(report.get("lane_dispositions"))
    lines.extend(
        [
            "",
            "## Lane Dispositions",
            "",
            f"- Status: `{disposition.get('lane_disposition_status')}`.",
            f"- Allowed statuses: `{_json_inline(disposition.get('allowed_statuses') or [])}`.",
            f"- Counts: `{_json_inline(disposition.get('status_counts') or {})}`.",
            f"- Quarantine archive: `{disposition.get('archived_quarantine_lane_count')}` archived, `{disposition.get('unarchived_quarantine_lane_count')}` unarchived.",
            "",
            "| Lane | Disposition | Archive | Priced | PF | Avg Net | Promotion State | Source Decision | Next Step |",
            "|---|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for item in _as_list(disposition.get("dispositions")):
        item = _as_dict(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("lane")),
                    f"`{_cell(item.get('disposition'))}`",
                    f"`{_cell(item.get('archive_status') or '')}`",
                    _cell(item.get("priced")),
                    _cell(item.get("profit_factor")),
                    _cell(item.get("avg_net_pnl_pct")),
                    _cell(item.get("promotion_state")),
                    _cell(item.get("source_decision")),
                    _cell(item.get("operator_next_step")),
                ]
            )
            + " |"
        )
    stale_archive = _as_dict(report.get("stale_candidate_archive"))
    stale_archive_metrics = _as_dict(stale_archive.get("metrics"))
    lines.extend(
        [
            "",
            "## Stale Candidate Archive",
            "",
            f"- Status: `{stale_archive.get('status')}` / `{stale_archive.get('implementation_status')}`.",
            f"- Source wait/archive rows: `{stale_archive_metrics.get('source_wait_or_archive_count')}`.",
            f"- Archived no-longer-matched candidates: `{stale_archive_metrics.get('archived_no_longer_matched_candidate_count')}`.",
            f"- Archive exceptions: `{stale_archive_metrics.get('archive_exception_count')}`.",
            f"- Archive complete: `{stale_archive_metrics.get('archive_complete')}`.",
            f"- Lane counts: `{_json_inline(stale_archive_metrics.get('lane_counts') or {})}`.",
            f"- Ticker counts: `{_json_inline(stale_archive_metrics.get('ticker_counts') or {})}`.",
            f"- Production proof-ready rows: `{stale_archive_metrics.get('production_proof_ready_count')}`.",
        ]
    )
    lane_outcome = _as_dict(report.get("lane_outcome_replay"))
    lane_outcome_metrics = _as_dict(lane_outcome.get("metrics"))
    lines.extend(
        [
            "",
            "## Lane Outcome Replay",
            "",
            f"- Status: `{lane_outcome.get('status')}` / `{lane_outcome.get('implementation_status')}`.",
            f"- Active / priced / missing lanes: `{lane_outcome_metrics.get('active_lane_count')}` / `{lane_outcome_metrics.get('priced_outcome_lane_count')}` / `{lane_outcome_metrics.get('missing_outcome_lane_count')}`.",
            f"- Outcome status counts: `{_json_inline(lane_outcome_metrics.get('outcome_status_counts') or {})}`.",
        ]
    )
    lane_scan_repair = _as_dict(report.get("lane_scan_hypothesis_repair"))
    lane_scan_metrics = _as_dict(lane_scan_repair.get("metrics"))
    lines.extend(
        [
            "",
            "## Lane Scan Hypothesis Repair",
            "",
            f"- Status: `{lane_scan_repair.get('status')}` / `{lane_scan_repair.get('implementation_status')}`.",
            f"- Target no-signal lanes: `{lane_scan_metrics.get('target_no_signal_lane_count')}`.",
            f"- Predeclared replacement candidates / lanes: `{lane_scan_metrics.get('predeclared_replacement_candidate_count')}` / `{lane_scan_metrics.get('predeclared_candidate_lane_count')}`.",
            f"- Missing replacement-candidate lanes: `{lane_scan_metrics.get('missing_replacement_candidate_lane_count')}`.",
            f"- Production proof-ready candidates: `{lane_scan_metrics.get('proof_ready_replacement_candidate_count')}`.",
            f"- Fresh exact scan retest / true lane outcome P&L rows: `{lane_scan_metrics.get('fresh_exact_scan_retest_row_count')}` / `{lane_scan_metrics.get('true_lane_outcome_pnl_row_count')}`.",
            f"- Repair status counts: `{_json_inline(lane_scan_metrics.get('repair_status_counts') or {})}`.",
        ]
    )
    exact_repair = _as_dict(report.get("exact_candidate_selection_repair"))
    exact_repair_metrics = _as_dict(exact_repair.get("metrics"))
    lines.extend(
        [
            "",
            "## Exact Candidate Selection Repair",
            "",
            f"- Status: `{exact_repair.get('status')}` / `{exact_repair.get('implementation_status')}`.",
            f"- Target lanes / dates: `{exact_repair_metrics.get('target_lane_count')}` / `{exact_repair_metrics.get('target_date_count')}`.",
            f"- Signals / exact candidates: `{exact_repair_metrics.get('target_signal_candidate_count')}` / `{exact_repair_metrics.get('target_exact_candidate_count')}`.",
            f"- Exact reject reasons: `{_json_inline(exact_repair_metrics.get('exact_reject_reason_counts') or {})}`.",
            f"- Top signal tickers: `{_json_inline(exact_repair_metrics.get('top_signal_tickers') or [])}`.",
        ]
    )
    chain_relaxation = _as_dict(report.get("chain_native_filter_relaxation_replay"))
    chain_relaxation_metrics = _as_dict(chain_relaxation.get("metrics"))
    lines.extend(
        [
            "",
            "## Chain-Native Filter Relaxation Replay",
            "",
            f"- Status: `{chain_relaxation.get('status')}` / `{chain_relaxation.get('implementation_status')}`.",
            f"- Target lanes / dates: `{chain_relaxation_metrics.get('target_lane_count')}` / `{chain_relaxation_metrics.get('target_date_count')}`.",
            f"- Replay signals / scenario rows: `{chain_relaxation_metrics.get('replay_signal_candidate_count')}` / `{chain_relaxation_metrics.get('scenario_row_count')}`.",
            f"- Current / relaxed selected entry spreads: `{chain_relaxation_metrics.get('current_selected_chain_native_entry_spread_count')}` / `{chain_relaxation_metrics.get('relaxed_selected_chain_native_entry_spread_count')}`.",
            f"- Entry quote demands: `{chain_relaxation_metrics.get('entry_quote_demand_count')}` / `{_json_inline(chain_relaxation_metrics.get('entry_quote_demand_tickers') or [])}`.",
            f"- Scenario status counts: `{_json_inline(chain_relaxation_metrics.get('scenario_status_counts') or {})}`.",
        ]
    )
    chain_exit = _as_dict(report.get("chain_native_exit_outcome_replay"))
    chain_exit_metrics = _as_dict(chain_exit.get("metrics"))
    lines.extend(
        [
            "",
            "## Chain-Native Exit Outcome Replay",
            "",
            f"- Status: `{chain_exit.get('status')}` / `{chain_exit.get('implementation_status')}`.",
            f"- Selected / priced rows: `{chain_exit_metrics.get('selected_scenario_row_count')}` / `{chain_exit_metrics.get('priced_scenario_row_count')}`.",
            f"- Current / relaxed priced rows: `{chain_exit_metrics.get('priced_current_scenario_row_count')}` / `{chain_exit_metrics.get('priced_relaxed_scenario_row_count')}`.",
            f"- Missing exit quote demands: `{chain_exit_metrics.get('missing_exit_quote_demand_count')}`.",
            f"- Best relaxed scenario: `{_json_inline(chain_exit_metrics.get('best_relaxed_scenario') or {})}`.",
        ]
    )
    chain_archive = _as_dict(report.get("chain_native_relaxation_archive"))
    chain_archive_metrics = _as_dict(chain_archive.get("metrics"))
    lines.extend(
        [
            "",
            "## Chain-Native Relaxation Archive",
            "",
            f"- Status: `{chain_archive.get('status')}` / `{chain_archive.get('implementation_status')}`.",
            f"- Source ready / archive requested: `{chain_archive_metrics.get('source_ready_for_archive')}` / `{chain_archive_metrics.get('archive_requested_by_exit_outcome_replay')}`.",
            f"- Total / negative / archived branches: `{chain_archive_metrics.get('branch_scenario_count')}` / `{chain_archive_metrics.get('negative_branch_count')}` / `{chain_archive_metrics.get('archived_negative_branch_count')}`.",
            f"- Current / negative / archived scenarios: `{chain_archive_metrics.get('current_scenario_count')}` / `{chain_archive_metrics.get('negative_current_scenario_count')}` / `{chain_archive_metrics.get('archived_negative_current_scenario_count')}`.",
            f"- Relaxed / negative / archived scenarios: `{chain_archive_metrics.get('relaxed_scenario_count')}` / `{chain_archive_metrics.get('negative_relaxed_scenario_count')}` / `{chain_archive_metrics.get('archived_negative_relaxed_scenario_count')}`.",
            f"- Unarchived negative branches: `{chain_archive_metrics.get('unarchived_negative_branch_count')}`.",
            f"- Archive complete: `{chain_archive_metrics.get('archive_complete')}`.",
        ]
    )
    exhausted_contract_archive = _as_dict(report.get("exhausted_contract_archive"))
    exhausted_contract_metrics = _as_dict(exhausted_contract_archive.get("metrics"))
    lines.extend(
        [
            "",
            "## Exhausted Contract Archive",
            "",
            f"- Status: `{exhausted_contract_archive.get('status')}` / `{exhausted_contract_archive.get('implementation_status')}`.",
            f"- Source ready: `{exhausted_contract_metrics.get('source_ready_for_archive')}`.",
            f"- Archived exhausted contracts: `{exhausted_contract_metrics.get('archived_exhausted_contract_count')}`.",
            f"- Previously / newly archived exhausted contracts: `{exhausted_contract_metrics.get('previous_archived_exhausted_contract_count')}` / `{exhausted_contract_metrics.get('newly_archived_exhausted_contract_count')}`.",
            f"- Remaining eligible exhausted contracts: `{exhausted_contract_metrics.get('remaining_eligible_exhausted_contract_count')}`.",
            f"- Source exhausted targets: `{exhausted_contract_metrics.get('source_exhausted_current_source_target_count')}`.",
        ]
    )
    drift = _as_dict(report.get("monthly_drift"))
    lines.extend(
        [
            "",
            "## Monthly Drift",
            "",
            f"- Showcase month: `{drift.get('showcase_month')}`.",
            f"- Recent month: `{drift.get('recent_month')}`.",
            f"- Recent week: `{drift.get('recent_week')}`.",
            "",
            "| Month | Priced | Avg P&L | Median | Negative Rate | Health |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for month, item in _as_dict(drift.get("monthly")).items():
        item = _as_dict(item)
        lines.append(
            f"| {_cell(month)} | {_cell(item.get('priced'))} | {_cell(item.get('avg_pnl_pct'))} | {_cell(item.get('median_pnl_pct'))} | {_cell(item.get('negative_rate_priced_pct'))} | {_cell(item.get('health_status'))} |"
        )
    lines.extend(
        [
            "",
            "| Recent Lane Cohort | Priced | Avg P&L | Median | Negative Rate | Health |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in _as_list(drift.get("recent_lane_health"))[:12]:
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('cohort'))} | {_cell(item.get('priced'))} | {_cell(item.get('avg_pnl_pct'))} | {_cell(item.get('median_pnl_pct'))} | {_cell(item.get('negative_rate_priced_pct'))} | {_cell(item.get('health_status'))} |"
        )
    lines.extend(
        [
            "",
            "| Recent Ticker Cohort | Priced | Avg P&L | Median | Negative Rate | Health |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in _as_list(drift.get("recent_ticker_health"))[:12]:
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('cohort'))} | {_cell(item.get('priced'))} | {_cell(item.get('avg_pnl_pct'))} | {_cell(item.get('median_pnl_pct'))} | {_cell(item.get('negative_rate_priced_pct'))} | {_cell(item.get('health_status'))} |"
        )
    worst = _as_dict(report.get("worst_buckets"))
    lines.extend(
        [
            "",
            "## Worst Buckets",
            "",
            "| Ticker Cluster | Rows | PF | Avg Net | Net USD |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for item in _as_list(worst.get("worst_ticker_clusters"))[:12]:
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('key') or item.get('ticker'))} | {_cell(item.get('rows'))} | {_cell(item.get('profit_factor'))} | {_cell(item.get('avg_net_pnl_pct'))} | {_cell(item.get('sum_net_pnl_usd'))} |"
        )
    lines.extend(
        [
            "",
            "| DTE Bucket | Rows | PF | Avg Net | Net USD |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for item in _as_list(worst.get("dte_bucket_metrics")):
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('key') or item.get('bucket'))} | {_cell(item.get('rows'))} | {_cell(item.get('profit_factor'))} | {_cell(item.get('avg_net_pnl_pct'))} | {_cell(item.get('sum_net_pnl_usd'))} |"
        )
    lines.extend(
        [
            "",
            f"- Fill degradation buckets: `{worst.get('fill_degradation_status')}`.",
        ]
    )
    lines.extend(
        [
            "",
            "## Candidate Rules",
            "",
            "| Scenario | Classification | Archive | Kept | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Rows | Later Pass | Blockers |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for rule in _as_list(report.get("candidate_rules")):
        if not isinstance(rule, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(rule.get("scenario_id")),
                    f"`{_cell(rule.get('classification'))}`",
                    f"`{_cell(rule.get('archive_status'))}`",
                    _cell(rule.get("kept_count")),
                    _cell(rule.get("profit_factor")),
                    _cell(rule.get("avg_net_pnl_pct")),
                    _cell(rule.get("lost_winner_count")),
                    _cell(rule.get("avoided_lte_minus_50")),
                    _cell(rule.get("later_date_rows")),
                    _cell(rule.get("survives_later_date_split")),
                    _cell(", ".join(str(item) for item in _as_list(rule.get("classification_blockers"))) or "none"),
                ]
            )
            + " |"
        )
    execution = _as_dict(report.get("execution_realism"))
    minute = _as_dict(execution.get("minute_exit_readiness"))
    quote_plan = _as_dict(report.get("execution_alternative_quote_import_plan"))
    quote_plan_metrics = _as_dict(quote_plan.get("metrics"))
    minute_quote_plan = _as_dict(report.get("minute_exit_quote_import_plan"))
    minute_quote_plan_metrics = _as_dict(minute_quote_plan.get("metrics"))
    open_risk_plan = _as_dict(report.get("open_risk_resolution_plan"))
    open_risk_plan_metrics = _as_dict(open_risk_plan.get("metrics"))
    suggested_trade_plan = _as_dict(report.get("suggested_trade_review_plan"))
    suggested_trade_plan_metrics = _as_dict(suggested_trade_plan.get("metrics"))
    risk = _as_dict(report.get("risk_portfolio"))
    oracle = _as_dict(report.get("oracle_ceiling"))
    promotion = _as_dict(report.get("promotion_gate"))
    lines.extend(
        [
            "",
            "## Execution Realism",
            "",
            f"- Fill-attempt rows: `{execution.get('row_count')}`.",
            f"- Candidate-shown rows: `{execution.get('candidate_shown_count')}`.",
            f"- Proof-live exact rows: `{execution.get('proof_live_exact_count')}`.",
            f"- No-fill / not-submitted / paper-fill-recorded: `{execution.get('no_fill_count')}` / `{execution.get('not_submitted_count')}` / `{execution.get('paper_fill_recorded_count')}`.",
            f"- Fill-discipline snapshots: `{execution.get('fill_discipline_snapshot_count')}`.",
            f"- Fill-discipline coverage: `{execution.get('fill_discipline_snapshot_coverage_pct')}%`.",
            f"- Replay blockers: `{_json_inline(execution.get('execution_realism_blockers') or [])}`.",
            f"- Minute-exit readiness: `{minute.get('minute_readiness_overall_status') or 'not_available'}`; entry seeds `{minute.get('entry_seed_ready_count')}`, position seeds `{minute.get('position_seed_ready_count')}`, true minute P&L `{minute.get('true_minute_exit_pnl_count')}`.",
            "",
            "## Execution Alternative Quote Import Plan",
            "",
            f"- Status: `{quote_plan.get('status')}` / `{quote_plan.get('implementation_status')}`.",
            f"- Source coverage: `{quote_plan_metrics.get('source_coverage_status')}` / `{quote_plan_metrics.get('source_quote_demand_manifest_status')}`.",
            f"- Exact demands / command groups: `{quote_plan_metrics.get('exact_contract_manifest_count')}` / `{quote_plan_metrics.get('command_group_count')}`.",
            f"- Entry / exit demands: `{quote_plan_metrics.get('entry_quote_demand_count')}` / `{quote_plan_metrics.get('exit_quote_demand_count')}`.",
            f"- Dates / underlyings: `{_json_inline(quote_plan_metrics.get('quote_dates') or [])}` / `{_json_inline(quote_plan_metrics.get('underlyings') or [])}`.",
            "",
            "## Minute-Exit Quote Import Plan",
            "",
            f"- Status: `{minute_quote_plan.get('status')}` / `{minute_quote_plan.get('implementation_status')}`.",
            f"- Source readiness: `{minute_quote_plan_metrics.get('source_readiness_status')}` / `{minute_quote_plan_metrics.get('source_overall_status')}`.",
            f"- Source entry / position seeds: `{minute_quote_plan_metrics.get('source_entry_seed_ready_count')}` / `{minute_quote_plan_metrics.get('source_position_seed_ready_count')}`.",
            f"- Exact demands / command groups: `{minute_quote_plan_metrics.get('exact_contract_manifest_count')}` / `{minute_quote_plan_metrics.get('command_group_count')}`.",
            f"- Position-linked / entry-only demands: `{minute_quote_plan_metrics.get('position_linked_quote_demand_count')}` / `{minute_quote_plan_metrics.get('entry_only_quote_demand_count')}`.",
            f"- Replay P&L status: `{minute_quote_plan_metrics.get('replay_pnl_status')}`.",
            f"- Dates / underlyings: `{_json_inline(minute_quote_plan_metrics.get('quote_dates') or [])}` / `{_json_inline(minute_quote_plan_metrics.get('underlyings') or [])}`.",
            "",
            "## Open-Risk Resolution Plan",
            "",
            f"- Status: `{open_risk_plan.get('status')}` / `{open_risk_plan.get('implementation_status')}`.",
            f"- Source open-risk status: `{open_risk_plan_metrics.get('source_open_risk_status')}`.",
            f"- Live entry allowed: `{open_risk_plan_metrics.get('live_entry_allowed')}`.",
            f"- Plan rows / live exact / display-only SELL: `{open_risk_plan_metrics.get('plan_row_count')}` / `{open_risk_plan_metrics.get('live_exact_plan_row_count')}` / `{open_risk_plan_metrics.get('display_only_sell_count')}`.",
            f"- Open rows / negative rows: `{open_risk_plan_metrics.get('open_position_row_count')}` / `{open_risk_plan_metrics.get('open_position_negative_count')}`.",
            f"- Avg / median open P&L: `{open_risk_plan_metrics.get('open_position_avg_pnl_pct')}` / `{open_risk_plan_metrics.get('open_position_median_pnl_pct')}`.",
            "",
            "| Priority | ID | Ticker | Lane | Class | Action | Status |",
            "|---:|---:|---|---|---|---|---|",
        ]
    )
    for row in _as_list(open_risk_plan.get("plan_rows"))[:20]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("priority")),
                    _cell(row.get("row_id")),
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("record_class")),
                    f"`{_cell(row.get('action'))}`",
                    f"`{_cell(row.get('resolution_status'))}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Suggested-Trade Review Plan",
            "",
            f"- Status: `{suggested_trade_plan.get('status')}` / `{suggested_trade_plan.get('implementation_status')}`.",
            f"- Open / attention / plan rows: `{suggested_trade_plan_metrics.get('open_suggested_trade_rows')}` / `{suggested_trade_plan_metrics.get('attention_trade_count')}` / `{suggested_trade_plan_metrics.get('plan_row_count')}`.",
            f"- Close-risk / stale-missing rows: `{suggested_trade_plan_metrics.get('close_risk_trade_count')}` / `{suggested_trade_plan_metrics.get('stale_or_missing_review_trade_count')}`.",
            f"- Missing / stale reviews: `{suggested_trade_plan_metrics.get('missing_review_count')}` / `{suggested_trade_plan_metrics.get('stale_review_count')}`.",
            f"- Executable / non-executable close-ready: `{suggested_trade_plan_metrics.get('executable_close_ready_count')}` / `{suggested_trade_plan_metrics.get('non_executable_close_risk_count')}`.",
            "",
            "| Priority | ID | Ticker | Lane | Class | Action | Status |",
            "|---:|---:|---|---|---|---|---|",
        ]
    )
    for row in _as_list(suggested_trade_plan.get("plan_rows"))[:20]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("priority")),
                    _cell(row.get("suggested_trade_id")),
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("record_class")),
                    f"`{_cell(row.get('action'))}`",
                    f"`{_cell(row.get('resolution_status'))}`",
                ]
            )
            + " |"
        )
    regime = _as_dict(report.get("regime_stratified_replay_report"))
    regime_metrics = _as_dict(regime.get("metrics"))
    lines.extend(
        [
            "",
            "## Regime Stratification",
            "",
            f"- Status: `{regime.get('status')}` / `{regime.get('implementation_status')}`.",
            f"- Regime robust: `{regime.get('regime_robust')}`.",
            f"- Eligible rows: `{regime_metrics.get('eligible_replay_row_count')}`.",
            f"- Branches: `{regime_metrics.get('branch_count')}`; branch buckets `{regime_metrics.get('branch_bucket_count')}`.",
            f"- Market context: `{regime_metrics.get('market_context_status')}`; VIX missing `{regime_metrics.get('vix_missing_count')}`, SPY50 missing `{regime_metrics.get('spy50_missing_count')}`.",
            f"- Evaluable / failing buckets: `{regime_metrics.get('evaluable_bucket_count')}` / `{regime_metrics.get('failing_bucket_count')}`.",
        ]
    )
    search_effort = _as_dict(report.get("autoresearch_search_effort"))
    search_metrics = _as_dict(search_effort.get("metrics"))
    lines.extend(
        [
            "",
            "## Autoresearch Search Effort",
            "",
            f"- Status: `{search_effort.get('status')}` / `{search_effort.get('implementation_status')}`.",
            f"- Strategy family: `{search_metrics.get('strategy_family')}`.",
            f"- Variants searched: `{search_metrics.get('variants_searched')}`.",
            f"- PF-LB selection-adjusted bar: `{search_metrics.get('selection_adjusted_bar')}`.",
            f"- Formula: `{search_metrics.get('selection_adjustment_formula')}`.",
            f"- Diagnostic only: `{search_metrics.get('diagnostic_only')}`.",
        ]
    )
    lines.extend(
        [
            "",
            "## Risk And Portfolio",
            "",
            f"- Open-risk status: `{risk.get('open_risk_status')}`.",
            f"- Live entry allowed: `{risk.get('live_entry_allowed')}`.",
            f"- Live exact negative IDs: `{_json_inline(risk.get('live_exact_negative_ids') or [])}`.",
            f"- Multilane quality status: `{risk.get('multilane_quality_status')}`.",
            f"- Risk-budget sizing status: `{risk.get('risk_budget_sizing_status')}` / `{risk.get('risk_budget_sizing_implementation_status')}`.",
            f"- Risk-budget sizing best research scenario: `{_as_dict(risk.get('risk_budget_sizing_metrics')).get('best_research_scenario_id')}` / net `{_as_dict(risk.get('risk_budget_sizing_metrics')).get('best_research_net_pnl_usd')}` / PF `{_as_dict(risk.get('risk_budget_sizing_metrics')).get('best_research_profit_factor')}`.",
            f"- Zero-bid/liquidity blockers: `{_json_inline(risk.get('zero_bid_liquidity_blockers') or [])}`.",
            f"- Promotion blockers: `{_json_inline(risk.get('promotion_blockers') or [])}`.",
            "",
            "## Oracle Ceiling",
            "",
            f"- Status: `{oracle.get('oracle_ceiling_status')}`.",
            "- V1 does not synthesize maximum possible P&L from midpoint, daily, stale, or display marks.",
            "",
            "## Next Evidence Queue",
            "",
            "| Priority | Source | Action | Count | Reason |",
            "|---:|---|---|---:|---|",
        ]
    )
    for item in _as_list(report.get("next_evidence_queue")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {_cell(item.get('priority'))} | {_cell(item.get('source'))} | `{_cell(item.get('action'))}` | {_cell(item.get('count'))} | {_cell(item.get('reason'))} |"
        )
    lines.extend(
        [
            "",
            "## Promotion Gate",
            "",
            f"- Status: `{promotion.get('status')}`.",
            f"- Promotion ready: `{promotion.get('promotion_ready')}`.",
            f"- Blockers: `{_json_inline(promotion.get('blockers') or [])}`.",
            "",
            "## Boundary",
            "",
            "This command center is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote paper/research/backfill evidence.",
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
    parser = argparse.ArgumentParser(description="Build the read-only monthly all-lanes profitability command center.")
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
