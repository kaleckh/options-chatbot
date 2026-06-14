from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

try:
    from scripts.audit_repository_constraints import build_constraint_audit
    from scripts.audit_repository_constraints import load_local_env as load_constraints_env
except Exception:  # pragma: no cover - direct import errors are reported in the gateboard.
    build_constraint_audit = None  # type: ignore[assignment]
    load_constraints_env = None  # type: ignore[assignment]

try:
    from scripts.scan_heartbeat import build_scan_heartbeat_health
except Exception:  # pragma: no cover - direct import errors are reported in scheduler health.
    build_scan_heartbeat_health = None  # type: ignore[assignment]


REPORT_ID = "project_operator_gateboard"
GENERATOR = "scripts/build_project_operator_gateboard.py"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "project-operator-gateboard.md"
DEFAULT_PATHWAY_REGISTRY = ROOT / "data" / "contracts" / "project-pathway-registry.json"
DEFAULT_SQLITE_SUGGESTED_DB = ROOT / "chat_history.db"

DEFAULT_MISSED_OUTCOME = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_FRESH_EVIDENCE = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_PAPER_SHORTLIST = ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist" / "latest.json"
DEFAULT_OPERATING_SCORECARD = ROOT / "data" / "profitability-lab" / "regular-options-operating-scorecard" / "latest.json"
DEFAULT_CANDIDATE_LIFECYCLE = ROOT / "data" / "contracts" / "candidate-lifecycle-contract.json"
DEFAULT_AI_COMMODITY = ROOT / "data" / "ai-commodity-infra" / "progress" / "latest.json"
DEFAULT_SCAN_HEARTBEAT = ROOT / "data" / "forward-tracking" / "scheduled_scan_heartbeat_latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(ROOT).as_posix()
    except (OSError, ValueError):
        return str(candidate)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "path": _rel(path),
            "error": "missing",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "available": False,
            "path": _rel(path),
            "error": f"unreadable:{type(exc).__name__}:{exc}",
        }
    if not isinstance(payload, dict):
        return {
            "available": False,
            "path": _rel(path),
            "error": "json_root_not_object",
        }
    payload.setdefault("available", True)
    payload.setdefault("path", _rel(path))
    return payload


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_float(value: Any, suffix: str = "") -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.2f}{suffix}"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _store_count(store: dict[str, Any], key: str) -> int:
    rows = store.get(key)
    if not isinstance(rows, list):
        return 0
    return sum(_safe_int(row.get("count"), 0) for row in rows if isinstance(row, dict))


def _artifact_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": _rel(path),
        "available": bool(payload.get("available", True) and not payload.get("error")),
        "report_id": payload.get("report_id"),
        "status": payload.get("status"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "error": payload.get("error"),
    }


def _pathway_owner(registry: dict[str, Any], pathway_id: str) -> dict[str, list[str]]:
    pathways = registry.get("pathways") if isinstance(registry.get("pathways"), list) else []
    for row in pathways:
        if isinstance(row, dict) and row.get("id") == pathway_id:
            return {
                "owner_docs": list(row.get("owner_docs") or []),
                "owner_scripts": list(row.get("owner_scripts") or []),
            }
    return {"owner_docs": [], "owner_scripts": []}


def _run_data_integrity_audit(
    *,
    sqlite_suggested_db: Path,
    database_url: str | None,
) -> dict[str, Any]:
    if build_constraint_audit is None:
        return {
            "audit": "repository_constraints",
            "status": "unavailable",
            "stores": [],
            "error": "scripts.audit_repository_constraints could not be imported",
        }
    if load_constraints_env is not None:
        load_constraints_env(ROOT)
    return build_constraint_audit(
        sqlite_suggested_db=str(sqlite_suggested_db),
        database_url=database_url if database_url is not None else os.environ.get("DATABASE_URL"),
    )


