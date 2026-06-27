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

from scripts import build_regular_options_strict_forward_30_exit_completion_stager as exit_stager
from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report


REPORT_ID = "regular_options_strict_forward_30_exit_evidence_plan"
DEFAULT_LATEST_JSON = ROOT / "data" / "forward-tracking" / f"{REPORT_ID}_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-exit-evidence-plan.md"

REQUIRED_EXIT_EVIDENCE_FIELDS = [
    "selection_id",
    "exit_quote_source",
    "exit_quote_timestamp_utc",
    "exit_bid",
    "exit_ask",
    "policy_exit_condition",
    "net_pnl_usd",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_source_count(value: Any) -> int:
    return int(value.get("row_count") or 0) if isinstance(value, dict) else 0


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return exit_stager._load_jsonl(path)


def _selection_id(row: dict[str, Any]) -> str:
    return exit_stager._selection_id(row)


def _contract_key(row: dict[str, Any]) -> str:
    direct = _norm(row.get("contract_or_spread_key"))
    if direct:
        return direct
    long_symbol = _norm(row.get("long_contract_symbol") or row.get("contract_symbol"))
    short_symbol = _norm(row.get("short_contract_symbol"))
    return f"{long_symbol}/{short_symbol}" if long_symbol and short_symbol else long_symbol


def _existing_evidence_by_selection(evidence_rows: list[dict[str, Any]]) -> tuple[dict[str, int], Counter[str]]:
    counts: dict[str, int] = {}
    missing_or_duplicate: Counter[str] = Counter()
    seen: set[str] = set()
    for row in evidence_rows:
        selection_id = _norm(row.get("selection_id") or row.get("source_selection_id"))
        if not selection_id:
            missing_or_duplicate["missing_selection_id"] += 1
            continue
        counts[selection_id] = counts.get(selection_id, 0) + 1
        if selection_id in seen:
            missing_or_duplicate["duplicate_selection_id"] += 1
        seen.add(selection_id)
    return counts, missing_or_duplicate


def _evidence_template(open_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_id": _selection_id(open_row),
        "exit_quote_source": "opra_nbbo_or_other_trusted_executable_source",
        "exit_quote_timestamp_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exit_bid": "spread_or_single_leg_executable_bid",
        "exit_ask": "spread_or_single_leg_executable_ask",
        "policy_exit_condition": "policy_exit_at_profit_target_or_stop_loss_or_time_exit",
        "net_pnl_usd": "realized_net_pnl_usd_from_entry_to_exit",
        "market_window_status": "open",
        "captured_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
    }


def _requirement_row(open_row: dict[str, Any], *, existing_evidence_count: int) -> dict[str, Any]:
    return {
        "selection_id": _selection_id(open_row),
        "open_row_id": _norm(open_row.get("row_id")),
        "lane_id": _norm(open_row.get("lane_id")),
        "ticker": _norm(open_row.get("ticker")),
        "selection_date": _norm(open_row.get("selection_date")),
        "selection_timestamp_utc": _norm(open_row.get("selection_timestamp_utc")),
        "contract_or_spread_key": _contract_key(open_row),
        "long_contract_symbol": _norm(open_row.get("long_contract_symbol")),
        "short_contract_symbol": _norm(open_row.get("short_contract_symbol")),
        "entry_quote_source": _norm(open_row.get("entry_quote_source")),
        "entry_quote_timestamp_utc": _norm(open_row.get("entry_quote_timestamp_utc")),
        "entry_bid": open_row.get("entry_bid"),
        "entry_ask": open_row.get("entry_ask"),
        "existing_exit_evidence_rows": existing_evidence_count,
        "required_exit_evidence_fields": list(REQUIRED_EXIT_EVIDENCE_FIELDS),
        "policy_rule": "Capture exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence.",
        "exit_evidence_template": _evidence_template(open_row),
    }


def build_report(
    *,
    cohort_log_path: Path = forward_report.DEFAULT_PHASE2_COHORT_LOG,
    exit_evidence_path: Path = exit_stager.DEFAULT_EVIDENCE_PATH,
    latest_json_path: Path = DEFAULT_LATEST_JSON,
    docs_report_path: Path = DEFAULT_DOCS_REPORT,
    no_write: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    cohort_rows, cohort_source = forward_report._load_jsonl(cohort_log_path)
    evidence_rows, evidence_source = _load_jsonl(exit_evidence_path)
    open_rows, completed_selections, duplicate_completed = exit_stager._open_rows_by_selection(cohort_rows)
    evidence_counts, evidence_shape_counts = _existing_evidence_by_selection(evidence_rows)

    requirements = [
        _requirement_row(open_row, existing_evidence_count=evidence_counts.get(selection_id, 0))
        for selection_id, open_row in sorted(open_rows.items())
        if selection_id not in completed_selections
    ]
    with_existing_evidence = sum(1 for row in requirements if int(row.get("existing_exit_evidence_rows") or 0) > 0)

    if cohort_source.get("status") != "loaded" or not cohort_rows:
        status = "exit_evidence_plan_waiting_for_open_forward_rows"
    elif not requirements:
        status = "exit_evidence_plan_no_open_rows"
    elif with_existing_evidence:
        status = "exit_evidence_plan_existing_evidence_review_needed"
    else:
        status = "exit_evidence_plan_waiting_for_policy_exit_evidence"

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "read_only": bool(no_write),
        "cohort_log_path": _rel(cohort_log_path),
        "exit_evidence_path": _rel(exit_evidence_path),
        "cohort_source": cohort_source,
        "exit_evidence_source": evidence_source,
        "open_forward_entry_count": len(open_rows),
        "existing_completed_selection_count": len(completed_selections),
        "duplicate_completed_selection_count": len(duplicate_completed),
        "pending_exit_evidence_count": len(requirements),
        "open_rows_with_existing_evidence_count": with_existing_evidence,
        "exit_evidence_rows_present_count": _safe_source_count(evidence_source),
        "required_exit_evidence_fields": list(REQUIRED_EXIT_EVIDENCE_FIELDS),
        "trusted_executable_quote_sources": sorted(forward_report.TRUSTED_EXECUTABLE_QUOTE_SOURCES),
        "exit_requirements": requirements,
        "evidence_shape_counts": dict(sorted(evidence_shape_counts.items())),
        "exit_completion_stager_command": "npm run options:goal-loop:strict-forward-30-exit-completion-stager -- --json",
        "guarded_append_after_staging_template": (
            "npm run options:append:phase2-forward-paper-shadow -- "
            "data/forward-tracking/phase2_regular_options_forward_paper_shadow_exit_completion_candidate_rows.jsonl "
            "--approval-token APPROVE_PHASE2_FORWARD_COHORT_APPEND --market-window-confirmed"
        ),
        "writes_performed": [],
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_mutation_allowed": False,
        "cohort_append_performed": False,
        "promotion_ready": False,
        "proof_bars_changed": False,
        "historical_rows_are_forward_proof": False,
        "prohibited_actions": [
            "do_not_append_from_exit_evidence_plan",
            "do_not_write_exit_evidence_from_exit_evidence_plan",
            "do_not_import_quotes_from_exit_evidence_plan",
            "do_not_enable_live_validation_from_exit_evidence_plan",
            "do_not_enable_auto_track_from_exit_evidence_plan",
            "do_not_submit_broker_orders_from_exit_evidence_plan",
            "do_not_force_policy_exit_to_manufacture_evidence",
            "do_not_lower_proof_bars_from_exit_evidence_plan",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
    }
    if not no_write:
        latest_json_path.parent.mkdir(parents=True, exist_ok=True)
        docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        docs_report_path.write_text(render_markdown(report) + "\n", encoding="utf8")
        report["writes_performed"].extend([_rel(latest_json_path), _rel(docs_report_path)])
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Strict Forward 30 Exit Evidence Plan",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Open forward entries: `{report.get('open_forward_entry_count')}`.",
        f"- Pending exit-evidence rows: `{report.get('pending_exit_evidence_count')}`.",
        f"- Open rows with existing evidence: `{report.get('open_rows_with_existing_evidence_count')}`.",
        f"- Exit evidence path: `{report.get('exit_evidence_path')}`.",
        f"- Required fields: `{json.dumps(report.get('required_exit_evidence_fields'))}`.",
        "",
        "This plan is read-only. It lists exact-exit evidence requirements for already-open Phase 2 forward rows and does not write evidence, append cohort rows, import quotes, enable live validation, auto-track positions, submit broker orders, lower proof bars, or count historical rows as forward proof.",
        "",
    ]
    requirements = report.get("exit_requirements")
    if isinstance(requirements, list) and requirements:
        lines.extend(["## Open Rows", ""])
        for row in requirements[:20]:
            lines.append(
                f"- `{row.get('selection_id')}` `{row.get('ticker')}` `{row.get('contract_or_spread_key')}` "
                f"existing_evidence=`{row.get('existing_exit_evidence_rows')}`."
            )
        if len(requirements) > 20:
            lines.append(f"- ... `{len(requirements) - 20}` additional open rows omitted from markdown.")
        lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only Phase 2 strict-forward exit-evidence plan.")
    parser.add_argument("--cohort-log", type=Path, default=forward_report.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--exit-evidence", type=Path, default=exit_stager.DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--latest-json", type=Path, default=DEFAULT_LATEST_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        cohort_log_path=args.cohort_log,
        exit_evidence_path=args.exit_evidence,
        latest_json_path=args.latest_json,
        docs_report_path=args.docs_report,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
