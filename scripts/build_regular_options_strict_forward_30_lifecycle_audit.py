from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report


REPORT_ID = "regular_options_strict_forward_30_lifecycle_audit"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-lifecycle-audit.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _selection_identity(row: dict[str, Any], index: int) -> str:
    return _norm(row.get("selection_id") or row.get("row_id") or f"row-index:{index}")


def _group_lifecycle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_selection: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_selection[_selection_identity(row, index)].append(row)

    waiting: list[str] = []
    completed: list[str] = []
    completion_rows_after_entry: list[str] = []
    exact_exit_without_entry: list[str] = []
    malformed_lifecycle: list[str] = []
    for selection_id, selection_rows in sorted(by_selection.items()):
        statuses = [_norm_lower(row.get("denominator_status")) for row in selection_rows]
        has_entry = any(status in {"exact_entry_captured", "open_waiting_policy_exit"} for status in statuses)
        has_exit = "exact_exit_captured" in statuses
        if has_exit:
            completed.append(selection_id)
            if has_entry:
                completion_rows_after_entry.append(selection_id)
            else:
                exact_exit_without_entry.append(selection_id)
        elif has_entry:
            waiting.append(selection_id)
        if len([status for status in statuses if status == "exact_exit_captured"]) > 1:
            malformed_lifecycle.append(selection_id)
    return {
        "selection_count": len(by_selection),
        "waiting_for_exact_exit_selection_ids": waiting,
        "completed_selection_ids": completed,
        "completion_rows_after_entry_selection_ids": completion_rows_after_entry,
        "exact_exit_without_prior_entry_selection_ids": exact_exit_without_entry,
        "malformed_duplicate_exact_exit_selection_ids": malformed_lifecycle,
    }


def _status_for(
    *,
    rows_loaded: bool,
    strict_rows: int,
    required_rows: int,
    accepted_profitability: bool,
    lifecycle: dict[str, Any],
    hard_fail_states: list[str],
) -> str:
    if strict_rows >= required_rows and accepted_profitability:
        return "lifecycle_goal_complete"
    if _as_list(lifecycle.get("malformed_duplicate_exact_exit_selection_ids")):
        return "lifecycle_duplicate_exact_exit_blocked"
    if hard_fail_states:
        return "lifecycle_protocol_failed"
    if not rows_loaded:
        return "lifecycle_waiting_for_first_entry_row"
    if _as_list(lifecycle.get("waiting_for_exact_exit_selection_ids")):
        return "lifecycle_waiting_for_policy_exit_evidence"
    if strict_rows < required_rows:
        return "lifecycle_waiting_for_additional_entry_rows"
    return "lifecycle_waiting_for_profitability_acceptance"


