from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_volatility_expansion_forward_paper_shadow_report as report_builder


NOW = "2026-06-18T12:00:00Z"
POLICY_HASH = "55e102c420e81c81baf8fd374b0c9c6c78c9acca349495f077b2877616b8657a"
BULLISH_POLICY_HASH = "e8af3d61712bd2fcecfed64c83b4a6a6e0cdc3a8a40ecfd71ea11031da1eecd7"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _base_sources(root: Path) -> dict[str, Path]:
    trade = {
        "generated_at_utc": NOW,
        "overall_status": "blocked_no_live_release",
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "best_current_lane_if_any": {
            "lane_id": "volatility_expansion_observation",
            "decision": "paper_shadow_collect",
            "profit_factor": 1.83,
            "avg_net_pnl_pct": 6.74,
            "fresh_exact_entry_count": 3,
            "exact_realized_pnl_count": 0,
        },
        "lane_decisions": [
            {
                "lane_id": "volatility_expansion_observation",
                "decision": "paper_shadow_collect",
                "promotion_state": "paper_probation",
                "reason_codes": ["no_exact_realized_pnl_rows"],
            }
        ],
    }
    robust = {
        "generated_at_utc": NOW,
        "overall_status": "paper_shadow_only",
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "best_candidate_if_any": {
            "candidate_id": "lane:volatility_expansion_observation",
            "lane_id": "volatility_expansion_observation",
            "decision": "paper_shadow_candidate",
            "total_exact_rows": 24,
            "holdout_rows": 0,
            "profit_factor": 1.83,
            "profit_factor_lower_bound": None,
        },
    }
    prereg = {
        "contract_id": "forward-cohort-preregistration",
        "last_updated": "2026-06-14",
        "status": "active",
        "cohort": {"frozen": True, "freeze_date": "2026-06-14", "eval_date": "2026-07-28"},
        "lanes": [
            {
                "lane_id": "volatility_expansion_observation",
                "policy_snapshot_sha256": POLICY_HASH,
                "symbols": ["SPY", "QQQ", "IWM", "DIA"],
            },
            {
                "lane_id": "bullish_pullback_observation",
                "policy_snapshot_sha256": BULLISH_POLICY_HASH,
                "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
            }
        ],
        "byte_frozen_policy_snapshot": {
            "source_file_sha256": "sourcehash",
            "lanes": {
                "volatility_expansion_observation": {"sha256": POLICY_HASH},
                "bullish_pullback_observation": {"sha256": BULLISH_POLICY_HASH},
            },
        },
    }
    schema = {
        "contract_id": "volatility-expansion-forward-paper-shadow-cohort-schema",
        "schema_version": 1,
        "record_required_fields": [
            "schema_version",
            "row_id",
            "lane_id",
            "selection_timestamp_utc",
            "selection_date",
            "scanner_run_id",
            "scanner_policy_hash",
            "denominator_status",
            "ticker",
            "contract_or_spread_key",
        ],
    }
    paths = {
        "trade_qualification_path": root / "trade.json",
        "robust_edge_path": root / "robust.json",
        "forward_cohort_preregistration_path": root / "prereg.json",
        "schema_path": root / "schema.json",
        "cohort_log_path": root / "cohort.jsonl",
    }
    _write_json(paths["trade_qualification_path"], trade)
    _write_json(paths["robust_edge_path"], robust)
    _write_json(paths["forward_cohort_preregistration_path"], prereg)
    _write_json(paths["schema_path"], schema)
    return paths


def _row(index: int, pnl: float | None = None, **overrides) -> dict:
    row = {
        "schema_version": 1,
        "row_id": f"row-{index}",
        "lane_id": "volatility_expansion_observation",
        "selection_timestamp_utc": f"2026-06-{18 + (index % 10):02d}T15:00:00Z",
        "selection_date": f"2026-06-{18 + (index % 10):02d}",
        "scanner_run_id": f"scan-{index}",
        "scanner_policy_hash": POLICY_HASH,
        "denominator_status": "exact_exit_captured" if pnl is not None else "open_waiting_policy_exit",
        "ticker": ["SPY", "QQQ", "IWM", "DIA"][index % 4],
        "contract_or_spread_key": f"spread-{index}",
        "entry_evidence_status": "exact_entry_captured",
        "entry_quote_source": "opra_nbbo",
        "entry_quote_timestamp_utc": f"2026-06-{18 + (index % 10):02d}T15:00:00Z",
        "entry_bid": 1.0,
        "entry_ask": 1.1,
        "exit_evidence_status": "exact_exit_captured" if pnl is not None else "open_waiting_policy_exit",
    }
    if pnl is not None:
        row["net_pnl_pct"] = pnl
        row["net_pnl_usd"] = pnl
        row["exit_quote_source"] = "opra_nbbo"
        row["exit_quote_timestamp_utc"] = f"{row['selection_date']}T19:55:00Z"
        row["exit_bid"] = 1.2
        row["exit_ask"] = 1.3
        row["policy_exit_condition"] = "policy_exit_at_close"
    row.update(overrides)
    return row


