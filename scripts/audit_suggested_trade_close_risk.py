from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from suggested_trades_repository import SQLiteSuggestedTradesRepository

from scripts.analyze_trading_desk_profitability_guardrails import canonical_lane, pnl_pct
from scripts.audit_trading_desk_negative_trade_decisions import _review_is_executable, _review_pnl


DEFAULT_DB_PATH = ROOT / "chat_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
TRIGGER_BUCKETS = {
    "stored_executable_sell",
    "stored_non_executable_sell",
    "below_configured_stop_mark",
    "above_configured_target_mark",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _source(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("source_pick_snapshot")
    return value if isinstance(value, dict) else {}


def _latest_review(row: dict[str, Any]) -> dict[str, Any] | None:
    review = row.get("latest_review")
    return review if isinstance(review, dict) else None


def _review_age_hours(review: dict[str, Any] | None, *, now: datetime) -> float | None:
    if review is None:
        return None
    reviewed_at = _parse_datetime(review.get("reviewed_at"))
    if reviewed_at is None:
        return None
    return max((now - reviewed_at).total_seconds() / 3600.0, 0.0)


def _metric(review: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(review, dict):
        return None
    metrics = review.get("metrics_snapshot")
    if isinstance(metrics, dict) and key in metrics:
        return metrics.get(key)
    return review.get(key)


def _record_class(row: dict[str, Any]) -> str:
    snap = _source(row)
    audit_id = str(snap.get("backfill_audit_id") or "").strip()
    if audit_id == "all_lanes_zero_pick_current_algo_v1":
        return "all_lanes_zero_pick_suggested_backfill"
    if audit_id == "main_lane_zero_pick_current_algo_v1":
        return "main_zero_pick_suggested_backfill"
    if audit_id:
        return "suggested_research_backfill"
    return "suggested_trade"


def _evidence_bucket(row: dict[str, Any], *, now: datetime, stale_hours: float) -> str:
    review = _latest_review(row)
    if review is None:
        return "missing_review"
    age_hours = _review_age_hours(review, now=now)
    stale = age_hours is None or age_hours > stale_hours
    if _review_is_executable(review):
        return "stale_executable_review" if stale else "fresh_executable_review"
    if _review_pnl(review) is not None:
        return "stale_mark_or_non_executable_review" if stale else "fresh_mark_or_non_executable_review"
    return "stale_unpriced_review" if stale else "fresh_unpriced_review"


def _action_bucket(row: dict[str, Any]) -> str:
    review = _latest_review(row)
    if review is None:
        return "no_stored_review"
    recommendation = str(review.get("recommendation") or row.get("last_recommendation") or "").upper()
    if recommendation == "SELL" and _review_is_executable(review):
        return "stored_executable_sell"
    if recommendation == "SELL":
        return "stored_non_executable_sell"
    value = pnl_pct(row)
    stop_loss_pct = _safe_float(row.get("stop_loss_pct"))
    profit_target_pct = _safe_float(row.get("profit_target_pct"))
    if value is not None and stop_loss_pct is not None and value <= -abs(stop_loss_pct):
        return "below_configured_stop_mark"
    if value is not None and profit_target_pct is not None and value >= abs(profit_target_pct):
        return "above_configured_target_mark"
    if value is not None and value < 0:
        return "negative_mark_hold_or_unknown"
    return "hold_or_positive"


def _next_safe_action(row: dict[str, Any], *, evidence_bucket: str, action_bucket: str) -> str:
    if action_bucket == "stored_executable_sell":
        return "explicit_review_should_auto_close_or_manual_close_with_executable_quote"
    if action_bucket == "stored_non_executable_sell":
        return "do_not_close_suggested_trade_from_non_executable_mark_rerun_explicit_review"
    if action_bucket in {"below_configured_stop_mark", "above_configured_target_mark"}:
        return "do_not_close_from_mark_alone_get_fresh_executable_review_quote"
    if evidence_bucket == "missing_review" or evidence_bucket.startswith("stale_"):
        return "refresh_explicit_suggested_trade_review_before_using_close_or_pnl_state"
    return "monitor"


def _detail(row: dict[str, Any], *, now: datetime, stale_hours: float) -> dict[str, Any]:
    review = _latest_review(row)
    action_bucket = _action_bucket(row)
    evidence_bucket = _evidence_bucket(row, now=now, stale_hours=stale_hours)
    warnings = list(review.get("warnings") or []) if isinstance(review, dict) else []
    return {
        "id": row.get("id"),
        "ticker": row.get("ticker"),
        "lane": canonical_lane(row),
        "record_class": _record_class(row),
        "status": row.get("status"),
        "action_bucket": action_bucket,
        "evidence_bucket": evidence_bucket,
        "last_reviewed_at": row.get("last_reviewed_at") or (review or {}).get("reviewed_at"),
        "recommendation": (review or {}).get("recommendation") or row.get("last_recommendation"),
        "reason": (review or {}).get("reason"),
        "pricing_source": (review or {}).get("pricing_source"),
        "pricing_state": (review or {}).get("pricing_state") or _metric(review, "pricing_state"),
        "current_option_price": _safe_float((review or {}).get("current_option_price")),
        "current_pnl_pct": _review_pnl(review or {}),
        "mark_pnl_pct": pnl_pct(row),
        "stop_loss_pct": _safe_float(row.get("stop_loss_pct")),
        "profit_target_pct": _safe_float(row.get("profit_target_pct")),
        "exit_execution_price": _safe_float((review or {}).get("exit_execution_price")),
        "exit_execution_basis": (review or {}).get("exit_execution_basis"),
        "price_trigger_ok": bool(_metric(review, "price_trigger_ok")),
        "warning_count": len(warnings),
        "first_warning": warnings[0] if warnings else None,
        "next_safe_action": _next_safe_action(
            row,
            evidence_bucket=evidence_bucket,
            action_bucket=action_bucket,
        ),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for value in (pnl_pct(row) for row in rows) if value is not None]
    return {
        "rows": len(rows),
        "priced_or_marked": len(values),
        "negative": sum(1 for value in values if value < 0),
        "positive_or_flat": sum(1 for value in values if value >= 0),
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "median_pnl_pct": round(median(values), 2) if values else None,
    }


def _group_counts(rows: list[dict[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(key_fn(row))].append(row)
    return {key: _summarize(items) for key, items in sorted(grouped.items())}


def load_trades(db_path: Path = DEFAULT_DB_PATH) -> tuple[list[dict[str, Any]], str | None]:
    if not db_path.exists():
        return [], f"Suggested trades DB not found: {db_path}"
    repo = SQLiteSuggestedTradesRepository(str(db_path))
    try:
        return repo.list_positions(None), None
    except Exception as exc:
        return [], str(exc)


def build_report(
    rows: list[dict[str, Any]],
    *,
    stale_hours: float = 24.0,
    now: datetime | None = None,
    db_path: Path | None = None,
    load_error: str | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    open_rows = [row for row in rows if str(row.get("status") or "").strip().lower() == "open"]
    closed_rows = [row for row in rows if str(row.get("status") or "").strip().lower() == "closed"]
    evidence_counts = Counter(_evidence_bucket(row, now=now, stale_hours=stale_hours) for row in open_rows)
    action_counts = Counter(_action_bucket(row) for row in open_rows)
    close_risk_rows = [row for row in open_rows if _action_bucket(row) in TRIGGER_BUCKETS]
    stale_or_missing_rows = [
        row
        for row in open_rows
        if (bucket := _evidence_bucket(row, now=now, stale_hours=stale_hours)) == "missing_review"
        or bucket.startswith("stale_")
    ]
    attention_rows_by_id: dict[Any, dict[str, Any]] = {}
    for row in close_risk_rows + stale_or_missing_rows:
        attention_rows_by_id[row.get("id")] = row
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "suggested_trades_close_risk_read_only",
        "read_only": True,
        "storage_available": load_error is None,
        "db_path": str(db_path) if db_path is not None else None,
        "load_error": load_error,
        "stale_review_hours": stale_hours,
        "summary": _summarize(open_rows),
        "closed_summary": _summarize(closed_rows),
        "by_lane": _group_counts(open_rows, canonical_lane),
        "by_record_class": _group_counts(open_rows, _record_class),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "close_risk_trade_ids": [row.get("id") for row in close_risk_rows],
        "stale_or_missing_review_trade_ids": [row.get("id") for row in stale_or_missing_rows],
        "attention_trade_ids": list(attention_rows_by_id.keys()),
        "attention_trades": [
            _detail(row, now=now, stale_hours=stale_hours)
            for row in attention_rows_by_id.values()
        ],
    }


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"suggested_trade_close_risk_{stamp}.json"
    latest_json = output_dir / "suggested_trade_close_risk_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of suggested-trade close risk and stale review state."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--stale-hours", type=float, default=24.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Run without writing latest JSON artifacts.")
    args = parser.parse_args(argv)
    rows, load_error = load_trades(args.db_path)
    report = build_report(
        rows,
        stale_hours=args.stale_hours,
        db_path=args.db_path,
        load_error=load_error,
    )
    artifacts = None if args.no_write else write_outputs(report, output_dir=args.output_dir)
    if args.json:
        payload: dict[str, Any] = {"report": report}
        if artifacts:
            payload["artifacts"] = artifacts
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "summary": report["summary"],
                    "closed_summary": report["closed_summary"],
                    "evidence_counts": report["evidence_counts"],
                    "action_counts": report["action_counts"],
                    "close_risk_trade_ids": report["close_risk_trade_ids"],
                    "stale_or_missing_review_trade_ids": report["stale_or_missing_review_trade_ids"],
                    "attention_trades": report["attention_trades"],
                    "artifacts": artifacts,
                    "load_error": load_error,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
