from __future__ import annotations

import argparse
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
    load_bullish_pullback_keep_tickers,
    pnl_pct,
    source,
)


OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DOCS_REPORT = ROOT / "docs" / "current-policy-historical-picks-audit.md"
BULLISH_PULLBACK_TICKER_AUDIT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "bullish-pullback-observation"
    / "ticker-audit"
    / "latest.json"
)
TRADING_DESK_GUARDRAILS = ROOT / "data" / "forward-tracking" / "trading_desk_profitability_guardrails_latest.json"
SYMBOL_SLEEVES = ROOT / "data" / "profitability-lab" / "regular-options-symbol-sleeves" / "latest.json"

CURRENT_POLICY_REPAIR_LANES = {
    "short_term",
    "swing",
    "bullish_momentum",
    "bullish_pullback_observation",
}
FALLBACK_PROMOTED_GUARDRAILS = [
    "debit_gt_45_width",
    "fill_degradation_ge_20",
    "worst_leg_spread_ge_20",
    "lane_ticker_quarantine",
    "bullish_pullback_not_keep_bucket",
    "bullish_pullback_ret5_lt_minus_2",
]
TRUSTED_EXIT_BASIS_TOKENS = [
    "spread_bid_ask",
    "spread_bid_ask_exact",
    "historical_spread_bid_ask",
    "historical_suggested_close",
    "auto_sell_recommendation",
    "broker",
]
UNTRUSTED_EXIT_BASIS_TOKENS = [
    "lifecycle",
    "elapsed",
    "last",
    "midpoint",
    "mark",
    "model",
    "unpriced",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


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


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def input_manifest_entry(path: Path, source_type: str) -> dict[str, Any]:
    entry = {
        "path": _rel(path),
        "source_type": source_type,
        "exists": path.exists(),
        "generated_at": None,
        "status": "missing",
    }
    if not path.exists():
        return entry
    try:
        payload = _load_json(path)
    except Exception as exc:
        entry["status"] = f"unreadable:{exc}"
        return entry
    entry["generated_at"] = (
        payload.get("generated_at_utc")
        or payload.get("generated_at")
        or payload.get("run_at")
        or payload.get("created_at")
    )
    entry["status"] = "ok"
    return entry


def load_promoted_guardrails(path: Path = TRADING_DESK_GUARDRAILS) -> list[str]:
    if not path.exists():
        return list(FALLBACK_PROMOTED_GUARDRAILS)
    try:
        payload = _load_json(path)
    except Exception:
        return list(FALLBACK_PROMOTED_GUARDRAILS)
    values = payload.get("promoted_guardrails")
    if not isinstance(values, list) or not values:
        return list(FALLBACK_PROMOTED_GUARDRAILS)
    return [str(value) for value in values if str(value)]


def load_symbol_sleeve_index(path: Path = SYMBOL_SLEEVES) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except Exception:
        return {}
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("lane_symbol_rows") or []:
        if not isinstance(row, dict):
            continue
        lane = str(row.get("lane_id") or "").strip()
        symbol = str(row.get("symbol") or "").strip().upper()
        if lane and symbol:
            index[(lane, symbol)] = row
    return index


def _entry_execution_price(row: dict[str, Any]) -> float | None:
    latest = _as_mapping(row.get("latest_review"))
    snap = source(row)
    for value in (
        latest.get("entry_execution_price"),
        row.get("entry_execution_price"),
        snap.get("entry_execution_price"),
        row.get("entry_option_price"),
    ):
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _realized_exit_price(row: dict[str, Any]) -> float | None:
    latest = _as_mapping(row.get("latest_review"))
    for value in (
        row.get("exit_execution_price"),
        row.get("exit_option_price"),
        latest.get("exit_execution_price"),
        latest.get("current_option_price"),
    ):
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _exit_execution_basis(row: dict[str, Any]) -> str:
    latest = _as_mapping(row.get("latest_review"))
    return str(
        row.get("exit_execution_basis")
        or latest.get("exit_execution_basis")
        or latest.get("pricing_source")
        or row.get("exit_reason")
        or ""
    ).strip().lower()


def has_executable_entry(row: dict[str, Any]) -> bool:
    entry_price = _entry_execution_price(row)
    return entry_price is not None and entry_price > 0


def has_trusted_executable_exit(row: dict[str, Any]) -> bool:
    exit_price = _realized_exit_price(row)
    if exit_price is None:
        return False
    basis = _exit_execution_basis(row)
    if not basis:
        return False
    if any(token in basis for token in UNTRUSTED_EXIT_BASIS_TOKENS):
        return False
    return any(token in basis for token in TRUSTED_EXIT_BASIS_TOKENS)


def is_realized_pnl_closed(row: dict[str, Any]) -> bool:
    if row.get("status") != "closed":
        return False
    return has_executable_entry(row) and has_trusted_executable_exit(row) and pnl_pct(row) is not None


def _evidence_values(row: dict[str, Any]) -> list[str]:
    snap = source(row)
    values = [
        row.get("proof_class"),
        row.get("proof_class_reason"),
        row.get("proof_ineligibility_reason"),
        row.get("notes"),
        snap.get("pricing_evidence_class"),
        snap.get("profitability_evidence_class"),
        snap.get("production_filter_action"),
        snap.get("source_separation"),
        snap.get("promotion_class"),
        snap.get("selection_source"),
        snap.get("event_type"),
        snap.get("candidate_execution_label"),
        snap.get("backfill_audit_id"),
        snap.get("position_migration_id"),
        snap.get("market_data_source"),
        snap.get("status"),
    ]
    return [str(value).strip().lower() for value in values if str(value or "").strip()]


def evidence_group(row: dict[str, Any]) -> str:
    snap = source(row)
    values = _evidence_values(row)
    migrated_paper = bool(snap.get("position_migration_id") or snap.get("position_migrated_at_utc"))
    backfill_or_research = bool(snap.get("research_only")) or any(
        any(token in value for token in ("backfill", "research", "historical_replay", "historical_selection"))
        for value in values
    )
    if row.get("status") == "closed" and _realized_exit_price(row) is None:
        return "lifecycle_only"
    if migrated_paper:
        return "historical_paper"
    if backfill_or_research:
        return "research_backfill"
    proof_class = str(row.get("proof_class") or snap.get("proof_class") or "").strip().lower()
    if snap.get("comparable_contract"):
        return "proof_ineligible"
    if proof_class == "ineligible" or row.get("proof_eligible") is False:
        return "proof_ineligible"
    if proof_class == "live_scan_exact_contract" or (row.get("proof_eligible") and proof_class != "manual_broker_exact_contract"):
        return "live_exact"
    if proof_class == "manual_broker_exact_contract":
        return "manual_exact"
    return "legacy_unclassified"


def current_policy_guardrail_hits(
    row: dict[str, Any],
    *,
    keep_tickers: set[str],
    promoted_guardrails: list[str],
) -> list[str]:
    probes = build_probe_definitions(keep_tickers)
    hits: list[str] = []
    for guardrail_id in promoted_guardrails:
        matcher = probes.get(guardrail_id)
        if matcher is None:
            continue
        try:
            if matcher(row):
                hits.append(guardrail_id)
        except Exception:
            continue
    return hits


def _symbol_sleeve_for_row(
    row: dict[str, Any],
    symbol_sleeves: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    lane = canonical_lane(row)
    ticker = str(row.get("ticker") or "").strip().upper()
    return symbol_sleeves.get((lane, ticker))


def classify_position(
    row: dict[str, Any],
    *,
    keep_tickers: set[str],
    promoted_guardrails: list[str],
    symbol_sleeves: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    symbol_sleeves = symbol_sleeves or {}
    lane = canonical_lane(row)
    in_scope_lane = lane in CURRENT_POLICY_REPAIR_LANES
    realized = is_realized_pnl_closed(row)
    hits = (
        current_policy_guardrail_hits(row, keep_tickers=keep_tickers, promoted_guardrails=promoted_guardrails)
        if in_scope_lane
        else []
    )
    sleeve = _symbol_sleeve_for_row(row, symbol_sleeves)

    if not in_scope_lane:
        decision = "out_of_scope_lane"
        reason = "lane does not have a promoted current-policy replay in this audit"
    elif hits:
        decision = "blocked_by_current_policy"
        reason = "current promoted entry guardrails would block this row"
    elif not realized:
        decision = "unknown_missing_evidence"
        reason = "row lacks trusted executable realized P&L for current-policy scoring"
    else:
        decision = "would_take_today"
        reason = "row clears the current promoted entry guardrails and has trusted realized P&L"

    value = pnl_pct(row)
    return {
        "trade_id": row.get("id"),
        "ticker": str(row.get("ticker") or "").upper(),
        "lane": lane,
        "status": row.get("status"),
        "entry_date": str(row.get("filled_at") or "")[:10] or None,
        "closed_at": str(row.get("closed_at") or "")[:10] or None,
        "evidence_group": evidence_group(row),
        "has_realized_pnl": realized,
        "pnl_pct": round(float(value), 4) if value is not None else None,
        "current_policy_decision": decision,
        "decision_reason": reason,
        "guardrail_hits": hits,
        "symbol_sleeve_status": sleeve.get("status") if sleeve else None,
        "symbol_sleeve_evidence_class": sleeve.get("evidence_class") if sleeve else None,
        "symbol_sleeve_reason_codes": list(sleeve.get("reason_codes") or [])[:8] if sleeve else [],
        "source_pick_snapshot": source(row),
        "_position": row,
    }


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "priced": 0,
            "negative": 0,
            "positive_or_flat": 0,
            "negative_rate_priced_pct": None,
            "avg_pnl_pct": None,
            "median_pnl_pct": None,
        }
    negative = [value for value in values if value < 0]
    return {
        "priced": len(values),
        "negative": len(negative),
        "positive_or_flat": len(values) - len(negative),
        "negative_rate_priced_pct": round(len(negative) / len(values) * 100.0, 1),
        "avg_pnl_pct": round(sum(values) / len(values), 2),
        "median_pnl_pct": round(median(values), 2),
    }


def summarize_audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["pnl_pct"]) for row in rows if row.get("pnl_pct") is not None]
    summary = _summary(values)
    summary["rows"] = len(rows)
    summary["unknown"] = len(rows) - len(values)
    return summary


