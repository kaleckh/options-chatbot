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

from scripts import pending_audit_candidates as pending  # noqa: E402
from scripts import replay_short_term_filter_point_in_time as point_in_time  # noqa: E402
from scripts.candidate_lifecycle import (  # noqa: E402
    STATUS_LIVE_VALIDATION_ATTEMPTED,
    STATUS_LIVE_VALIDATION_SCAN_FAILED,
    STATUS_PENDING_LIVE_VALIDATION,
    candidate_status_spec,
    fresh_evidence_loop_outcome_for_status,
    is_paper_only_status,
)


REPORT_ID = "regular_options_fresh_evidence_loop"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-fresh-evidence-loop.md"
EXACT_EXIT_BASES = {
    "historical_spread_bid_ask",
    "spread_bid_ask",
    "live_spread_bid_ask",
    "auto_sell_review",
}

BRIDGE_READY = "promotion_discussion_ready"
BRIDGE_PAPER_ENTRY_REQUIRED = "paper_probation_exact_entry_required"
BRIDGE_EXACT_EXIT_REQUIRED = "exact_exit_pnl_required"
BRIDGE_NON_EXECUTABLE_ENTRY = "non_executable_entry_blocked"
BRIDGE_NOT_CANDIDATE = "not_evidence_bridge_candidate"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _selected(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    value = row.get("selected_spread")
    return value if isinstance(value, dict) else {}


def _entry_tokens(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    selected = _selected(row)
    parts = [
        row.get("candidate_execution_label"),
        row.get("attempted_limit_basis"),
        row.get("entry_execution_basis"),
        row.get("quote_freshness_status"),
        row.get("options_data_source"),
        row.get("pricing_evidence_class"),
        row.get("selection_source"),
        selected.get("entry_execution_basis"),
        selected.get("quote_freshness_status"),
    ]
    for leg in selected.get("legs") or []:
        if isinstance(leg, dict):
            parts.extend(
                [
                    leg.get("quote_freshness_status"),
                    leg.get("quote_source"),
                    leg.get("data_source"),
                    leg.get("source_feed"),
                ]
            )
    return " ".join(_norm(part).lower() for part in parts)


def _entry_evidence_status(fill_attempt: dict[str, Any] | None) -> tuple[str, list[str]]:
    if not fill_attempt:
        return "fill_attempt_missing", ["no_fill_attempt_logged"]
    tokens = _entry_tokens(fill_attempt)
    basis = _norm(fill_attempt.get("attempted_limit_basis") or fill_attempt.get("entry_execution_basis")).lower()
    reasons: list[str] = []
    if "stale" in tokens:
        reasons.append("stale_entry_evidence")
    if "non_executable" in tokens or "non-executable" in tokens or "non executable" in tokens:
        reasons.append("non_executable_entry_evidence")
    if "manual" in tokens:
        reasons.append("manual_entry_evidence")
    if "fallback" in tokens:
        reasons.append("fallback_entry_evidence")
    if "daily" in tokens or "eod" in tokens:
        reasons.append("daily_or_eod_entry_evidence")
    if basis in {"mid", "midpoint", "midpoint_only", "midpoint-only"} or "midpoint" in tokens or "midpoint_only" in tokens or "midpoint-only" in tokens:
        reasons.append("midpoint_entry_evidence")

    label = _norm(fill_attempt.get("candidate_execution_label")).lower()
    source = _norm(fill_attempt.get("options_data_source")).lower()
    pricing = _norm(fill_attempt.get("pricing_evidence_class")).lower()
    selection = _norm(fill_attempt.get("selection_source")).lower()
    executable_label = "executable" in label and "opra" in label
    executable_basis = basis in {"spread_ask_bid", "spread_bid_ask", "bid_ask", "ask"}
    exact_source = (
        "opra" in source
        or "opra" in pricing
        or "live_chain_exact_contract" in selection
        or "exact_contract" in pricing
    )
    if not executable_label and not executable_basis:
        reasons.append("entry_execution_not_explicit")
    if not exact_source:
        reasons.append("entry_exact_opra_source_missing")

    if any(reason.startswith("stale") for reason in reasons):
        return "stale", sorted(set(reasons))
    if reasons:
        return "non_executable", sorted(set(reasons))
    return "fresh_executable_exact_entry", []


def _stop_rows_by_position(stop_grid: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in stop_grid.get("rows") or []:
        if not isinstance(row, dict):
            continue
        position_id = _safe_int(row.get("position_id") or row.get("trade_id"))
        if position_id is not None:
            rows[position_id] = row
    return rows


def _exit_basis(stop_row: dict[str, Any] | None) -> str:
    if not stop_row:
        return ""
    last = stop_row.get("last_priced_point") if isinstance(stop_row.get("last_priced_point"), dict) else {}
    first = stop_row.get("first_priced_point") if isinstance(stop_row.get("first_priced_point"), dict) else {}
    return _norm(
        stop_row.get("exit_execution_basis")
        or last.get("exit_execution_basis")
        or first.get("exit_execution_basis")
    )


def _realized_pnl_status(
    *,
    position_id: int | None,
    stop_row: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if position_id is None:
        return "no_position_link", {}
    if not stop_row:
        return "missing_realized_pnl", {"position_id": position_id}
    pnl = _safe_float(_first_present(stop_row.get("baseline_pnl_pct"), stop_row.get("pnl_pct"), stop_row.get("net_pnl_pct")))
    basis = _exit_basis(stop_row)
    basis_norm = basis.lower()
    exact_basis = basis_norm in EXACT_EXIT_BASES
    if pnl is None:
        return "missing_realized_pnl", {"position_id": position_id, "exit_execution_basis": basis or None}
    if not exact_basis:
        return (
            "missing_exact_exit_evidence",
            {"position_id": position_id, "baseline_pnl_pct": pnl, "exit_execution_basis": basis or None},
        )
    return (
        "exact_realized_pnl_available",
        {
            "position_id": position_id,
            "baseline_pnl_pct": pnl,
            "exit_execution_basis": basis,
            "baseline_close_date": stop_row.get("baseline_close_date"),
        },
    )


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _disposition_by_key(
    *,
    queue_file: Path,
    fill_attempt_file: Path,
) -> dict[str, dict[str, Any]]:
    report = pending.build_validation_disposition_report(
        queue_file=queue_file,
        fill_attempt_file=fill_attempt_file,
    )
    return {str(row.get("candidate_key") or ""): row for row in report.get("candidates") or []}


def _loop_outcome(row: dict[str, Any], disposition: dict[str, Any] | None) -> tuple[str, str]:
    status = _norm(row.get("candidate_status"))
    if disposition:
        return _norm(disposition.get("outcome")), _norm(disposition.get("outcome_reason"))
    status_outcome = fresh_evidence_loop_outcome_for_status(status, row.get("candidate_status_reason"))
    if status_outcome is not None:
        return status_outcome
    return status or "unknown", _norm(row.get("candidate_status_reason"))


def _has_contract_identity(candidate: dict[str, Any]) -> bool:
    return bool(_norm(candidate.get("contract_symbol")) or _norm(candidate.get("short_contract_symbol")))


def _promotion_gate_context(candidate: dict[str, Any]) -> str:
    if isinstance(candidate.get("lane_promotion_state"), dict):
        return "current_lane_promotion_state_payload"
    status = _norm(candidate.get("candidate_status"))
    if status in {
        STATUS_PENDING_LIVE_VALIDATION,
        STATUS_LIVE_VALIDATION_ATTEMPTED,
        STATUS_LIVE_VALIDATION_SCAN_FAILED,
    }:
        return "legacy_pre_promotion_state_gate"
    return "no_lane_promotion_state_payload"


def _evidence_bridge(
    *,
    candidate: dict[str, Any],
    validation_outcome: str,
    entry_status: str,
    realized_status: str,
    position_id: int | None,
    promotion_ready: bool,
) -> dict[str, Any]:
    status = _norm(candidate.get("candidate_status"))
    spec = candidate_status_spec(status)
    paper_only = is_paper_only_status(status)
    blockers: list[str] = []
    required_next_evidence: list[str] = []
    if promotion_ready:
        bridge_status = BRIDGE_READY
    elif paper_only:
        bridge_status = BRIDGE_PAPER_ENTRY_REQUIRED
        if not _has_contract_identity(candidate):
            blockers.append("exact_contract_identity_missing")
        if entry_status != "fresh_executable_exact_entry":
            required_next_evidence.append("fresh_executable_exact_opra_nbbo_entry")
        required_next_evidence.append("paper_only_validation_disposition")
        required_next_evidence.append("tracked_or_suggested_link_after_explicit_paper_review_only")
        required_next_evidence.append("trusted_exact_exit_realized_pnl_after_close")
    elif validation_outcome in {"created", "duplicate"} and entry_status == "fresh_executable_exact_entry":
        bridge_status = BRIDGE_EXACT_EXIT_REQUIRED
        required_next_evidence.append("trusted_exact_exit_realized_pnl_after_close")
        if realized_status == "missing_exact_exit_evidence":
            blockers.append("exact_exit_evidence_missing")
        elif realized_status == "missing_realized_pnl":
            blockers.append("realized_pnl_missing")
        elif realized_status == "no_position_link":
            blockers.append("position_link_missing")
    elif entry_status in {"stale", "non_executable", "fill_attempt_missing"}:
        bridge_status = BRIDGE_NON_EXECUTABLE_ENTRY
        blockers.append(f"entry_status:{entry_status}")
        required_next_evidence.append("fresh_executable_exact_opra_nbbo_entry")
    else:
        bridge_status = BRIDGE_NOT_CANDIDATE
    return {
        "status": bridge_status,
        "candidate_status_phase": spec.phase if spec else None,
        "candidate_status_family": spec.family if spec else None,
        "paper_only": paper_only,
        "live_policy_change": False,
        "position_id": position_id,
        "blockers": blockers,
        "required_next_evidence": required_next_evidence,
        "prohibited_actions": [
            "do_not_create_live_row_from_bridge_status",
            "do_not_submit_broker_order_from_bridge_status",
            "do_not_count_midpoint_stale_eod_or_manual_evidence",
        ],
    }


def build_report(
    *,
    queue_file: Path = pending.DEFAULT_QUEUE_FILE,
    fill_attempt_file: Path = pending.DEFAULT_FILL_ATTEMPT_FILE,
    stop_grid_path: Path = point_in_time.DEFAULT_STOP_GRID,
) -> dict[str, Any]:
    candidates = pending.latest_candidate_rows(queue_file)
    fill_attempts = pending.latest_fill_attempt_rows(fill_attempt_file)
    dispositions = _disposition_by_key(queue_file=queue_file, fill_attempt_file=fill_attempt_file)
    stop_grid = _read_json(stop_grid_path)
    stop_rows = _stop_rows_by_position(stop_grid)

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _norm(candidate.get("candidate_key"))
        fill_attempt = fill_attempts.get(key)
        disposition = dispositions.get(key)
        outcome, outcome_reason = _loop_outcome(candidate, disposition)
        position_id = _safe_int(
            (fill_attempt or {}).get("auto_track_position_id")
            or candidate.get("auto_track_position_id")
            or (disposition or {}).get("auto_track_position_id")
        )
        entry_status, entry_reasons = _entry_evidence_status(fill_attempt)
        realized_status, realized = _realized_pnl_status(
            position_id=position_id,
            stop_row=stop_rows.get(position_id or -1),
        )
        promotion_ready = (
            outcome in {"created", "duplicate"}
            and entry_status == "fresh_executable_exact_entry"
            and realized_status == "exact_realized_pnl_available"
        )
        evidence_bridge = _evidence_bridge(
            candidate=candidate,
            validation_outcome=outcome,
            entry_status=entry_status,
            realized_status=realized_status,
            position_id=position_id,
            promotion_ready=promotion_ready,
        )
        row = {
            "candidate_key": key,
            "scan_date": _norm(candidate.get("audit_generated_at_utc") or candidate.get("queue_recorded_at_utc"))[:10],
            "candidate_status": candidate.get("candidate_status"),
            "promotion_gate_context": _promotion_gate_context(candidate),
            "lane_promotion_state": candidate.get("lane_promotion_state"),
            "validation_outcome": outcome,
            "validation_outcome_reason": outcome_reason,
            "playbook_id": candidate.get("playbook_id"),
            "ticker": candidate.get("ticker"),
            "direction": candidate.get("direction"),
            "expiry": candidate.get("expiry"),
            "contract_symbol": candidate.get("contract_symbol"),
            "short_contract_symbol": candidate.get("short_contract_symbol"),
            "fill_attempt_status": "logged" if fill_attempt else "missing",
            "fill_status": (fill_attempt or {}).get("fill_status"),
            "fill_outcome": (fill_attempt or {}).get("fill_outcome"),
            "fill_outcome_reason": (fill_attempt or {}).get("fill_outcome_reason"),
            "entry_evidence_status": entry_status,
            "entry_evidence_reasons": entry_reasons,
            "position_link_status": "tracked_position_linked" if position_id is not None else "no_tracked_or_suggested_link",
            "auto_track_position_id": position_id,
            "realized_pnl_status": realized_status,
            "realized_pnl": realized,
            "evidence_bridge": evidence_bridge,
            "evidence_bridge_status": evidence_bridge["status"],
            "evidence_bridge_blockers": evidence_bridge["blockers"],
            "required_next_evidence": evidence_bridge["required_next_evidence"],
            "promotion_discussion_ready": promotion_ready,
            "live_policy_change": False,
        }
        rows.append(row)

    outcome_counts = Counter(str(row["validation_outcome"]) for row in rows)
    entry_counts = Counter(str(row["entry_evidence_status"]) for row in rows)
    realized_counts = Counter(str(row["realized_pnl_status"]) for row in rows)
    status_counts = Counter(str(row["candidate_status"]) for row in rows)
    bridge_counts = Counter(str(row["evidence_bridge_status"]) for row in rows)
    promotion_context_counts = Counter(str(row["promotion_gate_context"]) for row in rows)
    summary = {
        "candidate_count": len(rows),
        "validation_outcome_counts": dict(sorted(outcome_counts.items())),
        "candidate_status_counts": dict(sorted(status_counts.items())),
        "entry_evidence_status_counts": dict(sorted(entry_counts.items())),
        "realized_pnl_status_counts": dict(sorted(realized_counts.items())),
        "evidence_bridge_status_counts": dict(sorted(bridge_counts.items())),
        "promotion_gate_context_counts": dict(sorted(promotion_context_counts.items())),
        "linked_position_count": sum(1 for row in rows if row["auto_track_position_id"] is not None),
        "exact_realized_pnl_count": realized_counts.get("exact_realized_pnl_available", 0),
        "missing_realized_pnl_count": realized_counts.get("missing_realized_pnl", 0),
        "no_longer_matched_count": outcome_counts.get("no_longer_matched", 0),
        "proof_ineligible_count": outcome_counts.get("proof_ineligible", 0),
        "stale_count": entry_counts.get("stale", 0),
        "non_executable_count": entry_counts.get("non_executable", 0),
        "promotion_discussion_ready_count": sum(1 for row in rows if row["promotion_discussion_ready"]),
        "paper_probation_bridge_count": bridge_counts.get(BRIDGE_PAPER_ENTRY_REQUIRED, 0),
        "exact_exit_bridge_count": bridge_counts.get(BRIDGE_EXACT_EXIT_REQUIRED, 0),
        "non_executable_bridge_count": bridge_counts.get(BRIDGE_NON_EXECUTABLE_ENTRY, 0),
        "legacy_pre_promotion_state_gate_count": promotion_context_counts.get("legacy_pre_promotion_state_gate", 0),
        "live_policy_change": False,
    }
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "scope": "regular_options_fresh_exact_evidence_loop",
        "status": "fresh_evidence_loop_readback",
        "evidence_boundary": {
            "readback_is": (
                "pending candidate to validation, fill-attempt, tracked-link, and exact realized-P&L readback"
            ),
            "readback_is_not": "scanner promotion, broker action, proof-bar change, auth change, or DB mutation",
            "promotion_discussion_requires": [
                "fresh market-hours validation outcome created or duplicate",
                "fresh executable exact OPRA/NBBO entry evidence",
                "tracked/suggested row linkage without proof semantic merging",
                "exact OPRA/NBBO realized exit P&L",
                "live_policy_change=false",
            ],
            "paper_probation_bridge_requires": [
                "fresh executable exact OPRA/NBBO entry captured during a quote window",
                "paper-only validation disposition until lane promotion clears",
                "trusted exact exit realized P&L before promotion discussion",
            ],
        },
        "inputs": {
            "queue_file": _rel(queue_file),
            "fill_attempt_file": _rel(fill_attempt_file),
            "stop_grid_path": _rel(stop_grid_path),
            "stop_grid_report_id": stop_grid.get("report_id"),
            "stop_grid_generated_at_utc": stop_grid.get("generated_at_utc"),
        },
        "summary": summary,
        "candidates": sorted(
            rows,
            key=lambda row: (
                str(row.get("scan_date") or ""),
                str(row.get("playbook_id") or ""),
                str(row.get("ticker") or ""),
                str(row.get("candidate_key") or ""),
            ),
        ),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Regular Options Fresh Evidence Loop",
        "",
        "This report is generated from `scripts/build_regular_options_fresh_evidence_loop.py`. It reconciles pending validation candidates, fill attempts, tracked-position linkage, and exact realized P&L readbacks without changing scanner, broker, auth, DB, stop, or proof behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Candidates: `{summary['candidate_count']}`.",
        f"- Validation outcomes: `{json.dumps(summary['validation_outcome_counts'], sort_keys=True)}`.",
        f"- Entry evidence statuses: `{json.dumps(summary['entry_evidence_status_counts'], sort_keys=True)}`.",
        f"- Realized P&L statuses: `{json.dumps(summary['realized_pnl_status_counts'], sort_keys=True)}`.",
        f"- Evidence bridge statuses: `{json.dumps(summary['evidence_bridge_status_counts'], sort_keys=True)}`.",
        f"- Promotion gate contexts: `{json.dumps(summary['promotion_gate_context_counts'], sort_keys=True)}`.",
        f"- No-longer-matched: `{summary['no_longer_matched_count']}`.",
        f"- Proof-ineligible: `{summary['proof_ineligible_count']}`.",
        f"- Linked positions: `{summary['linked_position_count']}`.",
        f"- Exact realized P&L rows: `{summary['exact_realized_pnl_count']}`.",
        f"- Missing realized P&L: `{summary['missing_realized_pnl_count']}`.",
        f"- Stale entry evidence: `{summary['stale_count']}`.",
        f"- Non-executable entry evidence: `{summary['non_executable_count']}`.",
        f"- Promotion discussion ready: `{summary['promotion_discussion_ready_count']}`.",
        f"- Paper/probation bridge rows: `{summary['paper_probation_bridge_count']}`.",
        f"- Exact-exit bridge rows: `{summary['exact_exit_bridge_count']}`.",
        f"- Legacy pre-promotion rows: `{summary['legacy_pre_promotion_state_gate_count']}`.",
        f"- Live policy change: `{summary['live_policy_change']}`.",
        "",
        "## Evidence Boundary",
        "",
        "- Exact realized P&L is required before promotion discussion.",
        "- Entry evidence status describes scanner quote/limit evidence only; it is not a fill, position, or broker execution status.",
        "- `created` and `duplicate` validation outcomes are still paper/tracked linkage states, not broker fills.",
        "- Missing, stale, non-executable, proof-ineligible, and no-longer-matched rows remain blocked from promotion.",
        "- Paper/probation bridge rows collect exact evidence only; they are not live validation, auto-track, or broker instructions.",
        "",
        "## Candidate Readback",
        "",
        "| Date | Lane | Ticker | Outcome | Entry Evidence | P&L Status | Bridge | Position | Ready | Reason |",
        "|---|---|---|---|---|---|---|---:|---|---|",
    ]
    for row in report.get("candidates") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("scan_date")),
                    _fmt(row.get("playbook_id")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("validation_outcome")),
                    _fmt(row.get("entry_evidence_status")),
                    _fmt(row.get("realized_pnl_status")),
                    _fmt(row.get("evidence_bridge_status")),
                    _fmt(row.get("auto_track_position_id")),
                    _fmt(row.get("promotion_discussion_ready")),
                    _fmt(row.get("validation_outcome_reason")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    markdown_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_markdown = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(markdown_path),
        "latest_markdown": str(latest_markdown),
        "docs_report": str(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    json_payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(json_payload + "\n", encoding="utf8")
    latest_json.write_text(json_payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the regular options fresh evidence loop readback.")
    parser.add_argument("--queue-file", type=Path, default=pending.DEFAULT_QUEUE_FILE)
    parser.add_argument("--fill-attempt-file", type=Path, default=pending.DEFAULT_FILL_ATTEMPT_FILE)
    parser.add_argument("--stop-grid", type=Path, default=point_in_time.DEFAULT_STOP_GRID)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        queue_file=args.queue_file,
        fill_attempt_file=args.fill_attempt_file,
        stop_grid_path=args.stop_grid,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    else:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
