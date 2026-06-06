from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ROOT_TEXT = str(ROOT)
if ROOT_TEXT not in sys.path:
    sys.path.insert(0, ROOT_TEXT)

from scripts import audit_missed_regular_picks_outcomes as outcome_audit


DEFAULT_INPUT_REPORT = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "missed-regular-picks-failure-modes.md"
REPORT_ID = "missed_regular_picks_failure_modes"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: str | Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _safe_float(value: Any) -> float | None:
    return outcome_audit._safe_float(value)


def _norm_text(value: Any) -> str:
    return outcome_audit._norm_text(value)


def _mark(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("mark")
    return value if isinstance(value, dict) else {}


def _mark_value(row: dict[str, Any], key: str) -> float | None:
    return _safe_float(_mark(row).get(key))


def _is_priced(row: dict[str, Any]) -> bool:
    mark = _mark(row)
    return bool(mark.get("priced")) and _safe_float(mark.get("net_pnl_pct")) is not None


def _is_tracked(row: dict[str, Any]) -> bool:
    return int(row.get("tracked_match_count") or 0) > 0


def _marked_metric_rows(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    return outcome_audit._marked_values(rows)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values, usd_values = _marked_metric_rows(rows)
    return outcome_audit.metrics(values, usd_values, row_count=len(rows))


def _dte_bucket(row: dict[str, Any]) -> str:
    dte = _safe_float(row.get("dte"))
    if dte is None:
        return "missing"
    if dte <= 5:
        return "lte5"
    if dte <= 10:
        return "6_10"
    if dte <= 20:
        return "11_20"
    if dte <= 35:
        return "21_35"
    return "36_plus"


def _entry_debit_bucket(row: dict[str, Any]) -> str:
    entry = _safe_float(_mark(row).get("entry_debit") or row.get("net_debit"))
    if entry is None:
        return "missing"
    if entry < 2.0:
        return "lt2"
    if entry < 4.0:
        return "2_4"
    if entry < 6.0:
        return "4_6"
    return "6_plus"


def _debit_pct_bucket(row: dict[str, Any]) -> str:
    return outcome_audit.debit_bucket(row)[0]


def _spread_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            _norm_text(row.get("scan_date"))[:10],
            _norm_text(row.get("ticker")).upper(),
            _norm_text(row.get("contract_symbol")).upper(),
            _norm_text(row.get("short_contract_symbol")).upper(),
        ]
    )


def _cluster_metrics(
    rows: list[dict[str, Any]],
    key_func: Callable[[dict[str, Any]], str],
    *,
    min_rows: int = 1,
    sort: str = "damage",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_func(row) or "unknown"].append(row)
    clusters: list[dict[str, Any]] = []
    for key, items in grouped.items():
        if len(items) < min_rows:
            continue
        metric = _metrics(items)
        values, usd_values = _marked_metric_rows(items)
        loss_values = [value for value in values if value < 0]
        loss_usd = [value for value in usd_values if value < 0]
        cluster = {
            "key": key,
            **metric,
            "loss_pnl_pct_sum": round(sum(loss_values), 2),
            "loss_pnl_usd_sum": round(sum(loss_usd), 2) if loss_usd else None,
        }
        clusters.append(cluster)

    if sort == "avg":
        clusters.sort(
            key=lambda item: (
                float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else 999.0),
                -int(item.get("rows") or 0),
            )
        )
    elif sort == "rows":
        clusters.sort(
            key=lambda item: (
                -int(item.get("rows") or 0),
                float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else 999.0),
            )
        )
    else:
        clusters.sort(
            key=lambda item: (
                float(item.get("net_pnl_pct_points") if item.get("net_pnl_pct_points") is not None else 0.0),
                float(item.get("avg_net_pnl_pct") if item.get("avg_net_pnl_pct") is not None else 999.0),
                -int(item.get("rows") or 0),
            )
        )
    return clusters[:limit] if limit is not None else clusters


