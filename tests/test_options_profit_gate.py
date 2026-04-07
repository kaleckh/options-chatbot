import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from forward_options_ledger import build_forward_scan_snapshot, record_forward_snapshot
from historical_options_fixtures import make_validation_history, write_daily_options_parquet
from historical_options_store import HistoricalOptionsStore, import_daily_option_parquet
from options_profit_gate import evaluate_measurement_gate
from workspace_tempdir import WorkspaceTempDir


class _StubRepo:
    def __init__(self, *, available: bool, closed_positions: list[dict] | None = None, error_message: str | None = None):
        self.is_available = available
        self.error_message = error_message
        self._closed_positions = list(closed_positions or [])

    def list_positions(self, status=None):
        if not self.is_available:
            raise RuntimeError(self.error_message or "unavailable")
        if status == "closed":
            return list(self._closed_positions)
        return []


class OptionsProfitGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="options-profit-gate")
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)
        self.db_path = self.tmpdir / "options_history.db"
        self.daily_parquet = self.tmpdir / "spy_daily.parquet"
        histories = {"SPY": make_validation_history(length=14, start=500.0, step=0.8)}
        write_daily_options_parquet(self.daily_parquet, histories, symbol="SPY", strike_span=3)
        import_daily_option_parquet(self.daily_parquet, "spy_daily", underlying="SPY", db_path=self.db_path)
        self.store = HistoricalOptionsStore(self.db_path)

    def _write_valid_daily_artifact(self, path: Path, *, quote_coverage_pct: float = 100.0) -> None:
        truth_store = self.store.snapshot_summary("daily_eod", trusted_only=True)
        truth_store["data_trust"] = "trusted"
        path.write_text(
            json.dumps(
                {
                    "truth_source": "historical_imported_daily",
                    "quote_coverage_pct": quote_coverage_pct,
                    "truth_store": truth_store,
                },
                indent=2,
            ),
            encoding="utf8",
        )

    def test_gate_blocks_when_imported_daily_artifact_mismatches_store(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        artifact_path.write_text(
            json.dumps(
                {
                    "truth_source": "historical_imported_daily",
                    "quote_coverage_pct": 100.0,
                    "truth_store": {
                        "snapshot_kind": "daily_eod",
                        "data_trust": "trusted",
                        "quote_count": 1,
                        "batch_count": 1,
                        "latest_imported_at_utc": "2026-01-01T00:00:00Z",
                        "available_underlyings": ["SPY"],
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True)):
                    result = evaluate_measurement_gate(
                        min_eligible_forward_events=0,
                        min_eligible_events_per_symbol=0,
                        min_closed_tracked_positions=0,
                        recorded_before_utc="2026-04-01T23:00:00Z",
                    )

        self.assertEqual(result["state"], "blocked")
        self.assertIn(
            "imported_daily_store_mismatch",
            [item["code"] for item in result["blockers"]],
        )

    def test_gate_blocks_when_fixture_evidence_exists_in_shared_forward_ledger(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        ledger_path = self.tmpdir / "forward_tracking.db"
        self._write_valid_daily_artifact(artifact_path)

        snapshot = build_forward_scan_snapshot(
            picks=[
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "expiry": "2026-04-10",
                    "strike": 500.0,
                    "quote_time_et": "2026-04-01 10:15 ET",
                    "quote_basis": "mid",
                }
            ],
            policy_applied=True,
            policy={"truth_source": "historical_imported_daily", "promotion_status": "watch"},
            truth_lane="historical_imported_daily",
        )
        record_forward_snapshot(
            scan_snapshot=snapshot,
            reviewed_positions=[],
            tracked_positions=[],
            source_label="fixture_smoke",
            db_path=ledger_path,
        )

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True)):
                    result = evaluate_measurement_gate(
                        forward_db_path=ledger_path,
                        min_eligible_forward_events=0,
                        min_eligible_events_per_symbol=0,
                        min_closed_tracked_positions=0,
                    )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "blocked")
        self.assertIn("forward_ledger_contamination", blocker_codes)

    def test_gate_returns_pending_truth_when_only_forward_evidence_is_beyond_trusted_horizon(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [],
            "eligible_event_count": 0,
            "pending_truth_events": [{"ticker": "SPY"}],
            "pending_truth_event_count": 1,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {"SPY": {"eligible": 0, "pending_truth": 1, "ineligible": 0}},
        }

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True)):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=0,
                            min_eligible_events_per_symbol=0,
                            min_closed_tracked_positions=0,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "pending_truth")
        self.assertIn("pending_truth_horizon", blocker_codes)
        self.assertEqual(result["checks"]["forward_evidence"]["pending_truth_event_count"], 1)

    def test_gate_returns_degraded_watch_when_samples_are_small_but_truth_is_healthy(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [],
            "eligible_event_count": 0,
            "pending_truth_events": [],
            "pending_truth_event_count": 0,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {"SPY": {"eligible": 0, "pending_truth": 0, "ineligible": 0}},
        }

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True)):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=1,
                            min_eligible_events_per_symbol=0,
                            min_closed_tracked_positions=1,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "degraded-watch")
        self.assertIn("insufficient_eligible_forward_truth", blocker_codes)
        self.assertIn("insufficient_closed_tracked_positions", blocker_codes)

    def test_gate_surfaces_archive_live_evidence_when_authoritative_ledger_is_empty(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        authoritative_path = self.tmpdir / "authoritative_forward_tracking.db"
        archive_path = self.tmpdir / "archive_forward_tracking.db"
        self._write_valid_daily_artifact(artifact_path)

        snapshot = build_forward_scan_snapshot(
            picks=[
                {
                    "ticker": "SPY",
                    "direction": "call",
                    "contract_symbol": "SPY240101C00500000",
                    "expiry": "2026-04-10",
                    "strike": 500.0,
                    "quote_time_et": "2026-04-01 10:15 ET",
                    "quote_basis": "mid",
                }
            ],
            policy_applied=True,
            policy={"truth_source": "historical_imported_daily", "promotion_status": "watch"},
            truth_lane="historical_imported_daily",
        )
        record_forward_snapshot(
            scan_snapshot=snapshot,
            reviewed_positions=[],
            tracked_positions=[],
            source_label="live_production",
            db_path=archive_path,
        )

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate.authoritative_forward_ledger_db_path", return_value=authoritative_path), \
                     patch("options_profit_gate.archive_forward_ledger_db_path", return_value=archive_path), \
                     patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True)):
                    result = evaluate_measurement_gate(
                        min_eligible_forward_events=0,
                        min_eligible_events_per_symbol=0,
                        min_closed_tracked_positions=0,
                        recorded_before_utc="2026-04-03T23:00:00Z",
                    )

        self.assertEqual(result["state"], "healthy")
        self.assertEqual(
            result["checks"]["forward_evidence"]["authoritative_ledger_diagnostics"]["live_production_event_count"],
            0,
        )
        self.assertEqual(
            result["checks"]["forward_evidence"]["archive_ledger_diagnostics"]["live_production_session_count"],
            1,
        )

    def test_gate_returns_healthy_when_truth_forward_evidence_and_positions_are_ready(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [{} for _ in range(12)],
            "eligible_event_count": 12,
            "pending_truth_events": [],
            "pending_truth_event_count": 0,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {
                "SPY": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
                "QQQ": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
            },
        }
        closed_positions = [
            {
                "contract_symbol": "SPY240101C00500000",
                "entry_execution_price": 2.0,
                "exit_execution_price": 3.0,
                "net_pnl_pct": 50.0,
                "gross_pnl_pct": 50.0,
                "net_pnl_usd": 100.0,
                "gross_pnl_usd": 100.0,
            }
        ]

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True, closed_positions=closed_positions)):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=10,
                            min_eligible_events_per_symbol=3,
                            min_closed_tracked_positions=1,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        self.assertEqual(result["state"], "healthy")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["checks"]["tracked_positions"]["available"])
        self.assertEqual(result["checks"]["forward_evidence"]["eligible_event_count"], 12)
        self.assertEqual(result["checks"]["forward_evidence"]["trusted_truth_horizon"], "2026-04-01")
        self.assertIn("requested_manifest_inputs", result["checks"]["forward_evidence"])
        self.assertIn("daily_truth_source_latest_mtime_utc", result["checks"]["forward_evidence"])
        self.assertIn("daily_truth_source_stale", result["checks"]["forward_evidence"])
        self.assertIn("requested_manifest_inputs", result["checks"]["imported_daily_artifact"])
        self.assertIn("daily_truth_source_latest_mtime_utc", result["checks"]["imported_daily_artifact"])
        self.assertIn("daily_truth_source_stale", result["checks"]["imported_daily_artifact"])
        self.assertTrue(result["checks"]["tracked_positions"]["realized_profitability_ready"])

    def test_gate_returns_degraded_watch_when_realized_profit_factor_is_below_floor(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [{} for _ in range(12)],
            "eligible_event_count": 12,
            "pending_truth_events": [],
            "pending_truth_event_count": 0,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {
                "SPY": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
                "QQQ": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
            },
        }
        closed_positions = [
            {"contract_symbol": "SPY240101C00500000", "net_pnl_pct": 20.0, "gross_pnl_pct": 20.0},
            {"contract_symbol": "SPY240101C00510000", "net_pnl_pct": -25.0, "gross_pnl_pct": -25.0},
        ]

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True, closed_positions=closed_positions)):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=10,
                            min_eligible_events_per_symbol=3,
                            min_closed_tracked_positions=1,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "degraded-watch")
        self.assertIn("tracked_realized_underperforming", blocker_codes)
        self.assertFalse(result["checks"]["tracked_positions"]["realized_profitability_ready"])
        self.assertEqual(result["checks"]["tracked_positions"]["net_profit_factor"], 0.8)

    def test_gate_returns_degraded_watch_when_realized_avg_net_pnl_is_not_positive(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [{} for _ in range(12)],
            "eligible_event_count": 12,
            "pending_truth_events": [],
            "pending_truth_event_count": 0,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {
                "SPY": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
                "QQQ": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
            },
        }
        closed_positions = [
            {"contract_symbol": "SPY240101C00500000", "net_pnl_pct": 10.0, "gross_pnl_pct": 10.0},
            {"contract_symbol": "SPY240101C00510000", "net_pnl_pct": -10.0, "gross_pnl_pct": -10.0},
        ]

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch("options_profit_gate.create_positions_repository", return_value=_StubRepo(available=True, closed_positions=closed_positions)):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=10,
                            min_eligible_events_per_symbol=3,
                            min_closed_tracked_positions=1,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "degraded-watch")
        self.assertIn("tracked_realized_underperforming", blocker_codes)
        self.assertEqual(result["checks"]["tracked_positions"]["avg_net_pnl_pct"], 0.0)

    def test_gate_blocks_when_tracked_positions_are_unavailable(self):
        artifact_path = self.tmpdir / "latest_daily.json"
        self._write_valid_daily_artifact(artifact_path)

        forward_evidence = {
            "trusted_truth_horizon": "2026-04-01",
            "all_events": [],
            "eligible_events": [{} for _ in range(12)],
            "eligible_event_count": 12,
            "pending_truth_events": [],
            "pending_truth_event_count": 0,
            "contamination_findings": [],
            "stale_metadata_events": [],
            "by_symbol": {
                "SPY": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
                "QQQ": {"eligible": 6, "pending_truth": 0, "ineligible": 0},
            },
        }

        with patch.dict(os.environ, {"HISTORICAL_OPTIONS_DB_PATH": str(self.db_path)}, clear=False):
            with patch("options_profit_gate.OPTIONS_VALIDATION_DAILY_LATEST_FILE", str(artifact_path)):
                with patch("options_profit_gate._load_forward_evidence", return_value=forward_evidence):
                    with patch(
                        "options_profit_gate.create_positions_repository",
                        return_value=_StubRepo(
                            available=False,
                            error_message="Tracked positions are unavailable because DATABASE_URL is not configured.",
                        ),
                    ):
                        result = evaluate_measurement_gate(
                            min_eligible_forward_events=10,
                            min_eligible_events_per_symbol=3,
                            min_closed_tracked_positions=1,
                            recorded_before_utc="2026-04-01T23:00:00Z",
                        )

        blocker_codes = [item["code"] for item in result["blockers"]]
        self.assertEqual(result["state"], "blocked")
        self.assertIn("tracked_positions_unavailable", blocker_codes)
        self.assertFalse(result["checks"]["tracked_positions"]["available"])


if __name__ == "__main__":
    unittest.main()
