from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_selected_trade_depth as depth


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _trade(entry_date: str, pnl_pct: float = 10.0) -> dict:
    return {
        "entry_date": entry_date,
        "exit_date": entry_date,
        "ticker": "SPY",
        "lane_id": "alpha",
        "lane_family": "test_family",
        "direction": "call",
        "pnl_pct": pnl_pct,
        "exact_priced": True,
        "proof_grade": "trusted_intraday_opra_nbbo",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "fill_basis": "imported_spread_mark",
    }


def _feature_store() -> dict:
    return {
        "status": "feature_store_built",
        "shared_quote_dates": ["2024-06-03", "2024-07-01", "2024-08-01"],
        "summary": {
            "shared_quote_date_count": 3,
            "first_shared_quote_date_et": "2024-06-03",
            "latest_shared_quote_date_et": "2024-08-01",
        },
    }


def _holdout(start_date: str = "2026-06-05") -> dict:
    return {
        "contract_id": "forward-holdout-contract",
        "status": "active",
        "protected_range": {"start_date": start_date, "date_basis": "candidate_entry_date"},
    }


class RegularOptionsPointInTimeSelectedTradeDepthTests(unittest.TestCase):
    def test_default_trace_does_not_convert_quote_depth_to_zero_selection_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(source, {"selected_trades": [_trade("2024-06-15")]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-08-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_selected_trade_depth")
        self.assertEqual(report["calendar_coverage"]["covered_months"], ["2024-06"])
        self.assertEqual(report["calendar_coverage"]["unproven_requested_months"], ["2024-07", "2024-08"])
        self.assertFalse(report["calendar_coverage"]["zero_selection_months_explicit"])
        self.assertIn("historical_depth_no_candidate_generator_for_month", report["blockers"])
        self.assertIn("selected_trade_calendar_coverage_not_proven", report["blockers"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["canonical_multilane_latest_overwritten"])

    def test_candidate_generation_proof_makes_zero_selection_months_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(source, {"selected_trades": [_trade("2024-06-15")]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-08-31",
                as_of_date="2026-06-04",
                candidate_generation_proven=True,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "point_in_time_selected_trade_depth_ready_for_audit")
        self.assertEqual(report["calendar_coverage"]["covered_months"], ["2024-06", "2024-07", "2024-08"])
        self.assertEqual(report["calendar_coverage"]["zero_selection_months"], ["2024-07", "2024-08"])
        self.assertTrue(report["calendar_coverage"]["zero_selection_months_explicit"])
        self.assertEqual(report["blockers"], [])

    def test_source_with_explicit_calendar_coverage_is_accepted_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(
                source,
                {
                    "calendar_coverage": {
                        "status": "calendar_coverage_proven",
                        "coverage_basis": "explicit_candidate_generation_calendar_coverage",
                        "covered_months": ["2024-06", "2024-07", "2024-08"],
                    },
                    "selected_trades": [_trade("2024-06-15")],
                },
            )
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-08-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "point_in_time_selected_trade_depth_ready_for_audit")
        self.assertEqual(report["stage_status_counts"]["historical_depth_no_natural_selections_after_current_policy"], 2)

    def test_protected_holdout_overlap_blocks_even_when_generation_is_proven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(source, {"selected_trades": [_trade("2026-06-05")]})
            _write_json(
                feature,
                {
                    "status": "feature_store_built",
                    "shared_quote_dates": ["2026-06-05"],
                    "summary": {
                        "shared_quote_date_count": 1,
                        "first_shared_quote_date_et": "2026-06-05",
                        "latest_shared_quote_date_et": "2026-06-05",
                    },
                },
            )
            _write_json(holdout, _holdout("2026-06-05"))

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2026-06-01",
                window_end="2026-06-30",
                as_of_date="2026-06-30",
                candidate_generation_proven=True,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_selected_trade_depth")
        self.assertIn("historical_depth_protected_holdout_overlap_blocked", report["blockers"])
        self.assertTrue(report["protected_holdout_guard"]["protected_holdout_overlap"])


if __name__ == "__main__":
    unittest.main()
