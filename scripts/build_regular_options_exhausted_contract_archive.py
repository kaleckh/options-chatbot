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

REPORT_ID = "regular_options_exhausted_contract_archive"

DEFAULT_REPAIR_BURNDOWN = ROOT / "data" / "profitability-lab" / "regular-options-repair-burndown" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-exhausted-contract-archive"
DEFAULT_PREVIOUS_ARCHIVE = DEFAULT_OUTPUT_DIR / "latest.json"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-exhausted-contract-archive.md"

ARCHIVE_STATUS = "archived_current_source_exhausted_contract_date"
EXHAUSTED_TARGET_STATUS = "excluded_current_source_exhausted"
EXHAUSTED_REPAIR_STATUS = "current_source_exhausted"
EXHAUSTED_OUTCOME = "exact_date_no_match"

PROHIBITED_ACTIONS = (
    "do_not_create_trade_from_exhausted_contract_archive",
    "do_not_submit_broker_order_from_exhausted_contract_archive",
    "do_not_mutate_trading_rows_from_exhausted_contract_archive",
    "do_not_change_scanner_policy_from_exhausted_contract_archive",
    "do_not_change_contract_selection_policy_from_exhausted_contract_archive",
    "do_not_change_stop_or_sizing_from_exhausted_contract_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_exhausted_contract_archive",
    "do_not_count_no_match_archive_as_production_proof",
)


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


def _target_key(target: dict[str, Any]) -> str:
    symbol = _norm(target.get("symbol")) or "unknown_symbol"
    lane = _norm(target.get("lane_id")) or "unknown_lane"
    contract = _norm(target.get("contract_symbol")) or "unknown_contract"
    quote_date = _norm(target.get("missing_quote_date")) or "unknown_date"
    return f"{symbol}|{lane}|{contract}|{quote_date}"


def _attempt_is_exact_no_match(attempt: dict[str, Any], *, contract_symbol: str, missing_quote_date: str) -> bool:
    return (
        _norm(attempt.get("contract_symbol")) == contract_symbol
        and _norm(attempt.get("missing_quote_date")) == missing_quote_date
        and bool(attempt.get("current_source_exhausted_for_exact_date"))
        and _norm(attempt.get("outcome")) == EXHAUSTED_OUTCOME
        and _norm(attempt.get("proof_repair_status")) == EXHAUSTED_REPAIR_STATUS
        and _safe_int(attempt.get("exact_date_row_count")) == 0
        and _safe_int(attempt.get("total_row_count")) == 0
    )


def _eligible_exhausted_target(target: dict[str, Any], *, min_attempt_count: int) -> bool:
    contract_symbol = _norm(target.get("contract_symbol"))
    missing_quote_date = _norm(target.get("missing_quote_date"))
    if not contract_symbol or not missing_quote_date:
        return False
    if _norm(target.get("burndown_status")) != EXHAUSTED_TARGET_STATUS:
        return False
    if _norm(target.get("repair_actionability_status")) != EXHAUSTED_REPAIR_STATUS:
        return False
    attempts = [_as_dict(item) for item in _as_list(target.get("latest_attempts"))]
    exact_no_match_attempts = [
        attempt
        for attempt in attempts
        if _attempt_is_exact_no_match(
            attempt,
            contract_symbol=contract_symbol,
            missing_quote_date=missing_quote_date,
        )
    ]
    return len(exact_no_match_attempts) >= min_attempt_count


