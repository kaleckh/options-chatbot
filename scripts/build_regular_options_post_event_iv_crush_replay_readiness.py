from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_post_event_iv_crush_replay_readiness"
CONCEPT_ID = "post_event_iv_crush_index_iron_condor_v1"
EXPECTED_STRUCTURE = "defined_risk_short_iron_condors_or_iron_butterflies_only"

DEFAULT_PREREGISTERED_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-post-event-iv-crush-iron-condor-playbook" / "latest.json"
DEFAULT_MACRO_EVENT_CALENDAR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "latest.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_QUOTE_CAPABILITY = ROOT / "data" / "profitability-lab" / "regular-options-local-quote-structure-capability-matrix" / "latest.json"
DEFAULT_BASE_LEDGER = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-post-event-iv-crush-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-post-event-iv-crush-replay-readiness.md"

REQUIRED_DENOMINATOR_STATUSES = {
    "no_event",
    "no_candidate",
    "rejected_event_calendar_missing",
    "rejected_iv_crush_proxy_missing",
    "rejected_vix_bucket",
    "rejected_width_or_liquidity",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_captured",
    "open_waiting_policy_exit_or_expiry",
    "assignment_or_expiration_blocked",
    "exact_exit_captured",
    "expired_settled_exact",
    "missing_exit",
}

REQUIRED_EVENT_CATEGORIES = {
    "cpi",
    "fomc_minutes",
    "fomc_rate_decision",
    "nonfarm_payrolls",
    "pce",
    "scheduled_fed_chair_testimony",
}

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "replay_performed": False,
    "lane_implementation_performed": False,
    "event_calendar_implemented_in_this_slice": False,
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
    "historical_rows_are_forward_proof": False,
    "undefined_or_uncapped_short_premium_risk_allowed": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_implement_scanner_or_playbook_logic",
    "do_not_run_historical_replay",
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
    "do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
)


def _utc_now() -> str:
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


def _string_set(values: Any) -> set[str]:
    return {str(value) for value in _as_list(values) if str(value)}


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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("last_updated")
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    return payload, meta


def _assessment(prerequisite_id: str, label: str, ready: bool, blockers: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "prerequisite_id": prerequisite_id,
        "label": label,
        "status": "ready" if ready else "blocked",
        "blockers": sorted(set(blockers)),
        "details": details,
    }


def _validate_preregistration(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    concept = _as_dict(payload.get("concept"))
    concept_id = payload.get("concept_id") or concept.get("concept_id")
    status = payload.get("status") or concept.get("status")
    structure = payload.get("structure") or concept.get("structure")
    if meta["status"] != "loaded":
        reasons.append("missing_or_unreadable_preregistration")
    if payload.get("report_id") != "regular_options_preregistered_post_event_iv_crush_iron_condor_playbook":
        reasons.append("unexpected_report_id")
    if concept_id != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if status != "preregistered_design_only":
        reasons.append("unexpected_status")
    if structure != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    for flag in (
        "accepted_profitability",
        "lane_implementation_performed",
        "historical_replay_performed",
        "scanner_policy_changed",
        "strategy_logic_changed",
    ):
        if payload.get(flag) is not False:
            reasons.append(f"{flag}_not_false")
    denominator = _as_dict(payload.get("denominator_contract"))
    statuses = _string_set(denominator.get("statuses") or payload.get("denominator_statuses") or concept.get("denominator_statuses"))
    missing_statuses = sorted(REQUIRED_DENOMINATOR_STATUSES - statuses)
    if missing_statuses:
        reasons.append("missing_required_denominator_statuses")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "missing_denominator_statuses": missing_statuses,
        "concept_id": concept_id,
        "status": status,
        "structure": structure,
    }


def _event_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if lowered in REQUIRED_EVENT_CATEGORIES:
        return lowered
    if "fomc" in lowered and "minute" in lowered:
        return "fomc_minutes"
    if "fomc" in lowered or "fed rate" in lowered:
        return "fomc_rate_decision"
    if "fed chair" in lowered or "testimony" in lowered:
        return "scheduled_fed_chair_testimony"
    if "cpi" in lowered or "inflation" in lowered:
        return "cpi"
    if "payroll" in lowered or "nonfarm" in lowered or "nfp" in lowered:
        return "nonfarm_payrolls"
    if "pce" in lowered:
        return "pce"
    return None


