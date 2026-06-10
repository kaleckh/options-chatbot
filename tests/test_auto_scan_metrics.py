from __future__ import annotations

import unittest

from auto_scan_metrics import build_perf_snapshot_from_predictions


class AutoScanMetricsTests(unittest.TestCase):
    def test_headline_win_rate_counts_full_hits_not_directional_accuracy(self):
        snapshot = build_perf_snapshot_from_predictions(
            [
                {
                    "graded_date": "2026-06-09T16:00:00Z",
                    "type": "daily_scan",
                    "outcome": "directional",
                    "direction_score": 90,
                    "pick_status": "new",
                },
                {
                    "graded_date": "2026-06-09T16:05:00Z",
                    "type": "daily_scan",
                    "outcome": "hit",
                    "direction_score": 60,
                    "pick_status": "new",
                },
            ],
            "2026-06-09",
        )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["win_rate_pct"], 50.0)
        self.assertEqual(snapshot["directional_accuracy_pct"], 100.0)
        self.assertEqual(snapshot["all_time_win_rate_pct"], 50.0)
        self.assertEqual(snapshot["all_time_directional_accuracy_pct"], 100.0)
        self.assertEqual(snapshot["new_pick_win_rate_pct"], 50.0)
        self.assertEqual(snapshot["new_pick_directional_accuracy_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
