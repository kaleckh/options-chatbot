from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_robust_candidate_source_quality_manifest"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-robust-candidate-source-quality-manifest"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-robust-candidate-source-quality-manifest.md"
DEFAULT_WALK_FORWARD_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_ROBUST_SEARCH_REPORT = (
    ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json"
)
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_MULTILANE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_BULLISH_PULLBACK_RUN = (
    ROOT / "data" / "options-validation" / "runs" / "20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json"
)
DEFAULT_LANE_A_RUN = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json"
)
DEFAULT_LANE_A_ZERO_BID_REPORT = (
    ROOT / "data" / "profitability-lab" / "side-aware-zero-bid" / "latest_lane_a_side_aware_zero_bid.json"
)
DEFAULT_CVX_COVERAGE_DOC = ROOT / "docs" / "regular-options-cvx-executable-coverage.md"

ACTION_PERMISSIONS = {
    "read_only_research_ok": (
        "May inspect, classify, group, and recommend bounded follow-up without writing evidence stores or changing policy."
    ),
    "requires_explicit_approval_before_evidence_store_mutation": (
        "Any quote import, replay write that mutates evidence stores, or repair write needs explicit Prime CEO/operator approval."
    ),
    "requires_policy_change_approval": (
        "Any candidate kill/exclusion, source-quality policy change, contract-selection change, proof-bar change, or scanner-policy edit needs explicit approval."
    ),
    "not_actionable_without_forward_evidence": (
        "Historical rows cannot clear this gate; wait for pre-approved pre-holdout repair or fresh post-freeze forward evidence."
    ),
}

PROHIBITED_COMMANDS = (
    "no quote imports or evidence-store mutation without explicit approval",
    "no --apply",
    "no DB migrations, backups, deletes, broker, paper, or live-trading commands",
    "no scanner commands",
    "no promotion commands",
    "do not run --run-all-planned",
    "do not consume protected forward holdout",
    "do not edit source-quality policy from this manifest",
)

HIGH_PRIORITY_CATEGORY = "candidate_source_quality_repair"
ROW_IDS = (
    "combined_portfolio",
    "lane:bullish_pullback_core",
    "lane:lane_a_chain_native_ret20_4_stop200_time75",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path), "error": "missing_artifact"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unreadable", "path": str(path), "error": type(exc).__name__}
    return payload if isinstance(payload, dict) else {"status": "invalid", "path": str(path), "error": "json_root_not_object"}


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


def _ticker_from_row(row: dict[str, Any]) -> str:
    for key in ("ticker", "underlying", "symbol"):
        value = _norm(row.get(key)).upper()
        if value:
            return value
    for key in ("long_contract_symbol", "short_contract_symbol", "contract_symbol"):
        match = re.match(r"([A-Z]+)", _norm(row.get(key)).upper())
        if match:
            return match.group(1)
    return "UNKNOWN"


