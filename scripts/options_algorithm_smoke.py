import argparse
import json
import os
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import market_data_service as mds
import options_chatbot as oc
import wfo_optimizer as wfo
from options_algorithm_fixtures import FrozenDateTime, build_options_algorithm_fixture_bundle, load_backend_main


def _require_keys(payload: dict, keys: set[str], label: str):
    missing = keys.difference(payload.keys())
    if missing:
        raise AssertionError(f"{label} missing keys: {sorted(missing)}")


def _env_flag(name: str) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _expectancy_loader_for_path(results_path: str):
    def _loader(
        min_trades: int = oc.DEFAULT_SURFACE_MIN_TRADES,
        bucket_size: int = 10,
        **kwargs,
    ) -> dict | None:
        truth_lane = str(kwargs.get("truth_lane") or "").strip().lower()
        if truth_lane not in {"synthetic", wfo.SYNTHETIC_TRUTH_SOURCE}:
            return None
        return oc.build_expectancy_surface(
            results_file=results_path,
            min_trades=min_trades,
            bucket_size=bucket_size,
            shrinkage_trades=oc.DEFAULT_SHRINKAGE_TRADES,
            sparse_warning_trades=oc.DEFAULT_SPARSE_WARNING_TRADES,
        )

    return _loader


def _run_smoke_sequence(
    client: TestClient,
    *,
    scan_picks: int,
    lookback_years: int,
    iv_adj: float,
    min_trades: int,
    policy_truth_lane: str = "synthetic",
) -> dict[str, Any]:
    # Run the live scan before replay artifacts exist so the smoke covers the
    # raw deterministic picks path separately from replay-policy generation.
    scan_response = client.post(
        "/api/scan",
        json={"n_picks": scan_picks, "use_recommended_policy": False},
    )
    if scan_response.status_code != 200:
        raise AssertionError(f"/api/scan failed with {scan_response.status_code}: {scan_response.text}")
    scan_payload = scan_response.json()
    if "picks" not in scan_payload or not isinstance(scan_payload["picks"], list):
        raise AssertionError("/api/scan did not return a picks array")
    if scan_payload["picks"]:
        _require_keys(
            scan_payload["picks"][0],
            {"ticker", "type", "direction_score", "quality_score", "ev", "dte", "target_move_pct"},
            "scan pick",
        )

    backtest_response = client.post(
        "/api/backtest",
        json={"lookback_years": lookback_years, "iv_adj": iv_adj, "truth_lane": "synthetic"},
    )
    if backtest_response.status_code != 200:
        raise AssertionError(
            f"/api/backtest failed with {backtest_response.status_code}: {backtest_response.text}"
        )
    backtest_payload = backtest_response.json()

    live_policy_response = client.get(
        "/api/backtest/live-policy",
        params={"min_trades": min_trades, "truth_lane": policy_truth_lane},
    )
    if live_policy_response.status_code != 200:
        raise AssertionError(
            f"/api/backtest/live-policy failed with {live_policy_response.status_code}: {live_policy_response.text}"
        )
    live_policy_payload = live_policy_response.json()

    report_response = client.get(
        "/api/backtest/report",
        params={"min_trades": min_trades, "truth_lane": "synthetic"},
    )
    if report_response.status_code != 200:
        raise AssertionError(
            f"/api/backtest/report failed with {report_response.status_code}: {report_response.text}"
        )
    report_payload = report_response.json()
    _require_keys(
        report_payload,
        {"source", "overall", "by_direction_score", "by_ticker", "by_sector", "by_regime", "risk_flags"},
        "backtest report",
    )

    experiments_response = client.post(
        "/api/backtest/experiments",
        json={"min_trades": min_trades, "score_floors": [60, 70, 80], "truth_lane": "synthetic"},
    )
    if experiments_response.status_code != 200:
        raise AssertionError(
            f"/api/backtest/experiments failed with {experiments_response.status_code}: {experiments_response.text}"
        )
    experiments_payload = experiments_response.json()
    _require_keys(
        experiments_payload,
        {
            "source",
            "strategy_domain",
            "trade_types",
            "overall",
            "by_category",
            "experiments",
            "recommendations",
        },
        "backtest experiments",
    )

    summary = {
        "scan_picks": len(scan_payload["picks"]),
        "scan_candidate_count": scan_payload.get("candidate_count"),
        "scan_returned_count": scan_payload.get("returned_count"),
        "scan_truth_lane": scan_payload.get("truth_lane"),
        "scan_top_ticker": scan_payload["picks"][0]["ticker"] if scan_payload["picks"] else None,
        "scan_top_guardrail_decision": (
            scan_payload["picks"][0].get("guardrail_decision") if scan_payload["picks"] else None
        ),
        "scan_policy_applied": scan_payload.get("policy_applied"),
        "scan_policy_fail_closed": scan_payload.get("policy_fail_closed"),
        "scan_top_calibrated_expectancy_pct": (
            scan_payload["picks"][0].get("calibrated_expectancy_pct") if scan_payload["picks"] else None
        ),
        "live_policy_truth_source": live_policy_payload.get("truth_source"),
        "live_policy_promotion_status": live_policy_payload.get("scan_policy", {}).get("promotion_status"),
        "live_policy_quote_coverage_pct": live_policy_payload.get("quote_coverage_pct"),
        "scan_calibrated_expectancy_count": sum(
            1 for pick in scan_payload["picks"] if pick.get("calibrated_expectancy_pct") is not None
        ),
        "backtest_truth_source": backtest_payload.get("truth_source"),
        "backtest_total_trades": backtest_payload["total_trades"],
        "backtest_profit_factor": backtest_payload["profit_factor"],
        "report_total_trades": report_payload["source"]["total_trades"],
        "experiment_candidates": len(experiments_payload["experiments"]),
    }
    return summary


