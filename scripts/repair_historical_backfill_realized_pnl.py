from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from historical_options_store import HistoricalOptionsStore
from local_env import load_local_env
from options_execution import commission_total_usd, option_pnl_snapshot
from positions_repository import create_positions_repository
from us_equity_market_calendar import is_us_equity_market_day

from scripts.migrate_main_lane_backfills_to_positions import (
    DEFAULT_HISTORICAL_OPTIONS_DB,
    _backup_positions_snapshot,
    _parse_date,
    _safe_float,
    _source_snapshot,
    _spread_exit_snapshot,
)


ET = ZoneInfo("America/New_York")
REPAIR_ID = "historical_suggested_close_realized_pnl_repair_v1"
DEFAULT_AUDIT_IDS = (
    "all_lanes_zero_pick_current_algo_v1",
    "main_lane_zero_pick_current_algo_v1",
)
REPORT_LATEST = ROOT / "data" / "forward-tracking" / f"{REPAIR_ID}_latest.json"
DEFAULT_SOURCE_LABELS = ["thetadata_opra_nbbo_1m"]
PROFIT_HARVEST_LANES = {
    "bullish_pullback_observation",
    "tracked_winner_primary",
    "tracked_winner_observation",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _split_csv(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return list(default)
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _market_days(start: date, end: date):
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            yield current
        current += timedelta(days=1)


def _close_datetime(close_date: date) -> datetime:
    return datetime.combine(close_date, time(15, 55), tzinfo=ET)


def _fee_sides(source_pick: dict[str, Any]) -> int:
    return 2 if str(source_pick.get("strategy_type") or "").lower() == "vertical_spread" else 1


def _profit_harvest_enabled(source_pick: dict[str, Any]) -> bool:
    lane = str(source_pick.get("cohort_id") or source_pick.get("playbook_id") or "").strip().lower()
    return lane in PROFIT_HARVEST_LANES


def _candidate_sell_reason(
    *,
    position: dict[str, Any],
    source_pick: dict[str, Any],
    review_date: date,
    entry_date: date,
    gross_pnl_pct: float,
    peak_pnl_pct: float,
) -> tuple[str | None, str | None]:
    days_held = max((review_date - entry_date).days, 0)
    stop_loss_pct = _safe_float(position.get("stop_loss_pct"))
    stop_loss_pct = min(stop_loss_pct if stop_loss_pct is not None else 90.0, 90.0)
    profit_target_pct = _safe_float(position.get("profit_target_pct"))
    profit_target_pct = profit_target_pct if profit_target_pct is not None else 100.0
    time_exit_day = int(float(position.get("time_exit_day") or 1))

    if gross_pnl_pct <= -stop_loss_pct:
        return "historical_suggested_stop_loss", f"Historical executable exit hit the stop loss at {gross_pnl_pct:+.1f}%."
    if gross_pnl_pct >= profit_target_pct:
        return "historical_suggested_profit_target", f"Historical executable exit hit the profit target at {gross_pnl_pct:+.1f}%."
    if _profit_harvest_enabled(source_pick) and days_held >= 1 and gross_pnl_pct >= 50.0:
        return "historical_suggested_profit_harvest", (
            "Historical mechanical profit harvest triggered at "
            f"{gross_pnl_pct:+.1f}% executable P&L."
        )
    if (
        _profit_harvest_enabled(source_pick)
        and days_held >= 1
        and peak_pnl_pct >= 50.0
        and peak_pnl_pct - gross_pnl_pct >= 20.0
        and gross_pnl_pct >= 15.0
    ):
        return "historical_suggested_profit_harvest_giveback", (
            "Historical mechanical profit harvest triggered after a giveback from "
            f"{peak_pnl_pct:+.1f}% peak to {gross_pnl_pct:+.1f}%."
        )
    if days_held >= time_exit_day:
        return "historical_suggested_time_exit", (
            f"Historical time exit reached after {days_held} calendar day(s), "
            f"versus a {time_exit_day}-day limit."
        )
    return None, None


def _simulate_suggested_close(
    position: dict[str, Any],
    *,
    store: HistoricalOptionsStore,
    source_labels: list[str],
    pricing_lane: str,
    trusted_only: bool,
    as_of: date,
) -> dict[str, Any]:
    source_pick = _source_snapshot(position.get("source_pick_snapshot"))
    entry_date = _parse_date(position.get("filled_at"))
    expiry_date = _parse_date(position.get("expiry"))
    end_date = min(as_of, expiry_date)
    entry_execution_price = _safe_float(position.get("entry_execution_price") or position.get("entry_option_price"))
    if entry_execution_price is None or entry_execution_price <= 0:
        return {"status": "skipped", "reason": "missing_entry_execution_price"}

    contracts = max(int(position.get("contracts") or 1), 1)
    fee_sides = _fee_sides(source_pick)
    entry_fee = _safe_float(position.get("entry_fee_total_usd"))
    if entry_fee is None:
        entry_fee = commission_total_usd(contracts=contracts, sides=fee_sides)
    exit_fee = commission_total_usd(contracts=contracts, sides=fee_sides)

    peak_pnl_pct = _safe_float(position.get("peak_pnl_pct")) or 0.0
    first_unpriced_sell: dict[str, Any] | None = None
    priced_day_count = 0
    unpriced_day_count = 0

    for review_date in _market_days(entry_date, end_date):
        days_held = max((review_date - entry_date).days, 0)
        exit_snapshot = _spread_exit_snapshot(
            source_pick,
            close_date=review_date,
            store=store,
            source_labels=source_labels,
            requested_pricing_lane=pricing_lane,
            trusted_only=trusted_only,
        )
        if not exit_snapshot.get("priced"):
            unpriced_day_count += 1
            time_exit_day = int(float(position.get("time_exit_day") or 1))
            if days_held >= time_exit_day and first_unpriced_sell is None:
                first_unpriced_sell = {
                    "review_date": review_date.isoformat(),
                    "reason": "historical_suggested_time_exit_unpriced",
                    "unpriced_reason": exit_snapshot.get("unpriced_reason"),
                    "missing_long_contract_symbol": exit_snapshot.get("missing_long_contract_symbol"),
                    "missing_short_contract_symbol": exit_snapshot.get("missing_short_contract_symbol"),
                }
            continue

        priced_day_count += 1
        exit_price = float(exit_snapshot["exit_price"])
        pnl = option_pnl_snapshot(
            entry_execution_price=entry_execution_price,
            exit_execution_price=exit_price,
            contracts=contracts,
            entry_fee_total_usd=entry_fee,
            exit_fee_total_usd=exit_fee,
        )
        gross_pnl_pct = float(pnl.get("gross_pnl_pct") or 0.0)
        peak_pnl_pct = round(max(peak_pnl_pct, gross_pnl_pct), 4)
        exit_reason, reason_text = _candidate_sell_reason(
            position=position,
            source_pick=source_pick,
            review_date=review_date,
            entry_date=entry_date,
            gross_pnl_pct=gross_pnl_pct,
            peak_pnl_pct=peak_pnl_pct,
        )
        if exit_reason:
            return {
                "status": "sell",
                "review_date": review_date.isoformat(),
                "closed_at": _close_datetime(review_date),
                "exit_reason": exit_reason,
                "reason_text": reason_text,
                "exit_price": exit_price,
                "exit_execution_basis": exit_snapshot.get("exit_execution_basis"),
                "pnl": pnl,
                "peak_pnl_pct": peak_pnl_pct,
                "exit_snapshot": exit_snapshot,
                "first_unpriced_sell": first_unpriced_sell,
                "priced_day_count": priced_day_count,
                "unpriced_day_count": unpriced_day_count,
            }

    return {
        "status": "no_executable_suggested_close",
        "first_unpriced_sell": first_unpriced_sell,
        "priced_day_count": priced_day_count,
        "unpriced_day_count": unpriced_day_count,
    }


def _needs_update(position: dict[str, Any], repair: dict[str, Any]) -> bool:
    if repair.get("status") != "sell":
        return False
    close_date = str(position.get("closed_at") or "")[:10]
    exit_price = _safe_float(position.get("exit_execution_price"))
    gross_pnl = _safe_float(position.get("gross_pnl_pct"))
    return (
        str(position.get("status") or "") != "closed"
        or close_date != str(repair["review_date"])[:10]
        or exit_price is None
        or abs(exit_price - float(repair["exit_price"])) > 0.0001
        or gross_pnl is None
    )


def _repair_updates(position: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
    source_pick = _source_snapshot(position.get("source_pick_snapshot"))
    source_pick["historical_suggested_close_repair"] = {
        "repair_id": REPAIR_ID,
        "repaired_at_utc": _utc_now_iso(),
        "review_date": repair["review_date"],
        "exit_reason": repair["exit_reason"],
        "exit_snapshot": repair.get("exit_snapshot"),
        "first_unpriced_sell": repair.get("first_unpriced_sell"),
        "priced_day_count": repair.get("priced_day_count"),
        "unpriced_day_count": repair.get("unpriced_day_count"),
    }
    pnl = repair["pnl"]
    notes_suffix = (
        f"Historical realized P&L repaired by {REPAIR_ID}: closed at the first executable "
        f"historical review SELL on {repair['review_date']} ({repair['exit_reason']})."
    )
    notes = str(position.get("notes") or "").strip()
    if notes_suffix not in notes:
        notes = f"{notes}\n{notes_suffix}".strip()
    return {
        "status": "closed",
        "closed_at": repair["closed_at"],
        "exit_option_price": repair["exit_price"],
        "exit_execution_price": repair["exit_price"],
        "exit_execution_basis": repair.get("exit_execution_basis") or "historical_suggested_close",
        "exit_reason": repair["exit_reason"],
        "last_option_price": repair["exit_price"],
        "last_pnl_pct": pnl.get("gross_pnl_pct"),
        "gross_pnl_pct": pnl.get("gross_pnl_pct"),
        "net_pnl_pct": pnl.get("net_pnl_pct"),
        "gross_pnl_usd": pnl.get("gross_pnl_usd"),
        "net_pnl_usd": pnl.get("net_pnl_usd"),
        "fee_total_usd": pnl.get("fee_total_usd"),
        "peak_pnl_pct": repair.get("peak_pnl_pct"),
        "last_reviewed_at": repair["closed_at"],
        "last_recommendation": "SELL",
        "last_recommendation_reason": repair.get("reason_text"),
        "source_pick_snapshot": source_pick,
        "notes": notes,
    }


def repair(args: argparse.Namespace) -> dict[str, Any]:
    load_local_env(ROOT)
    os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(Path(args.historical_db_path))
    audit_ids = set(_split_csv(args.audit_ids, DEFAULT_AUDIT_IDS))
    source_labels = _split_csv(args.source_labels, tuple(DEFAULT_SOURCE_LABELS))
    as_of = _parse_date(args.as_of_date) if args.as_of_date else datetime.now(ET).date()
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    store = HistoricalOptionsStore(args.historical_db_path)

    positions = []
    for position in repository.list_positions(None) or []:
        source_pick = _source_snapshot(position.get("source_pick_snapshot"))
        if str(source_pick.get("backfill_audit_id") or "") in audit_ids:
            positions.append(position)

    counters: Counter[str] = Counter()
    changed: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    backup_path = None
    if args.apply:
        backup_path = _backup_positions_snapshot(repository, label=f"pre-{REPAIR_ID}")

    for position in positions:
        repair_result = _simulate_suggested_close(
            position,
            store=store,
            source_labels=source_labels,
            pricing_lane=args.pricing_lane,
            trusted_only=bool(args.trusted_only),
            as_of=as_of,
        )
        counters[f"simulated_{repair_result['status']}"] += 1
        missing_realized = (
            str(position.get("status") or "") == "closed"
            and (
                position.get("exit_execution_price") is None
                or position.get("gross_pnl_pct") is None
                or position.get("net_pnl_pct") is None
            )
        )
        if repair_result.get("status") != "sell":
            if missing_realized:
                counters["remaining_missing_realized_no_executable_sell"] += 1
                unresolved.append(
                    {
                        "id": position.get("id"),
                        "ticker": position.get("ticker"),
                        "audit_id": _source_snapshot(position.get("source_pick_snapshot")).get("backfill_audit_id"),
                        "playbook_id": _source_snapshot(position.get("source_pick_snapshot")).get("playbook_id"),
                        "status": position.get("status"),
                        "closed_at": position.get("closed_at"),
                        "exit_reason": position.get("exit_reason"),
                        "first_unpriced_sell": repair_result.get("first_unpriced_sell"),
                    }
                )
            continue
        if args.only_missing_realized and not missing_realized:
            counters["skipped_already_has_realized_due_only_missing"] += 1
            continue
        if not _needs_update(position, repair_result):
            counters["already_correct"] += 1
            if len(unchanged) < int(args.example_limit):
                unchanged.append(
                    {
                        "id": position.get("id"),
                        "ticker": position.get("ticker"),
                        "review_date": repair_result.get("review_date"),
                        "exit_reason": repair_result.get("exit_reason"),
                    }
                )
            continue

        counters["would_update" if not args.apply else "updated"] += 1
        update_payload = _repair_updates(position, repair_result)
        if args.apply:
            repository.update_position(int(position["id"]), update_payload)
        if len(changed) < int(args.example_limit):
            changed.append(
                {
                    "id": position.get("id"),
                    "ticker": position.get("ticker"),
                    "playbook_id": _source_snapshot(position.get("source_pick_snapshot")).get("playbook_id"),
                    "old_status": position.get("status"),
                    "old_closed_at": position.get("closed_at"),
                    "old_exit_execution_price": position.get("exit_execution_price"),
                    "old_gross_pnl_pct": position.get("gross_pnl_pct"),
                    "new_review_date": repair_result.get("review_date"),
                    "new_exit_reason": repair_result.get("exit_reason"),
                    "new_exit_execution_price": repair_result.get("exit_price"),
                    "new_gross_pnl_pct": repair_result.get("pnl", {}).get("gross_pnl_pct"),
                    "first_unpriced_sell": repair_result.get("first_unpriced_sell"),
                }
            )

    report = {
        "repair_id": REPAIR_ID,
        "apply": bool(args.apply),
        "audit_ids": sorted(audit_ids),
        "as_of_date": as_of.isoformat(),
        "position_count": len(positions),
        "summary": dict(counters),
        "changed_examples": changed,
        "unchanged_examples": unchanged,
        "unresolved_examples": unresolved[: int(args.example_limit)],
        "backup_path": str(backup_path) if backup_path else None,
        "source_labels": source_labels,
        "historical_options_db": str(Path(args.historical_db_path)),
        "generated_at_utc": _utc_now_iso(),
    }
    if args.apply:
        REPORT_LATEST.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_LATEST.with_name(f"{REPAIR_ID}_{stamp}.json")
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        REPORT_LATEST.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["report_path"] = str(report_path)
        REPORT_LATEST.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair historical backfill closed realized P&L at the first executable suggested-close date."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--audit-ids", default=",".join(DEFAULT_AUDIT_IDS))
    parser.add_argument("--as-of-date", default=datetime.now(ET).date().isoformat())
    parser.add_argument("--historical-db-path", default=str(DEFAULT_HISTORICAL_OPTIONS_DB))
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--pricing-lane", default="pessimistic", choices=["pessimistic", "mid"])
    parser.add_argument("--trusted-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--only-missing-realized",
        action="store_true",
        help="Repair only closed rows that are missing stored exit/P&L fields.",
    )
    parser.add_argument("--example-limit", type=int, default=25)
    return parser.parse_args()


def main() -> int:
    print(json.dumps(repair(parse_args()), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