def summarize_unpriced_targets(run_report: dict[str, Any], *, source_path: Path | str) -> dict[str, Any]:
    rows = [dict(row) for row in _as_list(run_report.get("unpriced_trades") or run_report.get("unpriced_candidates"))]
    reason_counts: Counter[str] = Counter()
    missing_leg_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    quote_dates: set[str] = set()
    contract_symbols: set[str] = set()
    missing_quote_rows = 0
    no_chain_rows = 0

    for row in rows:
        reason = _norm(row.get("non_promotable_reason") or row.get("unpriced_reason") or "unknown")
        reason_counts[reason] += 1
        ticker_counts[_ticker_from_row(row)] += 1
        quote_date = _norm(row.get("missing_quote_date"))[:10]
        if quote_date:
            quote_dates.add(quote_date)
        leg_tokens: list[str] = []
        for leg_name, key in (("long", "missing_long_contract_symbol"), ("short", "missing_short_contract_symbol")):
            symbol = _norm(row.get(key))
            if symbol:
                leg_tokens.append(leg_name)
                contract_symbols.add(symbol)
        if not leg_tokens:
            for key in ("long_contract_symbol", "short_contract_symbol", "contract_symbol"):
                symbol = _norm(row.get(key))
                if symbol:
                    contract_symbols.add(symbol)
        missing_leg_counts["+".join(leg_tokens) if leg_tokens else "none"] += 1
        if "missing" in reason and "quote" in reason:
            missing_quote_rows += 1
        if "no_chain_native_spread" in reason:
            no_chain_rows += 1

    first_quote_date = min(quote_dates) if quote_dates else None
    last_quote_date = max(quote_dates) if quote_dates else None
    return {
        "source_path": _rel(source_path),
        "candidate_trade_count": run_report.get("candidate_trade_count"),
        "priced_trade_count": run_report.get("exact_contract_match_count")
        or _as_dict(run_report.get("authoritative_profitability_metrics")).get("trade_count"),
        "quote_coverage_pct": _round_optional(run_report.get("quote_coverage_pct")),
        "unpriced_count": len(rows),
        "missing_quote_count": missing_quote_rows,
        "no_chain_native_spread_count": no_chain_rows,
        "reason_counts": dict(sorted(reason_counts.items())),
        "missing_leg_counts": dict(sorted(missing_leg_counts.items())),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "first_missing_quote_date": first_quote_date,
        "last_missing_quote_date": last_quote_date,
        "missing_quote_dates": sorted(quote_dates)[:20],
        "contract_symbols": sorted(contract_symbols)[:20],
    }


def _high_priority_rows(walk_forward_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in _as_list(walk_forward_report.get("repair_queue"))
        if row.get("category") == HIGH_PRIORITY_CATEGORY and row.get("subject_id") in ROW_IDS
    ]
    rows.sort(key=lambda row: ROW_IDS.index(str(row.get("subject_id"))) if row.get("subject_id") in ROW_IDS else 99)
    return rows


def _robust_candidate_by_id(robust_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("candidate_id")): dict(row) for row in _as_list(robust_report.get("candidates"))}


def _has(blockers: Sequence[str], needle: str) -> bool:
    needle = needle.lower()
    return any(needle in blocker.lower() for blocker in blockers)


def _matching_blockers(blockers: Sequence[str], *needles: str) -> list[str]:
    lowered = [needle.lower() for needle in needles]
    return [blocker for blocker in blockers if any(needle in blocker.lower() for needle in lowered)]


def _classification(
    *,
    class_id: str,
    label: str,
    blockers: Sequence[str],
    permission: str,
    evidence: dict[str, Any] | None = None,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "class_id": class_id,
        "label": label,
        "blockers": list(blockers),
        "action_permission": permission,
        "evidence": evidence or {},
        "recommendation": recommendation,
    }


def _statistical_evidence(candidate: dict[str, Any], queue_row: dict[str, Any]) -> dict[str, Any]:
    splits = _as_dict(candidate.get("split_metrics"))
    final = _as_dict(splits.get("final_holdout"))
    validation = _as_dict(splits.get("validation"))
    selection = _as_dict(candidate.get("selection_adjustment"))
    metrics = _as_dict(queue_row.get("metrics"))
    return {
        "validation_exact_trade_count": validation.get("exact_trade_count")
        or metrics.get("validation_exact_trade_count"),
        "final_holdout_exact_trade_count": final.get("exact_trade_count")
        or metrics.get("final_holdout_exact_trade_count"),
        "final_holdout_profit_factor": final.get("profit_factor") or metrics.get("final_holdout_profit_factor"),
        "final_holdout_pf_lb_5pct": _as_dict(final.get("bootstrap")).get("pf_lb_5pct")
        or metrics.get("final_holdout_pf_lb_5pct"),
        "selection_adjusted_bar": selection.get("selection_adjusted_bar"),
        "final_holdout_rows_needed_for_30_minimum": max(
            0,
            30
            - _safe_int(
                final.get("exact_trade_count")
                or metrics.get("final_holdout_exact_trade_count")
            ),
        ),
    }


