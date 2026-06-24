from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_vrp_credit_spread_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class RegularOptionsVrpCreditSpreadReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "latest.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_vrp_credit_spread_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
            },
        )
        return path

    def _evidence_file(self, tmp: Path) -> Path:
        path = tmp / "evidence.py"
        _write_text(
            path,
            """
def _condor_value():
    entry = float(short_put.bid or 0.0) - float(long_put.ask or 0.0)
    exit_debit = float(short_put.ask or 0.0) - float(long_put.bid or 0.0)
    risk_usd = max((width - entry_value) * 100.0, 1.0)
    fee_total_usd = entry_fee_total_usd + exit_fee_total_usd
    source_label = "thetadata_opra_nbbo_1m"
    quote_evidence_class = "trusted_intraday_opra_nbbo"
    symbols = ["SPY", "QQQ", "IWM", "DIA"]
    market_regime = "bullish"
    vix_symbol = "^VIX"
    protected_holdout_consumed = False
    proof_eligible = False
    # assignment near expiration requires review, not a classifier.
""",
        )
        return path

    def _ready_vix_bucket(self, tmp: Path) -> Path:
        path = tmp / "vix.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_vix_bucket",
                "status": "point_in_time_vix_bucket_ready",
                "point_in_time_vix_low_mid_bucket_available": True,
                "coverage_pct": 100.0,
                "source_rows_count": 10,
                "blockers": [],
            },
        )
        return path

    def test_report_is_read_only_and_blocks_partial_readiness(self) -> None:
        with WorkspaceTempDir(prefix="vrp-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                evidence_paths=[self._evidence_file(tmp)],
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_vrp_credit_spread_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["accepted_profitability"])
        self.assertIn("missing_credit_spread_side_aware_pricing_engine", report["blockers"])
        self.assertIn("missing_assignment_expiration_classifier", report["blockers"])
        self.assertIn("missing_index_credit_spread_quote_surface", report["blockers"])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(
                invalid,
                {
                    "status": "implemented",
                    "concept_id": "wrong",
                    "structure": "wrong",
                    "accepted_profitability": True,
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=invalid,
                evidence_paths=[self._evidence_file(tmp)],
            )

        self.assertEqual(report["status"], "blocked_invalid_vrp_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_exact_evidence_can_reach_ready_for_approval_question(self) -> None:
        with WorkspaceTempDir(prefix="vrp-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            exact = tmp / "exact.py"
            _write_text(
                exact,
                """
entry_credit = short_put_bid - long_put_ask
exit_debit = short_put_ask - long_put_bid
statuses = ["rejected_width_or_credit", "missing_leg_quote", "exact_entry_captured", "assignment_or_expiration_blocked", "missing_exit"]
assignment_expiration_classifier = True
max_loss_usd = (spread_width - entry_credit) * 100
fee_total_usd = entry_fee_total_usd + exit_fee_total_usd
net_pnl_usd = (entry_credit - exit_debit) * 100 - fee_total_usd
point_in_time_vix_bucket = "low_mid"
source_label = "thetadata_opra_nbbo_1m"
quote_evidence_class = "trusted_intraday_opra_nbbo"
credit_spread_quote_surface_ready = True
symbols = ["SPY", "QQQ", "IWM", "DIA"]
protected_holdout_consumed = False
proof_eligible = False
production proof is forbidden
""",
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                vix_bucket_path=self._ready_vix_bucket(tmp),
                evidence_paths=[exact],
            )

        self.assertEqual(report["status"], "ready_for_research_only_implementation_approval_question")
        self.assertEqual(report["blockers"], [])
        statuses = {row["prerequisite_id"]: row["status"] for row in report["critical_prerequisites"]}
        self.assertTrue(all(status == "ready" for status in statuses.values()))

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="vrp-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                evidence_paths=[self._evidence_file(tmp)],
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
            self.assertIn("Regular Options VRP Credit Spread Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
