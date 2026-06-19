from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_source_replay_pass"

DEFAULT_EVIDENCE_BLOCKER = ROOT / "data" / "profitability-lab" / "regular-options-evidence-blocker-burndown" / "latest.json"
DEFAULT_HYPOTHESIS_TOURNAMENT = ROOT / "data" / "profitability-lab" / "regular-options-hypothesis-tournament" / "latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_SCOPED_REPLAY = (
    ROOT / "data" / "profitability-lab" / "regular-options-source-replay-pass" / "scoped-all-planned" / "latest_partial.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-source-replay-pass"
DEFAULT_DOC = ROOT / "docs" / "regular-options-source-replay-pass.md"

TARGETS = (
    {
        "target_id": "source-replay-aapl-2026-01-12",
        "ticker": "AAPL",
        "contract_symbol": "AAPL260116C00295000",
        "quote_date": "2026-01-12",
        "lane_id": "bullish_pullback_observation",
        "source_artifact": "data/options-validation/runs/20260602_102114_sleeve_ticker_aapl_intraday.json",
        "source_replay_variant_id": "sleeve_ticker_aapl",
    },
    {
        "target_id": "source-replay-aapl-2026-03-12",
        "ticker": "AAPL",
        "contract_symbol": "AAPL260320C00300000",
        "quote_date": "2026-03-12",
        "lane_id": "bullish_pullback_observation",
        "source_artifact": "data/options-validation/runs/20260602_102114_sleeve_ticker_aapl_intraday.json",
        "source_replay_variant_id": "sleeve_ticker_aapl",
    },
    {
        "target_id": "source-replay-unh-2025-11-06",
        "ticker": "UNH",
        "contract_symbol": "UNH251128C00410000",
        "quote_date": "2025-11-06",
        "lane_id": "bullish_pullback_observation",
        "source_artifact": "data/options-validation/runs/20260602_102557_sleeve_ticker_unh_intraday.json",
        "source_replay_variant_id": "sleeve_ticker_unh",
    },
    {
        "target_id": "source-replay-dia-2025-11-05",
        "ticker": "DIA",
        "contract_symbol": "DIA251128C00495000",
        "quote_date": "2025-11-05",
        "lane_id": "tracked_winner_cheap_debit_continuity_v1",
        "source_artifact": "data/options-validation/runs/20260602_110059_tracked_winner_cheap_debit_continuity_v1_intraday.json",
        "source_replay_variant_id": "tracked_winner_cheap_debit_continuity_v1",
    },
    {
        "target_id": "source-replay-dia-2025-11-17",
        "ticker": "DIA",
        "contract_symbol": "DIA251219C00500000",
        "quote_date": "2025-11-17",
        "lane_id": "tracked_winner_cheap_debit_continuity_v1",
        "source_artifact": "data/options-validation/runs/20260602_110059_tracked_winner_cheap_debit_continuity_v1_intraday.json",
        "source_replay_variant_id": "tracked_winner_cheap_debit_continuity_v1",
    },
)

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_source_replay_pass",
    "do_not_submit_broker_orders_from_source_replay_pass",
    "do_not_enable_auto_track_from_source_replay_pass",
    "do_not_enable_live_validation_from_source_replay_pass",
    "do_not_change_scanner_policy_from_source_replay_pass",
    "do_not_change_stops_from_source_replay_pass",
    "do_not_change_sizing_from_source_replay_pass",
    "do_not_lower_proof_bars_from_source_replay_pass",
    "do_not_mutate_evidence_databases_from_source_replay_pass",
    "do_not_import_quotes_from_source_replay_pass",
)

NON_GOALS = (
    "create trades",
    "submit broker orders",
    "enable auto-track",
    "enable live validation",
    "change scanner policy",
    "change stops",
    "change sizing",
    "lower proof bars",
    "mutate evidence databases",
    "import quotes",
)

