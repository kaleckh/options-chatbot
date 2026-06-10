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

from exact_contract_accounting import contract_resolution_accounting, split_exact_and_research_trades


DEFAULT_RUN = ROOT / "data" / "options-validation" / "runs" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "imported-intraday-robustness"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _trade_date(trade: dict[str, Any]) -> str:
    return str(trade.get("date") or trade.get("entry_date") or "")[:10]


def _month(value: str) -> str:
    return str(value or "")[:7]


def _pnl_values(trades: Iterable[dict[str, Any]], *, slippage_pct_per_side: float = 0.0) -> list[float]:
    penalty = 2.0 * float(slippage_pct_per_side)
    return [_safe_float(trade.get("pnl_pct") or trade.get("net_pnl_pct")) - penalty for trade in trades]


def _profit_factor(values: Iterable[float]) -> float | None:
    rows = list(values)
    gross_win = sum(value for value in rows if value > 0)
    gross_loss = abs(sum(value for value in rows if value <= 0))
    if gross_loss <= 0:
        return None if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 2)


def _profit_factor_is_defined(metrics: dict[str, Any]) -> bool:
    return metrics.get("profit_factor") is not None


def _max_drawdown_pct(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return round(abs(max_drawdown), 2)


def _metrics(
    trades: Iterable[dict[str, Any]],
    *,
    total: int | None = None,
    slippage_pct_per_side: float = 0.0,
) -> dict[str, Any]:
    rows = [dict(trade) for trade in trades]
    pnls = _pnl_values(rows, slippage_pct_per_side=slippage_pct_per_side)
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value <= 0]
    denominator = int(total if total is not None else len(rows))
    sorted_rows = sorted(rows, key=lambda trade: (_trade_date(trade), str(trade.get("ticker") or "")))
    sorted_pnls = _pnl_values(sorted_rows, slippage_pct_per_side=slippage_pct_per_side)
    return {
        "trades": len(rows),
        "share_of_total_pct": round(len(rows) / max(denominator, 1) * 100.0, 1) if denominator else 0.0,
        "win_rate_pct": round(len(wins) / max(len(rows), 1) * 100.0, 1) if rows else 0.0,
        "profit_factor": _profit_factor(pnls),
        "no_loss_sample": bool(pnls and not losses and wins),
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "median_pnl_pct": round(sorted(pnls)[len(pnls) // 2], 2) if pnls else 0.0,
        "gross_win": round(sum(wins), 2),
        "gross_loss": round(abs(sum(losses)), 2),
        "max_drawdown_pct_points": _max_drawdown_pct(sorted_pnls),
        "worst_pnl_pct": round(min(pnls), 2) if pnls else 0.0,
        "best_pnl_pct": round(max(pnls), 2) if pnls else 0.0,
    }


def _window_dates(dates: list[str], *, train_days: int, test_days: int) -> list[tuple[list[str], list[str]]]:
    windows: list[tuple[list[str], list[str]]] = []
    start = 0
    while start + int(train_days) + int(test_days) <= len(dates):
        train = dates[start : start + int(train_days)]
        test = dates[start + int(train_days) : start + int(train_days) + int(test_days)]
        windows.append((train, test))
        start += int(test_days)
    return windows


def _rolling_windows(
    trades: list[dict[str, Any]],
    unpriced: list[dict[str, Any]],
    *,
    train_days: int,
    test_days: int,
    min_exact_test_trades: int,
) -> dict[str, Any]:
    candidate_rows = trades + unpriced
    dates = sorted({_trade_date(trade) for trade in candidate_rows if _trade_date(trade)})
    windows = _window_dates(dates, train_days=int(train_days), test_days=int(test_days))
    rows: list[dict[str, Any]] = []
    for index, (train_dates, test_dates) in enumerate(windows, start=1):
        train_set = set(train_dates)
        test_set = set(test_dates)
        train_trades = [trade for trade in trades if _trade_date(trade) in train_set]
        test_trades = [trade for trade in trades if _trade_date(trade) in test_set]
        test_unpriced = [trade for trade in unpriced if _trade_date(trade) in test_set]
        test_metrics = _metrics(test_trades, total=len(test_trades) + len(test_unpriced))
        blockers: list[str] = []
        if test_unpriced:
            blockers.append("unpriced_test_candidates_present")
        if test_metrics["trades"] < int(min_exact_test_trades):
            blockers.append("exact_test_trade_count_below_floor")
        if not _profit_factor_is_defined(test_metrics):
            blockers.append("exact_test_profit_factor_undefined")
        elif float(test_metrics["profit_factor"]) < 1.0:
            blockers.append("exact_test_profit_factor_below_1")
        if test_metrics["avg_pnl_pct"] <= 0:
            blockers.append("exact_test_avg_pnl_not_positive")
        rows.append(
            {
                "window": index,
                "train_start": train_dates[0],
                "train_end": train_dates[-1],
                "test_start": test_dates[0],
                "test_end": test_dates[-1],
                "train": _metrics(train_trades),
                "test": test_metrics,
                "unpriced_test_candidate_count": len(test_unpriced),
                "gate_passed": not blockers,
                "gate_blockers": blockers,
            }
        )
    failed = [row for row in rows if not row["gate_passed"]]
    return {
        "status": "passed" if rows and not failed else "watch",
        "date_count": len(dates),
        "window_count": len(rows),
        "passed_window_count": len(rows) - len(failed),
        "failed_window_count": len(failed),
        "blockers": sorted({blocker for row in failed for blocker in row["gate_blockers"]}),
        "windows": rows,
    }


def _remove_key_report(trades: list[dict[str, Any]], key_fn, *, label: str, limit: int = 15) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        key = str(key_fn(trade) or "unknown")
        by_key[key].append(trade)
    baseline_pf = _metrics(trades)["profit_factor"]
    rows: list[dict[str, Any]] = []
    for key, grouped in by_key.items():
        kept = [trade for trade in trades if trade not in grouped]
        kept_metrics = _metrics(kept, total=len(trades))
        group_metrics = _metrics(grouped, total=len(trades))
        rows.append(
            {
                "dimension": label,
                "removed": key,
                "removed_trades": len(grouped),
                "removed_metrics": group_metrics,
                "remaining_metrics": kept_metrics,
                "remaining_pf_delta": (
                    round(float(kept_metrics["profit_factor"]) - float(baseline_pf), 2)
                    if kept_metrics.get("profit_factor") is not None and baseline_pf is not None
                    else None
                ),
            }
        )
    rows.sort(key=lambda row: (float(row["remaining_metrics"].get("profit_factor") or 0.0), -row["removed_trades"]))
    return rows[:limit]


def _top_winner_removal(trades: list[dict[str, Any]], counts: list[int]) -> list[dict[str, Any]]:
    ranked = sorted(trades, key=lambda trade: _safe_float(trade.get("pnl_pct") or trade.get("net_pnl_pct")), reverse=True)
    rows: list[dict[str, Any]] = []
    for count in counts:
        removed = ranked[: int(count)]
        kept = ranked[int(count) :]
        rows.append(
            {
                "removed_top_trades": int(count),
                "removed_symbols": sorted({str(trade.get("ticker") or "") for trade in removed}),
                "removed_pnl_sum": round(sum(_pnl_values(removed)), 2),
                "remaining_metrics": _metrics(kept, total=len(trades)),
            }
        )
    return rows


def _slippage_stress(trades: list[dict[str, Any]], values: list[float]) -> list[dict[str, Any]]:
    return [
        {
            "slippage_pct_per_side": value,
            "total_slippage_pct_points": round(2.0 * value, 2),
            "metrics": _metrics(trades, slippage_pct_per_side=value),
        }
        for value in values
    ]


def build_intraday_robustness_report(
    result: dict[str, Any],
    *,
    train_days: int = 60,
    test_days: int = 20,
    min_exact_test_trades: int = 5,
    slippage_values: list[float] | None = None,
) -> dict[str, Any]:
    trades = [dict(trade) for trade in list(result.get("trades") or []) if dict(trade).get("priced", True)]
    exact_trades, research_trades = split_exact_and_research_trades(trades)
    unpriced = [dict(trade) for trade in list(result.get("unpriced_trades") or [])]
    if result.get("truth_source") != "historical_imported":
        status = "blocked_not_imported_intraday"
    elif result.get("imported_data_scope") not in {None, "trusted"}:
        status = "blocked_not_trusted_scope"
    else:
        status = "analyzed"
    slippage_values = slippage_values if slippage_values is not None else [0.0, 1.0, 2.5, 5.0]
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    accounting = contract_resolution_accounting(
        trades,
        priced_trade_count=result.get("priced_trade_count"),
        candidate_trade_count=result.get("candidate_trade_count"),
    )
    rolling = _rolling_windows(
        exact_trades,
        unpriced,
        train_days=int(train_days),
        test_days=int(test_days),
        min_exact_test_trades=int(min_exact_test_trades),
    )
    blockers: list[str] = []
    exact_metrics = _metrics(exact_trades)
    if exact_metrics["trades"] < 100:
        blockers.append("exact_trade_count_below_100_target")
    if not _profit_factor_is_defined(exact_metrics):
        blockers.append("exact_profit_factor_undefined")
    elif float(exact_metrics["profit_factor"]) < 1.0:
        blockers.append("exact_profit_factor_below_1")
    if exact_metrics["avg_pnl_pct"] <= 0:
        blockers.append("exact_avg_pnl_not_positive")
    if accounting["exact_contract_match_pct"] < 90.0:
        blockers.append("exact_contract_match_pct_below_90")
    if int(result.get("unpriced_trade_count") or 0) > 0:
        blockers.append("unpriced_candidates_remain")
    if rolling["status"] != "passed":
        blockers.append("rolling_oos_not_passed")
    return {
        "generated_at": generated_at,
        "status": "blocked" if blockers else status,
        "source": {
            "result_path": result.get("result_path"),
            "playbook": result.get("playbook"),
            "truth_source": result.get("truth_source"),
            "imported_data_scope": result.get("imported_data_scope"),
            "pricing_lane": result.get("pricing_lane") or result.get("effective_pricing_lane"),
            "candidate_trade_count": result.get("candidate_trade_count"),
            "priced_trade_count": result.get("priced_trade_count"),
            "unpriced_trade_count": result.get("unpriced_trade_count"),
            "quote_coverage_pct": result.get("quote_coverage_pct"),
        },
        "contract_accounting": accounting,
        "overall_priced_metrics": _metrics(trades),
        "exact_contract_metrics": exact_metrics,
        "research_only_metrics": _metrics(research_trades, total=len(trades)),
        "rolling_oos": rolling,
        "symbol_holdout_worst": _remove_key_report(exact_trades, lambda trade: trade.get("ticker"), label="ticker"),
        "month_holdout_worst": _remove_key_report(exact_trades, lambda trade: _month(_trade_date(trade)), label="month"),
        "date_holdout_worst": _remove_key_report(exact_trades, _trade_date, label="date"),
        "top_winner_removal": _top_winner_removal(exact_trades, [1, 2, 3, 5]),
        "slippage_stress": _slippage_stress(exact_trades, slippage_values),
        "blockers": blockers,
    }


def write_report(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    playbook = str((report.get("source") or {}).get("playbook") or "run")
    safe_playbook = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in playbook)[:40]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"imported_intraday_robustness_{safe_playbook}_{stamp}.json"
    latest_path = output_dir / "latest.json"
    latest_playbook_path = output_dir / f"latest_{safe_playbook}.json"
    serialized = json.dumps(report, indent=2, sort_keys=True)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    latest_playbook_path.write_text(serialized, encoding="utf8")
    return {
        "json": str(output_path),
        "latest_json": str(latest_path),
        "latest_playbook_json": str(latest_playbook_path),
    }


def _parse_slippage_values(raw: str) -> list[float]:
    values: list[float] = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        values.append(float(item))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Report exact-contract robustness for imported intraday replay JSON.")
    parser.add_argument("--run", default=str(DEFAULT_RUN), help="Existing replay JSON to analyze.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=20)
    parser.add_argument("--min-exact-test-trades", type=int, default=5)
    parser.add_argument("--slippage-pct-per-side", default="0,1,2.5,5")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_path = Path(args.run)
    result = json.loads(run_path.read_text(encoding="utf8"))
    report = build_intraday_robustness_report(
        result,
        train_days=int(args.train_days),
        test_days=int(args.test_days),
        min_exact_test_trades=int(args.min_exact_test_trades),
        slippage_values=_parse_slippage_values(args.slippage_pct_per_side),
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
                    "status": report.get("status"),
                    "blockers": report.get("blockers") or [],
                    "exact_contract_metrics": report.get("exact_contract_metrics"),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
