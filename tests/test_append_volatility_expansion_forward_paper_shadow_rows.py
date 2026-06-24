from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from tests import test_volatility_expansion_forward_paper_shadow_report as fixtures


NOW = "2026-06-21T12:00:00Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class VolatilityExpansionForwardPaperShadowAppendTests(unittest.TestCase):
    def _paths(self, root: Path, *, candidate_rows: list[dict], existing_rows: list[dict] | None = None) -> dict:
        paths = fixtures._base_sources(root)
        candidate_path = root / "candidate.jsonl"
        cohort_path = root / "cohort.jsonl"
        _write_jsonl(candidate_path, candidate_rows)
        if existing_rows is not None:
            _write_jsonl(cohort_path, existing_rows)
        paths["candidate_rows_path"] = candidate_path
        paths["cohort_log_path"] = cohort_path
        return paths

    def _append(self, *, candidate_rows: list[dict], existing_rows: list[dict] | None = None, **overrides):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root, candidate_rows=candidate_rows, existing_rows=existing_rows)
            paths.update(overrides)
            report = appender.build_append_report(generated_at_utc=NOW, **paths)
            cohort_text = paths["cohort_log_path"].read_text(encoding="utf8") if paths["cohort_log_path"].exists() else ""
            return report, cohort_text

    def test_append_blocks_without_operator_approval(self) -> None:
        report, cohort_text = self._append(
            candidate_rows=[fixtures._row(1, None)],
            market_window_confirmed=True,
        )

        self.assertEqual(report["status"], "blocked_missing_operator_approval")
        self.assertIn("approval_token_missing_or_invalid", report["reason_codes"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(cohort_text, "")

    def test_append_blocks_without_market_window_confirmation(self) -> None:
        report, cohort_text = self._append(
            candidate_rows=[fixtures._row(1, None)],
            approval_token=appender.APPROVAL_TOKEN,
        )

        self.assertEqual(report["status"], "blocked_market_window_not_confirmed")
        self.assertIn("market_window_not_confirmed", report["reason_codes"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(cohort_text, "")

    def test_dry_run_does_not_append_even_when_approved(self) -> None:
        report, cohort_text = self._append(
            candidate_rows=[fixtures._row(1, None)],
            approval_token=appender.APPROVAL_TOKEN,
            market_window_confirmed=True,
            dry_run=True,
        )

        self.assertEqual(report["status"], "append_ready_dry_run")
        self.assertIn("dry_run_no_append_performed", report["reason_codes"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(cohort_text, "")

    def test_approved_append_writes_candidate_rows_to_temp_cohort(self) -> None:
        report, cohort_text = self._append(
            candidate_rows=[fixtures._row(1, None)],
            approval_token=appender.APPROVAL_TOKEN,
            market_window_confirmed=True,
        )

        self.assertEqual(report["status"], "append_performed")
        self.assertTrue(report["cohort_append_performed"])
        self.assertEqual(report["appended_rows"], 1)
        self.assertTrue(report["post_append_verification"]["passed"])
        self.assertTrue(report["post_append_verification"]["checks"]["row_count_increment_matches"])
        self.assertTrue(report["post_append_verification"]["checks"]["no_duplicate_row_ids"])
        self.assertIn('"row_id":"row-1"', cohort_text)
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["promotion_ready"])

    def test_phase2_approval_token_allows_phase2_lane_scope(self) -> None:
        bullish_row = fixtures._row(
            1,
            None,
            lane_id="bullish_pullback_observation",
            ticker="AAPL",
            scanner_policy_hash=fixtures.BULLISH_POLICY_HASH,
            **fixtures._phase2_real_provenance(),
        )
        report, cohort_text = self._append(
            candidate_rows=[bullish_row],
            approval_token=appender.PHASE2_APPROVAL_TOKEN,
            market_window_confirmed=True,
            allowed_lane_ids=fixtures.report_builder.PHASE2_FROZEN_LANE_IDS,
        )

        self.assertEqual(report["status"], "append_performed")
        self.assertTrue(report["cohort_append_performed"])
        self.assertIn("bullish_pullback_observation", cohort_text)

    def test_phase2_append_blocks_fixture_rows_even_with_approval(self) -> None:
        fixture_row = fixtures._row(
            1,
            None,
            lane_id="bullish_pullback_observation",
            ticker="AAPL",
            scanner_policy_hash=fixtures.BULLISH_POLICY_HASH,
            candidate_source_mode="fixture",
            fixture_mode=True,
            source_artifact_path="tests/fixtures/phase2_forward_candidate_rows_valid.json",
            source_artifact_sha256="abc123",
            market_window_status="closed",
            captured_at_utc=NOW,
        )
        report, cohort_text = self._append(
            candidate_rows=[fixture_row],
            approval_token=appender.PHASE2_APPROVAL_TOKEN,
            market_window_confirmed=True,
            allowed_lane_ids=fixtures.report_builder.PHASE2_FROZEN_LANE_IDS,
        )

        self.assertEqual(report["status"], "blocked_candidate_validation_failed")
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])
        self.assertEqual(report["candidate_append_validation"]["append_reject_counts"]["fixture_rows_not_append_eligible"], 1)
        self.assertEqual(cohort_text, "")

    def test_append_rejects_candidate_rows_already_in_existing_cohort(self) -> None:
        existing = [fixtures._row(1, None)]
        report, cohort_text = self._append(
            candidate_rows=[fixtures._row(1, None)],
            existing_rows=existing,
            approval_token=appender.APPROVAL_TOKEN,
            market_window_confirmed=True,
        )

        self.assertEqual(report["status"], "blocked_duplicate_existing_rows")
        self.assertEqual(report["duplicate_existing_row_ids"], ["row-1"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(cohort_text.count("row-1"), 1)

    def test_append_rejects_rows_that_fail_candidate_validation(self) -> None:
        bad_row = fixtures._row(1, 2.0, quote_evidence_class="midpoint")
        report, cohort_text = self._append(
            candidate_rows=[bad_row],
            approval_token=appender.APPROVAL_TOKEN,
            market_window_confirmed=True,
        )

        self.assertEqual(report["status"], "blocked_candidate_validation_failed")
        self.assertFalse(report["candidate_append_validation"]["append_allowed"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(cohort_text, "")

    def test_append_blocks_when_required_preregistration_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root, candidate_rows=[fixtures._row(1, None)])
            paths["forward_cohort_preregistration_path"].unlink()
            report = appender.build_append_report(
                generated_at_utc=NOW,
                approval_token=appender.APPROVAL_TOKEN,
                market_window_confirmed=True,
                **paths,
            )

        self.assertEqual(report["status"], "blocked_candidate_validation_failed")
        self.assertIn("forward_preregistration_missing", report["candidate_append_validation"]["required_contract_blockers"])
        self.assertFalse(report["cohort_append_performed"])

    def test_append_blocks_when_required_schema_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root, candidate_rows=[fixtures._row(1, None)])
            paths["schema_path"].write_text("{bad", encoding="utf8")
            report = appender.build_append_report(
                generated_at_utc=NOW,
                approval_token=appender.APPROVAL_TOKEN,
                market_window_confirmed=True,
                **paths,
            )

        self.assertEqual(report["status"], "blocked_candidate_validation_failed")
        self.assertIn("cohort_schema_malformed", report["candidate_append_validation"]["required_contract_blockers"])
        self.assertFalse(report["cohort_append_performed"])


if __name__ == "__main__":
    unittest.main()
