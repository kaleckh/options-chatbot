from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_term_structure_calendar_structure_harness"
CONCEPT_ID = "low_mid_vix_index_calendar_term_structure_dislocation_v1"
EXPECTED_STRUCTURE = "defined_risk_calendar_or_diagonal_debit_spreads_only"

DEFAULT_PREREGISTERED_PLAYBOOK = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-term-structure-calendar-playbook" / "latest.json"
DEFAULT_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-replay-readiness" / "latest.json"
DEFAULT_FEATURE_STORE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_QUOTE_SURFACE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-quote-surface" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-structure-harness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-term-structure-calendar-structure-harness.md"

PROTECTED_HOLDOUT_START = "2026-06-01"
INITIAL_UNIVERSE = ("SPY", "QQQ")
FUTURE_EXTENSION_UNIVERSE = ("IWM", "DIA")
CONTRACT_MULTIPLIER = 100

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
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
    "rejected_term_structure_input",
    "rejected_geometry",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_captured",
    "open_waiting_policy_exit",
    "front_expired_waiting_back_exit",
    "assignment_or_expiration_blocked",
    "exact_exit_captured",
    "missing_exit",
    "protected_holdout_blocked",
    "duplicate_strict_new_identity",
    "malformed_candidate",
    "replay_gate_blocked",
)

