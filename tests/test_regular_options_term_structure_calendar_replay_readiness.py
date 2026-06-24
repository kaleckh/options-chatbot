from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_term_structure_calendar_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class RegularOptionsTermStructureCalendarReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "latest.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_term_structure_calendar_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
            },
        )
        return path

    def _partial_evidence_file(self, tmp: Path) -> Path:
        path = tmp / "evidence.py"
        _write_text(
            path,
            """
LANES = ["calendar_volatility", "pmcc_diagonal"]
source_label = "thetadata_opra_nbbo_1m"
quote_evidence_class = "trusted_intraday_opra_nbbo"
symbols = ["SPY", "QQQ"]
market_regime = "bullish"
vix_symbol = "^VIX"
expiration = "2026-06-19"
time_exit_day = 10
net_pnl_usd = 100.0
fee_total_usd = 2.0
protected_holdout_consumed = False
proof_eligible = False
strict_new_trade_count = 0
""",
        )
        return path

    def test_report_is_read_only_and_blocks_partial_readiness(self) -> None:
        with WorkspaceTempDir(prefix="term-calendar-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                evidence_paths=[self._partial_evidence_file(tmp)],
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["accepted_profitability"])
        self.assertIn("missing_calendar_diagonal_side_aware_pricing_engine", report["blockers"])
        self.assertIn("missing_calendar_diagonal_exit_or_expiry_engine", report["blockers"])
        self.assertIn("missing_full_denominator_status_mapping", report["blockers"])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="term-calendar-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(
                invalid,
                {
                    "status": "implemented",
                    "concept_id": "wrong",
                    "structure": "wrong",
                    "accepted_profitability": True,
                    "historical_replay_performed": True,
                    "lane_implementation_performed": True,
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=invalid,
                evidence_paths=[self._partial_evidence_file(tmp)],
            )

        self.assertEqual(report["status"], "blocked_invalid_term_structure_calendar_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_exact_evidence_can_reach_ready_for_approval_question(self) -> None:
        with WorkspaceTempDir(prefix="term-calendar-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            exact = tmp / "exact.py"
            _write_text(
                exact,
                """
entry_debit = long_back_month_ask - short_front_month_bid
exit_value = long_back_month_bid - short_front_month_ask
front_leg_expiry_value = policy_defined_intrinsic_or_settlement_value_for_short_front_leg
statuses = ["rejected_term_structure", "missing_leg_quote", "exact_entry_captured", "front_leg_expired", "assignment_or_expiration_blocked", "exact_exit_captured", "missing_exit"]
front_leg_assignment_expiration_classifier = True
open_waiting_policy_exit_or_expiry = True
fee_total_usd = entry_fee_total_usd + exit_fee_total_usd
net_pnl_usd = (exit_value - entry_debit) * 100 - fee_total_usd
point_in_time_vix_bucket = "low_mid"
point_in_time_term_structure = "dislocated"
term_structure_inputs_ready = True
calendar_diagonal_quote_surface_ready = True
multi_expiry_quote_surface_ready = True
source_label = "thetadata_opra_nbbo_1m"
quote_evidence_class = "trusted_intraday_opra_nbbo"
symbols = ["SPY", "QQQ"]
protected_holdout_consumed = False
strict_new_dedupe_ready = True
strict_new_trade_count = 0
proof_eligible = False
production proof is forbidden
""",
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                evidence_paths=[exact],
            )

        self.assertEqual(report["status"], "ready_for_research_only_implementation_approval_question")
        self.assertEqual(report["blockers"], [])
        statuses = {row["prerequisite_id"]: row["status"] for row in report["critical_prerequisites"]}
        self.assertTrue(all(status == "ready" for status in statuses.values()))

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="term-calendar-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                evidence_paths=[self._partial_evidence_file(tmp)],
            )
            artifacts = readiness.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "readiness.md",
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "readiness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Term Structure Calendar Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
