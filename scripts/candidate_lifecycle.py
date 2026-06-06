from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = ROOT / "data" / "contracts" / "candidate-lifecycle-contract.json"
DEFAULT_DOCS_PATH = ROOT / "docs" / "candidate-lifecycle-contract.md"
DEFAULT_TYPESCRIPT_PATH = ROOT / "src" / "lib" / "generated" / "candidateLifecycleContract.ts"

CONTRACT_VERSION = 1
REPORT_ID = "candidate_lifecycle_contract"

STATUS_PENDING_LIVE_VALIDATION = "pending_live_validation"
STATUS_PENDING_PAPER_EXACT_EVIDENCE = "pending_paper_exact_evidence"
STATUS_PAPER_EXACT_EVIDENCE_ATTEMPTED = "paper_exact_evidence_attempted"
STATUS_PAPER_EXACT_EVIDENCE_SCAN_FAILED = "paper_exact_evidence_scan_failed"
STATUS_LIVE_VALIDATION_ATTEMPTED = "live_validation_attempted"
STATUS_LIVE_VALIDATION_SCAN_FAILED = "live_validation_scan_failed"
STATUS_DIAGNOSTIC_UNAPPROVED_LANE = "diagnostic_only_unapproved_lane"
STATUS_DIAGNOSTIC_LANE_PROFITABILITY_GATE = "diagnostic_only_lane_profitability_gate"
STATUS_DIAGNOSTIC_LANE_PROMOTION_STATE = "diagnostic_only_lane_promotion_state"
STATUS_PAPER_LANE_PROFITABILITY_GATE = "paper_validation_only_lane_profitability_gate"
STATUS_PAPER_LANE_PROFITABILITY_PROBATION = "paper_validation_only_lane_profitability_probation"
STATUS_PAPER_LANE_PROMOTION_STATE = "paper_validation_only_lane_promotion_state"
STATUS_PAPER_CIRCUIT_BREAKER = "paper_validation_only_circuit_breaker"
STATUS_PAPER_DUPLICATE_EXACT_SPREAD = "paper_validation_only_duplicate_exact_spread"

OUTCOME_CREATED = "created"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_BLOCKED = "blocked"
OUTCOME_NO_LONGER_MATCHED = "no_longer_matched"
OUTCOME_PAPER_ONLY = "paper_only"
OUTCOME_PROOF_INELIGIBLE = "proof_ineligible"
OUTCOME_PENDING_VALIDATION = "pending_validation"
OUTCOME_DIAGNOSTIC_ONLY = "diagnostic_only"
OUTCOME_UNKNOWN = "unknown"


@dataclass(frozen=True)
class CandidateStatusSpec:
    status: str
    phase: str
    family: str
    description: str
    pending_validation: bool = False
    reportable_in_validation_disposition: bool = False
    paper_only: bool = False
    diagnostic_only: bool = False
    validation_attempt: bool = False
    terminal: bool = False
    validation_outcome: str | None = None
    default_outcome_reason: str | None = None
    fresh_evidence_loop_outcome: str | None = None
    fresh_evidence_loop_reason: str | None = None


