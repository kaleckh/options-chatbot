from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_preregistered_momentum_continuation_playbook"
CONCEPT_ID = "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1"

DEFAULT_CAUSAL_SLICE = ROOT / "data" / "profitability-lab" / "regular-options-causal-falsification-slice" / "latest.json"
DEFAULT_MOMENTUM_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-momentum-edge" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-momentum-continuation-playbook"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-preregistered-momentum-continuation-playbook.md"

PERMITTED_RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM")

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
    "do_not_implement_playbook",
    "do_not_create_scanner",
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
    "do_not_reuse_tracked_winner_retuning",
    "do_not_count_raw_overlapping_rows",
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
            "role": "index_breadth_carrier" if symbol in {"SPY", "QQQ", "IWM", "DIA"} else "liquid_confirming_constituent",
            "proof_note": "must be rechecked in any future implementation for point-in-time candidate generation and trusted OPRA/NBBO bid/ask evidence",
        }
        for symbol in PERMITTED_RESEARCH_UNIVERSE
    ]


def _concept(causal_slice: dict[str, Any], momentum_edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept_id": CONCEPT_ID,
        "status": "preregistered_design_only",
        "thesis": (
            "Strong index/QQQ momentum confirmed by breadth and low/mid VIX may support defined-risk call debit "
            "spreads, but only if the future implementation avoids tracked-winner overlap, quarantined lane reuse, "
            "and raw count aggregation."
        ),
        "structure": "defined_risk_call_debit_spreads_only",
        "permitted_research_universe": list(PERMITTED_RESEARCH_UNIVERSE),
        "symbol_rows": _symbol_rows(),
        "causal_inputs": [
            "SPY and QQQ trend/momentum confirmation must be present before candidate generation",
            "breadth confirmation must be measured point-in-time, not inferred after outcomes",
            "VIX state must be low-to-mid or otherwise explicitly bucketed before replay",
            "candidate selection must not use future option outcomes, source marks, or realized P&L",
        ],
        "explicit_exclusions": [
            "tracked-winner retuning",
            "raw overlapping aggregation",
            "existing quarantined lane reopening",
            "source marks as proof",
            "midpoint, EOD, display-only, manual, last-trade, synthetic, stale, or lookahead evidence as proof",
            "any scanner, stop, sizing, proof-bar, live-validation, auto-track, broker, quote-import, evidence-mutation, holdout-consumption, or promotion action",
        ],
        "future_proof_path_required_before_any_profit_claim": [
            "point-in-time candidate rows",
            "trusted OPRA/NBBO exact-contract entry and policy-defined exit bid/ask evidence",
            "side-aware debit-spread pricing",
            "full denominator rows including no-pick, unpriced, zero-bid, and rejected rows",
            "strict-new opportunity dedupe versus the 157-row clean base stack",
            "positive point PF and positive net USD P&L after fees and execution-realistic pricing",
            "stress PF and bootstrap PF lower-bound gates above the configured proof bars",
            "simulated-forward and robust-search compatibility without protected-holdout consumption",
            "fresh forward paper-shadow proof before promotion discussion",
        ],
        "upstream_stop_context": {
            "causal_falsification_status": causal_slice.get("status"),
            "branches_to_stop": causal_slice.get("branches_to_stop"),
            "momentum_edge_status": momentum_edge.get("status"),
        },
    }


def _status(source_artifacts: dict[str, dict[str, Any]]) -> str:
    causal = source_artifacts["causal_falsification"]
    if causal.get("status") != "loaded":
        return "blocked_missing_causal_falsification_slice"
    return "preregistered_design_only"


def build_report(
    *,
    causal_slice_path: Path = DEFAULT_CAUSAL_SLICE,
    momentum_edge_path: Path = DEFAULT_MOMENTUM_EDGE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    causal_slice, causal_meta = _load_json(causal_slice_path, required=True)
    momentum_edge, momentum_meta = _load_json(momentum_edge_path, required=False)
    source_artifacts = {
        "causal_falsification": causal_meta,
        "current_regime_momentum_edge": momentum_meta,
    }
    concept = _concept(causal_slice, momentum_edge) if causal_meta["status"] == "loaded" else None
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _status(source_artifacts),
        **READ_ONLY_FLAGS,
        "scope": "read_only_preregistered_momentum_continuation_playbook_design",
        "is_trade_recommendation": False,
        "concept": concept,
        "concept_id": CONCEPT_ID if concept else None,
        "allowed_next_step": (
            "Send this design back to GPT-5.5 Pro for a continue/stop decision. Future implementation, replay, "
            "quote import, evidence mutation, or forward collection requires a separate explicit decision."
            if concept
            else "Regenerate the causal falsification slice before preregistering a playbook."
        ),
        "acceptance_criteria_for_this_artifact": [
            "defines exactly one causal playbook",
            "keeps status preregistered_design_only",
            "records permitted universe and explicit exclusions",
            "records proof path for any future implementation",
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
    if report.get("concept") is not None and _as_dict(report["concept"]).get("status") != "preregistered_design_only":
        raise ValueError("concept must remain preregistered_design_only")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    concept = _as_dict(report.get("concept"))
    lines = [
        "# Regular Options Preregistered Momentum Continuation Playbook",
        "",
        "This report is generated from `scripts/build_regular_options_preregistered_momentum_continuation_playbook.py`. It defines one read-only causal playbook design only. It does not implement scanner logic, create trades, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        "",
    ]
    if not concept:
        lines.extend(["No concept was emitted because the required causal falsification slice was missing.", ""])
        return "\n".join(lines)
    lines.extend(
        [
            "## Concept",
            "",
            f"- Thesis: {concept['thesis']}",
            f"- Structure: `{concept['structure']}`.",
            f"- Status: `{concept['status']}`.",
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
    lines.extend(["", "## Causal Inputs", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("causal_inputs")))
    lines.extend(["", "## Future Proof Path", ""])
    lines.extend(f"- {item}." for item in _as_list(concept.get("future_proof_path_required_before_any_profit_claim")))
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
    parser = argparse.ArgumentParser(description="Build the read-only preregistered momentum continuation playbook design.")
    parser.add_argument("--causal-slice", type=Path, default=DEFAULT_CAUSAL_SLICE)
    parser.add_argument("--momentum-edge", type=Path, default=DEFAULT_MOMENTUM_EDGE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(causal_slice_path=args.causal_slice, momentum_edge_path=args.momentum_edge)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] == "preregistered_design_only" else 1


if __name__ == "__main__":
    sys.exit(main())
