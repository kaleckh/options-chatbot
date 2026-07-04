from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_forward_evidence_bar_throughput_projection as projection


NOW = "2026-07-03T23:59:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _fixture_paths(root: Path) -> dict[str, Path]:
    return {
        "policy": root / "contracts" / "policy.json",
        "bar": root / "contracts" / "bar.json",
        "tracker": root / "tracker" / "latest.json",
        "parity": root / "parity" / "latest.json",
        "throughput": root / "throughput" / "latest.json",
        "fresh": root / "fresh" / "latest.json",
    }


def _write_contracts(paths: dict[str, Path], *, bad_bar_hash: bool = False) -> None:
    policy = {
        "report_id": "regular_options_frozen_filtered_policy",
        "policy_id": "historical_filtered_candidate_policy_v1",
        "conditions": [
            {"field": "ticker", "op": "in", "value": ["SPY"]},
            {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.990605},
        ],
        "conditions_sha256": "",
    }
    policy["conditions_sha256"] = projection.tracker._conditions_sha256(projection.tracker._as_list(policy["conditions"]))
    _write_json(paths["policy"], policy)
    bar = {
        "report_id": "regular_options_filtered_forward_evidence_bar",
        "bar_id": "regular_options_filtered_forward_evidence_bar_v1",
        "requirements": {
            "min_completed_forward_paper_shadow_rows": 30,
            "min_ticker_week_clusters": 8,
            "min_calendar_months_with_rows": 3,
            "min_percent_cluster_pf_lb_5pct": 1.0,
            "min_usd_cluster_pf_lb_5pct": 1.0,
        },
        "source_policy_contract": {
            "path": str(paths["policy"]),
            "sha256": "bad" if bad_bar_hash else projection._file_hash(paths["policy"]),
        },
    }
    _write_json(paths["bar"], bar)


def _write_artifacts(
    paths: dict[str, Path],
    *,
    generated_at: str = NOW,
    market_days: int = 13,
    matched: int = 0,
    completed: int = 0,
    tracker_bar_completed: int | None = None,
    materializer_rows: int = 182,
    materializer_filter_matches: int = 0,
    parity_summary_filter_matches: int | None = None,
    drops: int = 2398,
) -> None:
    _write_json(
        paths["tracker"],
        {
            "status": "filtered_forward_paper_shadow_tracking_active",
            "generated_at_utc": generated_at,
            "forward_tracking": {
                "matched_candidate_count": matched,
                "completed_candidate_count": completed,
            },
            "forward_evidence_bar": {
                "completed_forward_rows": completed if tracker_bar_completed is None else tracker_bar_completed,
                "required_completed_forward_rows": 30,
            },
            "parity_disclosure": {
                "historical_filtered_materializer_rows": 306,
                "historical_filtered_materializer_months": 24,
            },
        },
    )
    _write_json(
        paths["parity"],
        {
            "status": "scanner_materializer_parity_diff_ready",
            "generated_at_utc": generated_at,
            "window": {"market_day_count": market_days},
            "materializer_coverage": {
                "row_count_in_window": materializer_rows,
                "filter_matched_selected_rows_in_window": materializer_filter_matches,
                "latest_materializer_date": "2026-07-02",
            },
            "summary": {
                "filtered_materializer_candidate_rows": materializer_filter_matches
                if parity_summary_filter_matches is None
                else parity_summary_filter_matches
            },
            "scheduled_scan_coverage": {"session_times_et": ["13:45:28"]},
            "boundary": {"materializer_entry_window_et": "10:10-10:25"},
            "divergence_rows": [
                {
                    "date": "2026-06-16",
                    "symbol": "SPY",
                    "divergence_class": "materializer_no_pick_scanner_pick",
                    "materializer_entry_window_et": "10:10-10:25",
                    "scheduled_session_times_et": ["13:45:28"],
                }
            ],
        },
    )
    _write_json(
        paths["throughput"],
        {
            "status": "blocked_no_same_day_phase2_natural_selections",
            "generated_at_utc": generated_at,
            "scheduled_phase2_drop_count_total": drops,
            "scheduled_phase2_scan_drop_reason_count_total": drops,
            "scheduled_phase2_drop_stage_summary": {
                "top_drop_stages": [{"stage": "option_liquidity", "count": drops}],
            },
            "scheduled_phase2_near_miss_summary": {"status": "symbol_level_near_miss_table_ready"},
        },
    )
    _write_json(
        paths["fresh"],
        {
            "status": "fresh_window_thetadata_opra_imported",
            "generated_at_utc": generated_at,
            "imported_rows": 21654,
            "protected_holdout_overlap_rows": 0,
        },
    )


