from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "bullish_pullback_layer_shadow_selection"

DEFAULT_LAYER_STACK = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "layer-stack" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "bullish-pullback-layer-shadow-selection.md"
MAX_SOURCE_AGE_HOURS = 720

PRIMARY_LAYER_ID = "layer_4_clean_exact"
COUNT_EXPANDED_LAYER_ID = "layer_5_count_expanded"
HIGH_PF_CORE_LAYER_ID = "layer_0_confidence_core_s_a_b"

ALLOWED_SYMBOLS = ("IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM")

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_bullish_pullback_layer_shadow_selection",
    "do_not_submit_broker_orders_from_bullish_pullback_layer_shadow_selection",
    "do_not_enable_live_validation_from_bullish_pullback_layer_shadow_selection",
    "do_not_enable_auto_track_from_bullish_pullback_layer_shadow_selection",
    "do_not_change_scanner_policy_from_bullish_pullback_layer_shadow_selection",
    "do_not_change_strategy_logic_from_bullish_pullback_layer_shadow_selection",
    "do_not_change_stops_from_bullish_pullback_layer_shadow_selection",
    "do_not_change_sizing_from_bullish_pullback_layer_shadow_selection",
    "do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_shadow_selection",
    "do_not_mutate_evidence_databases_from_bullish_pullback_layer_shadow_selection",
    "do_not_import_quotes_from_bullish_pullback_layer_shadow_selection",
    "do_not_append_forward_cohort_rows_from_bullish_pullback_layer_shadow_selection",
    "do_not_consume_protected_holdout_from_bullish_pullback_layer_shadow_selection",
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
        return path.name


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_layer_stack(
    path: Path,
    *,
    generated_at_utc: str,
    max_source_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": True,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": ["missing_layer_stack"],
        "error": None,
    }
    if not path.exists():
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source["status"] = "malformed"
        source["reason_codes"] = ["malformed_layer_stack"]
        source["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, source
    except OSError as exc:
        source["status"] = "unreadable"
        source["reason_codes"] = ["unreadable_layer_stack"]
        source["error"] = type(exc).__name__
        return {}, source
    if not isinstance(payload, dict):
        source["status"] = "invalid"
        source["reason_codes"] = ["json_root_not_object"]
        return {}, source

    source_generated = payload.get("generated_at_utc") or payload.get("generated_at")
    source["generated_at_utc"] = source_generated
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    source_dt = _parse_utc(source_generated)
    if source_dt is None:
        source["status"] = "invalid"
        source["reason_codes"] = ["missing_or_malformed_generated_at"]
        return payload, source
    age_hours = (as_of - source_dt).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        source["status"] = "invalid"
        source["reason_codes"] = ["layer_stack_generated_in_future"]
        return payload, source
    if age_hours > max_source_age_hours:
        source["status"] = "stale"
        source["reason_codes"] = ["stale_layer_stack"]
        return payload, source
    source["status"] = "loaded"
    source["reason_codes"] = []
    return payload, source


def _layers_by_id(layer_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for row in _as_list(layer_stack.get("ordered_layers")):
        if isinstance(row, dict):
            layer_id = _norm(row.get("layer_id"))
            if layer_id:
                layers[layer_id] = row
    return layers


def _metric(layer: dict[str, Any], name: str) -> Any:
    return _as_dict(layer.get("metrics")).get(name)


def _status(blockers: list[str]) -> str:
    return "layer_shadow_selection_ready" if not blockers else "blocked_layer_shadow_selection"


def _metric_blockers(layer: dict[str, Any], expected: dict[str, Any], *, prefix: str) -> list[str]:
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = _metric(layer, key)
        if isinstance(expected_value, float):
            parsed = _safe_float(actual)
            if parsed is None or round(parsed, 2) != round(expected_value, 2):
                blockers.append(f"{prefix}_{key}_expected_{expected_value}_got_{actual}")
        elif isinstance(expected_value, int):
            parsed_int = _safe_int(actual)
            if parsed_int != expected_value:
                blockers.append(f"{prefix}_{key}_expected_{expected_value}_got_{actual}")
        else:
            if actual != expected_value:
                blockers.append(f"{prefix}_{key}_expected_{expected_value}_got_{actual}")
    return blockers


def _layer_summary(layer: dict[str, Any], *, role: str, status: str) -> dict[str, Any]:
    metrics = _as_dict(layer.get("metrics"))
    return {
        "layer_id": layer.get("layer_id"),
        "variant_id": layer.get("variant_id"),
        "role": role,
        "status": status,
        "decision": layer.get("decision"),
        "source_result_path": layer.get("source_result_path"),
        "source_robustness_path": layer.get("source_robustness_path"),
        "next_action": layer.get("next_action"),
        "metrics": {
            "candidate_trade_count": metrics.get("candidate_trade_count"),
            "exact_trade_count": metrics.get("exact_trade_count"),
            "profit_factor": metrics.get("profit_factor"),
            "quote_coverage_pct": metrics.get("quote_coverage_pct"),
            "stress_5pct_per_side_profit_factor": metrics.get("stress_5pct_per_side_profit_factor"),
            "rolling_status": metrics.get("rolling_status"),
            "rolling_first_test_profit_factor": metrics.get("rolling_first_test_profit_factor"),
            "unpriced_trade_count": metrics.get("unpriced_trade_count"),
            "avg_pnl_pct": metrics.get("avg_pnl_pct"),
        },
        "gate_read": layer.get("gate_read"),
    }


def _harness_requirements(primary_layer: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_layer_id": primary_layer.get("layer_id"),
        "selected_variant_id": primary_layer.get("variant_id"),
        "source_result_path": primary_layer.get("source_result_path"),
        "allowed_symbols": list(ALLOWED_SYMBOLS),
        "future_evidence_posture": "future_natural_market_window_paper_shadow_collection_only",
        "exact_entry_quote_required": True,
        "policy_defined_exact_exit_required": True,
        "leg_level_bid_ask_audit_required": True,
        "assignment_expiration_risk_review_required": True,
        "denominator_failure_row_handling_required": True,
        "entry_exit_quote_source": "trusted exact OPRA/NBBO bid/ask only",
        "paper_shadow_only": True,
        "is_trade_recommendation": False,
        "is_broker_order": False,
    }


def build_report(
    *,
    layer_stack_path: Path = DEFAULT_LAYER_STACK,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    layer_stack, source = _load_layer_stack(
        layer_stack_path,
        generated_at_utc=generated_at,
        max_source_age_hours=max_source_age_hours,
    )
    blockers: list[str] = []
    if source["status"] != "loaded":
        blockers.extend(source["reason_codes"])
    if layer_stack and layer_stack.get("paper_shadow_only") is not True:
        blockers.append("layer_stack_not_paper_shadow_only")

    layers = _layers_by_id(layer_stack)
    for required_id in (PRIMARY_LAYER_ID, COUNT_EXPANDED_LAYER_ID, HIGH_PF_CORE_LAYER_ID):
        if required_id not in layers:
            blockers.append(f"missing_required_layer:{required_id}")

    primary = layers.get(PRIMARY_LAYER_ID, {})
    count_expanded = layers.get(COUNT_EXPANDED_LAYER_ID, {})
    high_pf_core = layers.get(HIGH_PF_CORE_LAYER_ID, {})

    if primary:
        blockers.extend(
            _metric_blockers(
                primary,
                {
                    "candidate_trade_count": 129,
                    "exact_trade_count": 129,
                    "profit_factor": 2.20,
                    "quote_coverage_pct": 100.0,
                    "stress_5pct_per_side_profit_factor": 1.67,
                    "rolling_status": "passed",
                    "unpriced_trade_count": 0,
                },
                prefix="primary_layer",
            )
        )
    if count_expanded:
        blockers.extend(
            _metric_blockers(
                count_expanded,
                {
                    "candidate_trade_count": 133,
                    "exact_trade_count": 130,
                    "profit_factor": 2.04,
                    "quote_coverage_pct": 97.7,
                    "stress_5pct_per_side_profit_factor": 1.53,
                    "unpriced_trade_count": 3,
                },
                prefix="count_expanded_layer",
            )
        )
    if high_pf_core:
        blockers.extend(
            _metric_blockers(
                high_pf_core,
                {
                    "exact_trade_count": 108,
                    "profit_factor": 4.86,
                },
                prefix="high_pf_core_layer",
            )
        )
        symbols = tuple(_norm(symbol).upper() for symbol in _as_list(high_pf_core.get("symbols")))
        if symbols != ALLOWED_SYMBOLS:
            blockers.append("high_pf_core_symbols_do_not_match_allowed_carrier_set")

    target_read = _as_dict(layer_stack.get("target_read"))
    target_truth = {
        "preferred_target_exact_trades": target_read.get("preferred_target_exact_trades"),
        "current_best_exact_trades": target_read.get("current_best_exact_trades"),
        "gap_to_200": target_read.get("gap_to_200"),
        "honest_status": target_read.get("honest_status"),
    }
    expected_target_truth = {
        "preferred_target_exact_trades": 200,
        "current_best_exact_trades": 130,
        "gap_to_200": 70,
        "honest_status": "not_reached",
    }
    for key, expected in expected_target_truth.items():
        if target_truth.get(key) != expected:
            blockers.append(f"target_truth_{key}_expected_{expected}_got_{target_truth.get(key)}")

    overall_status = _status(blockers)
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "bullish_pullback_layer_stack_to_paper_shadow_harness_selection",
        "read_only": True,
        "paper_shadow_only": True,
        "source_artifacts": {"bullish_pullback_layer_stack": source},
        "overall_status": overall_status,
        "selection_ready": overall_status == "layer_shadow_selection_ready",
        "blockers": blockers,
        "primary_harness_layer": _layer_summary(
            primary,
            role="primary_clean_harness_layer",
            status="selected_primary_clean_harness_layer" if primary else "missing",
        ),
        "count_expanded_reference": _layer_summary(
            count_expanded,
            role="count_expanded_reference",
            status="count_expanded_reference_blocked_by_unpriced_candidates" if count_expanded else "missing",
        ),
        "high_pf_core_reference": _layer_summary(
            high_pf_core,
            role="high_pf_core_queue_reference",
            status="high_pf_core_reference_with_provenance_caveat" if high_pf_core else "missing",
        ),
        "allowed_symbols": list(ALLOWED_SYMBOLS),
        "target_truth": target_truth,
        "harness_requirements": _harness_requirements(primary),
        "mutated_evidence_databases": False,
        "imported_quotes": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_broker_behavior": False,
        "changed_auto_track_behavior": False,
        "changed_live_validation": False,
        "promotion_ready": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "is_trade_recommendation": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    primary = _as_dict(report.get("primary_harness_layer"))
    count_ref = _as_dict(report.get("count_expanded_reference"))
    core = _as_dict(report.get("high_pf_core_reference"))
    lines = [
        "# Bullish Pullback Layer Shadow Selection",
        "",
        "No live release. This read-only report selects the bullish-pullback paper-shadow harness layer for future natural market-window evidence collection.",
        "",
        "## At a glance",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Selection ready: `{str(bool(report.get('selection_ready'))).lower()}`.",
        f"- Paper-shadow only: `{str(bool(report.get('paper_shadow_only'))).lower()}`.",
        f"- Live entry allowed: `{str(bool(report.get('live_entry_allowed'))).lower()}`.",
        f"- Auto-track allowed: `{str(bool(report.get('auto_track_allowed'))).lower()}`.",
        f"- Broker order allowed: `{str(bool(report.get('broker_order_allowed'))).lower()}`.",
        f"- Trade recommendation: `{str(bool(report.get('is_trade_recommendation'))).lower()}`.",
        "",
        "## Harness Selection",
        "",
        "| Role | Layer | Variant | Status | Exact | PF | Coverage | Stress PF | Unpriced |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (primary, count_ref, core):
        metrics = _as_dict(row.get("metrics"))
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("role")),
                    _fmt(row.get("layer_id")),
                    _fmt(row.get("variant_id")),
                    _fmt(row.get("status")),
                    _fmt(metrics.get("exact_trade_count")),
                    _fmt(metrics.get("profit_factor")),
                    _fmt(metrics.get("quote_coverage_pct")),
                    _fmt(metrics.get("stress_5pct_per_side_profit_factor")),
                    _fmt(metrics.get("unpriced_trade_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Target Truth",
            "",
            f"- Preferred target exact trades: `{_as_dict(report.get('target_truth')).get('preferred_target_exact_trades')}`.",
            f"- Current best exact trades: `{_as_dict(report.get('target_truth')).get('current_best_exact_trades')}`.",
            f"- Gap to 200: `{_as_dict(report.get('target_truth')).get('gap_to_200')}`.",
            f"- Honest status: `{_as_dict(report.get('target_truth')).get('honest_status')}`.",
            "",
            "## Allowed Symbols",
            "",
            f"`{', '.join(_as_list(report.get('allowed_symbols')))}`",
            "",
            "## Harness Requirements",
            "",
        ]
    )
    for key, value in sorted(_as_dict(report.get("harness_requirements")).items()):
        lines.append(f"- `{key}`: `{value}`.")
    lines.extend(["", "## Blockers", ""])
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(f"- `{item}`." for item in blockers)
    else:
        lines.append("- None.")
    lines.extend(["", "## Prohibited Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only bullish-pullback layer shadow harness selection.")
    parser.add_argument("--layer-stack", type=Path, default=DEFAULT_LAYER_STACK)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        layer_stack_path=args.layer_stack,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
