from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.backup_evidence_stores import run_evidence_backup


class EvidenceBackupTests(unittest.TestCase):
    def _make_sqlite(self, path: Path, value: str) -> None:
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO evidence (value) VALUES (?)", (value,))
            conn.commit()

    def test_sqlite_backups_use_backup_api_and_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.db"
            backup_root = root / "backups"
            self._make_sqlite(source, "irreplaceable")

            manifest = run_evidence_backup(
                backup_root=backup_root,
                sqlite_stores=(("source", source),),
                include_postgres=False,
                generated_at_utc="2026-06-12T12:00:00Z",
            )

            store = manifest["stores"][0]
            self.assertEqual(manifest["status"], "backup_completed")
            self.assertEqual(store["status"], "backed_up")
            backup_path = Path(store["destination_path"])
            with closing(sqlite3.connect(backup_path)) as conn:
                rows = conn.execute("SELECT value FROM evidence").fetchall()
            self.assertEqual(rows, [("irreplaceable",)])

            manifest_path = Path(manifest["run_dir"]) / "manifest.json"
            self.assertTrue(manifest_path.exists())
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["report_id"], "evidence_store_backup")

    def test_missing_sqlite_store_is_skipped_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.db"
            manifest = run_evidence_backup(
                backup_root=root / "backups",
                sqlite_stores=(("missing", missing),),
                include_postgres=False,
                generated_at_utc="2026-06-12T12:00:00Z",
            )

            self.assertFalse(missing.exists())
            self.assertEqual(manifest["stores"][0]["status"], "skipped_missing")

    def test_weekly_copy_manifest_records_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.db"
            self._make_sqlite(source, "weekly")

            manifest = run_evidence_backup(
                backup_root=root / "backups",
                sqlite_stores=(("source", source),),
                include_postgres=False,
                weekly_copy=True,
                weekly_copy_dir=root / "weekly",
                generated_at_utc="2026-06-12T12:00:00Z",
            )

            destination = Path(manifest["weekly_copy"]["destination_path"])
            copied_manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(copied_manifest["weekly_copy"]["status"], "copied")
            self.assertEqual(copied_manifest["weekly_copy"]["destination_path"], str(destination))


if __name__ == "__main__":
    unittest.main()
