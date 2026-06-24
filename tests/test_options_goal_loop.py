from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_options_goal_loop as loop


NOW = "2026-06-19T12:00:00Z"
POLICY_HASH = "55e102c420e81c81baf8fd374b0c9c6c78c9acca349495f077b2877616b8657a"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _policy() -> dict:
    return {
        "allowed_modes": ["audit", "verify", "prepare-protocol", "report"],
        "allowed_lanes": ["volatility_expansion_observation", "bullish_pullback_observation"],
        "allowed_read_only_commands": [
            "npm run options:report:volatility-forward-paper-shadow",
            "npm run options:report:phase2-forward-paper-shadow",
            "uv run --locked python -m unittest tests.test_options_goal_loop tests.test_volatility_expansion_forward_paper_shadow_report tests.test_append_volatility_expansion_forward_paper_shadow_rows -v",
            "npm run options:research:hypothesis-tournament -- --no-write --json",
        ],
        "denied_command_substrings": ["import", "broker", "order", "run_regular_options_goal_experiment"],
        "iteration_limits": {"default_max_iterations": 1, "hard_cap_max_iterations": 5},
        "proof_gates": {
            "minimum_exact_completed_forward_rows": 30,
            "preferred_exact_completed_forward_rows": 50,
            "minimum_pf_lower_bound_after_stress_gt": 1.0,
            "healthier_pf_lower_bound_after_stress_gte": 1.2,
        },
        "stopped_branches": [
            "combined_portfolio as promotion path",
            "broad hypothesis-tournament expansion",
            "tracked_winner_cheap_debit_continuity_v1 current shape",
        ],
    }


