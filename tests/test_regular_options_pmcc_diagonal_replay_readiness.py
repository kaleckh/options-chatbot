from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_pmcc_diagonal_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsPmccDiagonalReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "pmcc.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_or_uncapped_short_call_risk_allowed": False,
                "concept": {
                    "initial_research_universe": ["SPY", "QQQ"],
                    "future_extension_universe": ["IWM", "DIA"],
                    "undefined_or_uncapped_short_call_risk_allowed": False,
                    "denominator_statuses": [
                        "no_candidate",
                        "missing_leg_quote",
                        "exact_entry_captured",
                        "short_call_roll_captured",
                        "assignment_or_ex_dividend_blocked",
                        "exact_exit_captured",
                        "missing_exit",
                    ],
                    "frozen_design": {
                        "entry_regime": ["trend must be known point-in-time before entry"],
                        "roll_and_exit_policy": ["assignment", "ex-dividend", "expiration", "roll"],
                    },
                    "side_aware_pricing_formulas": {
                        "entry_debit": "long_call_ask - short_call_bid",
                        "roll_debit_or_credit": "buy_to_close_short_call_ask - sell_to_open_next_short_call_bid",
                        "exit_value_with_open_short": "long_call_bid - short_call_ask",
                        "net_pnl_usd": "net",
                        "max_loss_usd": "max",
                        "collateral_convention": "required collateral and undefined-risk short calls are forbidden",
                    },
                },
            },
        )
        return path

    def _feature_store(self, tmp: Path, *, trend_ready: bool = False) -> Path:
        path = tmp / "feature.json"
        payload = {
            "source_label": "thetadata_opra_nbbo_1m",
            "quote_evidence_class": "trusted_intraday_opra_nbbo",
            "join_contract": "feature.tradable_after_time <= candidate_entry_time",
            "symbols": ["SPY", "QQQ"],
        }
        if trend_ready:
            payload["point_in_time"] = {"underlying_return": True, "trend": True, "market_regime": True}
        _write_json(path, payload)
        return path

    def _vix(self, tmp: Path, *, ready: bool) -> Path:
        path = tmp / "vix.json"
        _write_json(
            path,
            {
                "status": "ready" if ready else "blocked_point_in_time_vix_source_missing",
                "point_in_time_vix_low_mid_bucket_available": ready,
                "blockers": [] if ready else ["point_in_time_vix_source_missing"],
            },
        )
        return path

    def _base_ledger(self, tmp: Path) -> Path:
        path = tmp / "base-ledger.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_base_clean_stack_identity_ledger",
                "status": "base_clean_stack_identity_ledger_ready",
                "unique_identity_count": 157,
                "duplicate_identity_count": 0,
            },
        )
        return path

    def _holdout(self, tmp: Path) -> Path:
        path = tmp / "holdout.json"
        _write_json(path, {"contract_id": "forward_holdout_contract", "status": "active"})
        return path

    def _options_db(self, tmp: Path, *, ready: bool = True) -> Path:
        path = tmp / "options_history.db"
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE import_batches (
                  id INTEGER PRIMARY KEY,
                  source_label TEXT,
                  data_trust TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE option_quote_snapshots (
                  id INTEGER PRIMARY KEY,
                  source_batch_id INTEGER,
                  snapshot_kind TEXT,
                  underlying TEXT,
                  option_type TEXT,
                  quote_date_et TEXT,
                  expiry TEXT,
                  bid REAL,
                  ask REAL
                )
                """
            )
            conn.execute("INSERT INTO import_batches VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')")
            if ready:
                rows = [
                    (1, 1, "intraday", "SPY", "call", "2026-01-02", "2026-06-19", 1.0, 1.2),
                    (2, 1, "intraday", "SPY", "call", "2026-01-02", "2026-02-20", 0.8, 0.9),
                    (3, 1, "intraday", "QQQ", "call", "2026-01-02", "2026-06-19", 1.1, 1.3),
                    (4, 1, "intraday", "QQQ", "call", "2026-01-02", "2026-02-20", 0.7, 0.8),
                ]
                conn.executemany("INSERT INTO option_quote_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        return path

    def test_report_is_read_only_and_blocks_missing_trend_and_vix(self) -> None:
        with WorkspaceTempDir(prefix="pmcc-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_vix_bucket_path=self._vix(tmp, ready=False),
                base_clean_stack_identity_ledger_path=self._base_ledger(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                options_history_db_path=self._options_db(tmp),
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_pmcc_diagonal_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertIn("missing_point_in_time_trend_or_regime_inputs", report["blockers"])
        self.assertIn("point_in_time_vix_bucket_blocked", report["blockers"])
        self.assertEqual(report["smallest_next_blocker_clearing_slice"], "missing_point_in_time_trend_or_regime_inputs")

    def test_invalid_uncapped_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="pmcc-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = self._valid_preregistration(tmp)
            payload = json.loads(invalid.read_text(encoding="utf8"))
            payload["undefined_or_uncapped_short_call_risk_allowed"] = True
            _write_json(invalid, payload)
            report = readiness.build_report(
                preregistered_playbook_path=invalid,
                feature_store_path=self._feature_store(tmp, trend_ready=True),
                point_in_time_vix_bucket_path=self._vix(tmp, ready=True),
                base_clean_stack_identity_ledger_path=self._base_ledger(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                options_history_db_path=self._options_db(tmp),
            )

        self.assertEqual(report["status"], "blocked_invalid_pmcc_diagonal_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("undefined_or_uncapped_short_call_risk_not_false", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_ready_fixture_can_reach_ready_status(self) -> None:
        with WorkspaceTempDir(prefix="pmcc-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp, trend_ready=True),
                point_in_time_vix_bucket_path=self._vix(tmp, ready=True),
                base_clean_stack_identity_ledger_path=self._base_ledger(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                options_history_db_path=self._options_db(tmp),
            )

        self.assertEqual(report["status"], "pmcc_diagonal_replay_readiness_ready")
        self.assertEqual(report["blockers"], [])
        self.assertIsNone(report["smallest_next_blocker_clearing_slice"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="pmcc-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                point_in_time_vix_bucket_path=self._vix(tmp, ready=False),
                base_clean_stack_identity_ledger_path=self._base_ledger(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                options_history_db_path=self._options_db(tmp),
            )
            artifacts = readiness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "readiness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "readiness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options PMCC Diagonal Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
