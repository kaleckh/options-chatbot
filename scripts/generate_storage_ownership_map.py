from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from local_db_hardening import local_database_manifest  # noqa: E402
from repository_constraints import constraint_manifest  # noqa: E402
from repository_indexes import index_manifest  # noqa: E402
from repository_migrations import migration_manifest  # noqa: E402
from repository_parity import record_parity_manifest, route_parity_manifest  # noqa: E402


ROUTE_INVENTORY_PATH = ROOT / "data" / "contracts" / "route-mutation-inventory.json"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "storage-ownership-map.json"
MD_OUTPUT_PATH = ROOT / "docs" / "storage-ownership-map.md"

SOURCE_PATHS = (
    "data/contracts/route-mutation-inventory.json",
    "python-backend/repository_migrations.py",
    "python-backend/repository_constraints.py",
    "python-backend/repository_indexes.py",
    "python-backend/local_db_hardening.py",
    "python-backend/repository_parity.py",
)

NON_GOALS = (
    "No DB reads, audits, migrations, DDL, PRAGMAs, repairs, vacuuming, file deletion, or schema initialization.",
    "No route handler, auth, request payload, response payload, or runtime validation behavior changes.",
    "No proof, scanner creation, replay, options-profit, or AI commodity semantics.",
    "No tracked-position SQLite fallback and no promotion of test or legacy stores to browser production storage.",
    "No OpenAPI, JSON Schema, generated TypeScript, Pydantic response_model, or stale-artifact governance replacement.",
    "Does not replace repository, migration, constraint, index, local DB, route, proof, scanner, or replay owner manifests.",
)

