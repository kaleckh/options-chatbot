from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend_route_context import BackendRouteContext


def _evidence_count(*values: Any) -> int:
    for value in values:
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count >= 0:
            return count
    return 0


def _tracked_position_counts(ctx: BackendRouteContext) -> dict[str, Any]:
    positions_available = False
    open_count = 0
    closed_count = 0
    raw_exact_contract_closed = 0
    proof_grade_exact_contract_closed = 0
    repository = ctx.POSITIONS_REPOSITORY
    if getattr(repository, "is_available", False):
        positions_available = True
        try:
            open_positions = repository.list_positions("open")
            closed_positions = repository.list_positions("closed")
            open_count = len(open_positions)
            closed_count = len(closed_positions)
            raw_exact_contract_closed = sum(
                1 for position in closed_positions
                if ctx._row_has_raw_exact_contract(dict(position))
            )
            proof_grade_exact_contract_closed = sum(
                1 for position in closed_positions
                if ctx._row_counts_as_proof_grade_exact_closed(dict(position))
            )
        except Exception:
            pass
    return {
        "available": positions_available,
        "open_count": open_count,
        "closed_count": closed_count,
        "raw_exact_contract_closed_count": raw_exact_contract_closed,
        "proof_grade_exact_contract_closed_count": proof_grade_exact_contract_closed,
        "exact_contract_closed_count": proof_grade_exact_contract_closed,
    }


def build_proof_summary(ctx: BackendRouteContext) -> dict[str, Any]:
    """Build the proof-lane readback without owning HTTP or proof semantics."""
    loop_health = ctx.evaluate_measurement_gate()
    claim_readiness = ctx.evaluate_claim_readiness()
    forward_evidence = ctx._cached_forward_evidence_report()
    ledger_summary = dict(forward_evidence.get("ledger_summary") or {})

    eligible_scan_pick_event_count = _evidence_count(
        forward_evidence.get("eligible_scan_pick_count"),
        ledger_summary.get("eligible_scan_pick_count"),
    )
    scan_pick_event_count = _evidence_count(
        forward_evidence.get("scan_pick_count"),
        ledger_summary.get("scan_pick_count"),
        eligible_scan_pick_event_count,
    )
    forward_event_count = _evidence_count(
        forward_evidence.get("scan_pick_count"),
        ledger_summary.get("scan_pick_count"),
        scan_pick_event_count,
    )

    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "loop_health": {
            "state": loop_health["state"],
            "blocker_count": len(loop_health["blockers"]),
            "blockers": loop_health["blockers"],
        },
        "claim_readiness": {
            "state": claim_readiness["state"],
            "claim_ready": claim_readiness["claim_ready"],
            "blocker_count": claim_readiness["blocker_count"],
            "blockers": claim_readiness["blockers"],
        },
        "evidence_counts": {
            "forward_event_count": forward_event_count,
            "scan_pick_event_count": scan_pick_event_count,
            "eligible_scan_pick_event_count": eligible_scan_pick_event_count,
            "position_opened_event_count": _evidence_count(
                ledger_summary.get("position_opened_event_count")
            ),
            "review_event_count": _evidence_count(ledger_summary.get("review_event_count")),
            "eligible_event_count": claim_readiness.get("eligible_event_count", 0),
            "pending_truth_event_count": claim_readiness.get("pending_truth_event_count", 0),
            "by_symbol": claim_readiness.get("by_symbol", {}),
        },
        "tracked_positions": _tracked_position_counts(ctx),
        "realized_metrics": claim_readiness.get("tracked_realized_metrics", {}),
    }
