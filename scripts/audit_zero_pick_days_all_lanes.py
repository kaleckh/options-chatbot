from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervised_scan import get_scan_playbook, get_scan_playbooks

from scripts import audit_zero_pick_days_current_main_lane as single_lane_audit


ALL_LANES_AUDIT_ID = "all_lanes_zero_pick_current_algo_v1"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in str(value).replace(";", ",").split(",") if item.strip()]


def selected_playbook_ids(args: argparse.Namespace) -> list[str]:
    available = [str(playbook["id"]).strip().lower() for playbook in get_scan_playbooks()]
    available_set = set(available)
    requested = _split_csv(getattr(args, "playbooks", None))
    excluded = set(_split_csv(getattr(args, "exclude_playbooks", None)))
    selected = requested or available
    unknown = sorted({playbook_id for playbook_id in [*selected, *excluded] if playbook_id not in available_set})
    if unknown:
        raise ValueError(f"Unknown scan playbook(s): {', '.join(unknown)}. Available: {', '.join(available)}")
    return [playbook_id for playbook_id in selected if playbook_id not in excluded]


def _single_lane_args(args: argparse.Namespace, playbook_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        playbook=playbook_id,
        scope=args.scope,
        date_from=args.date_from,
        date_to=args.date_to,
        truth_lane=args.truth_lane,
        pricing_lane=args.pricing_lane,
        source_labels=args.source_labels,
        historical_options_db=args.historical_options_db,
        allow_research_data=args.allow_research_data,
        lookback_years=args.lookback_years,
        n_picks=args.n_picks,
        apply=args.apply,
        audit_id=args.audit_id,
    )


