from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_materializer_match_rate_stationarity as stationarity


NOW = "2026-07-04T12:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _paths(root: Path) -> dict[str, Path]:
    return {
        "engine_dir": root / "engine",
        "engine_latest": root / "engine" / "latest.json",
        "policy": root / "contracts" / "policy.json",
        "tracker": root / "tracker" / "latest.json",
        "parity": root / "parity" / "latest.json",
        "throughput": root / "throughput" / "latest.json",
    }


def _market_dates(start: date, count: int) -> list[str]:
    days: list[str] = []
    current = start
    while len(days) < count:
        if stationarity.is_us_equity_market_day(current):
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _policy(path: Path, *, bad_hash: bool = False) -> None:
    policy = {
        "report_id": "regular_options_frozen_filtered_policy",
        "conditions": [
            {"field": "ticker", "op": "in", "value": ["SPY"]},
            {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
        ],
    }
    policy["conditions_sha256"] = stationarity.tracker._conditions_sha256(
        stationarity.tracker._as_list(policy["conditions"])
    )
    if bad_hash:
        policy["conditions_sha256"] = "bad"
    _write_json(path, policy)


def _selected_row(date: str, *, ticker: str = "SPY", prior20: float = 12.0) -> dict:
    return {
        "candidate_generation_date": date,
        "entry_date": date,
        "month": date[:7],
        "lane_id": "bullish_pullback_observation",
        "ticker": ticker,
        "symbol": ticker,
        "direction": "call",
        "selected_candidate": True,
        "exact_priced": True,
        "proof_grade": "trusted_intraday_opra_nbbo",
        "fill_basis": "imported_spread_mark",
        "net_pnl_pct": 1.0,
        "signal_evidence": {"prior_20_trading_day_return_pct": prior20},
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }


def _engine_payload(dates: list[str], match_dates: set[str], *, generated_at: str = NOW) -> dict:
    selected = [
        _selected_row(day, ticker="SPY" if day in match_dates else "QQQ", prior20=12.0 if day in match_dates else 9.0)
        for day in dates
    ]
    return {
        "report_id": "regular_options_13_symbol_frozen_candidate_generation_engine",
        "status": "frozen_13_symbol_candidate_generation_engine_ready",
        "generated_at_utc": generated_at,
        "selected_candidate_row_count": len(selected),
        "selected_candidates": selected,
        "daily_candidate_generation": [{"candidate_generation_date": day} for day in dates],
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }


def _write_engine(paths: dict[str, Path], dates: list[str], match_dates: set[str], *, latest_blocked: bool = False) -> None:
    if latest_blocked:
        _write_json(
            paths["engine_latest"],
            {
                "status": "blocked_frozen_13_symbol_candidate_generation_engine",
                "generated_at_utc": NOW,
                "selected_candidate_row_count": 0,
                "selected_candidates": [],
            },
        )
        _write_json(
            paths["engine_dir"] / "regular_options_13_symbol_frozen_candidate_generation_engine_20260704T010000Z.json",
            _engine_payload(dates, match_dates),
        )
    else:
        _write_json(paths["engine_latest"], _engine_payload(dates, match_dates))


def _write_artifacts(
    paths: dict[str, Path],
    *,
    observed_market_days: int = 3,
    observed_filter_matches: int = 0,
    observed_materializer_rows: int = 9,
    disclosed_rows: int,
    generated_at: str = NOW,
) -> None:
    _write_json(
        paths["tracker"],
        {
            "status": "filtered_forward_paper_shadow_tracking_active",
            "generated_at_utc": generated_at,
            "forward_tracking": {"matched_candidate_count": 0, "completed_candidate_count": 0},
            "parity_disclosure": {
                "historical_filtered_materializer_rows": disclosed_rows,
                "historical_filtered_materializer_months": 1,
            },
        },
    )
    _write_json(
        paths["parity"],
        {
            "status": "scanner_materializer_parity_diff_ready",
            "generated_at_utc": generated_at,
            "window": {"market_day_count": observed_market_days},
            "materializer_coverage": {
                "row_count_in_window": observed_materializer_rows,
                "filter_matched_selected_rows_in_window": observed_filter_matches,
            },
            "summary": {"filtered_materializer_candidate_rows": observed_filter_matches},
            "scheduled_scan_coverage": {"session_times_et": ["10:12:00", "13:45:28"]},
            "boundary": {"materializer_entry_window_et": "10:10-10:25"},
            "divergence_rows": [{"date": "2026-06-16", "symbol": "SPY", "divergence_class": "entry_time_basis_differs"}],
        },
    )
    _write_json(
        paths["throughput"],
        {
            "status": "blocked_no_same_day_phase2_natural_selections",
            "generated_at_utc": generated_at,
            "scheduled_phase2_near_miss_summary": {
                "status": "symbol_level_near_miss_table_ready",
                "ranked_symbol_near_misses": [{"symbol": "SPY", "distance_to_pass": 2.5}],
            },
        },
    )


def _build(paths: dict[str, Path], *, generated_at: str = NOW) -> dict:
    return stationarity.build_report(
        historical_engine_dir=paths["engine_dir"],
        historical_engine_latest_path=paths["engine_latest"],
        policy_contract_path=paths["policy"],
        tracker_latest_path=paths["tracker"],
        parity_latest_path=paths["parity"],
        throughput_latest_path=paths["throughput"],
        generated_at_utc=generated_at,
    )


class MaterializerMatchRateStationarityTests(unittest.TestCase):
    def test_zero_post_freeze_matches_indicate_break_when_zero_historical_windows_are_rare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, disclosed_rows=5)
            report = _build(paths)

        self.assertEqual(report["status"], "post_freeze_zero_indicates_regime_break")
        self.assertEqual(report["zero_run_stationarity"]["zero_match_window_fraction"], 0.0)
        self.assertEqual(report["historical_materializer"]["frozen_filter_match_rows"], 5)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["scanner_policy_changed"])

    def test_zero_post_freeze_matches_can_be_within_historical_variation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
            _write_engine(paths, dates, {"2026-01-02"})
            _write_artifacts(paths, disclosed_rows=1)
            report = _build(paths)

        self.assertEqual(report["status"], "post_freeze_zero_within_historical_variation")
        self.assertGreater(report["zero_run_stationarity"]["zero_match_window_fraction"], 0.05)
        self.assertNotIn("## Operator Escalation", stationarity.render_markdown(report))

    def test_zero_run_trigger_schedule_computes_dates_and_reuses_n13_fraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 20)
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, observed_market_days=13, disclosed_rows=20)
            report = _build(paths)

        schedule = report["zero_run_trigger_schedule"]
        window13 = schedule["windows"][0]
        window14 = schedule["windows"][1]
        self.assertEqual(schedule["status"], "ready")
        self.assertEqual(schedule["window_range_market_days"], [13, 90])
        self.assertEqual(len(schedule["windows"]), 78)
        self.assertEqual(window13["window_market_days"], 13)
        self.assertEqual(window13["projected_calendar_date_if_zero_run_continues"], "2026-07-04")
        self.assertEqual(window14["window_market_days"], 14)
        self.assertEqual(window14["projected_calendar_date_if_zero_run_continues"], "2026-07-06")
        self.assertEqual(window13["zero_match_window_fraction"], report["zero_run_stationarity"]["zero_match_window_fraction"])
        self.assertEqual(schedule["first_regime_break_trigger"]["window_market_days"], 13)
        self.assertEqual(schedule["first_confirmation_trigger"]["window_market_days"], 13)
        self.assertEqual(schedule["monotonicity_check"]["status"], "passed")

    def test_zero_run_trigger_schedule_degrades_when_history_is_too_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 10)
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, observed_market_days=3, disclosed_rows=10)
            report = _build(paths)

        schedule = report["zero_run_trigger_schedule"]
        self.assertEqual(schedule["status"], "insufficient_history")
        self.assertTrue(all(row["status"] == "insufficient_history" for row in schedule["windows"]))
        self.assertIsNone(schedule["first_regime_break_trigger"])
        self.assertIsNone(schedule["first_confirmation_trigger"])

    def test_zero_run_trigger_schedule_reports_missing_observed_window(self) -> None:
        schedule = stationarity._zero_run_trigger_schedule(
            match_dates=set(),
            all_dates=[],
            observed_market_days=0,
            observed_filter_matches=0,
            reference_date=date(2026, 7, 4),
        )

        self.assertEqual(schedule["status"], "insufficient_observed_zero_run")
        self.assertEqual(schedule["windows"], [])
        self.assertEqual(
            schedule["observed_filter_match_source"],
            "parity_materializer_filter_matched_selected_rows_in_window",
        )

    def test_zero_run_trigger_schedule_voids_after_post_freeze_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 20)
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, observed_market_days=13, observed_filter_matches=1, disclosed_rows=20)
            report = _build(paths)

        schedule = report["zero_run_trigger_schedule"]
        self.assertEqual(schedule["status"], "voided_by_post_freeze_match")
        self.assertTrue(schedule["voids_on_first_post_freeze_filter_match"])
        self.assertEqual(schedule["windows"], [])
        self.assertEqual(
            schedule["observed_filter_match_source"],
            "parity_materializer_filter_matched_selected_rows_in_window",
        )
        self.assertEqual(report["status"], "post_freeze_zero_within_historical_variation")

    def test_zero_run_trigger_reached_status_adds_escalation_block(self) -> None:
        def fake_zero_run(match_dates: set[str], all_dates: list[str], window_days: int) -> dict:
            return {
                "status": "ready",
                "observed_window_market_days": window_days,
                "historical_market_day_count": 60,
                "window_count": 10,
                "zero_match_window_count": 1,
                "zero_match_window_fraction": 0.04,
                "min_matches_in_any_window": 0,
                "max_matches_in_any_window": 1,
            }

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 60)
            _write_engine(paths, dates, set(dates[:10]))
            _write_artifacts(paths, observed_market_days=24, disclosed_rows=10)
            with patch.object(stationarity, "_sliding_zero_run", side_effect=fake_zero_run):
                report = _build(paths)

        self.assertEqual(report["status"], "post_freeze_zero_regime_break_trigger_reached")
        escalation = report["operator_escalation"]
        self.assertEqual(escalation["status"], "operator_question_required")
        self.assertIn("refreeze/filter-family research contract", escalation["question"])
        self.assertIn("does not authorize", escalation["non_authorization_statement"])
        self.assertIn("## Operator Escalation", stationarity.render_markdown(report))

    def test_zero_run_confirmation_status_takes_precedence(self) -> None:
        def fake_zero_run(match_dates: set[str], all_dates: list[str], window_days: int) -> dict:
            return {
                "status": "ready",
                "observed_window_market_days": window_days,
                "historical_market_day_count": 90,
                "window_count": 10,
                "zero_match_window_count": 1,
                "zero_match_window_fraction": 0.005,
                "min_matches_in_any_window": 0,
                "max_matches_in_any_window": 1,
            }

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 90)
            _write_engine(paths, dates, set(dates[:10]))
            _write_artifacts(paths, observed_market_days=41, disclosed_rows=10)
            with patch.object(stationarity, "_sliding_zero_run", side_effect=fake_zero_run):
                report = _build(paths)

        self.assertEqual(report["status"], "post_freeze_zero_regime_break_confirmed")
        self.assertEqual(report["operator_escalation"]["trigger_status"], "post_freeze_zero_regime_break_confirmed")

    def test_row_conditioned_zero_window_statistic_is_descriptive_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2024, 10, 1), 20)
            _write_engine(paths, dates, set())
            _write_artifacts(
                paths,
                observed_market_days=13,
                observed_materializer_rows=10,
                disclosed_rows=0,
            )
            report = _build(paths)

        statistic = report["row_conditioned_zero_window_statistic"]
        self.assertTrue(statistic["descriptive_only"])
        self.assertTrue(statistic["does_not_change_status_or_trigger_logic"])
        self.assertEqual(statistic["monthly_zero_precedents"][0]["month"], "2024-10")
        observed_window = next(row for row in statistic["window_summaries"] if row["window_market_days"] == 13)
        self.assertGreater(observed_window["zero_match_windows_with_at_least_observed_rows"], 0)

    def test_zero_run_trigger_schedule_monotonicity_violation_blocks_report(self) -> None:
        def fake_zero_run(match_dates: set[str], all_dates: list[str], window_days: int) -> dict:
            fraction = {3: 0.0, 13: 0.1, 14: 0.2}.get(window_days, 0.0)
            return {
                "status": "ready",
                "observed_window_market_days": window_days,
                "historical_market_day_count": 20,
                "window_count": 1,
                "zero_match_window_count": 1,
                "zero_match_window_fraction": fraction,
                "min_matches_in_any_window": 0,
                "max_matches_in_any_window": 1,
            }

        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = _market_dates(date(2026, 1, 2), 20)
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, observed_market_days=3, disclosed_rows=20)
            with patch.object(stationarity, "_sliding_zero_run", side_effect=fake_zero_run):
                report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("zero_run_trigger_schedule_monotonicity_violation", report["blockers"])
        self.assertEqual(report["zero_run_trigger_schedule"]["monotonicity_check"]["status"], "failed")

    def test_insufficient_history_blocks_stationarity_verdict_without_inventing_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, observed_market_days=3, disclosed_rows=2)
            report = _build(paths)

        self.assertEqual(report["status"], "insufficient_history_for_stationarity_verdict")
        self.assertEqual(report["zero_run_stationarity"]["historical_market_day_count"], 2)
        self.assertEqual(report["zero_run_stationarity"]["window_count"], 0)

    def test_disclosure_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, disclosed_rows=99)
            report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("historical_filtered_materializer_row_count_mismatch", report["blockers"])

    def test_zero_disclosure_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, disclosed_rows=0)
            report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("historical_filtered_materializer_row_count_mismatch", report["blockers"])

    def test_policy_hash_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"], bad_hash=True)
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, disclosed_rows=3)
            report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("policy_conditions_hash_mismatch", report["blockers"])
        self.assertFalse(report["policy_hash_checks"]["policy_conditions_hash_match"])

    def test_threshold_near_misses_only_use_non_threshold_policy_passers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
            selected = [
                _selected_row("2026-01-02", ticker="SPY", prior20=12.0),
                _selected_row("2026-01-05", ticker="SPY", prior20=9.5),
                _selected_row("2026-01-06", ticker="QQQ", prior20=9.99),
                _selected_row("2026-01-07", ticker="SPY", prior20=8.0),
            ]
            _write_json(
                paths["engine_latest"],
                {
                    "status": "frozen_13_symbol_candidate_generation_engine_ready",
                    "generated_at_utc": NOW,
                    "selected_candidate_row_count": len(selected),
                    "selected_candidates": selected,
                    "daily_candidate_generation": [{"candidate_generation_date": day} for day in dates],
                },
            )
            _write_artifacts(paths, disclosed_rows=1)
            report = _build(paths)

        summary = report["frozen_threshold_distance_summary"]
        self.assertEqual(summary["non_threshold_filter_eligible_row_count"], 3)
        self.assertEqual(summary["row_count_with_distance"], 2)
        self.assertEqual(summary["min_distance"], 0.5)
        self.assertNotIn("QQQ", {row["ticker"] for row in summary["nearest_rows"]})

    def test_blocked_latest_engine_falls_back_to_stamped_ready_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_engine(paths, dates, set(dates), latest_blocked=True)
            _write_artifacts(paths, disclosed_rows=3)
            report = _build(paths)

        self.assertEqual(report["inputs"]["historical_engine"]["source_mode"], "latest_ready_historical_engine_snapshot")
        self.assertEqual(report["historical_materializer"]["frozen_filter_match_rows"], 3)

    def test_write_outputs_and_hash_invariance_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _paths(root)
            hash_target = root / "evidence.jsonl"
            hash_target.write_text('{"row":1}\n', encoding="utf8")
            _policy(paths["policy"])
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_engine(paths, dates, set(dates))
            _write_artifacts(paths, disclosed_rows=3)
            before = stationarity._hash_snapshot((hash_target,))
            report = stationarity.build_report(
                historical_engine_dir=paths["engine_dir"],
                historical_engine_latest_path=paths["engine_latest"],
                policy_contract_path=paths["policy"],
                tracker_latest_path=paths["tracker"],
                parity_latest_path=paths["parity"],
                throughput_latest_path=paths["throughput"],
                generated_at_utc=NOW,
                hash_invariance_before=before,
                hash_invariance_paths=(hash_target,),
            )
            artifacts = stationarity.write_outputs(report, output_dir=root / "out", docs_report=root / "docs" / "stationarity.md")
            doc = (root / "docs" / "stationarity.md").read_text(encoding="utf8")

            self.assertTrue(report["hash_invariance"]["all_unchanged"])
            self.assertIn("latest_json", artifacts)
            self.assertIn("docs_report", artifacts)
            self.assertIn("Materializer Match-Rate Stationarity", doc)


if __name__ == "__main__":
    unittest.main()
