import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "architecture-best-practices.md"
INDEX_PATH = ROOT / "docs" / "index.md"
OVERVIEW_PATH = ROOT / "docs" / "architecture-overview.md"
AUDIT_PATH = ROOT / "docs" / "architecture-audit.md"
GOAL_PATH = ROOT / "docs" / "autoresearch" / "code-audit-remediation-goal.md"


class ArchitectureBestPracticesDocTests(unittest.TestCase):
    def test_target_doc_is_linked_from_living_docs(self):
        self.assertTrue(DOC_PATH.exists())
        for path in [INDEX_PATH, OVERVIEW_PATH, AUDIT_PATH, GOAL_PATH]:
            self.assertIn(
                "docs/architecture-best-practices.md",
                path.read_text(encoding="utf-8"),
                f"{path} should link the architecture target rubric",
            )

    def test_target_doc_names_required_architecture_bars(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        for token in [
            "## Architecture Principles",
            "## Boundary Acceptance Bars",
            "Read Versus Mutate",
            "Auth and mutation intent",
            "Proof and evidence",
            "Repository and database",
            "Generated artifacts",
            "## Verification Expectations",
            "## Docs Ownership",
            "## Non-Goals",
        ]:
            self.assertIn(token, doc)

    def test_target_doc_points_to_existing_owners_without_replacing_inventories(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        for owner in [
            "docs/architecture-overview.md",
            "docs/architecture-audit.md",
            "docs/route-parity.md",
            "docs/proof-evidence-contract.md",
            "docs/scanner-creation-safety-contract.md",
            "docs/replay-profit-contract.md",
            "docs/repository-contract.md",
            "docs/repository-migrations.md",
            "docs/repository-constraints.md",
            "docs/repository-indexes.md",
        ]:
            self.assertIn(owner, doc)

        for non_goal in [
            "generated route inventory",
            "storage ownership maps",
            "mutation inventory",
            "memory graph artifacts",
            "stale-artifact governance",
        ]:
            self.assertIn(non_goal, doc)

        self.assertNotIn("TBD", doc)
        self.assertNotIn("TODO", doc)


if __name__ == "__main__":
    unittest.main()
