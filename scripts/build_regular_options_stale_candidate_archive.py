from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_stale_candidate_archive"

DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-stale-candidate-archive.md"

TARGET_ACTION = "wait_for_fresh_match_or_archive_candidate"
ARCHIVED_STATUS = "archived_no_longer_matched_candidate"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_stale_candidate_archive",
    "do_not_submit_broker_order_from_stale_candidate_archive",
    "do_not_mutate_database_from_stale_candidate_archive",
    "do_not_change_scanner_policy_from_stale_candidate_archive",
    "do_not_change_lane_promotion_from_stale_candidate_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_stale_candidate_archive",
    "do_not_chase_no_longer_matched_candidates_without_fresh_executable_match",
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


def _target_rows(candidate_ledger: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _as_list(candidate_ledger.get("ledger_rows")):
        if not isinstance(row, dict):
            continue
        if _norm(row.get("next_evidence_action")) != TARGET_ACTION:
            continue
        validation_outcome = _norm(row.get("validation_outcome"))
        archive_status = ARCHIVED_STATUS if validation_outcome == "no_longer_matched" else "archive_review_required"
        rows.append(
            {
                "archive_status": archive_status,
                "ledger_key": row.get("ledger_key"),
                "candidate_key": row.get("candidate_key"),
                "scan_date": row.get("scan_date"),
                "ticker": row.get("ticker") or row.get("symbol"),
                "lane_id": row.get("lane_id") or row.get("playbook_id"),
                "direction": row.get("direction"),
                "expiry": row.get("expiry"),
                "contract_symbol": row.get("contract_symbol"),
                "short_contract_symbol": row.get("short_contract_symbol"),
                "candidate_status": row.get("candidate_status"),
                "validation_outcome": row.get("validation_outcome"),
                "action_reason": row.get("action_reason"),
                "entry_evidence_status": row.get("entry_evidence_status"),
                "fill_attempt_status": row.get("fill_attempt_status"),
                "position_link_status": row.get("position_link_status"),
                "realized_pnl_status": row.get("realized_pnl_status"),
                "promotion_discussion_ready": bool(row.get("promotion_discussion_ready")),
                "production_proof_ready": False,
                "blockers": _as_list(row.get("blocking_reasons")),
                "required_next_evidence": _as_list(row.get("required_next_evidence")),
                "operator_next_step": (
                    "Archive as no-longer-matched read-only evidence; require a fresh executable exact match before reconsidering."
                    if archive_status == ARCHIVED_STATUS
                    else "Review this stale-candidate row before archival because it is not explicitly no-longer-matched."
                ),
            }
        )
    rows.sort(key=lambda item: (_norm(item.get("scan_date")), _norm(item.get("lane_id")), _norm(item.get("ticker"))))
    return rows


def _next_evidence_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_count = sum(1 for row in rows if row.get("archive_status") != ARCHIVED_STATUS)
    if not review_count:
        return []
    return [
        {
            "priority": 8,
            "action": "review_stale_candidate_archive_exceptions",
            "count": review_count,
            "reason": "stale_candidate_rows_not_explicitly_no_longer_matched",
            "operator_next_step": "Review exception rows before archiving; do not create trades or treat stale candidates as proof.",
        }
    ]


def build_report(
    *,
    candidate_ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    candidate_ledger, input_meta = _load_json(candidate_ledger_path)
    missing_required = [] if input_meta.get("status") == "loaded" else ["regular_options_candidate_outcome_ledger"]
    live_policy_change = _has_live_policy_change(candidate_ledger)
    rows = _target_rows(candidate_ledger)
    next_queue = _next_evidence_queue(rows)
    archived = [row for row in rows if row.get("archive_status") == ARCHIVED_STATUS]
    exceptions = [row for row in rows if row.get("archive_status") != ARCHIVED_STATUS]
    lane_counts = Counter(_norm(row.get("lane_id")) for row in rows if _norm(row.get("lane_id")))
    ticker_counts = Counter(_norm(row.get("ticker")) for row in rows if _norm(row.get("ticker")))
    status_counts = Counter(_norm(row.get("archive_status")) for row in rows if _norm(row.get("archive_status")))

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    elif rows and not exceptions:
        status = "stale_candidate_archive_readback"
        overall_status = "stale_candidates_archived"
    elif rows:
        status = "stale_candidate_archive_readback"
        overall_status = "stale_candidate_archive_review_required"
    else:
        status = "stale_candidate_archive_readback"
        overall_status = "stale_candidate_archive_no_targets"

    blockers = []
    if exceptions:
        blockers.append("stale_candidate_archive_exceptions_require_review")
    if rows:
        blockers.append("fresh_executable_match_required_for_reactivation")

    summary = {
        "overall_status": overall_status,
        "missing_required_inputs": missing_required,
        "source_wait_or_archive_count": len(rows),
        "archived_no_longer_matched_candidate_count": len(archived),
        "archive_exception_count": len(exceptions),
        "archive_complete": bool(rows) and not exceptions and not live_policy_change and not missing_required,
        "lane_counts": dict(sorted(lane_counts.items())),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "archive_status_counts": dict(sorted(status_counts.items())),
        "production_proof_ready_count": 0,
        "promotion_ready": False,
        "next_evidence_action_count": len(next_queue),
        "blockers": sorted(set(blockers)),
        "live_policy_change": live_policy_change,
    }
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_stale_candidate_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only archive record for no-longer-matched regular-options candidates",
            "readback_is_not": "scanner policy change, DB mutation, live trade, broker order, or production proof",
            "trusted_proof_standard": "archived stale candidates require fresh executable exact OPRA/NBBO scanner matches before any new evidence path",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": {"regular_options_candidate_outcome_ledger": input_meta},
        "archived_candidates": rows,
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
        "# Regular Options Stale Candidate Archive",
        "",
        "This report is generated from `scripts/build_regular_options_stale_candidate_archive.py`. It records no-longer-matched regular-options candidates as read-only archived stale branches without mutating scanner, broker, database, proof, or promotion behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Source wait/archive rows: `{summary.get('source_wait_or_archive_count')}`.",
        f"- Archived no-longer-matched candidates: `{summary.get('archived_no_longer_matched_candidate_count')}`.",
        f"- Archive exceptions: `{summary.get('archive_exception_count')}`.",
        f"- Archive complete: `{summary.get('archive_complete')}`.",
        f"- Lane counts: `{_json_inline(summary.get('lane_counts') or {})}`.",
        f"- Ticker counts: `{_json_inline(summary.get('ticker_counts') or {})}`.",
        f"- Production proof-ready rows: `{summary.get('production_proof_ready_count')}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Candidates",
        "",
        "| Scan Date | Lane | Ticker | Direction | Expiry | Long Contract | Short Contract | Status | Validation | Archive |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in _as_list(report.get("archived_candidates")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("scan_date")),
                    _cell(row.get("lane_id")),
                    _cell(row.get("ticker")),
                    _cell(row.get("direction")),
                    _cell(row.get("expiry")),
                    _cell(row.get("contract_symbol")),
                    _cell(row.get("short_contract_symbol")),
                    f"`{_cell(row.get('candidate_status'))}`",
                    f"`{_cell(row.get('validation_outcome'))}`",
                    f"`{_cell(row.get('archive_status'))}`",
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
            "This archive is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change lane promotion, lower proof bars, or reactivate no-longer-matched candidates without fresh executable exact OPRA/NBBO evidence.",
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
    parser = argparse.ArgumentParser(description="Build the regular-options stale candidate archive.")
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(candidate_ledger_path=args.candidate_ledger)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
