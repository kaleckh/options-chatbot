from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.archive_project_memory import (
    ACKNOWLEDGEMENT,
    MEMORY_FILES,
    ProjectMemoryArchiveError,
    build_archive_plan,
    capture_project_memory_baseline,
    project_memory_corpus_paths,
    verify_archive_manifest,
)


def _make_memory_files(root: Path) -> None:
    for relative, _, _ in MEMORY_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n\n## 2026-06-01\n\nDurable content for {relative}.\n", encoding="utf-8")


def _resign(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProjectMemoryArchiveTests(unittest.TestCase):
    def test_capture_is_byte_exact_and_manifest_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_memory_files(root)

            result = capture_project_memory_baseline(
                root=root,
                capture_date="2026-07-10",
                acknowledgement=ACKNOWLEDGEMENT,
                captured_at_utc="2026-07-10T00:00:00Z",
            )

            self.assertEqual(result["status"], "captured")
            manifest_path = Path(result["manifest_path"])
            verification = verify_archive_manifest(root=root, manifest_path=manifest_path)
            self.assertEqual(verification["status"], "pass")
            manifest = verification["manifest"]
            worklog = next(item for item in manifest["files"] if item["logical_path"] == "docs/WORKLOG.md")
            self.assertTrue(worklog["living_history_ingest"])
            self.assertEqual(worklog["earliest_date"], "2026-06-01")
            self.assertEqual(
                (root / worklog["logical_path"]).read_bytes(),
                (root / worklog["archive_path"]).read_bytes(),
            )
            corpus = project_memory_corpus_paths(root=root, logical_path="docs/WORKLOG.md")
            self.assertEqual(corpus[-1], root / "docs" / "WORKLOG.md")
            self.assertEqual(corpus[0], root / worklog["archive_path"])

    def test_manifest_tamper_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_memory_files(root)
            result = capture_project_memory_baseline(
                root=root,
                capture_date="2026-07-10",
                acknowledgement=ACKNOWLEDGEMENT,
            )
            manifest_path = Path(result["manifest_path"])
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["captured_at_utc"] = "tampered"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")

            verification = verify_archive_manifest(root=root, manifest_path=manifest_path)

            self.assertEqual(verification["status"], "fail")
            self.assertIn("manifest_sha256_mismatch", verification["issues"])

    def test_target_is_immutable_and_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_memory_files(root)
            plan = build_archive_plan(root=root, capture_date="2026-07-10")
            self.assertEqual(plan["status"], "dry_run")
            self.assertFalse(Path(plan["target"]).exists())
            capture_project_memory_baseline(
                root=root,
                capture_date="2026-07-10",
                acknowledgement=ACKNOWLEDGEMENT,
            )
            with self.assertRaises(ProjectMemoryArchiveError):
                capture_project_memory_baseline(
                    root=root,
                    capture_date="2026-07-10",
                    acknowledgement=ACKNOWLEDGEMENT,
                )

    def test_capture_date_cannot_escape_archive_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_memory_files(root)

            with self.assertRaises(ProjectMemoryArchiveError):
                build_archive_plan(root=root, capture_date="../../../../escaped")

            self.assertFalse((root / "escaped").exists())

    def test_recomputed_hash_cannot_change_manifest_policy_semantics(self) -> None:
        cases = ("flip_ingest", "omit_worklog", "duplicate_worklog", "sibling_substitution")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _make_memory_files(root)
                result = capture_project_memory_baseline(
                    root=root,
                    capture_date="2026-07-10",
                    acknowledgement=ACKNOWLEDGEMENT,
                )
                manifest_path = Path(result["manifest_path"])
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                worklog = next(item for item in payload["files"] if item["logical_path"] == "docs/WORKLOG.md")
                if case == "flip_ingest":
                    worklog["living_history_ingest"] = False
                elif case == "omit_worklog":
                    payload["files"].remove(worklog)
                elif case == "duplicate_worklog":
                    payload["files"].append(dict(worklog))
                else:
                    sibling = root / "docs" / "archive" / "project-memory" / "2026-07-11" / "WORKLOG.md"
                    sibling.parent.mkdir(parents=True)
                    sibling.write_bytes((root / worklog["archive_path"]).read_bytes())
                    worklog["archive_path"] = "docs/archive/project-memory/2026-07-11/WORKLOG.md"
                _resign(payload)
                manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

                verification = verify_archive_manifest(root=root, manifest_path=manifest_path)

                self.assertEqual(verification["status"], "fail")
                with self.assertRaises(ProjectMemoryArchiveError):
                    project_memory_corpus_paths(root=root, logical_path="docs/WORKLOG.md")


if __name__ == "__main__":
    unittest.main()
