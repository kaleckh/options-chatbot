from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import research_regular_options_gate_variant_replay as gate_replay  # noqa: E402
from scripts import run_fresh_window_2018_2021_quote_imports as import_driver  # noqa: E402
from scripts import run_fresh_window_pipeline_e2e as pipeline  # noqa: E402


TEST_PASS = (
    {
        "label": "entry_1010",
        "start_time": "10:10:00",
        "end_time": "10:10:00",
        "min_dte": 5,
        "max_dte": 35,
    },
)


def _csv_path(db_path: Path) -> Path:
    return db_path.parent / "staged.csv"


def _test_file_hash(db_path: Path) -> str:
    return import_driver._file_hash(_csv_path(db_path))


def _create_test_store(db_path: Path) -> None:
    _csv_path(db_path).write_text(
        "as_of_utc,underlying,contract_symbol,expiry,option_type,strike,bid,ask\n"
        "2021-12-30T15:10:00Z,SPY,SPY220121C00470000,2022-01-21,call,470,1.0,1.1\n"
        "2021-12-30T15:10:00Z,SPY,SPY220121P00470000,2022-01-21,put,470,1.0,1.1\n",
        encoding="utf8",
    )
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY,
                source_label TEXT NOT NULL,
                dataset_kind TEXT NOT NULL,
                data_trust TEXT NOT NULL,
                input_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                imported_at_utc TEXT NOT NULL,
                total_rows INTEGER NOT NULL,
                imported_rows INTEGER NOT NULL,
                duplicate_rows INTEGER NOT NULL,
                rejected_rows INTEGER NOT NULL,
                warnings_json TEXT NOT NULL
            );
            CREATE TABLE option_quote_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_utc TEXT NOT NULL,
                source_batch_id INTEGER NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                snapshot_kind TEXT NOT NULL,
                underlying TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike REAL NOT NULL,
                bid REAL,
                ask REAL,
                last REAL,
                iv REAL,
                underlying_price REAL,
                volume INTEGER,
                open_interest INTEGER,
                UNIQUE(as_of_utc, contract_symbol, snapshot_kind)
            );
            CREATE INDEX idx_option_quotes_underlying_date
                ON option_quote_snapshots (underlying, snapshot_kind, quote_date_et, option_type, quote_minute_et);
            CREATE INDEX idx_option_quotes_contract_date
                ON option_quote_snapshots (contract_symbol, snapshot_kind, quote_date_et, quote_minute_et DESC);
            CREATE INDEX idx_option_quotes_tuple_date
                ON option_quote_snapshots (underlying, snapshot_kind, expiry, option_type, strike, quote_date_et, quote_minute_et DESC);
            CREATE INDEX idx_option_quotes_snapshot_underlying
                ON option_quote_snapshots (snapshot_kind, underlying);
            CREATE INDEX idx_option_quotes_snapshot_asof
                ON option_quote_snapshots (snapshot_kind, as_of_utc);
            CREATE INDEX idx_option_quotes_snapshot_quote_date
                ON option_quote_snapshots (snapshot_kind, quote_date_et, underlying);
            CREATE INDEX idx_option_quotes_source_batch_snapshot_date
                ON option_quote_snapshots (source_batch_id, snapshot_kind, quote_date_et);
            CREATE INDEX idx_import_batches_source_trust_kind
                ON import_batches (source_label, data_trust, dataset_kind, id);
            """
        )
        connection.execute(
            """
            INSERT INTO import_batches (
                id, source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (1, ?, 'intraday_csv', 'trusted', ?, ?, '2026-07-09T00:00:00Z', 2, 2, 0, 0, '[]')
            """,
            (
                import_driver.SOURCE_LABEL,
                str(_csv_path(db_path).resolve()),
                _test_file_hash(db_path),
            ),
        )
        connection.commit()


def _build_test_plan(
    temp_dir: Path,
    db_path: Path,
    *,
    window_start: date = date(2021, 12, 30),
    window_end: date = date(2021, 12, 30),
    passes=TEST_PASS,
) -> dict:
    return import_driver._build_plan_from_spec(
        window_start=window_start,
        window_end=window_end,
        symbols=("SPY",),
        passes=passes,
        contract_path=import_driver.CONTRACT_PATH,
        db_path=db_path,
    )


def _insert_quotes(db_path: Path, rights: tuple[str, ...] = ("call", "put")) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executemany(
            """
            INSERT INTO option_quote_snapshots (
                as_of_utc, source_batch_id, quote_date_et, quote_minute_et, underlying,
                contract_symbol, option_type, strike, bid, ask, expiry, snapshot_kind
            ) VALUES ('2021-12-30T15:10:00Z', 1, '2021-12-30', 610, 'SPY', ?, ?, 470, 1.0, 1.1, '2022-01-21', 'intraday')
            """,
            [
                (f"SPY220121{'C' if right == 'call' else 'P'}00470000", right)
                for right in rights
            ],
        )
        connection.commit()


def _insert_extra_trusted_quote(db_path: Path, *, quote_minute_et: int) -> None:
    timestamp = (
        "2021-12-30T15:10:00Z" if quote_minute_et == 610 else "2021-12-30T15:11:00Z"
    )
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            INSERT INTO import_batches (
                id, source_label, dataset_kind, data_trust, input_path, file_hash,
                imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
            ) VALUES (2, ?, 'intraday_csv', 'trusted', ?, ?, '2026-07-09T00:01:00Z', 1, 1, 0, 0, '[]')
            """,
            (
                import_driver.SOURCE_LABEL,
                str((db_path.parent / "extra.csv").resolve()),
                "e" * 64,
            ),
        )
        connection.execute(
            """
            INSERT INTO option_quote_snapshots (
                as_of_utc, source_batch_id, quote_date_et, quote_minute_et, underlying,
                contract_symbol, option_type, strike, bid, ask, expiry, snapshot_kind
            ) VALUES (?, 2, '2021-12-30', ?, 'SPY', 'SPY220121C00471000',
                      'call', 471, 0.8, 0.9, '2022-01-21', 'intraday')
            """,
            (timestamp, quote_minute_et),
        )
        connection.commit()


