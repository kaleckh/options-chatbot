from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_lane_scan_hypothesis_repair"

DEFAULT_LANE_OUTCOME_REPLAY = ROOT / "data" / "forward-tracking" / "regular_options_lane_outcome_replay_latest.json"
DEFAULT_ZERO_PICK_AUDIT = ROOT / "data" / "forward-tracking" / "all_lanes_zero_pick_current_algo_audit_latest.json"
DEFAULT_LANE_PROMOTION_STATE = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_SYMBOL_SLEEVES = ROOT / "data" / "profitability-lab" / "regular-options-symbol-sleeves" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-lane-scan-hypothesis-repair.md"

NO_SIGNAL_OUTCOME_STATUS = "no_signal_candidates_in_monthly_window"
PROOF_ONLY_REPLACEMENT_STATUSES = {"needs-paper", "watch"}
TRUSTED_INTRADAY_EVIDENCE_CLASSES = {
    "trusted_intraday_opra_nbbo_exact",
    "trusted_intraday_unresolved",
}

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_lane_scan_hypothesis_repair",
    "do_not_submit_broker_order_from_lane_scan_hypothesis_repair",
    "do_not_mutate_database_from_lane_scan_hypothesis_repair",
    "do_not_change_scanner_policy_from_lane_scan_hypothesis_repair",
    "do_not_tune_threshold_symbol_expiry_or_window_from_zero_signal_sample",
    "do_not_change_stop_policy_from_lane_scan_hypothesis_repair",
    "do_not_change_sizing_from_lane_scan_hypothesis_repair",
    "do_not_change_lane_promotion_from_lane_scan_hypothesis_repair",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_lane_scan_hypothesis_repair",
    "do_not_synthesize_pnl_for_no_signal_lanes",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _zero_pick_lane_map(zero_pick_audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for lane in _as_list(zero_pick_audit.get("lanes")):
        if not isinstance(lane, dict):
            continue
        playbook = _norm(lane.get("playbook"))
        if playbook:
            lanes[playbook] = lane
    return lanes


def _dominant_reason(reason_counts: dict[str, Any]) -> str | None:
    parsed = {
        _norm(reason): _safe_int(count)
        for reason, count in reason_counts.items()
        if _norm(reason) and _safe_int(count)
    }
    if not parsed:
        return None
    return max(sorted(parsed), key=lambda reason: parsed[reason])


def _lane_promotion_context(lane_promotion_state: dict[str, Any], lane: str) -> dict[str, Any]:
    lane_state = _as_dict(_as_dict(lane_promotion_state.get("lane_states")).get(lane))
    return {
        "promotion_state": lane_state.get("promotion_state"),
        "tracking_mode": lane_state.get("tracking_mode"),
        "candidate_status": lane_state.get("candidate_status"),
        "candidate_status_reason": lane_state.get("candidate_status_reason"),
        "blockers": sorted(
            set(
                str(item)
                for item in [
                    *_as_list(lane_state.get("blockers")),
                    *_as_list(lane_state.get("failed_promotion_gates")),
                ]
                if item
            )
        ),
        "fresh_evidence": lane_state.get("fresh_evidence"),
    }


def _candidate_proof_status(row: dict[str, Any]) -> str:
    metrics = _as_dict(row.get("metrics"))
    evidence_class = _norm(row.get("evidence_class"))
    exact_count = _safe_int(metrics.get("exact_trusted_priced_trades"))
    if (
        evidence_class == "trusted_intraday_opra_nbbo_exact"
        and exact_count > 0
        and row.get("executable_exit_pnl") is not None
    ):
        return "exact_contract_executable_pnl_available"
    if evidence_class in TRUSTED_INTRADAY_EVIDENCE_CLASSES:
        return "proof_only_collecting_not_production_proof"
    return "not_proof_eligible"


def _candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(row.get("metrics"))
    proof_status = _candidate_proof_status(row)
    return {
        "sleeve_id": row.get("sleeve_id"),
        "lane_family": row.get("lane_family"),
        "lane_id": row.get("lane_id"),
        "strategy_logic_id": row.get("strategy_logic_id"),
        "symbol": row.get("symbol"),
        "status": row.get("status"),
        "evidence_class": row.get("evidence_class"),
        "sample_status": row.get("sample_status"),
        "rolling_oos_status": row.get("rolling_oos_status"),
        "candidate_count": metrics.get("candidates"),
        "exact_trusted_priced_trades": metrics.get("exact_trusted_priced_trades"),
        "unresolved_rows": metrics.get("unresolved_rows"),
        "quote_coverage": metrics.get("quote_coverage"),
        "profit_factor": metrics.get("profit_factor"),
        "avg_pnl": metrics.get("avg_pnl"),
        "executable_exit_pnl": row.get("executable_exit_pnl"),
        "proof_status": proof_status,
        "production_proof_ready": proof_status == "exact_contract_executable_pnl_available",
        "reason_codes": _as_list(row.get("reason_codes")),
        "blockers": _as_list(row.get("blockers")),
        "source_artifacts": _as_list(row.get("source_artifacts")),
        "next_step": row.get("next_step"),
    }


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    status_rank = 0 if _norm(row.get("status")) in PROOF_ONLY_REPLACEMENT_STATUSES else 1
    evidence_rank = 0 if _norm(row.get("evidence_class")) in TRUSTED_INTRADAY_EVIDENCE_CLASSES else 1
    return (status_rank + evidence_rank, _norm(row.get("lane_id")), _norm(row.get("symbol")))


def _predeclared_candidates(symbol_sleeves: dict[str, Any], lane: str) -> list[dict[str, Any]]:
    rows = []
    for row in _as_list(symbol_sleeves.get("lane_symbol_rows")):
        if not isinstance(row, dict):
            continue
        lane_family = _norm(row.get("lane_family"))
        lane_id = _norm(row.get("lane_id"))
        strategy_logic_id = _norm(row.get("strategy_logic_id"))
        if lane_family != lane and not lane_id.startswith(lane) and not strategy_logic_id.startswith(lane):
            continue
        if _norm(row.get("status")) not in PROOF_ONLY_REPLACEMENT_STATUSES:
            continue
        if _norm(row.get("evidence_class")) not in TRUSTED_INTRADAY_EVIDENCE_CLASSES:
            continue
        rows.append(_candidate_row(row))
    rows.sort(key=_candidate_sort_key)
    return rows


def _target_rows(
    lane_outcome_replay: dict[str, Any],
    zero_pick_audit: dict[str, Any],
    lane_promotion_state: dict[str, Any],
    symbol_sleeves: dict[str, Any],
) -> list[dict[str, Any]]:
    zero_lanes = _zero_pick_lane_map(zero_pick_audit)
    rows = []
    for outcome_row in _as_list(lane_outcome_replay.get("lane_outcome_table")):
        if not isinstance(outcome_row, dict):
            continue
        if _norm(outcome_row.get("outcome_status")) != NO_SIGNAL_OUTCOME_STATUS:
            continue
        lane = _norm(outcome_row.get("lane"))
        zero_summary = _as_dict(_as_dict(zero_lanes.get(lane)).get("summary"))
        signal_reject_reason_counts = (
            zero_summary.get("signal_reject_reason_counts")
            or outcome_row.get("zero_pick_signal_reject_reason_counts")
            or {}
        )
        signal_reject_reason_counts = _as_dict(signal_reject_reason_counts)
        candidates = _predeclared_candidates(symbol_sleeves, lane)
        repair_status = (
            "predeclared_proof_only_candidate_found"
            if candidates
            else "causal_replacement_hypothesis_missing"
        )
        blockers = [
            "fresh_exact_scan_retest_rows_missing",
            "true_lane_outcome_pnl_rows_missing",
        ]
        if not candidates:
            blockers.append("predeclared_replacement_candidate_missing")
        rows.append(
            {
                "lane": lane,
                "outcome_status": outcome_row.get("outcome_status"),
                "repair_status": repair_status,
                "zero_pick_date_count": zero_summary.get("date_count", outcome_row.get("zero_pick_date_count")),
                "zero_pick_signal_candidate_count": zero_summary.get(
                    "signal_candidate_count",
                    outcome_row.get("zero_pick_signal_candidate_count"),
                ),
                "zero_pick_exact_candidate_count": zero_summary.get(
                    "exact_candidate_count",
                    outcome_row.get("zero_pick_exact_candidate_count"),
                ),
                "zero_pick_would_track_pick_count": zero_summary.get(
                    "would_track_pick_count",
                    outcome_row.get("zero_pick_would_track_pick_count"),
                ),
                "signal_reject_reason_counts": signal_reject_reason_counts,
                "dominant_signal_reject_reason": _dominant_reason(signal_reject_reason_counts),
                "promotion_context": _lane_promotion_context(lane_promotion_state, lane),
                "predeclared_replacement_candidates": candidates,
                "predeclared_replacement_candidate_count": len(candidates),
                "production_proof_ready_candidate_count": sum(
                    1 for candidate in candidates if candidate.get("production_proof_ready")
                ),
                "fresh_exact_scan_retest_row_count": 0,
                "true_lane_outcome_pnl_row_count": 0,
                "blockers": blockers,
                "operator_next_step": (
                    "Collect proof-only exact intraday quote coverage and forward paper scan rows for the predeclared replacement candidate; do not tune scanner filters from the zero-signal sample."
                    if candidates
                    else "Draft a causal replacement hypothesis from lane design evidence or keep the lane diagnostic; do not loosen thresholds, symbols, expiries, or windows from this zero-signal sample."
                ),
            }
        )
    rows.sort(key=lambda item: _norm(item.get("lane")))
    return rows


def _next_evidence_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_lane_count = sum(
        1 for row in rows if _safe_int(row.get("predeclared_replacement_candidate_count")) > 0
    )
    missing_lane_count = sum(
        1 for row in rows if _safe_int(row.get("predeclared_replacement_candidate_count")) == 0
    )
    queue: list[dict[str, Any]] = []
    if candidate_lane_count:
        queue.append(
            {
                "priority": 7,
                "action": "collect_proof_only_lane_scan_retest_rows",
                "count": candidate_lane_count,
                "reason": "no_signal_lanes_have_predeclared_proof_only_replacement_candidates",
                "operator_next_step": "Collect fresh exact intraday quote coverage and forward paper rows; do not promote or tune from thin samples.",
            }
        )
    if missing_lane_count:
        queue.append(
            {
                "priority": 7,
                "action": "draft_causal_hypothesis_for_no_signal_lane_without_tuning",
                "count": missing_lane_count,
                "reason": "no_signal_lanes_lack_predeclared_replacement_candidate",
                "operator_next_step": "Use design/evidence records to predeclare a causal diagnostic replacement, or keep the lane no-chase.",
            }
        )
    return queue


def build_report(
    *,
    lane_outcome_replay_path: Path = DEFAULT_LANE_OUTCOME_REPLAY,
    zero_pick_audit_path: Path = DEFAULT_ZERO_PICK_AUDIT,
    lane_promotion_state_path: Path = DEFAULT_LANE_PROMOTION_STATE,
    symbol_sleeves_path: Path = DEFAULT_SYMBOL_SLEEVES,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = {
        "lane_outcome_replay": lane_outcome_replay_path,
        "all_lanes_zero_pick_audit": zero_pick_audit_path,
        "lane_promotion_state": lane_promotion_state_path,
        "regular_options_symbol_sleeves": symbol_sleeves_path,
    }
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], inputs[key] = _load_json(path)

    missing_required = [key for key, meta in inputs.items() if meta.get("status") != "loaded"]
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())
    rows = _target_rows(
        reports["lane_outcome_replay"],
        reports["all_lanes_zero_pick_audit"],
        reports["lane_promotion_state"],
        reports["regular_options_symbol_sleeves"],
    )
    next_queue = _next_evidence_queue(rows)
    target_count = len(rows)
    candidate_count = sum(_safe_int(row.get("predeclared_replacement_candidate_count")) for row in rows)
    candidate_lane_count = sum(
        1 for row in rows if _safe_int(row.get("predeclared_replacement_candidate_count")) > 0
    )
    proof_ready_count = sum(_safe_int(row.get("production_proof_ready_candidate_count")) for row in rows)
    missing_candidate_lane_count = target_count - candidate_lane_count
    status_counts = Counter(_norm(row.get("repair_status")) for row in rows)

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    elif target_count:
        status = "lane_scan_hypothesis_repair_readback"
        overall_status = "lane_scan_hypothesis_repair_built_collecting"
    else:
        status = "lane_scan_hypothesis_repair_readback"
        overall_status = "lane_scan_hypothesis_repair_no_targets"

    blockers = []
    if target_count:
        blockers.extend(
            [
                "fresh_exact_scan_retest_rows_missing",
                "true_lane_outcome_pnl_rows_missing",
            ]
        )
    if missing_candidate_lane_count:
        blockers.append("some_no_signal_lanes_lack_predeclared_replacement_candidate")

    summary = {
        "overall_status": overall_status,
        "missing_required_inputs": missing_required,
        "target_no_signal_lane_count": target_count,
        "predeclared_replacement_candidate_count": candidate_count,
        "predeclared_candidate_lane_count": candidate_lane_count,
        "missing_replacement_candidate_lane_count": missing_candidate_lane_count,
        "proof_ready_replacement_candidate_count": proof_ready_count,
        "fresh_exact_scan_retest_row_count": 0,
        "true_lane_outcome_pnl_row_count": 0,
        "repair_status_counts": dict(sorted(status_counts.items())),
        "next_evidence_action_count": len(next_queue),
        "promotion_ready": False,
        "blockers": sorted(set(blockers)),
        "live_policy_change": live_policy_change,
    }
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_lane_scan_hypothesis_repair",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only proof-only diagnostic plan for no-signal regular-options lane scan hypotheses",
            "readback_is_not": "scanner tuning, broker recommendation, DB mutation, lane promotion, or production proof",
            "trusted_proof_standard": "production proof requires trusted intraday exact-contract OPRA/NBBO entry, exit, fill, and executable P&L",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "repair_rows": rows,
        "next_evidence_queue": next_queue,
        "live_policy_change": live_policy_change,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Lane Scan Hypothesis Repair",
        "",
        "This report is generated from `scripts/build_regular_options_lane_scan_hypothesis_repair.py`. It is a read-only proof-only diagnostic plan for active regular supervised lanes that produced no signal candidates in the monthly outcome window.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Target no-signal lanes: `{summary.get('target_no_signal_lane_count')}`.",
        f"- Predeclared replacement candidates: `{summary.get('predeclared_replacement_candidate_count')}` across `{summary.get('predeclared_candidate_lane_count')}` lanes.",
        f"- Missing replacement-candidate lanes: `{summary.get('missing_replacement_candidate_lane_count')}`.",
        f"- Production proof-ready replacement candidates: `{summary.get('proof_ready_replacement_candidate_count')}`.",
        f"- Fresh exact scan retest rows: `{summary.get('fresh_exact_scan_retest_row_count')}`.",
        f"- True lane outcome P&L rows: `{summary.get('true_lane_outcome_pnl_row_count')}`.",
        f"- Repair status counts: `{_json_inline(summary.get('repair_status_counts') or {})}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Repair Rows",
        "",
        "| Lane | Repair Status | Dates | Signals | Exact | Would Track | Dominant Reject | Candidates | Proof Ready | Next Step |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in _as_list(report.get("repair_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("lane")),
                    f"`{_cell(row.get('repair_status'))}`",
                    _cell(row.get("zero_pick_date_count")),
                    _cell(row.get("zero_pick_signal_candidate_count")),
                    _cell(row.get("zero_pick_exact_candidate_count")),
                    _cell(row.get("zero_pick_would_track_pick_count")),
                    _cell(row.get("dominant_signal_reject_reason")),
                    _cell(row.get("predeclared_replacement_candidate_count")),
                    _cell(row.get("production_proof_ready_candidate_count")),
                    _cell(row.get("operator_next_step")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Predeclared Replacement Candidates",
            "",
            "| Lane | Sleeve | Symbol | Status | Evidence | Candidates | Exact | Unresolved | Quote Coverage | PF | Proof Status |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in _as_list(report.get("repair_rows")):
        row = _as_dict(row)
        for candidate in _as_list(row.get("predeclared_replacement_candidates")):
            candidate = _as_dict(candidate)
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(row.get("lane")),
                        _cell(candidate.get("sleeve_id")),
                        _cell(candidate.get("symbol")),
                        f"`{_cell(candidate.get('status'))}`",
                        f"`{_cell(candidate.get('evidence_class'))}`",
                        _cell(candidate.get("candidate_count")),
                        _cell(candidate.get("exact_trusted_priced_trades")),
                        _cell(candidate.get("unresolved_rows")),
                        _cell(candidate.get("quote_coverage")),
                        _cell(candidate.get("profit_factor")),
                        f"`{_cell(candidate.get('proof_status'))}`",
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Next Evidence Queue",
            "",
            "| Priority | Action | Count | Reason |",
            "|---:|---|---:|---|",
        ]
    )
    for item in _as_list(report.get("next_evidence_queue")):
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('priority'))} | `{_cell(item.get('action'))}` | {_cell(item.get('count'))} | {_cell(item.get('reason'))} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This repair plan is read-only and proof-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, tune thresholds/symbols/expiries/windows from tiny samples, change stops or sizing, change lane promotion, lower proof bars, or synthesize P&L.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Build the regular-options lane scan hypothesis repair plan.")
    parser.add_argument("--lane-outcome-replay", type=Path, default=DEFAULT_LANE_OUTCOME_REPLAY)
    parser.add_argument("--zero-pick-audit", type=Path, default=DEFAULT_ZERO_PICK_AUDIT)
    parser.add_argument("--lane-promotion-state", type=Path, default=DEFAULT_LANE_PROMOTION_STATE)
    parser.add_argument("--symbol-sleeves", type=Path, default=DEFAULT_SYMBOL_SLEEVES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        lane_outcome_replay_path=args.lane_outcome_replay,
        zero_pick_audit_path=args.zero_pick_audit,
        lane_promotion_state_path=args.lane_promotion_state,
        symbol_sleeves_path=args.symbol_sleeves,
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
