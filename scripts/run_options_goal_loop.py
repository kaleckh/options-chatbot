from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report


REPORT_ID = "options_goal_loop"

DEFAULT_POLICY = ROOT / "data" / "contracts" / "options_goal_loop_policy.json"
DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_FORWARD_PROTOCOL_SCHEMA = (
    ROOT / "data" / "contracts" / "phase2-regular-options-forward-paper-shadow-cohort-schema.json"
)
DEFAULT_FORWARD_COHORT_PREREGISTRATION = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"
DEFAULT_FORWARD_COHORT_LOG = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_cohort.jsonl"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_OUTPUT_MD = ROOT / "docs" / "research-decisions" / "options_goal_loop_latest.md"

FROZEN_LANE_ID = "volatility_expansion_observation"
PHASE2_FROZEN_LANE_IDS = ("volatility_expansion_observation", "bullish_pullback_observation")
MAX_ITERATION_HARD_CAP = 5

NON_PROOF_EVIDENCE_CLASSES = {
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
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


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


def _load_json(path: Path, *, required: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "reason_codes": ["missing_readback"],
    }
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta.update({"status": "malformed", "reason_codes": [f"malformed_json:{exc.lineno}:{exc.colno}"]})
        return {}, meta
    except OSError as exc:
        meta.update({"status": "unreadable", "reason_codes": [type(exc).__name__]})
        return {}, meta
    if not isinstance(payload, dict):
        meta.update({"status": "invalid", "reason_codes": ["json_root_not_object"]})
        return {}, meta
    meta.update(
        {
            "status": "loaded",
            "generated_at_utc": payload.get("generated_at_utc") or payload.get("last_updated"),
            "reason_codes": [],
            "report_id": payload.get("report_id") or payload.get("contract_id"),
        }
    )
    return payload, meta


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": False,
        "exists": path.exists(),
        "status": "missing",
        "row_count": 0,
        "malformed_row_count": 0,
        "reason_codes": ["cohort_log_not_created_yet"],
    }
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            malformed += 1
    meta["row_count"] = len(rows)
    meta["malformed_row_count"] = malformed
    meta["status"] = "malformed" if malformed else "loaded"
    meta["reason_codes"] = ["malformed_jsonl_rows_present"] if malformed else []
    return rows, meta


def _value_from_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _policy_gate(policy: dict[str, Any], key: str, default: Any) -> Any:
    return _as_dict(policy.get("proof_gates")).get(key, default)


def _policy_allowed_lanes(policy: dict[str, Any]) -> tuple[str, ...]:
    lanes = tuple(_norm(lane_id) for lane_id in _as_list(policy.get("allowed_lanes")) if _norm(lane_id))
    return lanes or PHASE2_FROZEN_LANE_IDS


def command_allowed(command: str, policy: dict[str, Any]) -> tuple[bool, list[str]]:
    normalized = " ".join(command.split())
    allowed = {" ".join(str(item).split()) for item in _as_list(policy.get("allowed_read_only_commands"))}
    reasons: list[str] = []
    if normalized not in allowed:
        reasons.append("command_not_exactly_allowlisted")
    lower = normalized.lower()
    for denied in _as_list(policy.get("denied_command_substrings")):
        if str(denied).lower() in lower:
            reasons.append(f"denied_substring:{denied}")
    if "hypothesis-tournament" in lower and "--no-write" not in lower:
        reasons.append("broad_hypothesis_tournament_without_no_write")
    if "--max-variants" in lower:
        parts = lower.split()
        for index, part in enumerate(parts):
            if part == "--max-variants" and index + 1 < len(parts) and _safe_int(parts[index + 1]) > 100:
                reasons.append("variant_budget_expansion_denied")
    return not reasons, reasons


