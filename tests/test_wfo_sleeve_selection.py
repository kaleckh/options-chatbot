from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import wfo_optimizer as wfo


def _candidate(ticker: str, score: float = 90.0) -> dict:
    return {
        "ticker": ticker,
        "sector": "Unknown",
        "direction_score": score,
        "quality_score": score,
        "ev": score,
    }


class WfoSleeveSelectionTests(unittest.TestCase):
    def test_unknown_sector_ticker_bucket_does_not_cap_all_equities_together(self):
        candidates = [_candidate("AAA"), _candidate("BBB"), _candidate("CCC"), _candidate("DDD")]

        shared, shared_diag = wfo._pick_top_n_daily_configured(
            candidates,
            4,
            max_per_allocation_group=2,
            unknown_sector_policy="shared",
        )
        bucketed, bucketed_diag = wfo._pick_top_n_daily_configured(
            candidates,
            4,
            max_per_allocation_group=2,
            unknown_sector_policy="ticker_bucket",
        )

        self.assertEqual(len(shared), 2)
        self.assertEqual(shared_diag["reject_reasons"].get("allocation_group_cap"), 2)
        self.assertEqual(len(bucketed), 4)
        self.assertEqual(bucketed_diag["unused_slots"], 0)

    def test_capacity_tiers_are_ranked_and_preserve_sleeve_metadata(self):
        tiers = wfo._capacity_tiers_for_playbook(
            {
                "id": "base",
                "capacity_tiers": [
                    {"tier_id": "second", "tier_rank": 2, "sleeve_id": "alpha"},
                    {"tier_id": "first", "tier_rank": 1, "sleeve_id": "core"},
                ],
            }
        )

        self.assertEqual([tier["tier_id"] for tier in tiers], ["first", "second"])
        self.assertEqual(tiers[0]["sleeve_id"], "core")
        self.assertEqual(tiers[1]["sleeve_id"], "alpha")

    def test_configured_daily_picker_prefers_earlier_capacity_tier(self):
        early = _candidate("AAA", score=50.0)
        early.update({"tier_id": "strict", "tier_rank": 1})
        later = _candidate("BBB", score=99.0)
        later.update({"tier_id": "relaxed", "tier_rank": 3})

        picked, diag = wfo._pick_top_n_daily_configured(
            [later, early],
            1,
            max_per_allocation_group=2,
            unknown_sector_policy="ticker_bucket",
        )

        self.assertEqual([item["ticker"] for item in picked], ["AAA"])
        self.assertEqual(diag["rejected_candidates"][0]["selection_reject_reason"], "capacity_filled")

    def test_candidate_match_respects_excluded_tickers(self):
        self.assertFalse(
            wfo._candidate_matches_replay_playbook(
                {"ticker": "SLB"},
                {"allowed_tickers": ["SLB", "XOM"], "excluded_tickers": ["SLB"]},
            )
        )
        self.assertTrue(
            wfo._candidate_matches_replay_playbook(
                {"ticker": "XOM"},
                {"allowed_tickers": ["SLB", "XOM"], "excluded_tickers": ["SLB"]},
            )
        )

    def test_tradability_score_penalizes_short_leg_without_prior_survival(self):
        long_quote = SimpleNamespace(
            contract_symbol="AAA260220C00100000",
            bid=4.9,
            ask=5.1,
        )
        short_quote = SimpleNamespace(
            contract_symbol="AAA260220C00105000",
            bid=0.04,
            ask=0.20,
        )

        def _metrics(store, quote, **kwargs):
            if quote.contract_symbol == short_quote.contract_symbol:
                return {"quote_date_count": 0, "avg_bid_ask_pct": 80.0}
            return {"quote_date_count": 3, "avg_bid_ask_pct": 5.0}

        with patch.object(wfo, "_contract_prior_quote_continuity_metrics", side_effect=_metrics):
            score = wfo._spread_tradability_score(
                store=object(),
                long_quote=long_quote,
                short_quote=short_quote,
                entry_date=date(2026, 1, 15),
                snapshot_kind="intraday",
                source_labels=["thetadata_opra_nbbo_1m"],
                trusted_only=True,
                lookback_calendar_days=20,
                min_short_leg_prior_quote_days=2,
            )

        self.assertLess(score["tradability_score"], 70)
        self.assertIn("short_leg_survival_risk", score["tradability_reasons"])
        self.assertIn("low_entry_short_bid", score["tradability_reasons"])


if __name__ == "__main__":
    unittest.main()
