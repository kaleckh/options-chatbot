from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SOURCES = {"data/day-trading"}
ACKNOWLEDGEMENT = "ARCHIVE_VERIFIED_INACTIVE_DATA_V1"


class InactiveArchiveError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source(root: Path, relative_source: str) -> Path:
    normalized = relative_source.replace("\\", "/").strip("/")
    if normalized not in ALLOWED_SOURCES:
        raise InactiveArchiveError(f"source is not allowlisted: {relative_source}")
    resolved_root = root.resolve()
    source = (root / normalized).resolve()
    try:
        source.relative_to(resolved_root)
    except ValueError as exc:
        raise InactiveArchiveError("source escapes repository root") from exc
    return source


def _is_reparse_or_symlink(path: Path) -> bool:
    stat = path.lstat()
    attributes = int(getattr(stat, "st_file_attributes", 0))
    return path.is_symlink() or bool(attributes & 0x400)


def _validate_source_file(source: Path, path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(source.resolve())
    except ValueError as exc:
        raise InactiveArchiveError(f"source member escapes allowlisted root: {path}") from exc
    current = path
    while current != source.parent:
        if _is_reparse_or_symlink(current):
            raise InactiveArchiveError(f"source member uses symlink or reparse point: {current}")
        if current == source:
            break
        current = current.parent


def build_archive_plan(*, root: Path = ROOT, relative_source: str = "data/day-trading") -> dict[str, Any]:
    source = _safe_source(root, relative_source)
    archive_dir = source / ".archive"
    files = []
    if source.exists():
        for path in source.rglob("*"):
            if archive_dir in path.parents or not path.is_file():
                continue
            _validate_source_file(source, path)
            files.append(path)
        files.sort()
    return {
        "report_id": "inactive_project_data_archive_plan",
        "status": "dry_run",
        "source": str(source),
        "file_count": len(files),
        "source_bytes": sum(path.stat().st_size for path in files),
        "files": [path.relative_to(source).as_posix() for path in files],
        "deletes_before_verified_archive": False,
    }


def _verify_archive(archive: Path, manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected = {str(item["path"]): item for item in manifest["files"]}
    with tarfile.open(archive, "r:gz") as bundle:
        members = {member.name: member for member in bundle.getmembers() if member.isfile()}
        manifest_member = members.pop("MANIFEST.json", None)
        if manifest_member is None:
            issues.append("archive manifest missing")
        else:
            embedded = bundle.extractfile(manifest_member)
            if embedded is None:
                issues.append("archive manifest unreadable")
            else:
                try:
                    if json.loads(embedded.read().decode("utf-8")) != manifest:
                        issues.append("archive manifest content mismatch")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    issues.append("archive manifest invalid")
        if set(members) != set(expected):
            issues.append("archive member set mismatch")
        for name, item in expected.items():
            member = members.get(name)
            if member is None:
                continue
            extracted = bundle.extractfile(member)
            if extracted is None:
                issues.append(f"archive member unreadable: {name}")
                continue
            digest = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: extracted.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
            if size != int(item["size_bytes"]):
                issues.append(f"archive size mismatch: {name}")
            if digest.hexdigest() != item["sha256"]:
                issues.append(f"archive sha256 mismatch: {name}")
    return issues


def _restore_moved_sources(moved: list[tuple[Path, Path]], staging: Path) -> list[str]:
    issues: list[str] = []
    for original, staged in reversed(moved):
        if not staged.exists():
            continue
        if original.exists():
            issues.append(f"restore conflict; staged source preserved: {staged}")
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, original)
        except OSError as exc:
            issues.append(f"restore failed for {staged}: {exc}")
    if not issues:
        shutil.rmtree(staging, ignore_errors=True)
    return issues


def archive_inactive_data(
    *,
    root: Path = ROOT,
    relative_source: str = "data/day-trading",
    acknowledgement: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if acknowledgement != ACKNOWLEDGEMENT:
        raise InactiveArchiveError("archive acknowledgement token mismatch")
    source = _safe_source(root, relative_source)
    plan = build_archive_plan(root=root, relative_source=relative_source)
    if not plan["file_count"]:
        return {**plan, "status": "nothing_to_archive", "archive_path": ""}
    archive_dir = source / ".archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    generated = generated_at_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    stamp = generated.replace("-", "").replace(":", "").replace("+00:00", "Z")[:15] + "Z"
    archive = archive_dir / f"day-trading-{stamp}.tar.gz"
    sidecar = archive.with_suffix(".manifest.json")
    if archive.exists() or sidecar.exists():
        raise InactiveArchiveError(f"archive destination already exists: {archive}")
    source_files = [source / relative for relative in plan["files"]]
    staging = archive_dir / f".staging-{uuid.uuid4().hex}"
    moved: list[tuple[Path, Path]] = []
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for original in source_files:
            _validate_source_file(source, original)
            staged = staging / original.relative_to(source)
            staged.parent.mkdir(parents=True, exist_ok=True)
            os.replace(original, staged)
            moved.append((original, staged))
    except Exception:
        restore_issues = _restore_moved_sources(moved, staging)
        if restore_issues:
            raise InactiveArchiveError("; ".join(restore_issues))
        raise
    staged_files = [staging / relative for relative in plan["files"]]
    manifest: dict[str, Any] = {
        "report_id": "inactive_project_data_archive",
        "schema_version": 1,
        "generated_at_utc": generated,
        "source": relative_source,
        "files": [
            {
                "path": path.relative_to(staging).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in staged_files
        ],
    }
    manifest["source_bytes"] = sum(int(item["size_bytes"]) for item in manifest["files"])
    temporary = archive.with_suffix(f"{archive.suffix}.tmp")
    try:
        with tarfile.open(temporary, "w:gz", compresslevel=6) as bundle:
            for path in staged_files:
                bundle.add(path, arcname=path.relative_to(staging).as_posix(), recursive=False)
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            info = tarfile.TarInfo("MANIFEST.json")
            info.size = len(manifest_bytes)
            info.mtime = int(datetime.now(UTC).timestamp())
            bundle.addfile(info, io.BytesIO(manifest_bytes))
        issues = _verify_archive(temporary, manifest)
        if issues:
            raise InactiveArchiveError("; ".join(issues))
        os.replace(temporary, archive)
        sidecar.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.rmtree(staging)
    except Exception:
        temporary.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        restore_issues = _restore_moved_sources(moved, staging)
        if restore_issues:
            raise InactiveArchiveError("; ".join(restore_issues))
        raise
    for directory in sorted(
        (path for path in source.rglob("*") if path.is_dir() and path != archive_dir),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            continue
    return {
        **plan,
        "status": "archived",
        "archive_path": str(archive),
        "manifest_path": str(sidecar),
        "archive_bytes": archive.stat().st_size,
        "reclaimed_bytes": int(plan["source_bytes"]) - archive.stat().st_size - sidecar.stat().st_size,
        "verification": {"status": "pass", "issues": []},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive explicitly inactive project data with hash verification.")
    parser.add_argument("--source", default="data/day-trading", choices=sorted(ALLOWED_SOURCES))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = (
        archive_inactive_data(relative_source=args.source, acknowledgement=args.acknowledge)
        if args.apply
        else build_archive_plan(relative_source=args.source)
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['report_id']}: {result['status']} files={result['file_count']} bytes={result['source_bytes']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InactiveArchiveError as exc:
        print(f"archive_inactive_project_data: {exc}")
        raise SystemExit(2)
