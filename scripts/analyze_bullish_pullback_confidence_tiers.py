from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
SLEEVE_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "sleeves"
OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "confidence"
UNIVERSE_PATH = ROOT / "data" / "options-lanes" / "universes" / "bullish_pullback_observation.json"


DEFAULT_SOURCES = [
    {
        "role": "S_reference",
        "playbook": "sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1",
        "path": RUNS_DIR / "20260528_013544_sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1_intraday.json",
        "priority": 100,
        "evidence_points": 15,
    },
    {
        "role": "A_high_coverage",
        "playbook": "sleeve_winner_cluster_exit_balanced_quoted_v1",
        "path": RUNS_DIR / "20260528_013904_sleeve_winner_cluster_exit_balanced_quoted_v1_intraday.json",
        "priority": 90,
        "evidence_points": 12,
    },
    {
        "role": "A_cleaner_coverage",
        "playbook": "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_v1",
        "path": RUNS_DIR / "20260528_014001_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_v1_intraday.json",
        "priority": 88,
        "evidence_points": 12,
    },
    {
        "role": "A_coverage_cleaner",
        "playbook": "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1",
        "path": RUNS_DIR / "20260528_014057_sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1_intraday.json",
        "priority": 86,
        "evidence_points": 12,
    },
    {
        "role": "B_broad_alpha",
        "playbook": "sleeve_alpha_tiered_v1",
        "path": RUNS_DIR / "20260527_204129_sleeve_alpha_tiered_v1_intraday.json",
        "priority": 60,
        "evidence_points": 8,
    },
    {
        "role": "B_broad_portfolio",
        "playbook": "sleeve_portfolio_v1_target3",
        "path": RUNS_DIR / "20260527_204320_sleeve_portfolio_v1_target3_intraday.json",
        "priority": 55,
        "evidence_points": 7,
    },
    {
        "role": "B_sectorfix",
        "playbook": "sleeve_alpha_sectorfix",
        "path": RUNS_DIR / "20260527_204033_sleeve_alpha_sectorfix_intraday.json",
        "priority": 53,
        "evidence_points": 7,
    },
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _scaled(value: Any, low: float, high: float, points: float) -> float:
    if high <= low:
        return 0.0
    return _clamp((_safe_float(value) - low) / (high - low)) * points


def active_universe_symbols() -> list[str]:
    manifest = json.loads(UNIVERSE_PATH.read_text(encoding="utf8"))
    symbols: list[str] = []
    seen: set[str] = set()
    for tier in manifest.get("tiers") or []:
        if not bool(tier.get("scan_eligible", False)):
            continue
        for raw_symbol in tier.get("symbols") or []:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    return symbols


def _trade_date(trade: dict[str, Any]) -> str:
    return str(trade.get("date") or trade.get("entry_date") or "")[:10]


def _trade_key(trade: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(trade.get("ticker") or "").upper(),
        _trade_date(trade),
        str(trade.get("type") or trade.get("trade_type") or "").lower(),
    )


def _pnl(trade: dict[str, Any]) -> float:
    return _safe_float(trade.get("pnl_pct") if trade.get("pnl_pct") is not None else trade.get("net_pnl_pct"))


def _profit_factor(values: Iterable[float]) -> float:
    rows = list(values)
    gross_win = sum(value for value in rows if value > 0)
    gross_loss = abs(sum(value for value in rows if value <= 0))
    if gross_loss <= 0:
        return 999.0 if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 2)


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return round(abs(drawdown), 2)


