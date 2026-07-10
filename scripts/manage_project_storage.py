from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "data" / "contracts" / "project-storage-retention-policy.json"
TIMESTAMP_RE = re.compile(r"(?P<stamp>20\d{6}T\d{6}Z)")
TIMESTAMP_BYTES_RE = re.compile(rb"20\d{6}T\d{6}Z")


class StoragePolicyError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise StoragePolicyError("unsupported storage policy schema")
    if payload.get("default_mode") != "dry_run":
        raise StoragePolicyError("storage policy must default to dry_run")
    return payload


def _resolved_under(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise StoragePolicyError(f"path escapes repository root: {path}") from exc
    return resolved


def _relative(root: Path, path: Path) -> str:
    return _resolved_under(root, path).relative_to(root.resolve()).as_posix()


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except (FileNotFoundError, OSError):
            continue
    return total


def _age_hours(path: Path, *, now: datetime) -> float:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return max((now - modified).total_seconds() / 3600.0, 0.0)


def _tracked_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise StoragePolicyError("git ls-files failed; refusing cleanup planning")
    return {
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in result.stdout.split(b"\0")
        if item
    }


def _file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "device": int(stat.st_dev),
        "inode": int(stat.st_ino),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _referenced_timestamps(
    *, root: Path, tracked: set[str], snapshot_rules: Iterable[dict[str, Any]]
) -> set[str]:
    """Conservatively retain any run timestamp referenced by durable or latest files."""
    paths: set[Path] = set()
    text_suffixes = {".md", ".json", ".jsonl", ".py", ".js", ".ts", ".tsx", ".txt", ".yaml", ".yml"}
    for rel in tracked:
        path = root / rel
        if path.is_file() and path.suffix.lower() in text_suffixes:
            paths.add(path)
    for rule in snapshot_rules:
        snapshot_root = root / str(rule["path"])
        if not snapshot_root.exists():
            continue
        for path in snapshot_root.rglob("*"):
            if not path.is_file():
                continue
            stem = path.stem.lower()
            if stem == "latest" or stem.endswith("_latest"):
                paths.add(path)
    stamps: set[str] = set()
    for path in paths:
        try:
            with path.open("rb") as handle:
                overlap = b""
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    scan = overlap + chunk
                    stamps.update(match.group(0).decode("ascii") for match in TIMESTAMP_BYTES_RE.finditer(scan))
                    overlap = scan[-32:]
        except (OSError, PermissionError):
            continue
    return stamps


def _is_protected(relative_path: str, policy: dict[str, Any], tracked: set[str]) -> bool:
    normalized = relative_path.strip("/")
    if normalized in tracked:
        return True
    if normalized in set(policy.get("protected_exact_paths") or []):
        return True
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in policy.get("protected_path_prefixes") or []
    )


def _candidate(
    *,
    root: Path,
    path: Path,
    category: str,
    action: str,
    reason: str,
) -> dict[str, Any]:
    identity = _file_identity(path)
    return {
        "path": _relative(root, path),
        "category": category,
        "action": action,
        "reason": reason,
        "size_bytes": _path_size(path),
        "mtime_ns": identity["mtime_ns"],
        "device": identity["device"],
        "inode": identity["inode"],
    }


