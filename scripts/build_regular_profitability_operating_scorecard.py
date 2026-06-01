from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-operating-scorecard"
DEFAULT_DOC = ROOT / "docs" / "regular-options-operating-scorecard.md"
DEFAULT_AUTORESEARCH = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "experiments" / "latest.json"
DEFAULT_GUARDRAILS = ROOT / "data" / "forward-tracking" / "trading_desk_profitability_guardrails_latest.json"
DEFAULT_NEGATIVE_AUDIT = ROOT / "data" / "forward-tracking" / "trading_desk_negative_trade_decision_audit_latest.json"
DEFAULT_EXIT_REPLAY = ROOT / "data" / "forward-tracking" / "trading_desk_exit_policy_replay_latest.json"
DEFAULT_LEGACY_MISSED_CLOSE = ROOT / "data" / "forward-tracking" / "trading_desk_legacy_missed_close_audit_latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path), "missing": True}
    payload = json.loads(path.read_text(encoding="utf8"))
    if isinstance(payload, dict):
        payload.setdefault("available", True)
        payload.setdefault("path", str(path))
        return payload
    return {"available": False, "path": str(path), "error": "json_root_not_object"}


def _delta(after: Any, before: Any) -> float | None:
    before_value = safe_float(before)
    after_value = safe_float(after)
    if before_value is None or after_value is None:
        return None
    return round(after_value - before_value, 4)


def _summarize_autoresearch(payload: dict[str, Any]) -> dict[str, Any]:
    best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
    metrics = best.get("autoresearch_metrics") if isinstance(best.get("autoresearch_metrics"), dict) else {}
    blockers = best.get("promotion_blockers") if isinstance(best.get("promotion_blockers"), list) else []
    score = safe_float(best.get("score"))
    clean_count = safe_float(metrics.get("promotable_clean_count"))
    lane_a_pf = safe_float(metrics.get("lane_a_conservative_profit_factor"))
    zero_bid_rate = safe_float(metrics.get("zero_bid_exit_rate_pct"))
    status = str(best.get("status") or "missing")
    return {
        "artifact_path": payload.get("path"),
        "experiment_batch": payload.get("experiment_batch"),
        "best_variant_id": best.get("variant_id"),
        "status": status,
        "score": score,
        "research_score": safe_float(best.get("research_score")),
        "clean_count": clean_count,
        "scout_count": safe_float(metrics.get("scout_count")),
        "effective_quote_coverage_pct": safe_float(metrics.get("effective_quote_coverage_pct")),
        "effective_unresolved_count": safe_float(metrics.get("effective_unresolved_count")),
        "zero_bid_exit_rate_pct": zero_bid_rate,
        "lane_a_conservative_profit_factor": lane_a_pf,
        "promotion_blockers": blockers,
        "visible_result": bool(
            status == "promotable_clean"
            or (lane_a_pf is not None and lane_a_pf >= 1.30 and clean_count is not None and clean_count >= 200)
        ),
        "still_blocked": bool(score is None or score <= 0 or blockers),
    }


