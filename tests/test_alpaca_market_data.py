import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import alpaca_market_data as amd
import forward_options_ledger as fol
import options_chatbot as oc
import supervised_scan as ss


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if url.endswith("/stocks/bars"):
            return _Response(
                {
                    "bars": {
                        "SPY": [
                            {"t": "2026-05-18T14:30:00Z", "o": 600, "h": 602, "l": 599, "c": 601, "v": 1000},
                            {"t": "2026-05-19T14:30:00Z", "o": 601, "h": 604, "l": 600, "c": 603, "v": 1200},
                        ]
                    }
                }
            )
        if url.endswith("/options/contracts"):
            expiry = params.get("expiration_date") or "2026-06-19"
            return _Response(
                {
                    "option_contracts": [
                        {
                            "symbol": "SPY260619C00600000",
                            "expiration_date": expiry,
                            "strike_price": "600",
                            "type": "call",
                            "open_interest": "1234",
                            "tradable": True,
                            "underlying_symbol": "SPY",
                        },
                        {
                            "symbol": "SPY260619P00590000",
                            "expiration_date": expiry,
                            "strike_price": "590",
                            "type": "put",
                            "open_interest": "4321",
                            "tradable": True,
                            "underlying_symbol": "SPY",
                        },
                    ],
                    "next_page_token": None,
                }
            )
        if url.endswith("/v1beta1/options/bars"):
            symbols = [item.strip().upper() for item in str(params.get("symbols") or "").split(",") if item.strip()]
            return _Response(
                {
                    "bars": {
                        symbol: [
                            {"t": "2026-05-18T04:00:00Z", "o": 1.0, "h": 1.4, "l": 0.9, "c": 1.2, "v": 200}
                        ]
                        for symbol in symbols
                    },
                    "next_page_token": None,
                }
            )
        if url.endswith("/v1beta1/options/trades"):
            symbols = [item.strip().upper() for item in str(params.get("symbols") or "").split(",") if item.strip()]
            return _Response(
                {
                    "trades": {
                        symbol: [
                            {"t": "2026-05-18T14:31:00Z", "p": 1.22, "s": 3, "x": "C", "c": ["I"]}
                        ]
                        for symbol in symbols
                    },
                    "next_page_token": None,
                }
            )
        if "/v1beta1/options/snapshots/SPY" in url:
            symbol = "SPY260619C00600000" if params.get("type") == "call" else "SPY260619P00590000"
            delta = 0.52 if params.get("type") == "call" else -0.48
            return _Response(
                {
                    "snapshots": {
                        symbol: {
                            "latestQuote": {"bp": 10.0, "ap": 10.2, "t": "2026-05-19T19:59:30Z"},
                            "latestTrade": {"p": 10.1, "t": "2026-05-19T19:58:00Z"},
                            "dailyBar": {"v": 321},
                            "greeks": {"delta": delta, "iv": 0.21},
                        }
                    }
                }
            )
        return _Response({"message": "unexpected"}, status_code=404)


class _FallbackTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self._history = pd.DataFrame(
            {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [100]},
            index=pd.DatetimeIndex(["2026-05-19"]),
        )

    def history(self, *args, **kwargs):
        return self._history.copy()

    @property
    def options(self):
        return ["2026-06-19"]

    def option_chain(self, expiry):
        frame = pd.DataFrame(
            [
                {
                    "contractSymbol": "SPY260619C00600000",
                    "strike": 600.0,
                    "bid": 1.0,
                    "ask": 1.2,
                    "lastPrice": 1.1,
                    "volume": 10,
                    "openInterest": 100,
                }
            ]
        )
        return SimpleNamespace(calls=frame.copy(), puts=frame.copy())


