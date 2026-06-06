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

from scripts import pending_audit_candidates as pending  # noqa: E402
from scripts.build_regular_options_fresh_evidence_loop import DEFAULT_OUTPUT_DIR as FRESH_OUTPUT_DIR  # noqa: E402
from scripts.candidate_lifecycle import (  # noqa: E402
    STATUS_LIVE_VALIDATION_ATTEMPTED,
    STATUS_LIVE_VALIDATION_SCAN_FAILED,
    STATUS_PAPER_LANE_PROMOTION_STATE,
    STATUS_PENDING_LIVE_VALIDATION,
    STATUS_PENDING_PAPER_EXACT_EVIDENCE,
)
from scripts.lane_promotion_state import (  # noqa: E402
    DEFAULT_LANE_PROMOTION_REPORT,
    PROMOTION_STATE_PAPER_PROBATION,
    lane_promotion_for_playbook,
)
from scripts.regular_open_risk_governor import DEFAULT_OPEN_RISK_REPORT  # noqa: E402


REPORT_ID = "volatility_probation_reconciliation"
LANE_ID = "volatility_expansion_observation"
DEFAULT_FRESH_EVIDENCE = FRESH_OUTPUT_DIR / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "forward-tracking" / "volatility_probation_reconciliation_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "volatility-probation-reconciliation.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(ROOT).as_posix()
    except (OSError, ValueError):
        return str(candidate)


def _load_json(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _lane_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _norm(row.get("playbook_id")).lower() == LANE_ID]


def _context(row: dict[str, Any]) -> str:
    status = _norm(row.get("candidate_status"))
    if status == STATUS_PENDING_PAPER_EXACT_EVIDENCE:
        return "current_paper_probation_exact_evidence_pending"
    explicit = _norm(row.get("promotion_gate_context"))
    if explicit:
        return explicit
    if isinstance(row.get("lane_promotion_state"), dict):
        return "current_lane_promotion_state_payload"
    if status in {
        STATUS_PENDING_LIVE_VALIDATION,
        STATUS_LIVE_VALIDATION_ATTEMPTED,
        STATUS_LIVE_VALIDATION_SCAN_FAILED,
    }:
        return "legacy_pre_promotion_state_gate"
    if status == STATUS_PAPER_LANE_PROMOTION_STATE:
        return "legacy_or_terminal_paper_only_promotion_state"
    return "unclassified_or_diagnostic"


