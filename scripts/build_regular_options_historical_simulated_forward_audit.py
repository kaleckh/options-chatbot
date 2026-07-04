from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_robust_search_evaluation import (  # noqa: E402
    DEFAULT_FEATURE_STORE_REPORT,
    DEFAULT_SOURCE_QUALITY_POLICY,
    _load_json,
    apply_source_quality_scope_policy,
    normalize_trades,
)
from scripts.evaluate_regular_options_autoresearch import (  # noqa: E402
    block_bootstrap_confidence_for_values,
    bootstrap_confidence_for_values,
)


REPORT_ID = "regular_options_historical_simulated_forward_audit"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-historical-simulated-forward-audit"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-simulated-forward-audit.md"
DEFAULT_SOURCE_REPORT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-source-surface"
    / "latest.json"
)
DEFAULT_TRAIN_MONTHS = 20
DEFAULT_AUDIT_MONTHS = 4
MIN_AUDIT_EXACT_TRADES = 30
MIN_AUDIT_PF_LB = 1.0

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_historical_simulated_forward_audit",
    "do_not_submit_broker_orders_from_historical_simulated_forward_audit",
    "do_not_change_scanner_policy_from_historical_simulated_forward_audit",
    "do_not_change_strategy_logic_from_historical_simulated_forward_audit",
    "do_not_change_stops_or_sizing_from_historical_simulated_forward_audit",
    "do_not_lower_proof_bars_from_historical_simulated_forward_audit",
    "do_not_import_quotes_from_historical_simulated_forward_audit",
    "do_not_mutate_evidence_stores_from_historical_simulated_forward_audit",
    "do_not_consume_protected_forward_holdout_from_historical_simulated_forward_audit",
    "do_not_treat_historical_percent_rows_as_fresh_forward_profit_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


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


def _month_key(row: dict[str, Any]) -> str:
    return str(row.get("entry_date") or "")[:7]


def _ticker_value(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "").strip()


def _cluster_key(row: dict[str, Any]) -> str:
    ticker = _ticker_value(row) or "unknown"
    raw_date = str(row.get("entry_date") or row.get("candidate_generation_date") or row.get("date") or "")[:10]
    try:
        iso = date.fromisoformat(raw_date).isocalendar()
    except ValueError:
        return f"{ticker}:unknown-week"
    return f"{ticker}:{iso.year}-W{iso.week:02d}"


