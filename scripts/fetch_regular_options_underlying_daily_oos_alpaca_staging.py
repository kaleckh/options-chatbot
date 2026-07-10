from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpaca_market_data import AlpacaMarketDataClient, configured_for_alpaca  # noqa: E402
from scripts.capture_alpaca_opra_daily_snapshots import load_env_file  # noqa: E402


REPORT_ID = "regular_options_underlying_daily_oos_alpaca_staging_fetch"
DEFAULT_OUTPUT = ROOT / "data" / "import-staging" / "underlying_daily" / "point_in_time_underlying_daily_ohlcv_adjusted_oos_v1.csv"
DEFAULT_UNIVERSE = "SPY,QQQ,IWM,DIA,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM"

CSV_HEADER = (
    "symbol,bar_date,open,high,low,close,adjustment_policy,volume,vendor,source,"
    "source_event_date,published_at_utc,known_at_utc,fetched_at_utc,adjustment_mode,"
    "corporate_action_basis,source_url_or_file_name,provenance_id,source_quality"
)
# Match the accepted point_in_time_underlying_daily_ohlcv_adjusted_v1.csv provenance
# exactly: raw unadjusted SIP daily bars with a fixed conservative 21:15Z same-day
# publication timestamp (later than actual SIP publication in both EST and EDT).
PUBLISHED_AT_TIME_UTC = "21:15:00Z"
VENDOR = "Alpaca Markets SIP"
SOURCE = "alpaca_sip_stock_bars"
ADJUSTMENT_POLICY = "raw_unadjusted_alpaca_sip_daily_bar"
ADJUSTMENT_MODE = "raw_unadjusted"
CORPORATE_ACTION_BASIS = "alpaca_sip_raw_daily_bars_no_adjustment"
SOURCE_URL = "https://data.alpaca.markets/v2/stocks/bars"
SOURCE_QUALITY = "trusted"


def fetch_rows(client: AlpacaMarketDataClient, symbol: str, *, start: str, end: str, fetched_at: str) -> list[str]:
    frame = client.stock_bars(symbol, start=f"{start}T00:00:00Z", end=f"{end}T23:59:59Z", interval="1d")
    rows: list[str] = []
    for timestamp, bar in frame.iterrows():
        bar_date = timestamp.tz_convert("America/New_York").date().isoformat()
        if not (start <= bar_date <= end):
            continue
        published_at = f"{bar_date}T{PUBLISHED_AT_TIME_UTC}"
        rows.append(
            ",".join(
                [
                    symbol,
                    bar_date,
                    f"{float(bar['Open']):.6f}",
                    f"{float(bar['High']):.6f}",
                    f"{float(bar['Low']):.6f}",
                    f"{float(bar['Close']):.6f}",
                    ADJUSTMENT_POLICY,
                    str(int(bar["Volume"])),
                    VENDOR,
                    SOURCE,
                    bar_date,
                    published_at,
                    published_at,
                    fetched_at,
                    ADJUSTMENT_MODE,
                    CORPORATE_ACTION_BASIS,
                    SOURCE_URL,
                    f"{SOURCE}:{symbol}:{bar_date}",
                    SOURCE_QUALITY,
                ]
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Alpaca SIP daily bars into the point-in-time underlying daily staging CSV for the OOS extension window."
    )
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--start", default="2021-10-01")
    parser.add_argument("--end", default="2024-05-31")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    load_env_file(Path(args.env_file))
    if not configured_for_alpaca():
        print(json.dumps({"report_id": REPORT_ID, "status": "blocked_missing_alpaca_credentials"}))
        return 1

    client = AlpacaMarketDataClient()
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    symbols = [item.strip().upper() for item in args.universe.split(",") if item.strip()]
    all_rows: list[str] = []
    per_symbol: dict[str, int] = {}
    errors: list[str] = []
    for symbol in symbols:
        try:
            rows = fetch_rows(client, symbol, start=args.start, end=args.end, fetched_at=fetched_at)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        per_symbol[symbol] = len(rows)
        all_rows.extend(rows)

    status = "staging_csv_written" if all_rows and not errors else "blocked_fetch_errors"
    if all_rows and not errors:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(CSV_HEADER + "\n" + "\n".join(all_rows) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "report_id": REPORT_ID,
                "status": status,
                "output": str(args.output),
                "window": {"start": args.start, "end": args.end},
                "row_count": len(all_rows),
                "per_symbol_rows": per_symbol,
                "errors": errors[:10],
                "source_rows_written_to_trusted_stores": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if status == "staging_csv_written" else 1


if __name__ == "__main__":
    raise SystemExit(main())
