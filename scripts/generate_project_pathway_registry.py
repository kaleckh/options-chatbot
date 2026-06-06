from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "project-pathway-registry.json"
MD_OUTPUT_PATH = ROOT / "docs" / "project-operating-map.md"

REPORT_ID = "project_pathway_registry"
GENERATOR = "scripts/generate_project_pathway_registry.py"

PATHWAYS: tuple[dict[str, Any], ...] = (
    {
        "id": "data_path",
        "label": "Data Path",
        "question": "Can we trust the market data, repositories, and P&L fields?",
        "plain_english": "This path proves the raw material is usable before anyone argues about picks.",
        "owner_docs": (
            "docs/repository-constraints.md",
            "docs/storage-ownership-map.md",
            "docs/paid-options-data-import-checklist.md",
            "docs/NEXT_STEPS.md",
        ),
        "owner_scripts": (
            "scripts/audit_repository_constraints.py",
            "scripts/import_thetadata_options_nbbo.py",
            "scripts/audit_paid_data_readiness.py",
            "scripts/repair_historical_backfill_realized_pnl.py",
        ),
        "primary_artifacts": (
            "data/options-validation/options_history.db",
            "chat_history.db",
            "DATABASE_URL",
            "data/forward-tracking/historical_suggested_close_realized_pnl_repair_v1_latest.json",
        ),
        "gates": (
            "Closed production/unclassified tracked rows must have realized P&L.",
            "Closed suggested trades must have stored exit/P&L.",
            "Historical repairs must use trusted exact OPRA/NBBO quotes.",
            "Daily/EOD, midpoint, stale, last-trade, or display marks are not production proof.",
        ),
        "failure_mode": "Bad data makes every downstream pick, P&L, and blocker suspect.",
    },
    {
        "id": "candidate_path",
        "label": "Candidate Path",
        "question": "Did the scanner find a possible regular-options trade, and what is its lifecycle state?",
        "plain_english": "This path turns scanner output into queued, diagnostic, paper-only, or validation-attempted candidate rows.",
        "owner_docs": (
            "docs/scanner-creation-safety-contract.md",
            "docs/candidate-lifecycle-contract.md",
            "docs/regular-guardrail-starvation-audit.md",
        ),
        "owner_scripts": (
            "scripts/ensure_daily_all_lanes_audit_ran.py",
            "scripts/pending_audit_candidates.py",
            "scripts/validate_pending_scan_candidates.py",
            "scripts/candidate_lifecycle.py",
        ),
        "primary_artifacts": (
            "data/forward-tracking/regular_guardrail_starvation_latest.json",
            "data/forward-tracking/pending_scan_candidates.jsonl",
            "data/forward-tracking/pending_scan_candidate_validation_latest.json",
            "data/contracts/candidate-lifecycle-contract.json",
        ),
        "gates": (
            "All supervised lanes must be audited for no-pick explanations.",
            "Clear candidates are queued, not silently dropped.",
            "Candidate statuses must come from the lifecycle contract.",
            "Pending validation reruns must use portfolio caps and current lane gates.",
        ),
        "failure_mode": "Selected candidates can vanish or be mislabeled if queue/lifecycle status handling drifts.",
    },
    {
        "id": "evidence_path",
        "label": "Evidence Path",
        "question": "Is the quote/proof exact enough to support a claim or a tracked row?",
        "plain_english": "This path separates fresh executable OPRA/NBBO evidence from research, paper, stale, midpoint, and lifecycle-only rows.",
        "owner_docs": (
            "docs/proof-evidence-contract.md",
            "docs/proof-invariant-table.md",
            "docs/regular-options-fresh-evidence-loop.md",
        ),
        "owner_scripts": (
            "scripts/generate_proof_evidence_contract.py",
            "scripts/generate_proof_invariant_table.py",
            "scripts/build_regular_options_fresh_evidence_loop.py",
            "scripts/log_scan_picks.py",
        ),
        "primary_artifacts": (
            "data/contracts/proof-evidence-contract.json",
            "src/lib/generated/proofEvidenceContract.ts",
            "data/forward-tracking/fill_attempts.jsonl",
            "data/forward-tracking/regular_options_fresh_evidence_loop_latest.json",
        ),
        "gates": (
            "Production proof requires fresh live scanner exact-contract evidence and verified lineage.",
            "Exact realized P&L requires trusted exit evidence.",
            "Broker paper fills and research/backfill rows do not become production proof.",
            "Fresh evidence loop must reconcile candidate, fill attempt, tracked link, and exact realized P&L.",
        ),
        "failure_mode": "A row can look profitable while still being proof-ineligible or paper-only.",
    },
    {
        "id": "profitability_path",
        "label": "Profitability Path",
        "question": "Is a lane profitable enough to deserve more than diagnostics?",
        "plain_english": "This path prices selected candidates and converts broad scanner enthusiasm into lane-level evidence.",
        "owner_docs": (
            "docs/missed-regular-picks-outcome-audit.md",
            "docs/missed-regular-picks-failure-modes.md",
            "docs/missed-regular-picks-filter-matrix.md",
            "docs/regular-options-operating-scorecard.md",
        ),
        "owner_scripts": (
            "scripts/audit_missed_regular_picks_outcomes.py",
            "scripts/analyze_missed_regular_picks_failure_modes.py",
            "scripts/analyze_missed_regular_picks_filter_matrix.py",
            "scripts/build_regular_profitability_operating_scorecard.py",
        ),
        "primary_artifacts": (
            "data/forward-tracking/missed_regular_picks_outcome_latest.json",
            "data/forward-tracking/missed_regular_picks_failure_modes_latest.json",
            "data/forward-tracking/missed_regular_picks_filter_matrix_latest.json",
            "data/profitability-lab/regular-options-operating-scorecard/latest.json",
        ),
        "gates": (
            "Lanes need enough exact priced rows, positive average net P&L, and profit factor.",
            "Unprofitable or undersampled lanes remain diagnostic-only.",
            "Profitable historical pockets start as paper/probation, not live release.",
            "Counterfactual filters must be entry-time-only and survive later-date/OOS checks.",
        ),
        "failure_mode": "Clean data can still prove the strategy is losing.",
    },
    {
        "id": "promotion_path",
        "label": "Promotion Path",
        "question": "What is each lane allowed to do today?",
        "plain_english": "This path turns profitability, walk-forward, fresh-paper, risk, and circuit-breaker evidence into lane permissions.",
        "owner_docs": (
            "docs/lane-promotion-state.md",
            "docs/current-policy-circuit-breaker.md",
            "docs/current-policy-entry-filter-walkforward.md",
            "docs/current-policy-entry-filter-paper-monitor.md",
        ),
        "owner_scripts": (
            "scripts/lane_promotion_state.py",
            "scripts/build_current_policy_circuit_breaker.py",
            "scripts/validate_current_policy_entry_filter_walkforward.py",
            "scripts/monitor_current_policy_entry_filter_paper.py",
        ),
        "primary_artifacts": (
            "data/forward-tracking/lane_promotion_state_latest.json",
            "data/forward-tracking/current_policy_circuit_breaker_latest.json",
            "data/forward-tracking/current_policy_entry_filter_walkforward_latest.json",
            "data/forward-tracking/current_policy_entry_filter_paper_monitor_latest.json",
        ),
        "gates": (
            "Lanes move diagnostic -> paper_probation -> live_validation -> auto_track.",
            "Live validation needs clean lane profitability, walk-forward depth, fresh exact paper rows, and clean current risk.",
            "Auto-track remains reserved for explicit later release review.",
            "Recent broken cohorts route to paper validation only.",
        ),
        "failure_mode": "A historically promising lane can be promoted too early without fresh forward/risk evidence.",
    },
    {
        "id": "operator_path",
        "label": "Operator Path",
        "question": "What should a human or future agent look at next?",
        "plain_english": "This path turns many artifacts into one current readback and a small set of next actions.",
        "owner_docs": (
            "docs/project-operating-map.md",
            "docs/project-operator-gateboard.md",
            "docs/regular-options-operator-workflow.md",
            "docs/NEXT_STEPS.md",
        ),
        "owner_scripts": (
            "scripts/generate_project_pathway_registry.py",
            "scripts/build_project_operator_gateboard.py",
            "scripts/build_regular_profitability_operating_scorecard.py",
        ),
        "primary_artifacts": (
            "data/contracts/project-pathway-registry.json",
            "data/forward-tracking/project_operator_gateboard_latest.json",
            "docs/project-operator-gateboard.md",
            "docs/regular-options-operating-scorecard.md",
        ),
        "gates": (
            "Gateboard is read-only and summarizes current state.",
            "Operator next actions must preserve proof bars and lane promotion gates.",
            "Docs index and worklog must point future agents to the right pathway owner.",
        ),
        "failure_mode": "The project becomes technically correct but impossible to hold in your head.",
    },
)

