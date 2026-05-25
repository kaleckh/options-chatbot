import json
import os
import subprocess
import sys
import unittest
import csv
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from historical_options_fixtures import (  # noqa: E402
    make_validation_history,
    write_daily_options_parquet,
    write_historical_options_csv,
    write_underlying_daily_parquet,
)
from historical_options_store import (  # noqa: E402
    DAILY_SNAPSHOT_KIND,
    import_daily_option_parquet,
    import_historical_option_snapshots,
)
from scripts.audit_paid_data_readiness import (  # noqa: E402
    build_paid_data_readiness_audit,
    build_paid_data_readiness_fingerprint,
    find_duplicate_paid_data_readiness,
    write_paid_data_readiness_audit,
)
import wfo_optimizer as wfo  # noqa: E402
from workspace_tempdir import WorkspaceTempDir  # noqa: E402


class PaidDataReadinessAuditTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="paid-data-readiness")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "options_history.db"

    def _import_daily(
        self,
        symbol: str,
        *,
        length: int = 12,
        start: float = 500.0,
        source_label: str | None = None,
    ):
        histories = {symbol: make_validation_history(length=length, start=start, step=0.8)}
        options_path = self.tmp / f"{symbol.lower()}_options.parquet"
        underlying_path = self.tmp / f"{symbol.lower()}_underlying.parquet"
        write_daily_options_parquet(options_path, histories, symbol=symbol, strike_span=4)
        write_underlying_daily_parquet(underlying_path, histories, symbol=symbol)
        return import_daily_option_parquet(
            options_path,
            source_label or f"{symbol.lower()}_paid_data",
            underlying=symbol,
            underlying_input=underlying_path,
            db_path=self.db_path,
        )

    def test_audit_marks_fixture_ready_when_required_symbols_have_coverage(self):
        self._import_daily("SPY", length=14, start=500.0)
        self._import_daily("QQQ", length=14, start=420.0)

        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY", "QQQ"],
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            min_quote_dates=10,
            min_shared_quote_dates=10,
            min_executable_quote_pct=95.0,
        )

        self.assertEqual(audit["status"], "ready_for_exact_replay")
        self.assertIsNone(audit["blocker"])
        self.assertEqual(audit["missing_required_underlyings"], [])
        self.assertEqual(audit["thin_required_underlyings"], [])
        self.assertGreaterEqual(audit["shared_required_quote_dates"]["count"], 10)
        self.assertEqual(audit["source_labels_required"], [])
        self.assertGreater(audit["required_underlying_health"]["SPY"]["quote_rows"], 0)
        self.assertEqual(audit["required_underlying_health"]["SPY"]["executable_quote_pct"], 100.0)
        self.assertEqual(
            audit["next_actions"],
            ["Run exact-contract replay/backtest on the bullish-pullback main lane and canary proof/control yardstick."],
        )

    def test_audit_blocks_missing_required_symbols(self):
        self._import_daily("SPY", length=14, start=500.0)

        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY", "QQQ"],
            min_quote_dates=10,
            min_shared_quote_dates=10,
        )

        self.assertEqual(audit["status"], "not_ready")
        self.assertEqual(audit["blocker"], "missing_required_underlyings")
        self.assertEqual(audit["missing_required_underlyings"], ["QQQ"])
        self.assertTrue(audit["required_underlying_health"]["QQQ"]["missing"])
        self.assertIn("QQQ", audit["next_actions"][0])

    def test_audit_flags_low_executable_quote_coverage(self):
        csv_path = self.tmp / "snapshots.csv"
        histories = {"SPY": make_validation_history(length=12, start=500.0, step=0.8)}
        write_historical_options_csv(csv_path, histories, strike_span=2)
        with csv_path.open("r", encoding="utf8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
        for row in rows:
            row["ask"] = ""
        with csv_path.open("w", encoding="utf8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        import_historical_option_snapshots(csv_path, "spy_paid_intraday", db_path=self.db_path)

        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY"],
            snapshot_kind="intraday",
            min_quote_dates=10,
            min_shared_quote_dates=10,
            min_executable_quote_pct=99.9,
        )

        self.assertEqual(audit["status"], "not_ready")
        self.assertEqual(audit["blocker"], "low_executable_quote_coverage")
        self.assertEqual(audit["low_executable_required_underlyings"], ["SPY"])
        self.assertGreater(audit["required_underlying_health"]["SPY"]["missing_bid_ask_rows"], 0)

    def test_audit_does_not_count_zero_bid_quotes_as_executable(self):
        csv_path = self.tmp / "zero_bid_snapshots.csv"
        histories = {"SPY": make_validation_history(length=12, start=500.0, step=0.8)}
        write_historical_options_csv(csv_path, histories, strike_span=2)
        with csv_path.open("r", encoding="utf8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
        for row in rows:
            row["bid"] = "0"
        with csv_path.open("w", encoding="utf8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        import_historical_option_snapshots(csv_path, "spy_paid_intraday", db_path=self.db_path)

        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY"],
            snapshot_kind="intraday",
            min_quote_dates=10,
            min_shared_quote_dates=10,
            min_executable_quote_pct=99.9,
        )

        self.assertEqual(audit["status"], "not_ready")
        self.assertEqual(audit["blocker"], "low_executable_quote_coverage")
        self.assertEqual(audit["low_executable_required_underlyings"], ["SPY"])
        self.assertEqual(audit["required_underlying_health"]["SPY"]["executable_quote_pct"], 0.0)
        self.assertEqual(audit["required_underlying_health"]["SPY"]["missing_bid_ask_rows"], 0)

    def test_audit_can_require_specific_source_label(self):
        self._import_daily("SPY", length=14, start=500.0, source_label="alpaca_opra_daily_snapshot")
        self._import_daily("QQQ", length=14, start=420.0, source_label="thetadata_free_eod")

        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY", "QQQ"],
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            min_quote_dates=10,
            min_shared_quote_dates=10,
            source_labels=["alpaca_opra_daily_snapshot"],
        )

        self.assertEqual(audit["source_labels_required"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["status"], "not_ready")
        self.assertEqual(audit["blocker"], "missing_required_underlyings")
        self.assertEqual(audit["available_underlyings"], ["SPY"])
        self.assertEqual(audit["missing_required_underlyings"], ["QQQ"])
        self.assertEqual(audit["summary"]["source_labels"], ["alpaca_opra_daily_snapshot"])

    def test_audit_can_derive_scope_from_replay_playbook(self):
        self._import_daily("SPY", length=14, start=500.0, source_label="alpaca_opra_daily_snapshot")
        self._import_daily("QQQ", length=14, start=420.0, source_label="thetadata_free_eod")
        playbook = {
            "id": "test_paid_data_scope",
            "label": "Test Paid Data Scope",
            "historical_required_underlyings": ["SPY", "QQQ"],
            "historical_source_labels": ["alpaca_opra_daily_snapshot"],
        }

        with patch.dict(wfo.REPLAY_PLAYBOOKS, {"test_paid_data_scope": playbook}, clear=False):
            audit = build_paid_data_readiness_audit(
                db_path=self.db_path,
                playbook="test_paid_data_scope",
                snapshot_kind=DAILY_SNAPSHOT_KIND,
                min_quote_dates=10,
                min_shared_quote_dates=10,
            )

        self.assertEqual(audit["playbook"]["id"], "test_paid_data_scope")
        self.assertEqual(audit["source_labels_required"], ["alpaca_opra_daily_snapshot"])
        self.assertEqual(audit["required_underlyings"], ["QQQ", "SPY"])
        self.assertEqual(audit["available_underlyings"], ["SPY"])
        self.assertEqual(audit["missing_required_underlyings"], ["QQQ"])

    def test_write_audit_dedupes_by_fingerprint(self):
        self._import_daily("SPY", length=14, start=500.0)
        audit = build_paid_data_readiness_audit(
            db_path=self.db_path,
            required_underlyings=["SPY"],
            min_quote_dates=10,
            min_shared_quote_dates=10,
        )
        output_dir = self.tmp / "readiness"

        first = write_paid_data_readiness_audit(audit, output_dir=output_dir)
        second = write_paid_data_readiness_audit(audit, output_dir=output_dir)

        self.assertEqual(first["status"], "written")
        self.assertEqual(second["status"], "duplicate_skipped")
        self.assertEqual(
            find_duplicate_paid_data_readiness(output_dir, build_paid_data_readiness_fingerprint(audit)),
            Path(first["output"]),
        )

    def test_cli_emits_compact_readiness_json(self):
        self._import_daily("SPY", length=14, start=500.0)
        script_path = ROOT / "scripts" / "audit_paid_data_readiness.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--db-path",
                str(self.db_path),
                "--required-underlyings",
                "SPY",
                "--min-quote-dates",
                "10",
                "--min-shared-quote-dates",
                "10",
                "--output-dir",
                str(self.tmp / "readiness"),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
            cwd=ROOT,
            timeout=60,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(payload["status"], "ready_for_exact_replay")
        self.assertEqual(payload["blocker"], None)
        self.assertEqual(payload["required_underlyings"], ["SPY"])
        self.assertEqual(payload["missing_required_underlyings"], [])


if __name__ == "__main__":
    unittest.main()
