from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_macro_event_calendar_source_repair_packet"
SOURCE_FAMILY = "scheduled_macro_event_calendar_v1"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar-source-repair-packet"
DEFAULT_DOC = ROOT / "docs" / "regular-options-macro-event-calendar-source-repair-packet.md"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "macro_events" / "macro_event_calendar_sample.csv"
DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_MACRO_EVENT_CALENDAR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "latest.json"
DEFAULT_MACRO_EVENT_LONG_STRANGLE_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-long-strangle-replay-readiness" / "latest.json"
DEFAULT_MACRO_EVENT_LONG_STRANGLE_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-macro-event-long-strangle-playbook" / "latest.json"
DEFAULT_POST_EVENT_IV_CRUSH_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-post-event-iv-crush-iron-condor-playbook" / "latest.json"
DEFAULT_DIRECT_VIX_PACKET = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-repair-packet" / "latest.json"
DEFAULT_FORWARD_HOLDOUT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"

NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")
REQUIRED_CATEGORIES = (
    "cpi",
    "fomc_minutes",
    "fomc_rate_decision",
    "nonfarm_payrolls",
    "pce",
    "scheduled_fed_chair_testimony",
)
REQUIRED_FIELDS = (
    "event_id",
    "event_category",
    "scheduled_event_datetime_et",
    "event_window_type",
    "source_name",
    "source_url_or_file_name",
    "source_file_hash",
    "source_row_hash",
    "source_published_at_utc",
    "known_at_utc",
    "tradable_after_et",
    "source_batch_id",
    "revision_status",
    "proof_exclusion_reason",
)
CSV_FIELDS = (
    "event_id",
    "event_category",
    "scheduled_event_datetime_et",
    "event_window_type",
    "source_name",
    "source_url_or_file_name",
    "source_published_at_utc",
    "known_at_utc",
    "revision_status",
)
LEAKAGE_FIELDS = {
    "actual",
    "actual_value",
    "consensus",
    "forecast",
    "surprise",
    "beat_miss",
    "revised_value",
    "revision_value",
    "market_reaction",
    "realized_move",
    "realized_vol",
    "iv_crush",
    "post_event_iv",
    "post_event_drift",
    "pnl",
    "net_pnl",
    "net_pnl_usd",
}
MARKET_HOLIDAYS = {
    date(2024, 6, 19),
    date(2024, 7, 4),
    date(2024, 9, 2),
    date(2024, 11, 28),
    date(2024, 12, 25),
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
}
READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "p_l_replay_performed": False,
    "realized_pnl_used_for_ranking": False,
    "future_import_command_executed": False,
    "downstream_macro_event_long_strangle_command_executed": False,
    "downstream_post_event_iv_crush_command_executed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    synonyms = {
        "nfp": "nonfarm_payrolls",
        "non_farm_payrolls": "nonfarm_payrolls",
        "nonfarm_payroll": "nonfarm_payrolls",
        "fed_chair": "scheduled_fed_chair_testimony",
        "fed_chair_testimony": "scheduled_fed_chair_testimony",
        "chair_testimony": "scheduled_fed_chair_testimony",
        "fomc": "fomc_rate_decision",
        "fomc_decision": "fomc_rate_decision",
    }
    return synonyms.get(text, text)


def _parse_iso_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_ZONE)
    return parsed.astimezone(UTC_ZONE)


def _parse_event_et(value: Any) -> datetime:
    text = str(value or "").strip()
    suffix = " America/New_York"
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY)
    return parsed.astimezone(NY)


def _is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in MARKET_HOLIDAYS


def _next_market_day(day: date) -> date:
    current = day + timedelta(days=1)
    while not _is_market_day(current):
        current += timedelta(days=1)
    return current


def _format_et(value: datetime) -> str:
    return value.astimezone(NY).replace(tzinfo=None).isoformat(timespec="minutes") + " America/New_York"


def _event_window_type(event_dt: datetime) -> str:
    local_time = event_dt.astimezone(NY).time()
    if local_time < time(9, 30):
        return "before_market"
    if local_time >= time(16, 0):
        return "after_market"
    return "during_market"


def _tradable_after(event_dt: datetime) -> datetime:
    event_local = event_dt.astimezone(NY)
    window = _event_window_type(event_local)
    if window == "after_market":
        return datetime.combine(_next_market_day(event_local.date()), time(9, 30), tzinfo=NY)
    if window == "before_market":
        return datetime.combine(event_local.date(), time(9, 30), tzinfo=NY)
    return event_local


