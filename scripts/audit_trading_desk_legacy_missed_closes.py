from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from local_env import load_local_env
from positions_repository import create_positions_repository
from scripts.analyze_trading_desk_profitability_guardrails import canonical_lane, pnl_pct
from scripts.audit_trading_desk_negative_trade_decisions import _review_is_executable, _review_pnl
from scripts.replay_trading_desk_exit_policies import (
    LEGACY_MISSED_CLOSE_IDS,
    POLICIES,
    _days_held,
    _load_reviews,
    _parse_datetime,
    executable_reviews,
    simulate_exit_policy,
)


DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "trading-desk-legacy-missed-close-audit-2026-06-01.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _current_policy():
    for policy in POLICIES:
        if policy.policy_id == "current_policy_replay":
            return policy
    return POLICIES[0]


def _review_summary(position: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any] | None:
    if not review:
        return None
    return {
        "reviewed_at": str(review.get("reviewed_at")),
        "days_held": _days_held(position, review),
        "pnl_pct": _review_pnl(review),
        "recommendation": review.get("recommendation"),
        "reason": review.get("reason"),
        "exit_execution_price": review.get("exit_execution_price"),
        "exit_execution_basis": review.get("exit_execution_basis"),
    }


def _first_executable_sell(position: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any] | None:
    for review in executable_reviews(reviews):
        if str(review.get("recommendation") or "").upper() == "SELL":
            return review
    return None


def _first_positive_executable_sell(position: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any] | None:
    for review in executable_reviews(reviews):
        pnl = _review_pnl(review)
        if str(review.get("recommendation") or "").upper() == "SELL" and pnl is not None and pnl >= 0:
            return review
    return None


def _diagnosis(position: dict[str, Any], current_policy_result: dict[str, Any]) -> str:
    if not position:
        return "missing_position"
    if current_policy_result.get("status") == "unreplayable":
        return "no_executable_review_timeline"
    if current_policy_result.get("status") != "closed":
        return "current_policy_would_not_have_closed"
    closed_at = _parse_datetime(position.get("closed_at"))
    simulated_at = _parse_datetime(current_policy_result.get("reviewed_at"))
    actual_pnl = pnl_pct(position)
    simulated_pnl = _review_pnl(current_policy_result) if "recommendation" in current_policy_result else current_policy_result.get("pnl_pct")
    if closed_at is None:
        return "still_open_but_policy_would_close"
    if simulated_at is not None and simulated_at < closed_at:
        return "stale_or_non_autoclosing_review_path"
    if simulated_pnl is not None and actual_pnl is not None and float(simulated_pnl) > float(actual_pnl):
        return "later_close_worse_than_policy_replay"
    return "historical_only_no_current_action"


def _target_row(position: dict[str, Any] | None, reviews: list[dict[str, Any]]) -> dict[str, Any]:
    if not position:
        return {
            "trade_id": None,
            "diagnosis": "missing_position",
            "review_count": len(reviews),
        }
    current_policy_result = simulate_exit_policy(position, reviews, _current_policy())
    first_sell = _first_executable_sell(position, reviews)
    first_positive_sell = _first_positive_executable_sell(position, reviews)
    return {
        "trade_id": position.get("id"),
        "ticker": position.get("ticker"),
        "lane": canonical_lane(position),
        "status": position.get("status"),
        "filled_at": position.get("filled_at"),
        "closed_at": position.get("closed_at"),
        "exit_reason": position.get("exit_reason"),
        "final_pnl_pct": pnl_pct(position),
        "time_exit_day": position.get("time_exit_day"),
        "review_count": len(reviews),
        "executable_review_count": len(executable_reviews(reviews)),
        "first_executable_sell": _review_summary(position, first_sell),
        "first_positive_executable_sell": _review_summary(position, first_positive_sell),
        "current_policy_replay": current_policy_result,
        "diagnosis": _diagnosis(position, current_policy_result),
    }


