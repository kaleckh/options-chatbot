from __future__ import annotations

import argparse
import copy
import json
import sys
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from scripts import evaluate_regular_options_autoresearch as evaluator  # noqa: E402
from scripts import imported_intraday_robustness as robustness_runner  # noqa: E402
from scripts import run_bullish_pullback_next_round as next_round  # noqa: E402
from scripts import run_regular_options_multilane_portfolio as multilane  # noqa: E402
from scripts import run_side_aware_zero_bid_replay as zero_bid_replay  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "experiments"
FORWARD_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
LANE_A_SOURCE_ID = "lane_a_chain_native_ret20_4_stop200_time75"
DEFAULT_GOAL = (
    "Rank explicitly supplied regular-options clean-proof variants by frozen promotion score "
    "and diagnostic executable-P&L progress score."
)
DEFAULT_VARIANTS: list[str] = []


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "goal-experiment"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _load_forward_holdout_contract(path: Path = FORWARD_HOLDOUT_CONTRACT) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Forward holdout contract is missing: {path}")
    payload = _load_json(path)
    if str(payload.get("status") or "").strip().lower() != "active":
        return {**payload, "guard_active": False}
    protected = payload.get("protected_range")
    if not isinstance(protected, dict) or _parse_date(protected.get("start_date")) is None:
        raise RuntimeError(f"Forward holdout contract has no valid protected_range.start_date: {path}")
    return {**payload, "guard_active": True}


def _requested_replay_window(*, lookback_years: int, as_of_date: date | None = None) -> dict[str, str]:
    end = as_of_date or datetime.now(UTC).date()
    start = end - timedelta(days=max(int(lookback_years), 0) * 365)
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def _ranges_overlap(
    *,
    requested_start: date,
    requested_end: date,
    protected_start: date,
    protected_end: date | None,
) -> bool:
    actual_protected_end = protected_end or date.max
    return requested_start <= actual_protected_end and protected_start <= requested_end


def _ledger_has_holdout_consumption(
    *,
    ledger_path: Path,
    strategy_family: str,
    contract_id: str,
) -> bool:
    if not ledger_path.exists():
        return False
    family = str(strategy_family or "").strip()
    for raw in ledger_path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        marker = row.get("holdout_consumption")
        if not isinstance(marker, dict):
            continue
        marker_family = str(marker.get("strategy_family") or row.get("strategy_family") or "").strip()
        marker_contract = str(marker.get("contract_id") or "").strip()
        if marker.get("consumed") is True and marker_family == family and marker_contract == contract_id:
            return True
    return False


