from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "agent-memory-graph.json"
MD_OUTPUT_PATH = ROOT / "docs" / "agent-memory-graph.md"

NON_GOALS = (
    "Does not replace generated route inventory.",
    "Does not replace route mutation inventory.",
    "Does not replace storage ownership maps.",
    "Does not replace proof/source contracts.",
    "Does not replace the remediation loop handoff ledger.",
    "Does not replace generated artifact governance.",
    "Does not replace the final remediation closure pack.",
    "Does not define runtime behavior, route payloads, auth, scanner policy, proof semantics, or DB schema.",
)

NODES: tuple[dict[str, str], ...] = (
    {
        "id": "readme",
        "kind": "doc",
        "path": "README.md",
        "label": "README",
        "read_when": "Starting a repo session.",
        "owner_summary": "Top-level product and runtime summary.",
    },
    {
        "id": "agents_guide",
        "kind": "doc",
        "path": "AGENTS.md",
        "label": "Agent guide",
        "read_when": "Before code or docs edits.",
        "owner_summary": "Repo-specific agent startup, evidence rules, and docs placement.",
    },
    {
        "id": "docs_index",
        "kind": "doc",
        "path": "docs/index.md",
        "label": "Docs index",
        "read_when": "Choosing the living reading order.",
        "owner_summary": "Living docs map and reading order.",
    },
    {
        "id": "project_context",
        "kind": "doc",
        "path": "docs/PROJECT_CONTEXT.md",
        "label": "Project context",
        "read_when": "Checking product scope, lane boundaries, and proof posture.",
        "owner_summary": "Current product scope, lane boundaries, and architecture summary.",
    },
    {
        "id": "next_steps",
        "kind": "doc",
        "path": "docs/NEXT_STEPS.md",
        "label": "Next steps",
        "read_when": "Checking active blockers and current commands.",
        "owner_summary": "Active blockers, commands, and next actions.",
    },
    {
        "id": "profitability_paper_gate_goal",
        "kind": "doc",
        "path": "docs/autoresearch/profitability-paper-gate-goal.md",
        "label": "Profitability paper-gate goal",
        "read_when": "Running the paper-gate sprint backlog end to end.",
        "owner_summary": "Six-sprint goal prompt for the profitability paper-gate operator workflow.",
    },
    {
        "id": "regular_options_operating_scorecard_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-operating-scorecard.md",
        "label": "Regular options operating scorecard",
        "read_when": "Answering whether profitability progress is visible and whether proof remains blocked.",
        "owner_summary": "Generated active options scorecard with paper-gate readiness counts.",
    },
    {
        "id": "regular_options_operating_scorecard_generator",
        "kind": "script",
        "path": "scripts/build_regular_profitability_operating_scorecard.py",
        "label": "Operating scorecard generator",
        "read_when": "Regenerating or changing the active options scorecard.",
        "owner_summary": "Builds the active operating scorecard from profitability, paper-gate, and risk readbacks.",
    },
    {
        "id": "regular_options_profit_capture_queue_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-profit-capture-queue.md",
        "label": "Regular options profit-capture queue",
        "read_when": "Finding Tier A, Tier B, fresh-match, blocked, quarantine, and repair queue rows.",
        "owner_summary": "Generated paper/research visibility layer for profitable regular-options evidence.",
    },
    {
        "id": "regular_options_profit_capture_queue_generator",
        "kind": "script",
        "path": "scripts/build_regular_options_profit_capture_queue.py",
        "label": "Profit-capture queue generator",
        "read_when": "Regenerating the regular-options profit-capture queue.",
        "owner_summary": "Builds the profit-capture queue without lowering scanner proof bars.",
    },
    {
        "id": "regular_options_paper_shortlist_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-paper-shortlist.md",
        "label": "Regular options paper shortlist",
        "read_when": "Checking fresh executable Tier A paper-review eligibility.",
        "owner_summary": "Generated paper-review release gate for fresh executable Tier A lane matches.",
    },
    {
        "id": "regular_options_paper_shortlist_generator",
        "kind": "script",
        "path": "scripts/build_regular_options_paper_shortlist.py",
        "label": "Paper shortlist generator",
        "read_when": "Regenerating the paper-review release gate.",
        "owner_summary": "Builds the strict fail-closed paper shortlist readback.",
    },
    {
        "id": "regular_options_fresh_evidence_loop_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-fresh-evidence-loop.md",
        "label": "Regular options fresh evidence loop",
        "read_when": "Checking pending validation, fill-attempt evidence, tracked linkage, and exact realized P&L readiness.",
        "owner_summary": "Generated fresh exact-evidence loop readback for paper-gate candidates.",
    },
    {
        "id": "regular_options_fresh_evidence_loop_generator",
        "kind": "script",
        "path": "scripts/build_regular_options_fresh_evidence_loop.py",
        "label": "Fresh evidence loop generator",
        "read_when": "Regenerating fresh validation and exact realized P&L readbacks.",
        "owner_summary": "Builds the fresh evidence loop without changing scanner or broker behavior.",
    },
    {
        "id": "current_policy_circuit_breaker_doc",
        "kind": "generated_artifact",
        "path": "docs/current-policy-circuit-breaker.md",
        "label": "Current-policy circuit breaker",
        "read_when": "Checking paper-validation-only lane routes after recent cohort breaks.",
        "owner_summary": "Generated readback that routes affected current-policy lanes to paper validation only.",
    },
    {
        "id": "current_policy_circuit_breaker_generator",
        "kind": "script",
        "path": "scripts/build_current_policy_circuit_breaker.py",
        "label": "Current-policy circuit breaker generator",
        "read_when": "Regenerating recent-cohort paper-validation routes.",
        "owner_summary": "Builds the fail-closed current-policy circuit breaker.",
    },
    {
        "id": "regular_options_operator_workflow_doc",
        "kind": "doc",
        "path": "docs/regular-options-operator-workflow.md",
        "label": "Regular options operator workflow",
        "read_when": "Checking scanner evidence drawer and local operator-session workflow semantics.",
        "owner_summary": "Operator workflow for viewing paper-gate state without implying trade recommendations.",
    },
    {
        "id": "regular_options_repair_attempts_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-repair-attempts.md",
        "label": "Regular options repair attempts",
        "read_when": "Checking keyed exact-repair memory and lookahead/current-source-exhausted outcomes.",
        "owner_summary": "Generated repair-attempt memory readback for exact missing contract/date provider checks.",
    },
    {
        "id": "regular_options_repair_attempts_generator",
        "kind": "script",
        "path": "scripts/build_regular_options_repair_attempt_readback.py",
        "label": "Repair-attempt readback generator",
        "read_when": "Regenerating keyed repair-attempt memory from importer summaries.",
        "owner_summary": "Builds conservative repair-attempt memory without turning lookahead or unsafe aggregate rows into proof.",
    },
    {
        "id": "regular_options_repair_burndown_doc",
        "kind": "generated_artifact",
        "path": "docs/regular-options-repair-burndown.md",
        "label": "Regular options repair burn-down",
        "read_when": "Choosing active exact repair targets and avoiding repeated exhausted provider loops.",
        "owner_summary": "Generated exact repair burn-down that separates active, source-replay, diagnostic, and exhausted targets.",
    },
    {
        "id": "regular_options_repair_burndown_generator",
        "kind": "script",
        "path": "scripts/build_regular_options_repair_burndown.py",
        "label": "Repair burn-down generator",
        "read_when": "Regenerating the exact repair burn-down.",
        "owner_summary": "Builds the fail-closed exact repair burn-down from the queue and repair-attempt memory.",
    },
    {
        "id": "decisions",
        "kind": "doc",
        "path": "docs/DECISIONS.md",
        "label": "Decisions",
        "read_when": "Checking durable decisions.",
        "owner_summary": "Durable product and technical decisions.",
    },
    {
        "id": "worklog",
        "kind": "doc",
        "path": "docs/WORKLOG.md",
        "label": "Worklog",
        "read_when": "Checking dated local work evidence.",
        "owner_summary": "Dated summaries of meaningful local work.",
    },
    {
        "id": "architecture_overview",
        "kind": "doc",
        "path": "docs/architecture-overview.md",
        "label": "Architecture overview",
        "read_when": "Understanding the current system map.",
        "owner_summary": "Current system map and subsystem ownership.",
    },
    {
        "id": "architecture_best_practices",
        "kind": "doc",
        "path": "docs/architecture-best-practices.md",
        "label": "Architecture best practices",
        "read_when": "Judging whether a remediation improves architecture readability.",
        "owner_summary": "Target architecture and readability rubric.",
    },
    {
        "id": "living_docs_hygiene",
        "kind": "doc",
        "path": "docs/living-docs-hygiene.md",
        "label": "Living docs hygiene",
        "read_when": "Touching living docs, generated artifacts, or source-of-truth documentation.",
        "owner_summary": "Living-doc ownership, generated-artifact, and source-of-truth hygiene rules.",
    },
    {
        "id": "architecture_audit",
        "kind": "doc",
        "path": "docs/architecture-audit.md",
        "label": "Architecture audit",
        "read_when": "Finding current architecture risks and monoliths.",
        "owner_summary": "Live audit of confusing surfaces and remaining monoliths.",
    },
    {
        "id": "runtime_request_flow",
        "kind": "doc",
        "path": "docs/runtime-request-flow.md",
        "label": "Runtime request flow",
        "read_when": "Following browser to backend request flow.",
        "owner_summary": "Narrative request-flow map.",
    },
    {
        "id": "api_and_storage",
        "kind": "doc",
        "path": "docs/api-and-storage.md",
        "label": "API and storage",
        "read_when": "Touching routes, auth, storage, or backend-only endpoints.",
        "owner_summary": "Active route groups, auth boundaries, and storage ownership.",
    },
    {
        "id": "route_parity_doc",
        "kind": "generated_artifact",
        "path": "docs/route-parity.md",
        "label": "Route parity",
        "read_when": "Touching mounted browser routes or backend route parity.",
        "owner_summary": "Generated browser route to Next route to FastAPI map.",
    },
    {
        "id": "route_mutation_inventory_json",
        "kind": "generated_artifact",
        "path": "data/contracts/route-mutation-inventory.json",
        "label": "Route mutation inventory JSON",
        "read_when": "Machine-reading route auth, mutation, lifecycle, and store inventory.",
        "owner_summary": "Generated machine-readable route and mutation inventory.",
    },
    {
        "id": "route_parity_generator",
        "kind": "script",
        "path": "scripts/generate_route_parity.py",
        "label": "Route parity generator",
        "read_when": "Regenerating or checking route parity.",
        "owner_summary": "Generates docs/route-parity.md and route-mutation-inventory.json.",
    },
    {
        "id": "backend_route_ownership_map_doc",
        "kind": "generated_artifact",
        "path": "docs/backend-route-ownership-map.md",
        "label": "Backend route ownership map",
        "read_when": "Touching FastAPI route adapters, extracted routers, backend-only routes, or service delegation.",
        "owner_summary": "Generated FastAPI adapter ownership and backend route delegation map.",
    },
    {
        "id": "backend_route_ownership_map_json",
        "kind": "generated_artifact",
        "path": "data/contracts/backend-route-ownership-map.json",
        "label": "Backend route ownership JSON",
        "read_when": "Machine-reading FastAPI adapter ownership and backend route surface classifications.",
        "owner_summary": "Generated machine-readable backend route ownership map.",
    },
    {
        "id": "backend_route_ownership_map_generator",
        "kind": "script",
        "path": "scripts/generate_backend_route_ownership_map.py",
        "label": "Backend route ownership generator",
        "read_when": "Regenerating or checking backend route ownership artifacts.",
        "owner_summary": "Generates checked backend route ownership JSON and Markdown.",
    },
    {
        "id": "storage_ownership_map_json",
        "kind": "generated_artifact",
        "path": "data/contracts/storage-ownership-map.json",
        "label": "Storage ownership map JSON",
        "read_when": "Machine-reading route, repository, local DB, artifact, and virtual store ownership.",
        "owner_summary": "Generated machine-readable storage ownership map.",
    },
    {
        "id": "storage_ownership_map_doc",
        "kind": "generated_artifact",
        "path": "docs/storage-ownership-map.md",
        "label": "Storage ownership map",
        "read_when": "Finding storage owners, route usage, local DB roles, and repository-store boundaries.",
        "owner_summary": "Generated human-readable storage ownership map.",
    },
    {
        "id": "route_lifecycle_doc",
        "kind": "doc",
        "path": "docs/route-lifecycle-contracts.md",
        "label": "Route lifecycle contracts",
        "read_when": "Touching generic Next route lifecycle headers.",
        "owner_summary": "Descriptive lifecycle header contract for generic route groups.",
    },
    {
        "id": "route_lifecycle_code",
        "kind": "code",
        "path": "src/lib/route-lifecycle/routeContracts.ts",
        "label": "Route lifecycle registry",
        "read_when": "Changing generic route lifecycle headers.",
        "owner_summary": "Typed route lifecycle registry and helper.",
    },
    {
        "id": "app_api_routes",
        "kind": "code",
        "path": "src/app/api",
        "label": "Next API routes",
        "read_when": "Touching browser-facing API routes.",
        "owner_summary": "Same-origin Next route handlers.",
    },
    {
        "id": "backend_helpers",
        "kind": "code",
        "path": "src/lib/backend",
        "label": "Backend helpers",
        "read_when": "Touching Next-to-FastAPI transport helpers.",
        "owner_summary": "Backend helper layer used by Next route handlers.",
    },
    {
        "id": "fastapi_main",
        "kind": "code",
        "path": "python-backend/main.py",
        "label": "FastAPI composition root",
        "read_when": "Touching backend route composition.",
        "owner_summary": "FastAPI app wiring and remaining inline route adapters.",
    },
    {
        "id": "operator_auth",
        "kind": "code",
        "path": "src/lib/operator-auth.ts",
        "label": "Local operator auth",
        "read_when": "Touching browser-facing write authorization.",
        "owner_summary": "Local operator auth boundary for state-changing and tool routes.",
    },
    {
        "id": "backend_transport",
        "kind": "code",
        "path": "src/lib/backend/transport.ts",
        "label": "Backend transport",
        "read_when": "Touching Next-to-FastAPI auth or transport.",
        "owner_summary": "Backend bridge transport and optional backend API token forwarding.",
    },
    {
        "id": "proof_doc",
        "kind": "doc",
        "path": "docs/proof-evidence-contract.md",
        "label": "Proof evidence contract",
        "read_when": "Touching proof classes, evidence groups, or proof claims.",
        "owner_summary": "Semantic owner for Trading Desk proof and evidence language.",
    },
    {
        "id": "proof_contract_json",
        "kind": "contract",
        "path": "data/contracts/proof-evidence-contract.json",
        "label": "Proof contract JSON",
        "read_when": "Changing versioned proof/evidence tokens.",
        "owner_summary": "Versioned proof/evidence source contract.",
    },
    {
        "id": "proof_backend",
        "kind": "code",
        "path": "python-backend/proof_contract.py",
        "label": "Backend proof predicates",
        "read_when": "Touching backend proof classification.",
        "owner_summary": "Backend proof predicates and canonical tokens.",
    },
    {
        "id": "proof_generator",
        "kind": "script",
        "path": "scripts/generate_proof_evidence_contract.py",
        "label": "Proof contract generator",
        "read_when": "Regenerating frontend proof contract artifact.",
        "owner_summary": "Generates src/lib/generated/proofEvidenceContract.ts.",
    },
    {
        "id": "proof_generated_ts",
        "kind": "generated_artifact",
        "path": "src/lib/generated/proofEvidenceContract.ts",
        "label": "Generated frontend proof contract",
        "read_when": "Checking frontend proof policy source.",
        "owner_summary": "Generated TypeScript proof/evidence artifact.",
    },
    {
        "id": "proof_invariant_cases",
        "kind": "contract",
        "path": "data/contracts/proof-invariant-cases.json",
        "label": "Proof invariant cases",
        "read_when": "Checking backend/frontend proof invariant expectations.",
        "owner_summary": "Test-only proof invariant matrix for raw exact, production proof, Truth-grade, and realized-P&L boundaries.",
    },
    {
        "id": "proof_invariant_generator",
        "kind": "script",
        "path": "scripts/generate_proof_invariant_table.py",
        "label": "Proof invariant table generator",
        "read_when": "Regenerating the proof invariant table docs.",
        "owner_summary": "Generates the human proof invariant table from the test-only case manifest.",
    },
    {
        "id": "proof_invariant_doc",
        "kind": "generated_artifact",
        "path": "docs/proof-invariant-table.md",
        "label": "Proof invariant table",
        "read_when": "Reading proof edge cases across backend and frontend predicates.",
        "owner_summary": "Generated human-readable proof invariant matrix.",
    },
    {
        "id": "proof_frontend_facade",
        "kind": "code",
        "path": "src/lib/trading-desk/proofContract.ts",
        "label": "Frontend proof facade",
        "read_when": "Touching frontend proof constants.",
        "owner_summary": "Human TypeScript facade over the generated proof artifact.",
    },
    {
        "id": "position_evidence",
        "kind": "code",
        "path": "src/lib/trading-desk/positionEvidence.ts",
        "label": "Position evidence UI logic",
        "read_when": "Touching frontend evidence grouping.",
        "owner_summary": "Frontend evidence grouping and closed-row view predicates.",
    },
    {
        "id": "scanner_doc",
        "kind": "doc",
        "path": "docs/scanner-creation-safety-contract.md",
        "label": "Scanner creation safety contract",
        "read_when": "Touching scanner-origin creation.",
        "owner_summary": "Scanner stage map and creation safety rules.",
    },
    {
        "id": "scanner_contract_json",
        "kind": "contract",
        "path": "data/contracts/scanner-creation-safety-contract.json",
        "label": "Scanner safety JSON",
        "read_when": "Changing scanner creation safety tokens.",
        "owner_summary": "Versioned scanner creation safety source contract.",
    },
    {
        "id": "supervised_scan",
        "kind": "code",
        "path": "supervised_scan.py",
        "label": "Supervised scan engine",
        "read_when": "Touching live scan candidate generation or guardrails.",
        "owner_summary": "Regular supervised options scan logic.",
    },
    {
        "id": "replay_profit_doc",
        "kind": "doc",
        "path": "docs/replay-profit-contract.md",
        "label": "Replay profit contract",
        "read_when": "Touching replay readbacks, policy, or options-profit status.",
        "owner_summary": "Replay/profit ownership map.",
    },
    {
        "id": "replay_profit_service",
        "kind": "code",
        "path": "python-backend/replay_profit_service.py",
        "label": "Replay profit service",
        "read_when": "Touching replay/profit readback assembly.",
        "owner_summary": "Decorator-free replay/profit readback service.",
    },
    {
        "id": "wfo_optimizer",
        "kind": "code",
        "path": "wfo_optimizer.py",
        "label": "WFO optimizer",
        "read_when": "Touching replay or optimization engine behavior.",
        "owner_summary": "Large replay and optimization engine.",
    },
    {
        "id": "metric_truth_audit",
        "kind": "code",
        "path": "metric_truth_audit.py",
        "label": "Metric truth audit",
        "read_when": "Touching metric truth diagnostics.",
        "owner_summary": "Metric truth and calibration audit logic.",
    },
    {
        "id": "options_profit_gate",
        "kind": "code",
        "path": "options_profit_gate.py",
        "label": "Options profit gate",
        "read_when": "Touching profit readiness gates.",
        "owner_summary": "Production readiness and proof-grade profit gates.",
    },
    {
        "id": "options_profit_flywheel",
        "kind": "code",
        "path": "options_profit_flywheel.py",
        "label": "Options profit flywheel",
        "read_when": "Touching profit-cycle state.",
        "owner_summary": "Options profit-cycle orchestration state.",
    },
    {
        "id": "repository_doc",
        "kind": "doc",
        "path": "docs/repository-contract.md",
        "label": "Repository contract",
        "read_when": "Touching Trading Desk repository ownership.",
        "owner_summary": "Repository ownership map and structural interface contract.",
    },
    {
        "id": "record_parity_doc",
        "kind": "doc",
        "path": "docs/trading-desk-record-parity.md",
        "label": "Trading Desk record parity",
        "read_when": "Touching tracked versus suggested row parity.",
        "owner_summary": "Tracked-position versus suggested-trade parity and separation.",
    },
    {
        "id": "repository_migrations_doc",
        "kind": "doc",
        "path": "docs/repository-migrations.md",
        "label": "Repository migrations",
        "read_when": "Touching repository schema evolution.",
        "owner_summary": "Versioned repository migration manifest and ledger contract.",
    },
    {
        "id": "repository_constraints_doc",
        "kind": "doc",
        "path": "docs/repository-constraints.md",
        "label": "Repository constraints",
        "read_when": "Touching DB/API/proof invariant ownership.",
        "owner_summary": "DB-enforced, API-enforced, and proof-owned invariant boundaries.",
    },
    {
        "id": "repository_indexes_doc",
        "kind": "doc",
        "path": "docs/repository-indexes.md",
        "label": "Repository indexes",
        "read_when": "Touching repository read-path indexes.",
        "owner_summary": "Current and deferred repository index ownership.",
    },
    {
        "id": "local_db_doc",
        "kind": "doc",
        "path": "docs/local-db-hardening.md",
        "label": "Local DB hardening",
        "read_when": "Touching local SQLite stores or backups.",
        "owner_summary": "Local SQLite role and read-only audit contract.",
    },
    {
        "id": "repository_contracts_code",
        "kind": "code",
        "path": "python-backend/repository_contracts.py",
        "label": "Repository structural Protocols",
        "read_when": "Touching repository interface readability.",
        "owner_summary": "Structural Protocols for repository capabilities.",
    },
    {
        "id": "positions_repository",
        "kind": "code",
        "path": "python-backend/positions_repository.py",
        "label": "Positions repository",
        "read_when": "Touching tracked-position persistence.",
        "owner_summary": "Postgres-backed tracked-position repository.",
    },
    {
        "id": "suggested_trades_repository",
        "kind": "code",
        "path": "python-backend/suggested_trades_repository.py",
        "label": "Suggested trades repository",
        "read_when": "Touching suggested-trade persistence.",
        "owner_summary": "SQLite-backed suggested-trade repository.",
    },
    {
        "id": "local_db_manifest",
        "kind": "code",
        "path": "python-backend/local_db_hardening.py",
        "label": "Local DB role manifest",
        "read_when": "Touching local DB audit classifications.",
        "owner_summary": "Local SQLite role manifest.",
    },
    {
        "id": "repository_migrations_code",
        "kind": "code",
        "path": "python-backend/repository_migrations.py",
        "label": "Repository migrations manifest",
        "read_when": "Touching repository migration definitions.",
        "owner_summary": "Versioned repository migration manifest and ledger helpers.",
    },
    {
        "id": "repository_constraints_code",
        "kind": "code",
        "path": "python-backend/repository_constraints.py",
        "label": "Repository constraints manifest",
        "read_when": "Touching repository invariant ownership.",
        "owner_summary": "Repository constraint ownership manifest.",
    },
    {
        "id": "repository_indexes_code",
        "kind": "code",
        "path": "python-backend/repository_indexes.py",
        "label": "Repository indexes manifest",
        "read_when": "Touching index ownership.",
        "owner_summary": "Repository index ownership manifest.",
    },
    {
        "id": "storage_ownership_map_generator",
        "kind": "script",
        "path": "scripts/generate_storage_ownership_map.py",
        "label": "Storage ownership map generator",
        "read_when": "Regenerating or checking storage ownership map artifacts.",
        "owner_summary": "Generates storage ownership JSON and Markdown from route and repository manifests.",
    },
    {
        "id": "api_models_doc",
        "kind": "doc",
        "path": "docs/trading-desk-api-models.md",
        "label": "Trading Desk API models",
        "read_when": "Touching backend mutation body adapters.",
        "owner_summary": "Narrow Pydantic model boundary for Trading Desk mutation bodies.",
    },
    {
        "id": "api_models_code",
        "kind": "code",
        "path": "python-backend/trading_desk_api_models.py",
        "label": "Trading Desk API model code",
        "read_when": "Touching Pydantic adapters or envelope guards.",
        "owner_summary": "Pydantic mutation body adapters and envelope drift guards.",
    },
    {
        "id": "ts_api_contracts_doc",
        "kind": "doc",
        "path": "docs/typescript-api-contracts.md",
        "label": "TypeScript API contracts",
        "read_when": "Touching Trading Desk TypeScript request/response shapes.",
        "owner_summary": "Manual TypeScript API contract boundary.",
    },
    {
        "id": "ts_api_contracts_code",
        "kind": "code",
        "path": "src/lib/trading-desk/apiContracts.ts",
        "label": "TypeScript API contract code",
        "read_when": "Touching Trading Desk request/response envelope types.",
        "owner_summary": "Named Trading Desk TypeScript request and response contracts.",
    },
    {
        "id": "api_response_validation",
        "kind": "code",
        "path": "src/lib/trading-desk/apiResponseValidation.ts",
        "label": "Trading Desk response validation",
        "read_when": "Touching Next-boundary Trading Desk response validation.",
        "owner_summary": "Shallow Trading Desk response-envelope validation.",
    },
    {
        "id": "schema_bridge_doc",
        "kind": "generated_artifact",
        "path": "docs/trading-desk-schema-bridge.md",
        "label": "Trading Desk schema bridge docs",
        "read_when": "Touching Trading Desk schema bridge documentation.",
        "owner_summary": "Generated Trading Desk schema bridge documentation.",
    },
    {
        "id": "schema_bridge_json",
        "kind": "generated_artifact",
        "path": "data/contracts/trading-desk-api-schema-bridge.json",
        "label": "Trading Desk schema bridge JSON",
        "read_when": "Touching Trading Desk schema bridge artifact.",
        "owner_summary": "Generated Trading Desk schema bridge JSON artifact.",
    },
    {
        "id": "schema_bridge_generator",
        "kind": "script",
        "path": "scripts/generate_trading_desk_schema_bridge.py",
        "label": "Trading Desk schema bridge generator",
        "read_when": "Regenerating Trading Desk schema bridge artifacts.",
        "owner_summary": "Generates Trading Desk schema bridge JSON and Markdown.",
    },
    {
        "id": "store_ownership_code",
        "kind": "code",
        "path": "src/lib/trading-desk/storeOwnership.ts",
        "label": "Trading Desk store ownership",
        "read_when": "Touching Trading Desk route/store/lifecycle headers.",
        "owner_summary": "Trading Desk route lifecycle and store ownership registry.",
    },
    {
        "id": "strategy_replay_intent",
        "kind": "code",
        "path": "src/lib/strategy-lab/replayIntent.ts",
        "label": "Strategy Lab route intent",
        "read_when": "Touching Strategy Lab route lifecycle or mutation intent.",
        "owner_summary": "Strategy Lab route ownership and mutation-intent registry.",
    },
    {
        "id": "app_shell",
        "kind": "code",
        "path": "src/components/layout/AppShell.tsx",
        "label": "App shell",
        "read_when": "Touching main app shell or tab orchestration.",
        "owner_summary": "Main client shell and view switching.",
    },
    {
        "id": "navigation_tabs",
        "kind": "code",
        "path": "src/lib/navigation/tabs.ts",
        "label": "Main navigation tabs",
        "read_when": "Touching main app tab IDs or nav copy.",
        "owner_summary": "Typed main app tab catalog.",
    },
    {
        "id": "predictions_view",
        "kind": "code",
        "path": "src/components/predictions/PredictionsView.tsx",
        "label": "Trading Desk coordinator",
        "read_when": "Touching Trading Desk tab orchestration.",
        "owner_summary": "Trading Desk client coordinator.",
    },
    {
        "id": "trading_desk_tabs",
        "kind": "code",
        "path": "src/components/predictions/tradingDeskTabs.ts",
        "label": "Trading Desk tab IDs",
        "read_when": "Touching Trading Desk visible or active tab IDs.",
        "owner_summary": "Typed Trading Desk active and visible tab catalogs.",
    },
    {
        "id": "tracked_positions_tab",
        "kind": "code",
        "path": "src/components/predictions/TrackedPositionsTab.tsx",
        "label": "Tracked positions tab",
        "read_when": "Touching tracked-position table UI.",
        "owner_summary": "Tracked-position table surface.",
    },
    {
        "id": "suggested_trades_tab",
        "kind": "code",
        "path": "src/components/predictions/SuggestedTradesTab.tsx",
        "label": "Suggested trades tab",
        "read_when": "Touching suggested-trade table UI.",
        "owner_summary": "Suggested-trade table surface.",
    },
    {
        "id": "scanner_tab",
        "kind": "code",
        "path": "src/components/predictions/ScannerTab.tsx",
        "label": "Scanner tab",
        "read_when": "Touching archive-gated live scanner UI.",
        "owner_summary": "Scanner UI coordinator and table row/mobile contracts.",
    },
    {
        "id": "scanner_evidence_panel",
        "kind": "code",
        "path": "src/components/predictions/ScannerEvidencePanel.tsx",
        "label": "Scanner evidence panel",
        "read_when": "Touching scanner evidence/truth/guardrail display.",
        "owner_summary": "Scanner evidence and guardrail display component.",
    },
    {
        "id": "scanner_record_form",
        "kind": "code",
        "path": "src/components/predictions/ScannerPickRecordForm.tsx",
        "label": "Scanner record form",
        "read_when": "Touching scanner selected-pick record UI.",
        "owner_summary": "Selected-pick record form component.",
    },
    {
        "id": "fintable",
        "kind": "code",
        "path": "src/components/ui/FinTable.tsx",
        "label": "FinTable",
        "read_when": "Touching shared dense table rendering.",
        "owner_summary": "Shared table with explicit mobile-card contracts.",
    },
    {
        "id": "strategy_view",
        "kind": "code",
        "path": "src/components/strategy/StrategyView.tsx",
        "label": "Strategy Lab coordinator",
        "read_when": "Touching Strategy Lab client orchestration.",
        "owner_summary": "Strategy Lab client coordinator.",
    },
    {
        "id": "brain_tab",
        "kind": "code",
        "path": "src/components/strategy/BrainTab.tsx",
        "label": "Brain tab",
        "read_when": "Touching strategy profile editing.",
        "owner_summary": "Strategy profile and changelog surface.",
    },
    {
        "id": "optimizer_tab",
        "kind": "code",
        "path": "src/components/strategy/OptimizerTab.tsx",
        "label": "Optimizer tab",
        "read_when": "Touching replay/optimizer UI.",
        "owner_summary": "Replay and optimizer result surface.",
    },
    {
        "id": "ai_commodity_runner",
        "kind": "script",
        "path": "scripts/run_ai_commodity_opra_progress.py",
        "label": "AI commodity OPRA progress runner",
        "read_when": "Touching AI commodity proof lane.",
        "owner_summary": "Separate non-browser AI commodity proof-lane orchestrator.",
    },
    {
        "id": "ai_commodity_latest",
        "kind": "generated_artifact",
        "path": "data/ai-commodity-infra/progress/latest.md",
        "label": "AI commodity latest progress",
        "read_when": "Checking latest AI commodity proof state.",
        "owner_summary": "Generated AI commodity proof-lane progress readback.",
    },
    {
        "id": "ai_commodity_isolation_doc",
        "kind": "generated_artifact",
        "path": "docs/ai-commodity-isolation.md",
        "label": "AI commodity isolation",
        "read_when": "Checking AI commodity browser, scanner, proof-source, tool, and storage boundaries.",
        "owner_summary": "Generated AI commodity non-browser proof-lane isolation map.",
    },
    {
        "id": "ai_commodity_isolation_json",
        "kind": "generated_artifact",
        "path": "data/contracts/ai-commodity-isolation.json",
        "label": "AI commodity isolation JSON",
        "read_when": "Machine-reading AI commodity isolation guard results.",
        "owner_summary": "Generated machine-readable AI commodity isolation contract.",
    },
    {
        "id": "ai_commodity_isolation_generator",
        "kind": "script",
        "path": "scripts/generate_ai_commodity_isolation.py",
        "label": "AI commodity isolation generator",
        "read_when": "Regenerating or checking AI commodity isolation artifacts.",
        "owner_summary": "Generates checked AI commodity isolation JSON and Markdown.",
    },
    {
        "id": "remediation_loop_map_generator",
        "kind": "script",
        "path": "scripts/generate_remediation_loop_map.py",
        "label": "Remediation loop map generator",
        "read_when": "Regenerating or checking the 44-point remediation handoff ledger.",
        "owner_summary": "Generates checked remediation loop JSON and Markdown.",
    },
    {
        "id": "remediation_loop_map_json",
        "kind": "generated_artifact",
        "path": "data/contracts/remediation-loop-map.json",
        "label": "Remediation loop map JSON",
        "read_when": "Machine-reading 44-point remediation status, owner artifacts, checks, and evidence anchors.",
        "owner_summary": "Generated machine-readable remediation loop handoff ledger.",
    },
    {
        "id": "remediation_loop_map_doc",
        "kind": "generated_artifact",
        "path": "docs/remediation-loop-map.md",
        "label": "Remediation loop map",
        "read_when": "Continuing the 44-point remediation loop after context compaction.",
        "owner_summary": "Generated human-readable remediation loop handoff ledger.",
    },
    {
        "id": "generated_artifact_manifest",
        "kind": "script",
        "path": "scripts/generated_artifact_manifest.py",
        "label": "Generated artifact manifest",
        "read_when": "Touching generated artifact governance or living-doc generated artifact checks.",
        "owner_summary": "Shared manifest of checked generated artifacts.",
    },
    {
        "id": "generated_artifact_governance_generator",
        "kind": "script",
        "path": "scripts/generate_generated_artifact_governance.py",
        "label": "Generated artifact governance generator",
        "read_when": "Regenerating or checking generated artifact governance.",
        "owner_summary": "Generates checked generated artifact governance JSON and Markdown.",
    },
    {
        "id": "generated_artifact_governance_json",
        "kind": "generated_artifact",
        "path": "data/contracts/generated-artifact-governance.json",
        "label": "Generated artifact governance JSON",
        "read_when": "Machine-reading generated artifact trust boundaries and stale handling.",
        "owner_summary": "Generated machine-readable generated-artifact governance map.",
    },
    {
        "id": "generated_artifact_governance_doc",
        "kind": "generated_artifact",
        "path": "docs/generated-artifact-governance.md",
        "label": "Generated artifact governance",
        "read_when": "Checking generated artifact runtime posture, stale handling, owner commands, and hand-edit policy.",
        "owner_summary": "Generated generated-artifact trust-boundary and stale-handling inventory.",
    },
    {
        "id": "final_remediation_closure_pack_generator",
        "kind": "script",
        "path": "scripts/generate_final_remediation_closure_pack.py",
        "label": "Final remediation closure generator",
        "read_when": "Regenerating or checking the 44-point final closure pack.",
        "owner_summary": "Generates checked final closure JSON and Markdown.",
    },
    {
        "id": "final_remediation_closure_pack_json",
        "kind": "generated_artifact",
        "path": "data/contracts/final-remediation-closure-pack.json",
        "label": "Final remediation closure JSON",
        "read_when": "Machine-reading final remediation closure status, validation, and scope boundaries.",
        "owner_summary": "Generated machine-readable final closure pack.",
    },
    {
        "id": "final_remediation_closure_pack_doc",
        "kind": "generated_artifact",
        "path": "docs/final-remediation-closure-pack.md",
        "label": "Final remediation closure pack",
        "read_when": "Checking the final 44-point loop closure and verification ladder.",
        "owner_summary": "Generated human-readable final closure readback.",
    },
    {
        "id": "memory_graph_generator",
        "kind": "script",
        "path": "scripts/generate_agent_memory_graph.py",
        "label": "Agent memory graph generator",
        "read_when": "Regenerating this memory graph.",
        "owner_summary": "Generates checked agent orientation graph artifacts.",
    },
    {
        "id": "living_docs_hygiene_checker",
        "kind": "script",
        "path": "scripts/check_living_docs_hygiene.py",
        "label": "Living docs hygiene checker",
        "read_when": "Checking living-doc and generated-artifact hygiene.",
        "owner_summary": "Manifest-driven living-doc hygiene check.",
    },
    {
        "id": "memory_graph_json",
        "kind": "generated_artifact",
        "path": "data/contracts/agent-memory-graph.json",
        "label": "Agent memory graph JSON",
        "read_when": "Machine-readable owner and navigation graph.",
        "owner_summary": "Generated agent orientation graph JSON.",
    },
    {
        "id": "memory_graph_doc",
        "kind": "generated_artifact",
        "path": "docs/agent-memory-graph.md",
        "label": "Agent memory graph docs",
        "read_when": "Human-readable where-to-go memory graph.",
        "owner_summary": "Generated agent orientation graph Markdown.",
    },
)

