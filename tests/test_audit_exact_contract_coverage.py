from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.audit_exact_contract_coverage import build_exact_coverage_audit, find_duplicate_exact_coverage_audit
from workspace_tempdir import WorkspaceTempDir


class AuditExactContractCoverageTests(unittest.TestCase):
    def test_build_exact_coverage_audit_splits_exact_and_nearest(self):
        tmp = WorkspaceTempDir(prefix="exact-coverage")
        self.addCleanup(tmp.cleanup)
        run_path = Path(tmp.name) / "run.json"
        run_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "pricing_lane": "pessimistic",
                    "lookback_years": 3,
                    "quote_coverage_pct": 98.5,
                    "trades": [
                        {
                            "ticker": "SPY",
                            "date": "2025-01-02",
                            "entry_contract_resolution": "exact_target_contract",
                        },
                        {
                            "ticker": "SPY",
                            "date": "2025-01-03",
                            "entry_contract_resolution": "nearest_listed_contract",
                        },
                        {
                            "ticker": "QQQ",
                            "date": "2025-02-03",
                            "entry_contract_resolution": "nearest_listed_contract",
                        },
                        {
                            "ticker": "QQQ",
                            "date": "2025-02-04",
                            "entry_contract_resolution": "exact_archived_contract",
                        },
                    ],
                }
            ),
            encoding="utf8",
        )

        audit = build_exact_coverage_audit(run_path)

        self.assertEqual(audit["overall"]["total"], 4)
        self.assertEqual(audit["overall"]["exact"], 2)
        self.assertEqual(audit["overall"]["nearest"], 2)
        self.assertEqual(audit["authoritative_exact"]["total"], 2)
        self.assertEqual(audit["research_nearest_listed"]["total"], 2)
        self.assertEqual(audit["contract_accounting"]["exact_contract_match_count"], 2)
        self.assertEqual(audit["by_ticker"][0]["key"], "QQQ")
        self.assertTrue(audit["audit_fingerprint"])

    def test_find_duplicate_exact_coverage_audit_uses_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="exact-coverage-dupe")
        self.addCleanup(tmp.cleanup)
        audit_dir = Path(tmp.name)
        audit_path = audit_dir / "exact_coverage_audit_test.json"
        audit_path.write_text(json.dumps({"audit_fingerprint": "abc123"}), encoding="utf8")

        self.assertEqual(find_duplicate_exact_coverage_audit(audit_dir, "abc123"), audit_path)


if __name__ == "__main__":
    unittest.main()
