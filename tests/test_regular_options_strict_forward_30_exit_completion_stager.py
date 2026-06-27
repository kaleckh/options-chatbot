import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_strict_forward_30_exit_completion_stager as stager
from tests import test_volatility_expansion_forward_paper_shadow_report as fixtures


NOW = "2026-06-27T03:00:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _open_phase2_row(**overrides) -> dict:
    row = fixtures._row(
        1,
        None,
        lane_id="bullish_pullback_observation",
        ticker="AAPL",
        scanner_policy_hash=fixtures.BULLISH_POLICY_HASH,
        **fixtures._phase2_real_provenance(),
    )
    row["selection_id"] = "phase2-aapl-open-1"
    row["row_id"] = "phase2:phase2-aapl-open-1:open_waiting_policy_exit"
    row["entry_quote_source"] = "opra_nbbo"
    row["entry_quote_timestamp_utc"] = row["selection_timestamp_utc"]
    row["entry_bid"] = 3.1
    row["entry_ask"] = 3.2
    row.update(overrides)
    return row


def _exit_evidence(**overrides) -> dict:
    row = {
        "selection_id": "phase2-aapl-open-1",
        "exit_quote_source": "opra_nbbo",
        "exit_quote_timestamp_utc": "2026-06-29T19:55:00Z",
        "exit_bid": 4.4,
        "exit_ask": 4.5,
        "policy_exit_condition": "policy_exit_at_profit_target",
        "net_pnl_usd": 123.4,
        "market_window_status": "open",
        "captured_at_utc": "2026-06-29T19:55:02Z",
    }
    row.update(overrides)
    return row


class RegularOptionsStrictForward30ExitCompletionStagerTests(unittest.TestCase):
    def test_missing_cohort_waits_for_open_forward_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = stager.build_report(
                cohort_log_path=root / "missing-cohort.jsonl",
                exit_evidence_path=root / "missing-evidence.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_completion_waiting_for_open_forward_rows")
        self.assertEqual(report["candidate_rows_staged"], 0)
        self.assertFalse(report["cohort_append_performed"])

    def test_open_rows_wait_for_exit_evidence_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            _write_jsonl(cohort, [_open_phase2_row()])
            report = stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=root / "missing-evidence.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_completion_waiting_for_exit_evidence_jsonl")
        self.assertEqual(report["open_forward_entry_count"], 1)

    def test_valid_exit_evidence_stages_validation_ready_exact_exit_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            evidence = root / "exit-evidence.jsonl"
            output = root / "exit-candidates.jsonl"
            _write_jsonl(cohort, [_open_phase2_row()])
            _write_jsonl(evidence, [_exit_evidence()])

            report = stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=evidence,
                output_path=output,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )
            rows = [json.loads(line) for line in output.read_text(encoding="utf8").splitlines() if line.strip()]

        self.assertEqual(report["status"], "exit_completion_candidates_ready_no_append")
        self.assertTrue(report["append_allowed_by_validation"])
        self.assertEqual(report["candidate_rows_staged"], 1)
        self.assertEqual(rows[0]["selection_id"], "phase2-aapl-open-1")
        self.assertEqual(rows[0]["denominator_status"], "exact_exit_captured")
        self.assertNotEqual(rows[0]["row_id"], "phase2:phase2-aapl-open-1:open_waiting_policy_exit")
        self.assertFalse(report["cohort_append_performed"])
        self.assertIn("guarded_append_template", report)

    def test_rejects_exit_evidence_without_matching_open_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            evidence = root / "exit-evidence.jsonl"
            _write_jsonl(cohort, [_open_phase2_row(selection_id="different-selection")])
            _write_jsonl(evidence, [_exit_evidence()])

            report = stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=evidence,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_completion_evidence_rows_rejected")
        self.assertEqual(report["reject_counts"]["no_matching_open_forward_entry"], 1)

    def test_rejects_non_executable_exit_basis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            evidence = root / "exit-evidence.jsonl"
            _write_jsonl(cohort, [_open_phase2_row()])
            _write_jsonl(evidence, [_exit_evidence(exit_price_source="midpoint")])

            report = stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=evidence,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_completion_evidence_rows_rejected")
        self.assertEqual(report["reject_counts"]["non_executable_exit_basis"], 1)

    def test_rejects_untrusted_exit_quote_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            evidence = root / "exit-evidence.jsonl"
            _write_jsonl(cohort, [_open_phase2_row()])
            _write_jsonl(evidence, [_exit_evidence(exit_quote_source="unknown_vendor")])

            report = stager.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=evidence,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_completion_evidence_rows_rejected")
        self.assertEqual(report["reject_counts"]["untrusted_exit_quote_source"], 1)


if __name__ == "__main__":
    unittest.main()
