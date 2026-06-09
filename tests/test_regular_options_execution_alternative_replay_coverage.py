from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_execution_alternative_replay_coverage as coverage


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf8")


def _readiness_payload() -> dict:
    return {
        "status": "execution_alternative_replay_readiness_readback",
        "live_policy_change": False,
        "summary": {
            "overall_status": "blocked_ready_seed_missing_execution_alternative_replay_engine",
            "top_spread_replay_seed_count": 1,
            "contract_replacement_seed_count": 1,
        },
        "candidate_queue": [
            {
                "readiness_status": "alternative_seed_ready_engine_missing",
                "row_index": 0,
                "ticker": "QQQ",
                "lane": "volatility_expansion_observation",
                "scan_date": "2026-06-04",
                "entry_time_utc": "2026-06-04T14:10:30Z",
                "selected_long_contract_symbol": "QQQ260618C00728000",
                "selected_short_contract_symbol": "QQQ260618C00750000",
                "top_alternatives": [
                    {
                        "rank": 1,
                        "long_contract_symbol": "QQQ260618C00730000",
                        "short_contract_symbol": "QQQ260618C00752000",
                    }
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
        """
    )
    conn.execute(
        """
        INSERT INTO import_batches (
            source_label, dataset_kind, data_trust, input_path, file_hash, imported_at_utc,
            total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
        ) VALUES ('thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture.csv', 'hash', '2026-06-04T20:00:00Z', 0, 0, 0, 0, '[]')
        """
    )
    conn.commit()
    conn.close()


def _insert_quote(path: Path, *, symbol: str, minute: int, bid: float, ask: float) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
            contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
            underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, '2026-06-04', ?, 'intraday', 'QQQ', ?, '2026-06-18', 'call', 730.0, ?, ?, NULL, NULL, NULL, 10, 100, 1)
        """,
        (f"2026-06-04T{minute // 60 + 4:02d}:{minute % 60:02d}:00Z", minute, symbol, bid, ask),
    )
    conn.commit()
    conn.close()


class RegularOptionsExecutionAlternativeReplayCoverageTests(unittest.TestCase):
    def test_full_quote_coverage_emits_true_side_aware_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            db_path = root / "options_history.db"
            _write_json(readiness_path, _readiness_payload())
            _init_db(db_path)
            for symbol, entry_bid, entry_ask, exit_bid, exit_ask in [
                ("QQQ260618C00728000", 10.0, 10.1, 11.0, 11.1),
                ("QQQ260618C00750000", 2.0, 2.1, 2.3, 2.4),
                ("QQQ260618C00730000", 9.0, 9.2, 10.5, 10.6),
                ("QQQ260618C00752000", 1.4, 1.6, 1.7, 1.9),
            ]:
                _insert_quote(db_path, symbol=symbol, minute=610, bid=entry_bid, ask=entry_ask)
                _insert_quote(db_path, symbol=symbol, minute=955, bid=exit_bid, ask=exit_ask)

            report = coverage.build_report(
                readiness_path=readiness_path,
                db_path=db_path,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["status"], "execution_alternative_replay_coverage_readback")
        self.assertEqual(report["summary"]["overall_status"], "execution_alternative_replay_coverage_ready")
        self.assertEqual(report["summary"]["true_top_spread_replay_pnl_count"], 1)
        self.assertEqual(report["summary"]["true_contract_replacement_pnl_count"], 1)
        row = report["coverage_rows"][0]
        self.assertTrue(row["top_spread"]["true_side_aware_pnl_available"])
        self.assertEqual(row["top_spread"]["entry_side_aware_debit"], 7.8)
        self.assertIn("trusted_intraday_opra_nbbo", row["top_spread"]["entry_long_quote"]["quote_evidence_class"])
        self.assertEqual(report["summary"]["missing_quote_demand_count"], 0)
        self.assertEqual(report["summary"]["quote_demand_manifest_status"], "no_missing_quote_demands")
        self.assertEqual(report["quote_demands"], [])

    def test_missing_readiness_or_db_blocks_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = coverage.build_report(readiness_path=root / "missing.json", db_path=root / "missing.db")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("execution_alternative_replay_readiness", report["summary"]["missing_required_inputs"])
        self.assertIn("options_history_db", report["summary"]["missing_required_inputs"])

    def test_partial_exit_coverage_does_not_emit_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            db_path = root / "options_history.db"
            _write_json(readiness_path, _readiness_payload())
            _init_db(db_path)
            _insert_quote(db_path, symbol="QQQ260618C00730000", minute=610, bid=9.0, ask=9.2)
            _insert_quote(db_path, symbol="QQQ260618C00752000", minute=610, bid=1.4, ask=1.6)
            _insert_quote(db_path, symbol="QQQ260618C00730000", minute=955, bid=10.5, ask=10.6)

            report = coverage.build_report(readiness_path=readiness_path, db_path=db_path)

        self.assertEqual(report["summary"]["true_top_spread_replay_pnl_count"], 0)
        self.assertEqual(report["summary"]["top_spread_entry_quote_coverage_status"], "full")
        self.assertEqual(report["summary"]["top_spread_exit_quote_coverage_status"], "missing")
        self.assertIn("alternate_contract_exit_quote_coverage_missing", report["summary"]["blockers"])
        self.assertIn("missing_exit_short_quote", report["coverage_rows"][0]["top_spread"]["blockers"])
        self.assertEqual(report["summary"]["quote_demand_manifest_status"], "ready_for_import_or_query")
        self.assertEqual(report["summary"]["missing_quote_demand_count"], 5)
        self.assertEqual(report["summary"]["missing_entry_quote_demand_count"], 2)
        self.assertEqual(report["summary"]["missing_exit_quote_demand_count"], 3)
        top_exit_short_demands = [
            item
            for item in report["quote_demands"]
            if item["contract_symbol"] == "QQQ260618C00752000"
            and item["quote_phase"] == "exit"
            and item["quote_minute_et"] == 955
        ]
        self.assertEqual(len(top_exit_short_demands), 1)
        self.assertIn("top_spread:exit_short", top_exit_short_demands[0]["usage_labels"])
        self.assertIn("contract_replacement:exit_short", top_exit_short_demands[0]["usage_labels"])
        self.assertEqual(report["next_evidence_queue"][0]["count"], 2)
        self.assertEqual(report["next_evidence_queue"][1]["count"], 3)

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            db_path = root / "options_history.db"
            payload = _readiness_payload()
            payload["live_policy_change"] = True
            _write_json(readiness_path, payload)
            _init_db(db_path)

            report = coverage.build_report(readiness_path=readiness_path, db_path=db_path)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness_path = root / "readiness.json"
            db_path = root / "options_history.db"
            _write_json(readiness_path, _readiness_payload())
            _init_db(db_path)
            report = coverage.build_report(readiness_path=readiness_path, db_path=db_path)
            markdown = coverage.render_markdown(report)
            artifacts = coverage.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "coverage.md",
            )

            self.assertIn("# Regular Options Execution Alternative Replay Coverage", markdown)
            self.assertIn("## Quote Demand Manifest", markdown)
            self.assertIn("does not create trades", markdown)
            self.assertIn("P&L is emitted only", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
