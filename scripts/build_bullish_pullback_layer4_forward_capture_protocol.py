from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "bullish_pullback_layer4_forward_capture_protocol"

SELECTED_LANE_ID = "bullish_pullback_observation"
SELECTED_LAYER_ID = "layer_4_clean_exact"
SELECTED_VARIANT_ID = "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1"
SELECTED_SOURCE_RUN = "data/options-validation/runs/20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json"
FREEZE_DATE = "2026-06-14"
ALLOWED_SYMBOLS = ("IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM")

DEFAULT_SELECTION = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_shadow_selection_latest.json"
DEFAULT_EXECUTION_SAFETY = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_execution_safety_audit_latest.json"
DEFAULT_EXECUTABLE_ECONOMICS = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_executable_economics_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-bullish-pullback-layer4-forward-capture-protocol.md"
DEFAULT_APPROVAL_PACKET = ROOT / "docs" / "bullish-pullback-layer4-forward-paper-shadow-approval-packet.md"
MAX_SOURCE_AGE_HOURS = 96

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_submit_broker_orders_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_enable_live_validation_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_enable_auto_track_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_change_scanner_policy_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_change_strategy_logic_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_change_stops_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_change_sizing_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_mutate_evidence_databases_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_import_quotes_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_append_forward_cohort_rows_from_bullish_pullback_layer4_forward_capture_protocol",
    "do_not_consume_protected_holdout_from_bullish_pullback_layer4_forward_capture_protocol",
)

REQUIRED_ROW_FIELDS = (
    "row_id",
    "lane_id",
    "layer_id",
    "variant_id",
    "ticker",
    "selection_date",
    "denominator_status",
    "scanner_run_id",
    "scanner_policy_hash",
    "long_contract_symbol",
    "short_contract_symbol",
)

DENOMINATOR_STATUSES = (
    "exact_entry_captured",
    "open_waiting_policy_exit",
    "exact_exit_captured",
    "missed_entry",
    "zero_untradable",
    "stale_display_rejected",
    "failed_or_incomplete_fill_attempt",
    "missing_exit",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path, *, name: str, required: bool, generated_at_utc: str, max_age_hours: int) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": ["missing_readback"],
        "error": None,
    }
    if not path.exists():
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source.update({"status": "malformed", "error": f"JSONDecodeError:{exc.lineno}:{exc.colno}", "reason_codes": ["malformed_readback"]})
        return {}, source
    if not isinstance(payload, dict):
        source.update({"status": "invalid", "reason_codes": ["json_root_not_object"]})
        return {}, source
    source["generated_at_utc"] = payload.get("generated_at_utc")
    generated_dt = _parse_utc(payload.get("generated_at_utc"))
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    if generated_dt is None:
        source.update({"status": "stale", "reason_codes": ["missing_or_malformed_generated_at_utc", "stale_readback"]})
        return payload, source
    age_hours = (as_of - generated_dt).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours > max_age_hours:
        source.update({"status": "stale", "reason_codes": ["stale_readback"]})
        return payload, source
    source.update({"status": "loaded", "reason_codes": [], "report_id": payload.get("report_id") or name})
    return payload, source


def _selected_from_selection(selection: dict[str, Any]) -> dict[str, Any]:
    requirements = _as_dict(selection.get("harness_requirements"))
    primary = _as_dict(selection.get("primary_harness_layer"))
    return {
        "layer_id": _norm(requirements.get("selected_layer_id") or primary.get("layer_id")),
        "variant_id": _norm(requirements.get("selected_variant_id") or primary.get("variant_id")),
        "source_result_path": _norm(requirements.get("source_result_path") or primary.get("source_result_path")),
        "metrics": _as_dict(primary.get("metrics")),
    }


def _selected_from_named(payload: dict[str, Any], key: str = "selected_layer") -> dict[str, Any]:
    selected = _as_dict(payload.get(key))
    return {
        "layer_id": _norm(selected.get("layer_id")),
        "variant_id": _norm(selected.get("variant_id")),
        "source_result_path": _norm(selected.get("source_result_path")),
        "metrics": _as_dict(selected.get("metrics")),
    }


def _matches_selected(selected: dict[str, Any]) -> bool:
    return (
        selected.get("layer_id") == SELECTED_LAYER_ID
        and selected.get("variant_id") == SELECTED_VARIANT_ID
        and selected.get("source_result_path") == SELECTED_SOURCE_RUN
    )


