from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_historical_depth_selected_trades as depth


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
        "summary": {
            "shared_quote_date_count": 505,
            "first_shared_quote_date_et": "2024-05-22",
            "latest_shared_quote_date_et": "2026-06-04",
        },
    }


def _holdout() -> dict:
    return {
        "contract_id": "forward-holdout-contract",
        "status": "active",
        "protected_range": {"start_date": "2026-06-05", "date_basis": "candidate_entry_date"},
    }


class RegularOptionsHistoricalDepthSelectedTradesTests(unittest.TestCase):
    def test_row_months_only_do_not_prove_requested_calendar_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(source, {"selected_trades": [_trade("2025-08-15"), _trade("2026-03-15")]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2026-05-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_depth_selected_trades")
        self.assertFalse(report["calendar_coverage"]["zero_selection_months_explicit"])
        self.assertEqual(report["calendar_coverage"]["calendar_months_covered_count"], 2)
        self.assertIn("selected_trade_calendar_coverage_not_proven", report["blockers"])
        self.assertIn("calendar_months_covered_2_below_requested_24", report["blockers"])
        self.assertFalse(report["protected_holdout_guard"]["protected_holdout_overlap"])
        self.assertTrue(report["selected_trades"][0]["exact_priced"])
        self.assertEqual(report["selected_trades"][0]["entry_contract_resolution"], "exact_listed_spread_contract")
        self.assertEqual(report["selected_trades"][0]["fill_basis"], "imported_spread_mark")

    def test_explicit_calendar_coverage_can_include_zero_selection_months(self) -> None:
        months = ["2024-06", "2024-07", "2024-08"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(
                source,
                {
                    "calendar_coverage": {"covered_months": months},
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

        self.assertEqual(report["status"], "historical_depth_selected_trades_ready_for_audit")
        self.assertTrue(report["calendar_coverage"]["zero_selection_months_explicit"])
        self.assertEqual(report["calendar_coverage"]["zero_selection_months"], ["2024-07", "2024-08"])
        self.assertEqual(report["blockers"], [])

    def test_protected_holdout_overlap_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(
                source,
                {
                    "calendar_coverage": {"covered_months": ["2026-06"]},
                    "selected_trades": [_trade("2026-06-05")],
                },
            )
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = depth.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2026-06-01",
                window_end="2026-06-30",
                as_of_date="2026-06-30",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_depth_selected_trades")
        self.assertIn("protected_holdout_overlap_blocked", report["blockers"])
        self.assertTrue(report["protected_holdout_guard"]["protected_holdout_overlap"])


if __name__ == "__main__":
    unittest.main()
