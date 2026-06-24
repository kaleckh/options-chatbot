from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_point_in_time_vix_bucket"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "source_rows.jsonl"
DEFAULT_THRESHOLD_POLICY = ROOT / "data" / "contracts" / "regular-options-vix-bucket-policy.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-point-in-time-vix-bucket.md"

REQUIRED_ROW_FIELDS = (
    "bucket_date_et",
    "source_name",
    "source_ref",
    "source_timestamp_utc",
    "known_at_utc",
    "point_in_time_valid",
    "source_provenance_status",
)
LEAKAGE_KEYS = {
    "future_realized_vol",
    "realized_vol",
    "future_returns",
    "future_return",
    "option_outcome",
    "option_return",
    "option_pnl",
    "pnl",
    "net_pnl",
    "net_pnl_usd",
    "event_outcome",
    "actual",
    "forecast",
    "surprise",
    "post_entry_regime",
    "post_event_return",
    "future_iv",
}
READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "promotion_ready": False,
}
FORBIDDEN_ACTIONS = (
    "broker_orders",
    "broker_order_preparation",
    "live_validation",
    "auto_track",
    "production_scanner_changes",
    "strategy_logic_changes",
    "stop_changes",
    "sizing_changes",
    "proof_bar_changes",
    "quote_import",
    "options_history_db_mutation",
    "forward_or_evidence_store_mutation",
    "protected_holdout_consumption",
    "promotion",
    "historical_option_replay",
    "treating_vix_buckets_as_profitability_proof",
)

