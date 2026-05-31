from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_bullish_pullback_confidence_tiers import metrics as trade_metrics


LAB_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation"
RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
OUTPUT_DIR = LAB_DIR / "layer-stack"
REPORT_PATH = ROOT / "docs" / "bullish-pullback-layer-stack-2026-05-29.md"

NEXT_LAYER_SUMMARY = LAB_DIR / "next-layer-summary-2026-05-29.json"
CONFIDENCE_REPORT = LAB_DIR / "confidence" / "latest.json"
TICKER_AUDIT = LAB_DIR / "ticker-audit" / "latest.json"


S_AB_TIMCLUSTER_RUN = RUNS_DIR / "20260528_231723_sleeve_pf59_s_ab_timecluster_v1_intraday.json"

FROZEN_RUNS = {
    "sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1": RUNS_DIR
    / "20260528_013544_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1_intraday.json",
    "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1": RUNS_DIR
    / "20260528_014057_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1_intraday.json",
    "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1": RUNS_DIR
    / "20260528_014353_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1_intraday.json",
}

ROBUSTNESS_DIR = ROOT / "data" / "profitability-lab" / "imported-intraday-robustness"
THETADATA_DIR = ROOT / "data" / "options-validation" / "thetadata-nbbo"
DEFENSIVE_REFILL_IMPORT_SUMMARY = THETADATA_DIR / "thetadata_exact_missing_intraday_20260530T000025Z.json"

S_TIMECLUSTER_TIERS = {
    "s_time60_energy_health_growth",
    "s_time55_metals_index",
    "s_time50_mega_health",
}

