from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "short_term_filter_point_in_time_replay"
CHAMPION_FILTER_ID = "short_term_fill_degradation_ge_15"
DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_STOP_GRID = ROOT / "data" / "forward-tracking" / "current_policy_historical_stop_grid_latest.json"
DEFAULT_STARVATION_AUDIT = ROOT / "data" / "forward-tracking" / "regular_guardrail_starvation_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "current-policy-entry-filter-point-in-time.md"


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _lane(row: dict[str, Any]) -> str:
    return _norm_text(row.get("playbook_id") or row.get("lane")).lower()


def _fill_degradation(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("fill_degradation_vs_mid_pct") or row.get("fill_degradation_pct"))


def matches_champion(row: dict[str, Any]) -> bool:
    value = _fill_degradation(row)
    return _lane(row) == "short_term" and value is not None and value >= 15.0


def _position_id(row: dict[str, Any]) -> int | None:
    for key in ("auto_track_position_id", "position_id", "tracked_position_id", "id"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _stop_grid_rows_by_position(stop_grid: dict[str, Any]) -> dict[int, dict[str, Any]]:
    by_position: dict[int, dict[str, Any]] = {}
    for row in list(stop_grid.get("rows") or []):
        if not isinstance(row, dict):
            continue
        position_id = _position_id(row)
        if position_id is not None:
            by_position[position_id] = row
    return by_position


def _pnl(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("baseline_pnl_pct") or row.get("pnl_pct") or row.get("net_pnl_pct"))


def _has_asof_executable_entry(row: dict[str, Any]) -> bool:
    label = _norm_text(row.get("candidate_execution_label")).lower()
    basis = _norm_text(row.get("attempted_limit_basis") or row.get("entry_execution_basis")).lower()
    if "stale" in label or "fallback" in label or "manual" in basis:
        return False
    if "executable" in label and "opra" in label:
        return True
    return basis in {"spread_ask_bid", "ask", "bid_ask", "spread_bid_ask"}


def _candidate_record(row: dict[str, Any], stop_grid_by_position: dict[int, dict[str, Any]]) -> dict[str, Any]:
    position_id = _position_id(row)
    stop_row = stop_grid_by_position.get(position_id or -1, {})
    pnl = _pnl(stop_row) if stop_row else _pnl(row)
    exact_priced = pnl is not None and position_id is not None and _has_asof_executable_entry(row)
    reason = None
    if pnl is None:
        reason = "missing_realized_pnl"
    elif position_id is None:
        reason = "missing_tracked_position_link"
    elif not _has_asof_executable_entry(row):
        reason = "entry_not_fresh_executable_opra_nbbo"
    return {
        "candidate_key": "|".join(
            [
                _norm_text(row.get("scan_date")),
                _lane(row),
                _norm_text(row.get("ticker")).upper(),
                _norm_text(row.get("direction")).lower(),
                _norm_text(row.get("expiry"))[:10],
                _norm_text((row.get("selected_spread") or {}).get("long_contract_symbol")).upper()
                if isinstance(row.get("selected_spread"), dict)
                else "",
            ]
        ),
        "scan_date": row.get("scan_date"),
        "playbook_id": row.get("playbook_id"),
        "ticker": row.get("ticker"),
        "direction": row.get("direction"),
        "expiry": row.get("expiry"),
        "position_id": position_id,
        "matched_champion_filter": matches_champion(row),
        "fill_degradation_pct": _fill_degradation(row),
        "candidate_execution_label": row.get("candidate_execution_label"),
        "attempted_limit_basis": row.get("attempted_limit_basis"),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "fill_outcome_reason": row.get("fill_outcome_reason"),
        "exact_priced": exact_priced,
        "unpriced_reason": reason,
        "baseline_pnl_pct": pnl if exact_priced else None,
        "raw_pnl_pct": pnl,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["baseline_pnl_pct"]) for row in rows if row.get("baseline_pnl_pct") is not None]
    losses = [value for value in values if value < 0]
    winners = [value for value in values if value > 0]
    return {
        "rows": len(rows),
        "exact_priced_rows": len(values),
        "avg_pnl_pct": round(sum(values) / len(values), 4) if values else None,
        "median_pnl_pct": round(float(median(values)), 4) if values else None,
        "sum_pnl_pct": round(sum(values), 4) if values else 0.0,
        "negative_count": len(losses),
        "positive_count": len(winners),
        "negative_rate_pct": round(len(losses) / len(values) * 100.0, 4) if values else None,
        "loss_le_50_count": sum(1 for value in values if value <= -50.0),
        "loss_le_90_count": sum(1 for value in values if value <= -90.0),
    }


