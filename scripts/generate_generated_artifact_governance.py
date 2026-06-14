from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.generated_artifact_manifest import GENERATED_ARTIFACTS, GeneratedArtifact
except ModuleNotFoundError:  # pragma: no cover - direct script execution from scripts/
    from generated_artifact_manifest import GENERATED_ARTIFACTS, GeneratedArtifact


GENERATOR = "scripts/generate_generated_artifact_governance.py"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "generated-artifact-governance.json"
MD_OUTPUT_PATH = ROOT / "docs" / "generated-artifact-governance.md"

NON_GOALS = (
    "Does not govern volatile research runs, generated market-data outputs, DB sidecars, build output, archives, or dated evidence reports.",
    "Does not define route behavior, payloads, auth semantics, proof predicates, scanner policy, replay math, DB schema, or frontend behavior.",
    "Does not promote generated snapshots into runtime policy unless the artifact is already runtime-consumed generated code.",
    "Does not use timestamps, mtimes, content hashes, or network freshness checks.",
)

EXCLUDED_ARTIFACT_CLASSES = (
    "docs/archive/**",
    "docs/autoresearch/**",
    "research_runs/**",
    "data/ai-commodity-infra/progress/**",
    "data/options-validation/**",
    "data/options-profit/**",
    ".next/**",
    "*.db, *.db-wal, *.db-shm",
)

SOURCE_INPUTS_BY_GENERATOR = {
    "scripts/generate_route_parity.py": (
        "src/app/api",
        "python-backend",
        "src/lib/trading-desk/storeOwnership.ts",
        "src/lib/strategy-lab/replayIntent.ts",
        "src/lib/route-lifecycle/routeContracts.ts",
    ),
    "scripts/generate_backend_route_ownership_map.py": (
        "data/contracts/route-mutation-inventory.json",
        "python-backend/main.py",
        "python-backend/profile_routes.py",
        "python-backend/predictions_routes.py",
        "python-backend/tools_routes.py",
    ),
    "scripts/generate_storage_ownership_map.py": (
        "data/contracts/route-mutation-inventory.json",
        "python-backend/repository_migrations.py",
        "python-backend/repository_constraints.py",
        "python-backend/repository_indexes.py",
        "python-backend/local_db_hardening.py",
        "python-backend/repository_parity.py",
    ),
    "scripts/generate_trading_desk_schema_bridge.py": (
        "src/lib/trading-desk/storeOwnership.ts",
        "src/lib/trading-desk/apiContracts.ts",
        "python-backend/trading_desk_api_models.py",
    ),
    "scripts/generate_proof_evidence_contract.py": ("data/contracts/proof-evidence-contract.json",),
    "scripts/candidate_lifecycle.py": ("scripts/candidate_lifecycle.py",),
    "scripts/generate_proof_invariant_table.py": ("data/contracts/proof-invariant-cases.json",),
    "scripts/generate_legacy_lane_boundaries.py": (
        "data/contracts/route-mutation-inventory.json",
        "docs/PROJECT_CONTEXT.md",
    ),
    "scripts/generate_ai_commodity_isolation.py": (
        "data/contracts/route-mutation-inventory.json",
        "data/contracts/storage-ownership-map.json",
        "data/ai-commodity-infra/progress/latest.json",
    ),
    "scripts/generate_remediation_loop_map.py": (
        "docs/WORKLOG.md",
        "docs/architecture-best-practices.md",
    ),
    "scripts/generate_project_pathway_registry.py": (
        "scripts/generate_project_pathway_registry.py",
        "docs/PROJECT_CONTEXT.md",
        "docs/index.md",
        "docs/NEXT_STEPS.md",
    ),
    "scripts/generate_agent_memory_graph.py": (
        "docs/architecture-best-practices.md",
        "docs/index.md",
    ),
    GENERATOR: (
        "scripts/generated_artifact_manifest.py",
        "scripts/check_living_docs_hygiene.py",
        "package.json",
    ),
    "scripts/generate_final_remediation_closure_pack.py": (
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
        "docs/architecture-best-practices.md",
        "docs/WORKLOG.md",
        "package.json",
    ),
    "scripts/generate_forward_holdout_contract.py": (
        "scripts/generate_forward_holdout_contract.py",
        "scripts/run_regular_options_goal_experiment.py",
        "scripts/evaluate_regular_options_autoresearch.py",
        "docs/PROJECT_CONTEXT.md",
        "docs/NEXT_STEPS.md",
    ),
}

