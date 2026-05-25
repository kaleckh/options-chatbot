from __future__ import annotations

from lane_research_controls import build_event_macro_concentration_controls


def test_event_macro_concentration_controls_block_promotion_on_metadata_and_concentration():
    controls = build_event_macro_concentration_controls(
        [
            {
                "ticker": "FCX",
                "entry_date": "2026-05-20",
                "next_earnings_date": "2026-05-21",
                "market_regime": "bullish",
                "sector": "Basic Materials",
                "primary_theme": "copper",
                "pnl_dollars": 100.0,
            },
            {
                "ticker": "FCX",
                "entry_date": "2026-05-22",
                "market_regime": "bullish",
                "sector": "Basic Materials",
                "primary_theme": "copper",
                "pnl_dollars": 50.0,
            },
            {
                "ticker": "VRT",
                "entry_date": "2026-05-23",
                "sector": "Industrials",
                "primary_theme": "cooling",
                "pnl_dollars": -25.0,
            },
        ],
        lane_id="ai_commodity_infra_observation",
        max_symbol_profit_share=0.50,
        max_theme_profit_share=0.50,
    )

    assert controls["policy"] == "research_only_no_production_gate_changes"
    assert controls["event_controls"]["event_risk_count"] == 1
    assert controls["event_controls"]["missing_event_metadata_count"] == 2
    assert controls["macro_controls"]["missing_macro_regime_count"] == 1
    assert controls["concentration_controls"]["by_symbol"][0]["symbol"] == "FCX"
    assert controls["concentration_controls"]["by_symbol"][0]["positive_pnl_share"] == 1.0
    assert "missing_event_metadata" in controls["promotion_blockers"]
    assert "missing_macro_regime_metadata" in controls["promotion_blockers"]
    assert "symbol_profit_concentration" in controls["promotion_blockers"]
    assert "theme_profit_concentration" in controls["promotion_blockers"]
    assert controls["promotion_allowed"] is False


def test_event_macro_concentration_controls_require_records_before_promotion():
    controls = build_event_macro_concentration_controls(
        [],
        lane_id="bullish_pullback_observation",
    )

    assert controls["record_count"] == 0
    assert controls["promotion_allowed"] is False
    assert controls["promotion_blockers"] == ["insufficient_records_for_research_controls"]


def test_event_macro_concentration_controls_do_not_mix_usd_and_pct_pnl():
    controls = build_event_macro_concentration_controls(
        [
            {"ticker": "A", "entry_date": "2026-05-20", "sector": "Tech", "primary_theme": "ai", "pnl_usd": 100.0},
            {"ticker": "B", "entry_date": "2026-05-20", "sector": "Tech", "primary_theme": "ai", "pnl_pct": 300.0},
        ],
        lane_id="ai_commodity_infra_observation",
    )

    by_symbol = {row["symbol"]: row for row in controls["concentration_controls"]["by_symbol"]}
    assert by_symbol["A"]["pnl_basis"] == "usd"
    assert by_symbol["A"]["net_pnl"] == 100.0
    assert by_symbol["B"]["net_pnl"] == 0.0
