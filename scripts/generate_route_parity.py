from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_API_ROOT = ROOT / "src" / "app" / "api"
FASTAPI_MAIN = ROOT / "python-backend" / "main.py"
FASTAPI_ROUTE_FILES = tuple(sorted((ROOT / "python-backend").glob("*.py")))
OUTPUT_PATH = ROOT / "docs" / "route-parity.md"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "route-mutation-inventory.json"
TRADING_DESK_CONTRACTS_PATH = ROOT / "src" / "lib" / "trading-desk" / "storeOwnership.ts"
STRATEGY_LAB_CONTRACTS_PATH = ROOT / "src" / "lib" / "strategy-lab" / "replayIntent.ts"
OPTIONS_ROUTE_CONTRACTS_PATH = ROOT / "src" / "lib" / "route-lifecycle" / "routeContracts.ts"
CLIENT_FETCH_ROOTS = (ROOT / "src" / "components",)

ROUTE_INVENTORY_NON_GOALS = (
    "Does not define API behavior, route payload shape, response schema, auth behavior, proof semantics, scanner policy, or DB schema.",
    "Does not replace OpenAPI, JSON Schema, TypeScript contracts, or Pydantic models.",
    "Does not replace the future storage ownership map.",
    "Does not replace generated artifact governance or stale-artifact checks beyond this route inventory freshness check.",
    "Does not reopen crypto, Polymarket, day-trading, or AI commodity browser routes.",
)

HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")
MUTATING_METHODS = ("POST", "PUT", "DELETE", "PATCH")

GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Operator Auth", ("/api/operator",)),
    ("Scan And Truth Diagnostics", ("/api/scan", "/api/backtest")),
    (
        "Profiles, Predictions, And Status",
        ("/api/profile", "/api/changelog", "/api/predictions", "/api/risk-settings", "/api/options-profit")),
    ("Tracked Positions", ("/api/positions",)),
    ("Suggested Trades", ("/api/suggested-trades",)),
    ("Support", ("/api/sectors", "/api/tools")),
]
GROUP_NAMES = tuple(group for group, _prefixes in GROUPS) + ("Other",)

FASTAPI_OVERRIDES = {
    ("GET", "/api/risk-settings"): "/api/risk",
    ("POST", "/api/tools/[name]"): "/api/tools/{tool_name}",
    ("POST", "/api/positions/[id]/close"): "/api/positions/{position_id}/close",
    ("POST", "/api/suggested-trades/[id]/close"): "/api/suggested-trades/{position_id}/close",
}

NEXT_ONLY_ROUTES = {
    ("GET", "/api/operator/session"): "local operator session status",
    ("POST", "/api/operator/session"): "local operator session unlock",
}

NEXT_LIFECYCLE_OVERRIDES = {
    ("POST", "/api/scan"): "live_scan_run",
    ("POST", "/api/predictions/grade"): "prediction_grade",
    ("POST", "/api/tools/[name]"): "tool_dispatch",
    ("GET", "/api/operator/session"): "operator_session_status",
    ("POST", "/api/operator/session"): "operator_session_unlock",
}

BACKEND_ONLY_LIFECYCLE_OVERRIDES = {
    ("DELETE", "/api/predictions/{pred_id}"): "prediction_delete",
    ("POST", "/api/scan/recommendations"): "position_recommendation_support",
    ("POST", "/api/scan/roll"): "scan_roll_forward_write",
    ("POST", "/api/market-data/cache-stats/reset"): "market_data_cache_reset",
    ("POST", "/api/backtest/archived-forward"): "archived_forward_replay_run",
    ("POST", "/api/backtest/experiments"): "research_experiment_run",
}

