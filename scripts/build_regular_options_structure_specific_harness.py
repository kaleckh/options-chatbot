from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_structure_specific_harness"

DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_MINUTE_EXIT_REPLAY = (
    ROOT / "data" / "forward-tracking" / "regular_options_minute_exit_replay_readiness_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-structure-specific-harness.md"

BUILT_STATUS = "structure_specific_harness_built_collecting"
EMPTY_STATUS = "structure_specific_harness_empty_collecting"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_structure_specific_harness",
    "do_not_submit_broker_order_from_structure_specific_harness",
    "do_not_mutate_database_from_structure_specific_harness",
    "do_not_change_scanner_policy_from_structure_specific_harness",
    "do_not_change_stop_policy_from_structure_specific_harness",
    "do_not_change_sizing_from_structure_specific_harness",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_structure_specific_harness",
    "do_not_count_midpoint_daily_stale_last_trade_or_research_backfill_as_structure_proof",
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


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        parsed = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        meta["status"] = "invalid_json"
        meta["error"] = "JSONDecodeError"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(parsed, dict):
        meta["status"] = "invalid_shape"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = parsed.get("generated_at_utc")
    meta["source_status"] = parsed.get("status")
    rows = _as_list(parsed.get("minute_exit_replay_rows"))
    meta["minute_exit_replay_row_count"] = len([row for row in rows if isinstance(row, dict)])
    return parsed, meta


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


def _strategy_type(row: dict[str, Any]) -> str:
    selected = _as_dict(row.get("selected_spread"))
    return _norm(row.get("strategy_type") or selected.get("strategy_type")) or "unknown"


def _leg_count(row: dict[str, Any]) -> int:
    selected = _as_dict(row.get("selected_spread"))
    legs = _as_list(selected.get("legs")) or _as_list(row.get("legs"))
    if legs:
        return len(legs)
    if selected.get("long_contract_symbol") and selected.get("short_contract_symbol"):
        return 2
    if selected.get("contract_symbol") or row.get("contract_symbol"):
        return 1
    return 0


def _structure_bucket(row: dict[str, Any]) -> str:
    strategy = _strategy_type(row).lower()
    legs = _leg_count(row)
    if strategy in {"single_leg", "single_option", "long_call", "long_put", "call", "put"} or legs == 1:
        return "single_leg"
    if "vertical" in strategy or (
        legs == 2
        and _as_dict(row.get("selected_spread")).get("long_contract_symbol")
        and _as_dict(row.get("selected_spread")).get("short_contract_symbol")
    ):
        return "vertical_spread"
    if strategy == "unknown" and legs == 0:
        return "unknown"
    if legs > 1 or strategy not in {"", "unknown"}:
        return "multi_leg_other"
    return "unknown"


def _has_top_alternative(row: dict[str, Any]) -> bool:
    return bool(_as_list(row.get("top_alternatives")) or _as_list(row.get("top_spread_alternatives")))


def _is_proof_live_exact_entry(row: dict[str, Any]) -> bool:
    return _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"


def _has_true_structure_pnl(row: dict[str, Any]) -> bool:
    exit_result = _as_dict(row.get("exit_result"))
    if not exit_result:
        return False
    pnl_ready = any(
        _safe_float(exit_result.get(key)) is not None
        for key in ("net_pnl_pct", "net_pnl_usd", "realized_pnl_pct", "realized_pnl_usd")
    )
    if not pnl_ready:
        return False
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
    trusted_exit = "proof_live_opra_exact_contract" in exit_evidence or ("opra" in exit_evidence and "bid" in exit_evidence)
    return (
        _is_proof_live_exact_entry(row)
        and _norm(row.get("fill_outcome")) == "paper_fill_recorded"
        and _safe_float(row.get("filled_price")) is not None
        and trusted_exit
    )


def _contract_pair(row: dict[str, Any]) -> tuple[str, str] | None:
    selected = _as_dict(row.get("selected_spread"))
    long_symbol = _norm(selected.get("long_contract_symbol") or row.get("long_contract_symbol"))
    short_symbol = _norm(selected.get("short_contract_symbol") or row.get("short_contract_symbol"))
    if not long_symbol or not short_symbol:
        return None
    return long_symbol, short_symbol


def _quote_is_trusted_bid_ask(quote: Any) -> bool:
    quote = _as_dict(quote)
    evidence = _norm(quote.get("quote_evidence_class")).lower()
    source = _norm(quote.get("source_label") or quote.get("quote_source") or quote.get("data_source")).lower()
    return (
        _safe_float(quote.get("bid")) is not None
        and _safe_float(quote.get("ask")) is not None
        and bool(_norm(quote.get("contract_symbol")))
        and bool(_norm(quote.get("as_of_utc") or quote.get("quote_time_utc")))
        and ("trusted_intraday_opra_nbbo" in evidence or ("opra" in source and "nbbo" in source))
    )


def _minute_row_has_true_side_aware_pnl(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("true_side_aware_pnl_available"))
        and bool(row.get("entry_pair_complete"))
        and bool(row.get("exit_pair_complete"))
        and _safe_float(row.get("entry_side_aware_debit")) is not None
        and _safe_float(row.get("exit_side_aware_value")) is not None
        and _safe_float(row.get("gross_pnl_per_spread")) is not None
        and _quote_is_trusted_bid_ask(row.get("entry_long_quote"))
        and _quote_is_trusted_bid_ask(row.get("entry_short_quote"))
        and _quote_is_trusted_bid_ask(row.get("exit_long_quote"))
        and _quote_is_trusted_bid_ask(row.get("exit_short_quote"))
    )


