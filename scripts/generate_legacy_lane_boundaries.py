from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "legacy-lane-boundaries.json"
MD_OUTPUT_PATH = ROOT / "docs" / "legacy-lane-boundaries.md"
ROUTE_INVENTORY_PATH = ROOT / "data" / "contracts" / "route-mutation-inventory.json"

NON_GOALS = (
    "No deletion, repair, refactor, or expansion of paused day-trading, crypto-options, or Polymarket code.",
    "No browser route, navigation tab, route lifecycle, auth, payload, proof, scanner, replay, DB, or schema behavior changes.",
    "No package-script disabling; legacy and sidecar test commands may exist without making a lane active.",
    "No AI commodity isolation work beyond naming it as a separate lane deferred to the AI commodity isolation contract.",
)

LANES: tuple[dict[str, Any], ...] = (
    {
        "lane_id": "regular_supervised_options_browser",
        "label": "Regular supervised options browser",
        "status": "active_browser_product",
        "route_ui_status": "mounted_browser_product",
        "path_roots": (
            "src/components/predictions",
            "src/components/strategy",
            "src/app/api/scan",
            "src/app/api/positions",
            "src/app/api/suggested-trades",
            "src/app/api/backtest",
            "python-backend/main.py",
            "options_chatbot.py",
            "wfo_optimizer.py",
        ),
        "owner_docs": (
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-overview.md",
            "docs/api-and-storage.md",
            "docs/replay-profit-contract.md",
        ),
        "allowed_work": (
            "Live scan, replay diagnostics, paper ideas, tracked-position review, route/readback contracts, and regular-options proof hygiene.",
        ),
        "forbidden_work": (
            "Do not route active browser work through paused day-trading, crypto-options, or Polymarket code paths.",
        ),
        "hard_rules": (
            "This is the only mounted browser product family in the current worktree.",
            "Regular playbook lanes are peers; legacy cohort suffixes do not make a lane watch-only by themselves.",
        ),
    },
    {
        "lane_id": "legacy_prediction_analytics",
        "label": "Legacy prediction analytics tabs",
        "status": "active_browser_legacy_analytics",
        "route_ui_status": "mounted_inside_trading_desk_analytics",
        "path_roots": (
            "src/components/predictions/legacy-tabs.tsx",
            "src/components/predictions/tradingDeskTabs.ts",
            "tests/trading-desk/trading-desk-tab-ids.test.js",
        ),
        "owner_docs": (
            "docs/architecture-audit.md",
            "docs/architecture-overview.md",
        ),
        "allowed_work": (
            "Readability, mobile table contracts, and analytics maintenance when tied to the active Trading Desk.",
        ),
        "forbidden_work": (
            "Do not confuse these Trading Desk analytics tabs with paused day-trading, crypto-options, or Polymarket lanes.",
        ),
        "hard_rules": (
            "Legacy analytics are still inside the Trading Desk surface.",
            "They are not a reopen signal for paused sidecar lanes.",
        ),
    },
    {
        "lane_id": "ai_commodity_proof_lane",
        "label": "AI commodity proof lane",
        "status": "separate_non_browser_proof_lane",
        "route_ui_status": "not_mounted_browser_product",
        "detail_owner": "docs/ai-commodity-isolation.md",
        "path_roots": (
            "scripts/run_ai_commodity_opra_progress.py",
            "data/ai-commodity-infra",
            "tests/test_ai_commodity_opra_progress.py",
        ),
        "owner_docs": (
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-overview.md",
            "docs/ai-commodity-isolation.md",
        ),
        "allowed_work": (
            "Proof-source acquisition, readiness, OPRA/SIP/NBBO validation, and lane-specific automation when explicitly scoped.",
        ),
        "forbidden_work": (
            "Do not treat AI commodity as a mounted browser route or regular supervised browser fallback.",
        ),
        "hard_rules": (
            "AI commodity is separate from the active browser product.",
            "docs/ai-commodity-isolation.md owns deeper AI commodity isolation checks.",
        ),
    },
    {
        "lane_id": "day_trading",
        "label": "Paused day-trading lane",
        "status": "paused_out_of_scope",
        "route_ui_status": "empty_route_scaffolding_only",
        "path_roots": (
            "src/lib/day-trading",
            "tests/day-trading",
            "src/app/api/day-trading",
            "docs/day-trading-current-state.md",
            "docs/archive/day-trading-product-roadmap.md",
        ),
        "owner_docs": (
            "docs/day-trading-current-state.md",
            "docs/archive/day-trading-product-roadmap.md",
        ),
        "allowed_work": (
            "Only archive, remove, repair, or reopen work explicitly requested by the user.",
        ),
        "forbidden_work": (
            "Do not add app-facing routes, UI tabs, background automation, performance work, or fresh documentation effort by default.",
        ),
        "hard_rules": (
            "The current src/app/api/day-trading folders are empty scaffolding, not live routes.",
            "Existing engine code and tests may remain without making the lane active.",
            "Reopening requires an explicit user request.",
        ),
    },
    {
        "lane_id": "crypto_options_sidecar",
        "label": "Crypto options sidecar",
        "status": "paused_out_of_scope",
        "route_ui_status": "not_mounted_browser_product",
        "path_roots": (
            "crypto_options",
            "scripts/run_crypto_scan.bat",
        ),
        "owner_docs": (
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-audit.md",
        ),
        "allowed_work": (
            "Only archive, remove, repair, or reopen work explicitly requested by the user.",
        ),
        "forbidden_work": (
            "Do not tune, route, monitor, or expand crypto options from regular-options remediation loops.",
        ),
        "hard_rules": (
            "Crypto options are out of active product scope.",
            "Package scripts may exist without making this an active browser lane.",
            "Reopening requires an explicit user request.",
        ),
    },
    {
        "lane_id": "polymarket_sidecar",
        "label": "Polymarket sidecar",
        "status": "paused_out_of_scope",
        "route_ui_status": "not_mounted_browser_product",
        "path_roots": (
            "src/lib/polymarket",
            "tests/polymarket",
        ),
        "owner_docs": (
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-audit.md",
        ),
        "allowed_work": (
            "Only archive, remove, repair, or reopen work explicitly requested by the user.",
        ),
        "forbidden_work": (
            "Do not wire Polymarket into active navigation, route lifecycle, scanner, proof, or Trading Desk flows.",
        ),
        "hard_rules": (
            "Polymarket code is adjacent tooling, not the active browser product.",
            "Existing tests may remain without making this lane active.",
            "Reopening requires an explicit user request.",
        ),
    },
)

