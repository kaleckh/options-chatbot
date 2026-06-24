from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_flow_extreme_ratio_backspread_replay_readiness"
CONCEPT_ID = "index_flow_extreme_mean_reversion_ratio_backspread_v1"
EXPECTED_STRUCTURE = "defined_risk_ratio_spreads_or_backspreads_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-flow-extreme-ratio-backspread-playbook"
    / "latest.json"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_POINT_IN_TIME_VIX_BUCKET = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
)
DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-flow-extreme-input" / "latest.json"
)
DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY = (
    ROOT / "data" / "profitability-lab" / "regular-options-multi-leg-side-aware-pricing-capability" / "latest.json"
)
DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE = (
    ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-denominator-dedupe-bridge" / "latest.json"
)
DEFAULT_FORWARD_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-ratio-backspread-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-flow-extreme-ratio-backspread-replay-readiness.md"

DEFAULT_EVIDENCE_PATHS = (
    ROOT / "scripts" / "build_regular_options_feature_store.py",
    ROOT / "scripts" / "build_regular_options_structure_specific_harness.py",
    ROOT / "scripts" / "build_regular_options_vrp_credit_spread_structure_harness.py",
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
    "replay_performed": False,
    "lane_implementation_performed": False,
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
    "do_not_allow_naked_short_option_structures",
    "do_not_allow_undefined_or_uncapped_ratio_backspread_structures",
    "do_not_invent_point_in_time_flow_vix_breadth_event_known_at_or_threshold_inputs",
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
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
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
    if playbook.get("undefined_risk_allowed") is not False:
        reasons.append("undefined_risk_allowed_not_false")
    if concept and concept.get("undefined_risk_allowed") is not False:
        reasons.append("concept_undefined_risk_allowed_not_false")
    if concept and concept.get("naked_ratio_spreads_allowed") is not False:
        reasons.append("concept_naked_ratio_spreads_allowed_not_false")
    return not reasons, reasons


def _feature_store_status(feature_store: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    text = json.dumps(feature_store, sort_keys=True).lower()
    required_symbols = ("spy", "qqq")
    symbol_hits = [symbol.upper() for symbol in required_symbols if symbol in text]
    source_ready = "thetadata_opra_nbbo_1m" in text and (
        "trusted_intraday_opra_nbbo" in text or "tradable_after_time" in text
    )
    if len(symbol_hits) == len(required_symbols) and source_ready:
        status = "ready"
    elif symbol_hits or source_ready:
        status = "partial"
    else:
        status = "missing"
    return status, [{"path": _rel(DEFAULT_FEATURE_STORE), "matched_terms": symbol_hits + (["trusted_opra_nbbo"] if source_ready else [])}]


def _vix_status(vix_bucket: dict[str, Any], vix_meta: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [{"path": vix_meta["path"], "matched_terms": [str(vix_bucket.get("status"))]}]
    if vix_bucket.get("point_in_time_vix_low_mid_bucket_available") is True:
        return "ready", None, evidence, "Point-in-time VIX bucket artifact is available."
    if vix_meta.get("status") == "loaded":
        return "blocked", "missing_point_in_time_vix_bucket", evidence, "Existing VIX bucket artifact is loaded but blocked."
    return "missing", "missing_point_in_time_vix_bucket_artifact", evidence, "No point-in-time VIX bucket artifact is available."


def _flow_input_status(flow_input: dict[str, Any], flow_input_meta: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [
        {
            "path": flow_input_meta["path"],
            "matched_terms": [str(flow_input.get("status")), str(flow_input.get("report_id"))],
        }
    ]
    if flow_input_meta.get("status") != "loaded":
        return "missing", "missing_point_in_time_flow_extreme_input", evidence, "No point-in-time flow-extreme input artifact is available."
    if flow_input.get("report_id") != "regular_options_point_in_time_flow_extreme_input":
        return "blocked", "missing_point_in_time_flow_extreme_input", evidence, "Flow-extreme input artifact has the wrong report_id."
    unsafe_flags = [
        flag
        for flag in (
            "accepted_profitability",
            "historical_replay_performed",
            "historical_rows_are_forward_proof",
            "live_validation_enabled",
            "auto_track_enabled",
            "broker_order_allowed",
            "quotes_imported",
            "evidence_stores_mutated",
            "protected_holdout_consumed",
            "production_scanner_changed",
            "strategy_logic_changed",
            "stops_changed",
            "sizing_changed",
            "proof_bars_changed",
            "promotion_ready",
        )
        if flow_input.get(flag) is not False
    ]
    if unsafe_flags:
        evidence[0]["unsafe_flags"] = unsafe_flags
        return "blocked", "missing_point_in_time_flow_extreme_input", evidence, "Flow-extreme input artifact has unsafe flags."
    if flow_input.get("status") == "point_in_time_flow_extreme_input_available" and not flow_input.get("blockers"):
        return "ready", None, evidence, "Point-in-time flow-extreme input artifact is available."
    evidence[0]["blockers"] = flow_input.get("blockers")
    return "blocked", "missing_point_in_time_flow_extreme_input", evidence, "Existing flow-extreme input artifact is loaded but blocked."


def _pricing_capability_status(
    capability: dict[str, Any], capability_meta: dict[str, Any]
) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [
        {
            "path": capability_meta["path"],
            "matched_terms": [str(capability.get("status")), str(capability.get("report_id"))],
        }
    ]
    if capability_meta.get("status") != "loaded":
        return "missing", "missing_side_aware_ratio_backspread_pricing", evidence, "No multi-leg side-aware pricing capability artifact is available."
    unsafe_flags = [
        flag
        for flag in (
            "accepted_profitability",
            "historical_replay_performed",
            "historical_rows_are_forward_proof",
            "live_validation_enabled",
            "auto_track_enabled",
            "broker_order_allowed",
            "quotes_imported",
            "evidence_stores_mutated",
            "options_history_db_mutated",
            "protected_holdout_consumed",
            "production_scanner_changed",
            "strategy_logic_changed",
            "stops_changed",
            "sizing_changed",
            "proof_bars_changed",
            "scanner_strategy_stop_sizing_or_proof_bar_changed",
            "promotion_ready",
        )
        if capability.get(flag) is not False
    ]
    if capability.get("report_id") != "regular_options_multi_leg_side_aware_pricing_capability":
        evidence[0]["reason"] = "wrong_report_id"
        return "blocked", "missing_side_aware_ratio_backspread_pricing", evidence, "Pricing capability artifact has the wrong report_id."
    if capability.get("fixture_source_not_proof_eligible") is not True:
        evidence[0]["reason"] = "fixture_source_not_proof_eligible_not_true"
        return "blocked", "missing_side_aware_ratio_backspread_pricing", evidence, "Pricing capability artifact does not isolate fixture output from proof."
    if unsafe_flags:
        evidence[0]["unsafe_flags"] = unsafe_flags
        return "blocked", "missing_side_aware_ratio_backspread_pricing", evidence, "Pricing capability artifact has unsafe flags."
    ratio = _as_dict(_as_dict(capability.get("structure_support")).get("ratio_backspread_bounded"))
    evidence[0]["ratio_backspread_bounded_status"] = ratio.get("status")
    evidence[0]["pricing_capability_blockers"] = capability.get("pricing_capability_blockers")
    if (
        capability.get("status") == "multi_leg_side_aware_pricing_capability_available"
        and ratio.get("status") == "available"
        and ratio.get("denominator_mapping_status") == "ready"
        and not capability.get("pricing_capability_blockers")
    ):
        return "ready", None, evidence, "Side-aware bounded ratio/backspread pricing capability is available."
    return "blocked", "missing_side_aware_ratio_backspread_pricing", evidence, "Pricing capability artifact is loaded but blocked."


def _denominator_dedupe_bridge_status(
    bridge: dict[str, Any], bridge_meta: dict[str, Any]
) -> tuple[tuple[str, str | None, list[dict[str, Any]], str], tuple[str, str | None, list[dict[str, Any]], str]]:
    evidence = [
        {
            "path": bridge_meta["path"],
            "matched_terms": [str(bridge.get("status")), str(bridge.get("report_id"))],
            "full_denominator_mapping_status": bridge.get("full_denominator_mapping_status"),
            "strict_new_dedupe_status": bridge.get("strict_new_dedupe_status"),
            "bridge_blockers": bridge.get("bridge_blockers"),
        }
    ]
    if bridge_meta.get("status") != "loaded":
        full = (
            "missing",
            "missing_full_denominator_mapping",
            evidence,
            "No flow-extreme denominator/dedupe bridge artifact is available.",
        )
        strict = (
            "missing",
            "missing_strict_new_dedupe",
            evidence,
            "No flow-extreme denominator/dedupe bridge artifact is available.",
        )
        return full, strict
    unsafe_flags = [
        flag
        for flag in (
            "accepted_profitability",
            "historical_replay_performed",
            "replay_performed",
            "historical_rows_are_forward_proof",
            "live_validation_enabled",
            "auto_track_enabled",
            "broker_order_allowed",
            "quotes_imported",
            "evidence_stores_mutated",
            "protected_holdout_consumed",
            "production_scanner_changed",
            "strategy_logic_changed",
            "stops_changed",
            "sizing_changed",
            "proof_bars_changed",
            "promotion_ready",
        )
        if bridge.get(flag) is not False
    ]
    invalid = (
        bridge.get("report_id") != "regular_options_flow_extreme_denominator_dedupe_bridge"
        or bridge.get("concept_id") != CONCEPT_ID
        or bridge.get("structure") != "ratio_backspread_bounded"
        or bridge.get("fixture_source_not_proof_eligible") is not True
        or bridge.get("proof_row_count") != 0
        or bool(unsafe_flags)
    )
    if invalid:
        evidence[0]["unsafe_flags"] = unsafe_flags
        full = (
            "blocked",
            "missing_full_denominator_mapping",
            evidence,
            "Denominator/dedupe bridge artifact is invalid or unsafe.",
        )
        strict = (
            "blocked",
            "missing_strict_new_dedupe",
            evidence,
            "Denominator/dedupe bridge artifact is invalid or unsafe.",
        )
        return full, strict
    bridge_blockers = set(str(item) for item in _as_list(bridge.get("bridge_blockers")))
    full_ready = bridge.get("full_denominator_mapping_status") == "ready" and "missing_denominator_status" not in bridge_blockers
    strict_ready = bridge.get("strict_new_dedupe_status") == "ready" and not bridge_blockers
    full = (
        "ready" if full_ready else "blocked",
        None if full_ready else "missing_full_denominator_mapping",
        evidence,
        "Flow-extreme full denominator mapping is ready." if full_ready else "Flow-extreme denominator mapping remains blocked.",
    )
    strict = (
        "ready" if strict_ready else "blocked",
        None if strict_ready else "missing_strict_new_dedupe",
        evidence,
        "Flow-extreme strict-new dedupe is ready."
        if strict_ready
        else "Flow-extreme strict-new dedupe remains blocked; bridge blockers are preserved.",
    )
    return full, strict


def _build_prerequisite_assessments(
    *,
    texts: dict[str, str],
    feature_store: dict[str, Any],
    flow_input: dict[str, Any],
    flow_input_meta: dict[str, Any],
    pricing_capability: dict[str, Any],
    pricing_capability_meta: dict[str, Any],
    denominator_dedupe_bridge: dict[str, Any],
    denominator_dedupe_bridge_meta: dict[str, Any],
    vix_bucket: dict[str, Any],
    vix_meta: dict[str, Any],
    holdout_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    flow_status, flow_blocker, flow_evidence, flow_note = _flow_input_status(flow_input, flow_input_meta)
    pricing_status, pricing_blocker, pricing_evidence, pricing_note = _pricing_capability_status(
        pricing_capability, pricing_capability_meta
    )
    (
        (denominator_status, denominator_blocker, denominator_evidence, denominator_note),
        (strict_new_status, strict_new_blocker, strict_new_evidence, strict_new_note),
    ) = _denominator_dedupe_bridge_status(denominator_dedupe_bridge, denominator_dedupe_bridge_meta)
    vix_status, vix_blocker, vix_evidence, vix_note = _vix_status(vix_bucket, vix_meta)
    risk_exact = _find_terms(texts, ("max_loss_usd", "required collateral", "rejected_undefined_risk"))
    risk_partial = _find_terms(texts, ("max_loss", "collateral", "defined-risk cap", "undefined-risk"))
    assignment_exact = _find_terms(texts, ("assignment_or_expiration_blocked", "assignment and expiration classifier"))
    assignment_partial = _find_terms(texts, ("assignment", "expiration", "settlement"))
    proof_exact = _find_terms(texts, ("proof_eligible", "trusted_intraday_opra_nbbo", "production proof"))
    feature_status, feature_evidence = _feature_store_status(feature_store)
    holdout_ready = holdout_meta.get("status") == "loaded"

    return [
        _assessment(
            prerequisite_id="point_in_time_flow_extreme_inputs",
            label="Point-in-time flow or overextension inputs",
            critical=True,
            status=flow_status,
            blocker=flow_blocker,
            evidence=flow_evidence,
            note=flow_note,
        ),
        _assessment(
            prerequisite_id="point_in_time_vix_bucket",
            label="Point-in-time VIX bucket",
            critical=True,
            status=vix_status,
            blocker=vix_blocker,
            evidence=vix_evidence,
            note=vix_note,
        ),
        _assessment(
            prerequisite_id="side_aware_ratio_backspread_pricing",
            label="Side-aware ratio/backspread all-leg pricing",
            critical=True,
            status=pricing_status,
            blocker=pricing_blocker,
            evidence=pricing_evidence,
            note=pricing_note,
        ),
        _assessment(
            prerequisite_id="defined_risk_max_loss_collateral",
            label="Defined-risk max-loss and collateral convention",
            critical=True,
            status=_status_from_hits(exact_hits=risk_exact, partial_hits=risk_partial),
            blocker="missing_defined_risk_max_loss_or_collateral",
            evidence=risk_exact or risk_partial,
            note="Naked short, uncapped, or undefined-risk ratio/backspread exposure must be rejected before replay.",
        ),
        _assessment(
            prerequisite_id="assignment_expiration_classifier",
            label="Assignment, expiration, and settlement classifier",
            critical=True,
            status=_status_from_hits(exact_hits=assignment_exact, partial_hits=assignment_partial),
            blocker="missing_assignment_expiration_classifier",
            evidence=assignment_exact or assignment_partial,
            note="Every leg needs policy-defined assignment, expiration, and settlement handling.",
        ),
        _assessment(
            prerequisite_id="quote_surface_availability",
            label="Trusted OPRA/NBBO quote surface for SPY/QQQ",
            critical=True,
            status=feature_status,
            blocker="missing_flow_extreme_quote_surface",
            evidence=feature_evidence,
            note="Readiness only checks existing local trusted quote-surface metadata; it does not import quotes.",
        ),
        _assessment(
            prerequisite_id="full_denominator_mapping",
            label="Full denominator mapping",
            critical=True,
            status=denominator_status,
            blocker=denominator_blocker,
            evidence=denominator_evidence,
            note=denominator_note,
        ),
        _assessment(
            prerequisite_id="strict_new_dedupe",
            label="Strict-new dedupe versus the clean base stack",
            critical=True,
            status=strict_new_status,
            blocker=strict_new_blocker,
            evidence=strict_new_evidence,
            note=strict_new_note,
        ),
        _assessment(
            prerequisite_id="protected_holdout_guard",
            label="Protected-holdout guard",
            critical=True,
            status="ready" if holdout_ready else "missing",
            blocker="missing_protected_holdout_guard",
            evidence=[{"path": holdout_meta["path"], "matched_terms": [holdout_meta.get("status")]}],
            note="The readiness slice must not consume protected holdout.",
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
        return "blocked_invalid_flow_extreme_ratio_backspread_preregistration"
    if any(row["critical"] and row["status"] != "ready" for row in assessments):
        return "blocked_flow_extreme_ratio_backspread_replay_readiness"
    return "flow_extreme_ratio_backspread_replay_readiness_ready"


def _smallest_next_blocker(blockers: list[str]) -> str | None:
    priority = [
        "missing_point_in_time_flow_extreme_input",
        "missing_point_in_time_vix_bucket",
        "missing_side_aware_ratio_backspread_pricing",
        "missing_defined_risk_max_loss_or_collateral",
        "missing_full_denominator_mapping",
    ]
    for item in priority:
        if item in blockers:
            return item
    return blockers[0] if blockers else None


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    point_in_time_flow_extreme_input_path: Path = DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT,
    multi_leg_side_aware_pricing_capability_path: Path = DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY,
    flow_extreme_denominator_dedupe_bridge_path: Path = DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    forward_holdout_contract_path: Path = DEFAULT_FORWARD_HOLDOUT_CONTRACT,
    evidence_paths: tuple[Path, ...] | list[Path] = DEFAULT_EVIDENCE_PATHS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    feature_store, feature_store_meta = _load_json(feature_store_path, required=True)
    flow_input, flow_input_meta = _load_json(point_in_time_flow_extreme_input_path, required=False)
    pricing_capability, pricing_capability_meta = _load_json(multi_leg_side_aware_pricing_capability_path, required=False)
    denominator_dedupe_bridge, denominator_dedupe_bridge_meta = _load_json(
        flow_extreme_denominator_dedupe_bridge_path,
        required=False,
    )
    vix_bucket, vix_bucket_meta = _load_json(point_in_time_vix_bucket_path, required=False)
    holdout_contract, holdout_meta = _load_json(forward_holdout_contract_path, required=False)
    texts, evidence_meta = _read_evidence(evidence_paths)
    prereg_valid, prereg_reasons = (
        _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    )
    assessments = (
        _build_prerequisite_assessments(
            texts=texts,
            feature_store=feature_store,
            flow_input=flow_input,
            flow_input_meta=flow_input_meta,
            pricing_capability=pricing_capability,
            pricing_capability_meta=pricing_capability_meta,
            denominator_dedupe_bridge=denominator_dedupe_bridge,
            denominator_dedupe_bridge_meta=denominator_dedupe_bridge_meta,
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
        "scope": "read_only_flow_extreme_ratio_backspread_replay_readiness_audit",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "undefined_risk_allowed": playbook.get("undefined_risk_allowed"),
        "naked_ratio_spreads_allowed": _as_dict(playbook.get("concept")).get("naked_ratio_spreads_allowed"),
        "source_artifacts": {
            "preregistered_flow_extreme_ratio_backspread_playbook": playbook_meta,
            "feature_store": feature_store_meta,
            "point_in_time_flow_extreme_input": flow_input_meta,
            "multi_leg_side_aware_pricing_capability": pricing_capability_meta,
            "flow_extreme_denominator_dedupe_bridge": denominator_dedupe_bridge_meta,
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
            "undefined_risk_allowed_required": False,
            "naked_ratio_spreads_allowed_required": False,
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
        if report.get("undefined_risk_allowed") is not False:
            raise ValueError("undefined_risk_allowed must be false")
        if report.get("naked_ratio_spreads_allowed") is not False:
            raise ValueError("naked_ratio_spreads_allowed must be false")
        required_ids = {
            "point_in_time_flow_extreme_inputs",
            "point_in_time_vix_bucket",
            "side_aware_ratio_backspread_pricing",
            "defined_risk_max_loss_collateral",
            "assignment_expiration_classifier",
            "quote_surface_availability",
            "full_denominator_mapping",
            "strict_new_dedupe",
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
        "# Regular Options Flow-Extreme Ratio/Backspread Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_flow_extreme_ratio_backspread_replay_readiness.py`. It is a read-only readiness audit for a preregistered defined-risk ratio/backspread concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, submit broker orders, allow naked or undefined-risk structures, or promote any lane.",
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
    parser = argparse.ArgumentParser(description="Build a read-only flow-extreme ratio/backspread replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--point-in-time-flow-extreme-input", type=Path, default=DEFAULT_POINT_IN_TIME_FLOW_EXTREME_INPUT)
    parser.add_argument("--multi-leg-side-aware-pricing-capability", type=Path, default=DEFAULT_MULTI_LEG_SIDE_AWARE_PRICING_CAPABILITY)
    parser.add_argument("--flow-extreme-denominator-dedupe-bridge", type=Path, default=DEFAULT_FLOW_EXTREME_DENOMINATOR_DEDUPE_BRIDGE)
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
        point_in_time_flow_extreme_input_path=args.point_in_time_flow_extreme_input,
        multi_leg_side_aware_pricing_capability_path=args.multi_leg_side_aware_pricing_capability,
        flow_extreme_denominator_dedupe_bridge_path=args.flow_extreme_denominator_dedupe_bridge,
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
