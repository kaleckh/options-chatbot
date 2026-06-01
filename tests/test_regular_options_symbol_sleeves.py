from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from scripts import build_regular_options_symbol_sleeves as symbol_sleeves


class RegularOptionsSymbolSleevesTests(unittest.TestCase):
    def test_universe_merge_dedupes_source_tiers_and_details(self):
        universe: dict[str, dict] = {}

        symbol_sleeves.add_symbol_source(universe, "aapl", "current_queue/configured_scan_universe", "playbook:a")
        symbol_sleeves.add_symbol_source(universe, "AAPL", "current_queue/configured_scan_universe", "playbook:a")
        symbol_sleeves.add_symbol_source(universe, "AAPL", "lane_lab_all_planned_research", "lane_lab:b")

        self.assertEqual(sorted(universe), ["AAPL"])
        self.assertEqual(
            universe["AAPL"]["source_tiers"],
            ["current_queue/configured_scan_universe", "lane_lab_all_planned_research"],
        )
        self.assertEqual(universe["AAPL"]["source_details"], ["playbook:a", "lane_lab:b"])

    def test_proof_grade_requires_trusted_intraday_exact_imported_spread(self):
        run = {"truth_source": "historical_imported", "execution_realism": "quote_backed_intraday_replay"}
        trade = {
            "priced": True,
            "entry_contract_resolution": "exact_listed_spread_contract",
            "exit_fill_basis": "imported_spread_mark",
        }

        evidence = symbol_sleeves._proof_grade_for_run(run)

        self.assertEqual(evidence, symbol_sleeves.TRUSTED_EXACT)
        self.assertTrue(symbol_sleeves._is_exact_imported_trade(trade, evidence))
        self.assertFalse(
            symbol_sleeves._is_exact_imported_trade(
                {**trade, "exit_fill_basis": "daily_close_mark"},
                evidence,
            )
        )
        self.assertEqual(
            symbol_sleeves._proof_grade_for_run({"truth_source": "historical_imported_daily"}),
            symbol_sleeves.DAILY_RESEARCH,
        )

    def test_sparse_positive_exact_row_is_watch_not_keep(self):
        card = {
            "evidence_class": symbol_sleeves.TRUSTED_EXACT,
            "source_tiers": ["exact_intraday_run_artifacts"],
            "metrics": {
                "candidates": 3,
                "exact_trusted_priced_trades": 2,
                "unresolved_rows": 1,
                "quote_coverage": 66.67,
                "profit_factor": 4.0,
                "avg_pnl": 35.0,
            },
        }

        status, reasons = symbol_sleeves.classify_symbol_lane(card)

        self.assertEqual(status, "watch")
        self.assertIn("sample_status:thin", reasons)
        self.assertIn("positive_but_thin_or_incomplete", reasons)

    def test_adequate_negative_exact_evidence_is_rejected(self):
        card = {
            "evidence_class": symbol_sleeves.TRUSTED_EXACT,
            "source_tiers": ["exact_intraday_run_artifacts"],
            "metrics": {
                "candidates": 10,
                "exact_trusted_priced_trades": 10,
                "unresolved_rows": 0,
                "quote_coverage": 100.0,
                "profit_factor": 0.4,
                "avg_pnl": -20.0,
            },
        }

        status, reasons = symbol_sleeves.classify_symbol_lane(card)

        self.assertEqual(status, "rejected")
        self.assertIn("adequate_negative_exact_intraday_evidence", reasons)

    def test_latest_stale_detection_finds_newer_timestamped_sibling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            latest = root / "latest.json"
            newer = root / "regular_options_symbol_sleeves_20990101T000000Z.json"
            latest.write_text(json.dumps({"generated_at_utc": "2026-01-01T00:00:00Z"}), encoding="utf8")
            time.sleep(0.01)
            newer.write_text(json.dumps({"generated_at_utc": "2099-01-01T00:00:00Z"}), encoding="utf8")
            now = time.time()
            os.utime(newer, (now + 10, now + 10))

            stale = symbol_sleeves.latest_stale_info(latest)

            self.assertTrue(stale["stale"])
            self.assertEqual(len(stale["newer_siblings"]), 1)

    def test_position_risk_keeps_executable_exit_pnl_separate_from_mark_pnl(self):
        cards = {
            "bullish_pullback_observation:SBUX": symbol_sleeves._new_card(
                "bullish_pullback_observation",
                "bullish_pullback_observation",
                "per_ticker_bullish_pullback",
                "SBUX",
            )
        }
        universe: dict[str, dict] = {}
        open_risk = {
            "summary": {"rows": 1},
            "actionable_positions": [
                {
                    "id": 104,
                    "ticker": "SBUX",
                    "action_bucket": "stored_non_executable_sell",
                    "pricing_state": "priced_display_only_last",
                    "current_pnl_pct": -15.0,
                    "mark_pnl_pct": -15.0,
                    "exit_execution_price": None,
                    "next_safe_action": "rerun_explicit_review",
                }
            ],
        }

        symbol_sleeves.enrich_with_position_risk(cards, universe, open_risk, {})

        card = cards["bullish_pullback_observation:SBUX"]
        self.assertIsNone(card["executable_exit_pnl"])
        self.assertEqual(card["paper_or_mark_pnl"], -15.0)
        self.assertEqual(card["open_position_state"]["first_position_id"], 104)
        self.assertIn("tracked_and_suggested_trade_audits", card["source_tiers"])


if __name__ == "__main__":
    unittest.main()
