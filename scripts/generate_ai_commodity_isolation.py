from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "ai-commodity-isolation.json"
MD_OUTPUT_PATH = ROOT / "docs" / "ai-commodity-isolation.md"
ROUTE_INVENTORY_PATH = ROOT / "data" / "contracts" / "route-mutation-inventory.json"
STORAGE_OWNERSHIP_PATH = ROOT / "data" / "contracts" / "storage-ownership-map.json"
SCANNER_CONTRACT_PATH = ROOT / "data" / "contracts" / "scanner-creation-safety-contract.json"
LEGACY_BOUNDARIES_PATH = ROOT / "data" / "contracts" / "legacy-lane-boundaries.json"
LATEST_PROGRESS_PATH = ROOT / "data" / "ai-commodity-infra" / "progress" / "latest.json"
PACKAGE_JSON_PATH = ROOT / "package.json"

PLAYBOOK_ID = "ai_commodity_infra_observation"
LANE_ID = "ai_commodity_proof_lane"
PROOF_SOURCE_LABEL = "alpaca_opra_daily_snapshot"
PROOF_SCOPE = "ai_commodity_separate"
TRACKING_MODE_DISABLED = "disabled"

OWNER_PATHS = (
    "scripts/run_ai_commodity_opra_progress.py",
    "data/ai-commodity-infra",
    "data/ai-commodity-infra/universe.json",
    "data/ai-commodity-infra/progress/latest.json",
    "tests/test_ai_commodity_opra_progress.py",
    "tests/test_ai_commodity_universe.py",
)

ACTIVE_BROWSER_SCAN_ROOTS = (
    ROOT / "src" / "app",
    ROOT / "src" / "components",
    ROOT / "src" / "lib" / "backend",
    ROOT / "src" / "lib" / "navigation",
    ROOT / "src" / "lib" / "route-lifecycle",
)

DISALLOWED_ACTIVE_BROWSER_IMPORT_PATTERNS = (
    "scripts/run_ai_commodity_opra_progress",
    "run_ai_commodity_opra_progress.py",
    "ai_commodity_universe",
    "data/ai-commodity-infra",
)

FORBIDDEN_ROUTE_SURFACE_TOKENS = (
    "/api/ai-commodity",
    "/api/ai_commodity",
    "/api/commodity",
    "ai-commodity",
    "ai_commodity",
)

NAVIGATION_ROUTE_LIFECYCLE_TOKENS = (
    "ai_commodity_infra_observation",
    "ai_commodity",
    "ai commodity",
    "ai-commodity",
)

DOC_LINK_PATHS = (
    "docs/index.md",
    "docs/PROJECT_CONTEXT.md",
    "docs/architecture-overview.md",
    "docs/architecture-audit.md",
    "docs/scanner-creation-safety-contract.md",
)

NON_PROOF_SOURCE_RULES = (
    "Underlying bars, option OHLC bars, historical option trades, last trades, stale snapshots, indicative feeds, midpoint-only fills, tiny samples, and in-sample-only sweeps do not verify this lane.",
    "OnclickMedia EOD bid/ask and other non-OPRA-certified datasets are research context only.",
    "Regular-options ThetaData/NBBO proof work does not automatically promote AI commodity; this lane is locked to its own Alpaca SIP/OPRA bid/ask snapshot path.",
)

ALLOWED_SHARED_METADATA = (
    "Shared scanner/domain code may carry the `ai_commodity_infra_observation` playbook id.",
    "Frontend display helpers may show AI Commodity provenance labels for historical/source-snapshot rows.",
    "Read-only scorecards and operating dashboards may summarize AI commodity proof state beside regular-options status.",
    "`/api/scan` may route a playbook-scoped diagnostic scan, but the AI commodity playbook must not auto-track or create Trading Desk rows.",
)