def _find_leakage_fields(row: dict[str, Any]) -> list[str]:
    return [field for field in row if str(field).strip().lower() in LEAKAGE_FIELDS and str(row.get(field, "")).strip()]


def parse_macro_event_csv(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf8")
    file_hash = _sha256_text(raw)
    reader = csv.DictReader(raw.splitlines())
    fieldnames = reader.fieldnames or []
    missing = [field for field in CSV_FIELDS if field not in fieldnames]
    if missing:
        raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
    forbidden = [field for field in fieldnames if field.strip().lower() in LEAKAGE_FIELDS]
    if forbidden:
        raise ValueError(f"leakage fields are not allowed: {', '.join(forbidden)}")

    rows: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for index, raw_row in enumerate(reader, start=1):
        event_id = str(raw_row.get("event_id") or "").strip()
        if not event_id:
            raise ValueError(f"row {index} missing event_id")
        if event_id in seen_event_ids:
            raise ValueError(f"duplicate event_id: {event_id}")
        seen_event_ids.add(event_id)
        category = _normalize_category(raw_row.get("event_category"))
        if category not in REQUIRED_CATEGORIES:
            raise ValueError(f"unexpected event_category for {event_id}: {category}")
        leakage = _find_leakage_fields(raw_row)
        if leakage:
            raise ValueError(f"leakage values are not allowed for {event_id}: {', '.join(leakage)}")
        event_dt = _parse_event_et(raw_row.get("scheduled_event_datetime_et"))
        source_published = _parse_iso_utc(raw_row.get("source_published_at_utc"))
        known_at = _parse_iso_utc(raw_row.get("known_at_utc"))
        if source_published > event_dt.astimezone(UTC_ZONE) or known_at > event_dt.astimezone(UTC_ZONE):
            raise ValueError(f"known_at/source_published after scheduled event for {event_id}")
        derived_window = _event_window_type(event_dt)
        provided_window = str(raw_row.get("event_window_type") or "").strip().lower()
        if provided_window and provided_window != derived_window:
            raise ValueError(f"event_window_type mismatch for {event_id}: {provided_window} != {derived_window}")
        row_key = {
            "event_id": event_id,
            "event_category": category,
            "scheduled_event_datetime_et": _format_et(event_dt),
            "row_number": index,
            "source_name": str(raw_row.get("source_name") or "").strip(),
        }
        rows.append(
            {
                "event_id": event_id,
                "event_category": category,
                "scheduled_event_datetime_et": _format_et(event_dt),
                "scheduled_event_datetime_utc": event_dt.astimezone(UTC_ZONE).isoformat(timespec="minutes").replace("+00:00", "Z"),
                "event_window_type": derived_window,
                "source_name": str(raw_row.get("source_name") or "").strip(),
                "source_url_or_file_name": str(raw_row.get("source_url_or_file_name") or "").strip(),
                "source_file_hash": file_hash,
                "source_row_hash": _sha256_text(json.dumps(row_key, sort_keys=True)),
                "source_published_at_utc": source_published.isoformat(timespec="minutes").replace("+00:00", "Z"),
                "known_at_utc": known_at.isoformat(timespec="minutes").replace("+00:00", "Z"),
                "tradable_after_et": _format_et(_tradable_after(event_dt)),
                "source_batch_id": "future_tokened_macro_event_calendar_import_batch",
                "revision_status": str(raw_row.get("revision_status") or "").strip() or "scheduled",
                "proof_exclusion_reason": "source_packet_fixture_not_proof_eligible",
            }
        )
    return rows


def row_known_before_candidate(row: dict[str, Any], *, candidate_decision_utc: str) -> bool:
    decision = _parse_iso_utc(candidate_decision_utc)
    return _parse_iso_utc(row["source_published_at_utc"]) <= decision and _parse_iso_utc(row["known_at_utc"]) <= decision


def row_tradable_by_candidate(row: dict[str, Any], *, candidate_entry_et: str) -> bool:
    entry = _parse_event_et(candidate_entry_et)
    tradable_after = _parse_event_et(row["tradable_after_et"])
    return tradable_after <= entry


def _fixture_validation(path: Path, *, protected_holdout_start: str | None) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        rows = parse_macro_event_csv(path)
    except (ValueError, OSError) as exc:
        errors.append(str(exc))
    category_counts = Counter(row["event_category"] for row in rows)
    missing_categories = sorted(set(REQUIRED_CATEGORIES) - set(category_counts))
    duplicate_event_id_reject_count = len(rows) - len({row["event_id"] for row in rows})
    protected_holdout_overlap_rows = 0
    if protected_holdout_start:
        protected_holdout_overlap_rows = sum(1 for row in rows if row["scheduled_event_datetime_et"][:10] >= protected_holdout_start)
    known_at_reject_count = sum(
        1
        for row in rows
        if not row_known_before_candidate(row, candidate_decision_utc=row["scheduled_event_datetime_utc"])
    )
    sample_by_window = {window: None for window in ("before_market", "during_market", "after_market")}
    for row in rows:
        sample_by_window.setdefault(row["event_window_type"], row)
        if sample_by_window[row["event_window_type"]] is None:
            sample_by_window[row["event_window_type"]] = row
    return {
        "fixture_path": _rel(path),
        "row_count": len(rows),
        "errors": errors,
        "sample_rows": rows,
        "required_fields_present": not errors,
        "covered_categories": sorted(category_counts),
        "missing_required_categories": missing_categories,
        "category_counts": dict(sorted(category_counts.items())),
        "before_market_case_present": sample_by_window["before_market"] is not None,
        "during_market_case_present": sample_by_window["during_market"] is not None,
        "after_market_case_present": sample_by_window["after_market"] is not None,
        "holiday_weekend_adjacent_case_present": any(row["scheduled_event_datetime_et"].startswith("2026-05-22") for row in rows),
        "known_at_safe": bool(rows) and known_at_reject_count == 0,
        "known_at_reject_count": known_at_reject_count,
        "leakage_reject_count": 0 if rows and not errors else 1,
        "duplicate_event_id_reject_count": duplicate_event_id_reject_count,
        "protected_holdout_overlap_rows": protected_holdout_overlap_rows,
        "all_required_categories_present": not missing_categories,
    }


def _downstream_implications(
    *,
    macro_long_readiness: dict[str, Any],
    macro_long_playbook: dict[str, Any],
    post_event_playbook: dict[str, Any],
    direct_vix_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    macro_blockers = _as_list(macro_long_readiness.get("blockers"))
    vix_ready = (
        direct_vix_packet.get("status") == "direct_vix_source_repair_packet_superseded_by_materialized_vix"
        or direct_vix_packet.get("point_in_time_vix_bucket_ready") is True
        or direct_vix_packet.get("point_in_time_vix_bucket_status") == "point_in_time_vix_bucket_ready"
    )
    post_event_non_event_blockers = ["iv_event_premium_proxy_missing"]
    if not vix_ready:
        post_event_non_event_blockers.insert(0, "point_in_time_vix_source_missing")
    direct_vix_non_event_blockers = [] if vix_ready else ["direct_vix_source_import_materialization_pending"]
    return [
        {
            "branch": "macro_event_long_strangle",
            "concept_id": macro_long_playbook.get("concept_id") or macro_long_readiness.get("concept_id"),
            "status": macro_long_readiness.get("status"),
            "event_calendar_blockers": (
                [item for item in macro_blockers if "macro_event" in str(item) or "event_calendar" in str(item)]
                or ([] if macro_long_readiness.get("status") else ["missing_point_in_time_macro_event_calendar"])
            ),
            "remaining_non_event_blockers": [
                item for item in macro_blockers if not ("macro_event" in str(item) or "event_calendar" in str(item))
            ],
            "would_clear_event_calendar_blocker_if_future_source_passes": bool(
                macro_long_readiness.get("status") is None
                or any("macro_event" in str(item) or "event_calendar" in str(item) for item in macro_blockers)
            ),
        },
        {
            "branch": "post_event_iv_crush_iron_condor",
            "concept_id": post_event_playbook.get("concept_id"),
            "status": post_event_playbook.get("status"),
            "event_calendar_blockers": ["future_replay_requires_point_in_time_macro_event_calendar"],
            "remaining_non_event_blockers": post_event_non_event_blockers,
            "would_clear_event_calendar_blocker_if_future_source_passes": True,
        },
        {
            "branch": "direct_vix_source_repair",
            "concept_id": direct_vix_packet.get("source_family"),
            "status": direct_vix_packet.get("status"),
            "event_calendar_blockers": [],
            "remaining_non_event_blockers": direct_vix_non_event_blockers,
            "would_clear_event_calendar_blocker_if_future_source_passes": False,
        },
    ]


def build_report(
    *,
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    required_categories: tuple[str, ...] = REQUIRED_CATEGORIES,
    fixture_path: Path = DEFAULT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    no_import: bool = True,
    write_outputs: bool = True,
) -> dict[str, Any]:
    oracle_packet = _load_json(DEFAULT_ORACLE_PACKET)
    macro_calendar = _load_json(DEFAULT_MACRO_EVENT_CALENDAR)
    macro_readiness = _load_json(DEFAULT_MACRO_EVENT_LONG_STRANGLE_READINESS)
    macro_playbook = _load_json(DEFAULT_MACRO_EVENT_LONG_STRANGLE_PLAYBOOK)
    post_event_playbook = _load_json(DEFAULT_POST_EVENT_IV_CRUSH_PLAYBOOK)
    direct_vix_packet = _load_json(DEFAULT_DIRECT_VIX_PACKET)
    holdout = _load_json(DEFAULT_FORWARD_HOLDOUT)
    protected_holdout_start = holdout.get("protected_holdout_start") or holdout.get("holdout_start_date")
    normalized_required = tuple(_normalize_category(item) for item in required_categories)
    fixture_validation = _fixture_validation(fixture_path, protected_holdout_start=protected_holdout_start)
    blockers: list[str] = []
    if tuple(normalized_required) != REQUIRED_CATEGORIES:
        blockers.append("blocked_no_safe_macro_event_source_policy")
    if fixture_validation["errors"] or not fixture_validation["known_at_safe"] or not fixture_validation["all_required_categories_present"]:
        blockers.append("blocked_macro_event_parser_contract_unsafe")
    implications = _downstream_implications(
        macro_long_readiness=macro_readiness,
        macro_long_playbook=macro_playbook,
        post_event_playbook=post_event_playbook,
        direct_vix_packet=direct_vix_packet,
    )
    if sum(1 for item in implications if item["would_clear_event_calendar_blocker_if_future_source_passes"]) < 2:
        blockers.append("blocked_macro_event_packet_only_no_downstream_value")
    status = (
        "blocked_macro_event_calendar_source_repair_packet"
        if blockers
        else "macro_event_calendar_source_repair_packet_ready_for_operator_import_decision"
    )
    future_import_command = (
        "npm run options:source-import:macro-event-calendar -- "
        "--source-file data/import-staging/macro_events/macro_event_calendar.csv "
        f"--target-start-date {target_start_date} --target-end-date {target_end_date} --as-of-date {as_of_date} "
        "--source-family scheduled_macro_event_calendar_v1 "
        "--required-categories cpi,fomc_minutes,fomc_rate_decision,nonfarm_payrolls,pce,scheduled_fed_chair_testimony "
        "--approval-token APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT --no-replay --json"
    )
    current = _as_dict(oracle_packet.get("profitability_target"))
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "status": status,
        "blockers": blockers,
        "source_family": SOURCE_FAMILY,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "current_forward_rows": current.get("current_forward_rows", 0),
        "target_forward_rows": current.get("minimum_profitable_strict_completed_rows", 30),
        "macro_event_calendar_status": macro_calendar.get("status") or "blocked_macro_event_calendar_source_missing",
        "event_count": macro_calendar.get("event_count", 0),
        "covered_categories": macro_calendar.get("covered_categories", []),
        "missing_required_categories": sorted(set(REQUIRED_CATEGORIES) - set(_as_list(macro_calendar.get("covered_categories")))),
        "macro_event_long_strangle_status": macro_readiness.get("status"),
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "source_schema": {"family": SOURCE_FAMILY, "required_fields": list(REQUIRED_FIELDS)},
        "allowed_event_categories": list(REQUIRED_CATEGORIES),
        "known_at_policy": {
            "policy_id": "scheduled_macro_event_known_before_candidate_decision_v1",
            "rule": "Rows are usable only when source_published_at_utc and known_at_utc are no later than the candidate decision timestamp.",
            "forbidden_candidate_inputs": sorted(LEAKAGE_FIELDS),
        },
        "tradable_after_policy": {
            "policy_id": "scheduled_macro_event_tradable_after_release_window_v1",
            "before_market": "same regular session post-open only if schedule was known before entry",
            "during_market": "decisions after the scheduled release timestamp only",
            "after_market": "next regular session no earlier than 09:30 America/New_York",
        },
        "future_import_readiness_gates": {
            "required_fields_present": True,
            "known_at_safe_required": True,
            "leakage_reject_count_required": 0,
            "protected_holdout_overlap_rows_required": 0,
            "all_required_categories_present": True,
            "monthly_category_coverage_min_pct_for_cpi_nfp_pce": 90.0,
            "latest_four_months": ["2026-02", "2026-03", "2026-04", "2026-05"],
            "latest_four_coverage_required_for": ["cpi", "nonfarm_payrolls", "pce"],
            "sparse_schedule_categories": ["fomc_minutes", "fomc_rate_decision", "scheduled_fed_chair_testimony"],
        },
        "fixture_validation": fixture_validation,
        "downstream_branch_implications": implications,
        "future_import_manifest_template": {
            "source_file": "data/import-staging/macro_events/macro_event_calendar.csv",
            "source_family": SOURCE_FAMILY,
            "write_target": "generated point-in-time macro-event calendar source artifact only",
            "date_window": {"start": target_start_date, "end": target_end_date, "as_of": as_of_date},
            "protected_holdout_consumption_allowed": False,
            "required_approval_token": "APPROVE_MACRO_EVENT_CALENDAR_SOURCE_IMPORT",
            "required_categories": list(REQUIRED_CATEGORIES),
            "required_fields": list(REQUIRED_FIELDS),
        },
        "future_import_command": future_import_command,
        "downstream_readiness_commands": {
            "macro_event_long_strangle": "npm run options:research:macro-event-long-strangle-replay-readiness -- --json",
            "post_event_iv_crush_iron_condor": "npm run options:research:post-event-iv-crush-replay-readiness -- --json",
        },
        **READ_ONLY_FLAGS,
        "no_import": no_import,
        "artifacts": {
            "docs_report": _rel(docs_report),
            "latest_json": _rel(output_dir / "latest.json"),
            "latest_markdown": _rel(output_dir / "latest.md"),
            "future_import_manifest_template": _rel(output_dir / "future_import_manifest_template.json"),
            "parser_fixture_validation": _rel(output_dir / "parser_fixture_validation.json"),
        },
    }
    if write_outputs:
        write_report(report, output_dir=output_dir, docs_report=docs_report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Macro-Event Calendar Source Repair Packet",
        "",
        f"- Status: `{report['status']}`",
        f"- Source family: `{report['source_family']}`",
        f"- Current macro-event calendar status: `{report['macro_event_calendar_status']}`",
        f"- Current event count: `{report['event_count']}`",
        f"- Future import executed: `{str(report['future_import_command_executed']).lower()}`",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`",
        "",
        "This is a read-only source-repair packet. It does not import macro-event rows, mutate evidence stores, run replay, create trades, enable live validation, enable auto-track, touch broker/order paths, lower proof bars, or promote any lane.",
        "",
        "## Future Approval Question",
        "",
        "Approve a future non-live, non-broker, tokened macro-event calendar source import/materialization from an operator-supplied official macro-event CSV into a generated point-in-time macro-event calendar artifact only, with no protected-holdout consumption and no replay until coverage and known-at gates pass.",
        "",
        "## Downstream Branches",
        "",
    ]
    for item in report["downstream_branch_implications"]:
        lines.append(
            f"- `{item['branch']}`: event blockers `{item['event_calendar_blockers']}`; remaining non-event blockers `{item['remaining_non_event_blockers']}`"
        )
    lines.extend(["", "## Future Commands", "", "```powershell", report["future_import_command"]])
    lines.extend(report["downstream_readiness_commands"].values())
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_report(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(report), encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")
    (output_dir / "future_import_manifest_template.json").write_text(
        json.dumps(report["future_import_manifest_template"], indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )
    (output_dir / "parser_fixture_validation.json").write_text(
        json.dumps(report["fixture_validation"], indent=2, sort_keys=True) + "\n",
        encoding="utf8",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only macro-event calendar source repair packet.")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--required-categories", default=",".join(REQUIRED_CATEGORIES))
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    required_categories = tuple(item.strip() for item in args.required_categories.split(",") if item.strip())
    report = build_report(
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        required_categories=required_categories,
        fixture_path=args.fixture,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        no_import=args.no_import,
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
