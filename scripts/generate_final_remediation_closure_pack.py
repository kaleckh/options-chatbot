from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "scripts/generate_final_remediation_closure_pack.py"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "final-remediation-closure-pack.json"
MD_OUTPUT_PATH = ROOT / "docs" / "final-remediation-closure-pack.md"

EXPECTED_RUNTIME_GENERATED_ARTIFACTS = ("src/lib/generated/proofEvidenceContract.ts",)
DISCOVERY_TARGETS = (
    "docs/index.md",
    "docs/living-docs-hygiene.md",
    "docs/architecture-overview.md",
    "docs/architecture-best-practices.md",
    "docs/remediation-loop-map.md",
    "docs/agent-memory-graph.md",
    "docs/generated-artifact-governance.md",
)
GENERATED_CONTRACTS_WITH_VALIDATION = (
    "data/contracts/route-mutation-inventory.json",
    "data/contracts/backend-route-ownership-map.json",
    "data/contracts/storage-ownership-map.json",
    "data/contracts/legacy-lane-boundaries.json",
    "data/contracts/ai-commodity-isolation.json",
    "data/contracts/remediation-loop-map.json",
    "data/contracts/generated-artifact-governance.json",
)
NON_GOALS = (
    "Does not define route behavior, payloads, auth semantics, proof predicates, scanner policy, replay math, DB schema, or frontend behavior.",
    "Does not claim production profitability, broker execution readiness, or AI commodity proof completion.",
    "Does not reopen crypto options, Polymarket, day-trading, or other paused sidecar lanes.",
    "Does not govern volatile research runs, generated market-data outputs, DB sidecars, archives, or dated evidence reports.",
    "Does not use timestamps, mtimes, content hashes, network freshness checks, DB opens, migrations, or runtime app introspection.",
)
VERIFICATION_LADDER = (
    "uv run --locked python scripts/generate_final_remediation_closure_pack.py --check",
    "uv run --locked python -m unittest tests.test_final_remediation_closure_pack -v",
    "uv run --locked python -m unittest tests.test_final_remediation_closure_pack tests.test_remediation_loop_map tests.test_generated_artifact_governance tests.test_agent_memory_graph tests.test_living_docs_hygiene -v",
    "npm run verify:docs",
    "git diff --check",
)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_json(relative_path: str) -> dict[str, Any]:
    return json.loads(_read(relative_path))


def _package_scripts() -> dict[str, str]:
    return dict(_load_json("package.json")["scripts"])


def _validation_errors(payload: dict[str, Any]) -> list[str]:
    validation = payload.get("validation")
    if not isinstance(validation, dict):
        return []
    errors = validation.get("errors")
    return list(errors) if isinstance(errors, list) else []


def _existing_paths(relative_paths: list[str]) -> list[str]:
    return [path for path in relative_paths if (ROOT / path).exists()]


def _missing_paths(relative_paths: list[str]) -> list[str]:
    return [path for path in relative_paths if not (ROOT / path).exists()]


