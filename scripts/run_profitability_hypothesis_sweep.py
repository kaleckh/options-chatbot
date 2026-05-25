from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exact_contract_accounting import is_exact_contract_resolution

DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "hypothesis-sweeps"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pnl(trade: dict[str, Any]) -> float:
    return _num(trade.get("net_pnl_pct", trade.get("pnl_pct")))


def _debit_pct_of_width(trade: dict[str, Any]) -> float:
    spread_width = _num(trade.get("spread_width"))
    if spread_width <= 0:
        return 999.0
    return _num(trade.get("net_debit")) / spread_width * 100.0


def _exact_trades(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        trade
        for trade in list(report.get("trades") or [])
        if is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]


def _priced_trades(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [trade for trade in list(report.get("trades") or []) if trade.get("priced", True)]


def _trades_for_lens(report: dict[str, Any], lens: str) -> list[dict[str, Any]]:
    normalized = str(lens or "exact").strip().lower().replace("_", "-")
    if normalized == "all-priced":
        return _priced_trades(report)
    if normalized == "exact":
        return _exact_trades(report)
    raise ValueError(f"Unsupported hypothesis sweep lens: {lens!r}")


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_pnl(trade) for trade in trades]
    count = len(values)
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    profit_factor = None
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 999.0
    return {
        "trades": count,
        "avg_pnl_pct": round(sum(values) / count, 2) if count else 0.0,
        "profit_factor": profit_factor,
        "win_rate_pct": round(sum(1 for value in values if value > 0) / count * 100, 1) if count else 0.0,
        "worst_pnl_pct": round(min(values), 2) if values else 0.0,
        "best_pnl_pct": round(max(values), 2) if values else 0.0,
    }


def _source_run_identity(report_path: Path) -> str:
    return _path_identity(report_path)


