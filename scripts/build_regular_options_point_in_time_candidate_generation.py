from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_robust_search_evaluation import (  # noqa: E402
    DEFAULT_FEATURE_STORE_REPORT,
    DEFAULT_SOURCE_QUALITY_POLICY,
    DEFAULT_SOURCE_REPORT,
    _load_json,
    apply_source_quality_scope_policy,
    normalize_trades,
)


REPORT_ID = "regular_options_point_in_time_candidate_generation"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-candidate-generation"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-candidate-generation.md"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_WINDOW_START = "2024-06-01"
DEFAULT_WINDOW_END = "2026-05-31"
DEFAULT_AS_OF_DATE = "2026-06-04"
RUNNER_FILES = (
    ROOT / "scripts" / "run_bullish_pullback_sleeves.py",
    ROOT / "scripts" / "run_bullish_pullback_next_round.py",
    ROOT / "scripts" / "run_regular_options_all_planned_sleeves.py",
)

PROHIBITED_ACTIONS = (
    "do_not_import_quotes_from_point_in_time_candidate_generation",
    "do_not_mutate_evidence_stores_from_point_in_time_candidate_generation",
    "do_not_overwrite_regular_options_multilane_latest_from_point_in_time_candidate_generation",
    "do_not_create_live_trades_from_point_in_time_candidate_generation",
    "do_not_submit_broker_orders_from_point_in_time_candidate_generation",
    "do_not_enable_live_validation_from_point_in_time_candidate_generation",
    "do_not_enable_auto_track_from_point_in_time_candidate_generation",
    "do_not_change_scanner_policy_from_point_in_time_candidate_generation",
    "do_not_change_strategy_logic_from_point_in_time_candidate_generation",
    "do_not_change_stops_or_sizing_from_point_in_time_candidate_generation",
    "do_not_lower_proof_bars_from_point_in_time_candidate_generation",
    "do_not_consume_protected_holdout_from_point_in_time_candidate_generation",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_date(value: Any) -> date | None:
    raw = "" if value is None else str(value).strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _month_key(value: Any) -> str | None:
    parsed = _parse_date(value)
    return f"{parsed.year:04d}-{parsed.month:02d}" if parsed else None


def _month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return months


def _holdout_start(contract: dict[str, Any]) -> date | None:
    return _parse_date(_as_dict(contract.get("protected_range")).get("start_date"))


def _shared_quote_months(feature: dict[str, Any]) -> set[str]:
    months = {_month_key(item) for item in _as_list(feature.get("shared_quote_dates"))}
    months.discard(None)
    summary = _as_dict(feature.get("summary"))
    first = _parse_date(summary.get("first_shared_quote_date_et"))
    latest = _parse_date(summary.get("latest_shared_quote_date_et"))
    if first and latest:
        months.update(_month_range(first, latest))
    return {str(month) for month in months if month}


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _trade_entry_date(row: dict[str, Any]) -> str:
    return str(row.get("entry_date") or row.get("date") or row.get("candidate_entry_date") or "")[:10]


def _trade_direction(row: dict[str, Any]) -> str:
    return str(row.get("direction") or row.get("type") or row.get("trade_type") or "").strip().lower()


def _trade_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (_trade_entry_date(row), str(row.get("ticker") or "").strip().upper(), _trade_direction(row))


def _resolve_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate.resolve()


def _source_artifact_paths(rows: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for row in rows:
        path = _resolve_path(row.get("source_result_path") or row.get("source_id") or row.get("variant_id"))
        if path is None:
            continue
        key = str(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)
    return paths


def _runner_entrypoint_paths(playbook_id: str) -> list[str]:
    hits: list[str] = []
    if not playbook_id:
        return hits
    needle = str(playbook_id)
    for path in RUNNER_FILES:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf8")
        except OSError:
            continue
        if needle in text:
            try:
                hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            except ValueError:
                hits.append(str(path))
    return hits


def _load_source_artifacts(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in paths:
        meta = {"path": str(path), "exists": path.exists(), "status": "missing"}
        if not path.exists():
            errors.append(meta)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except Exception as exc:
            meta["status"] = "unreadable"
            meta["error"] = str(exc)
            errors.append(meta)
            continue
        playbook = str(payload.get("playbook") or payload.get("playbook_id") or path.stem)
        diagnostics = [_as_dict(item) for item in _as_list(payload.get("daily_selection_diagnostics"))]
        diagnostic_months = sorted({_month_key(item.get("date")) for item in diagnostics if _month_key(item.get("date"))})
        selected_months = sorted(
            {
                _month_key(item.get("date"))
                for item in diagnostics
                if _month_key(item.get("date")) and int(item.get("selected_count") or 0) > 0
            }
        )
        raw_trades = [_as_dict(item) for item in _as_list(payload.get("trades"))]
        unpriced = [_as_dict(item) for item in _as_list(payload.get("unpriced_trades"))]
        artifacts.append(
            {
                "path": path,
                "path_text": str(path),
                "status": "loaded",
                "playbook": playbook,
                "run_at": payload.get("run_at") or payload.get("generated_at_utc") or payload.get("generated_at"),
                "lookback_years": payload.get("lookback_years"),
                "replay_as_of_date": payload.get("replay_as_of_date"),
                "replay_calendar": _as_dict(payload.get("replay_calendar")),
                "daily_selection_diagnostics": diagnostics,
                "diagnostic_months": [str(month) for month in diagnostic_months if month],
                "selected_diagnostic_months": [str(month) for month in selected_months if month],
                "trades": raw_trades,
                "unpriced_trades": unpriced,
                "trade_keys": {_trade_key(item) for item in raw_trades},
                "runner_entrypoints": _runner_entrypoint_paths(playbook),
            }
        )
    return artifacts, errors


def _reproduction_check(rows: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    by_path = {str(item["path"]): item for item in artifacts}
    missing_rows: list[dict[str, Any]] = []
    checked = 0
    for row in rows:
        path = _resolve_path(row.get("source_result_path") or row.get("source_id") or row.get("variant_id"))
        key = _trade_key(row)
        checked += 1
        artifact = by_path.get(str(path)) if path is not None else None
        if artifact is None or key not in artifact.get("trade_keys", set()):
            missing_rows.append(
                {
                    "entry_date": key[0],
                    "ticker": key[1],
                    "direction": key[2],
                    "source_result_path": str(path) if path else None,
                    "lane_id": row.get("lane_id"),
                    "pnl_pct": row.get("pnl_pct"),
                }
            )
    return {
        "status": "passed" if not missing_rows else "failed",
        "checked_selected_rows": checked,
        "missing_selected_rows": missing_rows[:50],
        "missing_selected_row_count": len(missing_rows),
    }


def _selected_rows_by_month(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        month = _month_key(row.get("entry_date"))
        if month:
            grouped[month].append(dict(row))
    return dict(grouped)


def _diagnostics_by_month(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        playbook = str(artifact.get("playbook") or "unknown")
        for diagnostic in artifact.get("daily_selection_diagnostics") or []:
            diagnostic = _as_dict(diagnostic)
            month = _month_key(diagnostic.get("date"))
            if not month:
                continue
            bucket = grouped.setdefault(
                month,
                {
                    "candidate_generation_days": 0,
                    "selected_days": 0,
                    "zero_selection_days": 0,
                    "candidate_count": 0,
                    "selected_count": 0,
                    "preflight_rejected_count": 0,
                    "playbooks": set(),
                },
            )
            bucket["candidate_generation_days"] += 1
            selected_count = int(diagnostic.get("selected_count") or 0)
            candidate_count = int(diagnostic.get("candidate_count") or 0)
            bucket["candidate_count"] += candidate_count
            bucket["selected_count"] += selected_count
            bucket["preflight_rejected_count"] += int(diagnostic.get("preflight_rejected_count") or 0)
            if selected_count > 0:
                bucket["selected_days"] += 1
            else:
                bucket["zero_selection_days"] += 1
            bucket["playbooks"].add(playbook)
    for bucket in grouped.values():
        bucket["playbooks"] = sorted(str(item) for item in bucket.get("playbooks", set()))
    return grouped


def _audit_ready_selected_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item.setdefault("row_id", item.get("dedupe_key") or f"candidate_generation_selected_trade_{index}")
        item.setdefault("exact_priced", True)
        item.setdefault("entry_contract_resolution", "exact_listed_spread_contract")
        item.setdefault("fill_basis", "imported_spread_mark")
        item.setdefault("priced", True)
        item.setdefault("research_backfill", True)
        item.setdefault("production_proof", False)
        item.setdefault("current_definition_historical_replay", True)
        item.setdefault("protected_holdout_overlap", False)
        item.setdefault("candidate_entry_month", _month_key(item.get("entry_date")))
        item.setdefault("selection_timestamp_basis", "current_definition_historical_replay_from_source_artifact_diagnostics")
        item.setdefault("feature_asof_gate", "source_artifact_daily_selection_diagnostics")
        item.setdefault("entry_quote_evidence_class", item.get("proof_grade"))
        item.setdefault("exit_quote_evidence_class", item.get("proof_grade"))
        audit_rows.append(item)
    return audit_rows


def build_report(
    *,
    source_report_path: Path = DEFAULT_SOURCE_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    source_quality_policy_path: Path | None = DEFAULT_SOURCE_QUALITY_POLICY,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source, source_meta = _load_json(source_report_path)
    feature, feature_meta = _load_json(feature_store_report_path)
    policy, policy_meta = (
        _load_json(source_quality_policy_path)
        if source_quality_policy_path
        else ({}, {"status": "missing", "path": None, "exists": False, "error": "policy_not_configured"})
    )
    holdout, holdout_meta = _load_json(holdout_contract_path)
    start = _parse_date(window_start)
    end = _parse_date(window_end)
    as_of = _parse_date(as_of_date)
    if start is None or end is None or as_of is None or end < start:
        raise ValueError("window-start, window-end, and as-of-date must be valid YYYY-MM-DD values with start <= end")

    raw_rows, rejected = normalize_trades(_as_list(source.get("selected_trades")))
    scoped_rows, source_quality_exclusions = apply_source_quality_scope_policy(
        raw_rows,
        policy=policy,
        policy_meta=policy_meta,
    )
    selected_rows = [
        dict(row)
        for row in scoped_rows
        if (parsed := _parse_date(row.get("entry_date"))) is not None and start <= parsed <= end and parsed <= as_of
    ]
    selected_rows.sort(key=lambda item: (str(item.get("entry_date")), str(item.get("ticker")), str(item.get("lane_id"))))
    artifact_paths = _source_artifact_paths(selected_rows)
    artifacts, artifact_errors = _load_source_artifacts(artifact_paths)
    reproduction = _reproduction_check(selected_rows, artifacts)
    diagnostics_by_month = _diagnostics_by_month(artifacts)
    selected_by_month = _selected_rows_by_month(selected_rows)
    requested_months = _month_range(start, end)
    quote_months = _shared_quote_months(feature)
    feature_summary = _as_dict(feature.get("summary"))
    feature_store_available = (
        feature_meta.get("status") == "loaded"
        and str(feature.get("status") or feature_summary.get("overall_status") or "").startswith("feature_store_built")
    )
    protected_start = _holdout_start(holdout)
    artifact_playbooks = {str(item.get("playbook") or "") for item in artifacts}
    source_artifact_count = len(artifacts)
    missing_entrypoints = sorted(
        str(item.get("playbook"))
        for item in artifacts
        if str(item.get("playbook") or "") and not item.get("runner_entrypoints")
    )

    month_diagnostics: list[dict[str, Any]] = []
    for month in requested_months:
        month_start = _parse_date(f"{month}-01")
        holdout_overlap = (
            month_start is not None
            and protected_start is not None
            and month_start >= protected_start.replace(day=1)
        )
        rows = selected_by_month.get(month, [])
        diag = diagnostics_by_month.get(month, {})
        playbooks_with_diag = set(diag.get("playbooks") or [])
        all_artifacts_ran = source_artifact_count > 0 and artifact_playbooks.issubset(playbooks_with_diag)
        quote_history_available = month in quote_months
        candidate_generation_proven = bool(
            all_artifacts_ran
            and quote_history_available
            and feature_store_available
            and reproduction.get("status") == "passed"
            and not holdout_overlap
        )
        if holdout_overlap:
            stage_status = "historical_depth_protected_holdout_overlap_blocked"
        elif candidate_generation_proven and rows:
            stage_status = "selected_trades_available_after_candidate_generation"
        elif candidate_generation_proven:
            stage_status = "historical_depth_no_natural_selections_after_current_policy"
        elif reproduction.get("status") != "passed":
            stage_status = "historical_depth_source_reproduction_failed_existing_months"
        elif not quote_history_available:
            stage_status = "historical_depth_quote_history_missing"
        elif not feature_store_available:
            stage_status = "historical_depth_feature_join_not_point_in_time_safe"
        elif source_artifact_count == 0:
            stage_status = "historical_depth_candidate_generator_entrypoint_missing"
        else:
            stage_status = "historical_depth_candidate_generation_diagnostics_missing_for_month"
        stage_reasons = [
            "quote_history_available" if quote_history_available else "quote_history_missing",
            "feature_store_available" if feature_store_available else "feature_store_missing",
            "source_reproduction_passed" if reproduction.get("status") == "passed" else "source_reproduction_failed",
            "all_source_artifacts_have_daily_diagnostics" if all_artifacts_ran else "source_artifact_daily_diagnostics_missing",
        ]
        if rows:
            stage_reasons.append("selected_rows_present")
        elif candidate_generation_proven:
            stage_reasons.append("zero_selection_month_explicit")
        else:
            stage_reasons.append("zero_selection_month_not_proven")
        if holdout_overlap:
            stage_reasons.append("protected_holdout_overlap")
        month_diagnostics.append(
            {
                "month": month,
                "as_of_date": as_of.isoformat(),
                "calendar_month_covered": candidate_generation_proven,
                "selected_trade_calendar_covered": candidate_generation_proven,
                "candidate_generation_attempted": bool(diag),
                "candidate_generation_proven": candidate_generation_proven,
                "quote_history_available": quote_history_available,
                "feature_store_available": feature_store_available,
                "source_artifact_playbooks_expected": sorted(artifact_playbooks),
                "source_artifact_playbooks_with_diagnostics": sorted(playbooks_with_diag),
                "candidate_generation_days": int(diag.get("candidate_generation_days") or 0),
                "candidate_count": int(diag.get("candidate_count") or 0),
                "selected_trade_count": len(rows),
                "exact_selected_trade_count": len(rows),
                "diagnostic_selected_count": int(diag.get("selected_count") or 0),
                "zero_selection_month": len(rows) == 0,
                "zero_selection_month_explicit": len(rows) == 0 and candidate_generation_proven,
                "stage_status": stage_status,
                "stage_reasons": stage_reasons,
                "protected_holdout_overlap": holdout_overlap,
            }
        )

    covered_months = [row["month"] for row in month_diagnostics if row["candidate_generation_proven"]]
    selected_months = [row["month"] for row in month_diagnostics if row["selected_trade_count"] > 0]
    zero_selection_months = [row["month"] for row in month_diagnostics if row["zero_selection_month_explicit"]]
    unproven_months = [row["month"] for row in month_diagnostics if not row["candidate_generation_proven"]]
    stage_counts = Counter(str(row["stage_status"]) for row in month_diagnostics)
    by_lane = Counter(str(row.get("lane_id") or "unknown") for row in selected_rows)
    by_month = Counter(_month_key(row.get("entry_date")) or "unknown" for row in selected_rows)

    blockers: list[str] = []
    if source_meta.get("status") != "loaded":
        blockers.append("source_report_not_loaded")
    if feature_meta.get("status") != "loaded":
        blockers.append("feature_store_report_not_loaded")
    if holdout_meta.get("status") != "loaded" or protected_start is None:
        blockers.append("protected_holdout_contract_not_loaded")
    if artifact_errors:
        blockers.append("historical_depth_source_artifacts_not_loaded")
    if reproduction.get("status") != "passed":
        blockers.append("historical_depth_source_reproduction_failed_existing_months")
    if missing_entrypoints:
        blockers.append("historical_depth_candidate_generator_entrypoint_missing")
    if len(covered_months) < len(requested_months):
        blockers.append(f"calendar_months_covered_{len(covered_months)}_below_requested_{len(requested_months)}")
    if unproven_months:
        blockers.append("selected_trade_calendar_coverage_not_proven")
    if stage_counts.get("historical_depth_candidate_generation_diagnostics_missing_for_month"):
        blockers.append("historical_depth_candidate_generation_diagnostics_missing_for_month")
    if any(row["stage_status"] == "historical_depth_protected_holdout_overlap_blocked" for row in month_diagnostics):
        blockers.append("historical_depth_protected_holdout_overlap_blocked")
    diagnostic_month_count = len({month for artifact in artifacts for month in artifact.get("diagnostic_months", [])})
    if diagnostic_month_count == 8:
        blockers.append("historical_depth_existing_replay_artifacts_only_8_diagnostic_months")

    status = "point_in_time_candidate_generation_ready_for_audit" if not blockers else "blocked_point_in_time_candidate_generation"
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "canonical_multilane_latest_overwritten": False,
        "scanner_policy_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
        "proof_bars_changed": False,
        "protected_holdout_consumed": False,
        "scope": "regular_options_point_in_time_candidate_generation_reconstruction",
        "inputs": {
            "source_report": source_meta,
            "feature_store_report": feature_meta,
            "source_quality_policy": policy_meta,
            "holdout_contract": holdout_meta,
        },
        "requested_calendar_window": {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "as_of_date": as_of.isoformat(),
            "requested_months": requested_months,
            "requested_calendar_month_count": len(requested_months),
        },
        "source_reproduction_check": reproduction,
        "source_artifact_inventory": [
            {
                "path": artifact.get("path_text"),
                "playbook": artifact.get("playbook"),
                "run_at": artifact.get("run_at"),
                "lookback_years": artifact.get("lookback_years"),
                "replay_as_of_date": artifact.get("replay_as_of_date"),
                "replay_calendar": artifact.get("replay_calendar"),
                "daily_selection_diagnostic_day_count": len(artifact.get("daily_selection_diagnostics") or []),
                "diagnostic_months": artifact.get("diagnostic_months"),
                "selected_diagnostic_months": artifact.get("selected_diagnostic_months"),
                "trade_count": len(artifact.get("trades") or []),
                "unpriced_trade_count": len(artifact.get("unpriced_trades") or []),
                "runner_entrypoints": artifact.get("runner_entrypoints"),
            }
            for artifact in artifacts
        ],
        "source_artifact_errors": artifact_errors,
        "calendar_coverage": {
            "status": "calendar_coverage_proven" if status == "point_in_time_candidate_generation_ready_for_audit" else "calendar_coverage_not_proven",
            "coverage_basis": (
                "explicit_candidate_generation_calendar_coverage"
                if status == "point_in_time_candidate_generation_ready_for_audit"
                else "source_artifact_daily_selection_diagnostics_incomplete"
            ),
            "covered_months": covered_months,
            "calendar_months_covered": covered_months,
            "calendar_months_covered_count": len(covered_months),
            "selected_entry_months_with_rows": selected_months,
            "selected_entry_months_with_rows_count": len(selected_months),
            "zero_selection_months": zero_selection_months,
            "zero_selection_months_explicit": status == "point_in_time_candidate_generation_ready_for_audit",
            "unproven_requested_months": unproven_months,
            "unproven_requested_month_count": len(unproven_months),
        },
        "month_diagnostics": month_diagnostics,
        "stage_status_counts": dict(sorted(stage_counts.items())),
        "selected_trade_summary": {
            "accepted_exact_trade_count_before_source_quality_scope": len(raw_rows),
            "source_quality_excluded_trade_count": len(source_quality_exclusions),
            "selected_rows_in_window": len(selected_rows),
            "rejected_row_counts": dict(sorted(rejected.items())),
            "by_lane": dict(sorted(by_lane.items())),
            "by_month": dict(sorted(by_month.items())),
        },
        "selected_trades": _audit_ready_selected_rows(selected_rows),
        "source_quality_exclusions": source_quality_exclusions,
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "read-only reconstruction of existing selected-trade source artifacts and their daily candidate-generation diagnostics",
            "readback_is_not": "fresh forward proof, a quote import, a scanner change, a strategy change, a proof-bar change, live-validation eligibility, broker action, or protected-holdout consumption",
            "current_limitation": "existing source artifacts only prove months where daily_selection_diagnostics exist for every contributing source artifact",
            "next_if_blocked": "run or reconstruct the current source replay artifacts over the missing historical months without mutating evidence stores or changing policy",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("requested_calendar_window"))
    coverage = _as_dict(report.get("calendar_coverage"))
    selected = _as_dict(report.get("selected_trade_summary"))
    reproduction = _as_dict(report.get("source_reproduction_check"))
    lines = [
        "# Regular Options Point-In-Time Candidate Generation",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_candidate_generation.py`. It reconstructs candidate-generation coverage from existing selected-trade source artifacts and their `daily_selection_diagnostics`. It is read-only and does not import quotes, mutate evidence stores, overwrite canonical multilane artifacts, change policy, or create live trades.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested window: `{window.get('window_start')}` through `{window.get('window_end')}` as of `{window.get('as_of_date')}`.",
        f"- Requested months: `{window.get('requested_calendar_month_count')}`.",
        f"- Candidate-generation covered months: `{coverage.get('calendar_months_covered_count')}`.",
        f"- Selected months with rows: `{coverage.get('selected_entry_months_with_rows_count')}`.",
        f"- Selected rows in window: `{selected.get('selected_rows_in_window')}`.",
        f"- Zero-selection months explicit: `{coverage.get('zero_selection_months_explicit')}`.",
        f"- Source reproduction: `{reproduction.get('status')}` over `{reproduction.get('checked_selected_rows')}` rows.",
        "",
        "## Source Artifacts",
        "",
        "| Playbook | Diagnostic Months | Trades | Unpriced | Entrypoints |",
        "|---|---:|---:|---:|---|",
    ]
    for artifact in _as_list(report.get("source_artifact_inventory")):
        artifact = _as_dict(artifact)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(artifact.get('playbook'))}`",
                    _cell(len(_as_list(artifact.get("diagnostic_months")))),
                    _cell(artifact.get("trade_count")),
                    _cell(artifact.get("unpriced_trade_count")),
                    _cell(", ".join(str(item) for item in _as_list(artifact.get("runner_entrypoints"))) or "missing"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Monthly Diagnostics",
            "",
            "| Month | Covered | Attempted | Selected | Stage | Reasons |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for row in _as_list(report.get("month_diagnostics")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('month'))}`",
                    _cell(row.get("candidate_generation_proven")),
                    _cell(row.get("candidate_generation_attempted")),
                    _cell(row.get("selected_trade_count")),
                    f"`{_cell(row.get('stage_status'))}`",
                    _cell(", ".join(str(item) for item in _as_list(row.get("stage_reasons")))),
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A month is covered only when every contributing selected-trade source artifact has daily candidate-generation diagnostics for that month and the source-reproduction check passes. Existing selected rows alone and quote-history depth alone do not prove zero-selection months.",
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
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
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
    parser = argparse.ArgumentParser(description="Build the read-only point-in-time candidate-generation reconstruction.")
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--as-of-date", default=DEFAULT_AS_OF_DATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        source_report_path=args.source_report,
        feature_store_report_path=args.feature_store_report,
        source_quality_policy_path=args.source_quality_policy,
        holdout_contract_path=args.holdout_contract,
        window_start=args.window_start,
        window_end=args.window_end,
        as_of_date=args.as_of_date,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
