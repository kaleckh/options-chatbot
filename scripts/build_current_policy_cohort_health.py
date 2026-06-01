from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_REPORT = ROOT / "data" / "forward-tracking" / "current_policy_historical_picks_latest.json"
OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DOCS_REPORT = ROOT / "docs" / "current-policy-cohort-health.md"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


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


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _month_key(row: dict[str, Any]) -> str:
    value = str(row.get("entry_date") or "")[:7]
    return value if len(value) == 7 else "unknown"


def _week_key(row: dict[str, Any]) -> str:
    value = str(row.get("entry_date") or "")[:10]
    try:
        iso = date.fromisoformat(value).isocalendar()
    except ValueError:
        return "unknown"
    return f"{iso.year}-W{iso.week:02d}"


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for value in (safe_float(row.get("pnl_pct")) for row in rows) if value is not None]
    if not values:
        return {
            "rows": len(rows),
            "priced": 0,
            "negative": 0,
            "positive_or_flat": 0,
            "avg_pnl_pct": None,
            "median_pnl_pct": None,
            "negative_rate_priced_pct": None,
            "worst_pnl_pct": None,
            "best_pnl_pct": None,
        }
    negative = [value for value in values if value < 0]
    return {
        "rows": len(rows),
        "priced": len(values),
        "negative": len(negative),
        "positive_or_flat": len(values) - len(negative),
        "avg_pnl_pct": round(sum(values) / len(values), 2),
        "median_pnl_pct": round(median(values), 2),
        "negative_rate_priced_pct": round(len(negative) / len(values) * 100.0, 1),
        "worst_pnl_pct": round(min(values), 2),
        "best_pnl_pct": round(max(values), 2),
    }


def classify_cohort(summary: dict[str, Any], *, min_rows: int = 5) -> str:
    priced = int(summary.get("priced") or 0)
    avg = safe_float(summary.get("avg_pnl_pct"))
    med = safe_float(summary.get("median_pnl_pct"))
    neg_rate = safe_float(summary.get("negative_rate_priced_pct"))
    worst = safe_float(summary.get("worst_pnl_pct"))
    if priced == 0:
        return "insufficient_evidence"
    if priced < min_rows:
        if avg is not None and avg < 0 and worst is not None and worst <= -50:
            return "paper_only_thin_severe"
        return "thin_watch"
    if avg is not None and avg < 0:
        return "paper_only_recent_break"
    if med is not None and med < 0 and neg_rate is not None and neg_rate >= 50:
        return "paper_only_recent_break"
    if neg_rate is not None and neg_rate >= 70:
        return "paper_only_recent_break"
    if med is not None and med < 10:
        return "watch_recent_fragile"
    if neg_rate is not None and neg_rate >= 40:
        return "watch_recent_fragile"
    return "healthy"


