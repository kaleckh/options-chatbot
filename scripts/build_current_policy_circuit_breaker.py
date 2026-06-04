from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "current_policy_circuit_breaker"
DEFAULT_COHORT_HEALTH = ROOT / "data" / "forward-tracking" / "current_policy_cohort_health_latest.json"
DEFAULT_POINT_IN_TIME = ROOT / "data" / "forward-tracking" / "short_term_filter_point_in_time_replay_latest.json"
DEFAULT_PAPER_MONITOR = ROOT / "data" / "forward-tracking" / "current_policy_entry_filter_paper_monitor_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_CIRCUIT_BREAKER = DEFAULT_OUTPUT_DIR / "current_policy_circuit_breaker_latest.json"
DEFAULT_DOC = ROOT / "docs" / "current-policy-circuit-breaker.md"

AFFECTED_LANES = ("short_term", "bullish_pullback_observation")
CHAMPION_FILTER_ID = "short_term_fill_degradation_ge_15"
MIN_FRESH_CURRENT_POLICY_ROWS = 20
MIN_CHAMPION_MATCHED_ROWS = 5
POINT_IN_TIME_PASS_STATUS = "point_in_time_replay_pass_candidate_not_promoted"
PAPER_MONITOR_PASS_STATUS = "paper_pass_candidate"


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


def load_report(path: Path = DEFAULT_CIRCUIT_BREAKER) -> dict[str, Any]:
    return _load_json(path)


def _safe_int(value: Any) -> int:
    if value is None or value == "" or isinstance(value, bool):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _paper_only_status(value: Any) -> bool:
    return str(value or "").startswith("paper_only")


def _gate(
    *,
    gate_id: str,
    label: str,
    passed: bool,
    current: Any,
    target: Any,
    detail: str,
) -> dict[str, Any]:
    return {
        "gate": gate_id,
        "label": label,
        "passed": bool(passed),
        "current": current,
        "target": target,
        "detail": detail,
    }