def _source_quality_exclusion_summary(robust_candidate: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in _as_list(robust_candidate.get("source_quality_exclusions"))]
    ticker_counts = Counter(_norm(row.get("ticker")).upper() for row in rows if _norm(row.get("ticker")))
    rule_counts = Counter(_norm(row.get("rule_id")) for row in rows if _norm(row.get("rule_id")))
    return {
        "excluded_trade_count": len(rows),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "rule_counts": dict(sorted(rule_counts.items())),
        "examples": rows[:5],
    }


def _row_classifications(
    *,
    subject_id: str,
    blockers: Sequence[str],
    queue_row: dict[str, Any],
    robust_candidate: dict[str, Any],
    bullish_targets: dict[str, Any],
    lane_a_targets: dict[str, Any],
    lane_a_zero_bid: dict[str, Any],
) -> list[dict[str, Any]]:
    classifications: list[dict[str, Any]] = []

    if _has(blockers, "bullish_pullback_core:unpriced_candidates"):
        classifications.append(
            _classification(
                class_id="importable_missing_quote_candidate",
                label="Bullish-pullback unresolved exact exit quote targets",
                blockers=_matching_blockers(blockers, "bullish_pullback_core:unpriced_candidates"),
                permission="requires_explicit_approval_before_evidence_store_mutation",
                evidence=bullish_targets,
                recommendation=(
                    "Next worker may build a read-only import/query plan for these exact contract/date targets; actual quote import needs explicit approval."
                ),
            )
        )

    if _has(blockers, "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates"):
        evidence = dict(lane_a_targets)
        evidence["target_subset"] = "missing_exit_quote_for_leg"
        classifications.append(
            _classification(
                class_id="importable_missing_quote_candidate",
                label="Lane A missing exit quote targets",
                blockers=_matching_blockers(blockers, "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates"),
                permission="requires_explicit_approval_before_evidence_store_mutation",
                evidence=evidence,
                recommendation=(
                    "Next worker may separate exact missing quote targets from selection gaps; importing or replay-writing them needs explicit approval."
                ),
            )
        )
    if _safe_int(lane_a_targets.get("no_chain_native_spread_count")) and (
        subject_id == "lane:lane_a_chain_native_ret20_4_stop200_time75"
        or _has(blockers, "lane_a_chain_native_ret20_4_stop200_time75")
    ):
        classifications.append(
            _classification(
                class_id="no_chain_native_spread_selection_gap",
                label="Lane A signal rows without a chain-native spread under current filters",
                blockers=_matching_blockers(blockers, "lane_a_chain_native_ret20_4_stop200_time75:unpriced_candidates"),
                permission="requires_policy_change_approval",
                evidence={
                    "source_path": lane_a_targets.get("source_path"),
                    "no_chain_native_spread_count": lane_a_targets.get("no_chain_native_spread_count"),
                    "reason_counts": lane_a_targets.get("reason_counts"),
                },
                recommendation=(
                    "Only read-only diagnostics are allowed here; changing chain-native spread filters or backfill behavior is a policy change."
                ),
            )
        )

    if _has(blockers, "zero_bid"):
        classifications.append(
            _classification(
                class_id="observed_zero_bid_tradability_kill_candidate",
                label="Observed Lane A zero-bid/side-aware tradability failure",
                blockers=_matching_blockers(blockers, "zero_bid"),
                permission="requires_policy_change_approval",
                evidence=lane_a_zero_bid,
                recommendation=(
                    "Prepare a read-only kill/exclusion proposal if needed; do not edit source-quality policy or lane state without approval."
                ),
            )
        )

    exclusion_summary = _source_quality_exclusion_summary(robust_candidate)
    if exclusion_summary["excluded_trade_count"]:
        classifications.append(
            _classification(
                class_id="observed_zero_bid_tradability_kill_candidate",
                label="Existing CVX source-quality scope exclusions",
                blockers=["cvx_zero_bid_tradability_candidate_scope_v1"],
                permission="requires_policy_change_approval",
                evidence=exclusion_summary,
                recommendation=(
                    "Leave the active CVX candidate-scope exclusion unchanged unless Prime CEO explicitly approves policy work."
                ),
            )
        )

    if _has(blockers, "paper_shadow_fill_evidence_pending"):
        classifications.append(
            _classification(
                class_id="paper_shadow_evidence_gap",
                label="Paper-shadow fill evidence pending",
                blockers=_matching_blockers(blockers, "paper_shadow_fill_evidence_pending"),
                permission="not_actionable_without_forward_evidence",
                evidence={"source_quality_gate": _as_dict(robust_candidate.get("source_quality_gate")).get("status")},
                recommendation=(
                    "Historical artifacts cannot fill this gap; collect or review legitimate forward paper-shadow fill evidence only."
                ),
            )
        )

    statistical_blockers = _matching_blockers(
        blockers,
        "final_holdout",
        "validation_exact_trades_below_30",
        "rolling_oos_watch",
        "avg_not_above_baseline",
        "pf_not_above_baseline",
    )
    if statistical_blockers:
        classifications.append(
            _classification(
                class_id="pure_statistical_sample_blocker",
                label="Sample, PF lower-bound, baseline, or rolling-OOS blocker",
                blockers=statistical_blockers,
                permission="not_actionable_without_forward_evidence",
                evidence=_statistical_evidence(robust_candidate, queue_row),
                recommendation=(
                    "Do not promote or tune around this with protected holdout; wait for approved pre-holdout repair or future frozen-forward rows."
                ),
            )
        )

    if _has(blockers, "source_quality_gate:quality_pending"):
        classifications.append(
            _classification(
                class_id="source_quality_pending",
                label="Source-quality gate remains pending",
                blockers=_matching_blockers(blockers, "source_quality_gate:quality_pending"),
                permission="read_only_research_ok",
                evidence=_as_dict(robust_candidate.get("source_quality_gate")),
                recommendation=(
                    "Use this manifest to decide the next bounded read-only task; do not turn quality-pending rows into proof."
                ),
            )
        )

    return classifications


