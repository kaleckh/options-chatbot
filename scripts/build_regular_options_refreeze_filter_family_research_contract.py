from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_refreeze_filter_family_research_contract"
CONTRACT_ID = "regular_options_refreeze_filter_family_research_contract_v1"

DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_EVIDENCE_BAR_CONTRACT = ROOT / "data" / "contracts" / "regular-options-filtered-forward-evidence-bar-v1.json"
DEFAULT_AUDIT_WINDOW_REGISTRY = ROOT / "data" / "contracts" / "regular-options-audit-window-consumption-registry.json"
DEFAULT_PROJECTION = ROOT / "data" / "forward-tracking" / "regular-options-forward-evidence-bar-throughput-projection" / "latest.json"
DEFAULT_STATIONARITY = ROOT / "data" / "profitability-lab" / "regular-options-materializer-match-rate-stationarity" / "latest.json"
DEFAULT_DROP_DECOMPOSITION = ROOT / "data" / "forward-tracking" / "regular-options-phase2-drop-decomposition" / "latest.json"
DEFAULT_PARITY = ROOT / "data" / "forward-tracking" / "regular-options-scanner-materializer-parity-diff" / "latest.json"
DEFAULT_TRACKER = ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow" / "latest.json"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "contracts" / "regular-options-refreeze-filter-family-research-contract-v1.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-refreeze-filter-family-research-contract.md"

FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "forward_rows_are_profitability_proof": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "filter_or_threshold_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

PROHIBITED_ACTIONS = [
    "do_not_change_current_frozen_policy_from_this_contract",
    "do_not_change_scanner_policy_from_this_contract",
    "do_not_change_filters_or_thresholds_from_this_contract",
    "do_not_change_proof_bars_from_this_contract",
    "do_not_append_cohort_rows_from_this_contract",
    "do_not_import_quotes_from_this_contract",
    "do_not_mutate_evidence_stores_from_this_contract",
    "do_not_consume_protected_holdout_from_this_contract",
    "do_not_enable_live_validation_from_this_contract",
    "do_not_enable_auto_track_from_this_contract",
    "do_not_submit_broker_orders_from_this_contract",
    "do_not_promote_any_lane_from_this_contract",
    "do_not_treat_historical_rows_or_diagnostics_as_forward_proof",
]


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


def _safe_int(value: Any) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "sha256": _sha256(path)}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "invalid_json"
        meta["error"] = f"{exc.lineno}:{exc.colno}"
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid_payload"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("frozen_at_utc") or payload.get("updated_at_utc")
    return payload, meta


def _consumed_windows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in _as_list(registry.get("entries")):
        item = _as_dict(entry)
        if not item:
            continue
        rows.append(
            {
                "window_months": _as_list(item.get("window_months")),
                "consumed_by": item.get("consumed_by"),
                "consumed_at_utc": item.get("consumed_at_utc"),
                "selection_permitted": item.get("selection_permitted"),
                "filter_iteration_permitted": item.get("filter_iteration_permitted"),
                "new_filter_family_permitted": item.get("new_filter_family_permitted"),
                "threshold_change_permitted": item.get("threshold_change_permitted"),
                "disposition": item.get("disposition"),
            }
        )
    return rows


def _drop_decomposition_summary(drop_decomposition: dict[str, Any]) -> dict[str, Any]:
    scheduled = _as_dict(drop_decomposition.get("scheduled_phase2_throughput"))
    symbol_decomp = _as_dict(drop_decomposition.get("symbol_reason_decomposition"))
    survival = _as_dict(drop_decomposition.get("production_gate_survival"))
    aggregate_counts = _as_dict(drop_decomposition.get("aggregate_drop_counts"))
    top_drop_keys = (
        _as_list(symbol_decomp.get("top_drop_keys"))
        or _as_list(drop_decomposition.get("top_drop_keys"))
        or _as_list(drop_decomposition.get("top_drop_reasons"))
    )
    total = (
        _safe_int(scheduled.get("recorded_drop_denominator"))
        or sum(_safe_int(value) for value in aggregate_counts.values())
        or _safe_int(drop_decomposition.get("scheduled_phase2_drop_count_total"))
        or _safe_int(drop_decomposition.get("scheduled_drop_count_total"))
    )
    return {
        "scheduled_phase2_drop_count_total": total,
        "aggregate_drop_counts": aggregate_counts,
        "top_drop_keys": top_drop_keys[:5],
        "scheduled_phase2_throughput": {
            "session_count": scheduled.get("session_count"),
            "raw_candidates": scheduled.get("raw_candidates"),
            "returned_picks": scheduled.get("returned_picks"),
            "returned_pick_rate_over_recorded_drops": scheduled.get("returned_pick_rate_over_recorded_drops"),
        },
        "drop_share_by_gate_category": _as_list(survival.get("drop_share_by_gate_category"))[:5],
    }