def _snapshot_candidates(
    *,
    root: Path,
    rule: dict[str, Any],
    policy: dict[str, Any],
    tracked: set[str],
    referenced_timestamps: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    snapshot_root = _resolved_under(root, root / str(rule["path"]))
    if not snapshot_root.exists():
        return []
    keep_recent = max(int(rule.get("keep_recent_runs", 3)), 1)
    keep_monthly = max(int(rule.get("keep_monthly_runs", 0)), 0)
    min_age = max(float(rule.get("min_age_hours", 24)), 0.0)
    by_family: dict[tuple[Path, str], dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    iterator = snapshot_root.rglob("*") if bool(rule.get("recursive", True)) else snapshot_root.glob("*")
    for path in iterator:
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in {".json", ".md", ".csv"}:
            continue
        match = TIMESTAMP_RE.search(path.name)
        if match:
            family = path.name[: match.start()].rstrip("_-. ") if rule.get("family_from_filename") else ""
            by_family[(path.parent, family)][match.group("stamp")].append(path)

    candidates: list[dict[str, Any]] = []
    for groups in by_family.values():
        stamps = sorted(groups, reverse=True)
        retained = set(stamps[:keep_recent])
        keep_daily_days = max(int(rule.get("keep_daily_days", 0)), 0)
        if keep_daily_days:
            cutoff = now - timedelta(days=keep_daily_days)
            daily_seen: set[str] = set()
            for stamp in stamps:
                stamp_dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                day = stamp[:8]
                if stamp_dt >= cutoff and day not in daily_seen:
                    retained.add(stamp)
                    daily_seen.add(day)
        keep_weekly_weeks = max(int(rule.get("keep_weekly_weeks", 0)), 0)
        if keep_weekly_weeks:
            weekly_seen: set[tuple[int, int]] = set()
            for stamp in stamps:
                stamp_dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                iso_year, iso_week, _ = stamp_dt.isocalendar()
                week = (iso_year, iso_week)
                if week not in weekly_seen and len(weekly_seen) < keep_weekly_weeks:
                    retained.add(stamp)
                    weekly_seen.add(week)
        months: list[str] = []
        for stamp in stamps:
            month = stamp[:6]
            if month not in months:
                months.append(month)
        for month in months[:keep_monthly]:
            retained.add(next(stamp for stamp in stamps if stamp.startswith(month)))
        if rule.get("preserve_status_transitions"):
            ascending = sorted(stamps)
            payloads = {stamp: _bundle_payload(groups[stamp]) for stamp in ascending}
            for stamp, payload in payloads.items():
                if payload is None or _is_evidence_milestone(payload):
                    retained.add(stamp)
            fingerprints = {
                stamp: _status_fingerprint(payloads[stamp])
                for stamp in ascending
                if payloads[stamp] is not None
            }
            comparable = [(stamp, fingerprints[stamp]) for stamp in ascending if stamp in fingerprints and fingerprints[stamp] is not None]
            if comparable:
                retained.add(comparable[0][0])
                retained.add(comparable[-1][0])
                for (previous_stamp, previous), (stamp, current) in zip(comparable, comparable[1:]):
                    if current != previous:
                        retained.update({previous_stamp, stamp})
        for stamp, paths in groups.items():
            if stamp in retained or stamp in referenced_timestamps:
                continue
            for path in paths:
                rel = _relative(root, path)
                if _is_protected(rel, policy, tracked) or _age_hours(path, now=now) < min_age:
                    continue
                candidates.append(
                    _candidate(
                        root=root,
                        path=path,
                        category="generated_snapshots",
                        action="delete_file",
                        reason=f"timestamped snapshot outside recent={keep_recent} monthly={keep_monthly} retention",
                    )
                )
    return candidates


def _bundle_payload(paths: Iterable[Path]) -> dict[str, Any] | None:
    for path in sorted(paths):
        if path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _status_fingerprint(payload: dict[str, Any]) -> tuple[tuple[str, str], ...] | None:
    milestone_keys = {
        "accepted_profitability",
        "candidate_rows_staged",
        "cohort_append_performed",
        "remaining_rows",
        "strict_forward_rows",
    }
    values: list[tuple[str, str]] = []
    for key, value in payload.items():
        normalized = str(key).lower()
        status_key = (
            normalized == "status"
            or normalized.endswith("_status")
            or normalized == "verdict"
            or normalized.endswith("_verdict")
            or normalized in {"promotion_ready", "release_gate_status"}
            or normalized in milestone_keys
        )
        if status_key and isinstance(value, (str, int, float, bool, type(None))):
            values.append((str(key), json.dumps(value, sort_keys=True)))
    return tuple(sorted(values)) if values else None


def _is_evidence_milestone(payload: dict[str, Any]) -> bool:
    if int(payload.get("candidate_rows_staged") or 0) > 0:
        return True
    if payload.get("cohort_append_performed") is True:
        return True
    if payload.get("safety_violations"):
        return True
    if payload.get("scheduled_scan_session_error"):
        return True
    if int(payload.get("scan_sweep_failure_count") or 0) > 0:
        return True
    high_risk_flags = {
        "auto_track_allowed",
        "broker_order_allowed",
        "broker_order_submitted",
        "cohort_append_performed",
        "evidence_stores_mutated",
        "live_entry_allowed",
        "live_validation_enabled",
        "proof_bars_changed",
        "protected_holdout_consumed",
        "quotes_imported",
        "scanner_policy_changed",
        "sizing_changed",
        "stops_changed",
        "strategy_logic_changed",
    }
    return any(payload.get(key) is True for key in high_risk_flags)


def _python_cache_candidates(
    *, root: Path, policy: dict[str, Any], tracked: set[str], now: datetime
) -> list[dict[str, Any]]:
    names = set(policy.get("python_cache_names") or [])
    candidates: list[dict[str, Any]] = []
    excluded_roots = {".git", ".venv", "node_modules", ".tmp-dead-root", ".tmp-test-dead"}
    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in excluded_roots]
        for name in list(dirs):
            if name not in names:
                continue
            path = current_path / name
            rel = _relative(root, path)
            if not _is_protected(rel, policy, tracked):
                candidates.append(
                    _candidate(
                        root=root,
                        path=path,
                        category="python_cache",
                        action="delete_tree",
                        reason="rebuildable Python tool cache",
                    )
                )
            dirs.remove(name)
        for name in files:
            if not name.endswith((".pyc", ".pyo")):
                continue
            path = current_path / name
            rel = _relative(root, path)
            if not _is_protected(rel, policy, tracked):
                candidates.append(
                    _candidate(
                        root=root,
                        path=path,
                        category="python_cache",
                        action="delete_file",
                        reason="rebuildable Python bytecode",
                    )
                )
    return candidates


def _rebuildable_candidates(
    *, root: Path, policy: dict[str, Any], tracked: set[str], now: datetime
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for rule in policy.get("rebuildable_roots") or []:
        path = _resolved_under(root, root / str(rule["path"]))
        if not path.exists() or _age_hours(path, now=now) < float(rule.get("min_age_hours", 0)):
            continue
        rel = _relative(root, path)
        if _is_protected(rel, policy, tracked):
            continue
        candidates.append(
            _candidate(
                root=root,
                path=path,
                category=str(rule["category"]),
                action="delete_tree" if path.is_dir() else "delete_file",
                reason="rebuildable local dependency or build output",
            )
        )
    return candidates


def _log_candidates(*, root: Path, policy: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for rule in policy.get("log_rules") or []:
        path = _resolved_under(root, root / str(rule["path"]))
        if not path.is_file():
            continue
        if path.stat().st_size <= int(rule["max_bytes"]):
            continue
        if _age_hours(path, now=now) < float(rule.get("min_age_hours", 24)):
            continue
        item = _candidate(
            root=root,
            path=path,
            category="logs",
            action="rotate_log",
            reason=f"stale log exceeds {int(rule['max_bytes'])} bytes",
        )
        item["keep_archives"] = max(int(rule.get("keep_archives", 3)), 1)
        candidates.append(item)
    return candidates


def build_cleanup_plan(
    *,
    root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    categories: Iterable[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    tracked = _tracked_paths(root)
    current = now or _utc_now()
    selected = set(categories or ["python_cache", "generated_snapshots", "logs"])
    candidates: list[dict[str, Any]] = []
    if "python_cache" in selected:
        candidates.extend(_python_cache_candidates(root=root, policy=policy, tracked=tracked, now=current))
    if selected.intersection({"next_build", "dependencies"}):
        candidates.extend(
            item
            for item in _rebuildable_candidates(root=root, policy=policy, tracked=tracked, now=current)
            if item["category"] in selected
        )
    if "generated_snapshots" in selected:
        snapshot_rules = policy.get("snapshot_rules") or []
        referenced_timestamps = _referenced_timestamps(
            root=root,
            tracked=tracked,
            snapshot_rules=snapshot_rules,
        )
        for rule in snapshot_rules:
            candidates.extend(
                _snapshot_candidates(
                    root=root,
                    rule=rule,
                    policy=policy,
                    tracked=tracked,
                    referenced_timestamps=referenced_timestamps,
                    now=current,
                )
            )
    if "logs" in selected:
        candidates.extend(_log_candidates(root=root, policy=policy, now=current))
    candidates.sort(key=lambda item: (-int(item["size_bytes"]), str(item["path"])))
    return {
        "report_id": "project_storage_cleanup_plan",
        "status": "dry_run",
        "generated_at_utc": current.isoformat().replace("+00:00", "Z"),
        "policy_id": policy["policy_id"],
        "categories": sorted(selected),
        "candidate_count": len(candidates),
        "reclaimable_bytes": sum(int(item["size_bytes"]) for item in candidates),
        "candidates": candidates,
    }


def _rotate_log(path: Path, *, keep_archives: int, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    archive = path.with_name(f"{path.name}.{stamp}.gz")
    if archive.exists():
        raise StoragePolicyError(f"log archive already exists: {archive}")
    rotated = path.with_name(f".{path.name}.rotating-{uuid.uuid4().hex}")
    os.replace(path, rotated)
    try:
        path.open("xb").close()
    except FileExistsError:
        pass
    before = _file_identity(rotated)
    temporary = archive.with_suffix(f"{archive.suffix}.tmp")
    with rotated.open("rb") as source, gzip.open(temporary, "wb", compresslevel=6) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    if before != _file_identity(rotated):
        temporary.unlink(missing_ok=True)
        raise StoragePolicyError(f"rotated log changed during compression; preserved at {rotated}")
    os.replace(temporary, archive)
    rotated.unlink()
    archives = sorted(path.parent.glob(f"{path.name}.*.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old in archives[max(keep_archives, 1) :]:
        old.unlink()
    return archive


def _tree_contains_tracked(relative_path: str, tracked: set[str]) -> bool:
    prefix = relative_path.rstrip("/") + "/"
    return any(item == relative_path or item.startswith(prefix) for item in tracked)


def _has_reparse_or_symlink(path: Path) -> bool:
    for candidate in (path, *path.rglob("*")):
        try:
            stat = candidate.lstat()
        except OSError:
            return True
        attributes = int(getattr(stat, "st_file_attributes", 0))
        if candidate.is_symlink() or attributes & 0x400:
            return True
    return False


def _stage_and_delete_file(*, root: Path, path: Path, expected: dict[str, Any]) -> str:
    before = _file_identity(path)
    for key in ("size_bytes", "mtime_ns", "device", "inode"):
        if int(expected[key]) != before[key]:
            raise StoragePolicyError(f"file identity changed before deletion: {path}")
    digest = _sha256_file(path)
    if before != _file_identity(path):
        raise StoragePolicyError(f"file changed while hashing: {path}")
    staging_root = root / "tmp" / "project-storage-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = staging_root / f"{uuid.uuid4().hex}-{path.name}"
    os.replace(path, staged)
    if before != _file_identity(staged) or digest != _sha256_file(staged):
        if not path.exists():
            os.replace(staged, path)
        raise StoragePolicyError(f"file changed during atomic staging; preserved at {staged}")
    staged.unlink()
    return digest


def _stage_and_delete_tree(*, root: Path, path: Path, expected: dict[str, Any]) -> None:
    before = _file_identity(path)
    for key in ("mtime_ns", "device", "inode"):
        if int(expected[key]) != before[key]:
            raise StoragePolicyError(f"directory identity changed before deletion: {path}")
    if _has_reparse_or_symlink(path):
        raise StoragePolicyError(f"directory contains a symlink or reparse point: {path}")
    staging_root = root / "tmp" / "project-storage-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = staging_root / f"{uuid.uuid4().hex}-{path.name}"
    os.replace(path, staged)
    shutil.rmtree(staged)


def apply_cleanup_plan(
    plan: dict[str, Any],
    *,
    root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    acknowledgement: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    if acknowledgement != policy["apply_acknowledgement"]:
        raise StoragePolicyError("cleanup acknowledgement token mismatch")
    categories = list(plan.get("categories") or [])
    fresh_plan = build_cleanup_plan(
        root=root,
        policy_path=policy_path,
        categories=categories,
        now=now,
    )
    fresh_by_key = {
        (str(item["path"]), str(item["category"]), str(item["action"])): item
        for item in fresh_plan["candidates"]
    }
    requested = list(plan.get("candidates") or [])
    safe_candidates: list[dict[str, Any]] = []
    for item in requested:
        key = (str(item.get("path")), str(item.get("category")), str(item.get("action")))
        fresh = fresh_by_key.get(key)
        identity_keys = ("size_bytes", "mtime_ns", "device", "inode")
        if fresh is None or any(int(fresh[key]) != int(item.get(key, -1)) for key in identity_keys):
            raise StoragePolicyError(f"cleanup plan is stale or contains a non-allowlisted action: {key[0]}")
        safe_candidates.append(fresh)
    tracked = _tracked_paths(root)
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in safe_candidates:
        path = _resolved_under(root, root / str(item["path"]))
        rel = _relative(root, path)
        if _is_protected(rel, policy, tracked):
            errors.append({"path": rel, "error": "protected_at_apply_time"})
            continue
        if not path.exists():
            continue
        try:
            if item["action"] == "delete_file":
                item = {**item, "sha256": _stage_and_delete_file(root=root, path=path, expected=item)}
            elif item["action"] == "delete_tree":
                allowed = {
                    str(rule["path"]).strip("/") for rule in policy.get("rebuildable_roots") or []
                }
                allowed.update(set(policy.get("python_cache_names") or []))
                if rel not in allowed and path.name not in allowed:
                    raise StoragePolicyError(f"directory not explicitly allowlisted: {rel}")
                if _tree_contains_tracked(rel, tracked):
                    raise StoragePolicyError(f"directory contains tracked descendants: {rel}")
                _stage_and_delete_tree(root=root, path=path, expected=item)
            elif item["action"] == "rotate_log":
                archive = _rotate_log(
                    path,
                    keep_archives=int(item.get("keep_archives", 3)),
                    now=now or _utc_now(),
                )
                item = {**item, "archive_path": _relative(root, archive)}
            else:
                raise StoragePolicyError(f"unsupported cleanup action: {item['action']}")
            applied.append(item)
        except Exception as exc:
            errors.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})
    return {
        **{key: value for key, value in plan.items() if key != "status"},
        "status": "applied" if not errors else "applied_with_errors",
        "applied_count": len(applied),
        "applied_bytes": sum(int(item["size_bytes"]) for item in applied),
        "applied": applied,
        "errors": errors,
    }


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _sqlite_verification(path: Path, *, table: str, strong_hash: bool = False) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise StoragePolicyError(f"unsafe SQLite table identifier: {table}")
    before = path.stat()
    with closing(sqlite3.connect(_readonly_uri(path), uri=True, timeout=120)) as conn:
        quick_check = [str(row[0]) for row in conn.execute("PRAGMA quick_check").fetchall()]
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        row_count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) if table in tables else None
    after = path.stat()
    result = {
        "path": str(path),
        "quick_check": quick_check,
        "quick_check_ok": quick_check == ["ok"],
        "required_table": table,
        "required_table_present": table in tables,
        "row_count": row_count,
        "size_bytes": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "device": before.st_dev,
        "inode": before.st_ino,
        "stable_during_check": (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
    }
    if strong_hash:
        result["sha256"] = _sha256_file(path)
        result["stable_during_hash"] = (before.st_size, before.st_mtime_ns) == (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
    return result


def _marker_check(path: Path, markers: Iterable[str]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    missing = [marker for marker in markers if marker not in text]
    return {"path": str(path), "exists": path.exists(), "missing_markers": missing, "pass": path.exists() and not missing}


@contextmanager
def _held_import_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"project-storage-retirement {os.getpid()} {uuid.uuid4().hex}"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except FileExistsError as exc:
        raise StoragePolicyError(f"options-history import lock is already held: {path}") from exc
    try:
        yield
    finally:
        try:
            if path.read_text(encoding="utf-8", errors="replace").strip() == token:
                path.unlink()
        except FileNotFoundError:
            pass


def build_pre_vacuum_retirement_report(
    *,
    root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    replacement_backup: Path | None = None,
    verify_databases: bool = False,
    owned_import_lock: bool = False,
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    gate = policy["pre_vacuum_gate"]
    active = _resolved_under(root, root / gate["active_db"])
    old_backup = _resolved_under(root, root / gate["pre_vacuum_backup"])
    import_lock = _resolved_under(root, root / gate["import_lock"])
    checks: dict[str, Any] = {
        "active_exists": active.exists(),
        "pre_vacuum_backup_exists": old_backup.exists(),
        "import_lock_absent": owned_import_lock or not import_lock.exists(),
        "import_lock_owned_by_retirement": owned_import_lock,
        "vacuum_log": _marker_check(root / gate["vacuum_log"], gate["vacuum_required_markers"]),
        "import_log": _marker_check(root / gate["import_log"], gate["import_required_markers"]),
        "pipeline_log": _marker_check(root / gate["pipeline_log"], gate["pipeline_required_markers"]),
        "replacement_backup_supplied": replacement_backup is not None,
    }
    if verify_databases and active.exists():
        checks["active_database"] = _sqlite_verification(active, table=gate["required_table"], strong_hash=True)
    if verify_databases and replacement_backup is not None and replacement_backup.exists():
        replacement_resolved = replacement_backup.resolve()
        if replacement_resolved in {active.resolve(), old_backup.resolve()}:
            raise StoragePolicyError("replacement backup must be distinct from active and pre-vacuum databases")
        checks["replacement_database"] = _sqlite_verification(
            replacement_backup, table=gate["required_table"], strong_hash=True
        )
    active_check = checks.get("active_database") or {}
    replacement_check = checks.get("replacement_database") or {}
    checks["replacement_matches_active"] = bool(
        active_check.get("quick_check_ok")
        and replacement_check.get("quick_check_ok")
        and active_check.get("required_table_present")
        and replacement_check.get("required_table_present")
        and active_check.get("row_count") == replacement_check.get("row_count")
        and active_check.get("stable_during_check")
        and replacement_check.get("stable_during_check")
        and active_check.get("stable_during_hash")
        and replacement_check.get("stable_during_hash")
        and active_check.get("sha256") == replacement_check.get("sha256")
    )
    required = [
        checks["active_exists"],
        checks["pre_vacuum_backup_exists"],
        checks["import_lock_absent"],
        checks["vacuum_log"]["pass"],
        checks["import_log"]["pass"],
        checks["pipeline_log"]["pass"],
        checks["replacement_backup_supplied"],
        checks["replacement_matches_active"],
    ]
    eligible = all(required)
    return {
        "report_id": "pre_vacuum_backup_retirement_gate",
        "status": "eligible" if eligible else "blocked",
        "eligible": eligible,
        "checks": checks,
        "pre_vacuum_backup_path": str(old_backup),
        "pre_vacuum_backup_size_bytes": old_backup.stat().st_size if old_backup.exists() else 0,
        "pre_vacuum_backup_identity": _file_identity(old_backup) if old_backup.exists() else None,
        "replacement_backup_path": str(replacement_backup.resolve()) if replacement_backup is not None else "",
    }


def retire_pre_vacuum_backup(
    report: dict[str, Any], *, root: Path = ROOT, policy_path: Path = DEFAULT_POLICY, acknowledgement: str
) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    if acknowledgement != policy["pre_vacuum_retirement_acknowledgement"]:
        raise StoragePolicyError("pre-vacuum retirement acknowledgement token mismatch")
    replacement = Path(str(report.get("replacement_backup_path") or ""))
    gate = policy["pre_vacuum_gate"]
    import_lock = _resolved_under(root, root / gate["import_lock"])
    with _held_import_lock(import_lock):
        fresh = build_pre_vacuum_retirement_report(
            root=root,
            policy_path=policy_path,
            replacement_backup=replacement,
            verify_databases=True,
            owned_import_lock=True,
        )
        if not fresh.get("eligible"):
            raise StoragePolicyError("pre-vacuum backup retirement gate is blocked at apply time")
        active = _resolved_under(root, root / gate["active_db"])
        active_expected = fresh["checks"]["active_database"]
        replacement_expected = fresh["checks"]["replacement_database"]
        for candidate, expected_identity in ((active, active_expected), (replacement, replacement_expected)):
            current = _file_identity(candidate)
            for key in ("size_bytes", "mtime_ns", "device", "inode"):
                if int(expected_identity[key]) != current[key]:
                    raise StoragePolicyError(f"database identity changed before retirement: {candidate}")
        path = Path(str(fresh["pre_vacuum_backup_path"]))
        expected = (root / gate["pre_vacuum_backup"]).resolve()
        if path.resolve() != expected:
            raise StoragePolicyError("pre-vacuum path does not match protected policy path")
        identity = _file_identity(path)
        if identity != fresh.get("pre_vacuum_backup_identity"):
            raise StoragePolicyError("pre-vacuum backup changed during retirement checks")
        staged = path.with_name(f".{path.name}.retiring-{uuid.uuid4().hex}")
        os.replace(path, staged)
        staged.unlink()
        return {**fresh, "status": "retired", "retired_bytes": identity["size_bytes"]}


def build_storage_audit(*, root: Path = ROOT, policy_path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    rows: list[dict[str, Any]] = []
    for item in root.iterdir():
        try:
            rows.append({"path": item.name, "size_bytes": _path_size(item), "file_count": 1 if item.is_file() else sum(1 for p in item.rglob("*") if p.is_file())})
        except (PermissionError, OSError):
            rows.append({"path": item.name, "size_bytes": 0, "file_count": 0, "status": "unreadable"})
    rows.sort(key=lambda item: int(item["size_bytes"]), reverse=True)
    audit_only = []
    for rel in policy.get("audit_only_paths") or []:
        path = root / rel
        audit_only.append({"path": rel, "exists": path.exists(), "size_bytes": _path_size(path) if path.exists() else 0})
    return {
        "report_id": "project_storage_audit",
        "status": "pass",
        "total_bytes": sum(int(item["size_bytes"]) for item in rows),
        "top_level": rows,
        "audit_only": audit_only,
        "protected_exact_paths": policy.get("protected_exact_paths") or [],
        "rules": {"read_only": True, "deletes_files": False, "follows_symlinks": False},
    }


def _print_result(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"{payload['report_id']}: {payload['status']}")
    if "candidate_count" in payload:
        print(f"candidates={payload['candidate_count']} reclaimable_bytes={payload['reclaimable_bytes']}")
    if "eligible" in payload:
        print(f"eligible={payload['eligible']} backup_bytes={payload['pre_vacuum_backup_size_bytes']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and safely manage options-chatbot local storage.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--json", action="store_true")

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--category", action="append", choices=["python_cache", "generated_snapshots", "logs", "next_build", "dependencies"])
    cleanup_parser.add_argument("--apply", action="store_true")
    cleanup_parser.add_argument("--acknowledge", default="")
    cleanup_parser.add_argument("--json", action="store_true")

    retire_parser = subparsers.add_parser("retire-pre-vacuum")
    retire_parser.add_argument("--replacement-backup", type=Path)
    retire_parser.add_argument("--verify-databases", action="store_true")
    retire_parser.add_argument("--apply", action="store_true")
    retire_parser.add_argument("--acknowledge", default="")
    retire_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "audit":
        result = build_storage_audit(policy_path=args.policy)
    elif args.command == "cleanup":
        result = build_cleanup_plan(policy_path=args.policy, categories=args.category)
        if args.apply:
            result = apply_cleanup_plan(
                result,
                policy_path=args.policy,
                acknowledgement=args.acknowledge,
            )
    else:
        result = build_pre_vacuum_retirement_report(
            policy_path=args.policy,
            replacement_backup=args.replacement_backup,
            verify_databases=args.verify_databases,
        )
        if args.apply:
            result = retire_pre_vacuum_backup(
                result,
                policy_path=args.policy,
                acknowledgement=args.acknowledge,
            )
    _print_result(result, as_json=bool(args.json))
    return 1 if result.get("status") in {"blocked", "applied_with_errors"} else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StoragePolicyError as exc:
        print(f"manage_project_storage: {exc}", file=sys.stderr)
        raise SystemExit(2)
