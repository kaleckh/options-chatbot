import unittest

from scripts.imported_intraday_robustness import build_intraday_robustness_report


def _trade(day: int, pnl: float) -> dict:
    return {
        "date": f"2026-05-{day:02d}",
        "ticker": "SPY",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "pnl_pct": pnl,
        "priced": True,
    }


class ImportedIntradayRobustnessTests(unittest.TestCase):
    def test_rolling_oos_counts_unpriced_candidates_in_test_windows(self):
        result = {
            "truth_source": "historical_imported",
            "imported_data_scope": "trusted",
            "candidate_trade_count": 4,
            "priced_trade_count": 3,
            "unpriced_trade_count": 1,
            "trades": [
                _trade(1, 4.0),
                _trade(2, 5.0),
                _trade(3, 6.0),
            ],
            "unpriced_trades": [
                {
                    "date": "2026-05-04",
                    "ticker": "SPY",
                    "unpriced_reason": "missing_exit_quote",
                }
            ],
        }

        report = build_intraday_robustness_report(
            result,
            train_days=2,
            test_days=2,
            min_exact_test_trades=1,
        )

        self.assertEqual(report["rolling_oos"]["window_count"], 1)
        window = report["rolling_oos"]["windows"][0]
        self.assertEqual(window["test"]["trades"], 1)
        self.assertEqual(window["unpriced_test_candidate_count"], 1)
        self.assertIn("unpriced_test_candidates_present", window["gate_blockers"])
        self.assertIn("rolling_oos_not_passed", report["blockers"])


if __name__ == "__main__":
    unittest.main()
