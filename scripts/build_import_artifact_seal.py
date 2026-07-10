from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_ROOTS = (
    ROOT / "data" / "options-validation" / "thetadata-nbbo",
    ROOT / "data" / "profitability-lab" / "regular-options-13-symbol-out-of-sample-thetadata-opra-import" / "import-csv",
    ROOT / "data" / "profitability-lab" / "regular-options-59-symbol-source-repair-resume" / "import-csv",
)
ALLOWED_SUFFIXES = {".csv", ".parquet"}


class ImportSealError(RuntimeError):
    pass


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return int(stat.st_size), int(stat.st_mtime_ns), int(stat.st_dev), int(stat.st_ino)


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _normalized_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def _load_batches(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], dict[int, int]]:
    conn.row_factory = sqlite3.Row
    batches = [dict(row) for row in conn.execute("SELECT * FROM import_batches ORDER BY id")]
    batch_counts = {
        int(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT source_batch_id, COUNT(*) FROM option_quote_snapshots GROUP BY source_batch_id"
        )
    }
    return batches, batch_counts


def _batch_reconciliation(batch: dict[str, Any], db_row_count: int) -> dict[str, Any]:
    raw_values = [
        batch.get("total_rows"),
        batch.get("imported_rows"),
        batch.get("duplicate_rows"),
        batch.get("rejected_rows"),
        db_row_count,
    ]
    numeric_valid = all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in raw_values)
    if numeric_valid:
        total, imported, duplicates, rejected, _ = raw_values
    else:
        total = imported = duplicates = rejected = -1
    try:
        warnings = json.loads(str(batch.get("warnings_json")))
        if not isinstance(warnings, list):
            warnings = ["invalid_warnings_json_type"]
    except (json.JSONDecodeError, TypeError):
        warnings = ["invalid_warnings_json"]
    accounted = numeric_valid and imported + duplicates + rejected == total
    eligible = numeric_valid and accounted and rejected == 0 and not warnings and db_row_count == imported
    return {
        "batch_id": int(batch["id"]),
        "source_label": batch.get("source_label"),
        "dataset_kind": batch.get("dataset_kind"),
        "data_trust": batch.get("data_trust"),
        "input_path": batch.get("input_path"),
        "file_hash": batch.get("file_hash"),
        "total_rows": total,
        "imported_rows": imported,
        "duplicate_rows": duplicates,
        "rejected_rows": rejected,
        "database_row_count": db_row_count,
        "warnings": warnings,
        "rows_accounted": accounted,
        "numeric_fields_valid": numeric_valid,
        "eligible": eligible,
    }