def _recovery_gates(
    *,
    cohort_health: dict[str, Any],
    point_in_time: dict[str, Any],
    paper_monitor: dict[str, Any],
) -> list[dict[str, Any]]:
    cohort_summary = cohort_health.get("summary") if isinstance(cohort_health.get("summary"), dict) else {}
    point_decision = point_in_time.get("decision_summary") if isinstance(point_in_time.get("decision_summary"), dict) else {}
    point_baseline = point_in_time.get("baseline") if isinstance(point_in_time.get("baseline"), dict) else {}
    point_matched = point_in_time.get("matched") if isinstance(point_in_time.get("matched"), dict) else {}
    point_effects = point_in_time.get("effects") if isinstance(point_in_time.get("effects"), dict) else {}
    point_blockers = list(point_decision.get("promotion_blockers") or [])

    monitor_gate = paper_monitor.get("gate") if isinstance(paper_monitor.get("gate"), dict) else {}
    monitor_baseline = paper_monitor.get("baseline") if isinstance(paper_monitor.get("baseline"), dict) else {}
    champion = paper_monitor.get("champion") if isinstance(paper_monitor.get("champion"), dict) else {}
    champion_matched = champion.get("matched") if isinstance(champion.get("matched"), dict) else {}

    overall_status = str(cohort_summary.get("overall_status") or "missing")
    point_status = str(point_decision.get("status") or "missing")
    monitor_status = str(monitor_gate.get("status") or "missing")
    fresh_rows = _safe_int(monitor_baseline.get("rows"))
    champion_rows = _safe_int(champion_matched.get("rows"))
    exact_rows = _safe_int(point_baseline.get("exact_priced_rows"))
    exact_champion_rows = _safe_int(point_matched.get("exact_priced_rows"))
    point_winners_lost = _safe_int(point_effects.get("lost_winners"))
    point_losses_avoided = _safe_int(point_effects.get("avoided_losses"))
    monitor_winners_lost = _safe_int(champion.get("winners_lost"))
    monitor_losses_avoided = _safe_int(champion.get("losses_avoided"))
    no_winner_damage = (
        point_winners_lost <= point_losses_avoided
        and monitor_winners_lost <= monitor_losses_avoided
        and "winner_damage_exceeds_losses_avoided" not in point_blockers
        and "winner_damage_exceeds_losses_avoided" not in list(monitor_gate.get("failures") or [])
    )

    return [
        _gate(
            gate_id="recent_cohort_recovered",
            label="Recent cohort recovered",
            passed=not _paper_only_status(overall_status),
            current=overall_status,
            target="not paper_only_*",
            detail="The recent current-policy cohort must stop reporting a paper-only break.",
        ),
        _gate(
            gate_id="fresh_current_policy_rows",
            label="Fresh current-policy rows",
            passed=fresh_rows >= MIN_FRESH_CURRENT_POLICY_ROWS,
            current=fresh_rows,
            target=MIN_FRESH_CURRENT_POLICY_ROWS,
            detail="Forward monitor needs enough fresh current-policy rows before release discussion.",
        ),
        _gate(
            gate_id="fresh_champion_matched_rows",
            label="Champion-matched blocked rows",
            passed=champion_rows >= MIN_CHAMPION_MATCHED_ROWS,
            current=champion_rows,
            target=MIN_CHAMPION_MATCHED_ROWS,
            detail="The lane-scoped champion must match enough candidate-blocked rows.",
        ),
        _gate(
            gate_id="trusted_exact_realized_pnl_rows",
            label="Trusted exact realized P&L rows",
            passed=exact_rows >= MIN_FRESH_CURRENT_POLICY_ROWS and exact_champion_rows >= MIN_CHAMPION_MATCHED_ROWS,
            current={
                "exact_priced_candidate_rows": exact_rows,
                "exact_priced_champion_rows": exact_champion_rows,
            },
            target={
                "exact_priced_candidate_rows": MIN_FRESH_CURRENT_POLICY_ROWS,
                "exact_priced_champion_rows": MIN_CHAMPION_MATCHED_ROWS,
            },
            detail="Point-in-time replay must have exact-priced realized outcomes, not unpriced or display-only rows.",
        ),
        _gate(
            gate_id="point_in_time_replay_pass",
            label="Point-in-time replay pass",
            passed=point_status == POINT_IN_TIME_PASS_STATUS and not point_blockers,
            current={"status": point_status, "blockers": point_blockers},
            target={"status": POINT_IN_TIME_PASS_STATUS, "blockers": []},
            detail="The scanner-candidate replay must clear without promotion blockers.",
        ),
        _gate(
            gate_id="paper_monitor_pass",
            label="Paper monitor pass",
            passed=monitor_status == PAPER_MONITOR_PASS_STATUS and not list(monitor_gate.get("failures") or []),
            current={"status": monitor_status, "failures": list(monitor_gate.get("failures") or [])},
            target={"status": PAPER_MONITOR_PASS_STATUS, "failures": []},
            detail="The forward paper monitor must graduate from collecting/fail into pass-candidate.",
        ),
        _gate(
            gate_id="no_winner_damage",
            label="No winner damage",
            passed=no_winner_damage,
            current={
                "point_in_time_lost_winners": point_winners_lost,
                "point_in_time_losses_avoided": point_losses_avoided,
                "monitor_winners_lost": monitor_winners_lost,
                "monitor_losses_avoided": monitor_losses_avoided,
            },
            target="lost_winners <= losses_avoided in replay and monitor",
            detail="Recovery cannot pass by blocking more winners than losses avoided.",
        ),
        _gate(
            gate_id="live_policy_change_false",
            label="No live policy mutation",
            passed=not bool((point_in_time.get("filter") or {}).get("live_policy_change")) and not bool(monitor_gate.get("live_policy_change")),
            current={
                "point_in_time_live_policy_change": bool((point_in_time.get("filter") or {}).get("live_policy_change")),
                "paper_monitor_live_policy_change": bool(monitor_gate.get("live_policy_change")),
            },
            target=False,
            detail="The breaker is a safety/readback route, not a scanner, broker, stop, auth, DB, or proof-bar mutation.",
        ),
    ]


