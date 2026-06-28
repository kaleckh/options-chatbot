from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_phase2_regular_options_forward_paper_shadow_candidate_rows as stager
from us_equity_market_calendar import is_us_equity_market_day, previous_market_day


REPORT_ID = "regular_options_forward_candidate_throughput_audit"
DEFAULT_SCAN_PICKS = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
DEFAULT_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-forward-candidate-throughput-audit.md"
FREEZE_DATE = "2026-06-14"
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    malformed = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        text = raw.strip().lstrip("\ufeff")
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    return rows, malformed


def _lane_id(row: dict[str, Any]) -> str:
    return _norm(row.get("lane_id") or row.get("playbook_id") or row.get("cohort_id"))


def _selection_date(row: dict[str, Any]) -> str:
    explicit = _norm(row.get("selection_date") or row.get("scan_date"))
    if explicit:
        return explicit
    return _timestamp_market_date(row.get("selection_timestamp_utc") or row.get("logged_at"))


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _norm(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [text]


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = _norm(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _drop_stage_summary(drop_counts: Counter[str]) -> dict[str, Any]:
    nonzero = {key: drop_counts[key] for key in sorted(drop_counts) if drop_counts[key] > 0}
    return {
        "status": "candidate_starvation_from_scan_filters" if nonzero else "no_drop_stage_counts_reported",
        "total_drop_count": sum(nonzero.values()),
        "top_drop_stages": [
            {"stage": key, "count": value}
            for key, value in sorted(nonzero.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "drop_counts": nonzero,
    }


def _drop_reason_sample(drop_reasons: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for symbol, reason in sorted(drop_reasons.items(), key=lambda item: str(item[0]).upper()):
        reason_payload = _as_dict(reason)
        drop_key = _norm(reason_payload.get("drop_key"))
        details = _as_dict(reason_payload.get("details"))
        sample.append(
            {
                "symbol": str(symbol).strip().upper(),
                "drop_key": drop_key,
                "reason": _norm(details.get("reason") or details.get("candidate_execution_label")),
                "details": details,
            }
        )
        if len(sample) >= max(int(limit), 0):
            break
    return sample


def _candidate_starvation_evidence_status(
    *,
    returned_picks: int,
    drop_count_total: int,
    drop_reason_count_total: int,
) -> str:
    if returned_picks > 0:
        return "returned_picks_available"
    if drop_reason_count_total > 0:
        return "raw_symbol_drop_reasons_recorded"
    if drop_count_total > 0:
        return "stage_counts_only_waiting_for_symbol_drop_reasons"
    return "waiting_for_next_scan_funnel_evidence"


def _zero_candidate_diagnostics(
    *,
    target_selection_date: str,
    scheduled_sessions_reviewed: int,
    scheduled_session_error: str | None,
    missing_scheduled_sessions: list[str],
    scheduled_scan_picks_count: int,
    returned_picks: int,
    candidate_rows_staged: int,
    drop_stage_summary: dict[str, Any],
    drop_reason_count_total: int,
) -> dict[str, Any]:
    post_freeze_only = target_selection_date > FREEZE_DATE
    drop_count_total = int(drop_stage_summary.get("total_drop_count") or 0)
    top_drop_stages = drop_stage_summary.get("top_drop_stages")
    drop_stage_ranking = top_drop_stages if isinstance(top_drop_stages, list) else []
    if not post_freeze_only:
        status = "not_post_freeze_target_date"
    elif scheduled_session_error:
        status = "scheduled_phase2_session_source_unavailable"
    elif scheduled_scan_picks_count > 0 or returned_picks > 0 or candidate_rows_staged > 0:
        status = "not_zero_candidate_context_picks_available"
    elif missing_scheduled_sessions:
        status = "waiting_for_scheduled_phase2_sessions"
    elif drop_reason_count_total > 0:
        status = "zero_candidate_diagnosis_ready_symbol_drop_reasons_recorded"
    elif drop_count_total > 0:
        status = "opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons"
    else:
        status = "waiting_for_next_scan_funnel_evidence"
    if drop_reason_count_total > 0:
        symbol_drop_reason_status = "symbol_drop_reasons_recorded"
    elif drop_count_total > 0:
        symbol_drop_reason_status = "missing_symbol_drop_reasons_for_aggregate_drops"
    else:
        symbol_drop_reason_status = "no_symbol_drop_reasons_expected_until_scan_funnel_drops_exist"
    safe_next_read_only_actions = {
        "not_zero_candidate_context_picks_available": [
            "review_existing_phase2_picks_or_candidate_jsonl_without_append",
            "run_candidate_review_packet_read_only",
        ],
        "waiting_for_scheduled_phase2_sessions": [
            "wait_for_next_valid_market_window_scheduled_phase2_sweep",
            "refresh_forward_candidate_throughput_audit_no_write",
        ],
        "scheduled_phase2_session_source_unavailable": [
            "repair_or_refresh_forward_session_ledger_read_only",
            "refresh_forward_candidate_throughput_audit_no_write_after_source_available",
        ],
        "not_post_freeze_target_date": [
            "rerun_throughput_audit_for_post_freeze_target_date",
            "do_not_use_pre_freeze_rows_as_forward_zero_candidate_diagnosis",
        ],
        "zero_candidate_diagnosis_ready_symbol_drop_reasons_recorded": [
            "rank_symbol_level_drop_reasons_for_frozen_phase2_sessions",
            "compare_drop_stage_ranking_to_symbol_reason_samples_read_only",
        ],
        "opaque_zero_candidate_diagnosis_missing_symbol_drop_reasons": [
            "wait_for_future_scheduled_sessions_with_symbol_drop_reason_persistence",
            "inspect_existing_aggregate_drop_stage_counts_read_only",
        ],
        "waiting_for_next_scan_funnel_evidence": [
            "wait_for_next_valid_market_window_scan_funnel_evidence",
            "refresh_forward_candidate_throughput_audit_no_write",
        ],
    }[status]
    return {
        "status": status,
        "target_selection_date": target_selection_date,
        "allowed_lanes_only": True,
        "target_date_only": True,
        "post_freeze_only": post_freeze_only,
        "scheduled_sessions_reviewed": scheduled_sessions_reviewed,
        "scheduled_session_error": scheduled_session_error,
        "missing_scheduled_sessions": missing_scheduled_sessions,
        "scheduled_scan_picks_count": scheduled_scan_picks_count,
        "returned_picks": returned_picks,
        "candidate_rows_staged": candidate_rows_staged,
        "drop_count_total": drop_count_total,
        "drop_stage_ranking": drop_stage_ranking,
        "symbol_drop_reason_count_total": drop_reason_count_total,
        "symbol_drop_reason_status": symbol_drop_reason_status,
        "safe_next_read_only_actions": safe_next_read_only_actions,
        "deferred_actions": [
            "append_phase2_forward_cohort_rows",
            "create_candidate_identity",
            "promote_parked_lanes",
            "run_scanner_from_audit",
            "change_proof_bars",
            "enable_live_validation_auto_track_or_broker_orders",
            "mutate_evidence_stores",
        ],
        "candidate_scope_flags": {
            "parked_or_non_phase2_rows_excluded": True,
            "non_target_date_rows_excluded": True,
            "pre_freeze_rows_excluded": True,
            "scheduled_sessions_required_before_zero_candidate_diagnosis": True,
        },
        "safety_flags": {
            "read_only_diagnostic": True,
            "scanner_called": False,
            "cohort_append_allowed": False,
            "candidate_identity_created": False,
            "parked_lane_promotion_allowed": False,
            "proof_bar_change_allowed": False,
            "evidence_store_mutation_allowed": False,
        },
    }


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _default_selection_date(generated_at_utc: str) -> str:
    now_et = _parse_utc(generated_at_utc).astimezone(MARKET_TZ)
    today = now_et.date()
    if is_us_equity_market_day(today):
        open_dt = datetime.combine(today, MARKET_OPEN_ET, tzinfo=MARKET_TZ)
        close_dt = datetime.combine(today, MARKET_CLOSE_ET, tzinfo=MARKET_TZ)
        if open_dt <= now_et or now_et >= close_dt:
            return today.isoformat()
    return previous_market_day(today).isoformat()


def _timestamp_market_date(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        return parsed.date().isoformat()
    return parsed.astimezone(MARKET_TZ).date().isoformat()


def _load_scheduled_scan_sessions(
    *,
    ledger_db_path: Path,
    selection_date: str,
    playbooks: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not ledger_db_path.exists() or not playbooks:
        return [], None if ledger_db_path.exists() else "ledger_db_missing"
    placeholders = ",".join("?" for _ in playbooks)
    run_prefix = f"scheduled_scan:{selection_date}:%"
    conn: sqlite3.Connection | None = None
    try:
        ledger_uri = f"file:{ledger_db_path.resolve().as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(ledger_uri, uri=True)
        conn.row_factory = sqlite3.Row
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(forward_sessions)").fetchall()}
        blocker_select = ", eligibility_blockers" if "eligibility_blockers" in columns else ""
        notes_select = ", notes_json" if "notes_json" in columns else ""
        rows = conn.execute(
            f"""
            SELECT id, recorded_at_utc, playbook, scan_picks_count, eligibility_status, run_id{blocker_select}{notes_select}
            FROM forward_sessions
            WHERE source_label = 'scheduled_scan'
              AND run_id LIKE ?
              AND playbook IN ({placeholders})
            ORDER BY playbook, recorded_at_utc DESC, id DESC
            """,
            (run_prefix, *playbooks),
        ).fetchall()
        sessions = [dict(row) for row in rows]
    except sqlite3.Error as exc:
        return [], f"ledger_query_failed:{exc}"
    finally:
        if conn is not None:
            conn.close()
    return sessions, None


def build_report(
    *,
    scan_picks_path: Path = DEFAULT_SCAN_PICKS,
    ledger_db_path: Path = DEFAULT_LEDGER_DB,
    selection_date: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    target_date = selection_date or _default_selection_date(generated_at)
    rows, malformed = _load_jsonl(scan_picks_path)
    phase2_lanes = set(stager.ALLOWED_LANES)
    post_freeze = [row for row in rows if _selection_date(row) > FREEZE_DATE]
    post_freeze_phase2 = [row for row in post_freeze if _lane_id(row) in phase2_lanes]
    target_rows = [row for row in rows if _selection_date(row) == target_date]
    target_phase2 = [row for row in target_rows if _lane_id(row) in phase2_lanes]
    stage_report = stager.build_stage_report(
        source_scan_picks_path=scan_picks_path,
        no_write=True,
        market_window_confirmed=True,
        market_window_status="open",
        selection_date=target_date,
        generated_at_utc=generated_at,
    )
    target_phase2_lanes = Counter(_lane_id(row) for row in target_phase2)
    post_phase2_lanes = Counter(_lane_id(row) for row in post_freeze_phase2)
    scheduled_sessions, scheduled_session_error = _load_scheduled_scan_sessions(
        ledger_db_path=ledger_db_path,
        selection_date=target_date,
        playbooks=list(stager.ALLOWED_LANES),
    )
    scheduled_playbooks = set()
    scheduled_pick_count = 0
    scheduled_eligibility_statuses: Counter[str] = Counter()
    scheduled_eligibility_blockers: Counter[str] = Counter()
    scheduled_drop_counts: Counter[str] = Counter()
    scheduled_raw_candidates = 0
    scheduled_returned_picks = 0
    scheduled_drop_reason_count_total = 0
    scheduled_drop_reason_samples: list[dict[str, Any]] = []
    for session in scheduled_sessions:
        playbook = _norm(session.get("playbook"))
        if playbook:
            scheduled_playbooks.add(playbook)
        eligibility_status = _norm(session.get("eligibility_status")) or "unknown"
        scheduled_eligibility_statuses[eligibility_status] += 1
        for blocker in _parse_json_list(session.get("eligibility_blockers")):
            scheduled_eligibility_blockers[blocker] += 1
        notes = _parse_json_dict(session.get("notes_json"))
        scan_funnel = _as_dict(notes.get("scan_funnel"))
        symbol_diagnostics = _as_dict(notes.get("symbol_diagnostics"))
        scan_drop_reasons = _as_dict(
            symbol_diagnostics.get("scan_drop_reasons")
            or notes.get("scan_drop_reasons")
        )
        raw_candidates = 0
        returned_picks = 0
        try:
            raw_candidates = int(scan_funnel.get("raw_candidates") or notes.get("candidate_count") or 0)
        except (TypeError, ValueError):
            pass
        try:
            returned_picks = int(scan_funnel.get("returned_picks") or notes.get("returned_count") or 0)
        except (TypeError, ValueError):
            pass
        scheduled_raw_candidates += raw_candidates
        scheduled_returned_picks += returned_picks
        session_drop_counts: dict[str, int] = {}
        for key, value in _as_dict(scan_funnel.get("drop_counts")).items():
            try:
                parsed_count = int(value or 0)
            except (TypeError, ValueError):
                parsed_count = 0
            scheduled_drop_counts[str(key)] += parsed_count
            session_drop_counts[str(key)] = parsed_count
        session["scan_funnel_raw_candidates"] = raw_candidates
        session["scan_funnel_returned_picks"] = returned_picks
        session["scan_funnel_drop_counts"] = {key: session_drop_counts[key] for key in sorted(session_drop_counts)}
        session_drop_reason_sample = _drop_reason_sample(scan_drop_reasons)
        session["scan_drop_reason_count"] = len(scan_drop_reasons)
        session["scan_drop_reason_sample"] = session_drop_reason_sample
        scheduled_drop_reason_count_total += len(scan_drop_reasons)
        for sample in session_drop_reason_sample:
            if len(scheduled_drop_reason_samples) >= 10:
                break
            sample_with_context = dict(sample)
            sample_with_context["playbook"] = playbook
            sample_with_context["session_id"] = session.get("id")
            scheduled_drop_reason_samples.append(sample_with_context)
        session.pop("notes_json", None)
        try:
            scheduled_pick_count += int(session.get("scan_picks_count") or 0)
        except (TypeError, ValueError):
            pass
    missing_scheduled = [playbook for playbook in stager.ALLOWED_LANES if playbook not in scheduled_playbooks]
    scheduled_drop_stage_summary = _drop_stage_summary(scheduled_drop_counts)
    candidate_starvation_evidence_status = _candidate_starvation_evidence_status(
        returned_picks=scheduled_returned_picks,
        drop_count_total=sum(scheduled_drop_counts.values()),
        drop_reason_count_total=scheduled_drop_reason_count_total,
    )
    candidate_rows_staged = int(stage_report.get("candidate_rows_staged") or 0)
    zero_candidate_diagnostics = _zero_candidate_diagnostics(
        target_selection_date=target_date,
        scheduled_sessions_reviewed=len(scheduled_sessions),
        scheduled_session_error=scheduled_session_error,
        missing_scheduled_sessions=missing_scheduled,
        scheduled_scan_picks_count=scheduled_pick_count,
        returned_picks=scheduled_returned_picks,
        candidate_rows_staged=candidate_rows_staged,
        drop_stage_summary=scheduled_drop_stage_summary,
        drop_reason_count_total=scheduled_drop_reason_count_total,
    )
    status = "candidate_throughput_ready_for_validation" if stage_report.get("candidate_rows_staged") else "blocked_no_same_day_phase2_natural_selections"
    if malformed:
        status = "blocked_malformed_scan_picks"
    elif scheduled_session_error:
        status = "blocked_forward_cohort_scheduled_scan_session_source_unavailable"
    elif missing_scheduled:
        status = "blocked_forward_cohort_scheduled_scan_session_missing"
    next_action = (
        "validate_candidate_jsonl_read_only"
        if stage_report.get("candidate_rows_staged")
        else "repair_or_refresh_forward_session_ledger_read_only"
        if scheduled_session_error
        else "run_passive_forward_cohort_scan_sweep_in_valid_market_window"
        if missing_scheduled
        else "wait_for_valid_market_window_and_real_phase2_scan_picks"
    )
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_phase2_forward_candidate_throughput",
        "status": status,
        "scan_picks_path": _rel(scan_picks_path),
        "ledger_db_path": _rel(ledger_db_path),
        "scan_picks_exists": scan_picks_path.exists(),
        "scan_picks_row_count": len(rows),
        "malformed_scan_pick_rows": malformed,
        "freeze_date": FREEZE_DATE,
        "target_selection_date": target_date,
        "allowed_phase2_lanes": list(stager.ALLOWED_LANES),
        "post_freeze_scan_pick_count": len(post_freeze),
        "post_freeze_phase2_scan_pick_count": len(post_freeze_phase2),
        "target_date_scan_pick_count": len(target_rows),
        "target_date_phase2_scan_pick_count": len(target_phase2),
        "post_freeze_phase2_lane_counts": _counter_dict(post_phase2_lanes),
        "target_date_phase2_lane_counts": _counter_dict(target_phase2_lanes),
        "scheduled_scan_session_error": scheduled_session_error,
        "scheduled_scan_session_count": len(scheduled_sessions),
        "scheduled_scan_sessions": scheduled_sessions,
        "scheduled_phase2_playbooks_with_session": sorted(scheduled_playbooks),
        "scheduled_phase2_playbooks_missing_session": missing_scheduled,
        "scheduled_phase2_scan_picks_count": scheduled_pick_count,
        "scheduled_phase2_raw_candidates": scheduled_raw_candidates,
        "scheduled_phase2_returned_picks": scheduled_returned_picks,
        "scheduled_phase2_drop_count_total": sum(scheduled_drop_counts.values()),
        "scheduled_phase2_drop_counts": _counter_dict(scheduled_drop_counts),
        "scheduled_phase2_drop_stage_summary": scheduled_drop_stage_summary,
        "scheduled_phase2_scan_drop_reason_count_total": scheduled_drop_reason_count_total,
        "scheduled_phase2_scan_drop_reason_sample": scheduled_drop_reason_samples,
        "candidate_starvation_evidence_status": candidate_starvation_evidence_status,
        "zero_candidate_diagnostics": zero_candidate_diagnostics,
        "scheduled_phase2_eligibility_status_counts": _counter_dict(scheduled_eligibility_statuses),
        "scheduled_phase2_eligibility_blocker_counts": _counter_dict(scheduled_eligibility_blockers),
        "scheduled_phase2_all_lanes_scanned": not missing_scheduled and not scheduled_session_error,
        "passive_forward_cohort_scan_sweep_command": (
            "npm run options:scan:forward-cohort-sweep -- --force"
        ),
        "last_scan_pick_dates": sorted({_selection_date(row) for row in rows if _selection_date(row)})[-20:],
        "stager_status": stage_report.get("status"),
        "candidate_rows_staged": candidate_rows_staged,
        "candidate_jsonl_written": bool(stage_report.get("candidate_jsonl_written")),
        "candidate_jsonl_path": stage_report.get("output_path"),
        "stager_rejected_counts": _as_dict(stage_report.get("rejected_counts")),
        "validation": _as_dict(stage_report.get("validation")),
        "next_action": next_action,
        "accepted_profitability": False,
        "profitability_readiness": False,
        "cohort_append_performed": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
        "proof_bars_changed": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Forward Candidate Throughput Audit",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Target selection date: `{report.get('target_selection_date')}`.",
        f"- Scan-pick rows: `{report.get('scan_picks_row_count')}`.",
        f"- Post-freeze scan-pick rows: `{report.get('post_freeze_scan_pick_count')}`.",
        f"- Post-freeze Phase 2 rows: `{report.get('post_freeze_phase2_scan_pick_count')}`.",
        f"- Target-date rows: `{report.get('target_date_scan_pick_count')}`.",
        f"- Target-date Phase 2 rows: `{report.get('target_date_phase2_scan_pick_count')}`.",
        f"- Scheduled Phase 2 sessions: `{report.get('scheduled_scan_session_count')}`.",
        f"- Scheduled Phase 2 raw candidates: `{report.get('scheduled_phase2_raw_candidates')}`.",
        f"- Scheduled Phase 2 returned picks: `{report.get('scheduled_phase2_returned_picks')}`.",
        f"- Scheduled Phase 2 drop-count total: `{report.get('scheduled_phase2_drop_count_total')}`.",
        f"- Scheduled Phase 2 drop-stage status: `{_as_dict(report.get('scheduled_phase2_drop_stage_summary')).get('status')}`.",
        f"- Scheduled Phase 2 symbol drop reasons: `{report.get('scheduled_phase2_scan_drop_reason_count_total')}`.",
        f"- Candidate-starvation evidence status: `{report.get('candidate_starvation_evidence_status')}`.",
        f"- Zero-candidate diagnostics: `{_as_dict(report.get('zero_candidate_diagnostics')).get('status')}`.",
        f"- Scheduled Phase 2 scan picks: `{report.get('scheduled_phase2_scan_picks_count')}`.",
        f"- Scheduled Phase 2 all lanes scanned: `{str(bool(report.get('scheduled_phase2_all_lanes_scanned'))).lower()}`.",
        f"- Scheduled Phase 2 eligibility statuses: `{_as_dict(report.get('scheduled_phase2_eligibility_status_counts'))}`.",
        f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
        f"- Candidate JSONL written: `{str(bool(report.get('candidate_jsonl_written'))).lower()}`.",
        f"- Cohort append performed: `{str(bool(report.get('cohort_append_performed'))).lower()}`.",
        f"- Next action: `{report.get('next_action')}`.",
        "",
        "## Scheduled Sessions",
        "",
    ]
    sessions = report.get("scheduled_scan_sessions") if isinstance(report.get("scheduled_scan_sessions"), list) else []
    if sessions:
        for session in sessions:
            blockers = _parse_json_list(session.get("eligibility_blockers"))
            blocker_text = f" blockers `{', '.join(blockers)}`" if blockers else ""
            lines.append(
                f"- `{session.get('playbook')}` session `{session.get('id')}`: "
                f"`{session.get('scan_picks_count')}` picks, `{session.get('eligibility_status')}`, "
                f"`{session.get('scan_drop_reason_count', 0)}` symbol drop reasons.{blocker_text}"
            )
    else:
        lines.append("- None.")
    eligibility_blockers = _as_dict(report.get("scheduled_phase2_eligibility_blocker_counts"))
    if eligibility_blockers:
        lines.extend(["", "## Scheduled Eligibility Blockers", ""])
        lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(eligibility_blockers.items()))
    scheduled_drops = _as_dict(report.get("scheduled_phase2_drop_counts"))
    if scheduled_drops:
        lines.extend(["", "## Scheduled Drop Counts", ""])
        lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(scheduled_drops.items()))
    drop_summary = _as_dict(report.get("scheduled_phase2_drop_stage_summary"))
    top_stages = drop_summary.get("top_drop_stages") if isinstance(drop_summary.get("top_drop_stages"), list) else []
    if top_stages:
        lines.extend(["", "## Aggregate Candidate-Starvation Stages", ""])
        for item in top_stages:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('stage')}`: `{item.get('count')}`.")
    zero_diagnostics = _as_dict(report.get("zero_candidate_diagnostics"))
    if zero_diagnostics:
        safe_actions = zero_diagnostics.get("safe_next_read_only_actions")
        safe_action_text = ", ".join(f"`{item}`" for item in safe_actions) if isinstance(safe_actions, list) else "`none`"
        lines.extend(
            [
                "",
                "## Zero-Candidate Diagnostics",
                "",
                f"- Status: `{zero_diagnostics.get('status')}`.",
                f"- Scope: allowed lanes `{str(bool(zero_diagnostics.get('allowed_lanes_only'))).lower()}`, target date `{str(bool(zero_diagnostics.get('target_date_only'))).lower()}`, post-freeze `{str(bool(zero_diagnostics.get('post_freeze_only'))).lower()}`.",
                f"- Scheduled sessions reviewed: `{zero_diagnostics.get('scheduled_sessions_reviewed')}`.",
                f"- Symbol drop-reason status: `{zero_diagnostics.get('symbol_drop_reason_status')}`.",
                f"- Safe next read-only actions: {safe_action_text}.",
            ]
        )
    drop_reason_sample = report.get("scheduled_phase2_scan_drop_reason_sample")
    if isinstance(drop_reason_sample, list) and drop_reason_sample:
        lines.extend(["", "## Symbol Drop-Reason Samples", ""])
        for item in drop_reason_sample:
            if isinstance(item, dict):
                lines.append(
                    f"- `{item.get('symbol')}` / `{item.get('playbook')}`: "
                    f"`{item.get('drop_key')}`."
                )
    lines.extend(
        [
            "",
            "## Rejection Counts",
            "",
        ]
    )
    rejected = _as_dict(report.get("stager_rejected_counts"))
    lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(rejected.items())) if rejected else lines.append("- None.")
    lines.extend(
        [
            "",
            "This is a read-only throughput audit. It does not run the scanner, create trades, append cohort rows, import quotes, mutate evidence stores, change scanner policy, or promote a lane.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Phase 2 forward candidate throughput from scan-pick artifacts.")
    parser.add_argument("--scan-picks", type=Path, default=DEFAULT_SCAN_PICKS)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--selection-date", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(scan_picks_path=args.scan_picks, ledger_db_path=args.ledger_db, selection_date=args.selection_date)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
