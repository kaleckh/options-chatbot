from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "docs" / "archive" / "project-memory"
ACKNOWLEDGEMENT = "CAPTURE_PROJECT_MEMORY_BASELINE_V1"
MEMORY_FILES: tuple[tuple[str, str, bool], ...] = (
    ("docs/PROJECT_CONTEXT.md", "current_context", False),
    ("docs/DECISIONS.md", "decisions", True),
    ("docs/WORKLOG.md", "worklog", True),
    ("docs/NEXT_STEPS.md", "current_actions", False),
    ("docs/index.md", "documentation_index", False),
)
DATE_HEADING_RE = re.compile(r"(?m)^##\s+(20\d{2}-\d{2}-\d{2})\b")


class ProjectMemoryArchiveError(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_archive_plan(*, root: Path = ROOT, capture_date: str | None = None) -> dict[str, Any]:
    date = capture_date or datetime.now(UTC).date().isoformat()
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ProjectMemoryArchiveError("capture_date must be exact YYYY-MM-DD") from exc
    if parsed_date.isoformat() != date:
        raise ProjectMemoryArchiveError("capture_date must round-trip as exact YYYY-MM-DD")
    archive_root = (root / "docs" / "archive" / "project-memory").resolve()
    target = (archive_root / date).resolve()
    try:
        target.relative_to(archive_root)
    except ValueError as exc:
        raise ProjectMemoryArchiveError("archive target escapes project-memory archive root") from exc
    files = []
    for relative, parser_type, participates in MEMORY_FILES:
        source = root / relative
        if not source.is_file():
            raise ProjectMemoryArchiveError(f"memory source missing: {relative}")
        files.append(
            {
                "logical_path": relative,
                "archive_path": f"docs/archive/project-memory/{date}/{Path(relative).name}",
                "parser_type": parser_type,
                "living_history_ingest": participates,
                "size_bytes": source.stat().st_size,
                "mtime_ns": source.stat().st_mtime_ns,
            }
        )
    return {
        "report_id": "project_memory_archive_plan",
        "status": "dry_run",
        "capture_date": date,
        "target": str(target),
        "files": files,
        "total_bytes": sum(int(item["size_bytes"]) for item in files),
    }


def verify_archive_manifest(*, root: Path = ROOT, manifest_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "issues": [f"manifest_unreadable:{exc}"], "manifest": {}}
    if not isinstance(payload, dict):
        return {"status": "fail", "issues": ["manifest_not_object"], "manifest": {}}
    resolved_root = root.resolve()
    archive_root = (resolved_root / "docs" / "archive" / "project-memory").resolve()
    capture_date = str(payload.get("capture_date") or "")
    try:
        parsed_date = datetime.strptime(capture_date, "%Y-%m-%d").date()
        if parsed_date.isoformat() != capture_date:
            raise ValueError
    except ValueError:
        issues.append("invalid_capture_date")
    expected_manifest_path = (archive_root / capture_date / "manifest.json").resolve()
    if manifest_path.resolve() != expected_manifest_path:
        issues.append("manifest_path_not_bound_to_capture_date")
    if payload.get("report_id") != "project_memory_archive_manifest":
        issues.append("unexpected_report_id")
    if payload.get("schema_version") != 1:
        issues.append("unsupported_schema_version")
    if payload.get("logical_identity_rule") != "archived WORKLOG and DECISIONS entries retain their original logical_path":
        issues.append("unexpected_logical_identity_rule")
    captured_at = payload.get("captured_at_utc")
    try:
        if not isinstance(captured_at, str) or not captured_at.endswith("Z"):
            raise ValueError
        datetime.fromisoformat(captured_at[:-1] + "+00:00")
    except ValueError:
        issues.append("invalid_captured_at_utc")
    expected_hash = str(payload.get("manifest_sha256") or "")
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if _sha256_bytes(_canonical(unsigned).encode("utf-8")) != expected_hash:
        issues.append("manifest_sha256_mismatch")

    expected_files = {
        logical_path: {"parser_type": parser_type, "living_history_ingest": participates}
        for logical_path, parser_type, participates in MEMORY_FILES
    }
    files = payload.get("files")
    if not isinstance(files, list):
        issues.append("manifest_files_not_list")
        files = []
    by_logical: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        if not isinstance(item, dict):
            issues.append("manifest_file_not_object")
            continue
        by_logical.setdefault(str(item.get("logical_path") or ""), []).append(item)
    if set(by_logical) != set(expected_files):
        issues.append("manifest_logical_file_set_mismatch")
    for logical_path, entries in by_logical.items():
        if len(entries) != 1:
            issues.append(f"manifest_logical_file_not_unique:{logical_path}")
    for logical_path, expected in expected_files.items():
        entries = by_logical.get(logical_path) or []
        if len(entries) != 1:
            continue
        item = entries[0]
        expected_archive_path = f"docs/archive/project-memory/{capture_date}/{Path(logical_path).name}"
        if item.get("archive_path") != expected_archive_path:
            issues.append(f"archive_path_policy_mismatch:{logical_path}")
        if item.get("parser_type") != expected["parser_type"]:
            issues.append(f"parser_type_policy_mismatch:{logical_path}")
        if item.get("living_history_ingest") is not expected["living_history_ingest"]:
            issues.append(f"living_history_ingest_policy_mismatch:{logical_path}")
        if item.get("authority") != "historical_evidence_record_not_current_source_of_truth":
            issues.append(f"authority_policy_mismatch:{logical_path}")
        archive = (resolved_root / expected_archive_path).resolve()
        try:
            archive.relative_to(expected_manifest_path.parent)
        except ValueError:
            issues.append(f"archive_path_escapes_capture_directory:{logical_path}")
            continue
        if not archive.is_file():
            issues.append(f"missing:{expected_archive_path}")
            continue
        data = archive.read_bytes()
        size_bytes = item.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            issues.append(f"invalid_size:{expected_archive_path}")
        elif len(data) != size_bytes:
            issues.append(f"size_mismatch:{expected_archive_path}")
        sha256 = item.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            issues.append(f"invalid_sha256:{expected_archive_path}")
        elif _sha256_bytes(data) != sha256:
            issues.append(f"sha256_mismatch:{expected_archive_path}")
    return {"status": "pass" if not issues else "fail", "issues": issues, "manifest": payload}


def project_memory_corpus_paths(*, root: Path = ROOT, logical_path: str) -> list[Path]:
    known_paths = {relative for relative, _, _ in MEMORY_FILES}
    if logical_path not in known_paths:
        raise ProjectMemoryArchiveError(f"unknown project-memory logical path: {logical_path}")
    resolved_root = root.resolve()
    archive_root = (resolved_root / "docs" / "archive" / "project-memory").resolve()
    paths: list[Path] = []
    if archive_root.exists():
        for manifest_path in sorted(archive_root.glob("*/manifest.json")):
            verification = verify_archive_manifest(root=resolved_root, manifest_path=manifest_path)
            if verification["status"] != "pass":
                raise ProjectMemoryArchiveError(
                    f"invalid project-memory archive {manifest_path}: {', '.join(verification['issues'])}"
                )
            for item in verification["manifest"].get("files") or []:
                if item.get("logical_path") != logical_path:
                    continue
                archive = (resolved_root / str(item["archive_path"])).resolve()
                try:
                    archive.relative_to(archive_root)
                except ValueError as exc:
                    raise ProjectMemoryArchiveError(f"archive member escapes project-memory root: {archive}") from exc
                paths.append(archive)
    live = (resolved_root / logical_path).resolve()
    try:
        live.relative_to(resolved_root)
    except ValueError as exc:
        raise ProjectMemoryArchiveError(f"live project-memory path escapes repository root: {logical_path}") from exc
    if live.is_file():
        paths.append(live)
    return list(dict.fromkeys(paths))


def capture_project_memory_baseline(
    *,
    root: Path = ROOT,
    capture_date: str | None = None,
    acknowledgement: str,
    captured_at_utc: str | None = None,
) -> dict[str, Any]:
    if acknowledgement != ACKNOWLEDGEMENT:
        raise ProjectMemoryArchiveError("archive acknowledgement token mismatch")
    plan = build_archive_plan(root=root, capture_date=capture_date)
    target = Path(plan["target"])
    if target.exists():
        raise ProjectMemoryArchiveError(f"immutable archive target already exists: {target}")
    archive_root = target.parent
    archive_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=archive_root))
    try:
        manifest_files: list[dict[str, Any]] = []
        captured_identities: dict[str, tuple[int, int]] = {}
        for item in plan["files"]:
            source = root / str(item["logical_path"])
            before = source.stat()
            data = source.read_bytes()
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ProjectMemoryArchiveError(f"memory source changed during capture: {source}")
            captured_identities[str(source)] = (before.st_size, before.st_mtime_ns)
            destination = staging / Path(str(item["archive_path"])).name
            destination.write_bytes(data)
            text = data.decode("utf-8", errors="replace")
            dates = DATE_HEADING_RE.findall(text)
            manifest_files.append(
                {
                    **item,
                    "size_bytes": len(data),
                    "sha256": _sha256_bytes(data),
                    "source_mtime_ns": before.st_mtime_ns,
                    "earliest_date": min(dates) if dates else None,
                    "latest_date": max(dates) if dates else None,
                    "authority": "historical_evidence_record_not_current_source_of_truth",
                }
            )
        for source_text, identity in captured_identities.items():
            source = Path(source_text)
            current = source.stat()
            if identity != (current.st_size, current.st_mtime_ns):
                raise ProjectMemoryArchiveError(f"memory corpus changed during capture: {source}")
        captured = captured_at_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        manifest: dict[str, Any] = {
            "report_id": "project_memory_archive_manifest",
            "schema_version": 1,
            "capture_date": plan["capture_date"],
            "captured_at_utc": captured,
            "files": manifest_files,
            "logical_identity_rule": "archived WORKLOG and DECISIONS entries retain their original logical_path",
        }
        manifest["manifest_sha256"] = _sha256_bytes(_canonical(manifest).encode("utf-8"))
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    verification = verify_archive_manifest(root=root, manifest_path=target / "manifest.json")
    if verification["status"] != "pass":
        raise ProjectMemoryArchiveError("archive verification failed: " + ", ".join(verification["issues"]))
    return {
        **plan,
        "status": "captured",
        "manifest_path": str(target / "manifest.json"),
        "verification": {"status": "pass", "issues": []},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture an immutable baseline of project memory files.")
    parser.add_argument("--capture-date")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = (
        capture_project_memory_baseline(
            capture_date=args.capture_date,
            acknowledgement=args.acknowledge,
        )
        if args.apply
        else build_archive_plan(capture_date=args.capture_date)
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['report_id']}: {result['status']} bytes={result['total_bytes']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProjectMemoryArchiveError as exc:
        print(f"archive_project_memory: {exc}")
        raise SystemExit(2)
