from __future__ import annotations

import argparse
import copy
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

from historical_options_store import HistoricalOptionsStore, INTRADAY_SNAPSHOT_KIND
from local_env import load_local_env
from options_execution import commission_total_usd, option_pnl_snapshot
from positions_repository import create_positions_repository
from positions_service import build_position_payload, review_open_positions
from us_equity_market_calendar import is_us_equity_market_day
from wfo_optimizer import _resolve_imported_execution_price


ET = ZoneInfo("America/New_York")
AUDIT_ID = "main_lane_zero_pick_current_algo_v1"
MIGRATION_ID = "main_lane_zero_pick_position_migration_v1"
PLAYBOOK_ID = "bullish_pullback_observation"
DEFAULT_SOURCE_LABELS = ["thetadata_opra_nbbo_1m"]
DEFAULT_HISTORICAL_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
SCAN_LOG = ROOT / "data" / "forward-tracking" / "scan_picks.jsonl"
FILL_ATTEMPT_LOG = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
REPORT_LATEST = ROOT / "data" / "forward-tracking" / "main_lane_zero_pick_position_migration_latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _pick_fill_price(pick: dict[str, Any]) -> float | None:
    for key in ("entry_execution_price", "net_debit", "premium", "est_premium", "mid"):
        value = _safe_float(pick.get(key))
        if value is not None and value > 0:
            return round(float(value), 4)
    return None


def _market_day_on_or_after(day: date) -> date:
    current = day
    while not is_us_equity_market_day(current):
        current += timedelta(days=1)
    return current


def _entry_date(pick: dict[str, Any]) -> date:
    return _parse_date(
        pick.get("scan_date")
        or pick.get("date")
        or pick.get("quote_time_et")
        or pick.get("logged_at")
    )


def _filled_at(pick: dict[str, Any]) -> str:
    return str(
        pick.get("quote_time_et")
        or pick.get("logged_at")
        or datetime.combine(_entry_date(pick), time(10, 10), tzinfo=ET).isoformat()
    )


def _close_datetime(close_date: date) -> datetime:
    return datetime.combine(close_date, time(15, 55), tzinfo=ET)


def _lifecycle_for_pick(pick: dict[str, Any], *, as_of: date) -> dict[str, Any]:
    entry = _entry_date(pick)
    expiry = _parse_date(pick["expiry"])
    time_exit_day = max(int(float(pick.get("time_exit_day") or 1)), 1)
    time_exit_target = entry + timedelta(days=time_exit_day)
    time_exit_close = _market_day_on_or_after(time_exit_target)
    if expiry <= time_exit_close:
        scheduled_close = expiry
        close_reason = "historical_backfill_expired"
    else:
        scheduled_close = time_exit_close
        close_reason = "historical_backfill_time_exit_elapsed"
    status_at_migration = "closed" if scheduled_close <= as_of else "open"
    return {
        "entry_date": entry.isoformat(),
        "expiry": expiry.isoformat(),
        "time_exit_day": time_exit_day,
        "time_exit_target_date": time_exit_target.isoformat(),
        "time_exit_scheduled_market_date": time_exit_close.isoformat(),
        "scheduled_close_date": scheduled_close.isoformat(),
        "scheduled_close_reason": close_reason,
        "status_at_migration": status_at_migration,
        "as_of_date": as_of.isoformat(),
    }


