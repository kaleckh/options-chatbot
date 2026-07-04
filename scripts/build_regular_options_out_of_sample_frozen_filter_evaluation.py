from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    DEFAULT_CONSUMPTION_REGISTRY,
    _accepted_rows,
    _as_dict,
    _as_list,
    _bootstrap_dict,
    _dedupe_rows,
    _dedupe_summary,
    _field_value,
    _filter_rows,
    _load_jsonl,
    _metrics,
    _month_key,
    _safe_float,
)


REPORT_ID = "regular_options_out_of_sample_frozen_filter_evaluation"
DEFAULT_CONTRACT = ROOT / "data" / "contracts" / "regular-options-out-of-sample-extension-v1.json"
DEFAULT_SELECTED_CANDIDATES = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-out-of-sample-extension"
    / "frozen-candidate-generation-engine"
    / "selected_candidates.jsonl"
)
DEFAULT_MATERIALIZER_REPORT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-out-of-sample-extension"
    / "frozen-candidate-generation-engine"
    / "latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-out-of-sample-frozen-filter-evaluation"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-out-of-sample-frozen-filter-evaluation.md"

FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "forward_rows_are_profitability_proof": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "lane_promotion_authorized": False,
}

PROHIBITED_ACTIONS = [
    "do_not_select_filters_on_out_of_sample_window",
    "do_not_iterate_filter_thresholds_on_out_of_sample_window",
    "do_not_add_filter_family_from_out_of_sample_window",
    "do_not_change_scanner_policy_from_out_of_sample_window",
    "do_not_change_stops_sizing_or_proof_bars_from_out_of_sample_window",
    "do_not_enable_live_validation_or_auto_track",
    "do_not_submit_broker_orders",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "malformed", "error": f"{exc.lineno}:{exc.colno}"}
    return payload if isinstance(payload, dict) else {}, {"path": _rel(path), "exists": True, "status": "loaded"}


