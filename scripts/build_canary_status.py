from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_EXACT_COVERAGE_DIR = ROOT / "data" / "profitability-lab" / "exact-coverage-audits"
DEFAULT_PROMOTION_CHECKLIST_DIR = ROOT / "data" / "profitability-lab" / "promotion-checklists"
DEFAULT_FORWARD_EVIDENCE_DIR = ROOT / "data" / "profitability-lab" / "forward-evidence"
DEFAULT_SAMPLE_PLAN_DIR = ROOT / "data" / "profitability-lab" / "exact-sample-plans"
DEFAULT_LAB_LATEST = ROOT / "data" / "profitability-lab" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "canary-status"
DEFAULT_PLAYBOOK = "bullish_index_calls_quality90_debit55"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _latest_matching_run(runs_dir: Path, playbook: str) -> Path:
    matches = sorted(Path(runs_dir).glob(f"*{playbook}*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No runs found for playbook {playbook!r} under {runs_dir}")
    return matches[0]


def _optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _read_json(path)


def _metric(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _requirement_status(requirements: list[dict[str, Any]], requirement_id: str) -> str | None:
    for requirement in requirements:
        if requirement.get("id") == requirement_id:
            return str(requirement.get("status") or "")
    return None


def _fingerprint_payload(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "canary_status",
        "source_run": status.get("source_run"),
        "coverage_audit": status.get("coverage_audit"),
        "promotion_checklist": status.get("promotion_checklist"),
        "forward_evidence": status.get("forward_evidence"),
        "sample_plan": status.get("sample_plan"),
    }


def build_canary_status_fingerprint(status: dict[str, Any]) -> str:
    payload = _fingerprint_payload(status)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_canary_status(output_dir: Path, fingerprint: str) -> Path | None:
    for status_path in sorted(Path(output_dir).glob("canary_status_*.json")):
        try:
            status = _read_json(status_path)
        except (OSError, json.JSONDecodeError):
            continue
        if status.get("status_fingerprint") == fingerprint:
            return status_path
    return None


def build_canary_status(
    run_path: Path,
    *,
    exact_coverage_path: Path | None = None,
    promotion_checklist_path: Path | None = None,
    forward_evidence_path: Path | None = None,
    sample_plan_path: Path | None = None,
    lab_latest_path: Path | None = None,
) -> dict[str, Any]:
    run = _read_json(run_path)
    exact_coverage = _optional_json(exact_coverage_path)
    checklist = _optional_json(promotion_checklist_path)
    forward_evidence = _optional_json(forward_evidence_path)
    sample_plan = _optional_json(sample_plan_path)
    lab_latest = _optional_json(lab_latest_path)
    proof = dict(run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {})
    research = {
        "trade_count": run.get("total_trades"),
        "profit_factor": run.get("profit_factor"),
        "avg_pnl_pct": run.get("avg_pnl_pct"),
        "win_rate_pct": run.get("win_rate_pct"),
    }
    requirements = list(checklist.get("requirements") or [])
    blockers = [
        requirement
        for requirement in requirements
        if str(requirement.get("status") or "").lower() not in {"pass", "passed"}
    ]
    measurement_gate = dict(lab_latest.get("measurement_gate") or {})
    trusted_truth_blockers = [
        blocker
        for blocker in list(measurement_gate.get("blockers") or [])
        if str(blocker.get("severity") or "").lower() == "blocked"
    ]
    proof_trade_count = int(_metric(proof, "trade_count", "trades") or 0)
    proof_profit_factor = float(_metric(proof, "profit_factor", "net_profit_factor") or 0.0)
    research_profit_factor = float(research.get("profit_factor") or 0.0)
    exact_trade_status = _requirement_status(requirements, "exact_historical_trade_count")
    forward_status = _requirement_status(requirements, "closed_forward_trade_count")
    forward_progress = dict(forward_evidence.get("progress") or {})
    forward_closed_count = int(forward_progress.get("closed_forward_trade_count") or 0)
    if forward_status and forward_closed_count > 0:
        for requirement in requirements:
            if requirement.get("id") == "closed_forward_trade_count":
                requirement["current"] = max(int(requirement.get("current") or 0), forward_closed_count)
                requirement["status"] = "pass" if requirement["current"] >= int(requirement.get("target") or 0) else requirement["status"]
        blockers = [
            requirement
            for requirement in requirements
            if str(requirement.get("status") or "").lower() not in {"pass", "passed"}
        ]
    promotion_allowed = bool(requirements) and not blockers and not trusted_truth_blockers
    if promotion_allowed:
        readiness = "promotion_ready"
    elif research_profit_factor > 1.0 and (proof_trade_count < 40 or proof_profit_factor < 1.2):
        readiness = "research_positive_needs_exact_proof"
    else:
        readiness = "collecting_proof"
    status = {
        "canary_id": "quality90_debit55_canary",
        "cohort_role": "proof_control_yardstick",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_run": str(run_path),
        "coverage_audit": str(exact_coverage_path) if exact_coverage_path else None,
        "promotion_checklist": str(promotion_checklist_path) if promotion_checklist_path else None,
        "forward_evidence": str(forward_evidence_path) if forward_evidence_path else None,
        "sample_plan": str(sample_plan_path) if sample_plan_path else None,
        "playbook": run.get("playbook"),
        "readiness": readiness,
        "promotion_allowed": promotion_allowed,
        "research_signal": research,
        "proof_signal": proof,
        "exact_coverage": exact_coverage.get("overall"),
        "forward_progress": forward_progress,
        "sample_gaps": sample_plan.get("gaps"),
        "requirements": requirements,
        "measurement_gate_state": measurement_gate.get("state"),
        "trusted_truth_blockers": trusted_truth_blockers,
        "data_window": {
            "lookback_years_requested": run.get("lookback_years"),
            "earliest_quote_at_utc": (run.get("truth_store") or {}).get("earliest_quote_at_utc"),
            "latest_quote_at_utc": (run.get("truth_store") or {}).get("latest_quote_at_utc"),
        },
        "interpretation": {
            "current_claim": (
                "Research-positive, not promotable: all-priced rows look strong, but exact-contract proof and forward canary outcomes are not sufficient."
                if readiness == "research_positive_needs_exact_proof"
                else "Use the requirements and blockers before changing live policy."
            ),
            "exact_historical_trade_status": exact_trade_status,
            "closed_forward_trade_status": _requirement_status(requirements, "closed_forward_trade_count") or forward_status,
        },
        "next_actions": [
            "Keep the canary as a proof/control yardstick.",
            "Collect exact live-chain forward outcomes before promotion.",
            "Import more trusted exact-chain history if you want a larger historical proof sample faster.",
        ],
    }
    status["status_fingerprint"] = build_canary_status_fingerprint(status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact status artifact for the quality90/debit55 canary.")
    parser.add_argument("--run")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--playbook", default=DEFAULT_PLAYBOOK)
    parser.add_argument("--exact-coverage", default=str(DEFAULT_EXACT_COVERAGE_DIR / "latest.json"))
    parser.add_argument("--promotion-checklist", default=str(DEFAULT_PROMOTION_CHECKLIST_DIR / "latest.json"))
    parser.add_argument("--forward-evidence", default=str(DEFAULT_FORWARD_EVIDENCE_DIR / "latest_quality90_debit55_canary.json"))
    parser.add_argument("--sample-plan", default=str(DEFAULT_SAMPLE_PLAN_DIR / "latest.json"))
    parser.add_argument("--lab-latest", default=str(DEFAULT_LAB_LATEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Write a new status artifact even if the inputs were already summarized.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_path = Path(args.run) if args.run else _latest_matching_run(Path(args.runs_dir), args.playbook)
    exact_coverage_path = Path(args.exact_coverage) if args.exact_coverage else None
    checklist_path = Path(args.promotion_checklist) if args.promotion_checklist else None
    forward_evidence_path = Path(args.forward_evidence) if args.forward_evidence else None
    sample_plan_path = Path(args.sample_plan) if args.sample_plan else None
    lab_latest_path = Path(args.lab_latest) if args.lab_latest else None
    status = build_canary_status(
        run_path,
        exact_coverage_path=exact_coverage_path,
        promotion_checklist_path=checklist_path,
        forward_evidence_path=forward_evidence_path,
        sample_plan_path=sample_plan_path,
        lab_latest_path=lab_latest_path,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_canary_status(output_dir, str(status.get("status_fingerprint") or ""))
    if duplicate is not None and not args.force:
        compact = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "fingerprint": status.get("status_fingerprint"),
            "readiness": status.get("readiness"),
            "promotion_allowed": status.get("promotion_allowed"),
            "interpretation": status.get("interpretation"),
            "hint": "Use --force to write a new canary status artifact for these inputs.",
        }
        print(json.dumps(status if args.json else compact, indent=2))
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"canary_status_{stamp}_{run_path.stem}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(status, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "readiness": status.get("readiness"),
        "promotion_allowed": status.get("promotion_allowed"),
        "interpretation": status.get("interpretation"),
    }
    print(json.dumps(status if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