def _zero_pick_days(starvation_audit: dict[str, Any]) -> list[str]:
    days: set[str] = set()
    generated = _norm_text(starvation_audit.get("generated_at_utc"))
    for playbook in list(starvation_audit.get("playbooks") or []):
        if not isinstance(playbook, dict):
            continue
        if _norm_text(playbook.get("playbook_id")).lower() != "short_term":
            continue
        returned = int(playbook.get("returned_count") or len(playbook.get("returned_picks") or []))
        if returned == 0 and generated:
            days.add(generated[:10])
    return sorted(days)


def build_report(
    *,
    fill_attempt_rows: list[dict[str, Any]],
    stop_grid: dict[str, Any],
    starvation_audit: dict[str, Any],
) -> dict[str, Any]:
    stop_grid_by_position = _stop_grid_rows_by_position(stop_grid)
    shown_rows = [
        row
        for row in fill_attempt_rows
        if _norm_text(row.get("event_type")) in {"", "candidate_shown"}
        and _norm_text(row.get("status")) in {"", "shown"}
    ]
    candidate_rows = [_candidate_record(row, stop_grid_by_position) for row in shown_rows]
    matched = [row for row in candidate_rows if row["matched_champion_filter"]]
    kept = [row for row in candidate_rows if not row["matched_champion_filter"]]
    matched_summary = _summarize(matched)
    kept_summary = _summarize(kept)
    baseline_summary = _summarize(candidate_rows)
    unpriced = [row for row in candidate_rows if not row["exact_priced"]]
    lost_winners = sum(1 for row in matched if (value := row.get("baseline_pnl_pct")) is not None and float(value) > 0)
    avoided_losses = sum(1 for row in matched if (value := row.get("baseline_pnl_pct")) is not None and float(value) < 0)
    zero_pick_days = _zero_pick_days(starvation_audit)
    status = "paper_only_collecting"
    blockers: list[str] = []
    if baseline_summary["exact_priced_rows"] < 20:
        blockers.append("insufficient_exact_priced_candidate_rows")
    if matched_summary["exact_priced_rows"] < 5:
        blockers.append("insufficient_champion_matched_blocked_rows")
    if matched_summary["sum_pnl_pct"] >= 0 and matched_summary["loss_le_50_count"] < 2:
        blockers.append("matched_rows_not_net_harmful_or_deep_loss")
    if lost_winners > avoided_losses:
        blockers.append("winner_damage_exceeds_losses_avoided")
    if unpriced:
        blockers.append("unpriced_or_non_executable_rows_present")
    if not blockers:
        status = "point_in_time_replay_pass_candidate_not_promoted"
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_short_term_entry_filter_point_in_time_replay",
        "evidence_boundary": {
            "description": (
                "Read-only point-in-time scanner candidate replay for the short-term fill-degradation "
                "champion. It uses logged as-of candidate fields and exact priced tracked outcomes only."
            ),
            "not_claimed": "This does not change live scanner guardrails or exit policy.",
        },
        "inputs": {
            "fill_attempt_rows": len(fill_attempt_rows),
            "shown_candidate_rows": len(candidate_rows),
            "stop_grid_report_id": stop_grid.get("report_id"),
            "stop_grid_generated_at_utc": stop_grid.get("generated_at_utc"),
            "starvation_audit_report_id": starvation_audit.get("report_id"),
            "starvation_audit_generated_at_utc": starvation_audit.get("generated_at_utc"),
        },
        "filter": {
            "filter_id": CHAMPION_FILTER_ID,
            "live_policy_change": False,
            "matcher": "playbook_id == short_term and fill_degradation_vs_mid_pct >= 15",
        },
        "baseline": baseline_summary,
        "matched": matched_summary,
        "kept": kept_summary,
        "effects": {
            "avoided_losses": avoided_losses,
            "avoided_deep_losses": matched_summary["loss_le_50_count"],
            "avoided_near_total_losses": matched_summary["loss_le_90_count"],
            "lost_winners": lost_winners,
            "blocked_sum_delta_if_skipped_pct": round(-float(matched_summary["sum_pnl_pct"] or 0.0), 4),
        },
        "coverage": {
            "zero_pick_days": zero_pick_days,
            "zero_pick_day_count": len(zero_pick_days),
            "unpriced_or_non_executable_count": len(unpriced),
            "unpriced_reasons": dict(Counter(str(row.get("unpriced_reason") or "unknown") for row in unpriced)),
            "matched_ticker_counts": dict(Counter(str(row.get("ticker") or "unknown").upper() for row in matched)),
        },
        "decision_summary": {
            "status": status,
            "promotion_blockers": blockers,
            "recommended_next_action": (
                "Keep the champion filter paper-only; continue fresh monitor collection and only revisit "
                "promotion after this replay has enough exact priced rows with no winner damage."
            ),
        },
        "examples": {
            "matched": sorted(matched, key=lambda row: float(row.get("baseline_pnl_pct") or 0.0))[:25],
            "unpriced": unpriced[:25],
        },
    }


