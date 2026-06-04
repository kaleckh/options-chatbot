from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import UTC, date, datetime
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
    canonical_lane,
    fill_degradation_vs_mid_pct,
    pnl_pct,
)
from scripts.analyze_current_policy_entry_filters import _safe_float


REPORT_ID = "current_policy_entry_filter_paper_monitor"
DEFAULT_FILTER_LAB = ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_lab_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "current-policy-entry-filter-paper-monitor.md"
REPAIR_LANES = {"short_term", "swing", "bullish_momentum", "bullish_pullback_observation"}
SHADOW_THRESHOLDS = (10.0, 12.5, 15.0, 17.5, 20.0)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _default_since_date(filter_lab: dict[str, Any]) -> date:
    generated = _parse_date(filter_lab.get("generated_at_utc"))
    return generated or datetime.now(UTC).date()


def _position_date(row: dict[str, Any]) -> date | None:
    return _parse_date(row.get("filled_at"))


def _is_repair_lane(row: dict[str, Any]) -> bool:
    return canonical_lane(row) in REPAIR_LANES


def _filter_id_for_threshold(threshold: float) -> str:
    label = str(int(threshold)) if float(threshold).is_integer() else str(threshold).replace(".", "_")
    return f"short_term_fill_degradation_ge_{label}"


def matches_short_term_fill_filter(row: dict[str, Any], *, threshold: float) -> bool:
    return canonical_lane(row) == "short_term" and (
        (value := fill_degradation_vs_mid_pct(row)) is not None and value >= float(threshold)
    )


def _pnl_values(rows: list[dict[str, Any]]) -> list[float]:
    return [float(value) for row in rows if (value := pnl_pct(row)) is not None]


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = _pnl_values(rows)
    losses = [value for value in values if value < 0]
    winners = [value for value in values if value > 0]
    return {
        "rows": len(rows),
        "open_rows": sum(1 for row in rows if str(row.get("status") or "").lower() == "open"),
        "closed_rows": sum(1 for row in rows if str(row.get("status") or "").lower() == "closed"),
        "priced_rows": len(values),
        "avg_pnl_pct": round(sum(values) / len(values), 4) if values else None,
        "median_pnl_pct": round(float(median(values)), 4) if values else None,
        "sum_pnl_pct": round(sum(values), 4) if values else 0.0,
        "negative_count": len(losses),
        "positive_count": len(winners),
        "negative_rate_pct": round(len(losses) / len(values) * 100.0, 4) if values else None,
        "loss_le_50_count": sum(1 for value in values if value <= -50.0),
        "loss_le_90_count": sum(1 for value in values if value <= -90.0),
    }


def evaluate_threshold(rows: list[dict[str, Any]], *, threshold: float) -> dict[str, Any]:
    matched = [row for row in rows if matches_short_term_fill_filter(row, threshold=threshold)]
    kept = [row for row in rows if row not in matched]
    matched_summary = summarize_rows(matched)
    kept_summary = summarize_rows(kept)
    losses_avoided = int(matched_summary["negative_count"])
    winners_lost = int(matched_summary["positive_count"])
    return {
        "filter_id": _filter_id_for_threshold(threshold),
        "threshold_pct": float(threshold),
        "matched": matched_summary,
        "kept": kept_summary,
        "losses_avoided": losses_avoided,
        "deep_losses_avoided": int(matched_summary["loss_le_50_count"]),
        "near_total_losses_avoided": int(matched_summary["loss_le_90_count"]),
        "winners_lost": winners_lost,
        "sample_examples": [
            {
                "position_id": row.get("id"),
                "ticker": row.get("ticker"),
                "status": row.get("status"),
                "filled_at": row.get("filled_at"),
                "pnl_pct": pnl_pct(row),
                "fill_degradation_pct": fill_degradation_vs_mid_pct(row),
            }
            for row in sorted(matched, key=lambda item: str(item.get("filled_at") or ""), reverse=True)[:20]
        ],
    }


