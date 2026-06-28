from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_preregistered_playbook_readiness_selector as selector
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class PreregisteredPlaybookReadinessSelectorTests(unittest.TestCase):
    def _playbook(self, concept_id: str, structure: str) -> dict:
        return {
            "report_id": f"{concept_id}_report",
            "generated_at_utc": "2026-06-23T00:00:00Z",
            "status": "preregistered_design_only",
            "concept_id": concept_id,
            "structure": structure,
            **selector.READ_ONLY_FLAGS,
        }

    def _goal_loop(self, tmp: Path) -> Path:
        path = tmp / "goal.json"
        _write_json(
            path,
            {
                "report_id": "options_goal_loop",
                "current_decision_state": "underpowered_forward_evidence",
                "forward_evidence_accounting": {
                    "post_freeze_strict_exact_completed_rows": 0,
                    "minimum_required": 30,
                    "cohort_log_status": "missing",
                    "strict_usd_pf_lower_bound_5pct": None,
                    "live_entry_allowed": False,
                    "auto_track_allowed": False,
                    "broker_order_allowed": False,
                    "promotion_ready": False,
                },
            },
        )
        return path

    def _install_all_playbooks(self, tmp: Path, monkey_specs: list[dict]) -> list[dict]:
        specs = []
        for spec in monkey_specs:
            local = dict(spec)
            local["path"] = tmp / f"{spec['key']}.json"
            _write_json(local["path"], self._playbook(spec["concept_id"], spec["expected_structure"]))
            if spec.get("readiness_path"):
                local["readiness_path"] = tmp / f"{spec['key']}_readiness.json"
                blockers = ["known_blocker"] if spec["key"] in {"vrp_put_credit_spread", "term_structure_calendar_diagonal"} else []
                _write_json(local["readiness_path"], {"report_id": "readiness", "blockers": blockers})
            specs.append(local)
        return specs

    def test_selector_is_read_only_and_selects_one_candidate(self) -> None:
        with WorkspaceTempDir(prefix="playbook-selector") as tmp_dir:
            tmp = Path(tmp_dir)
            original = selector.PLAYBOOKS
            try:
                selector.PLAYBOOKS = tuple(self._install_all_playbooks(tmp, list(original)))
                report = selector.build_report(goal_loop_path=self._goal_loop(tmp), generated_at_utc="2026-06-23T01:00:00Z")
            finally:
                selector.PLAYBOOKS = original

        self.assertEqual(report["status"], "candidate_selected_for_research_only_implementation_approval")
        for key, expected in selector.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["lane_implementation_performed"])
        self.assertEqual(len(report["design_inventory"]), len(selector.PLAYBOOKS))
        self.assertEqual(
            report["top_ranked_candidate"]["concept_id"],
            "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
        )
        self.assertIsNone(report["recommended_operator_approval_question"])
        self.assertIn("no live validation", report["recommended_research_only_task_boundary"])
        self.assertIn("no broker orders", report["recommended_research_only_task_boundary"])
        self.assertIn("Do not ask an operator approval question", report["allowed_next_step"])

    def test_known_readiness_blockers_are_preserved(self) -> None:
        with WorkspaceTempDir(prefix="playbook-selector") as tmp_dir:
            tmp = Path(tmp_dir)
            original = selector.PLAYBOOKS
            try:
                selector.PLAYBOOKS = tuple(self._install_all_playbooks(tmp, list(original)))
                report = selector.build_report(goal_loop_path=self._goal_loop(tmp))
            finally:
                selector.PLAYBOOKS = original

        rows = {row["key"]: row for row in report["design_inventory"]}
        self.assertEqual(rows["vrp_put_credit_spread"]["readiness_status"], "blocked_by_known_readiness_audit")
        self.assertEqual(rows["term_structure_calendar_diagonal"]["readiness_status"], "blocked_by_known_readiness_audit")
        self.assertIn("known_blocker", rows["vrp_put_credit_spread"]["blockers"])
        self.assertIn("known_blocker", rows["term_structure_calendar_diagonal"]["blockers"])

    def test_pmcc_is_not_silently_skipped(self) -> None:
        with WorkspaceTempDir(prefix="playbook-selector") as tmp_dir:
            tmp = Path(tmp_dir)
            original = selector.PLAYBOOKS
            try:
                selector.PLAYBOOKS = tuple(self._install_all_playbooks(tmp, list(original)))
                report = selector.build_report(goal_loop_path=self._goal_loop(tmp))
            finally:
                selector.PLAYBOOKS = original

        rows = {row["key"]: row for row in report["design_inventory"]}
        self.assertIn("pmcc_diagonal_income", rows)
        self.assertEqual(rows["pmcc_diagonal_income"]["concept_id"], "low_mid_vix_index_pmcc_diagonal_income_v1")
        self.assertFalse(rows["pmcc_diagonal_income"]["accepted_profitability"])

    def test_missing_artifact_fails_to_named_blocker_without_mutation(self) -> None:
        with WorkspaceTempDir(prefix="playbook-selector") as tmp_dir:
            tmp = Path(tmp_dir)
            original = selector.PLAYBOOKS
            try:
                specs = self._install_all_playbooks(tmp, list(original))
                Path(specs[0]["path"]).unlink()
                selector.PLAYBOOKS = tuple(specs)
                report = selector.build_report(goal_loop_path=self._goal_loop(tmp))
            finally:
                selector.PLAYBOOKS = original

        rows = {row["key"]: row for row in report["design_inventory"]}
        self.assertEqual(rows["momentum_continuation_debit_spread"]["artifact_status"], "missing")
        self.assertIn("momentum_continuation_debit_spread", report["missing_preregistered_designs"])
        for key, expected in selector.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)

    def test_write_outputs_writes_docs_and_latest(self) -> None:
        with WorkspaceTempDir(prefix="playbook-selector") as tmp_dir:
            tmp = Path(tmp_dir)
            original = selector.PLAYBOOKS
            try:
                selector.PLAYBOOKS = tuple(self._install_all_playbooks(tmp, list(original)))
                report = selector.build_report(goal_loop_path=self._goal_loop(tmp))
                artifacts = selector.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "selector.md")
            finally:
                selector.PLAYBOOKS = original

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "selector.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "selector.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Preregistered Playbook Readiness Selector", markdown)
            self.assertIn("Recommended Research-Only Task Boundary", markdown)
            self.assertNotIn("Do you approve", markdown)


if __name__ == "__main__":
    unittest.main()
