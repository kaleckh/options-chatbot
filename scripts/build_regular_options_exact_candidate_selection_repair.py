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


REPORT_ID = "regular_options_exact_candidate_selection_repair"

DEFAULT_LANE_OUTCOME_REPLAY = ROOT / "data" / "forward-tracking" / "regular_options_lane_outcome_replay_latest.json"
DEFAULT_ZERO_PICK_AUDIT = ROOT / "data" / "forward-tracking" / "all_lanes_zero_pick_current_algo_audit_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-exact-candidate-selection-repair.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_exact_candidate_selection_repair",
    "do_not_submit_broker_order_from_exact_candidate_selection_repair",
    "do_not_mutate_database_from_exact_candidate_selection_repair",
    "do_not_change_scanner_policy_from_exact_candidate_selection_repair",
    "do_not_change_contract_selection_policy_from_exact_candidate_selection_repair",
    "do_not_change_lane_promotion_from_exact_candidate_selection_repair",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_exact_candidate_selection_repair",
    "do_not_synthesize_pnl_for_signal_only_rows",
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
        lane = _as_dict(lane)
        playbook = _norm(lane.get("playbook"))
        if playbook:
            lanes[playbook] = lane
    return lanes


def _target_lanes(lane_outcome_replay: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _as_list(lane_outcome_replay.get("lane_outcome_table")):
        row = _as_dict(row)
        if row.get("outcome_status") != "signal_candidates_without_exact_chain_native_spreads":
            continue
        rows.append(row)
    rows.sort(key=lambda item: _norm(item.get("lane")))
    return rows


def _target_rows(lane_outcome_replay: dict[str, Any], zero_pick_audit: dict[str, Any]) -> list[dict[str, Any]]:
    zero_lanes = _zero_pick_lane_map(zero_pick_audit)
    targets: list[dict[str, Any]] = []
    for lane_row in _target_lanes(lane_outcome_replay):
        lane = _norm(lane_row.get("lane"))
        zero_lane = _as_dict(zero_lanes.get(lane))
        for date_row in _as_list(zero_lane.get("dates")):
            date_row = _as_dict(date_row)
            signal_count = _safe_int(date_row.get("signal_candidate_count"))
            exact_count = _safe_int(date_row.get("exact_candidate_count"))
            if signal_count <= 0 or exact_count > 0:
                continue
            exact_reject_reasons = _as_dict(date_row.get("exact_reject_reasons"))
            top_signal_tickers = [_norm(item) for item in _as_list(date_row.get("top_signal_tickers")) if _norm(item)]
            target_id = f"{lane}:{_norm(date_row.get('scan_date'))}"
            targets.append(
                {
                    "target_id": target_id,
                    "lane": lane,
                    "disposition": lane_row.get("disposition"),
                    "scan_date": date_row.get("scan_date"),
                    "signal_candidate_count": signal_count,
                    "exact_candidate_count": exact_count,
                    "would_track_pick_count": _safe_int(date_row.get("selected_count") or date_row.get("would_track_pick_count")),
                    "top_signal_tickers": top_signal_tickers,
                    "exact_reject_reasons": exact_reject_reasons,
                    "primary_repair_reason": next(iter(exact_reject_reasons.keys()), "signals_without_exact_candidates"),
                    "next_action": "build_chain_native_filter_relaxation_replay",
                    "operator_next_step": (
                        "Run a read-only chain-native filter relaxation replay for this lane/date/ticker set; "
                        "do not change live contract selection until exact OPRA/NBBO and promotion gates pass."
                    ),
                }
            )
    targets.sort(key=lambda item: (_norm(item.get("lane")), _norm(item.get("scan_date"))))
    return targets


def _next_evidence_queue(target_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not target_rows:
        return []
    reason_counts = Counter()
    lane_counts = Counter()
    for row in target_rows:
        reason_counts[_norm(row.get("primary_repair_reason")) or "signals_without_exact_candidates"] += 1
        lane_counts[_norm(row.get("lane"))] += 1
    return [
        {
            "priority": 4,
            "action": "build_chain_native_filter_relaxation_replay",
            "count": len(target_rows),
            "reason": ", ".join(f"{key}:{value}" for key, value in sorted(reason_counts.items())),
            "operator_next_step": "Replay the listed lane/date/ticker signal set with diagnostic chain-native filter attribution only.",
            "target_lanes": sorted(lane_counts),
        }
    ]


def build_report(
    *,
    lane_outcome_replay_path: Path = DEFAULT_LANE_OUTCOME_REPLAY,
    zero_pick_audit_path: Path = DEFAULT_ZERO_PICK_AUDIT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in {
        "lane_outcome_replay": lane_outcome_replay_path,
        "all_lanes_zero_pick_audit": zero_pick_audit_path,
    }.items():
        reports[key], inputs[key] = _load_json(path)

    missing_required = [key for key, meta in inputs.items() if meta["status"] != "loaded"]
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())
    target_rows = _target_rows(reports["lane_outcome_replay"], reports["all_lanes_zero_pick_audit"])
    next_queue = _next_evidence_queue(target_rows)

    reason_counts = Counter()
    ticker_counts = Counter()
    signal_count = 0
    for row in target_rows:
        signal_count += _safe_int(row.get("signal_candidate_count"))
        for reason, count in _as_dict(row.get("exact_reject_reasons")).items():
            reason_counts[_norm(reason)] += _safe_int(count)
        for ticker in _as_list(row.get("top_signal_tickers")):
            ticker_counts[_norm(ticker)] += 1

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    elif target_rows:
        status = "exact_candidate_selection_repair_readback"
        overall_status = "exact_candidate_selection_repair_targets_ready"
    else:
        status = "exact_candidate_selection_repair_readback"
        overall_status = "exact_candidate_selection_repair_no_targets"

    blockers = []
    if target_rows:
        blockers.append("chain_native_filter_relaxation_replay_missing")
        blockers.extend(sorted(reason for reason in reason_counts if reason))

    summary = {
        "overall_status": overall_status,
        "missing_required_inputs": missing_required,
        "target_lane_count": len({row["lane"] for row in target_rows}),
        "target_date_count": len(target_rows),
        "target_signal_candidate_count": signal_count,
        "target_exact_candidate_count": sum(_safe_int(row.get("exact_candidate_count")) for row in target_rows),
        "target_would_track_count": sum(_safe_int(row.get("would_track_pick_count")) for row in target_rows),
        "exact_reject_reason_counts": dict(sorted(reason_counts.items())),
        "top_signal_tickers": sorted(ticker for ticker in ticker_counts if ticker),
        "next_evidence_action_count": len(next_queue),
        "promotion_ready": False,
        "blockers": sorted(set(blockers)),
        "live_policy_change": live_policy_change,
    }
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_exact_candidate_selection_repair",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only repair target list for signal candidates that produced zero exact chain-native spread candidates",
            "readback_is_not": "scanner policy, contract-selection policy, broker recommendation, DB mutation, lane promotion, or P&L proof",
            "trusted_proof_standard": "future replay P&L requires exact OPRA/NBBO entry and exit bid/ask evidence; this report only targets missing exact-candidate selection",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "repair_targets": target_rows,
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
        "# Regular Options Exact Candidate Selection Repair",
        "",
        "This report is generated from `scripts/build_regular_options_exact_candidate_selection_repair.py`. It is a read-only repair target list for lanes with signal candidates but zero exact chain-native spread candidates.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Target lanes: `{summary.get('target_lane_count')}`.",
        f"- Target dates: `{summary.get('target_date_count')}`.",
        f"- Signal candidates: `{summary.get('target_signal_candidate_count')}`.",
        f"- Exact candidates: `{summary.get('target_exact_candidate_count')}`.",
        f"- Would-track rows: `{summary.get('target_would_track_count')}`.",
        f"- Exact reject reasons: `{_json_inline(summary.get('exact_reject_reason_counts') or {})}`.",
        f"- Top signal tickers: `{_json_inline(summary.get('top_signal_tickers') or [])}`.",
        f"- Next evidence actions: `{summary.get('next_evidence_action_count')}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Repair Targets",
        "",
        "| Lane | Scan Date | Signals | Exact | Would Track | Tickers | Exact Reject Reasons | Next Action |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in _as_list(report.get("repair_targets")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("lane")),
                    _cell(row.get("scan_date")),
                    _cell(row.get("signal_candidate_count")),
                    _cell(row.get("exact_candidate_count")),
                    _cell(row.get("would_track_pick_count")),
                    _json_inline(row.get("top_signal_tickers") or []),
                    _json_inline(row.get("exact_reject_reasons") or {}),
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
            "This exact-candidate selection repair is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, lower exact OPRA/NBBO proof bars, or synthesize P&L for signal-only rows.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options exact candidate selection repair.")
    parser.add_argument("--lane-outcome-replay", type=Path, default=DEFAULT_LANE_OUTCOME_REPLAY)
    parser.add_argument("--zero-pick-audit", type=Path, default=DEFAULT_ZERO_PICK_AUDIT)
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
