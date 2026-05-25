from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from options_profitability_forensics import build_options_profitability_forensics  # noqa: E402


class OptionsProfitabilityForensicsTests(unittest.TestCase):
    def test_all_winning_exact_contract_sample_has_no_profit_factor_blocker(self):
        report = build_options_profitability_forensics(
            {
                "truth_source": "historical_imported_daily",
                "trades": [
                    {
                        "ticker": "SPY",
                        "type": "call",
                        "contract_resolution": "exact_contract",
                        "directional_correct": True,
                        "pnl_pct": 0.4,
                    }
                ],
            },
            min_trades=1,
        )

        self.assertEqual(report["overall"]["profit_factor"], 999.0)
        self.assertEqual(report["exactness_view"]["exact_only"]["profit_factor"], 999.0)
        self.assertFalse(any("profit factor is below 1.0" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