class AlpacaMarketDataTests(unittest.TestCase):
    def _env(self):
        return patch.dict(
            os.environ,
            {
                "APCA_API_KEY_ID": "key",
                "APCA_API_SECRET_KEY": "secret",
                "ALPACA_DATA_ENDPOINT": "https://data.alpaca.markets/v2",
                "ALPACA_TRADING_ENDPOINT": "https://paper-api.alpaca.markets/v2",
                "ALPACA_STOCK_FEED": "sip",
                "ALPACA_OPTIONS_FEED": "opra",
                "ALPACA_ENABLE_DURING_TESTS": "1",
                "OPTIONS_MARKET_DATA_PROVIDER": "alpaca",
                "OPTIONS_RUN_MODE": "",
            },
            clear=False,
        )

    def test_alpaca_stock_bars_and_option_chain_are_normalized(self):
        with self._env():
            client = amd.AlpacaMarketDataClient(session=_FakeSession())
            ticker = amd.AlpacaTicker("SPY", client=client, fallback_factory=_FallbackTicker)

            history = ticker.history(period="5d")
            expiries = ticker.options
            chain = ticker.option_chain(expiries[0])

        self.assertEqual(history.attrs["market_data_source"], amd.ALPACA_STOCK_SOURCE)
        self.assertEqual(history["Close"].tolist(), [601, 603])
        self.assertEqual(expiries, ["2026-06-19"])
        self.assertEqual(chain.market_data_source, amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(chain.calls.iloc[0]["contractSymbol"], "SPY260619C00600000")
        self.assertEqual(chain.calls.iloc[0]["bid"], 10.0)
        self.assertEqual(chain.calls.iloc[0]["ask"], 10.2)
        self.assertEqual(chain.calls.iloc[0]["volume"], 321)
        self.assertEqual(chain.calls.iloc[0]["openInterest"], 1234)
        self.assertEqual(chain.calls.iloc[0]["data_source"], amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(chain.puts.iloc[0]["delta"], -0.48)

    def test_stock_bars_formats_explicit_dates_as_rfc3339_utc(self):
        with self._env():
            session = _FakeSession()
            client = amd.AlpacaMarketDataClient(session=session)
            history = client.stock_bars("SPY", start="2026-05-14", end="2026-05-21", interval="1d")

        self.assertEqual(history.attrs["market_data_source"], amd.ALPACA_STOCK_SOURCE)
        params = session.calls[0][1]
        self.assertEqual(params["start"], "2026-05-14T00:00:00+00:00")
        self.assertEqual(params["end"], "2026-05-21T00:00:00+00:00")

    def test_historical_option_bars_omit_feed_and_keep_contract_keys(self):
        with self._env():
            session = _FakeSession()
            client = amd.AlpacaMarketDataClient(session=session)
            bars = client.historical_option_bars(
                ["SPY260619C00600000", "SPY260619P00590000"],
                start="2026-05-18",
                end="2026-05-19",
            )

        url, params = session.calls[0]
        self.assertTrue(url.endswith("/v1beta1/options/bars"))
        self.assertNotIn("feed", params)
        self.assertEqual(params["timeframe"], "1Day")
        self.assertEqual(params["start"], "2026-05-18T00:00:00+00:00")
        self.assertEqual(sorted(bars), ["SPY260619C00600000", "SPY260619P00590000"])
        self.assertEqual(bars["SPY260619C00600000"][0]["c"], 1.2)

    def test_historical_option_trades_omit_feed_and_keep_contract_keys(self):
        with self._env():
            session = _FakeSession()
            client = amd.AlpacaMarketDataClient(session=session)
            trades = client.historical_option_trades(
                ["SPY260619C00600000", "SPY260619P00590000"],
                start="2026-05-18",
                end="2026-05-19",
            )

        url, params = session.calls[0]
        self.assertTrue(url.endswith("/v1beta1/options/trades"))
        self.assertNotIn("feed", params)
        self.assertEqual(params["start"], "2026-05-18T00:00:00+00:00")
        self.assertEqual(sorted(trades), ["SPY260619C00600000", "SPY260619P00590000"])
        self.assertEqual(trades["SPY260619C00600000"][0]["p"], 1.22)

    def test_option_contracts_can_request_inactive_historical_contracts(self):
        with self._env():
            session = _FakeSession()
            client = amd.AlpacaMarketDataClient(session=session)
            contracts = client.option_contracts(
                "SPY",
                status="inactive",
                expiration_date_gte="2024-02-01",
                expiration_date_lte="2024-02-29",
                option_type="call",
            )

        params = session.calls[0][1]
        self.assertEqual(params["status"], "inactive")
        self.assertEqual(params["expiration_date_gte"], "2024-02-01")
        self.assertEqual(params["expiration_date_lte"], "2024-02-29")
        self.assertEqual(contracts[0]["symbol"], "SPY260619C00600000")

    def test_yahoo_fallback_is_labeled_when_alpaca_request_fails(self):
        class _FailingSession(_FakeSession):
            def get(self, url, headers=None, params=None, timeout=None):
                return _Response({"message": "forbidden"}, status_code=403)

        with self._env(), patch.dict(os.environ, {"ALPACA_ALLOW_YAHOO_FALLBACK": "1"}, clear=False):
            ticker = amd.AlpacaTicker(
                "SPY",
                client=amd.AlpacaMarketDataClient(session=_FailingSession()),
                fallback_factory=_FallbackTicker,
            )
            history = ticker.history(period="5d")
            chain = ticker.option_chain("2026-06-19")

        self.assertEqual(history.attrs["market_data_source"], amd.YAHOO_FALLBACK_SOURCE)
        self.assertEqual(chain.market_data_source, amd.YAHOO_FALLBACK_SOURCE)
        self.assertEqual(chain.calls.iloc[0]["data_source"], amd.YAHOO_FALLBACK_SOURCE)

    def test_yahoo_fallback_is_disabled_by_default(self):
        class _FailingSession(_FakeSession):
            def get(self, url, headers=None, params=None, timeout=None):
                return _Response({"message": "forbidden"}, status_code=403)

        with self._env(), patch.dict(os.environ, {"ALPACA_ALLOW_YAHOO_FALLBACK": ""}, clear=False):
            ticker = amd.AlpacaTicker(
                "SPY",
                client=amd.AlpacaMarketDataClient(session=_FailingSession()),
                fallback_factory=_FallbackTicker,
            )
            with self.assertRaises(amd.AlpacaMarketDataError):
                ticker.history(period="5d")

    def test_exact_contract_spread_keeps_alpaca_source_metadata(self):
        expiry = (datetime.now().date() + timedelta(days=30)).strftime("%Y-%m-%d")
        expiry_code = expiry.replace("-", "")[2:]
        calls = pd.DataFrame(
            [
                {
                    "contractSymbol": f"SPY{expiry_code}C00600000",
                    "strike": 600.0,
                    "bid": 12.0,
                    "ask": 12.2,
                    "lastPrice": 12.1,
                    "impliedVolatility": 0.22,
                    "delta": 0.52,
                    "volume": 500,
                    "openInterest": 1500,
                    "lastTradeDate": datetime.now().isoformat(),
                    "data_source": amd.ALPACA_OPTIONS_SOURCE,
                    "source_feed": "opra",
                },
                {
                    "contractSymbol": f"SPY{expiry_code}C00610000",
                    "strike": 610.0,
                    "bid": 6.8,
                    "ask": 7.0,
                    "lastPrice": 6.9,
                    "impliedVolatility": 0.22,
                    "delta": 0.25,
                    "volume": 450,
                    "openInterest": 1400,
                    "lastTradeDate": datetime.now().isoformat(),
                    "data_source": amd.ALPACA_OPTIONS_SOURCE,
                    "source_feed": "opra",
                },
            ]
        )
        chain = SimpleNamespace(calls=calls, puts=pd.DataFrame(), market_data_source=amd.ALPACA_OPTIONS_SOURCE)

        with patch.object(oc, "_cached_options_metadata", return_value=SimpleNamespace(status="fresh", source=amd.ALPACA_OPTIONS_SOURCE, value=[expiry])), \
             patch.object(oc, "_cached_option_chain_metadata", return_value=SimpleNamespace(status="fresh", source=amd.ALPACA_OPTIONS_SOURCE, value=chain)):
            spread = oc._fetch_best_spread(
                "SPY",
                "call",
                0.50,
                0.25,
                30,
                stock_price=603.0,
                hv30_fallback=0.22,
            )

        self.assertIsNotNone(spread)
        self.assertEqual(oc._live_contract_selection_source(spread), "live_chain_exact_contract")
        self.assertEqual(spread["options_data_source"], amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(spread["long_leg"]["data_source"], amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(spread["entry_quote_snapshot"]["options_data_source"], amd.ALPACA_OPTIONS_SOURCE)

    def test_yahoo_fallback_chain_is_not_promoted_as_executable_when_alpaca_enabled(self):
        snapshot = {
            "strategy_type": "vertical_spread",
            "live_chain": True,
            "long_leg": {
                "contract_symbol": "SPY260619C00600000",
                "data_source": amd.YAHOO_FALLBACK_SOURCE,
            },
            "short_leg": {
                "contract_symbol": "SPY260619C00610000",
                "data_source": amd.YAHOO_FALLBACK_SOURCE,
            },
        }
        with self._env():
            self.assertEqual(oc._live_contract_selection_source(snapshot), "fallback_chain_contract")
            self.assertEqual(
                oc._live_pick_promotion_class(
                    has_exact_contract=False,
                    calibration_lookup={"dense_cohort": True},
                    dense_calibration={"dense_cohort": True},
                ),
                "research_bootstrap",
            )

    def test_forward_ledger_exact_contract_eligibility_allows_alpaca_picks(self):
        pick = {
            "ticker": "SPY",
            "strategy_type": "vertical_spread",
            "contract_symbol": "SPY260619C00600000",
            "short_contract_symbol": "SPY260619C00610000",
            "selection_source": "live_chain_exact_contract",
            "promotion_class": "research_bootstrap",
            "quote_freshness_status": "fresh",
            "quote_basis": "mid",
            "entry_execution_price": 5.2,
            "entry_execution_basis": "spread_ask_bid",
            "legs": [
                {
                    "role": "long",
                    "contract_symbol": "SPY260619C00600000",
                    "strike": 600.0,
                    "bid": 10.0,
                    "ask": 10.2,
                    "quote_basis": "mid",
                },
                {
                    "role": "short",
                    "contract_symbol": "SPY260619C00610000",
                    "strike": 610.0,
                    "bid": 4.8,
                    "ask": 5.0,
                    "quote_basis": "mid",
                },
            ],
            "market_data_source": amd.ALPACA_OPTIONS_SOURCE,
            "options_data_source": amd.ALPACA_OPTIONS_SOURCE,
        }
        status, blockers, freshness = fol._eligibility_for_pick(
            pick,
            provenance={
                "evidence_class": fol.LIVE_PRODUCTION_EVIDENCE_CLASS,
                "is_fixture": False,
                "quote_freshness_status": "fresh",
            },
            policy_applied=True,
            truth_source="imported_daily_truth",
            promotion_status="approved",
            positions_available=True,
            positions_error=None,
        )

        self.assertEqual(status, fol.ELIGIBLE_STATUS)
        self.assertEqual(blockers, [])
        self.assertEqual(freshness, "fresh")

    def test_normal_and_commodity_lane_scans_preserve_alpaca_source_fields(self):
        def fake_scan(*, symbols=None, **kwargs):
            ticker = (symbols or ["SPY"])[0]
            return [
                {
                    "ticker": ticker,
                    "direction": "call",
                    "option_type": "call",
                    "strategy_type": "vertical_spread",
                    "asset_class": "index",
                    "contract_symbol": f"{ticker}260619C00600000",
                    "short_contract_symbol": f"{ticker}260619C00610000",
                    "strike": 600.0,
                    "short_strike": 610.0,
                    "spread_width": 10.0,
                    "net_debit": 4.0,
                    "debit_pct_of_width": 40.0,
                    "entry_execution_price": 4.1,
                    "entry_execution_basis": "spread_ask_bid",
                    "legs": [
                        {
                            "role": "long",
                            "contract_symbol": f"{ticker}260619C00600000",
                            "strike": 600.0,
                            "bid": 8.0,
                            "ask": 8.2,
                            "premium": 8.1,
                            "quote_basis": "mid",
                            "data_source": amd.ALPACA_OPTIONS_SOURCE,
                        },
                        {
                            "role": "short",
                            "contract_symbol": f"{ticker}260619C00610000",
                            "strike": 610.0,
                            "bid": 4.0,
                            "ask": 4.2,
                            "premium": 4.1,
                            "quote_basis": "mid",
                            "data_source": amd.ALPACA_OPTIONS_SOURCE,
                        },
                    ],
                    "direction_score": 90.0,
                    "quality_score": 82.0,
                    "tech_score": 88.0,
                    "ev_pct": 22.0,
                    "dte": 30,
                    "expiry": "2026-06-19",
                    "quote_basis": "mid",
                    "quote_freshness_status": "fresh",
                    "selection_source": "live_chain_exact_contract",
                    "candidate_execution_label": "executable_opra_paper_candidate",
                    "promotion_class": "promotable_exact_contract",
                    "market_data_source": amd.ALPACA_OPTIONS_SOURCE,
                    "options_data_source": amd.ALPACA_OPTIONS_SOURCE,
                    "underlying_data_source": amd.ALPACA_STOCK_SOURCE,
                    "quote_source": amd.ALPACA_OPTIONS_SOURCE,
                }
            ]

        normal = ss.run_supervised_scan(
            scan_func=fake_scan,
            positions_repository=None,
            n_picks=1,
            watchlist_size=1,
            playbook_id="short_term",
            enforce_portfolio_caps=False,
            include_blocked_guardrail_picks=True,
        )
        with patch.object(ss, "_load_ai_commodity_readiness", return_value={}):
            commodity = ss.run_supervised_scan(
                scan_func=fake_scan,
                positions_repository=None,
                n_picks=1,
                watchlist_size=1,
                playbook_id="ai_commodity_infra_observation",
                enforce_portfolio_caps=False,
                include_blocked_guardrail_picks=True,
            )

        self.assertEqual(normal["picks"][0]["options_data_source"], amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(commodity["picks"][0]["options_data_source"], amd.ALPACA_OPTIONS_SOURCE)
        self.assertEqual(commodity["playbook"]["id"], "ai_commodity_infra_observation")


if __name__ == "__main__":
    unittest.main()
