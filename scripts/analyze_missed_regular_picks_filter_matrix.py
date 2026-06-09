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
from scripts.quote_evidence_readback import (  # noqa: E402
    non_production_research_policy,
    quote_evidence_readback,
)


DEFAULT_INPUT_REPORT = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "missed-regular-picks-filter-matrix.md"
REPORT_ID = "missed_regular_picks_filter_matrix"

PRIMARY_DAMAGE_TICKERS = {"XLK", "SPY", "TSLA", "IWM"}
EXTENDED_DAMAGE_TICKERS = {
    "AA",
    "AMZN",
    "BA",
    "FCX",
    "IWM",
    "NVDA",
    "PLD",
    "SLB",
    "SMCI",
    "SPY",
    "TSLA",
    "XLK",
}


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


def _source_evidence_policy(
    outcome_report: dict[str, Any],
    *,
    record_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = outcome_report.get("inputs") if isinstance(outcome_report.get("inputs"), dict) else {}
    quote_evidence = inputs.get("quote_evidence") if isinstance(inputs.get("quote_evidence"), dict) else {}
    if not quote_evidence:
        quote_evidence = quote_evidence_readback(
            snapshot_kind="intraday",
            source_labels=inputs.get("source_labels") or [],
            trusted_only=inputs.get("trusted_only"),
        )
    evidence_policy = inputs.get("evidence_policy") if isinstance(inputs.get("evidence_policy"), dict) else {}
    if not evidence_policy:
        evidence_policy = non_production_research_policy(
            record_class=record_class,
            quote_evidence=quote_evidence,
        )
    return quote_evidence, evidence_policy


def _norm_text(value: Any) -> str:
    return outcome_audit._norm_text(value)


def _safe_float(value: Any) -> float | None:
    return outcome_audit._safe_float(value)


def _mark(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("mark")
    return value if isinstance(value, dict) else {}


def _mark_value(row: dict[str, Any], key: str) -> float | None:
    return _safe_float(_mark(row).get(key))


def _is_priced(row: dict[str, Any]) -> bool:
    return bool(_mark(row).get("priced")) and _mark_value(row, "net_pnl_pct") is not None


def _is_tracked(row: dict[str, Any]) -> bool:
    return int(row.get("tracked_match_count") or 0) > 0


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values, usd_values = outcome_audit._marked_values(rows)
    return outcome_audit.metrics(values, usd_values, row_count=len(rows))


def _ticker(row: dict[str, Any]) -> str:
    return _norm_text(row.get("ticker")).upper()


def _playbook(row: dict[str, Any]) -> str:
    return _norm_text(row.get("playbook") or row.get("playbook_id"))


def _scan_date(row: dict[str, Any]) -> str:
    return _norm_text(row.get("scan_date") or row.get("audit_generated_at_utc"))[:10]


def _spread_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            _scan_date(row),
            _ticker(row),
            _norm_text(row.get("direction") or row.get("type") or row.get("option_type")).lower(),
            _norm_text(row.get("expiry") or row.get("expiration_date"))[:10],
            _norm_text(row.get("contract_symbol")).upper(),
            _norm_text(row.get("short_contract_symbol")).upper(),
            _norm_text(row.get("long_strike") if row.get("long_strike") is not None else row.get("strike")),
            _norm_text(row.get("short_strike")),
        ]
    )