def build_all_lanes_audit(args: argparse.Namespace) -> dict[str, Any]:
    playbook_ids = selected_playbook_ids(args)
    lanes: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()

    for playbook_id in playbook_ids:
        lane_started_at = _utc_now_iso()
        try:
            audit = single_lane_audit.build_audit(_single_lane_args(args, playbook_id))
            summary = dict(audit.get("summary") or {})
            status = "completed"
            status_counts[status] += 1
            for key in (
                "date_count",
                "signal_candidate_count",
                "exact_candidate_count",
                "would_track_pick_count",
                "duplicate_pick_count",
                "scan_rows_appended",
                "fill_attempt_rows_appended",
                "ledger_sessions_recorded",
            ):
                totals[key] += int(summary.get(key) or 0)
            lane_report = {
                "status": status,
                "playbook": playbook_id,
                "label": get_scan_playbook(playbook_id).get("label") or playbook_id,
                "started_at_utc": lane_started_at,
                "completed_at_utc": _utc_now_iso(),
                "summary": summary,
                "parameters": audit.get("parameters"),
                "discovery": audit.get("discovery"),
                "ledger_results": audit.get("ledger_results"),
                "dates": audit.get("dates"),
            }
        except Exception as exc:  # Report the failed lane without hiding that other lanes ran.
            status = "failed"
            status_counts[status] += 1
            lane_report = {
                "status": status,
                "playbook": playbook_id,
                "label": get_scan_playbook(playbook_id).get("label") or playbook_id,
                "started_at_utc": lane_started_at,
                "completed_at_utc": _utc_now_iso(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if bool(getattr(args, "fail_fast", False)):
                lanes.append(lane_report)
                break
        lanes.append(lane_report)

    summary = {
        "audit_id": args.audit_id,
        "apply": bool(args.apply),
        "requested_lane_count": len(playbook_ids),
        "completed_lane_count": int(status_counts.get("completed", 0)),
        "failed_lane_count": int(status_counts.get("failed", 0)),
        "status_counts": dict(status_counts),
        "date_count_sum": int(totals.get("date_count", 0)),
        "signal_candidate_count": int(totals.get("signal_candidate_count", 0)),
        "exact_candidate_count": int(totals.get("exact_candidate_count", 0)),
        "would_track_pick_count": int(totals.get("would_track_pick_count", 0)),
        "duplicate_pick_count": int(totals.get("duplicate_pick_count", 0)),
        "scan_rows_appended": int(totals.get("scan_rows_appended", 0)),
        "fill_attempt_rows_appended": int(totals.get("fill_attempt_rows_appended", 0)),
        "ledger_sessions_recorded": int(totals.get("ledger_sessions_recorded", 0)),
    }
    return {
        "generated_at_utc": _utc_now_iso(),
        "summary": summary,
        "parameters": {
            "scope": args.scope,
            "playbooks": playbook_ids,
            "excluded_playbooks": _split_csv(args.exclude_playbooks),
            "truth_lane": args.truth_lane,
            "pricing_lane": args.pricing_lane,
            "source_labels": [
                item.strip()
                for item in str(args.source_labels or "").replace(";", ",").split(",")
                if item.strip()
            ],
            "trusted_only": not bool(args.allow_research_data),
            "n_picks": int(args.n_picks),
            "lookback_years": int(args.lookback_years),
            "historical_options_db": str(Path(str(args.historical_options_db)).expanduser()),
        },
        "lanes": lanes,
    }


def write_report(audit: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"all_lanes_zero_pick_current_algo_audit_{stamp}.json"
    latest = output_dir / "all_lanes_zero_pick_current_algo_audit_latest.json"
    payload = json.dumps(audit, indent=2, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return path, latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit zero-pick days against every runnable supervised scan lane.")
    parser.add_argument("--playbooks", help="Comma-separated scan playbook IDs. Omit to audit all scan playbooks.")
    parser.add_argument("--exclude-playbooks", help="Comma-separated scan playbook IDs to skip.")
    parser.add_argument("--scope", choices=["zero_any", "main_zero", "zero_any_or_main_zero"], default="zero_any_or_main_zero")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument(
        "--truth-lane",
        choices=[single_lane_audit.wfo.IMPORTED_TRUTH_SOURCE, single_lane_audit.wfo.IMPORTED_DAILY_TRUTH_SOURCE],
        default=single_lane_audit.wfo.IMPORTED_TRUTH_SOURCE,
    )
    parser.add_argument("--pricing-lane", default="pessimistic")
    parser.add_argument("--source-labels", default="thetadata_opra_nbbo_1m")
    parser.add_argument("--historical-options-db", default=str(single_lane_audit.HISTORICAL_OPTIONS_DB))
    parser.add_argument("--allow-research-data", action="store_true")
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--n-picks", type=int, default=10)
    parser.add_argument("--audit-id", default=ALL_LANES_AUDIT_ID)
    parser.add_argument("--apply", action="store_true", help="Append all-lane research-backfill rows. Omit for report-only audit.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first lane failure.")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    audit = build_all_lanes_audit(args)
    if not args.no_write_report:
        path, latest = write_report(audit, Path(args.output_dir))
        print(f"Wrote all-lanes audit report: {path}")
        print(f"Wrote latest all-lanes audit report: {latest}")

    for lane in audit["lanes"]:
        summary = lane.get("summary") or {}
        if lane.get("status") == "completed":
            print(
                f"{lane['playbook']}: dates={summary.get('date_count', 0)} "
                f"signals={summary.get('signal_candidate_count', 0)} "
                f"exact={summary.get('exact_candidate_count', 0)} "
                f"would_track={summary.get('would_track_pick_count', 0)} "
                f"duplicates={summary.get('duplicate_pick_count', 0)}"
            )
        else:
            print(f"{lane['playbook']}: failed {lane.get('error_type')}: {lane.get('error')}")

    summary = audit["summary"]
    print(
        "All-lanes zero-pick current-algo audit: "
        f"completed={summary['completed_lane_count']}/{summary['requested_lane_count']} "
        f"signals={summary['signal_candidate_count']} "
        f"exact={summary['exact_candidate_count']} "
        f"would_track={summary['would_track_pick_count']} "
        f"duplicates={summary['duplicate_pick_count']}"
    )
    return 1 if args.fail_fast and summary["failed_lane_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