def build_report(
    positions: list[dict[str, Any]],
    *,
    reviews_by_position: dict[int, list[dict[str, Any]]],
    target_ids: set[int] | None = None,
) -> dict[str, Any]:
    target_ids = target_ids or set(LEGACY_MISSED_CLOSE_IDS)
    by_id = {int(position.get("id") or 0): position for position in positions}
    rows = []
    for target_id in sorted(target_ids):
        rows.append(_target_row(by_id.get(target_id), reviews_by_position.get(target_id, [])))
    diagnoses: dict[str, int] = {}
    for row in rows:
        diagnosis = str(row.get("diagnosis") or "unknown")
        diagnoses[diagnosis] = diagnoses.get(diagnosis, 0) + 1
    current_bug_count = diagnoses.get("still_open_but_policy_would_close", 0)
    stale_count = diagnoses.get("stale_or_non_autoclosing_review_path", 0)
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_legacy_missed_close_audit",
        "evidence_standard": "stored executable review rows only; read-only audit; no position state is changed",
        "target_ids": sorted(target_ids),
        "summary": {
            "target_count": len(rows),
            "diagnosis_counts": diagnoses,
            "current_action_required_count": current_bug_count,
            "historical_stale_path_count": stale_count,
            "recommendation": (
                "fix_current_auto_close_path"
                if current_bug_count
                else "no_broad_exit_policy_change; preserve as historical stale-policy diagnostic"
                if stale_count
                else "no_current_action_from_targets"
            ),
        },
        "rows": rows,
    }


def load_current_report(target_ids: set[int] | None = None) -> dict[str, Any]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    return build_report(
        repository.list_positions("all"),
        reviews_by_position=_load_reviews(repository),
        target_ids=target_ids,
    )


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Trading Desk Legacy Missed-Close Audit - 2026-06-01",
        "",
        "This is a read-only audit of legacy rows that had stored executable SELL evidence before their final negative closed result. It does not mutate tracked positions.",
        "",
        "## Summary",
        "",
        f"- Recommendation: `{report['summary']['recommendation']}`",
        f"- Diagnosis counts: `{report['summary']['diagnosis_counts']}`",
        f"- Current action required count: `{report['summary']['current_action_required_count']}`",
        "",
        "## Targets",
        "",
        "| Trade | Ticker | Lane | Final P&L | Actual Close | Current Policy Replay | Diagnosis |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for row in report.get("rows") or []:
        policy = row.get("current_policy_replay") or {}
        policy_text = (
            f"{policy.get('reason')} at {policy.get('reviewed_at')} ({policy.get('pnl_pct')}%)"
            if policy
            else ""
        )
        lines.append(
            f"| {row.get('trade_id')} | {row.get('ticker')} | `{row.get('lane')}` | "
            f"{row.get('final_pnl_pct')}% | {row.get('closed_at')} / {row.get('exit_reason')} | "
            f"{policy_text} | `{row.get('diagnosis')}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Rows diagnosed as `stale_or_non_autoclosing_review_path` are historical policy/application evidence, not proof that the current review endpoint is failing. The current review service now auto-closes open rows when a saved executable review recommends `SELL`, so a current bug claim requires a still-open row with an executable SELL that does not close.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"trading_desk_legacy_missed_close_audit_{stamp}.json"
    latest_json = output_dir / "trading_desk_legacy_missed_close_audit_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    doc_path.write_text(markdown_report(report), encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json), "markdown": str(doc_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit legacy Trading Desk rows with missed executable close evidence.")
    parser.add_argument("--position-id", action="append", type=int, help="Position id to audit. Repeat for multiple ids.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    target_ids = set(args.position_id or []) or None
    report = load_current_report(target_ids=target_ids)
    payload: dict[str, Any] = {"report": report}
    if not args.no_write:
        payload["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps({"summary": report["summary"], "target_ids": report["target_ids"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
