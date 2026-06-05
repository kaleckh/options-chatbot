from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.regular_options_repair_targets import repair_attempt_key  # noqa: E402


DEFAULT_PROFIT_CAPTURE_QUEUE = (
    ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
)
DEFAULT_REPAIR_ATTEMPTS = ROOT / "data" / "profitability-lab" / "regular-options-repair-attempts" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-repair-burndown"
DEFAULT_DOC = ROOT / "docs" / "regular-options-repair-burndown.md"

STATUS_ACTIVE_UNATTEMPTED = "active_unattempted_exact_repair"
STATUS_ACTIVE_PLAN_ONLY = "active_plan_only_needs_provider_dry_run"
STATUS_SOURCE_REPLAY_REQUIRED = "source_replay_required_before_graduation"
STATUS_DIAGNOSTIC_LOOKAHEAD_ONLY = "diagnostic_lookahead_only_not_exact_proof"
STATUS_EXHAUSTED_CURRENT_SOURCE = "excluded_current_source_exhausted"
STATUS_TARGET_DETAILS_MISSING = "excluded_target_details_missing"
STATUS_MEMORY_UNAVAILABLE = "excluded_repair_attempt_memory_unavailable"

ACTIVE_STATUSES = {STATUS_ACTIVE_UNATTEMPTED, STATUS_ACTIVE_PLAN_ONLY}
EXACT_ROWS_OUTCOMES = {"exact_date_rows_found", "imported_pending_replay"}
EXACT_ROWS_PROOF_STATUSES = {"exact_date_repair_candidate", "exact_date_imported_pending_replay"}
LOOKAHEAD_OUTCOMES = {"lookahead_only_rows_found"}
LOOKAHEAD_PROOF_STATUSES = {"lookahead_only_not_exact_proof"}
EXHAUSTED_OUTCOMES = {"exact_date_no_match"}
EXHAUSTED_PROOF_STATUSES = {"current_source_exhausted"}
PLAN_ONLY_OUTCOMES = {"planned_not_requested"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(_safe_float(value), digits)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except Exception as exc:
        return {"missing": True, "path": str(path), "error": f"unreadable:{type(exc).__name__}:{exc}"}
    if isinstance(payload, dict):
        payload.setdefault("path", str(path))
        return payload
    return {"missing": True, "path": str(path), "error": "json_root_not_object"}


def _input_entry(path: Path, source_type: str) -> dict[str, Any]:
    entry = {
        "source_type": source_type,
        "path": _rel(path),
        "exists": path.exists(),
        "generated_at_utc": None,
        "status": "missing",
    }
    if not path.exists():
        return entry
    try:
        payload = _load_json(path)
    except Exception as exc:
        entry["status"] = f"unreadable:{exc}"
        return entry
    entry["generated_at_utc"] = payload.get("generated_at_utc")
    if payload.get("error"):
        entry["status"] = str(payload.get("error"))
    else:
        entry["status"] = "ok" if not payload.get("missing") else "missing"
    return entry


def _key_parts(value: str) -> dict[str, str]:
    source_artifact, ticker, contract_symbol, missing_quote_date = (str(value).split("|", 3) + ["", "", "", ""])[
        :4
    ]
    return {
        "source_artifact": source_artifact,
        "ticker": ticker.upper(),
        "contract_symbol": contract_symbol.upper(),
        "missing_quote_date": missing_quote_date[:10],
    }


def _attempt_indexes(repair_attempts: dict[str, Any]) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    by_target: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in repair_attempts.get("latest_attempts") or repair_attempts.get("repair_attempts") or []:
        if not isinstance(row, dict):
            continue
        keys = row.get("repair_attempt_keys") or [row.get("repair_attempt_key")]
        for raw_key in [str(key) for key in keys if key]:
            parts = _key_parts(raw_key)
            by_key[raw_key] = row
            by_target.setdefault(
                (parts["ticker"], parts["contract_symbol"], parts["missing_quote_date"]),
                [],
            ).append(row)
    return {"by_key": by_key, "by_target": by_target}


def _attempt_key_for_target(target: dict[str, Any], contract_symbol: str) -> str:
    return repair_attempt_key(
        source_artifact=str(target.get("source_artifact") or ""),
        ticker=str(target.get("ticker") or ""),
        contract_symbol=str(contract_symbol or ""),
        missing_quote_date=str(target.get("missing_quote_date") or ""),
    )


def _attempt_contract(attempt: dict[str, Any]) -> str:
    if attempt.get("contract_symbol"):
        return str(attempt.get("contract_symbol") or "").upper()
    key = str(attempt.get("repair_attempt_key") or "")
    return _key_parts(key)["contract_symbol"] if key else ""


def _compact_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    key = str(attempt.get("repair_attempt_key") or "")
    parts = _key_parts(key) if key else {}
    return {
        "repair_attempt_key": attempt.get("repair_attempt_key"),
        "summary_path": attempt.get("summary_path"),
        "summary_generated_at_utc": attempt.get("summary_generated_at_utc"),
        "outcome": attempt.get("outcome"),
        "proof_repair_status": attempt.get("proof_repair_status"),
        "exact_missing_date_status": attempt.get("exact_missing_date_status"),
        "exact_date_row_count": _safe_int(attempt.get("exact_date_row_count")),
        "lookahead_row_count": _safe_int(attempt.get("lookahead_row_count")),
        "total_row_count": _safe_int(attempt.get("total_row_count")),
        "first_available_after_missing_date": attempt.get("first_available_after_missing_date"),
        "available_quote_dates": list(attempt.get("available_quote_dates") or []),
        "current_source_exhausted_for_exact_date": bool(attempt.get("current_source_exhausted_for_exact_date")),
        "contract_symbol": attempt.get("contract_symbol") or parts.get("contract_symbol"),
        "missing_quote_date": attempt.get("missing_quote_date") or parts.get("missing_quote_date"),
    }


def _contract_attempts(
    *,
    target: dict[str, Any],
    contract_symbol: str,
    attempt_index: dict[str, Any],
) -> list[dict[str, Any]]:
    source_attempts = [
        attempt
        for attempt in target.get("latest_repair_attempts") or []
        if not _attempt_contract(attempt) or _attempt_contract(attempt) == str(contract_symbol).upper()
    ]
    key = _attempt_key_for_target(target, contract_symbol)
    indexed_attempts: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = attempt_index.get("by_key") or {}
    by_target: dict[tuple[str, str, str], list[dict[str, Any]]] = attempt_index.get("by_target") or {}
    if key in by_key:
        indexed_attempts.append(by_key[key])
    indexed_attempts.extend(
        by_target.get(
            (
                str(target.get("ticker") or "").upper(),
                str(contract_symbol or "").upper(),
                str(target.get("missing_quote_date") or "")[:10],
            ),
            [],
        )
    )

    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for attempt in [*source_attempts, *indexed_attempts]:
        if not isinstance(attempt, dict):
            continue
        compact = _compact_attempt(attempt)
        identity = (
            str(compact.get("repair_attempt_key") or ""),
            str(compact.get("summary_generated_at_utc") or ""),
            str(compact.get("outcome") or ""),
        )
        if identity in seen:
            continue
        seen.add(identity)
        attempts.append(compact)
    attempts.sort(
        key=lambda row: (
            str(row.get("summary_generated_at_utc") or ""),
            str(row.get("repair_attempt_key") or ""),
        ),
        reverse=True,
    )
    return attempts


def _attempt_sets(attempts: list[dict[str, Any]]) -> dict[str, set[str]]:
    return {
        "outcomes": {str(attempt.get("outcome") or "") for attempt in attempts if attempt.get("outcome")},
        "proof_statuses": {
            str(attempt.get("proof_repair_status") or "")
            for attempt in attempts
            if attempt.get("proof_repair_status")
        },
    }


def _target_burndown_status(
    *,
    row_actionability_status: str,
    attempts: list[dict[str, Any]],
) -> str:
    sets = _attempt_sets(attempts)
    outcomes = sets["outcomes"]
    proof_statuses = sets["proof_statuses"]
    exact_rows_found = any(_safe_int(attempt.get("exact_date_row_count")) > 0 for attempt in attempts)
    if exact_rows_found or outcomes & EXACT_ROWS_OUTCOMES or proof_statuses & EXACT_ROWS_PROOF_STATUSES:
        return STATUS_SOURCE_REPLAY_REQUIRED
    if outcomes & LOOKAHEAD_OUTCOMES or proof_statuses & LOOKAHEAD_PROOF_STATUSES:
        return STATUS_DIAGNOSTIC_LOOKAHEAD_ONLY
    if (
        row_actionability_status == "current_source_exhausted"
        or outcomes & EXHAUSTED_OUTCOMES
        or proof_statuses & EXHAUSTED_PROOF_STATUSES
        or (attempts and all(bool(attempt.get("current_source_exhausted_for_exact_date")) for attempt in attempts))
    ):
        return STATUS_EXHAUSTED_CURRENT_SOURCE
    if outcomes & PLAN_ONLY_OUTCOMES:
        return STATUS_ACTIVE_PLAN_ONLY
    return STATUS_ACTIVE_UNATTEMPTED


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "exact_trusted_priced_trades": _safe_int(metrics.get("exact_trusted_priced_trades")),
        "unresolved_rows": _safe_int(metrics.get("unresolved_rows")),
        "quote_coverage": _round(metrics.get("quote_coverage")),
        "profit_factor": _round(metrics.get("profit_factor")),
        "avg_pnl": _round(metrics.get("avg_pnl")),
        "median_pnl": _round(metrics.get("median_pnl")),
    }


