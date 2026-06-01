from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_regular_options_all_planned_sleeves as all_sleeves
from workspace_tempdir import WorkspaceTempDir


class RegularOptionsAllPlannedSleevesTests(unittest.TestCase):
    def test_default_plan_contains_planned_non_overlapping_families(self):
        lane_ids = {str(spec["lane_id"]) for spec in all_sleeves.IMPLEMENTED_PLANNED_VARIANTS}

        self.assertIn("etf_index_pullback_control", lane_ids)
        self.assertIn("high_beta_momentum_volatility", lane_ids)
        self.assertIn("defensive_refill_income", lane_ids)
        self.assertIn("reit_rate_sensitive", lane_ids)
        self.assertIn("industrial_scout", lane_ids)
        self.assertIn("bearish_put_debit_spread", lane_ids)
        self.assertIn("range_breakout_observation", lane_ids)
        self.assertIn("volatility_expansion_observation", lane_ids)
        self.assertIn("relative_strength_pullback", lane_ids)
        self.assertIn("xle_energy_inflation", lane_ids)
        self.assertIn("xlf_financials", lane_ids)
        self.assertIn("kre_regional_bank_observation", lane_ids)
        self.assertIn("smh_semiconductor", lane_ids)
        self.assertIn("tlt_duration_shock", lane_ids)
        self.assertIn("sector_rotation_confirmation", lane_ids)

    def test_repair_plan_contains_current_sleeve_and_new_signal_variants(self):
        variant_ids = {str(spec["variant_id"]) for spec in all_sleeves.IMPLEMENTED_PLANNED_VARIANTS}

        self.assertIn("tracked_winner_cheap_debit_continuity_v1", variant_ids)
        self.assertIn("tracked_winner_chain_native_no_spy_time65_all_sleeves", variant_ids)
        self.assertIn("volatility_expansion_observation_chain_native_call_fast35_all_sleeves", variant_ids)
        self.assertIn("relative_strength_pullback_ex_clean_universe_v1", variant_ids)

    def test_worth_status_rejects_unprofitable_shape(self):
        status = all_sleeves.worth_status(
            {
                "exact_trade_count": 40,
                "profit_factor": 0.9,
                "avg_pnl_pct": -2.0,
                "quote_coverage_pct": 100.0,
                "unpriced_trade_count": 0,
            },
            {"rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.5},
            {"strict_new_trade_count": 40},
        )

        self.assertEqual(status, "not_worth_current_shape")

    def test_worth_status_marks_small_profitable_samples_as_thin(self):
        status = all_sleeves.worth_status(
            {
                "exact_trade_count": 8,
                "profit_factor": 2.0,
                "avg_pnl_pct": 10.0,
                "quote_coverage_pct": 100.0,
                "unpriced_trade_count": 0,
            },
            {"rolling_status": "passed", "stress_5pct_per_side_profit_factor": 2.0},
            {"strict_new_trade_count": 8},
        )

        self.assertEqual(status, "thin_sample")

    def test_worth_status_surfaces_gap_closing_candidate(self):
        status = all_sleeves.worth_status(
            {
                "exact_trade_count": 100,
                "profit_factor": 1.8,
                "avg_pnl_pct": 12.0,
                "quote_coverage_pct": 100.0,
                "unpriced_trade_count": 0,
            },
            {"rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.5},
            {"strict_new_trade_count": 43},
        )

        self.assertEqual(status, "candidate_to_close_200_gap")

    def test_worth_status_blocks_sub_100_portfolio_candidate_even_if_gap_closing(self):
        status = all_sleeves.worth_status(
            {
                "exact_trade_count": 72,
                "profit_factor": 1.8,
                "avg_pnl_pct": 12.0,
                "quote_coverage_pct": 100.0,
                "unpriced_trade_count": 0,
            },
            {"rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.5},
            {"strict_new_trade_count": 43},
        )

        self.assertEqual(status, "below_portfolio_candidate_exact_count")

    def test_worth_status_rejects_gap_candidate_after_bad_zero_bid_replay(self):
        status = all_sleeves.worth_status(
            {
                "exact_trade_count": 100,
                "profit_factor": 1.9,
                "avg_pnl_pct": 12.0,
                "quote_coverage_pct": 70.0,
                "unpriced_trade_count": 30,
            },
            {"rolling_status": "passed", "stress_5pct_per_side_profit_factor": 1.5},
            {"strict_new_trade_count": 43},
            {
                "status": "completed",
                "modes": {
                    "conservative": {
                        "unpriced_count": 0,
                        "zero_bid_exit_rate_pct": 10.0,
                        "combined_with_existing_metrics": {
                            "profit_factor": 0.67,
                            "avg_pnl_pct": -12.68,
                        },
                    }
                },
            },
        )

        self.assertEqual(status, "not_worth_after_zero_bid_replay")

    def test_side_aware_probe_is_required_for_profitable_gap_closing_missing_exits(self):
        run = {
            "unpriced_trades": [
                {
                    "unpriced_reason": "missing_exit_quote_for_leg",
                    "missing_short_contract_symbol": "AAA260117C00110000",
                }
            ]
        }

        should_run, reason = all_sleeves._should_run_side_aware_zero_bid(
            run,
            {
                "profit_factor": 1.8,
                "avg_pnl_pct": 12.0,
            },
            {"gap_after_candidate": 0},
        )

        self.assertTrue(should_run)
        self.assertEqual(reason, "gap_closing_profitable_candidate_has_missing_exits")

    def test_intraday_readiness_payload_uses_current_trusted_store(self):
        with WorkspaceTempDir(prefix="all-planned-readiness") as tmp:
            db_path = Path(tmp) / "options_history.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE import_batches (
                        id INTEGER PRIMARY KEY,
                        source_label TEXT NOT NULL,
                        dataset_kind TEXT NOT NULL,
                        data_trust TEXT NOT NULL,
                        input_path TEXT NOT NULL,
                        file_hash TEXT NOT NULL,
                        imported_at_utc TEXT NOT NULL,
                        total_rows INTEGER NOT NULL,
                        imported_rows INTEGER NOT NULL,
                        duplicate_rows INTEGER NOT NULL,
                        rejected_rows INTEGER NOT NULL,
                        warnings_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE option_quote_snapshots (
                        id INTEGER PRIMARY KEY,
                        as_of_utc TEXT NOT NULL,
                        quote_date_et TEXT NOT NULL,
                        quote_minute_et INTEGER NOT NULL,
                        snapshot_kind TEXT NOT NULL,
                        underlying TEXT NOT NULL,
                        contract_symbol TEXT NOT NULL,
                        expiry TEXT NOT NULL,
                        option_type TEXT NOT NULL,
                        strike REAL NOT NULL,
                        bid REAL,
                        ask REAL,
                        last REAL,
                        iv REAL,
                        underlying_price REAL,
                        volume INTEGER,
                        open_interest INTEGER,
                        source_batch_id INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX idx_option_quotes_underlying_date ON option_quote_snapshots (underlying, snapshot_kind, quote_date_et, option_type, quote_minute_et)"
                )
                conn.execute(
                    """
                    INSERT INTO import_batches VALUES (
                        1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted',
                        'fixture.csv', 'hash', '2026-05-31T00:00:00Z', 3, 3, 0, 0, '[]'
                    )
                    """
                )
                for day in range(1, 4):
                    conn.execute(
                        """
                        INSERT INTO option_quote_snapshots (
                            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind,
                            underlying, contract_symbol, expiry, option_type, strike,
                            bid, ask, source_batch_id
                        ) VALUES (?, ?, 600, 'intraday', 'IWM', ?, '2026-07-17', 'call', 200, 1, 1.1, 1)
                        """,
                        (f"2026-01-0{day}T15:00:00Z", f"2026-01-0{day}", f"IWM260717C00{day}00000"),
                    )

            payload = all_sleeves._trusted_intraday_readiness_payload(
                ["IWM", "SMH"],
                db_path=db_path,
                min_quote_dates=3,
            )

        self.assertIn("IWM", payload["available_underlyings"])
        self.assertNotIn("SMH", payload["available_underlyings"])
        self.assertEqual(payload["required_underlying_health"]["IWM"]["quote_date_count"], 3)

    def test_same_lane_id_lane_lab_specs_remain_visible_until_evidence_exists(self):
        implemented_lane_ids = {str(spec["lane_id"]) for spec in all_sleeves.IMPLEMENTED_PLANNED_VARIANTS}
        with patch.object(
            all_sleeves,
            "_trusted_intraday_readiness_payload",
            return_value={
                "status": "ready_for_exact_replay",
                "available_underlyings": [],
                "shared_required_quote_dates": {"count": 0},
            },
        ):
            rows = all_sleeves.blocked_lane_lab_rows(implemented_lane_ids)

        by_lane_id = {str(row["lane_id"]): row for row in rows}
        relative_strength = by_lane_id["relative_strength_pullback"]
        bearish_put = by_lane_id["bearish_put_debit_spread"]

        self.assertEqual(relative_strength["status"], "pending_forward_paper_log")
        self.assertEqual(bearish_put["status"], "pending_forward_paper_log")
        self.assertIn("relative_strength_pullback_ex_clean_universe_v1", relative_strength["implemented_variant_ids"])
        self.assertIn("regular_bearish_put_primary_chain_native_timeexit_all_sleeves", bearish_put["implemented_variant_ids"])
        self.assertIn("same_lane_id_replay_tested", relative_strength["implementation_note"])

    def test_iwm_small_cap_risk_has_risk_on_and_risk_off_replay_variants(self):
        specs = {
            str(spec["variant_id"]): spec
            for spec in all_sleeves.WFO_VARIANTS
            if str(spec["lane_id"]) == "iwm_small_cap_risk"
        }

        self.assertEqual(
            sorted(specs),
            [
                "iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves",
                "iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves",
            ],
        )
        call = specs["iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves"]
        put = specs["iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves"]

        self.assertEqual(call["base_playbook"], "bullish_pullback_observation")
        self.assertEqual(put["base_playbook"], "bearish_index_put_observation")
        for direction, spec in (("call", call), ("put", put)):
            overrides = spec["overrides"]
            self.assertEqual(spec["n_picks"], 1)
            self.assertEqual(overrides["allowed_tickers"], ["IWM"])
            self.assertEqual(overrides["historical_required_underlyings"], ["IWM"])
            self.assertEqual(overrides["allowed_directions"], [direction])
            self.assertTrue(overrides["chain_native_spread_selection"])
            self.assertEqual(overrides["chain_native_min_dte"], 21)
            self.assertEqual(overrides["chain_native_max_dte"], 35)
            self.assertEqual(overrides["max_debit_pct_of_width"], 45.0)

    def test_iwm_small_cap_risk_exposes_existing_per_ticker_sleeve(self):
        specs = {
            str(spec["variant_id"]): spec
            for spec in all_sleeves.SLEEVE_VARIANTS
            if str(spec["lane_id"]) == "iwm_small_cap_risk"
        }

        self.assertEqual(sorted(specs), ["sleeve_ticker_iwm"])
        self.assertTrue(specs["sleeve_ticker_iwm"]["include_tickers"])

    def test_regular_sector_etf_variants_exclude_gld_commodity_lane(self):
        sector_specs = [
            spec
            for spec in all_sleeves.WFO_VARIANTS
            if str(spec["lane_id"])
            in {
                "xle_energy_inflation",
                "xlf_financials",
                "kre_regional_bank_observation",
                "smh_semiconductor",
                "tlt_duration_shock",
                "sector_rotation_confirmation",
            }
        ]
        variant_ids = {str(spec["variant_id"]) for spec in sector_specs}

        self.assertIn("xle_energy_inflation_call_chain_native_timeexit_all_sleeves", variant_ids)
        self.assertIn("xlf_financials_call_chain_native_timeexit_all_sleeves", variant_ids)
        self.assertIn("kre_regional_bank_call_chain_native_timeexit_all_sleeves", variant_ids)
        self.assertIn("smh_semiconductor_call_chain_native_timeexit_all_sleeves", variant_ids)
        self.assertIn("tlt_duration_shock_call_chain_native_timeexit_all_sleeves", variant_ids)
        self.assertIn("sector_rotation_regular_etf_call_stack_v1", variant_ids)
        self.assertNotIn("gld_macro_breakout", {str(spec["lane_id"]) for spec in sector_specs})

        for spec in sector_specs:
            overrides = spec["overrides"]
            self.assertNotIn("GLD", overrides.get("allowed_tickers") or [])
            self.assertNotIn("GLD", overrides.get("historical_required_underlyings") or [])
            self.assertTrue(overrides["chain_native_spread_selection"])

    def test_liquidity_first_contract_hygiene_variant_uses_entry_time_causal_knobs(self):
        spec = next(
            item
            for item in all_sleeves.WFO_VARIANTS
            if str(item["variant_id"]) == "tracked_winner_liquidity_first_contract_hygiene_v1"
        )
        overrides = spec["overrides"]

        self.assertEqual(spec["lane_id"], "liquidity_first_spread")
        self.assertEqual(spec["base_playbook"], "tracked_winner_chain_native_qqq_time65_research")
        self.assertEqual(overrides["allowed_tickers"], all_sleeves.TRACKED_WINNER_UNIVERSE)
        self.assertEqual(overrides["historical_required_underlyings"], all_sleeves.TRACKED_WINNER_UNIVERSE)
        self.assertEqual(overrides["chain_native_max_entry_leg_bid_ask_pct"], 30.0)
        self.assertEqual(overrides["chain_native_min_entry_short_bid"], 0.15)
        self.assertEqual(overrides["chain_native_min_prior_quote_days"], 2)
        self.assertEqual(overrides["chain_native_min_short_prior_quote_days"], 3)
        self.assertEqual(overrides["chain_native_short_inside_steps"], 1)
        self.assertTrue(overrides["execution_survivability_enabled"])
        self.assertEqual(overrides["min_tradability_score"], 70.0)

    def test_bullish_sleeve_variant_forwards_dynamic_variant_flags(self):
        with WorkspaceTempDir(prefix="all-planned-iwm-sleeve") as tmp:
            result_path = Path(tmp) / "iwm-result.json"
            with patch.object(all_sleeves.sleeve_runner, "run_variants") as run_variants:
                run_variants.return_value = {
                    "rows": [
                        {
                            "variant_id": "sleeve_ticker_iwm",
                            "result_path": str(result_path),
                        }
                    ]
                }

                result = all_sleeves._run_bullish_sleeve_variant(
                    {
                        "variant_id": "sleeve_ticker_iwm",
                        "include_tickers": True,
                        "include_themes": False,
                    },
                    lookback_years=1,
                )

        self.assertEqual(result, result_path.resolve())
        run_variants.assert_called_once_with(
            lookback_years=1,
            only={"sleeve_ticker_iwm"},
            include_themes=False,
            include_tickers=True,
        )


if __name__ == "__main__":
    unittest.main()