def _lane_a_zero_bid_summary(zero_bid_report: dict[str, Any], multilane_report: dict[str, Any]) -> dict[str, Any]:
    embedded = _as_dict(multilane_report.get("side_aware_zero_bid_replay"))
    source = _as_dict(zero_bid_report or embedded)
    modes = _as_dict(source.get("modes") or embedded.get("modes"))
    embedded_modes = _as_dict(embedded.get("modes"))
    conservative = _as_dict(modes.get("conservative"))
    embedded_conservative = _as_dict(embedded_modes.get("conservative"))
    side_aware_metrics = _as_dict(conservative.get("side_aware_metrics"))
    combined_metrics = _as_dict(conservative.get("combined_with_existing_lane_a_metrics"))
    zero_bid_priced_count = conservative.get("zero_bid_priced_count") or embedded_conservative.get("zero_bid_priced_count")
    combined_priced_count = conservative.get("combined_lane_a_priced_count") or embedded_conservative.get(
        "combined_lane_a_priced_count"
    )
    zero_bid_exit_rate_pct = conservative.get("zero_bid_exit_rate_pct") or embedded_conservative.get(
        "zero_bid_exit_rate_pct"
    )
    if zero_bid_exit_rate_pct is None and zero_bid_priced_count is not None and combined_priced_count:
        zero_bid_exit_rate_pct = round((_safe_float(zero_bid_priced_count) or 0.0) / combined_priced_count * 100.0, 2)
    return {
        "source_path": _rel(DEFAULT_LANE_A_ZERO_BID_REPORT),
        "generated_at_utc": source.get("generated_at_utc") or embedded.get("generated_at_utc"),
        "candidate_count": conservative.get("candidate_count"),
        "priced_count": conservative.get("priced_count"),
        "unpriced_count": conservative.get("unpriced_count"),
        "combined_lane_a_priced_count": combined_priced_count,
        "combined_lane_a_unpriced_count": conservative.get("combined_lane_a_unpriced_count"),
        "combined_lane_a_quote_coverage_pct": conservative.get("combined_lane_a_quote_coverage_pct"),
        "zero_bid_exit_rate_pct": zero_bid_exit_rate_pct,
        "zero_bid_priced_count": zero_bid_priced_count,
        "conservative_combined_profit_factor": combined_metrics.get("profit_factor"),
        "conservative_combined_avg_pnl_pct": combined_metrics.get("avg_pnl_pct"),
        "side_aware_profit_factor": side_aware_metrics.get("profit_factor"),
        "side_aware_avg_pnl_pct": side_aware_metrics.get("avg_pnl_pct"),
        "side_aware_trade_count": side_aware_metrics.get("trade_count"),
    }


