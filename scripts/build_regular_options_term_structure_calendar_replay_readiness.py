from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_term_structure_calendar_replay_readiness"
CONCEPT_ID = "low_mid_vix_index_calendar_term_structure_dislocation_v1"
EXPECTED_STRUCTURE = "defined_risk_calendar_or_diagonal_debit_spreads_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-term-structure-calendar-playbook"
    / "latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-term-structure-calendar-replay-readiness.md"

DEFAULT_EVIDENCE_PATHS = (
    ROOT / "scripts" / "run_alpaca_options_strategy_lab.py",
    ROOT / "scripts" / "build_regular_options_structure_specific_harness.py",
    ROOT / "scripts" / "run_regular_options_multilane_portfolio.py",
    ROOT / "scripts" / "build_regular_options_feature_store.py",
    ROOT / "scripts" / "run_side_aware_zero_bid_replay.py",
    ROOT / "python-backend" / "positions_service.py",
    ROOT / "python-backend" / "positions_repository.py",
    ROOT / "python-backend" / "proof_contract.py",
    ROOT / "docs" / "regular-options-feature-store.md",
    ROOT / "docs" / "proof-evidence-contract.md",
    ROOT / "data" / "contracts" / "forward-cohort-preregistration.json",
    ROOT / "data" / "contracts" / "forward-holdout-contract.json",
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "lane_implementation_performed": False,
    "historical_replay_performed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_implement_scanner_or_playbook_logic",
    "do_not_run_historical_calendar_diagonal_replay",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
)


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


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
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
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _read_evidence(paths: tuple[Path, ...] | list[Path]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    texts: dict[str, str] = {}
    meta: list[dict[str, Any]] = []
    for path in paths:
        item = {"path": _rel(path), "exists": path.exists(), "status": "missing", "bytes": 0}
        if not path.exists():
            meta.append(item)
            continue
        try:
            text = path.read_text(encoding="utf8")
        except OSError as exc:
            item["status"] = "unreadable"
            item["error"] = type(exc).__name__
            meta.append(item)
            continue
        item["status"] = "loaded"
        item["bytes"] = len(text.encode("utf8"))
        texts[_rel(path)] = text
        meta.append(item)
    return texts, meta


def _find_terms(texts: dict[str, str], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path, text in texts.items():
        lowered = text.lower()
        matched = [term for term in terms if term.lower() in lowered]
        if matched:
            hits.append({"path": path, "matched_terms": matched})
    return hits


def _matched_term_count(hits: list[dict[str, Any]]) -> int:
    terms: set[str] = set()
    for hit in hits:
        terms.update(str(term) for term in _as_list(hit.get("matched_terms")))
    return len(terms)


def _status_from_hits(*, exact_hits: list[dict[str, Any]], partial_hits: list[dict[str, Any]]) -> str:
    if exact_hits:
        return "ready"
    if partial_hits:
        return "partial"
    return "missing"


def _assessment(
    *,
    prerequisite_id: str,
    label: str,
    critical: bool,
    status: str,
    blocker: str | None,
    evidence: list[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    return {
        "prerequisite_id": prerequisite_id,
        "label": label,
        "critical": critical,
        "status": status,
        "blocker": blocker if status != "ready" else None,
        "evidence": evidence,
        "note": note,
    }


def _build_prerequisite_assessments(texts: dict[str, str]) -> list[dict[str, Any]]:
    entry_exact = _find_terms(texts, ("long_back_month_ask - short_front_month_bid",))
    entry_partial = _find_terms(texts, ("calendar_volatility", "pmcc_diagonal", "calendar", "diagonal"))
    exit_exact = _find_terms(texts, ("long_back_month_bid - short_front_month_ask", "front_leg_expiry_value"))
    exit_partial = _find_terms(texts, ("expiry settlement", "time_exit", "expiration", "calendar day"))
    denominator_exact = _find_terms(
        texts,
        (
            "rejected_term_structure",
            "missing_leg_quote",
            "exact_entry_captured",
            "front_leg_expired",
            "assignment_or_expiration_blocked",
            "exact_exit_captured",
            "missing_exit",
        ),
    )
    assignment_exact = _find_terms(
        texts,
        ("front_leg_assignment_expiration_classifier", "assignment_or_expiration_blocked", "front_leg_expired"),
    )
    assignment_partial = _find_terms(texts, ("assignment_expiration_risk_review_required", "assignment near expiration", "expiration"))
    roll_exact = _find_terms(texts, ("open_waiting_policy_exit_or_expiry", "front_leg_expired", "front-leg expiry or roll handling"))
    roll_partial = _find_terms(texts, ("time_exit_day", "expiry settlement", "roll", "expiration"))
    pnl_exact = _find_terms(texts, ("net_pnl_usd", "fee_total_usd", "entry_fee_total_usd", "exit_fee_total_usd"))
    term_exact = _find_terms(texts, ("point_in_time_vix_bucket", "point_in_time_term_structure", "term_structure_inputs_ready"))
    term_partial = _find_terms(texts, ("^vix", "market_regime", "tradable_after_time", "term structure", "term_structure"))
    quote_exact = _find_terms(texts, ("calendar_diagonal_quote_surface_ready", "multi_expiry_quote_surface_ready"))
    quote_partial = _find_terms(texts, ("thetadata_opra_nbbo_1m", "trusted_intraday_opra_nbbo", "spy", "qqq"))
    holdout_exact = _find_terms(texts, ("protected_holdout_consumed", "protected holdout", "forward-holdout"))
    strict_new_exact = _find_terms(texts, ("strict_new_trade_count", "strict-new dedupe", "strict_new_dedupe_ready"))
    proof_exact = _find_terms(texts, ("proof_eligible", "trusted_intraday_opra_nbbo", "production proof"))

    return [
        _assessment(
            prerequisite_id="calendar_diagonal_bid_ask_entry_pricing",
            label="Calendar/diagonal side-aware bid/ask entry pricing",
            critical=True,
            status=_status_from_hits(exact_hits=entry_exact, partial_hits=entry_partial),
            blocker="missing_calendar_diagonal_side_aware_pricing_engine",
            evidence=entry_exact or entry_partial,
            note="Readiness requires a dedicated multi-expiry entry debit formula, not just the presence of calendar or diagonal labels.",
        ),
        _assessment(
            prerequisite_id="calendar_diagonal_exit_or_expiry_engine",
            label="Calendar/diagonal side-aware exit, expiry, or roll pricing",
            critical=True,
            status=_status_from_hits(exact_hits=exit_exact, partial_hits=exit_partial),
            blocker="missing_calendar_diagonal_exit_or_expiry_engine",
            evidence=exit_exact or exit_partial,
            note="Future replay must price the back leg, short front leg, and policy-defined front-leg expiry or roll state.",
        ),
        _assessment(
            prerequisite_id="full_denominator_status_mapping",
            label="Full denominator status mapping",
            critical=True,
            status="ready" if _matched_term_count(denominator_exact) >= 6 else "missing",
            blocker="missing_full_denominator_status_mapping",
            evidence=denominator_exact,
            note="Calendar replay needs no-candidate, rejected, missing, zero-bid, open, front-expired, assignment, exact-exit, and missing-exit rows.",
        ),
        _assessment(
            prerequisite_id="front_leg_assignment_expiration_classifier",
            label="Front-leg assignment and expiration classification",
            critical=True,
            status=_status_from_hits(exact_hits=assignment_exact, partial_hits=assignment_partial),
            blocker="missing_front_leg_assignment_expiration_classifier",
            evidence=assignment_exact or assignment_partial,
            note="Generic expiration fields are not enough unless replay can classify front-leg assignment/expiration outcomes.",
        ),
        _assessment(
            prerequisite_id="roll_or_expiry_policy",
            label="Roll or front-leg expiry policy",
            critical=True,
            status=_status_from_hits(exact_hits=roll_exact, partial_hits=roll_partial),
            blocker="missing_roll_or_expiry_policy",
            evidence=roll_exact or roll_partial,
            note="The future harness needs a frozen policy for profit-take, loss-cut, time-exit, roll, and front-leg expiry handling.",
        ),
        _assessment(
            prerequisite_id="net_usd_pnl_after_costs",
            label="Contract multiplier, fees, slippage, and net USD P&L",
            critical=True,
            status="ready" if pnl_exact else "missing",
            blocker="missing_net_usd_pnl_after_costs",
            evidence=pnl_exact,
            note="The repo has net-P&L plumbing only if it can be applied to calendar/diagonal multi-leg rows.",
        ),
        _assessment(
            prerequisite_id="point_in_time_vix_and_term_structure_inputs",
            label="Point-in-time VIX and term-structure inputs",
            critical=True,
            status=_status_from_hits(exact_hits=term_exact, partial_hits=term_partial),
            blocker="missing_point_in_time_term_structure_inputs",
            evidence=term_exact or term_partial,
            note="Term-structure dislocation must be known before entry and cannot read future IV, future option returns, or realized P&L.",
        ),
        _assessment(
            prerequisite_id="index_calendar_quote_surface",
            label="Trusted OPRA/NBBO multi-expiry quote surface for SPY/QQQ",
            critical=True,
            status=_status_from_hits(exact_hits=quote_exact, partial_hits=quote_partial),
            blocker="missing_index_calendar_quote_surface",
            evidence=quote_exact or quote_partial,
            note="Trusted OPRA/NBBO infrastructure exists, but readiness requires exact multi-expiry leg coverage for calendar/diagonal candidates.",
        ),
        _assessment(
            prerequisite_id="protected_holdout_guard",
            label="Protected-holdout guard",
            critical=True,
            status="ready" if holdout_exact else "missing",
            blocker="missing_protected_holdout_guard",
            evidence=holdout_exact,
            note="The readiness slice must remain non-holdout-consuming and keep future replay behind an explicit approval boundary.",
        ),
        _assessment(
            prerequisite_id="strict_new_dedupe",
            label="Strict-new dedupe versus the clean base stack",
            critical=True,
            status="ready" if strict_new_exact else "missing",
            blocker="missing_strict_new_dedupe",
            evidence=strict_new_exact,
            note="Future rows must be de-duplicated against the existing 157-row clean base stack before count claims.",
        ),
        _assessment(
            prerequisite_id="proof_boundary_labeling",
            label="Proof-boundary labeling",
            critical=True,
            status="ready" if proof_exact else "missing",
            blocker="missing_proof_boundary_labeling",
            evidence=proof_exact,
            note="Readbacks must label research/backfill versus production proof so historical rows are not presented as forward proof.",
        ),
    ]


def _preregistration_valid(playbook: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if playbook.get("concept_id") != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if playbook.get("structure") != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    if playbook.get("historical_replay_performed") is not False:
        reasons.append("historical_replay_performed_not_false")
    if playbook.get("lane_implementation_performed") is not False:
        reasons.append("lane_implementation_performed_not_false")
    return not reasons, reasons


def _overall_status(assessments: list[dict[str, Any]], prereg_valid: bool) -> str:
    if not prereg_valid:
        return "blocked_invalid_term_structure_calendar_preregistration"
    blockers = [row for row in assessments if row["critical"] and row["status"] != "ready"]
    if blockers:
        return "blocked_term_structure_calendar_replay_readiness"
    return "ready_for_research_only_implementation_approval_question"


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    evidence_paths: tuple[Path, ...] | list[Path] = DEFAULT_EVIDENCE_PATHS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    texts, evidence_meta = _read_evidence(evidence_paths)
    prereg_valid, prereg_reasons = _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    assessments = _build_prerequisite_assessments(texts) if prereg_valid else []
    blockers = [
        row["blocker"]
        for row in assessments
        if row.get("critical") and row.get("status") != "ready" and row.get("blocker")
    ]
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(assessments, prereg_valid),
        **READ_ONLY_FLAGS,
        "scope": "read_only_term_structure_calendar_replay_readiness_audit",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "source_artifacts": {
            "preregistered_term_structure_calendar_playbook": playbook_meta,
            "evidence_files": evidence_meta,
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_concept_id": CONCEPT_ID,
            "required_status": "preregistered_design_only",
            "required_structure": EXPECTED_STRUCTURE,
        },
        "critical_prerequisites": assessments,
        "blockers": blockers,
        "next_approval_boundary": (
            "A later implementation/replay harness requires separate research-only approval and must still forbid "
            "live, broker, quote import, evidence mutation, protected-holdout consumption, scanner/strategy release, "
            "stop/sizing/proof-bar changes, and promotion."
        ),
        "allowed_next_step": (
            "Return this readiness artifact to GPT-5.5 Pro for a continue/stop decision. If ready, the next step is "
            "an exact operator approval question for one research-only implementation/replay harness. If blocked, "
            "GPT-5.5 Pro should decide whether a named blocker needs approval or whether another read-only option-structure branch remains."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["preregistration_validation"]["valid"]:
        if report.get("concept_id") != CONCEPT_ID:
            raise ValueError("unexpected concept_id")
        if report.get("structure") != EXPECTED_STRUCTURE:
            raise ValueError("unexpected structure")
        required_ids = {
            "calendar_diagonal_bid_ask_entry_pricing",
            "calendar_diagonal_exit_or_expiry_engine",
            "full_denominator_status_mapping",
            "front_leg_assignment_expiration_classifier",
            "roll_or_expiry_policy",
            "net_usd_pnl_after_costs",
            "point_in_time_vix_and_term_structure_inputs",
            "index_calendar_quote_surface",
            "protected_holdout_guard",
            "strict_new_dedupe",
            "proof_boundary_labeling",
        }
        seen = {row.get("prerequisite_id") for row in report["critical_prerequisites"]}
        missing = required_ids - seen
        if missing:
            raise ValueError(f"missing prerequisite assessments: {sorted(missing)}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Term Structure Calendar Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_term_structure_calendar_replay_readiness.py`. It is a read-only readiness audit. It does not implement a scanner or playbook, run historical replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        "",
        "## Preregistration Validation",
        "",
        f"- Valid: `{_fmt_bool(report['preregistration_validation']['valid'])}`.",
        f"- Reasons: `{json.dumps(report['preregistration_validation']['reasons'])}`.",
        "",
        "## Critical Prerequisites",
        "",
        "| Prerequisite | Status | Blocker | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in _as_list(report.get("critical_prerequisites")):
        row = _as_dict(row)
        evidence_paths = ", ".join(f"`{item.get('path')}`" for item in _as_list(row.get("evidence"))[:4])
        lines.append(
            f"| {row.get('label')} | `{row.get('status')}` | `{row.get('blocker')}` | {evidence_paths or '-'} |"
        )
    lines.extend(["", "## Blockers", ""])
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Approval Boundary", "", report["next_approval_boundary"], "", "## Forbidden Actions", ""])
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
    parser = argparse.ArgumentParser(description="Build a read-only term-structure calendar/diagonal replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(preregistered_playbook_path=args.preregistered_playbook)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["preregistration_validation"]["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
