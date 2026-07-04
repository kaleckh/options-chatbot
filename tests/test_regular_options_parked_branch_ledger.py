from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_parked_branch_ledger as ledger


class ParkedBranchLedgerTests(unittest.TestCase):
    def test_build_ledger_reports_reconstruction_fields_and_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            branch = ledger.ParkedBranch(
                branch_id="sample_parked_branch",
                title="Sample parked branch",
                status="parked",
                blocker="sample blocker",
                revival_condition="new trusted data changes the blocker",
                script_path="scripts/sample.py",
                live_doc_path="docs/sample.md",
                archived_doc_path="docs/archive/sample.md",
                data_artifact_path="data/sample/latest.json",
            )
            for rel_path in [branch.script_path, branch.live_doc_path, branch.archived_doc_path, branch.data_artifact_path]:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("sample\n", encoding="utf-8")
            docs_index = root / "docs" / "index.md"
            docs_index.write_text("- `docs/sample.md`\n", encoding="utf-8")
            daily_ops = root / "scripts" / "run_daily_ops.py"
            daily_ops.write_text("DAILY_OP_STEPS = []\n", encoding="utf-8")

            report = ledger.build_ledger(root=root, docs_index=docs_index, daily_ops=daily_ops, branches=[branch])

        self.assertEqual(report["branch_count"], 1)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["data_artifacts_deleted"])
        row = report["branches"][0]
        self.assertTrue(row["script_exists"])
        self.assertTrue(row["archived_doc_exists"])
        self.assertTrue(row["data_artifact_exists"])
        self.assertTrue(row["referenced_from_live_index"])
        self.assertFalse(row["archived_doc_referenced_from_live_index"])
        self.assertEqual(row["revival_condition"], "new trusted data changes the blocker")

    def test_archived_doc_live_index_hygiene_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            branch = ledger.ParkedBranch(
                branch_id="sample_parked_branch",
                title="Sample parked branch",
                status="parked",
                blocker="sample blocker",
                revival_condition="new trusted data changes the blocker",
                script_path="scripts/sample.py",
                live_doc_path="docs/sample.md",
                archived_doc_path="docs/archive/sample.md",
                data_artifact_path="data/sample/latest.json",
            )
            docs_index = root / "docs" / "index.md"
            docs_index.parent.mkdir(parents=True, exist_ok=True)
            docs_index.write_text("- `docs/archive/sample.md`\n", encoding="utf-8")
            daily_ops = root / "scripts" / "run_daily_ops.py"
            daily_ops.parent.mkdir(parents=True, exist_ok=True)
            daily_ops.write_text("DAILY_OP_STEPS = []\n", encoding="utf-8")

            report = ledger.build_ledger(root=root, docs_index=docs_index, daily_ops=daily_ops, branches=[branch])

        self.assertEqual(ledger.archived_docs_referenced_from_live_index(report), ["docs/archive/sample.md"])
        rendered = ledger.render_markdown(report)
        self.assertIn("Sample parked branch", rendered)
        self.assertIn("new trusted data changes the blocker", rendered)


if __name__ == "__main__":
    unittest.main()
