from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_current_regime_lane_incubator"

DEFAULT_MONTHLY_AUDIT = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_HYPOTHESIS_TOURNAMENT = ROOT / "data" / "profitability-lab" / "regular-options-hypothesis-tournament" / "latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_GOAL_LOOP = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-lane-incubator"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-current-regime-lane-incubator.md"

CONCEPT_STATUSES = {
    "read_only_research_design_ready",
    "requires_operator_approval_for_strategy_implementation",
    "requires_operator_approval_for_quote_import_or_data_surface",
    "blocked_by_existing_no_chase_or_quarantine",
    "blocked_by_missing_replay_engine",
    "blocked_by_missing_exact_opra_nbbo_coverage",
    "blocked_by_event_data_missing",
    "duplicate_of_existing_candidate",
}

READ_ONLY_FLAGS = {
    "read_only": True,
    "lane_implementation_performed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_current_regime_lane_incubator",
    "do_not_submit_broker_orders_from_current_regime_lane_incubator",
    "do_not_enable_auto_track_from_current_regime_lane_incubator",
    "do_not_enable_live_validation_from_current_regime_lane_incubator",
    "do_not_change_scanner_policy_from_current_regime_lane_incubator",
    "do_not_change_strategy_logic_from_current_regime_lane_incubator",
    "do_not_change_stops_from_current_regime_lane_incubator",
    "do_not_change_sizing_from_current_regime_lane_incubator",
    "do_not_lower_proof_bars_from_current_regime_lane_incubator",
    "do_not_import_quotes_from_current_regime_lane_incubator",
    "do_not_mutate_evidence_databases_from_current_regime_lane_incubator",
    "do_not_consume_protected_holdout_from_current_regime_lane_incubator",
    "do_not_treat_historical_rows_as_forward_proof",
)

REQUIRED_CONCEPT_FIELDS = (
    "concept_id",
    "regime_thesis",
    "structure_family",
    "candidate_universe",
    "intended_market_condition",
    "why_existing_lanes_do_not_already_cover_it",
    "data_available_from_existing_repo_artifacts",
    "trusted_opra_nbbo_evaluation_path",
    "required_engine_support",
    "expected_proof_blockers",
    "approval_required_before_implementation",
    "approval_required_before_quote_import",
    "approval_required_before_forward_collection",
    "proof_acceptance_plan",
    "do_not_trade_or_promote",
)


