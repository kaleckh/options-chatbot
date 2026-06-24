from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_multi_leg_side_aware_pricing_capability as capability
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _base_manifest() -> dict:
    statuses = {status: status for status in capability.DENOMINATOR_STATUSES}
    return {
        "manifest_id": "test_manifest",
        "proof_eligible": False,
        "fixtures": [
            {
                "fixture_id": "fixture_1",
                "structure": "ratio_backspread_bounded",
                "underlying": "QQQ",
                "entry_date": "2026-05-29",
                "entry_minute_et": 625,
                "exit_date": "2026-05-29",
                "exit_minute_et": 625,
                "entry_quote_basis": "bid_ask",
                "exit_quote_basis": "bid_ask",
                "bounded_risk": True,
                "undefined_risk_allowed": False,
                "max_loss_usd": 2000,
                "collateral_convention": "declared_fixture_cap",
                "fees_usd": 0,
                "slippage_usd": 0,
                "denominator_status_mapping": statuses,
                "legs": [
                    {
                        "leg_id": "short_lower",
                        "side": "short",
                        "quantity": 1,
                        "contract_symbol": "QQQ260603C00720000",
                        "expiry": "2026-06-03",
                        "option_type": "call",
                        "strike": 720,
                    },
                    {
                        "leg_id": "long_middle",
                        "side": "long",
                        "quantity": 2,
                        "contract_symbol": "QQQ260603C00725000",
                        "expiry": "2026-06-03",
                        "option_type": "call",
                        "strike": 725,
                    },
                    {
                        "leg_id": "short_cap",
                        "side": "short",
                        "quantity": 1,
                        "contract_symbol": "QQQ260603C00735000",
                        "expiry": "2026-06-03",
                        "option_type": "call",
                        "strike": 735,
                    },
                ],
            }
        ],
    }


