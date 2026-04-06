import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from unittest.mock import patch

from forward_options_ledger import (
    _trusted_truth_horizon_for_db,
    init_forward_ledger,
    list_forward_scan_pick_events,
    list_forward_sessions,
    migrate_live_production_evidence,
    record_forward_snapshot,
    summarize_forward_holdout,
)


class ForwardOptionsLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "forward_tracking.db")

    def test_record_forward_snapshot_persists_scan_and_reviews(self):
        result = record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "option_type": "call",
                        "contract_symbol": "SPY260417C00560000",
                        "expiry": "2026-04-17",
                        "strike": 560.0,
                        "quote_time_et": "2026-04-01",
                        "quote_basis": "mid",
                        "underlying_price_at_selection": 552.25,
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "bid": 4.9,
                        "ask": 5.1,
                        "mid": 5.0,
                        "delta": 0.32,
                        "iv_percentile": 44.0,
                        "trade_policy_decision": "watch",
                        "cohort_id": "baseline_broad_control",
                        "cohort_role": "control",
                    }
                ],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
                "scan_funnel": {
                    "raw_candidates": 3,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 1,
                    "returned_picks": 1,
                    "policy_filtered_out": 1,
                    "guardrail_filtered_out": 1,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "baseline_broad_control": {
                        "raw_candidates": 3,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 1,
                        "returned_picks": 1,
                        "policy_filtered_out": 1,
                        "guardrail_filtered_out": 1,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[
                {
                    "id": 7,
                    "ticker": "SPY",
                    "contract_symbol": "SPY260417C00560000",
                    "source_pick_snapshot": {
                        "contract_symbol": "SPY260417C00560000",
                        "expiry": "2026-04-17",
                        "strike": 560.0,
                        "quote_time_et": "2026-04-01",
                        "quote_basis": "mid",
                        "underlying_price_at_selection": 552.25,
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "cohort_id": "baseline_broad_control",
                    },
                    "latest_review": {
                        "recommendation": "HOLD",
                        "pricing_source": "mid",
                    },
                }
            ],
            tracked_positions=[
                {
                    "id": 7,
                    "ticker": "SPY",
                    "source_pick_snapshot": {
                        "contract_symbol": "SPY260417C00560000",
                        "cohort_id": "baseline_broad_control",
                    },
                }
            ],
            source_label="unit_test",
            db_path=self.db_path,
        )

        self.assertEqual(result["scan_picks_count"], 1)
        self.assertEqual(result["reviewed_positions_count"], 1)
        self.assertEqual(result["truth_source"], "historical_imported_daily")
        self.assertEqual(result["taken_pick_count"], 1)
        self.assertEqual(result["skipped_pick_count"], 0)
        self.assertEqual(result["blocked_pick_count"], 0)
        self.assertEqual(result["requested_cohort_ids"], [])
        self.assertEqual(result["scan_funnel"]["raw_candidates"], 3)
        self.assertEqual(result["evidence_class"], "unit_test")
        self.assertTrue(result["is_fixture"])
        self.assertEqual(result["eligibility_status"], "ineligible")
        self.assertIn("non_live_evidence_class", result["eligibility_blockers"])

        sessions = list_forward_sessions(db_path=self.db_path)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["source_label"], "unit_test")
        self.assertEqual(sessions[0]["scan_picks_count"], 1)
        self.assertEqual(sessions[0]["reviewed_positions_count"], 1)
        self.assertEqual(sessions[0]["notes"]["scan_funnel"]["post_guardrails_visible"], 1)
        self.assertEqual(sessions[0]["evidence_class"], "unit_test")
        self.assertTrue(sessions[0]["is_fixture"])
        self.assertEqual(sessions[0]["eligibility_status"], "ineligible")
        self.assertIn("non_live_evidence_class", sessions[0]["eligibility_blockers"])

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT
                    event_type,
                    contract_symbol,
                    expiry,
                    strike,
                    option_type,
                    quote_time_et,
                    quote_basis,
                    underlying_price_at_selection,
                    selection_source,
                    promotion_class,
                    policy_state,
                    outcome_state,
                    evidence_class,
                    is_fixture,
                    quote_freshness_status,
                    eligibility_status,
                    eligibility_blockers,
                    entry_execution_price,
                    entry_execution_basis,
                    entry_fee_total_usd
                FROM forward_events
                WHERE event_type = 'scan_pick'
                """
            ).fetchone()
        self.assertEqual(row[0], "scan_pick")
        self.assertEqual(row[1], "SPY260417C00560000")
        self.assertEqual(row[2], "2026-04-17")
        self.assertEqual(row[3], 560.0)
        self.assertEqual(row[4], "call")
        self.assertEqual(row[5], "2026-04-01")
        self.assertEqual(row[6], "mid")
        self.assertEqual(row[7], 552.25)
        self.assertEqual(row[8], "live_chain_exact_contract")
        self.assertEqual(row[9], "promotable_exact_contract")
        self.assertEqual(row[10], "watch")
        self.assertEqual(row[11], "taken")
        self.assertEqual(row[12], "unit_test")
        self.assertEqual(row[13], 1)
        self.assertEqual(row[14], "observed")
        self.assertEqual(row[15], "ineligible")
        self.assertIn("non_live_evidence_class", row[16])
        self.assertEqual(row[17], 5.1)
        self.assertEqual(row[18], "ask")
        self.assertEqual(row[19], 0.65)

        summary = summarize_forward_holdout(cohort_id=None, db_path=self.db_path)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(summary["taken_pick_count"], 1)
        self.assertEqual(summary["review_count"], 1)
        self.assertEqual(summary["eligible_event_count"], 0)
        self.assertEqual(summary["pending_truth_event_count"], 0)
        self.assertFalse(summary["tracked_positions_available"])
        self.assertEqual(summary["gross_realized_pnl_usd"], 0.0)
        self.assertEqual(summary["net_realized_pnl_usd"], 0.0)
        self.assertIsNone(summary["gross_realized_pnl_pct"])
        self.assertIsNone(summary["net_realized_pnl_pct"])
        self.assertEqual(summary["scan_funnel_totals"]["raw_candidates"], 3)
        self.assertEqual(summary["latest_starvation_stage"], None)
        self.assertEqual(summary["by_symbol"]["SPY"]["scan_pick_count"], 1)
        self.assertEqual(summary["by_playbook"]["short_term"]["review_count"], 1)
        self.assertEqual(summary["exact_contract_coverage"]["scan_pick"]["with_contract_count"], 1)
        self.assertEqual(summary["session_contract_coverage"][0]["taken_pick_with_contract_count"], 1)

        events = list_forward_scan_pick_events(db_path=self.db_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["contract_symbol"], "SPY260417C00560000")
        self.assertEqual(events[0]["selection_source"], "live_chain_exact_contract")
        self.assertEqual(events[0]["promotion_class"], "promotable_exact_contract")
        self.assertEqual(events[0]["evidence_class"], "unit_test")
        self.assertTrue(events[0]["is_fixture"])
        self.assertEqual(events[0]["eligibility_status"], "ineligible")
        self.assertIn("non_live_evidence_class", events[0]["eligibility_blockers"])

    def test_trusted_truth_horizon_uses_requested_db_path(self):
        _trusted_truth_horizon_for_db.cache_clear()
        with patch("forward_options_ledger.HistoricalOptionsStore") as store_cls:
            store_cls.return_value.snapshot_summary.return_value = {
                "latest_quote_at_utc": "2026-04-02T00:00:00Z",
            }
            horizon = _trusted_truth_horizon_for_db(self.db_path)

        self.assertEqual(horizon, date(2026, 4, 2))
        store_cls.assert_called_once_with(self.db_path)
        _trusted_truth_horizon_for_db.cache_clear()

    def test_init_forward_ledger_upgrades_legacy_schema_before_indexing(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(
                """
                CREATE TABLE forward_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at_utc TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    playbook TEXT,
                    truth_source TEXT,
                    promotion_status TEXT,
                    scan_picks_count INTEGER NOT NULL DEFAULT 0,
                    reviewed_positions_count INTEGER NOT NULL DEFAULT 0,
                    notes_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE forward_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES forward_sessions(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    event_key TEXT,
                    ticker TEXT,
                    contract_symbol TEXT,
                    recommendation TEXT,
                    pricing_source TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )
            conn.commit()

        init_forward_ledger(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(forward_events)").fetchall()
            }
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(forward_events)").fetchall()
            }

        self.assertIn("cohort_id", columns)
        self.assertIn("outcome_state", columns)
        self.assertIn("expiry", columns)
        self.assertIn("strike", columns)
        self.assertIn("selection_source", columns)
        self.assertIn("promotion_class", columns)
        self.assertIn("evidence_class", columns)
        self.assertIn("eligibility_status", columns)
        self.assertIn("eligibility_blockers", columns)
        self.assertIn("idx_forward_events_cohort", indexes)

    def test_eligible_only_filter_returns_only_live_production_contracts(self):
        with patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "SPY",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "SPY260417C00560000",
                            "expiry": "2026-04-17",
                            "strike": 560.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "bid": 4.9,
                            "ask": 5.1,
                            "entry_execution_price": 5.1,
                            "entry_execution_basis": "ask",
                            "entry_fee_total_usd": 0.65,
                        }
                    ],
                    "policy_applied": True,
                    "policy": {
                        "truth_source": "historical_imported_daily",
                        "promotion_status": "watch",
                    },
                    "playbook": {"id": "short_term"},
                    "evidence_class": "live_production",
                    "run_mode": "live",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
                db_path=self.db_path,
            )
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "QQQ",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "QQQ260417C00450000",
                            "expiry": "2026-04-17",
                            "strike": 450.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "fixture_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "bid": 3.9,
                            "ask": 4.1,
                            "entry_execution_price": 4.1,
                            "entry_execution_basis": "ask",
                            "entry_fee_total_usd": 0.65,
                        }
                    ],
                    "policy_applied": True,
                    "policy": {
                        "truth_source": "historical_imported_daily",
                        "promotion_status": "watch",
                    },
                    "playbook": {"id": "short_term"},
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="fixture_smoke",
                db_path=self.db_path,
            )
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "IWM",
                            "direction": "put",
                            "option_type": "put",
                            "contract_symbol": "IWM260417P00200000",
                            "expiry": "2026-04-17",
                            "strike": 200.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "quote_freshness_status": "stale",
                            "bid": 5.8,
                            "ask": 6.1,
                            "entry_execution_price": 6.1,
                            "entry_execution_basis": "ask",
                            "entry_fee_total_usd": 0.65,
                        }
                    ],
                    "policy_applied": True,
                    "policy": {
                        "truth_source": "historical_imported_daily",
                        "promotion_status": "watch",
                    },
                    "playbook": {"id": "short_term"},
                    "evidence_class": "live_production",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
                db_path=self.db_path,
            )

            all_events = list_forward_scan_pick_events(db_path=self.db_path)
            eligible_events = list_forward_scan_pick_events(eligible_only=True, db_path=self.db_path)

        self.assertEqual(len(all_events), 3)
        self.assertEqual(len(eligible_events), 1)
        self.assertEqual(eligible_events[0]["ticker"], "SPY")
        self.assertEqual(eligible_events[0]["evidence_class"], "live_production")
        self.assertEqual(eligible_events[0]["eligibility_status"], "eligible")
        self.assertEqual(eligible_events[0]["eligibility_blockers"], [])

    def test_pending_truth_events_are_counted_separately_from_eligible_events(self):
        with patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "SPY",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "SPY260417C00560000",
                            "expiry": "2026-04-17",
                            "strike": 560.0,
                            "quote_time_et": "2026-04-02T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "bid": 4.9,
                            "ask": 5.1,
                            "entry_execution_price": 5.1,
                            "entry_execution_basis": "ask",
                            "entry_fee_total_usd": 0.65,
                        }
                    ],
                    "policy_applied": True,
                    "policy": {
                        "truth_source": "historical_imported_daily",
                        "promotion_status": "watch",
                    },
                    "playbook": {"id": "short_term"},
                    "evidence_class": "live_production",
                    "run_mode": "live",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
                db_path=self.db_path,
            )

            all_events = list_forward_scan_pick_events(db_path=self.db_path)
            eligible_events = list_forward_scan_pick_events(eligible_only=True, db_path=self.db_path)
            summary = summarize_forward_holdout(db_path=self.db_path)

        self.assertEqual(len(all_events), 1)
        self.assertEqual(all_events[0]["eligibility_status"], "pending_truth")
        self.assertEqual(all_events[0]["eligibility_blockers"], ["entry_date_beyond_trusted_truth_horizon"])
        self.assertEqual(eligible_events, [])
        self.assertEqual(summary["eligible_event_count"], 0)
        self.assertEqual(summary["pending_truth_event_count"], 1)
        self.assertEqual(summary["by_symbol"]["SPY"]["pending_truth_event_count"], 1)
        self.assertEqual(summary["by_playbook"]["short_term"]["pending_truth_event_count"], 1)

    def test_summary_counts_recorded_sessions_even_when_no_events_exist(self):
        result = record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "block",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 4,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 0,
                    "returned_picks": 0,
                    "policy_filtered_out": 2,
                    "guardrail_filtered_out": 2,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 4,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 0,
                        "returned_picks": 0,
                        "policy_filtered_out": 2,
                        "guardrail_filtered_out": 2,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="quiet_day",
            db_path=self.db_path,
        )

        self.assertEqual(result["scan_picks_count"], 0)
        self.assertEqual(result["requested_cohort_ids"], ["broad_ev7"])

        overall = summarize_forward_holdout(cohort_id=None, db_path=self.db_path)
        self.assertTrue(overall["available"])
        self.assertEqual(overall["session_count"], 1)
        self.assertEqual(overall["scan_pick_count"], 0)
        self.assertEqual(overall["eligible_event_count"], 0)
        self.assertEqual(overall["pending_truth_event_count"], 0)
        self.assertFalse(overall["tracked_positions_available"])
        self.assertEqual(overall["gross_realized_pnl_usd"], 0.0)
        self.assertEqual(overall["net_realized_pnl_usd"], 0.0)
        self.assertIsNone(overall["gross_realized_pnl_pct"])
        self.assertIsNone(overall["net_realized_pnl_pct"])
        self.assertEqual(overall["truth_sources_seen"], ["historical_imported_daily"])
        self.assertEqual(overall["scan_funnel_totals"]["raw_candidates"], 4)
        self.assertEqual(overall["sessions_with_zero_scan_picks"], 1)
        self.assertEqual(overall["latest_starvation_stage"], "guardrails_filtered_all")
        self.assertEqual(overall["by_symbol"], {})
        self.assertEqual(overall["by_playbook"], {})

        cohort_summary = summarize_forward_holdout(cohort_id="broad_ev7", db_path=self.db_path)
        self.assertTrue(cohort_summary["available"])
        self.assertEqual(cohort_summary["session_count"], 1)
        self.assertEqual(cohort_summary["scan_pick_count"], 0)
        self.assertEqual(cohort_summary["eligible_event_count"], 0)
        self.assertEqual(cohort_summary["pending_truth_event_count"], 0)
        self.assertEqual(cohort_summary["scan_funnel_totals"]["raw_candidates"], 4)
        self.assertEqual(cohort_summary["latest_starvation_stage"], "guardrails_filtered_all")

    def test_session_and_holdout_filters_can_scope_to_api_scan_source_label(self):
        for label, ticker in (("api_scan_auto", "SPY"), ("manual_snapshot", "QQQ")):
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": ticker,
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": f"{ticker}260417C00560000",
                            "expiry": "2026-04-17",
                            "strike": 560.0,
                            "quote_time_et": "2026-04-01",
                            "quote_basis": "mid",
                            "underlying_price_at_selection": 552.25,
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                        }
                    ],
                    "policy_applied": True,
                    "policy": {
                        "truth_source": "historical_imported_daily",
                        "promotion_status": "watch",
                    },
                    "playbook": {"id": "short_term"},
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label=label,
                db_path=self.db_path,
            )

        sessions = list_forward_sessions(source_label="api_scan_auto", db_path=self.db_path)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["source_label"], "api_scan_auto")

        summary = summarize_forward_holdout(source_label="api_scan_auto", db_path=self.db_path)
        self.assertEqual(summary["source_label"], "api_scan_auto")
        self.assertEqual(summary["session_count"], 1)
        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(list(summary["by_symbol"].keys()), ["SPY"])

    def test_summary_counts_quiet_sessions_in_cohort_funnel_history(self):
        record_forward_snapshot(
            scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "contract_symbol": "SPY260417C00560000",
                        "trade_policy_decision": "watch",
                        "cohort_id": "broad_ev7",
                        "cohort_role": "broad_challenger",
                    }
                ],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 2,
                    "post_policy_visible": 1,
                    "post_guardrails_visible": 1,
                    "returned_picks": 1,
                    "policy_filtered_out": 1,
                    "guardrail_filtered_out": 0,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 2,
                        "post_policy_visible": 1,
                        "post_guardrails_visible": 1,
                        "returned_picks": 1,
                        "policy_filtered_out": 1,
                        "guardrail_filtered_out": 0,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="eventful_day",
            db_path=self.db_path,
        )
        record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "block",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
                "scan_funnel": {
                    "raw_candidates": 5,
                    "post_policy_visible": 2,
                    "post_guardrails_visible": 0,
                    "returned_picks": 0,
                    "policy_filtered_out": 3,
                    "guardrail_filtered_out": 2,
                    "final_trimmed": 0,
                },
                "cohort_funnels": {
                    "broad_ev7": {
                        "raw_candidates": 5,
                        "post_policy_visible": 2,
                        "post_guardrails_visible": 0,
                        "returned_picks": 0,
                        "policy_filtered_out": 3,
                        "guardrail_filtered_out": 2,
                        "final_trimmed": 0,
                    }
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="quiet_day",
            db_path=self.db_path,
        )

        summary = summarize_forward_holdout(cohort_id="broad_ev7", db_path=self.db_path)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["session_count"], 2)
        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(summary["sessions_with_zero_scan_picks"], 1)
        self.assertEqual(summary["scan_funnel_totals"]["raw_candidates"], 7)
        self.assertEqual(summary["scan_funnel_totals"]["guardrail_filtered_out"], 2)
        self.assertEqual(summary["latest_scan_funnel"]["post_guardrails_visible"], 0)
        self.assertEqual(summary["latest_starvation_stage"], "guardrails_filtered_all")

    def test_default_write_routing_sends_live_production_to_authoritative_ledger(self):
        archive_path = os.path.join(self._tmp.name, "forward_tracking_shared.db")
        authoritative_path = os.path.join(self._tmp.name, "forward_tracking_authoritative.db")
        with patch.dict(
            os.environ,
            {
                "FORWARD_OPTIONS_LEDGER_DB_PATH": archive_path,
                "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": authoritative_path,
            },
            clear=False,
        ), patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            live_result = record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "SPY",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "SPY260417C00560000",
                            "expiry": "2026-04-17",
                            "strike": 560.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "entry_execution_price": 5.1,
                            "entry_execution_basis": "ask",
                        }
                    ],
                    "policy_applied": True,
                    "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                    "playbook": {"id": "short_term"},
                    "evidence_class": "live_production",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
            )
            research_result = record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "QQQ",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "QQQ260417C00450000",
                            "expiry": "2026-04-17",
                            "strike": 450.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "model_target_contract",
                            "promotion_class": "research_bootstrap",
                        }
                    ],
                    "policy_applied": True,
                    "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                    "playbook": {"id": "short_term"},
                    "evidence_class": "research_backfill",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="research_backfill",
            )

        self.assertEqual(os.path.abspath(live_result["db_path"]), os.path.abspath(authoritative_path))
        self.assertEqual(os.path.abspath(research_result["db_path"]), os.path.abspath(archive_path))
        self.assertEqual(len(list_forward_sessions(db_path=authoritative_path)), 1)
        self.assertEqual(len(list_forward_sessions(db_path=archive_path)), 1)

    def test_migration_copies_only_live_production_sessions(self):
        archive_path = os.path.join(self._tmp.name, "forward_tracking_shared.db")
        authoritative_path = os.path.join(self._tmp.name, "forward_tracking_authoritative.db")
        with patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            record_forward_snapshot(
                scan_snapshot={
                "picks": [
                    {
                        "ticker": "SPY",
                        "direction": "call",
                        "option_type": "call",
                        "contract_symbol": "SPY260417C00560000",
                        "expiry": "2026-04-17",
                        "strike": 560.0,
                        "quote_time_et": "2026-04-01T09:45:00-04:00",
                        "quote_basis": "mid",
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "entry_execution_price": 5.1,
                        "entry_execution_basis": "ask",
                    }
                ],
                "policy_applied": True,
                "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                "playbook": {"id": "short_term"},
                "evidence_class": "live_production",
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="api_scan_auto",
                db_path=archive_path,
            )
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "QQQ",
                            "direction": "call",
                            "option_type": "call",
                            "contract_symbol": "QQQ260417C00450000",
                            "expiry": "2026-04-17",
                            "strike": 450.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "quote_basis": "mid",
                            "selection_source": "model_target_contract",
                            "promotion_class": "research_bootstrap",
                        }
                    ],
                    "policy_applied": True,
                    "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                    "playbook": {"id": "short_term"},
                    "evidence_class": "research_backfill",
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="research_backfill",
                db_path=archive_path,
            )

        result = migrate_live_production_evidence(
            source_db_path=archive_path,
            destination_db_path=authoritative_path,
        )

        authoritative_sessions = list_forward_sessions(db_path=authoritative_path)
        authoritative_events = list_forward_scan_pick_events(db_path=authoritative_path)
        self.assertEqual(result["status"], "migrated")
        self.assertEqual(result["selected_session_count"], 1)
        self.assertEqual(result["migrated_session_count"], 1)
        self.assertEqual(len(authoritative_sessions), 1)
        self.assertEqual(authoritative_sessions[0]["evidence_class"], "live_production")
        self.assertEqual(len(authoritative_events), 1)
        self.assertEqual(authoritative_events[0]["ticker"], "SPY")


if __name__ == "__main__":
    unittest.main()