def build_report(
    *,
    queue_file: Path = pending.DEFAULT_QUEUE_FILE,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION_REPORT,
    open_risk_path: Path = DEFAULT_OPEN_RISK_REPORT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    queue_rows = _lane_rows(pending.latest_candidate_rows(queue_file))
    fresh_evidence = _load_json(fresh_evidence_path)
    fresh_rows = _lane_rows([row for row in fresh_evidence.get("candidates") or [] if isinstance(row, dict)])
    lane_promotion = _load_json(lane_promotion_path)
    lane_state = lane_promotion_for_playbook(lane_promotion, LANE_ID) or {}
    open_risk = _load_json(open_risk_path)
    governor = open_risk.get("open_risk_governor") if isinstance(open_risk.get("open_risk_governor"), dict) else {}

    queue_by_key = {_norm(row.get("candidate_key")): row for row in queue_rows if _norm(row.get("candidate_key"))}
    fresh_by_key = {_norm(row.get("candidate_key")): row for row in fresh_rows if _norm(row.get("candidate_key"))}
    keys = sorted(set(queue_by_key) | set(fresh_by_key))
    reconciliation_rows: list[dict[str, Any]] = []
    for key in keys:
        queue_row = queue_by_key.get(key) or {}
        fresh_row = fresh_by_key.get(key) or {}
        status = _norm(fresh_row.get("candidate_status") or queue_row.get("candidate_status"))
        context = _context(fresh_row or queue_row)
        reconciliation_rows.append(
            {
                "candidate_key": key,
                "scan_date": _norm(
                    fresh_row.get("scan_date")
                    or queue_row.get("audit_generated_at_utc")
                    or queue_row.get("queue_recorded_at_utc")
                )[:10],
                "ticker": fresh_row.get("ticker") or queue_row.get("ticker"),
                "candidate_status": status,
                "reconciliation_context": context,
                "validation_outcome": fresh_row.get("validation_outcome"),
                "entry_evidence_status": fresh_row.get("entry_evidence_status"),
                "realized_pnl_status": fresh_row.get("realized_pnl_status"),
                "evidence_bridge_status": fresh_row.get("evidence_bridge_status"),
                "promotion_discussion_ready": bool(fresh_row.get("promotion_discussion_ready")),
                "auto_track_position_id": fresh_row.get("auto_track_position_id") or queue_row.get("auto_track_position_id"),
                "lane_promotion_state_payload_present": isinstance(
                    fresh_row.get("lane_promotion_state") or queue_row.get("lane_promotion_state"),
                    dict,
                ),
            }
        )

    context_counts = Counter(row["reconciliation_context"] for row in reconciliation_rows)
    promotion_ready_non_legacy = sum(
        1
        for row in reconciliation_rows
        if row["promotion_discussion_ready"] and row["reconciliation_context"] != "legacy_pre_promotion_state_gate"
    )
    live_exact_negative_ids = list(governor.get("live_exact_negative_ids") or [])
    open_risk_blockers = list(governor.get("blockers") or [])
    current_blockers = list(lane_state.get("blockers") or [])
    status = (
        "paper_probation_blocked"
        if lane_state.get("promotion_state") == PROMOTION_STATE_PAPER_PROBATION or current_blockers or open_risk_blockers
        else "review_required"
    )
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_volatility_probation_reconciliation",
        "status": status,
        "lane_id": LANE_ID,
        "read_only": True,
        "live_policy_change": False,
        "inputs": {
            "queue_file": _rel(queue_file),
            "fresh_evidence_path": _rel(fresh_evidence_path),
            "fresh_evidence_generated_at_utc": fresh_evidence.get("generated_at_utc"),
            "lane_promotion_path": _rel(lane_promotion_path),
            "lane_promotion_generated_at_utc": lane_promotion.get("generated_at_utc"),
            "open_risk_path": _rel(open_risk_path),
            "open_risk_generated_at_utc": open_risk.get("generated_at_utc"),
        },
        "summary": {
            "queue_candidate_count": len(queue_rows),
            "fresh_evidence_candidate_count": len(fresh_rows),
            "reconciled_candidate_count": len(reconciliation_rows),
            "context_counts": dict(sorted(context_counts.items())),
            "legacy_pre_promotion_state_gate_count": context_counts.get("legacy_pre_promotion_state_gate", 0),
            "current_paper_probation_exact_evidence_pending_count": context_counts.get(
                "current_paper_probation_exact_evidence_pending",
                0,
            ),
            "promotion_discussion_ready_excluding_legacy_count": promotion_ready_non_legacy,
            "lane_promotion_state": lane_state.get("promotion_state"),
            "lane_candidate_status": lane_state.get("candidate_status"),
            "lane_failed_promotion_gates": list(lane_state.get("failed_promotion_gates") or []),
            "lane_blockers": current_blockers,
            "open_risk_governor_status": governor.get("status"),
            "open_risk_governor_blockers": open_risk_blockers,
            "live_exact_negative_ids": live_exact_negative_ids,
            "prohibited_actions": [
                "do_not_count_legacy_pre_promotion_rows_as_current_paper_proof",
                "do_not_run_live_validation_for_paper_probation_candidates",
                "do_not_create_scanner_origin_rows_until_open_risk_governor_passes",
            ],
        },
        "reconciliation_rows": reconciliation_rows,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Volatility Probation Reconciliation",
        "",
        "This report is generated from `scripts/build_volatility_probation_reconciliation.py`. It reconciles the volatility lane's current paper/probation state against legacy live-validation rows, fresh-evidence rows, and open-risk blockers without creating trades or changing policy.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Lane: `{report['lane_id']}`.",
        f"- Lane promotion state: `{summary['lane_promotion_state']}`.",
        f"- Lane candidate status: `{summary['lane_candidate_status']}`.",
        f"- Context counts: `{json.dumps(summary['context_counts'], sort_keys=True)}`.",
        f"- Legacy pre-promotion rows: `{summary['legacy_pre_promotion_state_gate_count']}`.",
        f"- Current paper exact pending rows: `{summary['current_paper_probation_exact_evidence_pending_count']}`.",
        f"- Promotion-ready excluding legacy: `{summary['promotion_discussion_ready_excluding_legacy_count']}`.",
        f"- Open-risk governor: `{summary['open_risk_governor_status']}`.",
        f"- Open-risk blockers: `{json.dumps(summary['open_risk_governor_blockers'], sort_keys=True)}`.",
        f"- Live exact negative ids: `{json.dumps(summary['live_exact_negative_ids'], sort_keys=True)}`.",
        f"- Live policy change: `{report['live_policy_change']}`.",
        "",
        "## Prohibited Actions",
        "",
    ]
    for action in summary["prohibited_actions"]:
        lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Reconciliation Rows",
            "",
            "| Date | Ticker | Status | Context | Outcome | Entry | P&L | Bridge | Position | Ready |",
            "|---|---|---|---|---|---|---|---|---:|---|",
        ]
    )
    for row in report.get("reconciliation_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("scan_date")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("candidate_status")),
                    _fmt(row.get("reconciliation_context")),
                    _fmt(row.get("validation_outcome")),
                    _fmt(row.get("entry_evidence_status")),
                    _fmt(row.get("realized_pnl_status")),
                    _fmt(row.get("evidence_bridge_status")),
                    _fmt(row.get("auto_track_position_id")),
                    _fmt(row.get("promotion_discussion_ready")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    report: dict[str, Any],
    *,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the volatility paper/probation reconciliation readback.")
    parser.add_argument("--queue-file", type=Path, default=pending.DEFAULT_QUEUE_FILE)
    parser.add_argument("--fresh-evidence", type=Path, default=DEFAULT_FRESH_EVIDENCE)
    parser.add_argument("--lane-promotion", type=Path, default=DEFAULT_LANE_PROMOTION_REPORT)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK_REPORT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        queue_file=args.queue_file,
        fresh_evidence_path=args.fresh_evidence,
        lane_promotion_path=args.lane_promotion,
        open_risk_path=args.open_risk,
    )
    if not args.no_write:
        write_outputs(report, output_json=args.output_json, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
