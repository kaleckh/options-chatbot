from __future__ import annotations

import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.archive_inactive_project_data import (
    ACKNOWLEDGEMENT,
    InactiveArchiveError,
    archive_inactive_data,
    build_archive_plan,
    _restore_moved_sources,
)


class InactiveProjectDataArchiveTests(unittest.TestCase):
    def test_archive_is_verified_before_sources_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data" / "day-trading" / "crypto"
            source.mkdir(parents=True)
            first = source / "first.json"
            second = source / "second.txt"
            first.write_text(json.dumps({"rows": list(range(100))}), encoding="utf-8")
            second.write_text("evidence\n" * 100, encoding="utf-8")

            result = archive_inactive_data(
                root=root,
                acknowledgement=ACKNOWLEDGEMENT,
                generated_at_utc="2026-07-10T00:00:00Z",
            )

            self.assertEqual(result["status"], "archived")
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            archive = Path(result["archive_path"])
            self.assertTrue(archive.exists())
            with tarfile.open(archive, "r:gz") as bundle:
                self.assertEqual(
                    set(bundle.getnames()),
                    {"crypto/first.json", "crypto/second.txt", "MANIFEST.json"},
                )
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["files"]), 2)

    def test_dry_run_does_not_write_or_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data" / "day-trading"
            source.mkdir(parents=True)
            file = source / "state.json"
            file.write_text("state", encoding="utf-8")

            plan = build_archive_plan(root=root)

            self.assertEqual(plan["status"], "dry_run")
            self.assertTrue(file.exists())
            self.assertFalse((source / ".archive").exists())

    def test_non_allowlisted_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InactiveArchiveError):
                build_archive_plan(root=Path(tmp), relative_source="data/options-validation")

    def test_existing_archive_destination_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data" / "day-trading"
            source.mkdir(parents=True)
            file = source / "state.json"
            file.write_text("state", encoding="utf-8")
            archive_dir = source / ".archive"
            archive_dir.mkdir()
            collision = archive_dir / "day-trading-20260710T000000Z.tar.gz"
            collision.write_bytes(b"existing")

            with self.assertRaises(InactiveArchiveError):
                archive_inactive_data(
                    root=root,
                    acknowledgement=ACKNOWLEDGEMENT,
                    generated_at_utc="2026-07-10T00:00:00Z",
                )

            self.assertEqual(collision.read_bytes(), b"existing")
            self.assertTrue(file.exists())

    def test_restore_conflict_preserves_staged_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "data" / "day-trading" / "state.json"
            staged = root / "data" / "day-trading" / ".archive" / ".staging-test" / "state.json"
            original.parent.mkdir(parents=True)
            staged.parent.mkdir(parents=True)
            original.write_text("NEW", encoding="utf-8")
            staged.write_text("OLD", encoding="utf-8")

            issues = _restore_moved_sources([(original, staged)], staged.parent)

            self.assertTrue(issues)
            self.assertEqual(original.read_text(encoding="utf-8"), "NEW")
            self.assertEqual(staged.read_text(encoding="utf-8"), "OLD")


if __name__ == "__main__":
    unittest.main()
