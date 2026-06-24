from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer4_forward_capture_protocol as protocol


NOW = "2026-06-21T20:30:00Z"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _source_payloads() -> dict[str, dict]:
    selected = {
        "layer_id": protocol.SELECTED_LAYER_ID,
        "variant_id": protocol.SELECTED_VARIANT_ID,
        "source_result_path": protocol.SELECTED_SOURCE_RUN,
    }
    return {
        "selection": {
            "generated_at_utc": NOW,
            "overall_status": "layer_shadow_selection_ready",
            "primary_harness_layer": selected,
            "harness_requirements": {
                "selected_layer_id": protocol.SELECTED_LAYER_ID,
                "selected_variant_id": protocol.SELECTED_VARIANT_ID,
                "source_result_path": protocol.SELECTED_SOURCE_RUN,
            },
        },
        "execution_safety": {
            "generated_at_utc": NOW,
            "report_id": "bullish_pullback_layer_execution_safety_audit",
            "overall_status": "blocked_execution_safety_preflight",
            "selected_layer": selected,
            "row_counts": {
                "total_selected_rows": 129,
                "rows_with_existing_trusted_entry_leg_bid_ask": 129,
                "rows_with_existing_trusted_exit_leg_bid_ask": 126,
                "zero_bid_or_untradable_rows": 6,
                "fatal_blocker_count": 129,
            },
            "blockers": ["existing_trusted_leg_exit_quotes_missing"],
        },
        "economics": {
            "generated_at_utc": NOW,
            "report_id": "bullish_pullback_layer_executable_economics",
            "overall_status": "executable_economics_recomputed_profitable_but_preflight_blocked",
            "harness_decision": "profitable_but_preflight_blocked",
            "selected_layer": selected,
            "row_counts": {
                "selected_rows": 129,
                "tradable_executable_rows": 120,
                "missing_required_quote_rows": 3,
                "zero_or_untradable_rows": 6,
                "source_mark_mismatch_rows": 129,
            },
            "denominator_views": {
                "tradable_executable_only": {
                    "net_usd_total": 45610.0,
                    "profit_factor": 3.7414,
                    "bootstrap": {"pf_lb_5pct": 2.27, "avg_net_lb_5pct": 235.07},
                }
            },
        },
    }


def _write_sources(root: Path, payloads: dict[str, dict]) -> dict[str, Path]:
    paths = {
        "selection_path": root / "selection.json",
        "execution_safety_path": root / "execution-safety.json",
        "executable_economics_path": root / "economics.json",
        "approval_packet_path": root / "approval.md",
    }
    _write(paths["selection_path"], payloads["selection"])
    _write(paths["execution_safety_path"], payloads["execution_safety"])
    _write(paths["executable_economics_path"], payloads["economics"])
    return paths


class BullishPullbackLayer4ForwardCaptureProtocolTests(unittest.TestCase):
    def test_protocol_ready_when_sources_match_positive_blocked_economics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root, _source_payloads())
            report = protocol.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["capture_protocol_status"], "protocol_ready_waiting_for_market_window_and_operator_approval")
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertTrue(report["candidate_validator_read_only"])
        self.assertEqual(report["historical_executable_economics"]["historical_side_aware_pf"], 3.7414)
        self.assertEqual(report["selected_harness"]["allowed_symbols"], list(protocol.ALLOWED_SYMBOLS))

    def test_selected_layer_drift_blocks_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payloads = _source_payloads()
            payloads["economics"]["selected_layer"]["layer_id"] = "layer_5_count_expanded"
            paths = _write_sources(root, payloads)
            report = protocol.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["capture_protocol_status"], "blocked_capture_protocol")
        self.assertIn("selected_executable_economics_layer_drift", report["blockers"])

    def test_write_outputs_creates_approval_packet_without_authorizing_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = _write_sources(root, _source_payloads())
            report = protocol.build_report(generated_at_utc=NOW, **paths)
            artifacts = protocol.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "doc.md",
                approval_packet=root / "approval.md",
            )

            packet = (root / "approval.md").read_text(encoding="utf8")

        self.assertIn("approval_packet", artifacts)
        self.assertIn("does not approve appending rows", packet)
        self.assertIn("broker orders", packet)


if __name__ == "__main__":
    unittest.main()