def _command_quote(value: str) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(char.isspace() for char in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _target_commands(row: dict[str, Any]) -> dict[str, str]:
    source = _command_quote(str(row.get("source_artifact") or ""))
    ticker = _command_quote(str(row.get("symbol") or ""))
    contract = _command_quote(str(row.get("contract_symbol") or ""))
    quote_date = _command_quote(str(row.get("missing_quote_date") or ""))
    base = (
        "uv run --locked python scripts\\import_missing_replay_quotes_from_thetadata.py "
        f"{source} --ticker {ticker} --contract-symbol {contract} --quote-date {quote_date}"
    )
    return {
        "plan_only": f"{base} --plan-only --json",
        "exact_dry_run": f"{base} --dry-run --json",
        "lookahead_diagnostic_dry_run": f"{base} --lookahead-calendar-days 5 --dry-run --json",
    }


def _row_rank(row: dict[str, Any]) -> tuple[Any, ...]:
    status = str(row.get("burndown_status") or "")
    priority = str(row.get("evidence_repair_priority") or "")
    return (
        0 if status == STATUS_SOURCE_REPLAY_REQUIRED else 1 if status in ACTIVE_STATUSES else 2,
        0 if priority == "high" else 1 if priority == "medium" else 2,
        -_safe_float(row.get("rank_score")),
        -_safe_float((row.get("metrics") or {}).get("avg_pnl")),
        str(row.get("symbol") or ""),
        str(row.get("missing_quote_date") or ""),
        str(row.get("contract_symbol") or ""),
    )


def _row_identity(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("burndown_status") or ""),
        str(row.get("symbol") or ""),
        str(row.get("lane_id") or ""),
        str(row.get("source_artifact") or ""),
        str(row.get("missing_quote_date") or ""),
        str(row.get("contract_symbol") or ""),
        str(row.get("missing_leg_role") or ""),
        str(row.get("unpriced_reason") or ""),
    )


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        identity = _row_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(row)
    return unique