def _minute_rows_by_contract(minute_report: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in _as_list(minute_report.get("minute_exit_replay_rows")):
        row = _as_dict(item)
        pair = _contract_pair(row)
        if pair and _minute_row_has_true_side_aware_pnl(row):
            rows[pair].append(row)
    return rows


def _matching_minute_row(
    candidate: dict[str, Any],
    minute_rows_by_pair: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    pair = _contract_pair(candidate)
    if not pair:
        return None
    possible = minute_rows_by_pair.get(pair) or []
    if not possible:
        return None
    candidate_position_id = candidate.get("auto_track_position_id")
    if candidate_position_id is not None:
        for row in possible:
            if row.get("auto_track_position_id") == candidate_position_id:
                return row
    candidate_scan_date = _norm(candidate.get("scan_date"))
    candidate_lane = _norm(candidate.get("playbook_id"))
    for row in possible:
        if _norm(row.get("scan_date")) == candidate_scan_date and _norm(row.get("lane")) == candidate_lane:
            return row
    for row in possible:
        if _norm(row.get("scan_date")) == candidate_scan_date:
            return row
    return possible[0]


def _quote_payload(row: dict[str, Any], key: str) -> dict[str, Any]:
    quote = _as_dict(row.get(key))
    return {
        "contract_symbol": quote.get("contract_symbol"),
        "as_of_utc": quote.get("as_of_utc") or quote.get("quote_time_utc"),
        "quote_date_et": quote.get("quote_date_et"),
        "quote_minute_et": quote.get("quote_minute_et"),
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "source_label": quote.get("source_label"),
        "quote_evidence_class": quote.get("quote_evidence_class"),
        "data_trust": quote.get("data_trust"),
    }


def _structure_pnl_row(candidate: dict[str, Any], minute_row: dict[str, Any]) -> dict[str, Any]:
    pair = _contract_pair(candidate) or (_norm(minute_row.get("long_contract_symbol")), _norm(minute_row.get("short_contract_symbol")))
    return {
        "structure_bucket": _structure_bucket(candidate),
        "strategy_type": _strategy_type(candidate),
        "ticker": candidate.get("ticker") or minute_row.get("ticker"),
        "lane": candidate.get("playbook_id") or minute_row.get("lane"),
        "scan_date": candidate.get("scan_date") or minute_row.get("scan_date"),
        "auto_track_position_id": candidate.get("auto_track_position_id") or minute_row.get("auto_track_position_id"),
        "long_contract_symbol": pair[0],
        "short_contract_symbol": pair[1],
        "entry_quote_date_et": minute_row.get("entry_quote_date_et"),
        "entry_quote_minute_et": minute_row.get("entry_quote_minute_et"),
        "exit_quote_date_et": minute_row.get("exit_quote_date_et"),
        "exit_quote_minute_et": minute_row.get("exit_quote_minute_et"),
        "entry_long_quote": _quote_payload(minute_row, "entry_long_quote"),
        "entry_short_quote": _quote_payload(minute_row, "entry_short_quote"),
        "exit_long_quote": _quote_payload(minute_row, "exit_long_quote"),
        "exit_short_quote": _quote_payload(minute_row, "exit_short_quote"),
        "entry_side_aware_debit": minute_row.get("entry_side_aware_debit"),
        "exit_side_aware_value": minute_row.get("exit_side_aware_value"),
        "gross_pnl_per_spread": minute_row.get("gross_pnl_per_spread"),
        "gross_pnl_pct": minute_row.get("gross_pnl_pct"),
        "contract_quantity": minute_row.get("contract_quantity"),
        "fees_slippage_assumption": minute_row.get("fees_slippage_assumption"),
        "decision": minute_row.get("decision"),
        "decision_reason": minute_row.get("decision_reason"),
        "source_replay_status": minute_row.get("readiness_status"),
        "source_row_index": minute_row.get("row_index"),
        "true_executable_pnl": True,
        "production_proof": False,
        "production_proof_reason": "read_only_minute_replay_is_not_broker_fill_or_current_open_risk_resolution",
        "read_only": True,
    }


def _structure_pnl_rows(
    candidate_rows: list[dict[str, Any]],
    minute_rows_by_pair: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidate_rows:
        minute_row = _matching_minute_row(candidate, minute_rows_by_pair)
        if minute_row:
            rows.append(_structure_pnl_row(candidate, minute_row))
    return rows


def _latest_candidate(row: dict[str, Any]) -> dict[str, Any]:
    selected = _as_dict(row.get("selected_spread"))
    return {
        "logged_at": row.get("logged_at"),
        "scan_date": row.get("scan_date"),
        "playbook_id": row.get("playbook_id"),
        "ticker": row.get("ticker") or selected.get("ticker"),
        "direction": row.get("direction") or selected.get("direction"),
        "strategy_type": _strategy_type(row),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "auto_track_position_id": row.get("auto_track_position_id"),
        "selection_source": row.get("selection_source"),
        "pricing_evidence_class": row.get("pricing_evidence_class"),
    }


def _group_rows(candidate_rows: list[dict[str, Any]], structure_pnl_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        grouped[(_structure_bucket(row), _strategy_type(row))].append(row)
    pnl_counts = Counter(
        (_norm(row.get("structure_bucket")) or "unknown", _norm(row.get("strategy_type")) or "unknown")
        for row in structure_pnl_rows
    )
    pnl_decisions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in structure_pnl_rows:
        key = (_norm(row.get("structure_bucket")) or "unknown", _norm(row.get("strategy_type")) or "unknown")
        pnl_decisions[key][_norm(row.get("decision")) or "unknown"] += 1
    rows = []
    for (bucket, strategy), items in sorted(grouped.items()):
        fill_status_counts = Counter(_norm(row.get("fill_status")) or "unknown" for row in items)
        fill_outcome_counts = Counter(_norm(row.get("fill_outcome")) or "unknown" for row in items)
        source_counts = Counter(_norm(row.get("selection_source")) or "unknown" for row in items)
        latest = items[-1] if items else {}
        rows.append(
            {
                "structure_bucket": bucket,
                "strategy_type": strategy,
                "candidate_shown_count": len(items),
                "selected_spread_count": sum(1 for row in items if isinstance(row.get("selected_spread"), dict)),
                "top_alternative_count": sum(1 for row in items if _has_top_alternative(row)),
                "proof_live_exact_entry_count": sum(1 for row in items if _is_proof_live_exact_entry(row)),
                "paper_fill_recorded_count": sum(
                    1 for row in items if _norm(row.get("fill_outcome")) == "paper_fill_recorded"
                ),
                "auto_tracked_count": sum(1 for row in items if row.get("auto_track_position_id") is not None),
                "true_structure_specific_pnl_count": pnl_counts.get((bucket, strategy), 0),
                "structure_pnl_decision_counts": dict(sorted(pnl_decisions.get((bucket, strategy), Counter()).items())),
                "fill_status_counts": dict(sorted(fill_status_counts.items())),
                "fill_outcome_counts": dict(sorted(fill_outcome_counts.items())),
                "selection_source_counts": dict(sorted(source_counts.items())),
                "latest_candidate": _latest_candidate(latest) if latest else {},
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
                "action": "collect_structure_labeled_fill_attempts",
                "count": 1,
                "reason": "no_structure_labeled_candidate_shown_rows",
                "operator_next_step": "Collect fresh regular-options fill-attempt rows with explicit strategy_type and selected-spread legs.",
            }
        )
        return queue
    if _safe_int(summary.get("true_structure_specific_pnl_count")) == 0:
        queue.append(
            {
                "priority": 7,
                "action": "collect_structure_specific_exact_entry_exit_pnl",
                "count": summary.get("candidate_shown_count"),
                "reason": "structure_buckets_have_no_true_executable_entry_exit_pnl",
                "operator_next_step": "Collect exact-contract OPRA/NBBO executable entry, fill, and exit P&L before any structure-specific promotion claim.",
            }
        )
    if _safe_int(summary.get("single_leg_count")) == 0 or _safe_int(summary.get("multi_leg_other_count")) == 0:
        queue.append(
            {
                "priority": 8,
                "action": "collect_single_leg_or_other_multileg_structure_samples",
                "count": 1,
                "reason": "current_harness_only_has_vertical_spread_candidate_rows",
                "operator_next_step": "Keep vertical-spread evidence separate and collect other structures only as proof-only diagnostics.",
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
    harness_rows: list[dict[str, Any]],
    structure_pnl_rows: list[dict[str, Any]],
    minute_meta: dict[str, Any],
) -> dict[str, Any]:
    strategy_counts = Counter(_strategy_type(row) for row in candidate_rows)
    bucket_counts = Counter(_structure_bucket(row) for row in candidate_rows)
    fill_status_counts = Counter(_norm(row.get("fill_status")) or "unknown" for row in candidate_rows)
    fill_outcome_counts = Counter(_norm(row.get("fill_outcome")) or "unknown" for row in candidate_rows)
    true_pnl_count = len(structure_pnl_rows)
    pnl_decision_counts = Counter(_norm(row.get("decision")) or "unknown" for row in structure_pnl_rows)
    blockers = []
    if not candidate_rows:
        blockers.append("no_candidate_shown_fill_attempt_rows")
    if true_pnl_count == 0:
        blockers.append("true_structure_specific_pnl_rows_missing")
    if bucket_counts.get("vertical_spread", 0) == 0:
        blockers.append("no_vertical_spread_fill_attempt_rows")
    if bucket_counts.get("single_leg", 0) == 0 or bucket_counts.get("multi_leg_other", 0) == 0:
        blockers.append("single_leg_or_other_multileg_samples_missing")
    if bucket_counts.get("unknown", 0):
        blockers.append("unknown_structure_type_rows_present")
    return {
        "overall_status": status,
        "readback_status": "structure_specific_harness_readback",
        "source_fill_attempt_rows": fill_meta.get("row_count"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "candidate_shown_count": len(candidate_rows),
        "selected_spread_count": sum(1 for row in candidate_rows if isinstance(row.get("selected_spread"), dict)),
        "top_alternative_count": sum(1 for row in candidate_rows if _has_top_alternative(row)),
        "proof_live_exact_entry_count": sum(1 for row in candidate_rows if _is_proof_live_exact_entry(row)),
        "paper_fill_recorded_count": sum(
            1 for row in candidate_rows if _norm(row.get("fill_outcome")) == "paper_fill_recorded"
        ),
        "auto_tracked_count": sum(1 for row in candidate_rows if row.get("auto_track_position_id") is not None),
        "true_structure_specific_pnl_count": true_pnl_count,
        "structure_pnl_decision_counts": dict(sorted(pnl_decision_counts.items())),
        "minute_exit_replay_status": minute_meta.get("source_status"),
        "source_minute_exit_replay_rows": minute_meta.get("minute_exit_replay_row_count"),
        "structure_bucket_counts": {key: bucket_counts.get(key, 0) for key in ("vertical_spread", "single_leg", "multi_leg_other", "unknown")},
        "strategy_type_counts": dict(sorted(strategy_counts.items())),
        "fill_status_counts": dict(sorted(fill_status_counts.items())),
        "fill_outcome_counts": dict(sorted(fill_outcome_counts.items())),
        "vertical_spread_count": bucket_counts.get("vertical_spread", 0),
        "single_leg_count": bucket_counts.get("single_leg", 0),
        "multi_leg_other_count": bucket_counts.get("multi_leg_other", 0),
        "unknown_strategy_type_count": strategy_counts.get("unknown", 0),
        "harness_row_count": len(harness_rows),
        "blockers": sorted(set(blockers)),
        "promotion_ready": False,
        "operator_status": (
            "built_collecting_structure_breadth"
            if true_pnl_count
            else "built_collecting_true_structure_pnl"
            if candidate_rows
            else "waiting_for_structure_labeled_candidates"
        ),
    }


def build_report(
    *,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    minute_exit_replay_path: Path = DEFAULT_MINUTE_EXIT_REPLAY,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    fill_rows, fill_meta = _load_jsonl(fill_attempts_path)
    minute_report, minute_meta = _load_json(minute_exit_replay_path)
    missing_required = [] if fill_meta.get("status") == "loaded" else ["fill_attempts"]
    live_policy_change = _has_live_policy_change(fill_rows)
    candidates = [] if missing_required or live_policy_change else _candidate_rows(fill_rows)
    minute_rows_by_pair = {} if missing_required or live_policy_change else _minute_rows_by_contract(minute_report)
    structure_pnl_rows = _structure_pnl_rows(candidates, minute_rows_by_pair)
    harness_rows = _group_rows(candidates, structure_pnl_rows)
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
        harness_rows=harness_rows,
        structure_pnl_rows=structure_pnl_rows,
        minute_meta=minute_meta,
    )
    next_queue = _next_evidence_queue(summary)
    latest = candidates[-1] if candidates else {}
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_structure_specific_harness_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {"fill_attempts": fill_meta, "minute_exit_replay": minute_meta},
        "latest_candidate": _latest_candidate(latest) if latest else {},
        "structure_harness_rows": harness_rows,
        "structure_pnl_rows": structure_pnl_rows,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only structure-specific regular-options evidence harness",
            "readback_is_not": "broker action, DB mutation, scanner policy change, stop change, sizing change, proof-bar change, or lane promotion",
            "trusted_proof_standard": "production proof requires trusted intraday exact-contract OPRA/NBBO bid/ask plus executable entry, fill, and exit P&L",
            "current_limit": "structure P&L rows are read-only minute replay and do not become production proof, promotion, or open-risk resolution without fill/position/current-exit gates",
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
        "# Regular Options Structure-Specific Harness",
        "",
        "This report is generated from `scripts/build_regular_options_structure_specific_harness.py`. It separates regular-options fill-attempt evidence by option structure without creating trades, changing policy, mutating rows, or treating research/backfill/midpoint evidence as production proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Candidate-shown rows: `{summary.get('candidate_shown_count')}`.",
        f"- Structure buckets: `{_json_inline(summary.get('structure_bucket_counts') or {})}`.",
        f"- Strategy types: `{_json_inline(summary.get('strategy_type_counts') or {})}`.",
        f"- Proof-live exact entry rows: `{summary.get('proof_live_exact_entry_count')}`.",
        f"- Paper fill recorded rows: `{summary.get('paper_fill_recorded_count')}`.",
        f"- True structure-specific P&L rows: `{summary.get('true_structure_specific_pnl_count')}`.",
        f"- Structure P&L decisions: `{_json_inline(summary.get('structure_pnl_decision_counts') or {})}`.",
        f"- Harness rows: `{summary.get('harness_row_count')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Harness Rows",
        "",
        "| Bucket | Strategy | Candidates | Selected | Top Alts | Exact Entries | Paper Fills | True P&L | Fill Statuses |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("structure_harness_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('structure_bucket'))}`",
                    f"`{_cell(row.get('strategy_type'))}`",
                    _cell(row.get("candidate_shown_count")),
                    _cell(row.get("selected_spread_count")),
                    _cell(row.get("top_alternative_count")),
                    _cell(row.get("proof_live_exact_entry_count")),
                    _cell(row.get("paper_fill_recorded_count")),
                    _cell(row.get("true_structure_specific_pnl_count")),
                    _cell(_json_inline(row.get("fill_status_counts") or {})),
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
            "## Structure P&L Rows",
            "",
            "| Ticker | Lane | Long | Short | Entry UTC | Entry Bid/Ask | Exit UTC | Exit Bid/Ask | P&L/Spread | Decision |",
            "|---|---|---|---|---|---|---|---|---:|---|",
        ]
    )
    for row in _as_list(report.get("structure_pnl_rows")):
        row = _as_dict(row)
        entry_long = _as_dict(row.get("entry_long_quote"))
        entry_short = _as_dict(row.get("entry_short_quote"))
        exit_long = _as_dict(row.get("exit_long_quote"))
        exit_short = _as_dict(row.get("exit_short_quote"))
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('ticker'))}`",
                    f"`{_cell(row.get('lane'))}`",
                    f"`{_cell(row.get('long_contract_symbol'))}`",
                    f"`{_cell(row.get('short_contract_symbol'))}`",
                    _cell(entry_long.get("as_of_utc")),
                    _cell(f"{entry_long.get('bid')}/{entry_long.get('ask')} ; {entry_short.get('bid')}/{entry_short.get('ask')}"),
                    _cell(exit_long.get("as_of_utc")),
                    _cell(f"{exit_long.get('bid')}/{exit_long.get('ask')} ; {exit_short.get('bid')}/{exit_short.get('ask')}"),
                    _cell(row.get("gross_pnl_per_spread")),
                    f"`{_cell(row.get('decision'))}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This harness is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change stops, change sizing, lower exact OPRA/NBBO proof bars, or count daily/EOD, midpoint, stale, last-trade, display marks, migrated paper, or research/backfill rows as production proof.",
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options structure-specific harness.")
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--minute-exit-replay", type=Path, default=DEFAULT_MINUTE_EXIT_REPLAY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(fill_attempts_path=args.fill_attempts, minute_exit_replay_path=args.minute_exit_replay)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