def metrics(trades: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(trades)
    values = [_pnl(trade) for trade in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    ordered = sorted(rows, key=lambda trade: (_trade_date(trade), str(trade.get("ticker") or "")))
    ordered_values = [_pnl(trade) for trade in ordered]
    return {
        "trade_count": len(rows),
        "symbol_count": len({str(trade.get("ticker") or "").upper() for trade in rows}),
        "profit_factor": _profit_factor(values),
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else 0.0,
        "median_pnl_pct": round(sorted(values)[len(values) // 2], 2) if values else 0.0,
        "win_rate_pct": round(len(wins) / max(len(rows), 1) * 100.0, 1) if rows else 0.0,
        "gross_win": round(sum(wins), 2),
        "gross_loss": round(abs(sum(losses)), 2),
        "max_drawdown_pct_points": _max_drawdown(ordered_values),
        "worst_pnl_pct": round(min(values), 2) if values else 0.0,
        "best_pnl_pct": round(max(values), 2) if values else 0.0,
    }


def _is_exact_quoted_trade(trade: dict[str, Any]) -> bool:
    resolution = str(trade.get("entry_contract_resolution") or "").lower()
    fill_basis = str(trade.get("exit_fill_basis") or "").lower()
    exit_reason = str(trade.get("exit_reason") or "").lower()
    return (
        bool(trade.get("priced", True))
        and resolution.startswith("exact")
        and fill_basis == "imported_spread_mark"
        and exit_reason == "time_exit"
    )


def _signal_points(trade: dict[str, Any]) -> float:
    ret5 = _safe_float(trade.get("signal_ret5"))
    pullback_fit = 1.0 if -3.0 <= ret5 <= 0.75 else max(0.0, 1.0 - min(abs(ret5), 8.0) / 8.0)
    return (
        _scaled(trade.get("direction_score"), 55.0, 85.0, 20.0)
        + _scaled(trade.get("quality_score"), 55.0, 85.0, 7.0)
        + _scaled(trade.get("tech_score"), 55.0, 85.0, 7.0)
        + _scaled(trade.get("signal_ret20"), 4.0, 15.0, 8.0)
        + pullback_fit * 3.0
    )


def _execution_points(trade: dict[str, Any]) -> float:
    long_days = _safe_float(trade.get("long_prior_quote_days"))
    short_days = _safe_float(trade.get("short_prior_quote_days"))
    prior_score = min(long_days, short_days)
    exact_points = 5.0 if _is_exact_quoted_trade(trade) else 0.0
    return (
        _scaled(trade.get("tradability_score"), 55.0, 100.0, 14.0)
        + _scaled(prior_score, 1.0, 14.0, 10.0)
        + exact_points
        + _scaled(trade.get("short_delta_val"), 0.15, 0.35, 3.0)
        + _scaled(trade.get("avg_volume_20d"), 1_000_000.0, 20_000_000.0, 3.0)
    )


def confidence_score(trade: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    signal = _signal_points(trade)
    execution = _execution_points(trade)
    promotion_class = str(trade.get("promotion_class") or "").lower()
    evidence = float(source.get("evidence_points") or 0.0)
    if promotion_class == "promotable_exact_contract":
        evidence += 5.0
    elif promotion_class == "research_sparse_calibration":
        evidence += 2.5
    score = round(min(signal + execution + evidence, 100.0), 1)
    blockers: list[str] = []
    if not _is_exact_quoted_trade(trade):
        blockers.append("not_exact_quoted_time_exit")
    if _safe_float(trade.get("signal_ret20")) < 4.0:
        blockers.append("signal_ret20_below_4")
    if _safe_float(trade.get("tradability_score"), 0.0) < 60.0:
        blockers.append("tradability_below_60")
    if min(_safe_int(trade.get("long_prior_quote_days")), _safe_int(trade.get("short_prior_quote_days"))) < 1:
        blockers.append("missing_prior_quote_continuity")

    tier = "Blocked"
    direction_score = _safe_float(trade.get("direction_score"))
    source_role = str(source.get("role") or "")
    if not blockers:
        if source_role == "S_reference":
            if direction_score >= 75.0:
                tier = "S"
            elif direction_score >= 65.0:
                tier = "A"
            else:
                tier = "B"
        elif score >= 55.0:
            # Non-reference sources are expansion evidence until their marginal
            # contribution is proven positive; keep them visible but not tradable.
            tier = "C"
    elif score >= 55.0 and blockers == ["signal_ret20_below_4"]:
        tier = "C"

    evidence_cap = "paper_shadow"
    if promotion_class == "promotable_exact_contract":
        evidence_cap = "promotable_exact"
    elif promotion_class == "research_sparse_calibration":
        evidence_cap = "research_sparse"
    elif promotion_class == "research_bootstrap":
        evidence_cap = "research_bootstrap"

    return {
        "confidence_score": score,
        "confidence_tier": tier,
        "signal_points": round(signal, 1),
        "execution_points": round(execution, 1),
        "evidence_points": round(evidence, 1),
        "evidence_cap": evidence_cap,
        "blockers": blockers,
    }


def _tier_strength(tier: str) -> int:
    return {"S": 4, "A": 3, "B": 2, "C": 1, "Blocked": 0}.get(str(tier), 0)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _source_summary(result: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    metric = result.get("authoritative_profitability_metrics") or result.get("exact_contract_metrics") or {}
    return {
        "role": source.get("role"),
        "playbook": result.get("playbook") or source.get("playbook"),
        "path": str(source.get("path")),
        "candidate_trade_count": result.get("candidate_trade_count"),
        "priced_trade_count": result.get("priced_trade_count"),
        "unpriced_trade_count": result.get("unpriced_trade_count"),
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "exact_trade_count": metric.get("trade_count"),
        "profit_factor": metric.get("profit_factor"),
        "avg_pnl_pct": metric.get("avg_pnl_pct"),
    }


def _candidate_sources(extra_runs: list[Path] | None = None) -> list[dict[str, Any]]:
    sources = [dict(source) for source in DEFAULT_SOURCES]
    for index, path in enumerate(extra_runs or [], start=1):
        sources.append(
            {
                "role": f"extra_{index}",
                "playbook": path.stem,
                "path": path,
                "priority": 40 - index,
                "evidence_points": 5,
            }
        )
    return sources


def _latest_sleeve_round() -> Path | None:
    if not SLEEVE_DIR.exists():
        return None
    rounds = sorted(SLEEVE_DIR.glob("sleeve_round_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return rounds[0] if rounds else None


def _best_symbol_rows(round_path: Path | None) -> dict[str, dict[str, Any]]:
    if round_path is None or not round_path.exists():
        return {}
    report = _load_json(round_path)
    best: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        variant_id = str(row.get("variant_id") or "")
        if not variant_id.startswith("sleeve_ticker_"):
            continue
        symbol = variant_id.replace("sleeve_ticker_", "", 1).upper()
        current = best.get(symbol)
        if current is None or (
            _safe_float(row.get("exact_profit_factor")) > _safe_float(current.get("exact_profit_factor"))
            and _safe_int(row.get("exact_trade_count")) >= 1
        ):
            best[symbol] = dict(row)
    return best


def build_report(*, extra_runs: list[Path] | None = None, sleeve_round: Path | None = None) -> dict[str, Any]:
    active_symbols = active_universe_symbols()
    active_set = set(active_symbols)
    sleeve_round = sleeve_round or _latest_sleeve_round()
    combined: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []
    missing_sources: list[str] = []

    for source in _candidate_sources(extra_runs):
        path = Path(source["path"])
        if not path.exists():
            missing_sources.append(str(path))
            continue
        result = _load_json(path)
        source_rows.append(_source_summary(result, source))
        for raw_trade in result.get("trades") or []:
            trade = dict(raw_trade)
            symbol = str(trade.get("ticker") or "").upper()
            if symbol not in active_set:
                continue
            if not _is_exact_quoted_trade(trade):
                continue
            scored = confidence_score(trade, source)
            enriched = {
                **trade,
                **scored,
                "source_role": source.get("role"),
                "source_playbook": result.get("playbook") or source.get("playbook"),
                "source_priority": int(source.get("priority") or 0),
            }
            key = _trade_key(enriched)
            existing = combined.get(key)
            if existing is None:
                combined[key] = enriched
                continue
            if (
                (
                    _tier_strength(str(enriched["confidence_tier"])),
                    _safe_float(enriched["confidence_score"]),
                    _safe_int(enriched["source_priority"]),
                )
                > (
                    _tier_strength(str(existing["confidence_tier"])),
                    _safe_float(existing["confidence_score"]),
                    _safe_int(existing["source_priority"]),
                )
            ):
                combined[key] = enriched

    trades = list(combined.values())
    tier_order = {"S": 0, "A": 1, "B": 2, "C": 3, "Blocked": 4}
    trades.sort(
        key=lambda trade: (
            tier_order.get(str(trade.get("confidence_tier")), 9),
            -_safe_float(trade.get("confidence_score")),
            _trade_date(trade),
            str(trade.get("ticker") or ""),
        )
    )

    by_tier: dict[str, dict[str, Any]] = {}
    for tier in ["S", "A", "B", "C", "Blocked"]:
        tier_trades = [trade for trade in trades if trade.get("confidence_tier") == tier]
        by_tier[tier] = {
            **metrics(tier_trades),
            "symbols": sorted({str(trade.get("ticker") or "").upper() for trade in tier_trades}),
        }

    by_symbol: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("ticker") or "").upper()].append(trade)
    best_symbol_evidence = _best_symbol_rows(sleeve_round)
    for symbol in active_symbols:
        rows = grouped.get(symbol) or []
        ticker_row = best_symbol_evidence.get(symbol) or {}
        by_symbol[symbol] = {
            **metrics(rows),
            "best_tier": rows[0].get("confidence_tier") if rows else None,
            "best_confidence_score": rows[0].get("confidence_score") if rows else None,
            "best_source_playbook": rows[0].get("source_playbook") if rows else None,
            "per_symbol_candidate_trade_count": ticker_row.get("candidate_trade_count"),
            "per_symbol_exact_trade_count": ticker_row.get("exact_trade_count"),
            "per_symbol_profit_factor": ticker_row.get("exact_profit_factor"),
            "per_symbol_quote_coverage_pct": ticker_row.get("quote_coverage_pct"),
        }

    tradable = [trade for trade in trades if trade.get("confidence_tier") in {"S", "A", "B"}]
    scout = [trade for trade in trades if trade.get("confidence_tier") == "C"]
    positive_symbol_evidence = [
        symbol
        for symbol, row in by_symbol.items()
        if _safe_int(row.get("trade_count")) > 0 or _safe_float(row.get("per_symbol_profit_factor")) >= 1.0
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "active_universe_count": len(active_symbols),
        "cmcsa_active": "CMCSA" in active_set,
        "sleeve_round_path": str(sleeve_round) if sleeve_round else None,
        "source_runs": source_rows,
        "missing_sources": missing_sources,
        "combined_tradable_metrics": metrics(tradable),
        "combined_scout_metrics": metrics(scout),
        "combined_all_exact_metrics": metrics(trades),
        "by_confidence_tier": by_tier,
        "by_symbol": by_symbol,
        "coverage": {
            "symbols_with_s_a_b_trades": len({str(trade.get("ticker") or "").upper() for trade in tradable}),
            "symbols_with_any_report_trade": len(grouped),
            "symbols_with_positive_or_reported_evidence": len(positive_symbol_evidence),
            "symbols_without_s_a_b_trades": sorted(active_set - {str(trade.get("ticker") or "").upper() for trade in tradable}),
            "symbols_without_positive_or_reported_evidence": sorted(active_set - set(positive_symbol_evidence)),
        },
        "top_queue": [
            {
                "tier": trade.get("confidence_tier"),
                "score": trade.get("confidence_score"),
                "ticker": trade.get("ticker"),
                "date": _trade_date(trade),
                "type": trade.get("type") or trade.get("trade_type"),
                "pnl_pct": round(_pnl(trade), 2),
                "source_playbook": trade.get("source_playbook"),
                "direction_score": trade.get("direction_score"),
                "signal_ret20": trade.get("signal_ret20"),
                "signal_ret5": trade.get("signal_ret5"),
                "tradability_score": trade.get("tradability_score"),
                "prior_quotes": [
                    trade.get("long_prior_quote_days"),
                    trade.get("short_prior_quote_days"),
                ],
                "evidence_cap": trade.get("evidence_cap"),
                "blockers": trade.get("blockers"),
            }
            for trade in trades[:50]
        ],
        "stop_read": {
            "primary_lever": "Broaden S/A/B source sleeves; increasing n_picks alone does not help when daily candidate pools are empty.",
            "data_import_read": "Do not keep blind exact-fill loops for current provider no-match rows unless a new source/provider is added.",
            "promotion_read": "Use as paper/live-shadow evidence until forward fills and more OOS windows exist.",
        },
    }


def write_report(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"bullish_pullback_confidence_tiers_{stamp}.json"
    latest = output_dir / "latest.json"
    serialized = json.dumps(report, indent=2, sort_keys=True)
    path.write_text(serialized, encoding="utf8")
    latest.write_text(serialized, encoding="utf8")
    return {"json": str(path), "latest_json": str(latest)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build confidence/evidence tiers for bullish pullback sleeve runs.")
    parser.add_argument("--extra-run", action="append", default=[], help="Additional replay JSON to include.")
    parser.add_argument("--sleeve-round", default=None, help="Sleeve round JSON with per-symbol/theme evidence.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(
        extra_runs=[Path(path) for path in args.extra_run],
        sleeve_round=Path(args.sleeve_round) if args.sleeve_round else None,
    )
    artifacts = write_report(report, output_dir=Path(args.output_dir))
    payload = {"artifacts": artifacts, "report": report}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "artifacts": artifacts,
                    "combined_tradable_metrics": report["combined_tradable_metrics"],
                    "coverage": report["coverage"],
                    "by_confidence_tier": {
                        tier: {
                            "trade_count": row["trade_count"],
                            "symbol_count": row["symbol_count"],
                            "profit_factor": row["profit_factor"],
                            "avg_pnl_pct": row["avg_pnl_pct"],
                        }
                        for tier, row in report["by_confidence_tier"].items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
