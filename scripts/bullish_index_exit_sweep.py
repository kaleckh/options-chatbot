from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import options_chatbot as oc
import wfo_optimizer as wfo


DEFAULT_CONFIGS = "90:55,70:55,50:55,70:45"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "profitability-lab" / "exit-sweeps"


def _safe_float(value: Any) -> float:
    return float(str(value).strip())


def parse_exit_configs(value: str) -> list[dict[str, float]]:
    configs: list[dict[str, float]] = []
    for raw_item in str(value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 2:
            raise ValueError(f"Exit config must be stop:time, got {item!r}")
        stop_loss_pct = _safe_float(parts[0])
        time_exit_pct = _safe_float(parts[1])
        if stop_loss_pct <= 0 or time_exit_pct <= 0:
            raise ValueError(f"Exit config values must be positive, got {item!r}")
        configs.append(
            {
                "spread_stop_loss_pct": stop_loss_pct,
                "spread_time_exit_pct": time_exit_pct,
            }
        )
    if not configs:
        raise ValueError("At least one exit config is required.")
    return configs


def _trade_exit_reasons(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        str(item.get("exit_reason") or "unknown"): {
            "trades": item.get("trades"),
            "avg_pnl_pct": item.get("avg_pnl_pct"),
            "profit_factor": item.get("profit_factor"),
        }
        for item in list(metrics.get("exit_reasons") or [])
        if isinstance(item, dict)
    }


def _summarize_replay(
    *,
    result: dict[str, Any],
    min_trades: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
) -> dict[str, Any]:
    if result.get("error"):
        return {"error": result.get("error")}
    matrix = wfo.build_options_experiment_matrix(
        result=result,
        min_trades=int(min_trades),
        min_profit_factor=float(min_profit_factor),
        min_directional_accuracy_pct=float(min_directional_accuracy_pct),
    )
    metrics = dict(matrix.get("authoritative_profitability_metrics") or {})
    gate = dict(matrix.get("authoritative_profitability_gate") or {})
    return {
        "trade_count": metrics.get("trade_count"),
        "profit_factor": metrics.get("profit_factor"),
        "avg_pnl_pct": metrics.get("avg_pnl_pct"),
        "directional_accuracy_pct": metrics.get("directional_accuracy_pct"),
        "gate_passed": gate.get("passed"),
        "gate_blockers": gate.get("blockers") or [],
        "exit_reasons": _trade_exit_reasons(metrics),
        "top_experiments": [
            {
                "label": item.get("label"),
                "category": item.get("category"),
                "trades": item.get("trades"),
                "profit_factor": item.get("profit_factor"),
                "avg_pnl_pct": item.get("avg_pnl_pct"),
                "passes_quality_bar": item.get("passes_quality_bar"),
            }
            for item in list(matrix.get("experiments") or [])[:5]
        ],
    }


def _set_index_spread_exit(*, stop_loss_pct: float, time_exit_pct: float) -> None:
    for module_profiles in (oc.STRATEGY_PROFILES, wfo.STRATEGY_PROFILES):
        index_profile = module_profiles.setdefault("index", {})
        spread = index_profile.setdefault("spread", {})
        spread["stop_loss_pct"] = float(stop_loss_pct)
        spread["time_exit_pct"] = float(time_exit_pct)


def run_exit_sweep(
    *,
    configs: list[dict[str, float]],
    variant: str = "bullish_index_calls_score70",
    lookback_years: int = 2,
    pricing_lane: str = "pessimistic",
    n_picks: int = 3,
    truth_lane: str = "historical_imported_daily",
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
) -> dict[str, Any]:
    original_profiles = copy.deepcopy(oc.STRATEGY_PROFILES)
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    try:
        for config in configs:
            stop_loss_pct = float(config["spread_stop_loss_pct"])
            time_exit_pct = float(config["spread_time_exit_pct"])
            _set_index_spread_exit(
                stop_loss_pct=stop_loss_pct,
                time_exit_pct=time_exit_pct,
            )
            result = wfo.run_historical_backtest(
                lookback_years=int(lookback_years),
                n_picks=int(n_picks),
                pricing_lane=pricing_lane,
                truth_lane=truth_lane,
                playbook=variant,
                allowed_directions=["call"],
            )
            results.append(
                {
                    "variant": variant,
                    "lookback_years": int(lookback_years),
                    "pricing_lane": pricing_lane,
                    "n_picks": int(n_picks),
                    "spread_stop_loss_pct": stop_loss_pct,
                    "spread_time_exit_pct": time_exit_pct,
                    "summary": _summarize_replay(
                        result=result,
                        min_trades=min_trades,
                        min_profit_factor=min_profit_factor,
                        min_directional_accuracy_pct=min_directional_accuracy_pct,
                    ),
                }
            )
    finally:
        oc.STRATEGY_PROFILES.clear()
        oc.STRATEGY_PROFILES.update(original_profiles)
        wfo.STRATEGY_PROFILES.clear()
        wfo.STRATEGY_PROFILES.update(original_profiles)

    ranked = sorted(
        results,
        key=lambda row: (
            float((row.get("summary") or {}).get("profit_factor") or 0.0),
            float((row.get("summary") or {}).get("avg_pnl_pct") or 0.0),
            int((row.get("summary") or {}).get("trade_count") or 0),
        ),
        reverse=True,
    )
    return {
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "variant": variant,
        "lookback_years": int(lookback_years),
        "pricing_lane": pricing_lane,
        "n_picks": int(n_picks),
        "results": results,
        "best": ranked[0] if ranked else None,
    }


def write_report(report: dict[str, Any], *, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("exit_sweep_%Y%m%dT%H%M%SZ")
    json_path = output_root / f"{run_id}.json"
    latest_path = output_root / "latest.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    latest_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded exit sweep for bullish index call variants.")
    parser.add_argument("--configs", default=DEFAULT_CONFIGS, help="Comma-separated stop:time configs, e.g. 90:55,70:45")
    parser.add_argument("--variant", default="bullish_index_calls_score70")
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--n-picks", type=int, default=3)
    parser.add_argument("--truth-lane", default="historical_imported_daily")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_exit_sweep(
        configs=parse_exit_configs(args.configs),
        variant=args.variant,
        lookback_years=args.lookback_years,
        pricing_lane=args.pricing_lane,
        n_picks=args.n_picks,
        truth_lane=args.truth_lane,
    )
    artifacts = write_report(report, output_root=Path(args.output_root))
    if args.json:
        print(json.dumps({"artifacts": artifacts, "report": report}, indent=2))
    else:
        print(json.dumps({"artifacts": artifacts, "best": report.get("best")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
