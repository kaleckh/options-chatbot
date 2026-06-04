from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "scripts/generate_remediation_loop_map.py"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "remediation-loop-map.json"
MD_OUTPUT_PATH = ROOT / "docs" / "remediation-loop-map.md"
COMPLETED_THROUGH_POINT = 44
TOTAL_POINTS = 44

NON_GOALS = (
    "Does not replace owner docs, generated inventories, or generated contract artifacts.",
    "Does not define runtime behavior, route payloads, auth semantics, proof predicates, scanner policy, DB schema, or UI behavior.",
    "Does not replace the final closure pack; it records point status, owner artifacts, checks, and worklog anchors.",
    "Does not treat dated reports, archived docs, or chat context as more authoritative than code and living owner docs.",
)

POINT_41_DOES_NOT_OWN = (
    "route handler behavior",
    "auth semantics",
    "proof predicates",
    "scanner policy",
    "database schema or persistence behavior",
    "frontend runtime behavior",
    "generated artifact stale-governance rules",
    "backend route ownership inventory",
    "final closure verification pack",
)


def _completed(
    point: int,
    title: str,
    category: str,
    scope: str,
    summary: str,
    owner_docs: tuple[str, ...],
    owner_artifacts: tuple[str, ...],
    tests_or_checks: tuple[str, ...],
    *,
    behavior_changed: bool = False,
    does_not_own: tuple[str, ...] = (),
    worklog_evidence: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "point": point,
        "title": title,
        "status": "completed",
        "category": category,
        "scope": scope,
        "summary": summary,
        "owner_docs": list(owner_docs),
        "owner_artifacts": list(owner_artifacts),
        "tests_or_checks": list(tests_or_checks),
        "verification_scope": "focused tests and generated checks named by this point",
        "behavior_changed": behavior_changed,
        "does_not_own": list(
            does_not_own
            or (
                "unrelated lane behavior",
                "future remediation points",
                "historical evidence records as source of truth",
            )
        ),
        "worklog_evidence": list(worklog_evidence or (f"Added Point {point}",)),
    }


def _planned(
    point: int,
    title: str,
    category: str,
    planned_goal: str,
    planned_artifacts: tuple[str, ...],
    non_goals: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "point": point,
        "title": title,
        "status": "planned",
        "category": category,
        "scope": "remaining remediation target",
        "summary": planned_goal,
        "owner_docs": ["docs/architecture-best-practices.md"],
        "owner_artifacts": [],
        "tests_or_checks": [],
        "verification_scope": "to be defined by the point implementation debate",
        "behavior_changed": False,
        "does_not_own": list(non_goals),
        "worklog_evidence": [],
        "planned_goal": planned_goal,
        "planned_artifacts": list(planned_artifacts),
        "non_goals": list(non_goals),
    }


