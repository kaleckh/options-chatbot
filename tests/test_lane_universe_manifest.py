from __future__ import annotations

from pathlib import Path

import supervised_scan as ss
from ai_commodity_universe import ai_commodity_conditional_options_tickers, ai_commodity_core_options_tickers
from lane_universe_manifest import (
    LANE_UNIVERSE_DIR,
    lane_universe_summary,
    lane_universe_symbol_rows,
    lane_universe_symbols,
    load_lane_universe_manifest,
    validate_lane_universe_manifest,
)


def test_bullish_pullback_manifest_drives_scan_and_history_tiers():
    payload = load_lane_universe_manifest("bullish_pullback_observation")

    assert validate_lane_universe_manifest(payload) == []
    assert payload["universe_version"] == "2026-05-23.1"
    assert lane_universe_symbols("bullish_pullback_observation") == list(ss.BULLISH_PULLBACK_SCAN_TICKERS)
    assert lane_universe_symbols(
        "bullish_pullback_observation",
        tiers=["historical_ready"],
    ) == ["SPY", "QQQ"]
    assert lane_universe_symbols(
        "bullish_pullback_observation",
        tiers=["expansion_candidates"],
    ) == list(ss.BULLISH_PULLBACK_EXPANSION_TICKERS)

    rows = {row["symbol"]: row for row in lane_universe_symbol_rows("bullish_pullback_observation")}
    assert rows["SPY"]["admission_status"] == "exact_imported_daily_ready"
    assert rows["AAPL"]["admission_status"] == "scan_allowed_history_backfill_needed"

    summary = lane_universe_summary("bullish_pullback_observation")
    assert summary["symbol_count"] == len(ss.BULLISH_PULLBACK_SCAN_TICKERS)
    assert summary["scan_eligible_count"] == len(ss.BULLISH_PULLBACK_SCAN_TICKERS)
    assert summary["by_tier"] == {
        "historical_ready": len(ss.BULLISH_PULLBACK_HISTORICAL_READY_TICKERS),
        "expansion_candidates": len(ss.BULLISH_PULLBACK_EXPANSION_TICKERS),
    }


def test_ai_commodity_manifest_preserves_core_and_conditional_tiers():
    payload = load_lane_universe_manifest("ai_commodity_infra_observation")

    assert validate_lane_universe_manifest(payload) == []
    assert lane_universe_symbols("ai_commodity_infra_observation", tiers=["core_options"]) == ai_commodity_core_options_tickers()
    assert lane_universe_symbols(
        "ai_commodity_infra_observation",
        tiers=["conditional_options"],
    ) == ai_commodity_conditional_options_tickers()
    assert lane_universe_symbols("ai_commodity_infra_observation") == (
        ai_commodity_core_options_tickers() + ai_commodity_conditional_options_tickers()
    )

    summary = lane_universe_summary("ai_commodity_infra_observation")
    assert summary["by_tier"] == {"core_options": 9, "conditional_options": 15}
    assert summary["by_admission_status"]["conditional_contract_gated"] == 15
    assert summary["admission_policy"]["profitability_policy"].startswith("Lane B profitability")


def test_manifest_loader_uses_fallback_for_missing_manifest():
    missing_path = LANE_UNIVERSE_DIR / "does_not_exist.json"

    symbols = lane_universe_symbols(
        "missing_lane",
        path=missing_path,
        fallback=["spy", "qqq"],
    )

    assert symbols == ["SPY", "QQQ"]


def test_manifest_validation_rejects_duplicate_symbols():
    payload = {
        "schema_version": 1,
        "lane_id": "example",
        "universe_version": "test",
        "tiers": [
            {
                "tier_id": "tier_a",
                "scan_eligible": True,
                "admission_status": "ready",
                "symbols": ["SPY", "SPY"],
            }
        ],
    }

    assert "duplicate symbol SPY" in validate_lane_universe_manifest(payload)
