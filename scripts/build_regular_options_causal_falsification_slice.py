from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_causal_falsification_slice"

DEFAULT_FRONTIER = ROOT / "data" / "profitability-lab" / "regular-options-countable-throughput-frontier" / "latest.json"
DEFAULT_MOMENTUM_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-momentum-edge" / "latest.json"
DEFAULT_INCUBATOR = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-lane-incubator" / "latest.json"
DEFAULT_WALK_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-causal-falsification-slice"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-causal-falsification-slice.md"

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "live_entry_allowed": False,
    "auto_track_allowed": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades",
    "do_not_submit_broker_orders",
    "do_not_enable_auto_track",
    "do_not_enable_live_validation",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic_for_release",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_databases",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_raw_overlapping_rows",
    "do_not_treat_historical_rows_as_forward_proof",
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


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


def _candidate_map(frontier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _as_list(frontier.get("candidate_rankings")):
        row_dict = _as_dict(row)
        candidate_id = str(row_dict.get("candidate_id") or "").strip()
        if candidate_id:
            result[candidate_id] = row_dict
    return result


def _top_rows(frontier: dict[str, Any], decision: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = [row for row in _as_list(frontier.get("candidate_rankings")) if _as_dict(row).get("decision") == decision]
    rows = [_as_dict(row) for row in rows]
    return sorted(
        rows,
        key=lambda row: (
            -_safe_int(row.get("strict_new_rows_after_opportunity_dedupe")),
            -_safe_int(row.get("with_candidate_exact_rows")),
            str(row.get("candidate_id")),
        ),
    )[:limit]


def _hypothesis(
    *,
    hypothesis_id: str,
    causal_claim: str,
    status: str,
    evidence_rows: list[dict[str, Any]],
    falsification_reason: str,
    next_action: str,
    approval_required: bool = False,
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis_id,
        "causal_claim": causal_claim,
        "status": status,
        "approval_required": approval_required,
        "evidence": [
            {
                "candidate_id": row.get("candidate_id"),
                "candidate_family": row.get("candidate_family") or row.get("lane_id"),
                "decision": row.get("decision"),
                "strict_new_rows": row.get("strict_new_rows_after_opportunity_dedupe") or row.get("strict_new_trade_count"),
                "with_candidate_exact_rows": row.get("with_candidate_exact_rows") or row.get("with_candidate_trade_count"),
                "point_profit_factor": row.get("point_profit_factor") or row.get("profit_factor"),
                "strict_new_profit_factor": row.get("strict_new_profit_factor"),
                "stress_profit_factor": row.get("stress_profit_factor") or row.get("stress_5pct_per_side_profit_factor"),
                "quote_coverage_pct": row.get("quote_coverage_pct"),
                "unpriced_rows": row.get("unpriced_rows"),
                "blockers": row.get("blockers") or row.get("reason_codes") or [],
            }
            for row in evidence_rows
        ],
        "falsification_reason": falsification_reason,
        "next_action": next_action,
    }


def _build_hypotheses(frontier: dict[str, Any], momentum_edge: dict[str, Any], incubator: dict[str, Any], walk_forward: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _candidate_map(frontier)
    raw_count_rows = [row for row in _as_list(frontier.get("candidate_rankings")) if _as_dict(row).get("count_gap_closed")]
    execution_blocked = _top_rows(frontier, "blocked_execution_quality")
    negative = _top_rows(frontier, "rejected_negative_or_flat_edge")
    below_count = _top_rows(frontier, "blocked_below_strict_new_count")
    all_below_count = [_as_dict(row) for row in _as_list(frontier.get("candidate_rankings")) if _as_dict(row).get("decision") == "blocked_below_strict_new_count"]
    index_iwm_evidence = [
        row
        for row in all_below_count
        if row.get("candidate_id")
        in {
            "sleeve_next_index_refill_v1",
            "sleeve_ticker_iwm",
            "iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves",
            "sleeve_next_index_with_iwm_spy_control_v1",
        }
    ]
    index_iwm_evidence = sorted(
        index_iwm_evidence,
        key=lambda row: (
            row.get("candidate_id") != "sleeve_next_index_refill_v1",
            -_safe_int(row.get("strict_new_rows_after_opportunity_dedupe")),
            str(row.get("candidate_id")),
        ),
    )
    hypotheses = [
        _hypothesis(
            hypothesis_id="raw_count_aggregation_is_enough",
            causal_claim="Combining existing all-planned variants with the clean stack can reach profitable throughput by raw row count.",
            status="falsified_existing_surface",
            evidence_rows=[_as_dict(row) for row in raw_count_rows[:8]],
            falsification_reason=(
                f"{frontier.get('raw_count_candidate_count')} raw-count candidates exist, but "
                f"{frontier.get('countable_throughput_candidate_found')} countable throughput candidates passed strict-new, execution, stress, and lower-bound gates."
            ),
            next_action="Stop raw overlapping aggregation as a profitability branch.",
        ),
        _hypothesis(
            hypothesis_id="tracked_winner_throughput_addon",
            causal_claim="Tracked-winner variants can supply the missing strict-new profitable rows.",
            status="falsified_existing_surface",
            evidence_rows=[row for row in execution_blocked + negative if "tracked_winner" in str(row.get("candidate_id"))][:5],
            falsification_reason="The highest-count tracked-winner rows are execution-fragile, stress-fragile, negative/flat, or lower-bound blocked.",
            next_action="Do not spend the next loop retuning tracked-winner count variants without new causal evidence.",
        ),
        _hypothesis(
            hypothesis_id="index_or_iwm_clean_refill_closes_gap",
            causal_claim="Clean index/IWM refill rows can close the 43 strict-new row gap without damaging proof quality.",
            status="falsified_existing_surface",
            evidence_rows=index_iwm_evidence[:5] or [rows.get("sleeve_next_index_refill_v1", {})],
            falsification_reason="The cleaner index/IWM rows are too thin after strict-new opportunity dedupe to reach the 200-row target.",
            next_action="Keep them as small scouts or controls, not the next profitability loop driver.",
        ),
        _hypothesis(
            hypothesis_id="current_regime_momentum_playbook_existing_artifacts",
            causal_claim="The approved current-regime momentum continuation concept is already validated by existing artifacts.",
            status="falsified_existing_surface",
            evidence_rows=[_as_dict(row) for row in _as_list(momentum_edge.get("candidate_rankings"))[:6]],
            falsification_reason=(
                "The momentum-edge report found raw count but zero countable profitable momentum-edge candidates; "
                f"status is `{momentum_edge.get('status')}`."
            ),
            next_action="A genuinely new causal playbook would need preregistration; existing momentum-compatible artifacts are not enough.",
        ),
        _hypothesis(
            hypothesis_id="new_preregistered_causal_playbook",
            causal_claim="A new preregistered playbook may still be a significant upgrade if it tests a causal mechanism not already exhausted.",
            status="not_falsified_requires_next_oracle_or_operator_selection",
            evidence_rows=[],
            falsification_reason="This branch has not been tested because the current artifacts only cover implemented historical variants.",
            next_action=(
                "Ask GPT-5.5 Pro to choose exactly one new read-only causal playbook design or declare that no significant "
                "non-approved upgrade remains. Implementation must remain artifact-only unless operator approval is explicitly granted."
            ),
            approval_required=False,
        ),
    ]
    if _as_dict(walk_forward.get("summary")).get("promotion_ready") is True or walk_forward.get("promotion_ready") is True:
        hypotheses.append(
            _hypothesis(
                hypothesis_id="historical_walk_forward_nomination",
                causal_claim="The current historical walk-forward result is nomination-ready.",
                status="contradicted_by_current_readback",
                evidence_rows=[],
                falsification_reason="Walk-forward unexpectedly reports promotion-ready; this conflicts with the current frontier stop and needs review before any loop action.",
                next_action="Fail closed and reconcile walk-forward versus frontier before proceeding.",
            )
        )
    return hypotheses


def _overall_status(source_artifacts: dict[str, dict[str, Any]], hypotheses: list[dict[str, Any]]) -> str:
    if any(meta.get("required") and meta.get("status") != "loaded" for meta in source_artifacts.values()):
        return "blocked_missing_required_frontier"
    if any(row["status"] == "not_falsified_requires_next_oracle_or_operator_selection" for row in hypotheses):
        return "existing_surface_falsified_new_causal_branch_still_possible"
    return "causal_surface_exhausted_under_current_approvals"


def build_report(
    *,
    frontier_path: Path = DEFAULT_FRONTIER,
    momentum_edge_path: Path = DEFAULT_MOMENTUM_EDGE,
    incubator_path: Path = DEFAULT_INCUBATOR,
    walk_forward_path: Path = DEFAULT_WALK_FORWARD,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    frontier, frontier_meta = _load_json(frontier_path, required=True)
    momentum_edge, momentum_meta = _load_json(momentum_edge_path, required=False)
    incubator, incubator_meta = _load_json(incubator_path, required=False)
    walk_forward, walk_forward_meta = _load_json(walk_forward_path, required=False)
    source_artifacts = {
        "countable_throughput_frontier": frontier_meta,
        "current_regime_momentum_edge": momentum_meta,
        "current_regime_lane_incubator": incubator_meta,
        "historical_walk_forward": walk_forward_meta,
    }
    hypotheses = _build_hypotheses(frontier, momentum_edge, incubator, walk_forward) if frontier_meta["status"] == "loaded" else []
    counts = Counter(row["status"] for row in hypotheses)
    significant_upgrade_available = any(
        row["status"] == "not_falsified_requires_next_oracle_or_operator_selection" for row in hypotheses
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(source_artifacts, hypotheses),
        **READ_ONLY_FLAGS,
        "scope": "read_only_preregistered_causal_falsification_slice",
        "is_trade_recommendation": False,
        "frontier_status": frontier.get("status"),
        "frontier_decision_counts": frontier.get("decision_counts") or {},
        "frontier_candidate_count": frontier.get("candidate_count"),
        "frontier_raw_count_candidate_count": frontier.get("raw_count_candidate_count"),
        "frontier_countable_candidate_found": frontier.get("countable_throughput_candidate_found"),
        "momentum_edge_status": momentum_edge.get("status"),
        "incubator_status": incubator.get("status"),
        "source_artifacts": source_artifacts,
        "hypothesis_count": len(hypotheses),
        "hypothesis_status_counts": dict(sorted(counts.items())),
        "hypotheses": hypotheses,
        "continue_loop": significant_upgrade_available,
        "significant_upgrade_available": significant_upgrade_available,
        "next_oracle_packet_instruction": (
            "Use this causal falsification slice in the next GPT-5.5 Pro packet. GPT-5.5 must either select exactly one "
            "new read-only causal playbook/design task or return continue_loop=false because no significant upgrade remains "
            "without operator approval."
        ),
        "next_codex_task_if_oracle_stalls": {
            "objective": "Prepare, but do not implement, one new read-only causal playbook design surface for GPT-5.5 selection.",
            "allowed_files_or_artifacts": [
                "docs/research-decisions/options_oracle_profit_loop_packet_latest.md",
                "data/forward-tracking/options_oracle_profit_loop_packet_latest.json",
                "docs/regular-options-causal-falsification-slice.md",
                "data/profitability-lab/regular-options-causal-falsification-slice/latest.json",
            ],
            "forbidden_actions": list(PROHIBITED_ACTIONS),
            "stop_condition": "Stop if GPT-5.5 says no significant upgrade remains under current approvals.",
        },
        "branches_to_stop": [
            "raw overlapping count aggregation",
            "tracked-winner count retuning without new causal evidence",
            "clean index/IWM refill as the primary gap closer",
            "existing current-regime momentum-compatible artifact aggregation",
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("causal falsification slice cannot accept profitability")
    if report.get("promotion_ready") is not False:
        raise ValueError("causal falsification slice cannot promote")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Causal Falsification Slice",
        "",
        "This report is generated from `scripts/build_regular_options_causal_falsification_slice.py`. It is a read-only preregistered causal falsification artifact. It does not create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, run live validation, enable auto-track, submit broker orders, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Continue loop: `{_fmt_bool(report['continue_loop'])}`.",
        f"- Significant upgrade available: `{_fmt_bool(report['significant_upgrade_available'])}`.",
        f"- Frontier status: `{report.get('frontier_status')}`.",
        f"- Frontier candidates / raw-count candidates: `{report.get('frontier_candidate_count')}` / `{report.get('frontier_raw_count_candidate_count')}`.",
        f"- Countable candidate found: `{_fmt_bool(report.get('frontier_countable_candidate_found'))}`.",
        f"- Hypothesis status counts: `{json.dumps(report['hypothesis_status_counts'], sort_keys=True)}`.",
        "",
        "## Hypotheses",
        "",
        "| Hypothesis | Status | Approval Required | Falsification Reason | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in _as_list(report.get("hypotheses")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('hypothesis_id')}`",
                    f"`{row.get('status')}`",
                    f"`{_fmt_bool(row.get('approval_required'))}`",
                    str(row.get("falsification_reason")).replace("|", "/"),
                    str(row.get("next_action")).replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Evidence Rows", ""])
    for row in _as_list(report.get("hypotheses")):
        row = _as_dict(row)
        lines.extend([f"### `{row.get('hypothesis_id')}`", ""])
        evidence = [_as_dict(item) for item in _as_list(row.get("evidence"))]
        if not evidence:
            lines.append("- No existing artifact rows. This branch requires a new preregistered design before testing.")
            lines.append("")
            continue
        lines.extend(
            [
                "| Candidate | Decision | Strict New | With Base | PF | Stress PF | Coverage | Unpriced | Blockers |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for item in evidence:
            blockers = ", ".join(str(value) for value in _as_list(item.get("blockers")))[:260]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{item.get('candidate_id')}`",
                        f"`{item.get('decision')}`",
                        str(item.get("strict_new_rows")),
                        str(item.get("with_candidate_exact_rows")),
                        str(item.get("point_profit_factor")),
                        str(item.get("stress_profit_factor")),
                        str(item.get("quote_coverage_pct")),
                        str(item.get("unpriced_rows")),
                        blockers,
                    ]
                )
                + " |"
            )
        lines.append("")
    lines.extend(
        [
            "## Next GPT-5.5 Instruction",
            "",
            report["next_oracle_packet_instruction"],
            "",
            "## Branches To Stop",
            "",
        ]
    )
    lines.extend(f"- {item}." for item in _as_list(report.get("branches_to_stop")))
    lines.extend(["", "## Prohibited Actions", ""])
    lines.extend(f"- `{action}`" for action in _as_list(report.get("prohibited_actions")))
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options causal falsification slice.")
    parser.add_argument("--frontier", type=Path, default=DEFAULT_FRONTIER)
    parser.add_argument("--momentum-edge", type=Path, default=DEFAULT_MOMENTUM_EDGE)
    parser.add_argument("--incubator", type=Path, default=DEFAULT_INCUBATOR)
    parser.add_argument("--walk-forward", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        frontier_path=args.frontier,
        momentum_edge_path=args.momentum_edge,
        incubator_path=args.incubator,
        walk_forward_path=args.walk_forward,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
