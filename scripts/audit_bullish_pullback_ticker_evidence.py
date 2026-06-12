from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import expectancy_calibration as ec


UNIVERSE_PATH = ROOT / "data" / "options-lanes" / "universes" / "bullish_pullback_observation.json"
CONFIDENCE_PATH = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "confidence" / "latest.json"
SLEEVE_ROUND_PATH = (
    ROOT
    / "data"
    / "profitability-lab"
    / "bullish-pullback-observation"
    / "sleeves"
    / "sleeve_round_20260602T163650Z.json"
)
COUNT_EXPANDED_PATH = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260528_085047_sleeve_pf59_coverage_a_refill_v1_intraday.json"
)
OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "ticker-audit"
DOCS_OUTPUT = ROOT / "docs" / "bullish-pullback-ticker-audit-2026-05-29.md"

MIN_TICKER_EXACT_TRADES_FOR_DISPOSITION = 30
TICKER_EXPECTANCY_SHRINKAGE_TRADES = ec.DEFAULT_SHRINKAGE_TRADES


LANE_MAP: dict[str, str] = {
    "SPY": "index_etf_control",
    "QQQ": "index_etf_control",
    "DIA": "index_etf_control",
    "XLK": "tech_etf_control",
    "NVDA": "high_beta_momentum_volatility",
    "AMZN": "high_beta_momentum_volatility",
    "AMD": "high_beta_momentum_volatility",
    "META": "high_beta_momentum_volatility",
    "NFLX": "high_beta_momentum_volatility",
    "TSLA": "high_beta_momentum_volatility",
    "COIN": "high_beta_momentum_volatility",
    "MSTR": "high_beta_momentum_volatility",
    "PLTR": "high_beta_momentum_volatility",
    "ARM": "high_beta_momentum_volatility",
    "SMCI": "high_beta_momentum_volatility",
    "WMT": "defensive_retail_refill",
    "KO": "defensive_income",
    "PM": "defensive_income",
    "COST": "defensive_retail_refill",
    "PG": "defensive_income",
    "MCD": "defensive_retail_refill",
    "NKE": "consumer_discretionary_reversal",
    "SBUX": "consumer_discretionary_reversal",
    "DIS": "consumer_discretionary_reversal",
    "T": "defensive_income",
    "AMT": "reits_rate_sensitive",
    "PLD": "reits_rate_sensitive",
    "SPG": "reits_rate_sensitive",
    "WELL": "reits_rate_sensitive",
    "EQR": "reits_rate_sensitive",
    "CAT": "industrials_materials",
    "BA": "industrials_materials",
    "DE": "industrials_materials",
    "LMT": "industrials_materials",
    "RTX": "industrials_materials",
    "FCX": "commodity_materials",
    "SLB": "commodity_energy",
    "CLF": "commodity_materials",
    "AA": "commodity_materials",
    "LIN": "commodity_materials",
    "OXY": "commodity_energy",
    "JPM": "financials_reversal",
    "GS": "financials_reversal",
    "BAC": "financials_reversal",
    "V": "financials_reversal",
    "C": "financials_reversal",
    "ABBV": "healthcare_defensive",
    "PFE": "healthcare_defensive",
}

STRATEGIC_ALT_SYMBOLS = {
    "NVDA",
    "AMZN",
    "TSLA",
    "PLTR",
    "COIN",
    "MSTR",
    "ARM",
    "SMCI",
    "AMD",
    "META",
    "NFLX",
}