def _complete_child_payload(plan: dict, db_path: Path) -> dict:
    chunk = plan["chunks"][0]
    file_hash = _test_file_hash(db_path)
    csv_artifact = {
        "path": str(_csv_path(db_path).resolve()),
        "sha256": file_hash,
        "row_count": 2,
    }
    import_result = {
        "db_path": str(db_path.resolve()),
        "batch_id": 1,
        "source_label": import_driver.SOURCE_LABEL,
        "dataset_kind": "intraday_csv",
        "data_trust": "trusted",
        "input_path": str(_csv_path(db_path).resolve()),
        "file_hash": file_hash,
        "total_rows": 2,
        "imported_rows": 2,
        "duplicate_rows": 0,
        "rejected_rows": 0,
    }
    artifact_lineage = {
        "csv_path": csv_artifact["path"],
        "csv_sha256": file_hash,
        "csv_row_count": 2,
        "import_batch_id": 1,
        "import_file_hash": file_hash,
        "import_db_path": str(db_path.resolve()),
        "import_source_label": import_driver.SOURCE_LABEL,
        "import_data_trust": "trusted",
        "database_import_complete": True,
    }
    request_results = [
        {
            "request_id": f"{symbol}:{day}",
            "symbol": symbol,
            "date": day,
            "status": "request_complete",
            "provider_request_succeeded": True,
            "requested_right": chunk["right"],
            "min_dte": chunk["min_dte"],
            "max_dte": chunk["max_dte"],
            "start_time": chunk["start_time"],
            "end_time": chunk["end_time"],
            "provider_response_row_count": 2,
            "normalized_row_count": 2,
            "call_row_count": 1,
            "put_row_count": 1,
            "lineage_rejection_count": 0,
            "observed_min_dte": 22,
            "observed_max_dte": 22,
            "first_provider_timestamp_utc": "2021-12-30T15:10:00Z",
            "last_provider_timestamp_utc": "2021-12-30T15:10:00Z",
            "artifact_lineage": dict(artifact_lineage),
        }
        for day in chunk["market_dates"]
        for symbol in plan["symbols"]
    ]
    return {
        "status": "request_surface_complete",
        "expected_request_count": len(request_results),
        "successful_request_count": len(request_results),
        "failed_request_count": 0,
        "empty_request_count": 0,
        "request_surface_complete": True,
        "generated_rows": 2,
        "csv_path": csv_artifact["path"],
        "csv_artifact": csv_artifact,
        "import_result": import_result,
        "database_import_complete": True,
        "request_results": request_results,
        "chain_completeness": import_driver._unproved_chain_completeness(),
        "request_errors": [],
        "empty_requests": [],
    }


def _complete_child_result(
    command: list[str], plan: dict, db_path: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(_complete_child_payload(plan, db_path)),
        stderr="",
    )


def _complete_manifest(plan: dict, db_path: Path) -> dict:
    manifest = import_driver._new_manifest(plan)
    payload = _complete_child_payload(plan, db_path)
    child_result = import_driver._child_summary(payload)
    coverage = import_driver._coverage_for_chunk(
        db_path,
        plan["chunks"][0],
        tuple(plan["symbols"]),
        expected_database_identity=plan["database_identity"],
    )
    state = manifest["chunks"][plan["chunks"][0]["chunk_id"]]
    state.update(
        {
            "status": "complete_verified",
            "child_result": child_result,
            "last_coverage": coverage,
            "provider_request_lineage": {
                "status": "complete_verified",
                "request_results_sha256": import_driver._canonical_hash(
                    child_result["request_results"]
                ),
            },
        }
    )
    manifest["status"] = "complete_verified"
    manifest["completed_at_utc"] = "2026-07-09T00:00:00Z"
    manifest["downstream_corpus_binding"] = (
        import_driver.manifest_database_corpus_binding(
            manifest,
            plan,
            db_path=db_path,
        )
    )
    return manifest


def _satisfied_chain_manifest_stub() -> dict:
    digest = "a" * 64
    return {
        "spec_hash": "pipeline-spec",
        "chunks": {"chunk": {"chunk_spec_hash": "chunk-spec"}},
        "chain_completeness": {
            "standard_version": import_driver.CHAIN_COMPLETENESS_STANDARD_VERSION,
            "required_scope": import_driver.CHAIN_COMPLETENESS_SCOPE,
            "status": "satisfied",
            "standard_satisfied": True,
            "selection_or_evaluation_authorized": True,
            "proof_spec_hash": "pipeline-spec",
            "chunk_proofs": {
                "chunk": {
                    "chunk_spec_hash": "chunk-spec",
                    "provider_response_exhaustive": True,
                    "provider_contract_identity_set_sha256": digest,
                    "trusted_database_contract_identity_set_sha256": digest,
                    "provider_eligible_quote_row_set_sha256": digest,
                    "trusted_database_eligible_quote_row_set_sha256": digest,
                    "eligible_row_set_exact": True,
                }
            },
        },
    }


