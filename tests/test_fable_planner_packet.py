from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_fable_planner_packet as fable
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class FablePlannerPacketTests(unittest.TestCase):
    def test_build_packet_includes_schema_context_and_non_authority_rules(self) -> None:
        with WorkspaceTempDir(prefix="fable-planner") as tmp_raw:
            tmp = Path(tmp_raw)
            project_context = tmp / "PROJECT_CONTEXT.md"
            decisions = tmp / "DECISIONS.md"
            next_steps = tmp / "NEXT_STEPS.md"
            agent_control = tmp / "agent-control-plane.md"
            gateboard = tmp / "gateboard.json"
            oracle = tmp / "oracle.json"
            _write_text(project_context, "Project context: regular options only.")
            _write_text(decisions, "Decision: memory is orchestration only.")
            _write_text(next_steps, "Next: use Fable for planning.")
            _write_text(agent_control, "Control plane: task reports are not trading authority.")
            _write_json(
                gateboard,
                {
                    "report_id": "project_operator_gateboard",
                    "overall_status": "safe_blocked_no_live_release",
                    "no_chase_reasons": [{"reason": "no_live_validation_lanes"}],
                },
            )
            _write_json(
                oracle,
                {
                    "report_id": "options_oracle_profit_loop_packet",
                    "status": "ready_for_same_session_gpt55_guidance",
                    "safety_flags": {"broker_order_allowed": False},
                    "current_evidence_summary": {"forward_proof": {"strict_rows": 0}},
                },
            )

            packet = fable.build_packet(
                objective="Have Fable plan the next repo-safe implementation task.",
                project_context=project_context,
                decisions=decisions,
                next_steps=next_steps,
                agent_control=agent_control,
                gateboard=gateboard,
                oracle_packet=oracle,
            )

            self.assertEqual(packet["status"], "ready_for_fable_planning")
            self.assertEqual(packet["provider"]["model_id"], "claude-fable-5")
            self.assertFalse(packet["provider"]["api_call_implemented"])
            self.assertIn("selected_task", packet["plan_schema"])
            self.assertIn("safe_blocked_no_live_release", packet["prompt"])
            self.assertIn("does not authorize", packet["prompt"])

    def test_validate_plan_accepts_well_formed_non_authorizing_plan(self) -> None:
        plan = {
            "planner": "fable",
            "verdict": "implement",
            "selected_task": {
                "title": "Add packet docs",
                "objective": "Document the Fable handoff.",
                "why_now": "Planner coordination needs a repeatable path.",
                "scope": "Docs and tests only.",
                "non_goals": ["No provider call."],
                "files_to_read": ["docs/agent-control-plane.md"],
                "files_to_change": ["docs/fable-planner-bridge.md"],
                "commands": ["python -m pytest tests/test_fable_planner_packet.py -q"],
                "verification": ["Focused tests pass."],
                "acceptance_criteria": ["Packet schema is visible."],
                "failure_criteria": ["Validation rejects the plan."],
                "risks": ["Stale context."],
                "approval_required": [],
                "proof_boundary_statement": "This is orchestration only.",
            },
            "branch_statuses": [],
            "assumption_challenges": [],
            "operator_questions": [],
            "non_authorization_statement": (
                "This plan does not authorize trading, evidence mutation, scanner changes, proof-bar changes, "
                "broker action, promotion, live validation, stop/sizing changes, protected-holdout use, or treating "
                "historical rows as forward proof."
            ),
        }

        ok, errors = fable.validate_plan(plan)

        self.assertTrue(ok, errors)

    def test_validate_plan_rejects_authority_shaped_plan(self) -> None:
        plan = {
            "planner": "fable",
            "verdict": "implement",
            "selected_task": {
                "title": "Unsafe",
                "objective": "Authorize live validation.",
                "why_now": "n/a",
                "scope": "n/a",
                "non_goals": [],
                "files_to_read": [],
                "files_to_change": [],
                "commands": [],
                "verification": [],
                "acceptance_criteria": [],
                "failure_criteria": [],
                "risks": [],
                "approval_required": [],
                "proof_boundary_statement": "n/a",
            },
            "branch_statuses": [],
            "assumption_challenges": [],
            "operator_questions": [],
            "non_authorization_statement": "This plan does not authorize high-risk actions.",
        }

        ok, errors = fable.validate_plan(plan)

        self.assertFalse(ok)
        self.assertTrue(any("prohibited authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
