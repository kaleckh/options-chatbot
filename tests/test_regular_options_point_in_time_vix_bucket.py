from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_vix_bucket as vix
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsPointInTimeVixBucketTests(unittest.TestCase):
    def _feature_store(self, tmp: Path, dates: list[str] | None = None) -> Path:
        dates = dates or ["2026-01-02", "2026-01-05", "2026-01-06"]
        path = tmp / "feature-store.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_feature_store",
                "status": "feature_store_built",
                "summary": {
                    "overall_status": "feature_store_built",
                    "first_shared_quote_date_et": dates[0],
                    "latest_shared_quote_date_et": dates[-1],
                    "shared_quote_date_count": len(dates),
                },
                "shared_quote_dates": dates,
            },
        )
        return path

    def _threshold_policy(self, tmp: Path) -> Path:
        path = tmp / "policy.json"
        _write_json(
            path,
            {
                "policy_id": "fixture_low_mid_vix_policy_v1",
                "bucket_threshold_source": "fixture://vix-thresholds/low-15-mid-25",
                "low_max": 15,
                "mid_max": 25,
                "frozen_at_utc": "2025-12-01T00:00:00Z",
            },
        )
        return path

    def _rows(self) -> list[dict]:
        return [
            {
                "bucket_date_et": "2026-01-02",
                "vix_value": 14.2,
                "source_name": "fixture_vix",
                "source_ref": "fixture://vix/2026-01-01",
                "source_timestamp_utc": "2026-01-01T21:15:00Z",
                "known_at_utc": "2026-01-01T21:16:00Z",
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "daily_close",
            },
            {
                "bucket_date_et": "2026-01-05",
                "vix_value": 20.0,
                "source_name": "fixture_vix",
                "source_ref": "fixture://vix/2026-01-02",
                "source_timestamp_utc": "2026-01-02T21:15:00Z",
                "known_at_utc": "2026-01-02T21:16:00Z",
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "daily_close",
            },
            {
                "bucket_date_et": "2026-01-06",
                "vix_value": 27.0,
                "source_name": "fixture_vix",
                "source_ref": "fixture://vix/2026-01-05",
                "source_timestamp_utc": "2026-01-05T21:15:00Z",
                "known_at_utc": "2026-01-05T21:16:00Z",
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "daily_close",
            },
        ]

    def test_complete_clean_fixture_is_ready(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows())
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "point_in_time_vix_bucket_ready")
        self.assertTrue(report["point_in_time_vix_low_mid_bucket_available"])
        self.assertEqual(report["coverage_pct"], 100.0)
        self.assertEqual(report["bucket_rows"][0]["vix_bucket"], "low")
        self.assertEqual(report["bucket_rows"][1]["vix_bucket"], "mid")
        self.assertFalse(report["bucket_rows"][2]["low_mid_eligible"])

    def test_missing_source_rows_fails_closed_without_inventing_rows(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            report = vix.build_report(
                source_rows_path=tmp / "missing.jsonl",
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_vix_source_missing")
        self.assertIn("point_in_time_vix_source_missing", report["blockers"])
        self.assertEqual(report["bucket_rows"], [])

    def test_missing_threshold_policy_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows())
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=tmp / "missing-policy.json",
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_vix_bucket_validation")
        self.assertIn("missing_vix_bucket_threshold_policy", report["blockers"])
        self.assertFalse(report["point_in_time_vix_low_mid_bucket_available"])

    def test_coverage_must_match_requested_feature_store_dates(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows()[:2])
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_vix_bucket_validation")
        self.assertIn("vix_bucket_date_coverage_incomplete", report["blockers"])
        self.assertIn("2026-01-06", report["missing_dates"])

    def test_daily_close_same_day_known_at_is_not_available_for_same_day_entries(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["source_timestamp_utc"] = "2026-01-02T21:15:00Z"
            rows[0]["known_at_utc"] = "2026-01-02T21:16:00Z"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_vix_bucket_validation")
        self.assertEqual(report["late_known_at_count"], 1)
        self.assertIn("known_at_after_candidate_join_cutoff", report["rejected_rows"][0]["reasons"])

    def test_intraday_row_can_pass_when_known_before_candidate_entry(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["source_frequency"] = "intraday"
            rows[0]["source_timestamp_utc"] = "2026-01-02T14:40:00Z"
            rows[0]["known_at_utc"] = "2026-01-02T14:41:00Z"
            rows[0]["candidate_entry_timestamp_utc"] = "2026-01-02T14:45:00Z"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "point_in_time_vix_bucket_ready")

    def test_leakage_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["future_realized_vol"] = 0.22
            rows[1]["option_pnl"] = 100
            rows[2]["actual"] = "leak"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertEqual(report["status"], "blocked_point_in_time_vix_bucket_validation")
        self.assertEqual(report["leakage_reject_count"], 3)
        self.assertIn("point_in_time_vix_row_validation_failed", report["blockers"])

    def test_rows_require_provenance_and_point_in_time_valid(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["source_provenance_status"] = "unknown"
            rows[1]["point_in_time_valid"] = False
            rows[2].pop("source_ref")
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        reasons = [reason for row in report["rejected_rows"] for reason in row["reasons"]]
        self.assertIn("source_provenance_status_not_trusted_local_or_contract_declared", reasons)
        self.assertIn("point_in_time_valid_not_true", reasons)
        self.assertIn("missing_required_fields", reasons)

    def test_vix_bucket_rows_are_not_profitability_proof_and_preserve_forbidden_flags(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows())
            report = vix.build_report(
                source_rows_path=source,
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )

        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["promotion_ready"])
        self.assertTrue(all(row["proof_eligible"] is False for row in report["bucket_rows"]))

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="vix-bucket") as tmp_dir:
            tmp = Path(tmp_dir)
            report = vix.build_report(
                source_rows_path=tmp / "missing.jsonl",
                threshold_policy_path=self._threshold_policy(tmp),
                feature_store_path=self._feature_store(tmp),
            )
            artifacts = vix.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "vix.md",
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "vix.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Point-in-Time VIX Bucket", (tmp / "docs" / "vix.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
