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

REPORT_ID = "regular_options_open_risk_resolution_plan"

DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-open-risk-resolution-plan.md"

READY_STATUS = "open_risk_resolution_plan_ready_blocked_for_market_window"
CLEAR_STATUS = "open_risk_resolution_plan_clear"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_open_risk_resolution_plan",
    "do_not_submit_broker_order_from_open_risk_resolution_plan",
    "do_not_mutate_trading_row_database_from_open_risk_resolution_plan",
    "do_not_auto_close_from_display_only_marks",
    "do_not_change_scanner_policy_from_open_risk_resolution_plan",
    "do_not_change_stop_policy_from_open_risk_resolution_plan",
    "do_not_change_sizing_from_open_risk_resolution_plan",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_open_risk_resolution_plan",
    "do_not_promote_open_risk_plan_to_production_proof",
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
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


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


def _row_id(detail: dict[str, Any]) -> str:
    if detail.get("id") not in {None, ""}:
        return str(detail.get("id"))
    return "|".join(
        [
            _norm(detail.get("ticker")),
            _norm(detail.get("lane")),
            _norm(detail.get("record_class")),
            _norm(detail.get("last_reviewed_at")),
        ]
    )


def _plan_action(detail: dict[str, Any], *, source: str) -> tuple[int, str, str, list[str]]:
    action_bucket = _norm(detail.get("action_bucket"))
    evidence_bucket = _norm(detail.get("evidence_bucket"))
    record_class = _norm(detail.get("record_class"))
    recommendation = _norm(detail.get("recommendation")).upper()
    current_pnl = _safe_float(detail.get("current_pnl_pct"))
    mark_pnl = _safe_float(detail.get("mark_pnl_pct"))
    negative = any(value is not None and value < 0 for value in (current_pnl, mark_pnl))
    required_evidence = ["fresh_executable_open_position_review"]
    if record_class == "live_exact_tracked":
        required_evidence.append("open_risk_governor_rerun")
    if action_bucket == "stored_non_executable_sell":
        required_evidence.append("spread_bid_ask_exact_or_explicit_unpriced_review")
        return (
            1,
            "refresh_display_only_sell_executable_review",
            "market_window_required_display_only_sell_review",
            required_evidence,
        )
    if action_bucket == "stored_executable_sell":
        required_evidence.append("manual_close_or_auto_close_review_decision")
        return (
            0,
            "review_executable_sell_close_decision",
            "market_window_required_executable_close_decision",
            required_evidence,
        )
    if action_bucket == "below_configured_stop_mark":
        required_evidence.append("exact_exit_quote_before_stop_close_decision")
        return (
            0 if record_class == "live_exact_tracked" else 1,
            "refresh_stop_trigger_executable_review",
            "market_window_required_stop_trigger_review",
            required_evidence,
        )
    if record_class == "live_exact_tracked" and negative:
        if evidence_bucket == "fresh_executable_review" and recommendation == "HOLD":
            required_evidence.append("monitor_or_close_decision_under_exit_rules")
            return (
                0,
                "refresh_live_exact_negative_open_position_review",
                "fresh_quote_monitor_or_close_decision_required",
                required_evidence,
            )
        return (
            0,
            "refresh_live_exact_negative_open_position_review",
            "market_window_required_live_exact_negative_review",
            required_evidence,
        )
    if source == "open_risk_governor":
        return (
            0,
            "refresh_live_exact_open_position_review",
            "market_window_required_live_exact_review",
            required_evidence,
        )
    return (
        1,
        "refresh_open_position_executable_review",
        "market_window_required_open_position_review",
        required_evidence,
    )