def _spread_exit_snapshot(
    pick: dict[str, Any],
    *,
    close_date: date,
    store: HistoricalOptionsStore,
    source_labels: list[str],
    requested_pricing_lane: str,
    trusted_only: bool,
) -> dict[str, Any]:
    long_symbol = str(pick.get("contract_symbol") or "").strip().upper()
    short_symbol = str(pick.get("short_contract_symbol") or "").strip().upper()
    if not long_symbol or not short_symbol:
        return {"priced": False, "unpriced_reason": "missing_spread_contract_symbol"}

    long_quote = store.get_closing_quote(
        contract_symbol=long_symbol,
        quote_date_et=close_date,
        snapshot_kind=INTRADAY_SNAPSHOT_KIND,
        allow_last_price=False,
        source_labels=source_labels,
        trusted_only=trusted_only,
    )
    short_quote = store.get_closing_quote(
        contract_symbol=short_symbol,
        quote_date_et=close_date,
        snapshot_kind=INTRADAY_SNAPSHOT_KIND,
        allow_last_price=False,
        source_labels=source_labels,
        trusted_only=trusted_only,
    )
    if long_quote is None or short_quote is None:
        return {
            "priced": False,
            "unpriced_reason": "missing_exit_quote_for_leg",
            "missing_long_contract_symbol": long_symbol if long_quote is None else None,
            "missing_short_contract_symbol": short_symbol if short_quote is None else None,
            "quote_date_et": close_date.isoformat(),
        }

    long_exec = _resolve_imported_execution_price(
        side="exit",
        requested_pricing_lane=requested_pricing_lane,
        bid=long_quote.bid,
        ask=long_quote.ask,
        last=long_quote.last,
        slippage_pct=0.0,
    )
    short_exec = _resolve_imported_execution_price(
        side="entry",
        requested_pricing_lane=requested_pricing_lane,
        bid=short_quote.bid,
        ask=short_quote.ask,
        last=short_quote.last,
        slippage_pct=0.0,
    )
    long_price = _safe_float(long_exec.get("execution_price"))
    short_price = _safe_float(short_exec.get("execution_price"))
    if long_price is None or short_price is None:
        return {
            "priced": False,
            "unpriced_reason": "exit_quote_not_executable",
            "quote_date_et": close_date.isoformat(),
            "long_execution_price": long_price,
            "short_execution_price": short_price,
        }

    exit_price = round(max(float(long_price) - float(short_price), 0.0), 4)
    return {
        "priced": True,
        "quote_date_et": close_date.isoformat(),
        "exit_price": exit_price,
        "exit_execution_basis": (
            f"historical_spread_{long_exec.get('execution_basis')}_"
            f"{short_exec.get('execution_basis')}"
        ),
        "long_quote": {
            "contract_symbol": long_quote.contract_symbol,
            "bid": long_quote.bid,
            "ask": long_quote.ask,
            "quote_minute_et": long_quote.quote_minute_et,
            "as_of_utc": long_quote.as_of_utc,
        },
        "short_quote": {
            "contract_symbol": short_quote.contract_symbol,
            "bid": short_quote.bid,
            "ask": short_quote.ask,
            "quote_minute_et": short_quote.quote_minute_et,
            "as_of_utc": short_quote.as_of_utc,
        },
    }


def _closed_payload_updates(
    payload: dict[str, Any],
    *,
    close_dt: datetime,
    close_reason: str,
    exit_snapshot: dict[str, Any],
) -> dict[str, Any]:
    notes_suffix = (
        "Closed during historical paper-position migration because the position "
        f"had reached {close_reason.replace('_', ' ')}."
    )
    updates: dict[str, Any] = {
        "status": "closed",
        "closed_at": close_dt,
        "exit_reason": close_reason,
        "last_recommendation": "SELL",
        "last_recommendation_reason": close_reason,
        "last_reviewed_at": close_dt,
        "notes": f"{payload.get('notes') or ''}\n{notes_suffix}".strip(),
    }
    exit_price = _safe_float(exit_snapshot.get("exit_price"))
    if exit_snapshot.get("priced") and exit_price is not None:
        contracts = max(int(payload.get("contracts") or 1), 1)
        source_pick = payload.get("source_pick_snapshot") or {}
        fee_sides = 2 if str(source_pick.get("strategy_type") or "").lower() == "vertical_spread" else 1
        entry_fee = _safe_float(payload.get("entry_fee_total_usd"))
        if entry_fee is None:
            entry_fee = commission_total_usd(contracts=contracts, sides=fee_sides)
        exit_fee = commission_total_usd(contracts=contracts, sides=fee_sides)
        pnl = option_pnl_snapshot(
            entry_execution_price=payload.get("entry_execution_price") or payload["entry_option_price"],
            exit_execution_price=exit_price,
            contracts=contracts,
            entry_fee_total_usd=entry_fee,
            exit_fee_total_usd=exit_fee,
        )
        updates.update(
            {
                "exit_option_price": exit_price,
                "exit_execution_price": exit_price,
                "exit_execution_basis": exit_snapshot.get("exit_execution_basis"),
                "last_option_price": exit_price,
                "last_pnl_pct": pnl.get("gross_pnl_pct"),
                "gross_pnl_pct": pnl.get("gross_pnl_pct"),
                "net_pnl_pct": pnl.get("net_pnl_pct"),
                "gross_pnl_usd": pnl.get("gross_pnl_usd"),
                "net_pnl_usd": pnl.get("net_pnl_usd"),
                "fee_total_usd": pnl.get("fee_total_usd"),
                "peak_pnl_pct": max(_safe_float(pnl.get("gross_pnl_pct")) or 0.0, 0.0),
            }
        )
    else:
        updates["last_recommendation_reason"] = (
            f"{close_reason}; trusted historical exit quote was unavailable, "
            "so no exit P&L was assigned."
        )
        updates["notes"] = (
            f"{updates['notes']}\nTrusted historical exit quote was unavailable for one or both "
            "spread legs, so this closed migration row is lifecycle-only and has no assigned P&L."
        )
    return updates


