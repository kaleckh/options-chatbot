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
    DEFAULT_ACCEPTED_RECHECK_DRAWS,
    DEFAULT_AUDIT_MONTHS,
    DEFAULT_SELECTED_CANDIDATES,
    DEFAULT_TRAIN_MONTHS,
    _accepted_rows,
    _as_dict,
    _as_list,
    _bootstrap_dict,
    _dedupe_rows,
    _dedupe_summary,
    _filter_rows,
    _load_json,
    _load_jsonl,
    _metrics,
    _month_key,
    _rel,
    _safe_float,
)
from scripts.build_regular_options_historical_simulated_forward_audit import _split_months  # noqa: E402


REPORT_ID = "regular_options_historical_filtered_simulated_forward_audit"
DEFAULT_FILTER_ITERATION = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-profitability-filter-iteration" / "latest.json"
)
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-historical-filtered-simulated-forward-audit"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-filtered-simulated-forward-audit.md"
MIN_TRAIN_EXACT_TRADES = 100
MIN_AUDIT_EXACT_TRADES = 30
MIN_PF_LB = 1.0

PROHIBITED_ACTIONS = (
    "do_not_change_scanner_policy_from_filtered_historical_audit",
    "do_not_promote_lanes_from_filtered_historical_audit",
    "do_not_enable_live_validation_or_auto_track_from_filtered_historical_audit",
    "do_not_submit_broker_orders_from_filtered_historical_audit",
    "do_not_import_quotes_from_filtered_historical_audit",
    "do_not_mutate_evidence_stores_from_filtered_historical_audit",
    "do_not_lower_proof_bars_from_filtered_historical_audit",
    "do_not_consume_protected_holdout_from_filtered_historical_audit",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _blockers(train: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if int(train.get("exact_trade_count") or 0) < MIN_TRAIN_EXACT_TRADES:
        blockers.append(f"train_exact_trades_below_{MIN_TRAIN_EXACT_TRADES}")
    if int(audit.get("exact_trade_count") or 0) < MIN_AUDIT_EXACT_TRADES:
        blockers.append(f"audit_exact_trades_below_{MIN_AUDIT_EXACT_TRADES}")
    if int(train.get("net_pnl_usd_trade_count") or 0) != int(train.get("exact_trade_count") or 0):
        blockers.append("train_net_pnl_usd_missing")
    if int(audit.get("net_pnl_usd_trade_count") or 0) != int(audit.get("exact_trade_count") or 0):
        blockers.append("audit_net_pnl_usd_missing")
    train_lb = _safe_float(_bootstrap_dict(train, "bootstrap_cluster").get("pf_lb_5pct"))
    audit_lb = _safe_float(_bootstrap_dict(audit, "bootstrap_cluster").get("pf_lb_5pct"))
    train_usd_lb = _safe_float(_bootstrap_dict(train, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    audit_usd_lb = _safe_float(_bootstrap_dict(audit, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    if train_lb is None or train_lb <= MIN_PF_LB:
        blockers.append("train_bootstrap_pf_lb_not_above_1")
    if audit_lb is None or audit_lb <= MIN_PF_LB:
        blockers.append("audit_bootstrap_pf_lb_not_above_1")
    if train_usd_lb is None or train_usd_lb <= MIN_PF_LB:
        blockers.append("train_usd_bootstrap_pf_lb_not_above_1")
    if audit_usd_lb is None or audit_usd_lb <= MIN_PF_LB:
        blockers.append("audit_usd_bootstrap_pf_lb_not_above_1")
    if (_safe_float(train.get("avg_pnl_pct")) or 0.0) <= 0.0:
        blockers.append("train_avg_pnl_not_positive")
    if (_safe_float(audit.get("avg_pnl_pct")) or 0.0) <= 0.0:
        blockers.append("audit_avg_pnl_not_positive")
    if (_safe_float(train.get("total_net_pnl_usd")) or 0.0) <= 0.0:
        blockers.append("train_total_net_pnl_usd_not_positive")
    if (_safe_float(audit.get("total_net_pnl_usd")) or 0.0) <= 0.0:
        blockers.append("audit_total_net_pnl_usd_not_positive")
    return blockers


def _conditions_sha256(conditions: Sequence[Any]) -> str:
    payload = json.dumps(list(conditions), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


def _conditions_text(conditions: Sequence[Any]) -> str:
    rendered = []
    for condition in conditions:
        condition = _as_dict(condition)
        value = condition.get("value")
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        rendered.append(f"{condition.get('field')} {condition.get('op')} {value}")
    return "; ".join(rendered) if rendered else "none"


def _regime_concentration(rows: Sequence[dict[str, Any]], audit_months: Sequence[Any]) -> dict[str, Any]:
    row_count = len(rows)
    by_month = Counter(_month_key(row) for row in rows if _month_key(row))
    by_direction = Counter(str(row.get("direction") or "unknown") for row in rows)
    top_two_count = sum(count for _month, count in by_month.most_common(2))
    top_two_share = round((top_two_count / row_count) * 100.0, 2) if row_count else 0.0
    return {
        "audit_row_count": row_count,
        "audit_months": [str(month) for month in audit_months],
        "rows_by_audit_month": dict(sorted(by_month.items())),
        "direction_mix": dict(sorted(by_direction.items())),
        "top_two_month_row_count": top_two_count,
        "top_two_month_row_share_pct": top_two_share,
        "warning_threshold_pct": 60.0,
        "regime_concentrated": top_two_share > 60.0,
    }


def build_report(
    *,
    selected_candidates_path: Path = DEFAULT_SELECTED_CANDIDATES,
    filter_iteration_path: Path = DEFAULT_FILTER_ITERATION,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    train_months: int = DEFAULT_TRAIN_MONTHS,
    audit_months: int = DEFAULT_AUDIT_MONTHS,
    bootstrap_draws: int = DEFAULT_ACCEPTED_RECHECK_DRAWS,
    filter_rank: int = 1,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    raw_rows, selected_meta = _load_jsonl(selected_candidates_path)
    iteration, iteration_meta = _load_json(filter_iteration_path)
    policy_contract, policy_contract_meta = _load_json(policy_contract_path)
    accepted_filters = [_as_dict(row) for row in _as_list(iteration.get("accepted_filters"))]
    use_frozen_contract = iteration.get("selection_permitted") is False
    if use_frozen_contract:
        contract_conditions = _as_list(policy_contract.get("conditions"))
        selected_filter = {
            "filter_id": policy_contract.get("filter_id"),
            "description": policy_contract.get("description"),
            "conditions": contract_conditions,
        }
        expected_conditions_hash = str(policy_contract.get("conditions_sha256") or "")
        computed_conditions_hash = _conditions_sha256(contract_conditions) if contract_conditions else ""
        filter_source_mode = "frozen_contract"
    else:
        selected_filter = accepted_filters[max(int(filter_rank), 1) - 1] if len(accepted_filters) >= max(int(filter_rank), 1) else {}
        expected_conditions_hash = ""
        computed_conditions_hash = ""
        filter_source_mode = "accepted_filter"
    rows_before_dedupe = _accepted_rows(raw_rows)
    rows = _dedupe_rows(rows_before_dedupe)
    months = sorted({_month_key(row) for row in rows if _month_key(row)})
    split = _split_months(months, train_months=int(train_months), audit_months=int(audit_months))
    train_set = set(_as_list(split.get("train_months")))
    audit_set = set(_as_list(split.get("audit_months")))

    blockers: list[str] = []
    if selected_meta.get("status") != "loaded":
        blockers.append("selected_candidates_jsonl_not_loaded")
    if iteration_meta.get("status") != "loaded":
        blockers.append("filter_iteration_report_not_loaded")
    if use_frozen_contract and policy_contract_meta.get("status") != "loaded":
        blockers.append("frozen_filtered_policy_contract_not_loaded")
    if not selected_filter:
        blockers.append("accepted_filter_not_available")
    if use_frozen_contract and not _as_list(selected_filter.get("conditions")):
        blockers.append("frozen_contract_filter_conditions_missing")
    if use_frozen_contract and not expected_conditions_hash:
        blockers.append("frozen_contract_filter_hash_missing")
    if use_frozen_contract and expected_conditions_hash and computed_conditions_hash and expected_conditions_hash != computed_conditions_hash:
        blockers.append("frozen_contract_filter_hash_mismatch")
    if not split.get("sufficient_months_for_requested_split"):
        blockers.append("insufficient_months_for_requested_split")

    filtered_rows = _filter_rows(rows, selected_filter) if selected_filter else []
    train_filtered = [row for row in filtered_rows if _month_key(row) in train_set]
    audit_filtered = [row for row in filtered_rows if _month_key(row) in audit_set]
    regime_concentration = _regime_concentration(audit_filtered, _as_list(split.get("audit_months")))
    filter_id = str(selected_filter.get("filter_id") or "none")
    train_metrics = _metrics(
        train_filtered,
        branch_id=f"{REPORT_ID}:{filter_id}:train",
        bootstrap_draws=max(int(bootstrap_draws), 1),
    )
    audit_metrics = _metrics(
        audit_filtered,
        branch_id=f"{REPORT_ID}:{filter_id}:audit",
        bootstrap_draws=max(int(bootstrap_draws), 1),
    )
    blockers.extend(_blockers(train_metrics, audit_metrics))
    blockers = sorted(dict.fromkeys(blockers))
    warnings = ["audit_rows_regime_concentrated"] if regime_concentration.get("regime_concentrated") else []
    status = "historical_filtered_simulated_forward_audit_passed" if not blockers else "blocked_historical_filtered_simulated_forward_audit"
    by_month = Counter(_month_key(row) for row in filtered_rows)
    by_ticker = Counter(str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "") for row in filtered_rows)
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "accepted_historical_filtered_audit": not blockers,
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "scanner_policy_changed": False,
        "production_scanner_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "inputs": {
            "selected_candidates_jsonl": selected_meta,
            "filter_iteration": iteration_meta,
            "policy_contract": policy_contract_meta,
        },
        "filter_source": {
            "filter_source_mode": filter_source_mode,
            "source_report_id": policy_contract.get("report_id") if use_frozen_contract else iteration.get("report_id"),
            "source_status": "frozen_contract_loaded" if use_frozen_contract and policy_contract_meta.get("status") == "loaded" else iteration.get("status"),
            "filter_rank": int(filter_rank),
            "filter_id": filter_id,
            "description": selected_filter.get("description"),
            "conditions": _as_list(selected_filter.get("conditions")),
            "conditions_sha256": expected_conditions_hash or None,
            "computed_conditions_sha256": computed_conditions_hash or None,
            "selection_rule": (
                "recompute frozen policy contract filter because historical_profitability_filter_iteration reported selection_permitted=false"
                if use_frozen_contract
                else "consume accepted train-selected filter from historical_profitability_filter_iteration; do not search or tune inside this audit"
            ),
        },
        "selection_conditioned_confidence": {
            "applies": True,
            "raw_audit_cluster_confidence": _bootstrap_dict(audit_metrics, "bootstrap_cluster").get("statistical_confidence"),
            "audit_cluster_confidence_label": (
                "selection_conditioned_positive"
                if _bootstrap_dict(audit_metrics, "bootstrap_cluster").get("statistical_confidence") == "confident_positive"
                else _bootstrap_dict(audit_metrics, "bootstrap_cluster").get("statistical_confidence")
            ),
            "reason": "the v1 frozen filter was selected by a historical train-and-audit gate; audit-window confidence is selection-conditioned",
        },
        "requested_split": {
            "train_months": int(train_months),
            "audit_months": int(audit_months),
            "bootstrap_draws": max(int(bootstrap_draws), 1),
        },
        "split": split,
        "filtered_trade_history": {
            "accepted_exact_candidate_rows_before_filter": len(rows),
            **_dedupe_summary(len(rows_before_dedupe), len(rows)),
            "filtered_exact_candidate_rows": len(filtered_rows),
            "by_month": dict(sorted(by_month.items())),
            "by_ticker": dict(sorted(by_ticker.items())),
        },
        "regime_concentration": regime_concentration,
        "metrics": {
            "train": train_metrics,
            "simulated_forward_audit": audit_metrics,
        },
        "blockers": blockers,
        "warnings": warnings,
        "proof_policy": {
            "readback_is": "canonical filtered historical simulated-forward audit for the accepted train-selected deterministic local PIT filter",
            "readback_is_not": "scanner policy, accepted profitability, fresh forward proof, live validation, broker permission, quote import, proof-bar change, protected-holdout use, or promotion",
            "acceptance_scope": "historical-filtered-audit-only",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def render_markdown(report: dict[str, Any]) -> str:
    source = _as_dict(report.get("filter_source"))
    history = _as_dict(report.get("filtered_trade_history"))
    confidence = _as_dict(report.get("selection_conditioned_confidence"))
    regime = _as_dict(report.get("regime_concentration"))
    metrics = _as_dict(report.get("metrics"))
    train = _as_dict(metrics.get("train"))
    audit = _as_dict(metrics.get("simulated_forward_audit"))
    lines = [
        "# Regular Options Historical Filtered Simulated Forward Audit",
        "",
        "This generated artifact is the canonical filtered historical simulated-forward audit for the accepted train-selected filter from the profitability filter iteration. It recomputes metrics from selected candidates and does not search, tune, or change scanner policy.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Accepted historical filtered audit: `{report.get('accepted_historical_filtered_audit')}`.",
        f"- Accepted profitability: `{report.get('accepted_profitability')}`.",
        f"- Filter source mode: `{source.get('filter_source_mode')}`.",
        f"- Filter: `{source.get('filter_id')}`.",
        f"- Conditions: {_conditions_text(_as_list(source.get('conditions')))}.",
        f"- Dedupe: `{history.get('accepted_exact_candidate_rows_before_dedupe')}` rows before dedupe, `{history.get('deduped_row_count')}` rows after dedupe, `{history.get('duplicate_rows_removed')}` duplicates removed.",
        f"- Audit confidence label: `{confidence.get('audit_cluster_confidence_label')}`.",
        f"- Bootstrap draws: `{_as_dict(report.get('requested_split')).get('bootstrap_draws')}`.",
        "",
        "## Metrics",
        "",
        "| Window | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% | Confidence Label |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        f"| Train | {train.get('exact_trade_count')} | {train.get('ticker_week_cluster_count')} | {train.get('avg_pnl_pct')} | {train.get('profit_factor')} | {_bootstrap_dict(train, 'bootstrap_iid').get('pf_lb_5pct')} | {_bootstrap_dict(train, 'bootstrap_cluster').get('pf_lb_5pct')} | {train.get('total_net_pnl_usd')} | {train.get('usd_profit_factor')} | {_bootstrap_dict(train, 'bootstrap_usd_cluster').get('pf_lb_5pct')} | `{_bootstrap_dict(train, 'bootstrap_cluster').get('statistical_confidence')}` |",
        f"| Simulated forward audit | {audit.get('exact_trade_count')} | {audit.get('ticker_week_cluster_count')} | {audit.get('avg_pnl_pct')} | {audit.get('profit_factor')} | {_bootstrap_dict(audit, 'bootstrap_iid').get('pf_lb_5pct')} | {_bootstrap_dict(audit, 'bootstrap_cluster').get('pf_lb_5pct')} | {audit.get('total_net_pnl_usd')} | {audit.get('usd_profit_factor')} | {_bootstrap_dict(audit, 'bootstrap_usd_cluster').get('pf_lb_5pct')} | `{confidence.get('audit_cluster_confidence_label')}` |",
    ]
    lines.extend(
        [
            "",
            "## Selection And Regime Disclosure",
            "",
            f"- Raw audit cluster confidence: `{confidence.get('raw_audit_cluster_confidence')}`.",
            f"- Selection-conditioned label: `{confidence.get('audit_cluster_confidence_label')}`.",
            f"- Top two audit-month row share: `{regime.get('top_two_month_row_share_pct')}`%.",
            f"- Direction mix: `{json.dumps(regime.get('direction_mix') or {}, sort_keys=True)}`.",
            "",
            "| Audit Month | Rows |",
            "|---|---:|",
        ]
    )
    for month, count in _as_dict(regime.get("rows_by_audit_month")).items():
        lines.append(f"| `{month}` | {count} |")
    warnings = _as_list(report.get("warnings"))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in warnings)
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This audit accepts or blocks only the historical filtered audit readback. It does not change scanners, authorize paper/live trading, import quotes, mutate evidence stores, lower proof bars, promote lanes, or make historical rows fresh forward proof.",
            "",
        ]
    )
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


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the canonical filtered historical simulated-forward audit.")
    parser.add_argument("--selected-candidates", type=Path, default=DEFAULT_SELECTED_CANDIDATES)
    parser.add_argument("--filter-iteration", type=Path, default=DEFAULT_FILTER_ITERATION)
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS)
    parser.add_argument("--audit-months", type=int, default=DEFAULT_AUDIT_MONTHS)
    parser.add_argument("--bootstrap-draws", type=int, default=DEFAULT_ACCEPTED_RECHECK_DRAWS)
    parser.add_argument("--filter-rank", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        selected_candidates_path=args.selected_candidates,
        filter_iteration_path=args.filter_iteration,
        policy_contract_path=args.policy_contract,
        train_months=max(int(args.train_months), 1),
        audit_months=max(int(args.audit_months), 1),
        bootstrap_draws=max(int(args.bootstrap_draws), 1),
        filter_rank=max(int(args.filter_rank), 1),
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
