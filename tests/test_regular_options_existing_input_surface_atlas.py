from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_regular_options_existing_input_surface_atlas as atlas
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _control_files(tmp: Path) -> dict[str, Path]:
    paths = {
        "oracle_packet": tmp / "oracle.json",
        "all_local_quote_atlas": tmp / "all-local.json",
        "local_quote_matrix": tmp / "matrix.json",
        "opening_replay": tmp / "opening.json",
        "synthetic_forward": tmp / "synthetic.json",
        "vix_bucket": tmp / "vix.json",
        "flow_input": tmp / "flow.json",
        "flow_volume_oi": tmp / "flow-volume.json",
        "macro_event_calendar": tmp / "macro.json",
        "dispersion_proxy": tmp / "dispersion.json",
        "pmcc_readiness": tmp / "pmcc.json",
        "base_ledger": tmp / "ledger.json",
        "forward_holdout": tmp / "holdout.json",
        "forward_cohort": tmp / "cohort.json",
        "source_quality_policy": tmp / "source-policy.json",
    }
    _write_json(paths["oracle_packet"], {"status": "ready_for_same_session_gpt55_guidance", "blockers": ["missing_daily_candidate_generation_diagnostics"]})
    _write_json(paths["all_local_quote_atlas"], {"status": "all_local_quote_surface_replayability_exhausted_under_current_data", "all_local_quote_surface_replayability_exhausted_under_current_data": True, "base_identity_hash_count": 157})
    _write_json(paths["local_quote_matrix"], {"status": "local_quote_surface_only_structures_exhausted_under_current_data"})
    _write_json(paths["opening_replay"], {"status": "blocked", "blockers": ["blocked_missing_quote_surface_underlying_price"]})
    _write_json(paths["synthetic_forward"], {"status": "blocked", "blockers": ["blocked_missing_call_put_pairs"]})
    _write_json(paths["vix_bucket"], {"status": "blocked_point_in_time_vix_source_missing", "blockers": ["point_in_time_vix_source_missing"]})
    _write_json(paths["flow_input"], {"status": "blocked_point_in_time_flow_extreme_input", "blockers": ["missing_point_in_time_flow_extreme_source"]})
    _write_json(paths["flow_volume_oi"], {"status": "blocked_flow_extreme_volume_oi_source_rows", "blockers": ["trusted_rows_have_null_volume_open_interest"]})
    _write_json(paths["macro_event_calendar"], {"status": "blocked_macro_event_calendar_source_missing", "blockers": ["macro_event_calendar_source_missing"]})
    _write_json(paths["dispersion_proxy"], {"status": "blocked_point_in_time_dispersion_concentration_proxy", "blockers": ["missing_point_in_time_dispersion_proxy_source"]})
    _write_json(paths["pmcc_readiness"], {"status": "blocked_pmcc_diagonal_replay_readiness", "blockers": ["missing_point_in_time_trend_or_regime_inputs"]})
    _write_json(paths["base_ledger"], {"status": "base_clean_stack_identity_ledger_ready", "ledger_row_count": 157})
    _write_json(paths["forward_holdout"], {"contract_id": "forward_holdout_contract", "status": "active"})
    _write_json(paths["forward_cohort"], {"contract_id": "forward_cohort_preregistration", "status": "active"})
    _write_json(paths["source_quality_policy"], {"policy_id": "regular_options_source_quality_scope_policy", "status": "active"})
    return paths