def _completed_value(row: dict[str, Any]) -> float | None:
    entry = _norm_lower(row.get("entry_evidence_status")) in {"exact_entry_captured", "exact_entry"} or bool(
        row.get("exact_entry_captured")
    )
    exit_ = _norm_lower(row.get("exit_evidence_status")) in {"exact_exit_captured", "exact_exit"} or bool(
        row.get("exact_exit_captured")
    )
    if not (entry and exit_):
        return None
    status = _norm_lower(row.get("denominator_status"))
    if status in {"lookahead_only", "lookahead_only_diagnostic"}:
        return None
    evidence_classes = {
        _norm_lower(row.get("quote_evidence_class")),
        _norm_lower(row.get("entry_evidence_class")),
        _norm_lower(row.get("exit_evidence_class")),
        _norm_lower(row.get("entry_quote_source")),
        _norm_lower(row.get("exit_quote_source")),
    }
    if evidence_classes & NON_PROOF_EVIDENCE_CLASSES:
        return None
    for key in ("net_pnl_usd", "realized_net_pnl_usd"):
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not gains and not losses:
        return None
    if losses == 0:
        return None
    return round(gains / losses, 4)


def _cohort_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strict_values = [value for row in rows if (value := _completed_value(row)) is not None]
    zero_bid_rows = [
        row
        for row in rows
        if _norm_lower(row.get("denominator_status")) == "zero_bid_untradable"
        or "zero_bid" in json.dumps(row, sort_keys=True, default=str).lower()
    ]
    lookahead_rows = [row for row in rows if "lookahead" in json.dumps(row, sort_keys=True, default=str).lower()]
    non_proof_rows = []
    for row in rows:
        evidence_values = {
            _norm_lower(row.get("quote_evidence_class")),
            _norm_lower(row.get("entry_evidence_class")),
            _norm_lower(row.get("exit_evidence_class")),
            _norm_lower(row.get("entry_quote_source")),
            _norm_lower(row.get("exit_quote_source")),
            _norm_lower(row.get("denominator_status")),
        }
        if evidence_values & NON_PROOF_EVIDENCE_CLASSES:
            non_proof_rows.append(row)
    return {
        "total_rows": len(rows),
        "strict_exact_completed_forward_rows": len(strict_values),
        "strict_exact_realized_forward_pf": _profit_factor(strict_values),
        "zero_bid_untradable_rows": len(zero_bid_rows),
        "lookahead_only_rows": len(lookahead_rows),
        "non_proof_mark_rows": len(non_proof_rows),
        "zero_bid_is_execution_failure": bool(zero_bid_rows),
        "lookahead_only_is_diagnostic": bool(lookahead_rows),
        "non_executable_marks_not_counted_as_proof": bool(non_proof_rows),
    }


def _current_paper_shadow_lane(trade_qualification: dict[str, Any], robust_edge: dict[str, Any]) -> dict[str, Any] | None:
    best = _as_dict(trade_qualification.get("best_current_lane_if_any"))
    if _norm(best.get("lane_id")):
        return best
    candidate = _as_dict(robust_edge.get("best_candidate_if_any"))
    if _norm(candidate.get("lane_id")):
        return {
            "lane_id": candidate.get("lane_id"),
            "decision": candidate.get("decision"),
            "profit_factor": candidate.get("profit_factor"),
        }
    return None


def _promotion_ready_detected(trade_qualification: dict[str, Any], robust_edge: dict[str, Any], forward: dict[str, Any]) -> bool:
    return any(
        [
            bool(trade_qualification.get("promotion_ready")),
            _safe_int(trade_qualification.get("promotion_ready_count")) > 0,
            bool(robust_edge.get("existing_promotion_ready")),
            bool(forward.get("promotion_ready")),
        ]
    )


