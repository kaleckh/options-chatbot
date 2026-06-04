from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "forward-tracking" / "current_policy_historical_stop_grid_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "current-policy-entry-filter-walkforward.md"
REPORT_ID = "current_policy_entry_filter_walkforward"
FROZEN_CHAMPION_FILTER_ID = "short_term_fill_degradation_ge_15"
REPAIR_LANES = ("short_term", "swing", "bullish_momentum", "bullish_pullback_observation")
LOSS_BUCKET_THRESHOLDS = (50, 70, 80, 90, 95, 99)


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


def _lane(row: dict[str, Any]) -> str:
    return str(row.get("lane") or "").strip().lower()


def _ticker(row: dict[str, Any]) -> str:
    return str(row.get("ticker") or "unknown").strip().upper() or "UNKNOWN"


def _entry_month(row: dict[str, Any]) -> str:
    raw = str(row.get("entry_date") or "").strip()
    return raw[:7] if len(raw) >= 7 else "unknown"


def _signal(row: dict[str, Any], key: str) -> Any:
    signals = row.get("entry_signals") if isinstance(row.get("entry_signals"), dict) else {}
    return signals.get(key)


def _pnl(row: dict[str, Any], *, stop_key: str | None = None) -> float | None:
    if stop_key:
        stop_results = row.get("stop_results") if isinstance(row.get("stop_results"), dict) else {}
        stop_result = stop_results.get(stop_key) if isinstance(stop_results.get(stop_key), dict) else {}
        value = _safe_float(stop_result.get("pnl_pct"))
        if value is not None:
            return value
    return _safe_float(row.get("baseline_pnl_pct"))


def _fill_degradation(row: dict[str, Any]) -> float | None:
    return _safe_float(_signal(row, "fill_degradation_pct"))


def matches_frozen_champion(row: dict[str, Any]) -> bool:
    value = _fill_degradation(row)
    return _lane(row) == "short_term" and value is not None and value >= 15.0


def matches_fill_degradation(row: dict[str, Any], *, threshold: float = 15.0) -> bool:
    value = _fill_degradation(row)
    return value is not None and value >= float(threshold)


def matches_lane_fill_degradation(row: dict[str, Any], *, lane: str, threshold: float = 15.0) -> bool:
    return _lane(row) == lane and matches_fill_degradation(row, threshold=threshold)


def _loss_bucket_counts(values: list[float]) -> dict[str, int]:
    return {
        f"loss_le_{threshold}_pct": sum(1 for value in values if value <= -float(threshold))
        for threshold in LOSS_BUCKET_THRESHOLDS
    }


def summarize_rows(rows: list[dict[str, Any]], *, stop_key: str | None = None) -> dict[str, Any]:
    values = [value for row in rows if (value := _pnl(row, stop_key=stop_key)) is not None]
    losses = [value for value in values if value < 0]
    winners = [value for value in values if value > 0]
    total = round(sum(values), 4) if values else 0.0
    return {
        "rows": len(rows),
        "priced": len(values),
        "avg_pnl_pct": round(total / len(values), 4) if values else None,
        "median_pnl_pct": round(float(median(values)), 4) if values else None,
        "sum_pnl_pct": total,
        "negative_count": len(losses),
        "positive_count": len(winners),
        "positive_or_flat_count": len(values) - len(losses),
        "negative_rate_pct": round(len(losses) / len(values) * 100.0, 4) if values else None,
        "loss_bucket_counts": _loss_bucket_counts(values),
    }


def _top_counts(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str], limit: int = 8) -> dict[str, int]:
    return dict(Counter(key_fn(row) for row in rows).most_common(limit))


def _delta(new: Any, old: Any) -> float | None:
    left = _safe_float(new)
    right = _safe_float(old)
    return round(left - right, 4) if left is not None and right is not None else None


