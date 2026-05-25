from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpaca_market_data import _data_root, _headers  # noqa: E402
from scripts.capture_alpaca_opra_daily_snapshots import load_env_file  # noqa: E402


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ai-commodity-infra" / "progress"


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {"_non_json_text": response.text[:500]}
    return payload if isinstance(payload, dict) else {"_json_type": type(payload).__name__, "value": payload}


def _sample_contract(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            SELECT
                q.contract_symbol,
                q.underlying,
                q.expiry,
                q.option_type,
                q.strike,
                q.bid,
                q.ask,
                q.as_of_utc,
                q.quote_date_et
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.source_label = 'alpaca_opra_daily_snapshot'
              AND q.bid > 0
              AND q.ask >= q.bid
            ORDER BY q.quote_date_et DESC, q.open_interest DESC, q.volume DESC, q.id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else {}


def _contract_window(sample: dict[str, Any], minutes: int) -> tuple[str, str]:
    raw = str(sample.get("as_of_utc") or "").replace("Z", "+00:00")
    try:
        center = datetime.fromisoformat(raw)
    except ValueError:
        center = datetime.now(UTC)
    if center.tzinfo is None:
        center = center.replace(tzinfo=UTC)
    center = center.astimezone(UTC)
    start = center - timedelta(minutes=max(1, int(minutes)))
    end = center + timedelta(minutes=max(1, int(minutes)))
    return (
        start.isoformat(timespec="seconds").replace("+00:00", "Z"),
        end.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def _first_rows(payload: dict[str, Any], container_key: str, symbol: str) -> list[dict[str, Any]]:
    container = payload.get(container_key)
    if isinstance(container, dict):
        rows = container.get(symbol) or container.get(symbol.upper()) or []
        if isinstance(rows, dict):
            return [rows]
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if container_key == "snapshots":
            return [row for row in container.values() if isinstance(row, dict)]
    return []


def _summarize_response(
    *,
    label: str,
    method: str,
    url: str,
    params: dict[str, Any],
    response: requests.Response,
    symbol: str,
    data_key: str | None = None,
) -> dict[str, Any]:
    payload = _safe_json(response)
    rows = _first_rows(payload, data_key, symbol) if data_key else []
    message = payload.get("message") or payload.get("error") or payload.get("_non_json_text")
    summary: dict[str, Any] = {
        "label": label,
        "method": method,
        "url": url,
        "params": {key: value for key, value in params.items() if key != "page_token"},
        "status_code": response.status_code,
        "ok": response.ok,
        "top_level_keys": sorted(payload.keys())[:20],
        "message": str(message)[:500] if message else None,
        "next_page_token_present": bool(payload.get("next_page_token")),
    }
    if data_key:
        summary["data_key"] = data_key
        summary["row_count_first_page_for_symbol"] = len(rows)
        summary["first_row_keys"] = sorted(rows[0].keys()) if rows else []
    return summary


def _get(session: requests.Session, url: str, params: dict[str, Any]) -> requests.Response:
    return session.get(url, headers=_headers(), params=params, timeout=30)


def probe(sample: dict[str, Any], *, window_minutes: int) -> dict[str, Any]:
    symbol = str(sample.get("contract_symbol") or "").strip().upper()
    underlying = str(sample.get("underlying") or "").strip().upper()
    expiry = str(sample.get("expiry") or "")[:10]
    option_type = str(sample.get("option_type") or "").strip().lower()
    if not symbol:
        raise RuntimeError("No Alpaca OPRA contract is available in the local store to probe with.")

    start, end = _contract_window(sample, window_minutes)
    root = _data_root()
    session = requests.Session()
    endpoints = [
        {
            "label": "documented_historical_option_bars",
            "url": f"{root}/v1beta1/options/bars",
            "params": {
                "symbols": symbol,
                "timeframe": "1Min",
                "start": start,
                "end": end,
                "limit": 5,
                "sort": "asc",
            },
            "data_key": "bars",
        },
        {
            "label": "documented_historical_option_trades",
            "url": f"{root}/v1beta1/options/trades",
            "params": {
                "symbols": symbol,
                "start": start,
                "end": end,
                "limit": 5,
                "sort": "asc",
            },
            "data_key": "trades",
        },
        {
            "label": "suspected_historical_option_quotes",
            "url": f"{root}/v1beta1/options/quotes",
            "params": {
                "symbols": symbol,
                "start": start,
                "end": end,
                "limit": 5,
                "sort": "asc",
                "feed": "opra",
            },
            "data_key": "quotes",
        },
        {
            "label": "documented_latest_option_quotes",
            "url": f"{root}/v1beta1/options/quotes/latest",
            "params": {"symbols": symbol, "feed": "opra"},
            "data_key": "quotes",
        },
        {
            "label": "documented_option_snapshots_by_contract",
            "url": f"{root}/v1beta1/options/snapshots",
            "params": {"symbols": symbol, "feed": "opra"},
            "data_key": None,
        },
    ]
    if underlying and expiry:
        chain_params: dict[str, Any] = {
            "expiration_date": expiry,
            "limit": 10,
            "feed": "opra",
        }
        if option_type in {"call", "put"}:
            chain_params["type"] = option_type
        endpoints.append(
            {
                "label": "documented_option_chain_snapshots_by_underlying",
                "url": f"{root}/v1beta1/options/snapshots/{underlying}",
                "params": chain_params,
                "data_key": None,
            }
        )

    results = []
    for endpoint in endpoints:
        response = _get(session, endpoint["url"], endpoint["params"])
        results.append(
            _summarize_response(
                label=endpoint["label"],
                method="GET",
                url=endpoint["url"],
                params=endpoint["params"],
                response=response,
                symbol=symbol,
                data_key=endpoint.get("data_key"),
            )
        )

    historical_quotes = next(item for item in results if item["label"] == "suspected_historical_option_quotes")
    historical_bars = next(item for item in results if item["label"] == "documented_historical_option_bars")
    historical_trades = next(item for item in results if item["label"] == "documented_historical_option_trades")
    latest_quotes = next(item for item in results if item["label"] == "documented_latest_option_quotes")
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "provider": "alpaca:sip:opra",
        "sample_contract": sample,
        "probe_window_utc": {"start": start, "end": end},
        "access_findings": {
            "historical_option_bars_accessible": bool(historical_bars["ok"]),
            "historical_option_trades_accessible": bool(historical_trades["ok"]),
            "historical_option_quotes_accessible": bool(historical_quotes["ok"]),
            "latest_option_quotes_accessible": bool(latest_quotes["ok"]),
            "historical_option_quotes_status_code": historical_quotes["status_code"],
            "historical_option_quotes_message": historical_quotes.get("message"),
            "proof_grade_bid_ask_backfill_available_from_alpaca_probe": bool(historical_quotes["ok"]),
        },
        "endpoint_results": results,
        "interpretation": (
            "Historical option bars/trades access does not prove bid/ask replay. "
            "The lane can accelerate final proof from Alpaca only if the historical option quotes endpoint returns "
            "point-in-time bid/ask rows for OPRA-entitled credentials."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe authenticated Alpaca option history access without printing secrets.")
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--contract-symbol", help="Optional OCC option contract symbol to probe.")
    parser.add_argument("--underlying", help="Optional underlying for --contract-symbol.")
    parser.add_argument("--expiry", help="Optional expiry for --contract-symbol, YYYY-MM-DD.")
    parser.add_argument("--option-type", choices=["call", "put"], help="Optional option type for --contract-symbol.")
    parser.add_argument("--as-of-utc", help="Optional center timestamp for historical probe window.")
    parser.add_argument("--window-minutes", type=int, default=30)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    os.environ.setdefault("OPTIONS_MARKET_DATA_PROVIDER", "alpaca")
    os.environ.setdefault("ALPACA_STOCK_FEED", "sip")
    os.environ.setdefault("ALPACA_OPTIONS_FEED", "opra")

    sample = _sample_contract(Path(args.db_path))
    if args.contract_symbol:
        sample.update(
            {
                "contract_symbol": args.contract_symbol.strip().upper(),
                "underlying": (args.underlying or sample.get("underlying") or "").strip().upper(),
                "expiry": args.expiry or sample.get("expiry"),
                "option_type": args.option_type or sample.get("option_type"),
                "as_of_utc": args.as_of_utc or sample.get("as_of_utc") or datetime.now(UTC).isoformat(),
            }
        )

    report = probe(sample, window_minutes=args.window_minutes)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at_utc"].replace("-", "").replace(":", "").replace("Z", "Z")
    path = output_dir / f"alpaca_options_history_access_probe_{stamp}.json"
    latest_path = output_dir / "alpaca_options_history_access_probe_latest.json"
    serialized = json.dumps(report, indent=2)
    path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")

    if args.json:
        print(serialized)
    else:
        print(
            json.dumps(
                {
                    "generated_at_utc": report["generated_at_utc"],
                    "sample_contract": report["sample_contract"].get("contract_symbol"),
                    "access_findings": report["access_findings"],
                    "artifact": str(path),
                    "latest": str(latest_path),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
