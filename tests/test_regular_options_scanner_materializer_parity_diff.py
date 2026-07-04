from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_scanner_materializer_parity_diff as parity


NOW = "2026-06-24T20:30:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _materializer_row(date: str, ticker: str, *, lane: str = "bullish_pullback_observation", selected: bool = True) -> dict:
    return {
        "candidate_generation_date": date,
        "date": date,
        "entry_date": date,
        "lane_id": lane,
        "lane": lane,
        "ticker": ticker,
        "symbol": ticker,
        "selected_candidate": selected,
        "explicit_no_pick": not selected,
        "no_pick_reason": None if selected else "fixture_no_pick",
        "direction": "call",
        "long_contract_symbol": f"{ticker}260717C00100000",
        "short_contract_symbol": f"{ticker}260717C00105000",
        "signal_evidence": {"prior_20_trading_day_return_pct": 12.0},
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "scanner_parity": False,
        "production_scanner_replay": False,
    }


def _scan_pick(date: str, ticker: str, *, lane: str = "bullish_pullback_observation") -> dict:
    return {
        "scan_date": date,
        "logged_at": f"{date}T15:02:00Z",
        "playbook_id": lane,
        "ticker": ticker,
        "contract_symbol": f"{ticker}260717C00100000",
        "short_contract_symbol": f"{ticker}260717C00105000",
        "entry_execution_basis": "spread_ask_bid",
        "entry_execution_price": 1.2,
        "quote_source": "alpaca_opra",
        "quote_timestamp_utc": f"{date}T15:01:30Z",
    }


def _policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "policy_id": "historical_filtered_candidate_policy_v1",
                "conditions": [
                    {"field": "ticker", "op": "in", "value": ["AAPL", "GOOGL", "JNJ", "IWM", "CVX", "QQQ"]},
                    {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.990605},
                ],
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
            },
            sort_keys=True,
        ),
        encoding="utf8",
    )


