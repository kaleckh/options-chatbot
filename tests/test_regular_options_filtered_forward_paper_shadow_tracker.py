from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import hashlib
from datetime import UTC, date, datetime, time
from pathlib import Path
from unittest.mock import patch

from scripts import log_scan_picks
from scripts import (
    build_regular_options_filtered_forward_paper_shadow_tracker as tracker,
)
from scripts import (
    capture_regular_options_filtered_forward_exit_evidence as exit_capture,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")


def _write_authoritative_scan_event(
    path: Path,
    *,
    entry: dict,
    duplicate: bool = False,
    session_overrides: dict | None = None,
    payload_overrides: dict | None = None,
    event_overrides: dict | None = None,
    initialize: bool = True,
) -> None:
    source = dict(entry["source_row"])
    source.update(payload_overrides or {})
    session = {
        "recorded_at_utc": entry["source_scan_recorded_at_utc"],
        "source_label": "scheduled_scan",
        "playbook": entry["lane_id"],
        "run_id": entry["source_scan_run_id"],
        "run_mode": "scheduled_scan",
        "evidence_class": "live_production",
        "is_fixture": 0,
    }
    session.update(session_overrides or {})
    event = {
        "run_id": entry["source_scan_run_id"],
        "run_mode": "scheduled_scan",
        "evidence_class": "live_production",
        "is_fixture": 0,
    }
    event.update(event_overrides or {})
    connection = sqlite3.connect(path)
    try:
        if initialize:
            connection.executescript(
                """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT NOT NULL,
                source_label TEXT NOT NULL,
                playbook TEXT,
                run_id TEXT,
                run_mode TEXT,
                evidence_class TEXT,
                is_fixture INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE forward_events (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                event_key TEXT NOT NULL,
                run_id TEXT,
                run_mode TEXT,
                evidence_class TEXT,
                is_fixture INTEGER,
                payload_json TEXT
            );
            """
            )
        connection.execute(
            "INSERT INTO forward_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["source_scan_session_id"],
                session["recorded_at_utc"],
                session["source_label"],
                session["playbook"],
                session["run_id"],
                session["run_mode"],
                session["evidence_class"],
                session["is_fixture"],
            ),
        )
        rows = 2 if duplicate else 1
        next_event_id = int(
            connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM forward_events"
            ).fetchone()[0]
        )
        for event_id in range(next_event_id, next_event_id + rows):
            connection.execute(
                "INSERT INTO forward_events VALUES (?, ?, 'scan_pick', ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    entry["source_scan_session_id"],
                    entry["source_scan_event_key"],
                    event["run_id"],
                    event["run_mode"],
                    event["evidence_class"],
                    event["is_fixture"],
                    json.dumps(source),
                ),
            )
        connection.commit()
    finally:
        connection.close()


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
                {
                    "field": "signal_evidence.prior_20_trading_day_return_pct",
                    "op": "gte",
                    "value": 10.0,
                },
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


def _contract(
    audit: dict | None = None, *, conditions: list[dict] | None = None
) -> dict:
    source = audit or _audit()
    contract_conditions = (
        conditions if conditions is not None else source["filter_source"]["conditions"]
    )
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
        "generated_at_utc": "2026-07-08T18:05:52Z",
        "blockers": [],
        "config_blockers": [],
        "runtime_blockers": [],
        "expected": {
            "tasks": {
                "\\OptionsScanPicks": {"start_time": "11:00:00 AM"},
                "\\OptionsScanPicksSafetyNet": {"start_time": "11:30:00 AM"},
            }
        },
    }


def _ready_scan_task_health_path(root: Path) -> Path:
    path = root / "ready-scan-task-health.json"
    _write_json(path, _scan_task_health())
    return path


def _entry_fields(ticker: str = "AAPL", index: int = 1) -> dict:
    return {
        "scan_run_id": f"scan-{ticker}-{index}",
        "source_scan_session_id": 1000 + index,
        "source_scan_event_key": f"bullish_pullback_observation:rank_{index}",
        "source_scan_run_id": f"scan-{ticker}-{index}",
        "source_scan_recorded_at_utc": "2026-06-30T15:01:00Z",
        "scan_host": "TESTHOST",
        "scan_commit_sha": "1" * 40,
        "scan_branch": "test",
        "_source_scan_picks_sha256": "2" * 64,
        "_scan_task_health_sha256": "3" * 64,
        "_scan_task_health_status": tracker.READY_SCAN_TASK_HEALTH_STATUS,
        "_scan_task_health_generated_at_utc": "2026-12-31T23:59:59Z",
        "direction": "call",
        "playbook_id": "bullish_pullback_observation",
        "expiry": "2026-08-21",
        "dte": 52,
        "contract_symbol": f"{ticker}260821C00200000",
        "short_contract_symbol": f"{ticker}260821C00210000",
        "long_strike": 200,
        "short_strike": 210,
        "quote_source": "alpaca_opra",
        "quote_timestamp_utc": "2026-06-30T15:00:00Z",
        "long_entry_quote_timestamp_utc": "2026-06-30T15:00:00Z",
        "short_entry_quote_timestamp_utc": "2026-06-30T15:00:00Z",
        "decision_timestamp_utc": "2026-06-30T15:00:00Z",
        "spread_liquidity": {
            "long_ask": 4.2,
            "long_bid": 4.0,
            "short_bid": 1.0,
            "short_ask": 1.1,
        },
        "net_debit": 3.2,
        "signal_evidence": {
            "prior_20_trading_day_return_pct": 12.5,
            "prior_20_trading_day_return_source": "fixture_point_in_time_source",
            "known_at_utc": "2026-06-30T14:55:00Z",
            "source_ref": "fixture://signal/AAPL/2026-06-30",
            "source_row_hash": "4" * 64,
        },
    }


