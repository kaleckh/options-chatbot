from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_strict_forward_operator_queue"

DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_LAYER4_PROTOCOL = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer4_forward_capture_protocol_latest.json"
DEFAULT_MARKET_WINDOW_CHECKLIST = ROOT / "data" / "forward-tracking" / "regular_options_market_window_evidence_checklist_latest.json"
DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-operator-queue.md"

MAX_SOURCE_AGE_HOURS = 168
READY_PROTOCOL_STATUS = "protocol_ready_waiting_for_market_window_and_operator_approval"

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_strict_forward_operator_queue",
    "do_not_submit_broker_orders_from_strict_forward_operator_queue",
    "do_not_enable_live_validation_from_strict_forward_operator_queue",
    "do_not_enable_auto_track_from_strict_forward_operator_queue",
    "do_not_change_scanner_policy_from_strict_forward_operator_queue",
    "do_not_change_strategy_logic_from_strict_forward_operator_queue",
    "do_not_change_stops_from_strict_forward_operator_queue",
    "do_not_change_sizing_from_strict_forward_operator_queue",
    "do_not_lower_exact_executable_proof_bars_from_strict_forward_operator_queue",
    "do_not_import_quotes_from_strict_forward_operator_queue",
    "do_not_mutate_evidence_databases_from_strict_forward_operator_queue",
    "do_not_append_forward_cohort_rows_from_strict_forward_operator_queue",
    "do_not_consume_protected_holdout_from_strict_forward_operator_queue",
    "do_not_treat_historical_rows_as_forward_proof",
    "do_not_reopen_vix_selector_term_dispersion_vrp_cleanup_as_next_step",
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