def _run_live_smoke(
    *,
    scan_picks: int,
    lookback_years: int,
    iv_adj: float,
    min_trades: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "chat_history.db")
        results_path = os.path.join(tmpdir, "wfo_results.json")
        imported_results_dir = os.path.join(tmpdir, "options_validation_runs")
        imported_latest_path = os.path.join(imported_results_dir, "latest.json")
        backend = load_backend_main(db_path)

        with patch.object(wfo, "WFO_RESULTS_FILE", results_path), \
             patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", imported_results_dir), \
             patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", imported_latest_path), \
             patch.object(oc, "_load_expectancy_surface_for_live", side_effect=_expectancy_loader_for_path(results_path)):
            client = TestClient(backend.app)
            try:
                return _run_smoke_sequence(
                    client,
                    scan_picks=scan_picks,
                    lookback_years=lookback_years,
                    iv_adj=iv_adj,
                    min_trades=min_trades,
                    policy_truth_lane=str(getattr(backend, "LIVE_SCAN_TRUTH_LANE", "historical_imported_daily")),
                )
            finally:
                client.close()


def _run_fixture_smoke(
    *,
    scan_picks: int,
    lookback_years: int,
    iv_adj: float,
    min_trades: int,
) -> dict[str, Any]:
    bundle = build_options_algorithm_fixture_bundle()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "chat_history.db")
        results_path = os.path.join(tmpdir, "wfo_results.json")
        imported_results_dir = os.path.join(tmpdir, "options_validation_runs")
        imported_latest_path = os.path.join(imported_results_dir, "latest.json")
        imported_daily_latest_path = os.path.join(imported_results_dir, "latest_daily.json")
        with patch.dict(
            os.environ,
            {
                "MARKET_DATA_DB_PATH": os.path.join(tmpdir, "market_data.db"),
                "HISTORICAL_OPTIONS_DB_PATH": os.path.join(tmpdir, "options_history.db"),
            },
            clear=False,
        ):
            backend = load_backend_main(db_path)
            with ExitStack() as stack:
                stack.enter_context(patch.object(oc, "DEFAULT_WATCHLIST", bundle.watchlist))
                stack.enter_context(patch.object(wfo, "DEFAULT_WATCHLIST", bundle.watchlist))
                stack.enter_context(patch.object(oc.yf, "Ticker", side_effect=bundle.make_ticker))
                stack.enter_context(patch.object(wfo.yf, "Ticker", side_effect=bundle.make_ticker))
                stack.enter_context(patch.object(mds.yf, "Ticker", side_effect=bundle.make_ticker))
                stack.enter_context(patch.object(oc, "datetime", FrozenDateTime))
                stack.enter_context(patch.object(wfo, "datetime", FrozenDateTime))
                stack.enter_context(patch.object(mds, "datetime", FrozenDateTime))
                stack.enter_context(patch.object(oc, "_market_is_open", return_value=False))
                stack.enter_context(
                    patch.object(
                        oc,
                        "_load_expectancy_surface_for_live",
                        side_effect=_expectancy_loader_for_path(results_path),
                    )
                )
                stack.enter_context(patch.object(wfo, "WFO_RESULTS_FILE", results_path))
                stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", imported_results_dir))
                stack.enter_context(patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", imported_latest_path))
                stack.enter_context(
                    patch.object(wfo, "OPTIONS_VALIDATION_DAILY_LATEST_FILE", imported_daily_latest_path)
                )

                client = TestClient(backend.app)
                try:
                    return _run_smoke_sequence(
                        client,
                        scan_picks=scan_picks,
                        lookback_years=lookback_years,
                        iv_adj=iv_adj,
                        min_trades=min_trades,
                        policy_truth_lane="synthetic",
                    )
                finally:
                    client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise the options replay stack in a deterministic smoke test."
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Run against frozen local fixtures with no network access.",
    )
    args = parser.parse_args()

    scan_picks = int(os.getenv("OPTIONS_SMOKE_PICKS", "3"))
    lookback_years = int(os.getenv("OPTIONS_SMOKE_LOOKBACK_YEARS", "1"))
    iv_adj = float(os.getenv("OPTIONS_SMOKE_IV_ADJ", "1.2"))
    min_trades = int(os.getenv("OPTIONS_SMOKE_MIN_TRADES", "20"))
    fixture_mode = bool(args.fixture or _env_flag("OPTIONS_SMOKE_FIXTURE"))
    summary = (
        _run_fixture_smoke(
            scan_picks=scan_picks,
            lookback_years=lookback_years,
            iv_adj=iv_adj,
            min_trades=min_trades,
        )
        if fixture_mode
        else _run_live_smoke(
            scan_picks=scan_picks,
            lookback_years=lookback_years,
            iv_adj=iv_adj,
            min_trades=min_trades,
        )
    )
    summary["mode"] = "fixture" if fixture_mode else "live"
    summary["window_mode"] = "full"
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