def _trade(**overrides) -> dict:
    payload = {
        "generated_at_utc": NOW,
        "overall_status": "blocked_no_live_release",
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready_count": 0,
        "exact_realized_pnl_count": 0,
        "best_current_lane_if_any": {
            "lane_id": "volatility_expansion_observation",
            "decision": "paper_shadow_collect",
            "profit_factor": 1.83,
            "avg_net_pnl_pct": 6.74,
            "fresh_exact_entry_count": 3,
            "exact_realized_pnl_count": 0,
        },
        "lane_decisions": [
            {
                "lane_id": "volatility_expansion_observation",
                "decision": "paper_shadow_collect",
                "promotion_state": "paper_probation",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _robust(**overrides) -> dict:
    payload = {
        "generated_at_utc": NOW,
        "overall_status": "paper_shadow_only",
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "existing_promotion_ready": False,
        "best_candidate_if_any": {
            "candidate_id": "lane:volatility_expansion_observation",
            "lane_id": "volatility_expansion_observation",
            "decision": "paper_shadow_candidate",
            "profit_factor": 1.83,
            "profit_factor_lower_bound": None,
        },
    }
    payload.update(overrides)
    return payload


def _schema() -> dict:
    return {
        "contract_id": "volatility-expansion-forward-paper-shadow-cohort-schema",
        "schema_version": 1,
        "record_required_fields": [
            "schema_version",
            "row_id",
            "lane_id",
            "selection_timestamp_utc",
            "selection_date",
            "scanner_run_id",
            "scanner_policy_hash",
            "denominator_status",
            "ticker",
            "contract_or_spread_key",
        ],
    }


def _preregistration() -> dict:
    return {
        "contract_id": "forward-cohort-preregistration",
        "last_updated": "2026-06-14",
        "status": "active",
        "cohort": {"frozen": True, "freeze_date": "2026-06-14", "eval_date": "2026-07-28"},
        "lanes": [
            {
                "lane_id": "volatility_expansion_observation",
                "policy_snapshot_sha256": POLICY_HASH,
                "symbols": ["SPY", "QQQ", "IWM", "DIA"],
            },
            {
                "lane_id": "bullish_pullback_observation",
                "policy_snapshot_sha256": "e8af3d61712bd2fcecfed64c83b4a6a6e0cdc3a8a40ecfd71ea11031da1eecd7",
                "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
            }
        ],
        "byte_frozen_policy_snapshot": {"source_file_sha256": "sourcehash"},
    }


def _row(index: int, pnl: float | None = None, **overrides) -> dict:
    month = 7 + index // 8
    date = f"2026-{month:02d}-{1 + index % 8:02d}"
    payload = {
        "schema_version": 1,
        "row_id": f"row-{index}",
        "lane_id": "volatility_expansion_observation",
        "selection_timestamp_utc": f"{date}T15:00:00Z",
        "selection_date": date,
        "scanner_run_id": f"scan-{index}",
        "scanner_policy_hash": POLICY_HASH,
        "denominator_status": "exact_exit_captured" if pnl is not None else "open_waiting_policy_exit",
        "ticker": ["SPY", "QQQ", "IWM", "DIA"][index % 4],
        "contract_or_spread_key": f"spread-{index}",
        "entry_evidence_status": "exact_entry_captured",
        "exit_evidence_status": "exact_exit_captured" if pnl is not None else "open_waiting_policy_exit",
        "candidate_source_mode": "real_market_window_scan_picks",
        "fixture_mode": False,
        "source_artifact_path": "data/forward-tracking/scan_picks.jsonl",
        "source_artifact_sha256": "abc123",
        "market_window_status": "open",
        "captured_at_utc": NOW,
    }
    if pnl is not None:
        payload["net_pnl_pct"] = pnl
        payload["net_pnl_usd"] = pnl
        payload["entry_quote_source"] = "opra_nbbo"
        payload["entry_quote_timestamp_utc"] = payload["selection_timestamp_utc"]
        payload["entry_bid"] = 1.0
        payload["entry_ask"] = 1.1
        payload["exit_quote_source"] = "opra_nbbo"
        payload["exit_quote_timestamp_utc"] = f"{date}T19:55:00Z"
        payload["exit_bid"] = 1.2
        payload["exit_ask"] = 1.3
        payload["policy_exit_condition"] = "policy_exit_at_close"
    payload.update(overrides)
    return payload


class OptionsGoalLoopTests(unittest.TestCase):
    def _paths(self, root: Path, *, rows: list[dict] | None = None, trade: dict | None = None, robust: dict | None = None) -> dict:
        paths = {
            "policy_path": root / "policy.json",
            "trade_qualification_path": root / "trade.json",
            "robust_edge_path": root / "robust.json",
            "forward_protocol_schema_path": root / "schema.json",
            "forward_cohort_preregistration_path": root / "prereg.json",
            "forward_cohort_log_path": root / "cohort.jsonl",
        }
        _write_json(paths["policy_path"], _policy())
        _write_json(paths["trade_qualification_path"], trade or _trade())
        _write_json(paths["robust_edge_path"], robust or _robust())
        _write_json(paths["forward_protocol_schema_path"], _schema())
        _write_json(paths["forward_cohort_preregistration_path"], _preregistration())
        if rows is not None:
            _write_jsonl(paths["forward_cohort_log_path"], rows)
        return paths

    def _build(self, *, rows: list[dict] | None = None, trade: dict | None = None, robust: dict | None = None, **overrides):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root, rows=rows, trade=trade, robust=robust)
            paths.update(overrides)
            return loop.build_report(generated_at_utc=NOW, execute_commands=False, **paths)

    def test_live_flag_true_causes_immediate_stop(self) -> None:
        report = self._build(trade=_trade(live_entry_allowed=True))
        self.assertEqual(report["current_decision_state"], "safety_violation")
        self.assertEqual(report["next_safe_action"], "stop_immediately")

    def test_promotion_ready_true_without_gates_causes_immediate_stop(self) -> None:
        report = self._build(trade=_trade(promotion_ready_count=1))
        self.assertEqual(report["current_decision_state"], "promotion_policy_violation")
        self.assertEqual(report["next_safe_action"], "stop_immediately")

    def test_under_thirty_exact_forward_rows_is_underpowered(self) -> None:
        report = self._build(rows=[_row(index, 2.0) for index in range(12)])
        self.assertEqual(report["current_decision_state"], "underpowered_forward_evidence")
        self.assertEqual(report["next_safe_action"], "continue_paper_shadow_only")
        self.assertEqual(report["forward_evidence_accounting"]["state"], "strict_rows_under_minimum")
        self.assertEqual(report["forward_evidence_accounting"]["post_freeze_strict_exact_completed_rows"], 12)

    def test_forward_evidence_accounting_missing_log_is_named_blocker(self) -> None:
        report = self._build(rows=None)

        accounting = report["forward_evidence_accounting"]
        self.assertEqual(accounting["state"], "log_missing_blocker")
        self.assertFalse(accounting["cohort_log_exists"])
        self.assertEqual(accounting["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(accounting["strict_rows_remaining_to_minimum"], 30)
        self.assertFalse(accounting["promotion_ready"])
        self.assertFalse(accounting["live_entry_allowed"])
        self.assertFalse(accounting["auto_track_allowed"])
        self.assertFalse(accounting["broker_order_allowed"])

    def test_forward_evidence_accounting_initialized_empty_is_zero_of_gate(self) -> None:
        report = self._build(rows=[])

        accounting = report["forward_evidence_accounting"]
        self.assertEqual(accounting["state"], "initialized_empty_zero_of_gate")
        self.assertTrue(accounting["cohort_log_exists"])
        self.assertEqual(accounting["cohort_log_row_count"], 0)
        self.assertEqual(accounting["post_freeze_strict_exact_completed_rows"], 0)
        self.assertEqual(accounting["strict_rows_remaining_to_minimum"], 30)

    def test_forward_evidence_accounting_excluded_rows_are_explicit(self) -> None:
        rows = [
            _row(1, 2.0, selection_date="2026-06-14", selection_timestamp_utc="2026-06-14T15:00:00Z"),
            _row(2, 2.0, quote_evidence_class="midpoint"),
            _row(3, 2.0, lane_id="swing"),
        ]
        report = self._build(rows=rows)

        accounting = report["forward_evidence_accounting"]
        self.assertEqual(accounting["state"], "rows_present_none_strict_excluded")
        self.assertEqual(accounting["total_natural_selections"], 3)
        self.assertEqual(accounting["post_freeze_strict_exact_completed_rows"], 0)
        self.assertGreater(accounting["excluded_or_rejected_row_flags"], 0)

    def test_thirty_rows_with_pf_lb_not_above_one_rejects(self) -> None:
        rows = [_row(index, 1.0 if index % 2 == 0 else -1.0) for index in range(32)]
        report = self._build(rows=rows)
        self.assertEqual(report["current_decision_state"], "blocked_forward_gate")
        self.assertEqual(report["next_safe_action"], "continue_or_reject_based_on_blocker")

    def test_thirty_rows_with_concentration_failure_blocks(self) -> None:
        rows = [_row(index, 2.0 if index < 24 else -1.0, ticker="SPY") for index in range(32)]
        report = self._build(rows=rows)
        self.assertEqual(report["current_decision_state"], "blocked_forward_gate")

    def test_clean_minimum_packet_creates_review_state_only(self) -> None:
        rows = [_row(index, 2.0 if index < 24 else -1.0) for index in range(32)]
        report = self._build(rows=rows)
        self.assertEqual(report["current_decision_state"], "eligible_for_frozen_paper_validation_review")
        self.assertEqual(report["next_safe_action"], "produce_review_packet")
        self.assertFalse(report["live_entry_allowed"])

    def test_zero_bid_rows_are_execution_failures(self) -> None:
        report = self._build(rows=[_row(1, None, denominator_status="zero_bid_untradable")])
        self.assertTrue(report["cohort_audit"]["zero_bid_is_execution_failure"])
        self.assertTrue(report["quote_tradability_blockers_detected"])

    def test_lookahead_only_rows_are_diagnostic_only(self) -> None:
        report = self._build(rows=[_row(1, 10.0, denominator_status="lookahead_only_diagnostic")])
        self.assertTrue(report["cohort_audit"]["lookahead_only_is_diagnostic"])
        self.assertEqual(report["cohort_audit"]["strict_exact_completed_forward_rows"], 0)

    def test_non_executable_marks_are_not_proof(self) -> None:
        rows = [_row(1, 10.0, quote_evidence_class="midpoint"), _row(2, 10.0, entry_quote_source="display_only")]
        report = self._build(rows=rows)
        self.assertTrue(report["cohort_audit"]["non_executable_marks_not_counted_as_proof"])
        self.assertEqual(report["cohort_audit"]["strict_exact_completed_forward_rows"], 0)
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)

    def test_great_pf_with_non_executable_marks_stays_underpowered(self) -> None:
        rows = [_row(index, 10.0, quote_evidence_class="midpoint") for index in range(32)]
        report = self._build(rows=rows)

        self.assertEqual(report["current_decision_state"], "underpowered_forward_evidence")
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(report["acceptance_readiness"]["post_freeze_strict_exact_completed_rows"], 0)

    def test_percent_only_rows_do_not_satisfy_usd_acceptance_snapshot(self) -> None:
        rows = []
        for index in range(32):
            row = _row(index, 2.0 if index < 24 else -1.0)
            row.pop("net_pnl_usd")
            rows.append(row)
        report = self._build(rows=rows)

        self.assertEqual(report["current_decision_state"], "underpowered_forward_evidence")
        self.assertFalse(report["acceptance_readiness"]["positive_net_usd_pnl"])
        self.assertEqual(report["exact_realized_forward_pnl_count"], 0)
        self.assertNotIn("forward_report_goal_loop_strict_count_mismatch", report["reason_codes"])

    def test_promotion_ready_requires_strict_usd_acceptance_snapshot(self) -> None:
        rows = []
        for index in range(32):
            row = _row(index, 2.0 if index < 24 else -1.0)
            row.pop("net_pnl_usd")
            rows.append(row)
        trade = _trade(promotion_ready_count=1)
        report = self._build(rows=rows, trade=trade)

        self.assertEqual(report["current_decision_state"], "promotion_policy_violation")
        self.assertFalse(report["live_entry_allowed"])

    def test_denied_commands_are_not_run(self) -> None:
        allowed, reasons = loop.command_allowed("npm run options:record", _policy())
        self.assertFalse(allowed)
        self.assertIn("command_not_exactly_allowlisted", reasons)

    def test_execute_resolves_windows_command_shim(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with (
            patch.object(loop.shutil, "which", return_value=r"C:\Program Files\nodejs\npm.CMD"),
            patch.object(loop.subprocess, "run", return_value=completed) as run_mock,
        ):
            result = loop.run_commands(
                ["npm run options:report:volatility-forward-paper-shadow"],
                _policy(),
                execute=True,
            )

        self.assertEqual(run_mock.call_args.args[0][0], r"C:\Program Files\nodejs\npm.CMD")
        self.assertEqual(result["commands"][0]["returncode"], 0)

    def test_existing_evidence_databases_are_not_modified(self) -> None:
        report = self._build()
        self.assertFalse(report["mutated_evidence_databases"])
        self.assertFalse(report["imported_quotes"])
        self.assertFalse(report["repaired_historical_rows"])

    def test_stopped_branches_remain_stopped(self) -> None:
        report = self._build()
        self.assertIn("combined_portfolio as promotion path", report["stopped_branches"])
        self.assertIn("tracked_winner_cheap_debit_continuity_v1 current shape", report["stopped_branches"])

    def test_broad_tournament_expansion_remains_denied(self) -> None:
        allowed, reasons = loop.command_allowed("npm run options:research:hypothesis-tournament -- --max-variants 200", _policy())
        self.assertFalse(allowed)
        self.assertIn("variant_budget_expansion_denied", reasons)


if __name__ == "__main__":
    unittest.main()
