from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_underlying_daily_source_repair_packet as repair_packet


REPORT_ID = "regular_options_underlying_daily_source_acquisition_packet"
DEFAULT_STAGING_DIR = ROOT / "data" / "import-staging" / "underlying_daily"
DEFAULT_EXPECTED_SOURCE_FILE = DEFAULT_STAGING_DIR / "point_in_time_underlying_daily_ohlcv_adjusted_v1.csv"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-underlying-daily-source-acquisition"
DEFAULT_DOC = ROOT / "docs" / "regular-options-underlying-daily-source-acquisition.md"

APPROVAL_TOKEN = repair_packet.APPROVAL_TOKEN
SOURCE_FAMILY = repair_packet.SOURCE_FAMILY

SAFETY_FLAGS = {
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "source_rows_written": False,
    "source_import_command_executed": False,
}

LOCAL_SHORTCUT_MARKERS = (
    "market_data.db",
    "daily_history",
    "local_market_data_db",
    "historical_prior_bar_reconstruction",
    "bar_date_inferred_known_at",
    "known_at_inferred_from_bar_date",
)
LOCAL_SHORTCUT_FIELDS = (
    "vendor",
    "source",
    "source_name",
    "source_ref",
    "source_url_or_file_name",
    "provenance",
    "provenance_id",
    "source_provenance_status",
    "source_quality",
    "known_at_policy",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _feature_dates(path: Path, *, start: date, end: date, as_of: date) -> list[str]:
    payload = _load_json(path)
    dates: list[str] = []
    for value in payload.get("shared_quote_dates", []):
        try:
            parsed = _parse_date(value)
        except ValueError:
            continue
        if start <= parsed <= end and parsed <= as_of:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _parse_universe(value: str | Sequence[str]) -> tuple[str, ...]:
    raw = str(value).replace(";", ",").split(",") if isinstance(value, str) else list(value)
    return tuple(str(item).strip().upper() for item in raw if str(item).strip())


def _candidate_paths(staging_dir: Path, source_file: Path | None) -> list[Path]:
    if source_file is not None:
        return [source_file]
    if not staging_dir.exists():
        return []
    return sorted(path for path in staging_dir.glob("*.csv") if path.is_file())


def _local_shortcut_rejects(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rejects: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        values = " ".join(str(row.get(field) or "").lower() for field in LOCAL_SHORTCUT_FIELDS)
        markers = sorted(marker for marker in LOCAL_SHORTCUT_MARKERS if marker in values)
        if markers:
            rejects.append(
                {
                    "index": index,
                    "symbol": row.get("symbol"),
                    "bar_date": row.get("bar_date"),
                    "markers": markers,
                }
            )
    return rejects


def _future_import_command(source_file: Path) -> str:
    return (
        "npm run options:source-import:underlying-daily-history -- "
        f"--source-file {_rel(source_file)} "
        f"--approval-token {APPROVAL_TOKEN} --no-replay --json"
    )


def _inspect_source_file(
    path: Path,
    *,
    target_universe: Sequence[str],
    target_start_date: str,
    target_end_date: str,
    requested_dates: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": _rel(path),
        "exists": path.exists(),
        "ready_for_import_approval": False,
        "parse_status": "not_attempted",
        "row_count": 0,
        "blockers": [],
    }
    if not path.exists():
        result.update({"parse_status": "missing", "blockers": ["source_csv_missing"]})
        return result
    try:
        rows = repair_packet.parse_future_source_csv(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        result.update(
            {
                "parse_status": "invalid",
                "parse_error": str(exc),
                "blockers": ["source_csv_parser_rejected"],
            }
        )
        return result

    validation = repair_packet.validate_future_source_rows(
        rows,
        target_universe=target_universe,
        target_start_date=target_start_date,
        target_end_date=target_end_date,
        requested_dates=requested_dates,
    )
    shortcut_rejects = _local_shortcut_rejects(rows)
    blockers: list[str] = []
    if validation.get("reject_count"):
        blockers.append("source_csv_validation_rejected_rows")
    if validation.get("coverage_ready") is not True:
        blockers.append("source_csv_coverage_not_ready")
    if shortcut_rejects:
        blockers.append("local_market_data_db_or_reconstructed_source_not_allowed")

    result.update(
        {
            "parse_status": "loaded",
            "row_count": len(rows),
            "validation": validation,
            "local_shortcut_reject_count": len(shortcut_rejects),
            "local_shortcut_rejects": shortcut_rejects[:20],
            "blockers": blockers,
            "ready_for_import_approval": not blockers,
        }
    )
    return result


def build_report(
    *,
    staging_dir: Path = DEFAULT_STAGING_DIR,
    source_file: Path | None = None,
    feature_store: Path = DEFAULT_FEATURE_STORE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOC,
    target_universe: Sequence[str] = repair_packet.TARGET_UNIVERSE,
    target_start_date: str = repair_packet.TARGET_START_DATE,
    target_end_date: str = repair_packet.TARGET_END_DATE,
    as_of_date: str = repair_packet.AS_OF_DATE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    universe = tuple(target_universe)
    start = _parse_date(target_start_date)
    end = _parse_date(target_end_date)
    as_of = _parse_date(as_of_date)
    requested_dates = _feature_dates(feature_store, start=start, end=end, as_of=as_of)
    paths = _candidate_paths(staging_dir, source_file)
    path_by_display = {_rel(path): path for path in paths}
    candidates = [
        _inspect_source_file(
            path,
            target_universe=universe,
            target_start_date=target_start_date,
            target_end_date=target_end_date,
            requested_dates=requested_dates,
        )
        for path in paths
    ]
    ready_candidates = [item for item in candidates if item.get("ready_for_import_approval") is True]
    preferred_ready = next(
        (item for item in ready_candidates if item.get("path") == _rel(DEFAULT_EXPECTED_SOURCE_FILE)),
        ready_candidates[0] if ready_candidates else None,
    )
    blocker_counts = Counter(blocker for item in candidates for blocker in item.get("blockers", []))
    if not candidates:
        status = "blocked_underlying_daily_source_acquisition_missing"
        blockers = ["trusted_source_csv_missing"]
    elif preferred_ready:
        status = "ready_for_underlying_daily_source_import_approval"
        blockers = []
    else:
        status = "blocked_underlying_daily_source_acquisition_invalid"
        blockers = sorted(blocker_counts) or ["trusted_source_csv_invalid"]

    import_source = path_by_display.get(preferred_ready["path"], DEFAULT_EXPECTED_SOURCE_FILE) if preferred_ready else DEFAULT_EXPECTED_SOURCE_FILE
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "status": status,
        **SAFETY_FLAGS,
        "source_family": SOURCE_FAMILY,
        "staging_dir": _rel(staging_dir),
        "expected_source_file": _rel(DEFAULT_EXPECTED_SOURCE_FILE),
        "specific_source_file": _rel(source_file) if source_file else None,
        "feature_store": _rel(feature_store),
        "target_universe": list(universe),
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "requested_date_count": len(requested_dates),
        "candidate_source_files": candidates,
        "candidate_file_count": len(candidates),
        "ready_candidate_count": len(ready_candidates),
        "selected_ready_source_file": preferred_ready.get("path") if preferred_ready else None,
        "blockers": blockers,
        "candidate_blocker_counts": dict(sorted(blocker_counts.items())),
        "required_approval_token": APPROVAL_TOKEN,
        "future_import_command": _future_import_command(import_source),
        "future_import_command_currently_implemented": True,
        "future_import_command_executed": False,
        "next_action": (
            "stage trusted full-window point-in-time adjusted OHLCV CSV under data/import-staging/underlying_daily"
            if status == "blocked_underlying_daily_source_acquisition_missing"
            else (
                "repair or replace staged CSV until parser, local-provenance, and point-in-time coverage checks pass"
                if status == "blocked_underlying_daily_source_acquisition_invalid"
                else "operator may run the exact tokened source import command after approving source materialization"
            )
        ),
    }
    report["artifacts"] = {"json": _rel(output_dir / "latest.json"), "markdown": _rel(docs_report)}
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Underlying Daily Source Acquisition",
        "",
        "Read-only intake preflight for trusted point-in-time 13-symbol underlying daily OHLCV/adjusted-close CSVs.",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Candidate files: `{report.get('candidate_file_count')}`",
        f"- Ready candidates: `{report.get('ready_candidate_count')}`",
        f"- Requested feature dates: `{report.get('requested_date_count')}`",
        f"- Source rows written: `{str(report.get('source_rows_written')).lower()}`",
        f"- Import command executed: `{str(report.get('source_import_command_executed')).lower()}`",
        f"- Blockers: `{json.dumps(report.get('blockers'), sort_keys=True)}`",
        "",
        "## Future Import Command",
        "",
        "Run only after source materialization approval:",
        "",
        "```bash",
        str(report.get("future_import_command") or ""),
        "```",
        "",
        "## Candidate Files",
        "",
    ]
    for item in report.get("candidate_source_files", []):
        validation = item.get("validation") if isinstance(item.get("validation"), dict) else {}
        lines.append(
            "- "
            f"`{item.get('path')}`: ready `{str(item.get('ready_for_import_approval')).lower()}`, "
            f"rows `{item.get('row_count')}`, "
            f"coverage `{validation.get('coverage_ready')}`, "
            f"blockers `{json.dumps(item.get('blockers'), sort_keys=True)}`"
        )
    if not report.get("candidate_source_files"):
        lines.append("- No staged CSV files were found.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOC) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(report), encoding="utf8")
    docs_report.write_text(render_markdown(report), encoding="utf8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only underlying daily source acquisition preflight.")
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR)
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--target-universe", default=",".join(repair_packet.TARGET_UNIVERSE))
    parser.add_argument("--target-start-date", default=repair_packet.TARGET_START_DATE)
    parser.add_argument("--target-end-date", default=repair_packet.TARGET_END_DATE)
    parser.add_argument("--as-of-date", default=repair_packet.AS_OF_DATE)
    parser.add_argument("--generated-at-utc")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        staging_dir=args.staging_dir,
        source_file=args.source_file,
        feature_store=args.feature_store,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        target_universe=_parse_universe(args.target_universe),
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        generated_at_utc=args.generated_at_utc,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report["status"])
    return 0 if report["status"] == "ready_for_underlying_daily_source_import_approval" else 1


if __name__ == "__main__":
    sys.exit(main())