NEXT_ROUTE_ORDER = {
    ("POST", "/api/scan"): 10,
    ("POST", "/api/backtest"): 20,
    ("GET", "/api/backtest/summary"): 30,
    ("GET", "/api/backtest/last"): 40,
    ("GET", "/api/backtest/live-policy"): 50,
    ("GET", "/api/backtest/report"): 60,
    ("GET", "/api/backtest/metric-truth"): 70,
    ("GET", "/api/backtest/comparison"): 80,
    ("GET", "/api/backtest/forward-evidence"): 90,
    ("GET", "/api/backtest/exit-audit"): 100,
    ("GET", "/api/profile"): 110,
    ("PUT", "/api/profile"): 120,
    ("GET", "/api/changelog"): 130,
    ("GET", "/api/predictions"): 140,
    ("POST", "/api/predictions/grade"): 150,
    ("GET", "/api/risk-settings"): 160,
    ("GET", "/api/options-profit/status"): 170,
    ("GET", "/api/operator/session"): 180,
    ("POST", "/api/operator/session"): 190,
    ("GET", "/api/positions"): 200,
    ("POST", "/api/positions"): 210,
    ("POST", "/api/positions/review"): 220,
    ("POST", "/api/positions/[id]/close"): 230,
    ("GET", "/api/suggested-trades"): 240,
    ("POST", "/api/suggested-trades"): 250,
    ("POST", "/api/suggested-trades/review"): 260,
    ("POST", "/api/suggested-trades/[id]/close"): 270,
    ("GET", "/api/sectors"): 280,
    ("POST", "/api/tools/[name]"): 290,
}


@dataclass(frozen=True)
class NextRoute:
    method: str
    browser_path: str
    next_path: str
    fastapi_path: str


@dataclass(frozen=True)
class FastApiRoute:
    method: str
    path: str


@dataclass(frozen=True)
class ClientFetch:
    source_path: str
    browser_path: str
    absolute_url: bool = False


@dataclass(frozen=True)
class RouteContractMetadata:
    id: str
    method: str
    family: str
    route: str
    store: str
    lifecycle: str
    record_class: str
    owner: str


@dataclass(frozen=True)
class RouteAccessContract:
    lifecycle: str
    auth_boundary: str
    intent: str
    contract_id: str
    store: str
    record_class: str
    owner: str


def _to_browser_path(route_file: Path) -> str:
    parts = route_file.relative_to(NEXT_API_ROOT).parent.parts
    return "/api" + ("/" + "/".join(parts) if parts else "")


def _extract_next_methods(route_file: Path) -> list[str]:
    text = route_file.read_text(encoding="utf-8")
    return [method for method in HTTP_METHODS if re.search(rf"export\s+async\s+function\s+{method}\b", text)]


def _normalize_fastapi_path(method: str, browser_path: str) -> str:
    override = FASTAPI_OVERRIDES.get((method, browser_path))
    if override:
        return override
    return re.sub(r"\[([^\]]+)\]", r"{\1}", browser_path)


def _route_file_for(next_route: NextRoute) -> Path:
    return ROOT / next_route.next_path


def _read_route_source(next_route: NextRoute) -> str:
    route_file = _route_file_for(next_route)
    if not route_file.exists():
        return ""
    return route_file.read_text(encoding="utf-8")


def _extract_method_body(source: str, method: str) -> str:
    match = re.search(rf"export\s+async\s+function\s+{method}\b[\s\S]*?\)\s*\{{", source)
    if not match:
        return ""
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _split_inventory_values(value: str) -> list[str]:
    if not value or value == "none":
        return []
    return [part.strip() for part in value.split(", ") if part.strip()]