def gate_status(*, baseline: dict[str, Any], champion: dict[str, Any], min_rows: int, min_blocked: int) -> dict[str, Any]:
    matched = champion["matched"]
    kept = champion["kept"]
    failures: list[str] = []
    if int(baseline["rows"]) < int(min_rows):
        failures.append("insufficient_fresh_rows")
    if int(matched["rows"]) < int(min_blocked):
        failures.append("insufficient_candidate_blocked_rows")
    kept_median = _safe_float(kept.get("median_pnl_pct"))
    kept_negative_rate = _safe_float(kept.get("negative_rate_pct"))
    if kept_median is not None and kept_median <= 0:
        failures.append("kept_median_not_positive")
    if kept_negative_rate is not None and kept_negative_rate >= 40.0:
        failures.append("kept_negative_rate_too_high")
    matched_sum = _safe_float(matched.get("sum_pnl_pct")) or 0.0
    if matched_sum >= 0 and int(matched.get("loss_le_50_count") or 0) < 2:
        failures.append("blocked_rows_not_net_negative_or_deep_loss")
    if int(champion.get("winners_lost") or 0) > int(champion.get("losses_avoided") or 0):
        failures.append("winner_damage_exceeds_losses_avoided")

    if not failures:
        status = "paper_pass_candidate"
    elif "insufficient_fresh_rows" in failures or "insufficient_candidate_blocked_rows" in failures:
        status = "collecting"
    else:
        status = "paper_fail"
    return {
        "status": status,
        "failures": failures,
        "live_policy_change": False,
        "minimum_fresh_rows": int(min_rows),
        "minimum_candidate_blocked_rows": int(min_blocked),
    }


def build_report(
    positions: list[dict[str, Any]],
    *,
    filter_lab: dict[str, Any],
    since_date: date,
    min_rows: int = 20,
    min_blocked: int = 5,
) -> dict[str, Any]:
    rows = [
        row
        for row in positions
        if _is_repair_lane(row)
        and (filled := _position_date(row)) is not None
        and filled >= since_date
    ]
    baseline = summarize_rows(rows)
    thresholds = [evaluate_threshold(rows, threshold=threshold) for threshold in SHADOW_THRESHOLDS]
    champion_id = (
        (filter_lab.get("decision_summary") or {}).get("best_filter_id")
        or (filter_lab.get("paper_validation_plan") or {}).get("candidate_filter_id")
        or "short_term_fill_degradation_ge_15"
    )
    champion = next((item for item in thresholds if item["filter_id"] == champion_id), None)
    if champion is None:
        champion = next(item for item in thresholds if item["filter_id"] == "short_term_fill_degradation_ge_15")
    gate = gate_status(baseline=baseline, champion=champion, min_rows=min_rows, min_blocked=min_blocked)
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_entry_filter_forward_monitor",
        "evidence_boundary": {
            "description": (
                "Read-only paper monitor for the current-policy entry-filter champion. It classifies fresh "
                "tracked rows after the configured since date and does not mutate scanner guardrails."
            ),
            "not_claimed": "This is not promotion evidence until enough fresh rows mature with realized P&L.",
        },
        "inputs": {
            "since_date": since_date.isoformat(),
            "position_count": len(positions),
            "filter_lab_generated_at_utc": filter_lab.get("generated_at_utc"),
            "champion_filter_id": champion["filter_id"],
            "shadow_thresholds": list(SHADOW_THRESHOLDS),
        },
        "baseline": baseline,
        "thresholds": thresholds,
        "champion": champion,
        "gate": gate,
        "lane_counts": dict(Counter(canonical_lane(row) for row in rows).most_common()),
        "ticker_counts": dict(Counter(str(row.get("ticker") or "unknown").upper() for row in rows).most_common(20)),
    }


def _fmt_pct(value: Any) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:+.2f}%"


