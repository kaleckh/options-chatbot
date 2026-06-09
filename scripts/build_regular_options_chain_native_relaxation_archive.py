from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_chain_native_relaxation_archive"

DEFAULT_CHAIN_NATIVE_EXIT_OUTCOME_REPLAY = (
    ROOT / "data" / "forward-tracking" / "regular_options_chain_native_exit_outcome_replay_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-chain-native-relaxation-archive.md"

PROHIBITED_ACTIONS = (
    "do_not_delete_chain_native_scenarios_from_archive",
    "do_not_change_scanner_policy_from_chain_native_archive",
    "do_not_change_contract_selection_policy_from_chain_native_archive",
    "do_not_change_lane_promotion_from_chain_native_archive",
    "do_not_submit_broker_order_from_chain_native_archive",
    "do_not_mutate_database_from_chain_native_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_chain_native_archive",
    "do_not_promote_negative_chain_native_replay_to_paper_or_live_proof",
)

ARCHIVABLE_RELAXATION_KINDS = {"current", "relaxed"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return str(value or "").strip()


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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _source_ready_for_archive(exit_replay: dict[str, Any]) -> bool:
    summary = _as_dict(exit_replay.get("summary"))
    return (
        exit_replay.get("status") == "chain_native_exit_outcome_replay_readback"
        and summary.get("overall_status") == "chain_native_exit_outcome_replay_exact_pnl_available_diagnostic_only"
        and _safe_int(summary.get("missing_exit_quote_demand_count")) == 0
    )


def _branch_rows(exit_replay: dict[str, Any], scenario_id: str) -> list[dict[str, Any]]:
    return [
        _as_dict(row)
        for row in _as_list(exit_replay.get("outcome_rows"))
        if _norm(_as_dict(row).get("scenario_id")) == scenario_id
    ]


def _unique(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({_norm(row.get(key)) for row in rows if _norm(row.get(key))})


def _branch_id(metric: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    scenario_id = _norm(metric.get("scenario_id"))
    lanes = ",".join(_unique(rows, "lane")) or "unknown_lane"
    dates = ",".join(_unique(rows, "scan_date")) or "unknown_date"
    return f"{scenario_id}|{lanes}|{dates}"


def _archive_reason(metric: dict[str, Any]) -> str:
    avg = _safe_float(metric.get("avg_net_pnl_pct"))
    pf = _safe_float(metric.get("profit_factor"))
    if avg is not None and avg < 0 and pf is not None and pf < 1:
        return "negative_exact_exit_pnl_and_profit_factor_below_one"
    if avg is not None and avg < 0:
        return "negative_exact_exit_pnl"
    if pf is not None and pf < 1:
        return "profit_factor_below_one"
    return "archive_requested_by_exit_outcome_replay"


def _should_archive(metric: dict[str, Any]) -> bool:
    if _norm(metric.get("relaxation_kind")) not in ARCHIVABLE_RELAXATION_KINDS:
        return False
    if _safe_int(metric.get("priced")) <= 0 or _safe_int(metric.get("unpriced")) > 0:
        return False
    avg = _safe_float(metric.get("avg_net_pnl_pct"))
    pf = _safe_float(metric.get("profit_factor"))
    sum_usd = _safe_float(metric.get("sum_net_pnl_usd"))
    return bool(
        (avg is not None and avg < 0)
        or (pf is not None and pf < 1)
        or (sum_usd is not None and sum_usd < 0)
    )


def _archive_status(metric: dict[str, Any]) -> str:
    if _norm(metric.get("relaxation_kind")) == "current":
        return "archived_negative_chain_native_current_branch"
    return "archived_negative_chain_native_relaxation_branch"


def _archived_branches(exit_replay: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    archived: list[dict[str, Any]] = []
    non_archived: list[dict[str, Any]] = []
    for raw_metric in _as_list(exit_replay.get("scenario_metrics")):
        metric = _as_dict(raw_metric)
        if _norm(metric.get("relaxation_kind")) not in ARCHIVABLE_RELAXATION_KINDS:
            continue
        scenario_id = _norm(metric.get("scenario_id"))
        rows = _branch_rows(exit_replay, scenario_id)
        item = {
            "branch_id": _branch_id(metric, rows),
            "scenario_id": scenario_id,
            "relaxation_kind": metric.get("relaxation_kind"),
            "rows": metric.get("rows"),
            "priced": metric.get("priced"),
            "unpriced": metric.get("unpriced"),
            "profit_factor": metric.get("profit_factor"),
            "avg_net_pnl_pct": metric.get("avg_net_pnl_pct"),
            "median_net_pnl_pct": metric.get("median_net_pnl_pct"),
            "sum_net_pnl_usd": metric.get("sum_net_pnl_usd"),
            "win_rate_pct": metric.get("win_rate_pct"),
            "winner_count": metric.get("winner_count"),
            "loser_count": metric.get("loser_count"),
            "target_lanes": _unique(rows, "lane"),
            "target_dates": _unique(rows, "scan_date"),
            "target_tickers": _unique(rows, "ticker"),
            "promotion_ready": False,
        }
        if _should_archive(metric):
            archived.append(
                {
                    **item,
                    "archive_status": _archive_status(metric),
                    "archive_reason": _archive_reason(metric),
                }
            )
        else:
            non_archived.append({**item, "reason": "not_negative_exact_chain_native_branch"})
    archived.sort(key=lambda item: (_safe_float(item.get("avg_net_pnl_pct")) or 0.0, _norm(item.get("scenario_id"))))
    non_archived.sort(key=lambda item: _norm(item.get("scenario_id")))
    return archived, non_archived


def build_report(
    *,
    chain_native_exit_outcome_replay_path: Path = DEFAULT_CHAIN_NATIVE_EXIT_OUTCOME_REPLAY,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    exit_replay, input_meta = _load_json(chain_native_exit_outcome_replay_path)
    missing_required = []
    if input_meta.get("status") != "loaded":
        missing_required.append("chain_native_exit_outcome_replay")
    live_policy_change = _has_live_policy_change(exit_replay)
    source_ready = False if missing_required else _source_ready_for_archive(exit_replay)
    archived, non_archived = _archived_branches(exit_replay) if source_ready else ([], [])
    archived_relaxed = [item for item in archived if _norm(item.get("relaxation_kind")) == "relaxed"]
    archived_current = [item for item in archived if _norm(item.get("relaxation_kind")) == "current"]
    non_archived_relaxed = [item for item in non_archived if _norm(item.get("relaxation_kind")) == "relaxed"]
    non_archived_current = [item for item in non_archived if _norm(item.get("relaxation_kind")) == "current"]
    archived_ids = {str(item.get("branch_id")) for item in archived}
    negative_ids = set(archived_ids)
    unarchived = sorted(negative_ids - archived_ids)
    source_queue = [
        _as_dict(item)
        for item in _as_list(exit_replay.get("next_evidence_queue"))
        if _norm(_as_dict(item).get("action")) == "archive_negative_chain_native_relaxation_branch"
    ]

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "chain_native_relaxation_archive_readback"
        overall_status = (
            "negative_chain_native_branches_archived"
            if archived
            else "no_negative_chain_native_branches_to_archive"
        )

    summary = _as_dict(exit_replay.get("summary"))
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_chain_native_relaxation_branch_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "source_exit_outcome_status": summary.get("overall_status"),
            "source_ready_for_archive": source_ready,
            "missing_required_inputs": missing_required,
            "branch_scenario_count": len(archived) + len(non_archived),
            "negative_branch_count": len(archived),
            "archived_negative_branch_count": len(archived_ids),
            "unarchived_negative_branch_count": len(unarchived),
            "current_scenario_count": len(archived_current) + len(non_archived_current),
            "negative_current_scenario_count": len(archived_current),
            "archived_negative_current_scenario_count": len(archived_current),
            "unarchived_negative_current_scenario_count": 0,
            "relaxed_scenario_count": len(archived_relaxed) + len(non_archived_relaxed),
            "negative_relaxed_scenario_count": len(archived_relaxed),
            "archived_negative_relaxed_scenario_count": len(archived_relaxed),
            "unarchived_negative_relaxed_scenario_count": 0,
            "unarchived_branch_ids": unarchived,
            "archive_complete": bool(archived) and not unarchived,
            "archive_requested_by_exit_outcome_replay": bool(source_queue),
            "best_relaxed_scenario": summary.get("best_relaxed_scenario"),
            "live_policy_change": live_policy_change,
        },
        "inputs": {"chain_native_exit_outcome_replay": input_meta},
        "archived_branches": archived,
        "non_archived_branches": non_archived,
        "source_next_evidence_queue": source_queue,
        "proof_policy": {
            "readback_is": "read-only archive of exact-priced negative chain-native current and relaxation branches",
            "readback_is_not": "scenario deletion, scanner policy change, contract-selection change, lane promotion, broker action, DB mutation, or proof-bar reduction",
            "trusted_proof_standard": "trusted intraday exact-contract OPRA/NBBO exit evidence remains required before archiving profitability claims",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
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
        "# Regular Options Chain-Native Relaxation Archive",
        "",
        "This report is generated from `scripts/build_regular_options_chain_native_relaxation_archive.py`. It is a read-only archive for chain-native relaxation branches that exact exit replay already disproved.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Source exit-outcome status: `{summary.get('source_exit_outcome_status')}`.",
        f"- Archived negative chain-native branches: `{summary.get('archived_negative_branch_count')}` / `{summary.get('negative_branch_count')}`.",
        f"- Archived negative current scenarios: `{summary.get('archived_negative_current_scenario_count')}` / `{summary.get('negative_current_scenario_count')}`.",
        f"- Archived negative relaxed scenarios: `{summary.get('archived_negative_relaxed_scenario_count')}` / `{summary.get('negative_relaxed_scenario_count')}`.",
        f"- Unarchived negative branches: `{_json_inline(summary.get('unarchived_branch_ids') or [])}`.",
        f"- Archive requested by exit-outcome replay: `{str(bool(summary.get('archive_requested_by_exit_outcome_replay'))).lower()}`.",
        f"- Best relaxed scenario: `{_json_inline(summary.get('best_relaxed_scenario') or {})}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Branches",
        "",
        "| Branch | Scenario | Reason | Priced | PF | Avg Net | Net USD | Win Rate | Target Dates | Tickers |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for branch in _as_list(report.get("archived_branches")):
        branch = _as_dict(branch)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(branch.get("branch_id")),
                    _cell(branch.get("scenario_id")),
                    _cell(branch.get("archive_reason")),
                    _cell(branch.get("priced")),
                    _cell(branch.get("profit_factor")),
                    _cell(branch.get("avg_net_pnl_pct")),
                    _cell(branch.get("sum_net_pnl_usd")),
                    _cell(branch.get("win_rate_pct")),
                    _cell(", ".join(str(item) for item in _as_list(branch.get("target_dates")))),
                    _cell(", ".join(str(item) for item in _as_list(branch.get("target_tickers")))),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This archive is read-only. It does not delete chain-native scenarios, create trades, submit broker orders, mutate DB state, change scanner or contract-selection policy, change lane promotion, lower exact OPRA/NBBO proof bars, or promote negative chain-native replay.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Build the read-only regular-options chain-native relaxation archive.")
    parser.add_argument("--chain-native-exit-outcome-replay", type=Path, default=DEFAULT_CHAIN_NATIVE_EXIT_OUTCOME_REPLAY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = build_report(chain_native_exit_outcome_replay_path=args.chain_native_exit_outcome_replay)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    return 0 if report["status"] in {"chain_native_relaxation_archive_readback", "blocked_missing_inputs"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
