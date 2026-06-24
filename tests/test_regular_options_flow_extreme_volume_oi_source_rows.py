from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_flow_extreme_volume_oi_source_rows as generator
from scripts import build_regular_options_point_in_time_flow_extreme_input as flow_input
from workspace_tempdir import WorkspaceTempDir


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "regular_options_flow_extreme_volume_oi_source_rows"
    / "requested_dates.json"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _feature_store(tmp: Path) -> Path:
    fixture = json.loads(FIXTURE.read_text(encoding="utf8"))
    path = tmp / "feature-store.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_feature_store",
            "status": "feature_store_built",
            "shared_quote_dates": fixture["shared_quote_dates"],
            "inputs": {"symbols": fixture["underlyings"]},
            "symbol_surface_rows": [{"symbol": symbol} for symbol in fixture["underlyings"]],
        },
    )
    return path


def _playbook(tmp: Path) -> Path:
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


def _db(tmp: Path, *, data_trust: str = "trusted", volume_oi: bool = True) -> Path:
    path = tmp / "options_history.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            create table import_batches (
                id integer primary key,
                source_label text,
                data_trust text,
                imported_at_utc text
            )
            """
        )
        conn.execute(
            """
            create table option_quote_snapshots (
                id integer primary key,
                as_of_utc text,
                quote_date_et text,
                snapshot_kind text,
                underlying text,
                option_type text,
                volume integer,
                open_interest integer,
                source_batch_id integer
            )
            """
        )
        conn.execute(
            "insert into import_batches (id, source_label, data_trust, imported_at_utc) values (1, ?, ?, ?)",
            ("thetadata_opra_nbbo_1m", data_trust, "2026-01-02T22:00:00Z"),
        )
        row_id = 1
        for source_date in ("2026-01-02", "2026-01-03", "2026-01-04"):
            for underlying in ("SPY", "QQQ"):
                for option_type, base in (("call", 100), ("put", 140)):
                    for offset in range(2):
                        volume = base + offset if volume_oi else None
                        open_interest = base * 10 + offset if volume_oi else None
                        conn.execute(
                            """
                            insert into option_quote_snapshots
                            (id, as_of_utc, quote_date_et, snapshot_kind, underlying, option_type, volume, open_interest, source_batch_id)
                            values (?, ?, ?, 'intraday', ?, ?, ?, ?, 1)
                            """,
                            (
                                row_id,
                                f"{source_date}T21:00:00Z",
                                source_date,
                                underlying,
                                option_type,
                                volume,
                                open_interest,
                            ),
                        )
                        row_id += 1
        conn.commit()
    finally:
        conn.close()
    return path


class RegularOptionsFlowExtremeVolumeOiSourceRowsTests(unittest.TestCase):
    def test_generates_ready_rows_and_materializer_consumes_them(self) -> None:
        with WorkspaceTempDir(prefix="flow-oi") as tmp_dir:
            tmp = Path(tmp_dir)
            db = _db(tmp)
            report = generator.build_report(
                options_history_db_path=db,
                feature_store_path=_feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                write_source_rows_requested=True,
                generated_at_utc="2026-06-23T00:00:00Z",
            )
            artifacts = generator.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "flow-oi.md",
                source_rows_path=tmp / "source_rows.jsonl",
            )
            consumed = flow_input.build_report(
                source_rows_path=tmp / "source_rows.jsonl",
                feature_store_path=_feature_store(tmp),
                preregistered_playbook_path=_playbook(tmp),
                options_history_db_path=db,
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "flow_extreme_volume_oi_source_rows_available")
        self.assertEqual(report["source_row_count"], 6)
        self.assertEqual(report["coverage"]["date_coverage_pct"], 100.0)
        self.assertTrue(report["options_history_db"]["read_only_confirmed"])
        self.assertFalse(report["threshold_policy"]["plain_bid_ask_used_as_flow"])
        self.assertFalse(report["threshold_policy"]["quote_depth_fabricated"])
        self.assertNotIn("quote_depth_imbalance_score", report["source_rows"][0])
        self.assertIn("source_rows_jsonl", artifacts)
        self.assertEqual(consumed["status"], "point_in_time_flow_extreme_input_available")
        self.assertEqual(consumed["accepted_source_row_count"], 6)

    def test_research_grade_volume_oi_does_not_clear_trusted_source_gate(self) -> None:
        with WorkspaceTempDir(prefix="flow-oi") as tmp_dir:
            tmp = Path(tmp_dir)
            report = generator.build_report(
                options_history_db_path=_db(tmp, data_trust="research"),
                feature_store_path=_feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
            )

        self.assertEqual(report["status"], "blocked_flow_extreme_volume_oi_source_rows")
        self.assertEqual(report["source_row_count"], 0)
        self.assertIn("missing_trusted_volume_open_interest_source_rows", report["blockers"])
        self.assertIn("insufficient_date_coverage", report["blockers"])

    def test_trusted_rows_with_null_volume_oi_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="flow-oi") as tmp_dir:
            tmp = Path(tmp_dir)
            report = generator.build_report(
                options_history_db_path=_db(tmp, volume_oi=False),
                feature_store_path=_feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
            )

        self.assertEqual(report["status"], "blocked_flow_extreme_volume_oi_source_rows")
        self.assertIn("trusted_rows_have_null_volume_open_interest", report["blockers"])
        self.assertIn("missing_trusted_volume_open_interest_source_rows", report["blockers"])

    def test_blocked_report_does_not_write_source_rows(self) -> None:
        with WorkspaceTempDir(prefix="flow-oi") as tmp_dir:
            tmp = Path(tmp_dir)
            source_rows = tmp / "source_rows.jsonl"
            report = generator.build_report(
                options_history_db_path=_db(tmp, data_trust="research"),
                feature_store_path=_feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                write_source_rows_requested=True,
            )
            generator.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "flow-oi.md",
                source_rows_path=source_rows,
            )

        self.assertFalse(source_rows.exists())
        self.assertFalse(report["write_source_rows_allowed"])


if __name__ == "__main__":
    unittest.main()