FORBIDDEN_ACTIONS = (
    "do_not_run_full_historical_replay",
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


def entry_debit(row: dict[str, Any]) -> float | None:
    long_ask = _safe_float(row.get("long_back_month_ask"))
    short_bid = _safe_float(row.get("short_front_month_bid"))
    if long_ask is None or short_bid is None:
        return None
    return round(long_ask - short_bid, 4)


def exit_value(row: dict[str, Any]) -> float | None:
    long_bid = _safe_float(row.get("long_back_month_bid"))
    short_ask = _safe_float(row.get("short_front_month_ask"))
    if long_bid is None or short_ask is None:
        return None
    return round(long_bid - short_ask, 4)


def max_loss_usd(row: dict[str, Any], debit: float) -> float:
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    return round(debit * CONTRACT_MULTIPLIER + fees + slippage, 2)


def net_pnl_usd(row: dict[str, Any], debit: float, value: float) -> float:
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    return round((value - debit) * CONTRACT_MULTIPLIER - fees - slippage, 2)


def front_leg_assignment_expiration(row: dict[str, Any]) -> dict[str, Any]:
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    style = _norm(row.get("front_leg_exercise_style") or row.get("exercise_style")).lower()
    if ticker in INITIAL_UNIVERSE + FUTURE_EXTENSION_UNIVERSE or style == "american":
        return {"status": "classified", "classification": "etf_american_front_assignment_exposure", "blocker": None}
    if style in {"european", "index"}:
        return {"status": "classified", "classification": "cash_settled_or_index_style", "blocker": None}
    return {"status": "blocked", "classification": "unknown_front_leg_assignment_expiration_state", "blocker": "front_leg_assignment_expiration_uncertain"}


def classify_candidate(row: dict[str, Any], *, protected_holdout_start: str = PROTECTED_HOLDOUT_START) -> dict[str, Any]:
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    entry_date = _norm(row.get("entry_date") or row.get("selection_date"))
    if not ticker or not entry_date:
        return {"denominator_status": "malformed_candidate", "blockers": ["malformed_candidate"]}
    if ticker in FUTURE_EXTENSION_UNIVERSE:
        return {"denominator_status": "rejected_geometry", "blockers": ["future_extension_universe_requires_separate_recheck"]}
    if ticker not in INITIAL_UNIVERSE:
        return {"denominator_status": "malformed_candidate", "blockers": ["non_initial_universe_symbol"]}
    if entry_date >= protected_holdout_start:
        return {"denominator_status": "protected_holdout_blocked", "blockers": ["protected_holdout_blocked"]}
    assignment = front_leg_assignment_expiration(row)
    if assignment.get("blocker"):
        return {"denominator_status": "assignment_or_expiration_blocked", "assignment_expiration": assignment, "blockers": [assignment["blocker"]]}
    debit = entry_debit(row)
    if debit is None:
        return {"denominator_status": "missing_leg_quote", "assignment_expiration": assignment, "blockers": ["missing_leg_quote"]}
    if debit <= 0:
        return {"denominator_status": "zero_bid_or_untradable", "entry_debit": debit, "assignment_expiration": assignment, "blockers": ["zero_bid_or_untradable"]}
    value = exit_value(row)
    if value is not None:
        return {
            "denominator_status": "exact_exit_captured",
            "entry_debit": debit,
            "exit_debit_or_value": value,
            "max_loss_usd": max_loss_usd(row, debit),
            "net_pnl_usd": net_pnl_usd(row, debit, value),
            "assignment_expiration": assignment,
            "blockers": [],
        }
    if row.get("front_leg_expired"):
        return {
            "denominator_status": "front_expired_waiting_back_exit",
            "entry_debit": debit,
            "max_loss_usd": max_loss_usd(row, debit),
            "assignment_expiration": assignment,
            "blockers": [],
        }
    return {
        "denominator_status": "open_waiting_policy_exit",
        "entry_debit": debit,
        "max_loss_usd": max_loss_usd(row, debit),
        "assignment_expiration": assignment,
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


def _candidate_geometry_ready(playbook: dict[str, Any]) -> bool:
    concept = _as_dict(playbook.get("concept"))
    geometry = _as_dict(playbook.get("candidate_geometry") or concept.get("candidate_geometry"))
    required = ("front_back_expiry_spacing", "strike_delta_or_moneyness_rule", "max_debit", "max_bid_ask_width", "exit_policy")
    if geometry:
        return all(geometry.get(key) not in (None, "") for key in required)

    frozen = _as_dict(concept.get("frozen_design"))
    term_selection = [str(item).lower() for item in _as_list(frozen.get("term_structure_selection"))]
    exit_policy = _as_list(frozen.get("exit_policy"))
    has_spacing = any("spacing" in item for item in term_selection)
    has_strike_rule = any(("strike" in item or "delta" in item or "moneyness" in item) for item in term_selection)
    has_cost_rule = any(("debit" in item or "spread width" in item or "bid/ask" in item) for item in term_selection)
    return has_spacing and has_strike_rule and has_cost_rule and bool(exit_policy)


def _strict_new_dedupe_ready(playbook: dict[str, Any]) -> bool:
    concept = _as_dict(playbook.get("concept"))
    requirements = [str(item).lower() for item in _as_list(concept.get("required_future_replay_engine_support"))]
    has_contract = any("strict-new dedupe" in item and "157-row clean base stack" in item for item in requirements)
    return has_contract and "duplicate_strict_new_identity" in DENOMINATOR_STATUSES


def _input_surface_assessment(feature_store: dict[str, Any], quote_surface: dict[str, Any]) -> dict[str, Any]:
    term_ready = bool(feature_store.get("point_in_time_term_structure_inputs_ready") or feature_store.get("term_structure_inputs_ready"))
    vix_ready = bool(feature_store.get("point_in_time_vix_bucket_ready") or feature_store.get("vix_low_mid_bucket_ready"))
    quote_ready = bool(quote_surface.get("calendar_diagonal_quote_surface_ready") or quote_surface.get("multi_expiry_quote_surface_ready"))
    symbols_ready = set(str(item).upper() for item in _as_list(quote_surface.get("symbols_ready")))
    return {
        "point_in_time_term_structure_inputs": {
            "status": "ready" if term_ready and vix_ready else "missing",
            "blocker": None if term_ready and vix_ready else "missing_point_in_time_term_structure_inputs",
        },
        "index_calendar_quote_surface": {
            "status": "ready" if quote_ready and set(INITIAL_UNIVERSE).issubset(symbols_ready) else "missing",
            "blocker": None if quote_ready and set(INITIAL_UNIVERSE).issubset(symbols_ready) else "missing_index_calendar_quote_surface",
            "symbols_ready": sorted(symbols_ready),
        },
    }


def _blocker_burndown(readiness_blockers: list[str], input_assessment: dict[str, Any], geometry_ready: bool, strict_new_ready: bool) -> list[dict[str, Any]]:
    resolved_by_harness = {
        "missing_calendar_diagonal_side_aware_pricing_engine",
        "missing_calendar_diagonal_exit_or_expiry_engine",
        "missing_full_denominator_status_mapping",
        "missing_front_leg_assignment_expiration_classifier",
        "missing_roll_or_expiry_policy",
        "missing_net_usd_pnl_after_costs",
        "missing_protected_holdout_guard",
        "missing_proof_boundary_labeling",
    }
    unresolved = {
        row["blocker"]
        for row in input_assessment.values()
        if isinstance(row, dict) and row.get("blocker")
    }
    if geometry_ready:
        resolved_by_harness.add("missing_preregistered_calendar_diagonal_geometry")
    else:
        unresolved.add("missing_preregistered_calendar_diagonal_geometry")
    if strict_new_ready:
        resolved_by_harness.add("missing_strict_new_dedupe")
    else:
        unresolved.add("missing_strict_new_dedupe")
    blocker_ids = sorted(set(readiness_blockers) | resolved_by_harness | unresolved)
    rows: list[dict[str, Any]] = []
    for blocker in blocker_ids:
        if blocker in unresolved:
            rows.append({"blocker": blocker, "status": "unresolved", "note": "Required before any bounded replay; no data import or policy change was performed."})
        elif blocker in resolved_by_harness:
            rows.append({"blocker": blocker, "status": "satisfied_by_harness", "note": "Covered by deterministic structure math, denominator, assignment/expiry, roll, P&L, holdout, and proof-boundary logic."})
        else:
            rows.append({"blocker": blocker, "status": "blocked_with_reason", "note": "Reported by readiness artifact and not cleared by this harness."})
    return rows


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    readiness_path: Path = DEFAULT_READINESS,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    quote_surface_report_path: Path = DEFAULT_QUOTE_SURFACE_REPORT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    readiness, readiness_meta = _load_json(readiness_path, required=True)
    feature_store, feature_meta = _load_json(feature_store_report_path, required=False)
    quote_surface, quote_meta = _load_json(quote_surface_report_path, required=False)
    prereg_valid, prereg_reasons = _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    input_assessment = _input_surface_assessment(feature_store, quote_surface)
    geometry_ready = _candidate_geometry_ready(playbook)
    strict_new_ready = _strict_new_dedupe_ready(playbook)
    burndown = _blocker_burndown([str(item) for item in _as_list(readiness.get("blockers"))], input_assessment, geometry_ready, strict_new_ready) if prereg_valid else []
    remaining = [row["blocker"] for row in burndown if row["status"] != "satisfied_by_harness"]
    status = "blocked_invalid_term_structure_calendar_preregistration"
    if prereg_valid:
        status = "term_structure_calendar_structure_harness_ready" if not remaining else "blocked_term_structure_calendar_structure_harness"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "scope": "read_only_term_structure_calendar_structure_harness",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "initial_research_universe": list(INITIAL_UNIVERSE),
        "future_extension_universe": list(FUTURE_EXTENSION_UNIVERSE),
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "formulas": {
            "entry_debit": "long_back_month_ask - short_front_month_bid",
            "exit_debit_or_value": "long_back_month_bid - short_front_month_ask",
            "net_pnl_usd": "(exit_debit_or_value - entry_debit) * 100 - fees_and_slippage",
            "max_loss_usd": "entry_debit * 100 + fees_and_slippage",
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_concept_id": CONCEPT_ID,
            "required_structure": EXPECTED_STRUCTURE,
        },
        "input_surface_assessment": input_assessment,
        "candidate_geometry_ready": geometry_ready,
        "strict_new_dedupe_ready": strict_new_ready,
        "blocker_burndown": burndown,
        "remaining_blockers": remaining,
        "source_artifacts": {
            "preregistered_term_structure_calendar_playbook": playbook_meta,
            "term_structure_calendar_replay_readiness": readiness_meta,
            "feature_store_report": feature_meta,
            "quote_surface_report": quote_meta,
        },
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


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Term-Structure Calendar Structure Harness",
        "",
        "This generated report is read-only. It implements structure-specific calendar/diagonal formulas and blocker mapping only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Accepted profitability: `{str(report['accepted_profitability']).lower()}`.",
        f"- Historical replay performed: `{str(report['historical_replay_performed']).lower()}`.",
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
    artifacts = {"json": _rel(json_path), "markdown": _rel(md_path), "latest_json": _rel(latest_json), "latest_markdown": _rel(latest_md), "docs_report": _rel(docs_report)}
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
    parser = argparse.ArgumentParser(description="Build a read-only term-structure calendar/diagonal structure harness.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--quote-surface-report", type=Path, default=DEFAULT_QUOTE_SURFACE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        readiness_path=args.readiness,
        feature_store_report_path=args.feature_store_report,
        quote_surface_report_path=args.quote_surface_report,
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
