from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (  # noqa: E402
    build_regular_options_filtered_forward_paper_shadow_tracker as tracker,
)


REPORT_ID = "regular_options_filtered_forward_evidence_bar_evaluation"
DEFAULT_MATCHED_ROWS_LOG = tracker.DEFAULT_MATCHED_ROWS_LOG
DEFAULT_POLICY_CONTRACT = tracker.DEFAULT_POLICY_CONTRACT
DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT = tracker.DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "forward-tracking"
    / "regular-options-filtered-forward-evidence-bar-evaluation"
)
DEFAULT_DOCS_REPORT = (
    ROOT / "docs" / "regular-options-filtered-forward-evidence-bar-evaluation.md"
)


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {
            "path": _rel(path),
            "exists": True,
            "status": "invalid_json",
            "error": str(exc),
        }
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {
        "path": _rel(path),
        "exists": True,
        "status": "loaded",
        "sha256": _file_hash(path),
    }


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {
            "path": _rel(path),
            "exists": False,
            "status": "missing",
            "row_count": 0,
            "bad_row_count": 0,
        }
    rows: list[dict[str, Any]] = []
    bad = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            bad += 1
    return rows, {
        "path": _rel(path),
        "exists": True,
        "status": "loaded" if bad == 0 else "malformed",
        "row_count": len(rows),
        "bad_row_count": bad,
        "sha256": _file_hash(path),
    }


def _policy_hash_checks(
    policy_contract: dict[str, Any],
    policy_meta: dict[str, Any],
    bar_contract: dict[str, Any],
) -> dict[str, Any]:
    expected_conditions = str(policy_contract.get("conditions_sha256") or "")
    computed_conditions = (
        tracker._conditions_sha256(tracker._as_list(policy_contract.get("conditions")))
        if policy_contract.get("conditions")
        else ""
    )
    source_policy = tracker._as_dict(bar_contract.get("source_policy_contract"))
    expected_policy_sha = str(source_policy.get("sha256") or "")
    actual_policy_sha = str(policy_meta.get("sha256") or "")
    return {
        "policy_contract_loaded": policy_meta.get("status") == "loaded",
        "policy_conditions_hash_match": bool(
            expected_conditions and expected_conditions == computed_conditions
        ),
        "bar_source_policy_sha_match": bool(
            expected_policy_sha
            and actual_policy_sha
            and expected_policy_sha == actual_policy_sha
        ),
        "expected_conditions_sha256": expected_conditions,
        "computed_conditions_sha256": computed_conditions,
        "expected_policy_contract_sha256": expected_policy_sha,
        "actual_policy_contract_sha256": actual_policy_sha,
    }


