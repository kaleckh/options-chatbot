from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _accepted_rows,
    _as_list,
    _filter_rows,
)
from scripts import build_regular_options_filtered_forward_paper_shadow_tracker as tracker  # noqa: E402
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402


REPORT_ID = "regular_options_materializer_match_rate_stationarity"
DEFAULT_HISTORICAL_ENGINE_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-frozen-candidate-generation-engine"
)
DEFAULT_HISTORICAL_ENGINE_LATEST = DEFAULT_HISTORICAL_ENGINE_DIR / "latest.json"
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_TRACKER_LATEST = ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow" / "latest.json"
DEFAULT_PARITY_LATEST = ROOT / "data" / "forward-tracking" / "regular-options-scanner-materializer-parity-diff" / "latest.json"
DEFAULT_THROUGHPUT_LATEST = ROOT / "data" / "forward-tracking" / "regular_options_forward_candidate_throughput_audit_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-materializer-match-rate-stationarity"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-materializer-match-rate-stationarity.md"
DEFAULT_HASH_INVARIANCE_PATHS = (
    ROOT / "data" / "options-validation" / "options_history.db",
    ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow" / "matched_rows.jsonl",
    ROOT / "data" / "forward-tracking" / "regular-options-filtered-forward-paper-shadow" / "candidate_rows.jsonl",
)
MAX_INPUT_AGE_DAYS = 5
ZERO_RUN_REGIME_BREAK_MAX_FRACTION = 0.05
ZERO_RUN_CONFIRMATION_MAX_FRACTION = 0.01
ZERO_RUN_TRIGGER_MIN_WINDOW_DAYS = 13
ZERO_RUN_TRIGGER_MAX_WINDOW_DAYS = 90
STATUS_VOCABULARY = {
    "post_freeze_zero_within_historical_variation",
    "post_freeze_zero_indicates_regime_break",
    "insufficient_history_for_stationarity_verdict",
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
    "cohort_append_performed": False,
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


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "" or isinstance(value, bool):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    text = str(value or "").strip()
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
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _input_age_days(input_generated_at: Any, reference: datetime) -> int | None:
    parsed = _parse_datetime(input_generated_at)
    if parsed is None:
        return None
    return max((reference.date() - parsed.date()).days, 0)


def _month_key(row: dict[str, Any]) -> str:
    return str(row.get("month") or row.get("entry_date") or row.get("candidate_generation_date") or row.get("date") or "")[:7]


def _date_key(row: dict[str, Any]) -> str:
    return str(row.get("entry_date") or row.get("candidate_generation_date") or row.get("date") or "")[:10]


def _prior20(row: dict[str, Any]) -> float | None:
    signal = _as_dict(row.get("signal_evidence"))
    return _safe_float(signal.get("prior_20_trading_day_return_pct") if signal else row.get("prior_20_trading_day_return_pct"))


def _policy_hash_checks(policy: dict[str, Any], policy_meta: dict[str, Any]) -> dict[str, Any]:
    expected = str(policy.get("conditions_sha256") or "")
    computed = tracker._conditions_sha256(tracker._as_list(policy.get("conditions"))) if policy.get("conditions") else ""
    return {
        "policy_contract_loaded": policy_meta.get("status") == "loaded",
        "policy_conditions_hash_match": bool(expected and expected == computed),
        "expected_conditions_sha256": expected,
        "computed_conditions_sha256": computed,
        "actual_policy_contract_sha256": policy_meta.get("sha256"),
    }


def _historical_engine_candidates(engine_dir: Path, latest_path: Path) -> list[Path]:
    candidates = [latest_path] if latest_path.exists() else []
    if engine_dir.exists():
        candidates.extend(sorted(engine_dir.glob("regular_options_13_symbol_frozen_candidate_generation_engine_*.json"), key=lambda p: p.stat().st_mtime, reverse=True))
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _select_historical_engine_source(
    engine_dir: Path,
    latest_path: Path,
    *,
    reference: datetime,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    inspected: list[dict[str, Any]] = []
    for path in _historical_engine_candidates(engine_dir, latest_path):
        payload, meta = _load_json(path)
        selected = _as_list(payload.get("selected_candidates"))
        age_days = _input_age_days(payload.get("generated_at_utc"), reference)
        item = {
            "path": _rel(path),
            "status": payload.get("status"),
            "generated_at_utc": payload.get("generated_at_utc"),
            "age_days": age_days,
            "selected_candidate_row_count": payload.get("selected_candidate_row_count"),
            "embedded_selected_candidates": len(selected),
        }
        inspected.append(item)
        if (
            meta.get("status") == "loaded"
            and payload.get("status") == "frozen_13_symbol_candidate_generation_engine_ready"
            and selected
            and age_days is not None
            and age_days <= MAX_INPUT_AGE_DAYS
        ):
            meta.update(
                {
                    "source_mode": "latest_ready_historical_engine_snapshot"
                    if path.resolve() != latest_path.resolve()
                    else "latest_historical_engine",
                    "generated_at_utc": payload.get("generated_at_utc"),
                    "age_days": age_days,
                }
            )
            return payload, meta, inspected
    return {}, {"path": _rel(latest_path), "exists": latest_path.exists(), "status": "no_ready_historical_engine_snapshot"}, inspected


def _monthly_counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(_month_key(row) for row in rows if _month_key(row))
    return {key: counter[key] for key in sorted(counter)}


def _sliding_zero_run(match_dates: set[str], all_dates: Sequence[str], window_days: int) -> dict[str, Any]:
    dates = [day for day in sorted(set(all_dates)) if day]
    if window_days <= 0 or len(dates) < window_days:
        return {
            "status": "insufficient_history",
            "observed_window_market_days": window_days,
            "historical_market_day_count": len(dates),
            "window_count": 0,
            "zero_match_window_count": 0,
            "zero_match_window_fraction": None,
        }
    zero_count = 0
    min_matches: int | None = None
    max_matches = 0
    for index in range(0, len(dates) - window_days + 1):
        window = dates[index : index + window_days]
        matches = sum(1 for day in window if day in match_dates)
        if matches == 0:
            zero_count += 1
        min_matches = matches if min_matches is None else min(min_matches, matches)
        max_matches = max(max_matches, matches)
    window_count = len(dates) - window_days + 1
    return {
        "status": "ready",
        "observed_window_market_days": window_days,
        "historical_market_day_count": len(dates),
        "window_count": window_count,
        "zero_match_window_count": zero_count,
        "zero_match_window_fraction": round(zero_count / window_count, 6) if window_count else None,
        "min_matches_in_any_window": min_matches,
        "max_matches_in_any_window": max_matches,
    }


def _market_days_after(start_date: date, days_needed: int) -> date:
    if days_needed <= 0:
        return start_date
    remaining = days_needed
    current = start_date
    while remaining > 0:
        current += timedelta(days=1)
        if is_us_equity_market_day(current):
            remaining -= 1
    return current


def _zero_run_trigger_schedule(
    *,
    match_dates: set[str],
    all_dates: Sequence[str],
    observed_market_days: int,
    observed_filter_matches: int,
    reference_date: date,
    min_window_days: int = ZERO_RUN_TRIGGER_MIN_WINDOW_DAYS,
    max_window_days: int = ZERO_RUN_TRIGGER_MAX_WINDOW_DAYS,
) -> dict[str, Any]:
    if observed_filter_matches > 0:
        return {
            "status": "voided_by_post_freeze_match",
            "reason": "A parity materializer post-freeze filter match ends the zero-run schedule; rerun stationarity from the new matched observation.",
            "observed_window_market_days": observed_market_days,
            "observed_filter_match_source": "parity_materializer_filter_matched_selected_rows_in_window",
            "reference_date": reference_date.isoformat(),
            "voids_on_first_post_freeze_filter_match": True,
            "windows": [],
            "first_regime_break_trigger": None,
            "first_confirmation_trigger": None,
            "monotonicity_check": {"status": "not_applicable", "violations": []},
        }
    if observed_market_days <= 0:
        return {
            "status": "insufficient_observed_zero_run",
            "reason": "Observed zero-run market-day count is unavailable.",
            "observed_window_market_days": observed_market_days,
            "observed_filter_match_source": "parity_materializer_filter_matched_selected_rows_in_window",
            "reference_date": reference_date.isoformat(),
            "voids_on_first_post_freeze_filter_match": True,
            "windows": [],
            "first_regime_break_trigger": None,
            "first_confirmation_trigger": None,
            "monotonicity_check": {"status": "not_applicable", "violations": []},
        }

    windows: list[dict[str, Any]] = []
    previous_fraction: float | None = None
    violations: list[dict[str, Any]] = []
    first_regime_break: dict[str, Any] | None = None
    first_confirmation: dict[str, Any] | None = None
    for window_days in range(min_window_days, max_window_days + 1):
        zero_run = _sliding_zero_run(match_dates, all_dates, window_days)
        fraction = zero_run.get("zero_match_window_fraction")
        trigger_date = _market_days_after(reference_date, max(window_days - observed_market_days, 0))
        row = {
            "window_market_days": window_days,
            "status": zero_run.get("status"),
            "historical_market_day_count": zero_run.get("historical_market_day_count"),
            "window_count": zero_run.get("window_count"),
            "zero_match_window_count": zero_run.get("zero_match_window_count"),
            "zero_match_window_fraction": fraction,
            "projected_calendar_date_if_zero_run_continues": trigger_date.isoformat(),
            "already_reached": window_days <= observed_market_days,
            "regime_break_threshold": ZERO_RUN_REGIME_BREAK_MAX_FRACTION,
            "confirmation_threshold": ZERO_RUN_CONFIRMATION_MAX_FRACTION,
        }
        if fraction is not None:
            parsed_fraction = float(fraction)
            if previous_fraction is not None and parsed_fraction > previous_fraction:
                violations.append(
                    {
                        "window_market_days": window_days,
                        "previous_fraction": previous_fraction,
                        "current_fraction": parsed_fraction,
                    }
                )
            previous_fraction = parsed_fraction
            if first_regime_break is None and parsed_fraction <= ZERO_RUN_REGIME_BREAK_MAX_FRACTION:
                first_regime_break = dict(row)
            if first_confirmation is None and parsed_fraction <= ZERO_RUN_CONFIRMATION_MAX_FRACTION:
                first_confirmation = dict(row)
        windows.append(row)
    ready_windows = [row for row in windows if row.get("status") == "ready"]
    return {
        "status": "ready" if ready_windows else "insufficient_history",
        "observed_window_market_days": observed_market_days,
        "observed_filter_match_source": "parity_materializer_filter_matched_selected_rows_in_window",
        "reference_date": reference_date.isoformat(),
        "window_range_market_days": [min_window_days, max_window_days],
        "voids_on_first_post_freeze_filter_match": True,
        "first_regime_break_trigger": first_regime_break,
        "first_confirmation_trigger": first_confirmation,
        "monotonicity_check": {
            "status": "passed" if not violations else "failed",
            "expected": "historical_zero_match_window_fraction_should_not_increase_as_window_days_grow",
            "violations": violations,
        },
        "windows": windows,
    }


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 6)


def _threshold_condition_field(condition: dict[str, Any]) -> bool:
    return condition.get("field") == "signal_evidence.prior_20_trading_day_return_pct"


def _non_threshold_conditions(conditions: Sequence[Any]) -> list[dict[str, Any]]:
    return [_as_dict(condition) for condition in conditions if not _threshold_condition_field(_as_dict(condition))]


def _threshold_distance_summary(rows: Sequence[dict[str, Any]], conditions: Sequence[Any], threshold: float) -> dict[str, Any]:
    eligible_rows = _filter_rows(rows, {"conditions": _non_threshold_conditions(conditions)})
    distances: list[float] = []
    nearest_rows: list[dict[str, Any]] = []
    for row in eligible_rows:
        prior = _prior20(row)
        if prior is None:
            continue
        distance = round(threshold - prior, 6)
        if distance <= 0:
            continue
        distances.append(distance)
        nearest_rows.append(
            {
                "date": _date_key(row),
                "month": _month_key(row),
                "ticker": str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "").upper(),
                "lane_id": row.get("lane_id") or row.get("lane"),
                "distance_to_threshold": distance,
                "prior_20_trading_day_return_pct": round(prior, 6),
            }
        )
    nearest_rows.sort(key=lambda row: (row["distance_to_threshold"], row["date"], row["ticker"]))
    return {
        "distance_basis": "frozen_threshold_minus_prior_20_return_for_historical_accepted_rows_below_threshold",
        "threshold": threshold,
        "non_threshold_filter_conditions": _non_threshold_conditions(conditions),
        "non_threshold_filter_eligible_row_count": len(eligible_rows),
        "row_count_with_distance": len(distances),
        "min_distance": min(distances) if distances else None,
        "p25_distance": _percentile(distances, 0.25),
        "median_distance": _percentile(distances, 0.5),
        "p75_distance": _percentile(distances, 0.75),
        "nearest_rows": nearest_rows[:20],
        "counterfactual_match_counts_emitted": False,
        "counterfactual_economics_emitted": False,
    }


