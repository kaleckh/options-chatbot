from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import append_volatility_expansion_forward_paper_shadow_rows as appender
from scripts import build_volatility_expansion_forward_paper_shadow_report as forward_report


REPORT_ID = "regular_options_strict_forward_30_exit_completion_stager"
DEFAULT_EVIDENCE_PATH = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_exit_evidence.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "forward-tracking" / "phase2_regular_options_forward_paper_shadow_exit_completion_candidate_rows.jsonl"
DEFAULT_LATEST_JSON = ROOT / "data" / "forward-tracking" / f"{REPORT_ID}_latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-strict-forward-30-exit-completion-stager.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = {"path": _rel(path), "exists": path.exists(), "status": "missing", "row_count": 0, "malformed_row_count": 0}
    if not path.exists():
        return [], source
    rows: list[dict[str, Any]] = []
    malformed = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    source.update({"status": "loaded" if malformed == 0 else "malformed", "row_count": len(rows), "malformed_row_count": malformed})
    return rows, source


def _selection_id(row: dict[str, Any]) -> str:
    return _norm(row.get("selection_id") or row.get("row_id"))


def _is_open_entry(row: dict[str, Any]) -> bool:
    return _norm_lower(row.get("denominator_status")) in {"exact_entry_captured", "open_waiting_policy_exit"}


def _is_exact_exit(row: dict[str, Any]) -> bool:
    return _norm_lower(row.get("denominator_status")) == "exact_exit_captured"


