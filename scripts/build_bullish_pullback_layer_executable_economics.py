from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_bullish_pullback_layer_execution_safety_audit import (  # noqa: E402
    EXPECTED_METRICS,
    PRIMARY_LAYER_ID,
    PRIMARY_VARIANT_ID,
)
from scripts.evaluate_regular_options_autoresearch import bootstrap_confidence_for_values  # noqa: E402


REPORT_ID = "bullish_pullback_layer_executable_economics"

DEFAULT_EXECUTION_SAFETY_AUDIT = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_execution_safety_audit_latest.json"
DEFAULT_SELECTED_SOURCE_RUN = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-bullish-pullback-layer-executable-economics.md"

CONTRACT_MULTIPLIER = 100.0
DEFAULT_FEE_TOTAL_USD = 2.60
BOOTSTRAP_DRAWS = 10_000

STATUS_PROFITABLE_BUT_BLOCKED = "executable_economics_recomputed_profitable_but_preflight_blocked"
STATUS_NEGATIVE_OR_FLAT = "executable_economics_recomputed_negative_or_flat"
STATUS_MISSING_QUOTES = "executable_economics_recompute_blocked_missing_required_quotes"
STATUS_FEE_UNKNOWN = "executable_economics_recompute_blocked_fee_or_multiplier_unknown"
STATUS_SOURCE_SHAPE_MISSING = "executable_economics_recompute_blocked_source_shape_missing"

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_bullish_pullback_layer_executable_economics",
    "do_not_submit_broker_orders_from_bullish_pullback_layer_executable_economics",
    "do_not_enable_live_validation_from_bullish_pullback_layer_executable_economics",
    "do_not_enable_auto_track_from_bullish_pullback_layer_executable_economics",
    "do_not_change_scanner_policy_from_bullish_pullback_layer_executable_economics",
    "do_not_change_strategy_logic_from_bullish_pullback_layer_executable_economics",
    "do_not_change_stops_from_bullish_pullback_layer_executable_economics",
    "do_not_change_sizing_from_bullish_pullback_layer_executable_economics",
    "do_not_lower_exact_executable_proof_bars_from_bullish_pullback_layer_executable_economics",
    "do_not_mutate_evidence_databases_from_bullish_pullback_layer_executable_economics",
    "do_not_import_quotes_from_bullish_pullback_layer_executable_economics",
    "do_not_append_forward_cohort_rows_from_bullish_pullback_layer_executable_economics",
    "do_not_consume_protected_holdout_from_bullish_pullback_layer_executable_economics",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "required": required, "status": "missing", "error": None}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("run_at")
    return payload, meta


def _candidate_identity(row: dict[str, Any]) -> str:
    return "|".join(
        [
            _norm(row.get("ticker")),
            _norm(row.get("date")),
            _norm(row.get("contract_symbol")),
            _norm(row.get("short_contract_symbol")),
        ]
    )


