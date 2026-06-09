from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_risk_budget_sizing_replay as sizing


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _missed_outcome() -> dict:
    def row(playbook: str, ticker: str, scan_date: str, net_usd: float, net_pct: float) -> dict:
        return {
            "contract_symbol": f"{ticker}260626C00100000",
            "short_contract_symbol": f"{ticker}260626C00110000",
            "debit_pct_of_width": 25.0,
            "dte": 20,
            "mark": {
                "entry_debit": 2.0,
                "net_pnl_pct": net_pct,
                "net_pnl_usd": net_usd,
                "priced": True,
            },
            "net_debit": 2.0,
            "playbook": playbook,
            "scan_date": scan_date,
            "ticker": ticker,
            "tracked_match_count": 0,
        }

    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "rows": [
            row("short_term", "SPY", "2026-05-26", -100.0, -50.0),
            row("short_term", "QQQ", "2026-05-27", -80.0, -40.0),
            row("volatility_expansion_observation", "QQQ", "2026-06-01", 70.0, 35.0),
            row("volatility_expansion_observation", "IWM", "2026-06-02", 30.0, 15.0),
            row("speculative", "SPY", "2026-06-03", -20.0, -10.0),
            {**row("short_term", "MSFT", "2026-06-04", -10.0, -5.0), "tracked_match_count": 1},
        ],
    }


def _failure_modes() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_decisions": [
            {"playbook": "short_term", "decision": "diagnostic_only_until_earn_back", "blockers": []},
            {"playbook": "speculative", "decision": "diagnostic_only_until_earn_back", "blockers": []},
            {"playbook": "volatility_expansion_observation", "decision": "probation_candidate_flow_with_self_guardrails", "blockers": []},
        ],
        "failure_modes": {
            "by_playbook": [
                {
                    "key": "short_term",
                    "rows": 54,
                    "priced": 54,
                    "profit_factor": 0.0,
                    "avg_net_pnl_pct": -45.0,
                    "median_net_pnl_pct": -45.0,
                    "win_rate_pct": 0.0,
                    "sum_net_pnl_usd": -180.0,
                },
                {
                    "key": "speculative",
                    "rows": 1,
                    "priced": 1,
                    "profit_factor": 0.0,
                    "avg_net_pnl_pct": -10.0,
                    "median_net_pnl_pct": -10.0,
                    "win_rate_pct": 0.0,
                    "sum_net_pnl_usd": -20.0,
                },
                {
                    "key": "volatility_expansion_observation",
                    "rows": 2,
                    "priced": 2,
                    "profit_factor": 999.0,
                    "avg_net_pnl_pct": 25.0,
                    "median_net_pnl_pct": 25.0,
                    "win_rate_pct": 100.0,
                    "sum_net_pnl_usd": 100.0,
                },
            ]
        },
    }


def _lane_promotion_state() -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "lane_states": {
            "short_term": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "diagnostic",
                "candidate_status": "diagnostic_only_lane_promotion_state",
            },
            "speculative": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "diagnostic",
                "candidate_status": "diagnostic_only_lane_promotion_state",
            },
            "volatility_expansion_observation": {
                "tracking_mode": "auto_track",
                "fresh_live_validation_enabled": True,
                "promotion_state": "paper_probation",
                "candidate_status": "pending_paper_exact_evidence",
            },
        },
    }


def _open_risk(live_entry_allowed: bool = False) -> dict:
    return {
        "generated_at_utc": "2026-06-06T00:00:00Z",
        "live_policy_change": False,
        "open_risk_governor": {
            "status": "open_risk_governor_blocked" if not live_entry_allowed else "open_risk_governor_pass",
            "live_entry_allowed": live_entry_allowed,
            "live_exact_negative_ids": [537] if not live_entry_allowed else [],
            "blockers": ["live_exact_negative_open_risk"] if not live_entry_allowed else [],
        },
    }


class RegularOptionsRiskBudgetSizingReplayTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "missed_outcome_path": root / "missed_outcome.json",
            "failure_modes_path": root / "failure_modes.json",
            "lane_promotion_state_path": root / "lane_promotion.json",
            "open_risk_path": root / "open_risk.json",
            "multilane_portfolio_path": root / "multilane.json",
            "lane_quarantine_archive_path": root / "lane_quarantine.json",
        }
        _write_json(paths["missed_outcome_path"], _missed_outcome())
        _write_json(paths["failure_modes_path"], _failure_modes())
        _write_json(paths["lane_promotion_state_path"], _lane_promotion_state())
        _write_json(paths["open_risk_path"], _open_risk(False))
        _write_json(paths["multilane_portfolio_path"], {"quality_gate": {"overall_status": "quality_pending"}})
        _write_json(paths["lane_quarantine_archive_path"], {"status": "lane_quarantine_archive_readback", "archived_lanes": []})
        return paths

    def test_sizing_replay_builds_research_scenarios_without_live_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            report = sizing.build_report(**paths, generated_at_utc="2026-06-06T02:00:00Z")

        self.assertEqual(report["status"], "risk_budget_sizing_replay_readback")
        self.assertEqual(report["summary"]["overall_status"], "sizing_replay_built_open_risk_blocked")
        self.assertEqual(report["summary"]["source_row_count"], 5)
        self.assertEqual(report["summary"]["baseline_net_pnl_usd"], -100.0)
        self.assertEqual(report["summary"]["best_research_scenario_id"], "paper_shadow_only")
        self.assertEqual(report["summary"]["best_research_net_pnl_usd"], 100.0)
        self.assertFalse(report["summary"]["promotion_ready"])
        self.assertIn("open_risk_governor_blocks_sizing", report["summary"]["blockers"])
        scenarios = {row["scenario_id"]: row for row in report["scenarios"]}
        self.assertEqual(scenarios["paper_shadow_only"]["net_pnl_usd"], 100.0)
        self.assertEqual(scenarios["current_governor_zero_new_risk"]["risk_unit_count"], 0.0)
        lanes = {row["lane"]: row for row in report["lane_budget_table"]}
        self.assertEqual(lanes["short_term"]["disposition"], "quarantine")
        self.assertEqual(lanes["volatility_expansion_observation"]["paper_shadow_only_weight"], 1.0)

    def test_missing_inputs_block_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = sizing.build_report(
                missed_outcome_path=root / "missing.json",
                failure_modes_path=root / "missing_failure.json",
                lane_promotion_state_path=root / "missing_lane.json",
                open_risk_path=root / "missing_open.json",
                multilane_portfolio_path=root / "missing_multi.json",
                lane_quarantine_archive_path=root / "missing_archive.json",
            )

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("missed_picks_outcome", report["summary"]["missing_required_inputs"])
        self.assertIn("open_risk", report["summary"]["missing_required_inputs"])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            bad_open_risk = _open_risk(False)
            bad_open_risk["live_policy_change"] = True
            _write_json(paths["open_risk_path"], bad_open_risk)

            report = sizing.build_report(**paths)

        self.assertEqual(report["status"], "invalid_live_policy_change")
        self.assertTrue(report["summary"]["live_policy_change"])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            report = sizing.build_report(**paths)
            markdown = sizing.render_markdown(report)

            artifacts = sizing.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-risk-budget-sizing-replay.md",
            )

            self.assertIn("Scenario Replay", markdown)
            self.assertIn("does not change size tiers", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)


if __name__ == "__main__":
    unittest.main()
