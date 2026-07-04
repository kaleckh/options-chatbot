from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_filtered_forward_paper_shadow_tracker as tracker  # noqa: E402
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402


REPORT_ID = "regular_options_forward_evidence_bar_throughput_projection"
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT = ROOT / "data" / "contracts" / "regular-options-filtered-forward-evidence-bar-v1.json"
DEFAULT_TRACKER_LATEST = ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow" / "latest.json"
DEFAULT_PARITY_LATEST = ROOT / "data" / "forward-tracking" / "regular-options-scanner-materializer-parity-diff" / "latest.json"
DEFAULT_THROUGHPUT_LATEST = ROOT / "data" / "forward-tracking" / "regular_options_forward_candidate_throughput_audit_latest.json"
DEFAULT_FRESH_IMPORT_LATEST = ROOT / "data" / "profitability-lab" / "regular-options-fresh-window-thetadata-opra" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking" / "regular-options-forward-evidence-bar-throughput-projection"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-forward-evidence-bar-throughput-projection.md"
FREEZE_DATE = date(2026, 6, 14)
COHORT_EVAL_DATE = date(2026, 7, 28)
FOUR_MONTH_FORWARD_DATE = date(2026, 10, 14)
MAX_INPUT_AGE_DAYS = 5
MIN_OBSERVED_MARKET_DAYS = 5
APPROX_MARKET_DAYS_PER_MONTH = 21

STATUS_VOCABULARY = {
    "bar_reachable_at_current_rate",
    "bar_at_risk_needs_rate_increase",
    "bar_unreachable_without_state_change",
    "insufficient_post_freeze_observation_window",
    "blocked_missing_or_stale_inputs",
}

FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "forward_rows_are_profitability_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value in (None, "") or isinstance(value, bool):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_json", "error": str(exc), "sha256": _file_hash(path)}
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload", "sha256": _file_hash(path)}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded", "sha256": _file_hash(path)}


