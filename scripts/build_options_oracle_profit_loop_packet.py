from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "options_oracle_profit_loop_packet"

DEFAULT_FRONTIER = ROOT / "data" / "profitability-lab" / "regular-options-countable-throughput-frontier" / "latest.json"
DEFAULT_MOMENTUM_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-momentum-edge" / "latest.json"
DEFAULT_CAUSAL_FALSIFICATION = ROOT / "data" / "profitability-lab" / "regular-options-causal-falsification-slice" / "latest.json"
DEFAULT_PREREGISTERED_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-momentum-continuation-playbook" / "latest.json"
DEFAULT_MOMENTUM_CONTINUATION_REPLAY = ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-research-replay" / "latest.json"
DEFAULT_MOMENTUM_CONTINUATION_PROOF_RESOLUTION = ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-proof-blocker-resolution" / "latest.json"
DEFAULT_MOMENTUM_CONTINUATION_BOUNDED_REPLAY = ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-bounded-replay" / "latest.json"
DEFAULT_PREREGISTERED_VRP_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-vrp-credit-spread-playbook" / "latest.json"
DEFAULT_VRP_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-replay-readiness" / "latest.json"
DEFAULT_TERM_STRUCTURE_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-term-structure-calendar-playbook" / "latest.json"
DEFAULT_TERM_STRUCTURE_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-replay-readiness" / "latest.json"
DEFAULT_PREREGISTERED_SKEW_BROKEN_WING_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-skew-broken-wing-playbook" / "latest.json"
DEFAULT_PREREGISTERED_MACRO_EVENT_LONG_STRANGLE_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-macro-event-long-strangle-playbook" / "latest.json"
DEFAULT_MACRO_EVENT_CALENDAR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "latest.json"
DEFAULT_POINT_IN_TIME_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_MACRO_EVENT_LONG_STRANGLE_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-long-strangle-replay-readiness" / "latest.json"
DEFAULT_13_SYMBOL_CANDIDATE_GENERATION_SURFACE_AUDIT = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-candidate-generation-surface-audit" / "latest.json"
DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_SOURCE_SURFACE = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-source-surface" / "latest.json"
DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENTRYPOINT = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-entrypoint" / "latest.json"
DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENGINE = ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-engine" / "latest.json"
DEFAULT_PREREGISTERED_POST_EVENT_IV_CRUSH_IRON_CONDOR_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-post-event-iv-crush-iron-condor-playbook" / "latest.json"
DEFAULT_PREREGISTERED_FLOW_EXTREME_RATIO_BACKSPREAD_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-flow-extreme-ratio-backspread-playbook" / "latest.json"
DEFAULT_FLOW_EXTREME_VOLUME_OI_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-volume-oi-source-rows" / "latest.json"
DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "latest.json"
DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY = ROOT / "data" / "profitability-lab" / "regular-options-multi-leg-side-aware-pricing-capability" / "latest.json"
DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-denominator-dedupe-bridge" / "latest.json"
DEFAULT_FLOW_EXTREME_RATIO_BACKSPREAD_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-ratio-backspread-replay-readiness" / "latest.json"
DEFAULT_PREREGISTERED_DISPERSION_PROXY_HYBRID_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-dispersion-proxy-hybrid-playbook" / "latest.json"
DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "latest.json"
DEFAULT_DISPERSION_PROXY_HYBRID_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness" / "latest.json"
DEFAULT_PREREGISTERED_PMCC_DIAGONAL_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-pmcc-diagonal-playbook" / "latest.json"
DEFAULT_PMCC_DIAGONAL_REPLAY_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-pmcc-diagonal-replay-readiness" / "latest.json"
DEFAULT_59_SYMBOL_SOURCE_REPAIR = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair" / "latest.json"
DEFAULT_59_SYMBOL_SOURCE_REPAIR_RESUME = ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair-resume" / "latest.json"
DEFAULT_DIRECT_VIX_SOURCE_IMPORT = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-import" / "latest.json"
DEFAULT_DIRECT_VIX_SOURCE_REPAIR_PACKET = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-repair-packet" / "latest.json"
DEFAULT_MACRO_EVENT_CALENDAR_SOURCE_REPAIR_PACKET = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar-source-repair-packet" / "latest.json"
DEFAULT_FLOW_EXTREME_SOURCE_REPAIR_PACKET = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-source-repair-packet" / "latest.json"
DEFAULT_GOAL_LOOP = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_NEXT_STEPS = ROOT / "docs" / "NEXT_STEPS.md"
DEFAULT_DECISIONS = ROOT / "docs" / "DECISIONS.md"
DEFAULT_PROJECT_CONTEXT = ROOT / "docs" / "PROJECT_CONTEXT.md"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_OUTPUT_MD = ROOT / "docs" / "research-decisions" / "options_oracle_profit_loop_packet_latest.md"

SAFETY_FLAGS = {
    "live_entry_allowed": False,
    "auto_track_allowed": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}

CONTINUATION_BRANCHES = [
    {
        "branch_id": "fresh_forward_paper_shadow_collection",
        "requires_operator_approval": True,
        "why": "Only fresh post-freeze executable rows can become proof-qualified profitability.",
    },
    {
        "branch_id": "scoped_source_repair_or_replay",
        "requires_operator_approval": True,
        "why": "May require quote import, evidence repair, or source-surface mutation; must be explicitly scoped.",
    },
    {
        "branch_id": "new_causal_playbook_generation",
        "requires_operator_approval": False,
        "why": "Read-only preregistration/falsification can continue without live or evidence mutation.",
    },
    {
        "branch_id": "new_historical_data_surface_or_longer_lookback",
        "requires_operator_approval": True,
        "why": "Changes the data surface and can invalidate prior branch-scoped stop verdicts.",
    },
    {
        "branch_id": "dashboard_or_operator_visibility",
        "requires_operator_approval": False,
        "why": "Useful only if it changes execution decisions; not significant by itself unless tied to a proof blocker.",
    },
]

PROFITABILITY_TARGET = {
    "target_window": "latest approximately four months / post-freeze forward-style audit window",
    "minimum_profitable_strict_completed_rows": 30,
    "profitability_metric": "canonical executable exact net P&L after fees/slippage with PF lower-bound discipline",
    "current_forward_rows": 0,
    "current_status": "not forward-audit profitable",
}

OPERATOR_APPROVAL_POSTURE = {
    "read_only_research_only_work": "pre_approved_by_user_for_loop_continuation",
    "fixture_temp_verification_generated_artifacts": "pre_approved_by_user_for_loop_continuation",
    "questions_to_gpt55": "Do not block on read-only/research-only operator questions; state the assumption as approved and choose the next task.",
    "still_requires_separate_explicit_approval": [
        "broker orders or order preparation",
        "live validation",
        "auto-track enablement",
        "production scanner, strategy, stop, sizing, or proof-bar changes",
        "quote import",
        "protected-holdout consumption",
        "promotion",
        "unsafe evidence-store mutation",
    ],
}

EDGE_DISCOVERY_REQUIREMENTS = {
    "stop_is_exceptional": True,
    "must_consider_before_stop": [
        "fresh_forward_paper_shadow_collection",
        "scoped_source_repair_or_replay",
        "new_historical_data_surface_or_longer_lookback",
        "new_causal_playbook_generation",
        "new option structures beyond current directional spreads",
        "index/ETF lanes separately from single-name lanes",
        "data requirements that would make the latest-four-month audit proof-valid",
    ],
    "edge_families_to_evaluate": [
        "volatility risk premium",
        "skew mispricing",
        "term-structure dislocation",
        "earnings or macro event volatility",
        "post-event IV crush",
        "post-event drift",
        "trend or momentum continuation",
        "mean reversion",
        "dispersion-like proxy behavior",
        "liquidity or flow effects",
    ],
    "option_structures_to_consider": [
        "vertical spreads",
        "calendars",
        "diagonals",
        "broken-wing butterflies",
        "ratio spreads",
        "backspreads",
        "straddles",
        "strangles",
        "iron condors",
        "iron butterflies",
        "synthetic covered calls or PMCC-style diagonals",
        "debit/credit hybrids",
    ],
    "anti_handwave_rules": [
        "Do not say collect more data without naming the exact data, lane, date window, command, and pass/fail threshold.",
        "Do not say try more strategies without naming the exact market hypothesis, structure, universe, and falsification test.",
        "Do not say optimize parameters unless the search budget, frozen validation split, leakage controls, and multiple-hypothesis penalty are explicit.",
        "Do not treat historical dashboard artifacts, repaired historical rows, or point PF alone as proof-qualified profitability.",
    ],
}