def _target_rows(profit_queue: dict[str, Any], repair_attempts: dict[str, Any]) -> list[dict[str, Any]]:
    attempt_index = _attempt_indexes(repair_attempts)
    rows: list[dict[str, Any]] = []
    for queue_row in profit_queue.get("evidence_repair_queue") or []:
        if not isinstance(queue_row, dict):
            continue
        repair_summary = queue_row.get("repair_target_summary") if isinstance(queue_row.get("repair_target_summary"), dict) else {}
        repair_actionability = (
            queue_row.get("repair_actionability") if isinstance(queue_row.get("repair_actionability"), dict) else {}
        )
        actionability_status = str(repair_actionability.get("status") or "")
        metrics = _compact_metrics(queue_row.get("metrics") if isinstance(queue_row.get("metrics"), dict) else {})
        common = {
            "symbol": str(queue_row.get("symbol") or "").upper(),
            "lane_id": queue_row.get("lane_id"),
            "lane_family": queue_row.get("lane_family"),
            "capture_tier": queue_row.get("capture_tier"),
            "selection_readiness": queue_row.get("selection_readiness"),
            "evidence_repair_priority": queue_row.get("evidence_repair_priority"),
            "repair_actionability_status": actionability_status,
            "rank_score": _round(queue_row.get("rank_score")),
            "metrics": metrics,
            "blocking_gates": list((queue_row.get("tier_a_promotion_gap") or {}).get("blocking_gates") or []),
            "row_next_step": queue_row.get("next_step"),
        }
        targets = [target for target in repair_summary.get("targets") or [] if isinstance(target, dict)]
        if not targets:
            rows.append(
                {
                    **common,
                    "burndown_status": STATUS_TARGET_DETAILS_MISSING,
                    "detail_status": repair_summary.get("detail_status"),
                    "source_artifacts": list(repair_summary.get("source_artifacts") or []),
                    "latest_attempts": [],
                    "next_action": "Find readable source replay targets before provider repair work.",
                }
            )
            continue
        for target in targets:
            for contract_symbol in target.get("contracts") or []:
                contract = str(contract_symbol or "").upper()
                attempts = _contract_attempts(target=target, contract_symbol=contract, attempt_index=attempt_index)
                status = _target_burndown_status(
                    row_actionability_status=actionability_status,
                    attempts=attempts,
                )
                target_row = {
                    **common,
                    "burndown_status": status,
                    "source_artifact": target.get("source_artifact"),
                    "entry_date": target.get("entry_date"),
                    "missing_quote_date": str(target.get("missing_quote_date") or "")[:10],
                    "contract_symbol": contract,
                    "missing_leg_role": target.get("missing_leg_role"),
                    "unpriced_reason": target.get("unpriced_reason"),
                    "selected_spread": target.get("selected_spread") or {},
                    "latest_attempts": attempts[:5],
                    "latest_attempt_outcomes": sorted(
                        {str(attempt.get("outcome") or "") for attempt in attempts if attempt.get("outcome")}
                    ),
                    "latest_proof_repair_statuses": sorted(
                        {
                            str(attempt.get("proof_repair_status") or "")
                            for attempt in attempts
                            if attempt.get("proof_repair_status")
                        }
                    ),
                }
                target_row["commands"] = _target_commands(target_row)
                if status in ACTIVE_STATUSES:
                    target_row["next_action"] = (
                        "Run the plan-only command first, then exact dry-run/import only if the source can answer the "
                        "same missing contract/date. Rerun the source replay before any graduation discussion."
                    )
                elif status == STATUS_SOURCE_REPLAY_REQUIRED:
                    target_row["next_action"] = (
                        "Exact-date rows are present in repair memory; rerun the source replay and rebuild the queue "
                        "before treating this row as repaired."
                    )
                elif status == STATUS_DIAGNOSTIC_LOOKAHEAD_ONLY:
                    target_row["next_action"] = (
                        "Do not spend another same-source exact repair loop on this lookahead-only result; it is diagnostic, not proof."
                    )
                else:
                    target_row["next_action"] = (
                        "Current source is exhausted for this exact contract/date; retry only with a new source or materially new evidence."
                    )
                rows.append(target_row)
    rows = _dedupe_rows(rows)
    rows.sort(key=_row_rank)
    return rows


