from __future__ import annotations

import json
import tempfile
import unittest
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from scripts import log_scan_picks
from scripts import build_regular_options_filtered_forward_paper_shadow_tracker as tracker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")


def _conditions_hash(conditions: list[dict]) -> str:
    payload = json.dumps(conditions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


def _audit() -> dict:
    return {
        "report_id": "regular_options_historical_filtered_simulated_forward_audit",
        "status": "historical_filtered_simulated_forward_audit_passed",
        "generated_at_utc": "2026-06-30T14:00:00Z",
        "accepted_historical_filtered_audit": True,
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "filter_source": {
            "source_report_id": "regular_options_historical_profitability_filter_iteration",
            "source_status": "historical_profitability_filter_iteration_candidate_found",
            "filter_id": "fixture_filter",
            "description": "Fixture filter.",
            "conditions": [
                {"field": "ticker", "op": "in", "value": ["AAPL", "NEM"]},
                {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
            ],
        },
        "metrics": {
            "simulated_forward_audit": {
                "exact_trade_count": 65,
                "profit_factor": 2.47,
                "avg_pnl_pct": 29.58,
                "bootstrap": {"pf_lb_5pct": 1.54},
            }
        },
    }


def _contract(audit: dict | None = None, *, conditions: list[dict] | None = None) -> dict:
    source = audit or _audit()
    contract_conditions = conditions if conditions is not None else source["filter_source"]["conditions"]
    return {
        "report_id": "regular_options_frozen_filtered_policy",
        "schema_version": 1,
        "policy_id": "historical_filtered_candidate_policy_v1",
        "frozen_at_utc": "2026-06-30T05:03:45Z",
        "filter_id": "fixture_filter",
        "description": "Fixture filter.",
        "conditions": contract_conditions,
        "conditions_sha256": _conditions_hash(contract_conditions),
        "tracking_start_at_utc": "2026-06-30T14:00:00Z",
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }


def _bar_contract(*, min_rows: int = 30, draws: int = 100) -> dict:
    return {
        "report_id": "regular_options_filtered_forward_evidence_bar",
        "schema_version": 1,
        "bar_id": "regular_options_filtered_forward_evidence_bar_v1",
        "policy_id": "historical_filtered_candidate_policy_v1",
        "approval_authority": False,
        "requirements": {
            "min_completed_forward_paper_shadow_rows": min_rows,
            "min_ticker_week_clusters": 8,
            "min_calendar_months_with_rows": 3,
            "min_percent_cluster_pf_lb_5pct": 1.0,
            "min_usd_cluster_pf_lb_5pct": 1.0,
            "min_total_net_pnl_usd_exclusive": 0.0,
            "max_fixture_rows": 0,
            "bootstrap_draws": draws,
            "evaluation_may_not_occur_before_min_completed_rows": True,
        },
    }


def _scan_task_health() -> dict:
    return {
        "report_id": "regular_options_strict_forward_scan_task_health",
        "status": "scan_tasks_ready_for_next_market_window",
        "expected": {
            "tasks": {
                "\\OptionsScanPicks": {"start_time": "11:00:00 AM"},
                "\\OptionsScanPicksSafetyNet": {"start_time": "11:30:00 AM"},
            }
        },
    }


def _entry_fields(ticker: str = "AAPL", index: int = 1) -> dict:
    return {
        "scan_run_id": f"scan-{ticker}-{index}",
        "expiry": "2026-08-21",
        "dte": 52,
        "contract_symbol": f"{ticker}260821C00200000",
        "short_contract_symbol": f"{ticker}260821C00210000",
        "long_strike": 200,
        "short_strike": 210,
        "quote_source": "alpaca_opra",
        "quote_timestamp_utc": "2026-06-30T15:00:00Z",
        "spread_liquidity": {"long_ask": 4.2, "long_bid": 4.0, "short_bid": 1.0, "short_ask": 1.1},
        "net_debit": 3.2,
    }


class RegularOptionsFilteredForwardPaperShadowTrackerTests(unittest.TestCase):
    def test_tracks_matching_future_scan_rows_with_computed_prior_20(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "AAPL",
                        "playbook_id": "bullish_pullback_observation",
                        "strategy_type": "vertical_spread",
                        **_entry_fields("AAPL"),
                    },
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "MSFT",
                        "playbook_id": "bullish_pullback_observation",
                        "strategy_type": "vertical_spread",
                    },
                ],
            )
            _write_jsonl(
                daily_path,
                [
                    {
                        "symbol": "AAPL",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 12.5,
                    },
                    {
                        "symbol": "MSFT",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 20.0,
                    },
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                generated_at_utc="2026-06-30T15:00:00Z",
            )

        self.assertEqual(report["status"], "filtered_forward_paper_shadow_tracking_active")
        self.assertEqual(report["tracking_start_date"], "2026-06-30")
        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)
        self.assertEqual(report["candidate_rows"][0]["ticker"], "AAPL")
        self.assertEqual(report["candidate_rows"][0]["tracking_start_date"], "2026-06-30")
        self.assertEqual(report["candidate_rows"][0]["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["candidate_rows"][0]["evidence_bucket"], "forward_paper_shadow")
        self.assertFalse(report["candidate_rows"][0]["live_trade"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["scanner_policy_changed"])

    def test_logged_forward_scan_row_shape_evaluates_without_daily_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            scan_row = log_scan_picks._build_log_record(
                {
                    "ticker": "AAPL",
                    "direction": "call",
                    "strategy_type": "vertical_spread",
                    "expiry": "2026-08-21",
                    "dte": 52,
                    "strike": 200,
                    "short_strike": 210,
                    "net_debit": 3.2,
                    "signal_variant": "pullback_uptrend",
                    "signal_family": "bullish_pullback",
                    "signal_ret20": 12.5,
                    "contract_symbol": "AAPL260821C00200000",
                    "short_contract_symbol": "AAPL260821C00210000",
                    "quote_source": "alpaca_opra",
                    "quote_timestamp_utc": "2026-06-30T15:00:00Z",
                    "spread_liquidity": {"long_ask": 4.2, "long_bid": 4.0, "short_bid": 1.0, "short_ask": 1.1},
                    },
                run_at=datetime(2026, 6, 30, 15, 0, 0, tzinfo=UTC),
                scan_result={"playbook": {"id": "bullish_pullback_observation"}},
            )
            _write_jsonl(scan_path, [scan_row])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(report["status"], "filtered_forward_paper_shadow_tracking_active")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)
        self.assertEqual(report["forward_tracking"]["rejected_counts"], {})
        self.assertEqual(report["candidate_rows"][0]["prior_20_trading_day_return_pct"], 12.5)
        self.assertEqual(report["candidate_rows"][0]["prior_20_trading_day_return_source"], "scan_row")

    def test_uses_contract_when_latest_filtered_audit_is_doctored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = _audit()
            audit["status"] = "blocked_historical_filtered_simulated_forward_audit"
            audit["filter_source"]["conditions"] = [
                {"field": "ticker", "op": "in", "value": ["MSFT"]},
                {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 999.0},
            ]
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, audit)
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "AAPL",
                        "strategy_type": "vertical_spread",
                        **_entry_fields("AAPL"),
                    }
                ],
            )
            _write_jsonl(
                daily_path,
                [
                    {
                        "symbol": "AAPL",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 12.5,
                    }
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                generated_at_utc="2026-06-30T15:00:00Z",
            )

        self.assertEqual(report["status"], "filtered_forward_paper_shadow_tracking_active")
        self.assertEqual(report["policy_drift_status"], "latest_filtered_audit_diverged_from_frozen_contract")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)
        self.assertEqual(report["candidate_rows"][0]["ticker"], "AAPL")

    def test_rejects_scan_rows_before_tracking_start_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-29",
                        "ticker": "AAPL",
                        "strategy_type": "vertical_spread",
                    }
                ],
            )
            _write_jsonl(
                daily_path,
                [
                    {
                        "symbol": "AAPL",
                        "input_date_et": "2026-06-29",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 12.5,
                    }
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(report["status"], "filtered_forward_paper_shadow_tracking_active")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)
        self.assertEqual(report["forward_tracking"]["rejected_counts"], {"pre_tracking_start_date": 1})

    def test_blocks_when_policy_contract_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_jsonl(scan_path, [])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=root / "missing-contract.json",
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(report["status"], "blocked_filtered_forward_paper_shadow_tracker")
        self.assertIn("frozen_filtered_policy_contract_missing", report["blockers"])
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)

    def test_blocks_when_policy_contract_hash_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            contract = _contract()
            contract["conditions_sha256"] = "bad"
            _write_json(audit_path, _audit())
            _write_json(contract_path, contract)
            _write_jsonl(scan_path, [])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(report["status"], "blocked_filtered_forward_paper_shadow_tracker")
        self.assertIn("frozen_filtered_policy_hash_mismatch", report["blockers"])
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)

    def test_contract_tracking_timestamp_overrides_explicit_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(scan_path, [])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                tracking_start_date="2099-01-01",
                tracking_start_at_utc="2099-01-01T00:00:00Z",
            )

        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["tracking_start_date"], "2026-06-30")
        self.assertEqual(report["tracking_start_source"], "frozen_policy_contract")

    def test_rejects_same_day_rows_before_tracking_start_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T13:00:00Z",
                        "ticker": "AAPL",
                        "strategy_type": "vertical_spread",
                    },
                    {
                        "scan_date": "2026-06-30",
                        "ticker": "NEM",
                        "strategy_type": "vertical_spread",
                    },
                ],
            )
            _write_jsonl(
                daily_path,
                [
                    {
                        "symbol": "AAPL",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 12.5,
                    },
                    {
                        "symbol": "NEM",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 15.0,
                    },
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(report["status"], "filtered_forward_paper_shadow_tracking_active")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)
        self.assertEqual(
            report["forward_tracking"]["rejected_counts"],
            {"missing_post_tracking_timestamp": 1, "pre_tracking_start_timestamp": 1},
        )

    def test_previous_tracker_artifacts_keep_start_timestamp_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = _audit()
            audit["generated_at_utc"] = "2026-06-30T16:00:00Z"
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            tracker_dir = root / "tracker"
            _write_json(audit_path, audit)
            contract = _contract(audit)
            del contract["tracking_start_at_utc"]
            _write_json(contract_path, contract)
            _write_json(
                tracker_dir / "latest.json",
                {
                    "report_id": tracker.REPORT_ID,
                    "status": "filtered_forward_paper_shadow_tracking_active",
                    "tracking_policy_id": tracker.POLICY_ID,
                    "tracking_start_at_utc": "2026-06-30T14:00:00Z",
                    "generated_at_utc": "2026-06-30T14:05:00Z",
                },
            )
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "AAPL",
                        "strategy_type": "vertical_spread",
                        **_entry_fields("AAPL"),
                    }
                ],
            )
            _write_jsonl(
                daily_path,
                [
                    {
                        "symbol": "AAPL",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 12.5,
                    }
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                previous_tracker_dir=tracker_dir,
            )

        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["tracking_start_source"], "previous_tracker_artifacts")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)

    def test_matched_row_log_append_is_idempotent_and_missing_provenance_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            matched_log = root / "matched_rows.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "AAPL",
                        "strategy_type": "vertical_spread",
                        "signal_evidence": {"prior_20_trading_day_return_pct": 12.5},
                        **_entry_fields("AAPL"),
                    },
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": "2026-06-30T15:00:00Z",
                        "ticker": "NEM",
                        "strategy_type": "vertical_spread",
                        "signal_evidence": {"prior_20_trading_day_return_pct": 12.5},
                    },
                ],
            )
            _write_jsonl(daily_path, [])

            first = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            second = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            log_rows = [json.loads(line) for line in matched_log.read_text(encoding="utf8").splitlines() if line.strip()]

        self.assertEqual(first["forward_tracking"]["entry_rows_appended_count"], 1)
        self.assertEqual(second["forward_tracking"]["entry_rows_appended_count"], 0)
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(first["forward_tracking"]["matched_but_unappendable_missing_entry_provenance_count"], 1)
        self.assertIn("missing_long_contract_symbol", first["forward_tracking"]["matched_but_unappendable_counts"])
        self.assertEqual(first["matched_but_unappendable_rows"][0]["status"], "matched_but_unappendable_missing_entry_provenance")

    def test_same_day_repeated_sessions_append_one_daily_signal_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            matched_log = root / "matched_rows.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(
                scan_path,
                [
                    {
                        "scan_date": "2026-06-30",
                        "logged_at": f"2026-06-30T15:0{index}:00Z",
                        "ticker": "AAPL",
                        "direction": "call",
                        "strategy_type": "vertical_spread",
                        "signal_evidence": {"prior_20_trading_day_return_pct": 12.5},
                        **_entry_fields("AAPL", index),
                    }
                    for index in range(1, 4)
                ],
            )
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            log_rows = [json.loads(line) for line in matched_log.read_text(encoding="utf8").splitlines() if line.strip()]

        self.assertEqual(report["forward_tracking"]["raw_matched_scan_row_count"], 3)
        self.assertEqual(report["forward_tracking"]["daily_signal_matched_row_count"], 1)
        self.assertEqual(report["forward_tracking"]["entry_rows_appended_count"], 1)
        self.assertEqual(report["forward_tracking"]["same_day_signal_duplicate_matches_suppressed_count"], 2)
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0]["source_scan_run_id"], "scan-AAPL-1")
        self.assertEqual(log_rows[0]["long_contract_symbol"], "AAPL260821C00200000")
        self.assertEqual(log_rows[0]["candidate_identity_schema"], tracker.MATCHED_ROW_IDENTITY_SCHEMA)

    def test_nonempty_pre_v2_matched_log_blocks_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            matched_log = root / "matched_rows.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_jsonl(scan_path, [])
            _write_jsonl(daily_path, [])
            _write_jsonl(matched_log, [{"candidate_id": "old", "scan_date": "2026-06-30", "ticker": "AAPL"}])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )

        self.assertEqual(report["status"], "blocked_filtered_forward_paper_shadow_tracker")
        self.assertIn("matched_rows_log_nonempty_before_daily_signal_identity_upgrade", report["blockers"])

    def test_forward_evidence_bar_reports_incomplete_and_complete_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            bar_path = root / "bar.json"
            scan_health_path = root / "scan-health.json"
            scan_path = root / "scan.jsonl"
            matched_log = root / "matched_rows.jsonl"
            daily_path = root / "daily.jsonl"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_json(bar_path, _bar_contract())
            _write_json(scan_health_path, _scan_task_health())
            rows: list[dict] = []
            dates = [
                "2026-07-06",
                "2026-07-07",
                "2026-07-13",
                "2026-07-14",
                "2026-08-03",
                "2026-08-04",
                "2026-09-01",
                "2026-09-02",
            ]
            for index, date in enumerate(dates):
                ticker = "AAPL" if index % 2 == 0 else "NEM"
                for offset, pct in enumerate([10.0, 9.0, 8.0, -1.0]):
                    rows.append(
                        {
                            "scan_date": date,
                            "logged_at": f"{date}T16:00:00Z",
                            "ticker": ticker,
                            "candidate_id": f"{ticker}-{index}-{offset}",
                            "candidate_identity_schema": tracker.MATCHED_ROW_IDENTITY_SCHEMA,
                            "strategy_type": "vertical_spread",
                            "signal_evidence": {"prior_20_trading_day_return_pct": 12.5},
                            "tracking_state": "forward_paper_shadow_completed",
                            "realized_pnl_status": "realized_pnl_available",
                            "net_pnl_pct": pct,
                            "net_pnl_usd": 100.0 if pct > 0 else -10.0,
                            **_entry_fields(ticker, index * 10 + offset),
                            "tracking_state": "forward_paper_shadow_completed",
                            "realized_pnl_status": "completed_exact_exit",
                        }
                    )
            _write_jsonl(scan_path, [])
            _write_jsonl(matched_log, rows[:29])
            _write_jsonl(daily_path, [])

            incomplete = tracker.build_report(
                policy_contract_path=contract_path,
                forward_evidence_bar_contract_path=bar_path,
                scan_task_health_path=scan_health_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
            )
            _write_jsonl(matched_log, rows)
            complete = tracker.build_report(
                policy_contract_path=contract_path,
                forward_evidence_bar_contract_path=bar_path,
                scan_task_health_path=scan_health_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
            )
            fixture_rows = list(rows)
            fixture_rows[0] = {**fixture_rows[0], "is_fixture": True}
            _write_jsonl(matched_log, fixture_rows)
            fixture_blocked = tracker.build_report(
                policy_contract_path=contract_path,
                forward_evidence_bar_contract_path=bar_path,
                scan_task_health_path=scan_health_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
            )

        self.assertEqual(incomplete["forward_evidence_bar"]["status"], "waiting_for_min_completed_forward_rows")
        self.assertFalse(incomplete["forward_evidence_bar"]["evaluation_permitted"])
        self.assertIsNone(incomplete["forward_evidence_bar"]["percent_cluster_bootstrap"])
        self.assertFalse(incomplete["approval_authority"])
        self.assertEqual(complete["forward_evidence_bar"]["completed_forward_rows"], 32)
        self.assertTrue(complete["forward_evidence_bar"]["evaluation_permitted"])
        self.assertTrue(complete["forward_evidence_bar"]["criteria_met_reporting_only"])
        self.assertFalse(complete["approval_authority"])
        self.assertFalse(complete["forward_evidence_bar"]["approval_authority"])
        self.assertEqual(
            complete["parity_disclosure"]["forward_scheduled_session_times"]["\\OptionsScanPicks"],
            "11:00:00 AM",
        )
        self.assertEqual(fixture_blocked["forward_evidence_bar"]["completed_forward_rows"], 32)
        self.assertTrue(fixture_blocked["forward_evidence_bar"]["evaluation_permitted"])
        self.assertEqual(fixture_blocked["forward_evidence_bar"]["fixture_row_count"], 1)
        self.assertFalse(fixture_blocked["forward_evidence_bar"]["checks"]["fixture_rows"])
        self.assertFalse(fixture_blocked["forward_evidence_bar"]["criteria_met_reporting_only"])
        self.assertEqual(fixture_blocked["forward_evidence_bar"]["status"], "forward_evidence_bar_criteria_not_met")

    def test_write_outputs_creates_latest_docs_and_candidate_jsonl(self) -> None:
        report = {
            "report_id": tracker.REPORT_ID,
            "status": "filtered_forward_paper_shadow_tracking_active",
            "tracking_policy_id": tracker.POLICY_ID,
            "tracking_start_date": "2026-06-30",
            "tracking_start_at_utc": "2026-06-30T14:00:00Z",
            "tracking_start_source": "filtered_audit_timestamp",
            "frozen_filter": {"filter_id": "fixture", "conditions_text": "ticker in AAPL"},
            "historical_audit_context": {
                "status": "historical_filtered_simulated_forward_audit_passed",
                "audit_exact_trade_count": 65,
                "audit_profit_factor": 2.47,
                "audit_pf_lb_5pct": 1.54,
                "historical_rows_are_forward_proof": False,
            },
            "forward_tracking": {
                "source_scan_row_count": 1,
                "tracking_start_date": "2026-06-30",
                "tracking_start_at_utc": "2026-06-30T14:00:00Z",
                "tracking_start_source": "filtered_audit_timestamp",
                "evaluated_scan_row_count": 1,
                "matched_candidate_count": 1,
                "open_candidate_count": 1,
                "completed_candidate_count": 0,
                "rejected_counts": {},
            },
            "forward_evidence_bar": {
                "status": "waiting_for_min_completed_forward_rows",
                "bar_id": "fixture_bar",
                "completed_forward_rows": 0,
                "required_completed_forward_rows": 30,
                "ticker_week_cluster_count": 0,
                "required_ticker_week_clusters": 8,
                "calendar_month_count": 0,
                "required_calendar_months": 3,
                "fixture_row_count": 0,
                "max_fixture_rows": 0,
                "evaluation_permitted": False,
                "criteria_met_reporting_only": False,
                "approval_authority": False,
                "percent_cluster_bootstrap": None,
                "usd_cluster_bootstrap": None,
                "total_net_pnl_usd": None,
            },
            "parity_disclosure": {
                "historical_materializer_entry_window_et": "10:10-10:25",
                "historical_materializer": "deterministic_local_pit_candidate_materializer_v1",
                "forward_source": "production_scan_sessions",
                "forward_scheduled_session_times": {},
                "forward_results_are_new_distribution": True,
                "expected_match_rate_note": "fixture note",
            },
            "candidate_rows": [{"candidate_id": "abc", "ticker": "AAPL"}],
            "blockers": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = tracker.write_outputs(
                report,
                output_dir=root / "out",
                candidates_jsonl=root / "candidates.jsonl",
                docs_report=root / "doc.md",
            )

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "candidates.jsonl").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertIn("candidate_rows_jsonl", artifacts)


if __name__ == "__main__":
    unittest.main()
