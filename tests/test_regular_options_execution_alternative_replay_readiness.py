from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_execution_alternative_replay_readiness as readiness


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _fill_rows() -> list[dict]:
    return [
        {
            "event_type": "candidate_shown",
            "logged_at": "2026-06-05T14:43:31Z",
            "scan_date": "2026-06-05",
            "playbook_id": "volatility_expansion_observation",
            "ticker": "QQQ",
            "pricing_evidence_class": "proof_live_opra_exact_contract",
            "selection_source": "live_chain_exact_contract",
            "fill_status": "auto_tracked",
            "fill_outcome": "paper_fill_recorded",
            "auto_track_position_id": 537,
            "filled": True,
            "filled_price": 9.0405,
            "selected_spread": {
                "expiry": "2026-06-18",
                "long_contract_symbol": "QQQ260618C00728000",
                "short_contract_symbol": "QQQ260618C00750000",
                "entry_execution_price": 9.0405,
                "quote_time_utc": "2026-06-05T14:39:44Z",
                "spread_width": 22.0,
                "debit_pct_of_width": 41.1,
                "spread_bid_ask_pct_of_mid": 0.8,
            },
            "fill_degradation_vs_mid_pct": 5.49,
            "top_alternatives": [
                {
                    "rank": 1,
                    "long_contract_symbol": "QQQ260618C00728000",
                    "short_contract_symbol": "QQQ260618C00750000",
                    "net_debit": 9.0405,
                    "spread_width": 22.0,
                },
                {
                    "rank": 2,
                    "long_contract_symbol": "QQQ260618C00730000",
                    "short_contract_symbol": "QQQ260618C00752000",
                    "net_debit": 8.44,
                    "spread_width": 22.0,
                    "liquidity_first_score": 121.4,
                },
            ],
        },
        {
            "event_type": "candidate_shown",
            "logged_at": "2026-06-05T15:00:00Z",
            "playbook_id": "swing",
            "ticker": "SPY",
            "pricing_evidence_class": "proof_live_opra_exact_contract",
            "selection_source": "live_chain_exact_contract",
            "attempted_limit_price": 5.88,
            "attempted_limit_quote_time_utc": "2026-06-05T14:40:00Z",
            "selected_spread": {
                "expiry": "2026-06-26",
                "long_contract_symbol": "SPY260626C00760000",
                "short_contract_symbol": "SPY260626C00775000",
            },
            "top_alternatives": [
                {
                    "rank": 1,
                    "long_contract_symbol": "SPY260626C00760000",
                    "short_contract_symbol": "SPY260626C00775000",
                    "net_debit": 5.88,
                }
            ],
        },
        {
            "event_type": "candidate_shown",
            "playbook_id": "short_term",
            "ticker": "QQQ",
            "pricing_evidence_class": "diagnostic_midpoint",
            "selected_spread": {"long_contract_symbol": "QQQ260612C00728000"},
        },
    ]


class RegularOptionsExecutionAlternativeReplayReadinessTests(unittest.TestCase):
    def test_build_report_counts_seed_rows_without_claiming_alternative_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fills = Path(tmp) / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())

            report = readiness.build_report(
                fill_attempts_path=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["status"], "execution_alternative_replay_readiness_readback")
        self.assertEqual(report["summary"]["overall_status"], "blocked_ready_seed_missing_execution_alternative_replay_engine")
        self.assertEqual(report["summary"]["candidate_shown_count"], 3)
        self.assertEqual(report["summary"]["top_spread_replay_seed_count"], 2)
        self.assertEqual(report["summary"]["contract_replacement_seed_count"], 1)
        self.assertEqual(report["summary"]["true_top_spread_replay_pnl_count"], 0)
        self.assertEqual(report["summary"]["true_contract_replacement_pnl_count"], 0)
        self.assertIn("alternate_contract_exit_quote_coverage_missing", report["summary"]["blockers"])
        first = report["candidate_queue"][0]
        self.assertEqual(first["readiness_status"], "alternative_seed_ready_engine_missing")
        self.assertEqual(first["replacement_alternative_count"], 1)
        self.assertEqual(first["selected_long_contract_symbol"], "QQQ260618C00728000")

    def test_missing_fill_attempt_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = readiness.build_report(fill_attempts_path=Path(tmp) / "missing.jsonl")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("fill_attempts", report["summary"]["missing_required_inputs"])

    def test_rows_missing_exact_entry_or_alternatives_are_not_seed_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fills = Path(tmp) / "fills.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "ticker": "QQQ",
                        "pricing_evidence_class": "diagnostic_midpoint",
                        "selected_spread": {"long_contract_symbol": "QQQ260612C00728000"},
                    }
                ],
            )

            report = readiness.build_report(fill_attempts_path=fills)

        self.assertEqual(report["summary"]["top_spread_replay_seed_count"], 0)
        self.assertEqual(report["summary"]["blocked_missing_alternative_replay_seed_count"], 1)
        self.assertEqual(report["candidate_queue"][0]["readiness_status"], "blocked_missing_alternative_replay_seed")
        self.assertIn("entry_not_proof_live_exact_contract", report["candidate_queue"][0]["blockers"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fills = Path(tmp) / "fills.jsonl"
            rows = _fill_rows()
            rows[0]["live_policy_change"] = True
            _write_jsonl(fills, rows)

            report = readiness.build_report(fill_attempts_path=fills)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_renders_boundary_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fills = Path(tmp) / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())
            report = readiness.build_report(fill_attempts_path=fills)
            markdown = readiness.render_markdown(report)

        self.assertIn("# Regular Options Execution Alternative Replay Readiness", markdown)
        self.assertIn("## Candidate Queue", markdown)
        self.assertIn("| 0 | `build_contract_replacement_exit_survivability_replay_engine` |", markdown)
        self.assertIn("does not create trades", markdown)
        self.assertIn("does not simulate P&L", markdown)

    def test_write_outputs_creates_latest_and_timestamped_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fills.jsonl"
            _write_jsonl(fills, _fill_rows())
            report = readiness.build_report(
                fill_attempts_path=fills,
                generated_at_utc="2026-06-06T00:00:00Z",
            )

            artifacts = readiness.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-execution-alternative-replay-readiness.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], readiness.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
