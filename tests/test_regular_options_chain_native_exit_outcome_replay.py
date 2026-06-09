from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_chain_native_exit_outcome_replay as replay


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _chain_replay_payload() -> dict:
    selected_spread = {
        "long_contract_symbol": "META260626P00615000",
        "short_contract_symbol": "META260626P00555000",
        "expiry": "2026-06-26",
        "net_debit": 5.0,
        "ask_bid_debit": 4.9,
        "mid_debit": 4.5,
        "spread_width": 60.0,
        "debit_pct_of_width": 8.33,
    }
    return {
        "status": "chain_native_filter_relaxation_replay_readback",
        "live_policy_change": False,
        "summary": {"overall_status": "chain_native_filter_relaxation_replay_candidates_found_diagnostic_only"},
        "target_replays": [
            {
                "target_id": "regular_bearish_put_primary:2026-05-22",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "scenario_rows": [
                    {
                        "ticker": "META",
                        "scan_date": "2026-05-22",
                        "trade_type": "put",
                        "scenario_id": "current_chain_native_filters",
                        "scenario_description": "Current filters.",
                        "status": "selected_chain_native_entry_spread",
                        "selected_spread": selected_spread,
                    },
                    {
                        "ticker": "META",
                        "scan_date": "2026-05-22",
                        "trade_type": "put",
                        "scenario_id": "combined_broad_entry_relaxation",
                        "scenario_description": "Combined broad relaxation.",
                        "relaxed_filter_names": ["max_debit_pct_of_width"],
                        "status": "selected_chain_native_entry_spread",
                        "selected_spread": selected_spread,
                    },
                ],
            }
        ],
    }


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_label TEXT NOT NULL,
            dataset_kind TEXT NOT NULL DEFAULT 'intraday_csv',
            data_trust TEXT NOT NULL DEFAULT 'trusted',
            input_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            imported_rows INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            rejected_rows INTEGER NOT NULL,
            warnings_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            as_of_utc TEXT NOT NULL,
            quote_date_et TEXT NOT NULL,
            quote_minute_et INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL DEFAULT 'intraday',
            underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT
        );
        CREATE INDEX idx_option_quotes_contract_date
            ON option_quote_snapshots (contract_symbol, snapshot_kind, quote_date_et, quote_minute_et DESC);
        INSERT INTO import_batches (
            source_label, dataset_kind, data_trust, input_path, file_hash, imported_at_utc,
            total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
        ) VALUES ('thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture.csv', 'hash', '2026-06-04T20:00:00Z', 0, 0, 0, 0, '[]');
        """
    )
    conn.commit()
    conn.close()


def _insert_quote(path: Path, *, symbol: str, date: str, minute: int, bid: float, ask: float) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
            contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
            underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, ?, 'intraday', 'META', ?, '2026-06-26', 'put', 600.0, ?, ?, NULL, NULL, NULL, 10, 100, 1)
        """,
        (f"{date}T20:00:00Z", date, minute, symbol, bid, ask),
    )
    conn.commit()
    conn.close()


class RegularOptionsChainNativeExitOutcomeReplayTests(unittest.TestCase):
    def test_full_exit_coverage_emits_diagnostic_exact_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chain_path = root / "chain.json"
            db_path = root / "options_history.db"
            _write_json(chain_path, _chain_replay_payload())
            _init_db(db_path)
            _insert_quote(db_path, symbol="META260626P00615000", date="2026-06-04", minute=955, bid=8.0, ask=8.2)
            _insert_quote(db_path, symbol="META260626P00555000", date="2026-06-04", minute=955, bid=0.9, ask=1.0)

            report = replay.build_report(
                chain_native_replay_path=chain_path,
                db_path=db_path,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["status"], "chain_native_exit_outcome_replay_readback")
        self.assertEqual(
            report["summary"]["overall_status"],
            "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only",
        )
        self.assertEqual(report["summary"]["selected_scenario_row_count"], 2)
        self.assertEqual(report["summary"]["priced_scenario_row_count"], 2)
        self.assertEqual(report["summary"]["missing_exit_quote_demand_count"], 0)
        self.assertFalse(report["summary"]["promotion_ready"])
        self.assertEqual(report["outcome_rows"][0]["exit_side_aware_credit"], 7.0)
        self.assertEqual(report["outcome_rows"][0]["quote_evidence_class"], "trusted_intraday_opra_nbbo")
        self.assertEqual(report["next_evidence_queue"][0]["action"], "validate_chain_native_relaxation_on_later_holdout")

    def test_missing_exit_quotes_emit_demands_without_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chain_path = root / "chain.json"
            db_path = root / "options_history.db"
            _write_json(chain_path, _chain_replay_payload())
            _init_db(db_path)
            report = replay.build_report(chain_native_replay_path=chain_path, db_path=db_path)

        self.assertEqual(report["summary"]["overall_status"], "chain_native_exit_outcome_replay_exit_quote_gap")
        self.assertEqual(report["summary"]["priced_scenario_row_count"], 0)
        self.assertEqual(report["summary"]["missing_exit_quote_demand_count"], 2)
        self.assertIn("exit_quote_coverage_incomplete", report["summary"]["blockers"])
        self.assertEqual(report["next_evidence_queue"][0]["action"], "import_or_query_chain_native_exit_contract_quotes")

    def test_negative_relaxed_outcome_routes_to_archive_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chain_path = root / "chain.json"
            db_path = root / "options_history.db"
            _write_json(chain_path, _chain_replay_payload())
            _init_db(db_path)
            _insert_quote(db_path, symbol="META260626P00615000", date="2026-06-04", minute=955, bid=0.8, ask=1.0)
            _insert_quote(db_path, symbol="META260626P00555000", date="2026-06-04", minute=955, bid=0.4, ask=0.5)
            report = replay.build_report(chain_native_replay_path=chain_path, db_path=db_path)

        self.assertLess(report["summary"]["best_relaxed_scenario"]["avg_net_pnl_pct"], 0)
        self.assertEqual(report["next_evidence_queue"][0]["action"], "archive_negative_chain_native_relaxation_branch")

    def test_missing_inputs_and_live_policy_change_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = replay.build_report(chain_native_replay_path=root / "missing.json", db_path=root / "missing.db")
            self.assertEqual(missing["status"], "blocked_missing_inputs")
            self.assertIn("chain_native_filter_relaxation_replay", missing["summary"]["missing_required_inputs"])
            self.assertIn("options_history_db", missing["summary"]["missing_required_inputs"])

            chain_path = root / "chain.json"
            db_path = root / "options_history.db"
            payload = _chain_replay_payload()
            payload["live_policy_change"] = True
            _write_json(chain_path, payload)
            _init_db(db_path)
            invalid = replay.build_report(chain_native_replay_path=chain_path, db_path=db_path)
            self.assertEqual(invalid["status"], "invalid_live_policy_change")
            self.assertTrue(invalid["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chain_path = root / "chain.json"
            db_path = root / "options_history.db"
            _write_json(chain_path, _chain_replay_payload())
            _init_db(db_path)
            report = replay.build_report(chain_native_replay_path=chain_path, db_path=db_path)
            markdown = replay.render_markdown(report)
            artifacts = replay.write_outputs(report, output_dir=root / "out", docs_report=root / "docs" / "exit.md")

            self.assertIn("# Regular Options Chain-Native Exit Outcome Replay", markdown)
            self.assertIn("Exit Quote Demands", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
