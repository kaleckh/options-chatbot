import argparse
import json
import os
import shutil
import subprocess
import sys
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
from forward_options_ledger import DEFAULT_FORWARD_LEDGER_DB_PATH, init_forward_ledger
from options_algorithm_fixtures import FrozenDateTime, build_options_algorithm_fixture_bundle, load_backend_main
from positions_repository import MemoryTrackedPositionsRepository
from workspace_tempdir import WorkspaceTempDir


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
        if not os.path.exists(results_path):
            return None
        truth_lane = str(kwargs.get("truth_lane") or wfo.SYNTHETIC_TRUTH_SOURCE).strip().lower()
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


def _fixture_truth_store_db_path() -> str | None:
    daily_result = wfo._load_json_file(wfo.OPTIONS_VALIDATION_DAILY_LATEST_FILE)
    truth_store = dict((daily_result or {}).get("truth_store") or {})
    candidate = str(truth_store.get("db_path") or "").strip()
    if candidate and os.path.exists(candidate):
        return candidate
    summary = wfo._current_imported_store_summary(wfo.IMPORTED_DAILY_TRUTH_SOURCE)
    candidate = str((summary or {}).get("db_path") or "").strip()
    if candidate and os.path.exists(candidate):
        return candidate
    return None


def _run_git_command(*args: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _runtime_context() -> dict[str, Any]:
    head = _run_git_command("rev-parse", "HEAD")
    branch = _run_git_command("rev-parse", "--abbrev-ref", "HEAD")
    diff_stat = _run_git_command("diff", "--stat")
    changed_files = _run_git_command("diff", "--name-only")
    uv_path = shutil.which("uv")
    return {
        "repo_root": str(ROOT.resolve()),
        "cwd": str(Path.cwd().resolve()),
        "script_path": str(Path(__file__).resolve()),
        "interpreter_path": sys.executable,
        "python_version": sys.version.split()[0],
        "venv_active": bool(os.getenv("VIRTUAL_ENV")) or sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "virtual_env": os.getenv("VIRTUAL_ENV"),
        "uv_available": uv_path is not None,
        "uv_path": uv_path,
        "git_head": head["stdout"] if head["ok"] else None,
        "git_branch": branch["stdout"] if branch["ok"] else None,
        "git_status_available": head["ok"] and branch["ok"],
        "git_diff_stat": diff_stat["stdout"] if diff_stat["ok"] else None,
        "git_changed_files": changed_files["stdout"].splitlines() if changed_files["ok"] and changed_files["stdout"] else [],
    }


def _artifact_health(truth_lane_health: dict[str, Any]) -> dict[str, Any]:
    paths = dict(truth_lane_health.get("paths") or {})
    synthetic_path = str(Path(paths.get("synthetic_result") or wfo.WFO_RESULTS_FILE).resolve())
    imported_path = str(Path(paths.get("imported_result") or wfo.OPTIONS_VALIDATION_LATEST_FILE).resolve())
    imported_daily_path = str(
        Path(paths.get("imported_daily_result") or wfo.OPTIONS_VALIDATION_DAILY_LATEST_FILE).resolve()
    )
    archived_forward_path = str(
        Path(paths.get("archived_forward_daily_result") or wfo.OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE).resolve()
    )
    forward_ledger_path = str(Path(DEFAULT_FORWARD_LEDGER_DB_PATH).resolve())
    return {
        "wfo_results": {"path": synthetic_path, "present": os.path.exists(synthetic_path)},
        "imported_validation_latest": {"path": imported_path, "present": os.path.exists(imported_path)},
        "imported_validation_daily_latest": {
            "path": imported_daily_path,
            "present": os.path.exists(imported_daily_path),
        },
        "archived_forward_daily_latest": {
            "path": archived_forward_path,
            "present": os.path.exists(archived_forward_path),
        },
        "forward_truth_db": {"path": forward_ledger_path, "present": os.path.exists(forward_ledger_path)},
    }


def _doc_parity(artifact_health: dict[str, Any]) -> dict[str, Any]:
    current_state_path = ROOT / "docs" / "current-state.md"
    text = current_state_path.read_text(encoding="utf8") if current_state_path.exists() else ""
    claims_imported_daily_validation = "data/options-validation/runs/latest_daily.json" in text
    claims_forward_holdout = "forward holdout" in text.lower() or "forward_tracking.db" in text
    mismatches: list[dict[str, Any]] = []
    if claims_imported_daily_validation and not artifact_health["imported_validation_daily_latest"]["present"]:
        mismatches.append(
            {
                "claim": "imported_daily_validation_documented",
                "artifact": "imported_validation_daily_latest",
                "artifact_path": artifact_health["imported_validation_daily_latest"]["path"],
            }
        )
    if claims_forward_holdout and not artifact_health["forward_truth_db"]["present"]:
        mismatches.append(
            {
                "claim": "forward_holdout_documented",
                "artifact": "forward_truth_db",
                "artifact_path": artifact_health["forward_truth_db"]["path"],
            }
        )
    return {
        "current_state_doc_path": str(current_state_path.resolve()),
        "current_state_doc_present": current_state_path.exists(),
        "claims_imported_daily_validation": claims_imported_daily_validation,
        "claims_forward_holdout": claims_forward_holdout,
        "mismatches": mismatches,
    }


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

    calibrated_scan_response = client.post(
        "/api/scan",
        json={"n_picks": scan_picks, "use_recommended_policy": False},
    )
    if calibrated_scan_response.status_code != 200:
        raise AssertionError(
            f"/api/scan (post-backtest) failed with {calibrated_scan_response.status_code}: {calibrated_scan_response.text}"
        )
    calibrated_scan_payload = calibrated_scan_response.json()

    summary = {
        "requested_policy_truth_lane": policy_truth_lane,
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
        "post_backtest_scan_picks": len(calibrated_scan_payload.get("picks") or []),
        "post_backtest_scan_calibrated_expectancy_count": sum(
            1
            for pick in calibrated_scan_payload.get("picks") or []
            if pick.get("calibrated_expectancy_pct") is not None
        ),
        "post_backtest_scan_top_calibrated_expectancy_pct": (
            calibrated_scan_payload["picks"][0].get("calibrated_expectancy_pct")
            if calibrated_scan_payload.get("picks")
            else None
        ),
        "live_policy_truth_source": live_policy_payload.get("truth_source"),
        "live_policy_error": live_policy_payload.get("error"),
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
    with WorkspaceTempDir(prefix="options-algorithm-smoke-live") as tmpdir:
        db_path = os.path.join(tmpdir, "chat_history.db")
        results_path = os.path.join(tmpdir, "wfo_results.json")
        imported_results_dir = os.path.join(tmpdir, "options_validation_runs")
        imported_latest_path = os.path.join(imported_results_dir, "latest.json")
        backend = load_backend_main(db_path)

        with patch.object(wfo, "WFO_RESULTS_FILE", results_path), \
             patch.object(wfo, "OPTIONS_VALIDATION_RESULTS_DIR", imported_results_dir), \
             patch.object(wfo, "OPTIONS_VALIDATION_LATEST_FILE", imported_latest_path), \
             patch.object(oc, "_load_expectancy_surface_for_live", side_effect=_expectancy_loader_for_path(results_path)), \
             patch.object(backend, "POSITIONS_REPOSITORY", MemoryTrackedPositionsRepository()):
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

    with WorkspaceTempDir(prefix="options-algorithm-smoke-fixture") as tmpdir:
        db_path = os.path.join(tmpdir, "chat_history.db")
        results_path = os.path.join(tmpdir, "wfo_results.json")
        forward_ledger_path = os.path.join(tmpdir, "forward_tracking_fixture.db")
        fixture_truth_store_db_path = _fixture_truth_store_db_path()
        with patch.dict(
            os.environ,
            {
                "MARKET_DATA_DB_PATH": os.path.join(tmpdir, "market_data.db"),
                "HISTORICAL_OPTIONS_DB_PATH": fixture_truth_store_db_path or os.path.join(tmpdir, "options_history.db"),
                "FORWARD_OPTIONS_LEDGER_DB_PATH": forward_ledger_path,
                "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": forward_ledger_path,
                "OPTIONS_EVIDENCE_CLASS": "fixture_smoke",
                "OPTIONS_RUN_MODE": "fixture_smoke",
                "OPTIONS_IS_FIXTURE": "1",
            },
            clear=False,
        ):
            init_forward_ledger(forward_ledger_path)
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
                stack.enter_context(patch.object(backend, "POSITIONS_REPOSITORY", MemoryTrackedPositionsRepository()))

                client = TestClient(backend.app)
                try:
                    summary = _run_smoke_sequence(
                        client,
                        scan_picks=scan_picks,
                        lookback_years=lookback_years,
                        iv_adj=iv_adj,
                        min_trades=min_trades,
                        policy_truth_lane=str(getattr(backend, "LIVE_SCAN_TRUTH_LANE", "historical_imported_daily")),
                    )
                    summary["forward_truth_runtime_db_path"] = str(Path(forward_ledger_path).resolve())
                    summary["fixture_truth_store_db_path"] = fixture_truth_store_db_path
                    return summary
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
    summary["runtime_context"] = _runtime_context()
    summary["truth_lane_health"] = wfo.build_truth_lane_health_summary()
    summary["truth_lane_health"]["scan_truth_lane"] = summary.get("scan_truth_lane")
    summary["truth_lane_health"]["live_policy_truth_source"] = summary.get("live_policy_truth_source")
    summary["truth_lane_health"]["live_policy_promotion_status"] = summary.get("live_policy_promotion_status")
    summary["artifact_health"] = _artifact_health(summary["truth_lane_health"])
    summary["forward_truth_runtime_db_path"] = str(
        Path(
            summary.get("forward_truth_runtime_db_path")
            or os.getenv("FORWARD_OPTIONS_LEDGER_DB_PATH")
            or DEFAULT_FORWARD_LEDGER_DB_PATH
        ).resolve()
    )
    summary["doc_parity"] = _doc_parity(summary["artifact_health"])
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