def _summary(
    target_rows: list[dict[str, Any]],
    profit_queue: dict[str, Any],
    repair_attempts: dict[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("burndown_status") or "unknown") for row in target_rows)
    priority_counts = Counter(str(row.get("evidence_repair_priority") or "unknown") for row in target_rows)
    actionability_counts = Counter(str(row.get("repair_actionability_status") or "unknown") for row in target_rows)
    symbols = Counter(str(row.get("symbol") or "unknown") for row in target_rows if row.get("symbol"))
    active_rows = [row for row in target_rows if row.get("burndown_status") in ACTIVE_STATUSES]
    replay_rows = [row for row in target_rows if row.get("burndown_status") == STATUS_SOURCE_REPLAY_REQUIRED]
    if status_counts.get(STATUS_MEMORY_UNAVAILABLE):
        next_step = "Rebuild the repair-attempt readback before any provider import or dry-run repair work."
    elif replay_rows:
        next_step = "Rerun source replay for rows with exact-date repair memory before importing more data."
    elif active_rows:
        top = active_rows[0]
        next_step = (
            "Run plan-only for the top unexhausted exact target: "
            f"{(top.get('commands') or {}).get('plan_only')}"
        )
    else:
        next_step = "No keyed unexhausted exact targets remain; use a new exact source before retrying exhausted rows."
    queue_summary = profit_queue.get("summary") if isinstance(profit_queue.get("summary"), dict) else {}
    attempt_summary = repair_attempts.get("summary") if isinstance(repair_attempts.get("summary"), dict) else {}
    return {
        "target_count": len(target_rows),
        "active_exact_repair_target_count": len(active_rows),
        "source_replay_required_target_count": len(replay_rows),
        "diagnostic_lookahead_only_target_count": status_counts.get(STATUS_DIAGNOSTIC_LOOKAHEAD_ONLY, 0),
        "exhausted_current_source_target_count": status_counts.get(STATUS_EXHAUSTED_CURRENT_SOURCE, 0),
        "target_details_missing_count": status_counts.get(STATUS_TARGET_DETAILS_MISSING, 0),
        "repair_attempt_memory_unavailable_count": status_counts.get(STATUS_MEMORY_UNAVAILABLE, 0),
        "burndown_status_counts": dict(sorted(status_counts.items())),
        "evidence_repair_priority_counts": dict(sorted(priority_counts.items())),
        "repair_actionability_counts": dict(sorted(actionability_counts.items())),
        "top_symbols": dict(symbols.most_common(10)),
        "profit_capture_high_priority_repair_count": _safe_int(queue_summary.get("high_priority_evidence_repair_count")),
        "repair_attempt_latest_count": _safe_int(attempt_summary.get("latest_attempt_count")),
        "repair_attempt_input_summary_count": _safe_int(attempt_summary.get("input_summary_count")),
        "next_operator_step": next_step,
        "live_policy_change": False,
    }