def _evaluation_status(
    *,
    baseline: dict[str, Any],
    matched: dict[str, Any],
    kept: dict[str, Any],
    avoided_deep_losses: int,
    lost_winners: int,
    min_rows: int = 10,
    min_matched: int = 3,
) -> str:
    if int(baseline.get("priced") or 0) < min_rows:
        return "sample_too_small"
    if int(matched.get("rows") or 0) == 0:
        return "no_coverage"
    if int(matched.get("priced") or 0) < min_matched:
        return "matched_sample_too_small"
    if avoided_deep_losses <= 0:
        return "no_deep_loss_reduction"
    if lost_winners >= avoided_deep_losses:
        return "winner_damage_too_high"
    matched_sum = _safe_float(matched.get("sum_pnl_pct")) or 0.0
    if matched_sum >= 0:
        return "blocked_set_not_net_negative"
    if (kept.get("avg_pnl_pct") is not None and baseline.get("avg_pnl_pct") is not None) and (
        float(kept["avg_pnl_pct"]) < float(baseline["avg_pnl_pct"])
    ):
        return "kept_avg_worse"
    if (kept.get("median_pnl_pct") is not None and baseline.get("median_pnl_pct") is not None) and (
        float(kept["median_pnl_pct"]) < float(baseline["median_pnl_pct"])
    ):
        return "kept_median_worse"
    if (kept.get("negative_rate_pct") is not None and baseline.get("negative_rate_pct") is not None) and (
        float(kept["negative_rate_pct"]) > float(baseline["negative_rate_pct"])
    ):
        return "kept_negative_rate_worse"
    return "historical_pass_candidate"


def evaluate_filter(
    rows: list[dict[str, Any]],
    *,
    filter_id: str,
    description: str,
    matcher: Callable[[dict[str, Any]], bool],
    min_rows: int = 10,
    min_matched: int = 3,
) -> dict[str, Any]:
    matched_rows = [row for row in rows if matcher(row)]
    kept_rows = [row for row in rows if not matcher(row)]
    baseline = summarize_rows(rows)
    matched = summarize_rows(matched_rows)
    kept = summarize_rows(kept_rows)
    kept_stop_80 = summarize_rows(kept_rows, stop_key="80")
    avoided_losses = sum(1 for row in matched_rows if (value := _pnl(row)) is not None and value < 0)
    avoided_deep_losses = sum(1 for row in matched_rows if (value := _pnl(row)) is not None and value <= -50.0)
    avoided_near_total_losses = sum(1 for row in matched_rows if (value := _pnl(row)) is not None and value <= -90.0)
    lost_winners = sum(1 for row in matched_rows if (value := _pnl(row)) is not None and value > 0)
    status = _evaluation_status(
        baseline=baseline,
        matched=matched,
        kept=kept,
        avoided_deep_losses=avoided_deep_losses,
        lost_winners=lost_winners,
        min_rows=min_rows,
        min_matched=min_matched,
    )
    return {
        "filter_id": filter_id,
        "description": description,
        "status": status,
        "baseline": baseline,
        "matched": matched,
        "kept": kept,
        "kept_with_stop_80": kept_stop_80,
        "deltas_vs_baseline": {
            "kept_avg_pnl_pct": _delta(kept.get("avg_pnl_pct"), baseline.get("avg_pnl_pct")),
            "kept_median_pnl_pct": _delta(kept.get("median_pnl_pct"), baseline.get("median_pnl_pct")),
            "kept_negative_rate_pct": _delta(kept.get("negative_rate_pct"), baseline.get("negative_rate_pct")),
            "kept_stop_80_avg_pnl_pct": _delta(kept_stop_80.get("avg_pnl_pct"), baseline.get("avg_pnl_pct")),
        },
        "avoided_losses": avoided_losses,
        "avoided_deep_losses": avoided_deep_losses,
        "avoided_near_total_losses": avoided_near_total_losses,
        "lost_winners": lost_winners,
        "blocked_sum_delta_if_skipped_pct": round(-float(matched.get("sum_pnl_pct") or 0.0), 4),
        "matched_position_ids": [row.get("position_id") for row in matched_rows],
        "lost_winner_position_ids": [
            row.get("position_id") for row in matched_rows if (value := _pnl(row)) is not None and value > 0
        ],
        "avoided_deep_loss_position_ids": [
            row.get("position_id") for row in matched_rows if (value := _pnl(row)) is not None and value <= -50.0
        ],
        "matched_ticker_counts": _top_counts(matched_rows, _ticker),
        "matched_month_counts": _top_counts(matched_rows, _entry_month),
        "matched_lane_counts": _top_counts(matched_rows, _lane),
        "matched_examples": sorted(
            [
                {
                    "position_id": row.get("position_id"),
                    "ticker": row.get("ticker"),
                    "lane": row.get("lane"),
                    "entry_date": row.get("entry_date"),
                    "pnl_pct": _pnl(row),
                    "fill_degradation_pct": _fill_degradation(row),
                }
                for row in matched_rows
            ],
            key=lambda item: float(item.get("pnl_pct") or 0.0),
        )[:20],
    }


