from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "forward-evidence"
DEFAULT_COHORT_ID = "quality90_debit55_canary"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _fingerprint_payload(report: dict[str, Any]) -> dict[str, Any]:
    evidence = dict(report.get("evidence") or {})
    return {
        "kind": "canary_forward_evidence",
        "cohort_id": report.get("cohort_id"),
        "source_label": report.get("source_label"),
        "db_path": evidence.get("db_path"),
        "session_count": evidence.get("session_count"),
        "scan_pick_count": evidence.get("scan_pick_count"),
        "eligible_event_count": evidence.get("eligible_event_count"),
        "pending_truth_event_count": evidence.get("pending_truth_event_count"),
        "taken_pick_count": evidence.get("taken_pick_count"),
        "closed_review_count": evidence.get("closed_review_count"),
        "net_realized_pnl_pct": evidence.get("net_realized_pnl_pct"),
        "latest_recorded_at_utc": evidence.get("latest_recorded_at_utc"),
    }


def build_forward_evidence_fingerprint(report: dict[str, Any]) -> str:
    payload = _fingerprint_payload(report)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_forward_evidence(output_dir: Path, fingerprint: str) -> Path | None:
    for report_path in sorted(Path(output_dir).glob("forward_evidence_*.json")):
        try:
            report = _read_json(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("forward_evidence_fingerprint") == fingerprint:
            return report_path
    return None


def cohort_latest_filename(cohort_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in str(cohort_id or "").strip())
    return f"latest_{safe or 'unknown'}.json"


def build_canary_forward_evidence(
    *,
    cohort_id: str = DEFAULT_COHORT_ID,
    source_label: str | None = None,
    db_path: str | Path | None = None,
    min_closed_forward_trades: int = 20,
    summarize_func: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if summarize_func is None:
        from forward_options_ledger import summarize_forward_holdout

        summarize_func = summarize_forward_holdout
    evidence = summarize_func(cohort_id=cohort_id, source_label=source_label, db_path=db_path)
    closed_count = int(evidence.get("closed_review_count") or 0)
    eligible_count = int(evidence.get("eligible_event_count") or 0)
    scan_pick_count = int(evidence.get("scan_pick_count") or 0)
    session_count = int(evidence.get("session_count") or 0)
    if closed_count >= min_closed_forward_trades:
        readiness = "forward_sample_ready"
    elif scan_pick_count > 0 or eligible_count > 0:
        readiness = "collecting_forward_evidence"
    elif session_count > 0:
        readiness = "scanning_no_picks_yet"
    else:
        readiness = "no_forward_evidence_yet"
    report = {
        "cohort_id": cohort_id,
        "cohort_role": "proof_control_yardstick",
        "source_label": source_label,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "promotion_allowed": False,
        "readiness": readiness,
        "target": {
            "closed_forward_trade_count": min_closed_forward_trades,
        },
        "progress": {
            "closed_forward_trade_count": closed_count,
            "closed_forward_needed": max(min_closed_forward_trades - closed_count, 0),
            "eligible_event_count": eligible_count,
            "pending_truth_event_count": int(evidence.get("pending_truth_event_count") or 0),
            "scan_pick_count": scan_pick_count,
            "taken_pick_count": int(evidence.get("taken_pick_count") or 0),
            "session_count": session_count,
            "sessions_with_zero_scan_picks": int(evidence.get("sessions_with_zero_scan_picks") or 0),
            "latest_starvation_stage": evidence.get("latest_starvation_stage"),
        },
        "evidence": evidence,
        "next_actions": [
            "Run the canary scanner as a proof/control yardstick on market days.",
            "Track every canary pick with exact contract metadata.",
            "Wait for closed outcomes before treating forward P&L as proof.",
        ],
    }
    report["forward_evidence_fingerprint"] = build_forward_evidence_fingerprint(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a forward-evidence snapshot for the quality90/debit55 canary.")
    parser.add_argument("--cohort-id", default=DEFAULT_COHORT_ID)
    parser.add_argument("--source-label")
    parser.add_argument("--db-path")
    parser.add_argument("--min-closed-forward-trades", type=int, default=20)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Write a new artifact even if the forward snapshot is unchanged.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_canary_forward_evidence(
        cohort_id=args.cohort_id,
        source_label=args.source_label,
        db_path=args.db_path,
        min_closed_forward_trades=args.min_closed_forward_trades,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_forward_evidence(output_dir, str(report.get("forward_evidence_fingerprint") or ""))
    if duplicate is not None and not args.force:
        compact = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "fingerprint": report.get("forward_evidence_fingerprint"),
            "readiness": report.get("readiness"),
            "progress": report.get("progress"),
            "hint": "Use --force to write a new forward evidence artifact for the unchanged snapshot.",
        }
        print(json.dumps(report if args.json else compact, indent=2))
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"forward_evidence_{stamp}_{args.cohort_id}.json"
    latest_path = output_dir / cohort_latest_filename(args.cohort_id)
    generic_latest_path = output_dir / "latest.json"
    serialized = json.dumps(report, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    generic_latest_path.write_text(serialized, encoding="utf8")
    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "generic_latest": str(generic_latest_path),
        "readiness": report.get("readiness"),
        "progress": report.get("progress"),
    }
    print(json.dumps(report if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
