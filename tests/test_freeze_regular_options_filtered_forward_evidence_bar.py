from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_regular_options_filtered_forward_evidence_bar as freeze


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _policy_contract() -> dict:
    return {
        "report_id": "regular_options_frozen_filtered_policy",
        "policy_id": "historical_filtered_candidate_policy_v1",
        "filter_id": "fixture_filter",
        "conditions_sha256": "abc123",
    }


class FreezeRegularOptionsFilteredForwardEvidenceBarTests(unittest.TestCase):
    def test_main_refuses_without_freeze_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            output_path = root / "bar.json"
            _write_json(policy_path, _policy_contract())

            with self.assertRaises(SystemExit):
                freeze.main(["--policy-contract", str(policy_path), "--output", str(output_path)])

        self.assertFalse(output_path.exists())

    def test_build_contract_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            output_path = root / "regular-options-filtered-forward-evidence-bar-v1.json"
            _write_json(policy_path, _policy_contract())

            code = freeze.main(
                [
                    "--policy-contract",
                    str(policy_path),
                    "--output",
                    str(output_path),
                    "--freeze-token",
                    freeze.FREEZE_TOKEN,
                    "--json",
                ]
            )
            payload = json.loads(output_path.read_text(encoding="utf8"))

        self.assertEqual(code, 0)
        self.assertEqual(payload["bar_id"], freeze.BAR_ID)
        self.assertEqual(payload["source_policy_contract"]["filter_id"], "fixture_filter")
        requirements = payload["requirements"]
        self.assertEqual(requirements["min_completed_forward_paper_shadow_rows"], 30)
        self.assertEqual(requirements["min_ticker_week_clusters"], 8)
        self.assertEqual(requirements["min_calendar_months_with_rows"], 3)
        self.assertEqual(requirements["min_percent_cluster_pf_lb_5pct"], 1.0)
        self.assertEqual(requirements["min_usd_cluster_pf_lb_5pct"], 1.0)
        self.assertEqual(requirements["max_fixture_rows"], 0)
        self.assertTrue(requirements["evaluation_may_not_occur_before_min_completed_rows"])
        self.assertFalse(payload["approval_authority"])
        self.assertFalse(payload["accepted_profitability"])
        self.assertFalse(payload["scanner_policy_changed"])

    def test_refuses_to_overwrite_existing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            output_path = root / "regular-options-filtered-forward-evidence-bar-v1.json"
            _write_json(policy_path, _policy_contract())
            output_path.write_text("{}", encoding="utf8")

            with self.assertRaises(SystemExit):
                freeze.main(
                    [
                        "--policy-contract",
                        str(policy_path),
                        "--output",
                        str(output_path),
                        "--freeze-token",
                        freeze.FREEZE_TOKEN,
                    ]
                )


if __name__ == "__main__":
    unittest.main()