def _parse_datetime(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_date(value: Any) -> date | None:
    text = _norm(value)[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _market_day_count(start: date, end: date) -> int:
    if end < start:
        return 0
    count = 0
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def _input_age_days(input_generated_at: Any, reference: datetime) -> int | None:
    parsed = _parse_datetime(input_generated_at)
    if parsed is None:
        return None
    return max((reference.date() - parsed.date()).days, 0)


def _policy_hash_checks(policy_contract: dict[str, Any], policy_meta: dict[str, Any], bar_contract: dict[str, Any]) -> dict[str, Any]:
    expected_conditions = _norm(policy_contract.get("conditions_sha256"))
    computed_conditions = (
        tracker._conditions_sha256(tracker._as_list(policy_contract.get("conditions")))
        if policy_contract.get("conditions")
        else ""
    )
    source_policy = _as_dict(bar_contract.get("source_policy_contract"))
    expected_policy_sha = _norm(source_policy.get("sha256"))
    actual_policy_sha = _norm(policy_meta.get("sha256"))
    return {
        "policy_contract_loaded": policy_meta.get("status") == "loaded",
        "policy_conditions_hash_match": bool(expected_conditions and expected_conditions == computed_conditions),
        "bar_source_policy_sha_match": bool(expected_policy_sha and actual_policy_sha and expected_policy_sha == actual_policy_sha),
        "expected_conditions_sha256": expected_conditions,
        "computed_conditions_sha256": computed_conditions,
        "expected_policy_contract_sha256": expected_policy_sha,
        "actual_policy_contract_sha256": actual_policy_sha,
    }


def _horizon_projection(
    *,
    horizon_id: str,
    end_date: date,
    observed_completed_rows: int,
    required_completed_rows: int,
    observation_market_days: int,
) -> dict[str, Any]:
    total_market_days = _market_day_count(FREEZE_DATE, end_date)
    remaining_market_days = max(total_market_days - observation_market_days, 0)
    rows_remaining = max(required_completed_rows - observed_completed_rows, 0)
    current_rate = round(observed_completed_rows / observation_market_days, 6) if observation_market_days > 0 else 0.0
    projected_rows = round(current_rate * total_market_days, 3)
    required_rate = round(rows_remaining / remaining_market_days, 6) if remaining_market_days > 0 else None
    reachable_at_current_rate = projected_rows >= required_completed_rows
    return {
        "horizon_id": horizon_id,
        "start_date": FREEZE_DATE.isoformat(),
        "end_date": end_date.isoformat(),
        "total_market_days": total_market_days,
        "observed_market_days": observation_market_days,
        "remaining_market_days": remaining_market_days,
        "required_completed_rows": required_completed_rows,
        "observed_completed_rows": observed_completed_rows,
        "rows_remaining": rows_remaining,
        "current_completed_rows_per_market_day": current_rate,
        "required_rows_per_market_day": required_rate,
        "projected_completed_rows_at_current_rate": projected_rows,
        "reachable_at_current_rate": reachable_at_current_rate,
    }


def _report_status(
    *,
    blockers: list[str],
    observation_market_days: int,
    horizon_projections: list[dict[str, Any]],
    observed_matched_rows: int,
    materializer_filter_matches: int,
) -> str:
    if blockers:
        return "blocked_missing_or_stale_inputs"
    if observation_market_days < MIN_OBSERVED_MARKET_DAYS:
        return "insufficient_post_freeze_observation_window"
    if all(bool(item.get("reachable_at_current_rate")) for item in horizon_projections):
        return "bar_reachable_at_current_rate"
    if observed_matched_rows == 0 and materializer_filter_matches == 0:
        return "bar_unreachable_without_state_change"
    return "bar_at_risk_needs_rate_increase"


def _staleness_blockers(inputs: dict[str, dict[str, Any]], reference: datetime) -> list[str]:
    blockers: list[str] = []
    for name, payload in sorted(inputs.items()):
        meta = _as_dict(payload.get("meta"))
        data = _as_dict(payload.get("data"))
        if meta.get("status") != "loaded":
            blockers.append(f"{name}_not_loaded")
            continue
        age_days = _input_age_days(data.get("generated_at_utc"), reference)
        meta["age_days"] = age_days
        if age_days is None:
            blockers.append(f"{name}_missing_generated_at_utc")
        elif age_days > MAX_INPUT_AGE_DAYS:
            blockers.append(f"{name}_stale_generated_at_utc")
    return blockers


def _spy_divergence_readback(parity: dict[str, Any]) -> dict[str, Any]:
    rows = [
        _as_dict(row)
        for row in _as_list(parity.get("divergence_rows"))
        if _as_dict(row).get("symbol") == "SPY" and _as_dict(row).get("date") == "2026-06-16"
    ]
    return {
        "status": "spy_2026_06_16_divergence_found" if rows else "spy_2026_06_16_divergence_not_found",
        "rows": rows,
        "session_time_distribution_et": _as_dict(parity.get("scheduled_scan_coverage")).get("session_times_et") or [],
        "materializer_entry_window_et": _as_dict(parity.get("boundary")).get("materializer_entry_window_et"),
        "read_only": True,
    }


def build_report(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    forward_evidence_bar_contract_path: Path = DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    tracker_latest_path: Path = DEFAULT_TRACKER_LATEST,
    parity_latest_path: Path = DEFAULT_PARITY_LATEST,
    throughput_latest_path: Path = DEFAULT_THROUGHPUT_LATEST,
    fresh_import_latest_path: Path = DEFAULT_FRESH_IMPORT_LATEST,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    reference = _parse_datetime(generated_at) or datetime.now(UTC)
    policy_contract, policy_meta = _load_json(policy_contract_path)
    bar_contract, bar_meta = _load_json(forward_evidence_bar_contract_path)
    tracker_latest, tracker_meta = _load_json(tracker_latest_path)
    parity_latest, parity_meta = _load_json(parity_latest_path)
    throughput_latest, throughput_meta = _load_json(throughput_latest_path)
    fresh_import_latest, fresh_meta = _load_json(fresh_import_latest_path)

    source_inputs = {
        "tracker_latest": {"data": tracker_latest, "meta": tracker_meta},
        "parity_latest": {"data": parity_latest, "meta": parity_meta},
        "throughput_latest": {"data": throughput_latest, "meta": throughput_meta},
        "fresh_import_latest": {"data": fresh_import_latest, "meta": fresh_meta},
    }
    blockers = _staleness_blockers(source_inputs, reference)

    hash_checks = _policy_hash_checks(policy_contract, policy_meta, bar_contract)
    if bar_meta.get("status") != "loaded":
        blockers.append("forward_evidence_bar_contract_not_loaded")
    if policy_meta.get("status") != "loaded":
        blockers.append("frozen_policy_contract_not_loaded")
    if not hash_checks["policy_conditions_hash_match"]:
        blockers.append("frozen_policy_conditions_hash_mismatch")
    if not hash_checks["bar_source_policy_sha_match"]:
        blockers.append("bar_source_policy_contract_hash_mismatch")

    bar_requirements = _as_dict(bar_contract.get("requirements"))
    required_completed_rows = _safe_int(bar_requirements.get("min_completed_forward_paper_shadow_rows")) or 30
    tracker_forward = _as_dict(tracker_latest.get("forward_tracking"))
    tracker_bar = _as_dict(tracker_latest.get("forward_evidence_bar"))
    parity_coverage = _as_dict(parity_latest.get("materializer_coverage"))
    parity_summary = _as_dict(parity_latest.get("summary"))
    throughput_stage = _as_dict(throughput_latest.get("scheduled_phase2_drop_stage_summary"))
    throughput_near_miss = _as_dict(throughput_latest.get("scheduled_phase2_near_miss_summary"))
    tracker_disclosure = _as_dict(tracker_latest.get("parity_disclosure"))

    parity_window = _as_dict(parity_latest.get("window"))
    observation_market_days = _safe_int(parity_window.get("market_day_count"))
    if observation_market_days == 0:
        latest_materializer_date = _parse_date(parity_coverage.get("latest_materializer_date"))
        if latest_materializer_date:
            observation_market_days = _market_day_count(FREEZE_DATE, latest_materializer_date)

    observed_matched_rows = _safe_int(tracker_forward.get("matched_candidate_count"))
    observed_completed_rows = _safe_int(tracker_forward.get("completed_candidate_count") or tracker_bar.get("completed_forward_rows"))
    materializer_filter_matches = _safe_int(
        parity_coverage.get("filter_matched_selected_rows_in_window")
        or parity_summary.get("filtered_materializer_candidate_rows")
    )
    historical_materializer_rows = _safe_int(tracker_disclosure.get("historical_filtered_materializer_rows"))
    historical_materializer_months = _safe_int(tracker_disclosure.get("historical_filtered_materializer_months"))
    historical_upper_bound_rate = (
        round(historical_materializer_rows / (historical_materializer_months * APPROX_MARKET_DAYS_PER_MONTH), 6)
        if historical_materializer_rows and historical_materializer_months
        else None
    )

    horizon_projections = [
        _horizon_projection(
            horizon_id="cohort_eval_2026_07_28",
            end_date=COHORT_EVAL_DATE,
            observed_completed_rows=observed_completed_rows,
            required_completed_rows=required_completed_rows,
            observation_market_days=observation_market_days,
        ),
        _horizon_projection(
            horizon_id="freeze_anchored_four_month_forward_2026_10_14",
            end_date=FOUR_MONTH_FORWARD_DATE,
            observed_completed_rows=observed_completed_rows,
            required_completed_rows=required_completed_rows,
            observation_market_days=observation_market_days,
        ),
    ]
    status = _report_status(
        blockers=blockers,
        observation_market_days=observation_market_days,
        horizon_projections=horizon_projections,
        observed_matched_rows=observed_matched_rows,
        materializer_filter_matches=materializer_filter_matches,
    )
    assert status in STATUS_VOCABULARY

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "status_vocabulary": sorted(STATUS_VOCABULARY),
        "read_only": True,
        "scope": "regular_options_filtered_forward_evidence_bar_throughput_projection",
        "freeze_date": FREEZE_DATE.isoformat(),
        "cohort_eval_date": COHORT_EVAL_DATE.isoformat(),
        "four_month_forward_audit_end_date": FOUR_MONTH_FORWARD_DATE.isoformat(),
        "inputs": {
            "policy_contract": policy_meta,
            "forward_evidence_bar_contract": bar_meta,
            "tracker_latest": tracker_meta,
            "parity_latest": parity_meta,
            "throughput_latest": throughput_meta,
            "fresh_import_latest": fresh_meta,
        },
        "policy_hash_checks": hash_checks,
        "blockers": blockers,
        "evidence_bar_requirements": {
            "required_completed_forward_rows": required_completed_rows,
            "required_ticker_week_clusters": _safe_int(bar_requirements.get("min_ticker_week_clusters")),
            "required_calendar_months": _safe_int(bar_requirements.get("min_calendar_months_with_rows")),
            "required_percent_cluster_pf_lb_5pct": _safe_float(bar_requirements.get("min_percent_cluster_pf_lb_5pct")),
            "required_usd_cluster_pf_lb_5pct": _safe_float(bar_requirements.get("min_usd_cluster_pf_lb_5pct")),
        },
        "horizon_projections": horizon_projections,
        "denominators": {
            "tracker_forward_rows": {
                "denominator_id": "filtered_forward_paper_shadow_tracker",
                "observed_matched_rows": observed_matched_rows,
                "observed_completed_rows": observed_completed_rows,
                "source_status": tracker_latest.get("status"),
                "source_generated_at_utc": tracker_latest.get("generated_at_utc"),
            },
            "materializer_in_window_rows": {
                "denominator_id": "scanner_materializer_parity_diff_materializer_window",
                "materializer_rows_in_window": _safe_int(parity_coverage.get("row_count_in_window")),
                "materializer_filter_matched_selected_rows": materializer_filter_matches,
                "historical_materializer_upper_bound_rows_per_market_day": historical_upper_bound_rate,
                "historical_materializer_upper_bound_basis": "historical_filtered_materializer_rows / historical_filtered_materializer_months / 21",
                "source_status": parity_latest.get("status"),
                "source_generated_at_utc": parity_latest.get("generated_at_utc"),
            },
            "scheduled_scan_drop_rows": {
                "denominator_id": "forward_candidate_throughput_audit_scheduled_scan_drops",
                "scheduled_phase2_drop_count_total": _safe_int(throughput_latest.get("scheduled_phase2_drop_count_total")),
                "scheduled_phase2_scan_drop_reason_count_total": _safe_int(throughput_latest.get("scheduled_phase2_scan_drop_reason_count_total")),
                "top_drop_stages": _as_list(throughput_stage.get("top_drop_stages")),
                "near_miss_status": throughput_near_miss.get("status"),
                "source_status": throughput_latest.get("status"),
                "source_generated_at_utc": throughput_latest.get("generated_at_utc"),
            },
        },
        "dominant_starvation_stage": {
            "status": "forward_candidate_starvation" if materializer_filter_matches == 0 and observed_matched_rows == 0 else "forward_throughput_below_bar_rate",
            "reason": "No filter-matched materializer rows and no tracker matches in the observed post-freeze window."
            if materializer_filter_matches == 0 and observed_matched_rows == 0
            else "Some rows exist, but current completed-row pace does not satisfy every horizon.",
        },
        "spy_2026_06_16_divergence_readback": _spy_divergence_readback(parity_latest),
        "proof_boundary": (
            "This projection is not profitability evidence and is not a promotion input. "
            "Only fresh post-freeze executable exact rows evaluated by the frozen evidence-bar evaluator can support "
            "a bar_met_pending_operator_review outcome, and that outcome authorizes nothing."
        ),
        "approval_authority": False,
        "prohibited_actions": [
            "do_not_change_scanner_policy_from_projection",
            "do_not_change_filter_or_threshold_from_projection",
            "do_not_change_proof_bars_from_projection",
            "do_not_append_cohort_rows_from_projection",
            "do_not_import_quotes_from_projection",
            "do_not_mutate_evidence_stores_from_projection",
            "do_not_enable_live_validation_from_projection",
            "do_not_enable_auto_track_from_projection",
            "do_not_submit_broker_orders_from_projection",
            "do_not_consume_protected_holdout_from_projection",
            "do_not_treat_projection_or_historical_rows_as_forward_proof",
        ],
        **FALSE_FLAGS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    denominators = _as_dict(report.get("denominators"))
    tracker_rows = _as_dict(denominators.get("tracker_forward_rows"))
    materializer_rows = _as_dict(denominators.get("materializer_in_window_rows"))
    scheduled_rows = _as_dict(denominators.get("scheduled_scan_drop_rows"))
    lines = [
        "# Regular Options Forward Evidence-Bar Throughput Projection",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Freeze date: `{report.get('freeze_date')}`.",
        f"- Cohort eval date: `{report.get('cohort_eval_date')}`.",
        f"- Four-month forward audit end: `{report.get('four_month_forward_audit_end_date')}`.",
        f"- Blockers: `{json.dumps(report.get('blockers') or [], sort_keys=True)}`.",
        "",
        "## Horizon Projections",
        "",
        "| Horizon | Market Days | Remaining | Completed | Required Rate | Current Rate | Projected Rows | Reachable |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in _as_list(report.get("horizon_projections")):
        row = _as_dict(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('horizon_id')}`",
                    str(row.get("total_market_days")),
                    str(row.get("remaining_market_days")),
                    f"{row.get('observed_completed_rows')} / {row.get('required_completed_rows')}",
                    str(row.get("required_rows_per_market_day")),
                    str(row.get("current_completed_rows_per_market_day")),
                    str(row.get("projected_completed_rows_at_current_rate")),
                    str(bool(row.get("reachable_at_current_rate"))).lower(),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Separate Denominators",
            "",
            f"- Tracker denominator `{tracker_rows.get('denominator_id')}`: matched `{tracker_rows.get('observed_matched_rows')}`, completed `{tracker_rows.get('observed_completed_rows')}`.",
            f"- Materializer denominator `{materializer_rows.get('denominator_id')}`: in-window rows `{materializer_rows.get('materializer_rows_in_window')}`, filter-matched selected `{materializer_rows.get('materializer_filter_matched_selected_rows')}`, historical upper-bound rows/market-day `{materializer_rows.get('historical_materializer_upper_bound_rows_per_market_day')}`.",
            f"- Scheduled-scan denominator `{scheduled_rows.get('denominator_id')}`: drops `{scheduled_rows.get('scheduled_phase2_drop_count_total')}`, symbol drop reasons `{scheduled_rows.get('scheduled_phase2_scan_drop_reason_count_total')}`, near-miss status `{scheduled_rows.get('near_miss_status')}`.",
            "",
            "## Dominant Starvation Stage",
            "",
            f"- Status: `{_as_dict(report.get('dominant_starvation_stage')).get('status')}`.",
            f"- Reason: {_as_dict(report.get('dominant_starvation_stage')).get('reason')}",
            "",
            "## Boundary",
            "",
            str(report.get("proof_boundary") or ""),
            "",
            "This report is read-only. It does not import quotes, mutate evidence stores, append cohorts, change scanner policy, change filters, lower proof bars, enable live validation, enable auto-track, submit broker orders, consume protected holdout, or promote a lane.",
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
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
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


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project filtered forward evidence-bar throughput from existing read-only artifacts.")
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--forward-evidence-bar-contract", type=Path, default=DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT)
    parser.add_argument("--tracker-latest", type=Path, default=DEFAULT_TRACKER_LATEST)
    parser.add_argument("--parity-latest", type=Path, default=DEFAULT_PARITY_LATEST)
    parser.add_argument("--throughput-latest", type=Path, default=DEFAULT_THROUGHPUT_LATEST)
    parser.add_argument("--fresh-import-latest", type=Path, default=DEFAULT_FRESH_IMPORT_LATEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        policy_contract_path=args.policy_contract,
        forward_evidence_bar_contract_path=args.forward_evidence_bar_contract,
        tracker_latest_path=args.tracker_latest,
        parity_latest_path=args.parity_latest,
        throughput_latest_path=args.throughput_latest,
        fresh_import_latest_path=args.fresh_import_latest,
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
