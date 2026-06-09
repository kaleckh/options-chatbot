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

REPORT_ID = "regular_options_overfit_rule_archive"

DEFAULT_FILTER_MATRIX = ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-overfit-rule-archive.md"

PROHIBITED_ACTIONS = (
    "do_not_delete_filter_matrix_scenarios_from_overfit_rule_archive",
    "do_not_change_scanner_policy_from_overfit_rule_archive",
    "do_not_change_lane_promotion_from_overfit_rule_archive",
    "do_not_submit_broker_order_from_overfit_rule_archive",
    "do_not_mutate_database_from_overfit_rule_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_overfit_rule_archive",
    "do_not_promote_rejected_rules_to_paper_or_live_proof",
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


def _archive_reason(blockers: list[str]) -> str:
    if "not_entry_time_only" in blockers:
        return "uses_non_entry_time_information"
    if "winner_damage_exceeds_deep_losses_avoided" in blockers:
        return "winner_damage_exceeds_deep_losses_avoided"
    if "overfit_status" in blockers:
        return "source_status_is_overfit_warning"
    if "thin_later_date_holdout" in blockers:
        return "thin_later_date_holdout"
    if "later_date_holdout_not_passed" in blockers:
        return "later_date_holdout_not_passed"
    return "failed_reject_overfit_gate"


def _archived_rules(filter_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rules = monthly_audit._candidate_rule_table(filter_matrix)
    archived = []
    for rule in rules:
        if rule.get("classification") != "reject_overfit":
            continue
        blockers = [str(item) for item in _as_list(rule.get("classification_blockers"))]
        archived.append(
            {
                "scenario_id": rule.get("scenario_id"),
                "archive_status": "archived_rejected_rule",
                "archive_reason": _archive_reason(blockers),
                "classification_blockers": blockers,
                "source_status": rule.get("source_status"),
                "entry_time_only": rule.get("entry_time_only"),
                "kept_count": rule.get("kept_count"),
                "blocked_count": rule.get("blocked_count"),
                "profit_factor": rule.get("profit_factor"),
                "avg_net_pnl_pct": rule.get("avg_net_pnl_pct"),
                "lost_winner_count": rule.get("lost_winner_count"),
                "avoided_lte_minus_50": rule.get("avoided_lte_minus_50"),
                "later_date_rows": rule.get("later_date_rows"),
                "survives_later_date_split": rule.get("survives_later_date_split"),
                "promotion_ready": False,
            }
        )
    archived.sort(
        key=lambda item: (
            _archive_reason([str(blocker) for blocker in _as_list(item.get("classification_blockers"))]),
            -(_safe_float(item.get("profit_factor")) or 0.0),
            _norm(item.get("scenario_id")),
        )
    )
    return archived


def build_report(
    *,
    filter_matrix_path: Path = DEFAULT_FILTER_MATRIX,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    filter_matrix, input_meta = _load_json(filter_matrix_path)
    missing_required = []
    if input_meta.get("status") != "loaded":
        missing_required.append("missed_picks_filter_matrix")
    live_policy_change = _has_live_policy_change(filter_matrix)

    rules = monthly_audit._candidate_rule_table(filter_matrix) if not missing_required else []
    archived = _archived_rules(filter_matrix) if not missing_required else []
    archived_ids = {str(item.get("scenario_id")) for item in archived}
    rejected_ids = {str(rule.get("scenario_id")) for rule in rules if rule.get("classification") == "reject_overfit"}
    unarchived = sorted(rejected_ids - archived_ids)

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "overfit_rule_archive_readback"
        overall_status = "overfit_rules_archived" if not unarchived else "overfit_rules_unarchived"

    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_rejected_candidate_rule_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "missing_required_inputs": missing_required,
            "candidate_rule_count": len(rules),
            "reject_overfit_rule_count": len(rejected_ids),
            "archived_reject_overfit_rule_count": len(archived_ids),
            "unarchived_reject_overfit_rule_count": len(unarchived),
            "paper_candidate_rule_count": sum(1 for rule in rules if rule.get("classification") == "paper_candidate_only"),
            "diagnostic_retest_rule_count": sum(1 for rule in rules if rule.get("classification") == "diagnostic_retest_required"),
            "archive_complete": bool(rejected_ids) and not unarchived,
            "unarchived_rule_ids": unarchived,
            "live_policy_change": live_policy_change,
        },
        "inputs": {"missed_picks_filter_matrix": input_meta},
        "archived_rules": archived,
        "non_archived_rules": [
            {
                "scenario_id": rule.get("scenario_id"),
                "classification": rule.get("classification"),
                "reason": "not_reject_overfit",
                "promotion_ready": False,
            }
            for rule in rules
            if rule.get("classification") != "reject_overfit"
        ],
        "proof_policy": {
            "readback_is": "read-only archive of rejected candidate filter rules that failed overfit, holdout, or winner-damage checks",
            "readback_is_not": "scenario deletion, scanner policy change, lane promotion, broker action, DB mutation, or proof-bar reduction",
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
        "# Regular Options Overfit Rule Archive",
        "",
        "This report is generated from `scripts/build_regular_options_overfit_rule_archive.py`. It is a read-only archive of candidate filter rules rejected for overfit, holdout, non-entry-time, or winner-damage reasons.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Candidate rules: `{summary.get('candidate_rule_count')}`.",
        f"- Rejected/overfit rules archived: `{summary.get('archived_reject_overfit_rule_count')}` / `{summary.get('reject_overfit_rule_count')}`.",
        f"- Unarchived rejected rules: `{_json_inline(summary.get('unarchived_rule_ids') or [])}`.",
        f"- Paper-candidate rules: `{summary.get('paper_candidate_rule_count')}`.",
        f"- Diagnostic retest rules: `{summary.get('diagnostic_retest_rule_count')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Rules",
        "",
        "| Scenario | Reason | Kept | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Rows | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rule in _as_list(report.get("archived_rules")):
        rule = _as_dict(rule)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(rule.get("scenario_id")),
                    _cell(rule.get("archive_reason")),
                    _cell(rule.get("kept_count")),
                    _cell(rule.get("profit_factor")),
                    _cell(rule.get("avg_net_pnl_pct")),
                    _cell(rule.get("lost_winner_count")),
                    _cell(rule.get("avoided_lte_minus_50")),
                    _cell(rule.get("later_date_rows")),
                    _cell(", ".join(str(item) for item in _as_list(rule.get("classification_blockers"))) or "none"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This archive is read-only. It does not delete filter-matrix scenarios, create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote rejected rules.",
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
    parser.add_argument("--filter-matrix", type=Path, default=DEFAULT_FILTER_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = build_report(filter_matrix_path=args.filter_matrix)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    return 0 if report["status"] in {"overfit_rule_archive_readback", "blocked_missing_inputs"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
