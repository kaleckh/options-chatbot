from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_post_event_iv_crush_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsPostEventIvCrushReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "playbook.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_post_event_iv_crush_iron_condor_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "lane_implementation_performed": False,
                "historical_replay_performed": False,
                "scanner_policy_changed": False,
                "strategy_logic_changed": False,
                "formula_contract": {
                    "entry": "net_credit = short_call_bid + short_put_bid - long_call_ask - long_put_ask",
                    "exit": "exit_debit = short_call_ask + short_put_ask - long_call_bid - long_put_bid",
                    "risk": "max_loss_usd = width - net_credit; margin uses max_loss",
                    "assignment": "assignment and expiration are denominator states",
                },
                "denominator_contract": {"statuses": sorted(readiness.REQUIRED_DENOMINATOR_STATUSES)},
            },
        )
        return path

    def _ready_calendar(self, tmp: Path) -> Path:
        path = tmp / "calendar.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_macro_event_calendar",
                "status": "macro_event_calendar_ready",
                "event_count": 3,
                "blockers": [],
                "events": [
                    {"event_type": "cpi", "known_at_utc": "2026-01-01T00:00:00Z"},
                    {"event_type": "fomc_minutes", "known_at_utc": "2026-01-01T00:00:00Z"},
                    {"event_type": "fomc_rate_decision", "known_at_utc": "2026-01-01T00:00:00Z"},
                    {"event_type": "nonfarm_payrolls", "known_at_utc": "2026-01-01T00:00:00Z"},
                    {"event_type": "pce", "known_at_utc": "2026-01-01T00:00:00Z"},
                    {"event_type": "scheduled_fed_chair_testimony", "known_at_utc": "2026-01-01T00:00:00Z"},
                ],
            },
        )
        return path

    def _ready_features(self, tmp: Path) -> Path:
        path = tmp / "features.json"
        _write_json(path, {"features": ["iv_event_premium_proxy", "pre_event_iv", "post_event_iv"]})
        return path

    def _ready_vix(self, tmp: Path) -> Path:
        path = tmp / "vix.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_vix_bucket",
                "status": "point_in_time_vix_bucket_ready",
                "point_in_time_vix_low_mid_bucket_available": True,
                "coverage_pct": 100.0,
                "source_rows_count": 10,
                "blockers": [],
            },
        )
        return path

    def _ready_quote_surface(self, tmp: Path) -> Path:
        path = tmp / "quotes.json"
        _write_json(path, {"status": "post_event_iv_crush_iron_condor_quote_surface_ready"})
        return path

    def _ready_ledger(self, tmp: Path) -> Path:
        path = tmp / "ledger.json"
        _write_json(path, {"status": "base_clean_stack_identity_ledger_ready", "blockers": [], "ledger_row_count": 12})
        return path

    def _holdout(self, tmp: Path) -> Path:
        path = tmp / "holdout.json"
        _write_json(path, {"contract_id": "forward-holdout-contract", "protected_holdout_consumed": False})
        return path

    def test_report_is_read_only_and_names_concrete_current_blockers(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            missing_features = tmp / "missing-features.json"
            blocked_calendar = tmp / "calendar.json"
            _write_json(
                blocked_calendar,
                {"status": "blocked_macro_event_calendar_source_missing", "blockers": ["macro_event_calendar_source_missing"]},
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                macro_event_calendar_path=blocked_calendar,
                feature_store_path=missing_features,
                vix_bucket_path=self._ready_vix(tmp),
                quote_capability_path=tmp / "missing-quotes.json",
                base_ledger_path=self._ready_ledger(tmp),
                holdout_contract_path=self._holdout(tmp),
                generated_at_utc="2026-06-26T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_post_event_iv_crush_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertIn("macro_event_calendar_source_missing", report["blockers"])
        self.assertIn("iv_event_premium_proxy_missing", report["blockers"])
        self.assertIn("missing_index_iron_condor_quote_surface", report["blockers"])
        self.assertNotIn("point_in_time_vix_source_missing", report["blockers"])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(invalid, {"status": "implemented", "concept_id": "wrong", "accepted_profitability": True})
            report = readiness.build_report(preregistered_playbook_path=invalid)

        self.assertEqual(report["status"], "blocked_invalid_post_event_iv_crush_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_complete_fixture_reaches_research_only_approval_question(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                macro_event_calendar_path=self._ready_calendar(tmp),
                feature_store_path=self._ready_features(tmp),
                vix_bucket_path=self._ready_vix(tmp),
                quote_capability_path=self._ready_quote_surface(tmp),
                base_ledger_path=self._ready_ledger(tmp),
                holdout_contract_path=self._holdout(tmp),
            )

        self.assertEqual(report["status"], "ready_for_research_only_implementation_approval_question")
        self.assertEqual(report["blockers"], [])
        self.assertTrue(all(row["status"] == "ready" for row in report["critical_prerequisites"]))

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="post-event-iv-crush-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            report = readiness.build_report(preregistered_playbook_path=self._valid_preregistration(tmp))
            artifacts = readiness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "readiness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "readiness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Post-Event IV-Crush Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