def _source_snapshot(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _existing_positions_by_signature(repository: Any) -> dict[str, dict[str, Any]]:
    existing: dict[str, dict[str, Any]] = {}
    for position in repository.list_positions(None) or []:
        source = _source_snapshot(position.get("source_pick_snapshot"))
        signature = str(source.get("backfill_signature") or "").strip()
        if signature:
            existing[signature] = dict(position)
    return existing


def _backup_positions_snapshot(repository: Any, *, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = ROOT / "data" / f"tracked_positions.{label}-{stamp}.json"
    backup_path.write_text(
        json.dumps(repository.list_positions(None), indent=2, default=str),
        encoding="utf-8",
    )
    return backup_path


def _update_log_links(
    *,
    signature_to_position: dict[str, dict[str, Any]],
    reviewed_positions: dict[int, dict[str, Any]],
    apply: bool,
) -> dict[str, int]:
    updated_counts: Counter[str] = Counter()
    for path, label in ((SCAN_LOG, "scan"), (FILL_ATTEMPT_LOG, "fill_attempt")):
        rows = _jsonl_rows(path)
        changed = False
        for row in rows:
            if row.get("backfill_audit_id") != AUDIT_ID:
                continue
            signature = str(row.get("backfill_signature") or "").strip()
            position = signature_to_position.get(signature)
            if not position or position.get("id") is None:
                continue
            position_id = int(position["id"])
            reviewed = reviewed_positions.get(position_id, position)
            status = str(reviewed.get("status") or position.get("status") or "").strip()
            before = json.dumps(row, sort_keys=True, default=str)
            row["auto_track_position_id"] = position_id
            row["tracked_position_id"] = position_id
            row["position_migration_id"] = MIGRATION_ID
            row["position_migrated_at_utc"] = row.get("position_migrated_at_utc") or _utc_now_iso()
            if label == "fill_attempt":
                row["fill_status"] = "auto_tracked"
                row["fill_outcome"] = "paper_fill_recorded"
                row["fill_outcome_reason"] = "historical_backfill_position_migrated"
                row["filled"] = True
                row["review_status"] = status or "open"
                row["reviewed_at"] = reviewed.get("last_reviewed_at") or reviewed.get("updated_at")
                row["close_review_status"] = reviewed.get("exit_reason") if status == "closed" else None
                row["close_marked_at"] = reviewed.get("closed_at") if status == "closed" else None
            after = json.dumps(row, sort_keys=True, default=str)
            if after != before:
                changed = True
                updated_counts[f"{label}_rows_updated"] += 1
        if changed and apply:
            _write_jsonl(path, rows)
    return dict(updated_counts)


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    load_local_env(ROOT)
    os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(Path(args.historical_db_path))
    source_labels = [item.strip() for item in str(args.source_labels or "").split(",") if item.strip()]

    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))

    scan_rows = [
        row
        for row in _jsonl_rows(SCAN_LOG)
        if row.get("backfill_audit_id") == args.audit_id
        and str(row.get("playbook_id") or "").strip() == args.playbook_id
    ]
    as_of = _parse_date(args.as_of_date) if args.as_of_date else datetime.now(ET).date()
    store = HistoricalOptionsStore(args.historical_db_path)
    existing = _existing_positions_by_signature(repository)

    backup_path = None
    if args.apply:
        backup_path = _backup_positions_snapshot(repository, label="pre-main-lane-zero-pick-migration")

    created_open_ids: list[int] = []
    signature_to_position: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    created_positions: list[dict[str, Any]] = []

    for pick in scan_rows:
        signature = str(pick.get("backfill_signature") or "").strip()
        if not signature:
            counters["skipped_missing_signature"] += 1
            skipped.append({"ticker": pick.get("ticker"), "scan_date": pick.get("scan_date"), "reason": "missing_signature"})
            continue

        if signature in existing:
            counters["duplicate_existing_position"] += 1
            signature_to_position[signature] = existing[signature]
            continue

        fill_price = _pick_fill_price(pick)
        if fill_price is None:
            counters["skipped_missing_fill_price"] += 1
            skipped.append({"signature": signature, "reason": "missing_fill_price"})
            continue

        lifecycle = _lifecycle_for_pick(pick, as_of=as_of)
        scan_date = str(pick.get("scan_date") or lifecycle["entry_date"])
        source_pick = copy.deepcopy(pick)
        source_pick["source_scan_run_id"] = source_pick.get("source_scan_run_id") or f"{args.audit_id}:{scan_date}"
        source_pick["source_scan_event_key"] = source_pick.get("source_scan_event_key") or signature
        source_pick["source_scan_recorded_at_utc"] = (
            source_pick.get("source_scan_recorded_at_utc")
            or source_pick.get("quote_time_utc")
            or source_pick.get("logged_at")
        )
        if source_pick.get("strike") is None and source_pick.get("long_strike") is not None:
            source_pick["strike"] = source_pick.get("long_strike")
        if not source_pick.get("direction") and source_pick.get("type"):
            source_pick["direction"] = source_pick.get("type")
        if not source_pick.get("type") and source_pick.get("direction"):
            source_pick["type"] = source_pick.get("direction")
        if source_pick.get("stock_price") is None and source_pick.get("underlying_price") is not None:
            source_pick["stock_price"] = source_pick.get("underlying_price")
        source_pick["position_migration_id"] = MIGRATION_ID
        source_pick["historical_position_lifecycle"] = lifecycle
        source_pick["historical_position_migration_as_of"] = as_of.isoformat()

        notes = (
            f"Historical paper position migrated from zero-pick current-algorithm audit {args.audit_id} "
            f"for {scan_date}. Research/backfill tracking only; not live-production proof."
        )
        try:
            payload = build_position_payload(
                scan_pick=source_pick,
                fill_price=fill_price,
                contracts=int(args.contracts),
                filled_at=_filled_at(pick),
                notes=notes,
                require_proof_eligible=False,
                require_resolved_contract=True,
                preserve_fill_price=True,
            )
        except Exception as exc:
            counters["skipped_payload_error"] += 1
            skipped.append({"signature": signature, "reason": f"payload_error: {exc}"})
            continue

        if lifecycle["status_at_migration"] == "closed":
            close_date = _parse_date(lifecycle["scheduled_close_date"])
            exit_snapshot = _spread_exit_snapshot(
                pick,
                close_date=close_date,
                store=store,
                source_labels=source_labels,
                requested_pricing_lane=args.pricing_lane,
                trusted_only=bool(args.trusted_only),
            )
            payload["source_pick_snapshot"]["historical_position_exit_snapshot"] = exit_snapshot
            payload.update(
                _closed_payload_updates(
                    payload,
                    close_dt=_close_datetime(close_date),
                    close_reason=str(lifecycle["scheduled_close_reason"]),
                    exit_snapshot=exit_snapshot,
                )
            )
            if exit_snapshot.get("priced"):
                counters["created_closed_priced" if args.apply else "would_create_closed_priced"] += 1
            else:
                counters["created_closed_unpriced" if args.apply else "would_create_closed_unpriced"] += 1
        else:
            payload["source_pick_snapshot"]["historical_position_exit_snapshot"] = None
            counters["created_open" if args.apply else "would_create_open"] += 1

        if args.apply:
            created = repository.create_position(payload)
            created_positions.append(created)
            signature_to_position[signature] = created
            if created.get("status") == "open" and created.get("id") is not None:
                created_open_ids.append(int(created["id"]))
        else:
            signature_to_position[signature] = {"id": None, "status": payload.get("status"), "source_pick_snapshot": payload.get("source_pick_snapshot")}

    reviewed_positions: dict[int, dict[str, Any]] = {}
    review_error = None
    if args.apply and created_open_ids and not args.skip_open_review:
        try:
            for position in review_open_positions(repository, position_ids=created_open_ids) or []:
                if position and position.get("id") is not None:
                    reviewed_positions[int(position["id"])] = dict(position)
            counters["reviewed_new_open_positions"] = len(reviewed_positions)
            counters["review_closed_new_open_positions"] = sum(
                1 for position in reviewed_positions.values() if position.get("status") == "closed"
            )
        except Exception as exc:
            review_error = str(exc)

    if args.apply:
        refreshed_existing = _existing_positions_by_signature(repository)
        signature_to_position.update(
            {
                signature: refreshed_existing[signature]
                for signature in signature_to_position
                if signature in refreshed_existing
            }
        )

    log_update_counts = _update_log_links(
        signature_to_position=signature_to_position,
        reviewed_positions=reviewed_positions,
        apply=bool(args.apply),
    )
    counters.update(log_update_counts)

    final_positions = [
        position
        for position in (repository.list_positions(None) or [])
        if _source_snapshot(position.get("source_pick_snapshot")).get("backfill_audit_id") == args.audit_id
    ]
    final_by_status = Counter(str(position.get("status") or "unknown") for position in final_positions)
    final_by_exit_reason = Counter(
        str(position.get("exit_reason") or "open")
        for position in final_positions
    )

    report = {
        "migration_id": MIGRATION_ID,
        "audit_id": args.audit_id,
        "apply": bool(args.apply),
        "as_of_date": as_of.isoformat(),
        "scan_rows_seen": len(scan_rows),
        "created_position_count": len(created_positions),
        "created_open_ids": created_open_ids,
        "created_position_ids": [int(position["id"]) for position in created_positions if position.get("id") is not None],
        "summary": dict(counters),
        "final_audit_position_count": len(final_positions),
        "final_audit_positions_by_status": dict(final_by_status),
        "final_audit_positions_by_exit_reason": dict(final_by_exit_reason),
        "skipped": skipped,
        "review_error": review_error,
        "backup_path": str(backup_path) if backup_path else None,
        "source_labels": source_labels,
        "historical_options_db": str(Path(args.historical_db_path)),
        "generated_at_utc": _utc_now_iso(),
    }
    if args.apply:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_LATEST.with_name(f"main_lane_zero_pick_position_migration_{stamp}.json")
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        REPORT_LATEST.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["report_path"] = str(report_path)
        REPORT_LATEST.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate zero-pick main-lane audit rows into historical paper tracked positions."
    )
    parser.add_argument("--apply", action="store_true", help="Create positions and update log links.")
    parser.add_argument("--audit-id", default=AUDIT_ID)
    parser.add_argument("--playbook-id", default=PLAYBOOK_ID)
    parser.add_argument("--as-of-date", default=datetime.now(ET).date().isoformat())
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--historical-db-path", default=str(DEFAULT_HISTORICAL_OPTIONS_DB))
    parser.add_argument("--source-labels", default=",".join(DEFAULT_SOURCE_LABELS))
    parser.add_argument("--pricing-lane", default="pessimistic", choices=["pessimistic", "mid"])
    parser.add_argument("--trusted-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-open-review", action="store_true")
    return parser.parse_args()


def main() -> int:
    report = migrate(parse_args())
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
