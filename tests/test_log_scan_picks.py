import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import scripts.log_scan_picks as log_scan_picks


class _WeekendDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 4, 11, 11, 0, 0)


class _WeekdayDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 4, 14, 11, 0, 0)


class _HolidayDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 5, 25, 11, 0, 0)


class _UnavailableRepository:
    is_available = False


class _FakeRepository:
    is_available = True

    def __init__(self):
        self.positions = {
            7: {
                "id": 7,
                "ticker": "SPY",
                "source_pick_snapshot": {"ticker": "SPY"},
            }
        }
        self.updates = []

    def get_position(self, position_id):
        return dict(self.positions.get(position_id) or {})

    def update_position(self, position_id, updates):
        self.updates.append((position_id, dict(updates)))
        self.positions[position_id].update(updates)
        return dict(self.positions[position_id])


class _TrackingRepository:
    is_available = True

    def __init__(self):
        self.created = []

    def list_positions(self, status=None):
        return []

    def create_position(self, payload):
        created = {"id": len(self.created) + 1, **dict(payload)}
        self.created.append(created)
        return created


def _make_pick(ticker: str, *, debit: float) -> dict:
    return {
        "ticker": ticker,
        "direction": "call",
        "type": "daily_scan",
        "strategy_type": "vertical_spread",
        "strike": 500.0,
        "short_strike": 520.0,
        "net_debit": debit,
        "expiry": "2026-05-15",
    }