STORE_CLASSIFICATIONS: dict[str, dict[str, Any]] = {
    "postgres_tracked_positions": {
        "label": "Postgres tracked positions",
        "storage_role": "active_repository",
        "persistence": "postgres",
        "scope": "active_browser",
        "location": "DATABASE_URL",
        "production_role": "Production tracked-position rows, reviews, closes, proof/readback counts, and runtime health.",
        "owners": ("python-backend/positions_repository.py",),
        "owner_docs": (
            "docs/repository-contract.md",
            "docs/api-and-storage.md",
            "docs/repository-migrations.md",
            "docs/repository-constraints.md",
            "docs/repository-indexes.md",
        ),
        "hard_rules": (
            "Tracked positions are Postgres-owned in the browser product.",
            "Missing or failing DATABASE_URL fails closed through the unavailable sentinel.",
            "Do not silently fall back to SQLite.",
        ),
        "notes": ("Proof definitions remain in the proof contract, not in storage ownership.",),
    },
    "sqlite_suggested_trades": {
        "label": "SQLite suggested trades",
        "storage_role": "active_repository",
        "persistence": "sqlite",
        "scope": "active_browser",
        "location": "chat_history.db",
        "production_role": "Local paper and hypothetical suggested-trade workflow state.",
        "owners": ("python-backend/suggested_trades_repository.py",),
        "owner_docs": (
            "docs/repository-contract.md",
            "docs/api-and-storage.md",
            "docs/local-db-hardening.md",
            "docs/repository-migrations.md",
            "docs/repository-constraints.md",
            "docs/repository-indexes.md",
        ),
        "hard_rules": (
            "Suggested trades remain separate from tracked-position proof rows.",
            "Suggested trades are not broker fills and do not feed production proof truth.",
        ),
        "notes": ("Repository write connections enable SQLite foreign keys.",),
    },
    "sqlite_tracked_positions_test_legacy": {
        "label": "SQLite tracked positions test/legacy",
        "storage_role": "test_legacy_repository",
        "persistence": "sqlite",
        "scope": "test_legacy",
        "location": "data/tracked_positions.db",
        "production_role": "Explicit tests and legacy tools only; not browser tracked-position fallback.",
        "owners": ("python-backend/positions_repository.py::SqliteTrackedPositionsRepository",),
        "owner_docs": (
            "docs/repository-contract.md",
            "docs/local-db-hardening.md",
            "docs/repository-migrations.md",
        ),
        "hard_rules": (
            "Do not route browser tracked-position traffic to this store.",
            "Do not promote this store to production fallback behavior.",
        ),
        "notes": ("Kept visible so agents do not mistake legacy SQLite for production tracked storage.",),
    },
    "predictions_json": {
        "label": "Predictions JSON",
        "storage_role": "route_artifact",
        "persistence": "file_artifact",
        "scope": "active_browser",
        "location": "predictions.json",
        "production_role": "Prediction history and grade route artifact state.",
        "owners": ("python-backend/predictions_routes.py",),
        "owner_docs": ("docs/api-and-storage.md", "docs/route-lifecycle-contracts.md"),
        "hard_rules": ("Do not treat prediction history as Trading Desk repository proof storage.",),
        "notes": (),
    },
    "strategy_profile_files": {
        "label": "Strategy profile files",
        "storage_role": "route_artifact",
        "persistence": "file_artifact",
        "scope": "active_browser",
        "location": "strategy_profile.json, brain_changelog.json, and risk/profile artifacts",
        "production_role": "Strategy Lab profile, risk, and changelog state.",
        "owners": ("python-backend/profile_routes.py",),
        "owner_docs": ("docs/api-and-storage.md", "docs/route-lifecycle-contracts.md"),
        "hard_rules": ("Profile saves require local operator auth and mutation intent at the route boundary.",),
        "notes": (),
    },
    "latest_replay_artifacts": {
        "label": "Latest replay artifacts",
        "storage_role": "route_artifact",
        "persistence": "file_artifact",
        "scope": "active_browser",
        "location": "data/options-validation/* and related replay readbacks",
        "production_role": "Strategy Lab replay result, summary, report, comparison, and diagnostics artifacts.",
        "owners": ("python-backend/replay_profit_service.py", "wfo_optimizer.py"),
        "owner_docs": ("docs/replay-profit-contract.md", "docs/api-and-storage.md"),
        "hard_rules": ("Replay artifacts do not redefine scanner policy or proof truth by themselves.",),
        "notes": (),
    },
    "forward_evidence_artifacts": {
        "label": "Forward evidence artifacts",
        "storage_role": "route_artifact",
        "persistence": "file_artifact",
        "scope": "active_browser",
        "location": "data/options-validation/forward_tracking* and forward-evidence ledgers",
        "production_role": "Forward scan evidence, scanner lineage, and lifecycle event readbacks.",
        "owners": ("forward_options_ledger.py", "python-backend/replay_profit_service.py"),
        "owner_docs": (
            "docs/proof-evidence-contract.md",
            "docs/scanner-creation-safety-contract.md",
            "docs/api-and-storage.md",
        ),
        "hard_rules": (
            "Forward evidence can support proof but does not make suggested trades production proof rows.",
            "Exact-looking payloads without verified scan lineage remain proof-ineligible.",
        ),
        "notes": (),
    },
    "options_profit_state_artifacts": {
        "label": "Options-profit state artifacts",
        "storage_role": "route_artifact",
        "persistence": "file_artifact",
        "scope": "active_browser",
        "location": "data/options-profit/* and options-profit state",
        "production_role": "Options-profit status, gates, and proof/profit readbacks.",
        "owners": ("options_profit_gate.py", "options_profit_flywheel.py"),
        "owner_docs": ("docs/replay-profit-contract.md", "docs/api-and-storage.md"),
        "hard_rules": ("Options-profit status consumes proof and repository readbacks; it is not a proof owner.",),
        "notes": (),
    },
    "market_data_cache": {
        "label": "Market data cache",
        "storage_role": "support_cache",
        "persistence": "sqlite_or_file_cache",
        "scope": "backend_support",
        "location": "market_data.db",
        "production_role": "Market data cache and support readbacks such as sectors/cache stats.",
        "owners": ("market data service and research support workflows",),
        "owner_docs": ("docs/local-db-hardening.md", "docs/api-and-storage.md"),
        "hard_rules": ("Outside Trading Desk repository migrations, constraints, indexes, and local DB repair.",),
        "notes": ("Browser-readable support storage is not Trading Desk repository storage.",),
    },
    "local_operator_session_cookie": {
        "label": "Local operator session cookie",
        "storage_role": "session_cookie",
        "persistence": "cookie",
        "scope": "active_browser",
        "location": "HttpOnly options_local_operator_session cookie",
        "production_role": "Local browser unlock/session state for operator auth.",
        "owners": ("src/lib/operator-auth.ts", "src/app/api/operator/session/route.ts"),
        "owner_docs": ("docs/api-and-storage.md", "docs/route-lifecycle-contracts.md"),
        "hard_rules": ("Session status is auth state, not repository or proof storage.",),
        "notes": (),
    },
    "backend_tool_dispatch": {
        "label": "Backend tool dispatch",
        "storage_role": "backend_dispatch",
        "persistence": "virtual",
        "scope": "active_browser",
        "location": "POST /api/tools/{name} dispatch",
        "production_role": "Operator-gated tool invocation surface.",
        "owners": ("python-backend/tools_routes.py", "src/app/api/tools/[name]/route.ts"),
        "owner_docs": ("docs/api-and-storage.md", "docs/route-parity.md"),
        "hard_rules": ("Do not model backend tool dispatch as a concrete database.",),
        "notes": (),
    },
    "backend/domain": {
        "label": "Backend domain placeholder",
        "storage_role": "backend_domain",
        "persistence": "virtual",
        "scope": "backend_support",
        "location": "FastAPI backend-only route/domain logic",
        "production_role": "Placeholder for backend-only routes without a concrete route-lifecycle store contract.",
        "owners": ("python-backend",),
        "owner_docs": ("docs/api-and-storage.md", "docs/route-parity.md"),
        "hard_rules": ("Do not treat backend/domain as a hidden DB or repository fallback.",),
        "notes": ("Use the route owner module for the concrete implementation path.",),
    },
    "options_history_truth_store": {
        "label": "Options history truth store",
        "storage_role": "out_of_scope_local_db",
        "persistence": "sqlite",
        "scope": "out_of_scope",
        "location": "data/options-validation/options_history.db",
        "production_role": "Imported options truth store and replay input, outside Trading Desk repository hardening.",
        "owners": ("historical_options_store.py and import/replay scripts",),
        "owner_docs": ("docs/local-db-hardening.md", "docs/api-and-storage.md"),
        "hard_rules": ("Do not migrate or repair this store through Trading Desk repository contracts.",),
        "notes": (),
    },
    "forward_tracking_ledgers": {
        "label": "Forward tracking ledgers",
        "storage_role": "out_of_scope_local_db",
        "persistence": "sqlite",
        "scope": "out_of_scope",
        "location": "data/options-validation/forward_tracking*.db",
        "production_role": "Canonical and archive forward-evidence ledgers outside repository hardening.",
        "owners": ("forward-evidence and options-profit tooling",),
        "owner_docs": ("docs/local-db-hardening.md", "docs/proof-evidence-contract.md"),
        "hard_rules": ("Use forward-evidence runbooks rather than Trading Desk DB repair workflows.",),
        "notes": (),
    },
    "ai_commodity_artifacts": {
        "label": "AI commodity artifacts",
        "storage_role": "separate_lane",
        "persistence": "file_artifact",
        "scope": "separate_lane",
        "location": "data/ai-commodity-infra/*",
        "production_role": "Separate non-browser proof-first AI commodity lane artifacts.",
        "owners": ("scripts/run_ai_commodity_opra_progress.py",),
        "owner_docs": ("docs/PROJECT_CONTEXT.md", "docs/local-db-hardening.md"),
        "hard_rules": ("Do not mix AI commodity artifacts into browser Trading Desk storage ownership.",),
        "notes": (),
    },
    "evidence_store_backup_directory": {
        "label": "Evidence store backup directory",
        "storage_role": "ignored_sidecar_or_backup",
        "persistence": "backup_bundle",
        "scope": "out_of_scope",
        "location": "data/backups/**",
        "production_role": "Ignored rolling backup bundles for irreplaceable evidence stores.",
        "owners": ("scripts/backup_evidence_stores.py",),
        "owner_docs": ("docs/evidence-operations.md", "docs/local-db-hardening.md"),
        "hard_rules": (
            "Do not treat backup bundles as active stores.",
            "Do not commit data/backups contents.",
        ),
        "notes": ("Backups cover SQLite evidence stores and Postgres tracked-position dumps.",),
    },
    "sqlite_sidecars_and_backups": {
        "label": "SQLite sidecars and backups",
        "storage_role": "ignored_sidecar_or_backup",
        "persistence": "sqlite_sidecar_or_backup",
        "scope": "out_of_scope",
        "location": "*.db-wal, *.db-shm, chat_history.backup-*.db, data/tracked_positions.backup-*",
        "production_role": "Local sidecars and backups generated by runtime or repair workflows.",
        "owners": (".gitignore and manual backup hygiene",),
        "owner_docs": ("docs/local-db-hardening.md",),
        "hard_rules": ("Do not treat sidecars or backups as active stores.",),
        "notes": (),
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _unique_sorted(values: list[Any] | tuple[Any, ...] | set[Any]) -> list[Any]:
    return sorted({value for value in values if value not in (None, "")}, key=str)


def _group_by(entries: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry[key])].append(entry)
    return dict(grouped)


def _route_ref(route: dict[str, Any], *, surface: str) -> dict[str, Any]:
    path = route.get("browser_path") or route.get("path") or route.get("fastapi_path")
    contract_ids = route.get("contract_ids")
    if contract_ids is None and route.get("contract_id"):
        contract_ids = [route["contract_id"]]
    record_classes = route.get("record_classes")
    if record_classes is None and route.get("record_class"):
        record_classes = [route["record_class"]]
    owners = route.get("owners")
    if owners is None and route.get("owner"):
        owners = [route["owner"]]
    return {
        "surface": surface,
        "method": route.get("method"),
        "path": path,
        "route_group": route.get("route_group") or "Backend-Only FastAPI",
        "lifecycle": route.get("lifecycle"),
        "mutating": bool(route.get("mutating")),
        "auth_boundary": route.get("auth_boundary"),
        "contract_ids": _unique_sorted(_list(contract_ids)),
        "record_classes": _unique_sorted(_list(record_classes)),
        "owners": _unique_sorted(_list(owners)),
    }


def _route_usage(route_inventory: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    usage: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"active_browser": [], "backend_only": []}
    )
    for route in route_inventory.get("mounted_browser_routes", []):
        for store_id in route.get("stores", []):
            usage[store_id]["active_browser"].append(_route_ref(route, surface="active_browser"))
    for route in route_inventory.get("backend_only_routes", []):
        store_id = route.get("store")
        if store_id:
            usage[store_id]["backend_only"].append(_route_ref(route, surface="backend_only"))
    return dict(usage)


