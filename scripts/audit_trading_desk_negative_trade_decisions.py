from __future__ import annotations

import argparse
import csv
import json
import math
import os
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

from local_env import load_local_env
from positions_repository import create_positions_repository
from scripts.analyze_trading_desk_profitability_guardrails import (
    build_probe_definitions,
    canonical_lane,
    debit_pct_of_width,
    fill_degradation_vs_mid_pct,
    load_bullish_pullback_keep_tickers,
    pnl_pct,
    signal_ret5,
    source,
    worst_leg_bid_ask_spread_pct,
)


DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "trading-desk-negative-trade-decision-audit-2026-05-31.md"
DEFAULT_CSV = DEFAULT_OUTPUT_DIR / "trading_desk_negative_trade_decision_audit_latest.csv"
DEFAULT_JSON = DEFAULT_OUTPUT_DIR / "trading_desk_negative_trade_decision_audit_latest.json"
REPAIR_LANES = {"short_term", "swing", "bullish_momentum", "bullish_pullback_observation"}
LEGACY_MISSED_CLOSE_IDS = {26, 39, 44}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalized_dt(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _review_pnl(review: dict[str, Any]) -> float | None:
    for key in ("net_pnl_pct", "gross_pnl_pct", "current_pnl_pct"):
        value = safe_float(review.get(key))
        if value is not None:
            return value
    metrics = _as_mapping(review.get("metrics_snapshot"))
    for key in ("net_pnl_pct", "gross_pnl_pct", "current_pnl_pct"):
        value = safe_float(metrics.get(key))
        if value is not None:
            return value
    return None


def _review_is_executable(review: dict[str, Any]) -> bool:
    exit_price = safe_float(review.get("exit_execution_price"))
    if exit_price is None:
        return False
    basis = str(review.get("exit_execution_basis") or "").strip().lower()
    metrics = _as_mapping(review.get("metrics_snapshot"))
    return bool(metrics.get("price_trigger_ok")) or basis not in {"", "last", "last_price", "midpoint_mark"}


def _record_class(row: dict[str, Any]) -> str:
    snap = source(row)
    audit_id = str(snap.get("backfill_audit_id") or "").strip()
    if audit_id == "all_lanes_zero_pick_current_algo_v1":
        return "all_lanes_zero_pick_research_backfill"
    if audit_id == "main_lane_zero_pick_current_algo_v1":
        return "main_zero_pick_research_backfill"
    proof_class = str(row.get("proof_class") or snap.get("proof_class") or "").strip().lower()
    if "live" in proof_class and "exact" in proof_class:
        return "live_exact_tracked"
    if audit_id:
        return "research_backfill"
    return "legacy_or_unknown_tracked"


def evidence_quality(row: dict[str, Any]) -> str:
    snap = source(row)
    record_class = _record_class(row)
    if record_class in {"all_lanes_zero_pick_research_backfill", "main_zero_pick_research_backfill", "research_backfill"}:
        return "limited_research_backfill"
    if not row.get("contract_symbol") and not snap.get("contract_symbol"):
        return "insufficient_missing_contract"
    entry_basis = str(row.get("entry_execution_basis") or snap.get("entry_execution_basis") or "").lower()
    exit_basis = str(row.get("exit_execution_basis") or "").lower()
    candidate_label = str(snap.get("candidate_execution_label") or "").lower()
    exactish = (
        "opra" in candidate_label
        or "ask_bid" in entry_basis
        or "bid_ask" in entry_basis
        or "spread_bid_ask" in exit_basis
        or "exact" in exit_basis
    )
    if exactish and record_class != "legacy_or_unknown_tracked":
        return "trusted_exact_or_live_shadow"
    if exactish:
        return "limited_legacy_exact_like"
    return "insufficient_or_legacy_unclassified"


def _entry_rationale(row: dict[str, Any]) -> str:
    snap = source(row)
    parts = [f"playbook={canonical_lane(row)}"]
    for label, key in (
        ("event", "event_type"),
        ("selection", "selection_source"),
        ("candidate", "candidate_execution_label"),
        ("ev", "ev_pct"),
        ("direction", "direction_score"),
        ("quality", "quality_score"),
        ("tech", "tech_score"),
        ("ret5", "ret5"),
    ):
        value = snap.get(key)
        if value is not None and value != "":
            parts.append(f"{label}={value}")
    debit_pct = debit_pct_of_width(row)
    if debit_pct is not None:
        parts.append(f"debit_width={debit_pct:.1f}%")
    fill_degradation = fill_degradation_vs_mid_pct(row)
    if fill_degradation is not None:
        parts.append(f"fill_degradation={fill_degradation:.1f}%")
    worst_leg = worst_leg_bid_ask_spread_pct(row)
    if worst_leg is not None:
        parts.append(f"worst_leg_spread={worst_leg:.1f}%")
    return "; ".join(parts)


def _analyze_reviews(row: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_reviews = sorted(reviews, key=lambda item: str(item.get("reviewed_at") or ""))
    first_negative = None
    best_executable = None
    best_before_negative = None
    positive_sell_before_final = None
    positive_sell_before_negative = None
    for review in sorted_reviews:
        pnl = _review_pnl(review)
        executable = _review_is_executable(review)
        if pnl is not None and pnl < 0 and first_negative is None:
            first_negative = review
        if executable and pnl is not None:
            if best_executable is None or pnl > float(best_executable["pnl_pct"]):
                best_executable = {"reviewed_at": _normalized_dt(review.get("reviewed_at")), "pnl_pct": pnl}
            if (
                pnl >= 0
                and str(review.get("recommendation") or "").upper() == "SELL"
                and (positive_sell_before_final is None or pnl > float(positive_sell_before_final["pnl_pct"]))
            ):
                positive_sell_before_final = {
                    "reviewed_at": _normalized_dt(review.get("reviewed_at")),
                    "pnl_pct": pnl,
                    "reason": review.get("reason"),
                }
        if first_negative is None and executable and pnl is not None:
            if best_before_negative is None or pnl > float(best_before_negative["pnl_pct"]):
                best_before_negative = {"reviewed_at": _normalized_dt(review.get("reviewed_at")), "pnl_pct": pnl}
            if (
                pnl >= 0
                and str(review.get("recommendation") or "").upper() == "SELL"
                and positive_sell_before_negative is None
            ):
                positive_sell_before_negative = {
                    "reviewed_at": _normalized_dt(review.get("reviewed_at")),
                    "pnl_pct": pnl,
                    "reason": review.get("reason"),
                }
    return {
        "review_count": len(sorted_reviews),
        "first_negative_time": _normalized_dt(first_negative.get("reviewed_at")) if first_negative else None,
        "best_executable_exit": best_executable,
        "best_executable_before_negative": best_before_negative,
        "positive_executable_sell_before_negative": positive_sell_before_negative,
        "positive_executable_sell_before_final_loss": positive_sell_before_final,
    }


def _active_protections(row: dict[str, Any]) -> list[str]:
    lane = canonical_lane(row)
    protections = []
    if row.get("stop_loss_pct") is not None:
        protections.append(f"stop_loss={row.get('stop_loss_pct')}%")
    if row.get("profit_target_pct") is not None:
        protections.append(f"profit_target={row.get('profit_target_pct')}%")
    if row.get("time_exit_day") is not None:
        protections.append(f"time_exit_day={row.get('time_exit_day')}")
    if lane in {"bullish_pullback_observation", "tracked_winner_primary", "tracked_winner_observation"}:
        protections.append("profit_harvest_default")
    return protections


def _failure_category(
    row: dict[str, Any],
    *,
    guardrail_hits: list[str],
    review_audit: dict[str, Any],
) -> str:
    value = pnl_pct(row)
    if value is None or value >= 0:
        return "not_negative"
    quality = evidence_quality(row)
    if quality.startswith("insufficient"):
        return "unknown_insufficient_evidence"
    if guardrail_hits:
        return "entry_guardrail_now_blocks"
    positive_sell = review_audit.get("positive_executable_sell_before_negative")
    best_before = review_audit.get("best_executable_before_negative") or {}
    if positive_sell or safe_float(best_before.get("pnl_pct")) is not None and float(best_before["pnl_pct"]) >= 0:
        return "missed_executable_exit_before_negative"
    if review_audit.get("positive_executable_sell_before_final_loss"):
        return "missed_executable_profit_exit_before_final_loss"
    if int(review_audit.get("review_count") or 0) == 0:
        return "missing_review_timeline"
    if _record_class(row).endswith("research_backfill"):
        return "research_backfill_lane_weakness"
    if fill_degradation_vs_mid_pct(row) is not None or worst_leg_bid_ask_spread_pct(row) is not None:
        return "liquidity_or_execution_risk"
    return "expected_market_risk_or_unclassified"


def _confidence(row: dict[str, Any], review_audit: dict[str, Any]) -> str:
    quality = evidence_quality(row)
    if quality.startswith("trusted") and int(review_audit.get("review_count") or 0) > 0:
        return "high"
    if quality.startswith("limited") and int(review_audit.get("review_count") or 0) > 0:
        return "medium"
    return "low"


def _guardrail_hits(row: dict[str, Any], keep_tickers: set[str]) -> list[str]:
    hits = []
    probes = build_probe_definitions(keep_tickers)
    for probe_id, matcher in probes.items():
        if probe_id == "momentum_chase":
            continue
        try:
            if matcher(row):
                hits.append(probe_id)
        except Exception:
            continue
    return hits


def build_report(
    rows: list[dict[str, Any]],
    *,
    reviews_by_position: dict[int, list[dict[str, Any]]] | None = None,
    keep_tickers: set[str] | None = None,
) -> dict[str, Any]:
    reviews_by_position = reviews_by_position or {}
    keep_tickers = keep_tickers or {"IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
    audited_rows: list[dict[str, Any]] = []
    for row in rows:
        value = pnl_pct(row)
        if value is None or value >= 0:
            continue
        position_id = int(row.get("id") or 0)
        review_audit = _analyze_reviews(row, reviews_by_position.get(position_id, []))
        guardrail_hits = _guardrail_hits(row, keep_tickers)
        missed_exit = review_audit.get("positive_executable_sell_before_negative")
        best_before = review_audit.get("best_executable_before_negative") or {}
        profitable_sell_before_final = review_audit.get("positive_executable_sell_before_final_loss")
        audited_rows.append(
            {
                "trade_id": position_id,
                "ticker": row.get("ticker"),
                "lane": canonical_lane(row),
                "status": row.get("status"),
                "record_class": _record_class(row),
                "evidence_quality": evidence_quality(row),
                "why_picked": _entry_rationale(row),
                "final_pnl_pct": round(float(value), 4),
                "first_negative_time": review_audit.get("first_negative_time"),
                "executable_exit_before_negative": bool(
                    missed_exit
                    or safe_float(best_before.get("pnl_pct")) is not None
                    and float(best_before["pnl_pct"]) >= 0
                ),
                "best_executable_before_negative": review_audit.get("best_executable_before_negative"),
                "positive_executable_sell_before_negative": missed_exit,
                "positive_executable_sell_before_final_loss": profitable_sell_before_final,
                "executable_profit_sell_before_final_loss": bool(profitable_sell_before_final),
                "protections_active": _active_protections(row),
                "protections_failed_or_missing": guardrail_hits,
                "failure_category": _failure_category(
                    row,
                    guardrail_hits=guardrail_hits,
                    review_audit=review_audit,
                ),
                "confidence": _confidence(row, review_audit),
                "review_count": review_audit.get("review_count"),
                "notes": _notes_for_row(row, guardrail_hits, review_audit),
            }
        )
    return _summarize_audit(audited_rows)


def _notes_for_row(row: dict[str, Any], guardrail_hits: list[str], review_audit: dict[str, Any]) -> str:
    notes = []
    if _record_class(row).endswith("research_backfill"):
        notes.append("research/backfill row; not live-production proof")
    if guardrail_hits:
        notes.append("current promoted entry guardrails would block or flag this row: " + ", ".join(guardrail_hits))
    if review_audit.get("positive_executable_sell_before_negative"):
        notes.append("stored review history contains a positive executable SELL before first negative review")
    elif review_audit.get("positive_executable_sell_before_final_loss"):
        notes.append("stored review history contains a positive executable SELL before the final negative outcome")
    elif review_audit.get("best_executable_before_negative"):
        notes.append("stored review history contains a non-negative executable mark before first negative review")
    if int(row.get("id") or 0) in LEGACY_MISSED_CLOSE_IDS:
        notes.append("legacy missed-close audit target")
    return "; ".join(notes)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg": None, "median": None, "worst": None}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "median": round(median(values), 2),
        "worst": round(min(values), 2),
    }


def _summarize_audit(audited_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_lane = Counter(str(row["lane"]) for row in audited_rows)
    by_evidence = Counter(str(row["evidence_quality"]) for row in audited_rows)
    by_failure = Counter(str(row["failure_category"]) for row in audited_rows)
    by_guardrail: Counter[str] = Counter()
    for row in audited_rows:
        by_guardrail.update(row["protections_failed_or_missing"])
    pnl_values = [float(row["final_pnl_pct"]) for row in audited_rows]
    legacy_rows = [row for row in audited_rows if int(row["trade_id"]) in LEGACY_MISSED_CLOSE_IDS]
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "main_supervised_options_trading_desk_negative_trade_decision_audit",
        "summary": {
            "negative_trade_count": len(audited_rows),
            "pnl": _summary(pnl_values),
            "by_lane": dict(by_lane.most_common()),
            "by_evidence_quality": dict(by_evidence.most_common()),
            "by_failure_category": dict(by_failure.most_common()),
            "current_entry_guardrail_hits": dict(by_guardrail.most_common()),
            "executable_exit_before_negative_count": sum(
                1 for row in audited_rows if row["executable_exit_before_negative"]
            ),
            "executable_profit_sell_before_final_loss_count": sum(
                1 for row in audited_rows if row["executable_profit_sell_before_final_loss"]
            ),
            "legacy_missed_close_target_count": len(legacy_rows),
        },
        "negative_trades": sorted(audited_rows, key=lambda row: float(row["final_pnl_pct"])),
        "legacy_missed_close_targets": legacy_rows,
        "recommended_actions": _recommended_actions(audited_rows),
    }


def _recommended_actions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guardrail_rows = [row for row in rows if row["protections_failed_or_missing"]]
    exit_rows = [row for row in rows if row["executable_exit_before_negative"]]
    final_exit_rows = [row for row in rows if row["executable_profit_sell_before_final_loss"]]
    no_review_rows = [row for row in rows if int(row.get("review_count") or 0) == 0]
    return [
        {
            "priority": "P0",
            "action": "Keep promoted entry guardrails active and monitor starvation.",
            "evidence": f"{len(guardrail_rows)} negative rows hit at least one current promoted entry guardrail.",
            "verification": "Run trading_desk_profitability_guardrails_latest.json after new tracked rows accumulate.",
        },
        {
            "priority": "P1",
            "action": "Replay exit-policy variants only where exact executable bid/ask review history exists.",
            "evidence": (
                f"{len(exit_rows)} negative rows show non-negative executable evidence before the first negative review; "
                f"{len(final_exit_rows)} show a positive executable SELL before the final negative outcome."
            ),
            "verification": "Compare profit-harvest/giveback/time-exit variants against winners and losers before changing live review policy.",
        },
        {
            "priority": "P1",
            "action": "Do not claim missed exits for rows without intra-life review evidence.",
            "evidence": f"{len(no_review_rows)} negative rows have no stored review timeline.",
            "verification": "Rows need deterministic historical review snapshots or explicit insufficient-evidence labels.",
        },
        {
            "priority": "P1",
            "action": "Audit legacy rows 26, 39, and 44 separately before changing current policy.",
            "evidence": "They are legacy/unclassified rows with positive executable review evidence but are not current-lane production proof.",
            "verification": "Use exact review history and policy-version fields to determine whether old auto-close behavior differed from current review code.",
        },
    ]


def _load_reviews(repository: Any) -> dict[int, list[dict[str, Any]]]:
    if not hasattr(repository, "_connect"):
        return {}
    query = """
        SELECT
            position_id,
            reviewed_at,
            pricing_source,
            current_option_price,
            current_pnl_pct,
            gross_pnl_pct,
            net_pnl_pct,
            exit_execution_price,
            exit_execution_basis,
            recommendation,
            reason,
            metrics_snapshot
        FROM position_reviews
        ORDER BY position_id, reviewed_at, id
    """
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with repository._connect() as conn:  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    for row in rows:
        item = dict(row)
        item["metrics_snapshot"] = _as_mapping(item.get("metrics_snapshot"))
        grouped[int(item["position_id"])].append(item)
    return dict(grouped)


def load_current_report() -> dict[str, Any]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    keep_tickers = load_bullish_pullback_keep_tickers(
        ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "ticker-audit" / "latest.json"
    )
    return build_report(
        repository.list_positions("all"),
        reviews_by_position=_load_reviews(repository),
        keep_tickers=keep_tickers,
    )


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Trading Desk Negative Trade Decision Audit - 2026-05-31",
        "",
        "This audit explains negative Trading Desk tracked rows by entry rationale, evidence quality, current guardrail coverage, and available executable review history. It keeps research/backfill rows separate from production-proof claims.",
        "",
        "## Summary",
        "",
        f"- Negative rows audited: `{summary['negative_trade_count']}`",
        f"- Evidence quality: `{summary['by_evidence_quality']}`",
        f"- Failure categories: `{summary['by_failure_category']}`",
        f"- Current entry guardrail hits: `{summary['current_entry_guardrail_hits']}`",
        f"- Executable exit before first negative review: `{summary['executable_exit_before_negative_count']}`",
        f"- Positive executable SELL before final negative outcome: `{summary['executable_profit_sell_before_final_loss_count']}`",
        "",
        "## Legacy Missed-Close Targets",
        "",
        "| Trade | Ticker | Final P&L | First Negative | Best Before First Negative | Best Positive SELL Before Final Loss | Category | Notes |",
        "|---:|---|---:|---|---|---|---|---|",
    ]
    for row in report["legacy_missed_close_targets"]:
        best = row.get("best_executable_before_negative") or {}
        final_sell = row.get("positive_executable_sell_before_final_loss") or {}
        lines.append(
            f"| {row['trade_id']} | {row['ticker']} | {row['final_pnl_pct']}% | "
            f"{row.get('first_negative_time') or ''} | {best.get('pnl_pct', '')} | "
            f"{final_sell.get('pnl_pct', '')} | "
            f"{row['failure_category']} | {row['notes']} |"
        )
    lines.extend(
        [
            "",
            "## Worst Negative Rows",
            "",
            "| Trade | Ticker | Lane | Evidence | Final P&L | Why Picked | Guardrails/Missing Protections | Category |",
            "|---:|---|---|---|---:|---|---|---|",
        ]
    )
    for row in report["negative_trades"][:25]:
        lines.append(
            f"| {row['trade_id']} | {row['ticker']} | `{row['lane']}` | {row['evidence_quality']} | "
            f"{row['final_pnl_pct']}% | {row['why_picked']} | "
            f"{', '.join(row['protections_failed_or_missing']) or 'none'} | {row['failure_category']} |"
        )
    lines.extend(["", "## Recommended Actions", ""])
    for action in report["recommended_actions"]:
        lines.append(
            f"- **{action['priority']}** {action['action']} Evidence: {action['evidence']} Verification: {action['verification']}"
        )
    lines.extend(
        [
            "",
            "## Evidence Rules",
            "",
            "- Trusted executable bid/ask evidence is required before claiming a missed closeout.",
            "- Research/backfill rows are learning data, not live-production proof.",
            "- Hindsight-only price moves are not treated as failures unless the relevant signal or executable quote existed at the decision time.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], output_dir: Path, doc_path: Path) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"trading_desk_negative_trade_decision_audit_{stamp}.json"
    latest_json_path = output_dir / "trading_desk_negative_trade_decision_audit_latest.json"
    csv_path = output_dir / f"trading_desk_negative_trade_decision_audit_{stamp}.csv"
    latest_csv_path = output_dir / "trading_desk_negative_trade_decision_audit_latest.csv"
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    json_path.write_text(payload, encoding="utf-8")
    latest_json_path.write_text(payload, encoding="utf-8")
    fieldnames = [
        "trade_id",
        "ticker",
        "lane",
        "record_class",
        "evidence_quality",
        "why_picked",
        "final_pnl_pct",
        "first_negative_time",
        "executable_exit_before_negative",
        "executable_profit_sell_before_final_loss",
        "protections_failed_or_missing",
        "failure_category",
        "confidence",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["negative_trades"]:
            writer.writerow({key: row.get(key) for key in fieldnames})
    latest_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    doc_path.write_text(markdown_report(report), encoding="utf-8")
    return json_path, latest_json_path, csv_path, doc_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Trading Desk negative trade decisions.")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc-path", default=str(DEFAULT_DOC))
    args = parser.parse_args(argv)
    report = load_current_report()
    if not args.no_write:
        paths = write_outputs(report, Path(args.output_dir), Path(args.doc_path))
        print("Wrote audit artifacts:")
        for path in paths:
            print(path)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