def _live_flag_violation(*reports: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for name, report in reports:
        for key in ("live_entry_allowed", "auto_track_allowed", "broker_order_allowed"):
            if report.get(key) is True:
                violations.append(f"{name}.{key}=true")
    return violations


def classify_state(
    *,
    policy: dict[str, Any],
    trade_qualification: dict[str, Any],
    robust_edge: dict[str, Any],
    forward: dict[str, Any],
    cohort_audit: dict[str, Any],
    protocol_exists: bool,
) -> dict[str, Any]:
    live_violations = _live_flag_violation(
        ("trade_qualification", trade_qualification),
        ("robust_edge", robust_edge),
        ("forward_paper_shadow", forward),
    )
    if live_violations:
        return {
            "state": "safety_violation",
            "action": "stop_immediately",
            "recommendation": "restore false flags and require human review",
            "reason_codes": live_violations,
        }

    completed = _safe_int(cohort_audit.get("strict_exact_completed_forward_rows"))
    stressed_pf_lb = _safe_float(forward.get("stressed_pf_lower_bound"))
    hard_fail_states = set(_as_list(forward.get("hard_fail_states")))
    acceptance = _as_dict(forward.get("acceptance_readiness"))
    minimum_rows = _safe_int(_policy_gate(policy, "minimum_exact_completed_forward_rows", 30))
    acceptance_rows = _safe_int(acceptance.get("post_freeze_strict_exact_completed_rows"))
    acceptance_pf_lb = _safe_float(acceptance.get("bootstrap_pf_lower_bound_5pct_usd"))
    acceptance_ready = (
        acceptance_rows >= minimum_rows
        and bool(acceptance.get("positive_net_usd_pnl"))
        and acceptance_pf_lb is not None
        and acceptance_pf_lb > float(_policy_gate(policy, "minimum_pf_lower_bound_after_stress_gt", 1.0))
        and not hard_fail_states
    )
    concentration_fail = any("concentration" in item or "single_" in item for item in hard_fail_states)
    denominator_fail = any("denominator_leakage" in item for item in hard_fail_states)
    execution_fail = any(
        marker in item
        for item in hard_fail_states
        for marker in ("zero_bid", "stale", "display", "missing_exact", "fill_attempt", "policy_drift", "evidence_drift", "scanner_hash_drift")
    )
    if _promotion_ready_detected(trade_qualification, robust_edge, forward) and not (
        acceptance_ready
    ):
        return {
            "state": "promotion_policy_violation",
            "action": "stop_immediately",
            "recommendation": "preserve promotion_ready=false and require human review",
            "reason_codes": ["promotion_ready_without_strict_forward_gates"],
        }

    lane = _current_paper_shadow_lane(trade_qualification, robust_edge)
    if not lane:
        return {
            "state": "no_candidate",
            "action": "stop_research_search",
            "recommendation": "no promotion, no live, no broad expansion",
            "reason_codes": ["no_current_paper_shadow_lane"],
        }
    allowed_lane_ids = set(_policy_allowed_lanes(policy))
    if _norm(lane.get("lane_id")) not in allowed_lane_ids:
        return {
            "state": "no_candidate",
            "action": "stop_research_search",
            "recommendation": "current lane is outside the allowed frozen goal-loop lanes",
            "reason_codes": [f"unsupported_lane:{lane.get('lane_id')}"],
        }
    if not protocol_exists:
        return {
            "state": "protocol_missing",
            "action": "prepare_forward_denominator_protocol",
            "recommendation": "implement schema/report/tests before collecting more rows",
            "reason_codes": ["forward_denominator_protocol_missing"],
        }

    preferred_rows = _safe_int(_policy_gate(policy, "preferred_exact_completed_forward_rows", 50))
    if acceptance_rows != completed:
        hard_fail_states.add("forward_report_goal_loop_strict_count_mismatch")
    if acceptance_rows < minimum_rows:
        return {
            "state": "underpowered_forward_evidence",
            "action": "continue_paper_shadow_only",
            "recommendation": "collect more full-denominator paper-shadow evidence; no promotion",
            "reason_codes": [f"post_freeze_strict_exact_completed_forward_rows_{acceptance_rows}_below_{minimum_rows}", *sorted(hard_fail_states)],
        }
    if concentration_fail or denominator_fail or execution_fail:
        return {
            "state": "blocked_forward_gate",
            "action": "continue_or_reject_based_on_blocker",
            "recommendation": "no promotion; resolve or reject based on the blocker without changing policy",
            "reason_codes": sorted(hard_fail_states),
        }
    if not acceptance_ready:
        return {
            "state": "failed_forward_gate",
            "action": "reject_current_lane",
            "recommendation": "stop this promotion path unless a new human-approved protocol is opened",
            "reason_codes": ["strict_post_freeze_usd_acceptance_gate_not_passed", *sorted(hard_fail_states)],
        }
    if acceptance_rows >= preferred_rows and acceptance_pf_lb is not None and acceptance_pf_lb >= float(_policy_gate(policy, "healthier_pf_lower_bound_after_stress_gte", 1.2)):
        return {
            "state": "strong_paper_shadow_packet",
            "action": "produce_review_packet",
            "recommendation": "human review for frozen paper validation only; still no live trading",
            "reason_codes": ["preferred_forward_packet_clean"],
        }
    return {
        "state": "eligible_for_frozen_paper_validation_review",
        "action": "produce_review_packet",
        "recommendation": "human review only; still no live trading",
        "reason_codes": ["minimum_forward_packet_clean"],
    }


def _verify_commands(policy: dict[str, Any]) -> list[str]:
    return [
        "npm run options:report:phase2-forward-paper-shadow",
        "uv run --locked python -m unittest tests.test_options_goal_loop tests.test_volatility_expansion_forward_paper_shadow_report tests.test_append_volatility_expansion_forward_paper_shadow_rows -v",
    ]


def run_commands(commands: list[str], policy: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    for command in commands:
        allowed, reasons = command_allowed(command, policy)
        if not allowed:
            denied.append({"command": command, "reason_codes": reasons})
            continue
        row = {"command": command, "allowed": True, "executed": False, "returncode": None}
        if execute:
            command_args = shlex.split(command)
            resolved_executable = shutil.which(command_args[0]) if command_args else None
            if resolved_executable:
                command_args[0] = resolved_executable
            try:
                completed = subprocess.run(command_args, cwd=ROOT, text=True, capture_output=True, check=False)
            except FileNotFoundError as exc:
                row.update(
                    {
                        "executed": True,
                        "returncode": 127,
                        "stdout_tail": "",
                        "stderr_tail": str(exc)[-2000:],
                    }
                )
                results.append(row)
                continue
            row.update(
                {
                    "executed": True,
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                }
            )
        results.append(row)
    return {
        "commands": results,
        "denied_commands": denied,
        "denied_command_or_mutation_attempted": bool(denied),
    }


def _forward_evidence_accounting(
    *,
    cohort_meta: dict[str, Any],
    forward: dict[str, Any],
    acceptance: dict[str, Any],
    minimum_rows: int,
) -> dict[str, Any]:
    counts = _as_dict(forward.get("counts"))
    total_rows = _safe_int(counts.get("total_natural_selections"))
    strict_rows = _safe_int(acceptance.get("post_freeze_strict_exact_completed_rows"))
    strict_reject_counts = _as_dict(forward.get("strict_reject_counts"))
    excluded_rows = sum(_safe_int(value) for value in strict_reject_counts.values())
    log_status = _norm(cohort_meta.get("status")) or "missing"
    if log_status == "missing":
        accounting_state = "log_missing_blocker"
    elif log_status == "malformed":
        accounting_state = "log_malformed_blocker"
    elif total_rows == 0:
        accounting_state = "initialized_empty_zero_of_gate"
    elif strict_rows == 0 and excluded_rows > 0:
        accounting_state = "rows_present_none_strict_excluded"
    elif strict_rows < minimum_rows:
        accounting_state = "strict_rows_under_minimum"
    else:
        accounting_state = "minimum_strict_rows_present_require_pf_and_concentration_gates"
    return {
        "state": accounting_state,
        "cohort_log_status": log_status,
        "cohort_log_path": cohort_meta.get("path"),
        "cohort_log_exists": bool(cohort_meta.get("exists")),
        "cohort_log_row_count": _safe_int(cohort_meta.get("row_count")),
        "cohort_log_malformed_row_count": _safe_int(cohort_meta.get("malformed_row_count")),
        "total_natural_selections": total_rows,
        "post_freeze_strict_exact_completed_rows": strict_rows,
        "minimum_required": minimum_rows,
        "strict_rows_remaining_to_minimum": max(0, minimum_rows - strict_rows),
        "strict_reject_counts": strict_reject_counts,
        "excluded_or_rejected_row_flags": excluded_rows,
        "strict_usd_pf_lower_bound_5pct": acceptance.get("bootstrap_pf_lower_bound_5pct_usd"),
        "promotion_ready": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "cohort_append_performed": False,
    }


def build_report(
    *,
    mode: str = "audit",
    max_iterations: int = 1,
    policy_path: Path = DEFAULT_POLICY,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    forward_protocol_schema_path: Path = DEFAULT_FORWARD_PROTOCOL_SCHEMA,
    forward_cohort_preregistration_path: Path = DEFAULT_FORWARD_COHORT_PREREGISTRATION,
    forward_cohort_log_path: Path = DEFAULT_FORWARD_COHORT_LOG,
    execute_commands: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now()
    policy, policy_meta = _load_json(policy_path)
    if not policy:
        policy = {"iteration_limits": {"hard_cap_max_iterations": MAX_ITERATION_HARD_CAP}}
    hard_cap = min(_safe_int(_as_dict(policy.get("iteration_limits")).get("hard_cap_max_iterations"), MAX_ITERATION_HARD_CAP), MAX_ITERATION_HARD_CAP)
    requested_iterations = max_iterations
    iterations = max(1, min(max_iterations, hard_cap))
    mode_allowed = mode in set(_as_list(policy.get("allowed_modes")) or ["audit", "verify", "prepare-protocol", "report"])
    trade_qualification, trade_meta = _load_json(trade_qualification_path)
    robust_edge, robust_meta = _load_json(robust_edge_path)
    protocol_exists = forward_protocol_schema_path.exists() and (ROOT / "scripts" / "build_volatility_expansion_forward_paper_shadow_report.py").exists()
    forward = forward_report.build_report(
        trade_qualification_path=trade_qualification_path,
        robust_edge_path=robust_edge_path,
        forward_cohort_preregistration_path=forward_cohort_preregistration_path,
        cohort_log_path=forward_cohort_log_path,
        schema_path=forward_protocol_schema_path,
        allowed_lane_ids=_policy_allowed_lanes(policy),
        generated_at_utc=generated_at,
    )
    rows, cohort_meta = _load_jsonl(forward_cohort_log_path)
    cohort_audit = _cohort_audit(rows)
    classification = classify_state(
        policy=policy,
        trade_qualification=trade_qualification,
        robust_edge=robust_edge,
        forward=forward,
        cohort_audit=cohort_audit,
        protocol_exists=protocol_exists,
    )
    command_results = {"commands": [], "denied_commands": [], "denied_command_or_mutation_attempted": False}
    not_run: list[dict[str, str]] = []
    if not mode_allowed:
        command_results["denied_command_or_mutation_attempted"] = True
        command_results["denied_commands"] = [{"command": f"--mode {mode}", "reason_codes": ["mode_not_allowlisted"]}]
    elif mode == "verify" and classification["action"] != "stop_immediately":
        command_results = run_commands(_verify_commands(policy), policy, execute=execute_commands)
    elif mode in {"audit", "report"}:
        not_run.append({"item": "safe read-only command allowlist", "reason": f"{mode} mode only reads artifacts and writes the goal-loop report"})
    elif mode == "prepare-protocol":
        not_run.append({"item": "self-editing protocol preparation", "reason": "protocol files already exist or require a code-review task; this loop does not self-modify"})

    current_lane = _current_paper_shadow_lane(trade_qualification, robust_edge)
    exact_forward_rows = _safe_int(cohort_audit.get("strict_exact_completed_forward_rows"))
    acceptance_readiness = _as_dict(forward.get("acceptance_readiness"))
    acceptance_rows = _safe_int(acceptance_readiness.get("post_freeze_strict_exact_completed_rows"), exact_forward_rows)
    minimum_rows = _safe_int(_policy_gate(policy, "minimum_exact_completed_forward_rows", 30))
    evidence_accounting = _forward_evidence_accounting(
        cohort_meta=cohort_meta,
        forward=forward,
        acceptance=acceptance_readiness,
        minimum_rows=minimum_rows,
    )
    source_artifacts = {
        "policy": policy_meta,
        "trade_qualification": trade_meta,
        "robust_edge_discovery": robust_meta,
        "forward_cohort_log": cohort_meta,
        "forward_paper_shadow_report": {
            "status": "built_in_memory",
            "path": "scripts/build_volatility_expansion_forward_paper_shadow_report.py",
            "required": True,
        },
    }
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "mode": mode,
        "requested_max_iterations": requested_iterations,
        "max_iterations": iterations,
        "hard_cap_max_iterations": hard_cap,
        "iteration_count": 1,
        "read_only": True,
        "source_artifacts": source_artifacts,
        "current_decision_state": classification["state"],
        "next_safe_action": classification["action"],
        "final_recommendation": classification["recommendation"],
        "reason_codes": classification["reason_codes"],
        "live_entry_allowed": False if trade_qualification.get("live_entry_allowed") is not True else True,
        "auto_track_allowed": False if trade_qualification.get("auto_track_allowed") is not True else True,
        "broker_order_allowed": False if trade_qualification.get("broker_order_allowed") is not True else True,
        "promotion_ready": _promotion_ready_detected(trade_qualification, robust_edge, forward),
        "current_paper_shadow_lane": current_lane,
        "exact_realized_forward_pnl_count": exact_forward_rows,
        "minimum_review_rows_required": minimum_rows,
        "enough_rows_for_review": acceptance_rows >= minimum_rows,
        "current_blockers": _as_list(forward.get("hard_fail_states")) + _as_list(forward.get("warning_states")),
        "forward_evidence_accounting": evidence_accounting,
        "acceptance_readiness": acceptance_readiness,
        "strict_reject_counts": forward.get("strict_reject_counts"),
        "stopped_branches": _as_list(policy.get("stopped_branches")),
        "why_action_is_safe": "The selected action preserves paper-shadow-only posture and does not alter evidence, scanner, stops, sizing, broker, auto-track, live validation, quote imports, or strategy rules.",
        "not_run": not_run,
        "commands": command_results["commands"],
        "denied_commands": command_results["denied_commands"],
        "denied_command_or_mutation_attempted": command_results["denied_command_or_mutation_attempted"],
        "evidence_denominator_leakage_detected": any("denominator_leakage" in item for item in _as_list(forward.get("hard_fail_states"))),
        "policy_drift_detected": any("policy_drift" in item for item in _as_list(forward.get("hard_fail_states"))),
        "scanner_hash_drift_detected": any("scanner_hash_drift" in item for item in _as_list(forward.get("hard_fail_states"))),
        "quote_tradability_blockers_detected": bool(
            cohort_audit.get("zero_bid_untradable_rows")
            or any("zero_bid" in item or "untradable" in item for item in _as_list(forward.get("hard_fail_states")) + _as_list(forward.get("warning_states")))
        ),
        "exact_entry_exit_evidence_still_missing": acceptance_rows < minimum_rows,
        "cohort_audit": cohort_audit,
        "forward_paper_shadow_summary": {
            "overall_status": forward.get("overall_status"),
            "stressed_pf_lower_bound": forward.get("stressed_pf_lower_bound"),
            "evidence_accounting": evidence_accounting,
            "acceptance_readiness": acceptance_readiness,
            "gates": forward.get("gates"),
            "counts": forward.get("counts"),
            "hard_fail_states": forward.get("hard_fail_states"),
            "warning_states": forward.get("warning_states"),
        },
        "mutated_evidence_databases": False,
        "changed_strategy_logic": False,
        "changed_scanner_policy": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_broker_behavior": False,
        "changed_auto_track_behavior": False,
        "changed_live_validation": False,
        "imported_quotes": False,
        "repaired_historical_rows": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lane = _as_dict(report.get("current_paper_shadow_lane"))
    acceptance = _as_dict(report.get("acceptance_readiness"))
    evidence_accounting = _as_dict(report.get("forward_evidence_accounting"))
    lines = [
        "# Options Goal Loop",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`.",
        f"- Mode: `{report.get('mode')}`.",
        f"- Iterations: `{report.get('iteration_count')}` / `{report.get('max_iterations')}`.",
        f"- State: `{report.get('current_decision_state')}`.",
        f"- Next safest action: `{report.get('next_safe_action')}`.",
        f"- Final recommendation: {report.get('final_recommendation')}.",
        "",
        "## Decision Flags",
        "",
        f"- live_entry_allowed: `{str(report.get('live_entry_allowed')).lower()}`.",
        f"- auto_track_allowed: `{str(report.get('auto_track_allowed')).lower()}`.",
        f"- broker_order_allowed: `{str(report.get('broker_order_allowed')).lower()}`.",
        f"- promotion_ready: `{str(report.get('promotion_ready')).lower()}`.",
        "",
        "## Current Lane",
        "",
        f"- Paper-shadow lane: `{lane.get('lane_id')}`.",
        f"- Exact realized forward P&L rows: `{report.get('exact_realized_forward_pnl_count')}`.",
        f"- Post-freeze strict acceptance rows: `{acceptance.get('post_freeze_strict_exact_completed_rows')}` / `{acceptance.get('minimum_required')}`.",
        f"- Strict USD PF lower bound: `{acceptance.get('bootstrap_pf_lower_bound_5pct_usd')}`.",
        f"- Enough rows for review: `{str(report.get('enough_rows_for_review')).lower()}`.",
        "",
        "## Forward Evidence Accounting",
        "",
        f"- Accounting state: `{evidence_accounting.get('state')}`.",
        f"- Cohort log status: `{evidence_accounting.get('cohort_log_status')}`.",
        f"- Cohort log rows: `{evidence_accounting.get('cohort_log_row_count')}`.",
        f"- Strict rows remaining: `{evidence_accounting.get('strict_rows_remaining_to_minimum')}`.",
        f"- Excluded/rejected row flags: `{evidence_accounting.get('excluded_or_rejected_row_flags')}`.",
        f"- Cohort append performed: `{str(evidence_accounting.get('cohort_append_performed')).lower()}`.",
        "",
        "## Blockers",
        "",
    ]
    blockers = _as_list(report.get("current_blockers"))
    lines.extend([f"- `{item}`" for item in blockers] or ["- No hard blocker rows loaded; current read is still underpowered if row count is below gate."])
    lines.extend(["", "## Stopped Branches", ""])
    lines.extend(f"- {item}" for item in _as_list(report.get("stopped_branches")))
    lines.extend(["", "## Commands", ""])
    commands = _as_list(report.get("commands"))
    if commands:
        for command in commands:
            row = _as_dict(command)
            lines.append(f"- `{row.get('command')}` -> return code `{row.get('returncode')}`.")
    else:
        lines.append("- No commands were run in this mode.")
    denied = _as_list(report.get("denied_commands"))
    if denied:
        lines.extend(["", "## Denied", ""])
        for row in denied:
            row = _as_dict(row)
            lines.append(f"- `{row.get('command')}`: `{row.get('reason_codes')}`.")
    lines.extend(
        [
            "",
            "## Safety Confirmation",
            "",
            f"- Mutated evidence databases: `{str(report.get('mutated_evidence_databases')).lower()}`.",
            f"- Imported quotes: `{str(report.get('imported_quotes')).lower()}`.",
            f"- Repaired historical rows: `{str(report.get('repaired_historical_rows')).lower()}`.",
            f"- Changed scanner policy: `{str(report.get('changed_scanner_policy')).lower()}`.",
            f"- Changed strategy logic: `{str(report.get('changed_strategy_logic')).lower()}`.",
            f"- Changed stops/sizing/broker/auto-track/live-validation: `{str(any([report.get('changed_stops'), report.get('changed_sizing'), report.get('changed_broker_behavior'), report.get('changed_auto_track_behavior'), report.get('changed_live_validation')])).lower()}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_json: Path = DEFAULT_OUTPUT_JSON, output_md: Path = DEFAULT_OUTPUT_MD) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    output_md.write_text(render_markdown(report), encoding="utf8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one bounded options research goal-loop iteration.")
    parser.add_argument("--mode", choices=["audit", "verify", "prepare-protocol", "report"], default="audit")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--forward-protocol-schema", type=Path, default=DEFAULT_FORWARD_PROTOCOL_SCHEMA)
    parser.add_argument("--forward-cohort-preregistration", type=Path, default=DEFAULT_FORWARD_COHORT_PREREGISTRATION)
    parser.add_argument("--forward-cohort-log", type=Path, default=DEFAULT_FORWARD_COHORT_LOG)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        mode=args.mode,
        max_iterations=args.max_iterations,
        policy_path=args.policy,
        trade_qualification_path=args.trade_qualification,
        robust_edge_path=args.robust_edge,
        forward_protocol_schema_path=args.forward_protocol_schema,
        forward_cohort_preregistration_path=args.forward_cohort_preregistration,
        forward_cohort_log_path=args.forward_cohort_log,
        execute_commands=args.mode == "verify",
    )
    write_report(report, output_json=args.output_json, output_md=args.output_md)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{report['current_decision_state']} -> {report['next_safe_action']}")
        print(report["final_recommendation"])
    return 1 if report.get("current_decision_state") in {"safety_violation", "promotion_policy_violation"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
