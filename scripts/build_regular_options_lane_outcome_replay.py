from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_monthly_all_lanes_profitability_audit as monthly_audit  # noqa: E402


REPORT_ID = "regular_options_lane_outcome_replay"

DEFAULT_FAILURE_MODES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json"
DEFAULT_MISSED_OUTCOME = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_LANE_PROMOTION_STATE = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_ZERO_PICK_AUDIT = ROOT / "data" / "forward-tracking" / "all_lanes_zero_pick_current_algo_audit_latest.json"
DEFAULT_LANE_QUARANTINE_ARCHIVE = (
    ROOT / "data" / "forward-tracking" / "regular_options_lane_quarantine_archive_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-lane-outcome-replay.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_lane_outcome_replay",
    "do_not_submit_broker_order_from_lane_outcome_replay",
    "do_not_mutate_database_from_lane_outcome_replay",
    "do_not_change_scanner_policy_from_lane_outcome_replay",
    "do_not_change_lane_promotion_from_lane_outcome_replay",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_lane_outcome_replay",
    "do_not_synthesize_outcome_pnl_for_lanes_without_exact_priced_rows",
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


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _lane_disposition_map(
    failure_modes: dict[str, Any],
    lane_promotion_state: dict[str, Any],
    lane_quarantine_archive: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    leaderboard = monthly_audit._lane_leaderboard(failure_modes)
    dispositions = monthly_audit._lane_dispositions(
        leaderboard,
        lane_promotion_state,
        {"promotion_ready": False, "blockers": []},
    )
    annotated = monthly_audit._annotate_lane_quarantine_archive(dispositions, lane_quarantine_archive)
    return {
        _norm(item.get("lane")): item
        for item in _as_list(annotated.get("dispositions"))
        if isinstance(item, dict) and _norm(item.get("lane"))
    }


def _zero_pick_lane_map(zero_pick_audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for lane in _as_list(zero_pick_audit.get("lanes")):
        if not isinstance(lane, dict):
            continue
        playbook = _norm(lane.get("playbook"))
        if playbook:
            lanes[playbook] = lane
    return lanes


def _tracked_outcome_counts(missed_outcome: dict[str, Any]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in _as_list(missed_outcome.get("rows")):
        if not isinstance(row, dict):
            continue
        lane = _norm(row.get("playbook"))
        if not lane:
            continue
        item = counts.setdefault(lane, {"raw": 0, "priced": 0, "tracked": 0, "untracked_priced": 0})
        item["raw"] += 1
        if _as_dict(row.get("mark")).get("priced"):
            item["priced"] += 1
            if _safe_int(row.get("tracked_match_count")) == 0:
                item["untracked_priced"] += 1
        if _safe_int(row.get("tracked_match_count")) > 0:
            item["tracked"] += 1
    return counts


def _outcome_status(priced: int, zero_summary: dict[str, Any], zero_loaded: bool) -> tuple[str, str, list[str]]:
    signal_count = _safe_int(zero_summary.get("signal_candidate_count"))
    exact_count = _safe_int(zero_summary.get("exact_candidate_count"))
    would_count = _safe_int(zero_summary.get("would_track_pick_count"))
    if priced > 0:
        return "monthly_exact_outcome_available", "use_monthly_profitability_audit_disposition", []
    if not zero_loaded:
        return (
            "zero_pick_replay_missing_for_lane",
            "refresh_all_lanes_zero_pick_audit",
            ["all_lanes_zero_pick_audit_missing_for_lane"],
        )
    if signal_count == 0 and exact_count == 0:
        return (
            "no_signal_candidates_in_monthly_window",
            "build_or_repair_lane_scan_hypothesis_before_pnl_replay",
            ["no_signal_candidates_for_lane_outcome_replay"],
        )
    if signal_count > 0 and exact_count == 0:
        return (
            "signal_candidates_without_exact_chain_native_spreads",
            "repair_chain_native_exact_candidate_selection",
            ["signals_without_exact_candidates"],
        )
    if exact_count > 0 and would_count == 0:
        return (
            "exact_candidates_without_selected_would_track_rows",
            "repair_lane_selection_or_guardrail_logging",
            ["exact_candidates_without_selected_outcomes"],
        )
    return (
        "selected_rows_missing_priced_outcomes",
        "audit_missing_lane_outcome_marks",
        ["selected_rows_need_exact_outcome_marks"],
    )


def _lane_rows(
    failure_modes: dict[str, Any],
    missed_outcome: dict[str, Any],
    lane_promotion_state: dict[str, Any],
    zero_pick_audit: dict[str, Any],
    lane_quarantine_archive: dict[str, Any],
) -> list[dict[str, Any]]:
    dispositions = _lane_disposition_map(failure_modes, lane_promotion_state, lane_quarantine_archive)
    leaderboard = {
        _norm(item.get("lane")): item
        for item in monthly_audit._lane_leaderboard(failure_modes)
        if isinstance(item, dict)
    }
    zero_lanes = _zero_pick_lane_map(zero_pick_audit)
    missed_counts = _tracked_outcome_counts(missed_outcome)
    rows = []
    for lane, disposition in sorted(dispositions.items()):
        lane_row = leaderboard.get(lane, {})
        zero_lane = _as_dict(zero_lanes.get(lane))
        zero_summary = _as_dict(zero_lane.get("summary"))
        priced = _safe_int(lane_row.get("priced"))
        outcome_status, next_action, blockers = _outcome_status(priced, zero_summary, bool(zero_lane))
        rows.append(
            {
                "lane": lane,
                "disposition": disposition.get("disposition"),
                "archive_status": disposition.get("archive_status"),
                "promotion_state": disposition.get("promotion_state"),
                "candidate_status": disposition.get("candidate_status"),
                "outcome_status": outcome_status,
                "next_action": next_action,
                "blockers": blockers,
                "monthly_rows": lane_row.get("rows"),
                "monthly_priced": lane_row.get("priced"),
                "monthly_profit_factor": lane_row.get("profit_factor"),
                "monthly_avg_net_pnl_pct": lane_row.get("avg_net_pnl_pct"),
                "monthly_median_net_pnl_pct": lane_row.get("median_net_pnl_pct"),
                "monthly_win_rate_pct": lane_row.get("win_rate_pct"),
                "monthly_net_pnl_usd": lane_row.get("sum_net_pnl_usd"),
                "missed_outcome_raw_rows": _as_dict(missed_counts.get(lane)).get("raw", 0),
                "missed_outcome_priced_rows": _as_dict(missed_counts.get(lane)).get("priced", 0),
                "missed_outcome_tracked_rows": _as_dict(missed_counts.get(lane)).get("tracked", 0),
                "zero_pick_status": zero_lane.get("status"),
                "zero_pick_date_count": zero_summary.get("date_count"),
                "zero_pick_signal_candidate_count": zero_summary.get("signal_candidate_count"),
                "zero_pick_exact_candidate_count": zero_summary.get("exact_candidate_count"),
                "zero_pick_would_track_pick_count": zero_summary.get("would_track_pick_count"),
                "zero_pick_no_exact_reason_counts": zero_summary.get("no_exact_reason_counts") or {},
                "zero_pick_signal_reject_reason_counts": zero_summary.get("signal_reject_reason_counts") or {},
            }
        )
    return rows


def _next_evidence_queue(lane_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = Counter(row["next_action"] for row in lane_rows if row.get("next_action") != "use_monthly_profitability_audit_disposition")
    priorities = {
        "refresh_all_lanes_zero_pick_audit": 3,
        "repair_chain_native_exact_candidate_selection": 4,
        "repair_lane_selection_or_guardrail_logging": 4,
        "audit_missing_lane_outcome_marks": 4,
        "build_or_repair_lane_scan_hypothesis_before_pnl_replay": 7,
    }
    reason_map = {
        "refresh_all_lanes_zero_pick_audit": "zero_pick_replay_missing_for_active_lane",
        "repair_chain_native_exact_candidate_selection": "signals_exist_but_no_exact_chain_native_spreads",
        "repair_lane_selection_or_guardrail_logging": "exact_candidates_exist_but_no_selected_outcome_rows",
        "audit_missing_lane_outcome_marks": "selected_rows_exist_without_priced_exact_outcomes",
        "build_or_repair_lane_scan_hypothesis_before_pnl_replay": "no_signal_candidates_in_monthly_window",
    }
    queue = [
        {
            "priority": priorities.get(action, 7),
            "action": action,
            "count": count,
            "reason": reason_map.get(action, action),
        }
        for action, count in sorted(grouped.items())
    ]
    queue.sort(key=lambda item: (_safe_int(item.get("priority")), _norm(item.get("action"))))
    return queue


def build_report(
    *,
    failure_modes_path: Path = DEFAULT_FAILURE_MODES,
    missed_outcome_path: Path = DEFAULT_MISSED_OUTCOME,
    lane_promotion_state_path: Path = DEFAULT_LANE_PROMOTION_STATE,
    zero_pick_audit_path: Path = DEFAULT_ZERO_PICK_AUDIT,
    lane_quarantine_archive_path: Path = DEFAULT_LANE_QUARANTINE_ARCHIVE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = {
        "missed_picks_failure_modes": failure_modes_path,
        "missed_picks_outcome": missed_outcome_path,
        "lane_promotion_state": lane_promotion_state_path,
        "all_lanes_zero_pick_audit": zero_pick_audit_path,
        "lane_quarantine_archive": lane_quarantine_archive_path,
    }
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], inputs[key] = _load_json(path)

    required = (
        "missed_picks_failure_modes",
        "missed_picks_outcome",
        "lane_promotion_state",
        "all_lanes_zero_pick_audit",
    )
    missing_required = [key for key in required if inputs[key]["status"] != "loaded"]
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())
    lane_rows = _lane_rows(
        reports["missed_picks_failure_modes"],
        reports["missed_picks_outcome"],
        reports["lane_promotion_state"],
        reports["all_lanes_zero_pick_audit"],
        reports["lane_quarantine_archive"],
    )
    status_counts = Counter(row["outcome_status"] for row in lane_rows)
    missing_rows = [row for row in lane_rows if row["outcome_status"] != "monthly_exact_outcome_available"]
    priced_rows = [row for row in lane_rows if row["outcome_status"] == "monthly_exact_outcome_available"]
    next_queue = _next_evidence_queue(lane_rows)

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    elif missing_rows:
        status = "lane_outcome_replay_readback"
        overall_status = "lane_outcome_replay_built_collecting"
    else:
        status = "lane_outcome_replay_readback"
        overall_status = "lane_outcome_replay_all_active_lanes_priced"

    blockers = []
    if missing_rows:
        blockers.append(f"missing_monthly_exact_outcome_rows_for_{len(missing_rows)}_lanes")
    blockers.extend(sorted({blocker for row in missing_rows for blocker in _as_list(row.get("blockers"))}))

    summary = {
        "overall_status": overall_status,
        "missing_required_inputs": missing_required,
        "active_lane_count": len(lane_rows),
        "priced_outcome_lane_count": len(priced_rows),
        "missing_outcome_lane_count": len(missing_rows),
        "outcome_status_counts": dict(sorted(status_counts.items())),
        "zero_pick_requested_lane_count": _as_dict(reports["all_lanes_zero_pick_audit"].get("summary")).get(
            "requested_lane_count"
        ),
        "zero_pick_completed_lane_count": _as_dict(reports["all_lanes_zero_pick_audit"].get("summary")).get(
            "completed_lane_count"
        ),
        "next_evidence_action_count": len(next_queue),
        "promotion_ready": False,
        "blockers": sorted(set(blockers)),
        "live_policy_change": live_policy_change,
    }
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_lane_outcome_replay",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only lane outcome coverage replay over active regular supervised lanes",
            "readback_is_not": "synthetic P&L, live scanner policy, broker recommendation, DB mutation, or lane promotion",
            "trusted_proof_standard": "monthly lane P&L requires exact priced outcome rows; lanes without rows stay unpriced and collecting",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "lane_outcome_table": lane_rows,
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
        "# Regular Options Lane Outcome Replay",
        "",
        "This report is generated from `scripts/build_regular_options_lane_outcome_replay.py`. It is a read-only lane-outcome coverage report and does not synthesize P&L for lanes without exact priced outcome rows.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Active lanes: `{summary.get('active_lane_count')}`.",
        f"- Priced outcome lanes: `{summary.get('priced_outcome_lane_count')}`.",
        f"- Missing outcome lanes: `{summary.get('missing_outcome_lane_count')}`.",
        f"- Outcome status counts: `{_json_inline(summary.get('outcome_status_counts') or {})}`.",
        f"- Zero-pick lanes completed: `{summary.get('zero_pick_completed_lane_count')}` / `{summary.get('zero_pick_requested_lane_count')}`.",
        f"- Next evidence actions: `{summary.get('next_evidence_action_count')}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Lane Outcome Table",
        "",
        "| Lane | Disposition | Outcome Status | Monthly Priced | PF | Avg Net | Net USD | Signals | Exact | Would Track | Next Action |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("lane_outcome_table")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("lane")),
                    f"`{_cell(row.get('disposition'))}`",
                    f"`{_cell(row.get('outcome_status'))}`",
                    _cell(row.get("monthly_priced")),
                    _cell(row.get("monthly_profit_factor")),
                    _cell(row.get("monthly_avg_net_pnl_pct")),
                    _cell(row.get("monthly_net_pnl_usd")),
                    _cell(row.get("zero_pick_signal_candidate_count")),
                    _cell(row.get("zero_pick_exact_candidate_count")),
                    _cell(row.get("zero_pick_would_track_pick_count")),
                    f"`{_cell(row.get('next_action'))}`",
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
            "This lane outcome replay is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or synthesize outcome P&L for lanes without exact priced rows.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options lane outcome replay.")
    parser.add_argument("--failure-modes", type=Path, default=DEFAULT_FAILURE_MODES)
    parser.add_argument("--missed-outcome", type=Path, default=DEFAULT_MISSED_OUTCOME)
    parser.add_argument("--lane-promotion-state", type=Path, default=DEFAULT_LANE_PROMOTION_STATE)
    parser.add_argument("--zero-pick-audit", type=Path, default=DEFAULT_ZERO_PICK_AUDIT)
    parser.add_argument("--lane-quarantine-archive", type=Path, default=DEFAULT_LANE_QUARANTINE_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        failure_modes_path=args.failure_modes,
        missed_outcome_path=args.missed_outcome,
        lane_promotion_state_path=args.lane_promotion_state,
        zero_pick_audit_path=args.zero_pick_audit,
        lane_quarantine_archive_path=args.lane_quarantine_archive,
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
