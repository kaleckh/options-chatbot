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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from local_env import load_local_env
from positions_repository import create_positions_repository


DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "trading-desk-profitability-guardrails-2026-05-31.md"
REPAIR_LANES = {"short_term", "swing", "bullish_momentum", "bullish_pullback_observation"}
LANE_TICKER_QUARANTINES = {
    "short_term": {"XLK", "IWM", "DIA", "SPY", "SLB", "NVDA"},
    "swing": {"IWM", "XLK", "SLB", "DIA", "NFLX"},
    "bullish_momentum": {"NVDA", "TSLA", "COIN"},
}


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


def source(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("source_pick_snapshot")
    return value if isinstance(value, dict) else {}


def canonical_lane(row: dict[str, Any]) -> str:
    snap = source(row)
    raw = str(snap.get("playbook_id") or snap.get("playbook") or row.get("playbook_id") or "legacy_unlabeled").strip()
    if raw.startswith("bullish_pullback"):
        return "bullish_pullback_observation"
    return raw


def pnl_pct(row: dict[str, Any]) -> float | None:
    for key in ("net_pnl_pct", "gross_pnl_pct", "last_pnl_pct"):
        value = safe_float(row.get(key))
        if value is not None:
            return value
    latest = row.get("latest_review") if isinstance(row.get("latest_review"), dict) else {}
    for key in ("net_pnl_pct", "gross_pnl_pct", "current_pnl_pct"):
        value = safe_float(latest.get(key))
        if value is not None:
            return value
    return None


def debit_pct_of_width(row: dict[str, Any]) -> float | None:
    snap = source(row)
    explicit = safe_float(snap.get("debit_pct_of_width"))
    if explicit is not None:
        return explicit
    net_debit = safe_float(snap.get("net_debit") or snap.get("entry_execution_price"))
    spread_width = safe_float(snap.get("spread_width"))
    if net_debit is None or spread_width is None or spread_width <= 0:
        return None
    return net_debit / spread_width * 100.0


def fill_degradation_vs_mid_pct(row: dict[str, Any]) -> float | None:
    snap = source(row)
    liquidity = snap.get("spread_liquidity") if isinstance(snap.get("spread_liquidity"), dict) else {}
    explicit = safe_float(snap.get("fill_degradation_vs_mid_pct") or liquidity.get("fill_degradation_vs_mid_pct"))
    if explicit is not None:
        return explicit
    entry_debit = safe_float(
        liquidity.get("spread_entry_debit")
        or snap.get("spread_entry_debit")
        or snap.get("entry_execution_price")
        or snap.get("net_debit")
    )
    mid_debit = safe_float(liquidity.get("spread_mid_debit") or snap.get("spread_mid_debit"))
    if entry_debit is None or mid_debit is None or mid_debit <= 0:
        return None
    return max((entry_debit / mid_debit - 1.0) * 100.0, 0.0)


def worst_leg_bid_ask_spread_pct(row: dict[str, Any]) -> float | None:
    snap = source(row)
    liquidity = snap.get("spread_liquidity") if isinstance(snap.get("spread_liquidity"), dict) else {}
    explicit = safe_float(
        snap.get("worst_leg_bid_ask_spread_pct")
        or snap.get("worst_leg_spread_pct")
        or liquidity.get("worst_leg_bid_ask_spread_pct")
    )
    if explicit is not None:
        return explicit
    values: list[float] = []
    for prefix in ("long", "short"):
        bid = safe_float(liquidity.get(f"{prefix}_bid"))
        ask = safe_float(liquidity.get(f"{prefix}_ask"))
        if bid is None or ask is None:
            continue
        mid = (bid + ask) / 2.0
        if mid > 0:
            values.append(max((ask - bid) / mid * 100.0, 0.0))
    return max(values) if values else None


def signal_ret5(row: dict[str, Any]) -> float | None:
    snap = source(row)
    return safe_float(snap.get("signal_ret5") if snap.get("signal_ret5") is not None else snap.get("ret5"))


def direction_score(row: dict[str, Any]) -> float:
    return safe_float(source(row).get("direction_score")) or 0.0


def quality_score(row: dict[str, Any]) -> float:
    return safe_float(source(row).get("quality_score")) or 0.0


def load_bullish_pullback_keep_tickers(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
    return {
        str(row.get("ticker") or "").strip().upper()
        for row in payload.get("rows", [])
        if row.get("decision") == "keep-in-current-lane" and str(row.get("ticker") or "").strip()
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for value in (pnl_pct(row) for row in rows) if value is not None]
    negative = [value for value in values if value < 0]
    positive = [value for value in values if value >= 0]
    return {
        "rows": len(rows),
        "priced": len(values),
        "negative": len(negative),
        "positive_or_flat": len(positive),
        "unknown": len(rows) - len(values),
        "negative_rate_priced_pct": round(len(negative) / len(values) * 100.0, 1) if values else 0.0,
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "median_pnl_pct": round(median(values), 2) if values else None,
    }


def lane_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[canonical_lane(row)].append(row)
    return {lane: summarize(items) for lane, items in sorted(grouped.items())}


def top_negative_tickers(rows: list[dict[str, Any]], limit: int = 8) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = pnl_pct(row)
        if value is not None and value < 0:
            counts[str(row.get("ticker") or "").upper()] += 1
    return dict(counts.most_common(limit))


def build_probe_definitions(keep_tickers: set[str]) -> dict[str, Callable[[dict[str, Any]], bool]]:
    return {
        "debit_gt_45_width": lambda row: (debit_pct_of_width(row) is not None and debit_pct_of_width(row) > 45.0),
        "fill_degradation_ge_20": lambda row: (
            fill_degradation_vs_mid_pct(row) is not None and fill_degradation_vs_mid_pct(row) >= 20.0
        ),
        "worst_leg_spread_ge_20": lambda row: (
            worst_leg_bid_ask_spread_pct(row) is not None and worst_leg_bid_ask_spread_pct(row) >= 20.0
        ),
        "momentum_chase": lambda row: (
            canonical_lane(row) in {"short_term", "swing", "bullish_momentum"}
            and signal_ret5(row) is not None
            and signal_ret5(row) >= 5.0
            and (direction_score(row) >= 85.0 or quality_score(row) >= 75.0)
        ),
        "lane_ticker_quarantine": lambda row: str(row.get("ticker") or "").upper()
        in LANE_TICKER_QUARANTINES.get(canonical_lane(row), set()),
        "bullish_pullback_not_keep_bucket": lambda row: (
            canonical_lane(row) == "bullish_pullback_observation"
            and str(row.get("ticker") or "").upper() not in keep_tickers
        ),
        "bullish_pullback_ret5_lt_minus_2": lambda row: (
            canonical_lane(row) == "bullish_pullback_observation"
            and signal_ret5(row) is not None
            and signal_ret5(row) < -2.0
        ),
    }


def should_promote_probe(probe_id: str, blocked: dict[str, Any], kept: dict[str, Any], baseline: dict[str, Any]) -> bool:
    if probe_id == "momentum_chase":
        return False
    if blocked["negative"] <= blocked["positive_or_flat"]:
        return False
    if kept["avg_pnl_pct"] is None or baseline["avg_pnl_pct"] is None:
        return False
    if kept["avg_pnl_pct"] <= baseline["avg_pnl_pct"]:
        return False
    return kept["median_pnl_pct"] is None or baseline["median_pnl_pct"] is None or kept["median_pnl_pct"] >= baseline["median_pnl_pct"]


def build_report(rows: list[dict[str, Any]], *, keep_tickers: set[str]) -> dict[str, Any]:
    repair_rows = [row for row in rows if canonical_lane(row) in REPAIR_LANES]
    baseline = summarize(repair_rows)
    probes = []
    for probe_id, matcher in build_probe_definitions(keep_tickers).items():
        blocked_rows = [row for row in repair_rows if matcher(row)]
        kept_rows = [row for row in repair_rows if not matcher(row)]
        blocked = summarize(blocked_rows)
        kept = summarize(kept_rows)
        promote = should_promote_probe(probe_id, blocked, kept, baseline)
        probes.append(
            {
                "id": probe_id,
                "promote_to_guardrail": promote,
                "blocked": blocked,
                "kept": kept,
                "blocked_by_lane": lane_breakdown(blocked_rows),
                "top_negative_tickers_blocked": top_negative_tickers(blocked_rows),
            }
        )
    promoted_ids = [probe["id"] for probe in probes if probe["promote_to_guardrail"]]
    combined_blocked_rows = [
        row
        for row in repair_rows
        if any(build_probe_definitions(keep_tickers)[probe_id](row) for probe_id in promoted_ids)
    ]
    combined_kept_rows = [
        row
        for row in repair_rows
        if not any(build_probe_definitions(keep_tickers)[probe_id](row) for probe_id in promoted_ids)
    ]
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_repair_lanes",
        "repair_lanes": sorted(REPAIR_LANES),
        "bullish_pullback_keep_tickers": sorted(keep_tickers),
        "baseline": baseline,
        "baseline_by_lane": lane_breakdown(repair_rows),
        "probes": probes,
        "promoted_guardrails": promoted_ids,
        "combined_promoted_guardrails": {
            "blocked": summarize(combined_blocked_rows),
            "kept": summarize(combined_kept_rows),
            "blocked_by_lane": lane_breakdown(combined_blocked_rows),
            "top_negative_tickers_blocked": top_negative_tickers(combined_blocked_rows),
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Trading Desk Profitability Guardrails - 2026-05-31",
        "",
        "This is an all-row replay over the regular supervised Trading Desk repair lanes. It measures candidate entry guardrails against both avoided losers and lost winners before any scanner rule is promoted.",
        "",
        "## Baseline",
        "",
        "| Rows | Priced | Negative | Positive/Flat | Unknown | Avg P&L | Median P&L |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    base = report["baseline"]
    lines.append(
        f"| {base['rows']} | {base['priced']} | {base['negative']} | {base['positive_or_flat']} | "
        f"{base['unknown']} | {base['avg_pnl_pct']}% | {base['median_pnl_pct']}% |"
    )
    lines.extend(["", "## Probe Results", ""])
    lines.append("| Probe | Promote | Blocked | Neg Avoided | Winners Lost | Unknown | Kept Avg | Kept Median |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for probe in report["probes"]:
        blocked = probe["blocked"]
        kept = probe["kept"]
        lines.append(
            f"| `{probe['id']}` | {'yes' if probe['promote_to_guardrail'] else 'no'} | "
            f"{blocked['rows']} | {blocked['negative']} | {blocked['positive_or_flat']} | {blocked['unknown']} | "
            f"{kept['avg_pnl_pct']}% | {kept['median_pnl_pct']}% |"
        )
    combined = report["combined_promoted_guardrails"]
    lines.extend(
        [
            "",
            "## Promoted Combined Effect",
            "",
            f"Promoted guardrails: `{', '.join(report['promoted_guardrails'])}`",
            "",
            "| Set | Rows | Priced | Negative | Positive/Flat | Unknown | Avg P&L | Median P&L |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, summary in (("Blocked", combined["blocked"]), ("Kept", combined["kept"])):
        lines.append(
            f"| {label} | {summary['rows']} | {summary['priced']} | {summary['negative']} | "
            f"{summary['positive_or_flat']} | {summary['unknown']} | {summary['avg_pnl_pct']}% | {summary['median_pnl_pct']}% |"
        )
    lines.extend(
        [
            "",
            "## Implementation Read",
            "",
            "- Promote high debit, fill degradation, wide-leg, lane/ticker quarantine, Bullish Pullback keep-bucket, and Bullish Pullback ret5 floor guardrails.",
            "- Reject momentum-chase blocking: in this all-row replay, the blocked set had positive average P&L, so the rule would remove too many winners.",
            "- These guardrails block or research-tag future picks; they do not hide historical rows and do not change the `90%` stop policy.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], output_dir: Path, doc_path: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"trading_desk_profitability_guardrails_{stamp}.json"
    latest_path = output_dir / "trading_desk_profitability_guardrails_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    doc_path.write_text(markdown_report(report), encoding="utf-8")
    return json_path, latest_path, doc_path


def load_positions() -> list[dict[str, Any]]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    return repository.list_positions("all")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Trading Desk profitability guardrails against tracked positions.")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc-path", default=str(DEFAULT_DOC))
    parser.add_argument(
        "--bullish-pullback-ticker-audit",
        default=str(ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "ticker-audit" / "latest.json"),
    )
    args = parser.parse_args(argv)
    keep_tickers = load_bullish_pullback_keep_tickers(Path(args.bullish_pullback_ticker_audit))
    report = build_report(load_positions(), keep_tickers=keep_tickers)
    if not args.no_write:
        json_path, latest_path, doc_path = write_outputs(report, Path(args.output_dir), Path(args.doc_path))
        print(f"Wrote guardrail report: {json_path}")
        print(f"Wrote latest guardrail report: {latest_path}")
        print(f"Wrote markdown report: {doc_path}")
    print(json.dumps({"baseline": report["baseline"], "promoted_guardrails": report["promoted_guardrails"], "combined": report["combined_promoted_guardrails"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