def build_report(
    *,
    profit_capture_queue_path: Path = DEFAULT_PROFIT_CAPTURE_QUEUE,
    repair_attempts_path: Path = DEFAULT_REPAIR_ATTEMPTS,
) -> dict[str, Any]:
    profit_queue = _load_json(profit_capture_queue_path)
    repair_attempts = _load_json(repair_attempts_path)
    repair_attempt_memory_available = not repair_attempts.get("missing") and not repair_attempts.get("error")
    targets = _target_rows(profit_queue, repair_attempts) if not profit_queue.get("missing") else []
    if not repair_attempt_memory_available:
        for row in targets:
            row["burndown_status"] = STATUS_MEMORY_UNAVAILABLE
            row["latest_attempts"] = []
            row["latest_attempt_outcomes"] = []
            row["latest_proof_repair_statuses"] = []
            row["commands"] = {}
            row["next_action"] = "Rebuild the repair-attempt readback before provider repair work."
    active_targets = [row for row in targets if row.get("burndown_status") in ACTIVE_STATUSES]
    source_replay = [row for row in targets if row.get("burndown_status") == STATUS_SOURCE_REPLAY_REQUIRED]
    diagnostic = [row for row in targets if row.get("burndown_status") == STATUS_DIAGNOSTIC_LOOKAHEAD_ONLY]
    exhausted = [row for row in targets if row.get("burndown_status") == STATUS_EXHAUSTED_CURRENT_SOURCE]
    missing = [row for row in targets if row.get("burndown_status") == STATUS_TARGET_DETAILS_MISSING]
    memory_unavailable = [row for row in targets if row.get("burndown_status") == STATUS_MEMORY_UNAVAILABLE]
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_options_exact_repair_burndown",
        "status": (
            "repair_burndown_memory_unavailable"
            if targets and not repair_attempt_memory_available
            else "repair_burndown_ready"
            if targets
            else "repair_burndown_no_targets"
        ),
        "live_policy_change": False,
        "proof_policy": {
            "active_targets": "Only unexhausted exact missing contract/date targets are active repair work.",
            "lookahead_only": "Lookahead-only rows are diagnostics and do not repair the exact proof date.",
            "current_source_exhausted": "Do not repeat a provider no-match loop unless a new exact source or materially new evidence exists.",
            "source_replay_required": "Exact-date rows in repair memory still require rerunning the source replay before Tier B can graduate.",
            "not_a_policy_change": "This report does not change scanner policy, broker behavior, stop policy, auth, DB schema, proof bars, or trade recommendation, entry/exit, or sizing behavior.",
            "missing_memory": "Missing or unreadable repair-attempt memory fails closed and produces no active provider commands.",
        },
        "inputs": [
            _input_entry(profit_capture_queue_path, "regular_options_profit_capture_queue"),
            _input_entry(repair_attempts_path, "regular_options_repair_attempt_readback"),
        ],
        "summary": _summary(targets, profit_queue, repair_attempts),
        "active_exact_repair_targets": active_targets,
        "source_replay_required_targets": source_replay,
        "diagnostic_lookahead_only_targets": diagnostic,
        "exhausted_current_source_targets": exhausted,
        "target_details_missing_rows": missing,
        "repair_attempt_memory_unavailable_rows": memory_unavailable,
        "final_readback": {
            "top_active_exact_repair_targets": active_targets[:20],
            "source_replay_required_targets": source_replay[:20],
            "diagnostic_lookahead_only_targets": diagnostic[:20],
            "exhausted_current_source_targets": exhausted[:20],
            "target_details_missing_rows": missing[:20],
            "repair_attempt_memory_unavailable_rows": memory_unavailable[:20],
        },
    }