def build_import_artifact_seal(
    *,
    db_path: Path = DEFAULT_DB,
    artifact_roots: Iterable[Path] = DEFAULT_ROOTS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if not db_path.is_file():
        raise ImportSealError(f"options history database not found: {db_path}")
    roots = [Path(path) for path in artifact_roots]
    missing_roots = [str(path.resolve()) for path in roots if not path.exists()]
    files = sorted(
        {
            path.resolve()
            for root in roots
            if root.exists()
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in ALLOWED_SUFFIXES
        }
    )
    before = db_path.stat()
    with closing(sqlite3.connect(_readonly_uri(db_path), uri=True, timeout=120)) as conn:
        batches, batch_counts = _load_batches(conn)
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    after = db_path.stat()
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for batch in batches:
        by_hash.setdefault(str(batch.get("file_hash") or ""), []).append(batch)

    artifacts: list[dict[str, Any]] = []
    for path in files:
        before_file = _identity(path)
        digest = _sha256(path)
        after_file = _identity(path)
        stable_file = before_file == after_file
        matching = by_hash.get(digest, [])
        exact_path_matches = [
            batch for batch in matching if _normalized_path(str(batch.get("input_path") or "")) == _normalized_path(path)
        ]
        selected = exact_path_matches or matching
        reconciliations = [
            _batch_reconciliation(batch, batch_counts.get(int(batch["id"]), 0))
            for batch in selected
        ]
        eligible = bool(reconciliations) and all(item["eligible"] for item in reconciliations)
        blockers: list[str] = []
        if not matching:
            blockers.append("sha256_not_found_in_import_batches")
        if matching and not exact_path_matches:
            blockers.append("sha256_match_without_exact_recorded_path")
        if any(not item["rows_accounted"] for item in reconciliations):
            blockers.append("batch_rows_not_accounted")
        if any(item["rejected_rows"] for item in reconciliations):
            blockers.append("batch_has_rejected_rows")
        if any(item["warnings"] for item in reconciliations):
            blockers.append("batch_has_warnings")
        if any(item["database_row_count"] != item["imported_rows"] for item in reconciliations):
            blockers.append("database_batch_row_count_mismatch")
        if any(not item["numeric_fields_valid"] for item in reconciliations):
            blockers.append("invalid_batch_numeric_fields")
        if not stable_file:
            blockers.append("artifact_changed_during_hash")
        artifacts.append(
            {
                "path": str(path),
                "size_bytes": before_file[0],
                "mtime_ns": before_file[1],
                "sha256": digest,
                "stable_during_hash": stable_file,
                "exact_path_match": bool(exact_path_matches),
                "matching_batch_count": len(selected),
                "batches": reconciliations,
                "eligible_for_retirement_after_verified_replacement_backup": eligible and not blockers,
                "blockers": sorted(set(blockers)),
            }
        )

    blocked = [item for item in artifacts if not item["eligible_for_retirement_after_verified_replacement_backup"]]
    database_stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    top_level_blockers: list[str] = []
    if missing_roots:
        top_level_blockers.append("artifact_roots_missing")
    if not artifacts:
        top_level_blockers.append("no_import_artifacts_found")
    if not database_stable:
        top_level_blockers.append("database_changed_during_read")
    generated = generated_at_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "report_id": "options_history_import_artifact_seal",
        "schema_version": 1,
        "status": "sealed" if not blocked and not top_level_blockers else "blocked",
        "generated_at_utc": generated,
        "database": {
            "path": str(db_path.resolve()),
            "size_bytes": before.st_size,
            "mtime_ns": before.st_mtime_ns,
            "page_count": page_count,
            "page_size": page_size,
            "stable_during_read": database_stable,
        },
        "artifact_roots": [str(path.resolve()) for path in roots],
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(int(item["size_bytes"]) for item in artifacts),
        "eligible_count": len(artifacts) - len(blocked),
        "blocked_count": len(blocked),
        "top_level_blockers": top_level_blockers,
        "missing_roots": missing_roots,
        "artifacts": artifacts,
        "retirement_policy": {
            "deletes_files": False,
            "requires_distinct_verified_replacement_database": True,
            "requires_manifest_hash_verification_before_retirement": True,
            "requires_archive_location_when_offloaded": True,
        },
    }
    payload["manifest_sha256"] = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return payload


def verify_seal_manifest(payload: dict[str, Any]) -> bool:
    expected = str(payload.get("manifest_sha256") or "")
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    actual = hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()
    return bool(expected) and expected == actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hash and reconcile raw option import artifacts without deleting them.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--artifact-root", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    seal = build_import_artifact_seal(
        db_path=args.db,
        artifact_roots=args.artifact_root or DEFAULT_ROOTS,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(seal, indent=2, sort_keys=True))
    else:
        print(
            f"{seal['report_id']}: {seal['status']} artifacts={seal['artifact_count']} "
            f"eligible={seal['eligible_count']} blocked={seal['blocked_count']}"
        )
    return 1 if args.strict and seal["status"] != "sealed" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportSealError as exc:
        print(f"build_import_artifact_seal: {exc}", file=sys.stderr)
        raise SystemExit(2)
