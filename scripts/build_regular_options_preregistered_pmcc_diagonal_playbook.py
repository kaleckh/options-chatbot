from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_preregistered_pmcc_diagonal_playbook"
CONCEPT_ID = "low_mid_vix_index_pmcc_diagonal_income_v1"
STRUCTURE = "defined_risk_pmcc_style_call_diagonals_only"

DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-pmcc-diagonal-playbook"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-preregistered-pmcc-diagonal-playbook.md"

INITIAL_RESEARCH_UNIVERSE = ("SPY", "QQQ")
FUTURE_EXTENSION_UNIVERSE = ("IWM", "DIA")
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
    "historical_replay_performed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

DENOMINATOR_STATUSES = (
    "no_candidate",
    "rejected_trend_or_vix_bucket",
    "rejected_width_or_liquidity",
    "rejected_undefined_or_uncapped_short_call_risk",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_captured",
    "open_waiting_policy_roll_or_exit",
    "short_call_roll_captured",
    "short_call_expired",
    "assignment_or_ex_dividend_blocked",
    "exact_exit_captured",
    "expired_settled_exact",
    "missing_exit",
)

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
    "do_not_allow_undefined_risk_naked_short_calls",
    "do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
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
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _symbol_rows() -> list[dict[str, Any]]:
    rows = [
        {
            "symbol": symbol,
            "allowed_in_initial_research_design": True,
            "allowed_as_future_extension_only": False,
            "proof_note": "future implementation must recheck long-dated and near-dated call quote depth, short-call roll/assignment/ex-dividend handling, max-loss/collateral, and trusted OPRA/NBBO bid/ask evidence",
        }
        for symbol in INITIAL_RESEARCH_UNIVERSE
    ]
    rows.extend(
        {
            "symbol": symbol,
            "allowed_in_initial_research_design": False,
            "allowed_as_future_extension_only": True,
            "proof_note": "future extension only after a separate proof-surface recheck for diagonal quote depth, roll liquidity, and denominator completeness",
        }
        for symbol in FUTURE_EXTENSION_UNIVERSE
    )
    return rows