def _event_calendar_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    details: dict[str, Any] = {
        "source_status": meta["status"],
        "report_status": payload.get("status"),
        "event_count": payload.get("event_count"),
    }
    if meta["status"] != "loaded":
        blockers.append("macro_event_calendar_source_missing")
    else:
        blockers.extend(str(item) for item in _as_list(payload.get("blockers")) if item)
        events = _as_list(payload.get("events") or payload.get("event_rows"))
        categories: set[str] = set()
        late_known_at_count = 0
        missing_known_at_count = 0
        for event in events:
            row = _as_dict(event)
            category = _event_category(row.get("event_type") or row.get("category") or row.get("event_name"))
            if category:
                categories.add(category)
            if not (row.get("known_at_utc") or row.get("known_at")):
                missing_known_at_count += 1
            if row.get("known_after_event") is True:
                late_known_at_count += 1
        details.update(
            {
                "categories": sorted(categories),
                "missing_categories": sorted(REQUIRED_EVENT_CATEGORIES - categories),
                "missing_known_at_count": missing_known_at_count,
                "late_known_at_count": late_known_at_count,
            }
        )
        if not events:
            blockers.append("macro_event_calendar_source_missing")
        if REQUIRED_EVENT_CATEGORIES - categories:
            blockers.append("macro_event_calendar_category_coverage_missing")
        if missing_known_at_count or late_known_at_count:
            blockers.append("macro_event_calendar_known_at_not_point_in_time")
        if payload.get("status") == "blocked_macro_event_calendar_source_missing":
            blockers.append("macro_event_calendar_source_missing")
    return _assessment(
        "point_in_time_macro_event_calendar",
        "Point-in-time scheduled macro-event calendar",
        not blockers,
        blockers,
        details,
    )


def _feature_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            tokens.append(str(key))
            tokens.extend(_feature_tokens(item))
    elif isinstance(value, list):
        for item in value:
            tokens.extend(_feature_tokens(item))
    elif isinstance(value, str):
        tokens.append(value)
    return tokens


def _iv_event_premium_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    markers = ("iv_event_premium", "event_iv_premium", "iv_crush_proxy", "pre_event_iv", "post_event_iv", "event_premium")
    tokens = [token.lower() for token in _feature_tokens(payload)]
    matched = sorted({marker for marker in markers if any(marker in token for token in tokens)})
    blockers: list[str] = []
    if meta["status"] != "loaded" or not matched:
        blockers.append("iv_event_premium_proxy_missing")
    return _assessment(
        "point_in_time_iv_event_premium_proxy",
        "Point-in-time IV/event-premium proxy",
        not blockers,
        blockers,
        {"source_status": meta["status"], "matched_markers": matched, "report_status": payload.get("status")},
    )


def _vix_bucket_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if meta["status"] != "loaded":
        blockers.append("point_in_time_vix_bucket_missing")
    elif not (
        payload.get("status") == "point_in_time_vix_bucket_ready"
        and payload.get("point_in_time_vix_low_mid_bucket_available") is True
        and not _as_list(payload.get("blockers"))
    ):
        blockers.extend(str(item) for item in _as_list(payload.get("blockers")) if item)
        if not blockers:
            blockers.append("point_in_time_vix_bucket_not_ready")
    return _assessment(
        "point_in_time_vix_bucket",
        "Point-in-time VIX low/mid bucket",
        not blockers,
        blockers,
        {
            "source_status": meta["status"],
            "report_status": payload.get("status"),
            "coverage_pct": payload.get("coverage_pct"),
            "source_rows_count": payload.get("source_rows_count"),
        },
    )


def _quote_surface_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if meta["status"] != "loaded":
        blockers.append("missing_index_iron_condor_quote_surface")
    elif payload.get("post_event_iv_crush_iron_condor_quote_surface_ready") is True or payload.get("status") == "post_event_iv_crush_iron_condor_quote_surface_ready":
        blockers = []
    else:
        blockers.extend(str(item) for item in _as_list(payload.get("blockers")) if "vix" not in str(item).lower())
        if not blockers:
            blockers.append("missing_index_iron_condor_quote_surface")
    return _assessment(
        "trusted_four_leg_quote_surface",
        "Trusted four-leg index iron condor/butterfly quote surface",
        not blockers,
        blockers,
        {
            "source_status": meta["status"],
            "report_status": payload.get("status"),
            "ready_flag": payload.get("post_event_iv_crush_iron_condor_quote_surface_ready"),
        },
    )


