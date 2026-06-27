from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_strict_forward_market_window_readiness_refresh"

DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-market-window-readiness-refresh.md"
MAX_SOURCE_AGE_HOURS = 168

DEFAULT_SOURCES = {
    "strict_forward_operator_queue": ROOT / "data" / "forward-tracking" / "regular_options_strict_forward_operator_queue_latest.json",
    "gateboard": ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json",
    "trade_qualification": ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json",
    "bullish_pullback_layer_shadow_selection": ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_shadow_selection_latest.json",
    "bullish_pullback_layer_execution_safety_audit": ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_execution_safety_audit_latest.json",
    "bullish_pullback_layer_executable_economics": ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_executable_economics_latest.json",
    "bullish_pullback_layer4_forward_capture_protocol": ROOT / "data" / "forward-tracking" / "bullish_pullback_layer4_forward_capture_protocol_latest.json",
    "paper_shadow_evidence_plan": ROOT / "data" / "forward-tracking" / "regular_options_paper_shadow_evidence_plan_latest.json",
    "fill_attempt_evidence_capture_plan": ROOT / "data" / "forward-tracking" / "regular_options_fill_attempt_evidence_capture_plan_latest.json",
    "suggested_trade_review_plan": ROOT / "data" / "forward-tracking" / "regular_options_suggested_trade_review_plan_latest.json",
    "monthly_profitability_audit": ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json",
    "market_window_approval_preflight": ROOT / "data" / "forward-tracking" / "regular_options_market_window_approval_preflight_latest.json",
    "forward_candidate_throughput_audit": ROOT / "data" / "forward-tracking" / "regular_options_forward_candidate_throughput_audit_latest.json",
}

EXPECTED_SELECTED_PATH = {
    "lane_id": "bullish_pullback_observation",
    "layer_id": "layer_4_clean_exact",
    "freeze_date": "2026-06-14",
}