def _write_db(path: Path, *, patch_rows: dict[str, dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            create table import_batches (
                id integer primary key,
                source_label text not null,
                dataset_kind text not null default 'intraday_csv',
                data_trust text not null default 'trusted',
                input_path text not null default 'fixture.csv',
                file_hash text not null default 'hash',
                imported_at_utc text not null default '2026-05-29T14:25:01Z',
                total_rows integer not null default 3,
                imported_rows integer not null default 3,
                duplicate_rows integer not null default 0,
                rejected_rows integer not null default 0,
                warnings_json text not null default '[]'
            )
            """
        )
        con.execute(
            """
            create table option_quote_snapshots (
                id integer primary key,
                as_of_utc text not null,
                quote_date_et text not null,
                quote_minute_et integer not null,
                snapshot_kind text not null default 'intraday',
                underlying text not null,
                contract_symbol text not null,
                expiry text not null,
                option_type text not null,
                strike real not null,
                bid real,
                ask real,
                last real,
                iv real,
                underlying_price real,
                volume integer,
                open_interest integer,
                source_batch_id integer not null
            )
            """
        )
        con.execute(
            "insert into import_batches (id, source_label, data_trust) values (1, 'thetadata_opra_nbbo_1m', 'trusted')"
        )
        rows = {
            "QQQ260603C00720000": {"strike": 720, "bid": 18.96, "ask": 21.8, "source_batch_id": 1},
            "QQQ260603C00725000": {"strike": 725, "bid": 15.24, "ask": 15.95, "source_batch_id": 1},
            "QQQ260603C00735000": {"strike": 735, "bid": 8.06, "ask": 8.12, "source_batch_id": 1},
        }
        for symbol, patch in (patch_rows or {}).items():
            if patch is None:
                rows.pop(symbol, None)
            else:
                rows.setdefault(symbol, {}).update(patch)
        for idx, (symbol, row) in enumerate(rows.items(), start=1):
            con.execute(
                """
                insert into option_quote_snapshots (
                    id, as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                    contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                    underlying_price, volume, open_interest, source_batch_id
                ) values (?, '2026-05-29T14:25:00Z', '2026-05-29', 625, ?, 'QQQ',
                    ?, '2026-06-03', 'call', ?, ?, ?, null, null, 720, 10, 100, ?)
                """,
                (
                    idx,
                    row.get("snapshot_kind", "intraday"),
                    symbol,
                    row["strike"],
                    row.get("bid"),
                    row.get("ask"),
                    row.get("source_batch_id", 1),
                ),
            )
        con.commit()
    finally:
        con.close()


class RegularOptionsMultiLegSideAwarePricingCapabilityTests(unittest.TestCase):
    def _build(self, tmp: Path, *, manifest_patch: dict | None = None, row_patch: dict[str, dict] | None = None) -> dict:
        manifest = _base_manifest()
        if manifest_patch:
            fixture = manifest["fixtures"][0]
            for key, value in manifest_patch.items():
                if key == "remove_denominator_status":
                    fixture["denominator_status_mapping"].pop(value, None)
                else:
                    fixture[key] = value
        db_path = tmp / "options_history.db"
        manifest_path = tmp / "manifest.json"
        _write_db(db_path, patch_rows=row_patch)
        _write_json(manifest_path, manifest)
        return capability.build_report(
            options_db_path=db_path,
            manifest_path=manifest_path,
            as_of_date="2026-06-04",
            no_write_requested=True,
            generated_at_utc="2026-06-23T00:00:00Z",
        )

    def test_available_fixture_prices_side_aware_and_remains_not_proof(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir))

        self.assertEqual(report["status"], "multi_leg_side_aware_pricing_capability_available")
        self.assertEqual(report["pricing_capability_blockers"], [])
        self.assertEqual(report["structure_support"]["ratio_backspread_bounded"]["status"], "available")
        self.assertEqual(report["quote_resolution_counts"]["resolved_fixture_count"], 1)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertTrue(report["fixture_source_not_proof_eligible"])
        row = report["fixture_results"][0]
        self.assertAlmostEqual(row["entry_net_cashflow_per_share"], -4.88)
        self.assertAlmostEqual(row["exit_net_cashflow_per_share"], 0.56)

    def test_missing_quote_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), row_patch={"QQQ260603C00725000": None})

        self.assertEqual(report["status"], "blocked_multi_leg_side_aware_pricing_capability")
        self.assertIn("missing_leg_quote", report["pricing_capability_blockers"])

    def test_zero_bid_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), row_patch={"QQQ260603C00735000": {"bid": 0.0}})

        self.assertIn("zero_bid_or_untradable", report["pricing_capability_blockers"])

    def test_crossed_quote_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), row_patch={"QQQ260603C00720000": {"bid": 22.0, "ask": 21.0}})

        self.assertIn("crossed_or_invalid_quote", report["pricing_capability_blockers"])

    def test_stale_or_untrusted_source_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), row_patch={"QQQ260603C00720000": {"snapshot_kind": "daily_eod"}})

        self.assertIn("stale_or_untrusted_quote", report["pricing_capability_blockers"])

    def test_midpoint_basis_is_rejected(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), manifest_patch={"entry_quote_basis": "midpoint"})

        self.assertIn("non_executable_pricing_basis_rejected", report["pricing_capability_blockers"])

    def test_naked_or_undefined_ratio_is_rejected(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), manifest_patch={"bounded_risk": False, "undefined_risk_allowed": True})

        self.assertIn("rejected_undefined_risk", report["pricing_capability_blockers"])

    def test_missing_denominator_mapping_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), manifest_patch={"remove_denominator_status": "missing_exit"})

        self.assertIn("missing_denominator_mapping", report["pricing_capability_blockers"])

    def test_wrong_underlying_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), manifest_patch={"underlying": "TSLA"})

        self.assertIn("wrong_underlying", report["pricing_capability_blockers"])

    def test_protected_holdout_overlap_blocks(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            report = self._build(Path(tmp_dir), manifest_patch={"entry_date": "2026-06-01"})

        self.assertIn("protected_holdout_blocked", report["pricing_capability_blockers"])

    def test_no_write_main_does_not_create_outputs(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            tmp = Path(tmp_dir)
            db_path = tmp / "options_history.db"
            manifest_path = tmp / "manifest.json"
            _write_db(db_path)
            _write_json(manifest_path, _base_manifest())
            code = capability.main(
                [
                    "--options-db",
                    str(db_path),
                    "--manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(tmp / "out"),
                    "--docs-report",
                    str(tmp / "docs.md"),
                    "--no-write",
                    "--json",
                ]
            )

            self.assertEqual(code, 0)
            self.assertFalse((tmp / "out").exists())
            self.assertFalse((tmp / "docs.md").exists())

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="multi-leg-capability") as tmp_dir:
            tmp = Path(tmp_dir)
            report = self._build(tmp)
            artifacts = capability.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "capability.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "capability.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
