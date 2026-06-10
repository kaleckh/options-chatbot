from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exact_contract_accounting import is_exact_contract_resolution  # noqa: E402

DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "losing-window-audits"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _pct(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _trade_pnl(trade: dict[str, Any]) -> float:
    return float(_pct(trade.get("net_pnl_pct", trade.get("pnl_pct"))) or 0.0)


def _profit_factor(values: list[float]) -> float | None:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    if gross_loss <= 0:
        return None
    return round(gross_profit / gross_loss, 2)


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_trade_pnl(trade) for trade in trades]
    count = len(values)
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value < 0]
    return {
        "trades": count,
        "avg_pnl_pct": round(sum(values) / count, 2) if count else 0.0,
        "profit_factor": _profit_factor(values),
        "no_loss_sample": bool(values and not losers and winners),
        "win_rate_pct": round(len(winners) / count * 100, 1) if count else 0.0,
        "loss_count": len(losers),
        "avg_loss_pct": round(sum(losers) / len(losers), 2) if losers else 0.0,
        "worst_pnl_pct": round(min(values), 2) if values else 0.0,
        "best_pnl_pct": round(max(values), 2) if values else 0.0,
    }


def _bucket_score(value: Any) -> str:
    pct = _pct(value)
    if pct is None:
        return "unknown"
    if pct < 70:
        return "<70"
    if pct < 80:
        return "70-79"
    if pct < 90:
        return "80-89"
    return "90+"


def _bucket_dte(value: Any) -> str:
    dte = _pct(value)
    if dte is None:
        return "unknown"
    if dte <= 14:
        return "<=14"
    if dte <= 21:
        return "15-21"
    if dte <= 35:
        return "22-35"
    return "36+"


def _bucket_debit_pct(trade: dict[str, Any]) -> str:
    net_debit = _pct(trade.get("net_debit"))
    spread_width = _pct(trade.get("spread_width"))
    if net_debit is None or spread_width is None or spread_width <= 0:
        return "unknown"
    pct = net_debit / spread_width * 100
    if pct < 30:
        return "<30%"
    if pct < 45:
        return "30-44%"
    if pct < 60:
        return "45-59%"
    return "60%+"


def _bucket_spy_ret5(value: Any) -> str:
    pct = _pct(value)
    if pct is None:
        return "unknown"
    if pct < 0:
        return "<0%"
    if pct < 1:
        return "0-1%"
    if pct < 2:
        return "1-2%"
    return "2%+"


def _quarter(date_value: str) -> str:
    try:
        dt = datetime.fromisoformat(date_value[:10])
    except ValueError:
        return "unknown"
    return f"{dt.year}-Q{((dt.month - 1) // 3) + 1}"


def _month(date_value: str) -> str:
    return date_value[:7] if date_value else "unknown"


def _exact_trades(report: dict[str, Any]) -> list[dict[str, Any]]:
    authoritative_basis = str(report.get("authoritative_profitability_basis") or "").strip().lower()
    primary_judge_trade_class = str(report.get("primary_judge_trade_class") or "exact_archived_contract").strip().lower()
    return [
        trade
        for trade in list(report.get("trades") or [])
        if is_exact_contract_resolution(trade.get("entry_contract_resolution"))
        and (
            authoritative_basis != "archived_exact_contract_only"
            or str(trade.get("entry_contract_resolution") or "").strip().lower() == primary_judge_trade_class
        )
    ]


def _group_rows(
    trades: list[dict[str, Any]],
    label: str,
    key_fn: Callable[[dict[str, Any]], str],
    *,
    min_trades: int = 1,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[key_fn(trade)].append(trade)

    rows = []
    for key, group_trades in grouped.items():
        if len(group_trades) < min_trades:
            continue
        rows.append({"dimension": label, "key": key, **_metrics(group_trades)})
    rows.sort(key=lambda row: (row["avg_pnl_pct"], -row["trades"]))
    return rows


def _debit_pct_of_width_value(trade: dict[str, Any]) -> float | None:
    net_debit = _pct(trade.get("net_debit"))
    spread_width = _pct(trade.get("spread_width"))
    if net_debit is None or spread_width is None or spread_width <= 0:
        return None
    return net_debit / spread_width * 100


def _candidate_filter_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filters: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
        ("max_debit_pct_of_width", "debit<60%", lambda trade: (_debit_pct_of_width_value(trade) or 999.0) < 60),
        ("max_debit_pct_of_width", "debit<55%", lambda trade: (_debit_pct_of_width_value(trade) or 999.0) < 55),
        ("max_debit_pct_of_width", "debit<50%", lambda trade: (_debit_pct_of_width_value(trade) or 999.0) < 50),
        ("quality_score", "quality>=90", lambda trade: (_pct(trade.get("quality_score")) or 0.0) >= 90),
        ("direction_score", "direction>=90", lambda trade: (_pct(trade.get("direction_score")) or 0.0) >= 90),
        (
            "combined",
            "quality>=90,debit<60%",
            lambda trade: (_pct(trade.get("quality_score")) or 0.0) >= 90
            and (_debit_pct_of_width_value(trade) or 999.0) < 60,
        ),
        (
            "combined",
            "spy,debit<60%",
            lambda trade: trade.get("ticker") == "SPY" and (_debit_pct_of_width_value(trade) or 999.0) < 60,
        ),
        (
            "combined",
            "qqq,debit<60%",
            lambda trade: trade.get("ticker") == "QQQ" and (_debit_pct_of_width_value(trade) or 999.0) < 60,
        ),
    ]
    rows = []
    for dimension, key, filter_fn in filters:
        filtered = [trade for trade in trades if filter_fn(trade)]
        rows.append({"dimension": dimension, "key": key, **_metrics(filtered)})
    rows.sort(key=lambda row: (-float(row["profit_factor"] or 0.0), -row["avg_pnl_pct"], -row["trades"]))
    return rows