NON_GOALS = (
    "No proof-policy, replay math, scanner threshold, route payload, auth, frontend, DB, schema, or Trading Desk behavior changes.",
    "No split or refactor of scripts/run_ai_commodity_opra_progress.py.",
    "No network, WFO, capture, or fresh-scan execution in docs verification.",
    "No broad ban on AI commodity display/provenance metadata in shared code.",
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def _route_inventory_findings() -> list[str]:
    if not ROUTE_INVENTORY_PATH.exists():
        return [f"missing route inventory: {_relative(ROUTE_INVENTORY_PATH)}"]
    inventory = _read_json(ROUTE_INVENTORY_PATH)
    route_surface = {
        "mounted_browser_routes": inventory.get("mounted_browser_routes") or [],
        "client_fetches": inventory.get("client_fetches") or [],
        "backend_only_routes": inventory.get("backend_only_routes") or [],
    }
    route_text = json.dumps(route_surface, sort_keys=True).lower()
    return [token for token in FORBIDDEN_ROUTE_SURFACE_TOKENS if token in route_text]


def _active_browser_import_findings() -> list[str]:
    findings: list[str] = []
    for root in ACTIVE_BROWSER_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            if any(part in {"node_modules", ".next", "__pycache__"} for part in path.relative_to(ROOT).parts):
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in DISALLOWED_ACTIVE_BROWSER_IMPORT_PATTERNS:
                if pattern in text:
                    findings.append(f"{_relative(path)}: {pattern}")
    return findings


def _navigation_route_lifecycle_findings() -> list[str]:
    findings: list[str] = []
    for relative_path in (
        "src/lib/navigation/tabs.ts",
        "src/lib/route-lifecycle/routeContracts.ts",
    ):
        path = ROOT / relative_path
        if not path.exists():
            findings.append(f"missing navigation/lifecycle source: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        for token in NAVIGATION_ROUTE_LIFECYCLE_TOKENS:
            if token in text:
                findings.append(f"{relative_path}: {token}")
    return findings


def _tool_dispatch_findings() -> list[str]:
    path = ROOT / "options_chatbot.py"
    if not path.exists():
        return ["missing options_chatbot.py for tool dispatch check"]
    text = path.read_text(encoding="utf-8")
    start = text.find("TOOL_DISPATCH =")
    end = text.find("\ndef run_tool", start)
    if start < 0 or end < 0:
        return ["could not locate TOOL_DISPATCH block in options_chatbot.py"]
    block = text[start:end].lower()
    disallowed = ("ai_commodity", "ai commodity", "run_ai_commodity", "commodity_opra")
    return [token for token in disallowed if token in block]


def _storage_snapshot() -> dict[str, Any]:
    if not STORAGE_OWNERSHIP_PATH.exists():
        return {"available": False, "error": f"missing {_relative(STORAGE_OWNERSHIP_PATH)}"}
    payload = _read_json(STORAGE_OWNERSHIP_PATH)
    stores = payload.get("stores") if isinstance(payload.get("stores"), list) else []
    store = next((item for item in stores if item.get("store_id") == "ai_commodity_artifacts"), None)
    if not isinstance(store, dict):
        return {"available": False, "error": "storage map is missing ai_commodity_artifacts"}
    return {
        "available": True,
        "store_id": store.get("store_id"),
        "scope": store.get("scope"),
        "storage_role": store.get("storage_role"),
        "persistence": store.get("persistence"),
        "location": store.get("location"),
        "owners": list(store.get("owners") or []),
        "route_contract_ids": list(store.get("route_contract_ids") or []),
        "route_references": store.get("route_references") or {},
    }


def _scanner_contract_snapshot() -> dict[str, Any]:
    if not SCANNER_CONTRACT_PATH.exists():
        return {"available": False, "error": f"missing {_relative(SCANNER_CONTRACT_PATH)}"}
    payload = _read_json(SCANNER_CONTRACT_PATH)
    return {
        "available": True,
        "proof_scope": (payload.get("proofScopes") or {}).get("commodity"),
        "tracking_modes": payload.get("trackingModes") or {},
    }


def _runtime_scanner_snapshot() -> dict[str, Any]:
    try:
        import supervised_scan as ss
    except Exception as exc:  # pragma: no cover - exercised as validation data
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        playbook = ss.get_scan_playbook(PLAYBOOK_ID)
        position_tracking_mode = ss.scan_playbook_position_tracking_mode(PLAYBOOK_ID)
        auto_track_allowed = ss.scan_playbook_allows_auto_track(PLAYBOOK_ID)
        fresh_live_validation_enabled = ss.scan_playbook_fresh_live_validation_enabled(PLAYBOOK_ID)
    except Exception as exc:  # pragma: no cover - exercised as validation data
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "available": True,
        "playbook_id": playbook.get("id"),
        "label": playbook.get("label"),
        "proof_scope": playbook.get("proof_scope"),
        "commodity_proof_scope_constant": getattr(ss, "COMMODITY_PROOF_SCOPE", None),
        "position_tracking_mode": position_tracking_mode,
        "auto_track_allowed": auto_track_allowed,
        "fresh_live_validation_enabled": fresh_live_validation_enabled,
        "creation_blocker_when_visible": f"position_tracking_mode:{position_tracking_mode}",
        "scan_ticker_count": len(list(playbook.get("scan_tickers") or [])),
    }


def _latest_progress_snapshot() -> dict[str, Any]:
    if not LATEST_PROGRESS_PATH.exists():
        return {"available": False, "path": _relative(LATEST_PROGRESS_PATH)}
    report = _read_json(LATEST_PROGRESS_PATH)
    verification = report.get("verification_gate") if isinstance(report.get("verification_gate"), dict) else {}
    isolation = (
        report.get("proof_source_isolation_contract")
        if isinstance(report.get("proof_source_isolation_contract"), dict)
        else {}
    )
    proof_window = report.get("proof_window") if isinstance(report.get("proof_window"), dict) else {}
    shared_after = report.get("shared_quote_dates_after") if isinstance(report.get("shared_quote_dates_after"), dict) else {}
    return {
        "available": True,
        "path": _relative(LATEST_PROGRESS_PATH),
        "generated_at": report.get("generated_at"),
        "provider": report.get("provider"),
        "proof_source_label": report.get("proof_source_label"),
        "verification_status": verification.get("status") or report.get("verification_status"),
        "verified": bool(verification.get("verified")),
        "live_scan_candidate_count": verification.get("live_scan_candidate_count") or report.get("scan_candidate_count"),
        "shared_quote_dates": {
            "current": shared_after.get("count") or proof_window.get("current_shared_quote_dates"),
            "required": proof_window.get("required_shared_quote_dates"),
        },
        "proof_source_isolation": {
            "status": isolation.get("status"),
            "decision": isolation.get("decision"),
            "exact_profitability_proof_source_labels": list(
                isolation.get("exact_profitability_proof_source_labels") or []
            ),
            "research_only_source_labels": list(isolation.get("research_only_source_labels") or []),
            "blockers": list(isolation.get("blockers") or []),
            "top_level_shared_dates_match_proof_source": isolation.get(
                "top_level_shared_dates_match_proof_source"
            ),
        },
        "completion_claim_allowed": report.get("goal_completion_claim_allowed"),
        "no_mutation_guard": report.get("profitability_evidence_scorecard_readback_no_mutation_guard")
        or report.get("fresh_scan_decision_no_mutation_guard")
        or report.get("run_auxiliary_proof_event_no_mutation_guard"),
    }


def _legacy_boundary_snapshot() -> dict[str, Any]:
    if not LEGACY_BOUNDARIES_PATH.exists():
        return {"available": False, "error": f"missing {_relative(LEGACY_BOUNDARIES_PATH)}"}
    payload = _read_json(LEGACY_BOUNDARIES_PATH)
    lanes = {lane.get("lane_id"): lane for lane in payload.get("lanes") or [] if isinstance(lane, dict)}
    lane = lanes.get(LANE_ID)
    if not isinstance(lane, dict):
        return {"available": False, "error": f"missing {LANE_ID} in legacy lane boundaries"}
    return {
        "available": True,
        "status": lane.get("status"),
        "route_ui_status": lane.get("route_ui_status"),
        "detail_owner": lane.get("detail_owner") or lane.get("deferred_to"),
    }


def _package_script_findings() -> list[str]:
    if not PACKAGE_JSON_PATH.exists():
        return ["missing package.json"]
    scripts = (_read_json(PACKAGE_JSON_PATH).get("scripts") or {})
    findings: list[str] = []
    docs_command = scripts.get("docs:ai-commodity-isolation", "")
    verify_docs = scripts.get("verify:docs", "")
    if "scripts/generate_ai_commodity_isolation.py" not in docs_command:
        findings.append("docs:ai-commodity-isolation does not run the generator")
    if "scripts/generate_ai_commodity_isolation.py --check" not in verify_docs:
        findings.append("verify:docs does not check the AI commodity isolation generator")

    for script_name in ("accuracy:report", "verify:accuracy:no-write"):
        command = scripts.get(script_name, "")
        if "scripts/run_ai_commodity_opra_progress.py" not in command:
            findings.append(f"{script_name} does not name the AI commodity progress runner")
            continue
        for flag in ("--skip-capture", "--skip-scan", "--no-write", "--json"):
            if flag not in command:
                findings.append(f"{script_name} is missing safe readback flag {flag}")
    return findings


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path in contract["lane"]["owner_paths"]:
        if not _path_exists(path):
            errors.append(f"missing AI commodity owner path: {path}")

    runtime = contract["scanner_boundary"]["runtime"]
    if runtime.get("available") is not True:
        errors.append(f"runtime scanner snapshot unavailable: {runtime.get('error')}")
    else:
        if runtime.get("playbook_id") != PLAYBOOK_ID:
            errors.append(f"runtime playbook id mismatch: {runtime.get('playbook_id')}")
        if runtime.get("proof_scope") != PROOF_SCOPE:
            errors.append(f"runtime AI commodity proof scope is {runtime.get('proof_scope')}")
        if runtime.get("commodity_proof_scope_constant") != PROOF_SCOPE:
            errors.append(
                "supervised_scan.COMMODITY_PROOF_SCOPE changed from ai_commodity_separate"
            )
        if runtime.get("position_tracking_mode") != TRACKING_MODE_DISABLED:
            errors.append(
                f"AI commodity position_tracking_mode is {runtime.get('position_tracking_mode')}"
            )
        if runtime.get("auto_track_allowed") is not False:
            errors.append("AI commodity auto-track is enabled")
        if runtime.get("fresh_live_validation_enabled") is not False:
            errors.append("AI commodity fresh live validation is enabled")

    scanner_contract = contract["scanner_boundary"]["scanner_creation_contract"]
    if scanner_contract.get("available") is not True:
        errors.append(f"scanner creation contract unavailable: {scanner_contract.get('error')}")
    elif scanner_contract.get("proof_scope") != PROOF_SCOPE:
        errors.append(
            f"scanner creation contract commodity proof scope is {scanner_contract.get('proof_scope')}"
        )

    storage = contract["storage_boundary"]
    if storage.get("available") is not True:
        errors.append(f"storage boundary unavailable: {storage.get('error')}")
    else:
        if storage.get("scope") != "separate_lane" or storage.get("storage_role") != "separate_lane":
            errors.append("ai_commodity_artifacts is not classified as separate_lane storage")
        if storage.get("persistence") != "file_artifact":
            errors.append("ai_commodity_artifacts is not classified as file_artifact persistence")
        if "scripts/run_ai_commodity_opra_progress.py" not in storage.get("owners", []):
            errors.append("ai_commodity_artifacts does not name the AI commodity runner owner")
        route_refs = storage.get("route_references") or {}
        if route_refs.get("active_browser") or route_refs.get("backend_only"):
            errors.append("ai_commodity_artifacts has route references in the storage map")
        if storage.get("route_contract_ids"):
            errors.append("ai_commodity_artifacts has route contract ids")

    latest = contract["latest_progress_readback"]
    if latest.get("available") is True:
        isolation = latest.get("proof_source_isolation") or {}
        if latest.get("proof_source_label") != PROOF_SOURCE_LABEL:
            errors.append(f"latest AI commodity proof source is {latest.get('proof_source_label')}")
        if isolation.get("exact_profitability_proof_source_labels") != [PROOF_SOURCE_LABEL]:
            errors.append("latest AI commodity exact proof source labels are not Alpaca OPRA only")
        if isolation.get("blockers"):
            errors.append("latest AI commodity proof-source isolation has blockers")

    legacy = contract["legacy_lane_boundary"]
    if legacy.get("available") is not True:
        errors.append(f"legacy boundary unavailable: {legacy.get('error')}")
    else:
        if legacy.get("status") != "separate_non_browser_proof_lane":
            errors.append(f"legacy boundary status is {legacy.get('status')}")
        if legacy.get("route_ui_status") != "not_mounted_browser_product":
            errors.append(f"legacy boundary route/UI status is {legacy.get('route_ui_status')}")
        if (
            JSON_OUTPUT_PATH.exists()
            and MD_OUTPUT_PATH.exists()
            and legacy.get("detail_owner") != "docs/ai-commodity-isolation.md"
        ):
            errors.append("legacy boundary does not point AI commodity detail owner to docs/ai-commodity-isolation.md")

    for token in _route_inventory_findings():
        errors.append(f"route inventory exposes AI commodity route surface: {token}")
    for finding in _active_browser_import_findings():
        errors.append(f"active browser surface imports AI commodity proof-lane owner: {finding}")
    for finding in _navigation_route_lifecycle_findings():
        errors.append(f"navigation or route lifecycle exposes AI commodity as a browser route: {finding}")
    for finding in _tool_dispatch_findings():
        errors.append(f"tool dispatch exposes AI commodity runner/tool token: {finding}")
    for finding in _package_script_findings():
        errors.append(f"package script boundary issue: {finding}")

    for doc_path in DOC_LINK_PATHS:
        path = ROOT / doc_path
        if not path.exists():
            errors.append(f"missing living doc for AI commodity isolation link: {doc_path}")
            continue
        if "ai-commodity-isolation.md" not in path.read_text(encoding="utf-8"):
            errors.append(f"{doc_path} does not link docs/ai-commodity-isolation.md")

    return errors


def build_contract() -> dict[str, Any]:
    contract = {
        "artifact": "ai_commodity_isolation",
        "version": 1,
        "generated_by": "scripts/generate_ai_commodity_isolation.py",
        "runtime_use": False,
        "scope": (
            "Readability and drift-check contract for the separate, non-browser AI commodity "
            "proof-first strategy lane."
        ),
        "sources": [
            "AGENTS.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/legacy-lane-boundaries.md",
            "data/contracts/route-mutation-inventory.json",
            "data/contracts/storage-ownership-map.json",
            "data/contracts/scanner-creation-safety-contract.json",
            "data/ai-commodity-infra/progress/latest.json",
            "supervised_scan.py",
        ],
        "lane": {
            "lane_id": LANE_ID,
            "playbook_id": PLAYBOOK_ID,
            "status": "separate_non_browser_proof_lane",
            "route_ui_status": "not_mounted_browser_product",
            "owner_paths": list(OWNER_PATHS),
            "proof_source_label": PROOF_SOURCE_LABEL,
            "proof_scope": PROOF_SCOPE,
        },
        "browser_api_boundary": {
            "dedicated_browser_routes_allowed": False,
            "forbidden_route_surface_tokens": list(FORBIDDEN_ROUTE_SURFACE_TOKENS),
            "active_browser_import_patterns_forbidden": list(DISALLOWED_ACTIVE_BROWSER_IMPORT_PATTERNS),
            "route_inventory_findings": _route_inventory_findings(),
            "active_browser_import_findings": _active_browser_import_findings(),
            "navigation_route_lifecycle_findings": _navigation_route_lifecycle_findings(),
            "tool_dispatch_findings": _tool_dispatch_findings(),
        },
        "scanner_boundary": {
            "runtime": _runtime_scanner_snapshot(),
            "scanner_creation_contract": _scanner_contract_snapshot(),
            "hard_rules": [
                "AI commodity must keep proof_scope=ai_commodity_separate.",
                "AI commodity must keep position_tracking_mode=disabled.",
                "AI commodity must not allow scheduled auto-track or scanner-origin row creation.",
                "Fresh live validation for the regular browser auto-track lane must remain disabled for AI commodity.",
            ],
        },
        "proof_claim_boundary": {
            "exact_profitability_proof_source_labels": [PROOF_SOURCE_LABEL],
            "non_proof_source_rules": list(NON_PROOF_SOURCE_RULES),
            "claim_rule": (
                "Do not claim AI commodity profitability or promote filters until the generated progress "
                "readback independently verifies exact Alpaca OPRA bid/ask replay gates."
            ),
        },
        "storage_boundary": _storage_snapshot(),
        "latest_progress_readback": _latest_progress_snapshot(),
        "legacy_lane_boundary": _legacy_boundary_snapshot(),
        "allowed_shared_metadata": list(ALLOWED_SHARED_METADATA),
        "safe_readback_commands": {
            "accuracy_report": "npm run accuracy:report",
            "verify_accuracy_no_write": "npm run verify:accuracy:no-write",
        },
        "non_goals": list(NON_GOALS),
    }
    contract["validation"] = {"errors": validate_contract(contract)}
    return contract


def render_json(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def _bullet(items: list[str] | tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def _inline_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(contract: dict[str, Any]) -> str:
    lane = contract["lane"]
    runtime = contract["scanner_boundary"]["runtime"]
    latest = contract["latest_progress_readback"]
    storage = contract["storage_boundary"]
    browser = contract["browser_api_boundary"]
    lines = [
        "# AI Commodity Isolation",
        "",
        "Generated by `scripts/generate_ai_commodity_isolation.py`.",
        "Source: `data/contracts/ai-commodity-isolation.json`.",
        f"Runtime use: `{str(contract['runtime_use']).lower()}`.",
        "Do not hand-edit; run `npm run docs:ai-commodity-isolation`.",
        "",
        "This file is the semantic owner for keeping the AI commodity / commodity-infrastructure options lane separate from the mounted regular-options browser product while preserving its proof-first readbacks.",
        "",
        "## Lane Identity",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Lane | `{lane['lane_id']}` |",
        f"| Playbook | `{lane['playbook_id']}` |",
        f"| Status | `{lane['status']}` |",
        f"| Route/UI status | `{lane['route_ui_status']}` |",
        f"| Proof scope | `{lane['proof_scope']}` |",
        f"| Exact proof source | `{lane['proof_source_label']}` |",
        "",
        "Primary owner paths:",
        "",
    ]
    lines.extend(_bullet([f"`{path}`" for path in lane["owner_paths"]]))

    lines.extend(
        [
            "",
            "## Browser And API Boundary",
            "",
            "- Dedicated AI commodity browser/API routes are not allowed in the current product surface.",
            "- Active browser routes, components, backend helpers, navigation, and route-lifecycle registries must not import the AI commodity runner, universe helper, or data artifacts.",
            "- `/api/tools/{name}` must not expose an AI commodity runner/tool.",
            "- `/api/scan` may carry playbook metadata, but it remains the regular supervised scanner route and must not become an AI commodity product route.",
            "",
            "Current guard findings:",
            "",
            f"- Route inventory findings: `{browser['route_inventory_findings']}`",
            f"- Active browser import findings: `{browser['active_browser_import_findings']}`",
            f"- Navigation/route-lifecycle findings: `{browser['navigation_route_lifecycle_findings']}`",
            f"- Tool dispatch findings: `{browser['tool_dispatch_findings']}`",
            "",
            "## Scanner And Creation Boundary",
            "",
            "| Runtime field | Value |",
            "| --- | --- |",
            f"| Playbook id | `{runtime.get('playbook_id')}` |",
            f"| Position tracking mode | `{runtime.get('position_tracking_mode')}` |",
            f"| Auto-track allowed | `{_inline_json(runtime.get('auto_track_allowed'))}` |",
            f"| Fresh live validation enabled | `{_inline_json(runtime.get('fresh_live_validation_enabled'))}` |",
            f"| Proof scope | `{runtime.get('proof_scope')}` |",
            f"| Visible-pick creation blocker | `{runtime.get('creation_blocker_when_visible')}` |",
            "",
        ]
    )
    lines.extend(_bullet(contract["scanner_boundary"]["hard_rules"]))

    lines.extend(
        [
            "",
            "## Proof Claim Boundary",
            "",
            f"- Only `{PROOF_SOURCE_LABEL}` counts for exact AI commodity profitability proof.",
            f"- Latest verification status: `{latest.get('verification_status')}`.",
            f"- Latest verified flag: `{_inline_json(latest.get('verified'))}`.",
            f"- Latest shared quote dates: `{_inline_json(latest.get('shared_quote_dates'))}`.",
            f"- Latest completion claim allowed: `{_inline_json(latest.get('completion_claim_allowed'))}`.",
            "",
        ]
    )
    lines.extend(_bullet(contract["proof_claim_boundary"]["non_proof_source_rules"]))

    lines.extend(
        [
            "",
            "## Storage Boundary",
            "",
            f"- Store: `{storage.get('store_id')}`.",
            f"- Scope: `{storage.get('scope')}`.",
            f"- Persistence: `{storage.get('persistence')}`.",
            f"- Route references: `{_inline_json(storage.get('route_references'))}`.",
            "",
            "## Allowed Shared Metadata",
            "",
        ]
    )
    lines.extend(_bullet(contract["allowed_shared_metadata"]))
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(_bullet(contract["non_goals"]))
    lines.extend(["", "## Validation", ""])
    if contract["validation"]["errors"]:
        lines.extend(_bullet(contract["validation"]["errors"]))
    else:
        lines.append("- No AI commodity isolation violations detected.")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate AI commodity isolation artifacts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale or invalid.")
    args = parser.parse_args(argv)

    contract = build_contract()
    rendered_json = render_json(contract)
    rendered_markdown = render_markdown(contract)
    errors = list(contract["validation"]["errors"])

    if args.check:
        stale: list[str] = []
        if not JSON_OUTPUT_PATH.exists() or JSON_OUTPUT_PATH.read_text(encoding="utf-8") != rendered_json:
            stale.append(_relative(JSON_OUTPUT_PATH))
        if not MD_OUTPUT_PATH.exists() or MD_OUTPUT_PATH.read_text(encoding="utf-8") != rendered_markdown:
            stale.append(_relative(MD_OUTPUT_PATH))
        if stale or errors:
            for item in stale:
                print(f"stale generated artifact: {item}", file=sys.stderr)
            for error in errors:
                print(f"AI commodity isolation violation: {error}", file=sys.stderr)
            return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(rendered_json, encoding="utf-8")
    MD_OUTPUT_PATH.write_text(rendered_markdown, encoding="utf-8")
    if errors:
        for error in errors:
            print(f"AI commodity isolation violation: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
