from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTE_INVENTORY_PATH = ROOT / "data" / "contracts" / "route-mutation-inventory.json"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "backend-route-ownership-map.json"
MD_OUTPUT_PATH = ROOT / "docs" / "backend-route-ownership-map.md"
GENERATOR = "scripts/generate_backend_route_ownership_map.py"

ROUTE_ADAPTER_FILES = (
    "python-backend/main.py",
    "python-backend/profile_routes.py",
    "python-backend/predictions_routes.py",
    "python-backend/tools_routes.py",
)
SUPPORT_MODULES = (
    "python-backend/backend_route_context.py",
    "python-backend/proof_summary_service.py",
    "python-backend/replay_profit_service.py",
)
HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

NON_GOALS = (
    "Does not import or introspect the running FastAPI app.",
    "Does not define route behavior, payloads, response schemas, auth semantics, proof predicates, scanner policy, replay math, DB schema, or frontend behavior.",
    "Does not replace route parity, storage ownership, proof contracts, API contracts, or generated artifact governance.",
    "Does not refactor main.py or extracted routers.",
    "Does not reopen crypto, Polymarket, day-trading, or AI commodity browser lanes.",
)

MODULE_MANIFEST: dict[str, dict[str, Any]] = {
    "python-backend/main.py": {
        "role": "fastapi_composition_root",
        "adapter_kind": "main_inline_route_adapter",
        "dependency_style": "module_globals_and_backend_route_context",
        "owner_summary": "FastAPI app setup, middleware, router mounting, report caches, and remaining inline route adapters.",
        "owner_docs": ("docs/architecture-overview.md", "docs/api-and-storage.md"),
    },
    "python-backend/profile_routes.py": {
        "role": "extracted_router",
        "adapter_kind": "extracted_router",
        "router_factory": "create_profile_router",
        "dependency_style": "explicit_dependency_injection",
        "owner_summary": "Profile, profiles, changelog, and risk settings routes.",
        "owner_docs": ("docs/architecture-overview.md", "docs/api-and-storage.md"),
    },
    "python-backend/predictions_routes.py": {
        "role": "extracted_router",
        "adapter_kind": "extracted_router",
        "router_factory": "create_predictions_router",
        "dependency_style": "BackendRouteContext",
        "owner_summary": "Prediction history read/grade/delete routes.",
        "owner_docs": ("docs/architecture-overview.md", "docs/api-and-storage.md"),
    },
    "python-backend/tools_routes.py": {
        "role": "extracted_router",
        "adapter_kind": "extracted_router",
        "router_factory": "create_tools_router",
        "dependency_style": "BackendRouteContext",
        "owner_summary": "Operator-gated backend tool dispatch route.",
        "owner_docs": ("docs/architecture-overview.md", "docs/api-and-storage.md"),
    },
    "python-backend/backend_route_context.py": {
        "role": "support_context",
        "adapter_kind": "support_module",
        "dependency_style": "late_bound_namespace",
        "owner_summary": "Late-bound access to the loaded backend module namespace for extracted routers and services.",
        "owner_docs": ("docs/architecture-overview.md", "docs/api-and-storage.md"),
    },
    "python-backend/proof_summary_service.py": {
        "role": "application_service",
        "adapter_kind": "decorator_free_service",
        "dependency_style": "BackendRouteContext",
        "owner_summary": "Decorator-free proof-summary workflow assembly.",
        "owner_docs": ("docs/proof-evidence-contract.md", "docs/api-and-storage.md"),
    },
    "python-backend/replay_profit_service.py": {
        "role": "application_service",
        "adapter_kind": "decorator_free_service",
        "dependency_style": "BackendRouteContext",
        "owner_summary": "Decorator-free replay/profit readback assembly.",
        "owner_docs": ("docs/replay-profit-contract.md", "docs/api-and-storage.md"),
    },
}

