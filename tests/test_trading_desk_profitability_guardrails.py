from __future__ import annotations

import supervised_scan as ss
from scripts.analyze_trading_desk_profitability_guardrails import build_report


class _AvailablePositionsRepo:
    is_available = True

    def list_positions(self, status: str | None = "open"):
        return []


def _row(ticker: str, playbook_id: str, pnl_pct: float, **snapshot_overrides):
    snapshot = {
        "playbook_id": playbook_id,
        "spread_width": 10.0,
        "net_debit": 3.0,
        "ret5": 0.0,
        "quality_score": 50.0,
        "direction_score": 50.0,
    }
    snapshot.update(snapshot_overrides)
    return {
        "ticker": ticker,
        "net_pnl_pct": pnl_pct,
        "source_pick_snapshot": snapshot,
    }


def _pick(ticker: str, **overrides):
    pick = {
        "ticker": ticker,
        "asset_class": "equity",
        "sector": "Technology",
        "direction": "call",
        "type": "call",
        "strategy_type": "vertical_spread",
        "market_regime": "bullish",
        "expiry": "2026-06-19",
        "strike": 100.0,
        "short_strike": 110.0,
        "spread_width": 10.0,
        "net_debit": 3.0,
        "quality_score": 75.0,
        "direction_score": 75.0,
        "tech_score": 75.0,
        "spread_liquidity": {
            "spread_entry_debit": 3.0,
            "spread_mid_debit": 2.9,
            "long_bid": 3.9,
            "long_ask": 4.1,
            "short_bid": 0.9,
            "short_ask": 1.0,
        },
    }
    pick.update(overrides)
    return pick


def test_profitability_replay_promotes_quality_guards_but_rejects_momentum_chase():
    rows = [
        _row("XLK", "short_term", -50.0),
        _row("MSFT", "short_term", -40.0, net_debit=5.0, spread_width=10.0),
        _row(
            "AMD",
            "swing",
            -30.0,
            spread_liquidity={"spread_entry_debit": 1.25, "spread_mid_debit": 1.0},
        ),
        _row(
            "META",
            "bullish_momentum",
            -20.0,
            spread_liquidity={"long_bid": 0.9, "long_ask": 1.1, "short_bid": 0.9, "short_ask": 1.0},
        ),
        _row("SPY", "bullish_pullback_observation", -80.0),
        _row("IWM", "bullish_pullback_observation", -60.0, ret5=-3.0),
        _row("ORCL", "short_term", 20.0),
        _row("AAPL", "swing", 30.0),
        _row("GOOGL", "bullish_momentum", 25.0),
        _row("IWM", "bullish_pullback_observation", 40.0),
        _row("COST", "short_term", 100.0, ret5=7.0, quality_score=82.0, direction_score=90.0),
    ]

    report = build_report(rows, keep_tickers={"IWM", "AAPL", "GOOGL"})

    promoted = set(report["promoted_guardrails"])
    assert promoted == {
        "debit_gt_45_width",
        "fill_degradation_ge_20",
        "worst_leg_spread_ge_20",
        "lane_ticker_quarantine",
        "bullish_pullback_not_keep_bucket",
        "bullish_pullback_ret5_lt_minus_2",
    }
    probes = {probe["id"]: probe for probe in report["probes"]}
    assert probes["momentum_chase"]["promote_to_guardrail"] is False
    assert probes["momentum_chase"]["blocked"]["positive_or_flat"] == 1
    assert report["combined_promoted_guardrails"]["kept"]["avg_pnl_pct"] > report["baseline"]["avg_pnl_pct"]


def test_short_term_profitability_repair_blocks_promoted_entry_risks():
    result = ss.apply_playbook_guardrails(
        [
            _pick("ORCL"),
            _pick("XLK"),
            _pick("MSFT", net_debit=4.6, spread_liquidity={"spread_entry_debit": 4.6, "spread_mid_debit": 4.5}),
            _pick("AMD", spread_liquidity={"spread_entry_debit": 1.2, "spread_mid_debit": 1.0}),
            _pick(
                "META",
                spread_liquidity={"spread_entry_debit": 3.0, "spread_mid_debit": 2.9, "long_bid": 0.9, "long_ask": 1.1},
            ),
        ],
        playbook=ss.get_scan_playbook("short_term"),
        positions_repository=_AvailablePositionsRepo(),
        include_blocked=True,
    )

    by_ticker = {pick["ticker"]: pick for pick in result["ranked_picks"]}
    assert by_ticker["ORCL"]["guardrail_decision"] == "clear"
    assert by_ticker["XLK"]["guardrail_decision"] == "blocked"
    assert by_ticker["MSFT"]["guardrail_decision"] == "blocked"
    assert by_ticker["AMD"]["guardrail_decision"] == "blocked"
    assert by_ticker["META"]["guardrail_decision"] == "blocked"

    reasons = " ".join(reason for pick in result["ranked_picks"] for reason in pick["guardrail_reasons"])
    assert "quarantined" in reasons
    assert "Profitability repair blocks spread debit" in reasons
    assert "Fill degradation versus midpoint" in reasons
    assert "Worst leg bid/ask spread" in reasons


def test_bullish_pullback_profitability_repair_keeps_only_replay_backed_shapes():
    base = {
        "asset_class": "index",
        "sector": "Index ETF",
        "market_regime": "neutral",
        "candidate_execution_label": "executable_opra_paper_candidate",
        "expiry": "2026-06-26",
        "strike": 650.0,
        "short_strike": 680.0,
        "spread_width": 30.0,
        "spread_liquidity": {"spread_entry_debit": 12.0, "spread_mid_debit": 11.7, "long_bid": 15.0, "long_ask": 15.2},
    }
    result = ss.apply_playbook_guardrails(
        [
            _pick("IWM", **base, net_debit=12.0, ret5=0.0),
            _pick("SPY", **base, net_debit=12.0, ret5=0.0),
            _pick("AAPL", **{**base, "asset_class": "equity", "sector": "Technology"}, net_debit=12.0, ret5=-3.0),
            _pick(
                "GOOGL",
                **{
                    **base,
                    "asset_class": "equity",
                    "sector": "Technology",
                    "spread_liquidity": {"spread_entry_debit": 14.0, "spread_mid_debit": 13.7},
                },
                net_debit=14.0,
                ret5=0.0,
            ),
        ],
        playbook=ss.get_scan_playbook("bullish_pullback_observation"),
        positions_repository=_AvailablePositionsRepo(),
        include_blocked=True,
    )

    by_ticker = {pick["ticker"]: pick for pick in result["ranked_picks"]}
    assert by_ticker["IWM"]["guardrail_decision"] != "blocked"
    assert by_ticker["SPY"]["guardrail_decision"] == "blocked"
    assert by_ticker["AAPL"]["guardrail_decision"] == "blocked"
    assert by_ticker["GOOGL"]["guardrail_decision"] == "blocked"

    reasons = " ".join(reason for pick in result["ranked_picks"] for reason in pick["guardrail_reasons"])
    assert "profitability repair currently allows only" in reasons
    assert "Entry ret5 -3.0%" in reasons
    assert "Profitability repair blocks spread debit 46.7% of width" in reasons
