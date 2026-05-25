from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TMP_TEST_PATTERN = re.compile(r"^\.tmp-test(?:[-\w].*)?$", re.IGNORECASE)
TMP_DEAD_PATTERN = re.compile(r"^\.tmp-dead(?:[-\w].*)?$", re.IGNORECASE)
ROOT_TMP_PATTERN = re.compile(r"^tmp[a-z0-9_]{6,}$", re.IGNORECASE)


def _is_legacy_repo_temp(path: Path) -> bool:
    name = path.name
    if not path.is_dir():
        return False
    if name == "tmp_public":
        return False
    if name == "tmp":
        return True
    if TMP_TEST_PATTERN.fullmatch(name):
        return True
    if TMP_DEAD_PATTERN.fullmatch(name):
        return True
    return bool(ROOT_TMP_PATTERN.fullmatch(name))


def _candidate_paths(root: Path) -> list[Path]:
    candidates: dict[str, Path] = {}
    for entry in root.iterdir():
        if _is_legacy_repo_temp(entry):
            candidates[str(entry.resolve())] = entry
    return [candidates[key] for key in sorted(candidates)]


def _classify_exception(exc: BaseException) -> tuple[str, bool]:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    winerror = getattr(exc, "winerror", None)
    permission_denied = isinstance(exc, PermissionError) or "access is denied" in lowered or winerror == 5
    return message, permission_denied


def _remove_path(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path.resolve()),
        "name": path.name,
        "exists": path.exists(),
    }
    if not record["exists"]:
        record["status"] = "missing"
        return record

    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    except Exception as exc:
        message, permission_denied = _classify_exception(exc)
        record["status"] = "blocked" if permission_denied else "failed"
        record["error"] = message
        record["requires_elevation"] = permission_denied
        return record

    record["status"] = "removed"
    record["exists_after"] = path.exists()
    return record


def cleanup_repo_tempdirs(root: Path) -> dict[str, Any]:
    results = [_remove_path(path) for path in _candidate_paths(root)]
    removed = [item for item in results if item["status"] == "removed"]
    blocked = [item for item in results if item["status"] == "blocked"]
    failed = [item for item in results if item["status"] == "failed"]
    return {
        "repo_root": str(root.resolve()),
        "candidate_count": len(results),
        "removed_count": len(removed),
        "blocked_count": len(blocked),
        "failed_count": len(failed),
        "requires_elevation": bool(blocked),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove legacy automation temp directories that were created in the repo root."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the cleanup summary as JSON.",
    )
    args = parser.parse_args()

    summary = cleanup_repo_tempdirs(ROOT)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"repo_root: {summary['repo_root']}")
        print(f"candidate_count: {summary['candidate_count']}")
        print(f"removed_count: {summary['removed_count']}")
        print(f"blocked_count: {summary['blocked_count']}")
        print(f"failed_count: {summary['failed_count']}")
        if summary["requires_elevation"]:
            print("requires_elevation: true")
        for item in summary["results"]:
            line = f"{item['status']}: {item['path']}"
            if item.get("error"):
                line += f" :: {item['error']}"
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