def _permission_counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        for classification in _as_list(row.get("classifications")):
            permission = _norm(_as_dict(classification).get("action_permission"))
            if permission:
                counts[permission] += 1
    return {key: counts.get(key, 0) for key in ACTION_PERMISSIONS}


def build_manifest(
    *,
    walk_forward_report: dict[str, Any],
    robust_search_report: dict[str, Any],
    source_quality_policy: dict[str, Any],
    multilane_report: dict[str, Any],
    bullish_pullback_run: dict[str, Any],
    lane_a_run: dict[str, Any],
    lane_a_zero_bid_report: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    high_priority = _high_priority_rows(walk_forward_report)
    robust_by_id = _robust_candidate_by_id(robust_search_report)
    bullish_targets = summarize_unpriced_targets(
        bullish_pullback_run,
        source_path=DEFAULT_BULLISH_PULLBACK_RUN,
    )
    lane_a_targets = summarize_unpriced_targets(lane_a_run, source_path=DEFAULT_LANE_A_RUN)
    lane_a_zero_bid = _lane_a_zero_bid_summary(lane_a_zero_bid_report, multilane_report)
    rows: list[dict[str, Any]] = []

    for queue_row in high_priority:
        subject_id = str(queue_row.get("subject_id") or "")
        robust_candidate = robust_by_id.get(subject_id, {})
        blockers = [str(item) for item in _as_list(queue_row.get("blockers") or robust_candidate.get("blockers"))]
        classifications = _row_classifications(
            subject_id=subject_id,
            blockers=blockers,
            queue_row=queue_row,
            robust_candidate=robust_candidate,
            bullish_targets=bullish_targets,
            lane_a_targets=lane_a_targets,
            lane_a_zero_bid=lane_a_zero_bid,
        )
        rows.append(
            {
                "subject_id": subject_id,
                "priority_rank": queue_row.get("priority_rank"),
                "priority_band": queue_row.get("priority_band"),
                "source_queue_category": queue_row.get("category"),
                "source_queue_action": queue_row.get("action"),
                "source_queue_permission": queue_row.get("execution_permission"),
                "status": robust_candidate.get("status") or "unknown",
                "historical_nomination_ready": bool(robust_candidate.get("historical_nomination_ready")),
                "metrics": _as_dict(queue_row.get("metrics")),
                "blockers": blockers,
                "classifications": classifications,
            }
        )

    permission_counts = _permission_counts(rows)
    classification_counts = Counter(
        _as_dict(classification).get("class_id")
        for row in rows
        for classification in _as_list(row.get("classifications"))
    )
    robust_summary = _as_dict(robust_search_report.get("summary"))
    walk_summary = _as_dict(walk_forward_report.get("summary"))
    source_quality_gate = _as_dict(multilane_report.get("quality_gate"))
    status = "blocked_non_promotable_observe_only"
    if not rows:
        status = "blocked_missing_high_priority_rows"

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_historical_robust_candidate_source_quality_manifest",
        "read_only": True,
        "live_policy_change": False,
        "promotion_ready": False,
        "proof_claim": False,
        "inputs": {
            "walk_forward_report": _rel(DEFAULT_WALK_FORWARD_REPORT),
            "robust_search_report": _rel(DEFAULT_ROBUST_SEARCH_REPORT),
            "source_quality_policy": _rel(DEFAULT_SOURCE_QUALITY_POLICY),
            "cvx_executable_coverage_doc": _rel(DEFAULT_CVX_COVERAGE_DOC),
            "multilane_report": _rel(DEFAULT_MULTILANE_REPORT),
            "bullish_pullback_run": _rel(DEFAULT_BULLISH_PULLBACK_RUN),
            "lane_a_run": _rel(DEFAULT_LANE_A_RUN),
            "lane_a_zero_bid_report": _rel(DEFAULT_LANE_A_ZERO_BID_REPORT),
        },
        "summary": {
            "overall_status": status,
            "high_priority_row_count": len(rows),
            "expected_high_priority_row_ids": list(ROW_IDS),
            "observed_high_priority_row_ids": [row["subject_id"] for row in rows],
            "walk_forward_status": walk_forward_report.get("status"),
            "robust_search_status": robust_search_report.get("status"),
            "accepted_exact_trade_count": robust_summary.get("accepted_exact_trade_count"),
            "ready_candidate_count": robust_summary.get("ready_candidate_count"),
            "candidate_count": robust_summary.get("candidate_count"),
            "selection_adjusted_bar": robust_summary.get("selection_adjusted_bar"),
            "source_quality_gate_status": robust_summary.get("source_quality_gate_status")
            or source_quality_gate.get("overall_status"),
            "source_quality_scope_policy_status": _norm(source_quality_policy.get("status")) or None,
            "source_quality_scope_excluded_trade_count": robust_summary.get("source_quality_scope_excluded_trade_count"),
            "final_holdout_minimum": 30,
            "combined_final_holdout_exact_trade_count": _as_dict(
                _as_dict(robust_by_id.get("combined_portfolio", {})).get("split_metrics")
            )
            .get("final_holdout", {})
            .get("exact_trade_count"),
            "combined_final_holdout_pf_lb_5pct": _as_dict(
                _as_dict(
                    _as_dict(robust_by_id.get("combined_portfolio", {})).get("split_metrics")
                ).get("final_holdout", {})
                .get("bootstrap")
            ).get("pf_lb_5pct"),
            "protected_forward_holdout_start_date": walk_summary.get("protected_forward_holdout_start_date"),
            "protected_forward_holdout_overlap": walk_summary.get("protected_forward_holdout_overlap"),
            "classification_counts": dict(sorted((str(key), value) for key, value in classification_counts.items() if key)),
            "permission_counts": permission_counts,
        },
        "target_level_classifications": {
            "bullish_pullback_unpriced_targets": bullish_targets,
            "lane_a_unpriced_targets": lane_a_targets,
            "lane_a_zero_bid_tradability": lane_a_zero_bid,
            "cvx_scope_policy": {
                "policy_status": source_quality_policy.get("status"),
                "rules": _as_list(source_quality_policy.get("rules")),
                "source_doc": _rel(DEFAULT_CVX_COVERAGE_DOC),
            },
        },
        "rows": rows,
        "action_permissions": ACTION_PERMISSIONS,
        "next_worker_recommendations": [
            {
                "task": "Build a read-only exact target plan for the bullish-pullback 3 and Lane A missing-exit quote groups.",
                "permission": "read_only_research_ok",
                "requires_before_write": "requires_explicit_approval_before_evidence_store_mutation",
            },
            {
                "task": "Separate Lane A no-chain-native-spread rows from missing-quote rows and decide whether they are policy-change candidates or dead diagnostics.",
                "permission": "read_only_research_ok",
                "requires_before_write": "requires_policy_change_approval",
            },
            {
                "task": "Prepare a read-only zero-bid kill/exclusion proposal for Lane A if Prime CEO wants one; leave the active CVX scope policy unchanged.",
                "permission": "read_only_research_ok",
                "requires_before_write": "requires_policy_change_approval",
            },
            {
                "task": "Treat paper-shadow evidence and sample-size/PF-LB blockers as not actionable from historical rows alone.",
                "permission": "not_actionable_without_forward_evidence",
                "requires_before_write": "fresh post-freeze forward exact evidence or separately approved pre-holdout repair",
            },
        ],
        "proof_gate_status": {
            "current_status": "blocked_non_promotable_observe_only",
            "historical_rows_are_forward_proof": False,
            "live_validation_allowed": False,
            "promotion_allowed": False,
            "protected_holdout_consumed": False,
        },
        "prohibited_commands": list(PROHIBITED_COMMANDS),
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    proof_status = _as_dict(report.get("proof_gate_status"))
    lines = [
        "# Regular Options Robust Candidate Source-Quality Manifest",
        "",
        "This report is generated from `scripts/build_regular_options_robust_candidate_source_quality_manifest.py`. It classifies the current high-priority `candidate_source_quality_repair` blockers from the regular-options historical walk-forward workflow. It is read-only and does not import quotes, mutate evidence stores, edit source-quality policy, change scanner or proof rules, consume protected holdout, or claim production proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- High-priority rows: `{summary.get('high_priority_row_count')}` (`{', '.join(str(item) for item in _as_list(summary.get('observed_high_priority_row_ids')))}`).",
        f"- Walk-forward status: `{summary.get('walk_forward_status')}`.",
        f"- Robust-search status: `{summary.get('robust_search_status')}`; ready candidates `{summary.get('ready_candidate_count')}` / `{summary.get('candidate_count')}`.",
        f"- Accepted exact trades: `{summary.get('accepted_exact_trade_count')}`.",
        f"- Source-quality gate: `{summary.get('source_quality_gate_status')}`; scope-policy exclusions `{summary.get('source_quality_scope_excluded_trade_count')}`.",
        f"- Combined final holdout: `N={summary.get('combined_final_holdout_exact_trade_count')}`, PF-LB `{summary.get('combined_final_holdout_pf_lb_5pct')}`, selection-adjusted bar `{summary.get('selection_adjusted_bar')}`.",
        f"- Protected holdout starts `{summary.get('protected_forward_holdout_start_date')}`; overlap `{summary.get('protected_forward_holdout_overlap')}`.",
        f"- Proof/gate status: `{proof_status.get('current_status')}`; promotion allowed `{proof_status.get('promotion_allowed')}`.",
        "",
        "## Row Classifications",
        "",
        "| Row | Priority | Classes | Key Metrics | Permission Summary |",
        "|---|---|---|---|---|",
    ]
    for row in _as_list(report.get("rows")):
        row = _as_dict(row)
        metrics = _as_dict(row.get("metrics"))
        classes = ", ".join(f"`{_cell(_as_dict(item).get('class_id'))}`" for item in _as_list(row.get("classifications")))
        permissions = ", ".join(
            sorted(
                {
                    str(_as_dict(item).get("action_permission"))
                    for item in _as_list(row.get("classifications"))
                    if _as_dict(item).get("action_permission")
                }
            )
        )
        metric_text = (
            f"total N {metrics.get('combined_exact_trade_count')}; "
            f"holdout N {metrics.get('final_holdout_exact_trade_count')}; "
            f"holdout PF {metrics.get('final_holdout_profit_factor')}; "
            f"PF-LB {metrics.get('final_holdout_pf_lb_5pct')}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('subject_id'))}`",
                    f"`{_cell(row.get('priority_band'))}`",
                    classes,
                    _cell(metric_text),
                    _cell(permissions),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Target-Level Readback", ""])
    targets = _as_dict(report.get("target_level_classifications"))
    bullish = _as_dict(targets.get("bullish_pullback_unpriced_targets"))
    lane_a = _as_dict(targets.get("lane_a_unpriced_targets"))
    zero_bid = _as_dict(targets.get("lane_a_zero_bid_tradability"))
    lines.extend(
        [
            f"- Bullish-pullback unpriced targets: `{bullish.get('unpriced_count')}` total, `{bullish.get('missing_quote_count')}` missing-quote rows, reasons `{bullish.get('reason_counts')}`, tickers `{bullish.get('ticker_counts')}`.",
            f"- Lane A unpriced targets: `{lane_a.get('unpriced_count')}` total, `{lane_a.get('missing_quote_count')}` missing-quote rows, `{lane_a.get('no_chain_native_spread_count')}` no-chain-native-spread rows, coverage `{lane_a.get('quote_coverage_pct')}`%.",
            f"- Lane A zero-bid: conservative combined PF `{zero_bid.get('conservative_combined_profit_factor')}`, zero-bid exit rate `{zero_bid.get('zero_bid_exit_rate_pct')}`%, combined unpriced `{zero_bid.get('combined_lane_a_unpriced_count')}`, side-aware PF `{zero_bid.get('side_aware_profit_factor')}`.",
            "- CVX zero-bid/tradability: active source-quality scope policy excludes matching CVX bullish-pullback rows; changing that rule requires policy approval.",
        ]
    )

    lines.extend(["", "## Action Permissions", ""])
    for key, description in _as_dict(report.get("action_permissions")).items():
        lines.append(f"- `{key}`: {description}")

    lines.extend(["", "## Next Worker Recommendations", ""])
    for item in _as_list(report.get("next_worker_recommendations")):
        item = _as_dict(item)
        lines.append(
            f"- {item.get('task')} Permission: `{item.get('permission')}`; before write: `{item.get('requires_before_write')}`."
        )

    lines.extend(["", "## Prohibited Commands", ""])
    for command in _as_list(report.get("prohibited_commands")):
        lines.append(f"- {command}")

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Current status remains blocked, non-promotable, and observe-only. This manifest is a source-quality triage surface for Prime CEO task selection, not a quote import plan, source-quality policy change, scanner change, proof-bar change, broker instruction, or production proof claim.",
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


def run_manifest(
    *,
    write: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    walk_forward_report_path: Path = DEFAULT_WALK_FORWARD_REPORT,
    robust_search_report_path: Path = DEFAULT_ROBUST_SEARCH_REPORT,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
    multilane_report_path: Path = DEFAULT_MULTILANE_REPORT,
    bullish_pullback_run_path: Path = DEFAULT_BULLISH_PULLBACK_RUN,
    lane_a_run_path: Path = DEFAULT_LANE_A_RUN,
    lane_a_zero_bid_report_path: Path = DEFAULT_LANE_A_ZERO_BID_REPORT,
) -> dict[str, Any]:
    report = build_manifest(
        walk_forward_report=_load_json(walk_forward_report_path),
        robust_search_report=_load_json(robust_search_report_path),
        source_quality_policy=_load_json(source_quality_policy_path),
        multilane_report=_load_json(multilane_report_path),
        bullish_pullback_run=_load_json(bullish_pullback_run_path),
        lane_a_run=_load_json(lane_a_run_path),
        lane_a_zero_bid_report=_load_json(lane_a_zero_bid_report_path),
    )
    if write:
        write_outputs(report, output_dir=output_dir, docs_report=docs_report)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the read-only robust-candidate source-quality manifest for regular options."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--walk-forward-report", type=Path, default=DEFAULT_WALK_FORWARD_REPORT)
    parser.add_argument("--robust-search-report", type=Path, default=DEFAULT_ROBUST_SEARCH_REPORT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--multilane-report", type=Path, default=DEFAULT_MULTILANE_REPORT)
    parser.add_argument("--bullish-pullback-run", type=Path, default=DEFAULT_BULLISH_PULLBACK_RUN)
    parser.add_argument("--lane-a-run", type=Path, default=DEFAULT_LANE_A_RUN)
    parser.add_argument("--lane-a-zero-bid-report", type=Path, default=DEFAULT_LANE_A_ZERO_BID_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = run_manifest(
        write=not args.no_write,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        walk_forward_report_path=args.walk_forward_report,
        robust_search_report_path=args.robust_search_report,
        source_quality_policy_path=args.source_quality_policy,
        multilane_report_path=args.multilane_report,
        bullish_pullback_run_path=args.bullish_pullback_run,
        lane_a_run_path=args.lane_a_run,
        lane_a_zero_bid_report_path=args.lane_a_zero_bid_report,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
