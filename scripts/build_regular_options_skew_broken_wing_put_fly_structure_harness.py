from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_skew_broken_wing_structure_harness"
CONCEPT_ID = "low_mid_vix_index_skew_broken_wing_put_fly_v1"
EXPECTED_STRUCTURE = "defined_risk_broken_wing_put_butterflies_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-skew-broken-wing-playbook"
    / "latest.json"
)
DEFAULT_FEATURE_STORE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_QUOTE_SURFACE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-skew-broken-wing-quote-surface" / "latest.json"
DEFAULT_VIX_BUCKET_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-skew-broken-wing-structure-harness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-skew-broken-wing-structure-harness.md"

PROTECTED_HOLDOUT_START = "2026-06-01"
RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
CONTRACT_MULTIPLIER = 100

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

DENOMINATOR_STATUSES = (
    "no_candidate",
    "rejected_skew_input",
    "rejected_geometry",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_priced",
    "open_waiting_policy_exit",
    "exact_exit_priced",
    "assignment_or_expiration_blocked",
    "missing_exit",
    "protected_holdout_blocked",
    "malformed_candidate",
    "duplicate_strict_new_identity",
    "replay_gate_blocked",
)

FORBIDDEN_ACTIONS = (
    "do_not_run_bounded_historical_replay",
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_run_or_change_production_scanners",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort_rows",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_claim_accepted_profitability",
)