def _write_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT,
                source_label TEXT,
                playbook TEXT,
                scan_picks_count INTEGER,
                eligibility_status TEXT,
                eligibility_blockers TEXT,
                notes_json TEXT,
                run_id TEXT
            )
            """
        )
        rows = [
            (
                1,
                "2026-06-15T15:00:00Z",
                "bullish_pullback_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps(
                    {
                        "scan_funnel": {"returned_picks": 0, "drop_counts": {"momentum": 1}},
                        "symbol_diagnostics": {
                            "scan_drop_reasons": {
                                "AAPL": {"drop_key": "momentum", "details": {"reason": "below_momentum"}}
                            }
                        },
                    }
                ),
                "scheduled_scan:2026-06-15:test:bp",
            ),
            (
                2,
                "2026-06-17T15:00:00Z",
                "bullish_pullback_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps({"scan_funnel": {"returned_picks": 0, "drop_counts": {"history_or_liquidity": 1}}}),
                "scheduled_scan:2026-06-17:test:bp",
            ),
            (
                3,
                "2026-06-22T15:00:00Z",
                "bullish_pullback_observation",
                1,
                "eligible",
                json.dumps([]),
                json.dumps({"scan_funnel": {"returned_picks": 1, "drop_counts": {}}}),
                "scheduled_scan:2026-06-22:test:bp",
            ),
            (
                4,
                "2026-06-23T15:00:00Z",
                "bullish_pullback_observation",
                1,
                "eligible",
                json.dumps([]),
                json.dumps({"scan_funnel": {"returned_picks": 1, "drop_counts": {}}}),
                "scheduled_scan:2026-06-23:test:bp",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO forward_sessions (
                id, recorded_at_utc, source_label, playbook, scan_picks_count, eligibility_status,
                eligibility_blockers, notes_json, run_id
            )
            VALUES (?, ?, 'scheduled_scan', ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


class RegularOptionsScannerMaterializerParityDiffTests(unittest.TestCase):
    def test_fixture_days_cover_required_divergence_classes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            materializer = root / "materializer.jsonl"
            scan_picks = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            policy = root / "policy.json"
            _write_jsonl(
                materializer,
                [
                    _materializer_row("2026-06-15", "AAPL"),
                    _materializer_row("2026-06-16", "GOOGL"),
                    _materializer_row("2026-06-17", "JNJ"),
                    _materializer_row("2026-06-22", "CVX", selected=False),
                    _materializer_row("2026-06-23", "QQQ"),
                ],
            )
            _write_jsonl(scan_picks, [_scan_pick("2026-06-22", "CVX"), _scan_pick("2026-06-23", "QQQ")])
            _write_ledger(ledger)
            _policy(policy)

            report = parity.build_report(
                materializer_decisions_path=materializer,
                materializer_latest_path=root / "missing_latest.json",
                scan_picks_path=scan_picks,
                ledger_db_path=ledger,
                policy_contract_path=policy,
                start_date="2026-06-15",
                end_date="2026-06-23",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "scanner_materializer_parity_diff_ready")
        self.assertEqual(report["summary"]["filtered_materializer_candidate_rows"], 4)
        self.assertEqual(report["summary"]["matching_scheduled_scan_pick_rows"], 1)
        counts = report["summary"]["divergence_counts"]
        self.assertEqual(counts["scanner_gate_drop:momentum"], 1)
        self.assertEqual(counts["no_scheduled_session"], 1)
        self.assertEqual(counts["insufficient_drop_reason_data"], 1)
        self.assertEqual(counts["entry_time_basis_differs"], 1)
        self.assertEqual(counts["materializer_no_pick_scanner_pick"], 1)
        self.assertEqual(report["summary"]["top_starvation_gate"]["gate"], "momentum")
        self.assertTrue(report["boundary"]["does_not_change_scanner"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["scanner_policy_changed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        classes_by_symbol = {row["symbol"]: row["divergence_class"] for row in report["divergence_rows"]}
        self.assertEqual(classes_by_symbol["AAPL"], "scanner_gate_drop:momentum")
        self.assertEqual(classes_by_symbol["GOOGL"], "no_scheduled_session")
        self.assertEqual(classes_by_symbol["JNJ"], "insufficient_drop_reason_data")
        self.assertEqual(classes_by_symbol["QQQ"], "entry_time_basis_differs")
        self.assertEqual(classes_by_symbol["CVX"], "materializer_no_pick_scanner_pick")

    def test_default_post_freeze_window_reports_missing_materializer_rows_without_invention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            materializer = root / "materializer.jsonl"
            scan_picks = root / "scan_picks.jsonl"
            ledger = root / "forward_tracking_authoritative.db"
            policy = root / "policy.json"
            _write_jsonl(materializer, [_materializer_row("2026-05-29", "AAPL")])
            _write_jsonl(scan_picks, [])
            _write_ledger(ledger)
            _policy(policy)

            report = parity.build_report(
                materializer_decisions_path=materializer,
                materializer_latest_path=root / "missing_latest.json",
                scan_picks_path=scan_picks,
                ledger_db_path=ledger,
                policy_contract_path=policy,
                start_date="2026-06-14",
                end_date="2026-06-23",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "materializer_window_has_no_rows")
        self.assertEqual(report["materializer_coverage"]["row_count_in_window"], 0)
        self.assertEqual(report["materializer_coverage"]["filter_matched_selected_rows_in_window"], 0)
        self.assertIn("no rows are invented", report["materializer_coverage"]["current_default_window_note"])
        self.assertEqual(report["divergence_rows"], [])

    def test_write_outputs_creates_only_requested_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            materializer = root / "inputs" / "materializer.jsonl"
            scan_picks = root / "inputs" / "scan_picks.jsonl"
            ledger = root / "inputs" / "forward_tracking_authoritative.db"
            policy = root / "inputs" / "policy.json"
            output_dir = root / "out"
            docs_report = root / "docs" / "parity.md"
            _write_jsonl(materializer, [_materializer_row("2026-06-15", "AAPL")])
            _write_jsonl(scan_picks, [])
            _write_ledger(ledger)
            _policy(policy)
            report = parity.build_report(
                materializer_decisions_path=materializer,
                materializer_latest_path=root / "missing_latest.json",
                scan_picks_path=scan_picks,
                ledger_db_path=ledger,
                policy_contract_path=policy,
                start_date="2026-06-15",
                end_date="2026-06-15",
                generated_at_utc=NOW,
            )
            artifacts = parity.write_outputs(report, output_dir=output_dir, docs_report=docs_report)
            doc = docs_report.read_text(encoding="utf8")
            self.assertIn("latest_json", artifacts)
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "latest.md").exists())
            self.assertTrue(docs_report.exists())
            self.assertIn("Scanner Materializer Parity Diff", doc)
            self.assertIn("Diagnostic only", doc)
            self.assertIn("does not run or change the scanner", doc)


if __name__ == "__main__":
    unittest.main()
