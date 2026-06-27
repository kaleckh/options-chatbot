import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_strict_forward_30_exit_evidence_plan as plan
from tests import test_regular_options_strict_forward_30_exit_completion_stager as stager_fixtures


NOW = "2026-06-27T04:30:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsStrictForward30ExitEvidencePlanTests(unittest.TestCase):
    def test_missing_cohort_waits_for_open_forward_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = plan.build_report(
                cohort_log_path=root / "missing-cohort.jsonl",
                exit_evidence_path=root / "missing-evidence.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_evidence_plan_waiting_for_open_forward_rows")
        self.assertEqual(report["pending_exit_evidence_count"], 0)
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["quotes_imported"])

    def test_open_rows_emit_required_exit_evidence_templates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            _write_jsonl(cohort, [stager_fixtures._open_phase2_row()])
            report = plan.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=root / "missing-evidence.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_evidence_plan_waiting_for_policy_exit_evidence")
        self.assertEqual(report["open_forward_entry_count"], 1)
        self.assertEqual(report["pending_exit_evidence_count"], 1)
        requirement = report["exit_requirements"][0]
        self.assertEqual(requirement["selection_id"], "phase2-aapl-open-1")
        self.assertIn("net_pnl_usd", requirement["required_exit_evidence_fields"])
        self.assertEqual(requirement["exit_evidence_template"]["selection_id"], "phase2-aapl-open-1")
        self.assertIn("do_not_write_exit_evidence_from_exit_evidence_plan", report["prohibited_actions"])

    def test_completed_rows_are_excluded_from_pending_exit_requirements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            open_row = stager_fixtures._open_phase2_row()
            completed = dict(open_row)
            completed["row_id"] = "phase2:phase2-aapl-open-1:exact_exit"
            completed["denominator_status"] = "exact_exit_captured"
            completed["exit_quote_source"] = "opra_nbbo"
            completed["exit_quote_timestamp_utc"] = "2026-06-29T19:55:00Z"
            completed["exit_bid"] = 4.4
            completed["exit_ask"] = 4.5
            completed["policy_exit_condition"] = "policy_exit_at_profit_target"
            completed["net_pnl_usd"] = 123.4
            _write_jsonl(cohort, [open_row, completed])

            report = plan.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=root / "missing-evidence.jsonl",
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_evidence_plan_no_open_rows")
        self.assertEqual(report["pending_exit_evidence_count"], 0)
        self.assertEqual(report["existing_completed_selection_count"], 1)

    def test_existing_evidence_is_flagged_for_stager_review_without_writing_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cohort = root / "cohort.jsonl"
            evidence = root / "exit-evidence.jsonl"
            _write_jsonl(cohort, [stager_fixtures._open_phase2_row()])
            _write_jsonl(evidence, [stager_fixtures._exit_evidence()])
            report = plan.build_report(
                cohort_log_path=cohort,
                exit_evidence_path=evidence,
                latest_json_path=root / "latest.json",
                docs_report_path=root / "doc.md",
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "exit_evidence_plan_existing_evidence_review_needed")
        self.assertEqual(report["open_rows_with_existing_evidence_count"], 1)
        self.assertEqual(report["exit_evidence_rows_present_count"], 1)
        self.assertFalse(report["cohort_append_performed"])
        self.assertFalse(report["evidence_mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
