from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LEDGER_PATH = ROOT_DIR / "data" / "forward-tracking" / "alpaca_paper_order_events.jsonl"
PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
TRUTHY_VALUES = {"1", "true", "yes", "on"}
ORDER_FILLED_STATUSES = {"filled", "partially_filled"}
ORDER_REJECTED_STATUSES = {"rejected", "expired"}
ORDER_CANCELED_STATUSES = {"canceled", "cancelled"}


class AlpacaPaperTradingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

    def public_payload(self) -> dict[str, Any]:
        payload = {"message": str(self)}
        if self.details:
            payload["details"] = self.details
        return payload


def _env_flag(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in TRUTHY_VALUES


def alpaca_paper_execution_enabled() -> bool:
    return _env_flag("OPTIONS_ALPACA_PAPER_TRADING_ENABLED") or _env_flag("ALPACA_PAPER_TRADING_ENABLED")


def _env_text(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _credentials() -> tuple[str, str]:
    return (
        _env_text("APCA_API_KEY_ID", "ALPACA_API_KEY_ID"),
        _env_text("APCA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY"),
    )


def _paper_base_url() -> str:
    base_url = _env_text("ALPACA_TRADING_ENDPOINT", "APCA_API_BASE_URL") or PAPER_BASE_URL
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v2"):
        base_url = f"{base_url}/v2"
    return base_url


def _ensure_paper_base_url(base_url: str) -> None:
    if _env_flag("ALPACA_PAPER_TRADING_ALLOW_CUSTOM_BASE_URL"):
        return
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "paper-api.alpaca.markets":
        raise AlpacaPaperTradingError(
            "Alpaca paper execution is restricted to https://paper-api.alpaca.markets/v2.",
            status_code=400,
            details={"base_url": base_url},
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _price_string(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None or parsed <= 0:
        raise AlpacaPaperTradingError(
            "Alpaca paper orders require a positive limit price.",
            status_code=400,
        )
    return f"{parsed:.4f}".rstrip("0").rstrip(".")


def _source_snapshot(position_payload: dict[str, Any]) -> dict[str, Any]:
    source = position_payload.get("source_pick_snapshot")
    return source if isinstance(source, dict) else {}


def _contract_symbol_from_payload(position_payload: dict[str, Any]) -> str:
    source = _source_snapshot(position_payload)
    return str(
        position_payload.get("contract_symbol")
        or source.get("contract_symbol")
        or source.get("option_contract_symbol")
        or ""
    ).strip().upper()


def _short_contract_symbol_from_payload(position_payload: dict[str, Any]) -> str:
    source = _source_snapshot(position_payload)
    return str(
        source.get("short_contract_symbol")
        or source.get("short_option_contract_symbol")
        or ""
    ).strip().upper()


def _strategy_type(position_payload: dict[str, Any]) -> str:
    source = _source_snapshot(position_payload)
    explicit = str(source.get("strategy_type") or "").strip().lower()
    if explicit:
        return explicit
    if _short_contract_symbol_from_payload(position_payload):
        return "vertical_spread"
    return "single_leg"


def _client_order_id(position_payload: dict[str, Any]) -> str:
    source = _source_snapshot(position_payload)
    fingerprint = json.dumps(
        {
            "run": source.get("source_scan_run_id") or position_payload.get("source_scan_run_id"),
            "event": source.get("source_scan_event_key") or position_payload.get("source_scan_event_key"),
            "ticker": position_payload.get("ticker"),
            "direction": position_payload.get("direction"),
            "expiry": str(position_payload.get("expiry")),
            "contract": _contract_symbol_from_payload(position_payload),
            "short_contract": _short_contract_symbol_from_payload(position_payload),
            "limit": position_payload.get("entry_execution_price") or position_payload.get("entry_option_price"),
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:40]
    return f"opt-paper-{digest}"


def _validate_position_payload_for_order(position_payload: dict[str, Any]) -> None:
    if not bool(position_payload.get("proof_eligible")):
        raise AlpacaPaperTradingError(
            "Alpaca paper execution blocked: the tracked-position payload is not proof eligible.",
            status_code=409,
            details={"proof_ineligibility_reason": position_payload.get("proof_ineligibility_reason")},
        )
    contracts = int(position_payload.get("contracts") or 0)
    if contracts != 1:
        raise AlpacaPaperTradingError(
            "Alpaca paper execution is capped at exactly 1 contract per trade.",
            status_code=400,
            details={"contracts": contracts},
        )
    if not _contract_symbol_from_payload(position_payload):
        raise AlpacaPaperTradingError(
            "Alpaca paper execution requires an exact option contract symbol.",
            status_code=400,
        )


def build_alpaca_order_payload(position_payload: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(position_payload)
    _validate_position_payload_for_order(payload)
    limit_price = _price_string(payload.get("entry_execution_price") or payload.get("entry_option_price"))
    client_order_id = _client_order_id(payload)
    contract_symbol = _contract_symbol_from_payload(payload)

    if _strategy_type(payload) == "vertical_spread":
        short_contract_symbol = _short_contract_symbol_from_payload(payload)
        if not short_contract_symbol:
            raise AlpacaPaperTradingError(
                "Alpaca paper spread orders require both long and short contract symbols.",
                status_code=400,
            )
        return {
            "order_class": "mleg",
            "client_order_id": client_order_id,
            "qty": "1",
            "type": "limit",
            "limit_price": limit_price,
            "time_in_force": "day",
            "legs": [
                {
                    "symbol": contract_symbol,
                    "ratio_qty": "1",
                    "side": "buy",
                    "position_intent": "buy_to_open",
                },
                {
                    "symbol": short_contract_symbol,
                    "ratio_qty": "1",
                    "side": "sell",
                    "position_intent": "sell_to_open",
                },
            ],
        }

    return {
        "client_order_id": client_order_id,
        "symbol": contract_symbol,
        "qty": "1",
        "side": "buy",
        "position_intent": "buy_to_open",
        "type": "limit",
        "limit_price": limit_price,
        "time_in_force": "day",
    }


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    override = os.getenv("ALPACA_PAPER_ORDER_LEDGER_PATH")
    if override:
        return Path(override)
    return DEFAULT_EVENT_LEDGER_PATH


def record_alpaca_paper_order_event(event: dict[str, Any], *, ledger_path: Path | str | None = None) -> dict[str, Any]:
    row = {
        "recorded_at_utc": _now_iso(),
        **event,
    }
    path = _ledger_path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row


def _status_from_response(response_payload: dict[str, Any]) -> str:
    return str(response_payload.get("status") or "").strip().lower()


def _response_event_type(status: str, *, http_status_code: int) -> str:
    if http_status_code >= 400:
        return "rejected"
    if status in ORDER_REJECTED_STATUSES:
        return "rejected"
    if status in ORDER_FILLED_STATUSES:
        return "filled"
    if status in ORDER_CANCELED_STATUSES:
        return "cancelled"
    return "accepted"


def _response_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": getattr(response, "text", "")}
    return payload if isinstance(payload, dict) else {"payload": payload}


def _order_metadata(order_payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "alpaca",
        "environment": "paper",
        "client_order_id": order_payload.get("client_order_id"),
        "order_id": response_payload.get("id"),
        "status": response_payload.get("status"),
        "symbol": response_payload.get("symbol") or order_payload.get("symbol"),
        "order_class": response_payload.get("order_class") or order_payload.get("order_class") or "simple",
        "type": response_payload.get("type") or order_payload.get("type"),
        "qty": response_payload.get("qty") or order_payload.get("qty"),
        "limit_price": response_payload.get("limit_price") or order_payload.get("limit_price"),
        "filled_qty": response_payload.get("filled_qty"),
        "filled_avg_price": response_payload.get("filled_avg_price"),
        "submitted_at": response_payload.get("submitted_at"),
        "filled_at": response_payload.get("filled_at"),
        "canceled_at": response_payload.get("canceled_at"),
    }


def submit_alpaca_paper_order(
    position_payload: dict[str, Any],
    *,
    post: Callable[..., Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    if not alpaca_paper_execution_enabled():
        raise AlpacaPaperTradingError(
            "Alpaca paper execution is disabled. Set OPTIONS_ALPACA_PAPER_TRADING_ENABLED=1 to enable it.",
            status_code=409,
        )
    api_key, secret_key = _credentials()
    if not api_key or not secret_key:
        raise AlpacaPaperTradingError(
            "Alpaca paper execution requires APCA_API_KEY_ID and APCA_API_SECRET_KEY.",
            status_code=400,
        )
    base_url = _paper_base_url()
    _ensure_paper_base_url(base_url)
    order_payload = build_alpaca_order_payload(position_payload)
    submitted_event = record_alpaca_paper_order_event(
        {
            "event_type": "submitted",
            "provider": "alpaca",
            "environment": "paper",
            "client_order_id": order_payload.get("client_order_id"),
            "order_payload": order_payload,
            "source_scan_run_id": position_payload.get("source_scan_run_id"),
            "source_scan_event_key": position_payload.get("source_scan_event_key"),
        },
        ledger_path=ledger_path,
    )

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "accept": "application/json",
        "content-type": "application/json",
    }
    url = f"{base_url}/orders"
    post_fn = post or httpx.post
    try:
        response = post_fn(url, headers=headers, json=order_payload, timeout=15.0)
    except Exception as exc:
        record_alpaca_paper_order_event(
            {
                "event_type": "rejected",
                "provider": "alpaca",
                "environment": "paper",
                "client_order_id": order_payload.get("client_order_id"),
                "error": str(exc),
                "submitted_event_recorded_at_utc": submitted_event["recorded_at_utc"],
            },
            ledger_path=ledger_path,
        )
        raise AlpacaPaperTradingError(
            "Alpaca paper order submission failed before Alpaca accepted the request.",
            status_code=502,
            details={"error": str(exc)},
        ) from exc

    status_code = int(getattr(response, "status_code", 0) or 0)
    response_payload = _response_json(response)
    status = _status_from_response(response_payload)
    event_type = _response_event_type(status, http_status_code=status_code)
    response_event = record_alpaca_paper_order_event(
        {
            "event_type": event_type,
            "provider": "alpaca",
            "environment": "paper",
            "client_order_id": order_payload.get("client_order_id"),
            "order_id": response_payload.get("id"),
            "order_status": response_payload.get("status"),
            "http_status_code": status_code,
            "order_response": response_payload,
            "submitted_event_recorded_at_utc": submitted_event["recorded_at_utc"],
        },
        ledger_path=ledger_path,
    )
    if status_code >= 400 or event_type == "rejected":
        raise AlpacaPaperTradingError(
            "Alpaca paper order was rejected.",
            status_code=502,
            details={"http_status_code": status_code, "order_response": response_payload},
        )
    return {
        "order_payload": order_payload,
        "order_response": response_payload,
        "metadata": _order_metadata(order_payload, response_payload),
        "events": [submitted_event, response_event],
        "event_ledger_path": str(_ledger_path(ledger_path)),
    }


def apply_alpaca_order_result_to_position_payload(
    position_payload: dict[str, Any],
    order_result: dict[str, Any],
) -> dict[str, Any]:
    payload = copy.deepcopy(position_payload)
    source = copy.deepcopy(_source_snapshot(payload))
    metadata = copy.deepcopy(order_result.get("metadata") or {})
    metadata["event_ledger_path"] = order_result.get("event_ledger_path")
    metadata["proof_gate_class_before_order"] = payload.get("proof_class")
    source["alpaca_paper_order"] = metadata
    source["paper_broker"] = "alpaca"
    source["broker_execution_mode"] = "alpaca_paper"
    payload["source_pick_snapshot"] = source

    filled_price = _safe_float(metadata.get("filled_avg_price"))
    if filled_price is not None and filled_price > 0:
        payload["entry_option_price"] = round(filled_price, 4)
        payload["entry_execution_price"] = round(filled_price, 4)
        payload["entry_execution_basis"] = "alpaca_paper_fill"
        filled_at = metadata.get("filled_at")
        if filled_at:
            payload["filled_at"] = filled_at
    else:
        payload["entry_execution_basis"] = "alpaca_paper_limit_order"

    notes = str(payload.get("notes") or "").strip()
    client_order_id = str(metadata.get("client_order_id") or "").strip()
    order_note = f"Alpaca paper order {client_order_id} submitted."
    payload["notes"] = f"{notes}\n{order_note}".strip() if notes else order_note
    return payload


def record_alpaca_position_link_event(
    *,
    position: dict[str, Any],
    order_result: dict[str, Any],
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    metadata = order_result.get("metadata") or {}
    return record_alpaca_paper_order_event(
        {
            "event_type": "tracked_position_linked",
            "provider": "alpaca",
            "environment": "paper",
            "client_order_id": metadata.get("client_order_id"),
            "order_id": metadata.get("order_id"),
            "tracked_position_id": position.get("id"),
            "tracked_position_status": position.get("status"),
            "contract_symbol": position.get("contract_symbol"),
        },
        ledger_path=ledger_path,
    )