OWNER_DOCS_BY_GENERATOR = {
    "scripts/generate_route_parity.py": ("docs/route-parity.md", "docs/api-and-storage.md"),
    "scripts/generate_backend_route_ownership_map.py": ("docs/backend-route-ownership-map.md", "docs/api-and-storage.md"),
    "scripts/generate_storage_ownership_map.py": ("docs/storage-ownership-map.md", "docs/api-and-storage.md"),
    "scripts/generate_trading_desk_schema_bridge.py": ("docs/trading-desk-schema-bridge.md", "docs/typescript-api-contracts.md", "docs/trading-desk-api-models.md"),
    "scripts/generate_proof_evidence_contract.py": ("docs/proof-evidence-contract.md",),
    "scripts/candidate_lifecycle.py": ("docs/candidate-lifecycle-contract.md", "docs/scanner-creation-safety-contract.md"),
    "scripts/generate_proof_invariant_table.py": ("docs/proof-invariant-table.md", "docs/proof-evidence-contract.md"),
    "scripts/generate_legacy_lane_boundaries.py": ("docs/legacy-lane-boundaries.md", "docs/PROJECT_CONTEXT.md"),
    "scripts/generate_ai_commodity_isolation.py": ("docs/ai-commodity-isolation.md", "docs/PROJECT_CONTEXT.md"),
    "scripts/generate_remediation_loop_map.py": ("docs/remediation-loop-map.md", "docs/architecture-best-practices.md"),
    "scripts/generate_project_pathway_registry.py": ("docs/project-operating-map.md", "docs/PROJECT_CONTEXT.md", "docs/NEXT_STEPS.md"),
    "scripts/generate_agent_memory_graph.py": ("docs/agent-memory-graph.md", "docs/index.md"),
    GENERATOR: ("docs/generated-artifact-governance.md", "docs/living-docs-hygiene.md"),
    "scripts/generate_final_remediation_closure_pack.py": ("docs/final-remediation-closure-pack.md", "docs/remediation-loop-map.md"),
    "scripts/generate_forward_holdout_contract.py": ("docs/forward-holdout-contract.md", "docs/PROJECT_CONTEXT.md"),
}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _artifact_id(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_package_scripts() -> dict[str, str]:
    return dict(json.loads(_read("package.json"))["scripts"])


def _trust_role(artifact: GeneratedArtifact) -> str:
    if artifact.path == "src/lib/generated/proofEvidenceContract.ts":
        return "generated_runtime_bridge"
    if artifact.path.endswith(".json"):
        return "machine_readable_check"
    if "remediation-loop-map" in artifact.path:
        return "handoff_ledger"
    if "final-remediation-closure-pack" in artifact.path:
        return "closure_readback"
    if "proof-invariant-table" in artifact.path:
        return "test_readability_projection"
    return "generated_readability_doc"


def _source_of_truth_role(artifact: GeneratedArtifact) -> str:
    if artifact.path == "src/lib/generated/proofEvidenceContract.ts":
        return "generated runtime projection of data/contracts/proof-evidence-contract.json"
    if "proof-invariant" in artifact.path:
        return "derived test/readability projection"
    if "final-remediation-closure-pack" in artifact.path:
        return "derived final closure readback from checked generated artifacts and living docs"
    return "derived snapshot from generator source inputs"


def _runtime_posture(artifact: GeneratedArtifact) -> str:
    if artifact.path == "src/lib/generated/proofEvidenceContract.ts":
        return "generated_frontend_runtime_policy"
    return "non_runtime_metadata"


def _governed_artifact(artifact: GeneratedArtifact, scripts: dict[str, str]) -> dict[str, Any]:
    return {
        "id": _artifact_id(artifact.path),
        "path": artifact.path,
        "artifact_type": artifact.artifact_type,
        "generator": artifact.generator,
        "owner_command": artifact.command,
        "check_command": f"uv run --locked python {artifact.generator} --check",
        "verify_docs_covered": artifact.generator in scripts.get("verify:docs", ""),
        "owner_docs": list(OWNER_DOCS_BY_GENERATOR.get(artifact.generator, ("docs/living-docs-hygiene.md",))),
        "source_inputs": list(SOURCE_INPUTS_BY_GENERATOR.get(artifact.generator, (artifact.generator,))),
        "trust_role": _trust_role(artifact),
        "source_of_truth_role": _source_of_truth_role(artifact),
        "runtime_use": not artifact.runtime_use_false,
        "runtime_posture": _runtime_posture(artifact),
        "source_of_truth_for_runtime": artifact.path == "src/lib/generated/proofEvidenceContract.ts",
        "stale_detection": "owner generator --check in npm run verify:docs",
        "stale_action": f"Do not hand-edit; run npm run {artifact.command}. Trust the source inputs and generator over stale output.",
        "hand_edit_allowed": False,
        "must_not_claim": [
            "independent route behavior",
            "auth semantics",
            "proof/scanner/replay semantics",
            "database schema",
            "frontend behavior beyond declared runtime projection",
        ],
    }


def _narrow_generated_marker_paths() -> set[str]:
    paths: set[str] = set()
    for path in (ROOT / "docs").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^Generated by `scripts/", text):
            paths.add(_relative(path))
    for path in (ROOT / "data" / "contracts").glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "generated_by" in payload:
            paths.add(_relative(path))
    generated_root = ROOT / "src" / "lib" / "generated"
    if generated_root.exists():
        for path in generated_root.glob("*"):
            if path.is_file() and "Generated by" in path.read_text(encoding="utf-8"):
                paths.add(_relative(path))
    return paths


def _validate_artifact(
    artifact: GeneratedArtifact,
    scripts: dict[str, str],
    *,
    allow_output_paths: bool,
) -> list[str]:
    errors: list[str] = []
    artifact_path = ROOT / artifact.path
    generator_path = ROOT / artifact.generator
    output_paths = {JSON_OUTPUT_PATH, MD_OUTPUT_PATH}
    if not artifact_path.exists() and not (allow_output_paths and artifact_path in output_paths):
        errors.append(f"Governed artifact path is missing: {artifact.path}")
        return errors
    if not generator_path.exists():
        errors.append(f"Generator path is missing for {artifact.path}: {artifact.generator}")
    if artifact.command not in scripts:
        errors.append(f"Owner command is missing for {artifact.path}: {artifact.command}")
    elif artifact.generator not in scripts[artifact.command]:
        errors.append(f"Owner command {artifact.command} does not run {artifact.generator}")
    if artifact.generator not in scripts.get("verify:docs", ""):
        errors.append(f"verify:docs does not check {artifact.generator}")

    if not artifact_path.exists():
        return errors

    if artifact.artifact_type == "json":
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if payload.get("generated_by") != artifact.generator:
            errors.append(f"{artifact.path} generated_by does not match {artifact.generator}")
        if artifact.runtime_use_false and payload.get("runtime_use") is not False:
            errors.append(f"{artifact.path} must declare runtime_use=false")
    else:
        text = artifact_path.read_text(encoding="utf-8")
        if "Generated by" not in text or artifact.generator not in text:
            errors.append(f"{artifact.path} must name generator {artifact.generator}")
        if "Do not hand-edit" not in text and "Edit the generator" not in text:
            errors.append(f"{artifact.path} must include a do-not-hand-edit or edit-generator banner")
    return errors


def _validate_governance(governance: dict[str, Any], *, allow_output_paths: bool) -> list[str]:
    errors: list[str] = []
    scripts = _load_package_scripts()
    manifest_paths = [artifact.path for artifact in GENERATED_ARTIFACTS]
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("Generated artifact manifest contains duplicate paths.")
    ids = [artifact["id"] for artifact in governance["governed_artifacts"]]
    if len(ids) != len(set(ids)):
        errors.append("Generated artifact governance contains duplicate ids.")
    for artifact in GENERATED_ARTIFACTS:
        errors.extend(_validate_artifact(artifact, scripts, allow_output_paths=allow_output_paths))
    governed_paths = {artifact["path"] for artifact in governance["governed_artifacts"]}
    if governed_paths != set(manifest_paths):
        errors.append("Governed artifact paths drifted from scripts/generated_artifact_manifest.py.")
    marker_paths = _narrow_generated_marker_paths()
    ungoverned_marker_paths = sorted(marker_paths - set(manifest_paths))
    if ungoverned_marker_paths:
        errors.append(f"Generated marker paths are not governed: {ungoverned_marker_paths}")
    runtime_artifacts = sorted(
        artifact["path"] for artifact in governance["governed_artifacts"] if artifact["runtime_use"]
    )
    if runtime_artifacts != ["src/lib/generated/proofEvidenceContract.ts"]:
        errors.append(f"Unexpected generated runtime-use artifacts: {runtime_artifacts}")
    for relative_path in (
        "docs/index.md",
        "docs/living-docs-hygiene.md",
        "docs/architecture-best-practices.md",
        "docs/architecture-overview.md",
        "docs/agent-memory-graph.md",
        "docs/remediation-loop-map.md",
    ):
        path = ROOT / relative_path
        if not path.exists():
            errors.append(f"Discovery doc is missing: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "docs/generated-artifact-governance.md" not in text:
            errors.append(f"{relative_path} does not discover docs/generated-artifact-governance.md")
    return errors


def build_governance() -> dict[str, Any]:
    scripts = _load_package_scripts()
    governed = [_governed_artifact(artifact, scripts) for artifact in GENERATED_ARTIFACTS]
    governance = {
        "artifact": "generated_artifact_governance",
        "governance_version": 1,
        "generated_by": GENERATOR,
        "runtime_use": False,
        "scope": "Generated trust-boundary and stale-handling inventory for checked generated docs, contracts, and runtime-generated policy artifacts.",
        "sources": [
            "scripts/generated_artifact_manifest.py",
            "scripts/check_living_docs_hygiene.py",
            "package.json",
        ],
        "non_goals": list(NON_GOALS),
        "excluded_artifact_classes": list(EXCLUDED_ARTIFACT_CLASSES),
        "supporting_source_inputs": {
            generator: list(inputs)
            for generator, inputs in sorted(SOURCE_INPUTS_BY_GENERATOR.items())
        },
        "governed_artifacts": governed,
        "validation": {"errors": []},
    }
    governance["validation"]["errors"] = _validate_governance(governance, allow_output_paths=True)
    return governance


def render_json(governance: dict[str, Any]) -> str:
    return json.dumps(governance, indent=2, sort_keys=True) + "\n"


def _md_cell(value: Any) -> str:
    if value in (None, ""):
        return "none"
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value) or "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(governance: dict[str, Any]) -> str:
    lines = [
        "# Generated Artifact Governance",
        "",
        f"Generated by `{GENERATOR}`. Do not hand-edit this file.",
        "",
        "Runtime use: `false`.",
        "JSON sibling: `data/contracts/generated-artifact-governance.json`.",
        "",
        "This inventory explains which generated artifacts are checked, what owns them, how stale output is handled, and which generated files are runtime-consumed.",
        "",
        "## How To Use This",
        "",
        "- If a generated artifact is stale, run its owner command; do not edit the output file.",
        "- Trust source inputs and the generator over stale generated output.",
        "- Treat non-runtime generated docs/JSON as readability and drift-check metadata.",
        "- Treat `src/lib/generated/proofEvidenceContract.ts` as the single generated runtime-consumed policy projection.",
        "",
        "## Governed Artifacts",
        "",
        "| Artifact | Type | Runtime posture | Trust role | Owner command | Generator | Stale action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for artifact in governance["governed_artifacts"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(artifact["path"]),
                    _md_cell(artifact["artifact_type"]),
                    _md_cell(artifact["runtime_posture"]),
                    _md_cell(artifact["trust_role"]),
                    _md_cell(f"npm run {artifact['owner_command']}"),
                    _md_cell(artifact["generator"]),
                    _md_cell(artifact["stale_action"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Excluded Artifact Classes", ""])
    for excluded in governance["excluded_artifact_classes"]:
        lines.append(f"- `{excluded}`")

    lines.extend(["", "## Validation", ""])
    errors = governance["validation"]["errors"]
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- No validation errors.")

    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- {item}" for item in governance["non_goals"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate generated-artifact governance artifacts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifact governance outputs are stale.")
    args = parser.parse_args()

    governance = build_governance()
    rendered_json = render_json(governance)
    rendered_md = render_markdown(governance)

    if args.check:
        errors: list[str] = []
        for path, rendered in ((JSON_OUTPUT_PATH, rendered_json), (MD_OUTPUT_PATH, rendered_md)):
            if not path.exists():
                errors.append(f"{_relative(path)} is missing; run this script without --check.")
            elif path.read_text(encoding="utf-8") != rendered:
                errors.append(f"{_relative(path)} is out of date; run this script without --check.")
        errors.extend(_validate_governance(governance, allow_output_paths=False))
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