def build_report(
    *,
    cohort_log_path: Path = forward_report.DEFAULT_PHASE2_COHORT_LOG,
    schema_path: Path = forward_report.DEFAULT_PHASE2_SCHEMA,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    rows, source = forward_report._load_jsonl(cohort_log_path)
    phase2_report = forward_report.build_report(
        cohort_log_path=cohort_log_path,
        schema_path=schema_path,
        allowed_lane_ids=forward_report.PHASE2_FROZEN_LANE_IDS,
        generated_at_utc=generated_at,
    )
    acceptance = _as_dict(phase2_report.get("acceptance_readiness"))
    counts = _as_dict(phase2_report.get("counts"))
    lifecycle = _group_lifecycle(rows)
    strict_rows = _int(acceptance.get("post_freeze_strict_exact_completed_rows"))
    required_rows = _int(acceptance.get("minimum_required"), forward_report.MIN_COMPLETED_ROWS_FOR_REVIEW)
    hard_fail_states = _as_list(phase2_report.get("hard_fail_states"))
    accepted_profitability = bool(
        _as_dict(phase2_report.get("gates")).get("minimum_continuation_gate_passed")
        and acceptance.get("positive_net_usd_pnl")
        and not hard_fail_states
    )
    status = _status_for(
        rows_loaded=source.get("status") == "loaded" and bool(rows),
        strict_rows=strict_rows,
        required_rows=required_rows,
        accepted_profitability=accepted_profitability,
        lifecycle=lifecycle,
        hard_fail_states=hard_fail_states,
    )
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "read_only": True,
        "cohort_log_path": _rel(cohort_log_path),
        "cohort_source": source,
        "cohort_log_state": phase2_report.get("cohort_log_state"),
        "phase2_overall_status": phase2_report.get("overall_status"),
        "strict_forward_rows": strict_rows,
        "required_rows": required_rows,
        "remaining_rows": max(required_rows - strict_rows, 0),
        "accepted_profitability": accepted_profitability,
        "total_natural_selections": _int(counts.get("total_natural_selections")),
        "open_waiting_policy_exit_count": _int(counts.get("open_waiting_policy_exit_count")),
        "exact_completed_forward_pnl_count": _int(counts.get("exact_completed_forward_pnl_count")),
        "lifecycle": {
            **lifecycle,
            "waiting_for_exact_exit_count": len(_as_list(lifecycle.get("waiting_for_exact_exit_selection_ids"))),
            "completed_selection_count": len(_as_list(lifecycle.get("completed_selection_ids"))),
            "completion_rows_after_entry_count": len(_as_list(lifecycle.get("completion_rows_after_entry_selection_ids"))),
            "exact_exit_without_prior_entry_count": len(_as_list(lifecycle.get("exact_exit_without_prior_entry_selection_ids"))),
            "malformed_duplicate_exact_exit_count": len(_as_list(lifecycle.get("malformed_duplicate_exact_exit_selection_ids"))),
        },
        "append_only_completion_policy": {
            "open_entry_rows_may_be_completed_by_later_exact_exit_rows": True,
            "completion_rows_must_use_unique_row_id": True,
            "completion_rows_should_reuse_selection_id": True,
            "exact_exit_rows_still_require_candidate_validation_and_guarded_append": True,
            "historical_rows_are_not_forward_proof": True,
        },
        "next_actions": {
            "lifecycle_waiting_for_first_entry_row": "wait_for_real_market_window_phase2_entry_candidates",
            "lifecycle_waiting_for_policy_exit_evidence": "stage_exact_exit_candidate_rows_only_when_policy_exit_and_trusted_exit_quotes_exist",
            "lifecycle_waiting_for_additional_entry_rows": "continue_scheduled_forward_collection",
            "lifecycle_goal_complete": "verify_completion_monitor_then_close_goal",
        },
        "hard_fail_states": hard_fail_states,
        "warning_states": _as_list(phase2_report.get("warning_states")),
        "prohibited_actions": [
            "do_not_append_from_lifecycle_audit",
            "do_not_enable_live_validation_from_lifecycle_audit",
            "do_not_enable_auto_track_from_lifecycle_audit",
            "do_not_submit_broker_orders_from_lifecycle_audit",
            "do_not_import_quotes_from_lifecycle_audit",
            "do_not_lower_proof_bars_from_lifecycle_audit",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
        "phase2_forward_report": phase2_report,
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lifecycle = _as_dict(report.get("lifecycle"))
    return "\n".join(
        [
            "# Regular Options Strict Forward 30 Lifecycle Audit",
            "",
            f"Status: `{report.get('status')}`.",
            "",
            f"- Strict completed forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
            f"- Remaining rows: `{report.get('remaining_rows')}`.",
            f"- Accepted profitability: `{str(bool(report.get('accepted_profitability'))).lower()}`.",
            f"- Cohort log state: `{report.get('cohort_log_state')}`.",
            f"- Selections waiting for exact exit: `{lifecycle.get('waiting_for_exact_exit_count')}`.",
            f"- Completed selections: `{lifecycle.get('completed_selection_count')}`.",
            f"- Completion rows after entry rows: `{lifecycle.get('completion_rows_after_entry_count')}`.",
            f"- Duplicate exact-exit selections: `{lifecycle.get('malformed_duplicate_exact_exit_count')}`.",
            "",
            "This audit is read-only. It clarifies the append-only lifecycle from exact-entry/open rows to later exact-exit rows, but it does not append rows, enable live validation, enable auto-track, submit broker orders, import quotes, lower proof bars, or count historical rows as forward proof.",
            "",
        ]
    )


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
    payload = dict(report)
    payload["artifacts"] = artifacts
    text = render_markdown(payload)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(text, encoding="utf8")
    latest_md.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only lifecycle audit for strict-forward 30-row Phase 2 cohort.")
    parser.add_argument("--cohort-log", type=Path, default=forward_report.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--schema", type=Path, default=forward_report.DEFAULT_PHASE2_SCHEMA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(cohort_log_path=args.cohort_log, schema_path=args.schema)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] not in {"lifecycle_protocol_failed", "lifecycle_duplicate_exact_exit_blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