def _months(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(month for month in {_entry_month(row) for row in rows} if month != "unknown")


def _status_is_pass(status: str) -> bool:
    return status == "historical_pass_candidate"


def build_report(stop_grid_report: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in stop_grid_report.get("rows") or []
        if _pnl(row) is not None and (_lane(row) in REPAIR_LANES)
    ]
    months = _months(rows)
    latest_month = months[-1] if months else None
    train_rows = [row for row in rows if latest_month is None or _entry_month(row) < latest_month]
    holdout_rows = [row for row in rows if latest_month is not None and _entry_month(row) == latest_month]

    frozen = evaluate_filter(
        rows,
        filter_id=FROZEN_CHAMPION_FILTER_ID,
        description="Block short_term rows with entry fill degradation >= 15%.",
        matcher=matches_frozen_champion,
    )
    broad = evaluate_filter(
        rows,
        filter_id="all_lanes_fill_degradation_ge_15",
        description="Diagnostic only: block every lane with entry fill degradation >= 15%.",
        matcher=matches_fill_degradation,
    )
    lane_matrix = []
    for lane in REPAIR_LANES:
        lane_rows = [row for row in rows if _lane(row) == lane]
        lane_matrix.append(
            {
                "lane": lane,
                **evaluate_filter(
                    lane_rows,
                    filter_id=f"{lane}_fill_degradation_ge_15",
                    description=f"Diagnostic only: block {lane} rows with entry fill degradation >= 15%.",
                    matcher=lambda row, lane=lane: matches_lane_fill_degradation(row, lane=lane),
                    min_rows=5,
                    min_matched=3,
                ),
            }
        )

    train_eval = evaluate_filter(
        train_rows,
        filter_id=FROZEN_CHAMPION_FILTER_ID,
        description="Calibration slice: frozen short_term fill degradation >= 15%.",
        matcher=matches_frozen_champion,
        min_rows=10,
        min_matched=3,
    )
    holdout_eval = evaluate_filter(
        holdout_rows,
        filter_id=FROZEN_CHAMPION_FILTER_ID,
        description="Latest-month holdout: frozen short_term fill degradation >= 15%.",
        matcher=matches_frozen_champion,
        min_rows=10,
        min_matched=3,
    )
    month_folds = [
        {
            "month": month,
            **evaluate_filter(
                [row for row in rows if _entry_month(row) == month],
                filter_id=FROZEN_CHAMPION_FILTER_ID,
                description=f"Leave-month-read for {month}: frozen short_term fill degradation >= 15%.",
                matcher=matches_frozen_champion,
                min_rows=10,
                min_matched=3,
            ),
        }
        for month in months
    ]
    passing_months = [fold["month"] for fold in month_folds if _status_is_pass(str(fold["status"]))]
    failing_months = [fold["month"] for fold in month_folds if not _status_is_pass(str(fold["status"]))]
    lane_statuses = {item["lane"]: item["status"] for item in lane_matrix}

    if not rows or len(months) < 2:
        status = "insufficient_walkforward_history"
    elif _status_is_pass(str(frozen["status"])) and _status_is_pass(str(train_eval["status"])) and _status_is_pass(
        str(holdout_eval["status"])
    ):
        status = "walkforward_pass_candidate"
    elif _status_is_pass(str(frozen["status"])) and _status_is_pass(str(holdout_eval["status"])):
        status = "mixed_walkforward_watch_not_promoted"
    else:
        status = "walkforward_fail"

    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_all_lanes_entry_filter_walkforward",
        "evidence_boundary": {
            "description": (
                "Read-only all-regular-lanes walk-forward validation for frozen current-policy entry filters. "
                "This uses realized current-policy rows from the exact-contract stop-grid artifact."
            ),
            "not_claimed": (
                "This is not full scanner candidate-generation replay, not fresh paper validation, and not a live "
                "scanner guardrail change."
            ),
        },
        "inputs": {
            "source_report_id": stop_grid_report.get("report_id"),
            "source_generated_at_utc": stop_grid_report.get("generated_at_utc"),
            "row_count": len(rows),
            "months": months,
            "latest_holdout_month": latest_month,
            "lanes": list(REPAIR_LANES),
            "frozen_champion_filter_id": FROZEN_CHAMPION_FILTER_ID,
        },
        "portfolio": {
            "baseline": summarize_rows(rows),
            "frozen_champion": frozen,
            "broad_all_lanes_fill_degradation_ge_15": broad,
        },
        "chronological_holdout": {
            "train_months": [month for month in months if latest_month is None or month < latest_month],
            "holdout_month": latest_month,
            "train": train_eval,
            "holdout": holdout_eval,
        },
        "month_folds": month_folds,
        "lane_matrix": lane_matrix,
        "concentration": {
            "matched_ticker_counts": frozen["matched_ticker_counts"],
            "matched_month_counts": frozen["matched_month_counts"],
            "passing_months": passing_months,
            "failing_months": failing_months,
            "lane_statuses": lane_statuses,
        },
        "decision_summary": {
            "status": status,
            "live_policy_change": False,
            "candidate_filter_id": FROZEN_CHAMPION_FILTER_ID,
            "recommended_next_action": (
                "Keep the frozen short-term fill-degradation filter paper-only; expand point-in-time scanner "
                "candidate replay before promotion, and keep collecting the forward paper monitor."
                if status != "walkforward_pass_candidate"
                else "Review for operator approval after fresh paper monitor also passes; do not auto-promote."
            ),
            "interpretation": (
                "The frozen short-term rule improves the total and latest-month current-policy realized cohort, "
                "but the calibration slice is thin or mixed, and the same fill-degradation rule is not safe as a "
                "global all-lane guardrail."
                if status == "mixed_walkforward_watch_not_promoted"
                else "See fold and lane statuses for promotion blockers."
            ),
        },
    }


