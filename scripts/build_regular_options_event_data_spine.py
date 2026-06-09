from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_event_data_spine"

DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-event-data-spine.md"

BUILT_STATUS = "event_data_spine_built_collecting"
EMPTY_STATUS = "event_data_spine_empty_collecting"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"

EVENT_ANNOTATION_KEYS = (
    "earnings",
    "earnings_date",
    "earnings_time",
    "earnings_window",
    "event_calendar_source",
    "event_risk",
    "event_risk_score",
    "corporate_action",
    "dividend_date",
    "macro_event",
    "economic_event",
    "fomc_window",
    "cpi_window",
    "iv_crush_penalty",
    "post_event_vol_crush",
    "post_event_vol_crush_pct",
    "vol_crush",
    "iv_crush_pct",
    "pre_event_iv",
    "post_event_iv",
)

POST_EVENT_VOL_KEYS = (
    "iv_crush_penalty",
    "post_event_vol_crush",
    "post_event_vol_crush_pct",
    "vol_crush",
    "iv_crush_pct",
    "pre_event_iv",
    "post_event_iv",
)

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_event_data_spine",
    "do_not_submit_broker_order_from_event_data_spine",
    "do_not_mutate_database_from_event_data_spine",
    "do_not_change_scanner_policy_from_event_data_spine",
    "do_not_change_stop_policy_from_event_data_spine",
    "do_not_change_sizing_from_event_data_spine",
    "do_not_tune_event_thresholds_from_event_data_spine",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_event_data_spine",
    "do_not_count_midpoint_daily_stale_last_trade_or_research_backfill_as_event_proof",
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


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _norm(row.get("event_type")) == "candidate_shown"]