def _decision_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["current_policy_decision"])].append(row)
    return {decision: summarize_audit_rows(items) for decision, items in sorted(grouped.items())}


def _lane_decision_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["lane"])].append(row)
    return {lane: _decision_breakdown(items) for lane, items in sorted(grouped.items())}


def _strip_internal_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in row.items() if key not in {"_position", "source_pick_snapshot"}}
    if row.get("guardrail_hits"):
        cleaned["guardrail_hits"] = list(row["guardrail_hits"])
    return cleaned


def build_report(
    rows: list[dict[str, Any]],
    *,
    keep_tickers: set[str] | None = None,
    promoted_guardrails: list[str] | None = None,
    symbol_sleeves: dict[tuple[str, str], dict[str, Any]] | None = None,
    inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    keep_tickers = keep_tickers or {"IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
    promoted_guardrails = promoted_guardrails or list(FALLBACK_PROMOTED_GUARDRAILS)
    symbol_sleeves = symbol_sleeves or {}
    closed_rows = [row for row in rows if row.get("status") == "closed"]
    audited_rows = [
        classify_position(
            row,
            keep_tickers=keep_tickers,
            promoted_guardrails=promoted_guardrails,
            symbol_sleeves=symbol_sleeves,
        )
        for row in closed_rows
    ]
    in_scope_rows = [row for row in audited_rows if row["lane"] in CURRENT_POLICY_REPAIR_LANES]
    current_rows = [row for row in audited_rows if row["current_policy_decision"] == "would_take_today"]
    learned_away_rows = [row for row in audited_rows if row["current_policy_decision"] == "blocked_by_current_policy"]
    unknown_rows = [row for row in audited_rows if row["current_policy_decision"] == "unknown_missing_evidence"]
    raw_realized_rows = [row for row in in_scope_rows if row.get("has_realized_pnl")]

    guardrail_counts: Counter[str] = Counter()
    for row in audited_rows:
        guardrail_counts.update(row.get("guardrail_hits") or [])

    summary = {
        "closed_rows": len(closed_rows),
        "current_policy_scope_rows": len(in_scope_rows),
        "out_of_scope_lane_rows": sum(1 for row in audited_rows if row["current_policy_decision"] == "out_of_scope_lane"),
        "raw_realized_scope": summarize_audit_rows(raw_realized_rows),
        "would_take_today": summarize_audit_rows(current_rows),
        "blocked_by_current_policy": summarize_audit_rows(learned_away_rows),
        "unknown_missing_evidence": summarize_audit_rows(unknown_rows),
        "decision_counts": dict(Counter(str(row["current_policy_decision"]) for row in audited_rows).most_common()),
        "evidence_group_counts": dict(Counter(str(row["evidence_group"]) for row in audited_rows).most_common()),
        "guardrail_hit_counts": dict(guardrail_counts.most_common()),
        "symbol_sleeve_status_counts": dict(
            Counter(str(row["symbol_sleeve_status"] or "missing") for row in audited_rows).most_common()
        ),
    }
    raw_avg = summary["raw_realized_scope"]["avg_pnl_pct"]
    current_avg = summary["would_take_today"]["avg_pnl_pct"]
    summary["current_vs_raw_realized_delta_avg_pnl_pct"] = (
        round(float(current_avg) - float(raw_avg), 2)
        if current_avg is not None and raw_avg is not None
        else None
    )

    worst_learned_away = sorted(
        [row for row in learned_away_rows if row.get("pnl_pct") is not None],
        key=lambda row: float(row["pnl_pct"]),
    )[:25]
    current_examples = sorted(
        [row for row in current_rows if row.get("pnl_pct") is not None],
        key=lambda row: float(row["pnl_pct"]),
        reverse=True,
    )[:25]

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_supervised_trading_desk_current_policy_historical_picks",
        "policy": {
            "repair_lanes": sorted(CURRENT_POLICY_REPAIR_LANES),
            "promoted_guardrails": promoted_guardrails,
            "bullish_pullback_keep_tickers": sorted(keep_tickers),
            "truth_policy": "trusted executable entry plus trusted executable exit P&L remains separate from production-proof truth-grade claims",
            "history_policy": "historical paper and research/backfill rows are relabeled by current policy, not deleted or rewritten",
        },
        "inputs": inputs or [],
        "summary": summary,
        "decision_breakdown": _decision_breakdown(audited_rows),
        "lane_decision_breakdown": _lane_decision_breakdown(audited_rows),
        "rows": [_strip_internal_row(row) for row in sorted(audited_rows, key=lambda item: (str(item["lane"]), str(item["ticker"]), str(item.get("trade_id"))))],
        "worst_learned_away_rows": [_strip_internal_row(row) for row in worst_learned_away],
        "best_current_policy_rows": [_strip_internal_row(row) for row in current_examples],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _fmt_pct(value: Any) -> str:
    return "" if value is None else f"{value}%"


def _summary_table(label: str, summary: dict[str, Any]) -> str:
    return (
        f"| {label} | {summary.get('rows')} | {summary.get('priced')} | "
        f"{summary.get('negative')} | {summary.get('positive_or_flat')} | "
        f"{_fmt_pct(summary.get('avg_pnl_pct'))} | {_fmt_pct(summary.get('median_pnl_pct'))} | "
        f"{_fmt_pct(summary.get('negative_rate_priced_pct'))} |"
    )


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Current-Policy Historical Picks Audit",
        "",
        "This report replays closed Trading Desk history through the currently promoted entry guardrails. It does not delete, rewrite, or promote historical paper rows; it separates rows the current policy would still take from rows that have been learned away.",
        "",
        "## Summary",
        "",
        f"- Closed rows audited: `{summary['closed_rows']}`.",
        f"- Current-policy scope rows: `{summary['current_policy_scope_rows']}`.",
        f"- Decision counts: `{json.dumps(summary['decision_counts'], sort_keys=True)}`.",
        f"- Guardrail hit counts: `{json.dumps(summary['guardrail_hit_counts'], sort_keys=True)}`.",
        f"- Current-policy avg P&L delta versus raw realized scope: `{summary['current_vs_raw_realized_delta_avg_pnl_pct']}` percentage points.",
        "",
        "| Set | Rows | Priced | Negative | Positive/Flat | Avg P&L | Median P&L | Negative Rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        _summary_table("Raw realized scope", summary["raw_realized_scope"]),
        _summary_table("Would take today", summary["would_take_today"]),
        _summary_table("Blocked by current policy", summary["blocked_by_current_policy"]),
        _summary_table("Unknown or missing evidence", summary["unknown_missing_evidence"]),
        "",
        "## Policy",
        "",
        f"- Repair lanes: `{', '.join(report['policy']['repair_lanes'])}`.",
        f"- Promoted guardrails: `{', '.join(report['policy']['promoted_guardrails'])}`.",
        f"- Bullish Pullback keep tickers: `{', '.join(report['policy']['bullish_pullback_keep_tickers'])}`.",
        "- `would_take_today` means the row clears these current entry guardrails and has trusted realized P&L.",
        "- `blocked_by_current_policy` means today's promoted entry guardrails would block or flag the historical entry.",
        "- `unknown_missing_evidence` rows stay visible because they do not have trusted executable realized P&L.",
        "",
        "## Worst Learned-Away Rows",
        "",
        "| Trade | Ticker | Lane | P&L | Evidence | Guardrails | Sleeve |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for row in report.get("worst_learned_away_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("trade_id")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("lane")),
                    f"{row.get('pnl_pct')}%",
                    _fmt(row.get("evidence_group")),
                    _fmt(", ".join(row.get("guardrail_hits") or [])),
                    _fmt(row.get("symbol_sleeve_status")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Best Current-Policy Rows",
            "",
            "| Trade | Ticker | Lane | P&L | Evidence | Sleeve |",
            "|---:|---|---|---:|---|---|",
        ]
    )
    for row in report.get("best_current_policy_rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("trade_id")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("lane")),
                    f"{row.get('pnl_pct')}%",
                    _fmt(row.get("evidence_group")),
                    _fmt(row.get("symbol_sleeve_status")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Inputs",
            "",
            "| Source | Status | Generated | Path |",
            "|---|---|---|---|",
        ]
    )
    for entry in report.get("inputs") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(entry.get("source_type")),
                    _fmt(entry.get("status")),
                    _fmt(entry.get("generated_at")),
                    _fmt(entry.get("path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, docs_report: Path = DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"current_policy_historical_picks_{stamp}.json"
    latest_json = output_dir / "current_policy_historical_picks_latest.json"
    md_path = output_dir / f"current_policy_historical_picks_{stamp}.md"
    latest_md = output_dir / "current_policy_historical_picks_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True, default=str)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    docs_report.write_text(markdown, encoding="utf-8")
    return artifacts


def load_positions() -> list[dict[str, Any]]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    return repository.list_positions("all")


def build_current_report() -> dict[str, Any]:
    inputs = [
        input_manifest_entry(TRADING_DESK_GUARDRAILS, "trading_desk_profitability_guardrails"),
        input_manifest_entry(BULLISH_PULLBACK_TICKER_AUDIT, "bullish_pullback_ticker_audit"),
        input_manifest_entry(SYMBOL_SLEEVES, "regular_options_symbol_sleeves"),
    ]
    keep_tickers = load_bullish_pullback_keep_tickers(BULLISH_PULLBACK_TICKER_AUDIT)
    promoted_guardrails = load_promoted_guardrails(TRADING_DESK_GUARDRAILS)
    symbol_sleeves = load_symbol_sleeve_index(SYMBOL_SLEEVES)
    return build_report(
        load_positions(),
        keep_tickers=keep_tickers,
        promoted_guardrails=promoted_guardrails,
        symbol_sleeves=symbol_sleeves,
        inputs=inputs,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay historical Trading Desk picks through current policy guardrails.")
    parser.add_argument("--json", action="store_true", help="Print the generated report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Build without writing artifacts.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--doc-path", default=str(DOCS_REPORT))
    args = parser.parse_args(argv)

    report = build_current_report()
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=Path(args.output_dir), docs_report=Path(args.doc_path))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
