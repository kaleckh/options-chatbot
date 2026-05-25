from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAB_RUNS = ROOT / "data" / "profitability-lab" / "runs"
DEFAULT_EXIT_SWEEPS = ROOT / "data" / "profitability-lab" / "exit-sweeps"
DEFAULT_LOSING_AUDITS = ROOT / "data" / "profitability-lab" / "losing-window-audits"
DEFAULT_HYPOTHESIS_SWEEPS = ROOT / "data" / "profitability-lab" / "hypothesis-sweeps"
DEFAULT_EXACT_COVERAGE_AUDITS = ROOT / "data" / "profitability-lab" / "exact-coverage-audits"
DEFAULT_PROMOTION_CHECKLISTS = ROOT / "data" / "profitability-lab" / "promotion-checklists"
DEFAULT_CANARY_STATUS = ROOT / "data" / "profitability-lab" / "canary-status"
DEFAULT_FORWARD_EVIDENCE = ROOT / "data" / "profitability-lab" / "forward-evidence"
DEFAULT_EXACT_SAMPLE_PLANS = ROOT / "data" / "profitability-lab" / "exact-sample-plans"
DEFAULT_TRACKED_WINNER_PROFILES = ROOT / "data" / "profitability-lab" / "tracked-winner-profiles"
DEFAULT_PAID_DATA_READINESS = ROOT / "data" / "profitability-lab" / "paid-data-readiness"
DEFAULT_OUTPUT = ROOT / "data" / "profitability-lab" / "research_summary.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _variant_rows(lab_runs: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report_path in sorted(lab_runs.glob("*/report.json")):
        report = _read_json(report_path)
        for variant in list(report.get("variants") or []):
            summary = dict(variant.get("summary") or {})
            source = dict(summary.get("source") or {})
            overall = dict(summary.get("overall") or {})
            verdict = dict(variant.get("verdict") or {})
            rows.append(
                {
                    "run_dir": str(report_path.parent),
                    "generated_at": report.get("generated_at"),
                    "variant": variant.get("id"),
                    "status": variant.get("status"),
                    "verdict": verdict.get("status"),
                    "promotion_allowed": bool(verdict.get("promotion_allowed")),
                    "pricing_lane": source.get("pricing_lane"),
                    "lookback_years": source.get("lookback_years"),
                    "n_picks": source.get("n_picks"),
                    "trades": overall.get("trades"),
                    "profit_factor": overall.get("profit_factor"),
                    "avg_pnl_pct": overall.get("avg_pnl_pct"),
                    "directional_accuracy_pct": overall.get("directional_accuracy_pct"),
                    "authoritative_trade_count": source.get("authoritative_trade_count"),
                    "quote_coverage_pct": source.get("quote_coverage_pct"),
                }
            )
    return rows


