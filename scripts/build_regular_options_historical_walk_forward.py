from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_feature_store as feature_store  # noqa: E402
from scripts import build_regular_options_robust_search_evaluation as robust_search  # noqa: E402
from scripts import run_regular_options_all_planned_sleeves as all_planned_sleeves  # noqa: E402
from scripts.regular_options_repair_targets import json_item, missing_items_from_run_paths  # noqa: E402


REPORT_ID = "regular_options_historical_walkforward"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-walk-forward.md"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_ALL_PLANNED_REPORT = (
    ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "all-planned-sleeves" / "latest.json"
)

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_historical_walkforward",
    "do_not_submit_broker_orders_from_historical_walkforward",
    "do_not_change_scanner_policy_from_historical_walkforward",
    "do_not_change_proof_bars_from_historical_walkforward",
    "do_not_consume_protected_forward_holdout_from_historical_walkforward",
    "do_not_treat_historical_results_as_fresh_forward_proof",
)

VARIANT_WORTH_STATUS_PRIORITY = {
    "candidate_to_close_200_gap": 0,
    "repair_coverage_before_counting": 1,
    "repair_stress_before_counting": 2,
    "profitable_but_overlaps": 3,
    "weak_positive_or_marginal": 4,
    "thin_sample": 5,
    "not_worth_current_shape": 6,
    "no_current_candidates": 7,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_date(value: Any) -> date | None:
    raw = "" if value is None else str(value).strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "error": "missing_artifact",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "unreadable",
            "path": str(path),
            "error": type(exc).__name__,
        }
    return payload if isinstance(payload, dict) else {"status": "invalid", "path": str(path)}


def _holdout_start(contract: dict[str, Any]) -> str | None:
    protected = _as_dict(contract.get("protected_range"))
    start = _parse_date(protected.get("start_date"))
    return start.isoformat() if start else None


