from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from scripts import audit_zero_pick_days_all_lanes as all_lanes
from scripts import audit_zero_pick_days_current_main_lane as single_lane


class _MonkeyPatch:
    def __init__(self, test_case: unittest.TestCase) -> None:
        self._test_case = test_case

    def setattr(self, target: object, name: str, value: object) -> None:
        patcher = patch.object(target, name, value)
        patcher.start()
        self._test_case.addCleanup(patcher.stop)


def test_replay_adapter_does_not_force_pullback_defaults_for_momentum_lane() -> None:
    _, replay_playbook, adapter = single_lane._build_replay_playbook_for_audit("volatility_expansion_observation")

    assert replay_playbook.get("entry_signal_id") is None
    assert replay_playbook.get("allowed_signal_families") in (None, [])
    assert adapter["entry_signal_id"] == "momentum_default"
    assert adapter["uses_default_momentum_entry"] is True


def test_replay_adapter_uses_calibration_playbook_when_lane_lacks_direct_replay() -> None:
    _, replay_playbook, adapter = single_lane._build_replay_playbook_for_audit("quality90_debit55_canary")

    assert replay_playbook["id"] == "quality90_debit55_canary"
    assert adapter["source"] == "calibration_playbook"
    assert adapter["base_playbook_id"] == "bullish_index_calls_quality90_debit55"
    assert replay_playbook["min_quality_score"] == 90.0


def test_all_lanes_audit_invokes_requested_lanes(monkeypatch: object) -> None:
    calls: list[tuple[str, str]] = []

    def fake_build_audit(args: argparse.Namespace) -> dict:
        calls.append((args.playbook, args.audit_id))
        return {
            "summary": {
                "date_count": 1,
                "signal_candidate_count": 2,
                "exact_candidate_count": 1,
                "would_track_pick_count": 1,
                "duplicate_pick_count": 0,
            },
            "parameters": {"playbook": args.playbook},
            "discovery": {},
            "ledger_results": [],
            "dates": [],
        }

    monkeypatch.setattr(all_lanes.single_lane_audit, "build_audit", fake_build_audit)
    args = argparse.Namespace(
        playbooks="bullish_pullback_observation,volatility_expansion_observation",
        exclude_playbooks=None,
        scope="zero_any_or_main_zero",
        date_from=None,
        date_to=None,
        truth_lane=single_lane.wfo.IMPORTED_TRUTH_SOURCE,
        pricing_lane="pessimistic",
        source_labels="thetadata_opra_nbbo_1m",
        historical_options_db=str(single_lane.HISTORICAL_OPTIONS_DB),
        allow_research_data=False,
        lookback_years=2,
        n_picks=10,
        apply=False,
        audit_id="test_all_lanes",
        fail_fast=False,
    )

    audit = all_lanes.build_all_lanes_audit(args)

    assert calls == [
        ("bullish_pullback_observation", "test_all_lanes"),
        ("volatility_expansion_observation", "test_all_lanes"),
    ]
    assert audit["summary"]["completed_lane_count"] == 2
    assert audit["summary"]["signal_candidate_count"] == 4
    assert [lane["status"] for lane in audit["lanes"]] == ["completed", "completed"]


class ZeroPickAllLanesAuditTests(unittest.TestCase):
    def test_replay_adapter_does_not_force_pullback_defaults_for_momentum_lane(self) -> None:
        test_replay_adapter_does_not_force_pullback_defaults_for_momentum_lane()

    def test_replay_adapter_uses_calibration_playbook_when_lane_lacks_direct_replay(self) -> None:
        test_replay_adapter_uses_calibration_playbook_when_lane_lacks_direct_replay()

    def test_all_lanes_audit_invokes_requested_lanes(self) -> None:
        test_all_lanes_audit_invokes_requested_lanes(_MonkeyPatch(self))