def _lane_gates(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates: dict[str, dict[str, Any]] = {}
    raw = report.get("lane_gates")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                gates[_norm_text(key)] = value
    for value in report.get("lane_gate_rows") or []:
        if isinstance(value, dict):
            gates[_norm_text(value.get("playbook"))] = value
    return gates


def _lane_allowed(row: dict[str, Any], gates: dict[str, dict[str, Any]]) -> bool:
    gate = gates.get(_playbook(row))
    return bool(gate and gate.get("auto_track_allowed"))


def _lane_self_guardrail_allowed(row: dict[str, Any], gates: dict[str, dict[str, Any]]) -> bool:
    gate = gates.get(_playbook(row))
    if not gate or not bool(gate.get("auto_track_allowed")):
        return False
    self_guardrails = gate.get("self_guardrails") if isinstance(gate.get("self_guardrails"), dict) else {}
    blocked_tickers = {
        _norm_text(item.get("ticker") if isinstance(item, dict) else item).upper()
        for item in self_guardrails.get("blocked_tickers") or []
        if _norm_text(item.get("ticker") if isinstance(item, dict) else item)
    }
    if _ticker(row) in blocked_tickers:
        return False
    max_debit = _safe_float(self_guardrails.get("max_debit_pct_of_width"))
    debit_pct = _safe_float(row.get("debit_pct_of_width"))
    if max_debit is not None and (debit_pct is None or debit_pct > max_debit):
        return False
    return True


def _dedupe_exact_spreads(rows: list[dict[str, Any]], gates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[_spread_key(row)].append((index, row))

    kept: list[tuple[int, dict[str, Any]]] = []
    for items in grouped.values():
        owner = sorted(
            items,
            key=lambda item: (
                0 if _lane_self_guardrail_allowed(item[1], gates) else 1 if _lane_allowed(item[1], gates) else 2,
                _playbook(item[1]),
                item[0],
            ),
        )[0]
        kept.append(owner)
    return [row for _, row in sorted(kept, key=lambda item: item[0])]


def _later_dates(rows: list[dict[str, Any]]) -> set[str]:
    dates = sorted({date for date in (_scan_date(row) for row in rows) if date})
    if not dates:
        return set()
    holdout_count = max(2, math.ceil(len(dates) * 0.25))
    return set(dates[-holdout_count:])


def _tail_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    values = [_mark_value(row, "net_pnl_pct") for row in rows if _mark_value(row, "net_pnl_pct") is not None]
    return {
        "negative": sum(1 for value in values if value < 0),
        "lte_minus_50": sum(1 for value in values if value <= -50.0),
        "lte_minus_80": sum(1 for value in values if value <= -80.0),
        "winners": sum(1 for value in values if value > 0),
    }


def _scenario_readiness(kept: list[dict[str, Any]], later_rows: list[dict[str, Any]], *, status: str) -> dict[str, Any]:
    kept_metrics = _metrics(kept)
    later_metrics = _metrics(later_rows)
    kept_pf = _safe_float(kept_metrics.get("profit_factor"))
    kept_avg = _safe_float(kept_metrics.get("avg_net_pnl_pct"))
    later_pf = _safe_float(later_metrics.get("profit_factor"))
    later_avg = _safe_float(later_metrics.get("avg_net_pnl_pct"))
    passes_later = bool(later_rows) and later_pf is not None and later_pf >= 1.0 and (later_avg or 0.0) > 0.0
    paper_candidate = bool(kept) and kept_pf is not None and kept_pf >= 1.2 and (kept_avg or 0.0) > 0.0
    return {
        "status": status,
        "paper_shadow_candidate": paper_candidate and passes_later,
        "later_date_rows": len(later_rows),
        "later_date_profit_factor": later_metrics.get("profit_factor"),
        "later_date_avg_net_pnl_pct": later_metrics.get("avg_net_pnl_pct"),
        "survives_later_date_split": passes_later,
    }


def _evaluate_scenario(
    *,
    scenario_id: str,
    description: str,
    rows: list[dict[str, Any]],
    kept: list[dict[str, Any]],
    later_date_set: set[str],
    status: str,
    entry_time_only: bool,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    kept_ids = {id(row) for row in kept}
    blocked = [row for row in rows if id(row) not in kept_ids]
    blocked_values = [_mark_value(row, "net_pnl_pct") for row in blocked if _mark_value(row, "net_pnl_pct") is not None]
    lost_winners = [value for value in blocked_values if value > 0]
    avoided_losses = [value for value in blocked_values if value < 0]
    later_rows = [row for row in kept if _scan_date(row) in later_date_set]
    return {
        "scenario_id": scenario_id,
        "description": description,
        "status": status,
        "entry_time_only": entry_time_only,
        "kept_count": len(kept),
        "blocked_count": len(blocked),
        "candidate_flow_reduction_pct": round(len(blocked) / len(rows) * 100.0, 1) if rows else 0.0,
        "kept_metrics": _metrics(kept),
        "blocked_metrics": _metrics(blocked),
        "kept_tail": _tail_counts(kept),
        "blocked_tail": _tail_counts(blocked),
        "avoided_deep_loss_count_lte_minus_50": sum(1 for value in avoided_losses if value <= -50.0),
        "avoided_deep_loss_count_lte_minus_80": sum(1 for value in avoided_losses if value <= -80.0),
        "lost_winner_count": len(lost_winners),
        "lost_winner_pct_points": round(sum(lost_winners), 2),
        "avoided_loss_pct_points": round(abs(sum(avoided_losses)), 2),
        "later_date_read": _scenario_readiness(kept, later_rows, status=status),
        "notes": notes or [],
    }


def build_filter_matrix_report(
    outcome_report: dict[str, Any],
    *,
    input_report_path: Path | None = None,
) -> dict[str, Any]:
    rows = [row for row in outcome_report.get("rows") or [] if isinstance(row, dict)]
    untracked = [row for row in rows if not _is_tracked(row) and _is_priced(row)]
    gates = _lane_gates(outcome_report)
    later_date_set = _later_dates(untracked)

    lane_gate_rows = [row for row in untracked if _lane_allowed(row, gates)]
    lane_self_rows = [row for row in untracked if _lane_self_guardrail_allowed(row, gates)]
    deduped_rows = _dedupe_exact_spreads(untracked, gates)
    lane_self_deduped_rows = _dedupe_exact_spreads(lane_self_rows, gates)

    scenarios = [
        _evaluate_scenario(
            scenario_id="baseline_all_untracked",
            description="All priced untracked missed rows.",
            rows=untracked,
            kept=untracked,
            later_date_set=later_date_set,
            status="baseline_readback",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="current_lane_gate_allowlist",
            description="Keep only lanes whose current outcome audit allows candidate flow.",
            rows=untracked,
            kept=lane_gate_rows,
            later_date_set=later_date_set,
            status="active_safety_gate_paper_probation",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="current_lane_gate_self_guardrails",
            description="Keep only lane-gate-passed rows that also clear the lane's ticker/debit self-guardrails.",
            rows=untracked,
            kept=lane_self_rows,
            later_date_set=later_date_set,
            status="active_safety_gate_paper_probation",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="exact_spread_dedupe_only",
            description="Collapse same-date exact duplicate spreads to one deterministic risk owner.",
            rows=untracked,
            kept=deduped_rows,
            later_date_set=later_date_set,
            status="immediate_suppression_candidate",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="lane_gate_self_guardrails_plus_exact_spread_dedupe",
            description="Apply lane profitability, lane self-guardrails, then exact duplicate-spread suppression.",
            rows=untracked,
            kept=lane_self_deduped_rows,
            later_date_set=later_date_set,
            status="recommended_paper_shadow_policy_candidate",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="no_debit_gte_45",
            description="Reject debit >= 45% of spread width across all lanes.",
            rows=untracked,
            kept=[row for row in untracked if (_safe_float(row.get("debit_pct_of_width")) or 0.0) < 45.0],
            later_date_set=later_date_set,
            status="diagnostic_retest_required",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="no_dte_gte_36",
            description="Reject DTE >= 36 across all lanes.",
            rows=untracked,
            kept=[row for row in untracked if (_safe_float(row.get("dte")) is None or float(row.get("dte")) < 36.0)],
            later_date_set=later_date_set,
            status="diagnostic_retest_required",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="no_primary_damage_tickers",
            description="Reject XLK, SPY, TSLA, and IWM damage clusters.",
            rows=untracked,
            kept=[row for row in untracked if _ticker(row) not in PRIMARY_DAMAGE_TICKERS],
            later_date_set=later_date_set,
            status="diagnostic_retest_required",
            entry_time_only=True,
        ),
        _evaluate_scenario(
            scenario_id="no_extended_damage_tickers",
            description="Reject the extended in-sample damage ticker list.",
            rows=untracked,
            kept=[row for row in untracked if _ticker(row) not in EXTENDED_DAMAGE_TICKERS],
            later_date_set=later_date_set,
            status="overfit_warning",
            entry_time_only=True,
            notes=["Ticker set is learned from this sample and must not be promoted without fresh OOS evidence."],
        ),
        _evaluate_scenario(
            scenario_id="primary_combo_no_debit45_dte36_damage_tickers",
            description="Combine debit <45%, DTE <36, and primary damage ticker rejection across all lanes.",
            rows=untracked,
            kept=[
                row
                for row in untracked
                if (_safe_float(row.get("debit_pct_of_width")) or 0.0) < 45.0
                and (_safe_float(row.get("dte")) is None or float(row.get("dte")) < 36.0)
                and _ticker(row) not in PRIMARY_DAMAGE_TICKERS
            ],
            later_date_set=later_date_set,
            status="diagnostic_retest_required",
            entry_time_only=True,
        ),
    ]

    best_by_pf = sorted(
        scenarios,
        key=lambda item: (
            -float(item["kept_metrics"].get("profit_factor") or 0.0),
            -int(item["kept_count"]),
        ),
    )
    summary = outcome_report.get("summary") if isinstance(outcome_report.get("summary"), dict) else {}
    quote_evidence, evidence_policy = _source_evidence_policy(
        outcome_report,
        record_class="missed_regular_pick_filter_matrix_readback",
    )
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "missed_regular_picks_filter_matrix",
        "source_report": _rel(input_report_path),
        "source_generated_at_utc": outcome_report.get("generated_at_utc"),
        "summary": {
            "input_raw_row_count": len(rows),
            "priced_untracked_rows": len(untracked),
            "source_mark_unpriced_count": int(summary.get("mark_unpriced_count") or 0),
            "source_tracked_rows_with_stored_pnl": summary.get("tracked_rows_with_stored_pnl"),
            "source_tracked_row_count": summary.get("tracked_row_count"),
            "later_date_holdout_dates": sorted(later_date_set),
            "quote_evidence_class": quote_evidence.get("quote_evidence_class"),
            "row_evidence_group": evidence_policy.get("evidence_group"),
        },
        "baseline_metrics": _metrics(untracked),
        "scenarios": scenarios,
        "ranked_scenarios_by_kept_profit_factor": [
            {
                "scenario_id": item["scenario_id"],
                "kept_count": item["kept_count"],
                "profit_factor": item["kept_metrics"].get("profit_factor"),
                "avg_net_pnl_pct": item["kept_metrics"].get("avg_net_pnl_pct"),
                "lost_winner_count": item["lost_winner_count"],
                "avoided_lte_minus_50": item["avoided_deep_loss_count_lte_minus_50"],
                "status": item["status"],
                "survives_later_date_split": item["later_date_read"].get("survives_later_date_split"),
            }
            for item in best_by_pf
        ],
        "decision_read": {
            "live_policy_change": False,
            "recommended_active_protection": [
                "Keep lane profitability as a hard gate.",
                "Route passed lanes through paper/probation until fresh forward rows mature.",
                "Suppress duplicate exact spreads to one risk owner.",
            ],
            "next_research": [
                "Retest debit, DTE, and ticker damage filters on later/fresh samples before scanner promotion.",
                "Do not promote extended ticker exclusion because it is visibly in-sample fitted.",
            ],
        },
        "boundary": {
            "evidence_class": "historical_research_exact_contract_marks",
            "quote_evidence": quote_evidence,
            "evidence_policy": evidence_policy,
            "production_claim": False,
            "broker_fill_claim": False,
            "allowed_use": "counterfactual_filter_design_and_forward_paper_validation",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    baseline = report.get("baseline_metrics") or {}
    boundary = report.get("boundary") or {}
    quote_evidence = boundary.get("quote_evidence") or {}
    evidence_policy = boundary.get("evidence_policy") or {}
    lines = [
        "# Missed Regular Picks Filter Matrix",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Source report: `{report.get('source_report')}`",
        f"- Source generated: `{report.get('source_generated_at_utc')}`",
        f"- Priced untracked rows: `{(report.get('summary') or {}).get('priced_untracked_rows')}`",
        f"- Quote evidence class: `{quote_evidence.get('quote_evidence_class')}`",
        f"- Row evidence group: `{evidence_policy.get('evidence_group')}`",
        f"- Production proof claim: `{boundary.get('production_claim')}`",
        f"- Baseline PF: `{baseline.get('profit_factor')}`",
        f"- Baseline avg net P&L: `{baseline.get('avg_net_pnl_pct')}%`",
        f"- Later-date holdout dates: `{', '.join((report.get('summary') or {}).get('later_date_holdout_dates') or [])}`",
        "",
        "## Matrix",
        "",
        "| Scenario | Status | Kept | Blocked | PF | Avg Net | Lost Winners | Avoided <= -50% | Later Split |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.get("scenarios") or []:
        later = item.get("later_date_read") or {}
        metrics = item.get("kept_metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("scenario_id")),
                    str(item.get("status")),
                    str(item.get("kept_count")),
                    str(item.get("blocked_count")),
                    str(metrics.get("profit_factor")),
                    str(metrics.get("avg_net_pnl_pct")),
                    str(item.get("lost_winner_count")),
                    str(item.get("avoided_deep_loss_count_lte_minus_50")),
                    "pass" if later.get("survives_later_date_split") else "watch",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- Lane profitability remains the hard safety gate.",
            "- Passed lanes are paper/probation candidates, not live-production permission.",
            "- Exact duplicate spreads should be suppressed immediately to a single risk owner.",
            "- Debit, DTE, and ticker filters are promising diagnostics but need fresh/OOS proof before scanner promotion.",
            "- The extended ticker exclusion is explicitly overfit-warning territory.",
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
    parser = argparse.ArgumentParser(description="Build a frozen counterfactual filter matrix for missed regular picks.")
    parser.add_argument("--input-report", type=Path, default=DEFAULT_INPUT_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome_report = _load_json(args.input_report)
    report = build_filter_matrix_report(outcome_report, input_report_path=args.input_report)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "summary": report["summary"],
                    "boundary": report["boundary"],
                    "baseline_metrics": report["baseline_metrics"],
                    "ranked_scenarios_by_kept_profit_factor": report["ranked_scenarios_by_kept_profit_factor"],
                    "artifacts": report.get("artifacts"),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
