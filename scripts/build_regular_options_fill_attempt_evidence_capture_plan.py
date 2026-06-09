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

REPORT_ID = "regular_options_fill_attempt_evidence_capture_plan"

DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json"
DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-fill-attempt-evidence-capture-plan.md"

READY_STATUS = "fill_attempt_evidence_capture_plan_ready_blocked_for_fresh_selection"
CLEAR_STATUS = "fill_attempt_evidence_capture_plan_clear"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"

SOURCE_ACTION = "capture_missing_fill_attempt_evidence"
PLAN_ACTION = "execute_fill_attempt_evidence_capture_plan"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_fill_attempt_evidence_capture_plan",
    "do_not_submit_broker_order_from_fill_attempt_evidence_capture_plan",
    "do_not_mutate_trading_row_database_from_fill_attempt_evidence_capture_plan",
    "do_not_backfill_broker_fills_from_fill_attempt_evidence_capture_plan",
    "do_not_change_scanner_policy_from_fill_attempt_evidence_capture_plan",
    "do_not_change_stop_policy_from_fill_attempt_evidence_capture_plan",
    "do_not_change_sizing_from_fill_attempt_evidence_capture_plan",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_fill_attempt_evidence_capture_plan",
    "do_not_promote_fill_attempt_plan_to_production_proof",
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf8").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


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


def _candidate_key_parts(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        _norm(row.get("scan_date")),
        _norm(row.get("playbook_id") or row.get("lane_id")),
        _norm(row.get("ticker") or row.get("symbol")).upper(),
        _norm(row.get("direction")).lower(),
        _norm(row.get("expiry")),
        _norm(row.get("contract_symbol")).upper(),
        _norm(row.get("short_contract_symbol")).upper(),
    )