def _loop_closure(remediation: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    points = remediation.get("points", [])
    numbers = [point.get("point") for point in points]
    status_split = remediation.get("validation", {}).get("status_split", {})
    current_state = remediation.get("current_state", {})
    point_44 = points[43] if len(points) >= 44 else {}
    completed_points = [point for point in points if point.get("status") == "completed"]
    missing_evidence: list[dict[str, Any]] = []
    missing_owner_paths: list[dict[str, Any]] = []

    if remediation.get("artifact") != "remediation_loop_map":
        errors.append("Remediation loop source is not data/contracts/remediation-loop-map.json.")
    if remediation.get("runtime_use") is not False:
        errors.append("Remediation loop map must remain runtime_use=false.")
    if _validation_errors(remediation):
        errors.append(f"Remediation loop map validation errors are present: {_validation_errors(remediation)}")
    if numbers != list(range(1, 45)):
        errors.append("Remediation loop points must be unique, consecutive, and sorted 1..44.")
    if any(point.get("status") != "completed" for point in points):
        errors.append("All remediation loop points must be completed for final closure.")
    if current_state.get("completed_through_point") != 44:
        errors.append("Remediation loop completed_through_point must be 44.")
    if current_state.get("planned_points") != []:
        errors.append("Remediation loop planned_points must be empty.")
    if current_state.get("next_point") is not None:
        errors.append("Remediation loop next_point must be null after final closure.")
    if status_split.get("completed") != 44 or status_split.get("planned") != 0 or status_split.get("in_progress") != 0:
        errors.append("Remediation loop status split must be 44 completed, 0 planned, and 0 in_progress.")

    worklog = _read("docs/WORKLOG.md")
    for point in completed_points:
        owner_paths = [*point.get("owner_docs", []), *point.get("owner_artifacts", [])]
        missing = _missing_paths(owner_paths)
        if missing:
            missing_owner_paths.append({"point": point.get("point"), "missing_paths": missing})
        if not point.get("tests_or_checks"):
            missing_evidence.append({"point": point.get("point"), "reason": "missing tests_or_checks"})
        if not point.get("worklog_evidence"):
            missing_evidence.append({"point": point.get("point"), "reason": "missing worklog_evidence"})
        elif not any(anchor in worklog for anchor in point.get("worklog_evidence", [])):
            missing_evidence.append({"point": point.get("point"), "reason": "worklog evidence anchor not found"})

    if missing_owner_paths:
        errors.append(f"Completed remediation points have missing owner paths: {missing_owner_paths}")
    if missing_evidence:
        errors.append(f"Completed remediation points have missing evidence: {missing_evidence}")

    point_44_required_docs = {"docs/final-remediation-closure-pack.md"}
    point_44_required_artifacts = {
        GENERATOR,
        "data/contracts/final-remediation-closure-pack.json",
    }
    point_44_checks = set(point_44.get("tests_or_checks", []))
    if point_44.get("title") != "Final Goal Closure Verification Pack":
        errors.append("Point 44 must be titled Final Goal Closure Verification Pack.")
    if point_44.get("behavior_changed") is not False:
        errors.append("Point 44 must not be marked as behavior-changing.")
    if not point_44_required_docs.issubset(set(point_44.get("owner_docs", []))):
        errors.append("Point 44 must own docs/final-remediation-closure-pack.md.")
    if not point_44_required_artifacts.issubset(set(point_44.get("owner_artifacts", []))):
        errors.append("Point 44 must own the closure generator and JSON output.")
    if "tests.test_final_remediation_closure_pack" not in point_44_checks:
        errors.append("Point 44 must include tests.test_final_remediation_closure_pack as a check.")

    return {
        "source": "data/contracts/remediation-loop-map.json",
        "total_points": len(points),
        "completed_points": len(completed_points),
        "planned_points": status_split.get("planned"),
        "in_progress_points": status_split.get("in_progress"),
        "completed_through_point": current_state.get("completed_through_point"),
        "next_point": current_state.get("next_point"),
        "point_44_title": point_44.get("title"),
        "point_44_behavior_changed": point_44.get("behavior_changed"),
        "point_44_owner_docs": point_44.get("owner_docs", []),
        "point_44_owner_artifacts": point_44.get("owner_artifacts", []),
        "point_44_tests_or_checks": point_44.get("tests_or_checks", []),
        "missing_owner_paths": missing_owner_paths,
        "missing_evidence": missing_evidence,
    }


def _generated_artifact_closure(governance: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    governed_artifacts = governance.get("governed_artifacts", [])
    governed_by_path = {artifact.get("path"): artifact for artifact in governed_artifacts}
    closure_paths = {
        "docs/final-remediation-closure-pack.md",
        "data/contracts/final-remediation-closure-pack.json",
    }
    runtime_paths = sorted(
        artifact.get("path")
        for artifact in governed_artifacts
        if artifact.get("runtime_use")
    )
    missing_closure_artifacts = sorted(closure_paths - set(governed_by_path))
    uncovered_artifacts = sorted(
        artifact.get("path")
        for artifact in governed_artifacts
        if not artifact.get("verify_docs_covered")
    )
    hand_editable_artifacts = sorted(
        artifact.get("path")
        for artifact in governed_artifacts
        if artifact.get("hand_edit_allowed")
    )

    if governance.get("artifact") != "generated_artifact_governance":
        errors.append("Generated artifact governance source is not the expected artifact.")
    if governance.get("runtime_use") is not False:
        errors.append("Generated artifact governance must remain runtime_use=false.")
    if _validation_errors(governance):
        errors.append(f"Generated artifact governance validation errors are present: {_validation_errors(governance)}")
    if missing_closure_artifacts:
        errors.append(f"Closure artifacts are not governed: {missing_closure_artifacts}")
    if runtime_paths != list(EXPECTED_RUNTIME_GENERATED_ARTIFACTS):
        errors.append(f"Unexpected generated runtime-use artifacts: {runtime_paths}")
    if uncovered_artifacts:
        errors.append(f"Governed artifacts are not covered by verify:docs: {uncovered_artifacts}")
    if hand_editable_artifacts:
        errors.append(f"Governed artifacts allow hand edits: {hand_editable_artifacts}")

    return {
        "source": "data/contracts/generated-artifact-governance.json",
        "governed_artifact_count": len(governed_artifacts),
        "closure_artifacts_governed": sorted(closure_paths & set(governed_by_path)),
        "missing_closure_artifacts": missing_closure_artifacts,
        "runtime_generated_artifacts": runtime_paths,
        "uncovered_artifacts": uncovered_artifacts,
        "hand_editable_artifacts": hand_editable_artifacts,
        "excluded_artifact_classes": governance.get("excluded_artifact_classes", []),
    }


def _guard_artifact_closure(errors: list[str]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for relative_path in GENERATED_CONTRACTS_WITH_VALIDATION:
        payload = _load_json(relative_path)
        artifact_errors = _validation_errors(payload)
        if artifact_errors:
            errors.append(f"{relative_path} validation errors are present: {artifact_errors}")
        if payload.get("runtime_use") is not False:
            errors.append(f"{relative_path} must declare runtime_use=false.")
        summaries.append(
            {
                "path": relative_path,
                "artifact": payload.get("artifact"),
                "generated_by": payload.get("generated_by"),
                "runtime_use": payload.get("runtime_use"),
                "validation_error_count": len(artifact_errors),
            }
        )
    return summaries


def _discoverability_closure(memory_graph: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    required_path = "docs/final-remediation-closure-pack.md"
    missing_discovery_docs: list[str] = []
    for relative_path in DISCOVERY_TARGETS:
        text = _read(relative_path)
        if required_path not in text:
            missing_discovery_docs.append(relative_path)
    if missing_discovery_docs:
        errors.append(f"Closure pack is not discoverable from required docs: {missing_discovery_docs}")

    nodes = {node.get("id"): node for node in memory_graph.get("nodes", [])}
    required_nodes = {
        "final_remediation_closure_pack_doc": "docs/final-remediation-closure-pack.md",
        "final_remediation_closure_pack_json": "data/contracts/final-remediation-closure-pack.json",
        "final_remediation_closure_pack_generator": GENERATOR,
    }
    missing_memory_nodes = [
        node_id
        for node_id, path in required_nodes.items()
        if nodes.get(node_id, {}).get("path") != path
    ]
    if missing_memory_nodes:
        errors.append(f"Agent memory graph is missing closure pack nodes: {missing_memory_nodes}")

    return {
        "required_docs": list(DISCOVERY_TARGETS),
        "missing_discovery_docs": missing_discovery_docs,
        "memory_graph_source": "data/contracts/agent-memory-graph.json",
        "memory_graph_nodes": required_nodes,
        "missing_memory_nodes": missing_memory_nodes,
    }


def _active_scope_closure(errors: list[str]) -> dict[str, Any]:
    legacy = _load_json("data/contracts/legacy-lane-boundaries.json")
    ai = _load_json("data/contracts/ai-commodity-isolation.json")
    lanes = {lane.get("lane_id"): lane for lane in legacy.get("lanes", [])}
    expected_status = {
        "regular_supervised_options_browser": "active_browser_product",
        "ai_commodity_proof_lane": "separate_non_browser_proof_lane",
        "day_trading": "paused_out_of_scope",
        "crypto_options_sidecar": "paused_out_of_scope",
        "polymarket_sidecar": "paused_out_of_scope",
    }
    mismatches: list[dict[str, str | None]] = []
    for lane_id, expected in expected_status.items():
        actual = lanes.get(lane_id, {}).get("status")
        if actual != expected:
            mismatches.append({"lane_id": lane_id, "expected": expected, "actual": actual})
    if ai.get("lane", {}).get("status") != "separate_non_browser_proof_lane":
        mismatches.append(
            {
                "lane_id": "ai_commodity_isolation_detail",
                "expected": "separate_non_browser_proof_lane",
                "actual": ai.get("lane", {}).get("status"),
            }
        )
    if mismatches:
        errors.append(f"Active scope boundary mismatches are present: {mismatches}")

    return {
        "legacy_lane_boundary_source": "data/contracts/legacy-lane-boundaries.json",
        "ai_commodity_isolation_source": "data/contracts/ai-commodity-isolation.json",
        "expected_status": expected_status,
        "actual_status": {lane_id: lanes.get(lane_id, {}).get("status") for lane_id in expected_status},
        "ai_commodity_detail_status": ai.get("lane", {}).get("status"),
        "mismatches": mismatches,
    }


def _package_closure(errors: list[str]) -> dict[str, Any]:
    scripts = _package_scripts()
    owner_command = scripts.get("docs:final-remediation-closure-pack", "")
    verify_docs = scripts.get("verify:docs", "")
    if GENERATOR not in owner_command:
        errors.append("docs:final-remediation-closure-pack must run the closure generator.")
    if GENERATOR not in verify_docs:
        errors.append("verify:docs must check the closure generator.")
    return {
        "owner_command": "docs:final-remediation-closure-pack",
        "owner_command_present": "docs:final-remediation-closure-pack" in scripts,
        "verify_docs_covers_generator": GENERATOR in verify_docs,
    }


def build_closure_pack() -> dict[str, Any]:
    errors: list[str] = []
    remediation = _load_json("data/contracts/remediation-loop-map.json")
    governance = _load_json("data/contracts/generated-artifact-governance.json")
    memory_graph = _load_json("data/contracts/agent-memory-graph.json")
    source_paths = [
        "data/contracts/remediation-loop-map.json",
        "data/contracts/generated-artifact-governance.json",
        "data/contracts/agent-memory-graph.json",
        "data/contracts/route-mutation-inventory.json",
        "data/contracts/backend-route-ownership-map.json",
        "data/contracts/storage-ownership-map.json",
        "data/contracts/legacy-lane-boundaries.json",
        "data/contracts/ai-commodity-isolation.json",
        "docs/index.md",
        "docs/living-docs-hygiene.md",
        "docs/architecture-overview.md",
        "docs/architecture-best-practices.md",
        "docs/WORKLOG.md",
        "package.json",
    ]

    missing_sources = _missing_paths(source_paths)
    if missing_sources:
        errors.append(f"Closure source paths are missing: {missing_sources}")

    closure = {
        "artifact": "final_remediation_closure_pack",
        "closure_version": 1,
        "generated_by": GENERATOR,
        "runtime_use": False,
        "scope": "Final generated readback proving the 44-point architecture/readability remediation loop is closed and discoverable.",
        "sources": source_paths,
        "non_goals": list(NON_GOALS),
        "loop_closure": _loop_closure(remediation, errors),
        "generated_artifact_closure": _generated_artifact_closure(governance, errors),
        "guard_artifact_closure": _guard_artifact_closure(errors),
        "discoverability_closure": _discoverability_closure(memory_graph, errors),
        "active_scope_closure": _active_scope_closure(errors),
        "package_closure": _package_closure(errors),
        "risk_boundaries": [
            "Closure is read-only generated metadata.",
            "Closure verifies existing generated artifacts and living-doc links.",
            "Closure does not change route/auth/payload/proof/scanner/replay/DB/frontend behavior.",
            "Closure does not claim product profitability or AI commodity proof completion.",
        ],
        "verification_ladder": list(VERIFICATION_LADDER),
        "validation": {"errors": []},
    }
    closure["validation"]["errors"] = errors
    closure["closure_status"] = "closed" if not errors else "blocked"
    return closure


def render_json(closure: dict[str, Any]) -> str:
    return json.dumps(closure, indent=2, sort_keys=True) + "\n"


def _md_cell(value: Any) -> str:
    if value in (None, ""):
        return "none"
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value) or "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(closure: dict[str, Any]) -> str:
    loop = closure["loop_closure"]
    generated = closure["generated_artifact_closure"]
    scope = closure["active_scope_closure"]
    discovery = closure["discoverability_closure"]
    lines = [
        "# Final Remediation Closure Pack",
        "",
        f"Generated by `{GENERATOR}`. Do not hand-edit this file.",
        "",
        "Runtime use: `false`.",
        "JSON sibling: `data/contracts/final-remediation-closure-pack.json`.",
        "",
        "This generated readback closes the 44-point architecture/readability remediation loop. It proves status from the loop map, generated artifact governance, agent memory graph, living-doc links, and lane-boundary guard artifacts.",
        "",
        "## Final Status",
        "",
        f"- Closure status: `{closure['closure_status']}`",
        f"- Completed points: `{loop['completed_points']}` / `{loop['total_points']}`",
        f"- Planned points: `{loop['planned_points']}`",
        f"- In-progress points: `{loop['in_progress_points']}`",
        f"- Next point: `{loop['next_point']}`",
        "",
        "## Evidence Sources",
        "",
    ]
    for source in closure["sources"]:
        lines.append(f"- `{source}`")

    lines.extend(
        [
            "",
            "## Generated Artifact Closure",
            "",
            f"- Governed artifact count: `{generated['governed_artifact_count']}`",
            f"- Closure artifacts governed: `{_md_cell(generated['closure_artifacts_governed'])}`",
            f"- Runtime generated artifacts: `{_md_cell(generated['runtime_generated_artifacts'])}`",
            "- Stale generated output rule: trust source inputs and owner generator over stale output; do not hand-edit generated artifacts.",
            "",
            "## Discoverability",
            "",
            f"- Closure document: `docs/final-remediation-closure-pack.md`",
            f"- Missing discovery docs: `{_md_cell(discovery['missing_discovery_docs'])}`",
            "- Future agent path: closure pack -> remediation loop map -> agent memory graph -> owner docs.",
            "",
            "## Active Scope",
            "",
            "| Lane | Expected status | Actual status |",
            "| --- | --- | --- |",
        ]
    )
    for lane_id, expected in scope["expected_status"].items():
        lines.append(f"| `{lane_id}` | `{expected}` | `{scope['actual_status'].get(lane_id)}` |")

    lines.extend(["", "## Guard Artifacts", "", "| Path | Artifact | Runtime use | Validation errors |", "| --- | --- | --- | --- |"])
    for artifact in closure["guard_artifact_closure"]:
        lines.append(
            f"| `{artifact['path']}` | `{artifact['artifact']}` | `{artifact['runtime_use']}` | `{artifact['validation_error_count']}` |"
        )

    lines.extend(["", "## Verification Ladder", ""])
    for command in closure["verification_ladder"]:
        lines.append(f"- `{command}`")

    lines.extend(["", "## Risk Boundaries", ""])
    for boundary in closure["risk_boundaries"]:
        lines.append(f"- {boundary}")

    lines.extend(["", "## Validation", ""])
    if closure["validation"]["errors"]:
        lines.extend(f"- {error}" for error in closure["validation"]["errors"])
    else:
        lines.append("- No validation errors.")

    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- {item}" for item in closure["non_goals"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the final remediation closure pack.")
    parser.add_argument("--check", action="store_true", help="Fail if final remediation closure outputs are stale.")
    args = parser.parse_args()

    closure = build_closure_pack()
    rendered_json = render_json(closure)
    rendered_md = render_markdown(closure)

    if args.check:
        errors: list[str] = []
        for path, rendered in ((JSON_OUTPUT_PATH, rendered_json), (MD_OUTPUT_PATH, rendered_md)):
            if not path.exists():
                errors.append(f"{_relative(path)} is missing; run this script without --check.")
            elif path.read_text(encoding="utf-8") != rendered:
                errors.append(f"{_relative(path)} is out of date; run this script without --check.")
        errors.extend(closure["validation"]["errors"])
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