def _trigger_context(projection: dict[str, Any], stationarity: dict[str, Any], tracker: dict[str, Any]) -> dict[str, Any]:
    tracker_forward = _as_dict(tracker.get("forward_tracking"))
    completed_rows = _safe_int(tracker_forward.get("completed_candidate_count"))
    matched_rows = _safe_int(tracker_forward.get("matched_candidate_count"))
    projection_status = str(projection.get("status") or "")
    stationarity_status = str(stationarity.get("status") or "")
    trigger_statuses = {
        "post_freeze_zero_regime_break_trigger_reached",
        "post_freeze_zero_regime_break_confirmed",
    }
    return {
        "projection_status": projection_status,
        "stationarity_status": stationarity_status,
        "matched_forward_rows": matched_rows,
        "completed_forward_rows": completed_rows,
        "evidence_bar_completed_rows_required": _safe_int(
            _as_dict(projection.get("evidence_bar_requirements")).get("required_completed_forward_rows")
        )
        or 30,
        "operator_may_consider_research_contract_now": projection_status == "bar_unreachable_without_state_change",
        "zero_run_trigger_active": stationarity_status in trigger_statuses,
        "current_forward_denominator_empty": matched_rows == 0 and completed_rows == 0,
        "mandatory_checkpoint_dates": {
            "zero_run_regime_break_trigger_if_zero_continues": "2026-07-20",
            "phase2_forward_cohort_checkpoint": "2026-07-28",
            "zero_run_confirmation_if_zero_continues": "2026-08-12",
            "freeze_anchored_four_month_audit": "2026-10-14",
        },
    }


