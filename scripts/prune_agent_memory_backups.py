from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = ROOT / "data" / "agent-control" / "backups"
APPLY_ACKNOWLEDGEMENT = "DELETE_RESTORE_VERIFIED_REDUNDANT_AGENT_MEMORY_BACKUPS"
DEGRADED_APPLY_ACKNOWLEDGEMENT = "DELETE_REDUNDANT_MIRROR_DEGRADED_AGENT_MEMORY_BACKUPS"


class BackupRetentionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _created_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("created_at must be an ISO-8601 UTC string")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("created_at must be UTC")
    return parsed.astimezone(UTC)


def _tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink())


def _has_link_or_reparse(path: Path) -> bool:
    for item in (path, *path.rglob("*")):
        stat = item.lstat()
        if item.is_symlink() or int(getattr(stat, "st_file_attributes", 0)) & 0x400:
            return True
    return False


def _tree_identity(path: Path) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        stat = item.lstat()
        relative = item.relative_to(path).as_posix()
        result[relative] = (int(stat.st_size), int(stat.st_mtime_ns), int(stat.st_dev), int(stat.st_ino))
    return result


def _load_bundle(path: Path) -> tuple[dict[str, Any] | None, str]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return None, "manifest_missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not an object")
        created = _created_at(manifest.get("created_at"))
        if manifest.get("backup_id") != path.name:
            raise ValueError("backup_id does not match directory name")
        if _has_link_or_reparse(path):
            raise ValueError("bundle contains a symlink or reparse point")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"invalid_manifest: {exc}"
    return {
        "backup_id": path.name,
        "path": str(path.resolve()),
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "manifest_sha256": _sha256(manifest_path),
        "size_bytes": _tree_size(path),
    }, ""


def build_retention_plan(
    *,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    keep_daily: int = 3,
    keep_weekly: int = 4,
) -> dict[str, Any]:
    if keep_daily < 1 or keep_weekly < 1:
        raise BackupRetentionError("keep_daily and keep_weekly must both be positive")
    backup_root = backup_root.resolve()
    valid: list[dict[str, Any]] = []
    preserved_invalid: list[dict[str, str]] = []
    if backup_root.exists():
        for path in sorted(backup_root.iterdir()):
            if not path.is_dir() or path.name == ".retention-staging":
                continue
            bundle, issue = _load_bundle(path)
            if bundle is None:
                preserved_invalid.append({"path": str(path), "reason": issue})
            else:
                valid.append(bundle)
    valid.sort(key=lambda item: (str(item["created_at"]), str(item["backup_id"])), reverse=True)

    retained: dict[str, set[str]] = {}
    daily_seen: set[str] = set()
    weekly_seen: set[tuple[int, int]] = set()
    for item in valid:
        created = _created_at(item["created_at"])
        day = created.date().isoformat()
        if day not in daily_seen and len(daily_seen) < keep_daily:
            daily_seen.add(day)
            retained.setdefault(str(item["backup_id"]), set()).add("daily")
        iso_year, iso_week, _ = created.isocalendar()
        week = (iso_year, iso_week)
        if week not in weekly_seen and len(weekly_seen) < keep_weekly:
            weekly_seen.add(week)
            retained.setdefault(str(item["backup_id"]), set()).add("weekly")

    retained_items = [
        {**item, "retention_tiers": sorted(retained[str(item["backup_id"])])}
        for item in valid
        if str(item["backup_id"]) in retained
    ]
    candidates = [item for item in valid if str(item["backup_id"]) not in retained]
    return {
        "report_id": "agent_memory_backup_retention",
        "status": "dry_run",
        "backup_root": str(backup_root),
        "policy": {"keep_daily": keep_daily, "keep_weekly": keep_weekly},
        "valid_bundle_count": len(valid),
        "retained": retained_items,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "reclaimable_bytes": sum(int(item["size_bytes"]) for item in candidates),
        "preserved_invalid": preserved_invalid,
    }


def _default_restore_verifier(path: Path) -> dict[str, Any]:
    from agent_control import restore_check_memory_backup

    return restore_check_memory_backup(backup_dir=path)


def _plan_fingerprint(plan: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (str(item["backup_id"]), str(item["manifest_sha256"]))
            for item in plan.get("candidates", [])
        )
    )


def _is_mirror_only_degraded(result: dict[str, Any]) -> bool:
    if result.get("status") != "fail" or result.get("issues") != ["events.jsonl mirror audit failed"]:
        return False
    if any((result.get(name) or {}).get("status") != "pass" for name in ("ledger", "event_outbox", "anchors")):
        return False
    mirror = result.get("event_mirror") or {}
    allowed_issues = {
        "mirror hash differs from DB outbox",
        "mirror event fields differ from DB outbox",
        "mirror contains duplicate outbox id",
    }
    issues = mirror.get("issues")
    return bool(
        mirror.get("status") == "issues"
        and isinstance(issues, list)
        and issues
        and all(isinstance(item, dict) and item.get("issue") in allowed_issues for item in issues)
    )


