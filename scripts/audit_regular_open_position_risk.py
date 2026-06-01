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


def build_report(rows: list[dict[str, Any]], *, stale_hours: float = 24.0) -> dict[str, Any]:
    now = datetime.now(UTC)
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
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_open_positions_read_only",
        "read_only": True,
        "stale_review_hours": stale_hours,
        "summary": _summarize(open_rows),
        "by_lane": _group_counts(open_rows, canonical_lane),
        "by_record_class": _group_counts(open_rows, _record_class),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "actionable_position_ids": [row.get("id") for row in actionable],
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of open regular supervised tracked-position risk."
    )
    parser.add_argument("--stale-hours", type=float, default=24.0)
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    args = parser.parse_args(argv)
    report = build_report(load_positions(), stale_hours=args.stale_hours)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "summary": report["summary"],
                    "evidence_counts": report["evidence_counts"],
                    "action_counts": report["action_counts"],
                    "actionable_position_ids": report["actionable_position_ids"],
                    "top_negative_open_positions": report["top_negative_open_positions"][:10],
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