def _exit_sweep_rows(exit_sweeps: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sweep_path in sorted(exit_sweeps.glob("exit_sweep_*.json")):
        report = _read_json(sweep_path)
        for result in list(report.get("results") or []):
            summary = dict(result.get("summary") or {})
            rows.append(
                {
                    "sweep_path": str(sweep_path),
                    "variant": result.get("variant"),
                    "pricing_lane": result.get("pricing_lane"),
                    "lookback_years": result.get("lookback_years"),
                    "n_picks": result.get("n_picks"),
                    "spread_stop_loss_pct": result.get("spread_stop_loss_pct"),
                    "spread_time_exit_pct": result.get("spread_time_exit_pct"),
                    "trades": summary.get("trade_count"),
                    "profit_factor": summary.get("profit_factor"),
                    "avg_pnl_pct": summary.get("avg_pnl_pct"),
                    "directional_accuracy_pct": summary.get("directional_accuracy_pct"),
                    "gate_passed": summary.get("gate_passed"),
                    "exit_reasons": summary.get("exit_reasons"),
                }
            )
    return rows


def _losing_audit_rows(losing_audits: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit_path in sorted(losing_audits.glob("losing_window_audit_*.json")):
        audit = _read_json(audit_path)
        exact = dict(audit.get("exact_trade_metrics") or {})
        rows.append(
            {
                "audit_path": str(audit_path),
                "source_run": audit.get("source_run"),
                "playbook": audit.get("playbook"),
                "pricing_lane": audit.get("pricing_lane"),
                "lookback_years": audit.get("lookback_years"),
                "n_picks": audit.get("n_picks"),
                "trades": exact.get("trades"),
                "profit_factor": exact.get("profit_factor"),
                "avg_pnl_pct": exact.get("avg_pnl_pct"),
                "losing_trade_count": audit.get("losing_trade_count"),
                "top_worst_groups": list(audit.get("worst_groups") or [])[:5],
                "top_candidate_filters": list(audit.get("candidate_filters") or [])[:5],
            }
        )
    return rows


def _hypothesis_sweep_rows(hypothesis_sweeps: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sweep_path in sorted(hypothesis_sweeps.glob("hypothesis_sweep_*.json")):
        sweep = _read_json(sweep_path)
        rows.append(
            {
                "sweep_path": str(sweep_path),
                "source_run": sweep.get("source_run"),
                "lens": sweep.get("lens"),
                "hypothesis_suite": sweep.get("hypothesis_suite"),
                "playbook": sweep.get("playbook"),
                "pricing_lane": sweep.get("pricing_lane"),
                "lookback_years": sweep.get("lookback_years"),
                "n_picks": sweep.get("n_picks"),
                "baseline": sweep.get("baseline"),
                "hypothesis_count": sweep.get("hypothesis_count"),
                "top_results": list(sweep.get("results") or [])[:10],
            }
        )
    return rows


def _exact_coverage_rows(exact_coverage_audits: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for audit_path in sorted(exact_coverage_audits.glob("exact_coverage_audit_*.json")):
        audit = _read_json(audit_path)
        rows.append(
            {
                "audit_path": str(audit_path),
                "source_run": audit.get("source_run"),
                "playbook": audit.get("playbook"),
                "pricing_lane": audit.get("pricing_lane"),
                "lookback_years": audit.get("lookback_years"),
                "overall": audit.get("overall"),
                "by_ticker": audit.get("by_ticker"),
                "next_data_need": audit.get("next_data_need"),
            }
        )
    return rows


def _promotion_checklist_rows(promotion_checklists: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for checklist_path in sorted(promotion_checklists.glob("promotion_checklist_*.json")):
        checklist = _read_json(checklist_path)
        rows.append(
            {
                "checklist_path": str(checklist_path),
                "source_run": checklist.get("source_run"),
                "playbook": checklist.get("playbook"),
                "promotion_allowed": checklist.get("promotion_allowed"),
                "requirements": checklist.get("requirements"),
                "next_actions": checklist.get("next_actions"),
            }
        )
    return rows


def _canary_status_rows(canary_status: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status_path in sorted(canary_status.glob("canary_status_*.json")):
        status = _read_json(status_path)
        rows.append(
            {
                "status_path": str(status_path),
                "source_run": status.get("source_run"),
                "canary_id": status.get("canary_id"),
                "cohort_role": status.get("cohort_role"),
                "readiness": status.get("readiness"),
                "promotion_allowed": status.get("promotion_allowed"),
                "research_signal": status.get("research_signal"),
                "proof_signal": status.get("proof_signal"),
                "exact_coverage": status.get("exact_coverage"),
                "interpretation": status.get("interpretation"),
            }
        )
    return rows


def _forward_evidence_rows(forward_evidence: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report_path in sorted(forward_evidence.glob("forward_evidence_*.json")):
        report = _read_json(report_path)
        rows.append(
            {
                "report_path": str(report_path),
                "cohort_id": report.get("cohort_id"),
                "readiness": report.get("readiness"),
                "promotion_allowed": report.get("promotion_allowed"),
                "progress": report.get("progress"),
                "target": report.get("target"),
            }
        )
    return rows


def _exact_sample_plan_rows(exact_sample_plans: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan_path in sorted(exact_sample_plans.glob("exact_sample_plan_*.json")):
        plan = _read_json(plan_path)
        rows.append(
            {
                "plan_path": str(plan_path),
                "playbook": plan.get("playbook"),
                "targets": plan.get("targets"),
                "current": plan.get("current"),
                "gaps": plan.get("gaps"),
                "collection_order": plan.get("collection_order"),
            }
        )
    return rows


def _tracked_winner_profile_rows(tracked_winner_profiles: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_path in sorted(tracked_winner_profiles.glob("tracked_winner_profile_*.json")):
        profile = _read_json(profile_path)
        rows.append(
            {
                "profile_path": str(profile_path),
                "overall": profile.get("overall"),
                "winners": profile.get("winners"),
                "winner_count_by_ticker": profile.get("winner_count_by_ticker"),
                "candidate_lane": profile.get("candidate_lane"),
                "limitations": profile.get("limitations"),
            }
        )
    return rows


def _paid_data_readiness_rows(paid_data_readiness: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for readiness_path in sorted(paid_data_readiness.glob("paid_data_readiness_*.json")):
        readiness = _read_json(readiness_path)
        rows.append(
            {
                "readiness_path": str(readiness_path),
                "status": readiness.get("status"),
                "blocker": readiness.get("blocker"),
                "snapshot_kind": readiness.get("snapshot_kind"),
                "required_underlyings": readiness.get("required_underlyings"),
                "missing_required_underlyings": readiness.get("missing_required_underlyings"),
                "thin_required_underlyings": readiness.get("thin_required_underlyings"),
                "low_executable_required_underlyings": readiness.get("low_executable_required_underlyings"),
                "shared_required_quote_dates": readiness.get("shared_required_quote_dates"),
                "next_actions": readiness.get("next_actions"),
            }
        )
    return rows


def build_research_summary(
    *,
    lab_runs: Path = DEFAULT_LAB_RUNS,
    exit_sweeps: Path = DEFAULT_EXIT_SWEEPS,
    losing_audits: Path = DEFAULT_LOSING_AUDITS,
    hypothesis_sweeps: Path = DEFAULT_HYPOTHESIS_SWEEPS,
    exact_coverage_audits: Path = DEFAULT_EXACT_COVERAGE_AUDITS,
    promotion_checklists: Path = DEFAULT_PROMOTION_CHECKLISTS,
    canary_status: Path = DEFAULT_CANARY_STATUS,
    forward_evidence: Path = DEFAULT_FORWARD_EVIDENCE,
    exact_sample_plans: Path = DEFAULT_EXACT_SAMPLE_PLANS,
    tracked_winner_profiles: Path = DEFAULT_TRACKED_WINNER_PROFILES,
    paid_data_readiness: Path = DEFAULT_PAID_DATA_READINESS,
) -> dict[str, Any]:
    variants = _variant_rows(lab_runs)
    exit_rows = _exit_sweep_rows(exit_sweeps)
    losing_rows = _losing_audit_rows(losing_audits)
    hypothesis_rows = _hypothesis_sweep_rows(hypothesis_sweeps)
    exact_coverage_rows = _exact_coverage_rows(exact_coverage_audits)
    promotion_rows = _promotion_checklist_rows(promotion_checklists)
    canary_rows = _canary_status_rows(canary_status)
    forward_rows = _forward_evidence_rows(forward_evidence)
    sample_plan_rows = _exact_sample_plan_rows(exact_sample_plans)
    tracked_winner_rows = _tracked_winner_profile_rows(tracked_winner_profiles)
    paid_readiness_rows = _paid_data_readiness_rows(paid_data_readiness)
    return {
        "variant_run_count": len(variants),
        "exit_sweep_count": len(exit_rows),
        "losing_audit_count": len(losing_rows),
        "hypothesis_sweep_count": len(hypothesis_rows),
        "exact_coverage_audit_count": len(exact_coverage_rows),
        "promotion_checklist_count": len(promotion_rows),
        "canary_status_count": len(canary_rows),
        "forward_evidence_count": len(forward_rows),
        "exact_sample_plan_count": len(sample_plan_rows),
        "tracked_winner_profile_count": len(tracked_winner_rows),
        "paid_data_readiness_count": len(paid_readiness_rows),
        "variant_runs": variants,
        "exit_sweeps": exit_rows,
        "losing_window_audits": losing_rows,
        "hypothesis_sweeps": hypothesis_rows,
        "exact_coverage_audits": exact_coverage_rows,
        "promotion_checklists": promotion_rows,
        "canary_statuses": canary_rows,
        "forward_evidence": forward_rows,
        "exact_sample_plans": sample_plan_rows,
        "tracked_winner_profiles": tracked_winner_rows,
        "paid_data_readiness": paid_readiness_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize profitability research runs to avoid duplicate work.")
    parser.add_argument("--lab-runs", default=str(DEFAULT_LAB_RUNS))
    parser.add_argument("--exit-sweeps", default=str(DEFAULT_EXIT_SWEEPS))
    parser.add_argument("--losing-audits", default=str(DEFAULT_LOSING_AUDITS))
    parser.add_argument("--hypothesis-sweeps", default=str(DEFAULT_HYPOTHESIS_SWEEPS))
    parser.add_argument("--exact-coverage-audits", default=str(DEFAULT_EXACT_COVERAGE_AUDITS))
    parser.add_argument("--promotion-checklists", default=str(DEFAULT_PROMOTION_CHECKLISTS))
    parser.add_argument("--canary-status", default=str(DEFAULT_CANARY_STATUS))
    parser.add_argument("--forward-evidence", default=str(DEFAULT_FORWARD_EVIDENCE))
    parser.add_argument("--exact-sample-plans", default=str(DEFAULT_EXACT_SAMPLE_PLANS))
    parser.add_argument("--tracked-winner-profiles", default=str(DEFAULT_TRACKED_WINNER_PROFILES))
    parser.add_argument("--paid-data-readiness", default=str(DEFAULT_PAID_DATA_READINESS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = build_research_summary(
        lab_runs=Path(args.lab_runs),
        exit_sweeps=Path(args.exit_sweeps),
        losing_audits=Path(args.losing_audits),
        hypothesis_sweeps=Path(args.hypothesis_sweeps),
        exact_coverage_audits=Path(args.exact_coverage_audits),
        promotion_checklists=Path(args.promotion_checklists),
        canary_status=Path(args.canary_status),
        forward_evidence=Path(args.forward_evidence),
        exact_sample_plans=Path(args.exact_sample_plans),
        tracked_winner_profiles=Path(args.tracked_winner_profiles),
        paid_data_readiness=Path(args.paid_data_readiness),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf8")
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            json.dumps(
                {
                    "output": str(output),
                    "variant_run_count": summary["variant_run_count"],
                    "exit_sweep_count": summary["exit_sweep_count"],
                    "losing_audit_count": summary["losing_audit_count"],
                    "hypothesis_sweep_count": summary["hypothesis_sweep_count"],
                    "exact_coverage_audit_count": summary["exact_coverage_audit_count"],
                    "promotion_checklist_count": summary["promotion_checklist_count"],
                    "canary_status_count": summary["canary_status_count"],
                    "forward_evidence_count": summary["forward_evidence_count"],
                    "exact_sample_plan_count": summary["exact_sample_plan_count"],
                    "tracked_winner_profile_count": summary["tracked_winner_profile_count"],
                    "paid_data_readiness_count": summary["paid_data_readiness_count"],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
