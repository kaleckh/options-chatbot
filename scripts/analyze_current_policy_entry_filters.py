from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "forward-tracking" / "current_policy_historical_stop_grid_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "current-policy-entry-filter-lab.md"
REPORT_ID = "current_policy_entry_filter_lab"
LOSS_BUCKET_THRESHOLDS = (50, 70, 80, 90, 95, 99)


@dataclass(frozen=True)
class FilterCandidate:
    filter_id: str
    description: str
    matcher: Callable[[dict[str, Any]], bool]
    research_only_reason: str


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


def _entry_month(row: dict[str, Any]) -> str:
    raw = str(row.get("entry_date") or "").strip()
    return raw[:7] if len(raw) >= 7 else "unknown"


def _is_loss(row: dict[str, Any]) -> bool:
    value = _pnl(row)
    return value is not None and value < 0


def _is_winner(row: dict[str, Any]) -> bool:
    value = _pnl(row)
    return value is not None and value > 0


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


def _top_counts(rows: list[dict[str, Any]], key: str, limit: int = 8) -> dict[str, int]:
    return dict(Counter(str(row.get(key) or "unknown") for row in rows).most_common(limit))


def _month_breakdown(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    months = sorted({_entry_month(row) for row in rows})
    return {month: summarize_rows([row for row in rows if _entry_month(row) == month]) for month in months}


def _latest_month(rows: list[dict[str, Any]]) -> str | None:
    months = sorted(month for month in {_entry_month(row) for row in rows} if month != "unknown")
    return months[-1] if months else None


def _repeat_loss_tickers(rows: list[dict[str, Any]], *, loss_threshold_pct: float, min_count: int) -> set[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = _pnl(row)
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and value is not None and value <= -abs(float(loss_threshold_pct)):
            counts[ticker] += 1
    return {ticker for ticker, count in counts.items() if count >= int(min_count)}


def build_filter_candidates(rows: list[dict[str, Any]]) -> list[FilterCandidate]:
    repeat_tickers = _repeat_loss_tickers(rows, loss_threshold_pct=50.0, min_count=2)

    def fill_ge(row: dict[str, Any], threshold: float) -> bool:
        value = _safe_float(_signal(row, "fill_degradation_pct"))
        return value is not None and value >= threshold

    def quality_lt(row: dict[str, Any], threshold: float) -> bool:
        value = _safe_float(_signal(row, "quality_score"))
        return value is not None and value < threshold

    def lane(row: dict[str, Any], value: str) -> bool:
        return str(row.get("lane") or "").strip().lower() == value

    def repeat_ticker(row: dict[str, Any]) -> bool:
        return str(row.get("ticker") or "").strip().upper() in repeat_tickers

    candidates = []
    for threshold in (10.0, 12.5, 14.0, 15.0, 16.0, 17.5, 20.0):
        label = str(int(threshold)) if float(threshold).is_integer() else str(threshold).replace(".", "_")
        candidates.append(
            FilterCandidate(
                f"short_term_fill_degradation_ge_{label}",
                f"Block short_term rows with entry fill degradation >= {threshold:g}%.",
                lambda row, threshold=threshold: lane(row, "short_term") and fill_ge(row, threshold),
                "Threshold sweep for the loss cohort's short_term execution-quality signal.",
            )
        )
    candidates.extend(
        [
        FilterCandidate(
            "fill_degradation_ge_15",
            "Block rows with entry fill degradation >= 15%.",
            lambda row: fill_ge(row, 15.0),
            "Threshold was selected after observing the current-policy loss cohort.",
        ),
        FilterCandidate(
            "quality_lt_60",
            "Block rows with quality score below 60.",
            lambda row: quality_lt(row, 60.0),
            "Threshold was selected after observing the current-policy loss cohort.",
        ),
        FilterCandidate(
            "short_term_quality_lt_60",
            "Block short_term rows with quality score below 60.",
            lambda row: lane(row, "short_term") and quality_lt(row, 60.0),
            "Targets the loss cohort's short_term concentration.",
        ),
        FilterCandidate(
            "repeat_deep_loss_ticker",
            "Block tickers that appear at least twice in the <= -50% loss cohort.",
            repeat_ticker,
            "Uses loss-cohort ticker clusters and must be validated out of sample.",
        ),
        FilterCandidate(
            "short_term_repeat_deep_loss_ticker",
            "Block short_term rows for tickers that appear at least twice in the <= -50% loss cohort.",
            lambda row: lane(row, "short_term") and repeat_ticker(row),
            "Uses loss-cohort ticker clusters and must be validated out of sample.",
        ),
        FilterCandidate(
            "short_term_fill15_or_quality60",
            "Block short_term rows with fill degradation >= 15% or quality score below 60.",
            lambda row: lane(row, "short_term") and (fill_ge(row, 15.0) or quality_lt(row, 60.0)),
            "Compound filter from the two strongest loss-cohort entry-quality signals.",
        ),
        FilterCandidate(
            "short_term_loss_cohort_combo_v1",
            "Block short_term rows with fill >= 15%, quality < 60, or repeat deep-loss ticker.",
            lambda row: lane(row, "short_term")
            and (fill_ge(row, 15.0) or quality_lt(row, 60.0) or repeat_ticker(row)),
            "Data-mined compound filter; research-only unless it passes fresh paper validation.",
        ),
        ]
    )
    return candidates


def _promotion_status(
    *,
    baseline: dict[str, Any],
    blocked: dict[str, Any],
    kept: dict[str, Any],
    avoided_deep_losses: int,
    lost_winners: int,
) -> str:
    if blocked["rows"] == 0:
        return "no_coverage"
    if blocked["priced"] < 3:
        return "sample_too_small"
    if avoided_deep_losses <= 0:
        return "no_deep_loss_reduction"
    if lost_winners >= avoided_deep_losses:
        return "winner_damage_too_high"
    if kept["negative_count"] > baseline["negative_count"]:
        return "kept_negative_count_worse"
    if (kept["avg_pnl_pct"] or -10_000.0) < (baseline["avg_pnl_pct"] or -10_000.0):
        return "kept_avg_worse"
    if (kept["median_pnl_pct"] or -10_000.0) < (baseline["median_pnl_pct"] or -10_000.0):
        return "kept_median_worse"
    if blocked["sum_pnl_pct"] >= 0:
        return "blocked_set_not_net_negative"
    return "paper_research_candidate"


def evaluate_filter(rows: list[dict[str, Any]], candidate: FilterCandidate, baseline: dict[str, Any]) -> dict[str, Any]:
    blocked_rows = [row for row in rows if candidate.matcher(row)]
    kept_rows = [row for row in rows if not candidate.matcher(row)]
    blocked = summarize_rows(blocked_rows)
    kept = summarize_rows(kept_rows)
    kept_stop_80 = summarize_rows(kept_rows, stop_key="80")
    avoided_deep_losses = sum(1 for row in blocked_rows if (value := _pnl(row)) is not None and value <= -50.0)
    avoided_near_total_losses = sum(1 for row in blocked_rows if (value := _pnl(row)) is not None and value <= -90.0)
    lost_winners = sum(1 for row in blocked_rows if _is_winner(row))
    avoided_losses = sum(1 for row in blocked_rows if _is_loss(row))
    status = _promotion_status(
        baseline=baseline,
        blocked=blocked,
        kept=kept,
        avoided_deep_losses=avoided_deep_losses,
        lost_winners=lost_winners,
    )
    latest_month = _latest_month(rows)
    kept_by_month = _month_breakdown(kept_rows)
    blocked_by_month = _month_breakdown(blocked_rows)
    latest_kept = kept_by_month.get(latest_month or "", {})
    latest_kept_median = _safe_float(latest_kept.get("median_pnl_pct"))
    if status == "paper_research_candidate" and latest_kept_median is not None and latest_kept_median <= 0:
        status = "paper_research_candidate_recent_unproven"
    return {
        "filter_id": candidate.filter_id,
        "description": candidate.description,
        "research_only_reason": candidate.research_only_reason,
        "status": status,
        "blocked": blocked,
        "kept": kept,
        "kept_with_stop_80": kept_stop_80,
        "kept_stop_80_avg_delta_vs_kept_pct": (
            round(float(kept_stop_80["avg_pnl_pct"]) - float(kept["avg_pnl_pct"]), 4)
            if kept_stop_80.get("avg_pnl_pct") is not None and kept.get("avg_pnl_pct") is not None
            else None
        ),
        "avoided_losses": avoided_losses,
        "avoided_deep_losses": avoided_deep_losses,
        "avoided_near_total_losses": avoided_near_total_losses,
        "lost_winners": lost_winners,
        "lost_winner_sum_pnl_pct": round(
            sum(float(_pnl(row) or 0.0) for row in blocked_rows if _is_winner(row)),
            4,
        ),
        "blocked_sum_delta_if_skipped_pct": round(-float(blocked["sum_pnl_pct"] or 0.0), 4),
        "blocked_lane_counts": _top_counts(blocked_rows, "lane"),
        "blocked_ticker_counts": _top_counts(blocked_rows, "ticker"),
        "blocked_position_ids": [row.get("position_id") for row in blocked_rows],
        "lost_winner_position_ids": [row.get("position_id") for row in blocked_rows if _is_winner(row)],
        "avoided_deep_loss_position_ids": [
            row.get("position_id")
            for row in blocked_rows
            if (value := _pnl(row)) is not None and value <= -50.0
        ],
        "avoided_near_total_loss_position_ids": [
            row.get("position_id")
            for row in blocked_rows
            if (value := _pnl(row)) is not None and value <= -90.0
        ],
        "latest_entry_month": latest_month,
        "latest_month_kept": latest_kept,
        "blocked_by_entry_month": blocked_by_month,
        "kept_by_entry_month": kept_by_month,
        "blocked_examples": sorted(
            [
                {
                    "position_id": row.get("position_id"),
                    "ticker": row.get("ticker"),
                    "lane": row.get("lane"),
                    "entry_date": row.get("entry_date"),
                    "pnl_pct": row.get("baseline_pnl_pct"),
                    "fill_degradation_pct": _signal(row, "fill_degradation_pct"),
                    "quality_score": _signal(row, "quality_score"),
                }
                for row in blocked_rows
            ],
            key=lambda item: float(item.get("pnl_pct") or 0.0),
        )[:20],
    }


def build_report(stop_grid_report: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in stop_grid_report.get("rows") or [] if _pnl(row) is not None]
    baseline = summarize_rows(rows)
    baseline_stop_80 = summarize_rows(rows, stop_key="80")
    candidates = build_filter_candidates(rows)
    evaluations = [evaluate_filter(rows, candidate, baseline) for candidate in candidates]
    evaluations.sort(
        key=lambda item: (
            item["status"] in {"paper_research_candidate", "paper_research_candidate_recent_unproven"},
            item["status"] == "paper_research_candidate",
            int(item["avoided_near_total_losses"]),
            int(item["avoided_deep_losses"]),
            -int(item["lost_winners"]),
            float(item["kept"].get("avg_pnl_pct") or -10_000.0),
        ),
        reverse=True,
    )
    research_candidates = [
        item
        for item in evaluations
        if item["status"] in {"paper_research_candidate", "paper_research_candidate_recent_unproven"}
    ]
    best = research_candidates[0] if research_candidates else None
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_trading_desk_current_policy_entry_filter_lab",
        "evidence_boundary": {
            "description": (
                "Read-only historical-paper/current-policy entry-filter lab. It ranks candidate filters "
                "against realized current-policy rows and does not mutate scanner guardrails."
            ),
            "not_claimed": "This is not fresh paper validation or production proof.",
        },
        "inputs": {
            "source_report_id": stop_grid_report.get("report_id"),
            "source_generated_at_utc": stop_grid_report.get("generated_at_utc"),
            "row_count": len(rows),
            "repeat_deep_loss_tickers": sorted(_repeat_loss_tickers(rows, loss_threshold_pct=50.0, min_count=2)),
        },
        "baseline": baseline,
        "baseline_with_stop_80": baseline_stop_80,
        "filters": evaluations,
        "decision_summary": {
            "status": "paper_research_candidates_found" if research_candidates else "no_candidate_filter",
            "best_filter_id": best["filter_id"] if best else None,
            "research_candidate_count": len(research_candidates),
            "recommended_next_action": (
                "Paper-test the best candidate filters on fresh scans before changing promoted scanner guardrails."
                if research_candidates
                else "Do not change entry guardrails; gather more paper rows or test different features."
            ),
        },
        "paper_validation_plan": {
            "candidate_filter_id": best["filter_id"] if best else None,
            "candidate_status": best["status"] if best else None,
            "live_policy_change": False,
            "minimum_fresh_current_policy_rows": 20,
            "minimum_fresh_blocked_candidate_rows": 5,
            "pass_bar": [
                "fresh kept-row median P&L above 0%",
                "fresh kept-row negative rate below 40%",
                "candidate-blocked rows must be net negative or include at least 2 losses <= -50%",
                "lost fresh winners must not exceed fresh losses avoided",
            ],
            "fail_bar": [
                "candidate only works on historical paper rows",
                "fresh blocked rows include more winners than losers",
                "fresh kept rows remain negative-median",
            ],
            "operator_action": (
                "Tag matching paper candidates for review/monitoring; do not block live scanner output yet."
                if best
                else "No paper validation candidate selected."
            ),
        },
    }


def _fmt_pct(value: Any) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:+.2f}%"