EASTERN = ZoneInfo("America/New_York")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_json(path: Path, *, required: bool) -> tuple[Any, dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    meta["status"] = "loaded"
    if isinstance(payload, dict):
        meta["generated_at_utc"] = payload.get("generated_at_utc")
        meta["report_id"] = payload.get("report_id") or payload.get("policy_id")
    return payload, meta


def _load_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    meta.setdefault("non_object_lines", []).append(line_number)
        else:
            payload = json.loads(path.read_text(encoding="utf8"))
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
            elif isinstance(payload, dict):
                for key in ("source_rows", "bucket_rows", "vix_rows", "rows"):
                    if isinstance(payload.get(key), list):
                        rows = [row for row in payload[key] if isinstance(row, dict)]
                        break
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return [], meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _requested_dates(feature_store: Any) -> list[str]:
    payload = _as_dict(feature_store)
    dates = [str(value) for value in _as_list(payload.get("shared_quote_dates")) if value]
    return sorted(set(dates))


def _threshold_policy(policy: Any, meta: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    payload = _as_dict(policy)
    if meta.get("status") != "loaded":
        return None, ["missing_vix_bucket_threshold_policy"]
    for field in ("policy_id", "bucket_threshold_source", "low_max", "mid_max", "frozen_at_utc"):
        if payload.get(field) in (None, ""):
            reasons.append(f"missing_{field}")
    try:
        low_max = float(payload.get("low_max"))
        mid_max = float(payload.get("mid_max"))
    except (TypeError, ValueError):
        reasons.append("invalid_threshold_values")
        low_max = 0.0
        mid_max = 0.0
    if low_max <= 0 or mid_max <= 0 or low_max >= mid_max:
        reasons.append("invalid_threshold_order")
    if _parse_dt(payload.get("frozen_at_utc")) is None:
        reasons.append("invalid_frozen_at_utc")
    if reasons:
        return None, reasons
    return {
        "policy_id": str(payload["policy_id"]),
        "bucket_threshold_source": str(payload["bucket_threshold_source"]),
        "low_max": low_max,
        "mid_max": mid_max,
        "frozen_at_utc": str(payload["frozen_at_utc"]),
    }, []


def _find_leakage_keys(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if str(key).lower() in LEAKAGE_KEYS:
                    hits.append(path)
                walk(nested, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(row)
    return hits


def _classify_vix(value: float, policy: dict[str, Any]) -> str:
    if value <= float(policy["low_max"]):
        return "low"
    if value <= float(policy["mid_max"]):
        return "mid"
    return "high"


def _known_before_bucket_date(row: dict[str, Any], known_at: datetime) -> bool:
    source_frequency = str(row.get("source_frequency") or "daily_close").lower()
    candidate_entry = _parse_dt(row.get("candidate_entry_timestamp_utc"))
    if candidate_entry:
        return known_at <= candidate_entry
    if source_frequency == "intraday":
        return True
    try:
        bucket_date = datetime.fromisoformat(str(row["bucket_date_et"])).date()
    except ValueError:
        return False
    return known_at.astimezone(EASTERN).date() < bucket_date


def _validate_row(
    row: dict[str, Any],
    index: int,
    *,
    policy: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reasons: list[str] = []
    missing = [field for field in REQUIRED_ROW_FIELDS if row.get(field) in (None, "")]
    if missing:
        reasons.append("missing_required_fields")
    if row.get("point_in_time_valid") is not True:
        reasons.append("point_in_time_valid_not_true")
    if row.get("source_provenance_status") != "trusted_local_or_contract_declared":
        reasons.append("source_provenance_status_not_trusted_local_or_contract_declared")
    source_ts = _parse_dt(row.get("source_timestamp_utc"))
    known_at = _parse_dt(row.get("known_at_utc"))
    if not source_ts or not known_at:
        reasons.append("missing_or_invalid_source_or_known_at_timestamp")
    elif known_at < source_ts:
        reasons.append("known_at_before_source_timestamp")
    elif not _known_before_bucket_date(row, known_at):
        reasons.append("known_at_after_candidate_join_cutoff")
    leakage = _find_leakage_keys(row)
    if leakage:
        reasons.append("leakage_fields_present")
    if policy is None:
        reasons.append("missing_vix_bucket_threshold_policy")
    vix_value = row.get("vix_value")
    precomputed = str(row.get("precomputed_vix_bucket") or row.get("vix_bucket") or "").lower()
    if vix_value in (None, "") and not precomputed:
        reasons.append("missing_vix_value_or_precomputed_bucket")
    computed_bucket: str | None = None
    numeric_vix: float | None = None
    if vix_value not in (None, ""):
        try:
            numeric_vix = float(vix_value)
        except (TypeError, ValueError):
            reasons.append("invalid_vix_value")
        if numeric_vix is not None and policy is not None:
            computed_bucket = _classify_vix(numeric_vix, policy)
    elif precomputed in {"low", "mid", "high"}:
        computed_bucket = precomputed
    elif precomputed:
        reasons.append("invalid_precomputed_vix_bucket")
    if precomputed and computed_bucket and precomputed != computed_bucket:
        reasons.append("precomputed_vix_bucket_mismatch")
    if reasons:
        return None, {
            "index": index,
            "bucket_date_et": row.get("bucket_date_et"),
            "reasons": reasons,
            "missing_fields": missing,
            "leakage_keys": leakage,
        }
    bucket = computed_bucket or precomputed
    accepted = {
        "bucket_date_et": str(row["bucket_date_et"]),
        "vix_value": numeric_vix,
        "vix_bucket": bucket,
        "low_mid_eligible": bucket in {"low", "mid"},
        "source_name": str(row["source_name"]),
        "source_ref": str(row["source_ref"]),
        "source_timestamp_utc": str(row["source_timestamp_utc"]),
        "known_at_utc": str(row["known_at_utc"]),
        "point_in_time_valid": True,
        "source_provenance_status": "trusted_local_or_contract_declared",
        "source_frequency": str(row.get("source_frequency") or "daily_close"),
        "proof_eligible": False,
    }
    return accepted, None


def _status(source_meta: dict[str, Any], blockers: list[str]) -> str:
    if source_meta.get("status") == "missing" or source_meta.get("row_count") == 0:
        return "blocked_point_in_time_vix_source_missing"
    if blockers:
        return "blocked_point_in_time_vix_bucket_validation"
    return "point_in_time_vix_bucket_ready"


def _feature_store_window(payload: Any) -> dict[str, Any]:
    summary = _as_dict(_as_dict(payload).get("summary"))
    dates = _requested_dates(payload)
    return {
        "first_shared_quote_date_et": summary.get("first_shared_quote_date_et") or (dates[0] if dates else None),
        "latest_shared_quote_date_et": summary.get("latest_shared_quote_date_et") or (dates[-1] if dates else None),
        "shared_quote_date_count": summary.get("shared_quote_date_count") or len(dates),
        "feature_store_status": summary.get("overall_status") or _as_dict(payload).get("status"),
    }


def build_report(
    *,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    threshold_policy_path: Path = DEFAULT_THRESHOLD_POLICY,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source_rows, source_meta = _load_source_rows(source_rows_path)
    threshold_payload, threshold_meta = _load_json(threshold_policy_path, required=False)
    feature_store, feature_store_meta = _load_json(feature_store_path, required=False)
    policy, policy_reasons = _threshold_policy(threshold_payload, threshold_meta)
    requested_dates = _requested_dates(feature_store)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        clean, reject = _validate_row(row, index, policy=policy)
        if clean:
            accepted.append(clean)
        if reject:
            rejected.append(reject)

    covered_dates = sorted({row["bucket_date_et"] for row in accepted})
    missing_dates = sorted(set(requested_dates) - set(covered_dates))
    late_known_at_count = sum(1 for row in rejected if "known_at_after_candidate_join_cutoff" in row["reasons"])
    leakage_reject_count = sum(1 for row in rejected if "leakage_fields_present" in row["reasons"])
    blockers: list[str] = []
    if source_meta.get("status") == "missing" or source_meta.get("row_count") == 0:
        blockers.append("point_in_time_vix_source_missing")
    blockers.extend(policy_reasons)
    if not requested_dates:
        blockers.append("missing_requested_feature_store_dates")
    if missing_dates:
        blockers.append("vix_bucket_date_coverage_incomplete")
    if rejected:
        blockers.append("point_in_time_vix_row_validation_failed")
    blockers = list(dict.fromkeys(blockers))
    coverage_pct = 100.0 if not requested_dates else round(len(set(covered_dates) & set(requested_dates)) / len(requested_dates) * 100.0, 4)
    status = _status(source_meta, blockers)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "point_in_time_vix_low_mid_bucket_available": status == "point_in_time_vix_bucket_ready",
        "source_status": source_meta.get("status"),
        "source_rows_count": source_meta.get("row_count", 0),
        "requested_date_count": len(requested_dates),
        "covered_date_count": len(set(covered_dates) & set(requested_dates)),
        "coverage_pct": coverage_pct,
        "missing_dates": missing_dates,
        "late_known_at_count": late_known_at_count,
        "leakage_reject_count": leakage_reject_count,
        "bucket_threshold_source": policy.get("bucket_threshold_source") if policy else None,
        "threshold_policy": policy,
        "bucket_join_rule": "For daily close VIX, bucket_date_et candidate entries may use only rows whose known_at_utc is before bucket_date_et in ET. Intraday rows require known_at_utc <= candidate_entry_timestamp_utc when that timestamp is supplied.",
        "bucket_rows": accepted,
        "rejected_rows": rejected,
        "blockers": blockers,
        "source_artifacts": {
            "source_rows": source_meta,
            "threshold_policy": threshold_meta,
            "feature_store": feature_store_meta,
        },
        "research_window": _feature_store_window(feature_store),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] not in {
        "blocked_point_in_time_vix_source_missing",
        "blocked_point_in_time_vix_bucket_validation",
        "point_in_time_vix_bucket_ready",
    }:
        raise ValueError(f"unexpected status: {report['status']}")
    if report["point_in_time_vix_low_mid_bucket_available"] is True and report["blockers"]:
        raise ValueError("VIX bucket cannot be available while blockers are present")
    for row in _as_list(report.get("bucket_rows")):
        row_dict = _as_dict(row)
        for field in REQUIRED_ROW_FIELDS:
            if row_dict.get(field) in (None, ""):
                raise ValueError(f"accepted VIX bucket row missing {field}")
        if row_dict.get("proof_eligible") is not False:
            raise ValueError("VIX bucket rows cannot be profitability proof")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Point-in-Time VIX Bucket",
        "",
        "This report is generated from `scripts/build_regular_options_point_in_time_vix_bucket.py`. It is a read-only point-in-time VIX low/mid bucket validator for future regular-options research. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, consume protected holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Point-in-time VIX low/mid bucket available: `{str(report['point_in_time_vix_low_mid_bucket_available']).lower()}`.",
        f"- Source rows: `{report['source_rows_count']}`.",
        f"- Requested dates: `{report['requested_date_count']}`.",
        f"- Covered dates: `{report['covered_date_count']}`.",
        f"- Coverage: `{report['coverage_pct']}`.",
        f"- Late known-at rows: `{report['late_known_at_count']}`.",
        f"- Leakage rejects: `{report['leakage_reject_count']}`.",
        f"- Threshold source: `{report.get('bucket_threshold_source')}`.",
        "",
        "## Join Rule",
        "",
        report["bucket_join_rule"],
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Rejected Rows", ""])
    if report.get("rejected_rows"):
        for row in _as_list(report.get("rejected_rows"))[:20]:
            lines.append(f"- `{_as_dict(row).get('bucket_date_et')}`: `{json.dumps(_as_dict(row).get('reasons'))}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
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
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only point-in-time VIX bucket artifact.")
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--threshold-policy", type=Path, default=DEFAULT_THRESHOLD_POLICY)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        source_rows_path=args.source_rows,
        threshold_policy_path=args.threshold_policy,
        feature_store_path=args.feature_store,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