EDGES: tuple[dict[str, str], ...] = (
    {"from": "docs_index", "to": "architecture_overview", "type": "read_after", "reason": "Index points agents to the current system map."},
    {"from": "docs_index", "to": "living_docs_hygiene", "type": "documents", "reason": "Index points agents to living-doc ownership and source-of-truth rules."},
    {"from": "architecture_best_practices", "to": "memory_graph_doc", "type": "documents", "reason": "Best-practices rubric names the memory graph as orientation metadata."},
    {"from": "architecture_best_practices", "to": "living_docs_hygiene", "type": "documents", "reason": "Best-practices rubric names the living-doc hygiene owner."},
    {"from": "living_docs_hygiene_checker", "to": "living_docs_hygiene", "type": "checks", "reason": "Hygiene checker guards living-doc ownership and generated-artifact rules."},
    {"from": "living_docs_hygiene_checker", "to": "docs_index", "type": "checks", "reason": "Hygiene checker verifies the living reading order links required docs and artifacts."},
    {"from": "memory_graph_generator", "to": "memory_graph_json", "type": "generates", "reason": "Generator emits machine-readable graph."},
    {"from": "memory_graph_generator", "to": "memory_graph_doc", "type": "generates", "reason": "Generator emits human-readable graph."},
    {"from": "memory_graph_doc", "to": "memory_graph_json", "type": "documents", "reason": "Markdown is rendered from the JSON graph manifest."},
    {"from": "remediation_loop_map_generator", "to": "remediation_loop_map_json", "type": "generates", "reason": "Generator emits the machine-readable remediation handoff ledger."},
    {"from": "remediation_loop_map_generator", "to": "remediation_loop_map_doc", "type": "generates", "reason": "Generator emits the human-readable remediation handoff ledger."},
    {"from": "remediation_loop_map_doc", "to": "remediation_loop_map_json", "type": "documents", "reason": "Markdown is rendered from the JSON handoff ledger."},
    {"from": "architecture_best_practices", "to": "remediation_loop_map_doc", "type": "points_to", "reason": "Best-practices rubric tells agents to read the loop ledger before continuing the 44-point goal."},
    {"from": "remediation_loop_map_doc", "to": "worklog", "type": "checks", "reason": "Completed points require dated worklog evidence anchors."},
    {"from": "remediation_loop_map_doc", "to": "architecture_best_practices", "type": "does_not_replace", "reason": "The loop ledger records status and handoff anchors but not the architecture rubric."},
    {"from": "generated_artifact_governance_generator", "to": "generated_artifact_governance_json", "type": "generates", "reason": "Generator emits the machine-readable generated-artifact governance map."},
    {"from": "generated_artifact_governance_generator", "to": "generated_artifact_governance_doc", "type": "generates", "reason": "Generator emits the human-readable generated-artifact governance map."},
    {"from": "generated_artifact_governance_doc", "to": "generated_artifact_governance_json", "type": "documents", "reason": "Markdown is rendered from the JSON generated-artifact governance map."},
    {"from": "generated_artifact_governance_json", "to": "generated_artifact_manifest", "type": "checks", "reason": "Governance consumes the shared generated artifact manifest."},
    {"from": "living_docs_hygiene_checker", "to": "generated_artifact_manifest", "type": "consumes", "reason": "Hygiene checker and governance share one generated artifact manifest."},
    {"from": "living_docs_hygiene", "to": "generated_artifact_governance_doc", "type": "points_to", "reason": "Living-doc hygiene points detailed generated-artifact trust rules to the generated governance map."},
    {"from": "final_remediation_closure_pack_generator", "to": "final_remediation_closure_pack_json", "type": "generates", "reason": "Generator emits the machine-readable final closure pack."},
    {"from": "final_remediation_closure_pack_generator", "to": "final_remediation_closure_pack_doc", "type": "generates", "reason": "Generator emits the human-readable final closure pack."},
    {"from": "final_remediation_closure_pack_doc", "to": "final_remediation_closure_pack_json", "type": "documents", "reason": "Markdown is rendered from the JSON closure pack."},
    {"from": "final_remediation_closure_pack_json", "to": "remediation_loop_map_json", "type": "checks", "reason": "Closure pack proves all 44 remediation points are completed."},
    {"from": "final_remediation_closure_pack_json", "to": "generated_artifact_governance_json", "type": "checks", "reason": "Closure pack proves generated artifacts are governed and non-runtime except the explicit generated proof artifact."},
    {"from": "final_remediation_closure_pack_json", "to": "memory_graph_json", "type": "checks", "reason": "Closure pack proves the memory graph discovers closure artifacts."},
    {"from": "ai_commodity_isolation_generator", "to": "ai_commodity_isolation_json", "type": "generates", "reason": "Generator emits the AI commodity isolation contract."},
    {"from": "ai_commodity_isolation_generator", "to": "ai_commodity_isolation_doc", "type": "generates", "reason": "Generator emits the AI commodity isolation Markdown."},
    {"from": "ai_commodity_isolation_doc", "to": "ai_commodity_isolation_json", "type": "documents", "reason": "Markdown is rendered from the machine-readable isolation contract."},
    {"from": "route_parity_generator", "to": "route_parity_doc", "type": "generates", "reason": "Route parity generator owns the generated route inventory."},
    {"from": "route_parity_generator", "to": "route_mutation_inventory_json", "type": "generates", "reason": "Route parity generator owns the machine-readable route mutation inventory."},
    {"from": "backend_route_ownership_map_generator", "to": "backend_route_ownership_map_json", "type": "generates", "reason": "Generator emits the machine-readable FastAPI route ownership map."},
    {"from": "backend_route_ownership_map_generator", "to": "backend_route_ownership_map_doc", "type": "generates", "reason": "Generator emits the human-readable FastAPI route ownership map."},
    {"from": "backend_route_ownership_map_doc", "to": "backend_route_ownership_map_json", "type": "documents", "reason": "Markdown is rendered from the JSON backend route ownership map."},
    {"from": "backend_route_ownership_map_json", "to": "route_mutation_inventory_json", "type": "checks", "reason": "Backend map cross-checks FastAPI decorators against route inventory classifications."},
    {"from": "api_and_storage", "to": "backend_route_ownership_map_doc", "type": "points_to", "reason": "API/storage doc points route edits to backend adapter ownership."},
    {"from": "storage_ownership_map_generator", "to": "storage_ownership_map_json", "type": "generates", "reason": "Storage ownership generator emits the machine-readable storage map."},
    {"from": "storage_ownership_map_generator", "to": "storage_ownership_map_doc", "type": "generates", "reason": "Storage ownership generator emits the human-readable storage map."},
    {"from": "storage_ownership_map_json", "to": "route_mutation_inventory_json", "type": "consumes", "reason": "Storage map reads route inventory store references instead of reparsing routes."},
    {"from": "route_lifecycle_doc", "to": "route_lifecycle_code", "type": "owns", "reason": "Doc owns the descriptive lifecycle header contract."},
    {"from": "api_and_storage", "to": "app_api_routes", "type": "documents", "reason": "API/storage doc maps browser-facing route groups."},
    {"from": "api_and_storage", "to": "fastapi_main", "type": "documents", "reason": "API/storage doc names backend-only and mirrored FastAPI endpoints."},
    {"from": "operator_auth", "to": "app_api_routes", "type": "checks", "reason": "Browser-facing writes should pass local operator auth before body parsing."},
    {"from": "backend_transport", "to": "fastapi_main", "type": "implements", "reason": "Backend transport forwards optional backend bridge auth to FastAPI."},
    {"from": "proof_doc", "to": "proof_contract_json", "type": "owns", "reason": "Proof doc explains the versioned proof/evidence source contract."},
    {"from": "proof_backend", "to": "proof_contract_json", "type": "implements", "reason": "Backend proof predicates load the canonical contract."},
    {"from": "proof_generator", "to": "proof_generated_ts", "type": "generates", "reason": "Generator emits frontend proof artifact from the JSON contract."},
    {"from": "proof_invariant_generator", "to": "proof_invariant_doc", "type": "generates", "reason": "Generator emits human-readable proof invariant table."},
    {"from": "proof_invariant_generator", "to": "proof_invariant_cases", "type": "consumes", "reason": "Generator reads the test-only proof invariant manifest."},
    {"from": "proof_invariant_doc", "to": "proof_invariant_cases", "type": "documents", "reason": "Markdown table is rendered from the invariant case manifest."},
    {"from": "proof_doc", "to": "proof_invariant_doc", "type": "points_to", "reason": "Proof owner doc points agents to the invariant matrix."},
    {"from": "proof_frontend_facade", "to": "proof_generated_ts", "type": "consumes", "reason": "Frontend proof facade imports generated artifact."},
    {"from": "position_evidence", "to": "proof_frontend_facade", "type": "consumes", "reason": "Position evidence UI uses the human proof facade."},
    {"from": "scanner_doc", "to": "scanner_contract_json", "type": "owns", "reason": "Scanner doc explains the versioned creation-safety contract."},
    {"from": "supervised_scan", "to": "scanner_doc", "type": "implements", "reason": "Scanner engine implements scan policy and guardrail behavior."},
    {"from": "replay_profit_doc", "to": "replay_profit_service", "type": "owns", "reason": "Replay/profit doc maps readback assembly ownership."},
    {"from": "replay_profit_service", "to": "wfo_optimizer", "type": "read_after", "reason": "Replay service assembles readbacks from replay engine outputs."},
    {"from": "profitability_paper_gate_goal", "to": "next_steps", "type": "implements", "reason": "Goal prompt turns the active paper-gate sprint backlog into an end-to-end runbook."},
    {"from": "profitability_paper_gate_goal", "to": "decisions", "type": "bounded_by", "reason": "Paper-gate sprint work must preserve durable profitability bridge decisions."},
    {"from": "regular_options_operating_scorecard_generator", "to": "regular_options_operating_scorecard_doc", "type": "generates", "reason": "Scorecard generator emits the active options operating scorecard."},
    {"from": "regular_options_operating_scorecard_generator", "to": "regular_options_profit_capture_queue_doc", "type": "consumes", "reason": "Scorecard reads the profit-capture queue for paper-gate readiness counts."},
    {"from": "regular_options_operating_scorecard_generator", "to": "regular_options_paper_shortlist_doc", "type": "consumes", "reason": "Scorecard reads the paper shortlist release-gate state."},
    {"from": "regular_options_operating_scorecard_generator", "to": "regular_options_fresh_evidence_loop_doc", "type": "consumes", "reason": "Scorecard reads fresh validation and exact realized P&L readiness."},
    {"from": "regular_options_operating_scorecard_generator", "to": "current_policy_circuit_breaker_doc", "type": "consumes", "reason": "Scorecard reads paper-validation-only lane routes."},
    {"from": "regular_options_operating_scorecard_generator", "to": "regular_options_repair_burndown_doc", "type": "consumes", "reason": "Scorecard reads active/source-replay/diagnostic/exhausted exact repair counts."},
    {"from": "regular_options_profit_capture_queue_generator", "to": "regular_options_profit_capture_queue_doc", "type": "generates", "reason": "Profit-capture queue generator emits the queue report."},
    {"from": "regular_options_paper_shortlist_generator", "to": "regular_options_paper_shortlist_doc", "type": "generates", "reason": "Paper shortlist generator emits the paper-review release gate."},
    {"from": "regular_options_fresh_evidence_loop_generator", "to": "regular_options_fresh_evidence_loop_doc", "type": "generates", "reason": "Fresh evidence generator emits the validation and exact-P&L readback."},
    {"from": "current_policy_circuit_breaker_generator", "to": "current_policy_circuit_breaker_doc", "type": "generates", "reason": "Circuit breaker generator emits paper-validation-only lane routes."},
    {"from": "regular_options_repair_attempts_generator", "to": "regular_options_repair_attempts_doc", "type": "generates", "reason": "Repair-attempt generator emits keyed provider repair memory."},
    {"from": "regular_options_repair_burndown_generator", "to": "regular_options_repair_burndown_doc", "type": "generates", "reason": "Repair burn-down generator emits the exact repair target report."},
    {"from": "regular_options_repair_burndown_generator", "to": "regular_options_profit_capture_queue_doc", "type": "consumes", "reason": "Repair burn-down reads the profit-capture repair queue."},
    {"from": "regular_options_repair_burndown_generator", "to": "regular_options_repair_attempts_doc", "type": "consumes", "reason": "Repair burn-down reads repair-attempt memory before provider commands are active."},
    {"from": "profitability_paper_gate_goal", "to": "regular_options_operating_scorecard_doc", "type": "points_to", "reason": "Sprint 6 adds paper-gate readiness counts to the scorecard."},
    {"from": "repository_doc", "to": "repository_contracts_code", "type": "owns", "reason": "Repository doc maps structural repository capability contracts."},
    {"from": "record_parity_doc", "to": "positions_repository", "type": "documents", "reason": "Parity doc separates tracked-position and suggested-trade row semantics."},
    {"from": "record_parity_doc", "to": "suggested_trades_repository", "type": "documents", "reason": "Parity doc separates suggested paper ideas from tracked production rows."},
    {"from": "repository_migrations_doc", "to": "repository_migrations_code", "type": "owns", "reason": "Migration doc owns the versioned migration manifest."},
    {"from": "repository_constraints_doc", "to": "repository_constraints_code", "type": "owns", "reason": "Constraint doc owns DB/API/proof invariant boundaries."},
    {"from": "repository_indexes_doc", "to": "repository_indexes_code", "type": "owns", "reason": "Index doc owns read-path index boundaries."},
    {"from": "local_db_doc", "to": "local_db_manifest", "type": "owns", "reason": "Local DB doc owns SQLite role classifications."},
    {"from": "storage_ownership_map_doc", "to": "repository_doc", "type": "points_to", "reason": "Storage map points agents to repository ownership docs."},
    {"from": "storage_ownership_map_doc", "to": "local_db_doc", "type": "points_to", "reason": "Storage map points agents to local DB hardening docs."},
    {"from": "api_models_doc", "to": "api_models_code", "type": "owns", "reason": "API models doc owns backend mutation adapter boundary."},
    {"from": "ts_api_contracts_doc", "to": "ts_api_contracts_code", "type": "owns", "reason": "TypeScript contracts doc owns manual TS request/response shapes."},
    {"from": "api_response_validation", "to": "ts_api_contracts_code", "type": "implements", "reason": "Response validation checks shallow envelopes named by TS contracts."},
    {"from": "schema_bridge_generator", "to": "schema_bridge_json", "type": "generates", "reason": "Schema bridge generator emits JSON check artifact."},
    {"from": "schema_bridge_generator", "to": "schema_bridge_doc", "type": "generates", "reason": "Schema bridge generator emits Markdown check artifact."},
    {"from": "schema_bridge_json", "to": "ts_api_contracts_code", "type": "checks", "reason": "Bridge maps manual TypeScript contracts."},
    {"from": "schema_bridge_json", "to": "api_models_code", "type": "checks", "reason": "Bridge maps narrow Pydantic adapter schemas."},
    {"from": "store_ownership_code", "to": "route_parity_doc", "type": "documents", "reason": "Store/lifecycle registry appears in route parity output."},
    {"from": "strategy_replay_intent", "to": "route_parity_doc", "type": "documents", "reason": "Strategy Lab route contracts appear in route parity output."},
    {"from": "predictions_view", "to": "trading_desk_tabs", "type": "consumes", "reason": "Trading Desk coordinator uses typed tab IDs."},
    {"from": "scanner_tab", "to": "scanner_evidence_panel", "type": "implements", "reason": "Scanner evidence display is split into a focused component."},
    {"from": "scanner_tab", "to": "scanner_record_form", "type": "implements", "reason": "Selected-pick record UI is split into a focused component."},
    {"from": "tracked_positions_tab", "to": "fintable", "type": "consumes", "reason": "Tracked-position surface uses explicit FinTable mobile contract."},
    {"from": "suggested_trades_tab", "to": "fintable", "type": "consumes", "reason": "Suggested-trade surface uses explicit FinTable mobile contract."},
    {"from": "scanner_tab", "to": "fintable", "type": "consumes", "reason": "Scanner surface uses explicit FinTable mobile contract."},
    {"from": "app_shell", "to": "navigation_tabs", "type": "consumes", "reason": "App shell consumes typed main navigation tabs."},
    {"from": "strategy_view", "to": "brain_tab", "type": "implements", "reason": "Strategy Lab profile surface lives in BrainTab."},
    {"from": "strategy_view", "to": "optimizer_tab", "type": "implements", "reason": "Strategy Lab replay surface lives in OptimizerTab."},
    {"from": "ai_commodity_runner", "to": "ai_commodity_latest", "type": "generates", "reason": "AI commodity runner emits latest proof-lane readback."},
    {"from": "ai_commodity_isolation_doc", "to": "ai_commodity_runner", "type": "bounds", "reason": "Isolation contract tells agents when to avoid runner changes."},
    {"from": "ai_commodity_isolation_doc", "to": "storage_ownership_map_doc", "type": "checks", "reason": "Isolation contract consumes storage-map classification for AI commodity artifacts."},
    {"from": "ai_commodity_isolation_doc", "to": "route_mutation_inventory_json", "type": "checks", "reason": "Isolation contract consumes route inventory to guard browser/API exposure."},
    {"from": "ai_commodity_runner", "to": "project_context", "type": "deferred_to", "reason": "AI commodity remains separate from mounted browser product."},
    {"from": "memory_graph_doc", "to": "route_parity_doc", "type": "does_not_replace", "reason": "Memory graph points to generated route inventory instead of duplicating it."},
    {"from": "memory_graph_doc", "to": "route_mutation_inventory_json", "type": "does_not_replace", "reason": "Memory graph points to machine-readable route mutation inventory instead of duplicating it."},
    {"from": "memory_graph_doc", "to": "backend_route_ownership_map_doc", "type": "does_not_replace", "reason": "Memory graph points to the generated backend route ownership map instead of duplicating route adapters."},
    {"from": "memory_graph_doc", "to": "storage_ownership_map_doc", "type": "does_not_replace", "reason": "Memory graph points to generated storage ownership map instead of duplicating it."},
    {"from": "memory_graph_doc", "to": "generated_artifact_governance_doc", "type": "does_not_replace", "reason": "Memory graph points to generated artifact governance instead of duplicating trust boundaries."},
    {"from": "memory_graph_doc", "to": "remediation_loop_map_doc", "type": "does_not_replace", "reason": "Memory graph points to the 44-point handoff ledger instead of duplicating status."},
    {"from": "memory_graph_doc", "to": "final_remediation_closure_pack_doc", "type": "does_not_replace", "reason": "Memory graph points to the final closure pack instead of duplicating closure validation."},
    {"from": "final_remediation_closure_pack_doc", "to": "remediation_loop_map_doc", "type": "does_not_replace", "reason": "Closure pack proves the loop is closed but the loop map owns per-point status details."},
    {"from": "final_remediation_closure_pack_doc", "to": "generated_artifact_governance_doc", "type": "does_not_replace", "reason": "Closure pack proves governance is clean but governance owns generated-artifact trust boundaries."},
    {"from": "memory_graph_doc", "to": "api_and_storage", "type": "does_not_replace", "reason": "Memory graph points to storage/API owner docs instead of duplicating inventories."},
)

