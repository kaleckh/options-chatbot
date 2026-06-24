from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_preregistered_vrp_credit_spread_playbook"
CONCEPT_ID = "low_mid_vix_index_put_credit_spread_vrp_v1"

DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-vrp-credit-spread-playbook"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-preregistered-vrp-credit-spread-playbook.md"

PERMITTED_RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
HISTORICAL_RESEARCH_WINDOW = {
    "start_date": "2024-06-01",
    "end_date": "2026-05-31",
    "as_of_date": "2026-06-04",
    "protected_holdout_consumed": False,
}

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "lane_implementation_performed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_implement_scanner_or_playbook_logic",
    "do_not_run_replay",
    "do_not_create_trades",
    "do_not_submit_broker_orders",
    "do_not_enable_auto_track",
    "do_not_enable_live_validation",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_databases",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
)

DENOMINATOR_STATUSES = (
    "no_candidate",
    "rejected_width_or_credit",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_captured",
    "open_waiting_policy_exit",
    "exact_exit_captured",
    "assignment_or_expiration_blocked",
    "missing_exit",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _symbol_rows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "allowed_in_research_design": True,
            "role": "index_credit_spread_underlying",
            "proof_note": "future implementation must recheck point-in-time option-chain liquidity, assignment/expiration handling, and trusted OPRA/NBBO bid/ask evidence",
        }
        for symbol in PERMITTED_RESEARCH_UNIVERSE
    ]


def _concept(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept_id": CONCEPT_ID,
        "status": "preregistered_design_only",
        "thesis": (
            "In low/mid VIX, liquid index put-credit verticals may harvest volatility risk premium and skew "
            "while using defined max loss, but the idea is only useful if future replay proves side-aware credit "
            "entry, side-aware debit exit, assignment/expiration handling, and full-denominator economics."
        ),
        "structure": "defined_risk_put_credit_spreads_only",
        "permitted_research_universe": list(PERMITTED_RESEARCH_UNIVERSE),
        "symbol_rows": _symbol_rows(),
        "historical_research_window": dict(HISTORICAL_RESEARCH_WINDOW),
        "frozen_design": {
            "entry_regime": [
                "VIX low/mid bucket must be known point-in-time before entry",
                "index trend must not be in a crash regime before entry",
                "underlying must be one of SPY, QQQ, IWM, DIA",
            ],
            "contract_selection": [
                "short put is out-of-the-money by a fixed moneyness or delta proxy frozen before replay",
                "long put is farther out-of-the-money than the short put",
                "spread width, minimum credit, maximum bid/ask width, and liquidity thresholds must be frozen before replay",
                "both legs must have exact OPRA/NBBO bid/ask at the candidate entry timestamp",
            ],
            "exit_policy": [
                "future replay must predefine profit-take, loss-cut, time-exit, assignment, and expiration handling",
                "open rows must remain open_waiting_policy_exit until a policy-defined exit condition fires",
            ],
        },
        "candidate_geometry": {
            "dte_min": 21,
            "dte_max": 45,
            "short_put_moneyness_or_delta": "prefer_abs_delta_closest_to_0.20_between_0.15_and_0.25_else_3_to_7_pct_otm",
            "long_put_distance": "prefer_5_point_width_else_nearest_available_lower_put_with_width_between_3_and_10_points",
            "minimum_entry_credit_pct_width": 0.20,
            "maximum_leg_bid_ask_width_pct_mid": 0.25,
            "exit_policy": {
                "profit_take_pct_of_credit": 0.50,
                "loss_cut_multiple_of_credit": 2.00,
                "time_exit_dte": 7,
                "expiration_settlement": "cash_settled_index_intrinsic_value_or_etf_assignment_blocked_without_classification",
            },
        },
        "side_aware_pricing_formulas": {
            "entry_credit": "short_put_bid - long_put_ask",
            "exit_debit": "short_put_ask - long_put_bid",
            "net_pnl_usd": "(entry_credit - exit_debit) * 100 - fees_and_slippage",
            "max_loss_usd": "(spread_width - entry_credit) * 100 + fees_and_slippage",
        },
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "required_future_replay_engine_support": [
            "credit-spread side-aware bid/ask pricing",
            "assignment and expiration classification",
            "margin and max-loss convention",
            "policy-defined exit handling",
            "strict-new dedupe versus the 157-row clean base stack",
            "full denominator output including rejected, missing, zero-bid, open, exact-exit, assignment, and expiration rows",
        ],
        "future_falsification_plan": [
            "reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows",
            "reject if quote coverage is below 90 percent",
            "reject if PF lower bound is less than or equal to 1.0",
            "reject if stress PF is below 1.0",
            "reject if net USD P&L is negative",
            "reject if material single-ticker, month, date, or winner dependence drives profitability",
            "reject if assignment, expiration, margin, or max-loss accounting is unresolved",
            "reject if profitability depends on post-hoc exclusions or parameter mining",
        ],
        "explicit_exclusions": [
            "implementation or replay in this slice",
            "scanner policy or strategy logic changes",
            "quote import or evidence mutation",
            "protected holdout use",
            "live validation, auto-track, broker order, or promotion",
            "source marks, midpoint, EOD, display-only, stale, last-trade, manual, synthetic, lookahead, or percent-only values as proof",
        ],
        "oracle_context": {
            "selected_branch_id": "new_causal_playbook_generation:low_mid_vix_index_put_credit_spread_vrp_v1",
            "packet_status": packet.get("status"),
            "packet_report_id": packet.get("report_id"),
        },
    }


