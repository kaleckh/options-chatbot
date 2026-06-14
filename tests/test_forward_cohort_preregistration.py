from __future__ import annotations

import unittest

from scripts.forward_cohort_preregistration import (
    forward_cohort_is_active,
    forward_cohort_playbook_is_parked,
    parked_regular_lane_ids,
    scan_enabled_playbook_ids,
)
from scripts.generate_forward_cohort_preregistration import (
    LANE_BULLISH_CARRIER,
    LANE_VOLATILITY,
    build_contract,
)
from supervised_scan import BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS


class ForwardCohortPreregistrationTests(unittest.TestCase):
    def test_contract_freezes_the_two_phase2_lanes(self) -> None:
        contract = build_contract()

        self.assertTrue(forward_cohort_is_active(contract))
        self.assertTrue(contract["runtime_use"])
        self.assertEqual(contract["cohort"]["freeze_date"], "2026-06-14")
        self.assertEqual(contract["cohort"]["eval_date"], "2026-07-28")
        self.assertEqual(contract["cohort"]["fresh_rows_collected"][LANE_VOLATILITY], 0)
        self.assertEqual(contract["cohort"]["fresh_rows_collected"][LANE_BULLISH_CARRIER], 0)
        self.assertEqual([lane["lane_id"] for lane in contract["lanes"]], [LANE_VOLATILITY, LANE_BULLISH_CARRIER])
        self.assertEqual(
            next(lane for lane in contract["lanes"] if lane["lane_id"] == LANE_BULLISH_CARRIER)["symbols"],
            list(BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS),
        )
        self.assertEqual(contract["promotion_criteria"]["existing_promotion_bars"], "unchanged_never_lowered")
        self.assertIn(
            "bootstrap_pf_lower_bound_5pct_above_1_0_on_forward_cohort",
            contract["promotion_criteria"]["additional_forward_bars"],
        )
        self.assertIn(
            "fewer_than_10_fresh_forward_exact_realized_rows_by_eval_date_is_operational_kill_fix_funnel_and_refreeze",
            contract["kill_criteria"]["per_frozen_lane"],
        )

    def test_helpers_select_only_cohort_plus_requested_overrides_when_active(self) -> None:
        contract = build_contract()
        available = [
            "short_term",
            LANE_VOLATILITY,
            LANE_BULLISH_CARRIER,
            "ai_commodity_infra_observation",
        ]

        self.assertIn("short_term", parked_regular_lane_ids(contract))
        self.assertEqual(
            scan_enabled_playbook_ids(available, contract=contract),
            [LANE_VOLATILITY, LANE_BULLISH_CARRIER],
        )
        self.assertEqual(
            scan_enabled_playbook_ids(available, contract=contract, include_commodity=True),
            [LANE_VOLATILITY, LANE_BULLISH_CARRIER, "ai_commodity_infra_observation"],
        )
        self.assertEqual(
            scan_enabled_playbook_ids(available, contract=contract, include_parked=True),
            ["short_term", LANE_VOLATILITY, LANE_BULLISH_CARRIER],
        )
        self.assertTrue(forward_cohort_playbook_is_parked("short_term", contract))
        self.assertFalse(forward_cohort_playbook_is_parked(LANE_VOLATILITY, contract))
        self.assertFalse(forward_cohort_playbook_is_parked("ai_commodity_infra_observation", contract))


if __name__ == "__main__":
    unittest.main()