POINTS: tuple[dict[str, Any], ...] = (
    _completed(
        1,
        "Auth Boundaries",
        "auth_routes",
        "separate local operator auth from backend bridge auth",
        "State-changing browser routes gained local operator auth before body parsing, while backend bridge auth stayed separate.",
        ("docs/api-and-storage.md", "docs/runtime-request-flow.md"),
        ("src/lib/operator-auth.ts", "src/lib/backend/transport.ts", "src/app/api/operator/session/route.ts"),
        ("tests/ui/operator-auth.test.js", "tests.test_backend_bridge_auth"),
        behavior_changed=True,
    ),
    _completed(
        2,
        "Route Mutation Inventory",
        "routes",
        "make mutation/auth/lifecycle signals generated and inspectable",
        "Route parity began exposing mounted Next routes, backend routes, auth, mutation-intent, lifecycle, store, and owner fields.",
        ("docs/route-parity.md",),
        ("scripts/generate_route_parity.py", "data/contracts/route-mutation-inventory.json"),
        ("tests.test_route_parity_generator", "tests/ui/operator-auth.test.js"),
    ),
    _completed(
        3,
        "Proof And Evidence Contract Centralization",
        "proof_evidence",
        "centralize proof class and evidence semantics",
        "Backend predicates and frontend display group rules now share the canonical proof/evidence contract boundary.",
        ("docs/proof-evidence-contract.md",),
        (
            "data/contracts/proof-evidence-contract.json",
            "python-backend/proof_contract.py",
            "src/lib/trading-desk/proofContract.ts",
            "src/lib/trading-desk/positionEvidence.ts",
        ),
        ("tests.test_proof_contract", "tests/trading-desk/position-evidence.test.js"),
        behavior_changed=True,
        worklog_evidence=("Added Point 3", "Tightened Point 3", "Closed Point 3"),
    ),
    _completed(
        4,
        "Scanner Creation Safety Centralization",
        "scanner_creation",
        "make scanner-origin row creation eligibility explicit",
        "Scanner-origin tracked and suggested creates now require archived lineage, current guardrails, caps, creation eligibility, and proof eligibility.",
        ("docs/scanner-creation-safety-contract.md",),
        ("data/contracts/scanner-creation-safety-contract.json", "supervised_scan.py"),
        ("tests.test_scanner_creation_contract", "tests.test_tracked_positions_api", "tests.test_suggested_trades_api"),
        behavior_changed=True,
    ),
    _completed(
        5,
        "Evidence Recording Observability",
        "observability",
        "surface lifecycle evidence persistence status",
        "Tracked-position mutations and scan capture now report lifecycle/forward-evidence persistence outcomes instead of hiding failures.",
        ("docs/api-and-storage.md", "docs/scanner-creation-safety-contract.md"),
        ("python-backend/main.py",),
        ("tests.test_tracked_positions_api", "tests.test_forward_options_ledger"),
        behavior_changed=True,
    ),
    _completed(
        6,
        "FastAPI Router Split Pilot",
        "backend_routes",
        "keep main.py as composition root while extracting support routers",
        "Prediction support routes and tool dispatch moved to router modules with late-bound backend context.",
        ("docs/architecture-overview.md", "docs/api-and-storage.md"),
        ("python-backend/main.py", "python-backend/predictions_routes.py", "python-backend/tools_routes.py", "python-backend/backend_route_context.py"),
        ("tests.test_backend_support_routes", "tests.test_route_parity_generator"),
    ),
    _completed(
        7,
        "Application Service Pilot",
        "backend_services",
        "move proof-summary assembly behind a decorator-free service",
        "The proof summary route now delegates assembly work to a service while preserving route adapter ownership in main.py.",
        ("docs/architecture-overview.md", "docs/proof-evidence-contract.md"),
        ("python-backend/proof_summary_service.py", "python-backend/backend_route_context.py"),
        ("tests.test_proof_summary_service", "tests.test_proof_contract"),
    ),
    _completed(
        8,
        "Scanner Pipeline Stage Map",
        "scanner_creation",
        "name scanner pipeline stages for future changes",
        "The scanner creation safety contract and supervised scan code now share a descriptive stage map without changing scan behavior.",
        ("docs/scanner-creation-safety-contract.md",),
        ("data/contracts/scanner-creation-safety-contract.json", "supervised_scan.py"),
        ("tests.test_scanner_creation_contract",),
    ),
    _completed(
        9,
        "Replay And Profit Modularization",
        "replay_profit",
        "extract replay/profit readback assembly from route decorators",
        "Replay/profit readback assembly moved into a service while preserving replay math, cache ownership, and API payloads.",
        ("docs/replay-profit-contract.md",),
        ("python-backend/replay_profit_service.py", "python-backend/main.py"),
        ("tests.test_replay_profit_service", "tests.test_replay_profit_contract"),
    ),
    _completed(
        10,
        "Repository Interfaces",
        "database_repositories",
        "make repository capabilities structural and explicit",
        "Trading Desk repository Protocols now describe shared tracked/suggested capabilities and optional tracked-only capabilities.",
        ("docs/repository-contract.md",),
        ("python-backend/repository_contracts.py", "python-backend/positions_repository.py", "python-backend/suggested_trades_repository.py"),
        ("tests.test_repository_contract",),
    ),
    _completed(
        11,
        "Versioned Repository Migrations",
        "database_repositories",
        "record current repository schemas as versioned baselines",
        "Repository migrations gained a checksum-guarded manifest and schema migration ledger helpers.",
        ("docs/repository-migrations.md",),
        ("python-backend/repository_migrations.py", "python-backend/positions_repository.py", "python-backend/suggested_trades_repository.py"),
        ("tests.test_repository_migrations", "tests.test_positions_repository_schema"),
        behavior_changed=True,
    ),
    _completed(
        12,
        "Repository Constraint Ownership",
        "database_repositories",
        "separate DB-enforced invariants from API/proof-owned semantics",
        "Repository constraint ownership and read-only audits now identify DB, API, proof, and deferred constraint boundaries.",
        ("docs/repository-constraints.md",),
        ("python-backend/repository_constraints.py", "scripts/audit_repository_constraints.py", "python-backend/suggested_trades_repository.py"),
        ("tests.test_repository_constraints", "scripts/audit_repository_constraints.py --json"),
        behavior_changed=True,
    ),
    _completed(
        13,
        "Repository Index Ownership",
        "database_repositories",
        "document existing and deferred repository index ownership",
        "Repository index manifests and read-only audits now distinguish current indexes from deferred performance candidates.",
        ("docs/repository-indexes.md",),
        ("python-backend/repository_indexes.py", "scripts/audit_repository_indexes.py"),
        ("tests.test_repository_indexes", "scripts/audit_repository_indexes.py --json"),
    ),
    _completed(
        14,
        "Suggested-Trade Parity Ownership",
        "database_repositories",
        "clarify tracked versus suggested row parity and differences",
        "Suggested trades gained an explicit parity owner so local paper ideas are not confused with tracked production proof rows.",
        ("docs/trading-desk-record-parity.md",),
        ("python-backend/repository_parity.py",),
        ("tests.test_trading_desk_record_parity",),
    ),
    _completed(
        15,
        "Local DB Hardening Ownership",
        "database_repositories",
        "classify local SQLite stores and audit them read-only",
        "Local DB roles and read-only audit checks now keep support, legacy/test, out-of-scope, and ignored stores separate.",
        ("docs/local-db-hardening.md",),
        ("python-backend/local_db_hardening.py", "scripts/audit_local_databases.py"),
        ("tests.test_local_db_hardening", "scripts/audit_local_databases.py"),
    ),
    _completed(
        16,
        "Trading Desk API Model Ownership",
        "api_contracts",
        "name narrow backend mutation body adapters",
        "Trading Desk mutation bodies gained Pydantic adapters and top-level envelope drift guards without changing endpoint signatures.",
        ("docs/trading-desk-api-models.md",),
        ("python-backend/trading_desk_api_models.py",),
        ("tests.test_trading_desk_api_models",),
    ),
    _completed(
        17,
        "TypeScript API Contract Ownership",
        "api_contracts",
        "name frontend request and response envelopes",
        "Trading Desk TypeScript contracts now give route helpers and UI code named request/response types.",
        ("docs/typescript-api-contracts.md",),
        ("src/lib/trading-desk/apiContracts.ts", "src/lib/backend/positions.ts"),
        ("tests/trading-desk/api-contracts.test.js", "npm run verify:typecheck"),
    ),
    _completed(
        18,
        "Trading Desk Response-Envelope Validation",
        "api_contracts",
        "shallow-check backend envelopes at the Next boundary",
        "Trading Desk Next routes now reject malformed backend envelopes with scoped 502 errors and existing store headers.",
        ("docs/typescript-api-contracts.md",),
        ("src/lib/trading-desk/apiResponseValidation.ts", "src/app/api/positions/route.ts", "src/app/api/suggested-trades/route.ts"),
        ("tests/trading-desk/api-response-validation.test.js",),
        behavior_changed=True,
    ),
    _completed(
        19,
        "Generic Route Lifecycle Headers",
        "routes",
        "name lifecycle headers for mounted generic Next route groups",
        "Generic route contracts now apply route lifecycle headers for scan, predictions, risk/status, sectors, tools, and operator session routes.",
        ("docs/route-lifecycle-contracts.md", "docs/route-parity.md"),
        ("src/lib/route-lifecycle/routeContracts.ts", "scripts/generate_route_parity.py"),
        ("tests/ui/route-lifecycle.test.js", "tests.test_route_parity_generator"),
        behavior_changed=True,
    ),
    _completed(
        20,
        "Generated Trading Desk Schema Bridge",
        "generated_artifacts",
        "check TypeScript and Pydantic contract alignment",
        "A generated schema bridge now maps route contracts, manual TypeScript names, and narrow Pydantic adapter schemas.",
        ("docs/trading-desk-schema-bridge.md",),
        ("scripts/generate_trading_desk_schema_bridge.py", "data/contracts/trading-desk-api-schema-bridge.json"),
        ("tests.test_trading_desk_schema_bridge", "tests/trading-desk/schema-bridge.test.js"),
    ),
    _completed(
        21,
        "PredictionsView Close-Flow Extraction",
        "frontend_readability",
        "split tracked/suggested close dialogs from the Trading Desk coordinator",
        "Close dialog state, modal UI, and exit-price parsing moved into focused frontend modules.",
        ("docs/architecture-overview.md", "docs/architecture-best-practices.md"),
        (
            "src/components/predictions/PredictionsView.tsx",
            "src/components/predictions/useTradingDeskCloseDialogs.ts",
            "src/components/predictions/CloseTradeModal.tsx",
            "src/components/predictions/tradingDeskCloseForm.ts",
        ),
        ("tests/trading-desk/predictions-view-readability.test.js",),
    ),
    _completed(
        22,
        "ScannerTab Readability Split",
        "frontend_readability",
        "split scanner evidence and record form panels out of ScannerTab",
        "Scanner evidence and selected-pick record UI now live in focused components, reducing ScannerTab size.",
        ("docs/scanner-creation-safety-contract.md", "docs/architecture-best-practices.md"),
        (
            "src/components/predictions/ScannerTab.tsx",
            "src/components/predictions/ScannerEvidencePanel.tsx",
            "src/components/predictions/ScannerPickRecordForm.tsx",
        ),
        ("tests/trading-desk/scanner-tab-readability.test.js",),
    ),
    _completed(
        23,
        "Typed Tab And Route ID Catalogs",
        "frontend_readability",
        "centralize app tab and route contract identifiers",
        "Main app tabs, Trading Desk tabs, Strategy Lab IDs, and generic route contract IDs now derive types from readonly catalogs.",
        ("docs/architecture-overview.md", "docs/route-lifecycle-contracts.md"),
        ("src/lib/navigation/tabs.ts", "src/components/predictions/tradingDeskTabs.ts", "src/lib/route-lifecycle/routeContracts.ts"),
        ("tests/ui/navigation-tab-ids.test.js", "tests/ui/route-lifecycle.test.js"),
    ),
    _completed(
        24,
        "Generated Frontend Proof/Evidence Policy Artifact",
        "generated_artifacts",
        "generate frontend proof constants from the canonical proof contract",
        "The frontend proof facade now imports a generated TypeScript artifact produced from the proof/evidence contract.",
        ("docs/proof-evidence-contract.md",),
        ("scripts/generate_proof_evidence_contract.py", "src/lib/generated/proofEvidenceContract.ts"),
        ("tests/trading-desk/proof-contract-generation.test.js", "npm run verify:docs"),
    ),
    _completed(
        25,
        "FinTable Mobile Contract Coverage",
        "frontend_readability",
        "require explicit mobile contracts for production FinTable usage",
        "Production FinTable call sites now expose mobile title, subtitle, and priority-column contracts.",
        ("docs/architecture-best-practices.md",),
        ("src/components/ui/FinTable.tsx", "src/components/predictions/legacy-tabs.tsx"),
        ("tests/ui/fin-table.test.js",),
    ),
    _completed(
        26,
        "Architecture Best-Practices Target Doc",
        "living_docs",
        "write the target architecture/readability rubric",
        "The architecture best-practices doc now defines the target bar and completion checklist for remediation loops.",
        ("docs/architecture-best-practices.md",),
        ("tests/test_architecture_best_practices_doc.py",),
        ("tests.test_architecture_best_practices_doc",),
    ),
    _completed(
        27,
        "Generated Agent Memory Graph",
        "generated_artifacts",
        "create generated owner-doc navigation metadata",
        "The generated memory graph maps owner docs, code, contracts, generated artifacts, edges, and playbooks for agents.",
        ("docs/agent-memory-graph.md",),
        ("scripts/generate_agent_memory_graph.py", "data/contracts/agent-memory-graph.json"),
        ("tests.test_agent_memory_graph", "npm run verify:docs"),
    ),
    _completed(
        28,
        "Generated Route/Mutation JSON Inventory",
        "generated_artifacts",
        "emit machine-readable route and mutation inventory",
        "Route parity now writes a JSON sibling for route auth, mutation, lifecycle, store, backend-only, and client-fetch inventory.",
        ("docs/route-parity.md",),
        ("scripts/generate_route_parity.py", "data/contracts/route-mutation-inventory.json"),
        ("tests.test_route_parity_generator", "npm run verify:docs"),
    ),
    _completed(
        29,
        "Generated Storage Ownership Map",
        "generated_artifacts",
        "emit route, repository, artifact, local DB, and virtual storage ownership",
        "A generated storage ownership map now composes route inventory and repository manifests into human and JSON artifacts.",
        ("docs/storage-ownership-map.md",),
        ("scripts/generate_storage_ownership_map.py", "data/contracts/storage-ownership-map.json"),
        ("tests.test_storage_ownership_map", "npm run verify:docs"),
    ),
    _completed(
        30,
        "Living-Docs Hygiene Guard",
        "living_docs",
        "check living docs, source-of-truth boundaries, and generated artifacts",
        "The living-docs hygiene checker now guards required docs, generated links, generated banners, package wiring, and placeholder markers.",
        ("docs/living-docs-hygiene.md",),
        ("scripts/check_living_docs_hygiene.py",),
        ("tests.test_living_docs_hygiene", "npm run verify:docs"),
    ),
    _completed(
        31,
        "No-Unclassified-Mutation Route Guard",
        "routes",
        "fail generated route parity for authenticated mutators without explicit ownership",
        "Route parity validation now rejects mutating routes that lack explicit lifecycle/store/record contracts.",
        ("docs/route-parity.md",),
        ("scripts/generate_route_parity.py", "data/contracts/route-mutation-inventory.json"),
        ("tests.test_route_parity_generator", "npm run verify:docs"),
    ),
    _completed(
        32,
        "Auth Rejection/Allowance Coverage",
        "auth_routes",
        "pin local-operator auth rejection and allowance behavior",
        "Operator auth tests now prove mutating proxy routes reject bad auth before body parsing and allow valid local operator auth.",
        ("docs/api-and-storage.md",),
        ("tests/ui/operator-auth.test.js",),
        ("tests/ui/operator-auth.test.js",),
    ),
    _completed(
        33,
        "Proof Invariant Table Tests",
        "proof_evidence",
        "pin proof/evidence edge cases across backend and frontend",
        "A test-only proof invariant matrix now drives backend, frontend, proof-summary, and options-profit regression tests.",
        ("docs/proof-invariant-table.md", "docs/proof-evidence-contract.md"),
        ("scripts/generate_proof_invariant_table.py", "data/contracts/proof-invariant-cases.json"),
        ("tests.test_proof_invariant_cases", "tests/trading-desk/proof-invariants.test.js"),
    ),
    _completed(
        34,
        "Scanner Lineage Mutation Coverage",
        "scanner_creation",
        "test scanner-origin create tamper cases",
        "Tracked-position and suggested-trade create tests now reject scanner lineage, contract, execution, and source mutations.",
        ("docs/scanner-creation-safety-contract.md", "docs/api-and-storage.md"),
        ("tests/options_algorithm_fixtures.py",),
        ("tests.test_tracked_positions_api", "tests.test_suggested_trades_api"),
    ),
    _completed(
        35,
        "DB Migration/Constraint Safety Tests",
        "database_repositories",
        "pin migration ledger and constraint-audit safety",
        "Repository migration and constraint tests now guard baseline checksums, ledger uniqueness, unknown-store safety, and dirty audit reporting.",
        ("docs/repository-migrations.md", "docs/repository-constraints.md"),
        ("python-backend/repository_constraints.py",),
        ("tests.test_repository_migrations", "tests.test_repository_constraints"),
    ),
    _completed(
        36,
        "Suggested/Tracked Parity Runtime Tests",
        "database_repositories",
        "exercise common tracked and suggested row lifecycle shape",
        "Runtime tests now create, review, and close equivalent tracked/suggested rows while preserving tracked-only proof and lineage boundaries.",
        ("docs/trading-desk-record-parity.md",),
        ("tests/test_trading_desk_record_parity.py",),
        ("tests.test_trading_desk_record_parity",),
    ),
    _completed(
        37,
        "Golden Proof-Count/Replay Readback Tests",
        "proof_evidence",
        "pin aggregate proof and replay readbacks",
        "Golden readback fixtures now assert deterministic proof-summary, options-profit, profit-cycle, grouped summary, and replay-service counts.",
        ("docs/proof-evidence-contract.md", "docs/replay-profit-contract.md"),
        ("data/contracts/proof-replay-golden-readbacks.json", "tests/test_golden_proof_replay_readbacks.py"),
        ("tests.test_golden_proof_replay_readbacks",),
    ),
    _completed(
        38,
        "Encoding/Mojibake Cleanup",
        "hygiene",
        "remove corrupted text signatures from active files",
        "Active source/docs/test/checked-contract scans now reject replacement characters and common mojibake signatures.",
        ("docs/architecture-best-practices.md",),
        ("options_chatbot.py", "tests/test_text_encoding_hygiene.py"),
        ("tests.test_text_encoding_hygiene",),
    ),
    _completed(
        39,
        "Legacy Lane Boundary Governance",
        "lane_boundaries",
        "generate active, separate, legacy, and paused lane boundaries",
        "A checked lane-boundary manifest now keeps regular options, AI commodity, day-trading, crypto-options, and Polymarket scope readable.",
        ("docs/legacy-lane-boundaries.md",),
        ("scripts/generate_legacy_lane_boundaries.py", "data/contracts/legacy-lane-boundaries.json"),
        ("tests.test_legacy_lane_boundaries", "npm run verify:docs"),
    ),
    _completed(
        40,
        "AI Commodity Isolation Governance",
        "lane_boundaries",
        "generate non-browser AI commodity proof-lane isolation checks",
        "A checked isolation contract now verifies AI commodity remains separate from browser/API/tool routes, scanner tracking, and active proof claims.",
        ("docs/ai-commodity-isolation.md",),
        ("scripts/generate_ai_commodity_isolation.py", "data/contracts/ai-commodity-isolation.json"),
        ("tests.test_ai_commodity_isolation", "npm run verify:docs"),
    ),
    _completed(
        41,
        "Generated Remediation Loop Map / LLM Handoff Ledger",
        "llm_readability",
        "make the 44-point remediation loop recoverable without chat context",
        "This generated ledger records all point targets, status split, owner artifacts, verification anchors, non-goals, and worklog evidence.",
        ("docs/remediation-loop-map.md", "docs/architecture-best-practices.md", "docs/autoresearch/code-audit-remediation-goal.md"),
        ("scripts/generate_remediation_loop_map.py", "data/contracts/remediation-loop-map.json"),
        ("tests.test_remediation_loop_map", "npm run verify:docs"),
        does_not_own=POINT_41_DOES_NOT_OWN,
    ),
    _completed(
        42,
        "Backend Route Ownership Map",
        "backend_routes",
        "map FastAPI adapter ownership, router extraction, service delegation, and backend-only surfaces",
        "A generated backend route ownership map now statically cross-checks FastAPI decorators against the route inventory and owner docs.",
        ("docs/backend-route-ownership-map.md", "docs/api-and-storage.md", "docs/architecture-overview.md"),
        ("scripts/generate_backend_route_ownership_map.py", "data/contracts/backend-route-ownership-map.json"),
        ("tests.test_backend_route_ownership_map", "npm run verify:docs"),
        does_not_own=(
            "FastAPI route handler behavior",
            "decorators or route paths",
            "auth behavior",
            "request or response payloads",
            "proof/scanner/replay semantics",
            "database schema or repositories",
            "frontend behavior",
            "generated artifact stale-governance rules",
            "final closure verification pack",
        ),
    ),
    _completed(
        43,
        "Generated Artifact Governance And Stale-Artifact Trust Boundaries",
        "generated_artifacts",
        "classify generated artifact ownership, runtime posture, and stale handling",
        "A shared generated-artifact manifest and generated governance map now define owner commands, checks, trust roles, runtime posture, and stale-action rules.",
        ("docs/generated-artifact-governance.md", "docs/living-docs-hygiene.md", "docs/architecture-best-practices.md"),
        (
            "scripts/generated_artifact_manifest.py",
            "scripts/generate_generated_artifact_governance.py",
            "data/contracts/generated-artifact-governance.json",
        ),
        ("tests.test_generated_artifact_governance", "npm run verify:docs"),
        does_not_own=(
            "route behavior",
            "auth semantics",
            "request or response payloads",
            "proof/scanner/replay semantics",
            "database schema",
            "frontend behavior beyond existing generated runtime projection",
            "volatile research or market-data report governance",
            "final closure verification pack",
        ),
    ),
    _completed(
        44,
        "Final Goal Closure Verification Pack",
        "verification",
        "prove the 44-point loop is complete, checked, discoverable, and still within active scope",
        "The generated closure pack now reads the loop map, generated artifact governance, memory graph, living docs, and lane guard artifacts to prove all 44 points are complete.",
        ("docs/final-remediation-closure-pack.md", "docs/architecture-best-practices.md"),
        (
            "scripts/generate_final_remediation_closure_pack.py",
            "data/contracts/final-remediation-closure-pack.json",
        ),
        ("tests.test_final_remediation_closure_pack", "npm run verify:docs"),
        does_not_own=(
            "route behavior",
            "auth semantics",
            "request or response payloads",
            "proof/scanner/replay semantics",
            "database schema",
            "frontend behavior",
            "product profitability or broker execution readiness",
            "AI commodity proof completion",
            "paused sidecar lane reopening",
        ),
    ),
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _path_exists(relative_path: str, *, allow_outputs: bool = False) -> bool:
    path = ROOT / relative_path
    if allow_outputs and path in {JSON_OUTPUT_PATH, MD_OUTPUT_PATH}:
        return True
    return path.exists()


def _validate_points(points: list[dict[str, Any]], *, allow_output_paths: bool = False) -> list[str]:
    errors: list[str] = []
    numbers = [point["point"] for point in points]
    if len(points) != TOTAL_POINTS:
        errors.append(f"Expected {TOTAL_POINTS} remediation points, found {len(points)}.")
    if numbers != list(range(1, TOTAL_POINTS + 1)):
        errors.append(f"Point numbers must be unique, consecutive, and sorted 1..{TOTAL_POINTS}: {numbers}")

    worklog = (ROOT / "docs" / "WORKLOG.md").read_text(encoding="utf-8")
    valid_statuses = {"completed", "in_progress", "planned"}

    for point in points:
        point_number = point["point"]
        status = point["status"]
        if status not in valid_statuses:
            errors.append(f"Point {point_number} has invalid status {status!r}.")
        for field in (
            "title",
            "category",
            "scope",
            "summary",
            "owner_docs",
            "owner_artifacts",
            "tests_or_checks",
            "verification_scope",
            "behavior_changed",
            "does_not_own",
            "worklog_evidence",
        ):
            if field not in point:
                errors.append(f"Point {point_number} is missing {field}.")

        if point_number <= COMPLETED_THROUGH_POINT and status != "completed":
            errors.append(f"Point {point_number} must be completed.")
        if point_number > COMPLETED_THROUGH_POINT and status != "planned":
            errors.append(f"Point {point_number} must remain planned.")

        if status == "completed":
            owner_paths = [*point["owner_docs"], *point["owner_artifacts"]]
            if not owner_paths:
                errors.append(f"Completed Point {point_number} must have owner paths.")
            if not point["tests_or_checks"]:
                errors.append(f"Completed Point {point_number} must have tests or checks.")
            for relative_path in owner_paths:
                if not _path_exists(relative_path, allow_outputs=allow_output_paths):
                    errors.append(f"Point {point_number} references missing owner path: {relative_path}")
            if not any(anchor in worklog for anchor in point["worklog_evidence"]):
                errors.append(f"Point {point_number} has no matching worklog evidence: {point['worklog_evidence']}")
        else:
            if point["worklog_evidence"]:
                errors.append(f"Planned Point {point_number} must not claim worklog completion evidence.")
            if "planned_goal" not in point or "non_goals" not in point:
                errors.append(f"Planned Point {point_number} must include planned_goal and non_goals.")

    return errors


def _validate_discovery_links() -> list[str]:
    required_links = {
        "docs/index.md": ("docs/remediation-loop-map.md", "data/contracts/remediation-loop-map.json"),
        "docs/living-docs-hygiene.md": ("docs/remediation-loop-map.md", "data/contracts/remediation-loop-map.json"),
        "docs/architecture-best-practices.md": ("docs/remediation-loop-map.md",),
        "docs/autoresearch/code-audit-remediation-goal.md": ("docs/remediation-loop-map.md",),
        "scripts/generate_agent_memory_graph.py": (
            "scripts/generate_remediation_loop_map.py",
            "docs/remediation-loop-map.md",
            "data/contracts/remediation-loop-map.json",
        ),
        "docs/agent-memory-graph.md": ("docs/remediation-loop-map.md",),
    }
    errors: list[str] = []
    for relative_path, links in required_links.items():
        path = ROOT / relative_path
        if not path.exists():
            errors.append(f"Discovery owner is missing: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for link in links:
            if link not in text:
                errors.append(f"{relative_path} does not link remediation loop map target: {link}")
    return errors


def build_contract() -> dict[str, Any]:
    points = [dict(point) for point in POINTS]
    errors = _validate_points(points, allow_output_paths=True)
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "map_version": 1,
        "artifact": "remediation_loop_map",
        "generated_by": GENERATOR,
        "runtime_use": False,
        "scope": (
            "Generated handoff ledger for the 44-point architecture/readability remediation loop. "
            "It tells future LLM agents and senior engineers what has been completed, what remains, "
            "which owner artifacts to read, and which boundaries each point deliberately does not own."
        ),
        "sources": [
            f"Explicit manifest in {GENERATOR}",
            "docs/WORKLOG.md",
            "docs/architecture-best-practices.md",
            "docs/index.md",
        ],
        "non_goals": list(NON_GOALS),
        "current_state": {
            "total_points": TOTAL_POINTS,
            "completed_through_point": COMPLETED_THROUGH_POINT,
            "completed_points": list(range(1, COMPLETED_THROUGH_POINT + 1)),
            "planned_points": list(range(COMPLETED_THROUGH_POINT + 1, TOTAL_POINTS + 1)),
            "next_point": COMPLETED_THROUGH_POINT + 1 if COMPLETED_THROUGH_POINT < TOTAL_POINTS else None,
        },
        "points": points,
        "validation": {
            "errors": [],
            "point_count": len(points),
            "status_split": {
                "completed": sum(1 for point in points if point["status"] == "completed"),
                "planned": sum(1 for point in points if point["status"] == "planned"),
                "in_progress": sum(1 for point in points if point["status"] == "in_progress"),
            },
        },
    }


def render_json(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def _markdown_list(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def render_markdown(contract: dict[str, Any]) -> str:
    status_split = contract["validation"]["status_split"]
    completed = [point for point in contract["points"] if point["status"] == "completed"]
    planned = [point for point in contract["points"] if point["status"] == "planned"]
    latest_completed = completed[-1]
    next_point = contract["current_state"]["next_point"]
    next_point_label = str(next_point) if next_point is not None else "none"
    lines = [
        "# Remediation Loop Map",
        "",
        f"Generated by `{GENERATOR}`.",
        f"Source: explicit manifest in `{GENERATOR}`.",
        "Runtime use: `false`.",
        "Do not hand-edit; run `npm run docs:remediation-loop-map`.",
        "",
        "This is a handoff ledger for the 44-point architecture/readability remediation loop. It helps agents recover the loop after context compaction without treating chat history as the source of truth.",
        "",
        "## How To Use This Map",
        "",
        "- Read this after `docs/architecture-best-practices.md` when continuing the 44-point goal.",
        "- Use each point's owner docs, artifacts, and checks as the starting path for investigation.",
        "- Treat `docs/WORKLOG.md` as dated evidence, not as the owner of runtime semantics.",
        "- Keep planned points planned until their own debate, implementation, verification, and satisfaction review complete.",
        "",
        "## Status Summary",
        "",
        f"- Total points: `{contract['current_state']['total_points']}`",
        f"- Completed: `{status_split['completed']}`",
        f"- Planned: `{status_split['planned']}`",
        f"- Next point: `{next_point_label}`",
        "",
        "## Completed Points",
        "",
        "| Point | Category | Title | Primary owners | Checks |",
        "| --- | --- | --- | --- | --- |",
    ]
    for point in completed:
        owners = point["owner_docs"][:2] + point["owner_artifacts"][:2]
        checks = point["tests_or_checks"][:2]
        lines.append(
            f"| {point['point']} | `{point['category']}` | {point['title']} | {_markdown_list(owners)} | {_markdown_list(checks)} |"
        )

    lines.extend(
        [
            "",
            "## Latest Completed Point",
            "",
            f"Point {latest_completed['point']} is `{latest_completed['title']}`. It owns {_markdown_list(latest_completed['owner_docs'] + latest_completed['owner_artifacts'])}. It does not own {_markdown_list(latest_completed['does_not_own'])}.",
            "",
            "## Remaining Planned Points",
            "",
            "| Point | Title | Planned Goal | Planned Artifacts | Non-Goals |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for point in planned:
        lines.append(
            f"| {point['point']} | {point['title']} | {point['planned_goal']} | {_markdown_list(point['planned_artifacts'])} | {_markdown_list(point['non_goals'])} |"
        )

    lines.extend(
        [
            "",
            "## Verification Ladder",
            "",
            "Run the focused check for this map first:",
            "",
            "```powershell",
            "uv run --locked python scripts\\generate_remediation_loop_map.py --check",
            "uv run --locked python -m unittest tests.test_remediation_loop_map -v",
            "npm run verify:docs",
            "```",
            "",
            "## Non-Goals",
            "",
        ]
    )
    for non_goal in contract["non_goals"]:
        lines.append(f"- {non_goal}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the remediation loop handoff map.")
    parser.add_argument("--check", action="store_true", help="Fail if generated remediation loop artifacts are stale.")
    args = parser.parse_args()

    contract = build_contract()
    rendered_json = render_json(contract)
    rendered_md = render_markdown(contract)

    if args.check:
        artifact_errors: list[str] = []
        for path, rendered in ((JSON_OUTPUT_PATH, rendered_json), (MD_OUTPUT_PATH, rendered_md)):
            if not path.exists():
                artifact_errors.append(f"{_relative(path)} is missing; run this script without --check.")
            elif path.read_text(encoding="utf-8") != rendered:
                artifact_errors.append(f"{_relative(path)} is out of date; run this script without --check.")
        artifact_errors.extend(_validate_discovery_links())
        if artifact_errors:
            for error in artifact_errors:
                print(error, file=sys.stderr)
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
