from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_structure_specific_harness as harness


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsStructureSpecificHarnessTests(unittest.TestCase):
    def test_build_report_groups_structure_rows_without_promoting_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fill_attempts.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "logged_at": "2026-06-05T14:43:50Z",
                        "scan_date": "2026-06-05",
                        "playbook_id": "volatility_expansion_observation",
                        "ticker": "QQQ",
                        "direction": "call",
                        "strategy_type": "vertical_spread",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_status": "auto_tracked",
                        "fill_outcome": "paper_fill_recorded",
                        "filled_price": 9.04,
                        "auto_track_position_id": 537,
                        "selection_source": "live_chain_exact_contract",
                        "selected_spread": {
                            "ticker": "QQQ",
                            "strategy_type": "vertical_spread",
                            "long_contract_symbol": "QQQ260618C00728000",
                            "short_contract_symbol": "QQQ260618C00750000",
                            "legs": [{"role": "long"}, {"role": "short"}],
                        },
                        "top_alternatives": [{"rank": 1}],
                    },
                    {
                        "event_type": "candidate_shown",
                        "logged_at": "2026-06-05T14:45:00Z",
                        "scan_date": "2026-06-05",
                        "playbook_id": "diagnostic_single_leg",
                        "ticker": "SPY",
                        "direction": "put",
                        "strategy_type": "long_put",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_status": "not_submitted_auto_track_disabled",
                        "fill_outcome": "not_submitted",
                        "selection_source": "live_chain_exact_contract",
                        "selected_spread": {
                            "ticker": "SPY",
                            "strategy_type": "long_put",
                            "contract_symbol": "SPY260618P00700000",
                            "legs": [{"role": "long"}],
                        },
                    },
                    {"event_type": "historical_backfill_candidate_shown", "strategy_type": "vertical_spread"},
                ],
            )

            report = harness.build_report(
                fill_attempts_path=fills,
                minute_exit_replay_path=root / "missing_minute_exit.json",
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["status"], "structure_specific_harness_built_collecting")
        self.assertFalse(report["summary"]["live_policy_change"])
        self.assertEqual(report["summary"]["candidate_shown_count"], 2)
        self.assertEqual(report["summary"]["proof_live_exact_entry_count"], 2)
        self.assertEqual(report["summary"]["paper_fill_recorded_count"], 1)
        self.assertEqual(report["summary"]["true_structure_specific_pnl_count"], 0)
        self.assertEqual(report["summary"]["structure_bucket_counts"]["vertical_spread"], 1)
        self.assertEqual(report["summary"]["structure_bucket_counts"]["single_leg"], 1)
        self.assertIn("true_structure_specific_pnl_rows_missing", report["summary"]["blockers"])
        self.assertNotIn("multi_leg_structure_harness_missing", report["summary"]["blockers"])
        rows = {(row["structure_bucket"], row["strategy_type"]): row for row in report["structure_harness_rows"]}
        self.assertEqual(rows[("vertical_spread", "vertical_spread")]["top_alternative_count"], 1)
        self.assertEqual(rows[("single_leg", "long_put")]["candidate_shown_count"], 1)
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertIn("collect_structure_specific_exact_entry_exit_pnl", actions)

    def test_missing_fill_attempts_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = harness.build_report(
                fill_attempts_path=root / "missing.jsonl",
                minute_exit_replay_path=root / "missing_minute_exit.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("fill_attempts", report["summary"]["missing_required_inputs"])

    def test_exact_minute_replay_creates_read_only_structure_pnl_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fill_attempts.jsonl"
            minute = root / "minute_exit.json"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "scan_date": "2026-06-05",
                        "playbook_id": "volatility_expansion_observation",
                        "ticker": "QQQ",
                        "strategy_type": "vertical_spread",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_status": "auto_tracked",
                        "fill_outcome": "paper_fill_recorded",
                        "filled_price": 9.0405,
                        "auto_track_position_id": 537,
                        "selected_spread": {
                            "long_contract_symbol": "QQQ260618C00728000",
                            "short_contract_symbol": "QQQ260618C00750000",
                            "strategy_type": "vertical_spread",
                        },
                    }
                ],
            )
            quote_base = {
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "source_label": "thetadata_opra_nbbo_1m",
            }
            _write_json(
                minute,
                {
                    "status": "minute_exit_replay_coverage_ready",
                    "generated_at_utc": "2026-06-08T00:00:00Z",
                    "minute_exit_replay_rows": [
                        {
                            "auto_track_position_id": 537,
                            "scan_date": "2026-06-05",
                            "lane": "volatility_expansion_observation",
                            "ticker": "QQQ",
                            "long_contract_symbol": "QQQ260618C00728000",
                            "short_contract_symbol": "QQQ260618C00750000",
                            "entry_pair_complete": True,
                            "exit_pair_complete": True,
                            "true_side_aware_pnl_available": True,
                            "entry_quote_date_et": "2026-06-05",
                            "entry_quote_minute_et": 639,
                            "exit_quote_date_et": "2026-06-05",
                            "exit_quote_minute_et": 955,
                            "entry_long_quote": {
                                **quote_base,
                                "contract_symbol": "QQQ260618C00728000",
                                "as_of_utc": "2026-06-05T14:39:00Z",
                                "bid": 11.77,
                                "ask": 11.85,
                            },
                            "entry_short_quote": {
                                **quote_base,
                                "contract_symbol": "QQQ260618C00750000",
                                "as_of_utc": "2026-06-05T14:39:00Z",
                                "bid": 3.17,
                                "ask": 3.22,
                            },
                            "exit_long_quote": {
                                **quote_base,
                                "contract_symbol": "QQQ260618C00728000",
                                "as_of_utc": "2026-06-05T19:55:00Z",
                                "bid": 6.13,
                                "ask": 6.5,
                            },
                            "exit_short_quote": {
                                **quote_base,
                                "contract_symbol": "QQQ260618C00750000",
                                "as_of_utc": "2026-06-05T19:55:00Z",
                                "bid": 1.41,
                                "ask": 1.47,
                            },
                            "entry_side_aware_debit": 8.68,
                            "exit_side_aware_value": 4.66,
                            "gross_pnl_per_spread": -4.02,
                            "gross_pnl_pct": -46.31,
                            "contract_quantity": 1,
                            "fees_slippage_assumption": "gross replay: no extra fees or slippage beyond side-aware bid/ask execution prices",
                            "decision": "hold_for_current_open_risk_review",
                            "decision_reason": "historical minute replay is exact and executable, but open-risk resolution still requires fresh current exit evidence",
                            "readiness_status": "position_seed_ready_engine_missing",
                            "row_index": 11,
                        }
                    ],
                },
            )

            report = harness.build_report(
                fill_attempts_path=fills,
                minute_exit_replay_path=minute,
                generated_at_utc="2026-06-08T00:00:00Z",
            )

        self.assertEqual(report["summary"]["true_structure_specific_pnl_count"], 1)
        self.assertEqual(
            report["summary"]["structure_pnl_decision_counts"],
            {"hold_for_current_open_risk_review": 1},
        )
        self.assertNotIn("true_structure_specific_pnl_rows_missing", report["summary"]["blockers"])
        self.assertEqual(len(report["structure_pnl_rows"]), 1)
        pnl_row = report["structure_pnl_rows"][0]
        self.assertTrue(pnl_row["true_executable_pnl"])
        self.assertFalse(pnl_row["production_proof"])
        self.assertEqual(pnl_row["entry_long_quote"]["source_label"], "thetadata_opra_nbbo_1m")
        self.assertEqual(pnl_row["gross_pnl_per_spread"], -4.02)
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertNotIn("collect_structure_specific_exact_entry_exit_pnl", actions)

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fill_attempts.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "strategy_type": "vertical_spread",
                        "selected_spread": {"long_contract_symbol": "A", "short_contract_symbol": "B"},
                    }
                ],
            )
            report = harness.build_report(
                fill_attempts_path=fills,
                minute_exit_replay_path=root / "missing_minute_exit.json",
                generated_at_utc="2026-06-06T00:00:00Z",
            )
            artifacts = harness.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-structure-specific-harness.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], harness.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
