from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_monthly_all_lanes_profitability_audit as monthly_audit  # noqa: E402


REPORT_ID = "regular_options_risk_budget_sizing_replay"

DEFAULT_MISSED_OUTCOME = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_FAILURE_MODES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json"
DEFAULT_LANE_PROMOTION_STATE = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_MULTILANE_PORTFOLIO = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
DEFAULT_LANE_QUARANTINE_ARCHIVE = (
    ROOT / "data" / "forward-tracking" / "regular_options_lane_quarantine_archive_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-risk-budget-sizing-replay.md"

PROHIBITED_ACTIONS = (
    "do_not_change_live_size_tiers_from_risk_budget_sizing_replay",
    "do_not_create_live_row_from_risk_budget_sizing_replay",
    "do_not_submit_broker_order_from_risk_budget_sizing_replay",
    "do_not_mutate_database_from_risk_budget_sizing_replay",
    "do_not_change_scanner_policy_from_risk_budget_sizing_replay",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_risk_budget_sizing_replay",
    "do_not_promote_research_backfill_sizing_rows_to_production_proof",
)

WeightFn = Callable[[str], float]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


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
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "error": None,
    }
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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    return payload, meta


def _has_live_policy_change(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "live_policy_change" and bool(item):
                return True
            if _has_live_policy_change(item):
                return True
    if isinstance(value, list):
        return any(_has_live_policy_change(item) for item in value)
    return False


def _lane_disposition_map(
    failure_modes: dict[str, Any],
    lane_promotion_state: dict[str, Any],
    lane_quarantine_archive: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    leaderboard = monthly_audit._lane_leaderboard(failure_modes)
    dispositions = monthly_audit._lane_dispositions(
        leaderboard,
        lane_promotion_state,
        {"promotion_ready": False, "blockers": []},
    )
    annotated = monthly_audit._annotate_lane_quarantine_archive(dispositions, lane_quarantine_archive)
    return {
        _norm(item.get("lane")): item
        for item in _as_list(annotated.get("dispositions"))
        if isinstance(item, dict) and _norm(item.get("lane"))
    }


def _source_rows(missed_outcome: dict[str, Any], dispositions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _as_list(missed_outcome.get("rows")):
        if not isinstance(raw, dict):
            continue
        mark = _as_dict(raw.get("mark"))
        net_usd = _safe_float(mark.get("net_pnl_usd"))
        net_pct = _safe_float(mark.get("net_pnl_pct"))
        if not mark.get("priced") or net_usd is None or net_pct is None:
            continue
        if int(raw.get("tracked_match_count") or 0) > 0:
            continue
        lane = _norm(raw.get("playbook")) or "unknown"
        disposition = _as_dict(dispositions.get(lane)).get("disposition") or "needs_replay_engine"
        rows.append(
            {
                "scan_date": raw.get("scan_date"),
                "month": _norm(raw.get("scan_date"))[:7],
                "ticker": raw.get("ticker"),
                "lane": lane,
                "disposition": disposition,
                "net_pnl_usd": net_usd,
                "net_pnl_pct": net_pct,
                "entry_debit": _safe_float(mark.get("entry_debit") or raw.get("net_debit")),
                "debit_pct_of_width": _safe_float(raw.get("debit_pct_of_width")),
                "dte": raw.get("dte"),
            }
        )
    return rows


def _profit_factor(gross_profit: float, gross_loss_abs: float) -> float | None:
    if gross_loss_abs <= 0:
        return None
    return gross_profit / gross_loss_abs


def _scenario_metrics(
    *,
    scenario_id: str,
    label: str,
    rows: list[dict[str, Any]],
    weight_fn: WeightFn,
    baseline_net_usd: float | None,
    live_entry_allowed: bool,
) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    month_net: dict[str, float] = defaultdict(float)
    lane_net: dict[str, float] = defaultdict(float)
    lane_risk_units: dict[str, float] = defaultdict(float)
    gross_profit = 0.0
    gross_loss_abs = 0.0
    weighted_net = 0.0
    weighted_pct_sum = 0.0
    risk_units = 0.0
    winners = 0
    losers = 0
    for row in rows:
        disposition = _norm(row.get("disposition"))
        weight = max(0.0, float(weight_fn(disposition)))
        if weight <= 0:
            continue
        net_usd = float(row["net_pnl_usd"]) * weight
        net_pct = float(row["net_pnl_pct"])
        weighted_net += net_usd
        weighted_pct_sum += net_pct * weight
        risk_units += weight
        month_net[_norm(row.get("month")) or "unknown"] += net_usd
        lane_net[_norm(row.get("lane")) or "unknown"] += net_usd
        lane_risk_units[_norm(row.get("lane")) or "unknown"] += weight
        included.append({**row, "risk_weight": weight, "weighted_net_pnl_usd": net_usd})
        if net_usd >= 0:
            gross_profit += net_usd
            winners += 1
        else:
            gross_loss_abs += abs(net_usd)
            losers += 1

    avg_pct = weighted_pct_sum / risk_units if risk_units else None
    median_pct = statistics.median(float(row["net_pnl_pct"]) for row in included) if included else None
    pf = _profit_factor(gross_profit, gross_loss_abs)
    blockers = [
        "historical_research_backfill_rows_are_not_production_sizing_proof",
        "fresh_exact_realized_sizing_evidence_required",
    ]
    if not live_entry_allowed:
        blockers.insert(0, "open_risk_governor_blocks_sizing")
    if pf is None or pf < 1.2:
        blockers.append("profit_factor_below_sizing_gate")
    if weighted_net <= 0:
        blockers.append("net_pnl_not_positive")
    if risk_units == 0:
        blockers.append("zero_new_risk_budget_due_to_governor")

    return {
        "scenario_id": scenario_id,
        "label": label,
        "classification": "research_sizing_replay_only",
        "promotion_ready": False,
        "source_row_count": len(rows),
        "included_row_count": len(included),
        "risk_unit_count": _round(risk_units),
        "gross_profit_usd": _round(gross_profit),
        "gross_loss_abs_usd": _round(gross_loss_abs),
        "net_pnl_usd": _round(weighted_net),
        "improvement_vs_baseline_usd": _round(weighted_net - baseline_net_usd) if baseline_net_usd is not None else None,
        "profit_factor": _round(pf),
        "profit_factor_basis": "net_pnl_usd",
        "no_loss_sample": bool(included and gross_loss_abs <= 0 and gross_profit > 0),
        "avg_net_pnl_pct": _round(avg_pct),
        "median_net_pnl_pct": _round(median_pct),
        "win_rate_pct": _round((winners / len(included)) * 100.0 if included else None),
        "winner_count": winners,
        "loser_count": losers,
        "monthly_net_pnl_usd": {month: _round(value) for month, value in sorted(month_net.items())},
        "worst_month_net_pnl_usd": _round(min(month_net.values())) if month_net else None,
        "lane_net_pnl_usd": {lane: _round(value) for lane, value in sorted(lane_net.items())},
        "lane_risk_units": {lane: _round(value) for lane, value in sorted(lane_risk_units.items())},
        "blockers": sorted(set(blockers)),
    }


def _lane_budget_table(rows: list[dict[str, Any]], dispositions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_norm(row.get("lane")) or "unknown"].append(row)
    table = []
    for lane, lane_rows in sorted(grouped.items()):
        gross_profit = sum(float(row["net_pnl_usd"]) for row in lane_rows if float(row["net_pnl_usd"]) >= 0)
        gross_loss = abs(sum(float(row["net_pnl_usd"]) for row in lane_rows if float(row["net_pnl_usd"]) < 0))
        net = sum(float(row["net_pnl_usd"]) for row in lane_rows)
        disposition = _norm(_as_dict(dispositions.get(lane)).get("disposition")) or "needs_replay_engine"
        table.append(
            {
                "lane": lane,
                "disposition": disposition,
                "archive_status": _as_dict(dispositions.get(lane)).get("archive_status"),
                "baseline_rows": len(lane_rows),
                "baseline_net_pnl_usd": _round(net),
                "baseline_profit_factor": _round(_profit_factor(gross_profit, gross_loss)),
                "baseline_avg_net_pnl_pct": _round(
                    sum(float(row["net_pnl_pct"]) for row in lane_rows) / len(lane_rows) if lane_rows else None
                ),
                "paper_shadow_only_weight": 1.0 if disposition in {"paper_shadow", "profitable_candidate"} else 0.0,
                "tiered_research_weight": {
                    "profitable_candidate": 1.0,
                    "paper_shadow": 1.0,
                    "retest": 0.25,
                    "needs_replay_engine": 0.0,
                    "quarantine": 0.0,
                    "archive": 0.0,
                }.get(disposition, 0.0),
            }
        )
    table.sort(key=lambda item: (float(item.get("baseline_net_pnl_usd") or 0), item["lane"]))
    return table


def build_report(
    *,
    missed_outcome_path: Path = DEFAULT_MISSED_OUTCOME,
    failure_modes_path: Path = DEFAULT_FAILURE_MODES,
    lane_promotion_state_path: Path = DEFAULT_LANE_PROMOTION_STATE,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    multilane_portfolio_path: Path = DEFAULT_MULTILANE_PORTFOLIO,
    lane_quarantine_archive_path: Path = DEFAULT_LANE_QUARANTINE_ARCHIVE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    paths = {
        "missed_picks_outcome": missed_outcome_path,
        "missed_picks_failure_modes": failure_modes_path,
        "lane_promotion_state": lane_promotion_state_path,
        "open_risk": open_risk_path,
        "multilane_portfolio": multilane_portfolio_path,
        "lane_quarantine_archive": lane_quarantine_archive_path,
    }
    reports: dict[str, dict[str, Any]] = {}
    inputs: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        reports[key], inputs[key] = _load_json(path)

    required = ("missed_picks_outcome", "missed_picks_failure_modes", "lane_promotion_state", "open_risk", "multilane_portfolio")
    missing_required = [key for key in required if inputs[key]["status"] != "loaded"]
    live_policy_change = any(_has_live_policy_change(report) for report in reports.values())
    governor = _as_dict(reports["open_risk"].get("open_risk_governor"))
    live_entry_allowed = bool(governor.get("live_entry_allowed"))
    dispositions = _lane_disposition_map(
        reports["missed_picks_failure_modes"],
        reports["lane_promotion_state"],
        reports["lane_quarantine_archive"],
    )
    rows = _source_rows(reports["missed_picks_outcome"], dispositions)

    scenario_defs: tuple[tuple[str, str, WeightFn], ...] = (
        (
            "baseline_one_contract_all_untracked",
            "One contract for every priced untracked missed selected row",
            lambda _disposition: 1.0,
        ),
        (
            "quarantine_zero_weight",
            "Zero budget for archived/quarantined lanes; one unit for every other priced row",
            lambda disposition: 0.0 if disposition in {"quarantine", "archive"} else 1.0,
        ),
        (
            "paper_shadow_only",
            "One unit for paper-shadow/profitable-candidate lanes only",
            lambda disposition: 1.0 if disposition in {"paper_shadow", "profitable_candidate"} else 0.0,
        ),
        (
            "tiered_shadow_full_retest_quarter",
            "One unit for paper-shadow/profitable lanes, quarter unit for retest lanes, zero for quarantine/replay-missing lanes",
            lambda disposition: {
                "profitable_candidate": 1.0,
                "paper_shadow": 1.0,
                "retest": 0.25,
                "needs_replay_engine": 0.0,
                "quarantine": 0.0,
                "archive": 0.0,
            }.get(disposition, 0.0),
        ),
        (
            "current_governor_zero_new_risk",
            "Current open-risk governor allows zero new live sizing while blocked",
            lambda _disposition: 0.0 if not live_entry_allowed else 1.0,
        ),
    )
    baseline_net = None
    scenario_rows: list[dict[str, Any]] = []
    for scenario_id, label, weight_fn in scenario_defs:
        row = _scenario_metrics(
            scenario_id=scenario_id,
            label=label,
            rows=rows,
            weight_fn=weight_fn,
            baseline_net_usd=baseline_net,
            live_entry_allowed=live_entry_allowed,
        )
        if scenario_id == "baseline_one_contract_all_untracked":
            baseline_net = float(row.get("net_pnl_usd") or 0)
            row["improvement_vs_baseline_usd"] = 0.0
        scenario_rows.append(row)

    positive = [row for row in scenario_rows if float(row.get("net_pnl_usd") or 0) > 0 and float(row.get("risk_unit_count") or 0) > 0]
    positive_research = [row for row in scenario_rows if float(row.get("net_pnl_usd") or 0) > 0]
    best_candidates = [
        row
        for row in positive_research
        if row.get("scenario_id")
        not in {"baseline_one_contract_all_untracked", "current_governor_zero_new_risk", "quarantine_zero_weight"}
    ] or positive
    best = max(best_candidates, key=lambda row: float(row.get("net_pnl_usd") or -10**12), default={})
    blockers = []
    if not rows:
        blockers.append("no_priced_untracked_rows_for_sizing_replay")
    if not live_entry_allowed:
        blockers.append("open_risk_governor_blocks_sizing")
    blockers.extend(
        [
            "historical_research_backfill_rows_are_not_production_sizing_proof",
            "fresh_exact_realized_sizing_evidence_required",
            "sizing_change_requires_separate_promotion_gate",
        ]
    )

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "risk_budget_sizing_replay_readback"
        overall_status = "sizing_replay_built_open_risk_blocked" if not live_entry_allowed else "sizing_replay_built_collect_fresh_exact_evidence"

    summary = {
        "overall_status": overall_status,
        "missing_required_inputs": missing_required,
        "source_row_count": len(rows),
        "scenario_count": len(scenario_rows),
        "positive_research_scenario_count": len(positive),
        "baseline_net_pnl_usd": next(
            (row.get("net_pnl_usd") for row in scenario_rows if row.get("scenario_id") == "baseline_one_contract_all_untracked"),
            None,
        ),
        "best_research_scenario_id": best.get("scenario_id"),
        "best_research_net_pnl_usd": best.get("net_pnl_usd"),
        "best_research_profit_factor": best.get("profit_factor"),
        "best_research_risk_unit_count": best.get("risk_unit_count"),
        "open_risk_status": governor.get("status"),
        "live_entry_allowed": live_entry_allowed,
        "promotion_ready": False,
        "blockers": sorted(set(blockers)),
        "live_policy_change": live_policy_change,
    }
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_risk_budget_sizing_replay",
        "schema_version": 1,
        "read_only": True,
        "summary": summary,
        "proof_policy": {
            "readback_is": "read-only research sizing replay over priced untracked regular-options rows",
            "readback_is_not": "live sizing change, scanner policy change, broker recommendation, DB mutation, or production proof",
            "trusted_proof_standard": "fresh exact OPRA/NBBO entry plus exact executable realized exit evidence remains required for live sizing decisions",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": inputs,
        "open_risk_governor": governor,
        "lane_budget_table": _lane_budget_table(rows, dispositions),
        "scenarios": scenario_rows,
        "next_evidence_queue": [
            {
                "priority": 0,
                "action": "resolve_open_risk_for_sizing",
                "count": len(_as_list(governor.get("live_exact_negative_ids"))),
                "reason": "open_risk_governor_blocks_any_live_size_change",
            }
            if not live_entry_allowed
            else {
                "priority": 2,
                "action": "collect_fresh_exact_sizing_evidence",
                "count": len(positive),
                "reason": "research_sizing_scenarios_need_forward_exact_realized_pnl",
            }
        ],
        "live_policy_change": live_policy_change,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Risk-Budget Sizing Replay",
        "",
        "This report is generated from `scripts/build_regular_options_risk_budget_sizing_replay.py`. It is read-only sizing evidence over priced research/backfill rows and does not change live size tiers, scanner policy, broker behavior, DB state, proof bars, or lane promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Source rows: `{summary.get('source_row_count')}`.",
        f"- Baseline net P&L: `{summary.get('baseline_net_pnl_usd')}`.",
        f"- Best research scenario: `{summary.get('best_research_scenario_id')}` / net `{summary.get('best_research_net_pnl_usd')}` / PF `{summary.get('best_research_profit_factor')}`.",
        f"- Positive research scenarios: `{summary.get('positive_research_scenario_count')}`.",
        f"- Open-risk status / live entry allowed: `{summary.get('open_risk_status')}` / `{summary.get('live_entry_allowed')}`.",
        f"- Promotion ready: `{summary.get('promotion_ready')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Scenario Replay",
        "",
        "| Scenario | Included | Risk Units | Net USD | PF | Avg % | Median % | Win Rate | Worst Month | Blockers |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _as_list(report.get("scenarios")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("scenario_id")),
                    _cell(row.get("included_row_count")),
                    _cell(row.get("risk_unit_count")),
                    _cell(row.get("net_pnl_usd")),
                    _cell(row.get("profit_factor")),
                    _cell(row.get("avg_net_pnl_pct")),
                    _cell(row.get("median_net_pnl_pct")),
                    _cell(row.get("win_rate_pct")),
                    _cell(row.get("worst_month_net_pnl_usd")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers")))),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Lane Budget Table",
            "",
            "| Lane | Disposition | Archive | Rows | Net USD | PF | Avg % | Paper Weight | Tiered Weight |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in _as_list(report.get("lane_budget_table")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("lane")),
                    f"`{_cell(row.get('disposition'))}`",
                    f"`{_cell(row.get('archive_status') or '')}`",
                    _cell(row.get("baseline_rows")),
                    _cell(row.get("baseline_net_pnl_usd")),
                    _cell(row.get("baseline_profit_factor")),
                    _cell(row.get("baseline_avg_net_pnl_pct")),
                    _cell(row.get("paper_shadow_only_weight")),
                    _cell(row.get("tiered_research_weight")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This sizing replay is read-only. It does not change size tiers, create trades, submit broker orders, mutate DB state, change scanner policy, lower exact OPRA/NBBO proof bars, or promote research/backfill sizing rows to production proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options risk-budget sizing replay.")
    parser.add_argument("--missed-outcome", type=Path, default=DEFAULT_MISSED_OUTCOME)
    parser.add_argument("--failure-modes", type=Path, default=DEFAULT_FAILURE_MODES)
    parser.add_argument("--lane-promotion-state", type=Path, default=DEFAULT_LANE_PROMOTION_STATE)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--multilane-portfolio", type=Path, default=DEFAULT_MULTILANE_PORTFOLIO)
    parser.add_argument("--lane-quarantine-archive", type=Path, default=DEFAULT_LANE_QUARANTINE_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        missed_outcome_path=args.missed_outcome,
        failure_modes_path=args.failure_modes,
        lane_promotion_state_path=args.lane_promotion_state,
        open_risk_path=args.open_risk,
        multilane_portfolio_path=args.multilane_portfolio,
        lane_quarantine_archive_path=args.lane_quarantine_archive,
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
