import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import supervised_scan as ss
from scripts import log_scan_picks


CONTRACT_PATH = ROOT / "data" / "contracts" / "scanner-creation-safety-contract.json"
DOC_PATH = ROOT / "docs" / "scanner-creation-safety-contract.md"


class ScannerCreationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_exposes_canonical_modes_and_labels(self):
        self.assertEqual(self.contract["version"], 1)
        self.assertEqual(self.contract["creationModes"]["scanner"], "scanner")
        self.assertEqual(self.contract["creationModes"]["manualPaper"], "manual_paper")
        self.assertEqual(self.contract["creationModes"]["manualBroker"], "manual_broker")
        self.assertEqual(self.contract["trackingModes"]["autoTrack"], ss.POSITION_TRACKING_AUTO_TRACK)
        self.assertEqual(self.contract["trackingModes"]["paperReviewOnly"], ss.POSITION_TRACKING_PAPER_REVIEW_ONLY)
        self.assertEqual(self.contract["trackingModes"]["diagnosticOnly"], ss.POSITION_TRACKING_DIAGNOSTIC_ONLY)
        self.assertEqual(self.contract["trackingModes"]["disabled"], ss.POSITION_TRACKING_DISABLED)
        self.assertEqual(self.contract["proofScopes"]["regular"], ss.REGULAR_PROOF_SCOPE)
        self.assertEqual(self.contract["proofScopes"]["regularControl"], ss.REGULAR_CONTROL_PROOF_SCOPE)
        self.assertEqual(self.contract["proofScopes"]["commodity"], ss.COMMODITY_PROOF_SCOPE)
        self.assertEqual(
            self.contract["candidateExecutionLabels"]["executableOpraPaperCandidate"],
            ss.EXECUTABLE_OPRA_PAPER_CANDIDATE_LABEL,
        )

    def test_scanner_pipeline_stages_match_runtime_contract(self):
        runtime_stages = [
            {
                "id": stage["id"],
                "owner": stage["owner"],
                "emittedFields": stage["emitted_fields"],
            }
            for stage in ss.SCANNER_PIPELINE_STAGES
        ]
        contract_stages = self.contract["scannerPipelineStages"]
        self.assertEqual(contract_stages, runtime_stages)
        self.assertEqual(
            [stage["id"] for stage in contract_stages],
            [
                "playbook_resolution",
                "raw_candidate_generation",
                "scan_drop_diagnostics",
                "policy_gate",
                "policy_filter",
                "guardrail_annotation",
                "managed_selection",
                "payload_assembly",
                "forward_lineage_capture",
                "proof_classification",
                "creation_or_validation_disposition",
            ],
        )
        for stage in contract_stages:
            self.assertTrue(stage["owner"])
            self.assertTrue(stage["emittedFields"])

        stages_by_id = {stage["id"]: stage for stage in contract_stages}
        self.assertIn("creation_eligible", stages_by_id["guardrail_annotation"]["emittedFields"])
        self.assertIn("source_scan_session_id", stages_by_id["forward_lineage_capture"]["emittedFields"])
        self.assertIn("proof_class", stages_by_id["proof_classification"]["emittedFields"])
        self.assertIn("candidates[].outcome", stages_by_id["creation_or_validation_disposition"]["emittedFields"])
        self.assertIn("summary.outcome_counts", stages_by_id["creation_or_validation_disposition"]["emittedFields"])

    def test_scheduled_auto_track_blockers_match_gate_helper(self):
        allowed = {
            "playbook": {"id": "swing"},
            "market_open_at_run": True,
            "exposure_snapshot": {"available": True, "portfolio_caps_enforced": True},
        }
        self.assertEqual(log_scan_picks._scan_auto_track_blockers(allowed), [])

        blocked = {
            "playbook": {"id": "swing"},
            "exposure_snapshot": {"available": False, "portfolio_caps_enforced": False},
        }
        blockers = log_scan_picks._scan_auto_track_blockers(blocked)
        self.assertIn("market_not_open_or_unknown", blockers)
        self.assertIn("exposure_snapshot_unavailable", blockers)
        self.assertIn("portfolio_caps_not_enforced", blockers)
        self.assertTrue(set(blockers).issubset(set(self.contract["scheduledAutoTrack"]["blockers"])))

        with patch.dict("os.environ", {"OPTIONS_SCAN_AUTO_TRACK": "0"}):
            self.assertIn("auto_track_env_disabled", log_scan_picks._scan_auto_track_blockers(allowed))

    def test_contract_declares_creation_fields_and_pending_outcomes(self):
        scanner = self.contract["scannerOriginCreate"]
        self.assertIn("source_scan_session_id", scanner["requiredSourceFields"])
        self.assertIn("source_scan_event_key", scanner["requiredSourceFields"])
        self.assertIn("creation_eligible", scanner["requiredSourceFields"])
        self.assertIn("creation_eligible", scanner["requiredCurrentRerunFields"])
        self.assertIn("current_creation_eligible_not_true", scanner["hardBlockers"])
        self.assertEqual(
            set(self.contract["pendingValidation"]["outcomes"]),
            {"created", "duplicate", "blocked", "no_longer_matched", "paper_only", "proof_ineligible"},
        )

    def test_human_doc_points_to_contract_and_anchors(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("data/contracts/scanner-creation-safety-contract.json", doc)
        self.assertIn("Canonical Scanner Stage Map", doc)
        self.assertIn("scannerPipelineStages", doc)
        self.assertIn("guardrail_annotation", doc)
        self.assertIn("forward_lineage_capture", doc)
        self.assertIn("python-backend/main.py", doc)
        self.assertIn("scripts/log_scan_picks.py", doc)
        self.assertIn("scripts/validate_pending_scan_candidates.py", doc)
        self.assertIn("docs/proof-evidence-contract.md", doc)


if __name__ == "__main__":
    unittest.main()