def _loss_tail(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_mark_value(row, "net_pnl_pct") for row in rows if _mark_value(row, "net_pnl_pct") is not None]
    zero_exit_rows = [
        row
        for row in rows
        if (_safe_float(_mark(row).get("exit_credit")) or 0.0) <= 0.01
        and _mark(row).get("priced")
    ]
    low_exit_rows = []
    for row in rows:
        mark = _mark(row)
        if not mark.get("priced"):
            continue
        entry = _safe_float(mark.get("entry_debit"))
        exit_credit = _safe_float(mark.get("exit_credit"))
        if entry is not None and entry > 0 and exit_credit is not None and exit_credit <= entry * 0.25:
            low_exit_rows.append(row)

    priced = len(values)
    return {
        "priced_rows": priced,
        "negative_rows": sum(1 for value in values if value < 0),
        "rows_lte_minus_25_pct": sum(1 for value in values if value <= -25.0),
        "rows_lte_minus_50_pct": sum(1 for value in values if value <= -50.0),
        "rows_lte_minus_80_pct": sum(1 for value in values if value <= -80.0),
        "rows_lte_minus_100_pct": sum(1 for value in values if value <= -100.0),
        "zero_exit_credit_rows": len(zero_exit_rows),
        "low_exit_credit_lte_25pct_entry_rows": len(low_exit_rows),
        "negative_rate_pct": round(sum(1 for value in values if value < 0) / priced * 100.0, 1) if priced else 0.0,
    }


def _duplicate_spreads(rows: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_spread_key(row)].append(row)
    duplicates = []
    for key, items in grouped.items():
        if len(items) <= 1:
            continue
        duplicates.append(
            {
                "key": key,
                "scan_date": _norm_text(items[0].get("scan_date"))[:10],
                "ticker": _norm_text(items[0].get("ticker")).upper(),
                "contract_symbol": _norm_text(items[0].get("contract_symbol")).upper(),
                "short_contract_symbol": _norm_text(items[0].get("short_contract_symbol")).upper(),
                "playbooks": sorted({_norm_text(item.get("playbook")) for item in items}),
                **_metrics(items),
            }
        )
    duplicates.sort(
        key=lambda item: (
            float(item.get("net_pnl_pct_points") if item.get("net_pnl_pct_points") is not None else 0.0),
            -int(item.get("rows") or 0),
        )
    )
    return duplicates[:limit]


