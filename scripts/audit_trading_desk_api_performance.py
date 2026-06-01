from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_FRONTEND_BASE_URL = os.environ.get("TRADING_DESK_AUDIT_BASE_URL", "http://localhost:3000")
DEFAULT_BACKEND_BASE_URL = os.environ.get("PYTHON_BACKEND_URL", "")
BACKEND_DURATION_HEADER = "x-python-backend-duration-ms"


@dataclass(frozen=True)
class EndpointSpec:
    label: str
    target: str
    path: str
    lane: str
    record_class: str
    metric_type: str


FetchResult = tuple[int | None, dict[str, str], bytes, str | None]
Fetcher = Callable[[str, float], FetchResult]


FRONTEND_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        "next_tracked_positions_open",
        "next_route",
        "/api/positions?status=open&compact=1",
        "regular_supervised_options",
        "tracked_position",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "next_tracked_positions_closed_page_100",
        "next_route",
        "/api/positions?status=closed&limit=100&offset=0&compact=1",
        "regular_supervised_options",
        "tracked_position",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "next_suggested_trades_open",
        "next_route",
        "/api/suggested-trades?status=open&compact=1",
        "regular_supervised_options",
        "suggested_trade",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "next_suggested_trades_closed_page_100",
        "next_route",
        "/api/suggested-trades?status=closed&limit=100&offset=0&compact=1",
        "regular_supervised_options",
        "suggested_trade",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "next_options_profit_status",
        "next_route",
        "/api/options-profit/status",
        "regular_supervised_options",
        "proof_status",
        "proof_status",
    ),
)

BACKEND_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        "backend_tracked_positions_open",
        "python_backend",
        "/api/positions?status=open&compact=1",
        "regular_supervised_options",
        "tracked_position",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "backend_tracked_positions_closed_page_100",
        "python_backend",
        "/api/positions?status=closed&limit=100&offset=0&compact=1",
        "regular_supervised_options",
        "tracked_position",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "backend_suggested_trades_open",
        "python_backend",
        "/api/suggested-trades?status=open&compact=1",
        "regular_supervised_options",
        "suggested_trade",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "backend_suggested_trades_closed_page_100",
        "python_backend",
        "/api/suggested-trades?status=closed&limit=100&offset=0&compact=1",
        "regular_supervised_options",
        "suggested_trade",
        "trading_desk_rows",
    ),
    EndpointSpec(
        "backend_options_profit_status",
        "python_backend",
        "/api/options-profit/status",
        "regular_supervised_options",
        "proof_status",
        "proof_status",
    ),
    EndpointSpec(
        "backend_market_data_cache_stats",
        "python_backend",
        "/api/market-data/cache-stats",
        "regular_supervised_options",
        "market_data_cache",
        "market_data_cache_stats",
    ),
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _parse_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 1)


