from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_stale_candidate_archive as archive


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _candidate_ledger() -> dict:
    stale_row = {
        "action_reason": "candidate_not_returned_by_market_hours_validation_scan",
        "blocking_reasons": ["candidate_not_returned_by_market_hours_validation_scan"],
        "candidate_key": "2026-06-04|quality90_debit55_canary|QQQ|call|2026-06-18|LONG|SHORT|743.0|770.0",
        "candidate_status": "live_validation_attempted",
        "contract_symbol": "LONG",
        "direction": "call",
        "entry_evidence_status": "fill_attempt_missing",
        "expiry": "2026-06-18",
        "fill_attempt_status": "missing",
        "lane_id": "quality90_debit55_canary",
        "ledger_key": "fresh:2026-06-04|quality90_debit55_canary|QQQ|call|2026-06-18|LONG|SHORT|743.0|770.0",
        "next_evidence_action": "wait_for_fresh_match_or_archive_candidate",
        "position_link_status": "no_tracked_or_suggested_link",
        "promotion_discussion_ready": False,
        "realized_pnl_status": "no_position_link",
        "required_next_evidence": ["fresh_executable_exact_opra_nbbo_entry"],
        "row_type": "candidate",
        "scan_date": "2026-06-04",
        "short_contract_symbol": "SHORT",
        "source_report": "fresh_evidence_loop",
        "ticker": "QQQ",
        "validation_outcome": "no_longer_matched",
    }
    return {
        "report_id": "regular_options_candidate_outcome_ledger",
        "status": "candidate_outcome_ledger_readback",
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "live_policy_change": False,
        "summary": {
            "ledger_row_count": 3,
            "action_counts": {
                "wait_for_fresh_match_or_archive_candidate": 2,
                "collect_exact_exit_evidence": 1,
            },
        },
        "ledger_rows": [
            stale_row,
            {
                **stale_row,
                "ticker": "SPY",
                "ledger_key": "fresh:2026-06-04|quality90_debit55_canary|SPY|call|2026-06-18|LONG2|SHORT2|756.0|770.0",
                "candidate_key": "2026-06-04|quality90_debit55_canary|SPY|call|2026-06-18|LONG2|SHORT2|756.0|770.0",
                "contract_symbol": "LONG2",
                "short_contract_symbol": "SHORT2",
            },
            {
                "ledger_key": "fresh:exit",
                "next_evidence_action": "collect_exact_exit_evidence",
                "ticker": "QQQ",
                "lane_id": "volatility_expansion_observation",
            },
        ],
    }


class RegularOptionsStaleCandidateArchiveTests(unittest.TestCase):
    def test_build_report_archives_no_longer_matched_candidates_without_proof_or_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate_ledger.json"
            _write_json(path, _candidate_ledger())
            report = archive.build_report(candidate_ledger_path=path, generated_at_utc="2026-06-07T03:00:00Z")

        self.assertEqual(report["status"], "stale_candidate_archive_readback")
        self.assertEqual(report["summary"]["overall_status"], "stale_candidates_archived")
        self.assertEqual(report["summary"]["source_wait_or_archive_count"], 2)
        self.assertEqual(report["summary"]["archived_no_longer_matched_candidate_count"], 2)
        self.assertEqual(report["summary"]["archive_exception_count"], 0)
        self.assertTrue(report["summary"]["archive_complete"])
        self.assertEqual(report["summary"]["production_proof_ready_count"], 0)
        self.assertFalse(report["summary"]["promotion_ready"])
        self.assertEqual(report["summary"]["lane_counts"], {"quality90_debit55_canary": 2})
        self.assertEqual(report["summary"]["ticker_counts"], {"QQQ": 1, "SPY": 1})
        self.assertEqual(report["next_evidence_queue"], [])
        for row in report["archived_candidates"]:
            self.assertEqual(row["archive_status"], "archived_no_longer_matched_candidate")
            self.assertFalse(row["production_proof_ready"])
        self.assertIn("do_not_mutate_database_from_stale_candidate_archive", report["prohibited_actions"])

    def test_missing_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = archive.build_report(candidate_ledger_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("regular_options_candidate_outcome_ledger", report["summary"]["missing_required_inputs"])
        self.assertFalse(report["summary"]["archive_complete"])

    def test_write_outputs_creates_latest_and_docs_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "candidate_ledger.json"
            _write_json(path, _candidate_ledger())
            report = archive.build_report(candidate_ledger_path=path)
            markdown = archive.render_markdown(report)
            artifacts = archive.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-stale-candidate-archive.md",
            )

            self.assertIn("Regular Options Stale Candidate Archive", markdown)
            self.assertIn("does not create trades", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
