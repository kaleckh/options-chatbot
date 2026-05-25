from __future__ import annotations

from datetime import datetime, timedelta, timezone

import options_chatbot as oc


def test_quote_timestamp_context_prefers_latest_quote_time_over_trade_time():
    now = datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc)
    row = {
        "latestQuoteTime": (now - timedelta(hours=1)).isoformat(),
        "lastTradeDate": (now - timedelta(hours=30)).isoformat(),
    }

    context = oc._quote_timestamp_context_from_row(row, now_utc=now)

    assert context["quote_timestamp_source"] == "latest_quote"
    assert context["quote_age_hours"] == 1.0
    assert context["quote_timestamp_utc"].endswith("Z")
    assert oc._quote_freshness_from_age(context["quote_age_hours"]) == "fresh"


def test_point_in_time_rank_context_labels_true_iv_vs_hv_proxy():
    true_iv = oc._point_in_time_rank_context(
        0.30,
        [0.10, 0.20, 0.40],
        source_label="vendor_option_iv_history",
        value_label="option_iv",
        as_of_index=12,
    )
    proxy = oc._point_in_time_rank_context(
        0.30,
        [0.10, 0.20, 0.40],
        source_label="underlying_hv30_point_in_time_proxy",
        value_label="realized_vol_proxy",
        as_of_index=12,
    )

    assert true_iv["rank"] == 66.6667
    assert true_iv["point_in_time"] is True
    assert true_iv["proof_grade"] is True
    assert true_iv["quality_flag"] == "proof_point_in_time_option_iv"
    assert proxy["rank"] == 66.6667
    assert proxy["proof_grade"] is False
    assert proxy["quality_flag"] == "research_realized_vol_proxy"


def test_candidate_data_quality_separates_pricing_proof_from_profitability_research():
    candidate = {
        "strategy_type": "vertical_spread",
        "quote_time_utc": "2026-05-23T18:00:00Z",
        "quote_freshness_status": "fresh",
        "options_data_source": "alpaca_opra",
        "entry_execution_price": 2.5,
        "entry_execution_basis": "spread_ask_bid",
        "candidate_execution_label": "executable_opra_paper_candidate",
        "selection_source": "live_chain_exact_contract",
        "promotion_class": "research_bootstrap",
        "legs": [
            {
                "role": "long",
                "contract_symbol": "SPY260619C00600000",
                "bid": 4.9,
                "ask": 5.1,
            },
            {
                "role": "short",
                "contract_symbol": "SPY260619C00620000",
                "bid": 2.4,
                "ask": 2.6,
            },
        ],
    }

    quality = oc._candidate_data_quality(candidate)

    assert quality["status"] == "complete"
    assert quality["flags"] == []
    assert quality["pricing_evidence_class"] == "proof_live_opra_exact_contract"
    assert quality["profitability_evidence_class"] == "research_profitability_calibration"
    assert quality["source_separation"] == "pricing_proof_profitability_research"


def test_candidate_data_quality_flags_missing_required_quote_fields():
    quality = oc._candidate_data_quality(
        {
            "strategy_type": "single_leg",
            "quote_freshness_status": "unknown",
            "selection_source": "model_contract_fallback",
            "promotion_class": "research_bootstrap",
            "entry_execution_price": None,
        }
    )

    assert quality["status"] == "missing_or_research_limited"
    assert "missing_quote_timestamp" in quality["flags"]
    assert "missing_options_source" in quality["flags"]
    assert "missing_entry_execution_price" in quality["flags"]
    assert "missing_contract_symbol" in quality["flags"]
    assert "missing_bid_ask" in quality["flags"]
    assert quality["pricing_evidence_class"] == "research_model_fallback"