def build_losing_window_audit(report_path: Path, *, min_group_trades: int = 3) -> dict[str, Any]:
    report = _read_json(report_path)
    trades = _exact_trades(report)
    losing_trades = [trade for trade in trades if _trade_pnl(trade) < 0]

    grouped_rows: list[dict[str, Any]] = []
    grouped_rows.extend(_group_rows(trades, "month", lambda trade: _month(str(trade.get("date") or "")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "quarter", lambda trade: _quarter(str(trade.get("date") or "")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "ticker", lambda trade: str(trade.get("ticker") or "unknown"), min_trades=1))
    grouped_rows.extend(_group_rows(trades, "exit_reason", lambda trade: str(trade.get("exit_reason") or "unknown"), min_trades=1))
    grouped_rows.extend(_group_rows(trades, "quality_score", lambda trade: _bucket_score(trade.get("quality_score")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "direction_score", lambda trade: _bucket_score(trade.get("direction_score")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "tech_score", lambda trade: _bucket_score(trade.get("tech_score")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "dte", lambda trade: _bucket_dte(trade.get("dte")), min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "debit_pct_of_width", _bucket_debit_pct, min_trades=min_group_trades))
    grouped_rows.extend(_group_rows(trades, "spy_ret5", lambda trade: _bucket_spy_ret5(trade.get("spy_ret5")), min_trades=min_group_trades))

    worst_groups = sorted(
        grouped_rows,
        key=lambda row: (row["avg_pnl_pct"], -row["loss_count"], -row["trades"]),
    )[:20]
    worst_trades = sorted(losing_trades, key=_trade_pnl)[:20]

    return {
        "source_run": str(report_path),
        "playbook": report.get("playbook"),
        "pricing_lane": report.get("pricing_lane") or report.get("effective_pricing_lane"),
        "lookback_years": report.get("lookback_years"),
        "n_picks": report.get("n_picks"),
        "exact_trade_metrics": _metrics(trades),
        "losing_trade_count": len(losing_trades),
        "worst_groups": worst_groups,
        "candidate_filters": _candidate_filter_rows(trades),
        "worst_trades": [
            {
                "date": trade.get("date"),
                "exit_date": trade.get("exit_date"),
                "ticker": trade.get("ticker"),
                "strategy_type": trade.get("strategy_type"),
                "exit_reason": trade.get("exit_reason"),
                "net_pnl_pct": round(_trade_pnl(trade), 2),
                "stock_move_pct": _pct(trade.get("stock_move_pct")),
                "quality_score": _pct(trade.get("quality_score")),
                "direction_score": _pct(trade.get("direction_score")),
                "tech_score": _pct(trade.get("tech_score")),
                "spy_ret5": _pct(trade.get("spy_ret5")),
                "dte": _pct(trade.get("dte")),
                "net_debit": _pct(trade.get("net_debit")),
                "spread_width": _pct(trade.get("spread_width")),
            }
            for trade in worst_trades
        ],
    }


def _latest_matching_run(runs_dir: Path, playbook: str) -> Path:
    matches = sorted(
        runs_dir.glob(f"*{playbook}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No validation runs found for playbook {playbook!r} under {runs_dir}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit where a profitability replay loses money.")
    parser.add_argument("--run", help="Specific options-validation run JSON to audit.")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--playbook", default="bullish_index_calls_score70")
    parser.add_argument("--min-group-trades", type=int, default=3)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.run) if args.run else _latest_matching_run(Path(args.runs_dir), args.playbook)
    audit = build_losing_window_audit(report_path, min_group_trades=args.min_group_trades)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    source_label = report_path.stem.replace(" ", "_")
    output_path = output_dir / f"losing_window_audit_{stamp}_{source_label}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(audit, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")

    result = {
        "output": str(output_path),
        "latest": str(latest_path),
        "source_run": audit["source_run"],
        "exact_trade_metrics": audit["exact_trade_metrics"],
        "top_worst_groups": audit["worst_groups"][:5],
        "top_candidate_filters": audit["candidate_filters"][:5],
        "top_worst_trades": audit["worst_trades"][:5],
    }
    print(json.dumps(audit if args.json else result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
