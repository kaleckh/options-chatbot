from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_flow_extreme_input as flow_input
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsPointInTimeFlowExtremeInputTests(unittest.TestCase):
    def _feature_store(self, tmp: Path, dates: list[str] | None = None) -> Path:
        dates = dates or ["2026-01-02", "2026-01-05", "2026-01-06"]
        path = tmp / "feature-store.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_feature_store",
                "status": "feature_store_built",
                "shared_quote_dates": dates,
                "inputs": {"symbols": ["SPY", "QQQ"]},
                "symbol_surface_rows": [{"symbol": "SPY"}, {"symbol": "QQQ"}],
            },
        )
        return path

    def _playbook(self, tmp: Path) -> Path:
        path = tmp / "playbook.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_flow_extreme_ratio_backspread_playbook",
                "status": "preregistered_design_only",
                "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
            },
        )
        return path

    def _db(self, tmp: Path) -> Path:
        path = tmp / "options_history.db"
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                create table option_quote_snapshots (
                    id integer primary key,
                    as_of_utc text,
                    quote_date_et text,
                    snapshot_kind text,
                    underlying text,
                    option_type text,
                    bid real,
                    ask real,
                    volume integer,
                    open_interest integer
                )
                """
            )
        finally:
            conn.close()
        return path

    def _rows(self, dates: list[str] | None = None) -> list[dict]:
        dates = dates or ["2026-01-02", "2026-01-05", "2026-01-06"]
        rows: list[dict] = []
        for day in dates:
            for underlying, ratio in (("SPY", 1.3), ("QQQ", 0.7)):
                rows.append(
                    {
                        "input_date_et": day,
                        "underlying": underlying,
                        "flow_input_basis": "volume_open_interest",
                        "call_pressure_score": 1.2,
                        "put_pressure_score": 0.8,
                        "put_call_pressure_ratio": ratio,
                        "quote_depth_imbalance_score": 0.25,
                        "extreme_state": "call_pressure_extreme" if ratio < 1 else "put_pressure_extreme",
                        "threshold_policy_id": "fixture_static_policy_v1",
                        "source_name": "fixture_flow_source",
                        "source_ref": f"fixture://flow/{underlying}/{day}",
                        "source_timestamp_utc": "2026-01-01T21:00:00Z",
                        "known_at_utc": "2026-01-01T21:01:00Z",
                        "point_in_time_valid": True,
                        "source_provenance_status": "trusted_local_or_contract_declared",
                        "source_frequency": "prior_day_aggregate",
                    }
                )
        return rows

    def test_clean_fixture_is_available(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows(dates))
            report = flow_input.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp, dates),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "point_in_time_flow_extreme_input_available")
        self.assertEqual(report["coverage"]["covered_month_count"], 1)
        self.assertEqual(report["coverage"]["date_coverage_pct"], 100.0)
        self.assertEqual(report["accepted_source_row_count"], 6)
        self.assertEqual(report["proxy_basis"], ["volume_open_interest"])
        self.assertEqual(report["blockers"], [])

    def test_volume_open_interest_basis_does_not_require_quote_depth_score(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            rows = self._rows(dates)
            for row in rows:
                row.pop("quote_depth_imbalance_score")
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = flow_input.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp, dates),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "point_in_time_flow_extreme_input_available")
        self.assertEqual(report["accepted_source_row_count"], 6)
        self.assertIsNone(report["input_rows"][0]["quote_depth_imbalance_score"])

    def test_missing_source_fails_closed_without_inventing_flow(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            report = flow_input.build_report(
                source_rows_path=tmp / "missing.jsonl",
                feature_store_path=self._feature_store(tmp),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_flow_extreme_input")
        self.assertIn("missing_point_in_time_flow_extreme_source", report["blockers"])
        self.assertIn("missing_required_flow_fields", report["blockers"])
        self.assertEqual(report["input_rows"], [])
        self.assertTrue(report["source_inventory"]["plain_bid_ask_only_is_not_flow"])

    def test_unsupported_proxy_basis_wrong_underlying_and_leakage_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["flow_input_basis"] = "plain_bid_ask_price"
            rows[1]["underlying"] = "IWM"
            rows[2]["net_pnl_usd"] = 10
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = flow_input.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        reasons = [reason for row in report["rejected_source_rows"] for reason in row["reasons"]]
        leakage = [key for row in report["rejected_source_rows"] for key in row["leakage_keys"]]
        self.assertIn("unsupported_proxy_basis", reasons)
        self.assertIn("underlying_outside_requested_universe", reasons)
        self.assertIn("leakage_fields_present", reasons)
        self.assertIn("net_pnl_usd", leakage)
        self.assertIn("point_in_time_flow_extreme_row_validation_failed", report["blockers"])

    def test_insufficient_coverage_blocks(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows(dates[:2]))
            report = flow_input.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp, dates),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_flow_extreme_input")
        self.assertIn("insufficient_date_coverage", report["blockers"])

    def test_same_day_daily_known_at_is_rejected(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["source_timestamp_utc"] = "2026-01-02T21:00:00Z"
            rows[0]["known_at_utc"] = "2026-01-02T21:01:00Z"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = flow_input.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        reasons = [reason for row in report["rejected_source_rows"] for reason in row["reasons"]]
        self.assertIn("known_at_after_candidate_join_cutoff", reasons)

    def test_requires_no_write_mode(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            with self.assertRaises(ValueError):
                flow_input.build_report(
                    feature_store_path=self._feature_store(tmp),
                    preregistered_playbook_path=self._playbook(tmp),
                    options_history_db_path=self._db(tmp),
                    no_write=False,
                )

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="flow-input") as tmp_dir:
            tmp = Path(tmp_dir)
            report = flow_input.build_report(
                source_rows_path=tmp / "missing.jsonl",
                feature_store_path=self._feature_store(tmp),
                preregistered_playbook_path=self._playbook(tmp),
                options_history_db_path=self._db(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )
            artifacts = flow_input.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "flow.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "flow.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Flow-Extreme Input", (tmp / "docs" / "flow.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