STATUS_SPECS: tuple[CandidateStatusSpec, ...] = (
    CandidateStatusSpec(
        status=STATUS_PENDING_LIVE_VALIDATION,
        phase="queued",
        family="live_validation",
        description="Clear candidate is queued for a fresh market-hours live validation scan.",
        pending_validation=True,
        fresh_evidence_loop_outcome=OUTCOME_PENDING_VALIDATION,
        fresh_evidence_loop_reason="candidate_waiting_for_market_hours_validation",
    ),
    CandidateStatusSpec(
        status=STATUS_PENDING_PAPER_EXACT_EVIDENCE,
        phase="paper_evidence_pending",
        family="paper_exact_evidence",
        description="Paper/probation candidate is queued for exact OPRA/NBBO evidence capture with live creation disabled.",
        paper_only=True,
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="paper_probation_candidate_waiting_for_exact_evidence_capture",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_EXACT_EVIDENCE_ATTEMPTED,
        phase="paper_evidence_attempted",
        family="paper_exact_evidence",
        description="Paper/probation exact evidence capture ran; evidence rows remain paper-only and cannot create live/tracked rows.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        validation_attempt=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="paper_probation_exact_evidence_capture_attempted_no_live_create",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="paper_probation_exact_evidence_capture_attempted_no_live_create",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_EXACT_EVIDENCE_SCAN_FAILED,
        phase="paper_evidence_attempted",
        family="paper_exact_evidence",
        description="Paper/probation exact evidence capture failed before usable exact evidence was available.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="paper_probation_exact_evidence_capture_failed_no_live_create",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="paper_probation_exact_evidence_capture_failed_no_live_create",
    ),
    CandidateStatusSpec(
        status=STATUS_LIVE_VALIDATION_ATTEMPTED,
        phase="validation_attempted",
        family="live_validation",
        description="Fresh validation lane reran; fill-attempt evidence determines the final disposition.",
        reportable_in_validation_disposition=True,
        validation_attempt=True,
    ),
    CandidateStatusSpec(
        status=STATUS_LIVE_VALIDATION_SCAN_FAILED,
        phase="validation_attempted",
        family="live_validation",
        description="Fresh validation rerun failed before a usable fill/creation disposition was available.",
        reportable_in_validation_disposition=True,
        terminal=True,
        validation_outcome=OUTCOME_BLOCKED,
        default_outcome_reason="validation_scan_failed",
    ),
    CandidateStatusSpec(
        status=STATUS_DIAGNOSTIC_UNAPPROVED_LANE,
        phase="diagnostic",
        family="lane_scope",
        description="Candidate came from a lane that is not enabled for fresh live validation.",
        diagnostic_only=True,
        terminal=True,
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="candidate_lane_is_diagnostic_only",
    ),
    CandidateStatusSpec(
        status=STATUS_DIAGNOSTIC_LANE_PROFITABILITY_GATE,
        phase="diagnostic",
        family="lane_profitability_gate",
        description="Candidate or lane failed the current profitability gate or gate-health checks.",
        diagnostic_only=True,
        terminal=True,
        fresh_evidence_loop_outcome=OUTCOME_DIAGNOSTIC_ONLY,
        fresh_evidence_loop_reason="lane_profitability_gate_diagnostic_only",
    ),
    CandidateStatusSpec(
        status=STATUS_DIAGNOSTIC_LANE_PROMOTION_STATE,
        phase="diagnostic",
        family="lane_promotion_state",
        description="Lane promotion state is diagnostic-only, missing, stale, or otherwise unusable.",
        diagnostic_only=True,
        terminal=True,
        fresh_evidence_loop_outcome=OUTCOME_DIAGNOSTIC_ONLY,
        fresh_evidence_loop_reason="lane_promotion_state_diagnostic_only",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_LANE_PROFITABILITY_GATE,
        phase="paper_validation",
        family="lane_profitability_gate",
        description="Candidate is routed to paper validation by the lane profitability gate.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="lane_profitability_gate_routes_candidate_to_paper_only",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="lane_profitability_gate_routes_candidate_to_paper_only",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_LANE_PROFITABILITY_PROBATION,
        phase="paper_probation",
        family="lane_profitability_gate",
        description="Historically profitable lane is in probation and requires fresh paper validation before live validation.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="lane_profitability_gate_probation_requires_paper_validation",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="lane_profitability_gate_probation_requires_paper_validation",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_LANE_PROMOTION_STATE,
        phase="paper_probation",
        family="lane_promotion_state",
        description="Lane promotion state is paper/probation until walk-forward, fresh paper, and current risk gates clear.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="lane_promotion_state_routes_candidate_to_paper_only",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="lane_promotion_state_routes_candidate_to_paper_only",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_CIRCUIT_BREAKER,
        phase="paper_validation",
        family="current_policy_circuit_breaker",
        description="Recent-cohort circuit breaker routes the lane to paper validation only.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="recent_cohort_circuit_breaker_routes_lane_to_paper_validation_only",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="recent_cohort_circuit_breaker_routes_lane_to_paper_validation_only",
    ),
    CandidateStatusSpec(
        status=STATUS_PAPER_DUPLICATE_EXACT_SPREAD,
        phase="paper_validation",
        family="duplicate_spread_suppression",
        description="Exact duplicate spread was suppressed to a single deterministic risk owner.",
        reportable_in_validation_disposition=True,
        paper_only=True,
        terminal=True,
        validation_outcome=OUTCOME_PAPER_ONLY,
        default_outcome_reason="duplicate_exact_spread_suppressed_to_single_risk_slot",
        fresh_evidence_loop_outcome=OUTCOME_PAPER_ONLY,
        fresh_evidence_loop_reason="duplicate_exact_spread_suppressed_to_single_risk_slot",
    ),
)