def _source_paths() -> list[str]:
    return list(SOURCE_PATHS)


def _summarize_constraints(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry["enforcement"])].append(str(entry["constraint_id"]))
    return {key: sorted(values) for key, values in sorted(grouped.items())}


def _summarize_indexes(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry["status"])].append(str(entry["index_id"]))
    return {key: sorted(values) for key, values in sorted(grouped.items())}


def _route_store_references(
    usage: dict[str, dict[str, list[dict[str, Any]]]]
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for store_id, surfaces in usage.items():
        for surface, routes in surfaces.items():
            for route in routes:
                references.append(
                    {
                        "store_id": store_id,
                        "surface": surface,
                        "method": route["method"],
                        "path": route["path"],
                        "lifecycle": route["lifecycle"],
                        "mutating": route["mutating"],
                    }
                )
    return sorted(
        references,
        key=lambda item: (str(item["store_id"]), str(item["surface"]), str(item["path"]), str(item["method"])),
    )


def _tables_for_store(*entry_groups: list[dict[str, Any]]) -> list[str]:
    tables: list[str] = []
    for entries in entry_groups:
        for entry in entries:
            tables.extend(str(table) for table in _list(entry.get("tables")))
            if entry.get("table"):
                tables.append(str(entry["table"]))
            tables.extend(str(table) for table in _list(entry.get("expected_tables")))
    return _unique_sorted(tables)


def _build_store(
    store_id: str,
    *,
    usage: dict[str, dict[str, list[dict[str, Any]]]],
    migrations_by_store: dict[str, list[dict[str, Any]]],
    constraints_by_store: dict[str, list[dict[str, Any]]],
    indexes_by_store: dict[str, list[dict[str, Any]]],
    local_roles_by_store: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    classification = STORE_CLASSIFICATIONS.get(
        store_id,
        {
            "label": store_id,
            "storage_role": "unclassified",
            "persistence": "unknown",
            "scope": "unknown",
            "location": "unknown",
            "production_role": "Unclassified observed store.",
            "owners": (),
            "owner_docs": (),
            "hard_rules": (),
            "notes": (),
        },
    )
    route_usage = usage.get(store_id, {"active_browser": [], "backend_only": []})
    migrations = migrations_by_store.get(store_id, [])
    constraints = constraints_by_store.get(store_id, [])
    indexes = indexes_by_store.get(store_id, [])
    local_roles = local_roles_by_store.get(store_id, [])
    route_contract_ids: list[Any] = []
    record_classes: list[Any] = []
    lifecycles: list[Any] = []
    route_owners: list[Any] = []
    for route in route_usage["active_browser"] + route_usage["backend_only"]:
        route_contract_ids.extend(route["contract_ids"])
        record_classes.extend(route["record_classes"])
        lifecycles.append(route["lifecycle"])
        route_owners.extend(route["owners"])
    local_owners = [entry.get("owner") for entry in local_roles]
    return {
        "store_id": store_id,
        "label": classification["label"],
        "storage_role": classification["storage_role"],
        "persistence": classification["persistence"],
        "scope": classification["scope"],
        "location": classification["location"],
        "production_role": classification["production_role"],
        "owners": _unique_sorted([*classification.get("owners", ()), *route_owners, *local_owners]),
        "owner_docs": list(classification.get("owner_docs", ())),
        "hard_rules": list(classification.get("hard_rules", ())),
        "route_references": route_usage,
        "route_contract_ids": _unique_sorted(route_contract_ids),
        "record_classes": _unique_sorted(record_classes),
        "lifecycles": _unique_sorted(lifecycles),
        "tables": _tables_for_store(migrations, constraints, indexes, local_roles),
        "repository_migrations": [
            {
                "migration_id": entry["migration_id"],
                "dialect": entry["dialect"],
                "tables": entry["tables"],
            }
            for entry in migrations
        ],
        "repository_constraints_by_enforcement": _summarize_constraints(constraints),
        "repository_indexes_by_status": _summarize_indexes(indexes),
        "local_database_roles": sorted(local_roles, key=lambda entry: str(entry["database_id"])),
        "notes": list(classification.get("notes", ())),
    }


def _validate_map(
    *,
    route_inventory: dict[str, Any],
    store_ids: set[str],
    usage: dict[str, dict[str, list[dict[str, Any]]]],
    manifest_store_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if route_inventory.get("runtime_use") is not False:
        errors.append("Route mutation inventory must have runtime_use=false.")
    for source in SOURCE_PATHS:
        if not (ROOT / source).exists():
            errors.append(f"Source path is missing: {source}")
    observed_route_stores = set(usage)
    missing_route_stores = observed_route_stores - store_ids
    if missing_route_stores:
        errors.append(f"Route inventory stores are missing from storage map: {sorted(missing_route_stores)}")
    missing_manifest_stores = manifest_store_ids - store_ids
    if missing_manifest_stores:
        errors.append(f"Manifest stores are missing from storage map: {sorted(missing_manifest_stores)}")
    unclassified = sorted(store_id for store_id in store_ids if store_id not in STORE_CLASSIFICATIONS)
    if unclassified:
        errors.append(f"Observed stores need explicit classification: {unclassified}")
    if usage.get("sqlite_tracked_positions_test_legacy", {}).get("active_browser"):
        errors.append("sqlite_tracked_positions_test_legacy must not have active browser route usage.")
    backend_domain = STORE_CLASSIFICATIONS.get("backend/domain", {})
    if backend_domain.get("persistence") != "virtual":
        errors.append("backend/domain must stay classified as virtual.")
    return errors


def build_storage_ownership_map() -> dict[str, Any]:
    route_inventory = _load_json(ROUTE_INVENTORY_PATH)
    migrations = [dict(entry) for entry in migration_manifest()]
    constraints = [dict(entry) for entry in constraint_manifest()]
    indexes = [dict(entry) for entry in index_manifest()]
    local_roles = [dict(entry) for entry in local_database_manifest()]
    route_parity = [dict(entry) for entry in route_parity_manifest()]
    record_parity = [dict(entry) for entry in record_parity_manifest()]

    usage = _route_usage(route_inventory)
    migrations_by_store = _group_by(migrations, "store_id")
    constraints_by_store = _group_by(constraints, "store_id")
    indexes_by_store = _group_by(indexes, "store_id")
    local_roles_by_store = _group_by(local_roles, "store_id")

    manifest_store_ids = (
        set(migrations_by_store)
        | set(constraints_by_store)
        | set(indexes_by_store)
        | set(local_roles_by_store)
    )
    store_ids = set(STORE_CLASSIFICATIONS) | set(usage) | manifest_store_ids

    validation_errors = _validate_map(
        route_inventory=route_inventory,
        store_ids=store_ids,
        usage=usage,
        manifest_store_ids=manifest_store_ids,
    )

    stores = [
        _build_store(
            store_id,
            usage=usage,
            migrations_by_store=migrations_by_store,
            constraints_by_store=constraints_by_store,
            indexes_by_store=indexes_by_store,
            local_roles_by_store=local_roles_by_store,
        )
        for store_id in sorted(store_ids)
    ]

    return {
        "artifact": "storage_ownership_map",
        "map_version": 1,
        "generated_by": "scripts/generate_storage_ownership_map.py",
        "runtime_use": False,
        "scope": "Generated readability and drift-check map for route, repository, local DB, artifact, and virtual storage ownership.",
        "sources": _source_paths(),
        "non_goals": list(NON_GOALS),
        "stores": stores,
        "route_store_references": _route_store_references(usage),
        "tracked_suggested_parity": {
            "route_parity": route_parity,
            "record_boundaries": [
                entry
                for entry in record_parity
                if entry["parity_id"]
                in {
                    "store_and_record_class_split",
                    "tracked_only_proof_fields",
                    "tracked_only_lifecycle_event_persistence",
                    "tracked_only_profit_readbacks",
                    "suggested_trade_paper_boundary",
                }
            ],
        },
        "validation": {"errors": validation_errors},
    }


def render_json(storage_map: dict[str, Any]) -> str:
    return json.dumps(storage_map, indent=2, sort_keys=True) + "\n"


def _md_cell(value: Any) -> str:
    if value in (None, ""):
        return "none"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value) or "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(storage_map: dict[str, Any]) -> str:
    lines = [
        "# Storage Ownership Map",
        "",
        "Generated by `scripts/generate_storage_ownership_map.py`. Do not hand-edit this file.",
        "",
        "This map is readability and drift-check metadata only. `runtime_use` is `false`: it does not open databases, run audits, migrate schemas, change routes, or define proof/scanner/replay behavior.",
        "",
        "JSON sibling: `data/contracts/storage-ownership-map.json`",
        "",
        "## How To Read This",
        "",
        "Use this map to find the owner document or module for a store before changing routes, repositories, generated artifacts, local database rules, or proof-adjacent readbacks.",
        "Detailed rules remain in the owner manifests and docs listed under each store.",
        "",
        "## Sources",
        "",
    ]
    lines.extend(f"- `{source}`" for source in storage_map["sources"])
    lines.extend(
        [
            "",
            "## Store Summary",
            "",
            "| Store | Role | Persistence | Scope | Location | Active routes | Backend-only routes | Owner docs |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for store in storage_map["stores"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(store["store_id"]),
                    _md_cell(store["storage_role"]),
                    _md_cell(store["persistence"]),
                    _md_cell(store["scope"]),
                    _md_cell(store["location"]),
                    _md_cell(len(store["route_references"]["active_browser"])),
                    _md_cell(len(store["route_references"]["backend_only"])),
                    _md_cell(store["owner_docs"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Repository-Backed Stores", ""])
    for store in storage_map["stores"]:
        if store["storage_role"] not in {"active_repository", "test_legacy_repository"}:
            continue
        lines.extend(
            [
                f"### {store['store_id']}",
                "",
                f"- Role: {store['production_role']}",
                f"- Location: `{store['location']}`",
                f"- Route contracts: `{', '.join(store['route_contract_ids']) or 'none'}`",
                f"- Tables: `{', '.join(store['tables']) or 'none'}`",
                f"- Migrations: `{', '.join(entry['migration_id'] for entry in store['repository_migrations']) or 'none'}`",
                f"- Constraint groups: `{', '.join(store['repository_constraints_by_enforcement']) or 'none'}`",
                f"- Index groups: `{', '.join(store['repository_indexes_by_status']) or 'none'}`",
                "",
            ]
        )
        if store["hard_rules"]:
            lines.append("Hard rules:")
            lines.extend(f"- {rule}" for rule in store["hard_rules"])
            lines.append("")

    lines.extend(
        [
            "## Route Artifact And Virtual Stores",
            "",
            "| Store | Role | Persistence | Active browser routes | Backend-only routes | Boundary |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for store in storage_map["stores"]:
        if store["storage_role"] in {"active_repository", "test_legacy_repository", "out_of_scope_local_db", "separate_lane", "ignored_sidecar_or_backup"}:
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(store["store_id"]),
                    _md_cell(store["storage_role"]),
                    _md_cell(store["persistence"]),
                    _md_cell(len(store["route_references"]["active_browser"])),
                    _md_cell(len(store["route_references"]["backend_only"])),
                    _md_cell(store["hard_rules"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Local Database Roles",
            "",
            "| Store | Database role | Path pattern | Mutability | Audit checks |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for store in storage_map["stores"]:
        for role in store["local_database_roles"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(store["store_id"]),
                        _md_cell(role["database_id"]),
                        _md_cell(role["path_pattern"]),
                        _md_cell(role["mutability"]),
                        _md_cell(role["audit_checks"]),
                    ]
                )
                + " |"
            )

    lines.extend(["", "## Validation", ""])
    errors = storage_map["validation"]["errors"]
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- No validation errors.")

    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- {item}" for item in storage_map["non_goals"])
    lines.append("")
    return "\n".join(lines)


def _check_file(path: Path, expected: str) -> str | None:
    if not path.exists():
        return f"Missing generated artifact: {path.relative_to(ROOT).as_posix()}"
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return f"Generated artifact is stale: {path.relative_to(ROOT).as_posix()}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the storage ownership map.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale.")
    args = parser.parse_args(argv)

    storage_map = build_storage_ownership_map()
    json_text = render_json(storage_map)
    markdown_text = render_markdown(storage_map)

    if args.check:
        errors = [
            error
            for error in (
                _check_file(JSON_OUTPUT_PATH, json_text),
                _check_file(MD_OUTPUT_PATH, markdown_text),
            )
            if error
        ]
        errors.extend(storage_map["validation"]["errors"])
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(json_text, encoding="utf-8")
    MD_OUTPUT_PATH.write_text(markdown_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