def _build(paths: dict[str, Path], *, generated_at: str = NOW) -> dict:
    return projection.build_report(
        policy_contract_path=paths["policy"],
        forward_evidence_bar_contract_path=paths["bar"],
        tracker_latest_path=paths["tracker"],
        parity_latest_path=paths["parity"],
        throughput_latest_path=paths["throughput"],
        fresh_import_latest_path=paths["fresh"],
        generated_at_utc=generated_at,
    )


class ForwardEvidenceBarThroughputProjectionTests(unittest.TestCase):
    def test_zero_forward_denominator_is_unreachable_without_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(paths)
            report = _build(paths)

        self.assertEqual(report["status"], "bar_unreachable_without_state_change")
        self.assertEqual(report["denominators"]["tracker_forward_rows"]["observed_completed_rows"], 0)
        self.assertEqual(report["denominators"]["materializer_in_window_rows"]["materializer_filter_matched_selected_rows"], 0)
        self.assertEqual(report["denominators"]["scheduled_scan_drop_rows"]["scheduled_phase2_drop_count_total"], 2398)
        self.assertEqual(report["spy_2026_06_16_divergence_readback"]["status"], "spy_2026_06_16_divergence_found")
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["evidence_stores_mutated"])

    def test_zero_values_do_not_fall_back_to_nonzero_secondary_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(
                paths,
                completed=0,
                tracker_bar_completed=7,
                materializer_filter_matches=0,
                parity_summary_filter_matches=5,
            )
            report = _build(paths)

        self.assertEqual(report["denominators"]["tracker_forward_rows"]["observed_completed_rows"], 0)
        self.assertEqual(report["denominators"]["materializer_in_window_rows"]["materializer_filter_matched_selected_rows"], 0)
        self.assertEqual(report["status"], "bar_unreachable_without_state_change")

    def test_remaining_market_days_are_anchored_to_projection_reference_date(self) -> None:
        generated_at = "2026-07-07T16:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(paths, generated_at=generated_at, market_days=13, completed=2, materializer_filter_matches=2)
            report = _build(paths, generated_at=generated_at)

        cohort = report["horizon_projections"][0]
        expected_elapsed = projection._market_day_count(projection.FREEZE_DATE, projection.date(2026, 7, 7))
        self.assertEqual(cohort["observed_market_days"], 13)
        self.assertEqual(cohort["elapsed_market_days_as_of_reference"], expected_elapsed)
        self.assertEqual(cohort["remaining_market_days"], cohort["total_market_days"] - expected_elapsed)
        self.assertNotEqual(cohort["remaining_market_days"], cohort["total_market_days"] - cohort["observed_market_days"])

    def test_reachable_when_current_completed_rate_covers_both_horizons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(paths, matched=30, completed=30, materializer_filter_matches=30)
            report = _build(paths)

        self.assertEqual(report["status"], "bar_reachable_at_current_rate")
        self.assertTrue(all(row["reachable_at_current_rate"] for row in report["horizon_projections"]))

    def test_at_risk_when_rows_exist_but_current_rate_misses_a_horizon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(paths, matched=4, completed=2, materializer_filter_matches=4)
            report = _build(paths)

        self.assertEqual(report["status"], "bar_at_risk_needs_rate_increase")
        self.assertTrue(any(not row["reachable_at_current_rate"] for row in report["horizon_projections"]))

    def test_insufficient_observation_window_before_projection_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths)
            _write_artifacts(paths, market_days=3)
            report = _build(paths)

        self.assertEqual(report["status"], "insufficient_post_freeze_observation_window")

    def test_stale_input_or_hash_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture_paths(Path(tmp))
            _write_contracts(paths, bad_bar_hash=True)
            _write_artifacts(paths, generated_at="2026-06-20T00:00:00Z")
            report = _build(paths)

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("bar_source_policy_contract_hash_mismatch", report["blockers"])
        self.assertIn("tracker_latest_stale_generated_at_utc", report["blockers"])

    def test_write_outputs_creates_projection_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture_paths(root)
            _write_contracts(paths)
            _write_artifacts(paths)
            report = _build(paths)
            artifacts = projection.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            doc = (root / "doc.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Forward Evidence-Bar Throughput Projection", doc)
        self.assertIn("Separate Denominators", doc)
        self.assertIn("This report is read-only", doc)


if __name__ == "__main__":
    unittest.main()