CANDIDATE_LIFECYCLE_STATUSES = tuple(spec.status for spec in STATUS_SPECS)
CANDIDATE_VALIDATION_OUTCOMES = (
    OUTCOME_CREATED,
    OUTCOME_DUPLICATE,
    OUTCOME_BLOCKED,
    OUTCOME_NO_LONGER_MATCHED,
    OUTCOME_PAPER_ONLY,
    OUTCOME_PROOF_INELIGIBLE,
)
FRESH_EVIDENCE_LOOP_OUTCOMES = CANDIDATE_VALIDATION_OUTCOMES + (
    OUTCOME_PENDING_VALIDATION,
    OUTCOME_DIAGNOSTIC_ONLY,
    OUTCOME_UNKNOWN,
)

PENDING_VALIDATION_STATUSES = frozenset(
    spec.status for spec in STATUS_SPECS if spec.pending_validation
)
VALIDATION_REPORT_STATUSES = frozenset(
    spec.status for spec in STATUS_SPECS if spec.reportable_in_validation_disposition
)
PAPER_ONLY_STATUSES = frozenset(spec.status for spec in STATUS_SPECS if spec.paper_only)
DIAGNOSTIC_ONLY_STATUSES = frozenset(spec.status for spec in STATUS_SPECS if spec.diagnostic_only)
TERMINAL_STATUSES = frozenset(spec.status for spec in STATUS_SPECS if spec.terminal)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def candidate_status_spec(status: Any) -> CandidateStatusSpec | None:
    wanted = _norm(status)
    for spec in STATUS_SPECS:
        if spec.status == wanted:
            return spec
    return None


def is_candidate_lifecycle_status(status: Any) -> bool:
    return candidate_status_spec(status) is not None


def is_pending_validation_status(status: Any) -> bool:
    return _norm(status) in PENDING_VALIDATION_STATUSES


def is_validation_report_status(status: Any) -> bool:
    return _norm(status) in VALIDATION_REPORT_STATUSES


def is_paper_only_status(status: Any) -> bool:
    return _norm(status) in PAPER_ONLY_STATUSES


def is_diagnostic_only_status(status: Any) -> bool:
    return _norm(status) in DIAGNOSTIC_ONLY_STATUSES


def validation_outcome_for_status(
    status: Any,
    candidate_status_reason: Any = "",
) -> tuple[str, str] | None:
    spec = candidate_status_spec(status)
    if spec is None or not spec.validation_outcome:
        return None
    reason = _norm(candidate_status_reason) or spec.default_outcome_reason or spec.validation_outcome
    return spec.validation_outcome, reason


def fresh_evidence_loop_outcome_for_status(
    status: Any,
    candidate_status_reason: Any = "",
) -> tuple[str, str] | None:
    spec = candidate_status_spec(status)
    if spec is None or not spec.fresh_evidence_loop_outcome:
        return None
    reason = _norm(candidate_status_reason) or spec.fresh_evidence_loop_reason or spec.fresh_evidence_loop_outcome
    return spec.fresh_evidence_loop_outcome, reason


def candidate_status_contract_rows() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in STATUS_SPECS]


def build_contract() -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "version": CONTRACT_VERSION,
        "generated_by": "scripts/candidate_lifecycle.py",
        "runtime_use": False,
        "source": "scripts/candidate_lifecycle.py",
        "purpose": (
            "Canonical lifecycle statuses and validation outcomes for regular-options pending scan "
            "candidates, paper-validation routes, diagnostic routes, and fresh validation dispositions."
        ),
        "non_goals": [
            "create trades",
            "submit broker orders",
            "lower OPRA/NBBO proof bars",
            "change lane promotion policy",
            "turn research/backfill rows into production proof",
        ],
        "status_sets": {
            "pending_validation": sorted(PENDING_VALIDATION_STATUSES),
            "validation_report": sorted(VALIDATION_REPORT_STATUSES),
            "paper_only": sorted(PAPER_ONLY_STATUSES),
            "diagnostic_only": sorted(DIAGNOSTIC_ONLY_STATUSES),
            "terminal": sorted(TERMINAL_STATUSES),
        },
        "validation_outcomes": list(CANDIDATE_VALIDATION_OUTCOMES),
        "fresh_evidence_loop_outcomes": list(FRESH_EVIDENCE_LOOP_OUTCOMES),
        "statuses": candidate_status_contract_rows(),
    }


