import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import (
    DAILY_SNAPSHOT_KIND,
    INTRADAY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    import_daily_option_parquet,
    import_historical_option_snapshots,
)


def _download_to_temp(url: str) -> tuple[str, tempfile.TemporaryDirectory]:
    tmpdir = tempfile.TemporaryDirectory()
    filename = url.rstrip("/").split("/")[-1] or "downloaded.dat"
    target = Path(tmpdir.name) / filename
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)
    return str(target), tmpdir


def _resolve_input_path(value: str) -> tuple[str, tempfile.TemporaryDirectory | None]:
    if str(value).startswith(("http://", "https://")):
        path, tmpdir = _download_to_temp(str(value))
        return path, tmpdir
    return str(Path(value)), None


def _infer_format(input_path: str) -> str:
    lowered = input_path.lower()
    if lowered.endswith(".csv"):
        return "csv"
    if lowered.endswith(".parquet"):
        return "philippdubach_daily"
    return "csv"


def _parse_date_optional(value: Any) -> date | None:
    raw = str(value or "").strip()
    return date.fromisoformat(raw) if raw else None


def _load_manifest(path: str | Path) -> list[dict[str, Any]]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf8"))
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("imports")
    else:
        entries = None
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest must define a non-empty 'imports' list or be a non-empty list itself.")

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry {index} must be an object.")
        input_value = str(entry.get("input") or "").strip()
        source_value = str(entry.get("source") or "").strip()
        if not input_value:
            raise ValueError(f"Manifest entry {index} is missing 'input'.")
        if not source_value:
            raise ValueError(f"Manifest entry {index} is missing 'source'.")
        normalized.append(
            {
                "input": input_value,
                "source": source_value,
                "format": str(entry.get("format") or "").strip() or None,
                "underlying": str(entry.get("underlying") or "").strip() or None,
                "underlying_input": str(entry.get("underlying_input") or "").strip() or None,
                "date_from": str(entry.get("date_from") or "").strip() or None,
                "date_to": str(entry.get("date_to") or "").strip() or None,
            }
        )
    return normalized


def _run_single_import(
    entry: dict[str, Any],
    *,
    default_format: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    input_path, input_tmp = _resolve_input_path(str(entry["input"]))
    underlying_path = None
    underlying_tmp = None
    try:
        dataset_format = str(entry.get("format") or default_format or _infer_format(input_path))
        if entry.get("underlying_input"):
            underlying_path, underlying_tmp = _resolve_input_path(str(entry["underlying_input"]))
        date_from = _parse_date_optional(entry.get("date_from"))
        date_to = _parse_date_optional(entry.get("date_to"))

        if dataset_format == "philippdubach_daily":
            result = import_daily_option_parquet(
                input_path,
                str(entry["source"]),
                underlying=entry.get("underlying"),
                underlying_input=underlying_path,
                date_from=date_from,
                date_to=date_to,
                db_path=db_path,
            )
        else:
            result = import_historical_option_snapshots(
                input_path,
                str(entry["source"]),
                db_path=db_path,
            )
    finally:
        if input_tmp is not None:
            input_tmp.cleanup()
        if underlying_tmp is not None:
            underlying_tmp.cleanup()

    return {
        "input": str(entry["input"]),
        "source": str(entry["source"]),
        "format": dataset_format,
        "underlying": entry.get("underlying"),
        "underlying_input": entry.get("underlying_input"),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "result": result,
    }


def _build_store_summary(db_path: str | None = None) -> dict[str, Any]:
    store = HistoricalOptionsStore(db_path)
    summaries: dict[str, Any] = {}
    for snapshot_kind in (DAILY_SNAPSHOT_KIND, INTRADAY_SNAPSHOT_KIND):
        summaries[snapshot_kind] = store.snapshot_summary(snapshot_kind, trusted_only=True)
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import historical option data into the local validation store."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", help="Path or URL to the input file.")
    source_group.add_argument("--manifest", help="Path to a JSON manifest describing one or more imports.")
    parser.add_argument("--source", help="Source label recorded on the import batch.")
    parser.add_argument(
        "--format",
        choices=["csv", "philippdubach_daily"],
        help="Dataset format. Defaults from the file extension: .csv -> csv, .parquet -> philippdubach_daily.",
    )
    parser.add_argument(
        "--underlying-input",
        help="Optional local path or URL to the matching underlying parquet for daily imports.",
    )
    parser.add_argument(
        "--underlying",
        help="Optional ticker override for daily imports when the parquet symbol column needs a hint.",
    )
    parser.add_argument("--date-from", help="Optional inclusive start date for daily parquet imports (YYYY-MM-DD).")
    parser.add_argument("--date-to", help="Optional inclusive end date for daily parquet imports (YYYY-MM-DD).")
    parser.add_argument("--db-path", help="Optional SQLite path override for the historical options store.")
    parser.add_argument("--json", action="store_true", help="Print the full import summary JSON.")
    args = parser.parse_args()

    if args.manifest:
        entries = _load_manifest(args.manifest)
        results = [
            _run_single_import(entry, default_format=args.format, db_path=args.db_path)
            for entry in entries
        ]
        payload = {
            "mode": "manifest",
            "db_path": str(HistoricalOptionsStore(args.db_path).db_path),
            "entries": results,
            "total_imported_rows": sum(
                int((item.get("result") or {}).get("imported_rows", 0) or 0)
                for item in results
            ),
            "total_duplicate_rows": sum(
                int((item.get("result") or {}).get("duplicate_rows", 0) or 0)
                for item in results
            ),
            "total_rejected_rows": sum(
                int((item.get("result") or {}).get("rejected_rows", 0) or 0)
                for item in results
            ),
            "trusted_snapshot_summaries": _build_store_summary(args.db_path),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        compact = {
            "mode": payload["mode"],
            "db_path": payload["db_path"],
            "entries": len(results),
            "total_imported_rows": payload["total_imported_rows"],
            "total_duplicate_rows": payload["total_duplicate_rows"],
            "total_rejected_rows": payload["total_rejected_rows"],
            "trusted_snapshot_summaries": payload["trusted_snapshot_summaries"],
        }
        print(json.dumps(compact, indent=2))
        return 0

    if not args.source:
        parser.error("--source is required when using --input.")

    result = _run_single_import(
        {
            "input": args.input,
            "source": args.source,
            "format": args.format,
            "underlying": args.underlying,
            "underlying_input": args.underlying_input,
            "date_from": args.date_from,
            "date_to": args.date_to,
        },
        db_path=args.db_path,
    )["result"]

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    summary = {
        "db_path": result["db_path"],
        "batch_id": result["batch_id"],
        "source_label": result["source_label"],
        "dataset_kind": result.get("dataset_kind"),
        "snapshot_kind": result.get("snapshot_kind"),
        "imported_rows": result["imported_rows"],
        "duplicate_rows": result["duplicate_rows"],
        "rejected_rows": result["rejected_rows"],
        "warnings": result["warnings"][:5],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