def build_report(
    *,
    matched_rows_log_path: Path = DEFAULT_MATCHED_ROWS_LOG,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    forward_evidence_bar_contract_path: Path = DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    rows, rows_meta = _load_jsonl(matched_rows_log_path)
    policy_contract, policy_meta = _load_json(policy_contract_path)
    bar_contract, bar_meta = _load_json(forward_evidence_bar_contract_path)
    current_rows = tracker._merge_lifecycle_rows(rows)
    progress = tracker._forward_evidence_bar_progress(
        rows, bar_contract=bar_contract, bar_meta=bar_meta
    )
    validated_completed_ids = tracker._validated_completed_candidate_ids(rows)
    hash_checks = _policy_hash_checks(policy_contract, policy_meta, bar_contract)
    duplicate_identities = tracker._matched_log_duplicate_daily_signal_identities(rows)
    matched_log_identity_schema_current = (
        tracker._matched_log_has_current_identity_schema(rows)
    )
    blockers: list[str] = []
    if rows_meta.get("status") != "loaded":
        blockers.append("matched_rows_log_not_loaded")
    if rows and not matched_log_identity_schema_current:
        blockers.append(
            "matched_rows_log_nonempty_before_daily_signal_identity_upgrade"
        )
    if duplicate_identities:
        blockers.append("duplicate_ticker_date_direction_matched_rows")
    if bar_meta.get("status") != "loaded":
        blockers.append("forward_evidence_bar_contract_not_loaded")
    if policy_meta.get("status") != "loaded":
        blockers.append("frozen_policy_contract_not_loaded")
    if not hash_checks["policy_conditions_hash_match"]:
        blockers.append("frozen_policy_conditions_hash_mismatch")
    if not hash_checks["bar_source_policy_sha_match"]:
        blockers.append("bar_source_policy_contract_hash_mismatch")
    if blockers:
        status = "blocked_forward_evidence_bar_evaluation"
    elif not progress.get("evaluation_permitted"):
        status = "evaluation_not_permitted_yet"
    elif progress.get("criteria_met_reporting_only"):
        status = "bar_met_pending_operator_review"
    else:
        status = "bar_not_met"
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "read_only": True,
        "matched_rows_log": rows_meta,
        "policy_contract": policy_meta,
        "forward_evidence_bar_contract": bar_meta,
        "policy_hash_checks": hash_checks,
        "matched_rows_log_identity_schema": tracker.MATCHED_ROW_IDENTITY_SCHEMA,
        "matched_rows_log_identity_schema_current": matched_log_identity_schema_current,
        "duplicate_daily_signal_identity_count": len(duplicate_identities),
        "duplicate_daily_signal_identities": duplicate_identities,
        "current_lifecycle_row_count": len(current_rows),
        "completed_candidate_ids": sorted(validated_completed_ids),
        "forward_evidence_bar": progress,
        "blockers": blockers,
        "approval_authority": False,
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "forward_rows_are_profitability_proof": False,
        "scanner_policy_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "prohibited_actions": [
            "do_not_promote_from_forward_evidence_bar_evaluation",
            "do_not_change_scanner_policy_from_forward_evidence_bar_evaluation",
            "do_not_enable_live_validation_from_forward_evidence_bar_evaluation",
            "do_not_enable_auto_track_from_forward_evidence_bar_evaluation",
            "do_not_submit_broker_orders_from_forward_evidence_bar_evaluation",
            "do_not_import_quotes_from_forward_evidence_bar_evaluation",
            "do_not_mutate_evidence_stores_from_forward_evidence_bar_evaluation",
        ],
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    bar = tracker._as_dict(report.get("forward_evidence_bar"))
    return "\n".join(
        [
            "# Regular Options Filtered Forward Evidence-Bar Evaluation",
            "",
            f"- Status: `{report.get('status')}`.",
            f"- Completed rows: `{bar.get('completed_forward_rows')}` / `{bar.get('required_completed_forward_rows')}`.",
            f"- Ticker-week clusters: `{bar.get('ticker_week_cluster_count')}` / `{bar.get('required_ticker_week_clusters')}`.",
            f"- Calendar months: `{bar.get('calendar_month_count')}` / `{bar.get('required_calendar_months')}`.",
            f"- Fixture rows: `{bar.get('fixture_row_count')}` / max `{bar.get('max_fixture_rows')}`.",
            f"- Evaluation permitted: `{str(bool(bar.get('evaluation_permitted'))).lower()}`.",
            f"- Criteria met reporting-only: `{str(bool(bar.get('criteria_met_reporting_only'))).lower()}`.",
            f"- Percent cluster PF LB 5%: `{tracker._as_dict(bar.get('percent_cluster_bootstrap')).get('pf_lb_5pct')}`.",
            f"- USD cluster PF LB 5%: `{tracker._as_dict(bar.get('usd_cluster_bootstrap')).get('pf_lb_5pct')}`.",
            f"- Total net USD: `{bar.get('total_net_pnl_usd')}`.",
            f"- Approval authority: `{str(bool(report.get('approval_authority'))).lower()}`.",
            "",
            "This evaluator is read-only. Passing the bar means pending operator review only, never automatic promotion, scanner-policy change, live validation, auto-track, broker action, quote import, or evidence-store mutation.",
            "",
        ]
    )


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the filtered forward evidence bar from completed matched-row log entries."
    )
    parser.add_argument(
        "--matched-rows-log", type=Path, default=DEFAULT_MATCHED_ROWS_LOG
    )
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument(
        "--forward-evidence-bar-contract",
        type=Path,
        default=DEFAULT_FORWARD_EVIDENCE_BAR_CONTRACT,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        matched_rows_log_path=args.matched_rows_log,
        policy_contract_path=args.policy_contract,
        forward_evidence_bar_contract_path=args.forward_evidence_bar_contract,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
