from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_current_regime_momentum_edge"

DEFAULT_ALL_PLANNED = (
    ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "all-planned-sleeves" / "latest.json"
)
DEFAULT_INCUBATOR = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-lane-incubator" / "latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-momentum-edge"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-current-regime-momentum-edge.md"

DEFAULT_TARGET_MIN_EXACT_ROWS = 200
DEFAULT_MIN_QUOTE_COVERAGE_PCT = 90.0
DEFAULT_MIN_STRESS_PF = 1.0

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "lane_implementation_performed": False,
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

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_current_regime_momentum_edge_test",
    "do_not_submit_broker_orders_from_current_regime_momentum_edge_test",
    "do_not_enable_auto_track_from_current_regime_momentum_edge_test",
    "do_not_enable_live_validation_from_current_regime_momentum_edge_test",
    "do_not_change_scanner_policy_from_current_regime_momentum_edge_test",
    "do_not_change_strategy_logic_from_current_regime_momentum_edge_test",
    "do_not_change_stops_from_current_regime_momentum_edge_test",
    "do_not_change_sizing_from_current_regime_momentum_edge_test",
    "do_not_lower_proof_bars_from_current_regime_momentum_edge_test",
    "do_not_import_quotes_from_current_regime_momentum_edge_test",
    "do_not_mutate_evidence_databases_from_current_regime_momentum_edge_test",
    "do_not_consume_protected_holdout_from_current_regime_momentum_edge_test",
    "do_not_treat_raw_overlapping_trade_counts_as_countable_edge",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
)

INCLUDE_TERMS = (
    "index",
    "spy",
    "qqq",
    "iwm",
    "xlk",
    "smh",
    "semiconductor",
    "momentum",
    "relative_strength",
    "sector_rotation",
    "tracked_winner",
    "move_bucket",
)

EXCLUDE_TERMS = (
    "put",
    "bearish",
    "xle",
    "xlf",
    "kre",
    "tlt",
    "defensive",
    "reit",
    "industrial",
    "cat",
    "pld",
    "wmt",
    "pm_",
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
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 4) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "error": None,
    }
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


def _matches_momentum(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("variant_id", "candidate_id", "lane_id", "description", "strategy_family")
    ).lower()
    if not any(term in text for term in INCLUDE_TERMS):
        return False
    return not any(term in text for term in EXCLUDE_TERMS)


