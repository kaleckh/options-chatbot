import importlib.util
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
BACKEND_MAIN = ROOT / "python-backend" / "main.py"
FROZEN_NOW = datetime(2026, 3, 31, 9, 45, 0)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls(
                FROZEN_NOW.year,
                FROZEN_NOW.month,
                FROZEN_NOW.day,
                FROZEN_NOW.hour,
                FROZEN_NOW.minute,
                FROZEN_NOW.second,
            )
        aware = FROZEN_NOW.replace(tzinfo=timezone.utc).astimezone(tz)
        return cls(
            aware.year,
            aware.month,
            aware.day,
            aware.hour,
            aware.minute,
            aware.second,
            aware.microsecond,
            tzinfo=aware.tzinfo,
        )


def make_history(
    length: int,
    start: float,
    step: float = 0.0,
    wave: float = 0.0,
    volume: float = 8_000_000,
) -> pd.DataFrame:
    dates = pd.bdate_range(end=FROZEN_NOW.date(), periods=length)
    base = start + np.arange(length, dtype=float) * step
    if wave:
        base = base + np.sin(np.arange(length) / 2.0) * wave
    opens = base - 0.35
    highs = np.maximum(opens, base) + 0.85
    lows = np.minimum(opens, base) - 0.85
    volumes = np.full(length, float(volume))
    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": base,
            "Volume": volumes,
        },
        index=dates,
    )


def make_option_frame(symbol: str, expiry: str, option_type: str, spot: float, illiquid: bool = False) -> pd.DataFrame:
    strikes = [round(spot - 10.0, 2), round(spot - 5.0, 2), round(spot, 2), round(spot + 5.0, 2), round(spot + 10.0, 2)]
    rows: list[dict[str, Any]] = []
    expiry_code = expiry.replace("-", "")[2:]
    for idx, strike in enumerate(strikes):
        premium = max(0.6, 4.2 - idx * 0.55)
        contract_volume = 0 if illiquid else 250 - idx * 15
        open_interest = 0 if illiquid else 1500 - idx * 100
        bid = 0.0 if illiquid else round(max(0.01, premium - 0.01), 2)
        ask = 0.0 if illiquid else round(premium + 0.01, 2)
        strike_code = f"{int(round(strike * 1000)):08d}"
        rows.append(
            {
                "contractSymbol": f"{symbol.upper()}{expiry_code}{option_type.upper()}{strike_code}",
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "lastPrice": round(premium, 2),
                "impliedVolatility": 0.11 + idx * 0.01,
                "volume": contract_volume,
                "openInterest": open_interest,
                "lastTradeDate": pd.Timestamp(FROZEN_NOW, tz="America/New_York"),
            }
        )
    return pd.DataFrame(rows)


class FixtureTicker:
    def __init__(
        self,
        symbol: str,
        history_df: pd.DataFrame,
        sector: str | None = None,
        option_chains: dict[str, SimpleNamespace] | None = None,
    ):
        self.symbol = symbol
        self._history_df = history_df
        self._option_chains = option_chains or {}
        self.info = {"sector": sector} if sector is not None else {}
        self.earnings_dates = pd.DataFrame()

    @property
    def options(self):
        return list(self._option_chains.keys())

    def history(self, period="90d", start=None, end=None, interval=None):
        return self._history_df.copy()

    def option_chain(self, expiry: str):
        if expiry not in self._option_chains:
            raise KeyError(expiry)
        snap = self._option_chains[expiry]
        return SimpleNamespace(calls=snap.calls.copy(), puts=snap.puts.copy())


@dataclass
class OptionsAlgorithmFixtureBundle:
    watchlist: list[str]
    tickers: dict[str, FixtureTicker]

    def make_ticker(self, symbol: str):
        if symbol not in self.tickers:
            raise KeyError(symbol)
        return self.tickers[symbol]


