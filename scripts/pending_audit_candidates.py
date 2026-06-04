from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervised_scan import (
    scan_playbook_allows_auto_track,
    scan_playbook_fresh_live_validation_enabled,
    scan_playbook_position_tracking_mode,
)

DEFAULT_QUEUE_FILE = ROOT / "data" / "forward-tracking" / "pending_scan_candidates.jsonl"

def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_identity(
    *,
    audit_generated_at_utc: str,
    playbook_id: str,
    pick: dict[str, Any],
) -> str:
    parts = [
        audit_generated_at_utc[:10],
        playbook_id,
        _norm_text(pick.get("ticker")).upper(),
        _norm_text(pick.get("direction") or pick.get("type") or pick.get("option_type")).lower(),
        _norm_text(pick.get("expiry") or pick.get("expiration_date"))[:10],
        _norm_text(pick.get("contract_symbol") or pick.get("contractSymbol")).upper(),
        _norm_text(pick.get("short_contract_symbol") or pick.get("shortContractSymbol")).upper(),
        _norm_text(pick.get("long_strike") if pick.get("long_strike") is not None else pick.get("strike")),
        _norm_text(pick.get("short_strike")),
    ]
    return "|".join(parts)


def _iter_existing_keys(queue_file: Path) -> set[str]:
    keys: set[str] = set()
    try:
        rows = queue_file.read_text(encoding="utf8").splitlines()
    except OSError:
        return keys
    for line in rows:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = _norm_text(payload.get("candidate_key"))
        if key:
            keys.add(key)
    return keys


