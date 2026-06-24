from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_candidate_generation as generation


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _source_trade(entry_date: str, artifact: Path, *, ticker: str = "SPY", pnl_pct: float = 10.0) -> dict:
    return {
        "entry_date": entry_date,
        "exit_date": entry_date,
        "ticker": ticker,
        "lane_id": "alpha",
        "lane_family": "test_family",
        "direction": "call",
        "pnl_pct": pnl_pct,
        "exact_priced": True,
        "proof_grade": "trusted_intraday_opra_nbbo",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "fill_basis": "imported_spread_mark",
        "source_result_path": str(artifact),
    }


def _artifact_trade(entry_date: str, *, ticker: str = "SPY", pnl_pct: float = 10.0) -> dict:
    return {
        "date": entry_date,
        "ticker": ticker,
        "type": "call",
        "pnl_pct": pnl_pct,
        "priced": True,
        "entry_contract_resolution": "exact_listed_spread_contract",
    }


def _artifact(
    dates: list[str],
    trades: list[dict] | None = None,
    *,
    playbook: str = "sleeve_pf59_coverage_a_refill_v1",
) -> dict:
    return {
        "playbook": playbook,
        "run_at": "2026-06-21T00:00:00",
        "lookback_years": 2,
        "replay_as_of_date": "2026-06-04",
        "replay_calendar": {
            "source": "trusted_imported_shared_required_quote_dates",
            "start_date": min(dates),
            "end_date": max(dates),
        },
        "daily_selection_diagnostics": [
            {
                "date": item,
                "candidate_count": 1 if trades and any(str(trade.get("date")) == item for trade in trades) else 0,
                "selected_count": 1 if trades and any(str(trade.get("date")) == item for trade in trades) else 0,
                "preflight_passed_count": 1 if trades and any(str(trade.get("date")) == item for trade in trades) else 0,
                "preflight_rejected_count": 0,
            }
            for item in dates
        ],
        "trades": trades or [],
        "unpriced_trades": [],
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


class RegularOptionsPointInTimeCandidateGenerationTests(unittest.TestCase):
    def test_current_lane_a_source_playbook_has_replay_entrypoint(self) -> None:
        paths = generation._runner_entrypoint_paths("lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1")

        self.assertIn("scripts/run_bullish_pullback_next_round.py", paths)

    def test_existing_artifact_diagnostics_can_prove_zero_selection_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            trade = _artifact_trade("2024-06-03")
            _write_json(artifact, _artifact(["2024-06-03", "2024-07-01", "2024-08-01"], [trade]))
            _write_json(source, {"selected_trades": [_source_trade("2024-06-03", artifact)]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = generation.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-08-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "point_in_time_candidate_generation_ready_for_audit")
        self.assertEqual(report["source_reproduction_check"]["status"], "passed")
        self.assertEqual(report["calendar_coverage"]["covered_months"], ["2024-06", "2024-07", "2024-08"])
        self.assertEqual(report["calendar_coverage"]["zero_selection_months"], ["2024-07", "2024-08"])
        self.assertTrue(report["calendar_coverage"]["zero_selection_months_explicit"])
        self.assertFalse(report["canonical_multilane_latest_overwritten"])
        self.assertFalse(report["quotes_imported"])

    def test_missing_diagnostics_do_not_prove_zero_selection_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            trade = _artifact_trade("2024-06-03")
            _write_json(artifact, _artifact(["2024-06-03"], [trade]))
            _write_json(source, {"selected_trades": [_source_trade("2024-06-03", artifact)]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = generation.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-08-31",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_candidate_generation")
        self.assertEqual(report["calendar_coverage"]["covered_months"], ["2024-06"])
        self.assertEqual(report["calendar_coverage"]["unproven_requested_months"], ["2024-07", "2024-08"])
        self.assertIn("historical_depth_candidate_generation_diagnostics_missing_for_month", report["blockers"])

    def test_source_reproduction_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            _write_json(artifact, _artifact(["2024-06-03"], [_artifact_trade("2024-06-03", ticker="QQQ")]))
            _write_json(source, {"selected_trades": [_source_trade("2024-06-03", artifact, ticker="SPY")]})
            _write_json(feature, _feature_store())
            _write_json(holdout, _holdout())

            report = generation.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2024-06-01",
                window_end="2024-06-30",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_candidate_generation")
        self.assertEqual(report["source_reproduction_check"]["status"], "failed")
        self.assertIn("historical_depth_source_reproduction_failed_existing_months", report["blockers"])

    def test_protected_holdout_overlap_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.json"
            source = root / "source.json"
            feature = root / "feature.json"
            holdout = root / "holdout.json"
            trade = _artifact_trade("2026-06-05")
            _write_json(artifact, _artifact(["2026-06-05"], [trade]))
            _write_json(source, {"selected_trades": [_source_trade("2026-06-05", artifact)]})
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

            report = generation.build_report(
                source_report_path=source,
                feature_store_report_path=feature,
                source_quality_policy_path=None,
                holdout_contract_path=holdout,
                window_start="2026-06-01",
                window_end="2026-06-30",
                as_of_date="2026-06-30",
                generated_at_utc="2026-06-21T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_point_in_time_candidate_generation")
        self.assertIn("historical_depth_protected_holdout_overlap_blocked", report["blockers"])
        self.assertTrue(report["month_diagnostics"][0]["protected_holdout_overlap"])


if __name__ == "__main__":
    unittest.main()