def render_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Candidate Lifecycle Contract",
        "",
        "Generated by `scripts/candidate_lifecycle.py`. Do not hand-edit this file.",
        "",
        "This generated contract defines the canonical pending-candidate status vocabulary used by the regular-options all-lanes audit, pending validation reruns, paper-only gates, and fresh-evidence readbacks. It is generated from `scripts/candidate_lifecycle.py`.",
        "",
        "It does not create trades, submit broker orders, lower OPRA/NBBO proof bars, change lane promotion policy, or turn research/backfill rows into production proof.",
        "",
        "## Status Sets",
        "",
    ]
    for key, values in contract["status_sets"].items():
        lines.append(f"- `{key}`: `{json.dumps(values)}`")
    lines.extend(
        [
            "",
            "## Validation Outcomes",
            "",
            f"- Disposition outcomes: `{json.dumps(contract['validation_outcomes'])}`",
            f"- Fresh-evidence loop outcomes: `{json.dumps(contract['fresh_evidence_loop_outcomes'])}`",
            "",
            "## Statuses",
            "",
            "| Status | Phase | Family | Disposition outcome | Reported | Paper | Diagnostic | Description |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in contract["statuses"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("status")),
                    _fmt(row.get("phase")),
                    _fmt(row.get("family")),
                    _fmt(row.get("validation_outcome")),
                    _fmt(row.get("reportable_in_validation_disposition")),
                    _fmt(row.get("paper_only")),
                    _fmt(row.get("diagnostic_only")),
                    _fmt(row.get("description")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_typescript(contract: dict[str, Any]) -> str:
    version = contract.get("version")
    if not isinstance(version, int):
        raise ValueError("candidate lifecycle contract must declare an integer version")
    serialized = json.dumps(contract, indent=2, ensure_ascii=False)
    statuses = json.dumps([row["status"] for row in contract["statuses"]], indent=2)
    outcomes = json.dumps(contract["validation_outcomes"], indent=2)
    return (
        "// Generated by scripts/candidate_lifecycle.py.\n"
        "// Source: data/contracts/candidate-lifecycle-contract.json.\n"
        "// Do not hand-edit.\n\n"
        f"export const CANDIDATE_LIFECYCLE_CONTRACT_VERSION = {version} as const;\n\n"
        f"export const CANDIDATE_LIFECYCLE_CONTRACT = {serialized} as const;\n\n"
        f"export const CANDIDATE_LIFECYCLE_STATUSES = {statuses} as const;\n\n"
        "export type CandidateLifecycleStatus = typeof CANDIDATE_LIFECYCLE_STATUSES[number];\n\n"
        f"export const CANDIDATE_VALIDATION_OUTCOMES = {outcomes} as const;\n\n"
        "export type CandidateValidationOutcome = typeof CANDIDATE_VALIDATION_OUTCOMES[number];\n"
    )


def write_outputs(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    docs_path: Path = DEFAULT_DOCS_PATH,
    typescript_path: Path = DEFAULT_TYPESCRIPT_PATH,
) -> None:
    contract = build_contract()
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    typescript_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_path.write_text(render_markdown(contract), encoding="utf8")
    typescript_path.write_text(render_typescript(contract), encoding="utf8")


def _check_file(path: Path, rendered: str) -> bool:
    if not path.exists():
        print(f"{path.relative_to(ROOT)} is missing; run scripts/candidate_lifecycle.py.", file=sys.stderr)
        return False
    current = path.read_text(encoding="utf8")
    if current != rendered:
        print(f"{path.relative_to(ROOT)} is out of date; run scripts/candidate_lifecycle.py.", file=sys.stderr)
        return False
    return True


def check_outputs(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    docs_path: Path = DEFAULT_DOCS_PATH,
    typescript_path: Path = DEFAULT_TYPESCRIPT_PATH,
) -> bool:
    contract = build_contract()
    return all(
        [
            _check_file(contract_path, json.dumps(contract, indent=2, sort_keys=True) + "\n"),
            _check_file(docs_path, render_markdown(contract)),
            _check_file(typescript_path, render_typescript(contract)),
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the regular-options candidate lifecycle contract.")
    parser.add_argument("--contract-path", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--docs-path", type=Path, default=DEFAULT_DOCS_PATH)
    parser.add_argument("--typescript-path", type=Path, default=DEFAULT_TYPESCRIPT_PATH)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        return 0 if check_outputs(
            contract_path=args.contract_path,
            docs_path=args.docs_path,
            typescript_path=args.typescript_path,
        ) else 1
    write_outputs(
        contract_path=args.contract_path,
        docs_path=args.docs_path,
        typescript_path=args.typescript_path,
    )
    if args.json:
        print(json.dumps(build_contract(), indent=2, sort_keys=True))
    else:
        print(f"Wrote {args.contract_path}")
        print(f"Wrote {args.docs_path}")
        print(f"Wrote {args.typescript_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
