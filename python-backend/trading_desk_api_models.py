from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError


class TradingDeskRequestModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    def to_legacy_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class CreateTradingDeskRecordBody(TradingDeskRequestModel):
    scan_pick: dict[str, Any] | None = None
    fill_price: Any = None
    contracts: Any = None
    filled_at: Any = None
    notes: Any = None
    creation_mode: Any = None
    execute_alpaca_paper: Any = None


class ReviewTradingDeskRecordsBody(TradingDeskRequestModel):
    position_ids: Any = None


class CloseTradingDeskRecordBody(TradingDeskRequestModel):
    exit_price: Any = None
    closed_at: Any = None
    notes: Any = None


class TradingDeskEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrackedPositionEnvelope(TradingDeskEnvelopeModel):
    position: dict[str, Any]
    duplicate: bool | None = None
    position_event_persistence: dict[str, Any] | None = None


class TrackedPositionsEnvelope(TradingDeskEnvelopeModel):
    positions: list[dict[str, Any]]
    position_event_persistence: dict[str, Any] | None = None


class SuggestedTradeEnvelope(TradingDeskEnvelopeModel):
    trade: dict[str, Any]
    duplicate: bool | None = None


class SuggestedTradesEnvelope(TradingDeskEnvelopeModel):
    trades: list[dict[str, Any]]


BodyModel = TypeVar("BodyModel", bound=TradingDeskRequestModel)


@dataclass(frozen=True)
class TradingDeskApiModelRoute:
    route_id: str
    method: str
    route: str
    lifecycle: str
    store_id: str
    record_class: str
    request_model: str
    response_envelope_model: str
    notes: str


TRADING_DESK_API_MODEL_ROUTES: tuple[TradingDeskApiModelRoute, ...] = (
    TradingDeskApiModelRoute(
        route_id="tracked_positions_create",
        method="POST",
        route="/api/positions",
        lifecycle="create",
        store_id="postgres_tracked_positions",
        record_class="tracked_position",
        request_model="CreateTradingDeskRecordBody",
        response_envelope_model="TrackedPositionEnvelope",
        notes="Request body is modeled, but price/contracts semantics stay in existing route parsers.",
    ),
    TradingDeskApiModelRoute(
        route_id="tracked_positions_review",
        method="POST",
        route="/api/positions/review",
        lifecycle="review",
        store_id="postgres_tracked_positions",
        record_class="tracked_position",
        request_model="ReviewTradingDeskRecordsBody",
        response_envelope_model="TrackedPositionsEnvelope",
        notes="position_ids remains raw so current positive-int list validation and 400 behavior stay unchanged.",
    ),
    TradingDeskApiModelRoute(
        route_id="tracked_positions_close",
        method="POST",
        route="/api/positions/{id}/close",
        lifecycle="close",
        store_id="postgres_tracked_positions",
        record_class="tracked_position",
        request_model="CloseTradingDeskRecordBody",
        response_envelope_model="TrackedPositionEnvelope",
        notes="exit_price and closed_at remain raw so existing close parsers own validation.",
    ),
    TradingDeskApiModelRoute(
        route_id="suggested_trades_create",
        method="POST",
        route="/api/suggested-trades",
        lifecycle="create",
        store_id="sqlite_suggested_trades",
        record_class="suggested_trade",
        request_model="CreateTradingDeskRecordBody",
        response_envelope_model="SuggestedTradeEnvelope",
        notes="Missing contracts remains absent so suggested create keeps the legacy default of 1.",
    ),
    TradingDeskApiModelRoute(
        route_id="suggested_trades_review",
        method="POST",
        route="/api/suggested-trades/review",
        lifecycle="review",
        store_id="sqlite_suggested_trades",
        record_class="suggested_trade",
        request_model="ReviewTradingDeskRecordsBody",
        response_envelope_model="SuggestedTradesEnvelope",
        notes="Suggested review response envelope intentionally has no position_event_persistence.",
    ),
    TradingDeskApiModelRoute(
        route_id="suggested_trades_close",
        method="POST",
        route="/api/suggested-trades/{id}/close",
        lifecycle="close",
        store_id="sqlite_suggested_trades",
        record_class="suggested_trade",
        request_model="CloseTradingDeskRecordBody",
        response_envelope_model="SuggestedTradeEnvelope",
        notes="Suggested close response envelope intentionally has no position_event_persistence.",
    ),
)


def _validation_error_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "request body failed validation"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "body"
    return f"{loc}: {first.get('msg', 'invalid value')}"


def _parse_body(model_type: type[BodyModel], raw_body: dict[str, Any] | None) -> dict[str, Any]:
    if raw_body is None:
        raw_body = {}
    if not isinstance(raw_body, dict):
        raise ValueError("request body must be an object")
    try:
        return model_type.model_validate(raw_body).to_legacy_dict()
    except ValidationError as exc:
        raise ValueError(_validation_error_message(exc)) from exc


def parse_create_trading_desk_record_body(raw_body: dict[str, Any] | None) -> dict[str, Any]:
    return _parse_body(CreateTradingDeskRecordBody, raw_body)


def parse_review_trading_desk_records_body(raw_body: dict[str, Any] | None) -> dict[str, Any]:
    return _parse_body(ReviewTradingDeskRecordsBody, raw_body)


def parse_close_trading_desk_record_body(raw_body: dict[str, Any] | None) -> dict[str, Any]:
    return _parse_body(CloseTradingDeskRecordBody, raw_body)


def trading_desk_api_model_manifest() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "route_id": route.route_id,
            "method": route.method,
            "route": route.route,
            "lifecycle": route.lifecycle,
            "store_id": route.store_id,
            "record_class": route.record_class,
            "request_model": route.request_model,
            "response_envelope_model": route.response_envelope_model,
            "notes": route.notes,
        }
        for route in TRADING_DESK_API_MODEL_ROUTES
    )
