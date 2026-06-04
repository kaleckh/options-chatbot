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

from scripts.analyze_current_policy_entry_filters import build_report  # noqa: E402


def _row(
    position_id: int,
    ticker: str,
    lane: str,
    entry_date: str,
    pnl_pct: float,
    *,
    fill_degradation_pct: float | None = None,
    quality_score: float | None = None,
) -> dict:
    return {
        "position_id": position_id,
        "ticker": ticker,
        "lane": lane,
        "entry_date": entry_date,
        "baseline_pnl_pct": pnl_pct,
        "entry_signals": {
            "fill_degradation_pct": fill_degradation_pct,
            "quality_score": quality_score,
        },
    }


class CurrentPolicyEntryFilterLabTests(unittest.TestCase):
    def test_short_term_fill_filter_can_be_research_candidate(self):
        stop_grid_report = {
            "report_id": "fixture_stop_grid",
            "generated_at_utc": "2026-06-02T00:00:00Z",
            "rows": [
                _row(1, "AAA", "short_term", "2026-05-01", -95.0, fill_degradation_pct=16.0, quality_score=70.0),
                _row(2, "BBB", "short_term", "2026-05-02", -70.0, fill_degradation_pct=18.0, quality_score=75.0),
                _row(3, "CCC", "short_term", "2026-05-03", -20.0, fill_degradation_pct=12.0, quality_score=80.0),
                _row(4, "GGG", "short_term", "2026-05-04", -5.0, fill_degradation_pct=19.0, quality_score=75.0),
                _row(5, "DDD", "swing", "2026-05-03", 120.0, fill_degradation_pct=18.0, quality_score=80.0),
                _row(6, "EEE", "swing", "2026-05-04", 80.0, fill_degradation_pct=5.0, quality_score=65.0),
                _row(7, "FFF", "bullish_momentum", "2026-05-04", 60.0, fill_degradation_pct=4.0, quality_score=55.0),
            ],
        }

        report = build_report(stop_grid_report)
        by_id = {item["filter_id"]: item for item in report["filters"]}
        candidate = by_id["short_term_fill_degradation_ge_15"]

        self.assertIn(candidate["status"], {"paper_research_candidate", "paper_research_candidate_recent_unproven"})
        self.assertEqual(candidate["avoided_deep_losses"], 2)
        self.assertEqual(candidate["avoided_near_total_losses"], 1)
        self.assertEqual(candidate["lost_winners"], 0)
        self.assertGreater(candidate["kept"]["avg_pnl_pct"], report["baseline"]["avg_pnl_pct"])

    def test_quality_filter_can_be_rejected_for_winner_damage(self):
        stop_grid_report = {
            "rows": [
                _row(1, "AAA", "short_term", "2026-04-01", -95.0, quality_score=55.0),
                _row(2, "BBB", "short_term", "2026-04-02", 150.0, quality_score=55.0),
                _row(3, "CCC", "short_term", "2026-04-03", 120.0, quality_score=55.0),
                _row(4, "DDD", "swing", "2026-04-04", 20.0, quality_score=80.0),
                _row(5, "EEE", "swing", "2026-04-05", 40.0, quality_score=80.0),
            ],
        }

        report = build_report(stop_grid_report)
        by_id = {item["filter_id"]: item for item in report["filters"]}

        self.assertEqual(by_id["quality_lt_60"]["status"], "winner_damage_too_high")


if __name__ == "__main__":
    unittest.main()
