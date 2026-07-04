from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_regular_options_filtered_policy as freeze


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _filtered_audit() -> dict:
    return {
        "report_id": "regular_options_historical_filtered_simulated_forward_audit",
        "status": "historical_filtered_simulated_forward_audit_passed",
        "generated_at_utc": "2026-06-30T14:00:00Z",
        "filter_source": {
            "filter_id": "fixture_filter",
            "description": "Fixture filter.",
            "conditions": [
                {"field": "ticker", "op": "in", "value": ["AAPL"]},
                {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
            ],
        },
        "split": {
            "train_months": ["2024-06"],
            "audit_months": ["2026-02", "2026-03", "2026-04", "2026-05"],
            "window_months": ["2024-06", "2026-02"],
        },
    }


def _iteration() -> dict:
    return {
        "report_id": "regular_options_historical_profitability_filter_iteration",
        "status": "historical_profitability_filter_iteration_candidate_found",
        "generated_at_utc": "2026-06-30T13:59:00Z",
        "split": {"train_months": ["2024-06"], "audit_months": ["2026-02"]},
    }


class FreezeRegularOptionsFilteredPolicyTests(unittest.TestCase):
    def test_main_refuses_without_freeze_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            iteration_path = root / "iteration.json"
            output_path = root / "contract.json"
            _write_json(audit_path, _filtered_audit())
            _write_json(iteration_path, _iteration())

            with self.assertRaises(SystemExit):
                freeze.main(
                    [
                        "--filtered-audit",
                        str(audit_path),
                        "--filter-iteration",
                        str(iteration_path),
                        "--output",
                        str(output_path),
                    ]
                )

        self.assertFalse(output_path.exists())

    def test_build_contract_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            iteration_path = root / "iteration.json"
            output_path = root / "regular-options-frozen-filtered-policy-v1.json"
            _write_json(audit_path, _filtered_audit())
            _write_json(iteration_path, _iteration())

            code = freeze.main(
                [
                    "--filtered-audit",
                    str(audit_path),
                    "--filter-iteration",
                    str(iteration_path),
                    "--output",
                    str(output_path),
                    "--freeze-token",
                    freeze.FREEZE_TOKEN,
                    "--json",
                ]
            )

            payload = json.loads(output_path.read_text(encoding="utf8"))

        self.assertEqual(code, 0)
        self.assertEqual(payload["policy_id"], freeze.POLICY_ID)
        self.assertEqual(payload["filter_id"], "fixture_filter")
        self.assertEqual(payload["conditions_sha256"], freeze._conditions_sha256(payload["conditions"]))
        self.assertEqual(payload["tracking_start_at_utc"], "2026-06-30T05:03:45Z")
        self.assertFalse(payload["accepted_profitability"])
        self.assertFalse(payload["historical_rows_are_forward_proof"])
        self.assertIn("filtered_audit_artifact", payload["provenance"])
        self.assertEqual(payload["provenance"]["audit_months_at_freeze"], ["2026-02", "2026-03", "2026-04", "2026-05"])

    def test_refuses_to_overwrite_existing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_path = root / "audit.json"
            iteration_path = root / "iteration.json"
            output_path = root / "regular-options-frozen-filtered-policy-v1.json"
            _write_json(audit_path, _filtered_audit())
            _write_json(iteration_path, _iteration())
            output_path.write_text("{}", encoding="utf8")

            with self.assertRaises(SystemExit):
                freeze.main(
                    [
                        "--filtered-audit",
                        str(audit_path),
                        "--filter-iteration",
                        str(iteration_path),
                        "--output",
                        str(output_path),
                        "--freeze-token",
                        freeze.FREEZE_TOKEN,
                    ]
                )


if __name__ == "__main__":
    unittest.main()
