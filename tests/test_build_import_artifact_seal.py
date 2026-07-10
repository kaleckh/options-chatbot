from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.build_import_artifact_seal import _batch_reconciliation, build_import_artifact_seal, verify_seal_manifest


def _make_db(path: Path, artifact: Path, *, imported: int = 2, rejected: int = 0) -> None:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
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
                id INTEGER PRIMARY KEY,
                source_batch_id INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO import_batches VALUES (1, 'fixture', 'intraday_csv', 'trusted', ?, ?, '2026-01-01T00:00:00Z', ?, ?, 0, ?, '[]')",
            (str(artifact.resolve()), digest, imported + rejected, imported, rejected),
        )
        conn.executemany(
            "INSERT INTO option_quote_snapshots (source_batch_id) VALUES (1)",
            [() for _ in range(imported)],
        )
        conn.commit()


class ImportArtifactSealTests(unittest.TestCase):
    def test_seals_exact_hash_path_and_database_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "imports"
            artifacts.mkdir()
            source = artifacts / "source.csv"
            source.write_text("header\na\nb\n", encoding="utf-8")
            db = root / "options.db"
            _make_db(db, source)

            seal = build_import_artifact_seal(
                db_path=db,
                artifact_roots=[artifacts],
                generated_at_utc="2026-01-01T00:00:00Z",
            )

            self.assertEqual(seal["status"], "sealed")
            self.assertEqual(seal["eligible_count"], 1)
            self.assertTrue(seal["artifacts"][0]["eligible_for_retirement_after_verified_replacement_backup"])
            self.assertTrue(verify_seal_manifest(seal))

    def test_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "imports"
            artifacts.mkdir()
            source = artifacts / "source.csv"
            source.write_text("original", encoding="utf-8")
            db = root / "options.db"
            _make_db(db, source)
            source.write_text("changed", encoding="utf-8")

            seal = build_import_artifact_seal(db_path=db, artifact_roots=[artifacts])

            self.assertEqual(seal["status"], "blocked")
            self.assertIn("sha256_not_found_in_import_batches", seal["artifacts"][0]["blockers"])

    def test_rejected_rows_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "imports"
            artifacts.mkdir()
            source = artifacts / "source.csv"
            source.write_text("source", encoding="utf-8")
            db = root / "options.db"
            _make_db(db, source, imported=1, rejected=1)

            seal = build_import_artifact_seal(db_path=db, artifact_roots=[artifacts])

            self.assertEqual(seal["status"], "blocked")
            self.assertIn("batch_has_rejected_rows", seal["artifacts"][0]["blockers"])

    def test_empty_artifact_root_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "imports"
            artifacts.mkdir()
            source = root / "source.csv"
            source.write_text("source", encoding="utf-8")
            db = root / "options.db"
            _make_db(db, source)

            seal = build_import_artifact_seal(db_path=db, artifact_roots=[artifacts])

            self.assertEqual(seal["status"], "blocked")
            self.assertIn("no_import_artifacts_found", seal["top_level_blockers"])

    def test_non_list_warnings_fail_closed(self) -> None:
        for raw in ("null", "{}"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                artifacts = root / "imports"
                artifacts.mkdir()
                source = artifacts / "source.csv"
                source.write_text("source", encoding="utf-8")
                db = root / "options.db"
                _make_db(db, source)
                with closing(sqlite3.connect(db)) as conn:
                    conn.execute("UPDATE import_batches SET warnings_json = ?", (raw,))
                    conn.commit()

                seal = build_import_artifact_seal(db_path=db, artifact_roots=[artifacts])

                self.assertEqual(seal["status"], "blocked")
                self.assertIn("batch_has_warnings", seal["artifacts"][0]["blockers"])

    def test_numeric_fields_require_exact_non_bool_integers(self) -> None:
        base = {
            "id": 1,
            "source_label": "fixture",
            "dataset_kind": "intraday_csv",
            "data_trust": "trusted",
            "input_path": "fixture.csv",
            "file_hash": "hash",
            "total_rows": 1,
            "imported_rows": 1,
            "duplicate_rows": 0,
            "rejected_rows": 0,
            "warnings_json": "[]",
        }
        for field, value in (("total_rows", 1.5), ("imported_rows", "1"), ("duplicate_rows", True)):
            with self.subTest(field=field, value=value):
                result = _batch_reconciliation({**base, field: value}, 1)
                self.assertFalse(result["numeric_fields_valid"])
                self.assertFalse(result["eligible"])


if __name__ == "__main__":
    unittest.main()