GPT_OUTPUT_SCHEMA = {
    "verdict": "continue|stop_exception",
    "continue_loop": "boolean",
    "significant_upgrade_available": "boolean",
    "selected_branch_id": "string|null",
    "burden_of_proof_check": {
        "current_forward_rows": "number",
        "target_profitable_strict_completed_rows": "number",
        "stop_allowed": "boolean",
        "reason": "string",
    },
    "operator_questions": [
        {
            "question": "string",
            "why_it_matters": "string",
            "default_if_unanswered": "string",
        }
    ],
    "assumption_challenges": [
        {
            "assumption": "string",
            "risk": "string",
            "verification": "string",
        }
    ],
    "candidate_branches": [
        {
            "branch": "string",
            "expected_value": "string",
            "main_uncertainty": "string",
            "why_not_selected": "string|null",
        }
    ],
    "next_codex_task": {
        "objective": "one concrete implementation or verification task",
        "exact_scope": "files/modules/artifacts included and excluded",
        "allowed_files_or_artifacts": ["paths or artifact families"],
        "forbidden_actions": ["actions that remain forbidden"],
        "commands_to_run": ["exact commands"],
        "implementation_steps": ["ordered steps"],
        "acceptance_criteria": ["measurable pass/fail criteria"],
        "failure_criteria": ["what result rejects or parks this branch"],
        "expected_artifacts": ["files or readbacks expected after Codex runs"],
        "stop_condition_after_task": "what would make this branch exhausted",
    },
    "why_this_is_significant": "short explanation tied to profitability proof",
    "branches_to_stop": ["branch ids or candidate ids to avoid repeating"],
    "anti_handwave_audit": {
        "generic_advice_removed": "boolean",
        "exact_next_action_present": "boolean",
        "measurable_threshold_present": "boolean",
    },
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _without_vix_blockers(blockers: Any) -> list[Any]:
    return [blocker for blocker in _as_list(blockers) if "vix" not in str(blocker).lower()]


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing"}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError) as exc:
        meta["status"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("last_updated")
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    return payload, meta


FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED = {
    "report_id": "regular_options_flow_extreme_ratio_backspread_replay_readiness",
    "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
    "structure": "defined_risk_ratio_spreads_or_backspreads_only",
}

FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_REQUIRED_FALSE_FLAGS = (
    "accepted_profitability",
    "historical_replay_performed",
    "replay_performed",
    "lane_implementation_performed",
    "broker_order_allowed",
    "live_validation_enabled",
    "auto_track_enabled",
    "quotes_imported",
    "evidence_stores_mutated",
    "protected_holdout_consumed",
    "production_scanner_changed",
    "strategy_logic_changed",
    "stops_changed",
    "sizing_changed",
    "proof_bars_changed",
    "promotion_ready",
    "undefined_risk_allowed",
    "naked_ratio_spreads_allowed",
)

PMCC_DIAGONAL_READINESS_EXPECTED = {
    "report_id": "regular_options_pmcc_diagonal_replay_readiness",
    "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
    "structure": "defined_risk_pmcc_style_call_diagonals_only",
}

PMCC_DIAGONAL_READINESS_REQUIRED_FALSE_FLAGS = (
    "accepted_profitability",
    "historical_replay_performed",
    "replay_performed",
    "lane_implementation_performed",
    "broker_order_allowed",
    "live_validation_enabled",
    "auto_track_enabled",
    "quotes_imported",
    "evidence_stores_mutated",
    "protected_holdout_consumed",
    "scanner_policy_changed",
    "production_scanner_changed",
    "strategy_logic_changed",
    "stops_changed",
    "sizing_changed",
    "proof_bars_changed",
    "promotion_ready",
    "historical_rows_are_forward_proof",
    "undefined_or_uncapped_short_call_risk_allowed",
)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validate_flow_extreme_ratio_backspread_readiness_artifact(
    *,
    readiness: dict[str, Any],
    readiness_meta: dict[str, Any],
    playbook_meta: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed when Oracle packet evidence is absent, stale, or unsafe."""
    reason_codes: list[str] = []
    meta_status = readiness_meta.get("status")
    if meta_status == "missing":
        reason_codes.append("missing_flow_extreme_ratio_backspread_replay_readiness_artifact")
    elif meta_status != "loaded":
        reason_codes.append("malformed_flow_extreme_ratio_backspread_replay_readiness_artifact")

    if meta_status == "loaded":
        if readiness.get("report_id") != FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["report_id"]:
            reason_codes.append("invalid_flow_extreme_ratio_backspread_replay_readiness_report_id")
        if readiness.get("concept_id") != FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["concept_id"]:
            reason_codes.append("invalid_flow_extreme_ratio_backspread_replay_readiness_concept_id")
        if readiness.get("structure") != FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["structure"]:
            reason_codes.append("invalid_flow_extreme_ratio_backspread_replay_readiness_structure")

        readiness_generated_at = _parse_iso_datetime(readiness.get("generated_at_utc"))
        playbook_generated_at = _parse_iso_datetime(playbook_meta.get("generated_at_utc"))
        if readiness_generated_at is None or (
            playbook_generated_at is not None and readiness_generated_at < playbook_generated_at
        ):
            reason_codes.append("stale_flow_extreme_ratio_backspread_replay_readiness_artifact")

        unsafe_flags = [
            flag
            for flag in FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_REQUIRED_FALSE_FLAGS
            if readiness.get(flag) is not False
        ]
        if unsafe_flags:
            reason_codes.append("unsafe_flow_extreme_ratio_backspread_replay_readiness_flags")
    else:
        unsafe_flags = []

    return {
        "validated_status": reason_codes[0]
        if reason_codes
        else readiness.get("status", "loaded_flow_extreme_ratio_backspread_replay_readiness"),
        "raw_status": readiness.get("status"),
        "reason_codes": reason_codes,
        "unsafe_flags": unsafe_flags,
        "expected_report_id": FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["report_id"],
        "expected_concept_id": FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["concept_id"],
        "expected_structure": FLOW_EXTREME_RATIO_BACKSPREAD_READINESS_EXPECTED["structure"],
        "generated_at_utc": readiness.get("generated_at_utc"),
        "playbook_generated_at_utc": playbook_meta.get("generated_at_utc"),
    }


def _validate_pmcc_diagonal_readiness_artifact(
    *,
    readiness: dict[str, Any],
    readiness_meta: dict[str, Any],
    playbook_meta: dict[str, Any],
) -> dict[str, Any]:
    reason_codes: list[str] = []
    meta_status = readiness_meta.get("status")
    if meta_status == "missing":
        reason_codes.append("missing_pmcc_diagonal_replay_readiness_artifact")
    elif meta_status != "loaded":
        reason_codes.append("malformed_pmcc_diagonal_replay_readiness_artifact")

    if meta_status == "loaded":
        if readiness.get("report_id") != PMCC_DIAGONAL_READINESS_EXPECTED["report_id"]:
            reason_codes.append("invalid_pmcc_diagonal_replay_readiness_report_id")
        if readiness.get("concept_id") != PMCC_DIAGONAL_READINESS_EXPECTED["concept_id"]:
            reason_codes.append("invalid_pmcc_diagonal_replay_readiness_concept_id")
        if readiness.get("structure") != PMCC_DIAGONAL_READINESS_EXPECTED["structure"]:
            reason_codes.append("invalid_pmcc_diagonal_replay_readiness_structure")

        readiness_generated_at = _parse_iso_datetime(readiness.get("generated_at_utc"))
        playbook_generated_at = _parse_iso_datetime(playbook_meta.get("generated_at_utc"))
        if readiness_generated_at is None or (
            playbook_generated_at is not None and readiness_generated_at < playbook_generated_at
        ):
            reason_codes.append("stale_pmcc_diagonal_replay_readiness_artifact")

        unsafe_flags = [
            flag
            for flag in PMCC_DIAGONAL_READINESS_REQUIRED_FALSE_FLAGS
            if readiness.get(flag) is not False
        ]
        if unsafe_flags:
            reason_codes.append("unsafe_pmcc_diagonal_replay_readiness_flags")
    else:
        unsafe_flags = []

    return {
        "validated_status": reason_codes[0]
        if reason_codes
        else readiness.get("status", "loaded_pmcc_diagonal_replay_readiness"),
        "raw_status": readiness.get("status"),
        "reason_codes": reason_codes,
        "unsafe_flags": unsafe_flags,
        "expected_report_id": PMCC_DIAGONAL_READINESS_EXPECTED["report_id"],
        "expected_concept_id": PMCC_DIAGONAL_READINESS_EXPECTED["concept_id"],
        "expected_structure": PMCC_DIAGONAL_READINESS_EXPECTED["structure"],
        "generated_at_utc": readiness.get("generated_at_utc"),
        "playbook_generated_at_utc": playbook_meta.get("generated_at_utc"),
    }


def _load_text_excerpt(path: Path, *, max_chars: int = 8000) -> tuple[str, dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "excerpt_chars": 0}
    if not path.exists():
        return "", meta
    try:
        text = path.read_text(encoding="utf8")
    except OSError as exc:
        meta["status"] = type(exc).__name__
        return "", meta
    excerpt = text[:max_chars]
    meta["status"] = "loaded"
    meta["excerpt_chars"] = len(excerpt)
    return excerpt, meta


def _frontier_summary(frontier: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": frontier.get("status"),
        "candidate_count": frontier.get("candidate_count"),
        "raw_count_candidate_count": frontier.get("raw_count_candidate_count"),
        "countable_throughput_candidate_found": frontier.get("countable_throughput_candidate_found"),
        "current_historical_surface_exhausted_under_current_prohibitions": frontier.get(
            "current_historical_surface_exhausted_under_current_prohibitions"
        ),
        "decision_counts": frontier.get("decision_counts"),
        "base_clean_stack_exact_rows": frontier.get("base_clean_stack_exact_rows"),
        "target_exact_rows": frontier.get("target_exact_rows"),
        "strict_new_gap_required": frontier.get("strict_new_gap_required"),
    }


def build_packet(
    *,
    frontier_path: Path = DEFAULT_FRONTIER,
    momentum_edge_path: Path = DEFAULT_MOMENTUM_EDGE,
    causal_falsification_path: Path = DEFAULT_CAUSAL_FALSIFICATION,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    momentum_continuation_replay_path: Path = DEFAULT_MOMENTUM_CONTINUATION_REPLAY,
    momentum_continuation_proof_resolution_path: Path = DEFAULT_MOMENTUM_CONTINUATION_PROOF_RESOLUTION,
    momentum_continuation_bounded_replay_path: Path = DEFAULT_MOMENTUM_CONTINUATION_BOUNDED_REPLAY,
    preregistered_vrp_playbook_path: Path = DEFAULT_PREREGISTERED_VRP_PLAYBOOK,
    vrp_replay_readiness_path: Path = DEFAULT_VRP_REPLAY_READINESS,
    preregistered_term_structure_playbook_path: Path = DEFAULT_TERM_STRUCTURE_PLAYBOOK,
    term_structure_replay_readiness_path: Path = DEFAULT_TERM_STRUCTURE_REPLAY_READINESS,
    preregistered_skew_broken_wing_playbook_path: Path = DEFAULT_PREREGISTERED_SKEW_BROKEN_WING_PLAYBOOK,
    preregistered_macro_event_long_strangle_playbook_path: Path = DEFAULT_PREREGISTERED_MACRO_EVENT_LONG_STRANGLE_PLAYBOOK,
    macro_event_calendar_path: Path = DEFAULT_MACRO_EVENT_CALENDAR,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    macro_event_long_strangle_replay_readiness_path: Path = DEFAULT_MACRO_EVENT_LONG_STRANGLE_REPLAY_READINESS,
    candidate_generation_13_symbol_surface_audit_path: Path = DEFAULT_13_SYMBOL_CANDIDATE_GENERATION_SURFACE_AUDIT,
    candidate_generation_13_symbol_frozen_source_surface_path: Path = DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_SOURCE_SURFACE,
    candidate_generation_13_symbol_frozen_entrypoint_path: Path = DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENTRYPOINT,
    candidate_generation_13_symbol_frozen_engine_path: Path = DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENGINE,
    preregistered_post_event_iv_crush_iron_condor_playbook_path: Path = DEFAULT_PREREGISTERED_POST_EVENT_IV_CRUSH_IRON_CONDOR_PLAYBOOK,
    preregistered_flow_extreme_ratio_backspread_playbook_path: Path = DEFAULT_PREREGISTERED_FLOW_EXTREME_RATIO_BACKSPREAD_PLAYBOOK,
    flow_extreme_volume_oi_source_rows_path: Path = DEFAULT_FLOW_EXTREME_VOLUME_OI_SOURCE_ROWS,
    point_in_time_flow_extreme_input_path: Path = DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT,
    multi_leg_side_aware_pricing_capability_path: Path = DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY,
    base_clean_stack_identity_ledger_path: Path = DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER,
    flow_extreme_denominator_dedupe_bridge_path: Path = DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE,
    flow_extreme_ratio_backspread_replay_readiness_path: Path = DEFAULT_FLOW_EXTREME_RATIO_BACKSPREAD_REPLAY_READINESS,
    preregistered_dispersion_proxy_hybrid_playbook_path: Path = DEFAULT_PREREGISTERED_DISPERSION_PROXY_HYBRID_PLAYBOOK,
    point_in_time_dispersion_concentration_proxy_path: Path = DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY,
    dispersion_proxy_hybrid_replay_readiness_path: Path = DEFAULT_DISPERSION_PROXY_HYBRID_REPLAY_READINESS,
    preregistered_pmcc_diagonal_playbook_path: Path = DEFAULT_PREREGISTERED_PMCC_DIAGONAL_PLAYBOOK,
    pmcc_diagonal_replay_readiness_path: Path = DEFAULT_PMCC_DIAGONAL_REPLAY_READINESS,
    source_repair_59_symbol_path: Path = DEFAULT_59_SYMBOL_SOURCE_REPAIR,
    source_repair_59_symbol_resume_path: Path = DEFAULT_59_SYMBOL_SOURCE_REPAIR_RESUME,
    direct_vix_source_import_path: Path = DEFAULT_DIRECT_VIX_SOURCE_IMPORT,
    direct_vix_source_repair_packet_path: Path = DEFAULT_DIRECT_VIX_SOURCE_REPAIR_PACKET,
    macro_event_calendar_source_repair_packet_path: Path = DEFAULT_MACRO_EVENT_CALENDAR_SOURCE_REPAIR_PACKET,
    flow_extreme_source_repair_packet_path: Path = DEFAULT_FLOW_EXTREME_SOURCE_REPAIR_PACKET,
    goal_loop_path: Path = DEFAULT_GOAL_LOOP,
    next_steps_path: Path = DEFAULT_NEXT_STEPS,
    decisions_path: Path = DEFAULT_DECISIONS,
    project_context_path: Path = DEFAULT_PROJECT_CONTEXT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    frontier, frontier_meta = _load_json(frontier_path, required=True)
    momentum, momentum_meta = _load_json(momentum_edge_path, required=False)
    causal, causal_meta = _load_json(causal_falsification_path, required=False)
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=False)
    momentum_replay, momentum_replay_meta = _load_json(momentum_continuation_replay_path, required=False)
    momentum_resolution, momentum_resolution_meta = _load_json(momentum_continuation_proof_resolution_path, required=False)
    momentum_bounded, momentum_bounded_meta = _load_json(momentum_continuation_bounded_replay_path, required=False)
    vrp_playbook, vrp_playbook_meta = _load_json(preregistered_vrp_playbook_path, required=False)
    vrp_readiness, vrp_readiness_meta = _load_json(vrp_replay_readiness_path, required=False)
    term_structure_playbook, term_structure_playbook_meta = _load_json(preregistered_term_structure_playbook_path, required=False)
    term_structure_readiness, term_structure_readiness_meta = _load_json(term_structure_replay_readiness_path, required=False)
    skew_broken_wing_playbook, skew_broken_wing_playbook_meta = _load_json(preregistered_skew_broken_wing_playbook_path, required=False)
    macro_event_long_strangle_playbook, macro_event_long_strangle_playbook_meta = _load_json(
        preregistered_macro_event_long_strangle_playbook_path,
        required=False,
    )
    macro_event_calendar, macro_event_calendar_meta = _load_json(macro_event_calendar_path, required=False)
    point_in_time_vix_bucket, point_in_time_vix_bucket_meta = _load_json(point_in_time_vix_bucket_path, required=False)
    macro_event_long_strangle_readiness, macro_event_long_strangle_readiness_meta = _load_json(
        macro_event_long_strangle_replay_readiness_path,
        required=False,
    )
    candidate_generation_13_symbol_surface_audit, candidate_generation_13_symbol_surface_audit_meta = _load_json(
        candidate_generation_13_symbol_surface_audit_path,
        required=False,
    )
    candidate_generation_13_symbol_frozen_source_surface, candidate_generation_13_symbol_frozen_source_surface_meta = (
        _load_json(
            candidate_generation_13_symbol_frozen_source_surface_path,
            required=False,
        )
    )
    candidate_generation_13_symbol_frozen_entrypoint, candidate_generation_13_symbol_frozen_entrypoint_meta = _load_json(
        candidate_generation_13_symbol_frozen_entrypoint_path,
        required=False,
    )
    candidate_generation_13_symbol_frozen_engine, candidate_generation_13_symbol_frozen_engine_meta = _load_json(
        candidate_generation_13_symbol_frozen_engine_path,
        required=False,
    )
    post_event_iv_crush_iron_condor_playbook, post_event_iv_crush_iron_condor_playbook_meta = _load_json(
        preregistered_post_event_iv_crush_iron_condor_playbook_path,
        required=False,
    )
    flow_extreme_ratio_backspread_playbook, flow_extreme_ratio_backspread_playbook_meta = _load_json(
        preregistered_flow_extreme_ratio_backspread_playbook_path,
        required=False,
    )
    flow_extreme_volume_oi_source_rows, flow_extreme_volume_oi_source_rows_meta = _load_json(
        flow_extreme_volume_oi_source_rows_path,
        required=False,
    )
    point_in_time_flow_extreme_input, point_in_time_flow_extreme_input_meta = _load_json(
        point_in_time_flow_extreme_input_path,
        required=False,
    )
    multi_leg_side_aware_pricing_capability, multi_leg_side_aware_pricing_capability_meta = _load_json(
        multi_leg_side_aware_pricing_capability_path,
        required=False,
    )
    base_clean_stack_identity_ledger, base_clean_stack_identity_ledger_meta = _load_json(
        base_clean_stack_identity_ledger_path,
        required=False,
    )
    flow_extreme_denominator_dedupe_bridge, flow_extreme_denominator_dedupe_bridge_meta = _load_json(
        flow_extreme_denominator_dedupe_bridge_path,
        required=False,
    )
    flow_extreme_ratio_backspread_readiness, flow_extreme_ratio_backspread_readiness_meta = _load_json(
        flow_extreme_ratio_backspread_replay_readiness_path,
        required=False,
    )
    flow_extreme_ratio_backspread_readiness_validation = _validate_flow_extreme_ratio_backspread_readiness_artifact(
        readiness=flow_extreme_ratio_backspread_readiness,
        readiness_meta=flow_extreme_ratio_backspread_readiness_meta,
        playbook_meta=flow_extreme_ratio_backspread_playbook_meta,
    )
    flow_extreme_ratio_backspread_readiness_meta = {
        **flow_extreme_ratio_backspread_readiness_meta,
        "validated_status": flow_extreme_ratio_backspread_readiness_validation["validated_status"],
        "validation_reason_codes": flow_extreme_ratio_backspread_readiness_validation["reason_codes"],
        "unsafe_flags": flow_extreme_ratio_backspread_readiness_validation["unsafe_flags"],
    }
    dispersion_proxy_hybrid_playbook, dispersion_proxy_hybrid_playbook_meta = _load_json(
        preregistered_dispersion_proxy_hybrid_playbook_path,
        required=False,
    )
    point_in_time_dispersion_proxy, point_in_time_dispersion_proxy_meta = _load_json(
        point_in_time_dispersion_concentration_proxy_path,
        required=False,
    )
    dispersion_proxy_hybrid_readiness, dispersion_proxy_hybrid_readiness_meta = _load_json(
        dispersion_proxy_hybrid_replay_readiness_path,
        required=False,
    )
    pmcc_diagonal_playbook, pmcc_diagonal_playbook_meta = _load_json(
        preregistered_pmcc_diagonal_playbook_path,
        required=False,
    )
    pmcc_diagonal_readiness, pmcc_diagonal_readiness_meta = _load_json(
        pmcc_diagonal_replay_readiness_path,
        required=False,
    )
    pmcc_diagonal_readiness_validation = _validate_pmcc_diagonal_readiness_artifact(
        readiness=pmcc_diagonal_readiness,
        readiness_meta=pmcc_diagonal_readiness_meta,
        playbook_meta=pmcc_diagonal_playbook_meta,
    )
    pmcc_diagonal_readiness_meta = {
        **pmcc_diagonal_readiness_meta,
        "validated_status": pmcc_diagonal_readiness_validation["validated_status"],
        "validation_reason_codes": pmcc_diagonal_readiness_validation["reason_codes"],
        "unsafe_flags": pmcc_diagonal_readiness_validation["unsafe_flags"],
    }
    source_repair_59_symbol, source_repair_59_symbol_meta = _load_json(
        source_repair_59_symbol_path,
        required=False,
    )
    source_repair_59_symbol_resume, source_repair_59_symbol_resume_meta = _load_json(
        source_repair_59_symbol_resume_path,
        required=False,
    )
    direct_vix_source_import, direct_vix_source_import_meta = _load_json(
        direct_vix_source_import_path,
        required=False,
    )
    direct_vix_source_repair_packet, direct_vix_source_repair_packet_meta = _load_json(
        direct_vix_source_repair_packet_path,
        required=False,
    )
    macro_event_calendar_source_repair_packet, macro_event_calendar_source_repair_packet_meta = _load_json(
        macro_event_calendar_source_repair_packet_path,
        required=False,
    )
    flow_extreme_source_repair_packet, flow_extreme_source_repair_packet_meta = _load_json(
        flow_extreme_source_repair_packet_path,
        required=False,
    )
    goal_loop, goal_meta = _load_json(goal_loop_path, required=False)
    next_steps, next_meta = _load_text_excerpt(next_steps_path)
    decisions, decisions_meta = _load_text_excerpt(decisions_path)
    context, context_meta = _load_text_excerpt(project_context_path)
    source_artifacts = {
        "frontier": frontier_meta,
        "momentum_edge": momentum_meta,
        "causal_falsification": causal_meta,
        "preregistered_playbook": playbook_meta,
        "momentum_continuation_research_replay": momentum_replay_meta,
        "momentum_continuation_proof_blocker_resolution": momentum_resolution_meta,
        "momentum_continuation_bounded_replay": momentum_bounded_meta,
        "preregistered_vrp_credit_spread_playbook": vrp_playbook_meta,
        "vrp_credit_spread_replay_readiness": vrp_readiness_meta,
        "preregistered_term_structure_calendar_playbook": term_structure_playbook_meta,
        "term_structure_calendar_replay_readiness": term_structure_readiness_meta,
        "preregistered_skew_broken_wing_playbook": skew_broken_wing_playbook_meta,
        "preregistered_macro_event_long_strangle_playbook": macro_event_long_strangle_playbook_meta,
        "macro_event_calendar": macro_event_calendar_meta,
        "point_in_time_vix_bucket": point_in_time_vix_bucket_meta,
        "macro_event_long_strangle_replay_readiness": macro_event_long_strangle_readiness_meta,
        "candidate_generation_13_symbol_surface_audit": candidate_generation_13_symbol_surface_audit_meta,
        "candidate_generation_13_symbol_frozen_source_surface": candidate_generation_13_symbol_frozen_source_surface_meta,
        "candidate_generation_13_symbol_frozen_entrypoint": candidate_generation_13_symbol_frozen_entrypoint_meta,
        "candidate_generation_13_symbol_frozen_engine": candidate_generation_13_symbol_frozen_engine_meta,
        "preregistered_post_event_iv_crush_iron_condor_playbook": post_event_iv_crush_iron_condor_playbook_meta,
        "preregistered_flow_extreme_ratio_backspread_playbook": flow_extreme_ratio_backspread_playbook_meta,
        "flow_extreme_volume_oi_source_rows": flow_extreme_volume_oi_source_rows_meta,
        "point_in_time_flow_extreme_input": point_in_time_flow_extreme_input_meta,
        "multi_leg_side_aware_pricing_capability": multi_leg_side_aware_pricing_capability_meta,
        "base_clean_stack_identity_ledger": base_clean_stack_identity_ledger_meta,
        "flow_extreme_denominator_dedupe_bridge": flow_extreme_denominator_dedupe_bridge_meta,
        "flow_extreme_ratio_backspread_replay_readiness": flow_extreme_ratio_backspread_readiness_meta,
        "preregistered_dispersion_proxy_hybrid_playbook": dispersion_proxy_hybrid_playbook_meta,
        "point_in_time_dispersion_concentration_proxy": point_in_time_dispersion_proxy_meta,
        "dispersion_proxy_hybrid_replay_readiness": dispersion_proxy_hybrid_readiness_meta,
        "preregistered_pmcc_diagonal_playbook": pmcc_diagonal_playbook_meta,
        "pmcc_diagonal_replay_readiness": pmcc_diagonal_readiness_meta,
        "source_repair_59_symbol_thetadata_opra": source_repair_59_symbol_meta,
        "source_repair_59_symbol_thetadata_opra_resume": source_repair_59_symbol_resume_meta,
        "direct_vix_source_import": direct_vix_source_import_meta,
        "direct_vix_source_repair_packet": direct_vix_source_repair_packet_meta,
        "macro_event_calendar_source_repair_packet": macro_event_calendar_source_repair_packet_meta,
        "flow_extreme_source_repair_packet": flow_extreme_source_repair_packet_meta,
        "goal_loop": goal_meta,
        "next_steps": next_meta,
        "decisions": decisions_meta,
        "project_context": context_meta,
    }
    missing_required = [name for name, meta in source_artifacts.items() if meta.get("required") and meta.get("status") != "loaded"]
    vix_bucket_ready = (
        point_in_time_vix_bucket.get("status") == "point_in_time_vix_bucket_ready"
        and point_in_time_vix_bucket.get("point_in_time_vix_low_mid_bucket_available") is True
        and not _as_list(point_in_time_vix_bucket.get("blockers"))
    )
    direct_vix_materialized = (
        direct_vix_source_import.get("status") == "direct_vix_source_import_materialized"
        and direct_vix_source_import.get("source_rows_written") is True
        and vix_bucket_ready
    )
    direct_vix_current_state = {
        "materialized": direct_vix_materialized,
        "source_import_status": direct_vix_source_import.get("status"),
        "source_row_count": direct_vix_source_import.get("source_row_count"),
        "source_rows_written": direct_vix_source_import.get("source_rows_written"),
        "source_rows_path": direct_vix_source_import.get("source_rows_path"),
        "threshold_policy_path": direct_vix_source_import.get("threshold_policy_path"),
        "downstream_vix_bucket_status": direct_vix_source_import.get("downstream_vix_bucket_status"),
        "downstream_vix_coverage_pct": direct_vix_source_import.get("downstream_vix_coverage_pct"),
        "vix_bucket_status": point_in_time_vix_bucket.get("status"),
        "point_in_time_vix_bucket_status": point_in_time_vix_bucket.get("status"),
        "vix_bucket_source_rows_count": point_in_time_vix_bucket.get("source_rows_count"),
        "vix_source_rows_count": point_in_time_vix_bucket.get("source_rows_count"),
        "vix_bucket_coverage_pct": point_in_time_vix_bucket.get("coverage_pct"),
        "vix_coverage_pct": point_in_time_vix_bucket.get("coverage_pct"),
        "vix_bucket_blockers": point_in_time_vix_bucket.get("blockers"),
        "late_known_at_count": point_in_time_vix_bucket.get("late_known_at_count"),
        "leakage_reject_count": point_in_time_vix_bucket.get("leakage_reject_count"),
    }
    current_vix_branch_implications = [
        {
            "branch": "macro_event_long_strangle",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(macro_event_long_strangle_readiness.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": macro_event_long_strangle_readiness.get("status"),
        },
        {
            "branch": "flow_extreme_ratio_backspread",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(flow_extreme_ratio_backspread_readiness.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": flow_extreme_ratio_backspread_readiness.get("status"),
        },
        {
            "branch": "pmcc_diagonal",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(pmcc_diagonal_readiness.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": pmcc_diagonal_readiness.get("status"),
        },
        {
            "branch": "vrp_credit_spread",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(vrp_readiness.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": vrp_readiness.get("status"),
        },
        {
            "branch": "momentum_continuation",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(momentum_bounded.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": momentum_bounded.get("status"),
            "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
        },
        {
            "branch": "dispersion_proxy_hybrid",
            "vix_status": "ready" if vix_bucket_ready else "blocked",
            "remaining_non_vix_blockers": _without_vix_blockers(dispersion_proxy_hybrid_readiness.get("blockers")),
            "would_clear_vix_blocker_if_future_source_passes": not vix_bucket_ready,
            "source_status": dispersion_proxy_hybrid_readiness.get("status"),
            "note": "Refresh this artifact before ranking if it still predates the VIX source import.",
        },
    ]
    frozen_engine_decision = candidate_generation_13_symbol_frozen_engine.get("decision")
    frozen_engine_entrypoint_available = _as_dict(
        candidate_generation_13_symbol_frozen_engine.get("reusable_entrypoint_discovery")
    ).get("available")
    packet = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "status": "blocked_missing_required_artifact" if missing_required else "ready_for_same_session_gpt55_guidance",
        "purpose": "Create a reusable same-session GPT-5.5 Pro handoff that keeps the profitability loop moving until GPT-5.5 says no significant upgrades remain.",
        **SAFETY_FLAGS,
        "source_artifacts": source_artifacts,
        "missing_required_artifacts": missing_required,
        "loop_goal": {
            "plain_english": "Make the regular-options work profitable under proof-qualified criteria, targeting at least 30 profitable strict completed rows in the latest approximately four months, or prove there are no significant upgrades left under the current allowed branches.",
            "profit_target": "profitability with executable exact evidence, not raw historical row count or non-executable marks",
            "gpt55_role": "strategic reviewer and next-slice selector",
            "codex_role": "repo implementation, verification, and evidence refresh",
            "loop_stop_rule": "Stop only when GPT-5.5 Pro returns verdict=stop_exception after proving no significant upgrade remains across new lanes, new option structures, historical data-depth repair, and forward collection, or when a safety/proof violation is detected.",
        },
        "profitability_target": PROFITABILITY_TARGET,
        "operator_approval_posture": OPERATOR_APPROVAL_POSTURE,
        "edge_discovery_requirements": EDGE_DISCOVERY_REQUIREMENTS,
        "significant_upgrade_definition": [
            "materially increases proof-qualified forward rows, strict-new executable historical rows, quote/execution cleanliness, PF lower-bound confidence, holdout depth, or operator ability to collect exact evidence",
            "retires a false branch with a measurable stop verdict so future loops avoid it",
            "opens a new bounded causal playbook or data-surface branch with clear commands, tests, and acceptance gates",
            "does not count if it only aggregates raw overlapping rows, improves wording, reruns an exhausted variant, lowers proof bars, or depends on live/broker/evidence mutation without approval",
        ],
        "current_evidence_summary": {
            "frontier": _frontier_summary(frontier),
            "momentum_edge_status": momentum.get("status"),
            "causal_falsification_status": causal.get("status"),
            "causal_continue_loop": causal.get("continue_loop"),
            "causal_significant_upgrade_available": causal.get("significant_upgrade_available"),
            "causal_branches_to_stop": causal.get("branches_to_stop"),
            "preregistered_playbook_status": playbook.get("status"),
            "preregistered_playbook_concept_id": playbook.get("concept_id"),
            "momentum_continuation_replay_status": momentum_replay.get("status"),
            "momentum_continuation_replay_concept_id": momentum_replay.get("concept_id"),
            "momentum_continuation_replay_proof_rows": _as_dict(momentum_replay.get("proof_qualified")).get("row_count"),
            "momentum_continuation_replay_denominator_rows": _as_dict(momentum_replay.get("denominator")).get("row_count"),
            "momentum_continuation_replay_diagnostic_metrics": _as_dict(
                momentum_replay.get("diagnostic_only_existing_marks")
            ).get("metrics"),
            "momentum_continuation_proof_resolution_status": momentum_resolution.get("status"),
            "momentum_continuation_proof_resolution_after_rows": momentum_resolution.get("proof_qualified_rows_after_resolution"),
            "momentum_continuation_proof_resolution_side_aware_rows": _as_dict(momentum_resolution.get("resolution_counts")).get("side_aware_quotes_resolved"),
            "momentum_continuation_proof_resolution_blockers": momentum_resolution.get("blockers"),
            "momentum_continuation_bounded_replay_status": momentum_bounded.get("status"),
            "momentum_continuation_bounded_replay_exact_rows": _as_dict(momentum_bounded.get("metrics")).get("strict_new_exact_completed_rows"),
            "momentum_continuation_bounded_replay_side_aware_rows": _as_dict(momentum_bounded.get("metrics")).get("side_aware_quotes_resolved"),
            "momentum_continuation_bounded_replay_blockers": momentum_bounded.get("replay_gate_blockers"),
            "preregistered_vrp_credit_spread_status": vrp_playbook.get("status"),
            "preregistered_vrp_credit_spread_concept_id": vrp_playbook.get("concept_id"),
            "vrp_credit_spread_replay_readiness_status": vrp_readiness.get("status"),
            "vrp_credit_spread_replay_readiness_blockers": vrp_readiness.get("blockers"),
            "preregistered_term_structure_calendar_status": term_structure_playbook.get("status"),
            "preregistered_term_structure_calendar_concept_id": term_structure_playbook.get("concept_id"),
            "term_structure_calendar_replay_readiness_status": term_structure_readiness.get("status"),
            "term_structure_calendar_replay_readiness_blockers": term_structure_readiness.get("blockers"),
            "preregistered_skew_broken_wing_status": skew_broken_wing_playbook.get("status"),
            "preregistered_skew_broken_wing_concept_id": skew_broken_wing_playbook.get("concept_id"),
            "preregistered_macro_event_long_strangle_status": macro_event_long_strangle_playbook.get("status"),
            "preregistered_macro_event_long_strangle_concept_id": macro_event_long_strangle_playbook.get("concept_id"),
            "macro_event_calendar_status": macro_event_calendar.get("status"),
            "macro_event_calendar_blockers": macro_event_calendar.get("blockers"),
            "macro_event_calendar_event_count": macro_event_calendar.get("event_count"),
            "point_in_time_vix_bucket_status": point_in_time_vix_bucket.get("status"),
            "point_in_time_vix_bucket_available": point_in_time_vix_bucket.get("point_in_time_vix_low_mid_bucket_available"),
            "point_in_time_vix_bucket_blockers": point_in_time_vix_bucket.get("blockers"),
            "point_in_time_vix_bucket_coverage_pct": point_in_time_vix_bucket.get("coverage_pct"),
            "point_in_time_vix_bucket_source_rows_count": point_in_time_vix_bucket.get("source_rows_count"),
            "macro_event_long_strangle_replay_readiness_status": macro_event_long_strangle_readiness.get("status"),
            "macro_event_long_strangle_replay_readiness_blockers": macro_event_long_strangle_readiness.get("blockers"),
            "candidate_generation_13_symbol_surface_audit_status": candidate_generation_13_symbol_surface_audit.get("status"),
            "candidate_generation_13_symbol_surface_audit_blockers": candidate_generation_13_symbol_surface_audit.get("blockers"),
            "candidate_generation_13_symbol_quote_months": _as_dict(
                candidate_generation_13_symbol_surface_audit.get("quote_history_vs_candidate_generation")
            ).get("quote_surface_months_available_count"),
            "candidate_generation_13_symbol_candidate_months": _as_dict(
                candidate_generation_13_symbol_surface_audit.get("quote_history_vs_candidate_generation")
            ).get("candidate_generation_months_covered_count"),
            "candidate_generation_13_symbol_non_13_rows": _as_dict(
                candidate_generation_13_symbol_surface_audit.get("candidate_generation_surface")
            ).get("non_13_symbol_selected_row_count"),
            "candidate_generation_13_symbol_runner_status": _as_dict(
                candidate_generation_13_symbol_surface_audit.get("runner_support")
            ).get("status"),
            "candidate_generation_13_symbol_frozen_source_surface_status": candidate_generation_13_symbol_frozen_source_surface.get("status"),
            "candidate_generation_13_symbol_frozen_source_surface_blockers": candidate_generation_13_symbol_frozen_source_surface.get("blockers"),
            "candidate_generation_13_symbol_frozen_source_surface_months_covered": _as_dict(
                candidate_generation_13_symbol_frozen_source_surface.get("calendar_coverage")
            ).get("calendar_months_covered_count"),
            "candidate_generation_13_symbol_frozen_source_surface_selected_rows": _as_dict(
                candidate_generation_13_symbol_frozen_source_surface.get("selected_trade_summary")
            ).get("selected_rows_in_window"),
            "candidate_generation_13_symbol_frozen_source_surface_zero_pick_months": len(
                _as_list(
                    _as_dict(
                        candidate_generation_13_symbol_frozen_source_surface.get("calendar_coverage")
                    ).get("zero_selection_months")
                )
            ),
            "candidate_generation_13_symbol_frozen_entrypoint_status": candidate_generation_13_symbol_frozen_entrypoint.get("status"),
            "candidate_generation_13_symbol_frozen_entrypoint_blockers": candidate_generation_13_symbol_frozen_entrypoint.get("blockers"),
            "candidate_generation_13_symbol_frozen_entrypoint_daily_rows": candidate_generation_13_symbol_frozen_entrypoint.get(
                "daily_candidate_generation_row_count"
            ),
            "candidate_generation_13_symbol_frozen_entrypoint_selected_candidates": candidate_generation_13_symbol_frozen_entrypoint.get(
                "selected_candidate_row_count"
            ),
            "candidate_generation_13_symbol_frozen_entrypoint_covered_months": _as_dict(
                candidate_generation_13_symbol_frozen_entrypoint.get("coverage")
            ).get("candidate_generation_months_covered_count"),
            "candidate_generation_13_symbol_frozen_engine_status": candidate_generation_13_symbol_frozen_engine.get("status"),
            "candidate_generation_13_symbol_frozen_engine_decision": frozen_engine_decision,
            "candidate_generation_13_symbol_frozen_engine_blockers": candidate_generation_13_symbol_frozen_engine.get("blockers"),
            "candidate_generation_13_symbol_frozen_engine_daily_rows": candidate_generation_13_symbol_frozen_engine.get(
                "daily_candidate_generation_row_count"
            ),
            "candidate_generation_13_symbol_frozen_engine_selected_rows": candidate_generation_13_symbol_frozen_engine.get(
                "selected_candidate_row_count"
            ),
            "candidate_generation_13_symbol_frozen_engine_coverage": candidate_generation_13_symbol_frozen_engine.get("coverage"),
            "candidate_generation_13_symbol_frozen_engine_entrypoint_available": frozen_engine_entrypoint_available,
            "candidate_generation_13_symbol_frozen_engine_audit_consumed": candidate_generation_13_symbol_frozen_engine.get(
                "audit_consumed_generated_surface"
            ),
            "preregistered_post_event_iv_crush_iron_condor_status": post_event_iv_crush_iron_condor_playbook.get("status"),
            "preregistered_post_event_iv_crush_iron_condor_concept_id": post_event_iv_crush_iron_condor_playbook.get("concept_id"),
            "preregistered_flow_extreme_ratio_backspread_status": flow_extreme_ratio_backspread_playbook.get("status"),
            "preregistered_flow_extreme_ratio_backspread_concept_id": flow_extreme_ratio_backspread_playbook.get("concept_id"),
            "flow_extreme_volume_oi_source_rows_status": flow_extreme_volume_oi_source_rows.get("status"),
            "flow_extreme_volume_oi_source_row_count": flow_extreme_volume_oi_source_rows.get("source_row_count"),
            "flow_extreme_volume_oi_usable_aggregate_row_count": _as_dict(
                flow_extreme_volume_oi_source_rows.get("aggregate_source_summary")
            ).get("usable_aggregate_row_count"),
            "flow_extreme_volume_oi_coverage": flow_extreme_volume_oi_source_rows.get("coverage"),
            "flow_extreme_volume_oi_blockers": flow_extreme_volume_oi_source_rows.get("blockers"),
            "point_in_time_flow_extreme_input_status": point_in_time_flow_extreme_input.get("status"),
            "point_in_time_flow_extreme_input_blockers": point_in_time_flow_extreme_input.get("blockers"),
            "point_in_time_flow_extreme_input_covered_months": _as_dict(
                point_in_time_flow_extreme_input.get("coverage")
            ).get("covered_month_count"),
            "point_in_time_flow_extreme_input_date_coverage_pct": _as_dict(
                point_in_time_flow_extreme_input.get("coverage")
            ).get("date_coverage_pct"),
            "point_in_time_flow_extreme_input_source_inventory_status": _as_dict(
                point_in_time_flow_extreme_input.get("source_inventory")
            ).get("status"),
            "point_in_time_flow_extreme_input_proxy_basis": point_in_time_flow_extreme_input.get("proxy_basis"),
            "multi_leg_side_aware_pricing_capability_status": multi_leg_side_aware_pricing_capability.get("status"),
            "ratio_backspread_bounded_pricing_status": _as_dict(
                _as_dict(multi_leg_side_aware_pricing_capability.get("structure_support")).get("ratio_backspread_bounded")
            ).get("status"),
            "denominator_mapping_status": _as_dict(
                _as_dict(multi_leg_side_aware_pricing_capability.get("structure_support")).get("ratio_backspread_bounded")
            ).get("denominator_mapping_status"),
            "pricing_capability_blockers": multi_leg_side_aware_pricing_capability.get("pricing_capability_blockers"),
            "base_clean_stack_identity_ledger_status": base_clean_stack_identity_ledger.get("status"),
            "base_clean_stack_identity_ledger_expected_rows": base_clean_stack_identity_ledger.get(
                "expected_base_clean_stack_exact_rows"
            ),
            "base_clean_stack_identity_ledger_row_count": base_clean_stack_identity_ledger.get("ledger_row_count"),
            "base_clean_stack_identity_ledger_unique_count": base_clean_stack_identity_ledger.get("unique_identity_count"),
            "base_clean_stack_identity_ledger_duplicate_count": base_clean_stack_identity_ledger.get(
                "duplicate_identity_count"
            ),
            "base_clean_stack_identity_ledger_missing_identity_rows": base_clean_stack_identity_ledger.get(
                "missing_identity_field_row_count"
            ),
            "base_clean_stack_identity_ledger_future_dependency_rows": base_clean_stack_identity_ledger.get(
                "future_or_outcome_field_dependency_count"
            ),
            "base_clean_stack_identity_ledger_holdout_overlap_count": base_clean_stack_identity_ledger.get(
                "protected_holdout_overlap_count"
            ),
            "base_clean_stack_identity_ledger_blockers": base_clean_stack_identity_ledger.get("blockers"),
            "flow_readiness_pricing_blocker_cleared": "missing_side_aware_ratio_backspread_pricing"
            not in _as_list(flow_extreme_ratio_backspread_readiness.get("blockers")),
            "flow_extreme_denominator_dedupe_bridge_status": flow_extreme_denominator_dedupe_bridge.get("status"),
            "flow_extreme_full_denominator_mapping_status": flow_extreme_denominator_dedupe_bridge.get(
                "full_denominator_mapping_status"
            ),
            "flow_extreme_strict_new_dedupe_status": flow_extreme_denominator_dedupe_bridge.get("strict_new_dedupe_status"),
            "flow_extreme_denominator_dedupe_bridge_blockers": flow_extreme_denominator_dedupe_bridge.get("bridge_blockers"),
            "flow_readiness_full_denominator_blocker_cleared": "missing_full_denominator_mapping"
            not in _as_list(flow_extreme_ratio_backspread_readiness.get("blockers")),
            "flow_readiness_strict_new_dedupe_blocker_cleared": "missing_strict_new_dedupe"
            not in _as_list(flow_extreme_ratio_backspread_readiness.get("blockers")),
            "flow_extreme_ratio_backspread_replay_readiness_status": flow_extreme_ratio_backspread_readiness_validation[
                "validated_status"
            ],
            "flow_extreme_ratio_backspread_replay_readiness_raw_status": flow_extreme_ratio_backspread_readiness_validation[
                "raw_status"
            ],
            "flow_extreme_ratio_backspread_replay_readiness_reason_codes": flow_extreme_ratio_backspread_readiness_validation[
                "reason_codes"
            ],
            "flow_extreme_ratio_backspread_replay_readiness_generated_at_utc": flow_extreme_ratio_backspread_readiness_validation[
                "generated_at_utc"
            ],
            "flow_extreme_ratio_backspread_replay_readiness_blockers": flow_extreme_ratio_backspread_readiness.get("blockers"),
            "flow_extreme_ratio_backspread_replay_readiness_smallest_next_blocker": flow_extreme_ratio_backspread_readiness.get(
                "smallest_next_blocker_clearing_slice"
            ),
            "preregistered_dispersion_proxy_hybrid_status": dispersion_proxy_hybrid_playbook.get("status"),
            "preregistered_dispersion_proxy_hybrid_concept_id": dispersion_proxy_hybrid_playbook.get("concept_id"),
            "point_in_time_dispersion_concentration_proxy_status": point_in_time_dispersion_proxy.get("status"),
            "point_in_time_dispersion_concentration_proxy_blockers": point_in_time_dispersion_proxy.get("blockers"),
            "point_in_time_dispersion_concentration_proxy_covered_months": _as_dict(
                point_in_time_dispersion_proxy.get("coverage")
            ).get("covered_month_count"),
            "point_in_time_dispersion_concentration_proxy_date_coverage_pct": _as_dict(
                point_in_time_dispersion_proxy.get("coverage")
            ).get("date_coverage_pct"),
            "point_in_time_dispersion_concentration_proxy_source_inventory_status": _as_dict(
                point_in_time_dispersion_proxy.get("source_inventory")
            ).get("status"),
            "dispersion_proxy_hybrid_replay_readiness_status": dispersion_proxy_hybrid_readiness.get("status"),
            "dispersion_proxy_hybrid_replay_readiness_blockers": dispersion_proxy_hybrid_readiness.get("blockers"),
            "dispersion_proxy_hybrid_replay_readiness_smallest_next_blocker": dispersion_proxy_hybrid_readiness.get(
                "smallest_next_blocker_clearing_slice"
            ),
            "preregistered_pmcc_diagonal_status": pmcc_diagonal_playbook.get("status"),
            "preregistered_pmcc_diagonal_concept_id": pmcc_diagonal_playbook.get("concept_id"),
            "pmcc_diagonal_replay_readiness_status": pmcc_diagonal_readiness_validation["validated_status"],
            "pmcc_diagonal_replay_readiness_raw_status": pmcc_diagonal_readiness_validation["raw_status"],
            "pmcc_diagonal_replay_readiness_reason_codes": pmcc_diagonal_readiness_validation["reason_codes"],
            "pmcc_diagonal_replay_readiness_generated_at_utc": pmcc_diagonal_readiness_validation["generated_at_utc"],
            "pmcc_diagonal_replay_readiness_blockers": pmcc_diagonal_readiness.get("blockers"),
            "pmcc_diagonal_replay_readiness_smallest_next_blocker": pmcc_diagonal_readiness.get(
                "smallest_next_blocker_clearing_slice"
            ),
            "source_repair_59_symbol_status": source_repair_59_symbol.get("status"),
            "source_repair_59_symbol_approval_token_valid": source_repair_59_symbol.get("approval_token_valid"),
            "source_repair_59_symbol_blockers": source_repair_59_symbol.get("blockers"),
            "source_repair_59_symbol_theta_terminal": source_repair_59_symbol.get("theta_terminal"),
            "source_repair_59_symbol_shared_trusted_dates": source_repair_59_symbol.get(
                "shared_trusted_imported_quote_dates"
            ),
            "source_repair_59_symbol_missing_symbol_date_count": source_repair_59_symbol.get(
                "missing_symbol_date_count"
            ),
            "source_repair_59_symbol_import_attempted": source_repair_59_symbol.get("import_attempted"),
            "source_repair_59_symbol_imported_rows": source_repair_59_symbol.get("imported_rows"),
            "source_repair_59_symbol_quotes_imported": source_repair_59_symbol.get("quotes_imported"),
            "source_repair_59_symbol_accepted_profitability": source_repair_59_symbol.get("accepted_profitability"),
            "source_repair_59_symbol_resume_status": source_repair_59_symbol_resume.get("status"),
            "source_repair_59_symbol_resume_approval_token_valid": source_repair_59_symbol_resume.get("approval_token_valid"),
            "source_repair_59_symbol_resume_blockers": source_repair_59_symbol_resume.get("blockers"),
            "source_repair_59_symbol_resume_theta_terminal": source_repair_59_symbol_resume.get("theta_terminal"),
            "source_repair_59_symbol_resume_shared_trusted_dates": source_repair_59_symbol_resume.get(
                "shared_trusted_imported_quote_dates"
            ),
            "source_repair_59_symbol_resume_missing_symbol_date_count": source_repair_59_symbol_resume.get(
                "missing_symbol_date_count"
            ),
            "source_repair_59_symbol_resume_import_attempted": source_repair_59_symbol_resume.get("import_attempted"),
            "source_repair_59_symbol_resume_imported_rows": source_repair_59_symbol_resume.get("imported_rows"),
            "source_repair_59_symbol_resume_quotes_imported": source_repair_59_symbol_resume.get("quotes_imported"),
            "source_repair_59_symbol_resume_protected_holdout_overlap_rows": source_repair_59_symbol_resume.get(
                "protected_holdout_overlap_rows"
            ),
            "source_repair_59_symbol_resume_outside_universe_import_rows": source_repair_59_symbol_resume.get(
                "outside_universe_import_rows"
            ),
            "direct_vix_source_import_status": direct_vix_source_import.get("status"),
            "direct_vix_materialized": direct_vix_materialized,
            "direct_vix_current_state": direct_vix_current_state,
            "direct_vix_source_repair_packet_status": direct_vix_source_repair_packet.get("status"),
            "direct_vix_legacy_source_repair_packet_status": direct_vix_source_repair_packet.get("status"),
            "direct_vix_legacy_source_repair_packet_blockers": direct_vix_source_repair_packet.get("blockers"),
            "direct_vix_source_family": direct_vix_source_import.get("source_family")
            or direct_vix_source_repair_packet.get("source_family"),
            "direct_vix_source_baseline": direct_vix_current_state,
            "direct_vix_known_at_policy": direct_vix_source_repair_packet.get("known_at_policy"),
            "direct_vix_bucket_policy": direct_vix_source_repair_packet.get("bucket_policy"),
            "direct_vix_future_import_command_executed": direct_vix_materialized,
            "direct_vix_downstream_vix_bucket_command_executed": vix_bucket_ready,
            "direct_vix_quotes_imported": direct_vix_source_import.get("quotes_imported"),
            "direct_vix_evidence_stores_mutated": direct_vix_source_import.get("evidence_stores_mutated"),
            "direct_vix_protected_holdout_consumed": direct_vix_source_import.get("protected_holdout_consumed"),
            "direct_vix_fixture_validation": direct_vix_source_repair_packet.get("fixture_validation"),
            "direct_vix_future_import_manifest_template": direct_vix_source_repair_packet.get(
                "future_import_manifest_template"
            ),
            "direct_vix_future_commands": {
                "future_import_command": direct_vix_source_repair_packet.get("future_import_command"),
                "downstream_vix_bucket_materialization_command": direct_vix_source_repair_packet.get(
                    "downstream_vix_bucket_materialization_command"
                ),
            },
            "direct_vix_branch_implications": current_vix_branch_implications,
            "macro_event_calendar_source_repair_packet_status": macro_event_calendar_source_repair_packet.get(
                "status"
            ),
            "macro_event_calendar_source_repair_packet_blockers": macro_event_calendar_source_repair_packet.get(
                "blockers"
            ),
            "macro_event_calendar_source_family": macro_event_calendar_source_repair_packet.get("source_family"),
            "macro_event_calendar_source_baseline": {
                "macro_event_calendar_status": macro_event_calendar_source_repair_packet.get(
                    "macro_event_calendar_status"
                ),
                "event_count": macro_event_calendar_source_repair_packet.get("event_count"),
                "covered_categories": macro_event_calendar_source_repair_packet.get("covered_categories"),
                "missing_required_categories": macro_event_calendar_source_repair_packet.get(
                    "missing_required_categories"
                ),
                "current_forward_rows": macro_event_calendar_source_repair_packet.get("current_forward_rows"),
                "target_forward_rows": macro_event_calendar_source_repair_packet.get("target_forward_rows"),
            },
            "macro_event_calendar_known_at_policy": macro_event_calendar_source_repair_packet.get("known_at_policy"),
            "macro_event_calendar_tradable_after_policy": macro_event_calendar_source_repair_packet.get(
                "tradable_after_policy"
            ),
            "macro_event_calendar_future_import_command_executed": macro_event_calendar_source_repair_packet.get(
                "future_import_command_executed"
            ),
            "macro_event_calendar_quotes_imported": macro_event_calendar_source_repair_packet.get("quotes_imported"),
            "macro_event_calendar_evidence_stores_mutated": macro_event_calendar_source_repair_packet.get(
                "evidence_stores_mutated"
            ),
            "macro_event_calendar_protected_holdout_consumed": macro_event_calendar_source_repair_packet.get(
                "protected_holdout_consumed"
            ),
            "macro_event_calendar_fixture_validation": macro_event_calendar_source_repair_packet.get(
                "fixture_validation"
            ),
            "macro_event_calendar_future_import_manifest_template": macro_event_calendar_source_repair_packet.get(
                "future_import_manifest_template"
            ),
            "macro_event_calendar_future_commands": {
                "future_import_command": macro_event_calendar_source_repair_packet.get("future_import_command"),
                "downstream_readiness_commands": macro_event_calendar_source_repair_packet.get(
                    "downstream_readiness_commands"
                ),
            },
            "macro_event_calendar_branch_implications": macro_event_calendar_source_repair_packet.get(
                "downstream_branch_implications"
            ),
            "flow_extreme_source_repair_packet_status": flow_extreme_source_repair_packet.get("status"),
            "flow_extreme_source_repair_packet_blockers": flow_extreme_source_repair_packet.get("blockers"),
            "flow_extreme_source_family": flow_extreme_source_repair_packet.get("source_family"),
            "flow_extreme_source_baseline": {
                "point_in_time_flow_extreme_input_status": flow_extreme_source_repair_packet.get(
                    "point_in_time_flow_extreme_input_status"
                ),
                "flow_extreme_volume_oi_source_rows_status": flow_extreme_source_repair_packet.get(
                    "flow_extreme_volume_oi_source_rows_status"
                ),
                "covered_month_count": flow_extreme_source_repair_packet.get("covered_month_count"),
                "date_coverage_pct": flow_extreme_source_repair_packet.get("date_coverage_pct"),
                "flow_extreme_ratio_backspread_replay_readiness_status": flow_extreme_source_repair_packet.get(
                    "flow_extreme_ratio_backspread_replay_readiness_status"
                ),
                "current_forward_rows": flow_extreme_source_repair_packet.get("current_forward_rows"),
                "target_forward_rows": flow_extreme_source_repair_packet.get("target_forward_rows"),
            },
            "flow_extreme_known_at_policy": flow_extreme_source_repair_packet.get("known_at_policy"),
            "flow_extreme_threshold_policy": flow_extreme_source_repair_packet.get("threshold_policy"),
            "flow_extreme_future_import_command_executed": flow_extreme_source_repair_packet.get(
                "future_import_command_executed"
            ),
            "flow_extreme_quotes_imported": flow_extreme_source_repair_packet.get("quotes_imported"),
            "flow_extreme_evidence_stores_mutated": flow_extreme_source_repair_packet.get(
                "evidence_stores_mutated"
            ),
            "flow_extreme_protected_holdout_consumed": flow_extreme_source_repair_packet.get(
                "protected_holdout_consumed"
            ),
            "flow_extreme_fixture_validation": flow_extreme_source_repair_packet.get("fixture_validation"),
            "flow_extreme_future_import_manifest_template": flow_extreme_source_repair_packet.get(
                "future_import_manifest_template"
            ),
            "flow_extreme_future_commands": {
                "future_import_command": flow_extreme_source_repair_packet.get("future_import_command"),
                "downstream_readiness_commands": flow_extreme_source_repair_packet.get(
                    "downstream_readiness_commands"
                ),
            },
            "flow_extreme_branch_implications": [
                {
                    "branch": "flow_extreme_ratio_backspread",
                    "flow_blockers": [
                        blocker
                        for blocker in _as_list(flow_extreme_ratio_backspread_readiness.get("blockers"))
                        if "flow" in str(blocker).lower()
                    ],
                    "remaining_non_flow_blockers": [
                        blocker
                        for blocker in _as_list(flow_extreme_ratio_backspread_readiness.get("blockers"))
                        if "flow" not in str(blocker).lower()
                    ],
                    "status": flow_extreme_ratio_backspread_readiness.get("status"),
                    "vix_status": "ready" if vix_bucket_ready else "blocked",
                }
            ],
            "goal_loop_state": goal_loop.get("current_decision_state"),
            "goal_loop_next_safe_action": goal_loop.get("next_safe_action"),
            "goal_loop_forward_accounting": goal_loop.get("forward_evidence_accounting"),
        },
        "continuation_branches": CONTINUATION_BRANCHES,
        "gpt55_required_output_schema": GPT_OUTPUT_SCHEMA,
        "prompt": _render_prompt(
            frontier=frontier,
            momentum=momentum,
            causal=causal,
            playbook=playbook,
            momentum_replay=momentum_replay,
            momentum_resolution=momentum_resolution,
            momentum_bounded=momentum_bounded,
            vrp_playbook=vrp_playbook,
            vrp_readiness=vrp_readiness,
            term_structure_playbook=term_structure_playbook,
            term_structure_readiness=term_structure_readiness,
            skew_broken_wing_playbook=skew_broken_wing_playbook,
            macro_event_long_strangle_playbook=macro_event_long_strangle_playbook,
            macro_event_calendar=macro_event_calendar,
            point_in_time_vix_bucket=point_in_time_vix_bucket,
            macro_event_long_strangle_readiness=macro_event_long_strangle_readiness,
            candidate_generation_13_symbol_surface_audit=candidate_generation_13_symbol_surface_audit,
            candidate_generation_13_symbol_frozen_source_surface=candidate_generation_13_symbol_frozen_source_surface,
            candidate_generation_13_symbol_frozen_engine=candidate_generation_13_symbol_frozen_engine,
            candidate_generation_13_symbol_frozen_entrypoint=candidate_generation_13_symbol_frozen_entrypoint,
            post_event_iv_crush_iron_condor_playbook=post_event_iv_crush_iron_condor_playbook,
            flow_extreme_ratio_backspread_playbook=flow_extreme_ratio_backspread_playbook,
            flow_extreme_volume_oi_source_rows=flow_extreme_volume_oi_source_rows,
            point_in_time_flow_extreme_input=point_in_time_flow_extreme_input,
            multi_leg_side_aware_pricing_capability=multi_leg_side_aware_pricing_capability,
            base_clean_stack_identity_ledger=base_clean_stack_identity_ledger,
            flow_extreme_denominator_dedupe_bridge=flow_extreme_denominator_dedupe_bridge,
            flow_extreme_ratio_backspread_readiness=flow_extreme_ratio_backspread_readiness,
            flow_extreme_ratio_backspread_readiness_validation=flow_extreme_ratio_backspread_readiness_validation,
            dispersion_proxy_hybrid_playbook=dispersion_proxy_hybrid_playbook,
            point_in_time_dispersion_proxy=point_in_time_dispersion_proxy,
            dispersion_proxy_hybrid_readiness=dispersion_proxy_hybrid_readiness,
            pmcc_diagonal_playbook=pmcc_diagonal_playbook,
            pmcc_diagonal_readiness=pmcc_diagonal_readiness,
            pmcc_diagonal_readiness_validation=pmcc_diagonal_readiness_validation,
            source_repair_59_symbol=source_repair_59_symbol,
            source_repair_59_symbol_resume=source_repair_59_symbol_resume,
            direct_vix_source_import=direct_vix_source_import,
            direct_vix_source_repair_packet=direct_vix_source_repair_packet,
            current_vix_branch_implications=current_vix_branch_implications,
            macro_event_calendar_source_repair_packet=macro_event_calendar_source_repair_packet,
            flow_extreme_source_repair_packet=flow_extreme_source_repair_packet,
            goal_loop=goal_loop,
            next_steps_excerpt=next_steps,
            decisions_excerpt=decisions,
            context_excerpt=context,
        ),
    }
    _validate_packet(packet)
    return packet


def _validate_packet(packet: dict[str, Any]) -> None:
    for key, expected in SAFETY_FLAGS.items():
        if packet.get(key) is not expected:
            raise ValueError(f"safety flag mismatch for {key}")
    if not packet.get("prompt"):
        raise ValueError("prompt missing")


def _render_prompt(
    *,
    frontier: dict[str, Any],
    momentum: dict[str, Any],
    causal: dict[str, Any],
    playbook: dict[str, Any],
    momentum_replay: dict[str, Any],
    momentum_resolution: dict[str, Any],
    momentum_bounded: dict[str, Any],
    vrp_playbook: dict[str, Any],
    vrp_readiness: dict[str, Any],
    term_structure_playbook: dict[str, Any],
    term_structure_readiness: dict[str, Any],
    skew_broken_wing_playbook: dict[str, Any],
    macro_event_long_strangle_playbook: dict[str, Any],
    macro_event_calendar: dict[str, Any],
    point_in_time_vix_bucket: dict[str, Any],
    macro_event_long_strangle_readiness: dict[str, Any],
    candidate_generation_13_symbol_surface_audit: dict[str, Any],
    candidate_generation_13_symbol_frozen_source_surface: dict[str, Any],
    candidate_generation_13_symbol_frozen_engine: dict[str, Any],
    candidate_generation_13_symbol_frozen_entrypoint: dict[str, Any],
    post_event_iv_crush_iron_condor_playbook: dict[str, Any],
    flow_extreme_ratio_backspread_playbook: dict[str, Any],
    flow_extreme_volume_oi_source_rows: dict[str, Any],
    point_in_time_flow_extreme_input: dict[str, Any],
    multi_leg_side_aware_pricing_capability: dict[str, Any],
    base_clean_stack_identity_ledger: dict[str, Any],
    flow_extreme_denominator_dedupe_bridge: dict[str, Any],
    flow_extreme_ratio_backspread_readiness: dict[str, Any],
    flow_extreme_ratio_backspread_readiness_validation: dict[str, Any],
    dispersion_proxy_hybrid_playbook: dict[str, Any],
    point_in_time_dispersion_proxy: dict[str, Any],
    dispersion_proxy_hybrid_readiness: dict[str, Any],
    pmcc_diagonal_playbook: dict[str, Any],
    pmcc_diagonal_readiness: dict[str, Any],
    pmcc_diagonal_readiness_validation: dict[str, Any],
    source_repair_59_symbol: dict[str, Any],
    source_repair_59_symbol_resume: dict[str, Any],
    direct_vix_source_import: dict[str, Any],
    direct_vix_source_repair_packet: dict[str, Any],
    current_vix_branch_implications: list[dict[str, Any]],
    macro_event_calendar_source_repair_packet: dict[str, Any],
    flow_extreme_source_repair_packet: dict[str, Any],
    goal_loop: dict[str, Any],
    next_steps_excerpt: str,
    decisions_excerpt: str,
    context_excerpt: str,
) -> str:
    frontier_summary = _frontier_summary(frontier)
    return f"""Replace the current 5.5 Pro handoff prompt with this profitability-first blocker-ranking prompt before continuing the loop.

We are running an options-profitability loop. The user's goal is profit: at least 30 profitable strict completed forward-audit trades in the latest approximately 4-month/post-freeze audit window.

Current state:
- We are not forward-audit profitable.
- Strict completed forward proof is currently 0/30.
- Historical rows, dashboard rows, midpoint/stale/EOD/last/model/manual/synthetic/lookahead rows, and old-algorithm picks are not accepted profitability proof.
- Codex can implement, test, inspect the repo, build artifacts, run read-only research, and run non-live/non-broker source-planning tasks.
- The user approves non-live, non-broker research/source-planning work.
- Broker orders, live validation, auto-track, protected-holdout consumption, promotion, production scanner/strategy/stop/sizing/proof-bar changes, and real source/evidence mutation still require exact explicit approval.

Your job:
Do not optimize for documentation completeness. Do not choose the safest artifact by default. Optimize for the shortest honest path to 30 profitable strict completed forward-audit trades.

Before selecting a task, produce a blocker map with these categories:

1. Forward proof blocker
- Why are there 0/30 strict completed forward rows?
- Are current scanners producing real same-day candidates?
- If not, what is the fastest way to increase real candidate throughput without fake rows?

2. Candidate-generation blocker
- Is the current algorithm generating enough eligible candidates?
- If candidate generation is missing/broken, what exact repair unlocks real rows fastest?
- Do not accept quote-depth-only coverage as candidate-generation proof.

3. Data/source blocker
- Which missing point-in-time sources block the most downstream profitable tests?
- Current or recently cleared source blockers include VIX, macro-event calendar, flow volume/OI, dispersion/concentration, trend/regime, and possibly broader OPRA/NBBO coverage. Use the attached current artifacts: if VIX is `point_in_time_vix_bucket_ready`, do not rank VIX as still missing.
- Rank source repairs by downstream unlock value and time-to-test.
- Do not select another packet-only source plan unless it is the highest-leverage blocker to running a real replay or forward audit.

4. Replay/engine blocker
- Which strategies cannot be honestly tested because pricing/replay engine support is missing?
- Consider credit spreads, calendars, diagonals, condors, butterflies, ratio/backspreads, straddles/strangles, PMCC-style diagonals, debit/credit hybrids.
- Rank engine work by ability to unlock countable exact rows.

5. Strategy/edge blocker
- Are we testing enough option edge families?
- Consider volatility risk premium, skew, term structure, event volatility, IV crush, post-event drift, momentum continuation, mean reversion, dispersion proxy, and flow/liquidity effects.
- Do not assume existing directional debit-spread surfaces exhaust the opportunity set.

6. Historical audit blocker
- Can the existing 2-year data be used to produce a strict simulated-forward audit?
- If not, name the exact missing chain: candidate-generation surface, source depth, quote coverage, strict-new dedupe, exact bid/ask pricing, or holdout/proof issue.
- Do not say "collect more data" unless you name the exact file/source/command/threshold.

7. Dashboard/operator blocker
- Only choose dashboard work if it directly changes operator decisions or forward evidence capture.
- Dashboard visibility alone is not a profit upgrade.

Then rank all possible next tasks by:
- expected increase in countable profitable rows,
- chance of unlocking a replay or forward audit,
- time-to-test,
- number of downstream branches unblocked,
- overfit/leakage/data-integrity risk,
- whether it can be done now without live/broker action.

Return exactly one next Codex task.

The selected task must include:
- objective,
- why this is the highest-leverage path to profitability,
- exact files/artifacts allowed,
- exact files/artifacts forbidden,
- implementation steps,
- commands to run,
- acceptance criteria,
- failure criteria,
- what downstream replay/audit becomes possible if it passes,
- what branch should be stopped if it fails.

Hard rules:
- Do not repeat a branch already marked parked unless new source state changed.
- Do not select macro_event_calendar_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select direct_point_in_time_vix_source_repair_packet_v1 again; it is already implemented and verified.
- Do not select trusted_flow_volume_oi_source_repair_packet_v1 again if the attached/current artifact status is flow_extreme_source_repair_packet_ready_for_operator_import_decision; it is already implemented and verified.
- Do not select the 59-symbol ThetaTerminal retry again until provider/source availability changes.
- Do not select historical dashboard/picks visibility unless it directly affects forward capture.
- Do not claim profitability from historical rows alone.
- Do not stop unless you prove no meaningful upgrade remains across forward capture, source repair/materialization, candidate-generation repair, replay engine support, new option structures, and longer/lookback audits.

Output JSON-like structure:
{{
  "verdict": "continue|stop_exception",
  "continue_loop": true/false,
  "current_profitability_state": {{
    "forward_strict_completed_rows": number,
    "target_rows": 30,
    "accepted_profitability": true/false,
    "main_reason_not_profitable": "string"
  }},
  "blocker_map": {{
    "forward_proof": [],
    "candidate_generation": [],
    "data_sources": [],
    "replay_engine": [],
    "strategy_edges": [],
    "historical_audit": [],
    "dashboard_operator": []
  }},
  "ranked_next_tasks": [
    {{
      "rank": 1,
      "task_id": "string",
      "expected_profitability_impact": "string",
      "downstream_unlocks": [],
      "time_to_test": "string",
      "why_not_selected_if_applicable": null
    }}
  ],
  "selected_branch_id": "string",
  "next_codex_task": {{
    "objective": "string",
    "why_highest_leverage": "string",
    "exact_scope": "string",
    "allowed_files_or_artifacts": [],
    "forbidden_actions": [],
    "implementation_steps": [],
    "commands_to_run": [],
    "acceptance_criteria": [],
    "failure_criteria": [],
    "downstream_enabled_if_passes": [],
    "branch_stop_condition_if_fails": "string"
  }},
  "branches_to_stop": [],
  "operator_questions": [],
  "anti_handwave_audit": {{
    "exact_next_action_present": true,
    "measurable_threshold_present": true,
    "generic_advice_removed": true
  }}
}}

Current repo evidence appendix follows. Use this evidence for the blocker map and next-task ranking; do not ignore completed/parked artifacts.

We are continuing the same regular-options profitability loop in the existing GPT-5.5 Pro ChatGPT session.

You are GPT-5.5 Pro acting as strategic reviewer and next-slice selector. Codex will implement and verify. The user wants this loop to continue until GPT-5.5 Pro says there are no significant upgrades left.

Operator approval posture:
{json.dumps(OPERATOR_APPROVAL_POSTURE, indent=2, sort_keys=True)}

Primary goal:
Make the regular-options workflow profitable under proof-qualified criteria. The practical target is at least 30 profitable strict completed rows in the latest approximately four months / post-freeze forward-style audit window. Profit means executable exact net P&L after fees/slippage, defensible PF/lower-bound/holdout/forward proof, and no unresolved data-quality defects that could flip the result. Do not accept raw overlapping historical count, midpoint/stale/display/EOD/last/model/manual marks, lookahead-only rows, zero-bid/untradable rows, or historical dashboard/replay rows as live proof.

Current proof posture:
- The system is not forward-audit profitable.
- Strict post-freeze forward proof is currently 0/30 completed exact rows.
- The historical current-policy replay panel was removed from the operator dashboard because it could be mistaken for current recommendations or forward-audit performance.
- The latest-four-month simulated audit is hypothesis-generating only unless its row set, data depth, leakage controls, and PF lower-bound satisfy the strict proof contract.

Current frontier result:
{json.dumps(frontier_summary, indent=2, sort_keys=True)}

Current momentum-edge result:
{json.dumps({"status": momentum.get("status"), "decision_counts": momentum.get("decision_counts"), "countable_momentum_edge_candidate_count": momentum.get("countable_momentum_edge_candidate_count")}, indent=2, sort_keys=True)}

Current causal-falsification result, if available:
{json.dumps({"status": causal.get("status"), "continue_loop": causal.get("continue_loop"), "significant_upgrade_available": causal.get("significant_upgrade_available"), "hypothesis_status_counts": causal.get("hypothesis_status_counts"), "branches_to_stop": causal.get("branches_to_stop")}, indent=2, sort_keys=True)}

Current preregistered playbook result, if available:
{json.dumps({"status": playbook.get("status"), "concept_id": playbook.get("concept_id"), "accepted_profitability": playbook.get("accepted_profitability"), "lane_implementation_performed": playbook.get("lane_implementation_performed"), "allowed_next_step": playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current approved momentum-continuation research replay result, if available:
{json.dumps({"status": momentum_replay.get("status"), "concept_id": momentum_replay.get("concept_id"), "accepted_profitability": momentum_replay.get("accepted_profitability"), "research_only_replay_harness_implemented": momentum_replay.get("research_only_replay_harness_implemented"), "historical_replay_performed": momentum_replay.get("historical_replay_performed"), "lane_implementation_performed": momentum_replay.get("lane_implementation_performed"), "denominator_rows": _as_dict(momentum_replay.get("denominator")).get("row_count"), "denominator_status_counts": _as_dict(momentum_replay.get("denominator")).get("status_counts"), "proof_qualified_rows": _as_dict(momentum_replay.get("proof_qualified")).get("row_count"), "proof_metrics": _as_dict(momentum_replay.get("proof_qualified")).get("metrics"), "diagnostic_only_metrics": _as_dict(momentum_replay.get("diagnostic_only_existing_marks")).get("metrics"), "top_blockers": _as_dict(momentum_replay.get("denominator")).get("top_blockers")}, indent=2, sort_keys=True)}

Current momentum-continuation proof-blocker resolution result, if available:
{json.dumps({"status": momentum_resolution.get("status"), "concept_id": momentum_resolution.get("concept_id"), "accepted_profitability": momentum_resolution.get("accepted_profitability"), "source_denominator_rows": momentum_resolution.get("source_denominator_rows"), "reconstructed_denominator_rows": momentum_resolution.get("reconstructed_denominator_rows"), "proof_qualified_rows_before_resolution": momentum_resolution.get("proof_qualified_rows_before_resolution"), "proof_qualified_rows_after_resolution": momentum_resolution.get("proof_qualified_rows_after_resolution"), "historical_rows_are_forward_proof": momentum_resolution.get("historical_rows_are_forward_proof"), "resolution_counts": momentum_resolution.get("resolution_counts"), "strict_research_metrics": momentum_resolution.get("strict_research_metrics"), "side_aware_diagnostic_metrics": momentum_resolution.get("side_aware_diagnostic_metrics"), "blockers": momentum_resolution.get("blockers")}, indent=2, sort_keys=True)}

Current momentum-continuation bounded replay gate result, if available:
{json.dumps({"status": momentum_bounded.get("status"), "concept_id": momentum_bounded.get("concept_id"), "accepted_profitability": momentum_bounded.get("accepted_profitability"), "historical_replay_performed": momentum_bounded.get("historical_replay_performed"), "existing_resolution_consumed": momentum_bounded.get("existing_resolution_consumed"), "historical_rows_are_forward_proof": momentum_bounded.get("historical_rows_are_forward_proof"), "metrics": momentum_bounded.get("metrics"), "replay_gate_blockers": momentum_bounded.get("replay_gate_blockers"), "next_oracle_instruction": momentum_bounded.get("next_oracle_instruction")}, indent=2, sort_keys=True)}

Current preregistered VRP credit-spread playbook result, if available:
{json.dumps({"status": vrp_playbook.get("status"), "concept_id": vrp_playbook.get("concept_id"), "structure": vrp_playbook.get("structure"), "accepted_profitability": vrp_playbook.get("accepted_profitability"), "lane_implementation_performed": vrp_playbook.get("lane_implementation_performed"), "allowed_next_step": vrp_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current VRP credit-spread replay readiness result, if available:
{json.dumps({"status": vrp_readiness.get("status"), "concept_id": vrp_readiness.get("concept_id"), "accepted_profitability": vrp_readiness.get("accepted_profitability"), "historical_replay_performed": vrp_readiness.get("historical_replay_performed"), "lane_implementation_performed": vrp_readiness.get("lane_implementation_performed"), "blockers": vrp_readiness.get("blockers"), "allowed_next_step": vrp_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered term-structure calendar/diagonal playbook result, if available:
{json.dumps({"status": term_structure_playbook.get("status"), "concept_id": term_structure_playbook.get("concept_id"), "structure": term_structure_playbook.get("structure"), "accepted_profitability": term_structure_playbook.get("accepted_profitability"), "historical_replay_performed": term_structure_playbook.get("historical_replay_performed"), "lane_implementation_performed": term_structure_playbook.get("lane_implementation_performed"), "allowed_next_step": term_structure_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current term-structure calendar/diagonal replay readiness result, if available:
{json.dumps({"status": term_structure_readiness.get("status"), "concept_id": term_structure_readiness.get("concept_id"), "accepted_profitability": term_structure_readiness.get("accepted_profitability"), "historical_replay_performed": term_structure_readiness.get("historical_replay_performed"), "lane_implementation_performed": term_structure_readiness.get("lane_implementation_performed"), "blockers": term_structure_readiness.get("blockers"), "allowed_next_step": term_structure_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered skew broken-wing playbook result, if available:
{json.dumps({"status": skew_broken_wing_playbook.get("status"), "concept_id": skew_broken_wing_playbook.get("concept_id"), "structure": skew_broken_wing_playbook.get("structure"), "accepted_profitability": skew_broken_wing_playbook.get("accepted_profitability"), "historical_replay_performed": skew_broken_wing_playbook.get("historical_replay_performed"), "lane_implementation_performed": skew_broken_wing_playbook.get("lane_implementation_performed"), "allowed_next_step": skew_broken_wing_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered macro-event long straddle/strangle playbook result, if available:
{json.dumps({"status": macro_event_long_strangle_playbook.get("status"), "concept_id": macro_event_long_strangle_playbook.get("concept_id"), "structure": macro_event_long_strangle_playbook.get("structure"), "accepted_profitability": macro_event_long_strangle_playbook.get("accepted_profitability"), "historical_replay_performed": macro_event_long_strangle_playbook.get("historical_replay_performed"), "lane_implementation_performed": macro_event_long_strangle_playbook.get("lane_implementation_performed"), "allowed_next_step": macro_event_long_strangle_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current macro-event calendar artifact result, if available:
{json.dumps({"status": macro_event_calendar.get("status"), "accepted_profitability": macro_event_calendar.get("accepted_profitability"), "historical_replay_performed": macro_event_calendar.get("historical_replay_performed"), "event_calendar_implemented": macro_event_calendar.get("event_calendar_implemented"), "source_rows_proof_eligible": macro_event_calendar.get("source_rows_proof_eligible"), "event_count": macro_event_calendar.get("event_count"), "covered_categories": macro_event_calendar.get("covered_categories"), "missing_categories": macro_event_calendar.get("missing_categories"), "blockers": macro_event_calendar.get("blockers")}, indent=2, sort_keys=True)}

Current point-in-time VIX bucket artifact result, if available:
{json.dumps({"status": point_in_time_vix_bucket.get("status"), "point_in_time_vix_low_mid_bucket_available": point_in_time_vix_bucket.get("point_in_time_vix_low_mid_bucket_available"), "accepted_profitability": point_in_time_vix_bucket.get("accepted_profitability"), "historical_replay_performed": point_in_time_vix_bucket.get("historical_replay_performed"), "source_status": point_in_time_vix_bucket.get("source_status"), "source_rows_count": point_in_time_vix_bucket.get("source_rows_count"), "requested_date_count": point_in_time_vix_bucket.get("requested_date_count"), "covered_date_count": point_in_time_vix_bucket.get("covered_date_count"), "coverage_pct": point_in_time_vix_bucket.get("coverage_pct"), "late_known_at_count": point_in_time_vix_bucket.get("late_known_at_count"), "leakage_reject_count": point_in_time_vix_bucket.get("leakage_reject_count"), "bucket_threshold_source": point_in_time_vix_bucket.get("bucket_threshold_source"), "blockers": point_in_time_vix_bucket.get("blockers")}, indent=2, sort_keys=True)}

Current macro-event long straddle/strangle replay readiness result, if available:
{json.dumps({"status": macro_event_long_strangle_readiness.get("status"), "concept_id": macro_event_long_strangle_readiness.get("concept_id"), "accepted_profitability": macro_event_long_strangle_readiness.get("accepted_profitability"), "historical_replay_performed": macro_event_long_strangle_readiness.get("historical_replay_performed"), "lane_implementation_performed": macro_event_long_strangle_readiness.get("lane_implementation_performed"), "blockers": macro_event_long_strangle_readiness.get("blockers"), "smallest_next_blocker_clearing_slice": macro_event_long_strangle_readiness.get("smallest_next_blocker_clearing_slice"), "allowed_next_step": macro_event_long_strangle_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current 13-symbol candidate-generation surface audit result, if available:
{json.dumps({"status": candidate_generation_13_symbol_surface_audit.get("status"), "accepted_profitability": candidate_generation_13_symbol_surface_audit.get("accepted_profitability"), "historical_rows_are_forward_proof": candidate_generation_13_symbol_surface_audit.get("historical_rows_are_forward_proof"), "quote_vs_candidate_generation": candidate_generation_13_symbol_surface_audit.get("quote_history_vs_candidate_generation"), "candidate_surface": {"frozen_universe_exact_13_symbols": _as_dict(candidate_generation_13_symbol_surface_audit.get("candidate_generation_surface")).get("frozen_universe_exact_13_symbols"), "non_13_symbol_selected_row_count": _as_dict(candidate_generation_13_symbol_surface_audit.get("candidate_generation_surface")).get("non_13_symbol_selected_row_count"), "outside_allowed_universe": _as_dict(candidate_generation_13_symbol_surface_audit.get("candidate_generation_surface")).get("outside_allowed_universe")}, "runner_support": candidate_generation_13_symbol_surface_audit.get("runner_support"), "cvx_scope": candidate_generation_13_symbol_surface_audit.get("cvx_scope"), "blockers": candidate_generation_13_symbol_surface_audit.get("blockers")}, indent=2, sort_keys=True)}

Current frozen 13-symbol reusable candidate-generation entrypoint result, if available:
{json.dumps({"status": candidate_generation_13_symbol_frozen_entrypoint.get("status"), "accepted_profitability": candidate_generation_13_symbol_frozen_entrypoint.get("accepted_profitability"), "historical_rows_are_forward_proof": candidate_generation_13_symbol_frozen_entrypoint.get("historical_rows_are_forward_proof"), "read_only": candidate_generation_13_symbol_frozen_entrypoint.get("read_only"), "no_write": candidate_generation_13_symbol_frozen_entrypoint.get("no_write"), "daily_candidate_generation_row_count": candidate_generation_13_symbol_frozen_entrypoint.get("daily_candidate_generation_row_count"), "selected_candidate_row_count": candidate_generation_13_symbol_frozen_entrypoint.get("selected_candidate_row_count"), "coverage": candidate_generation_13_symbol_frozen_entrypoint.get("coverage"), "daily_status_counts": candidate_generation_13_symbol_frozen_entrypoint.get("daily_status_counts"), "blockers": candidate_generation_13_symbol_frozen_entrypoint.get("blockers")}, indent=2, sort_keys=True)}

Current 13-symbol frozen candidate-generation source-surface materializer result, if available:
{json.dumps({"status": candidate_generation_13_symbol_frozen_source_surface.get("status"), "accepted_profitability": candidate_generation_13_symbol_frozen_source_surface.get("accepted_profitability"), "historical_rows_are_forward_proof": candidate_generation_13_symbol_frozen_source_surface.get("historical_rows_are_forward_proof"), "read_only": candidate_generation_13_symbol_frozen_source_surface.get("read_only"), "no_write": candidate_generation_13_symbol_frozen_source_surface.get("no_write"), "posthoc_filtering_allowed_as_proof": candidate_generation_13_symbol_frozen_source_surface.get("posthoc_filtering_allowed_as_proof"), "source_artifact_universe_exact_13_symbols": candidate_generation_13_symbol_frozen_source_surface.get("source_artifact_universe_exact_13_symbols"), "calendar_coverage": candidate_generation_13_symbol_frozen_source_surface.get("calendar_coverage"), "selected_trade_summary": candidate_generation_13_symbol_frozen_source_surface.get("selected_trade_summary"), "blockers": candidate_generation_13_symbol_frozen_source_surface.get("blockers")}, indent=2, sort_keys=True)}

Current frozen 13-symbol candidate-generation engine result, if available:
{json.dumps({"status": candidate_generation_13_symbol_frozen_engine.get("status"), "decision": candidate_generation_13_symbol_frozen_engine.get("decision"), "accepted_profitability": candidate_generation_13_symbol_frozen_engine.get("accepted_profitability"), "read_only": candidate_generation_13_symbol_frozen_engine.get("read_only"), "no_write": candidate_generation_13_symbol_frozen_engine.get("no_write"), "daily_candidate_generation_row_count": candidate_generation_13_symbol_frozen_engine.get("daily_candidate_generation_row_count"), "selected_candidate_row_count": candidate_generation_13_symbol_frozen_engine.get("selected_candidate_row_count"), "coverage": candidate_generation_13_symbol_frozen_engine.get("coverage"), "reusable_entrypoint_discovery": candidate_generation_13_symbol_frozen_engine.get("reusable_entrypoint_discovery"), "audit_consumed_generated_surface": candidate_generation_13_symbol_frozen_engine.get("audit_consumed_generated_surface"), "historical_simulated_forward_audit_command": candidate_generation_13_symbol_frozen_engine.get("historical_simulated_forward_audit_command"), "blockers": candidate_generation_13_symbol_frozen_engine.get("blockers"), "legacy_blocker_aliases": ["missing_frozen_13_symbol_candidate_generation_engine"] if candidate_generation_13_symbol_frozen_engine.get("status") == "blocked_frozen_13_symbol_candidate_generation_engine" else []}, indent=2, sort_keys=True)}

Interpretation: the reusable frozen entrypoint now exists, but the real latest readback still has 0/24 covered candidate-generation months and 0 selected candidates because every daily row is blocked by missing daily candidate-generation diagnostics. Do not repeat the 13-symbol source-surface/no-write/denominator/engine branch unless a real daily frozen candidate-generation source changes this blocker. Treat quote depth alone as insufficient. Choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current preregistered post-event IV-crush iron-condor playbook result, if available:
{json.dumps({"status": post_event_iv_crush_iron_condor_playbook.get("status"), "concept_id": post_event_iv_crush_iron_condor_playbook.get("concept_id"), "structure": post_event_iv_crush_iron_condor_playbook.get("structure"), "accepted_profitability": post_event_iv_crush_iron_condor_playbook.get("accepted_profitability"), "historical_replay_performed": post_event_iv_crush_iron_condor_playbook.get("historical_replay_performed"), "lane_implementation_performed": post_event_iv_crush_iron_condor_playbook.get("lane_implementation_performed"), "event_calendar_implemented_in_this_slice": post_event_iv_crush_iron_condor_playbook.get("event_calendar_implemented_in_this_slice"), "allowed_next_step": post_event_iv_crush_iron_condor_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered flow-extreme ratio/backspread playbook result, if available:
{json.dumps({"status": flow_extreme_ratio_backspread_playbook.get("status"), "concept_id": flow_extreme_ratio_backspread_playbook.get("concept_id"), "structure": flow_extreme_ratio_backspread_playbook.get("structure"), "accepted_profitability": flow_extreme_ratio_backspread_playbook.get("accepted_profitability"), "historical_replay_performed": flow_extreme_ratio_backspread_playbook.get("historical_replay_performed"), "lane_implementation_performed": flow_extreme_ratio_backspread_playbook.get("lane_implementation_performed"), "undefined_risk_allowed": flow_extreme_ratio_backspread_playbook.get("undefined_risk_allowed"), "allowed_next_step": flow_extreme_ratio_backspread_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current flow-extreme volume/open-interest source-row generator result, if available:
{json.dumps({"status": flow_extreme_volume_oi_source_rows.get("status"), "source_row_count": flow_extreme_volume_oi_source_rows.get("source_row_count"), "write_source_rows_allowed": flow_extreme_volume_oi_source_rows.get("write_source_rows_allowed"), "aggregate_source_summary": flow_extreme_volume_oi_source_rows.get("aggregate_source_summary"), "coverage": flow_extreme_volume_oi_source_rows.get("coverage"), "blockers": flow_extreme_volume_oi_source_rows.get("blockers"), "threshold_policy": flow_extreme_volume_oi_source_rows.get("threshold_policy"), "accepted_profitability": flow_extreme_volume_oi_source_rows.get("accepted_profitability"), "historical_rows_are_forward_proof": flow_extreme_volume_oi_source_rows.get("historical_rows_are_forward_proof"), "quotes_imported": flow_extreme_volume_oi_source_rows.get("quotes_imported"), "evidence_stores_mutated": flow_extreme_volume_oi_source_rows.get("evidence_stores_mutated")}, indent=2, sort_keys=True)}

Current point-in-time flow-extreme input materializer result, if available:
{json.dumps({"status": point_in_time_flow_extreme_input.get("status"), "accepted_profitability": point_in_time_flow_extreme_input.get("accepted_profitability"), "historical_rows_are_forward_proof": point_in_time_flow_extreme_input.get("historical_rows_are_forward_proof"), "read_only": point_in_time_flow_extreme_input.get("read_only"), "no_write": point_in_time_flow_extreme_input.get("no_write"), "coverage": point_in_time_flow_extreme_input.get("coverage"), "source_inventory": point_in_time_flow_extreme_input.get("source_inventory"), "proxy_basis": point_in_time_flow_extreme_input.get("proxy_basis"), "blockers": point_in_time_flow_extreme_input.get("blockers")}, indent=2, sort_keys=True)}

Current multi-leg side-aware pricing capability result, if available:
{json.dumps({"status": multi_leg_side_aware_pricing_capability.get("status"), "accepted_profitability": multi_leg_side_aware_pricing_capability.get("accepted_profitability"), "historical_rows_are_forward_proof": multi_leg_side_aware_pricing_capability.get("historical_rows_are_forward_proof"), "fixture_source_not_proof_eligible": multi_leg_side_aware_pricing_capability.get("fixture_source_not_proof_eligible"), "source_inventory": multi_leg_side_aware_pricing_capability.get("source_inventory"), "structure_support": multi_leg_side_aware_pricing_capability.get("structure_support"), "quote_resolution_counts": multi_leg_side_aware_pricing_capability.get("quote_resolution_counts"), "pricing_capability_blockers": multi_leg_side_aware_pricing_capability.get("pricing_capability_blockers")}, indent=2, sort_keys=True)}

Current base clean stack row-level identity ledger result, if available:
{json.dumps({"status": base_clean_stack_identity_ledger.get("status"), "expected_base_clean_stack_exact_rows": base_clean_stack_identity_ledger.get("expected_base_clean_stack_exact_rows"), "ledger_row_count": base_clean_stack_identity_ledger.get("ledger_row_count"), "unique_identity_count": base_clean_stack_identity_ledger.get("unique_identity_count"), "duplicate_identity_count": base_clean_stack_identity_ledger.get("duplicate_identity_count"), "missing_identity_field_row_count": base_clean_stack_identity_ledger.get("missing_identity_field_row_count"), "future_or_outcome_field_dependency_count": base_clean_stack_identity_ledger.get("future_or_outcome_field_dependency_count"), "protected_holdout_overlap_count": base_clean_stack_identity_ledger.get("protected_holdout_overlap_count"), "accepted_profitability": base_clean_stack_identity_ledger.get("accepted_profitability"), "proof_row_count": base_clean_stack_identity_ledger.get("proof_row_count"), "historical_rows_are_forward_proof": base_clean_stack_identity_ledger.get("historical_rows_are_forward_proof"), "blockers": base_clean_stack_identity_ledger.get("blockers")}, indent=2, sort_keys=True)}

Current flow-extreme denominator/dedupe bridge result, if available:
{json.dumps({"status": flow_extreme_denominator_dedupe_bridge.get("status"), "concept_id": flow_extreme_denominator_dedupe_bridge.get("concept_id"), "structure": flow_extreme_denominator_dedupe_bridge.get("structure"), "accepted_profitability": flow_extreme_denominator_dedupe_bridge.get("accepted_profitability"), "proof_row_count": flow_extreme_denominator_dedupe_bridge.get("proof_row_count"), "historical_rows_are_forward_proof": flow_extreme_denominator_dedupe_bridge.get("historical_rows_are_forward_proof"), "fixture_source_not_proof_eligible": flow_extreme_denominator_dedupe_bridge.get("fixture_source_not_proof_eligible"), "full_denominator_mapping_status": flow_extreme_denominator_dedupe_bridge.get("full_denominator_mapping_status"), "strict_new_dedupe_status": flow_extreme_denominator_dedupe_bridge.get("strict_new_dedupe_status"), "base_identity_ledger_status": flow_extreme_denominator_dedupe_bridge.get("base_identity_ledger_status"), "base_identity_hash_count": flow_extreme_denominator_dedupe_bridge.get("base_identity_hash_count"), "bridge_blockers": flow_extreme_denominator_dedupe_bridge.get("bridge_blockers"), "identity_fields": flow_extreme_denominator_dedupe_bridge.get("identity_fields"), "denominator_status_contract": flow_extreme_denominator_dedupe_bridge.get("denominator_status_contract")}, indent=2, sort_keys=True)}

Current flow-extreme ratio/backspread replay-readiness result, if available:
{json.dumps({"packet_ingestion": flow_extreme_ratio_backspread_readiness_validation, "status": flow_extreme_ratio_backspread_readiness_validation.get("validated_status"), "raw_status": flow_extreme_ratio_backspread_readiness_validation.get("raw_status"), "concept_id": flow_extreme_ratio_backspread_readiness.get("concept_id"), "structure": flow_extreme_ratio_backspread_readiness.get("structure"), "accepted_profitability": flow_extreme_ratio_backspread_readiness.get("accepted_profitability"), "historical_replay_performed": flow_extreme_ratio_backspread_readiness.get("historical_replay_performed"), "replay_performed": flow_extreme_ratio_backspread_readiness.get("replay_performed"), "lane_implementation_performed": flow_extreme_ratio_backspread_readiness.get("lane_implementation_performed"), "undefined_risk_allowed": flow_extreme_ratio_backspread_readiness.get("undefined_risk_allowed"), "blockers": flow_extreme_ratio_backspread_readiness.get("blockers"), "smallest_next_blocker_clearing_slice": flow_extreme_ratio_backspread_readiness.get("smallest_next_blocker_clearing_slice"), "allowed_next_step": flow_extreme_ratio_backspread_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered dispersion-proxy hybrid playbook result, if available:
{json.dumps({"status": dispersion_proxy_hybrid_playbook.get("status"), "concept_id": dispersion_proxy_hybrid_playbook.get("concept_id"), "structure": dispersion_proxy_hybrid_playbook.get("structure"), "accepted_profitability": dispersion_proxy_hybrid_playbook.get("accepted_profitability"), "historical_replay_performed": dispersion_proxy_hybrid_playbook.get("historical_replay_performed"), "lane_implementation_performed": dispersion_proxy_hybrid_playbook.get("lane_implementation_performed"), "undefined_or_uncapped_pair_risk_allowed": dispersion_proxy_hybrid_playbook.get("undefined_or_uncapped_pair_risk_allowed"), "allowed_next_step": dispersion_proxy_hybrid_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current point-in-time dispersion/concentration proxy materializer result, if available:
{json.dumps({"status": point_in_time_dispersion_proxy.get("status"), "accepted_profitability": point_in_time_dispersion_proxy.get("accepted_profitability"), "historical_rows_are_forward_proof": point_in_time_dispersion_proxy.get("historical_rows_are_forward_proof"), "read_only": point_in_time_dispersion_proxy.get("read_only"), "no_write": point_in_time_dispersion_proxy.get("no_write"), "coverage": point_in_time_dispersion_proxy.get("coverage"), "source_inventory": point_in_time_dispersion_proxy.get("source_inventory"), "blockers": point_in_time_dispersion_proxy.get("blockers")}, indent=2, sort_keys=True)}

Current dispersion-proxy hybrid replay-readiness result, if available:
{json.dumps({"status": dispersion_proxy_hybrid_readiness.get("status"), "concept_id": dispersion_proxy_hybrid_readiness.get("concept_id"), "structure": dispersion_proxy_hybrid_readiness.get("structure"), "accepted_profitability": dispersion_proxy_hybrid_readiness.get("accepted_profitability"), "historical_replay_performed": dispersion_proxy_hybrid_readiness.get("historical_replay_performed"), "replay_performed": dispersion_proxy_hybrid_readiness.get("replay_performed"), "lane_implementation_performed": dispersion_proxy_hybrid_readiness.get("lane_implementation_performed"), "blockers": dispersion_proxy_hybrid_readiness.get("blockers"), "smallest_next_blocker_clearing_slice": dispersion_proxy_hybrid_readiness.get("smallest_next_blocker_clearing_slice"), "allowed_next_step": dispersion_proxy_hybrid_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current preregistered PMCC diagonal playbook result, if available:
{json.dumps({"status": pmcc_diagonal_playbook.get("status"), "concept_id": pmcc_diagonal_playbook.get("concept_id"), "structure": pmcc_diagonal_playbook.get("structure"), "accepted_profitability": pmcc_diagonal_playbook.get("accepted_profitability"), "historical_replay_performed": pmcc_diagonal_playbook.get("historical_replay_performed"), "lane_implementation_performed": pmcc_diagonal_playbook.get("lane_implementation_performed"), "undefined_or_uncapped_short_call_risk_allowed": pmcc_diagonal_playbook.get("undefined_or_uncapped_short_call_risk_allowed"), "allowed_next_step": pmcc_diagonal_playbook.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current PMCC diagonal replay-readiness result, if available:
{json.dumps({"packet_ingestion": pmcc_diagonal_readiness_validation, "status": pmcc_diagonal_readiness_validation.get("validated_status"), "raw_status": pmcc_diagonal_readiness_validation.get("raw_status"), "concept_id": pmcc_diagonal_readiness.get("concept_id"), "structure": pmcc_diagonal_readiness.get("structure"), "accepted_profitability": pmcc_diagonal_readiness.get("accepted_profitability"), "historical_replay_performed": pmcc_diagonal_readiness.get("historical_replay_performed"), "replay_performed": pmcc_diagonal_readiness.get("replay_performed"), "lane_implementation_performed": pmcc_diagonal_readiness.get("lane_implementation_performed"), "undefined_or_uncapped_short_call_risk_allowed": pmcc_diagonal_readiness.get("undefined_or_uncapped_short_call_risk_allowed"), "blockers": pmcc_diagonal_readiness.get("blockers"), "smallest_next_blocker_clearing_slice": pmcc_diagonal_readiness.get("smallest_next_blocker_clearing_slice"), "allowed_next_step": pmcc_diagonal_readiness.get("allowed_next_step")}, indent=2, sort_keys=True)}

Current approved 59-symbol ThetaData OPRA/NBBO source-repair result, if available:
{json.dumps({"status": source_repair_59_symbol.get("status"), "approval_token_valid": source_repair_59_symbol.get("approval_token_valid"), "blockers": source_repair_59_symbol.get("blockers"), "theta_terminal": source_repair_59_symbol.get("theta_terminal"), "shared_trusted_imported_quote_dates": source_repair_59_symbol.get("shared_trusted_imported_quote_dates"), "missing_symbol_date_count": source_repair_59_symbol.get("missing_symbol_date_count"), "import_attempted": source_repair_59_symbol.get("import_attempted"), "imported_rows": source_repair_59_symbol.get("imported_rows"), "quotes_imported": source_repair_59_symbol.get("quotes_imported"), "accepted_profitability": source_repair_59_symbol.get("accepted_profitability"), "historical_simulated_forward_status": source_repair_59_symbol.get("historical_simulated_forward_status")}, indent=2, sort_keys=True)}

Interpretation: if the 59-symbol source repair status is blocked_thetaterminal_source_unavailable, do not treat that as an operator-approval blocker or an earned stop. The operator approved non-live/non-broker research continuation. Choose the next meaningful non-live/non-broker branch unless your stop_exception burden of proof is fully satisfied.

Current tokened 59-symbol ThetaData OPRA/NBBO source-repair resume result, if available:
{json.dumps({"status": source_repair_59_symbol_resume.get("status"), "resume_missing_only": source_repair_59_symbol_resume.get("resume_missing_only"), "provider_recheck": source_repair_59_symbol_resume.get("provider_recheck"), "approval_token_valid": source_repair_59_symbol_resume.get("approval_token_valid"), "blockers": source_repair_59_symbol_resume.get("blockers"), "theta_terminal": source_repair_59_symbol_resume.get("theta_terminal"), "shared_trusted_imported_quote_dates": source_repair_59_symbol_resume.get("shared_trusted_imported_quote_dates"), "post_import_shared_trusted_imported_quote_dates": source_repair_59_symbol_resume.get("post_import_shared_trusted_imported_quote_dates"), "missing_symbol_date_count": source_repair_59_symbol_resume.get("missing_symbol_date_count"), "import_attempted": source_repair_59_symbol_resume.get("import_attempted"), "imported_rows": source_repair_59_symbol_resume.get("imported_rows"), "quotes_imported": source_repair_59_symbol_resume.get("quotes_imported"), "protected_holdout_overlap_rows": source_repair_59_symbol_resume.get("protected_holdout_overlap_rows"), "outside_universe_import_rows": source_repair_59_symbol_resume.get("outside_universe_import_rows"), "split_audit_gate": source_repair_59_symbol_resume.get("split_audit_gate")}, indent=2, sort_keys=True)}

Interpretation: if the tokened 59-symbol resume status is blocked_thetaterminal_source_unavailable_retry, do not select another 59-symbol ThetaTerminal retry until provider/source availability changes. The retry already proved token approval, exact universe, no protected-holdout overlap, no outside-universe import, no import attempted, and no coverage improvement under current provider state. Choose the next meaningful non-live/non-broker source family or causal branch unless your stop_exception burden of proof is fully satisfied.

Current direct point-in-time VIX source state:
{json.dumps({"source_import": {"status": direct_vix_source_import.get("status"), "source_family": direct_vix_source_import.get("source_family"), "source_row_count": direct_vix_source_import.get("source_row_count"), "source_rows_written": direct_vix_source_import.get("source_rows_written"), "source_rows_path": direct_vix_source_import.get("source_rows_path"), "threshold_policy_path": direct_vix_source_import.get("threshold_policy_path"), "downstream_vix_bucket_status": direct_vix_source_import.get("downstream_vix_bucket_status"), "downstream_vix_coverage_pct": direct_vix_source_import.get("downstream_vix_coverage_pct"), "quotes_imported": direct_vix_source_import.get("quotes_imported"), "evidence_stores_mutated": direct_vix_source_import.get("evidence_stores_mutated"), "protected_holdout_consumed": direct_vix_source_import.get("protected_holdout_consumed"), "accepted_profitability": direct_vix_source_import.get("accepted_profitability")}, "vix_bucket": {"status": point_in_time_vix_bucket.get("status"), "source_rows_count": point_in_time_vix_bucket.get("source_rows_count"), "coverage_pct": point_in_time_vix_bucket.get("coverage_pct"), "covered_date_count": point_in_time_vix_bucket.get("covered_date_count"), "requested_date_count": point_in_time_vix_bucket.get("requested_date_count"), "late_known_at_count": point_in_time_vix_bucket.get("late_known_at_count"), "leakage_reject_count": point_in_time_vix_bucket.get("leakage_reject_count"), "bucket_threshold_source": point_in_time_vix_bucket.get("bucket_threshold_source"), "threshold_policy": point_in_time_vix_bucket.get("threshold_policy") or direct_vix_source_repair_packet.get("bucket_policy"), "blockers": point_in_time_vix_bucket.get("blockers")}, "legacy_source_repair_packet_status": direct_vix_source_repair_packet.get("status"), "legacy_future_import_command": direct_vix_source_repair_packet.get("future_import_command"), "legacy_future_import_manifest_template": direct_vix_source_repair_packet.get("future_import_manifest_template"), "current_branch_implications": current_vix_branch_implications}, indent=2, sort_keys=True)}

Interpretation: when the current VIX state shows `direct_vix_source_import_materialized` and `point_in_time_vix_bucket_ready`, the prior operator-supplied official daily VIX CSV has already been materialized; do not select the direct VIX source plan or VIX source import again; do not rerun the same VIX packet. Branches that still name VIX as a blocker must be refreshed or treated as stale with respect to VIX; rank their remaining non-VIX blockers instead.

Current macro-event calendar source repair packet result, if available:
{json.dumps({"status": macro_event_calendar_source_repair_packet.get("status"), "source_family": macro_event_calendar_source_repair_packet.get("source_family"), "blockers": macro_event_calendar_source_repair_packet.get("blockers"), "current_macro_event_source_baseline": {"macro_event_calendar_status": macro_event_calendar_source_repair_packet.get("macro_event_calendar_status"), "event_count": macro_event_calendar_source_repair_packet.get("event_count"), "covered_categories": macro_event_calendar_source_repair_packet.get("covered_categories"), "missing_required_categories": macro_event_calendar_source_repair_packet.get("missing_required_categories"), "current_forward_rows": macro_event_calendar_source_repair_packet.get("current_forward_rows"), "target_forward_rows": macro_event_calendar_source_repair_packet.get("target_forward_rows")}, "known_at_policy": macro_event_calendar_source_repair_packet.get("known_at_policy"), "tradable_after_policy": macro_event_calendar_source_repair_packet.get("tradable_after_policy"), "fixture_validation": macro_event_calendar_source_repair_packet.get("fixture_validation"), "future_import_manifest_template": macro_event_calendar_source_repair_packet.get("future_import_manifest_template"), "future_import_command": macro_event_calendar_source_repair_packet.get("future_import_command"), "downstream_readiness_commands": macro_event_calendar_source_repair_packet.get("downstream_readiness_commands"), "branch_implications": macro_event_calendar_source_repair_packet.get("downstream_branch_implications"), "future_import_command_executed": macro_event_calendar_source_repair_packet.get("future_import_command_executed"), "quotes_imported": macro_event_calendar_source_repair_packet.get("quotes_imported"), "evidence_stores_mutated": macro_event_calendar_source_repair_packet.get("evidence_stores_mutated"), "protected_holdout_consumed": macro_event_calendar_source_repair_packet.get("protected_holdout_consumed"), "accepted_profitability": macro_event_calendar_source_repair_packet.get("accepted_profitability"), "historical_rows_are_forward_proof": macro_event_calendar_source_repair_packet.get("historical_rows_are_forward_proof")}, indent=2, sort_keys=True)}

Interpretation: if the macro-event calendar source repair packet status is macro_event_calendar_source_repair_packet_ready_for_operator_import_decision, do not rerun the same macro-event source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real macro-event source import/materialization still needs the exact tokened source-import slice and an operator-supplied official macro-event calendar CSV. Do not run macro-event or post-event replay until a real point-in-time macro-event source artifact exists. Decide whether the next meaningful slice is that tokened non-live source materialization path, a readiness audit for post-event IV-crush, direct VIX materialization if source is supplied, or another safe fallback.

Current flow-extreme volume/open-interest source repair packet result, if available:
{json.dumps({"status": flow_extreme_source_repair_packet.get("status"), "source_family": flow_extreme_source_repair_packet.get("source_family"), "blockers": flow_extreme_source_repair_packet.get("blockers"), "current_flow_source_baseline": {"point_in_time_flow_extreme_input_status": flow_extreme_source_repair_packet.get("point_in_time_flow_extreme_input_status"), "flow_extreme_volume_oi_source_rows_status": flow_extreme_source_repair_packet.get("flow_extreme_volume_oi_source_rows_status"), "covered_month_count": flow_extreme_source_repair_packet.get("covered_month_count"), "date_coverage_pct": flow_extreme_source_repair_packet.get("date_coverage_pct"), "flow_extreme_ratio_backspread_replay_readiness_status": flow_extreme_source_repair_packet.get("flow_extreme_ratio_backspread_replay_readiness_status"), "current_forward_rows": flow_extreme_source_repair_packet.get("current_forward_rows"), "target_forward_rows": flow_extreme_source_repair_packet.get("target_forward_rows")}, "known_at_policy": flow_extreme_source_repair_packet.get("known_at_policy"), "threshold_policy": flow_extreme_source_repair_packet.get("threshold_policy"), "fixture_validation": flow_extreme_source_repair_packet.get("fixture_validation"), "future_import_manifest_template": flow_extreme_source_repair_packet.get("future_import_manifest_template"), "future_import_command": flow_extreme_source_repair_packet.get("future_import_command"), "downstream_readiness_commands": flow_extreme_source_repair_packet.get("downstream_readiness_commands"), "branch_implications": flow_extreme_source_repair_packet.get("downstream_branch_implications"), "future_import_command_executed": flow_extreme_source_repair_packet.get("future_import_command_executed"), "quotes_imported": flow_extreme_source_repair_packet.get("quotes_imported"), "evidence_stores_mutated": flow_extreme_source_repair_packet.get("evidence_stores_mutated"), "protected_holdout_consumed": flow_extreme_source_repair_packet.get("protected_holdout_consumed"), "accepted_profitability": flow_extreme_source_repair_packet.get("accepted_profitability"), "historical_rows_are_forward_proof": flow_extreme_source_repair_packet.get("historical_rows_are_forward_proof")}, indent=2, sort_keys=True)}

Interpretation: if the flow-extreme source repair packet status is flow_extreme_source_repair_packet_ready_for_operator_import_decision, do not rerun the same flow-source packet. The operator has provided standing yes for non-live/non-broker research/source questions, but any real SPY/QQQ option volume/open-interest source import/materialization still needs the exact tokened source-import slice and an operator-supplied trusted daily volume/OI CSV. Do not run flow-extreme replay until real point-in-time flow source rows exist. VIX is no longer the flow blocker. Decide whether the next meaningful slice is that tokened non-live flow-source materialization path or another safe fallback.

Current goal-loop state:
{json.dumps({"state": goal_loop.get("current_decision_state"), "next_safe_action": goal_loop.get("next_safe_action"), "forward_evidence_accounting": goal_loop.get("forward_evidence_accounting")}, indent=2, sort_keys=True)}

Important instruction:
You are not being asked for generic strategy advice or a casual continue/stop vote. Treat stopping as an exceptional claim. Because strict post-freeze forward proof is currently 0/30, you may recommend stopping only if you can prove that no significant upgrade remains after explicitly considering new lanes, new option structures, historical data-depth repair, and forward collection. Ask up to five operator questions that would materially affect the decision, but do not block on read-only/research-only work; the user has already approved that category. For any live/broker/import/mutation/promotion/proof-bar/holdout action, name the needed approval and select a safe read-only fallback unless no such fallback exists.

Return a concrete loop decision. If a significant upgrade remains, return verdict=continue, continue_loop=true, and exactly one next Codex task with files/artifacts/commands/tests/acceptance criteria. If a branch needs operator approval, ask the exact operator question and explain why it is required. If no significant upgrade remains under current approvals, return verdict=stop_exception, continue_loop=false, and provide the burden-of-proof check that earned that stop.

Do not say "collect more data", "try more strategies", "optimize parameters", or "run more backtests" unless you specify the exact data, lane, option structure, date window, command, and pass/fail threshold.

Before any stop_exception, explicitly evaluate whether there is a falsifiable path through:
1. fresh forward paper-shadow collection,
2. scoped source repair or replay,
3. a new historical data surface or longer-lookback audit,
4. a new causal playbook,
5. new option structures beyond the current directional-spread surface.

New option edge families to consider before stopping:
- volatility risk premium,
- skew mispricing,
- term-structure dislocation,
- earnings or macro event volatility,
- post-event IV crush,
- post-event drift,
- trend or momentum continuation,
- mean reversion,
- dispersion-like proxy behavior,
- liquidity or flow effects.

Option structures to consider before stopping:
- vertical spreads,
- calendars,
- diagonals,
- broken-wing butterflies,
- ratio spreads,
- backspreads,
- straddles,
- strangles,
- iron condors,
- iron butterflies,
- synthetic covered calls or PMCC-style diagonals,
- debit/credit hybrids.

For every proposed lane, provide the frozen rule, eligible universe, inclusion/exclusion rules, leakage controls, required data repairs, minimum sample size, profitability thresholds, and the exact result that would falsify it. A lane should not pass because it has an attractive point backtest; it needs an economic mechanism and a falsifiable audit plan.

Allowed branch families:
1. fresh_forward_paper_shadow_collection - requires operator approval and a valid market-data window if rows will be appended.
2. scoped_source_repair_or_replay - requires operator approval before quote import, evidence mutation, or source repair.
3. new_causal_playbook_generation - read-only preregistration/falsification can continue without live/broker/evidence mutation.
4. new_historical_data_surface_or_longer_lookback - requires operator approval if it changes the data surface.
5. dashboard_or_operator_visibility - only significant if tied to a proof blocker or execution decision.

Forbidden unless explicitly approved later:
- broker orders, live validation, auto-track, scanner release, stop/sizing changes, proof-bar relaxation, quote import, evidence DB mutation, protected holdout consumption, promotion.

Required JSON-like output shape:
{json.dumps(GPT_OUTPUT_SCHEMA, indent=2, sort_keys=True)}

Relevant NEXT_STEPS excerpt:
{next_steps_excerpt}

Relevant DECISIONS excerpt:
{decisions_excerpt}

Relevant PROJECT_CONTEXT excerpt:
{context_excerpt}
"""


def render_markdown(packet: dict[str, Any]) -> str:
    current = _as_dict(packet.get("current_evidence_summary"))
    frontier = _as_dict(current.get("frontier"))
    lines = [
        "# Options Oracle Profit Loop Packet",
        "",
        "This artifact is the reusable same-session GPT-5.5 Pro handoff for the regular-options profitability loop.",
        "",
        "## Status",
        "",
        f"- Status: `{packet.get('status')}`.",
        f"- Frontier status: `{frontier.get('status')}`.",
        f"- Countable throughput candidate found: `{frontier.get('countable_throughput_candidate_found')}`.",
        f"- Raw count candidates: `{frontier.get('raw_count_candidate_count')}`.",
        f"- Decision counts: `{json.dumps(frontier.get('decision_counts'), sort_keys=True)}`.",
        "",
        "## Continuation Branches",
        "",
    ]
    for branch in packet["continuation_branches"]:
        lines.append(
            f"- `{branch['branch_id']}`: requires approval `{str(branch['requires_operator_approval']).lower()}`; {branch['why']}"
        )
    lines.extend(["", "## Prompt", "", "```text", packet["prompt"], "```", ""])
    return "\n".join(lines)


def write_outputs(
    packet: dict[str, Any],
    *,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_md: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"json": _rel(output_json), "markdown": _rel(output_md)}
    packet_with_artifacts = dict(packet)
    packet_with_artifacts["artifacts"] = artifacts
    output_json.write_text(json.dumps(packet_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    output_md.write_text(render_markdown(packet_with_artifacts), encoding="utf8")
    packet["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a same-session GPT-5.5 Pro profitability loop packet.")
    parser.add_argument("--frontier", type=Path, default=DEFAULT_FRONTIER)
    parser.add_argument("--momentum-edge", type=Path, default=DEFAULT_MOMENTUM_EDGE)
    parser.add_argument("--causal-falsification", type=Path, default=DEFAULT_CAUSAL_FALSIFICATION)
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--momentum-continuation-replay", type=Path, default=DEFAULT_MOMENTUM_CONTINUATION_REPLAY)
    parser.add_argument("--momentum-continuation-proof-resolution", type=Path, default=DEFAULT_MOMENTUM_CONTINUATION_PROOF_RESOLUTION)
    parser.add_argument("--momentum-continuation-bounded-replay", type=Path, default=DEFAULT_MOMENTUM_CONTINUATION_BOUNDED_REPLAY)
    parser.add_argument("--preregistered-vrp-playbook", type=Path, default=DEFAULT_PREREGISTERED_VRP_PLAYBOOK)
    parser.add_argument("--vrp-replay-readiness", type=Path, default=DEFAULT_VRP_REPLAY_READINESS)
    parser.add_argument("--preregistered-term-structure-playbook", type=Path, default=DEFAULT_TERM_STRUCTURE_PLAYBOOK)
    parser.add_argument("--term-structure-replay-readiness", type=Path, default=DEFAULT_TERM_STRUCTURE_REPLAY_READINESS)
    parser.add_argument("--preregistered-skew-broken-wing-playbook", type=Path, default=DEFAULT_PREREGISTERED_SKEW_BROKEN_WING_PLAYBOOK)
    parser.add_argument("--preregistered-macro-event-long-strangle-playbook", type=Path, default=DEFAULT_PREREGISTERED_MACRO_EVENT_LONG_STRANGLE_PLAYBOOK)
    parser.add_argument("--macro-event-calendar", type=Path, default=DEFAULT_MACRO_EVENT_CALENDAR)
    parser.add_argument("--point-in-time-vix-bucket", type=Path, default=DEFAULT_POINT_IN_TIME_VIX_BUCKET)
    parser.add_argument("--macro-event-long-strangle-replay-readiness", type=Path, default=DEFAULT_MACRO_EVENT_LONG_STRANGLE_REPLAY_READINESS)
    parser.add_argument("--candidate-generation-13-symbol-surface-audit", type=Path, default=DEFAULT_13_SYMBOL_CANDIDATE_GENERATION_SURFACE_AUDIT)
    parser.add_argument("--candidate-generation-13-symbol-frozen-source-surface", type=Path, default=DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_SOURCE_SURFACE)
    parser.add_argument("--candidate-generation-13-symbol-frozen-entrypoint", type=Path, default=DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENTRYPOINT)
    parser.add_argument("--candidate-generation-13-symbol-frozen-engine", type=Path, default=DEFAULT_13_SYMBOL_FROZEN_CANDIDATE_GENERATION_ENGINE)
    parser.add_argument("--preregistered-post-event-iv-crush-iron-condor-playbook", type=Path, default=DEFAULT_PREREGISTERED_POST_EVENT_IV_CRUSH_IRON_CONDOR_PLAYBOOK)
    parser.add_argument("--preregistered-flow-extreme-ratio-backspread-playbook", type=Path, default=DEFAULT_PREREGISTERED_FLOW_EXTREME_RATIO_BACKSPREAD_PLAYBOOK)
    parser.add_argument("--flow-extreme-volume-oi-source-rows", type=Path, default=DEFAULT_FLOW_EXTREME_VOLUME_OI_SOURCE_ROWS)
    parser.add_argument("--point-in-time-flow-extreme-input", type=Path, default=DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT)
    parser.add_argument("--multi-leg-side-aware-pricing-capability", type=Path, default=DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY)
    parser.add_argument("--base-clean-stack-identity-ledger", type=Path, default=DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER)
    parser.add_argument("--flow-extreme-denominator-dedupe-bridge", type=Path, default=DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE)
    parser.add_argument("--flow-extreme-ratio-backspread-replay-readiness", type=Path, default=DEFAULT_FLOW_EXTREME_RATIO_BACKSPREAD_REPLAY_READINESS)
    parser.add_argument("--preregistered-dispersion-proxy-hybrid-playbook", type=Path, default=DEFAULT_PREREGISTERED_DISPERSION_PROXY_HYBRID_PLAYBOOK)
    parser.add_argument("--point-in-time-dispersion-concentration-proxy", type=Path, default=DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY)
    parser.add_argument("--dispersion-proxy-hybrid-replay-readiness", type=Path, default=DEFAULT_DISPERSION_PROXY_HYBRID_REPLAY_READINESS)
    parser.add_argument("--preregistered-pmcc-diagonal-playbook", type=Path, default=DEFAULT_PREREGISTERED_PMCC_DIAGONAL_PLAYBOOK)
    parser.add_argument("--pmcc-diagonal-replay-readiness", type=Path, default=DEFAULT_PMCC_DIAGONAL_REPLAY_READINESS)
    parser.add_argument("--source-repair-59-symbol", type=Path, default=DEFAULT_59_SYMBOL_SOURCE_REPAIR)
    parser.add_argument("--source-repair-59-symbol-resume", type=Path, default=DEFAULT_59_SYMBOL_SOURCE_REPAIR_RESUME)
    parser.add_argument("--direct-vix-source-import", type=Path, default=DEFAULT_DIRECT_VIX_SOURCE_IMPORT)
    parser.add_argument("--direct-vix-source-repair-packet", type=Path, default=DEFAULT_DIRECT_VIX_SOURCE_REPAIR_PACKET)
    parser.add_argument("--macro-event-calendar-source-repair-packet", type=Path, default=DEFAULT_MACRO_EVENT_CALENDAR_SOURCE_REPAIR_PACKET)
    parser.add_argument("--flow-extreme-source-repair-packet", type=Path, default=DEFAULT_FLOW_EXTREME_SOURCE_REPAIR_PACKET)
    parser.add_argument("--goal-loop", type=Path, default=DEFAULT_GOAL_LOOP)
    parser.add_argument("--next-steps", type=Path, default=DEFAULT_NEXT_STEPS)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--project-context", type=Path, default=DEFAULT_PROJECT_CONTEXT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    packet = build_packet(
        frontier_path=args.frontier,
        momentum_edge_path=args.momentum_edge,
        causal_falsification_path=args.causal_falsification,
        preregistered_playbook_path=args.preregistered_playbook,
        momentum_continuation_replay_path=args.momentum_continuation_replay,
        momentum_continuation_proof_resolution_path=args.momentum_continuation_proof_resolution,
        momentum_continuation_bounded_replay_path=args.momentum_continuation_bounded_replay,
        preregistered_vrp_playbook_path=args.preregistered_vrp_playbook,
        vrp_replay_readiness_path=args.vrp_replay_readiness,
        preregistered_term_structure_playbook_path=args.preregistered_term_structure_playbook,
        term_structure_replay_readiness_path=args.term_structure_replay_readiness,
        preregistered_skew_broken_wing_playbook_path=args.preregistered_skew_broken_wing_playbook,
        preregistered_macro_event_long_strangle_playbook_path=args.preregistered_macro_event_long_strangle_playbook,
        macro_event_calendar_path=args.macro_event_calendar,
        point_in_time_vix_bucket_path=args.point_in_time_vix_bucket,
        macro_event_long_strangle_replay_readiness_path=args.macro_event_long_strangle_replay_readiness,
        candidate_generation_13_symbol_surface_audit_path=args.candidate_generation_13_symbol_surface_audit,
        candidate_generation_13_symbol_frozen_source_surface_path=args.candidate_generation_13_symbol_frozen_source_surface,
        candidate_generation_13_symbol_frozen_entrypoint_path=args.candidate_generation_13_symbol_frozen_entrypoint,
        candidate_generation_13_symbol_frozen_engine_path=args.candidate_generation_13_symbol_frozen_engine,
        preregistered_post_event_iv_crush_iron_condor_playbook_path=args.preregistered_post_event_iv_crush_iron_condor_playbook,
        preregistered_flow_extreme_ratio_backspread_playbook_path=args.preregistered_flow_extreme_ratio_backspread_playbook,
        flow_extreme_volume_oi_source_rows_path=args.flow_extreme_volume_oi_source_rows,
        point_in_time_flow_extreme_input_path=args.point_in_time_flow_extreme_input,
        multi_leg_side_aware_pricing_capability_path=args.multi_leg_side_aware_pricing_capability,
        base_clean_stack_identity_ledger_path=args.base_clean_stack_identity_ledger,
        flow_extreme_denominator_dedupe_bridge_path=args.flow_extreme_denominator_dedupe_bridge,
        flow_extreme_ratio_backspread_replay_readiness_path=args.flow_extreme_ratio_backspread_replay_readiness,
        preregistered_dispersion_proxy_hybrid_playbook_path=args.preregistered_dispersion_proxy_hybrid_playbook,
        point_in_time_dispersion_concentration_proxy_path=args.point_in_time_dispersion_concentration_proxy,
        dispersion_proxy_hybrid_replay_readiness_path=args.dispersion_proxy_hybrid_replay_readiness,
        preregistered_pmcc_diagonal_playbook_path=args.preregistered_pmcc_diagonal_playbook,
        pmcc_diagonal_replay_readiness_path=args.pmcc_diagonal_replay_readiness,
        source_repair_59_symbol_path=args.source_repair_59_symbol,
        source_repair_59_symbol_resume_path=args.source_repair_59_symbol_resume,
        direct_vix_source_import_path=args.direct_vix_source_import,
        direct_vix_source_repair_packet_path=args.direct_vix_source_repair_packet,
        macro_event_calendar_source_repair_packet_path=args.macro_event_calendar_source_repair_packet,
        flow_extreme_source_repair_packet_path=args.flow_extreme_source_repair_packet,
        goal_loop_path=args.goal_loop,
        next_steps_path=args.next_steps,
        decisions_path=args.decisions,
        project_context_path=args.project_context,
    )
    if not args.no_write:
        write_outputs(packet, output_json=args.output_json, output_md=args.output_md)
    if args.json_output:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(packet["status"])
        print(packet["prompt"])
    return 0 if packet["status"] == "ready_for_same_session_gpt55_guidance" else 1


if __name__ == "__main__":
    sys.exit(main())