def render_markdown(report: dict[str, Any]) -> str:
    baseline = report["baseline"]
    lines = [
        "# Current-Policy Entry Filter Lab",
        "",
        "Read-only current-policy filter lab. Candidate filters are research-only unless they pass fresh paper validation.",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Source rows: `{report['inputs']['row_count']}`",
        f"- Repeat deep-loss tickers: `{', '.join(report['inputs']['repeat_deep_loss_tickers']) or 'none'}`",
        "",
        "## Baseline",
        "",
        "| Rows | Avg | Median | Negatives | <= -50% | <= -90% |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {baseline['rows']} | {_fmt_pct(baseline['avg_pnl_pct'])} | {_fmt_pct(baseline['median_pnl_pct'])} | "
            f"{baseline['negative_count']} | {baseline['loss_bucket_counts']['loss_le_50_pct']} | "
            f"{baseline['loss_bucket_counts']['loss_le_90_pct']} |"
        ),
        "",
        "Baseline with daily close-check `stop_80`: "
        f"avg `{_fmt_pct(report['baseline_with_stop_80']['avg_pnl_pct'])}`, "
        f"median `{_fmt_pct(report['baseline_with_stop_80']['median_pnl_pct'])}`, "
        f"`{report['baseline_with_stop_80']['negative_count']}` negatives, "
        f"`{report['baseline_with_stop_80']['loss_bucket_counts']['loss_le_90_pct']}` rows `<= -90%`.",
        "",
        "## Candidate Filters",
        "",
        "| Filter | Status | Blocked | Avoided <= -50% | Avoided <= -90% | Lost winners | Blocked sum delta | Kept avg | Kept median | Kept+80 avg | Kept+80 <= -90% |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.get("filters") or []:
        lines.append(
            f"| `{item['filter_id']}` | `{item['status']}` | {item['blocked']['rows']} | "
            f"{item['avoided_deep_losses']} | {item['avoided_near_total_losses']} | {item['lost_winners']} | "
            f"{_fmt_pct(item['blocked_sum_delta_if_skipped_pct'])} | {_fmt_pct(item['kept']['avg_pnl_pct'])} | "
            f"{_fmt_pct(item['kept']['median_pnl_pct'])} | {_fmt_pct(item['kept_with_stop_80']['avg_pnl_pct'])} | "
            f"{item['kept_with_stop_80']['loss_bucket_counts']['loss_le_90_pct']} |"
        )
    lines.extend(["", "## Latest Month Kept Read", ""])
    lines.append("| Filter | Latest Month | Kept Rows | Kept Avg | Kept Median | Kept Negatives |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for item in report.get("filters") or []:
        latest = item.get("latest_month_kept") or {}
        lines.append(
            f"| `{item['filter_id']}` | `{item.get('latest_entry_month') or 'n/a'}` | "
            f"{latest.get('rows', 0)} | {_fmt_pct(latest.get('avg_pnl_pct'))} | "
            f"{_fmt_pct(latest.get('median_pnl_pct'))} | {latest.get('negative_count', 0)} |"
        )
    decision = report.get("decision_summary") or {}
    lines.extend(
        [
            "",
            "## Decision Read",
            "",
            f"Status: `{decision.get('status')}`",
            "",
            f"Best filter: `{decision.get('best_filter_id') or 'none'}`",
            "",
            f"Recommended next action: {decision.get('recommended_next_action')}",
            "",
            "## Paper Validation Plan",
            "",
        ]
    )
    plan = report.get("paper_validation_plan") or {}
    lines.extend(
        [
            f"- Candidate: `{plan.get('candidate_filter_id') or 'none'}`",
            f"- Live policy change: `{plan.get('live_policy_change')}`",
            f"- Minimum fresh rows: `{plan.get('minimum_fresh_current_policy_rows')}` current-policy rows and `{plan.get('minimum_fresh_blocked_candidate_rows')}` candidate-blocked rows.",
            f"- Operator action: {plan.get('operator_action')}",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("filters") or []:
        rows.append(
            {
                "filter_id": item["filter_id"],
                "status": item["status"],
                "blocked_rows": item["blocked"]["rows"],
                "blocked_avg_pnl_pct": item["blocked"]["avg_pnl_pct"],
                "kept_avg_pnl_pct": item["kept"]["avg_pnl_pct"],
                "kept_median_pnl_pct": item["kept"]["median_pnl_pct"],
                "kept_stop_80_avg_pnl_pct": item["kept_with_stop_80"]["avg_pnl_pct"],
                "kept_stop_80_median_pnl_pct": item["kept_with_stop_80"]["median_pnl_pct"],
                "kept_stop_80_loss_le_90_pct": item["kept_with_stop_80"]["loss_bucket_counts"]["loss_le_90_pct"],
                "avoided_losses": item["avoided_losses"],
                "avoided_deep_losses": item["avoided_deep_losses"],
                "avoided_near_total_losses": item["avoided_near_total_losses"],
                "lost_winners": item["lost_winners"],
                "blocked_sum_delta_if_skipped_pct": item["blocked_sum_delta_if_skipped_pct"],
                "latest_entry_month": item.get("latest_entry_month"),
                "latest_month_kept_avg_pnl_pct": (item.get("latest_month_kept") or {}).get("avg_pnl_pct"),
                "latest_month_kept_median_pnl_pct": (item.get("latest_month_kept") or {}).get("median_pnl_pct"),
                "latest_month_kept_negative_count": (item.get("latest_month_kept") or {}).get("negative_count"),
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
    parser = argparse.ArgumentParser(description="Analyze current-policy entry-filter candidates.")
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
        print(
            f"{REPORT_ID}: status={decision['status']} best={decision.get('best_filter_id') or 'none'} "
            f"candidates={decision['research_candidate_count']}"
        )
        for item in report.get("filters", [])[:8]:
            print(
                f"  {item['filter_id']}: {item['status']} blocked={item['blocked']['rows']} "
                f"deep={item['avoided_deep_losses']} near_total={item['avoided_near_total_losses']} "
                f"lost_winners={item['lost_winners']} kept_avg={_fmt_pct(item['kept']['avg_pnl_pct'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