def render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    champion = report["champion"]
    baseline = report["baseline"]
    lines = [
        "# Current-Policy Entry Filter Paper Monitor",
        "",
        "Read-only forward monitor for the entry-filter champion. It does not change live scanner behavior.",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Since date: `{report['inputs']['since_date']}`",
        f"- Champion: `{report['inputs']['champion_filter_id']}`",
        f"- Gate status: `{gate['status']}`",
        f"- Gate failures: `{', '.join(gate['failures']) or 'none'}`",
        "",
        "## Fresh Cohort",
        "",
        "| Rows | Open | Closed | Priced | Avg | Median | Negatives | <= -50% | <= -90% |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {baseline['rows']} | {baseline['open_rows']} | {baseline['closed_rows']} | {baseline['priced_rows']} | "
            f"{_fmt_pct(baseline['avg_pnl_pct'])} | {_fmt_pct(baseline['median_pnl_pct'])} | "
            f"{baseline['negative_count']} | {baseline['loss_le_50_count']} | {baseline['loss_le_90_count']} |"
        ),
        "",
        "## Threshold Shadows",
        "",
        "| Filter | Matched | Matched Closed | Matched Avg | Deep Losses | Near Total | Winners Lost | Kept Avg | Kept Median |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["thresholds"]:
        matched = item["matched"]
        kept = item["kept"]
        lines.append(
            f"| `{item['filter_id']}` | {matched['rows']} | {matched['closed_rows']} | "
            f"{_fmt_pct(matched['avg_pnl_pct'])} | {item['deep_losses_avoided']} | "
            f"{item['near_total_losses_avoided']} | {item['winners_lost']} | "
            f"{_fmt_pct(kept['avg_pnl_pct'])} | {_fmt_pct(kept['median_pnl_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Decision Read",
            "",
            f"Champion matched `{champion['matched']['rows']}` fresh rows and `{champion['matched']['closed_rows']}` closed rows.",
            "",
            "Keep this monitor in collection mode until the minimum fresh-row and candidate-blocked sample gates are met.",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report["thresholds"]:
        rows.append(
            {
                "filter_id": item["filter_id"],
                "threshold_pct": item["threshold_pct"],
                "matched_rows": item["matched"]["rows"],
                "matched_closed_rows": item["matched"]["closed_rows"],
                "matched_avg_pnl_pct": item["matched"]["avg_pnl_pct"],
                "deep_losses_avoided": item["deep_losses_avoided"],
                "near_total_losses_avoided": item["near_total_losses_avoided"],
                "winners_lost": item["winners_lost"],
                "kept_avg_pnl_pct": item["kept"]["avg_pnl_pct"],
                "kept_median_pnl_pct": item["kept"]["median_pnl_pct"],
            }
        )
    return rows


def write_outputs(report: dict[str, Any], *, output_dir: Path, docs_report: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    csv_path = output_dir / f"{REPORT_ID}_{stamp}.csv"
    latest_csv = output_dir / f"{REPORT_ID}_latest.csv"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "csv": str(csv_path),
        "latest_csv": str(latest_csv),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, default=str)
    markdown = render_markdown(report)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown + "\n", encoding="utf-8")
    latest_md.write_text(markdown + "\n", encoding="utf-8")
    docs_report.write_text(markdown + "\n", encoding="utf-8")
    csv_rows = _csv_rows(report)
    if csv_rows:
        fieldnames = list(csv_rows[0].keys())
        for path in (csv_path, latest_csv):
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(csv_rows)
    else:
        csv_path.write_text("", encoding="utf-8")
        latest_csv.write_text("", encoding="utf-8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor fresh paper rows for the current-policy entry filter champion.")
    parser.add_argument("--filter-lab", type=Path, default=DEFAULT_FILTER_LAB)
    parser.add_argument("--since-date", default=None)
    parser.add_argument("--min-rows", type=int, default=20)
    parser.add_argument("--min-blocked", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_local_env(ROOT)
    filter_lab = json.loads(Path(args.filter_lab).read_text(encoding="utf-8"))
    since_date = _parse_date(args.since_date) if args.since_date else _default_since_date(filter_lab)
    if since_date is None:
        raise ValueError("Unable to resolve since date.")
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository is unavailable."))
    positions = repository.list_positions(None) or []
    report = build_report(
        positions,
        filter_lab=filter_lab,
        since_date=since_date,
        min_rows=int(args.min_rows),
        min_blocked=int(args.min_blocked),
    )
    report["inputs"]["filter_lab"] = str(Path(args.filter_lab))
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=Path(args.output_dir), docs_report=Path(args.docs_report))
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(
            f"{REPORT_ID}: status={report['gate']['status']} rows={report['baseline']['rows']} "
            f"champion_matched={report['champion']['matched']['rows']} failures={','.join(report['gate']['failures']) or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
