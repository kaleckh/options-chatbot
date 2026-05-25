from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import supervised_scan as ss  # noqa: E402
from ai_commodity_universe import (  # noqa: E402
    CORE_OPTIONS,
    CONDITIONAL_OPTIONS,
    AI_COMMODITY_UNIVERSE_PATH,
    ai_commodity_conditional_options_tickers,
    ai_commodity_core_options_tickers,
    ai_commodity_data_ready_tickers,
    ai_commodity_index_like_tickers,
    ai_commodity_scan_tickers,
    ai_commodity_symbols_by_bucket,
    ai_commodity_tickers_by_options_bucket,
    load_ai_commodity_universe,
    validate_ai_commodity_universe,
)


class AICommodityUniverseTests(unittest.TestCase):
    def test_manifest_validates_and_drives_scan_tickers(self):
        payload = load_ai_commodity_universe()

        self.assertEqual(validate_ai_commodity_universe(payload), [])
        scan_tickers = ai_commodity_scan_tickers()

        self.assertEqual(scan_tickers, list(ss.AI_COMMODITY_INFRA_TICKERS))
        self.assertIn("FCX", scan_tickers)
        self.assertIn("VRT", scan_tickers)
        self.assertIn("GEV", scan_tickers)
        self.assertIn("MP", scan_tickers)
        self.assertNotIn("CPER", scan_tickers)
        self.assertNotIn("LIT", scan_tickers)
        self.assertEqual(len(scan_tickers), len(set(scan_tickers)))

    def test_manifest_keeps_watch_etfs_index_like_without_scan_permission(self):
        index_like = ai_commodity_index_like_tickers()
        buckets = ai_commodity_symbols_by_bucket()

        self.assertIn("SLV", buckets[CORE_OPTIONS])
        self.assertIn("GRID", index_like)
        self.assertIn("LIT", index_like)
        self.assertNotIn("GRID", ai_commodity_scan_tickers())
        self.assertTrue(AI_COMMODITY_UNIVERSE_PATH.exists())

    def test_core_and_conditional_tickers_are_separate_scan_subsets(self):
        core = ai_commodity_core_options_tickers()
        conditional = ai_commodity_conditional_options_tickers()
        scan = ai_commodity_scan_tickers()

        self.assertEqual(core, ai_commodity_tickers_by_options_bucket(CORE_OPTIONS, scan_eligible_only=True))
        self.assertEqual(
            conditional,
            ai_commodity_tickers_by_options_bucket(CONDITIONAL_OPTIONS, scan_eligible_only=True),
        )
        self.assertIn("FCX", core)
        self.assertIn("CEG", core)
        self.assertIn("ALB", conditional)
        self.assertIn("URA", conditional)
        self.assertEqual(set(core).intersection(conditional), set())
        self.assertEqual(core + conditional, scan)

    def test_data_ready_tickers_preserve_scan_order(self):
        self.assertEqual(
            ai_commodity_data_ready_tickers({"VRT", "FCX", "SPY"}),
            ["FCX", "VRT"],
        )


if __name__ == "__main__":
    unittest.main()