SAFETY_FLAG_KEYS = {
    "live_entry_allowed": ("live_entry_allowed",),
    "auto_track_allowed": ("auto_track_allowed", "auto_track_enabled", "changed_auto_track_behavior"),
    "broker_order_allowed": ("broker_order_allowed",),
    "quotes_imported": ("quotes_imported", "imported_quotes"),
    "evidence_stores_mutated": ("evidence_stores_mutated", "mutated_evidence_databases", "evidence_databases_mutated"),
    "cohort_append_performed": ("cohort_append_performed", "appended_forward_cohort_rows"),
    "protected_holdout_consumed": ("protected_holdout_consumed", "consumed_protected_holdout"),
    "proof_bars_changed": ("proof_bars_changed", "lowered_proof_bars"),
    "promotion_ready": ("promotion_ready",),
    "scanner_policy_changed": ("scanner_policy_changed", "changed_scanner_policy"),
    "strategy_logic_changed": ("strategy_logic_changed", "changed_strategy_logic"),
    "stops_changed": ("stops_changed", "changed_stops"),
    "sizing_changed": ("sizing_changed", "changed_sizing"),
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_strict_forward_market_window_readiness_refresh",
    "do_not_submit_broker_orders_from_strict_forward_market_window_readiness_refresh",
    "do_not_enable_live_validation_from_strict_forward_market_window_readiness_refresh",
    "do_not_enable_auto_track_from_strict_forward_market_window_readiness_refresh",
    "do_not_import_quotes_from_strict_forward_market_window_readiness_refresh",
    "do_not_mutate_evidence_databases_from_strict_forward_market_window_readiness_refresh",
    "do_not_append_forward_cohort_rows_from_strict_forward_market_window_readiness_refresh",
    "do_not_consume_protected_holdout_from_strict_forward_market_window_readiness_refresh",
    "do_not_change_scanner_policy_from_strict_forward_market_window_readiness_refresh",
    "do_not_change_strategy_logic_from_strict_forward_market_window_readiness_refresh",
    "do_not_change_stops_from_strict_forward_market_window_readiness_refresh",
    "do_not_change_sizing_from_strict_forward_market_window_readiness_refresh",
    "do_not_lower_exact_executable_proof_bars_from_strict_forward_market_window_readiness_refresh",
    "do_not_treat_historical_rows_as_forward_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "allowed", "enabled"}
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _load_json(path: Path, *, name: str, generated_at_utc: str, max_age_hours: int) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": True,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
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
    if not isinstance(payload, dict):
        source.update({"status": "invalid", "reason_codes": ["json_root_not_object"]})
        return {}, source
    source["generated_at_utc"] = payload.get("generated_at_utc")
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    generated_dt = _parse_utc(payload.get("generated_at_utc"))
    if generated_dt is None:
        source.update({"status": "stale", "reason_codes": ["missing_or_malformed_generated_at_utc", "stale_readback"]})
        return payload, source
    age_hours = (as_of - generated_dt).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        source.update({"status": "invalid", "reason_codes": ["readback_generated_in_future"]})
        return payload, source
    if age_hours > max_age_hours:
        source.update({"status": "stale", "reason_codes": ["stale_readback"]})
        return payload, source
    source.update({"status": "loaded", "reason_codes": [], "report_id": payload.get("report_id") or name})
    return payload, source


def _source_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [name for name, meta in source_artifacts.items() if meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(source_artifacts[name].get("status") == "stale" for name in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _safety_flags(payloads: dict[str, dict[str, Any]]) -> tuple[dict[str, bool], list[dict[str, str]]]:
    flags = {name: False for name in SAFETY_FLAG_KEYS}
    violations: list[dict[str, str]] = []
    for source_name, payload in payloads.items():
        for flag_name, keys in SAFETY_FLAG_KEYS.items():
            for key in keys:
                if key in payload and _truthy(payload.get(key)):
                    flags[flag_name] = True
                    violations.append({"source": source_name, "flag": flag_name, "field": key})
    return flags, violations


def _selected_path_drift(selected_path: dict[str, Any]) -> list[str]:
    drift = []
    for key, expected in EXPECTED_SELECTED_PATH.items():
        if _norm(selected_path.get(key)) != expected:
            drift.append(f"{key}_drift")
    allowed = selected_path.get("allowed_symbols")
    if isinstance(allowed, list) and not allowed:
        drift.append("allowed_symbols_empty")
    return drift


def _preflight_view(preflight: dict[str, Any]) -> dict[str, Any]:
    validation = _as_dict(preflight.get("candidate_validation"))
    candidate_rows = validation.get("total_candidate_rows", 0)
    return {
        "market_window_status": preflight.get("market_window_status"),
        "market_window_valid": bool(preflight.get("market_window_valid")),
        "operator_approval_required": bool(preflight.get("operator_approval_required", True)),
        "operator_approval_granted": bool(preflight.get("operator_approval_granted")),
        "append_allowed": bool(preflight.get("append_allowed")),
        "candidate_jsonl_exists": bool(validation.get("candidate_jsonl_supplied")),
        "candidate_validator_read_only": bool(validation.get("candidate_validator_read_only", True)),
        "candidate_rows": int(candidate_rows or 0),
        "valid_candidate_rows": int(validation.get("valid_candidate_rows") or 0),
        "rejected_candidate_rows": int(validation.get("rejected_candidate_rows") or 0),
        "preflight_status": preflight.get("overall_status"),
        "next_operator_action": preflight.get("next_operator_action"),
    }


def _status_for(*, source_status: str | None, safety_violations: list[dict[str, str]], drift: list[str], preflight: dict[str, Any], strict_rows: int, required_rows: int) -> tuple[str, list[str]]:
    if source_status:
        return source_status, [source_status]
    if safety_violations:
        return "safety_blocked", [f"safety_flag:{item['source']}:{item['flag']}" for item in safety_violations]
    if drift:
        return "selected_path_identity_drift", drift
    blockers: list[str] = []
    if strict_rows < required_rows:
        blockers.append(f"strict_forward_rows_{strict_rows}_below_{required_rows}")
    if not preflight.get("market_window_valid"):
        blockers.append("valid_market_window_required")
    if not preflight.get("candidate_jsonl_exists"):
        blockers.append("natural_candidate_jsonl_missing")
    if preflight.get("operator_approval_required") and not preflight.get("operator_approval_granted"):
        blockers.append("operator_approval_required")
    if not preflight.get("append_allowed"):
        blockers.append("append_allowed_false")
    if not preflight.get("market_window_valid"):
        return "market_window_blocked_no_candidate_jsonl", blockers
    if not preflight.get("candidate_jsonl_exists"):
        return "candidate_throughput_blocked_waiting_for_natural_rows", blockers
    if not preflight.get("append_allowed"):
        return "candidate_validation_blocked_no_append", blockers
    return "ready_for_later_operator_approval_discussion_no_append_performed", blockers


def build_report(
    *,
    source_paths: dict[str, Path] | None = None,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    paths = source_paths or DEFAULT_SOURCES
    payloads: dict[str, dict[str, Any]] = {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        payload, source = _load_json(path, name=name, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
        payloads[name] = payload
        source_artifacts[name] = source

    queue = payloads["strict_forward_operator_queue"]
    selected_path = _as_dict(queue.get("selected_path"))
    preflight = _preflight_view(payloads["market_window_approval_preflight"])
    throughput = payloads["forward_candidate_throughput_audit"]
    try:
        strict_rows = int(queue.get("strict_forward_rows") or 0)
    except (TypeError, ValueError):
        strict_rows = 0
    try:
        required_rows = int(queue.get("required_rows") or 30)
    except (TypeError, ValueError):
        required_rows = 30

    source_problem = _source_status(source_artifacts)
    safety, safety_violations = _safety_flags(payloads)
    drift = _selected_path_drift(selected_path)
    overall_status, blockers = _status_for(
        source_status=source_problem,
        safety_violations=safety_violations,
        drift=drift,
        preflight=preflight,
        strict_rows=strict_rows,
        required_rows=required_rows,
    )
    econ = _as_dict(queue.get("historical_executable_economics"))
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "strict_forward_bullish_pullback_layer4_market_window_readiness_refresh",
        "overall_status": overall_status,
        "blockers": blockers,
        "strict_forward_rows": strict_rows,
        "required_rows": required_rows,
        "accepted_profitability": False,
        "profitability_readiness": False,
        "promotion_ready": False,
        "historical_rows_are_forward_proof": False,
        "selected_path": selected_path,
        "selected_path_drift": drift,
        "preflight": preflight,
        "candidate_throughput": {
            "status": throughput.get("status"),
            "scan_picks_row_count": throughput.get("scan_picks_row_count"),
            "post_freeze_phase2_scan_pick_count": throughput.get("post_freeze_phase2_scan_pick_count"),
            "target_selection_date": throughput.get("target_selection_date"),
            "target_date_phase2_scan_pick_count": throughput.get("target_date_phase2_scan_pick_count"),
            "scheduled_scan_session_count": throughput.get("scheduled_scan_session_count"),
            "scheduled_phase2_scan_picks_count": throughput.get("scheduled_phase2_scan_picks_count"),
            "scheduled_phase2_drop_count_total": throughput.get("scheduled_phase2_drop_count_total"),
            "scheduled_phase2_scan_drop_reason_count_total": throughput.get("scheduled_phase2_scan_drop_reason_count_total"),
            "candidate_starvation_evidence_status": throughput.get("candidate_starvation_evidence_status"),
            "scheduled_phase2_all_lanes_scanned": throughput.get("scheduled_phase2_all_lanes_scanned"),
            "scheduled_phase2_playbooks_with_session": _as_list(throughput.get("scheduled_phase2_playbooks_with_session")),
            "scheduled_phase2_playbooks_missing_session": _as_list(throughput.get("scheduled_phase2_playbooks_missing_session")),
            "passive_forward_cohort_scan_sweep_command": throughput.get("passive_forward_cohort_scan_sweep_command"),
            "candidate_rows_staged": throughput.get("candidate_rows_staged"),
            "candidate_jsonl_written": throughput.get("candidate_jsonl_written"),
            "next_action": throughput.get("next_action"),
            "stager_rejected_counts": _as_dict(throughput.get("stager_rejected_counts")),
        },
        "safety": safety,
        "safety_violations": safety_violations,
        "source_artifacts": source_artifacts,
        "historical_executable_economics": {
            "status": econ.get("status"),
            "harness_decision": econ.get("harness_decision"),
            "tradable_executable_rows": econ.get("tradable_executable_rows"),
            "historical_side_aware_pf": econ.get("historical_side_aware_pf"),
            "historical_side_aware_pf_lb_5pct": econ.get("historical_side_aware_pf_lb_5pct"),
        },
        "readback_statuses": {name: payload.get("overall_status") or payload.get("status") for name, payload in payloads.items()},
        "operator_decision_table": [
            {
                "decision": "ready_for_later_approval_discussion",
                "pass": overall_status == "ready_for_later_operator_approval_discussion_no_append_performed",
                "requirements": ["market_window_valid", "candidate_jsonl_exists", "append_allowed", "safety_clean"],
            },
            {
                "decision": "market_window_blocked",
                "pass": "valid_market_window_required" in blockers,
                "requirements": ["wait_for_valid_market_window", "rerun_preflight"],
            },
            {
                "decision": "candidate_throughput_blocked",
                "pass": "natural_candidate_jsonl_missing" in blockers,
                "requirements": ["future_real_market_window_scan_picks", "no_fixture_or_historical_rows"],
            },
            {
                "decision": "safety_blocked",
                "pass": bool(safety_violations),
                "requirements": ["no_live_broker_autotrack_import_append_mutation_or_proof_changes"],
            },
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        **{name: False for name in SAFETY_FLAG_KEYS},
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    preflight = _as_dict(report.get("preflight"))
    throughput = _as_dict(report.get("candidate_throughput"))
    econ = _as_dict(report.get("historical_executable_economics"))
    lines = [
        "# Regular Options Strict Forward Market-Window Readiness Refresh",
        "",
        f"Status: `{report.get('overall_status')}`.",
        "",
        f"Strict forward proof: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
        f"Profitability readiness: `{str(bool(report.get('profitability_readiness'))).lower()}`.",
        f"Historical rows are forward proof: `{str(bool(report.get('historical_rows_are_forward_proof'))).lower()}`.",
        "",
        "This is a no-write readiness refresh. It does not stage candidate rows, validate fabricated rows, append cohorts, import quotes, mutate evidence stores, change production policy, submit orders, enable live validation, enable auto-track, consume holdout, or promote a lane.",
        "",
        "## Preflight",
        "",
        f"- Market-window status: `{preflight.get('market_window_status')}`.",
        f"- Market-window valid: `{str(bool(preflight.get('market_window_valid'))).lower()}`.",
        f"- Candidate JSONL exists: `{str(bool(preflight.get('candidate_jsonl_exists'))).lower()}`.",
        f"- Candidate rows: `{preflight.get('candidate_rows')}`.",
        f"- Valid candidate rows: `{preflight.get('valid_candidate_rows')}`.",
        f"- Append allowed: `{str(bool(preflight.get('append_allowed'))).lower()}`.",
        f"- Operator approval required: `{str(bool(preflight.get('operator_approval_required'))).lower()}`.",
        f"- Operator approval granted: `{str(bool(preflight.get('operator_approval_granted'))).lower()}`.",
        "",
        "## Candidate Throughput",
        "",
        f"- Throughput status: `{throughput.get('status')}`.",
        f"- Target selection date: `{throughput.get('target_selection_date')}`.",
        f"- Scan-pick rows: `{throughput.get('scan_picks_row_count')}`.",
        f"- Post-freeze Phase 2 rows: `{throughput.get('post_freeze_phase2_scan_pick_count')}`.",
        f"- Target-date Phase 2 rows: `{throughput.get('target_date_phase2_scan_pick_count')}`.",
        f"- Scheduled scan sessions: `{throughput.get('scheduled_scan_session_count')}`.",
        f"- Scheduled Phase 2 scan picks: `{throughput.get('scheduled_phase2_scan_picks_count')}`.",
        f"- Scheduled Phase 2 drop-count total: `{throughput.get('scheduled_phase2_drop_count_total')}`.",
        f"- Scheduled Phase 2 symbol drop reasons: `{throughput.get('scheduled_phase2_scan_drop_reason_count_total')}`.",
        f"- Candidate-starvation evidence status: `{throughput.get('candidate_starvation_evidence_status')}`.",
        f"- Scheduled Phase 2 all lanes scanned: `{str(bool(throughput.get('scheduled_phase2_all_lanes_scanned'))).lower()}`.",
        f"- Scheduled Phase 2 lanes with session: `{_json_inline(throughput.get('scheduled_phase2_playbooks_with_session'))}`.",
        f"- Scheduled Phase 2 missing lanes: `{_json_inline(throughput.get('scheduled_phase2_playbooks_missing_session'))}`.",
        f"- Candidate rows staged: `{throughput.get('candidate_rows_staged')}`.",
        f"- Candidate JSONL written: `{str(bool(throughput.get('candidate_jsonl_written'))).lower()}`.",
        f"- Next action: `{throughput.get('next_action')}`.",
        f"- Passive sweep command: `{throughput.get('passive_forward_cohort_scan_sweep_command')}`.",
        f"- Stager rejected counts: `{_json_inline(throughput.get('stager_rejected_counts'))}`.",
        "",
        "## Historical Ranking Context",
        "",
        f"- Status: `{econ.get('status')}`.",
        f"- Harness decision: `{econ.get('harness_decision')}`.",
        f"- Tradable executable rows: `{econ.get('tradable_executable_rows')}`.",
        f"- Side-aware PF: `{econ.get('historical_side_aware_pf')}`.",
        f"- Side-aware PF lower bound 5pct: `{econ.get('historical_side_aware_pf_lb_5pct')}`.",
        "",
        "## Decision Table",
        "",
    ]
    for row in _as_list(report.get("operator_decision_table")):
        item = _as_dict(row)
        lines.append(f"- `{item.get('decision')}`: `{str(bool(item.get('pass'))).lower()}`; requirements `{_json_inline(item.get('requirements'))}`.")
    lines.extend(["", "## Blockers", ""])
    blockers = _as_list(report.get("blockers"))
    lines.extend(f"- `{item}`" for item in blockers) if blockers else lines.append("- None.")
    lines.extend(["", "## Source Readbacks", ""])
    for name, meta in _as_dict(report.get("source_artifacts")).items():
        source = _as_dict(meta)
        lines.append(f"- `{name}`: `{source.get('status')}` age `{source.get('age_hours')}` hours at `{source.get('path')}`.")
    lines.extend(["", "## Prohibited Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build strict-forward market-window readiness refresh.")
    for name, path in DEFAULT_SOURCES.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    source_paths = {name: getattr(args, name) for name in DEFAULT_SOURCES}
    report = build_report(source_paths=source_paths, max_source_age_hours=args.max_source_age_hours)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
