from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_profitability_layer_stack"

DEFAULT_ARTIFACT_PATHS: dict[str, Path] = {
    "candidate_ledger": ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json",
    "fresh_evidence_loop": ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json",
    "paper_shortlist": ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist" / "latest.json",
    "profit_capture_queue": ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json",
    "repair_burndown": ROOT / "data" / "profitability-lab" / "regular-options-repair-burndown" / "latest.json",
    "repair_attempts": ROOT / "data" / "profitability-lab" / "regular-options-repair-attempts" / "latest.json",
    "open_risk": ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json",
    "suggested_close_risk": ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json",
    "volatility_probation": ROOT / "data" / "forward-tracking" / "volatility_probation_reconciliation_latest.json",
    "lane_promotion_state": ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json",
    "current_policy_circuit_breaker": ROOT / "data" / "forward-tracking" / "current_policy_circuit_breaker_latest.json",
    "missed_picks_outcome": ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json",
    "missed_picks_failure_modes": ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json",
    "missed_picks_filter_matrix": ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json",
    "overfit_rule_archive": ROOT / "data" / "forward-tracking" / "regular_options_overfit_rule_archive_latest.json",
    "entry_filter_walkforward": ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_walkforward_latest.json",
    "entry_filter_point_in_time": ROOT / "data" / "forward-tracking" / "short_term_filter_point_in_time_replay_latest.json",
    "entry_filter_paper_monitor": ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_paper_monitor_latest.json",
    "current_policy_stop_grid": ROOT / "data" / "forward-tracking" / "current_policy_historical_stop_grid_latest.json",
    "minute_exit_replay_readiness": ROOT / "data" / "forward-tracking" / "regular_options_minute_exit_replay_readiness_latest.json",
    "execution_alternative_replay_readiness": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_execution_alternative_replay_readiness_latest.json",
    "execution_alternative_replay_coverage": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_execution_alternative_replay_coverage_latest.json",
    "structure_specific_harness": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_structure_specific_harness_latest.json",
    "event_data_spine": ROOT / "data" / "forward-tracking" / "regular_options_event_data_spine_latest.json",
    "risk_budget_sizing_replay": ROOT
    / "data"
    / "forward-tracking"
    / "regular_options_risk_budget_sizing_replay_latest.json",
    "multilane_portfolio": ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json",
    "symbol_sleeves": ROOT / "data" / "profitability-lab" / "regular-options-symbol-sleeves" / "latest.json",
    "guardrail_starvation": ROOT / "data" / "forward-tracking" / "regular_guardrail_starvation_latest.json",
}

DEFAULT_FILL_ATTEMPT_FILE = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-profitability-layer-stack.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_profitability_layer_stack",
    "do_not_submit_broker_order_from_profitability_layer_stack",
    "do_not_change_scanner_policy_from_profitability_layer_stack",
    "do_not_change_stop_policy_from_profitability_layer_stack",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_profitability_layer_stack",
    "do_not_treat_midpoint_stale_eod_or_manual_rows_as_production_proof",
)


