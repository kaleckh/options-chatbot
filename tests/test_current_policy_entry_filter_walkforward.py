from __future__ import annotations

import sys
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from scripts.validate_current_policy_entry_filter_walkforward import build_report  # noqa: E402


def _row(
    position_id: int,
    ticker: str,
    lane: str,
    entry_date: str,
    pnl_pct: float,
    *,
    fill_degradation_pct: float | None = None,
) -> dict:
    return {
        "position_id": position_id,
        "ticker": ticker,
        "lane": lane,
        "entry_date": entry_date,
        "baseline_pnl_pct": pnl_pct,
        "entry_signals": {"fill_degradation_pct": fill_degradation_pct},
        "stop_results": {"80": {"pnl_pct": pnl_pct}},
    }


class CurrentPolicyEntryFilterWalkforwardTests(unittest.TestCase):
    def test_frozen_rule_can_be_holdout_positive_but_not_promoted_when_train_is_mixed(self):
        rows = [
            _row(1, "AAA", "short_term", "2026-04-01", -80.0, fill_degradation_pct=16.0),
            _row(2, "BBB", "short_term", "2026-04-02", -20.0, fill_degradation_pct=17.0),
            _row(3, "CCC", "short_term", "2026-04-03", 30.0, fill_degradation_pct=18.0),
            _row(4, "DDD", "short_term", "2026-04-04", 50.0, fill_degradation_pct=5.0),
            _row(5, "EEE", "short_term", "2026-04-05", 60.0, fill_degradation_pct=5.0),
            _row(6, "FFF", "short_term", "2026-04-06", 70.0, fill_degradation_pct=5.0),
            _row(7, "GGG", "short_term", "2026-04-07", 80.0, fill_degradation_pct=5.0),
            _row(8, "HHH", "short_term", "2026-04-08", 90.0, fill_degradation_pct=5.0),
            _row(9, "III", "short_term", "2026-04-09", 20.0, fill_degradation_pct=5.0),
            _row(10, "JJJ", "short_term", "2026-04-10", 10.0, fill_degradation_pct=5.0),
            _row(11, "AAA", "short_term", "2026-05-01", -90.0, fill_degradation_pct=16.0),
            _row(12, "BBB", "short_term", "2026-05-02", -70.0, fill_degradation_pct=17.0),
            _row(13, "CCC", "short_term", "2026-05-03", 40.0, fill_degradation_pct=18.0),
            _row(14, "DDD", "short_term", "2026-05-04", 10.0, fill_degradation_pct=5.0),
            _row(15, "EEE", "short_term", "2026-05-05", 20.0, fill_degradation_pct=5.0),
            _row(16, "FFF", "short_term", "2026-05-06", 30.0, fill_degradation_pct=5.0),
            _row(17, "GGG", "short_term", "2026-05-07", 40.0, fill_degradation_pct=5.0),
            _row(18, "HHH", "short_term", "2026-05-08", -10.0, fill_degradation_pct=5.0),
            _row(19, "III", "short_term", "2026-05-09", -20.0, fill_degradation_pct=5.0),
            _row(20, "JJJ", "short_term", "2026-05-10", 50.0, fill_degradation_pct=5.0),
        ]

        report = build_report({"rows": rows})

        self.assertEqual(report["decision_summary"]["status"], "mixed_walkforward_watch_not_promoted")
        self.assertFalse(report["decision_summary"]["live_policy_change"])
        self.assertEqual(report["portfolio"]["frozen_champion"]["status"], "historical_pass_candidate")
        self.assertEqual(report["chronological_holdout"]["holdout"]["status"], "historical_pass_candidate")
        self.assertEqual(report["chronological_holdout"]["train"]["status"], "winner_damage_too_high")

    def test_all_lane_fill_filter_is_rejected_when_other_lanes_lose_winners(self):
        rows = [
            _row(1, "AAA", "short_term", "2026-04-01", -80.0, fill_degradation_pct=16.0),
            _row(2, "BBB", "short_term", "2026-04-02", -70.0, fill_degradation_pct=17.0),
            _row(3, "CCC", "short_term", "2026-04-03", 20.0, fill_degradation_pct=18.0),
            _row(4, "DDD", "short_term", "2026-04-04", 30.0, fill_degradation_pct=5.0),
            _row(5, "EEE", "short_term", "2026-04-05", 40.0, fill_degradation_pct=5.0),
            _row(6, "FFF", "swing", "2026-04-01", 90.0, fill_degradation_pct=16.0),
            _row(7, "GGG", "swing", "2026-04-02", 100.0, fill_degradation_pct=17.0),
            _row(8, "HHH", "swing", "2026-04-03", 110.0, fill_degradation_pct=18.0),
            _row(9, "III", "swing", "2026-04-04", 20.0, fill_degradation_pct=5.0),
            _row(10, "JJJ", "swing", "2026-04-05", 25.0, fill_degradation_pct=5.0),
            _row(11, "KKK", "bullish_momentum", "2026-05-01", 30.0, fill_degradation_pct=5.0),
            _row(12, "LLL", "bullish_pullback_observation", "2026-05-01", 35.0, fill_degradation_pct=5.0),
        ]

        report = build_report({"rows": rows})
        broad = report["portfolio"]["broad_all_lanes_fill_degradation_ge_15"]
        by_lane = {item["lane"]: item for item in report["lane_matrix"]}

        self.assertEqual(broad["status"], "winner_damage_too_high")
        self.assertEqual(by_lane["short_term"]["status"], "historical_pass_candidate")
        self.assertIn(by_lane["swing"]["status"], {"no_deep_loss_reduction", "blocked_set_not_net_negative"})
        self.assertEqual(by_lane["bullish_pullback_observation"]["status"], "sample_too_small")


if __name__ == "__main__":
    unittest.main()