def _holdout_metadata_blockers(contract: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = str(contract.get("status") or "").strip()
    if status in {"missing", "unreadable", "invalid"}:
        blockers.append(f"forward_holdout_contract_{status}")
    elif status != "active":
        blockers.append("forward_holdout_contract_status_not_active")
    if not str(contract.get("contract_id") or "").strip():
        blockers.append("forward_holdout_contract_id_missing")
    date_basis = str(_as_dict(contract.get("protected_range")).get("date_basis") or "").strip()
    if date_basis != "candidate_entry_date":
        blockers.append("forward_holdout_date_basis_not_candidate_entry_date")
    return blockers


def _candidate_latest_entry_date(robust_report: dict[str, Any]) -> str | None:
    latest: date | None = None
    for candidate in _as_list(robust_report.get("candidates")):
        combined = _as_dict(_as_dict(candidate).get("split_metrics")).get("combined")
        entry = _parse_date(_as_dict(combined).get("latest_entry_date"))
        if entry is not None and (latest is None or entry > latest):
            latest = entry
    return latest.isoformat() if latest else None


def _forward_holdout_guard(robust_report: dict[str, Any], holdout_contract: dict[str, Any]) -> dict[str, Any]:
    protected_start_date = _holdout_start(holdout_contract)
    latest_candidate_entry_date = _candidate_latest_entry_date(robust_report)
    start = _parse_date(protected_start_date)
    latest = _parse_date(latest_candidate_entry_date)
    blockers = _holdout_metadata_blockers(holdout_contract)

    if start is None:
        blockers.append("forward_holdout_start_date_missing")
    if latest is None:
        blockers.append("latest_candidate_entry_date_missing")

    overlaps = bool(start and latest and latest >= start)
    if overlaps:
        blockers.append("protected_forward_holdout_overlap")

    return {
        "contract_id": holdout_contract.get("contract_id"),
        "contract_status": holdout_contract.get("status"),
        "contract_error": holdout_contract.get("error"),
        "contract_path": holdout_contract.get("path"),
        "date_basis": _as_dict(holdout_contract.get("protected_range")).get("date_basis"),
        "protected_start_date": protected_start_date,
        "latest_candidate_entry_date": latest_candidate_entry_date,
        "overlaps_protected_range": overlaps,
        "ordinary_workflow_consumes_holdout": False,
        "blockers": blockers,
        "status": "blocked" if blockers else "passed",
    }


def _protected_holdout_overlap(robust_report: dict[str, Any], holdout_contract: dict[str, Any]) -> bool:
    start = _parse_date(_holdout_start(holdout_contract))
    latest = _parse_date(_candidate_latest_entry_date(robust_report))
    return bool(start and latest and latest >= start)


def _as_of_overlaps_holdout(as_of_date: Any, holdout_contract: dict[str, Any]) -> bool:
    start = _parse_date(_holdout_start(holdout_contract))
    as_of = _parse_date(as_of_date)
    return bool(start and as_of and as_of >= start)


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _rel(path: Path | str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _candidate_rows(robust_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in _as_list(robust_report.get("candidates")):
        candidate = _as_dict(candidate)
        splits = _as_dict(candidate.get("split_metrics"))
        combined = _as_dict(splits.get("combined"))
        validation = _as_dict(splits.get("validation"))
        final = _as_dict(splits.get("final_holdout"))
        final_bootstrap = _as_dict(final.get("bootstrap"))
        rows.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "candidate_type": candidate.get("candidate_type"),
                "status": candidate.get("status"),
                "historical_nomination_ready": bool(candidate.get("historical_nomination_ready")),
                "combined_exact_trade_count": _safe_int(combined.get("exact_trade_count")),
                "validation_exact_trade_count": _safe_int(validation.get("exact_trade_count")),
                "final_holdout_exact_trade_count": _safe_int(final.get("exact_trade_count")),
                "combined_profit_factor": _round_optional(combined.get("profit_factor"), 4),
                "validation_profit_factor": _round_optional(validation.get("profit_factor"), 4),
                "final_holdout_profit_factor": _round_optional(final.get("profit_factor"), 4),
                "final_holdout_pf_lb_5pct": _round_optional(final_bootstrap.get("pf_lb_5pct"), 4),
                "final_holdout_statistical_confidence": final_bootstrap.get("statistical_confidence"),
                "combined_avg_pnl_pct": _round_optional(combined.get("avg_pnl_pct")),
                "final_holdout_avg_pnl_pct": _round_optional(final.get("avg_pnl_pct")),
                "combined_max_drawdown_pct_points": _round_optional(
                    _as_dict(combined.get("risk")).get("max_drawdown_pct_points")
                ),
                "final_holdout_max_drawdown_pct_points": _round_optional(
                    _as_dict(final.get("risk")).get("max_drawdown_pct_points")
                ),
                "blockers": list(candidate.get("blockers") or []),
            }
        )
    rows.sort(
        key=lambda row: (
            not bool(row["historical_nomination_ready"]),
            -float(row["final_holdout_pf_lb_5pct"] or -9999.0),
            -int(row["combined_exact_trade_count"] or 0),
            str(row["candidate_id"] or ""),
        )
    )
    return rows


def _variant_rows(all_planned_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _as_list(all_planned_report.get("variants")):
        variant = _as_dict(raw)
        metrics = _as_dict(variant.get("standalone_metrics"))
        robustness = _as_dict(variant.get("robustness"))
        novelty = _as_dict(variant.get("novelty_vs_core_plus_clean_reference"))
        incremental = _as_dict(novelty.get("incremental_metrics"))
        rows.append(
            {
                "lane_id": variant.get("lane_id"),
                "variant_id": variant.get("variant_id"),
                "runner": variant.get("runner"),
                "run_path": _rel(variant.get("run_path")),
                "robustness_path": _rel(variant.get("robustness_path")),
                "worth_status": variant.get("worth_status"),
                "standalone_exact_trade_count": _safe_int(metrics.get("exact_trade_count")),
                "standalone_candidate_trade_count": _safe_int(metrics.get("candidate_trade_count")),
                "standalone_unpriced_trade_count": _safe_int(metrics.get("unpriced_trade_count")),
                "standalone_profit_factor": _round_optional(metrics.get("profit_factor"), 4),
                "standalone_avg_pnl_pct": _round_optional(metrics.get("avg_pnl_pct")),
                "quote_coverage_pct": _round_optional(metrics.get("quote_coverage_pct")),
                "stress_5pct_per_side_profit_factor": _round_optional(
                    robustness.get("stress_5pct_per_side_profit_factor"), 4
                ),
                "rolling_status": robustness.get("rolling_status"),
                "strict_new_trade_count": _safe_int(novelty.get("strict_new_trade_count")),
                "gap_to_200_after_candidate": _safe_int(novelty.get("gap_after_candidate")),
                "incremental_profit_factor": _round_optional(incremental.get("profit_factor"), 4),
                "side_aware_zero_bid_status": _as_dict(variant.get("side_aware_zero_bid_replay")).get("status"),
                "error": variant.get("error"),
            }
        )
    rows.sort(
        key=lambda row: (
            VARIANT_WORTH_STATUS_PRIORITY.get(str(row.get("worth_status") or ""), 99),
            -int(row.get("strict_new_trade_count") or 0),
            -float(row.get("stress_5pct_per_side_profit_factor") or -9999.0),
            -float(row.get("standalone_profit_factor") or -9999.0),
            str(row.get("variant_id") or ""),
        )
    )
    return rows


def _priority_band(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def _queue_row(
    *,
    priority_score: int,
    category: str,
    subject_type: str,
    subject_id: Any,
    action: str,
    reason: str,
    blockers: Sequence[str],
    metrics: dict[str, Any] | None = None,
    repair_target_summary: dict[str, Any] | None = None,
    execution_permission: str = "read_only_research_ok",
    holdout_boundary: str = "protected_forward_holdout_must_remain_unused",
) -> dict[str, Any]:
    return {
        "priority_score": int(priority_score),
        "priority_band": _priority_band(int(priority_score)),
        "category": category,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "action": action,
        "reason": reason,
        "blockers": list(blockers),
        "metrics": metrics or {},
        "repair_target_summary": repair_target_summary or {},
        "execution_permission": execution_permission,
        "holdout_boundary": holdout_boundary,
        "live_policy_change_allowed": False,
    }


def _blocker_contains(blockers: Sequence[Any], *needles: str) -> bool:
    lowered = [str(blocker).lower() for blocker in blockers]
    return any(any(needle in blocker for needle in needles) for blocker in lowered)


def _repair_target_summary(run_path: Any) -> dict[str, Any]:
    raw_path = str(run_path or "").strip()
    if not raw_path:
        return {"detail_status": "run_path_missing", "base_target_count": 0}
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {"detail_status": "run_artifact_missing", "run_path": _rel(path), "base_target_count": 0}
    try:
        items = [json_item(item) for item in missing_items_from_run_paths([path])]
    except Exception as exc:
        return {
            "detail_status": f"unreadable:{type(exc).__name__}",
            "run_path": _rel(path),
            "base_target_count": 0,
        }

    ticker_counts: Counter[str] = Counter()
    source_field_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for item in items:
        for occurrence in _as_list(item.get("source_occurrences")):
            occurrence = _as_dict(occurrence)
            ticker = str(occurrence.get("ticker") or "").upper()
            if ticker:
                ticker_counts[ticker] += 1
            source_field = str(occurrence.get("source_field") or "unknown")
            source_field_counts[source_field] += 1
            reason = str(occurrence.get("unpriced_reason") or "unknown")
            reason_counts[reason] += 1

    missing_dates = sorted({str(item.get("quote_date") or "")[:10] for item in items if item.get("quote_date")})
    contracts = sorted({str(item.get("contract_symbol") or "") for item in items if item.get("contract_symbol")})
    source_occurrence_count = sum(len(_as_list(item.get("source_occurrences"))) for item in items)
    return {
        "detail_status": "available" if items else "no_missing_exact_targets",
        "run_path": _rel(path),
        "base_target_count": len(items),
        "source_occurrence_count": source_occurrence_count,
        "missing_quote_dates": missing_dates[:12],
        "contract_symbols": contracts[:12],
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "source_field_counts": dict(sorted(source_field_counts.items())),
        "unpriced_reason_counts": dict(sorted(reason_counts.items())),
    }


def _repair_queue(candidates: list[dict[str, Any]], variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in variants:
        worth_status = str(row.get("worth_status") or "")
        if worth_status == "repair_coverage_before_counting":
            rows.append(
                _queue_row(
                    priority_score=92 + min(_safe_int(row.get("strict_new_trade_count")), 7),
                    category="peer_variant_coverage_repair",
                    subject_type="variant",
                    subject_id=row.get("variant_id"),
                    action="repair_pre_holdout_quote_coverage_then_rerun_walkforward",
                    reason="Peer sleeve has positive standalone/stress economics but cannot be counted until coverage gaps are repaired.",
                    blockers=["quote_coverage_below_clean_counting_gate"],
                    metrics={
                        "candidate_trade_count": row.get("standalone_candidate_trade_count"),
                        "exact_trade_count": row.get("standalone_exact_trade_count"),
                        "unpriced_trade_count": row.get("standalone_unpriced_trade_count"),
                        "profit_factor": row.get("standalone_profit_factor"),
                        "stress_5pct_per_side_profit_factor": row.get("stress_5pct_per_side_profit_factor"),
                        "quote_coverage_pct": row.get("quote_coverage_pct"),
                        "strict_new_trade_count": row.get("strict_new_trade_count"),
                        "gap_to_200_after_candidate": row.get("gap_to_200_after_candidate"),
                        "run_path": row.get("run_path"),
                    },
                    repair_target_summary=_repair_target_summary(row.get("run_path")),
                    execution_permission="requires_explicit_approval_before_evidence_store_mutation",
                )
            )
        elif worth_status == "repair_stress_before_counting":
            rows.append(
                _queue_row(
                    priority_score=82,
                    category="peer_variant_stress_repair",
                    subject_type="variant",
                    subject_id=row.get("variant_id"),
                    action="repair_stress_or_risk_shape_before_counting",
                    reason="Coverage is clean enough, but the variant still fails stress or risk robustness before it can count toward a profitable lane.",
                    blockers=["stress_or_robustness_below_counting_gate"],
                    metrics={
                        "candidate_trade_count": row.get("standalone_candidate_trade_count"),
                        "exact_trade_count": row.get("standalone_exact_trade_count"),
                        "unpriced_trade_count": row.get("standalone_unpriced_trade_count"),
                        "profit_factor": row.get("standalone_profit_factor"),
                        "stress_5pct_per_side_profit_factor": row.get("stress_5pct_per_side_profit_factor"),
                        "quote_coverage_pct": row.get("quote_coverage_pct"),
                        "strict_new_trade_count": row.get("strict_new_trade_count"),
                        "gap_to_200_after_candidate": row.get("gap_to_200_after_candidate"),
                        "run_path": row.get("run_path"),
                    },
                )
            )
        elif worth_status == "profitable_but_overlaps":
            rows.append(
                _queue_row(
                    priority_score=64,
                    category="peer_variant_overlap_review",
                    subject_type="variant",
                    subject_id=row.get("variant_id"),
                    action="do_not_count_as_gap_closer_without_non_overlapping_edge",
                    reason="Variant is historically profitable but overlaps too much with the existing clean stack to solve the trade-count/profitability lane objective.",
                    blockers=["insufficient_non_overlapping_incremental_edge"],
                    metrics={
                        "candidate_trade_count": row.get("standalone_candidate_trade_count"),
                        "exact_trade_count": row.get("standalone_exact_trade_count"),
                        "profit_factor": row.get("standalone_profit_factor"),
                        "stress_5pct_per_side_profit_factor": row.get("stress_5pct_per_side_profit_factor"),
                        "quote_coverage_pct": row.get("quote_coverage_pct"),
                        "strict_new_trade_count": row.get("strict_new_trade_count"),
                        "gap_to_200_after_candidate": row.get("gap_to_200_after_candidate"),
                    },
                )
            )
        elif worth_status == "weak_positive_or_marginal":
            rows.append(
                _queue_row(
                    priority_score=55,
                    category="peer_variant_hypothesis_review",
                    subject_type="variant",
                    subject_id=row.get("variant_id"),
                    action="require_causal_hypothesis_before_tuning_or_more_replay",
                    reason="Variant is not strong enough for coverage repair priority without a causal filter or risk change.",
                    blockers=["weak_positive_or_marginal_historical_readback"],
                    metrics={
                        "exact_trade_count": row.get("standalone_exact_trade_count"),
                        "profit_factor": row.get("standalone_profit_factor"),
                        "stress_5pct_per_side_profit_factor": row.get("stress_5pct_per_side_profit_factor"),
                        "quote_coverage_pct": row.get("quote_coverage_pct"),
                    },
                )
            )

    for row in candidates:
        blockers = [str(blocker) for blocker in _as_list(row.get("blockers"))]
        subject_id = row.get("candidate_id")
        if _blocker_contains(blockers, "source_quality", "paper_shadow", "unpriced"):
            rows.append(
                _queue_row(
                    priority_score=96,
                    category="candidate_source_quality_repair",
                    subject_type="candidate",
                    subject_id=subject_id,
                    action="repair_source_quality_and_unpriced_rows_before_any_nomination",
                    reason="Robust candidate still depends on pending source-quality or unpriced exact-row repair.",
                    blockers=blockers,
                    metrics={
                        "combined_exact_trade_count": row.get("combined_exact_trade_count"),
                        "final_holdout_exact_trade_count": row.get("final_holdout_exact_trade_count"),
                        "final_holdout_profit_factor": row.get("final_holdout_profit_factor"),
                        "final_holdout_pf_lb_5pct": row.get("final_holdout_pf_lb_5pct"),
                    },
                    execution_permission="requires_explicit_approval_before_evidence_store_mutation",
                )
            )
        if _blocker_contains(blockers, "zero_bid"):
            rows.append(
                _queue_row(
                    priority_score=88,
                    category="candidate_zero_bid_economics",
                    subject_type="candidate",
                    subject_id=subject_id,
                    action="separate_zero_bid_artifacts_from_fillable_edge_or_keep_lane_parked",
                    reason="Historical P&L cannot be promoted while zero-bid or side-aware executable economics remain unresolved.",
                    blockers=blockers,
                    metrics={
                        "combined_exact_trade_count": row.get("combined_exact_trade_count"),
                        "final_holdout_profit_factor": row.get("final_holdout_profit_factor"),
                    },
                    execution_permission="read_only_research_ok",
                )
            )
        if _blocker_contains(blockers, "final_holdout_exact_trades_below_30", "validation_exact_trades_below_30"):
            final_n = _safe_int(row.get("final_holdout_exact_trade_count"))
            validation_n = _safe_int(row.get("validation_exact_trade_count"))
            rows.append(
                _queue_row(
                    priority_score=84 if final_n >= 25 else 72,
                    category="candidate_sample_size_gap",
                    subject_type="candidate",
                    subject_id=subject_id,
                    action="fill_sample_gap_only_with_pre_holdout_repair_or_future_frozen_forward_rows",
                    reason="Sample-size blockers remain; protected forward holdout cannot be used as ordinary tuning data.",
                    blockers=blockers,
                    metrics={
                        "validation_exact_trade_count": validation_n,
                        "final_holdout_exact_trade_count": final_n,
                        "final_holdout_rows_needed_for_30_minimum": max(0, 30 - final_n),
                    },
                    execution_permission="requires_new_forward_or_pre_holdout_evidence_repair",
                    holdout_boundary="do_not_use_protected_forward_holdout_to_fill_sample_gap",
                )
            )
        if _blocker_contains(blockers, "selection_adjusted", "pf_lb"):
            rows.append(
                _queue_row(
                    priority_score=68,
                    category="candidate_statistical_bar",
                    subject_type="candidate",
                    subject_id=subject_id,
                    action="do_not_promote_until_lower_bound_clears_adjusted_bar",
                    reason="Historical point estimate is insufficient while the lower-confidence profit factor stays below the selection-adjusted bar.",
                    blockers=blockers,
                    metrics={
                        "final_holdout_profit_factor": row.get("final_holdout_profit_factor"),
                        "final_holdout_pf_lb_5pct": row.get("final_holdout_pf_lb_5pct"),
                    },
                )
            )

    rows.sort(
        key=lambda row: (
            -_safe_int(row.get("priority_score")),
            str(row.get("category") or ""),
            str(row.get("subject_id") or ""),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["priority_rank"] = index
    return rows


def _repair_queue_summary(queue: list[dict[str, Any]]) -> dict[str, Any]:
    by_category = Counter(str(row.get("category") or "unknown") for row in queue)
    by_permission = Counter(str(row.get("execution_permission") or "unknown") for row in queue)
    by_band = Counter(str(row.get("priority_band") or "unknown") for row in queue)
    return {
        "total": len(queue),
        "high_priority_count": _safe_int(by_band.get("high")),
        "medium_priority_count": _safe_int(by_band.get("medium")),
        "low_priority_count": _safe_int(by_band.get("low")),
        "by_category": dict(sorted(by_category.items())),
        "by_execution_permission": dict(sorted(by_permission.items())),
        "top_subjects": [row.get("subject_id") for row in queue[:5]],
    }


def _all_planned_summary(all_planned_report: dict[str, Any], holdout_contract: dict[str, Any]) -> dict[str, Any]:
    missing = "variants" not in all_planned_report
    variants = _variant_rows(all_planned_report)
    worth_counts = Counter(str(row.get("worth_status") or "unknown") for row in variants)
    as_of_date = all_planned_report.get("as_of_date")
    as_of_missing = not bool(as_of_date)
    as_of_overlap = _as_of_overlaps_holdout(as_of_date, holdout_contract)
    implemented_variant_count = _safe_int(all_planned_report.get("implemented_variant_count"))
    tested_variant_count = _safe_int(all_planned_report.get("tested_end_to_end_variant_count"))
    run_failed_count = _safe_int(all_planned_report.get("run_failed_count"))
    incomplete_variant_coverage = implemented_variant_count > tested_variant_count
    status = "all_planned_sleeves_loaded"
    blockers: list[str] = []
    if missing:
        status = "all_planned_sleeves_missing"
        blockers.append("all_planned_sleeves_report_missing")
    if as_of_missing:
        status = "all_planned_sleeves_as_of_missing"
        blockers.append("all_planned_sleeves_as_of_date_missing")
    if as_of_overlap:
        status = "all_planned_sleeves_protected_holdout_overlap"
        blockers.append("all_planned_sleeves_as_of_date_overlaps_protected_holdout")
    if incomplete_variant_coverage:
        status = "all_planned_sleeves_incomplete_variant_coverage"
        blockers.append("all_planned_sleeves_incomplete_variant_coverage")
        blockers.append("all_planned_sleeves_tested_variant_count_below_implemented")
    if run_failed_count:
        status = "all_planned_sleeves_run_failures"
        blockers.append("all_planned_sleeves_run_failed")
    return {
        "status": status,
        "blockers": blockers,
        "generated_at_utc": all_planned_report.get("generated_at_utc"),
        "as_of_date": as_of_date,
        "protected_holdout_overlap": as_of_overlap,
        "implemented_variant_count": all_planned_report.get("implemented_variant_count"),
        "selected_variant_count": all_planned_report.get("selected_variant_count"),
        "tested_end_to_end_variant_count": all_planned_report.get("tested_end_to_end_variant_count"),
        "incomplete_variant_coverage": incomplete_variant_coverage,
        "run_failed_count": run_failed_count,
        "worth_status_counts": dict(sorted(worth_counts.items())),
        "base_clean_stack": all_planned_report.get("base_clean_stack"),
    }


def build_workflow_report(
    *,
    feature_report: dict[str, Any],
    robust_report: dict[str, Any],
    all_planned_report: dict[str, Any],
    holdout_contract: dict[str, Any],
    generated_at_utc: str | None = None,
    commands_run: Sequence[str] = (),
) -> dict[str, Any]:
    feature_summary = _as_dict(feature_report.get("summary"))
    robust_summary = _as_dict(robust_report.get("summary"))
    holdout_guard = _forward_holdout_guard(robust_report, holdout_contract)
    holdout_overlap = bool(holdout_guard.get("overlaps_protected_range"))
    robust_status = str(robust_report.get("status") or "")
    all_planned_summary = _all_planned_summary(all_planned_report, holdout_contract)
    feature_status = str(feature_report.get("status") or "")
    blockers: list[str] = []
    blockers.extend(str(item) for item in _as_list(holdout_guard.get("blockers")))
    if feature_status != "feature_store_built":
        blockers.append(f"feature_store_status:{feature_status or 'missing'}")
    if robust_status not in {
        "historical_candidates_ready_for_forward_nomination",
        "historical_candidates_blocked",
    }:
        blockers.append(f"robust_search_status:{robust_status or 'missing'}")
    blockers.extend(str(item) for item in _as_list(all_planned_summary.get("blockers")))

    if holdout_overlap:
        status = "historical_walkforward_blocked_protected_holdout_overlap"
    elif holdout_guard.get("blockers"):
        status = "historical_walkforward_blocked_forward_holdout_guard"
    elif all_planned_summary.get("blockers"):
        status = "historical_walkforward_blocked_all_planned_input"
    elif feature_status != "feature_store_built":
        status = "historical_walkforward_blocked_feature_store"
    elif robust_status == "historical_candidates_ready_for_forward_nomination":
        status = "historical_walkforward_ready_for_forward_nomination"
    elif robust_status == "historical_candidates_blocked":
        status = "historical_walkforward_ran_candidates_blocked"
    else:
        status = "historical_walkforward_blocked_inputs"

    candidates = _candidate_rows(robust_report)
    variants = _variant_rows(all_planned_report)
    repair_queue = _repair_queue(candidates, variants)
    repair_queue_summary = _repair_queue_summary(repair_queue)
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_historical_walkforward_operator_workflow",
        "schema_version": 2,
        "read_only": True,
        "live_policy_change": False,
        "commands_run": list(commands_run),
        "inputs": {
            "feature_store_report_id": feature_report.get("report_id"),
            "robust_search_report_id": robust_report.get("report_id"),
            "all_planned_report_path": str(DEFAULT_ALL_PLANNED_REPORT),
            "holdout_contract_id": holdout_contract.get("contract_id"),
            "holdout_contract_status": holdout_contract.get("status"),
        },
        "forward_holdout_guard": holdout_guard,
        "summary": {
            "overall_status": status,
            "live_policy_change": False,
            "feature_store_status": feature_status,
            "feature_store_shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
            "feature_store_latest_shared_quote_date_et": feature_summary.get("latest_shared_quote_date_et"),
            "robust_search_status": robust_status,
            "accepted_exact_trade_count": robust_summary.get("accepted_exact_trade_count"),
            "candidate_count": robust_summary.get("candidate_count"),
            "ready_candidate_count": robust_summary.get("ready_candidate_count"),
            "variants_searched": robust_summary.get("variants_searched"),
            "selection_adjusted_bar": robust_summary.get("selection_adjusted_bar"),
            "all_planned_status": all_planned_summary.get("status"),
            "all_planned_as_of_date": all_planned_summary.get("as_of_date"),
            "all_planned_variant_count": all_planned_summary.get("implemented_variant_count"),
            "all_planned_tested_variant_count": all_planned_summary.get("tested_end_to_end_variant_count"),
            "all_planned_run_failed_count": all_planned_summary.get("run_failed_count"),
            "latest_candidate_entry_date": holdout_guard.get("latest_candidate_entry_date"),
            "protected_forward_holdout_start_date": holdout_guard.get("protected_start_date"),
            "protected_forward_holdout_overlap": holdout_overlap,
            "forward_holdout_guard_status": holdout_guard.get("status"),
            "promotion_ready": False,
            "repair_queue_total": repair_queue_summary.get("total"),
            "repair_queue_high_priority_count": repair_queue_summary.get("high_priority_count"),
        },
        "candidate_rows": candidates,
        "all_planned_sleeves": all_planned_summary,
        "variant_rows": variants,
        "repair_queue_summary": repair_queue_summary,
        "repair_queue": repair_queue,
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "historical walk-forward research workflow over trusted intraday exact rows",
            "readback_is_not": "fresh forward proof, live-validation eligibility, broker action, scanner policy change, proof-bar reduction, or protected-holdout consumption",
            "historical_use": "nominate, reject, or refreeze candidate lanes for future forward tracking only",
            "fresh_forward_requirement": "production promotion still requires post-freeze exact realized OPRA/NBBO P&L under the existing contracts",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    holdout_guard = _as_dict(report.get("forward_holdout_guard"))
    guard_blockers = _as_list(holdout_guard.get("blockers"))
    lines = [
        "# Regular Options Historical Walk-Forward Workflow",
        "",
        "This report is generated from `scripts/build_regular_options_historical_walk_forward.py`. It refreshes the point-in-time feature-store readback, runs the robust historical search evaluation, ingests the all-planned peer sleeve readback, and combines the outputs into an operator-facing walk-forward summary. It is read-only research and does not create trades, change scanner policy, consume protected forward holdout, lower proof bars, or treat historical rows as fresh forward proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Feature store: `{summary.get('feature_store_status')}` with `{summary.get('feature_store_shared_quote_date_count')}` shared quote dates through `{summary.get('feature_store_latest_shared_quote_date_et')}`.",
        f"- Robust search: `{summary.get('robust_search_status')}`.",
        f"- Accepted exact trades: `{summary.get('accepted_exact_trade_count')}`.",
        f"- Ready historical candidates: `{summary.get('ready_candidate_count')}` / `{summary.get('candidate_count')}`.",
        f"- Variants searched: `{summary.get('variants_searched')}`; selection-adjusted PF-LB bar `{summary.get('selection_adjusted_bar')}`.",
        f"- All-planned sleeves: `{summary.get('all_planned_status')}`; tested `{summary.get('all_planned_tested_variant_count')}` / `{summary.get('all_planned_variant_count')}` as of `{summary.get('all_planned_as_of_date')}`.",
        f"- Latest candidate entry date: `{summary.get('latest_candidate_entry_date')}`.",
        f"- Protected forward holdout starts: `{summary.get('protected_forward_holdout_start_date')}`; overlap `{summary.get('protected_forward_holdout_overlap')}`.",
        f"- Forward holdout guard: `{summary.get('forward_holdout_guard_status')}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Repair queue: `{summary.get('repair_queue_high_priority_count')}` high-priority rows / `{summary.get('repair_queue_total')}` total.",
        "",
        "## Forward Holdout Guard",
        "",
        f"- Status: `{holdout_guard.get('status')}`.",
        f"- Contract status: `{holdout_guard.get('contract_status')}`.",
        f"- Date basis: `{holdout_guard.get('date_basis')}`.",
        f"- Protected start: `{holdout_guard.get('protected_start_date')}`.",
        f"- Latest candidate entry: `{holdout_guard.get('latest_candidate_entry_date')}`.",
        f"- Overlap: `{holdout_guard.get('overlaps_protected_range')}`.",
        f"- Blockers: `{', '.join(str(item) for item in guard_blockers) if guard_blockers else 'none'}`.",
        "",
        "## Candidate Results",
        "",
        "| Candidate | Status | Total N | Val N | Holdout N | Holdout PF | Holdout PF LB | Holdout DD | Total DD | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("candidate_rows")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('candidate_id'))}`",
                    f"`{_cell(row.get('status'))}`",
                    _cell(row.get("combined_exact_trade_count")),
                    _cell(row.get("validation_exact_trade_count")),
                    _cell(row.get("final_holdout_exact_trade_count")),
                    _cell(row.get("final_holdout_profit_factor")),
                    _cell(row.get("final_holdout_pf_lb_5pct")),
                    _cell(row.get("final_holdout_max_drawdown_pct_points")),
                    _cell(row.get("combined_max_drawdown_pct_points")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Workflow Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    repair_queue = _as_list(report.get("repair_queue"))
    if repair_queue:
        lines.extend(
            [
                "",
                "## Repair Queue",
                "",
                "| Rank | Priority | Category | Subject | Targets | Action | Permission | Holdout Boundary |",
                "|---:|---|---|---|---:|---|---|---|",
            ]
        )
        for row in repair_queue[:15]:
            row = _as_dict(row)
            target_summary = _as_dict(row.get("repair_target_summary"))
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(row.get("priority_rank")),
                        f"`{_cell(row.get('priority_band'))}`",
                        f"`{_cell(row.get('category'))}`",
                        f"`{_cell(row.get('subject_id'))}`",
                        _cell(target_summary.get("base_target_count") if target_summary else ""),
                        _cell(row.get("action")),
                        f"`{_cell(row.get('execution_permission'))}`",
                        f"`{_cell(row.get('holdout_boundary'))}`",
                    ]
                )
                + " |"
            )
        if len(repair_queue) > 15:
            lines.append("")
            lines.append(f"Showing top `15` of `{len(repair_queue)}` repair rows; see the JSON artifact for the full queue.")
        target_rows = [
            _as_dict(row)
            for row in repair_queue
            if _as_dict(_as_dict(row).get("repair_target_summary")).get("detail_status") == "available"
        ]
        if target_rows:
            lines.extend(
                [
                    "",
                    "### Repair Target Details",
                    "",
                    "| Subject | Targets | Occurrences | Tickers | Missing Dates | Contracts |",
                    "|---|---:|---:|---|---|---|",
                ]
            )
            for row in target_rows[:8]:
                target_summary = _as_dict(row.get("repair_target_summary"))
                ticker_counts = _as_dict(target_summary.get("ticker_counts"))
                ticker_text = ", ".join(f"{key}:{value}" for key, value in list(ticker_counts.items())[:6])
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{_cell(row.get('subject_id'))}`",
                            _cell(target_summary.get("base_target_count")),
                            _cell(target_summary.get("source_occurrence_count")),
                            _cell(ticker_text),
                            _cell(", ".join(str(item) for item in _as_list(target_summary.get("missing_quote_dates"))[:6])),
                            _cell(", ".join(str(item) for item in _as_list(target_summary.get("contract_symbols"))[:6])),
                        ]
                    )
                    + " |"
                )
    variants = _as_list(report.get("variant_rows"))
    if variants:
        lines.extend(
            [
                "",
                "## Peer/Variant Sleeve Results",
                "",
                "| Variant | Worth Status | Exact N | PF | Avg % | Coverage % | Stress PF | Strict New | Gap |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in variants[:15]:
            row = _as_dict(row)
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{_cell(row.get('variant_id'))}`",
                        f"`{_cell(row.get('worth_status'))}`",
                        _cell(row.get("standalone_exact_trade_count")),
                        _cell(row.get("standalone_profit_factor")),
                        _cell(row.get("standalone_avg_pnl_pct")),
                        _cell(row.get("quote_coverage_pct")),
                        _cell(row.get("stress_5pct_per_side_profit_factor")),
                        _cell(row.get("strict_new_trade_count")),
                        _cell(row.get("gap_to_200_after_candidate")),
                    ]
                )
                + " |"
            )
        if len(variants) > 15:
            lines.append("")
            lines.append(f"Showing top `15` of `{len(variants)}` variant rows; see the JSON artifact for the full table.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A ready candidate here means only that historical evidence is strong enough to nominate or refreeze future forward tracking. Production proof still requires fresh exact realized OPRA/NBBO P&L after the applicable freeze date.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


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
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def run_workflow(
    *,
    bootstrap_draws: int = 10_000,
    write: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    all_planned_report_path: Path = DEFAULT_ALL_PLANNED_REPORT,
    run_all_planned: bool = False,
    all_planned_as_of_date: date | None = None,
) -> dict[str, Any]:
    commands = [
        "npm run options:features:regular-options",
        "npm run options:robust-search:regular-options",
        "npm run options:replay:regular-options-walk-forward",
    ]
    holdout_contract = _load_json(holdout_contract_path)
    if run_all_planned:
        if all_planned_as_of_date is None:
            raise RuntimeError("--run-all-planned requires explicit --as-of-date before replay.")
        if _holdout_metadata_blockers(holdout_contract) or _parse_date(_holdout_start(holdout_contract)) is None:
            raise RuntimeError("--run-all-planned requires readable active forward holdout metadata before replay.")
        if _as_of_overlaps_holdout(all_planned_as_of_date.isoformat(), holdout_contract):
            raise RuntimeError("--as-of-date overlaps the protected forward holdout.")
        commands.insert(
            0,
            f"uv run --locked python scripts/run_regular_options_all_planned_sleeves.py --as-of-date {all_planned_as_of_date.isoformat()}",
        )
        all_planned_report = all_planned_sleeves.run_all_planned_sleeves(
            lookback_years=1,
            as_of_date=all_planned_as_of_date,
        )
    else:
        all_planned_report = _load_json(all_planned_report_path)
    feature_report = feature_store.build_report()
    if write:
        feature_artifacts = feature_store.write_outputs(feature_report)
        feature_report_path = Path(feature_artifacts["latest_json"])
        robust_report = robust_search.build_report(
            feature_store_report_path=feature_report_path,
            bootstrap_draws=max(int(bootstrap_draws), 1),
        )
        robust_search.write_outputs(robust_report)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            feature_report_path = Path(tmp) / "feature_store.json"
            feature_report_path.write_text(json.dumps(feature_report), encoding="utf8")
            robust_report = robust_search.build_report(
                feature_store_report_path=feature_report_path,
                bootstrap_draws=max(int(bootstrap_draws), 1),
            )
    report = build_workflow_report(
        feature_report=feature_report,
        robust_report=robust_report,
        all_planned_report=all_planned_report,
        holdout_contract=holdout_contract,
        commands_run=commands,
    )
    if write:
        write_outputs(report, output_dir=output_dir, docs_report=docs_report)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only regular-options historical walk-forward workflow.")
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--all-planned-report", type=Path, default=DEFAULT_ALL_PLANNED_REPORT)
    parser.add_argument("--run-all-planned", action="store_true")
    parser.add_argument("--as-of-date", default=None, help="Required with --run-all-planned; must be before protected holdout.")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = run_workflow(
        bootstrap_draws=max(int(args.bootstrap_draws), 1),
        write=not args.no_write,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        holdout_contract_path=args.holdout_contract,
        all_planned_report_path=args.all_planned_report,
        run_all_planned=bool(args.run_all_planned),
        all_planned_as_of_date=_parse_date(args.as_of_date),
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