def _path_identity(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _fingerprint_payload(
    *,
    source_run: str,
    min_trades: int,
    min_profit_factor: float,
    hypothesis_ids: list[str],
) -> str:
    payload = {
        "source_run": source_run.replace("\\", "/"),
        "min_trades": int(min_trades),
        "min_profit_factor": float(min_profit_factor),
        "hypothesis_ids": sorted(hypothesis_ids),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf8")).hexdigest()


def build_sweep_fingerprint(
    report_path: Path | str,
    *,
    min_trades: int,
    min_profit_factor: float,
    lens: str = "exact",
    hypotheses: tuple[dict[str, Any], ...] | None = None,
) -> str:
    hypothesis_rows = hypotheses if hypotheses is not None else HYPOTHESES
    return _fingerprint_payload(
        source_run=_source_run_identity(Path(report_path)),
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
        hypothesis_ids=[f"lens={str(lens).strip().lower()}"] + [str(hypothesis["id"]) for hypothesis in hypothesis_rows],
    )


def _verdict(metrics: dict[str, Any], *, min_trades: int, min_profit_factor: float) -> str:
    trades = int(metrics.get("trades") or 0)
    profit_factor = metrics.get("profit_factor")
    avg_pnl_pct = _num(metrics.get("avg_pnl_pct"))
    if trades < min_trades:
        return "sample_too_small"
    if profit_factor is not None and float(profit_factor) >= min_profit_factor and avg_pnl_pct > 0:
        return "candidate_for_replay"
    if profit_factor is not None and float(profit_factor) >= 1.0 and avg_pnl_pct > 0:
        return "watch"
    return "reject"


HYPOTHESES: tuple[dict[str, Any], ...] = (
    {
        "id": "max_debit_lt_60",
        "description": "Reject vertical spreads with debit >= 60% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 60,
    },
    {
        "id": "max_debit_lt_55",
        "description": "Reject vertical spreads with debit >= 55% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55,
    },
    {
        "id": "max_debit_lt_50",
        "description": "Reject vertical spreads with debit >= 50% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 50,
    },
    {
        "id": "spy_only",
        "description": "Keep only SPY exact-contract bullish index call spreads.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "SPY",
    },
    {
        "id": "qqq_only",
        "description": "Keep only QQQ exact-contract bullish index call spreads.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "QQQ",
    },
    {
        "id": "spy_max_debit_lt_60",
        "description": "Keep SPY and reject debit >= 60% of spread width.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "SPY"
        and _debit_pct_of_width(trade) < 60,
    },
    {
        "id": "qqq_max_debit_lt_60",
        "description": "Keep QQQ and reject debit >= 60% of spread width.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "QQQ"
        and _debit_pct_of_width(trade) < 60,
    },
    {
        "id": "direction_ge_90",
        "description": "Require direction score >= 90.",
        "filter": lambda trade: _num(trade.get("direction_score")) >= 90,
    },
    {
        "id": "max_debit_lt_50_tech_lt_95",
        "description": "Require debit < 50% of width and avoid extreme tech score >= 95.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 50 and _num(trade.get("tech_score")) < 95,
    },
    {
        "id": "max_debit_lt_55_spy_ret5_ge_1",
        "description": "Require debit < 55% of width and SPY five-day return >= 1%.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55 and _num(trade.get("spy_ret5")) >= 1,
    },
)


HYPOTHESES_BATCH_2: tuple[dict[str, Any], ...] = (
    {
        "id": "max_debit_lt_52_5",
        "description": "Reject vertical spreads with debit >= 52.5% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 52.5,
    },
    {
        "id": "max_debit_lt_47_5",
        "description": "Reject vertical spreads with debit >= 47.5% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 47.5,
    },
    {
        "id": "max_debit_lt_45",
        "description": "Reject vertical spreads with debit >= 45% of spread width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 45,
    },
    {
        "id": "max_debit_lt_55_tech_lt_95",
        "description": "Require debit < 55% of width and avoid extreme tech score >= 95.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55 and _num(trade.get("tech_score")) < 95,
    },
    {
        "id": "max_debit_lt_50_spy_ret5_ge_1",
        "description": "Require debit < 50% of width and SPY five-day return >= 1%.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 50 and _num(trade.get("spy_ret5")) >= 1,
    },
    {
        "id": "max_debit_lt_50_spy_ret5_1_to_2",
        "description": "Require debit < 50% of width and SPY five-day return from 1% to <2%.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 50
        and 1 <= _num(trade.get("spy_ret5")) < 2,
    },
    {
        "id": "max_debit_lt_55_direction_ge_85",
        "description": "Require debit < 55% of width and direction score >= 85.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55 and _num(trade.get("direction_score")) >= 85,
    },
    {
        "id": "max_debit_lt_55_direction_ge_90",
        "description": "Require debit < 55% of width and direction score >= 90.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55 and _num(trade.get("direction_score")) >= 90,
    },
    {
        "id": "max_debit_lt_55_quality_ge_90",
        "description": "Require debit < 55% of width and quality score >= 90.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55 and _num(trade.get("quality_score")) >= 90,
    },
    {
        "id": "max_debit_lt_55_quality_80_to_90",
        "description": "Require debit < 55% of width and quality score from 80 to <90.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55
        and 80 <= _num(trade.get("quality_score")) < 90,
    },
)


def _signal_ret5(trade: dict[str, Any]) -> float:
    return _num(trade.get("signal_ret5", trade.get("ret5")))


def _signal_ret20(trade: dict[str, Any]) -> float:
    return _num(trade.get("signal_ret20", trade.get("ret20")))


HYPOTHESES_LANE_A_PULLBACK_GATES: tuple[dict[str, Any], ...] = (
    {
        "id": "lane_a_max_debit_lt_55",
        "description": "Lane A pre-registered gate: reject vertical spreads with debit >= 55% of width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 55,
    },
    {
        "id": "lane_a_max_debit_lt_50",
        "description": "Lane A pre-registered gate: reject vertical spreads with debit >= 50% of width.",
        "filter": lambda trade: _debit_pct_of_width(trade) < 50,
    },
    {
        "id": "lane_a_ret5_minus3_to_0",
        "description": "Lane A pre-registered gate: keep pullbacks with five-day return from -3% to 0%.",
        "filter": lambda trade: -3.0 <= _signal_ret5(trade) <= 0.0,
    },
    {
        "id": "lane_a_ret5_minus2p5_to_minus0p5",
        "description": "Lane A pre-registered gate: keep pullbacks with five-day return from -2.5% to -0.5%.",
        "filter": lambda trade: -2.5 <= _signal_ret5(trade) <= -0.5,
    },
    {
        "id": "lane_a_ret20_ge_3",
        "description": "Lane A pre-registered gate: require 20-day trend return >= 3%.",
        "filter": lambda trade: _signal_ret20(trade) >= 3.0,
    },
    {
        "id": "lane_a_ret20_ge_4",
        "description": "Lane A pre-registered gate: require 20-day trend return >= 4%.",
        "filter": lambda trade: _signal_ret20(trade) >= 4.0,
    },
    {
        "id": "lane_a_direction_ge_70",
        "description": "Lane A pre-registered gate: require direction score >= 70.",
        "filter": lambda trade: _num(trade.get("direction_score")) >= 70,
    },
    {
        "id": "lane_a_quality_ge_60",
        "description": "Lane A pre-registered gate: require quality score >= 60.",
        "filter": lambda trade: _num(trade.get("quality_score")) >= 60,
    },
    {
        "id": "lane_a_spy_only",
        "description": "Lane A pre-registered split: SPY exact-contract pullback trades only.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "SPY",
    },
    {
        "id": "lane_a_qqq_only",
        "description": "Lane A pre-registered split: QQQ exact-contract pullback trades only.",
        "filter": lambda trade: str(trade.get("ticker") or "").upper() == "QQQ",
    },
)


HYPOTHESIS_SUITES: dict[str, tuple[dict[str, Any], ...]] = {
    "batch1": HYPOTHESES,
    "batch2": HYPOTHESES_BATCH_2,
    "lane_a_pullback_gates": HYPOTHESES_LANE_A_PULLBACK_GATES,
}


def build_hypothesis_sweep(
    report_path: Path,
    *,
    min_trades: int = 20,
    min_profit_factor: float = 1.2,
    lens: str = "exact",
    hypotheses: tuple[dict[str, Any], ...] = HYPOTHESES,
    hypothesis_suite: str = "custom",
) -> dict[str, Any]:
    report = _read_json(report_path)
    trades = _trades_for_lens(report, lens)
    baseline = _metrics(trades)
    results = []
    for hypothesis in hypotheses:
        filter_fn: Callable[[dict[str, Any]], bool] = hypothesis["filter"]
        filtered = [trade for trade in trades if filter_fn(trade)]
        metrics = _metrics(filtered)
        results.append(
            {
                "id": hypothesis["id"],
                "description": hypothesis["description"],
                "metrics": metrics,
                "coverage_pct": round((metrics["trades"] / baseline["trades"] * 100.0), 1)
                if baseline["trades"]
                else 0.0,
                "verdict": _verdict(metrics, min_trades=min_trades, min_profit_factor=min_profit_factor),
            }
        )
    results.sort(
        key=lambda item: (
            {"candidate_for_replay": 3, "watch": 2, "sample_too_small": 1, "reject": 0}.get(item["verdict"], 0),
            float(item["metrics"].get("profit_factor") or 0.0),
            float(item["metrics"].get("avg_pnl_pct") or 0.0),
            int(item["metrics"].get("trades") or 0),
        ),
        reverse=True,
    )
    return {
        "source_run": str(report_path),
        "source_run_identity": _source_run_identity(report_path),
        "fingerprint": build_sweep_fingerprint(
            report_path,
            min_trades=min_trades,
            min_profit_factor=min_profit_factor,
            lens=lens,
            hypotheses=hypotheses,
        ),
        "lens": str(lens or "exact"),
        "hypothesis_suite": hypothesis_suite,
        "playbook": report.get("playbook"),
        "pricing_lane": report.get("pricing_lane") or report.get("effective_pricing_lane"),
        "lookback_years": report.get("lookback_years"),
        "n_picks": report.get("n_picks"),
        "baseline": baseline,
        "min_trades": min_trades,
        "min_profit_factor": min_profit_factor,
        "hypothesis_count": len(results),
        "results": results,
    }


def find_duplicate_sweep(
    output_dir: Path,
    fingerprint: str,
    *,
    report_path: Path | str | None = None,
    min_trades: int | None = None,
    min_profit_factor: float | None = None,
    lens: str = "exact",
    hypotheses: tuple[dict[str, Any], ...] | None = None,
) -> Path | None:
    expected_legacy_fingerprint = None
    if report_path is not None and min_trades is not None and min_profit_factor is not None:
        expected_legacy_fingerprint = build_sweep_fingerprint(
            Path(report_path),
            min_trades=min_trades,
            min_profit_factor=min_profit_factor,
            lens=lens,
            hypotheses=hypotheses,
        )
    for sweep_path in sorted(output_dir.glob("hypothesis_sweep_*.json")):
        try:
            sweep = _read_json(sweep_path)
        except (OSError, json.JSONDecodeError):
            continue
        if sweep.get("fingerprint") == fingerprint:
            return sweep_path
        if expected_legacy_fingerprint is None:
            continue
        source_run = sweep.get("source_run_identity") or sweep.get("source_run")
        if not source_run:
            continue
        hypothesis_ids = [str(item.get("id")) for item in list(sweep.get("results") or [])]
        if not hypothesis_ids:
            continue
        legacy_lens = str(sweep.get("lens") or lens or "exact").strip().lower()
        hypothesis_ids = [f"lens={legacy_lens}"] + hypothesis_ids
        legacy_fingerprint = _fingerprint_payload(
            source_run=_path_identity(Path(str(source_run))),
            min_trades=int(sweep.get("min_trades") or 0),
            min_profit_factor=float(sweep.get("min_profit_factor") or 0.0),
            hypothesis_ids=hypothesis_ids,
        )
        if legacy_fingerprint == expected_legacy_fingerprint:
            return sweep_path
    return None


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
    parser = argparse.ArgumentParser(description="Run the next fixed set of profitability hypotheses.")
    parser.add_argument("--run", help="Specific options-validation run JSON to sweep.")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--playbook", default="bullish_index_calls_score70")
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-profit-factor", type=float, default=1.2)
    parser.add_argument("--lens", default="exact", choices=["exact", "all-priced"], help="Trade lens: exact proof only, or all priced trades as research-only proxy.")
    parser.add_argument("--suite", default="batch1", choices=sorted(HYPOTHESIS_SUITES), help="Hypothesis suite to run.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Run even when an identical sweep fingerprint already exists.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.run) if args.run else _latest_matching_run(Path(args.runs_dir), args.playbook)
    hypotheses = HYPOTHESIS_SUITES[args.suite]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = build_sweep_fingerprint(
        report_path,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        lens=args.lens,
        hypotheses=hypotheses,
    )
    duplicate = find_duplicate_sweep(
        output_dir,
        fingerprint,
        report_path=report_path,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        lens=args.lens,
        hypotheses=hypotheses,
    )
    if duplicate is not None and not args.force:
        result = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "source_run": str(report_path),
            "fingerprint": fingerprint,
            "hint": "Use --force to rerun this exact hypothesis sweep.",
        }
        print(json.dumps(result, indent=2))
        return 0

    sweep = build_hypothesis_sweep(
        report_path,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        lens=args.lens,
        hypotheses=hypotheses,
        hypothesis_suite=args.suite,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    source_label = report_path.stem.replace(" ", "_")
    output_path = output_dir / f"hypothesis_sweep_{stamp}_{source_label}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(sweep, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")

    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "source_run": sweep["source_run"],
        "lens": sweep["lens"],
        "hypothesis_suite": sweep["hypothesis_suite"],
        "fingerprint": sweep["fingerprint"],
        "baseline": sweep["baseline"],
        "hypothesis_count": sweep["hypothesis_count"],
        "top_results": sweep["results"][:10],
    }
    print(json.dumps(sweep if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
