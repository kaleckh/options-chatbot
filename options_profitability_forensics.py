from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import math
from statistics import median
from typing import Any, Iterable

from exact_contract_accounting import is_exact_contract_resolution, trade_contract_resolution


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(part / whole * 100.0, 1)


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _profit_factor(pnl_values: Iterable[float]) -> float:
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return 999.0 if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 2)


def _normalize_side(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"call", "bullish"}:
        return "call"
    if normalized in {"put", "bearish"}:
        return "put"
    return "unknown"


def _score_band(value: Any) -> str:
    score = max(0.0, min(100.0, _safe_number(value)))
    if score < 40.0:
        return "00-39"
    if score < 50.0:
        return "40-49"
    if score < 60.0:
        return "50-59"
    if score < 70.0:
        return "60-69"
    if score < 80.0:
        return "70-79"
    return "80-100"


def _dte_bucket(value: Any) -> str:
    try:
        dte = int(float(value))
    except (TypeError, ValueError):
        return "unknown"
    if dte <= 12:
        return "05-12"
    if dte <= 21:
        return "13-21"
    if dte <= 35:
        return "22-35"
    return "36+"


def _contract_resolution(trade: dict[str, Any]) -> str:
    return trade_contract_resolution(trade)


def _selection_source(trade: dict[str, Any]) -> str:
    return str(trade.get("selection_source") or "unknown").strip() or "unknown"


def _is_exact_contract_resolution(value: Any) -> bool:
    return is_exact_contract_resolution(value)


def _truth_source(result: dict[str, Any]) -> str:
    return str(result.get("truth_source") or "synthetic_research").strip().lower() or "synthetic_research"


