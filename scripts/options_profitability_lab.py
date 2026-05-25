from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from options_profitability_lab import DEFAULT_OUTPUT_ROOT, DEFAULT_VARIANTS, run_profitability_lab_loop


def _parse_variants(value: str) -> list[str] | None:
    values = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return values or None


def _validate_run_safety(*, run_backtests: bool, variants: list[str] | None, cycles: int, allow_heavy: bool) -> None:
    if not run_backtests or allow_heavy:
        return
    planned_variant_count = len(variants) if variants is not None else len(DEFAULT_VARIANTS)
    if planned_variant_count > 1:
        raise SystemExit(
            "Refusing multi-variant fresh backtests without --allow-heavy. "
            "Run one variant at a time, or add --allow-heavy if you intentionally want the heavier replay."
        )
    if int(cycles) > 1:
        raise SystemExit(
            "Refusing repeated fresh backtest cycles without --allow-heavy. "
            "Run one cycle at a time, or add --allow-heavy if you intentionally want a longer loop."
        )


def build_lab_run_fingerprint(
    *,
    truth_lane: str,
    pricing_lane: str,
    lookback_years: int,
    n_picks: int,
    iv_adj: float,
    min_trades: int,
    min_profit_factor: float,
    min_directional_accuracy: float,
    run_backtests: bool,
    variants: list[str] | None,
) -> str:
    payload = {
        "truth_lane": str(truth_lane or ""),
        "pricing_lane": str(pricing_lane or ""),
        "lookback_years": int(lookback_years),
        "n_picks": int(n_picks),
        "iv_adj": float(iv_adj),
        "min_trades": int(min_trades),
        "min_profit_factor": float(min_profit_factor),
        "min_directional_accuracy": float(min_directional_accuracy),
        "run_backtests": bool(run_backtests),
        "variants": sorted(str(item).strip() for item in list(variants or []) if str(item).strip()),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def find_duplicate_lab_run(output_root: Path, fingerprint: str) -> Path | None:
    for report_path in sorted((Path(output_root) / "runs").glob("*/report.json")):
        try:
            report = json.loads(report_path.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("run_fingerprint") == fingerprint:
            return report_path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an options profitability proof/control lab loop."
    )
    parser.add_argument("--truth-lane", default="historical_imported_daily")
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--lookback-years", type=int, default=1)
    parser.add_argument("--n-picks", type=int, default=3)
    parser.add_argument("--iv-adj", type=float, default=1.2)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-profit-factor", type=float, default=1.05)
    parser.add_argument("--min-directional-accuracy", type=float, default=50.0)
    parser.add_argument("--run-backtests", action="store_true", help="Run fresh historical replays instead of reading the cached lane result.")
    parser.add_argument("--allow-heavy", action="store_true", help="Allow multi-variant fresh backtests. This can be slow and resource-intensive.")
    parser.add_argument("--variants", default="", help="Comma-separated variant ids to evaluate.")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval-minutes", type=float, default=0.0)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--force", action="store_true", help="Run even when an identical lab fingerprint already exists.")
    parser.add_argument("--fail-on-error", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full loop JSON instead of a compact summary.")
    args = parser.parse_args()
    variants = _parse_variants(args.variants)
    _validate_run_safety(
        run_backtests=args.run_backtests,
        variants=variants,
        cycles=args.cycles,
        allow_heavy=args.allow_heavy,
    )
    fingerprint = build_lab_run_fingerprint(
        truth_lane=args.truth_lane,
        pricing_lane=args.pricing_lane,
        lookback_years=args.lookback_years,
        n_picks=args.n_picks,
        iv_adj=args.iv_adj,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        min_directional_accuracy=args.min_directional_accuracy,
        run_backtests=args.run_backtests,
        variants=variants,
    )
    duplicate = find_duplicate_lab_run(Path(args.output_root), fingerprint)
    if duplicate is not None and not args.force:
        print(
            json.dumps(
                {
                    "status": "duplicate_skipped",
                    "duplicate_of": str(duplicate),
                    "fingerprint": fingerprint,
                    "hint": "Use --force to rerun this exact profitability lab request.",
                },
                indent=2,
            )
        )
        return 0

    result = run_profitability_lab_loop(
        cycles=args.cycles,
        interval_seconds=max(float(args.interval_minutes), 0.0) * 60.0,
        output_root=Path(args.output_root),
        truth_lane=args.truth_lane,
        pricing_lane=args.pricing_lane,
        lookback_years=args.lookback_years,
        n_picks=args.n_picks,
        iv_adj=args.iv_adj,
        min_trades=args.min_trades,
        min_profit_factor=args.min_profit_factor,
        min_directional_accuracy_pct=args.min_directional_accuracy,
        run_backtests=args.run_backtests,
        variant_ids=variants,
        fail_on_error=args.fail_on_error,
        run_fingerprint=fingerprint,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    latest = dict(result.get("latest_report") or {})
    summary = {
        "cycle_count": result["cycle_count"],
        "completed_at": result["completed_at"],
        "latest_artifact": result["artifacts"][-1] if result.get("artifacts") else None,
        "measurement_gate_state": (latest.get("measurement_gate") or {}).get("state"),
        "variant_statuses": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "verdict": (item.get("verdict") or {}).get("status"),
                "promotion_allowed": bool((item.get("verdict") or {}).get("promotion_allowed")),
                "error": item.get("error"),
            }
            for item in list(latest.get("variants") or [])
        ],
        "next_actions": latest.get("next_actions"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