def _header_value(headers: dict[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value)
    return None


def _window_from_path(path: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(path)
    params = urllib.parse.parse_qs(parsed.query)
    window: dict[str, Any] = {}
    for key in ("status", "limit", "offset", "grouped", "compact"):
        values = params.get(key)
        if values:
            window[key] = values[-1]
    return window


def _decode_json(raw: bytes) -> tuple[Any, str | None]:
    if not raw:
        return {}, None
    try:
        return json.loads(raw.decode("utf8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"invalid_json: {exc}"


def _row_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("positions", "trades", "open", "closed"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    page = payload.get("page")
    if isinstance(page, dict):
        returned = page.get("returned")
        if isinstance(returned, int):
            return returned
    return None


def _page(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("page"), dict):
        return None
    page = payload["page"]
    return {
        key: page.get(key)
        for key in ("limit", "offset", "returned")
        if key in page
    }


def _shape(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {
            "top_level_keys": sorted(str(key) for key in payload.keys())[:20],
            "row_count": _row_count(payload),
            "page": _page(payload),
        }
    if isinstance(payload, list):
        return {"top_level_type": "list", "row_count": len(payload)}
    return {"top_level_type": type(payload).__name__}


def _cache_stats(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if "memory_cache_entries" not in payload and "totals" not in payload:
        return None
    return {
        "status": payload.get("status"),
        "memory_cache_entries": payload.get("memory_cache_entries"),
        "memory_cache_families": payload.get("memory_cache_families"),
        "request_scope_active": payload.get("request_scope_active"),
        "request_scope_entries": payload.get("request_scope_entries"),
        "schema_initialized": payload.get("schema_initialized"),
        "totals": payload.get("totals") if isinstance(payload.get("totals"), dict) else {},
    }


def fetch_url(url: str, timeout_seconds: float) -> FetchResult:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return (
                int(response.status),
                {str(key): str(value) for key, value in response.headers.items()},
                response.read(),
                None,
            )
    except urllib.error.HTTPError as exc:
        return (
            int(exc.code),
            {str(key): str(value) for key, value in exc.headers.items()},
            exc.read(),
            f"http_error: {exc.code}",
        )
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        return None, {}, b"", f"request_error: {exc}"


def measure_endpoint(
    spec: EndpointSpec,
    *,
    base_url: str,
    timeout_seconds: float,
    fetcher: Fetcher = fetch_url,
) -> dict[str, Any]:
    url = _join_url(base_url, spec.path)
    started = time.perf_counter()
    status_code, headers, raw, request_error = fetcher(url, timeout_seconds)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    payload, json_error = _decode_json(raw)
    backend_duration_ms = _parse_float(_header_value(headers, BACKEND_DURATION_HEADER))
    ok = bool(status_code is not None and 200 <= status_code < 300 and not request_error and not json_error)
    row: dict[str, Any] = {
        "label": spec.label,
        "target": spec.target,
        "lane": spec.lane,
        "record_class": spec.record_class,
        "metric_type": spec.metric_type,
        "method": "GET",
        "read_only": True,
        "path": spec.path,
        "url": url,
        "window": _window_from_path(spec.path),
        "status_code": status_code,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "backend_duration_ms": backend_duration_ms,
        "payload_bytes": len(raw),
        "payload_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "row_count": _row_count(payload),
        "page": _page(payload),
        "response_shape": _shape(payload),
    }
    cache_stats = _cache_stats(payload)
    if cache_stats:
        row["cache_stats"] = cache_stats
    if request_error or json_error:
        row["error"] = request_error or json_error
    return row


def build_endpoint_plan(base_url: str, backend_url: str | None = None) -> list[tuple[EndpointSpec, str]]:
    plan = [(spec, base_url) for spec in FRONTEND_ENDPOINTS]
    if backend_url:
        plan.extend((spec, backend_url) for spec in BACKEND_ENDPOINTS)
    return plan


def _endpoint_ref(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "label": row.get("label"),
        "target": row.get("target"),
        "path": row.get("path"),
        "status_code": row.get("status_code"),
        "elapsed_ms": row.get("elapsed_ms"),
        "backend_duration_ms": row.get("backend_duration_ms"),
        "payload_bytes": row.get("payload_bytes"),
        "row_count": row.get("row_count"),
        "page": row.get("page"),
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    frontend = [row for row in results if row.get("target") == "next_route"]
    backend = [row for row in results if row.get("target") == "python_backend"]
    ok_count = sum(1 for row in results if row.get("ok"))
    error_count = len(results) - ok_count
    slowest_frontend = max(frontend, key=lambda row: float(row.get("elapsed_ms") or 0.0), default=None)
    slowest_backend = max(backend, key=lambda row: float(row.get("elapsed_ms") or 0.0), default=None)
    largest_payload = max(results, key=lambda row: int(row.get("payload_bytes") or 0), default=None)
    backend_duration_rows = [row for row in results if row.get("backend_duration_ms") is not None]
    slowest_backend_duration = max(
        backend_duration_rows,
        key=lambda row: float(row.get("backend_duration_ms") or 0.0),
        default=None,
    )
    cache_stats = next(
        (row.get("cache_stats") for row in results if row.get("metric_type") == "market_data_cache_stats" and row.get("cache_stats")),
        None,
    )
    return {
        "status": "ok" if results and error_count == 0 else "route_errors" if results else "no_results",
        "endpoint_count": len(results),
        "ok_endpoint_count": ok_count,
        "error_endpoint_count": error_count,
        "frontend_max_elapsed_ms": max((float(row.get("elapsed_ms") or 0.0) for row in frontend), default=None),
        "frontend_total_payload_bytes": sum(int(row.get("payload_bytes") or 0) for row in frontend),
        "backend_max_elapsed_ms": max((float(row.get("elapsed_ms") or 0.0) for row in backend), default=None),
        "backend_max_duration_ms": max(
            (float(row.get("backend_duration_ms") or 0.0) for row in backend_duration_rows),
            default=None,
        ),
        "slowest_frontend_endpoint": _endpoint_ref(slowest_frontend),
        "slowest_backend_endpoint": _endpoint_ref(slowest_backend),
        "slowest_backend_duration_endpoint": _endpoint_ref(slowest_backend_duration),
        "largest_payload_endpoint": _endpoint_ref(largest_payload),
        "cache_stats": cache_stats,
        "routes": [_endpoint_ref(row) for row in results],
    }


def collect_audit(
    *,
    base_url: str,
    backend_url: str | None = None,
    timeout_seconds: float = 15.0,
    fetcher: Fetcher = fetch_url,
) -> dict[str, Any]:
    base_url = base_url.strip().rstrip("/")
    backend_url = backend_url.strip().rstrip("/") if backend_url else None
    endpoints = [
        measure_endpoint(spec, base_url=target_base, timeout_seconds=timeout_seconds, fetcher=fetcher)
        for spec, target_base in build_endpoint_plan(base_url, backend_url)
    ]
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "trading_desk_api_performance_audit",
        "read_only": True,
        "base_urls": {
            "frontend": base_url,
            "python_backend": backend_url,
        },
        "endpoints": endpoints,
        "summary": summarize_results(endpoints),
    }


def write_outputs(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"trading_desk_api_performance_{stamp}.json"
    latest_path = output_dir / "trading_desk_api_performance_latest.json"
    text = json.dumps(payload, indent=2, sort_keys=True)
    json_path.write_text(text + "\n", encoding="utf8")
    latest_path.write_text(text + "\n", encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit read-only Trading Desk API latency, payload windows, and cache stats.")
    parser.add_argument("--base-url", default=DEFAULT_FRONTEND_BASE_URL, help="Next.js app base URL.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_BASE_URL, help="FastAPI backend base URL for direct comparisons and cache stats.")
    parser.add_argument("--no-backend", action="store_true", help="Skip direct FastAPI probes.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    backend_url = None if args.no_backend else (args.backend_url or None)
    audit = collect_audit(base_url=args.base_url, backend_url=backend_url, timeout_seconds=args.timeout)
    payload: dict[str, Any] = {"audit": audit}
    if not args.no_write:
        payload["artifacts"] = write_outputs(audit, output_dir=args.output_dir)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(audit["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