def _dedupe_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str], tuple[tuple[str, str, int], dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        copied = dict(row)
        key = (
            str(copied.get("entry_date") or "")[:10],
            _ticker_value(copied),
            str(copied.get("direction") or "").strip(),
        )
        sort_key = (
            str(copied.get("lane_id") or copied.get("lane") or ""),
            str(copied.get("long_contract_symbol") or ""),
            index,
        )
        current = selected.get(key)
        if current is None or sort_key < current[0]:
            selected[key] = (sort_key, copied)
    return [item[1] for _key, item in sorted(selected.items(), key=lambda pair: pair[0])]


def _dedupe_summary(before_count: int, after_count: int) -> dict[str, int]:
    return {
        "accepted_exact_candidate_rows_before_dedupe": int(before_count),
        "deduped_row_count": int(after_count),
        "duplicate_rows_removed": max(int(before_count) - int(after_count), 0),
    }


def _bootstrap_dict(metrics: dict[str, Any], key: str = "bootstrap_cluster") -> dict[str, Any]:
    return _as_dict(metrics.get(key) or metrics.get("bootstrap_cluster") or metrics.get("bootstrap_iid") or metrics.get("bootstrap"))


def _trade_value(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("pnl_pct"))


def _trade_usd_value(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("net_pnl_usd"))


def _profit_factor(values: Sequence[float]) -> float | None:
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return None
    return sum(wins) / gross_loss


def _round_optional(value: Any, digits: int = 4) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _metrics(rows: Sequence[dict[str, Any]], *, branch_id: str, bootstrap_draws: int) -> dict[str, Any]:
    values = [value for row in rows if (value := _trade_value(row)) is not None]
    clustered_values = [(_cluster_key(row), value) for row in rows if (value := _trade_value(row)) is not None]
    usd_values = [value for row in rows if (value := _trade_usd_value(row)) is not None]
    clustered_usd_values = [(_cluster_key(row), value) for row in rows if (value := _trade_usd_value(row)) is not None]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    usd_wins = [value for value in usd_values if value > 0.0]
    usd_losses = [value for value in usd_values if value < 0.0]
    bootstrap_iid = bootstrap_confidence_for_values(values, branch_id=branch_id, draws=bootstrap_draws)
    bootstrap_cluster = block_bootstrap_confidence_for_values(
        clustered_values,
        branch_id=branch_id,
        draws=bootstrap_draws,
    )
    bootstrap_usd_cluster = block_bootstrap_confidence_for_values(
        clustered_usd_values,
        branch_id=f"{branch_id}:usd",
        draws=bootstrap_draws,
    )
    return {
        "exact_trade_count": len(values),
        "net_pnl_usd_trade_count": len(usd_values),
        "entry_month_count": len({_month_key(row) for row in rows if _month_key(row)}),
        "ticker_week_cluster_count": bootstrap_cluster.get("cluster_count"),
        "first_entry_month": min((_month_key(row) for row in rows if _month_key(row)), default=None),
        "latest_entry_month": max((_month_key(row) for row in rows if _month_key(row)), default=None),
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "win_rate_pct": round((len(wins) / len(values)) * 100.0, 2) if values else 0.0,
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "profit_factor": _round_optional(_profit_factor(values)),
        "total_net_pnl_usd": round(sum(usd_values), 2) if usd_values else None,
        "usd_profit_factor": _round_optional(_profit_factor(usd_values)),
        "gross_win_pct_points": round(sum(wins), 2),
        "gross_loss_pct_points": round(abs(sum(losses)), 2),
        "gross_win_usd": round(sum(usd_wins), 2),
        "gross_loss_usd": round(abs(sum(usd_losses)), 2),
        "bootstrap_iid": bootstrap_iid,
        "bootstrap_cluster": bootstrap_cluster,
        "bootstrap_usd_cluster": bootstrap_usd_cluster,
    }


def _month_rows(rows: Sequence[dict[str, Any]], months: set[str]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if _month_key(row) in months]


def _source_summary(source_report: dict[str, Any], feature_report: dict[str, Any]) -> dict[str, Any]:
    feature_summary = _as_dict(feature_report.get("summary"))
    selected = _as_list(source_report.get("selected_trades"))
    return {
        "source_selected_trade_count": len(selected),
        "candidate_materialization_basis": str(
            source_report.get("candidate_materialization_basis")
            or "deterministic_local_pit_candidate_materializer_v1"
        ),
        "scanner_parity": bool(source_report.get("scanner_parity")) if "scanner_parity" in source_report else False,
        "production_scanner_replay": bool(source_report.get("production_scanner_replay"))
        if "production_scanner_replay" in source_report
        else False,
        "feature_store_status": feature_report.get("status"),
        "feature_store_shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
        "feature_store_first_shared_quote_date_et": feature_summary.get("first_shared_quote_date_et"),
        "feature_store_latest_shared_quote_date_et": feature_summary.get("latest_shared_quote_date_et"),
        "distinction": (
            "trusted quote history can be deeper than selected trade history; this audit splits selected exact trades, "
            "not raw quote rows"
        ),
    }


def _split_months(months: Sequence[str], *, train_months: int, audit_months: int) -> dict[str, Any]:
    ordered = list(months)
    required = int(train_months) + int(audit_months)
    if len(ordered) >= required:
        window = ordered[-required:]
        train = window[:train_months]
        audit = window[train_months:]
    else:
        audit = ordered[-audit_months:] if ordered else []
        train = ordered[: max(len(ordered) - len(audit), 0)]
        window = train + audit
    return {
        "required_month_count": required,
        "available_month_count": len(ordered),
        "window_months": window,
        "train_months": train,
        "audit_months": audit,
        "sufficient_months_for_requested_split": len(ordered) >= required and len(train) >= train_months and len(audit) >= audit_months,
    }


def _coverage_months(source_report: dict[str, Any], row_months: Sequence[str]) -> tuple[list[str], str]:
    coverage = _as_dict(source_report.get("calendar_coverage"))
    explicit = [
        str(item)
        for item in _as_list(coverage.get("covered_months") or coverage.get("calendar_months_covered"))
        if str(item).strip()
    ]
    coverage_status = str(coverage.get("status") or "")
    coverage_basis = str(coverage.get("coverage_basis") or "")
    if explicit:
        if coverage_status == "calendar_coverage_not_proven" or "not_proven" in coverage_basis:
            return list(row_months), "source_calendar_coverage_not_proven"
        return sorted(set(explicit)), "source_explicit_calendar_coverage"
    return list(row_months), "selected_row_months_only"


def _audit_blockers(
    *,
    split: dict[str, Any],
    train_metrics: dict[str, Any],
    audit_metrics: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not split.get("sufficient_months_for_requested_split"):
        blockers.append(
            "selected_trade_months_"
            f"{split.get('available_month_count')}_below_required_{split.get('required_month_count')}"
        )
    if len(_as_list(split.get("train_months"))) < DEFAULT_TRAIN_MONTHS:
        blockers.append(f"train_calendar_months_{len(_as_list(split.get('train_months')))}_below_{DEFAULT_TRAIN_MONTHS}")
    if len(_as_list(split.get("audit_months"))) < DEFAULT_AUDIT_MONTHS:
        blockers.append(f"audit_calendar_months_{len(_as_list(split.get('audit_months')))}_below_{DEFAULT_AUDIT_MONTHS}")
    if int(audit_metrics.get("exact_trade_count") or 0) < MIN_AUDIT_EXACT_TRADES:
        blockers.append(f"audit_exact_trades_{audit_metrics.get('exact_trade_count')}_below_{MIN_AUDIT_EXACT_TRADES}")
    if int(audit_metrics.get("net_pnl_usd_trade_count") or 0) != int(audit_metrics.get("exact_trade_count") or 0):
        blockers.append("audit_net_pnl_usd_missing")
    pf_lb = _safe_float(_bootstrap_dict(audit_metrics, "bootstrap_cluster").get("pf_lb_5pct"))
    if pf_lb is None or pf_lb <= MIN_AUDIT_PF_LB:
        blockers.append("audit_bootstrap_pf_lb_not_above_1")
    usd_pf_lb = _safe_float(_bootstrap_dict(audit_metrics, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    if usd_pf_lb is None or usd_pf_lb <= MIN_AUDIT_PF_LB:
        blockers.append("audit_usd_bootstrap_pf_lb_not_above_1")
    total_usd = _safe_float(audit_metrics.get("total_net_pnl_usd"))
    if total_usd is None or total_usd <= 0:
        blockers.append("audit_total_net_pnl_usd_not_positive")
    avg = _safe_float(audit_metrics.get("avg_pnl_pct"))
    if avg is None or avg <= 0:
        blockers.append("audit_avg_pnl_not_positive")
    return blockers


def build_report(
    *,
    source_report_path: Path = DEFAULT_SOURCE_REPORT,
    feature_store_report_path: Path = DEFAULT_FEATURE_STORE_REPORT,
    source_quality_policy_path: Path | None = DEFAULT_SOURCE_QUALITY_POLICY,
    train_months: int = DEFAULT_TRAIN_MONTHS,
    audit_months: int = DEFAULT_AUDIT_MONTHS,
    bootstrap_draws: int = 10_000,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source_report, source_meta = _load_json(source_report_path)
    feature_report, feature_meta = _load_json(feature_store_report_path)
    policy, policy_meta = (
        _load_json(source_quality_policy_path)
        if source_quality_policy_path
        else ({}, {"status": "missing", "path": None, "exists": False, "error": "policy_not_configured"})
    )
    rows, rejected = normalize_trades(_as_list(source_report.get("selected_trades")))
    source_quality_scoped_rows, source_quality_exclusions = apply_source_quality_scope_policy(
        rows,
        policy=policy,
        policy_meta=policy_meta,
    )
    scoped_rows = _dedupe_rows(source_quality_scoped_rows)
    selected_months = sorted({_month_key(row) for row in scoped_rows if _month_key(row)})
    months, month_coverage_basis = _coverage_months(source_report, selected_months)
    split = _split_months(months, train_months=int(train_months), audit_months=int(audit_months))
    train_set = set(split["train_months"])
    audit_set = set(split["audit_months"])
    train_rows = _month_rows(scoped_rows, train_set)
    audit_rows = _month_rows(scoped_rows, audit_set)
    calendar_coverage = _as_dict(source_report.get("calendar_coverage"))
    zero_selection_months = [
        str(item)
        for item in _as_list(calendar_coverage.get("zero_selection_months"))
        if str(item).strip()
    ]
    split_zero_selection_months = [month for month in split["window_months"] if month in set(zero_selection_months)]
    audit_zero_selection_months = [month for month in split["audit_months"] if month in set(zero_selection_months)]

    train_metrics = _metrics(train_rows, branch_id=f"{REPORT_ID}:train", bootstrap_draws=bootstrap_draws)
    audit_metrics = _metrics(audit_rows, branch_id=f"{REPORT_ID}:audit", bootstrap_draws=bootstrap_draws)
    combined_metrics = _metrics(scoped_rows, branch_id=f"{REPORT_ID}:combined", bootstrap_draws=bootstrap_draws)
    blockers = _audit_blockers(split=split, train_metrics=train_metrics, audit_metrics=audit_metrics)
    blockers.extend(str(item) for item in _as_list(source_report.get("blockers")))
    blockers = sorted(dict.fromkeys(blockers))
    status = "historical_simulated_forward_audit_passed" if not blockers else "blocked_historical_simulated_forward_audit"

    per_month = []
    rows_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audit_rows:
        rows_by_month[_month_key(row)].append(row)
    for month in split["audit_months"]:
        per_month.append(
            {
                "month": month,
                "metrics": _metrics(rows_by_month.get(month, []), branch_id=f"{REPORT_ID}:audit:{month}", bootstrap_draws=bootstrap_draws),
            }
        )

    by_lane = Counter(str(row.get("lane_id") or "unknown") for row in scoped_rows)
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": False,
        "scope": "regular_options_historical_selected_trade_simulated_forward_audit",
        "inputs": {
            "source_report": source_meta,
            "feature_store_report": feature_meta,
            "source_quality_policy": policy_meta,
        },
        "requested_split": {
            "train_months": int(train_months),
            "audit_months": int(audit_months),
            "meaning": "first train months are calibration only; latest audit months are historical simulated-forward audit only",
        },
        "source_summary": _source_summary(source_report, feature_report),
        "candidate_materialization_basis": _source_summary(source_report, feature_report).get(
            "candidate_materialization_basis"
        ),
        "scanner_parity": _source_summary(source_report, feature_report).get("scanner_parity"),
        "production_scanner_replay": _source_summary(source_report, feature_report).get("production_scanner_replay"),
        "selected_trade_history": {
            "accepted_exact_trade_count_before_source_quality_scope": len(rows),
            "accepted_exact_trade_count": len(scoped_rows),
            **_dedupe_summary(len(source_quality_scoped_rows), len(scoped_rows)),
            "source_quality_excluded_trade_count": len(source_quality_exclusions),
            "rejected_row_counts": dict(sorted(rejected.items())),
            "available_entry_months": selected_months,
            "available_entry_month_count": len(selected_months),
            "calendar_months_available_for_split": months,
            "calendar_months_available_for_split_count": len(months),
            "month_coverage_basis": month_coverage_basis,
            "zero_selection_months": zero_selection_months,
            "zero_selection_months_explicit": bool(calendar_coverage.get("zero_selection_months_explicit")),
            "split_zero_selection_months": split_zero_selection_months,
            "audit_zero_selection_months": audit_zero_selection_months,
            "by_lane": dict(sorted(by_lane.items())),
        },
        "split": split,
        "metrics": {
            "combined": combined_metrics,
            "train": train_metrics,
            "simulated_forward_audit": audit_metrics,
            "simulated_forward_audit_by_month": per_month,
        },
        "blockers": blockers,
        "proof_policy": {
            "readback_is": "historical simulated-forward audit over current selected trusted-intraday exact rows",
            "readback_is_not": "fresh forward proof, live-validation eligibility, broker action, scanner policy change, proof-bar reduction, or protected-holdout consumption",
            "current_limitation": "current source artifact may have less selected-trade history than the trusted quote store",
            "required_next_if_blocked": "regenerate or build selected-trade candidates over the older trusted quote-history window before claiming a 20-month train plus 4-month audit",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    split = _as_dict(report.get("split"))
    selected = _as_dict(report.get("selected_trade_history"))
    source = _as_dict(report.get("source_summary"))
    metrics = _as_dict(report.get("metrics"))
    train = _as_dict(metrics.get("train"))
    audit = _as_dict(metrics.get("simulated_forward_audit"))
    audit_bootstrap_iid = _bootstrap_dict(audit, "bootstrap_iid")
    audit_bootstrap = _bootstrap_dict(audit, "bootstrap_cluster")
    combined = _as_dict(metrics.get("combined"))
    combined_bootstrap_iid = _bootstrap_dict(combined, "bootstrap_iid")
    combined_bootstrap = _bootstrap_dict(combined, "bootstrap_cluster")
    lines = [
        "# Regular Options Historical Simulated Forward Audit",
        "",
        "This report is generated from `scripts/build_regular_options_historical_simulated_forward_audit.py`. It tests whether the current selected exact historical trade source can support an explicit calendar split: calibration on the prior months and a latest-month historical simulated-forward audit. It is read-only and does not create trades, mutate evidence stores, consume protected holdout, or treat historical rows as fresh forward proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Requested split: `{_as_dict(report.get('requested_split')).get('train_months')}` train months + `{_as_dict(report.get('requested_split')).get('audit_months')}` simulated-forward audit months.",
        f"- Selected exact history: `{selected.get('available_entry_month_count')}` months, `{selected.get('accepted_exact_trade_count')}` accepted exact rows after source-quality scope.",
        f"- Dedupe: `{selected.get('accepted_exact_candidate_rows_before_dedupe')}` rows before dedupe, `{selected.get('deduped_row_count')}` rows after dedupe, `{selected.get('duplicate_rows_removed')}` duplicates removed.",
        f"- Calendar months available for split: `{selected.get('calendar_months_available_for_split_count')}` via `{selected.get('month_coverage_basis')}`.",
        f"- Available selected months: `{', '.join(str(item) for item in _as_list(selected.get('available_entry_months'))) or 'none'}`.",
        f"- Train months used: `{', '.join(str(item) for item in _as_list(split.get('train_months'))) or 'none'}`.",
        f"- Audit months used: `{', '.join(str(item) for item in _as_list(split.get('audit_months'))) or 'none'}`.",
        f"- Sufficient months for requested split: `{split.get('sufficient_months_for_requested_split')}`.",
        f"- Quote-history shared dates: `{source.get('feature_store_shared_quote_date_count')}` through `{source.get('feature_store_latest_shared_quote_date_et')}`.",
        f"- Candidate materialization basis: `{source.get('candidate_materialization_basis')}`.",
        f"- Scanner parity: `{source.get('scanner_parity')}`.",
        f"- Production scanner replay: `{source.get('production_scanner_replay')}`.",
        "",
        "## Metrics",
        "",
        "| Window | Months | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% | Cluster Confidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        f"| Combined | {combined.get('entry_month_count')} | {combined.get('exact_trade_count')} | {combined.get('ticker_week_cluster_count')} | {combined.get('avg_pnl_pct')} | {combined.get('profit_factor')} | {combined_bootstrap_iid.get('pf_lb_5pct')} | {combined_bootstrap.get('pf_lb_5pct')} | {combined.get('total_net_pnl_usd')} | {combined.get('usd_profit_factor')} | {_bootstrap_dict(combined, 'bootstrap_usd_cluster').get('pf_lb_5pct')} | `{combined_bootstrap.get('statistical_confidence')}` |",
        f"| Train | {train.get('entry_month_count')} | {train.get('exact_trade_count')} | {train.get('ticker_week_cluster_count')} | {train.get('avg_pnl_pct')} | {train.get('profit_factor')} | {_bootstrap_dict(train, 'bootstrap_iid').get('pf_lb_5pct')} | {_bootstrap_dict(train, 'bootstrap_cluster').get('pf_lb_5pct')} | {train.get('total_net_pnl_usd')} | {train.get('usd_profit_factor')} | {_bootstrap_dict(train, 'bootstrap_usd_cluster').get('pf_lb_5pct')} | `{_bootstrap_dict(train, 'bootstrap_cluster').get('statistical_confidence')}` |",
        f"| Simulated forward audit | {audit.get('entry_month_count')} | {audit.get('exact_trade_count')} | {audit.get('ticker_week_cluster_count')} | {audit.get('avg_pnl_pct')} | {audit.get('profit_factor')} | {audit_bootstrap_iid.get('pf_lb_5pct')} | {audit_bootstrap.get('pf_lb_5pct')} | {audit.get('total_net_pnl_usd')} | {audit.get('usd_profit_factor')} | {_bootstrap_dict(audit, 'bootstrap_usd_cluster').get('pf_lb_5pct')} | `{audit_bootstrap.get('statistical_confidence')}` |",
        "",
        "## Audit Months",
        "",
        "| Month | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD Cluster PF LB 5% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in _as_list(metrics.get("simulated_forward_audit_by_month")):
        row = _as_dict(row)
        row_metrics = _as_dict(row.get("metrics"))
        bootstrap_iid = _bootstrap_dict(row_metrics, "bootstrap_iid")
        bootstrap = _bootstrap_dict(row_metrics, "bootstrap_cluster")
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('month'))}`",
                    _cell(row_metrics.get("exact_trade_count")),
                    _cell(row_metrics.get("ticker_week_cluster_count")),
                    _cell(row_metrics.get("avg_pnl_pct")),
                    _cell(row_metrics.get("profit_factor")),
                    _cell(bootstrap_iid.get("pf_lb_5pct")),
                    _cell(bootstrap.get("pf_lb_5pct")),
                    _cell(row_metrics.get("total_net_pnl_usd")),
                    _cell(_bootstrap_dict(row_metrics, "bootstrap_usd_cluster").get("pf_lb_5pct")),
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This audit can falsify or support historical robustness. It cannot by itself satisfy fresh forward profitability acceptance because it uses historical selected rows and percent P&L, not post-freeze exact realized USD P&L rows.",
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
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only historical simulated-forward audit.")
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE_REPORT)
    parser.add_argument("--feature-store-report", type=Path, default=DEFAULT_FEATURE_STORE_REPORT)
    parser.add_argument("--source-quality-policy", type=Path, default=DEFAULT_SOURCE_QUALITY_POLICY)
    parser.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS)
    parser.add_argument("--audit-months", type=int, default=DEFAULT_AUDIT_MONTHS)
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        source_report_path=args.source_report,
        feature_store_report_path=args.feature_store_report,
        source_quality_policy_path=args.source_quality_policy,
        train_months=max(int(args.train_months), 1),
        audit_months=max(int(args.audit_months), 1),
        bootstrap_draws=max(int(args.bootstrap_draws), 1),
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