def _load_registry(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, meta = _load_json(path)
    if not payload:
        payload = {"report_id": "regular_options_audit_window_consumption_registry", "schema_version": 1, "entries": []}
    payload.setdefault("entries", [])
    return payload, meta


def _conditions_sha256(conditions: Sequence[Any]) -> str:
    return hashlib.sha256(json.dumps(list(conditions), sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def _month_range(start_month: str, end_month: str) -> list[str]:
    year, month = (int(part) for part in start_month.split("-"))
    end_year, end_m = (int(part) for part in end_month.split("-"))
    result: list[str] = []
    while (year, month) <= (end_year, end_m):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return result


def _row_date(row: dict[str, Any]) -> str:
    return str(row.get("entry_date") or row.get("candidate_generation_date") or row.get("date") or "")[:10]


def _target_months(contract: dict[str, Any]) -> list[str]:
    window = _as_dict(contract.get("target_window"))
    start = str(window.get("requested_start_month") or str(window.get("requested_start_date") or "2022-01")[:7])
    end = str(window.get("requested_end_month") or str(window.get("requested_end_date") or "2024-05")[:7])
    return _month_range(start, end)


def _materializer_covered_months(materializer: dict[str, Any]) -> list[str]:
    coverage = _as_dict(materializer.get("calendar_coverage") or materializer.get("coverage"))
    for key in ("calendar_months_covered", "covered_months", "requested_months_covered"):
        months = [str(item) for item in _as_list(coverage.get(key)) if str(item)]
        if months:
            return sorted(set(months))
    selected = _as_dict(materializer.get("selected_trade_summary")).get("selected_entry_months_with_rows")
    return sorted(set(str(item) for item in _as_list(selected) if str(item)))


def _gate_passes(metrics: dict[str, Any], gates: dict[str, Any]) -> tuple[bool, list[str]]:
    percent_lb = _safe_float(_bootstrap_dict(metrics, "bootstrap_cluster").get("pf_lb_5pct"))
    usd_lb = _safe_float(_bootstrap_dict(metrics, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    net_usd = _safe_float(metrics.get("total_net_pnl_usd"))
    blockers: list[str] = []
    if int(metrics.get("exact_trade_count") or 0) <= 0:
        blockers.append("out_of_sample_exact_trades_below_1")
    if int(metrics.get("net_pnl_usd_trade_count") or 0) != int(metrics.get("exact_trade_count") or 0):
        blockers.append("out_of_sample_net_pnl_usd_missing")
    if percent_lb is None or percent_lb <= _safe_float(gates.get("percent_cluster_pf_lb_5pct_must_be_gt")):
        blockers.append("out_of_sample_percent_cluster_pf_lb_not_above_1")
    if usd_lb is None or usd_lb <= _safe_float(gates.get("usd_cluster_pf_lb_5pct_must_be_gt")):
        blockers.append("out_of_sample_usd_cluster_pf_lb_not_above_1")
    if net_usd is None or net_usd <= _safe_float(gates.get("total_net_pnl_usd_must_be_gt")):
        blockers.append("out_of_sample_total_net_pnl_usd_not_positive")
    return not blockers, blockers


def _coverage_summary(rows: Sequence[dict[str, Any]], months: Sequence[str]) -> dict[str, Any]:
    by_month = Counter(_month_key(row) for row in rows if _month_key(row))
    by_ticker = Counter(str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "") for row in rows)
    return {
        "row_count": len(rows),
        "month_count": len({month for month in by_month if month}),
        "requested_months": list(months),
        "by_month": dict(sorted(by_month.items())),
        "by_ticker": dict(sorted((key, value) for key, value in by_ticker.items() if key)),
    }


def _append_consumption(report: dict[str, Any], registry_path: Path) -> bool:
    registry, _meta = _load_registry(registry_path)
    target_months = _as_list(_as_dict(report.get("evaluation_window")).get("requested_months"))
    entries = _as_list(registry.get("entries"))
    for entry in entries:
        entry = _as_dict(entry)
        if entry.get("consumed_by") == REPORT_ID and _as_list(entry.get("window_months")) == target_months:
            return False
    entry = {
        "window_months": target_months,
        "evaluated_months": _as_list(_as_dict(report.get("evaluation_window")).get("evaluated_full_months")),
        "excluded_or_missing_months": _as_list(_as_dict(report.get("evaluation_window")).get("excluded_or_missing_months")),
        "disposition": "consumed_for_evaluation",
        "consumed_by": REPORT_ID,
        "consumed_at_utc": report.get("generated_at_utc"),
        "contract_id": report.get("contract_id"),
        "accepted_filter_id": _as_dict(report.get("frozen_policy")).get("filter_id"),
        "conditions_sha256": _as_dict(report.get("frozen_policy")).get("conditions_sha256"),
        "selection_permitted": False,
        "filter_iteration_permitted": False,
        "threshold_change_permitted": False,
        "new_filter_family_permitted": False,
        "verdict": report.get("verdict"),
        "status": report.get("status"),
    }
    registry["entries"] = entries + [entry]
    registry.setdefault("report_id", "regular_options_audit_window_consumption_registry")
    registry.setdefault("schema_version", 1)
    registry["updated_at_utc"] = _utc_now_iso()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return True


def build_report(
    *,
    selected_candidates_path: Path = DEFAULT_SELECTED_CANDIDATES,
    materializer_report_path: Path = DEFAULT_MATERIALIZER_REPORT,
    contract_path: Path = DEFAULT_CONTRACT,
    consumption_registry_path: Path = DEFAULT_CONSUMPTION_REGISTRY,
    record_consumption: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    contract, contract_meta = _load_json(contract_path)
    materializer, materializer_meta = _load_json(materializer_report_path)
    raw_rows, selected_meta = _load_jsonl(selected_candidates_path)
    registry, registry_meta = _load_registry(consumption_registry_path)
    policy = _as_dict(contract.get("frozen_policy"))
    conditions = _as_list(policy.get("conditions"))
    expected_hash = str(policy.get("conditions_sha256") or "")
    computed_hash = _conditions_sha256(conditions) if conditions else ""
    target_months = _target_months(contract)
    covered_months = _materializer_covered_months(materializer)
    evaluated_months = [month for month in target_months if month in set(covered_months)]
    excluded_months = [month for month in target_months if month not in set(evaluated_months)]

    rows_before_dedupe = _accepted_rows(raw_rows)
    accepted = _dedupe_rows(rows_before_dedupe)
    in_target_window = [row for row in accepted if _month_key(row) in set(target_months)]
    rows_for_evaluation = [row for row in in_target_window if _month_key(row) in set(evaluated_months)]
    excluded_rows = [row for row in in_target_window if _month_key(row) not in set(evaluated_months)]
    filtered_rows = _filter_rows(rows_for_evaluation, {"conditions": conditions}) if conditions else []
    gates = _as_dict(contract.get("gates"))
    bootstrap_draws = int(gates.get("bootstrap_draws") or 10000)
    metrics = _metrics(filtered_rows, branch_id=REPORT_ID, bootstrap_draws=bootstrap_draws)
    gates_passed, gate_blockers = _gate_passes(metrics, gates)

    blockers: list[str] = []
    if contract_meta.get("status") != "loaded":
        blockers.append("out_of_sample_contract_not_loaded")
    if materializer_meta.get("status") != "loaded":
        blockers.append("out_of_sample_materializer_report_not_loaded")
    if selected_meta.get("status") != "loaded":
        blockers.append("selected_candidates_jsonl_not_loaded")
    if expected_hash != computed_hash:
        blockers.append("frozen_policy_conditions_sha256_mismatch")
    if not evaluated_months:
        blockers.append("no_full_out_of_sample_months_available_for_evaluation")
    blockers.extend(gate_blockers)
    blockers = list(dict.fromkeys(blockers))
    passed = bool(not blockers and gates_passed)
    interpretation = _as_dict(contract.get("interpretation"))
    verdict = str(
        interpretation.get("passing_verdict" if passed else "failure_verdict")
        or ("historically_consistent_still_awaiting_forward_bar" if passed else "park_filter_hypothesis_tracker_may_continue")
    )
    status = "out_of_sample_frozen_filter_passed" if passed else "out_of_sample_frozen_filter_parked"

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at,
        "schema_version": 1,
        "status": status,
        "verdict": verdict,
        "contract_id": contract.get("contract_id"),
        "contract": contract_meta,
        "materializer": materializer_meta,
        "selected_candidates": selected_meta,
        "consumption_registry": registry_meta,
        "frozen_policy": {
            "policy_id": policy.get("policy_id"),
            "filter_id": policy.get("filter_id"),
            "conditions": conditions,
            "conditions_sha256": expected_hash,
            "computed_conditions_sha256": computed_hash,
            "hash_verified": expected_hash == computed_hash,
        },
        "evaluation_window": {
            "requested_months": target_months,
            "materializer_covered_months": covered_months,
            "evaluated_full_months": evaluated_months,
            "excluded_or_missing_months": excluded_months,
            "partial_month_policy": "excluded_and_reported_never_padded",
            "new_months_only": True,
        },
        "row_counts": {
            "raw_selected_candidate_rows": len(raw_rows),
            "accepted_rows_before_dedupe": len(rows_before_dedupe),
            "accepted_rows_after_dedupe": len(accepted),
            "in_requested_window_rows": len(in_target_window),
            "excluded_rows_from_missing_or_partial_months": len(excluded_rows),
            "rows_for_frozen_policy_evaluation": len(rows_for_evaluation),
            "frozen_filter_exact_rows": len(filtered_rows),
        },
        "dedupe_summary": _dedupe_summary(len(rows_before_dedupe), len(accepted)),
        "coverage_summaries": {
            "rows_for_evaluation": _coverage_summary(rows_for_evaluation, evaluated_months),
            "frozen_filter_rows": _coverage_summary(filtered_rows, evaluated_months),
            "excluded_rows": _coverage_summary(excluded_rows, excluded_months),
        },
        "metrics": metrics,
        "gates": gates,
        "gates_passed": passed,
        "blockers": blockers,
        "registry_append_requested": bool(record_consumption),
        "registry_appended": False,
        "existing_registry_entry_count": len(_as_list(registry.get("entries"))),
        "selection_permitted": False,
        "filter_iteration_permitted": False,
        "threshold_change_permitted": False,
        "new_filter_family_permitted": False,
        "prohibited_actions": PROHIBITED_ACTIONS,
        **FALSE_FLAGS,
    }
    if record_consumption:
        report["registry_appended"] = _append_consumption(report, consumption_registry_path)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    window = _as_dict(report.get("evaluation_window"))
    metrics = _as_dict(report.get("metrics"))
    percent_lb = _bootstrap_dict(metrics, "bootstrap_cluster").get("pf_lb_5pct")
    usd_lb = _bootstrap_dict(metrics, "bootstrap_usd_cluster").get("pf_lb_5pct")
    lines = [
        "# Regular Options Out-of-Sample Frozen Filter Evaluation",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Verdict: `{report.get('verdict')}`.",
        f"- Evaluated full months: `{len(_as_list(window.get('evaluated_full_months')))}` / `{len(_as_list(window.get('requested_months')))}`.",
        f"- Excluded or missing months: `{len(_as_list(window.get('excluded_or_missing_months')))}`.",
        f"- Frozen filter exact rows: `{_as_dict(report.get('row_counts')).get('frozen_filter_exact_rows')}`.",
        f"- Percent cluster PF LB 5pct: `{percent_lb}`.",
        f"- USD cluster PF LB 5pct: `{usd_lb}`.",
        f"- Total net PnL USD: `{metrics.get('total_net_pnl_usd')}`.",
        f"- Registry appended: `{str(report.get('registry_appended')).lower()}`.",
        "",
        "This is a one-shot frozen-contract evaluation only. It does not select, iterate, tune, or authorize trading.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers"))) if report.get("blockers") else lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-shot Phase 15.3 frozen filter out-of-sample evaluation.")
    parser.add_argument("--selected-candidates", type=Path, default=DEFAULT_SELECTED_CANDIDATES)
    parser.add_argument("--materializer-report", type=Path, default=DEFAULT_MATERIALIZER_REPORT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--consumption-registry", type=Path, default=DEFAULT_CONSUMPTION_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-record-consumption", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        selected_candidates_path=args.selected_candidates,
        materializer_report_path=args.materializer_report,
        contract_path=args.contract,
        consumption_registry_path=args.consumption_registry,
        record_consumption=not args.no_record_consumption,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