def _archive_item(target: dict[str, Any], *, min_attempt_count: int) -> dict[str, Any]:
    attempts = [_as_dict(item) for item in _as_list(target.get("latest_attempts"))]
    contract_symbol = _norm(target.get("contract_symbol"))
    missing_quote_date = _norm(target.get("missing_quote_date"))
    exact_no_match_attempts = [
        attempt
        for attempt in attempts
        if _attempt_is_exact_no_match(
            attempt,
            contract_symbol=contract_symbol,
            missing_quote_date=missing_quote_date,
        )
    ]
    return {
        "archive_key": _target_key(target),
        "archive_status": ARCHIVE_STATUS,
        "archive_reason": "repeated_exact_date_no_match_current_source_exhausted",
        "symbol": target.get("symbol"),
        "lane_id": target.get("lane_id"),
        "lane_family": target.get("lane_family"),
        "contract_symbol": target.get("contract_symbol"),
        "missing_quote_date": target.get("missing_quote_date"),
        "missing_leg_role": target.get("missing_leg_role"),
        "unpriced_reason": target.get("unpriced_reason"),
        "source_artifact": target.get("source_artifact"),
        "selection_readiness": target.get("selection_readiness"),
        "capture_tier": target.get("capture_tier"),
        "repair_actionability_status": target.get("repair_actionability_status"),
        "burndown_status": target.get("burndown_status"),
        "min_attempt_count_required": min_attempt_count,
        "exact_no_match_attempt_count": len(exact_no_match_attempts),
        "latest_attempts": exact_no_match_attempts,
        "metrics": _as_dict(target.get("metrics")),
        "blocking_gates": _as_list(target.get("blocking_gates")),
        "promotion_ready": False,
        "production_proof": False,
    }