def _profit_factor(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return None if wins else 0.0
    return sum(wins) / gross_loss


def _round_optional(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _pnl_metrics(values: list[float], *, branch_id: str) -> dict[str, Any]:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    bootstrap = bootstrap_confidence_for_values(values, branch_id=branch_id, draws=BOOTSTRAP_DRAWS) if values else {}
    leave_one_out_pfs = []
    if len(values) > 1:
        for index in range(len(values)):
            pf = _profit_factor(values[:index] + values[index + 1 :])
            if pf is not None:
                leave_one_out_pfs.append(pf)
    total_net = sum(values)
    positive_values = sorted([value for value in values if value > 0], reverse=True)
    largest_winner_share = positive_values[0] / total_net * 100.0 if total_net > 0 and positive_values else None
    top_three_share = sum(positive_values[:3]) / total_net * 100.0 if total_net > 0 and positive_values else None
    return {
        "row_count": len(values),
        "net_usd_total": round(total_net, 2),
        "gross_win_usd": round(gross_win, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "win_rate_pct": round(len(wins) / len(values) * 100.0, 1) if values else 0.0,
        "avg_net_usd": round(total_net / len(values), 2) if values else None,
        "profit_factor": _round_optional(_profit_factor(values), 4),
        "bootstrap": bootstrap,
        "leave_one_out_pf_lower_bound": _round_optional(min(leave_one_out_pfs), 4) if leave_one_out_pfs else None,
        "largest_winner_pct_of_net_profit": _round_optional(largest_winner_share, 2),
        "top_three_winners_pct_of_net_profit": _round_optional(top_three_share, 2),
    }


def _group_dependency(rows: list[dict[str, Any]], values: list[float], key_name: str) -> dict[str, Any]:
    totals: dict[str, float] = defaultdict(float)
    for row, value in zip(rows, values):
        key = _norm(row.get(key_name))
        if key_name == "exit_month":
            key = _norm(row.get("exit_date"))[:7]
        totals[key or "unknown"] += value
    total_net = sum(values)
    if not totals:
        return {"dependency_gate_passed": False, "top_group": None, "top_group_pct_of_net_profit": None}
    top_group, top_value = max(totals.items(), key=lambda item: item[1])
    share = top_value / total_net * 100.0 if total_net > 0 else None
    return {
        "dependency_gate_passed": bool(share is not None and share <= 50.0),
        "top_group": top_group,
        "top_group_net_profit": round(top_value, 2),
        "top_group_pct_of_net_profit": _round_optional(share, 2),
        "single_group_dependency": bool(share is not None and share > 50.0),
    }


def _source_metrics(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in source_rows if (value := _safe_float(row.get("net_pnl_usd"))) is not None]
    return _pnl_metrics(values, branch_id=f"{PRIMARY_VARIANT_ID}:source_marks") if values else {"row_count": 0}


def _row_economics(audit_row: dict[str, Any], source_row: dict[str, Any]) -> dict[str, Any]:
    entry_price = _safe_float(_as_dict(audit_row.get("entry_quote_provenance")).get("side_aware_entry_price"))
    exit_price = _safe_float(_as_dict(audit_row.get("exit_quote_provenance")).get("side_aware_exit_price"))
    fee_total = _safe_float(source_row.get("fee_total_usd"))
    if fee_total is None:
        fee_total = DEFAULT_FEE_TOTAL_USD
    blockers = list(_as_list(audit_row.get("fatal_blockers")))
    status = "executable_priced"
    gross_pnl_usd = None
    net_pnl_usd = None
    net_pnl_pct = None
    capital_at_risk = entry_price * CONTRACT_MULTIPLIER if entry_price is not None and entry_price > 0 else None
    if entry_price is None or exit_price is None:
        status = "missing_required_side_aware_price"
    elif audit_row.get("crossed_or_missing_quote"):
        status = "missing_or_crossed_quote"
    elif audit_row.get("zero_bid_or_untradable"):
        status = "zero_or_untradable"
    else:
        gross_pnl_usd = (exit_price - entry_price) * CONTRACT_MULTIPLIER
        net_pnl_usd = gross_pnl_usd - fee_total
        net_pnl_pct = net_pnl_usd / capital_at_risk * 100.0 if capital_at_risk else None
    return {
        "candidate_identity": audit_row.get("candidate_identity"),
        "ticker": audit_row.get("ticker"),
        "entry_date": audit_row.get("entry_date"),
        "exit_date": audit_row.get("exit_date"),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "fee_total_usd": round(fee_total, 2),
        "contract_multiplier": CONTRACT_MULTIPLIER,
        "gross_pnl_usd": _round_optional(gross_pnl_usd, 2),
        "net_pnl_usd": _round_optional(net_pnl_usd, 2),
        "net_pnl_pct": _round_optional(net_pnl_pct, 2),
        "source_entry_price": _safe_float(_as_dict(audit_row.get("entry_quote_provenance")).get("source_entry_price")),
        "source_exit_price": _safe_float(_as_dict(audit_row.get("exit_quote_provenance")).get("source_exit_price")),
        "source_net_pnl_usd": _safe_float(source_row.get("net_pnl_usd")),
        "source_mark_mismatch": bool(audit_row.get("side_aware_price_mismatch_with_source_run")),
        "zero_bid_or_untradable": bool(audit_row.get("zero_bid_or_untradable")),
        "crossed_or_missing_quote": bool(audit_row.get("crossed_or_missing_quote")),
        "fatal_blockers": blockers,
        "economics_status": status,
    }


def _status(blockers: list[str], metrics: dict[str, Any]) -> str:
    source_shape_prefixes = ("source_shape", "selected_layer_drift", "selected_variant_drift", "selected_source_path_drift", "selected_metric_drift")
    if any(reason.startswith(source_shape_prefixes) or reason.endswith("source_shape_missing") for reason in blockers):
        return STATUS_SOURCE_SHAPE_MISSING
    if "fee_or_multiplier_unknown" in blockers:
        return STATUS_FEE_UNKNOWN
    pf = _safe_float(metrics.get("profit_factor"))
    pf_lb = _safe_float(_as_dict(metrics.get("bootstrap")).get("pf_lb_5pct"))
    total = _safe_float(metrics.get("net_usd_total"))
    no_loss_positive = bool(_as_dict(metrics.get("bootstrap")).get("no_loss_sample")) and total is not None and total > 0
    if total is not None and (total <= 0 or (pf is not None and pf <= 1.0) or (pf is None and not no_loss_positive) or (pf_lb is not None and pf_lb <= 1.0)):
        return STATUS_NEGATIVE_OR_FLAT
    if "missing_required_quotes" in blockers and not metrics.get("row_count"):
        return STATUS_MISSING_QUOTES
    return STATUS_PROFITABLE_BUT_BLOCKED


def build_report(
    *,
    execution_safety_audit_path: Path = DEFAULT_EXECUTION_SAFETY_AUDIT,
    selected_source_run_path: Path = DEFAULT_SELECTED_SOURCE_RUN,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    audit, audit_meta = _load_json(execution_safety_audit_path, required=True)
    source_run, source_meta = _load_json(selected_source_run_path, required=True)
    blockers: list[str] = []
    if audit_meta.get("status") != "loaded" or audit.get("report_id") != "bullish_pullback_layer_execution_safety_audit":
        blockers.append("source_shape_missing_execution_safety_audit")
    if source_meta.get("status") != "loaded":
        blockers.append("source_shape_missing_selected_source_run")

    selected = _as_dict(audit.get("selected_layer"))
    if selected.get("layer_id") != PRIMARY_LAYER_ID:
        blockers.append("selected_layer_drift")
    if selected.get("variant_id") != PRIMARY_VARIANT_ID:
        blockers.append("selected_variant_drift")
    selected_source_path = _norm(selected.get("source_result_path"))
    expected_source_path = _rel(selected_source_run_path)
    if selected_source_path not in {expected_source_path, selected_source_run_path.name}:
        blockers.append("selected_source_path_drift")
    selected_metrics = _as_dict(selected.get("metrics"))
    for key, expected in EXPECTED_METRICS.items():
        actual = selected_metrics.get(key)
        if isinstance(expected, float):
            if _safe_float(actual) is None or round(float(actual), 2) != round(expected, 2):
                blockers.append(f"selected_metric_drift:{key}")
        elif actual is None or int(actual) != int(expected):
            blockers.append(f"selected_metric_drift:{key}")

    audit_rows = [row for row in _as_list(audit.get("audit_rows")) if isinstance(row, dict)]
    source_rows = [row for row in _as_list(source_run.get("trades")) if isinstance(row, dict)]
    source_by_identity = {_candidate_identity(row): row for row in source_rows}
    if len(audit_rows) != EXPECTED_METRICS["exact_trade_count"] or len(source_rows) != EXPECTED_METRICS["exact_trade_count"]:
        blockers.append("source_shape_missing_expected_129_rows")

    economics_rows = [_row_economics(row, source_by_identity.get(_norm(row.get("candidate_identity")), {})) for row in audit_rows]
    resolved_rows = [row for row in economics_rows if row.get("entry_price") is not None and row.get("exit_price") is not None]
    executable_rows = [row for row in economics_rows if row.get("economics_status") == "executable_priced"]
    executable_values = [float(row["net_pnl_usd"]) for row in executable_rows if row.get("net_pnl_usd") is not None]
    if not executable_values:
        blockers.append("missing_required_quotes")
    if any(row.get("economics_status") in {"missing_required_side_aware_price", "missing_or_crossed_quote"} for row in economics_rows):
        blockers.append("missing_required_quotes")
    if any(row.get("economics_status") == "zero_or_untradable" for row in economics_rows):
        blockers.append("zero_or_untradable_rows")
    if any(row.get("source_mark_mismatch") for row in economics_rows):
        blockers.append("source_mark_mismatch_rows")

    executable_metrics = _pnl_metrics(executable_values, branch_id=f"{PRIMARY_VARIANT_ID}:side_aware_executable")
    unique_blockers = sorted(set(blockers))
    status = _status(unique_blockers, executable_metrics)
    if status == STATUS_NEGATIVE_OR_FLAT:
        harness_decision = "rejected_for_current_harness_selection"
    elif status == STATUS_PROFITABLE_BUT_BLOCKED:
        harness_decision = "profitable_but_preflight_blocked"
    else:
        harness_decision = "blocked_before_harness_decision"

    row_status_counts = Counter(str(row.get("economics_status")) for row in economics_rows)
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "bullish_pullback_layer_4_side_aware_executable_economics",
        "read_only": True,
        "paper_shadow_only": True,
        "overall_status": status,
        "harness_decision": harness_decision,
        "source_artifacts": {
            "execution_safety_audit": audit_meta,
            "selected_layer_source_run": source_meta,
        },
        "selected_layer": {
            "layer_id": PRIMARY_LAYER_ID,
            "variant_id": PRIMARY_VARIANT_ID,
            "source_result_path": _rel(selected_source_run_path),
            "source_metrics": selected_metrics,
        },
        "resolver_metrics": {
            "selected_rows": len(audit_rows),
            "parsed_leg_identity_rows": _as_dict(audit.get("row_counts")).get("rows_with_parsed_leg_identity"),
            "trusted_entry_quote_pair_rows": _as_dict(audit.get("row_counts")).get("rows_with_existing_trusted_entry_leg_bid_ask"),
            "trusted_exit_quote_pair_rows": _as_dict(audit.get("row_counts")).get("rows_with_existing_trusted_exit_leg_bid_ask"),
            "side_aware_entry_price_rows": _as_dict(audit.get("row_counts")).get("rows_with_side_aware_entry_price"),
            "side_aware_exit_price_rows": _as_dict(audit.get("row_counts")).get("rows_with_side_aware_exit_price"),
            "zero_or_untradable_rows": _as_dict(audit.get("row_counts")).get("zero_bid_or_untradable_rows"),
            "crossed_or_missing_quote_rows": _as_dict(audit.get("row_counts")).get("crossed_or_missing_quote_rows"),
            "side_aware_price_mismatch_rows": _as_dict(audit.get("row_counts")).get("rows_with_side_aware_price_mismatch"),
        },
        "denominator_views": {
            "resolved_side_aware_only": {
                "row_count": len(resolved_rows),
                "note": "Rows with side-aware entry and exit prices; includes rows that may still be zero/untradable.",
            },
            "tradable_executable_only": executable_metrics,
            "full_selected_fail_closed": {
                "selected_rows": len(economics_rows),
                "resolved_side_aware_rows": len(resolved_rows),
                "tradable_executable_rows": len(executable_rows),
                "missing_required_quote_rows": sum(
                    1 for row in economics_rows if row.get("economics_status") in {"missing_required_side_aware_price", "missing_or_crossed_quote"}
                ),
                "zero_or_untradable_rows": sum(1 for row in economics_rows if row.get("economics_status") == "zero_or_untradable"),
                "source_mark_mismatch_rows": sum(1 for row in economics_rows if row.get("source_mark_mismatch")),
                "row_status_counts": dict(sorted(row_status_counts.items())),
            },
            "source_mark_comparison": {
                "source_mark_metrics": _source_metrics(source_rows),
                "side_aware_executable_metrics": executable_metrics,
                "source_mark_mismatch_rows": sum(1 for row in economics_rows if row.get("source_mark_mismatch")),
                "source_marks_are_diagnostic_only": True,
            },
        },
        "dependency_checks": {
            "ticker": _group_dependency(executable_rows, executable_values, "ticker"),
            "entry_date": _group_dependency(executable_rows, executable_values, "entry_date"),
            "exit_month": _group_dependency(executable_rows, executable_values, "exit_month"),
        },
        "row_counts": {
            "selected_rows": len(economics_rows),
            "resolved_side_aware_rows": len(resolved_rows),
            "tradable_executable_rows": len(executable_rows),
            "missing_required_quote_rows": sum(
                1 for row in economics_rows if row.get("economics_status") in {"missing_required_side_aware_price", "missing_or_crossed_quote"}
            ),
            "zero_or_untradable_rows": sum(1 for row in economics_rows if row.get("economics_status") == "zero_or_untradable"),
            "source_mark_mismatch_rows": sum(1 for row in economics_rows if row.get("source_mark_mismatch")),
        },
        "blockers": unique_blockers,
        "economics_rows": economics_rows,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "is_trade_recommendation": False,
        "mutated_evidence_databases": False,
        "imported_quotes": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "changed_live_validation": False,
        "changed_auto_track_behavior": False,
        "changed_broker_behavior": False,
        "appended_forward_cohort_rows": False,
        "consumed_protected_holdout": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    return report


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    selected = _as_dict(report.get("selected_layer"))
    rows = _as_dict(report.get("row_counts"))
    views = _as_dict(report.get("denominator_views"))
    executable = _as_dict(views.get("tradable_executable_only"))
    lines = [
        "# Regular Options Bullish-Pullback Layer Executable Economics",
        "",
        f"Status: `{report.get('overall_status')}`.",
        "",
        "This is a read-only side-aware executable-economics falsification report. It does not import quotes, mutate evidence stores, create trades, submit broker orders, change scanner policy, change stops/sizing/proof bars, enable live validation, enable auto-track, consume protected holdout, append forward cohort rows, or promote a lane.",
        "",
        "## Selected Harness",
        "",
        f"- Layer: `{selected.get('layer_id')}`.",
        f"- Variant: `{selected.get('variant_id')}`.",
        f"- Source run: `{selected.get('source_result_path')}`.",
        f"- Source metrics: `{_json_inline(selected.get('source_metrics') or {})}`.",
        "",
        "## Result",
        "",
        f"- Harness decision: `{report.get('harness_decision')}`.",
        f"- Row counts: `{_json_inline(rows)}`.",
        f"- Side-aware executable metrics: `{_json_inline(executable)}`.",
        f"- Dependency checks: `{_json_inline(report.get('dependency_checks') or {})}`.",
        "",
        "## Blockers",
        "",
    ]
    blockers = _as_list(report.get("blockers"))
    lines.extend(f"- `{reason}`" for reason in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Denominator Views", ""])
    for name, view in sorted(views.items()):
        lines.append(f"- `{name}`: `{_json_inline(view)}`.")
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only bullish-pullback side-aware executable economics report.")
    parser.add_argument("--execution-safety-audit", type=Path, default=DEFAULT_EXECUTION_SAFETY_AUDIT)
    parser.add_argument("--selected-source-run", type=Path, default=DEFAULT_SELECTED_SOURCE_RUN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        execution_safety_audit_path=args.execution_safety_audit,
        selected_source_run_path=args.selected_source_run,
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
