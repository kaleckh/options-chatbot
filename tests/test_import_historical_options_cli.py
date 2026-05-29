import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (ROOT, TESTS_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from historical_options_fixtures import (
    make_validation_history,
    write_daily_options_parquet,
    write_underlying_daily_parquet,
)
import scripts.import_historical_options_snapshots as import_cli


class _FakeResponse:
    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"contract_symbol\n"


class HistoricalOptionsImportCliTests(unittest.TestCase):
    def test_url_download_temp_filename_ignores_query_string(self):
        with patch.object(import_cli.requests, "get", return_value=_FakeResponse()):
            path, tmpdir = import_cli._resolve_input_path("https://example.test/data.csv?sig=abc")
            try:
                self.assertEqual(Path(path).name, "data.csv")
                self.assertTrue(Path(path).exists())
            finally:
                assert tmpdir is not None
                tmpdir.cleanup()

    def test_url_download_temp_filename_sanitizes_encoded_slashes(self):
        with patch.object(import_cli.requests, "get", return_value=_FakeResponse()):
            path, tmpdir = import_cli._resolve_input_path("https://example.test/signed%2Fspy.parquet?sig=abc")
            try:
                self.assertEqual(Path(path).name, "spy.parquet")
                self.assertEqual(Path(path).parent, Path(tmpdir.name))
                self.assertTrue(Path(path).exists())
            finally:
                assert tmpdir is not None
                tmpdir.cleanup()

    def test_url_download_temp_filename_sanitizes_windows_invalid_characters(self):
        with patch.object(import_cli.requests, "get", return_value=_FakeResponse()):
            path, tmpdir = import_cli._resolve_input_path("https://example.test/bad%3Cname.parquet?sig=abc")
            try:
                self.assertEqual(Path(path).name, "bad_name.parquet")
                self.assertEqual(Path(path).parent, Path(tmpdir.name))
                self.assertTrue(Path(path).exists())
            finally:
                assert tmpdir is not None
                tmpdir.cleanup()

    def test_manifest_import_loads_multiple_daily_parquets_and_emits_store_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "options_history.db"
            manifest_path = tmp / "manifest.json"
            histories = {
                "SPY": make_validation_history(length=12, start=500.0, step=0.8),
                "QQQ": make_validation_history(length=12, start=420.0, step=0.9),
            }

            spy_options = tmp / "spy_options.parquet"
            spy_underlying = tmp / "spy_underlying.parquet"
            qqq_options = tmp / "qqq_options.parquet"
            qqq_underlying = tmp / "qqq_underlying.parquet"

            write_daily_options_parquet(spy_options, histories, symbol="SPY", strike_span=4)
            write_underlying_daily_parquet(spy_underlying, histories, symbol="SPY")
            write_daily_options_parquet(qqq_options, histories, symbol="QQQ", strike_span=4)
            write_underlying_daily_parquet(qqq_underlying, histories, symbol="QQQ")

            manifest_path.write_text(
                json.dumps(
                    {
                        "imports": [
                            {
                                "input": str(spy_options),
                                "source": "spy_daily_manifest",
                                "format": "philippdubach_daily",
                                "underlying": "SPY",
                                "underlying_input": str(spy_underlying),
                            },
                            {
                                "input": str(qqq_options),
                                "source": "qqq_daily_manifest",
                                "format": "philippdubach_daily",
                                "underlying": "QQQ",
                                "underlying_input": str(qqq_underlying),
                            },
                        ]
                    }
                ),
                encoding="utf8",
            )

            script_path = ROOT / "scripts" / "import_historical_options_snapshots.py"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                    "--db-path",
                    str(db_path),
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONUTF8": "1"},
                cwd=ROOT,
                timeout=60,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["mode"], "manifest")
            self.assertEqual(len(payload["entries"]), 2)
            self.assertGreater(payload["total_imported_rows"], 0)
            self.assertEqual(payload["total_rejected_rows"], 0)

            daily_summary = payload["trusted_snapshot_summaries"]["daily_eod"]
            self.assertGreater(daily_summary["quote_count"], 0)
            self.assertEqual(daily_summary["available_underlyings"], ["QQQ", "SPY"])


if __name__ == "__main__":
    unittest.main()