NON_PROOF_MARKS = (
    "midpoint",
    "mid",
    "eod",
    "stale",
    "display",
    "display_only",
    "last",
    "last_trade",
    "manual",
    "synthetic",
    "model",
    "lookahead",
    "percent_only",
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


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    meta["report_id"] = payload.get("report_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["source_status"] = payload.get("status")
    return payload, meta


def _leg(row: dict[str, Any], role: str) -> dict[str, Any]:
    for leg in _as_list(row.get("legs")):
        leg = _as_dict(leg)
        if _norm(leg.get("role")).lower() == role:
            return leg
    return {}


def _field(row: dict[str, Any], name: str, role: str | None = None) -> Any:
    value = row.get(name)
    if value not in (None, ""):
        return value
    if role:
        return _leg(row, role).get(name)
    return None


def _quote_basis(row: dict[str, Any]) -> str:
    values = [_norm(row.get("quote_basis")).lower(), _norm(row.get("evidence_basis")).lower(), _norm(row.get("price_basis")).lower()]
    for leg in _as_list(row.get("legs")):
        leg = _as_dict(leg)
        values.extend([_norm(leg.get("quote_basis")).lower(), _norm(leg.get("evidence_basis")).lower(), _norm(leg.get("price_basis")).lower()])
    return " ".join(value for value in values if value)


def _contains_non_proof_mark(row: dict[str, Any]) -> bool:
    basis = _quote_basis(row)
    return any(mark in basis for mark in NON_PROOF_MARKS)


def _strikes(row: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    upper = _safe_float(_field(row, "upper_strike", "upper_long"))
    middle = _safe_float(_field(row, "middle_strike", "middle_short"))
    lower = _safe_float(_field(row, "lower_strike", "lower_long"))
    return upper, middle, lower


def _put_contracts_and_same_expiry(row: dict[str, Any]) -> bool:
    legs = [_leg(row, "upper_long"), _leg(row, "middle_short"), _leg(row, "lower_long")]
    if any(not leg for leg in legs):
        return True
    expiries = {_norm(leg.get("expiration") or leg.get("expiry") or row.get("expiration")).lower() for leg in legs}
    option_types = {_norm(leg.get("option_type") or leg.get("right") or "put").lower() for leg in legs}
    return len(expiries) == 1 and option_types <= {"put", "p"}


def geometry_assessment(row: dict[str, Any]) -> dict[str, Any]:
    upper, middle, lower = _strikes(row)
    if upper is None or middle is None or lower is None:
        return {"status": "blocked", "blocker": "missing_broken_wing_strikes"}
    if not (upper > middle > lower):
        return {"status": "blocked", "blocker": "unordered_or_duplicate_broken_wing_strikes"}
    upper_width = upper - middle
    lower_width = middle - lower
    if upper_width <= 0 or lower_width <= 0 or upper_width == lower_width:
        return {"status": "blocked", "blocker": "not_broken_wing_width_relationship"}
    if not _put_contracts_and_same_expiry(row):
        return {"status": "blocked", "blocker": "mixed_option_type_or_expiration"}
    return {
        "status": "valid",
        "upper_strike": upper,
        "middle_strike": middle,
        "lower_strike": lower,
        "upper_width": round(upper_width, 4),
        "lower_width": round(lower_width, 4),
    }


def side_aware_entry_cost(row: dict[str, Any]) -> float | None:
    upper_ask = _safe_float(_field(row, "upper_long_put_ask", "upper_long"))
    middle_bid = _safe_float(_field(row, "middle_short_put_bid", "middle_short"))
    lower_ask = _safe_float(_field(row, "lower_long_put_ask", "lower_long"))
    if upper_ask is None:
        upper_ask = _safe_float(_leg(row, "upper_long").get("ask"))
    if middle_bid is None:
        middle_bid = _safe_float(_leg(row, "middle_short").get("bid"))
    if lower_ask is None:
        lower_ask = _safe_float(_leg(row, "lower_long").get("ask"))
    if upper_ask is None or middle_bid is None or lower_ask is None:
        return None
    return round(upper_ask + lower_ask - (2 * middle_bid), 4)


def side_aware_exit_value(row: dict[str, Any]) -> float | None:
    upper_bid = _safe_float(_field(row, "upper_long_put_bid", "upper_long"))
    middle_ask = _safe_float(_field(row, "middle_short_put_ask", "middle_short"))
    lower_bid = _safe_float(_field(row, "lower_long_put_bid", "lower_long"))
    if upper_bid is None:
        upper_bid = _safe_float(_leg(row, "upper_long").get("bid"))
    if middle_ask is None:
        middle_ask = _safe_float(_leg(row, "middle_short").get("ask"))
    if lower_bid is None:
        lower_bid = _safe_float(_leg(row, "lower_long").get("bid"))
    if upper_bid is None or middle_ask is None or lower_bid is None:
        return None
    return round(upper_bid + lower_bid - (2 * middle_ask), 4)


def _put_payoff(strike: float, underlying: float) -> float:
    return max(strike - underlying, 0.0)


def expiry_position_value(row: dict[str, Any], underlying: float) -> float | None:
    geometry = geometry_assessment(row)
    if geometry.get("status") != "valid":
        return None
    upper = float(geometry["upper_strike"])
    middle = float(geometry["middle_strike"])
    lower = float(geometry["lower_strike"])
    return round(_put_payoff(upper, underlying) + _put_payoff(lower, underlying) - (2 * _put_payoff(middle, underlying)), 4)


def max_loss_usd(row: dict[str, Any], entry_cost: float) -> float | None:
    geometry = geometry_assessment(row)
    if geometry.get("status") != "valid":
        return None
    upper = float(geometry["upper_strike"])
    middle = float(geometry["middle_strike"])
    lower = float(geometry["lower_strike"])
    checkpoints = (0.0, lower, middle, upper, upper * 2)
    pnl_values: list[float] = []
    for underlying in checkpoints:
        value = expiry_position_value(row, underlying)
        if value is None:
            return None
        pnl_values.append(value - entry_cost)
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    worst_contract_pnl = min(pnl_values) * CONTRACT_MULTIPLIER - fees - slippage
    return round(abs(min(worst_contract_pnl, 0.0)), 2)


def net_pnl_usd(row: dict[str, Any], entry_cost: float, exit_value: float) -> float:
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    return round((exit_value - entry_cost) * CONTRACT_MULTIPLIER - fees - slippage, 2)


def assignment_expiration_classification(row: dict[str, Any]) -> dict[str, Any]:
    style = _norm(row.get("exercise_style")).lower()
    settlement = _norm(row.get("settlement_style")).lower()
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    if row.get("assignment_or_expiration_unresolved") is True:
        return {"status": "blocked", "classification": "unresolved_short_middle_put_assignment_or_expiry", "blocker": "assignment_or_expiration_unresolved"}
    if settlement == "cash" or style in {"european", "index"}:
        return {"status": "classified", "classification": "cash_settled_or_index_style", "blocker": None}
    if ticker in RESEARCH_UNIVERSE or style == "american":
        return {"status": "classified", "classification": "etf_american_short_put_assignment_exposure", "blocker": None}
    return {"status": "blocked", "classification": "unknown_short_middle_put_assignment_expiration_state", "blocker": "assignment_expiration_metadata_uncertain"}


def strict_new_identity(row: dict[str, Any]) -> str:
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    entry = _norm(row.get("entry_timestamp") or row.get("entry_date") or row.get("selection_date"))
    expiration = _norm(row.get("expiration") or row.get("expiry") or row.get("expiration_date"))
    upper, middle, lower = _strikes(row)
    basis = _norm(row.get("pricing_timestamp_basis") or row.get("quote_timestamp") or row.get("entry_quote_timestamp"))
    leg_ids = []
    for role in ("upper_long", "middle_short", "lower_long"):
        leg = _leg(row, role)
        leg_ids.append(_norm(leg.get("occ_symbol") or leg.get("contract") or leg.get("contract_symbol") or role))
    if not ticker or not entry or upper is None or middle is None or lower is None:
        return ""
    parts = ["skew_broken_wing_put_fly", ticker, entry, expiration, str(upper), str(middle), str(lower), basis, *leg_ids]
    return "|".join(parts)


def classify_candidate(row: dict[str, Any], *, protected_holdout_start: str = PROTECTED_HOLDOUT_START) -> dict[str, Any]:
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    entry_date = _norm(row.get("entry_date") or row.get("selection_date") or row.get("entry_timestamp"))[:10]
    if not ticker or ticker not in RESEARCH_UNIVERSE or not entry_date:
        return {"denominator_status": "malformed_candidate", "blockers": ["malformed_candidate"]}
    if entry_date >= protected_holdout_start:
        return {"denominator_status": "protected_holdout_blocked", "blockers": ["protected_holdout_blocked"]}
    geometry = geometry_assessment(row)
    if geometry.get("status") != "valid":
        return {"denominator_status": "rejected_geometry", "geometry": geometry, "blockers": [str(geometry.get("blocker"))]}
    assignment = assignment_expiration_classification(row)
    if assignment.get("blocker"):
        return {"denominator_status": "assignment_or_expiration_blocked", "geometry": geometry, "assignment_expiration": assignment, "blockers": [assignment["blocker"]]}
    if _contains_non_proof_mark(row):
        return {"denominator_status": "missing_leg_quote", "geometry": geometry, "assignment_expiration": assignment, "blockers": ["non_proof_quote_basis"]}
    entry_cost = side_aware_entry_cost(row)
    if entry_cost is None:
        return {"denominator_status": "missing_leg_quote", "geometry": geometry, "assignment_expiration": assignment, "blockers": ["missing_leg_quote"]}
    quote_values = [
        _safe_float(_field(row, "upper_long_put_ask", "upper_long")),
        _safe_float(_field(row, "middle_short_put_bid", "middle_short")),
        _safe_float(_field(row, "lower_long_put_ask", "lower_long")),
    ]
    if any(value is not None and value <= 0 for value in quote_values):
        return {"denominator_status": "zero_bid_or_untradable", "geometry": geometry, "entry_cost": entry_cost, "assignment_expiration": assignment, "blockers": ["zero_bid_or_untradable"]}
    loss = max_loss_usd(row, entry_cost)
    if loss is None:
        return {"denominator_status": "rejected_geometry", "geometry": geometry, "entry_cost": entry_cost, "assignment_expiration": assignment, "blockers": ["missing_max_loss_convention"]}
    exit_value = side_aware_exit_value(row)
    if exit_value is None:
        return {
            "denominator_status": "open_waiting_policy_exit" if row.get("open_waiting_policy_exit") else "exact_entry_priced",
            "geometry": geometry,
            "entry_cost": entry_cost,
            "entry_type": "credit" if entry_cost < 0 else "debit",
            "max_loss_usd": loss,
            "assignment_expiration": assignment,
            "strict_new_identity": strict_new_identity(row),
            "blockers": [],
        }
    return {
        "denominator_status": "exact_exit_priced",
        "geometry": geometry,
        "entry_cost": entry_cost,
        "exit_value": exit_value,
        "entry_type": "credit" if entry_cost < 0 else "debit",
        "max_loss_usd": loss,
        "net_pnl_usd": net_pnl_usd(row, entry_cost, exit_value),
        "assignment_expiration": assignment,
        "strict_new_identity": strict_new_identity(row),
        "blockers": [],
    }


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
    return not reasons, reasons


def _vix_bucket_ready(vix_bucket: dict[str, Any]) -> bool:
    return (
        vix_bucket.get("status") == "point_in_time_vix_bucket_ready"
        and _as_list(vix_bucket.get("blockers")) == []
        and vix_bucket.get("point_in_time_vix_low_mid_bucket_available") is True
    )


def _input_surface_assessment(feature_store: dict[str, Any], quote_surface: dict[str, Any], vix_bucket: dict[str, Any]) -> dict[str, Any]:
    vix_ready = bool(
        feature_store.get("point_in_time_vix_bucket_ready")
        or feature_store.get("vix_low_mid_bucket_ready")
        or _vix_bucket_ready(vix_bucket)
    )
    skew_ready = bool(feature_store.get("point_in_time_downside_skew_ready") or feature_store.get("downside_skew_inputs_ready"))
    quote_ready = bool(quote_surface.get("skew_broken_wing_quote_surface_ready") or quote_surface.get("three_leg_put_bwb_quote_surface_ready"))
    quote_symbols = set(str(item).upper() for item in _as_list(quote_surface.get("symbols_ready")))
    return {
        "point_in_time_vix_bucket": {
            "status": "ready" if vix_ready else "missing",
            "blocker": None if vix_ready else "missing_point_in_time_vix_bucket",
        },
        "point_in_time_downside_skew_inputs": {
            "status": "ready" if skew_ready else "missing",
            "blocker": None if skew_ready else "missing_point_in_time_downside_skew_inputs",
        },
        "index_broken_wing_quote_surface": {
            "status": "ready" if quote_ready and set(RESEARCH_UNIVERSE).issubset(quote_symbols) else "missing",
            "blocker": None if quote_ready and set(RESEARCH_UNIVERSE).issubset(quote_symbols) else "missing_index_broken_wing_quote_surface",
            "symbols_ready": sorted(quote_symbols),
        },
    }


def _blocker_burndown(input_assessment: dict[str, Any]) -> list[dict[str, Any]]:
    resolved_by_harness = (
        "missing_three_leg_broken_wing_side_aware_entry_pricing",
        "missing_three_leg_broken_wing_side_aware_exit_pricing",
        "missing_broken_wing_geometry_validator",
        "missing_max_loss_margin_convention",
        "missing_assignment_expiration_classifier",
        "missing_full_denominator_status_mapping",
        "missing_strict_new_identity",
        "missing_protected_holdout_guard",
        "missing_proof_boundary_labeling",
    )
    rows = [
        {"blocker": blocker, "status": "satisfied_by_harness", "note": "Covered by deterministic BWB pricing, geometry, max-risk, denominator, assignment/expiry, strict-new, holdout, and proof-boundary logic."}
        for blocker in resolved_by_harness
    ]
    for item in input_assessment.values():
        item = _as_dict(item)
        if item.get("blocker"):
            rows.append({"blocker": item["blocker"], "status": "unresolved", "note": "Required before bounded replay; this harness does not import data or mutate evidence."})
    return sorted(rows, key=lambda row: row["blocker"])


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    quote_surface_report_path: Path = DEFAULT_QUOTE_SURFACE_REPORT,
    vix_bucket_report_path: Path = DEFAULT_VIX_BUCKET_REPORT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    feature_store, feature_meta = _load_json(feature_store_report_path, required=False)
    quote_surface, quote_meta = _load_json(quote_surface_report_path, required=False)
    vix_bucket, vix_meta = _load_json(vix_bucket_report_path, required=False)
    prereg_valid, prereg_reasons = _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    input_assessment = _input_surface_assessment(feature_store, quote_surface, vix_bucket)
    burndown = _blocker_burndown(input_assessment) if prereg_valid else []
    remaining = [row["blocker"] for row in burndown if row["status"] != "satisfied_by_harness"]
    status = "blocked_invalid_skew_broken_wing_preregistration"
    if prereg_valid:
        status = "ready_for_skew_broken_wing_bounded_read_only_replay" if not remaining else "blocked_skew_broken_wing_structure_harness"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "scope": "read_only_skew_broken_wing_structure_harness",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "protected_holdout_start": PROTECTED_HOLDOUT_START,
        "research_universe": list(RESEARCH_UNIVERSE),
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "formulas": {
            "entry_cost": "upper_long_put_ask + lower_long_put_ask - 2 * middle_short_put_bid",
            "exit_value": "upper_long_put_bid + lower_long_put_bid - 2 * middle_short_put_ask",
            "net_pnl_usd": "(exit_value - entry_cost) * 100 - fees_and_slippage",
            "max_loss_usd": "absolute worst net P&L from expiry payoff grid across critical strike regions",
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_concept_id": CONCEPT_ID,
            "required_status": "preregistered_design_only",
            "required_structure": EXPECTED_STRUCTURE,
        },
        "input_surface_assessment": input_assessment,
        "blocker_burndown": burndown,
        "remaining_blockers": remaining,
        "source_artifacts": {
            "preregistered_skew_broken_wing_playbook": playbook_meta,
            "feature_store_report": feature_meta,
            "quote_surface_report": quote_meta,
            "point_in_time_vix_bucket": vix_meta,
        },
        "proof_boundary": "structure readiness only; not replay, not forward proof, not production proof, not live validation, not a trade recommendation, and not promotion-ready",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    for status in DENOMINATOR_STATUSES:
        if status not in report.get("denominator_statuses", []):
            raise ValueError(f"missing denominator status {status}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Skew Broken-Wing Structure Harness",
        "",
        "This generated report is read-only. It implements structure-specific broken-wing put-fly formulas and blocker mapping only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        "",
        "## Remaining Blockers",
        "",
    ]
    if report.get("remaining_blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("remaining_blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Blocker Burndown", "", "| Blocker | Status | Note |", "| --- | --- | --- |"])
    for row in _as_list(report.get("blocker_burndown")):
        row = _as_dict(row)
        lines.append(f"| `{row.get('blocker')}` | `{row.get('status')}` | {row.get('note')} |")
    lines.extend(["", "## Denominator Statuses", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("denominator_statuses")))
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Build a read-only skew broken-wing put-fly structure harness.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--quote-surface-report", type=Path, default=DEFAULT_QUOTE_SURFACE_REPORT)
    parser.add_argument("--vix-bucket-report", type=Path, default=DEFAULT_VIX_BUCKET_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        feature_store_report_path=args.feature_store_report,
        quote_surface_report_path=args.quote_surface_report,
        vix_bucket_report_path=args.vix_bucket_report,
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