def _open_rows_by_selection(cohort_rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    open_rows: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()
    duplicate_completed: set[str] = set()
    for row in cohort_rows:
        selection_id = _selection_id(row)
        if not selection_id:
            continue
        if _is_exact_exit(row):
            if selection_id in completed:
                duplicate_completed.add(selection_id)
            completed.add(selection_id)
        elif _is_open_entry(row) and selection_id not in open_rows:
            open_rows[selection_id] = row
    return open_rows, completed, duplicate_completed


def _candidate_row_id(open_row: dict[str, Any], evidence: dict[str, Any]) -> str:
    explicit = _norm(evidence.get("row_id"))
    if explicit:
        return explicit
    selection_id = _selection_id(open_row)
    stamp = _norm(evidence.get("exit_quote_timestamp_utc") or evidence.get("captured_at_utc") or "exit").replace(":", "").replace("-", "")
    return f"phase2:{selection_id}:exact_exit_captured:{stamp}"


def _build_candidate(open_row: dict[str, Any], evidence: dict[str, Any], *, evidence_path: Path, evidence_sha256: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    selection_id = _selection_id(open_row)
    if _norm(evidence.get("selection_id") or evidence.get("source_selection_id")) != selection_id:
        reasons.append("selection_id_mismatch")
    exit_bid = _safe_float(evidence.get("exit_bid"))
    exit_ask = _safe_float(evidence.get("exit_ask"))
    net_pnl_usd = _safe_float(evidence.get("net_pnl_usd") if evidence.get("net_pnl_usd") is not None else evidence.get("realized_net_pnl_usd"))
    required = {
        "exit_quote_source": _norm(evidence.get("exit_quote_source") or evidence.get("quote_source")),
        "exit_quote_timestamp_utc": _norm(evidence.get("exit_quote_timestamp_utc") or evidence.get("quote_timestamp_utc")),
        "policy_exit_condition": _norm(evidence.get("policy_exit_condition")),
    }
    for key, value in required.items():
        if not value:
            reasons.append(f"missing_{key}")
    if required["exit_quote_source"] and _norm_lower(required["exit_quote_source"]) not in forward_report.TRUSTED_EXECUTABLE_QUOTE_SOURCES:
        reasons.append("untrusted_exit_quote_source")
    if exit_bid is None or exit_ask is None:
        reasons.append("missing_exit_bid_ask")
    if net_pnl_usd is None:
        reasons.append("missing_net_pnl_usd")
    if any(token in _norm_lower(evidence.get(key)) for key in ("quote_evidence_class", "exit_quote_evidence_class", "exit_price_source", "pnl_basis") for token in ("midpoint", "eod", "display", "last", "manual", "model", "synthetic", "lookahead")):
        reasons.append("non_executable_exit_basis")
    if reasons:
        return None, reasons

    candidate = dict(open_row)
    candidate.update(
        {
            "row_id": _candidate_row_id(open_row, evidence),
            "selection_id": selection_id,
            "denominator_status": "exact_exit_captured",
            "exit_evidence_status": "exact_exit_captured",
            "exit_quote_source": required["exit_quote_source"],
            "exit_quote_timestamp_utc": required["exit_quote_timestamp_utc"],
            "exit_bid": exit_bid,
            "exit_ask": exit_ask,
            "policy_exit_condition": required["policy_exit_condition"],
            "net_pnl_usd": net_pnl_usd,
            "candidate_source_mode": "real_market_window_scan_picks",
            "fixture_mode": False,
            "source_artifact_path": _rel(evidence_path),
            "source_artifact_sha256": evidence_sha256,
            "market_window_status": _norm(evidence.get("market_window_status") or "open"),
            "captured_at_utc": _norm(evidence.get("captured_at_utc") or required["exit_quote_timestamp_utc"]),
            "notes": f"staged_by={REPORT_ID}; open_row_id={_norm(open_row.get('row_id'))}; evidence_path={_rel(evidence_path)}",
        }
    )
    if evidence.get("net_pnl_pct") is not None:
        candidate["net_pnl_pct"] = evidence.get("net_pnl_pct")
    return candidate, []


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _validate_candidates(candidate_rows: list[dict[str, Any]], generated_at_utc: str, cohort_log_path: Path) -> dict[str, Any]:
    if not candidate_rows:
        return {"append_allowed": False, "append_ready_rows": 0, "append_rejected_rows": 0, "append_reject_counts": {}}
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        candidate_path = Path(temp_dir) / "exit_completion_candidates.jsonl"
        _write_jsonl(candidate_path, candidate_rows)
        report = forward_report.build_report(
            candidate_rows_path=candidate_path,
            cohort_log_path=cohort_log_path,
            schema_path=forward_report.DEFAULT_PHASE2_SCHEMA,
            allowed_lane_ids=forward_report.PHASE2_FROZEN_LANE_IDS,
            generated_at_utc=generated_at_utc,
        )
    return report.get("candidate_append_validation") if isinstance(report.get("candidate_append_validation"), dict) else {}


def build_report(
    *,
    exit_evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    cohort_log_path: Path = forward_report.DEFAULT_PHASE2_COHORT_LOG,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    latest_json_path: Path = DEFAULT_LATEST_JSON,
    docs_report_path: Path = DEFAULT_DOCS_REPORT,
    no_write: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    cohort_rows, cohort_source = forward_report._load_jsonl(cohort_log_path)
    evidence_rows, evidence_source = _load_jsonl(exit_evidence_path)
    evidence_sha256 = _sha256_file(exit_evidence_path)
    open_rows, completed_selections, duplicate_completed = _open_rows_by_selection(cohort_rows)
    reject_counts: Counter[str] = Counter()
    candidate_rows: list[dict[str, Any]] = []
    row_results: list[dict[str, Any]] = []
    seen_candidate_row_ids: set[str] = set()
    for index, evidence in enumerate(evidence_rows, start=1):
        selection_id = _norm(evidence.get("selection_id") or evidence.get("source_selection_id"))
        reasons: list[str] = []
        open_row = open_rows.get(selection_id)
        if not selection_id:
            reasons.append("missing_selection_id")
        elif selection_id in duplicate_completed:
            reasons.append("duplicate_existing_exact_exit_selection")
        elif selection_id in completed_selections:
            reasons.append("selection_already_completed")
        elif open_row is None:
            reasons.append("no_matching_open_forward_entry")
        candidate: dict[str, Any] | None = None
        if open_row is not None and not reasons:
            candidate, reasons = _build_candidate(open_row, evidence, evidence_path=exit_evidence_path, evidence_sha256=evidence_sha256)
            if candidate is not None:
                row_id = _norm(candidate.get("row_id"))
                if row_id in seen_candidate_row_ids:
                    reasons.append("duplicate_candidate_row_id")
                    candidate = None
                else:
                    seen_candidate_row_ids.add(row_id)
        for reason in reasons:
            reject_counts[reason] += 1
        if candidate is not None:
            candidate_rows.append(candidate)
        row_results.append({"row_number": index, "selection_id": selection_id, "valid": candidate is not None, "reject_reasons": reasons})

    validation = _validate_candidates(candidate_rows, generated_at, cohort_log_path)
    append_allowed = bool(validation.get("append_allowed"))
    writes_performed: list[str] = []
    if candidate_rows and append_allowed and not no_write:
        _write_jsonl(output_path, candidate_rows)
        writes_performed.append(_rel(output_path))
    status = "exit_completion_candidates_ready_no_append" if append_allowed else "exit_completion_candidates_not_ready"
    if cohort_source.get("status") != "loaded" or not cohort_rows:
        status = "exit_completion_waiting_for_open_forward_rows"
    elif evidence_source.get("status") == "missing":
        status = "exit_completion_waiting_for_exit_evidence_jsonl"
    elif evidence_source.get("status") != "loaded":
        status = "exit_completion_evidence_source_malformed"
    elif evidence_rows and not candidate_rows:
        status = "exit_completion_evidence_rows_rejected"
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "read_only": bool(no_write),
        "cohort_read_only": True,
        "cohort_log_path": _rel(cohort_log_path),
        "exit_evidence_path": _rel(exit_evidence_path),
        "output_path": _rel(output_path),
        "cohort_source": cohort_source,
        "exit_evidence_source": evidence_source,
        "open_forward_entry_count": len(open_rows),
        "existing_completed_selection_count": len(completed_selections),
        "candidate_rows_staged": len(candidate_rows),
        "candidate_row_ids": [_norm(row.get("row_id")) for row in candidate_rows],
        "append_validation": validation,
        "append_allowed_by_validation": append_allowed,
        "guarded_append_template": (
            "npm run options:append:phase2-forward-paper-shadow -- "
            f"{_rel(output_path)} --approval-token {appender.PHASE2_APPROVAL_TOKEN} --market-window-confirmed"
        ),
        "cohort_append_performed": False,
        "reject_counts": dict(sorted(reject_counts.items())),
        "row_results": row_results,
        "no_write": no_write,
        "writes_performed": writes_performed,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "quotes_imported": False,
        "proof_bars_changed": False,
        "historical_rows_are_forward_proof": False,
        "prohibited_actions": [
            "do_not_append_from_exit_completion_stager",
            "do_not_enable_live_validation_from_exit_completion_stager",
            "do_not_enable_auto_track_from_exit_completion_stager",
            "do_not_submit_broker_orders_from_exit_completion_stager",
            "do_not_import_quotes_from_exit_completion_stager",
            "do_not_lower_proof_bars_from_exit_completion_stager",
            "do_not_treat_historical_rows_as_forward_proof",
        ],
    }
    if not no_write:
        latest_json_path.parent.mkdir(parents=True, exist_ok=True)
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        docs_report_path.write_text(render_markdown(report) + "\n", encoding="utf8")
        report["writes_performed"].extend([_rel(latest_json_path), _rel(docs_report_path)])
        latest_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Regular Options Strict Forward 30 Exit Completion Stager",
            "",
            f"Status: `{report.get('status')}`.",
            "",
            f"- Open forward entries: `{report.get('open_forward_entry_count')}`.",
            f"- Exit evidence rows: `{_safe_source_count(report.get('exit_evidence_source'))}`.",
            f"- Candidate rows staged: `{report.get('candidate_rows_staged')}`.",
            f"- Append allowed by validation: `{str(bool(report.get('append_allowed_by_validation'))).lower()}`.",
            f"- Cohort append performed: `{str(bool(report.get('cohort_append_performed'))).lower()}`.",
            f"- Reject counts: `{json.dumps(report.get('reject_counts'), sort_keys=True)}`.",
            "",
            "This stager is not an appender. It builds candidate rows only when existing open forward rows have trusted exact-exit evidence, then leaves guarded append to the explicit tokened command.",
            "",
        ]
    )


def _safe_source_count(value: Any) -> int:
    return int(value.get("row_count") or 0) if isinstance(value, dict) else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage exact-exit completion candidate rows for strict-forward 30 open Phase 2 selections.")
    parser.add_argument("--exit-evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--cohort-log", type=Path, default=forward_report.DEFAULT_PHASE2_COHORT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--latest-json", type=Path, default=DEFAULT_LATEST_JSON)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        exit_evidence_path=args.exit_evidence,
        cohort_log_path=args.cohort_log,
        output_path=args.output,
        latest_json_path=args.latest_json,
        docs_report_path=args.docs_report,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
