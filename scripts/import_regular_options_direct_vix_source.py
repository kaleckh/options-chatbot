from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_regular_options_point_in_time_vix_bucket as vix_bucket


REPORT_ID = "regular_options_direct_vix_source_import"
APPROVAL_TOKEN = "APPROVE_DIRECT_VIX_SOURCE_IMPORT"
SOURCE_FAMILY = "direct_vix_daily_close"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "source_rows.jsonl"
DEFAULT_THRESHOLD_POLICY = ROOT / "data" / "contracts" / "regular-options-vix-bucket-policy.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-direct-vix-source-import"
DEFAULT_DOC = ROOT / "docs" / "regular-options-direct-vix-source-import.md"

READ_ONLY_FLAGS = {
    "accepted_profitability": False,
    "historical_replay_performed": False,
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
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_date(value: Any) -> date:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid date: {value!r}")


def _parse_float(value: Any, field: str) -> float:
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if number < 0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {}


def _feature_dates(path: Path, *, start: date, end: date, as_of: date) -> list[str]:
    payload = _load_json(path)
    dates: list[str] = []
    for value in payload.get("shared_quote_dates", []):
        parsed = _parse_date(value)
        if start <= parsed <= end and parsed <= as_of:
            dates.append(parsed.isoformat())
    return sorted(set(dates))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def _csv_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(raw.splitlines())
    headers = {str(name).strip().lower(): name for name in (reader.fieldnames or [])}
    missing = [name for name in ("date", "open", "high", "low", "close") if name not in headers]
    if missing:
        raise ValueError(f"missing required VIX CSV fields: {', '.join(missing)}")
    source_hash = _file_sha256(path)
    rows: list[dict[str, Any]] = []
    for line_number, raw_row in enumerate(reader, start=2):
        source_date = _parse_date(raw_row[headers["date"]])
        close = _parse_float(raw_row[headers["close"]], "close")
        parsed = {
            "source_date": source_date.isoformat(),
            "vix_open": _parse_float(raw_row[headers["open"]], "open"),
            "vix_high": _parse_float(raw_row[headers["high"]], "high"),
            "vix_low": _parse_float(raw_row[headers["low"]], "low"),
            "vix_close": close,
            "line_number": line_number,
            "source_file_sha256": source_hash,
        }
        parsed["source_row_sha256"] = _row_hash(parsed)
        rows.append(parsed)
    rows.sort(key=lambda item: item["source_date"])
    return rows


def _latest_prior(rows: list[dict[str, Any]], bucket_date: str) -> dict[str, Any] | None:
    prior = [row for row in rows if str(row["source_date"]) < bucket_date]
    return prior[-1] if prior else None


def _build_source_rows(
    *,
    source_file: Path,
    lookback_start_date: str,
    target_start_date: str,
    target_end_date: str,
    as_of_date: str,
    feature_store_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    start = min(_parse_date(lookback_start_date), _parse_date(target_start_date))
    end = max(_parse_date(target_end_date), _parse_date(as_of_date))
    as_of = _parse_date(as_of_date)
    source_rows = _csv_rows(source_file)
    requested_dates = _feature_dates(feature_store_path, start=start, end=end, as_of=as_of)
    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for bucket_date in requested_dates:
        prior = _latest_prior(source_rows, bucket_date)
        if prior is None:
            rejected.append({"bucket_date_et": bucket_date, "reason": "missing_prior_vix_close"})
            continue
        source_date = str(prior["source_date"])
        materialized.append(
            {
                "bucket_date_et": bucket_date,
                "vix_value": prior["vix_close"],
                "source_name": "cboe_vix_daily_history_csv",
                "source_ref": f"{_rel(source_file)}:{source_date}",
                "source_timestamp_utc": f"{source_date}T21:15:00Z",
                "known_at_utc": f"{source_date}T21:16:00Z",
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "daily_close",
                "source_family": SOURCE_FAMILY,
                "source_date_et": source_date,
                "source_file_sha256": prior["source_file_sha256"],
                "source_row_sha256": prior["source_row_sha256"],
                "proof_eligible": False,
            }
        )
    return materialized, rejected


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _write_threshold_policy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    policy = {
        "policy_id": "vix_prior_close_fixed_buckets_v1",
        "bucket_threshold_source": "direct_vix_daily_close_import_policy_v1",
        "low_max": 15.0,
        "mid_max": 25.0,
        "frozen_at_utc": "2026-06-04T00:00:00Z",
        "notes": "Point-in-time prior daily VIX close bucket policy. Historical source rows are not profitability proof.",
    }
    path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf8")


def build_report(
    *,
    source_file: Path,
    lookback_start_date: str = "2023-05-22",
    target_start_date: str = "2024-06-01",
    target_end_date: str = "2026-05-31",
    as_of_date: str = "2026-06-04",
    source_family: str = SOURCE_FAMILY,
    approval_token: str = "",
    no_replay: bool = True,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    threshold_policy_path: Path = DEFAULT_THRESHOLD_POLICY,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if approval_token != APPROVAL_TOKEN:
        blockers.append("missing_or_invalid_approval_token")
    if source_family != SOURCE_FAMILY:
        blockers.append("unsupported_source_family")
    if not no_replay:
        blockers.append("no_replay_flag_required")
    if not source_file.exists():
        blockers.append("source_file_missing")

    materialized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    downstream: dict[str, Any] | None = None
    if not blockers:
        materialized, rejected = _build_source_rows(
            source_file=source_file,
            lookback_start_date=lookback_start_date,
            target_start_date=target_start_date,
            target_end_date=target_end_date,
            as_of_date=as_of_date,
            feature_store_path=feature_store_path,
        )
        if rejected:
            blockers.append("vix_source_row_materialization_rejected_dates")
        if not materialized:
            blockers.append("no_vix_source_rows_materialized")
        if not blockers:
            _write_jsonl(source_rows_path, materialized)
            _write_threshold_policy(threshold_policy_path)
            downstream = vix_bucket.build_report(
                source_rows_path=source_rows_path,
                threshold_policy_path=threshold_policy_path,
                feature_store_path=feature_store_path,
                generated_at_utc=generated_at_utc,
            )
            if downstream.get("status") != "point_in_time_vix_bucket_ready":
                blockers.append("downstream_vix_bucket_validation_failed")

    status = "direct_vix_source_import_materialized" if not blockers else "blocked_direct_vix_source_import"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "source_file": _rel(source_file),
        "source_family": source_family,
        "approval_token_valid": approval_token == APPROVAL_TOKEN,
        "no_replay": no_replay,
        "lookback_start_date": lookback_start_date,
        "target_start_date": target_start_date,
        "target_end_date": target_end_date,
        "as_of_date": as_of_date,
        "source_rows_path": _rel(source_rows_path),
        "threshold_policy_path": _rel(threshold_policy_path),
        "source_rows_written": status == "direct_vix_source_import_materialized",
        "source_row_count": len(materialized),
        "rejected_rows": rejected[:50],
        "blockers": blockers,
        "downstream_vix_bucket_status": downstream.get("status") if downstream else None,
        "downstream_vix_coverage_pct": downstream.get("coverage_pct") if downstream else None,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Direct VIX Source Import",
        "",
        f"- Status: `{report['status']}`.",
        f"- Source rows written: `{str(report['source_rows_written']).lower()}`.",
        f"- Source rows: `{report['source_row_count']}`.",
        f"- Downstream VIX bucket status: `{report.get('downstream_vix_bucket_status')}`.",
        f"- Downstream coverage: `{report.get('downstream_vix_coverage_pct')}`.",
        "",
        "This import writes generated VIX source rows and the frozen VIX bucket policy only. It does not run replay, import option quotes, mutate evidence stores, create trades, enable live validation, enable auto-track, submit broker orders, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote any lane.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.get("blockers", [])) if report.get("blockers") else lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    markdown = render_markdown(payload)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize point-in-time VIX source rows from an official daily VIX CSV.")
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--lookback-start-date", default="2023-05-22")
    parser.add_argument("--target-start-date", default="2024-06-01")
    parser.add_argument("--target-end-date", default="2026-05-31")
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--source-family", default=SOURCE_FAMILY)
    parser.add_argument("--approval-token", default="")
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--threshold-policy", type=Path, default=DEFAULT_THRESHOLD_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(
        source_file=args.source_file,
        lookback_start_date=args.lookback_start_date,
        target_start_date=args.target_start_date,
        target_end_date=args.target_end_date,
        as_of_date=args.as_of_date,
        source_family=args.source_family,
        approval_token=args.approval_token,
        no_replay=args.no_replay,
        feature_store_path=args.feature_store,
        source_rows_path=args.source_rows,
        threshold_policy_path=args.threshold_policy,
    )
    if not args.no_write_report:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