class LogScanPicksTests(unittest.TestCase):
    def test_replace_scan_rows_rewrites_only_requested_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "scan_picks.jsonl"
            log_scan_picks._write_log_rows(
                [
                    {"scan_date": "2026-04-08", "ticker": "SPY"},
                    {"scan_date": "2026-04-09", "ticker": "QQQ"},
                    {"scan_date": "2026-04-09", "ticker": "IWM"},
                ],
                log_file=log_file,
            )

            replaced = log_scan_picks._replace_scan_rows(
                "2026-04-09",
                [{"scan_date": "2026-04-09", "ticker": "XLK"}],
                log_file=log_file,
            )

            rows = log_scan_picks._load_log_rows(log_file=log_file)
            self.assertEqual(replaced, 2)
            self.assertEqual(
                rows,
                [
                    {"scan_date": "2026-04-08", "ticker": "SPY"},
                    {"scan_date": "2026-04-09", "ticker": "XLK"},
                ],
            )

    def test_replace_scan_rows_keeps_other_same_day_playbooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "scan_picks.jsonl"
            log_scan_picks._write_log_rows(
                [
                    {"scan_date": "2026-04-14", "ticker": "SPY", "playbook_id": "short_term"},
                    {
                        "scan_date": "2026-04-14",
                        "ticker": "QQQ",
                        "playbook_id": "quality90_debit55_canary",
                    },
                ],
                log_file=log_file,
            )

            replaced = log_scan_picks._replace_scan_rows(
                "2026-04-14",
                [
                    {
                        "scan_date": "2026-04-14",
                        "ticker": "IWM",
                        "playbook_id": "quality90_debit55_canary",
                    }
                ],
                log_file=log_file,
            )

            rows = log_scan_picks._load_log_rows(log_file=log_file)
            self.assertEqual(replaced, 1)
            self.assertEqual(
                rows,
                [
                    {"scan_date": "2026-04-14", "ticker": "SPY", "playbook_id": "short_term"},
                    {
                        "scan_date": "2026-04-14",
                        "ticker": "IWM",
                        "playbook_id": "quality90_debit55_canary",
                    },
                ],
            )

    def test_main_skips_weekend_before_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekendDateTime),
                patch.object(log_scan_picks, "load_local_env") as load_local_env,
            ):
                log_scan_picks.main()

            load_local_env.assert_not_called()
            self.assertFalse(log_file.exists())

    def test_main_skips_exchange_holiday_before_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _HolidayDateTime),
                patch.object(log_scan_picks, "load_local_env") as load_local_env,
            ):
                log_scan_picks.main()

            load_local_env.assert_not_called()
            self.assertFalse(log_file.exists())

    def test_pick_fill_price_prefers_executable_spread_entry_over_net_debit(self):
        pick = _make_pick("AMZN", debit=7.625)
        pick["entry_execution_price"] = 11.34

        fill_price = log_scan_picks._pick_fill_price(pick)

        self.assertEqual(fill_price, 11.34)

    def test_build_fill_attempt_record_persists_selected_spread_and_auto_track_status(self):
        pick = _make_pick("SPY", debit=5.0)
        pick.update(
            {
                "entry_execution_price": 5.2,
                "entry_execution_basis": "spread_ask_bid",
                "contract_symbol": "SPY260626C00650000",
                "short_contract_symbol": "SPY260626C00680000",
                "spread_width": 30.0,
                "spread_liquidity": {"spread_mid_debit": 5.0},
                "spread_alternatives": [
                    {"rank": 1, "long_strike": 650.0, "short_strike": 680.0},
                    {"rank": 2, "long_strike": 645.0, "short_strike": 675.0},
                    {"rank": 3, "long_strike": 640.0, "short_strike": 670.0},
                    {"rank": 4, "long_strike": 635.0, "short_strike": 665.0},
                ],
                "candidate_execution_label": "executable_opra_paper_candidate",
                "signal_variant": "pullback_uptrend",
                "signal_family": "bullish_pullback",
                "quote_freshness_status": "fresh",
                "options_data_source": "alpaca_opra",
                "selection_source": "live_chain_exact_contract",
            }
        )

        record = log_scan_picks._build_fill_attempt_record(
            pick,
            run_at=_WeekdayDateTime.now(),
            scan_result={
                "playbook": {
                    "id": "bullish_pullback_observation",
                    "label": "Bullish Pullback",
                    "forced_cohort_id": "bullish_pullback_observation",
                }
            },
            candidate_rank=2,
        )

        self.assertEqual(record["event_type"], "candidate_shown")
        self.assertEqual(record["status"], "shown")
        self.assertEqual(record["fill_status"], "pending_auto_track")
        self.assertEqual(record["candidate_rank"], 2)
        self.assertEqual(record["playbook_id"], "bullish_pullback_observation")
        self.assertNotIn("observation_only", record)
        self.assertEqual(record["intended_limit_price"], 5.2)
        self.assertEqual(record["attempted_limit_price"], 5.2)
        self.assertEqual(record["fill_degradation_vs_mid"], 0.2)
        self.assertEqual(record["selected_spread"]["long_contract_symbol"], "SPY260626C00650000")
        self.assertEqual(len(record["top_alternatives"]), 3)
        self.assertEqual(record["top_spread_alternatives"], record["top_alternatives"])
        self.assertEqual(record["top_alternatives"][0]["short_strike"], 680.0)
        self.assertEqual(record["top_alternatives"][-1]["rank"], 3)
        self.assertEqual(record["candidate_execution_label"], "executable_opra_paper_candidate")

    def test_annotate_fill_attempt_outcome_records_review_and_close_marks(self):
        record = log_scan_picks._build_fill_attempt_record(
            _make_pick("SPY", debit=5.0),
            run_at=_WeekdayDateTime.now(),
            scan_result={"playbook": {"id": "bullish_pullback_observation"}},
            candidate_rank=1,
        )

        annotated = log_scan_picks._annotate_fill_attempt_outcomes(
            [record],
            tracked_links=[(42, 1)],
            auto_track_allowed=True,
            repository_available=True,
            reviewed_positions=[
                {
                    "id": 42,
                    "status": "closed",
                    "exit_reason": "auto_sell_recommendation",
                    "closed_at": "2026-04-14T12:00:00-04:00",
                }
            ],
        )[0]

        self.assertEqual(annotated["fill_status"], "auto_tracked")
        self.assertEqual(annotated["fill_outcome"], "paper_fill_recorded")
        self.assertTrue(annotated["filled"])
        self.assertEqual(annotated["auto_track_position_id"], 42)
        self.assertEqual(annotated["review_status"], "closed")
        self.assertEqual(annotated["close_review_status"], "auto_sell_recommendation")
        self.assertEqual(annotated["close_marked_at"], "2026-04-14T12:00:00-04:00")

    def test_build_liquidity_near_miss_record_preserves_alternatives_and_distance(self):
        record = log_scan_picks._build_liquidity_near_miss_records(
            scan_result={
                "candidate_count": 0,
                "returned_count": 0,
                "playbook": {
                    "id": "ai_commodity_infra_observation",
                    "label": "AI Commodity Infra",
                    "forced_cohort_id": "ai_commodity_infra_observation",
                },
                "scan_funnel": {"raw_candidates": 0, "returned_picks": 0},
                "scan_drop_reasons": {
                    "RIO": {
                        "drop_key": "option_liquidity",
                        "details": {
                            "reason": "illiquid_quote",
                            "no_fill_reason": "spread_ask_bid_not_fillable_inside_filters",
                            "ask_bid": {"ask": 3.2, "bid": 0.8},
                            "intended_ask_bid_debit": 2.4,
                            "executable_debit": 2.45,
                            "candidate_execution_label": "rejected_liquidity",
                            "signal_variant": "momentum",
                            "liquidity": {
                                "reasons": ["wide_leg_spread", "stale_leg_quote"],
                                "worst_leg_bid_ask_spread_pct": 12.5,
                                "spread_bid_ask_pct_of_mid": 8.0,
                                "min_leg_open_interest": 250,
                                "max_quote_age_hours": 18.25,
                            },
                            "liquidity_filters": {
                                "liquidity_spread_max_pct": 8.0,
                                "spread_liquidity_slippage_max_pct": 10.0,
                                "min_option_open_interest": 200,
                                "max_option_quote_age_hours": 8.0,
                            },
                            "selected_spread": {"long_leg": {"contract_symbol": "RIO260619C00070000"}},
                            "spread_alternatives": [{"rank": 1, "long_strike": 70.0, "short_strike": 75.0}],
                        },
                    }
                },
            },
            run_at=_WeekdayDateTime.now(),
        )[0]

        self.assertEqual(record["event_type"], "liquidity_near_miss")
        self.assertEqual(record["playbook_id"], "ai_commodity_infra_observation")
        self.assertEqual(record["ticker"], "RIO")
        self.assertEqual(record["distance_components"]["worst_leg_spread_excess_pct"], 4.5)
        self.assertEqual(record["distance_components"]["quote_age_excess_hours"], 10.25)
        self.assertEqual(record["distance_to_current_filters"], 14.75)
        self.assertEqual(record["selected_spread"]["long_leg"]["contract_symbol"], "RIO260619C00070000")
        self.assertEqual(record["top_alternatives"][0]["short_strike"], 75.0)
        self.assertEqual(record["top_spread_alternatives"], record["top_alternatives"])
        self.assertEqual(record["ask_bid"], {"ask": 3.2, "bid": 0.8})
        self.assertEqual(record["intended_ask_bid_debit"], 2.4)
        self.assertEqual(record["intended_limit_debit"], 2.4)
        self.assertEqual(record["executable_debit"], 2.45)
        self.assertEqual(record["max_quote_age_hours"], 18.25)
        self.assertEqual(record["quote_age_excess_hours"], 10.25)
        self.assertEqual(record["no_fill_reason"], "spread_ask_bid_not_fillable_inside_filters")
        self.assertEqual(record["liquidity_reason"], "illiquid_quote")
        self.assertTrue(record["research_only"])
        self.assertTrue(record["non_promotable"])
        self.assertEqual(record["production_filter_action"], "preserve_filters_until_exact_replay_unlock")

    def test_scan_allows_auto_track_ignores_legacy_observation_only_playbooks(self):
        self.assertFalse(
            log_scan_picks._scan_allows_auto_track(
                {
                    "playbook": {"id": "quality90_debit55_canary", "observation_only": True},
                    "picks": [_make_pick("SPY", debit=5.0)],
                    "exposure_snapshot": {"portfolio_caps_enforced": True},
                }
            )
        )

    def test_scan_allows_auto_track_honors_env_kill_switch(self):
        with patch.dict("os.environ", {"OPTIONS_SCAN_AUTO_TRACK": "0"}):
            self.assertFalse(
                log_scan_picks._scan_allows_auto_track(
                    {
                        "playbook": {"id": "short_term", "observation_only": False},
                        "picks": [_make_pick("SPY", debit=5.0)],
                        "exposure_snapshot": {"portfolio_caps_enforced": True},
                    }
                )
            )

    def test_scan_allows_auto_track_requires_market_open(self):
        self.assertFalse(
            log_scan_picks._scan_allows_auto_track(
                {
                    "playbook": {"id": "swing"},
                    "market_open_at_run": False,
                    "picks": [_make_pick("SPY", debit=5.0)],
                }
            )
        )

    def test_print_scan_diagnostics_explains_no_pick_blockers(self):
        output = StringIO()
        with redirect_stdout(output):
            log_scan_picks._print_scan_diagnostics(
                {
                    "candidate_count": 2,
                    "returned_count": 0,
                    "playbook": {"id": "short_term", "label": "Short-Term"},
                    "scan_funnel": {
                        "raw_candidates": 2,
                        "returned_picks": 0,
                        "drop_counts": {"momentum": 8, "option_liquidity": 3},
                        "guardrail_counts": {"blocked": 2, "clear": 0},
                        "policy_counts": {"watch": 2},
                    },
                    "candidate_audit_picks": [
                        {
                            **_make_pick("MSFT", debit=5.0),
                            "guardrail_decision": "blocked",
                            "guardrail_reasons": ["Spread debit is above cap."],
                        }
                    ],
                }
            )

        text = output.getvalue()
        self.assertIn("playbook=short_term", text)
        self.assertIn("momentum=8", text)
        self.assertIn("blocked=2", text)
        self.assertIn("MSFT call", text)
        self.assertIn("Spread debit is above cap.", text)

    def test_main_rerun_replaces_same_day_rows_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            current_picks = [_make_pick("SPY", debit=5.0)]
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY", "QQQ"],
                scan_daily_top_trades=lambda **kwargs: list(current_picks),
            )

            def fake_supervised_scan(**kwargs):
                return {
                    "picks": list(current_picks),
                    "watch_picks": [_make_pick("WATCH", debit=1.0)],
                    "ranked_picks": [_make_pick("RAW", debit=2.0)],
                    "candidate_audit_picks": [
                        {
                            **_make_pick("BLOCKED", debit=3.0),
                            "guardrail_decision": "blocked",
                        }
                    ],
                    "policy_applied": True,
                    "policy_fail_closed": False,
                    "truth_lane": "archived_forward_daily",
                    "playbook": {"id": "short_term", "label": "Short Term"},
                }

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(
                    log_scan_picks,
                    "create_positions_repository",
                    return_value=_UnavailableRepository(),
                ),
                patch.object(log_scan_picks, "run_supervised_scan", side_effect=fake_supervised_scan) as run_supervised_scan,
                patch.object(
                    log_scan_picks,
                    "record_forward_snapshot",
                    return_value={"session_id": 123, "scan_picks_count": 1, "eligibility_status": "eligible"},
                ) as record_forward_snapshot,
                patch.dict(
                    sys.modules,
                    {
                        "market_data_service": fake_mds,
                        "options_chatbot": fake_oc,
                    },
                ),
            ):
                log_scan_picks.main()
                current_picks[:] = [_make_pick("QQQ", debit=7.5)]
                log_scan_picks.main()

            rows = log_scan_picks._load_log_rows(log_file=log_file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["scan_date"], "2026-04-14")
            self.assertEqual(rows[0]["ticker"], "QQQ")
            self.assertEqual(rows[0]["playbook_id"], "short_term")
            self.assertEqual(rows[0]["truth_lane"], "archived_forward_daily")
            self.assertTrue(rows[0]["policy_applied"])
            self.assertEqual(run_supervised_scan.call_count, 2)
            self.assertIs(run_supervised_scan.call_args.kwargs["scan_func"], fake_oc.scan_daily_top_trades)
            self.assertEqual(run_supervised_scan.call_args.kwargs["playbook_id"], log_scan_picks.SCAN_PLAYBOOK_FALLBACK_ID)
            self.assertFalse(run_supervised_scan.call_args.kwargs["use_recommended_policy"])
            self.assertTrue(run_supervised_scan.call_args.kwargs["enforce_portfolio_caps"])
            self.assertEqual(record_forward_snapshot.call_count, 2)
            latest_snapshot = record_forward_snapshot.call_args.kwargs["scan_snapshot"]
            self.assertEqual(latest_snapshot["picks"][0]["ticker"], "QQQ")
            self.assertEqual(latest_snapshot["candidate_audit_picks"][0]["ticker"], "BLOCKED")
            self.assertEqual(latest_snapshot["evidence_class"], "live_production")
            self.assertEqual(latest_snapshot["run_mode"], "scheduled_scan")

    def test_main_skips_logging_when_supervised_scan_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY"],
                scan_daily_top_trades=lambda **kwargs: [_make_pick("SPY", debit=5.0)],
            )

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(
                    log_scan_picks,
                    "create_positions_repository",
                    return_value=_UnavailableRepository(),
                ),
                patch.object(
                    log_scan_picks,
                    "run_supervised_scan",
                    return_value={
                        "picks": [_make_pick("SPY", debit=5.0)],
                        "policy_fail_closed": True,
                        "policy_error": "no authoritative policy",
                    },
                ),
                patch.dict(
                    sys.modules,
                    {
                        "market_data_service": fake_mds,
                        "options_chatbot": fake_oc,
                    },
                ),
            ):
                log_scan_picks.main()

            self.assertFalse(log_file.exists())

    def test_main_records_forward_snapshot_when_scan_returns_no_picks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY"],
                scan_daily_top_trades=lambda **kwargs: [],
            )

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(
                    log_scan_picks,
                    "create_positions_repository",
                    return_value=_UnavailableRepository(),
                ),
                patch.object(
                    log_scan_picks,
                    "run_supervised_scan",
                    return_value={
                        "picks": [],
                        "policy_applied": False,
                        "policy_fail_closed": False,
                        "truth_lane": "historical_imported_daily",
                        "playbook": {
                            "id": "quality90_debit55_canary",
                            "label": "Quality90 Debit55 Canary",
                            "forced_cohort_id": "quality90_debit55_canary",
                        },
                        "scan_funnel": {"raw_candidates": 8, "returned_picks": 0},
                    },
                ),
                patch.object(
                    log_scan_picks,
                    "record_forward_snapshot",
                    return_value={"session_id": 456, "scan_picks_count": 0, "eligibility_status": "eligible"},
                ) as record_forward_snapshot,
                patch.dict(
                    sys.modules,
                    {
                        "market_data_service": fake_mds,
                        "options_chatbot": fake_oc,
                    },
                ),
            ):
                log_scan_picks.main()

            self.assertFalse(log_file.exists())
            self.assertEqual(record_forward_snapshot.call_count, 1)
            snapshot = record_forward_snapshot.call_args.kwargs["scan_snapshot"]
            self.assertEqual(snapshot["picks"], [])
            self.assertEqual(snapshot["playbook"]["id"], "quality90_debit55_canary")
            self.assertEqual(snapshot["cohort_ids"], ["quality90_debit55_canary"])
            self.assertIn("quality90_debit55_canary", snapshot["cohort_funnels"])

    def test_main_returns_nonzero_when_no_pick_forward_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY"],
                scan_daily_top_trades=lambda **kwargs: [],
            )

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(log_scan_picks, "create_positions_repository", return_value=_UnavailableRepository()),
                patch.object(
                    log_scan_picks,
                    "run_supervised_scan",
                    return_value={
                        "picks": [],
                        "policy_applied": False,
                        "policy_fail_closed": False,
                        "truth_lane": "historical_imported_daily",
                        "playbook": {"id": "short_term", "label": "Short Term"},
                    },
                ),
                patch.object(log_scan_picks, "record_forward_snapshot", side_effect=RuntimeError("ledger down")),
                patch.dict(sys.modules, {"market_data_service": fake_mds, "options_chatbot": fake_oc}),
            ):
                result = log_scan_picks.main()

            self.assertEqual(result, 1)

    def test_main_reviews_open_positions_before_no_pick_scan_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            repository = _TrackingRepository()
            reviewed = [
                {
                    "id": 9,
                    "ticker": "SPY",
                    "status": "closed",
                    "exit_reason": "auto_sell_recommendation",
                }
            ]
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY"],
                scan_daily_top_trades=lambda **kwargs: [],
            )
            call_order: list[str] = []

            def fake_review(repo):
                call_order.append("review")
                self.assertIs(repo, repository)
                return reviewed

            def fake_supervised_scan(**kwargs):
                call_order.append("scan")
                return {
                    "picks": [],
                    "policy_applied": False,
                    "policy_fail_closed": False,
                    "truth_lane": "historical_imported_daily",
                    "playbook": {"id": "short_term", "label": "Short Term"},
                    "scan_funnel": {"raw_candidates": 0, "returned_picks": 0},
                }

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(
                    log_scan_picks,
                    "create_positions_repository",
                    return_value=repository,
                ),
                patch.object(log_scan_picks, "review_open_positions", side_effect=fake_review),
                patch.object(log_scan_picks, "run_supervised_scan", side_effect=fake_supervised_scan),
                patch.object(
                    log_scan_picks,
                    "record_forward_snapshot",
                    return_value={"session_id": 789, "scan_picks_count": 0, "eligibility_status": "eligible"},
                ) as record_forward_snapshot,
                patch.dict(
                    sys.modules,
                    {
                        "market_data_service": fake_mds,
                        "options_chatbot": fake_oc,
                    },
                ),
            ):
                log_scan_picks.main()

            self.assertEqual(call_order, ["review", "scan"])
            snapshot = record_forward_snapshot.call_args.kwargs["scan_snapshot"]
            self.assertEqual(record_forward_snapshot.call_args.kwargs["reviewed_positions"], reviewed)
            self.assertEqual(snapshot["picks"], [])

    def test_auto_track_rejects_non_proof_exact_contract_picks(self):
        repository = _TrackingRepository()
        pick = _make_pick("SPY", debit=5.0)
        pick.update(
            {
                "selection_source": "model_contract_fallback",
                "promotion_class": "research_candidate",
                "quote_time_et": "2026-04-14T11:00:00-04:00",
                "bid": 4.9,
                "ask": 5.1,
                "entry_execution_price": 5.0,
                "entry_execution_basis": "spread_mid",
            }
        )

        created, duplicates, skipped = log_scan_picks._auto_track_scan_picks(
            repository=repository,
            picks=[pick],
            filled_at="2026-04-14T11:00:00-04:00",
            scan_date="2026-04-14",
        )

        self.assertEqual((created, duplicates, skipped), (0, 0, 1))
        self.assertEqual(repository.created, [])

    def test_main_logs_and_tracks_eligible_auto_track_lane_pick(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            repository = _TrackingRepository()
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY", "QQQ"],
                scan_daily_top_trades=lambda **kwargs: [_make_pick("SPY", debit=5.0)],
                _market_is_open=lambda: True,
            )
            pick = _make_pick("SPY", debit=5.0)
            pick.update(
                {
                    "cohort_id": "short_term",
                    "contract_symbol": "SPY260515C00500000",
                    "short_contract_symbol": "SPY260515C00520000",
                    "selection_source": "live_chain_exact_contract",
                    "promotion_class": "promotable_exact_contract",
                    "options_data_source": "alpaca_opra",
                    "quote_time_et": "2026-04-14T11:00:00-04:00",
                    "quote_time_utc": "2026-04-14T15:00:00Z",
                    "entry_execution_price": 5.0,
                    "entry_execution_basis": "spread_ask_bid",
                    "entry_quote_snapshot": {
                        "captured_at_et": "2026-04-14T11:00:00-04:00",
                        "captured_at_utc": "2026-04-14T15:00:00Z",
                        "entry_execution_price": 5.0,
                        "entry_execution_basis": "spread_ask_bid",
                        "net_debit": 5.0,
                        "legs": [
                            {
                                "role": "long",
                                "contract_symbol": "SPY260515C00500000",
                                "strike": 500.0,
                                "bid": 6.0,
                                "ask": 6.1,
                            },
                            {
                                "role": "short",
                                "contract_symbol": "SPY260515C00520000",
                                "strike": 520.0,
                                "bid": 1.1,
                                "ask": 1.2,
                            },
                        ],
                    },
                }
            )

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(
                    log_scan_picks,
                    "create_positions_repository",
                    return_value=repository,
                ),
                patch.object(
                    log_scan_picks,
                    "run_supervised_scan",
                    return_value={
                        "picks": [pick],
                        "policy_applied": False,
                        "policy_fail_closed": False,
                        "truth_lane": "historical_imported_daily",
                        "exposure_snapshot": {"portfolio_caps_enforced": True},
                        "playbook": {
                            "id": "short_term",
                            "label": "Short-Term",
                        },
                    },
                ),
                patch.object(log_scan_picks, "review_open_positions", return_value=[]) as review_open_positions,
                patch.object(
                    log_scan_picks,
                    "record_forward_snapshot",
                    return_value={
                        "session_id": 123,
                        "scan_picks_count": 1,
                        "eligibility_status": "eligible",
                        "run_id": "scheduled_scan:test",
                        "recorded_at_utc": "2026-04-14T17:00:00Z",
                    },
                ) as record_forward_snapshot,
                patch.dict(
                    sys.modules,
                    {
                        "market_data_service": fake_mds,
                        "options_chatbot": fake_oc,
                    },
                ),
            ):
                log_scan_picks.main()

            rows = log_scan_picks._load_log_rows(log_file=log_file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["playbook_id"], "short_term")
            fill_rows = log_scan_picks._load_log_rows(log_file=log_dir / "fill_attempts.jsonl")
            self.assertEqual(len(fill_rows), 1)
            self.assertEqual(fill_rows[0]["fill_status"], "auto_tracked")
            self.assertEqual(fill_rows[0]["fill_outcome"], "paper_fill_recorded")
            self.assertEqual(fill_rows[0]["attempted_limit_price"], 5.0)
            self.assertEqual(fill_rows[0]["auto_track_position_id"], 1)
            self.assertEqual(len(repository.created), 1)
            self.assertEqual(repository.created[0]["ticker"], "SPY")
            self.assertTrue(repository.created[0]["proof_eligible"])
            self.assertEqual(repository.created[0]["source_scan_session_id"], 123)
            self.assertEqual(repository.created[0]["source_scan_run_id"], "scheduled_scan:test")
            self.assertEqual(
                repository.created[0]["source_pick_snapshot"]["source_scan_recorded_at_utc"],
                "2026-04-14T17:00:00Z",
            )
            self.assertEqual(review_open_positions.call_count, 3)
            review_open_positions.assert_any_call(repository, position_ids=[1])
            self.assertEqual(record_forward_snapshot.call_count, 1)

    def test_main_returns_nonzero_when_pick_forward_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "scan_picks.jsonl"
            fake_mds = types.SimpleNamespace(_MEMORY_CACHE={})
            fake_oc = types.SimpleNamespace(
                DEFAULT_WATCHLIST=["SPY"],
                scan_daily_top_trades=lambda **kwargs: [_make_pick("SPY", debit=5.0)],
            )

            with (
                patch.object(log_scan_picks, "LOG_DIR", log_dir),
                patch.object(log_scan_picks, "LOG_FILE", log_file),
                patch.object(log_scan_picks, "datetime", _WeekdayDateTime),
                patch.object(log_scan_picks, "load_local_env"),
                patch.object(log_scan_picks, "create_positions_repository", return_value=_UnavailableRepository()),
                patch.object(
                    log_scan_picks,
                    "run_supervised_scan",
                    return_value={
                        "picks": [_make_pick("SPY", debit=5.0)],
                        "policy_applied": False,
                        "policy_fail_closed": False,
                        "truth_lane": "historical_imported_daily",
                        "playbook": {"id": "short_term", "label": "Short Term"},
                    },
                ),
                patch.object(log_scan_picks, "record_forward_snapshot", side_effect=RuntimeError("ledger down")),
                patch.dict(sys.modules, {"market_data_service": fake_mds, "options_chatbot": fake_oc}),
            ):
                result = log_scan_picks.main()

            self.assertEqual(result, 1)

    def test_backfills_position_scan_provenance_after_ledger_record(self):
        repo = _FakeRepository()
        pick = _make_pick("SPY", debit=5.0)

        updated = log_scan_picks._backfill_position_scan_provenance(
            repository=repo,
            picks=[pick],
            tracked_links=[(7, 1)],
            ledger_result={
                "session_id": 321,
                "run_id": "scheduled_scan:test",
                "recorded_at_utc": "2026-04-14T17:00:00Z",
            },
        )

        self.assertEqual(updated, 1)
        self.assertEqual(repo.updates[0][0], 7)
        update = repo.updates[0][1]
        self.assertEqual(update["source_scan_session_id"], 321)
        self.assertEqual(update["source_scan_event_key"], "rank_1")
        self.assertEqual(update["source_scan_run_id"], "scheduled_scan:test")
        self.assertEqual(
            update["source_pick_snapshot"]["source_scan_recorded_at_utc"],
            "2026-04-14T17:00:00Z",
        )


if __name__ == "__main__":
    unittest.main()