def _create_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
            source_label TEXT,
            dataset_kind TEXT,
            data_trust TEXT,
            imported_rows INTEGER
        )
        """
    )
    con.execute(
        """
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY,
            as_of_utc TEXT,
            quote_date_et TEXT,
            quote_minute_et INTEGER,
            snapshot_kind TEXT,
            underlying TEXT,
            contract_symbol TEXT,
            expiry TEXT,
            option_type TEXT,
            strike REAL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER
        )
        """
    )
    con.execute("INSERT INTO import_batches (id, source_label, dataset_kind, data_trust, imported_rows) VALUES (1, 'fixture', 'intraday_csv', 'trusted', 0)")
    con.commit()
    con.close()


def _insert_day(
    path: Path,
    quote_date: str,
    *,
    underlying_price: float | None = None,
    iv: float | None = None,
    volume: int | None = None,
    open_interest: int | None = None,
) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol,
            expiry, option_type, strike, bid, ask, last, iv, underlying_price, volume, open_interest, source_batch_id
        ) VALUES (?, ?, 600, 'intraday', 'SPY', 'SPYFIXTURE', ?, 'call', 100, 1, 1.1, NULL, ?, ?, ?, ?, 1)
        """,
        (f"{quote_date}T14:00:00Z", quote_date, (date.fromisoformat(quote_date) + timedelta(days=14)).isoformat(), iv, underlying_price, volume, open_interest),
    )
    con.commit()
    con.close()


