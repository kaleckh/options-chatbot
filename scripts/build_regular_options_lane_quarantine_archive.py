from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_monthly_all_lanes_profitability_audit as monthly_audit

REPORT_ID = "regular_options_lane_quarantine_archive"

DEFAULT_FAILURE_MODES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json"
DEFAULT_LANE_PROMOTION_STATE = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-lane-quarantine-archive.md"

PROHIBITED_ACTIONS = (
    "do_not_delete_or_disable_lanes_from_lane_quarantine_archive",
    "do_not_change_scanner_policy_from_lane_quarantine_archive",
    "do_not_change_lane_promotion_from_lane_quarantine_archive",
    "do_not_submit_broker_order_from_lane_quarantine_archive",
    "do_not_mutate_database_from_lane_quarantine_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_lane_quarantine_archive",
    "do_not_promote_quarantined_lanes_to_paper_or_live_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return str(value or "").strip()


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


def _archive_reason(row: dict[str, Any]) -> str:
    pf = _safe_float(row.get("profit_factor"))
    avg = _safe_float(row.get("avg_net_pnl_pct"))
    priced = int(row.get("priced") or 0)
    if priced >= 30 and avg is not None and avg < 0:
        return "negative_sufficient_sample_lane"
    if avg is not None and avg <= -20:
        return "severe_negative_average_pnl"
    if pf is not None and pf <= 0.3:
        return "profit_factor_at_or_below_quarantine_threshold"
    return "monthly_command_center_quarantine"


def _quarantine_dispositions(failure_modes: dict[str, Any], lane_promotion_state: dict[str, Any]) -> list[dict[str, Any]]:
    leaderboard = monthly_audit._lane_leaderboard(failure_modes)
    disposition = monthly_audit._lane_dispositions(leaderboard, lane_promotion_state, {"promotion_ready": False})
    archived = []
    for row in _as_list(disposition.get("dispositions")):
        row = _as_dict(row)
        if row.get("disposition") != "quarantine":
            continue
        archived.append(
            {
                "lane": row.get("lane"),
                "archive_status": "archived_quarantine_lane",
                "archive_reason": _archive_reason(row),
                "disposition": row.get("disposition"),
                "rows": row.get("rows"),
                "priced": row.get("priced"),
                "profit_factor": row.get("profit_factor"),
                "avg_net_pnl_pct": row.get("avg_net_pnl_pct"),
                "source_decision": row.get("source_decision"),
                "promotion_state": row.get("promotion_state"),
                "blockers": _as_list(row.get("blockers")),
                "operator_next_step": row.get("operator_next_step"),
                "promotion_ready": False,
            }
        )
    archived.sort(
        key=lambda item: (
            -(_safe_float(item.get("avg_net_pnl_pct")) or 0.0),
            _norm(item.get("lane")),
        )
    )
    return archived


def build_report(
    *,
    failure_modes_path: Path = DEFAULT_FAILURE_MODES,
    lane_promotion_state_path: Path = DEFAULT_LANE_PROMOTION_STATE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    failure_modes, failure_meta = _load_json(failure_modes_path)
    lane_state, lane_meta = _load_json(lane_promotion_state_path)
    missing_required = []
    if failure_meta.get("status") != "loaded":
        missing_required.append("missed_picks_failure_modes")
    if lane_meta.get("status") != "loaded":
        missing_required.append("lane_promotion_state")
    live_policy_change = _has_live_policy_change(failure_modes) or _has_live_policy_change(lane_state)

    archived = [] if missing_required else _quarantine_dispositions(failure_modes, lane_state)
    archived_ids = {_norm(item.get("lane")) for item in archived}

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "lane_quarantine_archive_readback"
        overall_status = "lane_quarantines_archived" if archived else "no_quarantine_lanes_to_archive"

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_negative_lane_quarantine_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "missing_required_inputs": missing_required,
            "quarantine_lane_count": len(archived),
            "archived_quarantine_lane_count": len(archived_ids),
            "unarchived_quarantine_lane_count": 0,
            "archive_complete": not missing_required and not live_policy_change,
            "archived_lane_ids": sorted(archived_ids),
            "live_policy_change": live_policy_change,
        },
        "inputs": {
            "missed_picks_failure_modes": failure_meta,
            "lane_promotion_state": lane_meta,
        },
        "archived_lanes": archived,
        "proof_policy": {
            "readback_is": "read-only archive of monthly command-center lanes classified as quarantine by trusted exact outcome economics",
            "readback_is_not": "lane deletion, scanner policy change, lane promotion change, broker action, DB mutation, or proof-bar reduction",
            "trusted_proof_standard": "trusted intraday exact-contract OPRA/NBBO evidence remains required for proof claims",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
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
        "# Regular Options Lane Quarantine Archive",
        "",
        "This report is generated from `scripts/build_regular_options_lane_quarantine_archive.py`. It is a read-only archive for lanes the monthly command center has already classified as `quarantine` from trusted exact outcome economics.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Archived quarantine lanes: `{summary.get('archived_quarantine_lane_count')}` / `{summary.get('quarantine_lane_count')}`.",
        f"- Archived lane IDs: `{_json_inline(summary.get('archived_lane_ids') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Lanes",
        "",
        "| Lane | Reason | Priced | PF | Avg Net | Promotion State | Source Decision | Next Step |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for lane in _as_list(report.get("archived_lanes")):
        lane = _as_dict(lane)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(lane.get("lane")),
                    _cell(lane.get("archive_reason")),
                    _cell(lane.get("priced")),
                    _cell(lane.get("profit_factor")),
                    _cell(lane.get("avg_net_pnl_pct")),
                    _cell(lane.get("promotion_state")),
                    _cell(lane.get("source_decision")),
                    _cell(lane.get("operator_next_step")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This archive is read-only. It does not delete or disable lanes, create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote quarantined lanes.",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure-modes", type=Path, default=DEFAULT_FAILURE_MODES)
    parser.add_argument("--lane-promotion-state", type=Path, default=DEFAULT_LANE_PROMOTION_STATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = build_report(
        failure_modes_path=args.failure_modes,
        lane_promotion_state_path=args.lane_promotion_state,
    )
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    return 0 if report["status"] in {"lane_quarantine_archive_readback", "blocked_missing_inputs"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
