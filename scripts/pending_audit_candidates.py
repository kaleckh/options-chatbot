from __future__ import annotations

import json
import sys
from collections import Counter
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
DEFAULT_FILL_ATTEMPT_FILE = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_DISPOSITION_FILE = ROOT / "data" / "forward-tracking" / "pending_scan_candidate_validation_latest.json"

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


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _candidate_identity_from_row(row: dict[str, Any]) -> str:
    selected = row.get("selected_spread") if isinstance(row.get("selected_spread"), dict) else {}
    pick = {
        "ticker": row.get("ticker"),
        "direction": row.get("direction") or row.get("type") or row.get("option_type"),
        "expiry": row.get("expiry") or selected.get("expiry"),
        "contract_symbol": row.get("contract_symbol") or selected.get("long_contract_symbol"),
        "short_contract_symbol": row.get("short_contract_symbol") or selected.get("short_contract_symbol"),
        "long_strike": (
            row.get("long_strike")
            if row.get("long_strike") is not None
            else selected.get("long_strike")
            if selected.get("long_strike") is not None
            else row.get("strike")
        ),
        "short_strike": row.get("short_strike") if row.get("short_strike") is not None else selected.get("short_strike"),
    }
    scan_date = _norm_text(row.get("scan_date") or row.get("audit_generated_at_utc") or row.get("queue_recorded_at_utc"))
    return _candidate_identity(
        audit_generated_at_utc=scan_date,
        playbook_id=_norm_text(row.get("playbook_id")),
        pick=pick,
    )


def latest_fill_attempt_rows(fill_attempt_file: Path = DEFAULT_FILL_ATTEMPT_FILE) -> dict[str, dict[str, Any]]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl_rows(fill_attempt_file):
        if _norm_text(row.get("event_type")) != "candidate_shown":
            continue
        key = _candidate_identity_from_row(row)
        if key:
            latest_by_key[key] = row
    return latest_by_key


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


def _validation_outcome(row: dict[str, Any], fill_attempt: dict[str, Any] | None) -> tuple[str, str]:
    status = _norm_text(row.get("candidate_status"))
    if status == "live_validation_scan_failed":
        return "blocked", "validation_scan_failed"
    if status != "live_validation_attempted":
        return "no_longer_matched", "candidate_has_not_completed_live_validation"
    if fill_attempt is None:
        return "no_longer_matched", "candidate_not_returned_by_market_hours_validation_scan"

    tracking_mode = _norm_text(row.get("position_tracking_mode") or fill_attempt.get("position_tracking_mode"))
    tracking_approved = bool(row.get("tracking_approved_lane"))
    fill_status = _norm_text(fill_attempt.get("fill_status"))
    fill_reason = _norm_text(fill_attempt.get("fill_outcome_reason"))
    track_outcome = _norm_text(fill_attempt.get("auto_track_outcome"))

    if not tracking_approved or tracking_mode not in {"", "auto_track"} or "auto_track_disabled" in fill_reason:
        return "paper_only", "validation_matched_but_lane_is_not_auto_track_eligible"
    if fill_attempt.get("filled") is True and fill_attempt.get("auto_track_position_id") is not None:
        if track_outcome == "duplicate_open":
            return "duplicate", "matching_position_was_already_open"
        return "created", "fresh_validation_created_or_confirmed_auto_track_position"
    if "not_submitted" in fill_status or "not_filled" in fill_status:
        return "proof_ineligible", fill_reason or "validation_matched_but_creation_or_proof_gate_failed"
    return "blocked", fill_reason or "validation_matched_but_no_create_outcome_was_recorded"


def build_validation_disposition_report(
    *,
    queue_file: Path = DEFAULT_QUEUE_FILE,
    fill_attempt_file: Path = DEFAULT_FILL_ATTEMPT_FILE,
    scan_date: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    fill_attempts = latest_fill_attempt_rows(fill_attempt_file)
    candidates = []
    for row in latest_candidate_rows(queue_file):
        status = _norm_text(row.get("candidate_status"))
        if status not in {"live_validation_attempted", "live_validation_scan_failed"}:
            continue
        if scan_date and _candidate_scan_date_for_disposition(row) != scan_date:
            continue
        key = _norm_text(row.get("candidate_key")) or _candidate_identity_from_row(row)
        fill_attempt = fill_attempts.get(key)
        outcome, reason = _validation_outcome(row, fill_attempt)
        candidates.append(
            {
                "candidate_key": key,
                "outcome": outcome,
                "outcome_reason": reason,
                "candidate_status": status,
                "validation_exit_code": row.get("validation_exit_code"),
                "playbook_id": row.get("playbook_id"),
                "position_tracking_mode": row.get("position_tracking_mode"),
                "tracking_approved_lane": row.get("tracking_approved_lane"),
                "ticker": row.get("ticker"),
                "direction": row.get("direction"),
                "expiry": row.get("expiry"),
                "contract_symbol": row.get("contract_symbol"),
                "short_contract_symbol": row.get("short_contract_symbol"),
                "validation_recorded_at_utc": row.get("validation_recorded_at_utc"),
                "fill_attempt_logged_at": fill_attempt.get("logged_at") if fill_attempt else None,
                "fill_status": fill_attempt.get("fill_status") if fill_attempt else None,
                "fill_outcome": fill_attempt.get("fill_outcome") if fill_attempt else None,
                "fill_outcome_reason": fill_attempt.get("fill_outcome_reason") if fill_attempt else None,
                "auto_track_outcome": fill_attempt.get("auto_track_outcome") if fill_attempt else None,
                "auto_track_position_id": fill_attempt.get("auto_track_position_id") if fill_attempt else None,
            }
        )
    counts = Counter(str(item["outcome"]) for item in candidates)
    return {
        "report_id": "pending_scan_candidate_validation_disposition",
        "generated_at_utc": generated_at,
        "scan_date": scan_date,
        "inputs": {
            "queue_file": str(queue_file),
            "fill_attempt_file": str(fill_attempt_file),
        },
        "summary": {
            "candidate_count": len(candidates),
            "outcome_counts": dict(sorted(counts.items())),
        },
        "candidates": sorted(
            candidates,
            key=lambda item: (
                str(item.get("playbook_id") or ""),
                str(item.get("ticker") or ""),
                str(item.get("candidate_key") or ""),
            ),
        ),
    }


def _candidate_scan_date_for_disposition(row: dict[str, Any]) -> str:
    validation = _norm_text(row.get("validation_recorded_at_utc"))
    if validation:
        return validation[:10]
    audit = _norm_text(row.get("audit_generated_at_utc"))
    if audit:
        return audit[:10]
    return _norm_text(row.get("queue_recorded_at_utc"))[:10]


def write_validation_disposition_report(
    *,
    queue_file: Path = DEFAULT_QUEUE_FILE,
    fill_attempt_file: Path = DEFAULT_FILL_ATTEMPT_FILE,
    output_file: Path = DEFAULT_DISPOSITION_FILE,
    scan_date: str | None = None,
) -> dict[str, Any]:
    report = build_validation_disposition_report(
        queue_file=queue_file,
        fill_attempt_file=fill_attempt_file,
        scan_date=scan_date,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report
