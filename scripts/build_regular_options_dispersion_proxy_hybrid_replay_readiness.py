from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_dispersion_proxy_hybrid_replay_readiness"
CONCEPT_ID = "index_constituent_dispersion_proxy_defined_risk_hybrid_v1"
EXPECTED_STRUCTURE = "defined_risk_index_constituent_debit_credit_hybrid_pairs_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-dispersion-proxy-hybrid-playbook"
    / "latest.json"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_SOURCE_QUALITY_POLICY = ROOT / "data" / "contracts" / "regular-options-source-quality-scope-policy.json"
DEFAULT_POINT_IN_TIME_VIX_BUCKET = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
)
DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-point-in-time-dispersion-concentration-proxy"
    / "latest.json"
)
DEFAULT_FORWARD_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-dispersion-proxy-hybrid-replay-readiness.md"

DEFAULT_EVIDENCE_PATHS = (
    ROOT / "scripts" / "build_regular_options_feature_store.py",
    ROOT / "scripts" / "build_regular_options_structure_specific_harness.py",
    ROOT / "scripts" / "run_regular_options_multilane_portfolio.py",
    ROOT / "scripts" / "build_regular_options_vrp_credit_spread_structure_harness.py",
    ROOT / "scripts" / "build_regular_options_term_structure_calendar_structure_harness.py",
    ROOT / "scripts" / "build_regular_options_skew_broken_wing_put_fly_structure_harness.py",
    ROOT / "python-backend" / "proof_contract.py",
    ROOT / "docs" / "regular-options-feature-store.md",
    ROOT / "docs" / "proof-evidence-contract.md",
    ROOT / "docs" / "forward-holdout-contract.md",
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "lane_implementation_performed": False,
    "replay_performed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_run_replay",
    "do_not_generate_trades",
    "do_not_import_quotes",
    "do_not_fetch_external_data",
    "do_not_mutate_options_history_db",
    "do_not_append_forward_cohort_rows",
    "do_not_overwrite_canonical_evidence_stores",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_allow_undefined_or_uncapped_pair_structures",
    "do_not_invent_point_in_time_dispersion_vix_or_known_at_inputs",
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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("last_updated")
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id") or payload.get("policy_id")
    meta["status_value"] = payload.get("status")
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


def _preregistration_valid(playbook: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    concept = _as_dict(playbook.get("concept"))
    if playbook.get("concept_id") != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("structure") != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    if playbook.get("historical_replay_performed") is not False:
        reasons.append("historical_replay_performed_not_false")
    if playbook.get("lane_implementation_performed") is not False:
        reasons.append("lane_implementation_performed_not_false")
    if playbook.get("undefined_or_uncapped_pair_risk_allowed") is not False:
        reasons.append("undefined_or_uncapped_pair_risk_not_false")
    if concept and concept.get("undefined_or_uncapped_pair_risk_allowed") is not False:
        reasons.append("concept_undefined_or_uncapped_pair_risk_not_false")
    return not reasons, reasons


def _feature_store_status(feature_store: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    required_symbols = {"SPY", "QQQ", "AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
    payload_text = json.dumps(feature_store, sort_keys=True).lower()
    symbol_hits = [symbol for symbol in required_symbols if symbol.lower() in payload_text]
    source_ready = "thetadata_opra_nbbo_1m" in payload_text and (
        "trusted_intraday_opra_nbbo" in payload_text or "tradable_after_time" in payload_text
    )
    if len(symbol_hits) == len(required_symbols) and source_ready:
        status = "ready"
    elif symbol_hits or source_ready:
        status = "partial"
    else:
        status = "missing"
    return status, [{"path": _rel(DEFAULT_FEATURE_STORE), "matched_terms": symbol_hits + (["trusted_opra_nbbo"] if source_ready else [])}]


def _source_quality_status(source_quality: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    text = json.dumps(source_quality, sort_keys=True).lower()
    terms = [
        term
        for term in (
            "cvx_zero_bid_tradability_candidate_scope_v1",
            "zero_bid_tradability_floor_failure",
            "do_not_lower_90pct_executable_quote_floor",
        )
        if term in text
    ]
    return ("ready" if len(terms) >= 3 else "partial" if terms else "missing"), [
        {"path": _rel(DEFAULT_SOURCE_QUALITY_POLICY), "matched_terms": terms}
    ]


def _vix_status(vix_bucket: dict[str, Any], vix_meta: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [{"path": vix_meta["path"], "matched_terms": [str(vix_bucket.get("status"))]}]
    if vix_bucket.get("point_in_time_vix_low_mid_bucket_available") is True and vix_bucket.get("status") not in (None, "missing"):
        return "ready", None, evidence, "Point-in-time VIX bucket artifact is available."
    if vix_meta.get("status") == "loaded":
        return "blocked", "point_in_time_vix_bucket_blocked", evidence, "Existing VIX bucket artifact is loaded but not ready."
    return "missing", "missing_point_in_time_vix_bucket_artifact", evidence, "No point-in-time VIX bucket artifact is available."


def _dispersion_input_status(
    dispersion_proxy: dict[str, Any],
    dispersion_proxy_meta: dict[str, Any],
) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [
        {
            "path": dispersion_proxy_meta["path"],
            "matched_terms": [str(dispersion_proxy.get("status") or dispersion_proxy_meta.get("status"))],
        }
    ]
    if (
        dispersion_proxy_meta.get("status") == "loaded"
        and dispersion_proxy.get("status") == "point_in_time_dispersion_concentration_proxy_available"
        and not dispersion_proxy.get("blockers")
    ):
        return "ready", None, evidence, "Point-in-time dispersion/concentration proxy artifact is available."
    if dispersion_proxy_meta.get("status") == "loaded":
        return (
            "blocked",
            "missing_dispersion_or_concentration_proxy_inputs",
            evidence,
            "Dispersion/concentration proxy artifact is loaded but not coverage-valid.",
        )
    return (
        "missing",
        "missing_dispersion_or_concentration_proxy_inputs",
        evidence,
        "No point-in-time dispersion/concentration proxy artifact is available.",
    )


def _build_prerequisite_assessments(
    *,
    texts: dict[str, str],
    feature_store: dict[str, Any],
    source_quality: dict[str, Any],
    dispersion_proxy: dict[str, Any],
    dispersion_proxy_meta: dict[str, Any],
    vix_bucket: dict[str, Any],
    vix_meta: dict[str, Any],
    holdout_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    pair_entry_exact = _find_terms(texts, ("pair_entry_cashflow", "credit_side_entry - debit_side_entry"))
    pair_entry_partial = _find_terms(texts, ("debit_side_entry", "credit_side_entry", "pair_exit_value"))
    side_aware_exact = _find_terms(
        texts,
        (
            "debit_side_entry",
            "debit_side_exit_value",
            "credit_side_entry",
            "credit_side_exit_debit",
            "pair_net_pnl_usd",
        ),
    )
    pair_risk_exact = _find_terms(texts, ("pair_max_loss_usd", "required_collateral_usd", "rejected_undefined_or_uncapped_risk"))
    pair_risk_partial = _find_terms(texts, ("max_loss_usd", "collateral", "undefined-risk"))
    denominator_exact = _find_terms(
        texts,
        (
            "rejected_dispersion_proxy_missing",
            "rejected_pair_universe_mismatch",
            "rejected_undefined_or_uncapped_risk",
            "missing_leg_quote",
            "zero_bid_or_untradable",
            "exact_entry_captured",
            "assignment_or_expiration_blocked",
            "exact_exit_captured",
            "missing_exit",
        ),
    )
    assignment_exact = _find_terms(texts, ("assignment_or_expiration_blocked", "assignment and expiration classifier"))
    assignment_partial = _find_terms(texts, ("assignment", "expiration", "settlement"))
    strict_new_exact = _find_terms(texts, ("strict-new dedupe", "strict_new_dedupe_ready", "157-row clean base stack"))
    proof_exact = _find_terms(texts, ("proof_eligible", "trusted_intraday_opra_nbbo", "production proof"))
    feature_status, feature_evidence = _feature_store_status(feature_store)
    cvx_status, cvx_evidence = _source_quality_status(source_quality)
    dispersion_status, dispersion_blocker, dispersion_evidence, dispersion_note = _dispersion_input_status(
        dispersion_proxy,
        dispersion_proxy_meta,
    )
    vix_status, vix_blocker, vix_evidence, vix_note = _vix_status(vix_bucket, vix_meta)
    holdout_ready = holdout_meta.get("status") == "loaded"

    return [
        _assessment(
            prerequisite_id="point_in_time_dispersion_concentration_inputs",
            label="Point-in-time dispersion or concentration proxy inputs",
            critical=True,
            status=dispersion_status,
            blocker=dispersion_blocker,
            evidence=dispersion_evidence,
            note=dispersion_note,
        ),
        _assessment(
            prerequisite_id="point_in_time_vix_bucket",
            label="Point-in-time VIX bucket requirement",
            critical=True,
            status=vix_status,
            blocker=vix_blocker,
            evidence=vix_evidence,
            note=vix_note,
        ),
        _assessment(
            prerequisite_id="pair_construction_rules",
            label="Index/constituent pair construction and universe rules",
            critical=True,
            status=_status_from_hits(exact_hits=pair_entry_exact, partial_hits=pair_entry_partial),
            blocker="missing_pair_construction_engine",
            evidence=pair_entry_exact or pair_entry_partial,
            note="The future replay needs deterministic pair sizing, leg quantities, DTE, strikes, and variant selection.",
        ),
        _assessment(
            prerequisite_id="side_aware_all_leg_pair_pricing",
            label="Side-aware all-leg pair pricing",
            critical=True,
            status="ready" if _matched_term_count(side_aware_exact) >= 5 else "partial" if side_aware_exact else "missing",
            blocker="missing_side_aware_all_leg_pair_pricing",
            evidence=side_aware_exact,
            note="Readiness requires debit and credit side entry/exit formulas plus pair net USD P&L after costs.",
        ),
        _assessment(
            prerequisite_id="pair_max_loss_collateral",
            label="Pair max-loss and required collateral convention",
            critical=True,
            status=_status_from_hits(exact_hits=pair_risk_exact, partial_hits=pair_risk_partial),
            blocker="missing_pair_max_loss_or_collateral_convention",
            evidence=pair_risk_exact or pair_risk_partial,
            note="Undefined or uncapped pair risk must be impossible before replay.",
        ),
        _assessment(
            prerequisite_id="assignment_expiration_classifier",
            label="Assignment, expiration, and settlement classifier",
            critical=True,
            status=_status_from_hits(exact_hits=assignment_exact, partial_hits=assignment_partial),
            blocker="missing_assignment_expiration_classifier",
            evidence=assignment_exact or assignment_partial,
            note="Every leg needs policy-defined assignment/expiration/settlement handling.",
        ),
        _assessment(
            prerequisite_id="quote_surface_availability",
            label="Trusted OPRA/NBBO quote surface for index and constituent legs",
            critical=True,
            status=feature_status,
            blocker="missing_dispersion_pair_quote_surface",
            evidence=feature_evidence,
            note="Feature-store readiness requires trusted bid/ask rows and tradable_after_time discipline for all research symbols.",
        ),
        _assessment(
            prerequisite_id="full_denominator_mapping",
            label="Full denominator mapping",
            critical=True,
            status="ready" if _matched_term_count(denominator_exact) >= 8 else "partial" if denominator_exact else "missing",
            blocker="missing_full_denominator_mapping",
            evidence=denominator_exact,
            note="Rows must include no-candidate, rejected, missing, zero-bid, open, assignment/expiration, exact-exit, and missing-exit statuses.",
        ),
        _assessment(
            prerequisite_id="strict_new_dedupe",
            label="Strict-new dedupe versus the clean base stack",
            critical=True,
            status="ready" if strict_new_exact else "missing",
            blocker="missing_strict_new_dedupe",
            evidence=strict_new_exact,
            note="Future pair rows must be deduped against the existing clean base stack before count claims.",
        ),
        _assessment(
            prerequisite_id="cvx_source_quality_handling",
            label="CVX source-quality handling",
            critical=True,
            status=cvx_status,
            blocker="missing_cvx_source_quality_scope",
            evidence=cvx_evidence,
            note="CVX must remain blocked or excluded under a preregistered rule until source-quality scope clears.",
        ),
        _assessment(
            prerequisite_id="protected_holdout_guard",
            label="Protected-holdout guard",
            critical=True,
            status="ready" if holdout_ready else "missing",
            blocker="missing_protected_holdout_guard",
            evidence=[{"path": holdout_meta["path"], "matched_terms": [holdout_meta.get("status")]}],
            note="This readiness slice must not consume protected holdout.",
        ),
        _assessment(
            prerequisite_id="proof_boundary_labeling",
            label="Proof-boundary labeling",
            critical=True,
            status="ready" if proof_exact else "missing",
            blocker="missing_proof_boundary_labeling",
            evidence=proof_exact,
            note="Readiness cannot be treated as replay, forward proof, or profitability.",
        ),
    ]


def _overall_status(assessments: list[dict[str, Any]], prereg_valid: bool) -> str:
    if not prereg_valid:
        return "blocked_invalid_dispersion_proxy_hybrid_preregistration"
    if any(row["critical"] and row["status"] != "ready" for row in assessments):
        return "blocked_dispersion_proxy_hybrid_replay_readiness"
    return "dispersion_proxy_hybrid_replay_readiness_ready"


def _smallest_next_blocker(blockers: list[str]) -> str | None:
    priority = [
        "missing_dispersion_or_concentration_proxy_inputs",
        "point_in_time_vix_bucket_blocked",
        "missing_side_aware_all_leg_pair_pricing",
        "missing_pair_max_loss_or_collateral_convention",
        "missing_dispersion_pair_quote_surface",
    ]
    for item in priority:
        if item in blockers:
            return item
    return blockers[0] if blockers else None


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    source_quality_policy_path: Path = DEFAULT_SOURCE_QUALITY_POLICY,
    point_in_time_dispersion_concentration_proxy_path: Path = DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    forward_holdout_contract_path: Path = DEFAULT_FORWARD_HOLDOUT_CONTRACT,
    evidence_paths: tuple[Path, ...] | list[Path] = DEFAULT_EVIDENCE_PATHS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    feature_store, feature_store_meta = _load_json(feature_store_path, required=True)
    source_quality, source_quality_meta = _load_json(source_quality_policy_path, required=False)
    dispersion_proxy, dispersion_proxy_meta = _load_json(point_in_time_dispersion_concentration_proxy_path, required=False)
    vix_bucket, vix_bucket_meta = _load_json(point_in_time_vix_bucket_path, required=False)
    holdout_contract, holdout_meta = _load_json(forward_holdout_contract_path, required=False)
    texts, evidence_meta = _read_evidence(evidence_paths)
    if playbook:
        texts[_rel(preregistered_playbook_path)] = json.dumps(playbook, sort_keys=True)
    prereg_valid, prereg_reasons = (
        _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    )
    assessments = (
        _build_prerequisite_assessments(
            texts=texts,
            feature_store=feature_store,
            source_quality=source_quality,
            dispersion_proxy=dispersion_proxy,
            dispersion_proxy_meta=dispersion_proxy_meta,
            vix_bucket=vix_bucket,
            vix_meta=vix_bucket_meta,
            holdout_meta=holdout_meta,
        )
        if prereg_valid
        else []
    )
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
        "scope": "read_only_dispersion_proxy_hybrid_replay_readiness_audit",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "undefined_or_uncapped_pair_risk_allowed": playbook.get("undefined_or_uncapped_pair_risk_allowed"),
        "source_artifacts": {
            "preregistered_dispersion_proxy_hybrid_playbook": playbook_meta,
            "feature_store": feature_store_meta,
            "source_quality_policy": source_quality_meta,
            "point_in_time_dispersion_concentration_proxy": dispersion_proxy_meta,
            "point_in_time_vix_bucket": vix_bucket_meta,
            "forward_holdout_contract": holdout_meta,
            "evidence_files": evidence_meta,
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_concept_id": CONCEPT_ID,
            "required_status": "preregistered_design_only",
            "required_structure": EXPECTED_STRUCTURE,
            "undefined_or_uncapped_pair_risk_allowed_required": False,
        },
        "critical_prerequisites": assessments,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": _smallest_next_blocker(blockers),
        "holdout_contract_loaded": bool(holdout_contract),
        "allowed_next_step": (
            "Return this readiness artifact to GPT-5.5 Pro for continue/stop. If ready, the next slice is a separate "
            "bounded no-write replay decision. If blocked, park this branch on the exact blockers and select another "
            "research-only structure-readiness branch."
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
        if report.get("undefined_or_uncapped_pair_risk_allowed") is not False:
            raise ValueError("undefined_or_uncapped_pair_risk_allowed must be false")
        required_ids = {
            "point_in_time_dispersion_concentration_inputs",
            "point_in_time_vix_bucket",
            "pair_construction_rules",
            "side_aware_all_leg_pair_pricing",
            "pair_max_loss_collateral",
            "assignment_expiration_classifier",
            "quote_surface_availability",
            "full_denominator_mapping",
            "strict_new_dedupe",
            "cvx_source_quality_handling",
            "protected_holdout_guard",
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
        "# Regular Options Dispersion-Proxy Hybrid Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_replay_readiness.py`. It is a read-only readiness audit for a preregistered index-versus-constituent defined-risk hybrid pair concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Replay performed: `{_fmt_bool(report['replay_performed'])}`.",
        f"- Smallest next blocker-clearing slice: `{report.get('smallest_next_blocker_clearing_slice')}`.",
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
    lines.extend(["", "## Boundary", "", report["allowed_next_step"], "", "## Forbidden Actions", ""])
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
    parser = argparse.ArgumentParser(description="Build a read-only dispersion-proxy hybrid replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--point-in-time-dispersion-concentration-proxy", type=Path, default=DEFAULT_POINT_IN_TIME_DISPERSION_CONCENTRATION_PROXY)
    parser.add_argument("--point-in-time-vix-bucket", type=Path, default=DEFAULT_POINT_IN_TIME_VIX_BUCKET)
    parser.add_argument("--forward-holdout-contract", type=Path, default=DEFAULT_FORWARD_HOLDOUT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        feature_store_path=args.feature_store,
        source_quality_policy_path=args.source_quality_policy,
        point_in_time_dispersion_concentration_proxy_path=args.point_in_time_dispersion_concentration_proxy,
        point_in_time_vix_bucket_path=args.point_in_time_vix_bucket,
        forward_holdout_contract_path=args.forward_holdout_contract,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["preregistration_validation"]["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
