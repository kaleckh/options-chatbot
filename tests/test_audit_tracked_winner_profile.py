from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.audit_tracked_winner_profile import (
    build_tracked_winner_profile,
    find_duplicate_tracked_winner_profile,
)
from workspace_tempdir import WorkspaceTempDir


def _position(
    ticker: str,
    pnl: float,
    *,
    quality: float = 62.0,
    asset_class: str = "index",
    promotion_class: str = "comparable_exact_contract",
) -> dict:
    return {
        "id": ticker,
        "status": "open",
        "ticker": ticker,
        "last_pnl_pct": pnl,
        "source_pick_snapshot": {
            "ticker": ticker,
            "direction": "call",
            "strategy_type": "vertical_spread",
            "asset_class": asset_class,
            "market_regime": "bullish",
            "quality_score": quality,
            "direction_score": 80.0,
            "net_debit": 3.0,
            "spread_width": 10.0,
            "promotion_class": promotion_class,
            "selection_source": "logged_comparable_exact_contract",
        },
    }


class AuditTrackedWinnerProfileTests(unittest.TestCase):
    def test_build_profile_surfaces_winner_traits_and_candidate_lane(self):
        profile = build_tracked_winner_profile(
            [
                _position("SPY", 50.0, quality=95.0),
                _position("XLK", 20.0, quality=63.0),
                _position("IWM", -10.0, quality=60.0),
            ]
        )

        self.assertEqual(profile["overall"]["count"], 3)
        self.assertEqual(profile["winners"]["winner_count"], 2)
        self.assertEqual(profile["winner_count_by_contract_proof_class"]["comparable_exact_contract"], 2)
        self.assertEqual(profile["candidate_lane"]["status"], "candidate")
        self.assertEqual(profile["candidate_lane"]["rules"]["suggested_starting_filter"]["max_debit_pct_of_width"], 40.0)
        self.assertTrue(profile["profile_fingerprint"])

    def test_find_duplicate_tracked_winner_profile_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="tracked-winner-profile-dupe")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        profile_path = root / "tracked_winner_profile_test.json"
        profile_path.write_text(json.dumps({"profile_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_tracked_winner_profile(root, "abc123"), profile_path)


if __name__ == "__main__":
    unittest.main()
