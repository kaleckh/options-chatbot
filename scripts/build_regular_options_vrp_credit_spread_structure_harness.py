from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_vrp_credit_spread_structure_harness"
CONCEPT_ID = "low_mid_vix_index_put_credit_spread_vrp_v1"
EXPECTED_STRUCTURE = "defined_risk_put_credit_spreads_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-vrp-credit-spread-playbook"
    / "latest.json"
)
DEFAULT_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-replay-readiness" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-structure-harness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-vrp-credit-spread-structure-harness.md"
DEFAULT_FEATURE_STORE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_VIX_BUCKET_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_QUOTE_SURFACE_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-quote-surface" / "latest.json"

PROTECTED_HOLDOUT_START = "2026-06-01"
RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
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
    "candidate_unpriced",
    "zero_bid_untradable",
    "entry_priced_exit_missing",
    "exact_closed",
    "expired_settled",
    "missing_required_quote",
    "rejected_liquidity",
    "protected_holdout_blocked",
    "malformed_candidate",
)

FORBIDDEN_ACTIONS = (
    "do_not_create_broker_orders",
    "do_not_prepare_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_run_or_change_production_scanners",
    "do_not_change_scanner_policy",
    "do_not_change_production_strategy_logic",
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


def _leg(row: dict[str, Any], role: str) -> dict[str, Any]:
    role = role.lower()
    for leg in _as_list(row.get("legs")) + _as_list(_as_dict(row.get("entry_quote_snapshot")).get("legs")):
        leg = _as_dict(leg)
        if _norm(leg.get("role")).lower() == role:
            return leg
    return {}


def _field(row: dict[str, Any], name: str, role: str | None = None) -> Any:
    direct = row.get(name)
    if direct not in (None, ""):
        return direct
    if role:
        return _leg(row, role).get(name)
    return None


def entry_credit(row: dict[str, Any]) -> float | None:
    short_bid = _safe_float(_field(row, "short_put_bid", "short"))
    long_ask = _safe_float(_field(row, "long_put_ask", "long"))
    if short_bid is None:
        short_bid = _safe_float(_leg(row, "short").get("bid"))
    if long_ask is None:
        long_ask = _safe_float(_leg(row, "long").get("ask"))
    if short_bid is None or long_ask is None:
        return None
    return round(short_bid - long_ask, 4)


def exit_debit(row: dict[str, Any]) -> float | None:
    short_ask = _safe_float(_field(row, "short_put_ask", "short"))
    long_bid = _safe_float(_field(row, "long_put_bid", "long"))
    if short_ask is None:
        short_ask = _safe_float(_leg(row, "short").get("ask"))
    if long_bid is None:
        long_bid = _safe_float(_leg(row, "long").get("bid"))
    if short_ask is None or long_bid is None:
        return None
    return round(short_ask - long_bid, 4)


def expiration_settlement_debit(row: dict[str, Any]) -> float | None:
    short_strike = _safe_float(row.get("short_strike"))
    long_strike = _safe_float(row.get("long_strike"))
    underlying_close = _safe_float(row.get("underlying_close"))
    if short_strike is None or long_strike is None or underlying_close is None:
        return None
    return round(max(short_strike - underlying_close, 0.0) - max(long_strike - underlying_close, 0.0), 4)


def spread_width(row: dict[str, Any]) -> float | None:
    short_strike = _safe_float(row.get("short_strike"))
    long_strike = _safe_float(row.get("long_strike"))
    if short_strike is None or long_strike is None:
        return None
    width = short_strike - long_strike
    return round(width, 4) if width > 0 else None


def max_loss_usd(row: dict[str, Any], credit: float) -> float | None:
    width = spread_width(row)
    if width is None or credit <= 0:
        return None
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    return round((width - credit) * CONTRACT_MULTIPLIER + fees + slippage, 2)


def net_pnl_usd(row: dict[str, Any], credit: float, closing_debit: float) -> float:
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    return round((credit - closing_debit) * CONTRACT_MULTIPLIER - fees - slippage, 2)


def assignment_expiration_classification(row: dict[str, Any]) -> dict[str, Any]:
    style = _norm(row.get("exercise_style")).lower()
    settlement = _norm(row.get("settlement_style")).lower()
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    if settlement == "cash" or style in {"european", "index"}:
        return {"status": "classified", "classification": "cash_settled_or_index_style", "blocker": None}
    if ticker in RESEARCH_UNIVERSE or style == "american":
        return {"status": "classified", "classification": "etf_american_assignment_exposure", "blocker": None}
    return {"status": "blocked", "classification": "unknown_assignment_expiration_state", "blocker": "assignment_expiration_metadata_uncertain"}


def classify_candidate(row: dict[str, Any], *, protected_holdout_start: str = PROTECTED_HOLDOUT_START) -> dict[str, Any]:
    ticker = _norm(row.get("ticker") or row.get("underlying")).upper()
    entry_date = _norm(row.get("entry_date") or row.get("selection_date"))
    if not ticker or ticker not in RESEARCH_UNIVERSE or not entry_date:
        return {"denominator_status": "malformed_candidate", "blockers": ["malformed_candidate"]}
    if entry_date >= protected_holdout_start:
        return {"denominator_status": "protected_holdout_blocked", "blockers": ["protected_holdout_blocked"]}
    assignment = assignment_expiration_classification(row)
    if assignment.get("blocker"):
        return {
            "denominator_status": "malformed_candidate",
            "assignment_expiration": assignment,
            "blockers": [assignment["blocker"]],
        }
    credit = entry_credit(row)
    if credit is None:
        return {"denominator_status": "missing_required_quote", "assignment_expiration": assignment, "blockers": ["missing_required_quote"]}
    if credit <= 0:
        return {"denominator_status": "zero_bid_untradable", "entry_credit": credit, "assignment_expiration": assignment, "blockers": ["zero_bid_untradable"]}
    width = spread_width(row)
    loss = max_loss_usd(row, credit)
    if width is None or loss is None:
        return {"denominator_status": "rejected_liquidity", "entry_credit": credit, "assignment_expiration": assignment, "blockers": ["missing_margin_max_loss_convention"]}
    debit = exit_debit(row)
    settlement = expiration_settlement_debit(row)
    if debit is not None:
        status = "exact_closed"
        close_debit = debit
    elif _norm(row.get("expiration_date")) and settlement is not None:
        status = "expired_settled"
        close_debit = settlement
    else:
        return {
            "denominator_status": "entry_priced_exit_missing",
            "entry_credit": credit,
            "spread_width": width,
            "max_loss_usd": loss,
            "assignment_expiration": assignment,
            "blockers": [],
        }
    return {
        "denominator_status": status,
        "entry_credit": credit,
        "exit_debit_or_settlement": close_debit,
        "spread_width": width,
        "max_loss_usd": loss,
        "net_pnl_usd": net_pnl_usd(row, credit, close_debit),
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


def _readiness_blockers(readiness_report: dict[str, Any]) -> list[str]:
    return [str(item) for item in _as_list(readiness_report.get("blockers")) if _norm(item)]


def _vix_bucket_ready(vix_bucket: dict[str, Any], feature_store: dict[str, Any]) -> bool:
    return bool(
        (
            vix_bucket.get("status") == "point_in_time_vix_bucket_ready"
            and not _as_list(vix_bucket.get("blockers"))
        )
        or feature_store.get("point_in_time_vix_bucket_ready")
        or feature_store.get("vix_low_mid_bucket_ready")
    )


def _input_surface_assessment(vix_bucket: dict[str, Any], feature_store: dict[str, Any], quote_surface: dict[str, Any]) -> dict[str, Any]:
    vix_ready = _vix_bucket_ready(vix_bucket, feature_store)
    quote_ready = bool(quote_surface.get("credit_spread_quote_surface_ready"))
    quote_symbols = set(str(item).upper() for item in _as_list(quote_surface.get("symbols_ready")))
    return {
        "point_in_time_vix_bucket": {
            "status": "ready" if vix_ready else "missing",
            "blocker": None if vix_ready else "missing_point_in_time_vix_bucket",
        },
        "index_credit_spread_quote_surface": {
            "status": "ready" if quote_ready and set(RESEARCH_UNIVERSE).issubset(quote_symbols) else "missing",
            "blocker": None if quote_ready and set(RESEARCH_UNIVERSE).issubset(quote_symbols) else "missing_index_credit_spread_quote_surface",
            "symbols_ready": sorted(quote_symbols),
        },
    }


def _blocker_burndown(readiness_blockers: list[str], input_assessment: dict[str, Any]) -> list[dict[str, Any]]:
    resolved_by_harness = {
        "missing_credit_spread_side_aware_pricing_engine",
        "missing_credit_spread_side_aware_exit_pricing_engine",
        "missing_full_denominator_status_mapping",
        "missing_assignment_expiration_classifier",
        "missing_margin_max_loss_convention",
        "missing_net_usd_pnl_after_costs",
        "missing_protected_holdout_guard",
        "missing_proof_boundary_labeling",
    }
    unresolved_inputs = {
        row["blocker"]
        for row in input_assessment.values()
        if isinstance(row, dict) and row.get("blocker")
    }
    resolved_inputs = {
        "missing_point_in_time_vix_bucket"
        if _as_dict(input_assessment.get("point_in_time_vix_bucket")).get("status") == "ready"
        else "",
        "missing_index_credit_spread_quote_surface"
        if _as_dict(input_assessment.get("index_credit_spread_quote_surface")).get("status") == "ready"
        else "",
    }
    resolved_inputs.discard("")
    blocker_ids = sorted(set(readiness_blockers) | resolved_by_harness | unresolved_inputs)
    rows: list[dict[str, Any]] = []
    for blocker in blocker_ids:
        if blocker in unresolved_inputs:
            status = "unresolved"
            note = "Requires existing point-in-time input or quote-surface artifact; harness does not import data."
        elif blocker in resolved_inputs:
            status = "resolved_by_existing_read_only_input"
            note = "Existing read-only input artifact claims this prerequisite is ready; no quote import was performed."
        elif blocker in resolved_by_harness:
            status = "resolved_by_harness"
            note = "Covered by deterministic structure math, denominator, assignment/expiration, margin, P&L, holdout, and proof-boundary logic."
        else:
            status = "not_testable_from_existing_inputs"
            note = "Reported by prior readiness artifact but not directly cleared by this harness."
        rows.append({"blocker": blocker, "status": status, "note": note})
    return rows


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    readiness_path: Path = DEFAULT_READINESS,
    vix_bucket_report_path: Path = DEFAULT_VIX_BUCKET_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    quote_surface_report_path: Path = DEFAULT_QUOTE_SURFACE_REPORT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    readiness_report, readiness_meta = _load_json(readiness_path, required=True)
    vix_bucket, vix_meta = _load_json(vix_bucket_report_path, required=False)
    feature_store, feature_meta = _load_json(feature_store_report_path, required=False)
    quote_surface, quote_meta = _load_json(quote_surface_report_path, required=False)
    prereg_valid, prereg_reasons = _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    input_assessment = _input_surface_assessment(vix_bucket, feature_store, quote_surface)
    burndown = _blocker_burndown(_readiness_blockers(readiness_report), input_assessment) if prereg_valid else []
    resolved_statuses = {"resolved_by_harness", "resolved_by_existing_read_only_input"}
    remaining_blockers = [row["blocker"] for row in burndown if row["status"] not in resolved_statuses]
    status = "blocked_invalid_vrp_preregistration"
    if prereg_valid:
        status = "ready_for_bounded_read_only_vrp_replay" if not remaining_blockers else "blocked_vrp_credit_spread_structure_harness"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "scope": "read_only_vrp_credit_spread_structure_harness",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "protected_holdout_start": PROTECTED_HOLDOUT_START,
        "research_universe": list(RESEARCH_UNIVERSE),
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "formulas": {
            "entry_credit": "short_put_bid - long_put_ask",
            "exit_debit": "short_put_ask - long_put_bid",
            "expiration_settlement_debit": "max(short_strike - underlying_close, 0) - max(long_strike - underlying_close, 0)",
            "max_loss_usd": "(short_strike - long_strike - entry_credit) * 100 + fees_and_slippage",
            "net_pnl_usd": "(entry_credit - exit_debit_or_settlement) * 100 - fees_and_slippage",
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
        "remaining_blockers": remaining_blockers,
        "source_artifacts": {
            "preregistered_vrp_credit_spread_playbook": playbook_meta,
            "vrp_credit_spread_replay_readiness": readiness_meta,
            "point_in_time_vix_bucket": vix_meta,
            "feature_store_report": feature_meta,
            "quote_surface_report": quote_meta,
        },
        "allowed_next_step": "If status is ready_for_bounded_read_only_vrp_replay, ask Oracle for a bounded read-only replay slice. Otherwise address the named remaining blockers without quote import, holdout use, live/broker, or proof-bar changes.",
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
    if report["preregistration_validation"]["valid"] and report.get("concept_id") != CONCEPT_ID:
        raise ValueError("unexpected concept_id")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options VRP Credit Spread Structure Harness",
        "",
        "This generated report is read-only. It implements deterministic structure math and readiness classification only; it does not run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change scanner/strategy/stops/sizing/proof bars, append forward rows, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Quotes imported: `{_fmt_bool(report['quotes_imported'])}`.",
        f"- Protected holdout consumed: `{_fmt_bool(report['protected_holdout_consumed'])}`.",
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
    parser = argparse.ArgumentParser(description="Build a read-only VRP put-credit-spread structure harness.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--vix-bucket-report", type=Path, default=DEFAULT_VIX_BUCKET_REPORT)
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
        vix_bucket_report_path=args.vix_bucket_report,
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