def _data_integrity_pathway(audit: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    stores = [store for store in audit.get("stores", []) if isinstance(store, dict)]
    violation_count = sum(_store_count(store, "violations") for store in stores)
    diagnostic_count = sum(_store_count(store, "diagnostics") for store in stores)
    skipped = [store.get("store_id") for store in stores if store.get("status") == "skipped"]
    if audit.get("status") == "violations_found" or violation_count:
        state = "fail"
        headline = "Hard repository data-integrity violations are present."
    elif skipped:
        state = "warning"
        headline = "Repository audit did not inspect every store."
    elif audit.get("status") == "pass_with_diagnostics" or diagnostic_count:
        state = "warning"
        headline = "Repository audit passed hard checks but has diagnostics."
    elif audit.get("status") == "pass_or_skipped" and stores:
        state = "pass"
        headline = "Trusted repository data is clean for current readbacks."
    else:
        state = "warning"
        headline = "Repository data-integrity audit is unavailable or inconclusive."
    details = [
        f"audit_status={audit.get('status')}",
        f"hard_violation_count={violation_count}",
        f"diagnostic_count={diagnostic_count}",
    ]
    for store in stores:
        details.append(f"{store.get('store_id')}={store.get('status')}")
    if skipped:
        details.append(f"skipped_stores={','.join(str(item) for item in skipped)}")
    return {
        "id": "data_path",
        "label": "Data Path",
        "state": state,
        "headline": headline,
        "details": details,
        **_pathway_owner(registry, "data_path"),
    }


def _candidate_pathway(lifecycle: dict[str, Any], fresh_evidence: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    lifecycle_ok = lifecycle.get("report_id") == "candidate_lifecycle_contract"
    summary = fresh_evidence.get("summary") if isinstance(fresh_evidence.get("summary"), dict) else {}
    status_counts = summary.get("candidate_status_counts") if isinstance(summary.get("candidate_status_counts"), dict) else {}
    if not lifecycle_ok:
        state = "fail"
        headline = "Candidate lifecycle contract is missing or invalid."
    elif fresh_evidence.get("error"):
        state = "warning"
        headline = "Candidate vocabulary exists, but current candidate readback is missing."
    else:
        state = "pass"
        headline = "Candidate statuses are centralized and current candidates are visible."
    return {
        "id": "candidate_path",
        "label": "Candidate Path",
        "state": state,
        "headline": headline,
        "details": [
            f"lifecycle_contract={'loaded' if lifecycle_ok else 'missing_or_invalid'}",
            f"fresh_candidate_count={_safe_int(summary.get('candidate_count'), 0)}",
            f"candidate_status_counts={json.dumps(status_counts, sort_keys=True)}",
        ],
        **_pathway_owner(registry, "candidate_path"),
    }


def _evidence_pathway(fresh_evidence: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    summary = fresh_evidence.get("summary") if isinstance(fresh_evidence.get("summary"), dict) else {}
    if fresh_evidence.get("error"):
        state = "fail"
        headline = "Fresh evidence loop artifact is missing or unreadable."
    elif _safe_int(summary.get("promotion_discussion_ready_count"), 0) > 0:
        state = "pass"
        headline = "Fresh proof evidence has promotion-discussion rows."
    else:
        state = "blocked"
        headline = "Fresh evidence is visible, but nothing is promotion-ready."
    entry_counts = summary.get("entry_evidence_status_counts") if isinstance(summary.get("entry_evidence_status_counts"), dict) else {}
    outcome_counts = summary.get("validation_outcome_counts") if isinstance(summary.get("validation_outcome_counts"), dict) else {}
    return {
        "id": "evidence_path",
        "label": "Evidence Path",
        "state": state,
        "headline": headline,
        "details": [
            f"candidate_count={_safe_int(summary.get('candidate_count'), 0)}",
            f"fresh_exact_entry_count={_safe_int(entry_counts.get('fresh_executable_exact_entry'), 0)}",
            f"linked_position_count={_safe_int(summary.get('linked_position_count'), 0)}",
            f"exact_realized_pnl_count={_safe_int(summary.get('exact_realized_pnl_count'), 0)}",
            f"promotion_discussion_ready_count={_safe_int(summary.get('promotion_discussion_ready_count'), 0)}",
            f"validation_outcome_counts={json.dumps(outcome_counts, sort_keys=True)}",
        ],
        **_pathway_owner(registry, "evidence_path"),
    }


def _profitability_pathway(missed_outcome: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    summary = missed_outcome.get("summary") if isinstance(missed_outcome.get("summary"), dict) else {}
    metrics = missed_outcome.get("metrics") if isinstance(missed_outcome.get("metrics"), dict) else {}
    untracked = metrics.get("untracked_rows_conservative_mark") if isinstance(metrics.get("untracked_rows_conservative_mark"), dict) else {}
    tracked_row_count = _safe_int(summary.get("tracked_row_count"), 0)
    tracked_with_pnl = _safe_int(summary.get("tracked_rows_with_stored_pnl"), 0)
    unpriced = _safe_int(summary.get("mark_unpriced_count"), 0)
    profit_factor = _safe_float(untracked.get("profit_factor"))
    avg_pnl = _safe_float(untracked.get("avg_net_pnl_pct"))
    if missed_outcome.get("error"):
        state = "fail"
        headline = "Missed-pick profitability artifact is missing or unreadable."
    elif unpriced > 0 or tracked_with_pnl < tracked_row_count:
        state = "fail"
        headline = "Profitability audit still has pricing or tracked-P&L data gaps."
    elif profit_factor is not None and avg_pnl is not None and profit_factor >= 1.0 and avg_pnl > 0:
        state = "pass"
        headline = "Broad missed-pick economics are positive."
    else:
        state = "blocked"
        headline = "Data is clean, but broad missed-pick economics are negative."
    return {
        "id": "profitability_path",
        "label": "Profitability Path",
        "state": state,
        "headline": headline,
        "details": [
            f"priced_rows={_safe_int(summary.get('mark_coverage_count'), 0)}/{_safe_int(summary.get('raw_row_count'), 0)}",
            f"mark_unpriced_count={unpriced}",
            f"tracked_pnl_complete={tracked_with_pnl}/{tracked_row_count}",
            f"untracked_rows={_safe_int(summary.get('untracked_row_count'), 0)}",
            f"untracked_winners={_safe_int(untracked.get('winner_count'), 0)}",
            f"untracked_losers={_safe_int(untracked.get('loser_count'), 0)}",
            f"untracked_avg_net_pnl_pct={_fmt_float(avg_pnl, '%')}",
            f"untracked_profit_factor={_fmt_float(profit_factor)}",
            f"lane_gate_allowed_count={_safe_int(summary.get('lane_gate_allowed_count'), 0)}",
            f"lane_gate_blocked_count={_safe_int(summary.get('lane_gate_blocked_count'), 0)}",
        ],
        **_pathway_owner(registry, "profitability_path"),
    }


def _promotion_pathway(lane_promotion: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    summary = lane_promotion.get("summary") if isinstance(lane_promotion.get("summary"), dict) else {}
    live_validation = _safe_int(summary.get("live_validation_lane_count"), 0)
    auto_track = _safe_int(summary.get("auto_track_lane_count"), 0)
    negative_open = _safe_int(summary.get("global_live_exact_negative_count"), 0)
    governor_status = summary.get("open_risk_governor_status")
    if lane_promotion.get("error"):
        state = "fail"
        headline = "Lane promotion state artifact is missing or unreadable."
    elif live_validation or auto_track:
        state = "pass"
        headline = "At least one lane is allowed beyond paper/probation."
    else:
        state = "blocked"
        headline = "No regular lane is live-validation or auto-track eligible."
    if negative_open and state == "pass":
        state = "warning"
        headline = "Lane permissions exist, but live exact negative risk needs review."
    return {
        "id": "promotion_path",
        "label": "Promotion Path",
        "state": state,
        "headline": headline,
        "details": [
            f"lane_count={_safe_int(summary.get('lane_count'), 0)}",
            f"diagnostic_lane_count={_safe_int(summary.get('diagnostic_lane_count'), 0)}",
            f"paper_probation_lane_count={_safe_int(summary.get('paper_probation_lane_count'), 0)}",
            f"live_validation_lane_count={live_validation}",
            f"auto_track_lane_count={auto_track}",
            f"global_live_exact_negative_count={negative_open}",
            f"open_risk_governor_status={governor_status}",
            f"live_policy_change={bool(summary.get('live_policy_change'))}",
        ],
        **_pathway_owner(registry, "promotion_path"),
    }


def _operator_pathway(
    paper_shortlist: dict[str, Any],
    scorecard: dict[str, Any],
    ai_commodity: dict[str, Any],
    open_risk: dict[str, Any],
    suggested_risk: dict[str, Any],
    scan_heartbeat_health: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    shortlist_summary = paper_shortlist.get("summary") if isinstance(paper_shortlist.get("summary"), dict) else {}
    scorecard_paper = scorecard.get("paper_gate_readiness") if isinstance(scorecard.get("paper_gate_readiness"), dict) else {}
    eligible = _safe_int(shortlist_summary.get("eligible_count"), _safe_int(scorecard_paper.get("eligible_paper_review_candidate_count"), 0))
    ai_verified = bool(ai_commodity.get("verified"))
    open_governor = open_risk.get("open_risk_governor") if isinstance(open_risk.get("open_risk_governor"), dict) else {}
    suggested_summary = suggested_risk.get("summary") if isinstance(suggested_risk.get("summary"), dict) else {}
    suggested_attention = _safe_int(suggested_summary.get("rows"), 0)
    if scan_heartbeat_health.get("state") == "fail":
        state = "fail"
        headline = "Scheduled scan heartbeat is missing or stale."
    elif paper_shortlist.get("error") or scorecard.get("error"):
        state = "warning"
        headline = "Operator readback is missing one or more current artifacts."
    elif eligible > 0:
        state = "pass"
        headline = "Operator has eligible paper-review candidates to inspect."
    else:
        state = "blocked"
        headline = "Operator readback is complete, but no paper/live candidates are eligible."
    shared_quote_dates = ai_commodity.get("shared_quote_dates")
    if isinstance(shared_quote_dates, dict):
        shared_quote_count = shared_quote_dates.get("count")
    else:
        shared_quote_count = None
    ai_current_shared = _first_present(
        ai_commodity.get("current_shared_quote_dates"),
        ai_commodity.get("profitability_evidence_scorecard_current_shared_quote_dates"),
        ai_commodity.get("alpaca_opra_data_usage_proof_window_shared_quote_dates"),
        shared_quote_count,
    )
    ai_required_shared = _first_present(
        ai_commodity.get("required_shared_quote_dates"),
        ai_commodity.get("profitability_evidence_scorecard_required_shared_quote_dates"),
        ai_commodity.get("alpaca_opra_data_usage_required_shared_quote_dates"),
        ai_commodity.get("exact_replay_runway_full_required_shared_quote_dates"),
    )
    details = [
        f"paper_shortlist_release_gate={shortlist_summary.get('release_gate_status')}",
        f"eligible_paper_review_candidates={eligible}",
        f"scorecard_status={scorecard.get('status')}",
        f"paper_gate_status={scorecard_paper.get('status')}",
        f"open_risk_governor_status={open_governor.get('status')}",
        f"open_risk_governor_blockers={json.dumps(open_governor.get('blockers') or [], sort_keys=True)}",
        f"suggested_open_rows={suggested_attention}",
        f"suggested_attention_trade_count={len(suggested_risk.get('attention_trade_ids') or [])}",
        f"scheduled_scan_heartbeat_status={scan_heartbeat_health.get('status')}",
        f"days_since_last_scheduled_scan={scan_heartbeat_health.get('days_since_last_scheduled_scan')}",
        f"last_scheduled_scan_host={scan_heartbeat_health.get('last_host')}",
        f"last_scheduled_scan_commit={scan_heartbeat_health.get('last_commit_sha')}",
        f"ai_commodity_verified={ai_verified}",
        f"ai_commodity_shared_quote_dates={ai_current_shared}/{ai_required_shared}",
    ]
    return {
        "id": "operator_path",
        "label": "Operator Path",
        "state": state,
        "headline": headline,
        "details": details,
        **_pathway_owner(registry, "operator_path"),
    }


def _next_actions(pathways: list[dict[str, Any]]) -> list[str]:
    states = {row["id"]: row["state"] for row in pathways}
    actions = [
        "Keep live validation and auto-track disabled until promotion-state rows move beyond paper/probation.",
        "Use the gateboard first when answering whether a blocker is data, evidence, profitability, promotion, or operator visibility.",
    ]
    if states.get("data_path") in {"fail", "warning"}:
        actions.insert(0, "Repair `npm run options:audit:data-integrity` before trusting picks, P&L, exposure, or dashboards.")
    if states.get("profitability_path") == "blocked":
        actions.append("Do not treat all clear scanner rows equally; investigate entry-time-only filters and lanes that can earn back from diagnostics.")
    if states.get("evidence_path") == "blocked":
        actions.append("Collect fresh executable exact entry/exit evidence before discussing live promotion.")
    if states.get("operator_path") == "blocked":
        actions.append("During the next valid market-data window, rerun all-lanes audit, pending validation, fresh evidence loop, and lane promotion readbacks.")
    return actions


def _no_chase_manifest(
    *,
    missed_outcome: dict[str, Any],
    lane_promotion: dict[str, Any],
    fresh_evidence: dict[str, Any],
    paper_shortlist: dict[str, Any],
    open_risk: dict[str, Any],
    suggested_risk: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    missed_summary = missed_outcome.get("summary") if isinstance(missed_outcome.get("summary"), dict) else {}
    missed_metrics = missed_outcome.get("metrics") if isinstance(missed_outcome.get("metrics"), dict) else {}
    untracked = (
        missed_metrics.get("untracked_rows_conservative_mark")
        if isinstance(missed_metrics.get("untracked_rows_conservative_mark"), dict)
        else {}
    )
    profit_factor = _safe_float(untracked.get("profit_factor"))
    avg_pnl = _safe_float(untracked.get("avg_net_pnl_pct"))
    if profit_factor is None or profit_factor < 1.0 or (avg_pnl is not None and avg_pnl <= 0):
        reasons.append(
            {
                "reason": "broad_missed_pick_economics_negative",
                "severity": "block_live_release",
                "evidence": {
                    "untracked_rows": _safe_int(missed_summary.get("untracked_row_count"), 0),
                    "profit_factor": profit_factor,
                    "avg_net_pnl_pct": avg_pnl,
                },
            }
        )
    promotion_summary = lane_promotion.get("summary") if isinstance(lane_promotion.get("summary"), dict) else {}
    if _safe_int(promotion_summary.get("live_validation_lane_count"), 0) == 0:
        reasons.append(
            {
                "reason": "no_live_validation_lanes",
                "severity": "block_live_validation",
                "evidence": {
                    "paper_probation_lane_count": _safe_int(promotion_summary.get("paper_probation_lane_count"), 0),
                    "auto_track_lane_count": _safe_int(promotion_summary.get("auto_track_lane_count"), 0),
                },
            }
        )
    governor = open_risk.get("open_risk_governor") if isinstance(open_risk.get("open_risk_governor"), dict) else {}
    if governor.get("status") != "open_risk_governor_pass":
        reasons.append(
            {
                "reason": "open_risk_governor_blocked_or_missing",
                "severity": "block_new_scanner_origin_entries",
                "evidence": {
                    "status": governor.get("status") or "missing",
                    "blockers": list(governor.get("blockers") or []),
                    "live_exact_negative_ids": list(governor.get("live_exact_negative_ids") or []),
                },
            }
        )
    fresh_summary = fresh_evidence.get("summary") if isinstance(fresh_evidence.get("summary"), dict) else {}
    if _safe_int(fresh_summary.get("promotion_discussion_ready_count"), 0) == 0:
        reasons.append(
            {
                "reason": "no_promotion_ready_fresh_evidence",
                "severity": "block_promotion_discussion",
                "evidence": {
                    "paper_probation_bridge_count": _safe_int(fresh_summary.get("paper_probation_bridge_count"), 0),
                    "exact_exit_bridge_count": _safe_int(fresh_summary.get("exact_exit_bridge_count"), 0),
                },
            }
        )
    shortlist_summary = paper_shortlist.get("summary") if isinstance(paper_shortlist.get("summary"), dict) else {}
    if _safe_int(shortlist_summary.get("eligible_count"), 0) == 0:
        reasons.append(
            {
                "reason": "no_eligible_paper_shortlist_candidates",
                "severity": "block_operator_chase",
                "evidence": {
                    "release_gate_status": shortlist_summary.get("release_gate_status"),
                    "fresh_bridge_blocker_counts": shortlist_summary.get("fresh_bridge_blocker_counts") or {},
                },
            }
        )
    attention_ids = list(suggested_risk.get("attention_trade_ids") or [])
    if attention_ids:
        reasons.append(
            {
                "reason": "suggested_trade_review_attention_required",
                "severity": "refresh_before_using_suggested_pnl",
                "evidence": {"attention_trade_ids": attention_ids},
            }
        )
    return {
        "status": "no_chase_active" if reasons else "no_chase_clear",
        "live_policy_change": False,
        "reasons": reasons,
        "reason_count": len(reasons),
        "prohibited_actions": [
            "do_not_open_live_or_auto_track_rows_from_blocked_readbacks",
            "do_not_chase_paper_or_historical_signature_rows_without_fresh_exact_bridge",
            "do_not_use_stale_midpoint_eod_manual_or_display_only_marks_as_proof",
        ],
    }


def _overall_status(pathways: list[dict[str, Any]]) -> tuple[str, str]:
    failures = [row for row in pathways if row["state"] == "fail"]
    warnings = [row for row in pathways if row["state"] == "warning"]
    blocked = [row for row in pathways if row["state"] == "blocked"]
    if failures:
        labels = ", ".join(row["label"] for row in failures)
        return "hard_blocker_present", f"Hard blocker in {labels}; do not trust downstream claims until repaired."
    if warnings:
        labels = ", ".join(row["label"] for row in warnings)
        return "warning_review_required", f"Review warnings in {labels} before making proof or release claims."
    if blocked:
        labels = ", ".join(row["label"] for row in blocked)
        return "safe_blocked_no_live_release", f"Data is readable, but release is intentionally blocked in {labels}."
    return "ready_for_operator_review", "No pathway reports a hard blocker; review live/paper permissions before any action."


def build_gateboard(
    *,
    generated_at_utc: str | None = None,
    data_integrity_audit: dict[str, Any] | None = None,
    sqlite_suggested_db: Path = DEFAULT_SQLITE_SUGGESTED_DB,
    database_url: str | None = None,
    pathway_registry_path: Path = DEFAULT_PATHWAY_REGISTRY,
    missed_outcome_path: Path = DEFAULT_MISSED_OUTCOME,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    suggested_risk_path: Path = DEFAULT_SUGGESTED_RISK,
    paper_shortlist_path: Path = DEFAULT_PAPER_SHORTLIST,
    operating_scorecard_path: Path = DEFAULT_OPERATING_SCORECARD,
    candidate_lifecycle_path: Path = DEFAULT_CANDIDATE_LIFECYCLE,
    ai_commodity_path: Path = DEFAULT_AI_COMMODITY,
    scan_heartbeat_path: Path = DEFAULT_SCAN_HEARTBEAT,
) -> dict[str, Any]:
    registry = _load_json(pathway_registry_path)
    missed_outcome = _load_json(missed_outcome_path)
    lane_promotion = _load_json(lane_promotion_path)
    fresh_evidence = _load_json(fresh_evidence_path)
    open_risk = _load_json(open_risk_path)
    suggested_risk = _load_json(suggested_risk_path)
    paper_shortlist = _load_json(paper_shortlist_path)
    scorecard = _load_json(operating_scorecard_path)
    lifecycle = _load_json(candidate_lifecycle_path)
    ai_commodity = _load_json(ai_commodity_path)
    if build_scan_heartbeat_health is None:
        scan_heartbeat_health = {
            "report_id": "scheduled_scan_heartbeat_health",
            "state": "fail",
            "status": "unavailable",
            "heartbeat_path": str(scan_heartbeat_path),
            "heartbeat_available": False,
            "blocker": "scheduled_scan_heartbeat_health_import_failed",
        }
    else:
        scan_heartbeat_health = build_scan_heartbeat_health(
            heartbeat_path=scan_heartbeat_path,
            as_of_utc=generated_at_utc,
        )
    integrity = data_integrity_audit or _run_data_integrity_audit(
        sqlite_suggested_db=sqlite_suggested_db,
        database_url=database_url,
    )

    pathways = [
        _data_integrity_pathway(integrity, registry),
        _candidate_pathway(lifecycle, fresh_evidence, registry),
        _evidence_pathway(fresh_evidence, registry),
        _profitability_pathway(missed_outcome, registry),
        _promotion_pathway(lane_promotion, registry),
        _operator_pathway(
            paper_shortlist,
            scorecard,
            ai_commodity,
            open_risk,
            suggested_risk,
            scan_heartbeat_health,
            registry,
        ),
    ]
    overall_status, primary_message = _overall_status(pathways)
    source_artifacts = {
        "pathway_registry": _artifact_summary(pathway_registry_path, registry),
        "candidate_lifecycle": _artifact_summary(candidate_lifecycle_path, lifecycle),
        "missed_regular_picks_outcome": _artifact_summary(missed_outcome_path, missed_outcome),
        "fresh_evidence_loop": _artifact_summary(fresh_evidence_path, fresh_evidence),
        "open_position_risk": _artifact_summary(open_risk_path, open_risk),
        "suggested_trade_close_risk": _artifact_summary(suggested_risk_path, suggested_risk),
        "lane_promotion_state": _artifact_summary(lane_promotion_path, lane_promotion),
        "paper_shortlist": _artifact_summary(paper_shortlist_path, paper_shortlist),
        "operating_scorecard": _artifact_summary(operating_scorecard_path, scorecard),
        "ai_commodity_progress": _artifact_summary(ai_commodity_path, ai_commodity),
        "scheduled_scan_heartbeat": {
            "path": _rel(scan_heartbeat_path),
            "available": bool(scan_heartbeat_health.get("heartbeat_available")),
            "status": scan_heartbeat_health.get("status"),
            "generated_at_utc": scan_heartbeat_health.get("last_run_at_utc"),
            "error": scan_heartbeat_health.get("blocker"),
        },
    }
    return {
        "report_id": REPORT_ID,
        "generated_by": GENERATOR,
        "runtime_use": False,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "overall_status": overall_status,
        "primary_message": primary_message,
        "pathway_statuses": pathways,
        "repository_data_integrity": integrity,
        "source_artifacts": source_artifacts,
        "scheduled_scan_health": scan_heartbeat_health,
        "no_chase_manifest": _no_chase_manifest(
            missed_outcome=missed_outcome,
            lane_promotion=lane_promotion,
            fresh_evidence=fresh_evidence,
            paper_shortlist=paper_shortlist,
            open_risk=open_risk,
            suggested_risk=suggested_risk,
        ),
        "operator_next_actions": _next_actions(pathways),
        "non_goals": [
            "create trades",
            "submit broker orders",
            "change scanner policy",
            "change lane promotion policy",
            "lower proof bars",
            "turn paper/research/backfill rows into production proof",
        ],
    }


def _md_cell(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _mermaid_gateboard(report: dict[str, Any]) -> str:
    labels = {row["id"]: f"{row['label']}: {row['state'].upper()}" for row in report["pathway_statuses"]}
    return "\n".join(
        [
            "flowchart LR",
            f'  data_path["{labels.get("data_path", "Data Path")}"] --> candidate_path["{labels.get("candidate_path", "Candidate Path")}"]',
            f'  candidate_path --> evidence_path["{labels.get("evidence_path", "Evidence Path")}"]',
            f'  evidence_path --> profitability_path["{labels.get("profitability_path", "Profitability Path")}"]',
            f'  profitability_path --> promotion_path["{labels.get("promotion_path", "Promotion Path")}"]',
            f'  promotion_path --> operator_path["{labels.get("operator_path", "Operator Path")}"]',
        ]
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project Operator Gateboard",
        "",
        f"Produced by `{GENERATOR}` as a current readback. Rebuild it with `npm run options:gateboard`.",
        "",
        "This is read-only. It explains where the project is blocked without changing scanner, broker, proof, stop, or lane-promotion behavior.",
        "",
        "## At A Glance",
        "",
        f"- Overall status: `{report['overall_status']}`",
        f"- Generated at UTC: `{report['generated_at_utc']}`",
        f"- Primary message: {report['primary_message']}",
        "",
        "## Current Flow",
        "",
        "```mermaid",
        _mermaid_gateboard(report),
        "```",
        "",
        "## Pathway Status",
        "",
        "| Pathway | State | Meaning | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["pathway_statuses"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row["label"]),
                    _md_cell(f"`{row['state']}`"),
                    _md_cell(row["headline"]),
                    _md_cell(row["details"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Operator Next Actions", ""])
    for action in report["operator_next_actions"]:
        lines.append(f"- {action}")
    no_chase = report.get("no_chase_manifest") if isinstance(report.get("no_chase_manifest"), dict) else {}
    lines.extend(["", "## No-Chase Manifest", ""])
    lines.append(f"- Status: `{no_chase.get('status')}`")
    lines.append(f"- Reason count: `{no_chase.get('reason_count', 0)}`")
    lines.append(f"- Live policy change: `{no_chase.get('live_policy_change')}`")
    lines.extend(["", "| Reason | Severity | Evidence |", "| --- | --- | --- |"])
    for reason in no_chase.get("reasons") or []:
        if isinstance(reason, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(reason.get("reason")),
                        _md_cell(reason.get("severity")),
                        _md_cell(json.dumps(reason.get("evidence") or {}, sort_keys=True)),
                    ]
                )
                + " |"
            )
    lines.extend(["", "### Prohibited Actions", ""])
    for item in no_chase.get("prohibited_actions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Source Artifacts", "", "| Artifact | Available | Status | Generated |", "| --- | --- | --- | --- |"])
    for name, artifact in report["source_artifacts"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(f"{name}: `{artifact.get('path')}`"),
                    _md_cell(artifact.get("available")),
                    _md_cell(artifact.get("status") or artifact.get("report_id") or artifact.get("error")),
                    _md_cell(artifact.get("generated_at_utc")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Non-Goals", ""])
    for item in report["non_goals"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def write_outputs(report: dict[str, Any], *, output_json: Path, docs_report: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(render_json(report), encoding="utf-8")
    docs_report.write_text(render_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the current project operator gateboard.")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--sqlite-suggested-db", type=Path, default=DEFAULT_SQLITE_SUGGESTED_DB)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    report = build_gateboard(
        sqlite_suggested_db=args.sqlite_suggested_db,
        database_url=args.database_url,
    )
    if not args.no_write:
        write_outputs(report, output_json=args.output_json, docs_report=args.docs_report)
    if args.json:
        print(render_json(report), end="")
    else:
        if args.no_write:
            print(f"{REPORT_ID}: {report['overall_status']}")
        else:
            print(f"Wrote {_rel(args.output_json)}")
            print(f"Wrote {_rel(args.docs_report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