def _throughput_near_miss_summary(throughput: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(throughput.get("scheduled_phase2_near_miss_summary"))
    ranked = [item for item in _as_list(summary.get("ranked_symbol_near_misses")) if isinstance(item, dict)]
    distances = [
        float(item["distance_to_pass"])
        for item in ranked
        if item.get("distance_to_pass") is not None
    ]
    return {
        "source_status": throughput.get("status"),
        "near_miss_status": summary.get("status"),
        "distance_available_count": len(distances),
        "min_distance_to_pass": min(distances) if distances else None,
        "median_distance_to_pass": _percentile(distances, 0.5),
        "nearest_rows": [
            {
                "selection_date": item.get("selection_date"),
                "symbol": item.get("symbol"),
                "playbook": item.get("playbook"),
                "drop_key": item.get("drop_key"),
                "reason": item.get("reason"),
                "distance_to_pass": item.get("distance_to_pass"),
                "near_miss_rank_basis": item.get("near_miss_rank_basis"),
                "non_promotable": item.get("non_promotable"),
            }
            for item in ranked[:20]
        ],
    }


def _session_overlap(parity: dict[str, Any]) -> dict[str, Any]:
    times = [str(item) for item in _as_list(_as_dict(parity.get("scheduled_scan_coverage")).get("session_times_et")) if str(item)]
    inside = [item for item in times if "10:10:00" <= item <= "10:25:59"]
    rows = [
        _as_dict(row)
        for row in _as_list(parity.get("divergence_rows"))
        if _as_dict(row).get("symbol") == "SPY" and _as_dict(row).get("date") == "2026-06-16"
    ]
    return {
        "materializer_entry_window_et": _as_dict(parity.get("boundary")).get("materializer_entry_window_et"),
        "distinct_scheduled_session_time_count": len(times),
        "distinct_session_times_inside_entry_window": len(inside),
        "distinct_session_time_overlap_fraction": round(len(inside) / len(times), 6) if times else None,
        "session_times_inside_entry_window": inside[:50],
        "spy_2026_06_16_divergence_rows": rows,
    }


def _hash_snapshot(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.append(
            {
                "path": _rel(path),
                "exists": path.exists(),
                "sha256": _file_hash(path),
                "length": path.stat().st_size if path.exists() else 0,
            }
        )
    return rows


def _record_hash_invariance(paths: Sequence[Path], before: Sequence[dict[str, Any]]) -> dict[str, Any]:
    after = _hash_snapshot(paths)
    before_by_path = {row["path"]: row for row in before}
    checks = []
    for row in after:
        before_row = before_by_path.get(row["path"], {})
        checks.append(
            {
                "path": row["path"],
                "before_sha256": before_row.get("sha256"),
                "after_sha256": row.get("sha256"),
                "unchanged": before_row.get("sha256") == row.get("sha256"),
                "length": row.get("length"),
            }
        )
    return {
        "recorded": True,
        "all_unchanged": all(bool(row["unchanged"]) for row in checks),
        "checks": checks,
    }


def build_report(
    *,
    historical_engine_dir: Path = DEFAULT_HISTORICAL_ENGINE_DIR,
    historical_engine_latest_path: Path = DEFAULT_HISTORICAL_ENGINE_LATEST,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    tracker_latest_path: Path = DEFAULT_TRACKER_LATEST,
    parity_latest_path: Path = DEFAULT_PARITY_LATEST,
    throughput_latest_path: Path = DEFAULT_THROUGHPUT_LATEST,
    generated_at_utc: str | None = None,
    hash_invariance_before: Sequence[dict[str, Any]] | None = None,
    hash_invariance_paths: Sequence[Path] = DEFAULT_HASH_INVARIANCE_PATHS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    reference = _parse_datetime(generated_at) or datetime.now(UTC)
    reference_date = reference.date()
    policy, policy_meta = _load_json(policy_contract_path)
    tracker_latest, tracker_meta = _load_json(tracker_latest_path)
    parity_latest, parity_meta = _load_json(parity_latest_path)
    throughput_latest, throughput_meta = _load_json(throughput_latest_path)
    engine, engine_meta, inspected_engine_sources = _select_historical_engine_source(
        historical_engine_dir,
        historical_engine_latest_path,
        reference=reference,
    )
    hash_checks = _policy_hash_checks(policy, policy_meta)
    blockers: list[str] = []
    for name, payload, meta in (
        ("tracker_latest", tracker_latest, tracker_meta),
        ("parity_latest", parity_latest, parity_meta),
        ("throughput_latest", throughput_latest, throughput_meta),
    ):
        if meta.get("status") != "loaded":
            blockers.append(f"{name}_not_loaded")
            continue
        age_days = _input_age_days(payload.get("generated_at_utc"), reference)
        meta["age_days"] = age_days
        if age_days is None:
            blockers.append(f"{name}_missing_generated_at_utc")
        elif age_days > MAX_INPUT_AGE_DAYS:
            blockers.append(f"{name}_stale_generated_at_utc")
    if engine_meta.get("status") != "loaded":
        blockers.append("historical_engine_source_not_loaded")
    if policy_meta.get("status") != "loaded":
        blockers.append("policy_contract_not_loaded")
    if not hash_checks["policy_conditions_hash_match"]:
        blockers.append("policy_conditions_hash_mismatch")

    conditions = _as_list(policy.get("conditions"))
    threshold = None
    for condition in conditions:
        condition = _as_dict(condition)
        if condition.get("field") == "signal_evidence.prior_20_trading_day_return_pct":
            threshold = _safe_float(condition.get("value"))
            break
    if threshold is None:
        blockers.append("frozen_prior20_threshold_missing")
        threshold = 0.0

    selected_rows = [_as_dict(row) for row in _as_list(engine.get("selected_candidates"))]
    accepted_rows = _accepted_rows(selected_rows)
    filtered_rows = _filter_rows(accepted_rows, {"conditions": conditions}) if conditions else []
    tracker_disclosure = _as_dict(tracker_latest.get("parity_disclosure"))
    disclosed_rows_raw = tracker_disclosure.get("historical_filtered_materializer_rows")
    disclosed_months_raw = tracker_disclosure.get("historical_filtered_materializer_months")
    disclosed_rows_present = disclosed_rows_raw is not None and disclosed_rows_raw != ""
    disclosed_months_present = disclosed_months_raw is not None and disclosed_months_raw != ""
    disclosed_rows = _safe_int(disclosed_rows_raw)
    disclosed_months = _safe_int(disclosed_months_raw)
    if not disclosed_rows_present:
        blockers.append("historical_filtered_materializer_row_count_missing")
    elif disclosed_rows != len(filtered_rows):
        blockers.append("historical_filtered_materializer_row_count_mismatch")
    if not disclosed_months_present:
        blockers.append("historical_filtered_materializer_month_count_missing")

    parity_coverage = _as_dict(parity_latest.get("materializer_coverage"))
    parity_summary = _as_dict(parity_latest.get("summary"))
    observed_filter_matches = _safe_int(
        parity_coverage.get("filter_matched_selected_rows_in_window")
        if parity_coverage.get("filter_matched_selected_rows_in_window") is not None
        else parity_summary.get("filtered_materializer_candidate_rows")
    )
    observed_market_days = _safe_int(_as_dict(parity_latest.get("window")).get("market_day_count"))

    monthly_match_counts = _monthly_counts(filtered_rows)
    monthly_accepted_counts = _monthly_counts(accepted_rows)
    monthly_table = []
    for month in sorted(set(monthly_accepted_counts) | set(monthly_match_counts)):
        accepted_count = monthly_accepted_counts.get(month, 0)
        match_count = monthly_match_counts.get(month, 0)
        monthly_table.append(
            {
                "month": month,
                "accepted_materializer_rows": accepted_count,
                "frozen_filter_match_rows": match_count,
                "match_rate": round(match_count / accepted_count, 6) if accepted_count else None,
            }
        )
    all_dates = [_date_key(row) for row in _as_list(engine.get("daily_candidate_generation")) if _date_key(_as_dict(row))]
    if not all_dates:
        all_dates = [_date_key(row) for row in accepted_rows if _date_key(row)]
    match_dates = {_date_key(row) for row in filtered_rows if _date_key(row)}
    zero_run = _sliding_zero_run(match_dates, all_dates, observed_market_days)
    zero_run_schedule = _zero_run_trigger_schedule(
        match_dates=match_dates,
        all_dates=all_dates,
        observed_market_days=observed_market_days,
        observed_filter_matches=observed_filter_matches,
        reference_date=reference_date,
    )
    if _as_dict(zero_run_schedule.get("monotonicity_check")).get("status") == "failed":
        blockers.append("zero_run_trigger_schedule_monotonicity_violation")

    if blockers:
        status = "blocked_missing_or_stale_inputs"
    elif zero_run["status"] != "ready" or disclosed_months <= 0:
        status = "insufficient_history_for_stationarity_verdict"
    elif observed_filter_matches == 0 and (zero_run.get("zero_match_window_fraction") or 0.0) <= ZERO_RUN_REGIME_BREAK_MAX_FRACTION:
        status = "post_freeze_zero_indicates_regime_break"
    else:
        status = "post_freeze_zero_within_historical_variation"
    assert status in STATUS_VOCABULARY

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "status_vocabulary": sorted(STATUS_VOCABULARY),
        "scope": "read_only_materializer_match_rate_stationarity",
        "read_only": True,
        "research_only": True,
        "inputs": {
            "historical_engine": engine_meta,
            "inspected_historical_engine_sources": inspected_engine_sources[:12],
            "policy_contract": policy_meta,
            "tracker_latest": tracker_meta,
            "parity_latest": parity_meta,
            "throughput_latest": throughput_meta,
        },
        "policy_hash_checks": hash_checks,
        "blockers": blockers,
        "frozen_filter": {
            "conditions_sha256": policy.get("conditions_sha256"),
            "conditions": conditions,
            "prior_20_trading_day_return_pct_threshold": threshold,
        },
        "historical_materializer": {
            "selected_candidate_rows": len(selected_rows),
            "accepted_exact_rows": len(accepted_rows),
            "frozen_filter_match_rows": len(filtered_rows),
            "disclosed_historical_filtered_materializer_rows": disclosed_rows,
            "disclosed_historical_filtered_materializer_months": disclosed_months,
            "monthly_table": monthly_table,
            "monthly_match_counts": monthly_match_counts,
        },
        "post_freeze_observation": {
            "observed_market_days": observed_market_days,
            "parity_materializer_rows_in_window": _safe_int(parity_coverage.get("row_count_in_window")),
            "parity_filter_matched_selected_rows_in_window": observed_filter_matches,
            "parity_status": parity_latest.get("status"),
            "tracker_matched_rows": _safe_int(_as_dict(tracker_latest.get("forward_tracking")).get("matched_candidate_count")),
            "tracker_completed_rows": _safe_int(_as_dict(tracker_latest.get("forward_tracking")).get("completed_candidate_count")),
        },
        "zero_run_stationarity": {
            **zero_run,
            "regime_break_fraction_threshold": ZERO_RUN_REGIME_BREAK_MAX_FRACTION,
            "interpretation": (
                "post_freeze_zero_is_rare_in_historical_materializer_windows"
                if status == "post_freeze_zero_indicates_regime_break"
                else "post_freeze_zero_is_not_rare_enough_to_call_regime_break"
                if status == "post_freeze_zero_within_historical_variation"
                else "not_interpreted"
            ),
        },
        "zero_run_trigger_schedule": zero_run_schedule,
        "frozen_threshold_distance_summary": _threshold_distance_summary(accepted_rows, conditions, threshold),
        "scheduled_scan_near_miss_summary": _throughput_near_miss_summary(throughput_latest),
        "session_entry_window_overlap": _session_overlap(parity_latest),
        "proof_boundary": (
            "This report emits descriptive stationarity and distance statistics only. It is not profitability evidence, "
            "does not evaluate alternative thresholds, and does not authorize scanner policy, filter, proof-bar, live, "
            "auto-track, broker, quote-import, cohort-append, holdout, or promotion actions."
        ),
        "prohibited_actions": [
            "do_not_change_scanner_policy_from_stationarity_report",
            "do_not_change_filter_or_threshold_from_stationarity_report",
            "do_not_emit_counterfactual_threshold_match_counts",
            "do_not_emit_counterfactual_threshold_economics",
            "do_not_import_quotes_from_stationarity_report",
            "do_not_mutate_evidence_stores_from_stationarity_report",
            "do_not_append_cohort_rows_from_stationarity_report",
            "do_not_enable_live_validation_from_stationarity_report",
            "do_not_enable_auto_track_from_stationarity_report",
            "do_not_submit_broker_orders_from_stationarity_report",
            "do_not_consume_protected_holdout_from_stationarity_report",
            "do_not_promote_from_stationarity_report",
        ],
        "hash_invariance": _record_hash_invariance(hash_invariance_paths, hash_invariance_before)
        if hash_invariance_before is not None
        else {"recorded": False, "reason": "run_with_record_hash_invariance_to_hash_large_evidence_inputs"},
        **FALSE_FLAGS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    historical = _as_dict(report.get("historical_materializer"))
    post = _as_dict(report.get("post_freeze_observation"))
    zero = _as_dict(report.get("zero_run_stationarity"))
    schedule = _as_dict(report.get("zero_run_trigger_schedule"))
    break_trigger = _as_dict(schedule.get("first_regime_break_trigger"))
    confirmation_trigger = _as_dict(schedule.get("first_confirmation_trigger"))
    threshold = _as_dict(report.get("frozen_threshold_distance_summary"))
    overlap = _as_dict(report.get("session_entry_window_overlap"))
    lines = [
        "# Regular Options Materializer Match-Rate Stationarity",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Blockers: `{json.dumps(report.get('blockers') or [], sort_keys=True)}`.",
        f"- Historical frozen-filter matches: `{historical.get('frozen_filter_match_rows')}` / disclosed `{historical.get('disclosed_historical_filtered_materializer_rows')}`.",
        f"- Post-freeze materializer rows: `{post.get('parity_materializer_rows_in_window')}`.",
        f"- Post-freeze filter-matched rows: `{post.get('parity_filter_matched_selected_rows_in_window')}`.",
        f"- Zero-run windows: `{zero.get('zero_match_window_count')}` / `{zero.get('window_count')}`; fraction `{zero.get('zero_match_window_fraction')}`.",
        f"- Zero-run trigger schedule: `{schedule.get('status')}`; monotonicity `{_as_dict(schedule.get('monotonicity_check')).get('status')}`.",
        f"- First <=0.05 trigger if zero-run continues: `{break_trigger.get('projected_calendar_date_if_zero_run_continues')}` at `{break_trigger.get('window_market_days')}` market days; fraction `{break_trigger.get('zero_match_window_fraction')}`.",
        f"- First <=0.01 confirmation if zero-run continues: `{confirmation_trigger.get('projected_calendar_date_if_zero_run_continues')}` at `{confirmation_trigger.get('window_market_days')}` market days; fraction `{confirmation_trigger.get('zero_match_window_fraction')}`.",
        f"- Minimum historical distance below frozen threshold: `{threshold.get('min_distance')}`.",
        f"- Session-time overlap with materializer entry window: `{overlap.get('distinct_session_times_inside_entry_window')}` / `{overlap.get('distinct_scheduled_session_time_count')}` distinct times.",
        "",
        "## Zero-Run Trigger Schedule",
        "",
        "| Threshold | Window Market Days | Projected Date If Zero Continues | Historical Zero Fraction |",
        "|---|---:|---|---:|",
        f"| `<=0.05` | {break_trigger.get('window_market_days')} | `{break_trigger.get('projected_calendar_date_if_zero_run_continues')}` | {break_trigger.get('zero_match_window_fraction')} |",
        f"| `<=0.01` | {confirmation_trigger.get('window_market_days')} | `{confirmation_trigger.get('projected_calendar_date_if_zero_run_continues')}` | {confirmation_trigger.get('zero_match_window_fraction')} |",
        "",
        "A single post-freeze parity materializer filter match voids this zero-run schedule and requires a fresh stationarity run.",
        "",
        "## Monthly Match Counts",
        "",
        "| Month | Accepted Rows | Frozen-Filter Matches | Match Rate |",
        "|---|---:|---:|---:|",
    ]
    for row in _as_list(historical.get("monthly_table")):
        row = _as_dict(row)
        lines.append(
            f"| `{row.get('month')}` | {row.get('accepted_materializer_rows')} | {row.get('frozen_filter_match_rows')} | {row.get('match_rate')} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            str(report.get("proof_boundary") or ""),
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
    parser = argparse.ArgumentParser(description="Build read-only materializer match-rate stationarity report.")
    parser.add_argument("--historical-engine-dir", type=Path, default=DEFAULT_HISTORICAL_ENGINE_DIR)
    parser.add_argument("--historical-engine-latest", type=Path, default=DEFAULT_HISTORICAL_ENGINE_LATEST)
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--tracker-latest", type=Path, default=DEFAULT_TRACKER_LATEST)
    parser.add_argument("--parity-latest", type=Path, default=DEFAULT_PARITY_LATEST)
    parser.add_argument("--throughput-latest", type=Path, default=DEFAULT_THROUGHPUT_LATEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--record-hash-invariance", action="store_true")
    parser.add_argument("--hash-invariance-path", type=Path, action="append", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    hash_paths = tuple(args.hash_invariance_path or DEFAULT_HASH_INVARIANCE_PATHS)
    before = _hash_snapshot(hash_paths) if args.record_hash_invariance else None
    report = build_report(
        historical_engine_dir=args.historical_engine_dir,
        historical_engine_latest_path=args.historical_engine_latest,
        policy_contract_path=args.policy_contract,
        tracker_latest_path=args.tracker_latest,
        parity_latest_path=args.parity_latest,
        throughput_latest_path=args.throughput_latest,
        hash_invariance_before=before,
        hash_invariance_paths=hash_paths,
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