ACTIVE_BROWSER_SCAN_ROOTS = (
    ROOT / "src" / "app",
    ROOT / "src" / "components",
    ROOT / "src" / "lib" / "backend",
    ROOT / "src" / "lib" / "navigation",
    ROOT / "src" / "lib" / "route-lifecycle",
)
PAUSED_BROWSER_IMPORT_PATTERNS = (
    "@/lib/day-trading",
    "src/lib/day-trading",
    "../lib/day-trading",
    "@/lib/polymarket",
    "src/lib/polymarket",
    "../lib/polymarket",
    "crypto_options",
)
EXCLUDED_SCAN_PARTS = {"day-trading", "polymarket", "node_modules", ".next", "__pycache__"}
DAY_TRADING_ROUTE_HANDLER_NAMES = {"route.ts", "route.tsx", "route.js", "route.jsx"}
DOC_LINK_PATHS = (
    "docs/index.md",
    "docs/PROJECT_CONTEXT.md",
    "docs/architecture-overview.md",
    "docs/architecture-audit.md",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def _day_trading_route_handlers() -> list[str]:
    root = ROOT / "src" / "app" / "api" / "day-trading"
    if not root.exists():
        return []
    return sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in root.rglob("*")
        if path.is_file() and path.name in DAY_TRADING_ROUTE_HANDLER_NAMES
    )


def _active_browser_import_findings() -> list[str]:
    findings: list[str] = []
    for root in ACTIVE_BROWSER_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_SCAN_PARTS for part in relative.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in PAUSED_BROWSER_IMPORT_PATTERNS:
                if pattern in text:
                    findings.append(f"{str(relative).replace('\\', '/')}: {pattern}")
    return findings


def _route_inventory_findings() -> list[str]:
    if not ROUTE_INVENTORY_PATH.exists():
        return [f"missing route inventory: {ROUTE_INVENTORY_PATH.relative_to(ROOT)}"]
    inventory = _read_json(ROUTE_INVENTORY_PATH)
    route_surface = {
        "mounted_browser_routes": inventory.get("mounted_browser_routes") or [],
        "backend_only_routes": inventory.get("backend_only_routes") or [],
        "client_fetches": inventory.get("client_fetches") or [],
    }
    inventory_text = json.dumps(route_surface, sort_keys=True).lower()
    disallowed = ("/api/day-trading", "day-trading", "polymarket", "crypto_options")
    return [token for token in disallowed if token in inventory_text]


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lanes = {lane["lane_id"]: lane for lane in contract["lanes"]}
    expected_statuses = {
        "regular_supervised_options_browser": "active_browser_product",
        "legacy_prediction_analytics": "active_browser_legacy_analytics",
        "ai_commodity_proof_lane": "separate_non_browser_proof_lane",
        "day_trading": "paused_out_of_scope",
        "crypto_options_sidecar": "paused_out_of_scope",
        "polymarket_sidecar": "paused_out_of_scope",
    }
    for lane_id, expected_status in expected_statuses.items():
        lane = lanes.get(lane_id)
        if lane is None:
            errors.append(f"missing lane: {lane_id}")
            continue
        if lane.get("status") != expected_status:
            errors.append(f"{lane_id} status is {lane.get('status')}, expected {expected_status}")
        for path in lane.get("path_roots") or []:
            if not _path_exists(path):
                errors.append(f"{lane_id} missing path root: {path}")
        for doc in lane.get("owner_docs") or []:
            if not _path_exists(doc):
                errors.append(f"{lane_id} missing owner doc: {doc}")
        if not lane.get("hard_rules"):
            errors.append(f"{lane_id} has no hard rules")

    for handler in _day_trading_route_handlers():
        errors.append(f"paused day-trading route handler is mounted: {handler}")
    for finding in _active_browser_import_findings():
        errors.append(f"active browser surface imports paused lane: {finding}")
    for token in _route_inventory_findings():
        errors.append(f"route mutation inventory mentions paused lane token: {token}")

    for doc_path in DOC_LINK_PATHS:
        path = ROOT / doc_path
        if not path.exists():
            errors.append(f"missing living doc for boundary link: {doc_path}")
            continue
        if "legacy-lane-boundaries.md" not in path.read_text(encoding="utf-8"):
            errors.append(f"{doc_path} does not link docs/legacy-lane-boundaries.md")

    return errors


