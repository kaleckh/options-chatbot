from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_API_ROOT = ROOT / "src" / "app" / "api"
FASTAPI_MAIN = ROOT / "python-backend" / "main.py"
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
    pattern = re.compile(r'@app\.(get|post|put|delete|patch)\("([^"]+)"')
    for line in FASTAPI_MAIN.read_text(encoding="utf-8").splitlines():
        match = pattern.search(line)
        if match:
            routes.append(FastApiRoute(method=match.group(1).upper(), path=match.group(2)))
    return routes


def _group_for(route: NextRoute) -> str:
    for group, prefixes in GROUPS:
        if any(route.browser_path == prefix or route.browser_path.startswith(f"{prefix}/") for prefix in prefixes):
            return group
    return "Other"


def render(routes: list[NextRoute], backend_routes: list[FastApiRoute]) -> str:
    backend_set = {(route.method, route.path) for route in backend_routes}
    mirrored_set = {(route.method, route.fastapi_path) for route in routes}
    backend_only = [route for route in backend_routes if (route.method, route.path) not in mirrored_set]
    missing_backend = [route for route in routes if (route.method, route.fastapi_path) not in backend_set]

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
            "These exist in `python-backend/main.py` but are not mirrored through active Next routes in this worktree:",
            "",
        ]
    )
    for route in backend_only:
        lines.append(f"- `{route.method} {route.path}`")
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

    if missing_backend:
        lines.extend(["", "## Generator Warnings", ""])
        for route in missing_backend:
            lines.append(
                f"- Missing FastAPI decorator for mirrored route: `{route.method} {route.fastapi_path}` from `{route.next_path}`"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/route-parity.md from Next and FastAPI routes.")
    parser.add_argument("--check", action="store_true", help="Fail if docs/route-parity.md is stale.")
    args = parser.parse_args()

    content = render(load_next_routes(), load_fastapi_routes())

    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if existing != content:
            print(f"{OUTPUT_PATH.relative_to(ROOT)} is out of date. Run python scripts/generate_route_parity.py", file=sys.stderr)
            return 1
        return 0

    OUTPUT_PATH.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