def _completion_pair(
    scan_date: str,
    *,
    ticker: str = "AAPL",
    index: int = 0,
    winning: bool = True,
    is_fixture: bool = False,
) -> tuple[dict, dict]:
    parsed_date = date.fromisoformat(scan_date)
    expiry = date(2026, 12, 18)
    expiry_token = expiry.strftime("%y%m%d")
    source = {
        "scan_date": scan_date,
        "logged_at": f"{scan_date}T15:00:00Z",
        "ticker": ticker,
        "direction": f"call_{index}",
        "strategy_type": "vertical_spread",
        "lane_id": "bullish_pullback_observation",
        "playbook_id": "bullish_pullback_observation",
        "expiry": expiry.isoformat(),
        "dte": (expiry - parsed_date).days,
        "contract_symbol": f"{ticker}{expiry_token}C00200000",
        "short_contract_symbol": f"{ticker}{expiry_token}C00210000",
        "quote_source": "alpaca_opra",
        "selection_source": "live_chain_exact_contract",
        "entry_execution_basis": "spread_ask_bid",
        "quote_freshness_status": "fresh",
        "quote_timestamp_utc": f"{scan_date}T15:00:00Z",
        "long_entry_quote_timestamp_utc": f"{scan_date}T15:00:00Z",
        "short_entry_quote_timestamp_utc": f"{scan_date}T15:00:00Z",
        "decision_timestamp_utc": f"{scan_date}T15:00:00Z",
        "spread_liquidity": {
            "long_ask": 4.2,
            "long_bid": 4.0,
            "short_bid": 1.0,
            "short_ask": 1.1,
        },
        "net_debit": 3.2,
        "source_scan_session_id": 77 + index,
        "source_scan_event_key": f"bullish_pullback_observation:rank_{index + 1}",
        "source_scan_run_id": f"scheduled_scan:{scan_date}:{ticker}:{index}",
        "source_scan_recorded_at_utc": f"{scan_date}T15:01:00Z",
        "scan_run_id": f"scan-{ticker}-{index}",
        "scan_host": "TESTHOST",
        "scan_commit_sha": "1" * 40,
        "scan_branch": "test",
        "_source_scan_picks_sha256": "2" * 64,
        "_scan_task_health_sha256": "3" * 64,
        "_scan_task_health_status": tracker.READY_SCAN_TASK_HEALTH_STATUS,
        "_scan_task_health_generated_at_utc": "2026-12-31T23:59:59Z",
        "signal_evidence": {
            "prior_20_trading_day_return_pct": 12.5,
            "prior_20_trading_day_return_source": "fixture_point_in_time_source",
            "known_at_utc": f"{scan_date}T14:55:00Z",
            "source_ref": f"fixture://signal/{ticker}/{scan_date}",
            "source_row_hash": "4" * 64,
        },
        "entry_quote_snapshot": {
            "quote_source": "alpaca_opra",
            "quote_freshness_status": "fresh",
            "legs": [
                {
                    "role": "long",
                    "contract_symbol": f"{ticker}{expiry_token}C00200000",
                    "bid": 4.0,
                    "ask": 4.2,
                    "quote_timestamp_utc": f"{scan_date}T15:00:00Z",
                },
                {
                    "role": "short",
                    "contract_symbol": f"{ticker}{expiry_token}C00210000",
                    "bid": 1.0,
                    "ask": 1.1,
                    "quote_timestamp_utc": f"{scan_date}T15:00:00Z",
                },
            ],
        },
    }
    entry, reasons = tracker._matched_entry_log_row(
        source,
        tracking_start_date=scan_date,
        tracking_start_at_utc=f"{scan_date}T00:00:00Z",
    )
    if reasons:
        raise AssertionError(reasons)
    exit_day = date.fromisoformat(str(entry["policy_exit_date"]))
    exit_timestamp = datetime.combine(
        exit_day, time(15, 55), tzinfo=tracker.EASTERN
    ).astimezone(UTC)
    exit_timestamp_utc = tracker._utc_iso(exit_timestamp)
    exit_value = 4.2 if winning else 3.1
    long_bid = exit_value + 1.0
    completion = exit_capture._completion_row(
        entry,
        {
            "source_label": "thetadata_opra_nbbo_1m",
            "long_contract_symbol": entry["long_contract_symbol"],
            "short_contract_symbol": entry["short_contract_symbol"],
            "timestamp_utc": exit_timestamp_utc,
            "long_timestamp_utc": exit_timestamp_utc,
            "short_timestamp_utc": exit_timestamp_utc,
            "long_quote_minute_et": 955,
            "short_quote_minute_et": 955,
            "long_bid": long_bid,
            "long_ask": long_bid + 0.1,
            "short_bid": 0.9,
            "short_ask": 1.0,
            "basis": "trusted_thetadata_intraday_options_history_db_read_only",
            "exit_quote_pair_synchronized": True,
        },
        exit_date=exit_day,
    )
    if completion is None:
        raise AssertionError("valid completion fixture was rejected")
    completion["is_fixture"] = is_fixture
    return entry, completion


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
                        "known_at": "2026-06-30T14:55:00Z",
                        "tradable_after": "2026-06-30T15:00:00Z",
                        "decision_timestamp_utc": "2026-06-30T15:00:00Z",
                        "entry_quote_timestamp_utc": "2026-06-30T15:00:00Z",
                        "long_entry_quote_timestamp_utc": "2026-06-30T15:00:00Z",
                        "short_entry_quote_timestamp_utc": "2026-06-30T15:00:00Z",
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
                        "known_at_utc": "2026-06-30T14:55:00Z",
                        "source_ref": "fixture://daily/AAPL/2026-06-30",
                        "source_row_hash": "4" * 64,
                    },
                    {
                        "symbol": "MSFT",
                        "input_date_et": "2026-06-30",
                        "point_in_time_valid": True,
                        "prior_20_trading_day_return_pct": 20.0,
                        "known_at_utc": "2026-06-30T14:55:00Z",
                        "source_ref": "fixture://daily/MSFT/2026-06-30",
                        "source_row_hash": "5" * 64,
                    },
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                generated_at_utc="2026-06-30T15:00:00Z",
            )

        self.assertEqual(
            report["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(report["tracking_start_date"], "2026-06-30")
        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)
        self.assertEqual(report["candidate_rows"][0]["ticker"], "AAPL")
        self.assertEqual(
            report["candidate_rows"][0]["tracking_start_date"], "2026-06-30"
        )
        self.assertEqual(
            report["candidate_rows"][0]["tracking_start_at_utc"], "2026-06-30T14:00:00Z"
        )
        self.assertEqual(
            report["candidate_rows"][0]["evidence_bucket"], "forward_paper_shadow"
        )
        self.assertEqual(
            report["candidate_rows"][0]["known_at"], "2026-06-30T14:55:00Z"
        )
        self.assertEqual(
            report["candidate_rows"][0]["tradable_after"], "2026-06-30T15:00:00Z"
        )
        self.assertEqual(
            report["candidate_rows"][0]["decision_timestamp_utc"],
            "2026-06-30T15:00:00Z",
        )
        self.assertEqual(
            report["candidate_rows"][0]["entry_quote_timestamp_utc"],
            "2026-06-30T15:00:00Z",
        )
        self.assertEqual(
            report["candidate_rows"][0]["long_entry_quote_timestamp_utc"],
            "2026-06-30T15:00:00Z",
        )
        self.assertEqual(
            report["candidate_rows"][0]["short_entry_quote_timestamp_utc"],
            "2026-06-30T15:00:00Z",
        )
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
                    "spread_liquidity": {
                        "long_ask": 4.2,
                        "long_bid": 4.0,
                        "short_bid": 1.0,
                        "short_ask": 1.1,
                    },
                },
                run_at=datetime(2026, 6, 30, 15, 0, 0, tzinfo=UTC),
                scan_result={"playbook": {"id": "bullish_pullback_observation"}},
            )
            _write_jsonl(scan_path, [scan_row])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(
            report["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)
        self.assertEqual(report["forward_tracking"]["rejected_counts"], {})
        self.assertEqual(
            report["forward_tracking"][
                "matched_but_unappendable_missing_entry_provenance_count"
            ],
            1,
        )
        self.assertIn(
            "missing_or_invalid_explicit_long_entry_quote_timestamp",
            report["forward_tracking"]["matched_but_unappendable_counts"],
        )
        self.assertIn(
            "signal_known_at_missing_or_not_timezone_aware",
            report["forward_tracking"]["matched_but_unappendable_counts"],
        )

    def test_uses_contract_when_latest_filtered_audit_is_doctored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit = _audit()
            audit["status"] = "blocked_historical_filtered_simulated_forward_audit"
            audit["filter_source"]["conditions"] = [
                {"field": "ticker", "op": "in", "value": ["MSFT"]},
                {
                    "field": "signal_evidence.prior_20_trading_day_return_pct",
                    "op": "gte",
                    "value": 999.0,
                },
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
                        "known_at_utc": "2026-06-30T14:55:00Z",
                        "source_ref": "fixture://daily/AAPL/2026-06-30",
                        "source_row_hash": "4" * 64,
                    }
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                generated_at_utc="2026-06-30T15:00:00Z",
            )

        self.assertEqual(
            report["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(
            report["policy_drift_status"],
            "latest_filtered_audit_diverged_from_frozen_contract",
        )
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
                        "known_at_utc": "2026-06-30T14:55:00Z",
                        "source_ref": "fixture://daily/AAPL/2026-06-30",
                        "source_row_hash": "4" * 64,
                    }
                ],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(
            report["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)
        self.assertEqual(
            report["forward_tracking"]["rejected_counts"],
            {"pre_tracking_start_date": 1},
        )

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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(
            report["status"], "blocked_filtered_forward_paper_shadow_tracker"
        )
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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(
            report["status"], "blocked_filtered_forward_paper_shadow_tracker"
        )
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
                scan_task_health_path=_ready_scan_task_health_path(root),
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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
            )

        self.assertEqual(
            report["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 0)
        self.assertEqual(
            report["forward_tracking"]["rejected_counts"],
            {
                "missing_or_invalid_timezone_aware_scan_timestamp": 1,
                "pre_tracking_start_timestamp": 1,
            },
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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                previous_tracker_dir=tracker_dir,
            )

        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T14:00:00Z")
        self.assertEqual(report["tracking_start_source"], "previous_tracker_artifacts")
        self.assertEqual(report["forward_tracking"]["matched_candidate_count"], 1)

    def test_scan_health_and_point_in_time_signal_lineage_are_proof_blockers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            health_path = root / "health.json"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_json(health_path, _scan_task_health())
            row = {
                "scan_date": "2026-06-30",
                "logged_at": "2026-06-30T15:00:00Z",
                "ticker": "AAPL",
                "strategy_type": "vertical_spread",
                **_entry_fields("AAPL"),
            }
            _write_jsonl(scan_path, [row])
            _write_jsonl(daily_path, [])
            missing_health = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                scan_task_health_path=root / "missing-health.json",
            )
            no_signal_lineage = dict(row)
            no_signal_lineage["signal_evidence"] = {
                "prior_20_trading_day_return_pct": 12.5
            }
            _write_jsonl(scan_path, [no_signal_lineage])
            missing_signal = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                scan_task_health_path=health_path,
            )

        self.assertEqual(
            missing_health["status"], "blocked_filtered_forward_paper_shadow_tracker"
        )
        self.assertIn("scan_task_health_not_loaded", missing_health["blockers"])
        self.assertIn("scan_task_health_status_not_ready", missing_health["blockers"])
        self.assertEqual(
            missing_signal["status"], "filtered_forward_paper_shadow_tracking_active"
        )
        self.assertEqual(
            missing_signal["forward_tracking"]["appendable_entry_count"], 0
        )
        self.assertIn(
            "signal_known_at_missing_or_not_timezone_aware",
            missing_signal["forward_tracking"]["matched_but_unappendable_counts"],
        )
        self.assertIn(
            "signal_source_ref_missing",
            missing_signal["forward_tracking"]["matched_but_unappendable_counts"],
        )

    def test_tracking_start_offsets_are_normalized_before_timestamp_comparison(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            health_path = root / "health.json"
            contract = _contract()
            contract["tracking_start_at_utc"] = "2026-06-30T14:00:00+02:00"
            _write_json(audit_path, _audit())
            _write_json(contract_path, contract)
            _write_json(health_path, _scan_task_health())
            row = {
                "scan_date": "2026-06-30",
                "logged_at": "2026-06-30T12:30:00Z",
                "ticker": "AAPL",
                "strategy_type": "vertical_spread",
                **_entry_fields("AAPL"),
            }
            for field in (
                "quote_timestamp_utc",
                "long_entry_quote_timestamp_utc",
                "short_entry_quote_timestamp_utc",
                "decision_timestamp_utc",
            ):
                row[field] = "2026-06-30T12:30:00Z"
            row["signal_evidence"] = {
                **row["signal_evidence"],
                "known_at_utc": "2026-06-30T12:29:00Z",
            }
            _write_jsonl(scan_path, [row])
            _write_jsonl(daily_path, [])

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                scan_task_health_path=health_path,
            )

        self.assertEqual(report["tracking_start_at_utc"], "2026-06-30T12:00:00Z")
        self.assertEqual(report["forward_tracking"]["rejected_counts"], {})
        self.assertEqual(report["forward_tracking"]["appendable_entry_count"], 1)

    def test_duplicate_point_in_time_signal_source_lineage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            contract_path = root / "contract.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            health_path = root / "health.json"
            _write_json(audit_path, _audit())
            _write_json(contract_path, _contract())
            _write_json(health_path, _scan_task_health())
            row = {
                "scan_date": "2026-06-30",
                "logged_at": "2026-06-30T15:00:00Z",
                "ticker": "AAPL",
                "strategy_type": "vertical_spread",
                **_entry_fields("AAPL"),
            }
            row.pop("signal_evidence", None)
            _write_jsonl(scan_path, [row])
            daily_row = {
                "symbol": "AAPL",
                "input_date_et": "2026-06-30",
                "point_in_time_valid": True,
                "prior_20_trading_day_return_pct": 12.5,
                "known_at_utc": "2026-06-30T14:55:00Z",
                "source_ref": "fixture://daily/AAPL/2026-06-30",
                "source_row_hash": "4" * 64,
            }
            _write_jsonl(
                daily_path, [daily_row, {**daily_row, "source_row_hash": "5" * 64}]
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                scan_task_health_path=health_path,
            )

        self.assertEqual(
            report["forward_tracking"]["rejected_counts"],
            {"duplicate_point_in_time_signal_source_lineage": 1},
        )

    def test_matched_row_log_append_is_idempotent_and_missing_provenance_is_visible(
        self,
    ) -> None:
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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            second = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            log_rows = [
                json.loads(line)
                for line in matched_log.read_text(encoding="utf8").splitlines()
                if line.strip()
            ]

        self.assertEqual(first["forward_tracking"]["entry_rows_appended_count"], 1)
        self.assertEqual(second["forward_tracking"]["entry_rows_appended_count"], 0)
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(
            first["forward_tracking"][
                "matched_but_unappendable_missing_entry_provenance_count"
            ],
            1,
        )
        self.assertIn(
            "missing_long_contract_symbol",
            first["forward_tracking"]["matched_but_unappendable_counts"],
        )
        self.assertEqual(
            first["matched_but_unappendable_rows"][0]["status"],
            "matched_but_unappendable_missing_entry_provenance",
        )

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
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )
            log_rows = [
                json.loads(line)
                for line in matched_log.read_text(encoding="utf8").splitlines()
                if line.strip()
            ]

        self.assertEqual(report["forward_tracking"]["raw_matched_scan_row_count"], 3)
        self.assertEqual(
            report["forward_tracking"]["daily_signal_matched_row_count"], 1
        )
        self.assertEqual(report["forward_tracking"]["entry_rows_appended_count"], 1)
        self.assertEqual(
            report["forward_tracking"][
                "same_day_signal_duplicate_matches_suppressed_count"
            ],
            2,
        )
        self.assertEqual(len(log_rows), 1)
        self.assertEqual(log_rows[0]["source_scan_run_id"], "scan-AAPL-1")
        self.assertEqual(log_rows[0]["long_contract_symbol"], "AAPL260821C00200000")
        self.assertEqual(
            log_rows[0]["candidate_identity_schema"],
            tracker.MATCHED_ROW_IDENTITY_SCHEMA,
        )

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
            _write_jsonl(
                matched_log,
                [{"candidate_id": "old", "scan_date": "2026-06-30", "ticker": "AAPL"}],
            )

            report = tracker.build_report(
                policy_contract_path=contract_path,
                filtered_audit_path=audit_path,
                scan_task_health_path=_ready_scan_task_health_path(root),
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
            )

        self.assertEqual(
            report["status"], "blocked_filtered_forward_paper_shadow_tracker"
        )
        self.assertIn(
            "matched_rows_log_nonempty_before_daily_signal_identity_upgrade",
            report["blockers"],
        )

    @patch.object(
        tracker, "_entry_quote_store_verification_established", return_value=True
    )
    def test_forward_evidence_bar_reports_incomplete_and_complete_progress(
        self,
        _store_verification: object,
    ) -> None:
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
            pairs: list[tuple[dict, dict]] = []
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
                    pairs.append(
                        _completion_pair(
                            date,
                            ticker=ticker,
                            index=offset,
                            winning=pct > 0,
                        )
                    )
            rows = [row for pair in pairs for row in pair]
            _write_jsonl(scan_path, [])
            _write_jsonl(matched_log, [row for pair in pairs[:29] for row in pair])
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
            fixture_rows = [dict(row) for row in rows]
            fixture_rows[1] = {**fixture_rows[1], "is_fixture": True}
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

        self.assertEqual(
            incomplete["forward_evidence_bar"]["status"],
            "waiting_for_min_completed_forward_rows",
        )
        self.assertFalse(incomplete["forward_evidence_bar"]["evaluation_permitted"])
        self.assertIsNone(
            incomplete["forward_evidence_bar"]["percent_cluster_bootstrap"]
        )
        self.assertFalse(incomplete["approval_authority"])
        self.assertEqual(complete["forward_evidence_bar"]["completed_forward_rows"], 32)
        self.assertTrue(complete["forward_evidence_bar"]["evaluation_permitted"])
        self.assertTrue(complete["forward_evidence_bar"]["criteria_met_reporting_only"])
        self.assertFalse(complete["approval_authority"])
        self.assertFalse(complete["forward_evidence_bar"]["approval_authority"])
        self.assertEqual(
            complete["parity_disclosure"]["forward_scheduled_session_times"][
                "\\OptionsScanPicks"
            ],
            "11:00:00 AM",
        )
        self.assertEqual(
            fixture_blocked["forward_evidence_bar"]["completed_forward_rows"], 32
        )
        self.assertTrue(fixture_blocked["forward_evidence_bar"]["evaluation_permitted"])
        self.assertEqual(
            fixture_blocked["forward_evidence_bar"]["fixture_row_count"], 1
        )
        self.assertFalse(
            fixture_blocked["forward_evidence_bar"]["checks"]["fixture_rows"]
        )
        self.assertFalse(
            fixture_blocked["forward_evidence_bar"]["criteria_met_reporting_only"]
        )
        self.assertEqual(
            fixture_blocked["forward_evidence_bar"]["status"],
            "forward_evidence_bar_criteria_not_met",
        )

    def test_fee_adjusted_net_return_is_canonical_for_tracker_and_exit_completion(
        self,
    ) -> None:
        source_row = {
            "scan_date": "2026-07-10",
            "logged_at": "2026-07-10T18:00:00Z",
            "ticker": "SPY",
            "direction": "call",
            "lane_id": "bullish_pullback_observation",
            "expiry": "2026-08-21",
            "dte": 42,
            "contract_symbol": "SPY260821C00500000",
            "short_contract_symbol": "SPY260821C00510000",
            "quote_source": "alpaca_opra",
            "quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "long_entry_quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "short_entry_quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "decision_timestamp_utc": "2026-07-10T18:00:00Z",
            "spread_liquidity": {
                "long_bid": 2.9,
                "long_ask": 3.0,
                "short_bid": 1.0,
                "short_ask": 1.1,
            },
            "net_debit": 2.0,
            "scan_run_id": "scan-SPY-proof",
            "scan_host": "TESTHOST",
            "scan_commit_sha": "1" * 40,
            "scan_branch": "test",
            "_source_scan_picks_sha256": "2" * 64,
            "_scan_task_health_sha256": "3" * 64,
            "_scan_task_health_status": tracker.READY_SCAN_TASK_HEALTH_STATUS,
            "_scan_task_health_generated_at_utc": "2026-07-10T19:00:00Z",
            "source_scan_session_id": 501,
            "source_scan_event_key": "bullish_pullback_observation:rank_1",
            "source_scan_run_id": "scheduled_scan:2026-07-10:SPY",
            "source_scan_recorded_at_utc": "2026-07-10T18:01:00Z",
            "signal_evidence": {
                "prior_20_trading_day_return_pct": 12.5,
                "prior_20_trading_day_return_source": "fixture_point_in_time_source",
                "known_at_utc": "2026-07-10T17:55:00Z",
                "source_ref": "fixture://signal/SPY/2026-07-10",
                "source_row_hash": "4" * 64,
            },
        }
        source, reasons = tracker._matched_entry_log_row(
            source_row,
            tracking_start_date="2026-07-10",
            tracking_start_at_utc="2026-07-10T00:00:00Z",
        )
        self.assertEqual(reasons, [])
        canonical_source = {
            "pnl_pct": 10.0,
            "gross_pnl_pct": 10.0,
            "net_pnl_pct": 9.0,
            "net_pnl_pct_after_fees": 8.5,
        }
        self.assertEqual(tracker._canonical_net_pnl_pct(canonical_source), 8.5)

        exit_day = date.fromisoformat(str(source["policy_exit_date"]))
        exit_timestamp = tracker._utc_iso(
            datetime.combine(exit_day, time(15, 55), tzinfo=tracker.EASTERN).astimezone(
                UTC
            )
        )

        completed = exit_capture._completion_row(
            source,
            {
                "source_label": "thetadata_opra_nbbo_1m",
                "long_contract_symbol": source["long_contract_symbol"],
                "short_contract_symbol": source["short_contract_symbol"],
                "timestamp_utc": exit_timestamp,
                "long_timestamp_utc": exit_timestamp,
                "short_timestamp_utc": exit_timestamp,
                "long_quote_minute_et": 955,
                "short_quote_minute_et": 955,
                "long_bid": 3.0,
                "short_ask": 0.8,
                "basis": "trusted_thetadata_intraday_options_history_db_read_only",
                "exit_quote_pair_synchronized": True,
            },
            exit_date=exit_day,
        )

        assert completed is not None
        self.assertEqual(completed["pnl_pct"], 10.0)
        self.assertEqual(completed["gross_pnl_pct"], 10.0)
        self.assertEqual(completed["net_pnl_pct"], 8.5884)
        self.assertEqual(completed["net_pnl_pct_after_fees"], 8.5884)
        self.assertEqual(completed["long_exit_quote_timestamp_utc"], exit_timestamp)
        self.assertEqual(completed["short_exit_quote_timestamp_utc"], exit_timestamp)
        self.assertTrue(tracker._is_completed_forward_row(completed))

        rejected = exit_capture._completion_row(
            source,
            {
                "source_label": "thetadata_opra_nbbo_1m",
                "long_contract_symbol": source["long_contract_symbol"],
                "short_contract_symbol": source["short_contract_symbol"],
                "timestamp_utc": exit_timestamp,
                "long_timestamp_utc": exit_timestamp,
                "short_timestamp_utc": tracker._utc_iso(
                    datetime.fromisoformat(
                        exit_timestamp.replace("Z", "+00:00")
                    ).replace(second=1)
                ),
                "long_quote_minute_et": 955,
                "short_quote_minute_et": 956,
                "long_bid": 3.0,
                "short_ask": 0.8,
                "basis": "trusted_thetadata_intraday_options_history_db_read_only",
                "exit_quote_pair_synchronized": False,
            },
            exit_date=exit_day,
        )
        self.assertIsNone(rejected)

    def test_entry_proof_requires_explicit_aware_exact_leg_timestamps(self) -> None:
        base = {
            "scan_date": "2026-07-10",
            "logged_at": "2026-07-10T18:00:00Z",
            "ticker": "SPY",
            "direction": "call",
            "lane_id": "bullish_pullback_observation",
            "expiry": "2026-08-21",
            "dte": 42,
            "contract_symbol": "SPY260821C00500000",
            "short_contract_symbol": "SPY260821C00510000",
            "quote_source": "alpaca_opra",
            "quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "spread_liquidity": {
                "long_bid": 2.9,
                "long_ask": 3.0,
                "short_bid": 1.0,
                "short_ask": 1.1,
            },
            "net_debit": 2.0,
        }
        _provenance, aggregate_only = tracker._entry_provenance(base)
        _provenance, naive = tracker._entry_provenance(
            {
                **base,
                "long_entry_quote_timestamp_utc": "2026-07-10T18:00:00",
                "short_entry_quote_timestamp_utc": "2026-07-10T18:00:00",
            }
        )
        _provenance, seconds_mismatch = tracker._entry_provenance(
            {
                **base,
                "long_entry_quote_timestamp_utc": "2026-07-10T18:00:00.100Z",
                "short_entry_quote_timestamp_utc": "2026-07-10T18:00:00.900Z",
            }
        )

        self.assertIn(
            "missing_or_invalid_explicit_long_entry_quote_timestamp", aggregate_only
        )
        self.assertIn(
            "missing_or_invalid_explicit_short_entry_quote_timestamp", aggregate_only
        )
        self.assertIn("missing_or_invalid_explicit_long_entry_quote_timestamp", naive)
        self.assertIn("missing_or_invalid_explicit_short_entry_quote_timestamp", naive)
        self.assertIn(
            "entry_quote_timestamps_not_exactly_synchronized", seconds_mismatch
        )

    def test_self_asserted_entry_quote_store_claim_cannot_enable_proof(self) -> None:
        entry, completion = _completion_pair("2026-07-10")
        caller_claims = {
            "entry_quote_store_verification_established": True,
            "entry_quote_store_verified": True,
            "entry_quote_store_binding_sha256": "f" * 64,
            "entry_quote_store_manifest_sha256": "e" * 64,
        }
        entry = {**entry, **caller_claims}
        completion = {**completion, **caller_claims}

        valid, declared, rejects = tracker._validated_completion_rows(
            [entry, completion]
        )
        progress = tracker._forward_evidence_bar_progress(
            [entry, completion],
            bar_contract=_bar_contract(min_rows=1, draws=10),
            bar_meta={"status": "loaded"},
        )
        merged = tracker._merge_lifecycle_rows([entry, completion])

        self.assertEqual(tracker._matched_entry_lineage_reject_reasons(entry), [])
        self.assertEqual(tracker._completion_lineage_reject_reasons(completion), [])
        self.assertEqual(valid, [])
        self.assertEqual(declared, [completion])
        self.assertEqual(rejects[tracker.ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER], 1)
        self.assertEqual(progress["completed_forward_rows"], 0)
        self.assertFalse(progress["evaluation_permitted"])
        self.assertFalse(progress["entry_quote_store_verification_established"])
        self.assertEqual(
            progress["proof_blockers"],
            [tracker.ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER],
        )
        self.assertEqual(
            progress["status"], tracker.ENTRY_QUOTE_STORE_VERIFICATION_BLOCKER
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["record_type"], "matched_entry")

        verifier_inputs: list[dict | None] = []
        with patch.object(
            tracker,
            "_entry_quote_store_verification_established",
            side_effect=lambda row=None: verifier_inputs.append(row) or False,
        ):
            tracker._validated_completion_rows([entry, completion])
        self.assertEqual(len(verifier_inputs), 1)
        self.assertIs(verifier_inputs[0], entry)

    def test_authoritative_entry_verifier_requires_one_exact_ledger_event(self) -> None:
        entry, _completion = _completion_pair("2026-07-10")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exact_db = root / "exact.db"
            duplicate_db = root / "duplicate.db"
            _write_authoritative_scan_event(exact_db, entry=entry)
            _write_authoritative_scan_event(duplicate_db, entry=entry, duplicate=True)

            verified = tracker._entry_quote_store_verification(entry, db_path=exact_db)
            tampered = tracker._entry_quote_store_verification(
                {**entry, "entry_long_bid": 4.00001}, db_path=exact_db
            )
            duplicate = tracker._entry_quote_store_verification(
                entry, db_path=duplicate_db
            )

        self.assertTrue(verified["verified"])
        self.assertEqual(verified["detail"], "exact_authoritative_scan_event_match")
        self.assertEqual(verified["session_id"], entry["source_scan_session_id"])
        self.assertRegex(verified["canonical_payload_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(tampered["verified"])
        self.assertEqual(
            tampered["detail"],
            "matched_entry_entry_long_bid_aliases_missing_or_invalid",
        )
        self.assertFalse(duplicate["verified"])
        self.assertEqual(duplicate["detail"], "authoritative_scan_event_match_count:2")

    def test_authoritative_entry_verifier_rejects_mixed_sources_and_freshness(
        self,
    ) -> None:
        entry, _completion = _completion_pair("2026-07-10")
        source = json.loads(json.dumps(entry["source_row"]))
        snapshot_source = json.loads(json.dumps(source["entry_quote_snapshot"]))
        snapshot_source["quote_source"] = "thetadata_opra_nbbo_1m"
        leg_source = json.loads(json.dumps(source["entry_quote_snapshot"]))
        leg_source["legs"][0]["quote_source"] = "thetadata_opra_nbbo_1m"
        leg_data_source = json.loads(json.dumps(source["entry_quote_snapshot"]))
        leg_data_source["legs"][0]["data_source"] = "daily_or_other"
        leg_stale = json.loads(json.dumps(source["entry_quote_snapshot"]))
        leg_stale["legs"][1]["quote_freshness_status"] = "stale"
        chain_stale = json.loads(json.dumps(source["entry_quote_snapshot"]))
        chain_stale["legs"][1]["option_chain_status"] = "stale"
        cases = {
            "snapshot_source": {"entry_quote_snapshot": snapshot_source},
            "leg_source": {"entry_quote_snapshot": leg_source},
            "leg_data_source": {"entry_quote_snapshot": leg_data_source},
            "leg_freshness": {"entry_quote_snapshot": leg_stale},
            "chain_stale": {"entry_quote_snapshot": chain_stale},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = {}
            for name, overrides in cases.items():
                db_path = root / f"{name}.db"
                _write_authoritative_scan_event(
                    db_path, entry=entry, payload_overrides=overrides
                )
                results[name] = tracker._entry_quote_store_verification(
                    entry, db_path=db_path
                )
            exact_db = root / "exact.db"
            _write_authoritative_scan_event(exact_db, entry=entry)
            matched_source = tracker._entry_quote_store_verification(
                {**entry, "entry_quote_source": "thetadata_opra_nbbo_1m"},
                db_path=exact_db,
            )

        self.assertEqual(
            results["snapshot_source"]["detail"],
            "authoritative_scan_event_quote_source_invalid",
        )
        self.assertEqual(
            results["leg_source"]["detail"],
            "authoritative_scan_event_quote_source_invalid",
        )
        self.assertEqual(
            results["leg_data_source"]["detail"],
            "authoritative_scan_event_quote_source_invalid",
        )
        self.assertEqual(
            results["leg_freshness"]["detail"],
            "authoritative_scan_event_quote_freshness_invalid",
        )
        self.assertEqual(
            results["chain_stale"]["detail"],
            "authoritative_scan_event_quote_freshness_invalid",
        )
        self.assertEqual(
            matched_source["detail"], "matched_entry_quote_source_mismatch"
        )

    def test_authoritative_entry_verifier_rejects_session_metadata_divergence(
        self,
    ) -> None:
        entry, _completion = _completion_pair("2026-07-10")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "divergent.db"
            _write_authoritative_scan_event(
                db_path,
                entry=entry,
                session_overrides={"run_id": "different-session-run"},
            )
            result = tracker._entry_quote_store_verification(entry, db_path=db_path)

        self.assertFalse(result["verified"])
        self.assertEqual(
            result["detail"], "authoritative_scan_event_session_run_id_mismatch"
        )

    def test_report_verifier_uses_one_sqlite_snapshot_and_locator_cache(self) -> None:
        first, _completion = _completion_pair("2026-07-10", index=0)
        second, _completion = _completion_pair("2026-07-11", index=1)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "snapshot.db"
            _write_authoritative_scan_event(db_path, entry=first)
            _write_authoritative_scan_event(db_path, entry=second, initialize=False)
            setup = sqlite3.connect(db_path)
            setup.execute("PRAGMA journal_mode=WAL")
            setup.close()

            queries: list[str] = []
            with tracker._EntryQuoteStoreVerifier(db_path) as verifier:
                assert verifier.connection is not None
                verifier.connection.set_trace_callback(queries.append)
                first_result = verifier.verify(first)
                verifier.verify(first)
                tampered_same_locator = verifier.verify(
                    {**first, "entry_long_bid": 9.9}
                )
                writer = sqlite3.connect(db_path)
                writer.execute(
                    "UPDATE forward_events SET payload_json = '{}' WHERE session_id = ?",
                    (second["source_scan_session_id"],),
                )
                writer.commit()
                writer.close()
                second_snapshot_result = verifier.verify(second)
            second_after_close = tracker._entry_quote_store_verification(
                second, db_path=db_path
            )

        select_count = sum("FROM forward_sessions" in query for query in queries)
        self.assertTrue(first_result["verified"])
        self.assertFalse(tampered_same_locator["verified"])
        self.assertTrue(second_snapshot_result["verified"])
        self.assertFalse(second_after_close["verified"])
        self.assertEqual(select_count, 3)
        self.assertEqual(len(verifier.cache), 3)

    def test_authoritative_event_rejects_conflicting_price_aliases(self) -> None:
        entry, _completion = _completion_pair("2026-07-10")
        snapshot = json.loads(json.dumps(entry["source_row"]["entry_quote_snapshot"]))
        snapshot["legs"][0]["bid"] = 9.0
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "conflict.db"
            _write_authoritative_scan_event(
                db_path,
                entry=entry,
                payload_overrides={
                    "entry_long_bid": 4.0,
                    "entry_quote_snapshot": snapshot,
                },
            )
            result = tracker._entry_quote_store_verification(entry, db_path=db_path)

        self.assertFalse(result["verified"])
        self.assertEqual(
            result["detail"],
            "authoritative_scan_event_entry_long_bid_aliases_conflict",
        )

    def test_report_verifier_database_init_error_fails_closed(self) -> None:
        entry, _completion = _completion_pair("2026-07-10")
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "corrupt.db"
            db_path.write_bytes(b"not-a-sqlite-database")
            with tracker._EntryQuoteStoreVerifier(db_path) as verifier:
                result = verifier.verify(entry)

        self.assertFalse(result["verified"])
        self.assertTrue(
            result["detail"].startswith("authoritative_forward_ledger_read_failed:")
        )

    def test_authoritative_locator_ids_are_strict_and_exact(self) -> None:
        entry, completion = _completion_pair("2026-07-10")
        for invalid in (True, 77.5, "77.5", "+77", 0, -1):
            with self.subTest(invalid=invalid):
                result = tracker._entry_quote_store_verification(
                    {**entry, "source_scan_session_id": invalid},
                    db_path=Path("missing.db"),
                )
                self.assertEqual(
                    result["detail"], "source_scan_session_id_missing_or_invalid"
                )
        large_entry = {**entry, "source_scan_session_id": 2**53 + 1}
        large_completion = {**completion, "source_scan_session_id": 2**53}
        reasons = tracker._completion_preceding_entry_reject_reasons(
            large_completion, large_entry
        )
        self.assertIn(
            "completion_preceding_entry_source_scan_session_id_mismatch", reasons
        )

    def test_duplicate_preceding_entries_fail_closed_instead_of_overwriting(
        self,
    ) -> None:
        entry, completion = _completion_pair("2026-07-10")
        with patch.object(
            tracker, "_entry_quote_store_verification_established", return_value=True
        ):
            valid, _declared, rejects = tracker._validated_completion_rows(
                [entry, dict(entry), completion]
            )

        self.assertEqual(valid, [])
        self.assertEqual(rejects["completion_preceding_matched_entry_not_unique"], 1)

    def test_valid_plus_malformed_preceding_entry_is_not_unique(self) -> None:
        entry, completion = _completion_pair("2026-07-10")
        malformed = {**entry, "source_scan_event_key": ""}
        with patch.object(
            tracker, "_entry_quote_store_verification_established", return_value=True
        ):
            valid, _declared, rejects = tracker._validated_completion_rows(
                [entry, malformed, completion]
            )

        self.assertEqual(valid, [])
        self.assertEqual(rejects["completion_preceding_matched_entry_not_unique"], 1)

    def test_authoritative_locator_cannot_bind_two_candidate_ids(self) -> None:
        first, completion = _completion_pair("2026-07-10")
        second = {**first, "candidate_id": "different-candidate"}
        with patch.object(
            tracker, "_entry_quote_store_verification_established", return_value=True
        ):
            valid, _declared, rejects = tracker._validated_completion_rows(
                [first, second, completion]
            )

        self.assertEqual(valid, [])
        self.assertEqual(rejects["completion_source_scan_locator_not_unique"], 1)

    def test_scanner_run_id_does_not_upgrade_to_authoritative_locator(self) -> None:
        source = {
            **_entry_fields(),
            "source_scan_run_id": None,
            "scanner_run_id": "legacy-scanner-run",
            "scan_date": "2026-06-30",
            "logged_at": "2026-06-30T15:00:00Z",
            "ticker": "AAPL",
            "strategy_type": "vertical_spread",
        }
        entry, reasons = tracker._matched_entry_log_row(
            source,
            tracking_start_date="2026-06-01",
            tracking_start_at_utc="2026-06-01T00:00:00Z",
        )

        self.assertIsNone(entry["source_scan_run_id"])
        self.assertIn(
            "preceding_entry_source_scan_run_id_missing",
            tracker._matched_entry_lineage_reject_reasons(entry),
        )
        self.assertEqual(reasons, [])

    def test_completion_semantics_policy_and_geometry_must_match_preceding_entry(
        self,
    ) -> None:
        entry, completion = _completion_pair("2026-07-10")
        semantic_mutation = {
            **completion,
            "ticker": "MSFT",
            "direction": "put",
            "lane_id": "other_lane",
            "expiry": "2027-01-15",
            "dte": 999,
            "tracking_policy_id": "other_policy",
            "long_strike": 999.0,
            "short_strike": 1.0,
            "spread_width": 998.0,
        }
        valid, _declared, rejects = tracker._validated_completion_rows(
            [entry, semantic_mutation]
        )
        same_day_exit = {
            **completion,
            "exit_date": entry["scan_date"],
            "policy_exit_date": entry["scan_date"],
        }
        policy_reasons = tracker._completion_lineage_reject_reasons(same_day_exit)

        self.assertEqual(valid, [])
        self.assertIn("completion_preceding_entry_ticker_mismatch", rejects)
        self.assertIn("completion_preceding_entry_direction_mismatch", rejects)
        self.assertIn("completion_preceding_entry_lane_id_mismatch", rejects)
        self.assertIn("completion_preceding_entry_tracking_policy_id_mismatch", rejects)
        self.assertIn("completion_exit_not_after_entry", policy_reasons)
        self.assertIn("completion_policy_exit_date_mismatch", policy_reasons)

    def test_occ_vertical_geometry_and_price_bounds_fail_closed(self) -> None:
        invalid = {
            "scan_date": "2026-07-10",
            "ticker": "AAPL",
            "direction": "call",
            "expiry": "2026-08-21",
            "dte": 42,
            "contract_symbol": "MSFT260821P00200000",
            "short_contract_symbol": "AAPL260918C00210000",
            "long_strike": 220.0,
            "short_strike": 210.0,
            "spread_width": 10.0,
            "quote_source": "alpaca_opra",
            "quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "long_entry_quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "short_entry_quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "spread_liquidity": {
                "long_bid": 5.0,
                "long_ask": 4.0,
                "short_bid": 3.0,
                "short_ask": 2.0,
            },
        }
        _provenance, reasons = tracker._entry_provenance(invalid)
        entry, _completion = _completion_pair("2026-07-10")
        exit_day = date.fromisoformat(str(entry["policy_exit_date"]))
        timestamp = tracker._utc_iso(
            datetime.combine(exit_day, time(15, 55), tzinfo=tracker.EASTERN).astimezone(
                UTC
            )
        )
        above_width = exit_capture._completion_row(
            entry,
            {
                "source_label": "thetadata_opra_nbbo_1m",
                "long_contract_symbol": entry["long_contract_symbol"],
                "short_contract_symbol": entry["short_contract_symbol"],
                "timestamp_utc": timestamp,
                "long_timestamp_utc": timestamp,
                "short_timestamp_utc": timestamp,
                "long_quote_minute_et": 955,
                "short_quote_minute_et": 955,
                "long_bid": 50.0,
                "long_ask": 50.1,
                "short_bid": 0.0,
                "short_ask": 0.0,
                "basis": "trusted_thetadata_intraday_options_history_db_read_only",
                "exit_quote_pair_synchronized": True,
            },
            exit_date=exit_day,
        )

        self.assertIn("occ_contract_root_ticker_mismatch", reasons)
        self.assertIn("vertical_contract_expiry_mismatch", reasons)
        self.assertIn("vertical_contract_right_mismatch", reasons)
        self.assertIn("entry_long_quote_crossed", reasons)
        self.assertIn("entry_short_quote_crossed", reasons)
        self.assertIsNone(above_width)

    def test_arbitrary_standalone_completion_cannot_count_or_override_recomputed_pnl(
        self,
    ) -> None:
        entry, completion = _completion_pair("2026-07-10")
        forged = {
            **completion,
            "net_pnl_pct_after_fees": 999999.0,
            "net_pnl_usd": 999999.0,
        }

        reasons = tracker._completion_lineage_reject_reasons(forged)
        progress = tracker._forward_evidence_bar_progress(
            [forged],
            bar_contract=_bar_contract(min_rows=1, draws=10),
            bar_meta={"status": "loaded"},
        )

        self.assertIn("completion_fee_adjusted_pnl_pct_not_recomputed", reasons)
        self.assertIn("completion_net_pnl_usd_not_recomputed", reasons)
        self.assertEqual(tracker._merge_lifecycle_rows([completion]), [])
        self.assertEqual(progress["completed_forward_rows"], 0)
        self.assertFalse(progress["evaluation_permitted"])
        self.assertTrue(tracker._is_completed_forward_row(completion))
        self.assertEqual(len(tracker._merge_lifecycle_rows([entry, completion])), 1)

    def test_completion_rejects_daily_snapshot_exit_and_entry_sources(self) -> None:
        _entry, completion = _completion_pair("2026-07-10")
        daily_exit = {**completion, "exit_quote_source": "alpaca_opra_daily_snapshot"}
        daily_entry_source = {
            "scan_date": "2026-07-10",
            "logged_at": "2026-07-10T18:00:00Z",
            "ticker": "AAPL",
            "direction": "call",
            "expiry": "2026-08-21",
            "dte": 42,
            "contract_symbol": "AAPL260821C00200000",
            "short_contract_symbol": "AAPL260821C00210000",
            "quote_source": "alpaca_opra_daily_snapshot",
            "quote_timestamp_utc": "2026-07-10T18:00:00Z",
            "spread_liquidity": {
                "long_bid": 2.9,
                "long_ask": 3.0,
                "short_bid": 1.0,
                "short_ask": 1.1,
            },
        }
        _daily_entry, entry_reasons = tracker._matched_entry_log_row(
            daily_entry_source,
            tracking_start_date="2026-07-10",
            tracking_start_at_utc="2026-07-10T00:00:00Z",
        )

        self.assertIn(
            "completion_exit_quote_source_untrusted",
            tracker._completion_lineage_reject_reasons(daily_exit),
        )
        self.assertFalse(tracker._is_completed_forward_row(daily_exit))
        self.assertIn("untrusted_entry_quote_source", entry_reasons)

    @patch.object(
        tracker, "_entry_quote_store_verification_established", return_value=True
    )
    def test_legacy_completion_without_record_type_does_not_block_trusted_recapture(
        self,
        _store_verification: object,
    ) -> None:
        entry, completion = _completion_pair("2026-07-10")
        legacy = {
            **entry,
            "tracking_state": "forward_paper_shadow_completed",
            "realized_pnl_status": "completed_exact_exit",
            "net_pnl_pct": 10.0,
            "net_pnl_usd": 100.0,
        }
        legacy.pop("record_type", None)
        legacy.pop("lifecycle_event", None)

        merged_before = tracker._merge_lifecycle_rows([entry, legacy])
        merged_after = tracker._merge_lifecycle_rows([entry, legacy, completion])
        progress = tracker._forward_evidence_bar_progress(
            [entry, legacy, completion],
            bar_contract=_bar_contract(min_rows=1, draws=10),
            bar_meta={"status": "loaded"},
        )

        self.assertEqual(
            tracker._matched_log_duplicate_daily_signal_identities([entry, legacy]), []
        )
        self.assertEqual(merged_before[0]["record_type"], "matched_entry")
        self.assertEqual(merged_after[0]["record_type"], "completion")
        self.assertTrue(tracker._is_completed_forward_row(merged_after[0]))
        self.assertEqual(progress["completed_forward_rows"], 1)
        self.assertEqual(progress["completion_lineage_incomplete_count"], 0)
        self.assertTrue(progress["checks"]["trusted_synchronized_exit_price_lineage"])
        self.assertIn(
            "completion_lineage_schema_missing_or_invalid",
            progress["completion_lineage_reject_counts"],
        )

    @patch.object(
        tracker, "_entry_quote_store_verification_established", return_value=True
    )
    def test_duplicate_valid_completion_events_count_once_and_block_uniqueness_check(
        self,
        _store_verification: object,
    ) -> None:
        entry, completion = _completion_pair("2026-07-10")
        progress = tracker._forward_evidence_bar_progress(
            [entry, completion, dict(completion)],
            bar_contract=_bar_contract(min_rows=2, draws=10),
            bar_meta={"status": "loaded"},
        )

        self.assertEqual(progress["declared_completed_forward_rows"], 2)
        self.assertEqual(progress["declared_completed_candidate_count"], 1)
        self.assertEqual(progress["completed_forward_rows"], 1)
        self.assertEqual(progress["duplicate_valid_completion_event_count"], 1)
        self.assertFalse(progress["checks"]["unique_valid_completion_events"])
        self.assertFalse(progress["evaluation_permitted"])

    def test_legacy_status_and_pnl_only_completion_is_incomplete_and_not_counted(
        self,
    ) -> None:
        legacy = {
            "candidate_id": "legacy",
            "scan_date": "2026-07-10",
            "ticker": "AAPL",
            "tracking_state": "forward_paper_shadow_completed",
            "realized_pnl_status": "completed_exact_exit",
            "net_pnl_pct": 10.0,
            "net_pnl_usd": 100.0,
        }

        progress = tracker._forward_evidence_bar_progress(
            [legacy],
            bar_contract=_bar_contract(min_rows=1, draws=10),
            bar_meta={"status": "loaded"},
        )

        self.assertFalse(tracker._is_completed_forward_row(legacy))
        self.assertEqual(progress["declared_completed_forward_rows"], 1)
        self.assertEqual(progress["completed_forward_rows"], 0)
        self.assertEqual(progress["completion_lineage_incomplete_count"], 1)
        self.assertFalse(progress["evaluation_permitted"])
        self.assertIn(
            "completion_lineage_schema_missing_or_invalid",
            progress["completion_lineage_reject_counts"],
        )

    def test_latest_completed_market_day_uses_dst_correct_eastern_close(self) -> None:
        self.assertEqual(
            exit_capture._latest_completed_market_day(
                "2026-07-09T19:59:00Z"
            ).isoformat(),
            "2026-07-08",
        )
        self.assertEqual(
            exit_capture._latest_completed_market_day(
                "2026-07-09T20:01:00Z"
            ).isoformat(),
            "2026-07-09",
        )

    def test_write_outputs_creates_latest_docs_and_candidate_jsonl(self) -> None:
        report = {
            "report_id": tracker.REPORT_ID,
            "status": "filtered_forward_paper_shadow_tracking_active",
            "tracking_policy_id": tracker.POLICY_ID,
            "tracking_start_date": "2026-06-30",
            "tracking_start_at_utc": "2026-06-30T14:00:00Z",
            "tracking_start_source": "filtered_audit_timestamp",
            "frozen_filter": {
                "filter_id": "fixture",
                "conditions_text": "ticker in AAPL",
            },
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
