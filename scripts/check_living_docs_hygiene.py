from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.generated_artifact_manifest import GENERATED_ARTIFACTS, GeneratedArtifact
except ModuleNotFoundError:  # pragma: no cover - direct script execution from scripts/
    from generated_artifact_manifest import GENERATED_ARTIFACTS, GeneratedArtifact


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON_PATH = ROOT / "package.json"

CORE_LIVING_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/index.md",
    "docs/living-docs-hygiene.md",
    "docs/PROJECT_CONTEXT.md",
    "docs/DECISIONS.md",
    "docs/WORKLOG.md",
    "docs/NEXT_STEPS.md",
    "docs/architecture-overview.md",
    "docs/architecture-best-practices.md",
    "docs/architecture-audit.md",
)

SOURCE_OF_TRUTH_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/index.md",
    "docs/living-docs-hygiene.md",
)

PLACEHOLDER_PATTERN = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_package_scripts() -> dict[str, str]:
    package = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    return dict(package["scripts"])


def _json(relative_path: str) -> dict[str, Any]:
    return json.loads(_read(relative_path))


def _contains_path(text: str, relative_path: str) -> bool:
    return relative_path in text or Path(relative_path).name in text


def check_living_docs_hygiene() -> list[str]:
    errors: list[str] = []
    scripts = _load_package_scripts()
    docs_index = _read("docs/index.md")
    hygiene_doc = _read("docs/living-docs-hygiene.md")
    verify_docs = scripts.get("verify:docs", "")

    for relative_path in CORE_LIVING_DOCS:
        path = ROOT / relative_path
        if not path.exists():
            errors.append(f"Missing required living doc: {relative_path}")
            continue
        if relative_path != "docs/index.md" and not _contains_path(docs_index, relative_path):
            errors.append(f"docs/index.md does not link required living doc: {relative_path}")
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER_PATTERN.search(text):
            errors.append(f"Placeholder marker found in core living doc: {relative_path}")

    for relative_path in SOURCE_OF_TRUTH_DOCS:
        text = _read(relative_path).lower()
        if "source of truth" not in text and "source-of-truth" not in text:
            errors.append(f"{relative_path} must state the source-of-truth boundary.")
        if "evidence record" not in text and "records" not in text:
            errors.append(f"{relative_path} must distinguish historical/generated records from living docs.")

    for heading in (
        "## Living Owners",
        "## Evidence Records",
        "## Generated Artifacts",
        "## Hygiene Rules",
        "## Verification",
        "## Non-Goals",
    ):
        if heading not in hygiene_doc:
            errors.append(f"docs/living-docs-hygiene.md is missing heading {heading!r}.")
    if "docs/generated-artifact-governance.md" not in hygiene_doc:
        errors.append("docs/living-docs-hygiene.md must link docs/generated-artifact-governance.md.")

    if not re.search(r"^Last updated:\s+\d{4}-\d{2}-\d{2}$", _read("docs/NEXT_STEPS.md"), re.MULTILINE):
        errors.append("docs/NEXT_STEPS.md must include 'Last updated: YYYY-MM-DD'.")
    if not re.search(r"^##\s+\d{4}-\d{2}-\d{2}$", _read("docs/WORKLOG.md"), re.MULTILINE):
        errors.append("docs/WORKLOG.md must contain dated '## YYYY-MM-DD' sections.")
    if "Durable decision:" not in _read("docs/DECISIONS.md"):
        errors.append("docs/DECISIONS.md must contain durable-decision language.")

    for artifact in GENERATED_ARTIFACTS:
        path = ROOT / artifact.path
        if not path.exists():
            errors.append(f"Missing generated artifact: {artifact.path}")
            continue
        if artifact.command not in scripts:
            errors.append(f"package.json is missing generated artifact command: {artifact.command}")
        if artifact.generator not in scripts.get(artifact.command, ""):
            errors.append(f"{artifact.command} does not run {artifact.generator}")
        if artifact.generator not in verify_docs:
            errors.append(f"verify:docs does not check {artifact.generator}")
        if artifact.path not in docs_index:
            errors.append(f"docs/index.md does not link generated artifact: {artifact.path}")
        if artifact.artifact_type == "json":
            payload = _json(artifact.path)
            if payload.get("generated_by") != artifact.generator:
                errors.append(f"{artifact.path} generated_by does not match {artifact.generator}")
            if artifact.runtime_use_false and payload.get("runtime_use") is not False:
                errors.append(f"{artifact.path} must declare runtime_use=false")
        else:
            text = path.read_text(encoding="utf-8")
            if "Generated by" not in text or artifact.generator not in text:
                errors.append(f"{artifact.path} must name generator {artifact.generator}")
            if "Do not hand-edit" not in text and "Edit the generator" not in text:
                errors.append(f"{artifact.path} must include a do-not-hand-edit or edit-generator banner")

    if "scripts/check_living_docs_hygiene.py" not in verify_docs:
        errors.append("verify:docs must include scripts/check_living_docs_hygiene.py")
    if "docs:living-docs-hygiene" not in scripts:
        errors.append("package.json is missing docs:living-docs-hygiene")
    elif "scripts/check_living_docs_hygiene.py" not in scripts["docs:living-docs-hygiene"]:
        errors.append("docs:living-docs-hygiene must run scripts/check_living_docs_hygiene.py")

    return errors


def main() -> int:
    errors = check_living_docs_hygiene()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