def _playbook_formula_assessments(playbook: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    text = json.dumps(playbook, sort_keys=True).lower()
    pricing_ready = (
        all(term in text for term in ("entry_credit", "exit_debit", "short_leg_bid", "long_leg_ask", "short_leg_ask", "long_leg_bid"))
        or all(term in text for term in ("short_call", "long_call", "short_put", "long_put", "net_credit", "exit_debit"))
    )
    margin_ready = "max_loss" in text and ("margin" in text or "width" in text)
    assignment_ready = "assignment" in text and "expiration" in text
    denominator_ready = validation["valid"] and not validation["missing_denominator_statuses"]
    return [
        _assessment(
            "four_leg_short_premium_formula_contract",
            "Four-leg side-aware short-premium entry/exit formula contract",
            pricing_ready,
            [] if pricing_ready else ["missing_four_leg_short_premium_formula_contract"],
            {"required_terms_present": pricing_ready},
        ),
        _assessment(
            "max_loss_margin_convention",
            "Defined-risk max-loss and margin convention",
            margin_ready,
            [] if margin_ready else ["missing_max_loss_margin_convention"],
            {"required_terms_present": margin_ready},
        ),
        _assessment(
            "assignment_expiration_contract",
            "Assignment/expiration handling contract",
            assignment_ready,
            [] if assignment_ready else ["missing_assignment_expiration_contract"],
            {"required_terms_present": assignment_ready},
        ),
        _assessment(
            "full_denominator_mapping",
            "Full denominator and outcome-status mapping",
            denominator_ready,
            [] if denominator_ready else ["missing_full_denominator_mapping"],
            {"missing_denominator_statuses": validation["missing_denominator_statuses"]},
        ),
    ]


def _base_ledger_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if meta["status"] != "loaded":
        blockers.append("missing_strict_new_dedupe")
    elif payload.get("status") not in {"base_clean_stack_identity_ledger_ready", "identity_ledger_ready"}:
        blockers.extend(str(item) for item in _as_list(payload.get("blockers")) if item)
        if not blockers:
            blockers.append("missing_strict_new_dedupe")
    return _assessment(
        "strict_new_dedupe_against_base_stack",
        "Strict-new dedupe against base clean stack",
        not blockers,
        blockers,
        {
            "source_status": meta["status"],
            "report_status": payload.get("status"),
            "ledger_row_count": payload.get("ledger_row_count"),
            "duplicate_identity_count": payload.get("duplicate_identity_count"),
            "protected_holdout_overlap_count": payload.get("protected_holdout_overlap_count"),
        },
    )


def _holdout_assessment(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if meta["status"] != "loaded":
        blockers.append("missing_protected_holdout_contract")
    elif payload.get("protected_holdout_consumed") is True:
        blockers.append("protected_holdout_already_consumed")
    return _assessment(
        "protected_holdout_guard",
        "Protected holdout guard",
        not blockers,
        blockers,
        {"source_status": meta["status"], "protected_holdout_consumed": payload.get("protected_holdout_consumed")},
    )


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    macro_event_calendar_path: Path = DEFAULT_MACRO_EVENT_CALENDAR,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    vix_bucket_path: Path = DEFAULT_VIX_BUCKET,
    quote_capability_path: Path = DEFAULT_QUOTE_CAPABILITY,
    base_ledger_path: Path = DEFAULT_BASE_LEDGER,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    calendar, calendar_meta = _load_json(macro_event_calendar_path, required=False)
    features, features_meta = _load_json(feature_store_path, required=False)
    vix_bucket, vix_meta = _load_json(vix_bucket_path, required=False)
    quote_capability, quote_meta = _load_json(quote_capability_path, required=False)
    base_ledger, base_ledger_meta = _load_json(base_ledger_path, required=False)
    holdout, holdout_meta = _load_json(holdout_contract_path, required=False)

    validation = _validate_preregistration(playbook, playbook_meta)
    if not validation["valid"]:
        prerequisites: list[dict[str, Any]] = []
        blockers = validation["reasons"]
        status = "blocked_invalid_post_event_iv_crush_preregistration"
    else:
        prerequisites = [
            _assessment("valid_preregistered_playbook", "Valid preregistered post-event IV-crush playbook", True, [], validation),
            _event_calendar_assessment(calendar, calendar_meta),
            _iv_event_premium_assessment(features, features_meta),
            _vix_bucket_assessment(vix_bucket, vix_meta),
            _quote_surface_assessment(quote_capability, quote_meta),
            *_playbook_formula_assessments(playbook, validation),
            _base_ledger_assessment(base_ledger, base_ledger_meta),
            _holdout_assessment(holdout, holdout_meta),
        ]
        blockers = sorted({blocker for row in prerequisites for blocker in _as_list(row.get("blockers"))})
        status = "ready_for_research_only_implementation_approval_question" if not blockers else "blocked_post_event_iv_crush_replay_readiness"

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "status": status,
        "concept_id": CONCEPT_ID,
        "structure": EXPECTED_STRUCTURE,
        **READ_ONLY_FLAGS,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "purpose": "Read-only readiness audit for the preregistered post-event IV-crush index iron condor/butterfly sleeve.",
        "preregistration_validation": validation,
        "critical_prerequisites": prerequisites,
        "blockers": blockers,
        "remaining_blockers": blockers,
        "smallest_next_blocker_clearing_slice": blockers[0] if blockers else None,
        "source_artifacts": {
            "preregistered_playbook": playbook_meta,
            "macro_event_calendar": calendar_meta,
            "feature_store": features_meta,
            "point_in_time_vix_bucket": vix_meta,
            "quote_capability": quote_meta,
            "base_clean_stack_identity_ledger": base_ledger_meta,
            "holdout_contract": holdout_meta,
        },
        "allowed_next_step": "send readiness back to GPT-5.5 Pro" if blockers else "ask GPT-5.5 Pro for one bounded research-only implementation task inside the current non-live, non-broker research posture",
    }
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Post-Event IV-Crush Replay Readiness",
        "",
        f"- Generated: `{report['generated_at_utc']}`.",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report['concept_id']}`.",
        f"- Structure: `{report['structure']}`.",
        f"- Accepted profitability: `{report['accepted_profitability']}`.",
        f"- Historical replay performed: `{report['historical_replay_performed']}`.",
        f"- Quotes imported: `{report['quotes_imported']}`.",
        f"- Protected holdout consumed: `{report['protected_holdout_consumed']}`.",
        "",
        "This report is a read-only prerequisite audit. It does not implement scanner or playbook logic, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.",
        "",
        "## Blockers",
        "",
    ]
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- None.")
    lines.extend(["", "## Critical Prerequisites", "", "| Prerequisite | Status | Blockers |", "|---|---:|---|"])
    for row in _as_list(report.get("critical_prerequisites")):
        blocker_text = ", ".join(f"`{blocker}`" for blocker in _as_list(row.get("blockers"))) or "None"
        lines.append(f"| {row.get('label')} | `{row.get('status')}` | {blocker_text} |")
    lines.extend(["", "## Source Artifacts", "", "| Artifact | Status | Path |", "|---|---:|---|"])
    for name, meta in _as_dict(report.get("source_artifacts")).items():
        lines.append(f"| `{name}` | `{meta.get('status')}` | `{meta.get('path')}` |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    latest_json = output_dir / "latest.json"
    stamped_json = output_dir / f"{stamp}.json"
    latest_md = output_dir / "latest.md"
    markdown = _markdown(report)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    latest_json.write_text(payload, encoding="utf8")
    stamped_json.write_text(payload, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return {
        "latest_json": _rel(latest_json),
        "stamped_json": _rel(stamped_json),
        "latest_md": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only post-event IV-crush replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--macro-event-calendar", type=Path, default=DEFAULT_MACRO_EVENT_CALENDAR)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--vix-bucket", type=Path, default=DEFAULT_VIX_BUCKET)
    parser.add_argument("--quote-capability", type=Path, default=DEFAULT_QUOTE_CAPABILITY)
    parser.add_argument("--base-ledger", type=Path, default=DEFAULT_BASE_LEDGER)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        macro_event_calendar_path=args.macro_event_calendar,
        feature_store_path=args.feature_store,
        vix_bucket_path=args.vix_bucket,
        quote_capability_path=args.quote_capability,
        base_ledger_path=args.base_ledger,
        holdout_contract_path=args.holdout_contract,
    )
    artifacts: dict[str, str] = {}
    if not args.no_write:
        artifacts = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
        report["written_artifacts"] = artifacts
    if args.json:
        print(json.dumps({"report": report, "artifacts": artifacts}, indent=2, sort_keys=True))
    return 0 if report["status"] in {"blocked_post_event_iv_crush_replay_readiness", "ready_for_research_only_implementation_approval_question"} else 1


if __name__ == "__main__":
    sys.exit(main())
