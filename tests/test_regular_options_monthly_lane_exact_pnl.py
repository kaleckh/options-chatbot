from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_monthly_lane_exact_pnl as monthly_pnl


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_quote_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY,
                source_label TEXT NOT NULL,
                data_trust TEXT NOT NULL
            );
            CREATE TABLE option_quote_snapshots (
                source_batch_id INTEGER NOT NULL,
                contract_symbol TEXT NOT NULL,
                snapshot_kind TEXT NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                as_of_utc TEXT NOT NULL,
                bid REAL,
                ask REAL,
                underlying_price REAL
            );
            """
        )
        conn.execute(
            "INSERT INTO import_batches(id, source_label, data_trust) VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')"
        )
        rows = [
            ("ABC250919C00100000", "2025-08-15", 610, "2025-08-15T14:10:00Z", 5.0, 5.1),
            ("ABC250919C00110000", "2025-08-15", 610, "2025-08-15T14:10:00Z", 1.0, 1.1),
            ("ABC250919C00100000", "2025-09-15", 955, "2025-09-15T19:55:00Z", 7.0, 7.2),
            ("ABC250919C00110000", "2025-09-15", 955, "2025-09-15T19:55:00Z", 2.0, 2.1),
            ("XYZ250919C00100000", "2025-08-16", 610, "2025-08-16T14:10:00Z", 4.0, 4.2),
            ("XYZ250919C00110000", "2025-08-16", 610, "2025-08-16T14:10:00Z", 1.2, 1.3),
            ("XYZ250919C00100000", "2025-09-15", 955, "2025-09-15T19:55:00Z", 5.0, 5.2),
            ("XYZ250919C00110000", "2025-09-15", 955, "2025-09-15T19:55:00Z", 1.0, 1.1),
        ]
        conn.executemany(
            """
            INSERT INTO option_quote_snapshots(
                source_batch_id,
                contract_symbol,
                snapshot_kind,
                quote_date_et,
                quote_minute_et,
                as_of_utc,
                bid,
                ask,
                underlying_price
            )
            VALUES (1, ?, 'intraday', ?, ?, ?, ?, ?, 100.0)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _multilane() -> dict:
    return {
        "generated_at": "2026-06-08T00:00:00Z",
        "selected_trades": [
            {
                "entry_date": "2025-08-15",
                "exit_date": "2025-09-15",
                "exact_priced": True,
                "priced": True,
                "proof_grade": "trusted_intraday_opra_nbbo",
                "lane_family": "bullish_pullback_observation",
                "lane_id": "bullish_pullback_core",
                "ticker": "ABC",
                "direction": "call",
                "strategy_type": "vertical_spread",
                "long_contract_symbol": "ABC250919C00100000",
                "short_contract_symbol": "ABC250919C00110000",
                "source_playbook": "fixture",
                "source_result_path": "fixture.json",
                "pnl_pct": 10.0,
            },
            {
                "entry_date": "2025-08-16",
                "exit_date": "2025-09-16",
                "exact_priced": True,
                "priced": True,
                "proof_grade": "trusted_intraday_opra_nbbo",
                "lane_family": "bullish_pullback_observation",
                "lane_id": "bullish_pullback_core",
                "ticker": "XYZ",
                "direction": "call",
                "strategy_type": "vertical_spread",
                "long_contract_symbol": "XYZ250919C00100000",
                "short_contract_symbol": "XYZ250919C00110000",
                "source_playbook": "fixture",
                "source_result_path": "fixture.json",
                "pnl_pct": -5.0,
            },
            {
                "entry_date": "2025-09-02",
                "exit_date": "2025-10-02",
                "exact_priced": True,
                "priced": True,
                "proof_grade": "trusted_intraday_opra_nbbo",
                "lane_family": "bullish_pullback_observation",
                "lane_id": "bullish_pullback_core",
                "ticker": "ABC",
                "direction": "call",
                "strategy_type": "vertical_spread",
                "long_contract_symbol": "ABC250919C00100000",
                "short_contract_symbol": "ABC250919C00110000",
                "source_playbook": "fixture",
                "source_result_path": "fixture.json",
                "pnl_pct": 8.0,
            },
        ],
    }


def _run_artifact() -> dict:
    return {
        "authoritative_profitability_basis": "exact_contract_only",
        "truth_source": "historical_imported",
        "execution_realism": "quote_backed_intraday_replay",
        "truth_store": {
            "snapshot_kind": "intraday",
            "data_trust": "trusted",
            "source_labels": ["thetadata_opra_nbbo_1m"],
        },
        "playbook": "tracked_winner_chain_native_qqq_time65_all_sleeves",
        "result_path": "fixture_run.json",
        "trades": [
            {
                "date": "2025-08-15",
                "exit_date": "2025-09-15",
                "priced": True,
                "ticker": "ABC",
                "strategy_type": "vertical_spread",
                "contract_symbol": "ABC250919C00100000",
                "short_contract_symbol": "ABC250919C00110000",
                "sleeve_id": "tracked_winner_chain_native_qqq_time65_all_sleeves",
                "net_pnl_pct": 10.0,
            },
            {
                "date": "2025-09-02",
                "exit_date": "2025-10-02",
                "priced": True,
                "ticker": "ABC",
                "strategy_type": "vertical_spread",
                "contract_symbol": "ABC250919C00100000",
                "short_contract_symbol": "ABC250919C00110000",
                "sleeve_id": "tracked_winner_chain_native_qqq_time65_all_sleeves",
                "net_pnl_pct": 8.0,
            },
        ],
        "unpriced_trades": [
            {
                "date": "2025-08-16",
                "ticker": "XYZ",
                "strategy_type": "vertical_spread",
                "unpriced_reason": "missing_exit_quote_for_leg",
                "selected_spread": {
                    "entry_date": "2025-08-16",
                    "long_contract_symbol": "XYZ250919C00100000",
                    "short_contract_symbol": "XYZ250919C00110000",
                },
            }
        ],
    }