EDGES = (
    ("data_path", "candidate_path", "trusted data enables candidate queueing"),
    ("candidate_path", "evidence_path", "candidate rows need fresh/proof evidence"),
    ("evidence_path", "profitability_path", "exact evidence prices outcomes"),
    ("profitability_path", "promotion_path", "lane economics feed permissions"),
    ("promotion_path", "operator_path", "permissions become current operator state"),
    ("operator_path", "data_path", "operator actions may trigger data repair or refresh"),
)


def build_registry() -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "version": 1,
        "generated_by": GENERATOR,
        "runtime_use": False,
        "purpose": "Human-readable operating model for the active options project pathways.",
        "non_goals": [
            "change scanner policy",
            "create trades",
            "submit broker orders",
            "lower proof bars",
            "replace source owner docs",
            "govern volatile research outputs",
        ],
        "pathways": list(PATHWAYS),
        "edges": [
            {"from": source, "to": target, "label": label}
            for source, target, label in EDGES
        ],
        "visual_model": {
            "short_form": [
                "Data first.",
                "Candidates second.",
                "Evidence third.",
                "Profitability fourth.",
                "Promotion fifth.",
                "Operator action last.",
            ],
            "active_scope": "regular supervised options plus separate AI commodity proof lane",
        },
    }


def _mermaid_flow(registry: dict[str, Any]) -> str:
    labels = {row["id"]: row["label"] for row in registry["pathways"]}
    lines = ["flowchart TB"]
    for row in registry["pathways"]:
        lines.append(f'  {row["id"]}["{row["label"]}<br/>{row["question"]}"]')
    for edge in registry["edges"]:
        lines.append(f'  {edge["from"]} -->|"{edge["label"]}"| {edge["to"]}')
    return "\n".join(lines)