PLAYBOOKS: tuple[dict[str, Any], ...] = (
    {
        "id": "start_here",
        "heading": "Start Here",
        "summary": "Use this path before broad architecture or product-scope work.",
        "nodes": ["agents_guide", "readme", "docs_index", "living_docs_hygiene", "project_context", "architecture_overview", "architecture_best_practices", "final_remediation_closure_pack_doc", "remediation_loop_map_doc", "next_steps"],
    },
    {
        "id": "routes_auth",
        "heading": "If Touching Routes/Auth",
        "summary": "Follow route ownership, auth boundaries, and generated parity before route edits.",
        "nodes": ["api_and_storage", "route_parity_doc", "route_mutation_inventory_json", "backend_route_ownership_map_doc", "runtime_request_flow", "route_lifecycle_doc", "operator_auth", "backend_transport", "app_api_routes", "fastapi_main"],
    },
    {
        "id": "proof_evidence",
        "heading": "If Touching Proof/Evidence",
        "summary": "Proof claims must stay stricter than UI display groups.",
        "nodes": ["proof_doc", "proof_contract_json", "proof_invariant_cases", "proof_invariant_doc", "proof_backend", "proof_generated_ts", "proof_frontend_facade", "position_evidence"],
    },
    {
        "id": "scanner_creation",
        "heading": "If Touching Scanner/Creation",
        "summary": "Keep candidate visibility, creation eligibility, and row creation separate.",
        "nodes": ["scanner_doc", "scanner_contract_json", "supervised_scan", "store_ownership_code", "route_parity_doc"],
    },
    {
        "id": "replay_profit",
        "heading": "If Touching Replay/Profit",
        "summary": "Replay readbacks, policy, proof predicates, and profit-cycle state have separate owners.",
        "nodes": ["replay_profit_doc", "replay_profit_service", "wfo_optimizer", "metric_truth_audit", "options_profit_gate", "options_profit_flywheel"],
    },
    {
        "id": "profitability_paper_gates",
        "heading": "If Touching Profitability Paper Gates",
        "summary": "Use the sprint goal and current readbacks before changing paper-gate eligibility or operator workflow.",
        "nodes": [
            "profitability_paper_gate_goal",
            "regular_options_operating_scorecard_doc",
            "regular_options_profit_capture_queue_doc",
            "regular_options_paper_shortlist_doc",
            "regular_options_fresh_evidence_loop_doc",
            "current_policy_circuit_breaker_doc",
            "regular_options_operator_workflow_doc",
            "regular_options_repair_attempts_doc",
            "regular_options_repair_burndown_doc",
            "next_steps",
            "project_context",
            "decisions",
            "replay_profit_doc",
            "scanner_doc",
            "proof_doc",
            "options_profit_gate",
            "options_profit_flywheel",
        ],
    },
    {
        "id": "db_repositories",
        "heading": "If Touching DB/Repositories",
        "summary": "Preserve tracked-position Postgres ownership and suggested-trade SQLite separation.",
        "nodes": ["storage_ownership_map_doc", "repository_doc", "record_parity_doc", "repository_migrations_doc", "repository_constraints_doc", "repository_indexes_doc", "local_db_doc", "positions_repository", "suggested_trades_repository"],
    },
    {
        "id": "frontend_trading_desk",
        "heading": "If Touching Frontend",
        "summary": "Use typed IDs and focused workflow components before changing Trading Desk or Strategy Lab surfaces.",
        "nodes": ["app_shell", "navigation_tabs", "predictions_view", "trading_desk_tabs", "tracked_positions_tab", "suggested_trades_tab", "scanner_tab", "fintable", "strategy_view"],
    },
    {
        "id": "generated_artifacts",
        "heading": "If Touching Generated Artifacts",
        "summary": "Run the owner generator and keep generated artifacts deterministic and checked.",
        "nodes": ["living_docs_hygiene", "living_docs_hygiene_checker", "generated_artifact_manifest", "generated_artifact_governance_generator", "final_remediation_closure_pack_generator", "route_parity_generator", "backend_route_ownership_map_generator", "storage_ownership_map_generator", "schema_bridge_generator", "proof_generator", "proof_invariant_generator", "ai_commodity_isolation_generator", "remediation_loop_map_generator", "memory_graph_generator", "route_parity_doc", "route_mutation_inventory_json", "backend_route_ownership_map_doc", "backend_route_ownership_map_json", "storage_ownership_map_json", "storage_ownership_map_doc", "schema_bridge_doc", "proof_generated_ts", "proof_invariant_doc", "ai_commodity_isolation_doc", "ai_commodity_isolation_json", "remediation_loop_map_doc", "remediation_loop_map_json", "generated_artifact_governance_doc", "generated_artifact_governance_json", "final_remediation_closure_pack_doc", "final_remediation_closure_pack_json", "memory_graph_doc"],
    },
    {
        "id": "ai_commodity",
        "heading": "If Touching AI Commodity",
        "summary": "Treat AI commodity as a separate non-browser proof-first lane.",
        "nodes": ["project_context", "ai_commodity_isolation_doc", "ai_commodity_isolation_json", "next_steps", "ai_commodity_runner", "ai_commodity_latest"],
    },
    {
        "id": "final_closure",
        "heading": "Final Closure",
        "summary": "Use this path to prove the 44-point remediation loop is closed without treating closure as runtime behavior.",
        "nodes": ["final_remediation_closure_pack_doc", "final_remediation_closure_pack_json", "remediation_loop_map_doc", "generated_artifact_governance_doc", "memory_graph_doc", "living_docs_hygiene", "architecture_best_practices", "project_context"],
    },
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _node_path(node: dict[str, str]) -> Path:
    return ROOT / node["path"]


def build_graph() -> dict[str, Any]:
    graph = {
        "graph_version": 1,
        "artifact": "agent_memory_graph",
        "generated_by": "scripts/generate_agent_memory_graph.py",
        "runtime_use": False,
        "scope": (
            "Orientation metadata for regular supervised options browser product work and the separate "
            "AI commodity proof lane. It helps agents choose owner docs and code paths."
        ),
        "sources": [
            "Explicit manifest in scripts/generate_agent_memory_graph.py",
            "docs/architecture-best-practices.md",
            "docs/index.md",
        ],
        "non_goals": list(NON_GOALS),
        "nodes": [dict(node) for node in NODES],
        "edges": [dict(edge) for edge in EDGES],
        "playbooks": [dict(playbook) for playbook in PLAYBOOKS],
    }
    _validate_graph(graph, allow_output_paths=True)
    return graph


def _validate_graph(graph: dict[str, Any], *, allow_output_paths: bool = False) -> None:
    nodes = graph["nodes"]
    ids = [node["id"] for node in nodes]
    duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate memory graph node ids: {duplicates}")

    node_ids = set(ids)
    output_paths = {JSON_OUTPUT_PATH, MD_OUTPUT_PATH}
    for node in nodes:
        path = _node_path(node)
        if allow_output_paths and path in output_paths:
            continue
        if not path.exists():
            raise ValueError(f"Memory graph node path does not exist: {node['id']} -> {node['path']}")

    for edge in graph["edges"]:
        for endpoint in ("from", "to"):
            if edge[endpoint] not in node_ids:
                raise ValueError(f"Unknown edge endpoint {edge[endpoint]} in {edge}")

    for playbook in graph["playbooks"]:
        for node_id in playbook["nodes"]:
            if node_id not in node_ids:
                raise ValueError(f"Unknown playbook node {node_id} in {playbook['id']}")


def render_json(graph: dict[str, Any]) -> str:
    return json.dumps(graph, indent=2, sort_keys=True) + "\n"


def _path_label(node: dict[str, str]) -> str:
    return f"`{node['path']}`"


def render_markdown(graph: dict[str, Any]) -> str:
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    lines = [
        "# Agent Memory Graph",
        "",
        "Generated by `scripts/generate_agent_memory_graph.py`.",
        "Source: explicit manifest in `scripts/generate_agent_memory_graph.py`.",
        "Runtime use: `false`.",
        "Do not hand-edit; run `npm run docs:agent-memory-graph`.",
        "",
        "This graph is a navigation artifact for agents. It points to owner docs, code, contracts, and generated artifacts so future work starts in the right place.",
        "",
        "## Scope",
        "",
        str(graph["scope"]),
        "",
    ]

    for playbook in graph["playbooks"]:
        lines.extend([f"## {playbook['heading']}", "", playbook["summary"], ""])
        for node_id in playbook["nodes"]:
            node = nodes_by_id[node_id]
            lines.append(
                f"- `{node['id']}`: {node['label']} - {_path_label(node)}. {node['read_when']}"
            )
        lines.append("")

    lines.extend(["## Graph Nodes", "", "| ID | Kind | Path | Owner Summary |", "| --- | --- | --- | --- |"])
    for node in graph["nodes"]:
        lines.append(
            f"| `{node['id']}` | `{node['kind']}` | `{node['path']}` | {node['owner_summary']} |"
        )

    lines.extend(["", "## Graph Edges", "", "| From | Type | To | Reason |", "| --- | --- | --- | --- |"])
    for edge in graph["edges"]:
        lines.append(
            f"| `{edge['from']}` | `{edge['type']}` | `{edge['to']}` | {edge['reason']} |"
        )

    lines.extend(["", "## Non-Goals", ""])
    for non_goal in graph["non_goals"]:
        lines.append(f"- {non_goal}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the agent memory graph artifacts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated memory graph artifacts are stale.")
    args = parser.parse_args()

    graph = build_graph()
    rendered_json = render_json(graph)
    rendered_md = render_markdown(graph)

    if args.check:
        for path, rendered in ((JSON_OUTPUT_PATH, rendered_json), (MD_OUTPUT_PATH, rendered_md)):
            if not path.exists():
                print(f"{_relative(path)} is missing; run this script without --check.", file=sys.stderr)
                return 1
            if path.read_text(encoding="utf-8") != rendered:
                print(f"{_relative(path)} is out of date; run this script without --check.", file=sys.stderr)
                return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(rendered_json, encoding="utf-8")
    MD_OUTPUT_PATH.write_text(rendered_md, encoding="utf-8")
    print(f"Wrote {_relative(JSON_OUTPUT_PATH)}")
    print(f"Wrote {_relative(MD_OUTPUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