def _fmt_pct(value: Any) -> str:
    parsed = _safe_float(value)
    return "n/a" if parsed is None else f"{parsed:+.2f}%"


def render_markdown(report: dict[str, Any]) -> str:
    decision = report["decision_summary"]
    effects = report["effects"]
    lines = [
        "# Current-Policy Entry Filter Point-In-Time Replay",
        "",
        "Read-only scanner candidate replay for the short-term fill-degradation champion. It does not change live guardrails.",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{decision['status']}`",
        f"- Filter: `{report['filter']['filter_id']}`",
        f"- Live policy change: `{report['filter']['live_policy_change']}`",
        f"- Promotion blockers: `{', '.join(decision['promotion_blockers']) or 'none'}`",
        "",
        "## Candidate Read",
        "",
        "| Slice | Rows | Exact priced | Avg | Median | Negatives | <= -50% | <= -90% |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, key in (("Baseline", "baseline"), ("Matched", "matched"), ("Kept", "kept")):
        item = report[key]
        lines.append(
            f"| {label} | {item['rows']} | {item['exact_priced_rows']} | {_fmt_pct(item['avg_pnl_pct'])} | "
            f"{_fmt_pct(item['median_pnl_pct'])} | {item['negative_count']} | "
            f"{item['loss_le_50_count']} | {item['loss_le_90_count']} |"
        )
    lines.extend(
        [
            "",
            "## Effect Read",
            "",
            f"- Avoided losses: `{effects['avoided_losses']}`",
            f"- Avoided deep losses: `{effects['avoided_deep_losses']}`",
            f"- Avoided near-total losses: `{effects['avoided_near_total_losses']}`",
            f"- Lost winners: `{effects['lost_winners']}`",
            f"- Blocked sum delta if skipped: `{_fmt_pct(effects['blocked_sum_delta_if_skipped_pct'])}`",
            "",
            "## Coverage",
            "",
            f"- Zero-pick days: `{report['coverage']['zero_pick_day_count']}`",
            f"- Unpriced or non-executable rows: `{report['coverage']['unpriced_or_non_executable_count']}`",
            f"- Unpriced reasons: `{json.dumps(report['coverage']['unpriced_reasons'], sort_keys=True)}`",
            "",
            f"Recommended next action: {decision['recommended_next_action']}",
            "",
        ]
    )
    return "\n".join(lines)


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.get("examples", {}).get("matched", []):
        rows.append(
            {
                "candidate_key": item.get("candidate_key"),
                "ticker": item.get("ticker"),
                "playbook_id": item.get("playbook_id"),
                "position_id": item.get("position_id"),
                "fill_degradation_pct": item.get("fill_degradation_pct"),
                "baseline_pnl_pct": item.get("baseline_pnl_pct"),
                "exact_priced": item.get("exact_priced"),
                "unpriced_reason": item.get("unpriced_reason"),
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
    parser = argparse.ArgumentParser(description="Replay the short-term fill-degradation filter point in time.")
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--stop-grid", type=Path, default=DEFAULT_STOP_GRID)
    parser.add_argument("--starvation-audit", type=Path, default=DEFAULT_STARVATION_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = build_report(
        fill_attempt_rows=_read_jsonl(Path(args.fill_attempts)),
        stop_grid=_read_json(Path(args.stop_grid)),
        starvation_audit=_read_json(Path(args.starvation_audit)),
    )
    report["inputs"]["fill_attempts"] = str(Path(args.fill_attempts))
    report["inputs"]["stop_grid"] = str(Path(args.stop_grid))
    report["inputs"]["starvation_audit"] = str(Path(args.starvation_audit))
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
            f"{REPORT_ID}: status={report['decision_summary']['status']} "
            f"matched={report['matched']['rows']} exact={report['matched']['exact_priced_rows']} "
            f"blockers={','.join(report['decision_summary']['promotion_blockers']) or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
