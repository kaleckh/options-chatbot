from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_lane_month_post_expiry_archive"

DEFAULT_MONTHLY_LANE_PNL = ROOT / "data" / "forward-tracking" / "regular_options_monthly_lane_exact_pnl_latest.json"
DEFAULT_PREVIOUS_ARCHIVE = ROOT / "data" / "forward-tracking" / f"{REPORT_ID}_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"

ARCHIVE_STATUS = "archived_lane_month_post_expiry_non_executable_exit"
READY_STATUSES = {"healthy", "durable_exact_no_match"}
CONTRACT_RE = re.compile(r"^(.+?)(\d{6})([CP])(\d{8})$")
EASTERN_TZ = ZoneInfo("America/New_York")

PROHIBITED_ACTIONS = (
    "do_not_create_trade_from_lane_month_post_expiry_archive",
    "do_not_submit_broker_order_from_lane_month_post_expiry_archive",
    "do_not_mutate_database_from_lane_month_post_expiry_archive",
    "do_not_change_scanner_policy_from_lane_month_post_expiry_archive",
    "do_not_change_contract_selection_policy_from_lane_month_post_expiry_archive",
    "do_not_change_stop_or_sizing_from_lane_month_post_expiry_archive",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_lane_month_post_expiry_archive",
    "do_not_count_post_expiry_archive_as_production_proof",
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


def _parse_iso_date(value: Any) -> date | None:
    raw = _norm(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_occ_expiration(contract_symbol: Any) -> date | None:
    symbol = _norm(contract_symbol).upper()
    match = CONTRACT_RE.match(symbol)
    if not match:
        return None
    raw = match.group(2)
    try:
        year = 2000 + int(raw[:2])
        month = int(raw[2:4])
        day = int(raw[4:6])
        return date(year, month, day)
    except ValueError:
        return None


def _exit_timestamp_utc(exit_date: date) -> str:
    local = datetime.combine(exit_date, time(15, 55), tzinfo=EASTERN_TZ)
    return local.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _archive_key(row: dict[str, Any], *, target_month: str, target_lane: str) -> str:
    return "|".join(
        [
            target_month,
            target_lane,
            _norm(row.get("ticker")) or "unknown_ticker",
            _norm(row.get("entry_date"))[:10] or "unknown_entry",
            _norm(row.get("exit_date"))[:10] or "unknown_exit",
            _norm(row.get("long_contract_symbol")).upper() or "unknown_long",
            _norm(row.get("short_contract_symbol")).upper() or "unknown_short",
        ]
    )


def _post_expiry_archive_item(
    row: dict[str, Any],
    *,
    target_month: str,
    target_lane: str,
    feed_readiness_status: str,
    feed_readiness_evidence: list[str],
) -> dict[str, Any] | None:
    exit_date = _parse_iso_date(row.get("exit_date"))
    long_symbol = _norm(row.get("long_contract_symbol")).upper()
    short_symbol = _norm(row.get("short_contract_symbol")).upper()
    long_expiration = _parse_occ_expiration(long_symbol)
    short_expiration = _parse_occ_expiration(short_symbol)
    if exit_date is None or long_expiration is None or short_expiration is None:
        return None
    if exit_date <= long_expiration or exit_date <= short_expiration:
        return None
    return {
        "archive_key": _archive_key(row, target_month=target_month, target_lane=target_lane),
        "archive_status": ARCHIVE_STATUS,
        "archive_reason": "exit_date_after_contract_expiration",
        "target_month": target_month,
        "target_lane": target_lane,
        "ticker": row.get("ticker"),
        "entry_date": _norm(row.get("entry_date"))[:10],
        "exit_date": exit_date.isoformat(),
        "exit_timestamp_utc": _exit_timestamp_utc(exit_date),
        "long_contract_symbol": long_symbol,
        "short_contract_symbol": short_symbol,
        "long_contract_expiration": long_expiration.isoformat(),
        "short_contract_expiration": short_expiration.isoformat(),
        "missing_blockers": _as_list(row.get("blockers")),
        "feed_readiness_status": feed_readiness_status,
        "feed_readiness_evidence": feed_readiness_evidence,
        "post_expiry_days": {
            "long_leg": (exit_date - long_expiration).days,
            "short_leg": (exit_date - short_expiration).days,
        },
        "contract_leg_count": 2,
        "production_proof": False,
        "true_executable_pnl_row": False,
        "promotion_ready": False,
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
    if previous_archive.get("status") != "lane_month_post_expiry_archive_readback":
        return []
    if _has_live_policy_change(previous_archive):
        return []
    return _dedupe_archive_items(
        [
            _as_dict(item)
            for item in _as_list(previous_archive.get("archived_lane_month_rows"))
            if _norm(_as_dict(item).get("archive_status")) == ARCHIVE_STATUS
        ]
    )


def _eligible_items(
    monthly_report: dict[str, Any],
    *,
    feed_readiness_status: str,
    feed_readiness_evidence: list[str],
) -> list[dict[str, Any]]:
    summary = _as_dict(monthly_report.get("summary"))
    target_month = _norm(summary.get("target_month"))
    target_lane = _norm(summary.get("target_lane"))
    items: list[dict[str, Any]] = []
    for raw in _as_list(monthly_report.get("lane_month_rows")):
        row = _as_dict(raw)
        if row.get("true_executable_pnl_available"):
            continue
        item = _post_expiry_archive_item(
            row,
            target_month=target_month,
            target_lane=target_lane,
            feed_readiness_status=feed_readiness_status,
            feed_readiness_evidence=feed_readiness_evidence,
        )
        if item:
            items.append(item)
    return _dedupe_archive_items(items)


def build_report(
    *,
    monthly_lane_pnl_path: Path = DEFAULT_MONTHLY_LANE_PNL,
    previous_archive_path: Path = DEFAULT_PREVIOUS_ARCHIVE,
    feed_readiness_status: str = "not_checked",
    feed_readiness_evidence: list[str] | None = None,
    limit: int | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    monthly_report, monthly_meta = _load_json(monthly_lane_pnl_path)
    previous_archive, previous_meta = _load_json(previous_archive_path)
    previous_archived = _previous_archive_items(previous_archive)
    previous_meta["required"] = False
    previous_meta["loaded_archive_item_count"] = len(previous_archived)

    missing_required = []
    if monthly_meta.get("status") != "loaded":
        missing_required.append("monthly_lane_exact_pnl")
    live_policy_change = _has_live_policy_change(monthly_report)
    readiness_status = _norm(feed_readiness_status).lower()
    readiness_ready = readiness_status in READY_STATUSES
    if not readiness_ready:
        missing_required.append("thetadata_readiness_or_durable_no_match_evidence")

    source_ready = not missing_required and not live_policy_change
    eligible = (
        _eligible_items(
            monthly_report,
            feed_readiness_status=readiness_status,
            feed_readiness_evidence=list(feed_readiness_evidence or []),
        )
        if source_ready
        else []
    )
    previous_keys = {_norm(item.get("archive_key")) for item in previous_archived}
    limit_count = max(1, limit) if limit is not None else None
    unarchived = [item for item in eligible if _norm(item.get("archive_key")) not in previous_keys]
    newly_archived = unarchived[:limit_count] if limit_count is not None else unarchived
    archived = _dedupe_archive_items([*previous_archived, *newly_archived])
    archived_current_keys = (previous_keys & {_norm(item.get("archive_key")) for item in eligible}) | {
        _norm(item.get("archive_key")) for item in newly_archived
    }
    remaining_eligible = max(0, len(eligible) - len(archived_current_keys))

    if live_policy_change:
        status = "invalid_live_policy_change"
        overall_status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
        overall_status = "blocked_missing_inputs"
    else:
        status = "lane_month_post_expiry_archive_readback"
        if newly_archived:
            overall_status = "post_expiry_lane_month_branches_archived"
        elif archived:
            overall_status = "post_expiry_lane_month_archive_no_new_branch"
        else:
            overall_status = "no_post_expiry_lane_month_branch_to_archive"

    monthly_summary = _as_dict(monthly_report.get("summary"))
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_read_only_lane_month_post_expiry_archive",
        "schema_version": 1,
        "read_only": True,
        "summary": {
            "overall_status": overall_status,
            "source_monthly_lane_status": monthly_report.get("status"),
            "source_target_month": monthly_summary.get("target_month"),
            "source_target_lane": monthly_summary.get("target_lane"),
            "source_true_executable_lane_month_pnl_rows": monthly_summary.get(
                "true_executable_lane_month_pnl_rows"
            ),
            "source_missing_proof_count": monthly_summary.get("missing_proof_count"),
            "feed_readiness_status": readiness_status,
            "feed_readiness_ready": readiness_ready,
            "missing_required_inputs": missing_required,
            "eligible_post_expiry_row_count": len(eligible),
            "archived_post_expiry_row_count": len(archived),
            "previous_archived_post_expiry_row_count": len(previous_archived),
            "newly_archived_post_expiry_row_count": len(newly_archived),
            "remaining_eligible_post_expiry_row_count": remaining_eligible,
            "archived_contract_leg_count": sum(_safe_int(item.get("contract_leg_count")) for item in archived),
            "newly_archived_contract_leg_count": sum(
                _safe_int(item.get("contract_leg_count")) for item in newly_archived
            ),
            "archive_limit": limit_count,
            "live_policy_change": live_policy_change,
        },
        "inputs": {
            "monthly_lane_exact_pnl": monthly_meta,
            "previous_archive": previous_meta,
            "feed_readiness_evidence": list(feed_readiness_evidence or []),
        },
        "archived_lane_month_rows": archived,
        "newly_archived_lane_month_rows": newly_archived,
        "proof_policy": {
            "readback_is": "read-only archive of selected lane-month branches whose exact exit request is after contract expiration",
            "readback_is_not": "production proof, true P&L, scanner policy, contract-selection policy, broker action, DB mutation, sizing, or stop policy",
            "trusted_proof_standard": "future proof still requires trusted intraday exact-contract OPRA/NBBO bid/ask rows with executable entry/exit/fill P&L",
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
        "# Regular Options Lane-Month Post-Expiry Archive",
        "",
        "This report is generated from `scripts/build_regular_options_lane_month_post_expiry_archive.py`. It is a read-only archive for selected lane-month missing-P&L branches whose requested exact exit quote is after the encoded OCC contract expiration.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Source lane-month: `{summary.get('source_target_month')}` / `{summary.get('source_target_lane')}`.",
        f"- Source true rows: `{summary.get('source_true_executable_lane_month_pnl_rows')}`.",
        f"- Source missing rows: `{summary.get('source_missing_proof_count')}`.",
        f"- Feed readiness: `{summary.get('feed_readiness_status')}`.",
        f"- Newly archived rows: `{summary.get('newly_archived_post_expiry_row_count')}`.",
        f"- Archived rows: `{summary.get('archived_post_expiry_row_count')}`.",
        f"- Archived contract legs: `{summary.get('archived_contract_leg_count')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Archived Branches",
        "",
        "| Archive Key | Ticker | Entry | Exit | Exit UTC | Long Contract | Short Contract | Expiration | Reason |",
        "|---|---|---:|---:|---:|---|---|---:|---|",
    ]
    for item in _as_list(report.get("archived_lane_month_rows")):
        item = _as_dict(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("archive_key")),
                    _cell(item.get("ticker")),
                    _cell(item.get("entry_date")),
                    _cell(item.get("exit_date")),
                    _cell(item.get("exit_timestamp_utc")),
                    _cell(item.get("long_contract_symbol")),
                    _cell(item.get("short_contract_symbol")),
                    _cell(item.get("long_contract_expiration")),
                    _cell(item.get("archive_reason")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This archive is read-only. It does not create trades, submit broker orders, mutate trading rows, change scanner or contract-selection policy, change stops or sizing, lower exact OPRA/NBBO proof bars, or count post-expiry no-match rows as production proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
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
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only lane-month post-expiry archive.")
    parser.add_argument("--monthly-lane-pnl", type=Path, default=DEFAULT_MONTHLY_LANE_PNL)
    parser.add_argument("--previous-archive", type=Path, default=DEFAULT_PREVIOUS_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--feed-readiness-status", default="not_checked", choices=sorted((*READY_STATUSES, "not_checked")))
    parser.add_argument("--feed-readiness-evidence", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = build_report(
        monthly_lane_pnl_path=args.monthly_lane_pnl,
        previous_archive_path=args.previous_archive,
        feed_readiness_status=args.feed_readiness_status,
        feed_readiness_evidence=list(args.feed_readiness_evidence or []),
        limit=args.limit,
    )
    artifacts = None if args.no_write else write_outputs(report, output_dir=args.output_dir)
    if args.as_json:
        payload = {"report": report}
        if artifacts:
            payload["artifacts"] = artifacts
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps({"summary": report["summary"], "artifacts": artifacts}, indent=2, sort_keys=True))
    return 0 if report["status"] in {"lane_month_post_expiry_archive_readback", "blocked_missing_inputs"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