def _load_json_artifact(
    path: Path,
    *,
    name: str,
    required: bool,
    generated_at_utc: str,
    max_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
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
    except OSError as exc:
        source.update({"status": "unreadable", "error": type(exc).__name__, "reason_codes": ["unreadable_readback"]})
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


def _source_block_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(meta.get("status") == "stale" or "stale_readback" in _as_list(meta.get("reason_codes")) for meta in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _strict_forward_target(oracle_packet: dict[str, Any]) -> tuple[int, int]:
    target = _as_dict(oracle_packet.get("profitability_target"))
    try:
        current = int(target.get("current_forward_rows") or 0)
    except (TypeError, ValueError):
        current = 0
    try:
        required = int(target.get("minimum_profitable_strict_completed_rows") or 30)
    except (TypeError, ValueError):
        required = 30
    return current, required


def _oracle_blocker_row(summary: dict[str, Any], *, branch_id: str, status_key: str, blocker_key: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "branch_id": branch_id,
        "status": summary.get(status_key),
        "blockers": _as_list(summary.get(blocker_key)) if blocker_key else [],
        "classification": "current_blocker",
        **(extra or {}),
    }


def _blocked_or_superseded_branches(oracle_packet: dict[str, Any]) -> list[dict[str, Any]]:
    summary = _as_dict(oracle_packet.get("current_evidence_summary"))
    rows = [
        {
            "branch_id": "direct_vix_source",
            "status": summary.get("direct_vix_source_import_status") or summary.get("direct_vix_source_repair_packet_status"),
            "blockers": [],
            "classification": "superseded_cleared",
            "superseded_by": "point_in_time_vix_bucket_ready",
        },
        {
            "branch_id": "direct_vix_bucket",
            "status": summary.get("point_in_time_vix_bucket_status"),
            "blockers": _as_list(summary.get("point_in_time_vix_bucket_blockers")),
            "classification": "cleared_current_input",
        },
        _oracle_blocker_row(
            summary,
            branch_id="candidate_generation_13_symbol_frozen_engine",
            status_key="candidate_generation_13_symbol_frozen_engine_status",
            blocker_key="candidate_generation_13_symbol_frozen_engine_blockers",
            extra={"candidate_months": summary.get("candidate_generation_13_symbol_candidate_months"), "selected_rows": summary.get("candidate_generation_13_symbol_frozen_engine_selected_rows")},
        ),
        _oracle_blocker_row(
            summary,
            branch_id="underlying_daily_source_acquisition",
            status_key="underlying_daily_source_acquisition_status",
            blocker_key="underlying_daily_source_acquisition_blockers",
            extra={"ready_candidate_count": summary.get("underlying_daily_source_acquisition_ready_candidate_count")},
        ),
        {
            "branch_id": "source_repair_59_symbol_thetadata_opra",
            "status": _as_dict(summary.get("source_repair_59_symbol_resume_theta_terminal")).get("status") or "blocked_thetaterminal_source_unavailable_retry",
            "blockers": ["thetaterminal_source_unavailable"],
            "classification": "current_provider_blocker",
        },
        _oracle_blocker_row(summary, branch_id="vrp_credit_spread", status_key="vrp_credit_spread_replay_readiness_status", blocker_key="vrp_credit_spread_replay_readiness_blockers"),
        _oracle_blocker_row(summary, branch_id="term_structure_calendar", status_key="term_structure_calendar_replay_readiness_status", blocker_key="term_structure_calendar_replay_readiness_blockers"),
        _oracle_blocker_row(summary, branch_id="skew_broken_wing", status_key="skew_broken_wing_bounded_replay_status", blocker_key="skew_broken_wing_bounded_replay_blockers"),
        _oracle_blocker_row(summary, branch_id="dispersion_proxy_hybrid", status_key="dispersion_proxy_hybrid_replay_readiness_status", blocker_key="dispersion_proxy_hybrid_replay_readiness_blockers"),
        _oracle_blocker_row(summary, branch_id="flow_extreme_ratio_backspread", status_key="flow_extreme_ratio_backspread_replay_readiness_status", blocker_key="flow_extreme_ratio_backspread_replay_readiness_blockers"),
        _oracle_blocker_row(summary, branch_id="momentum_continuation", status_key="momentum_continuation_bounded_replay_status", blocker_key="momentum_continuation_bounded_replay_blockers"),
        {
            "branch_id": "stale_cleanup_branches",
            "status": "do_not_repeat_without_new_artifact_or_source_state_change",
            "blockers": [],
            "classification": "superseded_or_exhausted",
            "notes": [
                "VIX cleanup is cleared by materialized point-in-time VIX.",
                "Selector, term mechanics, dispersion mechanics, VRP readiness, skew, and momentum stale-cleanup questions are not the next profitability loop task.",
            ],
        },
    ]
    if not summary.get("skew_broken_wing_bounded_replay_status"):
        rows.append(
            {
                "branch_id": "skew_broken_wing",
                "status": summary.get("preregistered_skew_broken_wing_status") or "parked_in_current_skew_artifacts",
                "blockers": ["missing_point_in_time_downside_skew_inputs", "missing_index_broken_wing_quote_surface"],
                "classification": "current_blocker",
            }
        )
    return [row for row in rows if row.get("status") is not None or row.get("classification") in {"superseded_cleared", "superseded_or_exhausted"}]


def _operator_checklist(market_checklist: dict[str, Any]) -> list[dict[str, Any]]:
    commands = _as_list(market_checklist.get("commands_to_run"))
    steps: list[dict[str, Any]] = []
    for item in commands:
        command = _as_dict(item)
        if not command:
            continue
        steps.append(
            {
                "priority": command.get("priority"),
                "command": command.get("command"),
                "purpose": command.get("purpose"),
                "read_only": True,
                "current_run_mutates_state": False,
                "is_broker_order": False,
                "is_trade_recommendation": False,
            }
        )
    steps.extend(
        [
            {
                "priority": 100,
                "command": "npm run options:validate:bullish-pullback-layer4-forward-candidate -- path/to/future_real_market_window_candidate_rows.jsonl",
                "purpose": "Read-only validation only if a future natural market-window candidate JSONL exists.",
                "read_only": True,
                "current_run_mutates_state": False,
                "is_broker_order": False,
                "is_trade_recommendation": False,
            },
            {
                "priority": 101,
                "command": "do not append from this queue",
                "purpose": "A future append would require a separate valid market window, explicit approval token, clean validator readback, and append_allowed=true.",
                "read_only": True,
                "current_run_mutates_state": False,
                "is_broker_order": False,
                "is_trade_recommendation": False,
            },
        ]
    )
    return steps


def build_report(
    *,
    oracle_packet_path: Path = DEFAULT_ORACLE_PACKET,
    layer4_protocol_path: Path = DEFAULT_LAYER4_PROTOCOL,
    market_window_checklist_path: Path = DEFAULT_MARKET_WINDOW_CHECKLIST,
    gateboard_path: Path = DEFAULT_GATEBOARD,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    oracle_packet, oracle_source = _load_json_artifact(oracle_packet_path, name="options_oracle_profit_loop_packet", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    layer4_protocol, layer4_source = _load_json_artifact(layer4_protocol_path, name="bullish_pullback_layer4_forward_capture_protocol", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    market_checklist, checklist_source = _load_json_artifact(market_window_checklist_path, name="regular_options_market_window_evidence_checklist", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    gateboard, gateboard_source = _load_json_artifact(gateboard_path, name="project_operator_gateboard", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    source_artifacts = {
        "options_oracle_profit_loop_packet": oracle_source,
        "bullish_pullback_layer4_forward_capture_protocol": layer4_source,
        "regular_options_market_window_evidence_checklist": checklist_source,
        "project_operator_gateboard": gateboard_source,
    }

    strict_rows, required_rows = _strict_forward_target(oracle_packet)
    source_status = _source_block_status(source_artifacts)
    protocol_status = _norm(layer4_protocol.get("capture_protocol_status") or layer4_protocol.get("overall_status"))
    if source_status:
        overall_status = source_status
        fresh_forward_capture_status = "blocked_readback_unavailable"
        blockers = [source_status]
    elif protocol_status != READY_PROTOCOL_STATUS:
        overall_status = "blocked_layer4_protocol_not_ready"
        fresh_forward_capture_status = "blocked_protocol_not_ready"
        blockers = ["layer4_protocol_not_ready"]
    else:
        overall_status = "strict_forward_queue_ready_approval_and_market_window_blocked"
        fresh_forward_capture_status = "approval_and_market_window_blocked"
        blockers = ["strict_forward_rows_0_below_30", "operator_approval_required", "valid_market_window_required"]

    profitability_readiness = strict_rows >= required_rows and not blockers
    selected_harness = _as_dict(layer4_protocol.get("selected_harness"))
    safety_flags = {
        "read_only": True,
        "paper_shadow_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "cohort_append_performed": False,
        "proof_bars_changed": False,
        "promotion_ready": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
    }
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "strict_forward_operator_visibility_queue",
        "overall_status": overall_status,
        "fresh_forward_capture_status": fresh_forward_capture_status,
        "blockers": blockers,
        "strict_forward_rows": strict_rows,
        "required_rows": required_rows,
        "profitability_readiness": profitability_readiness,
        "historical_rows_are_forward_proof": False,
        "source_artifacts": source_artifacts,
        "selected_path": {
            "lane_id": selected_harness.get("lane_id") or "bullish_pullback_observation",
            "layer_id": selected_harness.get("layer_id") or "layer_4_clean_exact",
            "variant_id": selected_harness.get("variant_id"),
            "source_result_path": selected_harness.get("source_result_path"),
            "freeze_date": selected_harness.get("freeze_date"),
            "allowed_symbols": selected_harness.get("allowed_symbols"),
        },
        "historical_executable_economics": _as_dict(layer4_protocol.get("historical_executable_economics")),
        "operator_posture": {
            "gateboard_status": gateboard.get("overall_status"),
            "market_window_status": market_checklist.get("market_window_status"),
            "market_window_checklist_status": market_checklist.get("overall_status"),
            "oracle_packet_status": oracle_packet.get("status"),
        },
        "future_operator_checklist": _operator_checklist(market_checklist),
        "blocked_or_superseded_branches": _blocked_or_superseded_branches(oracle_packet),
        "prohibited_actions": _unique(list(PROHIBITED_ACTIONS) + _as_list(layer4_protocol.get("prohibited_actions")) + _as_list(market_checklist.get("prohibited_actions"))),
        **safety_flags,
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    path = _as_dict(report.get("selected_path"))
    econ = _as_dict(report.get("historical_executable_economics"))
    posture = _as_dict(report.get("operator_posture"))
    lines = [
        "# Regular Options Strict Forward Operator Queue",
        "",
        f"Status: `{report.get('overall_status')}`.",
        "",
        f"Strict forward proof: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"Profitability readiness: `{str(bool(report.get('profitability_readiness'))).lower()}`.",
        f"Fresh forward capture status: `{report.get('fresh_forward_capture_status')}`.",
        "",
        "No live release. No broker orders. No proof bar changes. No source-row, quote, evidence, or cohort writes. Historical rows are not forward proof.",
        "",
        "## Selected Path",
        "",
        f"- Lane: `{path.get('lane_id')}`.",
        f"- Layer: `{path.get('layer_id')}`.",
        f"- Variant: `{path.get('variant_id')}`.",
        f"- Source run: `{path.get('source_result_path')}`.",
        f"- Freeze date: `{path.get('freeze_date')}`.",
        f"- Allowed symbols: `{_json_inline(path.get('allowed_symbols'))}`.",
        "",
        "## Historical Context",
        "",
        f"- Historical executable status: `{econ.get('status')}`.",
        f"- Harness decision: `{econ.get('harness_decision')}`.",
        f"- Tradable executable rows: `{econ.get('tradable_executable_rows')}`.",
        f"- Side-aware PF: `{econ.get('historical_side_aware_pf')}`.",
        f"- Side-aware PF lower bound 5pct: `{econ.get('historical_side_aware_pf_lb_5pct')}`.",
        f"- Historical rows are forward proof: `{str(bool(report.get('historical_rows_are_forward_proof'))).lower()}`.",
        "",
        "## Operator Posture",
        "",
        f"- Gateboard status: `{posture.get('gateboard_status')}`.",
        f"- Market-window checklist status: `{posture.get('market_window_checklist_status')}`.",
        f"- Market-window status: `{posture.get('market_window_status')}`.",
        f"- Oracle packet status: `{posture.get('oracle_packet_status')}`.",
        "",
        "## Future Non-Mutating Checklist",
        "",
    ]
    for step in _as_list(report.get("future_operator_checklist")):
        item = _as_dict(step)
        lines.append(f"- `{item.get('priority')}` `{item.get('command')}` - {item.get('purpose')}")
    lines.extend(["", "## Current Blockers And Parked Branches", ""])
    for branch in _as_list(report.get("blocked_or_superseded_branches")):
        item = _as_dict(branch)
        lines.append(f"- `{item.get('branch_id')}`: `{item.get('status')}` / `{item.get('classification')}`; blockers `{_json_inline(item.get('blockers'))}`.")
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
    parser = argparse.ArgumentParser(description="Build the strict-forward operator visibility queue.")
    parser.add_argument("--oracle-packet", type=Path, default=DEFAULT_ORACLE_PACKET)
    parser.add_argument("--layer4-protocol", type=Path, default=DEFAULT_LAYER4_PROTOCOL)
    parser.add_argument("--market-window-checklist", type=Path, default=DEFAULT_MARKET_WINDOW_CHECKLIST)
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        oracle_packet_path=args.oracle_packet,
        layer4_protocol_path=args.layer4_protocol,
        market_window_checklist_path=args.market_window_checklist,
        gateboard_path=args.gateboard,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