def latest_candidate_rows(queue_file: Path = DEFAULT_QUEUE_FILE) -> list[dict[str, Any]]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    try:
        lines = queue_file.read_text(encoding="utf8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        key = _norm_text(payload.get("candidate_key"))
        if not key:
            continue
        latest_by_key[key] = payload
    return list(latest_by_key.values())


def _candidate_status(playbook_id: str) -> tuple[str, str]:
    if scan_playbook_fresh_live_validation_enabled(playbook_id):
        return (
            "pending_live_validation",
            "clear_audit_candidate_requires_fresh_market_hours_opra_validation",
        )
    return (
        "diagnostic_only_unapproved_lane",
        "clear_audit_candidate_from_lane_not_enabled_for_fresh_live_validation",
    )


def build_pending_candidate_rows(report: dict[str, Any], *, recorded_at_utc: str | None = None) -> list[dict[str, Any]]:
    recorded_at = recorded_at_utc or _utc_now_iso()
    audit_generated = _norm_text(report.get("generated_at_utc"))
    scope = _norm_text(report.get("scope"))
    settings = report.get("settings") if isinstance(report.get("settings"), dict) else {}
    rows: list[dict[str, Any]] = []

    for playbook_report in list(report.get("playbooks") or []):
        if not isinstance(playbook_report, dict):
            continue
        playbook_id = _norm_text(playbook_report.get("playbook_id"))
        if not playbook_id:
            continue
        label = playbook_report.get("label")
        for pick in list(playbook_report.get("returned_picks") or []):
            if not isinstance(pick, dict):
                continue
            if _norm_text(pick.get("guardrail_decision")).lower() != "clear":
                continue
            status, reason = _candidate_status(playbook_id)
            tracking_mode = scan_playbook_position_tracking_mode(playbook_id)
            tracking_approved = scan_playbook_allows_auto_track(playbook_id)
            candidate_key = _candidate_identity(
                audit_generated_at_utc=audit_generated,
                playbook_id=playbook_id,
                pick=pick,
            )
            rows.append(
                {
                    "event_type": "audit_candidate_selected",
                    "candidate_key": candidate_key,
                    "candidate_status": status,
                    "candidate_status_reason": reason,
                    "queue_recorded_at_utc": recorded_at,
                    "audit_generated_at_utc": audit_generated,
                    "audit_scope": scope,
                    "audit_market_open_at_run": settings.get("market_open_at_run"),
                    "playbook_id": playbook_id,
                    "playbook_label": label,
                    "tracking_approved_lane": tracking_approved,
                    "fresh_live_validation_enabled": scan_playbook_fresh_live_validation_enabled(playbook_id),
                    "position_tracking_mode": tracking_mode,
                    "ticker": pick.get("ticker"),
                    "direction": pick.get("direction") or pick.get("type") or pick.get("option_type"),
                    "expiry": pick.get("expiry") or pick.get("expiration_date"),
                    "contract_symbol": pick.get("contract_symbol") or pick.get("contractSymbol"),
                    "short_contract_symbol": pick.get("short_contract_symbol") or pick.get("shortContractSymbol"),
                    "long_strike": pick.get("long_strike") if pick.get("long_strike") is not None else pick.get("strike"),
                    "short_strike": pick.get("short_strike"),
                    "net_debit": pick.get("net_debit"),
                    "entry_execution_price": pick.get("entry_execution_price"),
                    "entry_execution_basis": pick.get("entry_execution_basis"),
                    "debit_pct_of_width": pick.get("debit_pct_of_width"),
                    "quality_score": pick.get("quality_score"),
                    "guardrail_decision": pick.get("guardrail_decision"),
                    "guardrail_reasons": list(pick.get("guardrail_reasons") or []),
                    "candidate_execution_label": pick.get("candidate_execution_label"),
                    "suggested_size_tier": pick.get("suggested_size_tier"),
                    "quote_time_utc": pick.get("quote_time_utc"),
                    "quote_time_et": pick.get("quote_time_et"),
                    "quote_freshness_status": pick.get("quote_freshness_status"),
                    "selection_source": pick.get("selection_source"),
                    "promotion_class": pick.get("promotion_class"),
                    "source_pick_snapshot": pick,
                }
            )
    return rows


def append_pending_candidate_rows(
    report: dict[str, Any],
    *,
    queue_file: Path = DEFAULT_QUEUE_FILE,
    recorded_at_utc: str | None = None,
) -> dict[str, Any]:
    rows = build_pending_candidate_rows(report, recorded_at_utc=recorded_at_utc)
    existing_keys = _iter_existing_keys(queue_file)
    new_rows = [row for row in rows if _norm_text(row.get("candidate_key")) not in existing_keys]
    if new_rows:
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        with queue_file.open("a", encoding="utf8") as handle:
            for row in new_rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "queue_file": str(queue_file),
        "selected_clear_candidates": len(rows),
        "queued_new_candidates": len(new_rows),
        "duplicate_candidates": len(rows) - len(new_rows),
        "pending_live_validation": sum(
            1 for row in rows if row.get("candidate_status") == "pending_live_validation"
        ),
        "diagnostic_only_unapproved_lane": sum(
            1 for row in rows if row.get("candidate_status") == "diagnostic_only_unapproved_lane"
        ),
    }


def append_validation_attempt_rows(
    rows: list[dict[str, Any]],
    *,
    queue_file: Path = DEFAULT_QUEUE_FILE,
    playbook_id: str,
    exit_code: int,
    recorded_at_utc: str | None = None,
) -> int:
    recorded_at = recorded_at_utc or _utc_now_iso()
    status = "live_validation_attempted" if int(exit_code) == 0 else "live_validation_scan_failed"
    appended = 0
    if not rows:
        return appended
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    with queue_file.open("a", encoding="utf8") as handle:
        for row in rows:
            if _norm_text(row.get("playbook_id")) != playbook_id:
                continue
            next_row = dict(row)
            next_row.update(
                {
                    "event_type": "pending_candidate_validation",
                    "candidate_status": status,
                    "candidate_status_reason": (
                        "live_validation_lane_reran_review_scan_logs_for_promotion_or_block_reason"
                        if int(exit_code) == 0
                        else "live_validation_lane_scan_failed"
                    ),
                    "validation_exit_code": int(exit_code),
                    "validation_recorded_at_utc": recorded_at,
                }
            )
            handle.write(json.dumps(next_row, sort_keys=True) + "\n")
            appended += 1
    return appended