def _lane_decisions(outcome_report: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = []
    for gate in outcome_report.get("lane_gate_rows") or []:
        playbook = _norm_text(gate.get("playbook"))
        metrics = gate.get("metrics") if isinstance(gate.get("metrics"), dict) else {}
        self_guardrails = gate.get("self_guardrails") if isinstance(gate.get("self_guardrails"), dict) else {}
        allowed = bool(gate.get("auto_track_allowed"))
        decisions.append(
            {
                "playbook": playbook,
                "decision": "probation_candidate_flow_with_self_guardrails" if allowed else "diagnostic_only_until_earn_back",
                "auto_track_allowed_by_current_gate": allowed,
                "blockers": list(gate.get("blockers") or []),
                "metrics": metrics,
                "self_guardrails": self_guardrails,
                "required_action": (
                    "Allow only with self-guardrails, proof/freshness checks, hard portfolio caps, and forward paper monitoring."
                    if allowed
                    else "Do not auto-track or live-validate; rerun as diagnostics until the lane earns back with fresh exact outcomes."
                ),
            }
        )
    return sorted(decisions, key=lambda item: item["playbook"])


def _guardrail_candidates(untracked_rows: list[dict[str, Any]], lane_decisions: list[dict[str, Any]], *, min_cluster_rows: int) -> dict[str, Any]:
    blocked_lanes = [row["playbook"] for row in lane_decisions if not row["auto_track_allowed_by_current_gate"]]
    probation_lanes = [row["playbook"] for row in lane_decisions if row["auto_track_allowed_by_current_gate"]]
    worst_tickers = [
        {
            "ticker": item["key"],
            "rows": item["rows"],
            "avg_net_pnl_pct": item["avg_net_pnl_pct"],
            "profit_factor": item["profit_factor"],
            "winner_count": item["winner_count"],
            "loser_count": item["loser_count"],
            "net_pnl_pct_points": item["net_pnl_pct_points"],
        }
        for item in _cluster_metrics(untracked_rows, lambda row: _norm_text(row.get("ticker")).upper(), min_rows=min_cluster_rows, limit=15)
        if (item.get("avg_net_pnl_pct") is not None and float(item["avg_net_pnl_pct"]) < 0.0)
        and int(item.get("loser_count") or 0) >= int(item.get("winner_count") or 0)
    ]
    debit_45_plus = [
        row
        for row in untracked_rows
        if (_safe_float(row.get("debit_pct_of_width")) is not None and float(row["debit_pct_of_width"]) >= 45.0)
    ]
    long_dte_rows = [
        row
        for row in untracked_rows
        if (_safe_float(row.get("dte")) is not None and float(row["dte"]) >= 36.0)
    ]
    return {
        "active_lane_blocks": blocked_lanes,
        "block_entire_lanes": blocked_lanes,
        "probation_lanes": probation_lanes,
        "ticker_quarantine_candidates": worst_tickers,
        "ticker_quarantine_policy": "diagnostic_candidate_retest_before_scanner_change",
        "debit_pct_gte_45_diagnostic": _metrics(debit_45_plus),
        "debit_pct_gte_45_policy": "diagnostic_candidate_retest_before_scanner_change",
        "dte_gte_36_diagnostic": _metrics(long_dte_rows),
        "dte_gte_36_policy": "diagnostic_candidate_retest_before_scanner_change",
        "policy_read": [
            "Blocked lanes are not peers until they earn back with fresh exact outcomes.",
            "Ticker/debit/DTE candidates are diagnostic pre-entry filters, not live changes until retested.",
            "Allowed lanes still need proof, fresh quotes, hard portfolio caps, and self-guardrails.",
        ],
    }


def build_failure_report(
    outcome_report: dict[str, Any],
    *,
    input_report_path: Path | None = None,
    min_cluster_rows: int = 2,
) -> dict[str, Any]:
    rows = [row for row in outcome_report.get("rows") or [] if isinstance(row, dict)]
    tracked_rows = [row for row in rows if _is_tracked(row)]
    untracked_rows = [row for row in rows if not _is_tracked(row)]
    lane_decisions = _lane_decisions(outcome_report)
    summary = outcome_report.get("summary") if isinstance(outcome_report.get("summary"), dict) else {}
    mark_unpriced_count = int(summary.get("mark_unpriced_count") or (len(rows) - sum(1 for row in rows if _is_priced(row))))
    mark_coverage_count = int(summary.get("mark_coverage_count") or sum(1 for row in rows if _is_priced(row)))
    tracked_rows_with_stored_pnl = int(summary.get("tracked_rows_with_stored_pnl") or 0)
    tracked_pnl_complete = tracked_rows_with_stored_pnl >= len(tracked_rows)
    if mark_unpriced_count:
        data_status = "blocked_by_unpriced_exact_contract_rows"
    elif not tracked_pnl_complete:
        data_status = "tracked_pnl_incomplete"
    else:
        data_status = "clean_for_failure_analysis"
    untracked_metrics = _metrics(untracked_rows)
    untracked_pf = _safe_float(untracked_metrics.get("profit_factor"))
    untracked_avg = _safe_float(untracked_metrics.get("avg_net_pnl_pct"))
    if data_status == "clean_for_failure_analysis" and (untracked_pf is None or untracked_pf < 1.0 or (untracked_avg or 0.0) < 0.0):
        overall_status = "data_clean_strategy_unprofitable"
    elif data_status != "clean_for_failure_analysis":
        overall_status = "data_quality_blocked"
    else:
        overall_status = "data_clean_strategy_not_negative"
    guardrail_candidates = _guardrail_candidates(untracked_rows, lane_decisions, min_cluster_rows=min_cluster_rows)
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "missed_regular_picks_failure_mode_audit",
        "source_report": _rel(input_report_path),
        "source_generated_at_utc": outcome_report.get("generated_at_utc"),
        "summary": {
            "raw_row_count": len(rows),
            "tracked_row_count": len(tracked_rows),
            "untracked_row_count": len(untracked_rows),
            "mark_coverage_count": mark_coverage_count,
            "mark_unpriced_count": mark_unpriced_count,
            "tracked_rows_with_stored_pnl": tracked_rows_with_stored_pnl,
        },
        "data_quality": {
            "raw_rows": len(rows),
            "tracked_rows": len(tracked_rows),
            "tracked_rows_with_stored_pnl": summary.get("tracked_rows_with_stored_pnl"),
            "untracked_rows": len(untracked_rows),
            "mark_coverage_count": mark_coverage_count,
            "mark_unpriced_count": mark_unpriced_count,
            "tracked_pnl_complete": tracked_pnl_complete,
            "data_status": data_status,
            "data_read": data_status,
        },
        "overall_read": {
            "status": overall_status,
            "conclusions": [
                "The hard quote blocker is not the reason for this result when data_status is clean_for_failure_analysis.",
                "The missed rows are fully priced with trusted intraday exact-contract marks before lane/filter conclusions are drawn.",
                "Lane equality is rejected: blocked lanes stay diagnostic-only until they earn back.",
            ],
        },
        "overall_metrics": {
            "untracked": untracked_metrics,
            "tracked": _metrics(tracked_rows),
            "all": _metrics(rows),
        },
        "loss_tail": _loss_tail(untracked_rows),
        "lane_decisions": lane_decisions,
        "failure_modes": {
            "by_playbook": _cluster_metrics(untracked_rows, lambda row: _norm_text(row.get("playbook")), min_rows=1, sort="avg"),
            "worst_ticker_clusters": _cluster_metrics(
                untracked_rows,
                lambda row: _norm_text(row.get("ticker")).upper(),
                min_rows=min_cluster_rows,
                limit=20,
            ),
            "worst_playbook_ticker_clusters": _cluster_metrics(
                untracked_rows,
                lambda row: f"{_norm_text(row.get('playbook'))}:{_norm_text(row.get('ticker')).upper()}",
                min_rows=min_cluster_rows,
                limit=20,
            ),
            "debit_pct_bucket_metrics": _cluster_metrics(untracked_rows, _debit_pct_bucket, min_rows=1, sort="avg"),
            "entry_debit_bucket_metrics": _cluster_metrics(untracked_rows, _entry_debit_bucket, min_rows=1, sort="avg"),
            "dte_bucket_metrics": _cluster_metrics(untracked_rows, _dte_bucket, min_rows=1, sort="avg"),
            "scan_date_metrics": _cluster_metrics(untracked_rows, lambda row: _norm_text(row.get("scan_date"))[:10], min_rows=1, sort="avg"),
            "duplicate_exact_spread_groups": _duplicate_spreads(untracked_rows),
        },
        "pre_entry_guardrail_candidates": guardrail_candidates,
        "guardrail_candidates": guardrail_candidates,
        "earn_back_policy": {
            "status": "recommended_policy",
            "diagnostic_to_probation_requires": {
                "min_exact_marked_rows": 30,
                "max_unpriced_rows": 0,
                "min_profit_factor": 1.2,
                "min_avg_net_pnl_pct": 0.0,
                "min_later_date_or_out_of_sample_rows": 10,
                "must_use_entry_time_features_only": True,
                "must_survive_later_date_or_out_of_sample_split": True,
            },
            "probation_to_production_requires": {
                "target_profit_factor": 1.5,
                "positive_avg_after_fee_slippage_stress": True,
                "no_unblocked_negative_ticker_or_debit_cluster": True,
                "fresh_forward_paper_rows_required": True,
            },
        },
        "boundary": {
            "evidence_class": "historical_research_exact_contract_marks",
            "production_claim": False,
            "broker_fill_claim": False,
            "allowed_use": "routing_gate_design_and_forward_paper_validation",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    data = report.get("data_quality") or {}
    untracked = (report.get("overall_metrics") or {}).get("untracked") or {}
    loss_tail = report.get("loss_tail") or {}
    guardrails = report.get("pre_entry_guardrail_candidates") or report.get("guardrail_candidates") or {}
    overall = report.get("overall_read") or {}
    lines = [
        "# Missed Regular Picks Failure Modes",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Source report: `{report.get('source_report')}`",
        f"- Source generated: `{report.get('source_generated_at_utc')}`",
        f"- Data status: `{data.get('data_status') or data.get('data_read')}`",
        f"- Rows: `{data.get('raw_rows')}` total, `{data.get('tracked_rows')}` tracked, `{data.get('untracked_rows')}` untracked",
        f"- Mark coverage: `{data.get('mark_coverage_count')}` priced / `{data.get('mark_unpriced_count')}` unpriced",
        f"- Tracked P&L complete: `{data.get('tracked_pnl_complete')}`",
        "",
        "## Verdict",
        "",
        f"- Status: `{overall.get('status')}`",
        f"- Untracked avg net P&L: `{untracked.get('avg_net_pnl_pct')}%`",
        f"- Untracked PF: `{untracked.get('profit_factor')}`",
        f"- Winners / losers: `{untracked.get('winner_count')}` / `{untracked.get('loser_count')}`",
        f"- One-spread net dollars: `${untracked.get('sum_net_pnl_usd')}`",
        f"- Negative rate: `{loss_tail.get('negative_rate_pct')}%`",
        f"- Rows <= -50%: `{loss_tail.get('rows_lte_minus_50_pct')}`",
        f"- Rows <= -80%: `{loss_tail.get('rows_lte_minus_80_pct')}`",
        f"- Zero-exit-credit rows: `{loss_tail.get('zero_exit_credit_rows')}`",
        "",
        "## Lane Decisions",
        "",
        "| Lane | Decision | Rows | PF | Avg Net | Blockers |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in report.get("lane_decisions") or []:
        metric = item.get("metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("playbook") or ""),
                    str(item.get("decision") or ""),
                    str(metric.get("priced")),
                    str(metric.get("profit_factor")),
                    str(metric.get("avg_net_pnl_pct")),
                    ", ".join(str(blocker) for blocker in item.get("blockers") or []) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Guardrail Candidates",
            "",
            f"- Active lane blocks: `{', '.join(guardrails.get('active_lane_blocks') or guardrails.get('block_entire_lanes') or []) or 'none'}`",
            f"- Probation lanes: `{', '.join(guardrails.get('probation_lanes') or []) or 'none'}`",
            f"- Debit >= 45% of width: `{(guardrails.get('debit_pct_gte_45_diagnostic') or {}).get('rows')}` rows, avg `{(guardrails.get('debit_pct_gte_45_diagnostic') or {}).get('avg_net_pnl_pct')}%`, PF `{(guardrails.get('debit_pct_gte_45_diagnostic') or {}).get('profit_factor')}`",
            f"- DTE >= 36: `{(guardrails.get('dte_gte_36_diagnostic') or {}).get('rows')}` rows, avg `{(guardrails.get('dte_gte_36_diagnostic') or {}).get('avg_net_pnl_pct')}%`, PF `{(guardrails.get('dte_gte_36_diagnostic') or {}).get('profit_factor')}`",
            "",
            "## Ticker Quarantine Candidates",
            "",
            "| Ticker | Rows | PF | Avg Net | Winners | Losers | Net Points |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in (guardrails.get("ticker_quarantine_candidates") or [])[:12]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("ticker") or ""),
                    str(item.get("rows")),
                    str(item.get("profit_factor")),
                    str(item.get("avg_net_pnl_pct")),
                    str(item.get("winner_count")),
                    str(item.get("loser_count")),
                    str(item.get("net_pnl_pct_points")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Worst Ticker Clusters",
            "",
            "| Ticker | Rows | PF | Avg Net | Winners | Losers | Net Points |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in (report.get("failure_modes") or {}).get("worst_ticker_clusters") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("key") or ""),
                    str(item.get("rows")),
                    str(item.get("profit_factor")),
                    str(item.get("avg_net_pnl_pct")),
                    str(item.get("winner_count")),
                    str(item.get("loser_count")),
                    str(item.get("net_pnl_pct_points")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Failure Buckets",
            "",
            "### Debit Percent Of Width",
            "",
            "| Bucket | Rows | PF | Avg Net | Winners | Losers |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in (report.get("failure_modes") or {}).get("debit_pct_bucket_metrics") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("key") or ""),
                    str(item.get("rows")),
                    str(item.get("profit_factor")),
                    str(item.get("avg_net_pnl_pct")),
                    str(item.get("winner_count")),
                    str(item.get("loser_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### DTE",
            "",
            "| Bucket | Rows | PF | Avg Net | Winners | Losers |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in (report.get("failure_modes") or {}).get("dte_bucket_metrics") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("key") or ""),
                    str(item.get("rows")),
                    str(item.get("profit_factor")),
                    str(item.get("avg_net_pnl_pct")),
                    str(item.get("winner_count")),
                    str(item.get("loser_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Earn-Back Policy",
            "",
            "- Diagnostic lanes need at least `30` exact marked rows, `0` unpriced rows, PF `>= 1.2`, positive average net P&L, entry-time-only rules, and a later-date/OOS pass before probation.",
            "- Probation lanes need PF near `1.5`, positive fee/slippage stress, no unblocked negative ticker/debit cluster, and fresh forward paper rows before production discussion.",
            "- This report is a routing and repair audit, not broker execution evidence or a recommendation.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path, doc_path: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    latest_md.write_text(markdown + "\n", encoding="utf-8")
    doc_path.write_text(markdown + "\n", encoding="utf-8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze failure modes in the missed regular picks outcome audit.")
    parser.add_argument("--input-report", type=Path, default=DEFAULT_INPUT_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--min-cluster-rows", type=int, default=2)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome_report = _load_json(args.input_report)
    report = build_failure_report(
        outcome_report,
        input_report_path=args.input_report,
        min_cluster_rows=max(int(args.min_cluster_rows), 1),
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        payload = {
            "data_quality": report["data_quality"],
            "overall_metrics": report["overall_metrics"],
            "loss_tail": report["loss_tail"],
            "lane_decisions": report["lane_decisions"],
            "guardrail_candidates": report["guardrail_candidates"],
            "artifacts": report.get("artifacts"),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