def _concept(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept_id": CONCEPT_ID,
        "status": "preregistered_design_only",
        "structure": STRUCTURE,
        "undefined_or_uncapped_short_call_risk_allowed": False,
        "thesis": (
            "In low/mid VIX with persistent index or QQQ trend or range-bound grind, a long later-dated call financed "
            "by short nearer-dated calls may capture directional carry or term premium. This is only researchable if "
            "future replay proves point-in-time trend/regime inputs, diagonal side-aware OPRA/NBBO pricing, short-call "
            "roll/assignment/ex-dividend handling, max-loss/collateral, and full-denominator net USD economics."
        ),
        "initial_research_universe": list(INITIAL_RESEARCH_UNIVERSE),
        "future_extension_universe": list(FUTURE_EXTENSION_UNIVERSE),
        "symbol_rows": _symbol_rows(),
        "historical_research_window": dict(HISTORICAL_RESEARCH_WINDOW),
        "frozen_design": {
            "entry_regime": [
                "trend or range-bound grind signal must be known point-in-time before entry",
                "VIX low or mid bucket must be known point-in-time before entry",
                "no single-name earnings dependency is allowed in the initial index-only design",
                "underlying must be SPY or QQQ for the initial design",
            ],
            "structure_selection": [
                "long call DTE bucket, short call DTE bucket, long-call moneyness or delta proxy, short-call moneyness or delta proxy, max debit, max width, max bid/ask width, and minimum liquidity thresholds must be frozen before replay",
                "short call must be covered by the long later-dated call under a defined max-loss/collateral convention",
                "naked or undefined-risk short-call exposure is forbidden",
                "all entry, roll, and exit legs must have exact OPRA/NBBO bid/ask at the relevant timestamp",
            ],
            "roll_and_exit_policy": [
                "future replay must predefine short-call roll trigger, buy-to-close, sell-to-open, short-call expiry, long-call exit, profit-take, loss-cut, assignment, ex-dividend, and expiry-settlement handling",
                "open rows must remain open_waiting_policy_roll_or_exit until a policy-defined roll, exit, or expiry condition fires",
            ],
        },
        "side_aware_pricing_formulas": {
            "entry_debit": "long_call_ask - short_call_bid",
            "roll_debit_or_credit": "buy_to_close_short_call_ask - sell_to_open_next_short_call_bid",
            "exit_value_with_open_short": "long_call_bid - short_call_ask",
            "exit_value_without_open_short": "long_call_bid",
            "expiry_settlement_value": "policy_defined_intrinsic_value_for_long_call_and_short_call_assignment_or_expiration",
            "net_pnl_usd": "(exit_or_settlement_value - entry_debit - sum(roll_debits_or_credits)) * 100 - fees_and_slippage",
            "max_loss_usd": "policy_defined_long_call_debit_minus_short_call_credit_plus_roll_risk_and_assignment_adjustments_times_100_plus_fees",
            "collateral_convention": "future replay must derive max_loss_usd and required collateral from long/short call strikes, expiries, net debit, roll ledger, assignment/ex-dividend state, contract multiplier, fees, and slippage before any row can be exact",
        },
        "denominator_statuses": list(DENOMINATOR_STATUSES),
        "required_future_replay_engine_support": [
            "point-in-time trend and VIX inputs",
            "diagonal side-aware entry pricing",
            "short-call roll ledger with buy-to-close and sell-to-open bid/ask pricing",
            "side-aware exit pricing and expiry settlement",
            "short-call assignment and ex-dividend classifier",
            "long-call expiration and settlement classifier",
            "max-loss and collateral convention",
            "contract multiplier, fees, slippage, roll costs, and net USD P&L",
            "trusted OPRA/NBBO quote availability for entry, roll, and exit legs",
            "full denominator mapping including rejected undefined-risk short-call rows",
            "protected-holdout guard",
            "strict-new dedupe versus the 157-row clean base stack",
        ],
        "leakage_controls": [
            "candidate generation must not read future trend, future IV, future option returns, realized P&L, source marks, midpoint, EOD, display-only, manual, last-trade, model, synthetic, lookahead, or protected-holdout data",
            "trend signal, VIX bucket, DTE, strikes, roll policy, exit policy, and liquidity thresholds must be available point-in-time before candidate entry",
            "future implementation must freeze all thresholds and roll rules before replay",
        ],
        "future_falsification_plan": [
            "reject if a future implementation cannot produce at least 200 historical exact rows or 30 latest-audit exact rows",
            "reject if quote coverage is below 90 percent",
            "reject if bootstrap PF lower bound is less than or equal to 1.0",
            "reject if stress PF is below 1.0",
            "reject if net USD P&L is less than or equal to 0",
            "reject if material single-ticker, month, date, roll-state, or winner dependence drives profitability",
            "reject if roll, assignment, ex-dividend, expiration, settlement, collateral, or max-loss status is unresolved",
            "reject if any naked or undefined-risk short-call exposure is required",
            "reject if any protected-holdout overlap is detected",
            "reject if profitability depends on post-hoc exclusions or parameter mining",
        ],
        "explicit_exclusions": [
            "scanner or strategy implementation in this slice",
            "historical replay in this slice",
            "quote import or evidence mutation",
            "protected holdout use",
            "live validation, auto-track, broker order, or promotion",
            "naked or undefined-risk short-call exposure",
            "source marks, midpoint, EOD, display-only, stale, last-trade, manual, synthetic, lookahead, or percent-only values as proof",
        ],
        "oracle_context": {
            "selected_branch_id": "new_causal_playbook_generation:low_mid_vix_index_pmcc_diagonal_income_v1",
            "packet_status": packet.get("status"),
            "packet_report_id": packet.get("report_id"),
        },
    }


def _status(source_artifacts: dict[str, dict[str, Any]]) -> str:
    return "preregistered_design_only" if source_artifacts["oracle_packet"].get("status") == "loaded" else "blocked_missing_oracle_packet"