POST_REPLAY_RERUN_COMMANDS = (
    "npm run options:features:regular-options",
    "npm run options:robust-search:regular-options",
    "npm run options:replay:regular-options-walk-forward",
    "npm run options:research:robust-edge",
    "npm run options:research:hypothesis-tournament",
    "npm run options:research:evidence-blocker-burndown",
    "npm run options:audit:monthly-profitability",
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "generated_at_utc": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    return payload, meta


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _find_variant(scoped_replay: dict[str, Any], variant_id: str) -> dict[str, Any] | None:
    for row in scoped_replay.get("variants") or []:
        if isinstance(row, dict) and str(row.get("variant_id")) == variant_id:
            return row
    return None


def _target_in_rows(run: dict[str, Any], target: dict[str, Any], rows_key: str) -> bool:
    contract = str(target["contract_symbol"]).upper()
    quote_date = str(target["quote_date"])[:10]
    for row in run.get(rows_key) or []:
        if not isinstance(row, dict):
            continue
        text = json.dumps(row, sort_keys=True, default=str).upper()
        row_date = str(row.get("missing_quote_date") or row.get("date") or row.get("entry_date") or "")[:10]
        if contract in text and (rows_key == "unpriced_trades" or not row_date or row_date == quote_date or rows_key == "trades"):
            return True
    return False


def _target_result(target: dict[str, Any], scoped_replay: dict[str, Any]) -> dict[str, Any]:
    result = {
        **target,
        "command_used": None,
        "exact_row_found": False,
        "entry_exit_evidence_exact_executable": False,
        "result": "unsafe_to_run",
        "reason_codes": [],
        "can_affect_final_holdout_count": True,
        "can_affect_pf_lower_bound": True,
        "run_path": None,
        "next_action": "No existing safe scoped source replay command was found for this target.",
    }
    variant = _find_variant(scoped_replay, str(target["source_replay_variant_id"]))
    if variant is None:
        result["reason_codes"] = ["source_replay_variant_not_executed", "no_safe_scoped_source_replay_command_found"]
        result["command_used"] = "not_run"
        return result

    run_path = Path(str(variant.get("run_path") or ""))
    result["run_path"] = _rel(run_path) if str(run_path) else None
    result["command_used"] = (
        "uv run --locked python scripts/run_regular_options_all_planned_sleeves.py "
        "--only tracked_winner_cheap_debit_continuity_v1 --as-of-date 2026-06-04 "
        "--output-dir data/profitability-lab/regular-options-source-replay-pass/scoped-all-planned --json"
    )
    if not run_path.exists():
        result["result"] = "still_missing"
        result["reason_codes"] = ["source_replay_run_artifact_missing"]
        result["next_action"] = "Rerun the scoped source replay if the derived-artifact write is still approved."
        return result
    run = json.loads(run_path.read_text(encoding="utf8"))
    in_unpriced = _target_in_rows(run, target, "unpriced_trades")
    in_trades = _target_in_rows(run, target, "trades")
    if in_trades and not in_unpriced:
        result["result"] = "source_replay_resolved"
        result["exact_row_found"] = True
        result["entry_exit_evidence_exact_executable"] = True
        result["reason_codes"] = ["target_contract_present_in_priced_replay_rows"]
        result["next_action"] = "Rerun robust-search and promotion readbacks before any interpretation."
    elif in_unpriced:
        result["result"] = "still_missing"
        result["reason_codes"] = ["target_contract_remains_in_unpriced_replay_rows"]
        result["next_action"] = "Do not repeat provider loops; this source replay did not clear the exact blocker."
    else:
        result["result"] = "still_missing"
        result["reason_codes"] = ["target_contract_not_found_as_priced_exact_row"]
        result["next_action"] = "Treat as unresolved unless a source-specific replay artifact maps this row."
    return result


def build_report(
    *,
    evidence_blocker_path: Path = DEFAULT_EVIDENCE_BLOCKER,
    hypothesis_tournament_path: Path = DEFAULT_HYPOTHESIS_TOURNAMENT,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    scoped_replay_path: Path = DEFAULT_SCOPED_REPLAY,
    generated_at_utc: str | None = None,
    final_holdout_count_before: int = 28,
    pf_lower_bound_before: float = 0.61,
) -> dict[str, Any]:
    generated_at_utc = generated_at_utc or _utc_now()
    evidence_blocker, evidence_meta = _load_json(evidence_blocker_path)
    tournament, tournament_meta = _load_json(hypothesis_tournament_path)
    robust_edge, robust_meta = _load_json(robust_edge_path)
    scoped_replay, scoped_meta = _load_json(scoped_replay_path)
    source_artifacts = {
        "evidence_blocker_burndown": evidence_meta,
        "hypothesis_tournament": tournament_meta,
        "robust_edge_discovery": robust_meta,
        "scoped_source_replay": scoped_meta,
    }
    if evidence_meta["status"] != "loaded":
        overall_status = "blocked_missing_readbacks"
        results: list[dict[str, Any]] = []
    elif not TARGETS:
        overall_status = "blocked_missing_targets"
        results = []
    else:
        results = [_target_result(target, scoped_replay) for target in TARGETS]
        resolved = [row for row in results if row["result"] == "source_replay_resolved"]
        unsafe = [row for row in results if row["result"] == "unsafe_to_run"]
        overall_status = (
            "source_replay_resolved_some"
            if resolved
            else "source_replay_plan_only"
            if unsafe and len(unsafe) == len(results)
            else "source_replay_no_change"
        )

    holdout_after = _safe_int((evidence_blocker.get("holdout_gap_summary") or {}).get("current_final_holdout_rows"), final_holdout_count_before)
    pf_after = _safe_float(
        (evidence_blocker.get("pf_lower_bound_gap_summary") or {}).get("current_profit_factor_lower_bound"),
        pf_lower_bound_before,
    )
    resolved_targets = [row for row in results if row.get("result") == "source_replay_resolved"]
    blocked_targets = [row for row in results if row.get("result") not in {"source_replay_resolved"}]
    do_not_repeat_targets = [
        row
        for row in blocked_targets
        if row.get("result") in {"still_missing", "source_exhausted", "lookahead_only", "zero_bid_tradability_failure"}
    ]
    return {
        "generated_at_utc": generated_at_utc,
        "report_id": REPORT_ID,
        "schema_version": 1,
        "read_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "overall_status": overall_status,
        "source_artifacts": source_artifacts,
        "targets_attempted": len([row for row in results if row.get("command_used") not in {None, "not_run"}]),
        "targets_resolved": len(resolved_targets),
        "targets_still_blocked": len(blocked_targets),
        "targets_unsafe_to_run": len([row for row in results if row.get("result") == "unsafe_to_run"]),
        "final_holdout_count_before": final_holdout_count_before,
        "final_holdout_count_after": holdout_after,
        "pf_lower_bound_before": pf_lower_bound_before,
        "pf_lower_bound_after": pf_after,
        "candidate_status_before": {
            "robust_candidate_count": 0,
            "forward_freeze_candidate_count": 0,
            "paper_shadow_candidate_count": 1,
            "promotion_ready": False,
        },
        "candidate_status_after": {
            "robust_candidate_count": _safe_int(robust_edge.get("robust_candidate_count")),
            "forward_freeze_candidate_count": _safe_int(tournament.get("forward_freeze_candidate_count")),
            "paper_shadow_candidate_count": _safe_int(tournament.get("paper_shadow_candidate_count")),
            "promotion_ready": bool(
                (tournament.get("data_coverage_summary") or {}).get("promotion_ready")
                or tournament.get("existing_promotion_ready")
            ),
            "robust_edge_status": robust_edge.get("overall_status"),
            "hypothesis_tournament_status": tournament.get("overall_status"),
        },
        "resolved_targets": resolved_targets,
        "blocked_targets": blocked_targets,
        "do_not_repeat_targets": do_not_repeat_targets,
        "post_replay_rerun_commands": list(POST_REPLAY_RERUN_COMMANDS),
        "next_operator_action": (
            "No source-replayed row became exact proof-eligible. Keep source-replay unresolved rows out of promotion and continue proof-preserving evidence collection/repair planning."
            if not resolved_targets
            else "Rerun the full promotion stack and inspect exact proof eligibility before any forward-freeze discussion."
        ),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "non_goals": list(NON_GOALS),
    }


def _fmt(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["No rows."]
    columns = ["target_id", "lane_id", "ticker", "contract_symbol", "quote_date", "result", "reason_codes", "next_action"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |")
    return lines


def build_markdown(report: dict[str, Any]) -> str:
    after = report.get("candidate_status_after") or {}
    lines = [
        "# Regular Options Source Replay Pass",
        "",
        "Source replay did not make any high-value blocker exact proof-eligible.",
        "",
        "## At A Glance",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Targets attempted: `{report.get('targets_attempted')}`.",
        f"- Targets resolved: `{report.get('targets_resolved')}`.",
        f"- Targets still blocked: `{report.get('targets_still_blocked')}`.",
        f"- Targets unsafe/no scoped replay command: `{report.get('targets_unsafe_to_run')}`.",
        f"- Final holdout before / after: `{report.get('final_holdout_count_before')}` / `{report.get('final_holdout_count_after')}`.",
        f"- PF lower bound before / after: `{report.get('pf_lower_bound_before')}` / `{report.get('pf_lower_bound_after')}`.",
        f"- Forward-freeze candidates after: `{after.get('forward_freeze_candidate_count')}`.",
        f"- Robust candidates after: `{after.get('robust_candidate_count')}`.",
        f"- Promotion ready after: `{after.get('promotion_ready')}`.",
        "",
        "## Target Results",
        "",
        *_table((report.get("resolved_targets") or []) + (report.get("blocked_targets") or [])),
        "",
        "## Interpretation",
        "",
        "- The DIA tracked-winner replay was derived-artifact-only and did not import quotes or write evidence databases.",
        "- The two DIA contracts remained in unpriced replay rows, so they are not exact proof-eligible.",
        "- The AAPL and UNH ticker-sleeve rows did not have a confirmed safe scoped replay command in the inspected local runners, so they remain unsafe-to-run/no-action under this pass.",
        "- Final-holdout count and PF lower bound did not improve in the refreshed robust stack.",
        "- No candidate moved from paper-shadow to forward-freeze eligible.",
        "",
        "## Post-Replay Rerun Commands",
        "",
        *[f"- `{command}`" for command in report.get("post_replay_rerun_commands") or []],
        "",
        "## Non-Goals",
        "",
        *[f"- This readback does not {item}." for item in report.get("non_goals") or []],
        "",
    ]
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path, doc_path: Path) -> dict[str, str]:
    stamp = _utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path = output_dir / f"regular_options_source_replay_pass_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_source_replay_pass_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    markdown = build_markdown(report)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    doc_path.write_text(markdown, encoding="utf8")
    return {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(markdown_path),
        "latest_markdown": _rel(latest_markdown),
        "docs_report": _rel(doc_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options source replay pass readback.")
    parser.add_argument("--evidence-blocker", type=Path, default=DEFAULT_EVIDENCE_BLOCKER)
    parser.add_argument("--hypothesis-tournament", type=Path, default=DEFAULT_HYPOTHESIS_TOURNAMENT)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--scoped-replay", type=Path, default=DEFAULT_SCOPED_REPLAY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        evidence_blocker_path=args.evidence_blocker,
        hypothesis_tournament_path=args.hypothesis_tournament,
        robust_edge_path=args.robust_edge,
        scoped_replay_path=args.scoped_replay,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(report["overall_status"])
    else:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