def _fill_attempt_key_parts(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    spread = _as_dict(row.get("selected_spread"))
    return (
        _norm(row.get("scan_date")),
        _norm(row.get("playbook_id")),
        _norm(row.get("ticker")).upper(),
        _norm(row.get("direction")).lower(),
        _norm(spread.get("expiry")),
        _norm(spread.get("long_contract_symbol")).upper(),
        _norm(spread.get("short_contract_symbol")).upper(),
    )


def _fill_attempt_index(fill_attempts: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in fill_attempts:
        if _norm(row.get("event_type")) != "candidate_shown":
            continue
        key = _fill_attempt_key_parts(row)
        if not all(key):
            continue
        index.setdefault(key, []).append(row)
    return index


def _target_rows(candidate_ledger: dict[str, Any], fill_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fill_index = _fill_attempt_index(fill_attempts)
    rows: list[dict[str, Any]] = []
    for raw in _as_list(candidate_ledger.get("ledger_rows")):
        row = _as_dict(raw)
        if _norm(row.get("next_evidence_action")) != SOURCE_ACTION:
            continue
        key = _candidate_key_parts(row)
        matching_attempts = fill_index.get(key, [])
        latest_attempt = matching_attempts[-1] if matching_attempts else {}
        capture_status = "fill_attempt_logged_after_ledger_or_stale_ledger" if matching_attempts else "missing"
        action = "rerun_candidate_outcome_ledger_after_fill_attempt_log" if matching_attempts else "capture_durable_fill_attempt_on_fresh_selection"
        required_evidence = [
            "fresh_candidate_still_selected",
            "durable_fill_attempt_jsonl_row",
            "proof_live_opra_exact_contract_entry_snapshot",
            "fill_discipline_snapshot",
        ]
        if "lane_not_profitable_enough_for_live_validation" in _as_list(row.get("blocking_reasons")):
            required_evidence.append("keep_diagnostic_or_paper_only_until_lane_profitability_gate_passes")
        rows.append(
            {
                "priority": _safe_int(row.get("action_priority"), 7),
                "ledger_key": row.get("ledger_key"),
                "candidate_key": row.get("candidate_key"),
                "scan_date": row.get("scan_date"),
                "ticker": row.get("ticker") or row.get("symbol"),
                "lane_id": row.get("lane_id") or row.get("playbook_id"),
                "direction": row.get("direction"),
                "expiry": row.get("expiry"),
                "long_contract_symbol": row.get("contract_symbol"),
                "short_contract_symbol": row.get("short_contract_symbol"),
                "candidate_status": row.get("candidate_status"),
                "validation_outcome": row.get("validation_outcome"),
                "evidence_bridge_status": row.get("evidence_bridge_status"),
                "source_entry_evidence_status": row.get("entry_evidence_status"),
                "source_fill_attempt_status": row.get("fill_attempt_status"),
                "capture_status": capture_status,
                "action": action,
                "market_window_required": not bool(matching_attempts),
                "matching_fill_attempt_count": len(matching_attempts),
                "latest_fill_status": latest_attempt.get("fill_status"),
                "latest_fill_outcome": latest_attempt.get("fill_outcome"),
                "latest_logged_at": latest_attempt.get("logged_at"),
                "required_evidence": required_evidence,
                "blocking_reasons": _as_list(row.get("blocking_reasons")),
                "operator_next_step": (
                    "During the next fresh selection window, rerun the validation path only if this exact candidate is still selected, "
                    "then require a durable fill-attempt row with exact OPRA/NBBO entry evidence and fill-discipline snapshot."
                )
                if not matching_attempts
                else "Rerun the candidate outcome ledger; this exact candidate now has at least one matching fill-attempt row.",
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            _safe_int(item.get("priority"), 7),
            _norm(item.get("scan_date")),
            _norm(item.get("lane_id")),
            _norm(item.get("ticker")),
            _norm(item.get("long_contract_symbol")),
        ),
    )


def _summary(
    *,
    status: str,
    candidate_ledger: dict[str, Any],
    candidate_ledger_meta: dict[str, Any],
    fill_attempts_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    plan_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger_summary = _as_dict(candidate_ledger.get("summary"))
    missing_rows = [row for row in plan_rows if row.get("capture_status") == "missing"]
    stale_rows = [row for row in plan_rows if row.get("capture_status") != "missing"]
    lane_counts = Counter(_norm(row.get("lane_id")) for row in plan_rows)
    ticker_counts = Counter(_norm(row.get("ticker")).upper() for row in plan_rows)
    return {
        "overall_status": status,
        "readback_status": "fill_attempt_evidence_capture_plan_readback",
        "source_candidate_ledger_generated_at_utc": candidate_ledger_meta.get("generated_at_utc"),
        "source_candidate_ledger_status": candidate_ledger.get("status"),
        "source_candidate_ledger_operating_status": ledger_summary.get("operating_status"),
        "source_fill_attempt_rows": fill_attempts_meta.get("row_count"),
        "source_missing_fill_attempt_action_count": _as_dict(ledger_summary.get("action_counts")).get(SOURCE_ACTION),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "plan_row_count": len(plan_rows),
        "missing_fill_attempt_evidence_count": len(missing_rows),
        "ledger_stale_fill_attempt_logged_count": len(stale_rows),
        "market_window_required_count": len(missing_rows),
        "scan_dates": sorted({_norm(row.get("scan_date")) for row in plan_rows if _norm(row.get("scan_date"))}),
        "lane_counts": dict(sorted((key, count) for key, count in lane_counts.items() if key)),
        "ticker_counts": dict(sorted((key, count) for key, count in ticker_counts.items() if key)),
        "operator_plan_status": "ready_for_fresh_selection_capture" if missing_rows else "no_missing_fill_attempt_rows",
    }


def build_report(
    *,
    candidate_ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    candidate_ledger, candidate_ledger_meta = _load_json(candidate_ledger_path)
    fill_attempts, fill_attempts_meta = _load_jsonl(fill_attempts_path)
    missing_required: list[str] = []
    if candidate_ledger_meta.get("status") != "loaded" or not isinstance(candidate_ledger.get("ledger_rows"), list):
        missing_required.append("regular_options_candidate_outcome_ledger")
    if fill_attempts_meta.get("status") != "loaded":
        missing_required.append("fill_attempts")
    live_policy_change = _has_live_policy_change(candidate_ledger)
    rows: list[dict[str, Any]] = []
    if not missing_required and not live_policy_change:
        rows = _target_rows(candidate_ledger, fill_attempts)

    missing_count = sum(1 for row in rows if row.get("capture_status") == "missing")
    if live_policy_change:
        status = INVALID_STATUS
    elif missing_required:
        status = MISSING_STATUS
    elif missing_count:
        status = READY_STATUS
    else:
        status = CLEAR_STATUS

    summary = _summary(
        status=status,
        candidate_ledger=candidate_ledger,
        candidate_ledger_meta=candidate_ledger_meta,
        fill_attempts_meta=fill_attempts_meta,
        missing_required=missing_required,
        live_policy_change=live_policy_change,
        plan_rows=rows,
    )
    next_queue: list[dict[str, Any]] = []
    if missing_count:
        next_queue.append(
            {
                "priority": 7,
                "action": PLAN_ACTION,
                "count": missing_count,
                "reason": "fresh_candidates_need_durable_fill_attempt_evidence",
                "operator_next_step": "Rerun only the fresh selection/validation path for rows still selected; require durable fill-attempt logging and rerun the candidate ledger before any promotion discussion.",
            }
        )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_fill_attempt_evidence_capture_plan_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {"candidate_ledger": candidate_ledger_meta, "fill_attempts": fill_attempts_meta},
        "plan_rows": rows,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only row plan for missing fill-attempt evidence in regular supervised options",
            "readback_is_not": "broker action, trading-row DB mutation, scanner-policy change, stop/sizing change, proof-bar change, or lane promotion",
            "operator_rule": "A row may only move out of this plan after a fresh selection window creates durable fill-attempt evidence and the candidate ledger is rerun.",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Fill-Attempt Evidence Capture Plan",
        "",
        "This report is generated from `scripts/build_regular_options_fill_attempt_evidence_capture_plan.py`. It is a read-only row plan for candidates that still need durable fill-attempt evidence before monthly profitability, paper, live-validation, or promotion decisions.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source ledger status: `{summary.get('source_candidate_ledger_operating_status')}`.",
        f"- Source fill-attempt rows: `{summary.get('source_fill_attempt_rows')}`.",
        f"- Plan rows: `{summary.get('plan_row_count')}`.",
        f"- Missing fill-attempt evidence: `{summary.get('missing_fill_attempt_evidence_count')}`.",
        f"- Ledger-stale logged attempts: `{summary.get('ledger_stale_fill_attempt_logged_count')}`.",
        f"- Market-window required rows: `{summary.get('market_window_required_count')}`.",
        f"- Scan dates: `{_json_inline(summary.get('scan_dates') or [])}`.",
        f"- Lane counts: `{_json_inline(summary.get('lane_counts') or {})}`.",
        f"- Ticker counts: `{_json_inline(summary.get('ticker_counts') or {})}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Capture Rows",
        "",
        "| Priority | Date | Lane | Ticker | Long | Short | Status | Action | Evidence |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for row in _as_list(report.get("plan_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("priority")),
                    _cell(row.get("scan_date")),
                    _cell(row.get("lane_id")),
                    _cell(row.get("ticker")),
                    _cell(row.get("long_contract_symbol")),
                    _cell(row.get("short_contract_symbol")),
                    f"`{_cell(row.get('capture_status'))}`",
                    f"`{_cell(row.get('action'))}`",
                    _cell(",".join(str(item) for item in _as_list(row.get("required_evidence")))),
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
            "This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, backfill broker fills, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote fill-attempt evidence to production proof.",
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
    parser = argparse.ArgumentParser(description="Build a read-only fill-attempt evidence capture plan.")
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(candidate_ledger_path=args.candidate_ledger, fill_attempts_path=args.fill_attempts)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