def build_report(*, oracle_packet_path: Path = DEFAULT_ORACLE_PACKET, generated_at_utc: str | None = None) -> dict[str, Any]:
    oracle_packet, packet_meta = _load_json(oracle_packet_path, required=True)
    source_artifacts = {"oracle_packet": packet_meta}
    concept = _concept(oracle_packet) if packet_meta["status"] == "loaded" else None
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(source_artifacts),
        **READ_ONLY_FLAGS,
        "scope": "read_only_preregistered_pmcc_diagonal_design",
        "is_trade_recommendation": False,
        "concept": concept,
        "concept_id": CONCEPT_ID if concept else None,
        "structure": STRUCTURE if concept else None,
        "undefined_or_uncapped_short_call_risk_allowed": False,
        "allowed_next_step": (
            "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future readiness, implementation, "
            "or replay requires a separate explicit research-only approval and must still forbid live, broker, quote "
            "import, evidence mutation, protected holdout consumption, scanner/strategy release, stop/sizing/proof-bar changes, undefined-risk short calls, and promotion."
            if concept
            else "Regenerate the Oracle loop packet before preregistering this playbook."
        ),
        "acceptance_criteria_for_this_artifact": [
            "defines exactly one PMCC-style diagonal concept",
            "keeps status preregistered_design_only",
            "records frozen SPY/QQQ initial universe and IWM/DIA future extension boundary",
            "records side-aware diagonal entry, roll, exit, and expiry formulas",
            "records short-call assignment, ex-dividend, expiration, roll, collateral, and max-loss requirements",
            "records denominator statuses including rejected_undefined_or_uncapped_short_call_risk",
            "records future replay engine requirements and leakage controls",
            "records falsification criteria with sample, PF, stress, coverage, dependency, roll/assignment/ex-dividend/expiry, max-loss, and protected-holdout thresholds",
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
    if report.get("undefined_or_uncapped_short_call_risk_allowed") is not False:
        raise ValueError("undefined short-call risk must be forbidden")
    concept = _as_dict(report.get("concept"))
    if concept:
        if concept.get("concept_id") != CONCEPT_ID:
            raise ValueError("unexpected concept_id")
        if concept.get("status") != "preregistered_design_only":
            raise ValueError("concept must remain preregistered_design_only")
        if concept.get("structure") != STRUCTURE:
            raise ValueError("unexpected structure")
        if concept.get("undefined_or_uncapped_short_call_risk_allowed") is not False:
            raise ValueError("concept must forbid undefined short-call risk")
        for status in DENOMINATOR_STATUSES:
            if status not in concept.get("denominator_statuses", []):
                raise ValueError(f"missing denominator status {status}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    concept = _as_dict(report.get("concept"))
    lines = [
        "# Regular Options Preregistered PMCC Diagonal Playbook",
        "",
        "This report is generated from `scripts/build_regular_options_preregistered_pmcc_diagonal_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, allow naked short calls, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        f"- Undefined or uncapped short-call risk allowed: `{_fmt_bool(report['undefined_or_uncapped_short_call_risk_allowed'])}`.",
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
            "| Symbol | Initial | Future Extension | Proof Note |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in _as_list(concept.get("symbol_rows")):
        row = _as_dict(row)
        lines.append(
            f"| `{row.get('symbol')}` | `{_fmt_bool(row.get('allowed_in_initial_research_design'))}` | `{_fmt_bool(row.get('allowed_as_future_extension_only'))}` | {row.get('proof_note')} |"
        )

    lines.extend(["", "## Frozen Design", ""])
    for heading, values in _as_dict(concept.get("frozen_design")).items():
        lines.append(f"### {heading.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(f"- {item}." for item in _as_list(values))
        lines.append("")

    lines.extend(["## Side-Aware Pricing And Risk", ""])
    for key in (
        "entry_debit",
        "roll_debit_or_credit",
        "exit_value_with_open_short",
        "exit_value_without_open_short",
        "expiry_settlement_value",
        "net_pnl_usd",
        "max_loss_usd",
        "collateral_convention",
    ):
        lines.append(f"- `{key}`: `{formulas.get(key)}`.")

    lines.extend(["", "## Denominator Statuses", ""])
    lines.extend(f"- `{item}`" for item in _as_list(concept.get("denominator_statuses")))
    lines.extend(["", "## Leakage Controls", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("leakage_controls")))
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


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Build the read-only preregistered PMCC diagonal playbook design.")
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