def _extract_contract_metadata(path: Path, family: str) -> dict[str, RouteContractMetadata]:
    if not path.exists():
        return {}
    source = path.read_text(encoding="utf-8")
    contracts: dict[str, RouteContractMetadata] = {}
    pattern = re.compile(r"^\s{2}([A-Za-z0-9_]+):\s*\{(.*?)^\s{2}\},", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(source):
        contract_id = match.group(1)
        body = match.group(2)

        def field(name: str) -> str:
            field_match = re.search(rf"\b{name}:\s*\"([^\"]*)\"", body)
            return field_match.group(1) if field_match else ""

        contracts[contract_id] = RouteContractMetadata(
            id=contract_id,
            method=field("method"),
            family=family,
            route=field("route"),
            store=field("store"),
            lifecycle=field("lifecycle"),
            record_class=field("recordClass"),
            owner=field("owner"),
        )
    return contracts


def load_route_contract_metadata() -> dict[str, RouteContractMetadata]:
    contracts: dict[str, RouteContractMetadata] = {}
    contracts.update(_extract_contract_metadata(TRADING_DESK_CONTRACTS_PATH, "trading_desk"))
    contracts.update(_extract_contract_metadata(STRATEGY_LAB_CONTRACTS_PATH, "strategy_lab"))
    contracts.update(_extract_contract_metadata(OPTIONS_ROUTE_CONTRACTS_PATH, "options_route"))
    return contracts


def _default_lifecycle(method: str, path: str) -> str:
    override = NEXT_LIFECYCLE_OVERRIDES.get((method, path))
    if override:
        return override
    if method == "GET":
        return "read"
    if method == "DELETE":
        return "delete"
    return "write"


def _contract_compare_path(browser_path: str) -> str:
    return re.sub(r"\[([^\]]+)\]", r"{\1}", browser_path)


def _classify_auth_boundary(route: NextRoute, method_body: str) -> str:
    next_only = NEXT_ONLY_ROUTES.get((route.method, route.browser_path))
    if next_only:
        return "next_only_session"
    if "requireLocalOperator(req)" in method_body:
        return "local_operator"
    if route.method == "GET":
        return "same_origin_read"
    return "missing_local_operator"


def classify_next_route(
    route: NextRoute,
    contract_metadata: dict[str, RouteContractMetadata] | None = None,
) -> RouteAccessContract:
    metadata = contract_metadata or load_route_contract_metadata()
    source = _read_route_source(route)
    method_body = _extract_method_body(source, route.method)
    trading_intents = re.findall(r'requireTradingDeskMutationIntent\(\s*req,\s*"([^"]+)"', method_body)
    strategy_intents = re.findall(r'requireStrategyLabMutationIntent\(\s*req,\s*"([^"]+)"', method_body)
    contract_ids = _unique(
        [
            contract_id
            for helper in (
                "jsonWithTradingDeskStore",
                "jsonWithValidatedTradingDeskStore",
                "jsonWithStrategyLabContract",
                "jsonWithRouteLifecycle",
            )
            for contract_id in re.findall(
                rf'{helper}\([^;]*?,\s*"([^"]+)"',
                method_body,
                flags=re.DOTALL,
            )
        ]
    )
    route_contracts = [metadata[contract_id] for contract_id in contract_ids if contract_id in metadata]

    intent_parts = [
        *(f"x-trading-desk-mutation: {intent}" for intent in _unique(trading_intents)),
        *(f"x-strategy-lab-mutation: {intent}" for intent in _unique(strategy_intents)),
    ]
    lifecycle = ", ".join(_unique([contract.lifecycle for contract in route_contracts if contract.lifecycle]))
    if not lifecycle:
        lifecycle = _default_lifecycle(route.method, route.browser_path)

    return RouteAccessContract(
        lifecycle=lifecycle,
        auth_boundary=_classify_auth_boundary(route, method_body),
        intent=", ".join(intent_parts) or "none",
        contract_id=", ".join(contract_ids) or "none",
        store=", ".join(_unique([contract.store for contract in route_contracts if contract.store])) or "none",
        record_class=", ".join(_unique([contract.record_class for contract in route_contracts if contract.record_class])) or "none",
        owner=", ".join(_unique([contract.owner for contract in route_contracts if contract.owner])) or "backend/domain",
    )


def classify_backend_only_route(route: FastApiRoute) -> RouteAccessContract:
    lifecycle = BACKEND_ONLY_LIFECYCLE_OVERRIDES.get((route.method, route.path))
    if not lifecycle:
        lifecycle = "read" if route.method == "GET" else "backend_write"
    return RouteAccessContract(
        lifecycle=lifecycle,
        auth_boundary="backend_bridge_token_when_configured",
        intent="none",
        contract_id="backend_only",
        store="backend/domain",
        record_class="backend_endpoint",
        owner="python-backend",
    )


def load_next_routes() -> list[NextRoute]:
    routes: list[NextRoute] = []
    for route_file in sorted(NEXT_API_ROOT.rglob("route.ts")):
        browser_path = _to_browser_path(route_file)
        for method in _extract_next_methods(route_file):
            routes.append(
                NextRoute(
                    method=method,
                    browser_path=browser_path,
                    next_path=route_file.relative_to(ROOT).as_posix(),
                    fastapi_path=_normalize_fastapi_path(method, browser_path),
                )
            )
    return sorted(
        routes,
        key=lambda route: (
            NEXT_ROUTE_ORDER.get((route.method, route.browser_path), 9999),
            route.browser_path,
            route.method,
        ),
    )


def load_fastapi_routes() -> list[FastApiRoute]:
    routes: list[FastApiRoute] = []
    pattern = re.compile(r'@(app|router)\.(get|post|put|delete|patch)\("([^"]+)"')
    for route_file in FASTAPI_ROUTE_FILES:
        for line in route_file.read_text(encoding="utf-8").splitlines():
            match = pattern.search(line)
            if match:
                routes.append(FastApiRoute(method=match.group(2).upper(), path=match.group(3)))
    return routes


def _normalize_client_fetch(raw_path: str) -> tuple[str, bool] | None:
    path = raw_path.strip()
    absolute_url = bool(re.match(r"https?://", path))
    if absolute_url:
        api_index = path.find("/api/")
        if api_index < 0:
            return None
        path = path[api_index:]
    if not path.startswith("/api/"):
        return None
    path = re.sub(r"\$\{[^}]+\}", "[param]", path)
    path = path.split("?", 1)[0].split("#", 1)[0]
    return path.rstrip("/") or "/api", absolute_url


def _client_fetch_path(raw_path: str) -> str | None:
    normalized = _normalize_client_fetch(raw_path)
    if not normalized:
        return None
    return normalized[0]


def extract_client_fetch_paths(text: str) -> list[str]:
    pattern = re.compile(r"\b(?:fetch|fetchWithTimeout)\s*\(\s*([\"'`])([^\"'`]+)\1")
    paths: list[str] = []
    for match in pattern.finditer(text):
        path = _client_fetch_path(match.group(2))
        if path:
            paths.append(path)
    return paths


def load_client_fetches() -> list[ClientFetch]:
    fetches: list[ClientFetch] = []
    for source_root in CLIENT_FETCH_ROOTS:
        for source_file in sorted(source_root.rglob("*")):
            if source_file.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            text = source_file.read_text(encoding="utf-8")
            pattern = re.compile(r"\b(?:fetch|fetchWithTimeout)\s*\(\s*([\"'`])([^\"'`]+)\1")
            for match in pattern.finditer(text):
                normalized = _normalize_client_fetch(match.group(2))
                if normalized:
                    path, absolute_url = normalized
                    fetches.append(ClientFetch(source_file.relative_to(ROOT).as_posix(), path, absolute_url))
    return sorted(fetches, key=lambda fetch: (fetch.browser_path, fetch.source_path))


def _route_pattern_matches(pattern_path: str, concrete_path: str) -> bool:
    pattern_parts = pattern_path.strip("/").split("/")
    concrete_parts = concrete_path.strip("/").split("/")
    if len(pattern_parts) != len(concrete_parts):
        return False
    for pattern_part, concrete_part in zip(pattern_parts, concrete_parts):
        pattern_is_dynamic = pattern_part.startswith("[") and pattern_part.endswith("]")
        concrete_is_dynamic = concrete_part.startswith("[") and concrete_part.endswith("]")
        if pattern_is_dynamic or concrete_is_dynamic:
            continue
        if pattern_part != concrete_part:
            return False
    return True


def _group_for(route: NextRoute) -> str:
    for group, prefixes in GROUPS:
        if any(route.browser_path == prefix or route.browser_path.startswith(f"{prefix}/") for prefix in prefixes):
            return group
    return "Other"


def _validation_errors(
    routes: list[NextRoute],
    backend_routes: list[FastApiRoute],
    client_fetches: list[ClientFetch],
) -> list[str]:
    backend_set = {(route.method, route.path) for route in backend_routes}
    mirrored_set = {(route.method, route.fastapi_path) for route in routes}
    missing_backend = [
        route
        for route in routes
        if (route.method, route.browser_path) not in NEXT_ONLY_ROUTES
        and (route.method, route.fastapi_path) not in backend_set
    ]
    browser_paths = {route.browser_path for route in routes}
    missing_client_fetches = [
        fetch
        for fetch in client_fetches
        if not any(_route_pattern_matches(route_path, fetch.browser_path) for route_path in browser_paths)
    ]
    absolute_client_fetches = [fetch for fetch in client_fetches if fetch.absolute_url]

    errors = [
        f"Missing FastAPI decorator for mirrored route: {route.method} {route.fastapi_path} from {route.next_path}"
        for route in missing_backend
    ]
    errors.extend(
        f"Client fetch has no matching Next route: {fetch.browser_path} from {fetch.source_path}"
        for fetch in missing_client_fetches
    )
    errors.extend(
        f"Client fetch must use a relative Next route, not an absolute API URL: {fetch.browser_path} from {fetch.source_path}"
        for fetch in absolute_client_fetches
    )
    contract_metadata = load_route_contract_metadata()
    for route in routes:
        contract = classify_next_route(route, contract_metadata)
        if (
            route.method in MUTATING_METHODS
            and (route.method, route.browser_path) not in NEXT_ONLY_ROUTES
            and contract.auth_boundary != "local_operator"
        ):
            errors.append(
                f"Mutating Next route must require local operator auth: {route.method} {route.browser_path} from {route.next_path}"
            )
        if route.method in MUTATING_METHODS:
            contract_ids = _split_inventory_values(contract.contract_id)
            if (
                not contract_ids
                or contract.store == "none"
                or contract.record_class == "none"
                or contract.lifecycle in {"read", "write", "delete"}
            ):
                errors.append(
                    "Mutating Next route must declare a route lifecycle/store contract: "
                    f"{route.method} {route.browser_path} from {route.next_path}"
                )
            expected_contract_path = _contract_compare_path(route.browser_path)
            for contract_id in contract_ids:
                route_contract = contract_metadata.get(contract_id)
                if route_contract is None:
                    errors.append(
                        "Route references unknown route contract: "
                        f"{route.method} {route.browser_path} uses {contract_id} from {route.next_path}"
                    )
                    continue
                if route_contract.method and route_contract.method != route.method:
                    errors.append(
                        "Route method and contract disagree: "
                        f"{route.method} {route.browser_path} uses {contract_id} declared as {route_contract.method}"
                    )
                if route_contract.route and route_contract.route != expected_contract_path:
                    errors.append(
                        "Route path and contract disagree: "
                        f"{route.method} {route.browser_path} uses {contract_id} declared for {route_contract.route}"
                    )
        if contract.lifecycle != "read" and contract.contract_id.endswith("_read"):
            errors.append(
                f"Route lifecycle and contract disagree: {route.method} {route.browser_path} has {contract.contract_id}"
            )
    for route in _backend_only_routes(routes, backend_routes):
        contract = classify_backend_only_route(route)
        if route.method in MUTATING_METHODS and contract.lifecycle == "backend_write":
            errors.append(
                f"Backend-only mutating route must declare a lifecycle override: {route.method} {route.path}"
            )
    return errors


def _md_cell(value: str) -> str:
    return str(value or "none").replace("|", "\\|").replace("\n", " ")


def _render_contract_table(routes: list[NextRoute], contract_metadata: dict[str, RouteContractMetadata]) -> list[str]:
    lines = [
        "## Route Auth And Mutation Inventory",
        "",
        "This table is generated from route source signals, not hand-written prose. It shows auth boundaries, write intent labels, and storage/lifecycle contracts for the mounted browser route surface.",
        "",
        "| Browser route | Lifecycle | Auth boundary | Intent label | Contract | Store | Owner |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for route in routes:
        contract = classify_next_route(route, contract_metadata)
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(f"{route.method} {route.browser_path}"),
                    _md_cell(contract.lifecycle),
                    _md_cell(contract.auth_boundary),
                    _md_cell(contract.intent),
                    _md_cell(contract.contract_id),
                    _md_cell(contract.store),
                    _md_cell(contract.owner),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _render_backend_only_contract_table(backend_only: list[FastApiRoute]) -> list[str]:
    lines = [
        "## Backend-Only Auth And Mutation Inventory",
        "",
        "Backend-only routes are direct FastAPI surfaces. When `OPTIONS_BACKEND_API_TOKEN` is configured, direct `/api/*` calls must include `x-options-backend-token`; local operator auth applies at the Next route layer only.",
        "",
        "| FastAPI route | Lifecycle | Auth boundary | Contract | Store | Owner |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for route in backend_only:
        contract = classify_backend_only_route(route)
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(f"{route.method} {route.path}"),
                    _md_cell(contract.lifecycle),
                    _md_cell(contract.auth_boundary),
                    _md_cell(contract.contract_id),
                    _md_cell(contract.store),
                    _md_cell(contract.owner),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _backend_only_routes(routes: list[NextRoute], backend_routes: list[FastApiRoute]) -> list[FastApiRoute]:
    mirrored_set = {
        (route.method, route.fastapi_path)
        for route in routes
        if (route.method, route.browser_path) not in NEXT_ONLY_ROUTES
    }
    return [route for route in backend_routes if (route.method, route.path) not in mirrored_set]


def build_inventory(
    routes: list[NextRoute],
    backend_routes: list[FastApiRoute],
    client_fetches: list[ClientFetch],
) -> dict[str, object]:
    contract_metadata = load_route_contract_metadata()
    backend_only = _backend_only_routes(routes, backend_routes)
    validation_errors = _validation_errors(routes, backend_routes, client_fetches)

    mounted_browser_routes: list[dict[str, object]] = []
    for route in routes:
        contract = classify_next_route(route, contract_metadata)
        next_only_reason = NEXT_ONLY_ROUTES.get((route.method, route.browser_path), "")
        mounted_browser_routes.append(
            {
                "method": route.method,
                "browser_path": route.browser_path,
                "next_path": route.next_path,
                "fastapi_path": route.fastapi_path,
                "route_group": _group_for(route),
                "next_only": bool(next_only_reason),
                "next_only_reason": next_only_reason or None,
                "mutating": route.method in MUTATING_METHODS,
                "lifecycle": contract.lifecycle,
                "auth_boundary": contract.auth_boundary,
                "intent_labels": _split_inventory_values(contract.intent),
                "contract_ids": _split_inventory_values(contract.contract_id),
                "stores": _split_inventory_values(contract.store),
                "record_classes": _split_inventory_values(contract.record_class),
                "owners": _split_inventory_values(contract.owner),
            }
        )

    backend_inventory: list[dict[str, object]] = []
    for route in backend_only:
        contract = classify_backend_only_route(route)
        backend_inventory.append(
            {
                "method": route.method,
                "path": route.path,
                "mutating": route.method in MUTATING_METHODS,
                "lifecycle": contract.lifecycle,
                "auth_boundary": contract.auth_boundary,
                "contract_id": contract.contract_id,
                "store": contract.store,
                "record_class": contract.record_class,
                "owner": contract.owner,
            }
        )

    unique_client_fetches = sorted(
        {(fetch.browser_path, fetch.source_path, fetch.absolute_url) for fetch in client_fetches}
    )

    return {
        "inventory_version": 1,
        "artifact": "route_mutation_inventory",
        "generated_by": "scripts/generate_route_parity.py",
        "runtime_use": False,
        "sources": {
            "next_api_root": "src/app/api",
            "fastapi_route_root": "python-backend",
            "contract_registries": [
                "src/lib/trading-desk/storeOwnership.ts",
                "src/lib/strategy-lab/replayIntent.ts",
                "src/lib/route-lifecycle/routeContracts.ts",
            ],
            "client_fetch_roots": [
                source_root.relative_to(ROOT).as_posix()
                for source_root in CLIENT_FETCH_ROOTS
            ],
        },
        "non_goals": list(ROUTE_INVENTORY_NON_GOALS),
        "mounted_browser_routes": mounted_browser_routes,
        "backend_only_routes": backend_inventory,
        "client_fetches": [
            {
                "browser_path": browser_path,
                "source_path": source_path,
                "absolute_url": absolute_url,
            }
            for browser_path, source_path, absolute_url in unique_client_fetches
        ],
        "validation": {
            "errors": validation_errors,
        },
    }


def render_inventory_json(inventory: dict[str, object]) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True) + "\n"


def render(routes: list[NextRoute], backend_routes: list[FastApiRoute], client_fetches: list[ClientFetch]) -> str:
    backend_only = _backend_only_routes(routes, backend_routes)
    validation_errors = _validation_errors(routes, backend_routes, client_fetches)
    contract_metadata = load_route_contract_metadata()

    lines = [
        "# Route Parity",
        "",
        "> Generated by `python scripts/generate_route_parity.py`. Edit the generator, not this route list.",
        "> Machine-readable sibling: `data/contracts/route-mutation-inventory.json`.",
        "",
        "## Browser Entry Surface",
        "",
        "The mounted browser app is owned by:",
        "",
        "- `src/app/layout.tsx`",
        "- `src/components/layout/AppShell.tsx`",
        "",
        "`src/app/page.tsx` intentionally returns `null`.",
        "",
        "## Active Browser Routes",
        "",
    ]

    for group in GROUP_NAMES:
        group_routes = [route for route in routes if _group_for(route) == group]
        if not group_routes:
            continue
        lines.extend([f"### {group}", ""])
        for route in group_routes:
            next_only_label = NEXT_ONLY_ROUTES.get((route.method, route.browser_path))
            fastapi_label = (
                f"Next-only: {next_only_label}"
                if next_only_label
                else f"{route.method} {route.fastapi_path}"
            )
            lines.extend(
                [
                    f"- Browser: `{route.method} {route.browser_path}`",
                    f"  - Next: `{route.next_path}`",
                    f"  - FastAPI: `{fastapi_label}`",
                ]
            )
        lines.append("")

    lines.extend(_render_contract_table(routes, contract_metadata))

    lines.extend(
        [
            "## Backend-Only Endpoints",
            "",
            "These exist in the FastAPI backend but are not mirrored through active Next routes in this worktree:",
            "",
        ]
    )
    for route in backend_only:
        lines.append(f"- `{route.method} {route.path}`")
    lines.append("")

    lines.extend(_render_backend_only_contract_table(backend_only))

    unique_client_fetches = sorted({(fetch.browser_path, fetch.source_path) for fetch in client_fetches})
    lines.extend(
        [
            "## Client Fetch Surface",
            "",
            "Active client components fetch these mounted browser API routes through Next, not FastAPI directly:",
            "",
        ]
    )
    for browser_path, source_path in unique_client_fetches:
        lines.append(f"- `{browser_path}` from `{source_path}`")
    lines.append("")

    lines.extend(
        [
            "## Known Snapshot Caveats",
            "",
            "- `GET /api/predictions/history` was a duplicate Next alias and has been removed from the live route tree.",
            "- `src/app/api/day-trading/*` exists only as empty scaffolding folders in this worktree.",
            "- Any historical doc that describes mounted day-trading browser routes should be treated as archive context.",
        ]
    )

    if validation_errors:
        lines.extend(["", "## Generator Warnings", ""])
        for error in validation_errors:
            lines.append(f"- {error}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate docs/route-parity.md and data/contracts/route-mutation-inventory.json from Next and FastAPI routes."
    )
    parser.add_argument("--check", action="store_true", help="Fail if generated route inventory artifacts are stale.")
    args = parser.parse_args()

    routes = load_next_routes()
    backend_routes = load_fastapi_routes()
    client_fetches = load_client_fetches()
    content = render(routes, backend_routes, client_fetches)
    inventory_json = render_inventory_json(build_inventory(routes, backend_routes, client_fetches))
    errors = _validation_errors(routes, backend_routes, client_fetches)

    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if existing != content:
            print(f"{OUTPUT_PATH.relative_to(ROOT)} is out of date. Run python scripts/generate_route_parity.py", file=sys.stderr)
            return 1
        existing_json = JSON_OUTPUT_PATH.read_text(encoding="utf-8") if JSON_OUTPUT_PATH.exists() else ""
        if existing_json != inventory_json:
            print(
                f"{JSON_OUTPUT_PATH.relative_to(ROOT)} is out of date. Run python scripts/generate_route_parity.py",
                file=sys.stderr,
            )
            return 1
        if errors:
            print("Route parity validation failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    JSON_OUTPUT_PATH.write_text(inventory_json, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