def build_contract(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    evidence_bar_contract_path: Path = DEFAULT_EVIDENCE_BAR_CONTRACT,
    audit_window_registry_path: Path = DEFAULT_AUDIT_WINDOW_REGISTRY,
    projection_path: Path = DEFAULT_PROJECTION,
    stationarity_path: Path = DEFAULT_STATIONARITY,
    drop_decomposition_path: Path = DEFAULT_DROP_DECOMPOSITION,
    parity_path: Path = DEFAULT_PARITY,
    tracker_path: Path = DEFAULT_TRACKER,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    policy, policy_meta = _load_json(policy_contract_path)
    evidence_bar, evidence_bar_meta = _load_json(evidence_bar_contract_path)
    registry, registry_meta = _load_json(audit_window_registry_path)
    projection, projection_meta = _load_json(projection_path)
    stationarity, stationarity_meta = _load_json(stationarity_path)
    drop_decomposition, drop_meta = _load_json(drop_decomposition_path)
    parity, parity_meta = _load_json(parity_path)
    tracker, tracker_meta = _load_json(tracker_path)

    inputs = {
        "current_frozen_policy_contract": policy_meta,
        "current_forward_evidence_bar_contract": evidence_bar_meta,
        "audit_window_consumption_registry": registry_meta,
        "forward_evidence_bar_throughput_projection": projection_meta,
        "materializer_match_rate_stationarity": stationarity_meta,
        "phase2_drop_decomposition": drop_meta,
        "scanner_materializer_parity_diff": parity_meta,
        "filtered_forward_paper_shadow_tracker": tracker_meta,
    }
    blockers = [f"{name}_not_loaded" for name, meta in inputs.items() if meta.get("status") != "loaded"]
    trigger_context = _trigger_context(projection, stationarity, tracker)
    drop_summary = _drop_decomposition_summary(drop_decomposition)

    contract = {
        "report_id": REPORT_ID,
        "contract_id": CONTRACT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": "blocked_missing_context" if blockers else "refreeze_filter_family_research_contract_ready",
        "activation_status": "not_activated_operator_approval_required",
        "read_only": True,
        "research_only": True,
        "approval_authority": False,
        "fresh_fable_readback_available": False,
        "fable_basis": "derived_from_last_validated_fable_guidance_and_current_repo_artifacts_while_cli_auth_is_unavailable",
        "objective": "Pre-register the only safe path for considering a future frozen-policy refreeze or filter-family research proposal after the forward evidence denominator stayed empty.",
        "current_policy_preserved": {
            "policy_id": policy.get("policy_id"),
            "filter_id": policy.get("filter_id"),
            "conditions_sha256": policy.get("conditions_sha256"),
            "tracking_start_at_utc": policy.get("tracking_start_at_utc"),
            "path": policy_meta["path"],
            "sha256": policy_meta["sha256"],
        },
        "current_evidence_bar_preserved": {
            "bar_id": evidence_bar.get("bar_id"),
            "requirements": _as_dict(evidence_bar.get("requirements")),
            "path": evidence_bar_meta["path"],
            "sha256": evidence_bar_meta["sha256"],
        },
        "trigger_context": trigger_context,
        "blocked_or_consumed_selection_windows": _consumed_windows(registry),
        "allowed_research_questions": [
            {
                "id": "production_gate_drop_key_family_hypotheses",
                "basis": "Use Phase 2 drop decomposition to propose falsifiable families around momentum, option_liquidity, and history_or_liquidity drops.",
                "current_evidence": {
                    "scheduled_phase2_drop_count_total": drop_summary["scheduled_phase2_drop_count_total"],
                    "aggregate_drop_counts": drop_summary["aggregate_drop_counts"],
                    "top_drop_keys": drop_summary["top_drop_keys"],
                    "scheduled_phase2_throughput": drop_summary["scheduled_phase2_throughput"],
                    "drop_share_by_gate_category": drop_summary["drop_share_by_gate_category"],
                    "drop_summary": drop_summary,
                },
                "allowed_output": "design_only_hypothesis_family_packet",
            },
            {
                "id": "scanner_materializer_timing_alignment_hypothesis",
                "basis": "Use parity diagnostics, including the SPY 2026-06-16 scheduled-session versus materializer-entry-window divergence, as a research question only.",
                "current_evidence": {
                    "parity_status": parity.get("status"),
                    "materializer_rows_in_window": _as_dict(parity.get("materializer_coverage")).get("row_count_in_window"),
                    "filter_matched_selected_rows_in_window": _as_dict(parity.get("materializer_coverage")).get("filter_matched_selected_rows_in_window"),
                },
                "allowed_output": "design_only_timing_alignment_packet",
            },
            {
                "id": "filter_family_refreeze_candidate_design",
                "basis": "Only after operator approval, define candidate families and split rules before any code evaluates them.",
                "allowed_output": "separate_approval_required_preregistered_design",
            },
        ],
        "research_execution_prerequisites": [
            "explicit_operator_approval_for_this_contract_or_a_successor_contract",
            "fresh_Fable_or_operator_review_when_CLI_is_available_again",
            "all_input_artifacts_loaded_and_hash_recorded",
            "candidate_family_definitions_written_before_any_family_evaluation",
            "selection_windows_exclude_consumed_audit_windows_and_protected_holdout",
            "current_forward_evidence_bar_contract_remains_unchanged",
            "current_frozen_policy_remains_active_until_a_separate_approved_refreeze",
            "all outputs label historical rows as research_only_not_forward_proof",
        ],
        "failure_criteria": [
            "proposal_reuses_consumed_2026_02_through_2026_05_audit_window_for_selection",
            "proposal_reuses_consumed_2022_01_through_2024_05_oos_window_for_selection_or_threshold_choice",
            "proposal_changes_current_policy_without_separate_approval",
            "proposal_changes_or_lowers_forward_evidence_bar",
            "proposal_imports_quotes_or_mutates_evidence",
            "proposal_consumes_protected_holdout",
            "proposal_claims_accepted_profitability_without_forward_exact_bar_evaluation",
        ],
        "required_future_artifacts_before_any_state_change": [
            "preregistered_family_definitions_json",
            "window_split_and_consumption_check_json",
            "no_holdout_no_consumed_window_audit",
            "read_only_family_evaluation_plan",
            "operator_approval_packet_for_any_policy_refreeze",
            "fresh_forward_evidence_collection_plan_preserving_current_bar",
        ],
        "inputs": inputs,
        "blockers": blockers,
        "prohibited_actions": PROHIBITED_ACTIONS,
        **FALSE_FLAGS,
    }
    _validate_contract(contract)
    return contract


def _validate_contract(contract: dict[str, Any]) -> None:
    for key, expected in FALSE_FLAGS.items():
        if contract.get(key) is not expected:
            raise ValueError(f"{key} must be {expected}")
    if contract.get("read_only") is not True or contract.get("research_only") is not True:
        raise ValueError("contract must be read-only research-only")
    if contract.get("activation_status") != "not_activated_operator_approval_required":
        raise ValueError("contract cannot activate research execution")
    if "current_forward_evidence_bar_contract_remains_unchanged" not in contract.get("research_execution_prerequisites", []):
        raise ValueError("contract must preserve the current evidence bar")
    if not contract.get("blocked_or_consumed_selection_windows"):
        raise ValueError("contract must carry consumed-window context")


def render_markdown(contract: dict[str, Any]) -> str:
    trigger = _as_dict(contract.get("trigger_context"))
    current_policy = _as_dict(contract.get("current_policy_preserved"))
    current_bar = _as_dict(contract.get("current_evidence_bar_preserved"))
    lines = [
        "# Regular Options Refreeze / Filter-Family Research Contract",
        "",
        "This generated contract pre-registers the safe path for considering future refreeze or filter-family research while Fable CLI access is unavailable. It is not a refreeze, not scanner-policy approval, and not profitability evidence.",
        "",
        "## Summary",
        "",
        f"- Status: `{contract.get('status')}`.",
        f"- Activation: `{contract.get('activation_status')}`.",
        f"- Fresh Fable readback available: `{str(contract.get('fresh_fable_readback_available')).lower()}`.",
        f"- Current policy preserved: `{current_policy.get('filter_id')}` with conditions hash `{current_policy.get('conditions_sha256')}`.",
        f"- Current evidence bar preserved: `{current_bar.get('bar_id')}`.",
        f"- Projection status: `{trigger.get('projection_status')}`.",
        f"- Stationarity status: `{trigger.get('stationarity_status')}`.",
        f"- Forward rows: matched `{trigger.get('matched_forward_rows')}`, completed `{trigger.get('completed_forward_rows')}` / `{trigger.get('evidence_bar_completed_rows_required')}`.",
        "",
        "## Allowed Research Questions",
        "",
    ]
    for question in _as_list(contract.get("allowed_research_questions")):
        item = _as_dict(question)
        lines.extend(
            [
                f"### `{item.get('id')}`",
                "",
                f"- Basis: {item.get('basis')}",
                f"- Allowed output: `{item.get('allowed_output')}`.",
                "",
            ]
        )
    lines.extend(["## Prerequisites", ""])
    lines.extend(f"- `{item}`" for item in _as_list(contract.get("research_execution_prerequisites")))
    first_question = _as_dict(_as_list(contract.get("allowed_research_questions"))[0] if contract.get("allowed_research_questions") else {})
    drop_evidence = _as_dict(first_question.get("current_evidence"))
    if drop_evidence:
        aggregate_counts = ", ".join(
            f"{key}={value}" for key, value in _as_dict(drop_evidence.get("aggregate_drop_counts")).items()
        )
        lines.extend(
            [
                "",
                "## Current Drop Evidence",
                "",
                f"- Scheduled Phase 2 drops: `{drop_evidence.get('scheduled_phase2_drop_count_total')}`.",
                f"- Aggregate drop counts: `{aggregate_counts}`.",
                f"- Returned picks: `{_as_dict(drop_evidence.get('scheduled_phase2_throughput')).get('returned_picks')}`.",
                f"- Returned-pick survival over recorded drops: `{_as_dict(drop_evidence.get('scheduled_phase2_throughput')).get('returned_pick_rate_over_recorded_drops')}`.",
            ]
        )
    lines.extend(["", "## Failure Criteria", ""])
    lines.extend(f"- `{item}`" for item in _as_list(contract.get("failure_criteria")))
    lines.extend(["", "## Boundary", ""])
    lines.append(
        "This contract does not change scanner policy, filters, thresholds, proof bars, cohorts, quotes, evidence stores, protected holdout, live validation, auto-track, broker behavior, accepted profitability, or promotion."
    )
    lines.extend(["", "## Prohibited Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(contract.get("prohibited_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(contract: dict[str, Any], *, output_json: Path = DEFAULT_OUTPUT_JSON, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"json": _rel(output_json), "docs_report": _rel(docs_report)}
    payload = dict(contract)
    payload["artifacts"] = artifacts
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report.write_text(render_markdown(payload), encoding="utf8")
    contract["artifacts"] = artifacts
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only regular-options refreeze/filter-family research contract.")
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--evidence-bar-contract", type=Path, default=DEFAULT_EVIDENCE_BAR_CONTRACT)
    parser.add_argument("--audit-window-registry", type=Path, default=DEFAULT_AUDIT_WINDOW_REGISTRY)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    parser.add_argument("--stationarity", type=Path, default=DEFAULT_STATIONARITY)
    parser.add_argument("--drop-decomposition", type=Path, default=DEFAULT_DROP_DECOMPOSITION)
    parser.add_argument("--parity", type=Path, default=DEFAULT_PARITY)
    parser.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    contract = build_contract(
        policy_contract_path=args.policy_contract,
        evidence_bar_contract_path=args.evidence_bar_contract,
        audit_window_registry_path=args.audit_window_registry,
        projection_path=args.projection,
        stationarity_path=args.stationarity,
        drop_decomposition_path=args.drop_decomposition,
        parity_path=args.parity,
        tracker_path=args.tracker,
    )
    if not args.no_write:
        write_outputs(contract, output_json=args.output_json, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(contract, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(contract))
    return 0 if contract["status"] in {"refreeze_filter_family_research_contract_ready", "blocked_missing_context"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
