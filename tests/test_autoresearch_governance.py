import json
import tempfile
import unittest
from pathlib import Path

from scripts.autoresearch_governance import (
    generate_current_state,
    load_phase_manifest,
    record_decision_closure,
    render_queue_md,
)


class AutoresearchGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / "docs" / "autoresearch"
        self.docs.mkdir(parents=True, exist_ok=True)
        (self.docs / "phase.json").write_text(
            json.dumps(
                {
                    "phase_id": "truth-first",
                    "mode": "validation",
                    "freeze_search": True,
                    "allowed_truth_lanes": ["synthetic_research", "historical_imported_daily", "historical_imported"],
                    "required_watchlist": ["SPY", "QQQ"],
                    "required_baseline_control": "baseline",
                    "cohorts": [
                        {
                            "id": "baseline",
                            "role": "control",
                            "label": "Baseline",
                            "playbooks": ["broad"],
                            "overrides": {},
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (self.docs / "queue.json").write_text(
            json.dumps(
                {
                    "active": [{"slug": "sample-run", "status": "running", "summary": "Sample"}],
                    "frozen": [],
                    "historical": [],
                },
                indent=2,
            ),
            encoding="utf8",
        )

        self.run_dir = self.root / "research_runs" / "20260331_sample-run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "slug": "sample-run",
                    "mode": "validation",
                    "phase_id": "truth-first",
                    "cohort_id": "baseline",
                },
                indent=2,
            ),
            encoding="utf8",
        )
        (self.run_dir / "decision_packet.json").write_text(
            json.dumps(
                {
                    "recommended_verdict": "hold",
                    "recommended_stage": "holdout_recording",
                    "evidence_state": "insufficient_support",
                    "validation_outcome": "insufficient_support",
                    "authoritative_truth_source": "forward_holdout",
                    "next_allowed_action": "continue_holdout_recording",
                    "strongest_supporting_evidence": ["forward holdout exists"],
                    "strongest_counterargument": ["not enough closed reviews"],
                    "normalized_block_reasons": ["insufficient_support"],
                },
                indent=2,
            ),
            encoding="utf8",
        )

    def test_record_decision_closure_updates_queue_and_state(self):
        closure = record_decision_closure(
            root_dir=self.root,
            run_dir=self.run_dir,
            final_verdict="hold",
            approver="tester",
            rationale="Need more holdout evidence.",
            advance_queue_state=True,
            phase_manifest_path=self.docs / "phase.json",
            queue_json_path=self.docs / "queue.json",
        )

        self.assertEqual(closure["final_verdict"], "hold")
        queue_payload = json.loads((self.docs / "queue.json").read_text(encoding="utf8"))
        self.assertEqual(queue_payload["active"], [])
        self.assertEqual(queue_payload["historical"][0]["slug"], "sample-run")

        current_state = json.loads((self.docs / "current-state.json").read_text(encoding="utf8"))
        self.assertEqual(current_state["phase_id"], "truth-first")
        self.assertEqual(current_state["validation_scope_symbols"], ["SPY", "QQQ"])

        decision_log = (self.docs / "decision-log.md").read_text(encoding="utf8")
        self.assertIn("sample-run", decision_log)

    def test_generate_current_state_renders_queue_sections(self):
        phase_manifest = load_phase_manifest(self.docs / "phase.json")
        queue_payload = json.loads((self.docs / "queue.json").read_text(encoding="utf8"))
        current_state = generate_current_state(
            self.root,
            phase_manifest=phase_manifest,
            queue_payload=queue_payload,
            output_md=self.docs / "state.md",
            output_json=self.docs / "state.json",
        )
        queue_md = render_queue_md(queue_payload)

        self.assertEqual(current_state["phase_id"], "truth-first")
        self.assertEqual(current_state["validation_scope_symbols"], ["SPY", "QQQ"])
        self.assertIn("## Active", queue_md)


if __name__ == "__main__":
    unittest.main()
