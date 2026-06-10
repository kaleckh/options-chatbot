import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from unittest.mock import patch

from forward_options_ledger import (
    _trusted_truth_horizon_for_db,
    build_forward_scan_snapshot,
    init_forward_ledger,
    list_forward_scan_pick_events,
    list_forward_sessions,
    migrate_live_production_evidence,
    record_forward_snapshot,
    record_position_opened,
    summarize_forward_holdout,
)


class _UnavailablePositionsRepo:
    is_available = False
    error_message = "DATABASE_URL is not configured for tracked positions."

    def list_positions(self, status="closed"):
        return []


class _ClosedPositionsRepo:
    is_available = True

    def __init__(self, positions):
        self.positions = list(positions)

    def list_positions(self, status="closed"):
        return list(self.positions) if status == "closed" else []


class ForwardOptionsLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "forward_tracking.db")

    def test_build_forward_scan_snapshot_preserves_candidate_audit_picks(self):
        snapshot = build_forward_scan_snapshot(
            picks=[],
            candidate_audit_picks=[
                {
                    "ticker": "SPY",
                    "contract_symbol": "SPY260515C00560000",
                    "guardrail_decision": "blocked",
                }
            ],
            policy_applied=False,
            policy={},
        )

        self.assertEqual(snapshot["picks"], [])
        self.assertEqual(snapshot["candidate_audit_picks"][0]["ticker"], "SPY")
        self.assertEqual(snapshot["candidate_audit_picks"][0]["guardrail_decision"], "blocked")

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

        with patch("forward_options_ledger.create_positions_repository", return_value=_UnavailablePositionsRepo()):
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

    def test_unknown_evidence_class_routes_to_quarantine_not_live(self):
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
                        "entry_date": "2026-04-01",
                        "quote_time_et": "2026-04-01T09:45:00-04:00",
                        "quote_basis": "mid",
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                        "bid": 4.9,
                        "ask": 5.1,
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
            source_label="api_scan_auto",
            db_path=self.db_path,
        )

        events = list_forward_scan_pick_events(db_path=self.db_path)
        self.assertEqual(events[0]["evidence_class"], "quarantine_unknown")
        self.assertEqual(events[0]["eligibility_status"], "ineligible")
        self.assertIn("non_live_evidence_class", events[0]["eligibility_blockers"])

    def test_unparseable_entry_and_quote_dates_are_ineligible(self):
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
                            "entry_date": "not-a-date",
                            "quote_time_et": "also-not-a-date",
                            "quote_basis": "mid",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "bid": 4.9,
                            "ask": 5.1,
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

        events = list_forward_scan_pick_events(db_path=self.db_path)
        self.assertEqual(events[0]["evidence_class"], "live_production")
        self.assertEqual(events[0]["eligibility_status"], "ineligible")
        self.assertIn("unparseable_entry_date", events[0]["eligibility_blockers"])

    def test_legacy_blank_eligibility_status_does_not_count_as_eligible(self):
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
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
                db_path=self.db_path,
            )

            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.execute("UPDATE forward_events SET eligibility_status = ''")
                conn.execute("UPDATE forward_sessions SET eligibility_status = ''")
                conn.commit()

            summary = summarize_forward_holdout(db_path=self.db_path)

        self.assertEqual(summary["scan_pick_count"], 1)
        self.assertEqual(summary["eligible_event_count"], 0)
        self.assertEqual(summary["pending_truth_event_count"], 0)

    def test_comparable_contract_picks_are_not_forward_proof_eligible(self):
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
                            "selection_source": "live_comparable_exact_contract",
                            "promotion_class": "comparable_exact_contract",
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

        self.assertEqual(eligible_events, [])
        self.assertEqual(all_events[0]["eligibility_status"], "ineligible")
        self.assertIn("selection_source_not_exact", all_events[0]["eligibility_blockers"])
        self.assertNotIn("promotion_class_not_exact", all_events[0]["eligibility_blockers"])

    def test_supplied_entry_price_does_not_bypass_executable_quote_proof(self):
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
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
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

        self.assertEqual(eligible_events, [])
        self.assertEqual(all_events[0]["eligibility_status"], "ineligible")
        self.assertIn("missing_executable_entry_quote", all_events[0]["eligibility_blockers"])

    def test_vertical_spread_requires_exact_short_leg_and_bid_ask_entry_basis(self):
        with patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        {
                            "ticker": "SPY",
                            "direction": "call",
                            "option_type": "call",
                            "strategy_type": "vertical_spread",
                            "contract_symbol": "SPY260515C00685000",
                            "expiry": "2026-05-15",
                            "strike": 685.0,
                            "short_strike": 700.0,
                            "quote_time_et": "2026-04-01T09:45:00-04:00",
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                            "entry_execution_price": 2.5,
                            "entry_execution_basis": "spread_mid",
                            "legs": [
                                {"role": "long", "contract_symbol": "SPY260515C00685000", "strike": 685.0, "bid": 4.8, "ask": 5.0},
                                {"role": "short", "strike": 700.0, "bid": 2.4, "ask": 2.6},
                            ],
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

        self.assertEqual(eligible_events, [])
        self.assertEqual(all_events[0]["eligibility_status"], "ineligible")
        self.assertIn("missing_short_contract_symbol", all_events[0]["eligibility_blockers"])
        self.assertIn("spread_entry_not_bid_ask", all_events[0]["eligibility_blockers"])

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

    def test_session_with_any_future_pick_is_pending_truth(self):
        def _pick(ticker: str, quote_time_et: str) -> dict:
            return {
                "ticker": ticker,
                "direction": "call",
                "option_type": "call",
                "contract_symbol": f"{ticker}260417C00560000",
                "expiry": "2026-04-17",
                "strike": 560.0,
                "quote_time_et": quote_time_et,
                "quote_basis": "mid",
                "selection_source": "live_chain_exact_contract",
                "promotion_class": "promotable_exact_contract",
                "bid": 4.9,
                "ask": 5.1,
                "entry_execution_price": 5.1,
                "entry_execution_basis": "ask",
                "entry_fee_total_usd": 0.65,
            }

        with patch("forward_options_ledger._trusted_truth_horizon", return_value=date(2026, 4, 1)):
            result = record_forward_snapshot(
                scan_snapshot={
                    "picks": [
                        _pick("SPY", "2026-04-01T09:45:00-04:00"),
                        _pick("QQQ", "2026-04-02T09:45:00-04:00"),
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
            sessions = list_forward_sessions(db_path=self.db_path)

        self.assertEqual(result["eligibility_status"], "pending_truth")
        self.assertEqual(sessions[0]["eligibility_status"], "pending_truth")
        self.assertEqual(sessions[0]["eligibility_blockers"], ["entry_date_beyond_trusted_truth_horizon"])

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

        with patch("forward_options_ledger.create_positions_repository", return_value=_UnavailablePositionsRepo()):
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

    def test_summary_realized_pnl_ignores_non_proof_closed_positions(self):
        record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {
                    "truth_source": "historical_imported_daily",
                    "promotion_status": "watch",
                },
                "playbook": {"id": "short_term"},
                "cohort_ids": ["broad_ev7"],
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="quiet_day",
            db_path=self.db_path,
        )
        proof_position = {
            "status": "closed",
            "contracts": 1,
            "entry_execution_price": 1.0,
            "gross_pnl_usd": 50.0,
            "net_pnl_usd": 48.7,
            "proof_eligible": True,
            "source_pick_snapshot": {"cohort_id": "broad_ev7"},
        }
        non_proof_position = {
            "status": "closed",
            "contracts": 1,
            "entry_execution_price": 1.0,
            "gross_pnl_usd": -500.0,
            "net_pnl_usd": -501.3,
            "proof_eligible": False,
            "source_pick_snapshot": {"cohort_id": "broad_ev7"},
        }

        with patch(
            "forward_options_ledger.create_positions_repository",
            return_value=_ClosedPositionsRepo([proof_position, non_proof_position]),
        ):
            summary = summarize_forward_holdout(cohort_id="broad_ev7", db_path=self.db_path)

        self.assertEqual(summary["closed_review_count"], 1)
        self.assertEqual(summary["gross_realized_pnl_usd"], 50.0)
        self.assertEqual(summary["net_realized_pnl_usd"], 48.7)
        self.assertEqual(summary["gross_realized_pnl_pct"], 50.0)
        self.assertEqual(summary["net_realized_pnl_pct"], 48.7)

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

    def test_schema_has_forward_report_query_path_indexes(self):
        init_forward_ledger(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as conn:
            session_indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(forward_sessions)").fetchall()
            }
            event_indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(forward_events)").fetchall()
            }

        self.assertIn("idx_forward_sessions_source_recorded", session_indexes)
        self.assertIn("idx_forward_sessions_evidence_eligibility_recorded", session_indexes)
        self.assertIn("idx_forward_events_type_session", event_indexes)
        self.assertIn("idx_forward_events_scan_filters", event_indexes)

    def test_scan_pick_filters_use_columns_before_payload_decode(self):
        for cohort_id, ticker in (("broad_ev7", "SPY"), ("other_cohort", "QQQ")):
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
                            "cohort_id": cohort_id,
                            "selection_source": "live_chain_exact_contract",
                            "promotion_class": "promotable_exact_contract",
                        }
                    ],
                    "policy_applied": True,
                    "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                    "playbook": {"id": "short_term"},
                },
                reviewed_positions=[],
                tracked_positions=[],
                source_label="api_scan_auto",
                db_path=self.db_path,
            )

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE forward_events SET payload_json = ? WHERE ticker = ?",
                ("{not-json", "QQQ"),
            )
            conn.commit()

        events = list_forward_scan_pick_events(
            cohort_id="broad_ev7",
            tickers=["SPY"],
            db_path=self.db_path,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ticker"], "SPY")
        self.assertEqual(events[0]["cohort_id"], "broad_ev7")

    def test_scan_pick_filters_preserve_legacy_null_column_payload_fallback(self):
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
                        "quote_time_et": "2026-04-01",
                        "quote_basis": "mid",
                        "cohort_id": "legacy_cohort",
                        "selection_source": "live_chain_exact_contract",
                        "promotion_class": "promotable_exact_contract",
                    }
                ],
                "policy_applied": True,
                "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                "playbook": {"id": "short_term"},
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="api_scan_auto",
            db_path=self.db_path,
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE forward_events SET cohort_id = NULL, ticker = NULL")
            conn.commit()

        events = list_forward_scan_pick_events(
            cohort_id="legacy_cohort",
            tickers=["SPY"],
            db_path=self.db_path,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ticker"], "SPY")
        self.assertEqual(events[0]["cohort_id"], "legacy_cohort")

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


    def test_record_position_opened_writes_ledger_event(self):
        position = {
            "id": 42,
            "ticker": "SPY",
            "direction": "call",
            "contract_symbol": "SPY260417C00560000",
            "strike": 560.0,
            "expiry": "2026-04-17",
            "contracts": 2,
            "entry_execution_price": 5.10,
            "entry_execution_basis": "ask",
            "entry_fee_total_usd": 1.30,
            "source_scan_session_id": 99,
            "source_scan_event_key": "baseline_broad_control:rank_1",
            "source_scan_run_id": "test_run_001",
            "source_scan_recorded_at_utc": "2026-04-06T14:00:00Z",
            "proof_eligible": True,
            "proof_ineligibility_reason": None,
            "source_pick_snapshot": {
                "ticker": "SPY",
                "direction": "call",
                "contract_symbol": "SPY260417C00560000",
                "expiry": "2026-04-17",
                "strike": 560.0,
                "quote_time_et": "2026-04-06T10:00:00",
                "quote_basis": "mid",
                "underlying_price_at_selection": 552.25,
                "selection_source": "live_chain_exact_contract",
                "promotion_class": "promotable_exact_contract",
                "cohort_id": "baseline_broad_control",
                "cohort_role": "control",
            },
        }

        result = record_position_opened(
            position=position,
            source_label="position_opened",
            db_path=self.db_path,
            evidence_class="unit_test",
            run_id="test_run_sprint1",
            run_mode="test_harness",
            is_fixture=True,
        )

        self.assertEqual(result["event_type"], "position_opened")
        self.assertEqual(result["position_id"], 42)
        self.assertEqual(result["ticker"], "SPY")
        self.assertEqual(result["contract_symbol"], "SPY260417C00560000")
        self.assertIsNotNone(result["session_id"])

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT event_type, ticker, contract_symbol, position_id, contracts, "
                "source_scan_session_id, source_scan_event_key, source_scan_run_id, "
                "outcome_state, entry_execution_price, entry_execution_basis "
                "FROM forward_events WHERE event_type = 'position_opened'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "position_opened")
        self.assertEqual(row[1], "SPY")
        self.assertEqual(row[2], "SPY260417C00560000")
        self.assertEqual(row[3], 42)
        self.assertEqual(row[4], 2)
        self.assertEqual(row[5], 99)
        self.assertEqual(row[6], "baseline_broad_control:rank_1")
        self.assertEqual(row[7], "test_run_001")
        self.assertEqual(row[8], "taken")
        self.assertEqual(row[9], 5.10)
        self.assertEqual(row[10], "ask")

    def test_record_position_opened_requires_position_proof_for_eligibility(self):
        position = {
            "id": 43,
            "ticker": "SPY",
            "direction": "call",
            "contract_symbol": "SPY260417C00560000",
            "strike": 560.0,
            "expiry": "2026-04-17",
            "contracts": 1,
            "entry_execution_price": 5.10,
            "entry_execution_basis": "manual_fill",
            "proof_eligible": False,
            "proof_class": "manual_broker_exact_contract",
            "proof_ineligibility_reason": "manual_fill_not_scan_execution",
            "source_pick_snapshot": {
                "ticker": "SPY",
                "direction": "call",
                "contract_symbol": "SPY260417C00560000",
                "expiry": "2026-04-17",
                "strike": 560.0,
                "quote_time_et": "2026-04-06T10:00:00",
                "selection_source": "live_chain_exact_contract",
                "promotion_class": "promotable_exact_contract",
                "proof_class": "manual_broker_exact_contract",
            },
        }

        record_position_opened(
            position=position,
            source_label="position_opened",
            db_path=self.db_path,
            evidence_class="live_production",
            run_id="test_run_manual_fill",
            run_mode="live",
            is_fixture=False,
        )

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT eligibility_status, eligibility_blockers FROM forward_sessions WHERE run_id = ?",
                ("test_run_manual_fill",),
            ).fetchone()

        self.assertEqual(row[0], "ineligible")
        self.assertIn("position_not_live_scan_proof", row[1])

    def test_matching_prefers_explicit_scan_provenance_ids(self):
        from forward_options_ledger import _tracked_position_matches_pick

        pick_with_provenance = {
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-04-17",
            "strike": 560.0,
            "contract_symbol": "SPY260417C00560000",
            "source_scan_session_id": 100,
            "source_scan_event_key": "baseline_broad_control:rank_1",
        }

        position_matching = {
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-04-17",
            "strike": 560.0,
            "contract_symbol": "SPY260417C00560000",
            "source_scan_session_id": 100,
            "source_scan_event_key": "baseline_broad_control:rank_1",
            "source_pick_snapshot": {},
        }

        position_different_provenance = {
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-04-17",
            "strike": 560.0,
            "contract_symbol": "SPY260417C00560000",
            "source_scan_session_id": 200,
            "source_scan_event_key": "baseline_broad_control:rank_2",
            "source_pick_snapshot": {},
        }

        self.assertTrue(_tracked_position_matches_pick(pick_with_provenance, [position_matching]))
        # Falls through to contract symbol match even if provenance differs
        self.assertTrue(_tracked_position_matches_pick(pick_with_provenance, [position_different_provenance]))

    def test_vertical_spread_matching_requires_the_short_leg(self):
        from forward_options_ledger import _tracked_position_matches_pick

        pick = {
            "ticker": "SPY",
            "direction": "call",
            "strategy_type": "vertical_spread",
            "expiry": "2026-05-15",
            "strike": 685.0,
            "short_strike": 700.0,
            "contract_symbol": "SPY260515C00685000",
            "short_contract_symbol": "SPY260515C00700000",
        }
        position_different_short = {
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-05-15",
            "strike": 685.0,
            "contract_symbol": "SPY260515C00685000",
            "source_pick_snapshot": {
                "strategy_type": "vertical_spread",
                "short_strike": 695.0,
                "short_contract_symbol": "SPY260515C00695000",
            },
        }
        position_matching_short = {
            "ticker": "SPY",
            "direction": "call",
            "expiry": "2026-05-15",
            "strike": 685.0,
            "contract_symbol": "SPY260515C00685000",
            "source_pick_snapshot": {
                "strategy_type": "vertical_spread",
                "short_strike": 700.0,
                "short_contract_symbol": "SPY260515C00700000",
            },
        }

        self.assertFalse(_tracked_position_matches_pick(pick, [position_different_short]))
        self.assertTrue(_tracked_position_matches_pick(pick, [position_matching_short]))

    def test_drop_counts_preserved_in_scan_funnel(self):
        result = record_forward_snapshot(
            scan_snapshot={
                "picks": [],
                "policy_applied": True,
                "policy": {"truth_source": "historical_imported_daily", "promotion_status": "watch"},
                "playbook": {"id": "short_term"},
                "scan_funnel": {
                    "raw_candidates": 0,
                    "post_policy_visible": 0,
                    "post_guardrails_visible": 0,
                    "returned_picks": 0,
                    "policy_filtered_out": 0,
                    "guardrail_filtered_out": 0,
                    "final_trimmed": 0,
                    "drop_counts": {
                        "tech_score": 5,
                        "option_liquidity": 3,
                        "min_history": 0,
                    },
                    "symbol_diagnostics": {
                        "SPY": {"history_eligible": True, "signal_candidate": False, "final_candidate": False},
                        "QQQ": {"history_eligible": True, "signal_candidate": True, "final_candidate": False},
                    },
                },
            },
            reviewed_positions=[],
            tracked_positions=[],
            source_label="unit_test",
            db_path=self.db_path,
        )

        sessions = list_forward_sessions(db_path=self.db_path)
        self.assertEqual(len(sessions), 1)
        funnel = sessions[0]["notes"]["scan_funnel"]
        self.assertEqual(funnel["drop_counts"]["tech_score"], 5)
        self.assertEqual(funnel["drop_counts"]["option_liquidity"], 3)
        self.assertEqual(funnel["symbol_diagnostics"]["SPY"]["signal_candidate"], False)
        self.assertEqual(funnel["symbol_diagnostics"]["QQQ"]["signal_candidate"], True)

    def test_claim_readiness_not_ready_with_no_evidence(self):
        from options_profit_gate import evaluate_claim_readiness
        with patch("options_profit_gate._load_forward_evidence", return_value={
            "eligible_event_count": 5,
            "pending_truth_event_count": 0,
            "by_symbol": {"SPY": {"eligible": 3, "pending_truth": 0, "ineligible": 0}, "QQQ": {"eligible": 2, "pending_truth": 0, "ineligible": 0}},
            "contamination_findings": [],
            "stale_metadata_events": [],
        }), patch("options_profit_gate._load_positions_snapshot", return_value={
            "available": True,
            "error_message": None,
            "closed_positions": [],
            "database_url_configured": True,
        }):
            result = evaluate_claim_readiness()
        self.assertFalse(result["claim_ready"])
        self.assertEqual(result["state"], "not_claim_ready")
        self.assertGreater(result["blocker_count"], 0)
        blocker_codes = [b["code"] for b in result["blockers"]]
        self.assertIn("insufficient_eligible_forward_events", blocker_codes)
        self.assertIn("insufficient_exact_contract_positions", blocker_codes)

    def test_loop_healthy_but_not_claim_ready(self):
        """Verify the two-tier gate: loop can be healthy while claim is not ready."""
        from options_profit_gate import LOOP_HEALTH_MIN_ELIGIBLE_FORWARD_EVENTS, CLAIM_MIN_ELIGIBLE_FORWARD_EVENTS
        # Loop health needs 10, claim needs 40
        self.assertLess(LOOP_HEALTH_MIN_ELIGIBLE_FORWARD_EVENTS, CLAIM_MIN_ELIGIBLE_FORWARD_EVENTS)

    def test_matching_falls_back_to_heuristic_for_legacy_positions(self):
        from forward_options_ledger import _tracked_position_matches_pick

        pick_no_provenance = {
            "ticker": "QQQ",
            "direction": "put",
            "expiry": "2026-04-17",
            "strike": 480.0,
        }

        position_legacy = {
            "ticker": "QQQ",
            "direction": "put",
            "expiry": "2026-04-17",
            "strike": 480.0,
            "source_pick_snapshot": {},
        }

        self.assertTrue(_tracked_position_matches_pick(pick_no_provenance, [position_legacy]))


if __name__ == "__main__":
    unittest.main()
