from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bullish_index_exit_sweep import parse_exit_configs, run_exit_sweep, write_report as write_exit_report
from scripts.run_profitability_hypothesis_sweep import (
    HYPOTHESIS_SUITES,
    build_hypothesis_sweep,
)


LANE_A_PLAYBOOK = "bullish_pullback_observation"
LANE_A_GATE_SUITE = "lane_a_pullback_gates"
LANE_A_EXIT_CONFIGS = "90:55,70:55,50:55,70:45,50:45"
DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation"


def lane_a_pre_registered_plan() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "playbook": LANE_A_PLAYBOOK,
        "truth_lane": "historical_imported_daily",
        "authoritative_profitability_basis": "exact_contract_only",
        "gate_suite": LANE_A_GATE_SUITE,
        "gate_hypotheses": [
            {
                "id": item["id"],
                "description": item["description"],
            }
            for item in HYPOTHESIS_SUITES[LANE_A_GATE_SUITE]
        ],
        "exit_configs": parse_exit_configs(LANE_A_EXIT_CONFIGS),
        "registration_policy": (
            "Use these gates and exits before looking at the next replay result; nearest-listed rows remain research-only."
        ),
    }


def _latest_matching_run(runs_dir: Path) -> Path:
    matches = sorted(
        Path(runs_dir).glob(f"*{LANE_A_PLAYBOOK}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No Lane A validation runs found under {runs_dir}")
    return matches[0]


def run_lane_a_gate_sweep(
    *,
    run_path: Path,
    min_trades: int = 5,
    min_profit_factor: float = 1.05,
    lens: str = "exact",
) -> dict[str, Any]:
    return build_hypothesis_sweep(
        run_path,
        min_trades=int(min_trades),
        min_profit_factor=float(min_profit_factor),
        lens=lens,
        hypotheses=HYPOTHESIS_SUITES[LANE_A_GATE_SUITE],
        hypothesis_suite=LANE_A_GATE_SUITE,
    )


def run_lane_a_exit_sweep(
    *,
    lookback_years: int = 2,
    pricing_lane: str = "pessimistic",
    n_picks: int = 3,
    min_trades: int = 5,
    min_profit_factor: float = 1.05,
    truth_lane: str = "historical_imported",
    min_imported_calendar_dates: int = 252,
    historical_source_labels: str | None = "thetadata_opra_nbbo_1m",
) -> dict[str, Any]:
    return run_exit_sweep(
        configs=parse_exit_configs(LANE_A_EXIT_CONFIGS),
        variant=LANE_A_PLAYBOOK,
        lookback_years=int(lookback_years),
        pricing_lane=pricing_lane,
        n_picks=int(n_picks),
        truth_lane=truth_lane,
        min_trades=int(min_trades),
        min_profit_factor=float(min_profit_factor),
        min_imported_calendar_dates=int(min_imported_calendar_dates),
        historical_source_labels=historical_source_labels,
    )


def write_gate_report(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("lane_a_gate_sweep_%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{stamp}.json"
    latest_path = output_dir / "latest_gate_sweep.json"
    serialized = json.dumps(report, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    return {"json": str(output_path), "latest_json": str(latest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pre-registered Lane A gate and exit sweeps.")
    parser.add_argument("--run", help="Existing Lane A replay JSON for gate hypotheses.")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--skip-gates", action="store_true")
    parser.add_argument("--run-exits", action="store_true", help="Also run the heavier replay-backed exit sweep.")
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--n-picks", type=int, default=3)
    parser.add_argument("--truth-lane", default="historical_imported")
    parser.add_argument("--min-imported-calendar-dates", type=int, default=252)
    parser.add_argument("--historical-source-labels", default="thetadata_opra_nbbo_1m")
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--min-profit-factor", type=float, default=1.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    payload: dict[str, Any] = {"plan": lane_a_pre_registered_plan(), "artifacts": {}}
    if not args.skip_gates:
        run_path = Path(args.run) if args.run else _latest_matching_run(Path(args.runs_dir))
        gate_report = run_lane_a_gate_sweep(
            run_path=run_path,
            min_trades=args.min_trades,
            min_profit_factor=args.min_profit_factor,
        )
        payload["gate_sweep"] = gate_report
        payload["artifacts"]["gate_sweep"] = write_gate_report(gate_report, output_dir=output_dir)
    if args.run_exits:
        exit_report = run_lane_a_exit_sweep(
            lookback_years=args.lookback_years,
            pricing_lane=args.pricing_lane,
            n_picks=args.n_picks,
            min_trades=args.min_trades,
            min_profit_factor=args.min_profit_factor,
            truth_lane=args.truth_lane,
            min_imported_calendar_dates=args.min_imported_calendar_dates,
            historical_source_labels=args.historical_source_labels,
        )
        payload["exit_sweep"] = exit_report
        payload["artifacts"]["exit_sweep"] = write_exit_report(exit_report, output_root=output_dir / "exit-sweeps")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps({"plan": payload["plan"], "artifacts": payload["artifacts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