def _phase2_real_provenance(**overrides) -> dict:
    row = {
        "candidate_source_mode": "real_market_window_scan_picks",
        "fixture_mode": False,
        "source_artifact_path": "data/forward-tracking/scan_picks.jsonl",
        "source_artifact_sha256": "abc123",
        "market_window_status": "open",
        "captured_at_utc": NOW,
    }
    row.update(overrides)
    return row


class VolatilityExpansionForwardPaperShadowReportTests(unittest.TestCase):
    def _build(self, rows: list[dict] | None = None):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            if rows is not None:
                _write_jsonl(paths["cohort_log_path"], rows)
            return report_builder.build_report(generated_at_utc=NOW, **paths)

    def _validate_candidates(self, rows: list[dict]):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            candidate_rows_path = root / "candidate.jsonl"
            _write_jsonl(candidate_rows_path, rows)
            paths["candidate_rows_path"] = candidate_rows_path
            return report_builder.build_report(generated_at_utc=NOW, **paths)

    def test_missing_cohort_log_is_named_blocker_not_live_permission(self) -> None:
        report = self._build(rows=None)

        self.assertEqual(report["overall_status"], "cohort_log_missing_blocker")
        self.assertEqual(report["cohort_log_state"], "cohort_log_missing_blocker")
        self.assertIn("cohort_log_missing_blocker", report["warning_states"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["promotion_ready"])

    def test_denominator_counts_include_failed_and_missing_evidence_rows(self) -> None:
        rows = [
            _row(1, 12.0),
            _row(2, None, denominator_status="missed_entry_evidence_window", entry_evidence_status="missing"),
            _row(3, None, denominator_status="zero_bid_untradable", entry_evidence_status="zero_bid_untradable"),
            _row(4, None, denominator_status="stale_quote_rejected", entry_evidence_status="stale_quote_rejected"),
            _row(5, None, denominator_status="display_only_quote_rejected", entry_evidence_status="display_only_quote_rejected"),
            _row(6, None, denominator_status="fill_attempt_failed_or_incomplete", fill_attempt_status="fill_attempt_failed_or_incomplete"),
            _row(7, None, denominator_status="missing_exit_evidence", exit_evidence_status="missing_exit_evidence"),
        ]
        report = self._build(rows)

        self.assertEqual(report["counts"]["total_natural_selections"], 7)
        self.assertEqual(report["counts"]["exact_completed_forward_pnl_count"], 1)
        self.assertEqual(report["counts"]["missed_entry_evidence_count"], 1)
        self.assertEqual(report["counts"]["zero_bid_untradable_count"], 1)
        self.assertEqual(report["counts"]["stale_display_only_rejected_count"], 2)
        self.assertEqual(report["counts"]["failed_or_incomplete_fill_attempt_count"], 1)
        self.assertIn("missing_exact_entry_evidence", report["hard_fail_states"])

    def test_candidate_append_validation_allows_full_denominator_nonproof_rows(self) -> None:
        rows = [
            _row(1, 12.0),
            _row(2, None, denominator_status="exact_entry_captured", exit_evidence_status="open_waiting_policy_exit"),
            _row(3, None, denominator_status="open_waiting_policy_exit", exit_evidence_status="open_waiting_policy_exit"),
            _row(4, None, denominator_status="missed_entry_evidence_window", entry_evidence_status="missing"),
            _row(5, None, denominator_status="zero_bid_untradable", entry_evidence_status="zero_bid_untradable"),
            _row(6, None, denominator_status="stale_quote_rejected", entry_evidence_status="stale_quote_rejected"),
            _row(7, None, denominator_status="display_only_quote_rejected", entry_evidence_status="display_only_quote_rejected"),
            _row(8, None, denominator_status="fill_attempt_failed_or_incomplete", fill_attempt_status="fill_attempt_failed_or_incomplete"),
            _row(9, None, denominator_status="missing_exit_evidence", exit_evidence_status="missing_exit_evidence"),
        ]
        report = self._validate_candidates(rows)

        validation = report["candidate_append_validation"]
        self.assertTrue(report["candidate_validation_only"])
        self.assertEqual(report["overall_status"], "candidate_rows_append_validation_passed_no_append_performed")
        self.assertTrue(validation["append_allowed"])
        self.assertEqual(validation["append_ready_rows"], 9)
        self.assertEqual(validation["append_rejected_rows"], 0)
        self.assertFalse(validation["cohort_append_performed"])

    def test_phase2_candidate_append_validation_accepts_bullish_carrier_lane(self) -> None:
        row = _row(
            1,
            12.0,
            lane_id="bullish_pullback_observation",
            ticker="AAPL",
            scanner_policy_hash=BULLISH_POLICY_HASH,
            **_phase2_real_provenance(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            candidate_rows_path = root / "phase2-candidate.jsonl"
            _write_jsonl(candidate_rows_path, [row])
            paths["candidate_rows_path"] = candidate_rows_path
            report = report_builder.build_report(
                generated_at_utc=NOW,
                allowed_lane_ids=report_builder.PHASE2_FROZEN_LANE_IDS,
                **paths,
            )

        validation = report["candidate_append_validation"]
        self.assertTrue(validation["append_allowed"])
        self.assertEqual(validation["append_ready_rows"], 1)
        self.assertEqual(report["strict_reject_counts"]["non_frozen_lane"], 0)
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 1)

    def test_phase2_candidate_append_validation_rejects_fixture_provenance(self) -> None:
        row = _row(
            1,
            12.0,
            lane_id="bullish_pullback_observation",
            ticker="AAPL",
            scanner_policy_hash=BULLISH_POLICY_HASH,
            candidate_source_mode="fixture",
            fixture_mode=True,
            source_artifact_path="tests/fixtures/phase2_forward_candidate_rows_valid.json",
            source_artifact_sha256="abc123",
            market_window_status="closed",
            captured_at_utc=NOW,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            candidate_rows_path = root / "phase2-candidate.jsonl"
            _write_jsonl(candidate_rows_path, [row])
            paths["candidate_rows_path"] = candidate_rows_path
            report = report_builder.build_report(
                generated_at_utc=NOW,
                allowed_lane_ids=report_builder.PHASE2_FROZEN_LANE_IDS,
                **paths,
            )

        validation = report["candidate_append_validation"]
        self.assertFalse(validation["append_allowed"])
        self.assertEqual(validation["append_reject_counts"]["fixture_rows_not_append_eligible"], 1)
        self.assertEqual(validation["append_reject_counts"]["missing_real_source_provenance"], 1)

    def test_candidate_append_validation_accepts_utf8_bom_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            candidate_rows_path = root / "candidate.jsonl"
            candidate_rows_path.write_text("\ufeff" + json.dumps(_row(1, 12.0)), encoding="utf8")
            paths["candidate_rows_path"] = candidate_rows_path
            report = report_builder.build_report(generated_at_utc=NOW, **paths)

        validation = report["candidate_append_validation"]
        self.assertTrue(validation["append_allowed"])
        self.assertEqual(validation["append_ready_rows"], 1)

    def test_timestamp_fallback_uses_new_york_market_date_for_append_and_acceptance(self) -> None:
        row = _row(
            1,
            12.0,
            selection_date="",
            selection_timestamp_utc="2026-06-16T01:25:00Z",
            entry_quote_timestamp_utc="2026-06-16T01:25:00Z",
            exit_quote_timestamp_utc="2026-06-16T01:55:00Z",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            schema = json.loads(paths["schema_path"].read_text(encoding="utf8"))
            schema["record_required_fields"] = [
                field for field in schema["record_required_fields"] if field != "selection_date"
            ]
            _write_json(paths["schema_path"], schema)
            candidate_rows_path = root / "candidate.jsonl"
            _write_jsonl(candidate_rows_path, [row])
            paths["candidate_rows_path"] = candidate_rows_path
            report = report_builder.build_report(generated_at_utc=NOW, **paths)

        self.assertTrue(report["candidate_append_validation"]["append_allowed"])
        self.assertEqual(report["candidate_append_validation"]["append_ready_rows"], 1)
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 1)
        self.assertEqual(report["ticker_date_month_concentration"]["date"]["top_group"], "2026-06-15")

    def test_candidate_append_validation_rejects_bad_rows_before_append(self) -> None:
        rows = [
            _row(1, 2.0, row_id="dup"),
            _row(2, 2.0, row_id="dup"),
            _row(3, 2.0, lane_id="swing"),
            _row(4, 2.0, selection_date="2026-06-14", selection_timestamp_utc="2026-06-14T15:00:00Z"),
            _row(5, 2.0, denominator_status="unexpected_status"),
            _row(6, 2.0, scanner_policy_hash="changed"),
            _row(7, 2.0, entry_quote_source="lookahead_only"),
            _row(8, 2.0, quote_evidence_class="midpoint"),
        ]
        rows[0].pop("net_pnl_usd")
        report = self._validate_candidates(rows)

        validation = report["candidate_append_validation"]
        rejects = validation["append_reject_counts"]
        self.assertEqual(report["overall_status"], "candidate_rows_rejected_before_append")
        self.assertFalse(validation["append_allowed"])
        self.assertFalse(validation["cohort_append_performed"])
        self.assertEqual(rejects["duplicate_row_id"], 1)
        self.assertEqual(rejects["non_frozen_lane"], 1)
        self.assertEqual(rejects["pre_freeze_not_append_eligible"], 1)
        self.assertEqual(rejects["unknown_denominator_status"], 1)
        self.assertEqual(rejects["scanner_hash_drift"], 1)
        self.assertEqual(rejects["lookahead_source"], 1)
        self.assertEqual(rejects["exact_exit_missing_net_pnl_usd"], 1)
        self.assertEqual(rejects["exact_row_uses_non_executable_mark"], 1)

    def test_minimum_review_requires_thirty_completed_rows_and_pf_lower_bound(self) -> None:
        pnls = [2.0] * 24 + [-1.0] * 8
        rows = []
        for index, pnl in enumerate(pnls):
            month = 7 + (index // 8)
            day = 1 + (index % 8)
            date = f"2026-{month:02d}-{day:02d}"
            rows.append(_row(index, pnl, selection_date=date, selection_timestamp_utc=f"{date}T15:00:00Z"))
        report = self._build(rows)

        self.assertEqual(report["counts"]["exact_completed_forward_pnl_count"], 32)
        self.assertGreater(report["exact_realized_forward_profit_factor"], 1.0)
        self.assertIsNotNone(report["stressed_pf_lower_bound"])
        self.assertTrue(report["gates"]["minimum_review_packet_ready"])
        self.assertTrue(report["gates"]["minimum_continuation_gate_passed"])
        self.assertFalse(report["gates"]["live_trading_authorized"])
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 32)
        self.assertTrue(report["acceptance_readiness"]["positive_net_usd_pnl"])

    def test_non_executable_marks_do_not_count_for_acceptance(self) -> None:
        rows = [_row(index, 2.0, quote_evidence_class="midpoint") for index in range(32)]
        report = self._build(rows)

        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(report["strict_reject_counts"]["non_executable_mark_claimed_as_exact"], 32)

    def test_missing_usd_pnl_does_not_count_for_acceptance(self) -> None:
        rows = []
        for index in range(32):
            row = _row(index, 2.0)
            row.pop("net_pnl_usd")
            rows.append(row)
        report = self._build(rows)

        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(report["counts"]["exact_completed_forward_pnl_count"], 0)
        self.assertFalse(report["gates"]["minimum_review_packet_ready"])
        self.assertIsNone(report["exact_realized_forward_profit_factor"])
        self.assertEqual(report["strict_reject_counts"]["missing_net_pnl_usd"], 32)

    def test_missing_exact_quote_provenance_blocks_acceptance_and_append(self) -> None:
        row = _row(1, 2.0)
        row.pop("entry_quote_source")
        row.pop("exit_quote_timestamp_utc")
        row.pop("policy_exit_condition")
        report = self._validate_candidates([row])

        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(report["strict_reject_counts"]["exact_completed_missing_entry_quote_provenance"], 1)
        self.assertEqual(report["strict_reject_counts"]["exact_completed_missing_exit_quote_provenance"], 1)
        self.assertEqual(report["strict_reject_counts"]["exact_completed_missing_policy_exit_condition"], 1)
        rejects = report["candidate_append_validation"]["append_reject_counts"]
        self.assertEqual(rejects["exact_exit_missing_entry_quote_provenance"], 1)
        self.assertEqual(rejects["exact_exit_missing_exit_quote_provenance"], 1)
        self.assertEqual(rejects["exact_exit_missing_policy_exit_condition"], 1)
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])

    def test_untrusted_quote_source_blocks_exact_proof_and_append(self) -> None:
        row = _row(1, 2.0, entry_quote_source="unknown_vendor", exit_quote_source="unknown_vendor")
        report = self._validate_candidates([row])

        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(report["strict_reject_counts"]["exact_completed_missing_entry_quote_provenance"], 1)
        self.assertEqual(report["strict_reject_counts"]["exact_completed_missing_exit_quote_provenance"], 1)
        rejects = report["candidate_append_validation"]["append_reject_counts"]
        self.assertEqual(rejects["exact_entry_missing_entry_quote_provenance"], 1)
        self.assertEqual(rejects["exact_exit_missing_entry_quote_provenance"], 1)
        self.assertEqual(rejects["exact_exit_missing_exit_quote_provenance"], 1)
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])

    def test_non_frozen_lane_and_non_preregistered_symbol_are_counted(self) -> None:
        rows = [_row(1, 2.0, lane_id="swing"), _row(2, 2.0, ticker="AAPL")]
        report = self._build(rows)

        self.assertEqual(report["strict_reject_counts"]["non_frozen_lane"], 1)
        self.assertEqual(report["strict_reject_counts"]["non_preregistered_symbol"], 1)
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)

    def test_missing_required_preregistration_blocks_report_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            paths["forward_cohort_preregistration_path"].unlink()
            _write_jsonl(paths["cohort_log_path"], [_row(1, 2.0)])
            report = report_builder.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_required_contract")
        self.assertIn("forward_preregistration_missing", report["required_contract_blockers"])
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])

    def test_malformed_required_schema_blocks_report_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _base_sources(root)
            paths["schema_path"].write_text("{bad", encoding="utf8")
            _write_jsonl(paths["cohort_log_path"], [_row(1, 2.0)])
            report = report_builder.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_missing_required_contract")
        self.assertIn("cohort_schema_malformed", report["required_contract_blockers"])
        self.assertEqual(report["strict_reject_counts"]["blocked_by_required_contracts"], 1)
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])

    def test_pre_freeze_rows_do_not_count_for_acceptance(self) -> None:
        rows = [
            _row(
                index,
                2.0,
                selection_date="2026-06-14",
                selection_timestamp_utc="2026-06-14T15:00:00Z",
            )
            for index in range(32)
        ]
        report = self._build(rows)

        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(report["strict_reject_counts"]["pre_freeze_not_acceptance_eligible"], 32)

    def test_duplicate_unknown_missing_required_and_lookahead_rows_fail_acceptance(self) -> None:
        rows = [
            _row(1, 2.0, row_id="dup"),
            _row(2, 2.0, row_id="dup"),
            _row(3, 2.0, denominator_status="unexpected_status"),
            _row(4, 2.0, row_id=""),
            _row(5, 2.0, denominator_status="lookahead_only_diagnostic"),
        ]
        report = self._build(rows)

        self.assertLess(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 5)
        self.assertEqual(report["strict_reject_counts"]["duplicate_row_id"], 1)
        self.assertEqual(report["strict_reject_counts"]["unknown_denominator_status"], 2)
        self.assertEqual(report["strict_reject_counts"]["missing_required_schema_fields"], 1)
        self.assertEqual(report["strict_reject_counts"]["lookahead_claimed_as_exact"], 1)

    def test_point_pf_without_pf_lower_bound_does_not_pass(self) -> None:
        pnls = [20.0, -1.0, -1.0, -1.0]
        report = self._build([_row(index, pnl) for index, pnl in enumerate(pnls)])

        self.assertGreater(report["exact_realized_forward_profit_factor"], 1.0)
        self.assertFalse(report["gates"]["minimum_review_packet_ready"])
        self.assertFalse(report["gates"]["minimum_continuation_gate_passed"])
        self.assertIn("winner_concentration_largest_winner_failure", report["hard_fail_states"])

    def test_scanner_hash_drift_fails_closed(self) -> None:
        report = self._build([_row(1, 5.0, scanner_policy_hash="changed")])

        self.assertIn("scanner_hash_drift", report["hard_fail_states"])
        self.assertEqual(report["overall_status"], "failed_forward_paper_shadow_protocol")

    def test_single_ticker_dependency_is_flagged(self) -> None:
        rows = [_row(index, 2.0 if index < 20 else -1.0, ticker="SPY") for index in range(32)]
        report = self._build(rows)

        self.assertIn("single_ticker_dependency", report["hard_fail_states"])


if __name__ == "__main__":
    unittest.main()