def _plan_rows(open_risk: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    source_lists = [
        ("open_risk_governor", _as_list(_as_dict(open_risk.get("open_risk_governor")).get("governor_details"))),
        ("actionable_position", _as_list(open_risk.get("actionable_positions"))),
    ]
    for source, details in source_lists:
        for raw in details:
            detail = _as_dict(raw)
            if not detail:
                continue
            priority, action, status, required_evidence = _plan_action(detail, source=source)
            key = _row_id(detail)
            existing = rows_by_id.get(key)
            sources = sorted(set(_as_list((existing or {}).get("sources")) + [source]))
            row = {
                "priority": min(priority, _safe_int((existing or {}).get("priority"), priority)),
                "row_id": detail.get("id"),
                "ticker": detail.get("ticker"),
                "lane": detail.get("lane"),
                "record_class": detail.get("record_class"),
                "recommendation": detail.get("recommendation"),
                "action": action,
                "resolution_status": status,
                "sources": sources,
                "evidence_bucket": detail.get("evidence_bucket"),
                "action_bucket": detail.get("action_bucket"),
                "pricing_source": detail.get("pricing_source"),
                "pricing_state": detail.get("pricing_state"),
                "current_pnl_pct": detail.get("current_pnl_pct"),
                "mark_pnl_pct": detail.get("mark_pnl_pct"),
                "exit_execution_price": detail.get("exit_execution_price"),
                "exit_execution_basis": detail.get("exit_execution_basis"),
                "price_trigger_ok": detail.get("price_trigger_ok"),
                "last_reviewed_at": detail.get("last_reviewed_at"),
                "required_evidence": required_evidence,
                "source_next_safe_action": detail.get("next_safe_action"),
                "first_warning": detail.get("first_warning"),
                "reason": detail.get("reason"),
                "operator_next_step": (
                    "During the next fresh executable quote window, refresh this position's explicit executable review, "
                    "then rerun open-risk and monthly profitability readbacks before any live-validation decision."
                ),
            }
            rows_by_id[key] = row
    return sorted(
        rows_by_id.values(),
        key=lambda item: (
            _safe_int(item.get("priority")),
            _safe_int(item.get("row_id"), 999999),
            _norm(item.get("ticker")),
        ),
    )


def _summary(
    *,
    status: str,
    open_risk: dict[str, Any],
    open_risk_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    plan_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    governor = _as_dict(open_risk.get("open_risk_governor"))
    source_summary = _as_dict(open_risk.get("summary"))
    display_only = [
        row for row in plan_rows if _norm(row.get("action")) == "refresh_display_only_sell_executable_review"
    ]
    live_exact_negative = [
        row for row in plan_rows if _norm(row.get("record_class")) == "live_exact_tracked"
    ]
    return {
        "overall_status": status,
        "readback_status": "open_risk_resolution_plan_readback",
        "source_open_risk_generated_at_utc": open_risk_meta.get("generated_at_utc"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "source_open_risk_status": governor.get("status"),
        "live_entry_allowed": governor.get("live_entry_allowed"),
        "open_risk_blockers": _as_list(governor.get("blockers")),
        "live_exact_open_count": governor.get("live_exact_open_count"),
        "live_exact_negative_count": governor.get("live_exact_negative_count"),
        "live_exact_negative_ids": _as_list(governor.get("live_exact_negative_ids")),
        "live_exact_executable_close_ready_count": governor.get("live_exact_executable_close_ready_count"),
        "live_exact_review_blocked_count": governor.get("live_exact_review_blocked_count"),
        "open_position_row_count": source_summary.get("rows"),
        "open_position_priced_or_marked_count": source_summary.get("priced_or_marked"),
        "open_position_negative_count": source_summary.get("negative"),
        "open_position_avg_pnl_pct": source_summary.get("avg_pnl_pct"),
        "open_position_median_pnl_pct": source_summary.get("median_pnl_pct"),
        "plan_row_count": len(plan_rows),
        "market_window_required_count": len(plan_rows),
        "live_exact_plan_row_count": len(live_exact_negative),
        "display_only_sell_count": len(display_only),
        "action_counts": {
            action: sum(1 for row in plan_rows if row.get("action") == action)
            for action in sorted({str(row.get("action")) for row in plan_rows})
        },
        "operator_plan_status": "ready_for_fresh_executable_review_window" if plan_rows else "no_rows_to_resolve",
    }


def build_report(
    *,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    open_risk, open_risk_meta = _load_json(open_risk_path)
    missing_required: list[str] = []
    if open_risk_meta.get("status") != "loaded" or not isinstance(open_risk.get("open_risk_governor"), dict):
        missing_required.append("regular_open_position_risk")
    live_policy_change = _has_live_policy_change(open_risk)
    rows: list[dict[str, Any]] = []
    if not missing_required and not live_policy_change:
        rows = _plan_rows(open_risk)

    if live_policy_change:
        status = INVALID_STATUS
    elif missing_required:
        status = MISSING_STATUS
    elif rows:
        status = READY_STATUS
    else:
        status = CLEAR_STATUS

    summary = _summary(
        status=status,
        open_risk=open_risk,
        open_risk_meta=open_risk_meta,
        missing_required=missing_required,
        live_policy_change=live_policy_change,
        plan_rows=rows,
    )
    next_queue: list[dict[str, Any]] = []
    if rows:
        next_queue.append(
            {
                "priority": 0,
                "action": "execute_open_risk_resolution_review_plan",
                "count": len(rows),
                "reason": "open_risk_rows_need_fresh_executable_review_or_monitor_decision",
                "operator_next_step": "Use the row plan during the next fresh executable quote window; do not auto-close display-only marks and rerun monthly profitability after the open-risk audit refreshes.",
            }
        )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_open_risk_resolution_plan_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {"regular_open_position_risk": open_risk_meta},
        "plan_rows": rows,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only open-risk resolution review plan for regular supervised options",
            "readback_is_not": "broker action, auto-close instruction, trading-row DB mutation, scanner-policy change, stop/sizing change, proof-bar change, or lane promotion",
            "operator_rule": "Rows must be refreshed with fresh executable review evidence before using any close, P&L, live-entry, or promotion conclusion.",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    text = _norm(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Open-Risk Resolution Plan",
        "",
        "This report is generated from `scripts/build_regular_options_open_risk_resolution_plan.py`. It is a read-only row plan for resolving open-risk blockers before monthly profitability, live-entry, or promotion decisions.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source open-risk status: `{summary.get('source_open_risk_status')}`.",
        f"- Live entry allowed: `{summary.get('live_entry_allowed')}`.",
        f"- Live exact negative IDs: `{_json_inline(summary.get('live_exact_negative_ids') or [])}`.",
        f"- Open rows / negative rows: `{summary.get('open_position_row_count')}` / `{summary.get('open_position_negative_count')}`.",
        f"- Avg / median open P&L: `{summary.get('open_position_avg_pnl_pct')}` / `{summary.get('open_position_median_pnl_pct')}`.",
        f"- Plan rows: `{summary.get('plan_row_count')}`.",
        f"- Live exact plan rows: `{summary.get('live_exact_plan_row_count')}`.",
        f"- Display-only SELL rows: `{summary.get('display_only_sell_count')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Resolution Rows",
        "",
        "| Priority | ID | Ticker | Lane | Class | Action | Status | Evidence | P&L | Warning |",
        "|---:|---:|---|---|---|---|---|---|---:|---|",
    ]
    for row in _as_list(report.get("plan_rows")):
        row = _as_dict(row)
        pnl = row.get("current_pnl_pct")
        if pnl is None:
            pnl = row.get("mark_pnl_pct")
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("priority")),
                    _cell(row.get("row_id")),
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("record_class")),
                    f"`{_cell(row.get('action'))}`",
                    f"`{_cell(row.get('resolution_status'))}`",
                    _cell(",".join(str(item) for item in _as_list(row.get("required_evidence")))),
                    _cell(pnl),
                    _cell(row.get("first_warning") or ""),
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
            "This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, auto-close display-only marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote open-risk rows to production proof.",
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
    parser = argparse.ArgumentParser(description="Build a read-only open-risk resolution review plan.")
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(open_risk_path=args.open_risk)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
