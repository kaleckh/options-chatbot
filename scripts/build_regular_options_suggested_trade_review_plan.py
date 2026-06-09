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

REPORT_ID = "regular_options_suggested_trade_review_plan"

DEFAULT_SUGGESTED_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-suggested-trade-review-plan.md"

READY_STATUS = "suggested_trade_review_plan_ready_blocked_for_market_window"
CLEAR_STATUS = "suggested_trade_review_plan_clear"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"
PLAN_ACTION = "execute_suggested_trade_review_plan"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_suggested_trade_review_plan",
    "do_not_submit_broker_order_from_suggested_trade_review_plan",
    "do_not_mutate_suggested_trade_database_from_suggested_trade_review_plan",
    "do_not_auto_close_from_stale_display_or_missing_review_marks",
    "do_not_count_suggested_trades_as_production_proof",
    "do_not_change_scanner_policy_from_suggested_trade_review_plan",
    "do_not_change_stop_policy_from_suggested_trade_review_plan",
    "do_not_change_sizing_from_suggested_trade_review_plan",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_suggested_trade_review_plan",
    "do_not_promote_suggested_trade_review_plan_to_production_proof",
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


def _detail_id(detail: dict[str, Any]) -> str:
    if detail.get("id") not in {None, ""}:
        return str(detail.get("id"))
    return "|".join(
        [
            _norm(detail.get("ticker")),
            _norm(detail.get("lane")),
            _norm(detail.get("record_class")),
            _norm(detail.get("evidence_bucket")),
        ]
    )


def _plan_action(detail: dict[str, Any]) -> tuple[int, str, str, list[str]]:
    action_bucket = _norm(detail.get("action_bucket"))
    evidence_bucket = _norm(detail.get("evidence_bucket"))
    required_evidence = [
        "fresh_explicit_suggested_trade_review",
        "candidate_outcome_ledger_rerun",
        "monthly_profitability_audit_rerun",
    ]
    if action_bucket == "stored_executable_sell":
        required_evidence.append("paper_idea_close_decision_after_executable_review")
        return (
            0,
            "review_executable_suggested_trade_close_decision",
            "fresh_executable_review_close_decision_required",
            required_evidence,
        )
    if action_bucket == "stored_non_executable_sell":
        required_evidence.append("spread_bid_ask_exact_or_explicit_unpriced_review")
        return (
            1,
            "refresh_non_executable_suggested_trade_sell_review",
            "market_window_required_non_executable_sell_review",
            required_evidence,
        )
    if action_bucket in {"below_configured_stop_mark", "above_configured_target_mark"}:
        required_evidence.append("exact_exit_quote_before_close_decision")
        return (
            1,
            "refresh_mark_triggered_suggested_trade_review",
            "market_window_required_mark_trigger_review",
            required_evidence,
        )
    if evidence_bucket == "missing_review":
        required_evidence.append("stored_review_snapshot")
        return (
            1,
            "refresh_missing_suggested_trade_review",
            "market_window_required_missing_suggested_trade_review",
            required_evidence,
        )
    if evidence_bucket.startswith("stale_"):
        required_evidence.append("fresh_review_snapshot_replacing_stale_review")
        return (
            1,
            "refresh_stale_suggested_trade_review",
            "market_window_required_stale_suggested_trade_review",
            required_evidence,
        )
    return (
        2,
        "refresh_suggested_trade_review",
        "market_window_required_suggested_trade_review",
        required_evidence,
    )


