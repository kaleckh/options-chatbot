from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_macro_event_long_strangle_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsMacroEventLongStrangleReplayReadinessTests(unittest.TestCase):
    def _valid_playbook(self, tmp: Path) -> Path:
        path = tmp / "playbook.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_macro_event_long_strangle_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "concept": {
                    "initial_research_universe": ["SPY", "QQQ"],
                    "future_extension_universe": ["IWM", "DIA"],
                    "event_categories": list(readiness.REQUIRED_EVENT_CATEGORIES),
                },
            },
        )
        return path

    def _valid_calendar(self, tmp: Path) -> Path:
        path = tmp / "calendar.json"
        events = []
        for index, category in enumerate(readiness.REQUIRED_EVENT_CATEGORIES, start=1):
            events.append(
                {
                    "event_id": f"event-{index}",
                    "event_category": category,
                    "event_timestamp_utc": f"2026-0{index}-15T14:00:00Z",
                    "known_at_utc": f"2025-12-{index:02d}T00:00:00Z",
                }
            )
        _write_json(path, {"events": events})
        return path

    def _valid_feature_store(self, tmp: Path) -> Path:
        path = tmp / "feature-store.json"
        _write_json(path, {"status": "feature_store_built", "vix_bucket_point_in_time_available": True})
        return path

    def _valid_vix_bucket(self, tmp: Path) -> Path:
        path = tmp / "vix-bucket.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_vix_bucket",
                "status": "point_in_time_vix_bucket_ready",
                "point_in_time_vix_low_mid_bucket_available": True,
                "coverage_pct": 100.0,
                "source_rows_count": 3,
                "blockers": [],
            },
        )
        return path

    def _holdout_contract(self, tmp: Path) -> Path:
        path = tmp / "holdout.json"
        _write_json(path, {"report_id": "forward_holdout_contract", "protected_holdout_start_date": "2026-06-05"})
        return path

    def test_requires_macro_event_long_strangle_preregistered_design_only(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=tmp / "missing-calendar.json",
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["concept_id"], readiness.CONCEPT_ID)
        self.assertTrue(report["preregistration_validation"]["valid"])
        self.assertFalse(report["accepted_profitability"])

    def test_fails_closed_on_wrong_concept_id(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            playbook = self._valid_playbook(tmp)
            payload = json.loads(playbook.read_text(encoding="utf8"))
            payload["concept_id"] = "wrong"
            _write_json(playbook, payload)
            report = readiness.build_report(
                preregistered_playbook_path=playbook,
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["status"], "invalid_preregistered_playbook_state")
        self.assertIn("unexpected_concept_id", report["preregistration_validation"]["reasons"])

    def test_fails_closed_on_wrong_structure(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            playbook = self._valid_playbook(tmp)
            payload = json.loads(playbook.read_text(encoding="utf8"))
            payload["structure"] = "undefined_risk_short_strangles"
            _write_json(playbook, payload)
            report = readiness.build_report(
                preregistered_playbook_path=playbook,
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["status"], "invalid_preregistered_playbook_state")
        self.assertIn("unexpected_structure", report["preregistration_validation"]["reasons"])

    def test_detects_missing_point_in_time_event_calendar_as_named_blocker(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=tmp / "missing-calendar.json",
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["status"], "blocked_macro_event_long_strangle_replay_readiness")
        self.assertIn("missing_point_in_time_macro_event_calendar", report["blockers"])

    def test_consumes_calendar_source_missing_status_as_named_blocker(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            calendar = tmp / "calendar.json"
            _write_json(
                calendar,
                {
                    "report_id": "regular_options_macro_event_calendar",
                    "status": "blocked_macro_event_calendar_source_missing",
                    "event_count": 0,
                    "covered_categories": [],
                    "missing_categories": list(readiness.REQUIRED_EVENT_CATEGORIES),
                    "events": [],
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=calendar,
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertIn("macro_event_calendar_source_missing", report["blockers"])
        self.assertNotIn("missing_point_in_time_macro_event_calendar", report["blockers"])

    def test_valid_calendar_artifact_clears_calendar_blocker_but_not_vix(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            feature_store = tmp / "feature-store.json"
            _write_json(feature_store, {"status": "feature_store_built", "features": ["underlying_trend"]})
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=feature_store,
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertNotIn("missing_point_in_time_macro_event_calendar", report["blockers"])
        self.assertIn("missing_point_in_time_vix_bucket", report["blockers"])

    def test_consumes_vix_source_missing_status_as_named_blocker(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            vix_bucket = tmp / "vix-bucket.json"
            _write_json(
                vix_bucket,
                {
                    "report_id": "regular_options_point_in_time_vix_bucket",
                    "status": "blocked_point_in_time_vix_source_missing",
                    "point_in_time_vix_low_mid_bucket_available": False,
                    "source_rows_count": 0,
                    "coverage_pct": 0,
                    "blockers": ["point_in_time_vix_source_missing", "missing_vix_bucket_threshold_policy"],
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=vix_bucket,
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertIn("point_in_time_vix_source_missing", report["blockers"])
        self.assertIn("missing_vix_bucket_threshold_policy", report["blockers"])
        self.assertNotIn("missing_point_in_time_vix_bucket", report["blockers"])

    def test_valid_vix_bucket_artifact_clears_vix_blocker(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=self._valid_vix_bucket(tmp),
                feature_store_path=tmp / "missing-feature-store.json",
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["vix_bucket_readiness"]["status"], "ready")
        self.assertNotIn("missing_point_in_time_vix_bucket", report["blockers"])
        self.assertEqual(report["status"], "ready_for_bounded_read_only_replay_nomination")

    def test_requires_event_timestamp_before_candidate_entry(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            calendar = tmp / "calendar.json"
            _write_json(
                calendar,
                {
                    "events": [
                        {
                            "event_id": "bad-known-at",
                            "event_category": "cpi",
                            "event_timestamp_utc": "2026-02-15T14:00:00Z",
                            "known_at_utc": "2026-02-16T14:00:00Z",
                        }
                    ]
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=calendar,
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertIn("event_timestamp_not_point_in_time_before_candidate_entry", report["blockers"])

    def test_rejects_event_outcome_realized_move_future_iv_option_return_or_pnl_leakage(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            calendar = tmp / "calendar.json"
            events = json.loads(self._valid_calendar(tmp).read_text(encoding="utf8"))["events"]
            events[0]["realized_move"] = 0.018
            events[1]["future_iv"] = 0.21
            events[2]["option_return"] = 0.42
            events[3]["pnl"] = 100
            _write_json(calendar, {"events": events})
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=calendar,
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertIn("event_calendar_leakage_fields_present", report["blockers"])
        self.assertGreaterEqual(len(report["event_calendar_readiness"]["leakage_keys"]), 4)

    def test_requires_point_in_time_vix_low_mid_bucket(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            feature_store = tmp / "feature-store.json"
            _write_json(feature_store, {"status": "feature_store_built", "features": ["underlying_trend"]})
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=feature_store,
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertIn("missing_point_in_time_vix_bucket", report["blockers"])

    def test_requires_spy_qqq_initial_universe_only(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            playbook = self._valid_playbook(tmp)
            payload = json.loads(playbook.read_text(encoding="utf8"))
            payload["concept"]["initial_research_universe"] = ["SPY", "QQQ", "IWM"]
            _write_json(playbook, payload)
            report = readiness.build_report(
                preregistered_playbook_path=playbook,
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )

        self.assertEqual(report["status"], "invalid_preregistered_playbook_state")
        self.assertIn("unexpected_initial_research_universe", report["preregistration_validation"]["reasons"])

    def test_requires_side_aware_long_premium_entry_formula(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertIn("call_ask + put_ask", report["proof_formulas"]["entry_debit"])

    def test_requires_side_aware_exit_or_expiry_settlement_formula(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertIn("call_bid + put_bid", report["proof_formulas"]["exit_value"])
        self.assertIn("underlying_settlement", report["proof_formulas"]["expiry_settlement_value"])

    def test_requires_full_denominator_status_mapping(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertEqual(set(readiness.REQUIRED_DENOMINATOR_STATUSES), set(report["required_denominator_statuses"]))

    def test_requires_strict_new_identity_schema(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertEqual(set(readiness.STRICT_NEW_IDENTITY_FIELDS), set(report["strict_new_identity_schema"]))

    def test_requires_protected_holdout_guard_before_aggregation(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=self._valid_calendar(tmp),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=tmp / "missing-holdout.json",
            )

        self.assertIn("missing_protected_holdout_guard", report["blockers"])

    def test_requires_net_usd_pnl_after_multiplier_fees_slippage_for_future_replay(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertIn("* 100 - fees_and_slippage", report["proof_formulas"]["net_pnl_usd"])
        self.assertIn("net USD P&L", report["future_replay_pnl_convention"])

    def test_preserves_no_live_no_broker_no_auto_track_no_quote_import_no_evidence_mutation_no_promotion_flags(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["promotion_ready"])

    def test_does_not_run_replay_or_write_evidence_store(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(Path(tmp_dir)),
                event_calendar_path=self._valid_calendar(Path(tmp_dir)),
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(Path(tmp_dir)),
                holdout_contract_path=self._holdout_contract(Path(tmp_dir)),
            )

        self.assertFalse(report["historical_replay_performed"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertEqual(report["status"], "ready_for_bounded_read_only_replay_nomination")

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="macro-event-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_playbook(tmp),
                event_calendar_path=tmp / "missing-calendar.json",
                vix_bucket_path=Path(tmp_dir) / "missing-vix.json",
                feature_store_path=self._valid_feature_store(tmp),
                holdout_contract_path=self._holdout_contract(tmp),
            )
            artifacts = readiness.write_outputs(
                report,
                output_dir=tmp / "out",
                docs_report=tmp / "docs" / "macro-event-readiness.md",
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "macro-event-readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "macro-event-readiness.md").read_text(encoding="utf8")
            self.assertIn("Macro-Event Long Strangle Replay Readiness", markdown)


if __name__ == "__main__":
    unittest.main()