def _variant_candidate(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(row.get("standalone_metrics"))
    robustness = _as_dict(row.get("robustness"))
    novelty = _as_dict(row.get("novelty_vs_core_plus_clean_reference"))
    exact_rows = _safe_int(metrics.get("exact_trade_count") or metrics.get("priced_trade_count"))
    return {
        "candidate_id": str(row.get("variant_id") or ""),
        "lane_id": str(row.get("lane_id") or ""),
        "source_family": "all_planned_variant",
        "description": row.get("description"),
        "run_path": row.get("run_path"),
        "worth_status": row.get("worth_status"),
        "exact_rows": exact_rows,
        "priced_rows": _safe_int(metrics.get("priced_trade_count"), exact_rows),
        "unpriced_rows": _safe_int(metrics.get("unpriced_trade_count")),
        "profit_factor": _round(metrics.get("profit_factor")),
        "avg_pnl_pct": _round(metrics.get("avg_pnl_pct"), 2),
        "win_rate_pct": _round(metrics.get("win_rate_pct"), 2),
        "quote_coverage_pct": _round(metrics.get("quote_coverage_pct"), 2),
        "stress_5pct_per_side_profit_factor": _round(robustness.get("stress_5pct_per_side_profit_factor")),
        "rolling_status": robustness.get("rolling_status"),
        "base_clean_trade_count": _safe_int(novelty.get("base_clean_trade_count")),
        "with_candidate_trade_count": _safe_int(novelty.get("with_candidate_trade_count")),
        "strict_new_trade_count": _safe_int(novelty.get("strict_new_trade_count")),
        "gap_after_candidate": _safe_int(novelty.get("gap_after_candidate")),
        "suppressed_duplicate_trade_count": _safe_int(novelty.get("suppressed_duplicate_trade_count")),
        "duplicate_group_count": _safe_int(novelty.get("duplicate_group_count")),
        "raw_count_closes_target": False,
        "decision": "unclassified",
        "reason_codes": [],
        "next_step": "",
    }


def _classify_candidate(
    candidate: dict[str, Any],
    *,
    target_min_exact_rows: int,
    min_quote_coverage_pct: float,
    min_stress_pf: float,
) -> dict[str, Any]:
    row = dict(candidate)
    reasons: list[str] = []
    exact_rows = _safe_int(row.get("exact_rows"))
    with_count = _safe_int(row.get("with_candidate_trade_count"))
    strict_new = _safe_int(row.get("strict_new_trade_count"))
    base_count = _safe_int(row.get("base_clean_trade_count"))
    strict_new_needed = max(int(target_min_exact_rows) - base_count, 0) if base_count else int(target_min_exact_rows)
    pf = _safe_float(row.get("profit_factor"))
    stress_pf = _safe_float(row.get("stress_5pct_per_side_profit_factor"))
    coverage = _safe_float(row.get("quote_coverage_pct"))
    unpriced = _safe_int(row.get("unpriced_rows"))
    worth = str(row.get("worth_status") or "")

    row["strict_new_needed_to_hit_target"] = strict_new_needed
    row["raw_count_closes_target"] = (
        with_count >= int(target_min_exact_rows) and strict_new >= strict_new_needed
        if with_count
        else exact_rows >= int(target_min_exact_rows)
    )

    if exact_rows <= 0:
        row["decision"] = "blocked_no_current_candidates"
        reasons.append("no_exact_rows")
    elif pf is None or pf <= 1.0:
        row["decision"] = "rejected_negative_or_flat_edge"
        reasons.append("point_profit_factor_not_above_1")
    elif not row["raw_count_closes_target"]:
        row["decision"] = "blocked_below_trade_count_target"
        reasons.append(f"with_candidate_rows_{with_count or exact_rows}_below_target_{target_min_exact_rows}")
    else:
        row["decision"] = "candidate_count_target_met_research_only"

    if coverage is None:
        reasons.append("quote_coverage_missing")
    elif coverage < float(min_quote_coverage_pct):
        reasons.append(f"quote_coverage_{coverage}_below_{min_quote_coverage_pct}")
    if unpriced > 0:
        reasons.append(f"unpriced_rows_{unpriced}")
    if stress_pf is None:
        reasons.append("stress_pf_missing")
    elif stress_pf < float(min_stress_pf):
        reasons.append(f"stress_pf_{stress_pf}_below_{min_stress_pf}")
    if strict_new < strict_new_needed:
        reasons.append(f"strict_new_rows_{strict_new}_below_needed_{strict_new_needed}")
    if row["raw_count_closes_target"] and strict_new < strict_new_needed:
        reasons.append("raw_combined_count_not_countable_due_overlap_or_dedupe_gap")
    if worth in {"profitable_but_overlaps", "weak_positive_or_marginal", "repair_stress_before_counting", "thin_sample"}:
        reasons.append(f"worth_status:{worth}")
    if worth == "not_worth_current_shape":
        reasons.append("worth_status:not_worth_current_shape")
    if str(row.get("rolling_status") or "").lower() == "watch":
        reasons.append("rolling_status_watch")

    if row["decision"] == "candidate_count_target_met_research_only":
        blockers = [
            item
            for item in reasons
            if item.startswith(("quote_coverage_", "unpriced_rows_", "stress_pf_", "strict_new_rows_"))
            or item in {"quote_coverage_missing", "stress_pf_missing", "rolling_status_watch"}
        ]
        if blockers:
            row["decision"] = "raw_count_target_met_but_not_countable_edge"
        else:
            row["decision"] = "countable_momentum_edge_candidate_research_only"

    if row["decision"] == "countable_momentum_edge_candidate_research_only":
        row["next_step"] = "Freeze as a research candidate for Oracle review; this is still not forward proof or trading permission."
    elif row["raw_count_closes_target"]:
        row["next_step"] = "Do not count this as throughput until economics, overlap, coverage, and stress blockers clear."
    else:
        row["next_step"] = "Use as falsification evidence; a new causal playbook is needed to increase count without weakening proof."

    row["reason_codes"] = sorted(set(reasons))
    return row


def _candidate_rows_from_all_planned(
    all_planned: dict[str, Any],
    *,
    target_min_exact_rows: int,
    min_quote_coverage_pct: float,
    min_stress_pf: float,
) -> list[dict[str, Any]]:
    candidates = []
    for item in _as_list(all_planned.get("variants")):
        source = _as_dict(item)
        if not _matches_momentum(source):
            continue
        candidates.append(
            _classify_candidate(
                _variant_candidate(source),
                target_min_exact_rows=target_min_exact_rows,
                min_quote_coverage_pct=min_quote_coverage_pct,
                min_stress_pf=min_stress_pf,
            )
        )
    order = {
        "countable_momentum_edge_candidate_research_only": 0,
        "raw_count_target_met_but_not_countable_edge": 1,
        "blocked_below_trade_count_target": 2,
        "rejected_negative_or_flat_edge": 3,
        "blocked_no_current_candidates": 4,
    }
    return sorted(
        candidates,
        key=lambda row: (
            order.get(str(row.get("decision")), 99),
            -_safe_int(row.get("with_candidate_trade_count")),
            -_safe_int(row.get("exact_rows")),
            str(row.get("candidate_id")),
        ),
    )


def _best_positive(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    positives = [row for row in candidates if (_safe_float(row.get("profit_factor")) or 0.0) > 1.0]
    if not positives:
        return None
    return sorted(
        positives,
        key=lambda row: (
            _safe_int(row.get("strict_new_trade_count")),
            _safe_int(row.get("exact_rows")),
            _safe_float(row.get("profit_factor")) or 0.0,
        ),
        reverse=True,
    )[0]


def _overall_status(candidates: list[dict[str, Any]], source_artifacts: dict[str, dict[str, Any]]) -> str:
    if any(meta.get("required") and meta.get("status") != "loaded" for meta in source_artifacts.values()):
        return "blocked_missing_source_artifact"
    if any(row.get("decision") == "countable_momentum_edge_candidate_research_only" for row in candidates):
        return "momentum_edge_target_met_research_only"
    if any(row.get("raw_count_closes_target") for row in candidates):
        return "raw_count_available_but_not_countable_profitable_edge"
    return "blocked_no_countable_high_throughput_momentum_edge"


def build_report(
    *,
    all_planned_path: Path = DEFAULT_ALL_PLANNED,
    incubator_path: Path = DEFAULT_INCUBATOR,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    target_min_exact_rows: int = DEFAULT_TARGET_MIN_EXACT_ROWS,
    min_quote_coverage_pct: float = DEFAULT_MIN_QUOTE_COVERAGE_PCT,
    min_stress_pf: float = DEFAULT_MIN_STRESS_PF,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    all_planned, all_planned_meta = _load_json(all_planned_path, required=True)
    incubator, incubator_meta = _load_json(incubator_path, required=False)
    robust_edge, robust_meta = _load_json(robust_edge_path, required=False)
    source_artifacts = {
        "all_planned_sleeves": all_planned_meta,
        "current_regime_lane_incubator": incubator_meta,
        "robust_edge_discovery": robust_meta,
    }
    candidates = _candidate_rows_from_all_planned(
        all_planned,
        target_min_exact_rows=target_min_exact_rows,
        min_quote_coverage_pct=min_quote_coverage_pct,
        min_stress_pf=min_stress_pf,
    )
    counts = Counter(str(row.get("decision")) for row in candidates)
    raw_count_rows = [row for row in candidates if row.get("raw_count_closes_target")]
    countable_rows = [row for row in candidates if row.get("decision") == "countable_momentum_edge_candidate_research_only"]
    best_positive = _best_positive(candidates)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at,
        "status": _overall_status(candidates, source_artifacts),
        **READ_ONLY_FLAGS,
        "scope": "read_only_current_regime_momentum_edge_throughput_test",
        "concept_id": "regime_momentum_continuation_debit_spread",
        "is_trade_recommendation": False,
        "historical_rows_are_not_forward_proof": True,
        "target": {
            "target_min_exact_rows": int(target_min_exact_rows),
            "min_quote_coverage_pct": float(min_quote_coverage_pct),
            "min_stress_pf": float(min_stress_pf),
            "requires_strict_new_deduped_rows": True,
            "requires_positive_point_profit_factor": True,
            "does_not_accept_raw_overlapping_counts": True,
        },
        "source_artifacts": source_artifacts,
        "incubator_status": incubator.get("status"),
        "robust_edge_status": robust_edge.get("overall_status"),
        "all_planned_as_of_date": all_planned.get("as_of_date"),
        "base_clean_stack": _as_dict(all_planned.get("base_clean_stack")),
        "candidate_count": len(candidates),
        "decision_counts": dict(sorted(counts.items())),
        "raw_count_target_met_candidate_count": len(raw_count_rows),
        "countable_momentum_edge_candidate_count": len(countable_rows),
        "best_positive_candidate_if_any": best_positive,
        "raw_count_target_met_candidates": raw_count_rows,
        "candidate_rankings": candidates,
        "conclusion": _conclusion(candidates, countable_rows, raw_count_rows, best_positive),
        "next_oracle_question": (
            "Given this read-only edge test, choose the next concrete repo task to increase countable profitable "
            "regular-options throughput. Prefer a new causal, point-in-time momentum-continuation playbook or a "
            "specific falsification path; do not recommend raw overlapping aggregation, proof-bar reductions, quote "
            "imports, live validation, broker actions, scanner-policy release, protected-holdout use, or promotion."
        ),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    _validate_report(report)
    return report


def _conclusion(
    candidates: list[dict[str, Any]],
    countable_rows: list[dict[str, Any]],
    raw_count_rows: list[dict[str, Any]],
    best_positive: dict[str, Any] | None,
) -> dict[str, Any]:
    if countable_rows:
        best = countable_rows[0]
        return {
            "accepted_profitability": False,
            "summary": "A historical research candidate clears the local throughput screen, but it is not forward proof or trading permission.",
            "best_candidate_id": best.get("candidate_id"),
            "next_step": "Send the candidate to Oracle for frozen-forward paper-validation design.",
        }
    if raw_count_rows:
        return {
            "accepted_profitability": False,
            "summary": (
                "More historical rows exist, but the high-count current-regime/momentum-compatible candidates are "
                "negative, execution-fragile, stress-fragile, or overlap the existing clean stack."
            ),
            "best_candidate_id": best_positive.get("candidate_id") if best_positive else None,
            "next_step": "Ask Oracle for the next read-only causal playbook; do not aggregate raw overlapping counts as edge.",
        }
    return {
        "accepted_profitability": False,
        "summary": "No current momentum-compatible all-planned candidate reaches the count target under the local proof screen.",
        "best_candidate_id": best_positive.get("candidate_id") if best_positive else None,
        "next_step": "Implement or falsify a new preregistered read-only playbook rather than rerunning exhausted variants.",
    }


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("edge test cannot accept profitability")
    if report.get("promotion_ready") is not False:
        raise ValueError("edge test cannot promote")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    target = _as_dict(report.get("target"))
    base = _as_dict(report.get("base_clean_stack"))
    conclusion = _as_dict(report.get("conclusion"))
    lines = [
        "# Regular Options Current-Regime Momentum Edge Test",
        "",
        "This report is generated from `scripts/build_regular_options_current_regime_momentum_edge.py`. It is a read-only edge/throughput test over existing current-regime and momentum-compatible replay artifacts. It does not create trades, run live validation, import quotes, mutate evidence stores, change scanner policy, consume protected holdout, or promote a lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Target exact rows: `{target.get('target_min_exact_rows')}`.",
        f"- Base clean stack exact rows: `{base.get('strict_deduped_trade_count')}`.",
        f"- Raw count target met candidates: `{report.get('raw_count_target_met_candidate_count')}`.",
        f"- Countable momentum edge candidates: `{report.get('countable_momentum_edge_candidate_count')}`.",
        f"- Decision counts: `{json.dumps(report.get('decision_counts'), sort_keys=True)}`.",
        f"- Conclusion: {conclusion.get('summary')}",
        "",
        "## Candidate Rankings",
        "",
        "| Candidate | Decision | Exact | Strict New | With Candidate | PF | Stress PF | Coverage | Worth | Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in _as_list(report.get("candidate_rankings")):
        row = _as_dict(row)
        reasons = ", ".join(str(item) for item in _as_list(row.get("reason_codes")))[:260]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('candidate_id')}`",
                    f"`{row.get('decision')}`",
                    str(row.get("exact_rows")),
                    str(row.get("strict_new_trade_count")),
                    str(row.get("with_candidate_trade_count")),
                    str(row.get("profit_factor")),
                    str(row.get("stress_5pct_per_side_profit_factor")),
                    str(row.get("quote_coverage_pct")),
                    f"`{row.get('worth_status')}`",
                    reasons,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Historical rows are not forward proof: `{_fmt_bool(report['historical_rows_are_not_forward_proof'])}`.",
            "- Raw overlapping combined counts are not accepted as throughput unless the strict-new de-duplicated rows clear the gap.",
            "- Positive point PF is not enough without quote coverage, stress, and strict-new count gates.",
            "",
            "## Next Oracle Question",
            "",
            report["next_oracle_question"],
            "",
            "## Prohibited Actions",
            "",
        ]
    )
    lines.extend(f"- `{action}`" for action in report["prohibited_actions"])
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
    markdown = render_markdown(report)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only current-regime momentum edge throughput test.")
    parser.add_argument("--all-planned", type=Path, default=DEFAULT_ALL_PLANNED)
    parser.add_argument("--incubator", type=Path, default=DEFAULT_INCUBATOR)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--target-min-exact-rows", type=int, default=DEFAULT_TARGET_MIN_EXACT_ROWS)
    parser.add_argument("--min-quote-coverage-pct", type=float, default=DEFAULT_MIN_QUOTE_COVERAGE_PCT)
    parser.add_argument("--min-stress-pf", type=float, default=DEFAULT_MIN_STRESS_PF)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        all_planned_path=args.all_planned,
        incubator_path=args.incubator,
        robust_edge_path=args.robust_edge,
        target_min_exact_rows=args.target_min_exact_rows,
        min_quote_coverage_pct=args.min_quote_coverage_pct,
        min_stress_pf=args.min_stress_pf,
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