def _dedupe_archive_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _norm(item.get("archive_key"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _previous_archive_items(previous_archive: dict[str, Any]) -> list[dict[str, Any]]:
    if previous_archive.get("report_id") != REPORT_ID:
        return []
    if previous_archive.get("status") != "exhausted_contract_archive_readback":
        return []
    if _has_live_policy_change(previous_archive):
        return []
    return _dedupe_archive_items(
        [
            _as_dict(item)
            for item in _as_list(previous_archive.get("archived_contract_targets"))
            if _norm(_as_dict(item).get("archive_status")) == ARCHIVE_STATUS
        ]
    )


def _archive_targets(
    repair_burndown: dict[str, Any],
    *,
    previous_archived: list[dict[str, Any]],
    limit: int,
    min_attempt_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    candidates = [
        _as_dict(item)
        for item in _as_list(repair_burndown.get("exhausted_current_source_targets"))
        if _eligible_exhausted_target(_as_dict(item), min_attempt_count=min_attempt_count)
    ]
    previous = _dedupe_archive_items(previous_archived)
    previous_keys = {_norm(item.get("archive_key")) for item in previous}
    unarchived_candidates = [target for target in candidates if _target_key(target) not in previous_keys]
    newly_archived = [
        _archive_item(target, min_attempt_count=min_attempt_count)
        for target in unarchived_candidates[:limit]
    ]
    archived = _dedupe_archive_items([*previous, *newly_archived])
    candidate_keys = {_target_key(target) for target in candidates}
    archived_current_keys = (previous_keys & candidate_keys) | {
        _norm(item.get("archive_key")) for item in newly_archived
    }
    return archived, newly_archived, max(0, len(candidates) - len(archived_current_keys))


def _overall_status(archived: list[dict[str, Any]], newly_archived: list[dict[str, Any]]) -> str:
    if newly_archived:
        return "exhausted_contract_target_archived"
    if archived:
        return "exhausted_contract_archive_no_new_target"
    return "no_exhausted_contract_target_ready_to_archive"


def build_report(
    *,
    repair_burndown_path: Path = DEFAULT_REPAIR_BURNDOWN,
    previous_archive_path: Path = DEFAULT_PREVIOUS_ARCHIVE,
    limit: int = 1,
    min_attempt_count: int = 2,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    repair_burndown, input_meta = _load_json(repair_burndown_path)
    previous_archive, previous_meta = _load_json(previous_archive_path)
    previous_archived = _previous_archive_items(previous_archive)
    previous_meta["required"] = False
    previous_meta["loaded_archive_item_count"] = len(previous_archived)
    missing_required = []
    if input_meta.get("status") != "loaded":
        missing_required.append("repair_burndown")
    live_policy_change = _has_live_policy_change(repair_burndown)
    source_ready = (
        not missing_required
        and repair_burndown.get("status") == "repair_burndown_ready"
        and not live_policy_change
    )
    archived, newly_archived, remaining_eligible = (
        _archive_targets(
            repair_burndown,
            previous_archived=previous_archived,
            limit=max(1, limit),
            min_attempt_count=max(1, min_attempt_count),
        )
        if source_ready
        else (previous_archived, [], 0)
    )
    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "exhausted_contract_archive_readback"
        overall_status = _overall_status(archived, newly_archived)

    summary = _as_dict(repair_burndown.get("summary"))
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_exhausted_contract_date_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "source_repair_burndown_status": repair_burndown.get("status"),
            "source_ready_for_archive": source_ready,
            "missing_required_inputs": missing_required,
            "source_exhausted_current_source_target_count": summary.get("exhausted_current_source_target_count"),
            "archived_exhausted_contract_count": len(archived),
            "previous_archived_exhausted_contract_count": len(previous_archived),
            "newly_archived_exhausted_contract_count": len(newly_archived),
            "remaining_eligible_exhausted_contract_count": remaining_eligible,
            "archive_limit": max(1, limit),
            "new_target_limit": max(1, limit),
            "min_attempt_count_required": max(1, min_attempt_count),
            "archive_complete_for_selected_limit": bool(newly_archived),
            "live_policy_change": live_policy_change,
        },
        "inputs": {"repair_burndown": input_meta, "previous_archive": previous_meta},
        "archived_contract_targets": archived,
        "newly_archived_contract_targets": newly_archived,
        "proof_policy": {
            "readback_is": "read-only archive of current-source-exhausted exact contract/date targets",
            "readback_is_not": "production proof, scanner policy, contract-selection policy, broker action, DB mutation, sizing, or stop policy",
            "trusted_proof_standard": "no-match targets do not count as proof; future proof requires trusted intraday exact-contract OPRA/NBBO bid/ask rows",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "live_policy_change": live_policy_change,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Exhausted Contract Archive",
        "",
        "This report is generated from `scripts/build_regular_options_exhausted_contract_archive.py`. It is a read-only archive for exact contract/date repair targets where the current source repeatedly returned no exact rows.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Archived exhausted contracts: `{summary.get('archived_exhausted_contract_count')}`.",
        f"- Previously archived exhausted contracts: `{summary.get('previous_archived_exhausted_contract_count')}`.",
        f"- Newly archived exhausted contracts: `{summary.get('newly_archived_exhausted_contract_count')}`.",
        f"- Remaining eligible exhausted contracts: `{summary.get('remaining_eligible_exhausted_contract_count')}`.",
        f"- Source exhausted targets: `{summary.get('source_exhausted_current_source_target_count')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Contract Targets",
        "",
        "| Archive Key | Symbol | Lane | Contract | Missing Quote Date | Attempts | Reason |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for target in _as_list(report.get("archived_contract_targets")):
        target = _as_dict(target)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(target.get("archive_key")),
                    _cell(target.get("symbol")),
                    _cell(target.get("lane_id")),
                    _cell(target.get("contract_symbol")),
                    _cell(target.get("missing_quote_date")),
                    _cell(target.get("exact_no_match_attempt_count")),
                    _cell(target.get("archive_reason")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This archive is read-only. It does not create trades, submit broker orders, mutate trading rows, change scanner or contract-selection policy, change stops or sizing, lower exact OPRA/NBBO proof bars, or count no-match rows as production proof.",
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
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
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
    parser = argparse.ArgumentParser(description="Build the read-only exhausted contract/date archive.")
    parser.add_argument("--repair-burndown", type=Path, default=DEFAULT_REPAIR_BURNDOWN)
    parser.add_argument("--previous-archive", type=Path, default=DEFAULT_PREVIOUS_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--limit", type=int, default=1, help="Maximum new exhausted contract/date targets to archive.")
    parser.add_argument("--min-attempt-count", type=int, default=2)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = build_report(
        repair_burndown_path=args.repair_burndown,
        previous_archive_path=args.previous_archive,
        limit=args.limit,
        min_attempt_count=args.min_attempt_count,
    )
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    return 0 if report["status"] in {"exhausted_contract_archive_readback", "blocked_missing_inputs"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
