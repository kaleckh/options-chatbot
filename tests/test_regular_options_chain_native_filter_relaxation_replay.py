from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_chain_native_filter_relaxation_replay as replay


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _exact_repair() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "status": "exact_candidate_selection_repair_readback",
        "live_policy_change": False,
        "summary": {"overall_status": "exact_candidate_selection_repair_targets_ready"},
        "repair_targets": [
            {
                "target_id": "regular_bearish_put_primary:2026-05-22",
                "lane": "regular_bearish_put_primary",
                "scan_date": "2026-05-22",
                "signal_candidate_count": 4,
                "exact_candidate_count": 0,
                "would_track_pick_count": 0,
                "top_signal_tickers": ["META", "COIN", "SBUX", "DIS"],
                "primary_repair_reason": "no_chain_native_spread_passed_current_filters",
                "exact_reject_reasons": {"no_chain_native_spread_passed_current_filters": 4},
                "next_action": "build_chain_native_filter_relaxation_replay",
            }
        ],
    }


def _zero_pick_audit() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lanes": [
            {
                "playbook": "regular_bearish_put_primary",
                "parameters": {
                    "truth_lane": "historical_imported",
                    "pricing_lane": "pessimistic",
                    "source_labels": ["thetadata_opra_nbbo_1m"],
                    "trusted_only": True,
                    "lookback_years": 2,
                },
            }
        ],
    }


def _entry_gap_results() -> list[dict]:
    scenario_rows = []
    for ticker in ["META", "COIN"]:
        scenario_rows.append(
            {
                "ticker": ticker,
                "scan_date": "2026-05-22",
                "trade_type": "put",
                "scenario_id": "current_chain_native_filters",
                "status": "no_entry_contract_quotes",
                "reject_reason": "trusted_entry_contract_quote_coverage_missing",
                "exact_chain_native_spread_count": 0,
            }
        )
        scenario_rows.append(
            {
                "ticker": ticker,
                "scan_date": "2026-05-22",
                "trade_type": "put",
                "scenario_id": "combined_broad_entry_relaxation",
                "status": "no_entry_contract_quotes",
                "reject_reason": "trusted_entry_contract_quote_coverage_missing",
                "exact_chain_native_spread_count": 0,
            }
        )
    return [
        {
            "target_id": "regular_bearish_put_primary:2026-05-22",
            "lane": "regular_bearish_put_primary",
            "scan_date": "2026-05-22",
            "signal_candidate_count_before": 4,
            "exact_candidate_count_before": 0,
            "would_track_pick_count_before": 0,
            "top_signal_tickers": ["META", "COIN", "SBUX", "DIS"],
            "primary_reject_reason": "no_chain_native_spread_passed_current_filters",
            "replay_status": "replayed",
            "replay_signal_candidate_count": 2,
            "scenario_rows": scenario_rows,
            "entry_quote_demands": [
                {
                    "target_id": "regular_bearish_put_primary:2026-05-22",
                    "lane": "regular_bearish_put_primary",
                    "scan_date": "2026-05-22",
                    "ticker": "META",
                    "option_type": "put",
                    "quote_date": "2026-05-22",
                    "entry_quote_minute_et": 610,
                    "entry_window_minutes": 5,
                    "min_expiry": "2026-05-23",
                    "max_expiry": "2026-08-20",
                    "missing_reason": "trusted_entry_contract_quote_coverage_missing",
                },
                {
                    "target_id": "regular_bearish_put_primary:2026-05-22",
                    "lane": "regular_bearish_put_primary",
                    "scan_date": "2026-05-22",
                    "ticker": "COIN",
                    "option_type": "put",
                    "quote_date": "2026-05-22",
                    "entry_quote_minute_et": 610,
                    "entry_window_minutes": 5,
                    "min_expiry": "2026-05-23",
                    "max_expiry": "2026-08-20",
                    "missing_reason": "trusted_entry_contract_quote_coverage_missing",
                },
            ],
        }
    ]


class RegularOptionsChainNativeFilterRelaxationReplayTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "exact_candidate_repair_path": root / "exact_repair.json",
            "zero_pick_audit_path": root / "zero_pick.json",
        }
        _write_json(paths["exact_candidate_repair_path"], _exact_repair())
        _write_json(paths["zero_pick_audit_path"], _zero_pick_audit())
        return paths

    def test_entry_quote_gap_replaces_filter_relaxation_with_quote_demand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = replay.build_report(
                **self._fixture(Path(tmp)),
                replay_results=_entry_gap_results(),
                generated_at_utc="2026-06-06T04:00:00Z",
            )

        self.assertEqual(report["status"], "chain_native_filter_relaxation_replay_readback")
        self.assertEqual(report["summary"]["overall_status"], "chain_native_filter_relaxation_replay_entry_quote_gap")
        self.assertEqual(report["summary"]["entry_quote_demand_count"], 2)
        self.assertEqual(report["summary"]["entry_quote_demand_tickers"], ["COIN", "META"])
        self.assertEqual(report["summary"]["relaxed_selected_chain_native_entry_spread_count"], 0)
        self.assertEqual(report["next_evidence_queue"][0]["action"], "import_or_query_chain_native_entry_contract_quotes")
        self.assertFalse(report["summary"]["promotion_ready"])
        self.assertFalse(report["live_policy_change"])

    def test_relaxed_candidates_are_diagnostic_not_promotable(self) -> None:
        results = _entry_gap_results()
        results[0]["entry_quote_demands"] = []
        results[0]["scenario_rows"] = [
            {
                "ticker": "META",
                "scan_date": "2026-05-22",
                "trade_type": "put",
                "scenario_id": "current_chain_native_filters",
                "status": "no_viable_chain_native_spread",
                "exact_chain_native_spread_count": 0,
            },
            {
                "ticker": "META",
                "scan_date": "2026-05-22",
                "trade_type": "put",
                "scenario_id": "combined_broad_entry_relaxation",
                "status": "selected_chain_native_entry_spread",
                "exact_chain_native_spread_count": 1,
                "selected_spread": {
                    "long_contract_symbol": "META260619P00600000",
                    "short_contract_symbol": "META260619P00590000",
                    "debit_pct_of_width": 80.0,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            report = replay.build_report(**self._fixture(Path(tmp)), replay_results=results)

        self.assertEqual(
            report["summary"]["overall_status"],
            "chain_native_filter_relaxation_replay_candidates_found_diagnostic_only",
        )
        self.assertEqual(report["summary"]["relaxed_selected_chain_native_entry_spread_count"], 1)
        self.assertEqual(report["next_evidence_queue"][0]["action"], "build_exact_exit_outcome_replay_for_relaxed_chain_native_candidates")
        self.assertEqual(report["next_evidence_queue"][1]["action"], "validate_chain_native_relaxation_on_later_holdout")
        self.assertFalse(report["summary"]["promotion_ready"])

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = replay.build_report(
                exact_candidate_repair_path=root / "missing_exact.json",
                zero_pick_audit_path=root / "missing_zero.json",
                replay_results=[],
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("exact_candidate_selection_repair", report["summary"]["missing_required_inputs"])
        self.assertIn("all_lanes_zero_pick_audit", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            payload = _exact_repair()
            payload["live_policy_change"] = True
            _write_json(paths["exact_candidate_repair_path"], payload)

            report = replay.build_report(**paths, replay_results=[])

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertEqual(report["summary"]["overall_status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = replay.build_report(**self._fixture(root), replay_results=_entry_gap_results())
            markdown = replay.render_markdown(report)
            artifacts = replay.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-chain-native-filter-relaxation-replay.md",
            )

            self.assertIn("Entry Quote Demands", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