def build_options_algorithm_fixture_bundle() -> OptionsAlgorithmFixtureBundle:
    expirations = [
        (FROZEN_NOW.date() + timedelta(days=8)).strftime("%Y-%m-%d"),
        (FROZEN_NOW.date() + timedelta(days=17)).strftime("%Y-%m-%d"),
        (FROZEN_NOW.date() + timedelta(days=24)).strftime("%Y-%m-%d"),
    ]

    spy_history = make_history(length=320, start=400.0, step=1.3, wave=8.0, volume=75_000_000)
    aaa_history = make_history(length=320, start=120.0, step=1.05, wave=4.0, volume=9_000_000)
    illq_history = make_history(length=320, start=55.0, step=0.8, wave=2.5, volume=80_000)
    fail_history = make_history(length=320, start=90.0, step=0.0, wave=0.04, volume=8_500_000)
    vix_history = make_history(length=40, start=18.0, step=0.0, volume=0)

    tickers = {
        "SPY": FixtureTicker("SPY", spy_history, sector=None, option_chains={
            expiry: SimpleNamespace(
                calls=make_option_frame("SPY", expiry, "C", float(spy_history["Close"].iloc[-1])),
                puts=make_option_frame("SPY", expiry, "P", float(spy_history["Close"].iloc[-1])),
            )
            for expiry in expirations
        }),
        "AAA": FixtureTicker("AAA", aaa_history, sector="Technology", option_chains={
            expiry: SimpleNamespace(
                calls=make_option_frame("AAA", expiry, "C", float(aaa_history["Close"].iloc[-1])),
                puts=make_option_frame("AAA", expiry, "P", float(aaa_history["Close"].iloc[-1])),
            )
            for expiry in expirations
        }),
        "ILLQ": FixtureTicker("ILLQ", illq_history, sector="Technology", option_chains={
            expiry: SimpleNamespace(
                calls=make_option_frame("ILLQ", expiry, "C", float(illq_history["Close"].iloc[-1]), illiquid=True),
                puts=make_option_frame("ILLQ", expiry, "P", float(illq_history["Close"].iloc[-1]), illiquid=True),
            )
            for expiry in expirations
        }),
        "FAIL": FixtureTicker("FAIL", fail_history, sector="Industrials", option_chains={
            expiry: SimpleNamespace(
                calls=make_option_frame("FAIL", expiry, "C", float(fail_history["Close"].iloc[-1])),
                puts=make_option_frame("FAIL", expiry, "P", float(fail_history["Close"].iloc[-1])),
            )
            for expiry in expirations
        }),
        "^VIX": FixtureTicker("^VIX", vix_history),
    }
    return OptionsAlgorithmFixtureBundle(
        watchlist=["SPY", "AAA", "ILLQ", "FAIL"],
        tickers=tickers,
    )


def build_tracked_position_scan_pick(bundle: OptionsAlgorithmFixtureBundle) -> dict[str, Any]:
    ticker = bundle.tickers["AAA"]
    spot = float(ticker.history()["Close"].iloc[-1])
    expiry = ticker.options[0]
    calls = ticker.option_chain(expiry).calls
    strike = round(spot + 5.0, 2)
    contract_symbol = str(calls.loc[calls["strike"] == strike, "contractSymbol"].iloc[0])
    return {
        "ticker": "AAA",
        "type": "call",
        "prediction_type": "daily_scan",
        "direction": "call",
        "direction_score": 74.0,
        "quality_score": 68.0,
        "tech_score": 72.0,
        "ev": 19.5,
        "dte": 8,
        "target_move_pct": 4.25,
        "stock_price": round(spot, 2),
        "strike": strike,
        "premium": 3.20,
        "contract_symbol": contract_symbol,
        "expiry": expiry,
        "asset_class": "equity",
        "stop_loss_pct": 50.0,
        "profit_target_pct": 100.0,
        "time_exit_day": 4,
        "ret5": 2.8,
        "rsi14": 59.0,
        "strategy_label": "Hold to target",
        "strategy_comment": "High-conviction setup with aligned regime.",
    }


def load_backend_main(db_path: str, database_url: str | None = ""):
    module_name = f"options_chatbot_test_backend_{abs(hash(db_path))}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, BACKEND_MAIN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load backend module from {BACKEND_MAIN}")

    module = importlib.util.module_from_spec(spec)
    original_connect = sqlite3.connect

    def _connect(path, *args, **kwargs):
        target = db_path if str(path).endswith("chat_history.db") else path
        return original_connect(target, *args, **kwargs)

    default_env = {
        "DATABASE_URL": database_url or "",
        "FORWARD_OPTIONS_LEDGER_DB_PATH": str(Path(db_path).with_name("forward_tracking_test.db")),
        "FORWARD_OPTIONS_AUTHORITATIVE_LEDGER_DB_PATH": str(Path(db_path).with_name("forward_tracking_test.db")),
        "OPTIONS_EVIDENCE_CLASS": "e2e_test",
        "OPTIONS_RUN_MODE": "test_harness",
        "OPTIONS_IS_FIXTURE": "1",
    }

    with patch("sqlite3.connect", side_effect=_connect), patch.dict(
        "os.environ",
        default_env,
        clear=False,
    ):
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module
