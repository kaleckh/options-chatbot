from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


PositionPayload = dict[str, Any]
PositionRow = dict[str, Any]
ReviewPayload = dict[str, Any]


TRACKING_REPOSITORY_REQUIRED_METHODS = (
    "init_schema",
    "create_position",
    "list_positions",
    "get_position",
    "save_review",
    "close_position",
)
TRACKED_POSITIONS_REQUIRED_METHODS = (
    *TRACKING_REPOSITORY_REQUIRED_METHODS,
    "update_position",
    "get_realized_pnl_since",
)
TRACKED_POSITIONS_OPTIONAL_METHODS = (
    "list_compact_positions",
    "profit_status_snapshot",
)
SUGGESTED_TRADES_REQUIRED_METHODS = TRACKING_REPOSITORY_REQUIRED_METHODS


@runtime_checkable
class RepositoryAvailability(Protocol):
    is_available: bool
    error_message: Optional[str]

    def init_schema(self) -> bool:
        ...


@runtime_checkable
class TradingDeskPositionRepository(RepositoryAvailability, Protocol):
    def create_position(self, payload: PositionPayload) -> PositionRow:
        ...

    def list_positions(
        self,
        status: Optional[str] = "open",
        *,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[PositionRow]:
        ...

    def get_position(self, position_id: int) -> Optional[PositionRow]:
        ...

    def save_review(self, position_id: int, review: ReviewPayload) -> PositionRow:
        ...

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        closed_at: datetime,
        exit_reason: str,
        notes: Optional[str] = None,
        *,
        exit_execution_basis: str = "manual_close",
        allow_zero_exit_price: bool = False,
    ) -> Optional[PositionRow]:
        ...


@runtime_checkable
class TrackedPositionsRepository(TradingDeskPositionRepository, Protocol):
    def update_position(self, position_id: int, updates: dict[str, Any]) -> PositionRow:
        ...

    def get_realized_pnl_since(self, since: datetime) -> float:
        ...


@runtime_checkable
class SuggestedTradesRepository(TradingDeskPositionRepository, Protocol):
    pass


@runtime_checkable
class SupportsCompactPositionList(Protocol):
    def list_compact_positions(
        self,
        status: Optional[str] = "open",
        *,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[PositionRow]:
        ...


@runtime_checkable
class SupportsProfitStatusSnapshot(Protocol):
    def profit_status_snapshot(self) -> dict[str, Any]:
        ...


@runtime_checkable
class SupportsPositionUpdate(Protocol):
    def update_position(self, position_id: int, updates: dict[str, Any]) -> PositionRow:
        ...


@runtime_checkable
class SupportsRealizedPnl(Protocol):
    def get_realized_pnl_since(self, since: datetime) -> float:
        ...