class ExistingInputSurfaceAtlasTests(unittest.TestCase):
    def _report(self, tmp: Path, db: Path, **kwargs: object) -> dict:
        return atlas.build_report(
            db_path=db,
            data_root=tmp,
            start_date=str(kwargs.pop("start_date", "2026-02-01")),
            end_date=str(kwargs.pop("end_date", "2026-05-31")),
            latest_four_months=tuple(kwargs.pop("latest_four_months", ("2026-02", "2026-03", "2026-04", "2026-05"))),
            generated_at_utc="2026-06-23T00:00:00Z",
            control_artifacts=_control_files(tmp),
            **kwargs,
        )

    def test_read_only_db_open_is_enforced(self) -> None:
        with WorkspaceTempDir(prefix="existing-input-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            report = self._report(tmp, db)

        self.assertTrue(report["read_only_db_open"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["broker_order_allowed"])

    def test_unknown_or_missing_known_at_fails_closed(self) -> None:
        self.assertFalse(atlas._known_at_safe({"value": 1}))
        self.assertFalse(atlas._known_at_safe({"known_at_utc": "not-a-date"}))
        self.assertFalse(
            atlas._known_at_safe(
                {
                    "known_at_utc": "2026-02-02T15:00:00Z",
                    "candidate_entry_timestamp_utc": "2026-02-02T14:59:00Z",
                }
            )
        )

    def test_docs_only_evidence_and_proxy_mislabeling_cannot_pass(self) -> None:
        row = {
            "surface_id": "docs",
            "input_family": "direct_vix_or_volatility_regime",
            "source_type": "docs_only",
            "required_fields_present": True,
            "known_at_safe": True,
            "leakage_reject_count": 0,
            "protected_holdout_overlap_rows": 0,
            "train_months_covered": 20,
            "latest_four_months_covered": 4,
            "date_coverage_pct": 100.0,
            "latest_four_date_coverage_pct": 100.0,
            "approval_required": False,
            "remaining_blockers": [],
        }
        self.assertFalse(atlas._candidate_ready(row))
        row["source_type"] = "derived_point_in_time_proxy"
        self.assertFalse(atlas._candidate_ready(row))

    def test_forward_append_surfaces_are_approval_required(self) -> None:
        with WorkspaceTempDir(prefix="existing-input-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            report = self._report(tmp, db)

        forward = [row for row in report["source_surface_candidates"] if row["input_family"] == "fresh_forward_collection_readiness"][0]
        self.assertTrue(forward["approval_required"])
        self.assertFalse(forward["ready_for_branch_selection"])
        self.assertIn("forward_cohort_append_forbidden_in_this_slice", forward["remaining_blockers"])

    def test_ready_vix_bucket_clears_stale_missing_vix_blockers_without_becoming_next_branch(self) -> None:
        with WorkspaceTempDir(prefix="existing-input-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            controls = _control_files(tmp)
            bucket_rows = []
            day = date(2024, 6, 1)
            end = date(2026, 5, 31)
            while day <= end:
                if day.weekday() < 5:
                    bucket_rows.append(
                        {
                            "bucket_date_et": day.isoformat(),
                            "known_at_utc": f"{day.isoformat()}T00:00:00Z",
                            "point_in_time_valid": True,
                        }
                    )
                day += timedelta(days=1)
            _write_json(
                controls["vix_bucket"],
                {
                    "status": "point_in_time_vix_bucket_ready",
                    "blockers": [],
                    "covered_date_count": len(bucket_rows),
                    "requested_date_count": len(bucket_rows),
                    "coverage_pct": 100.0,
                    "bucket_rows": bucket_rows,
                },
            )

            report = atlas.build_report(
                db_path=db,
                data_root=tmp,
                start_date="2024-06-01",
                end_date="2026-05-31",
                latest_four_months=("2026-02", "2026-03", "2026-04", "2026-05"),
                generated_at_utc="2026-06-23T00:00:00Z",
                control_artifacts=controls,
            )

        vix = [row for row in report["source_surface_candidates"] if row["surface_id"] == "point_in_time_vix_bucket_artifact"][0]
        self.assertTrue(vix["required_fields_present"])
        self.assertTrue(vix["known_at_safe"])
        self.assertEqual(vix["remaining_blockers"], [])
        self.assertEqual(vix["latest_four_months_covered"], 4)
        self.assertEqual(vix["date_coverage_pct"], 100.0)
        self.assertFalse(vix["ready_for_branch_selection"])

    def test_coverage_train_latest_and_leakage_gates_block(self) -> None:
        row = {
            "surface_id": "almost",
            "input_family": "trend_or_regime",
            "source_type": "direct_market_source",
            "required_fields_present": True,
            "known_at_safe": True,
            "leakage_reject_count": 1,
            "protected_holdout_overlap_rows": 0,
            "train_months_covered": 19,
            "latest_four_months_covered": 3,
            "date_coverage_pct": 89.9,
            "latest_four_date_coverage_pct": 89.9,
            "approval_required": False,
            "remaining_blockers": [],
        }
        blockers = atlas._row_blockers(row)
        self.assertFalse(atlas._candidate_ready(row))
        self.assertIn("leakage_rejects_present", blockers)
        self.assertIn("train_months_below_20", blockers)
        self.assertIn("latest_four_months_below_4", blockers)
        self.assertIn("date_coverage_below_90", blockers)

    def test_clean_synthetic_existing_source_fixture_can_emit_ready_without_trading_state(self) -> None:
        with WorkspaceTempDir(prefix="existing-input-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            report = self._report(
                tmp,
                db,
                start_date="2024-06-01",
                end_date="2026-05-31",
                synthetic_candidate_rows=[
                    {
                        "surface_id": "fixture_trend_regime_source",
                        "input_family": "trend_or_regime",
                        "source_type": "direct_market_source",
                        "source_path": "fixture://trend-regime",
                        "train_months_covered": 20,
                        "latest_four_months_covered": 4,
                        "date_coverage_pct": 100.0,
                        "latest_four_date_coverage_pct": 100.0,
                        "clears_blockers": ["missing_point_in_time_trend_or_regime_inputs"],
                    }
                ],
            )

        self.assertEqual(report["status"], "existing_input_surface_ready_for_branch_selection")
        self.assertIsNotNone(report["next_research_branch"])
        self.assertFalse(report["p_l_replay_performed"])
        self.assertFalse(report["live_validation_enabled"])

    def test_write_outputs_creates_expected_artifacts(self) -> None:
        with WorkspaceTempDir(prefix="existing-input-atlas") as tmp_dir:
            tmp = Path(tmp_dir)
            db = tmp / "quotes.db"
            _create_db(db)
            _insert_day(db, "2026-02-03", underlying_price=100.0, iv=0.2, volume=10, open_interest=100)
            report = self._report(tmp, db)
            out = tmp / "out"
            doc = tmp / "doc.md"
            atlas.write_outputs(report, output_dir=out, docs_report=doc)
            self.assertTrue((out / "latest.json").exists())
            self.assertTrue((out / "latest.md").exists())
            self.assertTrue((out / "source_surface_candidates.jsonl").exists())
            self.assertTrue(doc.exists())


if __name__ == "__main__":
    unittest.main()
