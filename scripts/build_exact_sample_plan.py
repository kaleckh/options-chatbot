from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE_PATH = ROOT / "data" / "profitability-lab" / "exact-coverage-audits" / "latest.json"
DEFAULT_CHECKLIST_PATH = ROOT / "data" / "profitability-lab" / "promotion-checklists" / "latest.json"
DEFAULT_FORWARD_EVIDENCE_PATH = ROOT / "data" / "profitability-lab" / "forward-evidence" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "exact-sample-plans"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _read_json(path)


def _requirement(requirements: list[dict[str, Any]], requirement_id: str) -> dict[str, Any]:
    for item in requirements:
        if item.get("id") == requirement_id:
            return dict(item)
    return {}


def _fingerprint_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "exact_sample_plan",
        "coverage_audit": plan.get("coverage_audit"),
        "promotion_checklist": plan.get("promotion_checklist"),
        "forward_evidence": plan.get("forward_evidence"),
        "targets": plan.get("targets"),
    }


def build_exact_sample_plan_fingerprint(plan: dict[str, Any]) -> str:
    payload = _fingerprint_payload(plan)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_exact_sample_plan(output_dir: Path, fingerprint: str) -> Path | None:
    for plan_path in sorted(Path(output_dir).glob("exact_sample_plan_*.json")):
        try:
            plan = _read_json(plan_path)
        except (OSError, json.JSONDecodeError):
            continue
        if plan.get("sample_plan_fingerprint") == fingerprint:
            return plan_path
    return None


def build_exact_sample_plan(
    *,
    coverage_path: Path = DEFAULT_COVERAGE_PATH,
    checklist_path: Path = DEFAULT_CHECKLIST_PATH,
    forward_evidence_path: Path | None = DEFAULT_FORWARD_EVIDENCE_PATH,
) -> dict[str, Any]:
    coverage = _read_json(coverage_path)
    checklist = _read_json(checklist_path)
    forward = _optional_json(forward_evidence_path)
    requirements = list(checklist.get("requirements") or [])
    exact_req = _requirement(requirements, "exact_historical_trade_count")
    forward_req = _requirement(requirements, "closed_forward_trade_count")
    exact_current = int(exact_req.get("current") or (coverage.get("overall") or {}).get("exact") or 0)
    exact_target = int(exact_req.get("target") or 40)
    forward_progress = dict(forward.get("progress") or {})
    forward_current = int(forward_progress.get("closed_forward_trade_count") or forward_req.get("current") or 0)
    forward_target = int(forward_req.get("target") or 20)
    exact_needed = max(exact_target - exact_current, 0)
    forward_needed = max(forward_target - forward_current, 0)
    exact_pct = float((coverage.get("overall") or {}).get("exact_pct") or 0.0)
    candidate_rows_needed_at_current_coverage = ceil(exact_needed / (exact_pct / 100.0)) if exact_needed and exact_pct > 0 else None
    plan = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "coverage_audit": str(coverage_path),
        "promotion_checklist": str(checklist_path),
        "forward_evidence": str(forward_evidence_path) if forward_evidence_path else None,
        "playbook": coverage.get("playbook") or checklist.get("playbook"),
        "targets": {
            "exact_historical_trade_count": exact_target,
            "closed_forward_trade_count": forward_target,
        },
        "current": {
            "exact_historical_trade_count": exact_current,
            "closed_forward_trade_count": forward_current,
            "exact_coverage_pct": exact_pct,
        },
        "gaps": {
            "exact_historical_trades_needed": exact_needed,
            "closed_forward_trades_needed": forward_needed,
            "candidate_rows_needed_at_current_exact_coverage": candidate_rows_needed_at_current_coverage,
        },
        "data_window": {
            "earliest_quote_at_utc": coverage.get("earliest_quote_at_utc"),
            "latest_quote_at_utc": coverage.get("latest_quote_at_utc"),
        },
        "collection_order": [
            {
                "id": "collect_forward_canary_outcomes",
                "status": "active" if forward_needed else "complete",
                "why": "Forward exact-contract outcomes are the cleanest proof for promotion.",
                "needed": forward_needed,
            },
            {
                "id": "import_more_trusted_exact_chain_history",
                "status": "active" if exact_needed else "complete",
                "why": "The current trusted historical window only produced a thin exact-contract proof sample.",
                "needed": exact_needed,
                "estimated_candidate_rows_at_current_coverage": candidate_rows_needed_at_current_coverage,
            },
            {
                "id": "do_not_score_nearest_rows_as_proof",
                "status": "always_on",
                "why": "Nearest-listed rows are useful for research but should not promote the canary.",
            },
        ],
    }
    plan["sample_plan_fingerprint"] = build_exact_sample_plan_fingerprint(plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a concrete exact-sample collection plan for the canary.")
    parser.add_argument("--coverage", default=str(DEFAULT_COVERAGE_PATH))
    parser.add_argument("--checklist", default=str(DEFAULT_CHECKLIST_PATH))
    parser.add_argument("--forward-evidence", default=str(DEFAULT_FORWARD_EVIDENCE_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Write a new artifact even if the same inputs were already planned.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    forward_path = Path(args.forward_evidence) if args.forward_evidence else None
    plan = build_exact_sample_plan(
        coverage_path=Path(args.coverage),
        checklist_path=Path(args.checklist),
        forward_evidence_path=forward_path,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_exact_sample_plan(output_dir, str(plan.get("sample_plan_fingerprint") or ""))
    if duplicate is not None and not args.force:
        compact = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "fingerprint": plan.get("sample_plan_fingerprint"),
            "gaps": plan.get("gaps"),
            "hint": "Use --force to write a new exact sample plan for these unchanged inputs.",
        }
        print(json.dumps(plan if args.json else compact, indent=2))
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"exact_sample_plan_{stamp}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(plan, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "gaps": plan.get("gaps"),
        "collection_order": plan.get("collection_order"),
    }
    print(json.dumps(plan if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
