from __future__ import annotations

import json
from urllib.parse import urlparse

from scripts.audit_trading_desk_api_performance import (
    BACKEND_DURATION_HEADER,
    collect_audit,
    summarize_results,
)


def test_collect_audit_measures_payload_windows_and_cache_stats():
    def fake_fetch(url: str, timeout_seconds: float):
        del timeout_seconds
        parsed = urlparse(url)
        path = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
        headers = {BACKEND_DURATION_HEADER: "12.4"}
        if path == "/api/positions?status=open&compact=1":
            payload = {"positions": [{"id": 1}, {"id": 2}]}
        elif path == "/api/positions?status=closed&limit=100&offset=0&compact=1":
            payload = {"positions": [{"id": 3}], "page": {"limit": 100, "offset": 0, "returned": 1}}
        elif path == "/api/suggested-trades?status=open&compact=1":
            payload = {"trades": [{"id": 10}]}
        elif path == "/api/suggested-trades?status=closed&limit=100&offset=0&compact=1":
            payload = {"trades": [], "page": {"limit": 100, "offset": 0, "returned": 0}}
        elif path == "/api/market-data/cache-stats":
            payload = {
                "status": "ok",
                "memory_cache_entries": 7,
                "request_scope_active": False,
                "request_scope_entries": 0,
                "schema_initialized": True,
                "totals": {"hit": 4, "miss": 2},
            }
        else:
            payload = {"status": "ok"}
        return 200, headers, json.dumps(payload).encode("utf8"), None

    audit = collect_audit(
        base_url="http://next.test",
        backend_url="http://backend.test",
        timeout_seconds=1.0,
        fetcher=fake_fetch,
    )

    assert audit["read_only"] is True
    assert audit["summary"]["status"] == "ok"
    assert audit["summary"]["error_endpoint_count"] == 0
    assert audit["summary"]["ok_endpoint_count"] == len(audit["endpoints"])
    assert audit["summary"]["backend_max_duration_ms"] == 12.4
    assert audit["summary"]["cache_stats"]["memory_cache_entries"] == 7

    closed_window = next(row for row in audit["endpoints"] if row["label"] == "next_tracked_positions_closed_page_100")
    assert closed_window["row_count"] == 1
    assert closed_window["page"] == {"limit": 100, "offset": 0, "returned": 1}
    assert closed_window["window"] == {"status": "closed", "limit": "100", "offset": "0", "compact": "1"}
    assert closed_window["backend_duration_ms"] == 12.4


def test_summarize_results_marks_route_errors_without_throwing():
    summary = summarize_results(
        [
            {
                "label": "next_tracked_positions_open",
                "target": "next_route",
                "path": "/api/positions?status=open",
                "ok": False,
                "status_code": None,
                "elapsed_ms": 4.0,
                "backend_duration_ms": None,
                "payload_bytes": 0,
                "row_count": None,
                "page": None,
            },
            {
                "label": "next_suggested_trades_open",
                "target": "next_route",
                "path": "/api/suggested-trades?status=open",
                "ok": True,
                "status_code": 200,
                "elapsed_ms": 3.0,
                "backend_duration_ms": 2.0,
                "payload_bytes": 120,
                "row_count": 1,
                "page": None,
            },
        ]
    )

    assert summary["status"] == "route_errors"
    assert summary["endpoint_count"] == 2
    assert summary["ok_endpoint_count"] == 1
    assert summary["error_endpoint_count"] == 1
    assert summary["largest_payload_endpoint"]["label"] == "next_suggested_trades_open"
