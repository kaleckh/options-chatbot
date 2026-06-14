from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.backup_evidence_stores import DEFAULT_SQLITE_STORES, _prune_old_backups, run_evidence_backup


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

    def test_default_sqlite_store_set_includes_both_forward_ledgers(self) -> None:
        store_ids = {store_id for store_id, _path in DEFAULT_SQLITE_STORES}

        self.assertEqual(
            store_ids,
            {
                "chat_history",
                "forward_tracking_archive",
                "forward_tracking_authoritative",
                "options_history",
            },
        )

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

    def test_retention_prunes_timestamped_runs_older_than_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_root = Path(tmp)
            stale = backup_root / "20260527T000000Z"
            fresh = backup_root / "20260609T000000Z"
            non_run = backup_root / "manual-keep"
            for path in (stale, fresh, non_run):
                path.mkdir()
                (path / "manifest.json").write_text("{}", encoding="utf-8")

            removed = _prune_old_backups(
                backup_root,
                retention_days=14,
                now=datetime(2026, 6, 14, tzinfo=UTC),
            )

            self.assertEqual(removed, [str(stale)])
            self.assertFalse(stale.exists())
            self.assertTrue(fresh.exists())
            self.assertTrue(non_run.exists())

    def test_postgres_backup_uses_pg_dump_custom_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_root = Path(tmp) / "backups"

            def fake_run(command, **_kwargs):
                destination = Path(command[3])
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"PGDMP")
                return Mock(returncode=0, stderr="", stdout="")

            with patch(
                "scripts.backup_evidence_stores.build_operational_provenance",
                return_value={"run_id": "test-backup"},
            ):
                with patch("scripts.backup_evidence_stores.subprocess.run", side_effect=fake_run) as run:
                    manifest = run_evidence_backup(
                        backup_root=backup_root,
                        sqlite_stores=(),
                        include_postgres=True,
                        database_url="postgresql://user:pass@localhost/db",
                        generated_at_utc="2026-06-12T12:00:00Z",
                    )

            postgres = manifest["stores"][0]
            self.assertEqual(postgres["status"], "backed_up")
            command = run.call_args.args[0]
            self.assertEqual(command[0], "pg_dump")
            self.assertIn("--format=custom", command)
            self.assertIn("postgresql://user:pass@localhost/db", command)


if __name__ == "__main__":
    unittest.main()