def _fmt_pct(value: Any) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:+.2f}%"


def _bucket(summary: dict[str, Any], key: str) -> Any:
    buckets = summary.get("loss_bucket_counts") if isinstance(summary.get("loss_bucket_counts"), dict) else {}
    return buckets.get(key, 0)


def _eval_table_row(label: str, item: dict[str, Any]) -> str:
    matched = item["matched"]
    kept = item["kept"]
    return (
        f"| {label} | `{item['status']}` | {item['baseline']['rows']} | {matched['rows']} | "
        f"{item['avoided_deep_losses']} | {item['avoided_near_total_losses']} | {item['lost_winners']} | "
        f"{_fmt_pct(item['blocked_sum_delta_if_skipped_pct'])} | {_fmt_pct(kept['avg_pnl_pct'])} | "
        f"{_fmt_pct(kept['median_pnl_pct'])} | {_bucket(kept, 'loss_le_90_pct')} |"
    )


def render_markdown(report: dict[str, Any]) -> str:
    decision = report["decision_summary"]
    baseline = report["portfolio"]["baseline"]
    frozen = report["portfolio"]["frozen_champion"]
    broad = report["portfolio"]["broad_all_lanes_fill_degradation_ge_15"]
    holdout = report["chronological_holdout"]
    lines = [
        "# Current-Policy Entry Filter Walk-Forward",
        "",
        "Read-only all-regular-lanes validation for frozen entry filters. It does not change scanner guardrails.",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{decision['status']}`",
        f"- Candidate: `{decision['candidate_filter_id']}`",
        f"- Live policy change: `{decision['live_policy_change']}`",
        f"- Rows / months / lanes: `{report['inputs']['row_count']}` / `{', '.join(report['inputs']['months'])}` / `{', '.join(report['inputs']['lanes'])}`",
        f"- Interpretation: {decision['interpretation']}",
        "",
        "## Portfolio Read",
        "",
        "| Read | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept <= -90% |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        _eval_table_row("Frozen short-term filter", frozen),
        _eval_table_row("Diagnostic all-lane fill >= 15%", broad),
        "",
        "Baseline: "
        f"`{baseline['rows']}` rows, avg `{_fmt_pct(baseline['avg_pnl_pct'])}`, "
        f"median `{_fmt_pct(baseline['median_pnl_pct'])}`, negatives `{baseline['negative_count']}`, "
        f"`<= -50%` `{_bucket(baseline, 'loss_le_50_pct')}`, `<= -90%` `{_bucket(baseline, 'loss_le_90_pct')}`.",
        "",
        "## Chronological Holdout",
        "",
        f"- Train months: `{', '.join(holdout['train_months']) or 'none'}`",
        f"- Holdout month: `{holdout['holdout_month'] or 'none'}`",
        "",
        "| Slice | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept <= -90% |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        _eval_table_row("Train", holdout["train"]),
        _eval_table_row("Latest holdout", holdout["holdout"]),
        "",
        "## Lane Matrix",
        "",
        "| Lane | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["lane_matrix"]:
        lines.append(
            f"| `{item['lane']}` | `{item['status']}` | {item['baseline']['rows']} | {item['matched']['rows']} | "
            f"{item['avoided_deep_losses']} | {item['avoided_near_total_losses']} | {item['lost_winners']} | "
            f"{_fmt_pct(item['blocked_sum_delta_if_skipped_pct'])} | {_fmt_pct(item['kept']['avg_pnl_pct'])} | "
            f"{_fmt_pct(item['kept']['median_pnl_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Month Folds",
            "",
            "| Month | Status | Rows | Matched | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["month_folds"]:
        lines.append(
            f"| `{item['month']}` | `{item['status']}` | {item['baseline']['rows']} | {item['matched']['rows']} | "
            f"{item['avoided_deep_losses']} | {item['avoided_near_total_losses']} | {item['lost_winners']} | "
            f"{_fmt_pct(item['blocked_sum_delta_if_skipped_pct'])} | {_fmt_pct(item['kept']['avg_pnl_pct'])} | "
            f"{_fmt_pct(item['kept']['median_pnl_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Decision Read",
            "",
            f"Recommended next action: {decision['recommended_next_action']}",
            "",
            "Evidence boundary: this is current-policy realized-row walk-forward, not full point-in-time scanner candidate replay.",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add_row(scope: str, label: str, item: dict[str, Any]) -> None:
        rows.append(
            {
                "scope": scope,
                "label": label,
                "filter_id": item["filter_id"],
                "status": item["status"],
                "baseline_rows": item["baseline"]["rows"],
                "matched_rows": item["matched"]["rows"],
                "avoided_deep_losses": item["avoided_deep_losses"],
                "avoided_near_total_losses": item["avoided_near_total_losses"],
                "lost_winners": item["lost_winners"],
                "blocked_sum_delta_if_skipped_pct": item["blocked_sum_delta_if_skipped_pct"],
                "kept_avg_pnl_pct": item["kept"]["avg_pnl_pct"],
                "kept_median_pnl_pct": item["kept"]["median_pnl_pct"],
                "kept_negative_rate_pct": item["kept"]["negative_rate_pct"],
                "kept_loss_le_90_pct": _bucket(item["kept"], "loss_le_90_pct"),
            }
        )

    add_row("portfolio", "frozen_short_term", report["portfolio"]["frozen_champion"])
    add_row("portfolio", "all_lanes_fill_ge_15", report["portfolio"]["broad_all_lanes_fill_degradation_ge_15"])
    add_row("chronological_holdout", "train", report["chronological_holdout"]["train"])
    add_row("chronological_holdout", "holdout", report["chronological_holdout"]["holdout"])
    for item in report["lane_matrix"]:
        add_row("lane", item["lane"], item)
    for item in report["month_folds"]:
        add_row("month", item["month"], item)
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
    fieldnames = list(csv_rows[0].keys()) if csv_rows else []
    for path in (csv_path, latest_csv):
        if not csv_rows:
            path.write_text("", encoding="utf-8")
            continue
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate current-policy entry filters with walk-forward folds.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    source_report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = build_report(source_report)
    report["inputs"]["input"] = str(Path(args.input))
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=Path(args.output_dir), docs_report=Path(args.docs_report))
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        decision = report["decision_summary"]
        frozen = report["portfolio"]["frozen_champion"]
        holdout = report["chronological_holdout"]["holdout"]
        broad = report["portfolio"]["broad_all_lanes_fill_degradation_ge_15"]
        print(
            f"{REPORT_ID}: status={decision['status']} candidate={decision['candidate_filter_id']} "
            f"live_policy_change={decision['live_policy_change']}"
        )
        print(
            f"  frozen: {frozen['status']} matched={frozen['matched']['rows']} "
            f"deep={frozen['avoided_deep_losses']} near_total={frozen['avoided_near_total_losses']} "
            f"lost_winners={frozen['lost_winners']} kept_avg={_fmt_pct(frozen['kept']['avg_pnl_pct'])}"
        )
        print(
            f"  latest_holdout: {holdout['status']} matched={holdout['matched']['rows']} "
            f"kept_avg={_fmt_pct(holdout['kept']['avg_pnl_pct'])}"
        )
        print(
            f"  all_lane_fill15: {broad['status']} matched={broad['matched']['rows']} "
            f"lost_winners={broad['lost_winners']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