def _utc_now_iso() -> str:
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


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "error": None,
    }
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
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _candidate_ids(*payloads: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for payload in payloads:
        for row in _as_list(payload.get("candidate_rankings")):
            row_dict = _as_dict(row)
            candidate_id = str(row_dict.get("candidate_id") or "").strip()
            lane_id = str(row_dict.get("lane_id") or "").strip()
            if candidate_id:
                ids.add(candidate_id)
            if lane_id:
                ids.add(lane_id)
    return ids


def _monthly_summary(monthly: dict[str, Any]) -> dict[str, Any]:
    lane_dispositions = _as_dict(monthly.get("lane_dispositions"))
    counts = _as_dict(lane_dispositions.get("status_counts") or lane_dispositions.get("counts"))
    summary = _as_dict(monthly.get("summary"))
    return {
        "overall_status": monthly.get("overall_status") or summary.get("overall_status"),
        "baseline_profit_factor": monthly.get("baseline_profit_factor") or summary.get("baseline_profit_factor"),
        "baseline_avg_net_pnl_pct": monthly.get("baseline_avg_net_pnl_pct")
        or summary.get("baseline_avg_net_pnl_pct"),
        "recent_month": monthly.get("recent_month") or summary.get("recent_month"),
        "recent_month_health": monthly.get("recent_month_health") or summary.get("recent_month_health"),
        "lane_disposition_counts": counts,
        "paper_shadow_count": _safe_int(counts.get("paper_shadow")),
        "profitable_candidate_count": _safe_int(counts.get("profitable_candidate")),
        "quarantine_count": _safe_int(counts.get("quarantine")),
        "retest_count": _safe_int(counts.get("retest")),
    }


def _goal_loop_summary(goal_loop: dict[str, Any]) -> dict[str, Any]:
    acceptance = _as_dict(goal_loop.get("acceptance_readiness"))
    accounting = _as_dict(goal_loop.get("forward_evidence_accounting"))
    return {
        "status": goal_loop.get("status") or goal_loop.get("goal_status"),
        "post_freeze_strict_exact_completed_rows": _safe_int(
            acceptance.get("post_freeze_strict_exact_completed_rows")
            or accounting.get("post_freeze_strict_exact_completed_rows")
        ),
        "required_strict_exact_rows": _safe_int(
            acceptance.get("required_strict_exact_rows") or accounting.get("required_strict_exact_rows"), 30
        ),
        "strict_usd_pf_lower_bound": acceptance.get("strict_usd_pf_lower_bound"),
        "promotion_ready": bool(goal_loop.get("promotion_ready") or acceptance.get("promotion_ready")),
    }


def _proof_context(monthly: dict[str, Any], tournament: dict[str, Any], robust_edge: dict[str, Any], goal_loop: dict[str, Any]) -> dict[str, Any]:
    monthly_read = _monthly_summary(monthly)
    goal = _goal_loop_summary(goal_loop)
    return {
        "accepted_profitability": False,
        "new_lanes_are_research_concepts_only": True,
        "operator_approval_required_before_implementation": True,
        "historical_rows_are_not_forward_proof": True,
        "monthly": monthly_read,
        "hypothesis_tournament": {
            "candidate_count": _safe_int(tournament.get("candidate_count")),
            "forward_freeze_candidate": _as_dict(tournament.get("forward_freeze_candidate_spec")).get("status")
            or "not_recommended",
            "best_candidate": _as_dict(tournament.get("best_candidate_if_any")).get("candidate_id"),
            "blocked_candidate_count": _safe_int(tournament.get("blocked_candidate_count")),
            "rejected_candidate_count": _safe_int(tournament.get("rejected_candidate_count")),
        },
        "robust_edge": {
            "candidate_count": _safe_int(robust_edge.get("candidate_count")),
            "robust_candidate_count": _safe_int(robust_edge.get("robust_candidate_count")),
            "paper_shadow_candidate_count": _safe_int(robust_edge.get("paper_shadow_candidate_count")),
            "best_candidate": _as_dict(robust_edge.get("best_candidate_if_any")).get("candidate_id"),
        },
        "goal_loop": goal,
    }


def _concept(
    *,
    concept_id: str,
    regime_thesis: str,
    structure_family: str,
    candidate_universe: list[str],
    intended_market_condition: str,
    why_existing_lanes_do_not_already_cover_it: str,
    data_available_from_existing_repo_artifacts: str,
    trusted_opra_nbbo_evaluation_path: str,
    required_engine_support: list[str],
    expected_proof_blockers: list[str],
    status: str,
    proof_feasibility_rank: int,
    approval_required_before_implementation: bool,
    approval_required_before_quote_import: bool,
    approval_required_before_forward_collection: bool = True,
    duplicate_of: str | None = None,
) -> dict[str, Any]:
    if status not in CONCEPT_STATUSES:
        raise ValueError(f"unknown concept status {status}")
    return {
        "concept_id": concept_id,
        "status": status,
        "proof_feasibility_rank": proof_feasibility_rank,
        "regime_thesis": regime_thesis,
        "structure_family": structure_family,
        "candidate_universe": candidate_universe,
        "intended_market_condition": intended_market_condition,
        "why_existing_lanes_do_not_already_cover_it": why_existing_lanes_do_not_already_cover_it,
        "data_available_from_existing_repo_artifacts": data_available_from_existing_repo_artifacts,
        "trusted_opra_nbbo_evaluation_path": trusted_opra_nbbo_evaluation_path,
        "required_engine_support": required_engine_support,
        "expected_proof_blockers": expected_proof_blockers,
        "approval_required_before_implementation": approval_required_before_implementation,
        "approval_required_before_quote_import": approval_required_before_quote_import,
        "approval_required_before_forward_collection": approval_required_before_forward_collection,
        "proof_acceptance_plan": [
            "preregister concept before implementation",
            "evaluate with point-in-time trusted OPRA/NBBO bid/ask evidence where available",
            "require chronological split and final holdout before nomination",
            "freeze any surviving candidate before forward paper-shadow collection",
            "require at least 30 post-freeze strict exact realized USD rows before promotion discussion",
        ],
        "do_not_trade_or_promote": True,
        "duplicate_of": duplicate_of,
    }


def _build_concepts(candidate_ids: set[str]) -> list[dict[str, Any]]:
    has_smh = any("smh" in item.lower() for item in candidate_ids)
    has_xle = any("xle" in item.lower() for item in candidate_ids)
    has_volatility = any("volatility_expansion_observation" in item for item in candidate_ids)

    concepts = [
        _concept(
            concept_id="regime_momentum_continuation_debit_spread",
            regime_thesis="Strong broad/index momentum and strong QQQ/SMH leadership can justify a preregistered debit-spread continuation concept.",
            structure_family="defined_risk_debit_call_spread",
            candidate_universe=["SPY", "QQQ", "IWM", "SMH"],
            intended_market_condition="low_to_mid_vix_with_growth_or_semiconductor_leadership",
            why_existing_lanes_do_not_already_cover_it=(
                "Existing index/refill and SMH variants appear in prior tournaments, but no current concept is preregistered "
                "as a current-regime lane with explicit proof feasibility and approval gates."
            ),
            data_available_from_existing_repo_artifacts=(
                "SPY/QQQ/IWM are present in current proof surfaces; SMH appears in candidate history."
                if has_smh
                else "SPY/QQQ/IWM are present; SMH needs explicit coverage verification before replay."
            ),
            trusted_opra_nbbo_evaluation_path="Use existing trusted ThetaData OPRA/NBBO exact-contract replay only after a separately approved research playbook exists.",
            required_engine_support=["existing debit-spread replay", "point-in-time candidate diagnostics"],
            expected_proof_blockers=["sample_size", "winner_concentration", "recent_2026_05_break", "holdout_depth"],
            status="read_only_research_design_ready",
            proof_feasibility_rank=1,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=not has_smh,
        ),
        _concept(
            concept_id="regime_rotation_dispersion_hedge",
            regime_thesis="High dispersion and concentration risk can justify a hedged rotation concept rather than another one-way momentum chase.",
            structure_family="defined_risk_put_or_relative_rotation_spread",
            candidate_universe=["SPY", "QQQ", "IWM", "sector_etfs"],
            intended_market_condition="index_vol_subdued_with_single_stock_dispersion_and_rotation_risk",
            why_existing_lanes_do_not_already_cover_it="Existing bearish/sector variants were mostly rejected or fragile; this would be a new preregistered hedge thesis.",
            data_available_from_existing_repo_artifacts="Index underlyings are covered; sector ETF coverage must be checked concept by concept.",
            trusted_opra_nbbo_evaluation_path="Read-only historical replay if candidate generation can be expressed through existing exact-contract chain-native engine.",
            required_engine_support=["relative strength/weakness signal readback", "defined-risk spread replay"],
            expected_proof_blockers=["missing_sector_coverage", "thin_hedge_samples", "negative_existing_bearish_put_shapes"],
            status="requires_operator_approval_for_strategy_implementation",
            proof_feasibility_rank=2,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=True,
        ),
        _concept(
            concept_id="regime_low_mid_vix_defined_risk_credit_income",
            regime_thesis="Low-to-mid VIX can make defined-risk credit income attractive, but only if assignment, margin, and side-aware credit spread execution are modeled.",
            structure_family="defined_risk_credit_spread_or_iron_condor",
            candidate_universe=["SPY", "QQQ", "IWM"],
            intended_market_condition="low_to_mid_vix_with_range_or_grinding_trend",
            why_existing_lanes_do_not_already_cover_it="Current proof stack is debit-spread centric; credit-spread margin, assignment, and expiration risk are not proven as production gates.",
            data_available_from_existing_repo_artifacts="Underlying option quotes may exist, but credit-spread proof semantics are not established by current reports.",
            trusted_opra_nbbo_evaluation_path="Blocked until side-aware credit entry/exit, assignment/expiration, max loss, and margin conventions are implemented and tested.",
            required_engine_support=["credit-spread bid/ask accounting", "assignment/expiration model", "margin/max-loss risk model"],
            expected_proof_blockers=["missing_credit_replay_engine", "assignment_risk", "margin_model_missing"],
            status="blocked_by_missing_replay_engine",
            proof_feasibility_rank=3,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=False,
        ),
        _concept(
            concept_id="regime_volatility_expansion_breakout_hedge",
            regime_thesis="Dispersion and possible volatility expansion support a breakout/hedge concept, but the repo already has a volatility expansion paper-shadow candidate.",
            structure_family="defined_risk_debit_spread_breakout_or_hedge",
            candidate_universe=["SPY", "QQQ", "IWM"],
            intended_market_condition="volatility_expansion_or_breakout_after_low_index_vol",
            why_existing_lanes_do_not_already_cover_it=(
                "It is already partially covered by volatility_expansion_observation; new work must not duplicate or promote that lane."
            ),
            data_available_from_existing_repo_artifacts="Existing volatility expansion artifacts are available, but forward proof remains 0/30.",
            trusted_opra_nbbo_evaluation_path="Use existing paper-shadow evidence path first; do not create duplicate active lane behavior.",
            required_engine_support=["existing volatility expansion paper-shadow harness"],
            expected_proof_blockers=["duplicate_existing_candidate", "fresh_forward_rows_missing", "no_exact_realized_pnl_rows"],
            status="duplicate_of_existing_candidate" if has_volatility else "requires_operator_approval_for_strategy_implementation",
            proof_feasibility_rank=4,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=False,
            duplicate_of="volatility_expansion_observation" if has_volatility else None,
        ),
        _concept(
            concept_id="regime_weak_sector_relative_weakness",
            regime_thesis="Weak energy or other laggards can justify bearish or relative-weakness structures, but existing bearish/sector variants are fragile.",
            structure_family="defined_risk_put_debit_spread_or_relative_weakness_spread",
            candidate_universe=["XLE", "weak_recent_ticker_clusters"],
            intended_market_condition="sector_laggards_underperforming_growth_or_index_leadership",
            why_existing_lanes_do_not_already_cover_it="Existing XLE and bearish variants show no current candidates or weak/fragile proof in current reports.",
            data_available_from_existing_repo_artifacts=(
                "XLE appears in prior candidate surfaces but needs exact OPRA/NBBO coverage and candidate-generation confirmation."
                if has_xle
                else "No reliable current XLE proof path is visible from attached candidate reports."
            ),
            trusted_opra_nbbo_evaluation_path="Blocked until exact coverage and current candidate-generation path are confirmed for the selected weak-sector universe.",
            required_engine_support=["bearish debit-spread replay", "sector coverage diagnostic"],
            expected_proof_blockers=["existing_bearish_shapes_negative", "missing_exact_opra_nbbo_coverage", "no_current_candidates"],
            status="blocked_by_missing_exact_opra_nbbo_coverage",
            proof_feasibility_rank=3,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=True,
        ),
        _concept(
            concept_id="regime_event_catalyst_defined_risk",
            regime_thesis="Events can create options opportunity, but event lanes need reliable event annotation and a no-lookahead data spine.",
            structure_family="defined_risk_event_debit_or_credit_spread",
            candidate_universe=["earnings_or_macro_event_symbols"],
            intended_market_condition="known_event_or_catalyst_with_predeclared_entry_exit",
            why_existing_lanes_do_not_already_cover_it="The current monthly audit shows event-data-spine work as collecting, not proof-ready.",
            data_available_from_existing_repo_artifacts="Event annotations are not a complete proof path in current readbacks.",
            trusted_opra_nbbo_evaluation_path="Blocked until event data is point-in-time, no-lookahead, and joined to exact OPRA/NBBO replay.",
            required_engine_support=["event data spine", "event window preregistration", "no-lookahead event joins"],
            expected_proof_blockers=["event_data_missing", "lookahead_risk", "small_sample"],
            status="blocked_by_event_data_missing",
            proof_feasibility_rank=4,
            approval_required_before_implementation=True,
            approval_required_before_quote_import=True,
        ),
    ]
    return sorted(concepts, key=lambda row: (row["proof_feasibility_rank"], row["concept_id"]))


def _status(concepts: list[dict[str, Any]]) -> str:
    if any(row["status"] == "read_only_research_design_ready" for row in concepts):
        return "current_regime_lane_incubator_ready_for_operator_review"
    return "current_regime_lane_incubator_blocked"


def build_report(
    *,
    monthly_audit_path: Path = DEFAULT_MONTHLY_AUDIT,
    hypothesis_tournament_path: Path = DEFAULT_HYPOTHESIS_TOURNAMENT,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    goal_loop_path: Path = DEFAULT_GOAL_LOOP,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    monthly, monthly_meta = _load_json(monthly_audit_path, required=True)
    tournament, tournament_meta = _load_json(hypothesis_tournament_path, required=True)
    robust_edge, robust_meta = _load_json(robust_edge_path, required=True)
    goal_loop, goal_meta = _load_json(goal_loop_path, required=False)

    ids = _candidate_ids(tournament, robust_edge)
    concepts = _build_concepts(ids)
    concept_counts = Counter(row["status"] for row in concepts)
    proof_context = _proof_context(monthly, tournament, robust_edge, goal_loop)

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at,
        "status": _status(concepts),
        **READ_ONLY_FLAGS,
        "accepted_profitability": False,
        "new_lanes_are_research_concepts_only": True,
        "operator_approval_required_before_implementation": True,
        "historical_rows_are_not_forward_proof": True,
        "regime_snapshot": {
            "as_of_date": "2026-06-22",
            "source": "operator_supplied_plus_live_quote_snapshot",
            "conditions": [
                "strong broad/index momentum",
                "strong QQQ/SMH technology and semiconductor leadership",
                "low-to-mid VIX",
                "elevated dispersion and rotation risk",
                "weak energy relative to growth leadership",
            ],
            "not_trade_advice": True,
        },
        "source_artifacts": {
            "monthly_audit": monthly_meta,
            "hypothesis_tournament": tournament_meta,
            "robust_edge_discovery": robust_meta,
            "goal_loop": goal_meta,
        },
        "proof_context": proof_context,
        "concept_count": len(concepts),
        "concept_status_counts": dict(sorted(concept_counts.items())),
        "concepts": concepts,
        "best_next_operator_question": (
            "Approve implementation of one read-only research playbook for "
            "`regime_momentum_continuation_debit_spread`, writing only derived research artifacts, "
            "with no live validation, no auto-track, no broker, no quote import, no evidence-store mutation, "
            "no protected-holdout use, and no promotion."
        ),
        "approval_required_later_for": [
            "adding a new scanner playbook",
            "editing scanner or strategy logic",
            "changing stops or sizing",
            "implementing credit-spread execution logic",
            "adding or expanding universe symbols not already covered by trusted exact OPRA/NBBO data",
            "importing quotes",
            "mutating evidence stores",
            "running a source replay that overwrites canonical artifacts",
            "using protected holdout",
            "opening live validation",
            "enabling auto-track",
            "submitting broker or paper-broker orders",
            "promoting a lane",
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    _validate_report_shape(report)
    return report


def _validate_report_shape(report: dict[str, Any]) -> None:
    for key, value in READ_ONLY_FLAGS.items():
        if report.get(key) is not value:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("incubator cannot mark profitability accepted")
    for concept in _as_list(report.get("concepts")):
        missing = [field for field in REQUIRED_CONCEPT_FIELDS if field not in _as_dict(concept)]
        if missing:
            raise ValueError(f"concept {concept.get('concept_id')} missing fields: {missing}")
        if concept.get("status") not in CONCEPT_STATUSES:
            raise ValueError(f"concept {concept.get('concept_id')} has invalid status")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    proof = _as_dict(report.get("proof_context"))
    monthly = _as_dict(proof.get("monthly"))
    goal = _as_dict(proof.get("goal_loop"))
    lines = [
        "# Regular Options Current-Regime Lane Incubator",
        "",
        "This report is generated from `scripts/build_regular_options_current_regime_lane_incubator.py`. It preregisters lane concepts only. It does not implement scanner logic, create trades, import quotes, mutate evidence stores, enable live validation or auto-track, submit broker orders, consume protected holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Concepts: `{report['concept_count']}`.",
        f"- Concept status counts: `{json.dumps(report['concept_status_counts'], sort_keys=True)}`.",
        f"- Existing profitable candidate lanes: `{monthly.get('profitable_candidate_count')}`.",
        f"- Existing paper-shadow lanes: `{monthly.get('paper_shadow_count')}`.",
        f"- Forward strict rows: `{goal.get('post_freeze_strict_exact_completed_rows')}` / `{goal.get('required_strict_exact_rows')}`.",
        "",
        "## Current-Regime Snapshot",
        "",
    ]
    for condition in _as_list(_as_dict(report.get("regime_snapshot")).get("conditions")):
        lines.append(f"- {condition}.")
    lines.extend(
        [
            "",
            "## Concept Rankings",
            "",
            "| Rank | Concept | Status | Structure | Universe | Approval Before Implementation | Approval Before Quote Import |",
            "|---:|---|---|---|---|---|---|",
        ]
    )
    for row in _as_list(report.get("concepts")):
        row = _as_dict(row)
        lines.append(
            "| "
            f"{row.get('proof_feasibility_rank')} | "
            f"`{row.get('concept_id')}` | "
            f"`{row.get('status')}` | "
            f"{row.get('structure_family')} | "
            f"{', '.join(_as_list(row.get('candidate_universe')))} | "
            f"`{_fmt_bool(row.get('approval_required_before_implementation'))}` | "
            f"`{_fmt_bool(row.get('approval_required_before_quote_import'))}` |"
        )
    lines.extend(["", "## Concept Details", ""])
    for row in _as_list(report.get("concepts")):
        row = _as_dict(row)
        lines.extend(
            [
                f"### `{row.get('concept_id')}`",
                "",
                f"- Status: `{row.get('status')}`.",
                f"- Regime thesis: {row.get('regime_thesis')}",
                f"- Why not already covered: {row.get('why_existing_lanes_do_not_already_cover_it')}",
                f"- Existing data: {row.get('data_available_from_existing_repo_artifacts')}",
                f"- Evaluation path: {row.get('trusted_opra_nbbo_evaluation_path')}",
                f"- Expected blockers: `{', '.join(_as_list(row.get('expected_proof_blockers')))}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            f"- New lanes are research concepts only: `{_fmt_bool(report['new_lanes_are_research_concepts_only'])}`.",
            f"- Operator approval required before implementation: `{_fmt_bool(report['operator_approval_required_before_implementation'])}`.",
            f"- Historical rows are not forward proof: `{_fmt_bool(report['historical_rows_are_not_forward_proof'])}`.",
            "",
            "## Best Next Operator Question",
            "",
            report["best_next_operator_question"],
            "",
            "## Prohibited Actions",
            "",
        ]
    )
    lines.extend(f"- `{action}`" for action in report["prohibited_actions"])
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
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    markdown = render_markdown(report)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only current-regime lane incubator report.")
    parser.add_argument("--monthly-audit", type=Path, default=DEFAULT_MONTHLY_AUDIT)
    parser.add_argument("--hypothesis-tournament", type=Path, default=DEFAULT_HYPOTHESIS_TOURNAMENT)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--goal-loop", type=Path, default=DEFAULT_GOAL_LOOP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        monthly_audit_path=args.monthly_audit,
        hypothesis_tournament_path=args.hypothesis_tournament,
        robust_edge_path=args.robust_edge,
        goal_loop_path=args.goal_loop,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
