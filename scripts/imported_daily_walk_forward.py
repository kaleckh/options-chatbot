from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exact_contract_accounting import contract_resolution_accounting, split_exact_and_research_trades
import wfo_optimizer as wfo


DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "imported-daily-wfo"


def _trade_date(trade: dict[str, Any]) -> str:
    return str(trade.get("date") or trade.get("entry_date") or "")[:10]


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _profit_factor(values: Iterable[float]) -> float:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return 999.0 if wins else 0.0
    return round(sum(wins) / gross_loss, 2)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "hit", "correct"}


def _metrics(trades: list[dict[str, Any]], *, total_trades: int | None = None) -> dict[str, Any]:
    pnls = [_safe_number(trade.get("pnl_pct")) for trade in trades]
    wins = [value for value in pnls if value > 0]
    directional = [trade for trade in trades if _is_truthy(trade.get("directional_correct"))]
    total = int(total_trades if total_trades is not None else len(trades))
    return {
        "trade_count": len(trades),
        "share_of_total_pct": round(len(trades) / max(total, 1) * 100.0, 1) if total else 0.0,
        "win_rate_pct": round(len(wins) / max(len(trades), 1) * 100.0, 1) if trades else 0.0,
        "directional_accuracy_pct": round(len(directional) / max(len(trades), 1) * 100.0, 1) if trades else 0.0,
        "profit_factor": _profit_factor(pnls),
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
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


def build_imported_daily_walk_forward_validation(
    replay_result: dict[str, Any],
    *,
    train_days: int = 60,
    test_days: int = 20,
    min_exact_test_trades: int = 5,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    if replay_result.get("error"):
        return {
            "generated_at": generated_at,
            "status": "blocked_replay_error",
            "error": replay_result.get("error"),
            "source_replay": {
                "truth_source": replay_result.get("truth_source"),
                "playbook": replay_result.get("playbook"),
                "imported_data_scope": replay_result.get("imported_data_scope"),
                "source_labels_required": replay_result.get("source_labels_required"),
            },
        }

    trades = [dict(trade) for trade in list(replay_result.get("trades") or []) if _trade_date(dict(trade))]
    unpriced_trades = [
        dict(trade)
        for trade in list(replay_result.get("unpriced_trades") or [])
        if _trade_date(dict(trade))
    ]
    candidate_rows = trades + unpriced_trades
    dates = sorted({_trade_date(trade) for trade in candidate_rows})
    windows = _window_dates(dates, train_days=int(train_days), test_days=int(test_days))
    accounting = contract_resolution_accounting(
        trades,
        priced_trade_count=replay_result.get("priced_trade_count"),
        candidate_trade_count=replay_result.get("candidate_trade_count"),
    )
    frozen_universe = sorted({str(symbol).upper() for symbol in list(replay_result.get("validation_universe") or []) if str(symbol).strip()})
    research_mode = bool(replay_result.get("research_imported_data_allowed"))
    base = {
        "generated_at": generated_at,
        "truth_source": replay_result.get("truth_source"),
        "playbook": replay_result.get("playbook"),
        "pricing_lane": replay_result.get("pricing_lane") or replay_result.get("effective_pricing_lane"),
        "authoritative_profitability_basis": (
            "research_exact_contract_only_not_promotion_ready" if research_mode else "exact_contract_only"
        ),
        "imported_data_scope": replay_result.get("imported_data_scope"),
        "research_mode": research_mode,
        "promotion_policy": "research_only_not_proof_grade" if research_mode else "trusted_proof_gate",
        "frozen_universe": frozen_universe,
        "train_days": int(train_days),
        "test_days": int(test_days),
        "min_exact_test_trades": int(min_exact_test_trades),
        "source_contract_accounting": accounting,
        "source_trade_count": len(trades),
        "source_unpriced_trade_count": len(unpriced_trades),
        "source_candidate_trade_count": len(candidate_rows),
        "source_date_count": len(dates),
    }
    if not windows:
        return {
            **base,
            "status": "blocked_insufficient_oos_dates",
            "windows": [],
            "blockers": [
                f"need_at_least_{int(train_days) + int(test_days)}_trade_dates_for_one_window",
            ],
        }

    window_rows: list[dict[str, Any]] = []
    for index, (train_dates, test_dates) in enumerate(windows, start=1):
        train_set = set(train_dates)
        test_set = set(test_dates)
        train_trades = [trade for trade in trades if _trade_date(trade) in train_set]
        test_trades = [trade for trade in trades if _trade_date(trade) in test_set]
        train_unpriced = [trade for trade in unpriced_trades if _trade_date(trade) in train_set]
        test_unpriced = [trade for trade in unpriced_trades if _trade_date(trade) in test_set]
        exact_train, research_train = split_exact_and_research_trades(train_trades)
        exact_test, research_test = split_exact_and_research_trades(test_trades)
        gate_blockers: list[str] = []
        test_candidate_count = len(test_trades) + len(test_unpriced)
        train_candidate_count = len(train_trades) + len(train_unpriced)
        exact_test_metrics = _metrics(exact_test, total_trades=test_candidate_count)
        test_quote_coverage_pct = (
            round(len(test_trades) / max(test_candidate_count, 1) * 100.0, 1)
            if test_candidate_count
            else 0.0
        )
        if test_unpriced:
            gate_blockers.append("unpriced_test_candidates_present")
        if exact_test_metrics["trade_count"] < int(min_exact_test_trades):
            gate_blockers.append("exact_test_trade_count_below_floor")
        if exact_test_metrics["profit_factor"] < 1.0:
            gate_blockers.append("exact_test_profit_factor_below_1")
        if exact_test_metrics["avg_pnl_pct"] <= 0:
            gate_blockers.append("exact_test_avg_pnl_not_positive")
        window_rows.append(
            {
                "window": index,
                "train_start": train_dates[0],
                "train_end": train_dates[-1],
                "test_start": test_dates[0],
                "test_end": test_dates[-1],
                "train": _metrics(train_trades),
                "test": _metrics(test_trades),
                "exact_train": _metrics(exact_train, total_trades=train_candidate_count),
                "exact_test": exact_test_metrics,
                "research_train_trade_count": len(research_train),
                "research_test_trade_count": len(research_test),
                "unpriced_train_candidate_count": len(train_unpriced),
                "unpriced_test_candidate_count": len(test_unpriced),
                "train_candidate_count": train_candidate_count,
                "test_candidate_count": test_candidate_count,
                "test_quote_coverage_pct": test_quote_coverage_pct,
                "gate_passed": not gate_blockers,
                "gate_blockers": gate_blockers,
            }
        )

    failed = [row for row in window_rows if not row["gate_passed"]]
    return {
        **base,
        "status": "passed" if not failed else "watch",
        "window_count": len(window_rows),
        "passed_window_count": len(window_rows) - len(failed),
        "failed_window_count": len(failed),
        "windows": window_rows,
        "blockers": sorted({blocker for row in failed for blocker in row["gate_blockers"]}),
    }


def run_imported_daily_walk_forward_validation(
    *,
    playbook: str,
    lookback_years: int,
    n_picks: int,
    pricing_lane: str,
    train_days: int,
    test_days: int,
    min_exact_test_trades: int,
    min_imported_calendar_dates: int = 100,
    source_labels: str | None = None,
    all_source_labels: bool = False,
    allow_research_data: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if db_path is not None:
        os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(db_path)
    source_label_override = "" if all_source_labels else source_labels
    replay = wfo.run_historical_backtest(
        lookback_years=int(lookback_years),
        n_picks=int(n_picks),
        pricing_lane=pricing_lane,
        truth_lane=wfo.IMPORTED_DAILY_TRUTH_SOURCE,
        playbook=playbook,
        save_result=False,
        min_imported_calendar_dates=int(min_imported_calendar_dates),
        historical_source_labels=source_label_override,
        allow_research_imported_data=bool(allow_research_data),
    )
    report = build_imported_daily_walk_forward_validation(
        replay,
        train_days=int(train_days),
        test_days=int(test_days),
        min_exact_test_trades=int(min_exact_test_trades),
    )
    if allow_research_data:
        report["research_mode"] = True
        report["promotion_policy"] = "research_only_not_proof_grade"
    return report


def write_report(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("imported_daily_wfo_%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{stamp}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(report, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    return {"json": str(output_path), "latest_json": str(latest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run imported-daily rolling OOS validation with exact-contract authority.")
    parser.add_argument("--playbook", default="bullish_pullback_observation")
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--n-picks", type=int, default=3)
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=20)
    parser.add_argument("--min-exact-test-trades", type=int, default=5)
    parser.add_argument("--min-imported-calendar-dates", type=int, default=100)
    parser.add_argument("--source-labels", help="Override playbook historical source labels for this run.")
    parser.add_argument(
        "--all-source-labels",
        action="store_true",
        help="Use every imported source in scope instead of the playbook source-label allowlist.",
    )
    parser.add_argument(
        "--allow-research-data",
        action="store_true",
        help="Allow research-grade imported data for exploratory replay. Does not make results promotion-ready.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--db-path", help="Historical options SQLite DB path to use for imported replay.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_imported_daily_walk_forward_validation(
        playbook=args.playbook,
        lookback_years=args.lookback_years,
        n_picks=args.n_picks,
        pricing_lane=args.pricing_lane,
        train_days=args.train_days,
        test_days=args.test_days,
        min_exact_test_trades=args.min_exact_test_trades,
        min_imported_calendar_dates=args.min_imported_calendar_dates,
        source_labels=args.source_labels,
        all_source_labels=bool(args.all_source_labels),
        allow_research_data=bool(args.allow_research_data),
        db_path=args.db_path,
    )
    artifacts = write_report(report, output_dir=Path(args.output_dir))
    payload = {"artifacts": artifacts, "report": report}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        compact = {
            "artifacts": artifacts,
            "status": report.get("status"),
            "window_count": report.get("window_count", 0),
            "failed_window_count": report.get("failed_window_count", 0),
            "blockers": report.get("blockers") or [],
        }
        print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
