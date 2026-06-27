import json
import tempfile
import unittest
from pathlib import Path

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import build_regular_options_strict_forward_30_lifecycle_audit as audit
from tests import test_volatility_expansion_forward_paper_shadow_report as fixtures


NOW = "2026-06-27T02:45:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _phase2_row(index: int, pnl: float | None = None, **overrides) -> dict:
    row = fixtures._row(
        index,
        pnl,
        lane_id="bullish_pullback_observation",
        ticker="AAPL",
        scanner_policy_hash=fixtures.BULLISH_POLICY_HASH,
        **fixtures._phase2_real_provenance(),
    )
    row["selection_id"] = overrides.pop("selection_id", f"sel-{index}")
    status = "exact_exit_captured" if pnl is not None else "open_waiting_policy_exit"
    row["row_id"] = overrides.pop("row_id", f"phase2:{row['selection_id']}:{status}")
    row.update(overrides)
    return row


class RegularOptionsStrictForward30LifecycleAuditTests(unittest.TestCase):
    def test_missing_cohort_waits_for_first_entry_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = audit.build_report(
                cohort_log_path=root / "missing.jsonl",
                schema_path=fixtures._base_sources(root)["schema_path"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "lifecycle_waiting_for_first_entry_row")
        self.assertEqual(report["strict_forward_rows"], 0)
        self.assertTrue(report["append_only_completion_policy"]["open_entry_rows_may_be_completed_by_later_exact_exit_rows"])

    def test_open_rows_wait_for_policy_exit_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = fixtures._base_sources(root)
            cohort = root / "cohort.jsonl"
            _write_jsonl(cohort, [_phase2_row(1, None)])
            report = audit.build_report(cohort_log_path=cohort, schema_path=paths["schema_path"], generated_at_utc=NOW)

        self.assertEqual(report["status"], "lifecycle_waiting_for_policy_exit_evidence")
        self.assertEqual(report["lifecycle"]["waiting_for_exact_exit_count"], 1)
        self.assertEqual(report["lifecycle"]["completed_selection_count"], 0)

    def test_later_exact_exit_row_with_same_selection_completes_without_rewriting_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = fixtures._base_sources(root)
            cohort = root / "cohort.jsonl"
            open_row = _phase2_row(1, None, selection_id="same-selection")
            exit_row = _phase2_row(2, 12.0, selection_id="same-selection")
            _write_jsonl(cohort, [open_row])
            candidate = root / "candidate.jsonl"
            _write_jsonl(candidate, [exit_row])

            append_report = appender.build_append_report(
                candidate_rows_path=candidate,
                cohort_log_path=cohort,
                schema_path=paths["schema_path"],
                trade_qualification_path=paths["trade_qualification_path"],
                robust_edge_path=paths["robust_edge_path"],
                forward_cohort_preregistration_path=paths["forward_cohort_preregistration_path"],
                allowed_lane_ids=fixtures.report_builder.PHASE2_FROZEN_LANE_IDS,
                approval_token=appender.PHASE2_APPROVAL_TOKEN,
                market_window_confirmed=True,
                generated_at_utc=NOW,
            )
            lifecycle_report = audit.build_report(cohort_log_path=cohort, schema_path=paths["schema_path"], generated_at_utc=NOW)

        self.assertEqual(append_report["status"], "append_performed")
        self.assertEqual(append_report["duplicate_existing_row_ids"], [])
        self.assertEqual(lifecycle_report["lifecycle"]["completion_rows_after_entry_count"], 1)
        self.assertEqual(lifecycle_report["strict_forward_rows"], 1)

    def test_duplicate_exact_exit_selection_blocks_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = fixtures._base_sources(root)
            cohort = root / "cohort.jsonl"
            rows = [
                _phase2_row(1, 12.0, selection_id="dup-exit", row_id="exit-1"),
                _phase2_row(2, 8.0, selection_id="dup-exit", row_id="exit-2"),
            ]
            _write_jsonl(cohort, rows)
            report = audit.build_report(cohort_log_path=cohort, schema_path=paths["schema_path"], generated_at_utc=NOW)

        self.assertEqual(report["status"], "lifecycle_duplicate_exact_exit_blocked")
        self.assertEqual(report["lifecycle"]["malformed_duplicate_exact_exit_count"], 1)

    def test_write_outputs_creates_lifecycle_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = {
                "report_id": audit.REPORT_ID,
                "generated_at_utc": NOW,
                "status": "lifecycle_waiting_for_first_entry_row",
                "strict_forward_rows": 0,
                "required_rows": 30,
                "remaining_rows": 30,
                "accepted_profitability": False,
                "cohort_log_state": "cohort_log_missing_blocker",
                "lifecycle": {
                    "waiting_for_exact_exit_count": 0,
                    "completed_selection_count": 0,
                    "completion_rows_after_entry_count": 0,
                    "malformed_duplicate_exact_exit_count": 0,
                },
            }
            artifacts = audit.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "regular_options_strict_forward_30_lifecycle_audit_latest.json").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
