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

from scripts.analyze_trading_desk_profitability_guardrails import canonical_lane, load_positions, pnl_pct
from scripts.audit_trading_desk_negative_trade_decisions import _record_class, _review_is_executable, _review_pnl


DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
OPEN_RISK_GOVERNOR_PASS = "open_risk_governor_pass"
OPEN_RISK_GOVERNOR_BLOCKED = "open_risk_governor_blocked"
REGULAR_SUPERVISED_LANES = {
    "short_term",
    "swing",
    "bullish_momentum",
    "bullish_pullback_observation",
    "tracked_winner_primary",
    "tracked_winner_observation",
    "volatility_expansion_observation",
    "range_breakout_observation",
}


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return _utc_iso(datetime.now(UTC))


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


def _as_of_datetime(value: Any | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid --as-of timestamp: {value!r}")
    return parsed


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


def _evidence_bucket(row: dict[str, Any], *, now: datetime, stale_hours: float) -> str:
    review = _latest_review(row)
    if review is None:
        return "missing_review"
    age_hours = _review_age_hours(review, now=now)
    stale = age_hours is not None and age_hours > stale_hours
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
    if value is not None and stop_loss_pct is not None and value <= -abs(stop_loss_pct):
        return "below_configured_stop_mark"
    if value is not None and value < 0:
        return "negative_mark_hold_or_unknown"
    return "hold_or_positive"


def _metric(review: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(review, dict):
        return None
    metrics = review.get("metrics_snapshot")
    if isinstance(metrics, dict) and key in metrics:
        return metrics.get(key)
    return review.get(key)


def _actionable_next_step(action_bucket: str) -> str:
    if action_bucket == "stored_executable_sell":
        return "state_changing_review_should_auto_close_or_manual_close_with_executable_quote"
    if action_bucket == "stored_non_executable_sell":
        return "do_not_auto_close_from_display_only_mark_rerun_explicit_review_during_fresh_executable_quote_window"
    if action_bucket == "below_configured_stop_mark":
        return "do_not_close_from_mark_alone_get_executable_review_quote_before_exit"
    return "monitor"


def _is_live_exact_row(row: dict[str, Any]) -> bool:
    return _record_class(row) == "live_exact_tracked"


def _live_exact_negative_is_resolved_hold(row: dict[str, Any], *, now: datetime, stale_hours: float) -> bool:
    review = _latest_review(row)
    if not isinstance(review, dict):
        return False
    return bool(
        _action_bucket(row) == "negative_mark_hold_or_unknown"
        and _evidence_bucket(row, now=now, stale_hours=stale_hours) == "fresh_executable_review"
        and str(review.get("recommendation") or row.get("last_recommendation") or "").strip().upper() == "HOLD"
        and _review_is_executable(review)
        and bool(_metric(review, "price_trigger_ok"))
    )


def _actionable_position_detail(row: dict[str, Any], *, now: datetime, stale_hours: float) -> dict[str, Any]:
    review = _latest_review(row)
    action_bucket = _action_bucket(row)
    warnings = list(review.get("warnings") or []) if isinstance(review, dict) else []
    return {
        "id": row.get("id"),
        "ticker": row.get("ticker"),
        "lane": canonical_lane(row),
        "record_class": _record_class(row),
        "status": row.get("status"),
        "action_bucket": action_bucket,
        "evidence_bucket": _evidence_bucket(row, now=now, stale_hours=stale_hours),
        "last_reviewed_at": row.get("last_reviewed_at") or (review or {}).get("reviewed_at"),
        "recommendation": (review or {}).get("recommendation") or row.get("last_recommendation"),
        "reason": (review or {}).get("reason"),
        "pricing_source": (review or {}).get("pricing_source"),
        "pricing_state": (review or {}).get("pricing_state") or _metric(review, "pricing_state"),
        "current_option_price": _safe_float((review or {}).get("current_option_price")),
        "current_pnl_pct": _review_pnl(review or {}),
        "mark_pnl_pct": pnl_pct(row),
        "exit_execution_price": _safe_float((review or {}).get("exit_execution_price")),
        "exit_execution_basis": (review or {}).get("exit_execution_basis"),
        "price_trigger_ok": bool(_metric(review, "price_trigger_ok")),
        "warning_count": len(warnings),
        "first_warning": warnings[0] if warnings else None,
        "next_safe_action": _actionable_next_step(action_bucket),
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


def _build_open_risk_governor(
    open_rows: list[dict[str, Any]],
    *,
    now: datetime,
    stale_hours: float,
) -> dict[str, Any]:
    live_exact_rows = [row for row in open_rows if _is_live_exact_row(row)]
    live_exact_negative = [row for row in live_exact_rows if (pnl_pct(row) is not None and pnl_pct(row) < 0)]
    live_exact_negative_resolved_hold = [
        row for row in live_exact_negative if _live_exact_negative_is_resolved_hold(row, now=now, stale_hours=stale_hours)
    ]
    live_exact_negative_unresolved = [
        row for row in live_exact_negative if row not in live_exact_negative_resolved_hold
    ]
    live_exact_close_ready = [
        row for row in live_exact_rows if _action_bucket(row) == "stored_executable_sell"
    ]
    live_exact_review_blocked = [
        row
        for row in live_exact_rows
        if _evidence_bucket(row, now=now, stale_hours=stale_hours)
        in {
            "missing_review",
            "stale_executable_review",
            "stale_mark_or_non_executable_review",
            "stale_unpriced_review",
            "fresh_mark_or_non_executable_review",
            "fresh_unpriced_review",
        }
    ]
    blockers: list[str] = []
    if live_exact_negative_unresolved:
        blockers.append("live_exact_negative_open_risk")
    if live_exact_close_ready:
        blockers.append("live_exact_executable_close_ready")
    if live_exact_review_blocked:
        blockers.append("live_exact_review_stale_missing_or_non_executable")
    status = OPEN_RISK_GOVERNOR_BLOCKED if blockers else OPEN_RISK_GOVERNOR_PASS
    details = [
        _actionable_position_detail(row, now=now, stale_hours=stale_hours)
        for row in sorted(
            live_exact_negative_unresolved + live_exact_close_ready + live_exact_review_blocked,
            key=lambda item: (
                _safe_float(item.get("id")) or 0.0,
                item.get("ticker") or "",
            ),
        )
    ]
    return {
        "status": status,
        "live_entry_allowed": status == OPEN_RISK_GOVERNOR_PASS,
        "blockers": blockers,
        "live_exact_open_count": len(live_exact_rows),
        "live_exact_negative_count": len(live_exact_negative),
        "live_exact_negative_resolved_hold_count": len(live_exact_negative_resolved_hold),
        "live_exact_negative_unresolved_count": len(live_exact_negative_unresolved),
        "live_exact_executable_close_ready_count": len(live_exact_close_ready),
        "live_exact_review_blocked_count": len(live_exact_review_blocked),
        "live_exact_review_blocked_ids": [row.get("id") for row in live_exact_review_blocked],
        "live_exact_negative_ids": [row.get("id") for row in live_exact_negative],
        "live_exact_negative_resolved_hold_ids": [row.get("id") for row in live_exact_negative_resolved_hold],
        "live_exact_negative_unresolved_ids": [row.get("id") for row in live_exact_negative_unresolved],
        "live_exact_executable_close_ready_ids": [row.get("id") for row in live_exact_close_ready],
        "governor_details": details,
        "next_safe_actions": [
            "do_not_open_new_scanner_origin_rows_until_governor_passes"
            if status == OPEN_RISK_GOVERNOR_BLOCKED
            else "open_risk_governor_clear_for_promotion_checks",
            "refresh_open_position_reviews_with_live_executable_quotes",
            "resolve_executable_sell_or_negative_live_exact_rows_before_live_validation",
        ]
        if status == OPEN_RISK_GOVERNOR_BLOCKED
        else ["continue_monitoring_open_risk_before_each_promotion_readback"],
        "read_only": True,
        "live_policy_change": False,
    }


def build_report(
    rows: list[dict[str, Any]],
    *,
    stale_hours: float = 24.0,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    now = _as_of_datetime(as_of)
    open_rows = [
        row
        for row in rows
        if str(row.get("status") or "").strip().lower() == "open"
        and canonical_lane(row) in REGULAR_SUPERVISED_LANES
    ]
    evidence_counts = Counter(_evidence_bucket(row, now=now, stale_hours=stale_hours) for row in open_rows)
    action_counts = Counter(_action_bucket(row) for row in open_rows)
    actionable = [
        row
        for row in open_rows
        if _action_bucket(row) in {"stored_executable_sell", "stored_non_executable_sell", "below_configured_stop_mark"}
    ]
    negative = [row for row in open_rows if (pnl_pct(row) is not None and pnl_pct(row) < 0)]
    top_negative = sorted(negative, key=lambda row: pnl_pct(row) or 0.0)[:20]
    governor = _build_open_risk_governor(open_rows, now=now, stale_hours=stale_hours)
    return {
        "generated_at_utc": _utc_iso(now),
        "scope": "regular_supervised_open_positions_read_only",
        "read_only": True,
        "stale_review_hours": stale_hours,
        "summary": _summarize(open_rows),
        "by_lane": _group_counts(open_rows, canonical_lane),
        "by_record_class": _group_counts(open_rows, _record_class),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "actionable_position_ids": [row.get("id") for row in actionable],
        "open_risk_governor": governor,
        "actionable_positions": [
            _actionable_position_detail(row, now=now, stale_hours=stale_hours)
            for row in actionable
        ],
        "top_negative_open_positions": [
            {
                "id": row.get("id"),
                "ticker": row.get("ticker"),
                "lane": canonical_lane(row),
                "record_class": _record_class(row),
                "pnl_pct": round(pnl_pct(row) or 0.0, 2),
                "evidence_bucket": _evidence_bucket(row, now=now, stale_hours=stale_hours),
                "action_bucket": _action_bucket(row),
                "last_reviewed_at": row.get("last_reviewed_at"),
                "latest_recommendation": row.get("last_recommendation"),
            }
            for row in top_negative
        ],
    }


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_open_position_risk_{stamp}.json"
    latest_json = output_dir / "regular_open_position_risk_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of open regular supervised tracked-position risk."
    )
    parser.add_argument("--stale-hours", type=float, default=24.0)
    parser.add_argument("--as-of", help="ISO timestamp used for stale-review calculations.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Run without writing latest JSON artifacts.")
    args = parser.parse_args(argv)
    report = build_report(load_positions(), stale_hours=args.stale_hours, as_of=args.as_of)
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
                    "evidence_counts": report["evidence_counts"],
                    "action_counts": report["action_counts"],
                    "actionable_position_ids": report["actionable_position_ids"],
                    "open_risk_governor": report["open_risk_governor"],
                    "actionable_positions": report["actionable_positions"],
                    "top_negative_open_positions": report["top_negative_open_positions"][:10],
                    "artifacts": artifacts,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
