from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import build_phase2_regular_options_forward_paper_shadow_candidate_rows as stager
from scripts import build_volatility_expansion_forward_paper_shadow_report as report_builder


REPORT_ID = "regular_options_strict_forward_30_candidate_review_packet"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-candidate-review-packet.md"
DEFAULT_CAPTURE_LATEST = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_capture_latest.json"
DEFAULT_COLLECTOR_LATEST = ROOT / "data" / "forward-tracking" / "regular_options_strict_forward_30_market_window_collector_latest.json"
DEFAULT_SCHEDULER_HEALTH_LATEST = ROOT / "data" / "forward-tracking" / "regular_options_strict_forward_30_scheduler_health_latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _parse_utc_iso(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_source_status": "missing", "_source_path": _rel(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {"_source_status": "malformed", "_source_path": _rel(path), "_error": f"JSONDecodeError:{exc.lineno}:{exc.colno}"}
    if not isinstance(payload, dict):
        return {"_source_status": "invalid", "_source_path": _rel(path), "_error": "json_root_not_object"}
    payload["_source_status"] = "loaded"
    payload["_source_path"] = _rel(path)
    return payload


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safety_violations(*payloads: dict[str, Any]) -> list[str]:
    keys = {
        "live_entry_allowed",
        "auto_track_allowed",
        "broker_order_allowed",
        "promotion_ready",
        "quotes_imported",
        "imported_quotes",
        "proof_bars_changed",
        "changed_proof_bars",
        "historical_rows_are_forward_proof",
    }
    violations: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        for key in sorted(keys):
            if payload.get(key) is True:
                violations.append(f"payload_{index}:{key}")
    return violations


def _guarded_append_observed(*payloads: dict[str, Any]) -> bool:
    for payload in payloads:
        if payload.get("cohort_append_performed") is True:
            return True
        append_report = _as_dict(payload.get("append_report"))
        if append_report.get("cohort_append_performed") is True:
            return True
    return False


def _candidate_validation(candidate_path: Path, generated_at_utc: str) -> dict[str, Any]:
    if not candidate_path.exists():
        return {
            "candidate_jsonl_exists": False,
            "append_allowed": False,
            "candidate_rows": 0,
            "append_ready_rows": 0,
            "append_rejected_rows": 0,
            "append_reject_counts": {},
            "validation_report_status": None,
        }
    report = report_builder.build_report(
        candidate_rows_path=candidate_path,
        cohort_log_path=report_builder.DEFAULT_PHASE2_COHORT_LOG,
        schema_path=report_builder.DEFAULT_PHASE2_SCHEMA,
        allowed_lane_ids=report_builder.PHASE2_FROZEN_LANE_IDS,
        generated_at_utc=generated_at_utc,
    )
    validation = _as_dict(report.get("candidate_append_validation"))
    return {
        "candidate_jsonl_exists": True,
        "candidate_rows_path": _rel(candidate_path),
        "candidate_batch_sha256": _sha256_file(candidate_path),
        "append_allowed": bool(validation.get("append_allowed")),
        "candidate_rows": int(validation.get("candidate_rows") or validation.get("append_ready_rows") or 0),
        "append_ready_rows": int(validation.get("append_ready_rows") or 0),
        "append_rejected_rows": int(validation.get("append_rejected_rows") or 0),
        "append_reject_counts": validation.get("append_reject_counts") if isinstance(validation.get("append_reject_counts"), dict) else {},
        "validation_report_status": report.get("overall_status"),
        "candidate_append_validation": validation,
    }


def _scheduler_freshness(scheduler: dict[str, Any], collector: dict[str, Any]) -> dict[str, Any]:
    scheduler_generated_at = _norm(scheduler.get("generated_at_utc"))
    collector_generated_at = _norm(collector.get("generated_at_utc"))
    scheduler_ts = _parse_utc_iso(scheduler_generated_at)
    collector_ts = _parse_utc_iso(collector_generated_at)
    if scheduler.get("_source_status") != "loaded":
        return {
            "fresh": False,
            "status": "scheduler_health_source_not_loaded",
            "scheduler_generated_at_utc": scheduler_generated_at or None,
            "collector_generated_at_utc": collector_generated_at or None,
            "blockers": ["scheduler_health_source_not_loaded"],
        }
    if scheduler_ts is None:
        return {
            "fresh": False,
            "status": "scheduler_health_generated_at_missing_or_malformed",
            "scheduler_generated_at_utc": scheduler_generated_at or None,
            "collector_generated_at_utc": collector_generated_at or None,
            "blockers": ["scheduler_health_generated_at_missing_or_malformed"],
        }
    if collector_generated_at and collector_ts is None:
        return {
            "fresh": False,
            "status": "collector_generated_at_malformed",
            "scheduler_generated_at_utc": scheduler_generated_at,
            "collector_generated_at_utc": collector_generated_at,
            "blockers": ["collector_generated_at_malformed"],
        }
    if collector_ts is not None and scheduler_ts < collector_ts:
        return {
            "fresh": False,
            "status": "scheduler_health_older_than_collector",
            "scheduler_generated_at_utc": scheduler_generated_at,
            "collector_generated_at_utc": collector_generated_at,
            "blockers": ["scheduler_health_older_than_collector"],
        }
    return {
        "fresh": True,
        "status": "scheduler_health_fresh_for_candidate_review",
        "scheduler_generated_at_utc": scheduler_generated_at,
        "collector_generated_at_utc": collector_generated_at or None,
        "blockers": [],
    }


def _candidate_batch_provenance(candidate_path: Path, validation: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    if not validation.get("candidate_jsonl_exists"):
        return {
            "valid": True,
            "status": "candidate_batch_not_present",
            "blockers": [],
            "candidate_rows_path": _rel(candidate_path),
            "candidate_batch_sha256": None,
            "capture_candidate_output_path": _norm(capture.get("candidate_output_path")) or None,
            "capture_candidate_batch_sha256": _norm(capture.get("candidate_batch_sha256")) or None,
        }
    blockers: list[str] = []
    actual_path = _rel(candidate_path)
    actual_sha = _norm(validation.get("candidate_batch_sha256"))
    capture_path = _norm(capture.get("candidate_output_path"))
    capture_sha = _norm(capture.get("candidate_batch_sha256"))
    if not bool(capture.get("candidate_jsonl_exists")):
        blockers.append("fresh_capture_did_not_report_candidate_jsonl")
    if capture_path and capture_path != actual_path:
        blockers.append("candidate_path_mismatch_with_fresh_capture")
    if not capture_sha:
        blockers.append("candidate_batch_sha256_missing_from_fresh_capture")
    elif actual_sha != capture_sha:
        blockers.append("candidate_batch_sha256_mismatch_with_fresh_capture")
    return {
        "valid": not blockers,
        "status": "candidate_batch_matches_fresh_capture" if not blockers else "candidate_batch_provenance_blocked",
        "blockers": blockers,
        "candidate_rows_path": actual_path,
        "candidate_batch_sha256": actual_sha or None,
        "capture_candidate_output_path": capture_path or None,
        "capture_candidate_batch_sha256": capture_sha or None,
    }


def _fresh_capture_for_review(capture: dict[str, Any], collector: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    collector_generated_at = _norm(collector.get("generated_at_utc"))
    collector_ts = _parse_utc_iso(collector_generated_at)
    capture_generated_at = _norm(capture.get("generated_at_utc"))
    capture_ts = _parse_utc_iso(capture_generated_at)
    nested_capture = _as_dict(_as_dict(collector.get("latest_goal_loop_report")).get("capture_report"))
    nested_generated_at = _norm(nested_capture.get("generated_at_utc"))
    nested_ts = _parse_utc_iso(nested_generated_at)

    def details(*, fresh: bool, status: str, source: str, blockers: list[str]) -> dict[str, Any]:
        return {
            "fresh": fresh,
            "status": status,
            "effective_capture_source": source,
            "capture_latest_generated_at_utc": capture_generated_at or None,
            "collector_generated_at_utc": collector_generated_at or None,
            "collector_nested_capture_generated_at_utc": nested_generated_at or None,
            "blockers": blockers,
        }

    if collector_generated_at and collector_ts is None:
        return capture, details(
            fresh=False,
            status="collector_generated_at_malformed_for_capture_review",
            source="capture_latest",
            blockers=["collector_generated_at_malformed_for_capture_review"],
        )
    if capture.get("_source_status") != "loaded":
        if nested_capture and nested_ts is not None and (collector_ts is None or nested_ts >= collector_ts):
            return nested_capture, details(
                fresh=True,
                status="collector_nested_capture_fresh_for_candidate_review",
                source="collector_nested_capture_report",
                blockers=[],
            )
        return capture, details(
            fresh=False,
            status="capture_source_not_loaded",
            source="capture_latest",
            blockers=["capture_source_not_loaded"],
        )
    if capture_ts is None:
        if nested_capture and nested_ts is not None and (collector_ts is None or nested_ts >= collector_ts):
            return nested_capture, details(
                fresh=True,
                status="collector_nested_capture_fresh_for_candidate_review",
                source="collector_nested_capture_report",
                blockers=[],
            )
        return capture, details(
            fresh=False,
            status="capture_generated_at_missing_or_malformed",
            source="capture_latest",
            blockers=["capture_generated_at_missing_or_malformed"],
        )
    if collector_ts is not None and capture_ts < collector_ts:
        if nested_capture and nested_ts is not None and nested_ts >= collector_ts:
            return nested_capture, details(
                fresh=True,
                status="collector_nested_capture_fresh_for_candidate_review",
                source="collector_nested_capture_report",
                blockers=[],
            )
        return capture, details(
            fresh=False,
            status="capture_older_than_collector",
            source="capture_latest",
            blockers=["capture_older_than_collector"],
        )
    return capture, details(
        fresh=True,
        status="capture_latest_fresh_for_candidate_review",
        source="capture_latest",
        blockers=[],
    )


def _status_for(
    *,
    scheduler: dict[str, Any],
    scheduler_freshness: dict[str, Any],
    capture_freshness: dict[str, Any],
    capture: dict[str, Any],
    collector: dict[str, Any],
    validation: dict[str, Any],
    candidate_batch_provenance: dict[str, Any],
    safety_violations: list[str],
    guarded_append_observed: bool,
) -> str:
    if safety_violations:
        return "candidate_review_blocked_safety_violation"
    if scheduler.get("_source_status") != "loaded" or scheduler.get("status") != "scheduler_ready_for_next_market_window":
        return "candidate_review_waiting_for_scheduler_health"
    if not scheduler_freshness.get("fresh"):
        return "candidate_review_waiting_for_scheduler_health"
    if not capture_freshness.get("fresh"):
        return "candidate_review_waiting_for_fresh_capture_report"
    if guarded_append_observed:
        return "candidate_review_guarded_append_observed_waiting_for_exits"
    if not validation.get("candidate_jsonl_exists"):
        return "candidate_review_waiting_for_real_candidate_jsonl"
    if capture.get("candidate_rows_staged") or collector.get("candidate_rows_staged"):
        if not validation.get("append_allowed"):
            return "candidate_review_blocked_validation_failed"
    if not candidate_batch_provenance.get("valid"):
        return "candidate_review_blocked_candidate_batch_provenance"
    if validation.get("append_allowed"):
        return "candidate_review_required_append_allowed_no_append_performed"
    return "candidate_review_waiting_for_real_candidate_jsonl"


def build_report(
    *,
    candidate_jsonl_path: Path = stager.DEFAULT_OUTPUT,
    capture_latest_path: Path = DEFAULT_CAPTURE_LATEST,
    collector_latest_path: Path = DEFAULT_COLLECTOR_LATEST,
    scheduler_health_latest_path: Path = DEFAULT_SCHEDULER_HEALTH_LATEST,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    capture = _load_json(capture_latest_path)
    collector = _load_json(collector_latest_path)
    scheduler = _load_json(scheduler_health_latest_path)
    effective_capture, capture_freshness = _fresh_capture_for_review(capture, collector)
    validation = _candidate_validation(candidate_jsonl_path, generated_at)
    scheduler_freshness = _scheduler_freshness(scheduler, collector)
    candidate_batch_provenance = _candidate_batch_provenance(candidate_jsonl_path, validation, effective_capture)
    safety_violations = _safety_violations(effective_capture, collector, scheduler)
    guarded_append_observed = _guarded_append_observed(effective_capture, collector)
    status = _status_for(
        scheduler=scheduler,
        scheduler_freshness=scheduler_freshness,
        capture_freshness=capture_freshness,
        capture=effective_capture,
        collector=collector,
        validation=validation,
        candidate_batch_provenance=candidate_batch_provenance,
        safety_violations=safety_violations,
        guarded_append_observed=guarded_append_observed,
    )
    append_command_template = (
        "npm run options:append:phase2-forward-paper-shadow -- "
        f"{_rel(candidate_jsonl_path)} "
        "--approval-token <EXPLICIT_OPERATOR_APPROVAL_TOKEN> --market-window-confirmed"
    )
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "strict_forward_rows": collector.get("strict_forward_rows"),
        "required_rows": collector.get("required_rows"),
        "remaining_rows": collector.get("remaining_rows"),
        "accepted_profitability": bool(collector.get("accepted_profitability")),
        "candidate_jsonl_path": _rel(candidate_jsonl_path),
        "candidate_jsonl_exists": bool(validation.get("candidate_jsonl_exists")),
        "candidate_validation": validation,
        "candidate_batch_provenance": candidate_batch_provenance,
        "capture_status": effective_capture.get("status"),
        "capture_candidate_rows_staged": effective_capture.get("candidate_rows_staged"),
        "capture_freshness": capture_freshness,
        "collector_status": collector.get("status"),
        "collector_candidate_rows_staged": collector.get("candidate_rows_staged"),
        "scheduler_status": scheduler.get("status"),
        "scheduler_health_freshness": scheduler_freshness,
        "scheduler_blockers": [
            *(_as_list(scheduler.get("blockers"))),
            *(_as_list(scheduler_freshness.get("blockers"))),
        ],
        "safety_violations": safety_violations,
        "review_decision_table": [
            {
                "decision": "wait_for_real_candidate_jsonl",
                "pass": status == "candidate_review_waiting_for_real_candidate_jsonl",
                "requirements": ["valid_market_window", "real_phase2_scan_picks", "candidate_jsonl_written"],
            },
            {
                "decision": "operator_review_required_before_append",
                "pass": status == "candidate_review_required_append_allowed_no_append_performed",
                "requirements": ["append_allowed", "explicit_operator_approval_token", "confirmed_market_window", "no_safety_violations"],
            },
            {
                "decision": "validation_blocked",
                "pass": status == "candidate_review_blocked_validation_failed",
                "requirements": ["inspect_candidate_append_validation", "do_not_append"],
            },
            {
                "decision": "candidate_batch_provenance_blocked",
                "pass": status == "candidate_review_blocked_candidate_batch_provenance",
                "requirements": ["candidate_jsonl_matches_fresh_capture_path_and_sha256", "do_not_append"],
            },
            {
                "decision": "scheduler_health_blocked",
                "pass": status == "candidate_review_waiting_for_scheduler_health",
                "requirements": ["scheduler_ready_for_next_market_window", "scheduler_health_fresh_for_candidate_review"],
            },
            {
                "decision": "capture_freshness_blocked",
                "pass": status == "candidate_review_waiting_for_fresh_capture_report",
                "requirements": ["capture_latest_fresh_or_collector_nested_capture_fresh_for_candidate_review"],
            },
        ],
        "operator_commands": {
            "refresh_scheduler_health": "npm run options:goal-loop:strict-forward-30-scheduler-health -- --json",
            "refresh_collector_status": "npm run options:goal-loop:strict-forward-30-auto-window -- --json",
            "validate_candidate_jsonl": f"npm run options:validate:phase2-forward-paper-shadow-candidate -- {_rel(candidate_jsonl_path)}",
            "guarded_append_template": append_command_template,
        },
        "append_token_required": appender.PHASE2_APPROVAL_TOKEN,
        "append_allowed_by_current_validation": bool(validation.get("append_allowed")),
        "guarded_append_observed": guarded_append_observed,
        "cohort_append_performed": False,
        "append_performed_by_review_packet": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "quotes_imported": False,
        "proof_bars_changed": False,
        "historical_rows_are_forward_proof": False,
        "prohibited_actions": [
            "do_not_append_from_candidate_review_packet",
            "do_not_enable_live_validation_from_candidate_review_packet",
            "do_not_enable_auto_track_from_candidate_review_packet",
            "do_not_submit_broker_orders_from_candidate_review_packet",
            "do_not_import_quotes_from_candidate_review_packet",
            "do_not_lower_proof_bars_from_candidate_review_packet",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
        "source_artifacts": {
            "capture_latest": {"path": _rel(capture_latest_path), "status": capture.get("_source_status"), "report_status": capture.get("status")},
            "collector_latest": {"path": _rel(collector_latest_path), "status": collector.get("_source_status"), "report_status": collector.get("status")},
            "scheduler_health_latest": {"path": _rel(scheduler_health_latest_path), "status": scheduler.get("_source_status"), "report_status": scheduler.get("status")},
        },
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    validation = _as_dict(report.get("candidate_validation"))
    candidate_batch_provenance = _as_dict(report.get("candidate_batch_provenance"))
    lines = [
        "# Regular Options Strict Forward 30 Candidate Review Packet",
        "",
        f"Status: `{report.get('status')}`.",
        "",
        f"- Strict forward rows: `{report.get('strict_forward_rows')}/{report.get('required_rows')}`.",
        f"- Candidate JSONL exists: `{str(bool(report.get('candidate_jsonl_exists'))).lower()}`.",
        f"- Candidate rows: `{validation.get('candidate_rows')}`.",
        f"- Append allowed by validation: `{str(bool(report.get('append_allowed_by_current_validation'))).lower()}`.",
        f"- Append ready rows: `{validation.get('append_ready_rows')}`.",
        f"- Append rejected rows: `{validation.get('append_rejected_rows')}`.",
        f"- Capture status: `{report.get('capture_status')}`.",
        f"- Capture freshness: `{_as_dict(report.get('capture_freshness')).get('status')}`.",
        f"- Collector status: `{report.get('collector_status')}`.",
        f"- Scheduler status: `{report.get('scheduler_status')}`.",
        f"- Scheduler freshness: `{_as_dict(report.get('scheduler_health_freshness')).get('status')}`.",
        f"- Candidate batch provenance: `{candidate_batch_provenance.get('status')}`.",
        "",
        "This packet is review-only. It validates the candidate handoff and renders guarded commands, but it does not append rows or authorize live validation, auto-track, broker orders, quote import, proof-bar changes, promotion, or historical rows as forward proof.",
        "",
        "## Operator Commands",
        "",
    ]
    commands = _as_dict(report.get("operator_commands"))
    for name, command in commands.items():
        lines.append(f"- `{name}`: `{command}`")
    lines.append("")
    blockers = report.get("safety_violations") if isinstance(report.get("safety_violations"), list) else []
    if blockers:
        lines.extend(["## Safety Violations", ""])
        lines.extend(f"- `{item}`" for item in blockers)
        lines.append("")
    provenance_blockers = candidate_batch_provenance.get("blockers")
    if isinstance(provenance_blockers, list) and provenance_blockers:
        lines.extend(["## Candidate Batch Provenance Blockers", ""])
        lines.extend(f"- `{item}`" for item in provenance_blockers)
        lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    text = render_markdown(payload)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(text, encoding="utf8")
    latest_md.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only review packet for strict-forward 30-row candidate JSONL handoff.")
    parser.add_argument("--candidate-jsonl", type=Path, default=stager.DEFAULT_OUTPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(candidate_jsonl_path=args.candidate_jsonl)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] != "candidate_review_blocked_safety_violation" else 1


if __name__ == "__main__":
    raise SystemExit(main())