def _group(rows: list[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return dict(grouped)


def _summaries(grouped: dict[str, list[dict[str, Any]]], *, min_rows: int = 5) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for key, rows in sorted(grouped.items()):
        summary = summarize_rows(rows)
        summary["health_status"] = classify_cohort(summary, min_rows=min_rows)
        output[key] = summary
    return output


def _latest_key(keys: list[str]) -> str | None:
    candidates = sorted(key for key in keys if key and key != "unknown")
    return candidates[-1] if candidates else None


def _best_month(monthly: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    candidates = [
        (key, summary)
        for key, summary in monthly.items()
        if key != "unknown"
        and int(summary.get("priced") or 0) >= 5
        and safe_float(summary.get("avg_pnl_pct")) is not None
    ]
    if not candidates:
        return None, None
    return max(candidates, key=lambda item: float(item[1]["avg_pnl_pct"]))


def _recent_losers(rows: list[dict[str, Any]], recent_month: str | None, limit: int = 20) -> list[dict[str, Any]]:
    if not recent_month:
        return []
    losers = [
        row
        for row in rows
        if _month_key(row) == recent_month
        and safe_float(row.get("pnl_pct")) is not None
        and float(row["pnl_pct"]) < 0
    ]
    return sorted(losers, key=lambda row: float(row["pnl_pct"]))[:limit]


def _recommended_actions(
    *,
    recent_month: str | None,
    monthly: dict[str, dict[str, Any]],
    lane_monthly: dict[str, dict[str, Any]],
    ticker_monthly: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if recent_month:
        recent = monthly.get(recent_month) or {}
        status = str(recent.get("health_status") or "")
        if status.startswith("paper_only"):
            actions.append(
                {
                    "priority": "P0",
                    "scope": f"month:{recent_month}",
                    "action": "Mark current-policy picks paper-only until the recent cohort revalidates.",
                    "evidence": (
                        f"{recent_month} avg={recent.get('avg_pnl_pct')}%, "
                        f"median={recent.get('median_pnl_pct')}%, "
                        f"negative_rate={recent.get('negative_rate_priced_pct')}%."
                    ),
                }
            )
    for key, summary in sorted(lane_monthly.items()):
        month, _, lane = key.partition(":")
        status = str(summary.get("health_status") or "")
        if month == recent_month and status.startswith("paper_only"):
            actions.append(
                {
                    "priority": "P0",
                    "scope": f"lane:{lane}",
                    "action": "Pause this lane or route it to paper-only in the current regime.",
                    "evidence": (
                        f"{key} avg={summary.get('avg_pnl_pct')}%, "
                        f"median={summary.get('median_pnl_pct')}%, "
                        f"negative_rate={summary.get('negative_rate_priced_pct')}%."
                    ),
                }
            )
    severe_tickers = [
        (key, summary)
        for key, summary in ticker_monthly.items()
        if key.startswith(f"{recent_month}:")
        and str(summary.get("health_status") or "").startswith("paper_only")
    ]
    for key, summary in sorted(severe_tickers, key=lambda item: float(item[1].get("avg_pnl_pct") or 0.0))[:10]:
        _, _, ticker = key.partition(":")
        actions.append(
            {
                "priority": "P1",
                "scope": f"ticker:{ticker}",
                "action": "Do not showcase or re-enable this ticker cluster without a fresh recovery cohort.",
                "evidence": (
                    f"{key} avg={summary.get('avg_pnl_pct')}%, "
                    f"median={summary.get('median_pnl_pct')}%, "
                    f"negative_rate={summary.get('negative_rate_priced_pct')}%."
                ),
            }
        )
    return actions


def build_report(current_policy_report: dict[str, Any]) -> dict[str, Any]:
    source_rows = current_policy_report.get("rows") or []
    rows = [
        row
        for row in source_rows
        if row.get("current_policy_decision") == "would_take_today"
        and safe_float(row.get("pnl_pct")) is not None
    ]
    monthly = _summaries(_group(rows, _month_key), min_rows=5)
    weekly = _summaries(_group(rows, _week_key), min_rows=3)
    lane_monthly = _summaries(
        _group(rows, lambda row: f"{_month_key(row)}:{row.get('lane') or 'unknown'}"),
        min_rows=5,
    )
    ticker_monthly = _summaries(
        _group(rows, lambda row: f"{_month_key(row)}:{row.get('ticker') or 'unknown'}"),
        min_rows=2,
    )
    recent_month = _latest_key(list(monthly))
    recent_week = _latest_key(list(weekly))
    best_month, best_month_summary = _best_month(monthly)
    recent_month_summary = monthly.get(recent_month or "") if recent_month else None
    recent_week_summary = weekly.get(recent_week or "") if recent_week else None
    recent_status = str((recent_month_summary or {}).get("health_status") or "insufficient_evidence")
    latest_week_status = str((recent_week_summary or {}).get("health_status") or "insufficient_evidence")
    if latest_week_status.startswith("paper_only"):
        overall_status = "paper_only_recent_week_break"
    elif recent_status.startswith("paper_only"):
        overall_status = "paper_only_recent_month_break"
    elif recent_status.startswith("watch"):
        overall_status = "watch_recent_fragile"
    else:
        overall_status = recent_status

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_supervised_trading_desk_current_policy_cohort_health",
        "input": {
            "path": _rel(INPUT_REPORT),
            "generated_at_utc": current_policy_report.get("generated_at_utc"),
        },
        "summary": {
            "current_policy_rows": len(rows),
            "overall": summarize_rows(rows),
            "overall_status": overall_status,
            "showcase_month": best_month,
            "showcase_month_summary": best_month_summary,
            "recent_month": recent_month,
            "recent_month_summary": recent_month_summary,
            "recent_week": recent_week,
            "recent_week_summary": recent_week_summary,
            "status_interpretation": (
                "April-like historical cohorts can be shown as a discovered edge, but recent broken cohorts should be paper-only until revalidated."
                if overall_status.startswith("paper_only")
                else "Recent cohort remains showable with monitoring."
            ),
        },
        "monthly": monthly,
        "weekly": weekly,
        "lane_monthly": lane_monthly,
        "ticker_monthly": ticker_monthly,
        "recent_month_losers": _recent_losers(rows, recent_month),
        "recommended_actions": _recommended_actions(
            recent_month=recent_month,
            monthly=monthly,
            lane_monthly=lane_monthly,
            ticker_monthly=ticker_monthly,
        ),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _summary_row(label: str, summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    return (
        f"| {label} | {summary.get('priced', 0)} | {summary.get('avg_pnl_pct', '')}% | "
        f"{summary.get('median_pnl_pct', '')}% | {summary.get('negative_rate_priced_pct', '')}% | "
        f"{summary.get('health_status', '')} |"
    )


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Current-Policy Cohort Health",
        "",
        "This report separates the strong April current-policy cohort from the broken recent cohort. It is a read-only regime health and paper-only recommendation layer; it does not rewrite historical P&L.",
        "",
        "## Headline",
        "",
        f"- Overall status: `{summary['overall_status']}`.",
        f"- Showcase month: `{summary.get('showcase_month')}`.",
        f"- Recent month: `{summary.get('recent_month')}`.",
        f"- Recent week: `{summary.get('recent_week')}`.",
        f"- Interpretation: {summary['status_interpretation']}",
        "",
        "| Cohort | Priced | Avg P&L | Median P&L | Negative Rate | Health |",
        "|---|---:|---:|---:|---:|---|",
        _summary_row("Overall current policy", {**summary["overall"], "health_status": summary["overall_status"]}),
        _summary_row(f"Showcase {summary.get('showcase_month')}", summary.get("showcase_month_summary")),
        _summary_row(f"Recent {summary.get('recent_month')}", summary.get("recent_month_summary")),
        _summary_row(f"Recent {summary.get('recent_week')}", summary.get("recent_week_summary")),
        "",
        "## Monthly Cohorts",
        "",
        "| Month | Priced | Avg P&L | Median P&L | Negative Rate | Health |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for month, item in report.get("monthly", {}).items():
        lines.append(_summary_row(month, item))
    lines.extend(
        [
            "",
            "## Lane By Recent Month",
            "",
            "| Lane Cohort | Priced | Avg P&L | Median P&L | Negative Rate | Health |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    recent_month = summary.get("recent_month")
    for key, item in report.get("lane_monthly", {}).items():
        if not str(key).startswith(f"{recent_month}:"):
            continue
        lines.append(_summary_row(key, item))
    lines.extend(
        [
            "",
            "## Recent Month Losers",
            "",
            "| Trade | Ticker | Lane | Entry | Closed | P&L |",
            "|---:|---|---|---|---|---:|",
        ]
    )
    for row in report.get("recent_month_losers") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("trade_id")),
                    _fmt(row.get("ticker")),
                    _fmt(row.get("lane")),
                    _fmt(row.get("entry_date")),
                    _fmt(row.get("closed_at")),
                    f"{row.get('pnl_pct')}%",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions") or []:
        lines.append(
            f"- **{action['priority']}** `{action['scope']}`: {action['action']} Evidence: {action['evidence']}"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, docs_report: Path = DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"current_policy_cohort_health_{stamp}.json"
    latest_json = output_dir / "current_policy_cohort_health_latest.json"
    md_path = output_dir / f"current_policy_cohort_health_{stamp}.md"
    latest_md = output_dir / "current_policy_cohort_health_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    docs_report.write_text(markdown, encoding="utf-8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build current-policy cohort health readback.")
    parser.add_argument("--input", default=str(INPUT_REPORT), help="Current-policy historical picks report JSON.")
    parser.add_argument("--json", action="store_true", help="Print the generated report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Build without writing artifacts.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--doc-path", default=str(DOCS_REPORT))
    args = parser.parse_args(argv)

    report = build_report(_load_json(Path(args.input)))
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=Path(args.output_dir), docs_report=Path(args.doc_path))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