def build_contract() -> dict[str, Any]:
    contract = {
        "artifact": "legacy_lane_boundaries",
        "version": 1,
        "generated_by": "scripts/generate_legacy_lane_boundaries.py",
        "runtime_use": False,
        "owner": "Legacy, sidecar, paused, and active lane boundary map for agent orientation.",
        "scope": (
            "Classifies active browser product lanes, active legacy analytics inside Trading Desk, "
            "the separate AI commodity proof lane, and paused/out-of-scope sidecars."
        ),
        "non_goals": list(NON_GOALS),
        "sources": [
            "AGENTS.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-audit.md",
            "docs/architecture-overview.md",
            "data/contracts/route-mutation-inventory.json",
        ],
        "lanes": [dict(lane) for lane in LANES],
    }
    contract["validation"] = {"errors": validate_contract(contract)}
    return contract


def render_json(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def _bullet(items: list[str] | tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def render_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Legacy Lane Boundaries",
        "",
        "Generated by `scripts/generate_legacy_lane_boundaries.py`.",
        "Source: `data/contracts/legacy-lane-boundaries.json`.",
        f"Runtime use: `{str(contract['runtime_use']).lower()}`.",
        "Do not hand-edit; run `npm run docs:legacy-lane-boundaries`.",
        "",
        "This file is the semantic owner for active, separate, legacy, sidecar, and paused lane boundaries. It tells agents what is current product work and what must not be fixed, expanded, or documented unless the user explicitly reopens it.",
        "",
        "## Lane Map",
        "",
        "| Lane | Status | Route/UI status | Primary paths |",
        "| --- | --- | --- | --- |",
    ]
    for lane in contract["lanes"]:
        paths = "<br>".join(f"`{path}`" for path in lane["path_roots"])
        lines.append(
            f"| `{lane['lane_id']}` | `{lane['status']}` | `{lane['route_ui_status']}` | {paths} |"
        )

    lines.extend(["", "## Hard Rules", ""])
    for lane in contract["lanes"]:
        lines.append(f"### {lane['label']}")
        lines.extend(_bullet(lane["hard_rules"]))
        if lane.get("detail_owner"):
            lines.append(f"- Detail owner: `{lane['detail_owner']}`.")
        if lane.get("deferred_to"):
            lines.append(f"- Deferred detail owner: {lane['deferred_to']}.")
        lines.append("")

    lines.extend(
        [
            "## Guarded Checks",
            "",
            "- `src/app/api/day-trading/**` must not contain active `route.ts`, `route.tsx`, `route.js`, or `route.jsx` handlers.",
            "- Active browser surfaces must not import paused day-trading, crypto-options, or Polymarket modules.",
            "- `data/contracts/route-mutation-inventory.json` must not list day-trading, crypto-options, or Polymarket browser routes.",
            "- Living docs must link this boundary map so agents do not infer scope from old code or archive docs.",
            "",
            "## Non-Goals",
            "",
        ]
    )
    lines.extend(_bullet(contract["non_goals"]))
    lines.extend(["", "## Validation", ""])
    if contract["validation"]["errors"]:
        lines.extend(_bullet(contract["validation"]["errors"]))
    else:
        lines.append("- No boundary violations detected.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate legacy lane boundary artifacts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale or invalid.")
    args = parser.parse_args(argv)

    contract = build_contract()
    rendered_json = render_json(contract)
    rendered_markdown = render_markdown(contract)
    errors = list(contract["validation"]["errors"])

    if args.check:
        stale: list[str] = []
        if not JSON_OUTPUT_PATH.exists() or JSON_OUTPUT_PATH.read_text(encoding="utf-8") != rendered_json:
            stale.append(str(JSON_OUTPUT_PATH.relative_to(ROOT)))
        if not MD_OUTPUT_PATH.exists() or MD_OUTPUT_PATH.read_text(encoding="utf-8") != rendered_markdown:
            stale.append(str(MD_OUTPUT_PATH.relative_to(ROOT)))
        if stale or errors:
            for item in stale:
                print(f"stale generated artifact: {item}", file=sys.stderr)
            for error in errors:
                print(f"legacy lane boundary violation: {error}", file=sys.stderr)
            return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(rendered_json, encoding="utf-8")
    MD_OUTPUT_PATH.write_text(rendered_markdown, encoding="utf-8")
    if errors:
        for error in errors:
            print(f"legacy lane boundary violation: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