def render_markdown(registry: dict[str, Any]) -> str:
    lines = [
        "# Project Operating Map",
        "",
        f"Generated by `{GENERATOR}`. Do not hand-edit this file.",
        "",
        "This is the visual operating model for the active options project. It organizes the repo by pathway instead of by script name.",
        "",
        "It is a navigation and explanation layer only. It does not create trades, submit broker orders, lower proof bars, change scanner policy, or replace the owner docs listed below.",
        "",
        "## One-Screen Model",
        "",
        "```mermaid",
        _mermaid_flow(registry),
        "```",
        "",
        "## Short Form",
        "",
    ]
    for item in registry["visual_model"]["short_form"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Pathways",
            "",
            "| Pathway | Question | Main Owners | Main Artifacts | Failure Mode |",
            "|---|---|---|---|---|",
        ]
    )
    for row in registry["pathways"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row["label"]),
                    _fmt(row["question"]),
                    _fmt(", ".join(row["owner_scripts"])),
                    _fmt(", ".join(row["primary_artifacts"])),
                    _fmt(row["failure_mode"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## What To Read When Confused",
            "",
        ]
    )
    for row in registry["pathways"]:
        lines.append(f"### {row['label']}")
        lines.append("")
        lines.append(f"- Plain English: {row['plain_english']}")
        lines.append(f"- Question: {row['question']}")
        lines.append(f"- Owner docs: `{json.dumps(list(row['owner_docs']))}`")
        lines.append(f"- Owner scripts: `{json.dumps(list(row['owner_scripts']))}`")
        lines.append(f"- Primary artifacts: `{json.dumps(list(row['primary_artifacts']))}`")
        lines.append("- Gates:")
        for gate in row["gates"]:
            lines.append(f"  - {gate}")
        lines.append("")
    lines.extend(
        [
            "## Mental Check",
            "",
            "When the project feels tangled, translate any artifact into one of these questions:",
            "",
            "1. Is the data trustworthy?",
            "2. Did the scanner produce candidates?",
            "3. Is the evidence proof-grade or paper/diagnostic?",
            "4. Is the lane profitable?",
            "5. What is the lane allowed to do?",
            "6. What should the operator do next?",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_json(registry: dict[str, Any]) -> str:
    return json.dumps(registry, indent=2, sort_keys=True) + "\n"


def write_outputs(registry: dict[str, Any]) -> None:
    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(render_json(registry), encoding="utf8")
    MD_OUTPUT_PATH.write_text(render_markdown(registry), encoding="utf8")


def check_outputs(registry: dict[str, Any]) -> bool:
    checks = [
        (JSON_OUTPUT_PATH, render_json(registry)),
        (MD_OUTPUT_PATH, render_markdown(registry)),
    ]
    ok = True
    for path, expected in checks:
        if not path.exists():
            print(f"{path.relative_to(ROOT)} is missing; run {GENERATOR}.", file=sys.stderr)
            ok = False
            continue
        if path.read_text(encoding="utf8") != expected:
            print(f"{path.relative_to(ROOT)} is out of date; run {GENERATOR}.", file=sys.stderr)
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the project pathway registry and operating map.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    registry = build_registry()
    if args.check:
        return 0 if check_outputs(registry) else 1
    write_outputs(registry)
    if args.json:
        print(render_json(registry), end="")
    else:
        print(f"Wrote {JSON_OUTPUT_PATH.relative_to(ROOT)}")
        print(f"Wrote {MD_OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