INDEX_SCOUT_SYMBOLS = {"QQQ", "DIA", "XLK"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _variant_symbol(variant_id: str) -> str:
    return variant_id.replace("sleeve_ticker_", "", 1).upper()


def active_universe_rows(path: Path = UNIVERSE_PATH) -> list[dict[str, str]]:
    manifest = _load_json(path)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for tier in manifest.get("tiers") or []:
        if not bool(tier.get("scan_eligible", False)):
            continue
        tier_name = str(tier.get("tier_id") or tier.get("label") or tier.get("name") or tier.get("id") or "")
        for raw_symbol in tier.get("symbols") or []:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                rows.append({"ticker": symbol, "universe_tier": tier_name})
    return rows


def sleeve_rows(path: Path = SLEEVE_ROUND_PATH) -> dict[str, dict[str, Any]]:
    report = _load_json(path)
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        variant_id = str(row.get("variant_id") or "")
        if variant_id.startswith("sleeve_ticker_"):
            rows[_variant_symbol(variant_id)] = dict(row)
    return rows


def confidence_rows(path: Path = CONFIDENCE_PATH) -> dict[str, dict[str, Any]]:
    report = _load_json(path)
    return {str(symbol).upper(): dict(row) for symbol, row in (report.get("by_symbol") or {}).items()}


def _reason_counts(run: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for trade in run.get("unpriced_trades") or []:
        reason = (
            trade.get("unpriced_reason")
            or trade.get("non_promotable_reason")
            or trade.get("pre_entry_filter_reject_reason")
            or "unpriced"
        )
        counts[str(reason)] += 1
    for trade in run.get("post_entry_filtered_trades") or []:
        reason = trade.get("post_entry_filter_reject_reason") or "post_entry_filtered"
        counts[str(reason)] += 1
    return dict(counts)


def _exit_reasons(row: dict[str, Any]) -> dict[str, int]:
    metrics = row.get("by_tier") or {}
    if metrics:
        first = next(iter(metrics.values()))
        return {str(item.get("exit_reason") or ""): _safe_int(item.get("trades")) for item in first.get("exit_reasons") or []}
    return {}


def _load_run(row: dict[str, Any]) -> dict[str, Any]:
    result_path = row.get("result_path")
    if not result_path:
        return {}
    path = Path(str(result_path))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    return _load_json(path)


def classify_ticker(symbol: str, row: dict[str, Any], confidence: dict[str, Any]) -> tuple[str, str, str]:
    tier = confidence.get("best_tier")
    exact = _safe_int(row.get("exact_trade_count"))
    candidates = _safe_int(row.get("candidate_trade_count"))
    pf = _safe_float(row.get("exact_profit_factor"))
    avg = _safe_float(row.get("exact_avg_pnl_pct"))
    coverage = _safe_float(row.get("quote_coverage_pct"))
    lane = LANE_MAP.get(symbol, "research_lane")

    if tier in {"S", "A", "B"}:
        return (
            "keep-in-current-lane",
            "bullish_pullback_observation",
            "S/A/B confidence evidence supports current bullish-pullback paper-shadow eligibility.",
        )

    if exact >= 10 and pf < 1.0 and avg < 0:
        return (
            "remove",
            "",
            "Adequate scout sample is negative; remove from the current bullish-pullback tradable queue.",
        )

    if exact >= 3 and pf >= 1.3 and avg > 0:
        return (
            "move-to-different-lane",
            lane,
            "Positive but non-promoted evidence is better handled as a separately frozen lane.",
        )

    if symbol in INDEX_SCOUT_SYMBOLS and exact >= 1 and pf > 1.0 and avg > 0:
        return (
            "move-to-different-lane",
            lane,
            "Positive ETF/index evidence is too thin for current-lane promotion but deserves a separate scout lane.",
        )

    if symbol in STRATEGIC_ALT_SYMBOLS and exact >= 4:
        return (
            "move-to-different-lane",
            lane,
            "Current bullish-pullback evidence failed or stayed sparse, but the ticker is strategically liquid enough to retest under a better high-beta hypothesis.",
        )

    if exact >= 6 and pf < 0.5 and avg < 0:
        return (
            "remove",
            "",
            "Repeated exact losses under the current playbook; remove from the bullish-pullback tradable queue.",
        )

    if exact >= 6 and coverage >= 50.0 and pf < 1.0 and avg < 0:
        return (
            "remove",
            "",
            "Repeated exact losses under the current playbook; remove from the bullish-pullback tradable queue.",
        )

    if tier == "Blocked" and exact >= 1 and pf <= 0.0 and avg <= -95.0 and coverage >= 90.0:
        return (
            "remove",
            "",
            "Blocked confidence plus a clean near-total-loss exact sample; remove from the current tradable queue.",
        )

    if exact >= 4 and coverage >= 90.0 and pf < 0.25 and avg < 0:
        return (
            "remove",
            "",
            "Clean enough sample with very weak PF; remove from the current bullish-pullback tradable queue.",
        )

    if candidates == 0:
        return (
            "research-only/data-needed",
            lane,
            "No selected current-lane candidates; keep as research/control until a different lane generates evidence.",
        )

    if exact < 10:
        return (
            "research-only/data-needed",
            lane,
            "Exact sample is too thin for a durable ticker verdict.",
        )

    if coverage < 90.0:
        return (
            "research-only/data-needed",
            lane,
            "Coverage/unresolved candidates prevent current-lane promotion.",
        )

    return (
        "research-only/data-needed",
        lane,
        "No current-lane promotion evidence; keep as scout until a frozen rerun proves otherwise.",
    )


def _lane_parent_expectancy(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_pnl = 0.0
    total_trades = 0
    for row in rows.values():
        exact = _safe_int(row.get("exact_trade_count"))
        if exact <= 0:
            continue
        total_trades += exact
        total_pnl += _safe_float(row.get("exact_avg_pnl_pct")) * exact
    avg = total_pnl / total_trades if total_trades else 0.0
    return {
        "lane_id": "bullish_pullback_observation",
        "trade_count": total_trades,
        "avg_pnl_pct": round(avg, 2),
    }


def _n_floor_disposition(decision: str, exact_trades: int) -> str:
    if int(exact_trades) < MIN_TICKER_EXACT_TRADES_FOR_DISPOSITION:
        return "insufficient_n_frozen"
    return decision


def _queue_change_allowed(decision: str, exact_trades: int) -> bool:
    if int(exact_trades) < MIN_TICKER_EXACT_TRADES_FOR_DISPOSITION:
        return False
    return decision in {"keep-in-current-lane", "move-to-different-lane", "remove"}


def build_audit(
    *,
    universe_path: Path = UNIVERSE_PATH,
    confidence_path: Path = CONFIDENCE_PATH,
    sleeve_round_path: Path = SLEEVE_ROUND_PATH,
    count_expanded_path: Path = COUNT_EXPANDED_PATH,
) -> dict[str, Any]:
    universe = active_universe_rows(universe_path)
    sleeve_by_symbol = sleeve_rows(sleeve_round_path)
    confidence_by_symbol = confidence_rows(confidence_path)
    confidence_report = _load_json(confidence_path)
    count_expanded = _load_json(count_expanded_path) if count_expanded_path.exists() else {}
    lane_parent_expectancy = _lane_parent_expectancy(sleeve_by_symbol)

    rows: list[dict[str, Any]] = []
    for item in universe:
        symbol = item["ticker"]
        row = sleeve_by_symbol.get(symbol, {})
        conf = confidence_by_symbol.get(symbol, {})
        run = _load_run(row)
        decision, recommended_lane, rationale = classify_ticker(symbol, row, conf)
        exact = _safe_int(row.get("exact_trade_count"))
        n_floor_disposition = _n_floor_disposition(decision, exact)
        queue_change_allowed = _queue_change_allowed(decision, exact)
        raw_avg = _safe_float(row.get("exact_avg_pnl_pct"))
        expectancy = ec.shrink_expectancy_to_parent(
            raw_avg_pnl_pct=raw_avg,
            child_trade_count=exact,
            parent_avg_pnl_pct=lane_parent_expectancy["avg_pnl_pct"],
            parent_trade_count=lane_parent_expectancy["trade_count"],
            shrinkage_trades=TICKER_EXPECTANCY_SHRINKAGE_TRADES,
        )
        rows.append(
            {
                "ticker": symbol,
                "universe_tier": item["universe_tier"],
                "confidence_tier": conf.get("best_tier"),
                "confidence_score": conf.get("best_confidence_score"),
                "decision": decision,
                "n_floor_disposition": n_floor_disposition,
                "legacy_decision_preserved": True,
                "min_exact_trades_for_disposition": MIN_TICKER_EXACT_TRADES_FOR_DISPOSITION,
                "queue_change_allowed_by_n_floor": queue_change_allowed,
                "queue_change_block_reason": None if queue_change_allowed else "insufficient_exact_trades_for_ticker_disposition",
                "recommended_lane": recommended_lane,
                "candidate_trade_count": _safe_int(row.get("candidate_trade_count")),
                "exact_quoted_trade_count": exact,
                "unpriced_trade_count": _safe_int(row.get("unpriced_trade_count")),
                "quote_coverage_pct": _safe_float(row.get("quote_coverage_pct")),
                "profit_factor": _safe_float(row.get("exact_profit_factor")),
                "avg_pnl_pct": raw_avg,
                "expectancy_shrinkage": expectancy,
                "shrunk_avg_pnl_pct": expectancy.get("shrunk_avg_pnl_pct"),
                "directional_accuracy_pct": _safe_float(row.get("exact_directional_accuracy_pct")),
                "confidence_trade_count": _safe_int(conf.get("trade_count")),
                "confidence_profit_factor": _safe_float(conf.get("profit_factor")),
                "confidence_avg_pnl_pct": _safe_float(conf.get("avg_pnl_pct")),
                "result_path": row.get("result_path"),
                "unpriced_reasons": _reason_counts(run),
                "exit_reasons": _exit_reasons(row),
                "rationale": rationale,
                "next_action": _next_action(decision, recommended_lane),
            }
        )

    decision_counts = dict(Counter(row["decision"] for row in rows))
    n_floor_disposition_counts = dict(Counter(row["n_floor_disposition"] for row in rows))
    keep_symbols = [row["ticker"] for row in rows if row["decision"] == "keep-in-current-lane"]
    move_symbols = [row["ticker"] for row in rows if row["decision"] == "move-to-different-lane"]
    research_symbols = [row["ticker"] for row in rows if row["decision"] == "research-only/data-needed"]
    remove_symbols = [row["ticker"] for row in rows if row["decision"] == "remove"]
    queue_change_allowed_symbols = [
        row["ticker"]
        for row in rows
        if row["queue_change_allowed_by_n_floor"]
    ]
    insufficient_n_symbols = [row["ticker"] for row in rows if row["n_floor_disposition"] == "insufficient_n_frozen"]
    count_metrics = count_expanded.get("exact_contract_metrics") or count_expanded.get("authoritative_profitability_metrics") or {}
    count_exact = _safe_int(count_metrics.get("trade_count"))
    high_conf = confidence_report.get("combined_tradable_metrics") or {}
    high_conf_exact = _safe_int(high_conf.get("trade_count"))

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "universe_path": str(universe_path),
        "sleeve_round_path": str(sleeve_round_path),
        "confidence_path": str(confidence_path),
        "active_symbol_count": len(universe),
        "proof_rules": {
            "proof_source": "trusted ThetaData intraday OPRA/NBBO",
            "disallowed": [
                "nearest-listed substitutions",
                "midpoint-only fills",
                "underlying bars",
                "option OHLC bars",
                "unresolved candidates",
            ],
            "remove_scope": "remove from current bullish-pullback tradable queue unless explicitly stated otherwise",
            "per_ticker_disposition_floor": MIN_TICKER_EXACT_TRADES_FOR_DISPOSITION,
            "floor_migration_note": "Legacy decision fields are preserved. New keep/move/remove emission must use n_floor_disposition and queue_change_allowed_by_n_floor.",
        },
        "portfolio_targets": {
            "target_exact_trades_per_year_low": 200,
            "target_exact_trades_per_year_high": 260,
            "green_profit_factor": 1.75,
            "preferred_profit_factor": 2.0,
            "green_avg_pnl_pct": 15.0,
        },
        "portfolio_current": {
            "high_confidence_exact_trades": high_conf_exact,
            "high_confidence_profit_factor": high_conf.get("profit_factor"),
            "high_confidence_avg_pnl_pct": high_conf.get("avg_pnl_pct"),
            "count_expanded_exact_trades": count_exact,
            "count_expanded_profit_factor": count_metrics.get("profit_factor"),
            "count_expanded_avg_pnl_pct": count_metrics.get("avg_pnl_pct"),
            "gap_from_200_high_confidence": max(200 - high_conf_exact, 0),
            "gap_from_200_count_expanded": max(200 - count_exact, 0),
        },
        "decision_counts": decision_counts,
        "n_floor_disposition_counts": n_floor_disposition_counts,
        "lane_parent_expectancy": lane_parent_expectancy,
        "expectancy_shrinkage_trades": TICKER_EXPECTANCY_SHRINKAGE_TRADES,
        "symbols": {
            "keep_in_current_lane": keep_symbols,
            "move_to_different_lane": move_symbols,
            "research_only_data_needed": research_symbols,
            "remove": remove_symbols,
            "insufficient_n_frozen": insufficient_n_symbols,
            "queue_change_allowed_by_n_floor": queue_change_allowed_symbols,
        },
        "rows": rows,
    }


def _next_action(decision: str, lane: str) -> str:
    if decision == "keep-in-current-lane":
        return "Keep in current paper-shadow queue with caps; do not call strict proof-complete until unresolved rows and forward evidence clear."
    if decision == "move-to-different-lane":
        return f"Create or rerun a frozen `{lane}` hypothesis before allowing picks from this ticker."
    if decision == "remove":
        return "Remove from the current bullish-pullback tradable queue; reconsider only after a new frozen hypothesis or longer exact-data window."
    return "Keep out of current picks; collect exact data or rerun targeted research before promotion."


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    current = report["portfolio_current"]
    lines = [
        "# Bullish Pullback Ticker Audit - 2026-05-29",
        "",
        "This audit uses exact trusted ThetaData intraday OPRA/NBBO evidence only. Nearest-listed, midpoint, stale, bar-based, and unresolved fills are scout-only.",
        "",
        "## Portfolio Summary",
        "",
        f"- Active symbols: `{report['active_symbol_count']}`.",
        f"- High-confidence S/A/B current evidence: `{current['high_confidence_exact_trades']}` exact trades, PF `{current['high_confidence_profit_factor']}`, avg `{current['high_confidence_avg_pnl_pct']}%`.",
        f"- Count-expanded current candidate: `{current['count_expanded_exact_trades']}` exact trades, PF `{current['count_expanded_profit_factor']}`, avg `{current['count_expanded_avg_pnl_pct']}%`.",
        f"- Gap to `200` exact trades/year: `{current['gap_from_200_high_confidence']}` from high-confidence evidence, `{current['gap_from_200_count_expanded']}` from count-expanded evidence.",
        f"- Decision counts: `{json.dumps(report['decision_counts'], sort_keys=True)}`.",
        f"- N-floor disposition counts: `{json.dumps(report.get('n_floor_disposition_counts') or {}, sort_keys=True)}`.",
        f"- Per-ticker keep/move/remove floor: `{report.get('proof_rules', {}).get('per_ticker_disposition_floor')}` exact trades. Legacy `decision` values are preserved; new queue-change emission must use `n_floor_disposition` plus `queue_change_allowed_by_n_floor`.",
        f"- Lane parent expectancy for shrinkage: `{json.dumps(report.get('lane_parent_expectancy') or {}, sort_keys=True)}`.",
        "",
        "## Decision Buckets",
        "",
        f"- Keep in current lane: `{', '.join(report['symbols']['keep_in_current_lane']) or 'none'}`.",
        f"- Move to different lane: `{', '.join(report['symbols']['move_to_different_lane']) or 'none'}`.",
        f"- Research/data-needed: `{', '.join(report['symbols']['research_only_data_needed']) or 'none'}`.",
        f"- Remove from current queue: `{', '.join(report['symbols']['remove']) or 'none'}`.",
        f"- Insufficient-N frozen: `{', '.join(report['symbols'].get('insufficient_n_frozen') or []) or 'none'}`.",
        f"- Queue-change allowed by N floor: `{', '.join(report['symbols'].get('queue_change_allowed_by_n_floor') or []) or 'none'}`.",
        "",
        "## Per-Ticker Table",
        "",
        "| Ticker | Decision | N-Floor Label | Queue Emit | Lane | Conf | Exact/Cand | PF | Avg % | Shrunk Avg % | Coverage % | Main issue / rationale | Next action |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row["ticker"]),
                    _md_cell(row["decision"]),
                    _md_cell(row["n_floor_disposition"]),
                    _md_cell(row["queue_change_allowed_by_n_floor"]),
                    _md_cell(row["recommended_lane"]),
                    _md_cell(row["confidence_tier"] or ""),
                    f"{row['exact_quoted_trade_count']}/{row['candidate_trade_count']}",
                    _md_cell(row["profit_factor"]),
                    _md_cell(row["avg_pnl_pct"]),
                    _md_cell(row.get("shrunk_avg_pnl_pct")),
                    _md_cell(row["quote_coverage_pct"]),
                    _md_cell(row["rationale"]),
                    _md_cell(row["next_action"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `remove` means remove from the current bullish-pullback tradable queue. It is not a permanent ban from all future research unless a future decision explicitly says so.",
            "- Migration note: use `n_floor_disposition` and `queue_change_allowed_by_n_floor` for new keep/move/remove emission. Rows below `30` exact trades are `insufficient_n_frozen` even when legacy `decision` records the older call.",
            "- Per-ticker average P&L now also carries `expectancy_shrinkage`, which shrinks the ticker mean toward the bullish-pullback lane mean using `expectancy_calibration.py` shrinkage helpers.",
            "- The current one-year all-symbol data readiness is adequate for exact replay, but many high-profile names still have too few qualifying exact trades under this specific playbook.",
            "- The path to `200+` trades/year likely requires new frozen lanes for high-beta, ETF/index, defensive-income, REIT/rate-sensitive, commodity, and financial symbols rather than forcing the current bullish-pullback sleeve to trade weak evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, docs_output: Path = DOCS_OUTPUT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"bullish_pullback_ticker_audit_{stamp}.json"
    latest_path = output_dir / "latest.json"
    markdown_path = output_dir / f"bullish_pullback_ticker_audit_{stamp}.md"
    serialized = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf8")
    docs_output.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "latest_json": str(latest_path),
        "markdown": str(markdown_path),
        "docs_markdown": str(docs_output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit bullish_pullback_observation ticker evidence.")
    parser.add_argument("--universe", default=str(UNIVERSE_PATH))
    parser.add_argument("--confidence", default=str(CONFIDENCE_PATH))
    parser.add_argument("--sleeve-round", default=str(SLEEVE_ROUND_PATH))
    parser.add_argument("--count-expanded-run", default=str(COUNT_EXPANDED_PATH))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--docs-output", default=str(DOCS_OUTPUT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_audit(
        universe_path=Path(args.universe),
        confidence_path=Path(args.confidence),
        sleeve_round_path=Path(args.sleeve_round),
        count_expanded_path=Path(args.count_expanded_run),
    )
    artifacts = write_outputs(report, output_dir=Path(args.output_dir), docs_output=Path(args.docs_output))
    payload = {"artifacts": artifacts, "report": report}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps({"artifacts": artifacts, "decision_counts": report["decision_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
