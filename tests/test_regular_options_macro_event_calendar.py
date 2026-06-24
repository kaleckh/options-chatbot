from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_macro_event_calendar as calendar
from workspace_tempdir import WorkspaceTempDir


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsMacroEventCalendarTests(unittest.TestCase):
    def _feature_store(self, tmp: Path) -> Path:
        path = tmp / "feature-store.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_feature_store",
                "status": "feature_store_built",
                "summary": {
                    "overall_status": "feature_store_built",
                    "first_shared_quote_date_et": "2024-05-22",
                    "latest_shared_quote_date_et": "2026-06-04",
                    "shared_quote_date_count": 505,
                },
            },
        )
        return path

    def _complete_rows(self) -> list[dict]:
        rows: list[dict] = []
        for index, category in enumerate(calendar.REQUIRED_EVENT_CATEGORIES, start=1):
            rows.append(
                {
                    "event_id": f"macro-{index}",
                    "event_category": category,
                    "event_timestamp_utc": f"2026-0{index}-15T14:00:00Z",
                    "event_date_et": f"2026-0{index}-15",
                    "known_at_utc": f"2025-12-{index:02d}T00:00:00Z",
                    "source_name": "fixture_source",
                    "source_ref": f"fixture://macro/{index}",
                    "source_retrieved_at_utc": "2025-12-01T00:00:00Z",
                    "revision_id": "fixture-revision-1",
                    "point_in_time_valid": True,
                }
            )
        return rows

    def test_complete_clean_fixture_is_ready_for_readiness_recheck(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._complete_rows())
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        self.assertEqual(report["status"], "macro_event_calendar_ready_for_readiness_recheck")
        self.assertEqual(report["missing_categories"], [])
        self.assertEqual(set(report["covered_categories"]), set(calendar.REQUIRED_EVENT_CATEGORIES))
        self.assertEqual(report["leakage_reject_count"], 0)

    def test_missing_source_rows_fails_closed_without_inventing_events(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            report = calendar.build_report(source_rows_path=tmp / "missing.jsonl", feature_store_path=self._feature_store(tmp))

        self.assertEqual(report["status"], "blocked_macro_event_calendar_source_missing")
        self.assertIn("macro_event_calendar_source_missing", report["blockers"])
        self.assertEqual(report["events"], [])

    def test_missing_categories_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._complete_rows()[:-1])
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        self.assertEqual(report["status"], "blocked_macro_event_calendar_validation")
        self.assertIn("scheduled_fed_chair_testimony", report["missing_categories"])
        self.assertIn("missing_required_macro_event_categories", report["blockers"])

    def test_known_at_after_event_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._complete_rows()
            rows[0]["known_at_utc"] = "2026-12-31T00:00:00Z"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        self.assertEqual(report["status"], "blocked_macro_event_calendar_validation")
        self.assertIn("macro_event_calendar_row_validation_failed", report["blockers"])
        self.assertIn("known_at_after_event_timestamp", report["rejected_rows"][0]["reasons"])

    def test_leakage_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._complete_rows()
            rows[0]["actual"] = "leaking value"
            rows[1]["realized_move"] = 0.012
            rows[2]["future_iv"] = 0.22
            rows[3]["pnl"] = 123
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        self.assertEqual(report["status"], "blocked_macro_event_calendar_validation")
        self.assertEqual(report["leakage_reject_count"], 4)
        self.assertTrue(all("leakage_fields_present" in row["reasons"] for row in report["rejected_rows"][:4]))

    def test_rows_require_source_provenance_and_point_in_time_valid(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._complete_rows()
            rows[0].pop("source_ref")
            rows[1].pop("source_retrieved_at_utc")
            rows[2]["point_in_time_valid"] = False
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        reasons = [reason for row in report["rejected_rows"] for reason in row["reasons"]]
        self.assertIn("missing_source_ref_or_url", reasons)
        self.assertIn("missing_source_time", reasons)
        self.assertIn("point_in_time_valid_not_true", reasons)

    def test_calendar_rows_are_not_profitability_proof_and_preserve_forbidden_flags(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._complete_rows())
            report = calendar.build_report(source_rows_path=source, feature_store_path=self._feature_store(tmp))

        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["source_rows_proof_eligible"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["promotion_ready"])
        self.assertTrue(all(row["proof_eligible"] is False for row in report["events"]))

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-calendar") as tmp_dir:
            tmp = Path(tmp_dir)
            report = calendar.build_report(source_rows_path=tmp / "missing.jsonl", feature_store_path=self._feature_store(tmp))
            artifacts = calendar.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "calendar.md",
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "calendar.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Macro-Event Calendar", (tmp / "docs" / "calendar.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
