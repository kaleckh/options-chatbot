from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_regular_options_autoresearch import (  # noqa: E402
    bootstrap_confidence_for_values,
    selection_adjusted_bar,
)


REPORT_ID = "regular_options_robust_search_evaluation"

DEFAULT_SOURCE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_REGIME_REPORT = ROOT / "data" / "profitability-lab" / "regime-stratified-replay" / "latest.json"
DEFAULT_FEATURE_STORE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_AUTORESEARCH_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "ledger.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-robust-search-evaluation.md"

TRAIN_FRACTION = 0.60
VALIDATION_FRACTION = 0.25
FINAL_HOLDOUT_FRACTION = 0.15

MIN_TOTAL_EXACT_TRADES = 100
MIN_VALIDATION_EXACT_TRADES = 30
MIN_FINAL_HOLDOUT_EXACT_TRADES = 30
MIN_FINAL_HOLDOUT_BOOTSTRAP_PF_LB = 1.0

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_robust_search_evaluation",
    "do_not_submit_broker_order_from_robust_search_evaluation",
    "do_not_change_scanner_policy_from_robust_search_evaluation",
    "do_not_change_stop_policy_from_robust_search_evaluation",
    "do_not_change_sizing_from_robust_search_evaluation",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_robust_search_evaluation",
    "do_not_count_historical_rows_as_fresh_forward_promotion_proof",
    "do_not_consume_protected_forward_holdout_from_robust_search_evaluation",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


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
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _date_only(value: Any) -> date | None:
    raw = _norm(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    return payload, meta


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf8").splitlines():
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _profit_factor(values: Sequence[float]) -> float | None:
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_loss = abs(sum(losses))
    if gross_loss <= 0.0:
        return None
    return sum(wins) / gross_loss


def _normalize_trade(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    entry_date = _date_only(row.get("entry_date") or row.get("date"))
    pnl = _safe_float(row.get("net_pnl_pct", row.get("pnl_pct")))
    if entry_date is None:
        return None, "missing_or_invalid_entry_date"
    if pnl is None:
        return None, "missing_or_invalid_pnl_pct"
    exact = (
        bool(row.get("exact_priced"))
        and _norm(row.get("proof_grade")) == "trusted_intraday_opra_nbbo"
        and _norm(row.get("entry_contract_resolution")).startswith("exact")
        and _norm(row.get("fill_basis")) == "imported_spread_mark"
    )
    if not exact:
        return None, "not_trusted_intraday_exact_row"
    return {
        "entry_date": entry_date.isoformat(),
        "exit_date": _norm(row.get("exit_date")),
        "ticker": _norm(row.get("ticker")).upper(),
        "lane_id": _norm(row.get("lane_id")) or "unknown",
        "lane_family": _norm(row.get("lane_family")) or _norm(row.get("family")) or "unknown",
        "direction": _norm(row.get("direction")) or "unknown",
        "pnl_pct": pnl,
        "proof_grade": _norm(row.get("proof_grade")),
        "source_result_path": _norm(row.get("source_result_path")),
        "dedupe_key": _norm(row.get("dedupe_key")),
        "portfolio_eligible": bool(row.get("portfolio_eligible", True)),
    }, None


def normalize_trades(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    accepted: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    for row in rows:
        normalized, reason = _normalize_trade(dict(row))
        if normalized is None:
            rejected[reason or "unknown_reject"] += 1
            continue
        accepted.append(normalized)
    accepted.sort(key=lambda item: (item["entry_date"], item["ticker"], item["direction"], item["lane_id"]))
    return accepted, rejected


def chronological_split_rows(
    rows: Sequence[dict[str, Any]],
    *,
    train_fraction: float = TRAIN_FRACTION,
    validation_fraction: float = VALIDATION_FRACTION,
) -> dict[str, list[dict[str, Any]]]:
    unique_dates = sorted({str(row["entry_date"]) for row in rows})
    if not unique_dates:
        return {"train": [], "validation": [], "final_holdout": []}
    train_cut = int(math.floor(len(unique_dates) * train_fraction))
    validation_cut = int(math.floor(len(unique_dates) * (train_fraction + validation_fraction)))
    train_cut = max(0, min(train_cut, len(unique_dates)))
    validation_cut = max(train_cut, min(validation_cut, len(unique_dates)))
    date_to_split: dict[str, str] = {}
    for index, entry_date in enumerate(unique_dates):
        if index < train_cut:
            split = "train"
        elif index < validation_cut:
            split = "validation"
        else:
            split = "final_holdout"
        date_to_split[entry_date] = split
    splits = {"train": [], "validation": [], "final_holdout": []}
    for row in rows:
        splits[date_to_split[str(row["entry_date"])]].append(dict(row))
    return splits


def _metrics_for_values(values: list[float], *, branch_id: str, bootstrap_draws: int) -> dict[str, Any]:
    bootstrap = bootstrap_confidence_for_values(values, branch_id=branch_id, draws=bootstrap_draws)
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    return {
        "exact_trade_count": len(values),
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "win_rate_pct": round((len(wins) / len(values)) * 100.0, 2) if values else 0.0,
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "profit_factor": _round_optional(_profit_factor(values), 4),
        "gross_win_pct_points": round(sum(wins), 2),
        "gross_loss_pct_points": round(abs(sum(losses)), 2),
        "bootstrap": bootstrap,
    }


def _metrics_for_rows(rows: Sequence[dict[str, Any]], *, branch_id: str, bootstrap_draws: int) -> dict[str, Any]:
    values = [float(row["pnl_pct"]) for row in rows]
    metrics = _metrics_for_values(values, branch_id=branch_id, bootstrap_draws=bootstrap_draws)
    metrics["first_entry_date"] = rows[0]["entry_date"] if rows else None
    metrics["latest_entry_date"] = rows[-1]["entry_date"] if rows else None
    metrics["entry_date_count"] = len({row["entry_date"] for row in rows})
    metrics["ticker_count"] = len({row["ticker"] for row in rows})
    return metrics


def _split_metrics(rows: Sequence[dict[str, Any]], *, candidate_id: str, bootstrap_draws: int) -> dict[str, Any]:
    splits = chronological_split_rows(rows)
    return {
        split: _metrics_for_rows(split_rows, branch_id=f"{candidate_id}:{split}", bootstrap_draws=bootstrap_draws)
        for split, split_rows in splits.items()
    }


def _variants_searched(ledger_rows: list[dict[str, Any]]) -> int:
    experiment_ids = {
        _norm(row.get("experiment_id") or row.get("variant_id") or row.get("id"))
        for row in ledger_rows
        if _norm(row.get("experiment_id") or row.get("variant_id") or row.get("id"))
    }
    return max(len(experiment_ids), 1)


def _regime_check(regime_report: dict[str, Any], regime_meta: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(regime_report.get("summary"))
    if regime_meta.get("status") != "loaded":
        return {
            "status": "not_evaluated_missing_regime_report",
            "regime_robust": False,
            "blockers": ["regime_report_missing"],
        }
    robust = bool(summary.get("regime_robust"))
    blockers = []
    if not robust:
        blockers.append(summary.get("overall_status") or "regime_robust_false")
    return {
        "status": "regime_robust_passed" if robust else "regime_robust_blocked",
        "regime_robust": robust,
        "blockers": [str(item) for item in blockers if item],
        "summary": {
            "overall_status": summary.get("overall_status"),
            "market_context_status": summary.get("market_context_status"),
            "evaluable_bucket_count": summary.get("evaluable_bucket_count"),
            "failing_bucket_count": summary.get("failing_bucket_count"),
            "thin_bucket_count": summary.get("thin_bucket_count"),
        },
    }


def _ablation_check(
    final_metrics: dict[str, Any],
    baseline_report: dict[str, Any],
    baseline_meta: dict[str, Any],
) -> dict[str, Any]:
    if baseline_meta.get("status") != "loaded":
        return {
            "status": "not_evaluated_missing_baseline",
            "positive_ablation": False,
            "blockers": ["baseline_ablation_report_missing"],
        }
    baseline = (
        _as_dict(baseline_report.get("baseline_metrics"))
        or _as_dict(_as_dict(baseline_report.get("combined_portfolio")).get("metrics"))
        or _as_dict(baseline_report.get("metrics"))
        or _as_dict(baseline_report.get("summary"))
    )
    baseline_pf = _safe_float(baseline.get("profit_factor") or baseline.get("pf_point"))
    baseline_avg = _safe_float(baseline.get("avg_pnl_pct") or baseline.get("avg_net_pnl_pct") or baseline.get("avg_net_point"))
    final_pf = _safe_float(final_metrics.get("profit_factor"))
    final_avg = _safe_float(final_metrics.get("avg_pnl_pct"))
    blockers = []
    if baseline_pf is None or baseline_avg is None:
        blockers.append("baseline_metrics_missing_pf_or_avg")
    if final_pf is None:
        blockers.append("final_holdout_profit_factor_undefined")
    if not blockers:
        if (final_pf or -10_000.0) <= (baseline_pf or -10_000.0):
            blockers.append("final_holdout_pf_not_above_baseline")
        if (final_avg or -10_000.0) <= (baseline_avg or -10_000.0):
            blockers.append("final_holdout_avg_not_above_baseline")
    return {
        "status": "positive_ablation_passed" if not blockers else "positive_ablation_blocked",
        "positive_ablation": not blockers,
        "baseline_metrics": {
            "profit_factor": _round_optional(baseline_pf, 4),
            "avg_pnl_pct": _round_optional(baseline_avg, 4),
        },
        "final_holdout_metrics": {
            "profit_factor": _round_optional(final_pf, 4),
            "avg_pnl_pct": _round_optional(final_avg, 4),
        },
        "blockers": blockers,
    }


def _winner_fragility_check(rows: Sequence[dict[str, Any]], *, remove_count: int = 5) -> dict[str, Any]:
    values = sorted([float(row["pnl_pct"]) for row in rows], reverse=True)
    if len(values) <= remove_count:
        return {
            "status": "not_evaluable_too_few_rows",
            "zero_material_winner_damage_findings": False,
            "blockers": ["too_few_rows_for_top_winner_removal"],
        }
    remaining = values[remove_count:]
    remaining_pf = _profit_factor(remaining)
    remaining_avg = sum(remaining) / len(remaining) if remaining else None
    blockers = []
    if remaining_pf is None or remaining_pf <= 1.0:
        blockers.append("top_winner_removal_pf_not_above_1")
    if remaining_avg is None or remaining_avg <= 0.0:
        blockers.append("top_winner_removal_avg_not_positive")
    return {
        "status": "zero_material_winner_damage_findings" if not blockers else "winner_fragility_blocked",
        "zero_material_winner_damage_findings": not blockers,
        "removed_top_winner_count": remove_count,
        "remaining_trade_count": len(remaining),
        "remaining_profit_factor": _round_optional(remaining_pf, 4),
        "remaining_avg_pnl_pct": _round_optional(remaining_avg, 4),
        "blockers": blockers,
    }


def _quality_gate_check(source_report: dict[str, Any]) -> dict[str, Any]:
    gate = _as_dict(source_report.get("quality_gate"))
    status = _norm(gate.get("overall_status"))
    blockers = [str(item) for item in _as_list(gate.get("blockers")) if item]
    passed = status in {"passed", "quality_passed", "production_ready"}
    if not passed:
        blockers.append(f"source_quality_gate:{status or 'missing'}")
    return {
        "status": "source_quality_gate_passed" if passed else "source_quality_gate_blocked",
        "passed": passed,
        "overall_status": status or None,
        "blockers": sorted(set(blockers)),
    }


def _candidate_blockers(
    *,
    split_metrics: dict[str, Any],
    variants_searched: int,
    regime_check: dict[str, Any],
    ablation_check: dict[str, Any],
    winner_check: dict[str, Any],
    quality_gate: dict[str, Any],
) -> list[str]:
    total_n = _safe_int(split_metrics["combined"]["exact_trade_count"])
    validation_n = _safe_int(split_metrics["validation"]["exact_trade_count"])
    final_n = _safe_int(split_metrics["final_holdout"]["exact_trade_count"])
    final_bootstrap = _as_dict(split_metrics["final_holdout"].get("bootstrap"))
    final_pf_lb = _safe_float(final_bootstrap.get("pf_lb_5pct"))
    adjusted_bar = selection_adjusted_bar(variants_searched)
    blockers = []
    if total_n < MIN_TOTAL_EXACT_TRADES:
        blockers.append("total_exact_trades_below_100")
    if validation_n < MIN_VALIDATION_EXACT_TRADES:
        blockers.append("validation_exact_trades_below_30")
    if final_n < MIN_FINAL_HOLDOUT_EXACT_TRADES:
        blockers.append("final_holdout_exact_trades_below_30")
    if final_pf_lb is None or final_pf_lb <= MIN_FINAL_HOLDOUT_BOOTSTRAP_PF_LB:
        blockers.append("final_holdout_bootstrap_pf_lb_not_above_1")
    if final_pf_lb is None or final_pf_lb < adjusted_bar:
        blockers.append("final_holdout_pf_lb_below_selection_adjusted_bar")
    if not bool(regime_check.get("regime_robust")):
        blockers.extend(str(item) for item in _as_list(regime_check.get("blockers")) or ["regime_robust_false"])
    if not bool(ablation_check.get("positive_ablation")):
        blockers.extend(str(item) for item in _as_list(ablation_check.get("blockers")) or ["positive_ablation_missing"])
    if not bool(winner_check.get("zero_material_winner_damage_findings")):
        blockers.extend(str(item) for item in _as_list(winner_check.get("blockers")) or ["winner_damage_not_cleared"])
    if not bool(quality_gate.get("passed")):
        blockers.extend(str(item) for item in _as_list(quality_gate.get("blockers")) or ["source_quality_gate_not_passed"])
    return sorted(set(blockers))


def _candidate_report(
    *,
    candidate_id: str,
    rows: Sequence[dict[str, Any]],
    candidate_type: str,
    variants_searched: int,
    regime_check: dict[str, Any],
    baseline_report: dict[str, Any],
    baseline_meta: dict[str, Any],
    quality_gate: dict[str, Any],
    bootstrap_draws: int,
) -> dict[str, Any]:
    split_metrics = _split_metrics(rows, candidate_id=candidate_id, bootstrap_draws=bootstrap_draws)
    combined = _metrics_for_rows(rows, branch_id=f"{candidate_id}:combined", bootstrap_draws=bootstrap_draws)
    split_metrics["combined"] = combined
    ablation = _ablation_check(split_metrics["final_holdout"], baseline_report, baseline_meta)
    winner = _winner_fragility_check(rows)
    blockers = _candidate_blockers(
        split_metrics=split_metrics,
        variants_searched=variants_searched,
        regime_check=regime_check,
        ablation_check=ablation,
        winner_check=winner,
        quality_gate=quality_gate,
    )
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "status": "historical_candidate_ready_for_forward_nomination" if not blockers else "historical_candidate_blocked",
        "historical_nomination_ready": not blockers,
        "blockers": blockers,
        "selection_adjustment": {
            "variants_searched": variants_searched,
            "selection_adjusted_bar": selection_adjusted_bar(variants_searched),
            "metric": "final_holdout.bootstrap.pf_lb_5pct",
        },
        "split_metrics": split_metrics,
        "regime_check": regime_check,
        "ablation_check": ablation,
        "winner_damage_check": winner,
        "source_quality_gate": quality_gate,
        "read_only": True,
    }


def _group_candidates(rows: Sequence[dict[str, Any]]) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, tuple[str, list[dict[str, Any]]]] = {
        "combined_portfolio": ("combined", [dict(row) for row in rows])
    }
    by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_lane[str(row.get("lane_id") or "unknown")].append(dict(row))
    for lane_id, lane_rows in sorted(by_lane.items()):
        grouped[f"lane:{lane_id}"] = ("lane", lane_rows)
    return grouped


def build_report(
    *,
    source_report_path: Path = DEFAULT_SOURCE_REPORT,
    regime_report_path: Path = DEFAULT_REGIME_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    autoresearch_ledger_path: Path = DEFAULT_AUTORESEARCH_LEDGER,
    baseline_report_path: Path | None = None,
    generated_at_utc: str | None = None,
    bootstrap_draws: int = 10_000,
) -> dict[str, Any]:
    source, source_meta = _load_json(source_report_path)
    regime, regime_meta = _load_json(regime_report_path)
    feature_store, feature_meta = _load_json(feature_store_report_path)
    ledger_rows, ledger_meta = _load_jsonl(autoresearch_ledger_path)
    baseline, baseline_meta = _load_json(baseline_report_path) if baseline_report_path else ({}, {"status": "missing", "path": None})

    raw_rows = _as_list(source.get("selected_trades")) if source_meta.get("status") == "loaded" else []
    trades, rejected = normalize_trades([dict(row) for row in raw_rows if isinstance(row, dict)])
    variants = _variants_searched(ledger_rows)
    regime_check = _regime_check(regime, regime_meta)
    quality_gate = _quality_gate_check(source)
    candidates = [
        _candidate_report(
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            rows=rows,
            variants_searched=variants,
            regime_check=regime_check,
            baseline_report=baseline,
            baseline_meta=baseline_meta,
            quality_gate=quality_gate,
            bootstrap_draws=bootstrap_draws,
        )
        for candidate_id, (candidate_type, rows) in _group_candidates(trades).items()
        if rows
    ]
    ready = [candidate for candidate in candidates if candidate.get("historical_nomination_ready")]
    if source_meta.get("status") != "loaded":
        status = "blocked_missing_source_report"
    elif not trades:
        status = "blocked_no_exact_historical_rows"
    elif ready:
        status = "historical_candidates_ready_for_forward_nomination"
    else:
        status = "historical_candidates_blocked"
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_historical_robust_search_read_only",
        "schema_version": 1,
        "read_only": True,
        "inputs": {
            "source_report": source_meta,
            "regime_report": regime_meta,
            "feature_store_report": feature_meta,
            "autoresearch_ledger": ledger_meta,
            "baseline_report": baseline_meta,
        },
        "split_policy": {
            "train_fraction": TRAIN_FRACTION,
            "validation_fraction": VALIDATION_FRACTION,
            "final_holdout_fraction": FINAL_HOLDOUT_FRACTION,
            "split_unit": "unique_entry_date",
            "no_same_entry_date_crosses_splits": True,
        },
        "criteria": {
            "min_total_exact_trades": MIN_TOTAL_EXACT_TRADES,
            "min_validation_exact_trades": MIN_VALIDATION_EXACT_TRADES,
            "min_final_holdout_exact_trades": MIN_FINAL_HOLDOUT_EXACT_TRADES,
            "min_final_holdout_bootstrap_pf_lb": MIN_FINAL_HOLDOUT_BOOTSTRAP_PF_LB,
            "requires_regime_robust": True,
            "requires_positive_ablation_vs_baseline": True,
            "requires_zero_material_winner_damage_findings": True,
            "requires_source_quality_gate_passed": True,
            "bootstrap_draws": bootstrap_draws,
        },
        "summary": {
            "overall_status": status,
            "source_selected_trade_count": len(raw_rows),
            "accepted_exact_trade_count": len(trades),
            "rejected_row_counts": dict(sorted(rejected.items())),
            "candidate_count": len(candidates),
            "ready_candidate_count": len(ready),
            "variants_searched": variants,
            "selection_adjusted_bar": selection_adjusted_bar(variants),
            "feature_store_status": feature_store.get("status") if feature_meta.get("status") == "loaded" else feature_meta.get("status"),
            "feature_store_shared_quote_date_count": _as_dict(feature_store.get("summary")).get("shared_quote_date_count")
            if feature_meta.get("status") == "loaded"
            else None,
            "regime_status": regime_check.get("status"),
            "source_quality_gate_status": quality_gate.get("status"),
            "promotion_ready": False,
        },
        "candidates": candidates,
        "proof_policy": {
            "readback_is": "historical robust-search nomination readback over trusted intraday exact rows",
            "readback_is_not": "fresh forward proof, live-validation eligibility, broker action, scanner policy change, protected-holdout consumption, or proof-bar reduction",
            "historical_use": "nominate, reject, or refreeze candidate lanes for future forward tracking only",
            "forward_truth_requirement": "live-validation promotion still requires fresh post-freeze exact realized P&L under the existing contracts",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Robust Search Evaluation",
        "",
        "This report is generated from `scripts/build_regular_options_robust_search_evaluation.py`. It evaluates historical trusted intraday exact rows with chronological train/validation/final-holdout splits and fail-closed nomination criteria. It does not create trades, change policy, consume protected forward holdout, lower proof bars, or treat historical rows as fresh forward promotion proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Accepted exact trades: `{summary.get('accepted_exact_trade_count')}` / source selected `{summary.get('source_selected_trade_count')}`.",
        f"- Ready historical candidates: `{summary.get('ready_candidate_count')}` / `{summary.get('candidate_count')}`.",
        f"- Variants searched: `{summary.get('variants_searched')}`.",
        f"- Selection-adjusted PF-LB bar: `{summary.get('selection_adjusted_bar')}`.",
        f"- Regime status: `{summary.get('regime_status')}`.",
        f"- Feature-store status: `{summary.get('feature_store_status')}`; shared dates `{summary.get('feature_store_shared_quote_date_count')}`.",
        f"- Source quality gate: `{summary.get('source_quality_gate_status')}`.",
        f"- Rejected row counts: `{_json_inline(summary.get('rejected_row_counts') or {})}`.",
        "",
        "## Candidate Table",
        "",
        "| Candidate | Type | Status | Total N | Validation N | Final N | Final PF LB | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for candidate in _as_list(report.get("candidates")):
        candidate = _as_dict(candidate)
        splits = _as_dict(candidate.get("split_metrics"))
        combined = _as_dict(splits.get("combined"))
        validation = _as_dict(splits.get("validation"))
        final = _as_dict(splits.get("final_holdout"))
        final_bootstrap = _as_dict(final.get("bootstrap"))
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(candidate.get('candidate_id'))}`",
                    f"`{_cell(candidate.get('candidate_type'))}`",
                    f"`{_cell(candidate.get('status'))}`",
                    _cell(combined.get("exact_trade_count")),
                    _cell(validation.get("exact_trade_count")),
                    _cell(final.get("exact_trade_count")),
                    _cell(final_bootstrap.get("pf_lb_5pct")),
                    _cell(", ".join(str(item) for item in _as_list(candidate.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A ready row here means only that a historical candidate is eligible to be nominated for future forward tracking. It is not live-validation eligibility and is not a profit claim without later fresh exact realized P&L.",
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only regular-options robust historical search evaluation.")
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--regime-report", type=Path, default=DEFAULT_REGIME_REPORT)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--autoresearch-ledger", type=Path, default=DEFAULT_AUTORESEARCH_LEDGER)
    parser.add_argument("--baseline-report", type=Path, default=None)
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        source_report_path=args.source_report,
        regime_report_path=args.regime_report,
        feature_store_report_path=args.feature_store_report,
        autoresearch_ledger_path=args.autoresearch_ledger,
        baseline_report_path=args.baseline_report,
        bootstrap_draws=max(int(args.bootstrap_draws), 1),
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