def _status(source_artifacts: dict[str, dict[str, Any]]) -> str:
    packet = source_artifacts["oracle_packet"]
    if packet.get("status") != "loaded":
        return "blocked_missing_oracle_packet"
    return "preregistered_design_only"


def build_report(
    *,
    oracle_packet_path: Path = DEFAULT_ORACLE_PACKET,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    oracle_packet, packet_meta = _load_json(oracle_packet_path, required=True)
    source_artifacts = {"oracle_packet": packet_meta}
    concept = _concept(oracle_packet) if packet_meta["status"] == "loaded" else None
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(source_artifacts),
        **READ_ONLY_FLAGS,
        "scope": "read_only_preregistered_vrp_credit_spread_playbook_design",
        "is_trade_recommendation": False,
        "concept": concept,
        "concept_id": CONCEPT_ID if concept else None,
        "structure": "defined_risk_put_credit_spreads_only" if concept else None,
        "allowed_next_step": (
            "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation or replay "
            "requires a separate explicit research-only approval and must still forbid live, broker, quote import, "
            "evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, and promotion."
            if concept
            else "Regenerate the Oracle loop packet before preregistering this playbook."
        ),
        "acceptance_criteria_for_this_artifact": [
            "defines exactly one VRP credit-spread concept",
            "keeps status preregistered_design_only",
            "records frozen universe and inclusion/exclusion rules",
            "records side-aware entry and exit formulas",
            "records denominator statuses",
            "records future replay engine requirements",
            "records falsification criteria with sample, PF, stress, coverage, and concentration thresholds",
            "keeps all read-only and no-live/no-broker/no-mutation flags false",
        ],
        "source_artifacts": source_artifacts,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    concept = _as_dict(report.get("concept"))
    if concept:
        if concept.get("concept_id") != CONCEPT_ID:
            raise ValueError("unexpected concept_id")
        if concept.get("status") != "preregistered_design_only":
            raise ValueError("concept must remain preregistered_design_only")
        if concept.get("structure") != "defined_risk_put_credit_spreads_only":
            raise ValueError("unexpected structure")
        geometry = _as_dict(concept.get("candidate_geometry"))
        for key in ("dte_min", "dte_max", "short_put_moneyness_or_delta", "long_put_distance", "exit_policy"):
            if geometry.get(key) in (None, ""):
                raise ValueError(f"missing candidate geometry field {key}")
        for status in DENOMINATOR_STATUSES:
            if status not in concept.get("denominator_statuses", []):
                raise ValueError(f"missing denominator status {status}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    concept = _as_dict(report.get("concept"))
    lines = [
        "# Regular Options Preregistered VRP Credit Spread Playbook",
        "",
        "This report is generated from `scripts/build_regular_options_preregistered_vrp_credit_spread_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        "",
    ]
    if not concept:
        lines.extend(["No concept was emitted because the required Oracle loop packet was missing.", ""])
        return "\n".join(lines)

    window = _as_dict(concept.get("historical_research_window"))
    formulas = _as_dict(concept.get("side_aware_pricing_formulas"))
    lines.extend(
        [
            "## Concept",
            "",
            f"- Thesis: {concept['thesis']}",
            f"- Structure: `{concept['structure']}`.",
            f"- Status: `{concept['status']}`.",
            f"- Historical research window target: `{window.get('start_date')}` through `{window.get('end_date')}` as of `{window.get('as_of_date')}`.",
            "",
            "## Universe",
            "",
            "| Symbol | Role | Proof Note |",
            "| --- | --- | --- |",
        ]
    )
    for row in _as_list(concept.get("symbol_rows")):
        row = _as_dict(row)
        lines.append(f"| `{row.get('symbol')}` | `{row.get('role')}` | {row.get('proof_note')} |")

    lines.extend(["", "## Frozen Design", ""])
    frozen = _as_dict(concept.get("frozen_design"))
    for heading, values in frozen.items():
        lines.append(f"### {heading.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(f"- {item}." for item in _as_list(values))
        lines.append("")

    geometry = _as_dict(concept.get("candidate_geometry"))
    exit_policy = _as_dict(geometry.get("exit_policy"))
    lines.extend(
        [
            "## Candidate Geometry",
            "",
            f"- DTE range: `{geometry.get('dte_min')}` to `{geometry.get('dte_max')}`.",
            f"- Short put selection: `{geometry.get('short_put_moneyness_or_delta')}`.",
            f"- Long put distance: `{geometry.get('long_put_distance')}`.",
            f"- Minimum entry credit pct width: `{geometry.get('minimum_entry_credit_pct_width')}`.",
            f"- Maximum leg bid/ask width pct mid: `{geometry.get('maximum_leg_bid_ask_width_pct_mid')}`.",
            f"- Profit take: `{exit_policy.get('profit_take_pct_of_credit')}` of credit.",
            f"- Loss cut: `{exit_policy.get('loss_cut_multiple_of_credit')}` times credit.",
            f"- Time exit DTE: `{exit_policy.get('time_exit_dte')}`.",
            "",
        ]
    )

    lines.extend(["## Side-Aware Pricing", ""])
    for key in ("entry_credit", "exit_debit", "net_pnl_usd", "max_loss_usd"):
        lines.append(f"- `{key}`: `{formulas.get(key)}`.")

    lines.extend(["", "## Denominator Statuses", ""])
    lines.extend(f"- `{item}`" for item in _as_list(concept.get("denominator_statuses")))
    lines.extend(["", "## Required Future Replay Engine Support", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("required_future_replay_engine_support")))
    lines.extend(["", "## Falsification Plan", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("future_falsification_plan")))
    lines.extend(["", "## Explicit Exclusions", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("explicit_exclusions")))
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
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
    parser = argparse.ArgumentParser(description="Build the read-only preregistered VRP credit-spread playbook design.")
    parser.add_argument("--oracle-packet", type=Path, default=DEFAULT_ORACLE_PACKET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(oracle_packet_path=args.oracle_packet)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] == "preregistered_design_only" else 1


if __name__ == "__main__":
    sys.exit(main())
