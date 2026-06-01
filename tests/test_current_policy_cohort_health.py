from __future__ import annotations

import unittest

from scripts import build_current_policy_cohort_health as cohort


def _row(trade_id: int, ticker: str, lane: str, entry_date: str, pnl_pct: float, decision: str = "would_take_today"):
    return {
        "trade_id": trade_id,
        "ticker": ticker,
        "lane": lane,
        "entry_date": entry_date,
        "closed_at": entry_date,
        "pnl_pct": pnl_pct,
        "current_policy_decision": decision,
        "evidence_group": "historical_paper",
        "has_realized_pnl": True,
        "guardrail_hits": [],
    }


class CurrentPolicyCohortHealthTests(unittest.TestCase):
    def test_april_showcase_can_coexist_with_recent_paper_only_break(self):
        rows = [
            _row(1, "AMD", "short_term", "2026-04-13", 110.0),
            _row(2, "AMZN", "short_term", "2026-04-14", 70.0),
            _row(3, "QQQ", "swing", "2026-04-15", 82.0),
            _row(4, "SPY", "swing", "2026-04-16", 65.0),
            _row(5, "AAPL", "bullish_momentum", "2026-04-17", 95.0),
            _row(6, "TSLA", "short_term", "2026-05-13", 20.0),
            _row(7, "QQQ", "swing", "2026-05-14", 10.0),
            _row(8, "WMT", "short_term", "2026-05-20", -99.0),
            _row(9, "GOOGL", "bullish_pullback_observation", "2026-05-21", -83.0),
            _row(10, "UNH", "bullish_pullback_observation", "2026-05-22", -63.0),
            _row(11, "XLK", "short_term", "2026-05-20", -50.0, "blocked_by_current_policy"),
        ]

        report = cohort.build_report({"generated_at_utc": "2026-06-01T00:00:00Z", "rows": rows})
        summary = report["summary"]

        self.assertEqual(summary["showcase_month"], "2026-04")
        self.assertEqual(summary["showcase_month_summary"]["health_status"], "healthy")
        self.assertEqual(summary["recent_month"], "2026-05")
        self.assertEqual(summary["recent_month_summary"]["health_status"], "paper_only_recent_break")
        self.assertEqual(summary["recent_week"], "2026-W21")
        self.assertEqual(summary["recent_week_summary"]["health_status"], "paper_only_recent_break")
        self.assertEqual(summary["overall_status"], "paper_only_recent_week_break")
        self.assertEqual(summary["current_policy_rows"], 10)
        self.assertTrue(
            any(action["scope"] == "month:2026-05" and action["priority"] == "P0" for action in report["recommended_actions"])
        )

    def test_thin_recent_severe_loss_is_still_paper_only(self):
        report = cohort.build_report(
            {
                "generated_at_utc": "2026-06-01T00:00:00Z",
                "rows": [_row(1, "DIS", "short_term", "2026-05-20", -99.5)],
            }
        )

        self.assertEqual(report["summary"]["recent_month_summary"]["health_status"], "paper_only_thin_severe")
        self.assertEqual(report["summary"]["recent_week_summary"]["health_status"], "paper_only_thin_severe")
        self.assertEqual(report["summary"]["overall_status"], "paper_only_recent_week_break")

    def test_non_current_policy_rows_do_not_distort_cohort_health(self):
        report = cohort.build_report(
            {
                "generated_at_utc": "2026-06-01T00:00:00Z",
                "rows": [
                    _row(1, "AMD", "short_term", "2026-04-13", 80.0),
                    _row(2, "XLK", "short_term", "2026-04-13", -95.0, "blocked_by_current_policy"),
                ],
            }
        )

        self.assertEqual(report["summary"]["current_policy_rows"], 1)
        self.assertEqual(report["summary"]["overall"]["avg_pnl_pct"], 80.0)


if __name__ == "__main__":
    unittest.main()