def _selected(row: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(row.get("selected_spread"))


def _ticker(row: dict[str, Any]) -> str:
    return _norm(row.get("ticker") or _selected(row).get("ticker")) or "unknown"


def _playbook(row: dict[str, Any]) -> str:
    return _norm(row.get("playbook_id") or row.get("cohort_id")) or "unknown"


def _expiry(row: dict[str, Any]) -> str:
    selected = _selected(row)
    return _norm(row.get("expiry") or selected.get("expiry")) or "unknown"


def _contains_annotation_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        if key in value and value[key] is not None and value[key] != "":
            return True
        return any(_contains_annotation_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_annotation_key(item, key) for item in value)
    return False


def _annotation_keys(row: dict[str, Any]) -> list[str]:
    return [key for key in EVENT_ANNOTATION_KEYS if _contains_annotation_key(row, key)]


def _post_event_vol_keys(row: dict[str, Any]) -> list[str]:
    return [key for key in POST_EVENT_VOL_KEYS if _contains_annotation_key(row, key)]


def _is_proof_live_exact_entry(row: dict[str, Any]) -> bool:
    return _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"


def _has_exit_pnl(row: dict[str, Any]) -> bool:
    exit_result = _as_dict(row.get("exit_result"))
    if not exit_result:
        return False
    return any(
        _safe_float(exit_result.get(key)) is not None
        for key in ("net_pnl_pct", "net_pnl_usd", "realized_pnl_pct", "realized_pnl_usd")
    )


def _trusted_exit_evidence(row: dict[str, Any]) -> bool:
    exit_result = _as_dict(row.get("exit_result"))
    exit_evidence = " ".join(
        _norm(
            exit_result.get(key)
            or row.get(key)
            or _as_dict(row.get("close_review")).get(key)
        ).lower()
        for key in (
            "pricing_evidence_class",
            "profitability_evidence_class",
            "exit_pricing_evidence_class",
            "exit_execution_basis",
            "execution_basis",
            "quote_source",
        )
    )
    return "proof_live_opra_exact_contract" in exit_evidence or ("opra" in exit_evidence and "bid" in exit_evidence)


def _has_true_event_pnl(row: dict[str, Any]) -> bool:
    return (
        bool(_annotation_keys(row))
        and _is_proof_live_exact_entry(row)
        and _norm(row.get("fill_outcome")) == "paper_fill_recorded"
        and _safe_float(row.get("filled_price")) is not None
        and _has_exit_pnl(row)
        and _trusted_exit_evidence(row)
    )


def _has_post_event_vol_crush_pnl(row: dict[str, Any]) -> bool:
    return bool(_post_event_vol_keys(row)) and _has_true_event_pnl(row)


def _latest_seed(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "logged_at": row.get("logged_at"),
        "scan_date": row.get("scan_date"),
        "ticker": _ticker(row),
        "playbook_id": _playbook(row),
        "direction": row.get("direction") or _selected(row).get("direction"),
        "strategy_type": row.get("strategy_type") or _selected(row).get("strategy_type"),
        "expiry": _expiry(row),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "pricing_evidence_class": row.get("pricing_evidence_class"),
        "event_annotation_keys": _annotation_keys(row),
    }


def _spine_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        grouped[(_ticker(row), _playbook(row), _expiry(row))].append(row)
    rows = []
    for (ticker, playbook, expiry), items in sorted(grouped.items()):
        annotation_counts = Counter()
        for item in items:
            annotation_counts.update(_annotation_keys(item))
        latest = items[-1] if items else {}
        rows.append(
            {
                "ticker": ticker,
                "playbook_id": playbook,
                "expiry": expiry,
                "candidate_shown_count": len(items),
                "event_annotation_count": sum(1 for item in items if _annotation_keys(item)),
                "missing_event_annotation_count": sum(1 for item in items if not _annotation_keys(item)),
                "proof_live_exact_entry_count": sum(1 for item in items if _is_proof_live_exact_entry(item)),
                "paper_fill_recorded_count": sum(
                    1 for item in items if _norm(item.get("fill_outcome")) == "paper_fill_recorded"
                ),
                "true_event_replay_pnl_count": sum(1 for item in items if _has_true_event_pnl(item)),
                "post_event_vol_crush_replay_pnl_count": sum(1 for item in items if _has_post_event_vol_crush_pnl(item)),
                "event_annotation_field_counts": dict(sorted(annotation_counts.items())),
                "latest_seed": _latest_seed(latest) if latest else {},
                "read_only": True,
            }
        )
    return rows


def _next_evidence_queue(summary: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if _safe_int(summary.get("candidate_shown_count")) == 0:
        queue.append(
            {
                "priority": 7,
                "action": "collect_event_spine_candidate_rows",
                "count": 1,
                "reason": "no_regular_options_candidate_rows_for_event_spine",
                "operator_next_step": "Collect fresh regular-options candidate rows before event annotation replay.",
            }
        )
        return queue
    if _safe_int(summary.get("missing_event_annotation_count")) > 0:
        queue.append(
            {
                "priority": 7,
                "action": "collect_event_calendar_annotations",
                "count": summary.get("missing_event_annotation_count"),
                "reason": "candidate_rows_missing_durable_event_calendar_annotations",
                "operator_next_step": "Attach durable event-calendar fields without changing scanner, symbols, expiries, or thresholds.",
            }
        )
    if _safe_int(summary.get("post_event_vol_crush_replay_pnl_count")) == 0:
        queue.append(
            {
                "priority": 8,
                "action": "build_post_event_vol_crush_replay_from_annotated_rows",
                "count": summary.get("event_annotation_count"),
                "reason": "no_true_post_event_vol_crush_executable_pnl_rows",
                "operator_next_step": "After annotation coverage exists, replay post-event IV change only with exact entry/fill/exit P&L.",
            }
        )
    if _safe_int(summary.get("true_event_replay_pnl_count")) == 0:
        queue.append(
            {
                "priority": 8,
                "action": "collect_event_exact_entry_exit_pnl",
                "count": summary.get("candidate_shown_count"),
                "reason": "no_true_event_executable_entry_exit_pnl_rows",
                "operator_next_step": "Collect exact-contract OPRA/NBBO executable entry, fill, event annotation, and exit P&L before event-sensitive claims.",
            }
        )
    return queue


def _summary(
    *,
    status: str,
    fill_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    candidate_rows: list[dict[str, Any]],
    spine_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ticker_counts = Counter(_ticker(row) for row in candidate_rows)
    playbook_counts = Counter(_playbook(row) for row in candidate_rows)
    field_counts = Counter()
    for row in candidate_rows:
        field_counts.update(_annotation_keys(row))
    event_annotation_count = sum(1 for row in candidate_rows if _annotation_keys(row))
    missing_event_annotation_count = len(candidate_rows) - event_annotation_count
    true_event_count = sum(_safe_int(row.get("true_event_replay_pnl_count")) for row in spine_rows)
    post_event_vol_count = sum(_safe_int(row.get("post_event_vol_crush_replay_pnl_count")) for row in spine_rows)
    blockers = []
    if not candidate_rows:
        blockers.append("no_candidate_shown_fill_attempt_rows")
    if missing_event_annotation_count:
        blockers.append("event_calendar_annotations_missing")
    if true_event_count == 0:
        blockers.append("true_event_executable_pnl_rows_missing")
    if post_event_vol_count == 0:
        blockers.append("post_event_vol_crush_replay_rows_missing")
    return {
        "overall_status": status,
        "readback_status": "event_data_spine_readback",
        "source_fill_attempt_rows": fill_meta.get("row_count"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "candidate_shown_count": len(candidate_rows),
        "event_annotation_count": event_annotation_count,
        "missing_event_annotation_count": missing_event_annotation_count,
        "unique_ticker_count": len(ticker_counts),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "playbook_counts": dict(sorted(playbook_counts.items())),
        "event_annotation_field_counts": dict(sorted(field_counts.items())),
        "proof_live_exact_entry_count": sum(1 for row in candidate_rows if _is_proof_live_exact_entry(row)),
        "paper_fill_recorded_count": sum(
            1 for row in candidate_rows if _norm(row.get("fill_outcome")) == "paper_fill_recorded"
        ),
        "true_event_replay_pnl_count": true_event_count,
        "post_event_vol_crush_replay_pnl_count": post_event_vol_count,
        "spine_row_count": len(spine_rows),
        "blockers": sorted(set(blockers)),
        "promotion_ready": False,
        "operator_status": "built_collecting_event_annotations_and_exact_pnl"
        if candidate_rows
        else "waiting_for_regular_options_event_spine_seeds",
    }


def build_report(
    *,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    fill_rows, fill_meta = _load_jsonl(fill_attempts_path)
    missing_required = [] if fill_meta.get("status") == "loaded" else ["fill_attempts"]
    live_policy_change = _has_live_policy_change(fill_rows)
    candidates = [] if missing_required or live_policy_change else _candidate_rows(fill_rows)
    rows = _spine_rows(candidates)
    if live_policy_change:
        status = INVALID_STATUS
    elif missing_required:
        status = MISSING_STATUS
    elif candidates:
        status = BUILT_STATUS
    else:
        status = EMPTY_STATUS
    summary = _summary(
        status=status,
        fill_meta=fill_meta,
        missing_required=missing_required,
        live_policy_change=live_policy_change,
        candidate_rows=candidates,
        spine_rows=rows,
    )
    latest = candidates[-1] if candidates else {}
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_event_data_spine_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {"fill_attempts": fill_meta},
        "latest_seed": _latest_seed(latest) if latest else {},
        "event_spine_rows": rows,
        "next_evidence_queue": _next_evidence_queue(summary),
        "evidence_boundary": {
            "readback_is": "read-only regular-options event annotation and post-event vol-crush replay spine",
            "readback_is_not": "broker action, DB mutation, scanner policy change, stop change, sizing change, threshold tuning, proof-bar change, or lane promotion",
            "trusted_proof_standard": "production proof requires trusted intraday exact-contract OPRA/NBBO bid/ask plus executable entry, fill, event annotation, and exit P&L",
            "current_limit": "event rows are diagnostic until durable event-calendar annotations and true executable post-event P&L rows exist",
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
        "# Regular Options Event Data Spine",
        "",
        "This report is generated from `scripts/build_regular_options_event_data_spine.py`. It inventories regular-options candidate rows for durable event-calendar and post-event volatility-crush replay coverage without creating trades, changing policy, tuning thresholds, mutating rows, or treating research/backfill/midpoint evidence as production proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Candidate-shown rows: `{summary.get('candidate_shown_count')}`.",
        f"- Event-annotated rows: `{summary.get('event_annotation_count')}`.",
        f"- Missing event annotations: `{summary.get('missing_event_annotation_count')}`.",
        f"- Unique tickers: `{summary.get('unique_ticker_count')}`.",
        f"- Proof-live exact entry rows: `{summary.get('proof_live_exact_entry_count')}`.",
        f"- Paper fill recorded rows: `{summary.get('paper_fill_recorded_count')}`.",
        f"- True event replay P&L rows: `{summary.get('true_event_replay_pnl_count')}`.",
        f"- Post-event vol-crush replay P&L rows: `{summary.get('post_event_vol_crush_replay_pnl_count')}`.",
        f"- Spine rows: `{summary.get('spine_row_count')}`.",
        f"- Event annotation fields: `{_json_inline(summary.get('event_annotation_field_counts') or {})}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Spine Rows",
        "",
        "| Ticker | Playbook | Expiry | Candidates | Annotated | Missing Annotations | Exact Entries | Paper Fills | True Event P&L | Post-Event P&L |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in _as_list(report.get("event_spine_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('ticker'))}`",
                    f"`{_cell(row.get('playbook_id'))}`",
                    f"`{_cell(row.get('expiry'))}`",
                    _cell(row.get("candidate_shown_count")),
                    _cell(row.get("event_annotation_count")),
                    _cell(row.get("missing_event_annotation_count")),
                    _cell(row.get("proof_live_exact_entry_count")),
                    _cell(row.get("paper_fill_recorded_count")),
                    _cell(row.get("true_event_replay_pnl_count")),
                    _cell(row.get("post_event_vol_crush_replay_pnl_count")),
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
            "This spine is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, tune event thresholds, lower exact OPRA/NBBO proof bars, or count daily/EOD, midpoint, stale, last-trade, display marks, migrated paper, or research/backfill rows as production proof.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options event data spine.")
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(fill_attempts_path=args.fill_attempts)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