def _target_table(rows: list[dict[str, Any]], limit: int = 30) -> list[str]:
    lines = [
        "| Status | Priority | Symbol | Lane | Missing date | Contract | Exact | Unres | PF | Avg % | Attempts | Next |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows[:limit]:
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("burndown_status")),
                    _fmt(row.get("evidence_repair_priority")),
                    _fmt(row.get("symbol")),
                    _fmt(row.get("lane_id")),
                    _fmt(row.get("missing_quote_date")),
                    _fmt(row.get("contract_symbol")),
                    _fmt(metrics.get("exact_trusted_priced_trades")),
                    _fmt(metrics.get("unresolved_rows")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("avg_pnl")),
                    _fmt(len(row.get("latest_attempts") or [])),
                    _fmt(row.get("next_action")),
                ]
            )
            + " |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    final = report.get("final_readback") or {}
    lines = [
        "# Regular Options Exact Repair Burn-Down",
        "",
        "This report is generated from `scripts/build_regular_options_repair_burndown.py`. It ranks exact-date proof repair work for regular supervised options and keeps exhausted or lookahead-only rows out of the active import loop. It is not a trade recommendation, entry/exit instruction, or sizing signal.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Active exact repair targets: `{summary.get('active_exact_repair_target_count')}`.",
        f"- Source replay required targets: `{summary.get('source_replay_required_target_count')}`.",
        f"- Diagnostic lookahead-only targets: `{summary.get('diagnostic_lookahead_only_target_count')}`.",
        f"- Exhausted current-source targets: `{summary.get('exhausted_current_source_target_count')}`.",
        f"- Missing target-detail rows: `{summary.get('target_details_missing_count')}`.",
        f"- Repair-attempt memory unavailable rows: `{summary.get('repair_attempt_memory_unavailable_count')}`.",
        f"- Burn-down statuses: `{json.dumps(summary.get('burndown_status_counts') or {}, sort_keys=True)}`.",
        f"- Evidence repair priorities: `{json.dumps(summary.get('evidence_repair_priority_counts') or {}, sort_keys=True)}`.",
        f"- Latest keyed repair attempts: `{summary.get('repair_attempt_latest_count')}` from `{summary.get('repair_attempt_input_summary_count')}` summaries.",
        f"- Next operator step: {summary.get('next_operator_step')}",
        f"- Live policy change: `{report.get('live_policy_change')}`.",
        "",
        "## Proof Policy",
        "",
        "- Active work is limited to unexhausted exact missing contract/date targets.",
        "- Lookahead-only rows are diagnostic and never repair the exact missing proof date.",
        "- Current-source no-match rows must not be repeated without a new exact source or materially new evidence.",
        "- Exact-date rows already found or imported still require rerunning the source replay and rebuilding the queue before any Tier B graduation discussion.",
        "- Missing or unreadable repair-attempt memory fails closed and emits no active provider commands.",
        "- This report is paper/proof repair memory only; it does not alter scanner, broker, stop, auth, database, proof-bar, trade recommendation, entry/exit, or sizing behavior.",
        "",
        "## Active Exact Repair Targets",
        "",
        *_target_table(final.get("top_active_exact_repair_targets") or [], limit=30),
        "",
        "## Source Replay Required",
        "",
        *_target_table(final.get("source_replay_required_targets") or [], limit=30),
        "",
        "## Diagnostic Lookahead Only",
        "",
        *_target_table(final.get("diagnostic_lookahead_only_targets") or [], limit=30),
        "",
        "## Exhausted Current Source",
        "",
        *_target_table(final.get("exhausted_current_source_targets") or [], limit=30),
        "",
        "## Target Details Missing",
        "",
        *_target_table(final.get("target_details_missing_rows") or [], limit=30),
        "",
        "## Repair-Attempt Memory Unavailable",
        "",
        *_target_table(final.get("repair_attempt_memory_unavailable_rows") or [], limit=30),
        "",
        "## Inputs",
        "",
        "| Source | Status | Generated | Path |",
        "|---|---|---|---|",
    ]
    for entry in report.get("inputs") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(entry.get("source_type")),
                    _fmt(entry.get("status")),
                    _fmt(entry.get("generated_at_utc")),
                    _fmt(entry.get("path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"regular_options_repair_burndown_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_repair_burndown_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(markdown_path),
        "latest_markdown": str(latest_markdown),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    doc_path.write_text(markdown, encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options exact repair burn-down readback.")
    parser.add_argument("--profit-capture-queue", type=Path, default=DEFAULT_PROFIT_CAPTURE_QUEUE)
    parser.add_argument("--repair-attempts", type=Path, default=DEFAULT_REPAIR_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        profit_capture_queue_path=args.profit_capture_queue,
        repair_attempts_path=args.repair_attempts,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    else:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
