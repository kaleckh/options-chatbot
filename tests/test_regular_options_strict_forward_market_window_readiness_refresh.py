from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_strict_forward_market_window_readiness_refresh as refresh


NOW = "2026-06-26T15:00:00Z"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _base_payload(report_id: str, status: str = "ready", generated_at: str = NOW) -> dict:
    return {
        "generated_at_utc": generated_at,
        "report_id": report_id,
        "overall_status": status,
        "read_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "promotion_ready": False,
        "quotes_imported": False,
        "mutated_evidence_databases": False,
        "cohort_append_performed": False,
        "consumed_protected_holdout": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
    }


def _payloads(generated_at: str = NOW) -> dict[str, dict]:
    payloads = {
        name: _base_payload(name, generated_at=generated_at)
        for name in refresh.DEFAULT_SOURCES
    }
    payloads["strict_forward_operator_queue"].update(
        {
            "overall_status": "strict_forward_queue_ready_approval_and_market_window_blocked",
            "strict_forward_rows": 0,
            "required_rows": 30,
            "profitability_readiness": False,
            "historical_rows_are_forward_proof": False,
            "selected_path": {
                "lane_id": "bullish_pullback_observation",
                "layer_id": "layer_4_clean_exact",
                "freeze_date": "2026-06-14",
                "allowed_symbols": ["IWM", "AAPL"],
            },
            "historical_executable_economics": {
                "status": "executable_economics_recomputed_profitable_but_preflight_blocked",
                "harness_decision": "profitable_but_preflight_blocked",
                "tradable_executable_rows": 120,
                "historical_side_aware_pf": 3.7414,
                "historical_side_aware_pf_lb_5pct": 2.27,
            },
        }
    )
    payloads["market_window_approval_preflight"].update(
        {
            "overall_status": "blocked_market_closed",
            "market_window_status": "market_closed",
            "market_window_valid": False,
            "operator_approval_required": True,
            "operator_approval_granted": False,
            "append_allowed": False,
            "candidate_validation": {
                "candidate_jsonl_supplied": False,
                "candidate_validator_read_only": True,
                "cohort_append_performed": False,
                "total_candidate_rows": 0,
                "valid_candidate_rows": 0,
                "rejected_candidate_rows": 0,
            },
        }
    )
    payloads["forward_candidate_throughput_audit"].update(
        {
            "status": "blocked_no_same_day_phase2_natural_selections",
            "scan_picks_row_count": 550,
            "post_freeze_phase2_scan_pick_count": 1,
            "target_selection_date": "2026-06-26",
            "target_date_phase2_scan_pick_count": 0,
            "scheduled_scan_session_count": 2,
            "scheduled_phase2_scan_picks_count": 0,
            "scheduled_phase2_drop_count_total": 63,
            "scheduled_phase2_scan_drop_reason_count_total": 0,
            "candidate_starvation_evidence_status": "stage_counts_only_waiting_for_symbol_drop_reasons",
            "scheduled_phase2_all_lanes_scanned": True,
            "scheduled_phase2_playbooks_with_session": [
                "bullish_pullback_observation",
                "volatility_expansion_observation",
            ],
            "scheduled_phase2_playbooks_missing_session": [],
            "candidate_rows_staged": 0,
            "candidate_jsonl_written": False,
            "next_action": "wait_for_valid_market_window_and_real_phase2_scan_picks",
            "stager_rejected_counts": {"non_phase2_lane": 468},
        }
    )
    return payloads


def _write_sources(root: Path, payloads: dict[str, dict] | None = None) -> dict[str, Path]:
    payloads = payloads or _payloads()
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = root / f"{name}.json"
        _write(path, payload)
        paths[name] = path
    return paths


class RegularOptionsStrictForwardMarketWindowReadinessRefreshTests(unittest.TestCase):
    def test_current_state_is_market_window_blocked_no_candidate_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "market_window_blocked_no_candidate_jsonl")
        self.assertEqual(report["strict_forward_rows"], 0)
        self.assertEqual(report["required_rows"], 30)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["profitability_readiness"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["preflight"]["candidate_jsonl_exists"])
        self.assertFalse(report["preflight"]["append_allowed"])
        self.assertEqual(
            report["candidate_throughput"]["candidate_starvation_evidence_status"],
            "stage_counts_only_waiting_for_symbol_drop_reasons",
        )
        self.assertEqual(report["candidate_throughput"]["scheduled_phase2_drop_count_total"], 63)
        self.assertEqual(report["candidate_throughput"]["scheduled_phase2_scan_drop_reason_count_total"], 0)
        self.assertIn("valid_market_window_required", report["blockers"])
        self.assertIn("natural_candidate_jsonl_missing", report["blockers"])

    def test_missing_readback_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            paths["trade_qualification"].unlink()
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")

    def test_selected_path_drift_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _payloads()
            payloads["strict_forward_operator_queue"]["selected_path"]["layer_id"] = "layer_5_count_expanded"
            paths = _write_sources(Path(temp_dir), payloads)
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "selected_path_identity_drift")
        self.assertIn("layer_id_drift", report["blockers"])

    def test_safety_leakage_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _payloads()
            payloads["trade_qualification"]["live_entry_allowed"] = True
            paths = _write_sources(Path(temp_dir), payloads)
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "safety_blocked")
        self.assertEqual(report["safety_violations"][0]["source"], "trade_qualification")
        self.assertTrue(report["safety"]["live_entry_allowed"])

    def test_future_valid_candidate_still_does_not_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payloads = _payloads()
            payloads["market_window_approval_preflight"].update(
                {
                    "overall_status": "preflight_ready_for_operator_approval_discussion",
                    "market_window_status": "market_open",
                    "market_window_valid": True,
                    "operator_approval_required": True,
                    "operator_approval_granted": False,
                    "append_allowed": True,
                    "candidate_validation": {
                        "candidate_jsonl_supplied": True,
                        "candidate_validator_read_only": True,
                        "cohort_append_performed": False,
                        "total_candidate_rows": 3,
                        "valid_candidate_rows": 3,
                        "rejected_candidate_rows": 0,
                    },
                }
            )
            paths = _write_sources(Path(temp_dir), payloads)
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)

        self.assertEqual(report["overall_status"], "ready_for_later_operator_approval_discussion_no_append_performed")
        self.assertEqual(report["preflight"]["candidate_rows"], 3)
        self.assertFalse(report["cohort_append_performed"])

    def test_write_outputs_creates_doc_with_no_write_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root)
            report = refresh.build_report(source_paths=paths, generated_at_utc=NOW)
            artifacts = refresh.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            doc = (root / "doc.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Strict forward proof: `0/30`", doc)
        self.assertIn("Candidate-starvation evidence status", doc)
        self.assertIn("This is a no-write readiness refresh", doc)


if __name__ == "__main__":
    unittest.main()