def _authoritative_profitability_view(
    result: dict[str, Any],
    aggregate_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_source = str(result.get("candidate_source") or "").strip().lower()
    authoritative_evidence_source = str(result.get("authoritative_evidence_source") or "").strip().lower()
    truth_source = _truth_source(result)

    if candidate_source == "forward_ledger_scan" or authoritative_evidence_source == "archived_forward_daily":
        authoritative_trades = [
            trade
            for trade in aggregate_trades
            if _contract_resolution(trade) == "exact_archived_contract"
        ]
        label = "Archived exact-contract subset"
        description = "Forward profitability claims use only archived exact contracts; model fallback remains research-only."
    elif truth_source in {"historical_imported", "historical_imported_daily"}:
        authoritative_trades = [
            trade for trade in aggregate_trades if _is_exact_contract_resolution(_contract_resolution(trade))
        ]
        label = "Exact-contract subset"
        description = "Imported replay profitability claims use exact-contract matches only; nearest-listed substitutions remain research-only."
    else:
        authoritative_trades = list(aggregate_trades)
        label = "Aggregate replay"
        description = "No exact-contract split is available for this truth lane, so profitability falls back to all replay trades."

    authoritative_ids = {id(trade) for trade in authoritative_trades}
    research_only_trades = [trade for trade in aggregate_trades if id(trade) not in authoritative_ids]
    return {
        "label": label,
        "description": description,
        "trades": authoritative_trades,
        "research_only_trades": research_only_trades,
    }


def _summarize_trade_subset(
    category: str,
    value: str,
    trades: list[dict[str, Any]],
    total_trades: int,
    *,
    min_trades: int,
) -> dict[str, Any]:
    pnl_values = [_safe_number(trade.get("pnl_pct")) for trade in trades]
    profitable = [value for value in pnl_values if value > 0]
    directionally_correct = [trade for trade in trades if bool(trade.get("directional_correct"))]
    exact_contract_trades = [
        trade for trade in trades if _is_exact_contract_resolution(_contract_resolution(trade))
    ]
    replay_calibrated = [
        trade for trade in trades if _selection_source(trade) == "replay_calibrated"
    ]
    avg_direction_score = (
        sum(_safe_number(trade.get("direction_score")) for trade in trades) / len(trades)
        if trades
        else None
    )
    avg_quality_score = (
        sum(_safe_number(trade.get("quality_score")) for trade in trades) / len(trades)
        if trades
        else None
    )
    avg_tech_score = (
        sum(_safe_number(trade.get("tech_score")) for trade in trades) / len(trades)
        if trades
        else None
    )
    avg_dte = (
        sum(_safe_number(trade.get("dte")) for trade in trades) / len(trades)
        if trades
        else None
    )
    return {
        "group": category,
        "category": category,
        "value": value,
        "label": value,
        "trades": len(trades),
        "share_of_total_pct": _pct(len(trades), total_trades),
        "win_rate_pct": _pct(len(profitable), len(trades)),
        "directional_accuracy_pct": _pct(len(directionally_correct), len(trades)),
        "profit_factor": _profit_factor(pnl_values),
        "avg_pnl_pct": _round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else 0.0,
        "median_pnl_pct": _round(median(pnl_values), 2) if pnl_values else 0.0,
        "avg_direction_score": _round(avg_direction_score, 1) if avg_direction_score is not None else None,
        "avg_quality_score": _round(avg_quality_score, 1) if avg_quality_score is not None else None,
        "avg_tech_score": _round(avg_tech_score, 1) if avg_tech_score is not None else None,
        "avg_dte": _round(avg_dte, 1) if avg_dte is not None else None,
        "exact_contract_share_pct": _pct(len(exact_contract_trades), len(trades)),
        "replay_calibrated_share_pct": _pct(len(replay_calibrated), len(trades)),
        "sparse": len(trades) < int(min_trades),
    }


def _rank_best_slice(item: dict[str, Any]) -> tuple:
    return (
        0 if item.get("sparse") else 1,
        1 if float(item.get("avg_pnl_pct", 0.0) or 0.0) > 0 else 0,
        1 if float(item.get("profit_factor", 0.0) or 0.0) >= 1.0 else 0,
        float(item.get("profit_factor", 0.0) or 0.0),
        float(item.get("avg_pnl_pct", 0.0) or 0.0),
        float(item.get("directional_accuracy_pct", 0.0) or 0.0),
        int(item.get("trades", 0) or 0),
    )


def _rank_worst_slice(item: dict[str, Any]) -> tuple:
    return (
        0 if item.get("sparse") else 1,
        -float(item.get("profit_factor", 0.0) or 0.0),
        -float(item.get("avg_pnl_pct", 0.0) or 0.0),
        -float(item.get("directional_accuracy_pct", 0.0) or 0.0),
        int(item.get("trades", 0) or 0),
    )


def _result_source(result: dict[str, Any], total_trades: int) -> dict[str, Any]:
    selection_counts = Counter(
        _selection_source(trade) for trade in list(result.get("trades") or [])
    )
    resolution_counts = Counter(
        _contract_resolution(trade) for trade in list(result.get("trades") or [])
    )
    return {
        "run_at": result.get("run_at"),
        "mode": result.get("mode"),
        "lookback_years": result.get("lookback_years"),
        "pricing_lane": result.get("pricing_lane"),
        "playbook": result.get("playbook"),
        "truth_source": result.get("truth_source") or "synthetic_research",
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "priced_trade_count": result.get("priced_trade_count", total_trades),
        "unpriced_trade_count": result.get("unpriced_trade_count", 0),
        "total_trades": total_trades,
        "candidate_source": result.get("candidate_source") or "model_replay",
        "evidence_status": result.get("evidence_status"),
        "truth_window_status": result.get("truth_window_status"),
        "primary_judge_trade_class": result.get("primary_judge_trade_class"),
        "selection_source_counts": dict(selection_counts),
        "contract_resolution_counts": dict(resolution_counts),
    }


def build_options_profitability_forensics(
    result: dict[str, Any] | None,
    *,
    min_trades: int = 20,
) -> dict[str, Any]:
    if not result:
        return {"error": "No backtest results found"}

    aggregate_trades = list(result.get("trades") or [])
    profitability_view = _authoritative_profitability_view(result, aggregate_trades)
    trades = list(profitability_view["trades"])
    research_only_trades = list(profitability_view["research_only_trades"])
    total_trades = len(trades)
    source = _result_source(result, len(aggregate_trades))
    overall = _summarize_trade_subset("overall", "overall", trades, total_trades, min_trades=min_trades)
    aggregate_overall = _summarize_trade_subset(
        "aggregate_overall",
        "aggregate_overall",
        aggregate_trades,
        len(aggregate_trades),
        min_trades=min_trades,
    )
    research_only_overall = _summarize_trade_subset(
        "research_only_overall",
        "research_only_overall",
        research_only_trades,
        len(research_only_trades),
        min_trades=min_trades,
    )

    if not aggregate_trades:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "quality_bar": {"min_trades": int(min_trades)},
            "overall": overall,
            "aggregate_overall": aggregate_overall,
            "research_only_overall": research_only_overall,
            "authoritative_profitability_label": profitability_view["label"],
            "authoritative_profitability_description": profitability_view["description"],
            "exactness_view": {
                "exact_only": _summarize_trade_subset("exactness", "exact_only", [], 0, min_trades=min_trades),
                "nearest_allowed": _summarize_trade_subset("exactness", "nearest_allowed", [], 0, min_trades=min_trades),
                "nearest_only": _summarize_trade_subset("exactness", "nearest_only", [], 0, min_trades=min_trades),
            },
            "category_order": [],
            "by_category": {},
            "best_dense_slices": [],
            "worst_dense_slices": [],
            "blockers": ["No trades are available for profitability forensics."],
            "recommendations": ["Run a backtest or imported-daily refresh before using profitability forensics."],
        }

    groups: dict[str, dict[str, list[dict[str, Any]]]] = {
        "symbol": defaultdict(list),
        "side": defaultdict(list),
        "symbol_side": defaultdict(list),
        "selection_source": defaultdict(list),
        "contract_resolution": defaultdict(list),
        "score_bands": defaultdict(list),
        "dte_bucket": defaultdict(list),
        "exit_reason": defaultdict(list),
    }
    for trade in trades:
        symbol = str(trade.get("ticker") or "UNKNOWN").upper()
        side = _normalize_side(trade.get("type") or trade.get("trade_type") or trade.get("direction"))
        selection_source = _selection_source(trade)
        contract_resolution = _contract_resolution(trade)
        score_band = _score_band(trade.get("direction_score"))
        dte_bucket = _dte_bucket(trade.get("dte"))
        exit_reason = str(trade.get("exit_reason") or "unknown").strip().lower() or "unknown"
        groups["symbol"][symbol].append(trade)
        groups["side"][side].append(trade)
        groups["symbol_side"][f"{symbol}:{side}"].append(trade)
        groups["selection_source"][selection_source].append(trade)
        groups["contract_resolution"][contract_resolution].append(trade)
        groups["score_bands"][score_band].append(trade)
        groups["dte_bucket"][dte_bucket].append(trade)
        groups["exit_reason"][exit_reason].append(trade)

    category_order = [
        "symbol",
        "side",
        "symbol_side",
        "selection_source",
        "contract_resolution",
        "score_bands",
        "dte_bucket",
        "exit_reason",
    ]
    pretrade_category_order = [
        category
        for category in category_order
        if category != "exit_reason"
    ]
    by_category: dict[str, list[dict[str, Any]]] = {}
    pretrade_slices: list[dict[str, Any]] = []
    for category in category_order:
        summaries = [
            _summarize_trade_subset(category, value, subset, total_trades, min_trades=min_trades)
            for value, subset in sorted(groups[category].items())
        ]
        summaries = sorted(summaries, key=_rank_best_slice, reverse=True)
        by_category[category] = summaries
        if category in pretrade_category_order:
            pretrade_slices.extend(summaries)

    exact_only = [
        trade for trade in aggregate_trades if _is_exact_contract_resolution(_contract_resolution(trade))
    ]
    nearest_only = [
        trade for trade in aggregate_trades if _contract_resolution(trade) == "nearest_listed_contract"
    ]
    exactness_view = {
        "exact_only": _summarize_trade_subset("exactness", "exact_only", exact_only, len(aggregate_trades), min_trades=min_trades),
        "authoritative_only": _summarize_trade_subset(
            "exactness",
            "authoritative_only",
            trades,
            len(aggregate_trades),
            min_trades=min_trades,
        ),
        "nearest_allowed": _summarize_trade_subset("exactness", "nearest_allowed", aggregate_trades, len(aggregate_trades), min_trades=min_trades),
        "nearest_only": _summarize_trade_subset("exactness", "nearest_only", nearest_only, len(aggregate_trades), min_trades=min_trades),
        "research_only": _summarize_trade_subset(
            "exactness",
            "research_only",
            research_only_trades,
            len(aggregate_trades),
            min_trades=min_trades,
        ),
    }

    dense_slices = [item for item in pretrade_slices if not item.get("sparse")]
    best_dense_slices = sorted(dense_slices, key=_rank_best_slice, reverse=True)[:10]
    worst_dense_slices = sorted(dense_slices, key=_rank_worst_slice, reverse=True)[:10]

    blockers: list[str] = []
    recommendations: list[str] = []
    if float(overall.get("profit_factor", 0.0) or 0.0) < 1.0:
        blockers.append(f"{profitability_view['label']} profit factor is below 1.0.")
    if float(overall.get("avg_pnl_pct", 0.0) or 0.0) <= 0.0:
        blockers.append(f"{profitability_view['label']} average trade P&L is not positive.")
    if float(exactness_view["exact_only"].get("profit_factor", 0.0) or 0.0) < 1.0:
        blockers.append("Exact-contract-only subset is not profitable.")
    if float(exactness_view["exact_only"].get("avg_pnl_pct", 0.0) or 0.0) <= 0.0:
        blockers.append("Exact-contract-only average P&L is not positive.")

    side_rows = {row["value"]: row for row in by_category.get("side", [])}
    call_row = side_rows.get("call")
    put_row = side_rows.get("put")
    if call_row and put_row and float(put_row.get("avg_pnl_pct", 0.0) or 0.0) < float(call_row.get("avg_pnl_pct", 0.0) or 0.0):
        blockers.append("Put-side performance is materially worse than call-side performance.")
        recommendations.append("Treat put-side research as secondary until a positive exact-contract lane exists.")

    bootstrap_count = int(source["selection_source_counts"].get("bootstrap_heuristic", 0) or 0)
    bootstrap_share_pct = _pct(bootstrap_count, total_trades)
    if bootstrap_share_pct >= 80.0:
        blockers.append(
            f"Bootstrap-heuristic trades still dominate the sample ({bootstrap_share_pct:.1f}%)."
        )
    if research_only_trades:
        recommendations.append(
            f"{len(research_only_trades)} replay trade(s) remain outside the authoritative profitability lens and should stay research-only."
        )

    if best_dense_slices and float(best_dense_slices[0].get("avg_pnl_pct", 0.0) or 0.0) > 0.0:
        recommendations.append(
            f"Audit the strongest dense slice first: {best_dense_slices[0]['category']}={best_dense_slices[0]['value']}."
        )
    else:
        recommendations.append(
            "No dense slice is currently positive enough to treat as a surviving edge."
        )
        recommendations.append(
            "Redesign entry and exit rules before doing more optimizer tuning if no exact-contract slice turns positive."
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "quality_bar": {"min_trades": int(min_trades)},
        "overall": overall,
        "aggregate_overall": aggregate_overall,
        "research_only_overall": research_only_overall,
        "authoritative_profitability_label": profitability_view["label"],
        "authoritative_profitability_description": profitability_view["description"],
        "exactness_view": exactness_view,
        "category_order": category_order,
        "by_category": by_category,
        "best_dense_slices": best_dense_slices,
        "worst_dense_slices": worst_dense_slices,
        "blockers": blockers,
        "recommendations": recommendations,
    }