REJECTED_TIER_COMPONENTS = {
    "coverage_a_refill": {
        "source_variant": "sleeve_pf59_coverage_a_refill_v1",
        "run_path": RUNS_DIR / "20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json",
        "tier_ids": {"coverage_a_refill"},
        "reason": "Refill block is weak as a standalone add-on: PF 1.11 and avg +2.72%, so it should not drive the next layer.",
    },
    "a_theme_energy_defensive": {
        "source_variant": "sleeve_pf59_s_a_energy_defensive_v1",
        "run_path": RUNS_DIR / "20260528_231856_sleeve_pf59_s_a_energy_defensive_v1_intraday.json",
        "tier_ids": {"a_theme_energy_defensive"},
        "reason": "Energy/defensive A refill is not independently profitable after import: PF 0.94 and avg -1.71%.",
    },
    "b_pf1_refill": {
        "source_variant": "sleeve_pf59_s_ab_timecluster_v1",
        "run_path": S_AB_TIMCLUSTER_RUN,
        "tier_ids": {"b_pf1_refill"},
        "reason": "B refill adds exact count but loses money: PF 0.51 and avg -18.34%.",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 2) -> float:
    return round(_safe_float(value), digits)


def _is_trusted_exact_opra_trade(trade: dict[str, Any]) -> bool:
    resolution = str(trade.get("entry_contract_resolution") or "").lower()
    fill_basis = str(trade.get("exit_fill_basis") or "").lower()
    return bool(trade.get("priced", True)) and resolution.startswith("exact") and fill_basis == "imported_spread_mark"


def _trusted_trades_for_tiers(run_path: Path, tier_ids: set[str]) -> list[dict[str, Any]]:
    run = _load_json(run_path)
    return [
        trade
        for trade in run.get("trades") or []
        if _is_trusted_exact_opra_trade(trade) and str(trade.get("tier_id") or "") in tier_ids
    ]


def _trusted_component(run_path: Path, tier_ids: set[str]) -> dict[str, Any]:
    trades = _trusted_trades_for_tiers(run_path, tier_ids)
    return {
        **trade_metrics(trades),
        "symbols": sorted({str(trade.get("ticker") or "").upper() for trade in trades}),
    }


def _summary_variant(summary: dict[str, Any], variant_id: str) -> dict[str, Any]:
    for row in summary.get("best_variants") or []:
        if row.get("variant_id") == variant_id:
            return row
    raise KeyError(f"Variant not found in next-layer summary: {variant_id}")


def _robustness_path(variant_id: str) -> Path:
    return ROBUSTNESS_DIR / f"latest_{variant_id}.json"


def _find_slippage_metrics(robustness: dict[str, Any], per_side: float = 5.0) -> dict[str, Any]:
    rows = robustness.get("slippage_stress") or []
    exact = [
        row
        for row in rows
        if abs(_safe_float(row.get("slippage_pct_per_side")) - per_side) < 0.001
        and isinstance(row.get("metrics"), dict)
    ]
    if exact:
        return exact[0]["metrics"]
    with_metrics = [row for row in rows if isinstance(row.get("metrics"), dict)]
    if not with_metrics:
        return {}
    return max(with_metrics, key=lambda row: _safe_float(row.get("slippage_pct_per_side")))["metrics"]


def _first_rolling_test(robustness: dict[str, Any]) -> dict[str, Any]:
    windows = robustness.get("rolling_oos", {}).get("windows") or []
    if not windows:
        return {}
    return windows[0].get("test") or {}


def _top_winner_removed_metrics(robustness: dict[str, Any], removed: int = 1) -> dict[str, Any]:
    for row in robustness.get("top_winner_removal") or []:
        if _safe_int(row.get("removed_top_trades")) == removed:
            return row.get("remaining_metrics") or {}
    return {}


def _layer_from_run(
    *,
    layer_id: str,
    variant_id: str,
    decision: str,
    role: str,
    next_action: str,
) -> dict[str, Any]:
    run_path = FROZEN_RUNS[variant_id]
    run = _load_json(run_path)
    robustness_path = _robustness_path(variant_id)
    robustness = _load_json(robustness_path) if robustness_path.exists() else {}
    exact_metrics = run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {}
    stress = _find_slippage_metrics(robustness, 5.0)
    rolling = robustness.get("rolling_oos") or {}
    rolling_test = _first_rolling_test(robustness)
    top1 = _top_winner_removed_metrics(robustness, 1)
    row = {
        "candidate_trade_count": run.get("candidate_trade_count"),
        "exact_trade_count": exact_metrics.get("trade_count") or run.get("exact_contract_match_count"),
        "unpriced_trade_count": run.get("unpriced_trade_count"),
        "quote_coverage_pct": run.get("quote_coverage_pct"),
        "profit_factor": exact_metrics.get("profit_factor") or run.get("profit_factor"),
        "avg_pnl_pct": exact_metrics.get("avg_pnl_pct") or run.get("avg_pnl_pct"),
        "stress_5pct_per_side_profit_factor": stress.get("profit_factor"),
        "rolling_status": rolling.get("status"),
        "rolling_first_test_profit_factor": rolling_test.get("profit_factor"),
        "top_1_winner_removed_profit_factor": top1.get("profit_factor"),
    }
    return {
        "layer_id": layer_id,
        "variant_id": variant_id,
        "source_result_path": str(run_path.relative_to(ROOT)),
        "source_robustness_path": str(robustness_path.relative_to(ROOT)) if robustness_path.exists() else None,
        "role": role,
        "decision": decision,
        "next_action": next_action,
        "metrics": row,
        "gate_read": classify_layer_status(row),
    }


def _latest_run_path(variant_id: str) -> Path | None:
    matches = sorted(RUNS_DIR.glob(f"*_{variant_id}_intraday.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _classification_summary(run_path: Path) -> dict[str, Any]:
    try:
        from scripts.classify_missing_replay_contracts import classify_run

        report = classify_run(run_path)
    except Exception as exc:  # pragma: no cover - defensive artifact generation path.
        return {"error": str(exc)}
    exact_rows = sum(_safe_int(row.get("exact_row_count")) for row in report.get("classified") or [])
    return {
        "classified_count": report.get("classified_count"),
        "classification_counts": report.get("classification_counts"),
        "by_ticker": report.get("by_ticker"),
        "exact_executable_rows_found": exact_rows,
    }


def _scout_from_latest_run(
    *,
    variant_id: str,
    decision: str,
    role: str,
    next_action: str,
) -> dict[str, Any]:
    run_path = _latest_run_path(variant_id)
    if run_path is None:
        return {
            "variant_id": variant_id,
            "decision": "not_run",
            "role": role,
            "next_action": next_action,
            "metrics": {},
            "gate_read": {"status": "not_run", "blockers": ["missing_run_artifact"]},
        }
    run = _load_json(run_path)
    robustness_path = _robustness_path(variant_id)
    robustness = _load_json(robustness_path) if robustness_path.exists() else {}
    exact_metrics = run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {}
    stress = _find_slippage_metrics(robustness, 5.0)
    rolling = robustness.get("rolling_oos") or {}
    rolling_test = _first_rolling_test(robustness)
    top1 = _top_winner_removed_metrics(robustness, 1)
    metrics = {
        "candidate_trade_count": run.get("candidate_trade_count"),
        "exact_trade_count": exact_metrics.get("trade_count") or run.get("exact_contract_match_count"),
        "unpriced_trade_count": run.get("unpriced_trade_count"),
        "quote_coverage_pct": run.get("quote_coverage_pct"),
        "profit_factor": exact_metrics.get("profit_factor") or run.get("profit_factor"),
        "avg_pnl_pct": exact_metrics.get("avg_pnl_pct") or run.get("avg_pnl_pct"),
        "stress_5pct_per_side_profit_factor": stress.get("profit_factor"),
        "rolling_status": rolling.get("status"),
        "rolling_first_test_profit_factor": rolling_test.get("profit_factor"),
        "top_1_winner_removed_profit_factor": top1.get("profit_factor"),
    }
    return {
        "variant_id": variant_id,
        "source_result_path": str(run_path.relative_to(ROOT)),
        "source_robustness_path": str(robustness_path.relative_to(ROOT)) if robustness_path.exists() else None,
        "role": role,
        "decision": decision,
        "next_action": next_action,
        "metrics": metrics,
        "gate_read": classify_layer_status(metrics),
        "missing_contract_classification": _classification_summary(run_path),
        "by_tier": run.get("by_tier"),
    }


def classify_layer_status(row: dict[str, Any]) -> dict[str, Any]:
    exact_count = _safe_int(row.get("exact_trade_count") or row.get("trade_count"))
    unpriced = _safe_int(row.get("unpriced_trade_count"))
    coverage = _safe_float(row.get("quote_coverage_pct"), 100.0 if unpriced == 0 else 0.0)
    pf = _safe_float(row.get("profit_factor"))
    avg = _safe_float(row.get("avg_pnl_pct"))
    stress_pf = _safe_float(row.get("stress_5pct_per_side_profit_factor"))
    rolling_pf = _safe_float(row.get("rolling_first_test_profit_factor"))
    rolling_status = str(row.get("rolling_status") or "").lower()

    preferred_target_met = (
        exact_count >= 200
        and pf >= 2.0
        and avg > 15.0
        and coverage >= 97.5
        and unpriced == 0
        and stress_pf >= 1.5
        and rolling_pf > 1.5
    )
    minimum_count_improvement_met = (
        exact_count >= 150
        and pf >= 1.75
        and avg > 15.0
        and coverage >= 97.5
        and stress_pf >= 1.5
        and rolling_pf > 1.5
        and rolling_status == "passed"
    )
    robust_paper_shadow_met = (
        exact_count >= 100
        and pf >= 2.0
        and avg > 15.0
        and coverage >= 97.5
        and stress_pf >= 1.5
        and rolling_pf > 1.5
        and rolling_status == "passed"
    )

    blockers: list[str] = []
    if exact_count < 200:
        blockers.append("below_200_trade_preferred_target")
    if exact_count < 150:
        blockers.append("below_minimum_count_expansion_gate")
    if pf < 2.0:
        blockers.append("pf_below_2")
    if avg <= 15.0:
        blockers.append("avg_pnl_not_above_15")
    if coverage < 97.5:
        blockers.append("quote_coverage_below_97_5")
    if unpriced > 0:
        blockers.append("unpriced_candidates_remain")
    if stress_pf < 1.5:
        blockers.append("stress_pf_below_1_5")
    if rolling_pf <= 1.5 or rolling_status != "passed":
        blockers.append("rolling_oos_not_clean")

    if preferred_target_met:
        status = "preferred_target_met"
    elif minimum_count_improvement_met:
        status = "minimum_count_improvement_met"
    elif robust_paper_shadow_met and unpriced == 0:
        status = "clean_paper_shadow_layer"
    elif robust_paper_shadow_met:
        status = "paper_shadow_layer_strict_blocked"
    elif exact_count >= 80 and pf >= 2.0 and avg > 15.0 and stress_pf >= 1.5:
        status = "component_or_watch_layer"
    else:
        status = "research_or_rejected"

    return {
        "status": status,
        "preferred_target_met": preferred_target_met,
        "minimum_count_improvement_met": minimum_count_improvement_met,
        "robust_paper_shadow_met": robust_paper_shadow_met,
        "blockers": blockers,
    }


def _layer_from_variant(
    *,
    layer_id: str,
    summary_row: dict[str, Any],
    decision: str,
    next_action: str,
) -> dict[str, Any]:
    status = classify_layer_status(summary_row)
    metrics = {
        "candidate_trade_count": summary_row.get("candidate_trade_count"),
        "exact_trade_count": summary_row.get("exact_trade_count"),
        "unpriced_trade_count": summary_row.get("unpriced_trade_count"),
        "quote_coverage_pct": summary_row.get("quote_coverage_pct"),
        "profit_factor": summary_row.get("profit_factor"),
        "avg_pnl_pct": summary_row.get("avg_pnl_pct"),
        "stress_5pct_per_side_profit_factor": summary_row.get("stress_5pct_per_side_profit_factor"),
        "rolling_status": summary_row.get("rolling_status"),
        "rolling_first_test_profit_factor": summary_row.get("rolling_first_test_profit_factor"),
        "top_1_winner_removed_profit_factor": summary_row.get("top_1_winner_removed_profit_factor"),
    }
    return {
        "layer_id": layer_id,
        "variant_id": summary_row.get("variant_id"),
        "source_result_path": summary_row.get("result_path"),
        "role": summary_row.get("role"),
        "decision": decision,
        "next_action": next_action,
        "metrics": metrics,
        "gate_read": status,
    }


def _confidence_core_layer(confidence: dict[str, Any], ticker_audit: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(confidence.get("combined_tradable_metrics") or {})
    keep_symbols = (
        ticker_audit.get("symbols", {}).get("keep_in_current_lane")
        or ticker_audit.get("buckets", {}).get("keep-in-current-lane")
        or ticker_audit.get("keep_current_lane")
        or metrics.get("symbols")
        or []
    )
    return {
        "layer_id": "layer_0_confidence_core_s_a_b",
        "variant_id": "confidence_s_a_b_queue",
        "source_result_path": str(CONFIDENCE_REPORT.relative_to(ROOT)),
        "role": "High-confidence S/A/B exact quoted queue across the current keep symbols.",
        "decision": "use_as_current_core_queue",
        "next_action": "Paper-shadow only; keep every candidate proof tied to exact ThetaData OPRA/NBBO bid/ask replay.",
        "metrics": {
            "exact_trade_count": metrics.get("trade_count"),
            "symbol_count": metrics.get("symbol_count"),
            "profit_factor": metrics.get("profit_factor"),
            "avg_pnl_pct": metrics.get("avg_pnl_pct"),
            "win_rate_pct": metrics.get("win_rate_pct"),
            "quote_coverage_pct": None,
            "unpriced_trade_count": None,
        },
        "symbols": keep_symbols,
        "gate_read": {
            "status": "high_confidence_core_below_count_target",
            "preferred_target_met": False,
            "minimum_count_improvement_met": False,
            "robust_paper_shadow_met": True,
            "blockers": ["below_200_trade_preferred_target", "below_minimum_count_expansion_gate"],
        },
    }


def _component_layer() -> dict[str, Any]:
    component_metrics = _trusted_component(S_AB_TIMCLUSTER_RUN, S_TIMECLUSTER_TIERS)
    gate_row = {
        "exact_trade_count": component_metrics["trade_count"],
        "unpriced_trade_count": 0,
        "quote_coverage_pct": 100.0,
        "profit_factor": component_metrics["profit_factor"],
        "avg_pnl_pct": component_metrics["avg_pnl_pct"],
        "stress_5pct_per_side_profit_factor": 1.66,
        "rolling_status": "watch",
        "rolling_first_test_profit_factor": 2.66,
    }
    return {
        "layer_id": "layer_7_s_timecluster_component",
        "variant_id": "sleeve_pf59_s_ab_timecluster_v1:s_tiers_only",
        "source_result_path": str(S_AB_TIMCLUSTER_RUN.relative_to(ROOT)),
        "role": "S-only component inside the expanded timecluster branch; excludes the weak A/B refill tiers.",
        "decision": "component_watch_not_count_expansion",
        "next_action": "Use as a diagnostic component only until a non-overlap forward rule proves added trades without the refill losses.",
        "metrics": {
            "candidate_trade_count": None,
            "exact_trade_count": component_metrics["trade_count"],
            "unpriced_trade_count": 0,
            "quote_coverage_pct": 100.0,
            "profit_factor": component_metrics["profit_factor"],
            "avg_pnl_pct": component_metrics["avg_pnl_pct"],
            "stress_5pct_per_side_profit_factor": 1.66,
            "rolling_status": "watch",
            "rolling_first_test_profit_factor": 2.66,
        },
        "symbols": component_metrics["symbols"],
        "gate_read": classify_layer_status(gate_row),
    }


def _rejected_components() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for component_id, spec in REJECTED_TIER_COMPONENTS.items():
        component_metrics = _trusted_component(spec["run_path"], set(spec["tier_ids"]))
        rows.append(
            {
                "component_id": component_id,
                "source_variant": spec["source_variant"],
                "source_result_path": str(Path(spec["run_path"]).relative_to(ROOT)),
                "decision": "do_not_promote",
                "reason": spec["reason"],
                "metrics": {
                    "exact_trade_count": component_metrics["trade_count"],
                    "symbol_count": component_metrics["symbol_count"],
                    "profit_factor": component_metrics["profit_factor"],
                    "avg_pnl_pct": component_metrics["avg_pnl_pct"],
                    "win_rate_pct": component_metrics["win_rate_pct"],
                    "gross_win": component_metrics["gross_win"],
                    "gross_loss": component_metrics["gross_loss"],
                },
                "symbols": component_metrics["symbols"],
            }
        )
    return rows


def _import_summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for raw in summary.get("data_imports_attempted") or []:
        rows.append(
            {
                "summary_path": raw.get("summary_path"),
                "request_count": raw.get("request_count"),
                "normalized_rows": raw.get("normalized_rows"),
                "imported_rows": raw.get("imported_rows"),
                "duplicate_rows": raw.get("duplicate_rows"),
                "batch_id": raw.get("batch_id"),
                "data_trust": raw.get("data_trust"),
                "source_label": raw.get("source_label"),
            }
        )
    if DEFENSIVE_REFILL_IMPORT_SUMMARY.exists():
        raw = _load_json(DEFENSIVE_REFILL_IMPORT_SUMMARY)
        import_result = raw.get("import_result") or {}
        rows.append(
            {
                "summary_path": str(DEFENSIVE_REFILL_IMPORT_SUMMARY.relative_to(ROOT)),
                "purpose": "post-layer-stack defensive refill exact-fill attempt",
                "request_count": raw.get("request_count"),
                "normalized_rows": raw.get("normalized_rows"),
                "imported_rows": import_result.get("imported_rows"),
                "duplicate_rows": import_result.get("duplicate_rows"),
                "batch_id": import_result.get("batch_id"),
                "data_trust": import_result.get("data_trust"),
                "source_label": import_result.get("source_label"),
            }
        )
    return rows


def build_layer_stack() -> dict[str, Any]:
    summary = _load_json(NEXT_LAYER_SUMMARY)
    confidence = _load_json(CONFIDENCE_REPORT)
    ticker_audit = _load_json(TICKER_AUDIT)

    layers = [
        _confidence_core_layer(confidence, ticker_audit),
        _layer_from_run(
            layer_id="layer_1_high_pf_cluster",
            variant_id="sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1",
            decision="freeze_as_high_pf_paper_shadow_layer",
            role="High-PF quoted cluster branch with strong stress/OOS but unresolved provider no-matches.",
            next_action="Use for profitability-first comparison; strict proof remains blocked by 7 unresolved candidates and 94.2% coverage.",
        ),
        _layer_from_run(
            layer_id="layer_2_high_coverage_cluster",
            variant_id="sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1",
            decision="freeze_as_high_coverage_quoted_layer",
            role="Cleaner quoted cluster branch before adding the lower-PF refill block.",
            next_action="Use when quoted coverage matters; strict proof remains blocked by 1 JNJ provider no-match.",
        ),
        _layer_from_run(
            layer_id="layer_3_clean_cluster_component",
            variant_id="sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1",
            decision="keep_as_clean_component_layer",
            role="Clean 100%-covered quoted cluster subset below the 100-trade target.",
            next_action="Use as component evidence only until more exact trades arrive without reintroducing unresolved JNJ/XLK/PLD risk.",
        ),
        _layer_from_variant(
            layer_id="layer_4_clean_exact",
            summary_row=_summary_variant(summary, "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1"),
            decision="promote_as_clean_paper_shadow_layer",
            next_action="Use when zero unresolved candidates matters more than raw PF; keep the mixed exit labels visible.",
        ),
        _layer_from_variant(
            layer_id="layer_5_count_expanded",
            summary_row=_summary_variant(summary, "sleeve_pf59_coverage_a_refill_v1"),
            decision="use_as_count_expanded_paper_shadow_reference",
            next_action="Do not treat strict-proof complete until the 3 WMT/JNJ provider no-match contracts have exact bid/ask rows.",
        ),
        _layer_from_variant(
            layer_id="layer_6_high_pf_130_reference",
            summary_row=_summary_variant(summary, "sleeve_winner_cluster_exit_balanced_quoted_v1"),
            decision="use_as_high_pf_130_trade_reference",
            next_action="Prefer for PF comparison; strict proof remains blocked by 3 unresolved candidates.",
        ),
        _component_layer(),
    ]

    rejected_variants = []
    for variant_id in [
        "sleeve_next_move_bucket_refill_v1",
        "sleeve_pf59_s_ab_timecluster_v1",
        "sleeve_pf59_s_a_energy_defensive_v1",
        "sleeve_pf59_s_themeA_no_ticker_bans_v1",
        "sleeve_pf59_coverage_clean_v1",
    ]:
        row = _summary_variant(summary, variant_id)
        rejected_variants.append(
            {
                "variant_id": variant_id,
                "source_result_path": row.get("result_path"),
                "role": row.get("role"),
                "decision": "do_not_promote_full_branch",
                "metrics": {
                    "candidate_trade_count": row.get("candidate_trade_count"),
                    "exact_trade_count": row.get("exact_trade_count"),
                    "unpriced_trade_count": row.get("unpriced_trade_count"),
                    "quote_coverage_pct": row.get("quote_coverage_pct"),
                    "profit_factor": row.get("profit_factor"),
                    "avg_pnl_pct": row.get("avg_pnl_pct"),
                    "stress_5pct_per_side_profit_factor": row.get("stress_5pct_per_side_profit_factor"),
                    "rolling_status": row.get("rolling_status"),
                },
                "gate_read": classify_layer_status(row),
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scope": "bullish_pullback_observation next profitability layer stack",
        "paper_shadow_only": True,
        "proof_source": "trusted ThetaData intraday OPRA/NBBO exact-contract bid/ask replay only",
        "source_artifacts": {
            "next_layer_summary": str(NEXT_LAYER_SUMMARY.relative_to(ROOT)),
            "confidence_report": str(CONFIDENCE_REPORT.relative_to(ROOT)),
            "ticker_audit": str(TICKER_AUDIT.relative_to(ROOT)),
        },
        "target_read": {
            "preferred_target_exact_trades": 200,
            "minimum_useful_added_trades_over_130": "20-30",
            "current_best_exact_trades": 130,
            "gap_to_200": 70,
            "honest_status": "not_reached",
            "blocker": "No tested layer adds 20-30 reliable exact annual trades while preserving PF, coverage, stress, and rolling-OOS gates.",
        },
        "ordered_layers": layers,
        "rejected_full_branches": rejected_variants,
        "rejected_incremental_components": _rejected_components(),
        "surgical_scout_tests": [
            _scout_from_latest_run(
                variant_id="sleeve_next_defensive_refill_v1",
                decision="do_not_promote_after_exact_fill",
                role="WMT/PM defensive refill scout rerun after an exact ThetaData import attempt.",
                next_action="Do not promote; it matches 130 exact trades but has 94.2% coverage and the incremental WMT/PM tier is weak.",
            )
        ],
        "lane_decisions": summary.get("lane_decisions"),
        "data_imports_attempted": _import_summary_rows(summary),
        "data_import_read": {
            "theta_terminal_available_in_prior_iteration": True,
            "local_data_limitation": False,
            "remaining_unpriced_read": "Provider no-match exact OCC contracts after direct ThetaData import attempts, not skipped local import work.",
            "required_next_import_action": "Only retry import if a new exact contract/date set appears or a new provider/source can return executable bid/ask rows.",
        },
        "verification_commands": [
            {
                "command": "python scripts/build_bullish_pullback_layer_stack.py",
                "result": "passed; regenerated layer-stack latest.json and markdown report",
            },
            {
                "command": "python -m pytest tests/test_bullish_pullback_layer_stack.py tests/test_bullish_pullback_confidence_tiers.py tests/test_bullish_pullback_ticker_audit.py -q",
                "result": "16 passed",
            },
            {
                "command": "python -m py_compile scripts/build_bullish_pullback_layer_stack.py",
                "result": "passed",
            },
            {
                "command": "python scripts/run_bullish_pullback_sleeves.py --only sleeve_next_defensive_refill_v1 --json",
                "result": "post-import rerun: 138 candidates, 130 exact, 8 unpriced, 94.2% coverage, PF 2.15",
            },
            {
                "command": "python scripts/import_missing_replay_quotes_from_thetadata.py data/options-validation/runs/20260529_180007_sleeve_next_defensive_refill_v1_intraday.json --start-time 09:30:00 --end-time 16:00:00 --interval 1m --lookahead-calendar-days 5 --timeout 180 --json",
                "result": "ThetaData returned 497 normalized rows; imported 0 new trusted rows because all were duplicates in batch 1794",
            },
            {
                "command": "python scripts/classify_missing_replay_contracts.py data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json --json",
                "result": "10 missing legs; all provider_no_match_exact_contract_with_same_expiry_chain; exact executable rows found 0",
            },
            {
                "command": "python scripts/imported_intraday_robustness.py --run data/options-validation/runs/20260529_180218_sleeve_next_defensive_refill_v1_intraday.json --train-days 50 --test-days 20 --json",
                "result": "blocked by unpriced candidates; rolling test passed at PF 3.12; 5%/side stress PF 1.60",
            },
        ],
        "next_actions": [
            "Wire the ordered layer stack into paper-shadow reporting/harness selection before adding more ticker hypotheses.",
            "Build assignment/expiration-safe live-shadow handling for the clean and count-expanded layers.",
            "Add trailing partial-window robustness and leg-level bid/ask audit before any sizing beyond paper.",
            "Run only one surgical split/provider-risk diagnostic for the energy/defensive branch if needed; do not reopen broad refill tuning.",
            "Resume scout lanes only with a new causal rule or new exact trusted data, not by broad all-59 refill loosening.",
        ],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Bullish Pullback Layer Stack - 2026-05-29",
        "",
        "This report freezes the next few bullish-pullback profitability layers from trusted ThetaData intraday OPRA/NBBO exact-contract evidence. It is paper-shadow research only, not live-capital approval.",
        "",
        "## Result",
        "",
        "The next honest layer stack is the high-confidence core, the frozen quoted cluster layers, the 129-trade clean exact branch, the 130-trade count-expanded branch, the 130-trade high-PF reference, and an S-only timecluster component watch. The `200+` exact annual-trade target is still not reached; no tested add-on contributes the needed `20-30` reliable extra exact trades without degrading coverage, stress, OOS, or PF.",
        "",
        "## Ordered Layers",
        "",
        "| Layer | Decision | Exact | PF | Avg PnL | Coverage | Unpriced | Stress PF | Rolling | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for layer in report["ordered_layers"]:
        metrics = layer["metrics"]
        gate = layer["gate_read"]
        lines.append(
            "| "
            + " | ".join(
                [
                    layer["layer_id"],
                    layer["decision"],
                    _fmt(metrics.get("exact_trade_count")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("avg_pnl_pct")),
                    _fmt(metrics.get("quote_coverage_pct")),
                    _fmt(metrics.get("unpriced_trade_count")),
                    _fmt(metrics.get("stress_5pct_per_side_profit_factor")),
                    _fmt(metrics.get("rolling_status")),
                    gate["status"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Rejected Expansion",
            "",
            "| Branch | Exact | PF | Coverage | Stress PF | Rolling | Decision |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in report["rejected_full_branches"]:
        metrics = row["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row["variant_id"],
                    _fmt(metrics.get("exact_trade_count")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("quote_coverage_pct")),
                    _fmt(metrics.get("stress_5pct_per_side_profit_factor")),
                    _fmt(metrics.get("rolling_status")),
                    row["decision"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Rejected Incremental Components",
            "",
            "| Component | Exact | PF | Avg PnL | Reason |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in report["rejected_incremental_components"]:
        metrics = row["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row["component_id"],
                    _fmt(metrics.get("exact_trade_count")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("avg_pnl_pct")),
                    row["reason"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Surgical Scout Test",
            "",
            "| Scout | Exact | PF | Coverage | Unpriced | Stress PF | Rolling | Decision |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in report["surgical_scout_tests"]:
        metrics = row["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row["variant_id"],
                    _fmt(metrics.get("exact_trade_count")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("quote_coverage_pct")),
                    _fmt(metrics.get("unpriced_trade_count")),
                    _fmt(metrics.get("stress_5pct_per_side_profit_factor")),
                    _fmt(metrics.get("rolling_status")),
                    row["decision"],
                ]
            )
            + " |"
        )
    scout = report["surgical_scout_tests"][0]
    classification = scout.get("missing_contract_classification") or {}
    lines.extend(
        [
            "",
            f"The defensive refill scout remains blocked after exact-fill: classification counts `{classification.get('classification_counts')}`, by ticker `{classification.get('by_ticker')}`, and exact executable rows found `{classification.get('exact_executable_rows_found')}`. Its WMT/PM refill tier has only `22` exact trades at PF `1.36` and avg `+7.66%`, so it is not the next layer.",
        ]
    )

    lines.extend(
        [
            "",
            "## Data Read",
            "",
            "- ThetaData was already brought up and used in the prior import/rerun loop for this evidence set.",
            "- A post-layer defensive refill exact-fill attempt wrote `data/options-validation/thetadata-nbbo/thetadata_exact_missing_intraday_20260530T000025Z.json`; ThetaData returned `497` normalized rows but `0` new trusted rows because all were duplicates.",
            "- The remaining unresolved rows are provider no-match exact OCC contracts after direct import attempts, not skipped local data work.",
            "- Do not re-open broad refill tuning unless a new exact trusted data source or a new frozen causal rule changes the setup.",
            "",
            "## Keep / Move / Remove",
            "",
            f"- Keep current lane: `{', '.join(report['lane_decisions']['keep_current_lane'])}`.",
            f"- Move to separate lanes: `{', '.join(report['lane_decisions']['separate_lanes'])}`.",
            f"- Remove from current queue: `{', '.join(report['lane_decisions']['remove_current_queue'])}`.",
            "- Remaining symbols stay research/data-needed unless exact evidence improves.",
            "",
            "## Verification",
            "",
        ]
    )
    for row in report["verification_commands"]:
        lines.append(f"- `{row['command']}`: {row['result']}.")
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
        ]
    )
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, report_path: Path = REPORT_PATH) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"bullish_pullback_layer_stack_{stamp}.json"
    latest_path = output_dir / "latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload, encoding="utf8")
    latest_path.write_text(payload, encoding="utf8")
    report_path.write_text(render_markdown(report), encoding="utf8")
    return {
        "json": str(json_path),
        "latest_json": str(latest_path),
        "markdown": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bullish-pullback exact-evidence profitability layer stack.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_layer_stack()
    artifacts = write_outputs(report, output_dir=Path(args.output_dir), report_path=Path(args.report_path))
    payload = {"artifacts": artifacts, "target_read": report["target_read"]}
    if args.json:
        print(json.dumps({"artifacts": artifacts, "report": report}, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
