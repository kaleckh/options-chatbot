from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_API_ROOT = ROOT / "src" / "app" / "api"
FASTAPI_MAIN = ROOT / "python-backend" / "main.py"
FASTAPI_ROUTE_FILES = tuple(sorted((ROOT / "python-backend").glob("*.py")))
OUTPUT_PATH = ROOT / "docs" / "route-parity.md"

HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")

GROUPS: list[tuple[str, tuple[str, ...]]] = [
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
    ("GET", "/api/positions"): 180,
    ("POST", "/api/positions"): 190,
    ("POST", "/api/positions/review"): 200,
    ("POST", "/api/positions/[id]/close"): 210,
    ("GET", "/api/suggested-trades"): 220,
    ("POST", "/api/suggested-trades"): 230,
    ("POST", "/api/suggested-trades/review"): 240,
    ("POST", "/api/suggested-trades/[id]/close"): 250,
    ("GET", "/api/sectors"): 260,
    ("POST", "/api/tools/[name]"): 270,
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
    source_roots = (ROOT / "src" / "components",)
    for source_root in source_roots:
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
    missing_backend = [route for route in routes if (route.method, route.fastapi_path) not in backend_set]
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
    return errors


def render(routes: list[NextRoute], backend_routes: list[FastApiRoute], client_fetches: list[ClientFetch]) -> str:
    mirrored_set = {(route.method, route.fastapi_path) for route in routes}
    backend_only = [route for route in backend_routes if (route.method, route.path) not in mirrored_set]
    validation_errors = _validation_errors(routes, backend_routes, client_fetches)

    lines = [
        "# Route Parity",
        "",
        "> Generated by `python scripts/generate_route_parity.py`. Edit the generator, not this route list.",
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
            lines.extend(
                [
                    f"- Browser: `{route.method} {route.browser_path}`",
                    f"  - Next: `{route.next_path}`",
                    f"  - FastAPI: `{route.method} {route.fastapi_path}`",
                ]
            )
        lines.append("")

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
    parser = argparse.ArgumentParser(description="Generate docs/route-parity.md from Next and FastAPI routes.")
    parser.add_argument("--check", action="store_true", help="Fail if docs/route-parity.md is stale.")
    args = parser.parse_args()

    routes = load_next_routes()
    backend_routes = load_fastapi_routes()
    client_fetches = load_client_fetches()
    content = render(routes, backend_routes, client_fetches)
    errors = _validation_errors(routes, backend_routes, client_fetches)

    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if existing != content:
            print(f"{OUTPUT_PATH.relative_to(ROOT)} is out of date. Run python scripts/generate_route_parity.py", file=sys.stderr)
            return 1
        if errors:
            print("Route parity validation failed:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        return 0

    OUTPUT_PATH.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