def _summarize_guardrails(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
    combined = payload.get("combined_promoted_guardrails") if isinstance(payload.get("combined_promoted_guardrails"), dict) else {}
    kept = combined.get("kept") if isinstance(combined.get("kept"), dict) else {}
    blocked = combined.get("blocked") if isinstance(combined.get("blocked"), dict) else {}
    avg_delta = _delta(kept.get("avg_pnl_pct"), baseline.get("avg_pnl_pct"))
    median_delta = _delta(kept.get("median_pnl_pct"), baseline.get("median_pnl_pct"))
    negative_rate_delta = _delta(kept.get("negative_rate_priced_pct"), baseline.get("negative_rate_priced_pct"))
    promoted = payload.get("promoted_guardrails") if isinstance(payload.get("promoted_guardrails"), list) else []
    return {
        "artifact_path": payload.get("path"),
        "baseline": {
            "rows": baseline.get("rows"),
            "priced": baseline.get("priced"),
            "avg_pnl_pct": safe_float(baseline.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(baseline.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(baseline.get("negative_rate_priced_pct")),
        },
        "promoted_kept_subset": {
            "rows": kept.get("rows"),
            "priced": kept.get("priced"),
            "avg_pnl_pct": safe_float(kept.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(kept.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(kept.get("negative_rate_priced_pct")),
        },
        "promoted_blocked_subset": {
            "rows": blocked.get("rows"),
            "priced": blocked.get("priced"),
            "avg_pnl_pct": safe_float(blocked.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(blocked.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(blocked.get("negative_rate_priced_pct")),
        },
        "deltas_vs_baseline": {
            "avg_pnl_pct": avg_delta,
            "median_pnl_pct": median_delta,
            "negative_rate_priced_pct": negative_rate_delta,
        },
        "promoted_guardrails": promoted,
        "visible_result": bool(
            avg_delta is not None
            and avg_delta > 0
            and median_delta is not None
            and median_delta > 0
            and negative_rate_delta is not None
            and negative_rate_delta < 0
        ),
    }


def _summarize_negative_audit(payload: dict[str, Any]) -> dict[str, Any]:
    targets = payload.get("legacy_missed_close_targets")
    if not isinstance(targets, list):
        targets = []
    negative_trades = payload.get("negative_trades")
    if not isinstance(negative_trades, list):
        negative_trades = []
    categories: dict[str, int] = {}
    for row in negative_trades:
        if not isinstance(row, dict):
            continue
        category = str(row.get("failure_category") or "unknown")
        categories[category] = categories.get(category, 0) + 1
    return {
        "artifact_path": payload.get("path"),
        "negative_trade_count": len(negative_trades),
        "legacy_missed_close_target_count": len(targets),
        "failure_category_counts": categories,
        "legacy_targets": [
            {
                "trade_id": row.get("trade_id"),
                "ticker": row.get("ticker"),
                "final_pnl_pct": safe_float(row.get("final_pnl_pct")),
                "first_negative_time": row.get("first_negative_time"),
                "best_executable_before_negative": row.get("best_executable_before_negative"),
                "positive_executable_sell_before_final_loss": row.get("positive_executable_sell_before_final_loss"),
                "failure_category": row.get("failure_category"),
            }
            for row in targets
            if isinstance(row, dict)
        ],
        "visible_result": bool(targets),
    }


def _summarize_exit_replay(payload: dict[str, Any]) -> dict[str, Any]:
    policies = payload.get("policies") if isinstance(payload.get("policies"), list) else []
    best = policies[0] if policies and isinstance(policies[0], dict) else {}
    promote = [
        policy
        for policy in policies
        if isinstance(policy, dict)
        and (policy.get("recommendation") or {}).get("status") == "promote_candidate"
    ]
    legacy_rows = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        for row in policy.get("legacy_targets") or []:
            if isinstance(row, dict):
                legacy_rows.append(
                    {
                        "policy_id": policy.get("policy_id"),
                        "trade_id": row.get("trade_id"),
                        "ticker": row.get("ticker"),
                        "baseline_pnl_pct": safe_float(row.get("baseline_pnl_pct")),
                        "policy_pnl_pct": safe_float(row.get("policy_pnl_pct")),
                        "delta_vs_baseline_pct": safe_float(row.get("delta_vs_baseline_pct")),
                        "reason": row.get("reason"),
                        "reviewed_at": row.get("reviewed_at"),
                    }
                )
    return {
        "artifact_path": payload.get("path"),
        "baseline": payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {},
        "best_policy_id": best.get("policy_id"),
        "best_policy_recommendation": (best.get("recommendation") or {}).get("status") if isinstance(best, dict) else None,
        "promote_candidate_count": len(promote),
        "legacy_target_replay_rows": legacy_rows,
        "legacy_target_positive_delta_count": sum(
            1 for row in legacy_rows if (safe_float(row.get("delta_vs_baseline_pct")) or 0.0) > 0
        ),
        "visible_result": bool(legacy_rows),
        "broad_exit_rule_ready": bool(promote),
    }


def _summarize_legacy_missed_close(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    return {
        "artifact_path": payload.get("path"),
        "available": not bool(payload.get("missing")),
        "recommendation": summary.get("recommendation"),
        "diagnosis_counts": summary.get("diagnosis_counts") or {},
        "current_action_required_count": int(summary.get("current_action_required_count") or 0),
        "historical_stale_path_count": int(summary.get("historical_stale_path_count") or 0),
        "target_count": int(summary.get("target_count") or len(rows) or 0),
    }


def _next_actions(
    *,
    autoresearch: dict[str, Any],
    guardrails: dict[str, Any],
    negative_audit: dict[str, Any],
    exit_replay: dict[str, Any],
    legacy_missed_close: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if legacy_missed_close.get("current_action_required_count"):
        actions.append(
            "Fix current auto-close handling for still-open rows with executable SELL evidence."
        )
    elif negative_audit.get("legacy_missed_close_target_count") and not legacy_missed_close.get("available"):
        actions.append(
            "Run the legacy rows 26/39/44 missed-close audit before changing broad exit policy."
        )
    elif legacy_missed_close.get("historical_stale_path_count"):
        actions.append(
            "Treat legacy rows 26/39/44 as historical stale-policy diagnostics, not a broad current exit-policy change."
        )
    if guardrails.get("visible_result"):
        actions.append(
            "Keep promoted Trading Desk entry guardrails active and monitor starvation before loosening."
        )
    if autoresearch.get("still_blocked"):
        actions.append(
            "Do not tune Lane A entry/memory again; test a non-overlapping sleeve or materially different exit/liquidity rule."
        )
    if not exit_replay.get("broad_exit_rule_ready"):
        actions.append(
            "Do not promote a broad exit-policy replay; current candidates improve some rows but fail broader negative-rate/winner-loss checks."
        )
    return actions


def build_scorecard(
    *,
    autoresearch_path: Path = DEFAULT_AUTORESEARCH,
    guardrails_path: Path = DEFAULT_GUARDRAILS,
    negative_audit_path: Path = DEFAULT_NEGATIVE_AUDIT,
    exit_replay_path: Path = DEFAULT_EXIT_REPLAY,
    legacy_missed_close_path: Path = DEFAULT_LEGACY_MISSED_CLOSE,
) -> dict[str, Any]:
    autoresearch = _summarize_autoresearch(_load_json(autoresearch_path))
    guardrails = _summarize_guardrails(_load_json(guardrails_path))
    negative_audit = _summarize_negative_audit(_load_json(negative_audit_path))
    exit_replay = _summarize_exit_replay(_load_json(exit_replay_path))
    legacy_missed_close = _summarize_legacy_missed_close(_load_json(legacy_missed_close_path))
    product_progress = bool(guardrails.get("visible_result") or negative_audit.get("visible_result"))
    proof_progress = bool(autoresearch.get("visible_result"))
    status = (
        "proof_grade_profitability_ready"
        if proof_progress
        else "visible_product_profitability_progress_but_proof_still_blocked"
        if product_progress
        else "no_material_profitability_progress_visible"
    )
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_options_profitability_operating_scorecard",
        "status": status,
        "product_profitability_progress_visible": product_progress,
        "proof_grade_profitability_progress_visible": proof_progress,
        "autoresearch": autoresearch,
        "trading_desk_guardrails": guardrails,
        "negative_decision_audit": negative_audit,
        "exit_policy_replay": exit_replay,
        "legacy_missed_close_audit": legacy_missed_close,
        "next_actions": _next_actions(
            autoresearch=autoresearch,
            guardrails=guardrails,
            negative_audit=negative_audit,
            exit_replay=exit_replay,
            legacy_missed_close=legacy_missed_close,
        ),
    }


def markdown_report(scorecard: dict[str, Any]) -> str:
    guard = scorecard["trading_desk_guardrails"]
    auto = scorecard["autoresearch"]
    negative = scorecard["negative_decision_audit"]
    exit_replay = scorecard["exit_policy_replay"]
    legacy = scorecard["legacy_missed_close_audit"]
    lines = [
        "# Regular Options Operating Scorecard",
        "",
        f"- Status: `{scorecard['status']}`",
        f"- Product profitability progress visible: `{scorecard['product_profitability_progress_visible']}`",
        f"- Proof-grade profitability progress visible: `{scorecard['proof_grade_profitability_progress_visible']}`",
        "",
        "## Trading Desk Guardrails",
        "",
        (
            f"- Baseline avg/median/negative-rate: `{guard['baseline']['avg_pnl_pct']}%` / "
            f"`{guard['baseline']['median_pnl_pct']}%` / `{guard['baseline']['negative_rate_priced_pct']}%`"
        ),
        (
            f"- Promoted kept avg/median/negative-rate: `{guard['promoted_kept_subset']['avg_pnl_pct']}%` / "
            f"`{guard['promoted_kept_subset']['median_pnl_pct']}%` / "
            f"`{guard['promoted_kept_subset']['negative_rate_priced_pct']}%`"
        ),
        f"- Deltas: `{guard['deltas_vs_baseline']}`",
        "",
        "## Frozen Proof Judge",
        "",
        f"- Best variant: `{auto.get('best_variant_id')}`",
        f"- Score/status: `{auto.get('score')}` / `{auto.get('status')}`",
        f"- Clean/scout count: `{auto.get('clean_count')}` / `{auto.get('scout_count')}`",
        f"- Lane A conservative PF / zero-bid rate: `{auto.get('lane_a_conservative_profit_factor')}` / `{auto.get('zero_bid_exit_rate_pct')}%`",
        f"- Blockers: `{auto.get('promotion_blockers')}`",
        "",
        "## Closed-Trade Follow-Up",
        "",
        f"- Negative trade rows audited: `{negative.get('negative_trade_count')}`",
        f"- Legacy missed-close targets: `{negative.get('legacy_missed_close_target_count')}`",
        f"- Legacy missed-close recommendation: `{legacy.get('recommendation')}`",
        f"- Legacy current action required: `{legacy.get('current_action_required_count')}`",
        f"- Broad exit promote candidates: `{exit_replay.get('promote_candidate_count')}`",
        f"- Legacy target positive replay rows: `{exit_replay.get('legacy_target_positive_delta_count')}`",
        "",
        "## Next Actions",
        "",
    ]
    for action in scorecard.get("next_actions") or []:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def write_outputs(scorecard: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_options_operating_scorecard_{stamp}.json"
    latest_json = output_dir / "latest.json"
    payload = json.dumps(scorecard, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    doc_path.write_text(markdown_report(scorecard), encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json), "markdown": str(doc_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular supervised options profitability operating scorecard.")
    parser.add_argument("--autoresearch", type=Path, default=DEFAULT_AUTORESEARCH)
    parser.add_argument("--guardrails", type=Path, default=DEFAULT_GUARDRAILS)
    parser.add_argument("--negative-audit", type=Path, default=DEFAULT_NEGATIVE_AUDIT)
    parser.add_argument("--exit-replay", type=Path, default=DEFAULT_EXIT_REPLAY)
    parser.add_argument("--legacy-missed-close", type=Path, default=DEFAULT_LEGACY_MISSED_CLOSE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    scorecard = build_scorecard(
        autoresearch_path=args.autoresearch,
        guardrails_path=args.guardrails,
        negative_audit_path=args.negative_audit,
        exit_replay_path=args.exit_replay,
        legacy_missed_close_path=args.legacy_missed_close,
    )
    payload: dict[str, Any] = {"scorecard": scorecard}
    if not args.no_write:
        payload["artifacts"] = write_outputs(scorecard, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": scorecard["status"], "next_actions": scorecard["next_actions"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