def apply_retention_plan(
    plan: dict[str, Any],
    *,
    acknowledgement: str,
    verifier: Callable[[Path], dict[str, Any]] = _default_restore_verifier,
) -> dict[str, Any]:
    allow_mirror_degraded = acknowledgement == DEGRADED_APPLY_ACKNOWLEDGEMENT
    if acknowledgement not in {APPLY_ACKNOWLEDGEMENT, DEGRADED_APPLY_ACKNOWLEDGEMENT}:
        raise BackupRetentionError("backup-retention acknowledgement token mismatch")
    backup_root = Path(str(plan["backup_root"])).resolve()
    policy = plan.get("policy") or {}
    fresh = build_retention_plan(
        backup_root=backup_root,
        keep_daily=int(policy.get("keep_daily", 0)),
        keep_weekly=int(policy.get("keep_weekly", 0)),
    )
    if _plan_fingerprint(plan) != _plan_fingerprint(fresh):
        raise BackupRetentionError("backup set changed after planning; refusing a stale apply")
    if not fresh["retained"]:
        raise BackupRetentionError("retention plan has no retained backup")

    checked: list[dict[str, Any]] = []
    all_items = [*fresh["retained"], *fresh["candidates"]]
    identities: dict[str, dict[str, tuple[int, int, int, int]]] = {}
    for item in all_items:
        path = Path(str(item["path"]))
        before = _tree_identity(path)
        result = verifier(path)
        after = _tree_identity(path)
        if before != after:
            raise BackupRetentionError(f"backup changed during restore verification: {path}")
        verification_status = "pass"
        if result.get("status") != "pass" and allow_mirror_degraded and _is_mirror_only_degraded(result):
            verification_status = "degraded_mirror_only"
        elif result.get("status") != "pass":
            raise BackupRetentionError(f"restore verification failed; preserved all backups: {path}")
        identities[str(item["backup_id"])] = after
        checked.append({"backup_id": item["backup_id"], "status": verification_status})

    checked_by_id = {str(item["backup_id"]): str(item["status"]) for item in checked}
    newest_retained_id = str(fresh["retained"][0]["backup_id"])
    if checked_by_id.get(newest_retained_id) != "pass":
        raise BackupRetentionError("newest retained backup must pass the full restore-check")
    if not any(checked_by_id.get(str(item["backup_id"])) == "pass" for item in fresh["retained"]):
        raise BackupRetentionError("at least one retained backup must pass the full restore-check")

    final_plan = build_retention_plan(
        backup_root=backup_root,
        keep_daily=int(policy["keep_daily"]),
        keep_weekly=int(policy["keep_weekly"]),
    )
    if _plan_fingerprint(fresh) != _plan_fingerprint(final_plan):
        raise BackupRetentionError("backup set changed during restore verification; preserved all backups")

    staging_root = backup_root / ".retention-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    deleted: list[dict[str, Any]] = []
    try:
        for item in final_plan["candidates"]:
            path = Path(str(item["path"])).resolve()
            try:
                path.relative_to(backup_root)
            except ValueError as exc:
                raise BackupRetentionError(f"backup path escapes backup root: {path}") from exc
            if _has_link_or_reparse(path):
                raise BackupRetentionError(f"backup contains a symlink or reparse point: {path}")
            if _tree_identity(path) != identities[str(item["backup_id"])]:
                raise BackupRetentionError(f"backup changed immediately before deletion: {path}")
            staged = staging_root / f"{uuid.uuid4().hex}-{path.name}"
            os.replace(path, staged)
            if _tree_identity(staged) != identities[str(item["backup_id"])]:
                if not path.exists():
                    os.replace(staged, path)
                raise BackupRetentionError(f"backup changed during atomic staging; preserved at {staged}")
            shutil.rmtree(staged)
            deleted.append(item)
    finally:
        try:
            staging_root.rmdir()
        except OSError:
            pass
    return {
        **{key: value for key, value in final_plan.items() if key != "status"},
        "status": "applied",
        "restore_checked": checked,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "reclaimed_bytes": sum(int(item["size_bytes"]) for item in deleted),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune redundant agent-memory backups after restore assessment.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--keep-daily", type=int, default=3)
    parser.add_argument("--keep-weekly", type=int, default=4)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = build_retention_plan(
        backup_root=args.backup_root,
        keep_daily=args.keep_daily,
        keep_weekly=args.keep_weekly,
    )
    if args.apply:
        result = apply_retention_plan(result, acknowledgement=args.acknowledge)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"{result['report_id']}: {result['status']} "
            f"candidates={result['candidate_count']} bytes={result['reclaimable_bytes']}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupRetentionError as exc:
        print(f"prune_agent_memory_backups: {exc}", file=sys.stderr)
        raise SystemExit(2)