def _plan_rows(suggested_risk: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for raw in _as_list(suggested_risk.get("attention_trades")):
        detail = _as_dict(raw)
        if not detail:
            continue
        priority, action, status, required_evidence = _plan_action(detail)
        key = _detail_id(detail)
        existing = rows_by_key.get(key)
        rows_by_key[key] = {
            "priority": min(priority, _safe_int((existing or {}).get("priority"), priority)),
            "suggested_trade_id": detail.get("id"),
            "ticker": detail.get("ticker"),
            "lane": detail.get("lane"),
            "record_class": detail.get("record_class"),
            "status": detail.get("status"),
            "action": action,
            "resolution_status": status,
            "evidence_bucket": detail.get("evidence_bucket"),
            "action_bucket": detail.get("action_bucket"),
            "pricing_source": detail.get("pricing_source"),
            "pricing_state": detail.get("pricing_state"),
            "recommendation": detail.get("recommendation"),
            "current_pnl_pct": detail.get("current_pnl_pct"),
            "mark_pnl_pct": detail.get("mark_pnl_pct"),
            "stop_loss_pct": detail.get("stop_loss_pct"),
            "profit_target_pct": detail.get("profit_target_pct"),
            "exit_execution_price": detail.get("exit_execution_price"),
            "exit_execution_basis": detail.get("exit_execution_basis"),
            "price_trigger_ok": detail.get("price_trigger_ok"),
            "last_reviewed_at": detail.get("last_reviewed_at"),
            "required_evidence": required_evidence,
            "source_next_safe_action": detail.get("next_safe_action"),
            "first_warning": detail.get("first_warning"),
            "reason": detail.get("reason"),
            "market_window_required": True,
            "operator_next_step": (
                "During the next fresh executable quote window, refresh this paper idea's explicit review, "
                "then rerun the suggested close-risk, candidate-ledger, and monthly profitability readbacks."
            ),
        }
    return sorted(
        rows_by_key.values(),
        key=lambda item: (
            _safe_int(item.get("priority")),
            _safe_int(item.get("suggested_trade_id"), 999999),
            _norm(item.get("ticker")),
        ),
    )


def _source_count_list(report: dict[str, Any], key: str) -> int:
    return len(_as_list(report.get(key)))


def _summary(
    *,
    status: str,
    suggested_risk: dict[str, Any],
    suggested_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    plan_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    source_summary = _as_dict(suggested_risk.get("summary"))
    evidence_counts = _as_dict(suggested_risk.get("evidence_counts"))
    source_action_counts = _as_dict(suggested_risk.get("action_counts"))
    stale_review_count = sum(
        _safe_int(value)
        for key, value in evidence_counts.items()
        if str(key).startswith("stale_")
    )
    executable_close_ready_count = _safe_int(source_action_counts.get("stored_executable_sell"))
    non_executable_close_risk_count = _safe_int(source_action_counts.get("stored_non_executable_sell"))
    action_counts = {
        action: sum(1 for row in plan_rows if row.get("action") == action)
        for action in sorted({str(row.get("action")) for row in plan_rows})
    }
    return {
        "overall_status": status,
        "readback_status": "suggested_trade_review_plan_readback",
        "source_suggested_trade_generated_at_utc": suggested_meta.get("generated_at_utc"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "open_suggested_trade_rows": source_summary.get("rows"),
        "priced_or_marked_count": source_summary.get("priced_or_marked"),
        "attention_trade_count": _source_count_list(suggested_risk, "attention_trade_ids"),
        "close_risk_trade_count": _source_count_list(suggested_risk, "close_risk_trade_ids"),
        "stale_or_missing_review_trade_count": _source_count_list(
            suggested_risk,
            "stale_or_missing_review_trade_ids",
        ),
        "missing_review_count": _safe_int(evidence_counts.get("missing_review")),
        "stale_review_count": stale_review_count,
        "executable_close_ready_count": executable_close_ready_count,
        "non_executable_close_risk_count": non_executable_close_risk_count,
        "source_action_counts": source_action_counts,
        "source_evidence_counts": evidence_counts,
        "plan_row_count": len(plan_rows),
        "market_window_required_count": sum(1 for row in plan_rows if row.get("market_window_required")),
        "action_counts": action_counts,
        "operator_plan_status": "ready_for_fresh_suggested_trade_review_window"
        if plan_rows
        else "no_suggested_trade_review_rows_to_refresh",
    }


def build_report(
    *,
    suggested_close_risk_path: Path = DEFAULT_SUGGESTED_CLOSE_RISK,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    suggested_risk, suggested_meta = _load_json(suggested_close_risk_path)
    missing_required: list[str] = []
    if suggested_meta.get("status") != "loaded" or "attention_trades" not in suggested_risk:
        missing_required.append("suggested_trade_close_risk")
    live_policy_change = _has_live_policy_change(suggested_risk)
    rows: list[dict[str, Any]] = []
    if not missing_required and not live_policy_change:
        rows = _plan_rows(suggested_risk)

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
        suggested_risk=suggested_risk,
        suggested_meta=suggested_meta,
        missing_required=missing_required,
        live_policy_change=live_policy_change,
        plan_rows=rows,
    )
    next_queue: list[dict[str, Any]] = []
    if rows:
        next_queue.append(
            {
                "priority": 1,
                "action": PLAN_ACTION,
                "count": len(rows),
                "reason": "suggested_trade_attention_rows_need_fresh_explicit_review",
                "operator_next_step": (
                    "Use the row plan during the next fresh executable quote window; do not auto-close "
                    "or rely on paper-idea P&L from stale, missing, display-only, or non-executable marks."
                ),
            }
        )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_suggested_trade_review_plan_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {"suggested_trade_close_risk": suggested_meta},
        "plan_rows": rows,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only suggested-trade review plan for regular supervised options paper ideas",
            "readback_is_not": "broker action, auto-close instruction, suggested-trade DB mutation, production proof, scanner-policy change, stop/sizing change, proof-bar change, or lane promotion",
            "operator_rule": "Suggested-trade close or P&L conclusions require a fresh explicit review before use in the monthly profitability loop.",
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
        "# Regular Options Suggested-Trade Review Plan",
        "",
        "This report is generated from `scripts/build_regular_options_suggested_trade_review_plan.py`. It is a read-only row plan for refreshing suggested-trade attention rows before monthly profitability, paper-idea P&L, close-state, or promotion decisions.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Open suggested-trade rows: `{summary.get('open_suggested_trade_rows')}`.",
        f"- Attention rows: `{summary.get('attention_trade_count')}`.",
        f"- Close-risk rows: `{summary.get('close_risk_trade_count')}`.",
        f"- Stale/missing review rows: `{summary.get('stale_or_missing_review_trade_count')}`.",
        f"- Missing review rows: `{summary.get('missing_review_count')}`.",
        f"- Stale review rows: `{summary.get('stale_review_count')}`.",
        f"- Executable close-ready rows: `{summary.get('executable_close_ready_count')}`.",
        f"- Non-executable close-risk rows: `{summary.get('non_executable_close_risk_count')}`.",
        f"- Plan rows: `{summary.get('plan_row_count')}`.",
        f"- Market-window-required rows: `{summary.get('market_window_required_count')}`.",
        f"- Source evidence counts: `{_json_inline(summary.get('source_evidence_counts') or {})}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Review Rows",
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
                    _cell(row.get("suggested_trade_id")),
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
            "This plan is read-only. It does not create trades, submit broker orders, mutate suggested-trade DB state, auto-close from stale/display/missing review marks, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, count suggested trades as production proof, or promote paper/research/backfill evidence.",
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
    parser = argparse.ArgumentParser(description="Build a read-only suggested-trade review plan.")
    parser.add_argument("--suggested-close-risk", type=Path, default=DEFAULT_SUGGESTED_CLOSE_RISK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(suggested_close_risk_path=args.suggested_close_risk)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