class FreshWindowImportRecoveryTests(unittest.TestCase):
    def test_production_plan_rejects_tampered_contract_semantics_not_just_missing_file(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            contract = json.loads(
                import_driver.CONTRACT_PATH.read_text(encoding="utf8")
            )
            contract["quote_import_plan"]["exit_minute"] = (
                "13:00:00 ET silently substituted"
            )
            tampered_path = temp_dir / "tampered-contract.json"
            tampered_path.write_text(json.dumps(contract), encoding="utf8")

            with (
                patch.object(import_driver, "CONTRACT_PATH", tampered_path),
                self.assertRaisesRegex(ValueError, "contract_.*mismatch"),
            ):
                import_driver.build_plan(db_path=db_path)

    def test_plan_and_chunk_hashes_are_recomputed_from_exact_bodies(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            manifest = import_driver._new_manifest(plan)
            tampered_plan = json.loads(json.dumps(plan))
            tampered_plan["chunks"][0]["min_dte"] = 6

            errors = import_driver.manifest_validation_errors(
                manifest, tampered_plan, require_complete=False
            )

            self.assertIn("recomputed_plan_spec_hash_mismatch", errors)
            self.assertIn(
                "recomputed_chunk_spec_hash_mismatch:entry_1010:2021-12", errors
            )
            self.assertIn("manifest_exact_plan_mismatch", errors)

    def test_database_identity_rejects_minimal_tables_before_importer_schema_mutation(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            db_path = Path(raw_temp_dir) / "minimal.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    "CREATE TABLE import_batches (id INTEGER PRIMARY KEY);"
                    "CREATE TABLE option_quote_snapshots (source_batch_id INTEGER);"
                )
            identity = import_driver._database_identity(db_path)

            self.assertEqual(identity["status"], "schema_incomplete")
            self.assertFalse(identity["required_columns_present"])
            self.assertFalse(identity["required_indexes_present"])
            self.assertFalse(identity["unique_snapshot_key_present"])

    def test_timeout_resumes_then_revalidates_database_before_skipping(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            manifest_path = temp_dir / "manifest.json"
            lock_path = temp_dir / "driver.lock"
            log_path = temp_dir / "driver.log"

            def disk_usage(_path):
                return SimpleNamespace(free=100 * 2**30)

            def timeout_runner(command, **_kwargs):
                raise subprocess.TimeoutExpired(command, timeout=1)

            first_exit = import_driver.run_imports(
                plan=plan,
                manifest_path=manifest_path,
                db_path=db_path,
                lock_path=lock_path,
                log_path=log_path,
                min_free_gb=1,
                child_timeout_seconds=1,
                runner=timeout_runner,
                disk_usage=disk_usage,
            )
            blocked_manifest = json.loads(manifest_path.read_text(encoding="utf8"))
            chunk_id = plan["chunks"][0]["chunk_id"]
            self.assertEqual(first_exit, 1)
            self.assertEqual(blocked_manifest["status"], "blocked_child_timeout")
            self.assertEqual(blocked_manifest["chunks"][chunk_id]["attempt_count"], 1)
            self.assertFalse(lock_path.exists())
            self.assertNotIn(
                "FRESH_WINDOW_IMPORTS_COMPLETE_VERIFIED",
                log_path.read_text(encoding="utf8"),
            )

            resume_calls: list[list[str]] = []

            def successful_runner(command, **_kwargs):
                resume_calls.append(command)
                self.assertIn("--require-complete", command)
                _insert_quotes(db_path)
                return _complete_child_result(command, plan, db_path)

            second_exit = import_driver.run_imports(
                plan=plan,
                manifest_path=manifest_path,
                db_path=db_path,
                lock_path=lock_path,
                log_path=log_path,
                min_free_gb=1,
                runner=successful_runner,
                disk_usage=disk_usage,
            )
            complete_manifest = json.loads(manifest_path.read_text(encoding="utf8"))
            self.assertEqual(second_exit, 0)
            self.assertEqual(len(resume_calls), 1)
            self.assertEqual(complete_manifest["status"], "complete_verified")
            self.assertEqual(complete_manifest["chunks"][chunk_id]["attempt_count"], 2)
            self.assertEqual(
                import_driver.manifest_validation_errors(
                    complete_manifest, plan, require_complete=True
                ),
                [],
            )
            self.assertEqual(
                import_driver.revalidate_complete_manifest_database(
                    complete_manifest, plan, db_path=db_path
                ),
                [],
            )

            third_exit = import_driver.run_imports(
                plan=plan,
                manifest_path=manifest_path,
                db_path=db_path,
                lock_path=lock_path,
                log_path=log_path,
                min_free_gb=1,
                runner=lambda *_args, **_kwargs: self.fail(
                    "verified coverage must skip the child"
                ),
                disk_usage=disk_usage,
            )
            self.assertEqual(third_exit, 0)

            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "DELETE FROM option_quote_snapshots WHERE option_type = 'put'"
                )
                connection.commit()

            repair_calls: list[list[str]] = []

            def repair_runner(command, **_kwargs):
                repair_calls.append(command)
                _insert_quotes(db_path, ("put",))
                return _complete_child_result(command, plan, db_path)

            fourth_exit = import_driver.run_imports(
                plan=plan,
                manifest_path=manifest_path,
                db_path=db_path,
                lock_path=lock_path,
                log_path=log_path,
                min_free_gb=1,
                runner=repair_runner,
                disk_usage=disk_usage,
            )
            repaired_manifest = json.loads(manifest_path.read_text(encoding="utf8"))
            self.assertEqual(fourth_exit, 0)
            self.assertEqual(len(repair_calls), 1)
            self.assertEqual(repaired_manifest["chunks"][chunk_id]["attempt_count"], 3)

    def test_provider_failure_cannot_emit_verified_completion(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            manifest_path = temp_dir / "manifest.json"
            log_path = temp_dir / "driver.log"

            def failed_runner(command, **_kwargs):
                payload = {
                    "status": "blocked_request_surface_incomplete",
                    "request_surface_complete": False,
                    "failed_request_count": 1,
                    "request_errors": [{"symbol": "SPY", "date": "2021-12-30"}],
                }
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=json.dumps(payload),
                    stderr="provider unavailable",
                )

            exit_code = import_driver.run_imports(
                plan=plan,
                manifest_path=manifest_path,
                db_path=db_path,
                lock_path=temp_dir / "driver.lock",
                log_path=log_path,
                min_free_gb=1,
                runner=failed_runner,
                disk_usage=lambda _path: SimpleNamespace(free=100 * 2**30),
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf8"))
            self.assertEqual(exit_code, 1)
            self.assertEqual(manifest["status"], "blocked_import_incomplete")
            self.assertNotIn(
                "FRESH_WINDOW_IMPORTS_COMPLETE_VERIFIED",
                log_path.read_text(encoding="utf8"),
            )

    def test_disk_reserve_checks_selected_database_volume_separately_from_csv_volume(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(temp_dir, db_path)

            probes = iter(
                [
                    (("test", "csv"), Path("csv-volume")),
                    (("test", "db"), Path("db-volume")),
                ]
            )

            def disk_usage(path):
                free = 5 * 2**30 if path == Path("db-volume") else 100 * 2**30
                return SimpleNamespace(free=free)

            with patch.object(
                import_driver,
                "_storage_volume_probe",
                side_effect=lambda _path: next(probes),
            ):
                exit_code = import_driver.run_imports(
                    plan=plan,
                    manifest_path=temp_dir / "manifest.json",
                    db_path=db_path,
                    lock_path=temp_dir / "driver.lock",
                    log_path=temp_dir / "driver.log",
                    min_free_gb=20,
                    disk_usage=disk_usage,
                    runner=lambda *_args, **_kwargs: self.fail(
                        "low DB volume must block provider child"
                    ),
                )

            manifest = json.loads(
                (temp_dir / "manifest.json").read_text(encoding="utf8")
            )
            self.assertEqual(exit_code, 1)
            self.assertEqual(manifest["status"], "blocked_low_disk")
            self.assertIn("db-volume", manifest["last_error"])

    def test_full_plan_preflight_names_all_nine_early_closes_and_never_touches_provider_or_db_coverage(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(
                temp_dir,
                db_path,
                window_start=date(2018, 1, 1),
                window_end=date(2021, 12, 31),
                passes=import_driver.PASSES,
            )
            unsupported_dates = {
                item["date"]
                for item in plan["preflight"]["unsupported_market_sessions"]
            }
            self.assertEqual(
                unsupported_dates,
                {
                    "2018-07-03",
                    "2018-11-23",
                    "2018-12-24",
                    "2019-07-03",
                    "2019-11-29",
                    "2019-12-24",
                    "2020-11-27",
                    "2020-12-24",
                    "2021-11-26",
                },
            )
            self.assertFalse(plan["preflight"]["contract_time_reinterpreted"])

            with patch.object(
                import_driver,
                "_coverage_for_chunk",
                side_effect=AssertionError("preflight must precede DB coverage"),
            ):
                exit_code = import_driver.run_imports(
                    plan=plan,
                    manifest_path=temp_dir / "manifest.json",
                    db_path=db_path,
                    lock_path=temp_dir / "driver.lock",
                    log_path=temp_dir / "driver.log",
                    runner=lambda *_args, **_kwargs: self.fail(
                        "preflight must precede provider child"
                    ),
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse((temp_dir / "manifest.json").exists())
            self.assertFalse((temp_dir / "driver.lock").exists())
            with closing(sqlite3.connect(db_path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM option_quote_snapshots"
                    ).fetchone()[0],
                    0,
                )

            stdout = io.StringIO()
            cli_manifest = temp_dir / "cli-manifest.json"
            stale_manifest_bytes = (
                b'{"status":"complete_verified","spec_hash":"stale"}\n'
            )
            cli_manifest.write_bytes(stale_manifest_bytes)
            with (
                patch.object(import_driver, "build_plan", return_value=plan),
                redirect_stdout(stdout),
            ):
                cli_exit = import_driver.main(
                    [
                        "--resume",
                        "--manifest",
                        str(cli_manifest),
                        "--db-path",
                        str(db_path),
                        "--lock-path",
                        str(temp_dir / "cli.lock"),
                        "--log-path",
                        str(temp_dir / "cli.log"),
                        "--json",
                    ]
                )
            emitted = json.loads(stdout.getvalue())
            self.assertEqual(cli_exit, 1)
            self.assertEqual(emitted["status"], "blocked_preflight")
            self.assertEqual(cli_manifest.read_bytes(), stale_manifest_bytes)

    def test_missing_close_metadata_blocks_before_lock_manifest_provider_or_database_coverage(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            with (
                patch.object(
                    import_driver, "us_equity_market_close_time_et", return_value=None
                ),
                patch.object(
                    import_driver,
                    "_database_identity",
                    side_effect=AssertionError(
                        "unknown close metadata must block before database identity"
                    ),
                ) as database_identity,
            ):
                plan = _build_test_plan(temp_dir, db_path)

            database_identity.assert_not_called()
            self.assertEqual(plan["preflight"]["status"], "blocked")
            self.assertIn(
                "market_close_time_metadata_missing_for_planned_session",
                plan["preflight"]["blockers"],
            )
            self.assertEqual(
                plan["database_identity"]["status"],
                "not_checked_preflight_blocked",
            )
            self.assertEqual(
                plan["preflight"]["unsupported_market_sessions"][0]["reason"],
                "market_close_time_metadata_missing",
            )
            with patch.object(import_driver, "_coverage_for_chunk") as coverage:
                exit_code = import_driver.run_imports(
                    plan=plan,
                    manifest_path=temp_dir / "manifest.json",
                    db_path=db_path,
                    lock_path=temp_dir / "driver.lock",
                    log_path=temp_dir / "driver.log",
                    runner=lambda *_args, **_kwargs: self.fail(
                        "unknown close metadata must block provider child"
                    ),
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse((temp_dir / "manifest.json").exists())
            self.assertFalse((temp_dir / "driver.lock").exists())
            coverage.assert_not_called()

    def test_stale_lock_recovery_requires_explicit_same_spec_and_dead_pid(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            lock_path = temp_dir / "driver.lock"
            spec_hash = "exact-plan"

            lock_path.write_text(
                json.dumps({"pid": 123, "spec_hash": spec_hash}), encoding="utf8"
            )
            with self.assertRaisesRegex(RuntimeError, "lock already exists"):
                with import_driver._exclusive_lock(
                    lock_path, spec_hash=spec_hash, pid_is_live=lambda _pid: False
                ):
                    self.fail("recovery was not explicit")
            self.assertTrue(lock_path.exists())

            with self.assertRaisesRegex(RuntimeError, "still live"):
                with import_driver._exclusive_lock(
                    lock_path,
                    spec_hash=spec_hash,
                    recover_stale=True,
                    pid_is_live=lambda _pid: True,
                ):
                    self.fail("live owner must not be recovered")

            lock_path.write_text(
                json.dumps({"pid": 123, "spec_hash": "other-plan"}), encoding="utf8"
            )
            with self.assertRaisesRegex(RuntimeError, "spec does not match"):
                with import_driver._exclusive_lock(
                    lock_path,
                    spec_hash=spec_hash,
                    recover_stale=True,
                    pid_is_live=lambda _pid: False,
                ):
                    self.fail("wrong-spec lock must not be recovered")

            lock_path.write_text("legacy pid=123\n", encoding="utf8")
            with self.assertRaisesRegex(RuntimeError, "unreadable lock"):
                with import_driver._exclusive_lock(
                    lock_path,
                    spec_hash=spec_hash,
                    recover_stale=True,
                    pid_is_live=lambda _pid: False,
                ):
                    self.fail("malformed lock must not be recovered")

            lock_path.write_text(
                json.dumps({"pid": 123, "spec_hash": spec_hash}), encoding="utf8"
            )
            with import_driver._exclusive_lock(
                lock_path,
                spec_hash=spec_hash,
                recover_stale=True,
                pid_is_live=lambda _pid: False,
            ):
                active = json.loads(lock_path.read_text(encoding="utf8"))
                self.assertEqual(active["spec_hash"], spec_hash)
                self.assertTrue(active["owner_token"])
            self.assertFalse(lock_path.exists())

            with import_driver._exclusive_lock(lock_path, spec_hash=spec_hash):
                lock_path.write_text(
                    json.dumps(
                        {
                            "pid": 999,
                            "spec_hash": spec_hash,
                            "owner_token": "foreign-in-place-replacement",
                        }
                    ),
                    encoding="utf8",
                )
            self.assertTrue(lock_path.exists())
            self.assertEqual(
                json.loads(lock_path.read_text(encoding="utf8"))["owner_token"],
                "foreign-in-place-replacement",
            )
            lock_path.unlink()

    def test_unexpected_main_exception_persists_one_parseable_crash_manifest(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            manifest_path = temp_dir / "manifest.json"
            stdout = io.StringIO()
            real_run_imports = import_driver.run_imports

            def crashing_run_imports(**kwargs):
                def crashing_runner(_command, **_runner_kwargs):
                    raise RuntimeError("simulated crash")

                return real_run_imports(
                    **kwargs,
                    runner=crashing_runner,
                    disk_usage=lambda _path: SimpleNamespace(free=100 * 2**30),
                )

            with (
                patch.object(import_driver, "build_plan", return_value=plan),
                patch.object(
                    import_driver, "run_imports", side_effect=crashing_run_imports
                ),
                redirect_stdout(stdout),
            ):
                exit_code = import_driver.main(
                    [
                        "--resume",
                        "--manifest",
                        str(manifest_path),
                        "--db-path",
                        str(db_path),
                        "--lock-path",
                        str(temp_dir / "driver.lock"),
                        "--log-path",
                        str(temp_dir / "driver.log"),
                        "--json",
                    ]
                )

            emitted = json.loads(stdout.getvalue())
            persisted = json.loads(manifest_path.read_text(encoding="utf8"))
            self.assertEqual(exit_code, 1)
            self.assertEqual(emitted["status"], "crashed")
            self.assertEqual(persisted["status"], "crashed")
            self.assertIn("simulated crash", persisted["last_error"])
            chunk_state = persisted["chunks"][plan["chunks"][0]["chunk_id"]]
            self.assertEqual(chunk_state["status"], "crashed")


class FreshWindowPipelineHandoffTests(unittest.TestCase):
    def test_partial_retry_allows_csv_duplicates_backed_by_older_trusted_pair_coverage(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            _insert_quotes(db_path)
            retry_csv = temp_dir / "retry.csv"
            retry_csv.write_text(
                "as_of_utc,underlying,contract_symbol,expiry,option_type,strike,bid,ask\n"
                "2021-12-30T15:10:00Z,SPY,SPY220121C00470000,2022-01-21,call,470,1.0,1.1\n"
                "2021-12-30T15:10:00Z,SPY,SPY220121P00470000,2022-01-21,put,470,1.0,1.1\n"
                "2021-12-30T15:10:00Z,QQQ,QQQ220121C00390000,2022-01-21,call,390,1.0,1.1\n"
                "2021-12-30T15:10:00Z,QQQ,QQQ220121P00390000,2022-01-21,put,390,1.0,1.1\n",
                encoding="utf8",
            )
            retry_hash = import_driver._file_hash(retry_csv)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO import_batches (
                        id, source_label, dataset_kind, data_trust, input_path, file_hash,
                        imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
                    ) VALUES (2, ?, 'intraday_csv', 'trusted', ?, ?, '2026-07-09T00:01:00Z', 4, 2, 2, 0, '[]')
                    """,
                    (import_driver.SOURCE_LABEL, str(retry_csv.resolve()), retry_hash),
                )
                connection.executemany(
                    """
                    INSERT INTO option_quote_snapshots (
                        as_of_utc, source_batch_id, quote_date_et, quote_minute_et, underlying,
                        contract_symbol, option_type, strike, bid, ask, expiry, snapshot_kind
                    ) VALUES ('2021-12-30T15:10:00Z', 2, '2021-12-30', 610, 'QQQ', ?, ?, 390, 1.0, 1.1, '2022-01-21', 'intraday')
                    """,
                    [
                        ("QQQ220121C00390000", "call"),
                        ("QQQ220121P00390000", "put"),
                    ],
                )
                connection.commit()
            plan = import_driver._build_plan_from_spec(
                window_start=date(2021, 12, 30),
                window_end=date(2021, 12, 30),
                symbols=("SPY", "QQQ"),
                passes=TEST_PASS,
                contract_path=import_driver.CONTRACT_PATH,
                db_path=db_path,
            )
            chunk = plan["chunks"][0]
            artifact_lineage = {
                "csv_path": str(retry_csv.resolve()),
                "csv_sha256": retry_hash,
                "csv_row_count": 4,
                "import_batch_id": 2,
                "import_file_hash": retry_hash,
                "import_db_path": str(db_path.resolve()),
                "import_source_label": import_driver.SOURCE_LABEL,
                "import_data_trust": "trusted",
                "database_import_complete": True,
            }
            requests = [
                {
                    "request_id": f"{symbol}:2021-12-30",
                    "symbol": symbol,
                    "date": "2021-12-30",
                    "status": "request_complete",
                    "provider_request_succeeded": True,
                    "requested_right": "both",
                    "min_dte": 5,
                    "max_dte": 35,
                    "start_time": "10:10:00",
                    "end_time": "10:10:00",
                    "provider_response_row_count": 2,
                    "normalized_row_count": 2,
                    "call_row_count": 1,
                    "put_row_count": 1,
                    "lineage_rejection_count": 0,
                    "observed_min_dte": 22,
                    "observed_max_dte": 22,
                    "first_provider_timestamp_utc": "2021-12-30T15:10:00Z",
                    "last_provider_timestamp_utc": "2021-12-30T15:10:00Z",
                    "artifact_lineage": dict(artifact_lineage),
                }
                for symbol in ("SPY", "QQQ")
            ]
            payload = {
                "request_surface_complete": True,
                "expected_request_count": 2,
                "successful_request_count": 2,
                "failed_request_count": 0,
                "empty_request_count": 0,
                "generated_rows": 4,
                "database_import_complete": True,
                "csv_artifact": {
                    "path": str(retry_csv.resolve()),
                    "sha256": retry_hash,
                    "row_count": 4,
                },
                "import_result": {
                    "db_path": str(db_path.resolve()),
                    "batch_id": 2,
                    "source_label": import_driver.SOURCE_LABEL,
                    "dataset_kind": "intraday_csv",
                    "data_trust": "trusted",
                    "input_path": str(retry_csv.resolve()),
                    "file_hash": retry_hash,
                    "total_rows": 4,
                    "imported_rows": 2,
                    "duplicate_rows": 2,
                    "rejected_rows": 0,
                },
                "request_results": requests,
                "chain_completeness": import_driver._unproved_chain_completeness(),
            }
            coverage = import_driver._coverage_for_chunk(
                db_path,
                chunk,
                tuple(plan["symbols"]),
                expected_database_identity=plan["database_identity"],
            )

            errors = import_driver._provider_lineage_errors(
                payload,
                chunk=chunk,
                symbols=tuple(plan["symbols"]),
                expected_database_identity=plan["database_identity"],
                database_coverage=coverage,
            )

            self.assertEqual(errors, [])
            pair_batches = {
                item["symbol"]: item["import_batch_ids"]
                for item in coverage["pair_coverage"]
            }
            self.assertEqual(pair_batches, {"QQQ": [2], "SPY": [1]})

            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO import_batches (
                        id, source_label, dataset_kind, data_trust, input_path, file_hash,
                        imported_at_utc, total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
                    ) VALUES (3, ?, 'intraday_csv', 'trusted', ?, ?, '2026-07-09T00:02:00Z', 4, 0, 4, 0, '[]')
                    """,
                    (import_driver.SOURCE_LABEL, str(retry_csv.resolve()), retry_hash),
                )
                connection.commit()
            duplicate_payload = json.loads(json.dumps(payload))
            duplicate_payload["import_result"].update(
                {"batch_id": 3, "imported_rows": 0, "duplicate_rows": 4}
            )
            for request in duplicate_payload["request_results"]:
                request["artifact_lineage"]["import_batch_id"] = 3
            duplicate_errors = import_driver._provider_lineage_errors(
                duplicate_payload,
                chunk=chunk,
                symbols=tuple(plan["symbols"]),
                expected_database_identity=plan["database_identity"],
                database_coverage=coverage,
            )
            self.assertEqual(duplicate_errors, [])

    def test_extra_trusted_rows_outside_manifest_corpus_are_rejected_at_exact_and_adjacent_minutes(
        self,
    ):
        for quote_minute_et in (610, 611):
            with (
                self.subTest(quote_minute_et=quote_minute_et),
                tempfile.TemporaryDirectory() as raw_temp_dir,
            ):
                temp_dir = Path(raw_temp_dir)
                db_path = temp_dir / "quotes.sqlite3"
                _create_test_store(db_path)
                _insert_quotes(db_path)
                plan = _build_test_plan(temp_dir, db_path)
                manifest = _complete_manifest(plan, db_path)
                self.assertEqual(
                    import_driver.revalidate_complete_manifest_database(
                        manifest, plan, db_path=db_path
                    ),
                    [],
                )

                _insert_extra_trusted_quote(db_path, quote_minute_et=quote_minute_et)
                errors = import_driver.revalidate_complete_manifest_database(
                    manifest, plan, db_path=db_path
                )

                self.assertTrue(
                    any(
                        "trusted_database_rows_outside_manifest_corpus:1" in item
                        for item in errors
                    ),
                    errors,
                )
                self.assertIn("persisted_downstream_corpus_binding_mismatch", errors)
                if quote_minute_et == 610:
                    self.assertTrue(
                        any(
                            "trusted_database_rows_absent_from_csv_exact_set:1" in item
                            for item in errors
                        ),
                        errors,
                    )

    def test_each_request_pair_must_be_present_in_hashed_csv_artifact(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            _insert_quotes(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            chunk = plan["chunks"][0]
            _csv_path(db_path).write_text(
                "as_of_utc,underlying,contract_symbol,expiry,option_type,strike,bid,ask\n"
                "2021-12-30T15:10:00Z,QQQ,QQQ220121C00390000,2022-01-21,call,390,1.0,1.1\n"
                "2021-12-30T15:10:00Z,QQQ,QQQ220121P00390000,2022-01-21,put,390,1.0,1.1\n",
                encoding="utf8",
            )
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "UPDATE import_batches SET file_hash = ? WHERE id = 1",
                    (_test_file_hash(db_path),),
                )
                connection.commit()
            payload = import_driver._child_summary(
                _complete_child_payload(plan, db_path)
            )
            coverage = import_driver._coverage_for_chunk(
                db_path,
                chunk,
                tuple(plan["symbols"]),
                expected_database_identity=plan["database_identity"],
            )
            errors = import_driver._provider_lineage_errors(
                payload,
                chunk=chunk,
                symbols=tuple(plan["symbols"]),
                expected_database_identity=plan["database_identity"],
                database_coverage=coverage,
            )

            self.assertTrue(
                any(item.startswith("csv_unexpected_request_pair") for item in errors)
            )
            self.assertIn("csv_call_count_mismatch:2021-12-30:SPY", errors)
            self.assertIn("csv_put_count_mismatch:2021-12-30:SPY", errors)

    def test_forged_complete_manifest_and_db_coverage_deletion_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_path = temp_dir / "quotes.sqlite3"
            _create_test_store(db_path)
            _insert_quotes(db_path)
            plan = _build_test_plan(temp_dir, db_path)
            manifest = _complete_manifest(plan, db_path)
            state = manifest["chunks"][plan["chunks"][0]["chunk_id"]]
            state["child_result"]["import_result"]["batch_id"] = 999
            for request in state["child_result"]["request_results"]:
                request["artifact_lineage"]["import_batch_id"] = 999
            state["provider_request_lineage"]["request_results_sha256"] = (
                import_driver._canonical_hash(state["child_result"]["request_results"])
            )
            self.assertEqual(
                import_driver.manifest_validation_errors(
                    manifest, plan, require_complete=True
                ),
                [],
            )
            errors = import_driver.revalidate_complete_manifest_database(
                manifest, plan, db_path=db_path
            )
            self.assertIn("entry_1010:2021-12:persisted_import_batch_missing", errors)

            valid_manifest = _complete_manifest(plan, db_path)
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(json.dumps(valid_manifest), encoding="utf8")
            before_stat = db_path.stat()
            result = pipeline.wait_for_imports(
                manifest_path=manifest_path,
                max_hours=0,
                poll_seconds=0,
                expected_plan=plan,
                db_path=db_path,
                log_path=temp_dir / "pipeline.log",
            )
            after_stat = db_path.stat()
            self.assertEqual(result["spec_hash"], plan["spec_hash"])
            self.assertEqual(
                (after_stat.st_size, after_stat.st_mtime_ns),
                (before_stat.st_size, before_stat.st_mtime_ns),
            )

            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "DELETE FROM option_quote_snapshots WHERE option_type = 'put'"
                )
                connection.commit()
            with self.assertRaises(SystemExit):
                pipeline.wait_for_imports(
                    manifest_path=manifest_path,
                    max_hours=0,
                    poll_seconds=0,
                    expected_plan=plan,
                    db_path=db_path,
                    log_path=temp_dir / "pipeline.log",
                )

    def test_database_a_manifest_cannot_be_handed_off_against_database_b(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            db_a = temp_dir / "a.sqlite3"
            db_b = temp_dir / "b.sqlite3"
            _create_test_store(db_a)
            _create_test_store(db_b)
            _insert_quotes(db_a)
            plan_a = _build_test_plan(temp_dir, db_a)
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(_complete_manifest(plan_a, db_a)), encoding="utf8"
            )

            with self.assertRaises(SystemExit):
                pipeline.wait_for_imports(
                    manifest_path=manifest_path,
                    max_hours=0,
                    poll_seconds=0,
                    expected_plan=plan_a,
                    db_path=db_b,
                    log_path=temp_dir / "pipeline.log",
                )


class GateVariantReplayContractTests(unittest.TestCase):
    @staticmethod
    def _ready_member(**kwargs):
        member_id = f"{kwargs['family']['family_id']}[{kwargs['member_index']}]"
        return {
            "member_id": member_id,
            "family_id": kwargs["family"]["family_id"],
            "adapter_status": "blocked_historical_frozen_scanner_replay_adapter",
            "adapter_blockers": ["production_policy_parity_not_established"],
            "research_materializer_ready": True,
            "research_materializer_blockers": [],
            "production_proof_or_nomination_blockers": [
                "production_policy_parity_not_established"
            ],
            "production_parity_mismatches": [{"field": "candidate_admission"}],
            "scanner_parity": False,
            "production_scanner_replay": False,
            "diagnostic_selected_candidate_count": 1,
            "diagnostic_priced_candidate_count": 1,
            "diagnostic_metrics": {"exact_trade_count": 1},
            "analysis_class": "diagnostic_only",
            "member_score_valid_for_selection": False,
            "family_member_accepted": False,
        }

    def _base_args(self, temp_dir: Path, *, split: str = "family_train") -> list[str]:
        dummy = temp_dir / "unused.json"
        db_path = temp_dir / "gate-quotes.sqlite3"
        _create_test_store(db_path)
        _insert_quotes(db_path)
        plan = _build_test_plan(temp_dir, db_path)
        manifest_path = temp_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(_complete_manifest(plan, db_path)), encoding="utf8"
        )
        return [
            "--families",
            str(gate_replay.DEFAULT_FAMILIES),
            "--window-contract",
            str(gate_replay.DEFAULT_WINDOW_CONTRACT),
            "--split",
            split,
            "--import-manifest",
            str(manifest_path),
            "--feature-store",
            str(dummy),
            "--market-regime-inputs",
            str(dummy),
            "--vix-bucket",
            str(dummy),
            "--input-surface-tracker",
            str(dummy),
            "--earnings-calendar",
            str(dummy),
            "--options-db",
            str(db_path),
            "--output-dir",
            str(temp_dir / "output"),
        ]

    def test_family_train_uses_exact_bounds_and_research_readiness_while_retaining_production_blockers(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            calls: list[dict] = []

            def ready_member(**kwargs):
                calls.append(kwargs)
                return self._ready_member(**kwargs)

            stdout = io.StringIO()
            with (
                patch.object(gate_replay, "run_member", side_effect=ready_member),
                redirect_stdout(stdout),
            ):
                exit_code = gate_replay.main(self._base_args(temp_dir))

            report = json.loads(
                (temp_dir / "output" / "family_train_latest.json").read_text(
                    encoding="utf8"
                )
            )
            self.assertEqual(exit_code, 1)
            self.assertEqual(
                report["status"], "diagnostic_only_incomplete_quote_surface"
            )
            self.assertEqual(report["analysis_class"], "diagnostic_only")
            self.assertEqual(
                report["split_window"],
                {"start": "2018-01-01", "end": "2020-06-30", "as_of": "2020-06-30"},
            )
            self.assertEqual(len(calls), 15)
            self.assertTrue(all(call["split_end"] == "2020-06-30" for call in calls))
            self.assertTrue(all(call["as_of_date"] == "2020-06-30" for call in calls))
            self.assertTrue(all(call["bootstrap_draws"] == 10000 for call in calls))
            self.assertTrue(report["research_materializer_ready"])
            self.assertIn(
                "provider_chain_completeness_not_established", report["blockers"]
            )
            self.assertFalse(
                report["chain_completeness_standard"][
                    "chain_completeness_standard_satisfied"
                ]
            )
            self.assertFalse(report["selection_eligible"])
            self.assertFalse(report["evaluation_ready"])
            self.assertFalse(report["member_scores_valid_for_selection"])
            self.assertNotIn("gate_variant_member_scored", stdout.getvalue())
            self.assertIn(
                "gate_variant_member_diagnostic_materialized", stdout.getvalue()
            )
            self.assertIn(
                "production_policy_parity_not_established",
                report["production_proof_or_nomination_blockers"],
            )
            self.assertFalse(report["contract_complete"])
            self.assertFalse(report["top3_selected"])
            self.assertFalse(report["family_validation_scored"])
            self.assertFalse(report["backup_retirement_authorized"])
            self.assertFalse(report["seal_retirement_authorized"])
            self.assertEqual(
                report["unscored_families"][0]["family_id"], "F2_session_time_alignment"
            )
            self.assertIn(
                "missing_f2_session_time_alignment_scoring_path",
                report["validation_pending_blockers"],
            )

    def test_materializer_blockers_fail_research_even_when_production_blockers_are_separate(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            blocked = self._ready_member(
                family={"family_id": "F1a_ret20_threshold"},
                member_index=0,
            )
            blocked["research_materializer_ready"] = False
            blocked["research_materializer_blockers"] = ["missing_exact_quote_pair"]
            with patch.object(gate_replay, "run_member", return_value=blocked):
                exit_code = gate_replay.main(self._base_args(temp_dir))

            report = json.loads(
                (temp_dir / "output" / "family_train_latest.json").read_text(
                    encoding="utf8"
                )
            )
            self.assertEqual(exit_code, 1)
            self.assertEqual(report["status"], "blocked_gate_variant_replay")
            self.assertIn(
                "missing_exact_quote_pair", report["research_materializer_blockers"]
            )
            self.assertIn(
                "production_policy_parity_not_established",
                report["production_proof_or_nomination_blockers"],
            )

    def test_run_member_does_not_compute_metrics_from_stale_rows_when_materializer_is_blocked(
        self,
    ):
        family = {
            "family_id": "F1a_ret20_threshold",
            "grid": [0.0],
        }
        adapter_report = {
            "status": "blocked_historical_frozen_scanner_replay_adapter",
            "research_materializer_ready": False,
            "research_materializer_blockers": ["missing_exact_quote_pair"],
            "proof_or_nomination_blockers": [
                "production_policy_parity_not_established"
            ],
            "production_parity_mismatches": [],
            "selected_candidates": [{"net_pnl_usd": 100.0}],
            "daily_candidate_decision_row_count": 1,
            "scanner_parity": False,
            "production_scanner_replay": False,
        }
        dummy_paths = {
            key: Path("unused")
            for key in (
                "forward_cohort",
                "feature_store",
                "market_regime_inputs",
                "vix_bucket",
                "input_surface_tracker",
                "earnings_calendar",
                "options_db",
            )
        }

        with (
            patch.object(
                gate_replay.adapter, "build_report", return_value=adapter_report
            ),
            patch.object(gate_replay, "_metrics") as metrics,
        ):
            result = gate_replay.run_member(
                family=family,
                member=0.0,
                member_index=0,
                split_start="2018-01-01",
                split_end="2020-06-30",
                as_of_date="2020-06-30",
                adapter_paths=dummy_paths,
                bootstrap_draws=10000,
            )

        self.assertFalse(result["research_materializer_ready"])
        self.assertEqual(result["diagnostic_metrics"], {})
        metrics.assert_not_called()

    def test_same_size_grid_tampering_blocks_before_scoring(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            families = json.loads(
                gate_replay.DEFAULT_FAMILIES.read_text(encoding="utf8")
            )
            families["families"][0]["grid"][0] = 0.25
            tampered_path = temp_dir / "families.json"
            tampered_path.write_text(json.dumps(families), encoding="utf8")
            args = self._base_args(temp_dir)
            args[args.index("--families") + 1] = str(tampered_path)

            with patch.object(gate_replay, "run_member") as run_member:
                exit_code = gate_replay.main(args)

            report = json.loads(
                (temp_dir / "output" / "family_train_latest.json").read_text(
                    encoding="utf8"
                )
            )
            self.assertEqual(exit_code, 1)
            self.assertIn(
                "preregistered_family_grid_content_or_order_mismatch",
                report["blockers"],
            )
            run_member.assert_not_called()

    def test_validation_invocation_is_structured_nonzero_and_never_scores_or_appends_registry(
        self,
    ):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            with patch.object(gate_replay, "run_member") as run_member:
                exit_code = gate_replay.main(
                    self._base_args(temp_dir, split="family_validation")
                )

            report = json.loads(
                (temp_dir / "output" / "family_validation_latest.json").read_text(
                    encoding="utf8"
                )
            )
            self.assertEqual(exit_code, 1)
            self.assertEqual(report["status"], "blocked_formal_family_validation_path")
            self.assertEqual(
                report["split_window"],
                {"start": "2020-07-01", "end": "2021-12-31", "as_of": "2021-12-31"},
            )
            self.assertFalse(report["family_validation_scored"])
            self.assertFalse(report["consumption_registry_appended"])
            self.assertIn(
                "missing_formal_one_shot_family_validation_path", report["blockers"]
            )
            self.assertIn(
                "missing_consumption_registry_append_path", report["blockers"]
            )
            run_member.assert_not_called()

    def test_non_frozen_bootstrap_draw_count_blocks_before_scoring(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            with patch.object(gate_replay, "run_member") as run_member:
                exit_code = gate_replay.main(
                    [*self._base_args(temp_dir), "--bootstrap-draws", "9999"]
                )

            report = json.loads(
                (temp_dir / "output" / "family_train_latest.json").read_text(
                    encoding="utf8"
                )
            )
            self.assertEqual(exit_code, 1)
            self.assertTrue(
                any(
                    item.startswith("bootstrap_draws_not_frozen_10000")
                    for item in report["blockers"]
                )
            )
            run_member.assert_not_called()

    def test_pipeline_never_emits_completion_while_formal_paths_are_missing(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            log_messages: list[str] = []
            stage_calls: dict[str, list[str]] = {}

            def artifact(path, **_kwargs):
                if path.parent.name == "historical-scanner-input-surface-tracker":
                    return {
                        "surface_readiness": {
                            "entry_underlying_price_surface": {"available": True},
                            "option_chain_selection_surface": {"available": True},
                        }
                    }
                if path.name == "family_train_latest.json":
                    return {
                        "status": "diagnostic_only_incomplete_family_train",
                        "research_materializer_ready": True,
                        "diagnostic_materializer_ready": True,
                        "selection_eligible": False,
                        "evaluation_ready": False,
                        "validation_pending_blockers": [
                            "missing_formal_one_shot_family_validation_path"
                        ],
                    }
                return {"status": "ready", "blockers": []}

            with (
                patch.object(
                    pipeline,
                    "wait_for_imports",
                    return_value=_satisfied_chain_manifest_stub(),
                ),
                patch.object(
                    pipeline,
                    "run",
                    side_effect=lambda label, args: stage_calls.__setitem__(
                        label, list(args)
                    ),
                ),
                patch.object(pipeline, "artifact_status", side_effect=artifact),
                patch.object(
                    pipeline,
                    "log",
                    side_effect=lambda message, **_kwargs: log_messages.append(message),
                ),
            ):
                exit_code = pipeline.main(
                    [
                        "--import-manifest",
                        str(temp_dir / "manifest.json"),
                        "--db-path",
                        str(temp_dir / "quotes.sqlite3"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertTrue(
                any(
                    "PIPELINE_BLOCKED_INCOMPLETE_CONTRACT" in item
                    for item in log_messages
                )
            )
            self.assertTrue(
                all("PIPELINE_COMPLETE" not in item for item in log_messages)
            )
            self.assertTrue(
                any(
                    "backup_retirement_authorized=false" in item
                    for item in log_messages
                )
            )
            feature_args = stage_calls["feature-store"]
            gate_args = stage_calls["gate-variant-replay"]
            expected_db = str((temp_dir / "quotes.sqlite3").resolve())
            self.assertEqual(
                feature_args[feature_args.index("--db-path") + 1], expected_db
            )
            self.assertEqual(
                gate_args[gate_args.index("--options-db") + 1], expected_db
            )
            self.assertEqual(
                gate_args[gate_args.index("--import-manifest") + 1],
                str((temp_dir / "manifest.json").resolve()),
            )
            self.assertEqual(
                stage_calls["earnings-calendar"][
                    stage_calls["earnings-calendar"].index("--end-date") + 1
                ],
                "2020-06-30",
            )
            tracker_args = stage_calls["tracker"]
            self.assertEqual(
                tracker_args[tracker_args.index("--options-history-db") + 1],
                expected_db,
            )
            self.assertEqual(
                tracker_args[tracker_args.index("--end-date") + 1], "2020-06-30"
            )
            self.assertEqual(
                tracker_args[tracker_args.index("--as-of-date") + 1], "2020-06-30"
            )

    def test_pipeline_blocks_chain_unproved_manifest_before_any_downstream_reader(self):
        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            log_messages: list[str] = []
            with (
                patch.object(
                    pipeline,
                    "wait_for_imports",
                    return_value={
                        "chain_completeness": import_driver._unproved_chain_completeness()
                    },
                ),
                patch.object(pipeline, "run") as run_stage,
                patch.object(
                    pipeline,
                    "log",
                    side_effect=lambda message, **_kwargs: log_messages.append(message),
                ),
            ):
                exit_code = pipeline.main(
                    [
                        "--import-manifest",
                        str(temp_dir / "manifest.json"),
                        "--db-path",
                        str(temp_dir / "quotes.sqlite3"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            run_stage.assert_not_called()
            self.assertTrue(
                any(
                    "PIPELINE_BLOCKED_CHAIN_COMPLETENESS_STANDARD" in item
                    for item in log_messages
                )
            )


if __name__ == "__main__":
    unittest.main()