def _lane_recent_summary(cohort_health: dict[str, Any], lane: str) -> dict[str, Any]:
    summary = cohort_health.get("summary") if isinstance(cohort_health.get("summary"), dict) else {}
    recent_month = str(summary.get("recent_month") or "")
    lane_monthly = cohort_health.get("lane_monthly") if isinstance(cohort_health.get("lane_monthly"), dict) else {}
    return lane_monthly.get(f"{recent_month}:{lane}") or {}


def _lane_route(
    *,
    lane: str,
    recovery_passed: bool,
    recovery_failures: list[str],
    cohort_health: dict[str, Any],
) -> dict[str, Any]:
    lane_summary = _lane_recent_summary(cohort_health, lane)
    lane_status = str(lane_summary.get("health_status") or "missing")
    if not recovery_passed:
        route_status = "paper_validation_only"
        reason = "recovery_gates_failed"
    else:
        route_status = "recovery_review_required"
        reason = "recovery_gates_passed_requires_human_review"
    return {
        "lane_id": lane,
        "route_status": route_status,
        "route_reason": reason,
        "recent_month_health_status": lane_status,
        "recent_month_summary": lane_summary,
        "recovery_gate_failures": list(recovery_failures),
        "short_term_filter_scope": "lane_scoped_paper_only" if lane == "short_term" else None,
        "lane_deleted": False,
        "live_policy_change": False,
    }


def build_report(
    *,
    cohort_health: dict[str, Any],
    point_in_time: dict[str, Any],
    paper_monitor: dict[str, Any],
) -> dict[str, Any]:
    gates = _recovery_gates(
        cohort_health=cohort_health,
        point_in_time=point_in_time,
        paper_monitor=paper_monitor,
    )
    recovery_failures = [gate["gate"] for gate in gates if not gate["passed"]]
    recovery_passed = not recovery_failures
    cohort_summary = cohort_health.get("summary") if isinstance(cohort_health.get("summary"), dict) else {}
    overall_status = str(cohort_summary.get("overall_status") or "missing")
    breaker_active = _paper_only_status(overall_status)
    lane_routes = [
        _lane_route(
            lane=lane,
            recovery_passed=recovery_passed,
            recovery_failures=recovery_failures,
            cohort_health=cohort_health,
        )
        for lane in AFFECTED_LANES
    ]
    paper_only_count = sum(1 for route in lane_routes if route["route_status"] == "paper_validation_only")
    review_required_count = sum(1 for route in lane_routes if route["route_status"] == "recovery_review_required")
    route_status = "paper_validation_only" if paper_only_count else "recovery_review_required"
    return {
        "schema_version": 1,
        "report_id": REPORT_ID,
        "generated_at_utc": _utc_now(),
        "scope": "regular_supervised_current_policy_recent_cohort_circuit_breaker",
        "inputs": {
            "cohort_health_generated_at_utc": cohort_health.get("generated_at_utc"),
            "point_in_time_generated_at_utc": point_in_time.get("generated_at_utc"),
            "paper_monitor_generated_at_utc": paper_monitor.get("generated_at_utc"),
            "champion_filter_id": CHAMPION_FILTER_ID,
        },
        "routing_policy": {
            "readback_is": "recent-cohort paper-only circuit breaker for pending regular-options validation candidates",
            "readback_is_not": "lane deletion, scanner promotion, broker action, stop-policy change, auth change, DB migration, or proof-bar reduction",
            "affected_lanes": list(AFFECTED_LANES),
            "release_requires": [gate["gate"] for gate in gates],
        },
        "summary": {
            "overall_status": overall_status,
            "breaker_active": breaker_active,
            "route_status": route_status,
            "affected_lane_count": len(lane_routes),
            "paper_validation_only_lane_count": paper_only_count,
            "recovery_review_required_lane_count": review_required_count,
            "recovery_gate_passed_count": sum(1 for gate in gates if gate["passed"]),
            "recovery_gate_failed_count": len(recovery_failures),
            "recovery_gate_failures": recovery_failures,
            "live_policy_change": False,
            "lane_deletion": False,
        },
        "recovery_gates": gates,
        "lane_routes": lane_routes,
    }