ROUTER_MOUNTS = (
    {
        "router_factory": "create_profile_router",
        "router_module": "python-backend/profile_routes.py",
        "mounted_in": "python-backend/main.py",
        "dependency_style": "explicit_dependency_injection",
    },
    {
        "router_factory": "create_tools_router",
        "router_module": "python-backend/tools_routes.py",
        "mounted_in": "python-backend/main.py",
        "dependency_style": "BackendRouteContext",
    },
    {
        "router_factory": "create_predictions_router",
        "router_module": "python-backend/predictions_routes.py",
        "mounted_in": "python-backend/main.py",
        "dependency_style": "BackendRouteContext",
    },
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


class _FastApiRouteVisitor(ast.NodeVisitor):
    def __init__(self, source_path: str):
        self.source_path = source_path
        self.function_stack: list[str] = []
        self.routes: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            route = self._route_from_decorator(decorator)
            if route:
                route.update(
                    {
                        "handler": node.name,
                        "declared_in": self.source_path,
                        "line": route.pop("decorator_line"),
                        "router_factory": self.function_stack[-1] if self.function_stack else None,
                    }
                )
                self.routes.append(route)
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def _route_from_decorator(self, decorator: ast.AST) -> dict[str, Any] | None:
        if not isinstance(decorator, ast.Call):
            return None
        func = decorator.func
        if not isinstance(func, ast.Attribute):
            return None
        method = func.attr.lower()
        if method not in HTTP_METHODS:
            return None
        if not decorator.args:
            return None
        path_arg = decorator.args[0]
        if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
            return None
        registration = "unknown"
        if isinstance(func.value, ast.Name) and func.value.id == "app":
            registration = "direct_app"
        elif isinstance(func.value, ast.Name) and func.value.id == "router":
            registration = "included_router"
        return {
            "method": method.upper(),
            "path": path_arg.value,
            "registration": registration,
            "decorator_line": getattr(decorator, "lineno", 0),
        }


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def discover_fastapi_routes() -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for relative_path in ROUTE_ADAPTER_FILES:
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        visitor = _FastApiRouteVisitor(relative_path)
        visitor.visit(tree)
        discovered.extend(visitor.routes)
    return sorted(discovered, key=lambda route: (route["declared_in"], route["line"], route["method"], route["path"]))


def _load_route_inventory() -> dict[str, Any]:
    return json.loads(ROUTE_INVENTORY_PATH.read_text(encoding="utf-8"))


def _inventory_maps(route_inventory: dict[str, Any]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    mounted: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    excluded_next_only: list[dict[str, Any]] = []
    for route in route_inventory.get("mounted_browser_routes", []):
        if route.get("next_only"):
            excluded_next_only.append(route)
            continue
        mounted[(str(route["method"]), str(route["fastapi_path"]))].append(route)
    backend_only = {
        (str(route["method"]), str(route["path"])): route
        for route in route_inventory.get("backend_only_routes", [])
    }
    return dict(mounted), backend_only, excluded_next_only


def _module_info(relative_path: str, route_count_by_module: dict[str, int]) -> dict[str, Any]:
    info = dict(MODULE_MANIFEST[relative_path])
    info["path"] = relative_path
    info["imports_main"] = bool(re.search(r"(?m)^\s*(?:import\s+main|from\s+main\s+import)\b", _read(relative_path)))
    info["route_count"] = route_count_by_module.get(relative_path, 0)
    return info


def _route_inventory_fields(route: dict[str, Any] | None, *, surface: str) -> dict[str, Any]:
    if not route:
        return {
            "surface": "unknown",
            "next_routes": [],
            "lifecycle": "unknown",
            "auth_boundary": "unknown",
            "mutating": None,
            "store": "unknown",
            "record_class": "unknown",
            "contract_ids": [],
            "route_group": "unknown",
        }
    if surface == "mounted_browser":
        return {
            "surface": surface,
            "next_routes": [
                {
                    "browser_path": route["browser_path"],
                    "next_path": route["next_path"],
                    "route_group": route["route_group"],
                    "contract_ids": route.get("contract_ids", []),
                }
            ],
            "lifecycle": route["lifecycle"],
            "auth_boundary": route["auth_boundary"],
            "mutating": route["mutating"],
            "store": ", ".join(route.get("stores", [])) or "none",
            "record_class": ", ".join(route.get("record_classes", [])) or "none",
            "contract_ids": route.get("contract_ids", []),
            "route_group": route["route_group"],
        }
    return {
        "surface": surface,
        "next_routes": [],
        "lifecycle": route["lifecycle"],
        "auth_boundary": route["auth_boundary"],
        "mutating": route["mutating"],
        "store": route["store"],
        "record_class": route["record_class"],
        "contract_ids": [route["contract_id"]],
        "route_group": "Backend-Only FastAPI",
    }


def _family_for(path: str) -> dict[str, Any]:
    if path.startswith("/api/positions"):
        return {
            "route_family": "trading_desk_positions",
            "owner_docs": ("docs/api-and-storage.md", "docs/repository-contract.md", "docs/trading-desk-record-parity.md", "docs/scanner-creation-safety-contract.md"),
            "delegate_modules": ("python-backend/positions_service.py", "python-backend/positions_repository.py"),
            "domain_owners": ("python-backend/proof_contract.py",),
            "deferred_split": True,
        }
    if path.startswith("/api/suggested-trades"):
        return {
            "route_family": "suggested_trades",
            "owner_docs": ("docs/api-and-storage.md", "docs/repository-contract.md", "docs/trading-desk-record-parity.md", "docs/scanner-creation-safety-contract.md"),
            "delegate_modules": ("python-backend/positions_service.py", "python-backend/suggested_trades_repository.py"),
            "domain_owners": ("python-backend/proof_contract.py",),
            "deferred_split": True,
        }
    if path == "/api/proof-summary":
        return {
            "route_family": "proof_summary",
            "owner_docs": ("docs/proof-evidence-contract.md", "docs/api-and-storage.md"),
            "delegate_modules": ("python-backend/proof_summary_service.py",),
            "domain_owners": ("python-backend/proof_contract.py",),
            "deferred_split": False,
        }
    if path.startswith("/api/backtest"):
        service_modules = ("python-backend/replay_profit_service.py",) if path != "/api/backtest" else ()
        return {
            "route_family": "replay_profit",
            "owner_docs": ("docs/replay-profit-contract.md", "docs/api-and-storage.md"),
            "delegate_modules": service_modules,
            "domain_owners": ("wfo_optimizer.py", "metric_truth_audit.py"),
            "deferred_split": True,
        }
    if path.startswith("/api/scan"):
        return {
            "route_family": "scanner",
            "owner_docs": ("docs/scanner-creation-safety-contract.md", "docs/api-and-storage.md"),
            "delegate_modules": ("forward_options_ledger.py",),
            "domain_owners": ("supervised_scan.py", "options_chatbot.py"),
            "deferred_split": True,
        }
    if path in {"/api/profile", "/api/profiles", "/api/changelog", "/api/risk"}:
        return {
            "route_family": "profile",
            "owner_docs": ("docs/api-and-storage.md", "docs/architecture-overview.md"),
            "delegate_modules": (),
            "domain_owners": ("options_chatbot.py",),
            "deferred_split": False,
        }
    if path.startswith("/api/predictions"):
        return {
            "route_family": "predictions",
            "owner_docs": ("docs/api-and-storage.md", "docs/route-lifecycle-contracts.md"),
            "delegate_modules": (),
            "domain_owners": ("options_chatbot.py",),
            "deferred_split": False,
        }
    if path.startswith("/api/tools"):
        return {
            "route_family": "tools",
            "owner_docs": ("docs/api-and-storage.md", "docs/route-parity.md"),
            "delegate_modules": (),
            "domain_owners": ("python-backend/main.py",),
            "deferred_split": False,
        }
    if path == "/api/options-profit/status":
        return {
            "route_family": "options_profit_status",
            "owner_docs": ("docs/replay-profit-contract.md", "docs/api-and-storage.md"),
            "delegate_modules": (),
            "domain_owners": ("options_profit_gate.py", "options_profit_flywheel.py"),
            "deferred_split": True,
        }
    if path.startswith("/api/market-data") or path == "/api/sectors":
        return {
            "route_family": "market_data",
            "owner_docs": ("docs/api-and-storage.md", "docs/storage-ownership-map.md"),
            "delegate_modules": (),
            "domain_owners": ("market_data_service",),
            "deferred_split": True,
        }
    if path in {"/api/health", "/api/daily-performance"}:
        return {
            "route_family": "status",
            "owner_docs": ("docs/api-and-storage.md", "docs/architecture-overview.md"),
            "delegate_modules": (),
            "domain_owners": ("python-backend/main.py",),
            "deferred_split": True,
        }
    return {
        "route_family": "unclassified",
        "owner_docs": ("docs/api-and-storage.md",),
        "delegate_modules": (),
        "domain_owners": (),
        "deferred_split": True,
    }


def _build_route_entry(
    discovered_route: dict[str, Any],
    mounted_by_backend: dict[tuple[str, str], list[dict[str, Any]]],
    backend_only_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    key = (discovered_route["method"], discovered_route["path"])
    mounted_routes = mounted_by_backend.get(key, [])
    backend_only_route = backend_only_by_key.get(key)
    if mounted_routes:
        inventory = _route_inventory_fields(mounted_routes[0], surface="mounted_browser")
        if len(mounted_routes) > 1:
            inventory["next_routes"] = [
                {
                    "browser_path": route["browser_path"],
                    "next_path": route["next_path"],
                    "route_group": route["route_group"],
                    "contract_ids": route.get("contract_ids", []),
                }
                for route in mounted_routes
            ]
    else:
        inventory = _route_inventory_fields(backend_only_route, surface="backend_only" if backend_only_route else "unknown")

    module = MODULE_MANIFEST[discovered_route["declared_in"]]
    family = _family_for(discovered_route["path"])
    return {
        "method": discovered_route["method"],
        "path": discovered_route["path"],
        "handler": discovered_route["handler"],
        "declared_in": discovered_route["declared_in"],
        "line": discovered_route["line"],
        "registration": discovered_route["registration"],
        "router_factory": discovered_route["router_factory"],
        "adapter_kind": module["adapter_kind"],
        "dependency_style": module["dependency_style"],
        "surface": inventory["surface"],
        "next_routes": inventory["next_routes"],
        "route_group": inventory["route_group"],
        "route_family": family["route_family"],
        "lifecycle": inventory["lifecycle"],
        "auth_boundary": inventory["auth_boundary"],
        "mutating": inventory["mutating"],
        "store": inventory["store"],
        "record_class": inventory["record_class"],
        "contract_ids": inventory["contract_ids"],
        "adapter_owner_module": discovered_route["declared_in"],
        "delegate_modules": list(family["delegate_modules"]),
        "domain_owners": list(family["domain_owners"]),
        "owner_docs": list(family["owner_docs"]),
        "deferred_split": family["deferred_split"],
        "does_not_own": [
            "route payload semantics",
            "auth behavior",
            "proof/scanner/replay semantics",
            "database schema or migrations",
            "frontend behavior",
        ],
    }


def _path_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def _validate_map(backend_map: dict[str, Any], route_inventory: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    routes = backend_map["routes"]
    route_keys = [(route["method"], route["path"]) for route in routes]
    duplicate_keys = sorted({key for key in route_keys if route_keys.count(key) > 1})
    if duplicate_keys:
        errors.append(f"Duplicate backend route ownership entries: {duplicate_keys}")
    discovered_keys = {(route["method"], route["path"]) for route in discover_fastapi_routes()}
    if set(route_keys) != discovered_keys:
        errors.append("Backend route ownership entries do not match static FastAPI decorator discovery.")
    mounted_by_backend, backend_only_by_key, excluded_next_only = _inventory_maps(route_inventory)
    inventory_keys = set(mounted_by_backend) | set(backend_only_by_key)
    missing_inventory_keys = sorted(inventory_keys - set(route_keys))
    extra_route_keys = sorted(set(route_keys) - inventory_keys)
    if missing_inventory_keys:
        errors.append(f"Route inventory entries missing backend ownership: {missing_inventory_keys}")
    if extra_route_keys:
        errors.append(f"Backend routes missing from route inventory: {extra_route_keys}")
    if not excluded_next_only:
        errors.append("Next-only operator session routes must be explicitly excluded from backend ownership.")
    if route_inventory.get("runtime_use") is not False:
        errors.append("Route mutation inventory must be non-runtime.")
    if route_inventory.get("validation", {}).get("errors"):
        errors.append(f"Route mutation inventory has validation errors: {route_inventory['validation']['errors']}")

    main_text = _read("python-backend/main.py")
    for mount in backend_map["router_mounts"]:
        if mount["router_factory"] not in main_text or "app.include_router" not in main_text:
            errors.append(f"Router factory is not mounted from main.py: {mount['router_factory']}")

    for module in backend_map["modules"]:
        if not _path_exists(module["path"]):
            errors.append(f"Backend ownership module path is missing: {module['path']}")
        for owner_doc in module["owner_docs"]:
            if not _path_exists(owner_doc):
                errors.append(f"Backend ownership module owner doc is missing: {owner_doc}")
        if module["role"] in {"extracted_router", "application_service", "support_context"} and module["imports_main"]:
            errors.append(f"{module['path']} must not import canonical main.py")
        if module["role"] in {"application_service", "support_context"} and module["route_count"] != 0:
            errors.append(f"{module['path']} must stay decorator-free.")

    for route in routes:
        if route["surface"] == "unknown":
            errors.append(f"Backend route has unknown surface: {route['method']} {route['path']}")
        if route["route_family"] == "unclassified":
            errors.append(f"Backend route is unclassified: {route['method']} {route['path']}")
        for owner_doc in route["owner_docs"]:
            if not _path_exists(owner_doc):
                errors.append(f"Route owner doc is missing for {route['method']} {route['path']}: {owner_doc}")
        for owner_path in [*route["delegate_modules"], *route["domain_owners"]]:
            if owner_path == "market_data_service":
                continue
            if not _path_exists(owner_path):
                errors.append(f"Route owner path is missing for {route['method']} {route['path']}: {owner_path}")
        if route["registration"] == "included_router" and route["adapter_kind"] != "extracted_router":
            errors.append(f"Included router route is mislabeled: {route['method']} {route['path']}")
        if route["registration"] == "direct_app" and route["declared_in"] != "python-backend/main.py":
            errors.append(f"Direct app route is outside main.py: {route['method']} {route['path']}")

    return errors


def build_backend_route_ownership_map() -> dict[str, Any]:
    route_inventory = _load_route_inventory()
    mounted_by_backend, backend_only_by_key, excluded_next_only = _inventory_maps(route_inventory)
    discovered_routes = discover_fastapi_routes()
    route_count_by_module: dict[str, int] = defaultdict(int)
    for route in discovered_routes:
        route_count_by_module[route["declared_in"]] += 1
    routes = [
        _build_route_entry(route, mounted_by_backend, backend_only_by_key)
        for route in discovered_routes
    ]
    modules = [_module_info(path, route_count_by_module) for path in [*ROUTE_ADAPTER_FILES, *SUPPORT_MODULES]]
    backend_map = {
        "artifact": "backend_route_ownership_map",
        "map_version": 1,
        "generated_by": GENERATOR,
        "runtime_use": False,
        "scope": "Generated readability and drift-check map for FastAPI route adapter ownership, router extraction state, service delegation, and backend-only surfaces.",
        "sources": [
            "data/contracts/route-mutation-inventory.json",
            *ROUTE_ADAPTER_FILES,
            *SUPPORT_MODULES,
        ],
        "non_goals": list(NON_GOALS),
        "modules": modules,
        "router_mounts": [dict(mount) for mount in ROUTER_MOUNTS],
        "excluded_next_only_routes": [
            {
                "method": route["method"],
                "browser_path": route["browser_path"],
                "next_path": route["next_path"],
                "reason": route["next_only_reason"],
            }
            for route in excluded_next_only
        ],
        "routes": routes,
        "validation": {"errors": []},
    }
    backend_map["validation"]["errors"] = _validate_map(backend_map, route_inventory)
    return backend_map


def render_json(backend_map: dict[str, Any]) -> str:
    return json.dumps(backend_map, indent=2, sort_keys=True) + "\n"


def _md_cell(value: Any) -> str:
    if value in (None, ""):
        return "none"
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value) or "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(backend_map: dict[str, Any]) -> str:
    lines = [
        "# Backend Route Ownership Map",
        "",
        f"Generated by `{GENERATOR}`. Do not hand-edit this file.",
        "",
        "Runtime use: `false`.",
        "JSON sibling: `data/contracts/backend-route-ownership-map.json`.",
        "",
        "This map is static readability and drift-check metadata. Use it to find the FastAPI adapter module, extraction state, service/domain owner, route inventory classification, and owner docs for a backend route before editing code.",
        "",
        "## How To Read This",
        "",
        "- `main_inline_route_adapter` means the FastAPI decorator still lives directly in `python-backend/main.py`.",
        "- `extracted_router` means the decorator lives in a router module mounted by `main.py`.",
        "- Service modules are listed as delegation/support owners, not route adapters.",
        "- Auth, lifecycle, store, and record-class fields are copied from `data/contracts/route-mutation-inventory.json`.",
        "",
        "## Module Roles",
        "",
        "| Module | Role | Adapter kind | Dependency style | Routes | Owner summary |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for module in backend_map["modules"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(module["path"]),
                    _md_cell(module["role"]),
                    _md_cell(module["adapter_kind"]),
                    _md_cell(module["dependency_style"]),
                    _md_cell(module["route_count"]),
                    _md_cell(module["owner_summary"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Router Mounts", "", "| Router factory | Module | Mounted in | Dependency style |", "| --- | --- | --- | --- |"])
    for mount in backend_map["router_mounts"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(mount["router_factory"]),
                    _md_cell(mount["router_module"]),
                    _md_cell(mount["mounted_in"]),
                    _md_cell(mount["dependency_style"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Route Ownership",
            "",
            "| FastAPI route | Surface | Adapter | Handler | Family | Lifecycle | Auth | Store | Delegates / domain owners | Owner docs |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for route in backend_map["routes"]:
        delegates = [*route["delegate_modules"], *route["domain_owners"]]
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(f"{route['method']} {route['path']}"),
                    _md_cell(route["surface"]),
                    _md_cell(f"{route['adapter_owner_module']}:{route['line']} ({route['adapter_kind']})"),
                    _md_cell(route["handler"]),
                    _md_cell(route["route_family"]),
                    _md_cell(route["lifecycle"]),
                    _md_cell(route["auth_boundary"]),
                    _md_cell(route["store"]),
                    _md_cell(delegates),
                    _md_cell(route["owner_docs"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Next-Only Exclusions", ""])
    for route in backend_map["excluded_next_only_routes"]:
        lines.append(f"- `{route['method']} {route['browser_path']}` in `{route['next_path']}`: {route['reason']}")

    lines.extend(["", "## Validation", ""])
    errors = backend_map["validation"]["errors"]
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- No validation errors.")

    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- {item}" for item in backend_map["non_goals"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate backend route ownership map artifacts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated backend route ownership artifacts are stale.")
    args = parser.parse_args()

    backend_map = build_backend_route_ownership_map()
    rendered_json = render_json(backend_map)
    rendered_md = render_markdown(backend_map)

    if args.check:
        errors: list[str] = []
        for path, rendered in ((JSON_OUTPUT_PATH, rendered_json), (MD_OUTPUT_PATH, rendered_md)):
            if not path.exists():
                errors.append(f"{_relative(path)} is missing; run this script without --check.")
            elif path.read_text(encoding="utf-8") != rendered:
                errors.append(f"{_relative(path)} is out of date; run this script without --check.")
        errors.extend(backend_map["validation"]["errors"])
        if errors:
            for error in errors:
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