LAYER_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "layer": 1,
        "slug": "candidate_outcome_ledger",
        "title": "Unified candidate outcome ledger",
        "category": "evidence_control_plane",
        "artifact_keys": ("candidate_ledger",),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_candidate_outcome_ledger.py",),
    },
    {
        "layer": 2,
        "slug": "fresh_exact_paper_cohort",
        "title": "Fresh exact paper cohort",
        "category": "paper_evidence",
        "artifact_keys": ("fresh_evidence_loop", "lane_promotion_state"),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_fresh_evidence_loop.py",),
    },
    {
        "layer": 3,
        "slug": "paper_only_fill_attempt_logging",
        "title": "Paper-only fill-attempt logging",
        "category": "paper_evidence",
        "artifact_keys": ("fill_attempts", "fresh_evidence_loop"),
        "owner_commands": ("npm run options:log", "npm run options:validate:pending-candidates"),
    },
    {
        "layer": 4,
        "slug": "paper_review_create_link_workflow",
        "title": "Paper-review create/link workflow",
        "category": "operator_workflow",
        "artifact_keys": ("candidate_ledger", "paper_shortlist"),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_candidate_outcome_ledger.py",),
    },
    {
        "layer": 5,
        "slug": "fill_discipline_paper_log",
        "title": "Fill-discipline paper log",
        "category": "execution_quality",
        "artifact_keys": ("fill_attempts",),
        "owner_commands": ("npm run options:log",),
    },
    {
        "layer": 6,
        "slug": "operator_next_evidence_queue",
        "title": "Operator next-evidence queue",
        "category": "operator_workflow",
        "artifact_keys": ("candidate_ledger",),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_candidate_outcome_ledger.py",),
    },
    {
        "layer": 7,
        "slug": "volatility_paper_probation_current_cohort",
        "title": "Volatility paper/probation current cohort",
        "category": "lane_promotion",
        "artifact_keys": ("volatility_probation", "lane_promotion_state"),
        "owner_commands": ("npm run options:audit:volatility-probation", "npm run options:audit:lane-promotion-state"),
    },
    {
        "layer": 8,
        "slug": "open_risk_exact_exit_hygiene",
        "title": "Resolve open-risk exact-exit hygiene",
        "category": "risk_and_exit",
        "artifact_keys": ("open_risk", "candidate_ledger"),
        "owner_commands": ("uv run --locked python scripts/audit_regular_open_position_risk.py",),
    },
    {
        "layer": 9,
        "slug": "top_spread_alternative_replay",
        "title": "Top-spread alternative replay / liquidity-first v2",
        "category": "execution_quality",
        "artifact_keys": (
            "fill_attempts",
            "execution_alternative_replay_readiness",
            "execution_alternative_replay_coverage",
            "profit_capture_queue",
        ),
        "owner_commands": (
            "npm run options:replay:execution-alternatives",
            "npm run options:replay:execution-alternative-coverage",
            "uv run --locked python scripts/build_regular_options_profit_capture_queue.py",
        ),
    },
    {
        "layer": 10,
        "slug": "contract_replacement_exit_survivability",
        "title": "Contract replacement for exit survivability",
        "category": "execution_quality",
        "artifact_keys": (
            "fill_attempts",
            "execution_alternative_replay_readiness",
            "execution_alternative_replay_coverage",
            "symbol_sleeves",
        ),
        "owner_commands": (
            "npm run options:replay:execution-alternatives",
            "npm run options:replay:execution-alternative-coverage",
            "uv run --locked python scripts/build_regular_options_symbol_sleeves.py",
        ),
    },
    {
        "layer": 11,
        "slug": "minute_level_exit_quote_deterioration",
        "title": "Minute-level exit / quote-deterioration replay",
        "category": "risk_and_exit",
        "artifact_keys": ("current_policy_stop_grid", "minute_exit_replay_readiness", "open_risk"),
        "owner_commands": (
            "uv run --locked python scripts/build_regular_options_minute_exit_replay_readiness.py",
            "uv run --locked python scripts/replay_current_policy_historical_stop_grid.py",
        ),
    },
    {
        "layer": 12,
        "slug": "anti_overfit_controls",
        "title": "Anti-overfit controls",
        "category": "validation",
        "artifact_keys": (
            "missed_picks_filter_matrix",
            "overfit_rule_archive",
            "entry_filter_walkforward",
            "entry_filter_point_in_time",
            "entry_filter_paper_monitor",
            "current_policy_circuit_breaker",
        ),
        "owner_commands": (
            "npm run options:audit:missed-filter-matrix",
            "uv run --locked python scripts/build_regular_options_overfit_rule_archive.py",
            "uv run --locked python scripts/validate_current_policy_entry_filter_walkforward.py",
            "npm run options:replay:short-term-filter",
        ),
    },
    {
        "layer": 13,
        "slug": "rejected_near_miss_outcome_replay",
        "title": "Rejected near-miss outcome replay",
        "category": "validation",
        "artifact_keys": ("missed_picks_outcome", "missed_picks_failure_modes", "missed_picks_filter_matrix"),
        "owner_commands": ("npm run options:audit:missed-outcomes", "npm run options:audit:missed-failures"),
    },
    {
        "layer": 14,
        "slug": "tier_a_bridge_watchlist",
        "title": "Tier A bridge watchlist",
        "category": "paper_evidence",
        "artifact_keys": ("profit_capture_queue", "paper_shortlist"),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_profit_capture_queue.py", "uv run --locked python scripts/build_regular_options_paper_shortlist.py"),
    },
    {
        "layer": 15,
        "slug": "source_replay_repair_burndown",
        "title": "Source-replay repair burn-down",
        "category": "data_repair",
        "artifact_keys": ("repair_burndown", "repair_attempts", "profit_capture_queue"),
        "owner_commands": ("uv run --locked python scripts/build_regular_options_repair_burndown.py",),
    },
    {
        "layer": 16,
        "slug": "lane_lab_freshness_reconciler",
        "title": "Lane-lab freshness reconciler",
        "category": "lane_promotion",
        "artifact_keys": ("lane_promotion_state", "current_policy_circuit_breaker", "guardrail_starvation"),
        "owner_commands": ("npm run options:audit:lane-promotion-state", "npm run options:audit:all-lanes"),
    },
    {
        "layer": 17,
        "slug": "portfolio_throttle_replay",
        "title": "Portfolio throttle replay",
        "category": "risk_and_sizing",
        "artifact_keys": ("multilane_portfolio", "open_risk"),
        "owner_commands": ("uv run --locked python scripts/run_regular_options_multilane_portfolio.py",),
    },
    {
        "layer": 18,
        "slug": "risk_budget_sizing_replay",
        "title": "Risk-budget sizing replay",
        "category": "risk_and_sizing",
        "artifact_keys": ("risk_budget_sizing_replay", "open_risk", "multilane_portfolio", "candidate_ledger"),
        "owner_commands": (
            "uv run --locked python scripts/build_regular_options_risk_budget_sizing_replay.py",
            "uv run --locked python scripts/run_regular_options_multilane_portfolio.py",
            "uv run --locked python scripts/audit_regular_open_position_risk.py",
        ),
    },
    {
        "layer": 19,
        "slug": "structure_specific_multileg_harness",
        "title": "Structure-specific multi-leg harness",
        "category": "strategy_structure",
        "artifact_keys": ("structure_specific_harness", "fill_attempts", "fresh_evidence_loop"),
        "owner_commands": (
            "npm run options:replay:structure-specific-harness",
            "npm run options:log",
            "uv run --locked python scripts/build_regular_options_fresh_evidence_loop.py",
        ),
    },
    {
        "layer": 20,
        "slug": "event_data_spine_post_event_vol_crush",
        "title": "Event data spine / post-event vol crush",
        "category": "event_research",
        "artifact_keys": ("event_data_spine", "guardrail_starvation", "profit_capture_queue"),
        "owner_commands": (
            "npm run options:replay:event-data-spine",
            "npm run options:audit:all-lanes",
            "uv run --locked python scripts/build_regular_options_profit_capture_queue.py",
        ),
    },
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _input_refs(keys: tuple[str, ...], sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for key in keys:
        meta = sources.get(key, {})
        refs.append(
            {
                "key": key,
                "path": meta.get("path"),
                "status": meta.get("status"),
                "generated_at_utc": meta.get("generated_at_utc"),
                "row_count": meta.get("row_count"),
            }
        )
    return refs


def _counter_get(mapping: dict[str, Any], key: str) -> int:
    try:
        return int(mapping.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _ledger_action_count(ledger: dict[str, Any], action: str) -> int:
    return _counter_get(_as_dict(_as_dict(ledger.get("summary")).get("action_counts")), action)


def _fill_attempt_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_rows = [row for row in rows if _norm(row.get("event_type")) == "candidate_shown"]
    with_selected = [row for row in candidate_rows if isinstance(row.get("selected_spread"), dict)]
    with_top = [row for row in candidate_rows if _as_list(row.get("top_alternatives")) or _as_list(row.get("top_spread_alternatives"))]
    with_discipline = [row for row in candidate_rows if isinstance(row.get("fill_discipline_snapshot"), dict)]
    strategy_counts = Counter(_norm(row.get("strategy_type")) or "unknown" for row in candidate_rows)
    fill_status_counts = Counter(_norm(row.get("fill_status")) or "unknown" for row in candidate_rows)
    latest = candidate_rows[-1] if candidate_rows else {}
    return {
        "row_count": len(rows),
        "candidate_shown_count": len(candidate_rows),
        "selected_spread_count": len(with_selected),
        "top_alternative_count": len(with_top),
        "fill_discipline_snapshot_count": len(with_discipline),
        "proof_live_exact_count": sum(
            1 for row in candidate_rows if _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
        ),
        "paper_fill_recorded_count": sum(1 for row in candidate_rows if _norm(row.get("fill_outcome")) == "paper_fill_recorded"),
        "auto_tracked_count": sum(1 for row in candidate_rows if row.get("auto_track_position_id") is not None),
        "strategy_type_counts": dict(sorted(strategy_counts.items())),
        "fill_status_counts": dict(sorted(fill_status_counts.items())),
        "latest_candidate": {
            "logged_at": latest.get("logged_at"),
            "playbook_id": latest.get("playbook_id"),
            "ticker": latest.get("ticker"),
            "fill_status": latest.get("fill_status"),
            "fill_outcome": latest.get("fill_outcome"),
            "auto_track_position_id": latest.get("auto_track_position_id"),
        },
    }


def _compact_metrics(layer_slug: str, reports: dict[str, dict[str, Any]], fill_summary: dict[str, Any]) -> dict[str, Any]:
    ledger_summary = _as_dict(reports["candidate_ledger"].get("summary"))
    fresh_summary = _as_dict(reports["fresh_evidence_loop"].get("summary"))
    queue_summary = _as_dict(reports["profit_capture_queue"].get("summary"))
    shortlist_summary = _as_dict(reports["paper_shortlist"].get("summary"))
    repair_summary = _as_dict(reports["repair_burndown"].get("summary"))
    open_governor = _as_dict(reports["open_risk"].get("open_risk_governor"))
    volatility_summary = _as_dict(reports["volatility_probation"].get("summary"))
    lane_summary = _as_dict(reports["lane_promotion_state"].get("summary"))
    circuit_summary = _as_dict(reports["current_policy_circuit_breaker"].get("summary"))
    minute_summary = _as_dict(reports["minute_exit_replay_readiness"].get("summary"))
    execution_alternative_summary = _as_dict(reports["execution_alternative_replay_readiness"].get("summary"))
    execution_alternative_coverage_summary = _as_dict(reports["execution_alternative_replay_coverage"].get("summary"))
    sizing_summary = _as_dict(reports["risk_budget_sizing_replay"].get("summary"))
    missed_failure_quality = _as_dict(reports["missed_picks_failure_modes"].get("data_quality"))
    filter_summary = _as_dict(reports["missed_picks_filter_matrix"].get("summary"))
    archive_summary = _as_dict(reports["overfit_rule_archive"].get("summary"))
    multilane = reports["multilane_portfolio"]
    quality_gate = _as_dict(multilane.get("quality_gate"))
    symbol = reports["symbol_sleeves"]
    symbol_counts = _as_dict(symbol.get("classification_counts"))
    if layer_slug == "candidate_outcome_ledger":
        return {
            "ledger_row_count": ledger_summary.get("ledger_row_count"),
            "operating_status": ledger_summary.get("operating_status"),
            "action_counts": ledger_summary.get("action_counts"),
        }
    if layer_slug == "fresh_exact_paper_cohort":
        return {
            "fresh_candidate_count": fresh_summary.get("candidate_count"),
            "exact_realized_pnl_count": fresh_summary.get("exact_realized_pnl_count"),
            "paper_probation_bridge_count": fresh_summary.get("paper_probation_bridge_count"),
            "exact_exit_bridge_count": fresh_summary.get("exact_exit_bridge_count"),
        }
    if layer_slug in {"paper_only_fill_attempt_logging", "fill_discipline_paper_log"}:
        return dict(fill_summary)
    if layer_slug == "top_spread_alternative_replay":
        return {
            "candidate_shown_count": fill_summary.get("candidate_shown_count"),
            "top_alternative_logged_row_count": execution_alternative_summary.get("top_alternative_logged_row_count"),
            "top_spread_replay_seed_count": execution_alternative_summary.get("top_spread_replay_seed_count"),
            "contract_replacement_seed_count": execution_alternative_summary.get("contract_replacement_seed_count"),
            "true_top_spread_replay_pnl_count": execution_alternative_coverage_summary.get(
                "true_top_spread_replay_pnl_count",
                execution_alternative_summary.get("true_top_spread_replay_pnl_count"),
            ),
            "liquidity_first_replay_engine_status": execution_alternative_coverage_summary.get(
                "liquidity_first_replay_engine_status",
                execution_alternative_summary.get("liquidity_first_replay_engine_status"),
            ),
            "top_spread_entry_quote_coverage_status": execution_alternative_coverage_summary.get(
                "top_spread_entry_quote_coverage_status"
            ),
            "top_spread_exit_quote_coverage_status": execution_alternative_coverage_summary.get(
                "top_spread_exit_quote_coverage_status"
            ),
            "alternative_exit_quote_coverage_status": execution_alternative_coverage_summary.get(
                "alternative_exit_quote_coverage_status",
                execution_alternative_summary.get("alternative_exit_quote_coverage_status"),
            ),
            "coverage_status": execution_alternative_coverage_summary.get("overall_status")
            or reports["execution_alternative_replay_coverage"].get("status")
            or "missing",
            "quote_demand_manifest_status": execution_alternative_coverage_summary.get("quote_demand_manifest_status"),
            "missing_quote_demand_count": execution_alternative_coverage_summary.get("missing_quote_demand_count"),
            "missing_entry_quote_demand_count": execution_alternative_coverage_summary.get("missing_entry_quote_demand_count"),
            "missing_exit_quote_demand_count": execution_alternative_coverage_summary.get("missing_exit_quote_demand_count"),
            "quote_demand_usage_counts": execution_alternative_coverage_summary.get("quote_demand_usage_counts"),
            "readiness_status": reports["execution_alternative_replay_readiness"].get("status") or "missing",
        }
    if layer_slug == "contract_replacement_exit_survivability":
        return {
            "candidate_shown_count": fill_summary.get("candidate_shown_count"),
            "replacement_alternative_logged_row_count": execution_alternative_summary.get(
                "replacement_alternative_logged_row_count"
            ),
            "contract_replacement_seed_count": execution_alternative_summary.get("contract_replacement_seed_count"),
            "true_contract_replacement_pnl_count": execution_alternative_coverage_summary.get(
                "true_contract_replacement_pnl_count",
                execution_alternative_summary.get("true_contract_replacement_pnl_count"),
            ),
            "contract_replacement_replay_engine_status": execution_alternative_coverage_summary.get(
                "contract_replacement_replay_engine_status",
                execution_alternative_summary.get("contract_replacement_replay_engine_status"),
            ),
            "contract_replacement_entry_quote_coverage_status": execution_alternative_coverage_summary.get(
                "contract_replacement_entry_quote_coverage_status"
            ),
            "contract_replacement_exit_quote_coverage_status": execution_alternative_coverage_summary.get(
                "contract_replacement_exit_quote_coverage_status"
            ),
            "alternative_exit_quote_coverage_status": execution_alternative_coverage_summary.get(
                "alternative_exit_quote_coverage_status",
                execution_alternative_summary.get("alternative_exit_quote_coverage_status"),
            ),
            "coverage_status": execution_alternative_coverage_summary.get("overall_status")
            or reports["execution_alternative_replay_coverage"].get("status")
            or "missing",
            "quote_demand_manifest_status": execution_alternative_coverage_summary.get("quote_demand_manifest_status"),
            "missing_quote_demand_count": execution_alternative_coverage_summary.get("missing_quote_demand_count"),
            "missing_entry_quote_demand_count": execution_alternative_coverage_summary.get("missing_entry_quote_demand_count"),
            "missing_exit_quote_demand_count": execution_alternative_coverage_summary.get("missing_exit_quote_demand_count"),
            "quote_demand_usage_counts": execution_alternative_coverage_summary.get("quote_demand_usage_counts"),
            "readiness_status": reports["execution_alternative_replay_readiness"].get("status") or "missing",
        }
    if layer_slug == "paper_review_create_link_workflow":
        return {
            "create_or_link_rows": _ledger_action_count(reports["candidate_ledger"], "create_or_link_paper_review_row"),
            "paper_shortlist_eligible_count": shortlist_summary.get("eligible_count"),
        }
    if layer_slug == "operator_next_evidence_queue":
        return {
            "queue_action_count": len(_as_list(reports["candidate_ledger"].get("next_evidence_queue"))),
            "action_counts": ledger_summary.get("action_counts"),
        }
    if layer_slug == "volatility_paper_probation_current_cohort":
        return {
            "lane_promotion_state": volatility_summary.get("lane_promotion_state"),
            "current_paper_probation_exact_evidence_pending_count": volatility_summary.get(
                "current_paper_probation_exact_evidence_pending_count"
            ),
            "promotion_discussion_ready_excluding_legacy_count": volatility_summary.get(
                "promotion_discussion_ready_excluding_legacy_count"
            ),
            "lane_blockers": volatility_summary.get("lane_blockers"),
        }
    if layer_slug == "open_risk_exact_exit_hygiene":
        return {
            "open_risk_status": open_governor.get("status"),
            "live_entry_allowed": open_governor.get("live_entry_allowed"),
            "live_exact_negative_ids": open_governor.get("live_exact_negative_ids"),
            "collect_exact_exit_rows": _ledger_action_count(reports["candidate_ledger"], "collect_exact_exit_evidence"),
        }
    if layer_slug == "minute_level_exit_quote_deterioration":
        return {
            "daily_stop_grid_available": bool(reports["current_policy_stop_grid"]),
            "minute_level_replay_artifact": reports["minute_exit_replay_readiness"].get("status") or "missing",
            "minute_readiness_overall_status": minute_summary.get("overall_status"),
            "entry_seed_ready_count": minute_summary.get("entry_seed_ready_count"),
            "position_seed_ready_count": minute_summary.get("position_seed_ready_count"),
            "true_minute_exit_pnl_count": minute_summary.get("true_minute_exit_pnl_count"),
            "position_linked_true_minute_exit_pnl_count": minute_summary.get(
                "position_linked_true_minute_exit_pnl_count"
            ),
            "minute_quote_coverage_status": minute_summary.get("minute_quote_coverage_status"),
            "minute_exit_replay_engine_status": minute_summary.get("minute_exit_replay_engine_status"),
            "minute_exit_decision_counts": minute_summary.get("minute_exit_decision_counts"),
            "open_risk_status": open_governor.get("status"),
        }
    if layer_slug == "anti_overfit_controls":
        return {
            "filter_matrix_priced_untracked_rows": filter_summary.get("priced_untracked_rows"),
            "archived_reject_overfit_rule_count": archive_summary.get("archived_reject_overfit_rule_count"),
            "unarchived_reject_overfit_rule_count": archive_summary.get("unarchived_reject_overfit_rule_count"),
            "overfit_archive_status": archive_summary.get("overall_status"),
            "circuit_breaker_status": circuit_summary.get("overall_status"),
            "point_in_time_status": _as_dict(reports["entry_filter_point_in_time"].get("decision_summary")).get("status"),
            "paper_monitor_status": _as_dict(reports["entry_filter_paper_monitor"].get("gate")).get("status"),
        }
    if layer_slug == "rejected_near_miss_outcome_replay":
        return {
            "data_status": missed_failure_quality.get("status") or reports["missed_picks_failure_modes"].get("overall_read"),
            "priced_untracked_rows": filter_summary.get("priced_untracked_rows"),
            "source_mark_unpriced_count": filter_summary.get("source_mark_unpriced_count"),
        }
    if layer_slug == "tier_a_bridge_watchlist":
        return {
            "paper_review_candidates": _counter_get(_as_dict(queue_summary.get("selection_readiness_counts")), "paper_review_candidate"),
            "paper_shortlist_eligible_count": shortlist_summary.get("eligible_count"),
            "tier_a_fresh_match_bridge_count": queue_summary.get("tier_a_fresh_match_bridge_count"),
        }
    if layer_slug == "source_replay_repair_burndown":
        return {
            "active_unattempted_exact_targets": repair_summary.get("active_unattempted_exact_target_count"),
            "source_replay_required_targets": repair_summary.get("source_replay_required_target_count"),
            "diagnostic_lookahead_targets": repair_summary.get("diagnostic_lookahead_target_count"),
            "exhausted_targets": repair_summary.get("exhausted_target_count"),
        }
    if layer_slug == "lane_lab_freshness_reconciler":
        return {
            "lane_count": lane_summary.get("lane_count"),
            "diagnostic_lane_count": lane_summary.get("diagnostic_lane_count"),
            "paper_probation_lane_count": lane_summary.get("paper_probation_lane_count"),
            "live_validation_lane_count": lane_summary.get("live_validation_lane_count"),
            "open_risk_governor_status": lane_summary.get("open_risk_governor_status"),
        }
    if layer_slug == "portfolio_throttle_replay":
        return {
            "quality_gate_status": quality_gate.get("overall_status") or quality_gate.get("status"),
            "combined_portfolio": _as_dict(multilane.get("combined_portfolio")),
            "lane_status_counts": multilane.get("lane_status_counts"),
        }
    if layer_slug == "risk_budget_sizing_replay":
        return {
            "sizing_replay_status": sizing_summary.get("overall_status"),
            "source_row_count": sizing_summary.get("source_row_count"),
            "baseline_net_pnl_usd": sizing_summary.get("baseline_net_pnl_usd"),
            "best_research_scenario_id": sizing_summary.get("best_research_scenario_id"),
            "best_research_net_pnl_usd": sizing_summary.get("best_research_net_pnl_usd"),
            "best_research_profit_factor": sizing_summary.get("best_research_profit_factor"),
            "positive_research_scenario_count": sizing_summary.get("positive_research_scenario_count"),
            "open_risk_status": open_governor.get("status"),
            "quality_gate_status": quality_gate.get("overall_status") or quality_gate.get("status"),
            "live_entry_allowed": open_governor.get("live_entry_allowed"),
        }
    if layer_slug == "structure_specific_multileg_harness":
        structure_summary = _as_dict(reports["structure_specific_harness"].get("summary"))
        if structure_summary:
            return {
                "structure_harness_status": reports["structure_specific_harness"].get("status"),
                "candidate_shown_count": structure_summary.get("candidate_shown_count"),
                "structure_bucket_counts": structure_summary.get("structure_bucket_counts"),
                "strategy_type_counts": structure_summary.get("strategy_type_counts"),
                "proof_live_exact_entry_count": structure_summary.get("proof_live_exact_entry_count"),
                "paper_fill_recorded_count": structure_summary.get("paper_fill_recorded_count"),
                "true_structure_specific_pnl_count": structure_summary.get("true_structure_specific_pnl_count"),
                "harness_row_count": structure_summary.get("harness_row_count"),
                "blockers": structure_summary.get("blockers"),
            }
        return dict(fill_summary)
    if layer_slug == "event_data_spine_post_event_vol_crush":
        event_summary = _as_dict(reports["event_data_spine"].get("summary"))
        return {
            "event_data_spine_status": reports["event_data_spine"].get("status"),
            "candidate_shown_count": event_summary.get("candidate_shown_count"),
            "event_annotation_count": event_summary.get("event_annotation_count"),
            "missing_event_annotation_count": event_summary.get("missing_event_annotation_count"),
            "unique_ticker_count": event_summary.get("unique_ticker_count"),
            "true_event_replay_pnl_count": event_summary.get("true_event_replay_pnl_count"),
            "post_event_vol_crush_replay_pnl_count": event_summary.get("post_event_vol_crush_replay_pnl_count"),
            "event_annotation_field_counts": event_summary.get("event_annotation_field_counts"),
            "event_spine_blockers": event_summary.get("blockers"),
            "guardrail_starvation_status": _as_dict(reports["guardrail_starvation"].get("overall")).get("status")
            or reports["guardrail_starvation"].get("status"),
            "profit_capture_queue_rows": queue_summary.get("queue_rows"),
        }
    return {
        "profit_capture_queue_rows": queue_summary.get("queue_rows"),
        "symbol_classification_counts": symbol_counts,
    }


def _layer_status(layer_slug: str, reports: dict[str, dict[str, Any]], sources: dict[str, dict[str, Any]], fill_summary: dict[str, Any]) -> tuple[str, str, list[str], str]:
    ledger = reports["candidate_ledger"]
    ledger_summary = _as_dict(ledger.get("summary"))
    fresh_summary = _as_dict(reports["fresh_evidence_loop"].get("summary"))
    shortlist_summary = _as_dict(reports["paper_shortlist"].get("summary"))
    queue_summary = _as_dict(reports["profit_capture_queue"].get("summary"))
    repair_summary = _as_dict(reports["repair_burndown"].get("summary"))
    open_governor = _as_dict(reports["open_risk"].get("open_risk_governor"))
    volatility_summary = _as_dict(reports["volatility_probation"].get("summary"))
    lane_summary = _as_dict(reports["lane_promotion_state"].get("summary"))
    circuit_summary = _as_dict(reports["current_policy_circuit_breaker"].get("summary"))
    multilane_quality = _as_dict(reports["multilane_portfolio"].get("quality_gate"))
    minute_summary = _as_dict(reports["minute_exit_replay_readiness"].get("summary"))
    execution_alternative_summary = _as_dict(reports["execution_alternative_replay_readiness"].get("summary"))
    execution_alternative_coverage_summary = _as_dict(reports["execution_alternative_replay_coverage"].get("summary"))
    archive_summary = _as_dict(reports["overfit_rule_archive"].get("summary"))
    sizing_summary = _as_dict(reports["risk_budget_sizing_replay"].get("summary"))

    missing_required = []
    if layer_slug == "candidate_outcome_ledger" and sources["candidate_ledger"].get("status") != "loaded":
        missing_required.append("candidate_ledger")
    if layer_slug != "candidate_outcome_ledger" and not reports:
        missing_required.append("reports")
    if missing_required:
        return "wired_missing_input", "blocked", missing_required, "Regenerate or repair the missing input artifact before using this layer."

    if layer_slug == "candidate_outcome_ledger":
        blockers = []
        if ledger_summary.get("open_risk_live_entry_allowed") is False:
            blockers.append("open_risk_governor_blocked")
        if int(ledger_summary.get("exact_realized_pnl_count") or 0) == 0:
            blockers.append("no_exact_realized_pnl_rows")
        return "built", "blocked" if blockers else "ready", blockers, "Use the ledger queue from priority 0 downward."
    if layer_slug == "fresh_exact_paper_cohort":
        blockers = []
        if int(fresh_summary.get("exact_realized_pnl_count") or 0) == 0:
            blockers.append("no_fresh_exact_realized_pnl")
        if int(fresh_summary.get("paper_probation_bridge_count") or 0) > 0:
            blockers.append("paper_probation_exact_entry_required")
        return "built_collecting", "collecting", blockers, "Collect fresh exact paper entries and exact realized exits, then rebuild the fresh-evidence loop."
    if layer_slug == "paper_only_fill_attempt_logging":
        blockers = []
        if int(fill_summary.get("candidate_shown_count") or 0) == 0:
            blockers.append("no_candidate_shown_fill_attempt_rows")
        if int(fill_summary.get("proof_live_exact_count") or 0) == 0:
            blockers.append("no_proof_live_exact_fill_attempt_rows")
        return "built", "ready" if not blockers else "collecting", blockers, "Keep durable fill-attempt logging enabled for every paper/live-validation candidate."
    if layer_slug == "paper_review_create_link_workflow":
        count = _ledger_action_count(ledger, "create_or_link_paper_review_row")
        blockers = ["paper_review_rows_need_create_or_link"] if count else []
        return "built_collecting", "collecting" if blockers else "ready", blockers, "Create/link paper review rows for fresh exact entries; do not count them as live proof."
    if layer_slug == "fill_discipline_paper_log":
        blockers = []
        if int(fill_summary.get("fill_discipline_snapshot_count") or 0) == 0:
            blockers.append("fill_discipline_snapshot_missing")
        if int(fill_summary.get("top_alternative_count") or 0) == 0:
            blockers.append("top_alternatives_missing")
        return "built", "ready" if not blockers else "collecting", blockers, "Preserve fill-degradation, top alternatives, and leg-spread fields in every fill-attempt row."
    if layer_slug == "operator_next_evidence_queue":
        blockers = []
        if int(ledger_summary.get("ledger_row_count") or 0) == 0:
            blockers.append("empty_candidate_outcome_ledger")
        return "built", "ready" if not blockers else "blocked", blockers, "Use `docs/regular-options-candidate-outcome-ledger.md` as the operator queue."
    if layer_slug == "volatility_paper_probation_current_cohort":
        blockers = list(volatility_summary.get("lane_blockers") or [])
        return "built_collecting", "blocked" if blockers else "ready", blockers, "Collect current volatility paper exact evidence and clear open-risk before promotion discussion."
    if layer_slug == "open_risk_exact_exit_hygiene":
        blockers = []
        if open_governor.get("live_entry_allowed") is False:
            blockers.extend(list(open_governor.get("blockers") or ["open_risk_governor_blocked"]))
        if _ledger_action_count(ledger, "collect_exact_exit_evidence"):
            blockers.append("exact_exit_evidence_required")
        return "built_blocked", "blocked" if blockers else "ready", blockers, "Resolve open-risk governor and exact-exit evidence before any new live validation."
    if layer_slug == "top_spread_alternative_replay":
        if sources["execution_alternative_replay_readiness"].get("status") != "loaded":
            blockers = ["execution_alternative_replay_readiness_missing", "top_spread_liquidity_first_replay_engine_missing"]
            if int(fill_summary.get("top_alternative_count") or 0) == 0:
                blockers.append("top_spread_alternatives_not_logged")
            return (
                "wired_replay_gap",
                "blocked",
                blockers,
                "Build the execution-alternative readiness queue before changing spread selection.",
            )
        if sources["execution_alternative_replay_coverage"].get("status") != "loaded":
            blockers = ["execution_alternative_replay_coverage_missing"]
            if int(execution_alternative_summary.get("top_spread_replay_seed_count") or 0) == 0:
                blockers.append("no_top_spread_alternative_seed_rows")
            else:
                blockers.extend(
                    [
                        "top_spread_liquidity_first_replay_engine_missing",
                        "alternate_contract_exit_quote_coverage_missing",
                        "true_top_spread_replay_pnl_rows_missing",
                    ]
                )
            return (
                "built_readiness_blocked",
                "blocked",
                sorted(set(blockers)),
                "Build the execution-alternative coverage replay to separate quote gaps from engine gaps before changing selection.",
            )
        top_count = int(execution_alternative_coverage_summary.get("top_spread_candidate_count") or 0)
        true_top_count = int(execution_alternative_coverage_summary.get("true_top_spread_replay_pnl_count") or 0)
        blockers = []
        if top_count == 0:
            blockers.append("no_top_spread_alternative_seed_rows")
        if execution_alternative_coverage_summary.get("top_spread_entry_quote_coverage_status") != "full":
            blockers.append("top_spread_entry_quote_coverage_incomplete")
        if execution_alternative_coverage_summary.get("top_spread_exit_quote_coverage_status") != "full":
            blockers.append("alternate_contract_exit_quote_coverage_incomplete")
        if top_count and true_top_count == 0:
            blockers.append("true_top_spread_replay_pnl_rows_missing")
        elif true_top_count < top_count:
            blockers.append("true_top_spread_replay_pnl_rows_incomplete")
        if execution_alternative_coverage_summary.get("overall_status") in {"blocked_missing_inputs", "blocked_quote_store_unreadable"}:
            blockers.extend(_as_list(execution_alternative_coverage_summary.get("blockers")))
        return (
            "built_replay_coverage_blocked",
            "blocked" if blockers else "ready",
            sorted(set(str(item) for item in blockers if item)),
            "Use the execution-alternative quote-demand manifest to import/query missing trusted OPRA/NBBO alternative entry and exit quotes, then rerun side-aware coverage before changing selection.",
        )
    if layer_slug == "contract_replacement_exit_survivability":
        if sources["execution_alternative_replay_readiness"].get("status") != "loaded":
            return (
                "wired_replay_gap",
                "blocked",
                ["execution_alternative_replay_readiness_missing", "contract_replacement_exit_survivability_replay_engine_missing"],
                "Build the execution-alternative readiness queue before contract-selection changes.",
            )
        if sources["execution_alternative_replay_coverage"].get("status") != "loaded":
            blockers = ["execution_alternative_replay_coverage_missing"]
            if int(execution_alternative_summary.get("contract_replacement_seed_count") or 0) == 0:
                blockers.append("no_distinct_contract_replacement_seed_rows")
            else:
                blockers.extend(
                    [
                        "contract_replacement_exit_survivability_replay_engine_missing",
                        "alternate_contract_exit_quote_coverage_missing",
                        "true_contract_replacement_pnl_rows_missing",
                    ]
                )
            return (
                "built_readiness_blocked",
                "blocked",
                sorted(set(blockers)),
                "Build the execution-alternative coverage replay before contract-selection changes.",
            )
        replacement_count = int(execution_alternative_coverage_summary.get("contract_replacement_candidate_count") or 0)
        true_replacement_count = int(execution_alternative_coverage_summary.get("true_contract_replacement_pnl_count") or 0)
        blockers = []
        if replacement_count == 0:
            blockers.append("no_distinct_contract_replacement_seed_rows")
        if execution_alternative_coverage_summary.get("contract_replacement_entry_quote_coverage_status") != "full":
            blockers.append("contract_replacement_entry_quote_coverage_incomplete")
        if execution_alternative_coverage_summary.get("contract_replacement_exit_quote_coverage_status") != "full":
            blockers.append("contract_replacement_exit_quote_coverage_incomplete")
        if replacement_count and true_replacement_count == 0:
            blockers.append("true_contract_replacement_pnl_rows_missing")
        elif true_replacement_count < replacement_count:
            blockers.append("true_contract_replacement_pnl_rows_incomplete")
        if execution_alternative_coverage_summary.get("overall_status") in {"blocked_missing_inputs", "blocked_quote_store_unreadable"}:
            blockers.extend(_as_list(execution_alternative_coverage_summary.get("blockers")))
        return (
            "built_replay_coverage_blocked",
            "blocked" if blockers else "ready",
            sorted(set(str(item) for item in blockers if item)),
            "Use the execution-alternative quote-demand manifest to import/query missing trusted OPRA/NBBO replacement entry and exit quotes, then rerun side-aware coverage before contract-selection changes.",
        )
    if layer_slug == "minute_level_exit_quote_deterioration":
        if sources["minute_exit_replay_readiness"].get("status") != "loaded":
            return (
                "wired_replay_gap",
                "blocked",
                ["minute_exit_replay_readiness_missing", "minute_level_exit_replay_missing", "daily_stop_grid_is_not_minute_level_proof"],
                "Build the minute-exit readiness queue before stop/exit policy changes.",
            )
        blockers = list(minute_summary.get("blockers") or [])
        if int(minute_summary.get("true_minute_exit_pnl_count") or 0) == 0:
            blockers.append("true_minute_exit_pnl_rows_missing")
        true_count = int(minute_summary.get("true_minute_exit_pnl_count") or 0)
        return (
            "built_replay_coverage_ready" if true_count and not blockers else "built_readiness_blocked",
            "blocked" if blockers else "ready",
            sorted(set(str(item) for item in blockers if item)),
            "Use the minute-exit readiness queue to build exact OPRA/NBBO minute quote coverage and replay before stop/exit policy changes.",
        )
    if layer_slug == "anti_overfit_controls":
        blockers = list(circuit_summary.get("recovery_gate_failures") or [])
        if sources["overfit_rule_archive"].get("status") != "loaded":
            blockers.append("overfit_rule_archive_missing")
        if int(archive_summary.get("unarchived_reject_overfit_rule_count") or 0) > 0:
            blockers.append("rejected_overfit_rules_unarchived")
        return "built_blocked", "blocked" if blockers else "ready", blockers, "Keep anti-overfit controls active; require later-date and fresh-paper gates before promotion."
    if layer_slug == "rejected_near_miss_outcome_replay":
        blockers = []
        if _counter_get(_as_dict(reports["missed_picks_filter_matrix"].get("summary")), "source_mark_unpriced_count") > 0:
            blockers.append("unpriced_near_miss_rows")
        return "built", "ready" if not blockers else "blocked", blockers, "Use missed-pick outcome and failure-mode readbacks before retesting rejected filters."
    if layer_slug == "tier_a_bridge_watchlist":
        blockers = []
        if int(shortlist_summary.get("eligible_count") or 0) == 0:
            blockers.append("no_paper_shortlist_candidates")
        if int(queue_summary.get("tier_a_fresh_match_bridge_count") or 0) == 0:
            blockers.append("no_tier_a_fresh_match_bridge")
        return "built_collecting", "collecting", blockers, "Watch Tier A clean exact rows until a fresh executable lane-signature bridge appears."
    if layer_slug == "source_replay_repair_burndown":
        blockers = []
        if int(repair_summary.get("active_unattempted_exact_target_count") or 0) > 0:
            blockers.append("active_unattempted_exact_targets")
        if int(repair_summary.get("source_replay_required_target_count") or 0) > 0:
            blockers.append("source_replay_required_targets")
        return "built_collecting", "collecting" if blockers else "ready", blockers, "Run source replays before more provider imports or any repair graduation."
    if layer_slug == "lane_lab_freshness_reconciler":
        blockers = []
        if int(lane_summary.get("live_validation_lane_count") or 0) == 0:
            blockers.append("no_live_validation_lanes")
        if lane_summary.get("open_risk_governor_status") == "open_risk_governor_blocked":
            blockers.append("open_risk_governor_blocked")
        return "built_blocked", "blocked", blockers, "Regenerate lane promotion, circuit-breaker, and guardrail-starvation readbacks before candidate routing."
    if layer_slug == "portfolio_throttle_replay":
        blockers = list(multilane_quality.get("blockers") or [])
        status = _norm(multilane_quality.get("overall_status") or multilane_quality.get("status"))
        return "built_blocked", "blocked" if status and status != "pass" else "ready", blockers or [f"quality_gate:{status}"], "Use portfolio replay as throttle evidence; do not treat count success as quality success."
    if layer_slug == "risk_budget_sizing_replay":
        if sources["risk_budget_sizing_replay"].get("status") != "loaded":
            blockers = []
            if open_governor.get("live_entry_allowed") is False:
                blockers.append("open_risk_governor_blocks_sizing")
            blockers.append("risk_budget_sizing_replay_missing")
            return "wired_replay_gap", "blocked", blockers, "Build sizing replay from exact evidence and open-risk governor before changing size tiers."
        if reports["risk_budget_sizing_replay"].get("status") == "invalid_live_policy_change":
            return (
                "built_blocked",
                "blocked",
                ["risk_budget_sizing_replay_invalid_live_policy_change"],
                "Repair the sizing replay boundary before using this layer.",
            )
        blockers = []
        blockers.extend(str(item) for item in _as_list(sizing_summary.get("blockers")) if item)
        if reports["risk_budget_sizing_replay"].get("status") == "blocked_missing_inputs":
            blockers.append("risk_budget_sizing_replay_missing_inputs")
            return "built_blocked", "blocked", sorted(set(blockers)), "Repair sizing replay inputs before using it."
        if open_governor.get("live_entry_allowed") is False and "open_risk_governor_blocks_sizing" not in blockers:
            blockers.append("open_risk_governor_blocks_sizing")
        return (
            "built_collecting",
            "collecting",
            sorted(set(blockers)),
            "Use the sizing replay as research readback only; resolve open risk and collect fresh exact sizing evidence before any size-tier change.",
        )
    if layer_slug == "structure_specific_multileg_harness":
        if sources["structure_specific_harness"].get("status") != "loaded":
            blockers = []
            if _counter_get(_as_dict(fill_summary.get("strategy_type_counts")), "vertical_spread") == 0:
                blockers.append("no_vertical_spread_fill_attempt_rows")
            blockers.append("multi_leg_structure_harness_missing")
            return (
                "wired_replay_gap",
                "blocked",
                blockers,
                "Build the structure-specific harness to separate vertical, single-leg, and future multi-leg evidence.",
            )
        structure_status = _norm(reports["structure_specific_harness"].get("status"))
        structure_summary = _as_dict(reports["structure_specific_harness"].get("summary"))
        if structure_status == "invalid_live_policy_change":
            return (
                "built_blocked",
                "blocked",
                ["structure_specific_harness_invalid_live_policy_change"],
                "Repair the structure-specific harness boundary before using this layer.",
            )
        if structure_status == "blocked_missing_inputs":
            blockers = list(structure_summary.get("missing_required_inputs") or ["structure_specific_harness_missing_inputs"])
            return (
                "built_blocked",
                "blocked",
                sorted(set(str(item) for item in blockers if item)),
                "Repair structure-specific harness inputs before using this layer.",
            )
        blockers = [
            str(item)
            for item in _as_list(structure_summary.get("blockers"))
            if item and str(item) != "multi_leg_structure_harness_missing"
        ]
        return (
            "built_collecting",
            "collecting" if blockers else "ready",
            sorted(set(blockers)),
            "Use the structure-specific harness as diagnostic readback; collect true executable entry/fill/exit P&L before any structure-specific promotion claim.",
        )
    if layer_slug == "event_data_spine_post_event_vol_crush":
        if sources["event_data_spine"].get("status") != "loaded":
            return (
                "wired_data_gap",
                "blocked",
                ["event_data_spine_missing", "post_event_vol_crush_replay_missing"],
                "Build event/earnings/vol-crush annotations before event-sensitive lane changes.",
            )
        event_status = _norm(reports["event_data_spine"].get("status"))
        event_summary = _as_dict(reports["event_data_spine"].get("summary"))
        if event_status == "invalid_live_policy_change":
            return (
                "built_blocked",
                "blocked",
                ["event_data_spine_invalid_live_policy_change"],
                "Repair the event spine boundary before using this layer.",
            )
        if event_status == "blocked_missing_inputs":
            blockers = list(event_summary.get("missing_required_inputs") or ["event_data_spine_missing_inputs"])
            return (
                "built_blocked",
                "blocked",
                sorted(set(str(item) for item in blockers if item)),
                "Repair event spine inputs before using this layer.",
            )
        blockers = [
            str(item)
            for item in _as_list(event_summary.get("blockers"))
            if item and str(item) != "event_data_spine_missing"
        ]
        return (
            "built_collecting",
            "collecting" if blockers else "ready",
            sorted(set(blockers)),
            "Use the event data spine as diagnostic readback; collect durable event annotations and true executable post-event P&L before event-sensitive lane changes.",
        )
    return "built", "collecting", [], "Monitor this layer."


def _layer_rows(reports: dict[str, dict[str, Any]], sources: dict[str, dict[str, Any]], fill_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for blueprint in LAYER_BLUEPRINTS:
        artifact_keys = tuple(blueprint["artifact_keys"])
        implementation_status, gate_status, blockers, next_action = _layer_status(
            str(blueprint["slug"]),
            reports,
            sources,
            fill_summary,
        )
        rows.append(
            {
                "layer": blueprint["layer"],
                "slug": blueprint["slug"],
                "title": blueprint["title"],
                "category": blueprint["category"],
                "implementation_status": implementation_status,
                "gate_status": gate_status,
                "metrics": _compact_metrics(str(blueprint["slug"]), reports, fill_summary),
                "primary_blockers": blockers,
                "next_action": next_action,
                "input_artifacts": _input_refs(artifact_keys, sources),
                "owner_commands": list(blueprint["owner_commands"]),
                "read_only": True,
                "live_policy_change": False,
                "prohibited_actions": list(PROHIBITED_ACTIONS),
            }
        )
    return rows


def _overall_status(layers: list[dict[str, Any]], reports: dict[str, dict[str, Any]]) -> str:
    if len(layers) != 20:
        return "layer_stack_invalid_count"
    if any(bool(layer.get("live_policy_change")) for layer in layers):
        return "invalid_live_policy_change"
    open_governor = _as_dict(reports["open_risk"].get("open_risk_governor"))
    if open_governor.get("live_entry_allowed") is False:
        return "all_20_layers_wired_live_blocked_collect_evidence"
    if any(layer.get("gate_status") == "blocked" for layer in layers):
        return "all_20_layers_wired_research_blocked"
    return "all_20_layers_wired_collecting"


def build_report(
    *,
    artifact_paths: dict[str, Path] | None = None,
    fill_attempt_file: Path = DEFAULT_FILL_ATTEMPT_FILE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = dict(DEFAULT_ARTIFACT_PATHS)
    if artifact_paths:
        paths.update(artifact_paths)
    reports: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], sources[key] = _load_json(path)
    fill_rows, fill_meta = _load_jsonl(fill_attempt_file)
    sources["fill_attempts"] = fill_meta
    fill_summary = _fill_attempt_summary(fill_rows)
    layers = _layer_rows(reports, sources, fill_summary)
    implementation_counts = Counter(str(layer["implementation_status"]) for layer in layers)
    gate_counts = Counter(str(layer["gate_status"]) for layer in layers)
    category_counts = Counter(str(layer["category"]) for layer in layers)
    blocked_layers = [
        {
            "layer": layer["layer"],
            "slug": layer["slug"],
            "title": layer["title"],
            "gate_status": layer["gate_status"],
            "primary_blockers": layer["primary_blockers"],
            "next_action": layer["next_action"],
        }
        for layer in layers
        if layer["gate_status"] in {"blocked", "collecting"}
    ]
    return {
        "report_id": REPORT_ID,
        "status": "profitability_layer_stack_readback",
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_profitability_all_20_layers",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": _overall_status(layers, reports),
            "layer_count": len(layers),
            "wired_layer_count": len(layers),
            "expected_layer_count": 20,
            "blocked_or_collecting_layer_count": len(blocked_layers),
            "gate_status_counts": dict(sorted(gate_counts.items())),
            "implementation_status_counts": dict(sorted(implementation_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
            "candidate_ledger_status": _as_dict(reports["candidate_ledger"].get("summary")).get("operating_status"),
            "open_risk_status": _as_dict(reports["open_risk"].get("open_risk_governor")).get("status"),
            "live_policy_change": False,
        },
        "proof_policy": {
            "readback_is": "20-layer profitability iteration control plane for regular supervised options",
            "readback_is_not": "live-release approval, broker recommendation, scanner policy change, stop-policy change, sizing change, or proof-bar reduction",
            "trusted_proof_standard": "fresh executable exact OPRA/NBBO entry evidence plus exact executable exit realized-P&L evidence",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": sources,
        "fill_attempt_summary": fill_summary,
        "blocked_or_collecting_layers": blocked_layers,
        "layers": layers,
    }


def _markdown_cell(value: Any) -> str:
    text = _norm(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Profitability Layer Stack",
        "",
        "This report is generated from `scripts/build_regular_options_profitability_layer_stack.py`. It wires the 20 profitability iteration layers into one read-only control plane without changing scanner, broker, auth, DB, stop, sizing, or proof behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Layers wired: `{summary.get('wired_layer_count')}` / `{summary.get('expected_layer_count')}`.",
        f"- Blocked or collecting layers: `{summary.get('blocked_or_collecting_layer_count')}`.",
        f"- Gate statuses: `{_json_inline(summary.get('gate_status_counts') or {})}`.",
        f"- Implementation statuses: `{_json_inline(summary.get('implementation_status_counts') or {})}`.",
        f"- Candidate ledger status: `{summary.get('candidate_ledger_status')}`.",
        f"- Open-risk status: `{summary.get('open_risk_status')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Layer Table",
        "",
        "| # | Layer | Implementation | Gate | Blockers | Next action |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for layer in _as_list(report.get("layers")):
        if not isinstance(layer, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{layer.get('layer')}`",
                    _markdown_cell(layer.get("title")),
                    f"`{layer.get('implementation_status')}`",
                    f"`{layer.get('gate_status')}`",
                    _markdown_cell(", ".join(str(item) for item in _as_list(layer.get("primary_blockers"))) or "none"),
                    _markdown_cell(layer.get("next_action")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "All 20 layers are wired as readbacks. Blocked or collecting states are intentional fail-closed outputs when market-window evidence, exact exit evidence, source replay, or a deeper replay harness is missing. This stack does not create trades, submit broker orders, change scanner policy, change stops, change sizing, mutate DB state, lower proof bars, or promote paper/research evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    generated_at = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "")
    json_path = output_dir / f"{REPORT_ID}_{generated_at}.json"
    md_path = output_dir / f"{REPORT_ID}_{generated_at}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the all-20 regular-options profitability layer stack.")
    parser.add_argument("--fill-attempt-file", type=Path, default=DEFAULT_FILL_ATTEMPT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(fill_attempt_file=args.fill_attempt_file)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
