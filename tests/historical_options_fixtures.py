from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from options_algorithm_fixtures import make_history


def make_validation_history(length: int = 140, start: float = 400.0, step: float = 0.9) -> pd.DataFrame:
    return make_history(length=length, start=start, step=step, wave=1.2, volume=15_000_000)


def _next_fridays(base_date: date) -> list[date]:
    days_until_friday = (4 - base_date.weekday()) % 7
    first = base_date + timedelta(days=days_until_friday or 7)
    second = first + timedelta(days=7)
    return [first, second]


def _contract_symbol(symbol: str, expiry: date, option_type: str, strike: float) -> str:
    type_char = "C" if option_type == "call" else "P"
    strike_component = int(round(strike * 1000))
    return f"{symbol.upper()}{expiry.strftime('%y%m%d')}{type_char}{strike_component:08d}"


def write_historical_options_csv(
    path: str | Path,
    histories: dict[str, pd.DataFrame],
    *,
    strike_span: int = 12,
) -> Path:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "as_of",
        "underlying",
        "contract_symbol",
        "expiry",
        "option_type",
        "strike",
        "bid",
        "ask",
        "last",
        "iv",
        "underlying_price",
        "volume",
        "open_interest",
    ]
    with csv_path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for symbol, history in histories.items():
            for idx, (timestamp, row) in enumerate(history.iterrows()):
                trade_date = pd.Timestamp(timestamp).date()
                expiries = _next_fridays(trade_date)
                open_price = float(row["Open"])
                close_price = float(row["Close"])
                center_strike = round(close_price)
                strikes = [float(center_strike + offset) for offset in range(-strike_span, strike_span + 1)]
                for expiry in expiries:
                    dte_days = max((expiry - trade_date).days, 1)
                    for option_type in ("call", "put"):
                        for strike in strikes:
                            entry_underlying = open_price
                            close_underlying = close_price
                            entry_intrinsic = max(0.0, entry_underlying - strike) if option_type == "call" else max(0.0, strike - entry_underlying)
                            close_intrinsic = max(0.0, close_underlying - strike) if option_type == "call" else max(0.0, strike - close_underlying)
                            time_value = max(0.35, min(4.0, dte_days / 7.0))
                            entry_price = round(max(0.2, entry_intrinsic * 0.55 + time_value), 4)
                            close_price_option = round(max(0.2, close_intrinsic * 0.55 + max(0.2, time_value - 0.08)), 4)
                            contract_symbol = _contract_symbol(symbol, expiry, option_type, strike)
                            for snapshot_time, option_price, underlying_price in (
                                (time(10, 15), entry_price, entry_underlying),
                                (time(15, 55), close_price_option, close_underlying),
                            ):
                                local_stamp = datetime.combine(trade_date, snapshot_time)
                                writer.writerow(
                                    {
                                        "as_of": local_stamp.isoformat(),
                                        "underlying": symbol,
                                        "contract_symbol": contract_symbol,
                                        "expiry": expiry.isoformat(),
                                        "option_type": option_type,
                                        "strike": f"{strike:.2f}",
                                        "bid": f"{option_price * 0.97:.4f}",
                                        "ask": f"{option_price * 1.03:.4f}",
                                        "last": f"{option_price:.4f}",
                                        "iv": "0.28",
                                        "underlying_price": f"{underlying_price:.4f}",
                                        "volume": str(500 + idx),
                                        "open_interest": str(1000 + idx),
                                    }
                                )
    return csv_path


def write_daily_options_parquet(
    path: str | Path,
    histories: dict[str, pd.DataFrame],
    *,
    symbol: str,
    strike_span: int = 8,
) -> Path:
    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    history = histories[symbol]
    rows: list[dict[str, Any]] = []
    for idx, (timestamp, row) in enumerate(history.iterrows()):
        trade_date = pd.Timestamp(timestamp).date()
        expiries = _next_fridays(trade_date)
        close_price = float(row["Close"])
        center_strike = round(close_price)
        strikes = [float(center_strike + offset) for offset in range(-strike_span, strike_span + 1)]
        for expiry in expiries:
            dte_days = max((expiry - trade_date).days, 1)
            time_value = max(0.35, min(4.0, dte_days / 7.0))
            for option_type in ("call", "put"):
                for strike in strikes:
                    intrinsic = max(0.0, close_price - strike) if option_type == "call" else max(0.0, strike - close_price)
                    option_price = round(max(0.2, intrinsic * 0.55 + max(0.2, time_value - 0.08)), 4)
                    rows.append(
                        {
                            "contract_id": _contract_symbol(symbol, expiry, option_type, strike),
                            "symbol": symbol,
                            "expiration": expiry.isoformat(),
                            "strike": float(strike),
                            "type": option_type,
                            "date": trade_date.isoformat(),
                            "bid": round(option_price * 0.97, 4),
                            "ask": round(option_price * 1.03, 4),
                            "last": option_price,
                            "mark": option_price,
                            "volume": int(500 + idx),
                            "open_interest": int(1000 + idx),
                            "implied_volatility": 0.28,
                            "delta": 0.32 if option_type == "call" else -0.32,
                            "gamma": 0.04,
                            "theta": -0.08,
                            "vega": 0.11,
                            "rho": 0.02 if option_type == "call" else -0.02,
                        }
                    )
    pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    return parquet_path


def write_underlying_daily_parquet(
    path: str | Path,
    histories: dict[str, pd.DataFrame],
    *,
    symbol: str,
) -> Path:
    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    history = histories[symbol].copy()
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp(idx).date().isoformat() for idx in history.index],
            "close": history["Close"].astype(float).tolist(),
        }
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


class HistoricalReplayTicker:
    def __init__(self, symbol: str, history_df: pd.DataFrame):
        self.symbol = symbol
        self._history_df = history_df
        self.info = {"sector": "Index ETF" if symbol in {"SPY", "QQQ"} else "Technology"}

    def history(self, period="90d", start=None, end=None, interval=None):
        return self._history_df.copy()


def make_historical_replay_ticker_factory(histories: dict[str, pd.DataFrame]):
    def _factory(symbol: str) -> HistoricalReplayTicker:
        if symbol not in histories:
            raise KeyError(symbol)
        return HistoricalReplayTicker(symbol, histories[symbol])

    return _factory
