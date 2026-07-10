from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_historical_simulated_forward_audit as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _trade(entry_date: str, pnl_pct: float, *, ticker: str = "SPY") -> dict:
    return {
        "entry_date": entry_date,
        "exit_date": entry_date,
        "ticker": ticker,
        "lane_id": "alpha",
        "lane_family": "test_family",
        "direction": "call",
        "pnl_pct": pnl_pct,
        "net_pnl_usd": pnl_pct * 10.0,
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


class RegularOptionsHistoricalSimulatedForwardAuditTests(unittest.TestCase):
    def test_trade_value_prefers_fee_adjusted_net_return(self) -> None:
        row = {
            "pnl_pct": 12.0,
            "gross_pnl_pct": 12.0,
            "net_pnl_pct": 11.0,
            "net_pnl_pct_after_fees": 9.5,
        }

        self.assertEqual(audit._trade_value(row), 9.5)

    def test_current_shape_blocks_when_selected_trade_history_is_shorter_than_requested_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            rows = []
            for month in ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]:
                rows.append(_trade(f"{month}-15", 10.0))
            _write_json(source, {"selected_trades": rows})
            _write_json(feature, _feature_store())

            report = audit.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                bootstrap_draws=50,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_simulated_forward_audit")
        self.assertEqual(report["selected_trade_history"]["available_entry_month_count"], 8)
        self.assertEqual(report["split"]["train_months"], ["2025-08", "2025-09", "2025-10", "2025-11"])
        self.assertEqual(report["split"]["audit_months"], ["2025-12", "2026-01", "2026-02", "2026-03"])
        self.assertIn("selected_trade_months_8_below_required_24", report["blockers"])
        self.assertEqual(report["source_summary"]["feature_store_shared_quote_date_count"], 505)
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")

    def test_unproven_source_calendar_coverage_falls_back_to_selected_row_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            _write_json(
                source,
                {
                    "calendar_coverage": {
                        "status": "calendar_coverage_not_proven",
                        "coverage_basis": "row_months_only_calendar_coverage_not_proven",
                        "covered_months": ["2024-06", "2024-07", "2024-08"],
                    },
                    "selected_trades": [_trade("2024-06-15", 10.0)],
                },
            )
            _write_json(feature, _feature_store())

            report = audit.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                bootstrap_draws=50,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        history = report["selected_trade_history"]
        self.assertEqual(history["calendar_months_available_for_split"], ["2024-06"])
        self.assertEqual(history["month_coverage_basis"], "source_calendar_coverage_not_proven")
        self.assertIn("selected_trade_months_1_below_required_24", report["blockers"])

    def test_explicit_zero_selection_calendar_months_support_requested_split(self) -> None:
        months = [
            "2024-06",
            "2024-07",
            "2024-08",
            "2024-09",
            "2024-10",
            "2024-11",
            "2024-12",
            "2025-01",
            "2025-02",
            "2025-03",
            "2025-04",
            "2025-05",
            "2025-06",
            "2025-07",
            "2025-08",
            "2025-09",
            "2025-10",
            "2025-11",
            "2025-12",
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
            "2026-05",
        ]
        rows = []
        for month in ["2026-02", "2026-03"]:
            for slot in range(20):
                rows.append(_trade(f"{month}-{slot + 1:02d}", -1.0 if slot == 0 else 14.0, ticker=f"T{slot}"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            _write_json(
                source,
                {
                    "calendar_coverage": {
                        "status": "calendar_coverage_proven",
                        "coverage_basis": "explicit_candidate_generation_calendar_coverage",
                        "covered_months": months,
                        "zero_selection_months": [month for month in months if month not in {"2026-02", "2026-03"}],
                        "zero_selection_months_explicit": True,
                    },
                    "selected_trades": rows,
                },
            )
            _write_json(feature, _feature_store())

            report = audit.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                bootstrap_draws=100,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        history = report["selected_trade_history"]
        self.assertEqual(history["month_coverage_basis"], "source_explicit_calendar_coverage")
        self.assertEqual(report["split"]["train_months"], months[:20])
        self.assertEqual(report["split"]["audit_months"], ["2026-02", "2026-03", "2026-04", "2026-05"])
        self.assertEqual(history["audit_zero_selection_months"], ["2026-04", "2026-05"])
        self.assertNotIn("selected_trade_months_24_below_required_24", report["blockers"])
        self.assertNotIn("train_calendar_months_2_below_20", report["blockers"])
        self.assertNotIn("audit_calendar_months_2_below_4", report["blockers"])
        self.assertEqual(report["metrics"]["simulated_forward_audit"]["exact_trade_count"], 40)
        self.assertEqual(report["status"], "historical_simulated_forward_audit_passed")

    def test_requested_twenty_plus_four_split_can_pass_when_source_history_supports_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            rows = []
            year = 2024
            month = 1
            for month_index in range(24):
                month_key = f"{year:04d}-{month:02d}"
                for slot in range(10):
                    rows.append(_trade(f"{month_key}-{slot + 1:02d}", -1.0 if slot == 0 else 12.0, ticker=f"T{slot}"))
                month += 1
                if month > 12:
                    year += 1
                    month = 1
            _write_json(source, {"selected_trades": rows})
            _write_json(feature, _feature_store())

            report = audit.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                bootstrap_draws=100,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_simulated_forward_audit_passed")
        self.assertEqual(report["split"]["train_months"][0], "2024-01")
        self.assertEqual(report["split"]["audit_months"], ["2025-09", "2025-10", "2025-11", "2025-12"])
        self.assertEqual(report["metrics"]["train"]["entry_month_count"], 20)
        self.assertEqual(report["metrics"]["simulated_forward_audit"]["entry_month_count"], 4)
        self.assertEqual(report["metrics"]["simulated_forward_audit"]["exact_trade_count"], 40)
        self.assertEqual(report["selected_trade_history"]["duplicate_rows_removed"], 0)
        self.assertIn("bootstrap_iid", report["metrics"]["simulated_forward_audit"])
        self.assertIn("bootstrap_cluster", report["metrics"]["simulated_forward_audit"])
        self.assertGreater(report["metrics"]["simulated_forward_audit"]["bootstrap_cluster"]["pf_lb_5pct"], 1.0)
        self.assertEqual(report["blockers"], [])

    def test_dedupes_same_date_ticker_direction_before_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            duplicate = _trade("2026-01-15", 10.0, ticker="AAPL")
            _write_json(
                source,
                {
                    "selected_trades": [
                        duplicate,
                        {**duplicate, "lane_id": "zzz_duplicate_lane", "long_contract_symbol": "ZZZ"},
                    ]
                },
            )
            _write_json(feature, _feature_store())

            report = audit.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                train_months=1,
                audit_months=1,
                bootstrap_draws=20,
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        history = report["selected_trade_history"]
        self.assertEqual(history["accepted_exact_candidate_rows_before_dedupe"], 2)
        self.assertEqual(history["deduped_row_count"], 1)
        self.assertEqual(history["duplicate_rows_removed"], 1)
        self.assertIn("cross_lane_allocation_policy_missing", report["blockers"])
        self.assertFalse(report["allocation_policy"]["combined_portfolio_unbiased"])
        self.assertEqual(report["allocation_policy"]["collision_group_count"], 1)
        self.assertEqual(report["allocation_policy"]["rows_removed_by_lexical_dedupe"], 1)
        self.assertEqual(
            report["allocation_policy"]["dedupe_rule"],
            "lexical_lane_then_contract_diagnostic_only",
        )


if __name__ == "__main__":
    unittest.main()