def _blockers_for_sources(selection: dict[str, Any], execution_safety: dict[str, Any], economics: dict[str, Any], source_artifacts: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name, meta in source_artifacts.items():
        if meta.get("required") and meta.get("status") != "loaded":
            blockers.append(f"{name}_not_loaded")
    if selection and selection.get("overall_status") != "layer_shadow_selection_ready":
        blockers.append("layer_shadow_selection_not_ready")
    if selection and not _matches_selected(_selected_from_selection(selection)):
        blockers.append("selected_layer_shadow_selection_drift")
    if execution_safety and not _matches_selected(_selected_from_named(execution_safety)):
        blockers.append("selected_execution_safety_layer_drift")
    econ_status = _norm(economics.get("overall_status"))
    if economics and econ_status != "executable_economics_recomputed_profitable_but_preflight_blocked":
        blockers.append("historical_executable_economics_not_positive_preflight_blocked")
    if economics and _norm(economics.get("harness_decision")) != "profitable_but_preflight_blocked":
        blockers.append("historical_executable_harness_decision_drift")
    if economics and not _matches_selected(_selected_from_named(economics)):
        blockers.append("selected_executable_economics_layer_drift")
    return blockers


def build_report(
    *,
    selection_path: Path = DEFAULT_SELECTION,
    execution_safety_path: Path = DEFAULT_EXECUTION_SAFETY,
    executable_economics_path: Path = DEFAULT_EXECUTABLE_ECONOMICS,
    approval_packet_path: Path = DEFAULT_APPROVAL_PACKET,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    selection, selection_source = _load_json(selection_path, name="bullish_pullback_layer_shadow_selection", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    execution_safety, safety_source = _load_json(execution_safety_path, name="bullish_pullback_layer_execution_safety_audit", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    economics, economics_source = _load_json(executable_economics_path, name="bullish_pullback_layer_executable_economics", required=True, generated_at_utc=generated_at, max_age_hours=max_source_age_hours)
    source_artifacts = {
        "bullish_pullback_layer_shadow_selection": selection_source,
        "bullish_pullback_layer_execution_safety_audit": safety_source,
        "bullish_pullback_layer_executable_economics": economics_source,
    }
    blockers = _blockers_for_sources(selection, execution_safety, economics, source_artifacts)
    status = "blocked_capture_protocol" if blockers else "protocol_ready_waiting_for_market_window_and_operator_approval"
    econ_view = _as_dict(_as_dict(economics.get("denominator_views")).get("tradable_executable_only"))
    bootstrap = _as_dict(econ_view.get("bootstrap"))
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "bullish_pullback_layer4_future_forward_paper_shadow_capture_protocol",
        "capture_protocol_status": status,
        "overall_status": status,
        "blockers": blockers,
        "read_only": True,
        "paper_shadow_only": True,
        "candidate_validator_read_only": True,
        "cohort_append_performed": False,
        "historical_rows_are_forward_proof": False,
        "source_artifacts": source_artifacts,
        "selected_harness": {
            "lane_id": SELECTED_LANE_ID,
            "layer_id": SELECTED_LAYER_ID,
            "variant_id": SELECTED_VARIANT_ID,
            "source_result_path": SELECTED_SOURCE_RUN,
            "freeze_date": FREEZE_DATE,
            "allowed_symbols": list(ALLOWED_SYMBOLS),
        },
        "historical_executable_economics": {
            "status": economics.get("overall_status"),
            "harness_decision": economics.get("harness_decision"),
            "row_counts": economics.get("row_counts"),
            "tradable_executable_rows": _as_dict(economics.get("row_counts")).get("tradable_executable_rows"),
            "historical_side_aware_pf": econ_view.get("profit_factor"),
            "historical_side_aware_pf_lb_5pct": bootstrap.get("pf_lb_5pct"),
            "historical_side_aware_net_usd_total": econ_view.get("net_usd_total"),
            "historical_side_aware_avg_net_lb_5pct": bootstrap.get("avg_net_lb_5pct"),
        },
        "execution_safety_preflight": {
            "status": execution_safety.get("overall_status"),
            "row_counts": execution_safety.get("row_counts"),
            "fatal_reason_counts": execution_safety.get("fatal_reason_counts"),
            "blockers": execution_safety.get("blockers"),
        },
        "protocol_requirements": {
            "future_natural_scanner_selections_only": True,
            "full_denominator_logging_required": True,
            "denominator_statuses": list(DENOMINATOR_STATUSES),
            "required_row_fields": list(REQUIRED_ROW_FIELDS),
            "leg_level_occ_identity_required": True,
            "trusted_opra_nbbo_entry_bid_ask_required_for_entry_rows": True,
            "trusted_opra_nbbo_exit_bid_ask_required_for_exact_exit_rows": True,
            "side_aware_entry_price_formula": "long_ask_minus_short_bid",
            "side_aware_exit_price_formula": "long_bid_minus_short_ask",
            "policy_defined_exit_condition_required_for_exact_exit": True,
            "assignment_expiration_risk_classification_required": True,
            "scanner_policy_snapshot_required": True,
            "contract_multiplier_and_fee_convention_required": True,
            "net_pnl_usd_required_for_exact_exit": True,
            "source_marks_midpoint_eod_display_stale_last_trade_manual_synthetic_lookahead_percent_only_rejected_as_proof": True,
        },
        "approval_packet_path": _rel(approval_packet_path),
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_broker_behavior": False,
        "changed_auto_track_behavior": False,
        "changed_live_validation": False,
        "imported_quotes": False,
        "mutated_evidence_databases": False,
        "consumed_protected_holdout": False,
        "appended_forward_cohort_rows": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    selected = _as_dict(report.get("selected_harness"))
    econ = _as_dict(report.get("historical_executable_economics"))
    requirements = _as_dict(report.get("protocol_requirements"))
    lines = [
        "# Regular Options Bullish-Pullback Layer4 Forward Capture Protocol",
        "",
        f"Status: `{report.get('capture_protocol_status')}`.",
        "",
        "This is a read-only future paper-shadow capture protocol. It does not collect evidence, append rows, import quotes, mutate evidence stores, create trades, submit broker orders, enable live validation, enable auto-track, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, or promote a lane.",
        "",
        "## Selected Harness",
        "",
        f"- Lane: `{selected.get('lane_id')}`.",
        f"- Layer: `{selected.get('layer_id')}`.",
        f"- Variant: `{selected.get('variant_id')}`.",
        f"- Source run: `{selected.get('source_result_path')}`.",
        f"- Freeze date: `{selected.get('freeze_date')}`.",
        f"- Allowed symbols: `{_json_inline(selected.get('allowed_symbols'))}`.",
        "",
        "## Historical Context",
        "",
        f"- Historical executable status: `{econ.get('status')}`.",
        f"- Harness decision: `{econ.get('harness_decision')}`.",
        f"- Tradable executable rows: `{econ.get('tradable_executable_rows')}`.",
        f"- Side-aware PF: `{econ.get('historical_side_aware_pf')}`.",
        f"- Side-aware PF lower bound 5pct: `{econ.get('historical_side_aware_pf_lb_5pct')}`.",
        f"- Historical rows are forward proof: `{str(bool(report.get('historical_rows_are_forward_proof'))).lower()}`.",
        "",
        "## Protocol Requirements",
        "",
    ]
    for key, value in sorted(requirements.items()):
        lines.append(f"- `{key}`: `{_json_inline(value)}`.")
    lines.extend(["", "## Blockers", ""])
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- None for protocol readiness. Actual row collection still requires a future market-data window and separate operator approval.")
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.append("")
    return "\n".join(lines)


def render_approval_packet(report: dict[str, Any]) -> str:
    selected = _as_dict(report.get("selected_harness"))
    return "\n".join(
        [
            "# Bullish-Pullback Layer4 Forward Paper-Shadow Approval Packet",
            "",
            "This packet is informational until a future valid market-data window. It does not approve appending rows by itself.",
            "",
            "Approval, if later granted, is limited to append-only full-denominator paper-shadow candidate rows for:",
            "",
            f"- lane: `{selected.get('lane_id')}`",
            f"- layer: `{selected.get('layer_id')}`",
            f"- variant: `{selected.get('variant_id')}`",
            f"- allowed symbols: `{_json_inline(selected.get('allowed_symbols'))}`",
            "",
            "Any future approval must still forbid broker orders, live validation, auto-track, quote import, historical repair, scanner/strategy/stop/sizing/proof-bar changes, protected-holdout consumption, evidence-store mutation outside the approved append path, and promotion.",
            "",
            "Before approval, candidate rows must pass the read-only validator and report `cohort_append_performed=false`.",
            "",
        ]
    )


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT, approval_packet: Path = DEFAULT_APPROVAL_PACKET) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    approval_packet.parent.mkdir(parents=True, exist_ok=True)
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
        "approval_packet": _rel(approval_packet),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    approval_packet.write_text(render_approval_packet(report), encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build bullish-pullback layer4 forward capture protocol.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--execution-safety", type=Path, default=DEFAULT_EXECUTION_SAFETY)
    parser.add_argument("--executable-economics", type=Path, default=DEFAULT_EXECUTABLE_ECONOMICS)
    parser.add_argument("--approval-packet", type=Path, default=DEFAULT_APPROVAL_PACKET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        selection_path=args.selection,
        execution_safety_path=args.execution_safety,
        executable_economics_path=args.executable_economics,
        approval_packet_path=args.approval_packet,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report, approval_packet=args.approval_packet)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