def paper_validation_only_playbooks(report: dict[str, Any]) -> set[str]:
    routes = report.get("lane_routes")
    if report.get("missing") or not isinstance(routes, list) or not routes:
        return set(AFFECTED_LANES)
    return {
        str(route.get("lane_id") or "")
        for route in routes
        if isinstance(route, dict) and route.get("route_status") == "paper_validation_only"
    }


def validation_hold_playbooks(report: dict[str, Any]) -> set[str]:
    routes = report.get("lane_routes")
    if report.get("missing") or not isinstance(routes, list) or not routes:
        return set(AFFECTED_LANES)
    return {
        str(route.get("lane_id") or "")
        for route in routes
        if isinstance(route, dict) and route.get("route_status") in {"paper_validation_only", "recovery_review_required"}
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# Current-Policy Circuit Breaker",
        "",
        "This report is generated from `scripts/build_current_policy_circuit_breaker.py`. It is a readback-driven paper-validation route for recently broken current-policy cohorts, not a lane deletion or live scanner promotion.",
        "",
        "## Summary",
        "",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Breaker active: `{summary.get('breaker_active')}`.",
        f"- Route status: `{summary.get('route_status')}`.",
        f"- Paper-validation-only lanes: `{summary.get('paper_validation_only_lane_count')}`.",
        f"- Recovery-review-required lanes: `{summary.get('recovery_review_required_lane_count')}`.",
        f"- Recovery gate failures: `{', '.join(summary.get('recovery_gate_failures') or []) or 'none'}`.",
        f"- Live policy change: `{summary.get('live_policy_change')}`.",
        f"- Lane deletion: `{summary.get('lane_deletion')}`.",
        "",
        "## Lane Routes",
        "",
        "| Lane | Route | Recent Health | Reason | Gate Failures |",
        "|---|---|---|---|---|",
    ]
    for route in report.get("lane_routes") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(route.get("lane_id") or ""),
                    str(route.get("route_status") or ""),
                    str(route.get("recent_month_health_status") or ""),
                    str(route.get("route_reason") or ""),
                    ", ".join(route.get("recovery_gate_failures") or []) or "none",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Recovery Gates",
            "",
            "| Gate | Passed | Current | Target |",
            "|---|---:|---|---|",
        ]
    )
    for gate in report.get("recovery_gates") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(gate.get("gate") or ""),
                    str(gate.get("passed")),
                    json.dumps(gate.get("current"), sort_keys=True),
                    json.dumps(gate.get("target"), sort_keys=True),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- `paper_validation_only` means pending candidates in affected lanes should receive a paper-only validation disposition instead of entering the auto-track validation path while the breaker is active.",
            "- Recovery gates passing creates a review candidate, not an automatic live promotion.",
            "- The breaker never deletes `short_term` or `bullish_pullback_observation`; it keeps the lanes observable while recent evidence is broken.",
            "- The short-term fill-degradation rule remains lane-scoped and paper-only.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    md_path.write_text(markdown + "\n", encoding="utf8")
    latest_md.write_text(markdown + "\n", encoding="utf8")
    doc_path.write_text(markdown + "\n", encoding="utf8")
    return artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build current-policy recent-cohort circuit breaker readback.")
    parser.add_argument("--cohort-health", type=Path, default=DEFAULT_COHORT_HEALTH)
    parser.add_argument("--point-in-time", type=Path, default=DEFAULT_POINT_IN_TIME)
    parser.add_argument("--paper-monitor", type=Path, default=DEFAULT_PAPER_MONITOR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        cohort_health=_load_json(args.cohort_health),
        point_in_time=_load_json(args.point_in_time),
        paper_monitor=_load_json(args.paper_monitor),
    )
    report["input_paths"] = {
        "cohort_health": _rel(args.cohort_health),
        "point_in_time": _rel(args.point_in_time),
        "paper_monitor": _rel(args.paper_monitor),
    }
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
