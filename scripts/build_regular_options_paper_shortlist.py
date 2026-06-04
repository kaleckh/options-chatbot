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

from scripts import build_regular_options_profit_capture_queue as capture_queue  # noqa: E402


DEFAULT_QUEUE = ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist"
DEFAULT_DOC = ROOT / "docs" / "regular-options-paper-shortlist.md"


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
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf8"))
    return payload if isinstance(payload, dict) else {"missing": True, "path": str(path), "error": "json_root_not_object"}


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _safe_bool(value: Any) -> bool:
    return bool(value) if not isinstance(value, str) else value.strip().lower() == "true"


def _bridge(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("fresh_match_bridge")
    return value if isinstance(value, dict) else {}


def _eligible_invariant_violations(row: dict[str, Any]) -> list[str]:
    bridge = _bridge(row)
    violations: list[str] = []
    if bridge.get("status") != capture_queue.BRIDGE_READY:
        violations.append("bridge_status_not_ready")
    if not _safe_bool(bridge.get("eligible")):
        violations.append("bridge_not_marked_eligible")
    if row.get("guardrail_decision") != "clear":
        violations.append("guardrail_not_clear")
    if row.get("match_type") != "lane_signature":
        violations.append("lane_signature_not_matched")
    if not _safe_bool(row.get("fresh_executable_quote_window")):
        violations.append("fresh_executable_quote_missing")
    if int(bridge.get("tier_a_lane_match_count") or 0) <= 0:
        violations.append("no_tier_a_lane_match")
    if not bridge.get("matched_tier_a_lanes"):
        violations.append("matched_tier_a_lanes_missing")
    if bridge.get("blockers"):
        violations.append("bridge_has_blockers")
    if _safe_bool(row.get("live_policy_change")) or _safe_bool(bridge.get("live_policy_change")):
        violations.append("live_policy_change_true")
    return violations


def _paper_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    bridge = _bridge(row)
    return {
        "symbol": row.get("symbol"),
        "playbook_id": row.get("playbook_id"),
        "playbook_label": row.get("playbook_label"),
        "direction": row.get("direction"),
        "expiry": row.get("expiry"),
        "bridge_status": bridge.get("status"),
        "eligible": _safe_bool(bridge.get("eligible")),
        "guardrail_decision": row.get("guardrail_decision"),
        "match_type": row.get("match_type"),
        "fresh_executable_quote_window": _safe_bool(row.get("fresh_executable_quote_window")),
        "matched_tier_a_lanes": list(bridge.get("matched_tier_a_lanes") or []),
        "tier_a_lane_match_count": int(bridge.get("tier_a_lane_match_count") or 0),
        "debit_pct_of_width": row.get("debit_pct_of_width"),
        "quality_score": row.get("quality_score"),
        "candidate_execution_label": row.get("candidate_execution_label"),
        "quote_freshness_status": row.get("quote_freshness_status"),
        "options_data_source": row.get("options_data_source"),
        "pricing_evidence_class": row.get("pricing_evidence_class"),
        "selection_source": row.get("selection_source"),
        "matched_sleeves": list(row.get("matched_sleeves") or []),
        "live_policy_change": False,
    }


def _capture_bridge_counts(queue_payload: dict[str, Any]) -> dict[str, int]:
    counts = Counter()
    for row in queue_payload.get("capture_queue") or []:
        if not isinstance(row, dict):
            continue
        bridge = row.get("paper_shortlist_bridge") if isinstance(row.get("paper_shortlist_bridge"), dict) else {}
        counts[str(bridge.get("status") or "missing")] += 1
    return dict(sorted(counts.items()))


def _fresh_bridge_counts(queue_payload: dict[str, Any]) -> dict[str, int]:
    counts = Counter()
    for row in queue_payload.get("fresh_scan_matches") or []:
        if not isinstance(row, dict):
            continue
        counts[str(_bridge(row).get("status") or "missing")] += 1
    return dict(sorted(counts.items()))


def build_readback(queue_path: Path = DEFAULT_QUEUE) -> dict[str, Any]:
    queue_payload = _load_json(queue_path)
    source_missing = bool(queue_payload.get("missing"))
    fresh_rows = [row for row in queue_payload.get("fresh_scan_matches") or [] if isinstance(row, dict)]
    eligible_source_rows = [
        row for row in fresh_rows if _bridge(row).get("status") == capture_queue.BRIDGE_READY
    ]
    invariant_violations = [
        {
            "symbol": row.get("symbol"),
            "playbook_id": row.get("playbook_id"),
            "bridge_status": _bridge(row).get("status"),
            "violations": violations,
        }
        for row in eligible_source_rows
        for violations in [_eligible_invariant_violations(row)]
        if violations
    ]
    valid_eligible_source_rows = [row for row in eligible_source_rows if not _eligible_invariant_violations(row)]
    eligible_rows = [_paper_candidate_row(row) for row in valid_eligible_source_rows]
    fresh_blocker_counts = Counter(
        blocker
        for row in fresh_rows
        for blocker in (_bridge(row).get("blockers") or [])
        if _bridge(row).get("status") != capture_queue.BRIDGE_READY
    )
    summary = {
        "source_queue_status": queue_payload.get("status"),
        "source_queue_rows": (queue_payload.get("summary") or {}).get("queue_rows"),
        "eligible_count": len(eligible_rows),
        "invariant_violation_count": len(invariant_violations),
        "release_gate_status": (
            "source_missing"
            if source_missing
            else "blocked_invariant_violations"
            if invariant_violations
            else "paper_review_candidates_available"
            if eligible_rows
            else "no_paper_shortlist_candidates"
        ),
        "capture_bridge_status_counts": _capture_bridge_counts(queue_payload),
        "fresh_bridge_status_counts": _fresh_bridge_counts(queue_payload),
        "fresh_bridge_blocker_counts": dict(sorted(fresh_blocker_counts.items())),
        "selection_readiness_counts": (queue_payload.get("summary") or {}).get("selection_readiness_counts") or {},
        "tier_counts": (queue_payload.get("summary") or {}).get("tier_counts") or {},
        "live_policy_change": False,
    }
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_options_paper_shortlist",
        "status": "paper_shortlist_readback",
        "source_queue_path": _rel(queue_path),
        "source_queue_generated_at_utc": queue_payload.get("generated_at_utc"),
        "proof_policy": {
            "readback_is": "paper shortlist release gate for fresh executable Tier A lane matches",
            "readback_is_not": "scanner promotion, broker recommendation, stop-policy change, or proof-bar reduction",
            "eligible_requires": [
                "fresh executable quote-window scanner row",
                "guardrail clear",
                "lane-signature match",
                "matched Tier A clean exact evidence row",
                "no bridge blockers",
                "live_policy_change=false",
            ],
            "non_eligible_rows": "Tier B, Tier C, blocked, quarantine, symbol-only, stale, midpoint, EOD, fallback, and manual evidence remain non-promotable.",
        },
        "summary": summary,
        "eligible_paper_review_candidates": eligible_rows,
        "invariant_violations": invariant_violations,
        "fresh_scan_non_eligible_preview": [
            {
                "symbol": row.get("symbol"),
                "playbook_id": row.get("playbook_id"),
                "guardrail_decision": row.get("guardrail_decision"),
                "match_type": row.get("match_type"),
                "fresh_executable_quote_window": row.get("fresh_executable_quote_window"),
                "bridge_status": _bridge(row).get("status"),
                "blockers": list(_bridge(row).get("blockers") or []),
                "matched_tier_a_lanes": list(_bridge(row).get("matched_tier_a_lanes") or []),
            }
            for row in fresh_rows
            if _bridge(row).get("status") != capture_queue.BRIDGE_READY
        ][:50],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("eligible_paper_review_candidates") or []
    blocked = report.get("fresh_scan_non_eligible_preview") or []
    lines = [
        "# Regular Options Paper Shortlist",
        "",
        "This report is generated from `scripts/build_regular_options_paper_shortlist.py`. It is a paper-review release gate for fresh executable Tier A lane matches, not a scanner promotion or broker-action surface.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Release gate: `{summary.get('release_gate_status')}`.",
        f"- Eligible paper-review candidates: `{summary.get('eligible_count')}`.",
        f"- Invariant violations: `{summary.get('invariant_violation_count')}`.",
        f"- Source queue rows: `{summary.get('source_queue_rows')}`.",
        f"- Capture bridge statuses: `{json.dumps(summary.get('capture_bridge_status_counts') or {}, sort_keys=True)}`.",
        f"- Fresh bridge statuses: `{json.dumps(summary.get('fresh_bridge_status_counts') or {}, sort_keys=True)}`.",
        f"- Fresh bridge blockers: `{json.dumps(summary.get('fresh_bridge_blocker_counts') or {}, sort_keys=True)}`.",
        f"- Live policy change: `{summary.get('live_policy_change')}`.",
        "",
        "## Proof Policy",
        "",
        "- Eligible rows require a fresh executable quote-window scanner row, clear guardrails, a lane-signature match, matched Tier A clean exact evidence, no bridge blockers, and `live_policy_change=false`.",
        "- Tier B, Tier C, blocked, quarantine, symbol-only, stale, midpoint, EOD, fallback, and manual evidence remain non-promotable.",
        "- This report does not change scanner, broker, stop, auth, DB, or proof behavior.",
        "",
        "## Eligible Paper-Review Candidates",
        "",
        "| Symbol | Playbook | Direction | Expiry | Matched Tier A lanes | Debit % | Quality | Execution label |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("symbol")),
                    _fmt(row.get("playbook_id")),
                    _fmt(row.get("direction")),
                    _fmt(row.get("expiry")),
                    _fmt(", ".join(row.get("matched_tier_a_lanes") or [])),
                    _fmt(row.get("debit_pct_of_width")),
                    _fmt(row.get("quality_score")),
                    _fmt(row.get("candidate_execution_label")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Non-Eligible Fresh Matches",
            "",
            "| Symbol | Playbook | Decision | Match | Executable | Bridge | Blockers |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in blocked:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("symbol")),
                    _fmt(row.get("playbook_id")),
                    _fmt(row.get("guardrail_decision")),
                    _fmt(row.get("match_type")),
                    _fmt(row.get("fresh_executable_quote_window")),
                    _fmt(row.get("bridge_status")),
                    _fmt(", ".join(row.get("blockers") or [])),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"regular_options_paper_shortlist_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_paper_shortlist_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(markdown_path),
        "latest_markdown": str(latest_markdown),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    doc_path.write_text(markdown, encoding="utf8")
    return artifacts


def _strict_gate_failed(report: dict[str, Any]) -> bool:
    summary = report.get("summary") or {}
    return summary.get("release_gate_status") in {
        "source_missing",
        "blocked_invariant_violations",
    } or bool(summary.get("invariant_violation_count"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options paper-shortlist release gate.")
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict-gate", action="store_true")
    args = parser.parse_args(argv)

    report = build_readback(args.queue)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    else:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))

    if args.strict_gate and _strict_gate_failed(report):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