def validate_forward_holdout_guard(
    *,
    variants: Iterable[str],
    lookback_years: int,
    champion_final_eval: bool,
    ledger_path: Path,
    contract_path: Path = FORWARD_HOLDOUT_CONTRACT,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    variant_list = [str(item).strip() for item in variants if str(item).strip()]
    contract = _load_forward_holdout_contract(contract_path)
    requested = _requested_replay_window(lookback_years=lookback_years, as_of_date=as_of_date)
    protected = dict(contract.get("protected_range") or {})
    protected_start = _parse_date(protected.get("start_date"))
    protected_end = _parse_date(protected.get("end_date"))
    requested_start = _parse_date(requested["start_date"])
    requested_end = _parse_date(requested["end_date"])
    overlaps = False
    if contract.get("guard_active") and protected_start and requested_start and requested_end:
        overlaps = _ranges_overlap(
            requested_start=requested_start,
            requested_end=requested_end,
            protected_start=protected_start,
            protected_end=protected_end,
        )
    families = sorted({evaluator.infer_strategy_family(variant_id) for variant_id in variant_list})
    guard = {
        "contract_id": contract.get("contract_id"),
        "contract_version": contract.get("version"),
        "guard_active": bool(contract.get("guard_active")),
        "protected_range": protected,
        "requested_window": requested,
        "overlaps_protected_range": overlaps,
        "champion_final_eval": bool(champion_final_eval),
        "strategy_families": families,
        "ledger_path": str(ledger_path),
        "consumption_required": bool(overlaps and champion_final_eval),
    }
    if champion_final_eval and len(variant_list) != 1:
        raise RuntimeError("--champion-final-eval requires exactly one --variant.")
    if champion_final_eval and len(families) != 1:
        raise RuntimeError("--champion-final-eval requires exactly one inferred strategy family.")
    if overlaps and not champion_final_eval:
        raise RuntimeError(
            "Requested regular-options goal experiment overlaps the protected forward holdout range. "
            "Use --champion-final-eval only for the one-shot final champion evaluation."
        )
    if overlaps and champion_final_eval:
        family = families[0]
        contract_id = str(contract.get("contract_id") or "")
        if _ledger_has_holdout_consumption(
            ledger_path=ledger_path,
            strategy_family=family,
            contract_id=contract_id,
        ):
            raise RuntimeError(
                f"Protected forward holdout has already been consumed for strategy family {family!r}."
            )
        guard["consumption_strategy_family"] = family
    return guard


def _variant_row(report: dict[str, Any], variant_id: str) -> dict[str, Any]:
    for row in report.get("variants") or []:
        if str(row.get("variant_id")) == variant_id:
            return row
    raise RuntimeError(f"Variant {variant_id} did not produce a result row.")


def _run_lane_variant(variant_id: str, *, lookback_years: int) -> tuple[dict[str, Any], dict[str, Any]]:
    report = next_round.run_variants(lookback_years=lookback_years, only={variant_id})
    row = _variant_row(report, variant_id)
    if row.get("error"):
        raise RuntimeError(f"Variant {variant_id} failed: {row['error']}")
    result_path = row.get("result_path")
    if not result_path:
        raise RuntimeError(f"Variant {variant_id} did not write a replay result path.")
    return report, row


def _run_robustness(run_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = _load_json(run_path)
    report = robustness_runner.build_intraday_robustness_report(
        run,
        train_days=50,
        test_days=20,
        min_exact_test_trades=5,
        slippage_values=[0.0, 1.0, 2.5, 5.0],
    )
    artifacts = robustness_runner.write_report(report, output_dir=output_dir)
    report["artifacts"] = artifacts
    return report, Path(artifacts["latest_playbook_json"])


def _run_side_aware(run_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = zero_bid_replay.run_replay(
        run_path.resolve(),
        db_path=zero_bid_replay.DEFAULT_HISTORICAL_OPTIONS_DB_PATH.resolve(),
        theta_url=zero_bid_replay.DEFAULT_THETA_URL,
        source_labels=[zero_bid_replay.DEFAULT_SOURCE_LABEL],
        timeout=30.0,
        modes=["conservative"],
    )
    artifacts = zero_bid_replay.write_outputs(report, output_dir)
    report["artifacts"] = artifacts
    return report, Path(artifacts["latest_json"])


@contextmanager
def _patched_multilane_inputs(*, lane_a_run_path: Path, lane_a_robustness_path: Path, side_aware_path: Path):
    original_sources = copy.deepcopy(multilane.LANE_SOURCES)
    original_side_aware = multilane.SIDE_AWARE_ZERO_BID_LATEST
    patched_sources: list[dict[str, Any]] = []
    for source in original_sources:
        row = dict(source)
        if row.get("lane_id") == LANE_A_SOURCE_ID:
            row["artifact"] = lane_a_run_path
            row["robustness"] = lane_a_robustness_path
            row["decision"] = "goal_experiment"
            row["notes"] = (
                "Temporary goal-experiment Lane A artifact scored through the frozen regular-options autoresearch evaluator."
            )
        patched_sources.append(row)
    multilane.LANE_SOURCES = patched_sources
    multilane.SIDE_AWARE_ZERO_BID_LATEST = side_aware_path
    try:
        yield
    finally:
        multilane.LANE_SOURCES = original_sources
        multilane.SIDE_AWARE_ZERO_BID_LATEST = original_side_aware


def _score_variant(
    *,
    variant_id: str,
    run_path: Path,
    robustness_path: Path,
    side_aware_path: Path,
    hypothesis: str,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    with _patched_multilane_inputs(
        lane_a_run_path=run_path,
        lane_a_robustness_path=robustness_path,
        side_aware_path=side_aware_path,
    ):
        report = multilane.build_report()
    return evaluator.build_scoreboard(
        report,
        experiment_id=variant_id,
        hypothesis=hypothesis,
        strategy_family=evaluator.infer_strategy_family(variant_id, hypothesis),
        ledger_path=ledger_path or evaluator.LEDGER_PATH,
    )


def run_goal_experiments(
    *,
    variants: Iterable[str],
    lookback_years: int,
    output_dir: Path = OUTPUT_DIR,
    append_ledger: bool = True,
    write_global_latest: bool = False,
    champion_final_eval: bool = False,
    holdout_contract_path: Path = FORWARD_HOLDOUT_CONTRACT,
    holdout_ledger_path: Path = evaluator.LEDGER_PATH,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    if champion_final_eval and not append_ledger:
        raise RuntimeError("--champion-final-eval requires ledger append so holdout consumption is recorded.")
    variant_list = [str(item).strip() for item in variants if str(item).strip()]
    holdout_guard = validate_forward_holdout_guard(
        variants=variant_list,
        lookback_years=lookback_years,
        champion_final_eval=champion_final_eval,
        ledger_path=holdout_ledger_path,
        contract_path=holdout_contract_path,
        as_of_date=as_of_date,
    )
    stamp = _utc_stamp()
    root = output_dir / stamp
    rows: list[dict[str, Any]] = []
    for index, variant_id in enumerate(variant_list, start=1):
        variant_dir = root / f"v{index:02d}"
        variant_report, variant_row = _run_lane_variant(variant_id, lookback_years=lookback_years)
        run_path = Path(str(variant_row["result_path"])).resolve()
        _write_json(variant_dir / "lane_variant_report.json", variant_report)
        _write_json(variant_dir / "lane_variant_row.json", variant_row)

        robustness, robustness_path = _run_robustness(run_path, variant_dir / "robustness")
        _write_json(variant_dir / "robustness_report.json", robustness)

        side_aware, side_aware_path = _run_side_aware(run_path, variant_dir / "side-aware-zero-bid")
        _write_json(variant_dir / "side_aware_zero_bid_report.json", side_aware)

        hypothesis = str(variant_row.get("description") or variant_id)
        scoreboard = _score_variant(
            variant_id=variant_id,
            run_path=run_path,
            robustness_path=robustness_path,
            side_aware_path=side_aware_path,
            hypothesis=hypothesis,
            ledger_path=holdout_ledger_path,
        )
        scoreboard["forward_holdout_guard"] = holdout_guard
        scoreboard["champion_final_eval"] = bool(champion_final_eval)
        if holdout_guard.get("consumption_required"):
            metrics = scoreboard.get("metrics") or {}
            scoreboard["holdout_consumption"] = {
                "contract_id": holdout_guard.get("contract_id"),
                "contract_version": holdout_guard.get("contract_version"),
                "consumed": True,
                "consumed_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "strategy_family": metrics.get("strategy_family") or holdout_guard.get("consumption_strategy_family"),
                "variant_id": variant_id,
                "protected_range": holdout_guard.get("protected_range"),
                "requested_window": holdout_guard.get("requested_window"),
                "reason": "champion_final_eval",
            }
        if append_ledger:
            evaluator.append_ledger(scoreboard, path=holdout_ledger_path)
        artifacts = evaluator.write_outputs(scoreboard, output_dir=variant_dir / "autoresearch-scoreboard")
        if write_global_latest:
            artifacts = {
                **artifacts,
                "global": evaluator.write_outputs(scoreboard),
            }
        scoreboard["artifacts"] = artifacts
        _write_json(variant_dir / "scoreboard.json", scoreboard)

        metrics = scoreboard.get("metrics") or {}
        rows.append(
            {
                "variant_id": variant_id,
                "artifact_dir": str(variant_dir),
                "run_path": str(run_path),
                "robustness_path": str(robustness_path),
                "side_aware_path": str(side_aware_path),
                "score": scoreboard.get("score"),
                "progress_score": scoreboard.get("progress_score"),
                "research_score": scoreboard.get("research_score"),
                "pf_point": metrics.get("pf_point"),
                "pf_lb_5pct": metrics.get("pf_lb_5pct"),
                "pf_ub_95pct": metrics.get("pf_ub_95pct"),
                "avg_net_lb_5pct": metrics.get("avg_net_lb_5pct"),
                "n_trades": metrics.get("n_trades"),
                "statistical_confidence": metrics.get("statistical_confidence"),
                "strategy_family": metrics.get("strategy_family"),
                "variants_searched": metrics.get("variants_searched"),
                "selection_adjusted_bar": metrics.get("selection_adjusted_bar"),
                "selection_adjusted_confidence": metrics.get("selection_adjusted_confidence"),
                "selection_adjustment_formula": metrics.get("selection_adjustment_formula"),
                "status": scoreboard.get("status"),
                "promotion_blockers": scoreboard.get("promotion_blockers"),
                "score_line": scoreboard.get("score_line"),
                "lane_metrics": {
                    "candidate_trade_count": variant_row.get("candidate_trade_count"),
                    "exact_trade_count": variant_row.get("exact_trade_count"),
                    "unpriced_trade_count": variant_row.get("unpriced_trade_count"),
                    "quote_coverage_pct": variant_row.get("quote_coverage_pct"),
                    "profit_factor": variant_row.get("exact_profit_factor"),
                    "avg_pnl_pct": variant_row.get("exact_avg_pnl_pct"),
                    "pre_entry_filtered_candidate_count": variant_row.get("pre_entry_filtered_candidate_count"),
                    "pre_entry_filtered_candidate_reasons": variant_row.get("pre_entry_filtered_candidate_reasons"),
                },
                "autoresearch_metrics": metrics,
            }
        )

    ranked = sorted(rows, key=lambda row: (float(row.get("score") or 0.0), float(row.get("progress_score") or 0.0)), reverse=True)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "experiment_batch": stamp,
        "goal": DEFAULT_GOAL,
        "lookback_years": int(lookback_years),
        "append_ledger": bool(append_ledger),
        "write_global_latest": bool(write_global_latest),
        "champion_final_eval": bool(champion_final_eval),
        "forward_holdout_guard": holdout_guard,
        "variants": rows,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
    }
    _write_json(root / "summary.json", report)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "latest.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Lane A goal experiments and score them with the frozen evaluator.")
    parser.add_argument("--variant", action="append", help="Variant id to run. Repeat for multiple variants.")
    parser.add_argument("--lookback-years", type=int, default=1)
    parser.add_argument("--no-append-ledger", action="store_true")
    parser.add_argument(
        "--champion-final-eval",
        action="store_true",
        help="Consume the protected forward holdout for one final champion evaluation. One use per strategy family.",
    )
    parser.add_argument(
        "--write-global-latest",
        action="store_true",
        help="Also write the frozen evaluator's global latest.json/latest.md. Default keeps evaluator outputs experiment-scoped.",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    variants = args.variant or DEFAULT_VARIANTS
    if not variants:
        parser.error("No default variants are configured; pass --variant for a pre-registered clean-proof experiment.")
    report = run_goal_experiments(
        variants=variants,
        lookback_years=int(args.lookback_years),
        output_dir=args.output_dir,
        append_ledger=not args.no_append_ledger,
        write_global_latest=bool(args.write_global_latest),
        champion_final_eval=bool(args.champion_final_eval),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps({"best": report.get("best"), "variant_count": len(report.get("variants") or [])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