class RegularOptionsMonthlyLaneExactPnlTests(unittest.TestCase):
    def test_build_report_attaches_exact_bid_ask_and_side_aware_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            multilane = root / "multilane.json"
            quotes = root / "options_history.db"
            _write_json(multilane, _multilane())
            _write_quote_db(quotes)

            report = monthly_pnl.build_report(
                multilane_path=multilane,
                db_path=quotes,
                target_month="2025-08",
                target_lane="bullish_pullback_observation",
                generated_at_utc="2026-06-08T00:00:00Z",
            )

        self.assertEqual(report["status"], "lane_month_exact_pnl_partial")
        self.assertEqual(report["summary"]["target_month"], "2025-08")
        self.assertEqual(report["summary"]["true_executable_lane_month_pnl_rows"], 1)
        self.assertEqual(report["summary"]["missing_proof_count"], 1)
        self.assertEqual(report["summary"]["metrics"]["avg_net_pnl_pct"], 18.88)
        self.assertEqual(report["summary"]["later_month_holdout_status"], "pending_exact_quote_attachment")
        row = report["lane_month_rows"][0]
        self.assertEqual(row["entry_side_aware_debit"], 4.1)
        self.assertEqual(row["exit_side_aware_value"], 4.9)
        self.assertEqual(row["net_pnl_usd"], 77.4)
        self.assertEqual(row["entry_long_quote"]["ask"], 5.1)
        self.assertEqual(row["exit_short_quote"]["ask"], 2.1)
        self.assertEqual(row["decision"], "count_as_read_only_lane_month_exact_pnl")

    def test_build_report_consumes_exact_run_trade_schema_with_target_lane_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_path = root / "run.json"
            quotes = root / "options_history.db"
            _write_json(run_path, _run_artifact())
            _write_quote_db(quotes)

            report = monthly_pnl.build_report(
                multilane_path=run_path,
                db_path=quotes,
                target_month="2025-08",
                target_lane="tracked_winner_primary",
                generated_at_utc="2026-06-08T00:00:00Z",
            )

        self.assertEqual(report["status"], "lane_month_exact_pnl_partial")
        self.assertEqual(report["summary"]["target_lane"], "tracked_winner_primary")
        self.assertEqual(report["summary"]["source_candidate_count"], 2)
        self.assertEqual(report["summary"]["true_executable_lane_month_pnl_rows"], 1)
        self.assertEqual(report["summary"]["missing_proof_count"], 1)
        self.assertEqual(report["summary"]["later_month_source_counts"], {"2025-09": 1})
        priced = [row for row in report["lane_month_rows"] if row["true_executable_pnl_available"]][0]
        missing = [row for row in report["lane_month_rows"] if not row["true_executable_pnl_available"]][0]
        self.assertEqual(priced["lane"], "tracked_winner_primary")
        self.assertEqual(priced["lane_id"], "tracked_winner_chain_native_qqq_time65_all_sleeves")
        self.assertEqual(priced["source_playbook"], "tracked_winner_chain_native_qqq_time65_all_sleeves")
        self.assertEqual(priced["entry_side_aware_debit"], 4.1)
        self.assertEqual(missing["source_summary_pnl_pct"], None)
        self.assertIn("missing_exit_date", missing["blockers"])

    def test_build_report_uses_missing_quote_date_for_unpriced_exit_quote_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_path = root / "run.json"
            quotes = root / "options_history.db"
            run = _run_artifact()
            run["unpriced_trades"][0]["missing_quote_date"] = "2025-09-15"
            _write_json(run_path, run)
            _write_quote_db(quotes)

            report = monthly_pnl.build_report(
                multilane_path=run_path,
                db_path=quotes,
                target_month="2025-08",
                target_lane="tracked_winner_primary",
                generated_at_utc="2026-06-08T00:00:00Z",
            )

        self.assertEqual(report["summary"]["true_executable_lane_month_pnl_rows"], 2)
        self.assertEqual(report["summary"]["missing_proof_count"], 0)
        repaired = [
            row
            for row in report["lane_month_rows"]
            if row["ticker"] == "XYZ" and row["true_executable_pnl_available"]
        ][0]
        self.assertEqual(repaired["exit_date"], "2025-09-15")
        self.assertEqual(repaired["entry_side_aware_debit"], 3.0)
        self.assertEqual(repaired["exit_side_aware_value"], 3.9)
        self.assertEqual(repaired["net_pnl_usd"], 87.4)

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = monthly_pnl.build_report(
                multilane_path=Path(tmp) / "missing.json",
                db_path=Path(tmp) / "missing.db",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("regular_options_multilane", report["summary"]["missing_required_inputs"])
        self.assertIn("options_history_db", report["summary"]["missing_required_inputs"])

    def test_write_outputs_creates_latest_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            multilane = root / "multilane.json"
            quotes = root / "options_history.db"
            _write_json(multilane, _multilane())
            _write_quote_db(quotes)
            report = monthly_pnl.build_report(multilane_path=multilane, db_path=quotes)
            artifacts = monthly_pnl.write_outputs(report, output_dir=root / "out")

            self.assertTrue(Path(artifacts["json"]).exists())
            self.assertTrue(Path(artifacts["latest_json"]).exists())


if __name__ == "__main__":
    unittest.main()
